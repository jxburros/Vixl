from lib import *
cx, pinch = 1832, 852
stick, head = match(cx, 600, 330, 40)
ops = [{"type":"move","target":"hand","x":-60,"y":-480},
  {"type":"gradient","name":"ambient","x":cx-1400,"y":420-1400,"width":2800,"height":2800,"direction":"radial","falloff":"gaussian",
   "stops":[{"offset":0,"color":"#ff9a3a59"},{"offset":0.45,"color":"#a8441214"},{"offset":1,"color":"#00000000"}]},
  {"type":"blend","target":"ambient","value":"screen"},
] + stick + [{"type":"bottom","target":"match-char"},{"type":"bottom","target":"match-stick"},{"type":"bottom","target":"ambient"}] + head + flame(cx, 560, 470) + [
  {"type":"effect","target":"hand","name":"temperature","amount":0.35},
  {"type":"lighting","lights":[{"x":cx,"y":380,"radius":1700,"intensity":1.6,"color":"#ffb060"}],"ambient":0.18,"vignette":0.55,"saturation":1.1},
] + text("title","Friends and Flames","serif",70,"#e9dfd0",100,96,5) + text("artist","Jeffrey X Guntly","serif",70,"#e9dfd0",2300,96,5) + pa(2500, 2650, 400)
save('c01', ops)
