import json
ROWS=[f"row{i}" for i in range(7)]; ROWF=[r+"-f" for r in ROWS]
ACC=ROWS+["q1","q2","qdot","sun","t1"]   # red things
def pal(paper,accent,ink,light,stick="#e9c48a",hand=None,bar=None,t2=None,title=None,flame=None,name=None,sun=None):
    o=[{"type":"solid","target":"paper","color":paper},
       {"type":"shape","targets":ROWS+["qdot"],"fill":accent},
       {"type":"text-set","targets":["q1","q2"],"color":accent},
       {"type":"shape","target":"sun","fill":sun or accent},
       {"type":"text-set","target":"t1","color":title or accent},
       {"type":"layer-style","target":"t1","name":"stroke","settings":{"color":paper,"width":12}},
       {"type":"shape","targets":ROWF+["qdot-f","flame-f"],"fill":light},
       {"type":"shape","target":"flame","fill":flame or ink},
       {"type":"shape","target":"mhead","fill":flame or ink,"stroke":light},
       {"type":"shape","target":"bar","fill":bar or ink},
       {"type":"text-set","target":"t2","color":t2 or light},
       {"type":"text-set","target":"artist","color":name or ink},
       {"type":"shape","target":"stick","fill":stick,"stroke":ink}]
    if hand: o.append({"type":"effect","target":"hand","name":"duotone","shadow_color":hand[0],"highlight_color":hand[1]})
    return o
V={}
# ---- palettes ----
V["01-cobalt"]=pal("#efe6d2","#1f4fd6","#141414","#efe6d2")
V["02-orange-navy"]=pal("#f2ead9","#f05a28","#1b2a41","#f2ead9",hand=("#1b2a41","#f2ead9"))
V["03-gold-black"]=pal("#f4ecd8","#e0a020","#141414","#f4ecd8")
V["04-night"]=pal("#141414","#d4241c","#efe6d2","#141414",stick="#e9c48a",bar="#efe6d2",t2="#141414",name="#efe6d2")
V["05-riso-pink-teal"]=pal("#f3ecdc","#ff48b0","#00838a","#f3ecdc",hand=("#00838a","#f3ecdc"))
V["06-kraft"]=pal("#cfae84","#c8201a","#161210","#ead7b5")+[{"type":"look","target":"paper","look":"paper","amount":0.7}]
V["07-mono-red-flame"]=pal("#ffffff","#141414","#141414","#ffffff",flame="#d4241c",sun="#141414",title="#141414")
# ---- small changes ----
V["08-bigger-flame"]=[{"type":"resize","targets":["flame"],"width":280,"height":484,"anchor":"bottom"},
                      {"type":"resize","targets":["flame-f"],"width":113,"height":242,"anchor":"bottom-right"}]
V["09-bigger-sun"]=[{"type":"shape","target":"sun","x":1252,"y":-30,"width":1160,"height":1160},{"type":"layer-intent","target":"sun","allow_crop":True}]
V["10-smaller-sun"]=[{"type":"shape","target":"sun","x":1472,"y":190,"width":720,"height":720}]
V["11-flatter-bar"]=[{"type":"rotate","targets":["bar","t1","t2"],"value":4}]
V["12-black-title"]=[{"type":"text-set","target":"t1","color":"#141414"}]
V["13-red-name"]=[{"type":"text-set","target":"artist","color":"#d4241c"},{"type":"shape","targets":ROWS+["qdot"],"fill":"#141414"},{"type":"text-set","targets":["q1","q2"],"color":"#141414"}]
V["14-no-quote"]=[{"type":"remove","targets":["q1","q2","qdot","qdot-f"]}]
V["15-paper-grain"]=[{"type":"look","target":"paper","look":"paper","amount":0.8},{"type":"effect","target":"hand","name":"grain","amount":0.06,"seed":2}]
V["16-halftone-hand"]=[{"type":"effect","target":"hand","name":"halftone","amount":22}]
V["17-sun-ring"]=[{"type":"shape","shape":"ellipse","name":"ring","x":1322,"y":40,"width":1020,"height":1020,"fill":"#00000000","stroke":"#141414","stroke_width":14},{"type":"reorder","target":"ring","above":"sun"}]
V["18-mono-title-font"]=[{"type":"text-set","target":"t1","font":"rubikmono","size":250},{"type":"text-set","target":"t2","font":"rubikmono","size":190}]
V["19-hard-shadow"]=[{"type":"layer-style","target":"hand","name":"drop-shadow","settings":{"color":"#d4241c","dx":40,"dy":40,"blur":0,"opacity":1}}]
V["20-cream-head"]=[{"type":"shape","target":"mhead","fill":"#d4241c","stroke":"#141414"},{"type":"shape","target":"stick","fill":"#141414"}]
for k,v in V.items(): json.dump(v,open(f"/home/user/Vixl/friends-and-flames/ops/r9-{k}.json","w"))
print(" ".join(V))
