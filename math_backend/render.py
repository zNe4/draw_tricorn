"""Direct in-process access to the native fractal renderer."""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass

from PIL import Image

from .c_api import CRenderOptions, lib, require_success

_KIND = {"parameter": 0, "tricorn": 0, "julia": 1}
_DYNAMICS = {"holomorphic": 0, "antiholomorphic": 1}
_MODE = {
    "escape": 0,
    "grayscale": 1,
    "newton": 2,
    "lyapunov": 3,
    "period": 4,
}
_PRECISION = {"float": 0, "double": 1}


@dataclass(frozen=True)
class NativeRenderOptions:
    kind: str
    dynamics: str
    mode: str
    degree: int
    width: int
    height: int
    iterations: int
    max_period: int
    draw_boundary: bool
    precision: str
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    parameter_real: float = 0.0
    parameter_imag: float = 0.0


def render_native(options: NativeRenderOptions) -> Image.Image:
    """Render an RGB image entirely inside the shared C library."""
    try:
        c_options = CRenderOptions(
            _KIND[options.kind],
            _DYNAMICS[options.dynamics],
            _MODE[options.mode],
            options.degree,
            options.width,
            options.height,
            options.iterations,
            options.max_period,
            options.draw_boundary,
            _PRECISION[options.precision],
            float(options.xmin),
            float(options.xmax),
            float(options.ymin),
            float(options.ymax),
            float(options.parameter_real),
            float(options.parameter_imag),
            None,
        )
    except KeyError as exc:
        raise ValueError(f"Unsupported native render option: {exc.args[0]}") from exc

    size = options.width * options.height * 3
    buffer_type = ct.c_ubyte * size
    buffer = buffer_type()
    status = lib.loom_render_rgb(ct.byref(c_options), buffer, size)
    require_success(status)
    return Image.frombytes("RGB", (options.width, options.height), bytes(buffer))
