"""Read-only spatial reasoning with exact canvas-space geometry and applicable snap edits."""

import fnmatch
import math
from .errors import require
from .model import finite
from .affine import corners, envelope, layer_matrix

MODES = ("relations", "canvas", "matrix", "grid", "guides", "composition", "hit", "free", "snap", "all")


def canvas_boxes(project, bounds="box"):
    from .render import resolved_layers, resolve_layout, rest_size, extent, child_index
    from .checks import group_matrix

    layers = resolved_layers(project)
    index = {v["id"]: v for v in layers}
    local = resolve_layout(project, layers=layers)
    result = {}
    children = child_index(layers)
    memo = {}
    for layer in layers:
        parent = group_matrix(layer, index, local)
        if bounds == "ink":
            x, y, r, b = extent(layer, local, children, memo)
            if layer["type"] == "text" and not layer.get("repeat"):
                from .text_metrics import inspect_text

                box = local[layer["id"]]
                ink = inspect_text(project, layer, box).get("ink_bounds")
                if ink is not None:
                    # Text metrics are unrotated parent coordinates. Keep the glyph
                    # outline box distinct from a constrained/wrapped layout box,
                    # and carry it through the complete ancestor transform.
                    stroke = layer.get("stroke_width", 0)
                    glyph = (
                        ink[0] - box[0] - stroke,
                        ink[1] - box[1] - stroke,
                        ink[2] + 2 * stroke,
                        ink[3] + 2 * stroke,
                    )
                    transform = parent @ layer_matrix(layer, box)
                    ix, iy, iw, ih = envelope(corners(glyph, transform))
                    # Spreading styles/effects are measured in parent coordinates.
                    # Transform their conservative envelope separately from glyphs.
                    mx = max(box[0] - x, r - box[0] - box[2], 0)
                    my = max(box[1] - y, b - box[1] - box[3], 0)
                    ex = abs(parent[0, 0]) * mx + abs(parent[0, 1]) * my
                    ey = abs(parent[1, 0]) * mx + abs(parent[1, 1]) * my
                    result[layer["id"]] = (ix - ex, iy - ey, iw + 2 * ex, ih + 2 * ey)
                    continue
            result[layer["id"]] = envelope(corners((x, y, r - x, b - y), parent))
        else:
            w, h = rest_size(layer)
            result[layer["id"]] = envelope(
                corners((0, 0, w, h), parent @ layer_matrix(layer, local[layer["id"]]))
            )
    return result


def _select(project, target=None, targets=None):
    refs = targets or ([target] if target else ["*"])
    if isinstance(refs, str):
        refs = [refs]
    result = []
    for ref in refs:
        if isinstance(ref, dict):
            from .selectors import parse_where, matcher

            where = parse_where(ref)
            chosen = [v for v in project.state["layers"] if matcher(project, where)(v)]
        else:
            chosen = [
                v for v in project.state["layers"] if v["id"] == ref or fnmatch.fnmatchcase(v["name"], ref)
            ]
            if ref.startswith("group:"):
                from .design import descendants

                ids = descendants(project, project.layer(ref[6:])["id"])
                chosen = [v for v in project.state["layers"] if v["id"] in ids]
        require(chosen, f"No layers match {ref!r}", field="target")
        for layer in chosen:
            if layer not in result:
                result.append(layer)
    return result


def relation(a, b, tolerance=1):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    gx = max(bx - ax - aw, ax - bx - bw)
    gy = max(by - ay - ah, ay - by - bh)
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    area = iw * ih
    dx = bx + bw / 2 - ax - aw / 2
    dy = by + bh / 2 - ay - ah / 2
    positions = []
    if ax + aw <= bx + tolerance:
        positions.append("left-of")
    if bx + bw <= ax + tolerance:
        positions.append("right-of")
    if ay + ah <= by + tolerance:
        positions.append("above")
    if by + bh <= ay + tolerance:
        positions.append("below")
    if area > 0:
        positions.append("overlapping")

    def contains(x, y):
        return (
            x[0] <= y[0] + tolerance
            and x[1] <= y[1] + tolerance
            and x[0] + x[2] >= y[0] + y[2] - tolerance
            and x[1] + x[3] >= y[1] + y[3] - tolerance
        )

    if contains(a, b):
        positions.append("contains")
    if contains(b, a):
        positions.append("inside")

    def edges(q):
        return {
            "left": q[0],
            "center-x": q[0] + q[2] / 2,
            "right": q[0] + q[2],
            "top": q[1],
            "center-y": q[1] + q[3] / 2,
            "bottom": q[1] + q[3],
        }

    ea, eb = edges(a), edges(b)
    align = [key for key in ea if abs(ea[key] - eb[key]) <= tolerance]
    nearest = math.hypot(max(gx, 0), max(gy, 0)) if gx > 0 or gy > 0 else -min(iw, ih)
    return {
        "positions": positions,
        "horizontal_gap": gx,
        "vertical_gap": gy,
        "nearest_edge_distance": nearest,
        "overlap_area": area,
        "overlap_percent": {
            "a": 100 * area / (aw * ah) if aw * ah else 0,
            "b": 100 * area / (bw * bh) if bw * bh else 0,
        },
        "center_offset": [dx, dy],
        "center_distance": math.hypot(dx, dy),
        "angle": math.degrees(math.atan2(dy, dx)),
        "alignments": align,
    }


def _distances(box, region):
    x, y, w, h = box
    rx, ry, rw, rh = region
    return {"left": x - rx, "top": y - ry, "right": rx + rw - x - w, "bottom": ry + rh - y - h}


def _canvas(project, layer, box, boxes, safe_area=None):
    c = project.state["canvas"]
    w, h = c["width"], c["height"]
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    bleed = c.get("bleed", 0)
    margin = c.get("safe", 0) if safe_area is None else safe_area
    if isinstance(margin, (int, float)):
        margin = [margin] * 4
    if isinstance(margin, dict):
        require(
            not set(margin) - {"left", "top", "right", "bottom"},
            "safe_area accepts left, top, right, bottom insets",
        )
        margin = [margin.get(key, 0) for key in ("left", "top", "right", "bottom")]
    require(len(margin) == 4, "safe_area must be an inset or [left, top, right, bottom]")
    left, top, right, bottom = [finite(value, "safe_area", 0) for value in margin]
    distances = _distances(box, (0, 0, w, h))
    parent = project.layer(layer["parent"]) if layer.get("parent") else None
    parent_distances = _distances(box, boxes[parent["id"]]) if parent else None
    return {
        "edges": distances,
        "safe_area": _distances(
            box, (bleed + left, bleed + top, w - 2 * bleed - left - right, h - 2 * bleed - top - bottom)
        ),
        "trim": _distances(box, (bleed, bleed, w - 2 * bleed, h - 2 * bleed)),
        "bleed": distances,
        "center_fraction": [cx / w, cy / h],
        "quadrant": ("top" if cy < h / 2 else "bottom") + "-" + ("left" if cx < w / 2 else "right"),
        "thirds": [min(3, max(1, math.floor(cx / w * 3) + 1)), min(3, max(1, math.floor(cy / h * 3) + 1))],
        "cropped": {
            "canvas": any(v < -1e-8 for v in distances.values()),
            "parent": bool(parent_distances and any(v < -1e-8 for v in parent_distances.values())),
        },
        "parent_edges": parent_distances,
    }


def _guides(project, box, tolerance):
    from .guides import nearest

    x, y, w, h = box
    points = {
        "top-left": (x, y),
        "top": (x + w / 2, y),
        "top-right": (x + w, y),
        "left": (x, y + h / 2),
        "center": (x + w / 2, y + h / 2),
        "right": (x + w, y + h / 2),
        "bottom-left": (x, y + h),
        "bottom": (x + w / 2, y + h),
        "bottom-right": (x + w, y + h),
    }
    result = []
    for name, g in project.state.get("guides", {}).items():
        candidates = []
        for anchor, q in points.items():
            p, d, _ = nearest(g, project.state["canvas"], q)
            candidates.append(
                {"anchor": anchor, "distance": d, "move": [float(p[0] - q[0]), float(p[1] - q[1])]}
            )
        best = min(candidates, key=lambda v: v["distance"])
        result.append(
            {
                "guide": name,
                "axis": g.get("axis"),
                "grid": g.get("grid"),
                **best,
                "on": [v["anchor"] for v in candidates if v["distance"] <= tolerance],
            }
        )
    result.sort(key=lambda v: v["distance"])
    return {
        "nearest": {axis: next((v for v in result if v["axis"] == axis), None) for axis in ("x", "y")},
        "matches": [v for v in result if v["on"]],
        "guides": result,
    }


def _grid(project, box, name, tolerance):
    grids = project.state.get("grids", {})
    if name is None:
        name = project.state.get("active_grid") or (next(reversed(grids), None) if grids else None)
    require(name in grids, "No active grid; create a grid or pass its name", field="grid")
    lines = {
        axis: sorted(
            set(
                g["position"]
                for g in project.state.get("guides", {}).values()
                if g.get("grid") == name and g.get("axis") == axis
            )
        )
        for axis in ("x", "y")
    }
    answer = {"name": name, "kind": grids[name].get("kind", "columns")}
    for axis, start, size, label in (("x", box[0], box[2], "columns"), ("y", box[1], box[3], "rows")):
        cells = []
        guides = project.state.get("guides", {})
        for key, g in guides.items():
            if g.get("grid") == name and g.get("axis") == axis and key.endswith("-start"):
                end = guides.get(key[:-6] + "-end", {}).get("position")
                if end is not None:
                    cells.append((g["position"], end))
        if not cells:
            cells = list(zip(lines[axis], lines[axis][1:]))
        cells.sort()
        occupied = [i + 1 for i, (a, b) in enumerate(cells) if start < b - 1e-8 and start + size > a + 1e-8]
        offsets = {}
        for key, value in (("start", start), ("center", start + size / 2), ("end", start + size)):
            nearest = min(lines[axis], key=lambda n: abs(n - value)) if lines[axis] else None
            offsets[key] = {
                "line": nearest,
                "offset": value - nearest if nearest is not None else None,
                "snapped": nearest is not None and abs(value - nearest) <= tolerance,
            }
        answer[label] = {
            "occupied": occupied,
            "span": max(occupied) - min(occupied) + 1 if occupied else 0,
            "offsets": offsets,
            "cells": [list(c) for c in cells],
        }
    return answer


def _composition(project, box):
    c = project.state["canvas"]
    w, h = c["width"], c["height"]
    x, y = box[0] + box[2] / 2, box[1] + box[3] / 2
    phi = (math.sqrt(5) - 1) / 2
    result = {}
    for name, fractions in (("thirds", [1 / 3, 2 / 3]), ("golden", [1 - phi, phi]), ("center", [0.5])):
        result[name] = {
            "vertical_lines": [{"position": w * f, "distance": abs(x - w * f)} for f in fractions],
            "horizontal_lines": [{"position": h * f, "distance": abs(y - h * f)} for f in fractions],
            "points": [
                {"point": [w * a, h * b], "distance": math.hypot(x - w * a, y - h * b)}
                for a in fractions
                for b in fractions
            ],
        }
    return result


def _free(region, obstacles, limit):
    # Maximal empty rectangles: split every intersected candidate into all four residual strips,
    # then discard contained rectangles. Keeping overlapping candidates preserves large gaps.
    remaining = [tuple(region)]
    for obstacle in obstacles:
        ox, oy, ow, oh = obstacle
        pieces = []
        for rect in remaining:
            x, y, w, h = rect
            r, b = x + w, y + h
            if ox >= r or oy >= b or ox + ow <= x or oy + oh <= y:
                pieces.append(rect)
                continue
            if ox > x:
                pieces.append((x, y, ox - x, h))
            if ox + ow < r:
                pieces.append((ox + ow, y, r - ox - ow, h))
            if oy > y:
                pieces.append((x, y, w, oy - y))
            if oy + oh < b:
                pieces.append((x, oy + oh, w, b - oy - oh))
        unique = sorted(set(pieces), key=lambda r: r[2] * r[3], reverse=True)
        remaining = []
        for rect in unique:
            if not any(all(v >= -1e-8 for v in _distances(rect, other).values()) for other in remaining):
                remaining.append(rect)
        require(
            len(remaining) <= 10000,
            "Free-space query is too complex; restrict region or targets",
            "resource_limit",
        )
    return [
        {"bounds": list(r), "area": r[2] * r[3]}
        for r in sorted(remaining, key=lambda r: r[2] * r[3], reverse=True)[:limit]
    ]


def query(
    project,
    *,
    target=None,
    targets=None,
    to=None,
    mode="relations",
    bounds="box",
    tolerance=1,
    point=None,
    region=None,
    grid=None,
    describe=False,
    include_hidden=False,
    limit=20,
    artboard=None,
    page=None,
    safe_area=None,
):
    require(mode in MODES, f"Unknown spatial mode {mode!r}", field="mode", allowed=list(MODES))
    require(bounds in ("box", "ink"), "bounds must be box or ink", field="bounds")
    finite(tolerance, "tolerance", 0)
    require(isinstance(limit, int) and 1 <= limit <= 512, "limit must be 1–512")
    if page is not None:
        from .pages import page_project

        project = page_project(project, page)
    if artboard is not None:
        from .design_render import artboard_project

        project = artboard_project(project.clone(), artboard)
    selected = _select(project, target, targets) if project.state["layers"] else []
    boxes = canvas_boxes(project, bounds)
    index = {v["id"]: v for v in project.state["layers"]}

    def appearance(layer):
        opacity = 1.0
        visible = True
        item = layer
        while item:
            visible = visible and item["visible"]
            opacity *= item["opacity"]
            item = index.get(item.get("parent"))
        return visible, opacity

    def record(layer):
        visible, opacity = appearance(layer)
        return {
            "id": layer["id"],
            "name": layer["name"],
            "bounds": list(boxes[layer["id"]]),
            "visible": visible,
            "opacity": opacity,
        }

    if mode in ("hit", "free"):
        eligible = [v for v in selected if include_hidden or all((appearance(v)[0], appearance(v)[1] > 0))]
        if mode == "free":
            area = region or [0, 0, project.state["canvas"]["width"], project.state["canvas"]["height"]]
            require(
                len(area) == 4 and area[2] > 0 and area[3] > 0,
                "region must be [x,y,width,height] with positive size",
            )
            return {
                "mode": mode,
                "region": area,
                "rectangles": _free(area, [boxes[v["id"]] for v in eligible], limit),
            }
        require(point is not None or region is not None, "Hit test needs point or region")
        if point is not None:
            require(len(point) == 2, "point must be [x,y]")
        hits = []
        from .render import child_index

        children = child_index(project.state["layers"])
        ordered = []

        def visit(parent=None):
            for v in children.get(parent, []):
                ordered.append(v)
                if v["type"] == "group":
                    visit(v["id"])

        visit()
        ids = {v["id"] for v in eligible}
        for layer in reversed(ordered):
            if layer["id"] not in ids:
                continue
            x, y, w, h = boxes[layer["id"]]
            hit = (
                x <= point[0] <= x + w and y <= point[1] <= y + h
                if point is not None
                else relation(boxes[layer["id"]], region, 0)["overlap_area"] > 0
            )
            if hit and bounds == "ink":
                from .render import layer_canvas_surface

                surface = layer_canvas_surface(project, layer).getchannel("A")
                if point is not None:
                    px, py = map(math.floor, point)
                    hit = (
                        0 <= px < surface.width
                        and 0 <= py < surface.height
                        and surface.getpixel((px, py)) > 0
                    )
                else:
                    rx, ry, rw, rh = region
                    hit = (
                        surface.crop(
                            (math.floor(rx), math.floor(ry), math.ceil(rx + rw), math.ceil(ry + rh))
                        ).getbbox()
                        is not None
                    )
            if hit:
                hits.append(record(layer))
        return {"mode": mode, "hits": hits[:limit]}
    output = {"mode": mode, "space": "canvas", "bounds_kind": bounds, "layers": [record(v) for v in selected]}
    if mode in ("relations", "matrix", "all"):
        other = _select(project, to) if to else selected
        pairs = []
        for a in selected:
            for b in other:
                if a["id"] != b["id"]:
                    pairs.append(
                        {"a": a["id"], "b": b["id"], **relation(boxes[a["id"]], boxes[b["id"]], tolerance)}
                    )
        output["relations"] = pairs
        output["nearest_neighbours"] = {
            a["id"]: min(
                (p for p in pairs if p["a"] == a["id"]), key=lambda p: p["center_distance"], default=None
            )
            for a in selected
        }
    for entry, layer in zip(output["layers"], selected):
        box = boxes[layer["id"]]
        if mode in ("canvas", "all") or describe:
            entry["canvas"] = _canvas(project, layer, box, boxes, safe_area)
            entry["canvas"]["cropped"]["artboard"] = (
                entry["canvas"]["cropped"]["canvas"] if artboard is not None else False
            )
        if mode in ("guides", "snap", "all"):
            entry["guides"] = _guides(project, box, tolerance)
        if mode in ("grid", "all") or (mode == "snap" and grid):
            if mode == "grid" or grid or project.state.get("grids"):
                entry["grid"] = _grid(project, box, grid, tolerance)
        if mode in ("composition", "all"):
            entry["composition"] = _composition(project, box)
        if mode == "snap":
            suggestions = []
            for guide in entry["guides"]["guides"][:limit]:
                dx, dy = guide["move"]
                suggestions.append(
                    {
                        "to": guide["guide"],
                        "distance": guide["distance"],
                        "operation": {
                            "type": "move",
                            "target": layer["id"],
                            "relative": True,
                            "space": "canvas",
                            "x": dx,
                            "y": dy,
                        },
                    }
                )
            # Resizing an edge onto an axis guide keeps the opposite edge fixed. Validate the
            # suggested affine fit on a clone: some rotated aspect ratios cannot stretch into
            # an arbitrary axis-aligned box while retaining the rotation.
            from .transforms import execute as apply_transform
            from .errors import VixlError

            for axis, guide in entry["guides"]["nearest"].items():
                if guide is None:
                    continue
                position = project.state["guides"][guide["guide"]]["position"]
                coordinate, size_index = (0, 2) if axis == "x" else (1, 3)
                start, size = box[coordinate], box[size_index]
                end = start + size
                rect = list(box)
                if abs(position - start) < abs(position - end):
                    rect[coordinate], rect[size_index] = position, end - position
                else:
                    rect[size_index] = position - start
                if rect[size_index] <= 0:
                    continue
                operation = {"type": "fit", "target": layer["id"], "box": rect, "mode": "stretch"}
                try:
                    apply_transform(project.clone(), operation)
                except VixlError:
                    continue
                suggestions.append({"to": guide["guide"], "kind": "resize", "operation": operation})
            if entry.get("grid"):
                cells = entry["grid"]
                xs = cells["columns"]["cells"]
                ys = cells["rows"]["cells"]
                if xs and ys:
                    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
                    a, b = min(xs, key=lambda c: abs(sum(c) / 2 - cx))
                    d, e = min(ys, key=lambda c: abs(sum(c) / 2 - cy))
                    operation = {
                        "type": "fit",
                        "target": layer["id"],
                        "box": [a, d, b - a, e - d],
                        "mode": "stretch",
                    }
                    try:
                        apply_transform(project.clone(), operation)
                    except VixlError:
                        operation["mode"] = "contain"
                    suggestions.append({"to": cells["name"], "kind": "resize", "operation": operation})
            entry["suggestions"] = suggestions
        if describe:
            c = entry["canvas"]
            edges = c["edges"]
            text = f"{layer['name']}: {c['quadrant']}, {edges['top']:g} px from top, {edges['right']:g} px from right"
            nearest = output.get("nearest_neighbours", {}).get(layer["id"])
            if nearest:
                text += f", {'/'.join(nearest['positions'])} {index[nearest['b']]['name']} ({nearest['nearest_edge_distance']:g} px gap)"
                if nearest["alignments"]:
                    text += ", aligned " + ", ".join(nearest["alignments"])
            entry["description"] = text
    return output
