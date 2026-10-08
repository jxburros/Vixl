"""Sub-pixel, anchored and affine editing operations shared by every interface."""

import math
import re
import numpy as np
from .errors import require
from .model import finite
from .affine import layer_matrix, linear, matrix
from .geometry import ANCHORS, canonical_anchor

TYPES = ("skew", "transform", "match-size", "fit", "snap-to-pixel")
VECTOR_TYPES = ("shape", "pathfinder", "text", "solid", "gradient", "group", "symbol")


def anchor(value):
    if isinstance(value, str) and canonical_anchor(value):
        value = list(ANCHORS[canonical_anchor(value)])
    require(
        isinstance(value, (list, tuple)) and len(value) == 2,
        "Anchor must be a named anchor or [x, y] fractions",
        field="anchor",
    )
    return [finite(v, "anchor", -10, 10) for v in value]


def snapped(project, layer):
    return (
        layer.get("snap_to_pixel", project.state.get("snap_to_pixel", False))
        or layer["type"] not in VECTOR_TYPES
    )


def dimension(project, layer, value):
    finite(value, "dimension", 0.000001)
    return max(1, round(value)) if snapped(project, layer) else value


def schemas(add):
    from .schema import N, S, B, enum

    anchors = {
        "anyOf": [{"enum": list(ANCHORS)}, {"type": "array", "items": N, "minItems": 2, "maxItems": 2}]
    }
    add("skew", {"x": N, "y": N, "relative": B}, anyOf=[{"required": ["x"]}, {"required": ["y"]}])
    add(
        "transform",
        {"matrix": {"type": "array", "items": N, "minItems": 6, "maxItems": 6}, "relative": B},
        ["matrix"],
    )
    add(
        "match-size",
        {
            "targets": {"type": "array", "items": S, "minItems": 1},
            "to": S,
            "axis": enum("width", "height", "both"),
            "anchor": anchors,
        },
        ["targets", "to"],
    )
    add(
        "fit",
        {
            "box": {"anyOf": [S, {"type": "array", "items": N, "minItems": 4, "maxItems": 4}]},
            "mode": enum("contain", "cover", "stretch"),
            "align": anchors,
        },
        ["box"],
    )
    add("snap-to-pixel", {"value": B, "scope": enum("layer", "document")})


def enrich_transform_schemas(variants):
    from .schema import N, B

    anchors = {
        "anyOf": [{"enum": list(ANCHORS)}, {"type": "array", "items": N, "minItems": 2, "maxItems": 2}]
    }
    descriptions = {
        "skew": "Shear a layer around its pivot with editable x/y angles in degrees; form fields are excluded.",
        "transform": "Apply an invertible affine [a,b,c,d,e,f] matrix, decomposed into editable size, rotation and shear.",
        "match-size": "Resize selected layers to the reference width, height or both.",
        "fit": "Scale and align a layer into a canvas-space box or another layer, preserving aspect in contain/cover modes.",
        "snap-to-pixel": "Enable or disable pixel snapping for one layer or the document default.",
    }
    fields = {
        "x": "Horizontal shear in degrees (-89 to 89).",
        "y": "Vertical shear in degrees (-89 to 89).",
        "relative": "Add to the current shear or compose the matrix with the current transform.",
        "matrix": "Six affine coefficients [a,b,c,d,e,f]; x′=ax+cy+e, y′=bx+dy+f. Must be invertible.",
        "targets": "Layer names or IDs to resize.",
        "to": "Reference layer name or ID.",
        "axis": "Match width, height, or both (default).",
        "anchor": "Point kept fixed in parent/canvas space, as a named anchor or [x,y] fractions.",
        "box": "Canvas-space [x,y,width,height] or a reference layer name/ID.",
        "mode": "contain fits inside; cover fills with overflow; stretch changes the aspect ratio.",
        "align": "Placement within the box, as a named anchor or fractions; default center.",
        "scope": "layer (default) sets an override; document changes the default.",
        "value": "Whether to snap coordinates and scaled dimensions to pixels; default true.",
        "absolute": "Alias for space: canvas; space takes precedence.",
        "step": "Multiplier for x/y move values, useful with relative nudges (for example 0.25 or 10).",
    }
    for variant in variants:
        kind, props = variant["properties"]["type"]["const"], variant["properties"]
        if kind in descriptions:
            variant["description"] = descriptions[kind]
            for key, prop in list(props.items()):
                if key in fields and "description" not in prop:
                    props[key] = {**prop, "description": fields[key]}
        if kind in ("resize", "scale"):
            props["anchor"] = {**anchors, "description": fields["anchor"]}
        if kind == "resize":
            for key in ("width", "height"):
                props[key] = {
                    "anyOf": [props[key], {"type": "string", "pattern": r"^[+-]\d+(?:\.\d+)?%?$"}],
                    "description": "Pixels, unsigned canvas/parent percentage, or a signed delta relative to current size (+8, -5%).",
                }
        if kind == "move":
            props.update(
                space={
                    "enum": ["parent", "canvas"],
                    "description": "Default parent: grouped coordinates are relative to the parent. Canvas uses document coordinates.",
                },
                absolute={**B, "description": fields["absolute"]},
                step={"type": "number", "exclusiveMinimum": 0, "description": fields["step"]},
            )


def _relative(value, current):
    if isinstance(value, str) and re.fullmatch(r"[+-]\d+(?:\.\d+)?%?", value):
        return current + float(value.rstrip("%")) * (current / 100 if value.endswith("%") else 1)
    return value


def execute(project, op):
    from .render import layer_box, resolve_layout, stored_origin

    kind = op["type"]
    if kind == "match-size":
        ref = project.layer(op["to"])
        dimensions = {key: ref[key] for key in ("width", "height") if op.get("axis", "both") in ("both", key)}
        for target in op["targets"]:
            execute(
                project,
                {
                    "type": "resize",
                    "target": target,
                    **dimensions,
                    "keep_aspect": False,
                    "anchor": op.get("anchor", "top-left"),
                },
            )
        return
    if kind == "snap-to-pixel" and op.get("scope") == "document":
        project.state["snap_to_pixel"] = op.get("value", True)
        return
    layer = project.layer(op.get("target"))
    if kind == "snap-to-pixel":
        layer["snap_to_pixel"] = op.get("value", True)
        if layer["snap_to_pixel"]:
            for key in ("x", "y", "width", "height"):
                layer[key] = max(1, round(layer[key])) if key in ("width", "height") else round(layer[key])
        return
    box = layer_box(project, layer)
    if kind == "move":
        space = op.get("space", "canvas" if op.get("absolute") else "parent")
        origin = np.array(box[:2], dtype=float)
        parent_matrix = np.eye(3)
        if space == "canvas":
            from .checks import group_matrix
            from .render import resolved_layers

            index = {v["id"]: v for v in resolved_layers(project)}
            parent_matrix = group_matrix(index[layer["id"]], index, resolve_layout(project))
            from .spatial import canvas_boxes

            origin = np.array(canvas_boxes(project)[layer["id"]][:2])
        destination = origin.copy()
        for i, key in enumerate(("x", "y")):
            if key in op:
                value = finite(op[key], key) * op.get("step", 1)
                destination[i] = origin[i] + value if op.get("relative") else value
        delta = np.linalg.inv(parent_matrix) @ [*(destination - origin), 0]
        layer["x"], layer["y"] = stored_origin(layer, (box[0] + delta[0], box[1] + delta[1]))
        if snapped(project, layer):
            layer["x"], layer["y"] = round(layer["x"]), round(layer["y"])
        layer["constraints"] = {}
        return
    if kind in ("skew", "transform"):
        require(layer["type"] != "field", "PDF form fields are upright rectangles", field="target")
        if kind == "skew":
            fixed = layer.get("pivot", [0.5, 0.5])
            before = layer_matrix(layer, box) @ [fixed[0] * layer["width"], fixed[1] * layer["height"], 1]
            # Freeze the currently resolved pose before introducing the implicit center pivot.
            # Otherwise a previously rotated layer jumps back to its unrotated-box center.
            layer["x"], layer["y"] = stored_origin(layer, box)
            layer["constraints"] = {}
            layer.setdefault("pivot", [0.5, 0.5])
            for axis in ("x", "y"):
                if axis in op:
                    key = "skew_" + axis
                    value = finite(op[axis], key) + (layer.get(key, 0) if op.get("relative") else 0)
                    layer[key] = finite(value, key, -89, 89)
            require(abs(np.linalg.det(linear(layer))) > 1e-8, "Skew must not collapse the layer")
            after_box = layer_box(project, layer)
            after = layer_matrix(layer, after_box) @ [
                fixed[0] * layer["width"],
                fixed[1] * layer["height"],
                1,
            ]
            layer["x"], layer["y"] = stored_origin(
                layer, (after_box[0] + before[0] - after[0], after_box[1] + before[1] - after[1])
            )
        else:
            values = [finite(v, "matrix") for v in op["matrix"]]
            m = matrix(*values)
            require(abs(np.linalg.det(m)) > 1e-8, "Transform matrix must be invertible", field="matrix")
            if op.get("relative"):
                m = m @ linear(layer)
            # QR decomposition stores an editable rotation, x shear and dimensions.
            a, b, c, d, e, f = m[0, 0], m[1, 0], m[0, 1], m[1, 1], m[0, 2], m[1, 2]
            sx = math.hypot(a, b)
            sy = (a * d - b * c) / sx
            layer["rotation"] = math.degrees(math.atan2(b, a)) % 360
            layer["skew_x"] = math.degrees(math.atan((a * c + b * d) / (sx * sy)))
            layer["skew_y"] = 0
            layer["flip_x"], layer["flip_y"] = False, sy < 0
            layer["width"] = dimension(project, layer, layer["width"] * sx)
            layer["height"] = dimension(project, layer, layer["height"] * abs(sy))
            layer["auto_size"] = False
            layer.pop("affine", None)
            layer["x"] += e
            layer["y"] += f
        return
    if kind == "fit":
        from .spatial import canvas_boxes

        region = (
            canvas_boxes(project)[project.layer(op["box"])["id"]] if isinstance(op["box"], str) else op["box"]
        )
        x, y, w, h = region
        require(w > 0 and h > 0, "Fit box dimensions must be positive", field="box")
        mode = op.get("mode", "contain")
        align = anchor(op.get("align", "center"))
        # Solve transformed bounding size, including the inherited scale/rotation of groups.
        from .checks import group_matrix
        from .render import resolved_layers

        index = {v["id"]: v for v in resolved_layers(project)}
        parent = group_matrix(index[layer["id"]], index, resolve_layout(project))
        coeff = np.abs((parent @ linear(layer))[:2, :2])
        current = coeff @ [layer["width"], layer["height"]]
        if mode == "stretch":
            require(
                abs(np.linalg.det(coeff)) > 1e-8,
                "Stretch is ambiguous at this rotation; use contain or cover",
            )
            sizes = np.linalg.solve(coeff, [w, h])
        else:
            factor = (min if mode == "contain" else max)(w / current[0], h / current[1])
            sizes = np.array([layer["width"], layer["height"]]) * factor
        execute(
            project,
            {"type": "resize", "target": layer["id"], "width": float(sizes[0]), "height": float(sizes[1])},
        )
        result = canvas_boxes(project)[layer["id"]]
        execute(
            project,
            {
                "type": "move",
                "target": layer["id"],
                "space": "canvas",
                "x": x + (w - result[2]) * align[0],
                "y": y + (h - result[3]) * align[1],
            },
        )
        return
    w, h = layer["width"], layer["height"]
    fixed = anchor(op.get("anchor", "top-left"))
    before = layer_matrix(layer, box) @ [fixed[0] * w, fixed[1] * h, 1]
    if kind == "scale":
        fx, fy = op.get("x", op.get("value", 1)), op.get("y", op.get("value", 1))
        for factor in (fx, fy):
            finite(factor, "scale")
            require(0.001 <= abs(factor) <= 100, "Scale magnitude must be 0.001–100")
        require(layer["type"] != "field" or (fx > 0 and fy > 0), "PDF form fields cannot be mirrored")
        if fx < 0:
            layer["flip_x"] = not layer["flip_x"]
        if fy < 0:
            layer["flip_y"] = not layer["flip_y"]
        nw, nh = w * abs(fx), h * abs(fy)
    else:
        nw, nh = _relative(op.get("width", w), w), _relative(op.get("height", h), h)
        one = ("width" in op) != ("height" in op)
        require(one or not op.get("keep_aspect"), "keep_aspect requires exactly one dimension")
        if one and op.get("keep_aspect", layer["type"] == "raster"):
            if "width" in op:
                nh = h * nw / w
            else:
                nw = w * nh / h
    nw, nh = dimension(project, layer, nw), dimension(project, layer, nh)
    project.limits.size(nw, nh, vector=True)
    if layer.get("container") and kind == "resize":
        from .containers import resize

        resize(project, layer, {**op, "width": nw, "height": nh, "keep_aspect": False})
    else:
        layer.update(width=nw, height=nh, auto_size=False)
    if "anchor" in op:
        after_box = layer_box(project, layer)
        after = layer_matrix(layer, after_box) @ [fixed[0] * nw, fixed[1] * nh, 1]
        layer["x"], layer["y"] = stored_origin(
            layer, (after_box[0] + before[0] - after[0], after_box[1] + before[1] - after[1])
        )
        layer["constraints"] = {}
