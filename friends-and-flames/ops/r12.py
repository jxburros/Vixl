import json
exec(open('r10.py').read().split('V={}')[0]); _s=open('r11.py').read(); exec(_s[_s.index('RED="'):_s.index('NAVY=')+20])
BLK="#141414"
def s104(pre=()):
    return list(pre)+s1(blk=NAVY)+[{"type":"shape","targets":["bar","flame","mhead"],"fill":NAVY},{"type":"text-set","target":"artist","color":NAVY}]
def black_ink(name,t,dx=0,dy=0):
    return ink_copy(name,[{"name":"threshold","amount":t},{"name":"duotone","shadow_color":BLK,"highlight_color":"#ffffff"}],dx,dy,below=False)
V={}
V["01-black-bar"]=s104()+[{"type":"shape","target":"bar","fill":BLK}]
V["02-black-name-and-flame"]=s104()+[{"type":"text-set","target":"artist","color":BLK},{"type":"shape","targets":["flame","mhead"],"fill":BLK}]
V["03-black-deep-shadows"]=s104(black_ink("hand-black",45))
V["04-black-offset-ink"]=s104(black_ink("hand-black",70,-30,24))
V["05-black-title"]=s104()+[{"type":"text-set","target":"t1","color":BLK}]
V["06-layered-black-bar"]=s104()+[{"type":"duplicate","target":"bar","name":"bar-black"},{"type":"shape","target":"bar-black","fill":BLK},
  {"type":"move","target":"bar-black","x":-40,"y":95,"relative":True},{"type":"reorder","target":"bar-black","below":"bar"}]
V["07-black-frame"]=s104()+[{"type":"shape","shape":"rectangle","name":"frame","x":0,"y":0,"width":3000,"height":3000,"fill":"#00000000","stroke":BLK,"stroke_width":60,"stroke_align":"inside"},{"type":"move","target":"parental-advisory","x":2470,"y":2660},{"type":"top","target":"parental-advisory"}]
V["08-black-sun-ring-and-flames"]=s104()+[{"type":"shape","target":"sun","stroke":BLK,"stroke_width":22},{"type":"shape","targets":[f"row{i}" for i in range(7)]+["qdot"],"fill":BLK},{"type":"text-set","targets":["q1","q2"],"color":BLK}]
V["09-most-black"]=s104(black_ink("hand-black",45))+[{"type":"shape","target":"bar","fill":BLK},{"type":"text-set","target":"artist","color":BLK},{"type":"shape","targets":["flame","mhead"],"fill":BLK}]
for k,v in V.items(): json.dump(v,open(f"/home/user/Vixl/friends-and-flames/ops/r12-{k}.json","w"))
print(" ".join(V))
