from common import *
W, H = 1000, 750
o = Ops()
# ---------- scene ----------
o.add({"type": "gradient", "name": "sky", "start": "#FFF1BE", "end": "#FFC9A3", "direction": "vertical", "width": W, "height": H, "x": 0, "y": 0})
SX, SY, SR = 855, 150, 62
glow_ops(o, "sun-glow", SX, SY, 330)
o.add({"type": "shape", "shape": "ellipse", "name": "hill-back", "x": -200, "y": 600, "width": 1000, "height": 400, "fill": "#B7DE8B"})
o.add({"type": "shape", "shape": "ellipse", "name": "hill", "x": 150, "y": 640, "width": 1200, "height": 400, "fill": "#8FCB6E"})
for i, (cx, cy, w) in enumerate([(40, 560, 210), (500, 36, 150)]):
    o.add({"type": "shape", "shape": "cloud", "name": f"cloud{i}", "x": cx, "y": cy, "width": w, "height": w * 0.5, "fill": "#FFFFFF"})
    o.add({"type": "opacity", "target": f"cloud{i}", "value": 0.85})
sun_members = sun_ops(o, "sun", SX, SY, SR)
o.add({"type": "group", "name": "sun-g", "targets": sun_members})
# ---------- bear ----------
BX, BY = 672, 706
build_bear(o, BX, BY, 0.96)
head = group_head(o)
pivot_for(o, "head-g", head, BX, BY - 290 * 0.96)
body_parts = ["foot-l", "sole-l", "foot-r", "sole-r", "body", "tummy", "head-g", "arm-l", "arm-r"]
o.add({"type": "group", "name": "bear", "targets": body_parts})
o.add({"type": "pivot", "target": "bear", "value": "bottom"})
# hearts (born at the chest)
hearts = []
HC = [("#FF5C7A", 56), ("#FF8FA3", 40), ("#FF4D6D", 66), ("#FFA3B5", 36), ("#FF6B8A", 50)]
for i, (c, size) in enumerate(HC):
    o.add({"type": "shape", "shape": "heart", "name": f"heart{i}", "x": BX - size / 2, "y": 520, "width": size, "height": size * 0.9, "fill": c})
    o.add({"type": "opacity", "target": f"heart{i}", "value": 0})
    hearts.append(f"heart{i}")
# ---------- text ----------
o.add({"type": "text", "name": "greet", "text": "Good Morning,", "font": "heading", "size": 60, "color": "#7A3412", "x": 52, "y": 52})
o.add({"type": "text", "name": "daddy", "text": "Daddy!", "font": "heading", "size": 150, "color": "#E8501C", "x": 46, "y": 132})
o.add({"type": "layer-style", "target": "daddy", "name": "stroke", "settings": {"color": "#FFFFFF", "width": 12}})
o.add({"type": "layer-style", "target": "daddy", "name": "drop-shadow", "settings": {"color": "#7A341288", "dx": 0, "dy": 8, "blur": 0, "opacity": 0.35}})
o.add({"type": "text", "name": "sub1", "text": "Here's a great big hug", "font": "body", "size": 42, "color": "#7A3412", "x": 54, "y": 360})
o.add({"type": "text", "name": "sub2", "text": "to start your day!", "font": "body", "size": 42, "color": "#7A3412", "x": 54, "y": 412})
# ---------- animation (loop 4000 ms; every track returns to its t=0 value) ----------
T = 4000
# arms: rest(30) -> wide open(86) -> hug(-66) -> release -> rest
kf(o, "arm-l", "rotation", [(0, 28, "ease-in-out-sine"), (850, 82, "ease-in-out-sine"), (1150, 84, "ease-in-out-back"), (1500, -62, "ease-in-out-sine"),
                             (2500, -58, "ease-in-out-back"), (3250, 28, "ease-in-out-sine"), (T, 28)])
kf(o, "arm-r", "rotation", [(0, -28, "ease-in-out-sine"), (850, -82, "ease-in-out-sine"), (1150, -84, "ease-in-out-back"), (1500, 62, "ease-in-out-sine"),
                             (2500, 58, "ease-in-out-back"), (3250, -28, "ease-in-out-sine"), (T, -28)])
# whole bear: lean back while opening, squash-and-squeeze on the hug, settle
kf(o, "bear", "scale-x", [(0, 1, "ease-in-out-sine"), (900, 0.985, "ease-in-out-sine"), (1150, 0.99, "ease-in-out"), (1500, 1.05, "ease-in-out-sine"),
                           (2500, 1.04, "ease-in-out-sine"), (3250, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "bear", "scale-y", [(0, 1, "ease-in-out-sine"), (900, 1.012, "ease-in-out-sine"), (1150, 1.01, "ease-in-out"), (1500, 0.955, "ease-in-out-sine"),
                           (2500, 0.965, "ease-in-out-sine"), (3250, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "head-g", "rotation", [(0, 0, "ease-in-out-sine"), (900, 5, "ease-in-out-sine"), (1150, 5, "ease-in-out"), (1500, -6, "ease-in-out-sine"), (2500, -5, "ease-in-out-sine"),
                              (3250, 0, "ease-in-out-sine"), (T, 0)])
# expression: open eyes + smile -> happy-closed eyes + open mouth during the squeeze -> back (plus one blink)
for side in "lr":
    kf(o, f"eye-{side}", "opacity", [(0, 1, "hold"), (1380, 0, "hold"), (2650, 1, "hold"), (3560, 0, "hold"), (3680, 1, "hold"), (T, 1)])
    kf(o, f"eye-hl-{side}", "opacity", [(0, 1, "hold"), (1380, 0, "hold"), (2650, 1, "hold"), (3560, 0, "hold"), (3680, 1, "hold"), (T, 1)])
    kf(o, f"eye-closed-{side}", "opacity", [(0, 0, "hold"), (1380, 1, "hold"), (2650, 0, "hold"), (3560, 1, "hold"), (3680, 0, "hold"), (T, 0)])
    kf(o, f"cheek-{side}", "scale", [(0, 1, "ease-in-out-sine"), (1500, 1.3, "ease-in-out-sine"), (2500, 1.25, "ease-in-out-sine"), (3250, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "mouth-smile", "opacity", [(0, 1, "hold"), (1300, 0, "hold"), (2650, 1, "hold"), (T, 1)])
kf(o, "mouth-open", "opacity", [(0, 0, "hold"), (1300, 1, "hold"), (2650, 0, "hold"), (T, 0)])
kf(o, "tongue", "opacity", [(0, 0, "hold"), (1300, 1, "hold"), (2650, 0, "hold"), (T, 0)])
# sun: shares the moment -- rays turn exactly one 30-degree ray period per loop, whole sun pops with the hug
kf(o, "sun-rays", "rotation", [(0, 0, "linear"), (T, 30)])
kf(o, "sun-g", "scale", [(0, 1, "ease-in-out-sine"), (1450, 1, "ease-out"), (1700, 1.14, "ease-in-out-sine"), (2400, 1.08, "ease-in-out-sine"), (3300, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "sun-glow", "opacity", [(0, 0.8, "ease-in-out-sine"), (1700, 1, "ease-in-out-sine"), (T, 0.8)])
kf(o, "shadow", "scale-x", [(0, 1, "ease-in-out-sine"), (1500, 1.08, "ease-in-out-sine"), (2500, 1.06, "ease-in-out-sine"), (3250, 1, "ease-in-out-sine"), (T, 1)])
# clouds drift out and come back (sine) -> no jump at the loop point
kf(o, "cloud0", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, 60, "ease-in-out-sine"), (T, 0)])
kf(o, "cloud1", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, -50, "ease-in-out-sine"), (T, 0)])
# hearts: caused by the squeeze -- born at the chest as it closes, drift up and fade out
import math
for i, h in enumerate(hearts):
    t0 = 1500 + i * 190
    dx = [-215, 235, 285, -235, 195][i]
    kf(o, h, "opacity", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 250, 1, "ease-in-out-sine"), (t0 + 1100, 1, "ease-in"), (t0 + 1700, 0, "hold"), (T, 0)])
    kf(o, h, "scale", [(0, 0.2, "hold"), (t0, 0.2, "ease-out"), (t0 + 350, 1, "ease-in-out-sine"), (T, 1)])
    kf(o, h, "translate-y", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 1700, -300 - i * 20, "linear"), (T, -300 - i * 20)])
    kf(o, h, "translate-x", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 1700, dx, "ease-out"), (T, dx)])
p, r = make(W, H, "#FFF1BE", o)
print("warnings:", r.get("warnings"))
sheet(p, "c1_sheet.png", [0, 600, 1000, 1300, 1500, 2000, 2800, 3500, 3999], columns=3)
p.save("card1.vixl")
