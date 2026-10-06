"""Pip the robot: a rigged cut-out vector character and a short three-shot film.

Run from the repository root:

    python explorations/10-character-film/build.py

Everything is written to explorations/10-character-film/output/ (wiped first).
"""

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WORK = OUT / "work"  # film workspace: .vixl shot documents + audio

if OUT.exists():
    shutil.rmtree(OUT)
WORK.mkdir(parents=True)
os.environ["VIXL_RESOURCES"] = str(WORK / "resources.json")
os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.timeline import contact_sheet, export_timeline, render_at  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402
from vixl.render_cache import enable as enable_cache  # noqa: E402

CACHE = WORK / ".vixl-cache"

W, H = 960, 540
GROUND = 430  # ground line in the scene documents
INK = "#2b2d42"

# --------------------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------------------
BODY = "#f4a259"
BODY_DARK = "#d9823b"
BODY_BACK = "#c97a3a"
LIMB = "#5b8e7d"
LIMB_BACK = "#456f61"
SCREEN = "#1d2b3a"
EYE = "#7ff0ff"
BULB = "#ffd166"


class Rig:
    """Emit canonical operations for one character, in local units scaled by ``s``.

    (0, 0) in local units is the hip joint; the ground is at y = +100.
    """

    def __init__(self, hx, hy, s=1.0, outline=3):
        self.hx, self.hy, self.s = hx, hy, s
        self.sw = max(1.0, outline * s)
        self.ops = []

    def P(self, x, y):
        return round(self.hx + x * self.s, 2), round(self.hy + y * self.s, 2)

    def L(self, n):
        return max(1, round(n * self.s))

    def shape(self, name, kind, x, y, w, h, fill, stroke=True, **extra):
        px, py = self.P(x, y)
        op = {"type": "shape", "shape": kind, "name": name, "x": px, "y": py,
              "width": self.L(w), "height": self.L(h), "fill": fill}
        if stroke:
            op.update(stroke=INK, stroke_width=self.sw)
        op.update(extra)
        self.ops.append(op)
        return name

    def reach(self, name, cx, cy, half):
        """Invisible square centred on a joint. It puts the joint at the limb group's centre, so
        the pivot is simply [0.5, 0.5]. (In Vixl 0.16.0 it was also needed to stop the group
        cropping the limb as it rotated; groups no longer clip their members.)"""
        return self.shape(name, "rectangle", cx - half, cy - half, 2 * half, 2 * half,
                          "#00000000", stroke=False)

    def group(self, name, members):
        self.ops.append({"type": "group", "name": name, "targets": members})
        return name

    def pivot(self, target, value, units=None):
        op = {"type": "pivot", "target": target, "value": value}
        if units:
            op["units"] = units
        self.ops.append(op)

    # ---------------------------------------------------------------- limbs
    def arm(self, side, sx, sy, colour):
        sfx = "-" + side
        self.reach("reach-arm" + sfx, sx, sy, 100)
        self.shape("upper" + sfx, "rounded-rectangle", sx - 9, sy - 8, 18, 46, colour, radius=self.L(9))
        self.shape("bolt" + sfx, "ellipse", sx - 6, sy - 6, 12, 12, "#e9ecef", stroke=False)
        ex, ey = sx, sy + 36
        self.reach("reach-fore" + sfx, ex, ey, 62)
        self.shape("lower" + sfx, "rounded-rectangle", ex - 8, ey - 6, 16, 40, colour, radius=self.L(8))
        self.shape("elbow" + sfx, "ellipse", ex - 9, ey - 9, 18, 18, colour)
        # Mitten hand: own layer, px pivot at the wrist.
        self.shape("hand" + sfx, "ellipse", ex - 13, ey + 28, 26, 24, "#e9ecef")
        self.group("forearm" + sfx, ["reach-fore" + sfx, "lower" + sfx, "elbow" + sfx, "hand" + sfx])
        self.group("arm" + sfx, ["reach-arm" + sfx, "upper" + sfx, "forearm" + sfx, "bolt" + sfx])
        self.pivot("hand" + sfx, [13, 3], units="px")       # wrist, in pixels of the hand box...
        self.ops[-1]["value"] = [self.L(13), self.L(3)]      # ...scaled with the rig
        self.pivot("forearm" + sfx, [0.5, 0.5])             # elbow (centre of its reach box)
        self.pivot("arm" + sfx, "center")                   # shoulder

    def leg(self, side, hx, colour, boot):
        sfx = "-" + side
        self.reach("reach-leg" + sfx, hx, 0, 118)
        self.shape("thigh" + sfx, "rounded-rectangle", hx - 11, -8, 22, 54, colour, radius=self.L(10))
        kx, ky = hx, 44
        self.reach("reach-shin" + sfx, kx, ky, 72)
        self.shape("calf" + sfx, "rounded-rectangle", kx - 10, ky - 4, 20, 46, colour, radius=self.L(9))
        self.shape("knee" + sfx, "ellipse", kx - 12, ky - 12, 24, 24, colour)
        self.shape("boot" + sfx, "rounded-rectangle", kx - 15, ky + 38, 44, 20, boot, radius=self.L(8))
        self.group("shin" + sfx, ["reach-shin" + sfx, "calf" + sfx, "knee" + sfx, "boot" + sfx])
        self.group("leg" + sfx, ["reach-leg" + sfx, "thigh" + sfx, "shin" + sfx])
        self.pivot("shin" + sfx, [0.5, 0.5])  # knee
        self.pivot("leg" + sfx, "center")     # hip

    # ---------------------------------------------------------------- whole character
    def build(self, *, rust=True, front_shoulder=4):
        s = self
        gx, gy = s.P(-70, 100)
        s.shape("shadow", "ellipse", -70, 94, 140, 14, "#1b263b", stroke=False)
        s.ops.append({"type": "opacity", "target": "shadow", "value": 0.25})
        s.ops.append({"type": "pivot", "target": "shadow", "value": "center"})

        s.arm("b", -4, -74, LIMB_BACK)
        s.leg("b", -7, LIMB_BACK, "#2f3e46")
        s.leg("f", 7, LIMB, "#354f52")

        s.shape("hips", "rounded-rectangle", -32, -14, 64, 24, "#3d5a80", radius=s.L(10))
        s.shape("torso", "rounded-rectangle", -48, -94, 96, 88, BODY, radius=s.L(28))
        s.shape("panel", "rounded-rectangle", -28, -62, 56, 36, "#ffe8cc", radius=s.L(10))
        s.shape("heart", "heart", -10, -55, 20, 18, "#ff5d73", stroke=False)
        s.ops.append({"type": "pivot", "target": "heart", "value": "center"})
        torso_parts = ["hips", "torso", "panel", "heart"]
        if rust:
            # Painted weathering: dry-brush and spray strokes on a paint layer clipped to the torso.
            x0, y0 = s.P(-60, -100)
            s.ops.append({"type": "paint-layer", "name": "grime", "x": x0, "y": y0,
                          "width": s.L(120), "height": s.L(100)})
            for i, (a, b, c) in enumerate([((-50, -20), (-10, -12), (40, -24)),
                                           ((-46, -84), (-20, -90), (10, -86)),
                                           ((20, -70), (40, -60), (44, -40))]):
                pts = [list(s.P(*a)), list(s.P(*b)), list(s.P(*c))]
                s.ops.append({"type": "paint", "target": "grime", "brush": "dry-brush", "points": pts,
                              "size": 14 * s.s, "color": BODY_DARK, "opacity": 0.8, "seed": 11 + i})
            s.ops.append({"type": "paint", "target": "grime", "brush": "spray",
                          "points": [list(s.P(-40, -30)), list(s.P(-30, -20))], "size": 26 * s.s,
                          "color": "#8d5a2b", "opacity": 0.55, "seed": 4})
            s.ops.append({"type": "clip", "target": "grime", "base": "torso"})
            torso_parts.append("grime")

        # Head: neck, skull, face screen, eyes, mouth, cheeks, ear bolt, antenna sub-group.
        s.shape("neck", "rectangle", -10, -106, 20, 16, "#3d5a80")
        s.shape("ear", "rounded-rectangle", -60, -158, 14, 30, "#3d5a80", radius=s.L(6))
        s.shape("skull", "rounded-rectangle", -52, -184, 104, 80, BODY, radius=s.L(24))
        s.shape("screen", "rounded-rectangle", -30, -170, 80, 52, SCREEN, radius=s.L(14))
        s.shape("eye-l", "rounded-rectangle", -14, -160, 14, 20, EYE, stroke=False, radius=s.L(7))
        s.shape("eye-r", "rounded-rectangle", 18, -160, 14, 20, EYE, stroke=False, radius=s.L(7))
        s.shape("mouth", "path", 0, -137, 24, 9, EYE, stroke=False,
                path="M0 0 Q12 14 24 0 Q12 6 0 0 Z")
        s.shape("cheek", "ellipse", 30, -138, 14, 8, "#ff8fa3", stroke=False)
        s.shape("stem", "rectangle", -2, -206, 4, 24, INK, stroke=False)
        s.shape("bulb", "ellipse", -9, -220, 18, 18, BULB)
        s.group("antenna", ["stem", "bulb"])
        s.pivot("antenna", "bottom")
        for eye in ("eye-l", "eye-r"):
            s.pivot(eye, "center")
        s.group("head", ["neck", "ear", "skull", "screen", "eye-l", "eye-r", "mouth", "cheek", "antenna"])

        s.arm("f", front_shoulder, -74, LIMB)
        members = ["arm-b", "leg-b", "leg-f", *torso_parts, "head", "arm-f"]
        s.group("robot", members)
        return s.ops


def fix_pivots(project, rig):
    """Pixel pivots that depend on the final group boxes: neck for the head, feet for the robot."""
    layers = {l["name"]: l for l in project.state["layers"]}

    def origin(name):
        # canvas-space top-left of a (possibly nested) layer
        layer, x, y = layers[name], 0.0, 0.0
        while layer is not None:
            x, y = x + layer["x"], y + layer["y"]
            parent = layer.get("parent")
            layer = next((l for l in project.state["layers"] if l["id"] == parent), None)
        return x, y

    hx, hy = origin("head")
    nx, ny = rig.P(0, -96)
    rx, ry = origin("robot")
    fx, fy = rig.P(0, 100)
    project.apply([
        {"type": "pivot", "target": "head", "value": [round(nx - hx), round(ny - hy)], "units": "px"},
        {"type": "pivot", "target": "robot", "value": [round(fx - rx), round(fy - ry)], "units": "px"},
    ], detail="compact")


# --------------------------------------------------------------------------------------
# Scenery
# --------------------------------------------------------------------------------------

def hill_path(width, height, period, peaks):
    """Single-contour periodic hill silhouette; ``peaks`` repeat every len(peaks) bumps."""
    d = [f"M0 {height}", f"L0 {height - peaks[0] * 0.3:.1f}"]
    x, i = 0, 0
    while x < width:
        top = height - peaks[i % len(peaks)]
        y0 = height - peaks[i % len(peaks)] * 0.3
        y1 = height - peaks[(i + 1) % len(peaks)] * 0.3
        d.append(f"C{x + period * 0.3:.1f} {top:.1f} {x + period * 0.7:.1f} {top:.1f} {x + period:.1f} {y1:.1f}")
        x += period
        i += 1
    d.append(f"L{x:.1f} {height}")
    d.append("Z")
    return " ".join(d), x


def scenery(ops, *, extra=0, blur=0, sun=(760, 120)):
    """Dawn valley. ``extra`` widens the scrolling layers so they can slide left by that much."""
    ops += [
        {"type": "gradient", "name": "sky", "width": W + 80, "height": H + 80, "x": -40, "y": -40,
         "direction": "vertical", "stops": [
             {"offset": 0, "color": "#5e9fd6"}, {"offset": 0.55, "color": "#b9d8f0"},
             {"offset": 0.85, "color": "#ffe0b5"}, {"offset": 1, "color": "#ffd29a"}]},
        {"type": "shape", "shape": "ellipse", "name": "sun", "x": sun[0], "y": sun[1],
         "width": 90, "height": 90, "fill": "#fff3c4"},
        {"type": "layer-style", "target": "sun", "name": "outer-glow",
         "settings": {"color": "#ffe8a3", "size": 40, "opacity": 0.8}},
        {"type": "paint-layer", "name": "sky-wash", "x": 0, "y": 0, "width": W, "height": 320},
    ]
    for i, (y, c) in enumerate([(60, "#ffffff"), (175, "#fde2e4"), (265, "#fff1d6")]):
        ops.append({"type": "paint", "target": "sky-wash", "brush": "watercolor",
                    "path": f"M-60 {y} C220 {y - 50} 520 {y + 50} 1020 {y - 20}",
                    "size": 90, "color": c, "opacity": 0.22, "seed": 20 + i})
    for i, (cx, cy, k) in enumerate([(120, 80, 1.0), (430, 140, 0.7), (640, 60, 0.85)]):
        parts = []
        for j, (dx, dy, w, h) in enumerate([(0, 14, 70, 34), (26, 0, 60, 46), (60, 12, 62, 36)]):
            n = f"cloud{i}-{j}"
            ops.append({"type": "shape", "shape": "ellipse", "name": n, "x": cx + dx * k, "y": cy + dy * k,
                        "width": round(w * k), "height": round(h * k), "fill": "#ffffff"})
            parts.append(n)
        ops.append({"type": "group", "name": f"cloud{i}", "targets": parts})
        ops.append({"type": "opacity", "target": f"cloud{i}", "value": 0.85})

    # Far hills (period 150), mid hills with trees (period 300), ground tufts (period 75).
    d, _ = hill_path(W + extra // 4 + 150, 150, 150, [70, 70])
    ops.append({"type": "shape", "shape": "path", "name": "hills-far", "x": 0, "y": GROUND - 140,
                "width": W + extra // 4 + 150, "height": 150, "fill": "#9db4d6", "path": d})
    mw = W + extra // 2 + 300
    d, _ = hill_path(mw, 130, 150, [60, 95])
    ops.append({"type": "shape", "shape": "path", "name": "hills-mid", "x": 0, "y": GROUND - 105,
                "width": mw, "height": 130, "fill": "#86b98a", "path": d})
    trees = ["hills-mid"]
    for k, x in enumerate(range(40, mw - 40, 150)):
        big = k % 2 == 0
        top = GROUND - (150 if big else 115)
        ops += [
            {"type": "shape", "shape": "rectangle", "name": f"trunk{k}", "x": x - 4, "y": top + 40,
             "width": 8, "height": GROUND - top - 40, "fill": "#6b4f3a"},
            {"type": "shape", "shape": "ellipse" if big else "triangle", "name": f"crown{k}",
             "x": x - 26, "y": top, "width": 52, "height": 64 if big else 70,
             "fill": "#4f8a5b" if big else "#3e7a54", "stroke": "#2f5e45", "stroke_width": 2},
        ]
        trees += [f"trunk{k}", f"crown{k}"]
    ops.append({"type": "group", "name": "midground", "targets": trees})

    gw = W + extra + 150
    ops += [
        {"type": "shape", "shape": "rectangle", "name": "ground", "x": 0, "y": GROUND, "width": gw,
         "height": H - GROUND, "fill": "#7cb36b"},
        {"type": "shape", "shape": "rectangle", "name": "path-band", "x": 0, "y": GROUND + 2, "width": gw,
         "height": 26, "fill": "#e3c58f"},
        # One 75 px tile of brushwork, repeated across the strip: identical tiles scroll seamlessly
        # and the strokes are rasterized once instead of once per tile.
        {"type": "paint-layer", "name": "grass", "x": 0, "y": GROUND - 20, "width": 75,
         "height": H - GROUND + 20},
        {"type": "paint", "target": "grass", "brush": "dry-brush", "space": "layer",
         "points": [[5, 80], [35, 84], [65, 78]], "size": 10, "color": "#5d9a50", "opacity": 0.9, "seed": 7},
        {"type": "paint", "target": "grass", "brush": "dry-brush", "space": "layer",
         "points": [[40, 115], [60, 112], [72, 116]], "size": 8, "color": "#94c47d", "opacity": 0.8, "seed": 9},
    ]
    for j, dx in enumerate((10, 16, 22)):
        ops.append({"type": "paint", "target": "grass", "brush": "ink", "space": "layer",
                    "points": [[dx, 21], [dx + (j - 1) * 4, 8 + j * 3]], "size": 3, "color": "#4c8a43", "seed": 3})
    ops += [
        {"type": "paint", "target": "grass", "brush": "chalk", "space": "layer",
         "points": [[40, 35], [58, 34]], "size": 5, "color": "#c9a66b", "opacity": 0.8, "seed": 5},
        {"type": "repeat", "target": "grass", "count": gw // 75 + 1, "dx": 75},
    ]
    ops.append({"type": "group", "name": "foreground", "targets": ["ground", "path-band", "grass"]})
    if blur:
        # Depth of field for the close-up: blur the whole backdrop as one group. Its oversized
        # sky overhangs the canvas, so the blur's soft edges fall off-frame.
        top = ["sky", "sun", "sky-wash", "cloud0", "cloud1", "cloud2", "hills-far", "midground", "foreground"]
        ops.append({"type": "group", "name": "backdrop", "targets": top})
        ops.append({"type": "effect", "target": "backdrop", "name": "blur", "amount": blur})


def font(project):
    return install_font(project, "Fredoka", weight=600, name="fredoka")["name"]


# --------------------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------------------

def kf(target, prop, keys, easing="ease-in-out-sine", t0=0):
    return [{"type": "keyframe", "target": target, "property": prop, "time": round(t0 + t),
             "value": v, "easing": easing} for t, v in keys]


def cyc(values, period, cycles, phase=0.0, t0=0):
    """Keys for a looping curve given as [(fraction, value), ...] with fraction in [0, 1)."""
    keys = []
    for c in range(cycles):
        for f, v in values:
            t = ((f + phase) % 1.0 + c) * period
            keys.append((t, v))
    keys.sort()
    # close the loop exactly
    first = sorted(((f + phase) % 1.0, v) for f, v in values)[0]
    keys.append((first[0] * period + cycles * period, first[1]))
    if keys[0][0] > 0:  # value at 0 = value at the wrap point
        keys.insert(0, (0, interp_wrap(values, phase)))
    return [(t + t0, v) for t, v in keys if t <= cycles * period]


def interp_wrap(values, phase):
    pts = sorted(((f + phase) % 1.0, v) for f, v in values)
    a, b = pts[-1], pts[0]
    span = (1 - a[0]) + b[0]
    u = (1 - a[0]) / span if span else 0
    return a[1] + (b[1] - a[1]) * u


THIGH = [(0.0, -24), (0.5, 22)]
SHIN = [(0.0, 4), (0.12, 14), (0.5, 22), (0.62, 62), (0.82, 30)]
BOOT_LIFT = None
ARM = [(0.0, 22), (0.5, -22)]
FORE = [(0.0, -12), (0.5, -38)]
BOB = [(0.0, 5), (0.25, -5), (0.5, 5), (0.75, -5)]


def walk(period=1000, cycles=1, s=1.0, t0=0):
    ops = []
    ops += kf("leg-f", "rotation", cyc(THIGH, period, cycles, 0.0), t0=t0)
    ops += kf("leg-b", "rotation", cyc(THIGH, period, cycles, 0.5), t0=t0)
    ops += kf("shin-f", "rotation", cyc(SHIN, period, cycles, 0.0), t0=t0)
    ops += kf("shin-b", "rotation", cyc(SHIN, period, cycles, 0.5), t0=t0)
    ops += kf("arm-f", "rotation", cyc(ARM, period, cycles, 0.0), t0=t0)
    ops += kf("arm-b", "rotation", cyc(ARM, period, cycles, 0.5), t0=t0)
    ops += kf("forearm-f", "rotation", cyc(FORE, period, cycles, 0.0), t0=t0)
    ops += kf("forearm-b", "rotation", cyc(FORE, period, cycles, 0.5), t0=t0)
    ops += kf("robot", "translate-y", cyc([(f, v * s) for f, v in BOB], period, cycles), t0=t0)
    # secondary motion: head nods and the antenna lags behind the bob
    ops += kf("head", "rotation", cyc([(0.05, 2), (0.3, -2), (0.55, 2), (0.8, -2)], period, cycles), t0=t0)
    ops += kf("antenna", "rotation", cyc([(0.1, -9), (0.35, 6), (0.6, -9), (0.85, 6)], period, cycles), t0=t0)
    ops += kf("shadow", "scale-x", cyc([(0.0, 1.0), (0.25, 0.9), (0.5, 1.0), (0.75, 0.9)], period, cycles), t0=t0)
    return ops


def jump(t0, s=1.0, height=150):
    """Anticipation squash, stretch on take-off, tuck at the apex, squash on landing, settle."""
    T = lambda ms: t0 + ms  # noqa: E731
    up = -height * s
    ops = []
    ops += kf("robot", "scale-y", [(0, 1), (260, 0.78), (360, 1.18), (560, 1.0), (760, 1.12),
                                   (860, 0.74), (1000, 1.08), (1180, 1.0)], "ease-out-quad", t0)
    ops += kf("robot", "scale-x", [(0, 1), (260, 1.18), (360, 0.86), (560, 1.0), (760, 0.9),
                                   (860, 1.24), (1000, 0.95), (1180, 1.0)], "ease-out-quad", t0)
    ops += [{"type": "keyframe", "target": "robot", "property": "translate-y", "time": T(t), "value": v,
             "easing": e} for t, v, e in [(0, 0, "linear"), (300, 0, "ease-out-cubic"),
                                          (560, up, "ease-in-cubic"), (840, 0, "linear"), (1180, 0, "linear")]]
    ops += kf("shadow", "scale", [(0, 1), (300, 1), (560, 0.45), (840, 1), (1180, 1)], "ease-in-out-quad", t0)
    ops += kf("shadow", "opacity", [(0, 0.25), (300, 0.25), (560, 0.1), (840, 0.25)], "ease-in-out-quad", t0)
    for side in ("f", "b"):
        ops += kf("arm-" + side, "rotation", [(0, 0), (260, 35), (420, -118), (760, -105), (900, -20),
                                              (1180, 0)], "ease-out-back", t0)
        ops += kf("forearm-" + side, "rotation", [(0, 0), (260, -10), (420, -55), (760, -45), (900, -30), (1180, 0)],
                  "ease-in-out-sine", t0)
        ops += kf("leg-" + side, "rotation", [(0, 0), (360, 0), (520, -38 if side == "f" else -20),
                                              (800, 0)], "ease-in-out-sine", t0)
        ops += kf("shin-" + side, "rotation", [(0, 0), (360, 0), (520, 70 if side == "f" else 55),
                                               (800, 0)], "ease-in-out-sine", t0)
    ops += kf("head", "rotation", [(0, 0), (260, 8), (420, -6), (860, 6), (1180, 0)], "ease-in-out-sine", t0)
    ops += kf("antenna", "rotation", [(0, 0), (300, -16), (560, 14), (860, -22), (1000, 12), (1180, 0)],
              "ease-out-sine", t0)
    ops += kf("eye-l", "scale-y", [(0, 1), (240, 0.25), (330, 1.2), (860, 0.3), (1000, 1)], "ease-in-out-sine", t0)
    ops += kf("eye-r", "scale-y", [(0, 1), (240, 0.25), (330, 1.2), (860, 0.3), (1000, 1)], "ease-in-out-sine", t0)
    return ops


def blink(t):
    return [{"type": "keyframe", "targets": ["eye-l", "eye-r"], "property": "scale-y", "time": round(t + dt),
             "value": v, "easing": "ease-in-out-sine"} for dt, v in [(0, 1), (70, 0.1), (160, 1)]]


# --------------------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------------------

def save(project, name):
    path = WORK / name
    project.save(path)
    # Timeline export/contact sheets do not use the persistent render cache by default; without
    # it every frame re-rasterizes every brush stroke (~15 s/frame here instead of <1 s).
    enable_cache(project, CACHE)
    return path


def timed(label, fn, *a, **k):
    start = time.time()
    result = fn(*a, **k)
    print(f"  {label}: {time.time() - start:.1f}s")
    return result


def build_walk():
    """4 s scene: four strides in place while three parallax planes scroll at 1×, ½× and ¼×.
    Ground speed matches the stance foot (~150 px/s), so the scroll period (600 px / 4 s)
    lets the GIF loop seamlessly."""
    p = Project(W, H, "#5e9fd6")
    ops = []
    scenery(ops, extra=600)
    rig = Rig(430, GROUND - 92, 1.0)
    ops += rig.build()
    p.apply(ops, detail="compact")
    fix_pivots(p, rig)
    loop = 4000
    motion = [{"type": "timeline-set", "duration": loop, "fps": 12, "loop": 0}]
    motion += walk(1000, 4)
    motion += [
        {"type": "animate", "target": "foreground", "property": "translate-x", "from": 0, "to": -600,
         "start": 0, "duration": loop, "easing": "linear"},
        {"type": "animate", "target": "midground", "property": "translate-x", "from": 0, "to": -300,
         "start": 0, "duration": loop, "easing": "linear"},
        {"type": "animate", "target": "hills-far", "property": "translate-x", "from": 0, "to": -150,
         "start": 0, "duration": loop, "easing": "linear"},
        {"type": "animate", "target": "cloud1", "property": "translate-x", "from": 0, "to": -30,
         "start": 0, "duration": loop, "easing": "linear"},
        {"type": "marker", "name": "contact", "time": 0},
        {"type": "marker", "name": "passing", "time": 250},
    ]
    p.apply(motion, detail="compact")
    return p


def build_sprite():
    """Character only on a transparent canvas, one 1 s stride, for the sprite sheet."""
    p = Project(260, 340)
    rig = Rig(130, 232, 1.0)
    p.apply(rig.build(), detail="compact")
    fix_pivots(p, rig)
    p.apply([{"type": "timeline-set", "duration": 1000, "fps": 12, "loop": 0}, *walk(1000, 1)],
            detail="compact")
    return p


def build_jump():
    p = Project(520, 480, "#b9d8f0")
    p.apply([
        {"type": "gradient", "name": "sky", "width": 520, "height": 480, "x": 0, "y": 0,
         "direction": "vertical", "start": "#8ec5f0", "end": "#ffe0b5"},
        {"type": "shape", "shape": "rectangle", "name": "ground", "x": 0, "y": 440, "width": 520,
         "height": 40, "fill": "#7cb36b"},
        {"type": "paint-layer", "name": "grass"},
        {"type": "paint", "target": "grass", "brush": "crayon", "points": [[0, 448], [260, 452], [520, 446]],
         "size": 12, "color": "#5d9a50", "seed": 2},
    ], detail="compact")
    rig = Rig(260, 440 - 100, 1.0)
    p.apply(rig.build(), detail="compact")
    fix_pivots(p, rig)
    p.apply([{"type": "timeline-set", "duration": 1500, "fps": 15, "loop": 0}, *jump(150, height=95),
             *blink(1350)], detail="compact")
    return p


def build_establish():
    """Wide shot: the valley at dawn; tiny Pip wakes, blinks, looks round and jumps for joy."""
    p = Project(W, H, "#5e9fd6")
    fnt = font(p)
    ops = []
    scenery(ops, sun=(520, 50))
    # Pip's dome house, with a painted chimney puff and a lit window.
    ops += [
        {"type": "shape", "shape": "rounded-rectangle", "name": "house-wall", "x": 690, "y": 330,
         "width": 150, "height": 104, "fill": "#e9c46a", "stroke": INK, "stroke_width": 3, "radius": 10},
        {"type": "shape", "shape": "path", "name": "house-roof", "x": 676, "y": 268, "width": 178,
         "height": 72, "fill": "#e76f51", "stroke": INK, "stroke_width": 3,
         "path": "M0 72 C10 10 168 10 178 72 Z"},
        {"type": "shape", "shape": "rectangle", "name": "chimney", "x": 800, "y": 262, "width": 18,
         "height": 30, "fill": "#8d5a2b", "stroke": INK, "stroke_width": 3},
        {"type": "shape", "shape": "rounded-rectangle", "name": "door", "x": 712, "y": 370, "width": 38,
         "height": 62, "fill": "#3d5a80", "stroke": INK, "stroke_width": 3, "radius": 16},
        {"type": "shape", "shape": "ellipse", "name": "window", "x": 774, "y": 356, "width": 40,
         "height": 40, "fill": "#ffd166", "stroke": INK, "stroke_width": 3},
        {"type": "shape", "shape": "rectangle", "name": "mailbox-post", "x": 864, "y": 392, "width": 6,
         "height": 40, "fill": "#6b4f3a"},
        {"type": "shape", "shape": "rounded-rectangle", "name": "mailbox", "x": 852, "y": 378, "width": 30,
         "height": 20, "fill": "#457b9d", "stroke": INK, "stroke_width": 2, "radius": 8},
        {"type": "paint-layer", "name": "smoke", "x": 760, "y": 150, "width": 120, "height": 120},
        {"type": "paint", "target": "smoke", "brush": "soft-round",
         "path": "M50 110 C30 90 70 70 50 50 C30 30 70 20 60 5", "size": 22, "color": "#ffffff",
         "opacity": 0.7, "seed": 1},
        {"type": "group", "name": "house", "targets": ["smoke", "house-wall", "house-roof", "chimney",
                                                       "door", "window", "mailbox-post", "mailbox"]},
    ]
    s = 0.55
    rig = Rig(590, GROUND - 100 * s + 4, s, outline=4)
    ops += rig.build(rust=False)
    ops += [
        {"type": "text", "name": "title", "text": "Pip goes for a walk", "font": fnt, "size": 64,
         "color": "#ffffff", "x": 230, "y": 150},
        {"type": "layer-style", "target": "title", "name": "drop-shadow",
         "settings": {"color": "#2b2d42", "blur": 0, "dx": 3, "dy": 4, "opacity": 0.6}},
    ]
    p.apply(ops, detail="compact")
    fix_pivots(p, rig)
    m = [{"type": "timeline-set", "duration": 4000, "fps": 24, "loop": 0}]
    m += [{"type": "animate-preset", "target": "title", "preset": "slide-in-up", "start": 200,
           "duration": 900},
          {"type": "animate-preset", "target": "title", "preset": "fade-out", "start": 3100,
           "duration": 600}]
    m += kf("bulb", "fill", [(0, "#6c757d"), (500, BULB), (650, "#ffffff"), (800, BULB)], "ease-out-quad")
    m += blink(900) + blink(1250)
    m += kf("head", "rotation", [(0, 0), (1500, -12), (1900, -12), (2200, 10), (2500, 0)])
    m += kf("window", "fill", [(0, "#ffd166"), (600, "#fff3c4"), (1200, "#ffd166")])
    m += kf("smoke", "translate-y", [(0, 10), (4000, -30)], "linear")
    m += kf("smoke", "opacity", [(0, 0.4), (1500, 0.9), (4000, 0.5)])
    m += jump(2550, s)
    for c in ("cloud0", "cloud1", "cloud2"):
        m.append({"type": "animate", "target": c, "property": "translate-x", "from": 0, "to": 40,
                  "duration": 4000, "easing": "linear"})
    p.apply(m, detail="compact")
    return p


def build_wave():
    """Close-up: soft-focus background, Pip turns, waves and says hi."""
    p = Project(W, H, "#5e9fd6")
    fnt = font(p)
    ops = []
    scenery(ops, blur=6, sun=(820, 60))
    rig = Rig(400, 520, 2.1, outline=2.4)
    ops += rig.build(front_shoulder=36)  # 3/4 view: the waving shoulder sits at the torso's edge
    ops += [
        {"type": "shape", "shape": "speech-bubble", "name": "bubble", "x": 660, "y": 70, "width": 230,
         "height": 150, "fill": "#ffffff", "stroke": INK, "stroke_width": 5},
        {"type": "text", "name": "hi", "text": "Hi!", "font": fnt, "size": 72, "color": "#e76f51",
         "x": 715, "y": 88},
        {"type": "group", "name": "speech", "targets": ["bubble", "hi"]},
        {"type": "pivot", "target": "speech", "value": [0.15, 0.95]},
    ]
    p.apply(ops, detail="compact")
    fix_pivots(p, rig)
    m = [{"type": "timeline-set", "duration": 3800, "fps": 24, "loop": 0}]
    # raise the front arm, then wave the forearm and flick the hand at the wrist
    m += kf("arm-f", "rotation", [(0, 18), (500, 18), (900, -105), (3100, -105), (3600, 18)], "ease-in-out-back")
    wave_keys = [(500, -10), (900, -60)]
    for i in range(6):
        wave_keys.append((1100 + i * 320, -85 if i % 2 == 0 else -40))
    wave_keys += [(3100, -60), (3600, -12)]
    m += kf("forearm-f", "rotation", wave_keys, "ease-in-out-sine")
    hand_keys = [(900, 0)] + [(1180 + i * 320, 25 if i % 2 == 0 else -20) for i in range(6)] + [(3200, 0)]
    m += kf("hand-f", "rotation", hand_keys, "ease-in-out-sine")
    m += kf("arm-b", "rotation", [(0, 4), (1000, 10), (2200, 2), (3600, 6)])
    m += kf("forearm-b", "rotation", [(0, -10), (1000, -25), (3600, -12)])
    m += kf("head", "rotation", [(0, 0), (700, -6), (1500, 4), (2300, -4), (3100, 3), (3800, 0)])
    m += kf("antenna", "rotation", [(0, 0), (900, -18), (1150, 12), (1450, -10), (1800, 6), (2400, -4),
                                    (3000, 0)], "ease-out-sine")
    m += kf("bulb", "fill", [(0, BULB), (900, "#ff8fab"), (2000, "#ffd166"), (3000, "#ff8fab")])
    m += blink(300) + blink(2600)
    m += kf("cheek", "opacity", [(0, 0.2), (1100, 1), (3800, 1)])
    m += kf("robot", "translate-y", [(0, 0), (900, -10), (1300, 0), (2200, -8), (3000, 0)])
    m += [{"type": "animate-preset", "target": "heart", "preset": "pulse", "start": 1000, "duration": 600},
          {"type": "animate-preset", "target": "heart", "preset": "pulse", "start": 2200, "duration": 600},
          {"type": "animate-preset", "target": "speech", "preset": "pop-in", "start": 1100, "duration": 450},
          {"type": "keyframe", "target": "speech", "property": "rotation", "time": 1550, "value": 0},
          {"type": "keyframe", "target": "speech", "property": "rotation", "time": 1800, "value": -4,
           "easing": "ease-in-out-sine"},
          {"type": "keyframe", "target": "speech", "property": "rotation", "time": 2100, "value": 3,
           "easing": "ease-in-out-sine"},
          {"type": "keyframe", "target": "speech", "property": "rotation", "time": 2400, "value": 0}]
    p.apply(m, detail="compact")
    return p


# --------------------------------------------------------------------------------------
# Audio: a tiny synthesized score (sine arpeggios + footstep ticks)
# --------------------------------------------------------------------------------------

def write_wav(path, seconds, footsteps):
    rate = 22050
    n = int(seconds * rate)
    buf = [0.0] * n

    def tone(start, dur, freq, amp, decay=6.0):
        i0 = int(start * rate)
        for i in range(int(dur * rate)):
            if i0 + i >= n:
                break
            t = i / rate
            env = min(1.0, t * 80) * math.exp(-decay * t)
            buf[i0 + i] += amp * env * (math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(4 * math.pi * freq * t))

    notes = [523.25, 659.25, 783.99, 659.25, 587.33, 698.46, 880.0, 698.46]
    for k in range(int(seconds / 0.25)):
        tone(k * 0.25, 0.5, notes[k % len(notes)] / (2 if (k // 8) % 2 else 1), 0.12)
    for k in range(0, int(seconds), 2):
        tone(k, 1.8, 130.81 if (k // 2) % 2 == 0 else 174.61, 0.15, decay=1.5)
    for t in footsteps:
        tone(t, 0.06, 90, 0.5, decay=60)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in buf))


def vixl(*args, request=None):
    cmd = ["vixl", *args]
    if request is not None:
        req = WORK / f"_{args[-1] if args[0] != 'workflow' else args[1]}.json"
        req.write_text(json.dumps(request, indent=1))
        cmd += ["--request", str(req), "--workspace", str(WORK)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        print(out.stdout, out.stderr)
        raise SystemExit(f"vixl {' '.join(args)} failed")
    return json.loads(out.stdout) if out.stdout.strip().startswith("{") else out.stdout


# --------------------------------------------------------------------------------------

def main():
    print("Building documents")
    walk_doc = timed("walk", build_walk)
    save(walk_doc, "walk.vixl")
    sprite = timed("sprite", build_sprite)
    save(sprite, "walk-sprite.vixl")
    jump_doc = timed("jump", build_jump)
    save(jump_doc, "jump.vixl")
    establish = timed("establish", build_establish)
    save(establish, "establish.vixl")
    wave_doc = timed("wave", build_wave)
    save(wave_doc, "wave.vixl")

    QUICK = "--sheets" in sys.argv  # iterate on motion: contact sheets only
    if QUICK:
        for name, doc, times in [("walk", walk_doc, [i * 125 for i in range(8)]),
                                 ("jump", jump_doc, [150 + i * 120 for i in range(10)]),
                                 ("wave", wave_doc, None), ("establish", establish, None)]:
            timed(name + " sheet", lambda: contact_sheet(doc, count=len(times or [0] * 10), times=times)
                  .save(OUT / f"{name}-contact.png"))
        return
    print("Exports")
    timed("walk gif", export_timeline, walk_doc, OUT / "walk-cycle.gif", scale=0.5, colors=96)
    timed("walk sheet", lambda: contact_sheet(walk_doc, count=8, times=[i * 125 for i in range(8)])
          .save(OUT / "walk-contact.png"))
    timed("sprite sheet", export_timeline, sprite, OUT / "walk-sprite-sheet.png", format="sheet", columns=6)
    timed("sprite gif", export_timeline, sprite, OUT / "walk-sprite.gif", colors=64)
    timed("jump gif", export_timeline, jump_doc, OUT / "jump.gif", scale=0.75, colors=96)
    contact_sheet(jump_doc, count=10, times=[150 + i * 120 for i in range(10)]).save(OUT / "jump-contact.png")
    contact_sheet(wave_doc, count=8).save(OUT / "wave-contact.png")
    contact_sheet(establish, count=8).save(OUT / "establish-contact.png")

    # Film: establishing wide shot -> walk with parallax -> wave close-up.
    film_ms = 4000 + 4000 - 500 + 3800 - 500
    walk_start = 3500
    write_wav(WORK / "score.wav", film_ms / 1000 + 0.5,
              [walk_start / 1000 + 0.5 * k for k in range(8)])
    spec = {
        "version": 1, "width": W, "height": H, "fps": 24,
        "shots": [
            {"source": "establish.vixl", "duration": 4000,
             "camera": {"from": [0.5, 0.5, 1.0], "to": [0.6, 0.56, 1.25]}},
            {"source": "walk.vixl", "duration": 4000, "transition": 500,
             "camera": {"from": [0.45, 0.55, 1.15], "to": [0.5, 0.5, 1.0]}},
            {"source": "wave.vixl", "duration": 3800, "transition": 500,
             "camera": {"from": [0.5, 0.5, 1.0], "to": [0.55, 0.42, 1.12]}},
        ],
        "captions": [
            {"text": "Every morning, Pip checks the weather.", "start": 300, "end": 2400, "x": 60,
             "y": 470, "size": 30, "color": "#ffffff"},
            {"text": "Then off along the valley path...", "start": 4100, "end": 6900, "x": 60, "y": 480,
             "size": 30, "color": "#2b2d42"},
            {"text": "made with Vixl", "start": 9400, "end": 10800, "x": 760, "y": 500, "size": 22,
             "color": "#ffffff"},
        ],
        "audio": [{"source": "score.wav", "start": 0, "volume": 0.8}],
    }
    plan = vixl("workflow", "film-plan", request={"spec": spec})
    (OUT / "film-plan.json").write_text(json.dumps(plan, indent=1))
    start = time.time()
    vixl("workflow", "film-export", request={"spec": spec, "output": "pip-film.mp4"})
    print(f"  film: {time.time() - start:.1f}s")
    shutil.move(WORK / "pip-film.mp4", OUT / "pip-film.mp4")

    # Stills from the film for the README (ffmpeg grabs one frame per shot).
    for name, t in [("film-shot1", 2.9), ("film-shot2", 5.5), ("film-shot3", 9.2), ("film-xfade", 7.2)]:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(OUT / "pip-film.mp4"),
                        "-frames:v", "1", str(OUT / f"{name}.png")], check=True)
    shutil.rmtree(WORK / ".vixl-cache", ignore_errors=True)
    (WORK / ".vixl-cache.usage.json").unlink(missing_ok=True)  # the cache's bookkeeping file
    for f in WORK.glob("_*.json"):
        f.unlink()
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"Done: {total / 1e6:.2f} MB in {OUT}")


if __name__ == "__main__":
    main()
