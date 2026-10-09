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

Two looks also change geometry, and keep what they need to undo it in the same record:
``hand-made`` wobbles the layer's outlines with irregular (the pristine source stays in the
layer's ``irregular`` record, so removing the look restores it exactly), and ``plush`` grows fur
tufts along the edge and inner flicks with scatter, as helper layers (``part_of`` the layer)
that removing or re-applying the look deletes. Both are made from the layer as it is when the
look is applied: re-apply after moving or reshaping it.
"""

from copy import deepcopy
import zlib

from .errors import VixlError, require
from .model import MAX_LAYERS, finite, uid

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


def _soft_halo(layer, state, color, a):
    """A gradient layer becomes a radial fade with a gaussian falloff that reaches transparency at its
    inscribed ellipse, so its box never shows; other layers get a wide, soft glow."""
    base = color or _base(layer, state)
    if layer["type"] != "gradient":
        ref = _reference(layer)
        return {"outer-glow": {"color": base, "blur": round(_clamp(ref * (0.15 + 0.3 * a), 8, 100)),
                               "opacity": round(0.45 + 0.4 * a, 2)}}, []
    if layer.get("stops"):
        base = color or layer["stops"][0]["color"]
    core = round(0.55 + 0.45 * a, 2)
    return {}, [], {"direction": "radial", "falloff": "gaussian", "stops": [
        {"offset": 0, "color": f"color-mix(in srgb, {base} {round(core * 100)}%, transparent)" if core < 1 else base},
        {"offset": 1, "color": f"color-mix(in srgb, {base} 0%, transparent)"}]}


def _effect(name, amount, **extra):
    return {"name": name, "amount": amount, **extra}


def _seed(layer):
    return zlib.crc32(layer["name"].encode()) % 10000


def _grain(layer, state, color, a):
    return {}, [_effect("grain", round(0.02 + 0.12 * a, 3), seed=_seed(layer))]


def _paper(layer, state, color, a):
    return {}, [_effect("temperature", round(8 + 12 * a)), _effect("grain", round(0.03 + 0.05 * a, 3), seed=_seed(layer)),
                _effect("vignette", round(0.08 + 0.2 * a, 2), radius=0.85, strength=round(0.08 + 0.2 * a, 2))]


def _film(layer, state, color, a):
    return {}, [_effect("sepia", round(25 + 40 * a)), _effect("grain", round(0.04 + 0.06 * a, 3), seed=_seed(layer)),
                _effect("vignette", round(0.2 + 0.3 * a, 2), radius=0.7, strength=round(0.2 + 0.3 * a, 2))]


def _ink(layer, state, color, fallback):
    """The ink of a one-color print look: ``color``, else the layer's own color when it has a hue, else the
    palette's ``@accent``, else ``fallback``. A neutral gray ink is what makes a duotone muddy."""
    from .colors import parse, srgb_to_hsl

    if color:
        return _static(color, state)
    candidates = [_base(layer, state)] if layer["type"] not in ("raster", "pixel", "link") else []
    candidates += ["@accent"] if "accent" in state.get("swatches", {}) else []
    for value in candidates:
        try:
            ink = _static(value, state)
        except VixlError:
            continue
        _, saturation, lightness = srgb_to_hsl(parse(ink)[:3])
        if saturation >= 0.25 and 0.15 <= lightness <= 0.85:
            return ink
    return _static(fallback, state)


def _duotone(layer, state, color, a):
    # Shadow and highlight are the ink scaled down and up so that the ink's own brightness maps back onto
    # the ink: a flat fill in the ink keeps its color, darker tones deepen and lighter ones brighten.
    from .colors import hex_of, parse

    ink = _ink(layer, state, color, "#6366f1")
    rgb = parse(ink)[:3]
    tone = max(0.2, 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])
    shadow = tuple(c * 0.3 for c in rgb)
    highlight = tuple(min(1.0, c * (0.3 + 0.7 / tone)) for c in rgb)
    return {}, [_effect("duotone", round(70 + 30 * a), shadow_color=hex_of(shadow + (1.0,)),
                        highlight_color=hex_of(highlight + (1.0,)))]


def _risograph(layer, state, color, a):
    # One ink on warm paper. The solid ink is chosen so that the ink's own brightness prints as close to the
    # ink as the paper allows: a flat fill keeps its color, lighter tones become tints of it.
    from .colors import hex_of, parse

    ink = parse(_ink(layer, state, color, "#ff4d8d"))[:3]
    paper = parse("#fff7ec")[:3]
    tone = min(0.8, 0.299 * ink[0] + 0.587 * ink[1] + 0.114 * ink[2])
    solid = tuple(max(0.0, min(1.0, (c - tone * p) / (1 - tone))) for c, p in zip(ink, paper))
    return {}, [_effect("duotone", 100, shadow_color=hex_of(solid + (1.0,)), highlight_color=hex_of(paper + (1.0,))),
                _effect("grain", round(0.05 + 0.07 * a, 3), seed=_seed(layer))]


VECTOR = ("shape", "text", "group", "symbol")


def _sketch(layer, state, color, a):
    """Graphite hatching from the pencil-sketch effect, plus a pencil outline on vector layers (a shape that
    fills its own box has no edge inside it for the effect to find)."""
    styles = {}
    if layer["type"] in VECTOR:
        width = _clamp(_reference(layer) * (0.008 + 0.01 * a), 1, 6)
        styles["stroke"] = {"color": color or "#2f2f2f", "width": round(width, 1), "opacity": round(0.7 + 0.25 * a, 2)}
    return styles, [_effect("pencil-sketch", round(60 + 40 * a))]


def _watercolor(layer, state, color, a):
    return {}, [_effect("watercolor", round(60 + 40 * a), seed=_seed(layer))]


def _halftone(layer, state, color, a):
    return {}, [_effect("halftone", round(4 + 12 * a), color=_static(color or _base(layer, state), state))]


def _hand_made(layer, state, color, a):
    return {}, []


def _plush(layer, state, color, a):
    base = color or _base(layer, state)
    return {"gradient-overlay": {"start": f"lighten({base}, {round(6 + 12 * a)}%)",
                                 "end": f"darken({base}, {round(6 + 14 * a)}%)", "direction": "vertical"}}, []


def _wobble(project, layer, a, record):
    """hand-made: irregular wobble on the layer's vector outlines, restored when the look goes."""
    from .irregular import vector_layers
    from .operations import execute

    require(layer["type"] in ("shape", "group"), f"hand-made wobbles vector outlines; {layer['name']!r} is a "
            f"{layer['type']} layer (try the sketch look or drawn-texture)", field="look")
    members = vector_layers(project, {"target": layer["id"]})
    taken = [m["name"] for m in members if "irregular" in m]
    require(not taken, f"{', '.join(taken)} already carries irregular; remove it (irregular remove: true) or adjust "
            "it directly instead of adding hand-made", field="look")
    execute(project, {"type": "irregular", "target": layer["id"], "seed": _seed(layer), "strength": "natural",
                      "amount": round(0.3 + 1.2 * a, 3), "only": ["wobble", "jitter", "width"]})
    record["irregular"] = [m["id"] for m in members]


def _fur(project, layer, a, record):
    """plush: fur tufts behind the edge and flicks inside it, as helper layers of the layer."""
    from .scatter import execute_scatter

    require(layer["type"] == "shape", f"plush grows fur along a shape's outline; {layer['name']!r} is a "
            f"{layer['type']} layer", field="look")
    before = {x["id"] for x in project.state["layers"]}
    short = min(layer["width"], layer["height"])
    execute_scatter(project, {"type": "scatter", "target": layer["id"], "preset": "fur", "seed": _seed(layer),
                              "length": max(3.0, short * (0.04 + 0.06 * a)), "flicks": round(0.3 + 0.5 * a, 3),
                              "name": f"{layer['name']}-plush"})
    made = [x for x in project.state["layers"] if x["id"] not in before]
    below = project.state["layers"].index(layer)
    shading = _plush(layer, project.state, record.get("color"), a)[0]
    for item in made:
        item["part_of"] = layer["id"]
        item.pop("scatter", None)
        if item["type"] == "shape" and project.state["layers"].index(item) < below:
            # The tufts carry the body's gradient, so the fur edge shades with it.
            item["styles"] = deepcopy(shading)
    record["parts"] = [x["id"] for x in made]
    project.state["active_layer"] = layer["id"]


# Looks that also change geometry: name -> hook(project, layer, amount, record).
GEOMETRY = {"hand-made": _wobble, "plush": _fur}

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
    "soft-halo": (_soft_halo, "Soft light halo: a gradient layer becomes a radial gaussian fade to transparent (no visible box); other layers get a wide soft glow.", "native", ["glows behind subjects", "light sources", "backgrounds"]),
    "grain": (_grain, "Fine film grain that breaks up flat color.", "raster", ["backgrounds", "posters", "textures"]),
    "paper": (_paper, "Warm paper: slight warm tint, fibre grain and soft edge darkening.", "raster", ["full-canvas backgrounds", "letterpress", "zines"]),
    "film": (_film, "Faded film: sepia, grain and vignette.", "raster", ["photos", "vintage"]),
    "duotone": (_duotone, "Two tones of one ink: color, else the layer's own hue, else the palette @accent; a flat fill keeps its hue.", "raster", ["photos", "posters", "brand imagery"]),
    "risograph": (_risograph, "One ink on warm paper with grain (ink: color, else the layer's own hue, else @accent); lighter tones print as tints.", "raster", ["zines", "posters", "illustration"]),
    "sketch": (_sketch, "Graphite pencil: edge lines and tone hatching, plus a pencil outline on shapes and text.", "raster", ["photos", "illustration"]),
    "watercolor": (_watercolor, "Watercolor wash: lighter, blotchy pigment pooled in a darker rim inside every edge.", "raster", ["photos", "illustration", "backgrounds"]),
    "halftone": (_halftone, "Print-style dot screen: turns a photo or gradient into black and white dots.", "raster", ["pop art", "newsprint", "photos"]),
    "hand-made": (_hand_made, "Hand-drawn wobble on vector outlines and line weight (irregular); removing it restores the exact source.", "native", ["characters", "stickers", "botanical shapes"]),
    "plush": (_plush, "Soft toy fur: tufts along a shape's edge, inner flicks and a soft gradient.", "native", ["mascots", "toys", "animals"]),
}


def catalog():
    from .house_style import tier_of

    return {name: {"summary": summary, "svg": svg, "best_for": best, "tier": tier_of("looks", name),
                   "safe": tier_of("looks", name) == "safe"}
            for name, (_, summary, svg, best) in LOOKS.items()}


def schemas(add):
    from .schema import S, B

    add("look", {
        "look": {"enum": list(LOOKS)},
        "color": S,
        "amount": {"type": "number", "minimum": 0, "maximum": 1},
        "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS, "uniqueItems": True},
        "remove": B,
    }, ["look"])


def _strip(layer, name, project=None):
    """Remove what ``name`` added to ``layer`` and forget the record."""
    record = layer.get("looks", {}).pop(name, None)
    if record is None:
        return False
    if project is not None and (record.get("irregular") or record.get("parts")):
        from .design import descendants
        from .irregular import restore

        for item in project.state["layers"]:
            if item["id"] in record.get("irregular", []):
                restore(project, item)
        parts = {i for i in record.get("parts", []) if any(x["id"] == i and x.get("part_of") == layer["id"]
                                                           for x in project.state["layers"])}
        for ident in list(parts):
            parts |= descendants(project, ident)
        project.state["layers"][:] = [x for x in project.state["layers"] if x["id"] not in parts]
    for style in record.get("styles", []):
        layer.get("styles", {}).pop(style, None)
    for key, value in record.get("fields", {}).items():
        if value is None:
            layer.pop(key, None)
        else:
            layer[key] = deepcopy(value)
    if "styles" in layer and not layer["styles"] and record.get("styles"):
        layer.pop("styles")
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
        require(_strip(layer, name, project), f"{layer['name']!r} has no {name!r} look", field="look")
        return
    builder = LOOKS[name][0]
    _strip(layer, name, project)
    styles, effects, *rest = builder(layer, state, color, amount)
    fields = rest[0] if rest else {}
    record = {"styles": [], "effects": [], "amount": amount, **({"color": color} if color else {})}
    if fields:
        # The layer's own values, put back when the look is removed.
        record["fields"] = {key: deepcopy(layer.get(key)) for key in fields}
        candidate = {**layer, **deepcopy(fields)}
        from .design import validate_gradient
        validate_gradient(candidate, state)
        layer.update(deepcopy(fields))
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
    if name in GEOMETRY:
        GEOMETRY[name](project, layer, amount, record)
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
