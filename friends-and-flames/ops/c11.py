from lib import *
INK="#3b1d0e"
gx,gy,R=1500,1900,700
ops = strip_all() + [
 {"type":"gradient","name":"sky","x":0,"y":0,"width":3000,"height":3000,"direction":"vertical",
  "stops":[{"offset":0,"color":"#f7e3bd"},{"offset":0.5,"color":"#f2b872"},{"offset":0.75,"color":"#e38a4a"},{"offset":1,"color":"#c4602f"}]},
 {"type":"bottom","target":"sky"},
 {"type":"shape","shape":"ellipse","name":"sun","x":2180,"y":620,"width":420,"height":420,"fill":"#fff1d2","opacity":0.85},
 {"type":"shape","shape":"ellipse","name":"globe","x":gx-R,"y":gy-R,"width":2*R,"height":2*R,"fill":"#2f6f7e","stroke":INK,"stroke_width":14},
]
# grid lines on the globe, clipped to it
grid=[]
for k in (0.35,0.7,1.0):
    w=2*R*k
    grid.append(f"M{gx-w/2:.0f} {gy:.0f} a{w/2:.0f} {R:.0f} 0 1 0 {w:.0f} 0 a{w/2:.0f} {R:.0f} 0 1 0 {-w:.0f} 0 Z")
for f in (-0.6,-0.3,0,0.3,0.6):
    yy=gy+f*R; import math; hw=R*math.sqrt(1-f*f)
    grid.append(f"M{gx-hw:.0f} {yy:.0f} L{gx+hw:.0f} {yy:.0f}")
ops += [{"type":"shape","shape":"path","name":"grid","path":" ".join(grid),"x":0,"y":0,"stroke":"#f4e3c3","stroke_width":10,"opacity":0.7},
        {"type":"clip","target":"grid","base":"globe"}]
# continents: a few organic blobs, clipped
ops += [{"type":"shape","shape":"blob","name":"land1","x":gx-520,"y":gy-560,"width":520,"height":460,"fill":"#7fa36a","seed":4},
        {"type":"shape","shape":"blob","name":"land2","x":gx+90,"y":gy-380,"width":480,"height":620,"fill":"#7fa36a","seed":11},
        {"type":"clip","target":"land1","base":"globe"},{"type":"clip","target":"land2","base":"globe"},
        {"type":"reorder","target":"grid","above":"land2"}]
# flames along the globe's top edge (the world is burning)
fl=[]
import random; random.seed(3)
for a in range(-60,61,15):
    th=math.radians(a-90); x=gx+R*math.cos(th); y=gy+R*math.sin(th)
    h=random.uniform(160,300)*(1-abs(a)/140)
    fl.append(flame_sub(x,y+30,h*0.55,h))
ops += [{"type":"shape","shape":"path","name":"fire","path":" ".join(fl),"x":0,"y":0,"fill":"#ff6a1a","stroke":INK,"stroke_width":10},
        {"type":"reorder","target":"fire","below":"globe"}]
# dunes swallowing the bottom half
d1=f"M0 2050 C 500 1950 900 2150 1500 2100 C 2100 2050 2500 1900 3000 2000 L3000 3000 L0 3000 Z"
d2=f"M0 2400 C 700 2250 1200 2500 1800 2420 C 2400 2340 2700 2450 3000 2380 L3000 3000 L0 3000 Z"
d3=f"M0 2750 C 600 2650 1300 2820 2000 2720 C 2500 2650 2800 2720 3000 2700 L3000 3000 L0 3000 Z"
ops += [{"type":"shape","shape":"path","name":"dune1","path":d1,"x":0,"y":0,"fill":"#d9894a","stroke":INK,"stroke_width":10},
        {"type":"shape","shape":"path","name":"dune2","path":d2,"x":0,"y":0,"fill":"#b8673a","stroke":INK,"stroke_width":10},
        {"type":"shape","shape":"path","name":"dune3","path":d3,"x":0,"y":0,"fill":"#8f4826","stroke":INK,"stroke_width":10}]
# swirl ripples around the sinking globe
rip=" ".join(f"M{gx-R*k:.0f} {2110+40*i:.0f} Q {gx:.0f} {2160+70*i:.0f} {gx+R*k:.0f} {2110+40*i:.0f}" for i,k in enumerate((1.1,1.3,1.55)))
ops += [{"type":"shape","shape":"path","name":"ripples","path":rip,"x":0,"y":0,"stroke":INK,"stroke_width":10,"opacity":0.6}]
ops += [{"type":"look","target":"sky","look":"grain","amount":0.4}]
ops += text("title","Friends and Flames","abril",250,INK,"center",210)
ops += text("lyric","“this world is now in quicksand”","serif-italic",80,INK,"center",520)
ops += text("artist","JEFFREY X GUNTLY","grotesk",62,"#f7e3bd",150,2820,16)
ops += pa(2500,2650,400)
save('c11',ops)
