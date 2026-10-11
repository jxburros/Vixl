"""Round six: R2 pushed further. Exaggerated and deviant takes on the rippling reflection.

Run from the repository root: PYTHONPATH=explorations/logo-alternatives python explorations/logo-alternatives/build_t.py
"""

import math
import re

from build import BLUE, H, INK, OUT, PAPER, SKY, W, contact_sheet, path, poly
from build_m import wordmark
from build_r import clip
from vixl import Project
from vixl.timeline import export_timeline

PALE = "#A9C4FF"
MID = "#5B8FF5"
FAINT = "#D4E2FF"


def pts(points):
    return poly([(round(px, 2), round(py, 2)) for px, py in points])


def sliced(bands, shift, colour, stretch=1.0):
    """A reflect hook: stretch the reflection downwards, cut it into `bands` (pairs of 0-1 fractions of
    its height) and offset each band by shift(i) in its colour(i)."""
    def draw(name, points, x, y, fill, extra):
        height = max(py for _, py in points)
        tall = [(px, py * stretch) for px, py in points]
        ops = []
        for i, (f0, f1) in enumerate(bands):
            part = clip(tall, f0 * height * stretch, f1 * height * stretch)
            if len(part) >= 3:
                ops.append(path(f"{name} band {i + 1}", pts(part), x + shift(i), y, colour(i), **extra))
        return ops
    return draw


def even_bands(count, fill=0.62):
    """`count` equal slots from top to bottom, each `fill` inked and the rest gap."""
    step = 1 / count
    return [(i * step, i * step + step * fill) for i in range(count)]


def outlines(p, names):
    """Each layer as an absolute polygon (paths from their points, rectangles from their box)."""
    shapes = []
    for name in names:
        layer = p.inspect(name)
        x0, y0 = layer["x"], layer["y"]
        if layer.get("path"):
            nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", layer["path"])]
            shapes.append([(x0 + a, y0 + b) for a, b in zip(nums[::2], nums[1::2])])
        else:
            w, h = layer["width"], layer["height"]
            shapes.append([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)])
    return shapes


# T1 · Storm: many thin bands, big alternating drift.
storm = sliced(even_bands(7, 0.55), lambda i: [0, 16, -14, 22, -18, 26, -10][i],
               lambda i: [BLUE, BLUE, MID, MID, SKY, SKY, PALE][i])

# T2 · Long reflection: the reflection hangs twice as deep as the letter above it, rippling as it goes.
long_reflection = sliced(even_bands(8, 0.58), lambda i: [0, 4, -5, 7, -8, 10, -10, 12][i],
                         lambda i: [BLUE, BLUE, MID, MID, SKY, SKY, PALE, FAINT][i], stretch=2.2)

# T4 · Liquid: fourteen hairline slices that follow a sine wave, as if the water were bending the light.
liquid = sliced(even_bands(14, 0.72), lambda i: (2 + 1.1 * i) * math.sin(i * 0.9),
                lambda i: [BLUE, MID, SKY, PALE][min(i // 4, 3)])

# T5 · Glitch: digital tearing instead of water; slices jump sideways, and a few double up.
GLITCH_SHIFTS = [0, 24, -6, 38, -20, 10]


def glitch(name, points, x, y, fill, extra):
    height = max(py for _, py in points)
    ops = []
    for i, (f0, f1) in enumerate(even_bands(6, 0.8)):
        part = clip(points, f0 * height, f1 * height)
        if len(part) < 3:
            continue
        if i in (1, 3):  # a displaced ghost behind the slice, the way a torn scanline doubles
            ops.append(path(f"{name} ghost {i + 1}", pts(part), x + GLITCH_SHIFTS[i] - 30, y, PALE, **extra))
        ops.append(path(f"{name} band {i + 1}", pts(part), x + GLITCH_SHIFTS[i], y,
                        [BLUE, BLUE, INK, MID, BLUE, SKY][i], **extra))
    return ops


def whole_word(p, names, squash=0.6, gap=10):
    """T3: the entire word reflected under the baseline as rippling bands; xl was already a reflection,
    so the water repeats the trick for the whole name."""
    shapes = outlines(p, names)
    base = max(py for shape in shapes for _, py in shape)
    depth = (base - min(py for shape in shapes for _, py in shape)) * squash
    count = 9
    ops = []
    for k in range(count):
        y0 = base + gap + depth * k / count
        y1 = y0 + depth / count * (0.7 - 0.04 * k)
        shift = [0, 6, -6, 9, -9, 12, -12, 14, -14][k]
        colour = [MID, MID, SKY, SKY, PALE, PALE, FAINT, FAINT, FAINT][k]
        for j, shape in enumerate(shapes):
            mirrored = [(px, base + gap + (base - py) * squash) for px, py in shape]
            part = clip(mirrored, y0, y1)
            if len(part) >= 3:
                ops.append(path(f"Water {k + 1}-{j + 1}", pts(part), shift, 0, colour))
    p.apply(ops)


def drop_rings(p):
    """T6: a drop has just hit the water at the x's waist; rings spread along the waterline behind the word."""
    x_top = p.inspect("x (v)")
    cx = x_top["x"] + x_top["width"] / 2
    cy = x_top["y"] + x_top["height"]
    ops = []
    for i, (w, h, stroke, colour) in enumerate([(150, 22, 6, SKY), (330, 46, 5, PALE), (560, 74, 4, FAINT),
                                                 (840, 104, 3, FAINT)]):
        ops.append({"type": "shape", "shape": "ellipse", "name": f"Ring {i + 1}", "x": cx - w / 2, "y": cy - h / 2,
                    "width": w, "height": h, "fill": "none", "stroke": colour, "stroke_width": stroke})
    p.apply(ops)
    for i in range(4):
        p.apply([{"type": "bottom", "target": f"Ring {i + 1}"}])


def build(slug, options=None, after=None):
    p = Project(W, H, background=PAPER)
    names = wordmark(p, l_mode="split", **(options or {}))
    if after:
        after(p, names)
    return p


def moving_storm():
    """T7: the storm, animated. Every band swings on its own phase, the deeper ones further."""
    still = sliced(even_bands(7, 0.55), lambda i: 0, lambda i: [BLUE, BLUE, MID, MID, SKY, SKY, PALE][i])
    p = Project(W, H, background=PAPER)
    names = wordmark(p, l_mode="split", reflect=still)
    ops = [{"type": "timeline-set", "duration": 1600, "loop_mode": "seamless"}]
    for name in names:
        if " band " in name:
            i = int(name.rsplit(" ", 1)[1]) - 1
            if i:
                ops.append({"type": "keyframes", "target": name, "property": "translate-x",
                            "sample": {"fn": "sin", "period": 1600, "amplitude": 4 + 3.4 * i, "offset": 0,
                                       "phase": 0.37 * i, "samples": 32, "duration": 1600}})
    p.apply(ops)
    return p


VARIANTS = [
    ("t1-storm", "T1 · Storm", "Seven thin bands thrown far sideways", dict(reflect=storm)),
    ("t2-long", "T2 · Long reflection", "The reflection hangs twice as deep as the letter",
     dict(reflect=long_reflection, bounds=(0, 0, -264, 110))),
    ("t3-whole-word", "T3 · Whole word", "The whole name reflected in rippling water below",
     dict(reflect=sliced(even_bands(4, 0.7), lambda i: [0, 6, -5, 4][i], lambda i: [BLUE, BLUE, MID, SKY][i]),
          bounds=(0, 0, -264, 175)),
     lambda p, names: whole_word(p, names)),
    ("t4-liquid", "T4 · Liquid", "Hairline slices bent by a wave", dict(reflect=liquid)),
    ("t5-glitch", "T5 · Glitch", "Digital tearing instead of water: slices jump and double", dict(reflect=glitch)),
    ("t6-drop", "T6 · Drop", "A drop hits the waterline at the x; rings spread behind the word",
     dict(reflect=sliced(even_bands(4, 0.7), lambda i: [0, 6, -5, 4][i], lambda i: [BLUE, BLUE, MID, SKY][i])),
     lambda p, names: drop_rings(p)),
]


def main():
    made = []
    for slug, label, note, options, *after in VARIANTS:
        p = build(slug, options, after[0] if after else None)
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        made.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    p = moving_storm()
    p.save(str(OUT / "t7-moving-storm.vixl"), overwrite=True)
    p.export(str(OUT / "t7-moving-storm.png"), overwrite=True)
    export_timeline(p, str(OUT / "t7-moving-storm.gif"), fps=24, overwrite=True)
    made.append(("t7-moving-storm", "T7 · Moving storm", "Animated storm (see t7-moving-storm.gif)",
                 OUT / "t7-moving-storm.png"))
    print("built t7-moving-storm")
    contact_sheet(made, name="contact-sheet-t", title="R2, exaggerated",
                  subtitle="Pushing the ripple further, and a few deviant takes")


if __name__ == "__main__":
    main()
