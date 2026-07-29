"""Unicritical-family dynamics provided by the C backend."""

from __future__ import annotations

import ctypes as ct
import math

from .c_api import CComplex, last_error, lib, require_success
from .high_precision import (
    attracting_critical_orbit_arbitrary,
    escape_radius_arbitrary,
    is_arbitrary,
    unicritical_map_arbitrary,
)

ESCAPE_RADIUS = 2.0


def unicritical_map(
    value: complex,
    parameter: complex,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> complex:
    if is_arbitrary(value) or is_arbitrary(parameter):
        return unicritical_map_arbitrary(
            value,
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
    output = CComplex()
    status = lib.loom_unicritical_map(
        CComplex.from_python(value),
        CComplex.from_python(parameter),
        degree,
        int(antiholomorphic),
        ct.byref(output),
    )
    require_success(status)
    return output.to_python()


def anti_quadratic(value: complex, parameter: complex) -> complex:
    return unicritical_map(value, parameter)


def escape_radius(parameter: complex, degree: int) -> float:
    if is_arbitrary(parameter):
        return escape_radius_arbitrary(parameter, degree)
    result = lib.loom_escape_radius(CComplex.from_python(parameter), degree)
    if not math.isfinite(result):
        raise ValueError(last_error())
    return result


def attracting_critical_orbit(
    parameter: complex,
    *,
    max_steps: int = 4096,
    max_period: int = 64,
    tolerance: float = 1e-9,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[complex, ...] | None:
    if is_arbitrary(parameter):
        return attracting_critical_orbit_arbitrary(
            parameter,
            max_steps=max_steps,
            max_period=max_period,
            tolerance=tolerance,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
    array_type = CComplex * max_period
    cycle = array_type()
    count = ct.c_size_t()
    status = lib.loom_attracting_critical_orbit(
        CComplex.from_python(parameter),
        max_steps,
        max_period,
        tolerance,
        degree,
        int(antiholomorphic),
        cycle,
        max_period,
        ct.byref(count),
    )
    if status < 0:
        raise ValueError(last_error())
    if status == 0:
        return None
    return tuple(cycle[index].to_python() for index in range(count.value))
