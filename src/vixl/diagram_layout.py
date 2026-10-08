"""Graph layout and connector routing for diagrams: pure geometry, no document access.

``layout(nodes, edges, groups, options)`` places every box and routes every connector:

``layered``  Sugiyama-style flowcharts and dependency graphs. Cycles are broken by reversing back
             edges; nodes get layers (longest path, then balanced); long edges get dummy nodes;
             layer order minimises crossings (barycentre sweeps, adjacent swaps); coordinates come
             from weighted isotonic regression per layer; every gap between layers holds the
             connectors' runs on tracks ordered to avoid crossings. Swimlanes keep each lane in its
             own band, clusters keep group members together.
``tree``     org charts and hierarchies: a contour-packed tidy tree (one or several roots).
``radial``   a tree on concentric rings, angles shared in proportion to subtree size.
``mindmap``  two balanced horizontal trees growing left and right from the root.
``grid``     rows and columns in input order, connectors found by an obstacle-avoiding router.

Everything is deterministic: no set is iterated, nothing is random, ties keep input order.
Connectors are ``Route`` objects (line and cubic segments) that start and end on node borders.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import heapq
import math

import numpy as np

from .geometry import bezier_points

EPS = 1e-6
NORMALS = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
ALGORITHMS = ("layered", "tree", "radial", "mindmap", "grid")
DIRECTIONS = ("TB", "LR", "BT", "RL")
ROUTINGS = ("orthogonal", "curved", "straight")
EXIT = {"TB": "bottom", "BT": "top", "LR": "right", "RL": "left"}


@dataclass
class LNode:
    id: str
    w: float
    h: float
    shape: str = "rect"  # rect, capsule, diamond, ellipse, parallelogram, cylinder
    inset: float = 0.0  # corner radius (rect) or skew (parallelogram): attachments stay clear of it
    group: str = None
    x: float = 0.0
    y: float = 0.0

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def box(self):
        return (self.x, self.y, self.w, self.h)


@dataclass
class LEdge:
    id: str
    src: str
    dst: str
    label: tuple = None  # (width, height) of the label box, when labelled
    from_port: str = None  # top, right, bottom or left
    to_port: str = None


@dataclass
class LGroup:
    id: str
    title: tuple = (0.0, 0.0)  # (width, height) of the title text
    parent: str = None
    lane: bool = False


@dataclass
class Options:
    algorithm: str = "layered"
    direction: str = "TB"
    routing: str = "orthogonal"
    node_gap: float = 40.0  # between neighbours in a layer or level
    rank_gap: float = 64.0  # minimum between layers or levels
    edge_gap: float = 14.0  # between parallel connector tracks and dummy nodes
    arrow: float = 12.0  # arrowhead length: the run into a target keeps room for it
    pad: float = 16.0  # group padding
    lanes: bool = False
    columns: int = None
    aspect: float = 1.6  # target width / height, used to pick grid columns
    loop: float = 26.0  # how far a self loop sticks out
    scale: float = 1.0


@dataclass
class Route:
    segments: list  # ("L", p0, p1) or ("C", p0, c1, c2, p1), chained
    label: tuple = None  # centre of the label box
    reversed: bool = False

    @property
    def start(self):
        return self.segments[0][1]

    @property
    def end(self):
        return self.segments[-1][-1]


@dataclass
class Result:
    nodes: dict = field(default_factory=dict)  # id -> (x, y, w, h)
    edges: dict = field(default_factory=dict)  # id -> Route
    groups: dict = field(default_factory=dict)  # id -> (x, y, w, h, title_x, title_y)
    size: tuple = (0.0, 0.0)
    crossings: int = 0  # edge crossings counted on the final geometry
    reversed: list = field(default_factory=list)  # ids of edges drawn against their direction
    header: float = 0.0  # lane header thickness (along the layers)
    notes: list = field(default_factory=list)


def _polygon(node):
    x, y, w, h = node.x, node.y, node.w, node.h
    if node.shape == "diamond":
        return [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
    if node.shape == "parallelogram":
        k = min(node.inset, w / 2)
        return [(x + k, y), (x + w, y), (x + w - k, y + h), (x, y + h)]
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def side_point(node, side, offset=0.0):
    """The point on ``side`` of a node, ``offset`` px along it from the side's centre."""
    x, y, w, h = node.x, node.y, node.w, node.h
    if node.shape == "parallelogram" and side in ("left", "right"):
        k = min(node.inset, w / 2) / 2
        return (x + k, y + h / 2) if side == "left" else (x + w - k, y + h / 2)
    if side == "top":
        return (x + w / 2 + offset, y)
    if side == "bottom":
        return (x + w / 2 + offset, y + h)
    if side == "left":
        return (x, y + h / 2 + offset)
    return (x + w, y + h / 2 + offset)


def attach_limit(node, side):
    """How far from a side's centre a connector may attach (0 where the side is a single point)."""
    if node.shape in ("diamond", "ellipse", "cylinder"):
        return 0.0
    if node.shape == "capsule":
        return max(0.0, node.w / 2 - node.h / 2) if side in ("top", "bottom") else 0.0
    if node.shape == "parallelogram":
        return max(0.0, node.w / 2 - node.inset) if side in ("top", "bottom") else 0.0
    length = node.w if side in ("top", "bottom") else node.h
    return max(0.0, length / 2 - min(node.inset, length / 4) - 2)


def spread(count, limit, pitch):
    """``count`` attachment offsets centred on a side, at most ``pitch`` apart and within ±limit."""
    if count <= 1 or limit <= 0:
        return [0.0] * count
    step = min(pitch, 2 * limit / (count - 1))
    return [float(round((i - (count - 1) / 2) * step)) for i in range(count)]


def ray_border(node, target):
    """Where the line from the node's centre toward ``target`` leaves the node."""
    cx, cy = node.cx, node.cy
    dx, dy = target[0] - cx, target[1] - cy
    if abs(dx) < EPS and abs(dy) < EPS:
        dx, dy = 0.0, 1.0
    hw, hh = max(node.w / 2, EPS), max(node.h / 2, EPS)
    if node.shape == "ellipse":
        t = 1 / math.hypot(dx / hw, dy / hh)
    elif node.shape == "diamond":
        t = 1 / (abs(dx) / hw + abs(dy) / hh)
    elif node.shape == "parallelogram":
        t = _polygon_ray(_polygon(node), (cx, cy), (dx, dy))
    else:
        t = min(hw / abs(dx) if abs(dx) > EPS else math.inf, hh / abs(dy) if abs(dy) > EPS else math.inf)
    return (cx + dx * t, cy + dy * t)


def _polygon_ray(points, origin, direction):
    best = math.inf
    for p, q in zip(points, points[1:] + points[:1]):
        ex, ey = q[0] - p[0], q[1] - p[1]
        denom = direction[0] * ey - direction[1] * ex
        if abs(denom) < EPS:
            continue
        t = ((p[0] - origin[0]) * ey - (p[1] - origin[1]) * ex) / denom
        u = ((p[0] - origin[0]) * direction[1] - (p[1] - origin[1]) * direction[0]) / denom
        if t > 0 and -EPS <= u <= 1 + EPS:
            best = min(best, t)
    return best


def border_distance(node, point):
    """How far ``point`` is from the node's outline (0 when it lies on the border)."""
    if node.shape == "ellipse":
        hw, hh = node.w / 2, node.h / 2
        dx, dy = point[0] - node.cx, point[1] - node.cy
        return abs(math.hypot(dx / hw, dy / hh) - 1) * min(hw, hh)
    points = _polygon(node)
    return min(_segment_distance(point, p, q) for p, q in zip(points, points[1:] + points[:1]))


def _segment_distance(point, p, q):
    ex, ey = q[0] - p[0], q[1] - p[1]
    length = ex * ex + ey * ey
    t = 0.0 if length < EPS else max(0.0, min(1.0, ((point[0] - p[0]) * ex + (point[1] - p[1]) * ey) / length))
    return math.hypot(point[0] - (p[0] + t * ex), point[1] - (p[1] + t * ey))


def polyline(points):
    """Line segments through ``points``; repeated points and collinear middles are dropped."""
    cleaned = []
    for p in points:
        if not cleaned or math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) > 1e-3:
            cleaned.append((float(p[0]), float(p[1])))
    simple = []
    for p in cleaned:
        while len(simple) >= 2 and _collinear(simple[-2], simple[-1], p):
            simple.pop()
        simple.append(p)
    if len(simple) < 2:
        base = cleaned[0] if cleaned else (0.0, 0.0)
        simple = [base, (base[0] + 0.01, base[1])]
    return [("L", a, b) for a, b in zip(simple, simple[1:])]


def _collinear(a, b, c):
    cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    if abs(cross) > 1e-3:
        return False
    # Only drop b when the path keeps going the same way (not a reversal).
    return (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) > 0


def reverse_segments(segments):
    result = []
    for segment in reversed(segments):
        if segment[0] == "L":
            result.append(("L", segment[2], segment[1]))
        else:
            _, p0, c1, c2, p1 = segment
            result.append(("C", p1, c2, c1, p0))
    return result


def reverse_route(route):
    return Route(reverse_segments(route.segments), route.label, not route.reversed)


def _unit(dx, dy):
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length > EPS else (0.0, 0.0)


def start_direction(segments):
    segment = segments[0]
    if segment[0] == "L":
        return _unit(segment[2][0] - segment[1][0], segment[2][1] - segment[1][1])
    _, p0, c1, c2, p1 = segment
    for q in (c1, c2, p1):
        direction = _unit(q[0] - p0[0], q[1] - p0[1])
        if direction != (0.0, 0.0):
            return direction
    return (0.0, 0.0)


def end_direction(segments):
    segment = segments[-1]
    if segment[0] == "L":
        return _unit(segment[2][0] - segment[1][0], segment[2][1] - segment[1][1])
    _, p0, c1, c2, p1 = segment
    for q in (c2, c1, p0):
        direction = _unit(p1[0] - q[0], p1[1] - q[1])
        if direction != (0.0, 0.0):
            return direction
    return (0.0, 0.0)


def curve_points(controls, ts):
    """Points of a cubic segment's curve at ``ts`` as (x, y) tuples (geometry.bezier_points)."""
    return [tuple(point) for point in bezier_points(controls, ts).tolist()]


def split_bezier(p0, c1, c2, p1, t):
    def lerp(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    a, b, c = lerp(p0, c1), lerp(c1, c2), lerp(c2, p1)
    d, e = lerp(a, b), lerp(b, c)
    f = lerp(d, e)
    return ("C", p0, a, d, f), ("C", f, e, c, p1)


def flatten(segments, steps=24):
    """Points along a chain of segments (curves sampled)."""
    points = [segments[0][1]]
    for segment in segments:
        if segment[0] == "L":
            points.append(segment[2])
        else:
            _, p0, c1, c2, p1 = segment
            points.extend(curve_points((p0, c1, c2, p1), [i / steps for i in range(1, steps + 1)]))
    return points


def route_length(segments):
    points = flatten(segments)
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def point_at_fraction(segments, fraction=0.5):
    """The point a given fraction of the way along a chain of segments (by length)."""
    points = flatten(segments)
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    goal = sum(lengths) * fraction
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if goal <= length + EPS:
            t = 0.0 if length < EPS else goal / length
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        goal -= length
    return points[-1]


def trim_end(segments, length):
    """The chain with ``length`` px removed from its end, and the unit direction it ended in."""
    segments = list(segments)
    direction = end_direction(segments)
    while length > EPS and segments:
        segment = segments[-1]
        size = route_length([segment])
        if size <= length + EPS:
            segments.pop()
            length -= size
            continue
        if segment[0] == "L":
            _, p0, p1 = segment
            t = 1 - length / size
            segments[-1] = ("L", p0, (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
        else:
            _, p0, c1, c2, p1 = segment
            lo, hi = 0.0, 1.0
            for _ in range(24):
                mid = (lo + hi) / 2
                if route_length([split_bezier(p0, c1, c2, p1, mid)[1]]) > length:
                    lo = mid
                else:
                    hi = mid
            segments[-1] = split_bezier(p0, c1, c2, p1, (lo + hi) / 2)[0]
        length = 0.0
    return segments, direction


def inside_node(node, point, margin=0.0):
    """Whether ``point`` lies inside the node's outline, at least ``margin`` px from its border."""
    x, y = point
    if node.shape == "ellipse":
        inside = ((x - node.cx) / max(node.w / 2, EPS)) ** 2 + ((y - node.cy) / max(node.h / 2, EPS)) ** 2 < 1
    else:
        inside = False
        poly = _polygon(node)
        for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
            if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
                inside = not inside
    return inside and border_distance(node, point) > margin


def route_hits_node(segments, node, margin=1.0, step=3.0):
    """Whether a chain of segments runs through the inside of a node (touching its border is fine)."""
    points = flatten(segments, 24)
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        count = max(1, int(length / step))
        for i in range(count + 1):
            t = i / count
            if inside_node(node, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), margin):
                return True
    return False


def _inside(point, rect):
    return rect[0] < point[0] < rect[0] + rect[2] and rect[1] < point[1] < rect[1] + rect[3]


def route_hits_rect(segments, rect, margin=0.0):
    """Whether any part of the chain passes through the interior of ``rect`` (shrunk by ``margin``)."""
    rect = (rect[0] + margin, rect[1] + margin, rect[2] - 2 * margin, rect[3] - 2 * margin)
    if rect[2] <= 0 or rect[3] <= 0:
        return False
    for segment in segments:
        if any(kind == "drop" for kind, _ in _cut_segment(segment, rect)):
            return True
    return False


def cut_rect(segments, rect):
    """Chains of segments left after removing the parts that lie inside ``rect`` (x, y, w, h)."""
    chains, current = [], []
    for segment in segments:
        for kind, piece in _cut_segment(segment, rect):
            if kind == "keep":
                current.append(piece)
            elif current:
                chains.append(current)
                current = []
    if current:
        chains.append(current)
    return chains


def _cut_segment(segment, rect):
    """[("keep" | "drop", segment)] pieces of one segment against a rectangle."""
    x0, y0, w, h = rect
    if segment[0] == "L":
        _, p, q = segment
        t0, t1 = 0.0, 1.0
        for delta, lo, hi, start in ((q[0] - p[0], x0, x0 + w, p[0]), (q[1] - p[1], y0, y0 + h, p[1])):
            if abs(delta) < EPS:
                if not lo < start < hi:
                    return [("keep", segment)]
                continue
            a, b = (lo - start) / delta, (hi - start) / delta
            t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 >= t1 - 1e-9:
            return [("keep", segment)]

        def at(t):
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

        pieces = []
        if t0 > 1e-9:
            pieces.append(("keep", ("L", p, at(t0))))
        pieces.append(("drop", ("L", at(t0), at(t1))))
        if t1 < 1 - 1e-9:
            pieces.append(("keep", ("L", at(t1), q)))
        return pieces
    _, p0, c1, c2, p1 = segment
    samples = curve_points((p0, c1, c2, p1), [i / 64 for i in range(65)])
    inside = [i for i, s in enumerate(samples) if _inside(s, rect)]
    if not inside:
        return [("keep", segment)]
    # Refine where the curve enters and leaves by bisection.
    a, b = max(0, inside[0] - 1) / 64, inside[0] / 64
    for _ in range(22):
        m = (a + b) / 2
        a, b = (m, b) if not _inside(curve_points((p0, c1, c2, p1), [m])[0], rect) else (a, m)
    t_in = b
    a, b = inside[-1] / 64, min(64, inside[-1] + 1) / 64
    for _ in range(22):
        m = (a + b) / 2
        a, b = (a, m) if not _inside(curve_points((p0, c1, c2, p1), [m])[0], rect) else (m, b)
    t_out = a
    pieces = []
    head, rest = split_bezier(p0, c1, c2, p1, t_in)
    if t_in > 1e-9:
        pieces.append(("keep", head))
    scale = (t_out - t_in) / (1 - t_in) if t_in < 1 else 1.0
    middle, tail = split_bezier(*rest[1:], scale)
    pieces.append(("drop", middle))
    if t_out < 1 - 1e-9:
        pieces.append(("keep", tail))
    return pieces


def dash_chain(segments, dash, gap):
    """A chain cut into dashes (polylines) that start and end on a full dash."""
    points = flatten(segments)
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= dash + EPS:
        return [segments]
    periods = max(1, round((total + gap) / (dash + gap)))
    unit = (total + gap) / periods
    dash_len = unit - gap

    def locate(distance):
        offset = 0.0
        for i, length in enumerate(lengths):
            if distance <= offset + length + EPS or i == len(lengths) - 1:
                t = 0.0 if length < EPS else min(1.0, max(0.0, (distance - offset) / length))
                a, b = points[i], points[i + 1]
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), i
            offset += length
        return points[-1], len(lengths) - 1

    chains = []
    for k in range(periods):
        first, i0 = locate(k * unit)
        last, i1 = locate(k * unit + dash_len)
        run = [first, *points[i0 + 1:i1 + 1], last]
        chains.append(polyline(run))
    return chains


def _segments_cross(a, b, c, d):
    """Whether open segments a-b and c-d cross at an interior point."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = orient(a, b, c), orient(a, b, d)
    d3, d4 = orient(c, d, a), orient(c, d, b)
    return d1 * d2 < -EPS and d3 * d4 < -EPS


def overlap_length(a, b, tolerance=1.5):
    """How far two straight segments run along each other (collinear within ``tolerance`` px)."""
    (p, q), (r, t) = a, b
    length = math.hypot(q[0] - p[0], q[1] - p[1])
    if length < EPS or math.hypot(t[0] - r[0], t[1] - r[1]) < EPS:
        return 0.0
    ux, uy = (q[0] - p[0]) / length, (q[1] - p[1]) / length
    if any(abs((c[0] - p[0]) * uy - (c[1] - p[1]) * ux) > tolerance for c in (r, t)):
        return 0.0
    s0, s1 = sorted(((c[0] - p[0]) * ux + (c[1] - p[1]) * uy) for c in (r, t))
    return max(0.0, min(length, s1) - max(0.0, s0))


def count_crossings(routes):
    """How many pairs of connectors cross (shared endpoints and touching runs do not count)."""
    flat = []
    for key, route in routes.items():
        if route is None:
            continue
        points = flatten(route.segments, 12)
        flat.append((key, list(zip(points, points[1:]))))
    total = 0
    for i, (ka, sa) in enumerate(flat):
        for kb, sb in flat[i + 1:]:
            hit = False
            for a, b in sa:
                for c, d in sb:
                    if _segments_cross(a, b, c, d):
                        hit = True
                        break
                if hit:
                    break
            total += hit
    return total


class Router:
    """Right-angled routing on the compressed grid of obstacle edges (A*, bend and overlap penalties)."""

    def __init__(self, obstacles, bounds, clearance, points, bend=40.0):
        self.bend = bend
        inflated = [(x - clearance, y - clearance, x + w + clearance, y + h + clearance) for x, y, w, h in obstacles]
        xs = {bounds[0], bounds[2]}
        ys = {bounds[1], bounds[3]}
        for x0, y0, x1, y1 in inflated:
            xs.update((x0, x1))
            ys.update((y0, y1))
        for x, y in points:
            xs.add(x)
            ys.add(y)
        self.xs = sorted({round(v, 3) for v in xs})
        self.ys = sorted({round(v, 3) for v in ys})
        self.xi = {v: i for i, v in enumerate(self.xs)}
        self.yi = {v: i for i, v in enumerate(self.ys)}
        nx, ny = len(self.xs), len(self.ys)
        self.hblock = np.zeros((max(nx - 1, 1), ny), dtype=bool)  # segment [i, i+1] along row j
        self.vblock = np.zeros((nx, max(ny - 1, 1)), dtype=bool)  # segment [j, j+1] along column i
        for x0, y0, x1, y1 in inflated:
            i0, i1 = self.xi[round(x0, 3)], self.xi[round(x1, 3)]
            j0, j1 = self.yi[round(y0, 3)], self.yi[round(y1, 3)]
            self.hblock[i0:i1, j0 + 1:j1] = True
            self.vblock[i0 + 1:i1, j0:j1] = True
        self.used = defaultdict(int)

    def route(self, start, end, start_dir=None, end_dir=None):
        """Grid points of the cheapest axis-parallel path from ``start`` to ``end`` (None if blocked)."""
        s = (self.xi[round(start[0], 3)], self.yi[round(start[1], 3)])
        t = (self.xi[round(end[0], 3)], self.yi[round(end[1], 3)])
        if s == t:
            return [start]
        dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))

        def nearest(vector):
            return None if vector is None else min(range(4), key=lambda k: abs(dirs[k][0] - vector[0]) + abs(dirs[k][1] - vector[1]))

        first, last = nearest(start_dir), nearest(end_dir)
        xs, ys = self.xs, self.ys
        initial = -1 if first is None else first
        best = {(s, initial): 0.0}
        parent = {}
        queue = [(0.0, 0.0, 0, s, initial)]
        counter = 0
        goal = None
        while queue:
            _, g, _, node, d = heapq.heappop(queue)
            if best.get((node, d), math.inf) < g - 1e-9:
                continue
            if node == t and (last is None or d == last):
                goal = (node, d)
                break
            i, j = node
            for k, (dx, dy) in enumerate(dirs):
                ni, nj = i + dx, j + dy
                if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                    continue
                if dx:
                    if self.hblock[min(i, ni), j]:
                        continue
                    key = ("h", min(i, ni), j)
                else:
                    if self.vblock[i, min(j, nj)]:
                        continue
                    key = ("v", i, min(j, nj))
                cost = abs(xs[ni] - xs[i]) + abs(ys[nj] - ys[j]) + 18.0 * self.used.get(key, 0)
                if d not in (-1, k):
                    if d == (k + 2) % 4:
                        continue  # no U-turns
                    cost += self.bend
                ng = g + cost
                state = ((ni, nj), k)
                if ng < best.get(state, math.inf) - 1e-9:
                    best[state] = ng
                    parent[state] = (node, d)
                    counter += 1
                    h = abs(xs[ni] - xs[t[0]]) + abs(ys[nj] - ys[t[1]])
                    heapq.heappush(queue, (ng + h, ng, counter, (ni, nj), k))
        if goal is None:
            return None
        cells, state = [], goal
        while True:
            cells.append(state[0])
            if state not in parent:
                break
            state = parent[state]
        cells.reverse()
        for (i, j), (ni, nj) in zip(cells, cells[1:]):
            if j == nj:
                self.used[("h", min(i, ni), j)] += 1
            else:
                self.used[("v", i, min(j, nj))] += 1
        return [(xs[i], ys[j]) for i, j in cells]


def _port_side(node, other, port):
    """The side of ``node`` a connector toward ``other`` leaves from: the port, else the facing side."""
    if port in NORMALS:
        return port
    dx, dy = other.cx - node.cx, other.cy - node.cy
    if abs(dx) / max(node.w / 2 + other.w / 2, EPS) > abs(dy) / max(node.h / 2 + other.h / 2, EPS):
        return "right" if dx > 0 else "left"
    return "bottom" if dy > 0 else "top"


def _stub(point, side, length):
    nx, ny = NORMALS[side]
    return (point[0] + nx * length, point[1] + ny * length)


def straight_route(a, b, edge, spread_a=0.0, spread_b=0.0):
    p = side_point(a, edge.from_port, spread_a) if edge.from_port in NORMALS else ray_border(a, (b.cx, b.cy))
    q = side_point(b, edge.to_port, spread_b) if edge.to_port in NORMALS else ray_border(b, (a.cx, a.cy))
    if edge.from_port in NORMALS and edge.to_port not in NORMALS:
        q = ray_border(b, p)
    if edge.to_port in NORMALS and edge.from_port not in NORMALS:
        p = ray_border(a, q)
    return polyline([p, q])


def curved_route(a, b, edge, spread_a=0.0, spread_b=0.0, sides=None):
    """A cubic curve between node borders, leaving and arriving along the sides' normals."""
    if sides is not None and edge.from_port not in NORMALS:
        side_a = sides[0]
    else:
        side_a = _port_side(a, b, edge.from_port)
    if sides is not None and edge.to_port not in NORMALS:
        side_b = sides[1]
    else:
        side_b = _port_side(b, a, edge.to_port)
    p, q = side_point(a, side_a, spread_a), side_point(b, side_b, spread_b)
    k = max(24.0, math.hypot(q[0] - p[0], q[1] - p[1]) * 0.45)
    n0, n1 = NORMALS[side_a], NORMALS[side_b]
    return [("C", p, (p[0] + n0[0] * k, p[1] + n0[1] * k), (q[0] + n1[0] * k, q[1] + n1[1] * k), q)]


def rank_curves(points, flow):
    """One S-shaped cubic per hop, leaving and arriving along the flow direction. The curve between two
    anchors never leaves the box they span, so it stays clear of whatever the straight hop clears."""
    segments = []
    points = [p for i, p in enumerate(points) if i == 0 or math.hypot(p[0] - points[i - 1][0], p[1] - points[i - 1][1]) > 1e-3]
    for p, q in zip(points, points[1:]):
        k = max(14.0, abs((q[0] - p[0]) * flow[0] + (q[1] - p[1]) * flow[1]) * 0.5)
        segments.append(("C", p, (p[0] + flow[0] * k, p[1] + flow[1] * k), (q[0] - flow[0] * k, q[1] - flow[1] * k), q))
    return segments


def loop_route(node, side, size, curved=False):
    """A self loop leaving and re-entering one side of a node, and where its label goes."""
    if side in ("left", "right"):
        sign = 1 if side == "right" else -1
        x = side_point(node, side)[0]
        span = min(node.h * 0.5, 36.0)
        y1, y2 = node.cy - span / 2, node.cy + span / 2
        if curved:
            return [("C", (x, y1), (x + sign * size * 1.6, y1 - span * 0.2), (x + sign * size * 1.6, y2 + span * 0.2), (x, y2))]
        return polyline([(x, y1), (x + sign * size, y1), (x + sign * size, y2), (x, y2)])
    sign = 1 if side == "bottom" else -1
    y = side_point(node, side)[1]
    span = min(node.w * 0.5, 36.0)
    x1, x2 = node.cx - span / 2, node.cx + span / 2
    if curved:
        return [("C", (x1, y), (x1 - span * 0.2, y + sign * size * 1.6), (x2 + span * 0.2, y + sign * size * 1.6), (x2, y))]
    return polyline([(x1, y), (x1, y + sign * size), (x2, y + sign * size), (x2, y)])


def _loop(node, edge, side, o):
    segments = loop_route(node, side, o.loop, o.routing == "curved")
    label = None
    if edge.label:
        if side in ("left", "right"):
            sign = 1 if side == "right" else -1
            label = (side_point(node, side)[0] + sign * (o.loop + 6 + edge.label[0] / 2), node.cy)
        else:
            sign = 1 if side == "bottom" else -1
            label = (node.cx, side_point(node, side)[1] + sign * (o.loop + 6 + edge.label[1] / 2))
    return Route(segments, label)


class _Dummy:
    """A point a long connector passes through in a layer."""

    def __init__(self, ident, lane):
        self.id, self.lane = ident, lane
        self.a = self.r = 0.0


def _break_cycles(ids, edges):
    """DAG edges (upper, lower, edge index): back edges found by depth-first search are reversed."""
    out = defaultdict(list)
    indegree = defaultdict(int)
    for index, e in enumerate(edges):
        out[e.src].append((e.dst, index))
        indegree[e.dst] += 1
    state = {i: 0 for i in ids}
    flipped = {}
    for root in [i for i in ids if indegree[i] == 0] + list(ids):
        if state[root]:
            continue
        state[root] = 1
        stack = [(root, iter(out[root]))]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child, index in children:
                if state[child] == 1:
                    flipped[index] = True
                elif state[child] == 0:
                    state[child] = 1
                    stack.append((child, iter(out[child])))
                    advanced = True
                    break
            if not advanced:
                state[node] = 2
                stack.pop()
    return [((e.dst, e.src, i) if i in flipped else (e.src, e.dst, i)) for i, e in enumerate(edges)], list(flipped)


def _layering(ids, dag):
    """Longest-path layers, then balanced: a node with more in- than out-edges moves up (and vice versa)."""
    preds, succs = defaultdict(list), defaultdict(list)
    for a, b, _ in dag:
        preds[b].append(a)
        succs[a].append(b)
    indegree = {i: len(preds[i]) for i in ids}
    ready = [i for i in ids if indegree[i] == 0]
    rank = {i: 0 for i in ids}
    head = 0
    while head < len(ready):
        v = ready[head]
        head += 1
        for w in succs[v]:
            rank[w] = max(rank[w], rank[v] + 1)
            indegree[w] -= 1
            if indegree[w] == 0:
                ready.append(w)
    topo = ready
    for _ in range(4):
        moved = False
        for v in reversed(topo):
            lo = max((rank[u] + 1 for u in preds[v]), default=None)
            hi = min((rank[w] - 1 for w in succs[v]), default=None)
            ins, outs = len(preds[v]), len(succs[v])
            if ins == 0 and outs:
                target = hi
            elif outs == 0 and ins:
                target = lo
            elif ins > outs and lo is not None:
                target = lo
            elif outs > ins and hi is not None:
                target = hi
            else:
                continue
            if lo is not None:
                target = max(target, lo)
            if hi is not None:
                target = min(target, hi)
            if target != rank[v]:
                rank[v], moved = target, True
        if not moved:
            break
    remap = {r: i for i, r in enumerate(sorted(set(rank.values())))}
    return {i: remap[r] for i, r in rank.items()}


def _inversions(pairs):
    """Number of crossing pairs among (upper position, lower position) segments."""
    pairs = sorted(pairs)
    values = sorted({b for _, b in pairs})
    index = {v: i + 1 for i, v in enumerate(values)}
    tree = [0] * (len(values) + 2)
    crossings = seen = i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        for _, b in pairs[i:j]:
            k, below = index[b], 0
            while k > 0:
                below += tree[k]
                k -= k & -k
            crossings += seen - below
        for _, b in pairs[i:j]:
            k = index[b]
            while k < len(tree):
                tree[k] += 1
                k += k & -k
            seen += 1
        i = j
    return crossings


def _isotonic(targets, weights):
    """Weighted least-squares fit of a nondecreasing sequence (pool adjacent violators)."""
    blocks = []
    for t, w in zip(targets, weights):
        blocks.append([t * w, w, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1] - 1e-12:
            top = blocks.pop()
            blocks[-1][0] += top[0]
            blocks[-1][1] += top[1]
            blocks[-1][2] += top[2]
    result = []
    for total, weight, count in blocks:
        result.extend([total / weight] * count)
    return result


class _Layered:
    def __init__(self, nodes, edges, groups, o):
        self.nodes, self.edges, self.groups, self.o = nodes, edges, groups, o
        self.horizontal = o.direction in ("LR", "RL")
        self.flip = o.direction in ("BT", "RL")
        self.exit_side = EXIT[o.direction]
        self.entry_side = OPPOSITE[self.exit_side]

    # Sizes in the abstract frame: ``a`` runs across the layers, ``r`` along them.
    def sa(self, n):
        return n.h if self.horizontal else n.w

    def sr(self, n):
        return n.w if self.horizontal else n.h

    def xy(self, a, r):
        return (r, a) if self.horizontal else (a, r)

    def lane(self, v):
        if not self.o.lanes:
            return 0
        if v in self.dummies:
            return self.dummies[v].lane
        return self.lane_index.get(self.nodes[v].group, len(self.lane_ids) - 1)

    def cluster(self, v):
        return self.nodes[v].group if not self.o.lanes and v in self.nodes and self.nodes[v].group in self.groups else None

    def run(self):
        o, nodes = self.o, self.nodes
        ids = list(nodes)
        real = [e for e in self.edges if e.src != e.dst]
        loops = [e for e in self.edges if e.src == e.dst]
        self.real = real
        dag, flipped = _break_cycles(ids, real)
        rank = _layering(ids, dag)
        self.reversed = [real[i].id for i in flipped]
        self.dummies = {}
        self.lane_ids, self.lane_index = [], {}
        if o.lanes:
            self.lane_ids = [g.id for g in self.groups.values() if g.lane]
            if any(n.group not in self.lane_ids for n in nodes.values()):
                self.lane_ids.append("")
            self.lane_index = {g: i for i, g in enumerate(self.lane_ids)}
        layers = [[] for _ in range(max(rank.values(), default=0) + 1)]
        for i in ids:
            layers[rank[i]].append(i)
        self.hops, self.chain, self.rank = [], {}, dict(rank)
        for a, b, index in dag:
            span = rank[b] - rank[a]
            chain = [a]
            for k in range(1, span):
                ident = f"~{real[index].id}~{k}"
                near = nodes[a] if k <= span / 2 else nodes[b]
                lane = self.lane_index.get(near.group, len(self.lane_ids) - 1) if o.lanes else 0
                self.dummies[ident] = _Dummy(ident, lane)
                layers[rank[a] + k].append(ident)
                self.rank[ident] = rank[a] + k
                chain.append(ident)
            chain.append(b)
            self.chain[index] = chain
            self.hops += [(index, u, v) for u, v in zip(chain, chain[1:])]
        self.layers = layers
        self.up, self.down = defaultdict(list), defaultdict(list)
        for _, u, v in self.hops:
            self.down[u].append(v)
            self.up[v].append(u)
        self.order_layers()
        self.assign_across(loops)
        self.assign_along()
        return self.build(loops)

    def order_layers(self):
        layers, up, down = self.layers, self.up, self.down

        def crossings():
            total = 0
            for r in range(len(layers) - 1):
                lower = {v: i for i, v in enumerate(layers[r + 1])}
                total += _inversions([(i, lower[w]) for i, u in enumerate(layers[r]) for w in down[u]])
            return total

        def sweep(downward):
            for r in (range(1, len(layers)) if downward else range(len(layers) - 2, -1, -1)):
                ref = layers[r - 1] if downward else layers[r + 1]
                position = {v: i for i, v in enumerate(ref)}
                neighbours = up if downward else down
                scored = []
                for i, v in enumerate(layers[r]):
                    ns = sorted(position[n] for n in neighbours[v])
                    if ns:
                        mid = len(ns) // 2
                        median = ns[mid] if len(ns) % 2 else (ns[mid - 1] + ns[mid]) / 2
                        bary = (2 * median + sum(ns) / len(ns)) / 3
                    else:
                        bary = float(i)
                    scored.append((v, bary, i))
                blocks = defaultdict(list)
                for v, bary, _ in scored:
                    if self.cluster(v):
                        blocks[self.cluster(v)].append(bary)
                layers[r] = [
                    v for v, bary, i in sorted(scored, key=lambda s: (
                        self.lane(s[0]),
                        sum(blocks[self.cluster(s[0])]) / len(blocks[self.cluster(s[0])]) if self.cluster(s[0]) else s[1],
                        self.cluster(s[0]) or "", s[1], s[2]))
                ]

        def transpose():
            for _ in range(6):
                improved = False
                for r, layer in enumerate(layers):
                    for i in range(len(layer) - 1):
                        u, v = layer[i], layer[i + 1]
                        if self.lane(u) != self.lane(v) or self.cluster(u) != self.cluster(v):
                            continue
                        keep = swap = 0
                        for ref_r, neighbours in ((r - 1, up), (r + 1, down)):
                            if 0 <= ref_r < len(layers):
                                position = {w: j for j, w in enumerate(layers[ref_r])}
                                for a in neighbours[u]:
                                    for b in neighbours[v]:
                                        keep += position[a] > position[b]
                                        swap += position[a] < position[b]
                        if swap < keep:
                            layer[i], layer[i + 1] = v, u
                            improved = True
                if not improved:
                    break

        if self.o.lanes or any(self.cluster(v) for layer in layers for v in layer):
            for layer in layers:  # start with members grouped
                layer.sort(key=lambda v: (self.lane(v), self.cluster(v) or ""))
        best, best_count = [list(layer) for layer in layers], crossings()
        stale = 0
        for iteration in range(28):
            if best_count == 0:
                break
            sweep(iteration % 2 == 0)
            if iteration % 4 == 3:
                transpose()
            count = crossings()
            if count < best_count:
                best, best_count, stale = [list(layer) for layer in layers], count, 0
            else:
                stale += 1
                if stale >= 8:
                    break
        self.layers = layers = [list(layer) for layer in best]
        transpose()
        count = crossings()
        if count > best_count:
            self.layers = best

    def size_a(self, v):
        if v in self.nodes:
            return self.sa(self.nodes[v]) + 2 * self.loop_extra.get(v, 0.0)
        return self.o.edge_gap * 0.5

    def separation(self, u, v):
        both = u in self.nodes and v in self.nodes
        pad = (self.label_pad.get(u, 0.0) + self.label_pad.get(v, 0.0)) / 2
        return (self.size_a(u) + self.size_a(v)) / 2 + (self.o.node_gap if both else self.o.edge_gap) + pad

    def assign_across(self, loops):
        o, layers = self.o, self.layers
        self.loop_extra = {}
        # Branches with labels (a decision's yes/no) need runs long enough to hold their labels.
        self.label_pad = {}
        labelled = defaultdict(list)
        for index, chain in self.chain.items():
            if self.real[index].label:
                labelled[chain[0]].append((chain[1], self.real[index].label))
        for source, items in labelled.items():
            if len(items) > 1:
                for target, label in items:
                    across = label[1] if self.horizontal else label[0]
                    self.label_pad[target] = max(self.label_pad.get(target, 0.0), across + 14 * o.scale)
        for e in loops:
            extra = o.loop * 0.5 + ((e.label[1] if self.horizontal else e.label[0]) * 0.5 if e.label else 0.0)
            self.loop_extra[e.src] = max(self.loop_extra.get(e.src, 0.0), extra)
        position, bounds = {}, {}
        bands = self.lane_bands() if o.lanes else None
        for layer in layers:
            cursor = 0.0
            for i, v in enumerate(layer):
                if i:
                    cursor += self.separation(layer[i - 1], v)
                position[v] = cursor
        if bands:
            for layer in layers:
                for v in layer:
                    lo, hi = bands[self.lane(v)]
                    half = self.size_a(v) / 2
                    bounds[v] = (lo + o.pad + half, max(lo + o.pad + half, hi - o.pad - half))
                    position[v] = min(max(position[v], bounds[v][0]), bounds[v][1])
        offsets = {}
        for layer in layers:
            total = 0.0
            for i, v in enumerate(layer):
                if i:
                    total += self.separation(layer[i - 1], v)
                offsets[v] = total

        spine = self.spine_edges()
        hop_weight = {}
        for index, u, v in self.hops:
            w = 6.0 if (u in self.dummies and v in self.dummies) else 2.0 if (u in self.dummies or v in self.dummies) else 1.0
            w *= 3.0 if index in spine else 1.0
            for key in ((u, v), (v, u)):
                hop_weight[key] = max(hop_weight.get(key, 0.0), w)

        def weight(u, v):
            return hop_weight[(u, v)]

        def solve(layer, desired, weights):
            fit = _isotonic([desired[v] - offsets[v] for v in layer], weights)
            if bands:
                lows = [bounds[v][0] - offsets[v] for v in layer]
                highs = [bounds[v][1] - offsets[v] for v in layer]
                running = -math.inf
                for i in range(len(fit)):  # bounds are monotone, so clipping the fit is exact
                    running = max(running, lows[i])
                    fit[i] = max(fit[i], running)
                running = math.inf
                for i in range(len(fit) - 1, -1, -1):
                    running = min(running, highs[i])
                    fit[i] = min(fit[i], max(running, lows[i]))
            for v, q in zip(layer, fit):
                position[v] = q + offsets[v]

        def sweep(downward, both=False):
            for r in (range(len(layers)) if downward else range(len(layers) - 1, -1, -1)):
                layer = layers[r]
                desired, weights = {}, []
                for v in layer:
                    ns = []
                    if both or downward:
                        ns += [(position[n], weight(v, n)) for n in self.up[v]]
                    if both or not downward:
                        ns += [(position[n], weight(v, n)) for n in self.down[v]]
                    total = sum(w for _, w in ns)
                    desired[v] = sum(p * w for p, w in ns) / total if ns else position[v]
                    weights.append(total if ns else 0.05)
                solve(layer, desired, weights)

        for _ in range(8):
            sweep(True)
            sweep(False)
        sweep(True, both=True)
        sweep(False, both=True)
        self.straighten(position, bounds)
        sweep(True, both=True)
        self.straighten(position, bounds)
        low = 0.0 if bands else min((position[v] - self.size_a(v) / 2 for v in position), default=0.0)
        self.across = {v: float(round(p - low)) for v, p in position.items()}
        for r, layer in enumerate(layers):  # rounding must not squeeze neighbours together
            for i in range(1, len(layer)):
                need = self.across[layer[i - 1]] + self.separation(layer[i - 1], layer[i])
                if self.across[layer[i]] < need - 0.01:
                    self.across[layer[i]] = float(math.ceil(need - 0.01))
        if bands:
            self.band_edges = bands

    def spine_edges(self):
        """Indexes of the edges on the longest path through the graph: they are kept straight."""
        best, via = {}, {}
        for index, u, v in sorted(self.hops, key=lambda h: self.rank[h[1]]):
            if u in self.dummies or v in self.dummies:
                continue
            length = best.get(u, 0) + 1
            if length > best.get(v, 0):
                best[v], via[v] = length, (u, index)
        spine, node = set(), max(best, key=lambda k: (best[k], -self.rank[k]), default=None)
        while node in via:
            node, index = via[node][0], via[node][1]
            spine.add(index)
        return spine

    def straighten(self, position, bounds):
        """Put each long connector's dummies on one line wherever the neighbours leave room."""
        for chain in self.chain.values():
            inner = chain[1:-1]
            if len(inner) < 2:
                continue
            lo, hi = -math.inf, math.inf
            for d in inner:
                layer = self.layers[self.rank[d]]
                i = layer.index(d)
                if i:
                    lo = max(lo, position[layer[i - 1]] + self.separation(layer[i - 1], d))
                if i < len(layer) - 1:
                    hi = min(hi, position[layer[i + 1]] - self.separation(d, layer[i + 1]))
                if d in bounds:
                    lo, hi = max(lo, bounds[d][0]), min(hi, bounds[d][1])
            if lo <= hi + 1e-9:
                values = sorted(position[d] for d in inner)
                target = values[len(values) // 2]
                for d in inner:
                    position[d] = min(max(target, lo), hi)

    def lane_bands(self):
        widths = [0.0] * len(self.lane_ids)
        for layer in self.layers:
            totals, last = defaultdict(float), {}
            for v in layer:
                lane = self.lane(v)
                totals[lane] += self.separation(last[lane], v) if lane in last else self.size_a(v) / 2
                last[lane] = v
            for lane in totals:
                widths[lane] = max(widths[lane], totals[lane] + self.size_a(last[lane]) / 2)
        bands, cursor = [], 0.0
        for lane, width in enumerate(widths):
            group = self.groups.get(self.lane_ids[lane])
            title = group.title[1 if self.horizontal else 0] if group else 0.0
            width = max(width + 2 * self.o.pad, 2 * self.o.pad + self.o.node_gap, title + 2 * self.o.pad)
            bands.append((cursor, cursor + width))
            cursor += width
        return bands

    # Coordinates along the layers: one track per horizontal run in each gap.
    def attach_offsets(self):
        """Offsets along the node sides at both ends of every hop, spread so connectors do not merge."""
        out_slots, in_slots = defaultdict(list), defaultdict(list)
        for index, u, v in self.hops:
            out_slots[u].append((self.across[v], index, v))
            in_slots[v].append((self.across[u], index, u))
        pitch = max(12.0, self.o.edge_gap)
        offsets = {}
        for node, slots in out_slots.items():
            slots.sort()
            values = spread(len(slots), attach_limit(self.nodes[node], self.exit_side), pitch) if node in self.nodes else [0.0] * len(slots)
            for (_, index, v), off in zip(slots, values):
                offsets[("out", index, node, v)] = off
        for node, slots in in_slots.items():
            slots.sort()
            values = spread(len(slots), attach_limit(self.nodes[node], self.entry_side), pitch) if node in self.nodes else [0.0] * len(slots)
            for (_, index, u), off in zip(slots, values):
                offsets[("in", index, u, node)] = off
        return offsets

    def assign_along(self):
        o = self.o
        self.offsets = self.attach_offsets()
        self.tracks, gaps = {}, []
        self.header = 0.0
        if o.lanes and self.lane_ids:
            title = max((self.groups[g].title[0 if self.horizontal else 1] for g in self.lane_ids if g in self.groups), default=0.0)
            self.header = title + 2 * o.pad * 0.6 if title else 0.0
        for r in range(len(self.layers) - 1):
            items, max_label = [], 0.0
            for index, u, v in self.hops:
                if self.rank[u] != r:
                    continue
                a1 = self.across[u] + self.offsets[("out", index, u, v)]
                a2 = self.across[v] + self.offsets[("in", index, u, v)]
                label = self.real[index].label if self.chain[index][0] == u else None
                lab_a = lab_r = 0.0
                if label:
                    lab_a, lab_r = (label[1], label[0]) if self.horizontal else label
                    max_label = max(max_label, lab_r)
                if abs(a1 - a2) < 0.5 and not label:
                    continue
                mid = (a1 + a2) / 2
                items.append(((index, u, v), a1, a2, (min(a1, a2, mid - lab_a / 2), max(a1, a2, mid + lab_a / 2))))
            tracks = self.assign_tracks(items)
            count = max(tracks.values(), default=-1) + 1
            pitch = max(o.edge_gap * 0.8, max_label + 10 * o.scale if max_label else 0.0)
            pad_top, pad_bottom = 14 * o.scale, o.arrow + 10 * o.scale
            gap = max(o.rank_gap, pad_top + pad_bottom + max(count, 1) * pitch)
            block = pad_top + (gap - pad_top - pad_bottom - count * pitch) / 2
            gaps.append((gap, block, pitch, count))
            for key, track in tracks.items():
                self.tracks[key] = (r, track)
        self.gaps = gaps
        thick = [max((self.sr(self.nodes[v]) for v in layer if v in self.nodes), default=0.0) for layer in self.layers]
        edge_pad = o.pad if o.lanes else 0.0  # breathing room at both ends of a lane
        top, cursor = [], self.header + edge_pad
        for r, t in enumerate(thick):
            top.append(cursor)
            cursor += t + (gaps[r][0] if r < len(gaps) else 0.0)
        self.layer_top, self.thick, self.extent_r = top, thick, cursor + edge_pad

    @staticmethod
    def assign_tracks(items):
        """Track numbers for the horizontal runs in one gap, ordered so runs do not cross verticals."""
        keys = [it[0] for it in items]
        span = {it[0]: it[3] for it in items}
        a1 = {it[0]: it[1] for it in items}
        a2 = {it[0]: it[2] for it in items}
        below = defaultdict(list)  # key -> keys that must sit further from the upper layer

        def reaches(start, goal):
            stack, seen = [start], {start: True}
            while stack:
                n = stack.pop()
                if n == goal:
                    return True
                for m in below[n]:
                    if m not in seen:
                        seen[m] = True
                        stack.append(m)
            return False

        def add(x, y):
            if x != y and y not in below[x] and not reaches(y, x):
                below[x].append(y)

        margin = 3.0
        for e in keys:
            for f in keys:
                if e == f:
                    continue
                lo, hi = span[f]
                if lo + margin < a1[e] < hi - margin:
                    add(e, f)  # e comes down at a1 into f's run unless e's own run is above f's
                if lo + margin < a2[e] < hi - margin:
                    add(f, e)  # e rises to its run at a2 unless f's run is above e's
        for i, e in enumerate(keys):
            for f in keys[i + 1:]:
                if span[e][0] < span[f][1] - margin and span[f][0] < span[e][1] - margin and e not in below[f] and f not in below[e]:
                    first, second = (e, f) if (span[e][0], a1[e]) <= (span[f][0], a1[f]) else (f, e)
                    add(first, second)
        depth, indegree = {k: 0 for k in keys}, {k: 0 for k in keys}
        for k in keys:
            for m in below[k]:
                indegree[m] += 1
        ready, head = [k for k in keys if indegree[k] == 0], 0
        while head < len(ready):
            k = ready[head]
            head += 1
            for m in below[k]:
                depth[m] = max(depth[m], depth[k] + 1)
                indegree[m] -= 1
                if indegree[m] == 0:
                    ready.append(m)
        return depth

    def build(self, loops):
        o, nodes = self.o, self.nodes
        R = self.extent_r

        def rr(r):  # abstract r to the final coordinate along the layers
            return R - r if self.flip else r

        for r, layer in enumerate(self.layers):
            centre = self.layer_top[r] + self.thick[r] / 2
            for v in layer:
                if v in nodes:
                    n = nodes[v]
                    cx, cy = self.xy(self.across[v], rr(centre))
                    n.x, n.y = float(round(cx - n.w / 2)), float(round(cy - n.h / 2))
                else:
                    self.dummies[v].a, self.dummies[v].r = self.across[v], rr(centre)
        result = Result(reversed=self.reversed, header=self.header)
        pending = []
        for index, e in enumerate(self.real):
            chain = self.chain[index]
            if e.from_port in NORMALS or e.to_port in NORMALS:
                pending.append(e)
                continue
            route = self.route(index, e, chain, rr)
            result.edges[e.id] = reverse_route(route) if e.id in self.reversed else route
        for e in loops:
            result.edges[e.id] = _loop(nodes[e.src], e, "bottom" if self.horizontal else "right", o)
        for v, n in nodes.items():
            result.nodes[v] = n.box()
        if o.lanes:
            result.groups.update(self.lane_boxes())
        # ports named on a layered edge are the router's business
        result.pending = pending
        return result

    def route(self, index, e, chain, rr):
        o, nodes = self.o, self.nodes
        first, last = nodes[chain[0]], nodes[chain[-1]]
        p0 = side_point(first, self.exit_side, self.offsets[("out", index, chain[0], chain[1])])
        p1 = side_point(last, self.entry_side, self.offsets[("in", index, chain[-2], chain[-1])])
        inner = []
        for d in chain[1:-1]:  # straight through the layer, so the curve or diagonal never cuts a neighbour's corner
            r = self.rank[d]
            inner += [self.xy(self.across[d], rr(self.layer_top[r])), self.xy(self.across[d], rr(self.layer_top[r] + self.thick[r]))]
        label_at = None
        if o.routing == "straight":
            segments = polyline([p0, *inner, p1])
            return Route(segments, point_at_fraction(segments) if e.label else None)
        if o.routing == "curved":
            segments = rank_curves([p0, *inner, p1], NORMALS[self.exit_side])
            return Route(segments, point_at_fraction(segments) if e.label else None)
        points = [p0]
        for hop, (u, v) in enumerate(zip(chain, chain[1:])):
            start = p0 if hop == 0 else self.xy(self.dummies[u].a, self.dummies[u].r)
            end = p1 if hop == len(chain) - 2 else self.xy(self.dummies[v].a, self.dummies[v].r)
            track = self.tracks.get((index, u, v))
            if track is not None:
                gap_r, number = track
                _, block, pitch, _ = self.gaps[gap_r]
                t = rr(self.layer_top[gap_r] + self.thick[gap_r] + block + (number + 0.5) * pitch)
                a_pt, b_pt = ((t, start[1]), (t, end[1])) if self.horizontal else ((start[0], t), (end[0], t))
                points += [a_pt, b_pt]
                if hop == 0 and e.label:
                    label_at = ((a_pt[0] + b_pt[0]) / 2, (a_pt[1] + b_pt[1]) / 2)
            points.append(end)
        return Route(polyline(points), label_at)

    def lane_boxes(self):
        boxes = {}
        extent = self.extent_r
        for g in self.lane_ids:
            if g in self.groups:
                lo, hi = self.band_edges[self.lane_index[g]]
                boxes[g] = (0.0, lo, extent, hi - lo, 0.0, lo) if self.horizontal else (lo, 0.0, hi - lo, extent, lo, 0.0)
        return boxes


def _forest(ids, edges):
    """(parent map, children map, roots, edges left over) of a breadth-first spanning forest."""
    out = defaultdict(list)
    incoming = defaultdict(int)
    for e in edges:
        if e.src != e.dst:
            out[e.src].append(e)
            incoming[e.dst] += 1
    parent, children, seen, used = {}, defaultdict(list), {}, {}
    roots = []
    for root in [i for i in ids if incoming[i] == 0] + list(ids):
        if root in seen:
            continue
        roots.append(root)
        seen[root] = True
        queue, head = [root], 0
        while head < len(queue):
            v = queue[head]
            head += 1
            for e in out[v]:
                if e.dst not in seen:
                    seen[e.dst] = True
                    parent[e.dst] = v
                    children[v].append(e.dst)
                    used[e.id] = True
                    queue.append(e.dst)
    return parent, children, roots, [e for e in edges if e.id not in used]


def _tidy(children, roots, size_a, gap):
    """Centres across the levels of every node: subtrees packed against each other by their contours."""
    virtual = "~forest"
    kids_of = dict(children)
    kids_of[virtual] = list(roots)
    sizes = dict(size_a)
    sizes[virtual] = 0.0
    contour, offset = {}, {}

    def place(v):
        kids = kids_of.get(v, [])
        for k in kids:
            place(k)
        half = sizes[v] / 2
        if not kids:
            contour[v] = ([-half], [half])
            return
        lefts, rights, positions = [], [], []
        for i, k in enumerate(kids):
            left, right = contour[k]
            shift = 0.0
            if i:
                shift = max(rights[d] + gap - left[d] for d in range(min(len(rights), len(left))))
            positions.append(shift)
            for d, value in enumerate(left):
                if d >= len(lefts):
                    lefts.append(value + shift)
            for d, value in enumerate(right):
                if d < len(rights):
                    rights[d] = value + shift
                else:
                    rights.append(value + shift)
        centre = (positions[0] + positions[-1]) / 2
        for k, p in zip(kids, positions):
            offset[k] = p - centre
        contour[v] = ([-half] + [x - centre for x in lefts], [half] + [x - centre for x in rights])

    place(virtual)
    absolute = {virtual: 0.0}
    stack = [virtual]
    while stack:
        v = stack.pop()
        for k in kids_of.get(v, []):
            absolute[k] = absolute[v] + offset[k]
            stack.append(k)
    absolute.pop(virtual)
    return absolute


class _Tree:
    def __init__(self, nodes, edges, o):
        self.nodes, self.edges, self.o = nodes, edges, o
        self.horizontal = o.direction in ("LR", "RL")
        self.flip = o.direction in ("BT", "RL")
        self.exit_side = EXIT[o.direction]
        self.entry_side = OPPOSITE[self.exit_side]

    def sa(self, n):
        return n.h if self.horizontal else n.w

    def sr(self, n):
        return n.w if self.horizontal else n.h

    def run(self):
        o, nodes = self.o, self.nodes
        ids = list(nodes)
        self.parent, self.children, self.roots, self.extra = _forest(ids, self.edges)
        size_a = {v: self.sa(nodes[v]) for v in ids}
        a_pos = _tidy(self.children, self.roots, size_a, o.node_gap)
        depth = {}
        stack = [(r, 0) for r in reversed(self.roots)]
        while stack:
            v, d = stack.pop()
            depth[v] = d
            stack += [(k, d + 1) for k in reversed(self.children.get(v, []))]
        levels = max(depth.values(), default=0) + 1
        thick = [0.0] * levels
        for v in ids:
            thick[depth[v]] = max(thick[depth[v]], self.sr(nodes[v]))
        label_r = [0.0] * levels
        self.tree_edges = {}
        for e in self.edges:
            if e.src != e.dst and self.parent.get(e.dst) == e.src and e.id not in self.tree_edges:
                self.tree_edges[e.id] = e
                if e.label:
                    label_r[depth[e.dst]] = max(label_r[depth[e.dst]], e.label[0] if self.horizontal else e.label[1])
        gaps = [max(o.rank_gap, (label_r[d + 1] + 12 * o.scale + o.arrow) / 0.55) if label_r[d + 1] else o.rank_gap
                for d in range(levels - 1)]
        top, cursor = [], 0.0
        for d in range(levels):
            top.append(cursor)
            cursor += thick[d] + (gaps[d] if d < len(gaps) else 0.0)
        low = min((a_pos[v] - size_a[v] / 2 for v in ids), default=0.0)
        for v in ids:
            n = nodes[v]
            a, r = a_pos[v] - low, top[depth[v]] + thick[depth[v]] / 2
            if self.flip:
                r = cursor - r
            cx, cy = (r, a) if self.horizontal else (a, r)
            n.x, n.y = float(round(cx - n.w / 2)), float(round(cy - n.h / 2))
        self.depth, self.top, self.thick, self.gaps, self.extent_r = depth, top, thick, gaps, cursor
        return self

    def routes(self):
        """Routes of the spanning-tree edges (edges with ports and non-tree edges are left to the router)."""
        o, nodes = self.o, self.nodes
        routes = {}
        for e in self.edges:
            if e.id not in self.tree_edges or e.from_port in NORMALS or e.to_port in NORMALS:
                continue
            p, c = nodes[e.src], nodes[e.dst]
            d = self.depth[e.src]
            gap = self.gaps[d] if d < len(self.gaps) else o.rank_gap
            start, end = side_point(p, self.exit_side), side_point(c, self.entry_side)
            if o.routing == "straight":
                routes[e.id] = Route(straight_route(p, c, e), None)
            elif o.routing == "curved":
                segments = curved_route(p, c, e, sides=(self.exit_side, self.entry_side))
                routes[e.id] = Route(segments, point_at_fraction(segments) if e.label else None)
            else:
                bus_r = self.top[d] + self.thick[d] + gap * 0.45
                bus = self.extent_r - bus_r if self.flip else bus_r
                points = [start, (bus, start[1]), (bus, end[1]), end] if self.horizontal else [start, (start[0], bus), (end[0], bus), end]
                label = None
                if e.label:  # on the run into the child, midway
                    label = ((points[2][0] + end[0]) / 2, (points[2][1] + end[1]) / 2)
                routes[e.id] = Route(polyline(points), label)
        return routes


def _leaves(children, v, memo):
    if v not in memo:
        kids = children.get(v, [])
        memo[v] = 1 if not kids else sum(_leaves(children, k, memo) for k in kids)
    return memo[v]


def _place_radial(nodes, edges, o):
    """Places nodes on rings around the root; returns (parent map, depth map)."""
    ids = list(nodes)
    parent, children, roots, _ = _forest(ids, edges)
    children = dict(children)
    virtual = len(roots) > 1
    top = "~root" if virtual else roots[0]
    if virtual:
        children[top] = list(roots)
    depth, order = {top: 0}, [top]
    for v in order:
        for k in children.get(v, []):
            depth[k] = depth[v] + 1
            order.append(k)
    memo = {}
    angle = {top: (0.0, 2 * math.pi)}
    for v in order:
        kids = children.get(v, [])
        if kids:
            lo, hi = angle[v]
            total = sum(_leaves(children, k, memo) for k in kids)
            cursor = lo
            for k in kids:
                share = (hi - lo) * _leaves(children, k, memo) / total
                angle[k] = (cursor, cursor + share)
                cursor += share
    half = {v: math.hypot(nodes[v].w, nodes[v].h) / 2 for v in ids}
    levels = max(depth.values()) + 1
    rings = defaultdict(list)
    for v in ids:
        rings[depth[v]].append(v)
    radius = [0.0] * levels
    gap = o.rank_gap * 0.7
    for d in range(1, levels):
        previous = max((half[v] for v in rings[d - 1]), default=0.0) if not (virtual and d == 1) else 0.0
        floor = radius[d - 1] + previous + gap + max(half[v] for v in rings[d])
        members = sorted(rings[d], key=lambda v: sum(angle[v]))
        needed = floor
        if len(members) > 1:
            for u, v in zip(members, members[1:] + members[:1]):
                between = (sum(angle[v]) - sum(angle[u])) / 2 % (2 * math.pi)
                between = between if between > 1e-6 else 2 * math.pi / len(members)
                needed = max(needed, (half[u] + half[v] + o.node_gap * 0.6) / (2 * math.sin(min(between, math.pi) / 2)))
        elif virtual and d == 1:
            needed = 0.0
        radius[d] = needed
    for v in ids:
        theta = sum(angle[v]) / 2 - math.pi / 2
        n = nodes[v]
        cx, cy = radius[depth[v]] * math.cos(theta), radius[depth[v]] * math.sin(theta)
        n.x, n.y = float(round(cx - n.w / 2)), float(round(cy - n.h / 2))
    return parent, depth, (0.0, 0.0)


def layout(nodes, edges, groups=None, options=None):
    """Place ``nodes`` (LNode list), route ``edges`` (LEdge list) and return a ``Result`` whose
    coordinates start at (0, 0). ``groups`` are LGroup lanes and clusters (members via ``node.group``)."""
    o = options or Options()
    groups = {g.id: g for g in (groups or [])}
    node_map = {n.id: n for n in nodes if n.id not in groups}
    for n in node_map.values():
        if n.group not in groups:
            n.group = None
    edge_list = [e for e in edges if e.src in node_map and e.dst in node_map]
    if groups and not o.lanes and o.algorithm in ("layered", "tree"):
        # Room for cluster boxes and their titles between neighbours and between levels.
        title = max((g.title[1] for g in groups.values()), default=0.0)
        o = Options(**{**o.__dict__, "node_gap": max(o.node_gap, 2 * o.pad + 14), "rank_gap": max(o.rank_gap, 3 * o.pad + title + 12)})
    if o.algorithm == "layered":
        engine = _Layered(node_map, edge_list, groups, o)
        result = engine.run()
        _route_pending(result, node_map, result.pending, o)
    elif o.algorithm == "tree":
        engine = _Tree(node_map, edge_list, o).run()
        result = _tree_result(engine, node_map, edge_list, o)
    elif o.algorithm == "radial":
        result = _radial_result(node_map, edge_list, o)
    elif o.algorithm == "mindmap":
        result = _mindmap_result(node_map, edge_list, o)
    elif o.algorithm == "grid":
        result = _grid_result(node_map, edge_list, o)
    else:
        raise ValueError(f"unknown layout {o.algorithm}")
    _cluster_groups(result, node_map, groups, o)
    return _normalise(result, node_map, edge_list)


def _route_pending(result, nodes, pending, o):
    """Route edges the main pass left to the obstacle-avoiding router (explicit ports, extra edges such as a cycle's
    back edge). They attach beside connectors already on a side, never on top of them, and a straight or curved
    route that would cross another node goes around it instead."""
    if not pending:
        return
    boxes = [n.box() for n in nodes.values()]
    margin = 60.0
    clearance = 8.0 * max(o.scale, 0.5)
    stub = clearance + 2
    sides, slots = {}, defaultdict(list)
    for e in pending:
        a, b = nodes[e.src], nodes[e.dst]
        sides[e.id] = (_port_side(a, b, e.from_port), _port_side(b, a, e.to_port))
        slots[(e.src, sides[e.id][0])].append((e.id, 0))
        slots[(e.dst, sides[e.id][1])].append((e.id, 1))
    ends = [p for route in result.edges.values() if route.segments
            for p in (route.segments[0][1], route.segments[-1][-1])]
    offsets = {}
    for (node_id, side), members in slots.items():
        limit = attach_limit(nodes[node_id], side)
        centre = side_point(nodes[node_id], side)
        taken = limit > 0 and any(math.hypot(p[0] - centre[0], p[1] - centre[1]) < 1.5 for p in ends)
        choices = spread(len(members) + taken, limit, 14.0)
        if taken:
            # A connector of the main pass already attaches at the centre: keep the offsets beside it.
            choices.remove(min(choices, key=abs))
        for member, off in zip(members, choices):
            offsets[member] = off
    anchors = []
    for e in pending:
        for end, node_id in ((0, e.src), (1, e.dst)):
            side = sides[e.id][end]
            anchors.append(_stub(side_point(nodes[node_id], side, offsets[(e.id, end)]), side, stub))
    bounds = (min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin,
              max(b[0] + b[2] for b in boxes) + margin, max(b[1] + b[3] for b in boxes) + margin)
    router = None
    for e in pending:
        a, b = nodes[e.src], nodes[e.dst]
        side_a, side_b = sides[e.id]
        off_a, off_b = offsets[(e.id, 0)], offsets[(e.id, 1)]
        segments = None
        if o.routing == "straight":
            segments = straight_route(a, b, e, off_a, off_b)
        elif o.routing == "curved":
            segments = curved_route(a, b, e, off_a, off_b, sides=(side_a, side_b))
        if segments is not None and any(route_hits_node(segments, n) for n in nodes.values() if n.id not in (e.src, e.dst)):
            segments = None
        if segments is None:
            router = router or Router(boxes, bounds, clearance, anchors)
            start, end = side_point(a, side_a, off_a), side_point(b, side_b, off_b)
            path = router.route(_stub(start, side_a, stub), _stub(end, side_b, stub), NORMALS[side_a],
                                tuple(-v for v in NORMALS[side_b]))
            segments = polyline([start, *path, end]) if path else straight_route(a, b, e, off_a, off_b)
        result.edges[e.id] = Route(segments, _middle(segments) if e.label else None)


def _middle(segments):
    """The middle of the longest segment (a good place for a label)."""
    longest = max(segments, key=lambda s: route_length([s]))
    return point_at_fraction([longest])


def _tree_result(engine, nodes, edges, o):
    result = Result()
    result.edges = engine.routes()
    for v, n in nodes.items():
        result.nodes[v] = n.box()
    side = "bottom" if engine.horizontal else "right"
    for e in edges:
        if e.src == e.dst:
            result.edges[e.id] = _loop(nodes[e.src], e, side, o)
    _route_pending(result, nodes, [e for e in edges if e.src != e.dst and e.id not in result.edges], o)
    return result


def _radial_result(nodes, edges, o):
    parent, depth, _ = _place_radial(nodes, edges, o)
    result = Result()
    for v, n in nodes.items():
        result.nodes[v] = n.box()
    for e in edges:
        a, b = nodes[e.src], nodes[e.dst]
        if e.src == e.dst:
            result.edges[e.id] = _loop(a, e, "right", o)
            continue
        if e.from_port in NORMALS or e.to_port in NORMALS:
            continue
        segments = straight_route(a, b, e)
        if parent.get(e.dst) != e.src and (parent.get(e.src) == e.dst or any(
                route_hits_node(segments, n) for n in nodes.values() if n.id not in (e.src, e.dst))):
            # A back edge (a cycle) would lie on its tree edge or run through nodes: the router takes it around.
            continue
        if o.routing == "curved":
            p, q = segments[0][1], segments[0][2]
            length = math.hypot(q[0] - p[0], q[1] - p[1])
            # Bow away from the root's axis a little, the way spokes of a wheel curve.
            ux, uy = _unit(q[0] - p[0], q[1] - p[1])
            side = 1 if (a.cx * (b.cy - a.cy) - a.cy * (b.cx - a.cx)) >= 0 else -1
            bend = min(0.14 * length, 28.0) * side
            nx, ny = -uy * bend, ux * bend
            segments = [("C", p, (p[0] + (q[0] - p[0]) / 3 + nx, p[1] + (q[1] - p[1]) / 3 + ny),
                         (p[0] + 2 * (q[0] - p[0]) / 3 + nx, p[1] + 2 * (q[1] - p[1]) / 3 + ny), q)]
        result.edges[e.id] = Route(segments, point_at_fraction(segments) if e.label else None)
    _route_pending(result, nodes, [e for e in edges if e.src != e.dst and e.id not in result.edges], o)
    return result


def _transform(route, dx, dy, mirror):
    def move(p):
        return ((-(p[0] + dx) if mirror else p[0] + dx), p[1] + dy)

    segments = [(seg[0], *[move(p) for p in seg[1:]]) for seg in route.segments]
    return Route(segments, move(route.label) if route.label else None)


def _mindmap_result(nodes, edges, o):
    ids = list(nodes)
    result = Result()
    if not ids:
        return result
    parent, children, roots, _ = _forest(ids, edges)
    root = roots[0]
    if len(roots) > 1:
        result.notes.append(f"A mind map has one centre; {', '.join(roots[1:])} are extra roots drawn as branches of {root} without a connector.")
        children = dict(children)
        children[root] = list(children.get(root, [])) + roots[1:]
    memo = {}
    sides = {"right": [], "left": []}
    load = {"right": 0, "left": 0}
    for k in children.get(root, []):
        side = "right" if load["right"] <= load["left"] else "left"
        sides[side].append(k)
        load[side] += _leaves(children, k, memo)
    sub = Options(**{**o.__dict__, "algorithm": "tree", "direction": "LR"})
    routes = {}
    placed = {}
    for side, branch in sides.items():
        if not branch:
            continue
        members, stack = {root: None}, list(branch)
        while stack:
            v = stack.pop()
            members[v] = None
            stack += children.get(v, [])
        copies = {v: LNode(v, nodes[v].w, nodes[v].h, nodes[v].shape, nodes[v].inset) for v in ids if v in members}
        tree_edges = [e for e in edges if e.src in members and e.dst in members and (parent.get(e.dst) == e.src or (e.src == root and e.dst in branch))]
        tree = _Tree(copies, tree_edges, sub).run()
        # The centre is one node: shift each side so its root sits at the origin.
        r = copies[root]
        dx, dy = -r.cx, -r.cy
        for e_id, route in tree.routes().items():
            routes[e_id] = _transform(route, dx, dy, side == "left")
        for v, c in copies.items():
            cx = c.cx + dx
            placed.setdefault(v, (-cx if side == "left" else cx, c.cy + dy))
    for v, n in nodes.items():
        cx, cy = placed.get(v, (0.0, 0.0))
        n.x, n.y = float(round(cx - n.w / 2)), float(round(cy - n.h / 2))
        result.nodes[v] = n.box()
    result.edges = dict(routes)
    # Routes were computed before rounding the mirrored positions; re-anchor them on the final boxes.
    for e in edges:
        if e.src == e.dst:
            result.edges[e.id] = _loop(nodes[e.src], e, "right", o)
    if o.routing != "straight":
        for e in edges:
            if e.id in routes:
                result.edges[e.id] = _reanchor(routes[e.id], nodes[e.src], nodes[e.dst], e, o)
    else:
        for e in edges:
            if e.id in routes:
                result.edges[e.id] = Route(straight_route(nodes[e.src], nodes[e.dst], e), None)
    _route_pending(result, nodes, [e for e in edges if e.src != e.dst and e.id not in result.edges], o)
    return result


def _reanchor(route, a, b, e, o):
    """A mirrored or shifted route, snapped back onto its nodes' final (rounded) borders."""
    p = side_point(a, "right" if b.cx >= a.cx else "left")
    q = side_point(b, "left" if b.cx >= a.cx else "right")
    segments = list(route.segments)
    if segments[0][0] == "L":
        segments[0] = ("L", p, segments[0][2])
    else:
        old = segments[0]
        shift = (p[0] - old[1][0], p[1] - old[1][1])
        segments[0] = ("C", p, (old[2][0] + shift[0], old[2][1] + shift[1]), old[3], old[4])
    if segments[-1][0] == "L":
        segments[-1] = ("L", segments[-1][1], q)
    else:
        old = segments[-1]
        shift = (q[0] - old[4][0], q[1] - old[4][1])
        segments[-1] = ("C", old[1], old[2], (old[3][0] + shift[0], old[3][1] + shift[1]), q)
    if len(segments) > 1 and all(s[0] == "L" for s in segments):
        points = [segments[0][1]] + [s[2] for s in segments]
        # Keep the run orthogonal after snapping.
        if len(points) == 4:
            bus = points[1][0]
            points = [p, (bus, p[1]), (bus, q[1]), q]
        segments = polyline(points)
    return Route(segments, route.label)


def _grid_result(nodes, edges, o):
    ids = list(nodes)
    n = len(ids)
    columns = o.columns or max(1, math.ceil(math.sqrt(n * o.aspect)))
    columns = max(1, min(columns, n))
    cell_w = max((nodes[i].w for i in ids), default=0.0)
    cell_h = max((nodes[i].h for i in ids), default=0.0)
    gap_x, gap_y = o.node_gap * 1.5, o.rank_gap
    for index, i in enumerate(ids):
        row, col = divmod(index, columns)
        node = nodes[i]
        node.x = float(round(col * (cell_w + gap_x) + (cell_w - node.w) / 2))
        node.y = float(round(row * (cell_h + gap_y) + (cell_h - node.h) / 2))
    result = Result()
    for i, node in nodes.items():
        result.nodes[i] = node.box()
    for e in edges:
        if e.src == e.dst:
            result.edges[e.id] = _loop(nodes[e.src], e, "right", o)
    _route_pending(result, nodes, [e for e in edges if e.src != e.dst], o)
    return result


def _cluster_groups(result, nodes, groups, o):
    """Boxes around the members of groups that are not lanes."""
    if not groups:
        return
    members = defaultdict(list)
    for n in nodes.values():
        if n.group in groups:
            members[n.group].append(n)
    done = {}

    def box_of(gid):
        if gid in done:
            return done[gid]
        g = groups[gid]
        if g.lane and gid in result.groups:
            return result.groups[gid][:4]
        rects = [n.box() for n in members.get(gid, [])]
        rects += [box for other in groups.values() if other.parent == gid for box in [box_of(other.id)] if box]
        if not rects:
            return None
        title_h = g.title[1] + 6
        x0, y0 = min(r[0] for r in rects) - o.pad, min(r[1] for r in rects) - o.pad - title_h
        x1, y1 = max(r[0] + r[2] for r in rects) + o.pad, max(r[1] + r[3] for r in rects) + o.pad
        done[gid] = (x0, y0, max(x1 - x0, g.title[0] + 2 * o.pad), y1 - y0)
        return done[gid]

    for gid in groups:
        if groups[gid].lane and gid in result.groups:
            continue
        box = box_of(gid)
        if box:
            result.groups[gid] = (*box, box[0] + o.pad, box[1] + o.pad * 0.6)


def _normalise(result, nodes, edges):
    """Shift everything so the content's top-left corner is the origin; measure it and its crossings."""
    labels = {e.id: e.label for e in edges if e.label}
    xs0, ys0, xs1, ys1 = [], [], [], []

    def add(x0, y0, x1, y1):
        xs0.append(x0)
        ys0.append(y0)
        xs1.append(x1)
        ys1.append(y1)

    for x, y, w, h in result.nodes.values():
        add(x, y, x + w, y + h)
    for g in result.groups.values():
        add(g[0], g[1], g[0] + g[2], g[1] + g[3])
    for key, route in result.edges.items():
        for segment in route.segments:
            for p in (segment[1], segment[-1]):
                add(p[0], p[1], p[0], p[1])
            if segment[0] == "C":
                samples = curve_points(segment[1:], [i / 8 for i in range(9)])
                for p in samples:
                    add(p[0], p[1], p[0], p[1])
        if route.label and key in labels:
            w, h = labels[key]
            add(route.label[0] - w / 2, route.label[1] - h / 2, route.label[0] + w / 2, route.label[1] + h / 2)
    if not xs0:
        return result
    dx, dy = -min(xs0), -min(ys0)
    for v, (x, y, w, h) in list(result.nodes.items()):
        result.nodes[v] = (x + dx, y + dy, w, h)
        nodes[v].x, nodes[v].y = x + dx, y + dy
    result.groups = {g: (x + dx, y + dy, w, h, tx + dx, ty + dy) for g, (x, y, w, h, tx, ty) in result.groups.items()}
    for route in result.edges.values():
        route.segments = [(seg[0], *[(p[0] + dx, p[1] + dy) for p in seg[1:]]) for seg in route.segments]
        if route.label:
            route.label = (route.label[0] + dx, route.label[1] + dy)
    result.size = (max(xs1) + dx, max(ys1) + dy)
    result.crossings = count_crossings(result.edges)
    return result
