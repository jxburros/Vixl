"""THE LAST LAMPLIGHTER: a two-page comic drawn, lettered and laid out entirely in Vixl 0.20.0.

Run from the repo root:

    python explorations/12-lamplighter-comic/build.py

Each panel's artwork is its own Vixl scene, rendered at exactly the size of the panel's art slot.
The scenes use the 0.20 material and craft tools: the natural palette helper for sky light,
two-point perspective guides for receding houses and lamps, a painted star field multiplied with
the clone stamp, a custom brick tile captured with pattern-define, built-in patterns (halftone,
stone, hatching, stripes), drawn textures (pencil, charcoal, crayon, ink-wash, stipple, hatch), a
generated character posed with IK, and the parametric shape catalog. The pages are two
comic-layout pages with captions; dialogue is placed with speech bubbles whose tails follow
anchor layers at each speaker.

Outputs go to explorations/12-lamplighter-comic/output/.
"""

import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
PANELS = OUT / "panels"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from vixl import Project  # noqa: E402
from vixl.checks import check_design  # noqa: E402
from vixl.natural_guidance import natural_palette, perspective_guides  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

PAGE_W, PAGE_H = 1200, 1800
PAPER = "#F4ECD8"
INK = "#15171C"
CAPTION_BG = "#FFF1C2"
GOLD = "#F6C453"
FLAME = "#FFB547"
WARM = "#FFE7A3"
NIGHT = "#1B2440"
DIALOGUE = "comic-neue-700"
SHOUT = "bangers-400"

SKY = {time: natural_palette("sky", time)["colors"] for time in ("dusk", "night", "dawn")}
WATER = {time: natural_palette("water", time)["colors"] for time in ("night", "dawn")}
STONE = natural_palette("stone", "dusk")["colors"]


# Shared scene kit ----------------------------------------------------------------------------------
def shape(kind, name, x, y, w, h, **kw):
    return {"type": "shape", "shape": kind, "name": name, "x": x, "y": y, "width": w, "height": h, **kw}


def sky(w, h, stops, name="sky"):
    count = len(stops)
    return [{"type": "gradient", "name": name, "width": w, "height": h, "direction": "vertical",
             "stops": [{"offset": round(i / (count - 1), 4), "color": c} for i, c in enumerate(stops)]}]


def stars(w, h, seed, count=36, region=None):
    """A few painted stars, rasterized, then multiplied across the sky with the clone stamp."""
    rng = random.Random(seed)
    x0, y0, rw, rh = region or (0, 0, w * 0.3, h * 0.35)
    ops = [{"type": "paint-layer", "name": "stars"}]
    for _ in range(count):
        x, y = x0 + rng.random() * rw, y0 + rng.random() * rh
        ops.append({"type": "paint", "target": "stars", "brush": "soft-round", "size": rng.choice([2, 3, 3, 5]),
                    "color": "#FFF6D8", "points": [[x, y], [x + 0.4, y]], "seed": seed})
    sx, sy = x0 + rw / 2, y0 + rh / 2
    ops += [{"type": "rasterize", "target": "stars"},
            {"type": "clone-stamp", "target": "stars", "source": [round(sx), round(sy)], "size": round(min(rw, rh)),
             "hardness": 0.3, "opacity": 0.9, "brush": "round", "aligned": False,
             "strokes": [[[round(sx + rw * 1.1), round(sy - rh * 0.2)], [round(sx + rw * 2.2), round(sy + rh * 0.1)]],
                         [[round(sx + rw * 2.6), round(sy - rh * 0.1)], [round(min(w - 20, sx + rw * 3.0)),
                                                                          round(sy)]]]}]
    return ops


def brick_tile():
    """A 40 × 20 running-bond brick, captured as a reusable document pattern, then hidden."""
    return [
        shape("rectangle", "tile-brick", 0, 0, 40, 20, fill="#7B3F2F"),
        shape("rectangle", "tile-bed", 0, 9, 40, 2, fill="#C7B39A"),
        shape("rectangle", "tile-head-1", 19, 0, 2, 9, fill="#C7B39A"),
        shape("rectangle", "tile-head-2", 0, 11, 1, 9, fill="#C7B39A"),
        shape("rectangle", "tile-head-3", 39, 11, 1, 9, fill="#C7B39A"),
        {"type": "group", "name": "brick-tile", "targets": ["tile-brick", "tile-bed", "tile-head-1", "tile-head-2",
                                                            "tile-head-3"]},
        {"type": "pattern-define", "name": "brick", "target": "brick-tile", "seamless": True},
        {"type": "hide", "target": "brick-tile"},
    ]


def lamp_post(name, x, base_y, height, lit=True):
    """Post, crossbar and lantern; the lantern is a notched frame around a flame with a glow."""
    s = height / 300
    lw, lh = 44 * s, 60 * s
    lx, ly = x - lw / 2, base_y - height
    ops = [
        shape("rectangle", f"{name}-post", x - 5 * s, ly + lh, 10 * s, height - lh, fill=INK),
        shape("rounded-rectangle", f"{name}-foot", x - 16 * s, base_y - 14 * s, 32 * s, 14 * s, fill=INK,
              radius=[6 * s, 6 * s, 0, 0]),
        shape("isosceles-triangle", f"{name}-cap", lx - 6 * s, ly - 18 * s, lw + 12 * s, 20 * s, fill=INK),
    ]
    if lit:
        ops.append(shape("ellipse", f"{name}-glow", x - 90 * s, ly - 60 * s, 180 * s, 180 * s, fill="#FFD27A33"))
        ops.append({"type": "look", "target": f"{name}-glow", "look": "glow", "color": WARM, "amount": 0.6})
    ops += [
        shape("notched-rectangle", f"{name}-lantern", lx, ly, lw, lh, fill=WARM if lit else "#5B6275",
              stroke=INK, stroke_width=max(1.5, 3 * s), notch=6 * s),
    ]
    if lit:
        ops.append(shape("flame", f"{name}-flame", x - 9 * s, ly + 14 * s, 18 * s, 32 * s, fill=FLAME))
    return ops


def house(name, x, ground, w, h, fill, seed, lit_window=True):
    ops = [shape("house", name, x, ground - h, w, h, fill=fill),
           {"type": "pattern-fill", "target": name, "name": f"{name}-brick", "pattern": "brick",
            "scale": max(0.35, w / 260), "opacity": 0.9},
           {"type": "drawn-texture", "target": name, "name": f"{name}-hatch", "preset": "hatch", "color": NIGHT,
            "seed": seed, "strength": 0.45, "scale": max(0.5, w / 200)}]
    if lit_window:
        ww = w * 0.22
        ops.append(shape("rounded-rectangle", f"{name}-window", x + w * 0.2, ground - h * 0.52, ww, ww * 1.2,
                         fill=WARM, radius=[ww / 2, ww / 2, 2, 2], stroke=INK, stroke_width=max(1, w / 120)))
    return ops


def keeper(name, x, y, height, reach=None, arm="right", **colors):
    """The lamplighter: a generated standard-parts character with a wider shoulder range for IK."""
    palette = {"outfit": "#2F4A3A", "skin": "#C99A74", "hair": "#4A2F22", **colors}
    ops = [{"type": "character", "name": name, "x": round(x), "y": round(y), "height": round(height),
            "colors": palette}]
    if reach:
        side = f"{arm}-upper-arm"
        ops.append({"_rig": name, "arm": arm})
        ops.append({"type": "character-ik", "target": name, "chain": [side, f"{arm}-lower-arm"], "point": reach,
                    "bend": 1 if arm == "right" else -1})
    return ops


def resolve(p, ops):
    """Apply ops, widening a shoulder's joint limits (from the generated rig) before any IK reach."""
    batch = []
    for op in ops:
        if "_rig" in op:
            if batch:
                p.apply(batch, detail="brief")
                batch = []
            bones = p.layer(op["_rig"])["character"]["bones"]
            side = op["arm"]
            upper = bones[f"{side}-upper-arm"]
            p.apply({"type": "character-rig", "target": op["_rig"], "bones": {
                f"{side}-upper-arm": {"origin": upper["origin"], "length": upper["length"], "limits": [-185, 185]},
                f"{side}-lower-arm": {"parent": f"{side}-upper-arm", "length": bones[f"{side}-lower-arm"]["length"],
                                      "limits": [-150, 150]},
                f"{side}-hand": {"parent": f"{side}-lower-arm", "length": bones[f"{side}-hand"]["length"],
                                 "limits": [-70, 70]}}}, detail="brief")
        else:
            batch.append(op)
    if batch:
        p.apply(batch, detail="brief")


def cap(p, who, color="#1F2B3A"):
    hx, hy, hw, hh = p.spatial(target=f"{who}/head", mode="canvas")["layers"][0]["bounds"]
    return [shape("half-circle", f"{who}-cap", hx - hw * 0.06, hy - hh * 0.12, hw * 1.12, hh * 0.42, fill=color),
            shape("rounded-rectangle", f"{who}-brim", hx - hw * 0.12, hy + hh * 0.24, hw * 0.75, hh * 0.1,
                  fill=color, radius=4)]


def head_point(p, who, dx=0.5, dy=0.75):
    hx, hy, hw, hh = p.spatial(target=f"{who}/head", mode="canvas")["layers"][0]["bounds"]
    return [hx + hw * dx, hy + hh * dy]


# Panel scenes --------------------------------------------------------------------------------------
# Each scene returns (project, anchors) where anchors are named points in scene pixels.
def scene_establish(w, h):
    p = Project(w, h, NIGHT)
    horizon = h * 0.62
    guides = perspective_guides({"width": w, "height": h, "horizon": horizon, "points": 2,
                                 "vanishing": [[w * 1.35, horizon], [-w * 0.6, horizon]],
                                 "depths": [1, 1.5, 2.2, 3.3, 5], "reference_size": h * 0.46})
    install_font(p, "Bangers", 400)
    # Night overhead, the natural dusk palette (dark to light) down to the horizon glow.
    ops = sky(w, horizon, [SKY["night"][0], *SKY["dusk"]]) + guides["operations"]
    ops += [
        {"type": "pattern-fill", "target": "sky", "name": "sky-dots", "pattern": "halftone", "spacing": 9,
         "colors": ["#FFFFFF14", "#00000000"], "opacity": 0.8},
        *stars(w, h, seed=7, region=(30, 20, w * 0.22, h * 0.28)),
        shape("crescent", "moon", w * 0.12, h * 0.1, h * 0.16, h * 0.16, fill="#FFF3C8"),
        # Far headland with a small lighthouse and its beam.
        shape("ellipse", "headland", w * 0.55, horizon - h * 0.05, w * 0.6, h * 0.2, fill="#28304D"),
        shape("rectangle", "far-tower", w * 0.83, horizon - h * 0.2, w * 0.022, h * 0.17, fill="#E9E4D4"),
        {"type": "distort", "target": "far-tower", "kind": "corner-pin",
         "corners": [[w * 0.004, 0], [w * 0.018, 0], [w * 0.022, h * 0.17], [0, h * 0.17]]},
        shape("rectangle", "far-beam", w * 0.84, horizon - h * 0.25, w * 0.16, h * 0.08, fill="#FFE7A355"),
        {"type": "distort", "target": "far-beam", "kind": "corner-pin",
         "corners": [[0, h * 0.035], [w * 0.16, 0], [w * 0.16, h * 0.08], [0, h * 0.045]]},
        shape("rectangle", "sea", w * 0.5, horizon - h * 0.005, w * 0.5, h * 0.03, fill=WATER["night"][1]),
        shape("wave", "sea-wave", w * 0.5, horizon - 2, w * 0.5, 10, amplitude=3, wavelength=40,
              stroke="#9FB3D988", stroke_width=2, fill="transparent"),
        # The quay: cobbles from the stone pattern, then pencil grain.
        shape("rectangle", "quay", 0, horizon + h * 0.02, w, h - horizon, fill=STONE[1]),
        {"type": "pattern-fill", "target": "quay", "name": "cobbles", "pattern": "stone", "scale": 1.2,
         "colors": [STONE[2], STONE[0]], "opacity": 0.7, "seed": 3},
        {"type": "drawn-texture", "target": "quay", "name": "quay-pencil", "preset": "pencil", "color": INK,
         "seed": 5, "strength": 0.4, "grain": 0.6},
        *brick_tile(),
    ]
    # Houses recede toward the right vanishing point; sizes come from the perspective helper.
    sizes = [s["size"] for s in guides["sizes"]]
    near = h * 0.84

    def ground_at(size):
        # Equal-sized objects shrink with depth, and so does their ground line's drop below the horizon.
        return horizon + (near - horizon) * size / sizes[0]

    x = w * 0.02
    for i, size in enumerate(sizes):
        ground = ground_at(size)
        width = size * 0.82
        ops += house(f"house-{i}", x, ground, width, size, ["#7B3F2F", "#6E4A3A", "#8A5A3C", "#5E3E36", "#7A5B48"][i],
                     seed=10 + i, lit_window=i != 2)
        x += width * 1.02
    # Lamp posts receding along the quay, from big and lit to small.
    for i, size in enumerate(sizes[:4]):
        ops += lamp_post(f"lamp-{i}", w * 0.6 + sum(sizes[:i]) * 0.55, ground_at(size) + h * 0.12 * size / sizes[0],
                         size * 0.95, lit=i != 0)
    # Title lettering arched across the sky.
    ops += [{"type": "text", "name": "title", "text": "THE LAST LAMPLIGHTER", "font": SHOUT, "size": round(h * 0.15),
             "color": GOLD, "x": w * 0.24, "y": h * 0.06},
            {"type": "text-layout", "target": "title", "width": w * 0.56, "height": h * 0.24, "warp": "arc",
             "amount": 0.25},
            {"type": "layer-style", "target": "title", "name": "stroke", "settings": {"color": INK, "width": 6}},
            {"type": "layer-style", "target": "title", "name": "drop-shadow",
             "settings": {"color": "#000000", "opacity": 0.65, "dx": 5, "dy": 6, "blur": 0}}]
    resolve(p, ops)
    return p, {}


def scene_lighting(w, h):
    p = Project(w, h, NIGHT)
    ops = [*brick_tile(),
           shape("rectangle", "wall", 0, 0, w, h * 0.82, fill="#7B3F2F"),
           {"type": "pattern-fill", "target": "wall", "name": "wall-brick", "pattern": "brick", "scale": 1.4},
           {"type": "drawn-texture", "target": "wall", "name": "wall-shade", "preset": "charcoal", "color": NIGHT,
            "seed": 21, "strength": 0.55, "grain": 0.7},
           shape("rectangle", "street", 0, h * 0.82, w, h * 0.18, fill=STONE[1]),
           {"type": "pattern-fill", "target": "street", "name": "street-stone", "pattern": "stone", "scale": 0.9,
            "colors": [STONE[2], STONE[0]], "opacity": 0.6, "seed": 4},
           *lamp_post("lamp", w * 0.7, h * 0.95, h * 0.82, lit=True)]
    ops += keeper("wren", w * 0.12, h * 0.36, h * 0.56, reach=[w * 0.42, -h * 0.02])
    resolve(p, ops)
    # The lighting pole runs from Wren's raised hand to the lantern.
    hand = p.spatial(target="wren/right-hand", mode="canvas")["layers"][0]["bounds"]
    hx, hy = hand[0] + hand[2] / 2, hand[1] + hand[3] / 2
    lantern = p.spatial(target="lamp-lantern", mode="canvas")["layers"][0]["bounds"]
    tip = [lantern[0] + 4, lantern[1] + lantern[3] * 0.8]
    p.apply([{"type": "pen", "name": "pole", "points": [[hx - (tip[0] - hx) * 0.25, hy - (tip[1] - hy) * 0.25],
                                                         tip], "stroke": "#5A3B22", "stroke_width": 7,
              "line_cap": "round", "fill": "transparent"},
             shape("sparkle", "spark", tip[0] - 18, tip[1] - 18, 36, 36, fill="#FFF6D8"),
             *cap(p, "wren")], detail="brief")
    return p, {"wren": head_point(p, "wren")}


def scene_flame(w, h):
    p = Project(w, h, "#2A1E14")
    cx = w * 0.5
    ops = [
        shape("sunburst", "burst", cx - w * 0.7, h * 0.05 - w * 0.2, w * 1.4, w * 1.4, fill="#FFB54722", count=28),
        shape("notched-rectangle", "glass", cx - w * 0.3, h * 0.1, w * 0.6, h * 0.72, fill="#FFE7A340",
              stroke=INK, stroke_width=10, notch=30),
        {"type": "drawn-texture", "target": "glass", "name": "glass-crayon", "preset": "crayon", "color": "#FFFFFF",
         "seed": 31, "strength": 0.35, "grain": 0.8},
        shape("flame", "flame", cx - w * 0.15, h * 0.22, w * 0.3, h * 0.46, fill=FLAME),
        shape("teardrop", "flame-core", cx - w * 0.06, h * 0.42, w * 0.12, h * 0.2, fill="#FFF6D0"),
        shape("sparkle", "spark-1", cx + w * 0.18, h * 0.2, 40, 40, fill="#FFF6D8"),
        shape("sparkle", "spark-2", cx - w * 0.26, h * 0.32, 26, 26, fill="#FFF6D8"),
        # A cat on the ledge, built from catalog parts.
        shape("rectangle", "ledge", 0, h * 0.84, w, h * 0.16, fill="#3B2A1C"),
        {"type": "drawn-texture", "target": "ledge", "name": "ledge-ink", "preset": "ink-wash", "color": "#120C08",
         "seed": 32, "strength": 0.6},
        shape("ellipse", "cat-body", w * 0.06, h * 0.7, w * 0.26, h * 0.16, fill=INK),
        shape("ellipse", "cat-head", w * 0.22, h * 0.6, w * 0.15, w * 0.15, fill=INK),
        shape("isosceles-triangle", "cat-ear-1", w * 0.225, h * 0.565, w * 0.05, w * 0.06, fill=INK),
        shape("isosceles-triangle", "cat-ear-2", w * 0.305, h * 0.565, w * 0.05, w * 0.06, fill=INK),
        shape("lens", "cat-eye-1", w * 0.25, h * 0.635, w * 0.03, w * 0.022, fill=GOLD),
        shape("lens", "cat-eye-2", w * 0.31, h * 0.635, w * 0.03, w * 0.022, fill=GOLD),
        {"type": "pen", "name": "cat-tail", "x": w * 0.01, "y": h * 0.6, "smooth": True, "fill": "transparent",
         "points": [[w * 0.07, h * 0.18], [w * 0.01, h * 0.1], [w * 0.03, h * 0.02], [w * 0.08, 0]],
         "stroke": INK, "stroke_width": 12, "line_cap": "round", "width_profile": [[0, 1], [1, 0.45]]},
    ]
    resolve(p, ops)
    return p, {"cat": [w * 0.3, h * 0.62]}


def scene_truck(w, h):
    p = Project(w, h, NIGHT)
    road = h * 0.78
    ops = sky(w, h * 0.8, [SKY["night"][0], SKY["night"][2], SKY["dusk"][3]]) + [
        {"type": "pattern-fill", "target": "sky", "name": "sky-halftone", "pattern": "halftone", "spacing": 12,
         "colors": ["#FFFFFF18", "#00000000"], "opacity": 1},
        shape("rectangle", "road", 0, road, w, h - road, fill="#2E3242"),
        shape("dashed-line", "road-line", 0, road + (h - road) * 0.45, w, 8, stroke="#E8E2CF", stroke_width=6,
              dash=[40, 30]),
        shape("speed-lines", "speed", w * 0.02, h * 0.3, w * 0.3, h * 0.36, fill="#E8E2CF88", count=9),
        # Headlight beams: corner-pinned wedges ahead of the van.
        shape("rectangle", "beam", w * 0.55, h * 0.36, w * 0.4, h * 0.5, fill="#FFF3B055"),
        {"type": "distort", "target": "beam", "kind": "corner-pin",
         "corners": [[0, h * 0.2], [w * 0.4, 0], [w * 0.4, h * 0.5], [0, h * 0.26]]},
        # The van: chamfered body, cab, windows, wheels and a lightning-bolt company mark.
        shape("rounded-rectangle", "van-body", w * 0.22, h * 0.34, w * 0.26, h * 0.4, fill="#D9D2BE",
              radius=[18, 6, 6, 18], stroke=INK, stroke_width=5),
        shape("rounded-rectangle", "van-cab", w * 0.47, h * 0.45, w * 0.1, h * 0.29, fill="#D9D2BE",
              radius=[4, 40, 6, 0], stroke=INK, stroke_width=5),
        shape("rounded-rectangle", "van-window", w * 0.49, h * 0.49, w * 0.055, h * 0.1, fill="#9FC3E0",
              radius=[2, 26, 2, 2], stroke=INK, stroke_width=3),
        shape("lightning", "van-bolt", w * 0.31, h * 0.4, w * 0.06, h * 0.26, fill=GOLD, stroke=INK,
              stroke_width=3),
        shape("ring", "wheel-1", w * 0.26, h * 0.67, h * 0.17, h * 0.17, fill=INK, thickness=0.35),
        shape("ring", "wheel-2", w * 0.48, h * 0.67, h * 0.17, h * 0.17, fill=INK, thickness=0.35),
        shape("ellipse", "headlight", w * 0.555, h * 0.58, h * 0.06, h * 0.06, fill="#FFF6D0"),
        {"type": "drawn-texture", "target": "van-body", "name": "van-stipple", "preset": "stipple", "color": INK,
         "seed": 41, "strength": 0.4},
        *lamp_post("old-lamp", w * 0.86, road + 6, h * 0.66, lit=True),
    ]
    ops += keeper("wren", w * 0.9, h * 0.38, h * 0.42, reach=[-h * 0.02, -h * 0.02], arm="left")
    resolve(p, ops)
    p.apply(cap(p, "wren"), detail="brief")
    return p, {"driver": [w * 0.515, h * 0.53], "wren": head_point(p, "wren")}


def scene_storm(w, h):
    p = Project(w, h, "#10141F")
    horizon = h * 0.55
    ops = sky(w, horizon + 4, ["#0B0E16", "#232B3D", "#3C4560"]) + [
        shape("cloud", "cloud-1", -w * 0.05, -h * 0.05, w * 0.45, h * 0.32, fill="#2A3245"),
        shape("cloud", "cloud-2", w * 0.32, -h * 0.08, w * 0.5, h * 0.34, fill="#252C3E"),
        shape("cloud", "cloud-3", w * 0.68, -h * 0.02, w * 0.4, h * 0.3, fill="#2E3650"),
        *[{"type": "drawn-texture", "target": f"cloud-{i}", "name": f"cloud-{i}-charcoal", "preset": "charcoal",
           "color": "#0B0E16", "seed": 50 + i, "strength": 0.6, "grain": 0.8} for i in (1, 2, 3)],
        shape("lightning", "bolt-1", w * 0.42, h * 0.12, w * 0.06, h * 0.36, fill="#F3F0FF"),
        shape("lightning", "bolt-2", w * 0.58, h * 0.16, w * 0.035, h * 0.24, fill="#D9D4FF"),
        shape("rectangle", "sea", 0, horizon, w, h - horizon, fill=WATER["night"][0]),
    ]
    for i in range(6):
        y = horizon + i * (h - horizon) / 6
        ops.append(shape("wave", f"swell-{i}", -20, y, w + 40, 22 + i * 6, amplitude=6 + i * 3,
                         wavelength=70 + i * 26, phase=i * 0.7, stroke="#C9D6F0" if i % 2 else "#7F93BD",
                         stroke_width=2 + i * 0.6, fill="transparent"))
    ops += [
        {"type": "drawn-texture", "target": "sea", "name": "sea-wash", "preset": "ink-wash", "color": "#05070C",
         "seed": 61, "strength": 0.55},
        # The lighthouse, dark: a tapered tower with painted stripes.
        shape("rectangle", "tower", w * 0.76, h * 0.18, w * 0.12, h * 0.6, fill="#E9E4D4"),
        {"type": "pattern-fill", "target": "tower", "name": "tower-stripes", "pattern": "stripes", "spacing": 60,
         "rotation": 90, "colors": ["#B33A3A", "#00000000"], "opacity": 0.95},
        {"type": "distort", "target": "tower", "kind": "corner-pin",
         "corners": [[w * 0.02, 0], [w * 0.1, 0], [w * 0.12, h * 0.6], [0, h * 0.6]]},
        shape("rounded-rectangle", "lantern-room", w * 0.775, h * 0.08, w * 0.09, h * 0.1, fill="#3A4258",
              radius=[30, 30, 0, 0], stroke=INK, stroke_width=4),
        shape("rectangle", "gallery", w * 0.765, h * 0.175, w * 0.11, h * 0.02, fill=INK),
        shape("rectangle", "rock", w * 0.7, h * 0.76, w * 0.3, h * 0.24, fill="#1E2230"),
        # A small boat in trouble.
        shape("rounded-rectangle", "hull", w * 0.2, h * 0.68, w * 0.12, h * 0.05, fill="#5A3B22",
              radius=[0, 0, 30, 30], stroke=INK, stroke_width=3),
        {"type": "rotate", "target": "hull", "value": -8},
        shape("isosceles-triangle", "sail", w * 0.235, h * 0.53, w * 0.05, h * 0.15, fill="#E9E4D4", stroke=INK,
              stroke_width=3),
        {"type": "skew", "target": "sail", "x": -12},
    ]
    # Rain: tapered pen streaks. (A pattern fill is clipped to its source's alpha, so it can't rain
    # over a transparent sheet.)
    rng = random.Random(64)
    for i in range(140):
        x, y, length = rng.uniform(-40, w), rng.uniform(-20, h), rng.uniform(26, 60)
        ops.append({"type": "pen", "name": f"rain-{i}", "x": x, "y": y, "fill": "transparent",
                    "points": [[0, 0], [length * 0.32, length]], "stroke": "#C9D6F0", "stroke_width": 2.2,
                    "line_cap": "round", "taper_start": 0.1})
    ops.append({"type": "group", "name": "rain", "targets": [f"rain-{i}" for i in range(140)]})
    ops.append({"type": "opacity", "target": "rain", "value": 0.55})
    resolve(p, ops)
    return p, {"boat": [w * 0.255, h * 0.6]}


def scene_climb(w, h):
    p = Project(w, h, "#1C1A22")
    ops = [
        shape("rectangle", "wall", 0, 0, w, h, fill="#3B3A48"),
        {"type": "drawn-texture", "target": "wall", "name": "wall-hatch", "preset": "hatch", "color": "#0E0D12",
         "seed": 71, "strength": 0.6, "scale": 1.3},
        shape("stairs", "stairs", w * 0.05, h * 0.45, w * 0.9, h * 0.55, count=7, fill="#6B6478"),
        {"type": "drawn-texture", "target": "stairs", "name": "stairs-pencil", "preset": "pencil", "color": INK,
         "seed": 72, "strength": 0.5},
    ]
    ops += keeper("wren", w * 0.44, h * 0.2, h * 0.42, reach=[h * 0.22, -h * 0.1])
    resolve(p, ops)
    # Stand Wren on the step below: hit-test down from the feet to the first rendered stair pixel
    # ("ink" bounds; the default box test would hit the empty corner of the stepped shape).
    foot = p.spatial(target="wren/left-foot", mode="canvas")["layers"][0]["bounds"]
    fx, feet = foot[0] + foot[2] / 2, foot[1] + foot[3]
    stairs_id = p.layer("stairs")["id"]

    def on_stairs(y):
        return any(hit["id"] == stairs_id for hit in p.spatial(mode="hit", point=[fx, y], bounds="ink")["hits"])

    y = round(feet)
    step = -2 if on_stairs(y) else 2  # inside the riser: climb to the tread; in the air: drop to it
    while 0 < y < h and on_stairs(y) == (step < 0):
        y += step
    p.apply({"type": "move", "target": "wren", "x": 0, "y": y - feet, "relative": True}, detail="brief")
    hand = p.spatial(target="wren/right-hand", mode="canvas")["layers"][0]["bounds"]
    hx, hy = hand[0] + hand[2] / 2, hand[1]
    p.apply([shape("ellipse", "glow", hx - w * 0.3, hy - 50 - w * 0.3, w * 0.6, w * 0.6, fill="#FFD27A30"),
             {"type": "look", "target": "glow", "look": "glow", "color": WARM, "amount": 0.7},
             {"type": "reorder", "target": "glow", "below": "wren"},
             *cap(p, "wren"),
             shape("rectangle", "lantern-handle", hx - 2, hy - 30, 4, 30, fill=INK),
             shape("notched-rectangle", "lantern", hx - 22, hy - 76, 44, 52, fill=WARM, stroke=INK, stroke_width=3,
                   notch=6),
             shape("flame", "lantern-flame", hx - 8, hy - 66, 16, 30, fill=FLAME)], detail="brief")
    return p, {"wren": head_point(p, "wren")}


def scene_lens(w, h):
    p = Project(w, h, "#0F1E33")
    cx, cy = w * 0.5, h * 0.48
    ops = [shape("sunburst", "burst", cx - w * 0.8, cy - w * 0.8, w * 1.6, w * 1.6, fill="#FFD27A2E", count=36)]
    for i, (rw, rh) in enumerate([(0.86, 0.9), (0.7, 0.74), (0.54, 0.58), (0.38, 0.42), (0.22, 0.26)]):
        ops.append(shape("lens", f"ring-{i}", cx - w * rw / 2, cy - h * rh / 2, w * rw, h * rh, fill="#7FB2FF18",
                         stroke="#E8F1FF" if i % 2 == 0 else "#7FB2FF", stroke_width=5 if i % 2 == 0 else 3,
                         **({} if i % 2 == 0 else {"dash": [14, 8]})))
    ops += [shape("flame", "flame", cx - w * 0.07, cy - h * 0.12, w * 0.14, h * 0.22, fill=FLAME),
            shape("teardrop", "core", cx - w * 0.03, cy - h * 0.01, w * 0.06, h * 0.09, fill="#FFF6D0")]
    for i in range(6):
        ops.append(shape("sparkle", f"spark-{i}", cx + (i - 2.5) * w * 0.14, cy + (-1) ** i * h * 0.3, 30, 30,
                         fill="#FFF6D8"))
    ops += keeper("wren", w * 0.04, h * 0.42, h * 0.6, reach=[h * 0.32, h * 0.02])
    resolve(p, ops)
    p.apply(cap(p, "wren"), detail="brief")
    return p, {"wren": head_point(p, "wren")}


def scene_dawn(w, h):
    p = Project(w, h, "#22304F")
    horizon = h * 0.6
    ops = sky(w, horizon + 4, SKY["dawn"]) + [
        shape("half-circle", "sun", w * 0.12, horizon - h * 0.1, h * 0.2, h * 0.1, fill="#FFD27A"),
        shape("rectangle", "sea", 0, horizon, w, h - horizon, fill=WATER["dawn"][1]),
        {"type": "pattern-fill", "target": "sea", "name": "sea-lines", "pattern": "stripes", "spacing": 14,
         "rotation": 90, "colors": ["#FFFFFF22", "#00000000"], "opacity": 1},
        # The lit lighthouse with a sweeping beam across the morning sea.
        shape("rectangle", "tower", w * 0.8, h * 0.2, w * 0.07, h * 0.5, fill="#E9E4D4"),
        {"type": "pattern-fill", "target": "tower", "name": "tower-stripes", "pattern": "stripes", "spacing": 48,
         "rotation": 90, "colors": ["#B33A3A", "#00000000"], "opacity": 0.95},
        {"type": "distort", "target": "tower", "kind": "corner-pin",
         "corners": [[w * 0.012, 0], [w * 0.058, 0], [w * 0.07, h * 0.5], [0, h * 0.5]]},
        shape("rounded-rectangle", "lantern-room", w * 0.808, h * 0.12, w * 0.054, h * 0.09, fill=WARM,
              radius=[20, 20, 0, 0], stroke=INK, stroke_width=3),
        shape("rectangle", "beam", w * 0.3, h * 0.06, w * 0.52, h * 0.2, fill="#FFF3B066"),
        {"type": "distort", "target": "beam", "kind": "corner-pin",
         "corners": [[0, 0], [w * 0.52, h * 0.07], [w * 0.52, h * 0.11], [0, h * 0.2]]},
        shape("rectangle", "headland", w * 0.66, h * 0.68, w * 0.34, h * 0.32, fill="#2B2F3F"),
        {"type": "drawn-texture", "target": "headland", "name": "headland-stipple", "preset": "stipple",
         "color": "#0E1018", "seed": 81, "strength": 0.5},
        # Safe boat and the town's last lamps along the far quay.
        shape("half-circle", "hull", w * 0.42, h * 0.7, w * 0.08, h * 0.04, fill="#5A3B22"),
        {"type": "rotate", "target": "hull", "value": 180},
        shape("isosceles-triangle", "sail", w * 0.445, h * 0.6, w * 0.035, h * 0.1, fill="#F4ECD8"),
        shape("rectangle", "quay", 0, h * 0.88, w * 0.62, h * 0.12, fill="#3A3442"),
    ]
    for i in range(7):
        ops += lamp_post(f"quay-lamp-{i}", w * 0.04 + i * w * 0.085, h * 0.89, h * 0.14, lit=True)
    ops += keeper("wren", w * 0.835, h * 0.075, h * 0.1, outfit="#1E2A22")
    resolve(p, ops)
    return p, {"wren": head_point(p, "wren")}


# Pages ----------------------------------------------------------------------------------------------
PAGES = [
    [
        {"scene": scene_establish, "span": 2, "caption": "Port Halloran. The last night of the gas lamps."},
        {"scene": scene_lighting, "dialogue": [("wren", "Forty-one... forty-two.", "speech", (0.5, 0.06))]},
        {"scene": scene_flame, "dialogue": [("cat", "Warm.", "thought", (0.55, 0.12))]},
        {"scene": scene_truck, "span": 2, "caption": "By morning the whole town would be electric.",
         "dialogue": [("driver", "MAKE WAY! NEW LIGHTS!", "shout", (0.03, 0.04)),
                      ("wren", "...so this is goodbye.", "whisper", (0.66, 0.06))]},
    ],
    [
        {"scene": scene_storm, "span": 2, "caption": "Then the storm took the power. All of it.",
         "dialogue": [("boat", "THE LIGHTHOUSE IS DARK!", "shout", (0.03, 0.2))]},
        {"scene": scene_climb, "dialogue": [("wren", "Some lights you keep by hand.", "speech", (0.04, 0.04))]},
        {"scene": scene_lens, "dialogue": [("wren", "Forty-three.", "thought", (0.56, 0.06))]},
        {"scene": scene_dawn, "span": 2, "caption": "The lighthouse kept its lamp. Wren kept the matches.",
         "dialogue": [("wren", "goodnight, lamps", "whisper", (0.56, 0.2))]},
    ],
]
LAYOUT = {"columns": 2, "gutter": 22, "margin": 44, "caption_size": 24, "border": INK, "border_width": 6,
          "background": PAPER}


def art_boxes(page_spec):
    """Lay the page out once without artwork to learn each art slot's exact pixel box."""
    probe = Project(PAGE_W, PAGE_H, PAPER)
    panels = [{k: v for k, v in panel.items() if k in ("span", "caption")} for panel in page_spec]
    probe.apply({"type": "comic-layout", "name": "probe", "panels": panels, **LAYOUT}, detail="brief")
    boxes = []
    for i in range(len(page_spec)):
        boxes.append(probe.spatial(target=f"probe/panel-{i + 1}/art", mode="canvas")["layers"][0]["bounds"])
    return boxes


def build():
    PANELS.mkdir(parents=True, exist_ok=True)
    p = Project(PAGE_W, PAGE_H, PAPER)
    install_font(p, "Comic Neue", 700, role="body")
    install_font(p, "Bangers", 400, role="heading")
    report = {"panels": []}
    for page_index, page_spec in enumerate(PAGES, start=1):
        page = f"page-{page_index}"
        p.apply({"type": "page", "action": "add", "name": page}, detail="brief")
        boxes = art_boxes(page_spec)
        panels, bubbles = [], []
        for i, (panel, box) in enumerate(zip(page_spec, boxes), start=1):
            x, y, w, h = (round(v) for v in box)
            scene, anchors = panel["scene"](w, h)
            path = PANELS / f"{page}-panel-{i}.png"
            scene.render().save(path)
            scene.save(PANELS / f"{page}-panel-{i}.vixl")
            rel = str(path.relative_to(ROOT))
            panels.append({"image": rel, **{k: v for k, v in panel.items() if k in ("span", "caption")}})
            for j, (who, text, style, (fx, fy)) in enumerate(panel.get("dialogue", []), start=1):
                ax, ay = anchors[who]
                bubbles.append((f"{page}/p{i}-anchor-{j}", x + ax, y + ay, f"{page}/p{i}-line-{j}", text, style,
                                x + fx * w, y + fy * h, w))
            report["panels"].append({"page": page_index, "panel": i, "art_box": [x, y, w, h], "file": rel})
        p.apply({"type": "comic-layout", "name": page, "panels": panels, "page": page, **LAYOUT}, detail="brief")
        # Captions: Comic Neue on warm paper instead of the generated white.
        restyle = []
        for i, panel in enumerate(page_spec, start=1):
            if "caption" in panel:
                restyle += [{"type": "text", "target": f"{page}/panel-{i}/caption", "font": DIALOGUE, "page": page},
                            {"type": "solid", "target": f"{page}/panel-{i}/caption-background",
                             "color": CAPTION_BG, "page": page}]
        p.apply(restyle, detail="brief")
        # Dialogue: an invisible anchor at each speaker, and a bubble whose tail follows it.
        ops = []
        for anchor, ax, ay, name, text, style, bx, by, panel_w in bubbles:
            font = SHOUT if style == "shout" else DIALOGUE
            size = 34 if style == "shout" else 25
            ops += [{"type": "shape", "shape": "ellipse", "name": anchor, "x": ax - 2, "y": ay - 2, "width": 4,
                     "height": 4, "fill": "#00000000", "page": page},
                    {"type": "speech-bubble", "name": name, "text": text, "anchor": anchor, "style": style,
                     "x": round(bx), "y": round(by), "font": font, "size": size, "color": INK,
                     "max_width": round(min(panel_w * 0.62, 460)), "padding": 48 if style == "shout" else 16,
                     "fill": "#FFFFFF", "stroke": INK, "page": page}]
        p.apply(ops, detail="brief")
    p.apply({"type": "page", "action": "select", "page": "page-1"}, detail="brief")
    return p, report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p, report = build()
    p.save(OUT / "last-lamplighter.vixl")
    for page in ("page-1", "page-2"):
        p.render(page=page).save(OUT / f"last-lamplighter-{page}.png")
    p.export(OUT / "last-lamplighter.pdf", overwrite=True)
    p.export(OUT / "last-lamplighter-spread.png", page="all", overwrite=True)
    checks = {page: check_design(p, page=page, checks=["bounds", "contrast", "blanks", "fonts", "captions"])
              for page in ("page-1", "page-2")}
    (OUT / "last-lamplighter.check.json").write_text(json.dumps(checks, indent=2, default=str))
    (OUT / "panels.json").write_text(json.dumps(report, indent=2))
    for page, result in checks.items():
        print(page, "passed" if result["passed"] else "issues", result["errors"], "errors", result["warnings"],
              "warnings")


if __name__ == "__main__":
    main()
