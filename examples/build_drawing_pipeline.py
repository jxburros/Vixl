"""Rebuild docs/drawing-pipeline.png: a photographed sketch, cleaned, finished and compared.

Run from the repository root: python examples/build_drawing_pipeline.py [--output DIR]
Offline and deterministic. The "photo" is synthesized here with a fixed seed (pen lines with a
gentle wobble, a gap at the floor corner and in the ground line, dust, uneven light and paper
grain), so no fixture or camera is needed. Writes DIR/drawing-pipeline.png (default docs/).
"""

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project, __version__, drawing
from vixl.assets import add_image

PANEL_W, PANEL_H = 640, 480
BACKDROP = "#ecebf0"
INK = "#1d1d1f"


def sketch_photo(seed=17):
    """A phone photo of a pen sketch: house with door and window, hills, sun and ground."""
    rng = np.random.default_rng(seed)
    w, h = PANEL_W, PANEL_H
    ink = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(ink)

    def line(points, width=3, jitter=0.7):
        noise = rng.normal(0, jitter * 2.2, (len(points) + 8, 2))
        noise = np.array([noise[i:i + 9].mean(0) for i in range(len(points))])  # a steady hand
        draw.line([(x + dx, y + dy) for (x, y), (dx, dy) in zip(points, noise)], fill=255, width=width,
                  joint="curve")

    def along(corners, steps=24):
        out = []
        for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
            out += [(x0 + (x1 - x0) * t / steps, y0 + (y1 - y0) * t / steps) for t in range(steps)]
        return out + [corners[-1]]

    line(along([(176, 404), (174, 275), (183, 265), (315, 170), (330, 170), (470, 258), (478, 270),
                (480, 392), (470, 398), (190, 408)]))                                   # walls, roof, floor
    line(along([(287, 402), (286, 334), (334, 331), (337, 400)], 16))                   # door
    line(along([(376, 297), (430, 296), (431, 344), (377, 345), (376, 297)], 16))       # window
    line(along([(80, 150), (100, 135), (120, 140), (140, 125), (150, 128), (190, 152)], 8), 2)  # hills
    line([(536 + 42 * math.cos(a), 135 + 42 * math.sin(a))
          for a in np.linspace(0.3, 2 * math.pi + 0.35, 90)], 3, 0.9)                   # sun
    line(along([(80, 455), (305, 449)], 40))                                            # ground, with a gap
    line(along([(350, 445), (582, 434)], 40))
    for _ in range(40):                                                                 # dust
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=170)
    ink = ink.filter(ImageFilter.GaussianBlur(0.6))
    yy, xx = np.mgrid[0:h, 0:w]
    paper = 232 - 70 * (xx / w) * (yy / h) - 12 * (1 - xx / w) * (yy / h) + rng.normal(0, 2.5, (h, w))
    alpha = np.asarray(ink, float)[..., None] / 255 * 0.85
    rgb = paper[..., None] * np.array([0.98, 0.98, 1.0]) * (1 - alpha) + np.array([55, 55, 70]) * alpha
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def pipeline(photo):
    """Run the documented drawing actions; return the cleaned and finished renders, comparison and report."""
    project = Project(PANEL_W, PANEL_H, "#ffffff")
    asset = add_image(project, photo)
    project.apply({"type": "drawing", "action": "import", "asset": asset, "name": "house", "x": 0, "y": 0,
                   "width": PANEL_W})
    cleaned = project.render()
    project.apply([{"type": "drawing", "action": "vectorize", "target": "house"},
                   {"type": "drawing", "action": "straighten", "target": "house", "settings": {"close_gaps": 20}}])
    regions = sorted(drawing.report(project, "house")["regions"], key=lambda r: -r["area"])
    house, others = regions[0], sorted(regions[1:], key=lambda r: r["point"][1])
    sun, window, door = others[0], *sorted(others[1:], key=lambda r: r["point"][1])
    colors = [(house, "#f4a35a"), (window, "#9ad1f5"), (door, "#8b5a2b"), (sun, "#ffd23f")]
    project.apply([
        {"type": "drawing", "action": "fill", "target": "house",
         "points": [[*region["point"], color] for region, color in colors]},
        {"type": "drawing", "action": "stroke", "target": "house", "name": "house/chimney",  # same hand
         "points": [[392, 150], [392, 110], [422, 110], [422, 170]], "settings": {"smooth": False}},
    ])
    finished = project.render()
    return cleaned, finished, drawing.compare(project, "house"), drawing.report(project, "house")


def fit(image, width=PANEL_W, height=PANEL_H):
    image = image.convert("RGB")
    scale = min(width / image.width, height / image.height)
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    photo = sketch_photo()
    cleaned, finished, compared, report = pipeline(photo)
    percent = f"{report['preserved'] * 100:.1f}".rstrip("0").rstrip(".")
    panels = [("1. Photo of the sketch", photo), ("2. drawing import (cleaned)", cleaned),
              ("3. straighten, fill, stroke", finished), (f"4. compare: {percent}% of the original kept", compared)]
    sheet = Project(1310, 1060, BACKDROP)
    ops = []
    for i, (caption, image) in enumerate(panels):
        x, y = 10 + i % 2 * 650, 44 + i // 2 * 520
        ops += [dict(type="import", asset=add_image(sheet, fit(image)), name=f"panel-{i + 1}", x=x, y=y),
                dict(type="text", name=f"caption-{i + 1}", text=caption, x=x + 2, y=y - 30, size=20, color=INK)]
    sheet.apply(ops)
    sheet.export(output / "drawing-pipeline.png", alpha="auto", overwrite=True)
    print(f"Wrote {output / 'drawing-pipeline.png'} with Vixl {__version__}: preserved {report['preserved']}, "
          f"added {report['added']}, strokes {report['stroke_kinds']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs", help="directory for drawing-pipeline.png")
    build(parser.parse_args().output)
