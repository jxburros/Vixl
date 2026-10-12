"""Writes scene-ops.json: the Vixl operations for the poster's artwork (sky, lantern strings,
lanterns, quay silhouette, water and reflections). It only emits JSON operations; Vixl draws them.
Canvas: 3375 x 5175 px = 11.25 x 17.25 in at 300 dpi (tabloid trim plus 0.125 in bleed)."""
import json
import random
from pathlib import Path

W, H = 3375, 5175
HORIZON = 2960
rng = random.Random(12)
ops = []

# Sky and water, both edge to edge through the bleed.
ops.append({"type": "gradient", "name": "sky", "x": 0, "y": 0, "width": W, "height": HORIZON + 40,
            "direction": "vertical", "stops": [
                {"offset": 0, "color": "#060e1c"}, {"offset": 0.6, "color": "#0d1d38"},
                {"offset": 1, "color": "#1d3157"}]})
ops.append({"type": "gradient", "name": "horizon-haze", "x": -400, "y": HORIZON - 700, "width": W + 800,
            "height": 1400, "direction": "radial", "falloff": "gaussian", "stops": [
                {"offset": 0, "color": "#f2a65a33"}, {"offset": 1, "color": "#f2a65a00"}]})
ops.append({"type": "gradient", "name": "water", "x": 0, "y": HORIZON, "width": W, "height": H - HORIZON,
            "direction": "vertical", "stops": [
                {"offset": 0, "color": "#13284a"}, {"offset": 0.35, "color": "#0a1830"},
                {"offset": 1, "color": "#040a16"}]})

# Distant quay: a low silhouette of sheds and rooftops with a few lit windows.
x = -40
i = 0
while x < W:
    w = rng.randint(140, 380)
    h = rng.randint(40, 150)
    ops.append({"type": "shape", "shape": "rectangle", "name": f"quay-{i}", "x": x, "y": HORIZON - h,
                "width": w, "height": h + 4, "fill": "#071223"})
    if rng.random() < 0.6:
        for k in range(rng.randint(1, 3)):
            ops.append({"type": "shape", "shape": "rectangle", "name": f"window-{i}-{k}",
                        "x": x + rng.randint(15, max(16, w - 30)), "y": HORIZON - h + rng.randint(12, max(13, h - 26)),
                        "width": 12, "height": 14, "fill": "#f5c46a", "opacity": 0.85})
    x += w + rng.randint(0, 60)
    i += 1
ops.append({"type": "shape", "shape": "rectangle", "name": "quay-edge", "x": 0, "y": HORIZON - 6,
            "width": W, "height": 12, "fill": "#071223"})

COLORS = ["#f4b942", "#e8743b", "#d9534f", "#f7d488", "#e8743b", "#f4b942", "#d9534f"]


def curve(edge_y, sag):
    xc = W / 2
    hw = xc + 60
    y_mid = edge_y + sag
    def y_at(px):
        return y_mid - sag * ((px - xc) / hw) ** 2
    p0, p2 = (-60, edge_y), (W + 60, edge_y)
    p1 = (xc, y_mid + sag)  # quadratic control point
    c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
    nodes = [{"point": list(p0), "out": list(c1)}, {"point": list(p2), "in": list(c2)}]
    return nodes, y_at


def lantern(prefix, cx, top, bw, bh, color, glow_alpha):
    out = []
    g = bw * 3.4
    out.append({"type": "gradient", "name": f"{prefix}-glow", "x": cx - g / 2, "y": top + bh * 0.55 - g / 2,
                "width": g, "height": g, "direction": "radial", "falloff": "gaussian", "stops": [
                    {"offset": 0, "color": color + glow_alpha}, {"offset": 1, "color": color + "00"}]})
    cap_w, cap_h = bw * 0.46, bh * 0.08
    out.append({"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-cap", "x": cx - cap_w / 2,
                "y": top, "width": cap_w, "height": cap_h, "radius": cap_h * 0.3, "fill": "#2a1c14"})
    body_y = top + cap_h * 0.7
    out.append({"type": "shape", "shape": "ellipse", "name": f"{prefix}-body", "x": cx - bw / 2, "y": body_y,
                "width": bw, "height": bh, "fill": color})
    out.append({"type": "shape", "shape": "ellipse", "name": f"{prefix}-rib", "x": cx - bw * 0.27, "y": body_y,
                "width": bw * 0.54, "height": bh, "fill": "transparent", "stroke": "#7a3a1c",
                "stroke_width": max(3, bw * 0.02), "opacity": 0.45})
    core = bw * 0.7
    out.append({"type": "gradient", "name": f"{prefix}-core", "x": cx - core / 2, "y": body_y + bh / 2 - core * 0.55,
                "width": core, "height": core * 1.1, "direction": "radial", "falloff": "smooth", "stops": [
                    {"offset": 0, "color": "#fff4d6cc"}, {"offset": 1, "color": "#fff4d600"}]})
    out.append({"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-base", "x": cx - cap_w / 2,
                "y": body_y + bh - cap_h * 0.4, "width": cap_w, "height": cap_h, "radius": cap_h * 0.3,
                "fill": "#2a1c14"})
    out.append({"type": "shape", "shape": "line", "name": f"{prefix}-tassel", "x": cx - 2,
                "y": body_y + bh + cap_h * 0.5, "width": 4, "height": bh * 0.22, "stroke": "#c9862f",
                "stroke_width": max(3, bw * 0.02)})
    return out


strings = [
    # name, edge y, sag, lantern x positions, body w, body h, glow alpha, wire length
    ("back", 230, 330, [430, 900, 1400, 1940, 2450, 2930], 120, 150, "55", 40),
    ("front", 560, 470, [250, 700, 1190, 1687, 2185, 2675, 3125], 185, 235, "66", 55),
]
reflect = []
for name, edge_y, sag, xs, bw, bh, ga, wire in strings:
    nodes, y_at = curve(edge_y, sag)
    ops.append({"type": "pen", "name": f"string-{name}", "nodes": nodes, "fill": "transparent",
                "stroke": "#8c7a5a", "stroke_width": 7 if name == "front" else 5})
    for j, cx in enumerate(xs):
        color = COLORS[(j + (2 if name == "back" else 0)) % len(COLORS)]
        sy = y_at(cx)
        ops.append({"type": "shape", "shape": "line", "name": f"wire-{name}-{j}", "x": cx - 2, "y": sy,
                    "width": 4, "height": wire, "stroke": "#8c7a5a", "stroke_width": 4})
        ops.extend(lantern(f"lantern-{name}-{j}", cx, sy + wire, bw, bh, color, ga))
        if name == "front":
            reflect.append((cx, color, bw))

# Reflections: a soft glow and a broken column of ripple dashes under each front lantern, fading with depth.
reflection_ops = []
for j, (cx, color, bw) in enumerate(reflect):
    reflection_ops.append({"type": "gradient", "name": f"reflection-glow-{j}", "x": cx - bw * 0.8,
                           "y": HORIZON - 20, "width": bw * 1.6, "height": 1100, "direction": "radial",
                           "falloff": "gaussian", "stops": [
                               {"offset": 0, "color": color + "38"}, {"offset": 1, "color": color + "00"}]})
    y = HORIZON + 30
    k = 0
    while y < HORIZON + 820:
        depth = (y - HORIZON) / 820
        w = bw * rng.uniform(0.25, 0.9) * (1 + depth * 0.5)
        h = rng.randint(7, 11)
        op = round(max(0.1, 0.8 - depth * 0.75) * rng.uniform(0.6, 1.0), 2)
        reflection_ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"ripple-{j}-{k}",
                               "x": round(cx - w / 2 + rng.uniform(-30, 30)), "y": round(y), "width": round(w),
                               "height": h, "radius": h / 2, "fill": color, "opacity": op})
        y += rng.uniform(40, 75) * (1 + depth)
        k += 1
ops.extend(reflection_ops)

# Faint broad ripple lines across the water to read as a surface.
for k in range(18):
    y = HORIZON + 60 + k * 50 * (1 + k * 0.08)
    if y > H - 40:
        break
    w = rng.randint(500, 1300)
    ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"surface-{k}",
                "x": rng.randint(-200, W - w + 200), "y": round(y), "width": w, "height": 6, "radius": 3,
                "fill": "#5d7aa8", "opacity": round(0.18 - k * 0.006, 3)})
    reflection_ops.append(ops[-1])

Path(__file__).with_name("scene-ops.json").write_text(json.dumps(ops, indent=1))
# Second pass used on the existing document: replace the first-draft reflections and restyle the strings.
fix = [{"type": "edit-layers", "where": {"name": pat}, "do": {"type": "remove"}}
       for pat in ("ripple-*", "reflection-glow-*", "surface-*", "window-11-*")]
fix += [{"type": "shape", "target": n, "stroke": "#8c7a5a"} for n in ("string-front", "string-back")]
fix += [{"type": "shape", "target": f"wire-{s}-{j}", "stroke": "#8c7a5a"}
        for s, n in (("back", 6), ("front", 7)) for j in range(n)]
Path(__file__).with_name("reflection-ops.json").write_text(json.dumps(fix + reflection_ops, indent=1))
print(len(ops), "operations")
