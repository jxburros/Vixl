"""Fixed-size interchangeable template containers with validated local layouts."""

from copy import deepcopy

from .errors import require
from .model import finite, new_layer, Limits

TYPES = ("container-place", "container-swap", "container-reflow", "shape-place")
CONTENT = {"text", "solid", "gradient", "shape", "pen"}


def validate(value):
    from .schema import validate_operation
    from .resources import substitute
    from .interfaces import service_check
    from .automation import bounded_object

    bounded_object(
        value,
        {"width", "height", "operations", "rules", "defaults", "description"},
        "Unknown container field",
    )
    Limits().size(value["width"], value["height"])
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
        operation = validate_operation(op)
        service_check(operation)
        require(not operation.get("target"), "Container content cannot target existing layers")
        name = operation.get("name", operation["type"])
        require(name not in names, "Container layer names must be unique")
        names.add(name)


def schemas(add):
    from .schema import S, COORD

    obj = {"type": "object"}
    add(
        "container-place",
        {"name": S, "resource": S, "x": COORD, "y": COORD, "variables": obj},
        ["name", "resource"],
    )
    add("container-reflow", {}, ["target"])
    add("container-swap", {"resource": S, "variables": obj}, ["target", "resource"])
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
            apply(project, {"type": "resize", **{k: op[k] for k in ("width", "height") if k in op}})
        return
    item = get("containers", op["resource"], workspace=workspace)
    width, height = item["width"], item["height"]
    if op["type"] == "container-swap":
        group = project.layer(op["target"])
        require(group["type"] == "group" and "container" in group, "Target must be a template container")
        require(
            [width, height] == group["container"]["size"], "Replacement container must have the same size"
        )
        ids = descendants(project, group["id"])
        # Referenced children require explicit repair before swapping, rather than dangling IDs.
        for layer in project.state["layers"]:
            if layer["id"] not in ids:
                require(
                    layer.get("clip") not in ids, "Container children are referenced outside the container"
                )
        project.state["layers"] = [x for x in project.state["layers"] if x["id"] not in ids]
        for ident in ids:
            project.state.get("blanks", {}).pop(ident, None)
    else:
        group = new_layer(op["name"], "group", width, height, x=op.get("x", 0), y=op.get("y", 0))
        append_layer(project, group)
    group.update(
        content_width=width,
        content_height=height,
        container={
            "resource": op["resource"],
            "size": [width, height],
            "rules": deepcopy(item.get("rules", {})),
        },
    )
    variables = {**item.get("defaults", {}), **op.get("variables", {})}
    rules = item.get("rules", {})
    padding, gap = rules.get("padding", 0), rules.get("gap", 0)
    layout, cursor = rules.get("layout", "free"), padding
    columns = rules.get("columns", 2)
    ops = substitute(item["operations"], variables)
    budget = getattr(project, "_resource_budget", project.limits.max_operations) - len(ops)
    require(budget >= 0, "Container expansion exceeds operation limit", "resource_limit")
    project._resource_budget = budget
    children = []
    for index, operation in enumerate(ops):
        operation["name"] = group["name"] + "/" + operation.get("name", operation["type"])
        apply(project, operation)
        layer = project.layer()
        layer["parent"] = group["id"]
        if layout in ("vertical", "horizontal"):
            layer["x"], layer["y"] = (padding, cursor) if layout == "vertical" else (cursor, padding)
            cursor += layer["height" if layout == "vertical" else "width"] + gap
        elif layout == "grid":
            rows = (len(ops) + columns - 1) // columns
            cell_w, cell_h = (
                (width - 2 * padding - (columns - 1) * gap) / columns,
                (height - 2 * padding - (rows - 1) * gap) / rows,
            )
            require(cell_w > 0 and cell_h > 0, "Grid has no usable area")
            layer["x"] = padding + (index % columns) * (cell_w + gap)
            layer["y"] = padding + (index // columns) * (cell_h + gap)
            require(
                layer["width"] <= cell_w and layer["height"] <= cell_h, "Content exceeds container grid cell"
            )
        if rules.get("contain", True):
            require(
                layer["x"] >= padding
                and layer["y"] >= padding
                and layer["x"] + layer["width"] <= width - padding
                and layer["y"] + layer["height"] <= height - padding,
                "Content exceeds container bounds or padding",
            )
        if layer["type"] == "text":
            for key, value in item.get("defaults", {}).items():
                if (
                    key not in op.get("variables", {})
                    and isinstance(value, str)
                    and value.startswith("[")
                    and value.endswith("]")
                    and value in layer["text"]
                ):
                    project.state.setdefault("blanks", {})[layer["id"]] = {
                        "slot": key,
                        "text": layer["text"],
                        "hint": f"Fill {group['name']} variable {key}",
                        "source": f"container:{op['resource']}",
                    }
        children.append(layer["id"])
    project.state["active_layer"] = group["id"]
    project.state.setdefault("containers", {})[group["id"]] = {
        "resource": op["resource"],
        "children": children,
    }


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
    return containers, templates


def measure(project, target=None):
    """Audit container rules after edits; changing artwork never changes its expectations."""
    from .render import resolve_layout

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
    violations = []
    for group in groups:
        width, height = group["container"]["size"]
        rules = group["container"]["rules"]
        padding, gap = rules.get("padding", 0), rules.get("gap", 0)
        children = [layer for layer in project.state["layers"] if layer.get("parent") == group["id"]]
        if len(children) > rules.get("max_items", 100):
            violations.append({"container": group["name"], "rule": "max_items"})
        layout, cursor = rules.get("layout", "free"), padding
        columns = rules.get("columns", 2)
        rows = max(1, (len(children) + columns - 1) // columns)
        for index, layer in enumerate(children):
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
    rules = group["container"]["rules"]
    width, height = group["container"]["size"]
    layout, padding, gap = rules.get("layout", "free"), rules.get("padding", 0), rules.get("gap", 0)
    children = [layer for layer in project.state["layers"] if layer.get("parent") == group["id"]]
    cursor, columns = padding, rules.get("columns", 2)
    rows = max(1, (len(children) + columns - 1) // columns)
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
        report["passed"], "Reflow cannot satisfy container rules; resize or fit content first", report=report
    )
