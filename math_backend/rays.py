"""External rays with double-precision work delegated to C."""

from __future__ import annotations

import ctypes as ct
import math
from dataclasses import dataclass
from fractions import Fraction

from .c_api import CComplex, complex_array, last_error, lib, require_success
from .dynamics import unicritical_map
from .high_precision import (
    critical_orbit_bounded_arbitrary,
    is_arbitrary,
    ray_point_arbitrary,
)


class DisconnectedJuliaError(ValueError):
    """Raised when a full external ray is requested for an escaping critical orbit."""


@dataclass(frozen=True)
class AngleOrbit:
    angles: tuple[Fraction, ...]
    preperiod: int
    period: int


@dataclass(frozen=True)
class RayTrace:
    angle: Fraction
    points: tuple[complex, ...]

    @property
    def landing_approximation(self) -> complex:
        return self.points[-1]


@dataclass(frozen=True)
class EquipotentialTrace:
    potential: float
    points: tuple[complex, ...]


@dataclass(frozen=True)
class LandingCluster:
    angles: tuple[Fraction, ...]
    point: complex


def adaptive_minimum_potential(world_span: float, pixel_width: int) -> float:
    if world_span <= 0.0 or pixel_width <= 0:
        raise ValueError("Viewport span and pixel width must be positive.")
    return max(1e-12, 0.125 * world_span / pixel_width)


def normalize_angle(angle: Fraction) -> Fraction:
    return angle % 1


def parse_rational_angle(text: str) -> Fraction:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Enter an angle such as 1/7 or 0.125.")
    try:
        return normalize_angle(Fraction(cleaned))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("The angle must be an integer, decimal, or fraction p/q.") from exc


def angle_map(
    angle: Fraction,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> Fraction:
    return normalize_angle((-degree if antiholomorphic else degree) * angle)


def next_missing_angles(
    angles: tuple[Fraction, ...],
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[Fraction, ...]:
    normalized = tuple(normalize_angle(angle) for angle in angles)
    existing = set(normalized)
    result: list[Fraction] = []
    for angle in normalized:
        image = angle_map(angle, degree=degree, antiholomorphic=antiholomorphic)
        if image not in existing and image not in result:
            result.append(image)
    return tuple(result)


def image_angles(
    angles: tuple[Fraction, ...],
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[Fraction, ...]:
    result: list[Fraction] = []
    for angle in angles:
        image = angle_map(angle, degree=degree, antiholomorphic=antiholomorphic)
        if image not in result:
            result.append(image)
    return tuple(result)


def forward_angle_orbit(
    angle: Fraction,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
    max_steps: int = 10000,
) -> AngleOrbit:
    current = normalize_angle(angle)
    seen: dict[Fraction, int] = {}
    angles: list[Fraction] = []
    while current not in seen:
        if len(angles) >= max_steps:
            raise ValueError("The exact angle orbit exceeded the safety limit.")
        seen[current] = len(angles)
        angles.append(current)
        current = angle_map(
            current,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
    preperiod = seen[current]
    return AngleOrbit(tuple(angles), preperiod, len(angles) - preperiod)


def critical_orbit_appears_bounded(
    parameter: complex,
    *,
    degree: int = 2,
    antiholomorphic: bool = True,
    iterations: int = 2048,
) -> bool:
    if is_arbitrary(parameter):
        return critical_orbit_bounded_arbitrary(
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
            iterations=iterations,
        )
    status = lib.loom_critical_orbit_bounded(
        CComplex.from_python(parameter),
        degree,
        int(antiholomorphic),
        iterations,
    )
    if status < 0:
        raise ValueError(last_error())
    return bool(status)


def ray_point(
    parameter: complex,
    angle: Fraction,
    potential: float,
    *,
    outer_potential: float = 9.0,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> complex:
    normalized = normalize_angle(angle)
    if precision_bits is not None:
        return ray_point_arbitrary(
            parameter,
            normalized,
            potential,
            outer_potential=outer_potential,
            precision_bits=precision_bits,
            degree=degree,
            antiholomorphic=antiholomorphic,
        )
    output = CComplex()
    status = lib.loom_ray_point(
        CComplex.from_python(parameter),
        float(normalized),
        potential,
        outer_potential,
        degree,
        int(antiholomorphic),
        ct.byref(output),
    )
    require_success(status)
    return output.to_python()


def trace_external_ray(
    parameter: complex,
    angle: Fraction,
    *,
    samples: int = 260,
    minimum_potential: float = 8e-4,
    maximum_potential: float = 2.2,
    require_connected: bool = True,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> RayTrace:
    normalized = normalize_angle(angle)
    if precision_bits is not None:
        if samples < 2:
            raise ValueError("A ray needs at least two samples.")
        if not 0.0 < minimum_potential < maximum_potential:
            raise ValueError("Ray potential limits are invalid.")
        if require_connected and not critical_orbit_appears_bounded(
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
        ):
            raise DisconnectedJuliaError(
                "The critical orbit escapes, so a full unbranched ray is not available."
            )
        ratio = minimum_potential / maximum_potential
        points = tuple(
            ray_point(
                parameter,
                normalized,
                maximum_potential * ratio ** (index / (samples - 1)),
                precision_bits=precision_bits,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            for index in range(samples)
        )
        return RayTrace(normalized, points)

    array_type = CComplex * samples
    points = array_type()
    status = lib.loom_trace_external_ray(
        CComplex.from_python(parameter),
        float(normalized),
        samples,
        minimum_potential,
        maximum_potential,
        int(require_connected),
        degree,
        int(antiholomorphic),
        points,
        samples,
    )
    if status == 1:
        raise DisconnectedJuliaError(last_error())
    require_success(status)
    return RayTrace(
        normalized,
        tuple(points[index].to_python() for index in range(samples)),
    )


def trace_equipotential(
    parameter: complex,
    potential: float,
    *,
    samples: int = 900,
    require_connected: bool = True,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> EquipotentialTrace:
    if precision_bits is not None:
        if potential <= 0.0:
            raise ValueError("Equipotential must be positive.")
        if samples < 32:
            raise ValueError("An equipotential needs at least 32 samples.")
        if require_connected and not critical_orbit_appears_bounded(
            parameter,
            degree=degree,
            antiholomorphic=antiholomorphic,
        ):
            raise DisconnectedJuliaError(
                "The critical orbit escapes, so a full equipotential is not available."
            )
        points = tuple(
            ray_point(
                parameter,
                Fraction(index, samples),
                potential,
                precision_bits=precision_bits,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            for index in range(samples)
        )
        return EquipotentialTrace(potential, points + points[:1])

    array_type = CComplex * (samples + 1)
    points = array_type()
    status = lib.loom_trace_equipotential(
        CComplex.from_python(parameter),
        potential,
        samples,
        int(require_connected),
        degree,
        int(antiholomorphic),
        points,
        samples + 1,
    )
    if status == 1:
        raise DisconnectedJuliaError(last_error())
    require_success(status)
    return EquipotentialTrace(
        potential,
        tuple(points[index].to_python() for index in range(samples + 1)),
    )


def cluster_ray_landings(
    rays: tuple[RayTrace, ...],
    *,
    tolerance: float,
) -> tuple[LandingCluster, ...]:
    if tolerance <= 0.0:
        raise ValueError("Landing tolerance must be positive.")
    clusters: list[list[RayTrace]] = []
    centers: list[complex] = []
    for ray in rays:
        landing = ray.landing_approximation
        match = next(
            (
                index
                for index, center in enumerate(centers)
                if abs(landing - center) <= tolerance
            ),
            None,
        )
        if match is None:
            clusters.append([ray])
            centers.append(landing)
        else:
            clusters[match].append(ray)
            centers[match] = sum(
                item.landing_approximation for item in clusters[match]
            ) / len(clusters[match])
    return tuple(
        LandingCluster(tuple(ray.angle for ray in cluster), center)
        for cluster, center in zip(clusters, centers)
    )


def estimate_point_period(
    point: complex,
    parameter: complex,
    *,
    tolerance: float,
    max_period: int = 64,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> int | None:
    if is_arbitrary(point) or is_arbitrary(parameter):
        value = point
        for period in range(1, max_period + 1):
            value = unicritical_map(
                value,
                parameter,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            if abs(value - point) <= tolerance:
                return period
        return None
    result = lib.loom_estimate_point_period(
        CComplex.from_python(point),
        CComplex.from_python(parameter),
        tolerance,
        max_period,
        degree,
        int(antiholomorphic),
    )
    if result < 0:
        raise ValueError(last_error())
    return result or None


def _point_in_polygon_python(
    point: complex,
    polygon: tuple[complex, ...],
) -> bool:
    inside = False
    x = point.real
    y = point.imag
    previous = polygon[-1]
    for current in polygon:
        crosses = (previous.imag > y) != (current.imag > y)
        if crosses:
            x_cross = (
                (current.real - previous.real)
                * (y - previous.imag)
                / (current.imag - previous.imag)
                + previous.real
            )
            if x < x_cross:
                inside = not inside
        previous = current
    return inside


def _point_in_polygon(
    point: complex,
    polygon: tuple[complex, ...],
    *,
    arbitrary: bool,
) -> bool:
    if arbitrary:
        return _point_in_polygon_python(point, polygon)
    c_polygon = complex_array(polygon)
    result = lib.loom_point_in_polygon(
        CComplex.from_python(point),
        c_polygon,
        len(polygon),
    )
    if result < 0:
        raise ValueError(last_error())
    return bool(result)


def _outer_arc(
    parameter: complex,
    start: Fraction,
    end: Fraction,
    *,
    potential: float,
    samples_per_turn: int = 480,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[complex, ...]:
    length_fraction = (end - start) % 1
    length = float(length_fraction)
    samples = max(8, math.ceil(length * samples_per_turn))
    if precision_bits is not None:
        return tuple(
            ray_point(
                parameter,
                normalize_angle(start + length_fraction * Fraction(index, samples)),
                potential,
                precision_bits=precision_bits,
                degree=degree,
                antiholomorphic=antiholomorphic,
            )
            for index in range(samples + 1)
        )
    array_type = CComplex * (samples + 1)
    points = array_type()
    status = lib.loom_trace_outer_arc(
        CComplex.from_python(parameter),
        float(normalize_angle(start)),
        length,
        potential,
        samples,
        degree,
        int(antiholomorphic),
        points,
        samples + 1,
    )
    require_success(status)
    return tuple(points[index].to_python() for index in range(samples + 1))


def sector_polygon(
    parameter: complex,
    first_ray: RayTrace,
    second_ray: RayTrace,
    *,
    containing: complex,
    outer_potential: float = 2.2,
    precision_bits: int | None = None,
    degree: int = 2,
    antiholomorphic: bool = True,
) -> tuple[complex, ...]:
    first_arc = _outer_arc(
        parameter,
        first_ray.angle,
        second_ray.angle,
        potential=outer_potential,
        precision_bits=precision_bits,
        degree=degree,
        antiholomorphic=antiholomorphic,
    )
    second_arc = _outer_arc(
        parameter,
        second_ray.angle,
        first_ray.angle,
        potential=outer_potential,
        precision_bits=precision_bits,
        degree=degree,
        antiholomorphic=antiholomorphic,
    )
    first_polygon = tuple(
        list(reversed(first_ray.points))
        + list(first_arc[1:])
        + list(second_ray.points[1:])
    )
    second_polygon = tuple(
        list(reversed(second_ray.points))
        + list(second_arc[1:])
        + list(first_ray.points[1:])
    )
    arbitrary = precision_bits is not None
    if _point_in_polygon(containing, first_polygon, arbitrary=arbitrary):
        return first_polygon
    if _point_in_polygon(containing, second_polygon, arbitrary=arbitrary):
        return second_polygon
    raise ValueError("Could not identify which ray sector contains the target point.")
