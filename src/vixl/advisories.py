"""Advisories: problems an apply call can see cheaply, returned under ``warnings`` (never errors).

They cover text that spills off the canvas or out of its box and a valid field that changes nothing
for this shape, so a wrong guess does not look like success. Unknown fields and invalid values are
errors (schema.py, normalize.py), never advisories. These checks look only at the layers and
operations of this one call, so they add no noise about pre-existing problems. ``vixl_check`` remains the complete audit.
"""

MAX_WARNINGS = 12
MAX_LAYERS = 200
# A non-text layer may bleed past the canvas edge on purpose; warn when most of it is outside.
OUTSIDE_FRACTION = 0.25


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
        if "marker_size" in op:
            try:
                layer = candidate.layer(op.get("target") or op.get("name"))
            except Exception:  # noqa: BLE001 - a later operation may have deleted this layer
                layer = {}
            if (layer.get("marker_start", "none") != "none" or layer.get("marker_end", "none") != "none") and op["marker_size"] < 2 * layer.get("stroke_width", 1):
                found.append("marker_size is in local pixels, not a multiplier; use at least twice stroke_width "
                             "so the shaft does not hide the arrowhead")
        shape, name = op.get("shape"), repr(op.get("name", "shape"))
        if shape is None:  # editing an existing layer: its own shape decides what each field does
            try:
                shape = candidate.layer(op.get("target", op.get("layer"))).get("shape")
            except Exception:  # noqa: BLE001 - an unresolvable target is reported by the operation itself
                return found
        from .normalize import SHAPE_TYPES

        stored = shape
        shape = SHAPE_TYPES.get(shape, (shape,))[0] if isinstance(shape, str) else shape  # donut → arc, pill → ...
        from .shape_catalog import KINDS, SHAPE_ONLY, SHAPE_PARAMETERS

        for key in SHAPE_ONLY:
            if key in op and key not in SHAPE_PARAMETERS.get(stored, ()):
                readers = sorted(kind for kind, keys in SHAPE_PARAMETERS.items() if key in keys)
                found.append(f"shape {name}: {key} only shapes {_names(readers)}, not {stored!r}")
        if shape in KINDS:  # catalog shapes read their own parameters (burst/seal inner_radius, sides, radius ...)
            return found
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
        if issue["check"] != "bounds" or issue["severity"] == "info":
            continue  # Intentional bleed and marked crops are not warnings.
        box = issue.get("bounds")
        if box and "cut off by the canvas edge" in issue["message"] and issue["severity"] != "error":
            x, y, w, h = box
            seen = max(0, min(x + w, canvas["width"]) - max(x, 0)) * max(0, min(y + h, canvas["height"]) - max(y, 0))
            if w * h and 1 - seen / (w * h) <= OUTSIDE_FRACTION:
                continue  # a small bleed is normal for artwork
        suffix = f" (bounds {[round(v) for v in box]})" if box else ""
        if issue["message"] + suffix not in warnings:
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
