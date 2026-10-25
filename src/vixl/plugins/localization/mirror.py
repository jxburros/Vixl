"""Right-to-left mirroring of a layout, for ar, he and fa locales.

Each top-level layer is classified along x the way ``adapt-layout`` does (``adapt.infer``): a layer that spans
the canvas stays where it is, any other moves to the mirrored position (its left margin becomes its right
margin), and its inferred anchor flips through ``geometry.canonical_anchor`` (top-left becomes top-right; the
report lists each change). Layout constraints swap sides (``left: canvas.left+40`` becomes
``right: canvas.right-40``), and text alignment swaps left and right.
The glyph order of right-to-left text is already handled by the text shaper (bidi), so mirroring is layout only.
"""

import re

from ...geometry import ANCHORS, canonical_anchor

SIDES = {"left": "right", "right": "left"}
EXPRESSION = re.compile(r"^(.+)\.(left|right|top|bottom|center-x|center-y)([+-]\d+(?:\.\d+)?)?$")


def flip_anchor(value):
    """The horizontally mirrored anchor name (top-left -> top-right), or the value unchanged."""
    name = canonical_anchor(value)
    if name is None:
        return value
    fx, fy = ANCHORS[name]
    return next(key for key, (x, y) in ANCHORS.items() if (x, y) == (1 - fx, fy))


def flip_constraints(constraints, width):
    """Constraints mirrored left to right on a canvas ``width`` wide (inside a group, the group's content)."""
    result = {}
    for anchor, expression in constraints.items():
        key = SIDES.get(anchor, anchor)
        if anchor in ("top", "bottom", "center-y"):
            result[key] = expression
            continue
        if isinstance(expression, (int, float)) and not isinstance(expression, bool):
            result[key] = width - expression
            continue
        match = EXPRESSION.match(expression) if isinstance(expression, str) else None
        if match is None or match[1].startswith("guide:"):
            result[anchor] = expression
            continue
        ref, edge, offset = match.groups()
        edge = SIDES.get(edge, edge)
        number = -float(offset) if offset else 0
        text = "" if not number else f"{number:+g}"
        result[key] = f"{ref}.{edge}{text}"
    return result


def mirror(project, keep=()):
    """Mirror ``project`` (a candidate) in place. Returns ``[{layer, anchor?, align?, constraints?}]`` for the
    layers that moved or changed."""
    from ...adapt import _MODE, infer
    from ...render import resolve_layout

    names = {(fx, fy): name for name, (fx, fy) in ANCHORS.items()}
    fraction = {mode: value for value, mode in _MODE.items()}

    state = project.state
    width = state["canvas"]["width"]
    bounds = resolve_layout(project)
    changed, moves = [], []
    for layer in state["layers"]:
        if layer.get("name") in keep or layer.get("id") in keep:
            continue
        entry = {}
        if layer["type"] == "text" and layer.get("align") in SIDES:
            entry["align"] = f"{layer['align']} -> {SIDES[layer['align']]}"
            layer["align"] = SIDES[layer["align"]]
        constraints = layer.get("constraints") or {}
        horizontal = {"left", "right", "center-x"} & set(constraints)
        if horizontal:
            parent = layer.get("parent")
            span = width
            if parent:
                group = project.find_layer(parent)
                span = group.get("content_width", group.get("width", width)) if group else width
            layer["constraints"] = flip_constraints(constraints, span)
            entry["constraints"] = sorted(layer["constraints"])
        elif not layer.get("parent") and layer["id"] in bounds:
            x, y, w, h = bounds[layer["id"]]
            mode_x, mode_y = infer(x, w, width), infer(y, h, state["canvas"]["height"])
            if mode_x != "stretch":
                anchor = names[(fraction[mode_x], fraction.get(mode_y, 0.5))]
                flipped = flip_anchor(anchor)
                dx = (width - x - w) - x
                if abs(dx) > 0.5:
                    moves.append({"type": "move", "target": layer["id"], "x": round(dx, 3), "relative": True})
                    entry["anchor"] = anchor if flipped == anchor else f"{anchor} -> {flipped}"
        if entry:
            changed.append({"layer": layer["name"], **entry})
    if moves:
        project.apply(moves, detail="compact")
    return changed
