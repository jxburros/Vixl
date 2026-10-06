"""Editable pen geometry and local, pixel-accurate selection tools."""

import numpy as np
from PIL import Image, ImageDraw

from .errors import require
from .model import finite

TYPES = ("pen",)
TRIM_FIELDS = ("trim_start", "trim_end", "line_cap")  # Stroke trim and caps, shared with shape.


def schemas(add):
    from .schema import S, N, B, SIZE, COORD
    from .trim import schema as trim_schema

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
            **trim_schema(),
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


def shifted(op, dx, dy):
    """The pen operation with every node, handle and point moved by (dx, dy)."""
    def move(p):
        return [p[0] + dx, p[1] + dy]

    result = dict(op)
    if op.get("nodes") is not None:
        result["nodes"] = [{key: move(point(value)) for key, value in node.items()} for node in op["nodes"]]
    else:
        result["points"] = [move(point(p)) for p in op["points"]]
    return result


def node_extent(path, stroke_width=0):
    """(left, top, right, bottom) of a pen path, curves included, and of its stroke when given:
    half the width around every point, plus the tip of each sharp mitred join (SVG's default
    miter limit of 4 bevels sharper ones)."""
    import math

    from .geometry import path_polygons

    half = stroke_width / 2
    xs, ys = [], []
    for polygon in path_polygons(path):
        points = [p for i, p in enumerate(polygon) if not i or p != polygon[i - 1]]
        closed = len(points) > 2 and points[0] == points[-1]
        points = points[:-1] if closed else points
        for i, (x, y) in enumerate(points):
            xs += [x - half, x + half]
            ys += [y - half, y + half]
            if not half or (not closed and i in (0, len(points) - 1)):
                continue
            ax, ay = points[i - 1]
            bx, by = points[(i + 1) % len(points)]
            u = (ax - x, ay - y)
            v = (bx - x, by - y)
            lu, lv = math.hypot(*u), math.hypot(*v)
            if not lu or not lv:
                continue
            cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))
            sine = math.sin(math.acos(cos) / 2)
            if sine and 1 / sine <= 4:
                # The miter tip lies along the outer bisector, half / sin(θ/2) from the node.
                bisector = (u[0] / lu + v[0] / lv, u[1] / lu + v[1] / lv)
                length = math.hypot(*bisector)
                if length:
                    xs.append(x - bisector[0] / length * half / sine)
                    ys.append(y - bisector[1] / length * half / sine)
    return min(xs), min(ys), max(xs), max(ys)


def fit(op, stroke_width):
    """A pen path translated by whole pixels into a box that just holds it and its stroke:
    ``(path, (ox, oy), (width, height))``, where (ox, oy) is the box's corner in node coordinates."""
    import math

    import re

    path = pen_path(op)
    left, top, right, bottom = node_extent(path, stroke_width)
    # resvg rasterizes a curve slightly differently once a control point leaves the pixmap, so
    # the box holds the handles too.
    values = [float(v) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?", path)]
    left, right = min(left, *values[0::2]), max(right, *values[0::2])
    top, bottom = min(top, *values[1::2]), max(bottom, *values[1::2])
    ox, oy = math.floor(left - 1), math.floor(top - 1)
    width, height = math.ceil(right + 1) - ox, math.ceil(bottom + 1) - oy
    return pen_path(shifted(op, -ox, -oy)), (ox, oy), (width, height)


def require_inside(op, width, height):
    """Reject anchors outside an explicit box (a curve bulging slightly past it is allowed)."""
    anchors = [point(node["point"]) for node in op["nodes"]] if op.get("nodes") is not None else [
        point(p) for p in op["points"]
    ]
    xs, ys = zip(*anchors)
    left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    require(
        left >= -0.5 and top >= -0.5 and right <= width + 0.5 and bottom <= height + 0.5,
        f"Pen nodes span ({left:g}, {top:g})–({right:g}, {bottom:g}), outside the {width}×{height} box, and would "
        "be cut off; leave width and height out to fit the box to the nodes, or give a box that holds them",
        field="width",
    )


def place(project, layer, op, frame, origin):
    """Position a fitted pen box: numbers offset the node frame; 'center' centers the box."""
    canvas = project.state["canvas"]
    for axis, size, extent, start, offset in (("x", "width", "width", frame[0], origin[0]),
                                               ("y", "height", "height", frame[1], origin[1])):
        value = op.get(axis, start)
        layer[axis] = (canvas[extent] - layer[size]) / 2 if value == "center" else value + offset


def execute(project, op):
    from .operations import execute as apply

    if op.get("target"):
        layer = project.layer(op["target"])
        require(layer["type"] == "shape" and layer["shape"] == "path", "Pen editing needs a path layer")
        for key in ("fill", "stroke", "stroke_width", *TRIM_FIELDS):
            if key in op:
                layer[key] = op[key]
        if "pen_origin" in layer and "width" not in op and "height" not in op:
            # Nodes stay in the frame the pen was drawn in; refit the box around the new path.
            old = layer["pen_origin"]
            path, origin, size = fit(op, layer.get("stroke_width", 2))
            layer.update(path=path, width=size[0], height=size[1], path_view=list(size), pen_origin=list(origin))
            place(project, layer, op, (layer["x"] - old[0], layer["y"] - old[1]), origin)
            return
        layer["path"] = pen_path(op)
        for key in ("width", "height"):
            if key in op:
                layer[key] = op[key]
        place(project, layer, op, (layer["x"], layer["y"]), (0, 0))
        if "width" in op or "height" in op:
            layer["path_view"] = [layer["width"], layer["height"]]
            require_inside(op, *layer["path_view"])
            layer["pen_origin"] = [0, 0]
        return
    fields = {k: op[k] for k in ("name", "fill", "stroke", "stroke_width", *TRIM_FIELDS, "x", "y", "width", "height") if k in op}
    boxed = "width" in op or "height" in op
    if boxed:
        path, origin = pen_path(op), (0, 0)
    else:
        # Without a box, the layer fits its nodes (and stroke) instead of spanning the canvas.
        path, origin, size = fit(op, op.get("stroke_width", 2))
        fields.update(width=size[0], height=size[1])
        fields.pop("x", None)
        fields.pop("y", None)
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
    layer = project.layer()
    if boxed:
        require_inside(op, *layer["path_view"])
    else:
        place(project, layer, op, (0, 0), origin)
    layer["pen_origin"] = list(origin)


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

