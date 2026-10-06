"""Advisories: problems an apply call can see cheaply, returned under ``warnings`` (never errors).

A successful apply used to say nothing about text that spills off the canvas or out of its box, or
about a field that was accepted but changes nothing, so a wrong guess looked like success. These
checks look only at the layers and operations of this one call, so they add no noise about
pre-existing problems. ``vixl_check`` remains the complete audit.
"""

MAX_WARNINGS = 12
MAX_LAYERS = 200
# A non-text layer may bleed past the canvas edge on purpose; warn when most of it is outside.
OUTSIDE_FRACTION = 0.25
EFFECT_FIELDS = {"name", "amount", "value", "seed", "radius", "strength", "shadow_color", "highlight_color",
                 "black", "white", "points", "enabled"}


# Shapes that read inner_radius: a star's inner points and an arc's hole (donut/ring/pie share arc).
INNER_RADIUS_SHAPES = ("star", "arc")


def _names(shapes):
    return " and ".join(repr(shape) for shape in shapes)


def advise(candidate, before, after, operations):
    """Warnings for what ``operations`` changed in ``candidate`` (``before``/``after`` are inspect() states)."""
    warnings = []
    for index, operation in enumerate(operations):
        where = f"operations[{index}]" if len(operations) > 1 else "operation"
        warnings.extend(f"{where}: {text}" for text in ignored_fields(candidate, operation))
    try:
        warnings.extend(placement(candidate, before, after))
    except Exception:  # noqa: BLE001 - an advisory must never fail an edit that already succeeded
        pass
    unique = list(dict.fromkeys(warnings))
    if len(unique) > MAX_WARNINGS:
        unique = unique[:MAX_WARNINGS] + [f"... and {len(unique) - MAX_WARNINGS} more; run vixl_check for the full list"]
    return unique


def ignored_fields(candidate, op):
    """Fields the schema accepts that change nothing for this operation (a likely wrong guess)."""
    kind = op.get("type")
    found = []
    if kind == "shape":
        shape, name = op.get("shape"), repr(op.get("name", "shape"))
        if shape is None:  # editing an existing layer: its own shape decides what each field does
            try:
                shape = candidate.layer(op.get("target", op.get("layer"))).get("shape")
            except Exception:  # noqa: BLE001 - an unresolvable target is reported by the operation itself
                return found
        from .normalize import SHAPE_TYPES

        shape = SHAPE_TYPES.get(shape, (shape,))[0] if isinstance(shape, str) else shape  # donut → arc, pill → ...
        if "radius" in op and shape not in ("rounded-rectangle", "capsule"):
            found.append(f"shape {name}: radius only rounds 'rounded-rectangle' and 'capsule'; it does nothing "
                         f"for {shape!r}")
        if "sides" in op and shape not in ("polygon", "star"):
            found.append(f"shape {name}: sides only applies to 'polygon' and 'star', not {shape!r}")
        if "inner_radius" in op and shape not in INNER_RADIUS_SHAPES:
            found.append(f"shape {name}: inner_radius only applies to {_names(INNER_RADIUS_SHAPES)}, not {shape!r}")
        if "path" in op and shape != "path":
            found.append(f"shape {name}: path is only drawn for shape 'path', not {shape!r}")
        if "stroke_width" in op and "stroke" not in op and shape != "line":
            found.append(f"shape {name}: stroke_width draws nothing without a stroke colour; add stroke")
    elif kind == "gradient":
        name = repr(op.get("name", "gradient"))
        if "stops" in op and ("start" in op or "end" in op):
            found.append(f"gradient {name}: start/end are ignored when stops is given")
        if "angle" in op and op.get("direction", "vertical") != "angled":
            found.append(f"gradient {name}: angle only applies with direction 'angled' "
                         f"(this one is {op.get('direction', 'vertical')!r})")
    elif kind == "align":
        if op.get("margin") and op.get("alignment") in ("center", "center-x", "center-y"):
            found.append(f"align: margin has no effect on {op['alignment']!r}")
    elif kind == "adjustment":
        for number, effect in enumerate(op.get("effects") or []):
            if isinstance(effect, dict):
                extra = sorted(set(effect) - EFFECT_FIELDS)
                if extra:
                    found.append(f"adjustment effects[{number}]: unknown field(s) {', '.join(map(repr, extra))} are "
                                 f"ignored; known: {', '.join(sorted(EFFECT_FIELDS - {'enabled'}))}")
    elif kind == "preset-apply":
        saved = {effect["name"] for effect in candidate.state.get("presets", {}).get(op.get("name"), [])}
        extra = sorted(set(op.get("overrides") or {}) - saved)
        if extra:
            found.append(f"preset-apply: overrides for {', '.join(map(repr, extra))} match no effect in preset "
                         f"{op.get('name')!r} (it has {', '.join(sorted(saved)) or 'none'}); they are ignored")
    return found


def touched(before, after):
    """Visible layers that were added or changed, in ``after``."""
    old = {layer["id"]: layer for layer in before["layers"]}
    return [layer for layer in after["layers"]
            if layer["visible"] and layer.get("opacity", 1) > 0 and layer["type"] != "adjustment"
            and old.get(layer["id"]) != layer]


def needs_check(layer, canvas):
    """Whether a changed layer could be cut off or overflow: grouped layers (their bounds are local),
    text in a wrapping box, and anything reaching past the canvas edge."""
    x, y, w, h = layer["resolved_bounds"]
    boxed = layer["type"] == "text" and "width" in (layer.get("text_layout") or {})
    return bool(layer.get("parent")) or boxed or x < 0 or y < 0 or x + w > canvas["width"] or y + h > canvas["height"]


def placement(candidate, before, after):
    """Off-canvas layers, text that does not fit its box and text that spills out of its group."""
    from .checks import check_design

    layers = touched(before, after)[:MAX_LAYERS]
    if not layers:
        return []
    canvas = after["canvas"]
    index = {layer["id"]: layer for layer in after["layers"]}
    warnings = []
    # The full bounds check is skipped for the common case: top-level layers that sit inside the canvas.
    suspect = [layer["id"] for layer in layers if needs_check(layer, canvas)]
    report = check_design(candidate, checks=["bounds"], targets=suspect) if suspect else {"issues": []}
    for issue in report["issues"]:
        if issue["check"] != "bounds":
            continue
        box = issue.get("bounds")
        if box and "cut off by the canvas edge" in issue["message"] and issue["severity"] != "error":
            x, y, w, h = box
            seen = max(0, min(x + w, canvas["width"]) - max(x, 0)) * max(0, min(y + h, canvas["height"]) - max(y, 0))
            if w * h and 1 - seen / (w * h) <= OUTSIDE_FRACTION:
                continue  # a small bleed is normal for artwork
        suffix = f" (bounds {[round(v) for v in box]})" if box else ""
        warnings.append(issue["message"] + suffix)
    for layer in layers:
        parent = index.get(layer.get("parent"))
        if layer["type"] != "text" or parent is None or "content_width" not in parent:
            continue
        x, y, w, h = layer["resolved_bounds"]
        cw, ch = parent["content_width"], parent["content_height"]
        if x < -1 or y < -1 or x + w > cw + 1 or y + h > ch + 1:
            warnings.append(f"text {layer['name']!r} extends outside its group {parent['name']!r} ({cw}×{ch}); "
                            "groups do not clip, so it draws past the group's box")
    return warnings
