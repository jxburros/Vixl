"""Helpers for the promo scenes: brand constants, operation builders and motion shorthands.

A ``Scene`` collects Vixl operations (the same JSON that ``vixl apply`` accepts) and writes one
editable 1920 x 1080 ``.vixl`` master with a keyframe timeline. Times are milliseconds.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROMO = ROOT / "promo"
W, H, FPS = 1920, 1080, 30
os.chdir(ROOT)  # image paths in the scenes are repository-relative

# Digital Shift identity (assets/brand/digital-shift/START-HERE.md) plus the marketing pack's neutrals.
CHARCOAL = "#252B39"
DEEP = "#1A1F2B"
PANEL = "#2F3647"
LINE = "#3C4458"
BLUE = "#3575EE"
SKY = "#6A9AFF"
WHITE = "#FFFFFF"
MUTED = "#AEB7CA"
CODE_KEY = "#8FB4FF"
CODE_STR = "#9FE3B4"
CODE_NUM = "#FFC37A"
GOOD = "#5FD38D"
BAD = "#FF6B6B"

HEAD, BODY, SEMI, MONO = "inter-tight-800", "inter-400", "inter-600", "jetbrains-mono-500"
LOGOS = ROOT / "assets/brand/digital-shift/Editable-Vixl"


class Scene:
    def __init__(self, name: str, duration: int, background: str = CHARCOAL):
        self.name, self.duration, self.background = name, duration, background
        self.ops: list[dict] = []

    def add(self, *ops):
        for op in ops:
            if isinstance(op, list):
                self.ops.extend(op)
            else:
                self.ops.append(op)
        return self

    # ---------------------------------------------------------------- motion
    def key(self, target, prop, time, value, easing=None):
        op = {"type": "keyframe", "target": target, "property": prop, "time": int(time), "value": value}
        if easing:
            op["easing"] = easing
        self.ops.append(op)

    def keys(self, target, prop, frames, easing="ease-out-cubic"):
        """``frames`` is [(time, value), ...]; every key after the first uses ``easing``."""
        for i, (t, v) in enumerate(frames):
            self.key(target, prop, t, v, easing if i else None)

    def fade(self, target, t_in, t_out=None, dur=350, rise=0, easing="ease-out-cubic"):
        """Fade (and optionally rise ``rise`` px) in at t_in; fade out from t_out if given."""
        frames = [(0, 0), (t_in, 0), (t_in + dur, 1)]
        if t_out is not None:
            frames += [(t_out, 1), (t_out + dur * 0.8, 0)]
        self.keys(target, "opacity", frames, easing)
        if rise:
            self.keys(target, "translate-y", [(0, rise), (t_in, rise), (t_in + dur * 1.4, 0)], easing)

    def pop(self, target, t, dur=420, start_scale=0.6, t_out=None):
        self.keys(target, "scale", [(0, start_scale), (t, start_scale), (t + dur, 1)], "ease-out-back")
        self.fade(target, t, t_out, dur=int(dur * 0.6))

    def slide(self, target, t, dx=0, dy=0, dur=600, easing="ease-out-expo"):
        if dx:
            self.keys(target, "translate-x", [(0, dx), (t, dx), (t + dur, 0)], easing)
        if dy:
            self.keys(target, "translate-y", [(0, dy), (t, dy), (t + dur, 0)], easing)

    def show(self, target, t0, t1=None):
        self.key(target, "visible", 0, False)
        self.key(target, "visible", t0, True)
        if t1 is not None:
            self.key(target, "visible", t1, False)

    def words(self, target, start, preset="fade-up", unit="word", duration=450, stagger=None, easing="ease-out-cubic"):
        op = {"type": "text-animate", "target": target, "preset": preset, "unit": unit,
              "start": int(start), "duration": int(duration), "easing": easing}
        if stagger is not None:
            op["stagger"] = int(stagger)
        self.ops.append(op)

    # ---------------------------------------------------------------- build
    def project(self) -> Project:
        p = Project(W, H, self.background)
        p._workspace = str(ROOT)  # image sources resolve against the repository root
        install_font(p, "Inter Tight", 800, role="heading")
        install_font(p, "Inter", 400, role="body")
        install_font(p, "Inter", 600)
        install_font(p, "JetBrains Mono", 500)
        p.apply([{"type": "swatch", "name": "brand", "color": BLUE},
                 {"type": "swatch", "name": "sky", "color": SKY},
                 {"type": "swatch", "name": "charcoal", "color": CHARCOAL}], detail="brief")
        batch = [{"type": "timeline-set", "duration": self.duration, "fps": FPS, "loop_mode": "off"}] + self.ops
        for i in range(0, len(batch), 9000):
            p.apply(batch[i:i + 9000], detail="brief")
        return p

    def build(self) -> Project:
        p = self.project()
        p.compact()
        p.save(str(PROMO / "scenes" / f"{self.name}.vixl"), overwrite=True)
        return p


# -------------------------------------------------------------------- operation builders
def rect(name, x, y, w, h, fill, radius=0, stroke=None, stroke_width=2):
    op = {"type": "shape", "shape": "rounded-rectangle" if radius else "rectangle", "name": name,
          "x": round(x, 2), "y": round(y, 2), "width": max(1, round(w)), "height": max(1, round(h)), "fill": fill}
    if radius:
        op["radius"] = radius
    if stroke:
        op.update(stroke=stroke, stroke_width=stroke_width)
    return op


def ellipse(name, cx, cy, w, h, fill, stroke=None, stroke_width=2):
    op = {"type": "shape", "shape": "ellipse", "name": name, "x": round(cx - w / 2, 2), "y": round(cy - h / 2, 2),
          "width": max(1, round(w)), "height": max(1, round(h)), "fill": fill}
    if stroke:
        op.update(stroke=stroke, stroke_width=stroke_width)
    return op


def text(name, value, x, y, size, color=WHITE, font=BODY, **extra):
    return {"type": "text", "name": name, "text": value, "font": font, "size": size, "color": color,
            "x": round(x, 2), "y": round(y, 2), **extra}


def rich(name, spans, x, y, size, width, color=WHITE, font=HEAD, align="left", line_height=1.0):
    """Rich text; ``spans`` is a string or [(text, color or None), ...]."""
    if isinstance(spans, str):
        spans = [(spans, None)]
    out = [{"text": t, **({"color": c} if c else {})} for t, c in spans]
    return {"type": "rich-text", "name": name, "spans": out, "font": font, "size": size, "color": color,
            "x": round(x, 2), "y": round(y, 2), "width": round(width), "align": align, "line_height": line_height}


def centered(name, spans, y, size, color=WHITE, font=HEAD, line_height=1.0, x=0, width=W):
    return rich(name, spans, x, y, size, width, color, font, "center", line_height)


def glow(name, cx, cy, size, color=BLUE, strength="55"):
    return {"type": "gradient", "name": name, "direction": "radial", "width": size, "height": size,
            "x": round(cx - size / 2), "y": round(cy - size / 2),
            "stops": [{"offset": 0, "color": f"{color}{strength}"}, {"offset": 0.6, "color": f"{color}10"},
                      {"offset": 1, "color": f"{color}00"}]}


def group(name, targets):
    return {"type": "group", "name": name, "targets": list(targets)}


def shadow(target, blur=40, dy=18, opacity=0.45):
    return {"type": "layer-style", "target": target, "name": "drop-shadow",
            "settings": {"color": "#000000", "offset_x": 0, "offset_y": dy, "blur": blur, "opacity": opacity}}


def image(name, path, x, y, w, h, radius=18, fit="fill", base=PANEL):
    """A Vixl-made picture from the repository, cropped into a rounded, editable frame."""
    return [rect(f"{name}-base", x, y, w, h, base, radius),
            {"type": "frame", "name": f"{name}-img", "path": path, "x": round(x), "y": round(y),
             "width": round(w), "height": round(h), "fit": fit, "downsample": "placed@2x"},
            {"type": "clip", "target": f"{name}-img", "base": f"{name}-base"},
            group(name, [f"{name}-base", f"{name}-img"])]


def chip(name, label, x, y, size=26, fg=WHITE, bg=PANEL, font=SEMI, pad_x=22, stroke=None, width=None):
    """A pill label. Width is estimated from the font size so scenes need no measuring pass."""
    h = round(size * 1.9)
    w = width or round(len(label) * size * 0.58 + 2 * pad_x)
    return [rect(f"{name}-bg", x, y, w, h, bg, h / 2, stroke),
            rich(f"{name}-label", label, x, y + (h - size * 1.2) / 2, size, w, fg, font, "center", 1.2),
            group(name, [f"{name}-bg", f"{name}-label"])]


def backdrop(prefix="bg", glow_at=(1400, 300), glow2_at=(300, 900)):
    """Shared background so hard cuts between scenes feel continuous."""
    return [rect(f"{prefix}-base", 0, 0, W, H, CHARCOAL),
            glow(f"{prefix}-glow1", *glow_at, 1500, BLUE, "40"),
            glow(f"{prefix}-glow2", *glow2_at, 1200, SKY, "22")]


def mark(prefix, x, y, width, variant="mark-reverse"):
    """The paired-V symbol as editable layers: ``{prefix}-down``, ``-up`` and six pixels.

    Geometry is copied from the identity's Vixl master and scaled into place, so every part can move.
    """
    source = Project.load(LOGOS / f"{variant}.vixl")
    parts = [layer for layer in source.state["layers"] if layer["type"] == "shape"]
    left = min(layer["x"] for layer in parts)
    top = min(layer["y"] for layer in parts)
    right = max(layer["x"] + layer["width"] for layer in parts)
    s = width / (right - left)
    ops, names = [], []
    for layer in parts:
        label = layer["name"].lower()
        key = ("down" if "downward" in label else "up" if "upward" in label
               else label.replace("upper pixel ", "pu").replace("lower pixel ", "pl"))
        name = f"{prefix}-{key}"
        op = {"type": "shape", "shape": layer["shape"], "name": name, "fill": layer["fill"],
              "x": round(x + (layer["x"] - left) * s, 2), "y": round(y + (layer["y"] - top) * s, 2),
              "width": max(1, round(layer["width"] * s)), "height": max(1, round(layer["height"] * s))}
        if layer.get("path"):
            op["path"] = layer["path"]
        ops.append(op)
        names.append(name)
        if layer.get("path"):
            ops.append({"type": "path-fit", "target": name})
    return ops, names
