"""Auto-layout stacks and hide-if-empty text: a layout that reacts to empty content.

A text layer with ``hide_if_empty`` is not drawn while its text, after ``${variable}`` substitution,
is empty or blank. A group with a ``stack`` setting lays its members out in a column, a row (wrapping
onto new rows with ``wrap``) or a grid of columns, with the flexbox and grid vocabulary of CSS:
``justify`` distributes members along the stack (start, center, end, space-between, space-around,
space-evenly), ``align`` places them across it (start, center, end, stretch), a member's ``stack_grow``
shares the free space and its ``stack_span`` spans grid columns. Members that are hidden, or collapsed
because they are empty, take no space, so the rest reflow. Both are resolved every time the document is
laid out (render, export, check, inspect), so changing a variable at export time re-flows the design;
nothing is stored but the settings, and stretched or grown sizes exist only on the resolved copies.
Stack members are positioned by the stack, not by hand.
"""

from argparse import BooleanOptionalAction
import re

from .errors import VixlError, require
from .model import MAX_LAYERS, finite

TYPES = ("stack",)
DIRECTIONS = ("vertical", "horizontal", "grid")
ALIGNS = ("start", "center", "end")
JUSTIFY = (*ALIGNS, "space-between", "space-around", "space-evenly")
ALIGN = (*ALIGNS, "stretch")
EXTRAS = {"size", "background", "radius", "stroke", "stroke_width", "wrap", "columns", "row_gap"}
DEFAULTS = {"direction": "vertical", "gap": 0, "padding": 0, "align": "start", "justify": "start"}
# Operation field -> the member layer field it sets, and the value that means "not set".
MEMBER_FIELDS = {"grow": ("stack_grow", 0), "span": ("stack_span", 1)}
MAX_COLUMNS = 64
# Members a stack may resize (stretch, grow, a grid cell) without distorting them; text only takes a new width.
# A group would scale its contents and a photo would distort, so those keep their size inside a larger slot.
RESIZABLE = ("shape", "solid", "gradient", "frame")
FR = re.compile(r"^\d+(?:\.\d+)?fr$")
# Operations that set a layer's position, which a stack decides for its members.
POSITIONING = ("move", "align", "distribute", "constrain", "unconstrain")


def schemas(add):
    from .schema import S, B, SIZE, enum, field

    refs = {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS, "uniqueItems": True}
    amount = {"type": "number", "minimum": 0}
    spacing = {"oneOf": [amount, {"type": "string", "pattern": r"^\d+(?:\.\d+)?u$"}]}
    track = {"oneOf": [{"type": "number", "minimum": 1}, {"type": "string", "pattern": FR.pattern}]}
    add(
        "stack",
        {
            "name": {**S, "description": "Name for the new group when targets is given."},
            "targets": {**refs, "description": "Layers to group and stack in one step (needs name); "
                        "omit to configure the existing group in target."},
            "width": {**SIZE, "description": "Width of the stack's box, which members are laid out in: pixels or "
                      "a percentage of the canvas or parent group (default: the group's current box)."},
            "height": {**SIZE, "description": "Height of the stack's box: pixels or a percentage."},
            "direction": {**enum(*DIRECTIONS), "description": "CSS flex-direction: vertical lays members out top to "
                          "bottom (default, a column), horizontal left to right (a row); grid places them in "
                          "columns, row by row (CSS grid)."},
            "gap": field(spacing, "Pixels or shared spacing units (2u) between members (between columns in a grid); "
                         "hidden and empty members take none. New house-style stacks default to 2u."),
            "row_gap": field(spacing, "Between rows of a grid or of a wrapping row stack: pixels or units such as "
                             "2u (default: gap)."),
            "padding": {"oneOf": [amount, {"type": "object", "properties": {k: amount for k in ("top", "right", "bottom", "left")}, "additionalProperties": False}], "description": "Uniform pixels or per-side padding."},
            "size": {**enum("fixed", "hug"), "description": "hug follows visible content and per-side padding on "
                     "every render (a grid or wrapping row keeps its width and hugs its height)."},
            "background": {**S, "description": "Background fill color for a generated rectangle that follows the stack."},
            "radius": {**amount, "description": "Corner radius of the stack background in pixels."},
            "stroke": {**S, "description": "Outline color of the stack background."},
            "stroke_width": {**amount, "description": "Outline thickness of the stack background in pixels."},
            "align": {**enum(*ALIGN), "description": "CSS align-items, across the stack: start, center or end of "
                      "the box, or stretch (text wraps to the box's width; shapes, solids, gradients and frames "
                      "fill it). With wrap it also places the block of rows; in a grid it places members "
                      "vertically in their row."},
            "justify": {**enum(*JUSTIFY), "description": "CSS justify-content, along the stack: start, center or "
                        "end packs members together; space-between puts the first and last at the ends and spreads "
                        "the rest, space-around and space-evenly share the free space around them. In a grid it "
                        "places members horizontally in their cells (start, center or end)."},
            "wrap": field(B, "CSS flex-wrap for horizontal stacks: members that do not fit continue on a new row, "
                          "row_gap below; justify applies to each row."),
            "columns": {"oneOf": [{"type": "integer", "minimum": 1, "maximum": MAX_COLUMNS},
                                  {"type": "array", "items": track, "minItems": 1, "maxItems": MAX_COLUMNS}],
                        "description": "Grid columns (CSS grid-template-columns): a count of equal columns, or "
                                       "widths such as [\"1fr\", \"2fr\"] or [240, \"1fr\"]: pixels, and fr shares "
                                       "of the width the pixel columns and gaps leave."},
            "grow": {"type": "object", "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1000},
                     "description": "CSS flex-grow per member, {member name or ID: weight}: growing members share "
                                    "the stack's free space along it by weight (shapes, solids, gradients and frames "
                                    "fill their share, text takes it as width in a row); 0 removes."},
            "span": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 1, "maximum": MAX_COLUMNS},
                     "description": "Grid: columns a member spans, {member name or ID: count} (CSS grid-column: "
                                    "span N); 1 removes."},
            "hide_if_empty": {**B, "description": "Collapse the whole stack when every member is hidden or empty."},
            "remove": {**B, "description": "Release the members: they keep their current positions and sizes."},
        },
        description="Auto-layout like CSS flexbox and grid: a group's members in a column, row or grid. Hidden "
        "members and empty hide_if_empty text take no space, so the rest reflow.",
    )


def validate_columns(columns):
    if isinstance(columns, list):
        require(1 <= len(columns) <= MAX_COLUMNS, f"A grid has 1-{MAX_COLUMNS} columns", field="columns")
        for item in columns:
            require((isinstance(item, str) and FR.fullmatch(item)) or (isinstance(item, (int, float))
                    and not isinstance(item, bool) and 1 <= item <= 16384),
                    f"Grid columns are pixel widths or fr shares such as '1fr'; got {item!r}", field="columns")
    else:
        require(isinstance(columns, int) and not isinstance(columns, bool) and 1 <= columns <= MAX_COLUMNS,
                f"columns is a count from 1 to {MAX_COLUMNS} or a list of widths", field="columns")


def validate_layer(layer):
    stack = layer.get("stack")
    if stack is not None:
        require(layer["type"] == "group", "Only groups can be stacks", "invalid_project")
        require(
            isinstance(stack, dict) and set(stack) <= set(DEFAULTS) | EXTRAS, "Invalid stack settings", "invalid_project"
        )
        direction = stack.get("direction", "vertical")
        require(direction in DIRECTIONS, "Invalid stack direction", "invalid_project")
        for key in ("gap", "row_gap"):
            finite(stack.get(key, 0), f"stack {key}", 0, 16384)
        padding_sides(stack.get("padding", 0))
        require(stack.get("size", "fixed") in ("fixed", "hug"), "Invalid stack size")
        for key in ("radius", "stroke_width"):
            finite(stack.get(key, 0), key, 0, 16384)
        require(stack.get("align", "start") in ALIGN, "Invalid stack align", "invalid_project", field="align",
                allowed=list(ALIGN))
        require(stack.get("justify", "start") in JUSTIFY, "Invalid stack justify", "invalid_project",
                field="justify", allowed=list(JUSTIFY))
        require(isinstance(stack.get("wrap", False), bool), "wrap is true or false", field="wrap")
        require(not stack.get("wrap") or direction == "horizontal",
                "wrap breaks a horizontal stack into rows; a grid wraps by its columns", field="wrap")
        require(("columns" in stack) == (direction == "grid"),
                "A grid stack needs columns, and only a grid takes them (direction: grid)", field="columns")
        if direction == "grid":
            validate_columns(stack["columns"])
            require(stack.get("justify", "start") in ALIGNS, "In a grid, justify places members in their "
                    "cells: start, center or end", field="justify", allowed=list(ALIGNS))
    if "stack_grow" in layer:
        finite(layer["stack_grow"], "stack_grow", 0, 1000)
    if "stack_span" in layer:
        require(isinstance(layer["stack_span"], int) and not isinstance(layer["stack_span"], bool)
                and 1 <= layer["stack_span"] <= MAX_COLUMNS, f"stack_span is a column count from 1 to {MAX_COLUMNS}",
                "invalid_project")
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
        from .render import resolved_layers

        # Keep the layout as it is now: write the stacked sizes and positions into the members.
        settled = {item["id"]: item for item in resolved_layers(project)}
        members = [member for member in project.state["layers"] if member.get("parent") == group["id"]]
        for member in members:
            keep_size(member, settled[member["id"]])
            member.pop("stack_grow", None)
            member.pop("stack_span", None)
        bounds = resolve_layout(project)
        for member in members:
            member["constraints"] = {}
            member["x"], member["y"] = stored_origin(member, bounds[member["id"]][:2])
        if group["stack"].get("size") == "hug":
            for key in ("width", "height", "content_width", "content_height"):
                group[key] = settled[group["id"]][key]
            for member in members:
                if member.get("stack_background") == group["id"]:
                    member.update(width=settled[group["id"]]["content_width"],
                                  height=settled[group["id"]]["content_height"])
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
    from .craft import body_size, resolve_space
    defaults = dict(DEFAULTS)
    defaults["gap"] = resolve_space("2u", body_size(project))
    settings = {**defaults, **group.get("stack", {}), **{k: op[k] for k in set(DEFAULTS) | EXTRAS if k in op}}
    if settings["direction"] != "grid":
        require("columns" not in op, "columns belong to a grid: set direction: grid", field="columns")
        settings.pop("columns", None)
    if settings["direction"] != "horizontal":
        require(not op.get("wrap"), "wrap breaks a horizontal stack into rows; a grid wraps by its columns",
                field="wrap")
        settings.pop("wrap", None)
    if settings["direction"] == "grid" and "justify" not in op and settings["justify"] not in ALIGNS:
        settings["justify"] = "start"
    for key in ("gap", "row_gap"):
        if key in settings:
            settings[key] = resolve_space(settings[key], body_size(project))
    group["stack"] = settings
    if "hide_if_empty" in op:
        group["hide_if_empty"] = op["hide_if_empty"]
    validate_layer(group)
    for key, (name, default) in MEMBER_FIELDS.items():
        for ref, value in (op.get(key) or {}).items():
            member = project.layer(ref)
            require(member.get("parent") == group["id"] and not member.get("stack_background"),
                    f"{key}: {member['name']!r} is not a member of the stack {group['name']!r}", field=key)
            if value == default:
                member.pop(name, None)
            else:
                member[name] = value
            validate_layer(member)
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


def collapse(layers, project=None):
    """Resolve hide_if_empty and stack layout on the resolved layer copies (``render.resolved_layers``).
    ``project`` measures text that a stack re-wraps (stretch, grow, a grid cell); without it text keeps its box."""
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
            place(group, shown, project)
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


def distribute(extents, room, gap, justify, origin=0.0):
    """Start offsets along a line for members of these extents (CSS justify-content). When the members overflow,
    space-between packs them at the start and space-around and space-evenly centre them, as CSS does."""
    count = len(extents)
    free = room - (sum(extents) + gap * max(0, count - 1))
    between = gap
    if justify == "space-between" and count > 1 and free > 0:
        start, between = 0, gap + free / (count - 1)
    elif justify == "space-around" and free > 0:
        start, between = free / (2 * count), gap + free / count
    elif justify == "space-evenly" and free > 0:
        start, between = free / (count + 1), gap + free / (count + 1)
    else:
        start = {"center": free / 2, "end": free, "space-around": free / 2, "space-evenly": free / 2}.get(justify, 0)
    offsets, cursor = [], origin + start
    for extent in extents:
        offsets.append(cursor)
        cursor += extent + between
    return offsets


def cross(extent, room, align):
    """Offset of a member across a line of ``room`` (CSS align-items); a stretched member starts at 0."""
    return {"center": (room - extent) / 2, "end": room - extent}.get(align, 0)


def grow(extents, room, gap, weights):
    """Extents after members with a grow weight share the free space of a line (CSS flex-grow)."""
    total = sum(weights)
    free = room - (sum(extents) + gap * max(0, len(extents) - 1))
    if total <= 0 or free <= 0:
        return list(extents)
    return [extent + free * weight / total for extent, weight in zip(extents, weights)]


def rows(extents, room, gap):
    """Indexes of the members on each row when a row of ``room`` wraps (CSS flex-wrap)."""
    lines, current, used = [], [], 0.0
    for index, extent in enumerate(extents):
        need = used + gap + extent if current else extent
        if current and need > room + 0.5:
            lines.append(current)
            current, used = [index], extent
        else:
            current.append(index)
            used = need
    return lines + [current] if current else lines


def fill(item, axis, length, project):
    """Give a resolved member copy ``length`` along ``axis`` (0 width, 1 height); True when it took it. Text takes
    a new wrapping width and its height follows; shapes, solids, gradients and frames take the length. Rotated,
    skewed and repeated members and every other kind keep their size."""
    length = max(1, round(length))  # whole pixels, so stretched and grown edges stay crisp
    if (item.get("rotation", 0) % 360 or item.get("skew_x") or item.get("skew_y") or item.get("affine")
            or item.get("repeat")):
        return False
    if item["type"] == "text":
        settings = dict(item.get("text_layout") or {})
        if axis != 0 or project is None or settings.get("fit") or settings.get("path") \
                or settings.get("warp", "none") != "none":
            return False
        from .checks import boxed_text_need

        settings.pop("height", None)
        settings["width"] = length
        item.update(text_layout=settings, auto_size=False, width=length)
        need = boxed_text_need(project, item)
        if need:
            item["height"] = max(1, need[1])
        return True
    if item["type"] in RESIZABLE:
        item["width" if axis == 0 else "height"] = length
        return True
    return False


def keep_size(member, resolved):
    """Write a stretched or grown size from the resolved copy into the stored member (stack remove)."""
    if (resolved["width"], resolved["height"]) == (member["width"], member["height"]):
        return
    if member["type"] == "text" and not resolved.get("auto_size", True):
        member.update(auto_size=False, text_layout=resolved.get("text_layout", {}), width=resolved["width"],
                      height=resolved["height"])
    elif member["type"] in RESIZABLE:
        member.update(width=resolved["width"], height=resolved["height"])


def place(group, shown, project=None):
    from .render import stored_origin, transformed_size

    settings = {**DEFAULTS, **group["stack"]}
    if settings["direction"] == "grid":
        place_grid(group, shown, settings, project)
        return
    vertical = settings["direction"] == "vertical"
    along, across = (1, 0) if vertical else (0, 1)
    top, right, bottom, left = padding_sides(settings["padding"])
    gap = settings["gap"]
    row_gap = settings.get("row_gap", gap)
    before, after = ((top, bottom), (left, right)) if vertical else ((left, right), (top, bottom))
    hug = settings.get("size") == "hug"
    wrap = bool(settings.get("wrap")) and not vertical
    stretch = settings["align"] == "stretch"
    box = (group["content_width"], group["content_height"])
    if stretch and not hug and not wrap:
        for item in shown:
            fill(item, across, box[across] - sum(after), project)
    sizes = [list(transformed_size(item)) for item in shown]
    lines = rows([size[along] for size in sizes], box[along] - sum(before), gap) if wrap else [list(range(len(shown)))]
    if stretch and (hug or wrap):
        # Without a fixed box across, a stretched member takes its line's extent (the largest member on it).
        for line in lines:
            extent = max(sizes[i][across] for i in line)
            for i in line:
                if sizes[i][across] < extent and fill(shown[i], across, extent, project):
                    sizes[i] = list(transformed_size(shown[i]))
    # A member's slot along the line is its size, or more when it grows. A member that cannot be resized sits at
    # the start of its larger slot, so a growing photo or group leaves space instead of distorting.
    slots = [size[along] for size in sizes]
    weights = [max(0, item.get("stack_grow", 0)) for item in shown]
    if any(weights) and (wrap or not hug):
        for line in lines:
            grown = grow([slots[i] for i in line], box[along] - sum(before), gap, [weights[i] for i in line])
            for i, slot in zip(line, grown):
                if slot != slots[i]:
                    slots[i] = slot
                    if fill(shown[i], along, slot, project):
                        sizes[i] = list(transformed_size(shown[i]))
    extents = [max(sizes[i][across] for i in line) if line else 0 for line in lines]
    if hug:
        dimensions = [0, 0]
        if wrap:
            dimensions[along] = box[along]
            dimensions[across] = max(1, int(sum(extents) + row_gap * max(0, len(lines) - 1) + sum(after) + 0.5))
        else:
            used = sum(slots) + gap * max(0, len(shown) - 1)
            dimensions[along] = max(1, int(used + sum(before) + 0.5))
            dimensions[across] = max(1, int(max(extents, default=0) + sum(after) + 0.5))
        group.update(width=dimensions[0], height=dimensions[1], content_width=dimensions[0], content_height=dimensions[1])
        box = (group["content_width"], group["content_height"])
    room_along, room_across = box[along] - sum(before), box[across] - sum(after)
    line_start = after[0]
    if wrap:
        line_start += cross(sum(extents) + row_gap * max(0, len(lines) - 1), room_across, settings["align"])
    for number, line in enumerate(lines):
        offsets = distribute([slots[i] for i in line], room_along, gap, settings["justify"], before[0])
        room = extents[number] if wrap else room_across
        for i, cursor in zip(line, offsets):
            side = line_start + cross(sizes[i][across], room, settings["align"])
            point = (side, cursor) if vertical else (cursor, side)
            item = shown[i]
            item["constraints"] = {}
            # Whole pixels, so equal gaps stay equal after layout bounds are rounded.
            item["x"], item["y"] = stored_origin(item, (int(point[0] + 0.5), int(point[1] + 0.5)))
        if wrap:
            line_start += extents[number] + row_gap


def place_grid(group, shown, settings, project):
    """Lay members out row by row in the grid's columns (CSS grid auto-placement): a member spanning more
    columns than are left on a row starts the next one. A row is as tall as its tallest member."""
    from .guides import tracks
    from .render import stored_origin, transformed_size

    top, right, bottom, left = padding_sides(settings["padding"])
    gap = settings["gap"]
    row_gap = settings.get("row_gap", gap)
    columns = settings["columns"]
    count = columns if isinstance(columns, int) else len(columns)
    hug = settings.get("size") == "hug"
    width = group["content_width"]
    if hug and isinstance(columns, list) and not any(isinstance(item, str) for item in columns):
        width = max(1, int(sum(columns) + gap * (count - 1) + left + right + 0.5))
    cells = tracks(max(1, width - left - right), columns, gap)
    placed, row, column = [], 0, 0
    for item in shown:
        span = min(int(item.get("stack_span", 1)), count)
        if column + span > count:
            row, column = row + 1, 0
        start, end = cells[column][0], cells[column + span - 1][0] + cells[column + span - 1][1]
        placed.append((item, row, start, end - start))
        column += span
    stretch = settings["align"] == "stretch"
    sizes = []
    for item, _, _, cell in placed:
        size = transformed_size(item)
        # Text never runs out of its cell: wider text wraps at the cell's width.
        if (stretch or (item["type"] == "text" and size[0] > cell + 0.5)) and fill(item, 0, cell, project):
            size = transformed_size(item)
        sizes.append(list(size))
    heights = [0.0] * (row + 1 if placed else 0)
    for (_, number, _, _), size in zip(placed, sizes):
        heights[number] = max(heights[number], size[1])
    if stretch:
        for index, (item, number, _, _) in enumerate(placed):
            if item["type"] != "text" and sizes[index][1] < heights[number] and fill(item, 1, heights[number], project):
                sizes[index] = list(transformed_size(item))
    if hug:
        height = max(1, int(sum(heights) + row_gap * max(0, len(heights) - 1) + top + bottom + 0.5))
        group.update(width=width, height=height, content_width=width, content_height=height)
    starts, cursor = [], top
    for height in heights:
        starts.append(cursor)
        cursor += height + row_gap
    for (item, number, start, cell), size in zip(placed, sizes):
        x = left + start + cross(size[0], cell, settings["justify"])
        y = starts[number] + cross(size[1], heights[number], settings["align"])
        item["constraints"] = {}
        item["x"], item["y"] = stored_origin(item, (int(x + 0.5), int(y + 0.5)))


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser, spacing

    p = Parser(prog="vixl stack")
    p.add_argument("target", help="the group to stack, or the new group's name with --targets")
    p.add_argument("--targets", nargs="+", help="layers to group and stack in one step")
    p.add_argument("--direction", choices=DIRECTIONS)
    p.add_argument("--size", choices=("fixed", "hug"))
    p.add_argument("--background")
    p.add_argument("--radius", type=float)
    p.add_argument("--stroke")
    p.add_argument("--stroke-width", type=float)
    p.add_argument("--gap", type=spacing, help="pixels, or units such as 2u (one unit is half the body size)")
    p.add_argument("--padding", type=float)
    p.add_argument("--width", type=int, help="width of the stack's box in pixels")
    p.add_argument("--height", type=int, help="height of the stack's box in pixels")
    p.add_argument("--align", choices=ALIGN)
    p.add_argument("--justify", choices=JUSTIFY)
    p.add_argument("--wrap", action=BooleanOptionalAction, default=None, help="horizontal: continue on new rows")
    p.add_argument("--columns", type=grid_columns, help="grid: a count, or widths such as 1fr,2fr or 240,1fr")
    p.add_argument("--row-gap", type=spacing, help="grid or wrapping rows: pixels or units such as 2u")
    p.add_argument("--grow", nargs="+", type=member_value(float), metavar="MEMBER=WEIGHT",
                   help="members that share the free space, e.g. body=1")
    p.add_argument("--span", nargs="+", type=member_value(int), metavar="MEMBER=COLUMNS",
                   help="grid members spanning columns, e.g. hero=2")
    p.add_argument("--hide-if-empty", action=BooleanOptionalAction, default=None,
                   help="collapse the whole stack when every member is hidden or empty")
    p.add_argument("--remove", action="store_true", default=None, help="release the members in place")
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if "targets" in data:
        data["name"] = data.pop("target")
    for key in ("grow", "span"):
        if key in data:
            data[key] = dict(data[key])
    return {"type": "stack", **data}


def grid_columns(value):
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 1 and parts[0].isdigit():
        return int(parts[0])
    return [part if FR.fullmatch(part) else float(part) for part in parts]


def member_value(kind):
    def parse(value):
        name, separator, amount = value.rpartition("=")
        if not separator or not name:
            raise VixlError("usage_error", f"Expected MEMBER=VALUE, not {value!r}")
        return name, kind(amount)
    return parse


def scale_settings(layer, factor):
    """Scale stack pixel settings on a preview copy alongside its children."""
    settings = layer.get("stack")
    if not settings:
        return
    for key in ("gap", "row_gap", "padding", "radius", "stroke_width"):
        if key in settings:
            value = settings[key]
            settings[key] = {side: amount * factor for side, amount in value.items()} if isinstance(value, dict) else value * factor
    if isinstance(settings.get("columns"), list):
        settings["columns"] = [item if isinstance(item, str) else item * factor for item in settings["columns"]]
