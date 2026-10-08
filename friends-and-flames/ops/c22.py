# 4 + 7: screenprint protest poster on kraft
from lib import *
ORG="#ff5a1f"; BLK="#161210"; KRAFT="#cfae84"
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":KRAFT},{"type":"bottom","target":"paper"},
 {"type":"look","target":"paper","look":"paper","amount":0.8},
 {"type":"shape","shape":"rectangle","name":"block","x":1380,"y":0,"width":1620,"height":1700,"fill":ORG},
 {"type":"blend","target":"block","value":"multiply"},{"type":"reorder","target":"block","above":"paper"},
 {"type":"effect","target":"hand","name":"grayscale"},
 {"type":"effect","target":"hand","name":"levels","black":30,"white":150},
 {"type":"effect","target":"hand","name":"halftone","amount":30},
 {"type":"blend","target":"hand","value":"multiply"},
 {"type":"shape","shape":"rectangle","name":"stick","x":1816,"y":560,"width":34,"height":330,"fill":BLK},
 fshape("fo",1832,600,330,640,BLK), fshape("fi",1846,590,190,380,ORG),
]
ops += text("s","WE ARE\nSTRONGER\nTHAN YOU\nALONE.","anton",210,BLK,130,140,2,line_height=0.92)
ops += [{"type":"shape","shape":"rectangle","name":"band","x":0,"y":2330,"width":3000,"height":330,"fill":BLK}]
ops += text("title","FRIENDS AND FLAMES","anton",250,ORG,"center",2360,10)
ops += text("artist","JEFFREY X GUNTLY","anton",80,BLK,130,2740,12)
ops += [{"type":"look","target":"title","look":"risograph","amount":0.5}]
ops += pa(2500,2700,380)
save('c22',ops)
