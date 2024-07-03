import tkinter as tk
from PIL import ImageTk, Image
import os
from subprocess import call


def stop(event):
    with open("./files/params", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    with open("./params2", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    root.destroy()

def reset(event):
    with open("./files/params", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    
    global img
    global panel
    img = ImageTk.PhotoImage(Image.open("./3.png"))
    panel.configure(image=img)
    panel.image = img
    print("Reset complete!")

def reset2(event):
    with open("./files/params2", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    
    call(["./draw_j"])
    global img2
    global panel2
    img2 = ImageTk.PhotoImage(Image.open("./julia.ppm"))
    panel2.configure(image=img2)
    panel2.image = img2

def click2(event):
    x, y = event.x, event.y
    with open("./files/params2", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]

    x1 = xmin + x * (xmax-xmin)/700
    y1 = ymin + y * (ymax-ymin)/700
    with open("inter_file2", "w") as f:
        f.write(f'{x1}\n{y1}')
    print(f'Selecting from z1 = {x1} + i*{y1}')

def drag2(event):
    x, y = event.x, event.y
    with open("./files/params2", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]

    x2 = xmin + x * (xmax-xmin)/700
    y2= ymin + y * (ymax-ymin)/700
    with open("inter_file2", "r") as f:
        x1, y1 = [float(k.strip()) for k in f.readlines()]
    print(f'Selecting to z2 = {x2} + i*{y2}')
    xmin = min(x1, x2)
    xmax = max(x1, x2)
    ymin = min(y1, y2)
    ymax = max(y1, y2)
    with open("./files/params2", "w") as f:
        f.write(f'{xmin}\n{xmax}\n{ymin}\n{ymax}')
    
    # REWRITE THE TRICORN
    call(["./draw_j"])
    global img2
    global panel2
    img2 = ImageTk.PhotoImage(Image.open("./julia.ppm"))
    panel2.configure(image=img2)
    panel2.image = img2

def click(event):
    x, y = event.x, event.y
    with open("./files/params", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]

    x1 = xmin + x * (xmax-xmin)/700
    y1 = ymin + y * (ymax-ymin)/700
    with open("./files/inter_file", "w") as f:
        f.write(f'{x1}\n{y1}')
    print(f'Selecting from c1 = {x1} + i*{y1}')

def drag(event):
    x, y = event.x, event.y
    with open("./files/params", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]

    x2 = xmin + x * (xmax-xmin)/700
    y2= ymin + y * (ymax-ymin)/700
    with open("./files/inter_file", "r") as f:
        x1, y1 = [float(k.strip()) for k in f.readlines()]
    print(f'Selecting to c2 = {x2} + i*{y2}')
    xmin = min(x1, x2)
    xmax = max(x1, x2)
    ymin = min(y1, y2)
    ymax = max(y1, y2)
    with open("./files/params", "w") as f:
        f.write(f'{xmin}\n{xmax}\n{ymin}\n{ymax}')
    
    # REWRITE THE TRICORN
    call(["./draw"])
    global img
    global panel
    img = ImageTk.PhotoImage(Image.open("./3.ppm"))
    panel.configure(image=img)
    panel.image = img
    
def on_click(event):
    with open("./files/params2", "w") as f:
        f.write(f'-2.0\n2.0\n-2.0\n2.0')
    x, y = event.x, event.y
    with open("./files/params", "r") as f:
        xmin, xmax, ymin, ymax = [float(x.strip()) for x in f.readlines()]
    x1 = xmin + x * (xmax-xmin)/700
    y1 = ymin + y * (ymax-ymin)/700
    print(f'c = {x1} + i*{y1}\n')
    with open("./files/coords", "w") as f:
        f.write(f"{x1}\n{y1}")
    call(["./draw_j"])
    global img2
    global panel2
    img2 = ImageTk.PhotoImage(Image.open("./julia.ppm"))
    panel2.configure(image=img2)
    panel2.image = img2

root = tk.Tk()
root.bind("<Escape>", stop)
root.bind("<Button-1>", on_click)
root.bind("<ButtonPress-3>", click)
root.bind("<ButtonRelease-3>", drag)
root.bind("r", reset)


root2 = tk.Toplevel()

root2.bind("<Escape>", stop)
root2.bind("<ButtonPress-3>", click2)
root2.bind("<ButtonRelease-3>", drag2)
root2.bind("r", reset2)


img = ImageTk.PhotoImage(Image.open("./3.png"))
img2 = ImageTk.PhotoImage(Image.open("./julia.ppm"))
panel = tk.Label(root, image = img)
panel.pack(side = "bottom", fill = "both", expand = "yes")
panel2 = tk.Label(root2, image = img2)
panel2.pack(side = "bottom", fill = "both", expand = "yes")
root.mainloop()