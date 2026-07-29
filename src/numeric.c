#include "numeric.h"

#include "numeric_internal.h"

#include <complex.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static _Thread_local char error_message[256];

void loom_set_error(const char *message) {
    if (message == NULL) {
        error_message[0] = '\0';
        return;
    }
    snprintf(error_message, sizeof(error_message), "%s", message);
}

const char *loom_last_error(void) {
    return error_message;
}

static double complex to_complex(LoomComplex value) {
    return value.real + I * value.imag;
}

static LoomComplex from_complex(double complex value) {
    return (LoomComplex){creal(value), cimag(value)};
}

static double complex power_int(double complex value, int exponent) {
    double complex result = 1.0;
    while (exponent > 0) {
        if (exponent & 1) {
            result *= value;
        }
        value *= value;
        exponent >>= 1;
    }
    return result;
}

static double complex map_value(
    double complex value,
    double complex parameter,
    int degree,
    int antiholomorphic
) {
    double complex powered = power_int(value, degree);
    return (antiholomorphic ? conj(powered) : powered) + parameter;
}

static double normalize_angle(double angle) {
    double normalized = fmod(angle, 1.0);
    return normalized < 0.0 ? normalized + 1.0 : normalized;
}

static double map_angle(double angle, int degree, int antiholomorphic) {
    return normalize_angle((antiholomorphic ? -degree : degree) * angle);
}

static int valid_degree(int degree) {
    if (degree < 2 || degree > 32) {
        loom_set_error("Degree must be between 2 and 32.");
        return 0;
    }
    return 1;
}

int loom_render_rgb(
    const RenderOptions *options,
    unsigned char *rgb,
    size_t rgb_size
) {
    loom_set_error(NULL);
    if (options == NULL || rgb == NULL) {
        loom_set_error("Render options and output buffer are required.");
        return -1;
    }
    size_t required = (size_t)options->width * options->height * 3;
    if (options->width < 1 || options->height < 1 || rgb_size < required) {
        loom_set_error("The RGB output buffer is too small.");
        return -1;
    }
    if (render_fractal_rgb(options, rgb, rgb_size) != 0) {
        loom_set_error("The C renderer failed.");
        return -1;
    }
    return 0;
}

int loom_unicritical_map(
    LoomComplex value,
    LoomComplex parameter,
    int degree,
    int antiholomorphic,
    LoomComplex *result
) {
    loom_set_error(NULL);
    if (result == NULL || !valid_degree(degree)) {
        if (result == NULL) {
            loom_set_error("A map output pointer is required.");
        }
        return -1;
    }
    *result = from_complex(map_value(
        to_complex(value), to_complex(parameter), degree, antiholomorphic
    ));
    return 0;
}

double loom_escape_radius(LoomComplex parameter, int degree) {
    loom_set_error(NULL);
    if (!valid_degree(degree)) {
        return NAN;
    }
    return fmax(2.0, pow(2.0 * cabs(to_complex(parameter)), 1.0 / degree));
}

int loom_attracting_critical_orbit(
    LoomComplex parameter_value,
    int max_steps,
    int max_period,
    double tolerance,
    int degree,
    int antiholomorphic,
    LoomComplex *cycle,
    size_t cycle_capacity,
    size_t *cycle_count
) {
    loom_set_error(NULL);
    if (cycle_count == NULL || max_steps < 3 || max_period < 1
        || tolerance <= 0.0 || !isfinite(tolerance) || !valid_degree(degree)) {
        if (cycle_count == NULL) {
            loom_set_error("A cycle-count output pointer is required.");
        } else if (max_steps < 3 || max_period < 1) {
            loom_set_error("max_steps and max_period must be positive.");
        } else if (tolerance <= 0.0 || !isfinite(tolerance)) {
            loom_set_error("Orbit tolerance must be finite and positive.");
        }
        return -1;
    }
    *cycle_count = 0;
    double complex *history = malloc((size_t)max_steps * sizeof(*history));
    if (history == NULL) {
        loom_set_error("Not enough memory for the critical orbit history.");
        return -1;
    }

    double complex parameter = to_complex(parameter_value);
    double complex value = 0.0;
    double radius = fmax(2.0, pow(2.0 * cabs(parameter), 1.0 / degree));
    for (int step = 0; step < max_steps; ++step) {
        value = map_value(value, parameter, degree, antiholomorphic);
        if (cabs(value) > radius) {
            free(history);
            return 0;
        }
        history[step] = value;
    }

    int largest_period = max_period;
    int history_limit = (max_steps - 1) / 2;
    if (largest_period > history_limit) {
        largest_period = history_limit;
    }
    for (int period = 1; period <= largest_period; ++period) {
        double newest_error = cabs(
            history[max_steps - 1] - history[max_steps - 1 - period]
        );
        double previous_error = cabs(
            history[max_steps - 1 - period]
            - history[max_steps - 1 - 2 * period]
        );
        if (newest_error <= tolerance
            && previous_error <= tolerance * 100.0
            && newest_error <= previous_error + tolerance * 0.01) {
            if ((size_t)period > cycle_capacity || cycle == NULL) {
                free(history);
                loom_set_error("The attracting-cycle output buffer is too small.");
                return -1;
            }
            for (int index = 0; index < period; ++index) {
                cycle[index] = from_complex(history[max_steps - period + index]);
            }
            *cycle_count = (size_t)period;
            free(history);
            return 1;
        }
    }
    free(history);
    return 0;
}

int loom_critical_orbit_bounded(
    LoomComplex parameter_value,
    int degree,
    int antiholomorphic,
    int iterations
) {
    loom_set_error(NULL);
    if (iterations < 1 || !valid_degree(degree)) {
        if (iterations < 1) {
            loom_set_error("Iterations must be positive.");
        }
        return -1;
    }
    double complex parameter = to_complex(parameter_value);
    double radius = fmax(2.0, pow(2.0 * cabs(parameter), 1.0 / degree));
    double complex value = 0.0;
    for (int step = 0; step < iterations; ++step) {
        value = map_value(value, parameter, degree, antiholomorphic);
        if (cabs(value) > radius) {
            return 0;
        }
    }
    return 1;
}

static int ray_point_impl(
    double complex parameter,
    double angle,
    double potential,
    double outer_potential,
    int degree,
    int antiholomorphic,
    double complex *output
) {
    if (potential <= 0.0 || !isfinite(potential)) {
        loom_set_error("External potential must be finite and positive.");
        return -1;
    }
    if (!isfinite(outer_potential)) {
        loom_set_error("Outer potential must be finite.");
        return -1;
    }
    if (outer_potential <= potential) {
        outer_potential = potential * 2.0;
    }

    double logarithm = log(outer_potential / potential) / log((double)degree);
    int pullbacks = (int)ceil(logarithm);
    if (pullbacks < 1) {
        pullbacks = 1;
    }
    double *angles = malloc((size_t)(pullbacks + 1) * sizeof(*angles));
    if (angles == NULL) {
        loom_set_error("Not enough memory for ray pullback angles.");
        return -1;
    }
    angles[0] = normalize_angle(angle);
    for (int level = 0; level < pullbacks; ++level) {
        angles[level + 1] = map_angle(
            angles[level], degree, antiholomorphic
        );
    }

    double lifted_potential = potential * pow((double)degree, pullbacks);
    double complex point = cexp(
        lifted_potential + I * 2.0 * M_PI * angles[pullbacks]
    );
    double complex unity = cexp(I * 2.0 * M_PI / degree);
    for (int level = pullbacks - 1; level >= 0; --level) {
        double complex preimage = point - parameter;
        if (antiholomorphic) {
            preimage = conj(preimage);
        }
        double complex root = cexp(clog(preimage) / degree);
        double expected_potential = potential * pow((double)degree, level);
        double complex expected = cexp(
            expected_potential + I * 2.0 * M_PI * angles[level]
        );
        double best_distance = INFINITY;
        double complex best = root;
        double complex candidate = root;
        for (int branch = 0; branch < degree; ++branch) {
            double distance = cabs(candidate - expected);
            if (distance < best_distance) {
                best_distance = distance;
                best = candidate;
            }
            candidate *= unity;
        }
        point = best;
    }
    free(angles);
    *output = point;
    return 0;
}

int loom_ray_point(
    LoomComplex parameter,
    double angle,
    double potential,
    double outer_potential,
    int degree,
    int antiholomorphic,
    LoomComplex *point
) {
    loom_set_error(NULL);
    if (point == NULL || !valid_degree(degree)) {
        if (point == NULL) {
            loom_set_error("A ray-point output pointer is required.");
        }
        return -1;
    }
    double complex result;
    if (ray_point_impl(
            to_complex(parameter), angle, potential, outer_potential,
            degree, antiholomorphic, &result
        ) != 0) {
        return -1;
    }
    *point = from_complex(result);
    return 0;
}

int loom_trace_external_ray(
    LoomComplex parameter_value,
    double angle,
    int samples,
    double minimum_potential,
    double maximum_potential,
    int require_connected,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
) {
    loom_set_error(NULL);
    if (samples < 2 || points == NULL || point_capacity < (size_t)samples
        || !(minimum_potential > 0.0 && minimum_potential < maximum_potential)
        || !valid_degree(degree)) {
        if (samples < 2) {
            loom_set_error("A ray needs at least two samples.");
        } else if (points == NULL || point_capacity < (size_t)samples) {
            loom_set_error("The ray output buffer is too small.");
        } else if (!(minimum_potential > 0.0 && minimum_potential < maximum_potential)) {
            loom_set_error("Ray potential limits are invalid.");
        }
        return -1;
    }
    if (require_connected) {
        int bounded = loom_critical_orbit_bounded(
            parameter_value, degree, antiholomorphic, 2048
        );
        if (bounded < 0) {
            return -1;
        }
        if (!bounded) {
            loom_set_error(
                "The critical orbit escapes, so a full unbranched ray is not available."
            );
            return 1;
        }
    }
    double complex parameter = to_complex(parameter_value);
    double ratio = minimum_potential / maximum_potential;
    double normalized = normalize_angle(angle);
    for (int index = 0; index < samples; ++index) {
        double potential = maximum_potential * pow(
            ratio, (double)index / (samples - 1)
        );
        double complex point;
        if (ray_point_impl(
                parameter, normalized, potential, 9.0,
                degree, antiholomorphic, &point
            ) != 0) {
            return -1;
        }
        points[index] = from_complex(point);
    }
    return 0;
}

int loom_trace_equipotential(
    LoomComplex parameter_value,
    double potential,
    int samples,
    int require_connected,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
) {
    loom_set_error(NULL);
    size_t required = (size_t)samples + 1;
    if (potential <= 0.0 || samples < 32 || points == NULL
        || point_capacity < required || !valid_degree(degree)) {
        if (potential <= 0.0) {
            loom_set_error("Equipotential must be positive.");
        } else if (samples < 32) {
            loom_set_error("An equipotential needs at least 32 samples.");
        } else if (points == NULL || point_capacity < required) {
            loom_set_error("The equipotential output buffer is too small.");
        }
        return -1;
    }
    if (require_connected) {
        int bounded = loom_critical_orbit_bounded(
            parameter_value, degree, antiholomorphic, 2048
        );
        if (bounded < 0) {
            return -1;
        }
        if (!bounded) {
            loom_set_error(
                "The critical orbit escapes, so a full equipotential is not available."
            );
            return 1;
        }
    }
    double complex parameter = to_complex(parameter_value);
    for (int index = 0; index < samples; ++index) {
        double complex point;
        if (ray_point_impl(
                parameter, (double)index / samples, potential, 9.0,
                degree, antiholomorphic, &point
            ) != 0) {
            return -1;
        }
        points[index] = from_complex(point);
    }
    points[samples] = points[0];
    return 0;
}

int loom_trace_outer_arc(
    LoomComplex parameter_value,
    double start_angle,
    double angular_length,
    double potential,
    int samples,
    int degree,
    int antiholomorphic,
    LoomComplex *points,
    size_t point_capacity
) {
    loom_set_error(NULL);
    size_t required = (size_t)samples + 1;
    if (samples < 1 || potential <= 0.0 || points == NULL
        || point_capacity < required || !valid_degree(degree)) {
        if (samples < 1) {
            loom_set_error("An outer arc needs at least one segment.");
        } else if (potential <= 0.0) {
            loom_set_error("Outer-arc potential must be positive.");
        } else if (points == NULL || point_capacity < required) {
            loom_set_error("The outer-arc output buffer is too small.");
        }
        return -1;
    }
    double complex parameter = to_complex(parameter_value);
    for (int index = 0; index <= samples; ++index) {
        double angle = start_angle + angular_length * (double)index / samples;
        double complex point;
        if (ray_point_impl(
                parameter, angle, potential, 9.0,
                degree, antiholomorphic, &point
            ) != 0) {
            return -1;
        }
        points[index] = from_complex(point);
    }
    return 0;
}

int loom_estimate_point_period(
    LoomComplex point_value,
    LoomComplex parameter_value,
    double tolerance,
    int max_period,
    int degree,
    int antiholomorphic
) {
    loom_set_error(NULL);
    if (tolerance <= 0.0 || max_period < 1 || !valid_degree(degree)) {
        if (tolerance <= 0.0) {
            loom_set_error("Period tolerance must be positive.");
        } else if (max_period < 1) {
            loom_set_error("Maximum period must be positive.");
        }
        return -1;
    }
    double complex point = to_complex(point_value);
    double complex parameter = to_complex(parameter_value);
    double complex value = point;
    for (int period = 1; period <= max_period; ++period) {
        value = map_value(value, parameter, degree, antiholomorphic);
        if (cabs(value - point) <= tolerance) {
            return period;
        }
    }
    return 0;
}

int loom_point_in_polygon(
    LoomComplex point,
    const LoomComplex *polygon,
    size_t polygon_count
) {
    loom_set_error(NULL);
    if (polygon == NULL || polygon_count < 3) {
        loom_set_error("A polygon needs at least three points.");
        return -1;
    }
    int inside = 0;
    double x = point.real;
    double y = point.imag;
    LoomComplex previous = polygon[polygon_count - 1];
    for (size_t index = 0; index < polygon_count; ++index) {
        LoomComplex current = polygon[index];
        int crosses = (previous.imag > y) != (current.imag > y);
        if (crosses) {
            double x_cross = (current.real - previous.real)
                * (y - previous.imag) / (current.imag - previous.imag)
                + previous.real;
            if (x < x_cross) {
                inside = !inside;
            }
        }
        previous = current;
    }
    return inside;
}

static void critical_derivatives_impl(
    double complex parameter,
    int depth,
    int degree,
    int antiholomorphic,
    double complex *value,
    double complex *derivative_c,
    double complex *derivative_conjugate
) {
    *value = parameter;
    *derivative_c = 1.0;
    *derivative_conjugate = 0.0;
    for (int step = 0; step < depth; ++step) {
        double complex previous = *value;
        double complex previous_c = *derivative_c;
        double complex previous_conjugate = *derivative_conjugate;
        if (antiholomorphic) {
            double complex coefficient = degree
                * power_int(conj(previous), degree - 1);
            *derivative_c = coefficient * conj(previous_conjugate) + 1.0;
            *derivative_conjugate = coefficient * conj(previous_c);
            *value = conj(power_int(previous, degree)) + parameter;
        } else {
            double complex coefficient = degree
                * power_int(previous, degree - 1);
            *derivative_c = coefficient * previous_c + 1.0;
            *derivative_conjugate = coefficient * previous_conjugate;
            *value = power_int(previous, degree) + parameter;
        }
    }
}

int loom_critical_value_orbit_with_derivatives(
    LoomComplex parameter_value,
    int depth,
    int degree,
    int antiholomorphic,
    LoomComplex *value,
    LoomComplex *derivative_c,
    LoomComplex *derivative_conjugate
) {
    loom_set_error(NULL);
    if (depth < 1 || value == NULL || derivative_c == NULL
        || derivative_conjugate == NULL || !valid_degree(degree)) {
        if (depth < 1) {
            loom_set_error("Depth must be positive.");
        } else if (value == NULL || derivative_c == NULL
                   || derivative_conjugate == NULL) {
            loom_set_error("Derivative output pointers are required.");
        }
        return -1;
    }
    double complex raw_value;
    double complex raw_c;
    double complex raw_conjugate;
    critical_derivatives_impl(
        to_complex(parameter_value), depth, degree, antiholomorphic,
        &raw_value, &raw_c, &raw_conjugate
    );
    *value = from_complex(raw_value);
    *derivative_c = from_complex(raw_c);
    *derivative_conjugate = from_complex(raw_conjugate);
    return 0;
}

static void real_newton_impl(
    double complex target,
    int depth,
    double complex seed,
    double tolerance,
    int max_steps,
    int degree,
    int antiholomorphic,
    double complex *parameter_output,
    double *residual_output,
    int *converged_output
) {
    double complex parameter = seed;
    double residual = INFINITY;
    int converged = 0;
    for (int step = 0; step < max_steps; ++step) {
        double complex value;
        double complex derivative_c;
        double complex derivative_conjugate;
        critical_derivatives_impl(
            parameter, depth, degree, antiholomorphic,
            &value, &derivative_c, &derivative_conjugate
        );
        double complex error = value - target;
        residual = cabs(error);
        if (residual <= tolerance * fmax(1.0, cabs(target))) {
            converged = 1;
            break;
        }

        double determinant = pow(cabs(derivative_c), 2.0)
            - pow(cabs(derivative_conjugate), 2.0);
        double scale = pow(cabs(derivative_c), 2.0)
            + pow(cabs(derivative_conjugate), 2.0);
        if (!isfinite(determinant)
            || fabs(determinant) <= 1e-14 * fmax(1.0, scale)) {
            break;
        }
        double complex correction = (
            conj(derivative_c) * error
            - derivative_conjugate * conj(error)
        ) / determinant;
        if (!isfinite(creal(correction)) || !isfinite(cimag(correction))) {
            break;
        }

        double damping = 1.0;
        int accepted = 0;
        while (damping >= 1.0 / 256.0) {
            double complex candidate = parameter - damping * correction;
            double complex candidate_value;
            double complex unused_c;
            double complex unused_conjugate;
            critical_derivatives_impl(
                candidate, depth, degree, antiholomorphic,
                &candidate_value, &unused_c, &unused_conjugate
            );
            double candidate_residual = cabs(candidate_value - target);
            if (candidate_residual < residual) {
                parameter = candidate;
                residual = candidate_residual;
                accepted = 1;
                break;
            }
            damping *= 0.5;
        }
        if (!accepted) {
            break;
        }
    }
    *parameter_output = parameter;
    *residual_output = residual;
    *converged_output = converged;
}

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
) {
    loom_set_error(NULL);
    if (depth < 1 || tolerance <= 0.0 || max_steps < 1
        || parameter == NULL || residual == NULL || converged == NULL
        || !valid_degree(degree)) {
        if (depth < 1) {
            loom_set_error("Depth must be positive.");
        } else if (tolerance <= 0.0) {
            loom_set_error("Newton tolerance must be positive.");
        } else if (max_steps < 1) {
            loom_set_error("Newton steps must be positive.");
        } else if (parameter == NULL || residual == NULL || converged == NULL) {
            loom_set_error("Newton output pointers are required.");
        }
        return -1;
    }
    double complex result;
    double residual_value;
    int converged_value;
    real_newton_impl(
        to_complex(target), depth, to_complex(seed), tolerance, max_steps,
        degree, antiholomorphic, &result, &residual_value, &converged_value
    );
    *parameter = from_complex(result);
    *residual = residual_value;
    *converged = converged_value;
    return 0;
}

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
) {
    loom_set_error(NULL);
    if (depth < 1 || depth > 40 || sharpness < 1 || sharpness > 64
        || !isfinite(outer_radius) || outer_radius <= 1.0
        || tolerance <= 0.0 || max_newton_steps < 1
        || points == NULL || residuals == NULL || point_count == NULL
        || requested_samples == NULL || stopped_sample == NULL
        || !valid_degree(degree)) {
        if (depth < 1 || depth > 40) {
            loom_set_error("Depth must be between 1 and 40.");
        } else if (sharpness < 1 || sharpness > 64) {
            loom_set_error("Sharpness must be between 1 and 64.");
        } else if (!isfinite(outer_radius) || outer_radius <= 1.0) {
            loom_set_error("Outer radius must be finite and greater than one.");
        } else if (tolerance <= 0.0 || max_newton_steps < 1) {
            loom_set_error("Newton controls must be positive.");
        } else if (points == NULL || residuals == NULL || point_count == NULL
                   || requested_samples == NULL || stopped_sample == NULL) {
            loom_set_error("Parameter-ray output buffers are required.");
        }
        return -1;
    }

    size_t requested = (size_t)depth * sharpness;
    if (capacity < requested) {
        loom_set_error("The parameter-ray output buffer is too small.");
        return -1;
    }
    *point_count = 0;
    *requested_samples = requested;
    *stopped_sample = 0;

    double normalized = normalize_angle(angle);
    double complex seed = outer_radius
        * cexp(I * 2.0 * M_PI * normalized);
    for (size_t sample = 1; sample <= requested; ++sample) {
        int iterate_depth = (int)((sample - 1) / sharpness) + 1;
        double depth_exponent = iterate_depth
            - (double)sample / sharpness;
        double target_radius = pow(
            outer_radius, pow((double)degree, depth_exponent)
        );
        double target_angle = normalized;
        for (int step = 0; step < iterate_depth; ++step) {
            target_angle = map_angle(target_angle, degree, antiholomorphic);
        }
        double complex target = target_radius
            * cexp(I * 2.0 * M_PI * target_angle);
        double complex parameter;
        double residual;
        int converged;
        real_newton_impl(
            target, iterate_depth, seed, tolerance, max_newton_steps,
            degree, antiholomorphic, &parameter, &residual, &converged
        );
        seed = parameter;
        if (!converged) {
            residuals[*point_count] = residual;
            *stopped_sample = (int)sample;
            break;
        }
        points[*point_count] = from_complex(seed);
        residuals[*point_count] = residual;
        ++*point_count;
    }
    if (*point_count == 0) {
        loom_set_error("Parameter-ray continuation failed.");
        return 1;
    }
    return 0;
}
