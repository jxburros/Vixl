"""Named finishing looks: glow, shadows, grain, paper and more, applied in one operation.

A flat shape reads as a draft; a soft shadow, a gradient, a little grain make it read as finished.
Each look is a recipe over what the engine already renders: layer styles (drop shadow, outer glow,
stroke, gradient overlay) and non-destructive effects (grain, sepia, vignette, duotone, halftone
…). The result is ordinary, editable styles and effects on the layer, so the PNG and SVG exports
treat them exactly as hand-added ones: styles and blur-like effects are native SVG filters, the
rest fall back to an embedded raster under the usual ``svg_policy``. A layer remembers which
looks it carries (``looks``), so ``remove: true`` takes one off again without touching anything
added by hand, and applying a look twice replaces rather than stacks it.

``amount`` (0-1, default 0.5) moves each look between subtle and strong; sizes scale with the
layer, so the same look suits an icon and a poster.
"""

from copy import deepcopy
import zlib

from .errors import VixlError, require
from .model import finite, uid

TYPES = ("look",)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _reference(layer):
    return max(8, min(layer["width"], layer["height"]))


def _base(layer, state):
    """The layer's own main color, as written (it may be an @swatch): fill, text color, gradient start or, for an
    outline-only shape, its stroke; white when it has none."""
    for key in ("fill", "color", "start", "stroke"):
        value = layer.get(key)
        if isinstance(value, str) and value not in ("transparent", ""):
            return value
    return "#ffffff"


def _static(value, state):
    """A concrete #hex for effects, which store colors rather than swatch references."""
    from .colors import hex_of, parse
    from .design import resolve_color

    return hex_of(parse(resolve_color(value, state))[:3] + (1.0,))


def _glow(layer, state, color, a):
    ref = _reference(layer)
    return {"outer-glow": {"color": color or _base(layer, state), "blur": round(_clamp(ref * (0.04 + 0.14 * a), 4, 100)),
                           "opacity": round(0.55 + 0.45 * a, 2)}}, []


def _neon(layer, state, color, a):
    ref = _reference(layer)
    tube = color or _base(layer, state)
    return {"stroke": {"color": tube, "width": round(_clamp(ref * 0.02, 1, 8))},
            "outer-glow": {"color": tube, "blur": round(_clamp(ref * (0.06 + 0.2 * a), 6, 100)), "opacity": 0.9}}, []


def _soft_shadow(layer, state, color, a):
    ref = _reference(layer)
    return {"drop-shadow": {"color": color or "#000000", "dx": 0, "dy": round(_clamp(ref * (0.03 + 0.05 * a), 2, 60)),
                            "blur": round(_clamp(ref * (0.05 + 0.1 * a), 3, 100)), "opacity": round(0.2 + 0.3 * a, 2)}}, []


def _hard_shadow(layer, state, color, a):
    offset = round(_clamp(_reference(layer) * (0.04 + 0.04 * a), 3, 60))
    return {"drop-shadow": {"color": color or "#000000", "dx": offset, "dy": offset, "blur": 0, "opacity": 1}}, []


def _outline(layer, state, color, a):
    return {"stroke": {"color": color or "#000000", "width": round(_clamp(_reference(layer) * (0.015 + 0.02 * a), 1, 12))}}, []


def _gradient(layer, state, color, a):
    base = color or _base(layer, state)
    return {"gradient-overlay": {"start": f"lighten({base}, {round(8 + 20 * a)}%)",
                                 "end": f"darken({base}, {round(8 + 25 * a)}%)", "direction": "vertical"}}, []


def _effect(name, amount, **extra):
    return {"name": name, "amount": amount, **extra}


def _seed(layer):
    return zlib.crc32(layer["name"].encode()) % 10000


def _grain(layer, state, color, a):
    return {}, [_effect("grain", round(0.02 + 0.12 * a, 3), seed=_seed(layer))]


def _paper(layer, state, color, a):
    return {}, [_effect("temperature", round(6 + 16 * a)), _effect("grain", round(0.03 + 0.05 * a, 3), seed=_seed(layer)),
                _effect("vignette", round(0.08 + 0.2 * a, 2), radius=0.85, strength=round(0.08 + 0.2 * a, 2))]


def _film(layer, state, color, a):
    return {}, [_effect("sepia", round(25 + 40 * a)), _effect("grain", round(0.04 + 0.06 * a, 3), seed=_seed(layer)),
                _effect("vignette", round(0.2 + 0.3 * a, 2), radius=0.7, strength=round(0.2 + 0.3 * a, 2))]


def _duotone(layer, state, color, a):
    ink = _static(color or "#6366f1", state)
    return {}, [_effect("duotone", round(70 + 30 * a), shadow_color=_static(f"darken({ink}, 55%)", state),
                        highlight_color=_static(f"lighten({ink}, 60%)", state))]


def _risograph(layer, state, color, a):
    ink = _static(color or "#ff4d8d", state)
    return {}, [_effect("duotone", 100, shadow_color=_static(f"darken({ink}, 45%)", state), highlight_color="#fff7ec"),
                _effect("grain", round(0.05 + 0.07 * a, 3), seed=_seed(layer))]


def _sketch(layer, state, color, a):
    return {}, [_effect("pencil-sketch", round(60 + 40 * a))]


def _watercolor(layer, state, color, a):
    return {}, [_effect("watercolor", round(60 + 40 * a))]


def _halftone(layer, state, color, a):
    return {}, [_effect("halftone", round(4 + 12 * a))]


# name -> (builder, summary, svg export, best for). svg: "native" when every part is an SVG filter.
LOOKS = {
    "clean-flat": (lambda layer, state, color, amount: ({}, []), "Restrained flat color without effects.", "native", ["documents", "cards"]),
    "subtle-grain": (lambda layer, state, color, amount: _grain(layer, state, color, amount * 0.1), "A restrained grain finish for broad-use backgrounds.", "raster", ["backgrounds", "editorial"]),
    "light-paper": (lambda layer, state, color, amount: _paper(layer, state, color, amount * 0.1), "A quiet paper finish with minimal tint and texture.", "raster", ["documents", "backgrounds"]),
    "glow": (_glow, "Soft outer glow in the layer's own color (or color).", "native", ["neon signs", "icons on dark", "highlights"]),
    "neon": (_neon, "Bright outline with a wide glow, like a lit tube.", "native", ["cyberpunk", "nightlife", "text outlines"]),
    "soft-shadow": (_soft_shadow, "Gentle blurred drop shadow that lifts a card or button off the page.", "native", ["cards", "buttons", "ui"]),
    "hard-shadow": (_hard_shadow, "Solid offset shadow with no blur (sticker and neo-brutalist look).", "native", ["stickers", "neo-brutalism", "badges"]),
    "outline": (_outline, "Clean outline around the shape or text.", "native", ["stickers", "text on photos", "badges"]),
    "gradient": (_gradient, "Vertical light-to-dark gradient over a flat fill, from its own color (or color).", "native", ["buttons", "icons", "backgrounds"]),
    "grain": (_grain, "Fine film grain that breaks up flat color.", "raster", ["backgrounds", "posters", "textures"]),
    "paper": (_paper, "Warm paper: slight warm tint, fibre grain and soft edge darkening.", "raster", ["full-canvas backgrounds", "letterpress", "zines"]),
    "film": (_film, "Faded film: sepia, grain and vignette.", "raster", ["photos", "vintage"]),
    "duotone": (_duotone, "Map a photo or illustration to two tones of one color (color); a flat fill has one tone, so it turns gray.", "raster", ["photos", "posters", "brand imagery"]),
    "risograph": (_risograph, "Two-ink print: one ink color on warm paper with grain; best on photos and tonal artwork.", "raster", ["zines", "posters", "illustration"]),
    "sketch": (_sketch, "Pencil-sketch rendering of a photo or illustration (flat fills have no edges and fade out).", "raster", ["photos", "illustration"]),
    "watercolor": (_watercolor, "Soft watercolor wash for photos and illustration.", "raster", ["photos", "illustration", "backgrounds"]),
    "halftone": (_halftone, "Print-style dot screen: turns a photo or gradient into black and white dots.", "raster", ["pop art", "newsprint", "photos"]),
}


def catalog():
    from .safe_catalog import SAFE_LOOKS

    return {name: {"summary": summary, "svg": svg, "best_for": best, "safe": name in SAFE_LOOKS}
            for name, (_, summary, svg, best) in LOOKS.items()}


def schemas(add):
    from .schema import S, B

    add("look", {
        "look": {"enum": list(LOOKS)},
        "color": S,
        "amount": {"type": "number", "minimum": 0, "maximum": 1},
        "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": 512, "uniqueItems": True},
        "remove": B,
    }, ["look"])


def _strip(layer, name):
    """Remove what ``name`` added to ``layer`` and forget the record."""
    record = layer.get("looks", {}).pop(name, None)
    if record is None:
        return False
    for style in record.get("styles", []):
        layer.get("styles", {}).pop(style, None)
    gone = set(record.get("effects", []))
    layer["effects"] = [effect for effect in layer["effects"] if effect["id"] not in gone]
    if not layer["looks"]:
        layer.pop("looks")
    return True


def apply_look(project, layer, name, color=None, amount=0.5, remove=False):
    from .design import validate_style
    from .operations import effect_valid

    state = project.state
    if remove:
        require(_strip(layer, name), f"{layer['name']!r} has no {name!r} look", field="look")
        return
    builder = LOOKS[name][0]
    _strip(layer, name)
    styles, effects = builder(layer, state, color, amount)
    record = {"styles": [], "effects": [], "amount": amount, **({"color": color} if color else {})}
    for style, settings in styles.items():
        validate_style(style, settings, state)
        # A style belongs to one look: applying this one takes it over from any other.
        for other in layer.get("looks", {}).values():
            if style in other["styles"]:
                other["styles"].remove(style)
        layer.setdefault("styles", {})[style] = deepcopy(settings)
        record["styles"].append(style)
    require(len(layer["effects"]) + len(effects) <= 256, "Effect limit reached", "resource_limit")
    for settings in effects:
        effect = {"id": uid("fx"), "enabled": True, "selection": None, **settings}
        effect_valid(effect)
        layer["effects"].append(effect)
        record["effects"].append(effect["id"])
    layer.setdefault("looks", {})[name] = record


def execute(project, op):
    name = op["look"]
    amount = finite(op.get("amount", 0.5), "amount", 0, 1)
    if op.get("color") is not None:
        from .render import color as parse_color
        from .design import resolve_color

        parse_color(resolve_color(op["color"], project.state))
    targets = op.get("targets") or [op.get("target")]
    layers = [project.layer(t) for t in targets]
    require(len({layer["id"] for layer in layers}) == len(layers), "Duplicate layer references", field="targets")
    for layer in layers:
        if layer["type"] == "field":
            raise VixlError("invalid_operation", "Looks do not apply to form fields", field="target")
        apply_look(project, layer, name, op.get("color"), amount, bool(op.get("remove")))


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog="vixl look", description="Apply a finishing look: " + ", ".join(LOOKS))
    p.add_argument("target")
    p.add_argument("look", choices=list(LOOKS))
    p.add_argument("--color")
    p.add_argument("--amount", type=float)
    p.add_argument("--remove", action="store_true", default=None)
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
