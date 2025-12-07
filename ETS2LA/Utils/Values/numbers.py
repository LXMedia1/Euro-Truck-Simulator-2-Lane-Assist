# type: ignore
# TODO: Make this file type-safe.
from typing import Literal, Tuple
from collections import deque
import time


class SmoothedValue:
    valueArray: deque[float] | deque[Tuple[int, float]]
    smoothingType: Literal["frames", "time"]
    smoothingAmount: int | float

    def __init__(
        self,
        smoothingType: Literal["frames", "time"] = "frames",
        smoothingAmount: int | float = 10,
    ) -> None:
        self.smoothingType = smoothingType
        self.smoothingAmount = smoothingAmount
        if smoothingType == "frames":
            # deque with maxlen auto-discards oldest (O(1) vs O(n) for list.pop(0))
            self.valueArray = deque([0], maxlen=int(smoothingAmount))
        elif smoothingType == "time":
            # Time-based: use deque for O(1) popleft(), no maxlen since it's time-based
            self.valueArray = deque([[time.perf_counter(), 0]])

    def get(self):
        if self.smoothingType == "frames":
            return sum(self.valueArray) / len(self.valueArray)
        elif self.smoothingType == "time":
            while len(self.valueArray) > 1 and self.valueArray[-1][0] - self.valueArray[0][0] > self.smoothingAmount:
                self.valueArray.popleft()  # O(1) instead of O(n)
            if len(self.valueArray) == 0:
                return 0
            return sum([v for t, v in self.valueArray]) / len(self.valueArray)
        else:
            raise ValueError("Invalid smoothing type")

    def smooth(self, value):
        if self.smoothingType == "frames":
            self.valueArray.append(value)  # deque(maxlen) auto-discards oldest
            return sum(self.valueArray) / len(self.valueArray)
        elif self.smoothingType == "time":
            self.valueArray.append([time.perf_counter(), value])
            while len(self.valueArray) > 1 and self.valueArray[-1][0] - self.valueArray[0][0] > self.smoothingAmount:
                self.valueArray.popleft()  # O(1) instead of O(n)
            return sum([v for t, v in self.valueArray]) / len(self.valueArray)
        else:
            raise ValueError("Invalid smoothing type")

    def zero_percent_jitter(self, side: Literal["upper", "lower"] = "upper"):
        if self.smoothingType == "frames":
            sorted_values = sorted(self.valueArray)
            if side == "upper":
                return sorted_values[int(len(sorted_values) * 0.99)] - sorted_values[0]
            else:
                return sorted_values[0] - sorted_values[int(len(sorted_values) * 0.99)]
        elif self.smoothingType == "time":
            sorted_values = sorted([v for t, v in self.valueArray])
            if side == "upper":
                return sorted_values[int(len(sorted_values) * 0.99)] - sorted_values[0]
            else:
                return sorted_values[0] - sorted_values[int(len(sorted_values) * 0.99)]
        else:
            raise ValueError("Invalid smoothing type")

    def one_percent_jitter(self, side: Literal["upper", "lower"] = "upper"):
        if self.smoothingType == "frames":
            sorted_values = sorted(self.valueArray)
            if side == "upper":
                return (
                    sorted_values[int(len(sorted_values) * 0.99)]
                    - sorted_values[int(len(sorted_values) * 0.01)]
                )
            else:
                return (
                    sorted_values[int(len(sorted_values) * 0.01)]
                    - sorted_values[int(len(sorted_values) * 0.99)]
                )
        elif self.smoothingType == "time":
            sorted_values = sorted([v for t, v in self.valueArray])
            if side == "upper":
                return (
                    sorted_values[int(len(sorted_values) * 0.99)]
                    - sorted_values[int(len(sorted_values) * 0.01)]
                )
            else:
                return (
                    sorted_values[int(len(sorted_values) * 0.01)]
                    - sorted_values[int(len(sorted_values) * 0.99)]
                )
        else:
            raise ValueError("Invalid smoothing type")

    def ten_percent_jitter(self, side: Literal["upper", "lower"] = "upper"):
        if self.smoothingType == "frames":
            sorted_values = sorted(self.valueArray)
            if side == "upper":
                return (
                    sorted_values[int(len(sorted_values) * 0.9)]
                    - sorted_values[int(len(sorted_values) * 0.1)]
                )
            else:
                return (
                    sorted_values[int(len(sorted_values) * 0.1)]
                    - sorted_values[int(len(sorted_values) * 0.9)]
                )
        elif self.smoothingType == "time":
            sorted_values = sorted([v for t, v in self.valueArray])
            if side == "upper":
                return (
                    sorted_values[int(len(sorted_values) * 0.9)]
                    - sorted_values[int(len(sorted_values) * 0.1)]
                )
            else:
                return (
                    sorted_values[int(len(sorted_values) * 0.1)]
                    - sorted_values[int(len(sorted_values) * 0.9)]
                )
        else:
            raise ValueError("Invalid smoothing type")

    def __call__(self, value):
        return self.smooth(value)
