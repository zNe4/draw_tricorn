import tkinter as tk
from PIL import ImageTk, Image
import time
from subprocess import call
import os
# from tricorn_logic import *
# from tricorn_gui import *

def redraw_julia():
    global method_draw_julia, J, NAME_JULIA_IMAGE
    print("Redrawing Julia set, this may take a while...")
    call([method_draw_julia[J]])
    global img22, imgContainer2, julia_rect
    canvas2.delete(julia_rect)
    img22 = ImageTk.PhotoImage(Image.open(NAME_JULIA_IMAGE))
    canvas2.itemconfig(imgContainer2, image=img22)
    print("Redraw complete!")

def redraw_tricorn():
    global method_draw_tric, T, NAME_TRICORN_IMAGE
    print("Redrawing tricorn, this may take a while...")
    call([method_draw_tric[T]])
    global img11, imgContainer1, tricorn_rect
    
    canvas1.delete(tricorn_rect)
    img11 = ImageTk.PhotoImage(Image.open(NAME_TRICORN_IMAGE))
    canvas1.itemconfig(imgContainer1, image=img11)
    print("Redraw complete!")

def stop(event):
    with open("./files/params", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    with open("./files/params2", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    with open("./files/coords", "w") as f:
        f.write(f'0.0\n0.0')
    root.destroy()

def reset(event):
    with open("./files/params", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    redraw_tricorn()

def reset2(event):
    with open("./files/params2", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    redraw_julia()

def hold2(event):
    root.bind("<Button-3>", stop_selection)
    root2.bind("<Button-3>", stop_selection)
    global Jx, Jy
    Jx = event.x
    Jy = event.y
    # print(f'Selecting from c1 = {Tx} + i*{Ty}')

def release2(event):
    global Jx, Jy
    x, y = event.x, event.y
    global tricorn_rect2
    if abs(Jx - x) > 2 and abs(Jy - y) > 2:
        ## It's most likely a zoom, redraw the Julia set
        with open("./files/params2", "r") as f:
            xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
        global Jx_new, Jy_new
        Jx = xmin + Jx * (xmax-xmin)/700
        Jy = ymin + Jy * (ymax-ymin)/700
        Jx_new = xmin + x * (xmax-xmin)/700
        Jy_new = ymin + y * (ymax-ymin)/700
        # print(f'Selecting to c2 = {Tx_new} + i*{Ty_new}')
        xmin = min(Jx_new, Jx)
        xmax = max(Jx_new, Jx)
        ymin = min(Jy, Jy_new)
        ymax = max(Jy, Jy_new)
        with open("./files/params2", "w") as f:
            f.write(f'{xmin}\n{xmax}\n{ymin}\n{ymax}')
    
        # Redraw Julia set
        redraw_julia()
    else:
        canvas2.delete(julia_rect)
    root.unbind("<Button-3>")
    root2.unbind("<Button-3>")

def on_move_press2(event):
    with open("./files/params2", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
    global Jx_new, Jy_new, Jx, Jy
    Jx_new = event.x
    Jy_new = event.y
    xmin = min(Jx_new, Jx)
    xmax = max(Jx_new, Jx)
    ymin = min(Jy, Jy_new)
    ymax = max(Jy, Jy_new)
    ## Just draw a rectangle to show zoom area
    global julia_rect
    canvas2.delete(julia_rect)
    julia_rect = canvas2.create_rectangle(xmin, ymin, xmax, ymax, outline='#482C3D', width=2)

def hold(event):
    root.bind("<Button-3>", stop_selection)
    root2.bind("<Button-3>", stop_selection)
    global Tx, Ty
    Tx = event.x
    Ty = event.y
    # print(f'Selecting from c1 = {Tx} + i*{Ty}')

def release(event):
    global Tx, Ty
    x, y = event.x, event.y
    if abs(Tx - x) <= 2 or abs(Ty - y) <= 2:
        ## Probably just a click, redraw Julia set
        with open("./files/params2", "w") as f:
            f.write(f'-2.0\n2.0\n-2.0\n2.0')
        with open("./files/params", "r") as f:
            xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
        Tx = xmin + Tx * (xmax-xmin)/700
        Ty = ymin + Ty * (ymax-ymin)/700
        ## Remember to write coords
        with open("./files/coords", "w") as f:
            f.write(f'{Tx}\n{Ty}')
        global tricorn_rect
        canvas1.delete(tricorn_rect)
        redraw_julia()
    else:
        ## It's most likely a zoom, redraw the tricorn
        with open("./files/params", "r") as f:
            xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
        global Tx_new, Ty_new
        Tx = xmin + Tx * (xmax-xmin)/700
        Ty = ymin + Ty * (ymax-ymin)/700
        Tx_new = xmin + x * (xmax-xmin)/700
        Ty_new = ymin + y * (ymax-ymin)/700
        # print(f'Selecting to c2 = {Tx_new} + i*{Ty_new}')
        xmin = min(Tx_new, Tx)
        xmax = max(Tx_new, Tx)
        ymin = min(Ty, Ty_new)
        ymax = max(Ty, Ty_new)
        with open("./files/params", "w") as f:
            f.write(f'{xmin}\n{xmax}\n{ymin}\n{ymax}')
        redraw_tricorn()
    root.unbind("<Button-3>")
    root2.unbind("<Button-3>")

def on_move_press(event):
    global tricorn_rect
    with open("./files/params", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
    global Tx_new, Ty_new, Tx, Ty
    Tx_new = event.x
    Ty_new = event.y
    xmin = min(Tx_new, Tx)
    xmax = max(Tx_new, Tx)
    ymin = min(Ty, Ty_new)
    ymax = max(Ty, Ty_new)
    ## Just draw a rectangle to show zoom area
    canvas1.delete(tricorn_rect)
    tricorn_rect = canvas1.create_rectangle(xmin, ymin, xmax, ymax, outline='#482C3D', width=2)

def bind_again(event):
    root.bind("<ButtonPress-1>", hold)
    root.bind("<ButtonRelease-1>", release)
    root.bind("<B1-Motion>", on_move_press)
    root2.bind("<ButtonPress-1>", hold2)
    root2.bind("<ButtonRelease-1>", release2)
    root2.bind("<B1-Motion>", on_move_press2)


def stop_selection(event):
    print("Stopping selection...")

    root.unbind("<ButtonRelease-1>")
    root.unbind("<ButtonPress-1>")
    root.unbind("<B1-Motion>")

    root2.unbind("<ButtonRelease-1>")
    root2.unbind("<ButtonPress-1>")
    root2.unbind("<B1-Motion>")

    root.bind("<ButtonRelease-1>", bind_again)
    root2.bind("<ButtonRelease-1>", bind_again)

    global tricorn_rect, julia_rect
    canvas1.delete(tricorn_rect)
    canvas2.delete(julia_rect)


def change_newton(event):
    global T
    T=0
    redraw_tricorn()

def change_lyapunov(event):
    global T
    T=1
    redraw_tricorn()

def change_grayscale(event):
    global T
    T=2
    redraw_tricorn()

def change_colored(event):
    global T
    T=3
    redraw_tricorn()

def num_handler_tricorn(event):
    n = int(event.char)
    if 1 <= n <= 4:
        with open("./files/iter_param_tric", "w") as f:
            f.write(str(n))
        redraw_tricorn()

def change_grayscale_j(event):
    global J
    J=1
    redraw_julia()

def change_colored_j(event):
    global J
    J=0
    redraw_julia()

def num_handler_julia(event):
    n = int(event.char)
    if 1 <= n <= 4:
        with open("./files/iter_param_j", "w") as f:
            f.write(str(n))
        redraw_julia()
### Boring stuff
root = tk.Tk()
root.bind("<Escape>", stop)
root.bind("<ButtonPress-1>", hold)
root.bind("<ButtonRelease-1>", release)
root.bind("<B1-Motion>", on_move_press)

root.bind("r", reset)
root.bind("b", change_grayscale)
root.bind("c", change_colored)
root.bind("n", change_newton)
root.bind("l", change_lyapunov)
for i in range(10):
    root.bind(str(i), num_handler_tricorn)

w = 700
h = 700
ws = root.winfo_screenwidth()
hs = root.winfo_screenheight()

x = (ws/2) - (w/2) - 355
y = (hs/2) - (h/2)
root.geometry('%dx%d+%d+%d' % (w, h, x, y))
canvas1 = tk.Canvas(height=700, width=700)
canvas1.pack()
if not os.path.exists("./img/tricorn.jpg"):
    print(f'Error: file does not exists: img/tricorn.jpg. Try downloading it from the git repository or using imgmagick to create a new one.')
    exit()
img1 = ImageTk.PhotoImage(Image.open("./img/tricorn.jpg").convert('RGB'))
imgContainer1 = canvas1.create_image(0, 0, image=img1, anchor='nw')
tricorn_rect = 0



root2 = tk.Toplevel()
x = (ws/2) - (w/2) + 355
root2.geometry('%dx%d+%d+%d' % (w, h, x, y))

root2.bind("<Escape>", stop)
root2.bind("<ButtonPress-1>", hold2)
root2.bind("<ButtonRelease-1>", release2)
root2.bind("<B1-Motion>", on_move_press2)


root2.bind("r", reset2)
root2.bind("b", change_grayscale_j)
root2.bind("c", change_colored_j)
for i in range(10):
    root2.bind(str(i), num_handler_julia)

canvas2 = tk.Canvas(root2, height=700, width=700)
canvas2.pack()
if not os.path.exists("./img/julia.jpg"):
    print(f'Error: file does not exists: img/julia.jpg. Try downloading it from the git repository or using imgmagick to create a new one.')
    exit()
img2 = ImageTk.PhotoImage(Image.open("./img/julia.jpg").convert('RGB'))
imgContainer2 = canvas2.create_image(0, 0, image=img2, anchor='nw')
julia_rect = 0
# panel = tk.Label(root, image = img)
# panel.pack(side = "bottom", fill = "both", expand = "yes")
# panel2 = tk.Label(root2, image = img2)
# panel2.pack(side = "bottom", fill = "both", expand = "yes")
###

# Methods of drawing
method_draw_tric = ["./draw_mmap_n", "./draw_mmap_f", "./draw_bw", "./draw_colored"] # Types of drawing for the tricorn
T = 0
NAME_TRICORN_IMAGE = "./img/tricorn.ppm"
method_draw_julia = ["./draw_j", "./draw_j_bw"] # Types of drawing for the tricorn
J = 0
for f in method_draw_julia + method_draw_tric:
    if not os.path.exists(f):
        print(f'Error: File does not exist: {f}. Try running make again.')
        exit()
NAME_JULIA_IMAGE = "./img/julia.ppm"

with open("./files/params", "w") as f:
    f.write(f'-2.0\n2.0\n-2.0\n2.0')
with open("./files/params2", "w") as f:
    f.write(f'-2.0\n2.0\n-2.0\n2.0')
Tx = Ty = 0.0
Tx_new = Ty_new = 0.0
Txmin = Tymin = Jxmin = Jymin = -2.0
Txmax = Tymax = Jxmax = Jymax = 2.0

root.mainloop()
