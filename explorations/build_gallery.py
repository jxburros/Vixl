"""Compose explorations/gallery.jpg from the projects' outputs with Vixl.

Run from the repo root after the builds:  python explorations/build_gallery.py

Two rows of four 610 px cells on white. Each image is scaled to fit 600 x 600 and centred in
its cell's top-left 600 px square, which leaves a 10 px gutter between cells.
"""

from pathlib import Path

from PIL import Image

from vixl import Project

HERE = Path(__file__).resolve().parent
CELL, BOX = 610, 600
TILES = [
    ["01-print-concert-poster/output/poster-rgb.png",
     "02-brand-identity/output/board/brand-board.png",
     "05-generative-painting/output/painting.jpg",
     "08-infographic/output/infographic-world.png"],
    ["09-collab-campaign/output/00-overview.png",
     "04-pixel-rpg/output/title@4x.png",
     "06-photo-lab/output/diptych.jpg",
     "07-trading-cards/output/sheets/contact-sheet.jpg"],
]

p = Project(CELL * 4, CELL * 2, "white")
ops = []
for row, paths in enumerate(TILES):
    for col, rel in enumerate(paths):
        path = HERE / rel
        w, h = Image.open(path).size
        scale = min(BOX / w, BOX / h)
        tw, th = round(w * scale), round(h * scale)
        name = f"tile-{rel.split('/')[0]}"
        ops += [{"type": "add", "path": str(path), "name": name},
                {"type": "resize", "target": name, "width": tw, "height": th},
                {"type": "move", "target": name, "x": col * CELL + (BOX - tw) // 2, "y": row * CELL + (BOX - th) // 2}]
p.apply(ops, detail="compact")
p.export(HERE / "gallery.jpg", quality=85, overwrite=True)
print("wrote", HERE / "gallery.jpg")
