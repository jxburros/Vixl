from lib import *
PINK="#ff48b0"; BLUE="#0078bf"; YEL="#ffe800"; PAPER="#f4eee0"
ops = strip() + clear_hand_fx() + [
 {"type":"solid","name":"paper","color":PAPER},{"type":"bottom","target":"paper"},
 {"type":"effect","target":"hand","name":"levels","black":30,"white":160},
 {"type":"effect","target":"hand","name":"duotone","shadow_color":BLUE,"highlight_color":PAPER},
 {"type":"blend","target":"hand","value":"multiply"},
 {"type":"shape","shape":"rectangle","name":"stick","x":1816,"y":560,"width":32,"height":330,"fill":BLUE},{"type":"blend","target":"stick","value":"multiply"},
]
import math
def flame_path(w,h):
    return (f"M{w/2:.0f} 0 C {w*0.62:.0f} {h*0.25:.0f} {w:.0f} {h*0.5:.0f} {w*0.96:.0f} {h*0.74:.0f} C {w*0.92:.0f} {h*0.92:.0f} {w*0.72:.0f} {h:.0f} {w/2:.0f} {h:.0f} "
            f"C {w*0.28:.0f} {h:.0f} {w*0.08:.0f} {h*0.92:.0f} {w*0.04:.0f} {h*0.74:.0f} C 0 {h*0.5:.0f} {w*0.38:.0f} {h*0.25:.0f} {w/2:.0f} 0 Z")
ops += [{"type":"shape","shape":"path","name":"fl-pink","path":flame_path(300,640),"x":1832-150,"y":570-640,"width":300,"height":640,"fill":PINK},
        {"type":"shape","shape":"path","name":"fl-yel","path":flame_path(170,360),"x":1832-85+14,"y":570-360+10,"width":170,"height":360,"fill":YEL},
        {"type":"blend","targets":["fl-pink","fl-yel"],"value":"multiply"}]
# huge stacked type, pink with a blue misregistered echo
for nm,txt,y in [("w1","FRIENDS",1880),("w2","& FLAMES",2330)]:
    ops += text(nm+"b",txt,"grotesk",420,BLUE,96,y+10,-6) + text(nm,txt,"grotesk",420,PINK,84,y,-6)
    ops += [{"type":"blend","targets":[nm+"b",nm],"value":"multiply"},{"type":"opacity","target":nm+"b","value":0.55}]
ops += text("artist","JEFFREY X GUNTLY","grotesk",72,BLUE,100,110,18)
ops += text("lyric","we'll rally all around.\nwe're catching all the flames.","inter",54,PINK,100,230)
ops += [{"type":"look","targets":["paper"],"look":"risograph","amount":0.6}]
ops += pa(2500,2650,400)
save('c05',ops)
