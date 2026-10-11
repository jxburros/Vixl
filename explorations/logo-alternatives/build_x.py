"""Round two: two Vs that make an X, and reflection concepts where "xl" mirrors "vi".

Run from the repository root: python explorations/logo-alternatives/build_x.py
"""

from build import BLUE, H, INK, OUT, PAPER, SKY, W, centre, contact_sheet, fonts, path, poly, rect, word
from vixl import Project


def x_top(width, h, arm, extend=0.0, cut=0.0, cut_arm=None):
    """The top V of an X that is `width` wide and `2h` tall, made from two straight bars `arm` thick.

    `extend` lets the V run past the waist (for overlaps); `cut` removes the top of one arm
    (`"left"` or `"right"`) so pixels can replace it.
    """
    s = (width - arm) / (2 * h)
    yi = (width - 2 * arm) / (2 * s)  # where the inner edges cross
    yc = h + extend
    left = [(0, 0), (arm, 0)] if cut_arm != "left" else [(s * cut, cut), (arm + s * cut, cut)]
    right = [(width - arm, 0), (width, 0)] if cut_arm != "right" else [(width - arm - s * cut, cut), (width - s * cut, cut)]
    if extend <= 0:
        bottom = [(width - s * yc, yc), (s * yc, yc)]
    else:
        bottom = [((width + arm) / 2, h), (arm + s * yc, yc), (width - arm - s * yc, yc), ((width - arm) / 2, h)]
    return left + [(width / 2, yi)] + right + bottom, s


def rotate(points, width, height):
    """Turn points half a turn inside a width x height box."""
    return [(round(width - x, 2), round(height - y, 2)) for x, y in points]


def pixels(arm_edge, cut, arm, colours):
    """Cells that carry an arm upwards past `cut`, thinning out; `arm_edge(y)` is the arm's left edge."""
    c = arm / 2
    cells = []
    for r, row in enumerate(colours):
        y = cut - (c + 4) * (r + 1)
        for col, (size, colour) in enumerate(row):
            if size:
                x = arm_edge(y + c / 2) + col * (c + 4) + (c - size) / 2
                cells.append((x, y + (c - size) / 2, size, colour))
    return cells


def x_mark(p, x0, y0, width=300, h=150, arm=84, cut_arm="right", shift=(0, 0), seam=0, ends=True):
    """Downward V over an upward V (the same V turned half a turn), with pixel ends."""
    cut = h * 0.42 if ends else 0
    top, s = x_top(width, h, arm, cut=cut, cut_arm=cut_arm if ends else None)
    names = ["Downward V", "Upward V"]
    ops = [path("Downward V", poly(top), x0, y0, INK)]
    bx, by = x0 + shift[0], y0 + shift[1] + seam
    ops.append(path("Upward V", poly(rotate(top, width, 2 * h)), bx, by, BLUE))
    if ends:
        if cut_arm == "right":
            edge = lambda y: width - arm - s * y  # noqa: E731
            rows = [[(arm / 2, INK), (arm / 2, INK)], [(arm / 2 - 8, BLUE), (arm / 2, INK)], [(0, None), (arm / 4, SKY)]]
        else:
            edge = lambda y: s * y  # noqa: E731
            rows = [[(arm / 2, INK), (arm / 2, INK)], [(arm / 2, INK), (arm / 2 - 8, BLUE)], [(arm / 4, SKY), (0, None)]]
        for i, (x, y, size, colour) in enumerate(pixels(edge, cut, arm, rows)):
            ops.append(rect(f"Upper pixel {i + 1}", round(x0 + x, 1), round(y0 + y, 1), size, size, colour))
            rx, ry = width - x - size, 2 * h - y - size
            lower = {INK: BLUE, BLUE: SKY, SKY: BLUE}[colour]
            ops.append(rect(f"Lower pixel {i + 1}", round(bx + rx, 1), round(by + ry, 1), size, size, lower))
            names += [f"Upper pixel {i + 1}", f"Lower pixel {i + 1}"]
    p.apply(ops)
    return names


def lockup(p, mark_names, font=("Inter Tight", 800)):
    f, = fonts(p, font)
    word(p, "Wordmark", "Vixl", f, 230, INK, 560)
    centre(p, mark_names + ["Wordmark"])


def concept_i(p):
    lockup(p, x_mark(p, 120, 100))


def concept_j(p):
    """Overprint X: each V runs past the waist, and the shared diamond is its own colour."""
    width, h, arm, extra = 300, 150, 84, 46
    top, _ = x_top(width, h, arm, extend=extra)
    bottom = [(x, y + 0) for x, y in rotate(top, width, 2 * h)]
    p.apply([
        path("Downward V", poly(top), 120, 100, INK),
        path("Upward V", poly(bottom), 120, 100, BLUE),
        path("Overlap top", poly(top), 120, 100, SKY),
        path("Overlap bottom", poly(bottom), 120, 100, SKY),
    ])
    p.apply([{"type": "pathfinder", "name": "Overlap", "targets": ["Overlap top", "Overlap bottom"], "mode": "intersect"}])
    lockup(p, ["Downward V", "Upward V", "Overlap"])


def concept_k(p):
    """Shifted seam: the blue V slips one pixel sideways across a hairline gap."""
    lockup(p, x_mark(p, 120, 96, shift=(42, 0), seam=8))


def concept_l(p):
    """Half pixel X: concept B's dissolving arm, turned half a turn for the lower V."""
    lockup(p, x_mark(p, 120, 100, cut_arm="left"))


# Geometric letters for the reflection concepts.
T, HX, GAP = 52, 190, 22


def letter_v(x, baseline, h=HX, width=200, arm=66):
    top, _ = x_top(width, h, arm)
    return top, x, baseline - h


def concept_m(p):
    """Reflection wordmark: one mirror line through the x-height; x and l are v and i reflected in it."""
    ops, x, base = [], 150, 330
    axis = base - HX / 2
    v, vx, vy = letter_v(x, base)
    ops.append(path("v", poly(v), vx, vy, INK))
    x += 200 + 34
    ops += [rect("i stem", x, base - HX, T, HX, INK), rect("i dot", x, base - HX - GAP - T, T, T, INK)]
    x += T + 34
    line_from = x - 14
    # x: a v standing on the mirror line, and its reflection hanging below it.
    half, _ = x_top(200, HX / 2, 66)
    ops.append(path("x top (v)", poly(half), x, base - HX, INK))
    ops.append(path("x bottom (reflected v)", poly([(px, HX / 2 - py) for px, py in half]), x, axis, BLUE))
    x += 200 + 34
    # l: the upper part of an i (dot, gap, stem down to the line) and its reflection.
    reach = axis - (base - HX - GAP - T)
    stem = reach - T - GAP
    ops += [
        rect("l dot (i)", x, axis - reach, T, T, INK),
        rect("l stem (i)", x, axis - stem, T, stem, INK),
        rect("l stem (reflected i)", x, axis, T, stem, BLUE),
        rect("l dot (reflected i)", x, axis + stem + GAP, T, T, BLUE),
    ]
    ops.append(rect("Mirror line", line_from, axis - 2, x + T + 14 - line_from, 4, SKY))
    p.apply(ops)
    centre(p, [o["name"] for o in ops])


def concept_n(p):
    """Water reflection: "vi" standing on a line; with its reflection the pair reads as "Xl"."""
    base, x = 248, 120
    v, vx, vy = letter_v(x, base, h=150, width=170, arm=58)
    reflected = [(px, 150 - py) for px, py in v]
    ix = x + 170 + 26
    ops = [
        path("v", poly(v), vx, vy, INK),
        rect("i stem", ix, base - 150, 44, 150, INK),
        rect("i dot", ix, base - 150 - 18 - 44, 44, 44, INK),
        path("v reflection", poly(reflected), vx, base + 4, BLUE),
        rect("i stem reflection", ix, base + 4, 44, 150, BLUE),
        rect("i dot reflection", ix, base + 4 + 150 + 18, 44, 44, BLUE),
    ]
    p.apply(ops)
    lockup(p, [o["name"] for o in ops])


CONCEPTS = [
    ("i-clean-x", "I · Clean X", "Two Vs meet tip to tip; pixel ends turn half a turn", concept_i),
    ("j-overprint-x", "J · Overprint X", "A aligned into a true X; the diamond is the overlap", concept_j),
    ("k-shifted-seam", "K · Shifted seam", "The blue V slips one pixel across a hairline seam", concept_k),
    ("l-half-pixel-x", "L · Half pixel X", "B's dissolving arm, mirrored into an X", concept_l),
    ("m-reflection-wordmark", "M · Reflection", "x = v + its reflection, l = i + its reflection", concept_m),
    ("n-water", "N · Water", "\"vi\" on a waterline; with its reflection it reads \"Xl\"", concept_n),
]


def main():
    made = []
    for slug, label, note, build in CONCEPTS:
        p = Project(W, H, background=PAPER)
        build(p)
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        made.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    contact_sheet(made, name="contact-sheet-x", title="Vixl logo alternatives: round two",
                  subtitle="Two Vs making an X, and \"xl\" as a reflection of \"vi\"")


if __name__ == "__main__":
    main()
