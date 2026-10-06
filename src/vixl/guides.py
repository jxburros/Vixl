"""Guides and grids beyond right angles: geometry, generated systems, placement and checks.

A guide is named document metadata, never painted into output. Besides the original axis guides
(``{"axis": "x", "position": 64}``) a guide can be an angled ``line``, a ``ray`` or ``segment``,
a ``point``, a ``circle`` or a curved ``path``. ``grid`` generates whole systems of guides:
columns, baselines, thirds, golden sections, harmonic armatures, golden spirals, polar/radial,
isometric, triangular, hexagonal, oblique (skew) and 1–3 point perspective grids.

``place`` puts layers on a guide (at a position, distributed along it, at intersections) and can
turn them to follow it; ``snap`` moves near misses onto guides. The ``guides`` and ``alignment``
checks report what an agent cannot see: things almost, but not exactly, on a guide, almost
aligned with each other, or almost at the same angle.
"""

from copy import deepcopy
import math

import numpy as np

from .errors import VixlError, require
from .geometry import ANCHORS, canonical_anchor
from .model import finite

TYPES = ("place", "snap")
KINDS = ("axis", "line", "ray", "segment", "point", "circle", "path")
GRID_KINDS = ("columns", "baseline", "thirds", "golden", "armature", "golden-spiral", "polar", "isometric",
              "triangular", "hex", "oblique", "perspective")
MAX_GUIDES = 1024
PHI = (1 + 5 ** 0.5) / 2


# ---------------------------------------------------------------------------------------------
# Guide records


def kind_of(guide):
    return guide.get("kind", "axis")


def validate_guide(name, guide):
    from .design import named

    named(name)
    require(isinstance(guide, dict), "Invalid guide", "invalid_project")
    kind = kind_of(guide)
    require(kind in KINDS, f"Unknown guide kind {kind!r}", "invalid_project")
    common = {"grid", "kind", "generated"}
    fields = {
        "axis": {"axis", "position"},
        "line": {"x", "y", "angle"},
        "ray": {"x", "y", "angle"},
        "segment": {"points"},
        "point": {"x", "y"},
        "circle": {"x", "y", "radius"},
        "path": {"d"},
    }[kind]
    require(not set(guide) - fields - common, f"Invalid {kind} guide fields", "invalid_project")
    if kind == "axis":
        require(guide["axis"] in ("x", "y"), "Invalid guide axis")
        finite(guide["position"], "guide position", -1e9, 1e9)
    elif kind == "segment":
        points = guide["points"]
        require(isinstance(points, list) and len(points) == 2 and all(isinstance(q, list) and len(q) == 2 for q in points),
                "A segment guide needs two [x, y] points")
        for q in points:
            for v in q:
                finite(v, "guide point", -1e9, 1e9)
    elif kind == "path":
        from .geometry import parse_path

        parse_path(guide["d"])
    else:
        finite(guide["x"], "guide x", -1e9, 1e9)
        finite(guide["y"], "guide y", -1e9, 1e9)
        if kind in ("line", "ray"):
            finite(guide["angle"], "guide angle", -36000, 36000)
        if kind == "circle":
            finite(guide["radius"], "guide radius", 0.001, 1e9)


def make_guide(op):
    """A guide record from a ``guide`` operation."""
    kind = op.get("kind", "axis" if "axis" in op else None)
    require(kind in KINDS, f"guide needs axis + position, or kind: {', '.join(KINDS)}", field="kind", allowed=list(KINDS))
    if kind == "axis":
        require("axis" in op and "position" in op, "An axis guide needs axis (x or y) and position", field="axis")
        return {"axis": op["axis"], "position": op["position"]}
    if kind in ("line", "ray") and "points" in op and "angle" not in op:
        (x1, y1), (x2, y2) = op["points"]
        require((x1, y1) != (x2, y2), "The two points must differ", field="points")
        return {"kind": kind, "x": x1, "y": y1, "angle": math.degrees(math.atan2(y2 - y1, x2 - x1))}
    needs = {"line": ("x", "y", "angle"), "ray": ("x", "y", "angle"), "segment": ("points",), "point": ("x", "y"),
             "circle": ("x", "y", "radius"), "path": ("d",)}[kind]
    missing = [key for key in needs if key not in op]
    require(not missing, f"A {kind} guide needs {', '.join(needs)}", field=missing[0] if missing else None)
    return {"kind": kind, **{key: deepcopy(op[key]) for key in needs}}


# ---------------------------------------------------------------------------------------------
# Geometry


def _clip_line(px, py, dx, dy, box, ray=False):
    """The part of the line (or ray) p + t·d inside ``box`` (x0, y0, x1, y1), as two points."""
    x0, y0, x1, y1 = box
    low, high = (0.0 if ray else -math.inf), math.inf
    for p, d, lo, hi in ((px, dx, x0, x1), (py, dy, y0, y1)):
        if abs(d) < 1e-12:
            if p < lo or p > hi:
                return None
            continue
        a, b = (lo - p) / d, (hi - p) / d
        low, high = max(low, min(a, b)), min(high, max(a, b))
    if low > high:
        return None
    return np.array([[px + low * dx, py + low * dy], [px + high * dx, py + high * dy]])


def polyline(guide, canvas, samples=256):
    """The guide as points on the canvas: a 2-point segment for lines (clipped to the canvas,
    extended by a margin), a closed loop for circles, a sampled curve for paths, one point for
    points. Returns (points, closed)."""
    w, h = canvas["width"], canvas["height"]
    margin = max(w, h)
    box = (-margin, -margin, w + margin, h + margin)
    kind = kind_of(guide)
    if kind == "axis":
        if guide["axis"] == "x":
            return np.array([[guide["position"], box[1]], [guide["position"], box[3]]]), False
        return np.array([[box[0], guide["position"]], [box[2], guide["position"]]]), False
    if kind in ("line", "ray"):
        a = math.radians(guide["angle"])
        visible = _clip_line(guide["x"], guide["y"], math.cos(a), math.sin(a), (0, 0, w, h), kind == "ray")
        if visible is None:
            visible = _clip_line(guide["x"], guide["y"], math.cos(a), math.sin(a), box, kind == "ray")
        require(visible is not None, "Guide does not cross the canvas", field="guide")
        return visible, False
    if kind == "segment":
        return np.array(guide["points"], dtype=float), False
    if kind == "point":
        return np.array([[guide["x"], guide["y"]]], dtype=float), False
    if kind == "circle":
        t = np.linspace(0, math.tau, samples, endpoint=False)
        return np.column_stack([guide["x"] + guide["radius"] * np.cos(t), guide["y"] + guide["radius"] * np.sin(t)]), True
    from .geometry import path_polygons

    loops = [np.array(poly, dtype=float) for poly in path_polygons(guide["d"])]
    points = max(loops, key=len)
    closed = len(points) > 2 and np.allclose(points[0], points[-1])
    return (points[:-1] if closed else points), closed


def _segments(points, closed):
    if closed:
        return points, np.roll(points, -1, axis=0)
    return points[:-1], points[1:]


def nearest(guide, canvas, q):
    """(point, distance, tangent angle°) on ``guide`` closest to ``q``."""
    kind = kind_of(guide)
    q = np.asarray(q, dtype=float)
    if kind == "point":
        p = np.array([guide["x"], guide["y"]])
        return p, float(np.hypot(*(q - p))), 0.0
    if kind == "circle":
        c = np.array([guide["x"], guide["y"]])
        v = q - c
        r = float(np.hypot(*v))
        u = v / r if r > 1e-12 else np.array([1.0, 0.0])
        p = c + u * guide["radius"]
        return p, abs(r - guide["radius"]), math.degrees(math.atan2(u[1], u[0])) + 90
    if kind == "axis":
        if guide["axis"] == "x":
            return np.array([guide["position"], q[1]]), abs(q[0] - guide["position"]), 90.0
        return np.array([q[0], guide["position"]]), abs(q[1] - guide["position"]), 0.0
    if kind in ("line", "ray"):
        a = math.radians(guide["angle"])
        d = np.array([math.cos(a), math.sin(a)])
        o = np.array([guide["x"], guide["y"]])
        t = float(np.dot(q - o, d))
        if kind == "ray":
            t = max(0.0, t)
        p = o + t * d
        return p, float(np.hypot(*(q - p))), guide["angle"]
    points, closed = polyline(guide, canvas)
    a, b = _segments(points, closed)
    ab = b - a
    length = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-24)
    t = np.clip(np.einsum("ij,ij->i", q - a, ab) / length, 0, 1)
    candidates = a + ab * t[:, None]
    distance = np.hypot(*(candidates - q).T)
    i = int(np.argmin(distance))
    return candidates[i], float(distance[i]), math.degrees(math.atan2(ab[i, 1], ab[i, 0]))


def point_at(guide, canvas, fraction, start=-90.0):
    """(point, tangent angle°) at ``fraction`` (0–1) along a guide. Lines are measured across
    the canvas; circles clockwise from ``start`` degrees (−90 is the top)."""
    kind = kind_of(guide)
    if kind == "point":
        return np.array([guide["x"], guide["y"]], dtype=float), 0.0
    if kind == "circle":
        a = math.radians(start + 360 * fraction)
        p = np.array([guide["x"] + guide["radius"] * math.cos(a), guide["y"] + guide["radius"] * math.sin(a)])
        return p, math.degrees(a) + 90
    points, closed = polyline(guide, canvas)
    a, b = _segments(points, closed)
    lengths = np.hypot(*(b - a).T)
    total = float(lengths.sum())
    require(total > 0, "Guide has no length", field="guide")
    target = fraction * total
    cumulative = np.concatenate([[0], np.cumsum(lengths)])
    i = int(np.clip(np.searchsorted(cumulative, target, side="right") - 1, 0, len(lengths) - 1))
    t = (target - cumulative[i]) / max(lengths[i], 1e-12)
    p = a[i] + (b[i] - a[i]) * t
    return p, math.degrees(math.atan2(b[i, 1] - a[i, 1], b[i, 0] - a[i, 0]))


def guide_length(guide, canvas):
    kind = kind_of(guide)
    if kind == "point":
        return 0.0
    if kind == "circle":
        return math.tau * guide["radius"]
    points, closed = polyline(guide, canvas)
    a, b = _segments(points, closed)
    return float(np.hypot(*(b - a).T).sum())


def intersections(first, second, canvas):
    """Points where two guides cross, in reading order (top to bottom, left to right)."""
    found = []
    kinds = (kind_of(first), kind_of(second))
    if "point" in kinds:
        point, other = (first, second) if kinds[0] == "point" else (second, first)
        p = np.array([point["x"], point["y"]])
        if nearest(other, canvas, p)[1] < 0.5:
            found.append(p)
    elif kinds == ("circle", "circle"):
        c1, c2 = np.array([first["x"], first["y"]]), np.array([second["x"], second["y"]])
        r1, r2 = first["radius"], second["radius"]
        d = float(np.hypot(*(c2 - c1)))
        if 1e-9 < d <= r1 + r2 and d >= abs(r1 - r2):
            a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
            h = math.sqrt(max(0.0, r1 * r1 - a * a))
            m = c1 + a * (c2 - c1) / d
            off = h * np.array([-(c2 - c1)[1], (c2 - c1)[0]]) / d
            found += [m + off, m - off] if h > 1e-9 else [m]
    else:
        pa, ca = polyline(first, canvas)
        pb, cb = polyline(second, canvas)
        a1, a2 = _segments(pa, ca)
        b1, b2 = _segments(pb, cb)
        for p, p2 in zip(a1, a2):
            r = p2 - p
            s = b2 - b1
            denominator = r[0] * s[:, 1] - r[1] * s[:, 0]
            valid = np.abs(denominator) > 1e-12
            if not valid.any():
                continue
            qp = b1 - p
            t = np.where(valid, (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / np.where(valid, denominator, 1), -1)
            u = np.where(valid, (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / np.where(valid, denominator, 1), -1)
            hit = valid & (t >= -1e-9) & (t <= 1 + 1e-9) & (u >= -1e-9) & (u <= 1 + 1e-9)
            for k in np.nonzero(hit)[0]:
                found.append(p + t[k] * r)
    unique = []
    for q in found:
        if all(np.hypot(*(q - other)) > 0.5 for other in unique):
            unique.append(q)
    return sorted(unique, key=lambda q: (round(float(q[1]), 3), round(float(q[0]), 3)))


def angle_of(guide):
    """A straight guide's direction in degrees (0–180), or None for points, circles and paths."""
    kind = kind_of(guide)
    if kind == "axis":
        return 90.0 if guide["axis"] == "x" else 0.0
    if kind in ("line", "ray"):
        return guide["angle"] % 180
    if kind == "segment":
        (x1, y1), (x2, y2) = guide["points"]
        return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
    return None


# ---------------------------------------------------------------------------------------------
# Generated systems


def _region(op, canvas):
    region = op.get("region")
    if region is None:
        return 0.0, 0.0, float(canvas["width"]), float(canvas["height"])
    require(isinstance(region, list) and len(region) == 4, "region must be [x, y, width, height]", field="region")
    x, y, w, h = (finite(v, "region", -1e9, 1e9) for v in region)
    require(w > 0 and h > 0, "region width and height must be positive", field="region")
    return x, y, w, h


def _parallel(name, angle, spacing, region, through, prefix="a"):
    """Lines at ``angle`` every ``spacing`` px, one passing through ``through``, that cross the region."""
    x, y, w, h = region
    a = math.radians(angle)
    normal = np.array([-math.sin(a), math.cos(a)])
    corners = np.array([[x, y], [x + w, y], [x, y + h], [x + w, y + h]])
    reach = corners @ normal
    base = float(np.asarray(through) @ normal)
    first = math.ceil((reach.min() - base) / spacing)
    last = math.floor((reach.max() - base) / spacing)
    require(last - first < MAX_GUIDES, "The grid makes too many lines; raise spacing", "resource_limit", field="spacing")
    guides = {}
    for i, k in enumerate(range(first, last + 1), 1):
        p = np.asarray(through, dtype=float) + normal * (k * spacing)
        guides[f"{name}-{prefix}{i}"] = {"kind": "line", "x": round(float(p[0]), 4), "y": round(float(p[1]), 4),
                                         "angle": angle}
    return guides


def generate(op, canvas):
    """Guides for a ``grid`` operation, keyed by name (each tagged with the grid's name)."""
    kind = op.get("kind", "columns")
    require(kind in GRID_KINDS, f"Unknown grid kind {kind!r}; kinds: {', '.join(GRID_KINDS)}", field="kind",
            allowed=list(GRID_KINDS))
    name = op["name"]
    x, y, w, h = _region(op, canvas)
    guides = {}

    def axis(label, which, position):
        guides[f"{name}-{label}"] = {"axis": which, "position": round(float(position), 4)}

    def point(label, px, py):
        guides[f"{name}-{label}"] = {"kind": "point", "x": round(float(px), 4), "y": round(float(py), 4)}

    def line(label, x1, y1, x2, y2):
        guides[f"{name}-{label}"] = {"kind": "segment", "points": [[round(float(x1), 4), round(float(y1), 4)],
                                                                   [round(float(x2), 4), round(float(y2), 4)]]}

    if kind == "columns":
        margin, gutter = op.get("margin", 0), op.get("gutter", 0)
        finite(margin, "margin", 0)
        finite(gutter, "gutter", 0)
        for which, key, start, size in (("x", "columns", x, w), ("y", "rows", y, h)):
            count = op.get(key, 1)
            require(isinstance(count, int) and 1 <= count <= 512, "Grid limit is 512 rows/columns", field=key)
            cell = (size - 2 * margin - (count - 1) * gutter) / count
            require(cell > 0, "Grid margins and gutters exceed canvas", field="margin")
            for i in range(count):
                for edge, offset in (("start", 0), ("end", cell)):
                    guides[f"{name}-{which}{i + 1}-{edge}"] = {"axis": which, "position": start + margin + i * (cell + gutter) + offset}
    elif kind == "baseline":
        spacing = finite(op.get("spacing", 8), "spacing", 1, 1e6)
        top = finite(op.get("offset", 0), "offset", -1e6, 1e6)
        count = int((h - top) // spacing) + 1
        require(count <= 512, "Baseline grid makes more than 512 lines; raise spacing", "resource_limit", field="spacing")
        for i in range(count):
            axis(f"b{i + 1}", "y", y + top + i * spacing)
    elif kind in ("thirds", "golden"):
        fractions = (1 / 3, 2 / 3) if kind == "thirds" else (1 - 1 / PHI, 1 / PHI)
        for i, f in enumerate(fractions, 1):
            axis(f"x{i}", "x", x + w * f)
            axis(f"y{i}", "y", y + h * f)
        for i, fx in enumerate(fractions, 1):
            for j, fy in enumerate(fractions, 1):
                point(f"p{j}{i}", x + w * fx, y + h * fy)
    elif kind == "armature":
        # The harmonic armature: both diagonals, the four reciprocal diagonals (each from a corner,
        # perpendicular to a main diagonal), the centre lines and the rabatment lines.
        line("diagonal", x, y, x + w, y + h)
        line("anti-diagonal", x + w, y, x, y + h)
        # Each reciprocal runs from a corner perpendicular to the diagonal that does not touch it.
        for label, (cx, cy), (dx, dy) in (
            ("reciprocal-1", (x, y), (h, w)), ("reciprocal-2", (x + w, y + h), (-h, -w)),
            ("reciprocal-3", (x + w, y), (-h, w)), ("reciprocal-4", (x, y + h), (h, -w)),
        ):
            visible = _clip_line(cx, cy, dx, dy, (x, y, x + w, y + h), ray=True)
            if visible is not None:
                line(label, *visible[0], *visible[1])
        axis("center-x", "x", x + w / 2)
        axis("center-y", "y", y + h / 2)
        short = min(w, h)
        if w >= h:
            axis("rabatment-left", "x", x + short)
            axis("rabatment-right", "x", x + w - short)
        else:
            axis("rabatment-top", "y", y + short)
            axis("rabatment-bottom", "y", y + h - short)
        point("center", x + w / 2, y + h / 2)
    elif kind == "golden-spiral":
        turns = finite(op.get("turns", 4), "turns", 1, 8)
        corner = op.get("corner", "bottom-right")
        require(corner in ("bottom-right", "bottom-left", "top-right", "top-left"), "corner must be a canvas corner",
                field="corner")
        b = math.log(PHI) / (math.pi / 2)
        theta = np.linspace(-turns * 2 * math.pi, 0, 400)
        r = np.exp(b * theta)
        pts = np.column_stack([r * np.cos(theta), r * np.sin(theta)])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        scale = min(w / (hi[0] - lo[0]), h / (hi[1] - lo[1]))
        pts = (pts - lo) * scale + [x + (w - (hi[0] - lo[0]) * scale) / 2, y + (h - (hi[1] - lo[1]) * scale) / 2]
        if "left" in corner:
            pts[:, 0] = 2 * (x + w / 2) - pts[:, 0]
        if "top" in corner:
            pts[:, 1] = 2 * (y + h / 2) - pts[:, 1]
        eye = pts[0]
        guides[f"{name}-spiral"] = {"kind": "path", "d": "M" + " L".join(f"{px:.2f} {py:.2f}" for px, py in pts)}
        point("eye", *eye)
    elif kind == "polar":
        cx = finite(op.get("x", x + w / 2), "x", -1e9, 1e9)
        cy = finite(op.get("y", y + h / 2), "y", -1e9, 1e9)
        rings = op.get("rings", 4)
        radius = finite(op.get("radius", min(w, h) / 2), "radius", 1, 1e9)
        radii = rings if isinstance(rings, list) else [radius * (i + 1) / rings for i in range(int(rings))]
        require(isinstance(radii, list) and 0 <= len(radii) <= 128, "rings is a count up to 128 or a list of radii", field="rings")
        for i, value in enumerate(radii, 1):
            guides[f"{name}-r{i}"] = {"kind": "circle", "x": cx, "y": cy, "radius": finite(value, "ring radius", 0.001, 1e9)}
        spokes = op.get("spokes", 12)
        require(isinstance(spokes, int) and 0 <= spokes <= 360, "spokes is 0–360", field="spokes")
        start = finite(op.get("angle", -90), "angle", -36000, 36000)
        for i in range(spokes):
            guides[f"{name}-s{i + 1}"] = {"kind": "ray", "x": cx, "y": cy, "angle": round(start + 360 * i / spokes, 6)}
        point("center", cx, cy)
    elif kind in ("isometric", "triangular", "oblique"):
        spacing = finite(op.get("spacing", 40), "spacing", 2, 1e6)
        if kind == "isometric":
            angles = [30.0, 150.0, 90.0]
        elif kind == "triangular":
            angles = [0.0, 60.0, 120.0]
        else:
            angles = op.get("angles", [15.0, 105.0])
            require(isinstance(angles, list) and 1 <= len(angles) <= 4, "angles lists 1–4 line directions", field="angles")
            angles = [finite(a, "angle", -360, 360) for a in angles]
        spacings = op.get("spacings", [spacing] * len(angles))
        require(isinstance(spacings, list) and len(spacings) == len(angles), "spacings needs one value per angle",
                field="spacings")
        # Every family passes through one origin, so the lines meet at lattice points.
        through = (finite(op.get("x", x + w / 2), "x", -1e9, 1e9), finite(op.get("y", y + h / 2), "y", -1e9, 1e9))
        for i, (a, gap) in enumerate(zip(angles, spacings)):
            guides.update(_parallel(name, a, finite(gap, "spacing", 2, 1e6), (x, y, w, h), through, "abcd"[i]))
    elif kind == "hex":
        size = finite(op.get("spacing", 40), "spacing", 4, 1e6)
        dx, dy = size * math.sqrt(3), size * 1.5
        count = 0
        for row in range(int(h // dy) + 2):
            for col in range(int(w // dx) + 2):
                px = x + col * dx + (dx / 2 if row % 2 else 0)
                py = y + row * dy
                if px <= x + w and py <= y + h:
                    count += 1
                    require(count <= 512, "Hex grid makes more than 512 cells; raise spacing", "resource_limit", field="spacing")
                    point(f"c{row + 1}-{col + 1}", px, py)
    else:
        horizon = finite(op.get("horizon", y + h * 0.4), "horizon", -1e9, 1e9)
        points = op.get("vanishing")
        if points is None:
            count = op.get("points", 2)
            require(count in (1, 2, 3), "points is 1, 2 or 3", field="points")
            points = {1: [[x + w / 2, horizon]], 2: [[x - w * 0.25, horizon], [x + w * 1.25, horizon]],
                      3: [[x - w * 0.25, horizon], [x + w * 1.25, horizon], [x + w / 2, y + h * 2.2]]}[count]
        require(isinstance(points, list) and 1 <= len(points) <= 3, "vanishing lists 1–3 [x, y] points", field="vanishing")
        rays = op.get("rays", 16)
        require(isinstance(rays, int) and 2 <= rays <= 120, "rays is 2–120", field="rays")
        axis("horizon", "y", horizon)
        for k, (vx, vy) in enumerate(points, 1):
            finite(vx, "vanishing x", -1e9, 1e9)
            finite(vy, "vanishing y", -1e9, 1e9)
            point(f"vp{k}", vx, vy)
            corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
            if x <= vx <= x + w and y <= vy <= y + h:
                fan = [360 * i / rays for i in range(rays)]
            else:
                # Outside the canvas the corners span less than 180°: fan evenly across them.
                first = math.degrees(math.atan2(corners[0][1] - vy, corners[0][0] - vx))
                spread = [((math.degrees(math.atan2(cy - vy, cx - vx)) - first + 180) % 360) - 180 for cx, cy in corners]
                low, high = min(spread), max(spread)
                fan = [first + low + (high - low) * i / (rays - 1) for i in range(rays)]
            for i, angle in enumerate(fan):
                guides[f"{name}-vp{k}-r{i + 1}"] = {"kind": "ray", "x": vx, "y": vy, "angle": round(angle, 6)}
    for guide in guides.values():
        guide["grid"] = name
    require(len(guides) <= MAX_GUIDES, f"The grid makes more than {MAX_GUIDES} guides", "resource_limit")
    return guides


# ---------------------------------------------------------------------------------------------
# Layer geometry


def _layer_frame(project, target):
    """(layer, resolved layer, local bounds, group matrix, inverse) for a target."""
    from .checks import group_matrix
    from .render import resolve_layout, resolved_layers

    layer = project.layer(target)
    resolved = {item["id"]: item for item in resolved_layers(project)}
    local = resolve_layout(project, layers=list(resolved.values()))
    matrix = group_matrix(resolved[layer["id"]], resolved, local)
    return layer, resolved[layer["id"]], local[layer["id"]], matrix, np.linalg.inv(matrix)


def anchor_points(layer, box, matrix, names=None):
    """Canvas positions of a layer's anchors (corners, edge midpoints, centre) on its rotated box."""
    from .render import rest_size

    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    rw, rh = rest_size(layer)
    a = math.radians(layer.get("rotation", 0))
    co, si = math.cos(a), math.sin(a)
    result = {}
    for name, (fx, fy) in ANCHORS.items():
        if names and name not in names:
            continue
        ux, uy = (fx - 0.5) * rw * (-1 if layer.get("flip_x") else 1), (fy - 0.5) * rh * (-1 if layer.get("flip_y") else 1)
        lx, ly = cx + ux * co - uy * si, cy + ux * si + uy * co
        p = matrix @ [lx, ly, 1]
        result[name] = np.array(p[:2])
    return result


def _anchor(value):
    if value is None:
        return ANCHORS["center"]
    if isinstance(value, str):
        name = canonical_anchor(value)
        require(name, f"anchor must be one of {', '.join(ANCHORS)} or [fx, fy]", field="anchor", allowed=list(ANCHORS))
        return ANCHORS[name]
    require(isinstance(value, list) and len(value) == 2, "anchor must be a name or [fx, fy]", field="anchor")
    return tuple(finite(v, "anchor", -10, 10) for v in value)


def move_anchor_to(project, target, fraction, point, rotation=None):
    """Move (and optionally turn) a layer so its anchor at ``fraction`` of its box lands on the
    canvas ``point``."""
    from .render import rest_size, stored_origin, transformed_size

    layer, resolved, box, matrix, inverse = _layer_frame(project, target)
    group_angle = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
    if rotation is not None:
        layer["rotation"] = (rotation - group_angle) % 360
        if abs(layer["rotation"] - round(layer["rotation"])) < 1e-9:
            layer["rotation"] = round(layer["rotation"]) % 360
    local = inverse @ [point[0], point[1], 1]
    rw, rh = rest_size(layer)
    a = math.radians(layer.get("rotation", 0))
    co, si = math.cos(a), math.sin(a)
    ux = (fraction[0] - 0.5) * rw * (-1 if layer.get("flip_x") else 1)
    uy = (fraction[1] - 0.5) * rh * (-1 if layer.get("flip_y") else 1)
    cx, cy = local[0] - (ux * co - uy * si), local[1] - (ux * si + uy * co)
    tw, th = transformed_size(layer)
    layer["x"], layer["y"] = stored_origin(layer, (cx - tw / 2, cy - th / 2))
    layer["constraints"] = {}


# ---------------------------------------------------------------------------------------------
# Operations


def _guide(project, name, field="guide"):
    guides = project.state.get("guides", {})
    require(isinstance(name, str) and name in guides, f"Unknown guide {name!r}" + (
        f"; guides: {', '.join(list(guides)[:30])}" if guides else "; create one with guide or grid"),
        field=field, allowed=list(guides)[:50])
    return guides[name]


def execute_place(project, op):
    """Put layers on a guide: at a position, distributed along it, or at intersections."""
    targets = op.get("targets") or [op.get("target") or project.state["active_layer"]]
    require(all(targets), "place needs target or targets", field="target")
    require(len(targets) <= 512, "place moves at most 512 layers", field="targets")
    if "within" in op:
        require("guide" not in op, "place takes guide or within, not both", field="within")
        for target in targets:
            place_within(project, target, op["within"], op.get("box", "content"), op.get("anchor"), op.get("margin", 0))
        return
    guide = _guide(project, op.get("guide"))
    canvas = project.state["canvas"]
    fraction = _anchor(op.get("anchor"))
    orient = op.get("orient", "none")
    require(orient in ("none", "tangent", "normal", "radial", "upright"), "orient must be none, tangent, normal, radial or upright",
            field="orient")
    turn = finite(op.get("rotate", 0), "rotate", -3600, 3600)
    offset = finite(op.get("offset", 0), "offset", -1e6, 1e6)
    start = finite(op.get("start", 0), "start", -100, 100)
    end = finite(op.get("end", 1), "end", -100, 100)
    circle_start = finite(op.get("angle", -90), "angle", -36000, 36000)
    spots = []
    if op.get("with"):
        other = _guide(project, op["with"], "with")
        crossings = intersections(guide, other, canvas)
        require(crossings, f"Guides {op['guide']!r} and {op['with']!r} do not cross on the canvas", field="with")
        first = op.get("index", 0)
        require(isinstance(first, int) and 0 <= first < len(crossings),
                f"index must be 0–{len(crossings) - 1}; the guides cross {len(crossings)} time(s)", field="index")
        for k in range(len(targets)):
            spots.append((crossings[(first + k) % len(crossings)], 0.0))
    elif "at" in op and len(targets) == 1:
        spots.append(point_at(guide, canvas, finite(op["at"], "at", -100, 100), circle_start))
    elif "spacing" in op:
        total = guide_length(guide, canvas)
        spacing = finite(op["spacing"], "spacing", 0.01, 1e6)
        base = finite(op.get("at", start), "at", -100, 100)
        for k in range(len(targets)):
            spots.append(point_at(guide, canvas, base + k * spacing / max(total, 1e-9), circle_start))
    else:
        closed = kind_of(guide) == "circle" or (kind_of(guide) == "path" and polyline(guide, canvas)[1])
        n = len(targets)
        for k in range(n):
            if n == 1:
                f = float(op.get("at", (start + end) / 2 if "start" in op or "end" in op else 0.5 if not closed else 0))
            elif closed and start == 0 and end == 1:
                f = k / n
            else:
                f = start + (end - start) * k / (n - 1)
            spots.append(point_at(guide, canvas, f, circle_start))
    for target, (point, tangent) in zip(targets, spots):
        point = np.asarray(point, dtype=float)
        normal = math.radians(tangent + 90)
        if offset:
            point = point + offset * np.array([math.cos(normal), math.sin(normal)])
        rotation = None
        if orient == "tangent":
            rotation = tangent + turn
        elif orient in ("normal", "radial"):
            rotation = tangent + 90 + turn if orient == "normal" else tangent - 90 + turn
        elif orient == "upright":
            rotation = turn
        move_anchor_to(project, target, fraction, point, rotation)


def place_within(project, target, container, box="content", anchor=None, margin=0):
    """Move ``target`` so its ``anchor`` point lands on the same point of ``container``'s content box (or
    whole box), inset by ``margin``: centre text in a bubble's body or pin a label to a badge's corner."""
    from .spatial import canvas_boxes

    require(box in ("bounds", "content"), "box must be bounds or content", field="box")
    other = project.layer(container)
    layer = project.layer(target)
    require(other["id"] != layer["id"], "within must name another layer", field="within")
    content = {}
    boxes = canvas_boxes(project, content=content if box == "content" else None)
    x, y, w, h = content.get(other["id"], boxes[other["id"]])
    margin = finite(margin, "margin", 0, 1e6)
    x, y, w, h = x + margin, y + margin, max(0.0, w - 2 * margin), max(0.0, h - 2 * margin)
    fraction = _anchor(anchor)
    move_anchor_to(project, layer["id"], fraction, np.array([x + fraction[0] * w, y + fraction[1] * h]))


def execute_snap(project, op):
    """Move layers whose anchors are within ``tolerance`` of a guide (or an intersection of two
    guides) exactly onto it; with ``angles``, also straighten near-miss rotations."""
    targets = op.get("targets") or [op.get("target") or project.state["active_layer"]]
    tolerance = finite(op.get("tolerance", 8), "tolerance", 0, 1000)
    angle_tolerance = finite(op.get("angle_tolerance", 4), "angle_tolerance", 0, 45)
    names = op.get("guides") or list(project.state.get("guides", {}))
    require(names, "No guides to snap to; create one with guide or grid", field="guides")
    guides = {name: _guide(project, name, "guides") for name in names}
    wanted = op.get("anchors")
    canvas = project.state["canvas"]
    straight = sorted({a for a in (angle_of(g) for g in guides.values()) if a is not None})
    points = {name: np.array([g["x"], g["y"]]) for name, g in guides.items() if kind_of(g) == "point"}
    if op.get("intersections", True) and len(guides) <= 64:
        keys = [k for k, g in guides.items() if kind_of(g) != "point"]
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                for j, q in enumerate(intersections(guides[a], guides[b], canvas)):
                    points[f"{a}×{b}#{j}"] = q
    for target in targets:
        layer, resolved, box, matrix, _ = _layer_frame(project, target)
        if op.get("angles", True) and straight:
            current = (layer.get("rotation", 0) + math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))) % 180
            best = min(straight, key=lambda a: min(abs(current - a), 180 - abs(current - a)))
            gap = min(abs(current - best), 180 - abs(current - best))
            if 0 < gap <= angle_tolerance:
                layer["rotation"] = (layer.get("rotation", 0) + ((best - current + 90) % 180 - 90)) % 360
                layer, resolved, box, matrix, _ = _layer_frame(project, target)
        anchors = anchor_points(resolved, box, matrix, wanted)
        best = None
        for anchor, q in anchors.items():
            for p in points.values():
                d = float(np.hypot(*(p - q)))
                if d <= tolerance and (best is None or d < best[0] - 1e-9):
                    best = (d, anchor, p)
        if best is None:
            for anchor, q in anchors.items():
                for name, guide in guides.items():
                    if kind_of(guide) == "point":
                        continue
                    p, d, _ = nearest(guide, canvas, q)
                    if d <= tolerance and (best is None or d < best[0] - 1e-9):
                        best = (d, anchor, p)
        if best is not None and best[0] > 1e-6:
            move_anchor_to(project, target, ANCHORS[best[1]], best[2])


def execute(project, op):
    if op["type"] == "place":
        execute_place(project, op)
    else:
        execute_snap(project, op)


def schemas(add):
    from .schema import S, N, B

    refs = {"type": "array", "items": S, "minItems": 1, "maxItems": 512, "uniqueItems": True}
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    anchor = {"anyOf": [{"enum": list(ANCHORS)}, point]}
    add("place", {"targets": refs, "guide": S, "with": S, "index": {"type": "integer", "minimum": 0}, "at": N, "start": N,
                  "end": N, "spacing": N, "angle": N, "anchor": anchor, "orient": {"enum": ["none", "tangent", "normal", "radial", "upright"]},
                  "rotate": N, "offset": N,
                  "within": {**S, "description": "Instead of a guide: a layer to place inside. Each target's anchor "
                             "(default center) lands on the same point of that layer's content box, so text centres "
                             "in a speech bubble's body, a badge or a device screen."},
                  "box": {"enum": ["content", "bounds"], "description": "within: content (default) uses the layer's "
                          "usable inner area (content_bounds in inspect); bounds uses its whole box."},
                  "margin": {**N, "minimum": 0, "description": "within: inset from the box edges in pixels, for "
                             "corner and edge anchors."}},
        anyOf=[{"required": ["guide"]}, {"required": ["within"]}])
    add("snap", {"targets": refs, "guides": {"type": "array", "items": S, "maxItems": 1024}, "tolerance": N,
                 "angle_tolerance": N, "angles": B, "intersections": B,
                 "anchors": {"type": "array", "items": {"enum": list(ANCHORS)}, "minItems": 1}})


# ---------------------------------------------------------------------------------------------
# Checks and overlay


def check_guides(candidate, resolved, local_bounds, projection, layers, issue, tolerance=6.0, angle_tolerance=4.0):
    """Near misses: anchors almost (but not exactly) on a guide or guide point, and rotations
    almost (but not exactly) at a guide's angle."""
    guides = candidate.state.get("guides", {})
    if not guides:
        return
    canvas = candidate.state["canvas"]
    exact = 0.75
    straight = {name: a for name, g in guides.items() if (a := angle_of(g)) is not None}
    for item in layers:
        if item["type"] in ("group", "adjustment"):
            continue
        matrix = projection["matrices"][item["id"]]
        anchors = anchor_points(item, local_bounds[item["id"]], matrix)
        near = None
        on_guides = set()
        for name, guide in guides.items():
            for anchor, q in anchors.items():
                if kind_of(guide) == "point":
                    p = np.array([guide["x"], guide["y"]])
                    d = float(np.hypot(*(p - q)))
                else:
                    p, d, _ = nearest(guide, canvas, q)
                if d <= exact:
                    on_guides.add(name)
                elif d <= tolerance and (near is None or d < near[0]):
                    near = (d, name, anchor, p - q)
        if near and near[1] not in on_guides:
            d, name, anchor, delta = near
            issue("guides", "warning", f"{item['name']!r} {anchor} is {d:.1f} px off guide {name!r}; move it by "
                  f"({delta[0]:.1f}, {delta[1]:.1f}) or snap it", [item], guide=name, anchor=anchor,
                  distance=round(d, 2), move=[round(float(delta[0]), 2), round(float(delta[1]), 2)])
        rotation = (item.get("rotation", 0) + math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))) % 180
        if rotation and straight:
            name, angle = min(straight.items(), key=lambda kv: min(abs(rotation - kv[1]), 180 - abs(rotation - kv[1])))
            gap = min(abs(rotation - angle), 180 - abs(rotation - angle))
            if 0.25 < gap <= angle_tolerance:
                issue("guides", "warning", f"{item['name']!r} is turned {rotation:.1f}°, {gap:.1f}° off guide {name!r} "
                      f"({angle:.1f}°)", [item], guide=name, rotation=round(rotation, 2), guide_angle=round(angle, 2))


def check_alignment(candidate, resolved, local_bounds, projection, layers, issue, tolerance=3.0, angle_tolerance=3.0):
    """Layers almost aligned with each other: edges or centres a few pixels apart, or rotations a
    few degrees apart. Exact alignment and clearly different positions are fine."""
    items = [item for item in layers if item["type"] not in ("group", "adjustment")][:200]
    bounds = projection["bounds"]
    reported = set()
    for i, a in enumerate(items):
        ax, ay, aw, ah = bounds[a["id"]]
        for b in items[i + 1:]:
            if a.get("parent") != b.get("parent"):
                continue
            bx, by, bw, bh = bounds[b["id"]]
            pairs = (("left", ax, bx), ("right", ax + aw, bx + bw), ("center-x", ax + aw / 2, bx + bw / 2),
                     ("top", ay, by), ("bottom", ay + ah, by + bh), ("center-y", ay + ah / 2, by + bh / 2))
            for edge, va, vb in pairs:
                d = abs(va - vb)
                if 0.75 < d <= tolerance and (a["id"], b["id"], edge[-1]) not in reported:
                    reported.add((a["id"], b["id"], edge[-1]))
                    issue("alignment", "warning", f"{a['name']!r} and {b['name']!r} {edge} edges are {d:g} px apart; "
                          "align them exactly or offset them clearly", [a, b], edge=edge, distance=round(d, 2))
                    break
            ra, rb = a.get("rotation", 0) % 180, b.get("rotation", 0) % 180
            if ra or rb:
                gap = min(abs(ra - rb), 180 - abs(ra - rb))
                if 0.25 < gap <= angle_tolerance:
                    issue("alignment", "warning", f"{a['name']!r} ({ra:.1f}°) and {b['name']!r} ({rb:.1f}°) are almost "
                          "parallel; use the same angle", [a, b], angles=[round(ra, 2), round(rb, 2)])


def draw_overlay(image, project, scale=1.0, offset=(0, 0), names=None, labels=True):
    """Draw guides over a rendered image (in place). ``scale``/``offset`` map canvas pixels to the
    image (for previews and zoomed regions)."""
    from PIL import ImageDraw

    guides = project.state.get("guides", {})
    if names:
        guides = {k: v for k, v in guides.items() if k in names or v.get("grid") in names}
    draw = ImageDraw.Draw(image, "RGBA")
    canvas = project.state["canvas"]
    color = (0, 190, 255, 200)
    accent = (255, 60, 160, 230)

    def to_image(q):
        return ((q[0] - offset[0]) * scale, (q[1] - offset[1]) * scale)

    for name, guide in guides.items():
        kind = kind_of(guide)
        if kind == "point":
            x, y = to_image((guide["x"], guide["y"]))
            draw.line((x - 6, y, x + 6, y), fill=accent, width=1)
            draw.line((x, y - 6, x, y + 6), fill=accent, width=1)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=accent)
        elif kind == "circle":
            x, y = to_image((guide["x"], guide["y"]))
            r = guide["radius"] * scale
            draw.ellipse((x - r, y - r, x + r, y + r), outline=color)
        else:
            try:
                points, closed = polyline(guide, canvas)
            except VixlError:
                continue
            xy = [to_image(q) for q in points]
            if closed:
                xy.append(xy[0])
            draw.line(xy, fill=color, width=1)
        if labels and not guide.get("grid"):
            anchor = (guide.get("x", guide.get("position", 0)), guide.get("y", guide.get("position", 0)))
            if kind == "axis":
                anchor = (guide["position"], 2) if guide["axis"] == "x" else (2, guide["position"])
            elif kind == "segment":
                anchor = guide["points"][0]
            elif kind == "path":
                anchor = polyline(guide, canvas)[0][0]
            x, y = to_image(anchor)
            draw.text((x + 3, y + 2), name, fill=accent)
    return image


def describe(project):
    """Guides and grids with a short summary of each, for inspection."""
    guides = project.state.get("guides", {})
    grids = project.state.get("grids", {})
    loose = {k: v for k, v in guides.items() if not v.get("grid")}
    return {
        "guides": loose,
        "grids": {name: {**record, "guides": sum(1 for g in guides.values() if g.get("grid") == name)}
                  for name, record in grids.items()},
        "count": len(guides),
        "kinds": sorted({kind_of(g) for g in guides.values()}),
    }


def resolve_constraint(guide, anchor, ref):
    """The coordinate a constraint anchor reads from a guide: axis guides, horizontal or vertical
    lines, points (their x or y) and circles (their centre or extent)."""
    kind = kind_of(guide)
    horizontal = anchor in ("left", "right", "center-x")
    if kind == "axis":
        require(guide["axis"] == ("x" if horizontal else "y"), "Guide axis does not match constraint")
        return guide["position"]
    if kind in ("point", "circle"):
        value = guide["x"] if horizontal else guide["y"]
        if kind == "circle" and anchor in ("left", "top"):
            value -= guide["radius"]
        elif kind == "circle" and anchor in ("right", "bottom"):
            value += guide["radius"]
        return value
    if kind in ("line", "ray"):
        angle = guide["angle"] % 180
        if horizontal and abs(angle - 90) < 1e-9:
            return guide["x"]
        if not horizontal and abs(angle) < 1e-9:
            return guide["y"]
    raise VixlError("invalid_constraint", f"{ref} is an angled {kind} guide; constraints follow axis guides, points and "
                    "circles. Use place to put layers on angled guides", field="constraints")


def transform_guide(guide, scale=1.0, dx=0.0, dy=0.0):
    """Scale a guide about the origin and then move it (previews, artboard viewports)."""
    kind = kind_of(guide)
    if kind == "axis":
        guide["position"] = guide["position"] * scale - (dx if guide["axis"] == "x" else dy)
    elif kind == "segment":
        guide["points"] = [[px * scale - dx, py * scale - dy] for px, py in guide["points"]]
    elif kind == "path":
        from .geometry import parse_path

        parts = []
        for command, values in parse_path(guide["d"]):
            moved = [v * scale - (dx if i % 2 == 0 else dy) for i, v in enumerate(values)]
            parts.append(command + " ".join(f"{v:.4f}" for v in moved))
        guide["d"] = " ".join(parts)
    else:
        guide["x"], guide["y"] = guide["x"] * scale - dx, guide["y"] * scale - dy
        if kind == "circle":
            guide["radius"] = guide["radius"] * scale
    return guide


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog=f"vixl {cmd}")
    p.add_argument("targets", nargs="+")
    if cmd == "place":
        p.add_argument("--guide", required=True)
        p.add_argument("--with", dest="with_")
        p.add_argument("--index", type=int)
        for key in ("at", "start", "end", "spacing", "angle", "rotate", "offset"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--anchor", choices=list(ANCHORS))
        p.add_argument("--orient", choices=["none", "tangent", "normal", "radial", "upright"])
    else:
        p.add_argument("--guides", nargs="+")
        p.add_argument("--tolerance", type=float)
        p.add_argument("--angle-tolerance", type=float)
        p.add_argument("--no-angles", dest="angles", action="store_false", default=None)
        p.add_argument("--anchors", nargs="+", choices=list(ANCHORS))
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if "with_" in data:
        data["with"] = data.pop("with_")
    targets = data.pop("targets")
    return {"type": cmd, **({"target": targets[0]} if len(targets) == 1 else {"targets": targets}), **data}
