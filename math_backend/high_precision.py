"""Arbitrary-precision fallbacks intentionally kept in Python/mpmath."""

from __future__ import annotations

import math
from fractions import Fraction

import mpmath as mp


def normalize_angle(angle: Fraction) -> Fraction:
    return angle % 1


def angle_map(
    angle: Fraction,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> Fraction:
    return normalize_angle((-degree if antiholomorphic else degree) * angle)


def expected_point(angle: Fraction, potential: mp.mpf) -> mp.mpc:
    angle_value = mp.mpf(angle.numerator) / angle.denominator
    return mp.exp(potential + 2j * mp.pi * angle_value)


def ray_point_arbitrary(
    parameter: complex | mp.mpc,
    angle: Fraction,
    potential: float,
    *,
    outer_potential: float = 9.0,
    precision_bits: int,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> mp.mpc:
    with mp.workprec(precision_bits):
        current_potential = mp.mpf(potential)
        current_outer = mp.mpf(outer_potential)
        current_parameter = mp.mpc(parameter)
        if current_potential <= 0:
            raise ValueError("External potential must be positive.")
        if current_outer <= current_potential:
            current_outer = current_potential * 2
        pullbacks = max(
            1,
            math.ceil(math.log(float(current_outer / current_potential), degree)),
        )
        lifted_potential = current_potential * degree**pullbacks
        normalized = normalize_angle(angle)
        angle_levels = [normalized]
        for _ in range(pullbacks):
            angle_levels.append(
                angle_map(
                    angle_levels[-1],
                    degree=degree,
                    antiholomorphic=antiholomorphic,
                )
            )
        point = expected_point(angle_levels[-1], lifted_potential)
        unity = mp.exp(2j * mp.pi / degree)
        for level in range(pullbacks - 1, -1, -1):
            preimage = point - current_parameter
            if antiholomorphic:
                preimage = mp.conj(preimage)
            root = mp.exp(mp.log(preimage) / degree)
            candidates = tuple(root * unity**branch for branch in range(degree))
            expected = expected_point(
                angle_levels[level],
                current_potential * degree**level,
            )
            point = min(candidates, key=lambda candidate: abs(candidate - expected))
        return point


def critical_value_orbit_with_derivatives_arbitrary(
    parameter: complex | mp.mpc,
    depth: int,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[mp.mpc, mp.mpc, mp.mpc]:
    if depth < 1:
        raise ValueError("Depth must be positive.")
    parameter = mp.mpc(parameter)
    value = parameter
    derivative_c = mp.mpc(1)
    derivative_conjugate = mp.mpc(0)
    for _ in range(depth):
        previous = value
        previous_c = derivative_c
        previous_conjugate = derivative_conjugate
        if antiholomorphic:
            coefficient = degree * mp.conj(previous) ** (degree - 1)
            derivative_c = coefficient * mp.conj(previous_conjugate) + 1
            derivative_conjugate = coefficient * mp.conj(previous_c)
            value = mp.conj(previous**degree) + parameter
        else:
            coefficient = degree * previous ** (degree - 1)
            derivative_c = coefficient * previous_c + 1
            derivative_conjugate = coefficient * previous_conjugate
            value = previous**degree + parameter
    return value, derivative_c, derivative_conjugate


def real_newton_parameter_arbitrary(
    target: complex | mp.mpc,
    depth: int,
    seed: complex | mp.mpc,
    *,
    tolerance: float = 1e-11,
    max_steps: int = 40,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[mp.mpc, mp.mpf, bool]:
    parameter = mp.mpc(seed)
    target = mp.mpc(target)
    residual = mp.inf
    for _ in range(max_steps):
        value, derivative_c, derivative_conjugate = (
            critical_value_orbit_with_derivatives_arbitrary(
                parameter,
                depth,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
        )
        error = value - target
        residual = abs(error)
        if residual <= tolerance * max(1, abs(target)):
            return parameter, residual, True
        determinant = abs(derivative_c) ** 2 - abs(derivative_conjugate) ** 2
        scale = abs(derivative_c) ** 2 + abs(derivative_conjugate) ** 2
        if not mp.isfinite(determinant) or abs(determinant) <= mp.mpf("1e-14") * max(1, scale):
            return parameter, residual, False
        correction = (
            mp.conj(derivative_c) * error
            - derivative_conjugate * mp.conj(error)
        ) / determinant
        if not mp.isfinite(correction.real) or not mp.isfinite(correction.imag):
            return parameter, residual, False
        damping = mp.mpf(1)
        while damping >= mp.mpf(1) / 256:
            candidate = parameter - damping * correction
            candidate_value, _, _ = critical_value_orbit_with_derivatives_arbitrary(
                candidate,
                depth,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            candidate_residual = abs(candidate_value - target)
            if candidate_residual < residual:
                parameter = candidate
                residual = candidate_residual
                break
            damping *= mp.mpf("0.5")
        else:
            return parameter, residual, False
    return parameter, residual, False


def is_arbitrary(value: object) -> bool:
    """Return whether a value is an mpmath scalar carrying extra precision."""
    return hasattr(value, "_mpf_") or hasattr(value, "_mpc_")


def unicritical_map_arbitrary(
    value: complex | mp.mpc,
    parameter: complex | mp.mpc,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> mp.mpc:
    if degree < 2:
        raise ValueError("The degree must be at least two.")
    value = mp.mpc(value)
    parameter = mp.mpc(parameter)
    powered = value**degree
    return (mp.conj(powered) if antiholomorphic else powered) + parameter


def escape_radius_arbitrary(parameter: complex | mp.mpc, degree: int) -> mp.mpf:
    return max(mp.mpf(2), (2 * abs(mp.mpc(parameter))) ** (mp.mpf(1) / degree))


def critical_orbit_bounded_arbitrary(
    parameter: complex | mp.mpc,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
    iterations: int = 2048,
) -> bool:
    value = mp.mpc(0)
    parameter = mp.mpc(parameter)
    radius = escape_radius_arbitrary(parameter, degree)
    for _ in range(iterations):
        value = unicritical_map_arbitrary(
            value,
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
        if abs(value) > radius:
            return False
    return True


def attracting_critical_orbit_arbitrary(
    parameter: complex | mp.mpc,
    *,
    max_steps: int = 4096,
    max_period: int = 64,
    tolerance: float = 1e-9,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[mp.mpc, ...] | None:
    if max_steps < 3 or max_period < 1:
        raise ValueError("max_steps and max_period must be positive")
    parameter = mp.mpc(parameter)
    value = mp.mpc(0)
    radius = escape_radius_arbitrary(parameter, degree)
    history: list[mp.mpc] = []
    for _ in range(max_steps):
        value = unicritical_map_arbitrary(
            value,
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
        if abs(value) > radius:
            return None
        history.append(value)
    largest_period = min(max_period, (len(history) - 1) // 2)
    current_tolerance = mp.mpf(tolerance)
    for period in range(1, largest_period + 1):
        newest_error = abs(history[-1] - history[-1 - period])
        previous_error = abs(history[-1 - period] - history[-1 - 2 * period])
        if (
            newest_error <= current_tolerance
            and previous_error <= current_tolerance * 100
            and newest_error <= previous_error + current_tolerance * mp.mpf("0.01")
        ):
            return tuple(history[-period:])
    return None
