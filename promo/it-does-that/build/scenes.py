"""The eleven shots of "It does that?". Each function returns a ``Scene``; times are milliseconds.

The score runs at 120 BPM (a beat is 500 ms) and most entrances land on a beat. Shots 2-10 each run a
real Vixl feature inside the scene: the art on screen is the output of that feature, not a picture of it.
"""
from __future__ import annotations

import math
import re

import assets
import score
from film import (BAD, BLUE, BODY, CODE_KEY, CODE_NUM, CODE_STR, CORAL, DEEP, GOLD, GOOD, HEAD, INK, LILAC, LINE,
                  MINT, MONO, MUTED, PANEL, PAPER, SEMI, SKY, WHITE, Scene, backdrop, caption, centered, chip,
                  ellipse, exit_all, glow, group, headline, image, kicker, mark, rect, rel, rich, shadow, text)

DURATIONS = {"01-hook": 5000, "02-sketch": 6000, "03-badges": 6000, "04-emoji": 5000, "05-mandala": 5000,
             "06-pixel": 5000, "07-forms": 5000, "08-diagram": 5000, "09-garden": 5000, "10-score": 6000,
             "11-end": 4500}


def cuts():
    out, t = [], 0
    for ms in DURATIONS.values():
        out.append(t)
        t += ms
    return out, t


def code_lines(prefix, lines, x, y, size=28, gap=1.5, t=0, stagger=140):
    """Syntax-coloured lines ([(text, colour), ...] each) that type in one after another."""
    ops, names = [], []
    for i, spans in enumerate(lines):
        name = f"{prefix}{i}"
        ops.append(rich(name, spans, x, y + i * size * gap, size, 1200, WHITE, MONO, line_height=1.2))
        names.append(name)
    return ops, names, [(n, t + i * stagger) for i, n in enumerate(names)]


def panel(name, x, y, w, h, fill=DEEP):
    return [rect(name, x, y, w, h, fill, 22, LINE, 2), shadow(name, 40, 18, 0.4)]


def bye(sc, names, t):
    exit_all(sc, list(names), t)


# ----------------------------------------------------------------------------------------------- 1
def s01_hook():
    sc = Scene("01-hook", DURATIONS["01-hook"])
    sc.add(backdrop(glow_at=(1500, 250)))
    sc.add(rich("l1", "You know Vixl makes posters.", 160, 290, 96, 1600, WHITE, HEAD))
    sc.words("l1", 200, "fade-up", "word", 500, 90)
    sc.add(rich("l2", "And slides. And logos. And social cards.", 160, 420, 52, 1600, MUTED, SEMI))
    sc.words("l2", 1100, "fade-up", "word", 450, 80)
    for name in ("l1", "l2"):
        sc.keys(name, "opacity", [(2300, 1), (2800, 0.25)], "ease-in-out")
    sc.add(rich("l3", "Here are nine things", 160, 600, 120, 1600, WHITE, HEAD))
    sc.words("l3", 2500, "fade-up", "word", 450, 90)
    sc.add(rich("l4", "you might not expect.", 160, 740, 120, 1600, SKY, HEAD))
    sc.words("l4", 3100, "pop", "word", 450, 120)
    names = ["l1", "l2", "l3", "l4"]
    for name in names:
        sc.keys(name, "translate-x", [(0, 0), (4400, 0), (4950, -160)], "ease-in-cubic")
    exit_all(sc, ["l1", "l2"], 4450, start=0.25)
    bye(sc, ["l3", "l4"], 4450)
    return sc


# ----------------------------------------------------------------------------------------------- 2
def s02_sketch():
    sc = Scene("02-sketch", DURATIONS["02-sketch"])
    paths, report = assets.sketch()
    sc.add(backdrop(glow_at=(1500, 700)))
    kicker(sc, "01", "SKETCH → VECTORS")
    headline(sc, [("Photograph a sketch. ", None), ("Get clean, editable vectors.", SKY)])
    steps = [("photo", "photo of the sketch"), ("cleaned", "drawing import · vectorize"),
             ("finished", "straighten · fill · stroke")]
    names = []
    for i, (key, label) in enumerate(steps):
        x, y, w, h = 120 + i * 580, 340, 520, 390
        sc.add(image(f"p-{key}", rel(paths[key]), x, y, w, h, 18, "fit", PAPER), shadow(f"p-{key}-base", 40, 18, 0.45))
        t = 500 + i * 1000
        sc.pop(f"p-{key}", t, 520, 0.85)
        caption(sc, f"c-{key}", f"{i + 1}  {label}", x + 4, y + h + 26, t + 250, 24, SKY if i == 2 else MUTED)
        names += [f"p-{key}", f"c-{key}"]
        if i:
            sc.add(text(f"arrow{i}", "→", x - 52, y + h / 2 - 34, 56, SKY, HEAD))
            sc.fade(f"arrow{i}", t - 200, dur=300)
            names.append(f"arrow{i}")
    kept = f"{report['preserved']:.0%}".replace("%", " %")
    stat = f"{kept} of the original lines kept  ·  {report['strokes']} editable strokes  ·  " \
           f"tilt corrected {abs(report['tilt_corrected']):g}°"
    sc.add(chip("stat", stat, 120, 880, size=28, fg=WHITE, bg="#3575EE40", font=SEMI))
    sc.pop("stat", 3600, 450, 0.9)
    bye(sc, names + ["stat", "headline", "kicker"], 5450)
    return sc


# ----------------------------------------------------------------------------------------------- 3
def s03_badges():
    sc = Scene("03-badges", DURATIONS["03-badges"])
    run = assets.badges()
    sc.add(backdrop(glow_at=(1500, 600), glow2_at=(300, 300)))
    kicker(sc, "02", "SPREADSHEET → PRINT RUN")
    headline(sc, [("A CSV in, a print run out. ", None), ("Every QR code unique.", SKY)])
    sc.add(panel("csv-panel", 120, 330, 820, 440))
    sc.add(text("csv-title", "people.csv", 150, 352, 22, MUTED, MONO))
    rows = [[(",".join(run["csv"][0]), CODE_KEY)]]
    rows += [[(r[0], CODE_NUM), (",", WHITE), (r[1], CODE_STR), (",", WHITE), (r[2], WHITE)] for r in run["csv"][1:]]
    rows.append([(f"… {run['rows'] - len(run['csv']) + 1} more rows", MUTED)])
    ops, names, times = code_lines("row", rows, 150, 400, 26, 1.55, 400, 130)
    sc.add(ops)
    for n, t in times:
        sc.fade(n, t, dur=250)
    sc.fade("csv-panel", 0, dur=300)
    sc.fade("csv-title", 100, dur=300)
    sc.add(text("cmd", "$ vixl merge badge.vixl --data people.csv --out badges.pdf", 120, 800, 23, WHITE, MONO))
    sc.words("cmd", 1500, "typewriter", "char", 900)
    # Three imposed letter sheets, rendered from the sheet document the merge wrote.
    sw, sh = 520, 673
    layout = [(3, 1330, 330, 7), (2, 1300, 345, -5), (1, 1250, 350, 0)]
    for i, (page, x, y, rot) in enumerate(layout):
        key = f"sheet{page}"
        sc.add(image(key, rel(run["sheets"][page - 1]), x, y, sw, sh, 6, "fit", "#FFFFFF"),
               shadow(f"{key}-base", 50, 22, 0.55))
        t = 2100 + i * 220
        sc.pop(key, t, 560, 0.7)
        sc.keys(key, "rotation", [(0, rot * 2), (t, rot * 2), (t + 700, rot)], "ease-out-cubic")
        sc.keys(key, "translate-y", [(0, 120), (t, 120), (t + 700, 0)], "ease-out-expo")
    sc.keys("sheet1", "scale", [(3200, 1), (4600, 1.06)], "ease-in-out")
    stat = f"{run['rows']} rows  ·  {run['valid']} valid  ·  {run['pages']} sheets  ·  crop marks  ·  " \
           f"{run['errors']} errors"
    sc.add(chip("stat", stat, 120, 880, size=26, fg=WHITE, bg="#3575EE40", font=SEMI))
    sc.pop("stat", 3500, 450, 0.9)
    everything = ["csv-panel", "csv-title", "cmd", "stat", "headline", "kicker", "sheet1", "sheet2", "sheet3"] + names
    bye(sc, everything, 5450)
    return sc


# ----------------------------------------------------------------------------------------------- 4
def scale_path(path, s, dx=0.0, dy=0.0):
    """Scale an absolute SVG path (M L H V C Q Z) by ``s``; H takes x, V takes y."""
    out, axis = [], None
    for token in re.findall(r"[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?", path):
        if token.isalpha():
            out.append(token)
            axis = "x" if token == "H" else "y" if token == "V" else "xy"
            pair = 0
            continue
        v = float(token) * s
        if axis == "x":
            v += dx
        elif axis == "y":
            v += dy
        else:
            v += dx if pair % 2 == 0 else dy
            pair += 1
        out.append(f"{v:.2f}")
    return " ".join(out)


def centroid(path):
    nums = [float(n) for n in re.findall(r"-?\d*\.?\d+", path)]
    xs, ys = nums[0::2], nums[1::2]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def s04_emoji():
    from vixl import Project

    sc = Scene("04-emoji", DURATIONS["04-emoji"])
    path, entry, count = assets.emoji()
    sc.add(backdrop(glow_at=(1350, 620), glow2_at=(200, 900)))
    kicker(sc, "03", "EMOJI, TAKEN APART")
    headline(sc, [(f"{count:,} emoji. ", None), ("Every one an editable, layered master.", SKY)])
    layers = Project.load(path).state["layers"]
    s, ox, oy = 7.0, 1080, 330
    sc.add(glow("halo", ox + 36 * s, oy + 36 * s, 900, SKY, "38"))
    sc.pop("halo", 300, 700, 0.5)
    names, list_names = [], []
    recolor = {"#dc7366": LILAC, "#a3cfdc": MINT, "#69a9bd": "#2FA58A"}
    sc.add(panel("layers-panel", 120, 330, 560, 640))
    sc.add(text("layers-title", f"{entry['emoji']}  {entry['name']}  ·  {len(layers)} layers", 150, 352, 24, MUTED, MONO))
    sc.fade("layers-panel", 900, dur=300)
    sc.fade("layers-title", 950, dur=300)
    for i, layer in enumerate(layers):
        name = f"u-{layer['name']}"
        op = {"type": "shape", "shape": "path", "name": name, "x": 0, "y": 0, "width": round(72 * s + ox),
              "height": round(72 * s + oy), "path": scale_path(layer["path"], s, ox, oy),
              "fill": layer["fill"], "stroke": layer["stroke"], "stroke_width": round(layer["stroke_width"] * s, 2)}
        for key in ("line_cap", "line_join"):
            if key in layer:
                op[key] = layer[key]
        sc.add(op)
        names.append(name)
        cx, cy = centroid(layer["path"])
        # Exploded view: every layer moves the same distance out from the middle, along its own direction.
        vx, vy = cx - 36, cy - 36
        if math.hypot(vx, vy) < 3:
            vx, vy = math.cos(i * 2.4), math.sin(i * 2.4)
        dist = 150 + (i % 3) * 40
        dx, dy = vx / math.hypot(vx, vy) * dist, vy / math.hypot(vx, vy) * dist
        t0, t1, t2, t3 = 1200, 1900, 2700, 3300
        sc.keys(name, "translate-x", [(0, 0), (t0, 0), (t1, dx), (t2, dx), (t3, 0)], "ease-in-out-cubic")
        sc.keys(name, "translate-y", [(0, 0), (t0, 0), (t1, dy), (t2, dy), (t3, 0)], "ease-in-out-cubic")
        sc.keys(name, "rotation", [(0, 0), (t0, 0), (t1, (i % 5 - 2) * 6), (t2, (i % 5 - 2) * 6), (t3, 0)],
                "ease-in-out-cubic")
        colour = layer["fill"] if layer["fill"] != "transparent" else layer["stroke"]
        if layer["fill"] in recolor:
            sc.keys(name, "fill", [(0, layer["fill"]), (3500, layer["fill"]), (3900, recolor[layer["fill"]])],
                    "ease-in-out")
        # The layer list on the left, one row per layer with its swatch.
        row_y = 400 + i * 46
        sw = f"sw{i}"
        sc.add(rect(sw, 150, row_y + 6, 26, 26, colour, 6, "#FFFFFF33", 1))
        if layer["fill"] in recolor:
            sc.keys(sw, "fill", [(0, colour), (3500, colour), (3900, recolor[layer["fill"]])], "ease-in-out")
        kind = "fill  " if layer["fill"] != "transparent" else "stroke"
        sc.add(text(f"ln{i}", f"{layer['name']}   {kind}", 196, row_y + 4, 24, WHITE, MONO))
        for n in (sw, f"ln{i}"):
            sc.fade(n, 1100 + i * 60, dur=250)
        list_names += [sw, f"ln{i}"]
    sc.add(group("unicorn", names))
    sc.pop("unicorn", 200, 650, 0.6)
    sc.add(chip("recolor", "recolor: 3 swatches", 1180, 900, size=24, fg=WHITE, bg="#3575EE40", font=MONO))
    sc.pop("recolor", 3600, 400, 0.9)
    credit = f"Unicorn by {entry['author']} · {entry['source']} · {entry['license'].replace('-', ' ', 2)}"
    sc.add(text("credit", credit, 1180, 1020, 18, MUTED, BODY))
    sc.fade("credit", 400, dur=400)
    bye(sc, ["unicorn", "halo", "layers-panel", "layers-title", "recolor", "credit", "headline", "kicker"]
        + list_names, 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 5
def petal_points(cx, cy, r0, r1, width, curl):
    """An asymmetric petal pointing up from (cx, cy) between radii r0 and r1, so mirroring shows."""
    return [[cx, cy - r0], [cx + width * 0.9, cy - r0 - (r1 - r0) * 0.35],
            [cx + width * 0.55 + curl, cy - r0 - (r1 - r0) * 0.8], [cx + curl, cy - r1],
            [cx - width * 0.35, cy - r0 - (r1 - r0) * 0.65], [cx - width * 0.45, cy - r0 - (r1 - r0) * 0.25]]


def s05_mandala():
    sc = Scene("05-mandala", DURATIONS["05-mandala"])
    sc.add(backdrop(glow_at=(1330, 640), glow2_at=(300, 300)))
    kicker(sc, "04", "ONE PETAL → MANDALA")
    headline(sc, [("Draw one petal. ", None), ("Repeat it with mirror symmetry.", SKY)])
    sc.add(panel("code-panel", 120, 360, 620, 330))
    lines = [[("{", WHITE)],
             [('  "type"', CODE_KEY), (": ", WHITE), ('"radial-repeat"', CODE_STR), (",", WHITE)],
             [('  "target"', CODE_KEY), (": ", WHITE), ('"petal"', CODE_STR), (",", WHITE)],
             [('  "count"', CODE_KEY), (": ", WHITE), ("12", CODE_NUM), (",", WHITE)],
             [('  "mirror"', CODE_KEY), (": ", WHITE), ("true", CODE_NUM)],
             [("}", WHITE)]]
    ops, code, times = code_lines("code", lines, 160, 400, 28, 1.5, 300, 110)
    sc.add(ops)
    sc.fade("code-panel", 0, dur=300)
    for n, t in times:
        sc.fade(n, t, dur=250)
    cx, cy = 1330, 640
    rings = [  # name, count, petal or dot, colours, appear time, turn
        ("ra", 12, petal_points(cx, cy, 120, 380, 70, 26), BLUE, SKY, 900, 24),
        ("rb", 8, petal_points(cx, cy, 70, 220, 60, -18), GOLD, "#FFE7A6", 1500, -30),
        ("rc", 16, petal_points(cx, cy, 250, 330, 22, 6), CORAL, "#FFD0C2", 2000, 16),
    ]
    groups = []
    for name, count, pts, fill, stroke, t, turn in rings:
        sc.add({"type": "pen", "name": name, "points": pts, "closed": True, "smooth": True, "fill": fill,
                "stroke": stroke, "stroke_width": 3})
        sc.add({"type": "radial-repeat", "target": name, "count": count, "cx": cx, "cy": cy, "mirror": True})
        copies = [name, f"{name}-1-mirror"] + [f"{name}-{k}{m}" for k in range(2, count + 1) for m in ("", "-mirror")]
        sc.pop(name, t, 420, 0.3)
        for k, copy in enumerate(copies[1:], 1):
            sc.fade(copy, t + 300 + k * (700 // len(copies)), dur=220)
        sc.keys(f"{name}-radial", "rotation", [(0, 0), (DURATIONS["05-mandala"], turn)], "linear")
        groups.append(f"{name}-radial")
    sc.add(ellipse("dot", cx, cy - 420, 18, 18, LILAC))
    sc.add({"type": "radial-repeat", "target": "dot", "count": 24, "cx": cx, "cy": cy})
    sc.fade("dot-radial", 2500, dur=400)
    sc.add(ellipse("core", cx, cy, 110, 110, LILAC, "#FFFFFF", 4))
    sc.pop("core", 2700, 420, 0.2)
    copies = sum(2 * count for _, count, *_ in rings)
    sc.add(text("count", f"{len(rings)} petals  →  {copies} mirrored, editable copies", 120, 740, 30, WHITE, SEMI))
    sc.fade("count", 2900, dur=400, rise=12)
    bye(sc, groups + ["dot-radial", "core", "code-panel", "count", "headline", "kicker"] + code, 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 6
PIXEL_PALETTE = {".": "transparent", "k": "#1A1F2B", "s": SKY, "w": "#FFFFFF", "b": BLUE, "y": GOLD, "r": CORAL}
ROBOT = [".....kk.....",
         ".....yk.....",
         "..kkkkkkkk..",
         ".kssssssssk.",
         ".kswwsswwsk.",
         ".kswksswksk.",
         ".kssssrsssk.",
         "..kkkkkkkk..",
         ".kbbbbbbbbk.",
         "kbbbyybbbbbk",
         "kbkbbbbbbkbk",
         ".kkbbbbbbkk.",
         "..kkkkkkkk.."]
LEGS = [["..kbk..kbk..", "..kbk..kbk..", ".kkkk..kkkk."],
        ["..kbk..kbk..", ".kkkk..kbk..", ".......kkkk."],
        ["..kbk..kbk..", "..kbk..kbk..", ".kkkk..kkkk."],
        ["..kbk..kbk..", "..kbk..kkkk.", ".kkkk......."]]
GRASS = ["gggggggggggggggg", "gGggggGgggggGggg", "dddddddddddddddd", "dDddddddDddddddd"]


def pixel_spans(rows):
    """Rows of palette keys as coloured monospace text: each character in the colour it stands for."""
    lines = []
    for row in rows:
        spans = []
        for ch in row:
            colour = PIXEL_PALETTE[ch] if ch != "." else "#4A5368"
            if spans and spans[-1][1] == colour:
                spans[-1] = (spans[-1][0] + ch, colour)
            else:
                spans.append((ch, colour))
        lines.append(spans)
    return lines


def s06_pixel():
    sc = Scene("06-pixel", DURATIONS["06-pixel"])
    sc.add(backdrop(glow_at=(1350, 700), glow2_at=(300, 300)))
    kicker(sc, "05", "PIXEL ART THAT WALKS")
    headline(sc, [("Sprites from rows of text. ", None), ("Animated and exported.", SKY)])
    rows = ROBOT + LEGS[0]
    sc.add(panel("rows-panel", 120, 330, 470, 660))
    ops, rnames, times = code_lines("rw", pixel_spans(rows), 165, 365, 30, 1.25, 300, 55)
    sc.add(ops)
    sc.fade("rows-panel", 0, dur=300)
    for n, t in times:
        sc.fade(n, t, dur=200)
    # The walk: four pixel-art frames, one visible at a time, 150 ms each; the body bobs on frames 1 and 3.
    scale, x, y = 18, 1150, 420
    frames = []
    for i, legs in enumerate(LEGS):
        name = f"robot{i}"
        sc.add({"type": "pixel-art", "name": name, "x": x, "y": y, "palette": PIXEL_PALETTE, "rows": ROBOT + legs},
               {"type": "scale", "target": name, "factor": scale})
        frames.append(name)
    step, start = 150, 1500
    for i, name in enumerate(frames):
        sc.key(name, "visible", 0, i == 0)
        t, k = start, 0
        while t < DURATIONS["06-pixel"]:
            sc.key(name, "visible", t, k % 4 == i, "hold")
            t += step
            k += 1
    sc.add(group("robot", frames))
    sc.pop("robot", 1300, 450, 0.3)
    # Scrolling ground: a grass tile repeated, sliding left one tile per two steps.
    ground_pal = {"g": "#4FBF6A", "G": "#7EDB8E", "d": "#7A5236", "D": "#5E3E28"}
    tiles = []
    for i in range(10):
        name = f"tile{i}"
        sc.add({"type": "pixel-art", "name": name, "x": 880 + i * 96, "y": 420 + 15 * scale, "palette": ground_pal,
                "rows": GRASS}, {"type": "scale", "target": name, "factor": 6})
        tiles.append(name)
    sc.add(group("ground", tiles))
    sc.fade("ground", 1300, dur=300)
    # The tiles are identical, so sliding one tile width and jumping back loops without a seam.
    period = 2 * 2 * step
    t = start
    while t < DURATIONS["06-pixel"]:
        sc.key("ground", "translate-x", t, 0, "hold")
        sc.key("ground", "translate-x", t + period - 1, -96, "linear")
        t += period
    # The exported sprite sheet: the same four frames side by side.
    sheet = []
    for i, legs in enumerate(LEGS):
        name = f"sheet{i}"
        sc.add({"type": "pixel-art", "name": name, "x": 860 + i * 130, "y": 860, "palette": PIXEL_PALETTE,
                "rows": ROBOT + legs}, {"type": "scale", "target": name, "factor": 6})
        sc.pop(name, 2900 + i * 120, 350, 0.4)
        sheet.append(name)
    caption(sc, "sheet-label", "walk-sheet.png  ·  4 frames  ·  150 ms", 1400, 900, 3300, 22)
    bye(sc, ["robot", "ground", "rows-panel", "sheet-label", "headline", "kicker"] + rnames + sheet, 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 7
def s07_forms():
    sc = Scene("07-forms", DURATIONS["07-forms"])
    sc.add(backdrop(glow_at=(1400, 600), glow2_at=(300, 300)))
    kicker(sc, "06", "FORMS PEOPLE CAN FILL IN")
    headline(sc, [("Fillable PDF forms, ", None), ("with validation built in.", SKY)])
    kinds = ["text", "email", "date", "dropdown", "checkbox", "signature"]
    chips = []
    for i, kind in enumerate(kinds):
        name = f"kind{i}"
        sc.add(chip(name, kind, 120 + (i % 3) * 230, 360 + (i // 3) * 80, size=26, fg=WHITE, bg=PANEL, font=MONO,
                    width=210, stroke=LINE))
        sc.pop(name, 400 + i * 110, 380, 0.7)
        chips.append(name)
    sc.add(text("export", "$ vixl export form.pdf --fillable", 120, 560, 26, WHITE, MONO))
    sc.words("export", 1300, "typewriter", "char", 700)
    caption(sc, "export-note", "Real AcroForm fields: tab order, required marks, email and date rules.",
            120, 620, 2000, 22, MUTED, BODY)
    # The form: real field layers on a paper card.
    x0, y0, w0 = 940, 320, 860
    sc.add(rect("paper", x0, y0, w0, 700, PAPER, 20), shadow("paper", 50, 22, 0.5))
    sc.add(text("form-title", "Workshop sign-up", x0 + 50, y0 + 40, 40, INK, HEAD))
    box = {"style": "box", "fill": "#FFFFFF", "stroke": "#C3C9D6", "stroke_width": 2, "radius": 8}
    fields = [("name", "text", "Full name", x0 + 50, y0 + 150, 760, 58, {}),
              ("email", "text", "Email", x0 + 50, y0 + 260, 760, 58, {"format": "email"}),
              ("date", "date", "Date", x0 + 50, y0 + 370, 360, 58, {}),
              ("size", "dropdown", "T-shirt", x0 + 450, y0 + 370, 360, 58, {"options": ["S", "M", "L", "XL"]})]
    form_names = ["paper", "form-title"]
    for key, kind, label, x, y, w, h, extra in fields:
        sc.add(text(f"lbl-{key}", label, x, y - 34, 22, "#5A6377", SEMI),
               {"type": "field", "kind": kind, "name": f"f-{key}", "key": key, "label": label, "x": x, "y": y,
                "width": w, "height": h, "appearance": box, **extra})
        form_names += [f"lbl-{key}", f"f-{key}"]
    sc.add({"type": "field", "kind": "checkbox", "name": "f-slides", "key": "slides", "label": "Send me the slides",
            "x": x0 + 50, "y": y0 + 480, "width": 40, "height": 40, "appearance": {**box, "mark": "check"}},
           text("lbl-slides", "Send me the slides", x0 + 106, y0 + 486, 24, INK, BODY),
           {"type": "field", "kind": "signature", "name": "f-sig", "key": "signature", "label": "Signature",
            "x": x0 + 50, "y": y0 + 570, "width": 760, "height": 90, "required": True,
            "appearance": {"style": "underline", "stroke": "#8A93A6", "stroke_width": 2}},
           text("lbl-sig", "Signature *", x0 + 50, y0 + 668, 18, "#5A6377", SEMI))
    form_names += ["f-slides", "lbl-slides", "f-sig", "lbl-sig"]
    sc.add(group("form", form_names))
    sc.pop("form", 200, 600, 0.9)
    # Someone fills it in: typed values over the fields, and the email rule catching a typo first.
    values = [("v-name", "Ada Okafor", x0 + 66, y0 + 164, 900),
              ("v-date", "14 / 11 / 2026", x0 + 66, y0 + 384, 3100),
              ("v-size", "M", x0 + 466, y0 + 384, 3400)]
    for name, value, x, y, t in values:
        sc.add(text(name, value, x, y, 28, INK, BODY))
        sc.words(name, t, "typewriter", "char", 400 if len(value) > 2 else 120)
    sc.add(text("v-email", "ada@northwind", x0 + 66, y0 + 274, 28, INK, BODY))
    sc.words("v-email", 1500, "typewriter", "char", 450)
    sc.key("v-email", "text", 0, "ada@northwind")
    sc.key("v-email", "text", 2700, "ada@northwind.press", "hold")
    sc.add(rect("email-bad", x0 + 48, y0 + 258, 764, 62, "transparent", 9, BAD, 3))
    sc.keys("email-bad", "opacity", [(0, 0), (2100, 0), (2250, 1), (2700, 1), (2800, 0)], "ease-out-cubic")
    sc.add(text("email-msg", "Enter a valid email address", x0 + 560, y0 + 228, 20, BAD, SEMI))
    sc.keys("email-msg", "opacity", [(0, 0), (2100, 0), (2250, 1), (2700, 1), (2800, 0)], "ease-out-cubic")
    sc.add(text("email-ok", "✓", x0 + 770, y0 + 266, 36, GOOD, HEAD))
    sc.pop("email-ok", 2800, 300, 0.3)
    sc.add({"type": "pen", "name": "tick", "points": [[x0 + 58, y0 + 500], [x0 + 68, y0 + 512], [x0 + 82, y0 + 488]],
            "closed": False, "smooth": False, "fill": "none", "stroke": INK, "stroke_width": 5})
    sc.pop("tick", 3700, 250, 0.3)
    sig = [[x0 + 90, y0 + 640], [x0 + 110, y0 + 595], [x0 + 128, y0 + 640], [x0 + 150, y0 + 600],
           [x0 + 172, y0 + 636], [x0 + 205, y0 + 612], [x0 + 236, y0 + 630], [x0 + 268, y0 + 600],
           [x0 + 290, y0 + 634], [x0 + 340, y0 + 618]]
    sc.add({"type": "pen", "name": "sig", "points": sig, "closed": False, "smooth": True, "fill": "none",
            "stroke": "#1E3A8A", "stroke_width": 4})
    sc.keys("sig", "trim_end", [(0, 0), (3800, 0), (4400, 100)], "ease-in-out")
    typed = ["v-name", "v-date", "v-size", "v-email", "email-ok", "tick", "sig"]
    bye(sc, ["form", "export", "export-note", "headline", "kicker"] + chips + typed, 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 8
DIAGRAM = "idea -> sketch -> layers -> check -> ship\ncheck -> fix -> layers"


def s08_diagram():
    sc = Scene("08-diagram", DURATIONS["08-diagram"])
    sc.add(backdrop(glow_at=(960, 760), glow2_at=(1700, 200)))
    kicker(sc, "07", "ONE LINE → DIAGRAM")
    headline(sc, [("Type the flow. ", None), ("Get a laid-out, routed diagram.", SKY)])
    sc.add(panel("src-panel", 120, 320, 1680, 150))
    for i, line in enumerate(DIAGRAM.split("\n")):
        sc.add(text(f"src{i}", line, 160, 345 + i * 52, 32, CODE_STR, MONO))
        sc.words(f"src{i}", 300 + i * 700, "typewriter", "char", 650)
    sc.fade("src-panel", 0, dur=300)
    sc.add({"type": "diagram-from-text", "name": "dg", "text": DIAGRAM, "x": 120, "y": 510, "width": 1680,
            "height": 470, "direction": "LR", "routing": "curved", "theme": "dark", "node_color": PANEL,
            "edge_color": SKY, "text_color": WHITE, "font": SEMI, "size": 30, "stroke_width": 3, "margin": 10})
    nodes = ["idea", "sketch", "layers", "check", "fix", "ship"]
    for i, node in enumerate(nodes):
        t = 1700 + i * 170
        sc.pop(f"dg/{node}", t, 380, 0.5)
        sc.fade(f"dg/{node}.label", t + 80, dur=250)
    edges = ["idea->sketch", "sketch->layers", "layers->check", "check->ship", "check->fix", "fix->layers"]
    for i, edge in enumerate(edges):
        t = 1900 + i * 170
        sc.fade(f"dg/{edge}", t, dur=300)
        sc.keys(f"dg/{edge}", "trim_end", [(0, 0), (t, 0), (t + 450, 100)], "ease-out-cubic")
    sc.keys("dg/check", "fill", [(0, PANEL), (3500, PANEL), (3800, BLUE)], "ease-in-out")
    sc.keys("dg/check", "scale", [(3500, 1), (3700, 1.12), (3950, 1)], "ease-out-cubic")
    caption(sc, "dg-note", "Every node and edge stays a layer: rename one and the routes follow.", 120, 1000, 3300,
            22, MUTED, BODY)
    bye(sc, ["dg", "src-panel", "src0", "src1", "dg-note", "headline", "kicker"], 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 9
PLANTS = [("tree", 11, 120, 560, 380, 440), ("sunflower", 4, 520, 640, 300, 300), ("fern", 7, 860, 560, 300, 400),
          ("rose", 2, 1180, 660, 280, 280), ("pine", 5, 1480, 520, 320, 460)]


def s09_garden():
    sc = Scene("09-garden", DURATIONS["09-garden"])
    sc.add(backdrop(glow_at=(960, 800), glow2_at=(1600, 200)))
    kicker(sc, "08", "GROWN FROM A SEED")
    headline(sc, [("Plants grown from a number. ", None), ("Same seed, same plant.", SKY)])
    sc.add(rect("soil", 0, 1000, 1920, 80, "#1E2330"))
    names = ["soil"]
    for i, (preset, seed, x, y, w, h) in enumerate(PLANTS):
        for k, s in enumerate((seed, seed + 1)):
            name = f"{preset}-{k}"
            sc.add({"type": "organic", "preset": preset, "name": name, "seed": s, "x": x, "y": 1000 - h, "width": w,
                    "height": h}, {"type": "pivot", "target": name, "value": "bottom"})
            names.append(name)
        t = 500 + i * 220
        sc.keys(f"{preset}-0", "scale", [(0, 0.02), (t, 0.02), (t + 900, 1)], "ease-out-back")
        sc.keys(f"{preset}-0", "opacity", [(0, 0), (t, 0), (t + 200, 1), (3000 + i * 80, 1), (3300 + i * 80, 0)])
        sc.keys(f"{preset}-1", "scale", [(0, 0.02), (3000 + i * 80, 0.02), (3700 + i * 80, 1)], "ease-out-back")
        sc.keys(f"{preset}-1", "opacity", [(0, 0), (3000 + i * 80, 0), (3200 + i * 80, 1)])
        label = f"lab{i}"
        sc.add(text(label, f"{preset}  seed {seed}", x + 10, 1020, 24, MUTED, MONO))
        sc.fade(label, t + 300, dur=300)
        sc.key(label, "text", 0, f"{preset}  seed {seed}")
        sc.key(label, "text", 3000 + i * 80, f"{preset}  seed {seed + 1}", "hold")
        sc.keys(label, "color", [(0, MUTED), (3000 + i * 80, MUTED), (3050 + i * 80, SKY)])
        names.append(label)
    bye(sc, names + ["headline", "kicker"], 4500)
    return sc


# ----------------------------------------------------------------------------------------------- 10
LANES = [("kick", CORAL), ("snare", GOLD), ("hats", "#8A93A6"), ("bass", BLUE), ("keys", SKY), ("bells", LILAC),
         ("whoosh", MINT), ("pops", WHITE)]


def s10_score(start, total, track_ops):
    sc = Scene("10-score", DURATIONS["10-score"])
    sc.add(backdrop(glow_at=(960, 640), glow2_at=(1700, 200)))
    kicker(sc, "09", "EVEN THE SOUNDTRACK")
    headline(sc, [("This music is a Vixl document, ", None), ("too.", SKY)])
    px, py, pw, ph = 120, 320, 1680, 560
    sc.add(panel("roll", px, py, pw, ph))
    sc.fade("roll", 0, dur=300)
    rx, rw, lane_h = px + 190, pw - 220, (ph - 40) / len(LANES)
    by_name = {op["name"]: op for op in track_ops}
    names = ["roll"]
    for i, (lane, colour) in enumerate(LANES):
        notes = by_name[lane]["notes"]
        ly = py + 20 + i * lane_h
        sc.add(text(f"lane{i}", lane, px + 30, ly + lane_h / 2 - 14, 24, colour, MONO))
        lo = min(n["midi"] for n in notes)
        hi = max(n["midi"] for n in notes)
        note_names = []
        for j, n in enumerate(notes):
            y = ly + 8 + (1 - (n["midi"] - lo) / max(1, hi - lo)) * (lane_h - 24)
            name = f"n{i}-{j}"
            sc.add(rect(name, rx + n["start"] / total * rw, y, max(3, n["duration"] / total * rw), 8, colour, 2))
            note_names.append(name)
        sc.add(group(f"lane{i}-notes", note_names))
        t = 300 + i * 120
        sc.fade(f"lane{i}", t, dur=250)
        sc.fade(f"lane{i}-notes", t + 60, dur=300)
        sc.slide(f"lane{i}-notes", t + 60, dx=60, dur=500)
        names += [f"lane{i}", f"lane{i}-notes"]
    # The playhead sits where this shot actually plays in the film.
    x0 = rx + start / total * rw
    x1 = rx + (start + DURATIONS["10-score"]) / total * rw
    sc.add(rect("playhead", x0, py + 10, 4, ph - 20, WHITE, 2), glow("playhead-glow", x0 + 2, py + ph / 2, 220, SKY,
                                                                         "66"))
    for name in ("playhead", "playhead-glow"):
        sc.keys(name, "translate-x", [(0, 0), (DURATIONS["10-score"], x1 - x0)], "linear")
        sc.fade(name, 1100, dur=300)
    names += ["playhead", "playhead-glow"]
    code = [[('{"type"', CODE_KEY), (": ", WHITE), ('"audio-track"', CODE_STR), (", ", WHITE), ('"synth"', CODE_KEY),
             (": ", WHITE), ('"bell"', CODE_STR), (", ", WHITE), ('"notes"', CODE_KEY), (": [{", WHITE),
             ('"start"', CODE_KEY), (": ", WHITE), ("0", CODE_NUM), (", ", WHITE), ('"midi"', CODE_KEY),
             (": ", WHITE), ("76", CODE_NUM), ("}, …]}", WHITE)]]
    sc.add(rich("code", code[0], 120, 920, 24, 1680, WHITE, MONO))
    sc.fade("code", 1800, dur=400, rise=12)
    note_count = sum(len(op["notes"]) for op in track_ops)
    sc.add(chip("stat", f"{note_count:,} notes  ·  synthesized and mixed by Vixl  ·  score.vixl → WAV", 120, 980,
                size=24, fg=WHITE, bg="#3575EE40", font=SEMI))
    sc.pop("stat", 2600, 400, 0.9)
    bye(sc, names + ["code", "stat", "headline", "kicker"], 5450)
    return sc


# ----------------------------------------------------------------------------------------------- 11
RECAP = ["sketch → vectors", "print runs", "emoji masters", "mandalas", "pixel sprites", "fillable forms",
         "text → diagram", "seeded plants", "the soundtrack"]


def s11_end():
    sc = Scene("11-end", DURATIONS["11-end"])
    sc.add(backdrop(glow_at=(960, 420), glow2_at=(960, 1000)))
    sc.add(glow("pulse", 960, 260, 900, BLUE, "55"))
    ops, names = mark("m", 860, 110, 200)
    sc.add(ops, group("logo", names))
    sc.pop("logo", 0, 600, 0.5)
    sc.add(centered("line", [("It does ", None), ("that", SKY), (", too.", None)], 370, 130))
    sc.words("line", 300, "fade-up", "word", 500, 140)
    widths = [round(len(label) * 21 * 0.6 + 40) for label in RECAP]
    rows = [RECAP[:5], RECAP[5:]]
    y = 580
    k = 0
    for row in rows:
        row_w = sum(widths[k:k + len(row)]) + 14 * (len(row) - 1)
        x = (1920 - row_w) / 2
        for label in row:
            name = f"recap{k}"
            sc.add(chip(name, label, x, y, size=21, fg=WHITE, bg=PANEL, font=SEMI, width=widths[k], stroke=LINE))
            sc.pop(name, 900 + k * 70, 300, 0.7)
            x += widths[k] + 14
            k += 1
        y += 62
    sc.add(centered("url", "github.com/jxburros/Vixl", 760, 44, WHITE, MONO))
    sc.fade("url", 1700, dur=400, rise=16)
    sc.add(centered("made", "Every frame of this video is an editable Vixl document. So is the music.", 960, 26,
                    MUTED, BODY))
    sc.fade("made", 2100, dur=500)
    return sc


def all_scenes():
    starts, total = cuts()
    tracks = score.tracks(starts, total)
    return [s01_hook(), s02_sketch(), s03_badges(), s04_emoji(), s05_mandala(), s06_pixel(), s07_forms(),
            s08_diagram(), s09_garden(), s10_score(starts[9], total, tracks), s11_end()]
