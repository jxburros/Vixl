"""Forgiving input for model-written operations.

Language models reliably guess a handful of spellings that differ from the canonical schema
(``rect``, ``font_size``, ``opacity: "50%"``, camelCase keys, ``"50%"`` coordinates). Rejecting each
guess costs an agent a round trip, so every interface normalizes them here, the same way, and
reports what changed so the caller can learn the canonical form.
"""

import re

from .errors import VixlError, require

PERCENT = re.compile(r"^(-?\d+(?:\.\d+)?)%$")

TYPE_ALIASES = {
    "image": "add",
    "add-image": "add",
    "import": "add",
    "import-image": "add",
    "add-text": "text",
    "text-add": "text",
    "set-text": "text-set",
    "edit-text": "text-set",
    "update-text": "text-set",
    "delete": "remove",
    "delete-layer": "remove",
    "translate": "move",
    "set-position": "move",
    "set-opacity": "opacity",
    "set-blend": "blend",
    "blend-mode": "blend",
    "add-layer": "add",
    "remove-layer": "remove",
    "move-layer": "move",
    "set-effect": "effect",
    "filter": "effect",
    "make-selection": "select",
    "style": "layer-style",
    "add-shape": "shape",
    "rich": "rich-text",
    "markdown": "rich-text",
    "text-rich": "rich-text",
    "text-span": "text-style",
    "style-text": "text-style",
    "span": "text-style",
    "input": "field",
    "form-field": "field",
    "add-field": "field",
    "set-field": "field-set",
    "field-update": "field-set",
    "sketch": "drawing",
    "roughen": "irregular",
    "distress": "irregular",
    "imperfect": "irregular",
    "torn-edge": "tear",
    "rip": "tear",
    "torn": "tear",
    "add-chart": "chart",
    "graph": "chart",
    "update-chart": "chart",
    "set-chart-data": "chart-data",
    "update-chart-data": "chart-data",
    "flowchart": "diagram",
    "flow-chart": "diagram",
    "diagram-text": "diagram-from-text",
}
SHAPE_TYPES = {
    "rect": ("rectangle", {}),
    "rectangle": ("rectangle", {}),
    "square": ("rectangle", {}),
    "box": ("rectangle", {}),
    "rounded-rect": ("rounded-rectangle", {}),
    "rounded-rectangle": ("rounded-rectangle", {}),
    "roundrect": ("rounded-rectangle", {}),
    "rounded": ("rounded-rectangle", {}),
    "pill": ("rounded-rectangle", {}),
    "circle": ("ellipse", {}),
    "oval": ("ellipse", {}),
    "ellipse": ("ellipse", {}),
    "triangle": ("polygon", {"sides": 3}),
    "pentagon": ("polygon", {"sides": 5}),
    "hexagon": ("polygon", {"sides": 6}),
    "octagon": ("polygon", {"sides": 8}),
    "polygon": ("polygon", {}),
    "star": ("star", {}),
    "line": ("line", {}),
    "arc": ("arc", {}),
    "pie": ("arc", {}),
    "wedge": ("arc", {}),
    "sector": ("arc", {}),
    "donut": ("arc", {"inner_radius": 0.6}),
    "ring": ("arc", {"inner_radius": 0.8}),
}
STYLE_ALIASES = {
    "shadow": "drop-shadow",
    "dropshadow": "drop-shadow",
    "drop-shadow": "drop-shadow",
    "glow": "outer-glow",
    "outer-glow": "outer-glow",
    "outline": "stroke",
    "stroke": "stroke",
    "color-overlay": "color-overlay",
    "gradient-overlay": "gradient-overlay",
}
TARGET_ALIASES = ("layer", "layer_id", "layerId", "target_id", "targetId", "layer_name")
FIELD_ALIASES = {
    "text": {
        "font_size": "size",
        "fontsize": "size",
        "content": "text",
        "fill": "color",
        "colour": "color",
        "font_color": "color",
        "text_align": "align",
        "alignment": "align",
        "font_family": "font",
        "line_spacing": "spacing",
        "outline_width": "stroke_width",
        "outline_color": "stroke_color",
        **{key: "hide_if_empty" for key in ("hide_when_empty", "collapse_if_empty", "collapse_when_empty", "hide_empty")},
    },
    "shape": {
        "color": "fill",
        "colour": "fill",
        "fill_color": "fill",
        "stroke_color": "stroke",
        "outline": "stroke",
        "outline_color": "stroke",
        "border_color": "stroke",
        "border_width": "stroke_width",
        "outline_width": "stroke_width",
        "corner_radius": "radius",
        "border_radius": "radius",
        "type_of_shape": "shape",
        "kind": "shape",
        "start": "start_angle",
        "end": "end_angle",
        "angle_start": "start_angle",
        "angle_end": "end_angle",
        "hole": "inner_radius",
        "inner": "inner_radius",
    },
    "solid": {"fill": "color", "colour": "color", "fill_color": "color"},
    "gradient": {"from": "start", "to": "end", "start_color": "start", "end_color": "end"},
    "opacity": {"opacity": "value", "amount": "value", "alpha": "value"},
    "rotate": {"angle": "value", "degrees": "value", "rotation": "value"},
    "scale": {"factor": "value", "amount": "value"},
    "blend": {"mode": "value", "blend": "value", "blend_mode": "value"},
    "rename": {"new_name": "name", "to": "name"},
    "effect": {"effect": "name", "filter": "name", "value": "amount"},
    "canvas": {"color": "background", "fill": "background"},
    "variable": {"key": "name"},
    "align": {"align": "alignment", "position": "alignment", "relativeTo": "relative_to"},
    "animation-set": {"frames": "order", "sequence": "order"},
    "frames-edit": {"ops": "operations", "edits": "operations"},
    "resize": {
        key: "keep_aspect"
        for key in ("lock_aspect", "lock_aspect_ratio", "keep_aspect_ratio", "preserve_aspect", "proportional",
                    "maintain_aspect", "keep_ratio")
    },
    "link": {"path": "source", "file": "source", "src": "source", "document": "source", "doc": "source"},
}
FIELD_ALIASES["text-set"] = FIELD_ALIASES["text"]
GEOMETRY_TYPES = {
    "qr",
    "barcode",
    "solid",
    "gradient",
    "shape",
    "text",
    "add",
    "frame",
    "symbol-instance",
    "move",
    "resize",
    "select",
    "text-layout",
    "pen",
    "field",
    "stack",
    "link",
    "chart",
}
CENTER_TYPES = {"solid", "gradient", "shape", "add", "frame", "symbol-instance", "move", "field", "link", "chart", "qr",
                "barcode"}


def _snake(key):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower().replace("-", "_")


def _canonical_type(kind, known):
    if not isinstance(kind, str):
        return kind
    candidates = [kind, kind.lower(), kind.lower().replace("_", "-").replace(" ", "-")]
    for candidate in candidates:
        if candidate in known:
            return candidate
    for candidate in candidates:
        if candidate in TYPE_ALIASES:
            return TYPE_ALIASES[candidate]
    return candidates[-1] if candidates[-1] in SHAPE_TYPES or candidates[-1] in STYLE_ALIASES else kind


# What an adjustment layer's effects entries may hold.
ADJUSTMENT_FIELDS = frozenset({"name", "amount", "value", "seed", "radius", "strength", "shadow_color",
                               "highlight_color", "black", "white", "points", "enabled", "luminance", "chroma",
                               "search"})

# Colour fields where "none" means no paint, spelled "transparent" from here on.
COLOR_FIELDS = ("fill", "stroke", "color", "stroke_color", "background", "start", "end", "highlight")


def normalize_operation(operation, properties, known_types, effects, notes, index=None, required=None):
    """Rewrite well-known guesses into canonical form. ``properties(kind)`` returns the schema's
    property names for a canonical operation type; the result is still schema-validated."""
    require(isinstance(operation, dict), "Each operation must be an object")
    op = dict(operation)
    where = f"operations[{index}]" if index is not None else "operation"

    def note(text):
        notes.append(f"{where}: {text}")

    if "type" not in op and "operation" in op:
        op["type"] = op.pop("operation")
    original = op.get("type")
    kind = _canonical_type(original, known_types)
    if isinstance(kind, str) and kind in SHAPE_TYPES and kind not in known_types:
        shape, extra = SHAPE_TYPES[kind]
        op.setdefault("shape", shape)
        for key, value in extra.items():
            op.setdefault(key, value)
        kind = "shape"
    elif isinstance(kind, str) and kind in STYLE_ALIASES and kind not in known_types:
        settings = {k: op.pop(k) for k in list(op) if k not in ("type", "target", *TARGET_ALIASES, "remove")}
        op = {**op, "name": STYLE_ALIASES[kind]}
        if settings:
            op["settings"] = settings
        kind = "layer-style"
    if kind != original:
        op["type"] = kind
        note(f"type {original!r} → {kind!r}")
    if not isinstance(kind, str) or kind not in known_types:
        return op

    for alias in TARGET_ALIASES:
        if alias in op and "target" not in op:
            op["target"] = op.pop(alias)
            note(f"{alias!r} → 'target'")
    allowed = properties(kind)

    # Generic spelling: camelCase / kebab-case keys whose snake_case form is canonical.
    for key in list(op):
        if key not in allowed and key != "type":
            snake = _snake(key)
            if snake in allowed and snake not in op:
                op[snake] = op.pop(key)
                note(f"{key!r} → {snake!r}")
    aliases = FIELD_ALIASES.get(kind, {})
    for key in list(op):
        if key in allowed or key == "type":
            continue
        canonical = aliases.get(key) or aliases.get(_snake(key)) or aliases.get(key.lower())
        if canonical and canonical in allowed and canonical not in op:
            op[canonical] = op.pop(key)
            note(f"{key!r} → {canonical!r}")

    from .targets import normalize as normalize_targets

    op = normalize_targets(op, kind, allowed, required(kind) if required else frozenset(), note)

    from .design_schema import SHAPES
    from .geometry import ANCHORS, canonical_anchor

    if isinstance(op.get("easing"), str) and op["easing"] != op["easing"].strip().lower():
        note(f"easing {op['easing']!r} → {op['easing'].strip().lower()!r}")
        op["easing"] = op["easing"].strip().lower()
    # Anchor synonyms (bottom-center, center-left, ...) → the canonical anchor names.
    for key in ("anchor", "align", "position", *(("value",) if kind == "pivot" else ())):
        name = canonical_anchor(op.get(key))
        if name and name != op[key]:
            note(f"{key} {op[key]!r} → {name!r}")
            op[key] = name
    if kind == "pivot" and isinstance(op.get("value"), str) and op["value"] not in ANCHORS:
        raise VixlError("invalid_operation", f"Unknown pivot anchor {op['value']!r}; use {', '.join(ANCHORS)}", field="value",
                        allowed=list(ANCHORS))
    if kind == "snap" and isinstance(op.get("anchors"), list):
        op["anchors"] = [canonical_anchor(v) or v for v in op["anchors"]]

    if kind == "adjustment" and isinstance(op.get("effects"), list):
        for number, effect in enumerate(op["effects"]):
            extra = sorted(set(effect) - ADJUSTMENT_FIELDS) if isinstance(effect, dict) else []
            if extra:
                raise VixlError("invalid_operation", f"Unknown field(s) {', '.join(map(repr, extra))} in "
                                f"effects[{number}]. Allowed: {', '.join(sorted(ADJUSTMENT_FIELDS))}",
                                field=f"effects.{number}.{extra[0]}", allowed=sorted(ADJUSTMENT_FIELDS))
    if kind in ("field", "field-set"):
        from .forms import normalize as normalize_field

        op = normalize_field(op, note)
    if kind in ("chart", "chart-data"):
        from .charts import normalize as normalize_chart

        op = normalize_chart(op, note)
    if kind == "shape" and isinstance(op.get("shape"), str) and op["shape"] not in SHAPES:
        guess = op["shape"].lower().replace("_", "-").replace(" ", "-")
        if guess not in SHAPE_TYPES:
            # "hexagonal", "circular", "rectangular", "stars" → their base shape.
            guess = next((name for name in SHAPE_TYPES if len(name) > 3 and guess.startswith(name)), guess)
        if guess in SHAPE_TYPES and SHAPE_TYPES[guess][0] != op["shape"]:
            shape, extra = SHAPE_TYPES[guess]
            note(f"shape {op['shape']!r} → {shape!r}")
            op["shape"] = shape
            for key, value in extra.items():
                op.setdefault(key, value)
    normalize_opacity(op, kind, note)
    if kind == "blend" and isinstance(op.get("value"), str) and op["value"] != op["value"].lower():
        op["value"] = op["value"].lower()
    if kind == "effect" and isinstance(op.get("name"), str):
        name = op["name"].lower().replace("_", "-").replace(" ", "-")
        if name in STYLE_ALIASES and name not in effects:
            settings = {k: op.pop(k) for k in list(op) if k not in ("type", "target", "name")}
            op = {**op, "type": "layer-style", "name": STYLE_ALIASES[name]}
            if settings:
                op["settings"] = settings
            note(f"{name!r} is a layer style → {{type: 'layer-style', name: {STYLE_ALIASES[name]!r}}}")
            return op
        if name != op["name"] and name in effects:
            op["name"] = name
    blur = kind in ("blur", "gaussian-blur") or (
        kind == "effect" and op.get("name") in ("blur", "gaussian-blur")
    )
    if blur and "radius" in op and "amount" not in op and "value" not in op:
        # Blur strength lives in amount; a radius field used to be accepted and silently ignored.
        op["amount"] = op.pop("radius")
        note("blur 'radius' → 'amount'")
    if kind == "layer-style" and isinstance(op.get("name"), str):
        name = op["name"].lower().replace("_", "-").replace(" ", "-")
        if STYLE_ALIASES.get(name, name) != op["name"] and STYLE_ALIASES.get(name):
            note(f"style {op['name']!r} → {STYLE_ALIASES[name]!r}")
            op["name"] = STYLE_ALIASES[name]
        settings = op.get("settings")
        if isinstance(settings, dict):
            fixed = {}
            for key, value in settings.items():
                canonical = {
                    "offset_x": "dx",
                    "offsetX": "dx",
                    "x": "dx",
                    "offset_y": "dy",
                    "offsetY": "dy",
                    "y": "dy",
                    "radius": "blur",
                    "size": "width" if op["name"] == "stroke" else "blur",
                    "colour": "color",
                }.get(key, key)
                if canonical != key and canonical not in settings:
                    note(f"settings.{key} → settings.{canonical}")
                    key = canonical
                if key == "opacity":
                    value = opacity(value, "settings.opacity", note)
                fixed[key] = value
            op["settings"] = fixed
    if kind == "resize" and ("width" in op) != ("height" in op) and "keep_aspect" not in op:
        given, other = ("width", "height") if "width" in op else ("height", "width")
        note(
            f"only {given} given, so {other} is unchanged, except on image (raster) layers, which keep their "
            "aspect ratio; set keep_aspect to true (scale proportionally) or false (change one side) to choose"
        )
    if kind == "move" and "x" not in op and "y" not in op and ("dx" in op or "dy" in op):
        op["x"], op["y"] = op.pop("dx", 0), op.pop("dy", 0)
        op["relative"] = True
        note("dx/dy → x/y with relative: true")
    if kind == "gradient" and isinstance(op.get("colors"), list) and "stops" not in op:
        colors = op.pop("colors")
        if len(colors) == 2:
            op.setdefault("start", colors[0])
            op.setdefault("end", colors[1])
        elif len(colors) > 2:
            op["stops"] = [
                {"offset": round(i / (len(colors) - 1), 6), "color": c} for i, c in enumerate(colors)
            ]
        note("colors → start/end/stops")
    for key in COLOR_FIELDS:
        if isinstance(op.get(key), str) and op[key].strip().lower() == "none":
            op[key] = "transparent"
            note(f"{key} 'none' → 'transparent'")
    return op


def opacity(value, field, note):
    """One opacity scale everywhere: 0 (clear) to 1 (opaque). A percentage string such as "70%" is
    read as 0.7 (and noted); a bare number above 1 is an error, never guessed to be a percentage."""
    if isinstance(value, str):
        match = PERCENT.match(value.strip())
        if not match:
            return value  # the schema or the operation reports the wrong type
        number = float(match[1]) / 100
        note(f"{field} {value!r} → {number:g}")
        return number
    if _number(value) and value > 1:
        raise VixlError(
            "invalid_operation",
            f"{field if 'opacity' in field else 'opacity ' + field} is on a 0–1 scale (0 clear, 1 opaque); "
            f"got {value:g}. For {value:g}% use {value / 100:g} or the string \"{value:g}%\"",
            field=field,
            suggestions=[value / 100, f"{value:g}%"],
        )
    return value


def normalize_opacity(op, kind, note):
    """Read every opacity an operation carries on the 0–1 scale (see ``opacity``)."""
    if kind == "opacity" and "value" in op:
        op["value"] = opacity(op["value"], "value", note)
    if "opacity" in op:  # creation fields, paint, patterns ...
        op["opacity"] = opacity(op["opacity"], "opacity", note)
    if isinstance(op.get("box"), dict) and "opacity" in op["box"]:  # caption boxes
        op["box"] = {**op["box"], "opacity": opacity(op["box"]["opacity"], "box.opacity", note)}
    if op.get("property") != "opacity":
        return
    # Timeline values of the opacity property.
    for key in {"keyframe": ("value",), "animate": ("from", "to"), "motion": ("to",)}.get(kind, ()):
        if key in op:
            op[key] = opacity(op[key], key, note)
    if kind == "keyframes" and isinstance(op.get("keys"), list):
        for number, key in enumerate(op["keys"]):
            if isinstance(key, dict) and "value" in key:
                key["value"] = opacity(key["value"], f"keys.{number}.value", note)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_relative(value):
    return isinstance(value, str) and (value == "center" or PERCENT.match(value) is not None)


def resolve_geometry(project, op):
    """Resolve "N%" coordinates/sizes against the canvas (or the target's parent group) and
    remember which axes asked for "center" so creation operations can center afterwards."""
    kind = op.get("type")
    if kind not in GEOMETRY_TYPES:
        return op, {}
    c = project.state["canvas"]
    width, height = c["width"], c["height"]
    from .inplace import IN_PLACE_TYPES

    if kind in ("move", "resize", "text-layout", "stack") or (kind in IN_PLACE_TYPES and op.get("target")):
        try:
            layer = project.layer(op["targets"][0] if kind == "stack" and op.get("targets") else op.get("target"))
        except Exception:
            layer = None
        if layer and layer.get("parent") and op.get("space") != "canvas" and not op.get("absolute"):
            parent = project.layer(layer["parent"])
            width, height = parent.get("content_width", width), parent.get("content_height", height)
    centered = {}
    result = dict(op)
    for key, base in (("x", width), ("y", height), ("width", width), ("height", height)):
        value = result.get(key)
        if not isinstance(value, str):
            continue
        creates_pen = kind == "pen" and not op.get("target")
        if value == "center" and key in ("x", "y") and (kind in CENTER_TYPES or creates_pen):
            centered[key] = True
            result[key] = 0
            continue
        if kind == "resize" and key in ("width", "height") and value.startswith(("+", "-")):
            continue
        match = PERCENT.match(value)
        if match:
            amount = float(match[1]) * base / 100
            result[key] = int(amount) if amount.is_integer() else amount
    return result, centered


def apply_centering(project, centered, operation):
    """Center the created (or moved) layer within its canvas or parent group."""
    if not centered:
        return
    from .render import resolve_layout, stored_origin

    from .inplace import IN_PLACE_TYPES

    # A creation operation given a target edits that layer, so the target is what gets centered.
    edits = operation.get("type") == "move" or operation.get("type") in IN_PLACE_TYPES
    layer = project.layer(operation.get("target") if edits else None)
    bounds = resolve_layout(project)[layer["id"]]
    if edits and (operation.get("space") == "canvas" or operation.get("absolute")):
        from .spatial import canvas_boxes
        from .transforms import execute
        box = canvas_boxes(project)[layer["id"]]
        canvas = project.state["canvas"]
        coords = {key: (canvas["width" if key == "x" else "height"] - box[2 if key == "x" else 3]) / 2
                  for key in centered}
        execute(project, {"type": "move", "target": layer["id"], "space": "canvas", **coords})
        return
    if layer.get("parent"):
        parent = project.layer(layer["parent"])
        width, height = parent["content_width"], parent["content_height"]
    else:
        width, height = project.state["canvas"]["width"], project.state["canvas"]["height"]
    origin = [(width - bounds[2]) / 2 if centered.get("x") else bounds[0], (height - bounds[3]) / 2 if centered.get("y") else bounds[1]]
    x, y = stored_origin(layer, origin)
    if centered.get("x"):
        layer["x"] = x
    if centered.get("y"):
        layer["y"] = y
    if operation.get("type") == "move":
        layer["constraints"] = {}
