#ifndef FRACTAL_H
#define FRACTAL_H

#include <stdbool.h>
#include <stddef.h>

typedef enum {
    FRACTAL_PARAMETER,
    FRACTAL_JULIA
} FractalKind;

typedef enum {
    DYNAMICS_HOLOMORPHIC,
    DYNAMICS_ANTIHOL
} DynamicsKind;

typedef enum {
    MODE_ESCAPE,
    MODE_GRAYSCALE,
    MODE_NEWTON,
    MODE_LYAPUNOV,
    MODE_COMPONENT_PERIOD
} RenderMode;

typedef enum {
    PRECISION_FLOAT,
    PRECISION_DOUBLE
} NumericPrecision;

typedef struct {
    FractalKind kind;
    DynamicsKind dynamics;
    RenderMode mode;
    int degree;
    int width;
    int height;
    int max_iterations;
    int max_period;
    bool draw_boundary;
    NumericPrecision precision;
    double xmin;
    double xmax;
    double ymin;
    double ymax;
    double parameter_real;
    double parameter_imag;
    const char *output_path;
} RenderOptions;

int render_fractal_rgb(
    const RenderOptions *options,
    unsigned char *image,
    size_t image_size
);
int render_fractal(const RenderOptions *options);

#endif
