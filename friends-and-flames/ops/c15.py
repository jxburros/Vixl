from lib import *
import math, random
random.seed(8)
cx,cy=1500,1420; NAVY="#0c1626"; CREAM="#f6e7c8"
ops = strip_all() + [{"type":"solid","name":"bg","color":NAVY},{"type":"bottom","target":"bg"},
 {"type":"gradient","name":"glow","x":cx-1400,"y":cy-1400,"width":2800,"height":2800,"direction":"radial","falloff":"smooth",
  "stops":[{"offset":0,"color":"#ffb35acc"},{"offset":0.35,"color":"#c4552055"},{"offset":1,"color":"#0c162600"}]},
 {"type":"shape","shape":"ellipse","name":"ring","x":cx-560,"y":cy-560,"width":1120,"height":1120,"fill":"#00000000","stroke":"#f6e7c855","stroke_width":6,"dash":[10,30],"line_cap":"round"},
 {"type":"shape","shape":"ellipse","name":"ring2","x":cx-1150,"y":cy-1150,"width":2300,"height":2300,"fill":"#00000000","stroke":"#f6e7c833","stroke_width":5},
]
# stones around the fire pit
st=[]
for i in range(16):
    a=2*math.pi*i/16; r=310
    st.append(ellipse_rot(cx+r*math.cos(a),cy+r*math.sin(a),62,46,a))
ops.append({"type":"shape","shape":"path","name":"stones","path":" ".join(st),"x":0,"y":0,"fill":"#5d5a63","stroke":"#2b2a30","stroke_width":8})
logs=" ".join(rect_rot(cx,cy,480,80,math.radians(a)) for a in (20,80,140))
ops.append({"type":"shape","shape":"path","name":"logs","path":logs,"x":0,"y":0,"fill":"#5a3420","stroke":"#2a160c","stroke_width":8})
fo=" ".join(flame_rot(cx+60*math.cos(a),cy+60*math.sin(a),200,330,a) for a in [2*math.pi*i/9+0.2 for i in range(9)])
fy=" ".join(flame_rot(cx+30*math.cos(a),cy+30*math.sin(a),120,200,a) for a in [2*math.pi*i/7+0.5 for i in range(7)])
ops += [{"type":"shape","shape":"path","name":"fire-o","path":fo,"x":0,"y":0,"fill":"#ff6a1a"},
        {"type":"layer-style","target":"fire-o","name":"outer-glow","settings":{"color":"#ff7a1a","blur":80,"opacity":0.9}},
        {"type":"shape","shape":"path","name":"fire-y","path":fy,"x":0,"y":0,"fill":"#ffc44a"},
        {"type":"shape","shape":"ellipse","name":"core","x":cx-70,"y":cy-70,"width":140,"height":140,"fill":"#fff3c4"}]
shirts=["#c0392b","#2e86ab","#f4a261","#6a4c93","#2a9d8f","#e76f51","#457b9d","#f2c14e","#8d5a97","#3d5a80","#d1495b","#00798c"]
hair=["#2b1d14","#4a2c1a","#111111","#7a4a22","#c48a3a","#222222"]
for i in range(12):
    a=2*math.pi*i/12; r=800
    x,y=cx+r*math.cos(a),cy+r*math.sin(a)
    hx,hy=cx+(r-40)*math.cos(a),cy+(r-40)*math.sin(a)
    ops += [{"type":"shape","shape":"path","name":f"body{i}","path":ellipse_rot(x,y,85,175,a),"x":0,"y":0,"fill":shirts[i]},
            {"type":"layer-style","target":f"body{i}","name":"drop-shadow","settings":{"color":"#00000099","dx":round(40*math.cos(a)),"dy":round(40*math.sin(a)),"blur":30}},
            {"type":"shape","shape":"path","name":f"head{i}","path":ellipse_rot(hx,hy,62,62,0),"x":0,"y":0,"fill":random.choice(hair)}]
ops += text("title","Friends and Flames","serif",210,CREAM,"center",2560)
ops += text("artist","JEFFREY X GUNTLY","inter",56,CREAM,"center",130,26)
ops += text("ly","we’ll rally all around","serif-italic",64,"#f6c98c","center",2810)
ops += pa(2520,2680,360)
save('c15',ops)
