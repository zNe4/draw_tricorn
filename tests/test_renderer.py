from __future__ import annotations

import cmath
from fractions import Fraction
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

import mpmath as mp
from PIL import Image

from math_backend.arbitrary_renderer import ArbitraryRenderOptions, render_arbitrary
from app import FractalPane, Viewport
from math_backend.dynamics import (
    anti_quadratic,
    attracting_critical_orbit,
    unicritical_map,
)
from math_backend.internal_curves import trace_internal_grand_orbit
from math_backend.parameter_rays import (
    critical_value_orbit_with_derivatives,
    trace_parameter_ray,
)
from math_backend.parameter_path import ParameterPath
from math_backend.precision import precision_decision
from math_backend.render import NativeRenderOptions, render_native
from math_backend.rays import (
    DisconnectedJuliaError,
    adaptive_minimum_potential,
    angle_map,
    cluster_ray_landings,
    estimate_point_period,
    forward_angle_orbit,
    image_angles,
    next_missing_angles,
    parse_rational_angle,
    ray_point,
    RayTrace,
    sector_polygon,
    trace_equipotential,
    trace_external_ray,
)


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "build" / "fractal-renderer"


class RendererSmokeTests(unittest.TestCase):
    def render(self, kind: str, mode: str) -> Image.Image:
        temporary = tempfile.NamedTemporaryFile(suffix=".ppm", delete=False)
        output = Path(temporary.name)
        temporary.close()
        self.addCleanup(output.unlink, missing_ok=True)
        command = [
            str(RENDERER),
            "--kind",
            kind,
            "--mode",
            mode,
            "--width",
            "96",
            "--height",
            "96",
            "--iterations",
            "96",
            "--output",
            str(output),
        ]
        if kind == "julia":
            command.extend(["--cx", "-0.2", "--cy", "0.65"])
        subprocess.run(command, cwd=ROOT, check=True)
        with Image.open(output) as image:
            return image.copy()

    def test_all_supported_modes_render_rgb_images(self) -> None:
        combinations = [
            ("tricorn", "escape"),
            ("tricorn", "grayscale"),
            ("tricorn", "newton"),
            ("tricorn", "lyapunov"),
            ("tricorn", "period"),
            ("julia", "escape"),
            ("julia", "grayscale"),
        ]
        for kind, mode in combinations:
            with self.subTest(kind=kind, mode=mode):
                image = self.render(kind, mode)
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (96, 96))
                self.assertGreater(len(image.getcolors(maxcolors=96 * 96)), 4)

    def test_boundary_outline_changes_the_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "with.ppm"
            second = Path(directory) / "without.ppm"
            base = [
                str(RENDERER),
                "--kind",
                "tricorn",
                "--mode",
                "escape",
                "--width",
                "96",
                "--height",
                "96",
                "--iterations",
                "96",
            ]
            subprocess.run(base + ["--boundary", "1", "--output", str(first)], check=True)
            subprocess.run(base + ["--boundary", "0", "--output", str(second)], check=True)
            self.assertNotEqual(first.read_bytes(), second.read_bytes())

    def test_float_and_double_precision_kernels_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for precision in ("float", "double"):
                output = Path(directory) / f"{precision}.ppm"
                subprocess.run(
                    [
                        str(RENDERER),
                        "--kind",
                        "julia",
                        "--mode",
                        "escape",
                        "--precision",
                        precision,
                        "--cx",
                        "-1",
                        "--cy",
                        "0",
                        "--width",
                        "64",
                        "--height",
                        "64",
                        "--iterations",
                        "64",
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
                with Image.open(output) as image:
                    self.assertEqual(image.size, (64, 64))

    def test_holomorphic_and_antiholomorphic_degrees_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for dynamics in ("holomorphic", "antiholomorphic"):
                for degree in (2, 3, 5):
                    for kind in ("parameter", "julia"):
                        output = (
                            Path(directory)
                            / f"{dynamics}-{degree}-{kind}.ppm"
                        )
                        subprocess.run(
                            [
                                str(RENDERER),
                                "--kind",
                                kind,
                                "--dynamics",
                                dynamics,
                                "--degree",
                                str(degree),
                                "--mode",
                                "escape",
                                "--cx",
                                "-0.2",
                                "--cy",
                                "0.6",
                                "--iterations",
                                "96",
                                "--width",
                                "72",
                                "--height",
                                "72",
                                "--output",
                                str(output),
                            ],
                            check=True,
                        )
                        with Image.open(output) as image:
                            self.assertEqual(image.size, (72, 72))
                            self.assertGreater(
                                len(image.getcolors(maxcolors=72 * 72)),
                                4,
                            )

    def test_component_period_mode_distinguishes_known_centers(self) -> None:
        centers = {
            1: 0.0,
            2: -1.0,
            3: -1.7548776662467138,
        }
        colors: dict[int, tuple[int, int, int]] = {}
        with tempfile.TemporaryDirectory() as directory:
            for period, center in centers.items():
                output = Path(directory) / f"period-{period}.ppm"
                radius = 0.02 if period < 3 else 0.006
                subprocess.run(
                    [
                        str(RENDERER),
                        "--kind",
                        "tricorn",
                        "--mode",
                        "period",
                        "--xmin",
                        str(center - radius),
                        "--xmax",
                        str(center + radius),
                        "--ymin",
                        str(-radius),
                        "--ymax",
                        str(radius),
                        "--iterations",
                        "384",
                        "--max-period",
                        "8",
                        "--width",
                        "64",
                        "--height",
                        "64",
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
                with Image.open(output) as image:
                    colors[period] = image.getpixel((32, 32))
        self.assertEqual(len(set(colors.values())), 3)
        self.assertGreater(colors[1][1], colors[1][0])
        self.assertGreater(colors[2][0], colors[2][2])
        self.assertGreater(colors[3][2], colors[3][0])

    def test_component_period_limit_leaves_higher_period_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            colors = []
            for limit in (2, 3):
                output = Path(directory) / f"limit-{limit}.ppm"
                subprocess.run(
                    [
                        str(RENDERER),
                        "--kind",
                        "tricorn",
                        "--mode",
                        "period",
                        "--xmin",
                        "-1.7608776662467138",
                        "--xmax",
                        "-1.7488776662467138",
                        "--ymin",
                        "-0.006",
                        "--ymax",
                        "0.006",
                        "--iterations",
                        "384",
                        "--max-period",
                        str(limit),
                        "--width",
                        "64",
                        "--height",
                        "64",
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
                with Image.open(output) as image:
                    colors.append(image.getpixel((32, 32)))
            self.assertEqual(colors[0], (46, 54, 57))
            self.assertNotEqual(colors[0], colors[1])




class NativeLibraryTests(unittest.TestCase):
    def test_in_process_renderer_matches_command_line_core(self) -> None:
        options = NativeRenderOptions(
            kind="julia",
            dynamics="antiholomorphic",
            mode="escape",
            degree=3,
            width=72,
            height=72,
            iterations=96,
            max_period=12,
            draw_boundary=False,
            precision="double",
            xmin=-2.0,
            xmax=2.0,
            ymin=-2.0,
            ymax=2.0,
            parameter_real=-0.2,
            parameter_imag=0.55,
        )
        native = render_native(options)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli.ppm"
            subprocess.run(
                [
                    str(RENDERER),
                    "--kind", "julia",
                    "--dynamics", "antiholomorphic",
                    "--degree", "3",
                    "--mode", "escape",
                    "--cx", "-0.2",
                    "--cy", "0.55",
                    "--iterations", "96",
                    "--max-period", "12",
                    "--width", "72",
                    "--height", "72",
                    "--xmin", "-2",
                    "--xmax", "2",
                    "--ymin", "-2",
                    "--ymax", "2",
                    "--output", str(output),
                ],
                check=True,
            )
            with Image.open(output) as image:
                cli = image.convert("RGB")
        self.assertEqual(native.tobytes(), cli.tobytes())

class ViewportTests(unittest.TestCase):
    def test_screen_coordinates_use_standard_complex_orientation(self) -> None:
        viewport = Viewport()
        self.assertEqual(viewport.complex_at(0, 0, 100), complex(-2, 2))
        self.assertEqual(viewport.complex_at(100, 100, 100), complex(2, -2))

    def test_zoom_normalizes_drag_direction(self) -> None:
        viewport = Viewport()
        viewport.zoom_to_pixels((75, 75), (25, 25), 100)
        self.assertEqual(
            (viewport.xmin, viewport.xmax, viewport.ymin, viewport.ymax),
            (-1.0, 1.0, -1.0, 1.0),
        )


class ParameterPathTests(unittest.TestCase):
    def test_linear_path_includes_both_endpoints(self) -> None:
        path = ParameterPath(-1 + 0.5j, 1 - 0.5j, 5)
        self.assertEqual(path.parameter_at(0), -1 + 0.5j)
        self.assertEqual(path.parameter_at(4), 1 - 0.5j)
        self.assertEqual(path.parameter_at(2), 0j)

    def test_parameter_path_validates_frame_count(self) -> None:
        with self.assertRaises(ValueError):
            ParameterPath(0j, 1j, 1)

    def test_parameter_path_preserves_arbitrary_precision(self) -> None:
        with mp.workdps(80):
            start = mp.mpc("1.0000000000000000000000000000000000000001")
            end = mp.mpc("1.0000000000000000000000000000000000000009")
            middle = ParameterPath(start, end, 3).parameter_at(1)
            expected = (start + end) / 2
            self.assertLess(abs(middle - expected), mp.mpf("1e-78"))
            self.assertGreater(
                abs(middle - mp.mpc(complex(start))),
                mp.mpf("1e-41"),
            )


class OverlayLifecycleTests(unittest.TestCase):
    def test_julia_overlays_wait_until_base_render_is_ready(self) -> None:
        pane = object.__new__(FractalPane)
        pane.kind = "julia"
        pane.busy = True
        calls: list[str] = []
        method_names = (
            "_draw_sectors",
            "_draw_internal_curves",
            "_draw_equipotentials",
            "_draw_dynamical_rays",
            "_draw_portrait_labels",
            "_draw_attracting_orbit",
            "_draw_selected_point",
        )
        for name in method_names:
            setattr(pane, name, lambda current=name: calls.append(current))

        pane.draw_overlays()
        self.assertEqual(calls, [])

        pane.busy = False
        pane.draw_overlays()
        self.assertEqual(calls, list(method_names))

    def test_square_zoom_constraint_is_enabled_geometry(self) -> None:
        class Enabled:
            @staticmethod
            def get() -> bool:
                return True

        pane = object.__new__(FractalPane)
        pane.drag_start = (100, 100)
        pane.square_zoom = Enabled()
        self.assertEqual(pane._selection_endpoint(250, 180), (250, 250))
        self.assertEqual(pane._selection_endpoint(40, 20), (20, 20))


class PrecisionTests(unittest.TestCase):
    def test_automatic_precision_promotes_with_zoom_depth(self) -> None:
        full = Viewport()
        self.assertEqual(
            precision_decision("Automatic", full, 620).mode,
            "float",
        )
        double_view = Viewport(
            mp.mpf("1"),
            mp.mpf("1.000000001"),
            mp.mpf("0"),
            mp.mpf("0.000000001"),
        )
        self.assertEqual(
            precision_decision("Automatic", double_view, 620).mode,
            "double",
        )
        with mp.workprec(120):
            arbitrary_view = Viewport(
                mp.mpf("1"),
                mp.mpf("1.00000000000000000001"),
                mp.mpf("0"),
                mp.mpf("0.00000000000000000001"),
            )
        self.assertEqual(
            precision_decision("Automatic", arbitrary_view, 620).mode,
            "arbitrary",
        )

    def test_arbitrary_reference_renderer_writes_an_rgb_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "arbitrary.ppm"
            render_arbitrary(
                ArbitraryRenderOptions(
                    kind="julia",
                    mode="escape",
                    xmin="-2",
                    xmax="2",
                    ymin="-2",
                    ymax="2",
                    parameter_real="-1",
                    parameter_imag="0",
                    iterations=48,
                    width=64,
                    height=64,
                    bits=80,
                    output_path=output,
                )
            )
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (64, 64))
                self.assertGreater(len(image.getcolors(maxcolors=4096)), 8)

    def test_arbitrary_renderer_resolves_sub_binary64_unit_circle_zoom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "deep.ppm"
            render_arbitrary(
                ArbitraryRenderOptions(
                    kind="julia",
                    mode="escape",
                    xmin="0.999999999999999999",
                    xmax="1.000000000000000001",
                    ymin="-0.000000000000000001",
                    ymax="0.000000000000000001",
                    parameter_real="0",
                    parameter_imag="0",
                    iterations=256,
                    width=96,
                    height=96,
                    bits=100,
                    output_path=output,
                )
            )
            with Image.open(output) as image:
                inside = image.getpixel((12, 48))
                outside = image.getpixel((84, 48))
            self.assertLessEqual(max(inside), 5)
            self.assertGreater(max(outside) - min(outside), 20)

    def test_arbitrary_component_period_mode_preserves_period_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "arbitrary-period.ppm"
            render_arbitrary(
                ArbitraryRenderOptions(
                    kind="tricorn",
                    mode="period",
                    xmin="-2",
                    xmax="2",
                    ymin="-2",
                    ymax="2",
                    parameter_real="0",
                    parameter_imag="0",
                    iterations=256,
                    width=96,
                    height=96,
                    bits=80,
                    output_path=output,
                    max_period=8,
                )
            )
            with Image.open(output) as image:
                period_one = image.getpixel((48, 48))
                period_two = image.getpixel((24, 48))
            self.assertNotEqual(period_one, period_two)
            self.assertGreater(period_one[1], period_one[0])
            self.assertGreater(period_two[0], period_two[2])


class ParameterRayTests(unittest.TestCase):
    def test_wirtinger_derivatives_match_real_direction_differences(self) -> None:
        parameter = -0.4 + 0.3j
        depth = 4
        value, derivative_c, derivative_conjugate = (
            critical_value_orbit_with_derivatives(parameter, depth)
        )
        step = 1e-6
        real_forward = critical_value_orbit_with_derivatives(
            parameter + step, depth
        )[0]
        real_backward = critical_value_orbit_with_derivatives(
            parameter - step, depth
        )[0]
        real_derivative = (real_forward - real_backward) / (2 * step)
        imag_forward = critical_value_orbit_with_derivatives(
            parameter + 1j * step, depth
        )[0]
        imag_backward = critical_value_orbit_with_derivatives(
            parameter - 1j * step, depth
        )[0]
        imag_derivative = (imag_forward - imag_backward) / (2 * step)
        self.assertLess(
            abs(real_derivative - (derivative_c + derivative_conjugate)),
            1e-7,
        )
        self.assertLess(
            abs(
                imag_derivative
                - 1j * (derivative_c - derivative_conjugate)
            ),
            1e-7,
        )
        self.assertTrue(math.isfinite(abs(value)))

    def test_holomorphic_degree_three_parameter_derivative(self) -> None:
        parameter = -0.2 + 0.35j
        depth = 3
        value, derivative_c, derivative_conjugate = (
            critical_value_orbit_with_derivatives(
                parameter,
                depth,
                degree=3,
                antiholomorphic=False,
            )
        )
        step = 1e-6
        forward = critical_value_orbit_with_derivatives(
            parameter + step,
            depth,
            degree=3,
            antiholomorphic=False,
        )[0]
        backward = critical_value_orbit_with_derivatives(
            parameter - step,
            depth,
            degree=3,
            antiholomorphic=False,
        )[0]
        self.assertLess(
            abs((forward - backward) / (2 * step) - derivative_c),
            2e-3,
        )
        self.assertLess(abs(derivative_conjugate), 1e-12)
        self.assertTrue(math.isfinite(abs(value)))

    def test_real_parameter_ray_continuation_reaches_near_boundary(self) -> None:
        trace = trace_parameter_ray(
            Fraction(0),
            depth=8,
            sharpness=4,
            outer_radius=4.0,
        )
        self.assertEqual(len(trace.points), 32)
        self.assertIsNone(trace.stop_reason)
        self.assertTrue(all(abs(point.imag) < 1e-12 for point in trace.points))
        self.assertGreater(trace.points[0].real, trace.points[-1].real)
        self.assertLess(max(trace.residuals), 1e-8)


class InternalCurveTests(unittest.TestCase):
    def test_superattracting_period_two_grand_orbit_curves(self) -> None:
        parameter = -1 + 0j
        cycle = attracting_critical_orbit(parameter)
        self.assertIsNotNone(cycle)
        curves = trace_internal_grand_orbit(
            parameter,
            cycle or (),
            (-2.0, 2.0, -2.0, 2.0),
            representative_log_radius=-1.0,
            generations=3,
            resolution=100,
        )
        self.assertEqual(curves.coordinate_kind, "Böttcher")
        self.assertEqual(curves.return_period, 2)
        self.assertGreaterEqual(len(curves.curves), 3)
        self.assertTrue(any(curve.representative for curve in curves.curves))


class DynamicsTests(unittest.TestCase):
    def test_general_unicritical_map_supports_both_dynamics(self) -> None:
        value = 1 + 2j
        parameter = -0.3 + 0.4j
        self.assertEqual(
            unicritical_map(
                value,
                parameter,
                degree=3,
                antiholomorphic=False,
            ),
            value**3 + parameter,
        )
        self.assertEqual(
            unicritical_map(
                value,
                parameter,
                degree=3,
                antiholomorphic=True,
            ),
            (value**3).conjugate() + parameter,
        )

    def test_antiholomorphic_quadratic_map(self) -> None:
        self.assertEqual(
            anti_quadratic(1 + 2j, -0.5 + 0.25j),
            (-3.5 - 3.75j),
        )

    def test_fixed_critical_orbit_is_detected(self) -> None:
        self.assertEqual(attracting_critical_orbit(0j), (0j,))

    def test_period_two_critical_orbit_is_detected(self) -> None:
        orbit = attracting_critical_orbit(-1 + 0j)
        self.assertIsNotNone(orbit)
        self.assertEqual(len(orbit or ()), 2)
        self.assertEqual(set(orbit or ()), {-1 + 0j, 0j})

    def test_escaping_critical_orbit_has_no_attracting_cycle(self) -> None:
        self.assertIsNone(attracting_critical_orbit(1 + 0j))

    def test_mpmath_dynamics_stays_arbitrary_precision(self) -> None:
        with mp.workprec(180):
            value = mp.mpc("0.100000000000000000000000000000000000001", "0.2")
            parameter = mp.mpc("-0.3", "0.4")
            result = unicritical_map(value, parameter)
            expected = mp.conj(value**2) + parameter
            self.assertIsInstance(result, mp.mpc)
            self.assertEqual(result, expected)

    def test_julia_color_mode_has_black_interior_and_colored_exterior(self) -> None:
        temporary = tempfile.NamedTemporaryFile(suffix=".ppm", delete=False)
        output = Path(temporary.name)
        temporary.close()
        self.addCleanup(output.unlink, missing_ok=True)
        subprocess.run(
            [
                str(RENDERER),
                "--kind",
                "julia",
                "--mode",
                "escape",
                "--cx",
                "0",
                "--cy",
                "0",
                "--width",
                "101",
                "--height",
                "101",
                "--iterations",
                "96",
                "--output",
                str(output),
            ],
            check=True,
        )
        with Image.open(output) as image:
            center = image.convert("RGB").getpixel((50, 50))
            corner = image.convert("RGB").getpixel((0, 0))
        self.assertLessEqual(max(center), 5)
        self.assertGreater(max(corner) - min(corner), 25)


class DynamicalRayTests(unittest.TestCase):
    def test_degree_three_ray_conjugacy_for_both_dynamics(self) -> None:
        angle = Fraction(2, 11)
        potential = 0.04
        for antiholomorphic in (False, True):
            source = ray_point(
                0j,
                angle,
                potential,
                degree=3,
                antiholomorphic=antiholomorphic,
            )
            image = unicritical_map(
                source,
                0j,
                degree=3,
                antiholomorphic=antiholomorphic,
            )
            expected = ray_point(
                0j,
                angle_map(
                    angle,
                    degree=3,
                    antiholomorphic=antiholomorphic,
                ),
                3 * potential,
                degree=3,
                antiholomorphic=antiholomorphic,
            )
            self.assertLess(abs(image - expected), 2e-8)

    def test_rational_angles_are_parsed_and_normalized_exactly(self) -> None:
        self.assertEqual(parse_rational_angle("8/7"), Fraction(1, 7))
        self.assertEqual(parse_rational_angle("-0.125"), Fraction(7, 8))

    def test_antiholomorphic_angle_orbit_is_exact(self) -> None:
        orbit = forward_angle_orbit(Fraction(1, 7))
        self.assertEqual(
            orbit.angles,
            tuple(Fraction(value, 7) for value in (1, 5, 4, 6, 2, 3)),
        )
        self.assertEqual(orbit.preperiod, 0)
        self.assertEqual(orbit.period, 6)

    def test_preperiodic_angle_orbit_reports_preperiod(self) -> None:
        orbit = forward_angle_orbit(Fraction(1, 4))
        self.assertEqual(orbit.angles, (Fraction(1, 4), Fraction(1, 2), Fraction(0)))
        self.assertEqual((orbit.preperiod, orbit.period), (2, 1))

    def test_next_ray_iteration_adds_only_new_image_angles(self) -> None:
        self.assertEqual(
            next_missing_angles((Fraction(1, 7),)),
            (Fraction(5, 7),),
        )
        self.assertEqual(
            next_missing_angles((Fraction(1, 7), Fraction(5, 7))),
            (Fraction(4, 7),),
        )
        complete = forward_angle_orbit(Fraction(1, 7)).angles
        self.assertEqual(next_missing_angles(complete), ())

    def test_ray_images_can_replace_the_current_angle_collection(self) -> None:
        self.assertEqual(
            image_angles((Fraction(1, 7), Fraction(5, 7))),
            (Fraction(5, 7), Fraction(4, 7)),
        )

    def test_c_zero_rays_are_radial_bottcher_lines(self) -> None:
        angle = Fraction(1, 7)
        potential = 0.12
        point = ray_point(0j, angle, potential)
        expected = cmath.exp(potential + 2j * math.pi * float(angle))
        self.assertAlmostEqual(point.real, expected.real, places=11)
        self.assertAlmostEqual(point.imag, expected.imag, places=11)

    def test_ray_conjugacy_matches_angle_and_potential_dynamics(self) -> None:
        parameter = -0.4 + 0.2j
        angle = Fraction(2, 9)
        potential = 0.08
        source = ray_point(parameter, angle, potential)
        image = anti_quadratic(source, parameter)
        expected = ray_point(parameter, angle_map(angle), 2.0 * potential)
        self.assertLess(abs(image - expected), 2e-8)

    def test_full_ray_rejects_disconnected_julia_set(self) -> None:
        with self.assertRaises(DisconnectedJuliaError):
            trace_external_ray(1 + 0j, Fraction(1, 7), samples=16)

    def test_c_zero_ray_lands_near_the_expected_unit_circle_point(self) -> None:
        angle = Fraction(3, 11)
        ray = trace_external_ray(
            0j,
            angle,
            samples=32,
            minimum_potential=1e-5,
        )
        expected = cmath.exp(2j * math.pi * float(angle))
        self.assertLess(abs(ray.landing_approximation - expected), 2e-5)

    def test_zoom_and_resolution_reduce_the_ray_endpoint_potential(self) -> None:
        full_view = adaptive_minimum_potential(4.0, 620)
        zoomed = adaptive_minimum_potential(0.04, 620)
        high_resolution = adaptive_minimum_potential(4.0, 1860)
        self.assertLess(zoomed, full_view)
        self.assertLess(high_resolution, full_view)

    def test_zoom_retracing_moves_the_c_zero_endpoint_closer_to_julia(self) -> None:
        angle = Fraction(1, 9)
        full_view = trace_external_ray(
            0j,
            angle,
            samples=24,
            minimum_potential=adaptive_minimum_potential(4.0, 620),
        )
        zoomed = trace_external_ray(
            0j,
            angle,
            samples=24,
            minimum_potential=adaptive_minimum_potential(0.04, 620),
        )
        landing = cmath.exp(2j * math.pi * float(angle))
        full_gap = abs(full_view.landing_approximation - landing)
        zoomed_gap = abs(zoomed.landing_approximation - landing)
        self.assertLess(zoomed_gap, full_gap / 50.0)

    def test_c_zero_equipotential_is_a_round_circle(self) -> None:
        potential = 0.2
        equipotential = trace_equipotential(0j, potential, samples=64)
        expected_radius = math.exp(potential)
        for point in equipotential.points:
            self.assertAlmostEqual(abs(point), expected_radius, places=10)

    def test_numerical_landing_points_cluster_by_tolerance(self) -> None:
        rays = (
            RayTrace(Fraction(1, 7), (2 + 0j, 1 + 1e-5j)),
            RayTrace(Fraction(2, 7), (2 + 0j, 1 - 1e-5j)),
            RayTrace(Fraction(3, 7), (2 + 0j, -1 + 0j)),
        )
        clusters = cluster_ray_landings(rays, tolerance=1e-3)
        self.assertEqual(tuple(len(cluster.angles) for cluster in clusters), (2, 1))

    def test_landing_period_estimation(self) -> None:
        self.assertEqual(
            estimate_point_period(1 + 0j, 0j, tolerance=1e-12),
            1,
        )

    def test_ray_pair_builds_a_sector_polygon(self) -> None:
        parameter = -1 + 0j
        first = trace_external_ray(
            parameter,
            Fraction(4, 17),
            samples=96,
            minimum_potential=2e-3,
        )
        second = trace_external_ray(
            parameter,
            Fraction(7, 30),
            samples=96,
            minimum_potential=2e-3,
        )
        polygon = sector_polygon(parameter, first, second, containing=0j)
        self.assertGreater(len(polygon), 200)
        self.assertTrue(
            all(math.isfinite(point.real) and math.isfinite(point.imag) for point in polygon)
        )


if __name__ == "__main__":
    unittest.main()
