"""Irregularity and randomness: opt-in, seeded imperfection for vector layers, and torn edges.

Vector output is exact: every curve is true, every repeat identical. That is right for logos and
diagrams and wrong for an original character, a hand-inked outline or a ripped sheet of paper.
This module adds the small flaws that make such things look made rather than computed.

``irregular`` perturbs existing vector layers (shapes, paths, strokes, or groups of them):

* **Outline wobble**: each outline is displaced along its normals by smooth noise whose
  correlation length you choose (long waves read as a wavering line, short ones as roughness),
  and ``jitter`` moves the path's own vertices.
* **Stroke weight**: a per-layer weight change, and ``pressure``, which turns the stroke into a
  filled ribbon whose width varies along the line like ink.
* **Color drift**: a small lightness, chroma and hue shift, measured in OKLab.
* **Placement**: a micro rotation, scale and position change for every layer of a set, so a
  hundred copies of one leaf stop being identical.

``tear`` makes a torn, ripped edge: a fractal rough edge on any sides of a layer's box, with an
optional paper-white rim and fibres, applied as a mask on the layer or drawn as path layers.

Everything is deterministic: the same ``seed``, strength and source geometry always give the same
result, and different seeds give different ones. Every effect is bounded by the numbers you give
or the preset's, so no layer can wander off. The first application keeps the pristine source in
the layer's ``irregular`` record; applying again with a new ``seed`` regrows from that source
rather than stacking imperfections, and ``remove`` restores it.

Presets (``subtle``, ``natural``, ``rough``) set magnitudes relative to each layer's size, so the
same strength suits a button and a poster. This is a tool for chosen places, not a global
finish: see docs/irregular.md for when not to use it.
"""

from copy import deepcopy
import math

import numpy as np

from .errors import VixlError, require

TYPES = ("irregular", "tear")
EFFECTS = ("wobble", "jitter", "width", "pressure", "color", "placement")
EDGES = ("top", "right", "bottom", "left")
MAX_LAYERS = 256
MAX_POINTS = 3500          # per outline after perturbing; a ribbon has two sides, and a path takes 8192 commands
MAX_FIBRES = 1500
# What a layer is restored from: every field the engine may change.
SOURCE_KEYS = ("shape", "path", "path_view", "width", "height", "x", "y", "rotation", "fill", "stroke",
               "stroke_width", "line_cap")

# Magnitudes per strength. Lengths (wobble, jitter, position) are fractions of the layer's size.
STRENGTHS = {
    "subtle": {"wobble": 0.004, "length": 0.20, "jitter": 0.0015, "roughness": 0.15, "width": 0.05, "pressure": 0.08,
               "lightness": 0.008, "chroma": 0.04, "hue": 1.0, "rotation": 0.4, "scale": 0.008, "position": 0.004},
    "natural": {"wobble": 0.010, "length": 0.16, "jitter": 0.004, "roughness": 0.35, "width": 0.12, "pressure": 0.18,
                "lightness": 0.020, "chroma": 0.08, "hue": 2.5, "rotation": 1.2, "scale": 0.02, "position": 0.010},
    "rough": {"wobble": 0.028, "length": 0.10, "jitter": 0.012, "roughness": 0.65, "width": 0.25, "pressure": 0.35,
              "lightness": 0.045, "chroma": 0.16, "hue": 6.0, "rotation": 3.0, "scale": 0.05, "position": 0.025},
}
TEAR_STRENGTHS = {
    "subtle": {"depth": 0.015, "length": 0.22, "roughness": 0.35, "rim": 0.005, "fibres": 0.15},
    "natural": {"depth": 0.035, "length": 0.16, "roughness": 0.55, "rim": 0.012, "fibres": 0.35},
    "rough": {"depth": 0.075, "length": 0.10, "roughness": 0.75, "rim": 0.020, "fibres": 0.60},
}
# recipe field -> (effect it belongs to, preset key, relative to the layer's size?)
FIELDS = {
    "wobble": ("wobble", "wobble", True),
    "jitter": ("jitter", "jitter", True),
    "width_variation": ("width", "width", False),
    "pressure": ("pressure", "pressure", False),
    "lightness_drift": ("color", "lightness", False),
    "chroma_drift": ("color", "chroma", False),
    "hue_drift": ("color", "hue", False),
    "rotation_jitter": ("placement", "rotation", False),
    "scale_jitter": ("placement", "scale", False),
    "position_jitter": ("placement", "position", True),
}
RECIPE_KEYS = ("seed", "strength", "amount", "only", "wobble_length", "roughness", *FIELDS)
TEAR_KEYS = ("seed", "strength", "as", "edges", "depth", "length", "roughness", "rim_width", "rim_color", "fibres",
             "fibre_width", "fill")


# ---------------------------------------------------------------------------------------------
# Noise and outlines


def stream(seed, *keys):
    """A random stream for a seed and any number of integer keys; the same arguments always give
    the same stream, and each key path gives an independent one."""
    return np.random.default_rng([seed, *keys])


def correlated_noise(rng, arc, length, total, closed, octaves=1, persistence=0.5):
    """Smooth noise in [-1, 1] at arc-length positions ``arc`` (pixels along an outline).

    Value noise on a lattice ``length`` pixels apart; each further octave halves the spacing and
    scales its weight by ``persistence``. A closed outline repeats after ``total``, so there is no
    seam. The result is clipped, which is what bounds every displacement made from it.
    """
    arc = np.asarray(arc, dtype=float)
    total = max(float(total), 1e-6)
    out = np.zeros(len(arc))
    weight, norm = 1.0, 0.0
    for octave in range(max(1, octaves)):
        cells = max(2 if closed else 1, int(round(total / max(length / 2 ** octave, 1e-3))))
        lattice = rng.uniform(-1, 1, cells if closed else cells + 1)
        t = arc / total * cells
        i = np.minimum(np.floor(t).astype(int), cells - 1)
        f = t - i
        f = f * f * f * (f * (f * 6 - 15) + 10)
        low, high = lattice[i % len(lattice)], lattice[(i + 1) % len(lattice)]
        out += weight * (low + (high - low) * f)
        norm += weight
        weight *= persistence
    # Value noise rarely reaches its extremes; stretch it so the allowed range gets used.
    return np.clip(out / norm * 1.6, -1, 1)


def _bezier(controls, t):
    work = [np.tile(p, (len(t), 1)) for p in controls]
    while len(work) > 1:
        work = [(1 - t) * a + t * b for a, b in zip(work, work[1:])]
    return work[0]


def flatten(path, scale=(1.0, 1.0), offset=(0.0, 0.0)):
    """Subpaths of SVG path data as ``[(points, nodes, closed)]``; curves are sampled, and
    ``nodes`` marks the points that were the path's own vertices."""
    from .geometry import parse_path

    sx, sy = scale
    subs, pts, nodes = [], [], []

    def finish(closed):
        nonlocal pts, nodes
        if len(pts) >= 2:
            p, n = np.array(pts), np.array(nodes)
            if closed and np.hypot(*(p[-1] - p[0])) < 1e-6:
                p, n = p[:-1], n[:-1]
            if len(p) >= 2:
                subs.append((p, n, closed))
        pts, nodes = [], []

    start = current = np.zeros(2)
    for command, values in parse_path(path):
        v = np.array(values, dtype=float).reshape(-1, 2) * (sx, sy) + offset
        if command == "M":
            finish(False)
            current = start = v[0]
            pts, nodes = [current], [True]
        elif command == "L":
            current = v[0]
            pts.append(current)
            nodes.append(True)
        elif command in ("C", "Q"):
            controls = [current, *v]
            length = sum(np.hypot(*(b - a)) for a, b in zip(controls, controls[1:]))
            steps = int(np.clip(math.ceil(length / 5), 6, 96))
            curve = _bezier(controls, np.linspace(0, 1, steps + 1)[1:, None])
            pts.extend(curve)
            nodes.extend([False] * (steps - 1) + [True])
            current = curve[-1]
        elif command == "Z":
            finish(True)
            current = start
            pts, nodes = [current], [True]
    finish(False)
    return subs


def _arc(points, closed):
    seq = np.vstack([points, points[:1]]) if closed else points
    seg = np.hypot(*np.diff(seq, axis=0).T)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    return arc, arc[-1]


def resample(points, closed, step):
    """Evenly spaced points along a polyline, keeping its sharp corners. Returns (points, arc, total)."""
    seq = np.vstack([points, points[:1]]) if closed else points
    arc, total = _arc(points, closed)
    if total < 1e-9:
        return points, np.zeros(len(points)), 1e-6
    count = max(int(math.ceil(total / step)), 3 if closed else 1)
    grid = np.arange(count) * total / count if closed else np.linspace(0, total, count + 1)
    d = np.diff(seq, axis=0)
    heading = np.arctan2(d[:, 1], d[:, 0])
    turn = np.abs(np.angle(np.exp(1j * (heading[1:] - heading[:-1]))))
    corners = arc[1:-1][turn > math.radians(28)]
    grid = np.unique(np.concatenate([grid, corners]))
    grid = grid[np.concatenate([[True], np.diff(grid) > 1e-3])]
    x, y = np.interp(grid, arc, seq[:, 0]), np.interp(grid, arc, seq[:, 1])
    return np.column_stack([x, y]), grid, total


def normals(points, closed):
    """Unit normals of a polyline (central differences)."""
    if closed:
        t = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    else:
        t = np.gradient(points, axis=0)
    length = np.hypot(t[:, 0], t[:, 1])
    length[length < 1e-9] = 1.0
    return np.column_stack([t[:, 1], -t[:, 0]]) / length[:, None]


def jitter_nodes(points, nodes, closed, rng, amount):
    """Move the path's own vertices by up to ``amount``; the points between follow their neighbours."""
    idx = np.flatnonzero(nodes)
    if amount <= 0 or len(idx) < 1:
        return points
    angle = rng.uniform(0, 2 * math.pi, len(idx))
    radius = amount * np.sqrt(rng.uniform(0, 1, len(idx)))
    move = np.column_stack([radius * np.cos(angle), radius * np.sin(angle)])
    arc, total = _arc(points, closed)
    knots = arc[idx]
    if closed:
        knots = np.append(knots, total)
        move = np.vstack([move, move[:1]])
    at = arc[:len(points)]
    return points + np.column_stack([np.interp(at, knots, move[:, 0]), np.interp(at, knots, move[:, 1])])


def roughen(subs, seed, *, wobble=0.0, length=24.0, jitter=0.0, roughness=0.3, salt=1, densify=False):
    """Perturb flattened subpaths. Each subpath draws from its own stream of the seed.

    Vertices move by at most ``jitter``, then the outline is displaced along its normals by at
    most ``wobble`` (noise with correlation length ``length``, more octaves for more
    ``roughness``), so a point never moves more than ``jitter + wobble``. ``densify`` resamples
    the outline even with no wobble. Returns ``[(points, closed)]``.
    """
    octaves = 1 + int(round(roughness * 3))
    total = sum(_arc(p, c)[1] for p, _, c in subs)
    step = max(1.0, min(length / 5, length / 2 ** (octaves - 1) / 3), total / MAX_POINTS)
    out = []
    crowded = sum(len(p) for p, _, _ in subs) > MAX_POINTS
    for i, (points, nodes, closed) in enumerate(subs):
        rng = stream(seed, salt, i)
        pts = jitter_nodes(points, nodes, closed, rng, jitter)
        if wobble > 0 or densify or crowded:
            fine, arc, span = resample(pts, closed, step)
            if wobble > 0 and len(fine) >= 3:
                noise = correlated_noise(rng, arc, length, span, closed, octaves, 0.35 + 0.3 * roughness)
                fine = fine + normals(fine, closed) * (wobble * noise)[:, None]
            pts = fine
        out.append((pts, closed))
    return out


def roughen_path(path, seed, *, wobble=2.0, length=24.0, jitter=0.0, roughness=0.3):
    """Wobble SVG path data: a pure helper for code that wants one imperfect path.

    Coordinates keep the units they came in; ``wobble``, ``length`` and ``jitter`` use them too.
    """
    require(isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0, "seed must be a whole number",
            field="seed")
    subs = flatten(path)
    require(subs, "The path has no geometry")
    return emit(roughen(subs, seed, wobble=wobble, length=length, jitter=jitter, roughness=roughness))


def _fmt(value):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def emit(subs):
    """SVG path data for ``[(points, closed)]`` as polylines."""
    parts = []
    for points, closed in subs:
        if len(points) >= 2:
            parts.append("M" + " L".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points) + (" Z" if closed else ""))
    return " ".join(parts)


def ribbon(points, closed, widths):
    """The filled outline of a stroke whose width is ``widths`` at each point.

    An open line gives one polygon; a closed outline gives two loops running opposite ways, so
    the interior stays open under nonzero fill.
    """
    side = normals(points, closed) * (np.asarray(widths)[:, None] / 2)
    left, right = points + side, points - side
    if closed:
        return [(left, True), (right[::-1], True)]
    return [(np.vstack([left, right[::-1]]), True)]


# ---------------------------------------------------------------------------------------------
# Layers as outlines


def visible(value, project):
    from .colors import parse
    from .design import resolve_color

    return value is not None and parse(resolve_color(value, project.state))[3] > 0


def layer_outline(layer, project):
    """A shape layer's outline as flattened subpaths in the layer's own pixel space.

    Primitive shapes are drawn the way the renderer draws them, including the inset that keeps a
    stroke inside the box.
    """
    from .geometry import shape_path
    from .wedge import wedge_path

    w, h = layer["width"], layer["height"]
    shape = layer.get("shape", "rectangle")
    width = layer.get("stroke_width", 1)
    pad = width / 2 if visible(layer.get("stroke", "transparent"), project) and width > 0 else 0
    pad = min(pad, (min(w, h) - 1) / 4) if min(w, h) > 1 else 0
    if shape in ("rectangle", "rounded-rectangle", "capsule", "ellipse"):
        i = 2 * pad
        x0, y0, x1, y1 = i, i, w - i, h - i
        if shape == "rectangle":
            return flatten(f"M{x0} {y0} L{x1} {y0} L{x1} {y1} L{x0} {y1} Z")
        if shape == "ellipse":
            aspect = (y1 - y0) / (x1 - x0)
            return flatten(wedge_path((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, 0, 360, aspect=aspect))
        r = min(layer.get("radius", min(w, h) / (2 if shape == "capsule" else 5)), (x1 - x0) / 2, (y1 - y0) / 2)
        k = r * 0.5523
        return flatten(
            f"M{x0 + r} {y0} L{x1 - r} {y0} C{x1 - r + k} {y0} {x1} {y0 + r - k} {x1} {y0 + r} L{x1} {y1 - r} "
            f"C{x1} {y1 - r + k} {x1 - r + k} {y1} {x1 - r} {y1} L{x0 + r} {y1} C{x0 + r - k} {y1} {x0} {y1 - r + k} "
            f"{x0} {y1 - r} L{x0} {y0 + r} C{x0} {y0 + r - k} {x0 + r - k} {y0} {x0 + r} {y0} Z")
    if shape == "line":
        return flatten(f"M0 0 L{w} {h}")
    path, view = shape_path(layer)
    if shape in ("path", "arc"):
        return flatten(path, (w / view[0], h / view[1]))
    return flatten(path, ((w - 2 * pad) / view[0], (h - 2 * pad) / view[1]), (pad, pad))


def fit_box(layer, outlines, pad):
    """Grow the layer's box evenly on every side so nothing drawn is cut off, and refit the path
    view to it. Returns the offset every point must be moved by."""
    w, h = layer["width"], layer["height"]
    every = [p for outline in outlines for p, _ in outline]
    low = np.min([p.min(axis=0) for p in every], axis=0)
    high = np.max([p.max(axis=0) for p in every], axis=0)
    over = max(-low[0], -low[1], high[0] - w, high[1] - h, 0.0)
    grow = int(math.ceil(over + pad)) if over > 0 else 0
    if grow:
        layer.update(width=w + 2 * grow, height=h + 2 * grow, x=layer["x"] - grow, y=layer["y"] - grow)
    layer["path_view"] = [layer["width"], layer["height"]]
    return grow


def drifted(value, project, u, lightness, chroma, hue):
    """A color nudged by up to ``lightness`` (OKLab L), ``chroma`` (relative) and ``hue`` (degrees);
    ``u`` is three numbers in [-1, 1] choosing where in each range."""
    from .colors import from_polar, gamut_map, hex_of, parse, srgb_to_oklab, to_polar
    from .design import resolve_color

    rgba = parse(resolve_color(value, project.state))
    if rgba[3] == 0:
        return value
    light, c, h = to_polar(srgb_to_oklab(rgba[:3]))
    light = min(max(light + lightness * u[0], 0.0), 1.0)
    c = max(c * (1 + chroma * u[1]), 0.0)
    rgb = gamut_map(from_polar((light, c, h + hue * u[2])))
    return hex_of((*rgb, rgba[3]))


# ---------------------------------------------------------------------------------------------
# irregular


def size_of(w, h):
    """The size a layer's imperfections are proportioned to: the side of its area, but at least a
    third of its long side, so a thin line still gets visible waves."""
    return max(math.sqrt(w * h), 0.35 * max(w, h), 1.0)


def resolve(recipe, w, h):
    """The numbers one layer is perturbed with: preset values scaled to its size and to the
    recipe's ``amount``, then any explicit fields the recipe sets."""
    preset = STRENGTHS[recipe.get("strength", "natural")]
    amount = recipe.get("amount", 1.0)
    on = set(EFFECTS if recipe.get("only") is None else recipe["only"])
    size = size_of(w, h)
    values = {}
    for key, (effect, name, relative) in FIELDS.items():
        if key in recipe:
            values[key] = recipe[key]
        elif effect in on:
            values[key] = preset[name] * amount * (size if relative else 1)
        else:
            values[key] = 0.0
    values["wobble_length"] = min(max(recipe.get("wobble_length", preset["length"] * size), 2.0), 4000.0)
    values["roughness"] = recipe.get("roughness", preset["roughness"])
    return values


def vector_layers(project, op):
    """The shape layers an operation names, groups expanded, in document order."""
    from .design import descendants

    refs = list(op["targets"]) if op.get("targets") else [op.get("target")]
    found, seen = [], set()
    for ref in refs:
        layer = project.layer(ref)
        if layer.get("part_of"):
            raise VixlError("invalid_operation", f"{layer['name']!r} is a helper layer (stroke ribbon, rim or "
                            "fibres) of another layer; target that layer instead", field="target")
        if layer["type"] == "group":
            inside = descendants(project, layer["id"])
            members = [x for x in project.state["layers"] if x["id"] in inside and x["type"] == "shape"
                       and not x.get("part_of")]
            require(members, f"{layer['name']!r} holds no vector layers (shapes, paths or strokes); text and raster "
                    "layers cannot be made irregular", field="target")
        else:
            require(layer["type"] == "shape", f"{layer['name']!r} is a {layer['type']} layer; irregular works on "
                    "vector layers (shapes, paths, strokes) and groups of them", field="target")
            members = [layer]
        for member in members:
            if member["id"] not in seen:
                seen.add(member["id"])
                found.append(member)
    order = {x["id"]: i for i, x in enumerate(project.state["layers"])}
    found.sort(key=lambda x: order[x["id"]])
    require(len(found) <= MAX_LAYERS, f"At most {MAX_LAYERS} layers per operation", "resource_limit", field="target")
    return found


def drop_parts(project, owner, ids):
    """Remove the helper layers (stroke ribbon, rim, fibres, face) an owner made, but never ones
    that belong to another layer, such as a duplicate's shared record would otherwise name."""
    ids = {i for i in ids if i}
    project.state["layers"][:] = [x for x in project.state["layers"]
                                  if not (x["id"] in ids and x.get("part_of") == owner["id"])]


def restore(project, layer):
    """Put a layer back to the source its record kept, dropping the stroke ribbon made for it."""
    record = layer.get("irregular")
    if not record or "source" not in record:
        return
    for key in SOURCE_KEYS:
        if key in record["source"]:
            layer[key] = deepcopy(record["source"][key])
        else:
            layer.pop(key, None)
    drop_parts(project, layer, [record.get("ink")])
    layer.pop("irregular", None)


def make_irregular(project, layer, recipe, index):
    """Apply a recipe to one shape layer that is in its pristine state; returns the record."""
    from .operations import default_name
    from .model import new_layer

    w, h = layer["width"], layer["height"]
    source = {key: deepcopy(layer[key]) for key in SOURCE_KEYS if key in layer}
    values = resolve(recipe, w, h)
    seed = recipe["seed"]
    line = layer.get("shape") == "line"
    stroke_seen = visible(layer.get("stroke", "transparent"), project)
    fill_on = visible(layer.get("fill", "white"), project) and not line
    sw = layer.get("stroke_width", 1)
    stroke_on = (stroke_seen or line) and sw > 0
    ink_color = layer.get("stroke") if stroke_seen else layer.get("fill", "white")
    width_u = stream(seed, index, 2).uniform(-1, 1)
    color_u = stream(seed, index, 3).uniform(-1, 1, 3)
    rotation_u, scale_u, x_u, y_u = stream(seed, index, 4).uniform(-1, 1, 4)
    if stroke_on:
        sw = max(sw * (1 + values["width_variation"] * width_u), 0.1)
    scale = 1 + values["scale_jitter"] * scale_u
    pressure = values["pressure"] > 0 and stroke_on
    ribbons = None
    if values["wobble"] > 0 or values["jitter"] > 0 or pressure or scale != 1:
        subs = layer_outline(layer, project)
        require(subs, f"{layer['name']!r} has no geometry to change", field="target")
        outline = roughen(subs, seed, wobble=values["wobble"], length=values["wobble_length"],
                          jitter=values["jitter"], roughness=values["roughness"], salt=1000 + index, densify=pressure)
        if scale != 1:
            centre = np.array([w / 2, h / 2])
            outline = [((p - centre) * scale + centre, c) for p, c in outline]
        if pressure:
            ribbons = []
            for i, (points, closed) in enumerate(outline):
                arc, total = _arc(points, closed)
                noise = correlated_noise(stream(seed, index, 5, i), arc[:len(points)],
                                         max(values["wobble_length"] * 2.5, 12.0), total, closed, 2, 0.4)
                widths = np.maximum(sw * (1 + min(values["pressure"], 0.9) * noise), 0.15 * sw)
                ribbons += ribbon(points, closed, widths)
        pad = 0 if ribbons else (sw / 2 if stroke_on else 0)
        grow = fit_box(layer, [outline] + ([ribbons] if ribbons else []), pad)
        shift = np.array([grow, grow], dtype=float)
        outline = [(p + shift, c) for p, c in outline]
        ribbons = [(p + shift, c) for p, c in ribbons] if ribbons else None
        commands = max(sum(len(p) + 1 for p, _ in part) for part in (outline, ribbons or []))
        require(commands <= 8000, "The result is too detailed for one path; use a larger wobble_length or a smaller "
                "layer", "resource_limit", field="wobble_length")
        layer.update(shape="path", path=emit(outline))
    ink = None
    if stroke_on:
        layer["stroke_width"] = round(sw, 3)
    if ribbons:
        if fill_on:
            ink = new_layer(default_name(project, f"{layer['name']}-ink"), "shape", layer["width"], layer["height"],
                            shape="path", path=emit(ribbons), path_view=[layer["width"], layer["height"]],
                            fill=ink_color, stroke="transparent", stroke_width=0)
            layer["stroke"] = "transparent"
        else:
            layer.update(path=emit(ribbons), fill=ink_color, stroke="transparent", stroke_width=0)
    drift = (values["lightness_drift"], values["chroma_drift"], values["hue_drift"])
    if any(drift):
        for field in ("fill", "stroke"):
            if field in layer and layer[field] != "transparent":
                layer[field] = drifted(layer[field], project, color_u, *drift)
        if ink is not None:
            ink["fill"] = drifted(ink["fill"], project, color_u, *drift)
    if values["rotation_jitter"]:
        layer["rotation"] = (layer.get("rotation", 0) + values["rotation_jitter"] * rotation_u) % 360
    # A layer whose position is set by constraints keeps that axis; the constraint would undo the move.
    held = layer.get("constraints", {})
    for axis, u, anchors in (("x", x_u, ("left", "right", "center-x")), ("y", y_u, ("top", "bottom", "center-y"))):
        if values["position_jitter"] and not any(a in held for a in anchors):
            layer[axis] = layer[axis] + values["position_jitter"] * u
    if ink is not None:
        for key in ("x", "y", "rotation", "flip_x", "flip_y", "opacity", "blend", "parent", "pivot"):
            if key in layer:
                ink[key] = deepcopy(layer[key])
        order = project.state["layers"]
        order.insert(order.index(layer) + 1, ink)
        require(len(order) <= project.limits.max_layers, "Layer limit reached: the stroke ribbon of each filled "
                "shape is a layer of its own; set pressure to 0 for a big set", "resource_limit", field="pressure")
        ink["part_of"] = layer["id"]
    project.limits.size(layer["width"], layer["height"])
    return {"recipe": recipe, "source": source, **({"ink": ink["id"]} if ink is not None else {})}


def execute_irregular(project, op):
    layers = vector_layers(project, op)
    if op.get("remove"):
        made = [layer for layer in layers if "irregular" in layer]
        require(made, f"{layers[0]['name']!r} has no irregularity to remove" if len(layers) == 1 else
                "None of these layers has irregularity to remove", field="target")
        for layer in made:
            restore(project, layer)
        return
    require("seed" in op, "irregular needs a seed: the same seed always gives the same result", field="seed")
    for index, layer in enumerate(layers):
        recipe = {**(layer.get("irregular") or {}).get("recipe", {}),
                  **{k: deepcopy(op[k]) for k in RECIPE_KEYS if k in op}}
        restore(project, layer)
        layer["irregular"] = make_irregular(project, layer, recipe, index)


# ---------------------------------------------------------------------------------------------
# tear


MODES = ("mask", "clip", "path")


def edge_frame(edge, w, h):
    """Start, direction along, direction inward and length of a box edge (clockwise from top-left)."""
    return {"top": ((0, 0), (1, 0), (0, 1), w), "right": ((w, 0), (0, 1), (-1, 0), h),
            "bottom": ((w, h), (-1, 0), (0, -1), w), "left": ((0, h), (0, -1), (1, 0), h)}[edge]


def torn_edge(span, depth, rng, *, length, roughness=0.55, min_step=1.0):
    """A fractal torn edge: ``(stations, offsets)`` along ``span`` pixels, offsets between 0 and
    ``depth`` (how far the edge has been torn away). ``length`` is the size of its widest bays;
    ``roughness`` (0–1) adds finer octaves with more weight; ``min_step`` coarsens the sampling."""
    octaves = 2 + int(round(roughness * 4))
    step = max(1.0, min_step, min(length / 2 ** (octaves - 1) / 3, 4.0))
    stations = np.linspace(0, span, max(int(math.ceil(span / step)), 2) + 1)
    noise = correlated_noise(rng, stations, length, span, False, octaves, 0.45 + 0.25 * roughness)
    return stations, depth * (0.5 + 0.5 * noise)


def keep_inside(points, curves, w, h):
    """Pull points back inside every torn edge, so two torn edges that meet at a corner cut each
    other cleanly instead of leaving a spike. ``curves`` maps an edge name to its (stations, offsets)."""
    pts = np.array(points, dtype=float).reshape(-1, 2)
    x, y = pts[:, 0], pts[:, 1]
    if "top" in curves:
        y = np.maximum(y, np.interp(x, *curves["top"]))
    if "bottom" in curves:
        y = np.minimum(y, h - np.interp(w - x, *curves["bottom"]))
    if "left" in curves:
        x = np.maximum(x, np.interp(h - y, *curves["left"]))
    if "right" in curves:
        x = np.minimum(x, w - np.interp(y, *curves["right"]))
    return np.column_stack([x, y])


def torn_shapes(w, h, seed, edges, *, depth, length, roughness=0.55, rim=0.0, fibres=0.0):
    """The geometry of a torn sheet filling a ``w`` × ``h`` box.

    Returns ``face`` and ``rim`` (polygons as point arrays) and ``fibres`` (a list of
    ``(start, control, end)``). The face never leaves the box and is never torn deeper than
    ``depth``; the rim is the band of exposed paper between the box edge and the face, up to
    ``rim`` wide; fibres reach outward from the face edge but stay inside the box.
    """
    depth = min(depth, 0.45 * min(w, h))
    face, band, hairs, torn, bared = [], [], [], {}, {}
    frames = {}
    for number, edge in enumerate(EDGES):
        origin, tangent, inward, span = (np.array(v, dtype=float) if isinstance(v, tuple) else v
                                         for v in edge_frame(edge, w, h))
        frames[edge] = (origin, tangent, inward, span)
        if edge not in edges:
            face.append(origin)
            band.append(origin)
            continue
        stations, offsets = torn_edge(span, depth, stream(seed, number, 1), length=length, roughness=roughness,
                                      min_step=2 * (w + h) / (MAX_POINTS * 2))
        thick = rim * (0.35 + 0.65 * (0.5 + 0.5 * correlated_noise(stream(seed, number, 2), stations,
                                                                     max(length / 3, 3.0), span, False, 3, 0.6)))
        inner = np.maximum(offsets - thick, 0.0)
        torn[edge], bared[edge] = (stations, offsets), (stations, inner)
        face.extend(origin + tangent * s + inward * d for s, d in zip(stations, offsets))
        band.extend(origin + tangent * s + inward * d for s, d in zip(stations, inner))
    for number, edge in enumerate(EDGES):
        count = min(int(fibres * frames[edge][3] / 4), MAX_FIBRES) if rim > 0 and edge in torn else 0
        if not count:
            continue
        origin, tangent, inward, span = frames[edge]
        stations, offsets = torn[edge]
        rng = stream(seed, number, 3)
        at, bend, size = rng.uniform(0, span, count), rng.uniform(-0.7, 0.7, count), rng.uniform(0.35, 1.2, count)
        sway = rng.uniform(-0.25, 0.25, count)
        for s, a, f, q in zip(at, bend, size, sway):
            d = float(np.interp(s, stations, offsets))
            direction = -inward * math.cos(a) + tangent * math.sin(a)
            reach = min(f * rim * 1.6, d / max(math.cos(a), 0.2))
            if reach < 0.5:
                continue
            start = keep_inside(origin + tangent * s + inward * d, torn, w, h)[0]
            end = np.clip(start + direction * reach, 0, [w, h])
            control = (start + end) / 2 + np.array([-direction[1], direction[0]]) * reach * q
            hairs.append((start, control, end))
    return {"face": keep_inside(face, torn, w, h), "rim": keep_inside(band, bared, w, h), "fibres": hairs}


def polygon_path(points):
    return emit([(np.array(points), True)])


def fibre_path(hairs):
    return " ".join(f"M{_fmt(a[0])} {_fmt(a[1])} Q{_fmt(c[0])} {_fmt(c[1])} {_fmt(b[0])} {_fmt(b[1])}"
                    for a, c, b in hairs)


def mask_image(points, layer, size):
    """An 8-bit mask of a polygon in a layer's own upright box, turned and flipped the way the
    layer is drawn, on a frame of ``size`` (the layer's bounds) so it lines up with the pixels."""
    from PIL import Image, ImageDraw, ImageOps

    w, h = layer["width"], layer["height"]
    factor = max(1, min(4, int(math.sqrt(16_000_000 / max(w * h, 1)))))
    big = Image.new("L", (w * factor, h * factor), 0)
    ImageDraw.Draw(big).polygon([(x * factor, y * factor) for x, y in points], fill=255)
    mask = big.resize((w, h), Image.Resampling.BOX) if factor > 1 else big
    if layer.get("flip_x"):
        mask = ImageOps.mirror(mask)
    if layer.get("flip_y"):
        mask = ImageOps.flip(mask)
    if layer.get("rotation", 0) % 360:
        mask = mask.rotate(-layer["rotation"], Image.Resampling.BICUBIC, expand=True)
    if mask.size != tuple(size):
        frame = Image.new("L", tuple(size), 0)
        frame.paste(mask, ((size[0] - mask.width) // 2, (size[1] - mask.height) // 2))
        mask = frame
    return mask


def tear_numbers(recipe, w, h):
    preset = TEAR_STRENGTHS[recipe.get("strength", "natural")]
    short = min(w, h)
    edges = recipe.get("edges", ["bottom"])
    edges = EDGES if "all" in edges else tuple(e for e in EDGES if e in edges)
    return {
        "edges": edges,
        "depth": recipe.get("depth", preset["depth"] * short),
        "length": min(max(recipe.get("length", preset["length"] * max(w, h)), 2.0), 4000.0),
        "roughness": recipe.get("roughness", preset["roughness"]),
        "rim": recipe.get("rim_width", preset["rim"] * short),
        "fibres": recipe.get("fibres", preset["fibres"]),
    }


def clear_tear(project, holder, keep_face=False):
    """Undo a tear on its holder layer: the added rim and fibres go, a mask returns to what it was,
    and a clip tear releases the clip and drops its face (unless the face is being kept)."""
    record = holder.get("tear")
    if not record:
        return
    gone = [record.get("rim"), record.get("fibres")]
    if record["mode"] == "mask":
        holder["mask"] = deepcopy(record.get("base_mask"))
    elif record["mode"] == "clip" and not keep_face:
        gone.append(record["face"])
        if holder.get("clip") == record["face"]:
            holder.pop("clip")
    drop_parts(project, holder, gone)
    holder.pop("tear", None)


def execute_tear(project, op):
    from .assets import add_image
    from .model import new_layer
    from .operations import append_layer, default_name
    from .render import resolve_layout

    layer = project.layer(op["target"]) if op.get("target") else None
    previous = (layer or {}).get("tear")
    order = project.state["layers"]
    if op.get("remove"):
        require(previous, "That layer has no torn edge to remove", field="target")
        clear_tear(project, layer)
        if previous["mode"] == "path":
            order[:] = [x for x in order if x["id"] != layer["id"]]
            if project.state["active_layer"] == layer["id"]:
                project.state["active_layer"] = order[-1]["id"] if order else None
        return
    require("seed" in op, "tear needs a seed: the same seed always gives the same edge", field="seed")
    recipe = {**(previous or {}).get("recipe", {}), **{k: deepcopy(op[k]) for k in TEAR_KEYS if k in op}}
    mode = previous["mode"] if previous else recipe.get("as") or ("mask" if layer else "path")
    require(not previous or op.get("as", mode) == mode, f"This tear is a {mode}; remove it before switching",
            field="as")
    require(mode == "path" or layer is not None, f"as: {mode} needs a target layer to cut; for a free-standing "
            "torn sheet give as: path with width and height", field="target")
    require(mode != "clip" or previous or not layer.get("clip"), f"{layer and layer['name']!r} is already clipped; "
            "release its clip first", field="target")
    recipe["as"] = mode
    carried = dict(previous or {})
    if previous:
        clear_tear(project, layer, keep_face=True)
    base_mask = carried["base_mask"] if previous and mode == "mask" else (layer or {}).get("mask")
    if layer is not None:
        w, h = layer["width"], layer["height"]
    else:
        w, h = op.get("width"), op.get("height")
        require(w and h, "A standalone tear needs width and height (or a target layer to tear)", field="width")
    project.limits.size(w, h)
    numbers = tear_numbers(recipe, w, h)
    shapes = torn_shapes(w, h, recipe["seed"], numbers["edges"], depth=numbers["depth"], length=numbers["length"],
                         roughness=numbers["roughness"], rim=numbers["rim"], fibres=numbers["fibres"])
    name = op.get("name") or carried.get("name") or (layer["name"] if layer else "torn")
    rim_color = recipe.get("rim_color", "#fffdf7")
    if layer is not None:
        place = {k: deepcopy(layer[k]) for k in ("x", "y", "rotation", "flip_x", "flip_y", "pivot", "parent",
                                                 "constraints") if k in layer}
    else:
        place = {"x": op.get("x", 0), "y": op.get("y", 0)}

    def path_layer(label, d, **style):
        item = new_layer(label, "shape", w, h, shape="path", path=d, path_view=[w, h], **style)
        item.update(deepcopy(place))
        return item

    rim = fibres = face = None
    if numbers["rim"] > 0 and numbers["depth"] > 0:
        rim = path_layer(default_name(project, f"{name}-rim"), polygon_path(shapes["rim"]), fill=rim_color,
                         stroke="transparent", stroke_width=0)
    if shapes["fibres"]:
        fibres = path_layer(default_name(project, f"{name}-fibres"), fibre_path(shapes["fibres"]), fill="transparent",
                            stroke=rim_color, stroke_width=recipe.get("fibre_width", 0.8), line_cap="round")
    holder = layer
    if mode == "mask":
        mask = mask_image(shapes["face"], layer, resolve_layout(project)[layer["id"]][2:])
        if base_mask and base_mask.get("enabled", True):
            from PIL import ImageChops

            mask = ImageChops.multiply(mask, project.image(base_mask["asset"], "L").resize(mask.size))
        layer["mask"] = {"asset": add_image(project, mask, "masks"), "enabled": True}
    else:
        fill = recipe.get("fill", "#f1ebdf")
        d = polygon_path(shapes["face"])
        if previous:
            face = layer if mode == "path" else project.layer(carried["face"])
            face.update(path=d, path_view=[w, h], fill=fill, width=w, height=h,
                        **deepcopy(place if mode == "clip" else {}))
        else:
            face = path_layer(default_name(project, f"{name}-face"), d, fill=fill, stroke="transparent",
                              stroke_width=0)
        holder = layer if mode == "clip" else face
    for item in (rim, fibres, face if mode == "clip" else None):
        if item is not None:
            item["part_of"] = holder["id"]
    new = [item for item in (rim, None if previous else face, fibres) if item is not None]
    # Stack from the bottom: rim, face, fibres. A mask or clip tear tucks them under the layer, a
    # path tear puts them over it (or on top of the document), and a regrow keeps the old face.
    if previous and mode != "mask":
        spot = order.index(face)
        if rim is not None:
            order.insert(spot, rim)
        if fibres is not None:
            order.insert(order.index(face) + 1, fibres)
    elif layer is not None:
        spot = order.index(layer) + (1 if mode == "path" else 0)
        order[spot:spot] = new
    else:
        for item in new:
            append_layer(project, item)
    require(len(order) <= project.limits.max_layers, "Layer limit reached", "resource_limit")
    if mode == "clip":
        layer["clip"] = face["id"]
    holder["tear"] = {"recipe": recipe, "mode": mode, "name": name,
                      **{key: item["id"] for key, item in (("rim", rim), ("fibres", fibres)) if item is not None},
                      **({"base_mask": deepcopy(base_mask)} if mode == "mask" else {}),
                      **({"face": face["id"]} if mode == "clip" else {})}
    if mode == "path":
        project.state["active_layer"] = holder["id"]


# ---------------------------------------------------------------------------------------------
# Operations


def execute(project, op):
    if op["type"] == "irregular":
        return execute_irregular(project, op)
    return execute_tear(project, op)


def schemas(add):
    from .schema import S, B, POSITIVE_INT, enum

    seed = {"type": "integer", "minimum": 0,
            "description": "Required. The same seed always gives the same result; a new seed regrows it."}
    strength = {**enum("subtle", "natural", "rough"),
                "description": "Preset magnitudes, scaled to each layer's size. Default natural."}
    unit = {"type": "number", "minimum": 0, "maximum": 1}
    add("irregular", {
        "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS,
                    "description": "Several layers (groups expand to their vector layers); alternative to target."},
        "seed": seed,
        "strength": strength,
        "amount": {"type": "number", "minimum": 0, "maximum": 2,
                   "description": "Multiplier for the preset's magnitudes (not for fields you set). Default 1."},
        "only": {"type": "array", "items": enum(*EFFECTS), "uniqueItems": True,
                 "description": "Switch on only these effects from the preset; fields you set always apply."},
        "wobble": {"type": "number", "minimum": 0, "maximum": 500,
                   "description": "Largest outline displacement in pixels."},
        "wobble_length": {"type": "number", "minimum": 2, "maximum": 4000,
                          "description": "Correlation length of the wobble in pixels: long = waving, short = rough."},
        "jitter": {"type": "number", "minimum": 0, "maximum": 500,
                   "description": "Largest move of the path's own vertices, in pixels."},
        "roughness": {**unit, "description": "0 smooth waves to 1 fractal detail on the wobble."},
        "width_variation": {**unit, "description": "Each layer's stroke width changes by up to this fraction."},
        "pressure": {**unit, "description": "Stroke width varies along the line by up to this fraction (ink-like)."},
        "lightness_drift": {"type": "number", "minimum": 0, "maximum": 0.3,
                            "description": "Largest lightness shift of fill and stroke (OKLab L, 0-1)."},
        "chroma_drift": {**unit, "description": "Largest relative chroma change."},
        "hue_drift": {"type": "number", "minimum": 0, "maximum": 45, "description": "Largest hue shift in degrees."},
        "rotation_jitter": {"type": "number", "minimum": 0, "maximum": 45,
                            "description": "Largest rotation of each layer in degrees."},
        "scale_jitter": {"type": "number", "minimum": 0, "maximum": 0.5,
                         "description": "Each layer is scaled by 1 ± up to this fraction."},
        "position_jitter": {"type": "number", "minimum": 0, "maximum": 500,
                            "description": "Largest move of each layer in pixels."},
        "remove": {**B, "description": "Restore the layers to the source kept when irregular was first applied."},
    }, anyOf=[{"required": ["seed"]}, {"required": ["remove"]}])
    add("tear", {
        "name": S,
        "seed": seed,
        "strength": strength,
        "as": {**enum(*MODES),
               "description": "mask (default with a target): an alpha mask on the target. clip: a vector face layer "
                              "the target is clipped to. path (default without a target): free face, rim and fibre "
                              "layers, over the target if one is given."},
        "edges": {"type": "array", "items": enum(*EDGES, "all"), "minItems": 1, "maxItems": 5, "uniqueItems": True,
                  "description": "Which sides are torn; default bottom."},
        "depth": {"type": "number", "exclusiveMinimum": 0, "maximum": 8000,
                  "description": "Deepest bite in pixels (kept under 45% of the shorter side)."},
        "length": {"type": "number", "minimum": 2, "maximum": 4000,
                   "description": "Width of the widest bays in pixels."},
        "roughness": {**unit, "description": "0 gentle to 1 jagged fractal detail."},
        "rim_width": {"type": "number", "minimum": 0, "maximum": 1000,
                      "description": "Widest strip of exposed paper along the edge in pixels; 0 for none."},
        "rim_color": {**S, "description": "Paper-white rim and fibre color. Default #fffdf7."},
        "fibres": {**unit, "description": "Density of loose fibres along the edge."},
        "fibre_width": {"type": "number", "minimum": 0.1, "maximum": 10},
        "fill": {**S, "description": "Face color for as: path. Default #f1ebdf."},
        "x": {"type": "number", "description": "Standalone tear (no target): left edge."},
        "y": {"type": "number", "description": "Standalone tear (no target): top edge."},
        "width": POSITIVE_INT,
        "height": POSITIVE_INT,
        "remove": {**B, "description": "Undo the tear: the mask returns to what it was and the added layers go."},
    }, anyOf=[{"required": ["seed"]}, {"required": ["remove"]}])


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    if cmd == "irregular":
        p = Parser(prog="vixl irregular", description="Seeded, bounded imperfection for vector layers. Opt-in; see "
                   "docs/irregular.md.")
        p.add_argument("target", nargs="*", help="Layers or groups (default: the active layer)")
        p.add_argument("--seed", type=int)
        p.add_argument("--strength", choices=list(STRENGTHS))
        p.add_argument("--amount", type=float)
        p.add_argument("--only", nargs="+", choices=list(EFFECTS))
        for key in ("wobble", "wobble-length", "jitter", "roughness", "width-variation", "pressure",
                    "lightness-drift", "chroma-drift", "hue-drift", "rotation-jitter", "scale-jitter",
                    "position-jitter"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--remove", action="store_true", default=None)
        data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
        targets = data.pop("target", [])
        if len(targets) == 1:
            data["target"] = targets[0]
        elif targets:
            data["targets"] = targets
        return {"type": "irregular", **data}
    p = Parser(prog="vixl tear", description="A torn, ripped edge. See docs/irregular.md.")
    p.add_argument("target", nargs="?")
    p.add_argument("--name")
    p.add_argument("--seed", type=int)
    p.add_argument("--strength", choices=list(TEAR_STRENGTHS))
    p.add_argument("--as", dest="as_", choices=list(MODES))
    p.add_argument("--edges", nargs="+", choices=[*EDGES, "all"])
    for key in ("depth", "length", "roughness", "rim-width", "fibres", "fibre-width", "x", "y"):
        p.add_argument("--" + key, type=float)
    p.add_argument("--rim-color")
    p.add_argument("--fill")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--remove", action="store_true", default=None)
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if "as_" in data:
        data["as"] = data.pop("as_")
    return {"type": "tear", **data}
