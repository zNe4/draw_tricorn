#include "palette.h"

#include <math.h>
#include <stddef.h>

static unsigned char channel(double value) {
    if (value < 0.0) {
        return 0;
    }
    if (value > 255.0) {
        return 255;
    }
    return (unsigned char)lround(value);
}

static Rgb mix(Rgb first, Rgb second, double amount) {
    if (amount < 0.0) {
        amount = 0.0;
    } else if (amount > 1.0) {
        amount = 1.0;
    }
    return (Rgb){
        channel(first.red + (second.red - first.red) * amount),
        channel(first.green + (second.green - first.green) * amount),
        channel(first.blue + (second.blue - first.blue) * amount),
    };
}

static Rgb hsv(double hue, double saturation, double value) {
    hue -= floor(hue);
    double sector = hue * 6.0;
    int index = (int)floor(sector);
    double fraction = sector - index;
    double low = value * (1.0 - saturation);
    double falling = value * (1.0 - saturation * fraction);
    double rising = value * (1.0 - saturation * (1.0 - fraction));
    double red;
    double green;
    double blue;

    switch (index % 6) {
        case 0: red = value; green = rising; blue = low; break;
        case 1: red = falling; green = value; blue = low; break;
        case 2: red = low; green = value; blue = rising; break;
        case 3: red = low; green = falling; blue = value; break;
        case 4: red = rising; green = low; blue = value; break;
        default: red = value; green = low; blue = falling; break;
    }
    return (Rgb){
        channel(red * 255.0),
        channel(green * 255.0),
        channel(blue * 255.0),
    };
}

Rgb palette_exterior(
    FractalKind kind,
    RenderMode mode,
    double smooth_escape
) {
    double tone = 1.0 - exp(-smooth_escape / 12.0);
    if (kind == FRACTAL_JULIA && mode == MODE_ESCAPE) {
        /*
         * Closely spaced hue cycles recover the old rainbow character while
         * a dark-to-bright value ramp retains depth near the Julia boundary.
         */
        double hue = 0.68 + smooth_escape * 0.057581917135421046;
        double value = 0.34 + 0.62 * pow(tone, 0.42);
        return hsv(hue, 0.76, value);
    }

    const Rgb charcoal = {15, 22, 28};
    const Rgb blue_gray = {91, 111, 117};
    const Rgb gray = {177, 184, 183};
    tone = pow(tone, 0.38);

    if (mode == MODE_GRAYSCALE) {
        return mix((Rgb){19, 22, 24}, gray, tone);
    }
    return mix(charcoal, blue_gray, tone * 0.88);
}

Rgb palette_interior(
    FractalKind kind,
    RenderMode mode,
    double metric,
    int period
) {
    if (kind == FRACTAL_JULIA) {
        return mode == MODE_GRAYSCALE
            ? (Rgb){2, 2, 2}
            : (Rgb){2, 3, 5};
    }
    if (mode == MODE_GRAYSCALE) {
        return (Rgb){76, 82, 82};
    }
    if (mode == MODE_ESCAPE) {
        return (Rgb){73, 112, 110};
    }
    if (mode == MODE_COMPONENT_PERIOD) {
        static const Rgb period_colors[] = {
            {89, 191, 168},
            {230, 162, 74},
            {155, 125, 219},
            {94, 159, 214},
            {218, 113, 136},
            {159, 196, 90},
            {200, 117, 189},
            {75, 184, 196},
            {217, 121, 75},
            {105, 123, 208},
            {209, 191, 85},
            {213, 143, 168},
        };
        if (period <= 0) {
            return (Rgb){46, 54, 57};
        }
        size_t color_count =
            sizeof(period_colors) / sizeof(period_colors[0]);
        Rgb base = period_colors[(size_t)(period - 1) % color_count];
        Rgb center = mix(base, (Rgb){235, 242, 235}, 0.16);
        Rgb edge = mix(base, (Rgb){31, 39, 43}, 0.24);
        Rgb color = mix(center, edge, pow(metric, 0.72));
        if (((int)floor(metric * 10.0)) % 2 != 0) {
            color = mix(color, (Rgb){31, 39, 43}, 0.055);
        }
        return color;
    }

    /* Brighter blue-green to warm-gold ramps for multiplier information. */
    const Rgb stable = mode == MODE_NEWTON
        ? (Rgb){72, 128, 123}
        : (Rgb){65, 111, 126};
    const Rgb neutral = mode == MODE_NEWTON
        ? (Rgb){222, 176, 104}
        : (Rgb){207, 151, 100};
    Rgb color = mix(stable, neutral, metric);

    if (mode == MODE_NEWTON && period > 0) {
        double period_tint = (double)((period - 1) % 6) / 5.0;
        color = mix(color, (Rgb){126, 137, 128}, 0.18 * period_tint);
    }

    /* A quiet banding makes level sets readable without rainbow saturation. */
    if (((int)floor(metric * 14.0)) % 2 != 0) {
        color = mix(color, (Rgb){28, 36, 39}, 0.09);
    }
    return color;
}

Rgb palette_boundary(void) {
    return (Rgb){8, 12, 15};
}
