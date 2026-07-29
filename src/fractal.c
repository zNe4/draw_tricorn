#include "fractal.h"

#include "palette.h"

#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    double metric;
    double smooth_escape;
    double complex last_value;
    int period;
    bool inside;
} PixelData;

static inline double modulus_squared(double complex value) {
    double real = creal(value);
    double imag = cimag(value);
    return real * real + imag * imag;
}

static inline double complex power_int(double complex value, int exponent) {
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

static inline float complex power_int_float(
    float complex value,
    int exponent
) {
    float complex result = 1.0f;
    while (exponent > 0) {
        if (exponent & 1) {
            result *= value;
        }
        value *= value;
        exponent >>= 1;
    }
    return result;
}

static inline double complex unicritical_map(
    double complex value,
    double complex parameter,
    DynamicsKind dynamics,
    int degree
) {
    double complex powered = power_int(value, degree);
    return (
        dynamics == DYNAMICS_ANTIHOL ? conj(powered) : powered
    ) + parameter;
}

static inline double complex antiholomorphic_second_iterate(
    double complex value,
    double complex parameter,
    int degree
) {
    double complex first = power_int(value, degree) + conj(parameter);
    return power_int(first, degree) + parameter;
}

static inline double complex antiholomorphic_second_derivative(
    double complex value,
    double complex parameter,
    int degree
) {
    double complex powered = power_int(value, degree);
    return (
        (double)degree * degree
        * power_int(value, degree - 1)
        * power_int(powered + conj(parameter), degree - 1)
    );
}

static PixelData escape_data(
    double complex initial,
    double complex parameter,
    int max_iterations,
    DynamicsKind dynamics,
    int degree
) {
    double complex value = initial;
    double escape_radius = fmax(
        2.0,
        pow(2.0 * cabs(parameter), 1.0 / degree)
    );
    double escape_squared = escape_radius * escape_radius;
    for (int iteration = 0; iteration < max_iterations; ++iteration) {
        value = unicritical_map(value, parameter, dynamics, degree);
        double radius_squared = modulus_squared(value);
        if (radius_squared > escape_squared) {
            double log_radius = 0.5 * log(radius_squared);
            double smooth =
                iteration + 1.0 - log(log_radius) / log((double)degree);
            return (PixelData){
                .metric = 0.0,
                .smooth_escape = fmax(0.0, smooth),
                .last_value = value,
                .period = 0,
                .inside = false,
            };
        }
    }
    return (PixelData){
        .metric = 0.0,
        .smooth_escape = (double)max_iterations,
        .last_value = value,
        .period = 0,
        .inside = true,
    };
}

static PixelData escape_data_float(
    float complex initial,
    float complex parameter,
    int max_iterations,
    DynamicsKind dynamics,
    int degree
) {
    float complex value = initial;
    float escape_radius = fmaxf(
        2.0f,
        powf(2.0f * cabsf(parameter), 1.0f / degree)
    );
    float escape_squared = escape_radius * escape_radius;
    for (int iteration = 0; iteration < max_iterations; ++iteration) {
        float complex powered = power_int_float(value, degree);
        value = (
            dynamics == DYNAMICS_ANTIHOL ? conjf(powered) : powered
        ) + parameter;
        float real = crealf(value);
        float imag = cimagf(value);
        float radius_squared = real * real + imag * imag;
        if (radius_squared > escape_squared) {
            double log_radius = 0.5 * log((double)radius_squared);
            double smooth =
                iteration + 1.0 - log(log_radius) / log((double)degree);
            return (PixelData){
                .metric = 0.0,
                .smooth_escape = fmax(0.0, smooth),
                .last_value = (double complex)value,
                .period = 0,
                .inside = false,
            };
        }
    }
    return (PixelData){
        .metric = 0.0,
        .smooth_escape = (double)max_iterations,
        .last_value = (double complex)value,
        .period = 0,
        .inside = true,
    };
}

/*
 * Crowe--Hasson--Rippon--Strain-Clark describe the period-one component as
 *
 *     D_1 = {c = w - conjugate(w)^2 : |w| < 1/2}.
 *
 * Its boundary has c = (1/2)e^(it) - (1/4)e^(-2it).  Eliminating t gives the
 * following implicit deltoid test, with u = 4c:
 *
 *     |u|^4 + 18|u|^2 + 8 Re(u^3) - 27 < 0.
 */
static bool in_period_one_deltoid(double complex parameter) {
    double complex scaled = 4.0 * parameter;
    double radius_squared = modulus_squared(scaled);
    double implicit =
        radius_squared * radius_squared
        + 18.0 * radius_squared
        + 8.0 * creal(scaled * scaled * scaled)
        - 27.0;
    return implicit < -1e-10;
}

static void holomorphic_return(
    double complex root,
    double complex parameter,
    int original_steps,
    DynamicsKind dynamics,
    int degree,
    double complex *value,
    double complex *derivative
) {
    *value = root;
    *derivative = 1.0;
    if (dynamics == DYNAMICS_HOLOMORPHIC) {
        for (int iterate = 0; iterate < original_steps; ++iterate) {
            *derivative *=
                degree * power_int(*value, degree - 1);
            *value = power_int(*value, degree) + parameter;
        }
        return;
    }

    int pairs = original_steps / 2;
    for (int iterate = 0; iterate < pairs; ++iterate) {
        *derivative *= antiholomorphic_second_derivative(
            *value, parameter, degree
        );
        *value = antiholomorphic_second_iterate(
            *value, parameter, degree
        );
    }
}

static bool has_exact_period(
    double complex root,
    double complex parameter,
    int period,
    DynamicsKind dynamics,
    int degree
) {
    double complex value = root;
    double tolerance = 2e-6 * (1.0 + cabs(root));
    for (int step = 1; step <= period; ++step) {
        value = unicritical_map(value, parameter, dynamics, degree);
        if (step < period && period % step == 0
            && cabs(value - root) < tolerance) {
            return false;
        }
    }
    return cabs(value - root) < tolerance;
}

/*
 * Newton is applied only to a holomorphic return: f^p for even p and f^(2p)
 * for odd p.  The final exact-period check is essential because a root of
 * f^(2p)(z)-z may belong to a proper divisor cycle of the antiholomorphic map.
 */
static bool attracting_cycle_for_period(
    double complex parameter,
    int period,
    double complex seed,
    DynamicsKind dynamics,
    int degree,
    double *multiplier
) {
    int return_steps = (
        dynamics == DYNAMICS_HOLOMORPHIC || period % 2 == 0
        ? period
        : 2 * period
    );
    double complex root = seed;

    for (int step = 0; step < 36; ++step) {
        double complex value;
        double complex derivative;
        holomorphic_return(
            root,
            parameter,
            return_steps,
            dynamics,
            degree,
            &value,
            &derivative
        );
        double complex denominator = derivative - 1.0;
        if (cabs(denominator) < 1e-14) {
            return false;
        }
        double complex correction = (value - root) / denominator;
        root -= correction;
        if (!isfinite(creal(root)) || !isfinite(cimag(root))) {
            return false;
        }
        if (cabs(correction) < 2e-13 * (1.0 + cabs(root))) {
            break;
        }
    }

    double complex value;
    double complex derivative;
    holomorphic_return(
        root,
        parameter,
        return_steps,
        dynamics,
        degree,
        &value,
        &derivative
    );
    if (cabs(value - root) > 2e-7 * (1.0 + cabs(root))
        || !isfinite(cabs(derivative))
        || !has_exact_period(
            root, parameter, period, dynamics, degree
        )) {
        return false;
    }

    *multiplier = cabs(derivative);
    return *multiplier < 1.000001;
}

static int likely_component_period(
    double complex parameter,
    double complex seed,
    int max_period,
    DynamicsKind dynamics,
    int degree
) {
    double complex value = seed;
    double best_distance = INFINITY;
    int best_period = 0;
    for (int period = 1; period <= max_period; ++period) {
        value = unicritical_map(value, parameter, dynamics, degree);
        double distance = cabs(value - seed);
        if (distance < best_distance) {
            best_distance = distance;
            best_period = period;
        }
    }
    return best_period;
}

static PixelData component_period_data(
    PixelData membership,
    double complex parameter,
    int max_period,
    DynamicsKind dynamics,
    int degree
) {
    if (!membership.inside) {
        return membership;
    }

    bool direct_period_one = (
        dynamics == DYNAMICS_ANTIHOL
        && degree == 2
        && in_period_one_deltoid(parameter)
    );
    if (direct_period_one) {
        double fixed_multiplier =
            4.0 * modulus_squared(membership.last_value);
        membership.metric = fmin(1.0, fmax(0.0, fixed_multiplier));
        membership.period = 1;
        return membership;
    }

    double complex seed = membership.last_value;
    int candidate = likely_component_period(
        parameter, seed, max_period, dynamics, degree
    );
    if (candidate >= 1) {
        double multiplier = 0.0;
        if (attracting_cycle_for_period(
                parameter,
                candidate,
                seed,
                dynamics,
                degree,
                &multiplier
            )) {
            membership.metric = fmin(1.0, fmax(0.0, multiplier));
            membership.period = candidate;
            return membership;
        }
    }

    for (int period = 1; period <= max_period; ++period) {
        if (period == candidate) {
            continue;
        }
        double multiplier = 0.0;
        if (attracting_cycle_for_period(
                parameter,
                period,
                seed,
                dynamics,
                degree,
                &multiplier
            )) {
            membership.metric = fmin(1.0, fmax(0.0, multiplier));
            membership.period = period;
            return membership;
        }
    }

    /* Bounded, but no attracting cycle was certified within the chosen range. */
    membership.metric = 1.0;
    membership.period = 0;
    return membership;
}

static PixelData newton_multiplier_data(
    PixelData membership,
    double complex parameter,
    int max_period,
    DynamicsKind dynamics,
    int degree
) {
    return component_period_data(
        membership, parameter, max_period, dynamics, degree
    );
}

static PixelData lyapunov_data(
    PixelData membership,
    double complex parameter,
    int samples,
    DynamicsKind dynamics,
    int degree
) {
    if (!membership.inside) {
        return membership;
    }

    double complex value = 0.0;
    int burn_in = samples / 2;
    for (int iteration = 0; iteration < burn_in; ++iteration) {
        value = unicritical_map(value, parameter, dynamics, degree);
    }

    double log_sum = 0.0;
    int valid_samples = 0;
    for (int iteration = 0; iteration < samples; ++iteration) {
        value = unicritical_map(value, parameter, dynamics, degree);
        double derivative_modulus =
            degree * pow(cabs(value), degree - 1);
        if (derivative_modulus > 1e-15) {
            log_sum += log(derivative_modulus);
            ++valid_samples;
        }
    }

    if (valid_samples == 0) {
        membership.metric = 0.0;
    } else {
        double geometric_mean = exp(log_sum / valid_samples);
        membership.metric = fmin(1.0, fmax(0.0, geometric_mean));
    }
    return membership;
}

static bool boundary_pixel(
    const PixelData *pixels,
    int width,
    int height,
    int x,
    int y
) {
    bool membership = pixels[y * width + x].inside;
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if (dx == 0 && dy == 0) {
                continue;
            }
            int nx = x + dx;
            int ny = y + dy;
            if (nx >= 0 && nx < width && ny >= 0 && ny < height
                && pixels[ny * width + nx].inside != membership) {
                return true;
            }
        }
    }
    return false;
}

static int save_ppm(
    const char *path,
    const unsigned char *image,
    int width,
    int height
) {
    FILE *file = fopen(path, "wb");
    if (file == NULL) {
        fprintf(stderr, "Could not open output file: %s\n", path);
        return 1;
    }
    if (fprintf(file, "P6\n%d %d\n255\n", width, height) < 0
        || fwrite(image, 3, (size_t)width * height, file)
            != (size_t)width * height) {
        fprintf(stderr, "Could not write output file: %s\n", path);
        fclose(file);
        return 1;
    }
    if (fclose(file) != 0) {
        fprintf(stderr, "Could not finish output file: %s\n", path);
        return 1;
    }
    return 0;
}

int render_fractal_rgb(
    const RenderOptions *options,
    unsigned char *image,
    size_t image_size
) {
    size_t pixel_count = (size_t)options->width * options->height;
    if (image == NULL || image_size < pixel_count * 3) {
        fprintf(stderr, "The RGB output buffer is too small.\n");
        return 1;
    }
    PixelData *pixels = calloc(pixel_count, sizeof(*pixels));
    if (pixels == NULL) {
        fprintf(stderr, "Not enough memory for a %dx%d image.\n",
                options->width, options->height);
        return 1;
    }

    double complex parameter =
        options->parameter_real + I * options->parameter_imag;

    #pragma omp parallel for schedule(dynamic, 2)
    for (int y = 0; y < options->height; ++y) {
        for (int x = 0; x < options->width; ++x) {
            double real = options->xmin
                + (x + 0.5) * (options->xmax - options->xmin) / options->width;
            double imag = options->ymax
                - (y + 0.5) * (options->ymax - options->ymin) / options->height;
            double complex point = real + I * imag;
            double complex pixel_parameter =
                options->kind == FRACTAL_PARAMETER ? point : parameter;
            double complex initial =
                options->kind == FRACTAL_PARAMETER ? 0.0 : point;

            PixelData data;
            if (options->precision == PRECISION_FLOAT) {
                float complex point_float =
                    (float)real + I * (float)imag;
                float complex parameter_float =
                    (float)options->parameter_real
                    + I * (float)options->parameter_imag;
                float complex pixel_parameter_float =
                    options->kind == FRACTAL_PARAMETER
                    ? point_float
                    : parameter_float;
                float complex initial_float =
                    options->kind == FRACTAL_PARAMETER
                    ? 0.0f
                    : point_float;
                data = escape_data_float(
                    initial_float,
                    pixel_parameter_float,
                    options->max_iterations,
                    options->dynamics,
                    options->degree
                );
                pixel_parameter = (double complex)pixel_parameter_float;
            } else {
                data = escape_data(
                    initial,
                    pixel_parameter,
                    options->max_iterations,
                    options->dynamics,
                    options->degree
                );
            }
            if (
                options->kind == FRACTAL_PARAMETER
                && options->mode == MODE_NEWTON
            ) {
                data = newton_multiplier_data(
                    data,
                    pixel_parameter,
                    options->max_period,
                    options->dynamics,
                    options->degree
                );
            } else if (
                options->kind == FRACTAL_PARAMETER
                && options->mode == MODE_LYAPUNOV
            ) {
                data = lyapunov_data(
                    data,
                    pixel_parameter,
                    options->max_iterations,
                    options->dynamics,
                    options->degree
                );
            } else if (
                options->kind == FRACTAL_PARAMETER
                && options->mode == MODE_COMPONENT_PERIOD
            ) {
                data = component_period_data(
                    data,
                    pixel_parameter,
                    options->max_period,
                    options->dynamics,
                    options->degree
                );
            }
            pixels[y * options->width + x] = data;
        }
    }

    #pragma omp parallel for schedule(static)
    for (int y = 0; y < options->height; ++y) {
        for (int x = 0; x < options->width; ++x) {
            PixelData data = pixels[y * options->width + x];
            Rgb color;
            if (options->draw_boundary
                && boundary_pixel(
                    pixels, options->width, options->height, x, y
                )) {
                color = palette_boundary();
            } else if (data.inside) {
                color = palette_interior(
                    options->kind, options->mode, data.metric, data.period
                );
            } else {
                color = palette_exterior(
                    options->kind, options->mode, data.smooth_escape
                );
            }
            size_t offset = ((size_t)y * options->width + x) * 3;
            image[offset] = color.red;
            image[offset + 1] = color.green;
            image[offset + 2] = color.blue;
        }
    }

    free(pixels);
    return 0;
}

int render_fractal(const RenderOptions *options) {
    size_t image_size = (size_t)options->width * options->height * 3;
    unsigned char *image = malloc(image_size);
    if (image == NULL) {
        fprintf(stderr, "Not enough memory for a %dx%d image.\n",
                options->width, options->height);
        return 1;
    }
    int result = render_fractal_rgb(options, image, image_size);
    if (result == 0) {
        result = save_ppm(
            options->output_path, image, options->width, options->height
        );
    }
    free(image);
    return result;
}
