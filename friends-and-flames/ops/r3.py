from lib import *
import random
P={}
# ---------- derivatives ----------
P['01b']=[{"type":"gradient","name":"oxblood","x":-500,"y":-700,"width":4000,"height":4200,"direction":"radial","falloff":"smooth",
  "stops":[{"offset":0,"color":"#3a120a"},{"offset":0.5,"color":"#1a0705"},{"offset":1,"color":"#050403"}]},{"type":"bottom","target":"oxblood"},
  {"type":"remove","targets":["title","artist"]}] + text("title","Friends and Flames","serif",130,"#f0e2cc","center",2560) + \
  text("artist","JEFFREY X GUNTLY","serif",58,"#d9a77a","center",2470,18)
random.seed(4)
sch=[("#111111","#efe9df"),("#d4241c","#ffffff"),("#efe9df","#111111"),("#111111","#d4241c")]
P['04b']=[{"type":"solid","target":"paper","color":"#e6e3dc"},
  {"type":"shape","targets":["f-red"],"fill":"#111111"},{"type":"shape","target":"f-orange","fill":"#d4241c"},
  {"type":"text-set","target":"lyric","text":"we're coming for you,\nand that's the fucking truth."}]
for i in range(16):
    bg,fg=random.choice(sch); P['04b']+= [{"type":"shape","target":f"bx{i}","fill":bg},{"type":"text-set","target":f"ch{i}","color":fg}]
BLUE="#0078bf"; PINK="#ff48b0"
P['05b']=[{"type":"effect-set","target":"hand","effect":"duotone","shadow_color":PINK,"highlight_color":"#f4eee0"},
  {"type":"shape","target":"stick","fill":PINK},{"type":"shape","target":"fl-pink","fill":"#ff6c2f"},
  {"type":"text-set","target":"w1","color":BLUE},{"type":"text-set","target":"w2","color":BLUE},
  {"type":"text-set","target":"w1b","color":PINK},{"type":"text-set","target":"w2b","color":PINK},
  {"type":"text-set","target":"artist","color":PINK},
  {"type":"text-set","target":"lyric","text":"let's get all our friends.\nlet's start a little fire.","color":BLUE}]
P['07b']=[{"type":"shape","target":"sun","fill":"#141414"},{"type":"shape","target":"fl","fill":"#d4241c"},
  {"type":"shape","target":"bar","fill":"#d4241c"},{"type":"text-set","target":"t1","color":"#141414"},
  {"type":"shape","target":"slog-rule","fill":"#141414"},{"type":"text-set","target":"artist","color":"#141414"}]
P['09b']=[{"type":"shape","shape":"path","name":"stick2","path":"M1180 1380 L1590 640","x":0,"y":0,"stroke":"#d9b98a","stroke_width":62,"line_cap":"round"},
  {"type":"shape","shape":"path","name":"head2","path":ellipse_rot(1612,600,48,72,0.51),"x":0,"y":0,"fill":"#3b1a10"},
  fshape("fl2",1640,585,110,230,"#e4321b"),
  {"type":"text-set","target":"meta","text":"Single — 2026\nLet’s get all our friends.\nLet’s start a little fire.\nPass it on."}]
P['20b']=[{"type":"shape","target":"sun","fill":"#1f4fd6"},{"type":"text-set","target":"t3","color":"#1f4fd6"},{"type":"text-set","target":"slogan","color":"#1f4fd6"}]
P['22b']=[{"type":"solid","target":"paper","color":"#e9e2d0"},{"type":"shape","target":"block","fill":"#e8302a"},
  {"type":"shape","target":"fi","fill":"#e8302a"},{"type":"text-set","target":"title","color":"#e8302a"},{"type":"text-set","target":"artist","color":"#e8302a"}]
# ---------- "fix it" ----------
P['01c']=[{"type":"text-set","target":"title","size":100},{"type":"text-set","target":"artist","size":100},
  {"type":"move","target":"title","x":120,"y":110},{"type":"move","target":"artist","x":2140,"y":110},
  {"type":"gradient","name":"armfade","x":-300,"y":1700,"width":2200,"height":1600,"direction":"angled","angle":225,
   "stops":[{"offset":0,"color":"#05040300"},{"offset":0.55,"color":"#05040399"},{"offset":1,"color":"#050403"}]},
  {"type":"reorder","target":"armfade","above":"handlight"},
  {"type":"opacity","target":"flame-blue","value":0.3},
  {"type":"effect-set","target":"hand","effect":"grain","amount":0.008}]
P['04c']=[{"type":"group","name":"ransom","targets":[f"bx{i}" for i in range(16)]+[f"ch{i}" for i in range(16)]},
  {"type":"scale","target":"ransom","value":1.22,"anchor":"top-left"},
  {"type":"move","target":"tape","x":120,"y":1140},{"type":"move","target":"artist","x":0,"y":230,"relative":True},
  {"type":"resize","targets":["f-red"],"width":340,"height":560,"anchor":"bottom"},
  {"type":"effect-set","target":"hand","effect":"halftone","amount":20},
  {"type":"text-set","target":"lyric","size":72}]
P['05c']=[{"type":"look","target":"paper","look":"risograph","amount":0.25},{"type":"text-set","target":"lyric","size":72},
  {"type":"move","target":"lyric","x":100,"y":230},{"type":"text-set","target":"artist","size":84}]
P['07c']=[{"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#efe6d2","width":12}},
  {"type":"layer-style","target":"t1","name":"drop-shadow","settings":{"color":"#00000066","dx":10,"dy":12,"blur":0}},
  {"type":"text-set","target":"artist","size":66},{"type":"move","target":"parental-advisory","x":2500,"y":2690}]
P['09c']=[{"type":"text-set","target":"meta","size":54},{"type":"text-set","target":"artist","size":76},
  {"type":"move","target":"meta","x":1530,"y":1680},
  {"type":"text-set","target":"t1","size":360},{"type":"text-set","target":"t2","size":360},{"type":"text-set","target":"t3","size":360},
  {"type":"move","target":"t1","x":140,"y":1540},{"type":"move","target":"t2","x":140,"y":1900},{"type":"move","target":"t3","x":140,"y":2260},
  {"type":"move","target":"parental-advisory","x":2470,"y":2620}] + \
  text("quote","“we’ll march up to the stage,\nand turn the volume higher.”","serif-italic",80,"#111111",200,500,line_height=1.25) + \
  [{"type":"shape","shape":"rectangle","name":"qrule","x":200,"y":440,"width":160,"height":10,"fill":"#e4321b"}]
P['20c']=[{"type":"text-set","target":"artist","size":82},{"type":"move","target":"artist","x":160,"y":1065},
  {"type":"shape","shape":"rectangle","name":"arule","x":160,"y":1190,"width":420,"height":10,"fill":"#d4241c"}]
P['22c']=[{"type":"effect-set","target":"hand","effect":"halftone","amount":20},
  {"type":"text-set","target":"artist","color":"#161210","size":96},{"type":"move","target":"artist","x":130,"y":1080}]
import json
for k,v in P.items(): json.dump(v,open(f'/home/user/Vixl/friends-and-flames/ops/r3-{k}.json','w'))
print(list(P))
