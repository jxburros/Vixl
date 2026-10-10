"""Discoverable JSON Schema for the public structured operation format."""

from copy import deepcopy
from functools import lru_cache

from .geometry import ANCHORS
from .inplace import EDITS, target_schema
from .model import Limits
from .render import EFFECTS, BLENDS

S = {"type": "string"}
N = {"type": "number"}
POSITIVE_INT = {"type": "integer", "minimum": 1}
B = {"type": "boolean"}
TARGET = {"type": "string", "description": "Stable layer ID or unique name; omitted means active layer."}
COORD = {
    "anyOf": [N, {"type": "string", "pattern": r"^(center|-?\d+(\.\d+)?%)$"}],
    "description": "Pixels, 'center', or a percentage of the canvas/parent such as '50%'.",
}
SIZE = {
    "anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "string", "pattern": r"^\d+(\.\d+)?%$"}],
    "description": "Pixels or a percentage of the canvas/parent such as '25%'.",
}
COORD_FIELDS = ("x", "y", "width", "height")
OPACITY = {
    "type": "number", "minimum": 0, "maximum": 1,
    "description": "0 (clear) to 1 (opaque); a percentage string such as '70%' is read as 0.7. A bare number above "
    "1 is an error.",
}
# Layer-creating operations that also set the layer's opacity and rotation (the opacity and rotate
# operations, in one step); with target they change the edited layer's.
LAYER_FINISH = ("add", "solid", "gradient", "text", "shape")
FINISH_FIELDS = {
    "opacity": OPACITY,
    "rotation": {"type": "number", "description": "Rotation in degrees, clockwise, around the layer's pivot "
                 "(its center unless pivot moved it), as the rotate operation sets it."},
}
FONT = {
    "type": "string",
    "description": "Registered font name or role (heading, body); install with font install / font pair / font import. "
    "File paths work only in the CLI and Python API, not over MCP or REST. A new text layer without one uses the "
    "body face once the document has typography.",
}


def enum(*values):
    return {"enum": list(values)}


def field(base, description):
    """A copy of a shared schema constant carrying its own description (shared constants are never mutated)."""
    return {**base, "description": description}


def operation_schema():
    return deepcopy(_operation_schema())


@lru_cache(maxsize=1)
def _validators():
    from jsonschema import Draft202012Validator

    variants = _operation_schema()["properties"]["operations"]["items"]["oneOf"]
    return {s["properties"]["type"]["const"]: Draft202012Validator(s) for s in variants}


@lru_cache(maxsize=1)
def _operation_schema():
    variants = []

    def add(kind, properties=None, required=(), **extra):
        variants.append(
            {
                "type": "object",
                "properties": {"type": {"const": kind}, "target": TARGET, **(properties or {})},
                "required": ["type", *required],
                "additionalProperties": False,
                **extra,
            }
        )

    add(
        "add",
        {
            "path": S,
            "asset": S,
            "name": S,
            "linked": B,
            "x": COORD,
            "y": COORD,
            "provenance": {"type": "object"},
            "credit": {"type": "string", "maxLength": 1000},
            "license": {"type": "string", "maxLength": 1000},
            "width": SIZE,
            "height": SIZE,
            "max_pixels": {"type": "integer", "minimum": 1},
            "downsample": enum("placed@2x"),
        },
        anyOf=[{"required": ["path"]}, {"required": ["asset"]}],
    )
    add(
        "solid",
        {"target": target_schema("solid"), "name": S, "width": SIZE, "height": SIZE, "color": S, "x": COORD, "y": COORD},
    )
    add(
        "gradient",
        {
            "target": target_schema("gradient"),
            "name": S,
            "width": SIZE,
            "height": SIZE,
            "start": S,
            "end": S,
            "direction": enum("horizontal", "vertical", "radial", "angled"),
            "center": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1},
                       "minItems": 2, "maxItems": 2, "description": "Radial centre [x,y] as fractions of the layer; default [0.5,0.5]."},
            "stops": {"type": "array", "items": {"type": "object"}},
            "angle": N,
            "falloff": enum("linear", "smooth", "ease", "quadratic", "gaussian"),
            "x": COORD,
            "y": COORD,
        },
    )
    add("palette-define", {"name": S, "colors": {"type": "array", "items": S, "minItems": 2, "maxItems": 256}}, ["name", "colors"])
    from .palette_roles import role_schema

    add("palette-apply", {"name": S, "prefix": S, "roles": {"anyOf": [B, role_schema()]}, "keep_order": B,
                          "policy": enum("strict", "accessible")}, ["name"])
    add("template-apply", {"name": S, "variables": {"type": "object"}, "seed": {"type": ["integer", "string"]},
                           "palette": {"type": ["string", "array"], "items": S}, "look": {**S, "description": "Named finish for the template."}, "style": {**S, "description": "Named design style for the template."},
                           "mode": enum("light", "dark"), "columns": {"type": "integer", "minimum": 1, "maximum": 12}}, ["name"])
    add("guidance", {"name": S, "text": S, "style": S, "delete": B}, ["name"])
    add("font-register", {"name": S, "asset": S, "role": S}, ["name"])
    baseline_y = {"type": "number", "description": "Place the text's first baseline at this y (instead of y, the top "
                  "of its box), in the same coordinates as y. Multi-line text: the first line; mixed fonts: the measured "
                  "first line."}
    text = {
        "text": S,
        "size": POSITIVE_INT,
        "color": S,
        "align": enum("left", "center", "right"),
        "spacing": {"type": "integer", "minimum": -4096, "maximum": 1000},
        "line_height": {"type": "number", "minimum": 0.5, "maximum": 5,
                        "description": "Distance between baselines as a multiple of the size (1.45 body, 1.1 headings, "
                        "1.0 display). Kept when the size or font changes; spacing in pixels overrides it."},
        "hide_if_empty": {
            "type": "boolean",
            "description": "Do not draw the text (and take no space in a stack) while it is empty or blank "
            "after ${variable} substitution.",
        },
        "tracking": {"type": "number", "minimum": -1000, "maximum": 1000,
                     "description": "Letter spacing (tracking) in pixels added after every character, for the whole "
                     "layer: it applies to whatever text the layer holds, including text changed by keyframes and "
                     "${variable} values. Rich-text spans with their own tracking keep it. 0 removes it. Not line "
                     "spacing (that is spacing or line_height)."},
        "text_transform": {"enum": ["none", "uppercase", "lowercase", "capitalize"],
                           "description": "Draw the layer's text in this case without changing the stored text "
                           "(capitalize upper-cases the first letter of each word); applies to text changed by "
                           "keyframes and ${variable} values too. none removes it."},
    }
    add(
        "text",
        {
            **text,
            "target": target_schema("text"),
            "name": S,
            "font": FONT,
            "x": COORD,
            "y": COORD,
            "within": field(S, "A layer to centre the text in instead of x/y: the middle of its content box (a "
                            "speech bubble's body, a badge, a frame's opening; see content_bounds in inspect). "
                            "Use place with within for other anchors or a margin."),
            "baseline_y": baseline_y,
        },
        anyOf=[{"required": ["text"]}, {"required": ["target"]}],
    )
    add(
        "text-set",
        {
            **text,
            "text": {**S, "description": "New plain text for the whole layer. On rich text, lines and words are matched so "
                     "lists, spacing and span styles carry over where they still apply (the result's warnings list what "
                     "was dropped); use rich-text to rebuild formatted content."},
            "color": {**S, "description": "Layer text color. Spans of rich text that set their own color keep it; "
                      "use text-style to recolor those."},
            "font": FONT,
            "stroke_width": {"type": "integer", "minimum": 0},
            "stroke_color": S,
            "baseline_y": baseline_y,
        },
        description="Change a whole text layer: content, color, size, font, alignment, spacing or stroke. To style only "
        "part of the text (a phrase, a character range, a paragraph, bold/italic/tracking) use text-style.",
    )
    for kind in (
        "remove",
        "hide",
        "show",
        "raise",
        "lower",
        "top",
        "bottom",
        "select-layer",
        "rasterize",
        "unconstrain",
    ):
        add(kind)
    add("rename", {"name": S}, ["name"])
    add("duplicate", {"name": S})
    add("move", {"x": COORD, "y": COORD, "relative": B, "baseline_y": baseline_y},
        anyOf=[{"required": ["x"]}, {"required": ["y"]}, {"required": ["baseline_y"]}])
    add(
        "resize",
        {
            "width": SIZE,
            "height": SIZE,
            "keep_aspect": {
                "type": "boolean",
                "description": "With only width or only height: true scales the other side to keep the aspect "
                "ratio; false changes just the given side. Default: true for image (raster) layers, false for "
                "everything else.",
            },
        },
        anyOf=[{"required": ["width"]}, {"required": ["height"]}],
    )
    scale = {"type": "number", "description": "Size factor, 0.001-100 (0.8 = 80%). Negative values mirror the layer on that axis."}
    add("scale", {"value": {**scale, "description": "Size factor for both axes, 0.001-100 (0.8 = 80%). Negative mirrors both axes."},
                  "x": {**scale, "description": "Horizontal factor, overriding value. Negative mirrors horizontally, like flip."},
                  "y": {**scale, "description": "Vertical factor, overriding value. Negative mirrors vertically."}},
        anyOf=[{"required": ["value"]}, {"required": ["x"]}, {"required": ["y"]}])
    add("rotate", {"value": N, "about": {
        "anyOf": [{"type": "array", "items": N, "minItems": 2, "maxItems": 2}, enum("pivot", *ANCHORS)],
        "description": "The point that stays fixed: pivot (default; the layer's center when it has none), an anchor "
        "name such as top-left, or [x, y] fractions of the unrotated box. Another point than the pivot clears the "
        "layer's constraints."}}, ["value"])
    add("pivot", {"value": {"anyOf": [{"type": "array", "items": N, "minItems": 2, "maxItems": 2}, enum(*ANCHORS)],
                            "description": "[x, y] as fractions of the layer box (0.5, 0.5 is the center; pixels from the "
                            "top-left with units: px; a canvas point with units: canvas) or an anchor name: "
                            + ", ".join(ANCHORS) + ". Synonyms such as bottom-center or center-left are accepted."},
                  "units": enum("fraction", "px", "canvas"), "clear": B})
    add("opacity", {"value": OPACITY}, ["value"])
    add("blend", {"value": enum(*BLENDS)}, ["value"])
    add("flip", {"direction": enum("horizontal", "vertical")}, ["direction"])
    add(
        "crop", {"x": N, "y": N, "width": POSITIVE_INT, "height": POSITIVE_INT}, ["x", "y", "width", "height"]
    )
    add(
        "reorder",
        {"above": TARGET, "below": TARGET},
        oneOf=[{"required": ["above"]}, {"required": ["below"]}],
    )
    add(
        "align",
        {
            "alignment": enum(
                "center",
                "center-x",
                "center-y",
                "top",
                "bottom",
                "left",
                "right",
                "top-left",
                "top-right",
                "bottom-left",
                "bottom-right",
                "baseline",
            ),
            "margin": N,
            "relative_to": S,
            "box": field(enum("bounds", "content"),
                         "With relative_to a layer: bounds (default) aligns to its whole box; content aligns to its "
                         "usable inner area (a speech bubble's body, a badge's centre, a frame's opening, a device "
                         "screen), reported as content_bounds by inspect."),
            "targets": {"type": "array", "items": S, "minItems": 1, "uniqueItems": True},
        },
        ["alignment"],
    )
    add(
        "constrain",
        {
            "constraints": {
                "type": "object",
                "properties": {
                    key: {"type": ["string", "number"]}
                    for key in ("left", "right", "top", "bottom", "center-x", "center-y")
                },
                "additionalProperties": False,
            }
        },
        ["constraints"],
    )
    add(
        "canvas",
        {
            "width": POSITIVE_INT,
            "height": POSITIVE_INT,
            "background": S,
            "size": S,
            "preset": S,
            "dpi": {"type": "number", "minimum": 36, "maximum": 2400},
            "orientation": enum("portrait", "landscape"),
            "bleed": {"type": ["boolean", "number"]},
        },
    )
    add(
        "select",
        {
            "shape": enum("all", "none", "invert", "rect", "ellipse", "color", "alpha", "asset", "wand", "lasso", "path"),
            "x": COORD,
            "y": COORD,
            "width": SIZE,
            "height": SIZE,
            "color": S,
            "tolerance": N,
            "contiguous": B,
            "points": {"type": "array", "minItems": 3, "maxItems": 4096, "items": {"type": "array", "items": N, "minItems": 2, "maxItems": 2}},
            "path": S,
            "feather": N,
            "mode": enum("replace", "add", "subtract", "intersect"),
            "asset": S,
        },
        ["shape"],
    )
    add(
        "mask",
        {
            "action": enum("create", "from-selection", "import", "invert", "enable", "disable", "delete"),
            "path": S,
        },
    )
    effect = {
        "amount": N,
        "value": N,
        "seed": {"type": "integer", "minimum": 0},
        "radius": N,
        "strength": N,
        "shadow_color": S,
        "highlight_color": S,
        "black": N,
        "white": N,
        "luminance": {"type": "number", "minimum": 0, "maximum": 100,
                      "description": "denoise: luminance (grain) strength 0-100, relative to the noise measured in the image; default 50."},
        "chroma": {"type": "number", "minimum": 0, "maximum": 100,
                   "description": "denoise: colour-noise strength 0-100, smoothing blotches without bleeding across edges; default 50."},
        "search": {"type": "integer", "minimum": 1, "maximum": 10,
                   "description": "denoise: search window radius in pixels, default 5; render time grows with its square (about 1 s per megapixel at 5)."},
        "points": {
            "type": "array",
            "items": {"type": "array", "items": N, "minItems": 2, "maxItems": 2},
            "minItems": 2,
        },
        "gains": {"type": "array", "items": N, "minItems": 3, "maxItems": 3},
        "neutral": S,
    }
    add("effect", {"name": S, "lut": S, **effect}, ["name"])
    for kind in EFFECTS:
        add(kind, deepcopy(effect))
    ref = {"type": ["integer", "string"]}
    for kind in ("effect-disable", "effect-enable", "effect-remove", "effect-set"):
        add(
            kind,
            {"effect": ref, **({"lut": S, **effect} if kind == "effect-set" else {})},
            ["effect"],
        )
    add("effect-move", {"effect": ref, "to": ref, "before": ref, "after": ref}, ["effect"])
    add("variable", {"name": S, "value": {"type": ["string", "number", "boolean"]}, "delete": B}, ["name"])
    add("variable-map", {"name": S, "values": {"type": "object", "additionalProperties": {"type": ["string", "number", "boolean"]}},
                         "merge": B, "delete": B}, ["name"])
    add("preset-save", {"name": S}, ["name"])
    add(
        "preset-apply",
        {"name": S, "overrides": {"type": "object", "additionalProperties": {"type": ["string", "number"]}}},
        ["name"],
    )
    from .design_schema import schemas

    schemas(add)
    from .pixel_schema import schemas as pixel_schemas

    pixel_schemas(add)
    from .brushes import schemas as brush_schemas

    brush_schemas(add)
    from .timeline import schemas as timeline_schemas

    timeline_schemas(add)
    from .layouts import schemas as layout_schemas

    layout_schemas(add)
    from .automation import schemas as automation_schemas
    automation_schemas(add)
    from .creative import schemas as creative_schemas
    creative_schemas(add)
    from .emojis import schemas as emoji_schemas
    emoji_schemas(add)
    from .authoring import schemas as authoring_schemas
    authoring_schemas(add)
    from .containers import schemas as container_schemas
    container_schemas(add)
    from .stacks import schemas as stack_schemas
    stack_schemas(add)
    from .organic import schemas as organic_schemas
    organic_schemas(add)
    from .irregular import schemas as irregular_schemas
    irregular_schemas(add)
    from .guides import schemas as guide_schemas
    guide_schemas(add)
    from .richtext import schemas as rich_schemas
    rich_schemas(add)
    from .pages import schemas as page_schemas
    page_schemas(add)
    from .forms import schemas as form_schemas
    form_schemas(add)
    from .drawing import schemas as drawing_schemas
    drawing_schemas(add)
    from .selectors import schemas as selector_schemas
    selector_schemas(add)
    from .links import schemas as link_schemas
    link_schemas(add)
    from .codes import schemas as code_schemas
    code_schemas(add)
    from .charts import schemas as chart_schemas
    chart_schemas(add)
    from .finishing import schemas as finishing_schemas
    finishing_schemas(add)
    from .diagrams import schemas as diagram_schemas
    diagram_schemas(add)
    from .textflow import schemas as flow_schemas
    flow_schemas(add)
    add(
        "palette-generate",
        {"name": S, "color": S, "scheme": S, "count": {"type": "integer", "minimum": 2, "maximum": 12}},
        ["name", "color"],
    )
    from .scene import schemas as scene_schemas

    scene_schemas(add)
    from .captions import schemas as caption_schemas

    caption_schemas(add)
    from .merging import schemas as merge_schemas

    merge_schemas(add)
    from .vector_paths import schemas as vector_schemas

    vector_schemas(add)
    from .audio import schemas as audio_schemas

    audio_schemas(add)
    from .comics import schemas as comic_schemas
    from .textures import schemas as texture_schemas

    comic_schemas(add)
    texture_schemas(add)
    from .motion import schemas as motion_schemas
    from .characters import schemas as character_schemas

    motion_schemas(add)
    character_schemas(add)
    from .transforms import schemas as transform_schemas, enrich_transform_schemas

    transform_schemas(add)
    enrich_transform_schemas(variants)
    for variant in variants:
        if variant["properties"]["type"]["const"] in LAYER_FINISH:
            variant["properties"].update(deepcopy(FINISH_FIELDS))
        if variant["properties"]["type"]["const"] in EDITS:
            variant["properties"]["space"] = {
                "enum": ["parent", "canvas"],
                "description": "With target: how x/y read for a layer inside a group. parent (default): local to the "
                "group's box; canvas: document coordinates, as move's space: canvas.",
            }
    from .schema_docs import enrich
    from .targets import enrich as enrich_targets

    enrich(variants)
    enrich_targets(variants)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Vixl operation batch",
        "type": "object",
        "properties": {
            "operations": {"type": "array", "minItems": 1, "maxItems": Limits().max_operations, "items": {"oneOf": variants}}
        },
        "required": ["operations"],
        "additionalProperties": False,
    }


@lru_cache(maxsize=1)
def _properties():
    variants = _operation_schema()["properties"]["operations"]["items"]["oneOf"]
    return {v["properties"]["type"]["const"]: frozenset(v["properties"]) for v in variants}


@lru_cache(maxsize=1)
def _required():
    variants = _operation_schema()["properties"]["operations"]["items"]["oneOf"]
    return {v["properties"]["type"]["const"]: frozenset(v["required"]) for v in variants}


@lru_cache(maxsize=1)
def _integer_fields():
    """Top-level fields whose schema accepts integers but not other numbers, per operation type."""
    variants = _operation_schema()["properties"]["operations"]["items"]["oneOf"]

    def integer_only(spec):
        options = spec.get("anyOf") or spec.get("oneOf") or [spec]
        types = set()
        for option in options:
            kind = option.get("type")
            types.update(kind if isinstance(kind, list) else [kind])
        return "integer" in types and "number" not in types

    return {v["properties"]["type"]["const"]: frozenset(k for k, spec in v["properties"].items() if integer_only(spec))
            for v in variants}


def round_integers(op, notes, where):
    """Round fractional values given for integer fields (a computed 25.6 font size) and report it."""
    import math

    for key in _integer_fields().get(op.get("type"), ()):
        value = op.get(key)
        if isinstance(value, float) and math.isfinite(value):
            op[key] = round(value)
            if op[key] != value:
                notes.append(f"{where}: {key} {value!r} → {op[key]}")


def validate_operation(operation, notes=None, index=None):
    """Normalize common spellings, then validate before doing any I/O."""
    import json
    from .errors import VixlError, require
    from .normalize import normalize_operation

    require(isinstance(operation, dict), "Each operation must be an object")
    result = deepcopy(operation)
    kind = result.pop("operation", result.get("type"))
    result["type"] = kind
    # Any operation can name the page it edits; "page" operations use the field themselves.
    page = result.pop("page", None) if result["type"] != "page" else None
    if page is not None:
        require(isinstance(page, (str, int)) and not isinstance(page, bool), "page must be a page name or number",
                field="page")
    properties = _properties()
    result = normalize_operation(
        result, lambda k: properties.get(k, frozenset()), properties, EFFECTS, [] if notes is None else notes, index,
        required=lambda k: _required().get(k, frozenset()),
    )
    require(isinstance(result.get("type"), str), "Operation requires a string type", field="type")
    round_integers(result, [] if notes is None else notes, f"operations[{index}]" if index is not None else "operation")
    validator = _validators().get(result["type"])
    if validator is None:
        import difflib

        close = difflib.get_close_matches(result["type"], list(properties), 3, 0.5)
        raise VixlError(
            "unknown_operation",
            f"Unknown operation type {result['type']!r}"
            + (f"; did you mean {' or '.join(map(repr, close))}?" if close else "; see the operation schema")
            + " Fields of any type: vixl_operation_schema(types=[...])",
            field="type",
            suggestions=close,
        )
    from jsonschema.exceptions import best_match

    error = best_match(validator.iter_errors(result))
    if error is not None:
        raise schema_error(error, result, properties[result["type"]])
    try:
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise VixlError("invalid_operation", "Operations must contain finite JSON values") from exc
    if page is not None:
        result["page"] = page
    return result


def schema_error(error, operation, allowed):
    """Turn a JSON Schema failure into a message an agent can act on in one retry."""
    import difflib
    from .errors import VixlError

    kind = operation["type"]
    path = [str(part) for part in error.absolute_path]
    field = ".".join(path) or None
    allowed = sorted(k for k in allowed if k != "type")
    details = {"field": field}
    validator = error.validator
    if validator == "additionalProperties":
        known = set(error.schema.get("properties", {}))
        extras = sorted(set(error.instance) - known)
        from .normalize import FIELD_ALIASES

        # Aliases count as spellings of their field: 'colr' is close to 'color', which a shape reads as 'fill'.
        aliases = {alias: canonical for alias, canonical in FIELD_ALIASES.get(kind, {}).items() if canonical in known}
        spellings = sorted(known | set(aliases))
        suggestions = {}
        for k in extras:
            close = difflib.get_close_matches(k, spellings, 1, 0.5)
            suggestions[k] = [aliases.get(close[0], close[0])] if close else []
        if kind in ("text", "text-set") and "width" in extras:
            suggestions["width"] = []
        hints = [f"{v[0]!r} instead of {k!r}" for k, v in suggestions.items() if v]
        where = f" in {field}" if field else f" for {kind!r}"
        message = f"Unknown field(s) {', '.join(map(repr, extras))}{where}. Allowed: {', '.join(sorted(known))}"
        if hints:
            message += f". Did you mean {', '.join(hints)}?"
        from .richtext import field_hint

        message += field_hint(kind, extras)
        details.update(field=field or extras[0], allowed=sorted(known), suggestions={k: v[0] for k, v in suggestions.items() if v})
    elif validator == "enum":
        options = error.validator_value
        close = difflib.get_close_matches(str(error.instance), [str(o) for o in options], 1, 0.4)
        message = f"{field} must be one of {', '.join(map(repr, options))}; got {error.instance!r}"
        if close:
            message += f". Did you mean {close[0]!r}?"
        details.update(allowed=options, suggestions=close)
    elif validator == "required":
        missing = error.message.split("'")[1] if "'" in error.message else error.message
        message = f"{kind!r} is missing required field {missing!r}. Allowed fields: {', '.join(allowed)}"
        details.update(field=missing, allowed=allowed)
    elif validator in ("anyOf", "oneOf") and all(
        set(option) == {"required"} for option in error.validator_value
    ):
        options = [" + ".join(o["required"]) for o in error.validator_value]
        quantifier = "exactly one of" if validator == "oneOf" else "at least one of"
        message = f"{kind!r} requires {quantifier}: {', '.join(options)}"
        details.update(allowed=options)
    elif path and path[-1] in COORD_FIELDS and (
        validator == "anyOf" or (error.parent is not None and error.parent.validator == "anyOf")
    ):
        kind_of = "a positive integer" if path[-1] in ("width", "height") else "a number, 'center'"
        message = f"{field} must be {kind_of} or a percentage like '50%'; got {error.instance!r}"
    elif validator == "type":
        message = f"{field} must be {error.validator_value}; got {type(error.instance).__name__} {error.instance!r}"
    elif validator in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        message = f"{field} {error.message}"
        details["limit"] = error.validator_value
    elif validator in ("maxItems", "minItems", "maxLength", "minLength"):
        # Name the bound and the size given; never echo the (possibly huge) value back.
        most = validator.startswith("max")
        unit = "entries" if validator.endswith("Items") else "characters"
        message = (f"{field or kind} holds {'at most' if most else 'at least'} {error.validator_value} {unit}; "
                   f"got {len(error.instance)}")
        details["limit"] = error.validator_value
    else:
        message = f"{field + ': ' if field else ''}{error.message}"
    # Point at the exact contract so one lookup, not a guess, fixes the next attempt.
    hint = f"vixl_operation_schema(types=[{kind!r}])"
    details.setdefault("fields", allowed)
    if validator == "type" and isinstance(error.schema, dict):
        details["expected"] = {k: v for k, v in error.schema.items() if k != "description"}
    details["schema"] = hint
    return VixlError("invalid_operation", f"{message} (see {hint})", **details)
