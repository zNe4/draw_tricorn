"""External parameter rays backed by native Newton continuation."""

from __future__ import annotations

import cmath
import ctypes as ct
from dataclasses import dataclass
from fractions import Fraction

import mpmath as mp

from .c_api import CComplex, last_error, lib, require_success
from .high_precision import (
    critical_value_orbit_with_derivatives_arbitrary,
    real_newton_parameter_arbitrary,
)

TAU = 2.0 * mp.pi


@dataclass(frozen=True)
class ParameterRayTrace:
    angle: Fraction
    points: tuple[complex, ...]
    residuals: tuple[float, ...]
    requested_samples: int
    stop_reason: str | None = None

    @property
    def final_sample(self) -> complex:
        return self.points[-1]


def critical_value_orbit_with_derivatives(
    parameter: complex,
    depth: int,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[complex, complex, complex]:
    value = CComplex()
    derivative_c = CComplex()
    derivative_conjugate = CComplex()
    status = lib.loom_critical_value_orbit_with_derivatives(
        CComplex.from_python(parameter),
        depth,
        degree,
        int(antiholomorphic),
        ct.byref(value),
        ct.byref(derivative_c),
        ct.byref(derivative_conjugate),
    )
    require_success(status)
    return (
        value.to_python(),
        derivative_c.to_python(),
        derivative_conjugate.to_python(),
    )


def real_newton_parameter(
    target: complex,
    depth: int,
    seed: complex,
    *,
    tolerance: float = 1e-11,
    max_steps: int = 40,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[complex, float, bool]:
    if isinstance(target, mp.mpc) or isinstance(seed, mp.mpc):
        parameter, residual, converged = real_newton_parameter_arbitrary(
            target,
            depth,
            seed,
            tolerance=tolerance,
            max_steps=max_steps,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
        return parameter, residual, converged
    parameter = CComplex()
    residual = ct.c_double()
    converged = ct.c_int()
    status = lib.loom_real_newton_parameter(
        CComplex.from_python(target),
        depth,
        CComplex.from_python(seed),
        tolerance,
        max_steps,
        degree,
        int(antiholomorphic),
        ct.byref(parameter),
        ct.byref(residual),
        ct.byref(converged),
    )
    require_success(status)
    return parameter.to_python(), residual.value, bool(converged.value)


def _trace_parameter_ray_arbitrary(
    angle: Fraction,
    *,
    depth: int,
    sharpness: int,
    outer_radius: float,
    tolerance: float,
    max_newton_steps: int,
    precision_bits: int,
    degree: int,
    antiholomorphic: bool,
) -> ParameterRayTrace:
    normalized = angle % 1
    with mp.workprec(precision_bits):
        angle_value = mp.mpf(normalized.numerator) / normalized.denominator
        radius_value = mp.mpf(outer_radius)
        seed = radius_value * mp.exp(2j * mp.pi * angle_value)
        points: list[complex] = []
        residuals: list[float] = []
        requested = depth * sharpness
        stop_reason: str | None = None
        for sample in range(1, requested + 1):
            iterate_depth = (sample - 1) // sharpness + 1
            exponent = mp.power(degree, -mp.mpf(sample) / sharpness)
            radial = radius_value**exponent
            target_radius = radial ** (degree**iterate_depth)
            multiplier = -degree if antiholomorphic else degree
            target_fraction = (multiplier**iterate_depth * normalized) % 1
            target_angle = (
                mp.mpf(target_fraction.numerator) / target_fraction.denominator
            )
            target = target_radius * mp.exp(2j * mp.pi * target_angle)
            seed, residual, converged = real_newton_parameter_arbitrary(
                target,
                iterate_depth,
                seed,
                tolerance=tolerance,
                max_steps=max_newton_steps,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            residual_float = float(residual)
            if not converged:
                stop_reason = (
                    f"Continuation stopped at sample {sample}/{requested}; "
                    f"Newton residual {residual_float:.3g}."
                )
                break
            points.append(seed)
            residuals.append(residual_float)
    if not points:
        raise ValueError(stop_reason or "Parameter-ray continuation failed.")
    return ParameterRayTrace(
        normalized,
        tuple(points),
        tuple(residuals),
        requested,
        stop_reason,
    )


def trace_parameter_ray(
    angle: Fraction,
    *,
    depth: int = 12,
    sharpness: int = 6,
    outer_radius: float = 4.0,
    tolerance: float = 1e-11,
    max_newton_steps: int = 40,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> ParameterRayTrace:
    normalized = angle % 1
    if precision_bits is not None:
        return _trace_parameter_ray_arbitrary(
            normalized,
            depth=depth,
            sharpness=sharpness,
            outer_radius=outer_radius,
            tolerance=tolerance,
            max_newton_steps=max_newton_steps,
            precision_bits=precision_bits,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
    requested = depth * sharpness
    if requested <= 0:
        requested = 1
    point_type = CComplex * requested
    residual_type = ct.c_double * requested
    points = point_type()
    residuals = residual_type()
    point_count = ct.c_size_t()
    requested_samples = ct.c_size_t()
    stopped_sample = ct.c_int()
    status = lib.loom_trace_parameter_ray(
        float(normalized),
        depth,
        sharpness,
        outer_radius,
        tolerance,
        max_newton_steps,
        degree,
        int(antiholomorphic),
        points,
        residuals,
        requested,
        ct.byref(point_count),
        ct.byref(requested_samples),
        ct.byref(stopped_sample),
    )
    failed_residual = (
        float(residuals[point_count.value])
        if stopped_sample.value and point_count.value < requested
        else float("inf")
    )
    if status != 0:
        if stopped_sample.value:
            raise ValueError(
                f"Continuation stopped at sample {stopped_sample.value}/"
                f"{requested_samples.value}; Newton residual {failed_residual:.3g}."
            )
        raise ValueError(last_error())
    stop_reason = None
    if stopped_sample.value:
        stop_reason = (
            f"Continuation stopped at sample {stopped_sample.value}/"
            f"{requested_samples.value}; Newton residual {failed_residual:.3g}."
        )
    return ParameterRayTrace(
        normalized,
        tuple(points[index].to_python() for index in range(point_count.value)),
        tuple(float(residuals[index]) for index in range(point_count.value)),
        requested_samples.value,
        stop_reason,
    )
