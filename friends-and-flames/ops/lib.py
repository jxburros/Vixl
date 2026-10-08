import json, sys
OPS = '/home/user/Vixl/friends-and-flames/ops/'
def save(name, ops):
    json.dump(ops, open(OPS+name+'.json','w'), indent=1)
    print('friends-and-flames/ops/'+name+'.json', len(ops))

def flame(cx, base, h, prefix='flame', glow='#ff8a1e', core='#fff6d8', w=None):
    """Teardrop candle/match flame whose bottom centre sits at (cx, base)."""
    w = w or h*0.42
    path = (f"M{w/2:.1f} 0 C {w*0.62:.1f} {h*0.25:.1f} {w:.1f} {h*0.5:.1f} {w*0.96:.1f} {h*0.74:.1f} "
            f"C {w*0.92:.1f} {h*0.92:.1f} {w*0.72:.1f} {h:.1f} {w/2:.1f} {h:.1f} "
            f"C {w*0.28:.1f} {h:.1f} {w*0.08:.1f} {h*0.92:.1f} {w*0.04:.1f} {h*0.74:.1f} "
            f"C 0 {h*0.5:.1f} {w*0.38:.1f} {h*0.25:.1f} {w/2:.1f} 0 Z")
    cw, ch = w*0.5, h*0.5
    cpath = (f"M{cw/2:.1f} 0 C {cw*0.7:.1f} {ch*0.3:.1f} {cw:.1f} {ch*0.55:.1f} {cw:.1f} {ch*0.75:.1f} "
             f"C {cw:.1f} {ch*0.95:.1f} {cw*0.75:.1f} {ch:.1f} {cw/2:.1f} {ch:.1f} "
             f"C {cw*0.25:.1f} {ch:.1f} 0 {ch*0.95:.1f} 0 {ch*0.75:.1f} "
             f"C 0 {ch*0.55:.1f} {cw*0.3:.1f} {ch*0.3:.1f} {cw/2:.1f} 0 Z")
    return [
      {"type":"shape","shape":"path","name":prefix+"-outer","path":path,"x":cx-w/2,"y":base-h,"width":w,"height":h,"fill":"#ffb43a"},
      {"type":"layer-style","target":prefix+"-outer","name":"gradient-overlay","settings":{"direction":"vertical","stops":[
          {"offset":0,"color":"#ff6a00"},{"offset":0.35,"color":"#ff9a1f"},{"offset":0.75,"color":"#ffd25a"},{"offset":1,"color":"#fff1c2"}]}},
      {"type":"layer-style","target":prefix+"-outer","name":"outer-glow","settings":{"color":glow,"blur":min(100,h*0.35),"opacity":0.9}},
      {"type":"effect","target":prefix+"-outer","name":"gaussian-blur","amount":max(2,h*0.012)},
      {"type":"shape","shape":"path","name":prefix+"-core","path":cpath,"x":cx-cw/2,"y":base-ch*1.02,"width":cw,"height":ch,"fill":core},
      {"type":"effect","target":prefix+"-core","name":"gaussian-blur","amount":max(2,h*0.02)},
      {"type":"shape","shape":"ellipse","name":prefix+"-blue","x":cx-w*0.22,"y":base-h*0.1,"width":w*0.44,"height":h*0.13,"fill":"#3a6cff","opacity":0.55},
      {"type":"effect","target":prefix+"-blue","name":"gaussian-blur","amount":max(2,h*0.02)},
    ]

def match(cx, top, length, wd, prefix='match'):
    """Stick from y=top down by length; head on top. Returns (stick_ops, head_ops)."""
    stick = [{"type":"shape","shape":"rounded-rectangle","name":prefix+"-stick","x":cx-wd/2,"y":top,"width":wd,"height":length,"radius":wd*0.2,"fill":"#c99a5c"},
             {"type":"layer-style","target":prefix+"-stick","name":"gradient-overlay","settings":{"direction":"horizontal","stops":[
               {"offset":0,"color":"#7a5430"},{"offset":0.35,"color":"#e8c48c"},{"offset":0.7,"color":"#c49056"},{"offset":1,"color":"#5e3d20"}]}},
             {"type":"shape","shape":"rounded-rectangle","name":prefix+"-char","x":cx-wd/2,"y":top,"width":wd,"height":length*0.18,"radius":wd*0.2,"fill":"#1c0d06"},
             {"type":"layer-style","target":prefix+"-char","name":"gradient-overlay","settings":{"direction":"vertical","stops":[
               {"offset":0,"color":"#120804"},{"offset":0.7,"color":"#3a1d0c"},{"offset":1,"color":"#3a1d0c00"}]}}]
    head = [{"type":"shape","shape":"ellipse","name":prefix+"-head","x":cx-wd*0.78,"y":top-wd*1.3,"width":wd*1.56,"height":wd*2.2,"fill":"#2a120a"},
            {"type":"layer-style","target":prefix+"-head","name":"gradient-overlay","settings":{"direction":"horizontal","stops":[
               {"offset":0,"color":"#140805"},{"offset":0.4,"color":"#5a2614"},{"offset":1,"color":"#120604"}]}}]
    return stick, head

def pa(x, y, w):
    return [{"type":"resize","target":"parental-advisory","width":w,"keep_aspect":True},
            {"type":"move","target":"parental-advisory","x":x,"y":y},
            {"type":"top","target":"parental-advisory"}]

def text(name, s, font, size, color, x, y, tracking=0, **kw):
    o = [{"type":"text","name":name,"text":s,"font":font,"size":size,"color":color,"x":x,"y":y, **kw}]
    if tracking:
        o.append({"type":"text-style","target":name,"start":0,"end":len(s),"tracking":tracking})
    return o

def tiny_flame(cx, base, h, name, color="#ffb347", glow="#ff7a1a", opacity=1.0):
    w = h*0.45
    path = (f"M{w/2:.1f} 0 C {w*0.7:.1f} {h*0.3:.1f} {w:.1f} {h*0.55:.1f} {w:.1f} {h*0.75:.1f} "
            f"C {w:.1f} {h*0.92:.1f} {w*0.75:.1f} {h:.1f} {w/2:.1f} {h:.1f} C {w*0.25:.1f} {h:.1f} 0 {h*0.92:.1f} 0 {h*0.75:.1f} "
            f"C 0 {h*0.55:.1f} {w*0.3:.1f} {h*0.3:.1f} {w/2:.1f} 0 Z")
    o = [{"type":"shape","shape":"path","name":name,"path":path,"x":cx-w/2,"y":base-h,"width":w,"height":h,"fill":color,"opacity":opacity}]
    if glow:
        o.append({"type":"layer-style","target":name,"name":"outer-glow","settings":{"color":glow,"blur":min(100,max(4,h*0.9)),"opacity":0.85}})
    return o
REMOVE_BASE = ["title","artist"]

STRIP_BASE = ["ambient","handlight","match-stick","match-char","match-head","flame-outer","flame-core","flame-blue","title","artist"]
def strip(keep=()):
    t=[n for n in STRIP_BASE if n not in keep]
    return [{"type":"remove","targets":t}] if t else []
def clear_hand_fx():
    return [{"type":"effect-remove","target":"hand","effect":e} for e in ("temperature","exposure","contrast","grain")]

def strip_all():
    return strip() + [{"type":"remove","target":"hand"}]
def fpath(w,h):
    return (f"M{w/2:.1f} 0 C {w*0.62:.1f} {h*0.25:.1f} {w:.1f} {h*0.5:.1f} {w*0.96:.1f} {h*0.74:.1f} C {w*0.92:.1f} {h*0.92:.1f} {w*0.72:.1f} {h:.1f} {w/2:.1f} {h:.1f} "
            f"C {w*0.28:.1f} {h:.1f} {w*0.08:.1f} {h*0.92:.1f} {w*0.04:.1f} {h*0.74:.1f} C 0 {h*0.5:.1f} {w*0.38:.1f} {h*0.25:.1f} {w/2:.1f} 0 Z")
def fshape(name,cx,base,w,h,fill,**kw):
    return {"type":"shape","shape":"path","name":name,"path":fpath(w,h),"x":cx-w/2,"y":base-h,"width":w,"height":h,"fill":fill,**kw}

def person(x, base, s, arm=0, torch=False):
    """Silhouette subpaths (absolute canvas coords). arm: 0 none, 1 right arm raised, -1 left."""
    r=32*s
    hy=base-175*s
    p=[f"M{x-r:.0f} {hy:.0f} a{r:.0f} {r:.0f} 0 1 0 {2*r:.0f} 0 a{r:.0f} {r:.0f} 0 1 0 {-2*r:.0f} 0 Z",
       f"M{x-80*s:.0f} {base+400*s:.0f} L{x-72*s:.0f} {base-95*s:.0f} Q{x-70*s:.0f} {base-135*s:.0f} {x-30*s:.0f} {base-138*s:.0f} L{x+30*s:.0f} {base-138*s:.0f} Q{x+70*s:.0f} {base-135*s:.0f} {x+72*s:.0f} {base-95*s:.0f} L{x+80*s:.0f} {base+400*s:.0f} Z"]
    tip=None
    if arm:
        sx=x+arm*55*s; sy=base-120*s; ex=x+arm*95*s; ey=base-330*s; w=16*s
        p.append(f"M{sx-w:.0f} {sy:.0f} L{ex-w:.0f} {ey:.0f} L{ex+w:.0f} {ey:.0f} L{sx+w:.0f} {sy:.0f} Z")
        if torch:
            p.append(f"M{ex-7*s:.0f} {ey+20*s:.0f} L{ex-9*s:.0f} {ey-90*s:.0f} L{ex+9*s:.0f} {ey-90*s:.0f} L{ex+7*s:.0f} {ey+20*s:.0f} Z")
            tip=(ex, ey-88*s)
        else:
            p.append(f"M{ex-22*s:.0f} {ey:.0f} a{22*s:.0f} {26*s:.0f} 0 1 0 {44*s:.0f} 0 a{22*s:.0f} {26*s:.0f} 0 1 0 {-44*s:.0f} 0 Z")
    return p, tip
def flame_sub(cx, base, w, h):
    return (f"M{cx:.0f} {base-h:.0f} C {cx+w*0.12:.0f} {base-h*0.75:.0f} {cx+w*0.5:.0f} {base-h*0.5:.0f} {cx+w*0.46:.0f} {base-h*0.26:.0f} "
            f"C {cx+w*0.42:.0f} {base-h*0.08:.0f} {cx+w*0.22:.0f} {base:.0f} {cx:.0f} {base:.0f} C {cx-w*0.22:.0f} {base:.0f} {cx-w*0.42:.0f} {base-h*0.08:.0f} {cx-w*0.46:.0f} {base-h*0.26:.0f} "
            f"C {cx-w*0.5:.0f} {base-h*0.5:.0f} {cx-w*0.12:.0f} {base-h*0.75:.0f} {cx:.0f} {base-h:.0f} Z")

import math as _m
def _tf(pts, ox, oy, ang):
    c,s=_m.cos(ang),_m.sin(ang)
    return [(ox+x*c-y*s, oy+x*s+y*c) for x,y in pts]
def flame_rot(ox, oy, w, h, ang):
    """Flame with its base at (ox,oy), tip pointing along screen angle ang (radians; -pi/2 = up)."""
    # local frame: base at origin, tip at (0,-h) pointing up; rotate so 'up' maps to ang
    P=[(0,-h),(w*0.12,-h*0.75),(w*0.5,-h*0.5),(w*0.46,-h*0.26),(w*0.42,-h*0.08),(w*0.22,0),(0,0),
       (-w*0.22,0),(-w*0.42,-h*0.08),(-w*0.46,-h*0.26),(-w*0.5,-h*0.5),(-w*0.12,-h*0.75),(0,-h)]
    T=_tf(P,ox,oy,ang+_m.pi/2)
    f=lambda p:f"{p[0]:.0f} {p[1]:.0f}"
    return (f"M{f(T[0])} C {f(T[1])} {f(T[2])} {f(T[3])} C {f(T[4])} {f(T[5])} {f(T[6])} "
            f"C {f(T[7])} {f(T[8])} {f(T[9])} C {f(T[10])} {f(T[11])} {f(T[12])} Z")
def ellipse_rot(cx, cy, rx, ry, ang, n=48):
    P=[(rx*_m.cos(2*_m.pi*i/n), ry*_m.sin(2*_m.pi*i/n)) for i in range(n)]
    T=_tf(P,cx,cy,ang)
    return "M"+" L".join(f"{x:.0f} {y:.0f}" for x,y in T)+" Z"
def rect_rot(cx, cy, w, h, ang, r=0):
    P=[(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]
    T=_tf(P,cx,cy,ang)
    return "M"+" L".join(f"{x:.0f} {y:.0f}" for x,y in T)+" Z"
