"""Bifurcation Loom: interactive unicritical polynomial dynamics."""

from __future__ import annotations

import queue
import math
import subprocess
import threading
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mpmath as mp
from PIL import Image, ImageDraw, ImageTk

from math_backend.c_api import ensure_library
from math_backend.render import NativeRenderOptions, render_native
from math_backend.arbitrary_renderer import ArbitraryRenderOptions, render_arbitrary
from math_backend.dynamics import attracting_critical_orbit, unicritical_map
from math_backend.internal_curves import InternalCurveSet, trace_internal_grand_orbit
from math_backend.parameter_rays import ParameterRayTrace, trace_parameter_ray
from math_backend.parameter_path import ParameterPath
from math_backend.precision import PRECISION_CHOICES, PrecisionDecision, precision_decision
from math_backend.rays import (
    EquipotentialTrace,
    LandingCluster,
    RayTrace,
    adaptive_minimum_potential,
    cluster_ray_landings,
    critical_orbit_appears_bounded,
    estimate_point_period,
    forward_angle_orbit,
    image_angles,
    next_missing_angles,
    parse_rational_angle,
    sector_polygon,
    trace_equipotential,
    trace_external_ray,
)


PROJECT_ROOT = Path(__file__).resolve().parent
IMAGE_DIR = PROJECT_ROOT / "output"
CANVAS_SIZE = 620
COMPACT_LAYOUT = False
DEFAULT_VIEW = ("-2", "2", "-2", "2")

PARAMETER_MODES = {
    "Component periods": "period",
    "Newton multiplier": "newton",
    "Lyapunov multiplier": "lyapunov",
    "Muted escape": "escape",
    "Grayscale": "grayscale",
}
JULIA_MODES = {
    "Rainbow escape": "escape",
    "Grayscale": "grayscale",
}
ITERATION_OPTIONS = (256, 512, 1024, 2048)
PERIOD_OPTIONS = (8, 12, 20, 32)
DEGREE_OPTIONS = tuple(range(2, 13))
QUALITY_OPTIONS = {
    "1× · 620 px": 1,
    "2× · 1240 px": 2,
    "3× · 1860 px": 3,
}


def configure_display_layout(screen_width: int, screen_height: int) -> None:
    """Choose a canvas size that keeps all controls visible on common screens."""
    global CANVAS_SIZE, COMPACT_LAYOUT, QUALITY_OPTIONS

    if screen_height <= 800 or screen_width <= 1366:
        CANVAS_SIZE = 440
        COMPACT_LAYOUT = True
    elif screen_height <= 950:
        CANVAS_SIZE = 520
        COMPACT_LAYOUT = True
    else:
        CANVAS_SIZE = 620
        COMPACT_LAYOUT = False

    QUALITY_OPTIONS = {
        f"1× · {CANVAS_SIZE} px": 1,
        f"2× · {CANVAS_SIZE * 2} px": 2,
        f"3× · {CANVAS_SIZE * 3} px": 3,
    }


def quality_label(multiplier: int) -> str:
    return f"{multiplier}× · {CANVAS_SIZE * multiplier} px"
RAY_COLORS = (
    "#62e6ff",
    "#ff8fb8",
    "#ffe377",
    "#a9f38b",
    "#c7a1ff",
    "#ffad73",
)
PERIOD_COLORS = (
    "#59bfa8",
    "#e6a24a",
    "#9b7ddb",
    "#5e9fd6",
    "#da7188",
    "#9fc45a",
    "#c875bd",
    "#4bb8c4",
    "#d9794b",
    "#697bd0",
    "#d1bf55",
    "#d58fa8",
)


def format_complex(value: complex, digits: int = 9) -> str:
    sign = "+" if value.imag >= 0 else "−"
    real = mp.nstr(value.real, digits)
    imag = mp.nstr(abs(value.imag), digits)
    return f"{real} {sign} {imag}i"


@dataclass
class Viewport:
    xmin: mp.mpf = field(default_factory=lambda: mp.mpf("-2"))
    xmax: mp.mpf = field(default_factory=lambda: mp.mpf("2"))
    ymin: mp.mpf = field(default_factory=lambda: mp.mpf("-2"))
    ymax: mp.mpf = field(default_factory=lambda: mp.mpf("2"))

    def reset(self) -> None:
        self.xmin, self.xmax, self.ymin, self.ymax = (
            mp.mpf(value) for value in DEFAULT_VIEW
        )

    def complex_at(self, px: float, py: float, size: int) -> mp.mpc:
        real = self.xmin + px * (self.xmax - self.xmin) / size
        imag = self.ymax - py * (self.ymax - self.ymin) / size
        return mp.mpc(real, imag)

    def pixel_at(self, value: complex, size: int) -> tuple[float, float]:
        x = (value.real - self.xmin) * size / (self.xmax - self.xmin)
        y = (self.ymax - value.imag) * size / (self.ymax - self.ymin)
        return float(x), float(y)

    def zoom_to_pixels(
        self, start: tuple[int, int], end: tuple[int, int], size: int
    ) -> None:
        first = self.complex_at(*start, size)
        second = self.complex_at(*end, size)
        self.xmin, self.xmax = sorted((first.real, second.real))
        self.ymin, self.ymax = sorted((first.imag, second.imag))

    def description(self) -> str:
        return (
            f"Re [{mp.nstr(self.xmin, 7)}, {mp.nstr(self.xmax, 7)}]   "
            f"Im [{mp.nstr(self.ymin, 7)}, {mp.nstr(self.ymax, 7)}]"
        )


@dataclass(frozen=True)
class SectorSpec:
    kind: str
    first_angle: Fraction
    second_angle: Fraction


def ensure_renderer() -> None:
    """Build the shared C backend when it is missing or out of date."""
    ensure_library()


class ComplexInputDialog(tk.Toplevel):
    """Modal real/imaginary input used for both c and dynamical z."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        symbol: str,
        initial: complex,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.result: mp.mpc | None = None
        self.real = tk.StringVar(value=mp.nstr(initial.real, 25))
        self.imag = tk.StringVar(value=mp.nstr(initial.imag, 25))

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Enter {symbol} precisely").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(body, text="Real part").grid(row=1, column=0, sticky="w")
        real_entry = ttk.Entry(body, textvariable=self.real, width=24)
        real_entry.grid(row=1, column=1, padx=(10, 0), pady=3)
        ttk.Label(body, text="Imaginary part").grid(row=2, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.imag, width=24).grid(
            row=2, column=1, padx=(10, 0), pady=3
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._accept).pack(
            side="right", padx=(0, 7)
        )

        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        real_entry.focus_set()
        real_entry.selection_range(0, "end")
        self.grab_set()
        self.wait_window()

    def _accept(self) -> None:
        try:
            self.result = mp.mpc(
                mp.mpf(self.real.get()),
                mp.mpf(self.imag.get()),
            )
        except ValueError:
            messagebox.showerror(
                "Invalid complex number",
                "Both components must be valid real numbers.",
                parent=self,
            )
            return
        self.destroy()


class ParameterAnimationDialog(tk.Toplevel):
    """Controls a linear parameter path and its on-demand Julia frames."""

    def __init__(self, app: "BifurcationLoomApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Julia-set parameter path")
        self.transient(app)
        self.resizable(False, False)
        self.steps = tk.IntVar(value=app.animation_steps)
        self.fps = tk.IntVar(value=app.animation_fps)
        self.frame = tk.IntVar(value=app.animation_index)
        self.endpoint_text = tk.StringVar()
        self.frame_text = tk.StringVar()
        self.play_text = tk.StringVar(value="Pause" if app.animation_playing else "Play")
        self._updating_scale = False

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Render Julia sets along c(t) = (1−t)A + tB. "
                "Frames are computed on demand."
            ),
            wraplength=540,
        ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 10))
        ttk.Label(
            body,
            textvariable=self.endpoint_text,
            style="Meta.TLabel",
            wraplength=540,
        ).grid(row=1, column=0, columnspan=6, sticky="w")

        ttk.Button(
            body,
            text="A ← current c",
            command=lambda: app.set_path_endpoint("A", app.julia_parameter),
        ).grid(row=2, column=0, padx=(0, 5), pady=(10, 4), sticky="ew")
        ttk.Button(
            body,
            text="Pick A",
            command=lambda: app.begin_path_pick("A"),
        ).grid(row=2, column=1, padx=5, pady=(10, 4), sticky="ew")
        ttk.Button(
            body,
            text="Edit A…",
            command=lambda: app.prompt_path_endpoint("A"),
        ).grid(row=2, column=2, padx=5, pady=(10, 4), sticky="ew")
        ttk.Button(
            body,
            text="B ← current c",
            command=lambda: app.set_path_endpoint("B", app.julia_parameter),
        ).grid(row=2, column=3, padx=5, pady=(10, 4), sticky="ew")
        ttk.Button(
            body,
            text="Pick B",
            command=lambda: app.begin_path_pick("B"),
        ).grid(row=2, column=4, padx=5, pady=(10, 4), sticky="ew")
        ttk.Button(
            body,
            text="Edit B…",
            command=lambda: app.prompt_path_endpoint("B"),
        ).grid(row=2, column=5, padx=(5, 0), pady=(10, 4), sticky="ew")

        settings = ttk.Frame(body)
        settings.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(7, 3))
        ttk.Label(settings, text="Frames").pack(side="left")
        ttk.Spinbox(
            settings,
            from_=2,
            to=2000,
            textvariable=self.steps,
            width=6,
        ).pack(side="left", padx=(6, 14))
        ttk.Label(settings, text="Playback fps").pack(side="left")
        ttk.Spinbox(
            settings,
            from_=1,
            to=30,
            textvariable=self.fps,
            width=4,
        ).pack(side="left", padx=(6, 14))
        ttk.Button(
            settings,
            text="Apply path settings",
            command=self._apply_settings,
        ).pack(side="right")

        self.scale = ttk.Scale(
            body,
            from_=0,
            to=max(1, app.animation_steps - 1),
            variable=self.frame,
            command=self._scrub,
        )
        self.scale.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(9, 4))
        ttk.Label(
            body,
            textvariable=self.frame_text,
            style="Status.TLabel",
        ).grid(row=5, column=0, columnspan=6)

        controls = ttk.Frame(body)
        controls.grid(row=6, column=0, columnspan=6, pady=(10, 0))
        ttk.Button(
            controls,
            text="First",
            command=lambda: app.seek_animation(0),
        ).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="◀ Previous",
            command=lambda: app.step_animation(-1),
        ).pack(side="left", padx=3)
        ttk.Button(
            controls,
            textvariable=self.play_text,
            command=self._toggle,
        ).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="Next ▶",
            command=lambda: app.step_animation(1),
        ).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="Last",
            command=lambda: app.seek_animation(app.animation_steps - 1),
        ).pack(side="left", padx=3)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()

    def _apply_settings(self) -> bool:
        try:
            steps = int(self.steps.get())
            fps = int(self.fps.get())
            self.app.configure_animation(steps=steps, fps=fps)
        except (TypeError, ValueError) as exc:
            messagebox.showerror(
                "Invalid animation settings",
                str(exc),
                parent=self,
            )
            return False
        return True

    def _toggle(self) -> None:
        if self._apply_settings():
            self.app.toggle_animation()

    def _scrub(self, value: str) -> None:
        if self._updating_scale:
            return
        self.app.seek_animation(round(float(value)))

    def refresh(self) -> None:
        start = (
            format_complex(self.app.path_start, 8)
            if self.app.path_start is not None
            else "not selected"
        )
        end = (
            format_complex(self.app.path_end, 8)
            if self.app.path_end is not None
            else "not selected"
        )
        self.endpoint_text.set(f"A = {start}\nB = {end}")
        self.play_text.set("Pause" if self.app.animation_playing else "Play")
        self.frame_text.set(
            f"Frame {self.app.animation_index + 1}/{self.app.animation_steps}  ·  "
            f"F5 play/pause  ·  Left/Right step"
        )
        self.scale.configure(to=max(1, self.app.animation_steps - 1))
        self._updating_scale = True
        self.frame.set(self.app.animation_index)
        self._updating_scale = False

    def destroy(self) -> None:
        self.app.pause_animation()
        self.app.animation_dialog = None
        super().destroy()


class SectorDialog(tk.Toplevel):
    """Select a rational ray pair and shade its critical sector."""

    def __init__(self, pane: "FractalPane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.title("Critical sectors")
        self.resizable(False, False)
        self.transient(pane.winfo_toplevel())
        self.first = tk.StringVar(value="1/3")
        self.second = tk.StringVar(value="2/3")
        self.kind = tk.StringVar(value="critical")

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Choose two displayed rays with a common numerical landing point.",
            style="Status.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(body, text="First angle").grid(row=1, column=0, sticky="w")
        first_entry = ttk.Entry(body, textvariable=self.first, width=18)
        first_entry.grid(row=1, column=1, padx=(10, 0), pady=3)
        ttk.Label(body, text="Second angle").grid(row=2, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.second, width=18).grid(
            row=2, column=1, padx=(10, 0), pady=3
        )
        ttk.Radiobutton(
            body,
            text="Critical sector containing 0",
            variable=self.kind,
            value="critical",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Radiobutton(
            body,
            text="Critical-value sector containing c",
            variable=self.kind,
            value="critical-value",
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(
            buttons,
            text="Clear sectors",
            command=self.pane.clear_sectors,
        ).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(7, 0)
        )
        ttk.Button(buttons, text="Shade", command=self._accept).pack(side="right")

        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        first_entry.focus_set()
        first_entry.selection_range(0, "end")

    def _accept(self) -> None:
        try:
            first = parse_rational_angle(self.first.get())
            second = parse_rational_angle(self.second.get())
            self.pane.add_sector(first, second, kind=self.kind.get())
        except ValueError as exc:
            messagebox.showerror("Cannot shade sector", str(exc), parent=self)
            return
        self.destroy()


class EquipotentialDialog(tk.Toplevel):
    """Independent controls for dynamical equipotentials."""

    def __init__(self, pane: "FractalPane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.title("Dynamical equipotentials")
        self.resizable(False, False)
        self.transient(pane.winfo_toplevel())
        self.potential = tk.StringVar(value="0.15")
        self.status = tk.StringVar(
            value="Enter a positive external potential s."
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="External potential").grid(
            row=0, column=0, sticky="w"
        )
        entry = ttk.Entry(body, textvariable=self.potential, width=16)
        entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        ttk.Label(
            body,
            text=(
                "The curve is |φc(z)| = exp(s) in the basin of infinity.\n"
                "Full equipotentials require an apparently connected Julia set."
            ),
            style="Status.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 6))

        self.curve_list = tk.Listbox(
            body,
            width=48,
            height=6,
            background="#11181d",
            foreground="#dce4e2",
            selectbackground="#40535b",
            borderwidth=1,
        )
        self.curve_list.grid(row=2, column=0, columnspan=2, pady=(4, 5))
        ttk.Label(
            body,
            textvariable=self.status,
            style="Status.TLabel",
            wraplength=390,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(
            buttons,
            text="Clear equipotentials",
            command=self._clear,
        ).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right", padx=(7, 0)
        )
        ttk.Button(buttons, text="Draw", command=self._draw).pack(side="right")

        self.bind("<Return>", lambda _event: self._draw())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()
        entry.focus_set()
        entry.selection_range(0, "end")

    def _draw(self) -> None:
        try:
            description = self.pane.add_equipotential(float(self.potential.get()))
        except ValueError as exc:
            messagebox.showerror(
                "Cannot draw equipotential",
                str(exc),
                parent=self,
            )
            return
        self.status.set(description)
        self.pane.app.set_global_status(description)
        self.refresh()

    def _clear(self) -> None:
        self.pane.clear_equipotentials()
        self.status.set("Equipotentials cleared.")
        self.refresh()

    def refresh(self) -> None:
        self.curve_list.delete(0, "end")
        for potential in self.pane.equipotential_traces:
            self.curve_list.insert(
                "end",
                f"|φc| = exp({potential:.8g})",
            )

    def destroy(self) -> None:
        self.pane.equipotential_dialog = None
        super().destroy()


class ParameterRayDialog(tk.Toplevel):
    """Controls for real-Newton continuation of unicritical parameter rays."""

    def __init__(self, pane: "FractalPane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.title("External parameter rays")
        self.resizable(False, False)
        self.transient(pane.winfo_toplevel())
        self.angle = tk.StringVar(value="1/7")
        self.depth = tk.StringVar(value="12")
        self.sharpness = tk.StringVar(value="6")
        self.outer_radius = tk.StringVar(value="4")
        self.status = tk.StringVar(
            value="Continuation uses a real 2×2 Newton correction in c."
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        fields = (
            ("Rational angle", self.angle),
            ("Depth", self.depth),
            ("Sharpness", self.sharpness),
            ("Outer radius", self.outer_radius),
        )
        first_entry: ttk.Entry | None = None
        for row, (label, variable) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(body, textvariable=variable, width=18)
            entry.grid(row=row, column=1, padx=(9, 0), pady=2)
            if first_entry is None:
                first_entry = entry
        ttk.Label(
            body,
            text=(
                "The final sample is not automatically called a landing point:\n"
                "antiholomorphic parameter rays can accumulate on parabolic arcs."
            ),
            style="Status.TLabel",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 5))

        self.ray_list = tk.Listbox(
            body,
            width=58,
            height=7,
            background="#11181d",
            foreground="#dce4e2",
            selectbackground="#40535b",
            borderwidth=1,
        )
        self.ray_list.grid(row=5, column=0, columnspan=2, pady=(4, 5))
        ttk.Label(
            body,
            textvariable=self.status,
            style="Status.TLabel",
            wraplength=440,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e")
        ttk.Button(
            buttons,
            text="Clear parameter rays",
            command=self._clear,
        ).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right", padx=(7, 0)
        )
        ttk.Button(buttons, text="Draw", command=self._draw).pack(side="right")

        self.bind("<Return>", lambda _event: self._draw())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()
        if first_entry is not None:
            first_entry.focus_set()
            first_entry.selection_range(0, "end")

    def _draw(self) -> None:
        try:
            angle = parse_rational_angle(self.angle.get())
            description = self.pane.add_parameter_ray(
                angle,
                depth=int(self.depth.get()),
                sharpness=int(self.sharpness.get()),
                outer_radius=float(self.outer_radius.get()),
            )
        except ValueError as exc:
            messagebox.showerror(
                "Cannot draw parameter ray",
                str(exc),
                parent=self,
            )
            return
        self.status.set(description)
        self.pane.app.set_global_status(description)
        self.refresh()

    def _clear(self) -> None:
        self.pane.clear_parameter_rays()
        self.status.set("Parameter rays cleared.")
        self.refresh()

    def refresh(self) -> None:
        self.ray_list.delete(0, "end")
        for angle, trace in self.pane.parameter_ray_traces.items():
            final = format_complex(trace.final_sample, digits=9)
            suffix = " · truncated" if trace.stop_reason else ""
            self.ray_list.insert(
                "end",
                f"R_{angle}  final sample ≈ {final}{suffix}",
            )

    def destroy(self) -> None:
        self.pane.parameter_ray_dialog = None
        super().destroy()


class InternalCurveDialog(tk.Toplevel):
    """Controls for internal Koenigs/Böttcher grand-orbit contours."""

    def __init__(self, pane: "FractalPane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.title("Internal coordinate curves")
        self.resizable(False, False)
        self.transient(pane.winfo_toplevel())
        self.log_radius = tk.StringVar(value="-1")
        self.generations = tk.StringVar(value="4")
        self.resolution = tk.StringVar(value="240")
        self.status = tk.StringVar(
            value="Curves are extracted from a numerical basin-coordinate field."
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        fields = (
            ("Representative log |φ|", self.log_radius),
            ("Grand-orbit generations", self.generations),
            ("Field resolution", self.resolution),
        )
        first_entry: ttk.Entry | None = None
        for row, (label, variable) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(body, textvariable=variable, width=18)
            entry.grid(row=row, column=1, padx=(9, 0), pady=2)
            if first_entry is None:
                first_entry = entry
        ttk.Label(
            body,
            text=(
                "Even-period cycles use f^p; odd-period cycles use the\n"
                "holomorphic return f^(2p). The bold curve is the representative."
            ),
            style="Status.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 6))
        ttk.Label(
            body,
            textvariable=self.status,
            style="Status.TLabel",
            wraplength=420,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(
            buttons,
            text="Clear curves",
            command=self._clear,
        ).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right", padx=(7, 0)
        )
        ttk.Button(buttons, text="Draw", command=self._draw).pack(side="right")

        self.bind("<Return>", lambda _event: self._draw())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        if first_entry is not None:
            first_entry.focus_set()
            first_entry.selection_range(0, "end")

    def _draw(self) -> None:
        try:
            description = self.pane.add_internal_curves(
                representative_log_radius=float(self.log_radius.get()),
                generations=int(self.generations.get()),
                resolution=int(self.resolution.get()),
            )
        except ValueError as exc:
            messagebox.showerror(
                "Cannot draw internal curves",
                str(exc),
                parent=self,
            )
            return
        self.status.set(description)
        self.pane.app.set_global_status(description)

    def _clear(self) -> None:
        self.pane.clear_internal_curves()
        self.status.set("Internal coordinate curves cleared.")

    def destroy(self) -> None:
        self.pane.internal_curve_dialog = None
        super().destroy()


class RayDialog(tk.Toplevel):
    """Persistent controls for exact rational-angle dynamical rays."""

    def __init__(self, pane: "FractalPane") -> None:
        super().__init__(pane)
        self.pane = pane
        self.title("Dynamical rays")
        self.resizable(False, False)
        self.transient(pane.winfo_toplevel())
        self.angle = tk.StringVar(value="1/7")
        self.complete_orbit = tk.BooleanVar(value=False)
        self.status = tk.StringVar(
            value=(
                "Angles evolve exactly by  t ↦ "
                f"{'−' if pane.app.antiholomorphic else ''}"
                f"{pane.app.degree.get()}t  (mod 1)."
            )
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Rational angle").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(body, textvariable=self.angle, width=18)
        entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        ttk.Checkbutton(
            body,
            text="Draw complete forward angle orbit",
            variable=self.complete_orbit,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 5))
        ttk.Label(
            body,
            text=(
                "Full rays are drawn only when the critical orbit appears bounded.\n"
                "The final marker is a numerical landing approximation."
            ),
            style="Status.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        self.ray_list = tk.Listbox(
            body,
            width=58,
            height=8,
            background="#11181d",
            foreground="#dce4e2",
            selectbackground="#40535b",
            borderwidth=1,
        )
        self.ray_list.grid(row=3, column=0, columnspan=2, pady=(8, 5))
        ttk.Label(
            body,
            textvariable=self.status,
            style="Status.TLabel",
            wraplength=430,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 8))

        analysis_buttons = ttk.Frame(body)
        analysis_buttons.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            analysis_buttons,
            text="Clear rays",
            command=self._clear,
        ).pack(side="left")
        ttk.Button(
            analysis_buttons,
            text="Analyze portrait",
            command=self._portrait,
        ).pack(side="left", padx=(7, 0))
        ttk.Button(
            analysis_buttons,
            text="Sectors…",
            command=lambda: SectorDialog(self.pane),
        ).pack(side="left", padx=(7, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(7, 0))
        ttk.Button(
            buttons,
            text="Replace with next",
            command=self._replace_next,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Add next",
            command=self._add_next,
        ).pack(side="left", padx=(7, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right", padx=(7, 0)
        )
        ttk.Button(buttons, text="Draw", command=self._draw).pack(side="right")

        self.bind("<Return>", lambda _event: self._draw())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()
        entry.focus_set()
        entry.selection_range(0, "end")

    def _draw(self) -> None:
        try:
            angle = parse_rational_angle(self.angle.get())
            added, description = self.pane.add_dynamical_rays(
                angle,
                complete_orbit=self.complete_orbit.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Cannot draw ray", str(exc), parent=self)
            return
        self.status.set(description)
        self.refresh()
        if added:
            self.pane.app.set_global_status(description)

    def _clear(self) -> None:
        self.pane.clear_dynamical_rays()
        self.status.set("Rays, portrait labels, and ray sectors cleared.")
        self.refresh()

    def _replace_next(self) -> None:
        added, description = self.pane.replace_with_next_ray_iterates()
        self.status.set(description)
        self.refresh()
        if added:
            self.pane.app.set_global_status(description)

    def _add_next(self) -> None:
        added, description = self.pane.add_next_ray_iterates()
        self.status.set(description)
        self.refresh()
        if added:
            self.pane.app.set_global_status(description)

    def _portrait(self) -> None:
        try:
            report = self.pane.analyze_orbit_portrait()
        except ValueError as exc:
            messagebox.showerror("Cannot analyze portrait", str(exc), parent=self)
            return
        messagebox.showinfo("Numerical orbit portrait", report, parent=self)
        self.status.set("Orbit portrait analyzed and labeled on the canvas.")

    def refresh(self) -> None:
        self.ray_list.delete(0, "end")
        for angle, ray in self.pane.ray_traces.items():
            landing = format_complex(ray.landing_approximation, digits=7)
            self.ray_list.insert("end", f"R_{angle}   landing ≈ {landing}")
        for sector in self.pane.sector_specs:
            self.ray_list.insert(
                "end",
                f"{sector.kind}: {sector.first_angle}, {sector.second_angle}",
            )

    def destroy(self) -> None:
        self.pane.ray_dialog = None
        super().destroy()


class FractalPane(ttk.Frame):
    """Controls and canvas for one independently rendered fractal."""

    def __init__(
        self,
        master: tk.Misc,
        app: "BifurcationLoomApp",
        *,
        title: str,
        kind: str,
        modes: dict[str, str],
        initial_mode: str,
    ) -> None:
        super().__init__(master, padding=((9, 5) if COMPACT_LAYOUT else (12, 8)))
        self.app = app
        self.kind = kind
        self.modes = modes
        self.viewport = Viewport()
        self.output_path = IMAGE_DIR / f"{kind}.ppm"
        self.photo: ImageTk.PhotoImage | None = None
        self.drag_start: tuple[int, int] | None = None
        self.selection_id: int | None = None
        self.busy = False
        self.render_again = False
        self.ray_traces: dict[Fraction, RayTrace] = {}
        self.equipotential_traces: dict[float, EquipotentialTrace] = {}
        self.parameter_ray_traces: dict[Fraction, ParameterRayTrace] = {}
        self.portrait_clusters: tuple[LandingCluster, ...] = ()
        self.sector_specs: list[SectorSpec] = []
        self.sector_polygons: dict[SectorSpec, tuple[complex, ...]] = {}
        self.internal_curves: InternalCurveSet | None = None
        self.internal_curve_settings: tuple[float, int, int] | None = None
        self.ray_dialog: RayDialog | None = None
        self.equipotential_dialog: EquipotentialDialog | None = None
        self.parameter_ray_dialog: ParameterRayDialog | None = None
        self.internal_curve_dialog: InternalCurveDialog | None = None
        self.arbitrary_precision_allowed = False

        self.mode = tk.StringVar(value=initial_mode)
        self.iterations = tk.IntVar(value=512)
        self.max_period = tk.IntVar(value=20)
        self.quality = tk.StringVar(value=quality_label(2))
        self.precision = tk.StringVar(value="Automatic")
        self.precision_text = tk.StringVar(value="")
        self.square_zoom = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")
        self.view_text = tk.StringVar(value=self.viewport.description())
        self.show_attracting_orbit = tk.BooleanVar(value=True)
        self.orbit_text = tk.StringVar(value="")

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        self.title_label = ttk.Label(
            header,
            text=title,
            style="Title.TLabel",
        )
        self.title_label.pack(side="left")
        ttk.Label(header, textvariable=self.status, style="Status.TLabel").pack(
            side="right"
        )

        self.canvas = tk.Canvas(
            self,
            width=CANVAS_SIZE,
            height=CANVAS_SIZE,
            background="#11181d",
            highlightthickness=1,
            highlightbackground="#3d4b52",
            cursor="crosshair",
            takefocus=True,
        )
        self.canvas.pack(anchor="center")
        self.canvas.bind("<ButtonPress-1>", self._start_selection)
        self.canvas.bind("<B1-Motion>", self._move_selection)
        self.canvas.bind("<ButtonRelease-1>", self._finish_selection)
        self.canvas.bind("<Button-3>", self._cancel_selection)
        if self.kind == "julia":
            self.canvas.bind("<KeyPress-space>", self.app.iterate_dynamical_point)

        ttk.Label(self, textvariable=self.view_text, style="Meta.TLabel").pack(
            anchor="w", pady=(7, 4)
        )

        modes_frame = ttk.LabelFrame(self, text="Drawing mode", padding=7)
        modes_frame.pack(fill="x", pady=4)
        for column, label in enumerate(modes):
            ttk.Radiobutton(
                modes_frame,
                text=label,
                value=label,
                variable=self.mode,
                command=self.request_render,
            ).grid(
                row=column // 3,
                column=column % 3,
                padx=(0, 14),
                pady=(0, 3),
                sticky="w",
            )

        settings = ttk.Frame(self)
        settings.pack(fill="x", pady=(7, 0))
        ttk.Label(settings, text="Iterations").pack(side="left")
        iteration_box = ttk.Combobox(
            settings,
            textvariable=self.iterations,
            values=ITERATION_OPTIONS,
            state="readonly",
            width=6,
        )
        iteration_box.pack(side="left", padx=(6, 10))
        iteration_box.bind("<<ComboboxSelected>>", lambda _event: self.request_render())

        ttk.Label(settings, text="Quality").pack(side="left")
        quality_box = ttk.Combobox(
            settings,
            textvariable=self.quality,
            values=tuple(QUALITY_OPTIONS),
            state="readonly",
            width=14,
        )
        quality_box.pack(side="left", padx=(6, 8))
        quality_box.bind("<<ComboboxSelected>>", self._quality_changed)

        ttk.Button(settings, text="Reset", command=self.reset).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(settings, text="Save PNG…", command=self.save_png).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(settings, text="Render", command=self.request_render).pack(side="right")

        numerics = ttk.Frame(self)
        numerics.pack(fill="x", pady=(5, 0))
        ttk.Label(numerics, text="Precision").pack(side="left")
        precision_box = ttk.Combobox(
            numerics,
            textvariable=self.precision,
            values=PRECISION_CHOICES,
            state="readonly",
            width=17,
        )
        precision_box.pack(side="left", padx=(6, 8))
        precision_box.bind("<<ComboboxSelected>>", self._precision_changed)
        ttk.Label(
            numerics,
            textvariable=self.precision_text,
            style="Status.TLabel",
        ).pack(side="left")
        ttk.Checkbutton(
            numerics,
            text="Square zoom",
            variable=self.square_zoom,
        ).pack(side="right")

        if self.kind == "parameter":
            period_controls = ttk.Frame(self)
            period_controls.pack(fill="x", pady=(5, 0))
            ttk.Label(period_controls, text="Component search through period").pack(
                side="left"
            )
            period_box = ttk.Combobox(
                period_controls,
                textvariable=self.max_period,
                values=PERIOD_OPTIONS,
                state="readonly",
                width=4,
            )
            period_box.pack(side="left", padx=(6, 8))
            period_box.bind(
                "<<ComboboxSelected>>",
                lambda _event: self.request_render(),
            )
            ttk.Button(
                period_controls,
                text="Period legend…",
                command=self.show_period_legend,
            ).pack(side="right")

        if self.kind == "julia":
            overlays = ttk.LabelFrame(self, text="Dynamical overlays", padding=7)
            overlays.pack(fill="x", pady=(7, 0))
            ttk.Checkbutton(
                overlays,
                text="Attracting critical orbit",
                variable=self.show_attracting_orbit,
                command=self.draw_overlays,
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                overlays, textvariable=self.orbit_text, style="Status.TLabel"
            ).grid(row=0, column=1, padx=10, sticky="w")
            ttk.Button(
                overlays,
                text="Set z…",
                command=self.app.prompt_dynamical_point,
            ).grid(row=0, column=2, padx=(6, 0), sticky="e")
            ttk.Button(
                overlays,
                text="Dynamical rays…",
                command=self.show_ray_dialog,
            ).grid(row=1, column=2, padx=(6, 0), pady=(6, 0), sticky="e")
            ttk.Button(
                overlays,
                text="Equipotentials…",
                command=self.show_equipotential_dialog,
            ).grid(row=1, column=3, padx=(6, 0), pady=(6, 0), sticky="e")
            ttk.Button(
                overlays,
                text="Internal curves…",
                command=self.show_internal_curve_dialog,
            ).grid(row=1, column=4, padx=(6, 0), pady=(6, 0), sticky="e")
            overlays.columnconfigure(1, weight=1)
            ttk.Label(
                overlays,
                textvariable=self.app.dynamical_point_text,
                style="Status.TLabel",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        else:
            overlays = ttk.LabelFrame(self, text="Parameter overlays", padding=7)
            overlays.pack(fill="x", pady=(7, 0))
            ttk.Label(
                overlays,
                text="Choose A and B for a linear Julia-set path.",
                style="Status.TLabel",
            ).grid(row=0, column=0, sticky="w")
            ttk.Button(
                overlays,
                text="Parameter rays…",
                command=self.show_parameter_ray_dialog,
            ).grid(row=0, column=1, padx=(6, 0))
            ttk.Button(
                overlays,
                text="Pick A",
                command=lambda: self.app.begin_path_pick("A"),
            ).grid(row=0, column=2, padx=(6, 0))
            ttk.Button(
                overlays,
                text="Pick B",
                command=lambda: self.app.begin_path_pick("B"),
            ).grid(row=0, column=3, padx=(6, 0))
            ttk.Button(
                overlays,
                text="Animate path…",
                command=self.app.show_animation_dialog,
            ).grid(row=0, column=4, padx=(6, 0))
            overlays.columnconfigure(0, weight=1)
        self._update_precision_text()

    @property
    def render_size(self) -> int:
        return CANVAS_SIZE * QUALITY_OPTIONS[self.quality.get()]

    @property
    def effective_precision(self) -> PrecisionDecision:
        decision = precision_decision(
            self.precision.get(),
            self.viewport,
            self.render_size,
        )
        if self.precision.get() == "Automatic" and self.kind == "julia":
            parameter_bits = max(
                self.app.julia_parameter.real._mpf_[3],
                self.app.julia_parameter.imag._mpf_[3],
            )
            required = max(decision.required_bits, parameter_bits)
            if required > 53:
                return PrecisionDecision(
                    "arbitrary",
                    max(80, required + 24),
                    required,
                )
            if required > 24 and decision.mode == "float":
                return PrecisionDecision("double", 53, required)
        return decision

    def _update_precision_text(self) -> None:
        decision = self.effective_precision
        prefix = "Auto → " if self.precision.get() == "Automatic" else ""
        warning = (
            f" · needs ≈{decision.required_bits} bits"
            if decision.required_bits > decision.bits
            else ""
        )
        self.precision_text.set(prefix + decision.label + warning)

    def _confirm_arbitrary_precision(self, decision: PrecisionDecision) -> bool:
        if decision.mode != "arbitrary":
            return True
        if self.arbitrary_precision_allowed:
            mp.mp.prec = max(mp.mp.prec, decision.bits)
            return True
        reason = (
            "This zoom needs more coordinate precision than binary64 can "
            f"safely provide ({decision.required_bits} estimated bits)."
            if decision.required_bits > 53
            else "You selected the arbitrary-precision renderer."
        )
        accepted = messagebox.askyesno(
            "Switch to arbitrary precision?",
            (
                f"{reason}\n\n"
                f"The application will switch to a {decision.bits}-bit "
                "reference-orbit renderer. It can be substantially slower, "
                "especially above 1× quality.\n\nContinue with this zoom?"
            ),
            parent=self,
        )
        if accepted:
            self.arbitrary_precision_allowed = True
            mp.mp.prec = max(mp.mp.prec, decision.bits)
        return accepted

    def _precision_changed(self, _event: tk.Event | None = None) -> None:
        decision = self.effective_precision
        if not self._confirm_arbitrary_precision(decision):
            self.precision.set("Double (64-bit)")
            decision = self.effective_precision
        self._update_precision_text()
        self.retrace_external_overlays(redraw=False)
        self.request_render()

    @property
    def world_per_render_pixel(self) -> float:
        span = max(
            self.viewport.xmax - self.viewport.xmin,
            self.viewport.ymax - self.viewport.ymin,
        )
        return float(span / self.render_size)

    @property
    def ray_minimum_potential(self) -> float:
        # At c=0, potential is asymptotically the Euclidean gap to J(f_c).
        # One eighth of a render pixel keeps the endpoint visually attached
        # while leaving room for numerical error at distorted Julia boundaries.
        span = max(
            self.viewport.xmax - self.viewport.xmin,
            self.viewport.ymax - self.viewport.ymin,
        )
        if self.effective_precision.mode == "arbitrary":
            return max(
                1e-300,
                float(mp.mpf("0.125") * span / self.render_size),
            )
        return adaptive_minimum_potential(float(span), self.render_size)

    @property
    def landing_tolerance(self) -> float:
        return 3.0 * self.world_per_render_pixel

    def _trace_ray(self, angle: Fraction) -> RayTrace:
        decision = self.effective_precision
        return trace_external_ray(
            (
                self.app.julia_parameter
                if decision.mode == "arbitrary"
                else complex(self.app.julia_parameter)
            ),
            angle,
            samples=max(300, self.render_size // 3),
            minimum_potential=self.ray_minimum_potential,
            require_connected=False,
            precision_bits=(
                decision.bits if decision.mode == "arbitrary" else None
            ),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )

    def _quality_changed(self, _event: tk.Event | None = None) -> None:
        decision = self.effective_precision
        if not self._confirm_arbitrary_precision(decision):
            self.quality.set(quality_label(1))
        self._update_precision_text()
        self.retrace_external_overlays(redraw=False)
        self.request_render()

    def native_render_options(self) -> NativeRenderOptions:
        decision = self.effective_precision
        return NativeRenderOptions(
            kind=self.kind,
            dynamics=self.app.dynamics_code,
            mode=self.modes[self.mode.get()],
            degree=self.app.degree.get(),
            width=self.render_size,
            height=self.render_size,
            iterations=self.iterations.get(),
            max_period=self.max_period.get(),
            draw_boundary=False,
            precision=decision.mode,
            xmin=float(self.viewport.xmin),
            xmax=float(self.viewport.xmax),
            ymin=float(self.viewport.ymin),
            ymax=float(self.viewport.ymax),
            parameter_real=float(self.app.julia_parameter.real),
            parameter_imag=float(self.app.julia_parameter.imag),
        )

    def arbitrary_render_options(self) -> ArbitraryRenderOptions:
        decision = self.effective_precision
        return ArbitraryRenderOptions(
            kind=self.kind,
            mode=self.modes[self.mode.get()],
            xmin=mp.nstr(self.viewport.xmin, decision.bits // 3 + 10),
            xmax=mp.nstr(self.viewport.xmax, decision.bits // 3 + 10),
            ymin=mp.nstr(self.viewport.ymin, decision.bits // 3 + 10),
            ymax=mp.nstr(self.viewport.ymax, decision.bits // 3 + 10),
            parameter_real=mp.nstr(
                self.app.julia_parameter.real,
                decision.bits // 3 + 10,
            ),
            parameter_imag=mp.nstr(
                self.app.julia_parameter.imag,
                decision.bits // 3 + 10,
            ),
            iterations=self.iterations.get(),
            width=self.render_size,
            height=self.render_size,
            bits=decision.bits,
            output_path=self.output_path,
            max_period=self.max_period.get(),
            dynamics=self.app.dynamics_code,
            degree=self.app.degree.get(),
        )

    def show_period_legend(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Component-period colors")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Exact period of the detected attracting cycle"
            ),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        for index in range(self.max_period.get()):
            period = index + 1
            row = 1 + index // 4
            column = index % 4
            item = tk.Frame(body, background="#26343a", padx=5, pady=4)
            item.grid(row=row, column=column, padx=3, pady=3, sticky="ew")
            swatch = tk.Label(
                item,
                text="  ",
                background=PERIOD_COLORS[index % len(PERIOD_COLORS)],
            )
            swatch.pack(side="left")
            tk.Label(
                item,
                text=f"  {period}",
                background="#26343a",
                foreground="#eef4f1",
            ).pack(side="left")
        note_row = 2 + (self.max_period.get() - 1) // 4
        ttk.Label(
            body,
            text=(
                "Neutral charcoal means bounded, but no attracting cycle was "
                "certified within the selected range."
            ),
            style="Meta.TLabel",
            wraplength=440,
        ).grid(row=note_row, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(body, text="Close", command=dialog.destroy).grid(
            row=note_row + 1,
            column=3,
            sticky="e",
            pady=(10, 0),
        )
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def request_render(self) -> None:
        if self.busy:
            self.render_again = True
            self._delete_dynamical_overlay_items()
            return
        self.busy = True
        self._delete_dynamical_overlay_items()
        decision = self.effective_precision
        self._update_precision_text()
        self.status.set(
            f"Rendering {self.quality.get()} · {decision.label}…"
        )
        self.app.set_global_status(f"Rendering {self.kind}…")
        if decision.mode == "arbitrary":
            options = self.arbitrary_render_options()
            threading.Thread(
                target=self._render_worker_arbitrary,
                args=(options,),
                daemon=True,
                name=f"{self.kind}-arbitrary-renderer",
            ).start()
        else:
            options = self.native_render_options()
            threading.Thread(
                target=self._render_worker,
                args=(options,),
                daemon=True,
                name=f"{self.kind}-renderer",
            ).start()

    def _render_worker(self, options: NativeRenderOptions) -> None:
        try:
            render_native(options).save(self.output_path, format="PPM")
        except Exception as exc:
            result = subprocess.CompletedProcess(
                args=["native-shared-library"],
                returncode=1,
                stdout="",
                stderr=str(exc),
            )
        else:
            result = subprocess.CompletedProcess(
                args=["native-shared-library"],
                returncode=0,
                stdout="",
                stderr="",
            )
        self.app.results.put((self, result))

    def _render_worker_arbitrary(
        self,
        options: ArbitraryRenderOptions,
    ) -> None:
        try:
            render_arbitrary(options)
        except Exception as exc:  # Report numerical failures through the GUI queue.
            result = subprocess.CompletedProcess(
                args=["arbitrary-reference-renderer"],
                returncode=1,
                stdout="",
                stderr=str(exc),
            )
        else:
            result = subprocess.CompletedProcess(
                args=["arbitrary-reference-renderer"],
                returncode=0,
                stdout="",
                stderr="",
            )
        self.app.results.put((self, result))

    def finish_render(self, result: subprocess.CompletedProcess[str]) -> None:
        self.busy = False
        if result.returncode != 0:
            self.status.set("Render failed")
            self.app.set_global_status("A render failed")
            messagebox.showerror(
                "Rendering failed",
                result.stderr.strip() or "The C renderer returned an unknown error.",
                parent=self,
            )
        else:
            with Image.open(self.output_path) as source:
                display = source.convert("RGB")
            if display.size != (CANVAS_SIZE, CANVAS_SIZE):
                display = display.resize(
                    (CANVAS_SIZE, CANVAS_SIZE),
                    Image.Resampling.LANCZOS,
                )
            self.photo = ImageTk.PhotoImage(display)
            self.canvas.delete("fractal")
            self.canvas.create_image(
                0, 0, image=self.photo, anchor="nw", tags=("fractal",)
            )
            self.canvas.tag_lower("fractal")
            self.status.set("Ready")
            self.view_text.set(self.viewport.description())
            self.app.set_global_status("Ready")
            # Let Tk paint the new base image before adding vector overlays.
            self.after(1, self._draw_overlays_if_ready)

        if self.render_again:
            self.render_again = False
            self.request_render()

    def _delete_dynamical_overlay_items(self) -> None:
        tags = (
            ("parameter-ray", "parameter-path")
            if self.kind == "parameter"
            else (
                "ray-sector",
                "internal-curve",
                "equipotential",
                "dynamical-ray",
                "portrait-label",
                "attracting-orbit",
                "selected-point",
            )
        )
        for tag in tags:
            self.canvas.delete(tag)

    def _draw_overlays_if_ready(self) -> None:
        if not self.busy:
            self.draw_overlays()

    def draw_overlays(self) -> None:
        if self.busy:
            return
        if self.kind == "parameter":
            self._draw_parameter_rays()
            self._draw_parameter_path()
            return
        self._draw_sectors()
        self._draw_internal_curves()
        self._draw_equipotentials()
        self._draw_dynamical_rays()
        self._draw_portrait_labels()
        self._draw_attracting_orbit()
        self._draw_selected_point()

    def _draw_parameter_rays(self) -> None:
        self.canvas.delete("parameter-ray")
        if self.kind != "parameter":
            return
        for index, (angle, trace) in enumerate(
            self.parameter_ray_traces.items()
        ):
            color = RAY_COLORS[index % len(RAY_COLORS)]
            pixels = [
                self.viewport.pixel_at(value, CANVAS_SIZE)
                for value in trace.points
            ]
            flattened = [
                coordinate for point in pixels for coordinate in point
            ]
            self.canvas.create_line(
                *flattened,
                fill=color,
                width=2,
                tags=("parameter-ray",),
            )
            x, y = pixels[-1]
            self.canvas.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill="#11171b",
                outline=color,
                width=2,
                tags=("parameter-ray",),
            )
            self._create_contrast_text(
                x + 7,
                y - 7,
                text=f"R_{angle}",
                fill=color,
                tags=("parameter-ray",),
            )
        self.canvas.tag_raise("parameter-ray")

    def _draw_parameter_path(self) -> None:
        self.canvas.delete("parameter-path")
        if self.kind != "parameter":
            return
        start = self.app.path_start
        end = self.app.path_end
        if start is not None and end is not None:
            x1, y1 = self.viewport.pixel_at(start, CANVAS_SIZE)
            x2, y2 = self.viewport.pixel_at(end, CANVAS_SIZE)
            self.canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill="#f1f5f2",
                width=2,
                dash=(5, 4),
                tags=("parameter-path",),
            )
            current = ParameterPath(
                start,
                end,
                self.app.animation_steps,
            ).parameter_at(self.app.animation_index)
            current_x, current_y = self.viewport.pixel_at(
                current,
                CANVAS_SIZE,
            )
            self.canvas.create_oval(
                current_x - 4,
                current_y - 4,
                current_x + 4,
                current_y + 4,
                fill="#f5e27a",
                outline="#11171b",
                width=1,
                tags=("parameter-path",),
            )
        for label, point, color in (
            ("A", start, "#65dfad"),
            ("B", end, "#ff9b7c"),
        ):
            if point is None:
                continue
            x, y = self.viewport.pixel_at(point, CANVAS_SIZE)
            self.canvas.create_oval(
                x - 7,
                y - 7,
                x + 7,
                y + 7,
                fill="#11171b",
                outline=color,
                width=2,
                tags=("parameter-path",),
            )
            self._create_contrast_text(
                x + 9,
                y - 9,
                text=label,
                fill=color,
                tags=("parameter-path",),
            )
        self.canvas.tag_raise("parameter-path")

    def _draw_internal_curves(self) -> None:
        self.canvas.delete("internal-curve")
        if self.kind != "julia" or self.internal_curves is None:
            return
        for index, curve in enumerate(self.internal_curves.curves):
            color = "#f4f0e8" if curve.representative else "#b7d7cb"
            width = 3 if curve.representative else 1
            for polyline in curve.polylines:
                pixels = [
                    self.viewport.pixel_at(value, CANVAS_SIZE)
                    for value in polyline
                ]
                flattened = [
                    coordinate for point in pixels for coordinate in point
                ]
                self.canvas.create_line(
                    *flattened,
                    fill=color,
                    width=width,
                    smooth=True,
                    tags=("internal-curve",),
                )
        self.canvas.tag_raise("internal-curve")

    def _create_contrast_text(
        self,
        x: float,
        y: float,
        *,
        text: str,
        fill: str,
        anchor: str = "sw",
        tags: tuple[str, ...],
    ) -> None:
        for dx, dy in (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        ):
            self.canvas.create_text(
                x + dx,
                y + dy,
                text=text,
                fill="#ffffff",
                anchor=anchor,
                tags=tags,
            )
        self.canvas.create_text(
            x,
            y,
            text=text,
            fill=fill,
            anchor=anchor,
            tags=tags,
        )

    def _draw_sectors(self) -> None:
        self.canvas.delete("ray-sector")
        if self.kind != "julia":
            return
        for spec in self.sector_specs:
            polygon = self.sector_polygons.get(spec)
            if not polygon:
                continue
            pixels = [
                self.viewport.pixel_at(value, CANVAS_SIZE)
                for value in polygon
            ]
            flattened = [coordinate for point in pixels for coordinate in point]
            fill = "#6c4f86" if spec.kind == "critical" else "#8a613b"
            self.canvas.create_polygon(
                *flattened,
                fill=fill,
                outline="",
                stipple="gray25",
                tags=("ray-sector",),
            )
            target = 0j if spec.kind == "critical" else self.app.julia_parameter
            x, y = self.viewport.pixel_at(target, CANVAS_SIZE)
            self._create_contrast_text(
                x + 8,
                y - 8,
                text=(
                    "critical sector"
                    if spec.kind == "critical"
                    else "critical-value sector"
                ),
                fill="#33213f" if spec.kind == "critical" else "#4a2c16",
                tags=("ray-sector",),
            )
        self.canvas.tag_raise("ray-sector")

    def _draw_equipotentials(self) -> None:
        self.canvas.delete("equipotential")
        if self.kind != "julia":
            return
        for index, trace in enumerate(self.equipotential_traces.values()):
            points = [
                self.viewport.pixel_at(value, CANVAS_SIZE)
                for value in trace.points
            ]
            flattened = [coordinate for point in points for coordinate in point]
            color = ("#e8edf0", "#a9c9d2", "#d4b8df")[index % 3]
            self.canvas.create_line(
                *flattened,
                fill=color,
                width=1,
                dash=(4, 3),
                tags=("equipotential",),
            )
        self.canvas.tag_raise("equipotential")

    def _draw_attracting_orbit(self) -> None:
        self.canvas.delete("attracting-orbit")
        if self.kind != "julia":
            return
        if not self.show_attracting_orbit.get():
            self.orbit_text.set("Hidden")
            return
        orbit = self.app.attracting_orbit
        if orbit is None:
            self.orbit_text.set("No attracting cycle detected")
            return

        self.orbit_text.set(f"Detected period {len(orbit)}")
        for value in orbit:
            x, y = self.viewport.pixel_at(value, CANVAS_SIZE)
            if not (-8 <= x <= CANVAS_SIZE + 8 and -8 <= y <= CANVAS_SIZE + 8):
                continue
            self.canvas.create_oval(
                x - 7,
                y - 7,
                x + 7,
                y + 7,
                fill="#11171b",
                outline="#11171b",
                tags=("attracting-orbit",),
            )
            self.canvas.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill="#ffc867",
                outline="#ffe0a3",
                tags=("attracting-orbit",),
            )
        self.canvas.tag_raise("attracting-orbit")

    def _draw_selected_point(self) -> None:
        self.canvas.delete("selected-point")
        if self.kind != "julia" or self.app.dynamical_point is None:
            return
        x, y = self.viewport.pixel_at(self.app.dynamical_point, CANVAS_SIZE)
        if not (-10 <= x <= CANVAS_SIZE + 10 and -10 <= y <= CANVAS_SIZE + 10):
            return
        self.canvas.create_oval(
            x - 8,
            y - 8,
            x + 8,
            y + 8,
            fill="#10241c",
            outline="#10241c",
            tags=("selected-point",),
        )
        self.canvas.create_oval(
            x - 5,
            y - 5,
            x + 5,
            y + 5,
            fill="#61d69a",
            outline="#b2f5d0",
            width=2,
            tags=("selected-point",),
        )
        self.canvas.tag_raise("selected-point")

    def _draw_dynamical_rays(self) -> None:
        self.canvas.delete("dynamical-ray")
        if self.kind != "julia":
            return
        for index, (angle, ray) in enumerate(self.ray_traces.items()):
            color = RAY_COLORS[index % len(RAY_COLORS)]
            pixels = [
                self.viewport.pixel_at(value, CANVAS_SIZE)
                for value in ray.points
            ]
            flattened = [coordinate for point in pixels for coordinate in point]
            self.canvas.create_line(
                *flattened,
                fill=color,
                width=2,
                smooth=False,
                tags=("dynamical-ray",),
            )
            x, y = pixels[-1]
            self.canvas.create_oval(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill="#11171b",
                outline=color,
                width=2,
                tags=("dynamical-ray",),
            )
            self._create_contrast_text(
                x + 7,
                y - 7,
                text=str(angle),
                fill=color,
                anchor="sw",
                tags=("dynamical-ray",),
            )
        self.canvas.tag_raise("dynamical-ray")

    def _draw_portrait_labels(self) -> None:
        self.canvas.delete("portrait-label")
        if self.kind != "julia":
            return
        for index, cluster in enumerate(self.portrait_clusters, start=1):
            x, y = self.viewport.pixel_at(cluster.point, CANVAS_SIZE)
            angle_text = ", ".join(str(angle) for angle in cluster.angles)
            self._create_contrast_text(
                x + 8,
                y + 13,
                text=f"A{index} = {{{angle_text}}}",
                fill="#152027",
                tags=("portrait-label",),
            )
        self.canvas.tag_raise("portrait-label")

    def show_ray_dialog(self) -> None:
        if self.ray_dialog is not None and self.ray_dialog.winfo_exists():
            self.ray_dialog.lift()
            self.ray_dialog.focus_force()
            return
        self.ray_dialog = RayDialog(self)

    def show_equipotential_dialog(self) -> None:
        if (
            self.equipotential_dialog is not None
            and self.equipotential_dialog.winfo_exists()
        ):
            self.equipotential_dialog.lift()
            self.equipotential_dialog.focus_force()
            return
        self.equipotential_dialog = EquipotentialDialog(self)

    def show_parameter_ray_dialog(self) -> None:
        if (
            self.parameter_ray_dialog is not None
            and self.parameter_ray_dialog.winfo_exists()
        ):
            self.parameter_ray_dialog.lift()
            self.parameter_ray_dialog.focus_force()
            return
        self.parameter_ray_dialog = ParameterRayDialog(self)

    def show_internal_curve_dialog(self) -> None:
        if (
            self.internal_curve_dialog is not None
            and self.internal_curve_dialog.winfo_exists()
        ):
            self.internal_curve_dialog.lift()
            self.internal_curve_dialog.focus_force()
            return
        self.internal_curve_dialog = InternalCurveDialog(self)

    def add_parameter_ray(
        self,
        angle: Fraction,
        *,
        depth: int,
        sharpness: int,
        outer_radius: float,
    ) -> str:
        if self.kind != "parameter":
            raise ValueError("Parameter rays belong to the parameter plane.")
        trace = trace_parameter_ray(
            angle,
            depth=depth,
            sharpness=sharpness,
            outer_radius=outer_radius,
            precision_bits=(
                self.effective_precision.bits
                if self.effective_precision.mode == "arbitrary"
                else None
            ),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )
        self.parameter_ray_traces[angle] = trace
        self.draw_overlays()
        if self.parameter_ray_dialog is not None:
            self.parameter_ray_dialog.refresh()
        description = (
            f"Traced parameter ray {angle}: {len(trace.points)}/"
            f"{trace.requested_samples} continuation samples."
        )
        if trace.stop_reason:
            description += " " + trace.stop_reason
        return description

    def clear_parameter_rays(self) -> None:
        self.parameter_ray_traces.clear()
        self.canvas.delete("parameter-ray")
        if self.parameter_ray_dialog is not None:
            self.parameter_ray_dialog.refresh()

    def add_internal_curves(
        self,
        *,
        representative_log_radius: float,
        generations: int,
        resolution: int,
    ) -> str:
        orbit = self.app.attracting_orbit
        if not orbit:
            raise ValueError(
                "No attracting critical cycle is available for this parameter."
            )
        bounds = (
            float(self.viewport.xmin),
            float(self.viewport.xmax),
            float(self.viewport.ymin),
            float(self.viewport.ymax),
        )
        if max(
            self.viewport.xmax - self.viewport.xmin,
            self.viewport.ymax - self.viewport.ymin,
        ) < mp.mpf("1e-13"):
            raise ValueError(
                "Internal contour extraction currently needs a viewport wider "
                "than 1e-13; reset or zoom out before drawing these curves."
            )
        self.status.set("Computing internal coordinate curves…")
        self.update_idletasks()
        try:
            computed = trace_internal_grand_orbit(
                complex(self.app.julia_parameter),
                tuple(complex(value) for value in orbit),
                bounds,
                representative_log_radius=representative_log_radius,
                generations=generations,
                resolution=resolution,
                degree=self.app.degree.get(),
                antiholomorphic=self.app.antiholomorphic,
            )
        finally:
            self.status.set("Ready")
        self.internal_curves = computed
        self.internal_curve_settings = (
            representative_log_radius,
            generations,
            resolution,
        )
        self.draw_overlays()
        return (
            f"Drew {len(self.internal_curves.curves)} "
            f"{self.internal_curves.coordinate_kind} grand-orbit levels for "
            f"the holomorphic return f^{self.internal_curves.return_period}."
        )

    def clear_internal_curves(self) -> None:
        self.internal_curves = None
        self.internal_curve_settings = None
        self.canvas.delete("internal-curve")

    def add_dynamical_rays(
        self,
        angle: Fraction,
        *,
        complete_orbit: bool,
    ) -> tuple[int, str]:
        if not critical_orbit_appears_bounded(
            self.app.julia_parameter,
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        ):
            raise ValueError(
                "The critical orbit escapes for this parameter. This first ray "
                "implementation draws only full, unbranched rays for apparently "
                "connected Julia sets."
            )

        if complete_orbit:
            orbit = forward_angle_orbit(
                angle,
                degree=self.app.degree.get(),
                antiholomorphic=self.app.antiholomorphic,
            )
            angles = orbit.angles
            if len(angles) > 128:
                raise ValueError(
                    f"This exact forward orbit contains {len(angles)} angles. "
                    "Draw one ray or choose an orbit with at most 128 angles."
                )
            orbit_description = (
                f"preperiod {orbit.preperiod}, period {orbit.period}"
            )
        else:
            angles = (angle,)
            orbit_description = "single angle"

        added = 0
        for current in angles:
            if current in self.ray_traces:
                continue
            self.ray_traces[current] = self._trace_ray(current)
            added += 1

        self._refresh_portrait_clusters()
        self.draw_overlays()
        return (
            added,
            f"Added {added} ray{'s' if added != 1 else ''}; {orbit_description}.",
        )

    def clear_dynamical_rays(self) -> None:
        self.ray_traces.clear()
        self.portrait_clusters = ()
        self.clear_sectors()
        self.canvas.delete("dynamical-ray")
        self.canvas.delete("portrait-label")
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()

    def clear_external_overlays(self) -> None:
        self.ray_traces.clear()
        self.equipotential_traces.clear()
        self.portrait_clusters = ()
        self.sector_specs.clear()
        self.sector_polygons.clear()
        self.internal_curves = None
        self.internal_curve_settings = None
        for tag in (
            "dynamical-ray",
            "equipotential",
            "portrait-label",
            "ray-sector",
            "internal-curve",
        ):
            self.canvas.delete(tag)
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()
        if self.equipotential_dialog is not None:
            self.equipotential_dialog.refresh()

    def add_next_ray_iterates(self) -> tuple[int, str]:
        """Add the f_c-images of all currently displayed external rays."""
        if not self.ray_traces:
            description = "Draw at least one dynamical ray before advancing it."
            self.app.set_global_status(description)
            return 0, description

        next_angles = next_missing_angles(
            tuple(self.ray_traces),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )
        for angle in next_angles:
            self.ray_traces[angle] = self._trace_ray(angle)
        self._refresh_portrait_clusters()
        self.draw_overlays()
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()

        if next_angles:
            description = (
                f"Added {len(next_angles)} next ray "
                f"iterate{'s' if len(next_angles) != 1 else ''} "
                f"using t ↦ {'−' if self.app.antiholomorphic else ''}"
                f"{self.app.degree.get()}t."
            )
        else:
            description = "The displayed rays already contain their next iterates."
        self.app.set_global_status(description)
        return len(next_angles), description

    def replace_with_next_ray_iterates(self) -> tuple[int, str]:
        """Replace all displayed rays by their images under f_c."""
        if not self.ray_traces:
            description = "Draw at least one dynamical ray before advancing it."
            self.app.set_global_status(description)
            return 0, description

        old_traces = self.ray_traces
        angles = image_angles(
            tuple(old_traces),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )
        self.ray_traces = {
            angle: old_traces.get(angle) or self._trace_ray(angle)
            for angle in angles
        }
        self.portrait_clusters = ()
        self.clear_sectors()
        self.draw_overlays()
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()
        description = (
            f"Replaced the displayed rays with {len(angles)} image "
            f"ray{'s' if len(angles) != 1 else ''} under t ↦ "
            f"{'−' if self.app.antiholomorphic else ''}{self.app.degree.get()}t."
        )
        self.app.set_global_status(description)
        return len(angles), description

    def add_equipotential(self, potential: float) -> str:
        if not math.isfinite(potential) or potential <= 0.0:
            raise ValueError("External potential must be a positive finite number.")
        if not critical_orbit_appears_bounded(
            self.app.julia_parameter,
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        ):
            raise ValueError(
                "A full equipotential is currently supported only when the "
                "critical orbit appears bounded."
            )
        self.equipotential_traces[potential] = trace_equipotential(
            (
                self.app.julia_parameter
                if self.effective_precision.mode == "arbitrary"
                else complex(self.app.julia_parameter)
            ),
            potential,
            samples=max(720, self.render_size),
            require_connected=False,
            precision_bits=(
                self.effective_precision.bits
                if self.effective_precision.mode == "arbitrary"
                else None
            ),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )
        self.draw_overlays()
        if self.equipotential_dialog is not None:
            self.equipotential_dialog.refresh()
        return f"Added equipotential at external potential s = {potential:.8g}."

    def clear_equipotentials(self) -> None:
        self.equipotential_traces.clear()
        self.canvas.delete("equipotential")
        if self.equipotential_dialog is not None:
            self.equipotential_dialog.refresh()

    def _refresh_portrait_clusters(self) -> None:
        if not self.portrait_clusters or not self.ray_traces:
            return
        self.portrait_clusters = cluster_ray_landings(
            tuple(self.ray_traces.values()),
            tolerance=self.landing_tolerance,
        )

    def analyze_orbit_portrait(self) -> str:
        if not self.ray_traces:
            raise ValueError("Draw at least one rational dynamical ray first.")
        self.portrait_clusters = cluster_ray_landings(
            tuple(self.ray_traces.values()),
            tolerance=self.landing_tolerance,
        )
        self.draw_overlays()

        lines = [
            "Numerical orbit portrait from the currently displayed rays",
            f"Landing clustering tolerance: {self.landing_tolerance:.3g}",
            "",
        ]
        for index, cluster in enumerate(self.portrait_clusters, start=1):
            point_period = estimate_point_period(
                cluster.point,
                self.app.julia_parameter,
                tolerance=4.0 * self.landing_tolerance,
                degree=self.app.degree.get(),
                antiholomorphic=self.app.antiholomorphic,
            )
            angle_orbits = [
                forward_angle_orbit(
                    angle,
                    degree=self.app.degree.get(),
                    antiholomorphic=self.app.antiholomorphic,
                )
                for angle in cluster.angles
            ]
            angle_periods = [
                orbit.period if orbit.preperiod == 0 else None
                for orbit in angle_orbits
            ]
            lines.append(
                f"A{index} = "
                f"{{{', '.join(str(angle) for angle in cluster.angles)}}}"
            )
            lines.append(f"  landing ≈ {format_complex(cluster.point, digits=10)}")
            lines.append(
                "  estimated point period: "
                + (str(point_period) if point_period is not None else "not resolved")
            )
            lines.append(
                "  exact ray periods: "
                + ", ".join(
                    str(period) if period is not None else "preperiodic"
                    for period in angle_periods
                )
            )

            checks: list[str] = []
            quadratic_antiholomorphic = (
                self.app.antiholomorphic and self.app.degree.get() == 2
            )
            if (
                quadratic_antiholomorphic
                and point_period is not None
                and point_period % 2 == 1
            ):
                checks.append(
                    "odd-period ray-count restriction: "
                    + ("passes" if len(cluster.angles) <= 3 else "fails numerically")
                )
                periodic = {period for period in angle_periods if period is not None}
                allowed = {point_period, 2 * point_period}
                checks.append(
                    "odd-period p/2p restriction: "
                    + ("passes" if periodic <= allowed else "fails numerically")
                )
            elif quadratic_antiholomorphic and point_period is not None:
                periodic = [period for period in angle_periods if period is not None]
                checks.append(
                    "even-period equal ray periods: "
                    + (
                        "passes"
                        if not periodic or len(set(periodic)) == 1
                        else "fails numerically"
                    )
                )
            elif point_period is not None:
                checks.append(
                    "family-specific quadratic-antiholomorphic restrictions "
                    "are not applied to this map"
                )
            for check in checks:
                lines.append(f"  {check}")
            lines.append("")
        lines.append(
            "These are numerical landing clusters, not a proof of ray landing."
        )
        return "\n".join(lines)

    def add_sector(
        self,
        first: Fraction,
        second: Fraction,
        *,
        kind: str,
    ) -> None:
        if first == second:
            raise ValueError("Choose two distinct rational angles.")
        if kind not in {"critical", "critical-value"}:
            raise ValueError("Unknown sector type.")
        if not critical_orbit_appears_bounded(
            self.app.julia_parameter,
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        ):
            raise ValueError("Full ray sectors require an apparently connected Julia set.")

        for angle in (first, second):
            if angle not in self.ray_traces:
                self.ray_traces[angle] = self._trace_ray(angle)

        if kind == "critical-value":
            mapped = image_angles(
                (first, second),
                degree=self.app.degree.get(),
                antiholomorphic=self.app.antiholomorphic,
            )
            if len(mapped) != 2:
                raise ValueError(
                    "These two rays have the same image, so they do not bound "
                    "a non-degenerate critical-value sector."
                )
            first, second = mapped
            for angle in mapped:
                if angle not in self.ray_traces:
                    self.ray_traces[angle] = self._trace_ray(angle)

        first_ray = self.ray_traces[first]
        second_ray = self.ray_traces[second]
        if (
            abs(
                first_ray.landing_approximation
                - second_ray.landing_approximation
            )
            > 4.0 * self.landing_tolerance
        ):
            raise ValueError(
                "The selected rays do not have a common numerical landing point "
                "at the current precision. Zoom closer or choose a verified ray pair."
            )

        spec = SectorSpec(kind, first, second)
        target = 0j if kind == "critical" else self.app.julia_parameter
        polygon = sector_polygon(
            self.app.julia_parameter,
            first_ray,
            second_ray,
            containing=target,
            precision_bits=(
                self.effective_precision.bits
                if self.effective_precision.mode == "arbitrary"
                else None
            ),
            degree=self.app.degree.get(),
            antiholomorphic=self.app.antiholomorphic,
        )
        if spec not in self.sector_specs:
            self.sector_specs.append(spec)
        self.sector_polygons[spec] = polygon
        self.draw_overlays()
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()

    def clear_sectors(self) -> None:
        self.sector_specs.clear()
        self.sector_polygons.clear()
        self.canvas.delete("ray-sector")
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()

    def _rebuild_sectors(self) -> None:
        rebuilt: dict[SectorSpec, tuple[complex, ...]] = {}
        valid_specs: list[SectorSpec] = []
        for spec in self.sector_specs:
            first = self.ray_traces.get(spec.first_angle)
            second = self.ray_traces.get(spec.second_angle)
            if first is None or second is None:
                continue
            target = 0j if spec.kind == "critical" else self.app.julia_parameter
            try:
                rebuilt[spec] = sector_polygon(
                    self.app.julia_parameter,
                    first,
                    second,
                    containing=target,
                    precision_bits=(
                        self.effective_precision.bits
                        if self.effective_precision.mode == "arbitrary"
                        else None
                    ),
                    degree=self.app.degree.get(),
                    antiholomorphic=self.app.antiholomorphic,
                )
            except ValueError:
                continue
            valid_specs.append(spec)
        self.sector_specs = valid_specs
        self.sector_polygons = rebuilt

    def retrace_external_overlays(self, *, redraw: bool = True) -> None:
        if self.kind != "julia":
            return
        if self.ray_traces:
            self.ray_traces = {
                angle: self._trace_ray(angle)
                for angle in tuple(self.ray_traces)
            }
        if self.equipotential_traces:
            self.equipotential_traces = {
                potential: trace_equipotential(
                    (
                        self.app.julia_parameter
                        if self.effective_precision.mode == "arbitrary"
                        else complex(self.app.julia_parameter)
                    ),
                    potential,
                    samples=max(720, self.render_size),
                    require_connected=False,
                    precision_bits=(
                        self.effective_precision.bits
                        if self.effective_precision.mode == "arbitrary"
                        else None
                    ),
                    degree=self.app.degree.get(),
                    antiholomorphic=self.app.antiholomorphic,
                )
                for potential in tuple(self.equipotential_traces)
            }
        self._refresh_portrait_clusters()
        self._rebuild_sectors()
        if self.internal_curve_settings and self.app.attracting_orbit:
            representative, generations, resolution = self.internal_curve_settings
            span = max(
                self.viewport.xmax - self.viewport.xmin,
                self.viewport.ymax - self.viewport.ymin,
            )
            if span >= mp.mpf("1e-13"):
                bounds = (
                    float(self.viewport.xmin),
                    float(self.viewport.xmax),
                    float(self.viewport.ymin),
                    float(self.viewport.ymax),
                )
                try:
                    self.internal_curves = trace_internal_grand_orbit(
                        complex(self.app.julia_parameter),
                        tuple(
                            complex(value)
                            for value in self.app.attracting_orbit
                        ),
                        bounds,
                        representative_log_radius=representative,
                        generations=generations,
                        resolution=resolution,
                        degree=self.app.degree.get(),
                        antiholomorphic=self.app.antiholomorphic,
                    )
                except ValueError:
                    self.internal_curves = None
            else:
                self.internal_curves = None
        if self.ray_dialog is not None:
            self.ray_dialog.refresh()
        if self.equipotential_dialog is not None:
            self.equipotential_dialog.refresh()
        if redraw:
            self.draw_overlays()

    def reset(self) -> None:
        self.viewport.reset()
        self.view_text.set(self.viewport.description())
        self._update_precision_text()
        self.retrace_external_overlays(redraw=False)
        self.request_render()

    def save_png(self) -> None:
        if not self.output_path.exists():
            messagebox.showinfo("Nothing to save", "Render the image first.", parent=self)
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save {self.kind} image",
            defaultextension=".png",
            filetypes=(("PNG image", "*.png"), ("All files", "*.*")),
            initialfile=f"{self.kind}.png",
        )
        if not destination:
            return
        with Image.open(self.output_path) as source:
            image = source.convert("RGB")
        self._paint_overlays_for_export(image)
        image.save(destination, "PNG")
        self.app.set_global_status(
            f"Saved {Path(destination).name} at {image.width}×{image.height}"
        )

    def _paint_overlays_for_export(self, image: Image.Image) -> None:
        size = image.width
        scale = size / CANVAS_SIZE
        if self.kind == "parameter":
            draw = ImageDraw.Draw(image)
            for index, (angle, trace) in enumerate(
                self.parameter_ray_traces.items()
            ):
                color = RAY_COLORS[index % len(RAY_COLORS)]
                points = [
                    self.viewport.pixel_at(value, size)
                    for value in trace.points
                ]
                draw.line(
                    points,
                    fill=color,
                    width=max(2, round(2 * scale)),
                )
                x, y = points[-1]
                draw.text(
                    (x + 7 * scale, y - 14 * scale),
                    f"R_{angle}",
                    fill=color,
                    stroke_width=max(1, round(scale)),
                    stroke_fill="#ffffff",
                )
            if self.app.path_start is not None or self.app.path_end is not None:
                start = (
                    self.viewport.pixel_at(self.app.path_start, size)
                    if self.app.path_start is not None
                    else None
                )
                end = (
                    self.viewport.pixel_at(self.app.path_end, size)
                    if self.app.path_end is not None
                    else None
                )
                if start is not None and end is not None:
                    draw.line(
                        (start, end),
                        fill="#f1f5f2",
                        width=max(1, round(2 * scale)),
                    )
                    current_parameter = ParameterPath(
                        self.app.path_start,
                        self.app.path_end,
                        self.app.animation_steps,
                    ).parameter_at(self.app.animation_index)
                    current_x, current_y = self.viewport.pixel_at(
                        current_parameter,
                        size,
                    )
                    current_radius = 4 * scale
                    draw.ellipse(
                        (
                            current_x - current_radius,
                            current_y - current_radius,
                            current_x + current_radius,
                            current_y + current_radius,
                        ),
                        fill="#f5e27a",
                        outline="#11171b",
                        width=max(1, round(scale)),
                    )
                for label, point, color in (
                    ("A", start, "#65dfad"),
                    (
                        "B",
                        end,
                        "#ff9b7c",
                    ),
                ):
                    if point is None:
                        continue
                    x, y = point
                    radius = 6 * scale
                    draw.ellipse(
                        (x - radius, y - radius, x + radius, y + radius),
                        fill="#11171b",
                        outline=color,
                        width=max(1, round(2 * scale)),
                    )
                    draw.text(
                        (x + 8 * scale, y - 12 * scale),
                        label,
                        fill=color,
                        stroke_width=max(1, round(scale)),
                        stroke_fill="#ffffff",
                    )
            return
        if self.kind != "julia":
            return

        if self.sector_specs:
            base = image.convert("RGBA")
            shading = Image.new("RGBA", image.size, (0, 0, 0, 0))
            shade_draw = ImageDraw.Draw(shading)
            for spec in self.sector_specs:
                polygon = self.sector_polygons.get(spec)
                if not polygon:
                    continue
                points = [self.viewport.pixel_at(value, size) for value in polygon]
                fill = (
                    (108, 79, 134, 68)
                    if spec.kind == "critical"
                    else (138, 97, 59, 68)
                )
                shade_draw.polygon(points, fill=fill)
            image.paste(Image.alpha_composite(base, shading).convert("RGB"))

        draw = ImageDraw.Draw(image)

        if self.internal_curves is not None:
            for curve in self.internal_curves.curves:
                color = "#f4f0e8" if curve.representative else "#b7d7cb"
                width = max(
                    1,
                    round((3 if curve.representative else 1) * scale),
                )
                for polyline in curve.polylines:
                    points = [
                        self.viewport.pixel_at(value, size)
                        for value in polyline
                    ]
                    draw.line(points, fill=color, width=width)

        for index, trace in enumerate(self.equipotential_traces.values()):
            color = ("#e8edf0", "#a9c9d2", "#d4b8df")[index % 3]
            points = [self.viewport.pixel_at(value, size) for value in trace.points]
            draw.line(points, fill=color, width=max(1, round(scale)))

        for spec in self.sector_specs:
            target = 0j if spec.kind == "critical" else self.app.julia_parameter
            x, y = self.viewport.pixel_at(target, size)
            label = (
                "critical sector"
                if spec.kind == "critical"
                else "critical-value sector"
            )
            draw.text(
                (x + 8 * scale, y - 8 * scale),
                label,
                fill="#33213f" if spec.kind == "critical" else "#4a2c16",
                stroke_width=max(1, round(scale)),
                stroke_fill="#ffffff",
            )

        if self.show_attracting_orbit.get() and self.app.attracting_orbit:
            for value in self.app.attracting_orbit:
                x, y = self.viewport.pixel_at(value, size)
                draw.ellipse(
                    (x - 7 * scale, y - 7 * scale, x + 7 * scale, y + 7 * scale),
                    fill="#11171b",
                )
                draw.ellipse(
                    (x - 4 * scale, y - 4 * scale, x + 4 * scale, y + 4 * scale),
                    fill="#ffc867",
                    outline="#ffe0a3",
                    width=max(1, round(scale)),
                )

        for index, (angle, ray) in enumerate(self.ray_traces.items()):
            color = RAY_COLORS[index % len(RAY_COLORS)]
            points = [self.viewport.pixel_at(value, size) for value in ray.points]
            draw.line(points, fill=color, width=max(2, round(2 * scale)))
            x, y = points[-1]
            radius = 4 * scale
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill="#11171b",
                outline=color,
                width=max(1, round(2 * scale)),
            )
            draw.text(
                (x + 7 * scale, y - 14 * scale),
                str(angle),
                fill=color,
                stroke_width=max(1, round(scale)),
                stroke_fill="#ffffff",
            )

        for index, cluster in enumerate(self.portrait_clusters, start=1):
            x, y = self.viewport.pixel_at(cluster.point, size)
            angle_text = ", ".join(str(angle) for angle in cluster.angles)
            draw.text(
                (x + 8 * scale, y + 13 * scale),
                f"A{index} = {{{angle_text}}}",
                fill="#152027",
                stroke_width=max(1, round(scale)),
                stroke_fill="#ffffff",
            )

        if self.app.dynamical_point is not None:
            x, y = self.viewport.pixel_at(self.app.dynamical_point, size)
            draw.ellipse(
                (x - 8 * scale, y - 8 * scale, x + 8 * scale, y + 8 * scale),
                fill="#10241c",
            )
            draw.ellipse(
                (x - 5 * scale, y - 5 * scale, x + 5 * scale, y + 5 * scale),
                fill="#61d69a",
                outline="#b2f5d0",
                width=max(1, round(2 * scale)),
            )

    def _start_selection(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        self.drag_start = (event.x, event.y)
        self._delete_selection()

    def _move_selection(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        self._delete_selection()
        x0, y0 = self.drag_start
        x1, y1 = self._selection_endpoint(event.x, event.y)
        self.selection_id = self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            outline="#d9e1dd",
            width=2,
            dash=(5, 3),
        )

    def _selection_endpoint(self, x: int, y: int) -> tuple[int, int]:
        x = max(0, min(CANVAS_SIZE, x))
        y = max(0, min(CANVAS_SIZE, y))
        if self.drag_start is None or not self.square_zoom.get():
            return x, y
        x0, y0 = self.drag_start
        dx = x - x0
        dy = y - y0
        if dx == 0 or dy == 0:
            return x, y
        side = min(
            max(abs(dx), abs(dy)),
            CANVAS_SIZE - x0 if dx > 0 else x0,
            CANVAS_SIZE - y0 if dy > 0 else y0,
        )
        return (
            x0 + (side if dx > 0 else -side),
            y0 + (side if dy > 0 else -side),
        )

    def _finish_selection(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        start = self.drag_start
        end = self._selection_endpoint(event.x, event.y)
        self.drag_start = None
        self._delete_selection()

        if abs(start[0] - end[0]) >= 6 and abs(start[1] - end[1]) >= 6:
            proposed = Viewport(
                self.viewport.xmin,
                self.viewport.xmax,
                self.viewport.ymin,
                self.viewport.ymax,
            )
            proposed.zoom_to_pixels(start, end, CANVAS_SIZE)
            decision = precision_decision(
                self.precision.get(),
                proposed,
                self.render_size,
            )
            if not self._confirm_arbitrary_precision(decision):
                self.status.set("Zoom cancelled; precision unchanged")
                return
            self.viewport = proposed
            self.view_text.set(self.viewport.description())
            self._update_precision_text()
            self.retrace_external_overlays(redraw=False)
            self.request_render()
        elif self.kind == "parameter":
            self.app.select_parameter_point(
                self.viewport.complex_at(end[0], end[1], CANVAS_SIZE)
            )
        else:
            self.app.set_dynamical_point(
                self.viewport.complex_at(end[0], end[1], CANVAS_SIZE)
            )

    def _cancel_selection(self, _event: tk.Event | None = None) -> None:
        self.drag_start = None
        self._delete_selection()
        self.status.set("Selection cancelled")

    def _delete_selection(self) -> None:
        if self.selection_id is not None:
            self.canvas.delete(self.selection_id)
            self.selection_id = None


class BifurcationLoomApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bifurcation Loom")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        configure_display_layout(screen_width, screen_height)
        target_width = min(1420, max(1040, screen_width - 80))
        target_height = min(990, max(700, screen_height - 80))
        min_width = min(1180, target_width)
        min_height = min(720, target_height)
        self.minsize(min_width, min_height)
        self.geometry(f"{target_width}x{target_height}")
        self.configure(background="#151d22")
        self.dynamics = tk.StringVar(value="Antiholomorphic")
        self.degree = tk.IntVar(value=2)
        self.family_text = tk.StringVar()
        self.julia_parameter = mp.mpc(0)
        self.attracting_orbit = attracting_critical_orbit(
            self.julia_parameter,
            degree=self.degree.get(),
            antiholomorphic=self.antiholomorphic,
        )
        self.dynamical_point: mp.mpc | None = None
        self.path_start: mp.mpc | None = None
        self.path_end: mp.mpc | None = None
        self.path_pick_target: str | None = None
        self.animation_steps = 80
        self.animation_fps = 10
        self.animation_index = 0
        self.animation_playing = False
        self.animation_after_id: str | None = None
        self.animation_dialog: ParameterAnimationDialog | None = None
        self.results: queue.Queue[
            tuple[FractalPane, subprocess.CompletedProcess[str]]
        ] = queue.Queue()
        self.global_status = tk.StringVar(value="Ready")
        self.parameter_text = tk.StringVar()
        self.dynamical_point_text = tk.StringVar(value="No dynamical point selected.")

        self._configure_style()
        self._build_layout()
        self._bind_shortcuts()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<space>", self.iterate_dynamical_point)
        self.after(50, self._poll_results)
        self.after(100, self.render_all)

    @property
    def antiholomorphic(self) -> bool:
        return self.dynamics.get() == "Antiholomorphic"

    @property
    def dynamics_code(self) -> str:
        return "antiholomorphic" if self.antiholomorphic else "holomorphic"

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background="#151d22", foreground="#dce4e2")
        style.configure("TFrame", background="#151d22")
        style.configure("TLabel", background="#151d22", foreground="#dce4e2")
        style.configure(
            "Title.TLabel",
            font=("TkDefaultFont", 14, "bold"),
            foreground="#edf2ef",
        )
        style.configure("Status.TLabel", foreground="#9db2b3")
        style.configure("Meta.TLabel", foreground="#93a5aa", font=("TkFixedFont", 9))
        style.configure("TLabelframe", background="#151d22", foreground="#aebfbe")
        style.configure("TLabelframe.Label", background="#151d22", foreground="#aebfbe")
        style.configure("TButton", padding=(9, 5))
        style.configure("TRadiobutton", background="#151d22", foreground="#dce4e2")
        style.configure("TCheckbutton", background="#151d22", foreground="#dce4e2")
        style.configure(
            "TCombobox",
            fieldbackground="#26343a",
            background="#34464e",
            foreground="#eef4f1",
            arrowcolor="#dce4e2",
            selectbackground="#26343a",
            selectforeground="#eef4f1",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#26343a")],
            foreground=[("readonly", "#eef4f1")],
            selectbackground=[("readonly", "#26343a")],
            selectforeground=[("readonly", "#eef4f1")],
        )
        self.option_add("*TCombobox*Listbox.background", "#26343a")
        self.option_add("*TCombobox*Listbox.foreground", "#eef4f1")
        self.option_add("*TCombobox*Listbox.selectBackground", "#4d6670")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _build_layout(self) -> None:
        topbar = ttk.Frame(self, padding=(14, 10))
        topbar.pack(fill="x")
        ttk.Label(
            topbar,
            textvariable=self.family_text,
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(topbar, text="Map").pack(side="left", padx=(22, 5))
        dynamics_box = ttk.Combobox(
            topbar,
            textvariable=self.dynamics,
            values=("Antiholomorphic", "Holomorphic"),
            state="readonly",
            width=17,
        )
        dynamics_box.pack(side="left")
        dynamics_box.bind("<<ComboboxSelected>>", self._family_changed)
        ttk.Label(topbar, text="Degree d").pack(side="left", padx=(12, 5))
        degree_box = ttk.Combobox(
            topbar,
            textvariable=self.degree,
            values=DEGREE_OPTIONS,
            state="readonly",
            width=3,
        )
        degree_box.pack(side="left")
        degree_box.bind("<<ComboboxSelected>>", self._family_changed)
        ttk.Label(topbar, textvariable=self.parameter_text).pack(side="left", padx=18)
        ttk.Button(topbar, text="Set c…", command=self.prompt_julia_parameter).pack(
            side="left"
        )
        ttk.Button(topbar, text="Render both", command=self.render_all).pack(side="right")
        ttk.Label(topbar, textvariable=self.global_status, style="Status.TLabel").pack(
            side="right", padx=14
        )

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.parameter_plane = FractalPane(
            panes,
            self,
            title="Parameter plane · connectivity locus",
            kind="parameter",
            modes=PARAMETER_MODES,
            initial_mode="Component periods",
        )
        self.julia = FractalPane(
            panes,
            self,
            title="Dynamical plane · Julia set",
            kind="julia",
            modes=JULIA_MODES,
            initial_mode="Rainbow escape",
        )
        panes.add(self.parameter_plane, weight=1)
        panes.add(self.julia, weight=1)

        footer = ttk.Label(
            self,
            text=(
                "Click the Julia plane to select z; Space applies f_c once  •  "
                "F5 plays/pauses the parameter path; Left/Right steps frames  •  "
                "Ctrl+R / Alt+R reset parameter / dynamical zoom  •  "
                "Alt+Right replaces rays; Alt+Shift+Right adds their images"
            ),
            anchor="center",
            padding=(10, 7),
            style="Status.TLabel",
        )
        footer.pack(fill="x")
        self._update_family_label()
        self._update_parameter_label()

    def _bind_shortcuts(self) -> None:
        parameter_modes = {
            "b": "Grayscale",
            "c": "Muted escape",
            "p": "Component periods",
            "n": "Newton multiplier",
            "l": "Lyapunov multiplier",
        }
        dynamical_modes = {
            "b": "Grayscale",
            "c": "Rainbow escape",
        }
        for key, label in parameter_modes.items():
            self.bind_all(
                f"<Control-KeyPress-{key}>",
                lambda _event, selected=label: self._shortcut_mode(
                    self.parameter_plane, selected
                ),
            )
        for key, label in dynamical_modes.items():
            self.bind_all(
                f"<Alt-KeyPress-{key}>",
                lambda _event, selected=label: self._shortcut_mode(
                    self.julia, selected
                ),
            )
        for index, iterations in enumerate(ITERATION_OPTIONS, start=1):
            self.bind_all(
                f"<Control-KeyPress-{index}>",
                lambda _event, value=iterations: self._shortcut_iterations(
                    self.parameter_plane, value
                ),
            )
            self.bind_all(
                f"<Alt-KeyPress-{index}>",
                lambda _event, value=iterations: self._shortcut_iterations(
                    self.julia, value
                ),
            )
        self.bind_all(
            "<Control-KeyPress-r>",
            lambda _event: self._shortcut_reset(self.parameter_plane),
        )
        self.bind_all(
            "<Alt-KeyPress-r>",
            lambda _event: self._shortcut_reset(self.julia),
        )
        self.bind_all(
            "<Alt-KeyPress-Right>",
            lambda _event: self._shortcut_replace_rays(),
        )
        self.bind_all(
            "<Alt-Shift-KeyPress-Right>",
            lambda _event: self._shortcut_add_rays(),
        )
        self.bind_all("<F5>", self._animation_toggle_key)
        self.bind_all(
            "<KeyPress-Left>",
            lambda event: self._animation_step_key(event, -1),
        )
        self.bind_all(
            "<KeyPress-Right>",
            lambda event: self._animation_step_key(event, 1),
        )

    @staticmethod
    def _shortcut_mode(pane: FractalPane, label: str) -> str:
        pane.mode.set(label)
        pane.request_render()
        return "break"

    @staticmethod
    def _shortcut_iterations(pane: FractalPane, iterations: int) -> str:
        pane.iterations.set(iterations)
        pane.request_render()
        return "break"

    @staticmethod
    def _shortcut_reset(pane: FractalPane) -> str:
        pane.reset()
        return "break"

    def _shortcut_replace_rays(self) -> str:
        self.julia.replace_with_next_ray_iterates()
        return "break"

    def _shortcut_add_rays(self) -> str:
        self.julia.add_next_ray_iterates()
        return "break"

    @staticmethod
    def _text_input_has_focus(event: tk.Event) -> bool:
        return event.widget.winfo_class() in {
            "Entry",
            "TEntry",
            "Text",
            "TCombobox",
            "Spinbox",
            "TSpinbox",
            "Scale",
            "TScale",
        }

    def _animation_toggle_key(self, event: tk.Event) -> str | None:
        if self._text_input_has_focus(event):
            return None
        self.toggle_animation()
        return "break"

    def _animation_step_key(
        self,
        event: tk.Event,
        amount: int,
    ) -> str | None:
        if self._text_input_has_focus(event) or event.state & 0x0008:
            return None
        if self.path_start is None or self.path_end is None:
            return None
        self.step_animation(amount)
        return "break"

    def _poll_results(self) -> None:
        while True:
            try:
                pane, result = self.results.get_nowait()
            except queue.Empty:
                break
            pane.finish_render(result)
        self.after(50, self._poll_results)

    def _family_changed(self, _event: tk.Event | None = None) -> None:
        self.pause_animation()
        self._update_family_label()
        self.attracting_orbit = attracting_critical_orbit(
            self.julia_parameter,
            degree=self.degree.get(),
            antiholomorphic=self.antiholomorphic,
        )
        self.clear_dynamical_point()
        self.parameter_plane.clear_parameter_rays()
        self.julia.clear_external_overlays()
        self.parameter_plane.viewport.reset()
        self.julia.viewport.reset()
        self.parameter_plane.view_text.set(
            self.parameter_plane.viewport.description()
        )
        self.julia.view_text.set(self.julia.viewport.description())
        self.parameter_plane.request_render()
        self.julia.request_render()
        self.parameter_plane.draw_overlays()

    def _update_family_label(self) -> None:
        degree = self.degree.get()
        formula = (
            f"conj(z)^{degree} + c"
            if self.antiholomorphic
            else f"z^{degree} + c"
        )
        self.family_text.set(f"Bifurcation Loom · f_c(z) = {formula}")
        if hasattr(self, "parameter_plane"):
            adjective = (
                "antiholomorphic"
                if self.antiholomorphic
                else "holomorphic"
            )
            self.parameter_plane.title_label.configure(
                text=f"Parameter plane · {adjective} degree {degree}"
            )

    def show_animation_dialog(self) -> None:
        if (
            self.animation_dialog is not None
            and self.animation_dialog.winfo_exists()
        ):
            self.animation_dialog.lift()
            self.animation_dialog.focus_force()
            return
        self.animation_dialog = ParameterAnimationDialog(self)

    def begin_path_pick(self, endpoint: str) -> None:
        if endpoint not in {"A", "B"}:
            raise ValueError("A parameter-path endpoint must be A or B.")
        self.path_pick_target = endpoint
        self.parameter_plane.status.set(
            f"Click the parameter plane to choose point {endpoint}"
        )
        self.set_global_status(f"Choose path endpoint {endpoint} on the parameter plane.")
        self.parameter_plane.canvas.focus_set()

    def select_parameter_point(self, value: complex) -> None:
        endpoint = self.path_pick_target
        self.path_pick_target = None
        self.set_julia_parameter(value)
        if endpoint is not None:
            self.set_path_endpoint(endpoint, value)

    def set_path_endpoint(self, endpoint: str, value: complex) -> None:
        value = mp.mpc(value)
        if endpoint == "A":
            self.path_start = value
        elif endpoint == "B":
            self.path_end = value
        else:
            raise ValueError("A parameter-path endpoint must be A or B.")
        self.pause_animation()
        self.animation_index = 0
        self.parameter_plane.draw_overlays()
        if self.animation_dialog is not None:
            self.animation_dialog.refresh()
        self.set_global_status(
            f"Path endpoint {endpoint} = {format_complex(value, digits=9)}"
        )

    def prompt_path_endpoint(self, endpoint: str) -> None:
        initial = (
            self.path_start
            if endpoint == "A"
            else self.path_end
        ) or self.julia_parameter
        dialog = ComplexInputDialog(
            self,
            title=f"Set path endpoint {endpoint}",
            symbol=endpoint,
            initial=initial,
        )
        if dialog.result is not None:
            self.set_path_endpoint(endpoint, dialog.result)

    def _parameter_path(self) -> ParameterPath:
        if self.path_start is None or self.path_end is None:
            raise ValueError("Choose both parameter-path endpoints A and B first.")
        return ParameterPath(
            self.path_start,
            self.path_end,
            self.animation_steps,
        )

    def configure_animation(self, *, steps: int, fps: int) -> None:
        if fps < 1 or fps > 30:
            raise ValueError("Playback fps must be between 1 and 30.")
        if self.path_start is None or self.path_end is None:
            raise ValueError("Choose both parameter-path endpoints A and B first.")
        ParameterPath(
            self.path_start,
            self.path_end,
            int(steps),
        )
        previous_steps = self.animation_steps
        self.animation_steps = int(steps)
        self.animation_fps = int(fps)
        self._parameter_path()
        if previous_steps != self.animation_steps:
            self.animation_index = min(
                self.animation_index,
                self.animation_steps - 1,
            )
        self.parameter_plane.draw_overlays()
        if self.animation_dialog is not None:
            self.animation_dialog.refresh()

    def toggle_animation(self) -> None:
        if self.animation_playing:
            self.pause_animation()
            return
        try:
            path = self._parameter_path()
        except ValueError as exc:
            messagebox.showinfo("Parameter path", str(exc), parent=self)
            return
        if self.animation_index >= path.steps - 1:
            self.animation_index = 0
        self.animation_playing = True
        self._show_animation_frame(self.animation_index)
        self._schedule_animation_tick()
        if self.animation_dialog is not None:
            self.animation_dialog.refresh()

    def pause_animation(self) -> None:
        self.animation_playing = False
        if self.animation_after_id is not None:
            self.after_cancel(self.animation_after_id)
            self.animation_after_id = None
        if self.animation_dialog is not None:
            self.animation_dialog.refresh()

    def _schedule_animation_tick(self, delay: int | None = None) -> None:
        if not self.animation_playing:
            return
        milliseconds = (
            delay
            if delay is not None
            else max(1, round(1000 / self.animation_fps))
        )
        self.animation_after_id = self.after(
            milliseconds,
            self._animation_tick,
        )

    def _animation_tick(self) -> None:
        self.animation_after_id = None
        if not self.animation_playing:
            return
        if self.julia.busy or self.julia.render_again:
            self._schedule_animation_tick(25)
            return
        if self.animation_index >= self.animation_steps - 1:
            self.pause_animation()
            return
        self._show_animation_frame(self.animation_index + 1)
        self._schedule_animation_tick()

    def _show_animation_frame(self, index: int) -> None:
        path = self._parameter_path()
        self.animation_index = max(0, min(path.steps - 1, index))
        self.set_julia_parameter(
            path.parameter_at(self.animation_index),
            reset_view=False,
            from_animation=True,
        )
        self.parameter_plane.draw_overlays()
        if self.animation_dialog is not None:
            self.animation_dialog.refresh()

    def seek_animation(self, index: int) -> None:
        try:
            self._parameter_path()
        except ValueError as exc:
            messagebox.showinfo("Parameter path", str(exc), parent=self)
            return
        self.pause_animation()
        self._show_animation_frame(index)

    def step_animation(self, amount: int) -> None:
        self.seek_animation(self.animation_index + amount)

    def prompt_julia_parameter(self) -> None:
        dialog = ComplexInputDialog(
            self,
            title="Set Julia parameter",
            symbol="c",
            initial=self.julia_parameter,
        )
        if dialog.result is not None:
            self.set_julia_parameter(dialog.result)

    def prompt_dynamical_point(self) -> None:
        dialog = ComplexInputDialog(
            self,
            title="Set dynamical point",
            symbol="z",
            initial=self.dynamical_point or 0j,
        )
        if dialog.result is not None:
            self.set_dynamical_point(dialog.result)
            self.julia.canvas.focus_set()

    def set_julia_parameter(
        self,
        value: complex,
        *,
        reset_view: bool = True,
        from_animation: bool = False,
    ) -> None:
        if not from_animation:
            self.pause_animation()
        self.julia_parameter = mp.mpc(value)
        self.attracting_orbit = attracting_critical_orbit(
            value,
            degree=self.degree.get(),
            antiholomorphic=self.antiholomorphic,
        )
        if reset_view:
            self.julia.viewport.reset()
            self.julia.view_text.set(self.julia.viewport.description())
        self.julia.clear_external_overlays()
        self.clear_dynamical_point()
        self._update_parameter_label()
        decision = self.julia.effective_precision
        if not self.julia._confirm_arbitrary_precision(decision):
            self.julia.precision.set("Double (64-bit)")
        self.julia._update_precision_text()
        self.julia.request_render()

    def set_dynamical_point(self, value: complex) -> None:
        self.dynamical_point = mp.mpc(value)
        self.dynamical_point_text.set(
            f"Selected z = {format_complex(value, digits=10)}  ·  Space applies f_c"
        )
        self.julia.draw_overlays()
        self.set_global_status("Dynamical point selected; press Space to iterate.")

    def clear_dynamical_point(self) -> None:
        self.dynamical_point = None
        self.dynamical_point_text.set("No dynamical point selected.")
        if hasattr(self, "julia"):
            self.julia.canvas.delete("selected-point")

    def iterate_dynamical_point(self, event: tk.Event | None = None) -> str | None:
        if event is not None and event.widget is not self.julia.canvas:
            return None
        if self.dynamical_point is None:
            self.set_global_status("Select a dynamical point before pressing Space.")
            return "break"
        self.dynamical_point = unicritical_map(
            self.dynamical_point,
            self.julia_parameter,
            degree=self.degree.get(),
            antiholomorphic=self.antiholomorphic,
        )
        self.dynamical_point_text.set(
            f"Iterated z = {format_complex(self.dynamical_point, digits=10)}  "
            "·  Space iterates again"
        )
        self.julia.draw_overlays()
        return "break"

    def _update_parameter_label(self) -> None:
        self.parameter_text.set(
            f"Julia parameter  c = {format_complex(self.julia_parameter, digits=7)}"
        )

    def render_all(self) -> None:
        self.parameter_plane.request_render()
        self.julia.request_render()

    def set_global_status(self, text: str) -> None:
        self.global_status.set(text)


def main() -> None:
    IMAGE_DIR.mkdir(exist_ok=True)
    try:
        ensure_renderer()
    except (OSError, RuntimeError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Build failed", str(exc), parent=root)
        root.destroy()
        raise SystemExit(1) from exc
    BifurcationLoomApp().mainloop()


if __name__ == "__main__":
    main()
