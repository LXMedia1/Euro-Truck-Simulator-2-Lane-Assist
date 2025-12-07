import Plugins.Map.utils.math_helpers as math_helpers
from Plugins.Map import classes as c
from typing import List, TypeVar
import logging

T = TypeVar("T")

# NavGraph debug logger - use the same logger as classes.py
navgraph_logger = logging.getLogger("Map.NavGraph")


def get_connecting_item_uid(node_1, node_2) -> int:
    """Will return the connecting item between two nodes, or None if they are not connected.

    :param c.Node node_1: The first node.
    :param c.Node node_2: The second node.

    :return: The UID of the connecting item.
    """
    node_1_forward_item = node_1.forward_item_uid
    node_1_backward_item = node_1.backward_item_uid
    node_2_forward_item = node_2.forward_item_uid
    node_2_backward_item = node_2.backward_item_uid

    # Check each possible connection, but exclude 0 and None as valid UIDs
    # (0 is used as a sentinel value meaning "no item")
    if node_1_forward_item and node_1_forward_item == node_2_backward_item:
        return node_1_forward_item
    elif node_1_backward_item and node_1_backward_item == node_2_forward_item:
        return node_1_backward_item
    elif node_1_forward_item and node_1_forward_item == node_2_forward_item:
        return node_1_forward_item
    elif node_1_backward_item and node_1_backward_item == node_2_backward_item:
        return node_1_backward_item

    return None


def rotate_left(arr: List[T], count: int) -> List[T]:
    """Rotate an array to the left by a specified count.

    :param List[T] arr: The array to rotate.
    :param int count: The number of positions to rotate the array to the left.
    :return List[T]: The rotated array.
    """
    assert 0 <= count < len(arr), "count must be within the range of the array length"
    if count == 0:
        return arr
    return arr[count:] + arr[:count]


def rotate_right(arr: List[T], count: int) -> List[T]:
    """Rotate an array to the right by a specified count.

    :param List[T] arr: The array to rotate.
    :param int count: The number of positions to rotate the array to the right.
    :return List[T]: The rotated array.
    """
    assert 0 <= count < len(arr), "count must be within the range of the array length"
    if count == 0:
        return arr
    return arr[-count:] + arr[:-count]


def get_connecting_lanes_by_item(node_1, node_2, item, map_data) -> list[int]:
    """Get the connecting lanes between two nodes based on the item type.

    :param c.Node node_1: The starting node.
    :param c.Node node_2: The ending node.
    :param Item item: The Item instance.
    :param MapData map_data: A mapdata instance to use.
    :return list[int]: The list of connecting lane ids.
    """
    if isinstance(item, c.Road):
        if item.road_look is None:
            navgraph_logger.debug(f"       [Lanes] Road {item.uid}: road_look is None")
            return []
        left_lanes = len(item.road_look.lanes_left)
        right_lanes = len(item.road_look.lanes_right)
        start_node = item.start_node_uid
        navgraph_logger.debug(f"       [Lanes] Road {item.uid}: left={left_lanes}, right={right_lanes}, start_node={start_node}")
        if start_node == node_1.uid:
            lanes = [i for i in range(left_lanes, left_lanes + right_lanes)]
            navgraph_logger.debug(f"       [Lanes] Road direction: forward (node_1 is start), lanes={lanes}")
            return lanes
        else:
            if left_lanes > 0:
                lanes = [i for i in range(0, left_lanes)]
                navgraph_logger.debug(f"       [Lanes] Road direction: backward (using left lanes), lanes={lanes}")
                return lanes
            else:
                lanes = [i for i in range(0, right_lanes)]
                navgraph_logger.debug(f"       [Lanes] Road direction: backward (no left lanes, using right), lanes={lanes}")
                return lanes

    elif isinstance(item, c.Prefab):
        description = item.prefab_description
        if description is None:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: prefab_description is None")
            return []

        navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: token={item.token}, origin_index={item.origin_node_index}")
        navgraph_logger.debug(f"       [Lanes] Prefab node_uids: {item.node_uids}")

        item_nodes = [map_data.get_node_by_uid(uid) for uid in item.node_uids]
        none_nodes = [i for i, n in enumerate(item_nodes) if n is None]
        if none_nodes:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: Some nodes not found at indices {none_nodes}")

        rotated_nodes = (
            rotate_right(  # match the nodes to the nodes in the prefab description
                item_nodes, item.origin_node_index
            )
        )
        navgraph_logger.debug(f"       [Lanes] Rotated nodes UIDs: {[n.uid if n else None for n in rotated_nodes]}")

        try:
            node_1_matches = [i for i, n in enumerate(rotated_nodes) if n and n.uid == node_1.uid]
            if not node_1_matches:
                navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: node_1 ({node_1.uid}) NOT FOUND in rotated nodes")
                return []
            node_1_index = node_1_matches[0]
            start_prefab_node = description.nodes[node_1_index]

            node_2_matches = [i for i, n in enumerate(rotated_nodes) if n and n.uid == node_2.uid]
            if not node_2_matches:
                navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: node_2 ({node_2.uid}) NOT FOUND in rotated nodes")
                return []
            node_2_index = node_2_matches[0]
            end_prefab_node = description.nodes[node_2_index]

            navgraph_logger.debug(f"       [Lanes] Prefab indices: node_1_idx={node_1_index}, node_2_idx={node_2_index}")
            navgraph_logger.debug(f"       [Lanes] Start node input_lanes: {start_prefab_node.input_lanes}")
            navgraph_logger.debug(f"       [Lanes] End node output_lanes: {end_prefab_node.output_lanes}")

        except Exception as e:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: Exception finding nodes: {e}")
            return []

        if node_1_index == node_2_index:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: node_1 and node_2 have same index ({node_1_index})")
            return []

        routes = description.nav_routes
        navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: checking {len(routes)} nav_routes")

        if not routes:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: NO NAV_ROUTES available")
            return []

        accepted_routes = []
        for i, route in enumerate(routes):
            start_found = False
            end_found = False
            for curve in route.curves:
                try:
                    index = description.nav_curves.index(curve)
                except ValueError:
                    continue

                if index in start_prefab_node.input_lanes:
                    start_found = True
                if index in end_prefab_node.output_lanes and start_found:
                    end_found = True
                    break

            if start_found and end_found:
                accepted_routes.append(i)
            else:
                navgraph_logger.debug(f"       [Lanes] Route {i}: start_found={start_found}, end_found={end_found}")

        if not accepted_routes:
            navgraph_logger.debug(f"       [Lanes] Prefab {item.uid}: No routes found connecting nodes")
            navgraph_logger.debug(f"       [Lanes] Available nav_curves count: {len(description.nav_curves)}")
            navgraph_logger.debug(f"       [Lanes] Description nodes count: {len(description.nodes)}")

        return accepted_routes
    else:
        navgraph_logger.debug(f"       [Lanes] Unknown item type: {type(item).__name__}")
        return []


def get_nav_node_for_entry_and_node(entry, node):
    """Get a navigation node for a node in a given entry.

    :param c.NavigationEntry entry: The navigation entry to use.
    :param c.Node node: The node to look for.
    """
    possibilities = []
    if isinstance(entry, c.NavigationEntry):
        for nav_node in entry.forward:
            if nav_node.node_id == node.uid:
                possibilities.append(nav_node)
        for nav_node in entry.backward:
            if nav_node.node_id == node.uid:
                possibilities.append(nav_node)
    else:
        raise ValueError("entry must be a NavigationEntry instance")

    return possibilities


def get_surrounding_nav_nodes(route_nodes, x: float, z: float, rotation: float):
    """Get the surrounding (last, next) navigation nodes around the player.

    :param list[RouteNode] route_nodes: The list of route nodes.
    """
    position = (x, z)
    path = [route.node for route in route_nodes]
    distance_ordered = sorted(
        path,
        key=lambda node: math_helpers.DistanceBetweenPoints((node.x, node.y), position),
    )

    closest: c.Node = distance_ordered[0]
    # Check if it's behind or in front
    in_front = math_helpers.IsInFront((closest.x, closest.y), rotation, position)
    index = path.index(closest)
    if not in_front:
        lower_bound = index
        upper_bound = min(len(path), index + 2)
    else:
        lower_bound = max(0, index - 1)
        if lower_bound == 0:
            upper_bound = index + 2
        else:
            upper_bound = index + 1

    # Get the last and next node
    closest_nodes: list[c.Node] = path[lower_bound:upper_bound]
    in_front = [
        math_helpers.IsInFront((node.x, node.y), rotation, position)
        for node in closest_nodes
    ]

    try:
        last = closest_nodes[in_front.index(False)]
        next = closest_nodes[in_front.index(True)]
    except Exception:
        return None, None

    return last, next
