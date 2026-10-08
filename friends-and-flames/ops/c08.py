from lib import *
RED="#a51d1d"; CREAM="#f3e6c8"; INK="#2b1a12"; GOLD="#d9a441"
s=0.62; px,py=1500,1230
hx,hy = px-1892*s, py-1332*s
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"bg","color":RED},{"type":"bottom","target":"bg"},
 {"type":"shape","shape":"rectangle","name":"frame1","x":70,"y":70,"width":2860,"height":2860,"fill":"#00000000","stroke":CREAM,"stroke_width":22},
 {"type":"shape","shape":"rectangle","name":"frame2","x":120,"y":120,"width":2760,"height":2760,"fill":"#00000000","stroke":GOLD,"stroke_width":6},
 {"type":"shape","shape":"ellipse","name":"oval-rim","x":480,"y":520,"width":2040,"height":2040,"fill":GOLD},
 {"type":"shape","shape":"ellipse","name":"oval","x":510,"y":550,"width":1980,"height":1980,"fill":CREAM},
 {"type":"reorder","target":"frame1","above":"bg"},{"type":"reorder","target":"frame2","above":"frame1"},
 {"type":"reorder","target":"oval-rim","above":"frame2"},{"type":"reorder","target":"oval","above":"oval-rim"},
 {"type":"scale","target":"hand","value":s,"anchor":"top-left"},{"type":"move","target":"hand","x":hx,"y":hy},
 {"type":"reorder","target":"hand","above":"oval"},{"type":"clip","target":"hand","base":"oval"},
 {"type":"effect","target":"hand","name":"levels","black":30,"white":150},
 {"type":"effect","target":"hand","name":"sepia","amount":1},
 {"type":"effect","target":"hand","name":"crosshatch","amount":6},
 {"type":"shape","shape":"rectangle","name":"stick","x":px-12,"y":py-260,"width":24,"height":250,"fill":"#c99a5c","stroke":INK,"stroke_width":4},
 {"type":"shape","shape":"ellipse","name":"mhead","x":px-22,"y":py-300,"width":44,"height":64,"fill":RED,"stroke":INK,"stroke_width":4},
]
w,h=200,380
p=(f"M{w/2:.0f} 0 C {w*0.62:.0f} {h*0.25:.0f} {w:.0f} {h*0.5:.0f} {w*0.96:.0f} {h*0.74:.0f} C {w*0.92:.0f} {h*0.92:.0f} {w*0.72:.0f} {h:.0f} {w/2:.0f} {h:.0f} "
   f"C {w*0.28:.0f} {h:.0f} {w*0.08:.0f} {h*0.92:.0f} {w*0.04:.0f} {h*0.74:.0f} C 0 {h*0.5:.0f} {w*0.38:.0f} {h*0.25:.0f} {w/2:.0f} 0 Z")
ops += [{"type":"shape","shape":"path","name":"fl","path":p,"x":px-w/2,"y":py-270-h,"width":w,"height":h,"fill":"#e8572a","stroke":INK,"stroke_width":6},
        {"type":"shape","shape":"path","name":"flc","path":p,"x":px-w*0.27,"y":py-275-h*0.55,"width":w*0.54,"height":h*0.55,"fill":"#ffd25a"}]
# rays behind flame inside oval
ops += [{"type":"shape","shape":"sunburst","name":"rays","x":px-700,"y":py-470-700,"width":1400,"height":1400,"fill":"#e9d6ac","count":32},
        {"type":"reorder","target":"rays","above":"oval"},{"type":"clip","target":"rays","base":"oval"}]
ops += text("title","FRIENDS AND FLAMES","western",210,CREAM,"center",215)
ops += [{"type":"text-layout","target":"title","warp":"arc","amount":0.35},
        {"type":"layer-style","target":"title","name":"drop-shadow","settings":{"color":"#3a0a0a","dx":8,"dy":10,"blur":0}}]
ops += [{"type":"shape","shape":"ribbon","name":"ribbon","x":700,"y":2470,"width":1600,"height":230,"fill":CREAM,"stroke":INK,"stroke_width":6}]
ops += text("artist","JEFFREY X GUNTLY","western",92,RED,0,0)
ops += [{"type":"place","target":"artist","within":"ribbon","anchor":"center"}]
ops += text("tag1","STRIKE ANYWHERE","grotesk",54,CREAM,200,2800,14)
ops += text("tag2","LIGHT ONE FOR A FRIEND","grotesk",54,CREAM,200,170,14)
ops += pa(2470,2620,380)
save('c08',ops)
