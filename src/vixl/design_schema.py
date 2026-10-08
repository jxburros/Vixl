"""Schemas for editable design primitives shared by every operation interface."""

from .geometry import EXTRA_SHAPES

TYPES = (
    "shape",
    "group",
    "ungroup",
    "reparent",
    "clip",
    "layer-style",
    "distribute",
    "style-define",
    "style-apply",
    "swatch",
    "artboard",
    "frame",
    "replace-contents",
    "repeat",
    "repeat-blend",
    "adjustment",
    "lut",
    "lookup",
    "comp-save",
    "comp-apply",
    "text-layout",
    "guide",
    "grid",
    "pathfinder",
    "symbol",
    "symbol-instance",
)
SHAPES = ("rectangle", "rounded-rectangle", "ellipse", "polygon", "star", "line", *EXTRA_SHAPES)
STYLES = ("drop-shadow", "stroke", "outer-glow", "color-overlay", "gradient-overlay")


def schemas(add):
    from .inplace import target_schema
    from .model import MAX_LAYERS
    from .schema import S, N, B, POSITIVE_INT, COORD, SIZE, enum

    refs = {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS, "uniqueItems": True}
    obj = {"type": "object"}
    geometry = {"name": S, "width": SIZE, "height": SIZE, "x": COORD, "y": COORD}
    board = {"name": S, "width": POSITIVE_INT, "height": POSITIVE_INT, "x": N, "y": N}
    from .trim import schema as trim_schema
    from .shape_catalog import schema as catalog_schema
    from .vector_strokes import schema as stroke_schema

    add(
        "shape",
        {
            **geometry,
            "target": target_schema("shape"),
            "shape": enum(*SHAPES),
            "path": S,
            "fill": S,
            "stroke": S,
            "stroke_width": N,
            "radius": N,
            "sides": {"type": "integer", "minimum": 3, "maximum": 128},
            "inner_radius": {
                **N,
                "description": "star: inner point radius 0.01–1; arc: hole radius 0 (pie wedge) to 0.99 (thin ring), as a fraction of the outer radius.",
            },
            "start_angle": {
                **N,
                "description": "arc: start angle in degrees, 0 at 3 o'clock, clockwise (-90 is 12 o'clock). Default 0.",
            },
            "end_angle": {
                **N,
                "description": "arc: end angle in degrees, clockwise from start_angle; 360 or more past it is the full circle/ring. Default start_angle + 360.",
            },
            **trim_schema(),
            **catalog_schema(),
            **stroke_schema(),
        },
        anyOf=[{"required": ["shape"]}, {"required": ["target"]}],
    )
    add("group", {"name": S, "targets": refs,
                  "above": {**S, "description": "Place the new group directly above this layer (same parent) instead "
                            "of at its topmost member's slot."},
                  "below": {**S, "description": "Place the new group directly below this layer (same parent)."}},
        ["name", "targets"])
    add("ungroup")
    from .reparent import schema as reparent_schema

    reparent_schema(add)
    add("clip", {"base": S, "release": B})
    add("layer-style", {"name": enum(*STYLES), "settings": obj, "remove": B}, ["name"])
    add(
        "distribute", {"targets": refs, "axis": enum("horizontal", "vertical"), "gap": N}, ["targets", "axis"]
    )
    add(
        "style-define",
        {"name": S, "kind": enum("character", "paragraph"), "settings": obj},
        ["name", "settings"],
    )
    add("style-apply", {"name": S, "kind": enum("character", "paragraph")}, ["name"])
    add("swatch", {"name": S, "color": S}, ["name", "color"])
    add(
        "artboard",
        {**board, "preset": S, "background": S, "variables": obj, "targets": refs, "delete": B},
        ["name"],
    )
    add(
        "frame",
        {**geometry, "path": S, "asset": S, "fit": enum("fill", "fit"),
         "max_pixels": {"type": "integer", "minimum": 1}, "downsample": enum("placed@2x")},
        anyOf=[{"required": ["path"]}, {"required": ["asset"]}],
    )
    add(
        "replace-contents",
        {"path": S, "asset": S, "variable": S, "fit": enum("fill", "fit")},
        anyOf=[{"required": ["path"]}, {"required": ["asset"]}, {"required": ["variable"]}],
    )
    repeat = {"count": POSITIVE_INT, "dx": N, "dy": N, "dw": N, "dh": N}
    from .scatter import step_schema

    add("repeat", {**repeat, **step_schema(), "name": {**S, "description": "With per-step fields or merge: name of "
                   "the group (or merged layer) of copies."}}, ["count"])
    add("repeat-blend", {**repeat, "end": obj}, ["count", "end"])
    add("adjustment", {"name": S, "effects": {"type": "array", "items": obj, "maxItems": 256}}, ["effects"])
    add(
        "lut",
        {
            "name": S,
            "size": POSITIVE_INT,
            "values": {
                "type": "array",
                "items": {"type": "array", "items": N, "minItems": 3, "maxItems": 3},
                "maxItems": 35937,
            },
        },
        ["name", "size", "values"],
    )
    add("lookup", {"name": S, "amount": N}, ["name"])
    add("comp-save", {"name": S}, ["name"])
    add("comp-apply", {"name": S}, ["name"])
    add(
        "text-layout",
        {
            "width": SIZE,
            "height": SIZE,
            "fit": B,
            "warp": enum("none", "arc", "flag", "bulge"),
            "amount": N,
            "path": {
                "type": "array",
                "items": {"type": "array", "items": N, "minItems": 2, "maxItems": 2},
                "minItems": 2,
                "maxItems": 1024,
            },
        },
    )
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    add("guide", {"name": S, "axis": enum("x", "y"), "position": N,
                  "kind": enum("axis", "line", "ray", "segment", "point", "circle", "path"),
                  "x": N, "y": N, "angle": N, "radius": N, "d": S, "delete": B,
                  "points": {"type": "array", "items": point, "minItems": 2, "maxItems": 2}}, ["name"])
    from .guides import GRID_KINDS

    add(
        "grid",
        {"name": S, "kind": enum(*GRID_KINDS), "columns": POSITIVE_INT, "rows": {"anyOf": [POSITIVE_INT, {"type": "array", "items": N}]},
         "margin": N, "gutter": N, "spacing": N, "offset": N, "region": {"type": "array", "items": N, "minItems": 4, "maxItems": 4},
         "x": N, "y": N, "radius": N, "rings": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "array", "items": N}]},
         "spokes": {"type": "integer", "minimum": 0}, "angle": N, "angles": {"type": "array", "items": N},
         "spacings": {"type": "array", "items": N}, "turns": N, "corner": S, "horizon": N,
         "points": {"type": "integer", "minimum": 1, "maximum": 3},
         "vanishing": {"type": "array", "items": point, "minItems": 1, "maxItems": 3},
         "rays": {"type": "integer", "minimum": 2}, "delete": B},
        ["name"],
    )
    add(
        "pathfinder",
        {"name": S, "targets": refs, "mode": enum("union", "subtract", "intersect", "exclude", "divide", "minus-back", "trim", "merge")},
        ["name", "targets", "mode"],
    )
    add("symbol", {"name": S}, ["name"])
    add("symbol-instance", {**geometry, "symbol": S}, ["symbol"])
