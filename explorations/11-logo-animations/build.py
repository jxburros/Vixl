"""Vixl logo builds: seven ways to assemble the Digital Shift logo from nothing (or something simpler).

Run from the repo root:  python explorations/11-logo-animations/build.py [name ...]
Everything is written to explorations/11-logo-animations/output/. Each build starts from the editable
master in assets/brand/digital-shift and only adds keyframes (and temporary helper layers), so every
animation ends on the exact logo.
"""

import json
import math
import os
import random
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
SRC = ROOT / "assets" / "brand" / "digital-shift" / "Editable-Vixl" / "horizontal-color.vixl"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
sys.path.insert(0, str(ROOT / "src"))

from vixl import Project  # noqa: E402
from vixl.timeline import contact_sheet, export_timeline  # noqa: E402

FPS = 30
HOLD = 1400  # ms the finished logo stays on screen before the loop restarts
CHARCOAL = "#252b39"
BLUE = "#3575ee"
UPPER, LOWER, WORD = "Downward V", "Upward V offset", "Wordmark"
UPPER_PIXELS = ["Upper pixel 1", "Upper pixel 2", "Upper pixel 3"]
LOWER_PIXELS = ["Lower pixel 1", "Lower pixel 2", "Lower pixel 3"]
PIXELS = UPPER_PIXELS + LOWER_PIXELS
CELL = 14.4  # half of the logo's 28.8 px stair step, so the grid lines up with the stairs
MEET = (268.0, 240.0)  # where the two V's touch


def load():
    p = Project.load(SRC)
    p.apply([{"type": "canvas", "background": "#ffffff"},
             {"type": "timeline-set", "fps": FPS, "loop": 0, "loop_mode": "off"}])
    return p


def layer(p, name):
    return next(item for item in p.state["layers"] if item["name"] == name)


def centre(p, name):
    item = layer(p, name)
    return item["x"] + item["width"] / 2, item["y"] + item["height"] / 2


def polygon(p, name):
    """The V's outline in canvas pixels (its path is straight segments in local pixels)."""
    item = layer(p, name)
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", item["path"])]
    return [(item["x"] + nums[i], item["y"] + nums[i + 1]) for i in range(0, len(nums), 2)]


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def grid(p, name):
    """Grid cells over the V's bounding box, aligned to its origin; each knows whether it is part of the V."""
    item = layer(p, name)
    poly = polygon(p, name)
    cells = []
    for row in range(round(item["height"] / CELL)):
        for col in range(round(item["width"] / CELL)):
            x, y = item["x"] + col * CELL, item["y"] + row * CELL
            cells.append({"x": x, "y": y, "cx": x + CELL / 2, "cy": y + CELL / 2, "row": row, "col": col,
                          "in": inside((x + CELL / 2, y + CELL / 2), poly)})
    return cells


def add_cells(p, cells, prefix, fill):
    """Pixel squares, slightly oversized so neighbours overlap instead of showing hairline seams."""
    ops, names = [], []
    for i, c in enumerate(cells):
        name = f"{prefix}{i}"
        names.append(name)
        ops.append({"type": "shape", "shape": "rectangle", "name": name, "x": round(c["x"] - 0.3, 2),
                    "y": round(c["y"] - 0.3, 2), "width": CELL + 0.6, "height": CELL + 0.6, "fill": fill})
    p.apply(ops)
    return names


def hide_until(names, time, duration=1, easing="linear"):
    return [{"type": "animate", "target": n, "property": "opacity", "from": 0, "to": 1, "start": time,
             "duration": duration, "easing": easing} for n in names]


def fly_from(name, dx, dy, start, duration, easing="ease-out-cubic"):
    return [{"type": "animate", "target": name, "property": "translate-x", "from": dx, "to": 0,
             "start": start, "duration": duration, "easing": easing},
            {"type": "animate", "target": name, "property": "translate-y", "from": dy, "to": 0,
             "start": start, "duration": duration, "easing": easing}]


def pixels_burst(p, start, origin_upper=(396, 118), origin_lower=(142, 363), stagger=90):
    """The detached pixels shoot out of the stair corners and settle into place."""
    ops = []
    for group, origin in ((UPPER_PIXELS, origin_upper), (LOWER_PIXELS, origin_lower)):
        for i, name in enumerate(group):
            cx, cy = centre(p, name)
            t = start + i * stagger
            ops += fly_from(name, origin[0] - cx, origin[1] - cy, t, 480, "ease-out-back")
            ops.append({"type": "animate", "target": name, "property": "scale", "from": 0, "to": 1,
                        "start": t, "duration": 300, "easing": "ease-out-cubic"})
    return ops


def crossfade_to_vector(cells, start, duration=260):
    """Swap the pixel scaffold for the crisp vector V's (which sit above it)."""
    ops = hide_until([UPPER, LOWER], start, duration, "ease-in-out")
    ops += [{"type": "animate", "target": n, "property": "opacity", "to": 0, "start": start + duration // 2,
             "duration": duration, "easing": "ease-in"} for n in cells]
    return ops


def finish(p):
    timeline = p.state["timeline"]
    end = max(key["time"] for track in timeline.get("tracks", []) for key in track.get("keys", []))
    p.apply([{"type": "timeline-set", "duration": int(end + HOLD)}])
    return p


# ---------------------------------------------------------------------------------------------------
# 1. Slide and lock: the two V's slam in from opposite edges, click together and spit out their pixels.
def slide_lock():
    p = load()
    p.apply([{"type": "group", "name": "Mark", "targets": [UPPER, LOWER]}])
    ops = [
        {"type": "animate", "target": UPPER, "property": "translate-y", "from": -330, "to": 0, "start": 0,
         "duration": 620, "easing": "ease-out-quart"},
        {"type": "animate", "target": UPPER, "property": "opacity", "from": 0, "to": 1, "start": 0, "duration": 160},
        {"type": "animate", "target": LOWER, "property": "translate-y", "from": 330, "to": 0, "start": 140,
         "duration": 620, "easing": "ease-out-quart"},
        {"type": "animate", "target": LOWER, "property": "opacity", "from": 0, "to": 1, "start": 140, "duration": 160},
        # The click: a quick squash of the whole mark as the second V lands.
        {"type": "keyframe", "target": "Mark", "property": "scale", "time": 700, "value": 1, "easing": "ease-out-quad"},
        {"type": "keyframe", "target": "Mark", "property": "scale", "time": 780, "value": 0.94, "easing": "ease-out-back"},
        {"type": "keyframe", "target": "Mark", "property": "scale", "time": 1050, "value": 1},
    ]
    ops += pixels_burst(p, 760)
    ops.append({"type": "text-animate", "target": WORD, "preset": "slide-left", "unit": "char", "start": 1050,
                "duration": 520, "stagger": 80, "distance": 140})
    p.apply(ops)
    return finish(p)


# 2. Pixel swarm: a cloud of loose pixels flies in and snaps into the two V's, then resolves into vectors.
def pixel_swarm():
    p = load()
    rng = random.Random(11)
    upper = [c for c in grid(p, UPPER) if c["in"]]
    lower = [c for c in grid(p, LOWER) if c["in"]]
    cells = add_cells(p, upper, "u", CHARCOAL) + add_cells(p, lower, "l", BLUE)
    p.apply([{"type": "top", "target": UPPER}, {"type": "top", "target": LOWER}])
    ops = []
    for name, c in zip(cells, upper + lower):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(260, 620)
        t = int(rng.uniform(0, 650))
        ops += fly_from(name, math.cos(angle) * dist, math.sin(angle) * dist, t, 950)
        ops.append({"type": "animate", "target": name, "property": "rotation", "from": rng.uniform(-200, 200),
                    "to": 0, "start": t, "duration": 950, "easing": "ease-out-cubic"})
        ops.append({"type": "animate", "target": name, "property": "opacity", "from": 0, "to": 1, "start": t,
                    "duration": 250})
    ops += crossfade_to_vector(cells, 1680)
    ops += [{"type": "animate-preset", "targets": PIXELS, "preset": "pop-in", "start": 1650, "duration": 360,
             "stagger": 70}]
    ops.append({"type": "text-animate", "target": WORD, "preset": "fade-up", "unit": "char", "start": 1900,
                "duration": 500, "stagger": 70})
    p.apply(ops)
    return finish(p)


# 3. Pop-in: the V's pop into existence pixel by pixel, rippling outward from where they meet.
def ripple_pop():
    p = load()
    upper = [c for c in grid(p, UPPER) if c["in"]]
    lower = [c for c in grid(p, LOWER) if c["in"]]
    cells = add_cells(p, upper, "u", CHARCOAL) + add_cells(p, lower, "l", BLUE)
    p.apply([{"type": "top", "target": UPPER}, {"type": "top", "target": LOWER}])
    ops = []
    for name, c in zip(cells, upper + lower):
        t = int(math.dist((c["cx"], c["cy"]), MEET) * 3.4)
        ops.append({"type": "animate", "target": name, "property": "scale", "from": 0, "to": 1, "start": t,
                    "duration": 300, "easing": "ease-out-back"})
    ops += crossfade_to_vector(cells, 1100)
    ops.append({"type": "animate-preset", "targets": UPPER_PIXELS + LOWER_PIXELS[::-1], "preset": "pop-in",
                "start": 1050, "duration": 380, "stagger": 110, "easing": "elastic-out"})
    ops.append({"type": "text-animate", "target": WORD, "preset": "pop", "unit": "char", "start": 1350,
                "duration": 450, "stagger": 90})
    p.apply(ops)
    return finish(p)


# 4. Break apart: two plain offset bars appear, then shatter away to leave the V's carved out of them.
def pieces(cells):
    """Split a bar's grid into V cells plus debris; whole 2x2 blocks of debris break off as one chunk."""
    by_pos = {(c["row"], c["col"]): c for c in cells}
    out = []
    for row in range(0, max(r for r, _ in by_pos) + 1, 2):
        for col in range(0, max(k for _, k in by_pos) + 1, 2):
            block = [by_pos[(row + dr, col + dc)] for dr in (0, 1) for dc in (0, 1) if (row + dr, col + dc) in by_pos]
            if len(block) == 4 and not any(c["in"] for c in block):
                first = block[0]
                out.append(dict(first, cx=first["x"] + CELL, cy=first["y"] + CELL, size=2 * CELL))
            else:
                out += [dict(c, size=CELL) for c in block]
    return out


def break_apart():
    p = load()
    rng = random.Random(4)
    slabs = []
    for vname, prefix, fill in ((UPPER, "u", CHARCOAL), (LOWER, "l", BLUE)):
        parts = pieces(grid(p, vname))
        names = [f"{prefix}{i}" for i in range(len(parts))]
        ops = [{"type": "shape", "shape": "rectangle", "name": n, "x": round(c["x"] - 0.3, 2),
                "y": round(c["y"] - 0.3, 2), "width": c["size"] + 0.6, "height": c["size"] + 0.6, "fill": fill}
               for n, c in zip(names, parts)]
        if vname == LOWER:
            box = layer(p, LOWER)
            ops.append({"type": "shape", "shape": "rectangle", "name": "Lower cover", "x": box["x"] - 0.3,
                        "y": box["y"] - 0.3, "width": box["width"] + 0.6, "height": box["height"] + 0.6,
                        "fill": CHARCOAL})
            names.append("Lower cover")
        p.apply(ops)
        slabs.append((names, parts))
    p.apply([{"type": "group", "name": "Upper slab", "targets": slabs[0][0]},
             {"type": "group", "name": "Lower slab", "targets": slabs[1][0]},
             {"type": "pivot", "target": "Upper slab", "value": "left"},
             {"type": "pivot", "target": "Lower slab", "value": "right"},
             {"type": "pivot", "target": "Lower cover", "value": "left"},
             {"type": "top", "target": UPPER}, {"type": "top", "target": LOWER}])
    ops = [
        {"type": "animate", "target": "Upper slab", "property": "scale-x", "from": 0, "to": 1, "start": 0,
         "duration": 450, "easing": "ease-out-cubic"},
        {"type": "animate", "target": "Lower slab", "property": "scale-x", "from": 0, "to": 1, "start": 120,
         "duration": 450, "easing": "ease-out-cubic"},
        # The lower bar takes on the brand blue in a wipe from right to left.
        {"type": "animate", "target": "Lower cover", "property": "scale-x", "from": 1, "to": 0, "start": 650,
         "duration": 380, "easing": "ease-in-out-cubic"},
    ]
    # Everything that is not part of a V cracks off and falls away, outward from the centre line.
    for (names, parts), direction in zip(slabs, (-1, 1)):
        for name, c in zip(names, parts):
            if c["in"]:
                continue
            t = 1150 + int(abs(c["cx"] - MEET[0]) * 1.2 + rng.uniform(0, 160))
            dx = (c["cx"] - MEET[0]) * rng.uniform(0.3, 0.8)
            dy = direction * rng.uniform(120, 260) + rng.uniform(-40, 40)
            ops += [{"type": "animate", "target": name, "property": "translate-x", "to": dx, "start": t,
                     "duration": 650, "easing": "ease-out-quad"},
                    {"type": "animate", "target": name, "property": "translate-y", "to": dy, "start": t,
                     "duration": 650, "easing": "ease-in-quad"},
                    {"type": "animate", "target": name, "property": "rotation", "to": rng.uniform(-160, 160),
                     "start": t, "duration": 650, "easing": "linear"},
                    {"type": "animate", "target": name, "property": "opacity", "to": 0, "start": t + 250,
                     "duration": 400, "easing": "ease-in"}]
    ops += crossfade_to_vector(["Upper slab", "Lower slab"], 2050)
    ops += pixels_burst(p, 1700, stagger=110)
    ops.append({"type": "text-animate", "target": WORD, "preset": "fade-up", "unit": "char", "start": 2150,
                "duration": 500, "stagger": 70})
    p.apply(ops)
    return finish(p)


# 5. Draw-on: outlines trace the V's like a pen, then the fill floods in and the name types itself out.
def draw_on():
    p = load()
    p.apply([{"type": "duplicate", "target": UPPER, "name": "Upper outline"},
             {"type": "duplicate", "target": LOWER, "name": "Lower outline"},
             {"type": "shape", "target": "Upper outline", "fill": "none", "stroke": CHARCOAL, "stroke_width": 6},
             {"type": "shape", "target": "Lower outline", "fill": "none", "stroke": BLUE, "stroke_width": 6}])
    ops = [
        {"type": "animate", "target": "Upper outline", "property": "trim_end", "from": 0, "to": 100, "start": 0,
         "duration": 1100, "easing": "ease-in-out-cubic"},
        {"type": "animate", "target": "Lower outline", "property": "trim_end", "from": 0, "to": 100, "start": 250,
         "duration": 1100, "easing": "ease-in-out-cubic"},
    ]
    ops += hide_until([UPPER], 1150, 350, "ease-out")
    ops += hide_until([LOWER], 1350, 350, "ease-out")
    ops += [{"type": "animate", "target": n, "property": "opacity", "to": 0, "start": t, "duration": 300}
            for n, t in (("Upper outline", 1450), ("Lower outline", 1650))]
    ops.append({"type": "animate-preset", "targets": PIXELS, "preset": "pop-in", "start": 1500, "duration": 300,
                "stagger": 80})
    ops.append({"type": "text-animate", "target": WORD, "preset": "typewriter", "unit": "char", "start": 1800,
                "duration": 600})
    p.apply(ops)
    return finish(p)


# 6. Grow from a seed: one pixel appears, splits in two, and each half stretches and unfolds into a V.
def seed_grow():
    p = load()
    upper, lower = layer(p, UPPER), layer(p, LOWER)
    up_tip = (upper["x"] + 144, upper["y"] + upper["height"] - CELL)   # bottom flat of the upper V
    lo_tip = (lower["x"] + 144, lower["y"] + CELL)                     # top flat of the lower V
    size = 28.8
    p.apply([{"type": "shape", "shape": "rectangle", "name": "Seed blue", "x": MEET[0] - size / 2,
              "y": MEET[1] - size / 2, "width": size, "height": size, "fill": BLUE},
             {"type": "shape", "shape": "rectangle", "name": "Seed", "x": MEET[0] - size / 2,
              "y": MEET[1] - size / 2, "width": size, "height": size, "fill": CHARCOAL},
             {"type": "pivot", "target": UPPER, "value": [0.5, 1]},
             {"type": "pivot", "target": LOWER, "value": [0.5, 0]}])
    ops = [
        {"type": "animate-preset", "target": "Seed", "preset": "pop-in", "start": 0, "duration": 380},
        {"type": "animate-preset", "target": "Seed", "preset": "pulse", "start": 420, "duration": 300, "amount": 1.25},
        {"type": "animate", "target": "Seed blue", "property": "opacity", "from": 0, "to": 1, "start": 700,
         "duration": 1},
    ]
    ops += [{"type": "animate", "target": "Seed", "property": prop, "to": val, "start": 720, "duration": 300,
             "easing": "ease-in-out-cubic"}
            for prop, val in (("translate-x", up_tip[0] - MEET[0]), ("translate-y", up_tip[1] - MEET[1]))]
    ops += [{"type": "animate", "target": "Seed blue", "property": prop, "to": val, "start": 720, "duration": 300,
             "easing": "ease-in-out-cubic"}
            for prop, val in (("translate-x", lo_tip[0] - MEET[0]), ("translate-y", lo_tip[1] - MEET[1]))]
    for name, t in ((UPPER, 1000), (LOWER, 1080)):
        ops += [{"type": "animate", "target": name, "property": "opacity", "from": 0, "to": 1, "start": t,
                 "duration": 60},
                {"type": "animate", "target": name, "property": "scale-y", "from": 0.17, "to": 1, "start": t,
                 "duration": 380, "easing": "ease-out-cubic"},
                {"type": "animate", "target": name, "property": "scale-x", "from": 0.2, "to": 1, "start": t + 220,
                 "duration": 520, "easing": "ease-out-back"}]
    ops += [{"type": "animate", "target": n, "property": "opacity", "to": 0, "start": 1100, "duration": 120}
            for n in ("Seed", "Seed blue")]
    ops += pixels_burst(p, 1550, stagger=100)
    ops.append({"type": "text-animate", "target": WORD, "preset": "slide-right", "unit": "char", "start": 1700,
                "duration": 520, "stagger": 60, "distance": 90})
    p.apply(ops)
    return finish(p)


# 7. Digital shift: the logo glitches into place with RGB-split ghosts and jittering, stepped offsets.
def glitch():
    p = load()
    rng = random.Random(7)
    parts = [UPPER, LOWER, WORD]
    ghosts = []
    setup = []
    for part in parts:
        for tint, suffix in (("#00d8ff", "cyan"), ("#ff2fb3", "magenta")):
            name = f"{part} {suffix}"
            ghosts.append((name, part))
            setup.append({"type": "duplicate", "target": part, "name": name})
            if part == WORD:
                setup.append({"type": "text-set", "target": name, "color": tint})
            else:
                setup.append({"type": "shape", "target": name, "fill": tint})
            setup.append({"type": "blend", "target": name, "mode": "multiply"})
    p.apply(setup)
    windows = {UPPER: (0, 900), LOWER: (150, 1050), WORD: (900, 1750)}
    step = 1000 // FPS * 2  # glitch updates every other frame
    ops = []

    def jitter(name, start, end, spread, flicker):
        t = start
        ops.append({"type": "keyframe", "target": name, "property": "opacity", "time": 0, "value": 0,
                    "easing": "hold"})
        while t < end:
            settle = 1 - (t - start) / (end - start)
            ops.append({"type": "keyframe", "target": name, "property": "translate-x", "time": t,
                        "value": round(rng.uniform(-spread, spread) * settle, 1), "easing": "hold"})
            ops.append({"type": "keyframe", "target": name, "property": "translate-y", "time": t,
                        "value": round(rng.uniform(-spread, spread) * 0.25 * settle, 1), "easing": "hold"})
            ops.append({"type": "keyframe", "target": name, "property": "opacity", "time": t,
                        "value": flicker if rng.random() < 0.3 else 1, "easing": "hold"})
            t += step
        for prop, value in (("translate-x", 0), ("translate-y", 0), ("opacity", 1)):
            ops.append({"type": "keyframe", "target": name, "property": prop, "time": end, "value": value})

    for part in parts:
        jitter(part, *windows[part], spread=34, flicker=0)
    for name, part in ghosts:
        start, end = windows[part]
        jitter(name, start, end, spread=46, flicker=0.2)
        ops.append({"type": "animate", "target": name, "property": "opacity", "from": 1, "to": 0,
                    "start": end + 1, "duration": 220, "easing": "ease-out"})
    for i, name in enumerate(PIXELS):
        t = 1000 + i * 70
        ops += [{"type": "keyframe", "target": name, "property": "opacity", "time": 0, "value": 0, "easing": "hold"},
                {"type": "keyframe", "target": name, "property": "opacity", "time": t, "value": 1, "easing": "hold"},
                {"type": "keyframe", "target": name, "property": "opacity", "time": t + 66, "value": 0, "easing": "hold"},
                {"type": "keyframe", "target": name, "property": "opacity", "time": t + 133, "value": 1}]
    p.apply(ops)
    return finish(p)


BUILDS = {
    "01-slide-lock": slide_lock,
    "02-pixel-swarm": pixel_swarm,
    "03-ripple-pop": ripple_pop,
    "04-break-apart": break_apart,
    "05-draw-on": draw_on,
    "06-seed-grow": seed_grow,
    "07-glitch-shift": glitch,
}


def render(name, p):
    for suffix in (".gif", ".mp4", "-sheet.png"):
        (OUT / f"{name}{suffix}").unlink(missing_ok=True)
    scale = min(0.6, 800 / p.state["canvas"]["width"])
    fps = FPS if p.state["timeline"]["duration"] <= 12000 else 20  # long GIFs stay inside the frame budget
    gif = export_timeline(p, OUT / f"{name}.gif", scale=round(scale, 3), fps=fps, colors=128, dither="none")
    mp4 = export_timeline(p, OUT / f"{name}.mp4", scale=1.0)
    build_end = p.state["timeline"]["duration"] - HOLD
    times = [round(build_end * i / 9) for i in range(10)] + [p.state["timeline"]["duration"]]
    sheet = contact_sheet(p, times=times[1:], columns=5, max_width=2000)
    sheet.convert("RGB").save(OUT / f"{name}-sheet.png")
    return {"name": name, "duration_ms": p.state["timeline"]["duration"], "layers": len(p.state["layers"]),
            "gif_bytes": gif.get("bytes"), "mp4_bytes": mp4.get("bytes")}


def main(selected):
    from build_more import MORE
    BUILDS.update(MORE)

    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    for name, build in sorted(BUILDS.items()):
        if selected and not any(s in name for s in selected):
            continue
        info = render(name, build())
        print(json.dumps(info))
        report.append(info)
    if not selected:
        (OUT / "build-log.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
