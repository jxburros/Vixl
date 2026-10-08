# 7 + 9: swiss constructivist
from lib import *
RED="#d4241c"; CREAM="#efe8d8"; BLK="#141414"
s=0.75; px,py=2050,1080
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":CREAM},{"type":"bottom","target":"paper"},
 {"type":"shape","shape":"ellipse","name":"sun","x":px-430,"y":py-1060+60,"width":860,"height":860,"fill":RED},
 {"type":"reorder","target":"sun","above":"paper"},
 {"type":"scale","target":"hand","value":s,"anchor":"top-left"},
 {"type":"move","target":"hand","x":px-1892*s,"y":py-1332*s},
 {"type":"effect","target":"hand","name":"grayscale"},
 {"type":"effect","target":"hand","name":"levels","black":35,"white":150},
 {"type":"effect","target":"hand","name":"contrast","amount":0.35},
 {"type":"shape","shape":"rectangle","name":"stick","x":px-14,"y":py-280,"width":28,"height":270,"fill":BLK},
]
w,h=240,440
p=f"M{w/2:.0f} 0 L {w:.0f} {h*0.62:.0f} L {w*0.8:.0f} {h:.0f} L {w*0.2:.0f} {h:.0f} L 0 {h*0.62:.0f} Z"
ops += [{"type":"shape","shape":"path","name":"fl","path":p,"x":px-w/2,"y":py-270-h,"width":w,"height":h,"fill":BLK},
        {"type":"shape","shape":"path","name":"flc","path":p,"x":px-w*0.25,"y":py-270-h*0.5,"width":w*0.5,"height":h*0.5,"fill":CREAM}]
for x in (150,1500,2850): ops.append({"type":"shape","shape":"rectangle","name":f"v{x}","x":x,"y":150,"width":3,"height":2700,"fill":"#14141426"})
ops += [{"type":"shape","shape":"rectangle","name":"hr","x":150,"y":150,"width":1350,"height":10,"fill":BLK}]
ops += text("t1","Friends","grotesk",260,BLK,140,200,-8)
ops += text("t2","and","grotesk",260,BLK,140,460,-8)
ops += text("t3","Flames.","grotesk",260,RED,140,720,-8)
ops += text("artist","Jeffrey X Guntly","inter",58,BLK,160,1060)
ops += text("slogan","WE ARE STRONGER\nTHAN YOU ALONE.","anton",120,RED,150,2560,2,line_height=1.0)
ops += [{"type":"shape","shape":"rectangle","name":"bar","x":150,"y":2500,"width":620,"height":18,"fill":BLK}]
ops += pa(2500,2650,400)
save('c20',ops)
