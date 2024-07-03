// Code from https://commons.wikimedia.org/wiki/File:Tricorn.png

#include <stdio.h>
#include <limits.h>


int main() {
    unsigned int resx = 1000, resy = 1000;  //Resolution;
    unsigned int i = 0;                    //Iteration counter;


      float xmin, xmax, ymin, ymax; // Borders of the area to be plotted
      FILE* input_file = fopen("./files/params", "r");
      fscanf(input_file, "%f", &xmin);
      fscanf(input_file, "%f", &xmax);
      fscanf(input_file, "%f", &ymin);
      fscanf(input_file, "%f", &ymax);
      fclose(input_file);
      int render_zoom;
      input_file = fopen("./files/zoom_param", "r");
    fscanf(input_file, "%d", &render_zoom);


    unsigned int xpix = 0, ypix = 0;        //Column and row counters;
    float x, y;                             //Coordinates;
    long double Rez, Imz, Rez_new, Imz_new; //Real and imaginary parts.
    FILE *f;

    f = fopen("tricorn.pgm", "w");
    fprintf(f, "P2\n%d %d\n%d\n", resx, resy, UCHAR_MAX);
    for (ypix = 0; ypix < resy; ypix++) {
        for (xpix = 0; xpix < resx; xpix++) {
            x = xmin + xpix * (xmax - xmin)/resx;
            y = ymin + ypix * (ymax - ymin)/resy;
            Rez = x; Imz = y;
            for (i = 0; Rez*Rez + Imz*Imz <= 4; i++) {
                Rez_new = Rez*Rez - Imz*Imz + x;
                Imz_new = -2*Rez*Imz + y;
                Rez = Rez_new;
                Imz = Imz_new;
                if (i == render_zoom * UCHAR_MAX) break;
            }
            fprintf(f, "%d ", UCHAR_MAX - i / 4);
        }
        fprintf(f, "\n");
    }
}