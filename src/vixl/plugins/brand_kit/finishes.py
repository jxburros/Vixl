"""Print finishes for mockups: how a design looks once it is printed, stitched or enamelled onto a product.

A finish is an ordinary stack on the placed design layer: effects and layer styles on the linked design, plus a few
helper layers (a stitch hatch, a weave, a sheen) clipped to the design's own shape. Nothing is baked, so every
layer stays editable, and sizes scale with the area (``unit``) so one finish suits a sleeve and a full front.
The core's ``look`` operation stays as it is: these are mockup finishes, not general looks.
"""

import math

FINISHES = {
    "screen": {"summary": "screen print: ink that spreads a little into the weave, with a fine dot-screen texture"},
    "puff": {"summary": "puff print: raised foam ink, embossed with a soft shadow"},
    "embroidery": {"summary": "embroidery: diagonal stitch hatch, embossed with a satin sheen and a thread shadow"},
    "enamel": {"summary": "enamel: flat, saturated colour in a metal line, with a hard gloss"},
    "woven": {"summary": "woven label: a fine warp and weft over the art, a soft edge and a slight relief"},
}


def _unit(box):
    return max(0.4, min(box[2], box[3]) / 330)


def hatch_path(width, height, spacing, angle, offset=0.0):
    """Parallel lines every ``spacing`` px at ``angle`` degrees across a ``width`` × ``height`` box, clipped to it."""
    theta = math.radians(angle)
    dx, dy = math.cos(theta), math.sin(theta)
    nx, ny = -dy, dx
    half = math.hypot(width, height) / 2
    cx, cy = width / 2, height / 2
    parts = []
    count = int(half / spacing) + 1
    for i in range(-count, count + 1):
        t = i * spacing + offset
        px, py = cx + nx * t, cy + ny * t
        lo, hi = -2 * half, 2 * half
        for axis, (p, d, size) in enumerate(((px, dx, width), (py, dy, height))):
            if abs(d) < 1e-9:
                if not 0 <= p <= size:
                    lo, hi = 1, 0
                continue
            a, b = (0 - p) / d, (size - p) / d
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if lo >= hi:
            continue
        parts.append(f"M{px + dx * lo:.1f} {py + dy * lo:.1f} L{px + dx * hi:.1f} {py + dy * hi:.1f}")
    return " ".join(parts) or "M0 0 L1 1"


def _lines(name, box, spacing, angle, color, width, opacity, blend, base, offset=0.0, **style):
    x, y, w, h = box
    return [{"type": "shape", "shape": "path", "name": name, "x": x, "y": y, "width": w, "height": h,
             "path": hatch_path(w, h, spacing, angle, offset), "fill": "transparent", "stroke": color,
             "stroke_width": round(width, 2), "line_cap": "butt", "opacity": opacity, **style},
            {"type": "blend", "target": name, "value": blend},
            {"type": "clip", "target": name, "base": base}]


def _sheen(name, box, angle, stops, base, blend="screen"):
    x, y, w, h = box
    return [{"type": "gradient", "name": name, "x": x, "y": y, "width": w, "height": h, "direction": "angled",
             "angle": angle, "stops": [{"offset": o, "color": c} for o, c in stops]},
            {"type": "blend", "target": name, "value": blend}, {"type": "clip", "target": name, "base": base}]


def _shadow(name, u, dx, dy, blur, opacity):
    return {"type": "layer-style", "target": name, "name": "drop-shadow",
            "settings": {"color": "#000000", "dx": round(dx * u, 2), "dy": round(dy * u, 2), "blur": round(blur * u, 2),
                         "opacity": opacity}}


def _effect(name, effect, amount, **extra):
    return {"type": "effect", "target": name, "name": effect, "amount": amount, **extra}


def screen(name, box, u):
    ops = [_effect(name, "gaussian-blur", round(0.55 * u, 2)), _effect(name, "grain", 0.03, seed=7)]
    cell = max(2, round(3 * u))
    x, y, w, h = box
    dots = f"{name}-finish-dots"
    ops += [{"type": "shape", "shape": "rectangle", "name": dots, "x": x, "y": y, "width": w, "height": h,
             "fill": "#808080", "opacity": 0.14},
            _effect(dots, "halftone", cell),
            {"type": "blend", "target": dots, "value": "multiply"}, {"type": "clip", "target": dots, "base": name}]
    return ops


def puff(name, box, u):
    return [_effect(name, "emboss", 22), _effect(name, "saturation", 20), _effect(name, "gaussian-blur", round(0.5 * u, 2)),
            _shadow(name, u, 1.6, 3.2, 3.6, 0.5),
            *_sheen(f"{name}-finish-lift", box, 235, [(0, "rgba(255,255,255,0.28)"), (0.55, "rgba(255,255,255,0)"),
                                                      (1, "rgba(0,0,0,0.12)")], name)]


def embroidery(name, box, u):
    return [_effect(name, "emboss", 30), _effect(name, "saturation", 26), _effect(name, "contrast", 6),
            _effect(name, "grain", 0.05, seed=11),
            _shadow(name, u, 1.2, 2.0, 2.2, 0.55),
            *_lines(f"{name}-finish-threads", box, 2.6 * u, 52, "#000000", 1.1 * u, 0.26, "multiply", name),
            *_lines(f"{name}-finish-thread-light", box, 2.6 * u, 52, "#ffffff", 0.9 * u, 0.2, "screen", name,
                    offset=1.3 * u),
            *_sheen(f"{name}-finish-satin", box, 52, [(0, "rgba(255,255,255,0)"), (0.3, "rgba(255,255,255,0.34)"),
                                                      (0.5, "rgba(255,255,255,0)"), (0.75, "rgba(255,255,255,0.22)"),
                                                      (1, "rgba(255,255,255,0)")], name)]


def enamel(name, box, u):
    return [_effect(name, "saturation", 14), _effect(name, "contrast", 8),
            {"type": "layer-style", "target": name, "name": "stroke",
             "settings": {"color": "#c9a24a", "width": round(max(1.5, 2.4 * u), 2), "opacity": 1}},
            _shadow(name, u, 0.8, 2.2, 2.6, 0.45),
            *_sheen(f"{name}-finish-gloss", box, 38, [(0, "rgba(255,255,255,0.5)"), (0.34, "rgba(255,255,255,0.12)"),
                                                      (0.35, "rgba(255,255,255,0)"), (1, "rgba(255,255,255,0)")], name)]


def woven(name, box, u):
    return [_effect(name, "gaussian-blur", round(0.45 * u, 2)), _effect(name, "emboss", 14),
            _shadow(name, u, 0.6, 1.2, 1.6, 0.4),
            *_lines(f"{name}-finish-warp", box, 1.7 * u, 90, "#000000", 0.7 * u, 0.2, "multiply", name),
            *_lines(f"{name}-finish-weft", box, 1.7 * u, 0, "#000000", 0.7 * u, 0.16, "multiply", name),
            *_lines(f"{name}-finish-weft-light", box, 1.7 * u, 0, "#ffffff", 0.5 * u, 0.12, "screen", name,
                    offset=0.85 * u)]


BUILDERS = {"screen": screen, "puff": puff, "embroidery": embroidery, "enamel": enamel, "woven": woven}


def operations(finish, name, box):
    """The operations that give the placed design layer ``name`` (in ``box``) the ``finish``."""
    return BUILDERS[finish](name, box, _unit(box))
