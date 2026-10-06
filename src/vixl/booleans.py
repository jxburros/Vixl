"""Boolean operations on Bézier outlines: a pathfinder layer as real path geometry.

Rendered as pixels, a pathfinder layer is a max, a difference or a min of its operands' alpha channels.
SVG, PDF and PowerPoint need a path instead, so this module computes the result exactly. Every
operand outline (lines and cubic Béziers) is split where it crosses another outline; a piece is
kept when the combined shape lies on one side of it and not on the other; the kept pieces are joined
into closed contours with the inside on their left. Curves stay curves, outer contours and holes
wind in opposite directions and never overlap, so nonzero and even-odd fills agree and the result
is one compound path.

Geometry that cannot be combined reliably (coincident curves that only partly overlap, a stroked
or translucent operand, thousands of segments) raises ``Unsupported`` with the reason; callers draw the
layer as an image then and list it as a raster fallback.
"""

import math
from collections import defaultdict

KAPPA = 0.5522847498307936
TOLERANCE = 1.5e-3  # points closer than this are one point (a thousandth of a pixel is invisible)
MAX_SEGMENTS = 1200
SUBDIVISION_LIMIT = 6000  # box tests allowed when intersecting one pair of curves
CONTACT = 1e-3  # curves this close touch (a tangent, or a corner that only grazes)


class Unsupported(Exception):
    """The layer's boolean cannot be expressed as path geometry; the message says why."""


# A line segment is (p0, p1), a cubic Bézier is (p0, c1, c2, p3); points are (x, y).


def lerp(a, b, t):
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def point_at(seg, t):
    if len(seg) == 2:
        return lerp(seg[0], seg[1], t)
    u = 1 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * seg[0][0] + b * seg[1][0] + c * seg[2][0] + d * seg[3][0],
            a * seg[0][1] + b * seg[1][1] + c * seg[2][1] + d * seg[3][1])


def derivative_at(seg, t):
    if len(seg) == 2:
        return seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]
    p0, p1, p2, p3 = seg
    u = 1 - t
    return tuple(3 * (u * u * (p1[k] - p0[k]) + 2 * u * t * (p2[k] - p1[k]) + t * t * (p3[k] - p2[k])) for k in (0, 1))


def split_at(seg, t):
    if len(seg) == 2:
        m = lerp(seg[0], seg[1], t)
        return (seg[0], m), (m, seg[1])
    p0, p1, p2, p3 = seg
    a, b, c = lerp(p0, p1, t), lerp(p1, p2, t), lerp(p2, p3, t)
    d, e = lerp(a, b, t), lerp(b, c, t)
    m = lerp(d, e, t)
    return (p0, a, d, m), (m, e, c, p3)


def sub_segment(seg, t0, t1):
    """The part of ``seg`` between parameters t0 < t1."""
    if t0 > 0:
        seg = split_at(seg, t0)[1]
        t1 = (t1 - t0) / (1 - t0) if t0 < 1 else 1.0
    if t1 < 1:
        seg = split_at(seg, t1)[0]
    return seg


def reverse(seg):
    return tuple(reversed(seg))


def bounds_of(seg):
    xs, ys = [p[0] for p in seg], [p[1] for p in seg]
    return min(xs), min(ys), max(xs), max(ys)


def boxes_meet(a, b, slack=1e-9):
    return a[0] <= b[2] + slack and b[0] <= a[2] + slack and a[1] <= b[3] + slack and b[1] <= a[3] + slack


def is_flat(seg, tolerance=2e-3):
    """True when a cubic's control points lie within ``tolerance`` of its chord."""
    p0, p3 = seg[0], seg[-1]
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    length = math.hypot(dx, dy)
    for p in seg[1:-1]:
        if length < 1e-12:
            off = math.hypot(p[0] - p0[0], p[1] - p0[1])
        else:
            off = abs((p[0] - p0[0]) * dy - (p[1] - p0[1]) * dx) / length
        if off > tolerance:
            return False
    return True


def line_line(a, b, slack=1e-9):
    """(t_a, t_b) where two line segments meet; collinear overlaps give the overlap's end points."""
    (ax, ay), (bx, by) = a
    (cx, cy), (dx, dy) = b
    d1x, d1y, d2x, d2y = bx - ax, by - ay, dx - cx, dy - cy
    denom = d1x * d2y - d1y * d2x
    scale = math.hypot(d1x, d1y) * math.hypot(d2x, d2y)
    ex, ey = cx - ax, cy - ay
    if abs(denom) <= 1e-12 * max(scale, 1e-300):
        length = math.hypot(d1x, d1y)
        if length < 1e-12 or math.hypot(d2x, d2y) < 1e-12 or abs(ex * d1y - ey * d1x) / length > 1e-7:
            return []
        out, square = [], d1x * d1x + d1y * d1y
        for tb, (px, py) in ((0.0, (cx, cy)), (1.0, (dx, dy))):
            ta = ((px - ax) * d1x + (py - ay) * d1y) / square
            if -slack <= ta <= 1 + slack:
                out.append((min(1.0, max(0.0, ta)), tb))
        square = d2x * d2x + d2y * d2y
        for ta, (px, py) in ((0.0, (ax, ay)), (1.0, (bx, by))):
            tb = ((px - cx) * d2x + (py - cy) * d2y) / square
            if -slack <= tb <= 1 + slack:
                out.append((ta, min(1.0, max(0.0, tb))))
        return out
    ta = (ex * d2y - ey * d2x) / denom
    tb = (ex * d1y - ey * d1x) / denom
    if -slack <= ta <= 1 + slack and -slack <= tb <= 1 + slack:
        return [(min(1.0, max(0.0, ta)), min(1.0, max(0.0, tb)))]
    return []


def cubic_roots(c3, c2, c1, c0):
    """Real roots in [0, 1] of c3 t³ + c2 t² + c1 t + c0 (a trigonometric or Cardano solution)."""
    scale = max(abs(c3), abs(c2), abs(c1), abs(c0))
    if scale == 0:
        return []
    c3, c2, c1, c0 = c3 / scale, c2 / scale, c1 / scale, c0 / scale
    if abs(c3) < 1e-12:
        if abs(c2) < 1e-12:
            roots = [] if abs(c1) < 1e-12 else [-c0 / c1]
        else:
            disc = c1 * c1 - 4 * c2 * c0
            if disc < 0:
                roots = []
            else:
                root = math.sqrt(disc)
                roots = [(-c1 + root) / (2 * c2), (-c1 - root) / (2 * c2)]
    else:
        b, c, d = c2 / c3, c1 / c3, c0 / c3
        p, q = c - b * b / 3, 2 * b ** 3 / 27 - b * c / 3 + d
        shift = -b / 3
        disc = (q / 2) ** 2 + (p / 3) ** 3
        if disc > 1e-14:
            root = math.sqrt(disc)
            roots = [math.copysign(abs(-q / 2 + root) ** (1 / 3), -q / 2 + root)
                     + math.copysign(abs(-q / 2 - root) ** (1 / 3), -q / 2 - root) + shift]
        elif p == 0 and q == 0:
            roots = [shift]
        else:
            r = 2 * math.sqrt(-p / 3)
            arg = max(-1.0, min(1.0, 3 * q / (p * r))) if p else 0.0
            phi = math.acos(arg) / 3
            roots = [r * math.cos(phi - 2 * math.pi * k / 3) + shift for k in range(3)]
    return sorted({min(1.0, max(0.0, t)) for t in roots if -1e-9 <= t <= 1 + 1e-9})


def line_cubic(line, cubic, slack=1e-9):
    """(t_line, t_cubic) pairs where a line segment meets a cubic."""
    (ax, ay), (bx, by) = line
    dx, dy = bx - ax, by - ay
    square = dx * dx + dy * dy
    if square < 1e-18:
        return []
    nx, ny = -dy, dx
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = cubic
    # Signed distance of the cubic from the line's supporting line, as a polynomial in t.
    f = [nx * x + ny * y for x, y in ((x0 - ax, y0 - ay), (x1 - ax, y1 - ay), (x2 - ax, y2 - ay), (x3 - ax, y3 - ay))]
    c3 = -f[0] + 3 * f[1] - 3 * f[2] + f[3]
    c2 = 3 * f[0] - 6 * f[1] + 3 * f[2]
    c1 = -3 * f[0] + 3 * f[1]
    roots = cubic_roots(c3, c2, c1, f[0])
    # A line that only touches the cubic (a tangent) is a double root that rounding can lose: a turning
    # point of the distance that lies on the line is a contact too.
    reach = 1e-6 * math.sqrt(square)
    for t in cubic_roots(0.0, 3 * c3, 2 * c2, c1):
        if 1e-9 < t < 1 - 1e-9 and abs(((c3 * t + c2) * t + c1) * t + f[0]) < reach \
                and not any(abs(t - r) < 1e-6 for r in roots):
            roots.append(t)
    out = []
    for t in sorted(roots):
        px, py = point_at(cubic, t)
        s = ((px - ax) * dx + (py - ay) * dy) / square
        if -slack <= s <= 1 + slack:
            out.append((min(1.0, max(0.0, s)), t))
    return out


def _nearest(p, chord):
    """(distance, t) from point ``p`` to the closest point of a chord."""
    (x0, y0), (x1, y1) = chord
    dx, dy = x1 - x0, y1 - y0
    square = dx * dx + dy * dy
    t = 0.0 if square < 1e-18 else min(1.0, max(0.0, ((p[0] - x0) * dx + (p[1] - y0) * dy) / square))
    return math.hypot(p[0] - (x0 + dx * t), p[1] - (y0 + dy * t)), t


def chord_contact(a, b):
    """(s, t) of the closest points of two chords that do not cross, when they come within ``CONTACT``."""
    options = [(*_nearest(p, b), s) for s, p in ((0.0, a[0]), (1.0, a[1]))]
    best = min((d, s, t) for d, t, s in options)
    for t, p in ((0.0, b[0]), (1.0, b[1])):
        d, s = _nearest(p, a)
        if d < best[0]:
            best = (d, s, t)
    return (best[1], best[2]) if best[0] < CONTACT else None


def cubic_cubic(a, b):
    """(t_a, t_b) pairs where two cubics meet, by subdivision and Newton refinement."""
    if all(math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-9 for p, q in zip(a, b)):
        return [(0.0, 0.0), (1.0, 1.0)]  # the same curve: only its end points split it
    if all(math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-9 for p, q in zip(a, reversed(b))):
        return [(0.0, 1.0), (1.0, 0.0)]
    found, budget = [], SUBDIVISION_LIMIT
    stack = [(a, 0.0, 1.0, b, 0.0, 1.0)]
    while stack:
        ca, a0, a1, cb, b0, b1 = stack.pop()
        budget -= 1
        if budget < 0:
            raise Unsupported("curves overlap along part of their length")
        if not boxes_meet(bounds_of(ca), bounds_of(cb)):
            continue
        flat_a, flat_b = is_flat(ca), is_flat(cb)
        if flat_a and flat_b:
            hits = line_line((ca[0], ca[3]), (cb[0], cb[3]), slack=0.05)
            if not hits:
                near = chord_contact((ca[0], ca[3]), (cb[0], cb[3]))
                hits = [near] if near else []
            for s, t in hits:
                found.append((a0 + (a1 - a0) * s, b0 + (b1 - b0) * t))
            continue
        halves_a = [(ca, a0, a1)] if flat_a else [
            (half, lo, hi) for half, lo, hi in zip(split_at(ca, 0.5), (a0, (a0 + a1) / 2), ((a0 + a1) / 2, a1))]
        halves_b = [(cb, b0, b1)] if flat_b else [
            (half, lo, hi) for half, lo, hi in zip(split_at(cb, 0.5), (b0, (b0 + b1) / 2), ((b0 + b1) / 2, b1))]
        for xa, lo_a, hi_a in halves_a:
            for xb, lo_b, hi_b in halves_b:
                stack.append((xa, lo_a, hi_a, xb, lo_b, hi_b))
    refined = []
    for ta, tb in found:
        ta, tb = min(1.0, max(0.0, ta)), min(1.0, max(0.0, tb))
        for _ in range(8):
            pa, pb = point_at(a, ta), point_at(b, tb)
            rx, ry = pa[0] - pb[0], pa[1] - pb[1]
            da, db = derivative_at(a, ta), derivative_at(b, tb)
            det = -da[0] * db[1] + db[0] * da[1]
            if abs(det) < 1e-14:
                break
            ta -= (-rx * db[1] + db[0] * ry) / det
            tb -= (da[0] * ry - da[1] * rx) / det
            ta, tb = min(1.0, max(0.0, ta)), min(1.0, max(0.0, tb))
        pa, pb = point_at(a, ta), point_at(b, tb)
        if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < CONTACT:
            refined.append((ta, tb))
    result = []
    for ta, tb in sorted(refined):
        here = point_at(a, ta)
        if not any(math.hypot(here[0] - q[0], here[1] - q[1]) < CONTACT for q in (point_at(a, sa) for sa, _ in result)):
            result.append((ta, tb))
    return result


def intersections(a, b):
    if len(a) == 2 and len(b) == 2:
        return line_line(a, b)
    if len(a) == 2:
        return line_cubic(a, b)
    if len(b) == 2:
        return [(ta, tb) for tb, ta in line_cubic(b, a)]
    return cubic_cubic(a, b)


def turning_points(seg, axes):
    """Parameters inside (0, 1) where a cubic stops rising and starts falling (or back) along an axis."""
    cuts = []
    for axis in axes:
        d0, d1, d2 = (seg[1][axis] - seg[0][axis]), (seg[2][axis] - seg[1][axis]), (seg[3][axis] - seg[2][axis])
        a, b, c = d0 - 2 * d1 + d2, 2 * (d1 - d0), d0
        if abs(a) < 1e-12:
            if abs(b) > 1e-12:
                cuts.append(-c / b)
        else:
            disc = b * b - 4 * a * c
            if disc > 0:
                root = math.sqrt(disc)
                cuts += [(-b - root) / (2 * a), (-b + root) / (2 * a)]
    return sorted(t for t in cuts if 1e-9 < t < 1 - 1e-9)


def monotone_parts(seg, axes=(0, 1)):
    """(part, lo, hi) pieces of a segment that move steadily along every axis: such a part cannot cross
    itself, and two of them can be tested against each other cheaply."""
    if len(seg) == 2:
        return [(seg, 0.0, 1.0)]
    edges = [0.0, *turning_points(seg, axes), 1.0]
    return [(sub_segment(seg, lo, hi), lo, hi) for lo, hi in zip(edges, edges[1:])]


def monotone_pieces(seg):
    """The parts of a segment along which y only rises or only falls."""
    return [part for part, _, _ in monotone_parts(seg, (1,))]


def crossings(a, b, same=False):
    """(t_a, t_b) pairs where two segments meet, or where a segment crosses itself (``same``), tested part
    by part so that a cubic's own loops are found."""
    parts_a = monotone_parts(a)
    parts_b = parts_a if same else monotone_parts(b)
    if len(parts_a) == 1 and len(parts_b) == 1 and not same:
        return intersections(a, b)
    found = []
    for i, (pa, a0, a1) in enumerate(parts_a):
        for j, (pb, b0, b1) in enumerate(parts_b):
            if same and j <= i:
                continue
            if not boxes_meet(bounds_of(pa), bounds_of(pb)):
                continue
            for ta, tb in intersections(pa, pb):
                if same and j == i + 1 and ta > 1 - 1e-9 and tb < 1e-9:
                    continue  # the joint between two neighbouring parts
                found.append((a0 + (a1 - a0) * ta, b0 + (b1 - b0) * tb))
    return found


class Region:
    """Closed contours filled with the nonzero rule, with a winding-number test for points."""

    def __init__(self, contours):
        self.pieces = []
        for contour in contours:
            for seg in contour:
                for mono in monotone_pieces(seg):
                    y0, y1 = mono[0][1], mono[-1][1]
                    if y0 != y1:
                        self.pieces.append((mono, min(y0, y1), max(y0, y1), 1 if y1 > y0 else -1))
        self.top = min((p[1] for p in self.pieces), default=0.0)
        self.bottom = max((p[2] for p in self.pieces), default=0.0)

    def winding(self, x, y):
        if not self.pieces or y < self.top or y >= self.bottom:
            return 0
        total = 0
        for seg, low, high, direction in self.pieces:
            if low <= y < high and self._cross(seg, y) > x:
                total += direction
        return total

    @staticmethod
    def _cross(seg, y):
        (x0, y0), (x3, y3) = seg[0], seg[-1]
        if len(seg) == 2:
            return x0 + (x3 - x0) * (y - y0) / (y3 - y0)
        (_, ya), (_, yb) = seg[1], seg[2]
        rising = y3 > y0
        lo, hi = 0.0, 1.0
        for _ in range(52):
            t = (lo + hi) / 2
            u = 1 - t
            value = u * u * u * y0 + 3 * u * u * t * ya + 3 * u * t * t * yb + t * t * t * y3
            if (value < y) == rising:
                lo = t
            else:
                hi = t
        return point_at(seg, (lo + hi) / 2)[0]


class Points:
    """Canonical points: coordinates within ``TOLERANCE`` of each other are one point."""

    def __init__(self):
        self.cells, self.coords = {}, []

    def add(self, p):
        cx, cy = math.floor(p[0] / TOLERANCE), math.floor(p[1] / TOLERANCE)
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for ident in self.cells.get((i, j), ()):
                    q = self.coords[ident]
                    if math.hypot(q[0] - p[0], q[1] - p[1]) <= TOLERANCE:
                        return ident
        self.coords.append(p)
        self.cells.setdefault((cx, cy), []).append(len(self.coords) - 1)
        return len(self.coords) - 1


class Piece:
    """Part of an original segment (``source``, number ``parent``) between parameters ``t0`` and ``t1``,
    walked from point ``start`` to point ``end`` (``t0 > t1`` when walked backwards)."""

    __slots__ = ("seg", "source", "parent", "t0", "t1", "start", "end")

    def __init__(self, seg, source, parent, t0, t1, start, end):
        self.seg, self.source, self.parent, self.t0, self.t1, self.start, self.end = (
            seg, source, parent, t0, t1, start, end)


def combine_outlines(inputs, combine):
    """Contours of the shape ``combine(inside_0, inside_1, …)`` for operands given as contour lists.

    Each operand is a list of closed contours (lists of segments) filled with the nonzero rule.
    The result's contours have the inside on their left."""
    segments = [(seg, source) for source, contours in enumerate(inputs) for contour in contours for seg in contour]
    if len(segments) > MAX_SEGMENTS:
        raise Unsupported(f"the outlines have more than {MAX_SEGMENTS} segments")
    if not segments:
        return []
    regions = [Region(contours) for contours in inputs]
    points = Points()
    splits = [[(0.0, points.add(seg[0])), (1.0, points.add(seg[-1]))] for seg, _ in segments]
    boxes = [bounds_of(seg) for seg, _ in segments]
    order = sorted(range(len(segments)), key=lambda i: boxes[i][0])
    for n, i in enumerate(order):
        for j in order[n + 1:]:
            if boxes[j][0] > boxes[i][2] + 1e-9:
                break
            if not boxes_meet(boxes[i], boxes[j]):
                continue
            for ti, tj in crossings(segments[i][0], segments[j][0]):
                a, b = point_at(segments[i][0], ti), point_at(segments[j][0], tj)
                ident = points.add(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
                splits[i].append((ti, ident))
                splits[j].append((tj, ident))
    for i, (seg, _) in enumerate(segments):
        if len(seg) == 4:
            for ti, tj in crossings(seg, seg, same=True):  # a cubic that loops through itself
                a, b = point_at(seg, ti), point_at(seg, tj)
                ident = points.add(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
                splits[i] += [(ti, ident), (tj, ident)]
    pieces = []
    for index, ((seg, _), cuts) in enumerate(zip(segments, splits)):
        cuts.sort()
        for (t0, start), (t1, end) in zip(cuts, cuts[1:]):
            piece = sub_segment(seg, t0, t1)
            a, b = points.coords[start], points.coords[end]
            piece = (a, *piece[1:-1], b)
            if t1 - t0 < 1e-9 or (start == end and max(map(abs, (a[0] - piece[1][0], a[1] - piece[1][1],
                                                                 a[0] - piece[-2][0], a[1] - piece[-2][1]))) < TOLERANCE):
                continue  # a loop of a cubic back onto itself is a piece; a zero-length one is not
            pieces.append(Piece(piece, seg, index, t0, t1, start, end))
    kept = []
    for piece in pieces:
        mid = point_at(piece.seg, 0.5)
        tangent = derivative_at(piece.seg, 0.5)
        if math.hypot(*tangent) < 1e-12:
            tangent = (piece.seg[-1][0] - piece.seg[0][0], piece.seg[-1][1] - piece.seg[0][1])
        norm = math.hypot(*tangent)
        if norm < 1e-12:
            continue
        x0, y0, x1, y1 = bounds_of(piece.seg)
        probe = min(1e-3, max(1e-7, 0.05 * max(x1 - x0, y1 - y0)))  # a loop has no chord: size it by its box
        nx, ny = -tangent[1] / norm * probe, tangent[0] / norm * probe
        left = combine(*[r.winding(mid[0] + nx, mid[1] + ny) != 0 for r in regions])
        right = combine(*[r.winding(mid[0] - nx, mid[1] - ny) != 0 for r in regions])
        if left == right:
            continue
        if not left:  # the inside is on the right: walk the piece the other way
            piece.seg = reverse(piece.seg)
            piece.t0, piece.t1 = piece.t1, piece.t0
            piece.start, piece.end = piece.end, piece.start
        kept.append(piece)
    unique = []
    for piece in kept:  # coincident edges of two operands appear twice
        mid = point_at(piece.seg, 0.5)
        if not any(other.start == piece.start and other.end == piece.end
                   and math.hypot(*[a - b for a, b in zip(mid, point_at(other.seg, 0.5))]) < 1e-3 for other in unique):
            unique.append(piece)
    return [straighten(merge_pieces(chain, points)) for chain in chain_pieces(unique)]


def chain_pieces(pieces):
    by_start = defaultdict(list)
    for index, piece in enumerate(pieces):
        by_start[piece.start].append(index)
    used, chains = set(), []
    for first in range(len(pieces)):
        if first in used:
            continue
        chain, index = [], first
        while True:
            used.add(index)
            chain.append(pieces[index])
            end = pieces[index].end
            if end == pieces[first].start:
                break
            following = next((j for j in by_start[end] if j not in used), None)
            if following is None:
                raise Unsupported("the combined outline does not close up")
            index = following
        chains.append(chain)
    return chains


def straighten(contour):
    """Join consecutive lines that run the same way (the edge of one operand cut where another touches it)."""
    def same_line(a, b):
        d1, d2 = (a[1][0] - a[0][0], a[1][1] - a[0][1]), (b[1][0] - b[0][0], b[1][1] - b[0][1])
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        return abs(cross) <= 1e-9 * math.hypot(*d1) * math.hypot(*d2) and d1[0] * d2[0] + d1[1] * d2[1] > 0

    out = []
    for seg in contour:
        if out and len(seg) == 2 and len(out[-1]) == 2 and same_line(out[-1], seg):
            out[-1] = (out[-1][0], seg[1])
        else:
            out.append(seg)
    if len(out) > 2 and len(out[0]) == 2 and len(out[-1]) == 2 and same_line(out[-1], out[0]):
        out[0] = (out[-1][0], out[0][1])
        out.pop()
    return out


def merge_pieces(chain, points):
    """Join consecutive pieces that are parts of one original segment, so cut curves become whole again."""
    merged = list(chain)
    changed = True
    while changed and len(merged) > 1:
        changed = False
        for i in range(len(merged)):
            a, b = merged[i], merged[(i + 1) % len(merged)]
            if a is b or a.parent != b.parent or (a.t1 - a.t0) * (b.t1 - b.t0) <= 0 or abs(a.t1 - b.t0) > 1e-9:
                continue
            low, high = min(a.t0, b.t1), max(a.t0, b.t1)
            seg = sub_segment(a.source, low, high)
            if a.t0 > b.t1:
                seg = reverse(seg)
            seg = (points.coords[a.start], *seg[1:-1], points.coords[b.end])
            joined = Piece(seg, a.source, a.parent, a.t0, b.t1, a.start, b.end)
            if i + 1 < len(merged):
                merged[i:i + 2] = [joined]
            else:
                merged = [joined, *merged[1:-1]]
            changed = True
            break
    return [piece.seg for piece in merged]

