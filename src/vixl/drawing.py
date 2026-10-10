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
from .gaps import close_gaps
from .geometry import bezier_points
from .model import finite, new_layer

DEFAULT_INK = "#1d1d1f"  # near-black, a printed pen line; set `ink` on import (or `color` on vectorize/restyle) for pure black
TYPES = ("drawing",)
ACTIONS = ("import", "clean", "vectorize", "straighten", "smooth", "fill", "stroke", "restyle")
CLEAN = {"threshold": "auto", "sensitivity": 0.0, "despeckle": "auto", "weight": 0, "deskew": True, "crop": True,
         "margin": 24, "soft": True, "ink": DEFAULT_INK, "flatten": True, "max_size": 2400, "sheet": True,
         "perspective": True}
MAX_STROKES = 240


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
    """Euclidean distance (pixels) from each mask pixel to the nearest background pixel, up to
    ``limit``. Exact, so a diagonal line reads as wide as a straight one drawn with the same pen
    (a chessboard distance reads it about 30% thinner). One pass finds the distance along each
    row; the nearest background pixel in any row then follows from the rows above and below."""
    mask = np.asarray(mask, bool)
    result = np.zeros(mask.shape, np.float32)
    if not mask.any():
        return result
    columns = np.arange(mask.shape[1])[None, :]
    near = np.maximum.accumulate(np.where(mask, -(10 ** 6), columns), axis=1)
    far = np.minimum.accumulate(np.where(mask, 10 ** 6, columns)[:, ::-1], axis=1)[:, ::-1]
    along = np.minimum(columns - near, far - columns).astype(np.float32)
    squared = np.minimum(along, limit + 1) ** 2
    best = squared.copy()
    for rows in range(1, int(min(limit, np.sqrt(squared[mask].max()))) + 1):
        cost = np.float32(rows * rows)
        np.minimum(best[rows:], squared[:-rows] + cost, out=best[rows:])
        np.minimum(best[:-rows], squared[rows:] + cost, out=best[:-rows])
    result[mask] = np.minimum(np.sqrt(best[mask]), limit)
    return result


def flatten_paper(gray, sheet=None):
    """Divide out the paper's lighting: an estimate of the blank page (ink removed by a max
    filter, then blurred) becomes 1.0, so shadows and gradients disappear."""
    return np.clip(gray / np.maximum(paper_estimate(gray, sheet), 1.0), 0, 1)


def paper_estimate(gray, sheet=None):
    """The blank page under the drawing: a max filter removes the lines, a blur the grain. With a
    ``sheet`` mask only the paper counts: its edge is carried out over the desk, so the desk
    neither darkens the estimate near the edge nor shows through it."""
    height, width = gray.shape
    factor = max(1, round(max(height, width) / 300))
    values = np.clip(gray, 0, 255) if sheet is None else np.where(sheet, np.clip(gray, 0, 255), 0)
    small = Image.fromarray(values.astype(np.uint8)).resize(
        (max(1, width // factor), max(1, height // factor)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.MaxFilter(7))
    if sheet is not None:
        known = np.asarray(small)
        for _ in range(max(small.size)):
            if known.all() or not known.any():
                break
            grown = np.asarray(Image.fromarray(known).filter(ImageFilter.MaxFilter(3)))
            known = np.where(known > 0, known, grown)
        small = Image.fromarray(known)
    small = small.filter(ImageFilter.GaussianBlur(6))
    return np.asarray(small.resize((width, height), Image.Resampling.BILINEAR), np.float32)


def locate_sheet(gray, size=600):
    """The sheet of paper in a photo of a drawing on a darker desk or table: (a bool mask of the
    sheet, kept a few pixels inside its edge, and the convex hull of the paper in pixels), or
    (None, None) when no edge of the paper shows (a scan, or paper filling the frame).

    On a small copy with the ink closed away, the frame's border (where any desk shows) and its
    centre (where the drawing is) give a threshold between paper and desk. The sheet is the
    convex hull of the paper's bright pixels, so the desk is cut off along the paper's straight
    edges, even where it thins to a sliver at a corner. It counts only when the paper is much brighter than
    the desk right at their boundary (a shadow or uneven light fades instead) and fills its hull."""
    from PIL import ImageDraw

    from .organic import clip_convex, convex_hull

    height, width = gray.shape
    factor = max(1.0, max(height, width) / size)
    sw, sh = max(1, round(width / factor)), max(1, round(height / factor))
    if min(sw, sh) < 24:
        return None, None
    small = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).resize((sw, sh), Image.Resampling.BOX)
    raw = np.asarray(small, np.float32) / 255
    closed = np.asarray(small.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5)), np.float32) / 255
    band = max(2, round(min(sw, sh) * 0.02))
    border = np.ones((sh, sw), bool)
    border[band:-band, band:-band] = False
    centre = np.zeros((sh, sw), bool)
    centre[sh // 3:sh - sh // 3, sw // 3:sw - sw // 3] = True
    # The border as photographed: a sliver of desk at a slight tilt is as thin as a line of ink.
    cut = otsu(np.concatenate([raw[border], closed[centre]]), centered=True)
    paper = closed >= cut
    if (raw[border] < cut).mean() < 0.02 or paper[centre].mean() < 0.5:
        return None, None
    labels, count = label(paper)
    overlap = np.bincount(labels[centre], minlength=count + 1)
    overlap[0] = 0
    sheet = labels == int(np.argmax(overlap))
    bright = sheet & (raw >= cut)
    ys, xs = np.nonzero(bright)
    if len(xs) < 3:
        return None, None
    # The hull of the row ends (as pixel corners) is the hull of the whole sheet.
    first = np.r_[True, ys[1:] != ys[:-1]]
    last = np.r_[ys[1:] != ys[:-1], True]
    corners = np.vstack([np.column_stack([xs[first], ys[first]]), np.column_stack([xs[first], ys[first] + 1]),
                         np.column_stack([xs[last] + 1, ys[last]]), np.column_stack([xs[last] + 1, ys[last] + 1])])
    hull = convex_hull(corners)
    if len(hull) < 3:
        return None, None
    outline = Image.new("L", (sw, sh))
    ImageDraw.Draw(outline).polygon([tuple(q) for q in hull], fill=255)
    inside = np.asarray(outline) > 127
    outside = ~inside
    if inside.mean() < 0.25 or outside.mean() < 0.002:
        return None, None
    # A desk: much darker than the paper right at their boundary and out to the frame (a frame
    # drawn near the edge of the paper has paper beyond it), and the paper fills its hull
    # (straight page edges, not the curve of a shadow).
    rim_out, rim_in = outside & dilate(inside, 2), inside & dilate(outside, 2)
    frame = np.ones((sh, sw), bool)
    frame[1:-1, 1:-1] = False
    if not rim_out.any() or not rim_in.any() or not (frame & outside).any():
        return None, None
    level = 0.8 * np.median(raw[rim_in])
    if np.median(raw[rim_out]) > level or np.median(raw[frame & outside]) > level:
        return None, None
    holes, _ = label(~sheet)
    edge = np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]]))
    filled = ~np.isin(holes, edge[edge > 0])
    if (inside & ~filled).sum() > 0.03 * inside.sum():
        return None, None
    # The sheet is the inside of each of its edges, extended across the frame (so a sliver of desk
    # too thin to see at this size is cut off too) and moved in a little to stay clear of the
    # edge's own blur and shadow. Where the paper runs off the frame, the frame is no edge.
    inset = 1.5 * factor + 2
    region = np.array([[0, 0], [width, 0], [width, height], [0, height]], float)
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        if (a[0] == b[0] and a[0] in (0, sw)) or (a[1] == b[1] and a[1] in (0, sh)):
            continue
        a, b = a * [width / sw, height / sh], b * [width / sw, height / sh]
        d = b - a
        normal = np.array([-d[1], d[0]]) / max(1e-9, float(np.linalg.norm(d)))
        region = clip_convex(region, a + normal * inset, b + normal * inset)
        if len(region) < 3:
            return None, None
    outline = Image.new("L", (width, height))
    ImageDraw.Draw(outline).polygon([tuple(q) for q in region], fill=255)
    return np.asarray(outline) > 127, hull * [width / sw, height / sh]


def find_sheet(gray, size=600):
    """The mask of the sheet of paper in a photo (see ``locate_sheet``), or None."""
    return locate_sheet(gray, size)[0]


def otsu(values, centered=False):
    """Otsu's threshold (0-1). Between two clean peaks every threshold separates them equally well:
    the lowest is returned, or with ``centered`` the middle of that gap, which leaves the noise on
    either peak on its own side."""
    histogram, edges = np.histogram(values, bins=256, range=(0, 1))
    histogram = histogram.astype(float)
    total = histogram.sum()
    if total == 0:
        return 0.5
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(histogram)
    mean = np.cumsum(histogram * centers)
    between = (mean[-1] * weight / total - mean) ** 2 / np.maximum(weight * (total - weight), 1e-9)
    if centered:
        return float(centers[int(np.mean(np.nonzero(between >= between.max() * (1 - 1e-9))[0]))])
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


def clean(image, settings=None, state=None, frame=None):
    """Clean a photographed or scanned drawing. Returns {"ink": RGBA image of the lines on
    transparency, "mask": bool line mask, "angle", "crop": [x, y, w, h] of the result within the
    deskewed photo, "threshold", "perspective": the flattening applied to a page photographed at
    an angle (or None)}. ``state`` resolves swatch colours for ``ink``. ``frame`` is the
    flattening to apply instead of looking for one (False for none)."""
    from . import paper
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
    # The desk around a photographed page is dark too, but it is not ink: leave it out first.
    sheet, hull = locate_sheet(gray) if settings["sheet"] and not frame else (None, None)
    if frame is None and hull is not None and settings["perspective"]:
        # A page photographed at an angle is a trapezoid: flatten it before anything is traced.
        frame = paper.frame_for(hull, image.size, 1.5 * max(1.0, max(gray.shape) / 600) + 2)
    if frame:
        image = paper.rectify(image, frame)
        rgb = np.asarray(image, np.float32)
        gray = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
        sheet = None
    level = flatten_paper(gray, sheet) if settings["flatten"] else gray / 255
    darkness = 1 - level
    if sheet is not None:
        darkness = darkness * sheet
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
            if sheet is not None:
                sheet = np.asarray(Image.fromarray(sheet.astype(np.uint8) * 255).rotate(angle, expand=True)) > 127
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
        sheet = sheet[y0:y1, x0:x1] if sheet is not None else None
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
        paper = np.stack([paper_estimate(rgb[..., i], sheet) for i in range(3)], axis=-1)
        a = np.maximum(alpha, 0.25)[..., None]
        out[..., :3] = np.clip((rgb - paper * (1 - a)) / a, 0, 255).astype(np.uint8)
    else:
        out[..., :3] = color(resolve_color(settings["ink"], state or {"variables": {}}))[:3]
    out[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return {"ink": Image.fromarray(out, "RGBA"), "mask": mask, "angle": angle, "crop": crop, "threshold": round(cut, 3),
            "scale": scale, "sheet": sheet is not None or bool(frame), "perspective": frame or None}


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
    for item, width in zip(result, _widths(mask, result)):
        item["width"] = width
    return result


def _widths(mask, strokes):
    """The width of each stroke: the ink that belongs to it (each ink pixel goes to its nearest
    stroke) over its length. Unlike the distance from the centre line to the edge, which reads a
    line of even width a pixel thin, this gives the pen's width however the line runs."""
    from .trace import length

    labels = np.zeros(mask.shape, np.int32)
    for index, stroke in enumerate(strokes, 1):
        p = np.round(np.asarray(stroke["points"], float)).astype(int)
        labels[np.clip(p[:, 1], 0, mask.shape[0] - 1), np.clip(p[:, 0], 0, mask.shape[1] - 1)] = index
    reach = int(min(24, np.ceil(max([s["width"] for s in strokes], default=1) / 2) + 2))
    for _ in range(reach):
        empty = (labels == 0) & mask
        if not empty.any():
            break
        for axis, step in ((0, 1), (0, -1), (1, 1), (1, -1)):
            shifted = np.roll(labels, step, axis=axis)
            if axis == 0:
                shifted[0 if step == 1 else -1, :] = 0
            else:
                shifted[:, 0 if step == 1 else -1] = 0
            take = empty & (shifted > 0)
            labels[take] = shifted[take]
            empty &= ~take
    area = np.bincount(labels[mask], minlength=len(strokes) + 1)
    widths = []
    for index, stroke in enumerate(strokes, 1):
        span = length(stroke["points"], stroke["closed"])
        # A stroke only a few widths long is mostly junction: keep the distance reading.
        widths.append(max(1.0, round(float(area[index] / span), 1)) if span >= 4 * stroke["width"] else stroke["width"])
    return widths


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


def _turn(d0, d1):
    """The signed angle (degrees) from one unit direction to the next."""
    return math.degrees(math.atan2(d0[0] * d1[1] - d0[1] * d1[0], float(d0 @ d1)))


def _bend(points):
    """How far a stretch of a stroke turns along its length (degrees, signed like ``_turn``):
    the arc through its ends that encloses as much area with their chord. A wobble to both sides
    cancels out."""
    p = np.asarray(points, float)
    chord = float(np.linalg.norm(p[-1] - p[0]))
    if len(p) < 3 or chord < 1e-9:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    return math.copysign(math.degrees(4 * math.atan(3 * abs(area) / chord ** 2)), area)


def _against(points, closed, tolerance):
    """How far (degrees) a stroke turns against its own way round at sharp turns: the cusps
    between the lobes of a cloud; none on a circle, however wobbly."""
    p = np.asarray(points, float)
    if closed:
        p = np.vstack([p, p[:1]])
    v = p[_rdp_indices(p, max(tolerance, 1.5))]
    d = np.diff(v, axis=0)
    d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    if closed:
        d = np.vstack([d, d[:1]])
    turns = [_turn(a, b) for a, b in zip(d, d[1:])]
    way = sum(turns)
    return sum(abs(t) for t in turns if t * way < 0 and abs(t) >= 20)


def _curves(p, sides, closed):
    """Which ``sides`` ((first, last) indices into ``p``) are chords of a curve rather than
    straight sides.

    The chords of a curve turn the same way bit by bit: along each chord and at each joint as
    much (a lobe, a tight arc), or by small turns joint after joint (a gentle arc). A run of such
    joints that turns 45° or more in all is a curve; a corner (a large turn between sides that
    stay straight) or a turn the other way ends it. A side between two stretches of one curve goes
    with the curve, but one that stays straight where curving like the rest of its stretch would
    bend it 40° or more is a straight side the curve runs into (the arms of a U)."""
    n = len(sides)
    if n < 2:
        return [False] * n

    def unit(i0, i1):
        v = p[i1] - p[i0]
        return v / max(1e-9, np.linalg.norm(v))

    lengths = [max(1e-9, float(np.linalg.norm(p[i1] - p[i0]))) for i0, i1 in sides]
    bends = [_bend(p[i0:i1 + 1]) for i0, i1 in sides]
    joints = n if closed else n - 1  # joint j is between sides j and j + 1
    turns = [_turn(unit(*sides[j]), unit(*sides[(j + 1) % n])) for j in range(joints)]

    def smooth(j):
        k, m, turn = j, (j + 1) % n, turns[j]
        need = max(4.0, abs(turn) / 4)
        if bends[k] * turn > 0 and bends[m] * turn > 0 and abs(bends[k]) >= need and abs(bends[m]) >= need:
            return True
        near = [turns[q % joints] for q in (j - 1, j + 1) if closed or 0 <= q < joints]
        return abs(turn) <= 30 and any(abs(u) <= 30 and u * turn > 0 for u in near)

    linked = [smooth(j) for j in range(joints)]
    start = 0
    if closed:
        # Begin at a break so no run is split where the loop starts.
        start = next((j for j in range(joints) if not linked[j] or turns[j] * turns[j - 1] <= 0), 0)
    runs, run = [], []
    for j in ((start + i) % joints for i in range(joints)):
        if linked[j] and run and turns[j] * turns[run[-1]] > 0:
            run.append(j)
        else:
            runs.append(run)
            run = [j] if linked[j] else []
    runs.append(run)
    curved = [False] * n
    for run in runs:
        members = {k for j in run for k in (j, (j + 1) % n)}
        if sum(abs(bends[k]) for k in members) + sum(abs(turns[j]) for j in run) >= 45:
            for k in members:
                curved[k] = True
    if not any(curved):
        return curved
    gaps = []
    for k in range(n):
        if curved[k] or not closed and k in (0, n - 1):
            continue
        a, c, before, after = (k - 1) % n, (k + 1) % n, turns[(k - 1) % joints], turns[k % joints]
        if curved[a] and curved[c] and before * after > 0 and before * bends[a] > 0 and after * bends[c] > 0:
            gaps.append(k)
    for k in gaps:
        curved[k] = True
    straight = []
    for k in range(n):
        if not curved[k]:
            continue
        # The rest of the stretch of curve this side is in, and how sharply it curves on average.
        others = []
        for step in (-1, 1):
            m = k + step
            while (closed or 0 <= m < n) and curved[m % n] and m % n != k and m % n not in others:
                others.append(m % n)
                m += step
        drawn = sum(lengths[m] for m in others)
        follow = sum(abs(bends[m]) for m in others) / drawn * lengths[k] if drawn else 0.0
        if follow >= 40 and abs(bends[k]) < follow / 4:
            straight.append(k)
    return [curved[k] and k not in straight for k in range(n)]


def _spline(points, step=2.0):
    """Points about ``step`` apart along the Catmull–Rom spline through ``points``: the curve a
    smooth stroke draws (``trace.path_data``), for drawing it with straight segments."""
    p = np.asarray(points, float)
    if len(p) < 3:
        return p
    out = [p[:1]]
    for i in range(len(p) - 1):
        p0, p1, p2, p3 = p[max(i - 1, 0)], p[i], p[i + 1], p[min(i + 2, len(p) - 1)]
        c1, c2 = p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6
        t = np.linspace(0, 1, max(1, math.ceil(np.linalg.norm(p2 - p1) / step)) + 1)[1:]
        out.append(bezier_points((p1, c1, c2, p2), t))
    return np.vstack(out)


def straighten_stroke(points, closed, *, tolerance, angles, angle_tolerance, circles, corner, polylines=True):
    """A straightened version of one stroke: (points, closed, kind) where kind is ``line``,
    ``polyline``, ``circle`` or None (left as drawn). Each side is fitted to the points drawn
    along it; rounded corners become sharp ones where neighbouring sides meet. Curves (lobes,
    arcs, waves) keep their drawn shape: a stroke that is all curve is left as drawn, and in one
    with straight sides too only those are straightened."""
    from .trace import length, resample

    p = np.asarray(points, float)
    span = length(p, closed)
    if span < 4:
        return p, closed, None
    gap = float(np.linalg.norm(p[0] - p[-1]))
    nearly_closed = not closed and len(p) >= 8 and gap <= 3 * tolerance and span > 12 * tolerance
    if circles and (closed or nearly_closed or gap < span * 0.12) and len(p) >= 12:
        # Fitted to points evenly along the line (its vertices crowd into the corners), and only
        # for a round shape: the cusps between a cloud's lobes turn against its way round.
        centre, radius, error = _fit_circle(resample(p, max(48, int(span / 3)), closed))
        if radius > 3 and error <= max(tolerance, radius * 0.12) and _against(p, closed or nearly_closed, tolerance) < 90:
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
    along = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])

    def drawn_length(a, b):
        """The length drawn from index a to b (round the loop when b comes first)."""
        return along[b] - along[a] if a <= b else along[-1] - along[a] + along[b]

    # Curves (lobes, arcs, waves) stay as drawn and only straight sides are straightened. Short
    # edges between two sides make a rounded corner; a longer stretch of them is a curve too.
    curved = _curves(p, sides, closed)
    gaps = [drawn_length(sides[k][1], sides[(k + 1) % len(sides)][0]) for k in range(len(sides) if closed else len(sides) - 1)]
    if not closed:
        gaps += [drawn_length(0, sides[0][0]), drawn_length(sides[-1][1], len(p) - 1)]
    if any(curved) or max(gaps, default=0) > 2 * corner:
        # Beside curves, a side too short to tell straight from curved goes with them.
        curved = [c or np.linalg.norm(p[i1] - p[i0]) < 2 * corner for c, (i0, i1) in zip(curved, sides)]
    straight = [side for side, c in zip(sides, curved) if not c]
    if not straight:
        return p[:-1] if closed else p, closed, None
    lines = []
    for i0, i1 in straight:
        centre, direction = _line_through(p[i0:i1 + 1])
        if angles:
            reach = np.linalg.norm(p[i1] - p[i0]) / 2
            s2, e2, _ = snap_angle(centre - direction * reach, centre + direction * reach, angles, angle_tolerance)
            direction = (e2 - s2) / max(1e-9, np.linalg.norm(e2 - s2))
        lines.append((centre, direction))

    def onto(line, point):
        centre, direction = line
        return centre + direction * ((point - centre) @ direction)

    def curve_between(a, b):
        """Whether the stroke curves between drawn indices a and b (wrapping round a loop)."""
        return drawn_length(a, b) > 2 * corner or any(
            c and (a <= i0 < b if a <= b else (i0 >= a or i0 < b)) for (i0, _), c in zip(sides, curved))

    def drawn(a, b, start, end):
        """The curve as drawn from index a to b, from ``start`` to ``end``."""
        between = p[a + 1:b] if a < b else np.vstack([p[a + 1:-1], p[:b]])
        return _spline(np.vstack([start, between, end]))[1:-1]

    out = []
    count = len(lines)
    if not closed:
        first = straight[0][0]
        if curve_between(0, first):
            out += [p[0], *drawn(0, first, p[0], onto(lines[0], p[first])), onto(lines[0], p[first])]
        else:
            out.append(onto(lines[0], p[0]))
    for i in range(count if closed else count - 1):
        j = (i + 1) % count
        end, start = straight[i][1], straight[j][0]
        if curve_between(end, start):
            a, b = onto(lines[i], p[end]), onto(lines[j], p[start])
            out += [a, *drawn(end, start, a, b), b]
        else:
            out.append(_meet(lines[i], lines[j], (p[end] + p[start]) / 2))
    if not closed:
        last = straight[-1][1]
        if curve_between(last, len(p) - 1):
            out += [onto(lines[-1], p[last]), *drawn(last, len(p) - 1, onto(lines[-1], p[last]), p[-1]), p[-1]]
        else:
            out.append(onto(lines[-1], p[-1]))
    return np.asarray(out, float), closed, "polyline"


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


# The drawing group's content space is the cleaned image's pixel grid. Its record:
#   group["drawing"] = {"source": asset of the photo as imported, "reference": asset of the
#   cleaned line mask (what preservation is measured against), "settings": clean settings,
#   "angle", "crop", "scale", "ink": ink colour}
# Stroke layers are path shapes carrying "drawing_strokes": [{"points", "closed", "width",
# "smooth", "origin": traced|added, "kind": None|line|polyline|circle|smoothed}] in content
# coordinates.


def schemas(add):
    from .schema import S

    settings = ("Per-action settings (see docs/drawing.md). import/clean: ink (line colour, default #1d1d1f), sheet, "
                "perspective, deskew, crop, weight, threshold. vectorize: mode, width (pixels or 'uniform'), color; outline "
                "mode also curves (fit Bézier curves), tolerance, corner_threshold, split ('components': one layer per "
                "connected part, in reading order), min_area. "
                "straighten: angles ('drawn' keeps each line's angle, 'axes', '45', 'guides' or degrees), tolerance, "
                "close_gaps (pixels or 'auto'), circles, polylines. smooth: amount, corners (keep, the default, leaves "
                "straightened lines and polylines as they are; round smooths them too). restyle: width (pixels or 'uniform'), width_scale. "
                "fill: gap, min_area, under. stroke: width, smooth, closed.")
    add("drawing", {"action": {"enum": list(ACTIONS)}, "name": S, "target": S, "asset": S, "path": S, "x": {}, "y": {},
                    "width": {}, "height": {}, "settings": {"type": "object", "description": settings},
                    "strokes": {"type": ["array", "string"], "items": S},
                    "points": {"type": "array", "description": "stroke: [[x, y], …]; fill: [[x, y, color], …]. Canvas "
                               "positions by default (where the drawing shows now, through moved, scaled or rotated "
                               "groups); with space: group, the drawing's own coordinates (drawing report lists both)."},
                    "space": {"enum": ["canvas", "group"], "description": "How stroke and fill points read: canvas "
                              "(default) document pixels, or group: the drawing group's own coordinates, which move "
                              "with the group."},
                    "color": {"type": "string", "description": "Line colour: strokes' colour for restyle/stroke, vectorize's "
                              "colour, or on import shorthand for settings.ink (default #1d1d1f)."}},
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
    if result.get("perspective"):
        from .paper import rectify

        image = rectify(image, result["perspective"])
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


def _to_content(project, group, points, space="canvas"):
    """Drawing content coordinates of ``points``: canvas positions (default), or already in the
    drawing group's own coordinates with ``space: group``, which stay put when the group moves."""
    require(space in ("canvas", "group"), "space is canvas or group", field="space")
    try:
        p = np.asarray(points, float)
    except (TypeError, ValueError):
        p = np.zeros((0,))
    require(p.ndim == 2 and p.shape[1] >= 2 and len(p) <= 20000, f"points are [[x, y], …] {space} positions",
            field="points")
    if space == "group":
        return p[:, :2]
    matrix = np.linalg.inv(_content_matrix(project, group))
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
    fresh = stroke_layer(layer["name"], records, layer.get("stroke", DEFAULT_INK),
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
    if op.get("color") and "ink" not in (op.get("settings") or {}):
        settings["ink"] = op["color"]  # `color` is shorthand for the `ink` setting
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
                        "crop": result["crop"], "scale": result["scale"], "perspective": result["perspective"],
                        "paper": result["sheet"]}
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
    geometry_changed = (result["angle"], result["crop"], result["perspective"]) != (
        record["angle"], record["crop"], record.get("perspective"))
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
        record.update(angle=result["angle"], crop=result["crop"], scale=result["scale"], perspective=result["perspective"],
                      paper=result["sheet"])


def clean_in_frame(image, settings, record, state):
    """Clean with the drawing's stored tilt and crop (so existing strokes stay aligned)."""
    result = clean(image, {**settings, "deskew": False, "crop": False}, state, frame=record.get("perspective") or False)
    angle, (x, y, w, h) = record["angle"], record["crop"]
    ink, mask = result["ink"], result["mask"]
    if angle:
        ink = ink.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True)
        mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).rotate(angle, expand=True)) > 127
    ink = ink.crop((x, y, x + w, y + h))
    mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).crop((x, y, x + w, y + h))) > 127
    return {**result, "ink": ink, "mask": mask, "angle": angle, "crop": record["crop"]}


VECTORIZE = {"mode": "centerline", "min_length": 6, "detail": 0.75, "max_strokes": MAX_STROKES, "keep_ink": False,
             "color": None, "width": None, "curves": False, "tolerance": 1.0, "corner_threshold": 60.0, "split": "none",
             "min_area": 4}
MAX_PARTS = 256  # split: components makes at most this many part layers; smaller parts beyond it share one


def reading_order(boxes):
    """Indices of ``(x0, y0, x1, y1)`` boxes in reading order: lines top to bottom (a box joins a line when its
    vertical centre lies within the line's extent), left to right within a line."""
    lines = []
    for index in sorted(range(len(boxes)), key=lambda i: (boxes[i][1], boxes[i][0])):
        x0, y0, x1, y1 = boxes[index]
        centre = (y0 + y1) / 2
        line = next((line for line in lines if line["top"] <= centre <= line["bottom"]), None)
        if line is None:
            lines.append({"top": y0, "bottom": y1, "items": [index]})
        else:
            line["items"].append(index)
            line["top"], line["bottom"] = min(line["top"], y0), max(line["bottom"], y1)
    lines.sort(key=lambda line: line["top"])
    return [i for line in lines for i in sorted(line["items"], key=lambda i: boxes[i][0])]


def components(mask, min_area=4):
    """``[(x0, y0, x1, y1, sub-mask, area)]``: the 8-connected parts of ``mask`` in reading order."""
    labels, count = label(mask)
    if not count:
        return []
    ys, xs = np.nonzero(labels)
    ids = labels[ys, xs]
    area = np.bincount(ids, minlength=count + 1)
    low_x, low_y = np.full(count + 1, mask.shape[1]), np.full(count + 1, mask.shape[0])
    high_x, high_y = np.zeros(count + 1, int), np.zeros(count + 1, int)
    np.minimum.at(low_x, ids, xs)
    np.minimum.at(low_y, ids, ys)
    np.maximum.at(high_x, ids, xs + 1)
    np.maximum.at(high_y, ids, ys + 1)
    keep = [k for k in range(1, count + 1) if area[k] >= min_area]
    boxes = [(int(low_x[k]), int(low_y[k]), int(high_x[k]), int(high_y[k])) for k in keep]
    order = reading_order(boxes)
    result = []
    for i in order:
        k, (x0, y0, x1, y1) = keep[i], boxes[i]
        result.append((x0, y0, x1, y1, labels[y0:y1, x0:x1] == k, int(area[k])))
    return result


def outline_path(mask, settings, offset=(0.0, 0.0)):
    """Closed outline path data around ``mask`` (holes included): fitted Bézier curves with ``curves``, else
    simplified straight segments. Coordinates are pixel edges shifted by ``offset``."""
    from .trace import elements_path, mask_contours, mask_curves

    if settings["curves"]:
        path, _ = mask_curves(mask, tolerance=float(finite(settings["tolerance"], "tolerance", 0.1, 50)),
                              corner_threshold=float(finite(settings["corner_threshold"], "corner_threshold", 1, 179)),
                              smooth=0.6, min_area=float(settings["min_area"]), offset=offset)
        return path
    loops = mask_contours(mask, smooth=0.6, tolerance=float(settings["detail"]), min_area=float(settings["min_area"]))
    shift = np.asarray(offset, float) + 0.5
    return elements_path([{"points": loop + shift, "closed": True, "smooth": False} for loop in loops])


def _outline_layers(project, group, mask, settings, color):
    """The outline-mode line layers: one path for the whole drawing, or one per connected part."""
    name = group["name"]
    cw, ch = group["content_width"], group["content_height"]

    def add(label, box, path):
        x, y, w, h = box
        layer = new_layer(label, "shape", w, h, shape="path", fill=color, stroke="transparent", path=path,
                          path_view=[w, h], x=x, y=y)
        layer.update(parent=group["id"], drawing_role="lines")
        _insert(project, layer, before=group)
        return layer

    if settings["split"] != "components":
        if not settings["curves"]:
            from .trace import elements_path, mask_contours

            loops = mask_contours(mask, smooth=0.6, tolerance=float(settings["detail"]))
            require(loops, "No lines to trace", field="target")
            path = elements_path([{"points": loop, "closed": True, "smooth": False} for loop in loops])
        else:
            path = outline_path(mask, settings)
            require(path, "No lines to trace", field="target")
        add(f"{name}/lines", (0, 0, cw, ch), path)
        return 1
    parts = components(mask, int(finite(settings["min_area"], "min_area", 1, 1e7)))
    require(parts, "No lines to trace", field="target")
    main, rest = parts[:MAX_PARTS - 1], parts[MAX_PARTS - 1:]
    if len(parts) <= MAX_PARTS:
        main, rest = parts, []
    made = 0
    for x0, y0, x1, y1, sub, _ in main:
        # Trace with a 2-pixel margin so the blur and the contour close around the part.
        path = outline_path(np.pad(sub, 2), settings, offset=(-1.0, -1.0))
        if path:
            made += 1
            add(f"{name}/part-{made:03d}", (x0 - 1, y0 - 1, x1 - x0 + 2, y1 - y0 + 2), path)
    if rest:
        leftover = np.zeros_like(mask)
        for x0, y0, x1, y1, sub, _ in rest:
            leftover[y0:y1, x0:x1] |= sub
        path = outline_path(leftover, settings)
        if path:
            made += 1
            add(f"{name}/small-parts", (0, 0, cw, ch), path)
    require(made, "No lines to trace", field="target")
    return made


def uniform_width(records):
    """The pen width most of the line work has: the median stroke width, weighted by length."""
    from .trace import length

    widths = np.array([r["width"] for r in records], float)
    spans = np.array([max(length(np.asarray(r["points"], float), r["closed"]), 1e-6) for r in records])
    order = np.argsort(widths)
    reached = np.cumsum(spans[order])
    return round(float(widths[order][int(np.searchsorted(reached, reached[-1] / 2))]), 1)


def _width_setting(value, records):
    """A stroke width asked for: a number, or ``uniform`` (the median of ``records``' widths)."""
    if value == "uniform":
        return uniform_width(records)
    return finite(value, "width", 0.5, 500)


def _vectorize(project, group, op):
    from .trace import simplify

    settings = _settings(op.get("settings"), VECTORIZE)
    require(settings["mode"] in ("centerline", "outline"), "mode is centerline or outline", field="settings")
    require(settings["width"] is None or settings["mode"] == "centerline",
            "width applies to centerline mode; outline mode keeps the pen's own pressure", field="settings")
    require(settings["split"] in ("none", "components"), "split is none or components", field="settings")
    require(settings["mode"] == "outline" or not (settings["curves"] or settings["split"] == "components"),
            "curves and split apply to outline mode (centerline strokes are already smooth)", field="settings")
    record = group["drawing"]
    mask = np.asarray(project.image(record["reference"], "L")) > 127
    ink = _child(project, group, "ink")
    color = settings["color"] or op.get("color") or record["settings"].get("ink", DEFAULT_INK)
    if color == "original":
        color = DEFAULT_INK
    for layer in [layer for layer in _children(project, group) if "drawing_strokes" in layer or layer.get("drawing_role") == "lines"]:
        project.state["layers"].remove(layer)
    name = group["name"]
    if settings["mode"] == "outline":
        _outline_layers(project, group, mask, settings, color)
    else:
        strokes = strokes_from_mask(mask, min_length=float(settings["min_length"]))
        require(strokes, "No lines to trace", field="target")
        limit = int(finite(settings["max_strokes"], "max_strokes", 1, MAX_STROKES))
        records = [{"points": simplify(s["points"], float(settings["detail"]), s["closed"]), "closed": s["closed"],
                    "width": s["width"], "smooth": True, "origin": "traced"} for s in strokes]
        if settings["width"] is not None:
            # One pen width for every stroke (the pen's own pressure and the line's angle vary it a little).
            width = _width_setting(settings["width"], records)
            for record in records:
                record["width"] = width
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


# ``angles``: "drawn" keeps each straightened line at the angle it was drawn at; "axes" and "45" snap
# to horizontal/vertical or to 45° steps too; a list of degrees, or "guides", snaps to those.
ANGLE_SETS = {"drawn": [], "none": [], "axes": [0, 90], "45": [0, 45, 90, 135]}
STRAIGHTEN = {"tolerance": 4.0, "angles": "drawn", "angle_tolerance": 6.0, "circles": True, "close_gaps": 0.0,
              "corner": 24.0, "polylines": True, "amount": 0.5, "corners": "keep"}


def _snap_angles(project, value):
    """The angles (degrees) straightened sides may snap to; none keeps the drawn angle."""
    if value == "guides":
        value = _guide_angles(project)
        require(value, "The document has no angled guides to snap to", field="settings")
    elif value in (None, False) or (isinstance(value, str) and value in ANGLE_SETS):
        value = ANGLE_SETS.get(value, [])
    require(isinstance(value, list) and len(value) <= 64,
            "angles is 'drawn' (the default), 'axes', '45', 'guides' or a list of degrees", field="settings")
    return [finite(a, "angle") for a in value]


def _gap_limit(group, value):
    """Pixels of gap to close: a number, or ``auto`` (2% of the drawing's longer side, at least 8)."""
    if value == "auto":
        return max(8.0, 0.02 * max(group["content_width"], group["content_height"]))
    return finite(value, "close_gaps", 0, 1000)


def _straighten(project, group, op, action):
    from .trace import chaikin, simplify

    settings = _settings(op.get("settings"), STRAIGHTEN)
    layers = _records(project, group, op.get("strokes", "all"))
    angles = _snap_angles(project, settings["angles"])
    gap = _gap_limit(group, settings["close_gaps"]) if action == "straighten" else 0
    updated = {}
    for layer in layers:
        records = []
        for record in layer["drawing_strokes"]:
            points = np.asarray(record["points"], float)
            if action == "smooth":
                require(settings["corners"] in ("keep", "round"), "corners is keep (the default) or round",
                        field="settings")
                if record.get("kind") in ("line", "polyline") and settings["corners"] == "keep":
                    # Straightened sides and corners are deliberate; smoothing them would round a window into a blob.
                    records.append({**record})
                    continue
                amount = finite(settings["amount"], "amount", 0, 1)
                passes = max(1, round(amount * 4))
                smoothed = chaikin(points, passes, record["closed"])
                if not record["closed"] and len(points) > 2:
                    smoothed = np.vstack([points[:1], smoothed, points[-1:]])
                smoothed = simplify(smoothed, 0.5, record["closed"])
                rounded = {"rounded": record["kind"]} if record.get("kind") in ("line", "polyline") else {}
                records.append({**record, "points": smoothed.tolist(), "kind": "smoothed", "smooth": True, **rounded})
                continue
            new, closed, kind = straighten_stroke(points, record["closed"], tolerance=finite(settings["tolerance"], "tolerance", 0, 1000),
                                                  angles=angles, angle_tolerance=finite(settings["angle_tolerance"], "angle_tolerance", 0, 45),
                                                  circles=bool(settings["circles"]), corner=finite(settings["corner"], "corner", 0, 10000),
                                                  polylines=bool(settings["polylines"]))
            if kind is None:
                records.append({**record})
            else:
                records.append({**{k: v for k, v in record.items() if k != "rounded"}, "points": np.asarray(new).tolist(),
                                "closed": closed, "kind": kind, "smooth": kind == "circle"})
        updated[layer["id"]] = records
    if gap:
        # Gaps are closed once the sides are straight, so a corner is run on to where its lines cross.
        # Every stroke of the drawing is something an end can run on to; only the chosen ones move.
        everything = [layer for layer in _children(project, group) if "drawing_strokes" in layer]
        flat, movable = [], set()
        for layer in everything:
            for record in updated.get(layer["id"], layer["drawing_strokes"]):
                if layer["id"] in updated:
                    movable.add(len(flat))
                flat.append({**record, "points": np.asarray(record["points"], float)})
        close_gaps(flat, gap, movable)
        position = 0
        for layer in everything:
            for record in updated.get(layer["id"], layer["drawing_strokes"]):
                if layer["id"] in updated:
                    record["points"], record["closed"] = flat[position]["points"].tolist(), flat[position]["closed"]
                position += 1
    for layer in layers:
        _rebuild(layer, updated[layer["id"]])


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
    content = _to_content(project, group, [p[:2] for p in points], op.get("space", "canvas"))
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

            if layer.get("drawing_role") == "lines" and (layer["x"], layer["y"], layer["width"], layer["height"]) != (0, 0, cw, ch):
                # A part layer (split: components) covers its own box inside the drawing.
                x, y = int(round(layer["x"])), int(round(layer["y"]))
                alpha = layer_image(project, layer, (x, y, layer["width"], layer["height"])).getchannel("A")
                part = Image.new("L", (cw, ch))
                part.paste(alpha.point(lambda a: 255 if a > 96 else 0), (x, y))
                canvas.paste(255, mask=part)
                continue
            image = layer_image(project, layer, (0, 0, cw, ch)) if layer.get("drawing_role") == "lines" else project.image(layer["asset"])
            alpha = image.convert("RGBA").getchannel("A").resize((cw, ch))
            canvas.paste(255, mask=alpha.point(lambda a: 255 if a > 96 else 0))
    return np.asarray(canvas) > 127


STROKE = {"width": None, "smooth": True, "closed": False}


def _add_stroke(project, group, op):
    settings = _settings(op.get("settings"), STROKE)
    content = _to_content(project, group, op.get("points") or [], op.get("space", "canvas"))
    require(len(content) >= 2, "stroke needs at least two points", field="points")
    existing = [r for layer in _children(project, group) for r in layer.get("drawing_strokes", [])]
    width = settings["width"] or (float(np.median([r["width"] for r in existing])) if existing else 4.0)
    color = op.get("color") or next((layer.get("stroke") for layer in _children(project, group) if "drawing_strokes" in layer),
                                    group["drawing"]["settings"].get("ink", DEFAULT_INK))
    if color == "original":
        color = DEFAULT_INK
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
    width = settings["width"]
    if width is not None:
        width = _width_setting(width, [r for layer in layers for r in layer["drawing_strokes"]])
    for layer in layers:
        if op.get("color"):
            from .design import resolve_color
            from .render import color

            color(resolve_color(op["color"], project.state))
            layer["stroke"] = op["color"]
        records = layer["drawing_strokes"]
        if width is not None or settings["width_scale"] is not None:
            for record in records:
                record["width"] = (width if width is not None
                                   else record["width"] * finite(settings["width_scale"], "width_scale", 0.05, 20))
            layer["stroke_width"] = float(np.median([r["width"] for r in records]))
        _rebuild(layer, records)


def validate(layer, state, project):
    if "drawing" in layer:
        record = layer["drawing"]
        require(isinstance(record, dict) and layer["type"] == "group", "Invalid drawing record", "invalid_project")
        for key in ("source", "reference"):
            require(record.get(key) in project.assets, "Missing drawing asset", "missing_asset")
        flat = record.get("perspective")
        if flat is not None:
            require(isinstance(flat, dict) and len(flat.get("quad", [])) == 4 and len(flat.get("size", [])) == 2
                    and all(len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in flat["quad"])
                    and all(isinstance(v, int) and 1 <= v <= 20000 for v in flat["size"]),
                    "Invalid drawing perspective", "invalid_project")
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

    origin = canvas((0, 0))

    sizes = sorted(r["width"] for r in strokes)
    kinds = {}
    for r in strokes:
        kinds[r.get("kind") or r.get("origin", "traced")] = kinds.get(r.get("kind") or r.get("origin", "traced"), 0) + 1
    return {
        "drawing": group["name"], "preserved": round(preserved, 4), "added": round(new, 4), "tolerance_px": tolerance,
        "fidelity": fidelity(reference, current),
        "strokes": len(strokes), "stroke_kinds": kinds,
        "stroke_width": {"min": sizes[0], "median": uniform_width(strokes), "max": sizes[-1]} if strokes else None,
        # Region points work as fill points in either space: point with the default space canvas,
        # group_point with space: group.
        "space": "canvas",
        "group": {"offset": origin, "scale": round(float(np.linalg.norm(matrix[:2, 0])), 4),
                  "rotation": round(float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0]))), 2)},
        "regions": [{"id": i["id"], "area": i["area"], "point": canvas(i["point"]),
                     "group_point": [round(float(i["point"][0]), 1), round(float(i["point"][1]), 1)]}
                    for i in info if not i["outside"]][:64],
        "fills": [layer["name"] for layer in _children(project, group) if layer.get("drawing_role") == "fill"],
        "tilt_corrected": group["drawing"]["angle"],
        "perspective_corrected": bool(group["drawing"].get("perspective")),
        "paper_found": bool(group["drawing"].get("paper")),
    }


def fidelity(reference, current):
    """How exactly the current lines reproduce the original ink, pixel for pixel: ``iou`` (shared ink over all
    ink, 1 is exact), ``mismatch`` (the fraction of the drawing's pixels that differ) and ``mismatch_pixels``.
    The pixel difference is ``image_diff.diff_images``, the comparison ``vixl diff`` uses."""
    from .image_diff import diff_images

    union = int(np.count_nonzero(reference | current))
    shared = int(np.count_nonzero(reference & current))

    def picture(mask):
        return Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L").convert("RGBA")

    _, stats = diff_images(picture(reference), picture(current), threshold=8)
    return {"iou": round(shared / union, 4) if union else 1.0, "mismatch": round(stats["changed_pixels"] / max(1, reference.size), 6),
            "mismatch_pixels": stats["changed_pixels"], "mismatch_region": stats["changed_region"]}


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
        rounded = [layer["name"] for layer in _children(candidate, item)
                   if any(record.get("rounded") for record in layer.get("drawing_strokes", []))]
        if rounded:
            issue("drawing", "warning", f"Drawing {item['name']!r} has straightened strokes that smooth rounded "
                  f"({', '.join(rounded[:8])}): their corners are curves now. Undo, then smooth with "
                  "settings.corners: keep (the default)", [item], strokes=rounded[:64])


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
