"""``die-cut``: a sticker or label cut line around what the target layers draw.

The targets are drawn alone (``proxy.isolated``: ancestor groups still transform them), their ink is traced
(``trace.mask_contours``), holes are filled so the line follows the outer silhouette, and the union is grown by
``distance`` pixels with the same buffering ``offset-path`` uses (``vector_boolean.offset_geometry``). The
result is one new path layer in canvas coordinates, named ``cut-line`` by default: stroked and unfilled
(an explicit transparent fill, so every renderer and export leaves it open), placed above the topmost
target. Parts the distance does not join stay separate contours of the same path (``summary.pieces``).
"""

import numpy as np

from .errors import require
from .model import finite, new_layer

TYPES = ("die-cut",)
JOINS = ("round", "miter", "bevel")
DEFAULTS = {"distance": 12, "name": "cut-line", "stroke": "#ec008c", "stroke_width": 1, "join": "round",
            "threshold": 0.5, "smooth": 1.0}


def schemas(add):
    from .schema import S, enum, field

    N = {"type": "number"}
    from .model import MAX_LAYERS

    add("die-cut", {
        "targets": field({"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS, "uniqueItems": True},
                         "Layers the cut line goes around (IDs or names; a group brings its members)."),
        "distance": field({**N, "minimum": 0, "maximum": 1000}, "How far the cut line sits outside the artwork, in "
                          "pixels (default 12). 0 follows the ink exactly."),
        "name": field(S, "Name of the new cut-line layer (default cut-line)."),
        "stroke": field(S, "Cut-line color (default #ec008c, a magenta die line)."),
        "stroke_width": field({**N, "minimum": 0.1, "maximum": 100}, "Cut-line width in pixels (default 1)."),
        "join": field(enum(*JOINS), "Corner shape of the offset outline: round (default), miter or bevel."),
        "threshold": field({**N, "minimum": 0.01, "maximum": 1}, "Opacity from which a pixel counts as ink, 0-1 "
                           "(default 0.5)."),
        "smooth": field({**N, "minimum": 0, "maximum": 20}, "Blur radius in pixels before tracing, which rounds "
                        "stair steps (default 1)."),
    }, ["targets"], description="Add a sticker cut line: the union of the targets' ink outline, offset by a distance.")


def execute(project, op):
    from .operations import append_layer, unique_name
    from .proxy import isolated
    from .render import render, view_page
    from .shape_catalog import poly
    from .trace import mask_contours
    from .vector_boolean import offset_geometry

    settings = {**DEFAULTS, **{k: v for k, v in op.items() if k in DEFAULTS}}
    distance = finite(settings["distance"], "distance", 0, 1000)
    threshold = finite(settings["threshold"], "threshold", 0.01, 1)
    refs = op.get("targets") or ([op["target"]] if op.get("target") else [])
    require(refs, "die-cut needs targets: the layers the cut line goes around", field="targets")
    targets = [project.layer(ref) for ref in refs]
    view = isolated(view_page(project), [layer["id"] for layer in targets])
    view.state["canvas"]["background"] = "transparent"
    image = render(view)
    alpha = np.asarray(image.getchannel("A"))
    mask = alpha >= round(threshold * 255)
    require(mask.any(), "The targets draw nothing on the canvas to cut around", field="targets")
    # Trace with room around the canvas so ink touching an edge still closes into a loop.
    padded = np.pad(mask, 2)
    loops = mask_contours(padded, smooth=float(settings["smooth"]), tolerance=0.35, min_area=4.0)
    require(loops, "The targets' ink is too small to cut around", field="targets")
    path = " ".join(poly([(x - 1.5, y - 1.5) for x, y in loop]) for loop in loops)
    geometry = offset_geometry(path, distance, settings["join"], holes=False)
    polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    rings = [np.asarray(polygon.simplify(0.25).exterior.coords, float) for polygon in polygons]
    low = np.min([ring.min(axis=0) for ring in rings], axis=0)
    high = np.max([ring.max(axis=0) for ring in rings], axis=0)
    x0, y0 = np.floor(low)
    width, height = max(1, int(np.ceil(high[0] - x0))), max(1, int(np.ceil(high[1] - y0)))
    data = " ".join(poly([(x - x0, y - y0) for x, y in ring]) for ring in rings)
    require(data.count("L") <= 8192, "The cut line exceeds 8192 nodes; raise smooth or the distance",
            "resource_limit", field="smooth")
    stroke_width = finite(settings["stroke_width"], "stroke_width", 0.1, 100)
    layer = new_layer(unique_name(project, settings["name"]), "shape", width, height, shape="path", path=data,
                      path_view=[width, height], fill="transparent", stroke=settings["stroke"],
                      stroke_width=stroke_width, x=int(x0), y=int(y0), role="decoration",
                      die_cut={"targets": [layer["id"] for layer in targets], "distance": distance,
                               "pieces": len(rings)})
    layer["allow_overlap"] = [item["id"] for item in targets][:512]
    from .design import resolve_color
    from .render import color

    color(resolve_color(settings["stroke"], project.state))
    append_layer(project, layer)
    layers = project.state["layers"]
    roots = []
    for item in targets:  # the top-level layer each target belongs to
        while item.get("parent"):
            item = project.layer(item["parent"])
        roots.append(item)
    layers.remove(layer)
    layers.insert(max(layers.index(item) for item in roots) + 1, layer)
    project.state["active_layer"] = layer["id"]
    from .selectors import record

    record(project, "die_cut", {"layer": layer["name"], "pieces": len(rings), "distance": distance,
                                "bounds": [int(x0), int(y0), width, height]})


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog="vixl die-cut", description="Add a sticker cut line around the targets' ink.")
    p.add_argument("targets", nargs="+")
    p.add_argument("--distance", type=float)
    p.add_argument("--name")
    p.add_argument("--stroke")
    p.add_argument("--stroke-width", type=float)
    p.add_argument("--join", choices=list(JOINS))
    p.add_argument("--threshold", type=float)
    p.add_argument("--smooth", type=float)
    a = vars(p.parse_args(args))
    return {"type": "die-cut", **{k: v for k, v in a.items() if v is not None}}
