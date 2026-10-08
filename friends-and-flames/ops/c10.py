from lib import *
import random
random.seed(9)
ops = strip_all() + [
 {"type":"gradient","name":"sky","x":0,"y":0,"width":3000,"height":3000,"direction":"vertical",
  "stops":[{"offset":0,"color":"#170404"},{"offset":0.35,"color":"#5e1209"},{"offset":0.62,"color":"#c8360f"},{"offset":0.8,"color":"#ff8a2a"},{"offset":1,"color":"#ffc46a"}]},
 {"type":"bottom","target":"sky"},
 {"type":"shape","shape":"ellipse","name":"sun","x":900,"y":1500,"width":1200,"height":1200,"fill":"#ffd27a","opacity":0.9},
 {"type":"layer-style","target":"sun","name":"outer-glow","settings":{"color":"#ffb050","blur":100,"opacity":0.9}},
]
rows=[(0.55,2250,"#4a1008",34),(0.8,2480,"#260806",24),(1.15,2780,"#0f0303",15),(1.7,3150,"#050101",9)]
flames=[]
for ri,(s,base,col,n) in enumerate(rows):
    subs=[]
    xs=sorted(random.uniform(-60,3060) for _ in range(n))
    for x in xs:
        r=random.random()
        arm = (1 if random.random()<0.5 else -1) if r<0.55 else 0
        torch = arm!=0 and random.random()<0.7
        p,tip=person(x, base+random.uniform(-20,20)*s, s*random.uniform(0.9,1.1), arm, torch)
        subs+=p
        if tip: flames.append(flame_sub(tip[0],tip[1]+5*s,70*s,150*s))
    ops.append({"type":"shape","shape":"path","name":f"row{ri}","path":" ".join(subs),"x":0,"y":0,"fill":col})
ops += [{"type":"shape","shape":"path","name":"torches","path":" ".join(flames),"x":0,"y":0,"fill":"#ffb347"},
        {"type":"layer-style","target":"torches","name":"outer-glow","settings":{"color":"#ff6a00","blur":40,"opacity":1}},
        {"type":"layer-style","target":"torches","name":"gradient-overlay","settings":{"direction":"vertical","stops":[{"offset":0,"color":"#ff7a1a"},{"offset":1,"color":"#fff1b0"}]}}]
ops += text("t1","FRIENDS","anton",520,"#f6e6cf","center",140,20)
ops += text("t2","AND FLAMES","anton",300,"#f6e6cf","center",760,14)
ops += text("artist","JEFFREY X GUNTLY","inter",62,"#f6e6cf",150,2800,24)
ops += pa(2500,2650,400)
save('c10',ops)
