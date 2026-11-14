"""Find the guide lines of one colour in a printer's template image.

A template marks the board edge, the safe areas, a barcode notch and the folds as dashed or solid horizontal and
vertical lines, one colour per meaning. ``lines`` finds those lines in a pixel mask; ``outlines`` joins the ones
that meet into closed outlines (a rectangle, or a safe area with a notch cut out of it) and leaves the rest as open
lines. Everything is in whole image pixels. Diagonal and curved lines are not read.
"""

import math

import numpy as np

from ...errors import require

MAX_RUNS = 200_000


def color_mask(pixels, rgb, tolerance):
    """Where ``pixels`` (H × W × 4, uint8) match ``rgb`` within ``tolerance`` per channel and are opaque."""
    difference = np.abs(pixels[..., :3].astype(np.int16) - np.array(rgb, dtype=np.int16)).max(axis=2)
    return (difference <= tolerance) & (pixels[..., 3] >= 128)


def line_colors(pixels, limit=8):
    """The saturated colours a template draws with, most common first: ``[{color, pixels}]``. Greys and near-white
    are left out (a black or grey line can still be named in ``colors``)."""
    rgb = pixels[..., :3].astype(np.int16)
    vivid = (rgb.max(axis=2) - rgb.min(axis=2) >= 80) & (pixels[..., 3] >= 128)
    chosen = pixels[..., :3][vivid]
    if not len(chosen):
        return []
    # Bins of 16 levels per channel group a line with its anti-aliased edge; each bin reports its commonest colour.
    exact = (chosen[:, 0].astype(np.int64) << 16) | (chosen[:, 1].astype(np.int64) << 8) | chosen[:, 2]
    values, counts = np.unique(exact, return_counts=True)
    bins = ((values >> 20) << 8) | (((values >> 12) & 15) << 4) | ((values >> 4) & 15)
    found = {}
    for value, count, key in zip(values.tolist(), counts.tolist(), bins.tolist()):
        entry = found.setdefault(key, [0, 0, value])
        entry[0] += count
        if count > entry[1]:
            entry[1], entry[2] = count, value
    ranked = sorted(found.values(), key=lambda entry: -entry[0])[:limit]
    ranked = [entry for entry in ranked if entry[0] * 20 >= ranked[0][0]]  # not the blends along a line's edge
    return [{"color": f"#{value:06x}", "pixels": total} for total, _, value in ranked]


def _runs(mask, gap, minimum):
    """Runs of set pixels along each row once gaps of at most ``gap`` are bridged (dashes): (row, start, end) arrays,
    ``end`` exclusive. A run is kept when it is at least ``minimum`` long and a fifth of it is drawn."""
    height, width = mask.shape
    padded = np.zeros((height, width + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    edges = np.diff(padded, axis=1)
    rows, starts = np.nonzero(edges == 1)
    ends = np.nonzero(edges == -1)[1]
    if not len(rows):
        return rows, starts, ends
    breaks = np.ones(len(rows) + 1, dtype=bool)
    breaks[1:-1] = (rows[1:] != rows[:-1]) | (starts[1:] - ends[:-1] > gap)
    first, last = np.nonzero(breaks[:-1])[0], np.nonzero(breaks[1:])[0]
    row, start, end = rows[first], starts[first], ends[last]
    drawn = np.add.reduceat(ends - starts, first)
    keep = (end - start >= minimum) & (drawn * 5 >= end - start)
    return row[keep], start[keep], end[keep]


def _segments(mask, gap, minimum, thickness):
    """Horizontal line segments in ``mask`` as (position, start, end) with inclusive pixel ends: runs on adjacent
    rows with the same extent are one line of that many rows; anything thicker than ``thickness`` is not a line
    (lettering or a filled patch in the same colour)."""
    row, start, end = _runs(mask, gap, minimum)
    require(len(row) <= MAX_RUNS, "The colour covers too much of the template to be guide lines; name the line "
            "colour exactly or lower tolerance", "resource_limit", field="colors")
    groups, open_groups = [], []
    for r, s, e in zip(row.tolist(), start.tolist(), end.tolist()):
        still = []
        match = None
        for group in open_groups:
            if group[1] < r - 1:
                groups.append(group)
                continue
            still.append(group)
            if match is None and group[1] == r - 1 and abs(group[2] - s) <= gap and abs(group[3] - e) <= gap:
                match = group
        open_groups = still
        if match is None:
            open_groups.append([r, r, s, e, s, e])
        else:
            match[1], match[2], match[3] = r, s, e
            match[4], match[5] = min(match[4], s), max(match[5], e)
    groups += open_groups
    found = []
    for top, bottom, _, _, left, right in groups:
        if bottom - top + 1 > thickness:
            continue
        # A line stands alone: the rows beside it are empty but for the lines that cross it. Rows of lettering have
        # more of the same colour right above or below.
        beside = max((int(mask[near, left:right].sum()) for near in (top - 1, bottom + 1)
                      if 0 <= near < mask.shape[0]), default=0)
        if beside <= 4 * thickness + 0.1 * (right - left):
            found.append(((top + bottom + 1) // 2, left, right - 1))
    return found


def lines(mask, gap, minimum, thickness):
    """(horizontal, vertical) line segments of a mask: lists of (y, x0, x1) and (x, y0, y1)."""
    return _segments(mask, gap, minimum, thickness), _segments(mask.T, gap, minimum, thickness)


def outlines(horizontal, vertical, reach, minimum):
    """Join line segments that meet (within ``reach`` pixels, for a dash gap at a corner) into closed outlines.

    Returns ``(closed, open)``: ``closed`` is a list of polygons ([[x, y], …], corners only, each the smallest
    outline around one area, so two boxes sharing an edge give two) and ``open`` the remaining lines as
    ``("h", y, x0, x1)`` or ``("v", x, y0, y1)``."""
    cuts_h = [[] for _ in horizontal]
    cuts_v = [[] for _ in vertical]
    for i, (y, x0, x1) in enumerate(horizontal):
        for j, (x, y0, y1) in enumerate(vertical):
            if x0 - reach <= x <= x1 + reach and y0 - reach <= y <= y1 + reach:
                cuts_h[i].append(x)
                cuts_v[j].append(y)
    neighbours = {}
    stubs = []

    def link(a, b):
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)

    for (y, x0, x1), cuts in zip(horizontal, cuts_h):
        cuts = sorted(set(cuts))
        if not cuts:
            stubs.append(("h", y, x0, x1))
            continue
        for a, b in zip(cuts, cuts[1:]):
            link((a, y), (b, y))
        if cuts[0] - x0 > max(reach, minimum):
            stubs.append(("h", y, x0, cuts[0]))
        if x1 - cuts[-1] > max(reach, minimum):
            stubs.append(("h", y, cuts[-1], x1))
    for (x, y0, y1), cuts in zip(vertical, cuts_v):
        cuts = sorted(set(cuts))
        if not cuts:
            stubs.append(("v", x, y0, y1))
            continue
        for a, b in zip(cuts, cuts[1:]):
            link((x, a), (x, b))
        if cuts[0] - y0 > max(reach, minimum):
            stubs.append(("v", x, y0, cuts[0]))
        if y1 - cuts[-1] > max(reach, minimum):
            stubs.append(("v", x, cuts[-1], y1))
    # Lines that end without meeting another are open: peel them off until only loops are left.
    loose = [node for node, others in neighbours.items() if len(others) == 1]
    while loose:
        node = loose.pop()
        others = neighbours.pop(node, set())
        for other in others:
            stubs.append(("h", node[1], *sorted((node[0], other[0]))) if node[1] == other[1] else
                         ("v", node[0], *sorted((node[1], other[1]))))
            neighbours[other].discard(node)
            if len(neighbours[other]) == 1:
                loose.append(other)
            elif not neighbours[other]:
                del neighbours[other]
    closed = _faces(neighbours)
    return closed, _merge(stubs)


def _faces(neighbours):
    """The bounded faces of a planar graph of axis-aligned edges, as corner polygons."""
    order = {node: sorted(others, key=lambda other, node=node: math.atan2(other[1] - node[1], other[0] - node[0]))
             for node, others in neighbours.items()}
    seen, faces = set(), []
    for start in sorted(order):
        for following in order[start]:
            if (start, following) in seen:
                continue
            path, a, b = [], start, following
            while (a, b) not in seen and len(path) <= 4 * len(order) + 4:
                seen.add((a, b))
                path.append(a)
                ring = order[b]
                a, b = b, ring[(ring.index(a) + 1) % len(ring)]
            area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(path, path[1:] + path[:1])) / 2
            if area < -0.5 and len(path) >= 4:  # the unbounded face around a loop winds the other way
                faces.append(_corners_only(path))
    return sorted(faces, key=lambda face: (min(p[0] for p in face), min(p[1] for p in face)))


def _corners_only(path):
    kept = []
    for before, point, after in zip(path[-1:] + path[:-1], path, path[1:] + path[:1]):
        if (before[0] == point[0] == after[0]) or (before[1] == point[1] == after[1]):
            continue
        kept.append([int(point[0]), int(point[1])])
    return kept


def _merge(stubs):
    """Collinear pieces that touch, joined back into one line each."""
    merged = []
    for key in sorted({(kind, at) for kind, at, _, _ in stubs}):
        spans = sorted((a, b) for kind, at, a, b in stubs if (kind, at) == key)
        current = list(spans[0])
        for a, b in spans[1:]:
            if a <= current[1]:
                current[1] = max(current[1], b)
            else:
                merged.append((*key, *current))
                current = [a, b]
        merged.append((*key, *current))
    return merged
