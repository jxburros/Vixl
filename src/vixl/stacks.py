"""Auto-layout stacks and hide-if-empty text: a layout that reacts to empty content.

A text layer with ``hide_if_empty`` is not drawn while its text, after ``${variable}`` substitution,
is empty or blank. A group with a ``stack`` setting lays its members out in a column or a row. Members
that are hidden, or collapsed because they are empty, take no space, so the rest reflow and stay
centred (or start- or end-aligned) in the group's box. Both are resolved every time the document is
laid out (render, export, check, inspect), so changing a variable at export time re-flows the design;
nothing is stored but the settings. Stack members are positioned by the stack, not by hand.
"""

from argparse import BooleanOptionalAction

from .errors import VixlError, require
from .model import finite

TYPES = ("stack",)
DIRECTIONS = ("vertical", "horizontal")
ALIGNS = ("start", "center", "end")
EXTRAS = {"size", "background", "radius", "stroke", "stroke_width"}
DEFAULTS = {"direction": "vertical", "gap": 0, "padding": 0, "align": "start", "justify": "start"}
# Operations that set a layer's position, which a stack decides for its members.
POSITIONING = ("move", "align", "distribute", "constrain", "unconstrain")


def schemas(add):
    from .schema import S, B, SIZE, enum

    refs = {"type": "array", "items": S, "minItems": 1, "maxItems": 512, "uniqueItems": True}
    amount = {"type": "number", "minimum": 0}
    add(
        "stack",
        {
            "name": {**S, "description": "Name for the new group when targets is given."},
            "targets": {**refs, "description": "Layers to group and stack in one step (needs name); "
                        "omit to configure the existing group in target."},
            "width": {**SIZE, "description": "Width of the stack's box, which members are laid out in: pixels or "
                      "a percentage of the canvas or parent group (default: the group's current box)."},
            "height": {**SIZE, "description": "Height of the stack's box: pixels or a percentage."},
            "direction": {**enum(*DIRECTIONS), "description": "vertical lays members out top to bottom (default), "
                          "horizontal left to right."},
            "gap": {**amount, "description": "Pixels between members; hidden and empty members take none."},
            "padding": {"oneOf": [amount, {"type": "object", "properties": {k: amount for k in ("top", "right", "bottom", "left")}, "additionalProperties": False}], "description": "Uniform pixels or per-side padding."},
            "size": {**enum("fixed", "hug"), "description": "hug follows visible content and per-side padding on every render."},
            "background": {**S, "description": "Background fill color for a generated rectangle that follows the stack."},
            "radius": {**amount, "description": "Corner radius of the stack background in pixels."},
            "stroke": {**S, "description": "Outline color of the stack background."},
            "stroke_width": {**amount, "description": "Outline thickness of the stack background in pixels."},
            "align": {**enum(*ALIGNS), "description": "Across the stack: start, center or end of the box."},
            "justify": {**enum(*ALIGNS), "description": "Along the stack: start packs members at the start of "
                        "the box, center keeps them centred as members come and go, end packs them at the end."},
            "hide_if_empty": {**B, "description": "Collapse the whole stack when every member is hidden or empty."},
            "remove": {**B, "description": "Release the members: they keep their current positions."},
        },
        description="Auto-layout: stack a group's members in a column or row. Hidden members and text layers "
        "with hide_if_empty whose text is empty take no space, so the rest reflow and re-centre.",
    )


def validate_layer(layer):
    stack = layer.get("stack")
    if stack is not None:
        require(layer["type"] == "group", "Only groups can be stacks", "invalid_project")
        require(
            isinstance(stack, dict) and set(stack) <= set(DEFAULTS) | EXTRAS, "Invalid stack settings", "invalid_project"
        )
        require(stack.get("direction", "vertical") in DIRECTIONS, "Invalid stack direction", "invalid_project")
        finite(stack.get("gap", 0), "stack gap", 0, 16384)
        padding_sides(stack.get("padding", 0))
        require(stack.get("size", "fixed") in ("fixed", "hug"), "Invalid stack size")
        for key in ("radius", "stroke_width"):
            finite(stack.get(key, 0), key, 0, 16384)
        for key in ("align", "justify"):
            require(stack.get(key, "start") in ALIGNS, f"Invalid stack {key}", "invalid_project")
    if "hide_if_empty" in layer:
        require(
            isinstance(layer["hide_if_empty"], bool) and layer["type"] in ("text", "group"),
            "hide_if_empty is a boolean on text layers and stacks",
            "invalid_project",
        )


def execute(project, op):
    from .design import execute_design
    from .render import resolve_layout, stored_origin

    if "targets" in op:
        require(op.get("name"), "A new stack needs a name for its group", field="name")
        execute_design(project, {"type": "group", "name": op["name"], "targets": op["targets"]})
        group = project.layer()
    else:
        group = project.layer(op.get("target"))
        require(
            group["type"] == "group",
            f"{group['name']!r} is a {group['type']} layer, but a stack is a group: group the layers first, or "
            "pass targets and name to group and stack them in one step",
            field="target",
        )
    if op.get("remove"):
        require("stack" in group, f"{group['name']!r} is not a stack", field="target")
        # Keep the layout as it is now: write the stacked positions into the members.
        bounds = resolve_layout(project)
        for member in project.state["layers"]:
            if member.get("parent") == group["id"]:
                member["constraints"] = {}
                member["x"], member["y"] = stored_origin(member, bounds[member["id"]][:2])
        if group["stack"].get("size") == "hug":
            from .render import resolved_layers
            settled = next(item for item in resolved_layers(project) if item["id"] == group["id"])
            for key in ("width", "height", "content_width", "content_height"):
                group[key] = settled[key]
            for member in project.state["layers"]:
                if member.get("stack_background") == group["id"]:
                    member.update(width=settled["content_width"], height=settled["content_height"])
                    member.pop("stack_background", None)
        group.pop("stack")
        group.pop("hide_if_empty", None)
        return
    if "width" in op or "height" in op:
        require(
            (group["width"], group["height"]) == (group["content_width"], group["content_height"])
            and not group["rotation"],
            f"{group['name']!r} is scaled or rotated; reset that before setting the stack's box size",
            field="width",
        )
        width, height = op.get("width", group["width"]), op.get("height", group["height"])
        project.limits.size(width, height, vector=True)
        group.update(width=width, height=height, content_width=width, content_height=height)
    group["stack"] = {**DEFAULTS, **group.get("stack", {}), **{k: op[k] for k in set(DEFAULTS) | EXTRAS if k in op}}
    if "hide_if_empty" in op:
        group["hide_if_empty"] = op["hide_if_empty"]
    validate_layer(group)
    if "background" in op or "stroke" in op:
        from .operations import execute as apply
        bg = next((item for item in project.state["layers"] if item.get("stack_background") == group["id"]), None)
        if bg is None:
            apply(project, {"type": "shape", "name": group["name"] + "/background", "shape": "rounded-rectangle",
                            "width": max(1, group["width"]), "height": max(1, group["height"]), "fill": op.get("background", "transparent")})
            bg = project.layer()
            bg.update(parent=group["id"], stack_background=group["id"])
            project.state["layers"].remove(bg)
            project.state["layers"].insert(project.state["layers"].index(group), bg)
        bg.update(fill=group["stack"].get("background", "transparent"), radius=group["stack"].get("radius", 0),
                  stroke=group["stack"].get("stroke", "transparent"), stroke_width=group["stack"].get("stroke_width", 1))
        project.state["active_layer"] = group["id"]


def guard(project, op, target):
    """Positioning a stack member by hand would silently do nothing, so refuse and say what to use."""
    refs = op.get("targets") if op["type"] in ("align", "distribute") and op.get("targets") else [target]
    for ref in refs:
        layer = project.layer(ref)
        parent = project.layer(layer["parent"]) if layer.get("parent") else None
        if parent is not None and "stack" in parent:
            raise VixlError(
                "stack_managed",
                f"{layer['name']!r} is positioned by the stack {parent['name']!r}, so {op['type']} would have no "
                "effect: change the stack (stack operation: direction, gap, padding, align, justify), reorder or "
                "resize the member, or release the layers with stack remove: true to place them by hand",
                field="target",
                suggestions=["stack"],
            )


def collapsed(project):
    """IDs of layers that take no space right now: hidden, or collapsed because they are empty."""
    from .render import resolved_layers

    return {item["id"] for item in resolved_layers(project) if not item["visible"]}


def collapse(layers):
    """Resolve hide_if_empty and stack layout on the resolved layer copies (``render.resolved_layers``)."""
    if not any(layer.get("hide_if_empty") or "stack" in layer for layer in layers):
        return
    for layer in layers:
        if layer["type"] == "text" and layer.get("hide_if_empty") and not layer["text"].strip():
            layer["visible"] = False
    index = {layer["id"]: layer for layer in layers}
    members = {}
    for layer in layers:
        members.setdefault(layer.get("parent"), []).append(layer)

    def depth(layer):
        count = 0
        while layer.get("parent") in index and count < 64:
            layer, count = index[layer["parent"]], count + 1
        return count

    # Innermost groups first, so a nested stack's visibility is settled before its parent lays it out.
    groups = [item for item in layers if item["type"] == "group" and (item.get("hide_if_empty") or "stack" in item)]
    for group in sorted(groups, key=depth, reverse=True):
        shown = [item for item in members.get(group["id"], []) if item["visible"] and item["type"] != "adjustment" and not item.get("stack_background")]
        if group.get("hide_if_empty") and not shown:
            group["visible"] = False
        if "stack" in group:
            place(group, shown)
            for background in members.get(group["id"], []):
                if background.get("stack_background"):
                    background.update(x=0, y=0, width=group["content_width"], height=group["content_height"],
                                      radius=group["stack"].get("radius", 0))


def padding_sides(value):
    if isinstance(value, dict):
        require(not set(value) - {"top", "right", "bottom", "left"}, "Unknown padding side")
        sides = [value.get(k, 0) for k in ("top", "right", "bottom", "left")]
    else:
        sides = [value] * 4
    for side in sides:
        finite(side, "padding", 0, 16384)
    return sides


def place(group, shown):
    from .render import stored_origin, transformed_size

    settings = {**DEFAULTS, **group["stack"]}
    vertical = settings["direction"] == "vertical"
    sizes = [transformed_size(item) for item in shown]
    along, across = (1, 0) if vertical else (0, 1)
    top, right, bottom, left = padding_sides(settings["padding"])
    gap = settings["gap"]
    before, after = ((top, bottom), (left, right)) if vertical else ((left, right), (top, bottom))
    used = sum(size[along] for size in sizes) + gap * max(0, len(shown) - 1)
    if settings.get("size") == "hug":
        extent = max((size[across] for size in sizes), default=0)
        dimensions = [0, 0]
        dimensions[along] = max(1, int(used + sum(before) + 0.5))
        dimensions[across] = max(1, int(extent + sum(after) + 0.5))
        group.update(width=dimensions[0], height=dimensions[1], content_width=dimensions[0], content_height=dimensions[1])
    box = (group["content_width"], group["content_height"])
    room_along, room_across = box[along] - sum(before), box[across] - sum(after)

    def offset(room, extent, how):
        return {"start": 0, "center": (room - extent) / 2, "end": room - extent}[how]

    cursor = before[0] + offset(room_along, used, settings["justify"])
    for item, size in zip(shown, sizes):
        side = after[0] + offset(room_across, size[across], settings["align"])
        point = (side, cursor) if vertical else (cursor, side)
        item["constraints"] = {}
        # Whole pixels, so equal gaps stay equal after layout bounds are rounded.
        item["x"], item["y"] = stored_origin(item, (int(point[0] + 0.5), int(point[1] + 0.5)))
        cursor += size[along] + gap


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog="vixl stack")
    p.add_argument("target", help="the group to stack, or the new group's name with --targets")
    p.add_argument("--targets", nargs="+", help="layers to group and stack in one step")
    p.add_argument("--direction", choices=DIRECTIONS)
    p.add_argument("--size", choices=("fixed", "hug"))
    p.add_argument("--background")
    p.add_argument("--radius", type=float)
    p.add_argument("--stroke")
    p.add_argument("--stroke-width", type=float)
    p.add_argument("--gap", type=float)
    p.add_argument("--padding", type=float)
    p.add_argument("--width", type=int, help="width of the stack's box in pixels")
    p.add_argument("--height", type=int, help="height of the stack's box in pixels")
    p.add_argument("--align", choices=ALIGNS)
    p.add_argument("--justify", choices=ALIGNS)
    p.add_argument("--hide-if-empty", action=BooleanOptionalAction, default=None,
                   help="collapse the whole stack when every member is hidden or empty")
    p.add_argument("--remove", action="store_true", default=None, help="release the members in place")
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if "targets" in data:
        data["name"] = data.pop("target")
    return {"type": "stack", **data}


def scale_settings(layer, factor):
    """Scale stack pixel settings on a preview copy alongside its children."""
    settings = layer.get("stack")
    if not settings:
        return
    for key in ("gap", "padding", "radius", "stroke_width"):
        if key in settings:
            value = settings[key]
            settings[key] = {side: amount * factor for side, amount in value.items()} if isinstance(value, dict) else value * factor
