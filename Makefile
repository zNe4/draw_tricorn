# Try changing to -O3 to optimize cod
main:
	gcc -lm -o draw_j draw_julia.c
	gcc -lm -o draw_colored draw_tricorn_colored.c
	gcc -lm -o draw_mmap_n draw_tricorn_mmap_n.c
	gcc -lm -o draw_mmap_f draw_tricorn_mmap_f.c
	gcc -lm -o draw_bw draw_tricorn_bw.c
	gcc -lm -o draw_j_bw draw_julia_bw.c