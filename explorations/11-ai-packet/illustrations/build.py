"""AI packet, illustrations: neural network, helper mascot, tokens pattern tile, training-loop scene.

Run from the repo root:   python explorations/11-ai-packet/illustrations/build.py [piece ...]
Pieces: network, mascot, tokens, loop (default: all). Writes .vixl sources plus PNG (and SVG where useful)
next to this script. Fonts come from the Vixl font cache (downloaded from Google Fonts on first use).
"""

import math
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["VIXL_NO_UPDATE"] = "1"

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font, pair_fonts  # noqa: E402

# One packet palette, shared by every piece in this folder.
PAL = {
    "night": "#0d1030",
    "night2": "#1b1f4f",
    "night3": "#2a2f6e",
    "teal": "#2ee6c5",
    "coral": "#ff6b5b",
    "sun": "#ffd166",
    "lilac": "#a78bfa",
    "cream": "#fff6e5",
    "dim": "#4a4f8a",
    "ink": "#141633",
}
TIMINGS = {}


def swatches():
    return [{"type": "swatch", "name": k, "color": v} for k, v in PAL.items()]


def fonts(p):
    pair_fonts(p, "bricolage-figtree")  # heading Bricolage Grotesque 800, body Figtree 400
    install_font(p, "Space Mono", 700)  # registered as space-mono-700
    install_font(p, "Figtree", 700)  # registered as figtree-700


def path_layer(name, pts_d, **kw):
    """A path shape whose box hugs its geometry (padded, integer).

    Paths given in canvas coordinates with x=y=0 get a box from (0,0) to their farthest point: every
    such layer is rasterised near canvas size, and a fractional box goes through a slow warp. A tight
    integer box keeps renders fast, and the padding keeps strokes from being cut by a parent group's
    content box (see NOTES.md).
    """
    pad = kw.pop("pad", 12)
    xs = [x for x, _ in pts_d["pts"]]
    ys = [y for _, y in pts_d["pts"]]
    x0, y0 = math.floor(min(xs)) - pad, math.floor(min(ys)) - pad
    x1, y1 = math.ceil(max(xs)) + pad, math.ceil(max(ys)) + pad
    d = pts_d["d"](lambda x, y: f"{x - x0:.1f} {y - y0:.1f}")
    return {"type": "shape", "shape": "path", "name": name, "x": x0, "y": y0,
            "width": x1 - x0, "height": y1 - y0, "path": d, **kw}


def curve(p1, p2, bend=0.5):
    """Horizontal S-curve from p1 to p2 (cubic, control points at the horizontal midpoint)."""
    (x1, y1), (x2, y2) = p1, p2
    mx = x1 + (x2 - x1) * bend
    return {"pts": [p1, p2, (mx, y1), (mx, y2)],
            "d": lambda f: f"M{f(x1, y1)} C{f(mx, y1)} {f(mx, y2)} {f(x2, y2)}"}


def line(p1, p2):
    return {"pts": [p1, p2], "d": lambda f: f"M{f(*p1)} L{f(*p2)}"}


def poly(points, closed=False):
    def d(f):
        s = "M" + " L".join(f(x, y) for x, y in points)
        return s + (" Z" if closed else "")
    return {"pts": points, "d": d}


def text(name, s, x, y, size, color="@cream", font="body", **kw):
    return {"type": "text", "name": name, "text": s, "x": x, "y": y, "size": size, "color": color, "font": font, **kw}


def finish(p, stem, svg=False, check_kwargs=None):
    t = time.perf_counter()
    rep = p.check(**(check_kwargs or {}))
    fixes = [i for i in rep["issues"] if i.get("action") == "fix"]
    reviews = [i for i in rep["issues"] if i.get("action") == "review"]
    print(f"  check {stem}: {len(fixes)} fix, {len(reviews)} review")
    for i in fixes + reviews:
        print("    -", i.get("action"), i.get("check"), i.get("message"))
    p.save(str(HERE / f"{stem}.vixl"), overwrite=True)
    p.export(str(HERE / f"{stem}.png"), overwrite=True)
    if svg:
        p.export(str(HERE / f"{stem}.svg"), overwrite=True)
    TIMINGS[stem] = round(time.perf_counter() - t, 2)
    print(f"  {stem}: check+save+export {TIMINGS[stem]} s")
    return rep


# ----------------------------------------------------------------------------------------------
# 1. Inside a neural network


def build_network():
    W, H = 1920, 1200
    p = Project(W, H, background=PAL["night"])
    fonts(p)
    ops = swatches()
    ops.append({"type": "gradient", "name": "sky", "direction": "radial", "falloff": "smooth",
                "stops": [{"offset": 0, "color": "#262b6b"}, {"offset": 1, "color": PAL["night"]}]})
    # faint star dust in the background: a scatter of tiny dots inside a full-canvas rectangle
    ops.append({"type": "shape", "shape": "rectangle", "name": "dust-area", "x": 0, "y": 0, "width": W, "height": H,
                "fill": "#00000000"})
    ops.append({"type": "scatter", "target": "dust-area", "name": "dust", "count": 140, "seed": 4,
                "mark": {"shape": "ellipse", "width": 4, "height": 4, "fill": PAL["lilac"]},
                "scale_jitter": 0.6, "tone_variation": 0.08, "merge": True})
    ops.append({"type": "opacity", "target": "dust", "value": 0.35})
    ops.append({"type": "hide", "target": "dust-area"})
    ops.append({"type": "layer-intent", "target": "dust", "role": "decoration", "allow_crop": True})

    sizes = [4, 6, 6, 3]
    xs = [470, 850, 1230, 1560]
    top, bot = 380, 860
    gap = (bot - top) / (max(sizes) - 1)
    pos = []
    for li, n in enumerate(sizes):
        y0 = (top + bot) / 2 - gap * (n - 1) / 2
        pos.append([(xs[li], round(y0 + i * gap)) for i in range(n)])
    hot = [(0, 1), (1, 2), (2, 1), (3, 0)]  # the strongest route for this input, highlighted
    rnd = random.Random(7)
    dim, strong, hot_names = [], [], []
    for li in range(len(sizes) - 1):
        for a, p1 in enumerate(pos[li]):
            for b, p2 in enumerate(pos[li + 1]):
                w = rnd.random()
                name = f"weight-{li}{a}{b}"
                is_hot = (li, a) in hot and (li + 1, b) in hot
                if is_hot:
                    hot_names.append(name)
                    ops.append(path_layer(name, curve(p1, p2), stroke="@teal", stroke_width=8, line_cap="round"))
                elif w > 0.62:
                    strong.append(name)
                    ops.append(path_layer(name, curve(p1, p2), stroke="@lilac", stroke_width=round(2 + w * 3, 1),
                                          opacity=round(0.45 + w * 0.35, 2), line_cap="round"))
                else:
                    dim.append(name)
                    ops.append(path_layer(name, curve(p1, p2), stroke="@dim", stroke_width=round(1 + w * 2, 1),
                                          opacity=0.55, line_cap="round"))
    ops.append({"type": "group", "name": "weights-weak", "targets": dim})
    ops.append({"type": "group", "name": "weights-strong", "targets": strong})
    ops.append({"type": "group", "name": "signal-path", "targets": hot_names})
    ops.append({"type": "look", "targets": hot_names, "look": "glow", "color": "@teal", "amount": 0.45})
    # pulses travelling the highlighted route: dots scattered along each hot curve
    for i, nm in enumerate(hot_names):
        ops.append({"type": "scatter", "target": nm, "placement": "along", "spacing": 70, "seed": i,
                    "mark": {"shape": "ellipse", "width": 14, "height": 14, "fill": PAL["cream"]},
                    "anchor": "center", "name": f"pulse-{i}", "merge": True})
    nodes = []
    for li, col in enumerate(pos):
        for i, (x, y) in enumerate(col):
            r = 32
            on = (li, i) in hot
            nm = f"node-{li}{i}"
            ops.append({"type": "shape", "shape": "ellipse", "name": nm, "x": x - r, "y": y - r, "width": 2 * r,
                        "height": 2 * r, "fill": "@teal" if on else "@night2", "stroke": "@cream" if on else "@lilac",
                        "stroke_width": 5})
            nodes.append(nm)
    ops.append({"type": "look", "targets": [n for n in nodes if (int(n[5]), int(n[6])) in hot], "look": "glow",
                "color": "@teal", "amount": 0.7})
    ops.append({"type": "group", "name": "nodes", "targets": nodes})

    # input image: a tiny pixel-art cat, split into four "pixel" readings that feed the input nodes
    cat = [
        "#..........#",
        "##........##",
        "###......###",
        "############",
        "##oo####oo##",
        "##ow####ow##",
        "############",
        "#####pp#####",
        ".####oo####.",
        "..########..",
    ]
    ops.append({"type": "pixel-art", "name": "input-cat", "rows": cat, "x": 90, "y": 0,
                "palette": {".": "transparent", "#": PAL["sun"], "o": PAL["ink"], "w": PAL["cream"], "p": PAL["coral"]}})
    ops.append({"type": "resize", "target": "input-cat", "width": 192, "height": 160})
    ops.append({"type": "move", "target": "input-cat", "x": 94, "y": 540})
    ops.append({"type": "shape", "shape": "rounded-rectangle", "name": "input-frame", "x": 70, "y": 500, "width": 240,
                "height": 240, "radius": 20, "fill": "#00000000", "stroke": "@night3", "stroke_width": 4})
    ops.append({"type": "reorder", "target": "input-frame", "below": "input-cat"})
    ops.append(text("input-caption", "a 12 × 10 picture", 190, 762, 24, color="@lilac", align="center"))
    for i, (x, y) in enumerate(pos[0]):
        ops.append(path_layer(f"feed-{i}", curve((316, 620), (x - 100, y), 0.6), stroke="@dim", stroke_width=3,
                              dash=[6, 10], line_cap="round"))
        ops.append(text(f"input-value-{i}", ["0.9", "0.7", "0.1", "0.4"][i], x - 92, y - 15, 22, color="@sun",
                        font="space-mono-700", align="right"))

    # outputs: illustrative scores
    outs = [("cat", 0.91), ("fox", 0.06), ("dog", 0.03)]
    for i, ((label, v), (x, y)) in enumerate(zip(outs, pos[3])):
        hot_out = i == 0
        ops.append(text(f"out-label-{i}", label, x + 56, y - 26, 34, color="@cream" if hot_out else "@lilac",
                        font="heading"))
        ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"out-track-{i}", "x": x + 140, "y": y - 9,
                    "width": 120, "height": 18, "radius": 9, "fill": "@night3"})
        ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"out-bar-{i}", "x": x + 140, "y": y - 9,
                    "width": max(18, round(120 * v)), "height": 18, "radius": 9, "fill": "@teal" if hot_out else "@lilac"})
        ops.append(text(f"out-value-{i}", f"{round(v * 100)}%", x + 140, y + 16, 20,
                        color="@teal" if hot_out else "@lilac", font="space-mono-700"))

    # column labels
    for nm, label, x in (("col-in", "INPUT", xs[0]), ("col-h1", "HIDDEN LAYER 1", xs[1]),
                         ("col-h2", "HIDDEN LAYER 2", xs[2]), ("col-out", "OUTPUT", xs[3])):
        ops.append(text(nm, label, x, 0, 20, color="@teal", font="space-mono-700", align="center"))
        ops.append({"type": "constrain", "target": nm, "constraints": {"center-x": f"canvas.left+{x}", "bottom": "canvas.top+340"}})

    # title block
    ops.append(text("eyebrow", "HOW AI WORKS · 01", 120, 72, 22, color="@teal", font="space-mono-700"))
    ops.append(text("title", "Inside a neural network", 120, 106, 88, font="heading", line_height=1.0))
    ops.append(text("subtitle", "A picture goes in as numbers. Each layer passes signals along weighted\n"
                    "connections, and the network's best guess comes out the other side.", 120, 208, 28,
                    color="@lilac"))

    # three explanatory callouts along the bottom
    notes = [
        ("1", "Weights", "Every line is a weight: a number for how much\none node listens to another. Thicker = stronger."),
        ("2", "Nodes", "Each node adds up what flows in, and passes a\nsignal on when the total is strong enough."),
        ("3", "Learning", "Training nudges the weights, a tiny bit at a time,\nso each guess is a little less wrong than the last."),
    ]
    for i, (num, head, body) in enumerate(notes):
        x = 120 + i * 580
        ops.append({"type": "shape", "shape": "ellipse", "name": f"note-dot-{num}", "x": x, "y": 978, "width": 52,
                    "height": 52, "fill": "@sun"})
        ops.append({"type": "text", "name": f"note-num-{num}", "text": num, "within": f"note-dot-{num}", "size": 28,
                    "color": "@ink", "font": "heading"})
        ops.append(text(f"note-head-{num}", head, x + 72, 976, 32, font="heading"))
        ops.append(text(f"note-body-{num}", body, x + 72, 1022, 22, color="@lilac"))
    ops.append(text("footnote", "Scores are illustrative. Real networks have thousands to billions of weights.", 1800,
                    1104, 20, color="@lilac", align="right"))
    ops.append({"type": "constrain", "target": "footnote", "constraints": {"right": "canvas.right-120"}})
    p.apply(ops)
    finish(p, "neural-network", svg=True)
    return p


# ----------------------------------------------------------------------------------------------
# 2. Byte, the helper mascot (standalone, transparent, rigged with groups and pivots)

def rr(name, x, y, w, h, fill, radius=None, stroke="@ink", sw=10, **kw):
    o = {"type": "shape", "shape": "rounded-rectangle" if radius else "rectangle", "name": name, "x": x, "y": y,
         "width": w, "height": h, "fill": fill, **kw}
    if radius:
        o["radius"] = radius
    if stroke:
        o.update(stroke=stroke, stroke_width=sw, stroke_align="inside")
    return o


def ell(name, cx, cy, w, h, fill, stroke="@ink", sw=10, **kw):
    o = {"type": "shape", "shape": "ellipse", "name": name, "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h,
         "fill": fill, **kw}
    if stroke:
        o.update(stroke=stroke, stroke_width=sw, stroke_align="inside")
    return o


def mascot_ops(prefix="", dx=0, dy=0):
    """Byte's parts. Every name is prefixed so several copies can live in one document."""
    P = prefix
    o = []

    def X(v):
        return v + dx

    def Y(v):
        return v + dy

    o.append(ell(P + "shadow", X(540), Y(1012), 380, 44, "#0000002e", stroke=None))
    # antenna (behind the head): stalk + glowing bulb, pivot at its foot
    o.append(rr(P + "antenna-stalk", X(528), Y(150), 24, 100, "@lilac", radius=12, sw=8))
    o.append(ell(P + "antenna-bulb", X(540), Y(138), 64, 64, "@sun", sw=8))
    o.append({"type": "group", "name": P + "antenna", "targets": [P + "antenna-stalk", P + "antenna-bulb"]})
    # arms: upper arm (shoulder pivot) holding a forearm group (elbow pivot) of lower arm + hand
    for side, sx, rot in (("left", 326, 10), ("right", 690, -10)):
        o.append(rr(f"{P}upper-arm-{side}", X(sx), Y(610), 64, 140, "@lilac", radius=32))
        o.append(rr(f"{P}lower-arm-{side}", X(sx), Y(724), 64, 120, "@lilac", radius=32))
        o.append(ell(f"{P}hand-{side}", X(sx + 32), Y(858), 96, 88, "@cream"))
        o.append({"type": "group", "name": f"{P}forearm-{side}", "targets": [f"{P}lower-arm-{side}", f"{P}hand-{side}"]})
        o.append({"type": "pivot", "target": f"{P}forearm-{side}", "value": [X(sx + 32), Y(744)], "units": "canvas"})
        o.append({"type": "group", "name": f"{P}arm-{side}", "targets": [f"{P}upper-arm-{side}", f"{P}forearm-{side}"]})
        o.append({"type": "pivot", "target": f"{P}arm-{side}", "value": [X(sx + 32), Y(636)], "units": "canvas"})
        o.append({"type": "rotate", "target": f"{P}arm-{side}", "value": rot})
    # legs: thigh, shin, boot; hip pivot on the leg group, knee pivot on the shin group
    for side, lx in (("left", 436), ("right", 580)):
        o.append(rr(f"{P}upper-leg-{side}", X(lx), Y(840), 64, 90, "@lilac", radius=24))
        o.append(rr(f"{P}lower-leg-{side}", X(lx), Y(904), 64, 76, "@lilac", radius=24))
        o.append(rr(f"{P}foot-{side}", X(lx - 30 if side == "left" else lx - 16), Y(950), 110, 62, "@coral", radius=28))
        o.append({"type": "group", "name": f"{P}shin-{side}", "targets": [f"{P}lower-leg-{side}", f"{P}foot-{side}"]})
        o.append({"type": "pivot", "target": f"{P}shin-{side}", "value": [X(lx + 32), Y(916)], "units": "canvas"})
        o.append({"type": "group", "name": f"{P}leg-{side}", "targets": [f"{P}upper-leg-{side}", f"{P}shin-{side}"]})
        o.append({"type": "pivot", "target": f"{P}leg-{side}", "value": [X(lx + 32), Y(850)], "units": "canvas"})
    # body
    o.append(rr(P + "neck", X(500), Y(540), 80, 60, "@lilac", radius=10))
    o.append(rr(P + "torso-shell", X(356), Y(580), 368, 290, "@cream", radius=120))
    o.append(ell(P + "chest-panel", X(540), Y(722), 150, 150, "@night2", sw=8))
    o.append({"type": "shape", "shape": "heart", "name": P + "chest-heart", "x": X(500), "y": Y(688), "width": 80,
              "height": 72, "fill": "@coral"})
    o.append({"type": "group", "name": P + "torso", "targets": [P + "torso-shell", P + "chest-panel", P + "chest-heart"]})
    # head: shell, ear bolts, screen face (eyes, highlights, smile, cheeks); pivot at the neck
    o.append(ell(P + "ear-left", X(326), Y(392), 64, 96, "@teal", sw=8))
    o.append(ell(P + "ear-right", X(754), Y(392), 64, 96, "@teal", sw=8))
    o.append(rr(P + "head-shell", X(326), Y(228), 428, 330, "@cream", radius=110))
    o.append(rr(P + "screen", X(372), Y(272), 336, 240, "@night", radius=72, sw=8))
    o.append(path_layer(P + "screen-glare", {"pts": [(X(400), Y(300)), (X(470), Y(300)), (X(400), Y(350))],
                                             "d": lambda f: f"M{f(X(400), Y(350))} Q{f(X(400), Y(300))} {f(X(470), Y(300))}"},
                        stroke="#ffffff", stroke_width=10, line_cap="round", fill="none", opacity=0.22))
    o.append(ell(P + "eye-left", X(474), Y(380), 58, 88, "@teal", stroke=None))
    o.append(ell(P + "eye-right", X(606), Y(380), 58, 88, "@teal", stroke=None))
    o.append(ell(P + "eye-left-shine", X(484), Y(362), 18, 22, "@cream", stroke=None))
    o.append(ell(P + "eye-right-shine", X(616), Y(362), 18, 22, "@cream", stroke=None))
    o.append({"type": "group", "name": P + "eyes", "targets": [P + "eye-left", P + "eye-right", P + "eye-left-shine",
                                                              P + "eye-right-shine"]})
    o.append(path_layer(P + "mouth", {"pts": [(X(498), Y(448)), (X(582), Y(448)), (X(540), Y(492))],
                                      "d": lambda f: f"M{f(X(498), Y(448))} Q{f(X(540), Y(492))} {f(X(582), Y(448))}"},
                        stroke="@teal", stroke_width=12, line_cap="round", fill="none"))
    o.append(ell(P + "cheek-left", X(420), Y(462), 40, 22, "@coral", stroke=None, opacity=0.85))
    o.append(ell(P + "cheek-right", X(660), Y(462), 40, 22, "@coral", stroke=None, opacity=0.85))
    o.append({"type": "group", "name": P + "face", "targets": [P + "eyes", P + "mouth", P + "cheek-left",
                                                              P + "cheek-right"]})
    o.append({"type": "group", "name": P + "head", "targets": [P + "ear-left", P + "ear-right", P + "head-shell",
                                                              P + "screen", P + "screen-glare", P + "face"]})
    o.append({"type": "pivot", "target": P + "head", "value": [X(540), Y(560)], "units": "canvas"})
    o.append({"type": "pivot", "target": P + "antenna", "value": [X(540), Y(250)], "units": "canvas"})
    o.append({"type": "group", "name": P + "byte", "targets": [
        P + "antenna", P + "arm-left", P + "arm-right", P + "leg-left", P + "leg-right", P + "neck", P + "torso",
        P + "head"]})
    o.append({"type": "pivot", "target": P + "byte", "value": [X(540), Y(1010)], "units": "canvas"})
    o.append({"type": "look", "targets": [P + "eyes", P + "chest-heart", P + "antenna-bulb"], "look": "glow",
              "amount": 0.35})
    return o


def build_mascot():
    p = Project(1080, 1080, background="transparent")
    p.apply(swatches() + mascot_ops())
    finish(p, "mascot", svg=True)
    return p


def scale_about(p, target, k, point, dest):
    x, y, _, _ = p.inspect(target)["canvas_bounds"]
    p.apply([{"type": "scale", "target": target, "value": k}])
    nx, ny = x + k * (point[0] - x), y + k * (point[1] - y)
    p.apply([{"type": "move", "target": target, "relative": True, "x": round(dest[0] - nx), "y": round(dest[1] - ny)}])


def build_mascot_sheet():
    """Three poses of the same rig, posed only by rotating the groups about their pivots."""
    W, H = 1920, 1080
    p = Project(W, H, background=PAL["night"])
    fonts(p)
    ops = swatches()
    ops.append({"type": "gradient", "name": "sky", "direction": "radial", "falloff": "smooth",
                "stops": [{"offset": 0, "color": "#262b6b"}, {"offset": 1, "color": PAL["night"]}]})
    poses = [
        ("a-", "Hi! I'm Byte.", {"arm-right": -150, "forearm-right": -25, "head": -6, "arm-left": 12}),
        ("b-", "Let me think...", {"arm-left": -10, "forearm-left": -150, "head": 9, "arm-right": -8,
                                   "antenna": 14}),
        ("c-", "We did it!", {"arm-left": 150, "forearm-left": 20, "arm-right": -150, "forearm-right": -20,
                              "leg-left": 8, "leg-right": -8}),
    ]
    p.apply(ops)
    ops = []
    for i, (pre, caption, rots) in enumerate(poses):
        dx = -380 + i * 600
        p.apply(mascot_ops(pre, dx=dx, dy=0))
        for part, deg in rots.items():
            ops.append({"type": "rotate", "target": pre + part, "value": deg})
        if pre == "b-":  # the thinking hand goes in front of the body: restack inside the group
            ops.append({"type": "reorder", "target": pre + "arm-left", "above": pre + "head"})
        p.apply(ops)
        ops = []
        # `scale` shrinks towards the box's top-left corner and ignores the pivot (NOTES.md), so the
        # feet are put back where we want them with a relative move afterwards.
        cx = 400 + i * 560
        scale_about(p, pre + "byte", 0.7, (540 + dx, 1010), (cx, 880))
        ops.append({"type": "shape", "target": pre + "shadow", "fill": "#00000066", "width": 280, "height": 34,
                    "x": cx - 140, "y": 880 - 22})
        ops.append(text(pre + "caption", caption, 0, 0, 40, font="heading", align="center"))
        ops.append({"type": "constrain", "target": pre + "caption",
                    "constraints": {"center-x": f"canvas.left+{cx}", "top": "canvas.top+920"}})
    ops.append({"type": "shape", "shape": "speech-bubble", "name": "b-bubble", "x": 1130, "y": 200, "width": 200,
                "height": 150, "fill": "@cream", "pointer_side": "left", "pointer_position": 0.75})
    ops.append({"type": "text", "name": "b-bubble-text", "text": "?", "within": "b-bubble", "size": 72,
                "font": "heading", "color": "@ink"})
    ops.append({"type": "shape", "shape": "speech-bubble", "name": "a-bubble", "x": 590, "y": 250, "width": 190,
                "height": 130, "fill": "@teal", "pointer_side": "left", "pointer_position": 0.7})
    ops.append({"type": "text", "name": "a-bubble-text", "text": "Hi!", "within": "a-bubble", "size": 52,
                "font": "heading", "color": "@ink"})
    # 0.23 reparent: each speech bubble joins its pose's (scaled) group without moving, so the pose and
    # its bubble now move together
    for pre in ("a-", "b-"):
        ops.append({"type": "group", "name": pre + "speech", "targets": [pre + "bubble", pre + "bubble-text"]})
        ops.append({"type": "reparent", "targets": [pre + "speech"], "into": pre + "byte"})
    ops.append(text("sheet-title", "Meet Byte, your AI helper", 120, 70, 64, font="heading"))
    ops.append(text("sheet-sub", "One rig, three poses: every pose is just rotations about the joint pivots.", 120, 150,
                    28, color="@lilac"))
    p.apply(ops)
    finish(p, "mascot-poses")
    return p


# ----------------------------------------------------------------------------------------------
# 3. Tokens: a seamless pattern tile, plus a preview that fills a wall with it

TOKENS = ["the", "\u00b7cat", "ing", "AI", "42", "un", "help", "ful", "?", "token", "<s>", "learn", "ed", "\u00b7pre",
          "dict", "##able", "hello", "!", "data", "\u00b7is", "{", "}", "lo", "ve"]
TOKEN_COLORS = ["teal", "coral", "sun", "lilac", "cream"]


def token_motifs(prefix="m"):
    ops, names = [], []
    for i, t in enumerate(TOKENS):
        c = TOKEN_COLORS[i % len(TOKEN_COLORS)]
        w = 30 + len(t) * 18
        ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}chip{i}", "x": 0, "y": 0,
                    "width": w, "height": 44, "radius": 22, "fill": f"@{c}"})
        ops.append({"type": "text", "name": f"{prefix}chip{i}-t", "text": t, "within": f"{prefix}chip{i}", "size": 24,
                    "font": "space-mono-700", "color": "@night"})
        ops.append({"type": "group", "name": f"{prefix}tok{i}", "targets": [f"{prefix}chip{i}", f"{prefix}chip{i}-t"]})
        names.append(f"{prefix}tok{i}")
    # small accents between the chips
    # (a source may not be listed twice, so frequent accents need copies of their own)
    for k, (shape, size, col) in enumerate((("sparkle", 30, "teal"), ("sparkle", 22, "sun"), ("ellipse", 12, "lilac"),
                                            ("ellipse", 10, "coral"))):
        ops.append({"type": "shape", "shape": shape, "name": f"{prefix}accent{k}", "x": 0, "y": 0, "width": size,
                    "height": size, "fill": f"@{col}"})
        names.append(f"{prefix}accent{k}")
    return ops, names


def tile_ops(size, seed, names):
    return {"type": "pattern-scatter", "source": names, "width": size, "height": size, "spacing": 120, "seed": seed,
            "rotation_jitter": 10, "scale_jitter": 0.08, "background": PAL["night"], "pattern": "tokens",
            "name": "tile"}


def pick_tile_seed(size, seeds=range(1, 31)):
    """pattern-scatter picks motifs at random per copy; try seeds (dry runs on one document) and keep
    the one that shows the most different tokens with the fewest overlapping chips."""
    p = Project(size, size, background=PAL["night"])
    install_font(p, "Space Mono", 700)
    ops, names = token_motifs()
    p.apply(swatches() + ops)
    best = None
    for seed in seeds:
        p.apply([tile_ops(size, seed, names)])
        layers = p.inspect()["layers"]
        groups = [l for l in layers if l["name"].startswith("tile/") and l["name"].count("/") == 1]
        used, boxes = set(), []
        for g in groups:
            kids = [l for l in layers if l.get("parent") == g["id"] and "chip" in l["name"]
                    and not l["name"].endswith("-t")]
            if kids:
                used.add(kids[0]["name"].split("/")[-1])
                boxes.append(g["canvas_bounds"])
        overlaps = sum(1 for i, a in enumerate(boxes) for b in boxes[i + 1:]
                       if a[0] < b[0] + b[2] - 6 and b[0] < a[0] + a[2] - 6 and a[1] < b[1] + b[3] - 6
                       and b[1] < a[1] + a[3] - 6)
        score = len(used) - 3 * overlaps
        if best is None or score > best[0]:
            best = (score, seed, len(used), overlaps)
        p.undo(1)
    print(f"  tile seed {best[1]}: {best[2]} distinct tokens, {best[3]} overlapping pairs")
    return best[1]


def build_tokens():
    size = 800
    t = time.perf_counter()
    seed = pick_tile_seed(size)
    TIMINGS["tokens-seed-search"] = round(time.perf_counter() - t, 1)
    p = Project(size, size, background=PAL["night"])
    install_font(p, "Space Mono", 700)
    ops, names = token_motifs()
    r = p.apply(swatches() + ops + [tile_ops(size, seed, names)], detail="compact")
    print("  seam:", r["pattern_scatter"][0]["seam"])
    # wrapped ghost copies hang over the tile edge on purpose
    p.apply([{"type": "layer-intent", "target": "tile", "allow_crop": True, "role": "decoration"}])
    finish(p, "tokens-tile", svg=True, check_kwargs={"safe_area": 0})

    # the preview: a wall of the pattern with a card explaining tokens
    W, H = 1800, 1200
    q = Project(W, H, background=PAL["night"])
    fonts(q)
    ops, names = token_motifs()
    ops = swatches() + ops + [tile_ops(size, seed, names)]
    ops.append({"type": "shape", "shape": "rectangle", "name": "wall", "x": 0, "y": 0, "width": W, "height": H,
                "fill": "@night"})
    ops.append({"type": "pattern-fill", "target": "wall", "pattern": "tokens", "name": "wall-pattern"})
    ops.append({"type": "hide", "target": "tile"})
    ops.append({"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 330, "y": 330, "width": 1140,
                "height": 540, "radius": 36, "fill": "@cream"})
    ops.append({"type": "look", "target": "card", "look": "hard-shadow", "color": "@teal", "amount": 0.6})
    ops.append(text("card-eyebrow", "HOW AI READS · 02", 410, 400, 22, color="#b8382c", font="space-mono-700"))
    ops.append(text("card-title", "AI reads in tokens", 410, 436, 76, color="@ink", font="heading"))
    ops.append(text("card-body", "Before a language model sees your words, they are cut into tokens: whole words,\n"
                    "word pieces, numbers and punctuation. The model predicts one token at a time.", 410, 540, 26,
                    color="@ink"))
    # worked example: unhelpful -> un · help · ful
    x = 410
    ops.append(text("ex-word", "\u201cunhelpful\u201d", x, 690, 40, color="@ink", font="heading"))
    ops.append({"type": "shape", "shape": "arrow", "name": "ex-arrow", "x": 660, "y": 696, "width": 110, "height": 40,
                "fill": "@coral"})
    cx = 800
    for i, (piece, col) in enumerate((("un", "lilac"), ("help", "teal"), ("ful", "sun"))):
        w = 50 + len(piece) * 26
        ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"ex-chip{i}", "x": cx, "y": 686, "width": w,
                    "height": 60, "radius": 30, "fill": f"@{col}", "stroke": "@ink", "stroke_width": 4,
                    "stroke_align": "inside"})
        ops.append({"type": "text", "name": f"ex-chip{i}-t", "text": piece, "within": f"ex-chip{i}", "size": 34,
                    "font": "space-mono-700", "color": "@ink"})
        cx += w + 20
    ops.append(text("ex-note", "Token splits vary from model to model; this one is illustrative.", 410, 790, 22,
                    color="#4a4f8a"))
    q.apply(ops)
    finish(q, "tokens-wall")


# ----------------------------------------------------------------------------------------------
# 4. The training loop, around a brain made of circuits


def arc_path(cx, cy, r, a0, a1):
    """Clockwise circular arc from angle a0 to a1 (degrees, 0 = 3 o'clock)."""
    p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    pts = [p0, p1] + [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                      for a in range(int(a0), int(a1), 5)]
    return {"pts": pts, "d": lambda f: f"M{f(*p0)} A{r:.1f} {r:.1f} 0 {large} 1 {f(*p1)}"}


def brain_ops(cx, cy):
    o = []
    lobes = [(0, 0, 380, 290), (-118, -86, 170, 150), (0, -118, 190, 150), (118, -86, 170, 150),
             (-150, 22, 150, 180), (150, 22, 150, 180), (-66, 108, 190, 120), (72, 104, 180, 120)]
    names = []
    for i, (dx, dy, w, h) in enumerate(lobes):
        o.append({"type": "shape", "shape": "ellipse", "name": f"lobe-{i}", "x": cx + dx - w / 2, "y": cy + dy - h / 2,
                  "width": w, "height": h, "fill": "@lilac"})
        names.append(f"lobe-{i}")
    o.append({"type": "pathfinder", "name": "brain-shape", "targets": names, "mode": "union"})
    # a groove down the middle: subtract a thin wavy band
    o.append(path_layer("fissure", poly([(cx - 8, cy - 200), (cx + 8, cy - 120), (cx - 8, cy - 40), (cx + 8, cy + 40),
                                         (cx - 8, cy + 120), (cx + 8, cy + 200), (cx + 22, cy + 200),
                                         (cx + 22, cy + 120), (cx + 6, cy + 40), (cx + 22, cy - 40), (cx + 6, cy - 120),
                                         (cx + 22, cy - 200)], closed=True), fill="@night"))
    o.append({"type": "pathfinder", "name": "brain", "targets": ["brain-shape", "fissure"], "mode": "subtract"})
    o.append({"type": "look", "target": "brain", "look": "soft-halo", "color": "@lilac", "amount": 0.5})
    # circuit traces: right-angled runs ending in solder pads, teal on the left, sun on the right
    traces = [
        [(-40, -150), (-40, -100), (-110, -100), (-110, -60)],
        [(-30, -40), (-90, -40), (-90, 10), (-170, 10)],
        [(-40, 60), (-110, 60), (-110, 110)],
        [(-30, 140), (-30, 100), (-60, 100)],
        [(-50, -10), (-50, 30), (-20, 30)],
        [(55, -160), (55, -110), (120, -110), (120, -70)],
        [(50, -50), (110, -50), (110, 0), (185, 0)],
        [(50, 50), (130, 50), (130, 110)],
        [(60, 150), (60, 100), (90, 100)],
        [(70, -10), (70, 20), (40, 20)],
    ]
    pads = []
    for i, tr in enumerate(traces):
        col = "@teal" if tr[0][0] < 0 else "@sun"
        pts = [(cx + x, cy + y) for x, y in tr]
        o.append(path_layer(f"trace-{i}", poly(pts), stroke=col, stroke_width=7, line_cap="round", fill="none",
                            line_join="round"))
        for k, (x, y) in enumerate((pts[0], pts[-1])):
            o.append({"type": "shape", "shape": "ellipse", "name": f"pad-{i}-{k}", "x": x - 11, "y": y - 11,
                      "width": 22, "height": 22, "fill": "@night", "stroke": col, "stroke_width": 6})
            pads.append(f"pad-{i}-{k}")
    o.append({"type": "group", "name": "circuits", "targets": [f"trace-{i}" for i in range(len(traces))] + pads})
    o.append({"type": "look", "target": "circuits", "look": "glow", "color": "@teal", "amount": 0.4})
    return o


def build_loop():
    W, H = 1920, 1200
    p = Project(W, H, background=PAL["night"])
    fonts(p)
    ops = swatches()
    cx, cy, R = 1300, 640, 420
    ops.append({"type": "gradient", "name": "sky", "direction": "radial", "falloff": "smooth",
                "stops": [{"offset": 0, "color": "#29307a"}, {"offset": 0.55, "color": "#161a45"},
                          {"offset": 1, "color": PAL["night"]}]})
    # the ring: 60 ticks made with radial-repeat, then four arrows between the stations
    ops.append({"type": "shape", "shape": "rounded-rectangle", "name": "tick", "x": cx - 4, "y": cy - R + 44, "width": 8,
                "height": 8, "radius": 4, "fill": "@lilac", "opacity": 0.45})
    ops.append({"type": "radial-repeat", "target": "tick", "count": 60, "cx": cx, "cy": cy, "name": "ticks",
                "merge": True})
    stations = [
        (-90, "1", "Guess", "question", "teal"),
        (0, "2", "Check", "checkmark", "sun"),
        (90, "3", "Measure", "ruler", "coral"),
        (180, "4", "Nudge", "cog", "lilac"),
    ]
    for k, (a, *_rest) in enumerate(stations):
        ops.append(path_layer(f"arrow-{k}", arc_path(cx, cy, R, a + 13, a + 77), stroke="@cream", stroke_width=10,
                              line_cap="round", fill="none", marker_end="triangle"))
    ops += brain_ops(cx, cy - 10)
    labels = {
        "1": ("Guess", "The model makes a prediction."),
        "2": ("Check", "Compare it with the right answer."),
        "3": ("Measure", "How wrong was it? That's the loss."),
        "4": ("Nudge", "Adjust the weights a tiny bit."),
    }
    for a, num, name, icon, col in stations:
        bx = cx + R * math.cos(math.radians(a))
        by = cy + R * math.sin(math.radians(a))
        ops.append({"type": "shape", "shape": "ellipse", "name": f"station-{num}", "x": bx - 74, "y": by - 74,
                    "width": 148, "height": 148, "fill": f"@{col}", "stroke": "@night", "stroke_width": 10})
        ops.append({"type": "shape", "shape": icon, "name": f"station-{num}-icon", "x": bx - 38, "y": by - 38,
                    "width": 76, "height": 76, "fill": "@night"})
        ops.append({"type": "look", "target": f"station-{num}", "look": "hard-shadow", "color": "#070920",
                    "amount": 0.5})
        ops.append({"type": "shape", "shape": "ellipse", "name": f"station-{num}-badge", "x": bx + 34, "y": by - 84,
                    "width": 48, "height": 48, "fill": "@cream", "stroke": "@night", "stroke_width": 6})
        ops.append({"type": "text", "name": f"station-{num}-n", "text": num, "within": f"station-{num}-badge",
                    "size": 26, "font": "heading", "color": "@ink"})
    # title column
    ops.append(text("eyebrow", "HOW AI LEARNS · 03", 120, 140, 22, color="@teal", font="space-mono-700"))
    ops.append(text("title", "The training\nloop", 120, 176, 92, font="heading", line_height=1.0))
    ops.append(text("lede", "A model isn't programmed with answers.\nIt learns them by going round this loop,\n"
                    "over and over, on lots of examples.", 120, 390, 28, color="@lilac"))
    y = 560
    for num, (name, line_) in labels.items():
        col = stations[int(num) - 1][4]
        ops.append({"type": "shape", "shape": "ellipse", "name": f"list-dot-{num}", "x": 120, "y": y, "width": 44,
                    "height": 44, "fill": f"@{col}"})
        ops.append({"type": "text", "name": f"list-n-{num}", "text": num, "within": f"list-dot-{num}", "size": 24,
                    "font": "heading", "color": "@ink"})
        ops.append(text(f"list-head-{num}", name, 186, y - 4, 32, font="heading"))
        ops.append(text(f"list-body-{num}", line_, 186, y + 40, 24, color="@lilac"))
        y += 116
    ops.append(text("repeat", "Then repeat, millions of times: each lap, the guesses get a little better.", 120, 1050,
                    24, color="@cream", font="figtree-700"))
    p.apply(ops)
    finish(p, "training-loop", svg=True)
    return p


PIECES = {"loop": build_loop, "tokens": build_tokens, "poses": build_mascot_sheet, "network": build_network, "mascot": build_mascot}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PIECES)
    for name in wanted:
        t = time.perf_counter()
        print(f"[{name}]")
        PIECES[name]()
        print(f"  total {round(time.perf_counter() - t, 1)} s")
    print("timings:", TIMINGS)
