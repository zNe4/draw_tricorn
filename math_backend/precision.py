"""Precision policy shared by the GUI and numerical renderers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class Bounds(Protocol):
    xmin: object
    xmax: object
    ymin: object
    ymax: object


PRECISION_CHOICES = (
    "Automatic",
    "Float (32-bit)",
    "Double (64-bit)",
    "Arbitrary",
)


@dataclass(frozen=True)
class PrecisionDecision:
    mode: str
    bits: int
    required_bits: int

    @property
    def label(self) -> str:
        if self.mode == "arbitrary":
            return f"arbitrary · {self.bits} bits"
        return f"{self.mode} · {self.bits} bits"


def _positive_float(value: object) -> float:
    converted = float(value)
    if converted > 0.0 and math.isfinite(converted):
        return converted
    # Values below binary64 range still unambiguously need arbitrary precision.
    return math.ldexp(1.0, -1074)


def required_coordinate_bits(bounds: Bounds, render_size: int) -> int:
    """Estimate coordinate bits, including guard bits below one screen pixel."""
    if render_size <= 0:
        raise ValueError("Render size must be positive.")
    span = max(bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin)
    magnitude = max(
        abs(bounds.xmin),
        abs(bounds.xmax),
        abs(bounds.ymin),
        abs(bounds.ymax),
        1,
    )
    relative_pixel = _positive_float(span / (render_size * magnitude))
    return max(1, math.ceil(-math.log2(relative_pixel)) + 8)


def precision_decision(
    requested: str,
    bounds: Bounds,
    render_size: int,
) -> PrecisionDecision:
    required = required_coordinate_bits(bounds, render_size)
    if requested == "Float (32-bit)":
        return PrecisionDecision("float", 24, required)
    if requested == "Double (64-bit)":
        return PrecisionDecision("double", 53, required)
    if requested == "Arbitrary":
        return PrecisionDecision("arbitrary", max(80, required + 24), required)
    if requested != "Automatic":
        raise ValueError(f"Unknown precision selection: {requested}")
    if required <= 24:
        return PrecisionDecision("float", 24, required)
    if required <= 53:
        return PrecisionDecision("double", 53, required)
    return PrecisionDecision("arbitrary", max(80, required + 24), required)
