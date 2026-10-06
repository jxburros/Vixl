"""Rebuild docs/organic-gallery.png: every organic preset at its defaults, labelled, on cream.

Run from the repository root: python examples/build_organic_gallery.py [--output DIR]
Offline and deterministic (fixed seed); uses the bundled font. Writes DIR/organic-gallery.png.
"""

import argparse
import math
from pathlib import Path

from vixl import Project, __version__
from vixl.organic import PRESETS

CREAM = "#f6f1e7"
INK = "#2a2620"
COLUMNS, CELL_W, CELL_H, ART = 8, 180, 196, 160
SEED = 0


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    presets = list(PRESETS)
    rows = math.ceil(len(presets) / COLUMNS)
    project = Project(COLUMNS * CELL_W, rows * CELL_H, CREAM)
    ops = []
    for i, preset in enumerate(presets):
        x, y = i % COLUMNS * CELL_W, i // COLUMNS * CELL_H
        ops += [dict(type="organic", preset=preset, name=preset, seed=SEED,
                     x=x + (CELL_W - ART) // 2, y=y + 8, width=ART, height=ART),
                dict(type="text", name=f"label-{preset}", text=preset, x=x + 6, y=y + CELL_H - 18,
                     size=11, color=INK)]
    project.apply(ops)
    # A plain text layer's box hugs its ink, so "rose" would sit higher than "flower":
    # put every label on one baseline per row instead.
    moves = []
    for i, preset in enumerate(presets):
        baseline = project.inspect(f"label-{preset}")["baseline"]
        target = i // COLUMNS * CELL_H + CELL_H - 8
        moves.append(dict(type="move", target=f"label-{preset}", x=i % COLUMNS * CELL_W + 6,
                          y=project.layer(f"label-{preset}")["y"] + target - baseline))
    project.apply(moves)
    project.export(output / "organic-gallery.png", alpha="auto", overwrite=True)
    print(f"Wrote {len(presets)} presets to {output / 'organic-gallery.png'} with Vixl {__version__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs", help="directory for organic-gallery.png")
    build(parser.parse_args().output)
