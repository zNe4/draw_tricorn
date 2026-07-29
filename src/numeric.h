#ifndef NUMERIC_H
#define NUMERIC_H

#include <stddef.h>

#include "fractal.h"

typedef struct {
    double real;
    double imag;
} LoomComplex;

typedef struct {
    double log_radius;
    size_t first_polyline;
    size_t polyline_count;
    int representative;
} LoomInternalCurve;

typedef struct {
    size_t first_point;
    size_t point_count;
} LoomPolyline;

typedef struct {
    int coordinate_kind; /* 1 = Bottcher, 2 = Koenigs */
    int return_period;
    size_t curve_count;
    size_t polyline_count;
    size_t point_count;
    LoomInternalCurve *curves;
    LoomPolyline *polylines;
    LoomComplex *points;
} LoomInternalCurveResult;

const char *loom_last_error(void);

int loom_render_rgb(
    const RenderOptions *options,
    unsigned char *rgb,
    size_t rgb_size
);

int loom_unicritical_map(
    LoomComplex value,
    LoomComplex parameter,
    int degree,
    int antiholomorphic,
    LoomComplex *result
);

double loom_escape_radius(LoomComplex parameter, int degree);

int loom_attracting_critical_orbit(
    LoomComplex parameter,
    int max_steps,
    int max_period,
    double tolerance,
    int degree,
    int antiholomorphic,
    LoomComplex *cycle,
    size_t cycle_capacity,
    size_t *cycle_count
);

int loom_critical_orbit_bounded(
    LoomComplex parameter,
    int degree,
    int antiholomorphic,
    int iterations
);

int loom_ray_point(
    LoomComplex parameter,
    double angle,
    double potential,
    double outer_potential,
    int degree,
    int antiholomorphic,
    LoomComplex *point
);

int loom_trace_external_ray(
    LoomComplex parameter,
    double angle,
    int samples,
    double minimum_potential,
    double maximum_potential,
    int require_connected,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
);

int loom_trace_equipotential(
    LoomComplex parameter,
    double potential,
    int samples,
    int require_connected,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
);

int loom_trace_outer_arc(
    LoomComplex parameter,
    double start_angle,
    double angular_length,
    double potential,
    int samples,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
);

int loom_estimate_point_period(
    LoomComplex point,
    LoomComplex parameter,
    double tolerance,
    int max_period,
    int degree,
    int antiholomorphic
);

int loom_point_in_polygon(
    LoomComplex point,
    const LoomComplex *polygon,
    size_t polygon_count
);

int loom_critical_value_orbit_with_derivatives(
    LoomComplex parameter,
    int depth,
    int degree,
    int antiholomorphic,
    LoomComplex *value,
    LoomComplex *derivative_c,
    LoomComplex *derivative_conjugate
);

int loom_real_newton_parameter(
    LoomComplex target,
    int depth,
    LoomComplex seed,
    double tolerance,
    int max_steps,
    int degree,
    int antiholomorphic,
    LoomComplex *parameter,
    double *residual,
    int *converged
);

int loom_trace_parameter_ray(
    double angle,
    int depth,
    int sharpness,
    double outer_radius,
    double tolerance,
    int max_newton_steps,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    double *residuals,
    size_t capacity,
    size_t *point_count,
    size_t *requested_samples,
    int *stopped_sample
);

int loom_trace_internal_grand_orbit(
    LoomComplex parameter,
    const LoomComplex *cycle,
    size_t cycle_count,
    double xmin,
    double xmax,
    double ymin,
    double ymax,
    double representative_log_radius,
    int generations,
    int resolution,
    int max_returns,
    int degree,
    int antiholomorphic,
    LoomInternalCurveResult *result
);

void loom_free_internal_curve_result(LoomInternalCurveResult *result);

#endif
