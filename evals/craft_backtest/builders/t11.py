"""T11 sketch to vector, coloured (2000 × 1532): a house, a tree and a sun on a ground line.

Placed by hand from ``runs/T11/claude-V/sketch-color.png``: sky (the whole canvas), the ground band, the house
walls, roof, door and windows, the tree trunk and canopy, and the sun with its rays. No text."""

from ..kit import Doc


def build():
    d = Doc(2000, 1532, "#d8ebf2", body=40)
    d.rect("ground", 0, 1150, 2000, 382, "#a8d5c8")
    d.op({"type": "shape", "name": "roof", "shape": "triangle", "x": 590, "y": 450, "width": 530, "height": 260,
          "fill": "#e2725b", "stroke": "#1d1d1d", "stroke_width": 5})
    d.rect("walls", 600, 700, 510, 450, "#f7f1e5", stroke="#1d1d1d", stroke_width=5)
    d.rect("door", 800, 930, 120, 220, "#14263b")
    d.rect("window-left", 660, 780, 110, 90, "#14263b")
    d.rect("window-right", 940, 780, 110, 90, "#14263b")
    d.rect("trunk", 1380, 900, 30, 250, "#7a4b2a")
    d.ellipse("canopy", 1250, 660, 280, 300, "#3f8a4f", stroke="#1d1d1d", stroke_width=5)
    d.ellipse("sun", 1580, 230, 230, 230, "#f2a541", stroke="#1d1d1d", stroke_width=5)
    for i, (x, y, w, h) in enumerate([(1690, 120, 5, 70), (1690, 490, 5, 70), (1470, 340, 70, 5), (1840, 340, 70, 5)]):
        d.rect(f"ray-{i + 1}", x, y, w, h, "#1d1d1d")
    return {"T11-sketch": d.build()}
