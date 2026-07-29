"""Internal Koenigs/Böttcher curves generated entirely by C."""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass

from .c_api import (
    CComplex,
    CInternalCurveResult,
    complex_array,
    last_error,
    lib,
)


@dataclass(frozen=True)
class InternalCurve:
    log_radius: float
    polylines: tuple[tuple[complex, ...], ...]
    representative: bool


@dataclass(frozen=True)
class InternalCurveSet:
    coordinate_kind: str
    return_period: int
    curves: tuple[InternalCurve, ...]


def trace_internal_grand_orbit(
    parameter: complex,
    cycle: tuple[complex, ...],
    bounds: tuple[float, float, float, float],
    *,
    representative_log_radius: float = -1.0,
    generations: int = 4,
    resolution: int = 240,
    max_returns: int = 48,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> InternalCurveSet:
    c_cycle = complex_array(cycle)
    xmin, xmax, ymin, ymax = bounds
    result = CInternalCurveResult()
    status = lib.loom_trace_internal_grand_orbit(
        CComplex.from_python(parameter),
        c_cycle,
        len(cycle),
        xmin,
        xmax,
        ymin,
        ymax,
        representative_log_radius,
        generations,
        resolution,
        max_returns,
        degree,
        int(antiholomorphic),
        ct.byref(result),
    )
    if status != 0:
        lib.loom_free_internal_curve_result(ct.byref(result))
        raise ValueError(last_error())
    try:
        curves: list[InternalCurve] = []
        for curve_index in range(result.curve_count):
            c_curve = result.curves[curve_index]
            polylines: list[tuple[complex, ...]] = []
            for offset in range(c_curve.polyline_count):
                c_polyline = result.polylines[c_curve.first_polyline + offset]
                points = tuple(
                    result.points[c_polyline.first_point + point_index].to_python()
                    for point_index in range(c_polyline.point_count)
                )
                polylines.append(points)
            curves.append(
                InternalCurve(
                    c_curve.log_radius,
                    tuple(polylines),
                    bool(c_curve.representative),
                )
            )
        kind = {1: "Böttcher", 2: "Koenigs"}.get(
            result.coordinate_kind,
            "Unknown",
        )
        return InternalCurveSet(kind, result.return_period, tuple(curves))
    finally:
        lib.loom_free_internal_curve_result(ct.byref(result))
