from lib import *
import random
random.seed(11)
ops=[{"type":"remove","targets":["title","artist"]},
     {"type":"gradient","name":"sky","x":0,"y":0,"width":3000,"height":3000,"direction":"vertical",
      "stops":[{"offset":0,"color":"#050303"},{"offset":0.55,"color":"#0d0504"},{"offset":0.85,"color":"#3a0f06"},{"offset":1,"color":"#6a1e08"}]}]
names=[]
rows=[(2380,24,70),(2480,30,60),(2600,40,48),(2740,52,40),(2900,66,30)]
i=0
for y,h,n in rows:
    for k in range(n):
        x=random.uniform(-40,3040); yy=y+random.uniform(-30,30); hh=h*random.uniform(0.8,1.2)
        nm=f"crowd{i}"; i+=1; names.append(nm)
        ops += tiny_flame(x,yy,hh,nm,opacity=random.uniform(0.75,1.0))
        # the person holding it: a dark head/shoulders bump under the flame
ops += [{"type":"group","name":"crowd","targets":names},{"type":"bottom","target":"crowd"},{"type":"bottom","target":"sky"},
  {"type":"gradient","name":"haze","x":0,"y":2000,"width":3000,"height":1000,"direction":"vertical","stops":[{"offset":0,"color":"#ff6a1a00"},{"offset":1,"color":"#ff6a1a33"}]},
  {"type":"blend","target":"haze","value":"screen"},{"type":"reorder","target":"haze","above":"crowd"},
]
ops += text("title","FRIENDS AND FLAMES","anton",190,"#f3e6d6",110,110,6)
ops += text("artist","JEFFREY X GUNTLY","inter",62,"#d9a77a",118,360,22)
ops += pa(2500,2650,400)
save('c02',ops)
