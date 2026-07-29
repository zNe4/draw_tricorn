#include "fractal.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(FILE *stream) {
    fprintf(stream,
        "Usage: fractal-renderer [options]\n"
        "  --kind parameter|julia        Plane to render\n"
        "  --dynamics holomorphic|antiholomorphic\n"
        "  --degree N                     Unicritical degree (2..32)\n"
        "  --mode escape|grayscale|newton|lyapunov|period\n"
        "  --xmin N --xmax N --ymin N --ymax N\n"
        "  --cx N --cy N                 Julia parameter\n"
        "  --iterations N                Maximum orbit iterations\n"
        "  --max-period N                Largest component period to test\n"
        "  --precision float|double      Numeric escape kernel\n"
        "  --width N --height N\n"
        "  --boundary 0|1\n"
        "  --output PATH\n");
}

static const char *next_value(int argc, char **argv, int *index) {
    if (*index + 1 >= argc) {
        fprintf(stderr, "Missing value after %s.\n", argv[*index]);
        exit(2);
    }
    ++*index;
    return argv[*index];
}

static double parse_double(const char *text, const char *name) {
    char *end = NULL;
    errno = 0;
    double value = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0') {
        fprintf(stderr, "Invalid number for %s: %s\n", name, text);
        exit(2);
    }
    return value;
}

static int parse_int(const char *text, const char *name, int minimum) {
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0'
        || value < minimum || value > INT_MAX) {
        fprintf(stderr, "Invalid integer for %s: %s\n", name, text);
        exit(2);
    }
    return (int)value;
}

int main(int argc, char **argv) {
    RenderOptions options = {
        .kind = FRACTAL_PARAMETER,
        .dynamics = DYNAMICS_ANTIHOL,
        .mode = MODE_ESCAPE,
        .degree = 2,
        .width = 700,
        .height = 700,
        .max_iterations = 512,
        .max_period = 20,
        .draw_boundary = false,
        .precision = PRECISION_DOUBLE,
        .xmin = -2.0,
        .xmax = 2.0,
        .ymin = -2.0,
        .ymax = 2.0,
        .parameter_real = 0.0,
        .parameter_imag = 0.0,
        .output_path = "output.ppm",
    };

    for (int index = 1; index < argc; ++index) {
        const char *argument = argv[index];
        if (strcmp(argument, "--help") == 0) {
            usage(stdout);
            return 0;
        } else if (strcmp(argument, "--kind") == 0) {
            const char *value = next_value(argc, argv, &index);
            if (
                strcmp(value, "parameter") == 0
                || strcmp(value, "tricorn") == 0
            ) {
                options.kind = FRACTAL_PARAMETER;
            } else if (strcmp(value, "julia") == 0) {
                options.kind = FRACTAL_JULIA;
            } else {
                fprintf(stderr, "Unknown fractal kind: %s\n", value);
                return 2;
            }
        } else if (strcmp(argument, "--dynamics") == 0) {
            const char *value = next_value(argc, argv, &index);
            if (strcmp(value, "holomorphic") == 0) {
                options.dynamics = DYNAMICS_HOLOMORPHIC;
            } else if (strcmp(value, "antiholomorphic") == 0) {
                options.dynamics = DYNAMICS_ANTIHOL;
            } else {
                fprintf(stderr, "Unknown dynamics kind: %s\n", value);
                return 2;
            }
        } else if (strcmp(argument, "--degree") == 0) {
            options.degree =
                parse_int(next_value(argc, argv, &index), "degree", 2);
            if (options.degree > 32) {
                fprintf(stderr, "degree must be at most 32.\n");
                return 2;
            }
        } else if (strcmp(argument, "--mode") == 0) {
            const char *value = next_value(argc, argv, &index);
            if (strcmp(value, "escape") == 0) {
                options.mode = MODE_ESCAPE;
            } else if (strcmp(value, "grayscale") == 0) {
                options.mode = MODE_GRAYSCALE;
            } else if (strcmp(value, "newton") == 0) {
                options.mode = MODE_NEWTON;
            } else if (strcmp(value, "lyapunov") == 0) {
                options.mode = MODE_LYAPUNOV;
            } else if (strcmp(value, "period") == 0) {
                options.mode = MODE_COMPONENT_PERIOD;
            } else {
                fprintf(stderr, "Unknown rendering mode: %s\n", value);
                return 2;
            }
        } else if (strcmp(argument, "--xmin") == 0) {
            options.xmin = parse_double(next_value(argc, argv, &index), "xmin");
        } else if (strcmp(argument, "--xmax") == 0) {
            options.xmax = parse_double(next_value(argc, argv, &index), "xmax");
        } else if (strcmp(argument, "--ymin") == 0) {
            options.ymin = parse_double(next_value(argc, argv, &index), "ymin");
        } else if (strcmp(argument, "--ymax") == 0) {
            options.ymax = parse_double(next_value(argc, argv, &index), "ymax");
        } else if (strcmp(argument, "--cx") == 0) {
            options.parameter_real =
                parse_double(next_value(argc, argv, &index), "cx");
        } else if (strcmp(argument, "--cy") == 0) {
            options.parameter_imag =
                parse_double(next_value(argc, argv, &index), "cy");
        } else if (strcmp(argument, "--iterations") == 0) {
            options.max_iterations =
                parse_int(next_value(argc, argv, &index), "iterations", 8);
        } else if (strcmp(argument, "--max-period") == 0) {
            options.max_period =
                parse_int(next_value(argc, argv, &index), "max-period", 1);
            if (options.max_period > 128) {
                fprintf(stderr, "max-period must be at most 128.\n");
                return 2;
            }
        } else if (strcmp(argument, "--precision") == 0) {
            const char *value = next_value(argc, argv, &index);
            if (strcmp(value, "float") == 0) {
                options.precision = PRECISION_FLOAT;
            } else if (strcmp(value, "double") == 0) {
                options.precision = PRECISION_DOUBLE;
            } else {
                fprintf(stderr, "Unknown precision: %s\n", value);
                return 2;
            }
        } else if (strcmp(argument, "--width") == 0) {
            options.width =
                parse_int(next_value(argc, argv, &index), "width", 16);
        } else if (strcmp(argument, "--height") == 0) {
            options.height =
                parse_int(next_value(argc, argv, &index), "height", 16);
        } else if (strcmp(argument, "--boundary") == 0) {
            options.draw_boundary =
                parse_int(next_value(argc, argv, &index), "boundary", 0) != 0;
        } else if (strcmp(argument, "--output") == 0) {
            options.output_path = next_value(argc, argv, &index);
        } else {
            fprintf(stderr, "Unknown option: %s\n", argument);
            usage(stderr);
            return 2;
        }
    }

    if (options.xmin >= options.xmax || options.ymin >= options.ymax) {
        fprintf(stderr, "Each view minimum must be smaller than its maximum.\n");
        return 2;
    }
    if (options.kind == FRACTAL_JULIA
        && (
            options.mode == MODE_NEWTON
            || options.mode == MODE_LYAPUNOV
            || options.mode == MODE_COMPONENT_PERIOD
        )) {
        fprintf(stderr, "Multiplier modes apply to the parameter plane only.\n");
        return 2;
    }
    return render_fractal(&options);
}
