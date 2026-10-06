"""Fixed-size interchangeable template containers with validated local layouts."""

from copy import deepcopy

from .errors import require
from .model import finite, new_layer, Limits
from .stacks import collapsed

TYPES = ("container-place", "container-swap", "container-variant", "container-fill", "container-reflow", "shape-place", "image-slot")
CONTENT = {"text", "solid", "gradient", "shape", "pen", "image-slot"}


def validate(value):
    from .schema import validate_operation
    from .resources import substitute
    from .interfaces import service_check
    from .automation import bounded_object

    bounded_object(
        value,
        {"width", "height", "min_width", "max_width", "min_height", "max_height", "operations", "rules", "defaults", "description", "variants", "safe", "slots", "category", "default_variant"},
        "Unknown container field",
    )
    Limits().size(value["width"], value["height"])
    for axis in ("width", "height"):
        lo, hi = value.get("min_" + axis, value[axis]), value.get("max_" + axis, value[axis])
        require(type(lo) is int and type(hi) is int and 1 <= lo <= value[axis] <= hi <= 16384, "Invalid container size bounds")
    variants = value.get("variants", {})
    require(isinstance(variants, dict) and len(variants) <= 20, "Invalid container variants")
    for name, variant in variants.items():
        require(isinstance(name, str) and isinstance(variant, dict) and set(variant) <= {"operations", "rules"}, "Invalid variant")
        validate({**value, **variant, "variants": {}})
    rules = value.get("rules", {})
    bounded_object(
        rules, {"layout", "padding", "gap", "columns", "max_items", "contain"}, "Unknown container rule"
    )
    require(
        rules.get("layout", "free") in ("free", "vertical", "horizontal", "grid"), "Unknown container layout"
    )
    for key in ("padding", "gap"):
        finite(rules.get(key, 0), key, 0, min(value["width"], value["height"]) / 2)
    for key in ("columns", "max_items"):
        n = rules.get(key, 1 if key == "columns" else 100)
        require(type(n) is int and 1 <= n <= 100, f"Invalid {key}")
    require(type(rules.get("contain", True)) is bool, "contain must be boolean")
    require(isinstance(value.get("defaults", {}), dict), "Container defaults must be an object")
    ops = value.get("operations")
    require(
        isinstance(ops, list) and 0 < len(ops) <= rules.get("max_items", 100), "Container item limit exceeded"
    )
    names = set()
    for op in substitute(ops, value.get("defaults", {})):
        require(
            op.get("type") in CONTENT,
            "Container content must be self-contained text, shape, pen, solid or gradient",
        )
        if "frame" in op:
            frame = op["frame"]
            require(isinstance(frame, list) and len(frame) == 4, "Container frame needs four fractions")
            for fraction in frame:
                finite(fraction, "frame fraction", 0, 1)
            require(frame[2] > 0 and frame[3] > 0 and frame[0] + frame[2] <= 1.001 and frame[1] + frame[3] <= 1.001, "Container frame exceeds bounds")
        if "fit_text" in op:
            require(op["type"] == "text" and op["fit_text"] in (True, False, "wrap", "shrink"), "fit_text must be wrap, shrink or boolean on text")
        if "min_size" in op:
            finite(op["min_size"], "min_size", 1, 4096)
        operation = validate_operation({k: v for k, v in op.items() if k not in ("frame", "fit_text", "min_size")})
        service_check(operation)
        require(not operation.get("target"), "Container content cannot target existing layers")
        name = operation.get("name", operation["type"])
        require(name not in names, "Container layer names must be unique")
        names.add(name)


def schemas(add):
    from .schema import S, COORD
    register = add
    descriptions = {
        "container-variant": "Switch a container arrangement while preserving its filled slots.",
        "container-fill": "Fill container text and image slots and reflow their layout.",
        "image-slot": "Create an editable image placeholder or fit an embedded image into a shaped slot.",
    }
    fields = {"variant": "Named arrangement from the container resource; omitted choices are seeded.",
              "slot": "Semantic image slot name used by variables and checks.",
              "fit": "cover crops, contain letterboxes, and fill stretches to the slot.",
              "focal": "Subject position as [x, y] fractions in the source image.",
              "mask_shape": "Shape silhouette for the crop, including circle and rounded aliases.",
              "seed": "32-bit integer for reproducible choice, or random; omitted values use a fresh seed."}
    def add(kind, properties=None, required=(), **extra):
        properties = {k: {**v, "description": v.get("description", fields.get(k, k.replace("_", " ").capitalize() + " for this container or slot."))} for k,v in (properties or {}).items()}
        register(kind, properties, required, **({"description": descriptions[kind]} if kind in descriptions else {}), **extra)

    from .schema import SIZE, enum
    obj = {"type": "object"}
    common = {"variables": obj, "variant": S, "width": SIZE, "height": SIZE,
              "seed": {"type": ["integer", "string"]}}
    add(
        "container-place",
        {"name": S, "resource": S, "x": COORD, "y": COORD, **common},
        ["name", "resource"],
    )
    add("container-reflow", {}, ["target"])
    add("container-swap", {"resource": S, **common}, ["target", "resource"])
    add("container-variant", common, ["target", "variant"])
    add("container-fill", {"variables": obj}, ["target", "variables"])
    add("image-slot", {"name": S, "slot": S, "asset": S, "x": COORD, "y": COORD,
                       "width": SIZE, "height": SIZE, "fit": enum("cover", "contain", "fill"),
                       "focal": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1}, "minItems": 2, "maxItems": 2},
                       "mask_shape": S, "radius": {"type": "number", "minimum": 0}}, ["name", "width", "height"])
    add(
        "shape-place",
        {
            "resource": S,
            "name": S,
            "x": COORD,
            "y": COORD,
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
            "fill": S,
            "stroke": S,
        },
        ["resource", "name"],
    )


def execute(project, op):
    from .resources import get, substitute
    from .operations import execute as apply, append_layer
    from .design import descendants

    if op["type"] == "container-reflow":
        return reflow(project, op["target"])
    workspace = getattr(project, "_workspace", None)
    if op["type"] == "shape-place":
        item = get("shapes", op["resource"], workspace=workspace)
        operation = {**item, **{k: v for k, v in op.items() if k in ("name", "x", "y", "fill", "stroke")}}
        apply(project, operation)
        if "width" in op or "height" in op:
            # A library shape given one dimension keeps its proportions.
            apply(project, {"type": "resize", "keep_aspect": ("width" in op) != ("height" in op),
                            **{k: op[k] for k in ("width", "height") if k in op}})
        return
    if op["type"] == "image-slot":
        return image_slot(project, op)
    changing = op["type"] in ("container-swap", "container-variant", "container-fill")
    group = project.layer(op["target"]) if changing else None
    if changing:
        require(group["type"] == "group" and "container" in group, "Target must be a template container")
    previous = deepcopy(group["container"]) if group else {}
    resource = op.get("resource", previous.get("resource"))
    item = get("containers", resource, workspace=workspace)
    width, height = (op.get(k, previous.get("size", [item["width"], item["height"]])[i]) for i, k in enumerate(("width", "height")))
    if changing and "width" not in op and "height" not in op and resource != previous.get("resource"):
        require([item["width"], item["height"]] == previous.get("base_size", previous["size"]), "Replacement container must have the same size")
    size_bounds(item, width, height)
    from .variety import seed_for
    import random
    seed, _ = seed_for(project, op.get("seed", previous.get("seed")))
    choices = list(item.get("variants", {}))
    variant = op.get("variant", previous.get("variant") if previous.get("resource") == resource else None)
    direction = project.state.get("design_defaults", {}).get("direction", {})
    if variant is None and op.get("seed") is None and direction.get("container_variant") in choices:
        variant = direction["container_variant"]
    variant = variant or (random.Random(seed).choice(choices) if choices else "default")
    require(variant == "default" or variant in item.get("variants", {}), "Unknown container variant")
    selected = {**item, **item.get("variants", {}).get(variant, {})}
    edited = {}
    if group:
        for child in project.state["layers"]:
            if child.get("parent") == group["id"] and child.get("container_variable"):
                edited[child["container_variable"]] = child.get("text", child.get("image_slot", {}).get("source", ""))
    variables = {**item.get("defaults", {}), **previous.get("variables", {}), **edited, **op.get("variables", {})}
    if changing:
        ids = descendants(project, group["id"])
        for layer in project.state["layers"]:
            if layer["id"] not in ids:
                require(layer.get("clip") not in ids, "Container children are referenced outside the container")
        project.state["layers"] = [x for x in project.state["layers"] if x["id"] not in ids]
        for ident in ids:
            project.state.get("blanks", {}).pop(ident, None)
    else:
        group = new_layer(op["name"], "group", width, height, x=op.get("x", 0), y=op.get("y", 0))
        append_layer(project, group)
    group.update(width=width, height=height, content_width=width, content_height=height,
                 container={"resource": resource, "size": [width, height], "base_size": [item["width"], item["height"]],
                            "rules": deepcopy(selected.get("rules", {})), "variables": variables, "variant": variant,
                            "seed": seed, "bounds": {k: item[k] for k in ("min_width", "max_width", "min_height", "max_height") if k in item}})
    ops = substitute(selected["operations"], variables)
    budget = getattr(project, "_resource_budget", project.limits.max_operations) - len(ops)
    require(budget >= 0, "Container expansion exceeds operation limit", "resource_limit")
    project._resource_budget = budget
    children = []
    for original, operation in zip(selected["operations"], ops):
        operation = deepcopy(operation)
        local_name = operation.get("name", operation["type"])
        spec = {k: operation.pop(k) for k in ("frame", "fit_text", "min_size") if k in operation}
        operation["name"] = group["name"] + "/" + local_name
        if operation["type"] == "text" and spec.get("fit_text"):
            # Start from a type scale suited to the requested cell, then wrap/shrink locally.
            scale = min(width / item["width"], height / item["height"])
            operation["size"] = max(spec.get("min_size", 12), round(operation.get("size", 24) * scale))
        if operation["type"] == "image-slot":
            slot = operation.get("slot", local_name)
            operation["asset"] = variables.get(slot, operation.get("asset", ""))
        apply(project, operation)
        layer = project.layer()
        layer.update(parent=group["id"], container_local=local_name)
        template_text = original.get("text", "")
        if template_text.startswith("${") and template_text.endswith("}") and template_text.count("${") == 1:
            layer["container_variable"] = template_text[2:-1]
        elif layer.get("image_slot"):
            layer["container_variable"] = original.get("slot", local_name)
        if spec:
            layer["container_layout"] = spec
        for key, value in item.get("defaults", {}).items():
            if layer["type"] == "text" and isinstance(value, str) and value.startswith("[") and value.endswith("]") and value in layer["text"]:
                project.state.setdefault("blanks", {})[layer["id"]] = {"slot": key, "text": layer["text"], "hint": f"Fill {group['name']} variable {key}", "source": f"container:{resource}"}
        children.append(layer["id"])
    reflow(project, group["id"])
    project.state["active_layer"] = group["id"]
    project.state.setdefault("containers", {})[group["id"]] = {"resource": resource, "children": children}


def size_bounds(item, width, height):
    Limits().size(width, height, vector=True)
    for key, value in (("width", width), ("height", height)):
        if "min_" + key in item or "max_" + key in item:
            require(item.get("min_" + key, 1) <= value <= item.get("max_" + key, 16384), f"Container {key} exceeds min/max bounds")


def image_slot(project, op):
    """Embed a source once, retaining its identity and crop recipe for later resizing."""
    from pathlib import Path
    from .assets import add_encoded, read_bounded
    from .operations import append_layer
    w, h = op["width"], op["height"]
    layer = new_layer(op["name"], "raster", w, h, x=op.get("x", 0), y=op.get("y", 0))
    source = op.get("asset") or ""
    if source and source not in project.assets:
        require(not getattr(project, "_service", False), "Image slots in services require imported embedded assets", "forbidden")
        root = Path(getattr(project, "_workspace", None) or ".").resolve()
        path = (root / source).resolve()
        require(path.is_relative_to(root), "Image slot path escapes workspace", "forbidden")
        source, _ = add_encoded(project, read_bounded(path, project.limits.max_asset_bytes))
    layer["image_slot"] = {"slot": op.get("slot", op["name"]), "source": source,
                           "fit": op.get("fit", "cover"), "focal": op.get("focal", [0.5, 0.5]),
                           "mask_shape": op.get("mask_shape", "rectangle"), **({"radius": op["radius"]} if "radius" in op else {})}
    fit_image(project, layer)
    append_layer(project, layer)


def fit_image(project, layer):
    from PIL import Image, ImageOps, ImageChops
    from .assets import decode, add_image
    from .design_render import shape_image
    spec = layer["image_slot"]
    w, h = max(1, round(layer["width"])), max(1, round(layer["height"]))
    source = spec.get("source")
    if source:
        image = decode(project.assets[source], project.limits)
        spec["source_size"] = list(image.size)
        if spec["fit"] == "cover":
            scale = max(w / image.width, h / image.height)
            crop_w, crop_h = w / scale, h / scale
            left = max(0, min(image.width - crop_w, spec["focal"][0] * image.width - crop_w / 2))
            top = max(0, min(image.height - crop_h, spec["focal"][1] * image.height - crop_h / 2))
            image = image.resize((w, h), Image.Resampling.LANCZOS, box=(left, top, left + crop_w, top + crop_h))
        elif spec["fit"] == "contain":
            fit = ImageOps.contain(image, (w, h), Image.Resampling.LANCZOS)
            image = Image.new("RGBA", (w, h))
            image.alpha_composite(fit, ((w-fit.width)//2, (h-fit.height)//2))
        else:
            image = image.resize((w, h), Image.Resampling.LANCZOS)
    else:
        image = Image.new("RGBA", (w, h), "#d9dee5")
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        draw.line((0, 0, w, h), fill="#a3abb7", width=max(1, min(w, h)//100))
        draw.line((w, 0, 0, h), fill="#a3abb7", width=max(1, min(w, h)//100))
    shape = spec.get("mask_shape", "rectangle")
    shape = {"rect": "rectangle", "circle": "ellipse", "rounded": "rounded-rectangle"}.get(shape, shape)
    if shape != "rectangle":
        from .design_schema import SHAPES
        require(shape in SHAPES and shape != "path", "Unknown image mask shape")
        mask = shape_image(project, new_layer("mask", "shape", w, h, shape=shape, fill="#ffffff", stroke="transparent", stroke_width=0, radius=spec.get("radius", min(w,h)/8)))
        image.putalpha(ImageChops.multiply(image.getchannel("A"), mask.getchannel("A")))
    layer["asset"] = add_image(project, image)
    if not source:
        project.state.setdefault("blanks", {})[layer["id"]] = {"slot": spec["slot"], "asset": layer["asset"],
                                                              "hint": "Import and fill this image slot", "source": "image-slot"}
    elif project.state.get("blanks", {}).get(layer["id"], {}).get("source") == "image-slot":
        project.state["blanks"].pop(layer["id"])


def resize(project, group, op):
    """Resize the local layout box, preserving editable children and their IDs."""
    width, height = op.get("width", group["width"]), op.get("height", group["height"])
    if op.get("keep_aspect") and (("width" in op) != ("height" in op)):
        if "width" in op:
            height = round(group["height"] * width / group["width"])
        else:
            width = round(group["width"] * height / group["height"])
    size_bounds(group["container"].get("bounds", {}), width, height)
    group.update(width=width, height=height, content_width=width, content_height=height)
    group["container"]["size"] = [width, height]
    reflow(project, group["id"])


def builtins():
    containers = {}
    for name, layout, title, body in (
        ("headline-left", "vertical", "[Headline]", "[Supporting copy]"),
        ("quote-left", "vertical", "[A short quote]", "[Attribution]"),
        ("feature-left", "vertical", "[Feature]", "[One clear benefit]"),
    ):
        containers[name] = {
            "width": 480,
            "height": 320,
            "description": name.replace("-", " "),
            "rules": {"layout": layout, "padding": 32, "gap": 18, "max_items": 4},
            "defaults": {"title": title, "body": body, "ink": "@ink"},
            "operations": [
                {"type": "text", "name": "title", "text": "${title}", "size": 32, "color": "${ink}"},
                {"type": "text", "name": "body", "text": "${body}", "size": 18, "color": "${ink}"},
            ],
        }
    for name, shape in (("geometric-mark", "hexagon"), ("organic-mark", "heart"), ("badge-mark", "star")):
        containers[name] = {
            "width": 480,
            "height": 320,
            "description": "Interchangeable illustration",
            "rules": {"padding": 24},
            "defaults": {"accent": "@accent"},
            "operations": [
                {
                    "type": "shape",
                    "shape": shape,
                    "name": "mark",
                    "width": 220,
                    "height": 220,
                    "x": 130,
                    "y": 50,
                    "fill": "${accent}",
                }
            ],
        }
    templates = {}
    for name, cols, rows, choices in (
        ("modular-card", 1, 1, ["headline-left"]),
        ("modular-quote", 1, 1, ["quote-left"]),
        ("modular-logo", 1, 1, ["organic-mark"]),
        ("modular-split", 2, 1, ["headline-left", "geometric-mark"]),
        ("modular-story", 1, 3, ["headline-left", "organic-mark", "feature-left"]),
        ("modular-editorial", 2, 2, ["headline-left", "geometric-mark", "quote-left", "feature-left"]),
        (
            "modular-campaign",
            2,
            3,
            ["headline-left", "badge-mark", "feature-left", "organic-mark", "quote-left", "geometric-mark"],
        ),
        ("modular-gallery", 3, 2, ["geometric-mark", "organic-mark", "badge-mark"] * 2),
    ):
        w, h = cols * 480, rows * 320
        templates[name] = {
            "width": w,
            "height": h,
            "description": f"{'Simple' if rows * cols <= 2 else 'Complex'} interchangeable {cols}×{rows} composition",
            "suites": {"container-layout": {"rules": [{"id": "containers", "kind": "container"}]}},
            "operations": [
                {"type": "palette-apply", "name": "ocean"},
                {"type": "solid", "name": "background", "color": "@background", "width": w, "height": h},
            ]
            + [
                {
                    "type": "container-place",
                    "name": f"slot-{i + 1}",
                    "resource": resource,
                    "x": i % cols * 480,
                    "y": i // cols * 320,
                }
                for i, resource in enumerate(choices)
            ],
        }
    from .container_library import expand
    return expand(containers, templates)


def measure(project, target=None):
    """Audit container rules after edits; changing artwork never changes its expectations."""
    from .render import resolve_layout, resolved_layers
    from .checks import group_matrix
    import math

    groups = (
        [project.layer(target)]
        if target
        else [layer for layer in project.state["layers"] if "container" in layer]
    )
    require(
        groups and all(g["type"] == "group" and "container" in g for g in groups),
        "No template containers to check",
    )
    bounds = resolve_layout(project)
    resolved = {layer["id"]: layer for layer in resolved_layers(project)}
    hidden = collapsed(project)
    violations = []
    for group in groups:
        width, height = group["container"]["size"]
        rules = group["container"]["rules"]
        padding, gap = rules.get("padding", 0), rules.get("gap", 0)
        children = [layer for layer in project.state["layers"] if layer.get("parent") == group["id"]]
        if len(children) > rules.get("max_items", 100):
            violations.append({"container": group["name"], "rule": "max_items"})
        # Hidden and empty members take no space; a stack positions its members itself.
        children = [layer for layer in children if layer["id"] not in hidden]
        layout, cursor = "free" if "stack" in group else rules.get("layout", "free"), padding
        columns = rules.get("columns", 2)
        rows = max(1, (len(children) + columns - 1) // columns)
        for index, layer in enumerate(children):
            if layer.get("image_slot"):
                slot = layer["image_slot"]
                if not slot.get("source"):
                    violations.append({"container": group["name"], "target": layer["name"], "rule": "unfilled_image"})
                else:
                    matrix = group_matrix(layer, resolved, bounds)
                    scale = max(math.hypot(matrix[0, 0], matrix[1, 0]), math.hypot(matrix[0, 1], matrix[1, 1]))
                    ratio = max if slot.get("fit") == "contain" else min
                    effective = ratio(a / b for a, b in zip(slot["source_size"], (layer["width"], layer["height"]))) / max(scale, 1e-9)
                    if effective < 1:
                        violations.append({"container": group["name"], "target": layer["name"], "rule": "image_resolution", "source_size": slot["source_size"], "pixels_per_pixel": round(effective, 3)})
            x, y, w, h = bounds[layer["id"]]
            failed = []
            if rules.get("contain", True) and not (
                x >= padding and y >= padding and x + w <= width - padding and y + h <= height - padding
            ):
                failed.append("contain")
            if layout in ("horizontal", "vertical"):
                expected = (padding, cursor) if layout == "vertical" else (cursor, padding)
                if abs(x - expected[0]) > 1 or abs(y - expected[1]) > 1:
                    failed.append(layout)
                cursor += (h if layout == "vertical" else w) + gap
            if layout == "grid":
                cw, ch = (
                    (width - 2 * padding - (columns - 1) * gap) / columns,
                    (height - 2 * padding - (rows - 1) * gap) / rows,
                )
                if (
                    abs(x - padding - index % columns * (cw + gap)) > 1
                    or abs(y - padding - index // columns * (ch + gap)) > 1
                    or w > cw
                    or h > ch
                ):
                    failed.append("grid")
            for rule in failed:
                violations.append(
                    {
                        "container": group["name"],
                        "target": layer["name"],
                        "rule": rule,
                        "bounds": list(bounds[layer["id"]]),
                    }
                )
    return {"passed": not violations, "containers_checked": len(groups), "violations": violations}


def reflow(project, target):
    from .render import resolve_layout

    group = project.layer(target)
    require(group["type"] == "group" and "container" in group, "Reflow needs a template container")
    require("stack" not in group, f"{group['name']!r} is a stack, so its members follow the stack settings "
            "(change them with the stack operation)")
    rules = group["container"]["rules"]
    width, height = group["container"]["size"]
    layout, padding, gap = rules.get("layout", "free"), rules.get("padding", 0), rules.get("gap", 0)
    hidden = collapsed(project)
    # Hidden and empty members take no space, so reflow closes the gap they leave.
    children = [layer for layer in project.state["layers"]
                if layer.get("parent") == group["id"] and layer["id"] not in hidden]
    cursor, columns = padding, rules.get("columns", 2)
    rows = max(1, (len(children) + columns - 1) // columns)
    for layer in children:
        spec = layer.get("container_layout", {})
        frame = spec.get("frame")
        if frame:
            require(isinstance(frame, list) and len(frame) == 4 and all(isinstance(v, (int, float)) for v in frame), "frame must be [x,y,width,height] fractions")
            layer["x"], layer["y"] = round(frame[0] * width), round(frame[1] * height)
            layer["width"], layer["height"] = max(1, round(frame[2] * width)), max(1, round(frame[3] * height))
        if layer["type"] == "text" and spec.get("fit_text"):
            from .text import measure as text_measure, font_data
            if not frame:
                count = max(1, len(children))
                available_w, available_h = width - 2 * padding, height - 2 * padding
                if layout == "horizontal":
                    available_w = (available_w - gap * (count - 1)) / count
                elif layout == "grid":
                    available_w = (available_w - gap * (columns - 1)) / columns
                    available_h = (available_h - gap * (rows - 1)) / rows
                else:
                    available_h = (available_h - gap * (count - 1)) / count
                layer.update(width=max(1, round(available_w)), height=max(1, round(available_h)))
            maximum = layer.setdefault("container_font_size", layer["size"])
            minimum = spec.get("min_size", 12)
            size = maximum
            while True:
                _, box = text_measure(font_data(project, layer), layer["text"], size, layer.get("spacing", 0), layer.get("align", "left"), layer["width"])
                if (box[3] - box[1] <= layer["height"] and box[2] - box[0] <= layer["width"]) or size <= minimum or spec.get("fit_text") == "wrap":
                    break
                size -= 1
            require(box[3]-box[1] <= layer["height"] and box[2]-box[0] <= layer["width"], "Text cannot fit container at minimum size")
            if not frame:
                import math
                layer["height"] = max(1, math.ceil(box[3] - box[1]))
            layer.update(size=size, auto_size=False, text_layout={"width": layer["width"], "height": layer["height"]})
        if layer.get("image_slot"):
            fit_image(project, layer)
    bounds = resolve_layout(project)
    for index, layer in enumerate(children):
        require(
            not layer.get("constraints") and not layer.get("rotation") and not layer.get("pivot"),
            "Clear child constraints, rotation and pivot before container reflow",
        )
        if layout == "vertical":
            layer["x"], layer["y"] = padding, cursor
            cursor += bounds[layer["id"]][3] + gap
        elif layout == "horizontal":
            layer["x"], layer["y"] = cursor, padding
            cursor += bounds[layer["id"]][2] + gap
        elif layout == "grid":
            cw, ch = (
                (width - 2 * padding - (columns - 1) * gap) / columns,
                (height - 2 * padding - (rows - 1) * gap) / rows,
            )
            layer["x"], layer["y"] = (
                padding + index % columns * (cw + gap),
                padding + index // columns * (ch + gap),
            )
    report = measure(project, target)
    require(
        not any(v["rule"] not in ("unfilled_image", "image_resolution") for v in report["violations"]), "Reflow cannot satisfy container bounds or rules; resize or fit content first", report=report
    )
