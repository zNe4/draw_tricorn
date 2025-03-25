# draw_tricorn
C program with Python GUI "wrapper" for drawing fractals (Multicorn, Mandelbrot, Julia) adapted from the internet.

Most of the code was adapted from https://commons.wikimedia.org/wiki/File:Mandelbrot_set_-_multiplier_map.png.

The python code is not pretty since I'm not so familiar with making GUIs.

# Requirements
Tested with python 3.13.2 and gcc 14.2.1 on arch linux.

# Usage
Caution: The python funcion subprocess.call() is used in order to run the c code in the python GUI, which may be unsafe.

To use the program just execute `make` to compile the program and then run `python draw.py` inside the containing folder.

- To redraw a Julia set for a c value, left click on any part of the the image of the tricorn.
- To zoom into an image, left click and drag on an area of the image.
- To stop the zoom area selection, press right click while selecting zoom area.
- To reset an image press `r` while focusing on the window containing the image.
- To stop the program press `ESC` while focusing any window spawned by the program.
#### While focusing the window containing the Tricorn
- Use the keys `b`, `c`, `n` or `l` to change between greyscale + escape time, colored + escape time, Newton multiplier map + escape time or Lyapunov exponents + escape time types of drawing.
- Use the keys `1-4` to adjust number of max iterations.
#### While focusing the window containing the Julia set
- Use the keys `b` and `c` to change between greyscale + escape time and colored + escape time type of drawing.
- Use the keys `1-4` to adjust number of iterations.
## To do
- ~~use the `l` key to change to floquet multiplier map drawing of the tricorn.~~ (done, may need to improve the code)
- Add indicator for c values in the tricorn and for the z values in the julia set
- Add modes for multibrots and multicorns.
- Use the `s` key to save image/parameters
- Make a pretty GUI that also has buttons to interact with the program.
- Refactor and reorganize the code.
- Remove spooky use of call in draw.py by writing an actual wrapper.
