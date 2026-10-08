from lib import *
import random
random.seed(21)
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":"#ece4d2"},{"type":"bottom","target":"paper"},
 {"type":"look","target":"paper","look":"paper","amount":0.7},
 {"type":"effect","target":"hand","name":"photocopy","amount":0.8},
 {"type":"rectangle","name":"stick","shape":"rectangle","x":1814,"y":560,"width":36,"height":340,"fill":"#111111"},
]
ops[-1]["type"]="shape"
# cut paper flame: three stacked flame silhouettes
def fl(name,cx,base,h,fill,rot=0):
    w=h*0.55
    p=(f"M{w*0.5:.0f} 0 C {w*0.62:.0f} {h*0.18:.0f} {w*0.95:.0f} {h*0.32:.0f} {w*0.98:.0f} {h*0.6:.0f} C {w:.0f} {h*0.85:.0f} {w*0.78:.0f} {h:.0f} {w*0.5:.0f} {h:.0f} "
       f"C {w*0.2:.0f} {h:.0f} 0 {h*0.85:.0f} {w*0.03:.0f} {h*0.62:.0f} C {w*0.06:.0f} {h*0.45:.0f} {w*0.22:.0f} {h*0.38:.0f} {w*0.3:.0f} {h*0.22:.0f} "
       f"C {w*0.36:.0f} {h*0.36:.0f} {w*0.42:.0f} {h*0.4:.0f} {w*0.46:.0f} {h*0.42:.0f} C {w*0.42:.0f} {h*0.25:.0f} {w*0.46:.0f} {h*0.1:.0f} {w*0.5:.0f} 0 Z")
    return [{"type":"shape","shape":"path","name":name,"path":p,"x":cx-w/2,"y":base-h,"width":w,"height":h,"fill":fill,"rotation":rot}]
ops += fl("f-red",1832,600,620,"#e0261b",-4) + fl("f-orange",1840,600,430,"#ff8a1c",3) + fl("f-yellow",1832,600,250,"#ffd93a",-2)
ops += [{"type":"layer-style","target":"f-red","name":"drop-shadow","settings":{"color":"#00000088","dx":14,"dy":14,"blur":2}}]
# ransom note title
fonts=["anton","abril","typewriter","rubikmono","western","grotesk","marker","playfair-black-italic"]
schemes=[("#111111","#ece4d2"),("#e0261b","#ffffff"),("#ffffff","#111111"),("#ffd93a","#111111"),("#ece4d2","#e0261b"),("#111111","#ffd93a")]
rows=[("FRIENDS",130,150),("AND",130,410),("FLAMES",130,640)]
n=0
for word,x0,y0 in rows:
    x=x0
    for ch in word:
        s=random.randint(150,200); w=int(s*random.uniform(0.95,1.15)); h=int(s*1.25)
        bg,fg=random.choice(schemes); f=random.choice(fonts); r=random.uniform(-7,7)
        yy=y0+random.randint(-15,15)
        ops += [{"type":"shape","shape":"rectangle","name":f"bx{n}","x":x,"y":yy,"width":w,"height":h,"fill":bg,"rotation":r,
                 "stroke":"#00000022","stroke_width":2},
                {"type":"text","name":f"ch{n}","text":ch,"font":f,"size":int(s*0.82),"color":fg,"within":f"bx{n}","rotation":r}]
        x+=w+random.randint(4,18); n+=1
ops += [{"type":"look","targets":[f"bx{i}" for i in range(n)],"look":"hard-shadow","amount":0.3,"color":"#00000055"}]
# tape with artist name
ops += [{"type":"shape","shape":"rectangle","name":"tape","x":120,"y":930,"width":1020,"height":120,"fill":"#f6e27ad9","rotation":-3},
        {"type":"text","name":"artist","text":"JEFFREY X GUNTLY","font":"typewriter","size":78,"color":"#111111","within":"tape","rotation":-3}]
# lyric strip
ops += [{"type":"shape","shape":"rectangle","name":"strip","x":1500,"y":2380,"width":1380,"height":200,"fill":"#ffffff","rotation":2},
        {"type":"tear","target":"strip","seed":3,"edges":["left","right"]},
        {"type":"text","name":"lyric","text":"let's get all our friends.\nlet's start a little fire.","font":"typewriter","size":64,"color":"#111111","within":"strip","rotation":2,"align":"left"},
        {"type":"look","target":"strip","look":"soft-shadow","amount":0.4}]
ops += pa(2500,2650,400)
save('c04',ops)
