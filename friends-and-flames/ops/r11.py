import json, re
exec(open('r10.py').read().split('V={}')[0])   # reuse helpers
RED="#d4241c"; BLK="#141414"
def s1(dx=24,dy=-16,red_t=150,blk_t=105,red=RED,blk=BLK,paper_amt=0.6,extra_first=()):
    o=list(extra_first)
    o+=ink_copy("hand-red",[{"name":"threshold","amount":red_t},{"name":"duotone","shadow_color":red,"highlight_color":"#ffffff"}],dx,dy)
    o+=[{"type":"effect","target":"hand","name":"threshold","amount":blk_t},
        {"type":"effect","target":"hand","name":"duotone","shadow_color":blk,"highlight_color":"#ffffff"},
        {"type":"blend","target":"hand","value":"multiply"}]
    if paper_amt: o.append({"type":"look","target":"paper","look":"paper","amount":paper_amt})
    return o
NAVY="#1b2a41"
V={}
V["01-wide-misregister"]=s1(dx=55,dy=-34)
V["02-tight-register"]=s1(dx=10,dy=-6,red_t=175)
V["03-more-red-ink"]=s1(red_t=200,blk_t=75)
V["04-navy-and-red"]=s1(blk=NAVY)+[{"type":"shape","targets":["bar","flame","mhead"],"fill":NAVY},{"type":"text-set","target":"artist","color":NAVY}]
V["05-three-inks"]=ink_copy("hand-yellow",[{"name":"threshold","amount":215},{"name":"duotone","shadow_color":"#f2b81f","highlight_color":"#ffffff"}],-26,28)+s1()
V["06-kraft-paper"]=[{"type":"solid","target":"paper","color":"#cfae84"},{"type":"shape","targets":ROWF+["qdot-f"],"fill":"#cfae84"},{"type":"layer-style","target":"t1","name":"stroke","settings":{"color":"#cfae84","width":12}}]+s1(paper_amt=0.8)
V["07-red-hand-black-shadow"]=s1(red=BLK,blk=RED,red_t=60,blk_t=175,dx=-28,dy=22)
V["08-inky-texture"]=s1(extra_first=())
for e in V["08-inky-texture"]:
    if e.get("name")=="threshold":
        idx=V["08-inky-texture"].index(e); break
def inky(ops):
    out=[]
    for e in ops:
        if e.get("name")=="threshold":
            out.append({**e,"name":"noise","amount":0.14,"seed":5})
            out.append(e)
        else: out.append(e)
    return out
V["08-inky-texture"]=inky(V["08-inky-texture"])
for k,v in V.items(): json.dump(v,open(f"/home/user/Vixl/friends-and-flames/ops/r11-{k}.json","w"))
print(" ".join(V))
