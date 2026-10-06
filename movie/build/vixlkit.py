"""Small helpers for generating Vixl scene documents from Python.

A ``Doc`` collects operation dictionaries (the same JSON that ``vixl apply`` and
``vixl_operations_apply`` accept), writes a ``.vixl`` master and applies them. Layer
order is draw order: later calls draw on top. Geometry helpers take *pixels*;
ellipse helpers take a *centre*, rectangle helpers take a *top-left* corner.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile

from PIL import ImageFont

FONT_FAMILY = "Fredoka"
FONT_WEIGHT = 700
FONT_CACHE = os.path.expanduser("~/.cache/vixl/fonts/fredoka-700.ttf")
VIXL = shutil.which("vixl") or "vixl"


def vixl(*args: str, cwd: str) -> str:
    result = subprocess.run([VIXL, *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"vixl {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def text_width(text: str, size: int) -> float:
    """Pixel width of the widest line, measured with the real display font."""
    if not os.path.exists(FONT_CACHE):
        return max(len(line) for line in text.split("\n")) * size * 0.56
    font = ImageFont.truetype(FONT_CACHE, size)
    return max(font.getlength(line) for line in text.split("\n"))


def _i(value: float) -> int:
    return max(1, int(round(value)))


class Doc:
    def __init__(self, name: str, duration_ms: int, bg: str = "#000000", fps: int = 24,
                 width: int = 1280, height: int = 720):
        self.name, self.duration, self.bg, self.fps = name, duration_ms, bg, fps
        self.width, self.height = width, height
        self.ops: list[dict] = []
        self.talks: list[tuple] = []  # (mouth layer, start ms, end ms, step ms): drives the audio blips
        self._n = 0

    # ------------------------------------------------------------------ basics
    def op(self, **kw) -> None:
        self.ops.append(kw)

    def _opt(self, op: dict, fill=None, stroke=None, sw=None, opacity=None, name=None) -> str:
        if fill is not None:
            op["fill"] = fill
        if stroke:
            op["stroke"] = stroke
            op["stroke_width"] = sw or 2
        self.ops.append(op)
        if opacity is not None and opacity < 1:
            self.ops.append({"type": "opacity", "target": name, "value": opacity})
        return name

    # ------------------------------------------------------------------ shapes
    def rect(self, name, x, y, w, h, fill, r=0, stroke=None, sw=None, opacity=None):
        shape = "rounded-rectangle" if r else "rectangle"
        op = {"type": "shape", "shape": shape, "name": name, "x": x, "y": y,
              "width": _i(w), "height": _i(h)}
        if r:
            op["radius"] = r
        return self._opt(op, fill, stroke, sw, opacity, name)

    def crect(self, name, cx, cy, w, h, fill, **kw):
        return self.rect(name, cx - w / 2, cy - h / 2, w, h, fill, **kw)

    def ell(self, name, cx, cy, w, h, fill, stroke=None, sw=None, opacity=None, rot=0):
        op = {"type": "shape", "shape": "ellipse", "name": name, "x": cx - w / 2, "y": cy - h / 2,
              "width": _i(w), "height": _i(h)}
        self._opt(op, fill, stroke, sw, opacity, name)
        if rot:
            self.ops.append({"type": "rotate", "target": name, "value": rot})
        return name

    def star(self, name, cx, cy, size, fill, points=5, inner=0.45, rot=0, opacity=None):
        op = {"type": "shape", "shape": "star", "name": name, "x": cx - size / 2, "y": cy - size / 2,
              "width": _i(size), "height": _i(size), "sides": points, "inner_radius": inner}
        self._opt(op, fill, None, None, opacity, name)
        if rot:
            self.ops.append({"type": "rotate", "target": name, "value": rot})
        return name

    def shape(self, name, kind, x, y, w, h, fill=None, stroke=None, sw=None, opacity=None, **kw):
        op = {"type": "shape", "shape": kind, "name": name, "x": x, "y": y,
              "width": _i(w), "height": _i(h), **kw}
        return self._opt(op, fill, stroke, sw, opacity, name)

    def poly(self, name, pts, fill=None, stroke=None, sw=None, closed=True, smooth=False,
             opacity=None, tension=None):
        op = {"type": "pen", "name": name, "points": [[round(x, 2), round(y, 2)] for x, y in pts],
              "closed": closed, "smooth": smooth}
        if tension is not None:
            op["tension"] = tension
        if fill is not None:
            op["fill"] = fill
        if stroke:
            op["stroke"] = stroke
            op["stroke_width"] = sw or 2
        self.ops.append(op)
        if opacity is not None and opacity < 1:
            self.ops.append({"type": "opacity", "target": name, "value": opacity})
        return name

    def line(self, name, pts, stroke, sw=3, smooth=True, opacity=None):
        return self.poly(name, pts, None, stroke, sw, closed=False, smooth=smooth, opacity=opacity)

    def solid(self, name, color, x=0, y=0, w=None, h=None, opacity=None):
        op = {"type": "solid", "name": name, "color": color, "x": x, "y": y,
              "width": _i(w or self.width), "height": _i(h or self.height)}
        self.ops.append(op)
        if opacity is not None and opacity < 1:
            self.ops.append({"type": "opacity", "target": name, "value": opacity})
        return name

    def gradient(self, name, stops, direction="vertical", x=0, y=0, w=None, h=None, angle=None,
                 opacity=None, blend=None):
        op = {"type": "gradient", "name": name, "direction": direction, "x": x, "y": y,
              "width": _i(w or self.width), "height": _i(h or self.height),
              "stops": [{"offset": o, "color": c} for o, c in stops]}
        if angle is not None:
            op["angle"] = angle
        self.ops.append(op)
        if opacity is not None and opacity < 1:
            self.ops.append({"type": "opacity", "target": name, "value": opacity})
        if blend:
            self.ops.append({"type": "blend", "target": name, "value": blend})
        return name

    def text(self, name, s, x, y, size, color="#ffffff", align="left", spacing=0, font="display"):
        op = {"type": "text", "name": name, "text": s, "x": x, "y": y, "size": int(size),
              "color": color, "align": align, "spacing": spacing, "font": font}
        self.ops.append(op)
        return name

    def ctext(self, name, s, cx, cy, size, color="#ffffff", **kw):
        """Text centred on (cx, cy) using the real font metrics."""
        w = text_width(s, size)
        lines = s.count("\n") + 1
        h = size * 1.25 * lines
        return self.text(name, s, cx - w / 2, cy - h / 2, size, color, align="center", **kw)

    def text_stroke(self, name, width, color):
        self.ops.append({"type": "text-set", "target": name, "stroke_width": int(width), "stroke_color": color})

    # ------------------------------------------------------------------ structure
    def group(self, name, children):
        self.ops.append({"type": "group", "name": name, "targets": list(children)})
        return name

    def pivot(self, target, fx, fy):
        self.ops.append({"type": "pivot", "target": target, "value": [fx, fy]})

    def rotate(self, target, deg):
        self.ops.append({"type": "rotate", "target": target, "value": deg})

    def opacity(self, target, v):
        self.ops.append({"type": "opacity", "target": target, "value": v})

    def blend(self, target, mode):
        self.ops.append({"type": "blend", "target": target, "value": mode})

    def glow(self, target, color, radius=20, **kw):
        self.ops.append({"type": "layer-style", "target": target, "name": "outer-glow",
                         "settings": {"color": color, "radius": radius, **kw}})

    def shadow(self, target, color="#000000", dx=0, dy=6, blur=10, opacity=0.4):
        self.ops.append({"type": "layer-style", "target": target, "name": "drop-shadow",
                         "settings": {"color": color, "offset_x": dx, "offset_y": dy, "blur": blur,
                                      "opacity": opacity}})

    def effect(self, target, name, **kw):
        self.ops.append({"type": "effect", "target": target, "name": name, **kw})

    def hide(self, target):
        self.ops.append({"type": "hide", "target": target})

    # ------------------------------------------------------------------ motion
    def anim(self, target, prop, to, start=0, dur=500, easing="ease-in-out", frm=None):
        op = {"type": "animate", "target": target, "property": prop, "to": to,
              "start": start, "duration": dur, "easing": easing}
        if frm is not None:
            op["from"] = frm
        self.ops.append(op)

    def key(self, target, prop, t, value, easing=None):
        op = {"type": "keyframe", "target": target, "property": prop, "time": t, "value": value}
        if easing:
            op["easing"] = easing
        self.ops.append(op)

    def preset(self, target, name, start=0, dur=500, **kw):
        self.ops.append({"type": "animate-preset", "target": target, "preset": name,
                         "start": start, "duration": dur, **kw})

    def show_between(self, target, t0, t1):
        """Hold a layer hidden, then visible from t0 until t1 (stepped)."""
        self.key(target, "visible", 0, False)
        self.key(target, "visible", t0, True)
        self.key(target, "visible", t1, False)

    def fade_between(self, target, t0, t1, fade=160):
        self.key(target, "opacity", 0, 0)
        self.key(target, "opacity", t0, 0, "ease-out")
        self.key(target, "opacity", t0 + fade, 1)
        self.key(target, "opacity", t1, 1, "ease-in")
        self.key(target, "opacity", t1 + fade, 0)

    def cycle(self, target, prop, a, b, period, start=0, end=None, easing="ease-in-out-sine"):
        """Repeating a -> b -> a oscillation between ``start`` and ``end`` (ms)."""
        end = self.duration if end is None else end
        t, up = start, True
        self.key(target, prop, t, a)
        while t < end:
            t = min(end, t + period / 2)
            self.key(target, prop, t, b if up else a, easing)
            up = not up

    # ------------------------------------------------------------------ build
    def build(self, directory: str, install_font: bool = True) -> str:
        path = os.path.join(directory, f"{self.name}.vixl")
        if os.path.exists(path):
            os.remove(path)
        vixl("new", f"{self.width}x{self.height}", "--background", self.bg, "-o", path, cwd=directory)
        if install_font:
            vixl("-p", path, "font", "install", FONT_FAMILY, "--weight", str(FONT_WEIGHT),
                 "--name", "display", cwd=directory)
        batch = [{"type": "timeline-set", "duration": self.duration, "fps": self.fps}] + self.ops
        for i in range(0, len(batch), 900):  # one apply call holds at most 1000 operations
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(batch[i:i + 900], fh)
            try:
                vixl("-p", path, "apply", fh.name, cwd=directory)
            finally:
                os.unlink(fh.name)
        return path


def rad(deg: float) -> float:
    return deg * math.pi / 180.0
