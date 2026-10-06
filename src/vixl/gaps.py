"""Closing the small gaps in a hand drawing's strokes.

A gap is an open end that stops just short of another line. It is closed the way a draughtsman
would (never by running an end on further than half its own length, so a short tick is not turned
into a long line): two straight ends that were meant to make a corner are both run on to the point where
their lines cross (so the corner is sharp and the lines keep their angles); a straight end that
was meant to land on another line runs on until it touches it; two straight ends of one line
broken in the middle meet halfway along it; curved ends (a canopy, a cloud) are bridged. Gaps are
joined nearest first, each end at most once. Pure NumPy.
"""

import math

import numpy as np

MIN_SIDE = 6.0         # an end counts as straight when its last side is at least this long (pixels)
PARALLEL = math.sin(math.radians(12))
COLLINEAR = math.cos(math.radians(25))
REACH = 12.0           # arc length of a curved end that gives its direction


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _end(stroke, which):
    """(point, outward unit direction, whether the end is a straight side, length of that side) of
    one end of a stroke."""
    p = np.asarray(stroke["points"], float)
    q = p if which == 0 else p[::-1]
    v = q[0] - q[1]
    side = float(np.linalg.norm(v))
    straight = stroke.get("kind") in ("line", "polyline") and side >= MIN_SIDE
    if not straight:
        # A curved or untouched end: its direction is the chord of its last stretch.
        along = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
        v = q[0] - q[min(len(q) - 1, int(np.searchsorted(along, REACH)))]
        side = float(np.linalg.norm(v))
    return q[0], (v / side if side > 1e-9 else np.zeros(2)), straight, side


def _meet(pa, da, pb, db):
    """(t, u) with pa + t·da = pb + u·db, or None for parallel lines."""
    cross = float(_cross(da, db))
    if abs(cross) < PARALLEL:
        return None
    w = pb - pa
    return float(_cross(w, db)) / cross, float(_cross(w, da)) / cross


def close_gaps(strokes, gap, movable=None):
    """Close gaps of up to ``gap`` pixels between the open ends of ``strokes`` (dicts with an
    (n, 2) array ``points``, ``closed`` and optionally ``kind``), changing them in place. Only the
    strokes at the indices in ``movable`` (default: all) change; the rest are only run on to.
    Returns the number of gaps closed."""
    movable = set(range(len(strokes))) if movable is None else set(movable)
    ends = []
    for index, stroke in enumerate(strokes):
        if stroke["closed"] or len(stroke["points"]) < 2 or index not in movable:
            continue
        for which in (0, -1):
            point, direction, straight, side = _end(stroke, which)
            ends.append({"stroke": index, "which": which, "point": point, "direction": direction, "straight": straight,
                         "side": side})
    # Every side of every stroke, to run a straight end on until it touches one.
    first, last, owner = [], [], []
    for index, stroke in enumerate(strokes):
        p = np.asarray(stroke["points"], float)
        if stroke["closed"] and len(p) > 2:
            p = np.vstack([p, p[:1]])
        if len(p) >= 2:
            first.append(p[:-1])
            last.append(p[1:])
            owner.append(np.full(len(p) - 1, index))
    first, last, owner = (np.vstack(first), np.vstack(last), np.concatenate(owner)) if first else (None, None, None)

    candidates = []  # (cost, kind, end, other end or hit point)
    for i, a in enumerate(ends):
        for j in range(i + 1, len(ends)):
            b = ends[j]
            d = float(np.linalg.norm(a["point"] - b["point"]))
            same = a["stroke"] == b["stroke"]
            if 0 < d <= gap and not (same and len(strokes[a["stroke"]]["points"]) < 4):
                candidates.append((d, "ends", i, j))
        if a["straight"] and first is not None:
            r = a["direction"]
            s = last - first
            denom = _cross(r, s)
            with np.errstate(divide="ignore", invalid="ignore"):
                t = _cross(first - a["point"], s) / denom
                u = _cross(first - a["point"], r) / denom
            hit = (np.abs(denom) > 1e-9) & (t >= 0.25) & (t <= min(gap, a["side"] / 2)) & (u >= -0.02) & (u <= 1.02) \
                & (owner != a["stroke"])
            if hit.any():
                k = int(np.argmin(np.where(hit, t, np.inf)))
                candidates.append((float(t[k]), "body", i, float(t[k])))
    taken = set()
    joins = 0
    for _, kind, i, other in sorted(candidates, key=lambda c: (c[0], c[2])):
        a = ends[i]
        if i in taken:
            continue
        if kind == "body":
            _set_end(strokes[a["stroke"]], a["which"], a["point"] + a["direction"] * other)
            taken.add(i)
            joins += 1
            continue
        b = ends[other]
        if other in taken or not _join(strokes, a, b, gap):
            continue
        taken.update((i, other))
        joins += 1
    return joins


def _set_end(stroke, which, point):
    points = np.asarray(stroke["points"], float).copy()
    points[which] = point
    stroke["points"] = points


def _add_end(stroke, which, point):
    points = np.asarray(stroke["points"], float)
    stroke["points"] = np.vstack([point[None], points]) if which == 0 else np.vstack([points, point[None]])


def _join(strokes, a, b, gap):
    """Join two open ends; False when they should be left alone."""
    sa, sb = strokes[a["stroke"]], strokes[b["stroke"]]
    pa, pb, da, db = a["point"], b["point"], a["direction"], b["direction"]
    if a["straight"] and b["straight"]:
        meet = _meet(pa, da, pb, db)
        if meet is not None:
            t, u = meet
            if -3 <= t <= min(gap * 1.25, a["side"] / 2) and -3 <= u <= min(gap * 1.25, b["side"] / 2):
                corner = pa + da * t
                if sa is sb:
                    return _close_loop(sa, corner)
                _set_end(sa, a["which"], corner)
                _set_end(sb, b["which"], corner)
                return True
            return False
        if float(da @ db) < -COLLINEAR:
            # One line broken in the middle: both ends meet halfway, each staying on its own line.
            middle = (pa + pb) / 2
            if sa is sb:
                return False
            for stroke, end, p, d in ((sa, a["which"], pa, da), (sb, b["which"], pb, db)):
                _set_end(stroke, end, p + d * float((middle - p) @ d))
            return True
        return False
    if sa is sb:
        sa["closed"] = True
        return True
    middle = (pa + pb) / 2
    _add_end(sa, a["which"], middle)
    _add_end(sb, b["which"], middle)
    return True


def _close_loop(stroke, corner):
    """A polyline whose two ends meet at ``corner``: its first and last sides run on to it and the
    stroke closes (the corner replaces both ends, which lie on those sides)."""
    points = np.asarray(stroke["points"], float)
    if len(points) < 4:
        return False
    stroke["points"] = np.vstack([corner[None], points[1:-1]])
    stroke["closed"] = True
    return True
