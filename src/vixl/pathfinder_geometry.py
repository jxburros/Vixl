"""Pathfinder layers as path geometry: operand shapes become outlines, ``booleans`` combines them.

``pathfinder_commands`` is what the SVG, PDF and PowerPoint exports draw for a pathfinder layer: one
compound path (``M L C Z`` commands, as ``geometry.parse_path`` returns them) in the layer's own
pixel space. It raises ``booleans.Unsupported`` when the layer's pixels are not just the combined
coverage of its operands' outlines (a stroked, translucent or effect-carrying operand); the export
then draws the layer as an image and lists the reason.
"""


from .booleans import KAPPA, Unsupported, combine_outlines

__all__ = ["Unsupported", "pathfinder_commands", "path_data"]


def _line(p, q):
    return None if p == q else (p, q)


def _close(points):
    """A closed polygon's line segments (a zero-length one is dropped)."""
    return [seg for seg in (_line(p, q) for p, q in zip(points, points[1:] + points[:1])) if seg]


def _ellipse(w, h):
    cx, cy, rx, ry = w / 2, h / 2, w / 2, h / 2
    kx, ky = KAPPA * rx, KAPPA * ry
    return [[((cx + rx, cy), (cx + rx, cy + ky), (cx + kx, cy + ry), (cx, cy + ry)),
             ((cx, cy + ry), (cx - kx, cy + ry), (cx - rx, cy + ky), (cx - rx, cy)),
             ((cx - rx, cy), (cx - rx, cy - ky), (cx - kx, cy - ry), (cx, cy - ry)),
             ((cx, cy - ry), (cx + kx, cy - ry), (cx + rx, cy - ky), (cx + rx, cy))]]


def _rounded(w, h, radius):
    r = max(0.0, min(radius, w / 2, h / 2))
    if r <= 0:
        return [_close([(0, 0), (w, 0), (w, h), (0, h)])]
    k = KAPPA * r
    segs = [((r, 0), (w - r, 0)), ((w - r, 0), (w - r + k, 0), (w, r - k), (w, r)), ((w, r), (w, h - r)),
            ((w, h - r), (w, h - r + k), (w - r + k, h), (w - r, h)), ((w - r, h), (r, h)),
            ((r, h), (r - k, h), (0, h - r + k), (0, h - r)), ((0, h - r), (0, r)),
            ((0, r), (0, r - k), (r - k, 0), (r, 0))]
    return [[seg for seg in segs if seg[0] != seg[-1]]]


def _from_commands(commands, sx, sy):
    """Closed contours of parsed SVG path commands (M L C Q Z), scaled; open subpaths close themselves."""
    contours, state = [], {"contour": [], "start": None, "current": None}

    def finish():
        contour, start, current = state["contour"], state["start"], state["current"]
        if contour and current != start:
            contour.append((current, start))
        if contour:
            contours.append(contour)
        state["contour"] = []

    for command, values in commands:
        pts = [(x * sx, y * sy) for x, y in zip(values[0::2], values[1::2])]
        if command == "M":
            finish()
            state["start"] = state["current"] = pts[0]
        elif command == "Z":
            finish()
            state["current"] = state["start"]
        else:
            contour, current = state["contour"], state["current"]
            if command == "L":
                if pts[0] != current:
                    contour.append((current, pts[0]))
                current = pts[0]
            elif command == "C":
                contour.append((current, *pts))
                current = pts[-1]
            else:  # Q: a run of quadratic control points, as an equivalent chain of cubics
                controls, end = pts[:-1], pts[-1]
                for i, ctrl in enumerate(controls):
                    target = ((ctrl[0] + controls[i + 1][0]) / 2, (ctrl[1] + controls[i + 1][1]) / 2) \
                        if i + 1 < len(controls) else end
                    c1 = (current[0] + 2 / 3 * (ctrl[0] - current[0]), current[1] + 2 / 3 * (ctrl[1] - current[1]))
                    c2 = (target[0] + 2 / 3 * (ctrl[0] - target[0]), target[1] + 2 / 3 * (ctrl[1] - target[1]))
                    contour.append((current, c1, c2, target))
                    current = target
            state["current"] = current
    finish()
    # A cubic whose control points sit on its end points is a straight line.
    return [[seg if len(seg) == 2 or seg[1] != seg[0] or seg[2] != seg[3] else (seg[0], seg[3]) for seg in c]
            for c in contours]


def shape_contours(item):
    """The outline of a shape layer (width × height, no stroke) as closed contours of segments."""
    from .geometry import parse_path, shape_path

    w, h = float(item["width"]), float(item["height"])
    from .shape_catalog import active
    if active(item) or item.get("distort"):
        from .vector_paths import pixel_path
        return _from_commands(parse_path(pixel_path(item)), 1, 1)
    shape = item.get("shape", "rectangle")
    if shape == "rectangle":
        return [_close([(0, 0), (w, 0), (w, h), (0, h)])]
    if shape in ("rounded-rectangle", "capsule"):
        return _rounded(w, h, item.get("radius", min(w, h) / (2 if shape == "capsule" else 5)))
    if shape == "ellipse":
        return _ellipse(w, h)
    path, view = shape_path(item)
    contours = _from_commands(parse_path(path), w / view[0], h / view[1])
    if any(not (-1e-9 <= x <= w + 1e-9 and -1e-9 <= y <= h + 1e-9) for contour in contours for seg in contour
           for x, y in seg):
        # A path is drawn inside its box: whatever its coordinates reach beyond the box is cut off.
        box = [_close([(0, 0), (w, 0), (w, h), (0, h)])]
        contours = combine_outlines([contours, box], MODES["intersect"])
    return contours


def placed(contours, item, x, y):
    """``contours`` of ``item`` (a rotated, flipped layer whose transformed box has its top-left at x, y)
    in its parent's coordinates, as the renderers place it."""
    from .render import transformed_size
    from .affine import layer_matrix

    tw, th = transformed_size(item)
    transform = layer_matrix(item, (x, y, tw, th))

    def move(p):
        result = transform @ [p[0], p[1], 1]
        return float(result[0]), float(result[1])

    return [[tuple(move(p) for p in seg) for seg in contour] for contour in contours]


MODES = {
    "union": lambda *inside: any(inside),
    "subtract": lambda first, *rest: first and not any(rest),
    "intersect": lambda *inside: all(inside),
    "exclude": lambda *inside: sum(inside) % 2 == 1,
    "minus-back": lambda first, *rest: bool(rest) and rest[-1] and not (first or any(rest[:-1])),
    "merge": lambda *inside: any(inside),
    "trim": lambda *inside: any(inside),
    "divide": lambda *inside: any(inside),
}


def check_operand(item, state):
    """Raise ``Unsupported`` for operands whose pixels are not just their outline's coverage."""
    from .design import resolve_color
    from .render import color

    if item.get("opacity", 1) != 1:
        raise Unsupported("an operand is translucent")
    if item.get("effects"):
        raise Unsupported("an operand has effects")
    if item.get("mask"):
        raise Unsupported("an operand has a mask")
    if any(style.get("enabled", True) for style in (item.get("styles") or {}).values()):
        raise Unsupported("an operand has layer styles")
    if item.get("repeat"):
        raise Unsupported("an operand has a repeat")
    if item["type"] == "shape":
        if item.get("shape") == "line":
            raise Unsupported("an operand is a line, which has no area")
        if color(resolve_color(item.get("fill", "white"), state))[3] != 255:
            raise Unsupported("an operand has a translucent fill")
        if color(resolve_color(item.get("stroke", "transparent"), state))[3] and item.get("stroke_width", 1) > 0:
            raise Unsupported("an operand has a stroke (draw strokes as their own layers)")


def pathfinder_outline(layer, state):
    """Closed contours of a pathfinder layer's result, in the layer's own pixels (0…width, 0…height)."""
    w, h = layer["width"], layer["height"]
    sx, sy = w / layer["content_width"], h / layer["content_height"]
    inputs = []
    for operand in layer["operands"]:
        check_operand(operand, state)
        # The renderer scales each operand to whole pixels, so the geometry does too.
        item = {**operand, "width": max(1, round(operand["width"] * sx)), "height": max(1, round(operand["height"] * sy))}
        local = pathfinder_outline(item, state) if item["type"] == "pathfinder" else shape_contours(item)
        inputs.append(placed(local, item, round(operand["x"] * sx), round(operand["y"] * sy)))
    return combine_outlines(inputs, MODES[layer["mode"]])


def outline_commands(contours):
    """Path commands (as ``geometry.parse_path`` returns them) for closed contours of segments."""
    commands = []
    for contour in contours:
        commands.append(("M", [*contour[0][0]]))
        for i, seg in enumerate(contour):
            if len(seg) == 2:
                if i < len(contour) - 1:  # a closing line back to the start is what Z draws
                    commands.append(("L", [*seg[1]]))
            else:
                commands.append(("C", [v for p in seg[1:] for v in p]))
        commands.append(("Z", []))
    return commands


def pathfinder_commands(layer, state):
    """A pathfinder layer's result as path commands (``M L C Z``) in layer pixels, or ``Unsupported``."""
    return outline_commands(pathfinder_outline(layer, state))


def path_data(commands):
    """SVG path data for path commands."""
    from .geometry import compact_number

    parts = []
    for command, values in commands:
        parts.append(command + " ".join(compact_number(v, 3) for v in values) if values else command)
    return " ".join(parts)
