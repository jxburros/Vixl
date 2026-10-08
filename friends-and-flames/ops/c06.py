from lib import *
Q=[(0,0,"#1a1a8c","#ffd400","#ff2e88","#ff2e00","#ffffff"),
   (1500,0,"#000000","#3df2ff","#ff6a00","#ffe600","#000000"),
   (0,1500,"#6b00b8","#ff9ad5","#c8ff00","#ff2e88","#6b00b8"),
   (1500,1500,"#d10000","#fff1a8","#0047ff","#ffd400","#d10000")]
def fp(w,h):
    return (f"M{w/2:.0f} 0 C {w*0.62:.0f} {h*0.25:.0f} {w:.0f} {h*0.5:.0f} {w*0.96:.0f} {h*0.74:.0f} C {w*0.92:.0f} {h*0.92:.0f} {w*0.72:.0f} {h:.0f} {w/2:.0f} {h:.0f} "
            f"C {w*0.28:.0f} {h:.0f} {w*0.08:.0f} {h*0.92:.0f} {w*0.04:.0f} {h*0.74:.0f} C 0 {h*0.5:.0f} {w*0.38:.0f} {h*0.25:.0f} {w/2:.0f} 0 Z")
ops = strip() + clear_hand_fx() + [
  {"type":"effect","target":"hand","name":"levels","black":30,"white":150},
  {"type":"effect","target":"hand","name":"posterize","amount":4},
  {"type":"effect","target":"hand","name":"duotone","shadow_color":"#000000","highlight_color":"#ffffff"},
  {"type":"scale","target":"hand","value":0.5,"anchor":"top-left"},
]
for i,(qx,qy,sh,hi,bg,fl,stk) in enumerate(Q):
    ops += [{"type":"shape","shape":"rectangle","name":f"q{i}","x":qx,"y":qy,"width":1500,"height":1500,"fill":bg},
            {"type":"duplicate","target":"hand","name":f"hand{i}"},
            {"type":"move","target":f"hand{i}","x":qx-30,"y":qy-240},
            {"type":"effect-set","target":f"hand{i}","effect":"duotone","shadow_color":sh,"highlight_color":hi},
            {"type":"reorder","target":f"hand{i}","above":f"q{i}"},
            {"type":"clip","target":f"hand{i}","base":f"q{i}"},
            {"type":"shape","shape":"rectangle","name":f"stick{i}","x":qx+907,"y":qy+290,"width":18,"height":150,"fill":stk},
            {"type":"shape","shape":"path","name":f"fl{i}","path":fp(130,260),"x":qx+916-65,"y":qy+300-260,"width":130,"height":260,"fill":fl,"stroke":"#000000","stroke_width":6},
            {"type":"shape","shape":"path","name":f"flc{i}","path":fp(60,120),"x":qx+916-30,"y":qy+300-125,"width":60,"height":120,"fill":"#fff6a0"}]
ops += [{"type":"remove","target":"hand"},
  {"type":"shape","shape":"rectangle","name":"band","x":0,"y":1340,"width":3000,"height":320,"fill":"#ffffff","stroke":"#000000","stroke_width":14}]
ops += text("title","FRIENDS AND FLAMES","anton",230,"#000000",0,0,4)
ops += [{"type":"place","target":"title","within":"band","anchor":"center"}]
ops += text("artist","JEFFREY X GUNTLY","anton",80,"#ffffff",90,90,10)
ops += [{"type":"layer-style","target":"artist","name":"stroke","settings":{"color":"#000000","width":8}}]
ops += pa(2510,2660,400)
save('c06',ops)
