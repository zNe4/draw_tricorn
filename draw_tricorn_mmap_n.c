/*
  Código adaptado de https://commons.wikimedia.org/wiki/File:Mandelbrot_set_-_multiplier_map.png.
  
  to compile use
    gcc draw_tricorn.c -lm -o draw
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
  if (v == 0) {*r = 0; *g = 0; *b = 0;}
  if (s == 0) { *r = *g = *b =  0.0; } else {
    h = 6 * (h - floor(h));
    int ii = i = floor(h);
    f = h - i;
    p = v * (1 - s);
    q = v * (1 - (s * f));
    t = v * (1 - (s * (1 - f)));
    switch(ii) {
    case 0: *r = 2 * v; *g = 1.5 * t; *b = p; break;
    case 1: *r = 0.5 * q; *g = 1.5 * v; *b = 2 * p; break;
    case 2: *r = 2 * p; *g = 1.5 * v; *b = t; break;
    case 3: *r = 0.5 * p; *g = 1.5 * q; *b = 2 * v; break;
    case 4: *r = 2 * t; *g = 1.5 * p; *b = v; break;
    default:*r = 0.5 * v; *g = 1.5 * p; *b = 2 * q; break;
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

static inline void color_tricorn(unsigned char *image, int width, int i, int j, int period, double intRadius, int k) {
  double r, g, b;
  colour_hsv_to_rgb(k * colour_modulus, 0.5, 1.0, &r, &g, &b);
  int ir, ig, ib;
  colour_to_bytes(r, g, b, &ir, &ig, &ib);
  
  //generate internal grid 
  if (intRadius<1.0){
    int rMax=15; /* number of color segments */
    double m=rMax * intRadius;
    int im=(int)m; // integer of m

    // int aMax=15; /* number of color segments */
    // double k2=aMax; // * intAngle;
    // int ik =(int)k2; // integer of m
    
    if ( im % 2 ) {ir -=40; }
    // if ( ik % 2 ) {ig -=40; } // for intAngle
   }
  image_poke(image, width, i, j, ir, ig, ib);
}

/* newton function : N(z) = z - (fp(z)-z)/f'(z)) */

complex double N( complex double c, complex double zn , int pMax, double er2){
  complex double z = zn;
  complex double d = 1.0; /* d = first derivative with respect to z */
  int p;
  for (p=0; p < pMax; p++){ // find periodic point of period 2p
    d = (4.0*z*z*z+4*z*conj(c))*d;
    z = (z*z + conj(c))*(z*z + conj(c)) + c;
  }
  z = zn - (z - zn)/(d -1.0);
  return z;
}

complex double GivePeriodic(complex double c, complex double z0, int period, double eps2, double er2){
  complex double z = z0;
  complex double zPrev = z0; // previous value of z
  int n ; // iteration
  const int nMax = 128;

  for (n=0; n<nMax; n++) {
    z = N(c, z, period, er2);
    if (cabs2(z - zPrev)< eps2) break;
  }
  return z;
}

complex double ApproximateMultiplierMap(complex double c, int period, double eps2, double er2){
     
    complex double z;  // variable z 
    complex double zp ; // periodic point 
    complex double zcr = c;
    complex double d = 1.0;
    int p;
    zp =  GivePeriodic(c, zcr, period,  eps2, er2);
    if ( cabs2(zp)<er2) {
      z = zp;
      for (p=0; p < period; p++){
        d = (4.0*z*z*z+4*z*conj(c))*d;
        z = (z*z + conj(c))*(z*z + conj(c)) + c;
      }
    } else d = 1000000000;

    return sqrt(cabs(d));
}

// double GiveTurn( double complex z){
//   double t;

//   t =  carg(z);
//   t /= 2*pi; // now in turns
//   if (t<0.0) t += 1.0; // map from (-1/2,1/2] to [0, 1) 
//   return (t);
// }

static inline void render(unsigned char *image,  int pMax, int width, int height, float xmin, float ymin, float xmax, float ymax) {

  #pragma omp parallel for schedule(dynamic, 1)
    for (int j = 0; j < height; ++j) {
      for (int i = 0; i < width; ++i) {
        double x = xmin + i * (xmax - xmin)/width;
        double y = ymin + j * (ymax - ymin)/height;
        complex double c = x + I * y;

        // check if its inside
        complex double z = 0.0;
        bool is_inside = true;
        int k=0;
        for (k=0; k<UCHAR_MAX; k++) {
          z = (z * z + conj(c)) * (z * z + conj(c)) + c;
          if (cabs2(z) > 4) {is_inside = false; break;}
        }
        // done checking
        // k for channel h;

        if (!is_inside) {color_tricorn(image, width, i, j, 0, 0, UCHAR_MAX - k); continue;}
        complex double w;
        double iRadius;
        int period = 0;
        // find period and w 
        for (int p = 1; p < pMax; p++){
          iRadius =  ApproximateMultiplierMap(c,p, EPS2, ER2);
          if ( iRadius <= 1.0) {
            // iAngle = GiveTurn(w);
            period=p;
            break;
          }
        }
        color_tricorn(image, width, i, j, period, iRadius, UCHAR_MAX - k); // Can add iAngle
      }
    }
}

int main() {
  int PeriodMax = 20;
  int width = 700;
  int height = 700;
  //
  //
      float xmin, xmax, ymin, ymax; // Borders of the area to be plotted
      FILE* input_file = fopen("./files/params", "r");
      fscanf(input_file, "%f", &xmin);
      fscanf(input_file, "%f", &xmax);
      fscanf(input_file, "%f", &ymin);
      fscanf(input_file, "%f", &ymax);
      fclose(input_file);
  //
  //
  const char *filename = "tricorn.ppm";
  unsigned char *image = image_new(width, height);
  render(image,  PeriodMax, width, height, xmin, ymin, xmax, ymax);
  image_save_ppm(image, width, height, filename);
  image_delete(image);
  return 0;
}