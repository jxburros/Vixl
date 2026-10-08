# 1 + 5: riso duotone in the dark, real flame
from lib import *
PINK="#ff48b0"; BLUE="#3a6bff"
ops = [{"type":"remove","targets":["title","artist","handlight"]}] + [
 {"type":"effect-remove","target":"hand","effect":e} for e in ("temperature","exposure","contrast")] + [
 {"type":"effect","target":"hand","name":"levels","black":30,"white":160},
 {"type":"effect","target":"hand","name":"duotone","shadow_color":"#0a0820","highlight_color":"#4f7dff"},
 {"type":"gradient","name":"rim","x":-1168,"y":-2600,"width":6000,"height":6000,"direction":"radial","falloff":"smooth",
  "stops":[{"offset":0,"color":"#ffd2a0"},{"offset":0.13,"color":"#ff6ab8"},{"offset":0.35,"color":"#3a2a80"},{"offset":1,"color":"#05040f"}]},
 {"type":"blend","target":"rim","value":"overlay"},{"type":"reorder","target":"rim","above":"hand"},{"type":"clip","target":"rim","base":"hand"},
]
for nm,txt,y in [("w1","FRIENDS",1930),("w2","& FLAMES",2360)]:
    ops += text(nm+"b",txt,"grotesk",420,BLUE,100,y+14,-6) + text(nm,txt,"grotesk",420,PINK,84,y,-6)
    ops += [{"type":"blend","target":nm,"value":"screen"},{"type":"opacity","target":nm+"b","value":0.8}]
ops += text("artist","JEFFREY X GUNTLY","grotesk",64,PINK,100,110,18)
ops += pa(2500,2650,400)
save('c23',ops)
