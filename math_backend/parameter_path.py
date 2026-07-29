"""Linear parameter paths used by Julia-set animation controls."""

from __future__ import annotations

from dataclasses import dataclass

import mpmath as mp


@dataclass(frozen=True)
class ParameterPath:
    start: complex | mp.mpc
    end: complex | mp.mpc
    steps: int

    def __post_init__(self) -> None:
        if self.steps < 2 or self.steps > 2000:
            raise ValueError("Animation steps must be between 2 and 2000.")

    def parameter_at(self, index: int) -> mp.mpc:
        if index < 0 or index >= self.steps:
            raise IndexError("Animation frame is outside the parameter path.")
        amount = mp.mpf(index) / (self.steps - 1)
        return mp.mpc(self.start) + amount * (
            mp.mpc(self.end) - mp.mpc(self.start)
        )

    def frame_parameters(self) -> tuple[mp.mpc, ...]:
        return tuple(self.parameter_at(index) for index in range(self.steps))
