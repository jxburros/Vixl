"""Build the committed texture comparison with the same public operations as an agent."""
from pathlib import Path

from PIL import Image, ImageDraw

from vixl.project import Project
from vixl.textures import DRAWN, PATTERNS


def build(output):
    columns, cell = 4, 180
    entries = [("plain", None), *[(p, "drawn") for p in DRAWN], *[(p, "pattern") for p in PATTERNS]]
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell, rows * 200), "#eee9df")
    for i, (name, kind) in enumerate(entries):
        project = Project(160, 160)
        project.apply({"type": "shape", "shape": "ellipse", "name": "paper", "width": 150,
                       "height": 150, "x": 5, "y": 5, "fill": "#f5e9cc"})
        if kind == "drawn":
            project.apply({"type": "drawn-texture", "target": "paper", "preset": name,
                           "strength": .85, "color": "#304f66", "seed": 9})
        elif kind == "pattern":
            project.apply({"type": "pattern-fill", "target": "paper", "pattern": name,
                           "colors": ["#304f66", "#f5e9cc"], "spacing": 20})
        x, y = i % columns * cell, i // columns * 200
        image = project.render()
        sheet.paste(image, (x + 10, y + 10), image)
        ImageDraw.Draw(sheet).text((x + 12, y + 174), name, fill="#17232e")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "docs/images/texture-comparison.png")
