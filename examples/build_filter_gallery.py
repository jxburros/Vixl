"""Rebuild docs/filter-gallery.png: one source artwork and every local artistic filter.

Run from the repository root: python examples/build_filter_gallery.py [--output DIR]
Offline and deterministic; uses the bundled font. Writes DIR/filter-gallery.png (default docs/).
"""

import argparse
import math
from pathlib import Path

from vixl import Project, __version__
from vixl.assets import add_image
from vixl.constants import ARTISTIC_DEFAULTS

INK = "#23263a"
MUTED = "#5d6170"
PAPER = "#f2efe8"
CELL_W, CELL_H, COLUMNS, PITCH_X, PITCH_Y = 248, 186, 5, 260, 250


def petal(cx, cy, angle, length=70, width=40):
    """An egg-shaped petal pointing outward at ``angle`` degrees (0 = up), in canvas pixels."""
    r = math.radians(angle)
    ux, uy = math.sin(r), -math.cos(r)
    points = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        along = 14 + length / 2 * (1 - math.cos(t))
        side = width / 2 * math.sin(t) * (0.75 + 0.25 * (1 - math.cos(t)) / 2)
        points.append((cx + ux * along - uy * side, cy + uy * along + ux * side))
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points) + " Z"


def artwork():
    """The source: gradient sky, sun, flower, wordmark and a small caption."""
    project = Project(CELL_W, CELL_H, "#ffffff")
    cx, cy = 108, 88
    ops = [dict(type="gradient", name="sky", direction="angled", angle=35,
                stops=[dict(offset=0, color="#6dd6dc"), dict(offset=0.55, color="#d9d3b0"),
                       dict(offset=1, color="#ffcf9a")]),
           dict(type="shape", shape="ellipse", name="sun", x=160, y=8, width=72, height=72, fill="#ffd54a")]
    ops += [dict(type="shape", shape="path", name=f"petal-{i}", path=petal(cx, cy, i * 45),
                 x=0, y=0, width=CELL_W, height=CELL_H, fill="#c0457f" if i % 2 else "#6a4cb4")
            for i in range(8)]
    ops += [dict(type="shape", shape="ellipse", name="center", x=cx - 26, y=cy - 26, width=52, height=52,
                 fill="#f39a2c"),
            dict(type="gradient", name="center-glow", direction="radial", x=cx - 26, y=cy - 26,
                 width=52, height=52, stops=[dict(offset=0, color="#ffc64a"), dict(offset=1, color="#d9661c")]),
            dict(type="clip", target="center-glow", base="center"),
            dict(type="text", name="wordmark", text="Vixl", x=18, y=130, size=38, color="#1f2338"),
            dict(type="text", name="caption", text="local color + ink + motion", x=114, y=165, size=9,
                 color="#1f2338")]
    project.apply(ops)
    return project.render()


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    filters = list(ARTISTIC_DEFAULTS)
    cells = ["original", *filters]
    rows = math.ceil(len(cells) / COLUMNS)
    height = 106 + rows * PITCH_Y + 34
    sheet = Project(1320, height, PAPER)
    source = add_image(sheet, artwork())
    ops = [dict(type="text", name="title", text="VIXL / LOCAL FILTER LAB", x=24, y=12, size=32, color=INK),
           dict(type="text", name="subtitle", text=f"{len(filters)} deterministic treatments · no AI · editable settings",
                x=24, y=58, size=18, color=MUTED)]
    for i, name in enumerate(cells):
        x, y = 24 + i % COLUMNS * PITCH_X, 106 + i // COLUMNS * PITCH_Y
        ops.append(dict(type="import", asset=source, name=f"cell-{name}", x=x, y=y))
        if name != "original":
            ops.append({"type": name, "target": f"cell-{name}"})  # each filter at its default settings
        ops.append(dict(type="text", name=f"label-{name}", text=name.replace("-", " ").upper(),
                        x=x, y=y + CELL_H + 12, size=16, color=INK))
    sheet.apply(ops)
    sheet.export(output / "filter-gallery.png", alpha="auto", overwrite=True)
    print(f"Wrote {len(filters)} filters to {output / 'filter-gallery.png'} with Vixl {__version__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs", help="directory for filter-gallery.png")
    build(parser.parse_args().output)
