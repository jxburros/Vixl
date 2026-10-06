"""Rebuild docs/irregular-gallery.png: irregular strengths side by side, then the tear variants.

Run from the repository root: python examples/build_irregular_gallery.py [--output DIR]
Offline and deterministic (fixed seeds); uses the bundled font. Writes DIR/irregular-gallery.png.
"""

import argparse
from pathlib import Path

from vixl import Project, __version__

CREAM = "#f6f0e6"
INK = "#172a3f"
NIGHT = "#233045"
CORAL = "#e3735e"
LEAF = "#4f8a3b"
STRENGTHS = ["clean", "subtle", "natural", "rough"]
SEED = 7


def leaf_path(w, h):
    """A pointed lens, tips left and right, in the layer's own pixels."""
    c = h / 2
    k = (c - 3) / 0.75  # a cubic reaches 3/4 of the way to its control points
    return (f"M2 {c} C{w * 0.25:.1f} {c - k:.1f} {w * 0.75:.1f} {c - k:.1f} {w - 2} {c} "
            f"C{w * 0.75:.1f} {c + k:.1f} {w * 0.25:.1f} {c + k:.1f} 2 {c} Z")


def column(name, x):
    """A rectangle, ellipse, star, wave path and three leaves, all editable vector layers."""
    outline = dict(stroke=INK, stroke_width=5)
    return [
        dict(type="text", name=f"{name}-label", text=name, x=x, y=12, size=26, color=INK),
        dict(type="shape", shape="rounded-rectangle", name=f"{name}-rect", x=x + 4, y=64, width=114, height=82,
             radius=10, fill="#a8d8cc", **outline),
        dict(type="shape", shape="ellipse", name=f"{name}-ellipse", x=x + 144, y=64, width=104, height=82,
             fill="#f3a742", **outline),
        dict(type="shape", shape="star", name=f"{name}-star", x=x + 12, y=174, width=96, height=92,
             fill=CORAL, stroke=INK, stroke_width=4),
        dict(type="shape", shape="path", name=f"{name}-wave", x=x + 130, y=182, width=152, height=62,
             path="M8 44 C34 24 48 58 74 50 C102 42 110 8 132 8 C140 8 144 18 144 30",
             fill="transparent", stroke=INK, stroke_width=8),
        *[dict(type="shape", shape="path", name=f"{name}-leaf-{i}", x=x + i * 95, y=312, width=80, height=78,
               path=leaf_path(80, 78), fill=LEAF, stroke="#1d3a17", stroke_width=3) for i in range(3)],
    ]


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    project = Project(1240, 800, CREAM)
    ops = []
    for i, strength in enumerate(STRENGTHS):
        ops += column(strength, 40 + i * 300)
    for strength in STRENGTHS[1:]:
        parts = ["rect", "ellipse", "star", "wave", "leaf-0", "leaf-1", "leaf-2"]
        ops.append(dict(type="irregular", targets=[f"{strength}-{part}" for part in parts], seed=SEED,
                        strength=strength))
    ops += [dict(type="solid", name="band", x=0, y=480, width=1240, height=320, color=NIGHT),
            dict(type="text", name="tear-label", text="tear: mask, mask (rough), clip (rough), free paper",
                 x=40, y=492, size=20, color="#f6f0e6")]
    for i, (strength, mode) in enumerate([("natural", "mask"), ("rough", "mask"), ("rough", "clip")]):
        name = f"torn-{i}"
        ops += [dict(type="solid", name=name, x=40 + i * 300, y=540, width=260, height=200, color=CORAL),
                {"type": "tear", "target": name, "seed": 3 + i, "edges": ["top", "bottom"],
                 "strength": strength, "as": mode}]
    ops.append({"type": "tear", "name": "paper", "as": "path", "seed": 9, "x": 940, "y": 540,
                "width": 260, "height": 200, "edges": ["all"], "fill": "#f6f0e6"})
    project.apply(ops)
    project.export(output / "irregular-gallery.png", alpha="auto", overwrite=True)
    print(f"Wrote {output / 'irregular-gallery.png'} with Vixl {__version__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs", help="directory for irregular-gallery.png")
    build(parser.parse_args().output)
