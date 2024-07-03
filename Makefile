# Try changing to -O3 to optimize cod
main:
	gcc -lm -o draw_j draw_julia.c
	gcc -lm -o draw_colored draw_tricorn_colored.c
	gcc -lm -o draw_mmap draw_tricorn_mmap.c
	gcc -lm -o draw_bw draw_tricorn_bw.c