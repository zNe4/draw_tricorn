"""Arbitrary-coordinate fractal rendering using high-precision reference orbits."""

from __future__ import annotations

import math
from math import comb
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ArbitraryRenderOptions:
    kind: str
    mode: str
    xmin: str
    xmax: str
    ymin: str
    ymax: str
    parameter_real: str
    parameter_imag: str
    iterations: int
    width: int
    height: int
    bits: int
    output_path: Path
    max_period: int = 20
    dynamics: str = "antiholomorphic"
    degree: int = 2


PERIOD_COLORS = np.asarray(
    (
        (89, 191, 168),
        (230, 162, 74),
        (155, 125, 219),
        (94, 159, 214),
        (218, 113, 136),
        (159, 196, 90),
        (200, 117, 189),
        (75, 184, 196),
        (217, 121, 75),
        (105, 123, 208),
        (209, 191, 85),
        (213, 143, 168),
    ),
    dtype=np.uint8,
)


def _channel(value: float) -> int:
    return max(0, min(255, round(value)))


def _mix(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
    amount: np.ndarray,
) -> np.ndarray:
    amount = np.clip(amount, 0.0, 1.0)[..., np.newaxis]
    first_array = np.asarray(first, dtype=float)
    second_array = np.asarray(second, dtype=float)
    return np.rint(first_array + (second_array - first_array) * amount).astype(
        np.uint8
    )


def _hsv_pixels(
    hue: np.ndarray,
    saturation: float,
    value: np.ndarray,
) -> np.ndarray:
    hue = hue - np.floor(hue)
    sector = hue * 6.0
    index = np.floor(sector).astype(np.int8)
    fraction = sector - index
    low = value * (1.0 - saturation)
    falling = value * (1.0 - saturation * fraction)
    rising = value * (1.0 - saturation * (1.0 - fraction))
    channels = np.empty(hue.shape + (3,), dtype=float)
    choices = (
        (value, rising, low),
        (falling, value, low),
        (low, value, rising),
        (low, falling, value),
        (rising, low, value),
        (value, low, falling),
    )
    for current, choice in enumerate(choices):
        mask = index % 6 == current
        for channel_index, source in enumerate(choice):
            channels[..., channel_index][mask] = source[mask]
    return np.rint(np.clip(channels, 0.0, 1.0) * 255.0).astype(np.uint8)


def _paint(
    kind: str,
    mode: str,
    smooth: np.ndarray,
    inside: np.ndarray,
    periods: np.ndarray | None = None,
) -> np.ndarray:
    tone = 1.0 - np.exp(-smooth / 12.0)
    if kind == "julia" and mode == "escape":
        hue = 0.68 + smooth * 0.057581917135421046
        value = 0.34 + 0.62 * np.power(tone, 0.42)
        image = _hsv_pixels(hue, 0.76, value)
        image[inside] = (2, 3, 5)
        return image

    tone = np.power(tone, 0.38)
    if mode == "grayscale":
        image = _mix((19, 22, 24), (177, 184, 183), tone)
        image[inside] = (
            (76, 82, 82)
            if kind in {"parameter", "tricorn"}
            else (2, 2, 2)
        )
        return image

    image = _mix((15, 22, 28), (91, 111, 117), tone * 0.88)
    if kind in {"parameter", "tricorn"}:
        if mode == "escape":
            image[inside] = (73, 112, 110)
        elif mode == "period":
            image[inside] = (46, 54, 57)
            if periods is not None:
                for period in np.unique(periods[inside]):
                    if period <= 0:
                        continue
                    base = PERIOD_COLORS[
                        (int(period) - 1) % len(PERIOD_COLORS)
                    ].astype(float)
                    center = base + ((235, 242, 235) - base) * 0.16
                    edge = base + ((31, 39, 43) - base) * 0.24
                    color = np.rint(center + (edge - center) * 0.35).astype(
                        np.uint8
                    )
                    image[inside & (periods == period)] = color
        elif mode == "newton":
            # At arbitrary zoom scales the multiplier field is locally smooth.
            image[inside] = (
                _channel((72 + 222) / 2),
                _channel((128 + 176) / 2),
                _channel((123 + 104) / 2),
            )
        else:
            image[inside] = (
                _channel((65 + 207) / 2),
                _channel((111 + 151) / 2),
                _channel((126 + 100) / 2),
            )
    else:
        image[inside] = (2, 3, 5)
    return image


def _component_periods(
    parameters: np.ndarray,
    inside: np.ndarray,
    max_period: int,
    iterations: int,
    *,
    dynamics: str,
    degree: int,
) -> np.ndarray:
    """Estimate minimal antiholomorphic periods after a long critical-orbit burn-in."""
    periods = np.zeros(parameters.shape, dtype=np.int16)

    if dynamics == "antiholomorphic" and degree == 2:
        scaled = 4.0 * parameters
        radius_squared = scaled.real**2 + scaled.imag**2
        deltoid = (
            radius_squared**2
            + 18.0 * radius_squared
            + 8.0 * np.real(scaled**3)
            - 27.0
            < -1e-10
        )
        periods[inside & deltoid] = 1

    unresolved = inside & (periods == 0)
    if not np.any(unresolved):
        return periods

    value = np.zeros(parameters.shape, dtype=np.complex128)
    burn_in = max(96, min(iterations, 512))
    for _ in range(burn_in):
        powered = value[unresolved] ** degree
        value[unresolved] = (
            np.conj(powered)
            if dynamics == "antiholomorphic"
            else powered
        ) + parameters[unresolved]
    anchor = value.copy()
    current = value.copy()
    tolerance = 2e-7 * (1.0 + np.abs(anchor))
    for period in range(1, max_period + 1):
        powered = current[unresolved] ** degree
        current[unresolved] = (
            np.conj(powered)
            if dynamics == "antiholomorphic"
            else powered
        ) + parameters[unresolved]
        matched = (
            unresolved
            & (periods == 0)
            & (np.abs(current - anchor) < tolerance)
        )
        periods[matched] = period
        if not np.any(unresolved & (periods == 0)):
            break
    return periods


def _perturb_polynomial(
    reference: complex,
    perturbation: np.ndarray,
    degree: int,
) -> np.ndarray:
    """Evaluate (reference+delta)^d-reference^d without subtractive cancellation."""
    result = np.zeros_like(perturbation, dtype=np.complex128)
    for power in range(1, degree + 1):
        result += (
            comb(degree, power)
            * reference ** (degree - power)
            * perturbation**power
        )
    return result


def render_arbitrary(options: ArbitraryRenderOptions) -> None:
    """Render with an arbitrary-precision reference orbit and double perturbations."""
    if options.width < 16 or options.height < 16:
        raise ValueError("Image dimensions must be at least 16.")
    if options.bits < 64:
        raise ValueError("Arbitrary precision must use at least 64 bits.")
    if options.degree < 2 or options.degree > 32:
        raise ValueError("Degree must be between 2 and 32.")
    if options.dynamics not in {"holomorphic", "antiholomorphic"}:
        raise ValueError(f"Unknown dynamics kind: {options.dynamics}")

    with mp.workprec(options.bits):
        xmin = mp.mpf(options.xmin)
        xmax = mp.mpf(options.xmax)
        ymin = mp.mpf(options.ymin)
        ymax = mp.mpf(options.ymax)
        center = mp.mpc((xmin + xmax) / 2, (ymin + ymax) / 2)
        parameter = mp.mpc(options.parameter_real, options.parameter_imag)
        span_x = float(xmax - xmin)
        span_y = float(ymax - ymin)

        x_offsets = (
            np.arange(options.width, dtype=float) + 0.5
            - options.width / 2.0
        ) * (span_x / options.width)
        y_offsets = (
            options.height / 2.0
            - np.arange(options.height, dtype=float)
            - 0.5
        ) * (span_y / options.height)
        offsets = (
            x_offsets[np.newaxis, :] + 1j * y_offsets[:, np.newaxis]
        )

        if options.kind in {"parameter", "tricorn"}:
            reference_parameter = center
            reference = mp.mpc(0)
            perturbation = np.zeros_like(offsets, dtype=np.complex128)
            parameter_perturbation = offsets
        elif options.kind == "julia":
            reference_parameter = parameter
            reference = center
            perturbation = offsets.astype(np.complex128, copy=True)
            parameter_perturbation = 0.0
        else:
            raise ValueError(f"Unknown fractal kind: {options.kind}")

        active = np.ones(offsets.shape, dtype=bool)
        smooth = np.full(offsets.shape, float(options.iterations), dtype=float)

        for iteration in range(options.iterations):
            old_reference = reference
            powered_reference = old_reference**options.degree
            reference = (
                mp.conj(powered_reference)
                if options.dynamics == "antiholomorphic"
                else powered_reference
            ) + reference_parameter
            old_reference_double = complex(old_reference)
            current = perturbation[active]
            polynomial_delta = _perturb_polynomial(
                old_reference_double,
                current,
                options.degree,
            )
            if options.dynamics == "antiholomorphic":
                polynomial_delta = np.conj(polynomial_delta)
            perturbation[active] = polynomial_delta + (
                parameter_perturbation[active]
                if isinstance(parameter_perturbation, np.ndarray)
                else parameter_perturbation
            )

            reference_double = complex(reference)
            total = reference_double + perturbation
            radius_squared = total.real * total.real + total.imag * total.imag
            escaped = active & (radius_squared > 4.0)
            if np.any(escaped):
                log_radius = 0.5 * np.log(radius_squared[escaped])
                smooth[escaped] = np.maximum(
                    0.0,
                    iteration + 1.0
                    - np.log(log_radius) / math.log(options.degree),
                )
                active[escaped] = False
            if not np.any(active):
                break
            if abs(reference) > mp.mpf("1e150"):
                # Any unresolved perturbation is outside the reliable range.
                smooth[active] = float(iteration + 1)
                active[:] = False
                break

    periods = None
    if options.kind in {"parameter", "tricorn"} and options.mode == "period":
        center_double = complex(center)
        parameters = center_double + offsets
        periods = _component_periods(
            parameters,
            active,
            options.max_period,
            options.iterations,
            dynamics=options.dynamics,
            degree=options.degree,
        )
    image = _paint(options.kind, options.mode, smooth, active, periods)
    options.output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(options.output_path, format="PPM")
