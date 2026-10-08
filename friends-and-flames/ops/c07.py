from lib import *
RED="#d4241c"; CREAM="#efe6d2"; BLK="#141414"
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":CREAM},{"type":"bottom","target":"paper"},
 {"type":"shape","shape":"rectangle","name":"bar","x":-600,"y":1350,"width":4200,"height":300,"fill":BLK,"rotation":-32},
 {"type":"shape","shape":"ellipse","name":"sun","x":1832-520,"y":380-520,"width":1040,"height":1040,"fill":RED},
 {"type":"reorder","target":"bar","above":"paper"},{"type":"reorder","target":"sun","above":"bar"},
 {"type":"effect","target":"hand","name":"grayscale"},
 {"type":"effect","target":"hand","name":"levels","black":40,"white":150},
 {"type":"effect","target":"hand","name":"contrast","amount":0.4},
 {"type":"shape","shape":"rectangle","name":"stick","x":1814,"y":560,"width":36,"height":330,"fill":BLK},
]
w,h=300,560
p=(f"M{w/2:.0f} 0 L {w:.0f} {h*0.62:.0f} L {w*0.8:.0f} {h:.0f} L {w*0.2:.0f} {h:.0f} L 0 {h*0.62:.0f} Z")
ops += [{"type":"shape","shape":"path","name":"fl","path":p,"x":1832-w/2,"y":580-h,"width":w,"height":h,"fill":BLK},
        {"type":"shape","shape":"path","name":"flc","path":p,"x":1832-w*0.25,"y":580-h*0.5,"width":w*0.5,"height":h*0.5,"fill":CREAM}]
ops += text("slogan","WE ARE\nSTRONGER\nTHAN YOU\nALONE.","anton",150,BLK,110,110,2,line_height=0.95)
ops += [{"type":"shape","shape":"rectangle","name":"slog-rule","x":110,"y":780,"width":420,"height":24,"fill":RED}]
ops += text("t1","FRIENDS","anton",380,RED,1180,1880,4,rotation=-8)
ops += text("t2","AND FLAMES","anton",300,BLK,1150,2260,4,rotation=-8)
ops += text("artist","JEFFREY X GUNTLY","rubikmono",64,BLK,1240,2700,6)
ops += pa(2500,2650,400)
save('c07',ops)
