"""Editable brush strokes: paint layers keep stroke data and re-render deterministically.

A paint layer stores strokes (points with optional pressure, a brush preset and overrides),
never pixels, so strokes stay editable, undoable and resolution-independent. Rendering
stamps brush dabs along a smoothed, arc-length-resampled path; seeded jitter, simulated
pressure tapers and paper/canvas textures make strokes look hand-made yet reproducible.
"""

from copy import deepcopy
from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageFilter

from .errors import require
from .model import finite, new_layer

BRUSH_TYPES = ("paint-layer", "paint", "paint-clear", "brush-define")
MAX_STROKES = 4096
MAX_POINTS = 10000
MAX_LAYER_POINTS = 200_000

BASE = {
    "shape": "round",
    "hardness": 0.9,
    "spacing": 0.1,
    "flow": 1.0,
    "build": "max",
    "jitter": 0.0,
    "size_jitter": 0.0,
    "angle": 0.0,
    "roundness": 1.0,
    "texture": "none",
    "texture_strength": 0.0,
    "taper": [0.0, 0.0],
    "pressure_size": True,
    "pressure_opacity": False,
    "wet_edges": False,
    "blend": "normal",
    "smoothing": True,
    "bristles": 0,
    "scatter": 0.0,
    "density": 0,
}
BRUSHES = {
    "round": {"description": "Hard round brush for clean, even strokes", "hardness": 0.95, "spacing": 0.08},
    "soft-round": {"description": "Soft-edged round brush for shading and glows", "hardness": 0.0, "spacing": 0.06},
    "airbrush": {"description": "Soft spray that builds up with overlapping passes", "hardness": 0.0, "flow": 0.08, "build": "accumulate", "spacing": 0.04, "pressure_opacity": True},
    "pencil": {"description": "Thin graphite pencil with paper grain", "hardness": 0.85, "spacing": 0.05, "texture": "grain", "texture_strength": 0.55, "jitter": 0.03, "taper": [0.05, 0.08], "pressure_opacity": True},
    "ink": {"description": "Ink pen with tapered, pressure-sensitive lines", "hardness": 1.0, "spacing": 0.04, "taper": [0.18, 0.32]},
    "fineliner": {"description": "Even technical pen with no taper", "hardness": 1.0, "spacing": 0.04, "pressure_size": False},
    "brush-pen": {"description": "Brush pen with strong thick-thin contrast", "hardness": 0.95, "spacing": 0.035, "taper": [0.25, 0.45], "roundness": 0.8, "angle": 35},
    "marker": {"description": "Chisel marker; overlaps darken slightly", "hardness": 0.85, "spacing": 0.05, "roundness": 0.55, "angle": 30, "blend": "multiply", "pressure_size": False},
    "highlighter": {"description": "Flat translucent highlighter", "hardness": 0.9, "spacing": 0.05, "roundness": 0.3, "angle": 0, "blend": "multiply", "pressure_size": False},
    "calligraphy": {"description": "Broad 45° nib: thick downstrokes, thin hairlines", "hardness": 1.0, "spacing": 0.03, "roundness": 0.14, "angle": 45, "pressure_size": False},
    "chalk": {"description": "Dry chalk with broken, grainy coverage", "hardness": 0.7, "spacing": 0.06, "texture": "grain", "texture_strength": 0.85, "jitter": 0.06, "size_jitter": 0.08},
    "charcoal": {"description": "Charcoal stick with paper tooth", "hardness": 0.5, "spacing": 0.06, "texture": "paper", "texture_strength": 0.75, "size_jitter": 0.12, "roundness": 0.7, "angle": 20, "pressure_opacity": True},
    "crayon": {"description": "Waxy crayon with gaps on rough paper", "hardness": 0.8, "spacing": 0.05, "texture": "paper", "texture_strength": 0.65, "jitter": 0.04},
    "watercolor": {"description": "Wet, translucent wash with darker pooled edges", "hardness": 0.25, "spacing": 0.05, "flow": 0.06, "build": "accumulate", "wet_edges": True, "texture": "paper", "texture_strength": 0.3, "size_jitter": 0.1, "pressure_size": False},
    "dry-brush": {"description": "Bristle brush leaving streaky paint", "shape": "bristle", "bristles": 22, "hardness": 0.8, "spacing": 0.04, "texture": "canvas", "texture_strength": 0.2, "taper": [0.05, 0.3], "pressure_size": False},
    "spray": {"description": "Spray-paint dots inside the brush radius", "shape": "spray", "density": 24, "hardness": 1.0, "spacing": 0.15, "pressure_size": False},
    "splatter": {"description": "Random droplets scattered around the stroke", "shape": "spray", "density": 5, "scatter": 1.2, "hardness": 1.0, "spacing": 0.35, "size_jitter": 0.6, "pressure_size": False},
}
SHAPES = ("round", "bristle", "spray")
TEXTURES = ("none", "grain", "paper", "canvas")
SETTINGS = tuple(k for k in BASE if k != "smoothing") + ("smoothing",)


def brush_settings(state, name, overrides=None):
    custom = state.get("brushes", {})
    require(name in BRUSHES or name in custom, f"Unknown brush {name!r}; use {', '.join(sorted(BRUSHES))}")
    settings = dict(BASE)
    if name in custom:
        base = custom[name].get("base", "round")
        settings.update({k: v for k, v in BRUSHES[base].items() if k != "description"})
        settings.update({k: v for k, v in custom[name].items() if k not in ("base", "description")})
    else:
        settings.update({k: v for k, v in BRUSHES[name].items() if k != "description"})
    settings.update(overrides or {})
    validate_settings(settings)
    return settings


def validate_settings(settings):
    require(set(settings) <= set(BASE), f"Unknown brush setting; use {', '.join(SETTINGS)}")
    require(settings["shape"] in SHAPES, f"Brush shape must be one of {', '.join(SHAPES)}")
    require(settings["texture"] in TEXTURES, f"Brush texture must be one of {', '.join(TEXTURES)}")
    require(settings["build"] in ("max", "accumulate"), "Brush build must be max or accumulate")
    require(settings["blend"] in ("normal", "multiply"), "Brush blend must be normal or multiply")
    for key, low, high in (
        ("hardness", 0, 1),
        ("spacing", 0.01, 4),
        ("flow", 0.001, 1),
        ("jitter", 0, 4),
        ("size_jitter", 0, 1),
        ("angle", -360, 360),
        ("roundness", 0.05, 1),
        ("texture_strength", 0, 1),
        ("scatter", 0, 8),
    ):
        finite(settings[key], key, low, high)
    taper = settings["taper"]
    require(isinstance(taper, list) and len(taper) == 2, "taper is [start, end] fractions of the stroke")
    for value in taper:
        finite(value, "taper", 0, 0.5)
    for key in ("pressure_size", "pressure_opacity", "wet_edges", "smoothing"):
        require(isinstance(settings[key], bool), f"{key} must be true or false")
    for key, high in (("bristles", 64), ("density", 256)):
        require(isinstance(settings[key], int) and 0 <= settings[key] <= high, f"{key} must be an integer 0–{high}")


def validate_paint(layer, state):
    from .design import resolve_color
    from .render import color

    strokes = layer["strokes"]
    surface = layer.get("surface")
    require(isinstance(surface, list) and len(surface) == 2, "Paint layers need a surface size")
    from .model import Limits

    Limits().size(*surface)
    require(isinstance(strokes, list) and len(strokes) <= MAX_STROKES, f"Paint layers hold at most {MAX_STROKES} strokes")
    total = 0
    for stroke in strokes:
        require(isinstance(stroke, dict) and set(stroke) <= STROKE_KEYS, "Invalid paint stroke")
        points = stroke["points"]
        require(isinstance(points, list) and 1 <= len(points) <= MAX_POINTS, f"Strokes need 1–{MAX_POINTS} points")
        for point in points:
            require(isinstance(point, list) and len(point) in (2, 3), "Stroke points are [x, y] or [x, y, pressure]")
            finite(point[0], "x", -1e6, 1e6)
            finite(point[1], "y", -1e6, 1e6)
            if len(point) == 3:
                finite(point[2], "pressure", 0, 1)
        total += len(points)
        finite(stroke["size"], "size", 0.5, 2000)
        finite(stroke.get("opacity", 1), "opacity", 0, 1)
        require(stroke.get("mode", "paint") in ("paint", "erase"), "Stroke mode must be paint or erase")
        require(isinstance(stroke.get("seed", 0), int) and stroke.get("seed", 0) >= 0, "Seed must be a nonnegative integer")
        color(resolve_color(stroke.get("color", "black"), state))
        brush_settings(state, stroke["brush"], stroke.get("settings"))
    require(total <= MAX_LAYER_POINTS, "Paint layer exceeds 200000 points", "resource_limit")


STROKE_KEYS = {"brush", "points", "size", "color", "opacity", "mode", "seed", "settings"}


def validate_brushes(state):
    for name, custom in state.get("brushes", {}).items():
        from .design import named

        named(name)
        require(name not in BRUSHES, f"{name} is a built-in brush")
        require(isinstance(custom, dict) and custom.get("base", "round") in BRUSHES, "Custom brushes extend a built-in base brush")
        brush_settings(state, name)


# ---------------------------------------------------------------------------------------------
# Geometry


def _catmull_rom(points, steps=6):
    """Smooth a polyline through its points; pressure is interpolated alongside."""
    if len(points) < 3:
        return points
    padded = np.vstack([points[0], points, points[-1]])
    result = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1 : i + 3]
        for t in np.linspace(0, 1, steps, endpoint=False):
            t2, t3 = t * t, t * t * t
            result.append(
                0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            )
    result.append(points[-1])
    return np.array(result)


def _resample(points, step):
    """Evenly spaced samples along the polyline: (positions, pressures, distances, length)."""
    xy = points[:, :2]
    segments = np.hypot(*np.diff(xy, axis=0).T) if len(points) > 1 else np.zeros(0)
    distance = np.concatenate([[0], np.cumsum(segments)])
    length = float(distance[-1])
    if length < 1e-6:
        return points[:1, :2], points[:1, 2], np.zeros(1), 0.0
    count = min(int(length / step) + 1, 200_000)
    samples = np.linspace(0, length, max(count, 2))
    x = np.interp(samples, distance, xy[:, 0])
    y = np.interp(samples, distance, xy[:, 1])
    pressure = np.interp(samples, distance, points[:, 2])
    return np.stack([x, y], axis=1), pressure, samples, length


def _smoothstep(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


# ---------------------------------------------------------------------------------------------
# Rendering


@lru_cache(maxsize=8)
def _texture(kind, shape):
    """Deterministic texture field in 0–1 at layer resolution (same for every stroke)."""
    h, w = shape
    rng = np.random.default_rng({"grain": 11, "paper": 23, "canvas": 37}[kind])
    if kind == "canvas":
        yy, xx = np.mgrid[0:h, 0:w]
        weave = 0.5 + 0.25 * np.sin(xx * 1.9) * np.sin(yy * 1.9) + 0.25 * np.sin((xx + yy) * 0.7)
        noise = rng.random((h, w))
        return np.clip(weave * 0.75 + noise * 0.25, 0, 1).astype(np.float32)
    noise = Image.fromarray(np.uint8(rng.random((h, w)) * 255))
    if kind == "paper":
        noise = noise.filter(ImageFilter.GaussianBlur(1.6))
        values = np.asarray(noise, dtype=np.float32) / 255
        values = (values - values.mean()) / max(values.std(), 1e-6) * 0.22 + 0.5
        return np.clip(values, 0, 1)
    return np.asarray(noise, dtype=np.float32) / 255


def _dab(radius, settings, angle, rng, bristles=None, offset=(0.0, 0.0)):
    """A single dab's alpha (float32) centered at ``offset`` from the middle pixel."""
    size = max(1, int(math.ceil(radius * 2 + 3)))
    if size % 2 == 0:
        size += 1
    c = size // 2
    yy, xx = np.mgrid[-c : c + 1, -c : c + 1].astype(np.float32)
    # Sub-pixel placement keeps soft edges smooth instead of stepping per whole pixel.
    xx -= offset[0]
    yy -= offset[1]
    shape = settings["shape"]
    if shape == "spray":
        dab = np.zeros((size, size), np.float32)
        count = max(1, settings["density"])
        r = radius * np.sqrt(rng.random(count))
        theta = rng.random(count) * 2 * math.pi
        dot = max(0.6, radius * (0.06 if settings["scatter"] == 0 else 0.16))
        for px, py in zip(r * np.cos(theta), r * np.sin(theta)):
            d = np.hypot(xx - px, yy - py)
            dab = np.maximum(dab, np.clip(dot + 0.5 - d, 0, 1))
        return dab
    rotation = math.radians(angle)
    cos, sin = math.cos(rotation), math.sin(rotation)
    u = xx * cos + yy * sin
    v = (-xx * sin + yy * cos) / settings["roundness"]
    distance = np.hypot(u, v) / max(radius, 0.5)
    hardness = settings["hardness"]
    if shape == "bristle":
        dab = np.zeros((size, size), np.float32)
        for spread, strength, width in bristles:
            d = np.hypot(u, v - spread * radius) / max(radius * width, 0.6)
            dab = np.maximum(dab, (1 - _smoothstep((d - 0.4) / 0.6)) * strength)
        return dab * (distance <= 1.05)
    edge = 1 - hardness
    if radius < 1.5:
        # Small dabs: area coverage keeps 1–3px lines visible and antialiased.
        return np.clip(radius + 0.5 - np.hypot(u, v), 0, 1).astype(np.float32)
    return (1 - _smoothstep((distance - hardness) / max(edge, 1e-3))).astype(np.float32) * (distance <= 1)


def stroke_alpha(stroke, settings, shape):
    """Coverage of one stroke as a float32 array of the layer's shape."""
    h, w = shape
    buffer = np.zeros(shape, np.float32)
    rng = np.random.default_rng(stroke.get("seed", 0))
    bristles = None
    if settings["shape"] == "bristle":
        count = max(2, settings["bristles"])
        # Each bristle: offset across the brush, paint load and thickness.
        bristles = list(zip(rng.uniform(-1, 1, count), rng.uniform(0.45, 1, count), rng.uniform(0.08, 0.2, count)))
    raw = np.array([[p[0], p[1], p[2] if len(p) == 3 else 1.0] for p in stroke["points"]], dtype=np.float64)
    if settings["smoothing"] and len(raw) >= 3:
        raw = _catmull_rom(raw)
    size = stroke["size"]
    step = max(0.35, settings["spacing"] * size)
    positions, pressure, distances, length = _resample(raw, step)
    start, end = settings["taper"]
    taper = np.ones(len(positions))
    if length > 0:
        if start:
            taper *= _smoothstep(distances / max(start * length, 1e-6)) * 0.85 + 0.15
        if end:
            taper *= _smoothstep((length - distances) / max(end * length, 1e-6)) * 0.85 + 0.15
    radii = size / 2 * taper * (pressure if settings["pressure_size"] else 1)
    if settings["size_jitter"]:
        radii = radii * np.clip(1 + settings["size_jitter"] * rng.standard_normal(len(radii)), 0.2, 2)
    alphas = settings["flow"] * (pressure if settings["pressure_opacity"] else np.ones(len(positions)))
    if settings["jitter"]:
        positions = positions + settings["jitter"] * size * rng.standard_normal(positions.shape) * 0.5
    if settings["scatter"]:
        positions = positions + settings["scatter"] * size * (rng.random(positions.shape) - 0.5) * 2
    angles = np.full(len(positions), float(settings["angle"]))
    if settings["shape"] == "bristle" and len(positions) > 1:
        # Bristles trail behind the brush: spread them across the direction of travel.
        dx, dy = np.gradient(positions[:, 0]), np.gradient(positions[:, 1])
        angles = np.degrees(np.arctan2(dy, dx))
    for (x, y), radius, alpha, angle in zip(positions, radii, alphas, angles):
        if radius < 0.25 or alpha <= 0:
            continue
        cx, cy = int(round(x)), int(round(y))
        dab = _dab(radius, settings, angle, rng, bristles, (x - cx, y - cy))
        c = dab.shape[0] // 2
        left, top = cx - c, cy - c
        x0, y0 = max(0, left), max(0, top)
        x1, y1 = min(w, left + dab.shape[1]), min(h, top + dab.shape[0])
        if x0 >= x1 or y0 >= y1:
            continue
        patch = dab[y0 - top : y1 - top, x0 - left : x1 - left] * alpha
        region = buffer[y0:y1, x0:x1]
        if settings["build"] == "accumulate":
            buffer[y0:y1, x0:x1] = region + patch * (1 - region)
        else:
            np.maximum(region, patch, out=region)
    if settings["texture"] != "none" and settings["texture_strength"]:
        texture = _texture(settings["texture"], shape)
        strength = settings["texture_strength"]
        buffer *= np.clip(1 - strength * (1 - texture) * 1.4, 0, 1)
    if settings["wet_edges"]:
        image = Image.fromarray(np.uint8(np.clip(buffer, 0, 1) * 255))
        blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(max(1, size * 0.12))), dtype=np.float32) / 255
        edge = np.clip(buffer - blurred, 0, 1)
        buffer = np.clip(buffer * 0.8 + edge * 1.6, 0, 1)
    return np.clip(buffer, 0, 1)


def paint_image(project, layer):
    """Render a paint layer's strokes to RGBA at the layer's own pixel size."""
    from .design import resolve_color
    from .render import color

    w, h = layer.get("surface", [layer["width"], layer["height"]])
    premultiplied = np.zeros((h, w, 4), np.float32)
    for stroke in layer["strokes"]:
        settings = brush_settings(project.state, stroke["brush"], stroke.get("settings"))
        coverage = stroke_alpha(stroke, settings, (h, w))
        r, g, b, a = (v / 255 for v in color(resolve_color(stroke.get("color", "black"), project.state)))
        alpha = coverage * stroke.get("opacity", 1) * a
        if stroke.get("mode", "paint") == "erase":
            premultiplied *= (1 - alpha)[:, :, None]
            continue
        source = np.array([r, g, b], np.float32)
        if settings["blend"] == "multiply":
            existing_alpha = premultiplied[:, :, 3:4]
            existing = np.where(existing_alpha > 0, premultiplied[:, :, :3] / np.maximum(existing_alpha, 1e-6), 1)
            tinted = source * (existing * existing_alpha + (1 - existing_alpha))
        else:
            tinted = np.broadcast_to(source, (h, w, 3))
        a3 = alpha[:, :, None]
        premultiplied[:, :, :3] = tinted * a3 + premultiplied[:, :, :3] * (1 - a3)
        premultiplied[:, :, 3] = alpha + premultiplied[:, :, 3] * (1 - alpha)
    out = np.zeros_like(premultiplied)
    visible = premultiplied[:, :, 3:4] > 1e-6
    out[:, :, :3] = np.where(visible, premultiplied[:, :, :3] / np.maximum(premultiplied[:, :, 3:4], 1e-6), 0)
    out[:, :, 3] = premultiplied[:, :, 3]
    return Image.fromarray(np.uint8(np.clip(out, 0, 1) * 255 + 0.5), "RGBA")


# ---------------------------------------------------------------------------------------------
# Operations


def _unique(project, base):
    names = {layer["name"] for layer in project.state["layers"]}
    if base not in names:
        return base
    index = 2
    while f"{base} {index}" in names:
        index += 1
    return f"{base} {index}"


def _new_paint_layer(project, op, default_name="paint"):
    from .operations import append_layer

    c = project.state["canvas"]
    w, h = op.get("width", c["width"]), op.get("height", c["height"])
    layer = new_layer(
        op.get("name") or _unique(project, default_name),
        "paint",
        w,
        h,
        strokes=[],
        surface=[w, h],
        x=op.get("x", 0),
        y=op.get("y", 0),
    )
    finite(layer["x"], "x")
    finite(layer["y"], "y")
    append_layer(project, layer)
    return layer


def path_points(path, samples_per_segment=24):
    """Points along a single-contour SVG path (M/L/H/V/Q/C/Z)."""
    from .geometry import path_polygons

    polygons = path_polygons(path)
    require(polygons and len(polygons[0]) >= 1, "Path has no points")
    return [[round(x, 2), round(y, 2)] for x, y in polygons[0]]


def execute_brush(project, op):
    from .render import resolve_layout

    kind = op["type"]
    state = project.state
    if kind == "brush-define":
        from .design import named

        name = named(op["name"])
        require(name not in BRUSHES, "Built-in brush names are reserved; choose another name")
        custom = {"base": op.get("base", "round"), **deepcopy(op.get("settings", {}))}
        if op.get("description"):
            custom["description"] = op["description"]
        state.setdefault("brushes", {})[name] = custom
        brush_settings(state, name)
        return
    if kind == "paint-layer":
        _new_paint_layer(project, op)
        return
    if kind == "paint":
        target = op.get("target")
        if target is None:
            active = state["active_layer"]
            current = next((item for item in state["layers"] if item["id"] == active), None)
            layer = current if current and current["type"] == "paint" else _new_paint_layer(project, {})
        else:
            layer = project.layer(target)
        require(layer["type"] == "paint", "Brush strokes need a paint layer (paint-layer creates one)")
        require(len(layer["strokes"]) < MAX_STROKES, "Paint layer stroke limit reached", "resource_limit")
        require(("points" in op) != ("path" in op), "Provide either points or path")
        points = deepcopy(op["points"]) if "points" in op else path_points(op["path"])
        if op.get("pressure") is not None:
            pressure = op["pressure"]
            require(isinstance(pressure, list) and len(pressure) == len(points), "pressure needs one value per point")
            points = [[p[0], p[1], q] for p, q in zip(points, pressure)]
        bounds = resolve_layout(project)[layer["id"]]
        if op.get("space", "canvas") == "canvas":
            # Canvas pixels → the layer's stroke surface (which may have been moved or resized).
            sw, sh = layer["surface"]
            fx, fy = sw / layer["width"], sh / layer["height"]
            require(layer.get("rotation", 0) % 360 == 0, "Paint on rotated layers with space='layer'")
            points = [[(p[0] - bounds[0]) * fx, (p[1] - bounds[1]) * fy, *p[2:]] for p in points]
            points = [
                [round(sw - x if layer.get("flip_x") else x, 2), round(sh - y if layer.get("flip_y") else y, 2), *rest]
                for x, y, *rest in points
            ]
        stroke = {
            "brush": op.get("brush", "round"),
            "points": points,
            "size": op.get("size", 12),
            "color": op.get("color", "black"),
        }
        for key in ("opacity", "mode", "seed"):
            if key in op:
                stroke[key] = op[key]
        overrides = deepcopy(op.get("settings", {}))
        require(isinstance(overrides, dict), "settings must be an object of brush overrides")
        if overrides:
            stroke["settings"] = overrides
        layer["strokes"].append(stroke)
        state["active_layer"] = layer["id"]
        validate_paint(layer, state)
        return
    layer = project.layer(op.get("target"))
    require(layer["type"] == "paint", "paint-clear needs a paint layer")
    if "last" in op:
        count = op["last"]
        require(isinstance(count, int) and count > 0, "last must be a positive integer")
        del layer["strokes"][-count:]
    else:
        layer["strokes"] = []


def schemas(add):
    from .schema import S, N, COORD, SIZE

    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 3}
    settings = {"type": "object", "description": "Brush overrides (vixl brushes): hardness, spacing, flow, taper …"}
    add("paint-layer", {"name": S, "width": SIZE, "height": SIZE, "x": COORD, "y": COORD})
    add(
        "paint",
        {
            "brush": S,
            "points": {"type": "array", "items": point, "minItems": 1, "maxItems": MAX_POINTS},
            "path": S,
            "pressure": {"type": "array", "items": N},
            "space": {"enum": ["canvas", "layer"]},
            "size": {"type": "number", "minimum": 0.5, "maximum": 2000},
            "color": S,
            "opacity": {"type": "number", "minimum": 0, "maximum": 1},
            "mode": {"enum": ["paint", "erase"]},
            "seed": {"type": "integer", "minimum": 0},
            "settings": settings,
        },
        oneOf=[{"required": ["points"]}, {"required": ["path"]}],
    )
    add("paint-clear", {"last": {"type": "integer", "minimum": 1}})
    add("brush-define", {"name": S, "base": S, "description": S, "settings": settings}, ["name"])


def catalog():
    return {
        "brushes": {name: {"description": value["description"], **{k: v for k, v in value.items() if k != "description"}} for name, value in BRUSHES.items()},
        "settings": {k: v for k, v in BASE.items()},
        "notes": "Points are canvas pixels [x, y] or [x, y, pressure]. Use path for SVG curves. "
        "Strokes stay editable; paint-clear removes the last N strokes.",
    }



def stroke_diagnostics(layer, project=None):
    """Resolved local centerline bounds, separate from actual rendered coverage."""
    result = []
    for index, stroke in enumerate(layer.get("strokes", [])):
        points = stroke["points"]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        bounds = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
        result.append({"index": index, "space": "layer", "bounds": bounds,
                       "surface": list(layer["surface"])})
        if project is not None:
            settings = brush_settings(project.state, stroke["brush"], stroke.get("settings"))
            w, h = layer["surface"]
            result[-1]["intersects_surface"] = bool(np.any(stroke_alpha(stroke, settings, (h, w)) > 0))
    return result
