"""``path-split``: cut a filled path into two named parts along a polygon or a line.

The target's filled region (nonzero winding, as it renders) is cut by a ``polygon`` (inside and outside) or
by a ``line`` (an open polyline, extended past the shape at both ends: left and right of its direction).
``overlap`` lets both parts reach that many pixels across the cut, duplicating the strip they share, so two
traced shapes that cross (a vine through a letter) stay whole where they meet and can still be moved apart.
The parts are new path layers with the target's box, transform and appearance, placed above it; the target is
kept, hidden, as pathfinder keeps its operands. With ``curves`` (default) each part is refitted as Bézier
curves (``trace.fit_curves``) so it stays as easy to edit as the source.
"""

from copy import deepcopy

import numpy as np

from .errors import require
from .model import finite

TYPES = ("path-split",)
COPIED = ("x", "y", "rotation", "flip_x", "flip_y", "pivot", "skew_x", "skew_y", "affine", "opacity", "blend",
          "parent", "fill", "stroke", "stroke_width", "effects", "styles", "constraints")
FAR = 1e5


def schemas(add):
    from .schema import B, S, enum, field

    point = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
    add("path-split", {
        "polygon": field({"type": "array", "items": point, "minItems": 3, "maxItems": 4096},
                         "Cut out what lies inside this polygon [[x, y], …]: the first part is inside, the second outside."),
        "line": field({"type": "array", "items": point, "minItems": 2, "maxItems": 4096},
                      "Cut along this line [[x, y], …], extended past the shape at both ends: the first part lies left "
                      "of its direction (above a line drawn left to right), the second right."),
        "overlap": field({"type": "number", "minimum": 0, "maximum": 500},
                         "Pixels both parts reach across the cut, so crossing shapes stay whole (default 0)."),
        "names": field({"type": "array", "items": S, "minItems": 2, "maxItems": 2},
                       "Names of the two parts (default NAME-a and NAME-b)."),
        "space": field(enum("layer", "canvas"), "How the points read: layer (default), the target's own local pixels "
                       "as path-edit uses them, or canvas document pixels."),
        "curves": field(B, "Refit each part as Bézier curves (default true); false keeps straight segments."),
    }, ["target"], oneOf=[{"required": ["polygon"]}, {"required": ["line"]}],
        description="Cut a filled path into two named parts along a polygon or line, optionally overlapping the cut.")


def _local(project, layer, points, space):
    p = np.asarray(points, float)
    require(p.ndim == 2 and p.shape[1] == 2 and np.isfinite(p).all(), "points are [[x, y], …] numbers", field="polygon")
    if space == "layer":
        return p
    from .affine import layer_matrix
    from .checks import group_matrix
    from .render import resolve_layout, resolved_layers

    layers = resolved_layers(project)
    resolved = {item["id"]: item for item in layers}
    bounds = resolve_layout(project, layers=layers)
    matrix = group_matrix(resolved[layer["id"]], resolved, bounds) @ layer_matrix(resolved[layer["id"]], bounds[layer["id"]])
    inverse = np.linalg.inv(matrix)
    return (inverse @ np.column_stack([p, np.ones(len(p))]).T).T[:, :2]


def _cutter(op, points):
    """The region of the first part, as a shapely polygon."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import split

    if "polygon" in op:
        shape = Polygon(points).buffer(0)
        require(not shape.is_empty and shape.area > 0, "The polygon encloses no area", field="polygon")
        return shape
    start, end = points[0], points[-1]
    head = (points[0] - points[1]) / max(np.hypot(*(points[0] - points[1])), 1e-9)
    tail = (points[-1] - points[-2]) / max(np.hypot(*(points[-1] - points[-2])), 1e-9)
    require(np.hypot(*(end - start)) > 1e-6 or len(points) > 2, "The line needs two different points", field="line")
    line = LineString([start + head * 10 * FAR, *points, end + tail * 10 * FAR])
    halves = [part for part in split(box(-2 * FAR, -2 * FAR, 2 * FAR, 2 * FAR), line).geoms]
    require(len(halves) >= 2, "The line does not divide the plane; give it two different points", field="line")
    # The half on the left of the line's direction (y down: the side a left-to-right line has above it).
    direction = points[1] - points[0]
    probe = points[0] + direction / 2 + np.array([direction[1], -direction[0]]) / max(np.hypot(*direction), 1e-9)
    from shapely.geometry import Point

    left = [half for half in halves if half.contains(Point(*probe))]
    return left[0] if left else halves[0]


def _path(geometry, curves):
    from shapely.geometry.polygon import orient

    from .shape_catalog import poly
    from .trace import curves_path, fit_curves

    polygons = list(geometry.geoms) if geometry.geom_type in ("MultiPolygon", "GeometryCollection") else [geometry]
    parts = []
    for polygon in polygons:
        if polygon.geom_type != "Polygon" or polygon.is_empty or polygon.area < 0.5:
            continue
        polygon = orient(polygon, 1.0)
        for ring in (polygon.exterior, *polygon.interiors):
            coords = np.asarray(ring.coords, float)
            if curves and len(coords) > 8:
                segments = fit_curves(coords, True, 0.5, 50.0)
                if segments:
                    parts.append(curves_path(segments, True))
                    continue
            parts.append(poly([tuple(c) for c in coords[:-1]]))
    return " ".join(parts)


def execute(project, op):
    from .model import new_layer
    from .operations import append_layer, unique_name
    from .vector_boolean import offset_geometry
    from .vector_paths import pixel_path

    layer = project.layer(op.get("target"))
    require(layer["type"] == "shape", f"{layer['name']!r} is not a shape or path; path-split cuts filled vector shapes",
            field="target")
    require(("polygon" in op) != ("line" in op), "Give a polygon or a line to cut along, not both", field="polygon")
    overlap = finite(op.get("overlap", 0), "overlap", 0, 500)
    points = _local(project, layer, op.get("polygon") or op.get("line"), op.get("space", "layer"))
    region = offset_geometry(pixel_path(layer), 0)
    cutter = _cutter(op, points)
    first = region.intersection(cutter.buffer(overlap) if overlap else cutter)
    second = region.difference(cutter.buffer(-overlap) if overlap else cutter)
    names = op.get("names") or [f"{layer['name']}-a", f"{layer['name']}-b"]
    require(len(set(names)) == 2, "names must be two different names", field="names")
    pieces = [(name, _path(geometry, op.get("curves", True)) if not geometry.is_empty else "")
              for name, geometry in zip(names, (first, second))]
    empty = [name for name, data in pieces if not data]
    require(not empty, f"The cut does not cross {layer['name']!r}: nothing lies on the {' and '.join(empty)} side. "
            "Move the polygon or line so it divides the shape", field="polygon" if "polygon" in op else "line")
    made = []
    position = project.state["layers"].index(layer)
    for name, data in pieces:
        require(data.count("C") + data.count("L") <= 8192, "A part exceeds 8192 nodes", "resource_limit", field="target")
        part = new_layer(unique_name(project, name), "shape", layer["width"], layer["height"], shape="path", path=data,
                         path_view=[layer["width"], layer["height"]])
        for key in COPIED:
            if key in layer:
                part[key] = deepcopy(layer[key])
        part["path_split"] = {"source": layer["id"], "overlap": overlap}
        append_layer(project, part)
        project.state["layers"].remove(part)
        position += 1
        project.state["layers"].insert(position, part)
        made.append(part["name"])
    layer["visible"] = False
    project.state["active_layer"] = project.layer(made[0])["id"]
    from .selectors import record

    record(project, "path_split", {"source": layer["name"], "parts": made})


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    p = Parser(prog="vixl path-split", description="Cut a filled path into two parts along a polygon or line.")
    p.add_argument("target")
    p.add_argument("--polygon", type=json.loads, help="JSON [[x, y], …]")
    p.add_argument("--line", type=json.loads, help="JSON [[x, y], …]")
    p.add_argument("--overlap", type=float)
    p.add_argument("--names", help="two comma-separated names")
    p.add_argument("--space", choices=["layer", "canvas"])
    p.add_argument("--straight", dest="curves", action="store_false", default=None, help="keep straight segments")
    a = vars(p.parse_args(args))
    if a.get("names"):
        a["names"] = [n.strip() for n in a["names"].split(",")]
    return {"type": "path-split", **{k: v for k, v in a.items() if v is not None}}
