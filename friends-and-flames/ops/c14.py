from lib import *
BG="#efc35a"; GROUND="#d9a23e"; INK="#2a2118"; CREAM="#fbf1dc"
heads=["#1f6f78","#e4572e","#22355e","#8c2f39","#3e7c4a","#6b3fa0","#e07a5f"]
ops = strip_all() + [{"type":"solid","name":"bg","color":BG},{"type":"bottom","target":"bg"},
  {"type":"shape","shape":"rectangle","name":"ground","x":0,"y":2480,"width":3000,"height":520,"fill":GROUND}]
xs=[600+i*300 for i in range(7)]
for i,x in enumerate(xs):
    top=1250+(0 if i%2 else 60); base=2500
    ops += [{"type":"shape","shape":"path","name":f"sh{i}","path":f"M{x-22} {base} L{x+22} {base} L{x+322} {base+420} L{x+278} {base+420} Z","x":0,"y":0,"fill":"#00000026"},
            {"type":"shape","shape":"rounded-rectangle","name":f"st{i}","x":x-22,"y":top,"width":44,"height":base-top,"radius":6,"fill":CREAM,"stroke":INK,"stroke_width":8},
            {"type":"shape","shape":"ellipse","name":f"hd{i}","x":x-42,"y":top-110,"width":84,"height":150,"fill":heads[i],"stroke":INK,"stroke_width":8}]
    h=420 if i==3 else 330
    ops += [fshape(f"fo{i}",x,top-60,h*0.5,h,"#e4572e",stroke=INK,stroke_width=8),
            fshape(f"fi{i}",x,top-70,h*0.26,h*0.5,"#ffe08a")]
ops += text("title","Friends","playfair-black-italic",300,INK,150,150)
ops += text("title2","& Flames","playfair-black-italic",300,"#e4572e",700,470)
ops += text("artist","JEFFREY X GUNTLY","grotesk",64,INK,150,2620,16)
ops += text("ly","we’re catching all the flames.","serif-italic",70,INK,150,2720)
ops += pa(2500,2650,400)
save('c14',ops)
