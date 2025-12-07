"""Lane safety checking for safe lane changes.

This module provides functions to check if a lane change is safe
by detecting vehicles in the target lane.
"""

import math
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Modules.Traffic.classes import Vehicle
    from Plugins.Map.classes import Road, Position

import Plugins.Map.data as data
import Plugins.Map.utils.math_helpers as math_helpers

# Safety parameters
LANE_WIDTH = 3.5  # meters - typical lane width
SAFETY_DISTANCE_AHEAD = 30  # meters ahead to check
SAFETY_DISTANCE_BEHIND = 15  # meters behind to check
SAFETY_DISTANCE_BESIDE = 8  # meters beside (for blind spot)

# State tracking
_pending_lane_change = False
_target_lane_index = None
_slow_down_for_lane_change = False


def get_vehicles_from_plugin():
    """Get vehicles from the Traffic module via the plugin."""
    try:
        if data.plugin and hasattr(data.plugin, 'modules') and hasattr(data.plugin.modules, 'Traffic'):
            vehicles = data.plugin.modules.Traffic.run()
            return vehicles if vehicles else []
    except Exception as e:
        logging.debug(f"Could not get traffic data: {e}")
    return []


def distance_point_to_line_segment(point: tuple, line_start: tuple, line_end: tuple) -> float:
    """Calculate the shortest distance from a point to a line segment.

    All coordinates should be (x, z) tuples (ground plane).
    """
    px, pz = point
    x1, z1 = line_start
    x2, z2 = line_end

    # Vector from line_start to line_end
    dx = x2 - x1
    dz = z2 - z1

    # Length squared of the segment
    length_sq = dx * dx + dz * dz

    if length_sq == 0:
        # line_start and line_end are the same point
        return math.sqrt((px - x1) ** 2 + (pz - z1) ** 2)

    # Parameter t for the projection of point onto the line
    t = max(0, min(1, ((px - x1) * dx + (pz - z1) * dz) / length_sq))

    # Closest point on the segment
    closest_x = x1 + t * dx
    closest_z = z1 + t * dz

    return math.sqrt((px - closest_x) ** 2 + (pz - closest_z) ** 2)


def is_vehicle_in_lane(vehicle, lane_points: list, truck_pos: tuple, truck_rotation: float) -> bool:
    """Check if a vehicle is within a lane's area.

    Args:
        vehicle: Vehicle object from Traffic module
        lane_points: List of Position objects defining the lane centerline
        truck_pos: (x, z) tuple of truck position
        truck_rotation: Truck's rotation in radians

    Returns:
        True if vehicle is in the lane area, False otherwise
    """
    if not lane_points or len(lane_points) < 2:
        return False

    vehicle_pos = (vehicle.position.x, vehicle.position.z)

    # Check if vehicle is in front of, beside, or slightly behind the truck
    is_in_front = math_helpers.IsInFront(vehicle_pos, truck_rotation, truck_pos)

    # Calculate distance to truck
    dist_to_truck = math.sqrt(
        (vehicle_pos[0] - truck_pos[0]) ** 2 +
        (vehicle_pos[1] - truck_pos[1]) ** 2
    )

    # Skip vehicles too far away
    max_check_distance = SAFETY_DISTANCE_AHEAD if is_in_front else SAFETY_DISTANCE_BEHIND
    if dist_to_truck > max_check_distance + 10:  # +10 for some margin
        return False

    # Check distance from vehicle to lane centerline
    min_dist_to_lane = float('inf')

    for i in range(len(lane_points) - 1):
        p1 = lane_points[i]
        p2 = lane_points[i + 1]

        dist = distance_point_to_line_segment(
            vehicle_pos,
            (p1.x, p1.z),
            (p2.x, p2.z)
        )
        min_dist_to_lane = min(min_dist_to_lane, dist)

    # Vehicle is in lane if within half lane width of centerline
    return min_dist_to_lane < LANE_WIDTH / 2 + 1  # +1 meter margin


def check_lane_safety(target_lane_index: int, current_lane_index: int, road) -> tuple[bool, float]:
    """Check if it's safe to change to the target lane.

    Args:
        target_lane_index: Index of the lane to change to
        current_lane_index: Index of current lane
        road: Road object with lane information

    Returns:
        Tuple of (is_safe, recommended_speed_factor)
        - is_safe: True if lane change is safe
        - recommended_speed_factor: 0.0-1.0, multiply with current speed limit
    """
    global _pending_lane_change, _target_lane_index, _slow_down_for_lane_change

    if target_lane_index == current_lane_index:
        _pending_lane_change = False
        _slow_down_for_lane_change = False
        return True, 1.0

    # Get vehicles
    vehicles = get_vehicles_from_plugin()
    if not vehicles:
        # No traffic data available - allow lane change
        return True, 1.0

    # Get target lane points
    if not hasattr(road, 'lanes') or target_lane_index >= len(road.lanes):
        return True, 1.0

    target_lane = road.lanes[target_lane_index]
    if not hasattr(target_lane, 'points') or not target_lane.points:
        return True, 1.0

    lane_points = target_lane.points
    truck_pos = (data.truck_x, data.truck_z)
    truck_rotation = data.truck_rotation

    # Check each vehicle
    blocking_vehicles = []
    for vehicle in vehicles:
        if vehicle.position.is_zero():
            continue

        if is_vehicle_in_lane(vehicle, lane_points, truck_pos, truck_rotation):
            vehicle_pos = (vehicle.position.x, vehicle.position.z)
            dist = math.sqrt(
                (vehicle_pos[0] - truck_pos[0]) ** 2 +
                (vehicle_pos[1] - truck_pos[1]) ** 2
            )

            is_in_front = math_helpers.IsInFront(vehicle_pos, truck_rotation, truck_pos)

            # Check if within safety distance
            if is_in_front and dist < SAFETY_DISTANCE_AHEAD:
                blocking_vehicles.append((vehicle, dist, 'ahead'))
            elif not is_in_front and dist < SAFETY_DISTANCE_BEHIND:
                blocking_vehicles.append((vehicle, dist, 'behind'))
            elif dist < SAFETY_DISTANCE_BESIDE:
                blocking_vehicles.append((vehicle, dist, 'beside'))

    if not blocking_vehicles:
        _pending_lane_change = False
        _slow_down_for_lane_change = False
        return True, 1.0

    # Lane change not safe - mark as pending and calculate speed reduction
    _pending_lane_change = True
    _target_lane_index = target_lane_index
    _slow_down_for_lane_change = True

    # Find closest blocking vehicle
    closest_dist = min(v[1] for v in blocking_vehicles)

    # Calculate speed reduction factor based on distance
    # At 30m: factor = 1.0 (no reduction)
    # At 15m: factor = 0.7
    # At 5m: factor = 0.3
    speed_factor = min(1.0, max(0.3, closest_dist / SAFETY_DISTANCE_AHEAD))

    logging.debug(f"Lane change blocked: {len(blocking_vehicles)} vehicles in target lane, "
                  f"closest at {closest_dist:.1f}m, speed factor: {speed_factor:.2f}")

    return False, speed_factor


def is_waiting_for_lane_change() -> bool:
    """Check if we're waiting for a safe lane change opportunity."""
    return _pending_lane_change


def get_lane_change_speed_factor() -> float:
    """Get the recommended speed factor when waiting for lane change.

    Returns 1.0 if not waiting, or a lower value if we need to slow down.
    """
    if not _slow_down_for_lane_change:
        return 1.0

    # Re-check safety to get current speed factor
    # This will be called from the speed control system
    return 0.5  # Default reduction while waiting


def reset_lane_change_state():
    """Reset the lane change waiting state."""
    global _pending_lane_change, _target_lane_index, _slow_down_for_lane_change
    _pending_lane_change = False
    _target_lane_index = None
    _slow_down_for_lane_change = False
