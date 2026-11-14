"""Draws ``wrap-template.png``: a made-up print-on-demand hardcover wrap template (back, spine, front).

Run ``python tests/fixtures/print/make_template.py`` to regenerate the committed PNG. ``draw`` is also imported by
``tests/test_print_templates.py`` for the variants it builds on the fly (another size, solid lines, a PSD).

Magenta dashes: the board (trim) edge. Green dashes: the safe area of each cover, the back one with a barcode notch
cut out of its bottom edge. Red dashes: the barcode keep-out. Cyan dashes: the two spine folds. The lettering is in
the line colours on purpose: an import must not read it as lines.
"""

from pathlib import Path

from PIL import Image, ImageDraw

TRIM, SAFE, KEEP_OUT, FOLD = "#ff00ff", "#00a651", "#ed1c24", "#00aeef"
SIZE = (1000, 400)
BOARD = (10, 10, 990, 390)
BACK = [(40, 40), (440, 40), (440, 360), (300, 360), (300, 280), (180, 280), (180, 360), (40, 360)]
FRONT = (560, 40, 960, 360)
BARCODE = (195, 295, 285, 350)
FOLDS = (480, 520)


def _dashed(draw, start, end, fill, scale, dash, width):
    (x0, y0), (x1, y1) = start, end
    length = max(abs(x1 - x0), abs(y1 - y0))
    steps = range(0, int(length) + 1, 2 * dash) if dash else [0]
    for offset in steps:
        stop = min(offset + dash, length) if dash else length
        if x0 == x1:
            low, high = sorted((y0, y1))
            box = (x0, low + offset, x0, low + stop)
        else:
            low, high = sorted((x0, x1))
            box = (low + offset, y0, low + stop, y0)
        draw.line([c * scale for c in box], fill=fill, width=width)


def draw(scale=1, dash=6, width=2, lettering=True):
    """The template at ``scale``; ``dash`` 0 draws solid lines."""
    image = Image.new("RGB", (SIZE[0] * scale, SIZE[1] * scale), "white")
    pen = ImageDraw.Draw(image)

    def outline(points, fill):
        for a, b in zip(points, points[1:] + points[:1]):
            _dashed(pen, a, b, fill, scale, dash, width)

    def box(rect):
        left, top, right, bottom = rect
        return [(left, top), (right, top), (right, bottom), (left, bottom)]

    outline(box(BOARD), TRIM)
    outline(BACK, SAFE)
    outline(box(FRONT), SAFE)
    outline(box(BARCODE), KEEP_OUT)
    for x in FOLDS:
        _dashed(pen, (x, 0), (x, SIZE[1] - 1), FOLD, scale, dash, width)
    if lettering:
        pen.text((600 * scale, 60 * scale), "SAFE AREA - FRONT COVER", fill=SAFE)
        pen.text((60 * scale, 60 * scale), "SAFE AREA - BACK COVER", fill=SAFE)
        pen.text((198 * scale, 366 * scale), "BARCODE", fill=KEEP_OUT)
        pen.text((560 * scale, 18 * scale), "TRIM", fill=TRIM)
    return image


if __name__ == "__main__":
    draw().save(Path(__file__).with_name("wrap-template.png"), optimize=True)
