"""Pixel-art RPG asset pack built entirely with Vixl operations.

Run from the repo root:  python explorations/04-pixel-rpg/build.py

Produces (in explorations/04-pixel-rpg/output/):
  hero.vixl + walk/idle/attack GIF/APNG clips and a sprite sheet (+JSON)
  enemies.vixl palette-swapped slimes/bats + hero variants, animated lineup
  tileset.vixl tiles drawn with pixel-draw (pixel/line/rect/fill), sheet + 4x
  map.vixl tile-map scene built with repeat/repeated groups, frame + timeline animations
  title.vixl title screen with Press Start 2P + Space Mono at integer upscale
"""

import os
import random
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
os.environ["VIXL_RESOURCES"] = str(HERE / "resources")
os.environ.setdefault("VIXL_FONT_CACHE", str(HERE / ".font-cache"))
os.environ["VIXL_NO_UPDATE"] = "1"

from vixl import Project  # noqa: E402
from vixl.typefaces import pair_fonts  # noqa: E402

# Sweetie-16 palette (GrafxKid), the whole pack shares it.
C = {
    "ink": "#1a1c2c", "plum": "#5d275d", "red": "#b13e53", "orange": "#ef7d57",
    "sand": "#ffcd75", "lime": "#a7f070", "green": "#38b764", "teal": "#257179",
    "navy": "#29366f", "blue": "#3b5dc9", "sky": "#41a6f6", "cyan": "#73eff7",
    "white": "#f4f4f4", "silver": "#94b0c2", "slate": "#566c86", "night": "#333c57",
}


def grid(text):
    """Turn a triple-quoted block into equal-width rows, failing with the row number if ragged.

    Vixl only says "Pixel rows need equal widths of 1–256" without the offending row, so we
    check here first.
    """
    rows = [line.strip() for line in text.strip().splitlines()]
    width = len(rows[0])
    for i, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(f"row {i} has width {len(row)} (expected {width}): {row!r}")
    return rows


def ops(p, *batch):
    return p.apply(list(batch), detail="compact")


# ---------------------------------------------------------------------------------------------
# Hero (side view, facing right) — body + swappable leg poses + sword poses

HERO_PAL = {
    ".": "transparent", "o": C["ink"], "c": C["red"], "C": C["orange"], "h": C["plum"],
    "s": C["sand"], "S": C["orange"], "e": C["ink"], "t": C["blue"], "T": C["navy"],
    "b": C["plum"], "y": C["sand"], "p": C["slate"], "P": C["night"], "k": C["plum"],
    "K": C["ink"], "w": C["white"],
}

HERO_BODY = grid("""
    .....oooooo.....
    ....occccCCo....
    ...occcccccCo...
    ...occccoooooo..
    ...ohhhsssso....
    ...ohhsssweso...
    ...ohhssssesso..
    ...oohSsssso....
    ....ooSssoo.....
    ....otttttTo....
    ...otttTTsso....
    ...obbbbybbo....
    ...otttttTo.....
""")

LEGS = {
    "stand": grid("""
        ....oPpppo......
        ....oKkkkko.....
        ....ooooooo.....
    """),
    "stride-a": grid("""
        ....oPPopo......
        ...oKKo.okko....
        ...ooo..oooo....
    """),
    "stride-b": grid("""
        ....oppoPo......
        ...okko.oKKo....
        ...oooo..ooo....
    """),
    "pass": grid("""
        ....oPpppo......
        ....oPopo.......
        ....oKkkko......
        ....oooooo......
    """),
}

SWORD_PAL = {".": "transparent", "o": C["ink"], "B": C["white"], "b": C["silver"],
             "g": C["sand"], "h": C["plum"], "w": C["white"], "c": C["cyan"], "C": C["sky"]}

SWORD_FWD = grid("""
    ..goooooooo.
    hhgBBBBBBBBo
    ..gbbbbbbbo.
""")


def transpose(rows):
    return ["".join(r[i] for r in rows) for i in range(len(rows[0]))]


SWORD_UP = list(reversed(transpose(SWORD_FWD)))  # tip at top, hilt at bottom


def diag_sword(name, x, y, mirror=False):
    """A 12x12 diagonal sword drawn with pixel-draw lines; mirror=True points it up-left."""
    m = (lambda v: 11 - v) if mirror else (lambda v: v)
    lines = [((3, 8, 10, 1), "B"), ((4, 8, 11, 1), "b"), ((3, 7, 9, 1), "o"), ((5, 8, 11, 2), "o"),
             ((1, 8, 4, 11), "g"), ((1, 11, 2, 10), "h")]
    out = [{"type": "pixel-art", "name": name, "width": 12, "height": 12, "palette": SWORD_PAL, "x": x, "y": y}]
    for (x1, y1, x2, y2), color in lines:
        out.append({"type": "pixel-draw", "target": name, "tool": "line", "x": m(x1), "y": y1,
                    "x2": m(x2), "y2": y2, "color": color})
    out.append({"type": "pixel-draw", "target": name, "x": m(0), "y": 11, "color": "h"})
    return out


def hero_layers(p, x=0, y=0, prefix="hero", pal=None):
    """Add the hero's layers (body, four leg poses, three sword poses, slash) at canvas offset x, y."""
    pal = pal or HERO_PAL
    batch = [
        {"type": "pixel-art", "name": f"{prefix}-legs-{k}", "rows": v, "palette": pal, "x": x + 2,
         "y": y + (20 if k == "pass" else 21)}
        for k, v in LEGS.items()
    ]
    batch += [
        *diag_sword(f"{prefix}-sword-back", x + 1, y + 7, mirror=True),
        {"type": "pixel-art", "name": f"{prefix}-body", "rows": HERO_BODY, "palette": pal, "x": x + 2, "y": y + 8},
        {"type": "pixel-art", "name": f"{prefix}-sword-fwd", "rows": SWORD_FWD, "palette": SWORD_PAL,
         "x": x + 12, "y": y + 17},
        # Diagonal sword is drawn with pixel-draw lines on a blank grid (see diag_sword()).
        *diag_sword(f"{prefix}-sword-diag", x + 11, y + 6),
        {"type": "pixel-art", "name": f"{prefix}-slash", "width": 10, "height": 18, "palette": SWORD_PAL,
         "x": x + 14, "y": y + 4},
    ]
    # Crescent slash: a few stacked lines approximating an arc.
    arc = [(0, 0, 5, 2), (5, 2, 8, 6), (8, 6, 9, 11), (9, 11, 7, 15), (7, 15, 3, 17)]
    for x1, y1, x2, y2 in arc:
        batch.append({"type": "pixel-draw", "tool": "line", "x": x1, "y": y1, "x2": x2, "y2": y2, "color": "w"})
    inner = [(0, 2, 4, 3), (4, 3, 6, 6), (6, 6, 7, 11), (7, 11, 5, 14), (5, 14, 2, 16)]
    for x1, y1, x2, y2 in inner:
        batch.append({"type": "pixel-draw", "tool": "line", "x": x1, "y": y1, "x2": x2, "y2": y2, "color": "c"})
    batch.append({"type": "group", "name": prefix, "targets": [b["name"] for b in batch if b["type"] == "pixel-art"]})
    return batch


def pose(p, prefix, legs="stand", sword=None, body_dy=0, x=0, y=0, slash=False):
    """Operations that put the hero in one pose (absolute positions, so poses are independent).

    Children of a group are positioned in group-local coordinates whose origin is the members'
    bounding box when the group was made, so convert canvas coordinates first.
    """
    gx, gy = p.inspect(prefix)["x"], p.inspect(prefix)["y"]
    x, y = x - gx, y - gy
    out = []
    for k in LEGS:
        out.append({"type": "show" if k == legs else "hide", "target": f"{prefix}-legs-{k}"})
    for k in ("fwd", "back", "diag"):
        out.append({"type": "show" if k == sword else "hide", "target": f"{prefix}-sword-{k}"})
    out.append({"type": "show" if slash else "hide", "target": f"{prefix}-slash"})
    out.append({"type": "move", "target": f"{prefix}-body", "x": x + 2, "y": y + 8 + body_dy})
    return out


HERO_FRAMES = [
    # name, duration, pose kwargs
    ("idle-1", 400, dict()),
    ("idle-2", 400, dict(body_dy=1)),
    ("walk-1", 140, dict(legs="stride-a")),
    ("walk-2", 140, dict(legs="pass", body_dy=-1)),
    ("walk-3", 140, dict(legs="stride-b")),
    ("walk-4", 140, dict(legs="pass", body_dy=-1)),
    ("attack-1", 120, dict(sword="back", body_dy=1)),
    ("attack-2", 60, dict(sword="diag", legs="stride-a")),
    ("attack-3", 200, dict(sword="fwd", legs="stride-a", slash=True)),
    ("attack-4", 200, dict(sword="fwd", legs="stride-a")),
]


def clip(project, keep, path, **options):
    """Export a subset of frames. animation-set must list *every* frame, so we clone the
    project and frame-delete the others."""
    c = project.clone()
    names = [f["name"] for f in c.inspect_animation()["frames"]]
    c.apply([{"type": "frame-delete", "name": n} for n in names if n not in keep], detail="compact")
    c.apply({"type": "animation-set", "order": list(keep), "loop": 0}, detail="compact")
    return c.export_animation(path, **options)


def build_hero():
    p = Project(24, 24)
    ops(p, *hero_layers(p))
    for name, duration, kw in HERO_FRAMES:
        ops(p, *pose(p, "hero", **kw), {"type": "frame-save", "name": name, "duration": duration})
    ops(p, {"type": "frame-apply", "name": "idle-1"})
    p.save(OUT / "hero.vixl")
    walk = [f"walk-{i}" for i in range(1, 5)]
    idle = ["idle-1", "idle-2"]
    attack = [f"attack-{i}" for i in range(1, 5)]
    clip(p, walk, OUT / "hero-walk.gif", scale=8)
    clip(p, walk, OUT / "hero-walk.apng", format="apng", scale=8)
    clip(p, idle, OUT / "hero-idle.gif", scale=8)
    clip(p, attack + ["idle-1"], OUT / "hero-attack.gif", scale=8)
    clip(p, attack + ["idle-1"], OUT / "hero-attack.apng", format="apng", scale=8)
    p.export_animation(OUT / "hero-sheet.png", format="sheet", columns=len(HERO_FRAMES))
    p.export_animation(OUT / "hero-sheet@6x.png", format="sheet", columns=5, scale=6)
    return p


# ---------------------------------------------------------------------------------------------
# Enemies and palette swaps

MON_PAL = {".": "transparent", "o": C["ink"], "a": C["green"], "A": C["teal"], "l": C["lime"],
           "w": C["white"], "e": C["ink"], "f": C["red"]}

SLIME = {
    "up": grid("""
        ................
        ................
        ......oooo......
        ....oollaaoo....
        ...olwwlaaaao...
        ..olwlaaaaaaao..
        ..olaaeaaaeaao..
        .olaaaeaaaeaaAo.
        .olaaaaaaaaaaAo.
        .oAaaaafffaaAAo.
        .oAAaaaaaaaaAAo.
        ..oAAAAAAAAAAo..
        ...oooooooooo...
    """),
    "squash": grid("""
        ................
        ................
        ................
        ................
        .......ooo......
        ....oooollaoo...
        ..oolwwlaaaaaoo.
        .olwlaaeaaaeaaAo
        oolaaaaeaaaeaaAo
        olaaaaaaffaaaaAo
        oAAaaaaaaaaaaAAo
        .oAAAAAAAAAAAAo.
        ..oooooooooooo..
    """),
}

BAT = {
    "up": grid("""
        ................
        .o....o..o....o.
        .oo...oooo...oo.
        .oAo.oaaaao.oAo.
        .oAAoawaawaoAAo.
        .oAAAaeaaeaAAAo.
        ..oAAaaffaaAAo..
        ..oAoAaaaaAoAo..
        ...o.oAAAAo.o...
        ......o..o......
        ................
        ................
    """),
    "down": grid("""
        ................
        ................
        ......o..o......
        .....oaaaao.....
        ....oawaawao....
        ..ooAaeaaeaAoo..
        .oAAAaaffaaAAAo.
        oAAAoAaaaaAoAAAo
        oAAo.oAAAAo.oAAo
        oAo...oooo...oAo
        .o............o.
        ................
    """),
}

SWAPS = {
    "slime": [
        ("green", {}),
        ("ocean", {"a": C["sky"], "A": C["blue"], "l": C["cyan"]}),
        ("magma", {"a": C["orange"], "A": C["red"], "l": C["sand"], "f": C["plum"]}),
        ("king", {"a": C["silver"], "A": C["slate"], "l": C["white"], "f": C["red"],
                  "k": C["sand"], "K": C["orange"]}),
    ],
    "bat": [
        ("cave", {"a": C["night"], "A": C["plum"], "f": C["red"]}),
        ("frost", {"a": C["silver"], "A": C["sky"], "f": C["blue"]}),
        ("blood", {"a": C["red"], "A": C["plum"], "f": C["sand"]}),
        ("ghost", {"a": C["white"], "A": C["silver"], "o": C["slate"], "f": C["sky"]}),
    ],
}

HERO_SWAPS = [
    ("hero", {}),
    ("ranger", {"c": C["green"], "C": C["lime"], "h": C["teal"], "t": C["teal"], "T": C["ink"],
                "b": C["night"], "y": C["silver"], "k": C["teal"]}),
    ("shadow", {"c": C["night"], "C": C["slate"], "h": C["ink"], "s": C["silver"], "S": C["slate"],
                "t": C["plum"], "T": C["ink"], "b": C["red"], "y": C["red"], "w": C["red"],
                "p": C["ink"], "P": C["ink"], "k": C["night"]}),
    ("paladin", {"c": C["white"], "C": C["sand"], "h": C["sand"], "t": C["silver"], "T": C["slate"],
                 "b": C["orange"], "y": C["sand"], "p": C["navy"], "k": C["blue"]}),
]


def build_enemies():
    """Monsters: one drawing per pose, recoloured per variant with pixel-palette."""
    p = Project(4 * 24, 2 * 24)
    batch = []
    for row, kind in enumerate(("slime", "bat")):
        art = SLIME if kind == "slime" else BAT
        for col, (variant, colors) in enumerate(SWAPS[kind]):
            for pose_name, rows in art.items():
                name = f"{kind}-{variant}-{pose_name}"
                batch.append({"type": "pixel-art", "name": name, "rows": rows, "palette": MON_PAL,
                              "x": col * 24 + 4, "y": row * 24 + (24 - len(rows)) - (3 if kind == "bat" else 2)})
                if colors:
                    batch.append({"type": "pixel-palette", "target": name, "colors": colors})
                if variant == "king":  # pixel-palette added the k/K symbols; now draw a crown
                    top = 0 if pose_name == "up" else 2
                    batch += [
                        {"type": "pixel-draw", "target": name, "tool": "rect", "x": 5, "y": top + 1,
                         "width": 6, "height": 1 + (pose_name == "up"), "color": "k"},
                        *[{"type": "pixel-draw", "target": name, "x": cx, "y": top, "color": "k"}
                          for cx in (5, 7, 8, 10)],
                        {"type": "pixel-draw", "target": name, "tool": "line", "x": 5, "y": top + 2,
                         "x2": 10, "y2": top + 2, "color": "K"},
                        {"type": "pixel-draw", "target": name, "x": 7, "y": top + 1, "color": "f"},
                    ]
    ops(p, *batch)
    second = [b["name"] for b in batch if b["type"] == "pixel-art" and b["name"].endswith(("-squash", "-down"))]
    first = [b["name"] for b in batch if b["type"] == "pixel-art" and b["name"] not in second]
    ops(p, *[{"type": "hide", "target": n} for n in second], {"type": "frame-save", "name": "a", "duration": 300})
    ops(p, *[{"type": "hide", "target": n} for n in first], *[{"type": "show", "target": n} for n in second],
        {"type": "frame-save", "name": "b", "duration": 300})
    ops(p, {"type": "frame-apply", "name": "a"})
    p.save(OUT / "enemies.vixl")
    p.export_animation(OUT / "enemies.gif", scale=6)
    p.export_animation(OUT / "enemies-sheet.png", format="sheet", columns=2)
    p.export(OUT / "enemies@6x.png", scale=6, sampling="nearest")

    # Hero palette variants share the hero rig; each walks in place.
    h = Project(len(HERO_SWAPS) * 24, 24)
    for i, (variant, colors) in enumerate(HERO_SWAPS):
        ops(h, *hero_layers(h, x=i * 24, prefix=variant))
        if colors:
            ops(h, *[{"type": "pixel-palette", "target": f"{variant}-{part}", "colors": colors}
                     for part in ["body", *[f"legs-{k}" for k in LEGS]]])
    for name, duration, kw in HERO_FRAMES:
        ops(h, *[o for i, (variant, _) in enumerate(HERO_SWAPS) for o in pose(h, variant, x=i * 24, **kw)],
            {"type": "frame-save", "name": name, "duration": duration})
    ops(h, {"type": "frame-apply", "name": "idle-1"})
    h.save(OUT / "hero-variants.vixl")
    clip(h, [f"walk-{i}" for i in range(1, 5)], OUT / "hero-variants-walk.gif", scale=6)
    clip(h, [f"attack-{i}" for i in range(1, 5)] + ["idle-1"], OUT / "hero-variants-attack.gif", scale=6)
    h.export_animation(OUT / "hero-variants-sheet.png", format="sheet", columns=1)
    return p, h


# ---------------------------------------------------------------------------------------------
# Tileset — every tile starts as a blank grid and is drawn with pixel-draw pixel/line/rect/fill

TILE_PAL = {
    ".": "transparent", "o": C["ink"], "g": C["green"], "G": C["teal"], "l": C["lime"],
    "w": C["blue"], "W": C["sky"], "f": C["cyan"], "d": C["navy"], "s": C["silver"],
    "S": C["white"], "m": C["slate"], "n": C["night"], "b": C["plum"], "r": C["red"],
    "y": C["sand"], "Y": C["orange"],
}


class Tile:
    """Collects pixel-draw operations for one tile layer."""

    def __init__(self, name, w=16, h=16, bg="g"):
        self.name, self.ops = name, [{"type": "pixel-art", "name": name, "width": w, "height": h,
                                      "palette": TILE_PAL, "background": bg}]

    def px(self, x, y, c):
        self.ops.append({"type": "pixel-draw", "target": self.name, "x": x, "y": y, "color": c})
        return self

    def line(self, x, y, x2, y2, c):
        self.ops.append({"type": "pixel-draw", "target": self.name, "tool": "line", "x": x, "y": y,
                         "x2": x2, "y2": y2, "color": c})
        return self

    def rect(self, x, y, w, h, c):
        self.ops.append({"type": "pixel-draw", "target": self.name, "tool": "rect", "x": x, "y": y,
                         "width": w, "height": h, "color": c})
        return self

    def fill(self, x, y, c):
        self.ops.append({"type": "pixel-draw", "target": self.name, "tool": "fill", "x": x, "y": y, "color": c})
        return self


def blob(t, top, spans, fill_color, outline="o"):
    """Outline a round shape row by row with pixel-draw lines, then flood-fill its inside.

    `fill` is index-based (4-neighbour, same symbol), so the inside must be one uniform symbol
    when we fill; decorate afterwards.
    """
    rows = [r if isinstance(r, list) else [r] for r in spans]
    shape = {(x, top + i) for i, row in enumerate(rows) for a, b in row for x in range(a, b + 1)}
    edge = sorted((y, x) for x, y in shape
                  if any(n not in shape for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))))
    runs = []
    for y, x in edge:
        if runs and runs[-1][0] == y and runs[-1][2] == x - 1:
            runs[-1][2] = x
        else:
            runs.append([y, x, x])
    for y, a, b in runs:
        t.line(a, y, b, y, outline)
    mid = top + len(spans) // 2
    t.fill(sum(rows[len(rows) // 2][0]) // 2, mid, fill_color)
    return shape


def grass_detail(t, seed, flowers=0, avoid=()):
    rnd = random.Random(seed)
    for _ in range(7):  # dark tufts: little "v" shapes
        x, y = rnd.randrange(1, 14), rnd.randrange(1, 15)
        if any((x + dx, y + dy) in avoid for dx in (-1, 0, 1, 2, 3) for dy in (-1, 0, 1, 2)):
            continue
        t.px(x, y, "G").px(x + 2, y, "G").px(x + 1, y + 1 if y < 15 else y, "G")
    for _ in range(5):
        t.px(rnd.randrange(16), rnd.randrange(16), "l")
    for _ in range(flowers):
        x, y = rnd.randrange(1, 15), rnd.randrange(1, 15)
        petal = rnd.choice("Srs")
        t.px(x - 1, y, petal).px(x + 1, y, petal).px(x, y - 1, petal).px(x, y + 1, petal).px(x, y, "y")
    return t


def tile_grass():
    return grass_detail(Tile("grass"), 3)


def tile_flowers():
    return grass_detail(Tile("flowers"), 8, flowers=3)


def leaf(t, x, y, c):
    """A 4-pixel scallop: the leaf-cluster texture used on canopies and bushes."""
    return t.px(x, y, c).px(x + 1, y + 1, c).px(x + 2, y + 1, c).px(x + 3, y, c)


def tile_bush():
    t = Tile("bush")
    spans = [(5, 10), (3, 12), (2, 13), (1, 14), (1, 14), (1, 14), (1, 14), (1, 14), (2, 13), (3, 12), (5, 10)]
    shape = blob(t, 3, spans, "G")
    grass_detail(t, 11, avoid=shape)
    t.rect(4, 5, 5, 2, "g").rect(3, 6, 3, 2, "g").px(5, 4, "l").px(4, 5, "l").px(10, 7, "l")
    leaf(t, 8, 5, "g")
    leaf(t, 3, 9, "n")
    leaf(t, 8, 10, "n")
    t.line(5, 14, 10, 14, "G")
    t.px(10, 5, "r").px(6, 9, "r").px(12, 9, "r").px(8, 7, "r")
    return t


def tile_path():
    t = Tile("path", bg="m")
    stones = [(0, 0, 6, 4), (7, 0, 5, 3), (13, 0, 3, 4), (0, 5, 4, 5), (5, 4, 6, 5), (12, 5, 4, 4),
              (0, 11, 5, 5), (6, 10, 5, 6), (12, 10, 4, 6)]
    for x, y, w, h in stones:
        t.rect(x, y, w, h, "s").line(x, y, x + w - 1, y, "S").line(x, y + h - 1, x + w - 1, y + h - 1, "n")
    t.px(3, 2, "m").px(9, 13, "m").px(14, 7, "S")
    return t


def tile_sand():
    t = Tile("sand", bg="y")
    rnd = random.Random(5)
    for _ in range(10):
        t.px(rnd.randrange(16), rnd.randrange(16), "Y")
    for _ in range(4):
        t.px(rnd.randrange(16), rnd.randrange(16), "S")
    return t


def tile_wall():
    t = Tile("wall", bg="n")
    for row in range(4):
        y, off = row * 4, (row % 2) * 4
        for bx in range(-4 + off, 16, 8):
            x0, x1 = max(0, bx), min(15, bx + 6)
            t.rect(x0, y, x1 - x0 + 1, 3, "m").line(x0, y, x1, y, "s")
    t.line(0, 0, 15, 0, "S")
    return t


def tile_rock():
    t = grass_detail(Tile("rock"), 21)
    t.rect(3, 5, 10, 9, "o").rect(2, 7, 12, 6, "o").rect(4, 6, 8, 7, "m").rect(3, 8, 10, 4, "m")
    t.rect(4, 6, 5, 3, "s").px(5, 6, "S").px(6, 6, "S").line(4, 12, 11, 12, "n").line(3, 14, 12, 14, "G")
    return t


def tile_chest():
    t = grass_detail(Tile("chest"), 31)
    t.rect(2, 4, 12, 10, "o").rect(3, 5, 10, 8, "Y").line(3, 5, 12, 5, "y")
    t.line(3, 8, 12, 8, "o").rect(3, 9, 10, 4, "b").rect(4, 9, 8, 3, "Y")
    t.rect(7, 7, 2, 3, "y").px(7, 9, "o").line(2, 14, 13, 14, "G")
    return t


def tile_water(frame):
    t = Tile(f"water-{frame}", bg="w")
    waves = [(1, 3), (9, 6), (4, 10), (11, 13), (0, 14)]
    for i, (x, y) in enumerate(waves):
        x = (x + 3 * frame) % 12
        t.line(x, y, x + 3, y, "W").px(x + 1, y - 1, "W")
        if i % 2 == frame % 2:
            t.px(x + 2, y - 1, "f")
    t.px((6 + 5 * frame) % 16, 1, "d").px((13 + 7 * frame) % 16, 9, "d")
    return t


def tile_shore():
    """Grass on the left, water on the right; the map flips it for the opposite bank."""
    t = Tile("shore", bg="w")
    t.rect(0, 0, 5, 16, "g")
    for y in range(0, 16, 4):
        t.px(5, y, "g").px(5, y + 1, "g").px(6, y + 1, "G")
    t.line(5, 2, 5, 3, "G").line(6, 0, 6, 15, "f").line(7, 2, 7, 3, "W").line(7, 9, 7, 11, "W")
    t.line(11, 5, 13, 5, "W").line(10, 12, 12, 12, "W").px(1, 4, "G").px(3, 11, "l").px(2, 8, "G")
    return t


def tile_bridge():
    t = Tile("bridge", bg="Y")
    for x in range(0, 16, 4):
        t.line(x, 0, x, 15, "b").line(x + 1, 0, x + 1, 15, "y")
    t.rect(0, 0, 16, 2, "o").rect(0, 14, 16, 2, "o").line(0, 1, 15, 1, "b").line(0, 14, 15, 14, "n")
    for x in (2, 10):
        t.px(x, 4, "n").px(x + 4, 11, "n")
    return t


def tile_tree():
    """16x32: a lumpy canopy outlined with lines and flood-filled, shaded, textured, plus a trunk."""
    t = Tile("tree", 16, 32, bg=".")
    spans = [[(3, 7), (9, 12)], (2, 13), (1, 14), (1, 14), (0, 15), (0, 15), (0, 15), (1, 15), (1, 15),
             (0, 15), (0, 15), (0, 15), (0, 15), (1, 15), (0, 15), (0, 15), (0, 15), (1, 14), (1, 14),
             [(2, 7), (9, 13)], [(3, 6), (10, 12)]]
    blob(t, 0, spans, "g")
    # Lower half in shadow: a barrier line across the canopy, flood-filled below, then a
    # scalloped edge so the terminator reads as leaf clusters rather than a ruler line.
    t.line(1, 12, 14, 12, "G").fill(7, 15, "G")
    for x in (1, 5, 9):
        leaf(t, x, 12, "g")
    t.px(13, 12, "g").px(14, 13, "G")
    for x, y in ((2, 15), (7, 16), (11, 15), (4, 18)):
        leaf(t, x, y, "n")
    for x, y in ((6, 5), (9, 8), (3, 9), (10, 3)):
        leaf(t, x, y, "G")
    t.rect(4, 2, 3, 2, "l").rect(3, 3, 2, 3, "l").px(9, 2, "l").px(12, 5, "l").px(2, 7, "l").px(8, 10, "l")
    # Trunk with roots, visible between the two lower lobes.
    t.rect(6, 20, 4, 9, "o").rect(7, 20, 2, 8, "b").px(8, 22, "n").px(7, 25, "n")
    t.rect(4, 27, 8, 2, "o").rect(5, 27, 2, 1, "b").rect(9, 27, 2, 1, "b")
    t.line(3, 29, 12, 29, "G").line(5, 30, 10, 30, "G")  # ground shadow
    return t


TILES = [tile_grass, tile_flowers, tile_bush, tile_path, tile_sand, tile_wall, tile_rock, tile_chest,
         lambda: tile_water(0), lambda: tile_water(1), tile_shore, tile_bridge, tile_tree]
TILE_SLOTS = {"grass": (0, 0), "flowers": (1, 0), "bush": (2, 0), "path": (3, 0), "sand": (4, 0),
              "wall": (5, 0), "rock": (6, 0), "chest": (7, 0), "water-0": (0, 1), "water-1": (1, 1),
              "shore": (2, 1), "bridge": (3, 1), "tree": (4, 1)}


def build_tileset():
    p = Project(8 * 16, 3 * 16)
    for make in TILES:
        t = make()
        ops(p, *t.ops)
        col, row = TILE_SLOTS[t.name]
        ops(p, {"type": "move", "target": t.name, "x": col * 16, "y": row * 16})
    p.save(OUT / "tileset.vixl")
    p.export(OUT / "tileset.png")
    p.export(OUT / "tileset@4x.png", scale=4, sampling="nearest")
    return p


# ---------------------------------------------------------------------------------------------
# Tile-map scene: tiles copied from the tileset by rows, laid out with repeat / repeated groups

ICON_PAL = {".": "transparent", "o": C["ink"], "r": C["red"], "R": C["orange"], "w": C["white"],
            "y": C["sand"], "Y": C["orange"], "n": C["night"], "c": C["cyan"]}
HEART = grid("""
    .oo.oo.
    orRorro
    orwrrro
    orrrrro
    .orrro.
    ..oro..
    ...o...
""")
HEART_EMPTY = [r.replace("r", "n").replace("R", "n").replace("w", "n") for r in HEART]
COIN = grid("""
    ..YYY..
    .YyyyY.
    YyywyyY
    YyywyyY
    YyywyyY
    .YyyyY.
    ..YYY..
""")
ARROW = grid("""
    ooooooo
    owwwwwo
    .owwwo.
    ..owo..
    ...o...
""")


def build_map(tileset, enemies):
    W, H = 20 * 16, 12 * 16
    p = Project(W, H, C["green"])
    pair_fonts(p, "press-start-space-mono")

    def tile(name, layer, x, y, **extra):
        src = tileset.inspect_pixels(name)
        return {"type": "pixel-art", "name": layer, "rows": src["rows"], "palette": src["palette"],
                "x": x, "y": y, **extra}

    def mon(name, layer, x, y):
        src = enemies.inspect_pixels(name)
        return {"type": "pixel-art", "name": layer, "rows": src["rows"], "palette": src["palette"], "x": x, "y": y}

    # Ground: one grass tile -> a repeated row (20) -> a repeated group (12 rows).
    ops(p, tile("grass", "grass", 0, 0), {"type": "repeat", "target": "grass", "count": 20, "dx": 16},
        {"type": "group", "name": "ground", "targets": ["grass"]},
        {"type": "repeat", "target": "ground", "count": 12, "dy": 16})
    rnd = random.Random(7)
    flowers = [(rnd.randrange(0, 10), rnd.randrange(2, 12)) for _ in range(12)]
    flowers += [(rnd.randrange(14, 20), rnd.randrange(8, 12)) for _ in range(3)]
    ops(p, *[tile("flowers", f"flowers-{i}", cx * 16, cy * 16) for i, (cx, cy) in enumerate(set(flowers))
             if cy != 6])
    # River: three columns repeated down the map; the right bank is the left bank flipped.
    ops(p, tile("shore", "bank-left", 11 * 16, 0), {"type": "repeat", "target": "bank-left", "count": 12, "dy": 16},
        tile("shore", "bank-right", 13 * 16, 0), {"type": "flip", "target": "bank-right", "direction": "horizontal"},
        {"type": "repeat", "target": "bank-right", "count": 12, "dy": 16},
        tile("water-0", "water-a", 12 * 16, 0), {"type": "repeat", "target": "water-a", "count": 12, "dy": 16},
        tile("water-1", "water-b", 12 * 16, 0), {"type": "repeat", "target": "water-b", "count": 12, "dy": 16},
        {"type": "hide", "target": "water-b"})
    # Road with a bridge, a castle wall and a sandy yard.
    ops(p, tile("path", "road-west", 0, 96), {"type": "repeat", "target": "road-west", "count": 11, "dx": 16},
        tile("bridge", "bridge", 11 * 16, 96), {"type": "repeat", "target": "bridge", "count": 3, "dx": 16},
        tile("path", "road-east", 14 * 16, 96), {"type": "repeat", "target": "road-east", "count": 6, "dx": 16},
        tile("wall", "wall", 15 * 16, 16), {"type": "repeat", "target": "wall", "count": 5, "dx": 16},
        {"type": "group", "name": "castle", "targets": ["wall"]},
        {"type": "repeat", "target": "castle", "count": 4, "dy": 16},
        tile("sand", "yard", 15 * 16, 8 * 16), {"type": "repeat", "target": "yard", "count": 5, "dx": 16},
        {"type": "group", "name": "yard-rows", "targets": ["yard"]},
        {"type": "repeat", "target": "yard-rows", "count": 4, "dy": 16})
    # Props.
    props = [("bush", 1, 4), ("bush", 9, 3), ("bush", 2, 9), ("rock", 7, 9), ("rock", 10, 2),
             ("rock", 15, 7), ("bush", 14, 3), ("bush", 14, 9)]
    ops(p, *[tile(n, f"{n}-{i}", cx * 16, cy * 16) for i, (n, cx, cy) in enumerate(props)])
    # Props standing on sand: the same tiles with their grass palette swapped to sand.
    on_sand = {"g": C["sand"], "G": C["orange"], "l": C["white"]}
    ops(p, tile("chest", "chest-sand", 17 * 16, 9 * 16), tile("rock", "rock-sand", 19 * 16, 10 * 16),
        {"type": "pixel-palette", "target": "chest-sand", "colors": on_sand},
        {"type": "pixel-palette", "target": "rock-sand", "colors": on_sand})
    # Battlements and a door on the castle wall, plus a short path to the road.
    merlon = Tile("merlon", 16, 8, bg=".")
    merlon.rect(1, 1, 6, 7, "o").rect(9, 1, 6, 7, "o").rect(2, 2, 4, 6, "m").rect(10, 2, 4, 6, "m")
    merlon.line(2, 2, 5, 2, "S").line(10, 2, 13, 2, "S").line(0, 7, 15, 7, "o")
    door = Tile("door", 16, 16, bg=".")
    door.rect(3, 2, 10, 14, "o").rect(4, 1, 8, 1, "o").rect(4, 3, 8, 13, "b").rect(5, 2, 6, 1, "b")
    for x in (6, 9):
        door.line(x, 3, x, 15, "n")
    door.px(10, 9, "y").line(4, 6, 11, 6, "n").line(4, 12, 11, 12, "n")
    ops(p, *merlon.ops, {"type": "move", "target": "merlon", "x": 15 * 16, "y": 8},
        {"type": "repeat", "target": "merlon", "count": 5, "dx": 16},
        *door.ops, {"type": "move", "target": "door", "x": 17 * 16, "y": 64},
        tile("path", "door-path", 17 * 16, 80))
    # Trees: a back row via repeat (partly off-canvas), then hand-placed ones for rhythm.
    ops(p, tile("tree", "treeline", -6, -18), {"type": "repeat", "target": "treeline", "count": 11, "dx": 16})
    trees = [(10, 6), (38, 12), (74, 4), (130, 10), (0, 120), (22, 136), (88, 150), (150, 128), (296, 92),
             (226, 120)]
    ops(p, *[tile("tree", f"tree-{i}", x, y) for i, (x, y) in enumerate(trees)])
    # Characters.
    ops(p, *hero_layers(p, x=72, y=88, prefix="hero"))
    ops(p, mon("slime-green-up", "slime-a", 40, 64), mon("slime-ocean-up", "slime-b", 56, 150),
        mon("slime-king-up", "king", 236, 92), mon("bat-cave-up", "bat", 200, 40))
    ops(p, mon("slime-green-squash", "slime-a2", 40, 64), mon("slime-ocean-squash", "slime-b2", 56, 150),
        mon("slime-king-squash", "king2", 236, 92), mon("bat-cave-down", "bat2", 200, 40),
        *[{"type": "hide", "target": n} for n in ("slime-a2", "slime-b2", "king2", "bat2")])

    # HUD: top bar, hearts (repeat), coins, level; dialogue box with pixel font text.
    hud = [
        {"type": "solid", "name": "hud-bar", "x": 0, "y": 0, "width": W, "height": 15, "color": C["ink"]},
        {"type": "opacity", "target": "hud-bar", "value": 0.85},
        {"type": "pixel-art", "name": "hearts", "rows": HEART, "palette": ICON_PAL, "x": 5, "y": 4},
        {"type": "repeat", "target": "hearts", "count": 4, "dx": 9},
        {"type": "pixel-art", "name": "heart-empty", "rows": HEART_EMPTY, "palette": ICON_PAL, "x": 41, "y": 4},
        {"type": "pixel-art", "name": "coin", "rows": COIN, "palette": ICON_PAL, "x": 62, "y": 4},
        {"type": "text", "name": "coins", "text": "x042", "size": 8, "font": "heading", "color": C["sand"],
         "x": 72, "y": 4},
        {"type": "text", "name": "area", "text": "MOSSBRIDGE", "size": 8, "font": "heading",
         "color": C["white"], "x": 236, "y": 4},
        {"type": "solid", "name": "box-edge", "x": 8, "y": 144, "width": 304, "height": 42, "color": C["white"]},
        {"type": "solid", "name": "box-shade", "x": 9, "y": 145, "width": 302, "height": 40, "color": C["ink"]},
        {"type": "solid", "name": "box-fill", "x": 10, "y": 146, "width": 300, "height": 38, "color": C["navy"]},
        {"type": "solid", "name": "tag-edge", "x": 16, "y": 138, "width": 92, "height": 13, "color": C["white"]},
        {"type": "solid", "name": "tag-fill", "x": 17, "y": 139, "width": 90, "height": 11, "color": C["red"]},
        {"type": "text", "name": "speaker", "text": "KING SLIME", "size": 8, "font": "heading",
         "color": C["white"], "x": 22, "y": 141},
        {"type": "text", "name": "line-1", "text": "Halt, small hero! None cross", "size": 8, "font": "heading",
         "color": C["white"], "x": 18, "y": 156},
        {"type": "text", "name": "line-2", "text": "Mossbridge without my blessing.", "size": 8,
         "font": "heading", "color": C["white"], "x": 18, "y": 168},
        {"type": "pixel-art", "name": "next", "rows": ARROW, "palette": ICON_PAL, "x": 298, "y": 176},
    ]
    ops(p, *hud)
    hud_names = [o["name"] for o in hud if "name" in o and o["type"] != "opacity"]
    ops(p, {"type": "group", "name": "hud", "targets": hud_names})

    # Frame animation: water, monsters and hero walk in place, 4 frames.
    for i in range(4):
        b = i % 2 == 1
        ops(p, {"type": "show" if b else "hide", "target": "water-b"},
            *[{"type": "show" if b else "hide", "target": n} for n in ("slime-a2", "slime-b2", "king2", "bat2")],
            *[{"type": "hide" if b else "show", "target": n} for n in ("slime-a", "slime-b", "king", "bat")],
            {"type": "show" if i in (1, 2) else "hide", "target": "next"},
            *pose(p, "hero", x=72, y=88, **HERO_FRAMES[2 + i][2]),
            {"type": "frame-save", "name": f"f{i}", "duration": 180})
    ops(p, {"type": "frame-apply", "name": "f0"})
    # Comps capture the visibility of *every* layer (including the hero's pose layers), so they
    # are saved last, from a posed frame.
    ops(p, {"type": "comp-save", "name": "with-hud"}, {"type": "hide", "target": "hud"},
        {"type": "comp-save", "name": "map-only"}, {"type": "comp-apply", "name": "with-hud"})
    p.save(OUT / "map.vixl")
    p.export(OUT / "map.png", comp="map-only")
    p.export(OUT / "map@3x.png", comp="map-only", scale=3, sampling="nearest")
    p.export(OUT / "map-hud@3x.png", scale=3, sampling="smooth")  # smooth: text re-rendered crisp
    p.export_animation(OUT / "map-hud.gif", scale=2, colors=64)
    build_map_timeline(p)
    return p


def build_map_timeline(map_project):
    """Keyframe-timeline version: the hero walks over the bridge while water and monsters cycle.

    Sprite poses are switched with stepped `visible` keys; positions use steps() easing so the
    hero moves in whole pixels.
    """
    p = map_project.clone()
    ops(p, {"type": "comp-apply", "name": "map-only"}, *pose(p, "hero", x=72, y=88, legs="stand"),
        {"type": "show", "target": "hud-bar"}, {"type": "hide", "target": "box-edge"})
    # Keep only the top bar of the HUD.
    ops(p, {"type": "show", "target": "hud"},
        *[{"type": "hide", "target": n} for n in ("box-edge", "box-shade", "box-fill", "tag-edge", "tag-fill",
                                                   "speaker", "line-1", "line-2", "next")])
    step, duration = 160, 4800
    ops(p, {"type": "timeline-set", "duration": duration, "fps": 12, "loop": 0})
    keys = []
    legs_cycle = ["stride-a", "pass", "stride-b", "pass"]
    walking_until = 3840
    for i, t in enumerate(range(0, duration, step)):
        walking = t < walking_until
        current = legs_cycle[i % 4] if walking else "stand"
        for k in LEGS:
            keys.append({"type": "keyframe", "target": f"hero-legs-{k}", "property": "visible", "time": t,
                         "value": k == current})
        keys.append({"type": "keyframe", "target": "hero-body", "property": "translate-y", "time": t,
                     "value": -1 if walking and current == "pass" else 0, "easing": "hold"})
        flip = i % 2 == 1
        for a, b in (("water-a", "water-b"), ("slime-a", "slime-a2"), ("slime-b", "slime-b2"), ("king", "king2"),
                     ("bat", "bat2")):
            keys.append({"type": "keyframe", "target": a, "property": "visible", "time": t, "value": not flip})
            keys.append({"type": "keyframe", "target": b, "property": "visible", "time": t, "value": flip})
    ops(p, *keys)
    ops(p, {"type": "animate", "target": "hero", "property": "translate-x", "from": 0, "to": 144,
            "start": 0, "end": walking_until, "easing": "steps(48)"},
        {"type": "animate", "target": "bat", "property": "translate-y", "from": 0, "to": 24,
         "start": 0, "end": duration, "easing": "steps(12)"},
        {"type": "animate", "target": "bat2", "property": "translate-y", "from": 0, "to": 24,
         "start": 0, "end": duration, "easing": "steps(12)"},
        {"type": "text-set", "target": "area", "text": "MOSSBRIDGE"},
        {"type": "keyframe", "target": "coins", "property": "text", "time": 0, "value": "x042"},
        {"type": "keyframe", "target": "coins", "property": "text", "time": walking_until, "value": "x043"})
    p.save(OUT / "map-timeline.vixl")
    from vixl.timeline import export_timeline, contact_sheet

    export_timeline(p, OUT / "map-timeline.gif", scale=2, colors=64)
    export_timeline(p, OUT / "map-timeline.mp4", scale=3)
    contact_sheet(p, count=6, columns=3, max_width=960).save(OUT / "map-timeline-contact.png")
    return p


# ---------------------------------------------------------------------------------------------
# Title screen

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def dither_rows(w, h, symbols, seed=1):
    """Vertical ordered-dither gradient through `symbols`, plus a sprinkle of stars."""
    rnd = random.Random(seed)
    rows = []
    for y in range(h):
        t = y / (h - 1) * (len(symbols) - 1)
        band, frac = int(t), t - int(t)
        row = ""
        for x in range(w):
            hi = band + 1 if frac * 16 > BAYER[y % 4][x % 4] and band + 1 < len(symbols) else band
            row += symbols[hi]
        rows.append(row)
    for _ in range(40):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.55))
        rows[y] = rows[y][:x] + rnd.choice("**+") + rows[y][x + 1:]
    return rows


def ridge_rows(w, h, heights, fill="m", edge="M"):
    """Rows for a mountain silhouette given a column -> height function (rows strings)."""
    rows = []
    for y in range(h):
        row = ""
        for x in range(w):
            top = h - heights(x)
            row += "." if y < top else (edge if y == top else fill)
        rows.append(row)
    return rows


CASTLE = grid("""
    ....o.....................o....
    ...ooo...................ooo...
    ..ooooo.................ooooo..
    ..o.o.o.................o.o.o..
    ..ooooo.......o.o.......ooooo..
    ..ooooo......ooooo......ooooo..
    ..oyooo......ooooo......oooyo..
    ..ooooo.o.o.oooyooo.o.o.ooooo..
    ..ooooooooooooooooooooooooooo..
    ..ooooooooyoooooooooyoooooooo..
    ..ooooooooooooooooooooooooooo..
    ..oooooooooooo...oooooooooooo..
    ..ooooooooooo.....ooooooooooo..
    ..ooooooooooo.....ooooooooooo..
    ooooooooooooo.....ooooooooooooo
""")


def scale_pixel_group(p, group, factor, x, y):
    """Nearest-neighbour scale a group of pixel layers to canvas position x, y.

    `scale` on the group resamples with LANCZOS (blurry), and resizing children inside the group
    clips them to the group's old box, so: ungroup, resize/move each pixel layer, regroup.
    """
    gid = p.layer(group)["id"]
    kids = [c["id"] for c in p.state["layers"] if c.get("parent") == gid]
    ops(p, {"type": "ungroup", "target": group})
    x0 = min(p.layer(k)["x"] for k in kids)
    y0 = min(p.layer(k)["y"] for k in kids)
    batch = []
    for k in kids:
        c = p.layer(k)
        batch += [{"type": "resize", "target": k, "width": c["width"] * factor, "height": c["height"] * factor},
                  {"type": "move", "target": k, "x": x + (c["x"] - x0) * factor, "y": y + (c["y"] - y0) * factor}]
    ops(p, *batch, {"type": "group", "name": group, "targets": kids})


def build_title(enemies, tileset):
    import math

    W, H = 320, 180
    p = Project(W, H, C["ink"])
    pair_fonts(p, "press-start-space-mono")
    sky_pal = {"a": C["ink"], "b": C["navy"], "c": C["plum"], "d": C["red"], "e": C["orange"],
               "*": C["white"], "+": C["cyan"]}
    # Sky at half resolution, then an integer 2x resize (pixel layers resize with nearest).
    ops(p, {"type": "pixel-art", "name": "sky", "rows": dither_rows(160, 90, "abbccde"), "palette": sky_pal},
        {"type": "resize", "target": "sky", "width": 320, "height": 180})
    moon = Tile("moon", 20, 20, bg=".")
    moon.ops[0]["palette"] = {**TILE_PAL, "S": C["white"], "s": C["sand"]}
    blob(moon, 0, [(7, 12), (5, 14), (3, 16), (2, 17), (2, 17), (1, 18), (1, 18), (1, 18), (1, 18), (1, 18),
                   (1, 18), (1, 18), (1, 18), (2, 17), (2, 17), (3, 16), (5, 14), (7, 12)], "y", outline="Y")
    moon.rect(4, 4, 4, 3, "S").px(12, 6, "Y").px(13, 6, "Y").px(6, 12, "Y").px(10, 13, "Y").px(11, 13, "Y")
    ops(p, *moon.ops, {"type": "move", "target": "moon", "x": 278, "y": 66})
    # Two mountain ranges; each is 160 columns wide and tiles seamlessly with repeat.
    far = ridge_rows(160, 70, lambda x: int(38 + 18 * math.sin(x / 160 * 2 * math.pi * 2)
                                            + 9 * math.sin(x / 160 * 2 * math.pi * 5 + 1)))
    near = ridge_rows(160, 50, lambda x: int(26 + 12 * math.sin(x / 160 * 2 * math.pi * 3 + 2)
                                             + 5 * math.sin(x / 160 * 2 * math.pi * 7)))
    ops(p, {"type": "pixel-art", "name": "range-far", "rows": far,
            "palette": {".": "transparent", "m": C["night"], "M": C["slate"]}, "x": 0, "y": 76},
        {"type": "repeat", "target": "range-far", "count": 2, "dx": 160},
        {"type": "pixel-art", "name": "castle", "rows": CASTLE,
         "palette": {".": "transparent", "o": C["ink"], "y": C["sand"]}, "x": 144, "y": 96},
        {"type": "resize", "target": "castle", "width": 62, "height": 30},
        {"type": "move", "target": "castle", "x": 129, "y": 84},
        {"type": "pixel-art", "name": "range-near", "rows": near,
         "palette": {".": "transparent", "m": C["ink"], "M": C["plum"]}, "x": 0, "y": 108},
        {"type": "repeat", "target": "range-near", "count": 2, "dx": 160})
    # Foreground forest: the tree tile, palette-swapped to night colours, repeated.
    tree = tileset.inspect_pixels("tree")
    night = {"g": C["teal"], "G": C["navy"], "l": C["green"], "n": C["ink"], "b": C["ink"]}
    ops(p, {"type": "solid", "name": "ground", "x": 0, "y": 158, "width": W, "height": 22, "color": C["ink"]},
        {"type": "pixel-art", "name": "forest-back", "rows": tree["rows"], "palette": tree["palette"],
         "x": -10, "y": 140},
        {"type": "pixel-palette", "target": "forest-back",
         "colors": {**night, "g": C["navy"], "G": C["night"], "l": C["teal"]}},
        {"type": "repeat", "target": "forest-back", "count": 28, "dx": 12},
        {"type": "pixel-art", "name": "forest", "rows": tree["rows"], "palette": tree["palette"],
         "x": -4, "y": 150},
        {"type": "pixel-palette", "target": "forest", "colors": night},
        {"type": "repeat", "target": "forest", "count": 28, "dx": 12},
        {"type": "solid", "name": "footer", "x": 0, "y": 168, "width": W, "height": 12, "color": C["ink"]},
        {"type": "solid", "name": "footer-line", "x": 0, "y": 168, "width": W, "height": 1, "color": C["night"]})
    # Hero and king slime, 2x via integer resize of the pixel layers.
    king = enemies.inspect_pixels("slime-king-up")
    ops(p, *hero_layers(p, x=0, y=0, prefix="hero"))
    ops(p, *pose(p, "hero", sword="fwd", legs="stride-a"))
    # Workaround: `scale` on a *group* of pixel layers resamples with LANCZOS (blurry), so scale
    # each pixel child (nearest) and its group-local position instead.
    scale_pixel_group(p, "hero", 2, 26, 122)
    ops(p,
        {"type": "pixel-art", "name": "king", "rows": king["rows"], "palette": king["palette"], "x": 0, "y": 0},
        {"type": "flip", "target": "king", "direction": "horizontal"},
        {"type": "resize", "target": "king", "width": 32, "height": 26}, {"type": "move", "target": "king", "x": 262, "y": 143})
    # Type: Press Start 2P (heading) for the logo/menus, Space Mono (body) for the tagline.
    ops(p,
        {"type": "text", "name": "title-shadow", "text": "VIXL QUEST", "size": 24, "font": "heading",
         "color": C["plum"], "x": 43, "y": 31},
        {"type": "text", "name": "title", "text": "VIXL QUEST", "size": 24, "font": "heading",
         "color": C["sand"], "x": 40, "y": 28},
        {"type": "layer-style", "target": "title", "name": "gradient-overlay",
         "settings": {"stops": [{"offset": 0, "color": C["white"]}, {"offset": 0.45, "color": C["sand"]},
                                {"offset": 1, "color": C["orange"]}], "angle": 90}},
        {"type": "text", "name": "tagline", "text": "~ the headless kingdom ~", "size": 11, "font": "body",
         "color": C["cyan"], "x": "center", "y": 58},
        {"type": "text", "name": "press-start", "text": "PRESS START", "size": 8, "font": "heading",
         "color": C["white"], "x": "center", "y": 120},
        {"type": "text", "name": "menu", "text": "NEW GAME   CONTINUE", "size": 8, "font": "heading",
         "color": C["silver"], "x": "center", "y": 134},
        {"type": "text", "name": "credit", "text": "(C) 2026 VIXL SOFT", "size": 8, "font": "heading",
         "color": C["slate"], "x": "center", "y": 171},
        # Menu cursor: the dialogue arrow rotated a quarter turn (90-degree turns stay pixel-exact).
        {"type": "pixel-art", "name": "cursor", "rows": ARROW, "palette": ICON_PAL, "x": 74, "y": 134},
        {"type": "rotate", "target": "cursor", "value": -90})
    ops(p, {"type": "frame-save", "name": "on", "duration": 500}, {"type": "hide", "target": "press-start"},
        {"type": "frame-save", "name": "off", "duration": 300}, {"type": "frame-apply", "name": "on"})
    p.save(OUT / "title.vixl")
    p.export(OUT / "title.png")
    p.export(OUT / "title@4x-nearest.png", scale=4, sampling="nearest")
    p.export(OUT / "title@4x.png", scale=4, sampling="smooth")
    p.export_animation(OUT / "title.gif", scale=3, sampling="smooth", colors=64)
    return p


if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    build_hero()
    enemies, _ = build_enemies()
    tileset = build_tileset()
    build_map(tileset, enemies)
    build_title(enemies, tileset)
    print("done")
