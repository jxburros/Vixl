from lib import *
from lib import _tf
import math, json
RED="#d4241c"; CREAM="#efe6d2"; BLK="#141414"
def facet_paths(cx, base, w, h, ang=-math.pi/2):
    """Faceted flame (outer pentagon + right-hand light facet), base centre at (cx,base), tip along ang."""
    outer=[(0,-h),(w/2,-0.38*h),(0.3*w,0),(-0.3*w,0),(-w/2,-0.38*h)]
    facet=[(0,-0.6*h),(0.25*w,-0.28*h),(0.12*w,-0.07*h),(0,-0.07*h)]
    def poly(P):
        T=_tf(P,cx,base,ang+math.pi/2)
        return "M"+" L".join(f"{x:.0f} {y:.0f}" for x,y in T)+" Z"
    return poly(outer), poly(facet)
def facet(name, cx, base, w, h, fill, light, ang=None):
    # the exact construction of the cover-7 flame: pentagon plus a half-size light pentagon, bottom-aligned
    p=f"M{w/2:.1f} 0 L {w:.1f} {h*0.62:.1f} L {w*0.8:.1f} {h:.1f} L {w*0.2:.1f} {h:.1f} L 0 {h*0.62:.1f} Z"
    return [{"type":"shape","shape":"path","name":name,"path":p,"x":cx-w/2,"y":base-h,"width":w,"height":h,"fill":fill},
            {"type":"shape","shape":"path","name":name+"-f","path":p,"x":cx-w*0.25,"y":base-h*0.5,"width":w*0.5,"height":h*0.5,"fill":light}]
def build(v):
    sun_fill, flame, light, bar, t1c, row = {
        "A":(RED,BLK,CREAM,BLK,RED,RED),
        "B":(BLK,RED,CREAM,RED,BLK,RED),
        "C":(RED,BLK,CREAM,BLK,RED,BLK)}[v]
    cx=1832
    ops=[{"type":"remove","targets":["stick","fl","flc","slogan","slog-rule","artist"]},
         {"type":"shape","target":"sun","fill":sun_fill},
         {"type":"shape","target":"bar","fill":bar},{"type":"text-set","target":"t1","color":t1c}]
    if v=="C":   # rays of small flames around the sun
        for i in range(16):
            a=2*math.pi*i/16-math.pi/2
            deg=math.degrees(a)%360
            if 50<deg<130: continue          # keep the hand clear
            r=540
            ops+=facet(f"ray{i}",cx+r*math.cos(a),550+r*math.sin(a)+65,70,130,RED,CREAM)
    # the match: stick held by the fingertips (under the hand), head, faceted flame
    stick_c = CREAM if v=="B" else "#e8d3a8"
    ops+=[{"type":"shape","shape":"rounded-rectangle","name":"stick","x":cx-20,"y":610,"width":40,"height":330,"radius":6,"fill":stick_c,"stroke":BLK,"stroke_width":8},
          {"type":"reorder","target":"stick","below":"hand"},
          {"type":"shape","shape":"path","name":"mhead","path":ellipse_rot(cx,610,40,62,math.pi/2),"x":0,"y":0,"fill":BLK if v!="B" else RED,"stroke":CREAM,"stroke_width":10}]
    ops+=facet("flame",cx,590,260,470,flame,light)
    # name big, motif row, small quote
    ops+=text("artist","JEFFREY X\nGUNTLY","anton",250,BLK,150,110,4,line_height=0.92)
    for i in range(7):
        ops+=facet(f"row{i}",185+i*100,810,64,118,row,CREAM)
    ops+=text("q1","WE ARE STRONGER","anton",80,RED if v!="B" else BLK,152,855,3)
    ops+=text("q2","THAN YOU ALONE","anton",80,RED if v!="B" else BLK,152,945,3)
    ops+=facet("qdot",705,1037,40,72,RED if v!="B" else BLK,CREAM)
    return ops
for v in "ABC":
    json.dump(build(v),open(f"/home/user/Vixl/friends-and-flames/ops/r4-{v}.json","w"))
print("ok")
