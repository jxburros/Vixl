"""A small builder for the backtest documents: plain Vixl operations collected and applied in one batch."""

import json
from pathlib import Path

OPS = Path(__file__).parent / "ops"


def ops_file(name):
    return json.loads((OPS / name).read_text(encoding="utf-8"))


class Doc:
    """``Doc(width, height, background, body=27)``: ``body`` sets the document's type scale (its body size),
    which is what the spacing unit is read from, as on a document Vixl created with a rolled type scale."""

    def __init__(self, width, height, background, body=None):
        self.width, self.height, self.background = width, height, background
        self.ops = [{"type": "type-scale", "base": body}] if body else []

    def op(self, *operations):
        self.ops.extend(operations)
        return self

    def text(self, name, text, x, y, size, color="#14263b", align="left", width=None, **extra):
        self.ops.append({"type": "text", "name": name, "text": text, "x": x, "y": y, "size": size, "color": color,
                         "align": align, **extra})
        if width is not None:
            self.ops.append({"type": "text-layout", "target": name, "width": width})
        return self

    def centered(self, name, text, y, size, color="#14263b", left=None, right=None, **extra):
        """Text centred on the axis between ``left`` and ``right`` (default: the canvas)."""
        left = 0 if left is None else left
        right = self.width if right is None else right
        return self.text(name, text, left, y, size, color, align="center", width=right - left, **extra)

    def rect(self, name, x, y, width, height, fill, radius=None, **extra):
        op = {"type": "shape", "name": name, "shape": "rounded-rectangle" if radius else "rectangle", "x": x, "y": y,
              "width": width, "height": height, "fill": fill, **extra}
        if radius:
            op["radius"] = radius
        self.ops.append(op)
        return self

    def ellipse(self, name, x, y, width, height, fill, **extra):
        self.ops.append({"type": "shape", "name": name, "shape": "ellipse", "x": x, "y": y, "width": width,
                         "height": height, "fill": fill, **extra})
        return self

    def outline(self, name, x, y, width, height, stroke, stroke_width=2, **extra):
        return self.rect(name, x, y, width, height, "transparent", stroke=stroke, stroke_width=stroke_width, **extra)

    def wave(self, name, x, y, width, height, stroke, stroke_width=4, wavelength=120):
        self.ops.append({"type": "shape", "name": name, "shape": "wave", "x": x, "y": y, "width": width,
                         "height": height, "fill": "transparent", "stroke": stroke, "stroke_width": stroke_width,
                         "wavelength": wavelength})
        return self

    def glow(self, name, x, y, width, height, color):
        """A radial glow fading to transparent (a soft light behind something)."""
        self.ops.append({"type": "gradient", "name": name, "x": x, "y": y, "width": width, "height": height,
                         "direction": "radial", "stops": [{"color": color, "offset": 0},
                                                          {"color": "transparent", "offset": 1}]})
        return self

    def intent(self, target, **fields):
        self.ops.append({"type": "layer-intent", "target": target, **fields})
        return self

    def build(self):
        from vixl import Project

        project = Project(self.width, self.height, self.background)
        if self.ops:
            project.apply(self.ops)
        return project
