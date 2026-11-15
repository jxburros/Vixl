"""Schemas and CLI syntax for small pixel and animation documents."""

import json

from .pixel import FLIPS, MIRRORS, PIXEL_TYPES, TOOLS
from .animation import ANIMATION_TYPES


def schemas(add):
    from .schema import S, N, B, enum

    grid = {"type": "integer", "minimum": 1, "maximum": 256}
    coordinate = {"type": "integer", "minimum": 0, "maximum": 255}
    palette = {"type": "object", "additionalProperties": S, "minProperties": 1, "maxProperties": 94}
    cell = {
        "type": "array", "minItems": 2, "maxItems": 2,
        "description": "Sprite-sheet cell [row, column] to place the sprite in instead of computing x and y (row by "
        "name or index, column from 0; declare the grid with sprite-sheet). x and y are then offsets inside the "
        "cell; the sprite has to fit the cell, so its outline never reaches the next frame.",
    }
    shading = {
        "anyOf": [B, {"type": "object", "properties": {
            "light": enum("auto", "top-left", "top", "top-right"),
            "colors": {"type": "integer", "minimum": 2, "maximum": 64},
            "highlight": B}, "additionalProperties": False}],
        "description": "Shade each colour area as it draws: a darker, cooler band on the side away from the light and "
        "a lighter one facing it, while the sprite stays within colors (default 16) opaque colours. true, false, or "
        "{light: auto|top-left|top|top-right, colors, highlight}. Stored rows are not changed. Default true for a new "
        "layer.",
    }
    outline = {
        "anyOf": [B, S],
        "description": "Ring the silhouette with a 1 px outline on the transparent cells around it: true (the darkest "
        "palette colour), a colour, or false. Skipped when the edge is already dark. Default true for a new layer.",
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
                "description": "Strings, one per pixel row; each character is a palette key. A count before a key "
                "repeats it: \"3.2#\" is \"...##\" (run-length rows; literal when the palette uses digits "
                "as keys). With mirror, the left or top half.",
            },
            "mirror": {
                **enum(*MIRRORS),
                "description": "Complete the rows by reflection: x (rows give the left half), y (the top half) or "
                "xy. Give width or height one less than twice the half to make the last column or row the centre.",
            },
            "shading": shading,
            "outline": outline,
            "cell": cell,
        },
    )
    add(
        "pixel-draw",
        {
            "tool": enum(*TOOLS),
            "x": coordinate,
            "y": coordinate,
            "x2": coordinate,
            "y2": coordinate,
            "width": grid,
            "height": grid,
            "color": S,
            "only": {
                "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 1}, "minItems": 1,
                "maxItems": 94, "uniqueItems": True,
                "description": "Masked painting: palette symbols the tool may overwrite; every other cell is left "
                "as it is (shade only the cells that are already hair: only: [\"h\"]).",
            },
            "rows": {
                "type": "object", "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 256},
                "maxProperties": 256,
                "description": "Frame delta: only the rows that changed, {row index: row string} (run-length "
                "counts allowed). Replaces tool, x, y and color.",
            },
            "cells": {
                "type": "array", "items": {"type": "array", "minItems": 3, "maxItems": 3}, "maxItems": 65536,
                "description": "Frame delta: only the cells that changed, [[x, y, symbol], ...]. Replaces tool, "
                "x, y and color.",
            },
        },
        anyOf=[{"required": ["x", "y", "color"]}, {"required": ["rows"]}, {"required": ["cells"]}],
    )
    add("pixel-palette", {"colors": palette, "shading": shading, "outline": outline},
        anyOf=[{"required": ["colors"]}, {"required": ["shading"]}, {"required": ["outline"]}])
    add(
        "pixel-transform",
        {
            "flip": {**enum(*FLIPS), "description": "Mirror the stored rows: horizontal (a right-facing frame from "
                     "the left-facing one), vertical or both. Unlike the layer flip, shading still falls from the "
                     "same light."},
            "shift": {"type": "array", "items": {"type": "integer", "minimum": -256, "maximum": 256}, "minItems": 2,
                      "maxItems": 2, "description": "Move the grid contents by [dx, dy] cells (a walk-cycle bob is "
                      "[0, 1]); applied after flip. Cells pushed off the grid are dropped."},
            "wrap": {**B, "description": "Shifted cells come back in on the opposite side (a scrolling tile) "
                     "instead of being dropped. Default false."},
            "fill": {"type": "string", "minLength": 1, "maxLength": 1, "description": "Palette symbol for the cells "
                     "a shift leaves empty. Default: the palette's first transparent symbol."},
        },
        anyOf=[{"required": ["flip"]}, {"required": ["shift"]}],
    )
    add(
        "sprite-sheet",
        {
            "cell": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 1024}, "minItems": 2,
                     "maxItems": 2, "description": "Size of one frame, [width, height] in pixels."},
            "rows": {"type": "array", "items": S, "minItems": 1, "maxItems": 64, "uniqueItems": True,
                     "description": "Row names from the top, one per facing or state: [\"down\", \"left\", "
                     "\"right\", \"up\"]."},
            "columns": {"type": "integer", "minimum": 1, "maximum": 256, "description": "Frames per row."},
            "duration": {"type": "integer", "minimum": 10, "maximum": 60000,
                         "description": "Frame time in ms for clips that give none (default 100)."},
            "clips": {
                "type": "object", "maxProperties": 256,
                "description": "Named clips for the exported metadata: {name: {row, frames, duration, durations, "
                "loop}}. frames lists column indexes in play order (default every column); a clip without row "
                "stands for one per row, named NAME-ROW ({\"walk\": {}, \"idle\": {\"frames\": [0]}} gives "
                "walk-down, idle-left ...). Without clips each row is one clip named after the row.",
            },
            "fit_canvas": {**B, "description": "Resize the canvas to the grid, columns x rows cells (default true)."},
            "delete": {**B, "description": "Remove the sheet declaration (layers stay where they are)."},
        },
    )
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


def _cell(value):
    row, _, column = value.rpartition(",")
    return [int(row) if row.isdigit() else row, int(column)]


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
        p.add_argument("--mirror", choices=list(MIRRORS), help="rows give the left (x) or top (y) half")
        p.add_argument("--shading", type=json.loads, help="true, false or JSON {light, colors, highlight}")
        p.add_argument("--outline", type=_flag_or_color, help="true, false or a colour")
        p.add_argument("--cell", type=_cell, metavar="ROW,COLUMN", help="sprite-sheet cell, e.g. left,2")
    elif cmd == "pixel-draw":
        p.add_argument("target")
        p.add_argument("tool", choices=list(TOOLS))
        p.add_argument("x", type=int)
        p.add_argument("y", type=int)
        p.add_argument("--color", required=True)
        for key in ("x2", "y2", "width", "height"):
            p.add_argument("--" + key, type=int)
        p.add_argument("--only", nargs="+", metavar="SYMBOL", help="overwrite only cells holding these symbols")
    elif cmd == "pixel-transform":
        p.add_argument("target")
        p.add_argument("--flip", choices=list(FLIPS))
        p.add_argument("--shift", nargs=2, type=int, metavar=("DX", "DY"))
        p.add_argument("--wrap", action="store_true", default=None)
        p.add_argument("--fill", help="palette symbol for the cells a shift leaves empty")
    elif cmd == "sprite-sheet":
        p.add_argument("--cell", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
        p.add_argument("--rows", nargs="+", metavar="NAME")
        p.add_argument("--columns", type=int)
        p.add_argument("--duration", type=int)
        p.add_argument("--clips", type=json.loads, help="JSON {name: {row, frames, duration, durations, loop}}")
        p.add_argument("--no-fit-canvas", dest="fit_canvas", action="store_false", default=None)
        p.add_argument("--delete", action="store_true", default=None)
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
