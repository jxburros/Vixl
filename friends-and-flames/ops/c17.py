from lib import *
import random
random.seed(17)
shades=["#3a1712","#44201a","#331410","#4b241c"]
by={s:[] for s in shades}
bw,bh,m=300,120,14
for r in range(0,3000//bh+1):
    off=0 if r%2==0 else -bw/2
    for c in range(-1,3000//bw+2):
        x=c*bw+off; y=r*bh
        by[random.choice(shades)].append(f"M{x+m/2:.0f} {y+m/2:.0f}h{bw-m}v{bh-m}h-{bw-m}Z")
ops = strip_all() + [{"type":"solid","name":"mortar","color":"#1a0c0a"},{"type":"bottom","target":"mortar"}]
for i,s in enumerate(shades):
    ops.append({"type":"shape","shape":"path","name":f"brick{i}","path":"".join(by[s]),"x":0,"y":0,"fill":s})
ops += [{"type":"gradient","name":"shade","x":-500,"y":-500,"width":4000,"height":4000,"direction":"radial","falloff":"smooth",
         "stops":[{"offset":0,"color":"#00000033"},{"offset":0.6,"color":"#000000aa"},{"offset":1,"color":"#000000f2"}]},
        {"type":"gradient","name":"spill","x":200,"y":300,"width":2600,"height":2200,"direction":"radial","falloff":"gaussian",
         "stops":[{"offset":0,"color":"#ff4fd855"},{"offset":0.5,"color":"#ff7a2a22"},{"offset":1,"color":"#00000000"}]},
        {"type":"blend","target":"spill","value":"screen"}]
def neon(name, s, size, color, core, x, y, font="neon"):
    o=text(name,s,font,size,core,x,y)
    o+=[{"type":"layer-style","target":name,"name":"stroke","settings":{"color":color,"width":max(4,size//40)}},
        {"type":"layer-style","target":name,"name":"outer-glow","settings":{"color":color,"blur":min(100,size//4),"opacity":1}}]
    return o
ops += neon("t1","Friends",420,"#ff3fd0","#ffe3fa","center",620)
ops += neon("amp","&",300,"#5ad7ff","#e6fbff","center",1120)
ops += neon("t2","Flames",420,"#ff8a1f","#fff1d6","center",1480)
# neon flame outline above the title
fp=flame_sub(1500,560,200,400)
ops += [{"type":"shape","shape":"path","name":"nflame","path":fp,"x":0,"y":0,"fill":"#00000000","stroke":"#fff1d6","stroke_width":16,"line_join":"round"},
        {"type":"layer-style","target":"nflame","name":"outer-glow","settings":{"color":"#ff8a1f","blur":60,"opacity":1}},
        {"type":"shape","shape":"path","name":"nflame2","path":flame_sub(1500,540,90,200),"x":0,"y":0,"fill":"#00000000","stroke":"#ffe3fa","stroke_width":12},
        {"type":"layer-style","target":"nflame2","name":"outer-glow","settings":{"color":"#ff3fd0","blur":40,"opacity":1}}]
ops += neon("artist","JEFFREY X GUNTLY",110,"#5ad7ff","#e6fbff","center",2200)
ops += [{"type":"text-style","target":"artist","start":0,"end":16,"tracking":20}]
ops += pa(2500,2650,400)
save('c17',ops)
