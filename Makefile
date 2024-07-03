# Try changing to -O3 to optimize code

gcc draw_julia.c -lm -o draw_j
gcc draw_tricorn_colored.c -lm -o draw_j
gcc draw_tricorn_mmap.c -lm -o draw_j
gcc draw_tricorn_bw.c -lm -o draw_j