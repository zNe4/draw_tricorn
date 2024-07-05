// Code from https://commons.wikimedia.org/wiki/File:Tricorn.png

#include <stdio.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#define MIN(X, Y) ( (X) < (Y) ? (X) : (Y))

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

static inline void image_poke(unsigned char *image, int width, int i, int j, int bw) {
  int k = (width * j + i) * 3;
  image[k++] = bw;
  image[k++] = bw;
  image[k  ] = bw;
}

int main() {
    unsigned int width = 700, height = 700;  //Resolution;
    int i = 0;                    //Iteration counter;
    const char* filename = "./img/tricorn.ppm";


    double xmin, xmax, ymin, ymax; // Borders of the area to be plotted
    FILE* input_file = fopen("./files/params", "r");
    fscanf(input_file, "%lf", &xmin);
    fscanf(input_file, "%lf", &xmax);
    fscanf(input_file, "%lf", &ymin);
    fscanf(input_file, "%lf", &ymax);
    fclose(input_file);
    int times_iter;
    input_file = fopen("./files/iter_param_tric", "r");
    fscanf(input_file, "%d", &times_iter);
    fclose(input_file);

    unsigned int xpix = 0, ypix = 0;
    float x, y;
    long double Rez, Imz, Rez_new, Imz_new;
    unsigned char* image = malloc(width * height * 3 * sizeof(unsigned char));
    #pragma omp parallel for schedule(dynamic, 1)
    for (ypix = 0; ypix < height; ypix++) {
        for (xpix = 0; xpix < width; xpix++) {
            x = xmin + xpix * (xmax - xmin)/width;
            y = ymin + ypix * (ymax - ymin)/height;
            Rez = x; Imz = y;
            for (i = 0; Rez*Rez + Imz*Imz <= 4; i++) {
                for (int m=0; m<times_iter; m++) {
                    Rez_new = Rez*Rez - Imz*Imz + x;
                    Imz_new = -2*Rez*Imz + y;
                    Rez = Rez_new;
                    Imz = Imz_new;
                }
                if (i == 255) break;
            }
            i = 255 - i;
            image_poke(image, width, xpix, ypix, i);
        }
    }
    image_save_ppm(image, width, height, filename);
    free(image);
    return 0;
}