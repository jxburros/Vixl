from lib import *
import random
random.seed(18)
ops = strip_all() + [
 {"type":"gradient","name":"bgk","x":0,"y":0,"width":3000,"height":3000,"direction":"vertical","stops":[{"offset":0,"color":"#07040e"},{"offset":0.6,"color":"#1b0b2a"},{"offset":1,"color":"#2a0d12"}]},
 {"type":"bottom","target":"bgk"}]
# spotlight beams
beams=[(600,"#8a5cff"),(1500,"#fff1d0"),(2400,"#ff4f9a")]
for i,(x,col) in enumerate(beams):
    tx=1500+(x-1500)*0.25
    ops += [{"type":"shape","shape":"path","name":f"beam{i}","path":f"M{x-40} -20 L{x+40} -20 L{tx+420} 2100 L{tx-420} 2100 Z","x":0,"y":0,"fill":col,"opacity":0.22},
            {"type":"effect","target":f"beam{i}","name":"gaussian-blur","amount":30},{"type":"blend","target":f"beam{i}","value":"screen"}]
# stage floor
ops += [{"type":"shape","shape":"path","name":"stage","path":"M300 2000 L2700 2000 L3000 2350 L0 2350 Z","x":0,"y":0,"fill":"#140b10"},
        {"type":"shape","shape":"rectangle","name":"stage-front","x":0,"y":2350,"width":3000,"height":120,"fill":"#0a0507"},
        {"type":"shape","shape":"ellipse","name":"pool","x":1050,"y":1900,"width":900,"height":200,"fill":"#fff1d0","opacity":0.35},
        {"type":"effect","target":"pool","name":"gaussian-blur","amount":40}]
# mic stand
ops += [{"type":"shape","shape":"path","name":"mic","x":0,"y":0,"fill":"#050305",
         "path":"M1490 1100 L1510 1100 L1512 2000 L1488 2000 Z M1500 1990 L1380 2060 L1390 2075 L1500 2010 L1610 2075 L1620 2060 Z M1486 1100 L1395 905 L1410 898 L1502 1092 Z"},
        {"type":"shape","shape":"path","name":"mic-head","x":0,"y":0,"fill":"#1a1a1a","stroke":"#555","stroke_width":6,"path":ellipse_rot(1385,880,55,38,-1.13)}]
# pyro columns at the stage front
for i,x in enumerate((420,980,2020,2580)):
    h=random.uniform(900,1300); w=h*0.35
    ops += [{"type":"shape","shape":"path","name":f"pyro{i}","path":flame_sub(x,2010,w,h),"x":0,"y":0,"fill":"#ff6a1a"},
            {"type":"layer-style","target":f"pyro{i}","name":"gradient-overlay","settings":{"direction":"vertical","stops":[{"offset":0,"color":"#ff2a00"},{"offset":0.6,"color":"#ff9a1f"},{"offset":1,"color":"#fff3c0"}]}},
            {"type":"layer-style","target":f"pyro{i}","name":"outer-glow","settings":{"color":"#ff5a00","blur":100,"opacity":0.9}},
            {"type":"shape","shape":"path","name":f"pyroc{i}","path":flame_sub(x,2000,w*0.45,h*0.45),"x":0,"y":0,"fill":"#fff6d0"}]
# crowd with raised fists in the foreground
subs=[]
for x in range(-40,3100,170):
    arm=random.choice([1,-1,1,0])
    p,_=person(x+random.uniform(-40,40),2950+random.uniform(-40,40),1.6*random.uniform(0.9,1.1),arm,False)
    subs+=p
ops += [{"type":"shape","shape":"path","name":"crowd","path":" ".join(subs),"x":0,"y":0,"fill":"#030203"},
        {"type":"shape","shape":"rectangle","name":"crowd-floor","x":0,"y":2900,"width":3000,"height":100,"fill":"#030203"}]
ops += text("title","FRIENDS AND FLAMES","marker",250,"#ffffff","center",160)
ops += [{"type":"layer-style","target":"title","name":"outer-glow","settings":{"color":"#ff4f9a","blur":40,"opacity":0.8}}]
ops += text("artist","JEFFREY X GUNTLY","grotesk",70,"#ffd6e8","center",470,20)
ops += pa(2500,2650,400)
save('c18',ops)
