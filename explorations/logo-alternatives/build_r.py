"""Round four: M7 (waterline) with a reflection that does more than change colour.

Above the waterline the letters are clean vectors; below it the reflection carries Vixl's other half:
pixels, ripples, scanlines or a shift.

Run from the repository root: PYTHONPATH=explorations/logo-alternatives python explorations/logo-alternatives/build_r.py
"""

from build import BLUE, H, INK, OUT, PAPER, SKY, W, contact_sheet, path, poly, rect
from build_m import wordmark
from vixl import Project

PALE = "#A9C4FF"


def inside(points, px, py):
    hit = False
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def clip(points, y0, y1):
    """The part of a polygon between two horizontal lines (Sutherland-Hodgman, twice)."""
    def cut(pts, keep, edge):
        out = []
        for a, b in zip(pts, pts[1:] + pts[:1]):
            ia, ib = keep(a), keep(b)
            if ia:
                out.append(a)
            if ia != ib:
                t = (edge - a[1]) / (b[1] - a[1])
                out.append((a[0] + t * (b[0] - a[0]), edge))
        return out
    pts = cut(points, lambda q: q[1] >= y0, y0)
    return cut(pts, lambda q: q[1] <= y1, y1) if pts else []


def pixel_tail(cell=11, rows=3, gap=4, colours=("#5B8FF5", SKY, PALE)):
    """Keep the reflection a crisp vector and let it run out into pixels under the baseline.

    Pixelating the reflection itself fills the thin notch between the x's legs, so the x stops reading.
    """
    def draw(name, points, x, y, fill, extra):
        height = max(py for _, py in points)
        width = max(px for px, _ in points)
        ops = [path(name, poly(points), x, y, fill, **extra)]
        cols = int(width // cell)
        pad = (width - cols * cell) / 2
        for r in range(rows):
            size = cell - 3 - 2 * r
            top = y + height + gap + r * cell
            for c in range(cols):
                cx = pad + (c + 0.5) * cell
                # Only under ink, and fewer cells per row the further down.
                if inside(points, cx, height - 0.5) and (c + r) % (r + 1) == 0:
                    ops.append(rect(f"{name} px {r}-{c}", round(x + cx - size / 2, 1), round(top + (cell - size) / 2, 1),
                                    size, size, colours[min(r, len(colours) - 1)], **extra))
        return ops
    return draw


def ripple_reflection(bands=((0, 30), (34, 54), (60, 74), (82, 90)), shifts=(0, 6, -5, 4),
                      colours=(BLUE, BLUE, "#5B8FF5", SKY), scale_to=95):
    """Slice the reflection into bands that thin out and drift, like a reflection on moving water."""
    def draw(name, points, x, y, fill, extra):
        height = max(py for _, py in points)
        k = height / scale_to
        ops = []
        for i, ((y0, y1), dx, colour) in enumerate(zip(bands, shifts, colours)):
            part = clip(points, y0 * k, y1 * k)
            if len(part) >= 3:
                ops.append(path(f"{name} band {i + 1}", poly([(round(px, 2), round(py, 2)) for px, py in part]),
                                x + dx, y, colour, **extra))
        return ops
    return draw


def scanline_reflection(lines=7, colours=(BLUE,)):
    """The reflection as scanlines that get thinner towards the bottom."""
    def draw(name, points, x, y, fill, extra):
        height = max(py for _, py in points)
        pitch = height / lines
        ops = []
        for i in range(lines):
            thick = pitch * (0.78 - 0.08 * i)
            part = clip(points, i * pitch, i * pitch + thick)
            if len(part) >= 3:
                ops.append(path(f"{name} line {i + 1}", poly([(round(px, 2), round(py, 2)) for px, py in part]),
                                x, y, colours[i % len(colours)], **extra))
        return ops
    return draw


def shifted_reflection(dx=14):
    """The reflection slips sideways, the misregistration of the original Digital Shift mark."""
    def draw(name, points, x, y, fill, extra):
        return [path(name, poly(points), x + dx, y, fill, **extra)]
    return draw


def symbol(p, left, top, size=300, ink=INK, colour=BLUE, name="Symbol"):
    """A big x: a v above the waterline, its pixel reflection below."""
    from build_m import arm_for, mirrored
    from build_x import x_top
    hh = size / 2
    arm = arm_for(78, size, size)
    half, _ = x_top(size, hh, arm)
    ops = [path(f"{name} v", poly(half), left, top, ink)]
    ops += pixel_tail(cell=17, gap=6)(f"{name} reflection", mirrored(half, hh), left, top + hh, colour, {})
    p.apply(ops)


VARIANTS = [
    ("r1-pixel", "R1 · Pixel tail", "The reflection runs out into pixels under the baseline",
     dict(l_mode="split", reflect=pixel_tail(), bounds=(0, 0, -264, 40))),
    ("r2-ripple", "R2 · Ripple", "The reflection breaks into drifting bands, like water",
     dict(l_mode="split", reflect=ripple_reflection())),
    ("r3-scanlines", "R3 · Scanlines", "The reflection is drawn in thinning scanlines",
     dict(l_mode="split", reflect=scanline_reflection())),
    ("r4-shift", "R4 · Shift", "The reflection slips one pixel sideways, a nod to Digital Shift",
     dict(l_mode="split", reflect=shifted_reflection())),
]


def main():
    made = []
    for slug, label, note, options in VARIANTS:
        p = Project(W, H, background=PAPER)
        wordmark(p, **options)
        made.append((slug, label, note, p))
    # R5: symbol and wordmark lockup.
    p = Project(W, H, background=PAPER)
    wordmark(p, l_mode="split", reflect=pixel_tail(cell=9, gap=3), stroke=40, xh=150, gap=18, space=28,
             vw=158, xw=150, bounds=(-330, 0, -208, 30))
    symbol(p, 175, H / 2 - 170, size=280)
    made.append(("r5-lockup", "R5 · Symbol + wordmark", "The x on its own becomes the symbol and favicon", p))
    # R6: the pixel version reversed out of charcoal.
    p = Project(W, H, background=INK)
    wordmark(p, l_mode="split", ink=PAPER, reflection=SKY, reflect=pixel_tail(colours=(SKY, "#4F6FB5", "#3A5288")), bounds=(0, 0, -264, 40))
    made.append(("r6-dark", "R6 · On dark", "R1 reversed: white letters, light-blue reflection and pixels", p))

    sheet = []
    for slug, label, note, p in made:
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        sheet.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    contact_sheet(sheet, name="contact-sheet-r", title="Vixl logo alternatives: M7, and more",
                  subtitle="Vector letters above the waterline; the reflection below carries the pixels")


if __name__ == "__main__":
    main()
