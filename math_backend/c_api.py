"""ctypes bindings for the native numerical backend."""

from __future__ import annotations

import ctypes as ct
import subprocess
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_NAME = "libbifurcation.dylib" if sys.platform == "darwin" else "libbifurcation.so"
LIBRARY_PATH = PROJECT_ROOT / "build" / LIBRARY_NAME


class CComplex(ct.Structure):
    _fields_ = [("real", ct.c_double), ("imag", ct.c_double)]

    @classmethod
    def from_python(cls, value: complex) -> "CComplex":
        converted = complex(value)
        return cls(converted.real, converted.imag)

    def to_python(self) -> complex:
        return complex(self.real, self.imag)


class CRenderOptions(ct.Structure):
    _fields_ = [
        ("kind", ct.c_int),
        ("dynamics", ct.c_int),
        ("mode", ct.c_int),
        ("degree", ct.c_int),
        ("width", ct.c_int),
        ("height", ct.c_int),
        ("max_iterations", ct.c_int),
        ("max_period", ct.c_int),
        ("draw_boundary", ct.c_bool),
        ("precision", ct.c_int),
        ("xmin", ct.c_double),
        ("xmax", ct.c_double),
        ("ymin", ct.c_double),
        ("ymax", ct.c_double),
        ("parameter_real", ct.c_double),
        ("parameter_imag", ct.c_double),
        ("output_path", ct.c_char_p),
    ]


class CInternalCurve(ct.Structure):
    _fields_ = [
        ("log_radius", ct.c_double),
        ("first_polyline", ct.c_size_t),
        ("polyline_count", ct.c_size_t),
        ("representative", ct.c_int),
    ]


class CPolyline(ct.Structure):
    _fields_ = [
        ("first_point", ct.c_size_t),
        ("point_count", ct.c_size_t),
    ]


class CInternalCurveResult(ct.Structure):
    _fields_ = [
        ("coordinate_kind", ct.c_int),
        ("return_period", ct.c_int),
        ("curve_count", ct.c_size_t),
        ("polyline_count", ct.c_size_t),
        ("point_count", ct.c_size_t),
        ("curves", ct.POINTER(CInternalCurve)),
        ("polylines", ct.POINTER(CPolyline)),
        ("points", ct.POINTER(CComplex)),
    ]


def ensure_library() -> None:
    result = subprocess.run(
        ["make", "--quiet", "all"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not LIBRARY_PATH.exists():
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Could not build the C backend.\n\n{details}")


ensure_library()
lib = ct.CDLL(str(LIBRARY_PATH))

lib.loom_last_error.argtypes = []
lib.loom_last_error.restype = ct.c_char_p

lib.loom_render_rgb.argtypes = [
    ct.POINTER(CRenderOptions),
    ct.POINTER(ct.c_ubyte),
    ct.c_size_t,
]
lib.loom_render_rgb.restype = ct.c_int

lib.loom_unicritical_map.argtypes = [
    CComplex,
    CComplex,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
]
lib.loom_unicritical_map.restype = ct.c_int
lib.loom_escape_radius.argtypes = [CComplex, ct.c_int]
lib.loom_escape_radius.restype = ct.c_double
lib.loom_attracting_critical_orbit.argtypes = [
    CComplex,
    ct.c_int,
    ct.c_int,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.c_size_t,
    ct.POINTER(ct.c_size_t),
]
lib.loom_attracting_critical_orbit.restype = ct.c_int
lib.loom_critical_orbit_bounded.argtypes = [
    CComplex,
    ct.c_int,
    ct.c_int,
    ct.c_int,
]
lib.loom_critical_orbit_bounded.restype = ct.c_int
lib.loom_ray_point.argtypes = [
    CComplex,
    ct.c_double,
    ct.c_double,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
]
lib.loom_ray_point.restype = ct.c_int
lib.loom_trace_external_ray.argtypes = [
    CComplex,
    ct.c_double,
    ct.c_int,
    ct.c_double,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.c_size_t,
]
lib.loom_trace_external_ray.restype = ct.c_int
lib.loom_trace_equipotential.argtypes = [
    CComplex,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.c_size_t,
]
lib.loom_trace_equipotential.restype = ct.c_int
lib.loom_trace_outer_arc.argtypes = [
    CComplex,
    ct.c_double,
    ct.c_double,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.c_size_t,
]
lib.loom_trace_outer_arc.restype = ct.c_int
lib.loom_estimate_point_period.argtypes = [
    CComplex,
    CComplex,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
]
lib.loom_estimate_point_period.restype = ct.c_int
lib.loom_point_in_polygon.argtypes = [
    CComplex,
    ct.POINTER(CComplex),
    ct.c_size_t,
]
lib.loom_point_in_polygon.restype = ct.c_int
lib.loom_critical_value_orbit_with_derivatives.argtypes = [
    CComplex,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.POINTER(CComplex),
    ct.POINTER(CComplex),
]
lib.loom_critical_value_orbit_with_derivatives.restype = ct.c_int
lib.loom_real_newton_parameter.argtypes = [
    CComplex,
    ct.c_int,
    CComplex,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.POINTER(ct.c_double),
    ct.POINTER(ct.c_int),
]
lib.loom_real_newton_parameter.restype = ct.c_int
lib.loom_trace_parameter_ray.argtypes = [
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_double,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CComplex),
    ct.POINTER(ct.c_double),
    ct.c_size_t,
    ct.POINTER(ct.c_size_t),
    ct.POINTER(ct.c_size_t),
    ct.POINTER(ct.c_int),
]
lib.loom_trace_parameter_ray.restype = ct.c_int
lib.loom_trace_internal_grand_orbit.argtypes = [
    CComplex,
    ct.POINTER(CComplex),
    ct.c_size_t,
    ct.c_double,
    ct.c_double,
    ct.c_double,
    ct.c_double,
    ct.c_double,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.c_int,
    ct.POINTER(CInternalCurveResult),
]
lib.loom_trace_internal_grand_orbit.restype = ct.c_int
lib.loom_free_internal_curve_result.argtypes = [ct.POINTER(CInternalCurveResult)]
lib.loom_free_internal_curve_result.restype = None


def last_error(default: str = "The C backend returned an unknown error.") -> str:
    raw = lib.loom_last_error()
    if not raw:
        return default
    return raw.decode("utf-8", errors="replace") or default


def require_success(status: int, *, allow_positive: bool = False) -> int:
    if status < 0 or (status > 0 and not allow_positive):
        raise ValueError(last_error())
    return status


def complex_array(values: Iterable[complex]) -> ct.Array[CComplex]:
    converted = tuple(CComplex.from_python(value) for value in values)
    array_type = CComplex * len(converted)
    return array_type(*converted)
