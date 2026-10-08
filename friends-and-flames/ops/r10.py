import json, math
ROWS=[f"row{i}" for i in range(7)]; ROWF=[r+"-f" for r in ROWS]
def rowcols(cols): return [{"type":"shape","target":r,"fill":cols[i%len(cols)]} for i,r in enumerate(ROWS)]
def base(paper,sun,flame,facet,t1,bar,t2,name,quote,rows,light=None,stick="#e9c48a",ink="#141414"):
    light=light or paper
    return ([{"type":"solid","target":"paper","color":paper},{"type":"shape","target":"sun","fill":sun},
             {"type":"shape","target":"flame","fill":flame},{"type":"shape","target":"flame-f","fill":facet},
             {"type":"shape","target":"mhead","fill":flame,"stroke":light},{"type":"shape","target":"stick","fill":stick,"stroke":ink},
             {"type":"text-set","target":"t1","color":t1},{"type":"layer-style","target":"t1","name":"stroke","settings":{"color":paper,"width":12}},
             {"type":"shape","target":"bar","fill":bar},{"type":"text-set","target":"t2","color":t2},
             {"type":"text-set","target":"artist","color":name},{"type":"text-set","targets":["q1","q2"],"color":quote},
             {"type":"shape","target":"qdot","fill":quote},{"type":"shape","targets":ROWF+["qdot-f"],"fill":light}]
            + rowcols(rows))
def handtone(sh,hi): return [{"type":"effect","target":"hand","name":"duotone","shadow_color":sh,"highlight_color":hi}]
def dots(name,color,r,step,box=(0,0,3000,3000),opacity=1.0):
    x0,y0,w,h=box; parts=[]
    for j,y in enumerate(range(y0,y0+h+step,step)):
        for x in range(x0+(step//2 if j%2 else 0),x0+w+step,step):
            parts.append(f"M{x-r} {y}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 {-2*r} 0Z")
    out=[]; n=0
    for i in range(0,len(parts),500):
        out.append({"type":"shape","shape":"path","name":f"{name}{n}","path":"".join(parts[i:i+500]),"x":0,"y":0,"fill":color,"opacity":opacity}); n+=1
    out.append({"type":"group","name":name,"targets":[f"{name}{j}" for j in range(n)]})
    return out
def ink_copy(name,effects,dx,dy,below=True):
    o=[{"type":"duplicate","target":"hand","name":name}]
    o+=[{"type":"effect","target":name,**e} for e in effects]
    o+=[{"type":"move","target":name,"x":dx,"y":dy,"relative":True},{"type":"blend","target":name,"value":"multiply"}]
    if below: o.append({"type":"reorder","target":name,"below":"hand"})
    return o
V={}
# ---------- expanded palettes ----------
V["E1-sunset"]=base("#f6ead3","#f05a28","#2b1d3a","#ffd166","#e63946","#264653","#e9c46a","#264653","#2a9d8f",
                    ["#e63946","#f4a261","#e9c46a","#2a9d8f","#264653","#f4a261","#e63946"])
V["E2-protest-primaries"]=base("#f3ecdc","#d62828","#141414","#f3ecdc","#d62828","#1d3fbb","#ffd400","#141414","#1d3fbb",
                    ["#d62828","#ffd400","#1d3fbb"])
V["E3-earth"]=base("#efe3cc","#c1440e","#3d405b","#f2cc8f","#c1440e","#3d405b","#f2cc8f","#3d405b","#81b29a",
                    ["#c1440e","#e07a5f","#f2cc8f","#81b29a","#3d405b"])+handtone("#3d405b","#efe3cc")
V["E4-neon-night"]=base("#1a1033","#ff3c8e","#1a1033","#00e5ff","#ffe600","#00e5ff","#1a1033","#ffffff","#00e5ff",
                    ["#ff3c8e","#ffe600","#00e5ff","#7cff6b"],light="#1a1033",ink="#1a1033")
# ---------- screenprint hand ----------
V["S1-two-ink-misregistered"]=ink_copy("hand-red",[{"name":"threshold","amount":150},
        {"name":"duotone","shadow_color":"#d4241c","highlight_color":"#ffffff"}],24,-16)+[
    {"type":"effect","target":"hand","name":"threshold","amount":105},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#141414","highlight_color":"#ffffff"},
    {"type":"blend","target":"hand","value":"multiply"},{"type":"look","target":"paper","look":"paper","amount":0.6}]
V["S2-halftone-navy-red"]=ink_copy("hand-red",[{"name":"threshold","amount":120},
        {"name":"duotone","shadow_color":"#d4241c","highlight_color":"#ffffff"}],30,24)+[
    {"type":"effect","target":"hand","name":"halftone","amount":18},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#1b2a41","highlight_color":"#ffffff"},
    {"type":"blend","target":"hand","value":"multiply"},
    {"type":"shape","target":"bar","fill":"#1b2a41"},{"type":"shape","target":"flame","fill":"#1b2a41"},{"type":"shape","target":"mhead","fill":"#1b2a41"},
    {"type":"text-set","target":"artist","color":"#1b2a41"}]
V["S3-posterized-red-black"]=[{"type":"effect","target":"hand","name":"posterize","amount":2},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#141414","highlight_color":"#e8584e"},
    {"type":"look","target":"paper","look":"paper","amount":0.6}]
V["S4-silhouette-and-ink"]=ink_copy("hand-red",[{"name":"threshold","amount":0},
        {"name":"duotone","shadow_color":"#d4241c","highlight_color":"#d4241c"}],-30,26)+[
    {"type":"effect","target":"hand","name":"threshold","amount":95},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#141414","highlight_color":"#ffffff"},
    {"type":"blend","target":"hand","value":"multiply"},{"type":"look","target":"paper","look":"paper","amount":0.6}]
# ---------- pop art ----------
OUT={"type":"layer-style","target":"hand","name":"stroke","settings":{"color":"#141414","width":18}}
V["P1-ben-day"]=base("#ffe14d","#00a6d6","#141414","#ffffff","#e4002b","#141414","#ffffff","#141414","#e4002b",["#e4002b"],light="#ffffff")+[
    *dots("bendots","#f28c28",11,52,opacity=0.55),{"type":"reorder","target":"bendots","above":"paper"},
    {"type":"effect","target":"hand","name":"posterize","amount":2},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#141414","highlight_color":"#ffffff"},OUT,
    {"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#141414","width":14}}]
V["P2-warhol"]=base("#ff4fa3","#00c2d1","#2a1a6e","#ffe14d","#ffe14d","#2a1a6e","#ffe14d","#2a1a6e","#2a1a6e",["#ffe14d"],light="#2a1a6e")+[
    {"type":"effect","target":"hand","name":"posterize","amount":2},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#2a1a6e","highlight_color":"#ffe14d"},
    {"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#2a1a6e","width":14}}]
V["P3-comic-burst"]=base("#8fd3f4","#ffd400","#141414","#ffffff","#e4002b","#141414","#ffffff","#141414","#141414",["#e4002b"],light="#ffffff")+[
    {"type":"remove","target":"sun"},
    {"type":"shape","shape":"burst","name":"burst","x":1302,"y":20,"width":1060,"height":1060,"fill":"#ffd400","stroke":"#141414","stroke_width":16,"count":18},
    {"type":"reorder","target":"burst","above":"paper"},
    *dots("bendots","#2d7fd3",10,48,opacity=0.5),{"type":"reorder","target":"bendots","above":"paper"},
    {"type":"effect","target":"hand","name":"halftone","amount":16},OUT,
    {"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#141414","width":14}},
    {"type":"layer-style","target":"t1","name":"drop-shadow","settings":{"color":"#141414","dx":16,"dy":16,"blur":0,"opacity":1}}]
V["P4-lichtenstein"]=base("#ffffff","#ffd400","#141414","#ffffff","#e4002b","#1d4ed8","#ffffff","#141414","#1d4ed8",["#e4002b"],light="#ffffff")+[
    {"type":"shape","target":"sun","stroke":"#141414","stroke_width":16},
    {"type":"effect","target":"hand","name":"threshold","amount":55},
    {"type":"effect","target":"hand","name":"duotone","shadow_color":"#141414","highlight_color":"#f6d2b0"},OUT,
    *dots("skindots","#e4002b",9,40,box=(0,350,2700,2650),opacity=0.45),{"type":"reorder","target":"skindots","above":"hand"},
    {"type":"clip","target":"skindots","base":"hand"},
    {"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#141414","width":14}}]
for k,v in V.items(): json.dump(v,open(f"/home/user/Vixl/friends-and-flames/ops/r10-{k}.json","w"))
print(" ".join(V))
