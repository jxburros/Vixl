"""Radial repeat: N copies of a layer around a center, optionally mirrored.

``repeat`` steps a layer along a line; this turns it about a point, which is what mandalas,
rosettes, sunbursts, flower heads and gear teeth need. Each copy is an ordinary layer (turned
about its own center and moved to its place on the circle), so the result stays editable and
the copies are grouped under one name. ``mirror`` adds a reflection of every copy across the
vertical axis through the center, giving the dihedral symmetry of a kaleidoscope.
"""

import math

from .errors import VixlError, require
from .model import finite

TYPES = ("radial-repeat",)
MAX_COPIES = 360


def schemas(add):
    from .schema import S, N, B, COORD

    add("radial-repeat", {
        "count": {"type": "integer", "minimum": 2, "maximum": MAX_COPIES},
        "cx": COORD,
        "cy": COORD,
        "sweep": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
        "start_angle": N,
        "mirror": B,
        "group": B,
        "name": S,
    }, ["count"])


def _center(value, base, default, name):
    if value is None:
        return default
    if value == "center":
        return base / 2
    if isinstance(value, str):
        require(value.endswith("%"), f"{name} must be pixels, 'center' or a percentage like '50%'", field=name)
        return float(value[:-1]) * base / 100
    return finite(value, name, -1e6, 1e6)


def execute(project, op):
    from .operations import execute as apply
    from .render import resolve_layout, resolved_layers, transformed_size

    layer = project.layer(op.get("target"))
    require(layer["type"] != "field", "Form fields are upright rectangles and cannot be turned", field="target")
    count = op["count"]
    sweep = finite(op.get("sweep", 360), "sweep", 0.001, 360)
    start = finite(op.get("start_angle", 0), "start_angle", -3600, 3600)
    mirror = bool(op.get("mirror", False))
    grouped = op.get("group", True)
    require(count * (2 if mirror else 1) <= MAX_COPIES, f"At most {MAX_COPIES} copies including mirrors",
            "resource_limit", field="count")
    if layer.get("pivot") is not None:
        apply(project, {"type": "pivot", "target": layer["id"], "clear": True})
    parent = project.layer(layer["parent"]) if layer.get("parent") else None
    width = parent["content_width"] if parent else project.state["canvas"]["width"]
    height = parent["content_height"] if parent else project.state["canvas"]["height"]
    # The layer's current center, wherever its constraints or rotation put it.
    bounds = resolve_layout(project)[layer["id"]]
    mx, my = bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2
    cx = _center(op.get("cx"), width, width / 2, "cx")
    cy = _center(op.get("cy"), height, height / 2, "cy")
    resolved = next(item for item in resolved_layers(project) if item["id"] == layer["id"])
    base_rotation, base_flip = layer.get("rotation", 0), layer.get("flip_x", False)
    step = sweep / count if sweep >= 360 else sweep / max(1, count - 1)
    name = layer["name"]
    members = [layer["id"]]

    def place(item, theta, reflect):
        dx, dy = mx - cx, my - cy
        a = math.radians(theta)
        x = cx + dx * math.cos(a) - dy * math.sin(a)
        y = cy + dx * math.sin(a) + dy * math.cos(a)
        rotation = base_rotation + theta
        if reflect:
            x, rotation = 2 * cx - x, -rotation
        item["constraints"] = {}
        item["rotation"] = rotation % 360
        item["flip_x"] = (not base_flip) if reflect else base_flip
        # A turned layer's stored x/y is the corner of its (larger) rotated bounds, which stay centered on the layer.
        tw, th = transformed_size({**resolved, "rotation": item["rotation"]})
        item["x"], item["y"] = x - tw / 2, y - th / 2

    def clone(label):
        apply(project, {"type": "duplicate", "target": layer["id"], "name": label})
        copy = project.layer()
        members.append(copy["id"])
        return copy

    for i in range(count):
        theta = start + step * i
        if i:
            place(clone(f"{name}-{i + 1}"), theta, False)
        else:
            place(layer, theta, False)
        if mirror:
            place(clone(f"{name}-{i + 1}-mirror"), theta, True)
    # The original keeps its own name; put everything under one group so it moves as a whole.
    if grouped:
        label = op.get("name") or f"{name}-radial"
        apply(project, {"type": "group", "name": label, "targets": members})
        project.layer(label)["radial"] = {"count": count, "center": [round(cx, 2), round(cy, 2)], "sweep": sweep,
                                          "start_angle": start, "mirror": mirror}
    elif op.get("name"):
        raise VixlError("invalid_operation", "name names the group; set group to true or omit name", field="name")


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    def coordinate(value):
        return value if value == "center" or value.endswith("%") else float(value)

    p = Parser(prog="vixl radial-repeat", description="Copies of a layer around a center (mandalas, rosettes)")
    p.add_argument("target")
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--cx", type=coordinate, help="center x: pixels, 'center' or N%% (default the canvas center)")
    p.add_argument("--cy", type=coordinate, help="center y")
    p.add_argument("--sweep", type=float, help="degrees covered (default 360)")
    p.add_argument("--start-angle", type=float)
    p.add_argument("--mirror", action="store_true", default=None, help="add a mirrored copy of each")
    p.add_argument("--no-group", dest="group", action="store_false", default=None)
    p.add_argument("--name")
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
