"""Structural validation and a deliberately small assertion language (never eval)."""

import operator
from pathlib import Path
import re

from .errors import VixlError, require
from .model import finite
from .render import BLENDS, color, resolve_layout


def check_state(project, state):
    from .operations import effect_valid
    from .design import validate_design, resolve_color

    require(isinstance(state, dict), "Invalid document state", "invalid_project")
    c = state["canvas"]
    project.limits.size(c["width"], c["height"])
    require(c["color_mode"] == "rgba8", "Only RGBA8 documents are supported", "invalid_project")
    from .sizes import validate_canvas

    validate_canvas(c)
    color(resolve_color(c["background"], state))
    require(isinstance(state.get("design_guidance", {}), dict), "Invalid design guidance")
    from .resources import validate
    from .design import named
    require(isinstance(state.get("palettes", {}), dict), "Invalid palette registry")
    for name, colors in state.get("palettes", {}).items():
        named(name)
        validate("palettes", colors)
    for key, text in state.get("design_guidance", {}).items():
        named(key)
        validate("guidance", text)
    require(isinstance(state.get("fonts", {}), dict), "Invalid font registry")
    for key, asset in state.get("fonts", {}).items():
        named(key)
        require(asset in project.assets and asset.startswith("fonts/"), "Missing registered font")
    fallbacks = state.get("font_fallbacks", [])
    require(isinstance(fallbacks, list) and len(fallbacks) <= 16, "Invalid font fallback list", "invalid_project")
    require(all(isinstance(f, str) and (f in project.assets or f == "DejaVuSans.ttf") for f in fallbacks), "Fallback fonts must be embedded or bundled", "invalid_project")
    layers = state["layers"]
    require(
        isinstance(layers, list) and len(layers) <= project.limits.max_layers,
        "Invalid layer list",
        "invalid_project",
    )
    ids, names = set(), set()
    for layer in layers:
        require(
            isinstance(layer["id"], str) and isinstance(layer["name"], str) and layer["name"],
            "Invalid layer identifier",
        )
        require(
            layer["id"] not in ids and layer["name"] not in names,
            "Duplicate layer identifier",
            "invalid_project",
        )
        require(layer.get("role", "content") in ("content", "decoration", "background", "title"), "Invalid layer role", "invalid_project")
        if "pen_origin" in layer:
            origin = layer["pen_origin"]
            require(isinstance(origin, list) and len(origin) == 2, "Invalid pen origin", "invalid_project")
            for value in origin:
                finite(value, "pen origin", -1e6, 1e6)
        allowed = layer.get("allow_overlap", [])
        require(isinstance(allowed, list) and len(allowed) <= 512 and all(isinstance(x, str) for x in allowed), "Invalid overlap intent", "invalid_project")
        require(isinstance(layer.get("allow_crop", False), bool), "Invalid crop intent", "invalid_project")
        require(isinstance(layer.get("color_vision_safe", False), bool), "Invalid color vision intent", "invalid_project")
        require(isinstance(layer.get("detached_ok", False), bool), "Invalid detached intent", "invalid_project")
        ids.add(layer["id"])
        names.add(layer["name"])
        require(
            layer["type"]
            in (
                "raster",
                "text",
                "solid",
                "gradient",
                "shape",
                "group",
                "frame",
                "adjustment",
                "pathfinder",
                "symbol",
                "pixel",
                "paint",
                "field",
                "link",
            ),
            "Invalid layer type",
            "invalid_project",
        )
        from .transforms import VECTOR_TYPES
        project.limits.size(layer["width"], layer["height"], vector=layer["type"] in VECTOR_TYPES)
        for axis in ("x", "y", "rotation"):
            finite(layer[axis], axis, -1e9, 1e9)
        for axis in ("skew_x", "skew_y"):
            finite(layer.get(axis, 0), axis, -89.999999, 89.999999)
        if "snap_to_pixel" in layer:
            require(isinstance(layer["snap_to_pixel"], bool), "snap_to_pixel must be boolean")
        if "pivot" in layer:
            pivot = layer["pivot"]
            require(isinstance(pivot, list) and len(pivot) == 2, "Pivot must be [x, y] fractions of the layer box")
            for value in pivot:
                finite(value, "pivot", -10, 10)
        finite(layer["opacity"], "opacity", 0, 1)
        require(layer["blend"] in BLENDS, "Invalid blend mode")
        require(isinstance(layer["visible"], bool), "Visibility must be boolean")
        require(isinstance(layer["constraints"], dict), "Invalid constraints")
        if layer["type"] in ("raster", "frame"):
            require(layer["asset"] in project.assets, "Missing layer asset", "missing_asset")
        for key in ("color", "fill", "start", "end", "stroke_color"):
            if key in layer:
                color(resolve_color(layer[key], state))
        if layer["type"] == "pixel":
            from .pixel import validate_pixel

            validate_pixel(layer, state)
        if layer["type"] == "paint":
            from .brushes import validate_paint

            validate_paint(layer, state)
        if layer["type"] == "field":
            from .forms import validate_field

            validate_field(layer, state)
        if layer.get("code") is not None:
            from .codes import validate as validate_code

            validate_code(layer)
        if layer["type"] == "link":
            from .links import validate as validate_link

            validate_link(layer, state)
        if "chart" in layer:
            from .charts import validate_chart

            validate_chart(layer, state)
        if "drawing" in layer or "drawing_strokes" in layer:
            from .drawing import validate as validate_drawing

            validate_drawing(layer, state, project)
        if layer["type"] == "text":
            require(isinstance(layer["text"], str) and len(layer["text"]) <= 100000, "Invalid text")
            finite(layer["size"], "font size", 1, 4096)
            if "rich" in layer:
                from .richtext import validate_rich

                validate_rich(layer["rich"], state, layer["text"])
        mask = layer["mask"]
        if mask:
            require(mask["asset"] in project.assets, "Missing mask asset", "missing_asset")
        require(len(layer["effects"]) <= 256, "Too many effects", "resource_limit")
        for effect in layer["effects"]:
            effect_valid(effect)
            if effect.get("selection"):
                require(effect["selection"] in project.assets, "Missing effect selection", "missing_asset")
    validate_design(project, state)
    from .forms import validate_form

    validate_form(project, state)
    from .brushes import validate_brushes

    require(isinstance(state.get("brushes", {}), dict), "Invalid brush library")
    validate_brushes(state)
    from .animation import validate_animation

    validate_animation(project, state)
    from .timeline import validate_timeline

    validate_timeline(project, state)
    from .animation_support import validate_state as validate_animation_support

    validate_animation_support(project, state)
    from .layouts import validate_layout_record

    validate_layout_record(state)
    from .styles import validate_style_tag

    validate_style_tag(state)
    from .automation import validate_state
    validate_state(state)
    from .diagrams import validate as validate_diagrams

    validate_diagrams(state)
    from .textflow import validate as validate_flows

    validate_flows(state)
    from .pages import validate_pages

    validate_pages(project, state)
    require(not (ids & names), "Layer names cannot collide with IDs", "invalid_project")
    require(
        state["active_layer"] is None or state["active_layer"] in ids,
        "Invalid active layer",
        "invalid_project",
    )
    if state["selection"]:
        require(state["selection"] in project.assets, "Missing selection", "missing_asset")
    require(
        isinstance(state["variables"], dict) and isinstance(state["presets"], dict),
        "Invalid variables/presets",
    )


def check_document(project):
    check_state(project, project.state)
    require(0 < len(project.nodes) <= project.limits.max_history, "Invalid history length", "invalid_project")
    require(project.head in project.nodes, "Invalid history head", "invalid_project")
    from .project import NODE_KEYS

    completed = set()
    for key, node in project.nodes.items():
        require(
            isinstance(node, dict)
            and node.get("id") == key
            and set(node) <= NODE_KEYS
            and ("state" in node) != ("delta" in node)
            and isinstance(node.get("operations"), list)
            and (node.get("parent") is not None or "state" in node),
            "Invalid history node",
            "invalid_project",
        )
        # Historical states are reconstructed and validated when a revision is restored.
        chain = set()
        cursor = key
        while cursor is not None and cursor not in completed:
            require(
                cursor in project.nodes and cursor not in chain,
                "Invalid or cyclic history",
                "invalid_project",
            )
            chain.add(cursor)
            cursor = project.nodes[cursor]["parent"]
        completed.update(chain)
    for ref in [*project.branches.values(), *project.checkpoints.values(), *project.redo_stack]:
        require(ref in project.nodes, "Invalid history reference", "invalid_project")
    require(
        project.current_branch is None or project.current_branch in project.branches, "Invalid current branch"
    )
    if project.transaction:
        check_state(project, project.transaction["state"])
        require(isinstance(project.transaction["operations"], list), "Invalid transaction")
    from copy import deepcopy
    from .project import upgrade_state

    head = project._state_at(project.head)
    check_state(project, upgrade_state(deepcopy(head)))
    project._head_state = head
    project._verified = {project.head}
    resolve_layout(project)


def dependencies(project):
    result = {"embedded": [], "linked": [], "fonts": [], "providers": []}
    for layer in project.state["layers"]:
        if layer.get("linked"):
            path = Path(layer["linked"])
            if not path.is_absolute():
                path = (project.path.parent if project.path else Path.cwd()) / path
            result["linked"].append({"layer": layer["id"], "path": str(path), "exists": path.is_file()})
        elif layer.get("asset"):
            result["embedded"].append(layer["asset"])
        if layer.get("font"):
            result["fonts"].append(layer["font"])
        provenance = layer.get("provenance", {})
        if provenance.get("provider"):
            result["providers"].append(provenance["provider"])
        source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
        if source.get("url") or provenance.get("credit") or provenance.get("license"):
            result.setdefault("attributions", []).append({
                "layer": layer["id"], **{key: source[key] for key in ("url", "fetched_at") if source.get(key)},
                **{key: provenance[key] for key in ("credit", "license") if provenance.get(key)}})
    return result


def font_size(project, layer):
    """The size text renders at: a linked character style's size takes precedence."""
    style = project.state.get("character_styles", {}).get(layer.get("character_style") or "", {})
    return style.get("size", layer["size"])


def assert_rule(project, rule):
    bounds = resolve_layout(project)
    c = project.state["canvas"]
    match = re.fullmatch(r"layer\.(.+)\.(exists|bounds within canvas)", rule.strip())
    if match:
        try:
            layer = project.layer(match[1])
        except VixlError:
            return False
        if match[2] == "exists":
            return True
        x, y, w, h = bounds[layer["id"]]
        return x >= 0 and y >= 0 and x + w <= c["width"] and y + h <= c["height"]
    match = re.fullmatch(
        r"(canvas\.(?:width|height)|text\..+\.font-size|layer\..+\.(?:width|height|opacity))\s*(==|!=|>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)",
        rule.strip(),
    )
    require(match, "Unsupported assertion; see docs/commands.md", "invalid_assertion")
    path, op, expected = match.groups()
    if path.startswith("canvas."):
        actual = c[path.split(".")[1]]
    else:
        namespace, rest = path.split(".", 1)
        target, field = rest.rsplit(".", 1)
        try:
            layer = project.layer(target)
        except VixlError:
            return False
        if namespace == "text" and layer["type"] != "text":
            return False
        actual = font_size(project, layer) if field == "font-size" else layer[field]
    return {
        "==": operator.eq,
        "!=": operator.ne,
        ">=": operator.ge,
        "<=": operator.le,
        ">": operator.gt,
        "<": operator.lt,
    }[op](actual, float(expected))


def validate(project, profile=None, rules=None, *, suppress=None):
    checks = []

    from fnmatch import fnmatchcase

    require(suppress is None or isinstance(suppress, list) and all(isinstance(x, str) for x in suppress),
            "suppress must be a list of rule names or globs", field="suppress")

    def add(name, ok, severity="error", layer=None):
        if any(fnmatchcase(name, pattern) for pattern in suppress or []):
            return
        checks.append({"rule": name, "passed": bool(ok), "severity": severity,
                       **({"layer": layer["name"], "target": layer["id"]} if layer else {})})

    c = project.state["canvas"]
    if profile:
        profiles = {
            "instagram-post": (1, 1),
            "instagram-square": (1, 1),
            "story": (9, 16),
            "youtube-thumbnail": (16, 9),
        }
        require(profile in profiles, f"Unknown validation profile: {profile}")
        w, h = profiles[profile]
        add(f"Canvas ratio {w}:{h}", c["width"] * h == c["height"] * w)
        if profile.startswith("instagram"):
            add("PNG export under 8 MB", len(project.export(format="PNG")) <= 8 * 1024 * 1024)
    add("RGBA8 document", c["color_mode"] == "rgba8")
    from .checks import canvas_projection
    from .render import resolved_layers

    index = {layer["id"]: layer for layer in resolved_layers(project)}
    bounds = canvas_projection(index, resolve_layout(project, layers=list(index.values())))["bounds"]

    def bleed_intent(layer):
        while layer is not None:
            if layer.get("allow_crop") or layer.get("role") in ("decoration", "background"):
                return True
            layer = index.get(layer.get("parent"))
        return False

    for layer in project.state["layers"]:
        x, y, w, h = bounds[layer["id"]]
        inside = x >= 0 and y >= 0 and x + w <= c["width"] and y + h <= c["height"]
        intentional = bleed_intent(layer)
        add(f"layer.{layer['name']}.bounds within canvas", inside,
            "info" if intentional else "error", layer)
        if layer["type"] == "text":
            add(f"{layer['name']} font size >= 24", font_size(project, layer) >= 24, "warning", layer)
    from .checks import missing_glyphs

    for item in missing_glyphs(project):
        add(f"{item['layer']} has drawable glyphs (missing {''.join(item['missing'][:12])})", False)
    for item in dependencies(project)["linked"]:
        add(f"Linked asset exists: {item['path']}", item["exists"])
    for rule in rules or []:
        add(rule, assert_rule(project, rule))
    return {"valid": all(x["passed"] or x["severity"] in ("warning", "info") for x in checks), "checks": checks}

