"""Procedural creature art for the Aetherling card set, painted entirely with Vixl operations.

Each creature is a small editable .vixl scene: a radial-gradient sky, watercolor nebula
strokes, a spray starfield, a mountain silhouette (pen path), and a "spirit" built from a
star aura, mirrored wing paths, a gradient-overlaid body and glowing eyes.
"""

import math
import random

from vixl import Project

W, H = 640, 440

ELEMENTS = {
    "Ember": {"main": "#ff6b35", "dark": "#2a0905", "light": "#ffd166", "sky": "#7a1e0e"},
    "Tide": {"main": "#2ec4ff", "dark": "#03182b", "light": "#c9f6ff", "sky": "#0b4f7a"},
    "Grove": {"main": "#6fd08c", "dark": "#071f10", "light": "#e6ffd9", "sky": "#1d5a35"},
    "Storm": {"main": "#b388ff", "dark": "#130a2e", "light": "#f1e6ff", "sky": "#40207a"},
    "Void": {"main": "#ff4fa3", "dark": "#1a0412", "light": "#ffd6ec", "sky": "#5a1040"},
}


def wing_points(rng, span, lift):
    """Right-hand wing as a closed polyline in a local box (origin = shoulder)."""
    feathers = rng.randint(3, 5)
    pts = [[0, 60]]
    for i in range(feathers + 1):
        t = i / feathers
        x = span * (0.35 + 0.65 * t)
        y = 60 - lift * math.sin(math.pi * (0.15 + 0.7 * t)) - 30 * t
        pts.append([x, y])
        if i < feathers:
            pts.append([x - span * 0.04, y + 30 + rng.randint(0, 15)])
    pts.append([span * 0.25, 120])
    return pts


def creature_ops(seed, element):
    rng = random.Random(seed)
    c = ELEMENTS[element]
    cx, cy = W // 2, 225
    ops = [
        {"type": "gradient", "name": "sky", "direction": "radial", "width": W, "height": H,
         "stops": [{"offset": 0, "color": c["sky"]}, {"offset": 0.55, "color": c["dark"]},
                   {"offset": 1, "color": "#000000"}]},
        {"type": "paint-layer", "name": "nebula"},
    ]
    for i in range(4):
        y0 = rng.randint(40, 300)
        ops.append({"type": "paint", "target": "nebula", "brush": "watercolor", "size": rng.randint(90, 160),
                    "color": f"alpha({c['main']}, 0.6)", "seed": seed * 10 + i,
                    "path": f"M{rng.randint(-40, 120)} {y0} C{rng.randint(150, 300)} {y0 - 120} "
                            f"{rng.randint(340, 500)} {y0 + 140} {rng.randint(560, 700)} {rng.randint(40, 300)}"})
    ops.append({"type": "paint-layer", "name": "stars"})
    for i in range(60):
        sx, sy = rng.randint(0, W), rng.randint(0, 300)
        ops.append({"type": "paint", "target": "stars", "brush": "soft-round", "size": rng.choice([3, 4, 5, 7, 10]),
                    "color": c["light"], "seed": seed * 7 + i, "opacity": rng.uniform(0.5, 1.0),
                    "points": [[sx, sy], [sx + 1, sy]]})
    # mountain silhouette
    ridge = [[0, 120]]
    for k in range(1, 9):
        ridge.append([k * W / 8, rng.randint(10, 100)])
    ridge += [[W, 160], [0, 160]]
    ops.append({"type": "pen", "name": "ridge", "points": ridge, "closed": True, "smooth": False,
                "fill": c["dark"], "width": W, "height": 160, "x": 0, "y": H - 160})
    ops.append({"type": "layer-style", "target": "ridge", "name": "outer-glow",
                "settings": {"color": c["main"], "blur": 18, "opacity": 0.55}})
    # aura
    sides = rng.choice([5, 6, 7, 8, 9, 12])
    aura = rng.randint(250, 300)
    ops += [
        {"type": "shape", "name": "aura", "shape": "star", "sides": sides,
         "inner_radius": round(rng.uniform(0.35, 0.6), 2), "width": aura, "height": aura,
         "x": cx - aura // 2, "y": cy - aura // 2, "fill": f"alpha({c['light']}, 0.18)",
         "stroke": f"alpha({c['light']}, 0.7)", "stroke_width": 2},
        {"type": "shape", "name": "halo", "shape": "ellipse", "width": 210, "height": 210,
         "x": cx - 105, "y": cy - 105, "fill": "transparent", "stroke": f"alpha({c['main']}, 0.9)",
         "stroke_width": 4},
        {"type": "layer-style", "target": "halo", "name": "outer-glow", "settings": {"color": c["main"], "blur": 20}},
    ]
    # wings
    span, lift = rng.randint(150, 210), rng.randint(40, 90)
    wp = wing_points(rng, span, lift)
    # The feather tips rise above the shoulder line; the box must hold every point (Vixl rejects
    # points outside a pen's box rather than clipping them).
    top = min(0, math.floor(min(y for _, y in wp)) - 4)
    wp = [[x, y - top] for x, y in wp]
    ops += [
        {"type": "pen", "name": "wing-r", "points": wp, "closed": True, "smooth": True,
         "fill": f"alpha({c['main']}, 0.85)", "stroke": c["light"], "stroke_width": 2,
         "width": span + 20, "height": 140 - top, "x": cx + 20, "y": cy - 80 + top},
        {"type": "duplicate", "target": "wing-r", "name": "wing-l"},
        {"type": "flip", "target": "wing-l", "direction": "horizontal"},
        {"type": "move", "target": "wing-l", "x": cx - 20 - (span + 20), "y": cy - 80 + top},
        {"type": "layer-style", "target": "wing-r", "name": "gradient-overlay",
         "settings": {"start": c["light"], "end": c["main"], "direction": "horizontal", "opacity": 0.6}},
        {"type": "layer-style", "target": "wing-l", "name": "gradient-overlay",
         "settings": {"start": c["main"], "end": c["light"], "direction": "horizontal", "opacity": 0.6}},
    ]
    # body
    bw, bh = rng.randint(90, 130), rng.randint(150, 200)
    body_shape = rng.choice(["ellipse", "shield", "diamond", "hexagon"])
    ops += [
        {"type": "shape", "name": "body", "shape": body_shape, "width": bw, "height": bh,
         "x": cx - bw // 2, "y": cy - bh // 2 + 10, "fill": c["main"]},
        {"type": "layer-style", "target": "body", "name": "gradient-overlay",
         "settings": {"stops": [{"offset": 0, "color": c["light"]}, {"offset": 0.5, "color": c["main"]},
                                {"offset": 1, "color": c["dark"]}]}},
        {"type": "layer-style", "target": "body", "name": "outer-glow", "settings": {"color": c["light"], "blur": 24}},
        {"type": "shape", "name": "crest", "shape": "star", "sides": rng.choice([3, 4, 5]), "inner_radius": 0.4,
         "width": 70, "height": 70, "x": cx - 35, "y": cy - bh // 2 - 40, "fill": c["light"]},
        {"type": "layer-style", "target": "crest", "name": "outer-glow", "settings": {"color": c["main"], "blur": 14}},
    ]
    eye_y, gap, ew = cy - bh // 6, rng.randint(14, 24), rng.randint(16, 24)
    for side, sx in (("l", cx - gap - ew), ("r", cx + gap)):
        ops += [
            {"type": "shape", "name": f"eye-{side}", "shape": "ellipse", "width": ew, "height": ew + 8,
             "x": sx, "y": eye_y, "fill": "#ffffff"},
            {"type": "layer-style", "target": f"eye-{side}", "name": "outer-glow",
             "settings": {"color": "#ffffff", "blur": 12}},
        ]
    ops.append({"type": "vignette", "target": "sky", "strength": 0.6})
    return ops


def make_art(seed, element, path):
    project = Project(W, H, "#000000")
    project.apply(creature_ops(seed, element), detail="compact")
    project.export(str(path), quality=80)
    return path


if __name__ == "__main__":
    import sys

    make_art(int(sys.argv[1]), sys.argv[2], sys.argv[3])
