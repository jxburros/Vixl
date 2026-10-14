"""The ``composition`` check family: spacing, rhythm and alignment defects a reader sees as "not designed".

Five kinds of finding, each a ``review`` warning with a stable ``code``:

- ``dead_band``: an empty horizontal band between content blocks, or between content and an edge, that is
  much larger than the document's own gaps (from ``spatial``'s free rectangles); a hole of 30-70% of the frame
  with type directly above and below it counts even in a sparse frame;
- ``margin_drift``: stacked blocks whose left edges (right edges for right-aligned text, centres for centred
  text) are close but not equal: two margins where one was meant;
- ``uneven_rhythm``: a stack of lines whose consecutive gaps differ by more than the spacing scale allows: the
  middle line sits further from the line above it, which it matches in size, than from the next, or lines of one
  size are unevenly spaced; or a small block (secondary text, a row of dots) floats midway between two blocks of
  other kinds;
- ``crowding``: a rule, band or heading closer to the text below it than half a spacing unit;
- ``clumped_scatter``: a scatter (``pattern-scatter``, ``scatter``) whose motifs bunch in some cells of the
  tile and leave others empty.

Distances are measured in the craft spacing unit (half the body size, ``craft.spacing_unit``). Backgrounds,
glows that fade out and the insides of charts, scatters and repeats are not blocks; layers marked
``role: decoration`` and art that bleeds off the canvas fill space but are not aligned or spaced, and a band they
close off is not dead. A layer or document waiver of ``composition`` turns a deliberate finding informational.
The thresholds below were tuned on the craft backtest (``evals/craft_backtest``): change them only with its
numbers.
"""

import math
import re
from bisect import bisect_left, bisect_right
from statistics import median

CODES = ("dead_band", "margin_drift", "uneven_rhythm", "crowding", "clumped_scatter")

# Tuned on evals/craft_backtest (see its README for the catches and false findings at these values).
THRESHOLDS = {
    # A dead band is at least this share of its frame's height, this many spacing units, and this many times
    # the median gap between the frame's stacked blocks; it spans at least this share of the content width.
    "dead_band_share": 0.06,
    "dead_band_units": 4,
    "dead_band_gap_ratio": 2.25,
    "dead_band_width": 0.33,
    "dead_band_full": 0.85,
    # Space in a sparse frame (a title and a line on a slide) is the design, not a hole: bands are judged
    # only where blocks fill at least this share of the frame's height, and a band over this share of the
    # frame is a deliberate field of space.
    "dead_band_fill": 0.5,
    "dead_band_max_share": 0.42,
    "dead_band_hole": 0.3,  # an interior band between type this tall is dead even in a sparse frame
    "dead_band_hole_max": 0.7,
    # An edge band also has to be this many times the frame's margin on the opposite side.
    "edge_band_ratio": 1.75,
    # Edges further apart than this many pixels and closer than this many spacing units drift.
    "drift_tolerance_px": 2.0,
    "drift_units": 2,
    # Two consecutive gaps of a stack are uneven when the larger is this many times the smaller and they
    # differ by this many spacing units.
    "rhythm_ratio": 1.6,
    "rhythm_units": 2,
    # Siblings of one size: gaps up to this many units are one run (a larger gap is a break between groups).
    "rhythm_sibling_units": 3,
    # A small block floats when the gaps above and below it are both at least this many spacing units and the
    # larger is at most this many times the smaller.
    "float_units": 3,
    "float_ratio": 1.5,
    # Crowding: the gap below a rule, band or heading is under this many spacing units.
    "crowding_units": 0.5,
    # Clumped scatter: the coefficient of variation of motif coverage over the tile's cells.
    "scatter_cv": 0.6,
    "scatter_min_items": 8,
}

# A signed value or a share set beside its data (a bar's "−9", "+6", "38%"): placed by the data, not by a margin.
DATA_LABEL = re.compile(r"^\s*(?:[+\-−–]\s*\d[\d.,]*\s*(?:pts?|%)?|\d[\d.,]*\s*%)\s*$")
LIST_MARKER = re.compile(r"^\s*(?:[•·▪◦‣–—*-]|\d{1,3}[.)])\s")
UNIT_GROUPS = ("chart", "pattern_scatter", "repeat", "radial", "table", "diagram")
GROUND_SHARE = 0.2
# Layers drawn fainter than this (their opacity times their groups') are atmosphere, not blocks.
FAINT = 0.3
MAX_PER_CODE = 12
CONTAINER_SHARE = 0.005


class Block:
    __slots__ = ("item", "box", "kind", "decoration", "heading", "align", "size", "marker", "label", "container")

    def __init__(self, item, box, kind, decoration=False, heading=False, align=None, size=None, marker=False):
        self.item, self.box, self.kind = item, box, kind
        self.decoration, self.heading, self.align = decoration, heading, align
        self.size, self.marker = size, marker
        self.label = False
        self.container = None

    @property
    def left(self):
        return self.box[0]

    @property
    def right(self):
        return self.box[0] + self.box[2]

    @property
    def top(self):
        return self.box[1]

    @property
    def bottom(self):
        return self.box[1] + self.box[3]

    @property
    def center(self):
        return self.box[0] + self.box[2] / 2


def _round(box):
    return [round(v, 1) for v in box]


def _union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _inside(inner, outer, slack=1.0):
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[0] + inner[2] <= outer[0] + outer[2] + slack
            and inner[1] + inner[3] <= outer[1] + outer[3] + slack)


def _x_overlap(a, b):
    return min(a.right, b.right) - max(a.left, b.left)


def unit_of(project):
    """The craft spacing unit of this document (half its body size)."""
    from .craft import body_size, spacing_unit

    return spacing_unit(body_size(project))


def collect(candidate, resolved, geometry, content, role, ancestors, width, height):
    """The blocks the family judges, the canvas-covering grounds that frame them, and the scatter groups."""
    from .craft import body_size, stage_for

    body = body_size(candidate)
    children = {}
    for item in resolved.values():
        if item.get("parent"):
            children.setdefault(item["parent"], []).append(item)

    def leaves(group):
        out = []
        for child in children.get(group["id"], []):
            out.extend(leaves(child) if child["type"] == "group" else [child])
        return out

    def unit(item):
        return item["type"] == "group" and any(item.get(key) for key in UNIT_GROUPS)

    def emitter(item):
        kids = children.get(item["id"], [])
        return item["type"] == "group" and kids and all("particle" in kid for kid in kids)

    shown = {item["id"] for item in content}
    blocks, scatters = [], []
    for item in content:
        if any(unit(parent) or emitter(parent) for parent in ancestors(item)):
            continue
        if unit(item) or emitter(item):
            parts = [geometry[x["id"]] for x in leaves(item) if x["id"] in shown and x["type"] != "adjustment"]
            parts = [p for p in parts if p[2] > 0 and p[3] > 0]
            if not parts:
                continue
            box = _union(parts)
            kind = "unit"
        elif item["type"] in ("group", "adjustment"):
            continue
        elif math.prod(x["opacity"] for x in (item, *ancestors(item))) < FAINT:
            continue  # Atmosphere (smoke, haze, the last fading stripes of a reflection), not a block.
        elif item["type"] == "gradient" and not item.get("role") and role(item) == "decoration":
            continue  # A glow that fades out has no edge to space against.
        else:
            box = geometry[item["id"]]
            kind = item["type"]
        x, y, w, h = box
        if w <= 0 or h <= 0 or x >= width or y >= height or x + w <= 0 or y + h <= 0:
            continue
        bleeding = x < -0.5 or y < -0.5 or x + w > width + 0.5 or y + h > height + 0.5
        touching = sum((x <= 0.5, y <= 0.5, x + w >= width - 0.5, y + h >= height - 0.5))
        if item["type"] == "gradient" and touching >= 2 and w * h >= GROUND_SHARE * width * height:
            continue  # A gradient fill running to the page edges (sky, water) is ground, not a block.
        # Bleeding art (a hill, a wave band) fills space but is not aligned or spaced like a block.
        art = bleeding and item["type"] != "text"
        layer = resolved[item["id"]]
        text = item["type"] == "text"
        if text and not str(layer.get("text", "")).strip():
            continue
        if kind != "unit" and item["type"] == "shape" and not text:
            if h <= max(6.0, 0.02 * min(width, height)) and w >= 6 * h:
                kind = "rule"
            elif w >= 0.6 * width and h <= 0.25 * height:
                kind = "band"
        heading = text and (role(item) == "title" or stage_for(layer.get("size", 0), body) in ("display", "heading"))
        decoration = art or role(item) == "decoration" or bool(layer.get("decorative") and not text)
        align = layer.get("align", "left") if text else None
        # A list hangs its markers (bullets, numbers) left of the margin on purpose.
        marker = text and bool(LIST_MARKER.match(str(layer.get("text", ""))))
        block = Block(item, tuple(float(v) for v in box), kind, decoration, heading, align,
                      layer.get("size") if text else None, marker)
        if text:
            # A kicker or eyebrow: a few words set in capitals, read as a label of the line it sits on.
            words = str(layer.get("text", "")).split()
            block.label = len(words) <= 4 and (layer.get("text_transform") == "uppercase"
                                               or " ".join(words).isupper())
        blocks.append(block)
    # A scatter tile often covers the canvas, so it is found among every visible layer, not only the blocks.
    for item in resolved.values():
        if item["type"] == "group" and (item.get("pattern_scatter") or any(
                kid.get("scatter") for kid in children.get(item["id"], []))):
            if all(x["visible"] and x["opacity"] > 0 for x in (item, *ancestors(item))):
                scatters.append(item)
    # Text set in a chip (a highlight, pill or button that hugs it, wider than tall) aligns and spaces by the chip's edges: the
    # inset of the text inside it is padding, not a second margin.
    chips = set()
    for block in blocks:
        if block.kind != "text":
            continue
        for chip in blocks:
            if chip.kind == "shape" and id(chip) not in chips and hugs(block.box, chip.box):
                block.box = chip.box
                chips.add(id(chip))
                break
    blocks = [b for b in blocks if id(b) not in chips]
    # Grounds: large panels that hold other blocks frame their own composition (a navy lower half, a card).
    # Panels and cards: a filled shape or image large enough to hold a block (not a dot or an icon).
    containers = [b for b in blocks if b.kind in ("shape", "band", "image")
                  and b.box[2] * b.box[3] >= CONTAINER_SHARE * width * height]
    for block in blocks:
        best = None
        for panel in containers:
            if panel is block or not _inside(block.box, panel.box) or _inside(panel.box, block.box, 0):
                continue
            if best is None or panel.box[2] * panel.box[3] < best.box[2] * best.box[3]:
                best = panel
        block.container = best
    grounds = [b for b in containers if b.box[2] * b.box[3] >= GROUND_SHARE * width * height
               and any(other.container is b for other in blocks)]
    return blocks, grounds, scatters


def ink_heights(candidate, resolved, geometry, content, local_bounds):
    """``geometry`` with each text layer's vertical extent narrowed to its glyphs. A text box includes the line's
    leading above the capitals and below the baseline, which a reader sees as space: the gap between a picture
    and a title set in a tall line box is the gap to the letters. The horizontal extent stays the layout box,
    which is where text aligns (glyph side bearings differ from letter to letter)."""
    from .checks import group_matrix
    from .spatial import glyph_box

    narrowed = dict(geometry)
    for item in content:
        layer = resolved[item["id"]]
        if layer["type"] != "text" or layer.get("repeat") or not str(layer.get("text", "")).strip():
            continue
        glyph = glyph_box(candidate, layer, local_bounds[item["id"]], group_matrix(layer, resolved, local_bounds))
        if glyph is None:
            continue
        x, _, w, _ = geometry[item["id"]]
        narrowed[item["id"]] = (x, glyph[1], w, glyph[3])
    return narrowed


def hugs(text_box, chip_box):
    """Whether a shape is a chip around a line of text (a highlight, pill or button that hugs it, wider than tall)."""
    w, h = text_box[2], text_box[3]
    pad = max(h, 8.0)
    return (_inside(text_box, chip_box) and chip_box[2] <= w + 3 * pad and chip_box[3] <= h + 2 * pad
            and chip_box[2] >= 1.5 * chip_box[3])  # A badge or seal around initials is a mark, not a chip.


def geometry_boxes(project):
    """Canvas boxes of what every layer draws, as the family measures them (``checks.canvas_projection``)."""
    from .checks import canvas_projection
    from .render import resolve_layout, resolved_layers

    resolved = {item["id"]: item for item in resolved_layers(project)}
    local = resolve_layout(project, layers=list(resolved.values()))
    return resolved, canvas_projection(resolved, local)["geometry_bounds"]


def frame_of(block, grounds):
    """The ground a block sits on (the smallest that contains it), or None for the canvas."""
    best = None
    for ground in grounds:
        if ground is block or not _inside(block.box, ground.box):
            continue
        if best is None or ground.box[2] * ground.box[3] < best.box[2] * best.box[3]:
            best = ground
    return best


def stacked_gaps(blocks):
    """``(upper, lower, gap)`` for each block and the nearest block below it in the same column."""
    out = []
    ordered = sorted(blocks, key=lambda b: (b.top, b.left))
    tops = [b.top for b in ordered]
    for upper in ordered:
        # Sorted by top, the first block below that shares the column is the nearest one.
        for lower in ordered[bisect_left(tops, upper.bottom - 1):]:
            if lower is not upper and _x_overlap(upper, lower) > 0:
                out.append((upper, lower, lower.top - upper.bottom))
                break
    return out


def _grid_free(frame, boxes, limit, lines=400):
    """Maximal empty rectangles of ``frame`` among many obstacles, on a grid whose lines are the obstacles' own
    edges (merged to at most ``lines`` per axis, rounding obstacles outwards), so the result stays exact for a
    few dozen blocks and fast for thousands. The spatial search splits every rectangle by every obstacle,
    which grows too fast past a few dozen scattered blocks."""
    import numpy as np

    fx, fy, fw, fh = frame

    def axis(starts, ends, origin, size):
        edges = sorted({origin, origin + size, *starts, *ends})
        step = size / lines
        kept = [edges[0]]
        for edge in edges[1:]:
            if edge - kept[-1] >= step or edge == edges[-1]:
                kept.append(edge)
        return np.array(kept)

    xs = axis([b[0] for b in boxes], [b[0] + b[2] for b in boxes], fx, fw)
    ys = axis([b[1] for b in boxes], [b[1] + b[3] for b in boxes], fy, fh)
    taken = np.zeros((len(ys), len(xs)), dtype=np.int32)
    for x, y, w, h in boxes:
        c0 = max(0, int(np.searchsorted(xs, x, "right")) - 1)
        c1 = int(np.searchsorted(xs, x + w, "left"))
        r0 = max(0, int(np.searchsorted(ys, y, "right")) - 1)
        r1 = int(np.searchsorted(ys, y + h, "left"))
        taken[r0, c0] += 1
        taken[r0, c1] -= 1
        taken[r1, c0] -= 1
        taken[r1, c1] += 1
    free = taken.cumsum(0).cumsum(1)[:-1, :-1] == 0
    rows, cols = free.shape
    heights = np.zeros(cols, dtype=np.int64)
    found = set()
    for r in range(rows):
        heights = np.where(free[r], heights + 1, 0)
        below = free[r + 1] if r + 1 < rows else np.zeros(cols, dtype=bool)
        stack = []
        for c in range(cols + 1):
            h = int(heights[c]) if c < cols else 0
            first = c
            while stack and stack[-1][1] >= h:
                begin, height = stack.pop()
                # Maximal: it cannot grow downwards (it can't grow sideways or upwards by construction).
                if height > h and not below[begin:c].all():
                    found.add((begin, r - height + 1, c, r + 1))
                first = begin
            stack.append((first, h))
    rects = [(float(xs[c0]), float(ys[r0]), float(xs[c1] - xs[c0]), float(ys[r1] - ys[r0]))
             for c0, r0, c1, r1 in found]
    return sorted(rects, key=lambda r: r[2] * r[3], reverse=True)[:limit]


def free_rectangles(frame, boxes, limit=64):
    from .spatial import _free

    inside = []
    for x, y, w, h in boxes:
        left, top = max(x, frame[0]), max(y, frame[1])
        right, bottom = min(x + w, frame[0] + frame[2]), min(y + h, frame[1] + frame[3])
        if right > left and bottom > top:
            inside.append((left, top, right - left, bottom - top))
    if len(inside) > 40:
        return _grid_free(frame, inside, limit)
    return [tuple(r["bounds"]) for r in _free(list(frame), inside, limit)]


def dead_bands(blocks, grounds, unit, width, height, emit):
    t = THRESHOLDS
    frames = [None, *grounds]
    for ground in frames:
        frame = ground.box if ground else (0.0, 0.0, float(width), float(height))
        members = [b for b in blocks if b is not ground and frame_of(b, grounds) is ground]
        solid = [b for b in members if not b.decoration]
        # A band reads as dead where a layout of type has a hole; a scene without text is judged as a picture.
        if len(solid) < 2 or sum(1 for b in solid if b.kind == "text") < 2:
            continue
        left = min(b.left for b in members)
        right = max(b.right for b in members)
        spans = sorted((max(b.top, frame[1]), min(b.bottom, frame[1] + frame[3])) for b in members
                       if b.kind != "rule")
        filled, reach = 0.0, frame[1]
        for start, end in spans:
            if end > reach:
                filled += end - max(start, reach)
                reach = end
        # A sparse frame is judged as open space, except for a hole between two blocks of type (below).
        sparse = filled < t["dead_band_fill"] * frame[3]
        # The frame's rhythm is the gaps between its own blocks, not the padding inside its cards.
        gaps = [gap for _, _, gap in stacked_gaps([b for b in members if b.container is ground]) if gap > 0.5]
        typical = median(gaps) if gaps else 0
        need = max(t["dead_band_share"] * frame[3], t["dead_band_units"] * unit, t["dead_band_gap_ratio"] * typical)
        span = max(1.0, right - left)
        # Margins are read from blocks that carry weight: a tiny ornament in a corner does not set one.
        weighty = [b for b in solid if b not in grounds and (
            b.kind == "text" or b.box[2] * b.box[3] >= 0.005 * frame[2] * frame[3])] or solid
        margins = {"top": min(b.top for b in weighty) - frame[1],
                   "bottom": frame[1] + frame[3] - max(b.bottom for b in weighty)}
        found = []
        for rect in free_rectangles(frame, [b.box for b in members]):
            x, y, w, h = rect
            # Only the part of the band across the content column counts as its width.
            across = min(x + w, right) - max(x, left)
            interior = frame[1] + 0.5 < y and y + h < frame[1] + frame[3] - 0.5
            # A hole between a headline and the rest of the type (a poster whose middle was left empty) is dead
            # however sparse the frame or wide the hole; other very tall or sparse bands are open space.
            hole = interior and h >= t["dead_band_hole"] * frame[3] and h <= t["dead_band_hole_max"] * frame[3] and _between_type(
                members, x, y, w, h, frame[3])
            if (sparse or h > t["dead_band_max_share"] * frame[3]) and not hole:
                continue
            if hole:
                # With few blocks the hole is itself the median gap: judge it against the other gaps.
                others = [gap for gap in gaps if gap < h - 1]
                bar = max(t["dead_band_share"] * frame[3], t["dead_band_units"] * unit,
                          t["dead_band_gap_ratio"] * (median(others) if others else 0))
            else:
                bar = need
            if h < bar or across < t["dead_band_width"] * span:
                continue
            # Space beside a line of text or a rule on the same rows is a ragged edge, not a band: a band
            # short of the full column counts only when artwork, not type, closes its sides.
            if across < t["dead_band_full"] * span and any(
                    b.kind in ("text", "rule") and (b.right <= x + 1 or b.left >= x + w - 1)
                    and min(b.bottom, y + h) - max(b.top, y) >= 0.5 * b.box[3] for b in members):
                continue
            if y <= frame[1] + 0.5 or y + h >= frame[1] + frame[3] - 0.5:
                # Open to the frame's edge: an edge band, dead only when it dwarfs the opposite margin.
                side = "top" if y <= frame[1] + 0.5 else "bottom"
                opposite = margins["bottom" if side == "top" else "top"]
                if h < t["edge_band_ratio"] * max(opposite, unit):
                    continue
                where = f"between the content and the {side} edge"
            else:
                side = None
                where = "between content blocks"
            above = [b for b in members if b.bottom <= y + 1 and min(b.right, x + w) > max(b.left, x)]
            below = [b for b in members if b.top >= y + h - 1 and min(b.right, x + w) > max(b.left, x)]
            near = ([max(above, key=lambda b: b.bottom)] if above else []) + (
                [min(below, key=lambda b: b.top)] if below else [])
            # Space that a marked decoration or bleeding art closes off is that art's setting, not a hole.
            if any(b.decoration for b in near):
                continue
            found.append((h * across, rect, side, where, near))
        kept = []
        for _, rect, side, where, near in sorted(found, key=lambda f: -f[0]):
            if any(_overlap_share(rect, other) > 0.3 for other, *_ in kept):
                continue
            kept.append((rect, side, where, near))
        for rect, side, where, near in kept[:3]:
            x, y, w, h = rect
            emit("dead_band", f"An empty band {h:.0f} px tall ({h / frame[3]:.0%} of the "
                 f"{'canvas' if ground is None else repr(ground.item['name'])} height) sits {where}; the "
                 f"document's typical gap is {typical:.0f} px. Close it up (move the blocks below up, or grow the "
                 "content into it) or give it a purpose",
                 [b.item for b in near], rect, actual=round(h, 1), expected=round(need, 1),
                 values={"height": round(h, 1), "width": round(w, 1), "typical_gap": round(typical, 1),
                         "frame_share": round(h / frame[3], 3), **({"edge": side} if side else {})},
                 threshold={"min_height": round(need, 1), "min_width_share": t["dead_band_width"],
                            **({"edge_ratio": t["edge_band_ratio"]} if side else {})})


def _between_type(members, x, y, w, h, frame_height):
    """Whether text closes a band from above and from below (not artwork, which sets a scene in it), and one side
    carries the copy (three blocks or a tenth of the frame): a headline over a credit line far below is a
    minimal composition, not a hole."""
    above = [b for b in members if b.bottom <= y + 1 and min(b.right, x + w) > max(b.left, x)]
    below = [b for b in members if b.top >= y + h - 1 and min(b.right, x + w) > max(b.left, x)]
    if not (above and below) or max(above, key=lambda b: b.bottom).kind != "text" or min(
            below, key=lambda b: b.top).kind != "text":
        return False
    return any(len(side) >= 3 or max(b.bottom for b in side) - min(b.top for b in side) >= 0.1 * frame_height
               for side in (above, below))


def _overlap_share(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / max(1e-9, min(a[2] * a[3], b[2] * b[3]))


def _lead_ins(blocks, unit):
    """The blocks with something just left of them on their line (a bullet, a dot, an icon before a label):
    their left edge follows that lead-in rather than the margin."""
    by_right = sorted(blocks, key=lambda b: b.right)
    rights = [b.right for b in by_right]
    led = set()
    for block in blocks:
        start = bisect_left(rights, block.left - 2 * unit)
        for other in by_right[start:bisect_right(rights, block.left + 1)]:
            if other is block:
                continue
            shared = min(other.bottom, block.bottom) - max(other.top, block.top)
            if shared >= 0.5 * min(other.box[3], block.box[3]):
                led.add(id(block))
                break
    return led


def margin_drift(blocks, unit, emit, area):
    t = THRESHOLDS
    window = t["drift_units"] * unit
    tolerance = t["drift_tolerance_px"]
    led = _lead_ins(blocks, unit)
    mark_area = CONTAINER_SHARE * area
    judged = [b for b in blocks if not b.decoration and b.kind != "band"]
    groups = {}
    for block in judged:
        groups.setdefault(id(block.container), []).append(block)
    labels = {"left": "left edges", "right": "right edges", "center": "centre axes"}
    for members in groups.values():
        if not any(b.kind == "text" for b in members):
            continue
        for axis in ("left", "right", "center"):
            def edge(b):
                return b.left if axis == "left" else b.right if axis == "right" else b.center

            def takes(b):
                if b.kind == "text":
                    if axis == "left" and (b.marker or id(b) in led):
                        return False
                    if DATA_LABEL.match(str(b.item.get("text", "")).strip()):
                        return False
                    return (b.align or "left") == axis or (axis == "left" and b.align == "justify")
                # Rules, charts, images and free-standing marks keep a margin; the parts of a drawing do not.
                return axis != "center" and (b.kind in ("rule", "unit", "image") or (
                    b.kind == "shape" and not b.item.get("parent") and b.box[2] * b.box[3] >= mark_area))

            pool = sorted((b for b in members if takes(b)), key=edge)
            if len(pool) < 2:
                continue
            edges = [edge(b) for b in pool]
            # One finding per pair of edge positions: the edge more blocks share is the margin.
            pairs = {}
            for i, a in enumerate(pool):
                for b in pool[bisect_right(edges, edges[i] + tolerance):bisect_right(edges, edges[i] + window)]:
                    if a.kind != "text" and b.kind != "text":
                        continue
                    # The same column: stacked, sharing horizontal extent.
                    if _x_overlap(a, b) <= 0.3 * min(a.box[2], b.box[2]):
                        continue
                    key = (round(edge(a)), round(edge(b)))
                    pairs.setdefault(key, {})
                    pairs[key][id(a)] = a
                    pairs[key][id(b)] = b
            for (e1, e2), found in pairs.items():
                involved = list(found.values())
                count = {e: bisect_right(edges, e + tolerance) - bisect_left(edges, e - tolerance) for e in (e1, e2)}
                margin, stray = (e1, e2) if count[e1] >= count[e2] else (e2, e1)
                strays = [x for x in involved if abs(edge(x) - stray) <= 0.5]
                anchors = [x for x in involved if abs(edge(x) - margin) <= 0.5]
                stray_at, margin_at = edge(strays[0]), edge(anchors[0])
                offset = stray_at - margin_at
                emit("margin_drift", f"{', '.join(repr(x.item['name']) for x in strays[:4])} "
                     f"{'sits' if len(strays) == 1 else 'sit'} at {axis} {stray_at:g} px while "
                     f"{', '.join(repr(x.item['name']) for x in anchors[:3])} {'sits' if len(anchors) == 1 else 'sit'} "
                     f"at {margin_at:g} px: {abs(offset):g} px apart, two {labels[axis]} where one was meant. Snap "
                     "them to one edge (align), or move them a clear step apart",
                     strays + anchors, _union([x.box for x in involved]), actual=round(abs(offset), 1), expected=0,
                     values={"axis": axis, "edge": round(stray_at, 1), "margin": round(margin_at, 1),
                             "offset": round(offset, 1), "stray_ids": [x.item["id"] for x in strays]},
                     threshold={"tolerance_px": tolerance, "window_px": round(window, 1)})


def _related(a, b):
    """How alike two text sizes are (1 = the same); a block's own lines belong with the closest-sized one."""
    return min(a.size, b.size) / max(a.size, b.size)


def uneven_rhythm(blocks, unit, emit, body):
    t = THRESHOLDS
    # Rules and bands are in the stack so that they break it: a divider starts a new run of rhythm.
    judged = [b for b in blocks if not b.decoration and b.kind in ("text", "image", "unit", "rule", "band")]
    groups = {}
    for block in judged:
        groups.setdefault(id(block.container), []).append(block)
    for members in groups.values():
        links = {id(upper): (lower, gap) for upper, lower, gap in stacked_gaps(members)
                 if 0 <= gap <= 10 * unit and _x_overlap(upper, lower) >= 0.5 * min(upper.box[2], lower.box[2])
                 and upper.kind not in ("rule", "band") and lower.kind not in ("rule", "band")}
        starts = set(links) - {id(lower) for lower, _ in links.values()}
        by_id = {id(b): b for b in members}
        for start in starts:
            chain, gaps = [by_id[start]], []
            while id(chain[-1]) in links and len(chain) < 256:
                lower, gap = links[id(chain[-1])]
                chain.append(lower)
                gaps.append(gap)
            for i in range(len(gaps) - 1):
                a, b, c = chain[i:i + 3]
                if not all(x.kind == "text" and x.size for x in (a, b, c)):
                    continue
                g1, g2 = gaps[i], gaps[i + 1]
                small, large = sorted((g1, g2))
                if large < t["rhythm_ratio"] * max(small, 1):
                    continue
                if _related(a, b) > 0.95 and _related(b, c) > 0.95:
                    # Siblings (list rows, lines of one size): their gaps should match, unless the larger gap
                    # is a break between groups (over the run's own step).
                    uneven = large - small >= unit and large <= t["rhythm_sibling_units"] * unit
                elif any(x.size <= 0.85 * body or x.label for x in ((a, b) if g1 < g2 else (b, c))):
                    # A small or capitalised label (a kicker, an eyebrow) sits tight to what it labels.
                    uneven = False
                else:
                    # Lines of different sizes: a line belongs with the closer-sized line above it (a first and a
                    # last name), so a larger gap above it than below splits a group apart. A line that sits
                    # close under the one above and away from the next is a subtitle or lead-in: by design.
                    uneven = (large - small >= t["rhythm_units"] * unit and g1 > g2 and not b.label
                              and _related(a, b) > _related(b, c) + 0.05)
                if not uneven:
                    continue
                trio = (a, b, c)
                emit("uneven_rhythm", f"Gaps in the stack {', '.join(repr(x.item['name']) for x in trio)} are "
                     f"{g1:.0f} px and then {g2:.0f} px ({g1 / unit:.1f} and {g2 / unit:.1f} spacing units of "
                     f"{unit:g} px): lines that belong together sit further apart than lines that do not. Give "
                     "related lines one step of the spacing scale, and keep larger steps for breaks between groups",
                     list(trio), _union([x.box for x in trio]), actual=round(large / max(small, 1), 2),
                     expected=t["rhythm_ratio"],
                     values={"gaps": [round(g1, 1), round(g2, 1)], "units": [round(g1 / unit, 2), round(g2 / unit, 2)],
                             "sizes": [a.size, b.size, c.size]},
                     threshold={"ratio": t["rhythm_ratio"], "min_difference_px": round(t["rhythm_units"] * unit, 1),
                                "sibling_max_units": t["rhythm_sibling_units"]})


def _alike(a, b):
    """Two blocks of one kind: text of about the same size, or artwork of about the same height."""
    if (a.kind == "text") != (b.kind == "text"):
        return False
    first, second = (a.size or 0, b.size or 0) if a.kind == "text" else (a.box[3], b.box[3])
    return abs(first - second) <= 0.15 * max(first, second, 1)


def floating(blocks, unit, emit, taken):
    """A small block of a stack (a line of secondary text, a row of dots) as far from the block above as from
    the one below, between blocks of other kinds, so proximity no longer says what it belongs to. Evenly spaced
    items of one kind (lines of a list) are a rhythm, not a float. Gaps inside ``taken`` (dead bands) are not
    reported again."""
    t = THRESHOLDS
    # Layout blocks only: the parts of a drawing (a lantern's ribs, the stripes of a reflection) have their own
    # small gaps, which are not the rhythm of the page.
    judged = [b for b in blocks if not b.decoration and b.container is None and (
        b.kind in ("text", "rule", "band", "unit", "image") or not b.item.get("parent"))]
    links = {id(upper): (lower, gap) for upper, lower, gap in stacked_gaps(judged) if gap > 0.5}
    starts = set(links) - {id(lower) for lower, _ in links.values()}
    by_id = {id(b): b for b in judged}
    seen = set()

    def reported(upper, lower):
        return (id(upper), id(lower)) in seen or any(
            r[1] <= upper.bottom + 1 and r[1] + r[3] >= lower.top - 1 for r in taken)

    for start in sorted(starts, key=lambda key: by_id[key].top):
        chain, gaps = [by_id[start]], []
        while id(chain[-1]) in links and len(chain) < 256:
            lower, gap = links[id(chain[-1])]
            chain.append(lower)
            gaps.append(gap)
        for i in range(len(gaps) - 1):
            a, b, c = chain[i:i + 3]
            g1, g2 = gaps[i], gaps[i + 1]
            # Small: secondary text (a heading counts when a line at least 2.5 times its size sits next to it, as a
            # subtitle under a display title does) or a mark under two spacing units tall.
            small = (b.kind == "text" and (not b.heading or any(
                x.kind == "text" and x.size and b.size and b.size * 2.5 <= x.size for x in (a, c)))) or (
                b.kind != "text" and b.box[3] < 2 * unit)
            if not small or min(g1, g2) < t["float_units"] * unit or max(g1, g2) > t["float_ratio"] * min(g1, g2):
                continue
            if _alike(a, b) or _alike(b, c) or reported(a, b) or reported(b, c):
                continue
            seen.update({(id(a), id(b)), (id(b), id(c))})
            emit("uneven_rhythm", f"{b.item['name']!r} floats midway: {g1:.0f} px below {a.item['name']!r} and "
                 f"{g2:.0f} px above {c.item['name']!r}, so it belongs to neither. Move it close to the block it "
                 f"goes with (about one spacing unit, {unit:g} px) and let the larger gap separate the groups",
                 [a, b, c], _union([x.box for x in (a, b, c)]), actual=round(max(g1, g2) / min(g1, g2), 2),
                 expected=t["float_ratio"], values={"gaps": [round(g1, 1), round(g2, 1)], "floating": b.item["name"]},
                 threshold={"max_ratio": t["float_ratio"], "min_gap_px": round(t["float_units"] * unit, 1)})


def crowding(blocks, unit, emit):
    t = THRESHOLDS
    limit = t["crowding_units"] * unit
    for upper, lower, gap in stacked_gaps(blocks):
        if not (upper.kind in ("rule", "band") or upper.heading):
            continue
        if upper.decoration and upper.kind not in ("rule", "band"):
            continue
        if lower.kind != "text" or lower.container is upper or upper.container is lower or gap >= limit or gap < -2:
            continue
        if _x_overlap(upper, lower) <= 0.3 * min(upper.box[2], lower.box[2]):
            continue
        what = "rule" if upper.kind == "rule" else "band" if upper.kind == "band" else "heading"
        emit("crowding", f"The {what} {upper.item['name']!r} is {max(gap, 0):.0f} px above "
             f"{lower.item['name']!r}, under half a spacing unit ({limit:g} px): it presses onto the block below. "
             f"Leave at least {math.ceil(unit):g} px",
             [upper.item, lower.item], _union([upper.box, lower.box]), actual=round(gap, 1), expected=round(limit, 1),
             values={"gap": round(gap, 1), "kind": what}, threshold={"min_gap_px": round(limit, 1)})


def clumped_scatter(candidate, resolved, geometry, scatters, emit):
    import numpy as np

    t = THRESHOLDS
    children = {}
    for item in resolved.values():
        if item.get("parent"):
            children.setdefault(item["parent"], []).append(item)
    for group in scatters:
        items = [kid for kid in children.get(group["id"], []) if kid["visible"]
                 and not kid["name"].endswith("/background") and kid.get("role") != "background"]
        if len(items) < t["scatter_min_items"]:
            continue
        recipe = group.get("pattern_scatter") or {}
        gx, gy, gw, gh = geometry[group["id"]]
        if recipe.get("width") and recipe.get("height"):
            scale = gw / max(1e-9, group.get("content_width") or recipe["width"])
            gw, gh = recipe["width"] * scale, recipe["height"] * scale
        if gw <= 0 or gh <= 0:
            continue
        cells, size = 4, 64
        grid = np.zeros((size, size))
        for kid in items:
            x, y, w, h = geometry[kid["id"]]
            c0, c1 = int((x - gx) / gw * size), math.ceil((x + w - gx) / gw * size)
            r0, r1 = int((y - gy) / gh * size), math.ceil((y + h - gy) / gh * size)
            grid[max(0, r0):max(0, min(size, r1)), max(0, c0):max(0, min(size, c1))] = 1
        coverage = grid.reshape(cells, size // cells, cells, size // cells).mean(axis=(1, 3))
        mean = float(coverage.mean())
        if mean <= 0:
            continue
        cv = float(coverage.std()) / mean
        if cv <= t["scatter_cv"]:
            continue
        empty = int((coverage < 0.05).sum())
        emit("clumped_scatter", f"The scatter {group['name']!r} is clumped: motif coverage varies by {cv:.2f} "
             f"(coefficient of variation over {cells}×{cells} cells; {empty} of {cells * cells} cells are nearly "
             "empty), so it reads as bunches and holes. Re-seed it, raise the spacing or count, or move the "
             "largest motifs into the gaps",
             [group], (gx, gy, gw, gh), actual=round(cv, 3), expected=t["scatter_cv"],
             values={"coverage_cv": round(cv, 3), "empty_cells": empty, "cells": cells * cells,
                     "items": len(items)},
             threshold={"max_cv": t["scatter_cv"]})


def check(candidate, resolved, geometry, content, role, ancestors, issue, local_bounds=None):
    """Run the composition family on a check_design candidate, reporting through ``issue``. With the candidate's
    ``local_bounds`` (layout boxes), text is measured from the top to the bottom of its glyphs."""
    from .craft import body_size

    canvas = candidate.state["canvas"]
    width, height = canvas["width"], canvas["height"]
    unit = float(unit_of(candidate))
    if local_bounds is not None:
        geometry = ink_heights(candidate, resolved, geometry, content, local_bounds)
    blocks, grounds, scatters = collect(candidate, resolved, geometry, content, role, ancestors, width, height)
    pending = []

    def emit(code, message, layers, region, *, actual, expected, values, threshold):
        items = []
        for x in layers:
            x = x.item if isinstance(x, Block) else x
            if x is not None and all(x["id"] != y["id"] for y in items):
                items.append(x)
        pending.append((code, message, items, {
            "code": code, "action": "review", "region": _round(region),
            "measured": {"actual": actual, "expected": expected,
                         "unit": "ratio" if code in ("clumped_scatter", "uneven_rhythm") else "px"},
            "values": values, "threshold": threshold, "spacing_unit": unit}))

    dead_bands(blocks, grounds, unit, width, height, emit)
    margin_drift(blocks, unit, emit, width * height)
    uneven_rhythm(blocks, unit, emit, body_size(candidate))
    floating(blocks, unit, emit, [entry[3]["region"] for entry in pending if entry[0] == "dead_band"])
    crowding(blocks, unit, emit)
    clumped_scatter(candidate, resolved, geometry, scatters, emit)
    # A page of scattered labels can drift in hundreds of pairs: report the first few of each kind and count
    # the rest on the last one, so the findings stay readable.
    for code in CODES:
        mine = [entry for entry in pending if entry[0] == code]
        for index, (_, message, items, extra) in enumerate(mine[:MAX_PER_CODE]):
            if index == MAX_PER_CODE - 1 and len(mine) > MAX_PER_CODE:
                more = len(mine) - MAX_PER_CODE
                message += f" ({more} more {code} finding{'s' if more > 1 else ''} not listed)"
                extra = {**extra, "omitted": more}
            issue("composition", "warning", message, items, **extra)
