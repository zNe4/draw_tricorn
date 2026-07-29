#ifndef PALETTE_H
#define PALETTE_H

#include "fractal.h"

typedef struct {
    unsigned char red;
    unsigned char green;
    unsigned char blue;
} Rgb;

Rgb palette_exterior(
    FractalKind kind,
    RenderMode mode,
    double smooth_escape
);
Rgb palette_interior(
    FractalKind kind,
    RenderMode mode,
    double metric,
    int period
);
Rgb palette_boundary(void);

#endif
