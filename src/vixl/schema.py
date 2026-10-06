"""Discoverable JSON Schema for the public structured operation format."""

from copy import deepcopy
from functools import lru_cache

from .inplace import target_schema
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
    "anyOf": [POSITIVE_INT, {"type": "string", "pattern": r"^\d+(\.\d+)?%$"}],
    "description": "Pixels or a percentage of the canvas/parent such as '25%'.",
}
COORD_FIELDS = ("x", "y", "width", "height")
FONT = {
    "type": "string",
    "description": "Registered font name or role (heading, body); install with font install / font pair / font import. "
    "File paths work only in the CLI and Python API, not over MCP or REST.",
}


def enum(*values):
    return {"enum": list(values)}


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
            "stops": {"type": "array", "items": {"type": "object"}},
            "angle": N,
            "x": COORD,
            "y": COORD,
        },
    )
    add("palette-define", {"name": S, "colors": {"type": "array", "items": S, "minItems": 2, "maxItems": 256}}, ["name", "colors"])
    from .palette_roles import role_schema

    add("palette-apply", {"name": S, "prefix": S, "roles": {"anyOf": [B, role_schema()]}, "keep_order": B,
                          "policy": enum("strict", "accessible")}, ["name"])
    add("template-apply", {"name": S, "variables": {"type": "object"}, "seed": {"type": ["integer", "string"]}}, ["name"])
    add("guidance", {"name": S, "text": S, "style": S, "delete": B}, ["name"])
    add("font-register", {"name": S, "asset": S, "role": S}, ["name"])
    text = {
        "text": S,
        "size": POSITIVE_INT,
        "color": S,
        "align": enum("left", "center", "right"),
        "spacing": {"type": "integer", "minimum": 0},
        "hide_if_empty": {
            "type": "boolean",
            "description": "Do not draw the text (and take no space in a stack) while it is empty or blank "
            "after ${variable} substitution.",
        },
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
    add("move", {"x": COORD, "y": COORD, "relative": B}, anyOf=[{"required": ["x"]}, {"required": ["y"]}])
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
    # A negative factor mirrors: value flips both axes, x or y just that one (scale x: -1 = flip horizontal).
    scale = {"type": "number", "description": "Size factor, 0.001-100 (0.8 = 80%). Negative values mirror the layer on that axis."}
    add("scale", {"value": {**scale, "description": "Size factor for both axes, 0.001-100 (0.8 = 80%). Negative mirrors both axes."},
                  "x": {**scale, "description": "Horizontal factor, overriding value. Negative mirrors horizontally, like flip."},
                  "y": {**scale, "description": "Vertical factor, overriding value. Negative mirrors vertically."}},
        anyOf=[{"required": ["value"]}, {"required": ["x"]}, {"required": ["y"]}])
    add("rotate", {"value": N}, ["value"])
    # value: [x, y] fractions of the unrotated box (0.5, 0.5 = center) or an anchor such as "top-left".
    add("pivot", {"value": {"type": ["array", "string"], "items": N}, "units": enum("fraction", "px"), "clear": B})
    add("opacity", {"value": {"type": "number", "minimum": 0, "maximum": 1}}, ["value"])
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
            ),
            "margin": N,
            "relative_to": S,
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
    }
    add("effect", {"name": S, **effect}, ["name"])
    for kind in EFFECTS:
        add(kind, deepcopy(effect))
    for kind in ("effect-disable", "effect-enable", "effect-remove", "effect-set"):
        add(
            kind,
            {"effect": {"type": ["integer", "string"]}, **(effect if kind == "effect-set" else {})},
            ["effect"],
        )
    add("variable", {"name": S, "value": {"type": ["string", "number", "boolean"]}, "delete": B}, ["name"])
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
    from .schema_docs import enrich

    enrich(variants)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Vixl operation batch",
        "type": "object",
        "properties": {
            "operations": {"type": "array", "minItems": 1, "maxItems": 1000, "items": {"oneOf": variants}}
        },
        "required": ["operations"],
        "additionalProperties": False,
    }


@lru_cache(maxsize=1)
def _properties():
    variants = _operation_schema()["properties"]["operations"]["items"]["oneOf"]
    return {v["properties"]["type"]["const"]: frozenset(v["properties"]) for v in variants}


def validate_operation(operation, notes=None, index=None):
    """Normalize common spellings, then validate before doing any I/O."""
    import json
    from .errors import VixlError, require
    from .normalize import normalize_operation
    from .operations import ALIASES

    require(isinstance(operation, dict), "Each operation must be an object")
    result = deepcopy(operation)
    kind = result.pop("operation", result.get("type"))
    result["type"] = ALIASES.get(kind, kind) if isinstance(kind, str) else kind
    # Any operation can name the page it edits; "page" operations use the field themselves.
    page = result.pop("page", None) if result["type"] != "page" else None
    if page is not None:
        require(isinstance(page, (str, int)) and not isinstance(page, bool), "page must be a page name or number",
                field="page")
    properties = _properties()
    result = normalize_operation(
        result, lambda k: properties.get(k, frozenset()), properties, EFFECTS, [] if notes is None else notes, index
    )
    require(isinstance(result.get("type"), str), "Operation requires a string type", field="type")
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
        suggestions = {k: difflib.get_close_matches(k, sorted(known), 1, 0.5) for k in extras}
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
    else:
        message = f"{field + ': ' if field else ''}{error.message}"
    # Point at the exact contract so one lookup, not a guess, fixes the next attempt.
    hint = f"vixl_operation_schema(types=[{kind!r}])"
    details.setdefault("fields", allowed)
    if validator == "type" and isinstance(error.schema, dict):
        details["expected"] = {k: v for k, v in error.schema.items() if k != "description"}
    details["schema"] = hint
    return VixlError("invalid_operation", f"{message} (see {hint})", **details)

