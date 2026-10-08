import json, math
src=open('r12.py').read()
exec(src[:src.index('\nV={}')])
CREAM="#efe6d2"
B09=s104(black_ink("hand-black",45))+[{"type":"shape","target":"bar","fill":BLK},{"type":"text-set","target":"artist","color":BLK},{"type":"shape","targets":["flame","mhead"],"fill":BLK}]
ROWSN=[f"row{i}" for i in range(7)]
NAVY_ACC=[{"type":"shape","targets":ROWSN+["qdot"],"fill":NAVY},{"type":"text-set","targets":["q1","q2"],"color":NAVY}]
def reg(name,cx,cy,r=38,w=6):
    p=(f"M{cx-r} {cy}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 {-2*r} 0Z "
       f"M{cx-r*1.6:.0f} {cy}L{cx+r*1.6:.0f} {cy}M{cx} {cy-r*1.6:.0f}L{cx} {cy+r*1.6:.0f}")
    return {"type":"shape","shape":"path","name":name,"path":p,"x":0,"y":0,"fill":"#00000000","stroke":NAVY,"stroke_width":w}
REG=[reg("reg1",90,90),reg("reg2",2910,90),reg("reg3",70,1500),reg("reg4",2930,1500)]
def bracket(name,x,y,dx,dy,L=150):
    return {"type":"shape","shape":"path","name":name,"path":f"M{x+dx*L} {y}L{x} {y}L{x} {y+dy*L}","x":0,"y":0,"fill":"#00000000","stroke":NAVY,"stroke_width":12,"line_cap":"square"}
V={}
V["01-navy-accents"]=B09+NAVY_ACC
V["02-registration-marks"]=B09+NAVY_ACC+REG
V["03-corner-brackets"]=B09+NAVY_ACC+[bracket("br1",60,60,1,1),bracket("br2",2940,60,-1,1),bracket("br3",60,2940,1,-1),bracket("br4",2940,2940,-1,-1)]
V["04-double-rule"]=B09+NAVY_ACC+[{"type":"shape","shape":"rectangle","name":"rule1","x":152,"y":826,"width":680,"height":8,"fill":NAVY},
                                  {"type":"shape","shape":"rectangle","name":"rule2","x":152,"y":842,"width":680,"height":3,"fill":NAVY},
                                  {"type":"move","targets":["q1","q2","qdot","qdot-f"],"x":0,"y":22,"relative":True}]
V["05-sun-ring"]=B09+NAVY_ACC+[{"type":"shape","shape":"ellipse","name":"ring","x":1322,"y":40,"width":1020,"height":1020,"fill":"#00000000","stroke":NAVY,"stroke_width":10},
                               {"type":"reorder","target":"ring","above":"sun"}]
V["06-small-seal"]=B09+NAVY_ACC+[{"type":"shape","shape":"ellipse","name":"seal","x":2490,"y":150,"width":340,"height":340,"fill":NAVY},
     {"type":"shape","shape":"ellipse","name":"seal-ring","x":2512,"y":172,"width":296,"height":296,"fill":"#00000000","stroke":CREAM,"stroke_width":5},
     {"type":"text","name":"seal-text","text":"SINGLE\n2026","font":"anton","size":72,"color":CREAM,"align":"center","line_height":1.0,"within":"seal"}]
dots=[]
for j in range(7):
    for i in range(7-j):
        cx,cy=2860-i*44,170+j*44; r=12-j*1.2-i*0.8
        if r>3: dots.append(f"M{cx-r:.0f} {cy}a{r:.1f} {r:.1f} 0 1 0 {2*r:.1f} 0a{r:.1f} {r:.1f} 0 1 0 {-2*r:.1f} 0Z")
V["07-dot-cluster"]=B09+NAVY_ACC+[{"type":"shape","shape":"path","name":"dots","path":"".join(dots),"x":0,"y":0,"fill":NAVY}]
V["08-navy-flame-and-marks"]=B09+NAVY_ACC+REG+[{"type":"shape","targets":["flame","mhead"],"fill":NAVY}]
V["09-navy-name-and-marks"]=B09+REG+[{"type":"text-set","target":"artist","color":NAVY},{"type":"shape","targets":ROWSN[::2],"fill":NAVY}]
for k,v in V.items(): json.dump(v,open(f"/home/user/Vixl/friends-and-flames/ops/r13-{k}.json","w"))
print(" ".join(V))
