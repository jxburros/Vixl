"""Creation operations aimed at an existing layer edit it in place instead of adding one.

``shape``, ``solid``, ``gradient`` and ``text`` normally add a layer. Given a ``target`` of the same
kind they change that layer's fill, stroke, colours, text or geometry, so its ID, stacking order,
effects, masks and constraints stay put. A target of another kind, or a ``target`` on an operation
that can only create (``add``, ``frame``, ``adjustment``, ``symbol-instance``), is an error that
names the operation to use, never a silent new layer.
"""

from copy import deepcopy

from .errors import VixlError, require
from .shape_catalog import PARAMETERS as CATALOG_FIELDS
from .vector_strokes import FIELDS as STROKE_FIELDS

# Operation type -> the layer type it creates and edits.
EDITS = {"shape": "shape", "solid": "solid", "gradient": "gradient", "text": "text"}
CREATE_ONLY = {
    "add": "add imports a new image layer. To swap the image of an existing layer use replace-contents; "
    "to move or scale it use move, resize or scale",
    "frame": "frame adds a new image frame. To swap the picture of an existing frame use replace-contents; "
    "to move or scale it use move, resize or scale",
    "adjustment": "adjustment adds a new adjustment layer. To change an existing adjustment layer's effects use "
    "effect, effect-set or effect-remove with target",
    "symbol-instance": "symbol-instance adds a new instance of a symbol. To change an existing instance use "
    "move, resize, rotate or opacity with target",
}
IN_PLACE_TYPES = (*EDITS, *CREATE_ONLY)
USE_INSTEAD = {
    "text": ("text-set", "change text, size, color, font or alignment with text-set (or text with target)"),
    "shape": ("shape", "change fill, stroke or geometry with shape and target"),
    "solid": ("solid", "change the color or size with solid and target"),
    "gradient": ("gradient", "change colors, stops or direction with gradient and target"),
    "raster": ("replace-contents", "swap the image with replace-contents; adjust it with effect, opacity, resize"),
    "frame": ("replace-contents", "swap the picture with replace-contents; adjust it with move or resize"),
    "group": ("layer-style", "style or move the group with layer-style, opacity, move or resize, or edit its "
              "children by name"),
    "pathfinder": ("layer-style", "style it with layer-style or opacity, or move or resize it"),
    "adjustment": ("effect-set", "change its effects with effect-set, effect-remove or effect"),
    "field": ("field-set", "change the form field with field-set"),
}

SHAPE_FIELDS = (*CATALOG_FIELDS, *STROKE_FIELDS, "shape", "path", "fill", "stroke", "stroke_width", "radius", "sides", "inner_radius", "start_angle", "end_angle", "trim_start", "trim_end")
TEXT_FIELDS = ("text", "size", "color", "align", "spacing", "font", "hide_if_empty")


def target_schema(kind):
    """The ``target`` property for a creation operation: it edits a layer of the same kind."""
    return {
        "type": "string",
        "description": f"Layer ID or name of an existing {EDITS[kind]} layer to edit in place (same ID, order and "
        "effects) instead of adding a new layer; only the fields you pass change.",
    }


def wrong_target(kind, layer):
    """The error for aiming ``kind`` at a layer it cannot edit, naming what to use instead."""
    if kind in CREATE_ONLY:
        return VixlError(
            "invalid_operation",
            f"{CREATE_ONLY[kind]}; omit target to add a new layer",
            field="target",
            suggestions=["replace-contents" if kind in ("add", "frame") else "effect-set"],
        )
    fallback = (None, "see vixl_operation_schema for the operations that edit it")
    operation, advice = USE_INSTEAD.get(layer["type"], fallback)
    return VixlError(
        "invalid_operation",
        f"{kind} with a target edits an existing {EDITS[kind]} layer, but {layer['name']!r} is a "
        f"{layer['type']} layer: {advice}. Omit target to add a new {EDITS[kind]} layer",
        field="target",
        suggestions=[operation] if operation else [],
    )


def execute(project, op):
    from .operations import execute as apply, unique_name

    kind = op["type"]
    layer = project.layer(op["target"])
    if kind in CREATE_ONLY or layer["type"] != EDITS[kind]:
        raise wrong_target(kind, layer)
    ident = layer["id"]
    if kind == "shape":
        for key in SHAPE_FIELDS:
            if key in op:
                layer[key] = deepcopy(op[key])
        width, height = op.get("width", layer["width"]), op.get("height", layer["height"])
        if "path" in op:
            layer["path_view"] = [width, height]
        require(layer["shape"] != "path" or layer.get("path"), "A path shape needs a path", field="path")
    elif kind == "solid":
        if "color" in op:
            layer["fill"] = op["color"]
    elif kind == "gradient":
        edit_gradient(layer, op)
    else:
        fields = {key: op[key] for key in TEXT_FIELDS if key in op}
        if fields:
            apply(project, {"type": "text-set", "target": ident, **fields})
    if kind != "text" and ("width" in op or "height" in op):
        width, height = op.get("width", layer["width"]), op.get("height", layer["height"])
        project.limits.size(width, height, vector=True)
        layer.update(width=width, height=height)
    centered = {axis: True for axis in ("x", "y") if op.get(axis) == "center"}
    position = {axis: op[axis] for axis in ("x", "y") if axis in op and axis not in centered}
    if position:
        space = {"space": op["space"]} if "space" in op else {}  # canvas: x/y in document coordinates
        apply(project, {"type": "move", "target": ident, **position, **space})
    if centered:
        from .normalize import apply_centering

        apply_centering(project, centered, op)
    if "within" in op:
        from .guides import place_within

        require(not {"x", "y"} & set(op), "within positions the text; drop x and y (or use place with within "
                "and an anchor)", field="within")
        place_within(project, ident, op["within"])
    if "name" in op and op["name"] != layer["name"]:
        layer["name"] = unique_name(project, op["name"])


def edit_gradient(layer, op):
    """Colours and direction of an existing gradient. ``start``/``end`` recolour the first and last
    stop of a multi-stop gradient, so one call recolours it however it was built."""
    for key in ("start", "end", "direction", "angle", "falloff", "center"):
        if key in op:
            layer[key] = op[key]
    if "stops" in op:
        layer["stops"] = deepcopy(op["stops"])
    elif layer.get("stops"):
        for key, stop in (("start", layer["stops"][0]), ("end", layer["stops"][-1])):
            if key in op:
                stop["color"] = op[key]
