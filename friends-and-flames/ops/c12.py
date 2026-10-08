from lib import *
W="#f2f2ee"; R="#ff3b1f"
ops = strip_all() + [{"type":"solid","name":"bg","color":"#0b0b0b"},{"type":"bottom","target":"bg"}]
for y in (150,1050,2560,2850): ops.append({"type":"shape","shape":"rectangle","name":f"h{y}","x":150,"y":y,"width":2700,"height":4,"fill":W})
ops += text("lbl1","(01) FRIENDS AND FLAMES","grotesk",46,W,150,80,4)
ops += text("lbl2","JEFFREY X GUNTLY","grotesk",46,W,1950,80,4)
ops += text("t1","FRIENDS","rubikmono",370,W,140,280)
ops += text("amp","&","rubikmono",620,R,2310,620)
ops += text("t2","FLAMES","rubikmono",440,W,140,1300)
ops += [{"type":"layer-style","target":"t2","name":"gradient-overlay","settings":{"direction":"vertical","stops":[{"offset":0,"color":"#fff3b0"},{"offset":0.35,"color":"#ffb020"},{"offset":0.7,"color":"#ff3b1f"},{"offset":1,"color":"#7a0c06"}]}},
        {"type":"layer-style","target":"t2","name":"outer-glow","settings":{"color":"#ff4a1a","blur":60,"opacity":0.6}}]
ops += text("ly","WE'RE COMING FOR YOU,\nAND THAT'S THE FUCKING TRUTH.","grotesk",92,W,150,2000,0,line_height=1.05)
ops += text("ly2","LET'S GET ALL OUR FRIENDS / LET'S START A LITTLE FIRE / WE'LL MARCH UP TO THE STAGE / AND TURN THE VOLUME HIGHER","grotesk",38,"#8a8a86",150,2620,2)
ops += [{"type":"shape","shape":"rectangle","name":"box","x":150,"y":1880,"width":90,"height":90,"fill":R}]
ops += pa(2470,2660,380)
save('c12',ops)
