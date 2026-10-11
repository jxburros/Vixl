"""Second set of logo builds: the logo assembled by Vixl's own features, in a design app and in a terminal.

Run through build.py (python explorations/11-logo-animations/build.py [name ...]), which registers these.
"""

import math
import random

from build import (BLUE, CELL, CHARCOAL, FPS, LOWER, LOWER_PIXELS, PIXELS, UPPER, UPPER_PIXELS, WORD, SRC,
                   finish, inside, layer, polygon)
from vixl import Project
from vixl.typefaces import install_font

LOGO_LAYERS = PIXELS + [WORD, UPPER, LOWER]
CONTENT = (90, 75, 983, 406)  # the logo's visible extent in the master, x0 y0 x1 y1
MONO, UI, UI_BOLD = "jetbrains-mono-500", "inter-500", "inter-700"


def stage(width, height, background, cx=None, cy=None):
    """The master on a bigger canvas, with the logo's visible extent centred on (cx, cy)."""
    p = Project.load(SRC)
    cx = width / 2 if cx is None else cx
    cy = height / 2 if cy is None else cy
    dx = round(cx - (CONTENT[0] + CONTENT[2]) / 2, 1)
    dy = round(cy - (CONTENT[1] + CONTENT[3]) / 2, 1)
    p.apply([{"type": "canvas", "width": width, "height": height, "background": background},
             {"type": "timeline-set", "fps": FPS, "loop": 0, "loop_mode": "off"},
             {"type": "move", "targets": LOGO_LAYERS, "x": dx, "y": dy, "relative": True}])
    return p


def fonts(p, *names):
    table = {MONO: ("JetBrains Mono", 500), UI: ("Inter", 500), UI_BOLD: ("Inter", 700)}
    for name in names:
        install_font(p, *table[name])


def key(target, prop, time, value, easing="linear"):
    return {"type": "keyframe", "target": target, "property": prop, "time": int(time), "value": value,
            "easing": easing}


def tween(target, prop, start, duration, to, frm=None, easing="ease-in-out-cubic"):
    op = {"type": "animate", "target": target, "property": prop, "to": to, "start": int(start),
          "duration": int(duration), "easing": easing}
    if frm is not None:
        op["from"] = frm
    return op


def appear(target, time, duration=1):
    return tween(target, "opacity", time, duration, 1, 0, "ease-out")


def rect(name, x, y, w, h, fill, **extra):
    return dict({"type": "shape", "shape": "rectangle", "name": name, "x": x, "y": y, "width": w, "height": h,
                 "fill": fill}, **extra)


def text(name, content, x, y, size, color, font, **extra):
    return dict({"type": "text", "name": name, "text": content, "x": x, "y": y, "size": size, "color": color,
                 "font": font}, **extra)


# ---------------------------------------------------------------------------------------------------
# 10. Layer stack: the logo's layers hang in an exploded 3D stack, then collapse into one flat logo.
def layer_stack():
    W, H = 1600, 900
    p = stage(W, H, "#e9edf4", cy=470)
    fonts(p, MONO)
    ox = layer(p, UPPER)["x"] - 108  # how far the logo moved
    oy = layer(p, UPPER)["y"] - 75
    plate = (ox + 50, oy + 35, 953 + 40 - 30, 371 + 50)
    planes = [("Downward V", [UPPER]), ("Upward V", [LOWER]), ("Pixels x6", PIXELS), ("Wordmark", [WORD])]
    ops = []
    for i, (label, parts) in enumerate(planes):
        ops += [rect(f"Plate {i}", *plate, "#ffffff", radius=18, stroke="#b8c3d6", stroke_width=3, opacity=0.6),
                text(f"Label {i}", f"layer {i + 1}  {label}", plate[0] + 24, plate[1] + 18, 26, "#7d8aa3", MONO)]
    p.apply(ops)
    ops = []
    for i, (label, parts) in enumerate(planes):
        ops += [{"type": "group", "name": f"Tilt {i}", "targets": [f"Plate {i}", f"Label {i}"] + parts},
                {"type": "group", "name": f"Plane {i}", "targets": [f"Tilt {i}"]}]
    for i in range(len(planes)):  # draw order: plane 0 at the bottom, each plate under its own artwork
        ops += [{"type": "top", "target": f"Plane {i}"}, {"type": "bottom", "target": f"Plate {i}"}]
    p.apply(ops)
    spread = 150
    ops = []
    for i in range(len(planes)):
        drop = 260 + i * 330
        rest = (1.5 - i) * spread
        ops += [key(f"Tilt {i}", "rotation", 0, -38), key(f"Tilt {i}", "rotation", 2900, -38, "ease-in-out-cubic"),
                key(f"Tilt {i}", "rotation", 3700, 0),
                key(f"Plane {i}", "scale-y", 0, 0.52), key(f"Plane {i}", "scale-y", 2900, 0.52, "ease-in-out-cubic"),
                key(f"Plane {i}", "scale-y", 3700, 1),
                tween(f"Plane {i}", "translate-y", drop, 650, rest, rest - 700, "ease-out-back"),
                tween(f"Plane {i}", "opacity", drop, 200, 1, 0, "ease-out"),
                tween(f"Plane {i}", "translate-y", 2300, 600, 0, easing="ease-in-out-cubic"),
                tween(f"Plate {i}", "opacity", 3300, 400, 0, easing="ease-in"),
                tween(f"Label {i}", "opacity", 2300, 300, 0, easing="ease-in")]
    ops.append(tween("canvas", "background", 3000, 700, "#ffffff", "#e9edf4"))
    p.apply(ops)
    return finish(p)


# 11. Depixelate: the logo resolves out of a pixelate effect, from one giant block down to crisp vector.
def depixelate():
    p = stage(1200, 500, "#ffffff")
    fonts(p, MONO)
    p.apply([{"type": "group", "name": "Logo", "targets": LOGO_LAYERS},
             {"type": "effect", "target": "Logo", "name": "pixelate", "amount": 256},
             text("Readout", "pixelate 256", 1180, 462, 20, "#8a93a6", MONO, align="right")])
    readout = layer(p, "Readout")
    p.apply([{"type": "move", "target": "Readout", "x": 1180 - readout["width"] - 220, "y": 458}])
    steps = [256, 192, 128, 96, 64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1]
    ops = [appear("Logo", 0, 200)]
    t = 250
    for i, size in enumerate(steps):
        hold = 300 if i < 4 else 190
        ops.append(key("Logo", "effect:1", t, size, "hold"))
        label = f"pixelate {size} px" if size > 1 else "vector  1:1"
        ops.append(key("Readout", "text", t, label, "hold"))
        t += hold
    ops.append(key("Readout", "opacity", t + 300, 1, "ease-in"))
    ops.append(key("Readout", "opacity", t + 700, 0))
    ops.append(tween("Logo", "scale", t - 190, 380, 1, 1.04, "ease-out-back"))
    p.apply(ops)
    return finish(p)


# 12. Deep zoom: the view starts inside one loose pixel and pulls all the way out to the whole logo.
def ease_in_out_cubic(u):
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def deep_zoom():
    W, H = 1600, 900
    p = stage(W, H, "#ffffff")
    rng = random.Random(12)
    target = layer(p, "Upper pixel 3")
    px, py = target["x"] + target["width"] / 2, target["y"] + target["height"] / 2
    # Faint pixels in the background zoom out more slowly, which gives the pull-out some parallax.
    dust = []
    for i in range(70):
        size = rng.choice([8, 12, 16, 23])
        dust.append(rect(f"Dust {i}", round(rng.uniform(-200, W + 200)), round(rng.uniform(-150, H + 150)),
                         size, size, rng.choice(["#dfe5ef", "#cfd9f7", "#e6e8ec"])))
    p.apply(dust)
    p.apply([{"type": "group", "name": "Dust", "targets": [d["name"] for d in dust]},
             {"type": "bottom", "target": "Dust"},
             {"type": "pivot", "target": "Dust", "value": [W / 2, H / 2], "units": "canvas"}])
    # A camera zoom is capped at 16x and a layer at 16,384 px, so each logo layer is scaled on its own as if
    # about the pixel (capped below that size and the
    # 40-megapixel layer limit; a capped layer is far off screen by then). The scale is interpolated
    # in log space so the zoom speed feels even, while the pixel slides from the frame centre to its place.
    start, duration, zoom = 250, 2800, 60
    centres = {n: (layer(p, n)["x"] + layer(p, n)["width"] / 2, layer(p, n)["y"] + layer(p, n)["height"] / 2)
               for n in LOGO_LAYERS}
    caps = {n: min(16000 / max(layer(p, n)["width"], layer(p, n)["height"]),
                   math.sqrt(39e6 / (layer(p, n)["width"] * layer(p, n)["height"]))) for n in LOGO_LAYERS}
    frames = int(duration / (1000 / FPS) / 2)
    ops, shown = [], {}
    for f in range(frames + 1):
        u = f / frames
        e = ease_in_out_cubic(u)
        t = start + duration * u
        s = zoom ** (1 - e)
        for n in LOGO_LAYERS:
            cx, cy = centres[n]  # scaling about the pixel = scaling about the centre, then moving the centre
            dx = (s - 1) * (cx - px) + (W / 2 - px) * (1 - e)
            dy = (s - 1) * (cy - py) + (H / 2 - py) * (1 - e)
            w, h = layer(p, n)["width"] * s / 2, layer(p, n)["height"] * s / 2
            on_screen = cx + dx + w > 0 and cx + dx - w < W and cy + dy + h > 0 and cy + dy - h < H
            if on_screen != shown.get(n, True):  # off-screen layers are hidden so they are never rasterized
                ops.append(key(n, "opacity", t, 1 if on_screen else 0, "hold"))
                shown[n] = on_screen
            if not on_screen:
                continue
            ops += [key(n, "scale", t, round(min(s, caps[n]), 4)),
                    key(n, "translate-x", t, round(dx, 2)), key(n, "translate-y", t, round(dy, 2))]
        ops.append(key("Dust", "scale", t, round(s ** 0.3, 4)))
    ops += [tween("Dust", "opacity", 900, 900, 1, 0, "ease-out"),
            tween("Dust", "opacity", start + duration + 300, 700, 0, easing="ease-in-out"),
            {"type": "text-animate", "target": WORD, "preset": "wave", "unit": "char", "start": start + duration,
             "duration": 700, "stagger": 70}]
    p.apply(ops)
    return finish(p)


# 13. Stack: the V's are built from falling blocks, Tetris style, then snap to vector.
def tetris():
    p = stage(1200, 500, "#ffffff")
    rng = random.Random(13)
    step = 2 * CELL
    pieces = []
    for vname, fill in ((UPPER, CHARCOAL), (LOWER, BLUE)):
        item, poly = layer(p, vname), polygon(p, vname)
        cells = {}
        for row in range(round(item["height"] / step)):
            for col in range(round(item["width"] / step)):
                x, y = item["x"] + col * step, item["y"] + row * step
                if inside((x + step / 2, y + step / 2), poly):
                    cells[(row, col)] = (x, y)
        # Greedy tetromino-ish pieces: grow each piece to four connected cells, bottom rows first.
        free = sorted(cells, key=lambda rc: (-rc[0], rc[1]))
        taken = set()
        for seed in free:
            if seed in taken:
                continue
            piece, frontier = [seed], [seed]
            taken.add(seed)
            while frontier and len(piece) < 4:
                r, c = frontier.pop(0)
                options = [(r + dr, c + dc) for dr, dc in ((0, 1), (0, -1), (-1, 0), (1, 0))]
                rng.shuffle(options)
                for nb in options:
                    if nb in cells and nb not in taken and len(piece) < 4:
                        taken.add(nb)
                        piece.append(nb)
                        frontier.append(nb)
            pieces.append({"fill": fill, "cells": [cells[rc] for rc in piece]})
    pieces.sort(key=lambda pc: -max(y for _, y in pc["cells"]))
    ops, names = [], []
    for i, pc in enumerate(pieces):
        for j, (x, y) in enumerate(pc["cells"]):
            ops.append(rect(f"b{i}_{j}", round(x + 1.2, 2), round(y + 1.2, 2), step - 2.4, step - 2.4, pc["fill"],
                            radius=3))
    p.apply(ops)
    p.apply([{"type": "group", "name": f"Piece {i}", "targets": [f"b{i}_{j}" for j in range(len(pc["cells"]))]}
             for i, pc in enumerate(pieces)])
    p.apply([{"type": "top", "target": UPPER}, {"type": "top", "target": LOWER}])
    ops = []
    for i, pc in enumerate(pieces):
        t = i * 85
        top = min(y for _, y in pc["cells"])
        fall = top + step + 40
        ops.append(tween(f"Piece {i}", "translate-y", t, 260 + fall * 0.9, 0, -fall, "bounce-out"))
        names.append(f"Piece {i}")
    end = len(pieces) * 85 + 500
    for vname in (UPPER, LOWER):
        ops += [tween(vname, "opacity", end, 200, 1, 0, "ease-out")]
    ops += [tween(n, "opacity", end + 150, 200, 0, easing="ease-in") for n in names]
    ops.append({"type": "animate-preset", "targets": PIXELS, "preset": "pop-in", "start": end + 150,
                "duration": 300, "stagger": 60})
    ops.append({"type": "text-animate", "target": WORD, "preset": "fade-down", "unit": "char", "start": end + 300,
                "duration": 420, "stagger": 90, "easing": "bounce-out", "distance": 160})
    p.apply(ops)
    return finish(p)


# ---------------------------------------------------------------------------------------------------
# 08. Design app: a cursor builds the logo in an editor, with pen, fill, duplicate, rotate, rectangle and text.
APP_BG, PANEL, LINE, INK, DIM, SELECT = "#121419", "#1d2028", "#2a2e39", "#d5dae4", "#7b8496", "#4f8cff"


class Cursor:
    """Keyframes for the pointer: moves ease between stops, clicks flash a ring."""

    def __init__(self, x, y):
        self.x, self.y, self.t = x, y, 0
        self.ops = [key("Cursor", "translate-x", 0, x), key("Cursor", "translate-y", 0, y)]
        self.clicks = []

    def move(self, t, x, y, duration=380, easing="ease-in-out-cubic"):
        begin = max(self.t, t - duration)
        self.ops += [key("Cursor", "translate-x", begin, self.x, easing), key("Cursor", "translate-y", begin, self.y, easing),
                     key("Cursor", "translate-x", t, x), key("Cursor", "translate-y", t, y)]
        self.x, self.y, self.t = x, y, t

    def click(self, t=None):
        t = self.t if t is None else t
        self.clicks.append((t, self.x, self.y))

    def finish(self):
        ops = list(self.ops) + [key("Click", "opacity", 0, 0, "hold")]
        for t, x, y in self.clicks:
            ops += [key("Click", "translate-x", t, x - 18, "hold"), key("Click", "translate-y", t, y - 18, "hold"),
                    key("Click", "opacity", t, 0.95, "ease-out"), key("Click", "opacity", t + 320, 0, "hold"),
                    key("Click", "scale", t, 0.3, "ease-out"), key("Click", "scale", t + 320, 1.5, "hold")]
        return ops


def design_app():
    W, H = 1920, 1080
    p = stage(W, H, APP_BG, cx=822, cy=566)
    fonts(p, MONO, UI, UI_BOLD)
    up, lo = layer(p, UPPER), layer(p, LOWER)
    poly = polygon(p, UPPER)
    ops = [rect("Artboard", 172, 256, 1300, 620, "#ffffff"),
           text("Artboard label", "Logo  1200 x 500", 172, 222, 18, DIM, UI),
           # Chrome
           rect("Top bar", 0, 0, W, 52, PANEL), rect("Toolbar", 0, 52, 64, H - 52, PANEL),
           rect("Panel", 1580, 52, 340, H - 52, PANEL), rect("Top line", 0, 52, W, 1, LINE),
           rect("Panel line", 1580, 52, 1, H - 52, LINE), rect("Tool line", 64, 52, 1, H - 52, LINE)]
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        ops.append({"type": "shape", "shape": "ellipse", "name": f"Dot {i}", "x": 20 + i * 22, "y": 19, "width": 14,
                    "height": 14, "fill": color})
    ops += [text("Title", "logo.vixl", 900, 15, 17, INK, UI),
            rect("Export button", 1790, 10, 110, 32, BLUE, radius=8),
            text("Export label", "Export", 1817, 16, 16, "#ffffff", UI_BOLD),
            rect("Tool highlight", 10, 58, 44, 44, "#2c3240", radius=8),
            {"type": "shape", "shape": "path", "name": "Tool move", "x": 25, "y": 69,
             "path": "M0 0 L0 20 L5 15 L9 23 L12 22 L8 14 L15 14 Z", "fill": INK},
            rect("Tool rect", 22, 130, 20, 20, "none", stroke=INK, stroke_width=2),
            {"type": "shape", "shape": "path", "name": "Tool pen", "x": 21, "y": 189, "path": "M1 21 C 4 0, 18 0, 21 21",
             "fill": "none", "stroke": INK, "stroke_width": 2},
            text("Tool text", "T", 23, 243, 26, INK, UI_BOLD),
            text("Layers title", "Layers", 1600, 70, 16, "#eef1f6", UI_BOLD),
            rect("Row highlight", 1588, 100, 316, 34, "#263252", radius=6, opacity=0),
            text("Fill title", "Fill", 1600, 330, 16, "#eef1f6", UI_BOLD),
            text("Hex", "-", 1736, 368, 16, INK, MONO),
            text("Transform title", "Transform", 1600, 430, 16, "#eef1f6", UI_BOLD),
            text("Readout 1", "X -    Y -", 1600, 466, 16, INK, MONO),
            text("Readout 2", "W -    H -", 1600, 496, 16, INK, MONO),
            text("Readout 3", "R 0", 1600, 526, 16, INK, MONO)]
    swatches = {"charcoal": (1604, CHARCOAL), "blue": (1646, BLUE), "white": (1688, "#ffffff")}
    for name, (x, color) in swatches.items():
        ops.append({"type": "shape", "shape": "ellipse", "name": f"Swatch {name}", "x": x, "y": 362, "width": 30,
                    "height": 30, "fill": color, "stroke": "#3a4050", "stroke_width": 2})
    rows = ["Downward V", "Upward V", "Pixels x6", "Vixl"]
    for i, label in enumerate(rows):
        y = 106 + i * 40
        ops += [rect(f"Row swatch {i}", 1604, y + 3, 16, 16, BLUE if i == 1 else CHARCOAL, radius=3, stroke="#59617a",
                     stroke_width=1.5),
                text(f"Row {i}", label, 1632, y, 16, INK, UI)]
    # The pen outline, its anchor points, and the selection box.
    ops += [{"type": "shape", "shape": "path", "name": "Pen outline", "x": up["x"], "y": up["y"], "width": up["width"],
             "height": up["height"], "path": up["path"], "fill": "none", "stroke": SELECT, "stroke_width": 2.5,
             "trim_end": 0}]
    for i, (x, y) in enumerate(poly):
        ops.append(rect(f"Node {i}", round(x - 5, 1), round(y - 5, 1), 10, 10, "#ffffff", stroke=SELECT,
                        stroke_width=2))
    ops += [rect("Selection", 0, 0, 10, 10, "none", stroke=SELECT, stroke_width=2, opacity=0),
            text("Size tag", "-", 0, 0, 15, SELECT, MONO, opacity=0),
            text("Toast", "Duplicate   Ctrl+D", 760, 960, 18, INK, UI),
            text("Export toast", "Exported  logo.svg   logo.png   logo.pdf", 640, 960, 18, "#9fe3b0", UI),
            {"type": "shape", "shape": "ellipse", "name": "Click", "x": 0, "y": 0, "width": 36, "height": 36,
             "fill": "none", "stroke": SELECT, "stroke_width": 3},
            {"type": "shape", "shape": "path", "name": "Cursor", "x": 0, "y": 0,
             "path": "M0 0 L0 30 L8 23 L14 36 L19 34 L13 21 L23 21 Z", "fill": "#ffffff", "stroke": "#000000",
             "stroke_width": 1.5}]
    p.apply(ops)
    p.apply([{"type": "bottom", "target": "Artboard"}])
    hidden = [f"Row {i}" for i in range(4)] + [f"Row swatch {i}" for i in range(4)] + PIXELS + [UPPER, LOWER, WORD]
    hidden += [f"Node {i}" for i in range(len(poly))] + ["Toast", "Export toast"]
    hidden += ["Selection", "Size tag", "Row highlight"]
    ops = [key(n, "opacity", 0, 0, "hold") for n in hidden]
    c = Cursor(980, 760)
    tool_y = {"move": 58, "rect": 118, "pen": 178, "text": 238}

    def tool(t, name):
        c.move(t, 32, tool_y[name] + 24)
        c.click()
        ops.append(key("Tool highlight", "translate-y", t - 1, ops_tool[-1], "hold"))
        ops.append(key("Tool highlight", "translate-y", t, tool_y[name] - 58, "hold"))
        ops_tool.append(tool_y[name] - 58)

    ops_tool = [0]

    def select(t, box, label=None, easing="hold"):
        x, y, w, h = box
        for prop, value in (("x", x - 4), ("y", y - 4), ("width", w + 8), ("height", h + 8)):
            ops.append(key("Selection", prop, t, round(value, 1), easing))
        ops.extend([key("Size tag", "x", t, round(x, 1), easing), key("Size tag", "y", t, round(y + h + 12, 1), easing)])
        if label:
            ops.append(key("Size tag", "text", t, label, "hold"))

    def readout(t, x, y, w, h, r=0, hexval=None):
        x, y = x - (up["x"] - 108), y - (up["y"] - 75)  # artboard coordinates, as in the master
        ops.extend([key("Readout 1", "text", t, f"X {x:<6.0f} Y {y:.0f}", "hold"),
                key("Readout 2", "text", t, f"W {w:<6.0f} H {h:.0f}", "hold"),
                key("Readout 3", "text", t, f"R {r:.0f}", "hold")])
        if hexval:
            ops.append(key("Hex", "text", t, hexval, "hold"))

    def row(t, i):
        ops.extend([key(f"Row {i}", "opacity", t, 1, "hold"), key(f"Row swatch {i}", "opacity", t, 1, "hold"),
                key("Row highlight", "opacity", t, 1, "hold"), key("Row highlight", "translate-y", t, i * 40, "hold")])

    # 1. Pen tool: click each anchor of the upper V; the outline follows the cursor.
    tool(600, "pen")
    lengths = [math.dist(a, b) for a, b in zip(poly, poly[1:] + poly[:1])]
    total = sum(lengths)
    t, run = 1000, 0.0
    ops.append(key("Pen outline", "trim_end", t, 0))
    for i, (x, y) in enumerate(poly + poly[:1]):
        if i:
            run += lengths[i - 1]
            t += 70 + lengths[i - 1] * 0.55
        c.move(int(t), x, y, duration=int(70 + (lengths[i - 1] if i else 300) * 0.55), easing="linear" if i else "ease-in-out-cubic")
        c.click()
        ops.append(key("Pen outline", "trim_end", int(t), round(100 * run / total, 2)))
        if i < len(poly):
            ops.append(key(f"Node {i}", "opacity", int(t), 1, "hold"))
    closed = int(t)
    row(closed, 0)
    box_up = (up["x"], up["y"], up["width"], up["height"])
    select(closed + 120, box_up, "288 x 173")
    readout(closed + 120, up["x"], up["y"], up["width"], up["height"], hexval="none")
    ops.append(key("Selection", "opacity", closed + 120, 1, "hold"))
    ops.append(key("Size tag", "opacity", closed + 120, 1, "hold"))
    # 2. Fill it charcoal from the swatch.
    t = closed + 700
    c.move(t, 1619, 377)
    c.click()
    ops += [tween(UPPER, "opacity", t, 220, 1, 0, "ease-out"), tween("Pen outline", "opacity", t, 220, 0)]
    ops += [key(f"Node {i}", "opacity", t + 120, 0, "hold") for i in range(len(poly))]
    ops.append(key("Hex", "text", t, "#252B39", "hold"))
    # 3. Duplicate (the lower V is the upper V turned 180 degrees), rotate it, drag it into place.
    t += 500
    c.move(t, up["x"] + 150, up["y"] + 60)
    dup = t + 250
    off_x, off_y = up["x"] - lo["x"] + 46, up["y"] - lo["y"] + 46
    ops += [key("Toast", "opacity", dup, 1, "hold"), key("Toast", "opacity", dup + 900, 0, "hold"),
            key(LOWER, "opacity", dup, 1, "hold"), key(LOWER, "translate-x", dup, off_x, "hold"),
            key(LOWER, "translate-y", dup, off_y, "hold"), key(LOWER, "rotation", dup, 180, "hold"),
            key(LOWER, "fill", dup, CHARCOAL, "hold")]
    row(dup, 1)
    ops.append(key("Row swatch 1", "fill", dup, CHARCOAL, "hold"))
    copy_box = (lo["x"] + off_x, lo["y"] + off_y, lo["width"], lo["height"])
    select(dup, copy_box, "288 x 173")
    readout(dup, copy_box[0], copy_box[1], lo["width"], lo["height"], 0)
    # Rotate: grab outside the top-right corner and swing round.
    t = dup + 350
    cx, cy = copy_box[0] + lo["width"] / 2, copy_box[1] + lo["height"] / 2
    radius = 190
    c.move(t, cx + radius * math.cos(-0.6), cy + radius * math.sin(-0.6), duration=300)
    ops += [key("Selection", "opacity", t, 0, "hold"), key("Size tag", "opacity", t, 0, "hold")]
    spin = 900
    for k in range(1, 13):
        u = k / 12
        e = ease_in_out_cubic(u)
        a = -0.6 - math.pi * e
        tk = int(t + spin * u)
        c.move(tk, round(cx + radius * math.cos(a), 1), round(cy + radius * math.sin(a), 1), duration=int(spin / 12),
               easing="linear")
        ops.append(key("Readout 3", "text", tk, f"R {round(180 * (1 - e))}", "hold"))
    ops += [key(LOWER, "rotation", t, 180, "ease-in-out-cubic"), key(LOWER, "rotation", t + spin, 0)]
    t += spin
    select(t + 1, copy_box)
    ops += [key("Selection", "opacity", t + 1, 1, "hold"), key("Size tag", "opacity", t + 1, 1, "hold")]
    # Drag into place.
    t += 300
    c.move(t, cx, cy)
    drag = 700
    ops += [key(LOWER, "translate-x", t, off_x, "ease-in-out-cubic"), key(LOWER, "translate-x", t + drag, 0),
            key(LOWER, "translate-y", t, off_y, "ease-in-out-cubic"), key(LOWER, "translate-y", t + drag, 0)]
    select(t, copy_box, easing="ease-in-out-cubic")
    box_lo = (lo["x"], lo["y"], lo["width"], lo["height"])
    select(t + drag, box_lo)
    c.move(t + drag, cx - off_x, cy - off_y, duration=drag)
    readout(t + drag, lo["x"], lo["y"], lo["width"], lo["height"])
    # Fill blue.
    t += drag + 600
    c.move(t, 1661, 377)
    c.click()
    ops += [key(LOWER, "fill", t, CHARCOAL, "ease-out"), key(LOWER, "fill", t + 220, BLUE),
            key("Row swatch 1", "fill", t, BLUE, "hold"), key("Hex", "text", t, "#3575EE", "hold")]
    # 4. Rectangle tool: drag out the six loose pixels.
    t += 500
    tool(t, "rect")
    ops.append(key("Hex", "text", t, "#252B39", "hold"))
    for i, name in enumerate(UPPER_PIXELS + LOWER_PIXELS):
        px = layer(p, name)
        ops.append({"type": "pivot", "target": name, "value": "top-left"})
        t += 380
        c.move(t, px["x"], px["y"], duration=300)
        ops += [key(name, "opacity", t, 1, "hold"), key(name, "scale", t, 0.05, "ease-out-cubic"),
                key(name, "scale", t + 160, 1)]
        c.move(t + 160, px["x"] + px["width"], px["y"] + px["height"], duration=160, easing="ease-out-cubic")
        select(t, (px["x"], px["y"], px["width"], px["height"]), f'{px["width"]} x {px["height"]}')
        readout(t, px["x"], px["y"], px["width"], px["height"], hexval="#3575EE" if name in LOWER_PIXELS else None)
        if i == 0:
            row(t, 2)
    # 5. Text tool: click and type the name.
    t += 600
    tool(t, "text")
    word = layer(p, WORD)
    t += 500
    c.move(t, word["x"] + 6, word["y"] + 40)
    c.click()
    ops.append(key("Selection", "opacity", t, 0, "hold"))
    ops.append(key("Size tag", "opacity", t, 0, "hold"))
    ops.append(key(WORD, "opacity", t, 1, "hold"))
    row(t + 100, 3)
    readout(t + 100, word["x"], word["y"], word["width"], word["height"], hexval="#252B39")
    ops.append({"type": "text-animate", "target": WORD, "preset": "typewriter", "unit": "char", "start": t + 150,
                "duration": 600})
    c.move(t + 800, word["x"] + word["width"] + 60, word["y"] + word["height"] + 30, duration=500)
    # 6. Export.
    t += 1500
    tool(t - 600, "move")
    c.move(t, 1845, 30, duration=700)
    c.click()
    ops += [key("Export button", "fill", t, "#6a9aff", "ease-out"), key("Export button", "fill", t + 250, BLUE),
            key("Export toast", "opacity", t + 200, 0, "ease-out"), key("Export toast", "opacity", t + 400, 1),
            key("Export toast", "translate-y", t + 200, 30, "ease-out-back"), key("Export toast", "translate-y", t + 500, 0),
            key("Row highlight", "opacity", t, 0, "hold")]
    ops += c.finish()
    p.apply(ops)
    return finish(p)


# ---------------------------------------------------------------------------------------------------
# 09. Terminal: the logo rebuilt with real vixl CLI commands, each one showing up in a preview window.
# Every command below was run as shown and rebuilds the master (outputs condensed from the JSON).
SESSION = [
    ("vixl new 1200x500 --purpose logo --out logo.vixl", ["created logo.vixl  1200 x 500"], "new"),
    ('vixl shape path --name "Downward V" --x 108 --y 75 \\\n'
     '    --path "M0 0 L68.4 0 L144 104.4 L216 0 L259.2 0 ... Z" \\\n'
     '    --fill "#252b39"', ["+ Downward V  288 x 172.8"], "upper"),
    ('vixl duplicate "Downward V" "Upward V"', ["+ Upward V"], "duplicate"),
    ('vixl rotate "Upward V" 180', [], "rotate"),
    ('vixl shape --target "Upward V" --fill "#3575ee"', [], "blue"),
    ('vixl move "Upward V" --x 142.2 --y 233.4', [], "move"),
    ('vixl shape rectangle --width 23 --height 23 \\\n    --x 401.4 --y 75 --fill "#252b39"   # + 5 more',
     ["+ 6 shapes"], "pixels"),
    ('vixl font install "Inter Tight" --weight 800', ["installed inter-tight-800"], "font"),
    ('vixl text add Vixl --font inter-tight-800 --size 240 \\\n    --x 550 --y 155 --color "#252b39"',
     ["+ text  ink 423 x 186"], "text"),
    ("vixl export --out logo.svg", ["wrote logo.svg  3,787 bytes, vector only"], "export"),
]


def terminal():
    W, H = 1920, 1080
    p = stage(W, H, "#0d0f14", cx=1462, cy=540)
    fonts(p, MONO, UI)
    p.apply([{"type": "group", "name": "Logo", "targets": LOGO_LAYERS},
             {"type": "scale", "target": "Logo", "value": 0.85, "anchor": "center"}])
    term = (40, 60, 990, 960)
    card = (1040, 270, 844, 540)
    size, lead = 19, 33
    char = size * 0.6  # JetBrains Mono advance
    x0, y0 = term[0] + 34, term[1] + 70
    ops = [rect("Terminal", *term, "#161a22", radius=14, stroke="#262b36", stroke_width=2),
           rect("Terminal bar", term[0], term[1], term[2], 44, "#1d222c", radius=14),
           rect("Terminal bar edge", term[0], term[1] + 30, term[2], 14, "#1d222c"),
           text("Terminal title", "zsh  ~/brand", term[0] + term[2] / 2 - 60, term[1] + 11, 17, DIM, UI),
           rect("Card", *card, "#ffffff", radius=12),
           rect("Card bar", card[0], card[1] - 40, card[2], 52, "#232835", radius=12),
           text("Card title", "logo.vixl  preview", card[0] + 20, card[1] - 30, 17, DIM, UI),
           rect("Badge", card[0] + card[2] / 2 - 150, card[1] + card[3] + 40, 300, 52, "#1f3a2a", radius=26,
                stroke="#3c7a52", stroke_width=2),
           text("Badge label", "logo.svg   3.8 KB", card[0] + card[2] / 2 - 17 * 20 * 0.6 / 2, card[1] + card[3] + 52, 20,
                "#9fe3b0", MONO)]
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        ops.append({"type": "shape", "shape": "ellipse", "name": f"TDot {i}", "x": term[0] + 18 + i * 22,
                    "y": term[1] + 15, "width": 14, "height": 14, "fill": color})
    lines = []  # (name, x, y, full text, kind)
    row = 0
    for n, (command, outputs, _) in enumerate(SESSION):
        for k, part in enumerate(command.split("\n")):
            lines.append((f"Cmd {n}.{k}", x0 + 2 * char, y0 + row * lead, part, n))
            if k == 0:
                ops.append(text(f"Prompt {n}", "$", x0, y0 + row * lead, size, "#7ee0a3", MONO))
            row += 1
        for k, out in enumerate(outputs):
            lines.append((f"Out {n}.{k}", x0 + 2 * char, y0 + row * lead, out, "out"))
            row += 1
    ops.append(text("Prompt end", "$", x0, y0 + row * lead, size, "#7ee0a3", MONO))
    for name, x, y, full, kind in lines:
        ops.append(text(name, full, x, y, size, "#8fa0b8" if kind == "out" else "#e6e9ef", MONO))
    ops.append(rect("Caret", x0 + 2 * char, y0, char, size + 6, "#e6e9ef", opacity=0.85))
    p.apply(ops)
    for name in ("Card title", "Card", "Card bar"):
        p.apply([{"type": "bottom", "target": name}])
    p.apply([{"type": "top", "target": "Logo"}, {"type": "top", "target": "Caret"}])
    hidden = [name for name, *_ in lines] + [f"Prompt {n}" for n in range(len(SESSION))] + ["Prompt end"]
    hidden += ["Card", "Card bar", "Card title", "Badge", "Badge label"] + LOGO_LAYERS
    ops = [key(n, "opacity", 0, 0, "hold") for n in hidden]
    up, lo = layer(p, UPPER), layer(p, LOWER)
    off = (up["x"] - lo["x"], up["y"] - lo["y"])
    t = 500
    caret = [(0, x0 + 2 * char, y0)]
    for n, (command, outputs, effect) in enumerate(SESSION):
        ops.append(key(f"Prompt {n}", "opacity", t - 200, 1, "hold"))
        for name, x, y, full, kind in [ln for ln in lines if ln[4] == n]:
            ops.append(key(name, "opacity", t, 1, "hold"))
            for k in range(1, len(full) + 1, 3):
                ops.append(key(name, "text", t, full[:k], "hold"))
                caret.append((t, x + k * char, y))
                t += 26
            ops.append(key(name, "text", t, full, "hold"))
            caret.append((t, x + len(full) * char, y))
        t += 250  # the enter key
        outs = [ln for ln in lines if ln[0].startswith(f"Out {n}.")]
        for name, x, y, *_ in outs:
            ops.append(key(name, "opacity", t, 1, "hold"))
        if outs:
            caret.append((t, outs[-1][1], outs[-1][2] + lead))
        # What the command does, in the preview.
        if effect == "new":
            ops += [tween(nm, "opacity", t, 300, 1, 0, "ease-out") for nm in ("Card", "Card bar", "Card title")]
            ops += [tween(nm, "translate-y", t, 400, 0, 30, "ease-out-back") for nm in ("Card", "Card bar", "Card title")]
        elif effect == "upper":
            ops += [tween(UPPER, "opacity", t, 200, 1, 0, "ease-out"),
                    tween(UPPER, "scale", t, 350, 1, 0.6, "ease-out-back")]
        elif effect == "duplicate":
            ops += [key(LOWER, "opacity", t, 1, "hold"), key(LOWER, "translate-x", 0, off[0], "hold"),
                    key(LOWER, "translate-y", 0, off[1], "hold"), key(LOWER, "rotation", 0, 180, "hold"),
                    key(LOWER, "fill", 0, CHARCOAL, "hold"), tween(LOWER, "scale", t, 300, 1, 1.08, "ease-out-back")]
        elif effect == "rotate":
            ops += [key(LOWER, "rotation", t, 180, "ease-in-out-cubic"), key(LOWER, "rotation", t + 500, 0)]
        elif effect == "blue":
            ops += [key(LOWER, "fill", t, CHARCOAL, "ease-out"), key(LOWER, "fill", t + 250, BLUE)]
        elif effect == "move":
            ops += [key(LOWER, "translate-x", t, off[0], "ease-in-out-cubic"), key(LOWER, "translate-x", t + 450, 0),
                    key(LOWER, "translate-y", t, off[1], "ease-in-out-cubic"), key(LOWER, "translate-y", t + 450, 0)]
        elif effect == "pixels":
            ops.append({"type": "animate-preset", "targets": PIXELS, "preset": "pop-in", "start": t,
                        "duration": 300, "stagger": 70})
        elif effect == "text":
            ops += [key(WORD, "opacity", t, 1, "hold"),
                    {"type": "text-animate", "target": WORD, "preset": "fade-up", "unit": "char", "start": t,
                     "duration": 350, "stagger": 60}]
        elif effect == "export":
            ops += [key("Card", "fill", 0, "#ffffff", "hold"), key("Card", "fill", t, "#dfe9ff", "ease-out"),
                    key("Card", "fill", t + 300, "#ffffff"),
                    tween("Badge", "opacity", t + 150, 250, 1, 0, "ease-out"),
                    tween("Badge label", "opacity", t + 150, 250, 1, 0, "ease-out"),
                    tween("Badge", "translate-y", t + 150, 400, 0, -40, "ease-out-back"),
                    tween("Badge label", "translate-y", t + 150, 400, 0, -40, "ease-out-back")]
        t += 450
    ops.append(key("Prompt end", "opacity", t - 300, 1, "hold"))
    caret.append((t - 300, x0 + 2 * char, y0 + row * lead))
    for tk, x, y in caret:
        ops += [key("Caret", "translate-x", tk, round(x - x0 - 2 * char, 1), "hold"),
                key("Caret", "translate-y", tk, round(y - y0 + 2, 1), "hold")]
    # Blink while idle at the end.
    for b in range(4):
        ops += [key("Caret", "opacity", t + b * 500, 0.85, "hold"), key("Caret", "opacity", t + b * 500 + 250, 0, "hold")]
    ops.append(key("Caret", "opacity", t + 2000, 0.85, "hold"))
    p.apply(ops)
    return finish(p)


MORE = {
    "09-terminal": terminal,
    "08-design-app": design_app,
    "10-layer-stack": layer_stack,
    "11-depixelate": depixelate,
    "12-deep-zoom": deep_zoom,
    "13-block-stack": tetris,
}
