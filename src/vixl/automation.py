"""Bounded reusable actions, role-based motion and typed recipe inputs."""

from copy import deepcopy

from .errors import require
from .model import finite

TYPES = (
    "suite-set",
    "suite-capture",
    "role-set",
    "motion-define",
    "motion-apply",
    "action-define",
    "action-apply",
    "fit-text",
    "arrange-grid",
    "adapt-layout",
    "recipe-set",
)
MACROS = {"fit-text", "arrange-grid", "adapt-layout", "motion-apply"}


def bounded_object(value, keys, message):
    require(isinstance(value, dict) and not set(value) - set(keys), message)


def validate_inputs(schema, values, *, partial=False):
    require(isinstance(schema, dict) and len(schema) <= 100, "Inputs must be a bounded object")
    require(isinstance(values, dict), "Input values must be an object")
    require(not set(values) - set(schema), "Unknown recipe inputs", fields=sorted(set(values) - set(schema)))
    result = {}
    for name, spec in schema.items():
        bounded_object(
            spec,
            {"type", "default", "required", "minimum", "maximum", "enum", "maxLength"},
            "Invalid input definition",
        )
        kind = spec.get("type", "string")
        require(kind in ("string", "number", "integer", "boolean", "asset", "color"), "Invalid input type")
        if name not in values and "default" not in spec:
            require(partial or not spec.get("required", True), f"Missing input: {name}", field=name)
            continue
        value = values.get(name, spec.get("default"))
        if kind in ("string", "asset", "color"):
            require(
                isinstance(value, str) and len(value) <= spec.get("maxLength", 100000),
                f"Invalid string input: {name}",
                field=name,
            )
            if kind == "color":
                from .render import color

                color(value)
        elif kind == "boolean":
            require(type(value) is bool, f"{name} must be boolean", field=name)
        else:
            require(type(value) in ((int,) if kind == "integer" else (int, float)), f"Invalid number: {name}")
            finite(value, name, spec.get("minimum", -1e9), spec.get("maximum", 1e9))
        require("enum" not in spec or value in spec["enum"], f"Invalid choice for {name}", field=name)
        result[name] = value
    return result


def validate_motion(value):
    bounded_object(value, {"steps", "description"}, "Invalid motion recipe")
    steps = value.get("steps")
    require(isinstance(steps, list) and 0 < len(steps) <= 100, "Motion needs 1–100 steps")
    for step in steps:
        bounded_object(
            step,
            {
                "role",
                "preset",
                "property",
                "from",
                "to",
                "start",
                "duration",
                "stagger",
                "easing",
                "amount",
                "distance",
                "after",
                "id",
            },
            "Invalid motion step",
        )
        require(isinstance(step.get("role"), str), "Motion step needs a role")
        require(("preset" in step) != ("property" in step), "Motion step needs preset or property")


def validate_action(value):
    from .schema import validate_operation
    from .interfaces import service_check

    bounded_object(value, {"operations", "description"}, "Invalid action")
    ops = value.get("operations")
    require(isinstance(ops, list) and 0 < len(ops) <= 100, "Action needs 1–100 operations")
    for op in ops:
        validated = validate_operation(op)
        service_check(validated)
        require(
            validated["type"] not in set(TYPES) - MACROS and validated["type"] != "template-apply",
            "Actions cannot change contracts, define resources or invoke other actions/templates",
        )


def validate_recipe(recipe):
    bounded_object(recipe, {"version", "inputs", "actions", "examples", "description"}, "Invalid recipe")
    require(recipe.get("version", 1) == 1, "Unsupported recipe version")
    validate_inputs(recipe.get("inputs", {}), {}, partial=True)
    require(
        isinstance(recipe.get("actions", []), list)
        and len(recipe.get("actions", [])) <= 100
        and all(isinstance(name, str) and name for name in recipe.get("actions", [])),
        "Invalid recipe actions",
    )
    examples = recipe.get("examples", [])
    require(isinstance(examples, list) and len(examples) <= 100, "Invalid recipe examples")
    for values in examples:
        validate_inputs(recipe.get("inputs", {}), values)


def validate_state(state):
    from .assurance import validate_suite
    from .design import named

    for key, validator in (
        ("suites", validate_suite),
        ("motions", validate_motion),
        ("actions", validate_action),
    ):
        items = state.get(key, {})
        require(isinstance(items, dict) and len(items) <= 100, f"Invalid {key}")
        for name, value in items.items():
            named(name)
            validator(value)
    roles = state.get("roles", {})
    require(isinstance(roles, dict) and len(roles) <= 100, "Invalid roles")
    for name, targets in roles.items():
        named(name)
        require(
            isinstance(targets, list)
            and 0 < len(targets) <= 512
            and all(isinstance(t, str) for t in targets),
            "Role needs layer identifiers",
        )
    if "recipe" in state:
        validate_recipe(state["recipe"])


def text_fits(project, layer, size, width, height, wrap=True):
    """Whether the text set at ``size`` fits ``width`` × ``height``; ``wrap=False`` measures it as
    unwrapped lines, the way text without a text-layout box is drawn."""
    from .text import measure, font_data
    from .render import document_variables, substitute

    text = substitute(layer["text"], document_variables(project))
    _, box = measure(
        font_data(project, layer),
        text,
        size,
        layer.get("spacing", 4),
        layer.get("align", "left"),
        width if wrap else None,
    )
    stroke = layer.get("stroke_width", 0) * 2
    return box[2] - box[0] + stroke <= width and box[3] - box[1] + stroke <= height


def expand(project, op):
    kind = op["type"]
    if kind == "fit-text":
        layer = project.layer(op["target"])
        require(layer["type"] == "text", "fit-text requires text")
        width, height = op["width"], op["height"]
        project.limits.size(width, height)
        low, high = op.get("minimum", 12), op.get("maximum", layer["size"])
        require(
            type(low) is int and type(high) is int and 1 <= low <= high <= 4096, "Invalid font size range"
        )
        require(
            text_fits(project, layer, low, width, height),
            "Text cannot fit at the minimum size",
            "text_overflow",
            target=layer["id"],
            minimum=low,
        )
        while low < high:
            mid = (low + high + 1) // 2
            if text_fits(project, layer, mid, width, height):
                low = mid
            else:
                high = mid - 1
        return [
            {"type": "text-set", "target": layer["id"], "size": low},
            {"type": "text-layout", "target": layer["id"], "width": width, "height": height, "fit": False},
        ]
    if kind == "arrange-grid":
        targets = op["targets"]
        require(0 < len(targets) <= 512, "Grid needs 1–512 targets")
        layers = [project.layer(t) for t in targets]
        require(len({x["id"] for x in layers}) == len(layers), "Grid targets must be unique")
        require(len({x.get("parent") for x in layers}) == 1, "Grid targets must be siblings")
        columns = op["columns"]
        require(type(columns) is int and columns > 0, "Columns must be positive")
        from .render import resolve_layout

        bounds = resolve_layout(project)
        w = max(bounds[x["id"]][2] for x in layers)
        h = max(bounds[x["id"]][3] for x in layers)
        gap = finite(op.get("gap", 24), "gap", 0, 1e6)
        return [
            {
                "type": "move",
                "target": layer["id"],
                "x": op.get("x", 0) + i % columns * (w + gap),
                "y": op.get("y", 0) + i // columns * (h + gap),
            }
            for i, layer in enumerate(layers)
        ]
    if kind == "adapt-layout":
        # Intentional, explicit policy: resize canvas, then reflow selected roles vertically.
        width, height = op["width"], op["height"]
        margin, gap = op.get("margin", 40), op.get("gap", 24)
        require(width > 2 * margin and height > 2 * margin, "Margins consume the canvas")
        targets = [project.layer(t) for t in op["targets"]]
        require(
            targets and all(not t.get("parent") for t in targets), "Adapt targets must be top-level layers"
        )
        require(len({t["id"] for t in targets}) == len(targets), "Adapt targets must be unique")
        y, ops = margin, [{"type": "canvas", "width": width, "height": height}]
        from .render import resolve_layout

        bounds = resolve_layout(project)
        for layer in targets:
            _, _, w, h = bounds[layer["id"]]
            require(w <= width - 2 * margin, "Target too wide; resize or fit text before adapting")
            require(y + h <= height - margin, "Targets cannot fit within canvas", "layout_overflow")
            ops.append({"type": "move", "target": layer["id"], "x": margin, "y": y})
            y += h + gap
        return ops
    if kind == "action-apply":
        require(op["name"] in project.state.get("actions", {}), "Unknown action")
        return deepcopy(project.state["actions"][op["name"]]["operations"])
    require(op["name"] in project.state.get("motions", {}), "Unknown motion recipe")
    recipe = project.state["motions"][op["name"]]
    from .timeline import parse_time

    scale = finite(op.get("speed", 1), "speed", 0.01, 100)
    timeline = project.state.get("timeline", {})
    markers = timeline.get("markers", {})
    offset = parse_time(op.get("start", 0), timeline.get("duration", 3000), markers)
    ends, ops = {}, []
    bindings = {**project.state.get("roles", {}), **op.get("roles", {})}
    for index, step in enumerate(recipe["steps"]):
        require(step["role"] in bindings, f"Missing motion role: {step['role']}")
        targets = bindings[step["role"]]
        targets = [targets] if isinstance(targets, str) else targets
        require(isinstance(targets, list) and 0 < len(targets) <= 512, "Invalid role binding")
        after = step.get("after")
        require(after is None or after in ends, "Motion dependencies must reference an earlier step")
        start = (ends[after] if after else offset) + parse_time(step.get("start", 0), markers=markers) / scale
        duration = max(1, round(parse_time(step.get("duration", "500ms")) / scale))
        stagger = parse_time(step.get("stagger", 0)) / scale
        for i, target in enumerate(targets):
            target = "canvas" if target == "canvas" else project.layer(target)["id"]
            result = {
                k: deepcopy(v)
                for k, v in step.items()
                if k in {"preset", "property", "from", "to", "easing", "amount", "distance"}
            }
            result.update(
                type="animate-preset" if "preset" in step else "animate",
                target=target,
                start=round(start + i * stagger),
                duration=duration,
            )
            ops.append(result)
        ident = step.get("id", str(index))
        require(ident not in ends, "Duplicate motion step ID")
        ends[ident] = start + (len(targets) - 1) * stagger + duration
    return ops


def execute(project, op):
    from .design import named

    kind = op["type"]
    if kind == "adapt-layout":
        # One verb, two behaviours: targets reflow vertically (below); without them every layer is re-laid out.
        mode = op.get("mode") or ("stack" if "targets" in op else "proportional")
        if mode == "proportional":
            require("targets" not in op and "margin" not in op and "gap" not in op,
                    "targets, margin and gap belong to mode 'stack'; proportional adapts every layer "
                    "(restrict it with where)", field="mode")
            from .adapt import execute as adapt

            return adapt(project, op)
        from .adapt import OPTIONS

        require("targets" in op and "width" in op and "height" in op,
                "mode 'stack' needs targets, width and height", field="targets")
        extra = [key for key in OPTIONS if key in op and key not in ("width", "height")]
        require(not extra, f"{', '.join(extra)} belong to mode 'proportional' (leave out targets)", field=extra[0] if extra else "mode")
    if kind in MACROS or kind == "action-apply":
        if kind == "fit-text":
            # Fitting one headline must not resize every use of a shared typography style.
            layer = project.layer(op["target"])
            for category in ("character", "paragraph"):
                name = layer.pop(category + "_style", None)
                if name:
                    layer.update(deepcopy(project.state[category + "_styles"][name]))
        from .operations import execute as apply_operation
        from .schema import validate_operation
        from .interfaces import service_check
        from .normalize import resolve_geometry, apply_centering

        operations = expand(project, op)
        remaining = getattr(project, "_resource_budget", project.limits.max_operations) - len(operations)
        require(remaining >= 0, "Expanded actions exceed operation budget", "resource_limit")
        project._resource_budget = remaining
        for operation in operations:
            operation = validate_operation(operation)
            service_check(operation)
            resolved, centered = resolve_geometry(project, operation)
            apply_operation(project, resolved)
            apply_centering(project, centered, operation)
        return
    if kind == "recipe-set":
        validate_recipe(op["recipe"])
        project.state["recipe"] = deepcopy(op["recipe"])
        return
    name = named(op["name"])
    if kind == "role-set":
        project.state.setdefault("roles", {})[name] = [project.layer(t)["id"] for t in op["targets"]]
    elif kind == "suite-capture":
        from .assurance import capture

        require(
            name not in project.state.get("suites", {}), "Baseline already exists; use suite-set explicitly"
        )
        project.state.setdefault("suites", {})[name] = capture(
            project, op.get("targets", []), op.get("regions", [])
        )
    else:
        key, field, validator = {
            "suite-set": ("suites", "suite", None),
            "motion-define": ("motions", "motion", validate_motion),
            "action-define": ("actions", "action", validate_action),
        }[kind]
        if kind == "suite-set":
            from .assurance import validate_suite

            validator = validate_suite
        validator(op[field])
        project.state.setdefault(key, {})[name] = deepcopy(op[field])


def schemas(add):
    from .schema import S, N, POSITIVE_INT
    from .workflow_schema import RECIPE, SUITE

    obj = {"type": "object"}
    targets = {"type": "array", "items": S, "minItems": 1, "maxItems": 512}
    add("suite-set", {"name": S, "suite": SUITE}, ["name", "suite"])
    add(
        "suite-capture",
        {"name": S, "targets": targets, "regions": {"type": "array", "maxItems": 100}},
        ["name"],
    )
    add("role-set", {"name": S, "targets": targets}, ["name", "targets"])
    add("motion-define", {"name": S, "motion": obj}, ["name", "motion"])
    add(
        "motion-apply",
        {"name": S, "roles": obj, "speed": N, "start": {"type": ["number", "string"]}},
        ["name"],
    )
    add("action-define", {"name": S, "action": obj}, ["name", "action"])
    add("action-apply", {"name": S}, ["name"])
    add("recipe-set", {"recipe": RECIPE}, ["recipe"])
    add(
        "fit-text",
        {"width": POSITIVE_INT, "height": POSITIVE_INT, "minimum": POSITIVE_INT, "maximum": POSITIVE_INT},
        ["target", "width", "height"],
    )
    add(
        "arrange-grid",
        {"targets": targets, "columns": POSITIVE_INT, "gap": N, "x": N, "y": N},
        ["targets", "columns"],
    )
    from .adapt import SCHEMA as adapt_fields

    add(
        "adapt-layout",
        {
            "targets": targets,
            "width": POSITIVE_INT,
            "height": POSITIVE_INT,
            "margin": {"type": "number", "minimum": 0},
            "gap": {"type": "number", "minimum": 0},
            **adapt_fields,
        },
        anyOf=[{"required": ["targets", "width", "height"]}, {"required": ["size"]}, {"required": ["width", "height"]}],
    )


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json
    from .commands import Parser

    parser = Parser(prog=f"vixl {cmd}")
    if cmd in (
        "suite-set",
        "suite-capture",
        "role-set",
        "motion-define",
        "motion-apply",
        "action-define",
        "action-apply",
    ):
        parser.add_argument("name")
    if cmd == "fit-text":
        parser.add_argument("target")
    if cmd in ("fit-text", "adapt-layout"):
        # adapt-layout needs targets (vertical reflow) or a size (proportional); the operation checks which.
        parser.add_argument("--width", type=int, required=cmd == "fit-text")
        parser.add_argument("--height", type=int, required=cmd == "fit-text")
    if cmd == "fit-text":
        parser.add_argument("--minimum", type=int, default=12)
        parser.add_argument("--maximum", type=int)
    if cmd in ("suite-capture", "role-set", "arrange-grid", "adapt-layout"):
        parser.add_argument("--targets", nargs="+", required=cmd not in ("suite-capture", "adapt-layout"))
    if cmd == "arrange-grid":
        parser.add_argument("--columns", type=int, required=True)
        parser.add_argument("--x", type=float)
        parser.add_argument("--y", type=float)
    if cmd in ("arrange-grid", "adapt-layout"):
        parser.add_argument("--gap", type=float)
    if cmd == "adapt-layout":
        parser.add_argument("--margin", type=float)
        parser.add_argument("--size", help="Proportional mode: named target size instead of --width/--height")
        parser.add_argument("--orientation", choices=["portrait", "landscape"])
        parser.add_argument("--dpi", type=float)
        parser.add_argument("--scale", type=lambda v: float(v) if v.replace(".", "", 1).isdigit() else v,
                            help="fit, fill, width, height or a factor")
        parser.add_argument("--anchors", type=json.loads, help='JSON, e.g. \'{"logo": "bottom-right"}\'')
        parser.add_argument("--where", type=json.loads, help="edit-layers selector limiting the adapted layers")
        parser.add_argument("--text", choices=["scale", "keep"])
        parser.add_argument("--no-report", dest="report", action="store_false", default=None)
    if cmd == "suite-capture":
        parser.add_argument("--regions", type=json.loads)
    if cmd == "motion-apply":
        parser.add_argument("--roles", type=json.loads)
        parser.add_argument("--speed", type=float)
        parser.add_argument("--start")
    if cmd in ("suite-set", "motion-define", "action-define", "recipe-set"):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--settings", type=json.loads)
        source.add_argument("--file", help="Read reusable settings from a JSON file")
    values = {k: v for k, v in vars(parser.parse_args(args)).items() if v is not None}
    if "file" in values:
        from .assets import read_bounded
        values["settings"] = json.loads(read_bounded(values.pop("file"), 1024 * 1024))
    if "settings" in values:
        field = {
            "suite-set": "suite",
            "motion-define": "motion",
            "action-define": "action",
            "recipe-set": "recipe",
        }[cmd]
        values[field] = values.pop("settings")
    return {"type": cmd, **values}
