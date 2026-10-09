"""Build alternative Vixl logo concepts as editable .vixl documents plus PNG previews.

Run from the repository root: python explorations/logo-alternatives/build.py
"""

from pathlib import Path

from vixl import Project
from vixl.typefaces import install_font

OUT = Path(__file__).parent / "output"
W, H = 1200, 500
INK, BLUE, SKY, PAPER = "#252B39", "#3575EE", "#6A9AFF", "#FFFFFF"


def fonts(p, *styles):
    return [install_font(p, family, weight)["name"] for family, weight in styles]


def path(name, d, x, y, fill, **extra):
    return {"type": "shape", "shape": "path", "name": name, "path": d, "x": x, "y": y, "fill": fill, **extra}


def rect(name, x, y, w, h, fill, radius=0, **extra):
    shape = "rounded-rectangle" if radius else "rectangle"
    op = {"type": "shape", "shape": shape, "name": name, "x": x, "y": y, "width": w, "height": h, "fill": fill, **extra}
    if radius:
        op["radius"] = radius
    return op


def poly(points):
    head, *rest = points
    return f"M{head[0]} {head[1]} " + " ".join(f"L{x} {y}" for x, y in rest) + " Z"


def word(p, name, text, font, size, color, left, mid_y=H / 2):
    """Place text with its ink box starting at `left` and vertically centred on `mid_y`."""
    p.apply([{"type": "text", "name": name, "text": text, "font": font, "size": size, "color": color, "x": 0, "y": 0}])
    ink = p.inspect(name)["ink_bounds"]
    p.apply([{"type": "move", "target": name, "x": left - ink[0], "y": mid_y - ink[3] / 2 - ink[1]}])
    ink = p.inspect(name)["ink_bounds"]
    return ink[0] + ink[2]


def centre(p, names, bg_w=W):
    """Shift everything horizontally so the lockup sits centred on the canvas."""
    boxes = [p.inspect(n).get("ink_bounds") or p.inspect(n)["canvas_bounds"] for n in names]
    left = min(b[0] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    dx = round((bg_w - (right - left)) / 2 - left, 1)
    for n in names:
        layer = p.inspect(n)
        p.apply([{"type": "move", "target": n, "x": layer["x"] + dx, "y": layer["y"]}])


def v_chevron(width, height, arm):
    """A downward V with arms `arm` px thick measured horizontally."""
    half = width / 2
    inner = height * (half - arm) / half
    return [(0, 0), (arm, 0), (half, inner), (width - arm, 0), (width, 0), (half + arm / 2, height), (half - arm / 2, height)]


def concept_a(p):
    """Overprint: two identical solid Vs, offset; the overlap is its own colour (two layers, one blend)."""
    f, = fonts(p, ("Inter Tight", 800))
    up = v_chevron(250, 200, 74)
    down = [(x, 200 - y) for x, y in up]
    p.apply([
        path("Downward V", poly(up), 120, 105, INK),
        path("Upward V", poly(down), 190, 195, BLUE),
        # Pathfinder takes the first operand's fill and hides its operands, so it gets its own copies.
        path("Overlap top", poly(up), 120, 105, SKY),
        path("Overlap bottom", poly(down), 190, 195, SKY),
    ])
    p.apply([{"type": "pathfinder", "name": "Overlap", "targets": ["Overlap top", "Overlap bottom"], "mode": "intersect"}])
    word(p, "Wordmark", "Vixl", f, 230, INK, 560)
    centre(p, ["Downward V", "Upward V", "Overlap", "Wordmark"])


def concept_b(p):
    """One V, not an X: the left arm's top dissolves into pixels, the rest stays a clean vector."""
    f, = fonts(p, ("Inter Tight", 800))
    arm, height, width = 80, 260, 300
    half = width / 2
    inner_h = height * (half - arm) / half

    def outer(y):  # left edge of the left arm at height y
        return y * (half - arm / 2) / height

    def inner(y):  # right edge of the left arm at height y
        return arm + y * (half - arm) / inner_h

    cut = 120  # the left arm is solid below this height
    body = [(outer(cut), cut), (inner(cut), cut), (half, inner_h), (width - arm, 0), (width, 0),
            (half + arm / 2, height), (half - arm / 2, height)]
    ops = [path("V", poly(body), 110, 120, INK)]
    # Rows of cells continue the arm upwards on a 40 px grid, thinning out as they leave the letter.
    rows = [[(0, 36, INK), (1, 36, INK)], [(0, 30, BLUE), (1, 36, INK)], [(0, 22, BLUE), (1, 16, SKY)]]
    for r, cells in enumerate(rows):
        y = cut - 40 * (r + 1)
        for col, size, colour in cells:
            x = outer(y + 20) + col * 40 + (36 - size) / 2
            ops.append(rect(f"Pixel {r + 1}-{col + 1}", round(110 + x, 1), round(120 + y + 2 + (36 - size) / 2, 1), size, size, colour))
    p.apply(ops)
    word(p, "Wordmark", "Vixl", f, 230, INK, 560)
    centre(p, [o["name"] for o in ops] + ["Wordmark"])


def concept_c(p):
    """A V built from stacked layer bars that shorten downwards: the layer stack is the letter."""
    f, = fonts(p, ("Space Grotesk", 700))
    bars, ops = [(260, BLUE), (196, "#2F5FC4"), (132, "#2A4589"), (68, INK)], []
    y = 112
    for i, (w, colour) in enumerate(bars):
        ops.append(rect(f"Layer {i + 1}", 250 - w / 2, y, w, 52, colour, radius=14))
        y += 52 + 14
    p.apply(ops)
    word(p, "Wordmark", "vixl", f, 250, INK, 450)
    centre(p, [o["name"] for o in ops] + ["Wordmark"])


def concept_d(p):
    """The V as a selected vector path: anchor squares and Bezier handles, a design-tool signature."""
    f, = fonts(p, ("Geist", 700))
    pts = [(130, 140), (240, 360), (350, 140)]
    ops = [{"type": "shape", "shape": "path", "name": "V stroke",
            "path": "M130 140 C175 230 205 330 240 360 C275 330 305 230 350 140",
            "x": 0, "y": 0, "stroke": INK, "stroke_width": 30, "line_cap": "round"}]
    for i, (hx, hy, ax, ay) in enumerate([(175, 230, 130, 140), (305, 230, 350, 140)]):
        ops.append({"type": "shape", "shape": "path", "name": f"Handle line {i + 1}", "path": f"M{ax} {ay} L{hx} {hy}",
                    "x": 0, "y": 0, "stroke": BLUE, "stroke_width": 5})
        ops.append({"type": "shape", "shape": "ellipse", "name": f"Handle {i + 1}", "x": hx - 12, "y": hy - 12,
                    "width": 24, "height": 24, "fill": PAPER, "stroke": BLUE, "stroke_width": 5})
    for i, (x, y) in enumerate(pts):
        ops.append(rect(f"Anchor {i + 1}", x - 17, y - 17, 34, 34, BLUE if i == 1 else PAPER, stroke=BLUE, stroke_width=6))
    p.apply(ops)
    word(p, "Wordmark", "vixl", f, 240, INK, 450)
    centre(p, [o["name"] for o in ops] + ["Wordmark"])


def concept_e(p):
    """Agent-first: a terminal prompt wordmark with a block cursor."""
    mono, = fonts(p, ("JetBrains Mono", 800))
    p.apply([path("Prompt", poly([(0, 0), (34, 0), (96, 62), (34, 124), (0, 124), (62, 62)]), 0, H / 2 - 62, BLUE)])
    end = word(p, "Wordmark", "vixl", mono, 220, INK, 140)
    p.apply([rect("Cursor", end + 26, H / 2 - 70, 64, 140, BLUE)])
    centre(p, ["Prompt", "Wordmark", "Cursor"])


def concept_f(p):
    """App-tile monogram: a white V cut from a charcoal tile, one blue pixel jumping out of the corner."""
    f, = fonts(p, ("Unbounded", 800))
    ops = [
        rect("Tile", 100, 70, 360, 360, INK, radius=84),
        path("V", poly(v_chevron(220, 200, 76)), 170, 150, PAPER),
        rect("Pixel", 400, 40, 70, 70, BLUE),
    ]
    p.apply(ops)
    word(p, "Wordmark", "vixl", f, 170, INK, 530)
    centre(p, ["Tile", "V", "Pixel", "Wordmark"])


def concept_g(p):
    """Wordmark only: the i-dot is a blue pixel and the x is two offset strokes in two colours."""
    f, = fonts(p, ("Space Grotesk", 700))
    size = 300
    end = word(p, "Vi", "vı", f, size, INK, 200, mid_y=275)
    vi = p.inspect("Vi")["ink_bounds"]
    stem_right = end
    x_h = vi[3]
    top, bottom = vi[1], vi[1] + vi[3]
    p.apply([rect("Dot", stem_right - 46, top - 82, 46, 46, BLUE)])
    w, t = 150, 46
    left = end + 24
    p.apply([
        path("X down", poly([(0, 0), (t * 1.15, 0), (w, x_h), (w - t * 1.15, x_h)]), left, top, INK),
        path("X up", poly([(w - t * 1.15, 0), (w, 0), (t * 1.15, x_h), (0, x_h)]), left + 14, top - 14, BLUE),
    ])
    word(p, "L", "l", f, size, INK, left + w + 40, mid_y=None or 275)
    l_ink = p.inspect("L")["ink_bounds"]
    p.apply([{"type": "move", "target": "L", "x": p.inspect("L")["x"], "y": p.inspect("L")["y"] + bottom - (l_ink[1] + l_ink[3])}])
    centre(p, ["Vi", "Dot", "X down", "X up", "L"])


def concept_h(p):
    """Editorial: a high-contrast serif wordmark with a pixel full stop, for a calmer, crafted tone."""
    serif, = fonts(p, ("Fraunces", 900))
    end = word(p, "Wordmark", "Vixl", serif, 260, INK, 300)
    base = p.inspect("Wordmark")["ink_bounds"]
    p.apply([rect("Full stop", end + 18, base[1] + base[3] - 52, 52, 52, BLUE)])
    centre(p, ["Wordmark", "Full stop"])


CONCEPTS = [
    ("a-overprint", "A · Overprint", "Same paired-V idea, solid shapes; the overlap shows layering", concept_a),
    ("b-half-pixel", "B · Half pixel", "One clear V: pixels on one arm, vector on the other", concept_b),
    ("c-layer-stack", "C · Layer stack", "Layer bars stacked into a V", concept_c),
    ("d-bezier", "D · Bezier", "The V as an editable path with anchors and handles", concept_d),
    ("e-prompt", "E · Prompt", "Terminal prompt for an agent-first tool", concept_e),
    ("f-tile", "F · Tile", "App-icon monogram that scales down to a favicon", concept_f),
    ("g-wordmark", "G · Wordmark", "Custom letters: pixel i-dot, two-layer x", concept_g),
    ("h-editorial", "H · Editorial", "Serif wordmark with a pixel full stop", concept_h),
]


def contact_sheet(made, name="contact-sheet", title="Vixl logo alternatives",
                  subtitle="Eight directions, each an editable .vixl document"):
    cols, cw, ch, gap, pad, head = 2, 900, 375, 40, 70, 190
    rows = (len(made) + cols - 1) // cols
    sheet = Project(pad * 2 + cols * cw + (cols - 1) * gap, head + rows * (ch + 80 + gap) + pad - gap, background="#F3F2EE")
    bold, body = fonts(sheet, ("Inter Tight", 800), ("Inter", 400))
    sheet.apply([
        {"type": "text", "name": "Title", "text": title, "font": bold, "size": 64, "color": INK, "x": pad, "y": 60},
        {"type": "text", "name": "Subtitle", "text": subtitle, "font": body,
         "size": 30, "color": "#6B7080", "x": pad, "y": 140},
    ])
    for i, (slug, label, note, png) in enumerate(made):
        x = pad + (i % cols) * (cw + gap)
        y = head + 40 + (i // cols) * (ch + 80 + gap)
        sheet.apply([
            rect(f"Card {slug}", x, y, cw, ch + 80, PAPER, radius=24),
            {"type": "add", "path": str(png), "name": f"Logo {slug}", "x": x, "y": y + 50},
            {"type": "resize", "target": f"Logo {slug}", "width": cw, "height": ch},
            {"type": "text", "name": f"Label {slug}", "text": label, "font": bold, "size": 28, "color": INK, "x": x + 30, "y": y + 26},
            {"type": "text", "name": f"Note {slug}", "text": note, "font": body, "size": 22, "color": "#6B7080",
             "x": x + 30, "y": y + ch + 30},
        ])
    sheet.save(str(OUT / f"{name}.vixl"), overwrite=True)
    sheet.export(str(OUT / f"{name}.png"), overwrite=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for slug, label, note, build in CONCEPTS:
        p = Project(W, H, background=PAPER)
        build(p)
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        made.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    contact_sheet(made)


if __name__ == "__main__":
    main()
