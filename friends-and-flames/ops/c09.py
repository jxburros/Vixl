from lib import *
BG="#f1efe9"; INK="#111111"; RED="#e4321b"
ops = strip_all() + [{"type":"solid","name":"bg","color":BG},{"type":"bottom","target":"bg"}]
# swiss grid rules
for x in (150,1500,2850): ops.append({"type":"shape","shape":"rectangle","name":f"v{x}","x":x,"y":150,"width":3,"height":2700,"fill":"#11111122"})
ops += [{"type":"shape","shape":"rectangle","name":"hr","x":150,"y":1500,"width":2700,"height":6,"fill":INK}]
# one matchstick on the diagonal, lit
ops += [{"type":"shape","shape":"rounded-rectangle","name":"stick","x":2100,"y":700,"width":44,"height":1400,"radius":8,"fill":"#d9b98a","rotation":28},
        {"type":"shape","shape":"ellipse","name":"head","x":2406,"y":712,"width":90,"height":140,"fill":"#3b1a10","rotation":28}]
ops += [fshape("fl",2445,745,190,420,RED)]
ops += text("t1","Friends","grotesk",330,INK,150,1560,-10)
ops += text("t2","and","grotesk",330,INK,150,1900,-10)
ops += text("t3","Flames.","grotesk",330,RED,150,2240,-10)
ops += text("artist","Jeffrey X Guntly","inter",60,INK,1530,1560)
ops += text("meta","Single — 2026\nLet’s get all our friends.\nLet’s start a little fire.","inter",44,"#555555",1530,1660,line_height=1.4)
ops += text("num","01","grotesk",120,INK,2650,180)
ops += pa(2470,2620,380)
save('c09',ops)
