"""Editable Bézier nodes, path construction operations and non-destructive vector warps."""

from copy import deepcopy
import math

from .errors import require

TYPES = (
    "shape-to-path",
    "path-edit",
    "path-simplify",
    "path-smooth",
    "offset-path",
    "outline-stroke",
    "round-corners",
    "distort",
)
WARPS = (
    "arc",
    "arch",
    "bulge",
    "flag",
    "wave",
    "fisheye",
    "inflate",
    "squeeze",
    "twist",
    "corner-pin",
    "free-distort",
    "pucker",
    "bloat",
    "zig-zag",
)


def schemas(add):
    emit = add
    summaries = {
        "shape-to-path": "Convert a parametric or organic shape to editable Bézier nodes, preserving its layer identity and appearance.",
        "path-edit": "Edit one indexed Bézier node, handle or segment, or open, close and reverse a contour.",
        "path-simplify": "Reduce path nodes within a pixel tolerance, preserving separate contours and holes.",
        "path-smooth": "Replace path tangents with editable smooth Bézier handles.",
        "offset-path": "Grow or inset a closed vector outline by a pixel distance, with miter, round or bevel joins.",
        "outline-stroke": "Convert visible strokes into filled, editable vector outlines; preserve separate stroke paints.",
        "round-corners": "Round every corner of a closed path, or the interior corners of an open path.",
        "distort": "Keep a shape or vector group editable while applying an envelope, corner-pin or procedural vector distortion.",
    }
    descriptions = {
        "action": "Node edit action; index addresses the node starting a segment for insertion.",
        "index": "Zero-based node index from document inspection; default 0.",
        "contour": "Zero-based contour index from document inspection; default 0.",
        "point": "Absolute local [x,y] coordinates, or a delta when relative is true.",
        "relative": "Apply point coordinates as offsets; default false.",
        "handle": "Incoming or outgoing handle for move-handle; default out.",
        "fraction": "Fraction along the Bézier segment, between 0 and 1; default 0.5.",
        "symmetric": "Mirror handle length and direction around the node; default true when smoothing.",
        "radius": "Corner cut distance in local pixels, clamped to half each adjacent edge.",
        "tolerance": "Maximum simplification deviation in local pixels; default 1.",
        "amount": "Smoothing strength (0–1) or signed warp strength; default 0.5 or 0.25 respectively.",
        "iterations": "Number of smoothing passes; default 1.",
        "distance": "Positive grows the outline; negative creates an inset, in local pixels.",
        "join": "Offset corner join; default miter.",
        "miter_limit": "Maximum miter length relative to offset distance; default 4.",
        "kind": "Editable vector warp kind. Roughening uses irregular instead.",
        "angle": "Maximum twist angle in degrees; strength falls toward the boundary.",
        "phase": "Wave phase in turns; animatable as distort:phase.",
        "frequency": "Wave cycles across the envelope; default 1.",
        "size": "Zig-zag displacement in local pixels.",
        "ridges": "Zig-zag ridges or pucker/bloat lobes; default 8 or 4.",
        "smooth": "Use sinusoidal rather than cornered zig-zag peaks.",
        "corners": "Top-left, top-right, bottom-right and bottom-left target points in local pixels.",
        "remove": "Remove the non-destructive distortion and restore the original geometry.",
    }

    def add(kind, properties=None, required=(), **extra):
        properties = {
            key: {**value, "description": descriptions[key]} for key, value in (properties or {}).items()
        }
        emit(kind, properties, required, description=summaries[kind], **extra)

    from .schema import N, B, enum

    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    add("shape-to-path", {}, ["target"])
    add(
        "path-edit",
        {
            "action": enum(
                "move",
                "move-handle",
                "insert",
                "delete",
                "corner",
                "smooth",
                "round",
                "open",
                "close",
                "reverse",
            ),
            "index": {"type": "integer", "minimum": 0},
            "contour": {"type": "integer", "minimum": 0},
            "point": point,
            "relative": B,
            "handle": enum("in", "out"),
            "fraction": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
            "symmetric": B,
            "radius": {"type": "number", "minimum": 0},
        },
        ["target", "action"],
    )
    add(
        "path-simplify", {"tolerance": {"type": "number", "exclusiveMinimum": 0, "maximum": 1024}}, ["target"]
    )
    add(
        "path-smooth",
        {
            "amount": {"type": "number", "minimum": 0, "maximum": 1},
            "iterations": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        ["target"],
    )
    add(
        "offset-path",
        {
            "distance": {"type": "number", "minimum": -4096, "maximum": 4096},
            "join": enum("miter", "round", "bevel"),
            "miter_limit": {"type": "number", "minimum": 1, "maximum": 1000},
        },
        ["target", "distance"],
    )
    add("outline-stroke", {}, ["target"])
    add("round-corners", {"radius": {"type": "number", "minimum": 0, "maximum": 4096}}, ["target", "radius"])
    add(
        "distort",
        {
            "kind": enum(*WARPS),
            "amount": {"type": "number", "minimum": -10, "maximum": 10},
            "angle": N,
            "phase": N,
            "frequency": {"type": "number", "exclusiveMinimum": 0, "maximum": 128},
            "size": {"type": "number", "minimum": 0, "maximum": 4096},
            "ridges": {"type": "integer", "minimum": 1, "maximum": 128},
            "smooth": B,
            "corners": {"type": "array", "items": point, "minItems": 4, "maxItems": 4},
            "remove": B,
        },
        ["target"],
    )


def path_nodes(path):
    """Return exact cubic nodes for every contour; quadratics are degree-elevated."""
    from .geometry import parse_path

    result = []
    nodes = []
    closed = False

    def finish():
        if nodes:
            if len(nodes) > 1 and nodes[-1]["point"] == nodes[0]["point"]:
                if "in" in nodes[-1]:
                    nodes[0]["in"] = nodes[-1]["in"]
                nodes.pop()
            for node in nodes:
                for handle in ("in", "out"):
                    if node.get(handle) == node["point"]:
                        node.pop(handle, None)
            result.append({"nodes": deepcopy(nodes), "closed": closed})

    for command, values in parse_path(path):
        pts = [list(p) for p in zip(values[::2], values[1::2])]
        if command == "M":
            finish()
            nodes = [{"point": pts[0]}]
            closed = False
        elif command == "L":
            nodes.append({"point": pts[0]})
        elif command == "C":
            nodes[-1]["out"] = pts[0]
            nodes.append({"point": pts[-1], "in": pts[-2]})
        elif command == "Q":
            current = nodes[-1]["point"]
            for i, ctrl in enumerate(pts[:-1]):
                end = [(ctrl[j] + pts[i + 1][j]) / 2 for j in (0, 1)] if i + 2 < len(pts) else pts[-1]
                nodes[-1]["out"] = [current[j] + 2 / 3 * (ctrl[j] - current[j]) for j in (0, 1)]
                nodes.append({"point": end, "in": [end[j] + 2 / 3 * (ctrl[j] - end[j]) for j in (0, 1)]})
                current = end
        elif command == "Z":
            closed = True
    finish()
    return result


def nodes_path(contours):
    from .creative import pen_path

    return " ".join(pen_path(c) for c in contours if len(c["nodes"]) >= 2) or "M0 0 L0 0"


def reverse_path(path):
    contours = path_nodes(path)
    for contour in contours:
        contour["nodes"] = [
            {
                "point": node["point"],
                **({"in": node["out"]} if "out" in node else {}),
                **({"out": node["in"]} if "in" in node else {}),
            }
            for node in reversed(contour["nodes"])
        ]
    return nodes_path(contours)


def inspect_nodes(layer):
    return [
        {"contour": i, "closed": c["closed"], "nodes": [{"index": j, **n} for j, n in enumerate(c["nodes"])]}
        for i, c in enumerate(path_nodes(pixel_path({**layer, "distort": None})))
    ]


def pixel_path(layer, distort=True):
    from .geometry import shape_path, parse_path
    from .pathfinder_geometry import path_data
    from .shape_catalog import path as catalog_path

    shape = layer["shape"]
    if shape in ("rectangle", "rounded-rectangle", "capsule", "ellipse", "line"):
        path = catalog_path(layer)
    else:
        path, view = shape_path({k: v for k, v in layer.items() if k != "distort"})
        sx, sy = layer["width"] / view[0], layer["height"] / view[1]
        path = path_data(
            [
                (cmd, [v * (sx if i % 2 == 0 else sy) for i, v in enumerate(values)])
                for cmd, values in parse_path(path)
            ]
        )
    if distort and layer.get("distort"):
        path = warp_path(path, layer["width"], layer["height"], layer["distort"])
    return path


def warp_point(x, y, w, h, settings):
    u, v = x / w, y / h
    a = settings.get("amount", 0.25)
    kind = settings.get("kind", "arc")
    phase = settings.get("phase", 0)
    frequency = settings.get("frequency", 1)
    q, r = 2 * u - 1, 2 * v - 1
    if kind in ("corner-pin", "free-distort"):
        corners = settings.get("corners", [[0, 0], [w, 0], [w, h], [0, h]])
        # Bilinear envelope: each corner remains independently addressable.
        weights = [(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v]
        return tuple(sum(c[j] * weight for c, weight in zip(corners, weights)) for j in (0, 1))
    if kind in ("arc", "arch"):
        if kind == "arch":
            return x, y - a * h * (1 - q * q)
        theta = q * a * math.pi / 2
        if abs(a) < 1e-9:
            return x, y
        radius = w / (a * math.pi)
        return w / 2 + (radius + y - h / 2) * math.sin(theta), h / 2 + (radius + y - h / 2) * math.cos(
            theta
        ) - radius
    if kind in ("wave", "flag"):
        return x, y + a * h * math.sin(math.tau * (u * frequency + phase)) * (1 if kind == "wave" else u)
    if kind == "bulge":
        return w / 2 + (x - w / 2) * (1 + a * (1 - r * r)), h / 2 + (y - h / 2) * (1 + a * (1 - q * q))
    if kind in ("inflate", "fisheye", "squeeze"):
        radius = min(1, math.hypot(q, r))
        scale = 1 + a * (1 - radius * radius) * (-1 if kind == "squeeze" else 1)
        return w / 2 + (x - w / 2) * scale, h / 2 + (y - h / 2) * scale
    if kind == "twist":
        angle = math.radians(settings.get("angle", a * 180)) * (1 - min(1, math.hypot(q, r)))
        return w / 2 + (x - w / 2) * math.cos(angle) - (y - h / 2) * math.sin(angle), h / 2 + (
            x - w / 2
        ) * math.sin(angle) + (y - h / 2) * math.cos(angle)
    if kind in ("pucker", "bloat"):
        theta = math.atan2(r, q)
        n = settings.get("ridges", 4)
        scale = 1 + a * math.cos(theta * n) * (1 if kind == "bloat" else -1)
        return w / 2 + (x - w / 2) * scale, h / 2 + (y - h / 2) * scale
    return x, y


def warp_path(path, w, h, settings):
    from .shape_catalog import poly
    from .geometry import path_polygons

    result = []
    for contour in path_polygons(path):
        closed = contour[0] == contour[-1]
        # Subdivide lines as well as curves: an envelope bends rectangle edges too.
        points = []
        for a, b in zip(contour, contour[1:]):
            count = max(1, min(256, math.ceil(math.dist(a, b) / max(min(w, h) / 64, 1))))
            points.extend(
                (a[0] + (b[0] - a[0]) * j / count, a[1] + (b[1] - a[1]) * j / count) for j in range(count)
            )
        points.append(contour[-1])
        if settings.get("kind") == "zig-zag":
            from .vector_strokes import unit

            size = settings.get("size", min(w, h) * 0.05)
            ridges = settings.get("ridges", 8)
            distances = [0]
            for a, b in zip(points, points[1:]):
                distances.append(distances[-1] + math.dist(a, b))
            warped = []
            for i, p in enumerate(points):
                tangent = unit(points[max(0, i - 1)], points[min(len(points) - 1, i + 1)])
                q = distances[i] / max(distances[-1], 1e-9) * ridges
                d = size * (
                    math.sin(q * math.tau) if settings.get("smooth", False) else 4 * abs(q % 1 - 0.5) - 1
                )
                warped.append((p[0] - tangent[1] * d, p[1] + tangent[0] * d))
        else:
            warped = [warp_point(*p, w, h, settings) for p in points]
        result.append(poly(warped, closed))
    return " ".join(result)


def _store(layer, contours=None, path=None):
    layer.update(
        shape="path",
        path=path if path is not None else nodes_path(contours),
        path_view=[layer["width"], layer["height"]],
        vector_geometry=True,
    )
    layer.pop("organic", None)
    layer.pop("pen_origin", None)


def _round_nodes(contour, index, radius):
    nodes = contour["nodes"]
    n = len(nodes)
    require(contour["closed"] or 0 < index < n - 1, "Cannot round an endpoint of an open path")
    a, p, b = nodes[(index - 1) % n]["point"], nodes[index]["point"], nodes[(index + 1) % n]["point"]
    da, db = math.dist(a, p), math.dist(p, b)
    r = min(radius, da / 2, db / 2)
    left = [p[j] + (a[j] - p[j]) * r / max(da, 1e-9) for j in (0, 1)]
    right = [p[j] + (b[j] - p[j]) * r / max(db, 1e-9) for j in (0, 1)]
    nodes[index : index + 1] = [
        {"point": left, "out": [left[j] + 2 / 3 * (p[j] - left[j]) for j in (0, 1)]},
        {"point": right, "in": [right[j] + 2 / 3 * (p[j] - right[j]) for j in (0, 1)]},
    ]


def execute(project, op):
    from .geometry import path_polygons

    layer = project.layer(op.get("target"))
    kind = op["type"]
    if kind == "distort":
        require(layer["type"] in ("shape", "group"), "Distort requires a shape, pen path or group")
        if op.get("remove"):
            layer.pop("distort", None)
        else:
            settings = deepcopy(layer.get("distort", {}))
            settings.update({k: v for k, v in op.items() if k not in ("type", "target", "remove")})
            require(
                settings.get("kind") in WARPS,
                "Choose a distort kind; roughen uses the existing irregular operation",
            )
            if settings["kind"] in ("corner-pin", "free-distort"):
                require("corners" in settings, "Corner pin requires four corners")
            if layer["type"] == "group":
                from .design import descendants

                require(
                    all(
                        item["type"] in ("shape", "group")
                        for item in project.state["layers"]
                        if item["id"] in descendants(project, layer["id"])
                    ),
                    "Vector group distortion requires shape/path children",
                )
            layer["distort"] = settings
        return
    require(layer["type"] == "shape", "Path operations require a shape or pen path")
    path = pixel_path(layer, False)
    if kind == "shape-to-path":
        _store(layer, path=path)
        return
    if kind == "outline-stroke":
        from .vector_strokes import expanded
        from .model import new_layer
        from .operations import append_layer

        outlines = [(d, c) for d, c in expanded(layer, path) if d and c != "transparent"]
        require(outlines, "Target has no visible stroke")
        _store(layer, path=outlines[0][0])
        layer["fill"] = outlines[0][1]
        layer["stroke"] = "transparent"
        layer["stroke_width"] = 0
        layer.pop("strokes", None)
        for i, (d, paint) in enumerate(outlines[1:]):
            child = new_layer(
                f"{layer['name']}-stroke-{i + 2}",
                "shape",
                layer["width"],
                layer["height"],
                shape="path",
                path=d,
                path_view=[layer["width"], layer["height"]],
                fill=paint,
                stroke="transparent",
                x=layer["x"],
                y=layer["y"],
                parent=layer.get("parent"),
                rotation=layer.get("rotation", 0),
            )
            for key in (
                "flip_x",
                "flip_y",
                "pivot",
                "skew_x",
                "skew_y",
                "affine",
                "opacity",
                "blend",
                "constraints",
                "effects",
                "styles",
                "mask",
                "clip",
                "distort",
            ):
                if key in layer:
                    child[key] = deepcopy(layer[key])
            child["vector_geometry"] = True
            append_layer(project, child)
        return
    if kind == "offset-path":
        from .vector_boolean import offset

        _store(layer, path=offset(path, op["distance"], op.get("join", "miter"), op.get("miter_limit", 4)))
        return
    contours = path_nodes(path)
    if kind == "path-simplify":
        from .trace import simplify
        import numpy as np

        tolerance = op.get("tolerance", 1)
        simplified = []
        for pts in path_polygons(path):
            closed = pts[0] == pts[-1]
            points = simplify(np.asarray(pts[:-1] if closed else pts), tolerance, closed)
            require(len(points) >= (3 if closed else 2), "Tolerance collapses a contour")
            simplified.append({"nodes": [{"point": list(p)} for p in points], "closed": closed})
        _store(layer, simplified)
        return
    if kind == "path-smooth":
        from .creative import pen_path

        for _ in range(op.get("iterations", 1)):
            paths = []
            for c in contours:
                points = [n["point"] for n in c["nodes"]]
                amount = op.get("amount", 0.5)
                smoothed = []
                for index, point in enumerate(points):
                    if not c["closed"] and index in (0, len(points) - 1):
                        smoothed.append(point)
                    else:
                        before, after = points[index - 1], points[(index + 1) % len(points)]
                        smoothed.append(
                            [
                                point[j] * (1 - amount * 0.25) + (before[j] + after[j]) * amount * 0.125
                                for j in (0, 1)
                            ]
                        )
                paths.append(
                    pen_path({"points": smoothed, "closed": c["closed"], "smooth": True, "tension": amount})
                )
            contours = path_nodes(" ".join(paths))
        _store(layer, contours)
        return
    if kind == "round-corners":
        for c in contours:
            for index in reversed(range(len(c["nodes"]))):
                if c["closed"] or 0 < index < len(c["nodes"]) - 1:
                    _round_nodes(c, index, op["radius"])
        _store(layer, contours)
        return
    ci = op.get("contour", 0)
    require(ci < len(contours), "Contour index out of range")
    c = contours[ci]
    nodes = c["nodes"]
    action = op["action"]
    index = op.get("index", 0)
    require(index < len(nodes), "Node index out of range")
    node = nodes[index]
    if action in ("open", "close"):
        c["closed"] = action == "close"
    elif action == "reverse":
        c["nodes"] = path_nodes(reverse_path(nodes_path([c])))[0]["nodes"]
    elif action == "delete":
        require(len(nodes) > (3 if c["closed"] else 2), "Deleting this node would collapse the path")
        nodes.pop(index)
    elif action in ("move", "move-handle"):
        require("point" in op, "A point [x,y] is required")
        field = "point" if action == "move" else op.get("handle", "out")
        old = node.get(field, node["point"])
        value = op["point"]
        dest = [old[j] + value[j] for j in (0, 1)] if op.get("relative") else value
        if field == "point":
            delta = [dest[j] - old[j] for j in (0, 1)]
            for handle in ("in", "out"):
                if handle in node:
                    node[handle] = [node[handle][j] + delta[j] for j in (0, 1)]
        elif op.get("symmetric"):
            node["in" if field == "out" else "out"] = [2 * node["point"][j] - dest[j] for j in (0, 1)]
        node[field] = list(dest)
    elif action == "insert":
        require(c["closed"] or index + 1 < len(nodes), "An open path endpoint has no following segment")
        nxt = nodes[(index + 1) % len(nodes)]
        t = op.get("fraction", 0.5)
        controls = [node["point"], node.get("out", node["point"]), nxt.get("in", nxt["point"]), nxt["point"]]
        if "out" not in node and "in" not in nxt:
            nodes.insert(
                index + 1, {"point": [controls[0][j] * (1 - t) + controls[3][j] * t for j in (0, 1)]}
            )
        else:

            def lerp(a, b):
                return [a[j] * (1 - t) + b[j] * t for j in (0, 1)]

            a, b, d = [lerp(a, b) for a, b in zip(controls, controls[1:])]
            e, f = lerp(a, b), lerp(b, d)
            g = lerp(e, f)
            node["out"] = a
            nxt["in"] = d
            nodes.insert(index + 1, {"point": g, "in": e, "out": f})
    elif action == "corner":
        node.pop("in", None)
        node.pop("out", None)
    elif action == "smooth":
        prev = nodes[index - 1]["point"] if index or c["closed"] else node["point"]
        nxt = (
            nodes[(index + 1) % len(nodes)]["point"]
            if index + 1 < len(nodes) or c["closed"]
            else node["point"]
        )
        tangent = [(nxt[j] - prev[j]) / 6 for j in (0, 1)]
        norm = max(math.hypot(*tangent), 1e-12)
        for handle, sign in (("in", -1), ("out", 1)):
            scale = (
                1
                if op.get("symmetric", True)
                else math.dist(node["point"], node.get(handle, prev if sign < 0 else nxt)) / norm / 3
            )
            node[handle] = [node["point"][j] + sign * tangent[j] * scale for j in (0, 1)]
    elif action == "round":
        _round_nodes(c, index, op.get("radius", 5))
    require(
        sum(len(c["nodes"]) for c in contours) <= 8192, "Path supports at most 8192 nodes", "resource_limit"
    )
    _store(layer, contours)


def pathfinder_parts(project, op, children, bounds):
    """Divide into independently editable faces; trim/merge retain foreground paints."""
    from .pathfinder_geometry import (
        shape_contours,
        pathfinder_outline,
        placed,
        path_data,
        outline_commands,
        check_operand,
    )
    from .booleans import combine_outlines
    from .operations import append_layer
    from .design import union_bounds
    from .model import new_layer
    from .render import stored_origin

    x, y, w, h = union_bounds([bounds[item["id"]] for item in children])
    inputs = []
    for item in children:
        check_operand(item, project.state)
        local = (
            pathfinder_outline(item, project.state) if item["type"] == "pathfinder" else shape_contours(item)
        )
        b = bounds[item["id"]]
        inputs.append(placed(local, item, b[0] - x, b[1] - y))
    mode = op["mode"]
    pieces = []
    if mode == "divide":
        for i, outline in enumerate(inputs):
            remaining = outline
            updated = []
            for previous, owner in pieces:
                overlap = combine_outlines([previous, outline], lambda a, b: a and b)
                outside = combine_outlines([previous, outline], lambda a, b: a and not b)
                if overlap:
                    updated.append((overlap, i))
                if outside:
                    updated.append((outside, owner))
                remaining = combine_outlines([remaining, previous], lambda a, b: a and not b)
            if remaining:
                updated.append((remaining, i))
            pieces = updated
            require(len(pieces) <= 256, "Divide exceeds 256 pieces", "resource_limit")
    else:
        for i, outline in enumerate(inputs):
            visible = combine_outlines(
                [outline, *inputs[i + 1 :]], lambda first, *later: first and not any(later)
            )
            if visible:
                pieces.append((visible, i))
        if mode == "merge":
            paints = {}
            for outline, owner in pieces:
                paints.setdefault(children[owner].get("fill", "white"), []).append((outline, owner))
            pieces = [
                (combine_outlines([c for c, _ in group], lambda *inside: any(inside)), group[-1][1])
                for group in paints.values()
            ]
    require(pieces, "Pathfinder result is empty")
    group = new_layer(
        op["name"],
        "group",
        w,
        h,
        x=x,
        y=y,
        parent=children[0].get("parent"),
        content_width=w,
        content_height=h,
    )
    append_layer(project, group)
    for i, (outline, owner) in enumerate(pieces):
        child = new_layer(
            f"{op['name']}-{i + 1}",
            "shape",
            w,
            h,
            shape="path",
            path=path_data(outline_commands(outline)),
            path_view=[w, h],
            fill=children[owner].get("fill", "white"),
            stroke="transparent",
            parent=group["id"],
        )
        child["x"], child["y"] = stored_origin(child, (0, 0))
        append_layer(project, child)
    for item in children:
        item["visible"] = False
    project.state["active_layer"] = group["id"]


def attach_ancestors(layers):
    index = {item["id"]: item for item in layers}
    for layer in layers:
        if layer["type"] != "shape":
            continue
        ancestors = []
        parent = index.get(layer.get("parent"))
        while parent:
            if parent.get("distort"):
                ancestors.append(
                    {
                        key: deepcopy(parent[key])
                        for key in ("id", "distort", "content_width", "content_height", "width", "height")
                    }
                )
            parent = index.get(parent.get("parent"))
        if ancestors:
            layer["_distort_groups"] = ancestors


def group_warp(path, layer, project):
    """Warp in each ancestor's content coordinate system and map back to leaf space."""
    import numpy as np
    from .affine import layer_matrix, matrix
    from .render import resolve_layout, resolved_layers
    from .geometry import path_polygons
    from .shape_catalog import poly

    layers = resolved_layers(project)
    index = {item["id"]: item for item in layers}
    bounds = resolve_layout(project, layers=layers)
    transform = layer_matrix(layer, bounds[layer["id"]])
    parent = index.get(layer.get("parent"))
    while parent:
        if parent.get("distort"):
            inverse = np.linalg.inv(transform)
            parts = []
            for contour in path_polygons(path):
                closed = contour[0] == contour[-1]
                moved = []
                # Straight edges need samples before a nonlinear mapping.
                points = []
                for a, b in zip(contour, contour[1:]):
                    n = max(1, min(128, math.ceil(math.dist(a, b) / 4)))
                    points.extend(
                        (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)
                    )
                points.append(contour[-1])
                local = [(transform @ [*p, 1])[:2] for p in points]
                warped = warp_path(
                    poly(local, closed), parent["content_width"], parent["content_height"], parent["distort"]
                )
                for warped_contour in path_polygons(warped):
                    moved = [tuple((inverse @ [*p, 1])[:2]) for p in warped_contour]
                    parts.append(poly(moved, closed))
            path = " ".join(parts)
        transform = (
            layer_matrix(parent, bounds[parent["id"]])
            @ matrix(
                parent["width"] / parent["content_width"], 0, 0, parent["height"] / parent["content_height"]
            )
            @ transform
        )
        parent = index.get(parent.get("parent"))
    return path


def validate_distort(layer):
    settings = layer.get("distort")
    if settings is None:
        return
    from .model import finite

    require(
        layer.get("type") in ("shape", "group") and isinstance(settings, dict), "Invalid vector distortion"
    )
    require(settings.get("kind") in WARPS, "Invalid vector distortion kind")
    for key in ("amount", "angle", "phase", "frequency", "size", "ridges"):
        if key in settings:
            finite(settings[key], "distort " + key, -1e6, 1e6)
    require(-10 <= settings.get("amount", 0.25) <= 10, "Warp amount must be -10 to 10")
    require(0 < settings.get("frequency", 1) <= 128, "Warp frequency must be positive and at most 128")
    require(0 <= settings.get("size", 0) <= 4096, "Zig-zag size must be 0–4096 pixels")
    require(1 <= settings.get("ridges", 4) <= 128, "Warp ridges must be 1–128")
    if settings["kind"] in ("corner-pin", "free-distort"):
        corners = settings.get("corners")
        require(isinstance(corners, list) and len(corners) == 4, "Corner pin requires four corners")
        for point in corners:
            require(isinstance(point, (list, tuple)) and len(point) == 2, "Corners must be [x,y] points")
            for value in point:
                finite(value, "corner coordinate", -1e6, 1e6)
