"""Scene atmosphere as single operations: ``reflection``, ``haze``, ``star-field``, ``string-lights`` and ``bokeh``.

Four of them build ordinary editable layers (shapes, pen paths and radial gradients in one named group), so
every exporter draws them with its own fill, stroke and gradient rules and nothing new is needed per format.
They are operations rather than stack effects on purpose: an effect has no parts, so one star or one band of fog
could not be moved, recoloured or deleted, and every exporter would have to learn to draw it. Light falloff is the
``lighting`` operation's gaussian lights.
``reflection`` cannot be vector: it mirrors rendered pixels, so it makes one raster layer and keeps its
settings on that layer; running it again with ``target`` set to that layer re-renders it after the scene
above the horizon changed. Everything random is drawn from ``seed``, so a seed gives the same result.
"""

from copy import deepcopy
import math

import numpy as np

from ...errors import VixlError, require
from ...geometry import compact_number
from ...model import finite
from ...notices import note

TYPES = ("reflection", "haze", "star-field", "string-lights", "bokeh")
TEXT_TYPES = ("text", "table", "field")
BULBS = ("globe", "pear", "lantern")
MAX_STARS = 600
MAX_BULBS = 120
MAX_DISCS = 80
FOG_LAYERS = (2, 5)
FOG_COLOR = "#dfe6ee"
REFLECTION_KEYS = ("horizon", "targets", "squash", "ripple", "breakup", "fade", "blur", "opacity", "tint",
                   "tint_amount", "seed")


def schemas(add):
    from ...schema import N, S, field

    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    region = {"type": "array", "items": N, "minItems": 4, "maxItems": 4,
              "description": "[x, y, width, height] in canvas pixels; default the whole canvas."}
    span = {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 2, "maxItems": 2}
    unit = {"type": "number", "minimum": 0, "maximum": 1}
    seed = {"type": "integer", "minimum": 0}
    layers = {"type": "array", "items": S, "maxItems": 256}
    below = field(S, "Insert the new group directly below this top-level layer. Default: below the lowest text "
                     "layer, so copy stays on top (star-field and bokeh: just above the backdrop, the full-width "
                     "sky, sea or background layers at the bottom of the stack).")
    add("reflection", {
        "target": field(S, "An existing reflection layer to re-render (after the scene above the horizon "
                           "changed), keeping its settings except the ones given here."),
        "name": field(S, "Name of the reflection layer (default reflection)."),
        "horizon": field(N, "The waterline in canvas pixels: what lies above it is mirrored into the area below it."),
        "targets": {**layers, "description": "Layers to mirror (top-level, sharing a parent). Default: every "
                    "visible top-level layer that lies above the horizon, except text and full-canvas backgrounds."},
        "squash": field({"type": "number", "minimum": 0.2, "maximum": 1.5},
                        "Vertical scale of the mirrored image (default 0.8; 1 is a true mirror)."),
        "ripple": field(unit, "Sideways ripple displacement, growing toward the viewer: 0 still water to 1 choppy "
                              "(default 0.35)."),
        "breakup": field(unit, "How much the reflection breaks into horizontal ripple bands: 0 unbroken to 1 "
                               "strongly banded (default 0.4)."),
        "fade": field(unit, "How fast the reflection fades with depth: 0 slow to 1 fast (default 0.6)."),
        "blur": field({"type": "number", "minimum": 0, "maximum": 200},
                      "Vertical smear in pixels (default 0.3% of the canvas height)."),
        "opacity": field(unit, "Strength of the reflection at the waterline (default 0.7)."),
        "tint": field(S, "Water colour mixed into the reflection (optional)."),
        "tint_amount": field(unit, "How much of tint is mixed in (default 0.25 when tint is given)."),
        "seed": field(seed, "Seed for the ripple pattern (default 0)."),
    })
    add("haze", {
        "target": field(S, "The light source (a lamp, sun, lantern or window): the haze is centred on it and "
                           "placed directly below it. For fog: a layer whose box is the fog zone instead."),
        "name": field(S, "Name of the group (default haze, or fog for form fog)."),
        "x": field(N, "Centre x in canvas pixels when there is no target (fog: the zone's centre, default the "
                      "canvas centre)."),
        "y": field(N, "Centre y in canvas pixels when there is no target (fog: the zone's centre, default 60% "
                      "of the canvas height)."),
        "width": field({"type": "number", "exclusiveMinimum": 0},
                       "Width of the glow band in pixels (default 6x the target's width and at least 15% of the canvas "
                       "width, or 60% of the canvas without a target; fog: 110% of the canvas width)."),
        "height": field({"type": "number", "exclusiveMinimum": 0},
                        "Height of the glow band in pixels (default 45% of the width for a band, equal for round; "
                        "fog: the height the bands are stacked over, default 30% of the canvas height)."),
        "form": field({"enum": ["band", "round", "fog"]},
                      "band (default): a wide soft band, as light spreads over a horizon or along a street; round: "
                      "an even halo; fog: stacked soft horizontal bands that are lighter and less saturated toward "
                      "the horizon (set layers, density and behind)."),
        "color": field(S, "Glow colour. Default: the target's fill, or warm #ffd38a. For fog: the colour of the "
                          "nearest band (default #dfe6ee); the bands toward the horizon are lighter and less "
                          "saturated."),
        "strength": field(unit, "Opacity at the centre of the glow (default 0.45). Fog uses density instead."),
        "layers": field({"type": "integer", "minimum": FOG_LAYERS[0], "maximum": FOG_LAYERS[1]},
                        "Fog only: how many bands (2-5, default 3), the farthest first."),
        "density": field(unit, "Fog only: how thick the fog is, 0 clear to 1 heavy (default 0.5); the farthest "
                               "band is the densest."),
        "behind": {"type": "array", "items": S, "minItems": 1, "maxItems": 64,
                   "description": "Fog only: foreground layers the fog sits behind, so they stay crisp. The fog "
                                  "goes directly below the lowest of them (default: below the lowest text layer). "
                                  "Run the fog once per gap to put it between several ranges of hills."},
        "seed": field(seed, "Seed for where the fog's bands drift (default 0); band and round are not random."),
        "below": below,
    })
    add("star-field", {
        "target": field(S, "A layer whose box is the region (the sky, say), instead of region."),
        "name": field(S, "Name of the star group (default stars)."),
        "region": region,
        "count": field({"type": "integer", "minimum": 1, "maximum": MAX_STARS},
                       "Number of stars (default from the region's area)."),
        "size": {**span, "description": "[smallest, largest] star radius in pixels (default 0.12%-0.45% of the "
                 "canvas's shorter side); most stars are small."},
        "opacity": {**span, "description": "[dimmest, brightest] star opacity, 0-1 (default [0.35, 1])."},
        "color": field(S, "Star colour (default #fff6e0)."),
        "sparkles": field({"type": "integer", "minimum": 0, "maximum": 60},
                          "How many of the brightest stars are drawn as four-point sparkles (default count/25)."),
        "fade": field(unit, "Thin the stars toward the bottom of the region, as a sky does toward the horizon: 0 "
                            "even to 1 none at the bottom (default 0.5)."),
        "avoid": {**layers, "description": "Layers the stars keep clear of. Default: every visible text, table "
                  "and field layer."},
        "clearance": field({"type": "number", "minimum": 0},
                           "Gap kept around avoided layers in pixels (default 2.5% of the canvas's shorter side)."),
        "seed": field(seed, "Seed for star placement (default 0)."),
        "below": below,
    })
    add("string-lights", {
        "target": field(S, "A path or shape layer to hang the bulbs along (it stays the wire). Without it, give "
                           "from and to."),
        "name": field(S, "Name of the group (default string-lights)."),
        "from": {**point, "description": "Start of the wire [x, y] in canvas pixels when there is no target."},
        "to": {**point, "description": "End of the wire [x, y] in canvas pixels when there is no target."},
        "sag": field(N, "How far the wire dips at its middle in pixels (default 12% of the span)."),
        "count": field({"type": "integer", "minimum": 1, "maximum": MAX_BULBS},
                       "Number of bulbs, evenly spaced along the wire (default from spacing)."),
        "spacing": field({"type": "number", "exclusiveMinimum": 0},
                         "Distance between bulbs along the wire in pixels (default 4x the bulb size)."),
        "size": field({"type": "number", "exclusiveMinimum": 0},
                      "Bulb width in pixels (default 2.4% of the canvas's shorter side)."),
        "bulb": field({"enum": list(BULBS)}, "Bulb form: globe (round, default), pear (tall) or lantern (a paper "
                      "lantern with cap and base)."),
        "colors": {"type": "array", "items": S, "minItems": 1, "maxItems": 12,
                   "description": "Bulb colours, used in turn along the wire (default warm #ffd77a)."},
        "glow": field(unit, "Glow around each bulb: 0 none to 1 wide (default 0.6)."),
        "hang": field({"type": "number", "minimum": 0},
                      "Drop from the wire to the top of each bulb in pixels (default half the bulb size)."),
        "jitter": field(unit, "Seeded variation of each bulb's drop below the wire (default 0.25)."),
        "wire": field(S, "Wire colour (default #2b2620)."),
        "wire_width": field({"type": "number", "exclusiveMinimum": 0},
                            "Wire thickness in pixels (default 8% of the bulb size, at least 1.5)."),
        "seed": field(seed, "Seed for the jitter (default 0)."),
        "below": below,
    })
    add("bokeh", {
        "target": field(S, "A layer whose box is the region, instead of region."),
        "name": field(S, "Name of the group (default bokeh)."),
        "region": region,
        "count": field({"type": "integer", "minimum": 1, "maximum": MAX_DISCS}, "Number of discs (default 14)."),
        "size": {**span, "description": "[smallest, largest] disc diameter in pixels (default 4%-12% of the "
                 "canvas's shorter side)."},
        "opacity": {**span, "description": "[faintest, strongest] disc opacity, 0-1 (default [0.2, 0.55])."},
        "colors": {"type": "array", "items": S, "minItems": 1, "maxItems": 12,
                   "description": "Disc colours, picked in turn (default warm lights #ffd38a, #ffb36b, #fff1c9)."},
        "softness": field(unit, "Edge softness: 0 crisp discs to 1 fully soft (default 0.3)."),
        "avoid": {**layers, "description": "Layers the discs keep clear of (default none)."},
        "blend": field({"enum": ["normal", "screen", "add", "lighten"]},
                       "How the discs mix with what is below (default screen)."),
        "seed": field(seed, "Seed for placement and sizes (default 0)."),
        "below": below,
    })


# ---------------------------------------------------------------------------------------------------------------
# Shared helpers


def _rng(op):
    seed = op.get("seed", 0)
    require(isinstance(seed, int) and 0 <= seed < 2 ** 63, "Seed must be a nonnegative 63-bit integer", field="seed")
    return np.random.default_rng(seed)


def _canvas(project):
    c = project.state["canvas"]
    return float(c["width"]), float(c["height"])


def _region(project, op):
    w, h = _canvas(project)
    if op.get("target") and "region" not in op:
        x0, y0, x1, y1 = _boxes(project, [project.layer(op["target"])])[0]
        return x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0)
    value = op.get("region", [0, 0, w, h])
    require(isinstance(value, list) and len(value) == 4, "region is [x, y, width, height]", field="region")
    x, y = finite(value[0], "region x"), finite(value[1], "region y")
    rw, rh = finite(value[2], "region width", 1, 1e6), finite(value[3], "region height", 1, 1e6)
    return x, y, rw, rh


def _span(op, key, default, low, high):
    value = op.get(key, default)
    require(isinstance(value, list) and len(value) == 2, f"{key} is [smallest, largest]", field=key)
    a, b = (finite(v, key, low, high) for v in value)
    return (a, b) if a <= b else (b, a)


def _boxes(project, refs):
    """Canvas bounding boxes (x0, y0, x1, y1) of the listed layers."""
    from ...scatter import _matrices, outline

    cache = _matrices(project)
    boxes = []
    for layer in refs:
        points = np.vstack([p for p, _ in outline(project, layer, cache=cache)])
        boxes.append((*points.min(axis=0), *points.max(axis=0)))
    return boxes


def _avoided(project, op, default_text):
    if "avoid" in op:
        return [project.layer(ref) for ref in op["avoid"]]
    if not default_text:
        return []
    return [layer for layer in project.state["layers"] if layer["type"] in TEXT_TYPES and layer.get("visible", True)]


def _top(project, layer):
    index = {item["id"]: item for item in project.state["layers"]}
    while layer.get("parent") and layer["parent"] in index:
        layer = index[layer["parent"]]
    return layer


def _settle(project, group, op, under=None):
    """Move a new top-level group below ``op['below']``, ``under``, or the lowest top-level text layer."""
    from ...operations import execute as apply

    if "below" in op:
        under = _top(project, project.layer(op["below"]))
    elif under is None:
        texts = [layer for layer in project.state["layers"]
                 if not layer.get("parent") and layer["type"] in TEXT_TYPES and layer["id"] != group["id"]]
        under = texts[0] if texts else None
    if under is not None and under["id"] != group["id"]:
        apply(project, {"type": "reorder", "target": group["id"], "below": under["id"]})


def _backdrop(project, group, op):
    """Move a new top-level group to just above the backdrop: the run of full-width layers covering at least a
    quarter of the canvas height at the bottom of the stack (sky, sea, a background solid)."""
    from ...operations import execute as apply
    from ...render import resolve_layout

    if "below" in op:
        return _settle(project, group, op)
    bounds = resolve_layout(project)
    cw, ch = _canvas(project)
    anchor = None
    for layer in project.state["layers"]:
        if layer.get("parent") or layer["id"] == group["id"]:
            continue
        x, y, w, h = bounds[layer["id"]]
        if layer["type"] in TEXT_TYPES or w < 0.95 * cw or h < 0.25 * ch:
            break
        anchor = layer
    if anchor is not None:
        apply(project, {"type": "reorder", "target": group["id"], "above": anchor["id"]})
    else:
        apply(project, {"type": "bottom", "target": group["id"]})


def _group(project, op, ids, default):
    from ...operations import default_name, execute as apply, unique_name

    require(ids, "Nothing was drawn", field="region")
    name = unique_name(project, op["name"]) if op.get("name") else default_name(project, default)
    apply(project, {"type": "group", "name": name, "targets": ids})
    return project.layer(name)


def _budget(project, needed):
    require(len(project.state["layers"]) + needed + 1 <= project.limits.max_layers,
            "The effect would exceed the layer budget; lower count", "resource_limit", field="count")


def _alpha(value, alpha):
    """``value`` as an 8-digit hex colour with ``alpha`` (0-1) applied to its own alpha."""
    from ...render import color

    r, g, b, a = color(value)
    return f"#{r:02x}{g:02x}{b:02x}{max(0, min(255, round(a * alpha))):02x}"


def _radial(project, name, cx, cy, w, h, stops, falloff="linear"):
    from ...operations import execute as apply

    apply(project, {"type": "gradient", "name": name, "x": cx - w / 2, "y": cy - h / 2, "width": max(1.0, w),
                    "height": max(1.0, h), "direction": "radial", "falloff": falloff, "stops": stops})
    return project.layer()


def _shape(project, **spec):
    from ...operations import execute as apply

    apply(project, {"type": "shape", "stroke_width": 0, **spec})
    return project.layer()


def _fill_of(project, layer, default):
    from ...design import resolve_color
    from ...render import color

    fill = layer.get("fill") if layer["type"] == "shape" else layer.get("color") if layer["type"] == "solid" else None
    if isinstance(fill, str) and fill.strip().lower() not in ("transparent", "none", ""):
        try:
            if color(resolve_color(fill, project.state))[3] > 0:
                return fill
        except VixlError:
            pass
    return default


def _resolved(project, value):
    from ...design import resolve_color
    from ...render import color

    resolved = resolve_color(value, project.state)
    color(resolved)
    return resolved


# ---------------------------------------------------------------------------------------------------------------
# haze


def haze(project, op):
    from ...operations import default_name

    form = op.get("form", "band")
    require(form in ("band", "round", "fog"), "form is band, round or fog", field="form")
    if form == "fog":
        return fog(project, op)
    stray = [key for key in ("layers", "density", "behind") if key in op]
    require(not stray, f"{', '.join(stray)} only apply to form fog; band and round take strength",
            field=stray[0] if stray else None)
    source = project.layer(op["target"]) if op.get("target") else None
    cw, ch = _canvas(project)
    if source is not None:
        x0, y0, x1, y1 = _boxes(project, [source])[0]
        cx, cy, width = (x0 + x1) / 2, (y0 + y1) / 2, max(6 * (x1 - x0), 0.15 * cw)
    else:
        require("x" in op and "y" in op, "haze needs a target (the light source) or x and y", field="target")
        cx, cy, width = finite(op["x"], "x"), finite(op["y"], "y"), cw * 0.6
    width = finite(op.get("width", width), "width", 1, 1e6)
    height = finite(op.get("height", width * (0.45 if form == "band" else 1)), "height", 1, 1e6)
    strength = finite(op.get("strength", 0.45), "strength", 0, 1)
    tone = _resolved(project, op.get("color") or (_fill_of(project, source, "#ffd38a") if source else "#ffd38a"))
    name = op.get("name") or default_name(project, "haze")
    ids = []
    outer = _radial(project, f"{name}/band", cx, cy, width, height,
                    [{"offset": 0, "color": _alpha(tone, strength)}, {"offset": 1, "color": _alpha(tone, 0)}],
                    "gaussian")
    ids.append(outer["id"])
    core = min(width, height) * (0.55 if form == "band" else 0.45)
    inner = _radial(project, f"{name}/core", cx, cy, core, core,
                    [{"offset": 0, "color": _alpha(tone, min(1.0, strength * 1.4))},
                     {"offset": 1, "color": _alpha(tone, 0)}], "gaussian")
    ids.append(inner["id"])
    group = _group(project, {**op, "name": name}, ids, "haze")
    _settle(project, group, op, under=_top(project, source) if source is not None else None)
    return {"group": group["id"], "center": [round(cx, 2), round(cy, 2)], "width": width, "height": height}


def _fog_tone(tone, depth):
    """The fog colour ``depth`` of the way from the horizon (0) to the nearest band (1): lighter and less
    saturated toward the horizon, as distance washes colour out."""
    from ...colors import hex_of, hsl_to_srgb, parse, srgb_to_hsl

    r, g, b, a = parse(tone)
    hue, saturation, light = srgb_to_hsl((r, g, b))
    far = 1 - depth
    return hex_of((*hsl_to_srgb(hue, saturation * (1 - 0.65 * far), light + (1 - light) * 0.5 * far), a))


def fog(project, op):
    """Stacked soft horizontal bands, the farthest (highest, lightest, densest) first. Each band is a few wide
    overlapping gaussian gradients at seeded positions, so the fog drifts instead of lying in a ruled stripe."""
    from ...operations import default_name

    rng = _rng(op)
    cw, ch = _canvas(project)
    count = op.get("layers", 3)
    require(isinstance(count, int) and not isinstance(count, bool) and FOG_LAYERS[0] <= count <= FOG_LAYERS[1],
            f"layers must be {FOG_LAYERS[0]}-{FOG_LAYERS[1]}", field="layers")
    density = finite(op.get("density", 0.5), "density", 0, 1)
    if op.get("target"):
        x0, y0, x1, y1 = _boxes(project, [project.layer(op["target"])])[0]
        cx, cy, width, height = (x0 + x1) / 2, (y0 + y1) / 2, max(1.0, x1 - x0), max(1.0, y1 - y0)
    else:
        cx, cy, width, height = cw / 2, ch * 0.6, cw * 1.1, ch * 0.3
    cx, cy = finite(op.get("x", cx), "x"), finite(op.get("y", cy), "y")
    width, height = finite(op.get("width", width), "width", 1, 1e6), finite(op.get("height", height), "height", 1, 1e6)
    tone = _resolved(project, op.get("color", FOG_COLOR))
    behind = None
    if "behind" in op:
        require("below" not in op, "Give behind or below, not both", field="behind")
        refs = op["behind"]
        require(isinstance(refs, list) and refs, "behind lists the foreground layers the fog sits behind",
                field="behind")
        order = {layer["id"]: index for index, layer in enumerate(project.state["layers"])}
        behind = min((_top(project, project.layer(ref)) for ref in refs), key=lambda layer: order[layer["id"]])
    puffs = 3
    _budget(project, count * (puffs + 1))
    name = op.get("name") or default_name(project, "fog")
    step = height / count
    top = cy - height / 2
    ids, bands = [], []
    for index in range(count):
        depth = index / (count - 1)
        band_tone = _fog_tone(tone, depth)
        # The farthest band is the densest, as haze is at the horizon, and the near ones are taller (perspective).
        alpha = min(0.9, density * 1.1 * (1 - 0.5 * depth))
        band_y = top + (index + 0.5) * step
        for part in range(puffs):
            px = cx - width / 2 + (part + 0.5 + float(rng.uniform(-0.3, 0.3))) * width / puffs
            pw = width * float(rng.uniform(0.55, 0.85))
            ph = step * (2.2 + 0.8 * depth) * float(rng.uniform(0.85, 1.15))
            py = band_y + step * float(rng.uniform(-0.15, 0.15))
            disc = _radial(project, f"{name}/band-{index + 1}/puff-{part + 1}", px, py, pw, ph,
                           [{"offset": 0, "color": _alpha(band_tone, alpha * float(rng.uniform(0.75, 1.0)))},
                            {"offset": 1, "color": _alpha(band_tone, 0)}], "gaussian")
            ids.append(disc["id"])
        bands.append({"band": index + 1, "y": round(band_y, 2), "color": band_tone, "opacity": round(alpha, 3)})
    group = _group(project, {**op, "name": name}, ids, "fog")
    # Fog runs on past the canvas edges, as a sky does: not a crop to report.
    group["allow_crop"] = True
    _settle(project, group, op, under=behind)
    note(project, f"haze fog: {count} bands in {group['name']!r}"
                  + (f" behind {behind['name']!r}" if behind is not None else ""))
    return {"group": group["id"], "form": "fog", "bands": bands, "center": [round(cx, 2), round(cy, 2)],
            "width": round(width, 2), "height": round(height, 2)}


# ---------------------------------------------------------------------------------------------------------------
# star-field


def star_field(project, op):
    from ...scatter import _poisson

    rng = _rng(op)
    x, y, w, h = _region(project, op)
    cw, ch = _canvas(project)
    short = min(cw, ch)
    count = op.get("count", int(max(12, min(MAX_STARS, 260 * (w * h) / (1080 * 1080)))))
    require(isinstance(count, int) and 1 <= count <= MAX_STARS, f"count must be 1-{MAX_STARS}", field="count")
    small, large = _span(op, "size", [max(0.6, short * 0.0012), max(1.2, short * 0.0045)], 0.2, 200)
    dim, bright = _span(op, "opacity", [0.35, 1.0], 0, 1)
    fade = finite(op.get("fade", 0.5), "fade", 0, 1)
    sparkles = op.get("sparkles", count // 25)
    require(isinstance(sparkles, int) and 0 <= sparkles <= min(60, count), "sparkles must be 0-60 and at most count",
            field="sparkles")
    clearance = finite(op.get("clearance", short * 0.025), "clearance", 0, 1e5)
    tone = _resolved(project, op.get("color", "#fff6e0"))
    blocked = [(b[0] - clearance, b[1] - clearance, b[2] + clearance, b[3] + clearance)
               for b in _boxes(project, _avoided(project, op, True))]
    _budget(project, count)

    def clear(px, py, reach):
        return all(not (b[0] - reach <= px <= b[2] + reach and b[1] - reach <= py <= b[3] + reach) for b in blocked)

    # Poisson-disc spacing keeps stars from clumping; sample more than needed, then thin by the fade and drop
    # anything inside an avoided box (with its own radius as extra margin, so no star touches the copy).
    chosen = []
    for share in (0.3, 0.1):
        spacing = max(1.0, math.sqrt(share * w * h / count))
        candidates = _poisson(rng, lambda px, py: x <= px <= x + w and y <= py <= y + h, (x, y, x + w, y + h),
                              spacing, count * 4)
        radii = small + (large - small) * rng.random(len(candidates)) ** 3
        keep = rng.random(len(candidates))
        chosen = []
        for i in rng.permutation(len(candidates)):
            px, py = candidates[i]
            if keep[i] > 1 - fade * (py - y) / h or not clear(px, py, radii[i]):
                continue
            chosen.append((px, py, float(radii[i])))
            if len(chosen) == count:
                break
        if len(chosen) == count:
            break
    require(chosen, "The avoided layers cover the whole region; give a region or a smaller clearance",
            field="avoid")
    # The largest stars become the sparkles, where a sparkle's longer arms still keep clear of the copy.
    chosen.sort(key=lambda s: -s[2])
    flagged = []
    for px, py, r in chosen:
        flagged.append((px, py, r, sum(1 for f in flagged if f[3]) < sparkles and clear(px, py, r * 3.5)))
    ids = []
    name = op.get("name") or "stars"
    for index, (px, py, r, sparkle) in enumerate(flagged):
        level = (r - small) / max(large - small, 1e-6)
        alpha = dim + (bright - dim) * min(1.0, 0.25 + 0.75 * level + 0.25 * float(rng.random()))
        if sparkle:
            size = r * 7
            layer = _shape(project, shape="sparkle", name=f"{name}/sparkle-{index + 1}", x=px - size / 2,
                           y=py - size / 2, width=size, height=size, fill=tone, inner_radius=0.18)
        else:
            layer = _shape(project, shape="ellipse", name=f"{name}/star-{index + 1}", x=px - r, y=py - r,
                           width=2 * r, height=2 * r, fill=tone)
        layer["opacity"] = round(min(1.0, alpha), 3)
        ids.append(layer["id"])
    group = _group(project, op, ids, "stars")
    # A star on the region's edge belongs to a sky that runs on past it: not a crop to report.
    group["allow_crop"] = True
    _backdrop(project, group, op)
    note(project, f"star-field: {len(ids)} stars in {group['name']!r}, clear of {len(blocked)} avoided layer(s)")
    return {"group": group["id"], "stars": len(ids), "avoided": len(blocked)}


# ---------------------------------------------------------------------------------------------------------------
# string-lights


def _wire_points(project, op):
    """The wire as a dense canvas polyline, plus pen nodes when the operation draws the wire itself."""
    from ...geometry import bezier_points

    if op.get("target"):
        from ...scatter import outline

        layer = project.layer(op["target"])
        subs = [p for p, _ in outline(project, layer) if len(p) >= 2]
        require(subs, f"{layer['name']!r} has no path to hang lights along", field="target")
        return max(subs, key=len), None
    require("from" in op and "to" in op, "string-lights needs a target path or from and to", field="from")
    a = np.array([finite(v, "from") for v in op["from"]])
    b = np.array([finite(v, "to") for v in op["to"]])
    span = float(np.hypot(*(b - a)))
    require(span > 1, "from and to must be apart", field="to")
    sag = finite(op.get("sag", span * 0.12), "sag", -1e5, 1e5)
    # A quadratic whose midpoint dips by sag has its control point 2 x sag below the chord's middle.
    control = (a + b) / 2 + np.array([0, 2 * sag])
    c1, c2 = a + 2 / 3 * (control - a), b + 2 / 3 * (control - b)
    points = bezier_points([a, c1, c2, b], np.linspace(0, 1, 256))
    nodes = [{"point": [float(a[0]), float(a[1])], "out": [float(c1[0]), float(c1[1])]},
             {"point": [float(b[0]), float(b[1])], "in": [float(c2[0]), float(c2[1])]}]
    return points, nodes


def _bulb(project, kind, name, cx, top, size, tone):
    """One bulb hanging from (cx, top): its layers back to front."""
    from ...colors import parse

    r, g, b = (round(c * 255) for c in parse(tone)[:3])
    cap_tone = f"#{int(r * 0.25):02x}{int(g * 0.22):02x}{int(b * 0.2):02x}"
    layers = []
    if kind == "lantern":
        body_w, body_h = size, size * 1.2
        cap_w, cap_h = size * 0.46, max(1.0, size * 0.1)
        layers.append(_shape(project, shape="rounded-rectangle", name=f"{name}/cap", x=cx - cap_w / 2, y=top,
                             width=cap_w, height=cap_h, radius=cap_h * 0.3, fill=cap_tone))
        body_top = top + cap_h * 0.7
        layers.append(_shape(project, shape="ellipse", name=f"{name}/body", x=cx - body_w / 2, y=body_top,
                             width=body_w, height=body_h, fill=tone))
        layers.append(_shape(project, shape="ellipse", name=f"{name}/rib", x=cx - body_w * 0.27, y=body_top,
                             width=body_w * 0.54, height=body_h, fill="transparent", stroke=cap_tone,
                             stroke_width=max(1.0, size * 0.025), opacity=0.4))
        layers.append(_shape(project, shape="rounded-rectangle", name=f"{name}/base", x=cx - cap_w / 2,
                             y=body_top + body_h - cap_h * 0.4, width=cap_w, height=cap_h, radius=cap_h * 0.3,
                             fill=cap_tone))
        centre = body_top + body_h / 2
    else:
        body_w, body_h = (size, size) if kind == "globe" else (size * 0.78, size * 1.15)
        cap_w, cap_h = size * 0.34, max(1.0, size * 0.22)
        layers.append(_shape(project, shape="rounded-rectangle", name=f"{name}/cap", x=cx - cap_w / 2, y=top,
                             width=cap_w, height=cap_h, radius=cap_h * 0.25, fill=cap_tone))
        body_top = top + cap_h * 0.8
        layers.append(_shape(project, shape="ellipse", name=f"{name}/body", x=cx - body_w / 2, y=body_top,
                             width=body_w, height=body_h, fill=tone))
        centre = body_top + body_h / 2
    # A lit core reads as light, where a flat disc reads as a dot.
    core = body_w * 0.62
    layers.append(_radial(project, f"{name}/core", cx, centre, core, core * (body_h / body_w),
                          [{"offset": 0, "color": "#fff8e6d9"}, {"offset": 1, "color": "#fff8e600"}], "smooth"))
    return layers, centre


def string_lights(project, op):
    from ...operations import default_name, execute as apply

    rng = _rng(op)
    cw, ch = _canvas(project)
    points, nodes = _wire_points(project, op)
    seg = np.hypot(*np.diff(points, axis=0).T)
    arc = np.concatenate([[0], np.cumsum(seg)])
    total = float(arc[-1])
    require(total > 1, "The wire is too short", field="target")
    size = finite(op.get("size", min(cw, ch) * 0.024), "size", 1, 1e4)
    kind = op.get("bulb", "globe")
    require(kind in BULBS, f"bulb must be one of {', '.join(BULBS)}", field="bulb", allowed=list(BULBS))
    if "count" in op:
        count = op["count"]
        require(isinstance(count, int) and 1 <= count <= MAX_BULBS, f"count must be 1-{MAX_BULBS}", field="count")
    else:
        spacing = finite(op.get("spacing", size * 4), "spacing", 1, 1e6)
        count = max(1, min(MAX_BULBS, int(round(total / spacing))))
    colors = [_resolved(project, c) for c in op.get("colors", ["#ffd77a"])]
    glow = finite(op.get("glow", 0.6), "glow", 0, 1)
    hang = finite(op.get("hang", size * 0.5), "hang", 0, 1e5)
    jitter = finite(op.get("jitter", 0.25), "jitter", 0, 1)
    wire = _resolved(project, op.get("wire", "#2b2620"))
    wire_width = finite(op.get("wire_width", max(1.5, size * 0.08)), "wire_width", 0.1, 1e3)
    _budget(project, count * 7 + 1)
    name = op.get("name") or default_name(project, "string-lights")
    ids = []
    if nodes is not None:
        apply(project, {"type": "pen", "name": f"{name}/wire", "nodes": nodes, "fill": "transparent",
                        "stroke": wire, "stroke_width": wire_width, "line_cap": "round"})
        ids.append(project.layer()["id"])
    bulbs = []
    for index in range(count):
        station = (index + 0.5) * total / count
        px, py = float(np.interp(station, arc, points[:, 0])), float(np.interp(station, arc, points[:, 1]))
        drop = hang * (1 + jitter * 0.5 * float(rng.uniform(-1, 1)))
        tone = colors[index % len(colors)]
        label = f"{name}/bulb-{index + 1}"
        made = []
        if drop > 0.5:
            made.append(_shape(project, shape="line", name=f"{label}/hanger", x=px - 1, y=py, width=2,
                               height=max(1.0, drop), stroke=wire, stroke_width=max(1.0, wire_width * 0.7)))
        parts, centre = _bulb(project, kind, label, px, py + drop, size, tone)
        if glow > 0:
            reach = size * (2 + 3 * glow)
            halo = _radial(project, f"{label}/glow", px, centre, reach, reach,
                           [{"offset": 0, "color": _alpha(tone, 0.25 + 0.4 * glow)},
                            {"offset": 1, "color": _alpha(tone, 0)}], "gaussian")
            made.insert(0, halo)
        made.extend(parts)
        ids.extend(layer["id"] for layer in made)
        bulbs.append({"wire": [round(px, 2), round(py, 2)], "center": [round(px, 2), round(centre, 2)]})
    group = _group(project, {**op, "name": name}, ids, "string-lights")
    if op.get("target") and "below" not in op:
        apply(project, {"type": "reorder", "target": group["id"], "above": _top(project, project.layer(op["target"]))["id"]})
    else:
        _settle(project, group, op)
    note(project, f"string-lights: {count} bulbs along {round(total)} px of wire in {group['name']!r}")
    return {"group": group["id"], "bulbs": bulbs, "length": round(total, 2)}


# ---------------------------------------------------------------------------------------------------------------
# bokeh


def bokeh(project, op):
    from ...operations import execute as apply

    rng = _rng(op)
    x, y, w, h = _region(project, op)
    cw, ch = _canvas(project)
    short = min(cw, ch)
    count = op.get("count", 14)
    require(isinstance(count, int) and 1 <= count <= MAX_DISCS, f"count must be 1-{MAX_DISCS}", field="count")
    small, large = _span(op, "size", [short * 0.04, short * 0.12], 1, 1e5)
    faint, strong = _span(op, "opacity", [0.2, 0.55], 0, 1)
    softness = finite(op.get("softness", 0.3), "softness", 0, 1)
    blend = op.get("blend", "screen")
    require(blend in ("normal", "screen", "add", "lighten"), "blend is normal, screen, add or lighten", field="blend")
    colors = [_resolved(project, c) for c in op.get("colors", ["#ffd38a", "#ffb36b", "#fff1c9"])]
    blocked = _boxes(project, _avoided(project, op, False))
    _budget(project, count)
    ids = []
    name = op.get("name") or "bokeh"
    tries = 0
    while len(ids) < count and tries < count * 40:
        tries += 1
        d = small + (large - small) * float(rng.random()) ** 1.6
        cx, cy = x + float(rng.random()) * w, y + float(rng.random()) * h
        r = d / 2
        if any(b[0] - r <= cx <= b[2] + r and b[1] - r <= cy <= b[3] + r for b in blocked):
            continue
        tone = colors[len(ids) % len(colors)]
        alpha = faint + (strong - faint) * float(rng.random())
        # A real out-of-focus highlight is an even disc with a slightly brighter rim and a soft edge.
        edge = 1 - 0.6 * softness
        stops = [{"offset": 0, "color": _alpha(tone, alpha * 0.8)},
                 {"offset": round(edge * 0.9, 4), "color": _alpha(tone, alpha)},
                 {"offset": round(edge, 4), "color": _alpha(tone, alpha * 0.9)},
                 {"offset": 1, "color": _alpha(tone, 0)}]
        disc = _radial(project, f"{name}/disc-{len(ids) + 1}", cx, cy, d, d, stops)
        if blend != "normal":
            apply(project, {"type": "blend", "target": disc["id"], "value": blend})
        ids.append(disc["id"])
    require(ids, "The avoided layers leave no room for the discs", field="avoid")
    group = _group(project, op, ids, "bokeh")
    _backdrop(project, group, op)
    note(project, f"bokeh: {len(ids)} discs in {group['name']!r}")
    return {"group": group["id"], "discs": len(ids)}


# ---------------------------------------------------------------------------------------------------------------
# reflection


def _sources(project, settings, exclude):
    """The layers to mirror: the named ones, or every visible top-level layer above the horizon."""
    horizon = settings["horizon"]
    if settings.get("targets"):
        picked = [project.layer(ref) for ref in settings["targets"]]
        require(len({layer.get("parent") for layer in picked}) == 1,
                "Reflection targets must share a parent; group them first", field="targets")
        return picked
    from ...render import resolve_layout

    bounds = resolve_layout(project)
    cw, ch = _canvas(project)
    tolerance = max(8.0, ch * 0.01)
    picked = []
    for layer in project.state["layers"]:
        if layer.get("parent") or not layer.get("visible", True) or layer["id"] in exclude:
            continue
        if layer["type"] in TEXT_TYPES or layer["type"] == "adjustment":
            continue
        lx, ly, lw, lh = bounds[layer["id"]]
        # A background (most of the canvas) or anything reaching well below the waterline is the water or the
        # sky behind everything, not something standing above the water.
        if lw * lh >= 0.8 * cw * ch or ly + lh > horizon + tolerance or ly >= horizon:
            continue
        picked.append(layer)
    require(picked, "Nothing lies above the horizon to reflect; pass targets", field="targets")
    return picked


def _mirror(image, horizon_depth, settings, rng):
    """Flip, squash, ripple, band and fade an RGBA tile whose bottom row touches the waterline."""
    from PIL import Image

    rgba = np.asarray(image, dtype=np.float32) / 255
    rgba = rgba[::-1]  # the row just above the waterline becomes the first row below it
    alpha = rgba[:, :, 3:4]
    premul = np.concatenate([rgba[:, :, :3] * alpha, alpha], axis=2)
    squash = settings["squash"]
    rows = max(1, min(horizon_depth, int(round(premul.shape[0] * squash))))
    source_rows = np.clip((np.arange(rows) + 0.5) / squash - 0.5, 0, premul.shape[0] - 1)
    low = np.floor(source_rows).astype(int)
    high = np.minimum(low + 1, premul.shape[0] - 1)
    t = (source_rows - low)[:, None, None]
    out = premul[low] * (1 - t) + premul[high] * t
    height, width = out.shape[:2]
    depth = (np.arange(height) + 0.5) / height
    # Ripples: each row slides sideways by a sum of seeded sines whose amplitude and wavelength grow toward
    # the viewer (perspective), so near water breaks up more than water at the horizon.
    amplitude = settings["ripple"] * max(width, height) * 0.025 * (0.25 + depth)
    wavelength = np.maximum(3.0, height * 0.035 * (0.4 + 1.6 * depth))
    phase = np.cumsum(1 / wavelength) * math.tau
    offsets = amplitude * (np.sin(phase + rng.uniform(0, math.tau))
                           + 0.5 * np.sin(phase * 2.3 + rng.uniform(0, math.tau))
                           + 0.35 * rng.standard_normal(height)) / 1.5
    columns = np.arange(width)[None, :] - offsets[:, None]
    left = np.clip(np.floor(columns).astype(int), 0, width - 1)
    right = np.clip(left + 1, 0, width - 1)
    frac = (columns - np.floor(columns))[:, :, None]
    row_index = np.arange(height)[:, None]
    out = out[row_index, left] * (1 - frac) + out[row_index, right] * frac
    blur = settings["blur"]
    if blur >= 1:
        k = int(round(blur))
        padded = np.pad(out, ((k, k), (0, 0), (0, 0)), mode="edge")
        summed = np.cumsum(padded, axis=0)
        summed = np.concatenate([np.zeros_like(summed[:1]), summed], axis=0)
        out = (summed[2 * k + 1:] - summed[:-2 * k - 1]) / (2 * k + 1)
    band = 0.5 + 0.5 * np.sin(phase * 0.5 + rng.uniform(0, math.tau))
    weight = 1 - settings["breakup"] * np.clip((band - 0.35) / 0.65, 0, 1) ** 1.5
    fade = (1 - depth) ** (0.5 + 2.5 * settings["fade"])
    out = out * (settings["opacity"] * weight * fade)[:, None, None]
    a = out[:, :, 3:4]
    rgb = np.where(a > 1e-6, out[:, :, :3] / np.maximum(a, 1e-6), 0)
    if settings.get("tint"):
        from ...render import color

        tint = np.array(color(settings["tint"])[:3], dtype=np.float32) / 255
        rgb = rgb * (1 - settings["tint_amount"]) + tint * settings["tint_amount"]
    pixels = np.clip(np.concatenate([rgb, a], axis=2) * 255 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, "RGBA")


def reflection(project, op):
    from ...assets import add_image
    from ...model import new_layer
    from ...operations import append_layer, default_name, execute as apply, unique_name
    from ...render import render_members, resolve_layout

    existing = project.layer(op["target"]) if op.get("target") else None
    if existing is not None:
        require(existing.get("reflection"), f"{existing['name']!r} was not made by reflection; target a reflection "
                "layer or leave target out", field="target")
        settings = deepcopy(existing["reflection"])
    else:
        settings = {}
    for key in REFLECTION_KEYS:
        if key in op:
            settings[key] = deepcopy(op[key])
    require("horizon" in settings, "reflection needs horizon (the waterline y in canvas pixels)", field="horizon")
    cw, ch = _canvas(project)
    horizon = finite(settings["horizon"], "horizon", 1, ch - 1)
    settings["horizon"] = horizon
    for key, default, low, high in (("squash", 0.8, 0.2, 1.5), ("ripple", 0.35, 0, 1), ("breakup", 0.4, 0, 1),
                                    ("fade", 0.6, 0, 1), ("opacity", 0.7, 0, 1),
                                    ("blur", round(ch * 0.003, 2), 0, 200)):
        settings[key] = finite(settings.get(key, default), key, low, high)
    if settings.get("tint"):
        settings["tint"] = _resolved(project, settings["tint"])
        settings["tint_amount"] = finite(settings.get("tint_amount", 0.25), "tint_amount", 0, 1)
    seed = settings.get("seed", 0)
    rng = _rng({"seed": seed})
    exclude = {existing["id"]} if existing is not None else set()
    if existing is not None:
        # Re-rendering looks only at what lies below the reflection in the stack, so text and later decoration
        # added on top never fall into the water.
        position = project.state["layers"].index(existing)
        exclude |= {layer["id"] for layer in project.state["layers"][position:]}
    sources = _sources(project, settings, exclude)
    bounds = resolve_layout(project)
    below_water = int(math.floor(ch - horizon))
    reach = min(horizon, below_water / settings["squash"] + 2)
    top = int(math.floor(horizon - reach))
    image, (left, tile_top) = render_members(project, [layer["id"] for layer in sources],
                                             (0, top, int(cw), int(math.ceil(horizon)) - top))
    mirrored = _mirror(image, below_water, settings, rng)
    box = mirrored.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
    require(box, "The layers above the horizon draw nothing to reflect", field="targets")
    mirrored = mirrored.crop(box)
    x, y = left + box[0], int(math.ceil(horizon)) + box[1]
    stored = {k: deepcopy(v) for k, v in settings.items() if k in REFLECTION_KEYS}
    if existing is not None:
        existing.update(asset=add_image(project, mirrored), width=mirrored.width, height=mirrored.height, x=x, y=y,
                        reflection=stored)
        note(project, f"reflection: re-rendered {existing['name']!r} from {_listed(sources)}")
        return {"layer": existing["id"], "sources": [layer["name"] for layer in sources]}
    name = unique_name(project, op["name"]) if op.get("name") else default_name(project, "reflection")
    layer = new_layer(name, "raster", mirrored.width, mirrored.height, x=x, y=y, asset=add_image(project, mirrored),
                      reflection=stored, provenance={"type": "reflection"})
    append_layer(project, layer)
    # Sit above the mirrored layers and the water they fall into, and below any copy above those.
    layers = project.state["layers"]
    ids = {item["id"] for item in sources}
    water = {item["id"] for item in layers
             if not item.get("parent") and item["type"] not in TEXT_TYPES and item["id"] != layer["id"]
             and _overlaps(bounds.get(item["id"]), (x, y, mirrored.width, mirrored.height))}
    anchors = [item for item in layers if item["id"] in ids | water]
    if anchors and layers.index(anchors[-1]) < len(layers) - 2:
        apply(project, {"type": "reorder", "target": layer["id"], "above": anchors[-1]["id"]})
    note(project, f"reflection: {layer['name']!r} mirrors {_listed(sources)} below y={compact_number(horizon, 2)}; "
                  f"after changing them, run {{type: reflection, target: {layer['name']!r}}} to re-render it")
    return {"layer": layer["id"], "sources": [item["name"] for item in sources]}


def _listed(layers):
    names = [repr(layer["name"]) for layer in layers]
    return ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")


def _overlaps(a, b):
    if a is None:
        return False
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def execute(project, op):
    kind = op["type"]
    if kind == "reflection":
        return reflection(project, op)
    if kind == "haze":
        return haze(project, op)
    if kind == "star-field":
        return star_field(project, op)
    if kind == "string-lights":
        return string_lights(project, op)
    return bokeh(project, op)
