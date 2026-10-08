"""Named agent design resources; user additions are bounded JSON, never executable code."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from .effect_workflows import WORKFLOWS, SUITES
from .containers import builtins as container_builtins

from .fileio import file_lock

from .assets import read_bounded
from .design import named
from .errors import require
from .guidance import GUIDANCE
from . import house_style

PALETTES = {
    "midnight": ["#101828", "#344054", "#667085", "#e4e7ec", "#f9fafb"],
    "ocean": ["#003049", "#006d77", "#83c5be", "#edf6f9", "#ffddd2"],
    "sunset": ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"],
    "forest": ["#132a13", "#31572c", "#4f772d", "#90a955", "#ecf39e"],
    "desert": ["#582f0e", "#936639", "#a68a64", "#b6ad90", "#e6ccb2"],
    "berry": ["#590d22", "#800f2f", "#a4133c", "#ff758f", "#fff0f3"],
    "lavender": ["#240046", "#5a189a", "#9d4edd", "#c77dff", "#e0aaff"],
    "pastel": ["#ffadad", "#ffd6a5", "#fdffb6", "#caffbf", "#a0c4ff"],
    "neon": ["#080708", "#00f5d4", "#00bbf9", "#fee440", "#f15bb5"],
    "earth": ["#283618", "#606c38", "#fefae0", "#dda15e", "#bc6c25"],
    "copper": ["#3d1308", "#7b3f00", "#b87333", "#e0b589", "#fff4e6"],
    "ice": ["#03045e", "#0077b6", "#00b4d8", "#90e0ef", "#caf0f8"],
    "rose": ["#450920", "#a53860", "#da627d", "#ffa5ab", "#f9dbbd"],
    "mint": ["#004b23", "#006400", "#38b000", "#9ef01a", "#ccff33"],
    "gold": ["#212529", "#6c757d", "#d4af37", "#f1d67a", "#fff8dc"],
    "slate": ["#0f172a", "#334155", "#64748b", "#cbd5e1", "#f8fafc"],
    "coral": ["#073b4c", "#118ab2", "#06d6a0", "#ffd166", "#ef476f"],
    "autumn": ["#582f0e", "#7f4f24", "#a44a3f", "#d4a373", "#faedcd"],
    "spring": ["#355070", "#6d597a", "#b56576", "#e56b6f", "#eaac8b"],
    "summer": ["#023047", "#219ebc", "#8ecae6", "#ffb703", "#fb8500"],
    "winter": ["#22223b", "#4a4e69", "#9a8c98", "#c9ada7", "#f2e9e4"],
    "mono": ["#000000", "#404040", "#808080", "#c0c0c0", "#ffffff"],
    "accessible-blue": ["#172554", "#1e40af", "#2563eb", "#dbeafe", "#ffffff"],
    "accessible-green": ["#052e16", "#166534", "#15803d", "#dcfce7", "#ffffff"],
    "accessible-red": ["#450a0a", "#991b1b", "#dc2626", "#fee2e2", "#ffffff"],
    "candy": ["#ff006e", "#fb5607", "#ffbe0b", "#8338ec", "#3a86ff"],
    "retro": ["#2b2d42", "#8d99ae", "#edf2f4", "#ef233c", "#d90429"],
    "nordic": ["#2e3440", "#4c566a", "#d8dee9", "#88c0d0", "#a3be8c"],
    "coffee": ["#2b2118", "#6f4e37", "#a67b5b", "#d2b48c", "#fff8e7"],
    "plum": ["#231942", "#5e548e", "#9f86c0", "#be95c4", "#e0b1cb"],
    "peach": ["#5c374c", "#985277", "#ce6a85", "#ff8c61", "#ffd6a5"],
    "sage": ["#344e41", "#3a5a40", "#588157", "#a3b18a", "#dad7cd"],
}
# The house-style palettes (safe, dark, saturated, duotone, earthy, bold and avant-garde) by name.
PALETTES.update(house_style.palette_colors())


def template(width, height, operations, description):
    return {
        "description": description,
        "width": width,
        "height": height,
        "background": "transparent",
        "operations": operations,
    }



TEMPLATES = {}
for name, w, h in (
    ("social-square", 1080, 1080),
    ("story", 1080, 1920),
    ("thumbnail", 1280, 720),
    ("poster", 1200, 1600),
    ("business-card", 1050, 600),
):
    TEMPLATES[name] = template(
        w,
        h,
        [
            {"type": "solid", "name": "background", "color": "${background}", "width": w, "height": h},
            {
                "type": "text",
                "name": "title",
                "text": "${title}",
                "size": 80,
                "color": "${foreground}",
                "x": 70,
                "y": 80,
            },
            {
                "type": "text",
                "name": "subtitle",
                "text": "${subtitle}",
                "size": 32,
                "color": "${foreground}",
                "x": 70,
                "y": 200,
            },
        ],
        f"Editable {name.replace('-', ' ')} with headline and subtitle.",
    )
    # Copy is fill-in-the-blank and colors are rolled from a seeded palette unless supplied:
    # the template fixes structure, not the content or the look.
    TEMPLATES[name]["blanks"] = {"title": "[Headline]", "subtitle": "[Subheading]"}
    TEMPLATES[name]["roll"] = {"background": "background", "foreground": "ink"}
    # Sizes and positions are drawn for the native size and scale with the canvas it is applied to.
    TEMPLATES[name]["proportional"] = True
TEMPLATES["logo"] = template(
    512,
    512,
    [
        {
            "type": "shape",
            "shape": "hexagon",
            "name": "mark",
            "width": 240,
            "height": 240,
            "x": 136,
            "y": 136,
            "fill": "${accent}",
        }
    ],
    "Transparent geometric logo starter.",
)
TEMPLATES["logo"]["roll"] = {"accent": "accent"}
TEMPLATES["logo"]["proportional"] = True
CONTAINERS, MODULAR_TEMPLATES = container_builtins()
TEMPLATES.update(MODULAR_TEMPLATES)
BUILTINS = {"palettes": PALETTES, "templates": TEMPLATES, "guidance": GUIDANCE,
            "containers": CONTAINERS, "shapes": {}, "suites": SUITES, "workflows": WORKFLOWS}


def proportional(project, item, operations):
    """Scale a proportional template's operations from its native size to the canvas: one factor for sizes and
    offsets (so the copy keeps its relative size and place on any aspect ratio), and full-canvas backgrounds."""
    if not item.get("proportional"):
        return operations
    c = project.state["canvas"]
    w, h = item["width"], item["height"]
    factor = min(c["width"] / w, c["height"] / h)
    result = []
    for operation in operations:
        operation = dict(operation)
        if operation.get("type") == "solid" and (operation.get("width"), operation.get("height")) == (w, h):
            operation.update(width=c["width"], height=c["height"])
        for key in ("x", "y", "width", "height"):
            if isinstance(operation.get(key), (int, float)) and operation.get("type") != "solid":
                operation[key] = round(operation[key] * factor)
        if isinstance(operation.get("size"), (int, float)):
            operation["size"] = max(6, round(operation["size"] * factor))
        result.append(operation)
    return result


def resource_path(workspace=None):
    if workspace is not None:
        root = Path(workspace).resolve()
        path = (root / ".vixl-resources.json").resolve()
        require(path.is_relative_to(root), "Resource path escapes workspace", "forbidden")
        return path
    return Path(os.environ.get("VIXL_RESOURCES", "~/.config/vixl/resources.json")).expanduser()


def catalog(kind, *, workspace=None):
    require(kind in BUILTINS, "Unknown resource category")
    path = resource_path(workspace)
    user = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
    require(isinstance(user, dict) and isinstance(user.get(kind, {}), dict), "Invalid resource library")
    inherited = catalog(kind) if workspace is not None else BUILTINS[kind]
    return deepcopy({**inherited, **user.get(kind, {})})


def get(kind, name, *, workspace=None):
    items = catalog(kind, workspace=workspace)
    require(name in items, f"Unknown {kind} resource: {name}")
    value = items[name]
    validate(kind, value)
    return value


def validate(kind, value):
    from .render import color
    from .schema import validate_operation

    if kind == "palettes":
        require(isinstance(value, list) and 2 <= len(value) <= 256, "Palette needs 2–256 colors")
        for c in value:
            color(c)
    elif kind == "containers":
        from .containers import validate as validate_container
        validate_container(value)
    elif kind == "shapes":
        from .interfaces import service_check
        require(isinstance(value, dict) and value.get("type") in ("shape", "pen"), "Saved shapes need a shape or pen operation")
        service_check(validate_operation(value))
        require(not value.get("target"), "Saved shapes cannot target an existing layer")
    elif kind == "suites":
        from .assurance import validate_suite
        validate_suite(value)
    elif kind == "workflows":
        from .effect_workflows import validate as validate_workflow
        validate_workflow(value)
    elif kind == "guidance":
        require(isinstance(value, str) and 0 < len(value) <= 100000, "Guidance needs 1–100000 characters")
    elif kind == "templates":
        require(isinstance(value, dict), "Template must be a JSON object")
        from .model import Limits

        require("width" in value and "height" in value, "Template requires width and height")
        Limits().size(value["width"], value["height"])
        color(value.get("background", "transparent"))
        require(isinstance(value.get("defaults", {}), dict), "Template defaults must be an object")
        from .automation import validate_inputs, validate_state as validate_automation
        validate_automation(value)
        if "inputs" in value:
            validate_inputs(value["inputs"], value.get("defaults", {}))
        blanks, roll = value.get("blanks", {}), value.get("roll", {})
        require(isinstance(blanks, dict) and all(isinstance(v, str) and v for v in blanks.values()),
                "Template blanks map variables to placeholder text")
        roles = ("background", "surface", "ink", "muted", "accent", "accent-text", "on-accent")
        require(isinstance(roll, dict) and all(v in roles for v in roll.values()),
                f"Template roll maps variables to color roles: {', '.join(roles)}")
        sample = {**{k: "#000000" for k in roll}, **blanks, **value.get("defaults", {})}
        ops = value.get("operations")
        maximum = Limits().max_operations
        require(isinstance(ops, list) and 0 < len(ops) <= maximum, f"Template needs 1–{maximum} operations")
        for op in ops:
            validate_operation(substitute(op, sample))
            require(
                op["type"] not in ("template-apply", "font-register")
                and not any(k in op for k in ("font", "linked"))
                and ("path" not in op or op["type"] in ("shape", "text-layout")),
                "Templates cannot read files or recursively apply templates",
            )


def register(kind, name, value, *, workspace=None):
    require(kind in BUILTINS, "Unknown resource category")
    named(name)
    validate(kind, value)
    path = resource_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(str(path)):
        data = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
        require(not any(name in plugin.get("resources", {}).get(kind, []) for plugin in data.get("_plugins", {}).values()),
                "Resource belongs to a plugin; update the pack or save under another name")
        data.setdefault(kind, {})[name] = value
        payload = json.dumps(data, ensure_ascii=False).encode()
        require(len(payload) <= 1024 * 1024, "Resource library exceeds limit", "resource_limit")
        fd, temp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return {"registered": name, "kind": kind}


def substitute(value, variables):
    from .render import substitute as text_substitute

    if isinstance(value, dict):
        return {k: substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, variables) for v in value]
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}") and value[2:-1] in variables:
            return deepcopy(variables[value[2:-1]])
        return text_substitute(value, variables)
    return value


RESOURCE_TYPES = ("palette-define", "palette-apply", "template-apply", "guidance", "font-register")


def execute_resource(project, op):
    kind, name = op["type"], named(op["name"])
    if kind == "palette-define":
        validate("palettes", op["colors"])
        project.state.setdefault("palettes", {})[name] = deepcopy(op["colors"])
    elif kind == "palette-apply":
        if op.get("prefix"):
            named(op["prefix"])
        colors = project.state.get("palettes", {}).get(name) or get("palettes", name, workspace=getattr(project, "_workspace", None))
        project.state.setdefault("palettes", {})[name] = deepcopy(colors)
        project.state["active_palette"] = name
        swatches = project.state.setdefault("swatches", {})
        swatches.update({f"{op.get('prefix', name)}-{i + 1}": c for i, c in enumerate(colors)})
        if op.get("roles", True):
            # Role swatches recolor every layer that references them (layouts, templates, @accent …).
            import random

            from .colors import parse, relative_luminance
            from .layouts import ROLES, assign_roles

            # Keep the document's light or dark mode, unless the palette's own order is kept.
            mode, mode_source = "light", "default (no @background swatch yet)"
            if "background" in swatches:
                mode = "dark" if relative_luminance(parse(swatches["background"])[:3]) < 0.2 else "light"
                mode_source = "the document's @background swatch"
            keep_order = bool(op.get("keep_order"))
            explicit = op["roles"] if isinstance(op.get("roles"), dict) else {}
            roles = assign_roles({"palette": colors, "policy": op.get("policy", "strict"), "keep_order": keep_order,
                                  "role_map": explicit, **({} if keep_order else {"mode": mode, "_mode_source": mode_source})},
                                 random.Random(name))
            swatches.update({role: roles[role] for role in ROLES})
            # Echoed in the apply result: which color became which role, from where, and why.
            project.state["palette_roles"] = {"palette": name, "mode": roles["_mode"], "mode_source": roles["_mode_source"],
                                              "keep_order": keep_order, "roles": roles["_explain"], "notes": roles["_notes"]}
    elif kind == "guidance":
        key = op.get("style", "overall")
        named(key)
        if op.get("delete"):
            project.state.setdefault("design_guidance", {}).pop(key, None)
        else:
            text = op.get("text") or get("guidance", name)
            validate("guidance", text)
            project.state.setdefault("design_guidance", {})[key] = text
    elif kind == "font-register":
        from .fonts import validate_font

        role = op.get("role")
        require(op.get("asset") or role, "font-register needs an asset, a role, or both")
        if op.get("asset"):
            asset = op["asset"]
            require(asset in project.assets and asset.startswith("fonts/"), "Import a font asset first")
            validate_font(project.assets[asset])
            project.state.setdefault("fonts", {})[name] = asset
        if role:
            require(role in ("heading", "body"), "role must be heading or body", field="role")
            require(name in project.state.get("fonts", {}), f"Font {name!r} is not registered; install or import it first")
            project.state.setdefault("typography", {})[role] = name
            from .render import text_metrics

            for layer in project.state["layers"]:
                if layer["type"] == "text" and layer.get("font_role") == role:
                    layer["font"] = project.state["fonts"][name]
                    if layer.get("auto_size", True):
                        layer["width"], layer["height"], _ = text_metrics(project, layer)
    else:
        from .operations import execute
        from .schema import validate_operation

        item = get("templates", name, workspace=getattr(project, "_workspace", None))
        from .typefaces import resolve_seed
        import random
        from .layouts import assign_roles, ROLES
        from .brand import for_project
        kit = for_project(project)
        from .variety import sparse_options

        explicit_palette = "palette" in op
        op = sparse_options(project, op)
        # Every template receives a reproducible direction; explicit and brand roles win.
        role_options = {k: op[k] for k in ("palette", "mode") if k in op}
        if explicit_palette:
            role_options["policy"] = "strict"
        if kit.get("palette") and not explicit_palette:
            role_options["colors"] = kit["palette"]
        chosen_roles = assign_roles(role_options, random.Random(op["seed"]))
        swatches = project.state.setdefault("swatches", {})
        for role in ROLES:
            if role in kit.get("palette", {}) and not explicit_palette:
                swatches[role] = kit["palette"][role]
            elif "palette" in op or role not in swatches:
                swatches[role] = chosen_roles[role]
        supplied = op.get("variables", {})
        values = {**item.get("defaults", {}), **supplied}
        before = {layer["id"] for layer in project.state["layers"]}
        from .pages import page_content
        for page in project.state.get("pages", []):
            before.update(layer["id"] for layer in page_content(project, page).get("layers", []))
        blanks = {k: v for k, v in item.get("blanks", {}).items() if k not in values}
        values.update(blanks)
        rolled, seed = {"palette": chosen_roles["_palette"], "mode": chosen_roles["_mode"]}, op["seed"]
        missing = {var: role for var, role in item.get("roll", {}).items() if var not in values}
        if missing:
            import random
            import secrets

            from .layouts import assign_roles

            seed = op.get("seed")
            if seed == "random":
                seed = secrets.randbelow(2**32)
            elif seed is None:
                seed = resolve_seed(None)
            require(isinstance(seed, int) and 0 <= seed < 2**32, "seed must be a nonnegative 32-bit integer or 'random'", field="seed")
            roles = chosen_roles
            # Rolled colors become role swatches (existing ones are kept), so palette apply can
            # recolor the template later.
            swatches = project.state.setdefault("swatches", {})
            for role in set(missing.values()):
                swatches.setdefault(role, roles[role])
            rolled = {var: swatches[role] for var, role in missing.items()}
            rolled["palette"] = roles["_palette"]
            values.update({var: f"@{role}" for var, role in missing.items()})
        if "inputs" in item:
            from .automation import validate_inputs
            values = validate_inputs(item["inputs"], values)
            project.state["variables"].update(values)
        from .container_library import template_operations
        expanded = substitute(proportional(project, item, template_operations(project, item, op, values)), values)
        # Template text follows the document typography: the largest text is the heading.
        texts = [o for o in expanded if o.get("type") == "text" and "font" not in o]
        largest = max((o.get("size", 48) for o in texts), default=None)
        for operation in texts:
            operation["font"] = "heading" if operation.get("size", 48) == largest else "body"
        remaining = getattr(project, "_resource_budget", project.limits.max_operations) - len(expanded) + 1
        require(remaining >= 0, "Expanded templates exceed the operation limit", "resource_limit")
        project._resource_budget = remaining
        from .normalize import resolve_geometry, apply_centering

        for operation in expanded:
            operation = validate_operation(operation)
            resolved, centered = resolve_geometry(project, operation)
            execute(project, resolved)
            apply_centering(project, centered, operation)
        look = op.get("look", "none")
        from .container_library import finish_template
        finish_template(project, look, before)
        rolled["look"] = look
        if op.get("style"):
            from .styles import apply_operations

            for operation in apply_operations(op["style"], palette=False):
                execute(project, operation)
            rolled["style"] = op["style"]
        for key, kind, field in (("suites", "suite-set", "suite"), ("motions", "motion-define", "motion"),
                                 ("actions", "action-define", "action")):
            for resource_name, resource in item.get(key, {}).items():
                execute(project, {"type": kind, "name": resource_name, field: resource})
        for role, targets in item.get("roles", {}).items():
            execute(project, {"type": "role-set", "name": role, "targets": targets})
        if "recipe" in item:
            execute(project, {"type": "recipe-set", "recipe": item["recipe"]})
        registry = project.state.setdefault("blanks", {})
        found = []
        for layer in project.state["layers"]:
            if layer["id"] in before or layer["type"] != "text":
                continue
            slot = next((var for var, text in blanks.items() if text in layer["text"]), None)
            if slot:
                registry[layer["id"]] = {"slot": slot, "text": layer["text"], "hint": f"template variable {slot!r}", "source": f"template:{name}"}
                found.append({"slot": slot, "layer": layer["name"]})
        if found or rolled:
            record = {"name": name}
            if not project.state.get("typography"):
                from .variety import font_next_step

                record["font_choice"] = font_next_step(project, seed)
            if rolled:
                record.update(seed=seed, rolled=rolled)
            if found:
                record["blanks"] = found
                record["note"] = "Fill the blanks: pass them as template variables, or edit the layers' text."
            project.state["template"] = record


def create_template(name, variables=None, *, limits=None, workspace=None, seed=None, palette=None, look=None):
    from .project import Project

    item = get("templates", name, workspace=workspace)
    p = Project(item["width"], item["height"], item.get("background", "transparent"), limits=limits)
    p._workspace = workspace
    p.apply({"type": "template-apply", "name": name, "variables": variables or {}, **{k:v for k,v in {"seed":seed,"palette":palette,"look":look}.items() if v is not None}}, detail="compact")
    return p
