"""Kinetic type: per-character, per-word and per-line animation of one text layer.

``text-animate`` stores a spec under ``timeline["text_animations"]``; the layer's text, font and
styles stay as they are, so the text remains editable. At each frame ``apply_frame`` computes a
pose (opacity, offset, scale, rotation, colour sweep) for every unit and leaves it on the
render-only copy as ``layer["_kinetic"]``; the raster text renderers (``text.render_text`` and
``richtext.render``) apply those poses while drawing the glyphs. Without a frame time (stills,
SVG, PDF, PPTX) nothing is attached and the layer draws its resting state.

Units are counted from the laid-out glyphs: a character is a visible glyph cluster, a word a run
of them between spaces or line breaks, a line a rendered (wrapped) line with visible glyphs.
"""

import math
import random
import re

from .errors import require
from .model import finite

UNITS = ("char", "word", "line")
PRESETS = ("fade", "fade-up", "fade-down", "slide-left", "slide-right", "pop", "wave", "typewriter", "color-sweep")
DIRECTIONS = ("forward", "reverse", "center", "edges", "random")
MODES = ("in", "out", "in-out")
EASING = {"pop": "ease-out-back", "wave": "ease-in-out-sine", "color-sweep": "ease-in-out", "typewriter": "linear"}
STAGGER = {"char": 40, "word": 120, "line": 250}
SPEC_KEYS = {"target", "unit", "preset", "start", "duration", "stagger", "easing", "direction", "seed", "mode",
             "distance", "amount", "from", "rotate", "repeat"}
MAX_PER_LAYER = 16
MAX_SPECS = 1024
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, None)  # opacity, dx, dy, scale, rotation, (sweep colour, progress)


# ---------------------------------------------------------------------------------------------
# Units


def assign(items):
    """Unit indices for glyphs given as ``[(cluster text, line)]``: ``(per-glyph (char, word, line)
    or None for blank glyphs, {unit: count})``. A glyph that continues a cluster (empty text) joins
    the unit of the glyph before it."""
    result, lines = [], {}
    char = word = -1
    gap, previous_line, last = True, None, None
    for text, line in items:
        if text == "" and last is not None:
            result.append(last)
            continue
        if not text.strip():
            gap, last = True, None
            result.append(None)
            continue
        if line != previous_line:
            gap = True
        char += 1
        if gap:
            word += 1
        last = (char, word, lines.setdefault(line, len(lines)))
        result.append(last)
        gap, previous_line = False, line
    return result, {"char": char + 1, "word": word + 1, "line": len(lines)}


def _rich_lines(result):
    tops = [top for top, *_ in result.lines]
    lines = []
    for glyph in result.glyphs:
        index = 0
        for i, top in enumerate(tops):
            if glyph.y >= top:
                index = i
        lines.append(index)
    return lines


def glyphs(project, layer):
    """``(kind, glyph list, per-glyph units, counts)`` for a text layer, where kind is "plain"
    (``text.placed_glyphs`` tuples plus the plan) or "rich" (``richtext.Placed`` plus the layout).
    None when the layer's glyphs are bent (warp, text on a path) or drawn by the fallback renderer."""
    from .richtext import active

    if active(layer):
        from .richtext import fitted

        layout = fitted(project, layer)
        units, counts = assign(list(zip((g.text for g in layout.glyphs), _rich_lines(layout))))
        return "rich", layout, units, counts
    from .text import UnsupportedText, placed_glyphs, plan

    try:
        layout = plan(project, layer)
        placed = placed_glyphs(project, layer, layout)
    except UnsupportedText:
        return None
    if placed is None:
        return None
    units, counts = assign([(item[5], item[6]) for item in placed])
    return "plain", (layout, placed), units, counts


# ---------------------------------------------------------------------------------------------
# Timing and poses


def ranks(direction, count, seed=0):
    """Start order of each unit: 0 starts first; units with equal rank start together."""
    if direction == "reverse":
        return [count - 1 - i for i in range(count)]
    if direction in ("center", "edges"):
        middle = (count - 1) / 2
        distance = [abs(i - middle) for i in range(count)]
        if direction == "edges":
            distance = [max(distance) - d for d in distance] if distance else []
        low = min(distance, default=0)
        return [d - low for d in distance]
    if direction == "random":
        order = list(range(count))
        random.Random(seed).shuffle(order)
        result = [0] * count
        for rank, index in enumerate(order):
            result[index] = rank
        return result
    return list(range(count))


def stagger_ms(spec, count):
    value = spec.get("stagger")
    if value is None:
        if spec["preset"] == "typewriter":
            return spec["duration"] / max(count, 1)
        return STAGGER[spec["unit"]]
    if isinstance(value, str):
        return spec["duration"] * float(value.strip().rstrip("%")) / 100
    return value


def span(spec, count):
    """Milliseconds from the first unit's start to the last unit's end of one pass."""
    order = ranks(spec.get("direction", "forward"), count, spec.get("seed", 0))
    return max(order, default=0) * stagger_ms(spec, count) + _unit_length(spec)


def _unit_length(spec):
    return 1 if spec["preset"] == "typewriter" else spec["duration"]


def _clamp(value, low=0.0, high=1.0):
    return min(max(value, low), high)


def pose(spec, k, size):
    """The unit's pose at progress ``k`` (1 is the resting state; may overshoot with back easings)."""
    preset = spec["preset"]
    opacity, dx, dy, scale, rotation, sweep = IDENTITY
    distance = spec.get("distance")
    if preset in ("fade", "fade-up", "fade-down", "slide-left", "slide-right"):
        opacity = _clamp(k)
        if preset == "fade-up":
            dy = (size * 0.35 if distance is None else distance) * (1 - k)
        elif preset == "fade-down":
            dy = -(size * 0.35 if distance is None else distance) * (1 - k)
        elif preset == "slide-left":
            dx = -(size * 1.5 if distance is None else distance) * (1 - k)
        elif preset == "slide-right":
            dx = (size * 1.5 if distance is None else distance) * (1 - k)
    elif preset == "pop":
        scale = max(0.0, k)
        opacity = _clamp(k * 2)
    elif preset == "wave":
        dy = -(size * 0.3 if spec.get("amount") is None else spec["amount"]) * math.sin(math.pi * _clamp(k))
    elif preset == "typewriter":
        opacity = 1.0 if k >= 0.5 else 0.0
    elif preset == "color-sweep" and k < 1:
        sweep = (spec.get("from"), _clamp(k))
    if spec.get("rotate") and preset != "wave":
        rotation = spec["rotate"] * (1 - _clamp(k))
    return (opacity, dx, dy, scale, rotation, sweep)


def unit_poses(spec, count, time, timeline_duration, size):
    """The pose of each of ``count`` units at ``time`` (ms)."""
    from .timeline import easing_function

    ease = easing_function(spec.get("easing") or EASING.get(spec["preset"], "ease-out-cubic"))
    order = ranks(spec.get("direction", "forward"), count, spec.get("seed", 0))
    step = stagger_ms(spec, count)
    length = _unit_length(spec)
    mode = spec.get("mode", "in")
    start = spec["start"]
    out_start = timeline_duration - span(spec, count) if mode == "in-out" else start
    result = []
    for rank in order:
        offset = rank * step
        if spec["preset"] == "wave":
            elapsed = time - start - offset
            if spec.get("repeat"):
                progress = (elapsed / length) % 1.0
            else:
                progress = _clamp(elapsed / length)
            result.append(pose(spec, ease(progress), size))
            continue
        if mode == "in" or (mode == "in-out" and time < out_start + offset):
            k = ease(_clamp((time - start - offset) / length))
        else:
            k = ease(1 - _clamp((time - out_start - offset) / length))
        result.append(pose(spec, k, size))
    return result


def combine(a, b):
    sweep = b[5] if b[5] is not None else a[5]
    return (a[0] * b[0], a[1] + b[1], a[2] + b[2], a[3] * b[3], a[4] + b[4], sweep)


def resting(item):
    return (abs(item[0] - 1) < 1e-6 and abs(item[1]) < 1e-6 and abs(item[2]) < 1e-6 and abs(item[3] - 1) < 1e-6
            and abs(item[4]) < 1e-6 and item[5] is None)


def layer_poses(project, layer, specs, time, duration, counts=None):
    """``{unit: [pose per unit]}`` combining every spec on the layer, or None when every unit rests."""
    if counts is None:
        found = glyphs(project, layer)
        if found is None:
            return None
        counts = found[3]
    combined = {}
    size = float(layer.get("size", 48))
    for spec in specs:
        count = counts[spec["unit"]]
        poses = unit_poses(spec, count, time, duration, size)
        current = combined.setdefault(spec["unit"], [IDENTITY] * count)
        combined[spec["unit"]] = [combine(x, y) for x, y in zip(current, poses)]
    if all(resting(item) for poses in combined.values() for item in poses):
        return None
    return {unit: [list(item[:5]) + [list(item[5]) if item[5] else None] for item in poses] for unit, poses in combined.items()}


def specs_by_layer(timeline):
    result = {}
    for spec in timeline.get("text_animations") or []:
        result.setdefault(spec["target"], []).append(spec)
    return result


def apply_frame(candidate, timeline, time):
    """Attach the poses at ``time`` to each animated text layer of a render-only copy."""
    layers = {layer["id"]: layer for layer in candidate.state["layers"]}
    for target, specs in specs_by_layer(timeline).items():
        layer = layers.get(target)
        if layer is None or layer["type"] != "text":
            continue
        poses = layer_poses(candidate, layer, specs, time, timeline["duration"])
        if poses:
            layer["_kinetic"] = poses


def hidden(layer):
    """True when the attached poses leave every glyph (nearly) transparent."""
    poses = layer.get("_kinetic")
    return bool(poses) and any(units and all(item[0] <= 0.01 for item in units) for units in poses.values())


# ---------------------------------------------------------------------------------------------
# Drawing


def multiply(a, b):
    """``a`` after ``b`` for 2x3 affine matrices ``(a, b, c, d, e, f)`` in SVG order."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3],
            a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _about(center, dx, dy, scale, rotation):
    cx, cy = center
    turn = math.radians(rotation)
    c, s = math.cos(turn) * scale, math.sin(turn) * scale
    # Translate the centre to the origin, scale and turn, then move back plus the offset.
    return (c, s, -s, c, cx + dx - (c * cx - s * cy), cy + dy - (s * cx + c * cy))


def glyph_boxes(items):
    """Ink box of each glyph ``(data, name, x, y, size, skew)`` in image pixels, or None."""
    from .text import face, glyph_outline

    boxes = []
    for data, name, x, y, size, skew in items:
        _, box = glyph_outline(data, name)
        if not box:
            boxes.append(None)
            continue
        f = size / face(data)[0]["head"].unitsPerEm
        xs = [x + (box[0] + skew * box[1]) * f, x + (box[2] + skew * box[3]) * f, x + (box[0] + skew * box[3]) * f,
              x + (box[2] + skew * box[1]) * f]
        boxes.append((min(xs), y - box[3] * f, max(xs), y - box[1] * f))
    return boxes


def motion(poses, units, boxes, colors):
    """Per glyph ``(matrix prefix, opacity, fill rgba or None)`` from unit poses. ``colors`` is
    each glyph's own fill (0-255 RGBA), the colour a sweep ends on."""
    from .colors import mix, parse

    centres = {}
    for unit in poses:
        position = UNITS.index(unit)
        gathered = {}
        for owner, box in zip(units, boxes):
            if owner is None or box is None:
                continue
            area = gathered.setdefault(owner[position], [math.inf, math.inf, -math.inf, -math.inf])
            area[:] = [min(area[0], box[0]), min(area[1], box[1]), max(area[2], box[2]), max(area[3], box[3])]
        centres[unit] = {k: ((v[0] + v[2]) / 2, (v[1] + v[3]) / 2) for k, v in gathered.items()}
    result = []
    for owner, own in zip(units, colors):
        prefix, opacity, fill = (1, 0, 0, 1, 0, 0), 1.0, None
        if owner is not None:
            for unit in ("line", "word", "char"):
                if unit not in poses:
                    continue
                index = owner[UNITS.index(unit)]
                if index >= len(poses[unit]):
                    continue
                o, dx, dy, scale, rotation, sweep = poses[unit][index]
                opacity *= o
                if dx or dy or scale != 1 or rotation:
                    centre = centres[unit].get(index, (0.0, 0.0))
                    prefix = multiply(_about(centre, dx, dy, scale, rotation), prefix)
                if sweep:
                    start = parse(sweep[0]) if sweep[0] else (*(v / 255 for v in own[:3]), own[3] / 255 * 0.25)
                    mixed = mix(start, tuple(v / 255 for v in own), sweep[1], "oklab")
                    fill = tuple(round(_clamp(v) * 255) for v in mixed)
        result.append((prefix, _clamp(opacity), fill))
    return result


def padding(boxes, prefixes, width, height, extra=0):
    """Margins ``(x, y)`` that keep every moved glyph inside a canvas centred on the box."""
    mx = my = 0.0
    for box, prefix in zip(boxes, prefixes):
        if box is None or prefix == (1, 0, 0, 1, 0, 0):
            continue
        for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
            px = prefix[0] * x + prefix[2] * y + prefix[4]
            py = prefix[1] * x + prefix[3] * y + prefix[5]
            mx, my = max(mx, -px, px - width), max(my, -py, py - height)
    return math.ceil(mx + extra) + 1 if mx else 0, math.ceil(my + extra) + 1 if my else 0


def svg_canvas(width, height, mx, my):
    """SVG root attributes for a ``width`` x ``height`` box padded by ``(mx, my)`` on each side,
    centred the way the layer pipeline places an overflowing vector image."""
    w, h = max(1, math.ceil(width)), max(1, math.ceil(height))
    size = (w + 2 * mx, h + 2 * my)
    return size, {"width": str(size[0]), "height": str(size[1]),
                  "viewBox": f"{-mx - (w - width) / 2} {-my - (h - height) / 2} {size[0]} {size[1]}"}


def render_plain(project, layer, layout, placed):
    """``text.render_text`` with unit poses applied."""
    import io
    import xml.etree.ElementTree as ET

    import resvg_py
    from PIL import Image

    from .design import resolve_color
    from .render import color
    from .text import Plan, append_paths, face, glyph_outline

    units, _ = assign([(item[5], item[6]) for item in placed])
    fill = color(resolve_color(layer.get("color", "white"), project.state))
    boxes = glyph_boxes([(d, n, x, y, s, 0) for d, n, x, y, s, *_ in placed])
    moves = motion(layer["_kinetic"], units, boxes, [fill] * len(placed))
    paths, kept = [], []
    for item, move in zip(placed, moves):
        data, name, x, y, size = item[:5]
        path, _ = glyph_outline(data, name)
        if not path:
            continue
        f = size / face(data)[0]["head"].unitsPerEm
        paths.append((path, (f, 0, 0, -f, x, y)))
        kept.append(move)
    mx, my = padding(boxes, [m[0] for m in moves], layout.width, layout.height, layer.get("stroke_width", 0))
    (w, h), attrs = svg_canvas(layout.width, layout.height, mx, my)
    project.limits.size(w, h)
    root = ET.Element("{http://www.w3.org/2000/svg}svg", attrs)
    append_paths(root, Plan(layout.width, layout.height, paths, layout.box), layer, project, motion=kept)
    image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode")))).convert("RGBA")
    image.info["vixl_vector_overflow"] = True
    return image


def rich_motion(project, layer, result):
    """Per-glyph motion and padding for a rich text layout."""
    from .richtext import SYNTHETIC_SKEW

    units, _ = assign(list(zip((g.text for g in result.glyphs), _rich_lines(result))))
    boxes = glyph_boxes([(g.data, g.name, g.x, g.y, g.size, SYNTHETIC_SKEW if g.italic else 0) for g in result.glyphs])
    moves = motion(layer["_kinetic"], units, boxes, [g.color for g in result.glyphs])
    return moves, boxes


# ---------------------------------------------------------------------------------------------
# Operation


def _resolve_stagger(value, duration, markers):
    from .timeline import parse_time

    if isinstance(value, str) and value.strip().endswith("%"):
        number = value.strip()[:-1]
        try:
            finite(float(number), "stagger percent", 0, 10000)
        except ValueError:
            require(False, f"Invalid stagger {value!r}; use ms, '80ms', '0.1s' or a percent of duration such as '30%'",
                    field="stagger")
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return finite(value, "stagger", 0, 600000)
    return parse_time(value, duration, markers)


def check_layer(project, layer):
    require(layer["type"] == "text", f"text-animate animates a text layer; {layer['name']!r} is a {layer['type']} layer",
            field="target")
    settings = layer.get("text_layout") or {}
    require(not settings.get("path") and settings.get("warp", "none") == "none",
            f"text-animate cannot move the glyphs of {layer['name']!r}: warped text and text on a path bend their glyphs. "
            "Remove the warp/path, or use animate-preset on the whole layer", field="target")
    found = glyphs(project, layer)
    require(found is not None, f"text-animate needs outline text; {layer['name']!r} uses a font drawn by the fallback "
            "renderer (bitmap or colour font)", field="target")
    return found


def execute(project, op, timeline, note):
    from .colors import parse
    from .design import resolve_color
    from .timeline import easing_function, parse_time, MAX_DURATION

    specs = timeline.setdefault("text_animations", [])
    layer = project.layer(op.get("target") or project.state["active_layer"])
    if op.get("remove"):
        timeline["text_animations"] = [s for s in specs if s["target"] != layer["id"]
                                       or ("preset" in op and s["preset"] != op["preset"])]
        if not timeline["text_animations"]:
            timeline.pop("text_animations")
        return
    require("preset" in op, "text-animate needs a preset", field="preset")
    require(op["preset"] in PRESETS, f"Unknown text-animate preset {op['preset']!r}; use {', '.join(PRESETS)}", field="preset")
    _, _, _, counts = check_layer(project, layer)
    duration, markers = timeline["duration"], timeline.get("markers", {})
    unit = op.get("unit", "char")
    require(unit in UNITS, f"unit must be one of {', '.join(UNITS)}", field="unit")
    spec = {"target": layer["id"], "unit": unit, "preset": op["preset"],
            "start": parse_time(op.get("start", 0), duration, markers),
            "duration": parse_time(op.get("duration", 500), duration, markers)}
    require(spec["duration"] >= 10, "duration must be at least 10 ms", field="duration")
    if "stagger" in op:
        spec["stagger"] = _resolve_stagger(op["stagger"], duration, markers)
    if op.get("easing"):
        easing_function(op["easing"])
        spec["easing"] = op["easing"]
    direction = op.get("direction", "forward")
    require(direction in DIRECTIONS, f"direction must be one of {', '.join(DIRECTIONS)}", field="direction")
    if direction != "forward":
        spec["direction"] = direction
    if direction == "random":
        seed = op.get("seed", 0)
        require(isinstance(seed, int) and not isinstance(seed, bool), "seed must be an integer", field="seed")
        spec["seed"] = seed
    looping = timeline.get("loop_mode") == "seamless"
    mode = op.get("mode", "in-out" if looping and op["preset"] != "wave" else "in")
    require(mode in MODES, f"mode must be one of {', '.join(MODES)}", field="mode")
    spec["mode"] = mode
    for key, low, high in (("distance", -1e5, 1e5), ("amount", -1e5, 1e5), ("rotate", -3600, 3600)):
        if key in op:
            spec[key] = finite(op[key], key, low, high)
    if "from" in op:
        require(op["preset"] == "color-sweep", "from is the starting colour of color-sweep", field="from")
        require(isinstance(op["from"], str), "from must be a colour", field="from")
        parse(resolve_color(op["from"], project.state))
        spec["from"] = resolve_color(op["from"], project.state)
    if op.get("repeat"):
        require(op["preset"] == "wave", "repeat cycles the wave preset; other presets play once (use mode in-out for loops)",
                field="repeat")
        spec["repeat"] = True
    kept = [s for s in specs if not (s["target"] == layer["id"] and s["preset"] == spec["preset"] and s["unit"] == unit)]
    require(sum(1 for s in kept if s["target"] == layer["id"]) < MAX_PER_LAYER, "Too many text animations on one layer",
            "resource_limit")
    require(len(kept) < MAX_SPECS, "Text animation limit reached", "resource_limit")
    kept.append(spec)
    timeline["text_animations"] = kept
    count = counts[unit]
    length = span(spec, count)
    end = spec["start"] + (0 if spec.get("repeat") else length)
    needed = end if mode != "in-out" else spec["start"] + 2 * length
    if needed > timeline["duration"]:
        if op.get("extend", True) and mode != "in-out":
            old = timeline["duration"]
            require(needed <= MAX_DURATION, "Timeline exceeds 10 minutes")
            timeline["duration"] = math.ceil(needed)
            note(f"timeline duration changed {old} -> {timeline['duration']} ms: the last {unit} of {layer['name']!r} "
                 f"finishes at {math.ceil(needed)} ms. Pass extend: false to keep {old} ms")
        else:
            note(f"text-animate on {layer['name']!r} needs {math.ceil(needed)} ms ({count} {unit} unit(s)"
                 + (", in and out" if mode == "in-out" else "") + f") but the timeline is {timeline['duration']} ms: "
                 "shorten duration or stagger, or lengthen the timeline")
    if spec.get("repeat") and looping and timeline["duration"] % spec["duration"]:
        note(f"the wave on {layer['name']!r} repeats every {spec['duration']} ms, which does not divide the "
             f"{timeline['duration']} ms loop: the loop jumps at the seam")
    elif looping and mode == "in" and spec["preset"] != "wave":
        note(f"text-animate {spec['preset']} on {layer['name']!r} ends at rest but starts hidden, so the seamless loop "
             "jumps at the seam; pass mode: in-out to play it out again before the loop ends")


def validate(state, timeline):
    from .timeline import easing_function

    specs = timeline.get("text_animations", [])
    require(isinstance(specs, list) and len(specs) <= MAX_SPECS, "Invalid text animations", "invalid_project")
    layers = {layer["id"]: layer for layer in state["layers"]}
    for spec in specs:
        require(isinstance(spec, dict) and {"target", "unit", "preset", "start", "duration"} <= set(spec) <= SPEC_KEYS,
                "Invalid text animation", "invalid_project")
        require(spec["target"] in layers and layers[spec["target"]]["type"] == "text",
                "Text animation targets a missing or non-text layer", "invalid_project")
        require(spec["unit"] in UNITS and spec["preset"] in PRESETS and spec.get("mode", "in") in MODES
                and spec.get("direction", "forward") in DIRECTIONS, "Invalid text animation", "invalid_project")
        for key in ("start", "duration"):
            require(isinstance(spec[key], int) and 0 <= spec[key] <= 600_000, "Invalid text animation time", "invalid_project")
        if "easing" in spec:
            easing_function(spec["easing"])
        if "stagger" in spec:
            stagger = spec["stagger"]
            require(isinstance(stagger, str) and re.fullmatch(r"\d+(\.\d+)?%", stagger) or isinstance(stagger, (int, float))
                    and not isinstance(stagger, bool) and 0 <= stagger <= 600_000, "Invalid text animation stagger",
                    "invalid_project")


def seam_findings(project, timeline):
    """Text animations whose units pose differently at the loop end than at t=0."""
    result = []
    layers = {layer["id"]: layer for layer in project.state["layers"]}
    for target, specs in specs_by_layer(timeline).items():
        layer = layers.get(target)
        if layer is None:
            continue
        found = glyphs(project, layer)
        if found is None:
            continue
        first = layer_poses(project, layer, specs, 0, timeline["duration"], found[3])
        last = layer_poses(project, layer, specs, timeline["duration"], timeline["duration"], found[3])
        if not _same(first, last):
            result.append(layer)
    return result


def _same(a, b):
    if a is None or b is None:
        return a is b
    if a.keys() != b.keys():
        return False
    for unit in a:
        for x, y in zip(a[unit], b[unit]):
            if any(abs(p - q) > 1e-3 for p, q in zip(x[:5], y[:5])) or bool(x[5]) != bool(y[5]):
                return False
    return True


def inspect(project, timeline):
    names = {layer["id"]: layer for layer in project.state["layers"]}
    result = []
    for spec in timeline.get("text_animations") or []:
        layer = names.get(spec["target"])
        found = glyphs(project, layer) if layer else None
        count = found[3][spec["unit"]] if found else 0
        result.append({**{k: v for k, v in spec.items()}, "layer": layer["name"] if layer else spec["target"],
                       "units": count, "stagger_ms": round(stagger_ms(spec, count), 3), "span_ms": round(span(spec, count), 3)})
    return result


def schemas(add):
    from .schema import B, N, S, field
    from .timeline import easing_schema

    time = {"type": ["number", "string"]}
    add("text-animate", {
        "preset": {"enum": list(PRESETS), "description": "Per-unit motion: fade, fade-up, fade-down, slide-left (units enter from "
                   "the left), slide-right, pop (scale up from 0), wave (rise and settle; repeat cycles it), typewriter "
                   "(units appear one by one), color-sweep (from a colour to the text's own)."},
        "unit": {"enum": list(UNITS), "description": "What moves on its own: char (each visible character), word, or line "
                 "(each rendered, wrapped line). Default char."},
        "start": field(time, "When the first unit starts: ms, '1.2s', '50%' of the timeline or a marker. Default 0."),
        "duration": field(time, "How long each unit's motion lasts (ms or '0.5s'; default 500). For typewriter, the time "
                          "to type the whole text when stagger is not given."),
        "stagger": {"type": ["number", "string"], "description": "Delay between successive units' starts: ms, '80ms', '0.1s', "
                    "or a percentage of duration such as '30%'. Default 40 ms per char, 120 per word, 250 per line "
                    "(typewriter: duration divided by the unit count)."},
        "easing": easing_schema("Easing of each unit's motion (default ease-out-cubic; pop ease-out-back, wave ease-in-out-sine)."),
        "direction": {"enum": list(DIRECTIONS), "description": "Order in which units start: forward (reading order, default), "
                      "reverse, center (from the middle out), edges (from both ends in), random (seeded by seed)."},
        "seed": {"type": "integer", "description": "Seed for direction random; the same seed gives the same order."},
        "mode": {"enum": list(MODES), "description": "in (default): units animate into their resting state. out: they "
                 "leave it (the entrance played backwards). in-out: in from start, then out again so the last unit is "
                 "hidden at the timeline end, which makes a seamless loop; the default when timeline loop_mode is seamless."},
        "distance": field(N, "Travel in pixels for fade-up/fade-down (default 0.35 x font size) and slide-left/slide-right "
                          "(default 1.5 x font size)."),
        "amount": field(N, "Height of the wave in pixels (default 0.3 x font size)."),
        "rotate": field(N, "Degrees each unit turns from as it enters (any preset but wave), about its own centre."),
        "from": field(S, "color-sweep: the colour units start from (default the text colour at 25% opacity)."),
        "repeat": field(B, "wave only: cycle the wave every duration ms for the whole timeline (a ripple that never "
                        "rests; make the timeline a whole number of cycles for a seamless loop)."),
        "remove": field(B, "true removes this layer's text animations (only the given preset's when preset is set)."),
        "extend": field(B, "Default true: when the last unit finishes past the timeline end, lengthen the timeline (the "
                        "result's warnings say so). False keeps the duration."),
    })
