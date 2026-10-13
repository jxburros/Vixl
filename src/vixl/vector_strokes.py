"""Shared vector stroke expansion, including dashes, variable widths and alignment.

Stroke expansion yields filled SVG paths; raster/SVG/PDF consume the same geometry.
Widths and dash distances are measured in local pixels, independent of path viewBox.
"""

import math

from .errors import require
from .geometry import OPEN_SHAPES, PATH_SHAPES
from .geometry import default_fill, stroke_align

FIELDS = (
    "dash",
    "dash_offset",
    "line_cap",
    "line_join",
    "miter_limit",
    "stroke_align",
    "strokes",
    "width_profile",
    "taper_start",
    "taper_end",
    "marker_start",
    "marker_end",
    "marker_size",
    "marker_style",
)


def schema():
    from .schema import N, S, enum

    props = {
        "dash": {
            "anyOf": [
                enum("dashed", "dotted"),
                {
                    "type": "array",
                    "items": {"type": "number", "exclusiveMinimum": 0},
                    "minItems": 1,
                    "maxItems": 32,
                },
            ]
        },
        "dash_offset": N,
        "line_cap": enum("butt", "round", "square"),
        "line_join": enum("miter", "round", "bevel"),
        "miter_limit": {"type": "number", "minimum": 1, "maximum": 1000},
        "stroke_align": enum("center", "inside", "outside"),
        "width_profile": {
            "type": "array",
            "minItems": 2,
            "maxItems": 128,
            "items": {
                "type": "array",
                "items": {"type": "number", "minimum": 0},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "taper_start": {"type": "number", "minimum": 0, "maximum": 1},
        "taper_end": {"type": "number", "minimum": 0, "maximum": 1},
        "marker_start": enum("none", "triangle", "open", "concave", "round"),
        "marker_end": enum("none", "triangle", "open", "concave", "round"),
        "marker_size": {"type": "number", "exclusiveMinimum": 0, "maximum": 4096},
        "marker_style": enum("triangle", "open", "concave", "round"),
    }
    props["strokes"] = {
        "type": "array",
        "maxItems": 16,
        "items": {
            "type": "object",
            "properties": {
                "color": S,
                "width": {"type": "number", "minimum": 0, "maximum": 1024},
                **{
                    key: value
                    for key, value in props.items()
                    if key not in ("marker_start", "marker_end", "marker_size", "marker_style")
                },
            },
            "required": ["color", "width"],
            "additionalProperties": False,
        },
    }
    for key, value in list(props.items()):
        props[key] = {**value, "description": {
            "dash": "Dash/gap pixel lengths or dashed/dotted preset; separate from trim_start/trim_end reveal.",
            "width_profile": "Ordered [fraction along path, width multiplier] control points; endpoints 0 and 1.",
            "strokes": "Additional strokes painted in array order after the base stroke.",
            "taper_start": "Width multiplier at the start; reaches full width at the middle.",
            "marker_size": "Arrowhead length and width in local pixels (not a multiplier). Use at least twice stroke_width for a visible head; 1–5 px heads may be hidden by a thick shaft.",
            "taper_end": "Width multiplier at the end; starts tapering from the middle.",
            "stroke_align": "Where the stroke sits on the outline: inside (the default for closed shapes: its outer "
                            "edge on the outline, so it stays in the box), center (the default for paths, arcs, lines "
                            "and open shapes) or outside. The same in every renderer and export.",
        }.get(key, key.replace("_", " ").capitalize() + ".")}
    return props


def validate(layer):
    from .model import finite

    for settings in [layer, *layer.get("strokes", [])]:
        for key in ("dash_offset", "taper_start", "taper_end", "marker_size", "miter_limit", "width"):
            if key in settings:
                finite(settings[key], key, -1e6 if key == "dash_offset" else 0, 1e6)
        require(settings.get("line_cap", "butt") in ("butt", "round", "square"), "Invalid line cap")
        require(settings.get("line_join", "miter") in ("miter", "round", "bevel"), "Invalid line join")
        require(
            settings.get("stroke_align", "center") in ("center", "inside", "outside"),
            "Invalid stroke alignment",
        )
        require(1 <= settings.get("miter_limit", 4) <= 1000, "Invalid miter limit")
        dash = settings.get("dash")
        require(
            dash is None or dash in ("dashed", "dotted")
            if isinstance(dash, str)
            else dash is None
            or isinstance(dash, list)
            and 1 <= len(dash) <= 32
            and all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in dash),
            "Invalid dash pattern",
        )
        profile = settings.get("width_profile")
        if profile:
            require(
                len(profile) >= 2
                and profile[0][0] == 0
                and profile[-1][0] == 1
                and all(0 <= a[0] < b[0] <= 1 for a, b in zip(profile, profile[1:]))
                and all(0 <= q[1] <= 100 for q in profile),
                "Width profile must have increasing fractions from 0 to 1 and nonnegative widths",
            )
    require(len(layer.get("strokes", [])) <= 16, "At most 16 additional strokes")


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def area(points):
    return sum(cross(a, b) for a, b in zip(points, points[1:] + points[:1])) / 2


def unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d) if d > 1e-12 else (1, 0)


def _parallel(points, distances, closed, join, miter_limit):
    out = []
    for i, p in enumerate(points):
        before = unit(points[i - 1], p) if closed or i else unit(p, points[1])
        after = unit(p, points[(i + 1) % len(points)]) if closed or i + 1 < len(points) else before
        d = distances[i]
        a = (p[0] - before[1] * d, p[1] + before[0] * d)
        b = (p[0] - after[1] * d, p[1] + after[0] * d)
        turn = cross(before, after)
        if abs(turn) < 1e-9 or not closed and i in (0, len(points) - 1):
            out.append(b)
            continue
        t = cross((b[0] - a[0], b[1] - a[1]), after) / turn
        intersection = (a[0] + before[0] * t, a[1] + before[1] * t)
        outer = turn * d < 0
        reach = math.dist(p, intersection)
        inner_limit = max(abs(d), min(math.dist(points[i - 1], p),
                                     math.dist(p, points[(i + 1) % len(points)])))
        if (not outer and reach <= inner_limit) or (outer and join == "miter" and reach <= abs(d) * miter_limit):
            out.append(intersection)
        elif outer and join == "round" and abs(d) > 1e-12:
            start, end = math.atan2(a[1] - p[1], a[0] - p[0]), math.atan2(b[1] - p[1], b[0] - p[0])
            delta = (end - start + math.pi) % math.tau - math.pi
            count = max(2, math.ceil(abs(delta) * max(3, math.sqrt(abs(d) * 2))))
            out.extend(
                (
                    p[0] + abs(d) * math.cos(start + delta * j / count),
                    p[1] + abs(d) * math.sin(start + delta * j / count),
                )
                for j in range(count + 1)
            )
        else:
            out.extend((a, b))
    return out


def offset_polygon(points, distance, join="miter", miter_limit=4):
    points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if points and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        return []
    signed = -distance if area(points) > 0 else distance
    return _parallel(points, [signed] * len(points), True, join, miter_limit)


def stroke_outline(
    points, width, closed=False, cap="butt", join="miter", miter_limit=4, widths=None, align="center"
):
    from .shape_catalog import poly

    points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if closed and len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 2 or width <= 0:
        return ""
    widths = widths if widths and len(widths) == len(points) else [width] * len(points)
    half = [v / 2 for v in widths]
    left, right = half, [-v for v in half]
    if closed and align != "center":
        inward = area(points) > 0
        if (align == "inside") == inward:
            left, right = widths, [0] * len(points)
        else:
            left, right = [0] * len(points), [-v for v in widths]
    a = _parallel(points, left, closed, join, miter_limit)
    b = _parallel(points, right, closed, join, miter_limit)
    if closed:
        # Same-orientation components around a contour cancel the inner winding.
        return poly(a) + " " + poly(b[::-1])
    if cap == "square":
        u, v = unit(points[0], points[1]), unit(points[-2], points[-1])
        for contour in (a, b):
            contour[0] = (contour[0][0] - u[0] * half[0], contour[0][1] - u[1] * half[0])
            contour[-1] = (contour[-1][0] + v[0] * half[-1], contour[-1][1] + v[1] * half[-1])
    outline = list(a)
    if cap == "round":
        q, r = points[-1], half[-1]
        start = math.atan2(a[-1][1] - q[1], a[-1][0] - q[0])
        count = max(8, math.ceil(math.sqrt(max(1, r)) * 4))
        outline.extend(
            (
                q[0] + r * math.cos(start - math.pi * i / count),
                q[1] + r * math.sin(start - math.pi * i / count),
            )
            for i in range(1, count)
        )
    outline.extend(b[::-1])
    if cap == "round":
        q, r = points[0], half[0]
        start = math.atan2(b[0][1] - q[1], b[0][0] - q[0])
        count = max(8, math.ceil(math.sqrt(max(1, r)) * 4))
        outline.extend(
            (
                q[0] + r * math.cos(start - math.pi * i / count),
                q[1] + r * math.sin(start - math.pi * i / count),
            )
            for i in range(1, count)
        )
    return poly(outline)


def dashed(points, pattern, offset=0):
    """Slice the arc-length domain, retaining fractions for variable-width interpolation."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 1e-12:
        return []
    if not pattern:
        return [(points, [sum(lengths[:i]) / total for i in range(len(points))])]
    pattern = pattern * 2 if len(pattern) % 2 else pattern
    phase = offset % sum(pattern)
    index = 0
    while phase >= pattern[index]:
        phase -= pattern[index]
        index = (index + 1) % len(pattern)
    remaining = pattern[index] - phase
    distance = 0
    runs = []
    run = []
    fractions = []
    for a, b, length in zip(points, points[1:], lengths):
        used = 0
        while used < length - 1e-9:
            step = min(remaining, length - used)
            p = (a[0] + (b[0] - a[0]) * used / length, a[1] + (b[1] - a[1]) * used / length)
            q = (a[0] + (b[0] - a[0]) * (used + step) / length, a[1] + (b[1] - a[1]) * (used + step) / length)
            if index % 2 == 0:
                if not run:
                    run = [p]
                    fractions = [(distance + used) / total]
                run.append(q)
                fractions.append((distance + used + step) / total)
            used += step
            remaining -= step
            if remaining <= 1e-9:
                if run:
                    runs.append((run, fractions))
                    run = []
                    fractions = []
                index = (index + 1) % len(pattern)
                remaining = pattern[index]
        distance += length
    if run:
        runs.append((run, fractions))
    return runs


def width_at(t, settings):
    profile = settings.get("width_profile") or [
        [0, settings.get("taper_start", 1)],
        [0.5, 1],
        [1, settings.get("taper_end", 1)],
    ]
    for a, b in zip(profile, profile[1:]):
        if t <= b[0]:
            return a[1] + (b[1] - a[1]) * (t - a[0]) / max(b[0] - a[0], 1e-12)
    return profile[-1][1]


def expanded(layer, path):
    from .geometry import path_polygons
    from .shape_catalog import arrowhead

    contours = path_polygons(path)
    result = []
    settings = [
        {
            "color": layer.get("stroke", "transparent"),
            "width": layer.get("stroke_width", 1),
            **{k: layer[k] for k in FIELDS if k in layer and k != "strokes"},
        },
        *layer.get("strokes", []),
    ]
    if layer.get("shape") in OPEN_SHAPES:
        if settings[0]["color"] == "transparent":
            settings[0]["color"] = layer.get("fill", "white")
    from .trim import trim_range

    trim = trim_range(layer)
    for style in settings:
        width = style["width"]
        if width <= 0 or style["color"] == "transparent":
            continue
        dash = style.get("dash")
        pattern = (
            (
                [width * 3, width * 2]
                if dash == "dashed"
                else [max(width * 0.01, 0.01), width * 2]
                if dash == "dotted"
                else dash
            )
            if isinstance(dash, str)
            else dash
        )
        cap = style.get("line_cap", "round" if dash == "dotted" else "butt")
        alignment = stroke_align(layer, style)
        join, miter_limit = style.get("line_join", "miter"), style.get("miter_limit", 4)
        out = []
        rest = contours
        if alignment != "center" and not (pattern or trim or any(
                key in style for key in ("width_profile", "taper_start", "taper_end"))):
            # Inside and outside strokes of the closed contours: the band between the filled area and
            # that area shrunk or grown by the stroke width, so the stroke's outer (inside) or inner
            # (outside) edge is exactly the outline, holes included, however tight the curves.
            out.append(aligned_band([c for c in contours if len(c) > 3 and c[0] == c[-1]], width, alignment,
                                    join, miter_limit))
            rest = [c for c in contours if not (len(c) > 3 and c[0] == c[-1])]
        for original in rest:
            points = [
                point for index, point in enumerate(original) if index == 0 or point != original[index - 1]
            ]
            closed = len(points) > 2 and points[0] == points[-1]
            if closed and (pattern or trim) and alignment != "center":
                inward = area(points) > 0
                sign = 1 if (alignment == "inside") == inward else -1
                points = _parallel(
                    points[:-1],
                    [sign * width / 2] * (len(points) - 1),
                    True,
                    join,
                    miter_limit,
                )
                points = points + points[:1]
            for run, fractions in dashed(points, pattern, style.get("dash_offset", 0)):
                if trim:
                    run, fractions = clip_run(run, fractions, *trim)
                    if len(run) < 2:
                        continue
                widths = [width * width_at(q, style) for q in fractions]
                if closed and not pattern and not trim:
                    widths = widths[:-1]
                out.append(
                    stroke_outline(
                        run,
                        width,
                        closed and not pattern and not trim,
                        cap,
                        join,
                        miter_limit,
                        widths,
                        alignment,
                    )
                )
            marker_points = points
            if trim and not closed:
                runs = list(dashed(points, None, 0))
                marker_points = clip_run(*runs[0], *trim)[0] if runs else []
            if not closed and len(marker_points) >= 2:
                points = marker_points
                for which, tip, tangent in [
                    ("start", points[0], (points[0][0] - points[1][0], points[0][1] - points[1][1])),
                    ("end", points[-1], (points[-1][0] - points[-2][0], points[-1][1] - points[-2][1])),
                ]:
                    marker = style.get("marker_" + which, layer.get("marker_" + which, "none"))
                    if marker != "none":
                        out.append(
                            arrowhead(
                                tip,
                                tangent,
                                layer.get("marker_size", width * 4),
                                layer.get("marker_size", width * 4),
                                marker,
                            )
                        )
        result.append((" ".join(out), style["color"]))
    return result


def aligned_band(contours, width, alignment, join="miter", miter_limit=4):
    """Path data of an ``inside`` or ``outside`` stroke of ``width`` around the area the closed point
    lists ``contours`` fill (nonzero winding); the whole area when an inside stroke is wider than it."""
    from shapely import BufferJoinStyle
    from shapely.geometry.polygon import orient
    from .shape_catalog import poly
    from .vector_boolean import filled_region

    if not contours or width <= 0:
        return ""
    region = filled_region(contours)
    if region.is_empty:
        return ""
    style = {"round": BufferJoinStyle.round, "bevel": BufferJoinStyle.bevel}.get(join, BufferJoinStyle.mitre)

    def grown(distance):
        return region.buffer(distance, quad_segs=16, join_style=style, mitre_limit=miter_limit)

    band = region.difference(grown(-width)) if alignment == "inside" else grown(width).difference(region)
    parts = []
    for polygon in getattr(band, "geoms", [band]):
        if polygon.geom_type != "Polygon" or polygon.is_empty:
            continue
        polygon = orient(polygon)
        parts.append(poly(list(polygon.exterior.coords)))
        parts.extend(poly(list(ring.coords)) for ring in polygon.interiors)
    return " ".join(parts)


# The miter limit of native strokes that trace inside_centre_line: high enough that a sharp star point
# keeps its tip (the band drawn in PNG has no limit on its outer edge).
NATIVE_MITER_LIMIT = 16


def inside_centre_line(layer, pad):
    """Path data, in the layer's pixels, of the line a native stroke of width ``2 * pad`` (mitred, miter
    limit ``NATIVE_MITER_LIMIT``) follows to stroke a plain polygon, star or shortcut inside its outline:
    the outline shrunk by ``pad``, so the stroke's outer edge is the outline. None when that native
    stroke would not draw the same band as ``aligned_band`` (the stroke reaches the shape's middle, or a
    corner is too sharp): draw the band from ``primitives`` instead."""
    from shapely import BufferJoinStyle
    from shapely.geometry.polygon import orient
    from .geometry import path_polygons
    from .shape_catalog import poly
    from .vector_boolean import filled_region
    from .vector_paths import pixel_path

    contours = [c for c in path_polygons(pixel_path(layer)) if len(c) > 3 and c[0] == c[-1]]
    region = filled_region(contours) if contours else None
    if region is None or region.geom_type != "Polygon":
        return None
    mitre = {"join_style": BufferJoinStyle.mitre, "mitre_limit": NATIVE_MITER_LIMIT}
    centre = region.buffer(-pad, **mitre)
    if centre.is_empty or centre.geom_type != "Polygon" or len(centre.interiors) != len(region.interiors):
        return None
    if centre.buffer(pad, **mitre).symmetric_difference(region).area > 0.05 * region.length:
        return None
    centre = orient(centre)
    return " ".join([poly(list(centre.exterior.coords)), *(poly(list(r.coords)) for r in centre.interiors)])


def active(layer):
    return layer.get("vector_geometry", False) or any(key in layer for key in FIELDS if key != "line_cap")


def primitives(layer, project=None):
    """Ordered (filled path, paint) primitives in the layer's pixel coordinate space."""
    from .vector_paths import pixel_path

    line = plain_line(layer, project)
    if line is not None:
        return line
    path = pixel_path(layer)
    if project is not None and layer.get("_distort_groups"):
        from .vector_paths import group_warp

        path = group_warp(path, layer, project)
    result = []
    open_kind = layer.get("shape") in OPEN_SHAPES
    if not open_kind:
        result.append((path, default_fill(layer)))
    stroke_path = path
    if layer.get("shape") == "star-rating":
        stroke_path = pixel_path({**layer, "rating": layer.get("count", 5)})
        if project is not None and layer.get("_distort_groups"):
            from .vector_paths import group_warp

            stroke_path = group_warp(stroke_path, layer, project)
    return result + expanded(layer, stroke_path)


def plain_line(layer, project=None):
    """The primitives of a plain ``line`` with a visible stroke (drawn here only for its fractional size):
    its ends half a stroke in from the box corners, as every renderer draws it
    (``geometry.stroke_inset``); None for other layers."""
    from .shape_catalog import active as catalog_active
    from .geometry import stroke_inset

    if (layer.get("shape") != "line" or active(layer) or catalog_active(layer) or layer.get("distort")
            or layer.get("_distort_groups")):
        return None
    stroke = layer.get("stroke", "transparent")
    if project is not None:
        from .design import resolve_color
        from .render import color

        visible = color(resolve_color(stroke, project.state))[3] > 0
    else:
        visible = stroke != "transparent"
    inset, pad = stroke_inset(layer, visible)
    if not pad:
        return None
    w, h = layer["width"], layer["height"]
    return expanded(layer, f"M {inset} {inset} L {w - inset} {h - inset}")


def render(project, layer, size=None, matrix=None):
    """The shape as an RGBA image of its box plus the margin its geometry reaches past it (centred on the
    box). ``size`` and ``matrix`` draw that image's content into an image of ``size`` instead, mapped by
    the affine ``matrix`` from the image's pixels (see ``text.render_text``)."""
    import io
    import xml.etree.ElementTree as ET
    from PIL import Image
    import resvg_py
    from .colors import parse, hex_of
    from .design import resolve_color

    w, h = layer["width"], layer["height"]
    drawn = primitives(layer, project)
    mx, my = path_margin(drawn, w, h)
    own = (max(1, math.ceil(w)) + 2 * mx, max(1, math.ceil(h)) + 2 * my)
    project.limits.size(*own)
    frame = {"width": str(own[0]), "height": str(own[1]),
             "viewBox": f"{-mx - (math.ceil(w) - w) / 2} {-my - (math.ceil(h) - h) / 2} {own[0]} {own[1]}"}
    if matrix is None:
        root = parent = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", **frame)
    else:
        project.limits.size(*size)
        root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(size[0]), height=str(size[1]))
        group = ET.SubElement(root, "g", transform="matrix(" + " ".join(format(v, ".10g") for v in matrix) + ")")
        # The frame's margin already holds everything drawn, so it needs no clip (whose anti-aliased
        # edge would dim ink ending on it).
        parent = ET.SubElement(group, "svg", overflow="visible", **frame)
    for path, paint in drawn:
        rgba = parse(resolve_color(paint, project.state))
        if path and rgba[3]:
            ET.SubElement(
                parent, "path", d=path, fill=hex_of((*rgba[:3], 1)), attrib={"fill-opacity": str(rgba[3])}
            )
    image = Image.open(
        io.BytesIO(resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode")))
    ).convert("RGBA")
    image.info["vixl_vector_overflow"] = True
    return image


def path_margin(primitives, w, h):
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.svgLib.path import parse_path

    pen = BoundsPen(None)
    for path, paint in primitives:
        if path and paint != "transparent":
            parse_path(path, pen)
    if pen.bounds is None:
        return 0, 0
    x0, y0, x1, y1 = pen.bounds
    return math.ceil(max(0, -x0, x1 - w)), math.ceil(max(0, -y0, y1 - h))


def margin(layer):
    if layer.get("type") != "shape":
        return 0, 0
    from .shape_catalog import active as catalog_active

    from .geometry import path_overflows

    if not (path_overflows(layer) or active(layer) or catalog_active(layer) or layer.get("distort") or layer.get("_distort_groups")):
        visible = layer.get("stroke", "transparent") != "transparent" and layer.get("stroke_width", 1) > 0
        if visible and layer.get("shape") in PATH_SHAPES:
            return native_stroke_margin(layer)
        if stroke_align(layer) == "inside":
            return 0, 0  # The stroke stays inside the shape's box.
        width = layer.get("stroke_width", 0) if layer.get("stroke", "transparent") != "transparent" else 0
        return math.ceil(width / 2), math.ceil(width / 2)
    mx, my = path_margin(primitives(layer), layer["width"], layer["height"])
    for parent in layer.get("_distort_groups", []):
        settings = parent["distort"]
        amount = abs(settings.get("amount", 0.25))
        extra = max(parent["content_width"], parent["content_height"]) * (2 + amount)
        mx += math.ceil(extra)
        my += math.ceil(extra)
    return mx, my


def native_stroke_margin(layer):
    """Whole pixels ``(mx, my)`` by which a path or arc drawn with a native SVG stroke (stroke width in
    its view units, miter limit 4) reaches past its box: the raster image holds all of it, as the SVG
    and PDF exports draw it."""
    from .geometry import path_extents, shape_path

    path, view = shape_path(layer)
    w, h = layer["width"], layer["height"]
    sx, sy = w / view[0], h / view[1]
    cap = layer.get("line_cap")
    # A miter join reaches up to the miter limit (4) times half the stroke; a square cap sqrt(2) times.
    reach = layer.get("stroke_width", 1) / 2 * (1 if cap == "round" else 4)
    x0, y0, x1, y1 = path_extents(path)
    return (math.ceil(max(0, reach * sx - x0 * sx, x1 * sx + reach * sx - w)),
            math.ceil(max(0, reach * sy - y0 * sy, y1 * sy + reach * sy - h)))


def clip_run(points, fractions, start, end):
    output, positions = [], []
    for a, b, ta, tb in zip(points, points[1:], fractions, fractions[1:]):
        lo, hi = max(start, ta), min(end, tb)
        if hi <= lo or tb <= ta:
            continue
        for t in (lo, hi):
            point = tuple(a[j] + (b[j] - a[j]) * (t - ta) / (tb - ta) for j in (0, 1))
            if not output or output[-1] != point:
                output.append(point)
                positions.append(t)
    return output, positions
