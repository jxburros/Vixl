"""The eleven shots of "Vixl in 60 seconds". Each function returns a ``Scene``; times are milliseconds.

Beat grid: the score runs at 120 BPM, so a beat is 500 ms and most entrances land on one.
"""
from __future__ import annotations

import math

from kit import (BAD, BLUE, BODY, CODE_KEY, CODE_NUM, CODE_STR, DEEP, GOOD, HEAD, LINE, MONO,
                 MUTED, PANEL, SEMI, SKY, WHITE, Scene, backdrop, centered, chip, ellipse, glow, group,
                 image, mark, rect, rich, ripple_in, shadow, text, wordmark)

# The poster the agent builds in shots 3-5: a desert festival card, drawn from plain layers.
DUSK = [(0, "#1B1446"), (0.45, "#6B2C91"), (0.75, "#F2709C"), (1, "#FFB36B")]
DAWN = [(0, "#0E3A5B"), (0.45, "#1F7A8C"), (0.75, "#7FD1C7"), (1, "#F6E7B0")]
SUN, SUN2 = "#FFD36E", "#FFF4D6"
DIM_DATES = "#B5658F"  # the low-contrast colour the check catches in shot 5


def wave(x, y, w, h, top, amp, phase, freq=1.6, n=48):
    """A closed dune silhouette: a sine ridge at ``top`` (fraction of h) filled to the bottom edge."""
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append([round(x + u * w, 2),
                    round(y + h * top + amp * h * math.sin(2 * math.pi * (freq * u + phase)), 2)])
    pts += [[x + w, y + h], [x, y + h]]
    return pts


def poster(p, x, y, w, h, title="SOLSTICE", dates_color=WHITE, sky=DUSK):
    """Poster sheets bottom to top: {sheet: [ops]}. Every layer stays inside the poster box."""
    s = w / 640
    sheets = {
        "sky": [{"type": "gradient", "name": f"{p}-sky", "direction": "vertical", "x": x, "y": y,
                 "width": w, "height": h, "stops": [{"offset": o, "color": c} for o, c in sky]}],
        "halo": [glow(f"{p}-halo", x + w / 2, y + h * 0.6, w * 1.1, "#FFD36E", "70")],
        "sun": [ellipse(f"{p}-sun", x + w / 2, y + h * 0.6, w * 0.52, w * 0.52, SUN)],
        "dunes-back": [{"type": "pen", "name": f"{p}-dunes-back", "points": wave(x, y, w, h, 0.72, 0.035, 0.1),
                        "closed": True, "smooth": False, "fill": "#3A1F5C"}],
        "dunes-front": [{"type": "pen", "name": f"{p}-dunes-front", "points": wave(x, y, w, h, 0.84, 0.03, 0.55, 1.2),
                         "closed": True, "smooth": False, "fill": "#170F2E"}],
        "title": [rich(f"{p}-title", title, x, y + 70 * s, round(104 * s), w, WHITE, HEAD, "center")],
        "dates": [rich(f"{p}-dates", "JUNE 19-21  ·  MOJAVE", x, y + 200 * s, round(30 * s), w, dates_color,
                       SEMI, "center")],
        "badge": [{"type": "shape", "shape": "star", "name": f"{p}-badge-star", "x": round(x + w - 190 * s),
                   "y": round(y + 270 * s), "width": round(150 * s), "height": round(150 * s), "sides": 14,
                   "inner_radius": 0.82, "fill": "#3FE0F0"},
                  rich(f"{p}-badge-label", "LIVE", x + w - 190 * s, y + 325 * s, round(32 * s), 150 * s, DEEP,
                       HEAD, "center"),
                  group(f"{p}-badge", [f"{p}-badge-star", f"{p}-badge-label"])],
    }
    sheets["dunes-front"].append({"type": "layer-intent", "targets": [f"{p}-dunes-back", f"{p}-dunes-front"],
                                  "allow_crop": True})
    return sheets


def flat(sheets):
    return [op for ops in sheets.values() for op in ops]


def kicker(sc, number, label, t=0):
    sc.add(chip("kicker", f"{number}  {label}", 120, 70, size=24, fg=SKY, bg="#3575EE26", font=MONO))
    sc.fade("kicker", t, dur=300)


def headline(sc, spans, t=150, y=140, size=72):
    sc.add(rich("headline", spans, 120, y, size, 1680, WHITE, HEAD))
    sc.words("headline", t, "fade-up", "word", 500, 70)


# ----------------------------------------------------------------------------------------------- 1
def s01_hook():
    sc = Scene("01-hook", 6000)
    sc.add(backdrop(glow_at=(1500, 250)))
    # Pixel stair on the right, a raster motif, one block per beat.
    for i in range(8):
        size = 104 - i * 9
        x, y = 1590 + i * 38, 250 + i * 70
        name = f"px{i}"
        sc.add(rect(name, x, y, size, size, SKY if i % 2 else BLUE))
        sc.pop(name, 250 + i * 500, 380, 0.2)
        sc.keys(name, "opacity", [(250 + i * 500 + 380, 1), (4200, 1), (5000, 0.35)], "ease-in-out")
    lines = [("l1", [("Ask an AI for a poster.", None)], 230, 300, 110),
             ("l2", [("Get a picture of a poster.", None)], 380, 1300, 110),
             ("l3", [("Now get the ", None), ("real thing.", SKY)], 570, 2300, 130)]
    for name, spans, y, t, size in lines:
        sc.add(rich(name, spans, 160, y, size, 1420, WHITE, HEAD))
        sc.words(name, t, "fade-up" if name != "l3" else "pop", "word", 520, 110)
    for name in ("l1", "l2"):
        sc.keys(name, "opacity", [(3600, 1), (4200, 0.28)], "ease-in-out")
    sc.add(text("cmd", "$ vixl mcp --workspace .", 160, 900, 30, MUTED, MONO))
    sc.words("cmd", 3400, "typewriter", "char", 900)
    for name in ("l1", "l2", "l3", "cmd"):
        sc.keys(name, "translate-x", [(0, 0), (5300, 0), (5950, -140)], "ease-in-cubic")
    sc.keys("l3", "opacity", [(5300, 1), (5950, 0)], "ease-in-cubic")
    sc.keys("cmd", "opacity", [(5300, 1), (5950, 0)], "ease-in-cubic")
    sc.keys("l1", "opacity", [(5300, 0.28), (5950, 0)])
    sc.keys("l2", "opacity", [(5300, 0.28), (5950, 0)])
    return sc


# ----------------------------------------------------------------------------------------------- 2
def s02_logo():
    sc = Scene("02-logo", 4000)
    sc.add(backdrop(glow_at=(960, 420), glow2_at=(960, 900)))
    sc.add(glow("pulse", 960, 430, 1100, BLUE, "66"))
    sc.keys("pulse", "scale", [(0, 0.4), (500, 0.4), (1300, 1.05)], "ease-out-cubic")
    sc.keys("pulse", "opacity", [(0, 0), (500, 0), (900, 1)])
    # The Ripple wordmark builds letter by letter, then its reflection ripples in and keeps moving.
    ops, names = wordmark("w", 550, 300, 820)
    sc.add(ops)
    letters = ["w-v", "w-i-stem", "w-i-dot", "w-x", "w-l"]
    for i, name in enumerate(letters):
        sc.pop(name, 250 + i * 110, 380, 0.4)
    ripple_in(sc, [n for n in names if "-band-" in n], 850, stagger=45)
    sc.add(centered("tag", "A design engine for AI agents.", 800, 50, MUTED, BODY))
    sc.words("tag", 1500, "fade-up", "word", 480, 80)
    sc.add(centered("pillars", [("Programmable.  ", None), ("Editable.  ", None), ("Checked.", SKY)], 890, 40,
                    WHITE, SEMI))
    sc.words("pillars", 2300, "pop", "word", 400, 260)
    return sc


# ----------------------------------------------------------------------------------------------- 3
OPS = [
    ("sky", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"gradient"', CODE_STR), (', ', WHITE),
             ('"name"', CODE_KEY), (': ', WHITE), ('"sky"', CODE_STR), ('}', WHITE)]),
    ("sun", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"shape"', CODE_STR), (', ', WHITE),
             ('"shape"', CODE_KEY), (': ', WHITE), ('"ellipse"', CODE_STR), ('}', WHITE)]),
    ("dunes", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"pen"', CODE_STR), (', ', WHITE),
               ('"name"', CODE_KEY), (': ', WHITE), ('"dunes"', CODE_STR), ('}', WHITE)]),
    ("title", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"text"', CODE_STR), (', ', WHITE),
               ('"text"', CODE_KEY), (': ', WHITE), ('"SOLSTICE"', CODE_STR), ('}', WHITE)]),
    ("dates", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"text"', CODE_STR), (', ', WHITE),
               ('"size"', CODE_KEY), (': ', WHITE), ('30', CODE_NUM), ('}', WHITE)]),
    ("badge", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"shape"', CODE_STR), (', ', WHITE),
               ('"shape"', CODE_KEY), (': ', WHITE), ('"star"', CODE_STR), ('}', WHITE)]),
    ("look", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"look"', CODE_STR), (', ', WHITE),
              ('"look"', CODE_KEY), (': ', WHITE), ('"glow"', CODE_STR), ('}', WHITE)]),
]


def s03_build():
    sc = Scene("03-build", 10000)
    sc.add(backdrop(glow_at=(1450, 500)))
    kicker(sc, "01", "PROGRAMMABLE")
    headline(sc, [("Your agent ", None), ("makes it.", SKY)])
    cx, cy, cw, ch = 120, 290, 860, 690
    sc.add(rect("code-bg", cx, cy, cw, ch, DEEP, 22, LINE))
    for i, c in enumerate(["#FF6B6B", "#FFC37A", "#5FD38D"]):
        sc.add(ellipse(f"code-dot{i}", cx + 34 + i * 26, cy + 34, 14, 14, c))
    sc.add(text("code-title", "vixl_operations_apply", cx + 120, cy + 20, 24, MUTED, MONO))
    sc.add(text("code-open", "[", cx + 40, cy + 80, 26, WHITE, MONO))
    sc.add(rect("cursor", cx + 20, cy + 128, cw - 40, 56, "#3575EE30", 10))
    sc.fade("cursor", 900, dur=200)
    times = [1000 + i * 800 for i in range(len(OPS))]
    for i, (name, spans) in enumerate(OPS):
        y = cy + 136 + i * 62
        sc.add(rich(f"op-{name}", spans, cx + 70, y, 25, cw - 100, WHITE, MONO, line_height=1.2))
        sc.fade(f"op-{name}", times[i], dur=250)
        sc.slide(f"op-{name}", times[i], dx=-30, dur=400)
        if i:
            sc.key("cursor", "translate-y", times[i] - 120, (i - 1) * 62)
            sc.key("cursor", "translate-y", times[i], i * 62, "ease-out-cubic")
    sc.key("cursor", "translate-y", 0, 0)
    end = cy + 136 + len(OPS) * 62
    sc.add(text("code-close", "]", cx + 40, end, 26, WHITE, MONO))
    t_done = times[-1] + 900
    sc.add(rich("result", [("✓ ", GOOD), ("7 operations · all or nothing, one undo", MUTED)],
                cx + 40, cy + ch - 80, 26, cw - 80, WHITE, MONO))
    sc.fade("result", t_done, dur=300, rise=12)
    sc.keys("cursor", "opacity", [(t_done - 200, 1), (t_done + 100, 0)])

    px, py, pw, ph = 1180, 300, 552, 690
    sc.add(rect("canvas", px, py, pw, ph, DEEP, 0, "#FFFFFF22"), shadow("canvas", 50, 24, 0.5))
    sc.add(text("canvas-label", "poster.vixl  ·  1080 × 1350", px, py - 40, 22, MUTED, MONO))
    sheets = poster("p", px, py, pw, ph)
    sc.add(flat(sheets))
    t = dict(zip([n for n, _ in OPS], times))
    sc.fade("p-sky", t["sky"], dur=500)
    sc.pop("p-sun", t["sun"], 600, 0.2)
    sc.slide("p-dunes-back", t["dunes"], dy=260, dur=800)
    sc.slide("p-dunes-front", t["dunes"] + 120, dy=220, dur=800)
    sc.fade("p-dunes-back", t["dunes"], dur=200)
    sc.fade("p-dunes-front", t["dunes"] + 120, dur=200)
    sc.words("p-title", t["title"], "pop", "char", 380, 50)
    sc.words("p-dates", t["dates"], "fade-up", "word", 400, 90)
    sc.pop("p-badge", t["badge"], 500, 0.1)
    sc.keys("p-badge", "rotation", [(0, -40), (t["badge"], -40), (t["badge"] + 600, 12)], "ease-out-back")
    sc.fade("p-halo", t["look"], dur=700)
    sc.keys("p-sun", "fill", [(t["look"], SUN), (t["look"] + 700, "#FFE59A")])
    return sc


# ----------------------------------------------------------------------------------------------- 4
LAYER_ROWS = [("badge", "★", "star"), ("dates", "T", "text"), ("title", "T", "text"),
              ("dunes-front", "▲", "pen"), ("dunes-back", "▲", "pen"), ("sun", "●", "ellipse"),
              ("halo", "◐", "gradient"), ("sky", "▦", "gradient")]


def s04_edit():
    sc = Scene("04-edit", 6000)
    sc.add(backdrop(glow_at=(700, 500)))
    kicker(sc, "02", "EDITABLE")
    headline(sc, [("You keep the ", None), ("layers.", SKY)], t=100)
    px, py, pw, ph = 330, 290, 520, 650
    sc.add(rect("canvas", px, py, pw, ph, DEEP), shadow("canvas", 50, 24, 0.5))
    sheets = poster("p", px, py, pw, ph)
    sheets["sky2"] = [{"type": "gradient", "name": "p-sky2", "direction": "vertical", "x": px, "y": py,
                       "width": pw, "height": ph, "stops": [{"offset": o, "color": c} for o, c in DAWN]}]
    order = ["sky", "sky2", "halo", "sun", "dunes-back", "dunes-front", "title", "dates", "badge"]
    t_open, t_close = 700, 2900
    level = 0
    for name in order:
        ops = sheets[name]
        members = [op["name"] for op in ops if op["type"] not in ("group", "layer-intent")]
        if name == "badge":
            members = ["p-badge"]
        outline = f"sheet-{name}"
        sc.add(ops, rect(outline, px, py, pw, ph, "#6A9AFF08", 0, SKY, 2), group(f"g-{name}", members + [outline]))
        sc.keys(outline, "opacity", [(0, 0), (t_open, 0), (t_open + 500, 1), (t_close, 1), (t_close + 400, 0)])
        if name == "sky2":
            continue  # shares the sky's level: it fades in over it later
        dx, dy = level * 44, -level * 14
        for prop, v in (("translate-x", dx), ("translate-y", dy)):
            sc.keys(f"g-{name}", prop, [(0, 0), (t_open, 0), (t_open + 800, v), (t_close, v), (t_close + 600, 0)],
                    "ease-in-out-cubic")
        sc.keys(f"g-{name}", "scale", [(0, 1), (t_open, 1), (t_open + 800, 0.8), (t_close, 0.8), (t_close + 600, 1)],
                "ease-in-out-cubic")
        level += 1
    for prop in ("translate-x", "translate-y", "scale"):
        src = [o for o in sc.ops if o.get("target") == "g-sky" and o.get("property") == prop]
        for o in src:
            sc.ops.append({**o, "target": "g-sky2"})
    sc.keys("p-sky2", "opacity", [(0, 0), (3700, 0), (4400, 1)], "ease-in-out")
    sc.keys("p-sun", "fill", [(3700, SUN), (4400, SUN2)], "ease-in-out")
    sc.key("p-title", "text", 0, "SOLSTICE")
    sc.key("p-title", "text", 3700, "EQUINOX")
    sc.keys("p-title", "scale", [(3700, 1.12), (4100, 1)], "ease-out-back")

    # Layer panel
    lx, ly = 1120, 300
    sc.add(text("panel-title", "LAYERS", lx, ly - 4, 24, MUTED, MONO))
    for i, (name, icon, kind) in enumerate(LAYER_ROWS):
        y = ly + 50 + i * 60
        row = f"row-{name}"
        sc.add(rect(f"{row}-bg", lx, y, 680, 52, PANEL, 12),
               rich(f"{row}-icon", icon, lx + 14, y + 10, 26, 40, SKY, SEMI, "center", 1.2),
               text(f"{row}-name", name, lx + 70, y + 11, 26, WHITE, MONO),
               text(f"{row}-kind", kind, lx + 540, y + 13, 22, MUTED, MONO),
               group(row, [f"{row}-bg", f"{row}-icon", f"{row}-name", f"{row}-kind"]))
        sc.fade(row, 300 + i * 70, dur=300)
        sc.slide(row, 300 + i * 70, dx=60, dur=500)
    sc.keys("row-title-bg", "fill", [(0, PANEL), (3300, PANEL), (3500, "#3575EE"), (5200, "#3575EE")])
    sc.keys("row-sky-bg", "fill", [(0, PANEL), (3300, PANEL), (3500, "#3575EE"), (5200, "#3575EE")])
    sc.add(rich("edit-op", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"text-set"', CODE_STR), (', ', WHITE),
                            ('"target"', CODE_KEY), (': ', WHITE), ('"title"', CODE_STR), (', ', WHITE),
                            ('"text"', CODE_KEY), (': ', WHITE), ('"EQUINOX"', CODE_STR), ('}', WHITE)],
                lx, 860, 22, 780, WHITE, MONO))
    sc.words("edit-op", 3200, "typewriter", "char", 500)
    sc.add(rich("sub", "One edit, not a whole new image. Text stays text.", lx, 920, 30, 760, MUTED, BODY,
                line_height=1.25))
    sc.fade("sub", 4300, dur=400, rise=12)
    return sc


# ----------------------------------------------------------------------------------------------- 5
def s05_check(before, needs):
    """``before`` and ``needs`` are the contrast figures the real ``check`` reported for the dates line."""
    sc = Scene("05-check", 6000)
    sc.add(backdrop(glow_at=(1300, 600)))
    kicker(sc, "03", "CHECKED")
    headline(sc, [("Vixl ", None), ("checks", SKY), (" the work.", None)], t=100)
    px, py, pw, ph = 200, 290, 520, 650
    sc.add(rect("canvas", px, py, pw, ph, DEEP), shadow("canvas", 50, 24, 0.5))
    sc.add(flat(poster("p", px, py, pw, ph, dates_color=DIM_DATES)))
    t_fix = 2700
    sc.keys("p-dates", "color", [(0, DIM_DATES), (t_fix, DIM_DATES), (t_fix + 400, WHITE)], "ease-in-out")
    s = pw / 640
    sc.add(rect("flag", px + 70 * s, py + 190 * s, pw - 140 * s, 60 * s, "#FF6B6B14", 8, BAD, 3))
    sc.keys("flag", "opacity", [(0, 0), (1000, 0), (1200, 1), (1500, 0.4), (1800, 1), (2100, 0.4), (2400, 1)])
    sc.keys("flag", "stroke_color", [(t_fix, BAD), (t_fix + 300, GOOD)])
    sc.keys("flag", "fill", [(t_fix, "#FF6B6B14"), (t_fix + 300, "#5FD38D14")])
    sc.keys("flag", "opacity", [(t_fix + 900, 1), (t_fix + 1400, 0)])
    sc.add(rect("safe", px + 24, py + 24, pw - 48, ph - 48, "#00000000", 0, "#6A9AFF99", 2))
    sc.fade("safe", 3400, 4600, dur=300)

    fx, fy, fw = 860, 290, 940
    sc.add(rect("panel", fx, fy, fw, 650, DEEP, 22, LINE))
    sc.add(text("panel-title", "vixl check  ·  bounds  overlap  contrast  fonts", fx + 40, fy + 30, 24, MUTED, MONO))
    rows = [("contrast", f"dates  {before}:1, needs {needs}:1", 1000),
            ("bounds", "every layer inside the canvas", 1300),
            ("overlap", "title, dates and badge stay clear", 1600),
            ("fonts", "Inter Tight and Inter embedded", 1900)]
    for i, (name, detail, t) in enumerate(rows):
        y = fy + 110 + i * 120
        bad = name == "contrast"
        sc.add(rect(f"r{i}-bg", fx + 30, y, fw - 60, 96, PANEL, 16),
               ellipse(f"r{i}-dot", fx + 84, y + 48, 44, 44, BAD if bad else GOOD),
               rich(f"r{i}-mark", "!" if bad else "✓", fx + 62, y + 30, 28, 44, DEEP, HEAD, "center", 1.2),
               text(f"r{i}-name", name, fx + 130, y + 28, 32, WHITE, SEMI),
               text(f"r{i}-detail", detail, fx + 330, y + 32, 27, BAD if bad else MUTED, BODY),
               group(f"r{i}", [f"r{i}-bg", f"r{i}-dot", f"r{i}-mark", f"r{i}-name", f"r{i}-detail"]))
        sc.fade(f"r{i}", t, dur=300)
        sc.slide(f"r{i}", t, dx=50, dur=450)
    sc.keys("r0-dot", "fill", [(t_fix, BAD), (t_fix + 300, GOOD)])
    sc.key("r0-mark", "text", 0, "!")
    sc.key("r0-mark", "text", t_fix + 150, "✓")
    sc.key("r0-detail", "text", 0, f"dates  {before}:1, needs {needs}:1")
    sc.key("r0-detail", "text", t_fix + 150, f"dates  now clears {needs}:1")
    sc.keys("r0-detail", "color", [(t_fix, BAD), (t_fix + 300, MUTED)])
    sc.add(rich("fix-op", [('{', WHITE), ('"type"', CODE_KEY), (': ', WHITE), ('"text-set"', CODE_STR), (', ', WHITE),
                           ('"target"', CODE_KEY), (': ', WHITE), ('"dates"', CODE_STR), (', ', WHITE),
                           ('"color"', CODE_KEY), (': ', WHITE), ('"white"', CODE_STR), ('}', WHITE)],
                fx + 40, fy + 590, 23, fw - 80, WHITE, MONO))
    sc.words("fix-op", 2200, "typewriter", "char", 450)
    sc.add(chip("pass", "✓  4 of 4 checks pass", 1240, 960, size=30, fg=DEEP, bg=GOOD, font=SEMI, width=420))
    sc.pop("pass", 3600, 450, 0.5)
    sc.add(rich("before", "Before the print shop finds it.", px, 968, 30, 640, MUTED, BODY))
    sc.fade("before", 3900, dur=400, rise=12)
    return sc


# ----------------------------------------------------------------------------------------------- 6-8
SHOW = "explorations/{}/output/{}"


def montage(name, words, tiles, number="04"):
    sc = Scene(name, 4000)
    sc.add(backdrop(glow_at=(1300, 540), glow2_at=(200, 900)))
    kicker(sc, number, "ALL MADE WITH VIXL")
    sc.add(rich("big", words, 120, 330, 92, 600, WHITE, HEAD, line_height=1.02))
    sc.words("big", 100, "fade-up", "word", 450, 90)
    names = []
    for i, (key, path, x, y, w, h, label, *swap) in enumerate(tiles):
        sc.add(image(key, path, x, y, w, h, 20))
        sc.add(shadow(f"{key}-base", 36, 16, 0.5))
        lab = f"{key}-chip"
        sc.add(chip(lab, label, x + 16, y + h - 58, size=21, fg=WHITE, bg="#141824D9", font=SEMI))
        t = 250 + i * 160
        sc.pop(key, t, 520, 0.82)
        sc.fade(lab, t + 350, dur=250)
        names += [key, lab]
        if swap:
            alt_path, alt_label, t_swap = swap
            sc.add(image(f"{key}-alt", alt_path, x, y, w, h, 20))
            sc.keys(f"{key}-alt", "opacity", [(0, 0), (t_swap, 0), (t_swap + 500, 1)], "ease-in-out")
            sc.add(chip(f"{lab}-alt", alt_label, x + 16, y + h - 58, size=21, fg=WHITE, bg="#141824D9", font=SEMI))
            sc.keys(lab, "opacity", [(t_swap, 1), (t_swap + 300, 0)])
            sc.keys(f"{lab}-alt", "opacity", [(0, 0), (t_swap + 200, 0), (t_swap + 500, 1)])
            names += [f"{key}-alt", f"{lab}-alt"]
    sc.add(group("wall", names))
    sc.keys("wall", "translate-x", [(0, 40), (4000, -40)], "linear")
    sc.keys("wall", "scale", [(0, 1), (4000, 1.04)], "linear")
    return sc


def s06_graphics():
    return montage("06-graphics", [("Posters, brands ", None), ("& print.", SKY)], [
        ("poster", SHOW.format("01-print-concert-poster", "poster-rgb.png"), 760, 120, 460, 840, "CMYK print poster"),
        ("brand", SHOW.format("02-brand-identity", "board/brand-board.png"), 1240, 120, 600, 400, "Brand identity"),
        ("cards", SHOW.format("07-trading-cards", "sheets/contact-sheet.jpg"), 1240, 540, 290, 420, "Card sets"),
        ("campaign", SHOW.format("09-collab-campaign", "00-overview.png"), 1550, 540, 290, 420, "Campaigns"),
    ])


def s07_data():
    return montage("07-data", [("Charts, decks ", None), ("& forms.", SKY)], [
        ("donut", SHOW.format("08-infographic", "social-donut-1080.png"), 760, 120, 440, 440, "Infographics"),
        ("chart", "docs/assets/generated/chart.png", 1220, 120, 620, 348, "Editable charts"),
        ("slides", "docs/assets/generated/slides.png", 1220, 488, 620, 200, "Slide decks"),
        ("form", "docs/assets/generated/registration-filled.png", 760, 580, 440, 380, "PDFs people fill in"),
        ("flow", "docs/assets/generated/workflow.png", 1220, 708, 620, 252, "Routed diagrams"),
    ])


def s08_art():
    return montage("08-art", [("Art, games ", None), ("& motion.", SKY)], [
        ("paint", SHOW.format("05-generative-painting", "painting.jpg"), 760, 120, 640, 400, "Brush painting",
         SHOW.format("05-generative-painting", "variant-watercolor.jpg"), "Watercolor filter", 2300),
        ("map", SHOW.format("04-pixel-rpg", "map@3x.png"), 1420, 120, 420, 252, "Pixel-art games"),
        ("emoji", "docs/assets/generated/emojis.png", 1420, 392, 420, 568, "Emoji sets"),
        ("film", "promo/assets/germ-king.png", 760, 540, 640, 420, "Animated films"),
    ])


# ----------------------------------------------------------------------------------------------- 9
FORMATS = ["PNG", "SVG", "PDF", "PPTX", "Layered PSD", "HTML deck", "GIF", "WebP", "MP4", "CMYK PDF",
           "Fillable PDF", ".vixl master"]


def s09_deliver():
    sc = Scene("09-deliver", 6000)
    sc.add(backdrop(glow_at=(960, 600), glow2_at=(1700, 200)))
    kicker(sc, "05", "DELIVER")
    headline(sc, [("Every size. Every format. ", None), ("Plus the master.", SKY)], t=100)
    cx, cy = 960, 610
    shapes = [(0, 520, 520, "1080 × 1080  ·  feed post"), (1900, 360, 640, "1080 × 1920  ·  story"),
              (3700, 800, 450, "1920 × 1080  ·  video")]
    sc.add(rect("card", cx - 260, cy - 260, 520, 520, BLUE, 28), shadow("card", 50, 24, 0.5))
    sc.add(glow("card-glow", cx, cy - 40, 520, SKY, "55"))
    ops, _ = mark("cm", cx - 70, cy - 150, 140, "mark-white")
    sc.add(ops)
    sc.add(centered("card-title", "Launch day", cy + 30, 58, WHITE, HEAD, x=cx - 200, width=400))
    sc.add(centered("card-sub", "Ideas become editable.", cy + 108, 26, "#DDE6FF", BODY, x=cx - 200, width=400))
    sc.add(centered("size", shapes[0][3], cy + 360, 28, MUTED, MONO, x=cx - 300, width=600))
    for i, (t, w, h, label) in enumerate(shapes):
        ease = None if i == 0 else "ease-in-out-cubic"
        start = t - 600 if i else 0
        if i:
            for prop, v0, v1 in (("x", cx - shapes[i - 1][1] / 2, cx - w / 2), ("y", cy - shapes[i - 1][2] / 2, cy - h / 2),
                                 ("width", shapes[i - 1][1], w), ("height", shapes[i - 1][2], h)):
                sc.key("card", prop, start, round(v0))
                sc.key("card", prop, t, round(v1), ease)
            sc.key("size", "text", t - 300, label)
    sc.key("size", "text", 0, shapes[0][3])
    sc.pop("card", 0, 500, 0.7)
    left = [(200, 330 + i * 110) for i in range(6)]
    right = [(1460, 330 + i * 110) for i in range(6)]
    for i, (label, (x, y)) in enumerate(zip(FORMATS, [p for pair in zip(left, right) for p in pair])):
        name = f"fmt{i}"
        master = label == ".vixl master"
        sc.add(chip(name, label, x, y, size=28, fg=DEEP if master else WHITE, bg=SKY if master else PANEL,
                    font=MONO, width=260, stroke=None if master else LINE))
        sc.pop(name, 900 + i * 300, 380, 0.5)
    return sc


# ----------------------------------------------------------------------------------------------- 10
PILLARS = [("Can my agent drive it?", "Programmable",
            "One operation format for MCP, CLI, Python and REST. 10,000 operations, one undo."),
           ("Can I still change it?", "Editable",
            "Text stays text. Real PowerPoint charts, PDFs people fill in, a master you can rewind."),
           ("Can I trust it?", "Checked",
            "Contrast, spacing, bleed and your own rules, checked before anything ships."),
           ("Where does it run?", "On your machine",
            "Core authoring runs locally. AI providers only when you configure them.")]


def s10_why():
    sc = Scene("10-why", 6000)
    sc.add(backdrop(glow_at=(960, 700), glow2_at=(300, 200)))
    kicker(sc, "06", "WHY VIXL")
    headline(sc, [("Not a picture. ", None), ("A document.", SKY)], t=100)
    for i, (question, title, body) in enumerate(PILLARS):
        x, y = (120 if i % 2 == 0 else 980), (300 if i < 2 else 640)
        name = f"pillar{i}"
        sc.add(rect(f"{name}-bg", x, y, 820, 300, PANEL, 26, LINE),
               text(f"{name}-bar", question, x + 40, y + 36, 26, SKY, MONO),
               text(f"{name}-num", f"0{i + 1}", x + 720, y + 36, 30, MUTED, MONO),
               rich(f"{name}-title", title, x + 40, y + 84, 54, 740, WHITE, HEAD),
               rich(f"{name}-body", body, x + 40, y + 168, 31, 700, MUTED, BODY, line_height=1.3),
               group(name, [f"{name}-bg", f"{name}-bar", f"{name}-num", f"{name}-title", f"{name}-body"]))
        sc.pop(name, 600 + i * 800, 500, 0.85)
        sc.slide(name, 600 + i * 800, dy=40, dur=600)
    return sc


# ----------------------------------------------------------------------------------------------- 11
def s11_end():
    sc = Scene("11-end", 4000)
    sc.add(backdrop(glow_at=(960, 420), glow2_at=(960, 1000)))
    sc.add(glow("pulse", 960, 300, 900, BLUE, "55"))
    ops, names = wordmark("m", 760, 110, 400)
    sc.add(ops, group("logo", names))
    sc.pop("logo", 0, 600, 0.5)
    sc.add(centered("line", [("Ideas become ", None), ("editable.", SKY)], 420, 120))
    sc.words("line", 300, "fade-up", "word", 500, 120)
    sc.add(centered("url", "github.com/jxburros/Vixl", 640, 44, WHITE, MONO))
    sc.fade("url", 1000, dur=400, rise=16)
    sc.add(centered("cta", "A design engine for AI agents. Programmable, editable, checked.", 730, 32, MUTED, SEMI))
    sc.fade("cta", 1300, dur=400, rise=16)
    sc.add(centered("made", "Every frame of this video is an editable Vixl document. Yes, really.", 960, 26, MUTED, BODY))
    sc.fade("made", 1700, dur=500)
    return sc


SCENES = [s01_hook, s02_logo, s03_build, s04_edit, s05_check, s06_graphics, s07_data, s08_art, s09_deliver,
          s10_why, s11_end]
