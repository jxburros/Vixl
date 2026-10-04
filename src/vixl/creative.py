"""Editable pen geometry and local, pixel-accurate selection tools."""

import numpy as np
from PIL import Image, ImageDraw

from .errors import require
from .model import finite

TYPES = ("pen",)


def schemas(add):
    from .schema import S, N, B, SIZE, COORD

    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    node = {
        "type": "object",
        "properties": {"point": point, "in": point, "out": point},
        "required": ["point"],
        "additionalProperties": False,
    }
    add(
        "pen",
        {
            "name": S,
            "nodes": {"type": "array", "items": node, "minItems": 2, "maxItems": 512},
            "points": {"type": "array", "items": point, "minItems": 2, "maxItems": 512},
            "closed": B,
            "smooth": B,
            "tension": {"type": "number", "minimum": 0, "maximum": 1},
            "corners": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 512},
            "fill": S,
            "stroke": S,
            "stroke_width": N,
            "width": SIZE,
            "height": SIZE,
            "x": COORD,
            "y": COORD,
        },
        oneOf=[
            {"required": ["nodes"], "not": {"required": ["points"]}},
            {"required": ["points"], "not": {"required": ["nodes"]}},
        ],
    )


def point(value):
    require(isinstance(value, (list, tuple)) and len(value) == 2, "Expected [x,y]")
    return [finite(v, "coordinate", -1e6, 1e6) for v in value]


def pen_path(op):
    nodes = op.get("nodes")
    closed = op.get("closed", False)
    if nodes is None:
        pts = [point(p) for p in op["points"]]
        nodes = [{"point": p} for p in pts]
        if op.get("smooth", True):
            for i, node in enumerate(nodes):
                prev = pts[(i - 1) % len(pts)] if closed or i else pts[i]
                nxt = pts[(i + 1) % len(pts)] if closed or i < len(pts) - 1 else pts[i]
                if i in op.get("corners", []):
                    continue
                tangent = [(b - a) * op.get("tension", 1) / 6 for a, b in zip(prev, nxt)]
                node["in"] = [v - t for v, t in zip(node["point"], tangent)]
                node["out"] = [v + t for v, t in zip(node["point"], tangent)]

    def coords(p):
        return " ".join(f"{v:.8g}" for v in point(p))

    commands = ["M" + coords(nodes[0]["point"])]
    pairs = list(zip(nodes, nodes[1:])) + ([(nodes[-1], nodes[0])] if closed else [])
    for a, b in pairs:
        if "out" in a or "in" in b:
            commands.append(
                "C"
                + " ".join(coords(p) for p in (a.get("out", a["point"]), b.get("in", b["point"]), b["point"]))
            )
        else:
            commands.append("L" + coords(b["point"]))
    if closed:
        commands.append("Z")
    return " ".join(commands)


def execute(project, op):
    from .operations import execute as apply

    path = pen_path(op)
    if op.get("target"):
        layer = project.layer(op["target"])
        require(layer["type"] == "shape" and layer["shape"] == "path", "Pen editing needs a path layer")
        layer["path"] = path
        for key in ("fill", "stroke", "stroke_width", "x", "y", "width", "height"):
            if key in op:
                layer[key] = op[key]
        if "width" in op or "height" in op:
            layer["path_view"] = [layer["width"], layer["height"]]
    else:
        fields = {
            k: op[k]
            for k in ("name", "fill", "stroke", "stroke_width", "x", "y", "width", "height")
            if k in op
        }
        apply(
            project,
            {
                "type": "shape",
                "shape": "path",
                "path": path,
                "fill": "transparent",
                "stroke": "black",
                "stroke_width": 2,
                **fields,
            },
        )


def selection(project, op):
    canvas = project.state["canvas"]
    size = canvas["width"], canvas["height"]
    if op["shape"] in ("lasso", "path"):
        from .geometry import path_polygons

        mask = Image.new("L", size)
        draw = ImageDraw.Draw(mask)
        polygons = path_polygons(op["path"]) if op["shape"] == "path" else [[point(p) for p in op["points"]]]
        for polygon in polygons:
            require(len(polygon) >= 3, "Lasso needs at least three points")
            draw.polygon([tuple(p) for p in polygon], fill=255)
        return mask
    x, y = op.get("x"), op.get("y")
    require(
        type(x) is int and type(y) is int and 0 <= x < size[0] and 0 <= y < size[1],
        "Wand seed must be an integer pixel inside the canvas",
    )
    rgba = np.asarray(project.render(), dtype=np.int16)
    tolerance = finite(op.get("tolerance", 15), "tolerance", 0, 255)
    matches = np.max(np.abs(rgba - rgba[y, x]), axis=2) <= tolerance
    # RGB under fully transparent pixels is visually irrelevant.
    if rgba[y, x, 3] == 0:
        matches = rgba[:, :, 3] <= tolerance
    if not op.get("contiguous", True):
        return Image.fromarray(matches.astype(np.uint8) * 255)
    # Pillow floodfill uses an iterative frontier, avoiding recursive traversal.
    mask = Image.fromarray(matches.astype(np.uint8)).copy()
    ImageDraw.floodfill(mask, (x, y), 2, thresh=0)
    return Image.fromarray((np.asarray(mask) == 2).astype(np.uint8) * 255)

