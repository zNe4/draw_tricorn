# draw_tricorn
C program with Python GUI wrapper for drawing fractals (Multicorn, Mandelbrot, Julia) adapted from the internet.

Most code was adapted from https://commons.wikimedia.org/wiki/File:Mandelbrot_set_-_multiplier_map.png.

The python code is not fully optimized since I'm not so familiar with making GUIs.

# Usage
To use the program just execute `make && python draw.py` inside the containing folder.

Caution: The python funcion subprocess.call() is used in order to run the c code in the python GUI, which may be unsafe.

- To redraw a Julia set, left click on the image of the tricorn.
- To zoom into an image, use the right click draw on an area of the image.
- To reset an image press `r` while focusing on the window containing the image.
- To stop the program press `ESC` while focusing any window.
#### While focusing the window containing the Tricorn
- Use the keys `b`, `c` and `n` to change between greyscale + escape time, colored + escape time and newton multiplier map types of drawing.
- Use the keys `1-4` to adjust number of max iterations. (Implemented but doesn't seem to add detail to the image)
#### While focusing the window containing the Julia set
- Use the keys `1-4` to adjust number of iterations.
- Use the keys `b` and `c` to change between greyscale + escape time and colored + escape time type of drawing.
## To do
- Use the 'f' key to change to floquet multiplier map drawing of the tricorn.
- Make a pretty GUI that adds easier user input and has buttons to interact with the program.
- Refactor and reorganize the code.
- Remove spooky use of call in draw.py