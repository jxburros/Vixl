"""Plush teddy-bear + sun builders that emit Vixl operations.

Every body part is a *furry* silhouette (scalloped, flicked tufts) with seeded fur-flick
strokes, so the bear reads as fuzzy rather than as flat ovals.  Parts are grouped so joints can
rotate about a real pivot.
"""
import math
import random

FUR = "#B8773E"
FUR_DARK = "#8A4F24"
FUR_LIGHT = "#E0A56C"
CREAM = "#F3D6A8"
CREAM_DARK = "#DDB77F"
NOSE = "#3A2314"
CHEEK = "#F4958A"


class Ops:
    def __init__(self):
        self.ops = []
        self.boxes = {}  # name -> (x, y, w, h)

    def add(self, op):
        self.ops.append(op)
        return op


def _fmt(v):
    return f"{v:.1f}"


def fur_silhouette(cx, cy, rx, ry, n, tuft, rng, swirl=0.45):
    """Closed path of soft pointed tufts around an ellipse; returns (points, bbox)."""
    pts = []
    step = 2 * math.pi / n
    valleys = []
    for i in range(n):
        a = i * step
        k = 1 - tuft * 0.5 * (0.6 + 0.8 * rng.random()) / max(rx, ry) * 1.0
        valleys.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    cmds = []
    xs, ys = [], []
    for i in range(n):
        a0 = i * step
        am = a0 + step * (0.5 + swirl * 0.5)
        h = tuft * (0.7 + 0.6 * rng.random())
        tip = (cx + (rx + h) * math.cos(am), cy + (ry + h) * math.sin(am))
        v0 = valleys[i]
        v1 = valleys[(i + 1) % n]
        if i == 0:
            cmds.append(("M", v0))
        cmds.append(("Q", tip, v1))
        for p in (v0, tip, v1):
            xs.append(p[0])
            ys.append(p[1])
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return cmds, (x0, y0, x1 - x0, y1 - y0)


def to_path(cmds, ox, oy):
    out = []
    for c in cmds:
        if c[0] == "M":
            out.append(f"M{_fmt(c[1][0] - ox)} {_fmt(c[1][1] - oy)}")
        else:
            out.append(f"Q{_fmt(c[1][0] - ox)} {_fmt(c[1][1] - oy)} {_fmt(c[2][0] - ox)} {_fmt(c[2][1] - oy)}")
    return " ".join(out) + " Z"


def flick_paths(cx, cy, rx, ry, count, rng, region, length=(10, 20), skip=None):
    """Short curved fur strokes radiating from the centre; returns (subpaths, bbox)."""
    segs = []
    tries = 0
    while len(segs) < count and tries < count * 40:
        tries += 1
        r = math.sqrt(rng.random()) * 0.96
        a = rng.random() * 2 * math.pi
        x, y = cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)
        if not region(x - cx, y - cy, rx, ry):
            continue
        if skip and skip(x, y):
            continue
        ang = math.atan2((y - cy) / ry, (x - cx) / rx) + rng.uniform(-0.5, 0.5)
        ln = rng.uniform(*length)
        x2, y2 = x + ln * math.cos(ang), y + ln * math.sin(ang)
        bend = rng.uniform(-0.35, 0.35)
        mx, my = (x + x2) / 2 - ln * bend * math.sin(ang), (y + y2) / 2 + ln * bend * math.cos(ang)
        segs.append((x, y, mx, my, x2, y2))
    xs = [v for s in segs for v in (s[0], s[2], s[4])]
    ys = [v for s in segs for v in (s[1], s[3], s[5])]
    return segs, (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def fur_part(o, name, cx, cy, rx, ry, base, *, seed, n=None, tuft=None, flicks=160,
             dark=FUR_DARK, light=FUR_LIGHT, skip=None, shade=True, light_flicks=True):
    """One fuzzy blob: silhouette + shadow flicks + highlight flicks, grouped as ``name``."""
    rng = random.Random(seed)
    n = n or max(14, int(2 * math.pi * (rx + ry) / 2 / 20))
    tuft = tuft if tuft is not None else max(5, (rx + ry) / 2 * 0.075)
    cmds, (bx, by, bw, bh) = fur_silhouette(cx, cy, rx, ry, n, tuft, rng)
    o.add({"type": "shape", "shape": "path", "name": f"{name}-fur", "x": round(bx, 1), "y": round(by, 1),
           "width": round(bw, 1), "height": round(bh, 1), "path": to_path(cmds, bx, by), "fill": base})
    members = [f"{name}-fur"]
    if shade:
        o.add({"type": "layer-style", "target": f"{name}-fur", "name": "gradient-overlay",
               "settings": {"start": "#FFFFFF", "end": "#4A2A10", "direction": "angled", "angle": 70, "opacity": 0.38}})
    size = (rx + ry) / 2
    for tag, color, region, w, op in (
        ("dk", dark, lambda dx, dy, rx_, ry_: (dx / rx_) * 0.55 + (dy / ry_) * 0.85 > -0.1, max(2.2, size * 0.026), 0.55),
        ("lt", light, lambda dx, dy, rx_, ry_: (dx / rx_) * -0.5 + (dy / ry_) * -0.85 > -0.05, max(2.0, size * 0.024), 0.6),
    ):
        if tag == "lt" and not light_flicks:
            continue
        segs, (fx, fy, fw, fh) = flick_paths(cx, cy, rx, ry, flicks, rng, region,
                                             (size * 0.09, size * 0.19), skip)
        d = " ".join(f"M{_fmt(s[0] - fx)} {_fmt(s[1] - fy)} Q{_fmt(s[2] - fx)} {_fmt(s[3] - fy)} {_fmt(s[4] - fx)} {_fmt(s[5] - fy)}" for s in segs)
        o.add({"type": "shape", "shape": "path", "name": f"{name}-{tag}", "x": round(fx, 1), "y": round(fy, 1),
               "width": round(max(fw, 1), 1), "height": round(max(fh, 1), 1), "path": d, "fill": "#00000000",
               "stroke": color, "stroke_width": round(w, 1), "line_cap": "round"})
        o.add({"type": "opacity", "target": f"{name}-{tag}", "value": op})
        members.append(f"{name}-{tag}")
    # group bbox = union of members' boxes
    o.add({"type": "group", "name": name, "targets": members})
    o.boxes[name] = (bx, by, bw, bh)
    return name


def box_union(*boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def ell(o, name, cx, cy, rx, ry, fill, **extra):
    opacity = extra.pop("opacity", None)
    o.add({"type": "shape", "shape": "ellipse", "name": name, "x": round(cx - rx, 1), "y": round(cy - ry, 1),
           "width": round(2 * rx, 1), "height": round(2 * ry, 1), "fill": fill, **extra})
    if opacity is not None:
        o.add({"type": "opacity", "target": name, "value": opacity})
    o.boxes[name] = (cx - rx, cy - ry, 2 * rx, 2 * ry)


def path_layer(o, name, pts_abs, *, fill="#00000000", stroke=None, sw=0, closed=False, cap="round", pad=0):
    """pts_abs: list of ('M'|'L'|'Q'|'C', (x,y),...) absolute coordinates."""
    xs = [p[0] for c in pts_abs for p in c[1:]]
    ys = [p[1] for c in pts_abs for p in c[1:]]
    bx, by = min(xs) - pad, min(ys) - pad
    bw, bh = max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    d = ""
    for c in pts_abs:
        d += c[0] + " ".join(f"{_fmt(p[0] - bx)} {_fmt(p[1] - by)}" for p in c[1:]) + " "
    d += "Z" if closed else ""
    op = {"type": "shape", "shape": "path", "name": name, "x": round(bx, 1), "y": round(by, 1),
          "width": round(max(bw, 1), 1), "height": round(max(bh, 1), 1), "path": d.strip(), "fill": fill}
    if stroke:
        op.update({"stroke": stroke, "stroke_width": sw, "line_cap": cap, "line_join": "round"})
    o.add(op)
    o.boxes[name] = (bx, by, bw, bh)


def pivot_for(o, group, members, px, py):
    """Set a group's pivot at absolute canvas point (px, py)."""
    bx, by, bw, bh = box_union(*[o.boxes[m] for m in members])
    o.add({"type": "pivot", "target": group, "value": [round((px - bx) / bw, 4), round((py - by) / bh, 4)]})


def build_bear(o, ox, oy, s=1.0, *, prefix="", before_arms=None, seed=7):
    """Front-facing sitting teddy.  (ox, oy) = ground contact between the feet.

    Returns dict of group names.  Joint groups: head-g (pivot at the neck), arm-l / arm-r
    (pivot at shoulders), eyes/mouth variants for expressions, cheeks.
    """
    P = prefix

    def X(v):
        return ox + v * s

    def Y(v):
        return oy + v * s

    n = lambda nm: f"{P}{nm}"
    # ground shadow
    ell(o, n("shadow"), X(0), Y(6), 190 * s, 26 * s, "#2D5A27", opacity=0.28)
    # feet (front, soles toward the viewer)
    for side, sx in (("l", -1), ("r", 1)):
        fur_part(o, n(f"foot-{side}"), X(sx * 92), Y(-40), 62 * s, 42 * s, FUR, seed=seed + 11 + sx, flicks=60)
        ell(o, n(f"sole-{side}"), X(sx * 92), Y(-40), 34 * s, 22 * s, CREAM)
    # body
    fur_part(o, n("body"), X(0), Y(-165), 150 * s, 138 * s, FUR, seed=seed + 1, flicks=240)
    fur_part(o, n("tummy"), X(0), Y(-150), 92 * s, 98 * s, CREAM, seed=seed + 2, flicks=110,
             dark=CREAM_DARK, light="#FFF1D6", tuft=6 * s, shade=False)
    # head group pieces
    hx, hy, hrx, hry = X(0), Y(-385), 142 * s, 124 * s
    for side, sx in (("l", -1), ("r", 1)):
        fur_part(o, n(f"ear-{side}"), X(sx * 112), Y(-492), 54 * s, 54 * s, FUR, seed=seed + 20 + sx, flicks=60)
        fur_part(o, n(f"ear-in-{side}"), X(sx * 112), Y(-490), 30 * s, 30 * s, "#E7B88A", seed=seed + 30 + sx,
                 flicks=24, dark="#C58E5E", light="#F5D3AE", shade=False, tuft=3.5 * s)
    muz = (X(0), Y(-352))
    fur_part(o, n("head"), hx, hy, hrx, hry, FUR, seed=seed + 3, flicks=210,
             skip=lambda x, y: ((x - muz[0]) / (70 * s)) ** 2 + ((y - muz[1]) / (52 * s)) ** 2 < 1)
    fur_part(o, n("muzzle"), muz[0], muz[1], 66 * s, 50 * s, CREAM, seed=seed + 4, flicks=70,
             dark=CREAM_DARK, light="#FFF1D6", tuft=4.5 * s, shade=False)
    # nose + mouth (two expressions) + eyes (open / happy-closed)
    ell(o, n("nose"), X(0), Y(-375), 23 * s, 16 * s, NOSE)
    ell(o, n("nose-shine"), X(-7), Y(-381), 7 * s, 4 * s, "#FFFFFF", opacity=0.55)
    path_layer(o, n("mouth-smile"), [("M", (X(-26), Y(-342))), ("Q", (X(-13), Y(-326)), (X(0), Y(-343))),
                                     ("M", (X(0), Y(-343))), ("Q", (X(13), Y(-326)), (X(26), Y(-342))),
                                     ("M", (X(0), Y(-359))), ("L", (X(0), Y(-343)))],
               stroke=NOSE, sw=5 * s)
    path_layer(o, n("mouth-open"), [("M", (X(-30), Y(-342))), ("Q", (X(0), Y(-292)), (X(30), Y(-342))),
                                    ("Q", (X(0), Y(-330)), (X(-30), Y(-342)))], fill="#7A2B22", stroke=NOSE, sw=4.5 * s, closed=True)
    ell(o, n("tongue"), X(0), Y(-318), 13 * s, 8 * s, "#EE7B77")
    for side, sx in (("l", -1), ("r", 1)):
        ell(o, n(f"eye-{side}"), X(sx * 56), Y(-405), 13 * s, 17 * s, "#24140B")
        ell(o, n(f"eye-hl-{side}"), X(sx * 56 - 4 * sx), Y(-411), 4.5 * s, 5.5 * s, "#FFFFFF")
        path_layer(o, n(f"eye-closed-{side}"), [("M", (X(sx * 56 - 15), Y(-402))), ("Q", (X(sx * 56), Y(-424)), (X(sx * 56 + 15), Y(-402)))],
                   stroke="#24140B", sw=5.5 * s)
        ell(o, n(f"cheek-{side}"), X(sx * 98), Y(-352), 24 * s, 14 * s, CHEEK, opacity=0.6)
    extra = before_arms(o, X, Y, s) if before_arms else []
    # --- arms (drawn last, in front of body) ---
    for side, sx in (("l", -1), ("r", 1)):
        shx, shy = X(sx * 128), Y(-262)
        fur_part(o, n(f"arm-fur-{side}"), shx + sx * 6 * s, shy + 62 * s, 46 * s, 82 * s, FUR, seed=seed + 40 + sx, flicks=90)
        fur_part(o, n(f"shoulder-{side}"), shx, shy + 4 * s, 50 * s, 46 * s, FUR, seed=seed + 50 + sx, flicks=24, light_flicks=False)
        ell(o, n(f"paw-{side}"), shx + sx * 8 * s, shy + 128 * s, 24 * s, 20 * s, CREAM)
        members = [n(f"arm-fur-{side}"), n(f"shoulder-{side}"), n(f"paw-{side}")]
        o.add({"type": "group", "name": n(f"arm-{side}"), "targets": members})
        o.boxes[n(f"arm-{side}")] = box_union(*[o.boxes[m] for m in members if m in o.boxes] or [(shx, shy, 1, 1)])
        pivot_for(o, n(f"arm-{side}"), [m for m in members if m in o.boxes] or [n(f"arm-{side}")], shx, shy)
    return {"s": s, "ox": ox, "oy": oy, "extra": extra}


def group_head(o, P=""):
    n = lambda nm: f"{P}{nm}"
    members = [n("ear-l"), n("ear-in-l"), n("ear-r"), n("ear-in-r"), n("head"), n("muzzle"), n("nose"), n("nose-shine"),
               n("mouth-smile"), n("mouth-open"), n("tongue"), n("eye-l"), n("eye-hl-l"), n("eye-r"), n("eye-hl-r"),
               n("eye-closed-l"), n("eye-closed-r"), n("cheek-l"), n("cheek-r")]
    o.add({"type": "group", "name": n("head-g"), "targets": members})
    return members


def sun_ops(o, name, cx, cy, r, *, rays=12, face=True, rng_seed=3):
    """Sun whose disc, rays and face share one centre; rays rotate in their own group."""
    ray_in, ray_out = r * 1.18, r * 1.78
    cmds = []
    pts = []
    for i in range(rays):
        a = 2 * math.pi * i / rays
        half = math.pi / rays * 0.42
        p1 = (cx + ray_in * math.cos(a - half), cy + ray_in * math.sin(a - half))
        p2 = (cx + ray_out * math.cos(a), cy + ray_out * math.sin(a))
        p3 = (cx + ray_in * math.cos(a + half), cy + ray_in * math.sin(a + half))
        cmds.append(("M", p1))
        cmds.append(("L", p2))
        cmds.append(("L", p3))
        cmds.append(("L", p1))
        pts += [p1, p2, p3]
    path_layer(o, f"{name}-rays", cmds, fill="#FFC21F", stroke="#FFC21F", sw=r * 0.12, closed=False, pad=r * 0.1)
    # symmetric box so rotation pivot is exactly the centre
    bx = cx - ray_out - r * 0.2
    by = cy - ray_out - r * 0.2
    box = (bx, by, 2 * (ray_out + r * 0.2), 2 * (ray_out + r * 0.2))
    o.ops[-1].update({"x": round(bx, 1), "y": round(by, 1), "width": round(box[2], 1), "height": round(box[3], 1)})
    # rebuild path in the symmetric box
    d = ""
    for c in cmds:
        d += c[0] + " ".join(f"{_fmt(p[0] - bx)} {_fmt(p[1] - by)}" for p in c[1:]) + " "
    o.ops[-1]["path"] = d.strip() + " "
    o.boxes[f"{name}-rays"] = box
    o.add({"type": "pivot", "target": f"{name}-rays", "value": [0.5, 0.5]})
    ell(o, f"{name}-disc", cx, cy, r, r, "#FFD84A")
    o.add({"type": "layer-style", "target": f"{name}-disc", "name": "gradient-overlay",
           "settings": {"start": "#FFF3A8", "end": "#FFAA1D", "direction": "angled", "angle": 60, "opacity": 0.8}})
    members = [f"{name}-rays", f"{name}-disc"]
    if face:
        for side, sx in (("l", -1), ("r", 1)):
            ell(o, f"{name}-eye-{side}", cx + sx * r * 0.36, cy - r * 0.08, r * 0.075, r * 0.1, "#6A3B0B")
            ell(o, f"{name}-cheek-{side}", cx + sx * r * 0.58, cy + r * 0.2, r * 0.17, r * 0.1, "#FF8F5A", opacity=0.6)
            members += [f"{name}-eye-{side}", f"{name}-cheek-{side}"]
        path_layer(o, f"{name}-smile", [("M", (cx - r * 0.3, cy + r * 0.2)), ("Q", (cx, cy + r * 0.55), (cx + r * 0.3, cy + r * 0.2))],
                   stroke="#6A3B0B", sw=r * 0.06)
        members.append(f"{name}-smile")
    for m in members[2:]:
        pass
    return members


def glow_ops(o, name, cx, cy, r, color="#FFF2A0", strength=0.9):
    """Soft halo: many stops, fades to zero well before the box edge so no rectangle shows."""
    stops = []
    N = 12
    for i in range(N + 1):
        t = i / N
        a = strength * (1 - t) ** 2.2
        stops.append({"offset": round(t * 0.9, 4), "color": f"{color}{int(max(0, min(255, a * 255))):02X}"})
    stops.append({"offset": 1.0, "color": f"{color}00"})
    o.add({"type": "gradient", "name": name, "direction": "radial", "x": round(cx - r), "y": round(cy - r),
           "width": round(2 * r), "height": round(2 * r), "stops": stops})
    o.boxes[name] = (cx - r, cy - r, 2 * r, 2 * r)


import math as _m


def paw_pos(side, theta, s):
    """Paw centre relative to the ground contact point, for an arm rotated by theta degrees."""
    sx = -1 if side == "l" else 1
    sh = (sx * 128 * s, -262 * s)
    vx, vy = sx * 8 * s, (128 + 4) * s - 4 * s
    a = _m.radians(theta)
    return (sh[0] + vx * _m.cos(a) - vy * _m.sin(a), sh[1] + vx * _m.sin(a) + vy * _m.cos(a))


def sunflower(o, name, cx, cy, r, stem_len, seed=5):
    """Fuzzy-edged sunflower whose stem ends at (cx, cy+stem_len) -- the grip point.
    Returns member layer names (grouped by the caller)."""
    rng = random.Random(seed)
    members = []
    # stem + leaf
    gx, gy = cx, cy + stem_len
    path_layer(o, f"{name}-stem", [("M", (cx, cy)), ("C", (cx - 10, cy + stem_len * 0.35), (cx + 12, cy + stem_len * 0.7), (gx, gy))], stroke="#4E9A3A", sw=r * 0.2)
    members.append(f"{name}-stem")
    lx, ly = cx + r * 0.1, cy + stem_len * 0.62
    path_layer(o, f"{name}-leaf", [("M", (lx, ly)), ("Q", (lx + r * 1.05, ly - r * 0.15), (lx + r * 1.15, ly - r * 0.8)),
                                    ("Q", (lx + r * 0.2, ly - r * 0.7), (lx, ly))], fill="#5DB046", closed=True)
    members.append(f"{name}-leaf")
    # petals: two offset rings of pointed petals
    for tag, rr, col, sw_ in (("back", r, "#F59F00", 0.0), ("front", r * 0.9, "#FFC81E", 1.0)):
        n = 15
        cmds, (bx, by, bw, bh) = fur_silhouette(cx, cy, rr * 0.72, rr * 0.72, n, rr * 0.42, random.Random(seed + (0 if tag == "back" else 9)), swirl=sw_)
        o.add({"type": "shape", "shape": "path", "name": f"{name}-petals-{tag}", "x": round(bx, 1), "y": round(by, 1), "width": round(bw, 1), "height": round(bh, 1),
               "path": to_path(cmds, bx, by), "fill": col})
        members.append(f"{name}-petals-{tag}")
        o.boxes[f"{name}-petals-{tag}"] = (bx, by, bw, bh)
    ell(o, f"{name}-ring", cx, cy, r * 0.5, r * 0.5, "#8A5A1E")
    members.append(f"{name}-ring")
    fur_part(o, f"{name}-disc", cx, cy, r * 0.44, r * 0.44, "#5B3A1E", seed=seed + 3, n=24, tuft=r * 0.05, flicks=80, dark="#2E1B0C", light="#9C6B35", shade=False)
    members.append(f"{name}-disc")
    return members, (gx, gy)
