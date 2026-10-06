"""Robust offsets of flattened vector contours, including holes and concave splits.

Curves are flattened to a tenth-pixel error bound before GEOS polygonization. Faces are
selected by the SVG nonzero winding rule, so crossing star paths and compound logos retain
exactly the same filled regions. GEOS handles inset collapse and changes in topology.
"""

import math

from .errors import require


def flatten(path, tolerance=0.1):
    from .geometry import parse_path

    contours = []
    points = []
    current = None
    total = 0

    def curve(controls, depth=0):
        a, b = controls[0], controls[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        error = max(
            (
                abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / norm if norm > 1e-12 else math.dist(p, a)
                for p in controls[1:-1]
            ),
            default=0,
        )
        # Collinear control points may still reverse the path; test their chord projection too.
        inside = all(
            -tolerance <= (p[0] - a[0]) * dx + (p[1] - a[1]) * dy <= norm * norm + tolerance
            for p in controls[1:-1]
        )
        if depth >= 20 or error <= tolerance and inside:
            return [b]
        left, right = [a], [b]
        row = controls
        while len(row) > 1:
            row = [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for p, q in zip(row, row[1:])]
            left.append(row[0])
            right.append(row[-1])
        return curve(left, depth + 1) + curve(right[::-1], depth + 1)

    for command, values in parse_path(path):
        pts = [tuple(p) for p in zip(values[::2], values[1::2])]
        if command == "M":
            if points:
                contours.append(points)
            points = [pts[0]]
            current = pts[0]
        elif command == "L":
            if current != pts[0]:
                points.append(pts[0])
            current = pts[0]
        elif command in ("C", "Q"):
            points.extend(curve([current, *pts]))
            current = pts[-1]
        elif command == "Z":
            if points[-1] != points[0]:
                points.append(points[0])
            current = points[0]
        total += len(pts)
        require(total + len(points) <= 100_000, "Offset geometry exceeds 100,000 points", "resource_limit")
    if points:
        contours.append(points)
    require(
        sum(len(p) for p in contours) <= 100_000, "Offset geometry exceeds 100,000 points", "resource_limit"
    )
    return contours


def winding(points, x, y):
    result = 0
    for a, b in zip(points, points[1:]):
        side = (b[0] - a[0]) * (y - a[1]) - (x - a[0]) * (b[1] - a[1])
        if a[1] <= y < b[1] and side > 0:
            result += 1
        elif b[1] <= y < a[1] and side < 0:
            result -= 1
    return result


def offset(path, distance, join="miter", miter_limit=4):
    from shapely import BufferJoinStyle
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    from .shape_catalog import poly

    contours = flatten(path)
    require(
        contours and all(len(p) > 3 and p[0] == p[-1] for p in contours),
        "Offset requires closed contours; use outline-stroke for an open path",
    )
    faces = polygonize(unary_union([LineString(p) for p in contours]))
    filled = []
    for face in faces:
        q = face.representative_point()
        if sum(winding(p, q.x, q.y) for p in contours):
            filled.append(face)
    geometry = unary_union(filled)
    require(not geometry.is_empty, "Path has no filled area to offset")
    result = geometry.buffer(
        distance,
        quad_segs=24,
        join_style={
            "round": BufferJoinStyle.round,
            "miter": BufferJoinStyle.mitre,
            "bevel": BufferJoinStyle.bevel,
        }[join],
        mitre_limit=miter_limit,
    )
    require(not result.is_empty, "Offset collapses the path")
    polygons = list(result.geoms) if result.geom_type == "MultiPolygon" else [result]
    paths = []
    for polygon in polygons:
        paths.append(poly(list(polygon.exterior.coords)))
        paths.extend(poly(list(ring.coords)) for ring in polygon.interiors)
    require(
        sum(part.count("L") for part in paths) <= 8192,
        "Offset result exceeds 8192 editable nodes",
        "resource_limit",
    )
    return " ".join(paths)
