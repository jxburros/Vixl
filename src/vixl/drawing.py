"""Hand drawings: bring in a sketch, keep it, and build on it.

A photographed or scanned drawing becomes a drawing group:

* ``NAME/original`` — the photo as imported (hidden; the reference everything is compared to);
* ``NAME/ink`` — the cleaned lines: paper, shadows and dust removed, the tilt corrected, the
  pencil's own texture and weight kept (``clean`` re-runs it with other settings);
* ``NAME/s001`` … — editable vector strokes traced along the lines (``vectorize``), which
  ``straighten`` snaps to straight lines, angles, guides and circles and ``smooth`` evens out,
  and whose gaps it can close; ``stroke`` adds new strokes in the same hand;
* ``NAME/fill-1`` … — colour under the lines, filling the regions the lines enclose (``fill``).

Every step keeps what it does not need to change. The ``drawing`` check measures how much of the
original line work the current drawing still covers (and how much is new), and ``compare``
draws the original under the result, so an agent can see what moved. Directions such as "clean
it up", "straighten the walls", "close the gaps", "colour the roof red" or "add a chimney" map to
these actions.
"""

import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .errors import require
from .model import finite, new_layer

TYPES = ("drawing",)
ACTIONS = ("import", "clean", "vectorize", "straighten", "smooth", "fill", "stroke", "restyle")
CLEAN = {"threshold": "auto", "sensitivity": 0.0, "despeckle": "auto", "weight": 0, "deskew": True, "crop": True,
         "margin": 24, "soft": True, "ink": "#1d1d1f", "flatten": True, "max_size": 2400}
MAX_STROKES = 240


# ---------------------------------------------------------------------------------------------
# Raster helpers


def label(mask):
    """8-connected components of a boolean mask: (labels int32 array, count). Union–find over
    the runs of each row, so it is fast on line art (no per-pixel Python loop)."""
    mask = np.asarray(mask, bool)
    height, width = mask.shape
    padded = np.zeros((height, width + 2), bool)
    padded[:, 1:-1] = mask
    edges = np.diff(padded.astype(np.int8), axis=1)
    rows, starts = np.nonzero(edges == 1)
    _, ends = np.nonzero(edges == -1)
    count = len(starts)
    labels = np.zeros((height, width), np.int32)
    if count == 0:
        return labels, 0
    parent = list(range(count))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    row_index = np.searchsorted(rows, np.arange(height + 1))
    for y in range(1, height):
        a0, a1 = row_index[y - 1], row_index[y]
        b0, b1 = row_index[y], row_index[y + 1]
        i, j = a0, b0
        while i < a1 and j < b1:
            # Runs [s, e) overlap with one pixel of slack for diagonal (8-connected) contact.
            if starts[i] <= ends[j] and starts[j] <= ends[i]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
            if ends[i] < ends[j]:
                i += 1
            else:
                j += 1
    roots = np.array([find(i) for i in range(count)])
    unique, compact = np.unique(roots, return_inverse=True)
    for index in range(count):
        labels[rows[index], starts[index]:ends[index]] = compact[index] + 1
    return labels, len(unique)


def dilate(mask, radius):
    if radius <= 0:
        return mask
    image = Image.fromarray(np.asarray(mask, np.uint8) * 255)
    while radius > 0:
        step = min(radius, 3)
        image = image.filter(ImageFilter.MaxFilter(2 * step + 1))
        radius -= step
    return np.asarray(image) > 127


def erode(mask, radius):
    return ~dilate(~np.asarray(mask, bool), radius)


def distance(mask, limit=64):
    """Approximate distance (in pixels) from each mask pixel to the nearest background pixel."""
    result = np.zeros(mask.shape, np.float32)
    current = np.asarray(mask, bool)
    image = Image.fromarray(current.astype(np.uint8) * 255)
    for step in range(1, limit + 1):
        if not current.any():
            break
        result[current] = step
        image = image.filter(ImageFilter.MinFilter(3))
        current = np.asarray(image) > 127
    return result


def flatten_paper(gray):
    """Divide out the paper's lighting: an estimate of the blank page (ink removed by a max
    filter, then blurred) becomes 1.0, so shadows and gradients disappear."""
    return np.clip(gray / np.maximum(paper_estimate(gray), 1.0), 0, 1)


def paper_estimate(gray):
    """The blank page under the drawing: a max filter removes the lines, a blur the grain."""
    height, width = gray.shape
    factor = max(1, round(max(height, width) / 300))
    small = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).resize(
        (max(1, width // factor), max(1, height // factor)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(6))
    return np.asarray(small.resize((width, height), Image.Resampling.BILINEAR), np.float32)


def otsu(values):
    histogram, edges = np.histogram(values, bins=256, range=(0, 1))
    histogram = histogram.astype(float)
    total = histogram.sum()
    if total == 0:
        return 0.5
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(histogram)
    mean = np.cumsum(histogram * centers)
    between = (mean[-1] * weight / total - mean) ** 2 / np.maximum(weight * (total - weight), 1e-9)
    return float(centers[int(np.argmax(between))])


def skew_angle(mask, limit=8.0):
    """The rotation (degrees) that makes the drawing's lines most horizontal/vertical."""
    height, width = mask.shape
    scale = min(1.0, 500 / max(height, width))
    small = Image.fromarray(np.asarray(mask, np.uint8) * 255).resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.BOX)
    if not np.asarray(small).any():
        return 0.0

    def score(angle):
        rotated = np.asarray(small.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True), float)
        return float(np.var(rotated.sum(axis=1)) + np.var(rotated.sum(axis=0)))

    best, best_score = 0.0, score(0.0)
    for angle in np.arange(-limit, limit + 0.01, 0.5):
        value = score(float(angle))
        if value > best_score * 1.0001:
            best, best_score = float(angle), value
    for angle in np.arange(best - 0.4, best + 0.41, 0.1):
        value = score(float(angle))
        if value > best_score:
            best, best_score = float(angle), value
    # Lines drawn by hand are rarely exact; only correct a clear tilt of the whole page.
    return round(best, 2) if abs(best) >= 0.3 else 0.0


def clean(image, settings=None, state=None):
    """Clean a photographed or scanned drawing. Returns {"ink": RGBA image of the lines on
    transparency, "mask": bool line mask, "angle", "crop": [x, y, w, h] of the result within the
    deskewed photo, "threshold"}. ``state`` resolves swatch colours for ``ink``."""
    from .design import resolve_color
    from .render import color

    settings = {**CLEAN, **(settings or {})}
    image = ImageOps.exif_transpose(image).convert("RGB")
    scale = min(1.0, settings["max_size"] / max(image.size))
    if scale < 1:
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                             Image.Resampling.LANCZOS)
    rgb = np.asarray(image, np.float32)
    gray = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    level = flatten_paper(gray) if settings["flatten"] else gray / 255
    darkness = 1 - level
    if settings["threshold"] == "auto":
        cut = otsu(darkness[darkness > 0.04]) if (darkness > 0.04).any() else 0.5
        cut = max(0.08, cut * 0.9)
    else:
        cut = finite(settings["threshold"], "threshold", 0.01, 0.99)
    cut = float(np.clip(cut - 0.15 * finite(settings["sensitivity"], "sensitivity", -1, 1), 0.01, 0.99))
    mask = darkness > cut
    angle = 0.0
    if settings["deskew"]:
        angle = skew_angle(mask)
        if angle:
            mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).rotate(
                angle, resample=Image.Resampling.BILINEAR, expand=True)) > 127
            darkness = np.asarray(Image.fromarray(np.clip(darkness * 255, 0, 255).astype(np.uint8)).rotate(
                angle, resample=Image.Resampling.BILINEAR, expand=True), np.float32) / 255
            rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8)).rotate(
                angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255)), np.float32)
    labels, count = label(mask)
    if count:
        sizes = np.bincount(labels.ravel())
        despeckle = settings["despeckle"]
        minimum = max(6, mask.size * 0.00002) if despeckle == "auto" else finite(despeckle, "despeckle", 0, 1e7)
        keep = sizes >= minimum
        keep[0] = False
        mask = keep[labels]
    weight = int(finite(settings["weight"], "weight", -10, 10))
    if weight > 0:
        mask = dilate(mask, weight)
    elif weight < 0:
        thinned = erode(mask, -weight)
        mask = thinned if thinned.sum() > mask.sum() * 0.2 else mask
    crop = [0, 0, mask.shape[1], mask.shape[0]]
    if settings["crop"] and mask.any():
        ys, xs = np.nonzero(mask)
        margin = int(finite(settings["margin"], "margin", 0, 2000))
        x0, y0 = max(0, xs.min() - margin), max(0, ys.min() - margin)
        x1, y1 = min(mask.shape[1], xs.max() + 1 + margin), min(mask.shape[0], ys.max() + 1 + margin)
        crop = [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]
        mask, darkness, rgb = mask[y0:y1, x0:x1], darkness[y0:y1, x0:x1], rgb[y0:y1, x0:x1]
    if settings["soft"]:
        # Keep the pencil's own grain and anti-aliasing inside (and just around) the lines.
        near = dilate(mask, 1)
        alpha = np.clip((darkness - cut * 0.5) / max(1e-3, (1 - cut * 0.5) * 0.6), 0, 1) * near
        alpha = np.maximum(alpha, mask * 0.85)
    else:
        alpha = mask.astype(np.float32)
    out = np.zeros(mask.shape + (4,), np.uint8)
    if settings["ink"] == "original":
        # Unmix the paper: observed = paper · (1 − a) + ink · a, so the pencil keeps its own
        # colour even where a thin line is mostly paper.
        paper = np.stack([paper_estimate(rgb[..., i]) for i in range(3)], axis=-1)
        a = np.maximum(alpha, 0.25)[..., None]
        out[..., :3] = np.clip((rgb - paper * (1 - a)) / a, 0, 255).astype(np.uint8)
    else:
        out[..., :3] = color(resolve_color(settings["ink"], state or {"variables": {}}))[:3]
    out[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return {"ink": Image.fromarray(out, "RGBA"), "mask": mask, "angle": angle, "crop": crop, "threshold": round(cut, 3),
            "scale": scale}


# ---------------------------------------------------------------------------------------------
# Thinning and tracing


def thin(mask):
    """Zhang–Suen thinning to a one-pixel skeleton."""
    image = np.pad(np.asarray(mask, np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = image[:-2, 1:-1], image[:-2, 2:], image[1:-1, 2:]
            p5, p6, p7 = image[2:, 2:], image[2:, 1:-1], image[2:, :-2]
            p8, p9 = image[1:-1, :-2], image[:-2, :-2]
            neighbours = [p2, p3, p4, p5, p6, p7, p8, p9]
            b = sum(n.astype(np.int32) for n in neighbours)
            sequence = neighbours + [p2]
            a = sum(((sequence[i] == 0) & (sequence[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                c, d = p2 * p4 * p6, p4 * p6 * p8
            else:
                c, d = p2 * p4 * p8, p2 * p6 * p8
            centre = image[1:-1, 1:-1]
            remove = (centre == 1) & (b >= 2) & (b <= 6) & (a == 1) & (c == 0) & (d == 0)
            if remove.any():
                centre[remove] = 0
                changed = True
    return image[1:-1, 1:-1].astype(bool)


NEIGHBOURS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


def trace(skeleton):
    """Polylines along a skeleton: [(points as (x, y) list, closed)]. Paths run between end
    points and junctions; closed loops come back to their start."""
    ys, xs = np.nonzero(skeleton)
    pixels = set(zip(xs.tolist(), ys.tolist()))

    def neighbours(p):
        # m-adjacency: a diagonal neighbour counts only when no orthogonal pixel already links
        # the two, so staircase steps are not mistaken for junctions.
        x, y = p
        found = []
        for dx, dy in NEIGHBOURS:
            q = (x + dx, y + dy)
            if q not in pixels:
                continue
            if dx and dy and ((x + dx, y) in pixels or (x, y + dy) in pixels):
                continue
            found.append(q)
        return found

    degree = {p: len(neighbours(p)) for p in pixels}
    nodes = {p for p, n in degree.items() if n != 2}
    used = set()
    paths = []

    def edge(a, b):
        return (a, b) if a <= b else (b, a)

    def walk(start, nxt):
        path = [start, nxt]
        used.add(edge(start, nxt))
        previous, current = start, nxt
        while current not in nodes:
            options = [q for q in neighbours(current) if q != previous and edge(current, q) not in used]
            if not options:
                break
            # Prefer orthogonal steps so diagonal shortcuts do not skip pixels.
            options.sort(key=lambda q: abs(q[0] - current[0]) + abs(q[1] - current[1]))
            previous, current = current, options[0]
            used.add(edge(previous, current))
            path.append(current)
            if current == start:
                break
        return path

    for node in sorted(nodes):
        for q in neighbours(node):
            if edge(node, q) not in used:
                path = walk(node, q)
                paths.append((path, len(path) > 3 and path[0] == path[-1]))
    for p in sorted(pixels):
        if p in nodes:
            continue
        for q in neighbours(p):
            if edge(p, q) not in used:
                path = walk(p, q)
                paths.append((path, path[0] == path[-1]))
    return paths


def _direction(points, at_start, reach=8):
    p = np.asarray(points, float)
    if len(p) < 2:
        return np.zeros(2)
    if at_start:
        v = p[min(reach, len(p) - 1)] - p[0]
    else:
        v = p[max(-reach - 1, -len(p))] - p[-1]
    n = np.linalg.norm(v)
    return v / n if n else v


def strokes_from_mask(mask, *, min_length=6.0, join_angle=40.0):
    """Centre-line strokes of a line mask: [{"points", "closed", "width"}], with skeleton spurs
    pruned and branches that continue each other through a junction joined into one stroke."""
    from .trace import length

    skeleton = thin(mask)
    depth = distance(mask)
    raw = [(np.asarray(points, float), closed) for points, closed in trace(skeleton) if len(points) >= 2]
    # Width at each skeleton pixel is twice its distance from the edge.
    items = []
    for points, closed in raw:
        widths = depth[points[:, 1].astype(int), points[:, 0].astype(int)] * 2 - 1
        items.append({"points": points, "closed": closed, "width": float(np.median(widths)) if len(widths) else 1.0})
    endpoint_keys = {}
    for index, item in enumerate(items):
        if item["closed"]:
            continue
        for end in (0, -1):
            key = tuple(item["points"][end].astype(int))
            endpoint_keys.setdefault(key, []).append((index, end))
    # Prune short spurs that end in nothing (skeleton noise at line ends and corners).
    pruned = set()
    for index, item in enumerate(items):
        if item["closed"]:
            continue
        ends = [len(endpoint_keys.get(tuple(item["points"][e].astype(int)), [])) for e in (0, -1)]
        if length(item["points"]) < max(min_length, item["width"] * 1.2) and min(ends) == 1 and max(ends) > 1:
            pruned.add(index)
    items = [item for i, item in enumerate(items) if i not in pruned]
    # Join pairs of branches that run straight through a junction.
    changed = True
    while changed:
        changed = False
        ends = {}
        for index, item in enumerate(items):
            if item["closed"]:
                continue
            for end in (0, -1):
                key = tuple(np.round(item["points"][end]).astype(int))
                ends.setdefault(key, []).append((index, end))
        for key, members in ends.items():
            if len(members) < 2:
                continue
            best, pair = None, None
            for i, (a, ea) in enumerate(members):
                for b, eb in members[i + 1:]:
                    if a == b:
                        continue
                    da = _direction(items[a]["points"], ea == 0)
                    db = _direction(items[b]["points"], eb == 0)
                    straightness = float(-(da @ db))  # 1 when they continue each other
                    if straightness > math.cos(math.radians(join_angle)) and (best is None or straightness > best):
                        best, pair = straightness, ((a, ea), (b, eb))
            if pair:
                (a, ea), (b, eb) = pair
                pa = items[a]["points"] if ea == -1 else items[a]["points"][::-1]
                pb = items[b]["points"] if eb == 0 else items[b]["points"][::-1]
                joined = np.vstack([pa, pb[1:]])
                width = (items[a]["width"] * len(pa) + items[b]["width"] * len(pb)) / (len(pa) + len(pb))
                closed = bool(np.allclose(joined[0], joined[-1]) and len(joined) > 8)
                merged = {"points": joined, "closed": closed, "width": width}
                items = [item for i, item in enumerate(items) if i not in (a, b)] + [merged]
                changed = True
                break
    result = []
    for item in items:
        if length(item["points"], item["closed"]) < min_length and not item["closed"]:
            continue
        result.append({**item, "width": max(1.0, round(item["width"], 1))})
    result.sort(key=lambda item: (-length(item["points"], item["closed"])))
    return result


# ---------------------------------------------------------------------------------------------
# Straightening and smoothing


def _fit_line(points):
    p = np.asarray(points, float)
    centre = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - centre)
    direction = vt[0]
    t = (p - centre) @ direction
    deviation = np.abs((p - centre) @ np.array([-direction[1], direction[0]]))
    return centre + direction * t.min(), centre + direction * t.max(), float(deviation.max())


def _fit_circle(points):
    p = np.asarray(points, float)
    a = np.column_stack([2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))])
    b = (p ** 2).sum(axis=1)
    (cx, cy, c), *_ = np.linalg.lstsq(a, b, rcond=None)
    radius = math.sqrt(max(c + cx * cx + cy * cy, 0))
    error = np.abs(np.hypot(p[:, 0] - cx, p[:, 1] - cy) - radius)
    return (float(cx), float(cy)), radius, float(error.max())


def snap_angle(start, end, angles, tolerance):
    """Rotate a segment about its centre onto the nearest allowed angle (degrees, y down)
    within ``tolerance``; returns (start, end, snapped angle or None)."""
    start, end = np.asarray(start, float), np.asarray(end, float)
    v = end - start
    angle = math.degrees(math.atan2(v[1], v[0])) % 180
    best = None
    for target in angles:
        diff = (angle - target % 180 + 90) % 180 - 90
        if abs(diff) <= tolerance and (best is None or abs(diff) < abs(best[1])):
            best = (target % 180, diff)
    if best is None:
        return start, end, None
    centre, half = (start + end) / 2, np.linalg.norm(v) / 2
    theta = math.radians(angle - best[1])
    if v @ np.array([math.cos(theta), math.sin(theta)]) < 0:
        theta += math.pi
    u = np.array([math.cos(theta), math.sin(theta)])
    return centre - u * half, centre + u * half, best[0]


def _rdp_indices(points, tolerance):
    """Indices of the Ramer–Douglas–Peucker vertices of an open polyline."""
    p = np.asarray(points, float)
    keep = np.zeros(len(p), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = p[first], p[last]
        v = b - a
        norm = np.linalg.norm(v)
        inner = p[first + 1:last]
        if norm < 1e-9:
            distances = np.linalg.norm(inner - a, axis=1)
        else:
            distances = np.abs(v[0] * (inner[:, 1] - a[1]) - v[1] * (inner[:, 0] - a[0])) / norm
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            middle = first + 1 + index
            keep[middle] = True
            stack += [(first, middle), (middle, last)]
    return np.nonzero(keep)[0].tolist()


def _line_through(points):
    """(point, unit direction) of the least-squares line through points."""
    p = np.asarray(points, float)
    centre = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - centre)
    return centre, vt[0]


def _meet(line_a, line_b, fallback):
    (p, r), (q, s) = line_a, line_b
    cross = r[0] * s[1] - r[1] * s[0]
    if abs(cross) < 1e-6:
        return fallback
    t = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / cross
    point = p + t * r
    return point if np.linalg.norm(point - fallback) < 200 else fallback


def straighten_stroke(points, closed, *, tolerance, angles, angle_tolerance, circles, corner, polylines=True):
    """A straightened version of one stroke: (points, closed, kind) where kind is ``line``,
    ``polyline``, ``circle`` or None (left as drawn). Each side is fitted to the points drawn
    along it; rounded corners become sharp ones where neighbouring sides meet."""
    from .trace import length

    p = np.asarray(points, float)
    span = length(p, closed)
    if span < 4:
        return p, closed, None
    gap = float(np.linalg.norm(p[0] - p[-1]))
    nearly_closed = not closed and len(p) >= 8 and gap <= 3 * tolerance and span > 12 * tolerance
    if circles and (closed or nearly_closed or gap < span * 0.12) and len(p) >= 12:
        centre, radius, error = _fit_circle(p)
        if radius > 3 and error <= max(tolerance, radius * 0.12):
            angles_ = np.linspace(0, 2 * math.pi, max(24, int(radius / 2)), endpoint=False)
            circle = np.column_stack([centre[0] + radius * np.cos(angles_), centre[1] + radius * np.sin(angles_)])
            return circle, True, "circle"
    a, b, deviation = _fit_line(p)
    if not closed and not nearly_closed and deviation <= max(tolerance, span * 0.015):
        if angles:
            a, b, _ = snap_angle(a, b, angles, angle_tolerance)
        return np.array([a, b]), False, "line"
    if not polylines:
        return p, closed, None
    closed = closed or nearly_closed
    if closed:
        # Start the loop at its sharpest-looking vertex so no side wraps around the seam.
        p = p[:-1] if np.linalg.norm(p[0] - p[-1]) < 1e-6 else p
        seed = _rdp_indices(np.vstack([p, p[:1]]), max(tolerance, 1.5))
        start = seed[len(seed) // 2] % len(p) if len(seed) > 2 else 0
        p = np.roll(p, -start, axis=0)
        p = np.vstack([p, p[:1]])
    indices = _rdp_indices(p, max(tolerance, 1.5))

    def unit(i0, i1):
        v = p[i1] - p[i0]
        return v / max(1e-9, np.linalg.norm(v))

    # One side drawn with a wobble: merge neighbours that turn by less than 8°.
    merged = True
    while merged and len(indices) > 2:
        merged = False
        for k in range(1, len(indices) - 1):
            if unit(indices[k - 1], indices[k]) @ unit(indices[k], indices[k + 1]) > math.cos(math.radians(8)):
                del indices[k]
                merged = True
                break
    edges = list(zip(indices, indices[1:]))
    lengths = [float(np.linalg.norm(p[i1] - p[i0])) for i0, i1 in edges]
    shortest = min(corner, span * 0.08)
    sides = []  # (first index, last index) of each long side
    for k, (i0, i1) in enumerate(edges):
        if lengths[k] < shortest:
            continue
        neighbours = [m % len(edges) for m in (k - 1, k + 1)] if closed else [m for m in (k - 1, k + 1) if 0 <= m < len(edges)]
        if len(neighbours) == 2:
            a, c = neighbours
            d0, d1, d2 = unit(*edges[a]), unit(i0, i1), unit(*edges[c])
            turn1 = d0[0] * d1[1] - d0[1] * d1[0]
            turn2 = d1[0] * d2[1] - d1[1] * d2[0]
            # A short side whose two turns go the same way is a rounded corner, not a side
            # (a staircase alternates its turns and keeps its steps).
            if turn1 * turn2 > 0 and lengths[k] < 0.25 * min(lengths[a], lengths[c]) and lengths[k] < 3 * corner:
                continue
        sides.append((i0, i1))
    if len(sides) < (3 if closed else 1) or len(sides) > max(3, len(p) // 3):
        return p[:-1] if closed else p, closed, None
    lines = []
    for i0, i1 in sides:
        centre, direction = _line_through(p[i0:i1 + 1])
        if angles:
            reach = np.linalg.norm(p[i1] - p[i0]) / 2
            s2, e2, _ = snap_angle(centre - direction * reach, centre + direction * reach, angles, angle_tolerance)
            direction = (e2 - s2) / max(1e-9, np.linalg.norm(e2 - s2))
        lines.append((centre, direction))
    out = []
    count = len(lines)
    if not closed:
        centre, direction = lines[0]
        out.append(centre + direction * ((p[0] - centre) @ direction))
    for i in range(count if closed else count - 1):
        j = (i + 1) % count
        fallback = (p[sides[i][1]] + p[sides[j][0]]) / 2
        out.append(_meet(lines[i], lines[j], fallback))
    if not closed:
        centre, direction = lines[-1]
        out.append(centre + direction * ((p[-1] - centre) @ direction))
    return np.asarray(out, float), closed, "polyline"


def _intersect(s1, s2):
    p, r = s1[0], s1[1] - s1[0]
    q, s = s2[0], s2[1] - s2[0]
    cross = r[0] * s[1] - r[1] * s[0]
    if abs(cross) < 1e-9:
        return (s1[1] + s2[0]) / 2
    t = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / cross
    point = p + t * r
    # A nearly parallel pair can meet far away; then keep the drawn joint.
    if np.linalg.norm(point - s1[1]) > np.linalg.norm(r) + np.linalg.norm(s):
        return (s1[1] + s2[0]) / 2
    return point


def close_gaps(strokes, gap):
    """Extend open stroke ends to meet a nearby end (or a stroke body) within ``gap`` pixels.
    Returns the number of joins."""
    joins = 0
    ends = []
    for index, stroke in enumerate(strokes):
        if stroke["closed"] or len(stroke["points"]) < 2:
            continue
        for end in (0, -1):
            ends.append((index, end))
    taken = set()
    for i, (a, ea) in enumerate(ends):
        if (a, ea) in taken:
            continue
        pa = strokes[a]["points"][ea]
        best = None
        for b, eb in ends[i + 1:]:
            if (b, eb) in taken or (a == b and len(strokes[a]["points"]) < 4):
                continue
            pb = strokes[b]["points"][eb]
            d = float(np.linalg.norm(pa - pb))
            if 0 < d <= gap and (best is None or d < best[0]):
                best = (d, b, eb)
        if best:
            _, b, eb = best
            middle = (pa + strokes[b]["points"][eb]) / 2
            for index, end in ((a, ea), (b, eb)):
                points = strokes[index]["points"]
                strokes[index]["points"] = np.vstack([middle[None], points]) if end == 0 else np.vstack([points, middle[None]])
                taken.add((index, end))
            if a == b:
                strokes[a]["closed"] = True
            joins += 1
    return joins


# ---------------------------------------------------------------------------------------------
# Regions


def regions(mask, gap=4, min_area=64):
    """Regions enclosed by the lines: (labels, info) where info lists each region's id, area,
    bounding box and an interior point. ``gap`` closes small breaks in the outlines first; the
    region touching the image border is the outside."""
    closed = dilate(mask, gap)
    labels, count = label(~closed)
    info = []
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    for index in range(1, count + 1):
        ys, xs = np.nonzero(labels == index)
        if len(xs) < min_area:
            continue
        depth = distance(labels[ys.min():ys.max() + 1, xs.min():xs.max() + 1] == index, limit=32)
        iy, ix = np.unravel_index(int(np.argmax(depth)), depth.shape)
        info.append({"id": index, "area": int(len(xs)), "box": [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
                     int(ys.max() - ys.min() + 1)], "point": [int(xs.min() + ix), int(ys.min() + iy)],
                     "outside": index in border})
    return labels, info


# ---------------------------------------------------------------------------------------------
# Document model
#
# The drawing group's content space is the cleaned image's pixel grid. Its record:
#   group["drawing"] = {"source": asset of the photo as imported, "reference": asset of the
#   cleaned line mask (what preservation is measured against), "settings": clean settings,
#   "angle", "crop", "scale", "ink": ink colour}
# Stroke layers are path shapes carrying "drawing_strokes": [{"points", "closed", "width",
# "smooth", "origin": traced|added, "kind": None|line|polyline|circle|smoothed}] in content
# coordinates.


def schemas(add):
    from .schema import S

    add("drawing", {"action": {"enum": list(ACTIONS)}, "name": S, "target": S, "asset": S, "path": S, "x": {}, "y": {},
                    "width": {}, "height": {}, "settings": {"type": "object"},
                    "strokes": {"type": ["array", "string"], "items": S}, "points": {"type": "array"}, "color": S},
        ["action"])


def _group(project, target):
    group = project.layer(target)
    if group.get("parent") and "drawing" not in group:
        parent = project.layer(group["parent"])
        if "drawing" in parent:
            group = parent
    require(group["type"] == "group" and "drawing" in group,
            f"{group['name']!r} is not a drawing; import one with drawing import", field="target")
    return group


def _children(project, group):
    return [layer for layer in project.state["layers"] if layer.get("parent") == group["id"]]


def _child(project, group, role):
    return next((layer for layer in _children(project, group) if layer.get("drawing_role") == role), None)


def _settings(value, defaults):
    value = value or {}
    require(isinstance(value, dict), "settings must be an object", field="settings")
    unknown = sorted(set(value) - set(defaults))
    require(not unknown, f"Unknown setting(s) {unknown}; available: {', '.join(sorted(defaults))}", field="settings")
    return {**defaults, **value}


def _source_image(project, op):
    from .assets import add_encoded, read_bounded

    if op.get("asset"):
        return op["asset"], project.image(op["asset"])
    require(op.get("path"), "drawing import needs an image: asset (from an import) or path", field="asset")
    from pathlib import Path

    data = read_bounded(Path(op["path"]).resolve(), project.limits.max_asset_bytes)
    asset, image = add_encoded(project, data)
    return asset, image


def _aligned_photo(image, result):
    """The photo rotated and cropped exactly like the cleaned lines, for comparison."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    if result["scale"] < 1:
        image = image.resize((max(1, round(image.width * result["scale"])), max(1, round(image.height * result["scale"]))),
                             Image.Resampling.LANCZOS)
    if result["angle"]:
        image = image.rotate(result["angle"], resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    x, y, w, h = result["crop"]
    return image.crop((x, y, x + w, y + h))


def _insert(project, layer, before=None):
    """Append a layer (or insert it just before ``before``) and make it active."""
    from .operations import append_layer

    append_layer(project, layer)
    if before is not None:
        layers = project.state["layers"]
        layers.remove(layer)
        layers.insert(layers.index(before), layer)
    return layer


def _content_matrix(project, group):
    """3×3 matrix from the drawing's content coordinates to the canvas."""
    from .checks import group_matrix
    from .render import resolve_layout, resolved_layers

    layers = resolved_layers(project)
    resolved = {item["id"]: item for item in layers}
    local = resolve_layout(project, layers=layers)
    child = next((item for item in layers if item.get("parent") == group["id"]), None)
    require(child is not None, "The drawing is empty", field="target")
    return group_matrix(child, resolved, local)


def _to_content(project, group, points):
    matrix = np.linalg.inv(_content_matrix(project, group))
    p = np.asarray(points, float)
    require(p.ndim == 2 and p.shape[1] >= 2 and len(p) <= 20000, "points are [[x, y], …] canvas positions", field="points")
    homogeneous = np.column_stack([p[:, :2], np.ones(len(p))])
    return (matrix @ homogeneous.T).T[:, :2]


def stroke_layer(name, records, color, width=None):
    """A path shape drawing ``records`` (content coordinates), boxed around them."""
    from .trace import path_data

    widths = [r["width"] for r in records]
    stroke_width = float(width if width is not None else np.median(widths))
    pad = stroke_width / 2 + 2
    allpoints = np.vstack([np.asarray(r["points"], float) for r in records])
    x0, y0 = np.floor(allpoints.min(axis=0) - pad)
    x1, y1 = np.ceil(allpoints.max(axis=0) + pad)
    w, h = int(max(1, x1 - x0)), int(max(1, y1 - y0))
    parts = []
    for r in records:
        local = np.asarray(r["points"], float) - [x0, y0]
        if len(local) == 1:
            local = np.vstack([local, local + [0.01, 0]])
        parts.append(path_data(local, r["closed"], r.get("smooth", True)))
    layer = new_layer(name, "shape", w, h, shape="path", path=" ".join(parts), path_view=[w, h], fill="transparent",
                      stroke=color, stroke_width=round(stroke_width, 2), line_cap="round", x=float(x0), y=float(y0))
    layer["drawing_strokes"] = [{**r, "points": np.round(np.asarray(r["points"], float), 2).tolist()} for r in records]
    return layer


def _rebuild(layer, records):
    fresh = stroke_layer(layer["name"], records, layer.get("stroke", "#1d1d1f"),
                         layer["stroke_width"] if len(records) > 1 else None)
    for key in ("path", "path_view", "width", "height", "x", "y", "stroke_width", "drawing_strokes"):
        layer[key] = fresh[key]


def _records(project, group, strokes):
    layers = [layer for layer in _children(project, group) if "drawing_strokes" in layer]
    require(layers, "The drawing has no strokes yet; run drawing vectorize first", field="target")
    if strokes in (None, "all"):
        return layers
    require(isinstance(strokes, list), "strokes is 'all' or a list of stroke layer names", field="strokes")
    wanted = {project.layer(name)["id"] for name in strokes}
    chosen = [layer for layer in layers if layer["id"] in wanted]
    require(len(chosen) == len(wanted), "strokes must name stroke layers of this drawing", field="strokes")
    return chosen


def _guide_angles(project):
    from .guides import angle_of

    angles = set()
    for guide in project.state.get("guides", {}).values():
        try:
            angle = angle_of(guide)
        except Exception:  # noqa: BLE001 - guides without a direction (points, circles) add none
            angle = None
        if angle is not None:
            angles.add(round(float(angle) % 180, 3))
    return sorted(angles)


def execute(project, op):
    action = op["action"]
    require(action in ACTIONS, f"action must be one of {', '.join(ACTIONS)}", field="action")
    if action == "import":
        return _import(project, op)
    group = _group(project, op.get("target") or op.get("name"))
    if action == "clean":
        return _clean(project, group, op)
    if action == "vectorize":
        return _vectorize(project, group, op)
    if action in ("straighten", "smooth"):
        return _straighten(project, group, op, action)
    if action == "fill":
        return _fill(project, group, op)
    if action == "stroke":
        return _add_stroke(project, group, op)
    return _restyle(project, group, op)


def _import(project, op):
    from .assets import add_image
    from .operations import default_name, unique_name

    settings = _settings(op.get("settings"), CLEAN)
    source, image = _source_image(project, op)
    result = clean(image, settings, project.state)
    require(result["mask"].any(), "No lines found in the image; try a higher sensitivity", field="settings")
    name = unique_name(project, op["name"]) if "name" in op else default_name(project, "drawing")
    ink_asset = add_image(project, result["ink"])
    photo = add_image(project, _aligned_photo(image, result).convert("RGBA"))
    reference = add_image(project, Image.fromarray(result["mask"].astype(np.uint8) * 255, "L"), "masks")
    cw, ch = result["ink"].size
    c = project.state["canvas"]
    if "width" in op or "height" in op:
        width = op.get("width") or round(op["height"] * cw / ch)
        height = op.get("height") or round(op["width"] * ch / cw)
    else:
        fit = min(1.0, c["width"] * 0.9 / cw, c["height"] * 0.9 / ch)
        width, height = max(1, round(cw * fit)), max(1, round(ch * fit))
    x = op.get("x", (c["width"] - width) / 2)
    y = op.get("y", (c["height"] - height) / 2)
    original = new_layer(f"{name}/original", "raster", cw, ch, asset=photo, provenance={"type": "imported"}, visible=False)
    original["drawing_role"] = "original"
    ink = new_layer(f"{name}/ink", "raster", cw, ch, asset=ink_asset, provenance={"type": "generated"})
    ink["drawing_role"] = "ink"
    group = new_layer(name, "group", int(width), int(height), x=finite(x, "x"), y=finite(y, "y"),
                      content_width=cw, content_height=ch, role="content")
    group["drawing"] = {"source": source, "reference": reference, "settings": settings, "angle": result["angle"],
                        "crop": result["crop"], "scale": result["scale"]}
    for child in (original, ink):
        child["parent"] = group["id"]
        _insert(project, child)
    _insert(project, group)


def _clean(project, group, op):
    from .assets import add_image

    record = group["drawing"]
    settings = _settings({**record["settings"], **(op.get("settings") or {})}, CLEAN)
    image = project.image(record["source"])
    result = clean(image, settings, project.state)
    strokes = [layer for layer in _children(project, group) if "drawing_strokes" in layer or layer.get("drawing_role") == "fill"]
    geometry_changed = (result["angle"], result["crop"]) != (record["angle"], record["crop"])
    if geometry_changed and strokes:
        # Keep strokes and fills aligned: clean again in the drawing's existing frame.
        result = clean_in_frame(image, settings, record, project.state)
    require(result["mask"].any(), "No lines found with these settings", field="settings")
    ink = _child(project, group, "ink")
    original = _child(project, group, "original")
    ink["asset"] = add_image(project, result["ink"])
    record.update(settings=settings, reference=add_image(project, Image.fromarray(result["mask"].astype(np.uint8) * 255, "L"),
                                                         "masks"))
    if not (geometry_changed and strokes):
        cw, ch = result["ink"].size
        sx, sy = group["width"] / group["content_width"], group["height"] / group["content_height"]
        original["asset"] = add_image(project, _aligned_photo(image, result).convert("RGBA"))
        for layer in (ink, original):
            layer["width"], layer["height"] = cw, ch
        group.update(content_width=cw, content_height=ch, width=max(1, round(cw * sx)), height=max(1, round(ch * sy)))
        record.update(angle=result["angle"], crop=result["crop"], scale=result["scale"])


def clean_in_frame(image, settings, record, state):
    """Clean with the drawing's stored tilt and crop (so existing strokes stay aligned)."""
    result = clean(image, {**settings, "deskew": False, "crop": False}, state)
    angle, (x, y, w, h) = record["angle"], record["crop"]
    ink, mask = result["ink"], result["mask"]
    if angle:
        ink = ink.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
        mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).rotate(angle, expand=True)) > 127
    ink = ink.crop((x, y, x + w, y + h))
    mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).crop((x, y, x + w, y + h))) > 127
    return {**result, "ink": ink, "mask": mask, "angle": angle, "crop": record["crop"]}


VECTORIZE = {"mode": "centerline", "min_length": 6, "detail": 0.75, "max_strokes": MAX_STROKES, "keep_ink": False,
             "color": None}


def _vectorize(project, group, op):
    from .trace import mask_contours, elements_path, simplify

    settings = _settings(op.get("settings"), VECTORIZE)
    require(settings["mode"] in ("centerline", "outline"), "mode is centerline or outline", field="settings")
    record = group["drawing"]
    mask = np.asarray(project.image(record["reference"], "L")) > 127
    ink = _child(project, group, "ink")
    color = settings["color"] or op.get("color") or record["settings"].get("ink", "#1d1d1f")
    if color == "original":
        color = "#1d1d1f"
    for layer in [layer for layer in _children(project, group) if "drawing_strokes" in layer or layer.get("drawing_role") == "lines"]:
        project.state["layers"].remove(layer)
    name = group["name"]
    if settings["mode"] == "outline":
        loops = mask_contours(mask, smooth=0.6, tolerance=float(settings["detail"]))
        require(loops, "No lines to trace", field="target")
        cw, ch = group["content_width"], group["content_height"]
        layer = new_layer(f"{name}/lines", "shape", cw, ch, shape="path", fill=color, stroke="transparent",
                          path=elements_path([{"points": loop, "closed": True, "smooth": False} for loop in loops]), path_view=[cw, ch])
        layer.update(parent=group["id"], drawing_role="lines")
        _insert(project, layer, before=group)
    else:
        strokes = strokes_from_mask(mask, min_length=float(settings["min_length"]))
        require(strokes, "No lines to trace", field="target")
        limit = int(finite(settings["max_strokes"], "max_strokes", 1, MAX_STROKES))
        records = [{"points": simplify(s["points"], float(settings["detail"]), s["closed"]), "closed": s["closed"],
                    "width": s["width"], "smooth": True, "origin": "traced"} for s in strokes]
        main, rest = (records[:limit - 1], records[limit - 1:]) if len(records) > limit else (records, [])
        for index, item in enumerate(main, 1):
            layer = stroke_layer(f"{name}/s{index:03d}", [item], color)
            layer["parent"] = group["id"]
            _insert(project, layer, before=group)
        if rest:
            layer = stroke_layer(f"{name}/detail", rest, color)
            layer["parent"] = group["id"]
            _insert(project, layer, before=group)
    if not settings["keep_ink"]:
        ink["visible"] = False
    project.state["active_layer"] = group["id"]


STRAIGHTEN = {"tolerance": 4.0, "angles": [0, 45, 90, 135], "angle_tolerance": 6.0, "circles": True, "close_gaps": 0.0,
              "corner": 24.0, "polylines": True, "amount": 0.5}


def _straighten(project, group, op, action):
    from .trace import chaikin

    settings = _settings(op.get("settings"), STRAIGHTEN)
    layers = _records(project, group, op.get("strokes", "all"))
    angles = settings["angles"]
    if angles == "guides":
        angles = _guide_angles(project)
        require(angles, "The document has no angled guides to snap to", field="settings")
    elif angles in (None, "none", False):
        angles = []
    require(isinstance(angles, list) and len(angles) <= 64, "angles is a list of degrees, 'guides' or 'none'", field="settings")
    angles = [finite(a, "angle") for a in angles]
    if action == "straighten" and settings["close_gaps"]:
        records = [r for layer in layers for r in layer["drawing_strokes"]]
        arrays = [{**r, "points": np.asarray(r["points"], float)} for r in records]
        close_gaps(arrays, finite(settings["close_gaps"], "close_gaps", 0, 1000))
        for r, a in zip(records, arrays):
            r["points"], r["closed"] = a["points"].tolist(), a["closed"]
    for layer in layers:
        updated = []
        for record in layer["drawing_strokes"]:
            points = np.asarray(record["points"], float)
            if action == "smooth":
                amount = finite(settings["amount"], "amount", 0, 1)
                passes = max(1, round(amount * 4))
                smoothed = chaikin(points, passes, record["closed"])
                if not record["closed"] and len(points) > 2:
                    smoothed = np.vstack([points[:1], smoothed, points[-1:]])
                from .trace import simplify

                smoothed = simplify(smoothed, 0.5, record["closed"])
                updated.append({**record, "points": smoothed.tolist(), "kind": "smoothed", "smooth": True})
                continue
            new, closed, kind = straighten_stroke(points, record["closed"], tolerance=finite(settings["tolerance"], "tolerance", 0, 1000),
                                                  angles=angles, angle_tolerance=finite(settings["angle_tolerance"], "angle_tolerance", 0, 45),
                                                  circles=bool(settings["circles"]), corner=finite(settings["corner"], "corner", 0, 10000),
                                                  polylines=bool(settings["polylines"]))
            if kind is None:
                updated.append(record)
            else:
                updated.append({**record, "points": np.asarray(new).tolist(), "closed": closed, "kind": kind,
                                "smooth": kind == "circle"})
        _rebuild(layer, updated)


FILL = {"gap": 6.0, "min_area": 64, "under": True}


def _fill(project, group, op):
    from .design import resolve_color
    from .render import color as rgba
    from .trace import elements_path, mask_contours

    settings = _settings(op.get("settings"), FILL)
    points = op.get("points")
    require(isinstance(points, list) and 1 <= len(points) <= 64,
            "fill takes points: [[x, y, color], …] (canvas positions inside the regions to colour)", field="points")
    mask = line_mask(project, group)
    gap = int(finite(settings["gap"], "gap", 0, 200))
    labels, info = regions(mask, gap, int(settings["min_area"]))
    content = _to_content(project, group, [p[:2] for p in points])
    count = len([layer for layer in _children(project, group) if layer.get("drawing_role") == "fill"])
    anchor = next((layer for layer in _children(project, group) if layer.get("drawing_role") in ("ink", "lines")
                   or "drawing_strokes" in layer), group)
    for (x, y), point in zip(content, points):
        require(len(point) >= 3 and isinstance(point[2], str), "Each point is [x, y, color]", field="points")
        rgba(resolve_color(point[2], project.state))
        xi, yi = int(round(x)), int(round(y))
        require(0 <= xi < labels.shape[1] and 0 <= yi < labels.shape[0], f"Point {point[:2]} is outside the drawing",
                field="points")
        region = labels[yi, xi]
        require(region and any(i["id"] == region for i in info), f"Point {point[:2]} is on a line, not inside a region; "
                "pick a point inside the shape (drawing report lists region points)", field="points")
        require(not next(i for i in info if i["id"] == region)["outside"], f"Point {point[:2]} is outside every closed "
                "shape (the lines do not enclose it; raise settings.gap to bridge small breaks)", field="points")
        strokes = [r["width"] for layer in _children(project, group) for r in layer.get("drawing_strokes", [])]
        area = grow_region(labels, region, mask, gap, (float(np.median(strokes)) / 2 + 1) if strokes else 3)
        loops = mask_contours(area, smooth=0.8, tolerance=0.8)
        count += 1
        cw, ch = group["content_width"], group["content_height"]
        layer = new_layer(f"{group['name']}/fill-{count}", "shape", cw, ch, shape="path", path_view=[cw, ch],
                          path=elements_path([{"points": loop, "closed": True, "smooth": False} for loop in loops]), fill=point[2],
                          stroke="transparent")
        layer.update(parent=group["id"], drawing_role="fill")
        _insert(project, layer, before=anchor if settings["under"] else group)


def grow_region(labels, region, lines, gap, width=3):
    """Grow region ``region`` of ``labels`` (found with gaps bridged) back out to its lines.
    Every region grows through the non-line pixels at once, so neighbours meet halfway across
    a bridged gap while each still fills its own corners; the edge is then tucked under the
    lines (never past them)."""
    ys, xs = np.nonzero(labels == region)
    if not len(xs):
        return labels == region
    margin = 3 * gap + 12
    y0, y1 = max(0, ys.min() - margin), min(labels.shape[0], ys.max() + margin + 1)
    x0, x1 = max(0, xs.min() - margin), min(labels.shape[1], xs.max() + margin + 1)
    grid = labels[y0:y1, x0:x1].copy()
    free = ~lines[y0:y1, x0:x1]
    grid[~free] = 0
    for _ in range(margin):
        empty = (grid == 0) & free
        if not empty.any():
            break
        before = int(empty.sum())
        for axis, step in ((0, 1), (0, -1), (1, 1), (1, -1)):
            shifted = np.roll(grid, step, axis=axis)
            if axis == 0:
                shifted[0 if step == 1 else -1, :] = 0
            else:
                shifted[:, 0 if step == 1 else -1] = 0
            take = empty & (shifted > 0)
            grid[take] = shifted[take]
            empty &= ~take
        if int(empty.sum()) == before:
            break
    grown = grid == region
    grown |= dilate(grown, max(1, int(round(width)))) & ~free
    result = np.zeros(labels.shape, bool)
    result[y0:y1, x0:x1] = grown
    return result


def line_mask(project, group):
    """The drawing's current lines in content coordinates (strokes, outline paths and visible ink)."""
    from PIL import ImageDraw

    cw, ch = group["content_width"], group["content_height"]
    canvas = Image.new("L", (cw, ch))
    draw = ImageDraw.Draw(canvas)
    for layer in _children(project, group):
        if not layer["visible"]:
            continue
        if "drawing_strokes" in layer:
            for record in layer["drawing_strokes"]:
                pts = [tuple(p) for p in np.asarray(record["points"], float)]
                if record["closed"] and len(pts) > 2:
                    pts.append(pts[0])
                width = max(1, round(record["width"]))
                if len(pts) >= 2:
                    draw.line(pts, fill=255, width=width, joint="curve")
                for px, py in (pts[0], pts[-1]):
                    draw.ellipse([px - width / 2, py - width / 2, px + width / 2, py + width / 2], fill=255)
        elif layer.get("drawing_role") in ("ink", "lines"):
            from .render import layer_image

            image = layer_image(project, layer, (0, 0, cw, ch)) if layer.get("drawing_role") == "lines" else project.image(layer["asset"])
            alpha = image.convert("RGBA").getchannel("A").resize((cw, ch))
            canvas.paste(255, mask=alpha.point(lambda a: 255 if a > 96 else 0))
    return np.asarray(canvas) > 127


STROKE = {"width": None, "smooth": True, "closed": False}


def _add_stroke(project, group, op):
    settings = _settings(op.get("settings"), STROKE)
    content = _to_content(project, group, op.get("points") or [])
    require(len(content) >= 2, "stroke needs at least two points", field="points")
    existing = [r for layer in _children(project, group) for r in layer.get("drawing_strokes", [])]
    width = settings["width"] or (float(np.median([r["width"] for r in existing])) if existing else 4.0)
    color = op.get("color") or next((layer.get("stroke") for layer in _children(project, group) if "drawing_strokes" in layer),
                                    group["drawing"]["settings"].get("ink", "#1d1d1f"))
    if color == "original":
        color = "#1d1d1f"
    count = 1 + sum(1 for layer in _children(project, group) if layer["name"].startswith(f"{group['name']}/added"))
    name = op.get("name") or f"{group['name']}/added-{count}"
    record = {"points": content.tolist(), "closed": bool(settings["closed"]), "width": finite(width, "width", 0.5, 500),
              "smooth": bool(settings["smooth"]), "origin": "added"}
    layer = stroke_layer(name, [record], color)
    layer["parent"] = group["id"]
    _insert(project, layer, before=group)


def _restyle(project, group, op):
    settings = _settings(op.get("settings"), {"width": None, "width_scale": None})
    layers = _records(project, group, op.get("strokes", "all"))
    for layer in layers:
        if op.get("color"):
            from .design import resolve_color
            from .render import color

            color(resolve_color(op["color"], project.state))
            layer["stroke"] = op["color"]
        records = layer["drawing_strokes"]
        if settings["width"] is not None or settings["width_scale"] is not None:
            for record in records:
                record["width"] = (finite(settings["width"], "width", 0.5, 500) if settings["width"] is not None
                                   else record["width"] * finite(settings["width_scale"], "width_scale", 0.05, 20))
            layer["stroke_width"] = float(np.median([r["width"] for r in records]))
        _rebuild(layer, records)


# ---------------------------------------------------------------------------------------------
# Validation, reports and checks


def validate(layer, state, project):
    if "drawing" in layer:
        record = layer["drawing"]
        require(isinstance(record, dict) and layer["type"] == "group", "Invalid drawing record", "invalid_project")
        for key in ("source", "reference"):
            require(record.get(key) in project.assets, "Missing drawing asset", "missing_asset")
    if "drawing_strokes" in layer:
        records = layer["drawing_strokes"]
        require(layer["type"] == "shape" and isinstance(records, list) and 1 <= len(records) <= 5000,
                "Invalid drawing strokes", "invalid_project")
        total = 0
        for record in records:
            require(isinstance(record, dict) and isinstance(record.get("points"), list) and record["points"],
                    "Invalid drawing stroke", "invalid_project")
            total += len(record["points"])
            finite(record.get("width", 1), "stroke width", 0.1, 1000)
        require(total <= 200000, "Drawing strokes hold too many points", "resource_limit")


def report(project, target):
    """Preservation of the original line work, strokes and regions of a drawing."""
    group = _group(project, target)
    reference = np.asarray(project.image(group["drawing"]["reference"], "L")) > 127
    current = line_mask(project, group)
    strokes = [r for layer in _children(project, group) for r in layer.get("drawing_strokes", [])]
    widths = [r["width"] for r in strokes] or [3.0]
    tolerance = max(2, int(round(float(np.median(widths)))))
    covered = reference & dilate(current, tolerance)
    added = current & ~dilate(reference, tolerance)
    preserved = float(covered.sum() / max(1, reference.sum()))
    new = float(added.sum() / max(1, current.sum()))
    _, info = regions(current, 6)
    matrix = _content_matrix(project, group)

    def canvas(point):
        x, y, _ = matrix @ np.array([point[0], point[1], 1.0])
        return [round(float(x), 1), round(float(y), 1)]

    kinds = {}
    for r in strokes:
        kinds[r.get("kind") or r.get("origin", "traced")] = kinds.get(r.get("kind") or r.get("origin", "traced"), 0) + 1
    return {
        "drawing": group["name"], "preserved": round(preserved, 4), "added": round(new, 4), "tolerance_px": tolerance,
        "strokes": len(strokes), "stroke_kinds": kinds,
        "regions": [{"id": i["id"], "area": i["area"], "point": canvas(i["point"])} for i in info if not i["outside"]][:64],
        "fills": [layer["name"] for layer in _children(project, group) if layer.get("drawing_role") == "fill"],
        "tilt_corrected": group["drawing"]["angle"],
    }


def compare(project, target, max_size=1600):
    """The original lines (red) under the current drawing (dark blue); purple where they agree."""
    group = _group(project, target)
    reference = np.asarray(project.image(group["drawing"]["reference"], "L")) > 127
    current = line_mask(project, group)
    image = np.full(reference.shape + (3,), 255, np.uint8)
    image[reference] = (235, 90, 90)
    image[current] = (40, 60, 160)
    image[reference & current] = (110, 40, 120)
    result = Image.fromarray(image, "RGB")
    if max(result.size) > max_size:
        result.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return result


def check_drawings(candidate, layers, issue):
    """The ``drawing`` check: each drawing still covers its original lines."""
    for item in layers:
        if item["type"] != "group" or "drawing" not in item:
            continue
        info = report(candidate, item["id"])
        if info["preserved"] < 0.9:
            issue("drawing", "warning" if info["preserved"] >= 0.7 else "error",
                  f"Drawing {item['name']!r} keeps {info['preserved']:.0%} of the original lines; compare it with "
                  "drawing compare and restore or redraw what was lost", [item], preserved=info["preserved"])
        if info["added"] > 0.35:
            issue("drawing", "warning", f"{info['added']:.0%} of drawing {item['name']!r} is new line work", [item],
                  added=info["added"])


# ---------------------------------------------------------------------------------------------
# AI colouring


def line_art(project, group):
    """The drawing as drawn so far (fills and lines, no AI colour) on white, in content pixels."""
    from .render import render_layers

    cw, ch = group["content_width"], group["content_height"]
    view = project.clone()
    view._disk_cache = None
    for layer in view.state["layers"]:
        if layer.get("parent") == group["id"] and layer.get("drawing_role") == "color":
            layer["visible"] = False
    art = render_layers(view, parent=group["id"], size=(cw, ch))
    base = Image.new("RGBA", (cw, ch), "white")
    base.alpha_composite(art)
    return base.convert("RGB")


def ai_color(project, target, prompt, backend, *, strength=0.6, seed=None, model=None):
    """Colour and shade the drawing with an image-to-image provider. The result is a layer
    under the drawing's own lines and fills, so every line stays exactly as drawn."""
    from .ai import generate
    from .assets import add_image

    group = _group(project, target)
    require(isinstance(prompt, str) and prompt.strip(), "Describe the colouring with a prompt", field="prompt")
    candidate = project.clone()
    group = candidate.layer(group["id"])
    cw, ch = group["content_width"], group["content_height"]
    request = {"mode": "img2img", "prompt": prompt.strip() + ". Keep every line of the drawing exactly where it is; "
               "colour and shade the shapes the lines describe.", "strength": finite(strength, "strength", 0, 1),
               "seed": seed, "model": model, "width": cw, "height": ch,
               "source_asset": add_image(candidate, line_art(candidate, group))}
    name = f"{group['name']}/color"
    for layer in [x for x in candidate.state["layers"] if x["name"] == name]:
        candidate.state["layers"].remove(layer)
    result = generate(candidate, request, backend, name=name)
    layer = candidate.layer(result["layer"])
    layer.update(parent=group["id"], x=0, y=0, width=cw, height=ch, drawing_role="color")
    layers = candidate.state["layers"]
    layers.remove(layer)
    original = _child(candidate, group, "original")
    layers.insert(layers.index(original) + 1 if original in layers else layers.index(group), layer)
    from .validation import check_state

    check_state(candidate, candidate.state)
    if candidate.transaction is None:
        candidate._amend_head()
    project.__dict__.update(candidate.__dict__)
    return result


# ---------------------------------------------------------------------------------------------
# CLI


def compile_command(cmd, args):
    if cmd != "drawing":
        return None
    import json

    from .commands import Parser

    p = Parser(prog="vixl drawing", description="import FILE | clean | vectorize | straighten | smooth | fill | stroke | "
               "restyle (report and compare are document commands)")
    p.add_argument("action", choices=list(ACTIONS))
    p.add_argument("source", nargs="?", help="import: the image file; otherwise the drawing")
    p.add_argument("--name")
    p.add_argument("--target")
    for key in ("x", "y", "width", "height"):
        p.add_argument("--" + key, type=float)
    p.add_argument("--settings", type=json.loads, help="JSON settings object")
    p.add_argument("--strokes", help="Comma-separated stroke layers (default: all)")
    p.add_argument("--points", type=json.loads, help="JSON points: [[x, y], …] (fill: [[x, y, color], …])")
    p.add_argument("--color")
    a = vars(p.parse_args(args))
    op = {"type": "drawing", "action": a.pop("action")}
    source = a.pop("source")
    if op["action"] == "import":
        require(source, "drawing import needs an image file", field="path")
        op["path"] = source
    elif source:
        op["target"] = source
    if a.get("strokes"):
        a["strokes"] = [s.strip() for s in a["strokes"].split(",") if s.strip()]
    for key in ("x", "y", "width", "height"):
        if isinstance(a.get(key), float) and a[key].is_integer():
            a[key] = int(a[key])
    return {**op, **{k: v for k, v in a.items() if v is not None}}
