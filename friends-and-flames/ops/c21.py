# 1 + 9: dark swiss — keeps the lit match scene from cover 1
from lib import *
W="#efe6d8"
ops = [{"type":"remove","targets":["title","artist"]}]
for x in (150,1500,2850): ops.append({"type":"shape","shape":"rectangle","name":f"v{x}","x":x,"y":150,"width":2,"height":2700,"fill":"#efe6d826"})
ops += [{"type":"shape","shape":"rectangle","name":"hr","x":150,"y":1960,"width":2700,"height":3,"fill":"#efe6d880"}]
ops += text("num","01","grotesk",110,W,2660,170)
ops += text("t1","Friends","grotesk",250,W,140,2000,-8)
ops += text("t2","and Flames.","grotesk",250,W,140,2260,-8)
ops += [{"type":"text-style","target":"t2","match":"Flames.","color":"#ff9a3c"}]
ops += text("artist","Jeffrey X Guntly","inter",56,W,1530,2010)
ops += text("meta","Let’s get all our friends.\nLet’s start a little fire.","inter",42,"#bfb3a2",1530,2100,line_height=1.4)
ops += text("label","SINGLE","grotesk",40,W,160,170,8)
ops += pa(2500,2650,400)
save('c21',ops)
