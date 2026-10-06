"""Scatter motifs inside or along a layer's outline, and seamless scattered pattern tiles.

``scatter`` places copies of one or more motif layers (or a built-in mark) inside a region layer's
outline with Poisson-disc spacing, or along its edge pointing out, along or in a cone. Every
copy gets seeded rotation, scale, position and tone jitter. Copies are ordinary layers grouped
under one name, or, with ``merge``, one path layer per tone, so a thousand marks cost a few layers.
The ``fur`` preset grows tufts along the edge and a second layer of inner flicks.

``pattern-scatter`` scatters motifs in a W x H tile with toroidal (wrap-around) Poisson-disc
spacing; a copy that crosses an edge gets a wrapped ghost on the opposite side, so the tile
repeats without a seam. The recipe stays on the group, so applying it again after editing a
motif rebuilds and re-wraps the tile, and the result reports a seam score.

The shared helpers also serve ``repeat`` and ``radial-repeat`` (per-step transforms, jitter,
``merge``) and the ``plush`` look. Everything is deterministic for a given ``seed``.
"""

from copy import deepcopy
import math

import numpy as np

from .errors import require
from .geometry import compact_number
from .model import finite, uid

TYPES = ("scatter", "pattern-scatter")
PLACEMENTS = ("inside", "along")
DIRECTIONS = ("normal", "tangent", "cone", "random")
ANCHORS = ("center", "base")
PRESETS = ("fur",)
MAX_ITEMS = 5000
MAX_COMMANDS = 8000  # per merged path; geometry.parse_path accepts 8192
MAX_POISSON_CELLS = 4_000_000
# Built-in marks in a 100 x 100 view, drawn pointing up with their base at the bottom centre.
MARKS = {
    "tuft": "M30 100 Q28 52 10 0 Q44 38 50 100 Z M40 100 Q47 46 50 0 Q58 46 62 100 Z "
            "M52 100 Q70 50 90 2 Q76 52 72 100 Z",
    "flick": "M42 100 Q47 52 38 0 Q58 48 58 100 Z",
}
STEP_KEYS = ("rotation_step", "scale_step", "opacity_step", "seed", "rotation_jitter", "scale_jitter",
             "position_jitter", "opacity_jitter", "merge")
RECIPE_KEYS = ("source", "mark", "width", "height", "spacing", "count", "seed", "scale", "scale_jitter", "rotation",
               "rotation_jitter", "colors", "tone_variation", "tones", "background", "merge", "pattern")


def stream(seed, *keys):
    return np.random.default_rng([int(seed), *keys])


# ---------------------------------------------------------------------------------------------
# Schema


def schemas(add):
    from .schema import S, N, B, field

    refs = {"anyOf": [S, {"type": "array", "items": S, "minItems": 1, "maxItems": 32}]}
    positive = {"type": "number", "exclusiveMinimum": 0}
    shared = {
        "source": {**refs, "description": "Motif layer(s) to copy: one ID or name, or a list (picked at random per copy)."},
        "mark": {"type": "object", "description": "A motif drawn on the fly instead of source: a shape spec "
                 "{shape, width, height, fill, stroke, stroke_width, path} as the shape operation takes it, or "
                 "{mark: tuft|flick, width, height, fill}."},
        "spacing": field(positive, "Minimum distance between copies in pixels (Poisson-disc), or the step along an edge."),
        "count": {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS,
                  "description": f"How many copies to aim for (1-{MAX_ITEMS}); sets spacing when spacing is omitted."},
        "seed": {"type": "integer", "minimum": 0, "description": "Seed: the same seed always gives the same scatter."},
        "scale": field(positive, "Base size of each copy relative to its motif (default 1)."),
        "scale_jitter": {"type": "number", "minimum": 0, "maximum": 0.95,
                         "description": "Random size change per copy, as a fraction (0.2 = up to 20% larger or smaller)."},
        "rotation": field(N, "Base rotation added to every copy, in degrees."),
        "rotation_jitter": {"type": "number", "minimum": 0, "maximum": 180,
                            "description": "Random turn per copy, up to this many degrees either way."},
        "colors": {"type": "array", "items": S, "minItems": 1, "maxItems": 32,
                   "description": "Fill colors picked at random per copy (shape motifs, and shapes inside group motifs)."},
        "tone_variation": {"type": "number", "minimum": 0, "maximum": 0.5,
                           "description": "Random lightness change per copy (OKLab L, 0.05 is subtle), in tones steps."},
        "tones": {"type": "integer", "minimum": 2, "maximum": 9,
                  "description": "How many lightness steps tone_variation uses (default 3); merge makes one path per tone."},
        "merge": field(B, "Draw all copies as one path layer per color/tone instead of a layer per copy (needs shape motifs)."),
        "name": field(S, "Name of the group (or merged layer) that holds the result."),
        "hide_source": field(B, "Hide the motif layers after copying them (default true)."),
    }
    add("scatter", {
        **shared,
        "placement": {"enum": list(PLACEMENTS), "description": "inside the target's outline (default) or along its edge."},
        "direction": {"enum": list(DIRECTIONS), "description": "Along an edge: copies point out along the normal "
                      "(default), along the tangent, in a cone around the normal (spread), or at random."},
        "spread": {"type": "number", "minimum": 0, "maximum": 360, "description": "Cone width in degrees (default 60)."},
        "anchor": {"enum": list(ANCHORS), "description": "Which point of a copy sits on the sample point: its centre, "
                   "or its base (bottom centre; default along an edge, so tufts and blades grow out of it)."},
        "offset": field(N, "Along an edge: move the sample points out (positive) or in (negative) by this many pixels."),
        "exclude": {"type": "array", "items": S, "minItems": 1, "maxItems": 64,
                    "description": "Layers whose outlines stay clear of copies."},
        "exclude_margin": {"type": "number", "minimum": 0, "description": "Extra clearance around exclude, in pixels."},
        "position_jitter": {"type": "number", "minimum": 0, "description": "Random move per copy, up to this many pixels."},
        "preset": {"enum": list(PRESETS), "description": "fur: tufts along the edge pointing out (behind the target) "
                   "plus a layer of inner flicks (above it), merged, colored from the target."},
        "length": field(positive, "fur: tuft length in pixels (default about 7% of the target's short side)."),
        "flicks": {"type": "number", "minimum": 0, "maximum": 2,
                   "description": "fur: inner flicks per tuft (default 0.5; 0 for none)."},
    }, ["target"], anyOf=[{"required": ["source"]}, {"required": ["mark"]}, {"required": ["preset"]}])
    add("pattern-scatter", {
        **shared,
        "width": field(positive, "Tile width in pixels."),
        "height": field(positive, "Tile height in pixels."),
        "x": field(N, "Tile left edge in pixels (default 0)."),
        "y": field(N, "Tile top edge in pixels (default 0)."),
        "background": field(S, "Tile background color (a rectangle at the bottom of the tile); omit for transparent."),
        "pattern": field(S, "Also save the tile as a document pattern of this name, for pattern-fill."),
    }, anyOf=[{"required": ["source"]}, {"required": ["mark"]}, {"required": ["target"]}])


# ---------------------------------------------------------------------------------------------
# Geometry


def _matrices(project):
    from .render import resolve_layout, resolved_layers

    layers = resolved_layers(project)
    index = {layer["id"]: layer for layer in layers}
    return index, resolve_layout(project, layers=layers)


def parent_matrix(project, layer, cache=None):
    """Matrix from ``layer``'s parent space to the canvas."""
    from .checks import group_matrix

    index, local = cache or _matrices(project)
    return group_matrix(index[layer["id"]], index, local)


def outline(project, layer, space="canvas", cache=None):
    """``layer``'s outline as ``[(points, closed)]`` in canvas (or its parent's) pixels. Shapes give
    their drawn outline; every other layer its box."""
    from .affine import layer_matrix
    from .irregular import layer_outline
    from .render import rest_size

    index, local = cache or _matrices(project)
    resolved = index[layer["id"]]
    if layer["type"] == "shape" and not layer.get("repeat"):
        subs = [(p, c) for p, _, c in layer_outline(resolved, project)]
    else:
        w, h = rest_size(resolved)
        subs = [(np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=float), True)]
    matrix = layer_matrix(resolved, local[layer["id"]])
    if space == "canvas":
        matrix = parent_matrix(project, layer, (index, local)) @ matrix
    return [(_apply(matrix, p), c) for p, c in subs]


def _apply(matrix, points):
    p = np.asarray(points, dtype=float)
    return p @ matrix[:2, :2].T + matrix[:2, 2]


def _polygon(subs):
    """Even-odd area of the closed outlines as a shapely geometry (None when there is none)."""
    from shapely.geometry import Polygon

    area = None
    for points, closed in subs:
        if not closed or len(points) < 3:
            continue
        shape = Polygon(points).buffer(0)
        if shape.is_empty:
            continue
        area = shape if area is None else area.symmetric_difference(shape)
    return area


def outward_normals(points, closed):
    """Unit normals pointing out of a closed outline (an open line keeps its left-hand normals)."""
    from .irregular import normals
    from .trace import area

    n = normals(points, closed)
    return -n if closed and area(points) < 0 else n


def _poisson(rng, inside, bounds, spacing, count):
    """Bridson Poisson-disc samples inside ``bounds`` (x0, y0, x1, y1) where ``inside(x, y)``."""
    from .organic import _poisson as bridson

    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    extent = max(x1 - x0, y1 - y0) / 2 + spacing
    cells = (2 * extent / (spacing / math.sqrt(2)) + 1) ** 2
    require(cells <= MAX_POISSON_CELLS, f"spacing {spacing:g} is too small for a region this size; use at least "
            f"{2 * extent * math.sqrt(2) / math.sqrt(MAX_POISSON_CELLS):.1f} px", "resource_limit", field="spacing")
    samples = bridson(rng, spacing, count, lambda q: inside(q[0] + cx, q[1] + cy), extent)
    return [(float(x + cx), float(y + cy)) for x, y in samples]


def toroidal_poisson(rng, width, height, spacing, count):
    """Poisson-disc samples on a W x H torus: distances wrap across the edges, so the tile repeats
    with the same minimum spacing across its seams."""
    cell = spacing / math.sqrt(2)
    cols, rows = max(1, int(width // cell)), max(1, int(height // cell))
    require(cols * rows <= MAX_POISSON_CELLS, "spacing is too small for this tile", "resource_limit", field="spacing")
    cw, ch = width / cols, height / rows
    grid = -np.ones((rows, cols), dtype=int)
    reach_x, reach_y = int(math.ceil(spacing / cw)), int(math.ceil(spacing / ch))
    points, active = [], []

    def far_enough(x, y):
        gx, gy = int(x / cw) % cols, int(y / ch) % rows
        for j in range(-reach_y, reach_y + 1):
            for i in range(-reach_x, reach_x + 1):
                k = grid[(gy + j) % rows, (gx + i) % cols]
                if k >= 0:
                    dx = abs(points[k][0] - x)
                    dy = abs(points[k][1] - y)
                    dx, dy = min(dx, width - dx), min(dy, height - dy)
                    if dx * dx + dy * dy < spacing * spacing:
                        return False
        return True

    def put(x, y):
        grid[int(y / ch) % rows, int(x / cw) % cols] = len(points)
        points.append((x, y))
        active.append(len(points) - 1)

    put(*rng.uniform(0, 1, 2) * (width, height))
    while active and len(points) < count:
        k = active[rng.integers(len(active))]
        for _ in range(30):
            angle, distance = rng.uniform(0, math.tau), rng.uniform(spacing, 2 * spacing)
            x = (points[k][0] + distance * math.cos(angle)) % width
            y = (points[k][1] + distance * math.sin(angle)) % height
            if far_enough(x, y):
                put(x, y)
                break
        else:
            active.remove(k)
    return points[:count]


# ---------------------------------------------------------------------------------------------
# Copies and merged paths


def up_vector(rotation):
    a = math.radians(rotation)
    return math.sin(a), -math.cos(a)


def heading_rotation(dx, dy):
    """The rotation that turns a motif drawn pointing up to point along (dx, dy)."""
    return math.degrees(math.atan2(dx, -dy))


def placed(source, cx, cy, rotation=0.0, scale=1.0, flip_x=None, opacity=None, fill=None):
    """A copy of ``source`` (a layer dict) centred on (cx, cy), turned by ``rotation`` on top of its
    own and scaled; returns ``(copy, bounds)`` with bounds in the copy's parent space."""
    from .render import transformed_size

    item = deepcopy(source)
    item.pop("pivot", None)
    item["constraints"] = {}
    item["width"] = max(source["width"] * scale, 0.01)
    item["height"] = max(source["height"] * scale, 0.01)
    if item["type"] == "group":
        item["content_width"], item["content_height"] = source["content_width"], source["content_height"]
    if item["type"] == "shape" and item.get("stroke_width"):
        item["stroke_width"] = round(item["stroke_width"] * scale, 3)
    if item["type"] == "text" and "size" in item:
        item["size"] = max(1, round(item["size"] * scale))
    item["rotation"] = (source.get("rotation", 0) + rotation) % 360
    if flip_x is not None:
        item["flip_x"] = flip_x
    if opacity is not None:
        item["opacity"] = round(min(max(opacity, 0.0), 1.0), 4)
    if fill is not None and item["type"] == "shape":
        item["fill"] = fill
    tw, th = transformed_size(item)
    item["x"], item["y"] = cx - tw / 2, cy - th / 2
    return item, (item["x"], item["y"], tw, th)


def item_commands(project, layer, bounds):
    """``layer``'s outline as path commands ``[(letter, [x, y, ...])]`` in its parent's pixels."""
    from .affine import layer_matrix
    from .geometry import parse_path
    from .irregular import layer_path

    path, (sx, sy), (ox, oy) = layer_path(layer, project)
    matrix = layer_matrix(layer, bounds)
    out = []
    for letter, values in parse_path(path):
        if letter == "Z":
            out.append(("Z", []))
            continue
        local = np.array(values, dtype=float).reshape(-1, 2) * (sx, sy) + (ox, oy)
        out.append((letter, list(_apply(matrix, local).ravel())))
    return out


STYLE_KEYS = ("fill", "stroke", "stroke_width", "line_cap", "line_join", "dash", "opacity", "blend")


def _style_key(project, layer):
    from .geometry import default_fill

    values = [default_fill(layer) if key == "fill" else layer.get(key) for key in STYLE_KEYS]
    return repr(values)


def merged(project, entries, name):
    """One path layer per style for ``entries`` [(shape layer, bounds)] (none of them in the
    document). Returns the new layer dicts (unparented), each under MAX_COMMANDS commands."""
    from .geometry import default_fill

    groups = {}
    for layer, bounds in entries:
        require(layer["type"] == "shape", f"merge needs shape motifs; {layer['name']!r} is a {layer['type']} layer. "
                "Leave merge off, or use shape motifs", field="merge")
        groups.setdefault(_style_key(project, layer), []).append((layer, bounds))
    result = []
    for members in groups.values():
        chunks, chunk, used = [], [], 0
        for layer, bounds in members:
            commands = item_commands(project, layer, bounds)
            require(len(commands) <= MAX_COMMANDS, f"{layer['name']!r} has too many path commands to merge",
                    "resource_limit", field="merge")
            if used + len(commands) > MAX_COMMANDS:
                chunks.append(chunk)
                chunk, used = [], 0
            chunk.append(commands)
            used += len(commands)
        chunks.append(chunk)
        template = members[0][0]
        for chunk in chunks:
            values = np.array([v for commands in chunk for _, vals in commands for v in vals], dtype=float).reshape(-1, 2)
            stroked = str(template.get("stroke", "transparent")).strip().lower() not in ("", "none", "transparent")
            pad = (template.get("stroke_width", 1) / 2 + 1) if stroked else 1
            x0, y0 = math.floor(values[:, 0].min() - pad), math.floor(values[:, 1].min() - pad)
            w = max(1, math.ceil(values[:, 0].max() + pad) - x0)
            h = max(1, math.ceil(values[:, 1].max() + pad) - y0)
            parts = []
            for commands in chunk:
                for letter, vals in commands:
                    shifted = [v - (x0 if i % 2 == 0 else y0) for i, v in enumerate(vals)]
                    parts.append(letter + " ".join(compact_number(v, 2) for v in shifted))
            layer = deepcopy(template)
            for key in ("pivot", "skew_x", "skew_y", "affine", "radius", "sides", "inner_radius", "irregular", "organic",
                        "scatter", "pattern_scatter", "radial", "repeat", "looks", "part_of", "parent", "path_nodes"):
                layer.pop(key, None)
            layer.update(id=uid("lyr"), name=name, shape="path", path=" ".join(parts), path_view=[w, h], width=w,
                         height=h, x=x0, y=y0, rotation=0, flip_x=False, flip_y=False, constraints={},
                         fill=default_fill(template))
            if "styles" in layer and not layer["styles"]:
                layer.pop("styles")
            project.limits.size(w, h, vector=True)
            result.append(layer)
    return result


class Namer:
    """Free layer names without rescanning the document for every copy."""

    def __init__(self, project):
        self.taken = {x["name"] for x in project.state["layers"]} | {x["id"] for x in project.state["layers"]}

    def __call__(self, base, explicit=False):
        if explicit:
            require(base not in self.taken, f"Layer name already exists: {base}", field="name")
            self.taken.add(base)
            return base
        name, index = base, 2
        while name in self.taken:
            name, index = f"{base} {index}", index + 1
        self.taken.add(name)
        return name


def budget(project, needed, what="copies"):
    room = project.limits.max_layers - len(project.state["layers"])
    require(needed <= room, f"These {what} need {needed} layers and the document has room for {room} more (at most "
            f"{project.limits.max_layers}); use merge: true to draw them as one path per tone, or fewer copies",
            "resource_limit", field="merge")


def add_copies(project, entries, parent, namer, base):
    # Copies are named BASE/1, BASE/2 ... after the group (or tile) that holds them.
    """Put placed copies into the document under ``parent``; group motifs bring copies of their
    children. Returns the new top-level copy ids."""
    from .design import descendants

    budget(project, sum(1 + _child_count(project, layer) for layer, _ in entries))
    ids = []
    layers = project.state["layers"]
    for number, (layer, _) in enumerate(entries, 1):
        source_id = layer.pop("source_id", None)
        layer.update(id=uid("lyr"), name=namer(f"{base}/{number}"))
        if parent is None:
            layer.pop("parent", None)
        else:
            layer["parent"] = parent
        if layer["type"] == "group" and source_id:
            inside = descendants(project, source_id)
            children = [deepcopy(x) for x in layers if x["id"] in inside]
            mapping = {source_id: layer["id"], **{x["id"]: uid("lyr") for x in children}}
            for child in children:
                child.update(id=mapping[child["id"]], name=namer(f"{layer['name']}/{child['name']}"),
                             parent=mapping[child["parent"]])
                if child.get("clip") in mapping:
                    child["clip"] = mapping[child["clip"]]
                child.pop("part_of", None)
                layers.append(child)
        layers.append(layer)
        ids.append(layer["id"])
    return ids


def gather(project, group):
    """Move every descendant of ``group`` (in its current order) to just before the group, where
    the group operation keeps children."""
    from .design import descendants

    inside = descendants(project, group["id"])
    order = project.state["layers"]
    moved = [x for x in order if x["id"] in inside]
    rest = [x for x in order if x["id"] not in inside]
    at = rest.index(group)
    order[:] = rest[:at] + moved + rest[at:]


def _child_count(project, layer):
    if layer["type"] != "group":
        return 0
    from .design import descendants

    return len(descendants(project, layer.get("source_id", layer["id"])))


def recolor_group(project, group_id, fill_fn):
    from .design import descendants

    inside = descendants(project, group_id)
    for item in project.state["layers"]:
        if item["id"] in inside and item["type"] == "shape" and str(item.get("fill", "white")).lower() != "transparent":
            item["fill"] = fill_fn(item["fill"])


# ---------------------------------------------------------------------------------------------
# Motifs, tones and jitter


def _mark_layer(project, spec, namer, default_fill="#2f2f2f"):
    """A motif from a ``mark`` spec: a built-in mark or a shape spec (validated by the shape operation)."""
    from .model import new_layer
    from .operations import execute as apply

    require(isinstance(spec, dict), "mark must be an object", field="mark")
    if "mark" in spec:
        require(spec["mark"] in MARKS, f"mark must be one of {', '.join(MARKS)}", field="mark.mark", allowed=list(MARKS))
        require(not set(spec) - {"mark", "width", "height", "fill", "stroke", "stroke_width"},
                "a built-in mark takes width, height, fill, stroke and stroke_width", field="mark")
        w = finite(spec.get("width", 12), "mark.width", 0.5, 4096)
        h = finite(spec.get("height", 24), "mark.height", 0.5, 4096)
        return new_layer(spec["mark"], "shape", w, h, shape="path", path=MARKS[spec["mark"]], path_view=[100, 100],
                         fill=spec.get("fill", default_fill), stroke=spec.get("stroke", "transparent"),
                         stroke_width=spec.get("stroke_width", 0))
    allowed = {"shape", "width", "height", "fill", "stroke", "stroke_width", "path", "radius", "sides", "inner_radius",
               "line_cap"}
    require(not set(spec) - allowed, f"mark takes {', '.join(sorted(allowed))}", field="mark")
    label = namer("scatter-mark")
    apply(project, {"type": "shape", **{k: deepcopy(v) for k, v in spec.items()}, "name": label})
    layer = project.layer(label)
    project.state["layers"].remove(layer)
    return deepcopy(layer)


def motif_sources(project, op, namer, default_fill="#2f2f2f"):
    """The motif layer dicts for ``source`` or ``mark``, plus the document layers to hide afterwards."""
    if "mark" in op:
        require("source" not in op, "Pass source or mark, not both", field="mark")
        return [_mark_layer(project, op["mark"], namer, default_fill)], []
    refs = op["source"] if isinstance(op["source"], list) else [op["source"]]
    layers = [project.layer(ref) for ref in refs]
    require(len({x["id"] for x in layers}) == len(layers), "source lists a layer twice", field="source")
    sources = []
    for layer in layers:
        require(layer["type"] not in ("field", "adjustment"), f"{layer['name']!r} is a {layer['type']} layer and "
                "cannot be scattered", field="source")
        copy = deepcopy(layer)
        copy["source_id"] = layer["id"]
        copy["visible"] = True
        copy.pop("parent", None)
        sources.append(copy)
    return sources, layers


class Variation:
    """Seeded per-copy choices: which motif, size, turn, move, opacity and color."""

    def __init__(self, project, op, sources, seed):
        self.project, self.sources, self.seed = project, sources, seed
        self.rng = stream(seed, 2)
        self.scale = finite(op.get("scale", 1), "scale", 0.001, 1000)
        self.scale_jitter = finite(op.get("scale_jitter", 0), "scale_jitter", 0, 0.95)
        self.rotation = finite(op.get("rotation", 0), "rotation", -3600, 3600)
        self.rotation_jitter = finite(op.get("rotation_jitter", 0), "rotation_jitter", 0, 180)
        self.position_jitter = finite(op.get("position_jitter", 0), "position_jitter", 0, 100000)
        self.colors = op.get("colors") or []
        self.tone = finite(op.get("tone_variation", 0), "tone_variation", 0, 0.5)
        self.tones = op.get("tones", 3)
        require(isinstance(self.tones, int) and 2 <= self.tones <= 9, "tones must be 2-9", field="tones")
        from .design import resolve_color
        from .render import color

        for value in self.colors:
            color(resolve_color(value, project.state))

    def pick(self):
        rng = self.rng
        draw = [float(v) for v in rng.uniform(-1, 1, 5)]
        source = self.sources[int(rng.integers(len(self.sources)))] if len(self.sources) > 1 else self.sources[0]
        scale = self.scale * (1 + self.scale_jitter * draw[0])
        turn = self.rotation + self.rotation_jitter * draw[1]
        angle, radius = (draw[2] + 1) * math.pi, self.position_jitter * math.sqrt(abs(draw[3]))
        move = (radius * math.cos(angle), radius * math.sin(angle))
        color = self.colors[int(rng.integers(len(self.colors)))] if self.colors else None
        step = int(round((draw[4] + 1) / 2 * (self.tones - 1))) if self.tone else None
        return source, scale, turn, move, color, step

    def fill(self, value, step):
        """``value`` shifted to tone ``step`` (of ``tones``) within ±tone_variation lightness."""
        if step is None or not self.tone or value in (None, "transparent", "none"):
            return value
        from .irregular import drifted

        u = -1 + 2 * step / (self.tones - 1)
        return drifted(value, self.project, (u, 0.0, 0.0), self.tone, 0.0, 0.0)


def build(project, variation, points, anchor):
    """Placed copies for ``points`` [(x, y, heading or None)]. A heading turns the motif to point
    along it; ``base`` anchoring puts the motif's bottom centre on the point."""
    entries = []
    for x, y, heading in points:
        source, scale, turn, (mx, my), color, step = variation.pick()
        rotation = turn + (heading if heading is not None else 0)
        cx, cy = x + mx, y + my
        if anchor == "base":
            ux, uy = up_vector(source.get("rotation", 0) + rotation)
            half = source["height"] * scale / 2
            cx, cy = cx + ux * half, cy + uy * half
        layer, bounds = placed(source, cx, cy, rotation, scale)
        if source["type"] == "shape":
            from .geometry import default_fill

            own = default_fill(source)
            if color is None and str(own).strip().lower() in ("transparent", "none"):
                # A line-only motif keeps no fill; its tone goes to the stroke.
                layer["fill"] = own
                if str(layer.get("stroke", "transparent")).strip().lower() not in ("transparent", "none"):
                    layer["stroke"] = variation.fill(layer["stroke"], step)
            else:
                layer["fill"] = variation.fill(color or own, step)
        elif source["type"] == "group" and (color is not None or step is not None):
            layer["recolor"] = (color, step)
        entries.append((layer, bounds))
    return entries


def finish_copies(project, variation, ids, entries):
    """Apply the colour choices recorded on group copies to their shape children."""
    for ident, (layer, _) in zip(ids, entries):
        recolor = layer.pop("recolor", None)
        if recolor:
            color, step = recolor
            recolor_group(project, ident, lambda value: variation.fill(color or value, step))


# ---------------------------------------------------------------------------------------------
# scatter


def _clear(project, op, region, cache, into_parent):
    """The area copies must avoid: the exclude layers' outlines grown by exclude_margin."""
    from shapely.geometry import LineString

    refs = op.get("exclude") or []
    margin = finite(op.get("exclude_margin", 0), "exclude_margin", 0, 100000)
    blocked = None
    for ref in refs:
        layer = project.layer(ref)
        require(layer["id"] != region["id"], "exclude cannot name the target itself", field="exclude")
        subs = [(_apply(into_parent, p), c) for p, c in outline(project, layer, "canvas", cache)]
        area = _polygon(subs)
        lines = [LineString(p) for p, c in subs if not c and len(p) >= 2]
        for shape in ([area] if area is not None else []) + lines:
            grown = shape.buffer(margin) if margin or shape.geom_type == "LineString" else shape
            blocked = grown if blocked is None else blocked.union(grown)
    return blocked


def scatter_points(project, op, region, subs, blocked, rng, variation):
    """Sample points [(x, y, heading)] for ``placement`` inside or along ``subs``."""
    import shapely

    placement = op.get("placement", "inside")
    count = op.get("count")
    spacing = op.get("spacing")
    if placement == "inside":
        area = _polygon(subs)
        require(area is not None and area.area > 0, f"{region['name']!r} has no closed outline to scatter inside; use "
                "placement: along", field="target")
        if blocked is not None:
            area = area.difference(blocked)
        require(not area.is_empty, "The exclude layers cover the whole target", field="exclude")
        if spacing is None:
            if count is not None:
                spacing = math.sqrt(0.68 * area.area / count)
            else:
                spacing = 1.1 * max(max(s["width"], s["height"]) for s in variation.sources) * variation.scale
        spacing = max(float(spacing), 1.0)
        shapely.prepare(area)
        x0, y0, x1, y1 = area.bounds
        samples = _poisson(rng, lambda x, y: bool(shapely.contains_xy(area, x, y)), (x0, y0, x1, y1), spacing,
                           count or MAX_ITEMS)
        return [(x, y, None) for x, y in samples], spacing
    direction = op.get("direction", "normal")
    spread = finite(op.get("spread", 60), "spread", 0, 360)
    offset = finite(op.get("offset", 0), "offset", -100000, 100000)
    from .irregular import resample
    from .trace import length

    total = sum(length(p, c) for p, c in subs)
    require(total > 0, f"{region['name']!r} has no edge to scatter along", field="target")
    if spacing is None:
        spacing = total / count if count else max(2.0, 0.6 * min(max(s["width"], s["height"]) for s in variation.sources)
                                                   * variation.scale)
    spacing = max(float(spacing), 0.5)
    require(total / spacing <= MAX_ITEMS * 1.05, f"spacing {spacing:g} gives more than {MAX_ITEMS} copies along this "
            "edge; use a larger spacing", "resource_limit", field="spacing")
    points = []
    for p, closed in subs:
        if len(p) < 2:
            continue
        fine, _, _ = resample(p, closed, spacing / 4)
        normals = outward_normals(fine, closed)
        arc = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.vstack([fine, fine[:1]]) if closed else fine,
                                                                        axis=0).T))])
        span = arc[-1]
        n = max(1, int(round(span / spacing)))
        start = float(rng.uniform(0, spacing)) if closed else 0.0
        stations = (start + np.arange(n) * span / n) % span if closed else np.linspace(0, span, n + 1 if n > 1 else 1)
        seq = np.vstack([fine, fine[:1]]) if closed else fine
        nseq = np.vstack([normals, normals[:1]]) if closed else normals
        for s in stations:
            x, y = np.interp(s, arc, seq[:, 0]), np.interp(s, arc, seq[:, 1])
            nx, ny = np.interp(s, arc, nseq[:, 0]), np.interp(s, arc, nseq[:, 1])
            norm = math.hypot(nx, ny) or 1.0
            nx, ny = nx / norm, ny / norm
            x, y = x + nx * offset, y + ny * offset
            if direction == "normal":
                heading = heading_rotation(nx, ny)
            elif direction == "tangent":
                heading = heading_rotation(-ny, nx)
            elif direction == "cone":
                heading = heading_rotation(nx, ny) + float(rng.uniform(-spread / 2, spread / 2))
            else:
                heading = float(rng.uniform(0, 360))
            points.append((float(x), float(y), heading))
    if blocked is not None and points:
        keep = shapely.contains_xy(blocked, np.array([q[0] for q in points]), np.array([q[1] for q in points]))
        points = [q for q, hit in zip(points, keep) if not hit]
    return points[:MAX_ITEMS], spacing


def _fur_settings(project, op, region, subs):
    from .design import resolve_color

    xs = np.vstack([p for p, _ in subs])
    short = float(min(np.ptp(xs[:, 0]), np.ptp(xs[:, 1]))) or 100.0
    length = finite(op.get("length", min(max(short * 0.07, 4.0), 200.0)), "length", 0.5, 4096)
    base = region.get("fill") if region["type"] == "shape" else region.get("color")
    if not isinstance(base, str) or base.strip().lower() in ("transparent", "none", ""):
        base = "#8b6b4a"
    resolve_color(base, project.state)
    return length, base


def _insert(project, layers, region, below=False):
    """Insert ``layers`` (already parented like ``region``) right above (or below) it."""
    order = project.state["layers"]
    budget(project, len(layers), "layers")
    at = order.index(region) + (0 if below else 1)
    order[at:at] = layers


def execute_scatter(project, op):
    region = project.layer(op.get("target"))
    preset = op.get("preset")
    seed = op.get("seed", 0)
    require(isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0, "seed must be a whole number",
            field="seed")
    namer = Namer(project)
    cache = _matrices(project)
    into_parent = np.linalg.inv(parent_matrix(project, region, cache))
    subs = [(_apply(into_parent, p), c) for p, c in outline(project, region, "canvas", cache)]
    blocked = _clear(project, op, region, cache, into_parent)
    name = op.get("name") or f"{region['name']}-{preset or 'scatter'}"
    explicit = "name" in op
    parent = region.get("parent")
    hide = []
    if preset == "fur":
        length, base = _fur_settings(project, op, region, subs)
        settings = {"placement": "along", "direction": "cone", "spread": 50, "anchor": "base", "merge": True,
                    "scale_jitter": 0.25, **({} if "count" in op else {"spacing": length * 0.32}), **op}
        if "source" in op or "mark" in op:
            sources, hide = motif_sources(project, op, namer, base)
        else:
            sources = [_mark_layer(project, {"mark": "tuft", "width": length * 0.6, "height": length, "fill": base},
                                   namer)]
    else:
        settings = dict(op)
        sources, hide = motif_sources(project, op, namer)
    for source in sources:
        require(source.get("source_id") != region["id"], "source cannot be the target itself", field="source")
    variation = Variation(project, settings, sources, seed)
    rng = stream(seed, 1)
    points, spacing = scatter_points(project, settings, region, subs, blocked, rng, variation)
    require(points, "No copies fit: the target is too small for this spacing, or exclude covers it", field="spacing")
    anchor = settings.get("anchor", "base" if settings.get("placement") == "along" else "center")
    entries = build(project, variation, points, anchor)
    report = {"name": name, "copies": len(entries), "spacing": round(spacing, 2), "seed": seed}
    recipe = {k: deepcopy(v) for k, v in op.items() if k not in ("type", "target")}
    recipe["region"] = region["id"]
    merge = bool(settings.get("merge"))
    created = place_result(project, entries, variation, name, explicit, parent, region, merge, namer,
                           below=preset == "fur")
    report["name"], report["layers"] = created[0], created
    if preset == "fur":
        flicks = finite(op.get("flicks", 0.5), "flicks", 0, 2)
        if flicks > 0:
            flick = [_mark_layer(project, {"mark": "flick", "width": length * 0.22, "height": length * 0.7,
                                           "fill": f"darken({base}, 12%)"}, namer)]
            inner = {**settings, "offset": -length * 0.55 + op.get("offset", 0), "direction": "cone", "spread": 30,
                     "spacing": spacing / flicks}
            inner.pop("count", None)
            fv = Variation(project, inner, flick, seed + 1)
            fpoints, _ = scatter_points(project, inner, region, subs, blocked, stream(seed, 3), fv)
            if fpoints:
                flick_entries = build(project, fv, fpoints, "base")
                report["flicks"] = len(flick_entries)
                report["layers"] += place_result(project, flick_entries, fv, f"{name}-flicks",
                                                 False, parent, region, merge, namer)
    first = project.layer(report["layers"][0])
    first["scatter"] = recipe
    if op.get("hide_source", True):
        for layer in hide:
            layer["visible"] = False
    from .selectors import record

    record(project, "scatter", report)
    project.state["active_layer"] = first["id"]


def place_result(project, entries, variation, name, explicit, parent, region, merge, namer, below=False):
    """Add copies (grouped) or merged paths next to ``region``; returns the names of the top layers."""
    from .operations import execute as apply

    label = namer(name, explicit)
    if merge:
        layers = merged(project, entries, label)
        for i, layer in enumerate(layers):
            layer["name"] = label if len(layers) == 1 else namer(f"{label}/tone-{i + 1}")
            if parent:
                layer["parent"] = parent
        _insert(project, layers, region, below)
        if len(layers) > 1:
            apply(project, {"type": "group", "name": label, "targets": [x["id"] for x in layers]})
        return [label]
    ids = add_copies(project, entries, parent, namer, label)
    finish_copies(project, variation, ids, entries)
    where = {"below": region["id"]} if below else {"above": region["id"]}
    apply(project, {"type": "group", "name": label, "targets": ids, **where})
    return [label]


# ---------------------------------------------------------------------------------------------
# pattern-scatter


def ghosts(bounds, width, height):
    """The (dx, dy) shifts that bring a copy with box ``bounds`` back into the W x H tile from
    across an edge (its wrapped ghosts)."""
    x, y, w, h = bounds
    out = []
    for dx in (-width, 0, width):
        for dy in (-height, 0, height):
            if (dx or dy) and x + dx < width and x + dx + w > 0 and y + dy < height and y + dy + h > 0:
                out.append((dx, dy))
    return out


def tile_image(project, group):
    """The tile exactly as it repeats: the group alone, cropped to its W x H box."""
    from copy import copy

    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    width, height = round(group["content_width"]), round(group["content_height"])
    candidate.state["canvas"].update(width=width, height=height, background="transparent")
    candidate.state.pop("pages", None)
    candidate.state.pop("artboards", None)
    for layer in candidate.state["layers"]:
        if not layer.get("parent") and layer["id"] != group["id"]:
            layer["visible"] = False
    tile = next(x for x in candidate.state["layers"] if x["id"] == group["id"])
    tile.update(x=0, y=0, constraints={}, rotation=0, flip_x=False, flip_y=False, width=width, height=height,
                opacity=1, visible=True, effects=[], mask=None)
    tile.pop("pivot", None)
    tile.pop("styles", None)
    return candidate.render()


def execute_pattern_scatter(project, op):
    from .design import descendants
    from .model import new_layer
    from .textures import seamless_check

    namer = Namer(project)
    group = None
    if op.get("target") is not None:
        group = project.layer(op["target"])
        require(group.get("pattern_scatter"), f"{group['name']!r} was not made by pattern-scatter; target a "
                "pattern-scatter tile, or omit target to make one", field="target")
        recipe = {**deepcopy(group["pattern_scatter"]), **{k: deepcopy(op[k]) for k in RECIPE_KEYS if k in op}}
        if "mark" in op:
            recipe.pop("source", None)
        if "source" in op:
            recipe.pop("mark", None)
    else:
        recipe = {k: deepcopy(op[k]) for k in RECIPE_KEYS if k in op}
        require("width" in recipe and "height" in recipe, "pattern-scatter needs the tile's width and height",
                field="width")
    width = finite(recipe["width"], "width", 1, 8192)
    height = finite(recipe["height"], "height", 1, 8192)
    project.limits.size(math.ceil(width), math.ceil(height))
    seed = recipe.get("seed", 0)
    require(isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0, "seed must be a whole number",
            field="seed")
    require("source" in recipe or "mark" in recipe, "pattern-scatter needs source or mark", field="source")
    sources, hide = motif_sources(project, recipe, namer)
    if group is not None:
        inside = descendants(project, group["id"])
        require(not any(s.get("source_id") in inside for s in sources), "A motif must live outside the tile it "
                "is scattered into", field="source")
    variation = Variation(project, recipe, sources, seed)
    count = recipe.get("count")
    spacing = recipe.get("spacing")
    if spacing is None:
        spacing = math.sqrt(0.68 * width * height / count) if count else \
            1.1 * max(max(s["width"], s["height"]) for s in sources) * variation.scale
    spacing = finite(float(spacing), "spacing", 1, 100000)
    points = toroidal_poisson(stream(seed, 1), width, height, spacing, count or MAX_ITEMS)
    entries = build(project, variation, [(x, y, None) for x, y in points], "center")
    wrapped = []
    for layer, bounds in entries:
        for dx, dy in ghosts(bounds, width, height):
            ghost = deepcopy(layer)
            ghost["x"] += dx
            ghost["y"] += dy
            wrapped.append((ghost, (bounds[0] + dx, bounds[1] + dy, bounds[2], bounds[3])))
    every = entries + wrapped
    if group is None:
        explicit = "name" in op
        label = namer(op.get("name") or "pattern-tile", explicit)
        group = new_layer(label, "group", width, height, x=op.get("x", 0), y=op.get("y", 0))
        group["content_width"], group["content_height"] = width, height
        budget(project, 1, "tile")
        project.state["layers"].append(group)
    else:
        from .timeline import prune_targets

        inside = descendants(project, group["id"])
        project.state["layers"][:] = [x for x in project.state["layers"] if x["id"] not in inside]
        prune_targets(project.state, inside)
        group.update(content_width=width, content_height=height)
    base = group["name"]
    children = []
    if recipe.get("background"):
        from .design import resolve_color
        from .render import color

        color(resolve_color(recipe["background"], project.state))
        children.append(new_layer(namer(f"{base}/background"), "shape", width, height, shape="rectangle",
                                  fill=recipe["background"], stroke="transparent", stroke_width=0))
    for layer in children:
        layer["parent"] = group["id"]
    if recipe.get("merge"):
        paths = merged(project, every, base)
        for i, layer in enumerate(paths):
            layer["name"] = namer(f"{base}/tone-{i + 1}" if len(paths) > 1 else f"{base}/motifs")
            layer["parent"] = group["id"]
        children += paths
        budget(project, len(children), "tile layers")
        project.state["layers"].extend(children)
    else:
        budget(project, len(children), "tile layers")
        project.state["layers"].extend(children)
        ids = add_copies(project, every, group["id"], namer, base)
        finish_copies(project, variation, ids, every)
    gather(project, group)
    stored = {k: v for k, v in recipe.items() if k in RECIPE_KEYS}
    stored["spacing_used"] = round(spacing, 3)
    if "source" in stored:
        stored["source"] = [s["source_id"] for s in sources]
    group["pattern_scatter"] = stored
    if op.get("hide_source", True):
        for layer in hide:
            layer["visible"] = False
    image = tile_image(project, group)
    check = seamless_check(image)
    report = {"name": group["name"], "copies": len(entries), "ghosts": len(wrapped), "spacing": round(spacing, 2),
              "seed": seed, "seam": check}
    if recipe.get("pattern"):
        from .assets import add_image
        from .design import named

        named(recipe["pattern"])
        patterns = project.state.setdefault("patterns", {})
        require(recipe["pattern"] in patterns or len(patterns) < 128, "Pattern library is full", "resource_limit")
        patterns[recipe["pattern"]] = {"asset": add_image(project, image), "width": image.width, "height": image.height,
                                       "check": check}
        report["pattern"] = recipe["pattern"]
    from .selectors import record

    record(project, "pattern_scatter", report)
    project.state["active_layer"] = group["id"]


def execute(project, op):
    if op["type"] == "scatter":
        return execute_scatter(project, op)
    return execute_pattern_scatter(project, op)


# ---------------------------------------------------------------------------------------------
# Per-step transforms for repeat and radial-repeat


def step_schema():
    """Fields ``repeat`` and ``radial-repeat`` share for per-step transforms, jitter and merge."""
    from .schema import B, N, field

    return {
        "rotation_step": field(N, "Degrees each copy turns more than the one before (about its own centre)."),
        "scale_step": {"type": "number", "exclusiveMinimum": 0, "maximum": 100,
                       "description": "Size factor applied once more per copy (0.9 = each copy 10% smaller)."},
        "opacity_step": {"type": "number", "minimum": -1, "maximum": 1,
                         "description": "Opacity added per copy (-0.1 fades each copy by 0.1; clamped to 0-1)."},
        "seed": {"type": "integer", "minimum": 0, "description": "Seed for the jitter fields (default 0)."},
        "rotation_jitter": {"type": "number", "minimum": 0, "maximum": 180,
                            "description": "Random turn per copy, up to this many degrees either way."},
        "scale_jitter": {"type": "number", "minimum": 0, "maximum": 0.95,
                         "description": "Random size change per copy, as a fraction."},
        "position_jitter": {"type": "number", "minimum": 0, "description": "Random move per copy, up to this many pixels."},
        "opacity_jitter": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": "Random opacity change per copy, up to this much either way."},
        "merge": field(B, "Draw every copy as one path layer (one per color) instead of a layer each; shape layers only."),
    }


def step_arguments(parser):
    """CLI flags for the per-step fields of repeat and radial-repeat."""
    for key in ("rotation-step", "scale-step", "opacity-step", "rotation-jitter", "scale-jitter", "position-jitter",
                "opacity-jitter"):
        parser.add_argument("--" + key, type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--merge", action="store_true", default=None, help="draw the copies as one path")


def stepped(op):
    """Whether ``op`` asks for per-step transforms, jitter or a merged result."""
    return any(key in op for key in STEP_KEYS)


def step_values(op, index, rng):
    """(rotation added, scale factor, opacity added, (dx, dy)) for copy ``index``."""
    rotation = finite(op.get("rotation_step", 0), "rotation_step", -3600, 3600) * index
    scale = finite(op.get("scale_step", 1), "scale_step", 0.01, 100) ** index
    opacity = finite(op.get("opacity_step", 0), "opacity_step", -1, 1) * index
    draw = rng.uniform(-1, 1, 5)
    rotation += finite(op.get("rotation_jitter", 0), "rotation_jitter", 0, 180) * draw[0]
    scale *= 1 + finite(op.get("scale_jitter", 0), "scale_jitter", 0, 0.95) * draw[1]
    opacity += finite(op.get("opacity_jitter", 0), "opacity_jitter", 0, 1) * draw[2]
    jitter = finite(op.get("position_jitter", 0), "position_jitter", 0, 100000)
    angle, radius = (draw[3] + 1) * math.pi, jitter * math.sqrt(abs(draw[4]))
    return float(rotation), float(scale), float(opacity), (radius * math.cos(angle), radius * math.sin(angle))


def adjust(project, layer, rotation, scale, opacity, move):
    """Turn, scale (about its centre), fade and move a document layer in place."""
    from .render import resolve_layout, transformed_size

    x, y, w, h = resolve_layout(project)[layer["id"]]
    cx, cy = x + w / 2 + move[0], y + h / 2 + move[1]
    layer.pop("pivot", None)
    layer["constraints"] = {}
    if scale != 1:
        layer["width"], layer["height"] = max(layer["width"] * scale, 0.01), max(layer["height"] * scale, 0.01)
        if layer["type"] == "shape" and layer.get("stroke_width"):
            layer["stroke_width"] = round(layer["stroke_width"] * scale, 3)
        if layer["type"] == "text" and "size" in layer:
            layer["size"] = max(1, round(layer["size"] * scale))
    layer["rotation"] = (layer.get("rotation", 0) + rotation) % 360
    layer["opacity"] = round(min(max(layer.get("opacity", 1) + opacity, 0.0), 1.0), 4)
    tw, th = transformed_size(layer)
    layer["x"], layer["y"] = cx - tw / 2, cy - th / 2


def merge_in_place(project, layers, name, explicit=True):
    """Replace document shape layers (siblings) by one merged path per style, at the first one's slot."""
    from .render import resolve_layout

    parents = {x.get("parent") for x in layers}
    require(len(parents) == 1, "merge needs layers in the same group", field="merge")
    bounds = resolve_layout(project)
    entries = [(deepcopy(x), bounds[x["id"]]) for x in layers]
    paths = merged(project, entries, name)
    order = project.state["layers"]
    at = min(order.index(x) for x in layers)
    gone = {x["id"] for x in layers}
    order[:] = [x for x in order if x["id"] not in gone]
    namer = Namer(project)
    parent = parents.pop()
    for i, layer in enumerate(paths):
        layer["name"] = namer(name, explicit) if len(paths) == 1 else namer(f"{name}/part-{i + 1}")
        if parent:
            layer["parent"] = parent
    order[at:at] = paths
    budget(project, 0)
    if len(paths) > 1:
        from .operations import execute as apply

        apply(project, {"type": "group", "name": namer(name, explicit), "targets": [x["id"] for x in paths]})
    project.state["active_layer"] = project.layer(name)["id"]
    return paths


def bake_repeat(project, op):
    """``repeat`` with per-step transforms, jitter or merge: real copies (grouped) or one path."""
    from .operations import execute as apply
    from .render import resolve_layout

    layer = project.layer(op.get("target"))
    count = op["count"]
    require(isinstance(count, int) and 1 <= count <= MAX_ITEMS, f"count must be 1-{MAX_ITEMS}", field="count")
    require("end" not in op, "repeat-blend does not take per-step fields", field="end")
    require(layer["type"] != "field", "Form fields cannot be repeated", field="target")
    layer.pop("repeat", None)  # real copies replace a live repeat
    if op.get("merge"):
        require(layer["type"] == "shape", f"merge needs a shape layer; {layer['name']!r} is a {layer['type']} layer",
                field="merge")
    else:
        budget(project, (count - 1) * (1 + _child_count(project, layer)) + 1)
    seed = op.get("seed", 0)
    require(isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0, "seed must be a whole number",
            field="seed")
    rng = stream(seed, 4)
    dx, dy = finite(op.get("dx", 0), "dx", -16384, 16384), finite(op.get("dy", 0), "dy", -16384, 16384)
    dw, dh = finite(op.get("dw", 0), "dw", -16384, 16384), finite(op.get("dh", 0), "dh", -16384, 16384)
    x, y, w, h = resolve_layout(project)[layer["id"]]
    cx, cy = x + w / 2, y + h / 2
    base = layer["name"]
    members = [layer]
    for i in range(1, count):
        apply(project, {"type": "duplicate", "target": layer["id"], "name": Namer(project)(f"{base}-{i + 1}")})
        copy = project.layer()
        require(copy["width"] + i * dw > 0 and copy["height"] + i * dh > 0, "dw/dh shrink a copy to nothing",
                field="dw")
        copy["width"] += i * dw
        copy["height"] += i * dh
        members.append(copy)
    for i, item in enumerate(members):
        rotation, scale, opacity, move = step_values(op, i, rng)
        x, y, w, h = resolve_layout(project)[item["id"]]
        shift = (cx + i * dx - (x + w / 2) + move[0], cy + i * dy - (y + h / 2) + move[1])
        adjust(project, item, rotation, scale, opacity, shift)
    label = op.get("name") or f"{base}-repeat"
    if op.get("merge"):
        merge_in_place(project, members, label, "name" in op)
        return
    apply(project, {"type": "group", "name": label, "targets": [x["id"] for x in members]})


def mark_catalog():
    return {name: {"path": path, "view": [100, 100]} for name, path in MARKS.items()}



def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    if cmd == "scatter":
        p = Parser(prog="vixl scatter", description="Scatter motif copies inside or along a layer's outline")
        p.add_argument("target")
        p.add_argument("--placement", choices=PLACEMENTS)
        p.add_argument("--direction", choices=DIRECTIONS)
        p.add_argument("--anchor", choices=ANCHORS)
        p.add_argument("--preset", choices=PRESETS)
        p.add_argument("--exclude", action="append", help="layer to keep clear (repeatable)")
        for key in ("spread", "offset", "exclude-margin", "position-jitter", "length", "flicks"):
            p.add_argument("--" + key, type=float)
    else:
        p = Parser(prog="vixl pattern-scatter", description="Scatter motifs in a seamless wrap-around tile")
        p.add_argument("--target", help="rebuild this pattern-scatter tile")
        for key in ("width", "height", "x", "y"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--background")
        p.add_argument("--pattern", help="also save the tile as a pattern of this name")
    p.add_argument("--source", action="append", help="motif layer (repeatable)")
    p.add_argument("--mark", type=json.loads, help="JSON shape spec for a motif drawn on the fly")
    p.add_argument("--count", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--tones", type=int)
    for key in ("spacing", "scale", "scale-jitter", "rotation", "rotation-jitter", "tone-variation"):
        p.add_argument("--" + key, type=float)
    p.add_argument("--color", dest="colors", action="append", help="fill color picked per copy (repeatable)")
    p.add_argument("--merge", action="store_true", default=None, help="one path layer per tone")
    p.add_argument("--keep-source", dest="hide_source", action="store_false", default=None)
    p.add_argument("--name")
    op = {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
    if isinstance(op.get("source"), list) and len(op["source"]) == 1:
        op["source"] = op["source"][0]
    return op
