# 4 + 5: risograph zine
from lib import *
import random
random.seed(41)
TEAL="#00838a"; RED="#ff4b3e"; YEL="#ffd400"; PAPER="#f3ecdc"
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":PAPER},{"type":"bottom","target":"paper"},
 {"type":"effect","target":"hand","name":"grayscale"},
 {"type":"effect","target":"hand","name":"levels","black":30,"white":150},
 {"type":"effect","target":"hand","name":"halftone","amount":22},
 {"type":"effect","target":"hand","name":"duotone","shadow_color":TEAL,"highlight_color":PAPER},
 {"type":"blend","target":"hand","value":"multiply"},
 {"type":"shape","shape":"rectangle","name":"stick","x":1816,"y":560,"width":32,"height":330,"fill":TEAL},
 fshape("f1",1840,600,320,640,RED), fshape("f2",1822,590,180,360,YEL),
 {"type":"blend","targets":["f1","f2","stick"],"value":"multiply"},
]
schemes=[(TEAL,PAPER),(RED,PAPER),(PAPER,TEAL),(YEL,TEAL),(PAPER,RED),(TEAL,YEL)]
fonts=["anton","abril","typewriter","rubikmono","grotesk","marker","playfair-black-italic"]
rows=[("FRIENDS",150,2080),("&FLAMES",150,2420)]
n=0
for word,x0,y0 in rows:
    x=x0
    for ch in word:
        s=random.randint(230,280); w=int(s*random.uniform(0.95,1.1)); h=int(s*1.2)
        bg,fg=random.choice(schemes); r=random.uniform(-6,6)
        ops += [{"type":"shape","shape":"rectangle","name":f"bx{n}","x":x,"y":y0+random.randint(-20,20),"width":w,"height":h,"fill":bg,"rotation":r},
                {"type":"text","name":f"ch{n}","text":ch,"font":random.choice(fonts),"size":int(s*0.8),"color":fg,"within":f"bx{n}","rotation":r},
                {"type":"blend","target":f"bx{n}","value":"multiply"}]
        x+=w+random.randint(6,20); n+=1
ops += [{"type":"shape","shape":"rectangle","name":"strip","x":120,"y":160,"width":1250,"height":330,"fill":"#ffffff","rotation":-2},
        {"type":"tear","target":"strip","seed":7,"edges":["left","right"]},
        {"type":"text","name":"lyric","text":"if you start getting nervous,\nit’s ’cause you’re the one to blame.","font":"typewriter","size":56,"color":TEAL,"within":"strip","rotation":-2},
        {"type":"shape","shape":"rectangle","name":"tape","x":140,"y":560,"width":900,"height":110,"fill":"#ff4b3e99","rotation":2},
        {"type":"text","name":"artist","text":"JEFFREY X GUNTLY","font":"typewriter","size":70,"color":"#1b1b1b","within":"tape","rotation":2},
        {"type":"look","target":"paper","look":"risograph","amount":0.5}]
ops += pa(2500,2650,400)
save('c19',ops)
