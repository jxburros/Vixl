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
            "padding": {**amount, "description": "Pixels kept clear inside the group box on every side."},
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
            isinstance(stack, dict) and set(stack) <= set(DEFAULTS), "Invalid stack settings", "invalid_project"
        )
        require(stack.get("direction", "vertical") in DIRECTIONS, "Invalid stack direction", "invalid_project")
        for key in ("gap", "padding"):
            finite(stack.get(key, 0), f"stack {key}", 0, 16384)
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
        project.limits.size(width, height)
        group.update(width=width, height=height, content_width=width, content_height=height)
    group["stack"] = {**DEFAULTS, **group.get("stack", {}), **{k: op[k] for k in DEFAULTS if k in op}}
    if "hide_if_empty" in op:
        group["hide_if_empty"] = op["hide_if_empty"]
    validate_layer(group)


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
        shown = [item for item in members.get(group["id"], []) if item["visible"] and item["type"] != "adjustment"]
        if group.get("hide_if_empty") and not shown:
            group["visible"] = False
        if "stack" in group and shown:
            place(group, shown)


def place(group, shown):
    from .render import stored_origin, transformed_size

    settings = {**DEFAULTS, **group["stack"]}
    vertical = settings["direction"] == "vertical"
    sizes = [transformed_size(item) for item in shown]
    along, across = (1, 0) if vertical else (0, 1)
    padding, gap = settings["padding"], settings["gap"]
    box = (group["content_width"], group["content_height"])
    room_along, room_across = box[along] - 2 * padding, box[across] - 2 * padding
    used = sum(size[along] for size in sizes) + gap * (len(shown) - 1)

    def offset(room, extent, how):
        return {"start": 0, "center": (room - extent) / 2, "end": room - extent}[how]

    cursor = padding + offset(room_along, used, settings["justify"])
    for item, size in zip(shown, sizes):
        side = padding + offset(room_across, size[across], settings["align"])
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
