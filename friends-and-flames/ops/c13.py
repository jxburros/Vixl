from lib import *
import math, random
random.seed(2)
cx,cy=1500,1720; GOLD="#e2c27a"
ops = strip_all() + [{"type":"solid","name":"tolex","color":"#121110"},{"type":"bottom","target":"tolex"},
  {"type":"effect","target":"tolex","name":"noise","amount":0.08,"seed":4}]
# flames rising from below, behind everything
fl=[]
for i in range(26):
    x=random.uniform(-100,3100); h=random.uniform(350,900); w=h*random.uniform(0.35,0.5)
    fl.append(flame_sub(x,3150,w,h))
ops += [{"type":"shape","shape":"path","name":"fire","path":" ".join(fl),"x":0,"y":0,"fill":"#ff5a14","opacity":0.9},
        {"type":"layer-style","target":"fire","name":"gradient-overlay","settings":{"direction":"vertical","stops":[{"offset":0,"color":"#ff2a00"},{"offset":0.75,"color":"#ff8a1c"},{"offset":1,"color":"#ffe08a"}]}},
        {"type":"layer-style","target":"fire","name":"outer-glow","settings":{"color":"#ff4a00","blur":100,"opacity":0.8}},
        {"type":"effect","target":"fire","name":"gaussian-blur","amount":6}]
# ticks and numbers
ticks=[]
for i in range(0,56):
    a=math.radians(135+i*4.8); big=i%5==0
    r1=640; r2=720 if big else 680
    ticks.append(f"M{cx+r1*math.cos(a):.0f} {cy+r1*math.sin(a):.0f} L{cx+r2*math.cos(a):.0f} {cy+r2*math.sin(a):.0f}")
ops += [{"type":"shape","shape":"path","name":"ticks","path":" ".join(ticks),"x":0,"y":0,"stroke":GOLD,"stroke_width":12,"line_cap":"round"}]
for n in range(0,11):
    a=math.radians(135+n*24); r=820
    ops += text(f"n{n}",str(n),"grotesk",90,GOLD,0,0)
    ops += [{"type":"shape","shape":"ellipse","name":f"np{n}","x":cx+r*math.cos(a)-60,"y":cy+r*math.sin(a)-60,"width":120,"height":120,"fill":"#00000000"},
            {"type":"place","target":f"n{n}","within":f"np{n}","anchor":"center"}]
a=math.radians(135+11*24); r=850
ops += text("n11","11","grotesk",150,"#ff3b1f",0,0)
ops += [{"type":"shape","shape":"ellipse","name":"np11","x":cx+r*math.cos(a)-90,"y":cy+r*math.sin(a)-90,"width":180,"height":180,"fill":"#00000000"},
        {"type":"place","target":"n11","within":"np11","anchor":"center"},
        {"type":"layer-style","target":"n11","name":"outer-glow","settings":{"color":"#ff3b1f","blur":30,"opacity":0.9}}]
# knob: skirt, body, cap, pointer
ops += [{"type":"shape","shape":"ellipse","name":"skirt","x":cx-560,"y":cy-560,"width":1120,"height":1120,"fill":"#1c1c1c","stroke":"#3a3a3a","stroke_width":10},
        {"type":"layer-style","target":"skirt","name":"drop-shadow","settings":{"color":"#000000","dx":0,"dy":40,"blur":80,"opacity":0.9}},
        {"type":"shape","shape":"gear","name":"grip","x":cx-470,"y":cy-470,"width":940,"height":940,"fill":"#0d0d0d","teeth":48,"depth":0.05},
        {"type":"gradient","name":"cap","x":cx-380,"y":cy-380,"width":760,"height":760,"direction":"angled","angle":135,
         "stops":[{"offset":0,"color":"#f4f4f4"},{"offset":0.35,"color":"#9a9a9a"},{"offset":0.5,"color":"#e8e8e8"},{"offset":0.7,"color":"#6f6f6f"},{"offset":1,"color":"#cfcfcf"}]},
        {"type":"shape","shape":"ellipse","name":"capmask","x":cx-380,"y":cy-380,"width":760,"height":760,"fill":"#ffffff"},
        {"type":"reorder","target":"capmask","below":"cap"},{"type":"clip","target":"cap","base":"capmask"}]
pa_=math.radians(135+11*24)
px,py=cx+520*math.cos(pa_),cy+520*math.sin(pa_)
ops += [{"type":"shape","shape":"path","name":"pointer","path":f"M{cx+150*math.cos(pa_):.0f} {cy+150*math.sin(pa_):.0f} L{cx+360*math.cos(pa_):.0f} {cy+360*math.sin(pa_):.0f}","x":0,"y":0,"stroke":"#ff3b1f","stroke_width":56,"line_cap":"round"},
        {"type":"shape","shape":"ellipse","name":"hub","x":cx-60,"y":cy-60,"width":120,"height":120,"fill":"#2a2a2a"}]
# top plate
ops += [{"type":"shape","shape":"rounded-rectangle","name":"plate","x":150,"y":140,"width":2700,"height":560,"radius":30,"fill":"#0a0a0a","stroke":GOLD,"stroke_width":10}]
ops += text("title","Friends and Flames","playfair-black-italic",250,GOLD,"center",190)
ops += text("artist","JEFFREY X GUNTLY","grotesk",60,"#cfc6b0","center",530,18)
ops += pa(2500,2650,400)
save('c13',ops)
