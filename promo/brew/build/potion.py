"""The "Harvest Moon" poster family and the cauldron, as plain Vixl operations.

``harvest()`` is the one recipe behind every poster in the film: the hero, the eight fixes, the
twenty-a-round variations and every size in the bottle rack. It lays itself out for the box it is
given, so a 1584 x 396 banner and a 1080 x 1920 story come from the same function and palette.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "build"))
from kit import HEAD, SEMI, BODY, ellipse, glow, group, rect, rich  # noqa: E402

# Palettes: sky stops top to bottom, moon, far hills, near hills, title, info line, badge, badge text.
PALETTES = {
    "harvest": dict(sky=["#1C1440", "#4B2A6B", "#C2577A", "#F4A259"], moon="#FFE3A3", far="#3B2357",
                    near="#1A1030", title="#FFF6E6", info="#FFE3C2", badge="#F4A259", badge_text="#1C1440"),
    "ember": dict(sky=["#2A0F1E", "#6E1F2E", "#D9572B", "#FFB347"], moon="#FFF0C9", far="#4A1726",
                  near="#22080F", title="#FFF4E0", info="#FFE0B8", badge="#FFD166", badge_text="#2A0F1E"),
    "teal": dict(sky=["#0B2230", "#12485A", "#2E8C8C", "#E8C57A"], moon="#FFF1C1", far="#123A47",
                 near="#081A22", title="#F2FFF8", info="#D8F3E8", badge="#E8C57A", badge_text="#0B2230"),
    "plum": dict(sky=["#160C26", "#3C1A55", "#7E3C8A", "#E79AC3"], moon="#FFE9F2", far="#2C1442",
                 near="#120820", title="#FFF0F7", info="#F6D5E8", badge="#E79AC3", badge_text="#160C26"),
    "forest": dict(sky=["#0F1A14", "#1E3B2A", "#5E7F45", "#E3B65B"], moon="#FFF3CF", far="#1B3324",
                   near="#0B140E", title="#FBF7E6", info="#E8E1C0", badge="#E3B65B", badge_text="#0F1A14"),
    "dusk": dict(sky=["#101A3A", "#283C7A", "#7A6FB0", "#F3B6A0"], moon="#FFF4E4", far="#22305E",
                 near="#0C1330", title="#FFFFFF", info="#E5E8FF", badge="#F3B6A0", badge_text="#101A3A"),
    "mono": dict(sky=["#141414", "#2A2A2A", "#4A4A4A", "#8A8A8A"], moon="#F2F2F2", far="#2E2E2E",
                 near="#111111", title="#FFFFFF", info="#E0E0E0", badge="#F2F2F2", badge_text="#141414"),
    "cocoa": dict(sky=["#1E120C", "#4A2A1A", "#9C5B2E", "#F0C27B"], moon="#FFF1D6", far="#3A2015",
                  near="#170C07", title="#FFF7EA", info="#F5DEC0", badge="#F0C27B", badge_text="#1E120C"),
    "berry": dict(sky=["#1A0B1F", "#4E1640", "#B23A68", "#FF9E7A"], moon="#FFEBDD", far="#3A1033",
                  near="#160716", title="#FFF2F2", info="#FFD9D2", badge="#FF9E7A", badge_text="#1A0B1F"),
    "slate": dict(sky=["#1B2230", "#2F3C55", "#5D6F94", "#C9D3E6"], moon="#FFFFFF", far="#28334A",
                  near="#121825", title="#FFFFFF", info="#E3E9F5", badge="#C9D3E6", badge_text="#1B2230"),
}


def hills(x, y, w, h, top, amp, phase, freq=1.3, n=40):
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append([round(x + u * w, 2), round(y + h * top + amp * h * math.sin(2 * math.pi * (freq * u + phase)), 2)])
    return pts + [[x + w, y + h], [x, y + h]]


def harvest(p, x, y, w, h, palette="harvest", title="HARVEST MOON", info="NIGHT MARKET  ·  OCT 24", badge="FREE",
            title_at="top", moon_at=None, moon_size=1.0, title_scale=1.0, align=None, frame=False, plain=False,
            info_on=True, hill_amp=1.0, wide=None):
    """One poster as {sheet: [ops]}, bottom to top. Layer names start with ``p``.

    ``plain`` drops the halo, far hills and badge (the "pinch of direction" version). Landscape boxes
    (wider than 1.25:1) put the type on the left and the moon on the right.
    """
    c = PALETTES[palette] if isinstance(palette, str) else palette
    wide = (w / h > 1.25) if wide is None else wide
    s = min(w, h)
    sheets: dict[str, list] = {}
    sheets["sky"] = [{"type": "gradient", "name": f"{p}-sky", "direction": "vertical", "x": round(x, 2), "y": round(y, 2),
                      "width": round(w), "height": round(h),
                      "stops": [{"offset": o, "color": col} for o, col in zip((0, 0.45, 0.78, 1), c["sky"])]}]
    if wide:
        mx, my, md = (moon_at or (0.74, 0.42))[0], (moon_at or (0.74, 0.42))[1], 0.62 * h * moon_size
    else:
        squarish = w / h > 0.9
        mx, my = moon_at or ((0.5, 0.66 if squarish else 0.64) if title_at == "top" else (0.5, 0.38))
        md = (0.4 if squarish else 0.5) * w * moon_size
    cx, cy = x + w * mx, y + h * my
    if not plain:
        sheets["halo"] = [glow(f"{p}-halo", cx, cy, md * 2.1, c["moon"], "55")]
    sheets["moon"] = [ellipse(f"{p}-moon", cx, cy, md, md, c["moon"])]
    if not plain:
        sheets["crater"] = [ellipse(f"{p}-crater1", cx - md * 0.18, cy - md * 0.1, md * 0.16, md * 0.16, "#00000014"),
                            ellipse(f"{p}-crater2", cx + md * 0.16, cy + md * 0.14, md * 0.1, md * 0.1, "#00000012")]
        sheets["far"] = [{"type": "pen", "name": f"{p}-far", "points": hills(x, y, w, h, 0.8 if wide else 0.74, 0.04 * hill_amp, 0.15),
                          "closed": True, "smooth": False, "fill": c["far"], "stroke": "none"}]
    sheets["near"] = [{"type": "pen", "name": f"{p}-near", "points": hills(x, y, w, h, 0.9 if wide else 0.85, 0.03 * hill_amp, 0.6, 1.0),
                       "closed": True, "smooth": False, "fill": c["near"], "stroke": "none"}]
    if wide:
        size = min(0.104 * w, 0.3 * h) * title_scale
        tx, tw = x + 0.06 * w, 0.5 * w
        ty = y + (0.8 * h - 2.25 * size) / 2
        al = align or "left"
    else:
        size = (0.15 if w / h > 0.9 else 0.19) * w * title_scale
        tx, tw = x, w
        ty = y + 0.07 * h if title_at == "top" else y + h * 0.62
        al = align or "center"
        if al == "left":
            tx, tw = x + 0.08 * w, 0.84 * w
            size = min(size, 0.165 * w)
    words = title.split(" ", 1)
    sheets["title"] = [rich(f"{p}-title", "\n".join(words), tx, ty, round(size), tw, c["title"], HEAD, al, 0.92)]
    if info_on:
        isize = max(8, round(size * 0.2))
        sheets["info"] = [rich(f"{p}-info", info, tx, ty + size * 2.0, isize, tw, c["info"], SEMI, al, 1.2)]
    if badge and not plain:
        bs = 0.22 * s
        if wide:
            bs = 0.3 * md
            bx, by = cx + md * 0.28, max(y + 0.05 * h, cy - md * 0.62)
        else:
            bx, by = x + w - bs - 0.05 * w, (y + 0.4 * h) if title_at == "top" else (y + 0.06 * h)
        sheets["badge"] = [{"type": "shape", "shape": "star", "name": f"{p}-badge-star", "x": round(bx), "y": round(by),
                            "width": round(bs), "height": round(bs), "sides": 12, "inner_radius": 0.84, "fill": c["badge"]},
                           rich(f"{p}-badge-label", badge, bx, by + bs * 0.36, round(bs * 0.24), bs, c["badge_text"], HEAD,
                                "center", 1.0),
                           group(f"{p}-badge", [f"{p}-badge-star", f"{p}-badge-label"])]
    if frame:
        inset = 0.035 * s
        sheets["frame"] = [rect(f"{p}-frame", x + inset, y + inset, w - 2 * inset, h - 2 * inset, "#00000000", 0,
                                c["title"], max(1, round(0.006 * s)))]
    hills_named = [f"{p}-near"] + ([] if plain else [f"{p}-far"])
    sheets["near"].append({"type": "layer-intent", "targets": hills_named, "allow_crop": True})
    return sheets


def names(sheets):
    out = []
    for ops in sheets.values():
        for op in ops:
            if op["type"] in ("layer-intent",):
                continue
            if op["type"] == "group":
                out = [n for n in out if n not in op["targets"]] + [op["name"]]
            else:
                out.append(op["name"])
    return out


def flat(sheets):
    return [op for ops in sheets.values() for op in ops]


def poster_group(name, x, y, w, h, **kw):
    """A poster wrapped in one group (and clipped to its box) so it can move and scale as a unit."""
    sheets = harvest(name, x, y, w, h, **kw)
    return flat(sheets) + [group(name, names(sheets))]


# ------------------------------------------------------------------------------------------ cauldron
POT, POT_RIM, POT_HI = "#2A2240", "#463A66", "#FFFFFF14"
BREW = "#3FE0B0"


def cauldron(cx, rim_y, scale=1.0, brew=BREW):
    """A cauldron whose rim is centred on (cx, rim_y). Parts: pot-leg1/2, pot-body, pot-hi, pot-rim, pot-brew."""
    k = scale
    ops = [rect("pot-leg1", cx - 210 * k, rim_y + 330 * k, 60 * k, 110 * k, POT, 20 * k),
           rect("pot-leg2", cx + 150 * k, rim_y + 330 * k, 60 * k, 110 * k, POT, 20 * k),
           ellipse("pot-body", cx, rim_y + 200 * k, 640 * k, 470 * k, POT),
           ellipse("pot-hi", cx - 170 * k, rim_y + 170 * k, 90 * k, 200 * k, POT_HI),
           ellipse("pot-rim", cx, rim_y, 680 * k, 130 * k, POT_RIM),
           ellipse("pot-brew", cx, rim_y + 4 * k, 590 * k, 92 * k, brew),
           glow("pot-glow", cx, rim_y - 40 * k, 760 * k, brew, "50")]
    return ops
