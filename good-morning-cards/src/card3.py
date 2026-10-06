from common import *
import math
W, H = 720, 1000
T = 4000
o = Ops()
# ---------- scene: bright meadow morning ----------
o.add({"type": "gradient", "name": "sky", "x": 0, "y": 0, "width": W, "height": H, "direction": "vertical",
       "stops": [{"offset": 0, "color": "#8FD0FF"}, {"offset": 0.55, "color": "#D5F0FF"}, {"offset": 1, "color": "#FFF4C9"}]})
SX, SY, SR = 632, 430, 46
glow_ops(o, "sun-glow", SX, SY, 250, color="#FFF4A8")
sun_members = sun_ops(o, "sun", SX, SY, SR)
o.add({"type": "group", "name": "sun-g", "targets": sun_members})
o.add({"type": "shape", "shape": "ellipse", "name": "hill-back", "x": -300, "y": 800, "width": 1000, "height": 400, "fill": "#A7DB8B"})
o.add({"type": "shape", "shape": "ellipse", "name": "hill", "x": -80, "y": 880, "width": 1000, "height": 360, "fill": "#7CC25F"})
for i, (cx, cy, w) in enumerate([(30, 420, 170), (470, 640, 120)]):
    o.add({"type": "shape", "shape": "cloud", "name": f"cloud{i}", "x": cx, "y": cy, "width": w, "height": w * 0.5, "fill": "#FFFFFF"})
# ---------- bear (+ held sunflower) ----------
S = 0.84
BX, BY = 262, 978
TH_R_REST, TH_R_UP = 18, -112
TH_L_REST, TH_L_UP = 30, 78
prest = paw_pos("r", TH_R_REST, S)
FR = 70  # flower head radius
STEM = 160
bear_info = build_bear(o, BX, BY, S)
head = group_head(o)
pivot_for(o, "head-g", head, BX, BY - 290 * S)
body_parts = ["foot-l", "sole-l", "foot-r", "sole-r", "body", "tummy", "head-g", "arm-l", "arm-r"]
o.add({"type": "group", "name": "bear", "targets": body_parts})
o.add({"type": "pivot", "target": "bear", "value": "bottom"})
gx, gy = BX + prest[0], BY + prest[1]  # grip point at rest
members, grip = sunflower(o, "sf", gx, gy - STEM, FR, STEM)
ell(o, "sf-grip", gx, gy + 2, 26 * S, 22 * S, CREAM)
members.append("sf-grip")
sp = []
for i, (dx, dy_, sz) in enumerate([(-62, -50, 30), (66, -20, 24), (14, -92, 28)]):
    o.add({"type": "shape", "shape": "sparkle", "name": f"spark{i}", "x": gx + dx - sz / 2, "y": gy - STEM + dy_ - sz / 2, "width": sz, "height": sz, "fill": "#FFFFFF"})
    o.add({"type": "opacity", "target": f"spark{i}", "value": 0})
    members.append(f"spark{i}")
o.add({"type": "group", "name": "flower-g", "targets": members})
o.add({"type": "pivot", "target": "flower-g", "value": [0.5, 0.92]})
# ---------- text ----------
o.add({"type": "text", "name": "greet", "text": "Good Morning,", "font": "heading", "size": 62, "color": "#12467A", "x": "center", "y": 26})
o.add({"type": "text", "name": "daddy", "text": "Daddy!", "font": "heading", "size": 170, "color": "#E8501C", "x": "center", "y": 104})
o.add({"type": "layer-style", "target": "daddy", "name": "stroke", "settings": {"color": "#FFFFFF", "width": 12}})
o.add({"type": "layer-style", "target": "daddy", "name": "drop-shadow", "settings": {"color": "#12467A88", "dx": 0, "dy": 8, "blur": 0, "opacity": 0.3}})
o.add({"type": "text", "name": "sub1", "text": "I picked you the", "font": "body", "size": 38, "color": "#12467A", "x": 150, "y": 322})
o.add({"type": "text", "name": "sub2", "text": "sunniest flower!", "font": "body", "size": 38, "color": "#12467A", "x": 150, "y": 368})
# ---------- animation ----------
def smooth(u): return u * u * (3 - 2 * u)
def back(u, k=1.0):
    c1 = 1.2 * k; c3 = c1 + 1
    v = u - 1
    return 1 + c3 * v ** 3 + c1 * v ** 2
def mix(a, b, u): return a + (b - a) * u
# phase table for the raise/offer/return (times in ms)
R0, R1, H1, L1 = 500, 1300, 2500, 3300
def theta_r(t):
    if t <= R0: return TH_R_REST
    if t < R1: return mix(TH_R_REST, TH_R_UP, back((t - R0) / (R1 - R0), 0.8))
    if t <= H1: return TH_R_UP + 6 * math.sin((t - R1) / 300 * math.pi) * (1 - (t - R1) / (H1 - R1)) * 0  # steady hold
    if t < L1: return mix(TH_R_UP, TH_R_REST, smooth((t - H1) / (L1 - H1)))
    return TH_R_REST
def theta_l(t):
    if t <= R0: return TH_L_REST
    if t < R1: return mix(TH_L_REST, TH_L_UP, smooth((t - R0) / (R1 - R0)))
    if t <= H1: return TH_L_UP + 14 * math.sin((t - R1) / 330 * 2 * math.pi) * smooth(min(1, (t - R1) / 250))   # little wave of encouragement
    if t < L1: return mix(TH_L_UP + 14 * math.sin((H1 - R1) / 330 * 2 * math.pi), TH_L_REST, smooth((t - H1) / (L1 - H1)))
    return TH_L_REST
def flower_sway(t):
    REST = 104
    if t < R0: return REST
    if t < R1: return mix(REST, 18, back((t - R0) / (R1 - R0), 0.5))
    if t <= H1: return 18 + 7 * math.sin((t - R1) / 520 * 2 * math.pi)
    if t < L1: return mix(18 + 7 * math.sin((H1 - R1) / 520 * 2 * math.pi), REST, smooth((t - H1) / (L1 - H1)))
    return REST
STEP = 50
times = list(range(0, T + 1, STEP))
def keys(fn): return [(t, round(fn(t), 3), "linear") for t in times]
kf(o, "arm-r", "rotation", keys(theta_r))
kf(o, "arm-l", "rotation", keys(theta_l))
# flower rides the paw exactly: translation sampled from the same arm angle (no drift between paw and stem)
kf(o, "flower-g", "translate-x", keys(lambda t: paw_pos("r", theta_r(t), S)[0] - prest[0]))
kf(o, "flower-g", "translate-y", keys(lambda t: paw_pos("r", theta_r(t), S)[1] - prest[1]))
kf(o, "flower-g", "rotation", keys(flower_sway))
kf(o, "head-g", "rotation", [(0, 0, "ease-in-out-sine"), (R0, 0, "ease-in-out-sine"), (R1, 6, "ease-in-out-sine"), (H1, 6, "ease-in-out-sine"), (L1, 0, "ease-in-out-sine"), (T, 0)])
kf(o, "bear", "scale-y", [(0, 1, "ease-in-out-sine"), (R0, 0.99, "ease-in-out-sine"), (R1 - 100, 1.025, "ease-out"), (R1 + 150, 0.995, "ease-in-out-sine"), (H1, 1.004, "ease-in-out-sine"), (L1, 1.0, "ease-in-out-sine"), (T, 1)])
kf(o, "bear", "scale-x", [(0, 1, "ease-in-out-sine"), (R0, 1.01, "ease-in-out-sine"), (R1 - 100, 0.985, "ease-out"), (R1 + 150, 1.004, "ease-in-out-sine"), (L1, 1.0, "ease-in-out-sine"), (T, 1)])
for side in "lr":
    for nm, a, b in ((f"eye-{side}", 1, 0), (f"eye-hl-{side}", 1, 0), (f"eye-closed-{side}", 0, 1)):
        kf(o, nm, "opacity", [(0, a, "hold"), (1550, b, "hold"), (2400, a, "hold"), (3640, b, "hold"), (3760, a, "hold"), (T, a)])
    kf(o, f"cheek-{side}", "scale", [(0, 1, "ease-in-out-sine"), (1500, 1.3, "ease-in-out-sine"), (3000, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "mouth-smile", "opacity", [(0, 1, "hold"), (R1, 0, "hold"), (L1, 1, "hold"), (T, 1)])
for nm in ("mouth-open", "tongue"):
    kf(o, nm, "opacity", [(0, 0, "hold"), (R1, 1, "hold"), (L1, 0, "hold"), (T, 0)])
for i in range(3):
    t0 = R1 + 100 + i * 230
    kf(o, f"spark{i}", "opacity", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 150, 1, "ease-in-out-sine"), (t0 + 500, 0, "hold"), (T, 0)])
    kf(o, f"spark{i}", "scale", [(0, 0.2, "hold"), (t0, 0.2, "ease-out"), (t0 + 250, 1.4, "ease-in-out-sine"), (t0 + 500, 0.3, "ease-in"), (T, 0.3)])
    kf(o, f"spark{i}", "rotation", [(0, 0, "hold"), (t0, 0, "linear"), (t0 + 500, 90, "hold"), (T, 90)])
kf(o, "sun-rays", "rotation", [(0, 0, "linear"), (T, 30)])
kf(o, "sun-g", "scale", [(0, 1, "ease-in-out-sine"), (R1, 1, "ease-out"), (R1 + 300, 1.1, "ease-in-out-sine"), (H1, 1.05, "ease-in-out-sine"), (L1, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "sun-glow", "opacity", [(0, 0.75, "ease-in-out-sine"), (R1 + 300, 1, "ease-in-out-sine"), (T, 0.75)])
kf(o, "cloud0", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, 50, "ease-in-out-sine"), (T, 0)])
kf(o, "cloud1", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, -45, "ease-in-out-sine"), (T, 0)])
p, r = make(W, H, "#D5F0FF", o)
print("warnings:", [w for w in (r.get("warnings") or []) if 'cut off' not in w and 'bleeds' not in w])
sheet(p, "c3_sheet.png", [0, 700, 1100, 1500, 1900, 2600, 3000, 3500, 3999], columns=3)
p.save("card3.vixl")
