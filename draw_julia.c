/*
  Código adaptado de https://commons.wikimedia.org/wiki/File:Mandelbrot_set_-_multiplier_map.png.
  
  to compile use
    gcc draw_julia.c -lm -o draw_j
*/

#include <complex.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

const double pi = 3.141592653589793;
const double infinity = 1.0 / 0.0;
const double colour_modulus = 5.7581917135421046e-2; // (1.0 + 1.0 / (phi * phi)) / 24.0;
const double ER2 = 2.0 * 2.0; // ER*ER
const double EPS2 = 1e-100 * 1e-100; // EPS*EPS

static inline double cabs2(complex double z) {
  return creal(z) * creal(z) + cimag(z) * cimag(z);
}

static inline unsigned char *image_new(int width, int height) {
  return malloc(width * height * 3);
}

static inline void image_delete(unsigned char *image) {
  free(image);
}

static inline void image_save_ppm(unsigned char *image, int width, int height, const char *filename) {
  FILE *f = fopen(filename, "wb");
  if (f) {
    fprintf(f, "P6\n%d %d\n255\n", width, height);
    fwrite(image, width * height * 3, 1, f);
    fclose(f);
  } else {
    fprintf(stderr, "ERROR saving `%s'\n", filename);
  }
}

static inline void image_poke(unsigned char *image, int width, int i, int j, int r, int g, int b) {
  int k = (width * j + i) * 3;
  image[k++] = r;
  image[k++] = g;
  image[k  ] = b;
}

static inline void colour_hsv_to_rgb(double h, double s, double v, double *r, double *g, double *b) {
  double i, f, p, q, t;
  if (s == 0) { *r = *g = *b =  0.0; } else {
    h = 6 * (h - floor(h));
    int ii = i = floor(h);
    f = h - i;
    p = v * (1 - s);
    q = v * (1 - (s * f));
    t = v * (1 - (s * (1 - f)));
    switch(ii) {
    case 0: *r = v; *g = t; *b = p; break;
    case 1: *r = q; *g = v; *b = p; break;
    case 2: *r = p; *g = v; *b = t; break;
    case 3: *r = p; *g = q; *b = v; break;
    case 4: *r = t; *g = p; *b = v; break;
    default:*r = v; *g = p; *b = q; break;
    }
  }
}

static inline void colour_to_bytes(double r, double g, double b, int *r_out, int *g_out, int *b_out) {
  *r_out = fmin(fmax(255 * r, 0), 255);
  *g_out = fmin(fmax(255 * g, 0), 255);
  *b_out = fmin(fmax(255 * b, 0), 255);
}

// static inline void color_directly(unsigned char *image, int width, int i, int j, int period, double intRadius) {
//   double r, g, b
// }

static inline void color_tricorn(unsigned char *image, int width, int i, int j, int k) {
  double r, g, b;
  if (k == 0) {
	  image_poke(image, width, i, j, 0, 0, 0);
  } else{
    colour_hsv_to_rgb(k * colour_modulus, 0.5, 1.0, &r, &g, &b);
    int ir, ig, ib;
    colour_to_bytes(r, g, b, &ir, &ig, &ib);
    image_poke(image, width, i, j, ir, ig, ib);
  }
}

static inline void render(unsigned char *image, int width, int height, double xmin, double ymin, double xmax, double ymax, complex double c) {

  #pragma omp parallel for schedule(dynamic, 1)
    for (int j = 0; j < height; ++j) {
      for (int i = 0; i < width; ++i) {
        double x = xmin + i * (xmax - xmin)/width;
        double y = ymin + j * (ymax - ymin)/height;
        complex double z = x + I * y;

        // check if its inside
        // complex double c = -1.07+0.12*I;
        bool is_inside = true;
        int k=0;
        for (k=0; k<UCHAR_MAX; k++) {
          z = conj(z*z) + c;
          if (cabs2(z) > 4) {is_inside = false; break;}
        }
        // done checking
        // k for channel h;
        color_tricorn(image, width, i, j, UCHAR_MAX - k); // Can add iAngle
      }
    }
}

int main() {
  int PeriodMax = 20;
  int width = 700;
  int height = 700;
  //
  //
      double xmin, xmax, ymin, ymax; // Borders of the area to be plotted
      FILE* input_file = fopen("./files/params2", "r");
      fscanf(input_file, "%lf", &xmin);
      fscanf(input_file, "%lf", &xmax);
      fscanf(input_file, "%lf", &ymin);
      fscanf(input_file, "%lf", &ymax);
      fclose(input_file);
      double x, y;
      input_file = fopen("./files/coords", "r");
      fscanf(input_file, "%lf", &x);
      fscanf(input_file, "%lf", &y);
      fclose(input_file);
  //
  //
  const char *filename = "julia.ppm";
  unsigned char *image = image_new(width, height);
  render(image, width, height, xmin, ymin, xmax, ymax, x+I*y);
  image_save_ppm(image, width, height, filename);
  image_delete(image);
  printf("done!\n");
  return 0;
}