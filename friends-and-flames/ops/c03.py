from lib import *
import random, math
random.seed(5)
cx, cy = 1832, 520
d=[]
for i in range(70):
    a = math.radians(random.uniform(-175, -5)) if random.random()<0.85 else math.radians(random.uniform(0,180))
    r0 = random.uniform(90, 520); L = random.uniform(25, 120)*(1.4 if r0>300 else 1)
    x1,y1 = cx+r0*math.cos(a), cy+r0*math.sin(a)
    x2,y2 = cx+(r0+L)*math.cos(a), cy+(r0+L)*math.sin(a)
    d.append(f"M{x1:.0f} {y1:.0f} L{x2:.0f} {y2:.0f}")
dots=[]
for i in range(60):
    a=random.uniform(0,2*math.pi); r=random.uniform(120,900)
    x,y=cx+r*math.cos(a), cy+r*math.sin(a)*0.8-150; s=random.uniform(3,9)
    dots.append(f"M{x-s:.0f} {y:.0f} a{s:.0f} {s:.0f} 0 1 0 {2*s:.0f} 0 a{s:.0f} {s:.0f} 0 1 0 {-2*s:.0f} 0 Z")
smoke=[]
for k,(dx,amp) in enumerate([(0,60),(-40,90),(50,120)]):
    pts=f"M{cx+dx} 120 C {cx+dx+amp} -40 {cx+dx-amp} -200 {cx+dx+amp*0.5} -400"
    smoke.append(pts)
ops=[{"type":"remove","targets":["title","artist"]},
 {"type":"gradient","name":"bg","x":-500,"y":-1100,"width":4000,"height":4400,"direction":"radial","falloff":"smooth",
  "stops":[{"offset":0,"color":"#163a40"},{"offset":0.45,"color":"#0a1d22"},{"offset":1,"color":"#020607"}]},
 {"type":"bottom","target":"bg"},
 {"type":"gradient","target":"handlight","stops":[{"offset":0,"color":"#fff0d8"},{"offset":0.12,"color":"#ffae60"},{"offset":0.3,"color":"#b0582a"},{"offset":0.55,"color":"#2a4a50"},{"offset":1,"color":"#06181c"}]},
 {"type":"shape","shape":"path","name":"sparks","path":" ".join(d),"x":0,"y":0,"stroke":"#ffc46b","stroke_width":5,"line_cap":"round"},
 {"type":"layer-style","target":"sparks","name":"outer-glow","settings":{"color":"#ff7a1a","blur":18,"opacity":1}},
 {"type":"shape","shape":"path","name":"embers","path":" ".join(dots),"x":0,"y":0,"fill":"#ffb04a","opacity":0.85},
 {"type":"layer-style","target":"embers","name":"outer-glow","settings":{"color":"#ff6a00","blur":22,"opacity":0.9}},
 {"type":"effect","target":"embers","name":"gaussian-blur","amount":2},
]
for i,p in enumerate(smoke):
    ops += [{"type":"shape","shape":"path","name":f"smoke{i}","path":p,"x":0,"y":0,"stroke":"#9fb6b8","stroke_width":40+i*20,"line_cap":"round","opacity":0.12},
            {"type":"effect","target":f"smoke{i}","name":"gaussian-blur","amount":30}]
ops += [{"type":"reorder","target":f"smoke{i}","below":"ambient"} for i in range(3)]
ops += text("artist","JEFFREY X GUNTLY","inter",54,"#9cc3c4","center",2330,30)
ops += text("title","Friends and Flames","playfair-black-italic",250,"#f4e2c6","center",2400)
ops += [{"type":"layer-style","target":"title","name":"drop-shadow","settings":{"color":"#000000aa","dx":0,"dy":8,"blur":30}}]
ops += pa(2560,2700,340)
save('c03',ops)
