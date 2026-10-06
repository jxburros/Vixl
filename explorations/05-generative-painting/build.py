"""Generative brush painting: a misty mountain lake at dusk, painted stroke by stroke with Vixl.

Run from the repo root:  python explorations/05-generative-painting/build.py
Everything is written to explorations/05-generative-painting/output/ (wiped first).
"""

import json
import math
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
CACHE = OUT / "_cache"
CACHE.mkdir()
os.environ["VIXL_RESOURCES"] = str(CACHE / "resources.json")
os.environ["VIXL_FONT_CACHE"] = str(CACHE / "fonts")
os.environ["VIXL_NO_UPDATE"] = "1"

from vixl import Project  # noqa: E402  (env must be set first)
from vixl.timeline import export_timeline  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

SEED = int(os.environ.get("PAINT_SEED", "1907"))
rng = random.Random(SEED)
W, H = 1600, 1000
HORIZON = 612  # lake line
SUN = None  # placed just above the far ridge, see paint_landscape()

timings = {}
strokes_per_layer = {}
apply_times = {}


def timed(label):
    class T:
        def __enter__(self):
            self.t = time.perf_counter()

        def __exit__(self, *exc):
            timings[label] = round(time.perf_counter() - self.t, 2)
            print(f"  {label}: {timings[label]} s", flush=True)

    return T()


# --------------------------------------------------------------------------------------------
# Small generative helpers


def lerp(a, b, t):
    return a + (b - a) * t


def hexmix(c1, c2, t):
    a = [int(c1[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(lerp(x, y, t)):02x}" for x, y in zip(a, b))


def ramp(stops, t):
    """Piecewise color ramp: stops = [(t, '#rrggbb'), ...]."""
    t = min(max(t, 0), 1)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            return hexmix(c0, c1, (t - t0) / max(t1 - t0, 1e-9))
    return stops[-1][1]


def jitter_color(c, amount, r=rng):
    k = [int(c[i : i + 2], 16) for i in (1, 3, 5)]
    d = r.uniform(-amount, amount)
    return "#" + "".join(f"{max(0, min(255, round(v + d + r.uniform(-amount, amount) * 0.4))):02x}" for v in k)


class Ridge:
    """1-D fractal value noise: a seeded mountain silhouette y(x)."""

    def __init__(self, base, amp, octaves=6, seed=0, peaks=()):
        r = random.Random(seed)
        self.base, self.amp = base, amp
        self.layers = []
        for o in range(octaves):
            n = 3 * 2**o + 2
            self.layers.append(([r.uniform(-1, 1) for _ in range(n + 1)], n, 0.5**o))
        self.peaks = peaks  # (x, height, width) gaussian bumps for designed peaks

    def __call__(self, x):
        t = x / W
        v = 0
        for vals, n, a in self.layers:
            f = t * n
            i = int(f)
            u = f - i
            u = u * u * (3 - 2 * u)
            v += lerp(vals[min(i, n)], vals[min(i + 1, n)], u) * a
        for px, ph, pw in self.peaks:
            v += ph * math.exp(-(((x - px) / pw) ** 2))
        return self.base - v * self.amp


def wobble_path(x0, x1, y, amp, r, segs=4):
    """Horizontal SVG cubic path with a gentle random wobble (used sparingly: paths sample ~24 pts/segment)."""
    xs = [lerp(x0, x1, i / segs) for i in range(segs + 1)]
    d = f"M{xs[0]:.1f} {y + r.uniform(-amp, amp):.1f}"
    for a, b in zip(xs, xs[1:]):
        c1 = lerp(a, b, 0.33)
        c2 = lerp(a, b, 0.66)
        d += f" C{c1:.1f} {y + r.uniform(-amp, amp):.1f} {c2:.1f} {y + r.uniform(-amp, amp):.1f} {b:.1f} {y + r.uniform(-amp, amp):.1f}"
    return d


def wobble(x0, x1, y, amp, r, segs=4):
    """Same idea as wobble_path but as a few control points; Vixl smooths them (Catmull-Rom)."""
    return [[lerp(x0, x1, i / segs), y + r.uniform(-amp, amp)] for i in range(segs + 1)]


class Layer:
    """Collects paint operations for one paint layer and counts strokes."""

    def __init__(self, name, x=0, y=0, w=W, h=H):
        self.name = name
        self.ops = [{"type": "paint-layer", "name": name, "x": x, "y": y, "width": w, "height": h}]
        self.count = 0

    def stroke(self, brush, size, color, *, points=None, path=None, pressure=None, opacity=None, seed=None, settings=None, erase=False):
        op = {"type": "paint", "target": self.name, "brush": brush, "size": round(size, 2), "color": color}
        if points is not None:
            op["points"] = [[round(v, 2) for v in p] for p in points]
        else:
            op["path"] = path
        if pressure is not None:
            op["pressure"] = [round(p, 3) for p in pressure]
        if opacity is not None:
            op["opacity"] = round(opacity, 3)
        op["seed"] = rng.randrange(1_000_000) if seed is None else seed
        if settings:
            op["settings"] = settings
        if erase:
            op["mode"] = "erase"
        self.ops.append(op)
        self.count += 1


PINES = []
BRANCHES = []  # (branch name, [Layer...], extra ops) -- each painted on its own vixl branch
FINISH = []  # document-level ops applied after every branch is merged


def commit(p, layer, extra=(), *, into=None):
    """Queue a paint layer for its own branch (or append it to an existing branch ``into``)."""
    strokes_per_layer[layer.name] = strokes_per_layer.get(layer.name, 0) + layer.count
    for entry in BRANCHES:
        if entry[0] == (into or layer.name):
            entry[1].append(layer)
            entry[2].extend(extra)
            return
    BRANCHES.append((layer.name, [layer], list(extra)))


# --------------------------------------------------------------------------------------------
# The painting


BASE_OPS = [
            # Custom brushes (brush-define): a soft wash, a pine-needle bristle, a reed brush and a mist puff.
            {"type": "brush-define", "name": "wash", "base": "watercolor", "description": "Loose sky wash",
             "settings": {"flow": 0.045, "texture_strength": 0.07, "size_jitter": 0.18, "hardness": 0.15}},
            {"type": "brush-define", "name": "pine", "base": "dry-brush", "description": "Sparse needle clusters",
             "settings": {"bristles": 9, "hardness": 0.9, "taper": [0.02, 0.45], "texture": "grain", "texture_strength": 0.25}},
            {"type": "brush-define", "name": "reed", "base": "brush-pen", "description": "Pressure-led reed blade",
             "settings": {"taper": [0.05, 0.5], "roundness": 0.6, "angle": 70}},
            {"type": "brush-define", "name": "mist", "base": "airbrush", "description": "Low-flow mist puff",
             "settings": {"flow": 0.07, "spacing": 0.08, "pressure_opacity": False}},
]


def paint_landscape():
    global SUN
    p = None  # generation only queues operations; see main()
    ranges = [
        # name, ridge, light color, shadow color
        ("range-far", Ridge(400, 95, seed=SEED + 1, peaks=((520, 1.1, 120), (1350, 0.6, 160), (1000, -0.6, 140))), "#b7a6c4", "#8d7fa8"),
        ("range-mid", Ridge(470, 80, seed=SEED + 2, peaks=((260, 0.9, 140), (900, 0.5, 120))), "#8a7fa3", "#5f5880"),
        ("range-near", Ridge(540, 70, seed=SEED + 3, peaks=((1450, 1.3, 160), (120, 0.8, 120))), "#545a78", "#363b56"),
    ]
    sx = min(range(880, 1120, 10), key=lambda x: -ranges[0][1](x))
    SUN = (sx, round(ranges[0][1](sx) - 34))

    # ---- 1. sky wash --------------------------------------------------------------------
    sky = Layer("sky-wash", 0, 0, W, HORIZON + 40)
    sky_ramp = [(0, "#2e3160"), (0.28, "#5c4f86"), (0.52, "#a56f99"), (0.72, "#e7957a"), (0.88, "#f6c08a"), (1, "#fbe1b0")]
    y = -30
    while y < HORIZON + 30:
        t = (y + 30) / (HORIZON + 60)
        for k in range(2):
            sky.stroke("wash", rng.uniform(110, 150), ramp(sky_ramp, t + rng.uniform(-0.03, 0.03)),
                       points=wobble(-120, W + 120, y + k * 14, 16, rng), opacity=rng.uniform(0.7, 0.95))
        y += 34
    # sun glow: airbrush builds up in concentric loops, pressure-driven opacity
    for ring, (rad, col, size) in enumerate([(150, "#ffd79a", 160), (90, "#ffe6b3", 120), (40, "#fff3d6", 80)]):
        pts = []
        for i in range(25):
            a = i / 24 * math.tau
            pts.append([SUN[0] + math.cos(a) * rad, SUN[1] + math.sin(a) * rad * 0.8, 0.4 + 0.6 * abs(math.sin(a * 2))])
        sky.stroke("airbrush", size, col, points=pts, opacity=0.9, settings={"flow": 0.05 + 0.03 * ring})
    sky.stroke("soft-round", 82, "#fff6e0", points=[[SUN[0] - 2, SUN[1]], [SUN[0] + 2, SUN[1]]], settings={"hardness": 0.55})
    commit(p, sky)

    # ---- 2. clouds: chalk streaks with dark undersides --------------------------------
    clouds = Layer("clouds", 0, 0, W, HORIZON)
    for i in range(46):
        cy = rng.uniform(70, 430)
        cx = rng.uniform(-100, W)
        ln = rng.uniform(160, 520)
        t = cy / 430
        lit = ramp([(0, "#c58aa6"), (0.5, "#f2a98e"), (1, "#ffd3a1")], t)
        under = ramp([(0, "#3a3466"), (1, "#7d5e8d")], t)
        # the first dozen clouds are SVG cubic paths, the rest sparse smoothed points (far cheaper to apply)
        body = {"path": wobble_path(cx, cx + ln, cy, 5, rng, 2)} if i < 12 else {"points": wobble(cx, cx + ln, cy, 5, rng, 3)}
        clouds.stroke("chalk", rng.uniform(8, 22), lit, **body, opacity=rng.uniform(0.45, 0.8),
                      settings={"taper": [0.3, 0.45], "texture_strength": 0.6})
        clouds.stroke("soft-round", rng.uniform(6, 12), under, points=wobble(cx + 30, cx + ln * 0.9, cy + rng.uniform(7, 12), 3, rng, 2),
                      opacity=0.35, settings={"taper": [0.35, 0.45]})
    commit(p, clouds, [{"type": "blend", "target": "clouds", "value": "normal"}, {"type": "opacity", "target": "clouds", "value": 0.85}])

    # ---- 3. mountain ranges (far -> near) ---------------------------------------------
    mist_bases = []
    for idx, (name, ridge, light, shade) in enumerate(ranges):
        top = int(min(ridge(x) for x in range(0, W, 4))) - 12
        ranges[idx] = (name, ridge, light, shade, top)
        region_h = HORIZON + 14 - top
        lay = Layer(name, 0, top, W, region_h)
        step = 17
        x = -20
        while x < W + 20:
            ry = ridge(x)
            slope = ridge(x + 6) - ridge(x - 6)  # >0 means ground rises leftwards => faces the sun (right)
            sunlit = slope > 0
            col = jitter_color(light if sunlit else shade, 6)
            # body: a vertical watercolor pull from the ridge down to the lake line
            lay.stroke("watercolor", rng.uniform(32, 40), col,
                       points=[[x, ry + 4], [x + rng.uniform(-3, 3), (ry + HORIZON) / 2], [x, HORIZON + 10]],
                       opacity=0.96, settings={"texture_strength": 0.18, "flow": 0.09})
            x += step
        # ridge-line crisp edge + dry-brush rock streaks following fall lines
        xs = [i * 8 for i in range(-2, W // 8 + 3)]
        lay.stroke("round", 6, shade, points=[[x, ridge(x) + 3] for x in xs], opacity=0.9, settings={"hardness": 0.6})
        for _ in range(80 + 30 * idx):
            x = rng.uniform(0, W)
            ry = ridge(x)
            ln = rng.uniform(25, 90) * (1 + idx * 0.3)
            dx = (ridge(x + 5) - ridge(x - 5)) * 1.5
            col = hexmix(shade, "#1d1b33", rng.uniform(0.1, 0.4)) if rng.random() < 0.6 else hexmix(light, "#f4c8a0", rng.uniform(0.2, 0.5))
            lay.stroke("dry-brush", rng.uniform(10, 18), col,
                       points=[[x, ry + rng.uniform(4, 20)], [x + dx * 0.5, ry + ln * 0.5], [x + dx, ry + ln]],
                       opacity=rng.uniform(0.18, 0.4) + 0.15 * idx)
        # warm rim light on sunlit ridges near the sun
        run = []
        for x in list(range(0, W, 6)) + [None]:
            if x is not None and ridge(x + 6) - ridge(x - 6) > 0.8:
                run.append([x, ridge(x) + 1.5])
                continue
            if len(run) > 2:  # one pencil stroke per sunlit run of ridge
                d = abs(run[len(run) // 2][0] - SUN[0]) / W
                lay.stroke("pencil", 3, "#ffd9a8", points=run, opacity=max(0.15, 0.85 - d * 1.6) * (1 - idx * 0.2))
            run = []
        commit(p, lay)
        mist_bases.append((ridge, top))

    # ---- 4. mist bands between ranges: airbrush/mist puffs, screen blend, feathered mask ----
    mist = Layer("mist", 0, 250, W, HORIZON + 30 - 250)
    for ridge, _ in mist_bases:
        base = max(ridge(x) for x in range(0, W, 40))
        for band in range(6):
            yb = base - band * 18 + rng.uniform(-10, 10)
            yb = min(yb, HORIZON - 6)
            x0 = rng.uniform(-200, 600)
            mist.stroke("mist", rng.uniform(60, 120), rng.choice(["#eadff0", "#f7e3d4", "#dcd2ea"]),
                        points=wobble(x0, x0 + rng.uniform(700, 1400), yb, 10, rng, 3), opacity=0.9)
    # erase-mode strokes lift gaps in the mist so it reads as drifting banks
    for _ in range(14):
        x0 = rng.uniform(0, W)
        mist.stroke("soft-round", rng.uniform(30, 60), "#000000",
                    points=wobble(x0, x0 + rng.uniform(120, 320), rng.uniform(380, 600), 8, rng, 2),
                    opacity=0.6, erase=True)
    commit(p, mist, [
        {"type": "blend", "target": "mist", "value": "screen"},
        {"type": "opacity", "target": "mist", "value": 0.8},
        {"type": "select", "shape": "ellipse", "x": -300, "y": 200, "width": W + 600, "height": 640, "feather": 120},
        {"type": "mask", "target": "mist", "action": "from-selection"},
        {"type": "select", "shape": "none"},
    ])
    # place mist between ranges: above far + mid, under near
    FINISH.append({"type": "reorder", "target": "mist", "below": "range-near"})

    # ---- 5. water base: horizontal washes mirroring the sky ramp ------------------------
    water = Layer("water", 0, HORIZON - 10, W, H - HORIZON + 10)
    y = HORIZON - 4
    while y < H + 40:
        t = (y - HORIZON) / (H - HORIZON)
        col = ramp([(0, "#f3c08e"), (0.18, "#d58f86"), (0.45, "#7b5f8c"), (1, "#252a4c")], t + rng.uniform(-0.02, 0.02))
        water.stroke("wash", rng.uniform(40, 70), col, points=wobble(-80, W + 80, y, 3, rng, 5), opacity=0.92)
        y += 13 + t * 10
    commit(p, water)

    # ---- 6. reflections: duplicate + flip every range, ripple-break with erase strokes --------
    for name, ridge, light, shade, top in ranges:
        region_h = HORIZON + 14 - top
        rname = f"{name}-reflection"
        lay = Layer(rname)
        # in the range's own branch: duplicate the finished range, flip it, drop it into the lake
        lay.ops = [
            {"type": "duplicate", "target": name, "name": rname},
            {"type": "flip", "target": rname, "direction": "vertical"},
            {"type": "move", "target": rname, "x": 0, "y": 2 * HORIZON - (top + region_h) + 4},
        ]
        for _ in range(70):
            yy = rng.uniform(HORIZON + 8, HORIZON + 330)
            x0 = rng.uniform(-50, W)
            lay.stroke("round", rng.uniform(1.5, 4) * (1 + (yy - HORIZON) / 200), "#000",
                       points=[[x0, yy], [x0 + rng.uniform(60, 400), yy + rng.uniform(-1, 1)]], opacity=0.85,
                       settings={"taper": [0.3, 0.3], "hardness": 0.6}, erase=True)
        strokes_per_layer[rname] = strokes_per_layer[name]
        commit(p, lay, into=name)
    FINISH.extend([
        {"type": "group", "name": "reflections", "targets": [f"{n}-reflection" for n, *_ in ranges]},
        {"type": "opacity", "target": "reflections", "value": 0.62},
        {"type": "blur", "target": "reflections", "amount": 2.5},
        {"type": "wave", "target": "reflections", "amount": 3, "radius": 22},
        # fade the reflection out with depth: feathered rectangle mask
        {"type": "select", "shape": "rect", "x": 0, "y": HORIZON - 40, "width": W, "height": 330, "feather": 90},
        {"type": "mask", "target": "reflections", "action": "from-selection"},
        {"type": "select", "shape": "none"},
    ])

    # ---- 7. water light: sun column, ripples, sparkles ------------------------------------
    shimmer = Layer("water-light", 0, HORIZON - 10, W, H - HORIZON + 10)
    for i in range(120):
        t = i / 120
        yy = HORIZON + 4 + t ** 1.4 * 330
        half = lerp(70, 18, t) * rng.uniform(0.4, 1.3)
        cx = SUN[0] + rng.gauss(0, 14 + t * 30)
        shimmer.stroke("round", lerp(3.5, 2, t), rng.choice(["#fff1cf", "#ffd89c", "#ffe7b8"]),
                       points=[[cx - half, yy], [cx + half, yy + rng.uniform(-0.6, 0.6)]],
                       opacity=lerp(0.95, 0.35, t), settings={"taper": [0.4, 0.4], "hardness": 0.7})
    for _ in range(170):  # dark wind ripples, wider and darker towards the viewer
        yy = rng.uniform(HORIZON + 20, H - 10)
        t = (yy - HORIZON) / (H - HORIZON)
        x0 = rng.uniform(-40, W)
        ln = rng.uniform(40, 180) * (0.5 + t)
        shimmer.stroke(rng.choice(["fineliner", "pencil"]), lerp(1.2, 3.2, t), hexmix("#4a3f6e", "#141832", t),
                       points=[[x0, yy], [x0 + ln * 0.5, yy + rng.uniform(-2, 2)], [x0 + ln, yy]],
                       opacity=lerp(0.25, 0.6, t), settings={"taper": [0.4, 0.4]})
    for _ in range(90):  # pale catch-lights on ripple tops
        yy = rng.uniform(HORIZON + 10, H - 40)
        x0 = rng.uniform(0, W)
        ln = rng.uniform(20, 90)
        shimmer.stroke("highlighter", rng.uniform(2, 4), "#f5d8c0",
                       points=[[x0, yy], [x0 + ln, yy]], opacity=0.5, settings={"blend": "normal", "taper": [0.3, 0.3]})
    shimmer.stroke("spray", 90, "#fff4d8", points=[[SUN[0] - 80, HORIZON + 18], [SUN[0] + 80, HORIZON + 30]],
                   settings={"density": 10, "spacing": 0.25})
    commit(p, shimmer, [{"type": "blend", "target": "water-light", "value": "normal"}])

    # ---- 8. foreground shore: soft-round body, charcoal/crayon tooth on top -----------------
    shore = Layer("shore", 0, 700, W, H - 700)
    noise_l = Ridge(0, 1, octaves=5, seed=SEED + 7)
    noise_r = Ridge(0, 1, octaves=4, seed=SEED + 8)

    def shore_l(x):  # a headland on the left that slides under the frame by x ~ 800
        return 772 + 300 * max(x, 0) ** 2.1 / 780 ** 2.1 + noise_l(x) * 18

    def shore_r(x):  # a reedy bank rising to the right edge
        return 1012 - 150 * max(x - 1120, 0) ** 1.5 / 480 ** 1.5 + noise_r(x) * 10

    for ridge, xr in ((shore_l, (-20, 820)), (shore_r, (1110, W + 20))):
        x = xr[0]
        while x < xr[1]:
            ry = ridge(x)
            if ry < H + 10:
                shore.stroke("round", rng.uniform(20, 26), jitter_color("#1e202c", 6),
                             points=[[x, ry + 4], [x + rng.uniform(-4, 4), H + 30]], settings={"hardness": 0.75})
            x += 12
        for _ in range(70):
            x = rng.uniform(*xr)
            ry = ridge(x)
            if ry < H - 5:
                y0 = ry + rng.uniform(8, 60)
                shore.stroke(rng.choice(["charcoal", "crayon"]), rng.uniform(10, 22), rng.choice(["#3d3348", "#4b3b45", "#2f3a3c", "#5a4250"]),
                             points=[[x, y0], [x + rng.uniform(-70, 70), y0 + rng.uniform(5, 40)]],
                             opacity=0.55, settings={"texture_strength": 0.85})
        # grass tufts along the crest: little fans of pressure-tapered pencil and brush-pen blades
        for _ in range(55):
            x = rng.uniform(*xr)
            ry = ridge(x)
            if ry > H - 20:
                continue
            for _ in range(rng.randint(3, 6)):
                ang = rng.uniform(-0.5, 0.5)
                hh = rng.uniform(8, 26)
                shore.stroke(rng.choice(["pencil", "brush-pen"]), rng.uniform(1.5, 3), rng.choice(["#2a2a2c", "#3a3330", "#4a3a34"]),
                             points=[[x, ry + 3], [x + math.sin(ang) * hh * 0.5, ry + 3 - hh * 0.5], [x + math.sin(ang) * hh, ry + 3 - hh]],
                             pressure=[1, 0.7, 0.1], opacity=0.9)
        # sun-warmed lip of the shore line
        xs = [x for x in range(int(xr[0]), int(xr[1]), 7) if ridge(x) < H]
        if xs:
            shore.stroke("pencil", 2.5, "#f2b98c", points=[[x, ridge(x) + 1] for x in xs], opacity=0.7)
    commit(p, shore)

    # ---- 9. pines: one small paint layer per tree (cheap to render), grouped later ------------
    near_ridge = ranges[2][1]

    def pine(name, bx, by, height, dark, sz=1.0):
        span_max = height * 0.36 + 30
        trees = Layer(name, int(bx - span_max), int(by - height * 1.06 - 10), int(2 * span_max), int(height * 1.06 + 24))
        trees.stroke("ink", max(1.5, 4 * sz), dark, points=[[bx, by], [bx + rng.uniform(-2, 2), by - height]], opacity=0.95)
        levels = max(6, int(height / (7 * sz)))
        for k in range(levels):
            t = k / levels
            yy = by - height * (0.08 + 0.92 * t)
            span = (1 - t) ** 1.1 * height * 0.30 * rng.uniform(0.75, 1.15) + 3 * sz
            for side in (-1, 1):
                ln = span * rng.uniform(0.7, 1.05)
                droop = ln * rng.uniform(0.15, 0.35)
                trees.stroke("pine", max(4, rng.uniform(7, 12) * sz * (1 - 0.5 * t)), jitter_color(dark, 6),
                             points=[[bx, yy], [bx + side * ln * 0.55, yy + droop * 0.4], [bx + side * ln, yy + droop]],
                             opacity=0.95)
        trees.stroke("pine", 5 * sz, dark, points=[[bx, by - height * 1.02], [bx, by - height * 0.9]])
        commit(p, trees, into="pines")
        PINES.append(name)

    tree_xs = sorted(rng.uniform(10, 560) for _ in range(9))
    for i, tx in enumerate(tree_xs):
        base = shore_l(tx) + 10
        h_ = rng.uniform(170, 360) * (1.15 - tx / 900)
        pine(f"pine-{i + 1}", tx, base, h_, rng.choice(["#141b22", "#1a2224", "#191826"]))
    dtop = int(min(near_ridge(x) for x in range(0, W, 8))) - 30
    trees = Layer("distant-pines", 0, dtop, W, HORIZON + 10 - dtop)
    for _ in range(26):  # distant pines as tiny brush-pen ticks on the near range
        tx = rng.uniform(1180, 1580) if rng.random() < 0.6 else rng.uniform(40, 420)
        base = near_ridge(tx) + rng.uniform(8, 50)
        hh = rng.uniform(10, 22)
        trees.stroke("brush-pen", rng.uniform(4, 6), "#2b2e45", points=[[tx, base], [tx, base - hh]],
                     pressure=[1.0, 0.1], opacity=0.85)
    commit(p, trees)
    FINISH.append({"type": "group", "name": "pines", "targets": PINES})


    # ---- 10. reeds and grasses with pressure curves -------------------------------------
    reeds = Layer("reeds", 900, 640, W - 900, H - 640)
    for _ in range(260):
        bx = rng.uniform(1120, W + 20) if rng.random() < 0.8 else rng.uniform(900, 1120)
        by = H + 10 if bx > 1150 else shore_r(bx) + 30
        hgt = rng.uniform(70, 300) * (0.6 + 0.4 * (bx - 900) / 700)
        lean = rng.uniform(-0.25, 0.45) * hgt
        pts = [[bx, by], [bx + lean * 0.2, by - hgt * 0.4], [bx + lean * 0.6, by - hgt * 0.78], [bx + lean, by - hgt]]
        pressure = [1.0, 0.85, 0.5, 0.05]  # explicit pressure curve, thick at the root
        reeds.stroke("reed", rng.uniform(4, 9), jitter_color(rng.choice(["#1d2121", "#28262c", "#2f2a26"]), 7),
                     points=pts, pressure=pressure, opacity=0.95)
    for _ in range(26):  # cattail heads: thick charcoal dabs on stalk tips
        bx = rng.uniform(1180, 1560)
        by = H + 10
        hgt = rng.uniform(220, 330)
        lean = rng.uniform(-0.05, 0.2) * hgt
        tip = (bx + lean, by - hgt)
        reeds.stroke("ink", 3, "#1e1c1c", points=[[bx, by], [bx + lean * 0.5, by - hgt * 0.55], tip], pressure=[1, 0.8, 0.4])
        reeds.stroke("charcoal", 11, "#3a2420", points=[[tip[0] - lean * 0.02, tip[1] + 34], [tip[0], tip[1] + 6]],
                     settings={"pressure_opacity": False, "texture_strength": 0.4})
        reeds.stroke("ink", 1.5, "#1e1c1c", points=[[tip[0], tip[1] + 6], [tip[0] + lean * 0.01, tip[1] - 16]])
    commit(p, reeds)

    # ---- 11. line work: pencil hatching, ink contour, calligraphy birds -------------------
    lines = Layer("line-work")
    near = ranges[2][1]
    for _ in range(140):  # hatching on the shadow flanks of the near range
        x = rng.uniform(0, W)
        if near(x + 6) - near(x - 6) < -1.0:
            y0 = near(x) + rng.uniform(10, 50)
            lines.stroke("pencil", 1.6, "#2a2640", points=[[x, y0], [x + 14, y0 + 26]], opacity=0.45)
    segs = 0
    x = 0
    while x < W:  # broken ink contour on the near ridge
        ln = rng.uniform(60, 200)
        xs = [x + i * 6 for i in range(int(ln / 6))]
        if len(xs) > 2 and rng.random() < 0.65:
            pr = [0.3 + 0.7 * math.sin(math.pi * i / (len(xs) - 1)) for i in range(len(xs))]
            lines.stroke("fineliner", 1.8, "#25213a", points=[[xx, near(xx) + 1] for xx in xs], pressure=pr, opacity=0.7,
                         settings={"pressure_size": True})
            segs += 1
        x += ln + rng.uniform(20, 120)
    for i in range(9):  # birds: two calligraphy arcs, SVG path strokes
        bx, by = rng.uniform(620, 1000), rng.uniform(170, 330)
        s = rng.uniform(7, 15)
        lines.stroke("calligraphy", 4.5 * s / 10, "#2a2238",
                     path=f"M{bx - s:.1f} {by - s * 0.2:.1f} Q{bx - s * 0.5:.1f} {by - s * 0.65:.1f} {bx:.1f} {by:.1f} "
                          f"Q{bx + s * 0.5:.1f} {by - s * 0.7:.1f} {bx + s * 1.1:.1f} {by - s * 0.35:.1f}", opacity=0.9)
    # a lone heron in ink on the right shore
    hx, hy = 905, 938  # wading in the shallows between the headland and the reeds
    lines.stroke("brush-pen", 7, "#141418", path=f"M{hx} {hy} C{hx - 6} {hy - 30} {hx + 10} {hy - 50} {hx + 2} {hy - 70}")
    lines.stroke("ink", 4, "#141418", path=f"M{hx + 2} {hy - 70} Q{hx + 6} {hy - 84} {hx + 16} {hy - 82} L{hx + 30} {hy - 79}")
    lines.stroke("brush-pen", 16, "#1c1c22", path=f"M{hx - 4} {hy - 8} C{hx - 30} {hy - 20} {hx - 30} {hy + 10} {hx - 46} {hy + 14}")
    lines.stroke("fineliner", 2, "#141418", points=[[hx - 6, hy + 4], [hx - 4, hy + 46]])
    lines.stroke("fineliner", 2, "#141418", points=[[hx + 2, hy + 2], [hx + 6, hy + 46]])
    commit(p, lines)

    # ---- 12. texture: splatter + spray, multiply, low opacity ------------------------------
    tex = Layer("texture")
    for _ in range(16):
        x0, y0 = rng.uniform(0, W), rng.uniform(HORIZON + 60, H)
        tex.stroke("splatter", rng.uniform(8, 20), rng.choice(["#5a3f3a", "#3c3552", "#7a5a48"]),
                   points=[[x0, y0], [x0 + rng.uniform(-200, 200), y0 + rng.uniform(-80, 80)]], opacity=rng.uniform(0.3, 0.7))
    for _ in range(10):
        x0, y0 = rng.uniform(0, W), rng.uniform(HORIZON, H)
        tex.stroke("spray", rng.uniform(40, 90), "#2b2440",
                   points=[[x0, y0], [x0 + rng.uniform(-300, 300), y0 + rng.uniform(-30, 30)]], opacity=0.35)
    commit(p, tex, [{"type": "blend", "target": "texture", "value": "multiply"}, {"type": "opacity", "target": "texture", "value": 0.5}])
    flecks = Layer("flecks")
    for _ in range(10):  # white gouache flecks over sky/water
        x0, y0 = rng.uniform(0, W), rng.uniform(0, H)
        flecks.stroke("splatter", rng.uniform(10, 24), "#fff7e8",
                   points=[[x0, y0], [x0 + rng.uniform(-100, 100), y0 + rng.uniform(-40, 40)]], opacity=0.6)
    commit(p, flecks, [{"type": "opacity", "target": "flecks", "value": 0.7}], into="texture")

    # ---- 13. grading: adjustment layer -------------------------------------------------
    FINISH.extend([
        {"type": "adjustment", "name": "grade", "effects": [
            {"name": "curves", "points": [[0, 12], [70, 58], [150, 160], [255, 250]]},
            {"name": "temperature", "amount": 16},
            {"name": "saturation", "amount": 8},
            {"name": "vignette", "strength": 0.38, "radius": 0.85},
            {"name": "grain", "amount": 0.035, "seed": 7},
        ]},
    ])


# --------------------------------------------------------------------------------------------
# Brush specimen sheet


def specimen_sheet():
    from vixl.brushes import BRUSHES

    names = list(BRUSHES) + ["wash", "pine", "reed", "mist"]
    cols, cw, ch = 4, 400, 210
    rows = math.ceil(len(names) / cols)
    sw, sh = cols * cw, rows * ch + 150
    p = Project(sw, sh, "#f4ecdc")
    fonts = {}
    for family, weight, role in (("Cormorant Garamond", 600, "heading"), ("IBM Plex Mono", 400, "body")):
        try:
            fonts[role] = install_font(p, family, weight, role=role)["name"]
        except Exception as exc:  # network trouble falls back to the bundled proofing font
            print("  font install failed:", exc)
    hfont, bfont = fonts.get("heading"), fonts.get("body")
    p.apply([
        {"type": "brush-define", "name": "wash", "base": "watercolor", "settings": {"flow": 0.045, "texture_strength": 0.14, "size_jitter": 0.18, "hardness": 0.15}},
        {"type": "brush-define", "name": "pine", "base": "dry-brush", "settings": {"bristles": 9, "hardness": 0.9, "taper": [0.02, 0.45], "texture": "grain", "texture_strength": 0.25}},
        {"type": "brush-define", "name": "reed", "base": "brush-pen", "settings": {"taper": [0.05, 0.5], "roundness": 0.6, "angle": 70}},
        {"type": "brush-define", "name": "mist", "base": "airbrush", "settings": {"flow": 0.03, "spacing": 0.08, "pressure_opacity": False}},
        {"type": "text", "name": "title", "text": "Brush specimens", "size": 64, "color": "#2a2238", "x": 40, "y": 28,
         **({"font": hfont} if hfont else {})},
        {"type": "text", "name": "subtitle", "text": "17 built-in presets + 4 brush-define customs  ·  pressure 0.15 → 1 → 0.3  ·  seed 7",
         "size": 18, "color": "#6b5d6e", "x": 44, "y": 104, **({"font": bfont} if bfont else {})},
    ], detail="compact")
    sheet = Layer("strokes", 0, 0, sw, sh)
    palette = ["#2a3b6b", "#7b3045", "#2f5d50", "#8a5a1e", "#4b2f6b"]
    labels = []
    for i, name in enumerate(names):
        cx, cy = (i % cols) * cw, 150 + (i // cols) * ch
        size = {"spray": 46, "splatter": 22, "watercolor": 42, "wash": 46, "airbrush": 50, "mist": 60, "dry-brush": 34,
                "pine": 22, "highlighter": 26, "marker": 22, "chalk": 22, "charcoal": 24, "crayon": 20, "soft-round": 30,
                "calligraphy": 20, "pencil": 6, "fineliner": 5, "ink": 12, "brush-pen": 16, "reed": 14, "round": 16}.get(name, 14)
        color = palette[i % len(palette)]
        if name in ("highlighter",):
            color = "#e8b923"
        path = f"M{cx + 40} {cy + 110} C{cx + 130} {cy + 20} {cx + 230} {cy + 170} {cx + 360} {cy + 70}"
        sheet.stroke(name, size, color, path=path, seed=7)
        # pressure-curve variant underneath as points with explicit pressure
        pts = [[cx + 40 + k * 32, cy + 150 + 10 * math.sin(k * 0.8)] for k in range(11)]
        pr = [0.15, 0.4, 0.7, 0.95, 1, 1, 0.9, 0.75, 0.55, 0.4, 0.3]
        sheet.stroke(name, size * 0.45, color, points=pts, pressure=pr, seed=8, opacity=0.9)
        custom = name in ("wash", "pine", "reed", "mist")
        labels.append({"type": "text", "name": f"label-{name}", "text": name + ("  (custom)" if custom else ""), "size": 20,
                       "color": "#7b3045" if custom else "#2a2238", "x": cx + 40, "y": cy + 12, **({"font": bfont} if bfont else {})})
    t = time.perf_counter()
    p.apply(sheet.ops + labels, detail="compact")
    strokes_per_layer["specimen-sheet"] = sheet.count
    p.apply([{"type": "shape", "shape": "line", "name": f"rule-{r}", "width": sw - 80, "height": 1, "x": 40, "y": 150 + r * ch - 6,
              "stroke": "#cdbfa8", "stroke_width": 1} for r in range(rows)], detail="compact")
    return p


# --------------------------------------------------------------------------------------------


WORK = OUT / "branches"
LAYER_ORDER = ["sky-wash", "clouds", "range-far", "range-mid", "mist", "range-near", "distant-pines", "water", "range-far-reflection",
               "range-mid-reflection", "range-near-reflection", "water-light", "shore", "PINES", "reeds", "line-work",
               "texture", "flecks"]


def vixl_cli(args, request, cwd):
    out = subprocess.run(["vixl", *args, "--request", "-", "--workspace", str(cwd)], input=json.dumps(request),
                         capture_output=True, text=True, cwd=cwd, env=os.environ)
    if out.returncode:
        raise RuntimeError(out.stdout + out.stderr)
    return json.loads(out.stdout)


def paint_branch(job):
    """Worker: open one forked branch document, paint its layers, save. Returns timing."""
    name, layers, extra = job
    t = time.perf_counter()
    doc = Project.load(WORK / f"{name}.vixl")
    ops = [op for layer in layers for op in layer.ops] + extra
    for i in range(0, len(ops), 900):  # Project.apply accepts at most 1000 operations per batch
        doc.apply(ops[i : i + 900], detail="compact")
    doc.save()
    return name, round(time.perf_counter() - t, 2), sum(layer.count for layer in layers)


def build_painting():
    """Each layer is painted on its own Vixl branch (in parallel), then three-way merged into one document."""
    from multiprocessing import Pool

    paint_landscape()
    WORK.mkdir()
    src = WORK / "painting.vixl"
    base = Project(W, H, "#f1e7d3")  # warm cold-press paper
    base.apply(BASE_OPS, detail="compact")
    base.save(src)
    with timed("branch-fork x%d" % len(BRANCHES)):
        for name, *_ in BRANCHES:
            vixl_cli(["-p", "painting.vixl", "workflow", "branch-fork"], {"branch": name, "output": f"{name}.vixl", "author": name}, WORK)
    with timed("paint branches (4 worker processes)"):
        with Pool(4) as pool:
            for name, secs, n in pool.imap_unordered(paint_branch, BRANCHES):
                apply_times[name] = secs
                print(f"    branch {name}: {n} strokes painted in {secs} s", flush=True)
    with timed("branch-merge x%d" % len(BRANCHES)):
        # A merged branch's new layers land at the *bottom* of the stack, so merge top-most first.
        for name, *_ in reversed(BRANCHES):
            r = vixl_cli(["-p", "painting.vixl", "workflow", "branch-merge"], {"branch": name, "dry_run": False}, WORK)
            assert r.get("success"), r
    p = Project.load(src)
    with timed("finishing ops"):
        order = [m for n in LAYER_ORDER for m in (PINES if n == "PINES" else [n])]
        p.apply([{"type": "top", "target": n} for n in order] + FINISH, detail="compact")
    return p


def isolate_layers(p):
    """Render every top-level layer alone (RGBA) -- each is a disk-cache hit after the full render.
    The pines group is split so the trees appear one by one in the timelapse."""
    from vixl.render_cache import enable

    tops = [l for l in p.state["layers"] if not l.get("parent")]
    units = []
    for layer in tops:
        if layer["type"] == "adjustment":
            continue
        if layer["name"] == "pines":
            kids = [l for l in p.state["layers"] if l.get("parent") == layer["id"]]
            units += [(kid, layer, kids) for kid in kids]
        else:
            units.append((layer, None, []))
    out = []
    for layer, group, siblings in units:
        c = p.clone()
        enable(c, CACHE / "render")
        keep = {layer["id"], group["id"] if group else None}
        hide = [{"type": "hide", "target": o["id"]} for o in tops + siblings if o["id"] not in keep and o.get("visible", True)]
        c.apply(hide + [{"type": "canvas", "background": "transparent"}], detail="compact")
        path = FRAMES / f"{layer['name']}.png"
        c.export(path)
        out.append((layer["name"], path, layer.get("blend", "normal")))
    return out


def timelapse(p):
    """A light document of pre-rendered layer plates whose opacities are keyframed in painting order."""
    plates = isolate_layers(p)
    grade = next(l for l in p.state["layers"] if l["type"] == "adjustment")
    t = Project(W, H, "#f1e7d3")
    ops = [{"type": "add", "path": str(path), "name": name} for name, path, _ in plates]
    ops += [{"type": "blend", "target": name, "value": blend} for name, _, blend in plates if blend != "normal"]
    ops += [{"type": "adjustment", "name": "grade", "effects": grade["effects"]},
            {"type": "timeline-set", "duration": "10s", "fps": 12, "loop": 0}]
    step = 7.4 / len(plates)
    for i, (name, _, _) in enumerate(plates + [("grade", None, None)]):
        start = 0.3 + i * step
        ops += [{"type": "keyframe", "target": name, "property": "opacity", "time": 0, "value": 0, "easing": "hold"},
                {"type": "animate", "target": name, "property": "opacity", "from": 0, "to": 1,
                 "start": f"{start:.2f}s", "duration": f"{step * 1.6:.2f}s", "easing": "ease-out"}]
    ops.append({"type": "marker", "name": "finished", "time": "8.6s"})
    t.apply(ops, detail="compact")
    return t


FRAMES = CACHE / "plates"


def main():
    from vixl.render_cache import enable

    print(f"seed {SEED}")
    with timed("build painting (generate + branches + merge)"):
        p = build_painting()
    enable(p, CACHE / "render")  # persistent per-layer PNG cache: later renders reuse the strokes
    with timed("first render (painting, cold)"):
        p.export(OUT / "painting.jpg", quality=93)
    with timed("second render (painting, disk cache)"):
        p.render()
    p.save(OUT / "painting.vixl")
    shutil.rmtree(WORK, ignore_errors=True)
    if os.environ.get("QUICK"):
        print(json.dumps({"strokes": strokes_per_layer, "apply": apply_times, "timings": timings}, indent=1))
        return

    with timed("specimen sheet (apply + render)"):
        s = specimen_sheet()
        s.export(OUT / "brush-specimens.png")

    # Stylized variants: an artistic filter on an adjustment layer above the whole painting.
    variants = {
        "variant-oil-paint": [{"name": "oil-paint", "amount": 4}, {"name": "saturation", "amount": 12}],
        "variant-watercolor": [{"name": "watercolor", "amount": 100, "seed": 3}, {"name": "brightness", "amount": 4}],
        "variant-riso-halftone": [{"name": "brightness", "amount": 28}, {"name": "contrast", "amount": 15},
                                  {"name": "halftone", "amount": 5},
                                  {"name": "duotone", "amount": 100, "shadow_color": "#2b2452", "highlight_color": "#f5e6c8"}],
        "variant-pencil-sketch": [{"name": "pencil-sketch", "amount": 100, "radius": 10}],
    }
    for name, effects in variants.items():
        with timed(name):
            v = p.clone()
            enable(v, CACHE / "render")
            v.apply([{"type": "adjustment", "name": "stylize", "effects": effects}], detail="compact")
            v.export(OUT / f"{name}.jpg", quality=88)
    FRAMES.mkdir(parents=True, exist_ok=True)
    with timed("timelapse plates (isolated layer renders)"):
        t = timelapse(p)
    with timed("timelapse contact sheet"):
        export_timeline(t, OUT / "timelapse-sheet.png", format="sheet", columns=5, scale=0.2, fps=1.5)
        (OUT / "timelapse-sheet.json").unlink(missing_ok=True)  # sheet export also writes frame metadata
    with timed("timelapse GIF (0.35x, 10 fps, 64 colors)"):
        r = export_timeline(t, OUT / "timelapse.gif", scale=0.35, fps=10, colors=64)
        print("   gif", r)
    with timed("timelapse MP4 (0.6x, 12 fps)"):
        export_timeline(t, OUT / "timelapse.mp4", scale=0.6)

    shutil.rmtree(CACHE, ignore_errors=True)
    total = sum(v for k, v in strokes_per_layer.items() if k != "specimen-sheet")
    stats = {"seed": SEED, "canvas": [W, H], "strokes_per_layer": strokes_per_layer, "painting_strokes_total": total,
             "branch_paint_seconds": apply_times, "timings_seconds": timings,
             "files": {f.name: f.stat().st_size for f in sorted(OUT.iterdir())}}
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
