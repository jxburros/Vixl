"""Round three: refinements of the reflection wordmark (concept M).

The x is a v standing on its own reflection. M's l (an i over an upside-down i) kept the i's detached
dot, so it read as a second i ("vixi"); these variants keep the l one solid stroke.

Run from the repository root: PYTHONPATH=explorations/logo-alternatives python explorations/logo-alternatives/build_m.py
"""

import math

from build import BLUE, H, INK, OUT, PAPER, SKY, W, contact_sheet, path, poly, rect
from build_x import x_top
from vixl import Project


def arm_for(stroke, width, run_height):
    """Horizontal arm width that gives a diagonal bar `stroke` px thick across `width` x `run_height`."""
    arm = stroke
    for _ in range(20):
        arm = stroke * math.hypot(1, (width - arm) / run_height)
    return arm


def mirrored(points, axis_height):
    return [(x, axis_height - y) for x, y in points]


def wordmark(p, *, stroke=52, xh=190, gap=22, space=34, ink=INK, reflection=BLUE, reflection_opacity=1.0,
             l_mode="reflect", seam=0, horizon=None, l_gap=None, vw=200, xw=190):
    """Lay out v, i, x, l on one baseline and return the layer names.

    l_mode: "plain" (one stem), "split" (one stem cut at the x's waterline), "up" (the i's stem with its
    reflection above it), "reflect" (half-height i over its reflection) or "joined" (an i whose reflection
    closes the dot's gap). "reflect" and "joined" keep a detached cap, so the l reads as a second i.
    """
    base = 0
    ops, x = [], 0
    v_arm = arm_for(stroke, vw, 2 * xh)
    v, _ = x_top(vw, xh, v_arm)
    ops.append(path("v", poly(v), x, base - xh, ink))
    x += vw + space
    ops += [rect("i stem", x, base - xh, stroke, xh, ink), rect("i dot", x, base - xh - gap - stroke, stroke, stroke, ink)]
    x += stroke + space

    # x: a half-height v on the x-height midline, and its reflection under it.
    axis = base - xh / 2
    x_arm = arm_for(stroke, xw, xh)
    hh = (xh - seam) / 2  # each half; a seam is cut out of the middle, never added below the baseline
    half, _ = x_top(xw, hh, x_arm)
    extra = {"opacity": reflection_opacity} if reflection_opacity < 1 else {}
    ops.append(path("x (v)", poly(half), x, base - xh, ink))
    ops.append(path("x (reflected v)", poly(mirrored(half, hh)), x, base - hh, reflection, **extra))
    x_left = x
    x += xw + space

    full = xh + gap + stroke  # height of the i, dot included
    if l_mode == "plain":
        ops.append(rect("l", x, base - full, stroke, full, ink))
    elif l_mode == "split":
        # Cut at the same waterline as the x: everything under it is reflection.
        ops += [rect("l (above)", x, base - full, stroke, full - xh / 2 - seam / 2, ink),
                rect("l (reflection)", x, axis + seam / 2, stroke, xh / 2 - seam / 2, reflection, **extra)]
    elif l_mode == "up":
        # The i's stem reflected upwards from the x-height, cropped at the dot's height.
        ops += [rect("l (i stem)", x, base - xh, stroke, xh, ink),
                rect("l (reflected stem)", x, base - full, stroke, full - xh - seam, reflection, **extra)]
    elif l_mode == "joined":
        # The i on top; its reflection fills the gap under the dot, so the l reads solid.
        lg = gap if l_gap is None else l_gap
        ops += [rect("l dot (i)", x, base - full, stroke, stroke, ink),
                rect("l (reflected i)", x, base - full + stroke + lg, stroke, full - stroke - lg, reflection, **extra)]
    else:
        lg = gap if l_gap is None else l_gap
        l_axis = base - full / 2
        stem = full / 2 - stroke - lg
        ops += [
            rect("l dot (i)", x, base - full, stroke, stroke, ink),
            rect("l stem (i)", x, l_axis - stem, stroke, stem, ink),
            rect("l stem (reflected i)", x, l_axis + seam, stroke, stem, reflection, **extra),
            rect("l dot (reflected i)", x, l_axis + seam + stem + lg, stroke, stroke, reflection, **extra),
        ]
    x += stroke
    if horizon:
        ops.insert(0, rect("Horizon", x_left - space / 2, axis - horizon / 2, x - x_left + space, horizon, SKY))
    # Centre the word on the canvas by optical height (x-height plus the dot).
    dx, dy = (W - x) / 2, H / 2 + (xh + gap + stroke) / 2
    for op in ops:
        op["x"] = round(op["x"] + dx, 1)
        op["y"] = round(op["y"] + dy, 1)
    p.apply(ops)
    return [op["name"] for op in ops]


VARIANTS = [
    ("m2-x-only", "M2 · Only the x", "The reflection lives in one letter; the l is a plain stem",
     {"l_mode": "plain"}),
    ("m7-waterline", "M7 · Waterline", "x and l share one waterline; everything under it is reflection",
     {"l_mode": "split"}),
    ("m8-seam", "M8 · Seam", "One colour; a hairline cut along the waterline is the mirror",
     {"l_mode": "split", "reflection": INK, "seam": 8}),
    ("m9-both-ways", "M9 · Both ways", "v reflects down into x; i's stem reflects up into l",
     {"l_mode": "up"}),
    ("m10-ghost", "M10 · Ghost", "Waterline with a faint reflection in the same ink",
     {"l_mode": "split", "reflection": INK, "reflection_opacity": 0.38}),
    ("m11-light", "M11 · Lighter", "Waterline with thinner strokes and more air",
     {"l_mode": "split", "stroke": 38, "space": 40, "gap": 18}),
]


def main():
    made = []
    for slug, label, note, options in VARIANTS:
        p = Project(W, H, background=PAPER)
        wordmark(p, **options)
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        made.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    contact_sheet(made, name="contact-sheet-m", title="Vixl logo alternatives: refining M",
                  subtitle="x is a v over its reflection; the l stays one solid stroke")


if __name__ == "__main__":
    main()
