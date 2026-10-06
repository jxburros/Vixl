from common import *
W, H = 900, 900
o = Ops()
T = 4000
# ---------- scene: dawn ----------
o.add({"type": "gradient", "name": "sky", "x": 0, "y": 0, "width": W, "height": H, "direction": "vertical",
       "stops": [{"offset": 0, "color": "#A9B9F5"}, {"offset": 0.5, "color": "#FFD3C2"}, {"offset": 0.8, "color": "#FFE6A5"}, {"offset": 1, "color": "#FFE6A5"}]})
SX, SY, SR = 735, 585, 78
glow_ops(o, "sun-glow", SX, SY, 330, color="#FFE9A0")
sun_members = sun_ops(o, "sun", SX, SY, SR)
o.add({"type": "group", "name": "sun-g", "targets": sun_members})
o.add({"type": "shape", "shape": "ellipse", "name": "hill-far", "x": 380, "y": 612, "width": 760, "height": 240, "fill": "#B9D99A"})
o.add({"type": "shape", "shape": "ellipse", "name": "hill-mid", "x": -260, "y": 690, "width": 1100, "height": 360, "fill": "#92CC78"})
o.add({"type": "shape", "shape": "ellipse", "name": "hill", "x": -120, "y": 780, "width": 1250, "height": 360, "fill": "#74B861"})
for i, (cx, cy, w) in enumerate([(560, 372, 180), (40, 470, 150)]):
    o.add({"type": "shape", "shape": "cloud", "name": f"cloud{i}", "x": cx, "y": cy, "width": w, "height": w * 0.48, "fill": "#FFFFFF"})
    o.add({"type": "opacity", "target": f"cloud{i}", "value": 0.8})
# ---------- bear + mug ----------
S = 0.88
BX, BY = 330, 868
TH_REST, TH_LIFT = -40, -54
def pawy(th): return paw_pos("l", th, S)[1]
def mug(o, X, Y, s):
    cy = Y(pawy(TH_REST) / S - 34 / S)  # mug centre at rest, parented via translate keys later
    cx = X(0)
    w, h = 124 * s, 108 * s
    o.add({"type": "shape", "shape": "ellipse", "name": "mug-handle", "x": cx + w / 2 - 16 * s, "y": cy - 26 * s, "width": 64 * s, "height": 64 * s,
           "fill": "#00000000", "stroke": "#D9402B", "stroke_width": 14 * s})
    o.add({"type": "shape", "shape": "rounded-rectangle", "name": "mug-body", "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h, "radius": 22 * s, "fill": "#E8503A"})
    o.add({"type": "layer-style", "target": "mug-body", "name": "gradient-overlay", "settings": {"start": "#FFFFFF", "end": "#8A1F10", "direction": "angled", "angle": 80, "opacity": 0.3}})
    o.add({"type": "shape", "shape": "heart", "name": "mug-heart", "x": cx - 24 * s, "y": cy - 20 * s, "width": 48 * s, "height": 43 * s, "fill": "#FFFFFF"})
    o.add({"type": "shape", "shape": "ellipse", "name": "mug-coffee", "x": cx - w / 2 + 8 * s, "y": cy - h / 2 - 3 * s, "width": w - 16 * s, "height": 14 * s, "fill": "#5A3320"})
    steam = []
    for i, dx in enumerate((-26, 0, 26)):
        x0, y0 = cx + dx * s * 1.1, cy - h / 2 - 12 * s
        path_layer(o, f"steam{i}", [("M", (x0, y0)), ("C", (x0 - 12 * s, y0 - 16 * s), (x0 + 12 * s, y0 - 30 * s), (x0 + 6 * s, y0 - 46 * s))],
                   stroke="#FFFFFF", sw=8 * s)
        o.add({"type": "shape", "target": f"steam{i}", "trim_end": 0})
        steam.append(f"steam{i}")
    for i in range(2):
        o.add({"type": "shape", "shape": "heart", "name": f"mug-heart-up{i}", "x": cx + (30 + i * 14) * s, "y": cy - h / 2 + 6 * s, "width": (52 - i * 12) * s, "height": (46 - i * 11) * s,
               "fill": ["#FF5C7A", "#FF8FA3"][i]})
        o.add({"type": "opacity", "target": f"mug-heart-up{i}", "value": 0})
    return ["mug-handle", "mug-body", "mug-heart", "mug-coffee"] + steam + ["mug-heart-up0", "mug-heart-up1"]
info = build_bear(o, BX, BY, S, before_arms=mug)
head = group_head(o)
pivot_for(o, "head-g", head, BX, BY - 290 * S)
body_parts = ["foot-l", "sole-l", "foot-r", "sole-r", "body", "tummy", "head-g", "arm-l", "arm-r"]
o.add({"type": "group", "name": "mug-g", "targets": info["extra"]})
body_parts.insert(body_parts.index("arm-l"), "mug-g")
o.add({"type": "group", "name": "bear", "targets": body_parts})
o.add({"type": "pivot", "target": "bear", "value": "bottom"})
# ---------- text ----------
o.add({"type": "text", "name": "greet", "text": "Good Morning,", "font": "heading", "size": 58, "color": "#4A2F8F", "x": "center", "y": 30})
o.add({"type": "text", "name": "daddy", "text": "Daddy!", "font": "heading", "size": 160, "color": "#E8501C", "x": "center", "y": 108})
o.add({"type": "layer-style", "target": "daddy", "name": "stroke", "settings": {"color": "#FFFFFF", "width": 12}})
o.add({"type": "layer-style", "target": "daddy", "name": "drop-shadow", "settings": {"color": "#4A2F8F88", "dx": 0, "dy": 8, "blur": 0, "opacity": 0.3}})
o.add({"type": "text", "name": "sub", "text": "Warm hugs and a cup of sunshine", "font": "body", "size": 40, "color": "#4A2F8F", "x": "center", "y": 322})
# ---------- animation ----------
dy = lambda th: (pawy(th) - pawy(TH_REST))
LIFT0, LIFT1, HOLD1, LOW1 = 1100, 1800, 2600, 3300
kf(o, "arm-l", "rotation", [(0, TH_REST, "ease-in-out-sine"), (LIFT0, TH_REST, "ease-in-out-sine"), (LIFT1, TH_LIFT, "ease-in-out-sine"), (HOLD1, TH_LIFT, "ease-in-out-sine"), (LOW1, TH_REST, "ease-in-out-sine"), (T, TH_REST)])
kf(o, "arm-r", "rotation", [(0, -TH_REST, "ease-in-out-sine"), (LIFT0, -TH_REST, "ease-in-out-sine"), (LIFT1, -TH_LIFT, "ease-in-out-sine"), (HOLD1, -TH_LIFT, "ease-in-out-sine"), (LOW1, -TH_REST, "ease-in-out-sine"), (T, -TH_REST)])
kf(o, "mug-g", "translate-y", [(0, 0, "ease-in-out-sine"), (LIFT0, 0, "ease-in-out-sine"), (LIFT1, dy(TH_LIFT), "ease-in-out-sine"), (HOLD1, dy(TH_LIFT), "ease-in-out-sine"), (LOW1, 0, "ease-in-out-sine"), (T, 0)])
kf(o, "head-g", "rotation", [(0, 0, "ease-in-out-sine"), (LIFT0, 0, "ease-in-out-sine"), (LIFT1, -5, "ease-in-out-sine"), (HOLD1, -5, "ease-in-out-sine"), (LOW1, 1, "ease-in-out-sine"), (T, 0)])
kf(o, "bear", "scale-y", [(0, 1, "ease-in-out-sine"), (LIFT0, 1.006, "ease-in-out-sine"), (LIFT1, 0.994, "ease-in-out-sine"), (HOLD1, 0.996, "ease-in-out-sine"), (LOW1, 1.01, "ease-in-out-sine"), (T, 1)])
for side in "lr":
    for nm, a, b in ((f"eye-{side}", 1, 0), (f"eye-hl-{side}", 1, 0), (f"eye-closed-{side}", 0, 1)):
        kf(o, nm, "opacity", [(0, a, "hold"), (1750, b, "hold"), (2650, a, "hold"), (3640, b, "hold"), (3760, a, "hold"), (T, a)])
    kf(o, f"cheek-{side}", "scale", [(0, 1, "ease-in-out-sine"), (2200, 1.25, "ease-in-out-sine"), (3400, 1.1, "ease-in-out-sine"), (T, 1)])
kf(o, "mouth-smile", "opacity", [(0, 1, "hold"), (2800, 0, "hold"), (3600, 1, "hold"), (T, 1)])
kf(o, "mouth-open", "opacity", [(0, 0, "hold"), (2800, 1, "hold"), (3600, 0, "hold"), (T, 0)])
kf(o, "tongue", "opacity", [(0, 0, "hold"), (2800, 1, "hold"), (3600, 0, "hold"), (T, 0)])
# steam rises while the bear waits, then is gone before the cup meets its face
for i in range(3):
    t0 = 100 + i * 200
    kf(o, f"steam{i}", "trim_end", [(0, 0, "ease-out"), (t0, 0, "ease-out"), (t0 + 650, 100, "hold"), (T, 100)])
    kf(o, f"steam{i}", "trim_start", [(0, 0, "hold"), (t0 + 750, 0, "ease-in-out-sine"), (t0 + 1250, 100, "hold"), (T, 100)])
# after the sip: two hearts waft up and away from the cup, clear of the face
for i in range(2):
    t0 = 2650 + i * 200
    kf(o, f"mug-heart-up{i}", "opacity", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 250, 1, "ease-in-out-sine"), (t0 + 650, 1, "ease-in"), (t0 + 1050, 0, "hold"), (T, 0)])
    kf(o, f"mug-heart-up{i}", "translate-y", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 1050, -70 - i * 40, "hold"), (T, -70 - i * 40)])
    kf(o, f"mug-heart-up{i}", "translate-x", [(0, 0, "hold"), (t0, 0, "ease-out"), (t0 + 1050, 150 + i * 60, "hold"), (T, 150 + i * 60)])
    kf(o, f"mug-heart-up{i}", "scale", [(0, 0.3, "hold"), (t0, 0.3, "ease-out"), (t0 + 300, 1, "ease-in-out-sine"), (T, 1)])
kf(o, "sun-rays", "rotation", [(0, 0, "linear"), (T, 30)])
kf(o, "sun-g", "translate-y", [(0, 0, "ease-in-out-sine"), (2000, -14, "ease-in-out-sine"), (T, 0)])
kf(o, "sun-glow", "opacity", [(0, 0.75, "ease-in-out-sine"), (2000, 1, "ease-in-out-sine"), (T, 0.75)])
kf(o, "cloud0", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, -70, "ease-in-out-sine"), (T, 0)])
kf(o, "cloud1", "translate-x", [(0, 0, "ease-in-out-sine"), (2000, 60, "ease-in-out-sine"), (T, 0)])
p, r = make(W, H, "#FFD3C2", o)
print("warnings:", [w for w in (r.get("warnings") or []) if 'cut off' not in w])
sheet(p, "c2_sheet.png", [0, 600, 1300, 1900, 2300, 2800, 3200, 3600, 3999], columns=3)
p.save("card2.vixl")
