"""Schemas and CLI syntax for small pixel and animation documents."""

import json

from .pixel import PIXEL_TYPES
from .animation import ANIMATION_TYPES


def schemas(add):
    from .schema import S, N, B, enum

    grid = {"type": "integer", "minimum": 1, "maximum": 256}
    coordinate = {"type": "integer", "minimum": 0, "maximum": 255}
    palette = {"type": "object", "additionalProperties": S, "minProperties": 1, "maxProperties": 94}
    shading = {
        "anyOf": [B, {"type": "object", "properties": {
            "light": enum("auto", "top-left", "top", "top-right"),
            "colors": {"type": "integer", "minimum": 2, "maximum": 64},
            "highlight": B}, "additionalProperties": False}],
        "description": "Shade each colour area as it draws: a darker, cooler band on the side away from the light and "
        "a lighter one facing it, while the sprite stays within colors (default 16) opaque colours. true, false, or "
        "{light: auto|top-left|top|top-right, colors, highlight}. Stored rows are not changed. Default true for new "
        "documents (house style 4).",
    }
    outline = {
        "anyOf": [B, S],
        "description": "Ring the silhouette with a 1 px outline on the transparent cells around it: true (the darkest "
        "palette colour), a colour, or false. Skipped when the edge is already dark. Default true for new documents "
        "(house style 4).",
    }
    add(
        "pixel-art",
        {
            "name": S,
            "width": grid,
            "height": grid,
            "x": N,
            "y": N,
            "palette": palette,
            "background": S,
            "rows": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 256},
                "minItems": 1,
                "maxItems": 256,
            },
            "shading": shading,
            "outline": outline,
        },
    )
    add(
        "pixel-draw",
        {
            "tool": enum("pixel", "line", "rect", "fill"),
            "x": coordinate,
            "y": coordinate,
            "x2": coordinate,
            "y2": coordinate,
            "width": grid,
            "height": grid,
            "color": S,
        },
        ["x", "y", "color"],
    )
    add("pixel-palette", {"colors": palette, "shading": shading, "outline": outline},
        anyOf=[{"required": ["colors"]}, {"required": ["shading"]}, {"required": ["outline"]}])
    add(
        "frame-save",
        {"name": S, "duration": {"type": "integer", "minimum": 10, "maximum": 60000, "multipleOf": 10}},
        ["name"],
    )
    add("frame-apply", {"name": S}, ["name"])
    add("frame-delete", {"name": S}, ["name"])
    # Ranges (10–60000 ms in tens, 1–1024 entries, 1–200 operations) are checked in animation_sets, which keeps
    # the inline schema that MCP clients download small.
    add(
        "animation-set",
        {
            "loop": {"type": "integer", "minimum": 0, "maximum": 65535},
            "order": {
                "type": "array",
                "items": S,
                "description": "Frame names in play order. Without name: every saved frame exactly once "
                "(reorders the document's default animation). With name: any subset of the saved frames, "
                "repeats allowed.",
            },
            "name": {
                "type": "string",
                "description": "Define, update (loop/duration/durations only) or delete (delete=true) a named "
                "animation: a subset of saved frames with its own order, timing and loop. Export it alone with "
                "export-animation animation=NAME.",
            },
            "duration": {
                "type": "integer",
                "description": "Named animations: ms (10–60000, multiple of 10) for every frame, overriding saved durations.",
            },
            "durations": {
                "type": "array",
                "description": "Named animations: one ms value (10–60000, multiple of 10) per entry of order.",
            },
            "delete": {**B, "description": "Remove the named animation (its saved frames stay)."},
        },
    )
    add(
        "frames-edit",
        {
            "operations": {
                "type": "array",
                "description": "1–200 operations to run on each target frame, e.g. a pixel-palette recolour. "
                "Frames are snapshots, so layers are found by name or ID within each frame. Animation "
                "operations, layouts, templates and filesystem paths are not allowed.",
            },
            "animation": {"type": "string", "description": "Edit only the frames of this named animation."},
            "frames": {
                "type": "array",
                "description": "Edit only these saved frame names. Omit frames and animation to edit every frame.",
            },
            "scene": {**B, "description": "Also apply the operations to the working scene (default false)."},
        },
        ["operations"],
    )


def _flag_or_color(value):
    return {"true": True, "false": False}.get(value.lower(), value)


def compile_pixel(cmd, args):
    from .commands import Parser

    if cmd not in PIXEL_TYPES + ANIMATION_TYPES:
        return None
    p = Parser(prog=f"vixl {cmd}")
    if cmd == "pixel-art":
        p.add_argument("--name")
        p.add_argument("--width", type=int)
        p.add_argument("--height", type=int)
        p.add_argument("--x", type=int)
        p.add_argument("--y", type=int)
        p.add_argument("--palette", type=json.loads)
        p.add_argument("--rows", type=json.loads)
        p.add_argument("--background")
        p.add_argument("--shading", type=json.loads, help="true, false or JSON {light, colors, highlight}")
        p.add_argument("--outline", type=_flag_or_color, help="true, false or a colour")
    elif cmd == "pixel-draw":
        p.add_argument("target")
        p.add_argument("tool", choices=["pixel", "line", "rect", "fill"])
        p.add_argument("x", type=int)
        p.add_argument("y", type=int)
        p.add_argument("--color", required=True)
        for key in ("x2", "y2", "width", "height"):
            p.add_argument("--" + key, type=int)
    elif cmd == "pixel-palette":
        p.add_argument("target")
        p.add_argument("--colors", type=json.loads)
        p.add_argument("--shading", type=json.loads, help="true, false or JSON {light, colors, highlight}")
        p.add_argument("--outline", type=_flag_or_color, help="true, false or a colour")
    elif cmd.startswith("frame-"):
        p.add_argument("name")
        if cmd == "frame-save":
            p.add_argument("--duration", type=int)
    elif cmd == "frames-edit":
        p.add_argument("--operations", type=json.loads, required=True)
        p.add_argument("--animation")
        p.add_argument("--frames", nargs="+")
        p.add_argument("--scene", action="store_true", default=None)
    else:
        p.add_argument("--loop", type=int)
        p.add_argument("--order", nargs="+")
        p.add_argument("--name")
        p.add_argument("--duration", type=int)
        p.add_argument("--durations", nargs="+", type=int)
        p.add_argument("--delete", action="store_true", default=None)
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
