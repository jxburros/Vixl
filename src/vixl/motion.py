"""Bounded, deterministic motion recipes compiled to ordinary editable timeline keys.

Coordinates and gravity use pixels and seconds; operation times use milliseconds.
"""
import math
from .errors import require
from .geometry import compact_number
from .model import MAX_LAYERS, finite

TYPES = ("motion", "keyframes")
RECIPES = ("follow-path", "orbit", "bounce", "shake", "wiggle", "spring", "look-at", "overlap", "breathing", "blink", "hover", "spin",
           "attach", "line-boil")
SAMPLE_FUNCTIONS = ("sin", "cos", "triangle", "saw", "square", "noise")
BOIL_STRENGTHS = ("subtle", "natural", "rough")
# Recipes whose duration defaults to the rest of the timeline rather than one second.
FILL_RECIPES = ("spin", "attach", "wiggle", "line-boil")


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N, B
    from .timeline import easing_schema
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    time = {"type": ["number", "string"]}
    add("motion", {"recipe": {"enum": list(RECIPES)}, "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS},
        "start": time, "duration": time, "period": N, "amount": N, "frequency": N, "damping": N,
        "gravity": N, "restitution": N, "radius": N, "center": point, "points": {"type": "array", "items": point, "minItems": 2, "maxItems": 256},
        "to": {"type": ["number", "string"], "description": "spring: end value. attach: the layer to ride on (same as follow)."},
        "anchor": {"anyOf": [point, {"type": "string"}], "description": "attach: the point of the followed layer to "
                   "ride on, in its own box: [fx, fy] fractions (units: fraction, default), [x, y] pixels from its top-left "
                   "corner (units: px) or an anchor name (center, top-right …). Default: where the layer is now."},
        "units": {"enum": ["fraction", "px"], "description": "attach: how anchor reads (default fraction)."},
        "offset": {**point, "description": "attach: [dx, dy] pixels added to the anchor, in the followed layer's own "
                   "frame (it turns and scales with that layer)."},
        "rotation": {"type": "boolean", "description": "attach: also turn with the followed layer (default true); "
                     "false keeps the layer upright and moves it only."},
        "property": S, "follow": S, "stagger": N, "children": B, "samples": {"type": "integer", "minimum": 2, "maximum": 512},
        "phase": N, "easing": easing_schema(), "extend": B,
        "turns": N,
        "symmetry": {"type": "integer", "minimum": 1, "maximum": 1000},
        "close": B,
        "fps": {"type": "number", "minimum": 1, "maximum": 30, "description": "line-boil: redraws per second, each "
                "held until the next (default 10; 8-12 reads as hand-drawn boil)."},
        "variants": {"type": "integer", "minimum": 2, "maximum": 8, "description": "line-boil: how many wobbled "
                     "drawings cycle (default 3); each is a copy of the layer, so this multiplies its layers."},
        "seed": {"type": "integer", "minimum": 0, "description": "line-boil: seed of the first drawing; the others use "
                 "the next seeds."},
        "strength": {"enum": list(BOIL_STRENGTHS), "description": "line-boil: wobble strength (default subtle)."}},
        ["recipe"])
    sample = {"type": "object", "description": "Generate the keys from a periodic function instead of listing them: "
              "{fn: sin|cos|triangle|saw|square|noise, period (ms), amplitude, offset, phase (cycles), step_ms or "
              "samples, duration (ms), start (ms), seed (noise)}. value = offset + amplitude * fn(phase + t/period).",
              "properties": {"fn": {"enum": list(SAMPLE_FUNCTIONS)}, "period": {"type": "number", "exclusiveMinimum": 0},
                             "amplitude": N, "offset": N, "phase": N,
                             "step_ms": {"type": "number", "minimum": 1}, "samples": {"type": "integer", "minimum": 1,
                                                                                    "maximum": 8192},
                             "duration": {"type": "number", "exclusiveMinimum": 0}, "start": N,
                             "seed": {"type": "integer", "minimum": 0}},
              "required": ["fn"], "additionalProperties": False}
    add("keyframes", {"property": S, "keys": {"type": "array", "minItems": 1, "maxItems": 8192,
        "items": {"type": "object", "properties": {"time": time, "value": {}, "easing": easing_schema()}, "required": ["time", "value"], "additionalProperties": False}},
        "sample": sample, "extend": B}, ["property"], anyOf=[{"required": ["keys"]}, {"required": ["sample"]}])


def sampled_keys(project, spec):
    """Keys from a ``sample`` spec: a periodic function sampled every ``step_ms`` (or ``samples``
    times) over ``duration``. Square waves hold between keys; the rest are linear."""
    from .timeline import _timeline

    settings = _timeline(project)
    fn = spec["fn"]
    period = finite(spec.get("period", 1000), "sample.period", 1, 600000)
    duration = finite(spec.get("duration", settings["duration"]), "sample.duration", 1, 600000)
    start = finite(spec.get("start", 0), "sample.start", 0, 600000)
    amplitude = finite(spec.get("amplitude", 1), "sample.amplitude", -1e6, 1e6)
    offset = finite(spec.get("offset", 0), "sample.offset", -1e6, 1e6)
    phase = finite(spec.get("phase", 0), "sample.phase", -1e4, 1e4)
    require(not ("step_ms" in spec and "samples" in spec), "sample takes step_ms or samples, not both", field="sample.samples")
    if "samples" in spec:
        count = spec["samples"]
    else:
        step = finite(spec.get("step_ms", 1000 / settings.get("fps", 30)), "sample.step_ms", 1, 600000)
        count = max(1, math.ceil(duration / step - 1e-9))
    require(isinstance(count, int) and 1 <= count <= 8192, "sample makes 1-8192 keys; raise step_ms", "resource_limit",
            field="sample.step_ms")
    times = [start + duration * i / count for i in range(count + 1)]
    cycles = [phase + (t - start) / period for t in times]
    if fn == "noise":
        import numpy as np
        from .irregular import correlated_noise

        rng = np.random.default_rng([spec.get("seed", 0), 7])
        loop = (times[-1] - start) / period
        closed = abs(loop - round(loop)) < 1e-9 and round(loop) >= 1
        values = correlated_noise(rng, [(c - phase) * period for c in cycles], period, duration, closed, 2, 0.5)
        values = [float(v) for v in values]
    else:
        wave = {"sin": lambda c: math.sin(math.tau * c), "cos": lambda c: math.cos(math.tau * c),
                "triangle": lambda c: 1 - 4 * abs((c + 0.25) % 1 - 0.5), "saw": lambda c: 2 * (c % 1) - 1,
                "square": lambda c: 1.0 if c % 1 < 0.5 else -1.0}[fn]
        values = [wave(c) for c in cycles]
    easing = "hold" if fn == "square" else "linear"
    return [{"time": round(t, 3), "value": round(offset + amplitude * v, 6), "easing": easing} for t, v in zip(times, values)]


def line_boil(project, op, targets, start, length):
    """Hand-drawn line boil: ``variants`` copies of each target, each wobbled by irregular with
    its own seed, shown one at a time and held for 1/fps seconds, cycling."""
    from .operations import execute as apply
    from .timeline import execute_timeline
    from .scatter import Namer

    fps = finite(op.get("fps", 10), "fps", 1, 30)
    variants = op.get("variants", 3)
    require(isinstance(variants, int) and 2 <= variants <= 8, "variants must be 2-8", field="variants")
    seed = op.get("seed", 0)
    strength = op.get("strength", "subtle")
    require(strength in BOIL_STRENGTHS, f"strength must be {', '.join(BOIL_STRENGTHS)}", field="strength")
    frames = max(1, math.ceil(length * fps / 1000 - 1e-9))
    hold = 1000 / fps
    settings = project.state["timeline"]
    closes = settings.get("loop_mode") == "seamless" and start + length == settings["duration"]
    if closes:
        # The drawing after the last one is the first again, so the cycle closes the loop: a whole number
        # of cycles, each drawing held for the same time, with the first drawing keyed again at the end.
        frames = max(1, round(length * fps / 1000 / variants)) * variants
        hold = length / frames
        if abs(1000 / hold - fps) > 0.01:
            from .timeline import _note
            _note(project, f"line-boil holds each drawing {hold:.0f} ms ({1000 / hold:.2f} redraws per second, not {fps:g}) so "
                  f"{frames // variants} whole cycle(s) of {variants} drawings close the {length} ms loop")
    require(frames * variants * len(targets) <= 8192, "line-boil would write too many keys; shorten duration or lower "
            "fps or variants", "resource_limit", field="fps")
    namer = Namer(project)
    for layer in targets:
        require(layer["type"] in ("shape", "group"), f"line-boil redraws vector layers; {layer['name']!r} is a "
                f"{layer['type']} layer", field="targets")
        copies = [layer["id"]]
        for k in range(1, variants):
            apply(project, {"type": "duplicate", "target": layer["id"], "name": namer(f"{layer['name']}-boil-{k + 1}")})
            copies.append(project.state["active_layer"])
        for k, ident in enumerate(copies):
            apply(project, {"type": "irregular", "target": ident, "seed": seed + k, "strength": strength,
                            "only": ["wobble", "jitter", "width"]})
        apply(project, {"type": "group", "name": namer(f"{layer['name']}-boil"), "targets": copies})
        for k, ident in enumerate(copies):
            for j in range(frames + closes):
                execute_timeline(project, {"type": "keyframe", "target": ident, "property": "visible",
                                           "time": start + round(j * hold), "value": j % variants == k,
                                           "easing": "hold", "extend": op.get("extend", True)})


def execute(project, op):
    from .timeline import execute_timeline, _timeline, parse_time, static_value, project_at, _snapshot
    if op["type"] == "keyframes":
        keys = (sampled_keys(project, op["sample"]) if "sample" in op else []) + list(op.get("keys", []))
        require(len(keys) <= 8192, "keyframes writes at most 8192 keys", "resource_limit", field="sample")
        for key in keys:
            execute_timeline(project, {"type": "keyframe", "target": op.get("target"), "property": op["property"], "extend": op.get("extend", True), **key})
        return
    settings = _timeline(project)
    start = parse_time(op.get("start", 0), settings["duration"], settings.get("markers"))
    # Spin, attach, wiggle and line boil fill the rest of the timeline by default: one operation, one loop.
    rest = op.get("recipe") in FILL_RECIPES
    length = parse_time(op.get("duration", settings["duration"] - start if rest else 1000), settings["duration"], settings.get("markers"))
    require(length >= 10, "Motion duration must be at least 10 ms")
    recipe = op["recipe"]
    require(recipe in RECIPES, "Unknown motion recipe")
    targets = [project.layer(ref) for ref in op.get("targets", [op.get("target")])]
    if op.get("children"):
        roots = {layer["id"] for layer in targets}
        targets = [layer for layer in project.state["layers"] if layer.get("parent") in roots]
    require(targets, "Motion needs at least one target")
    stagger = finite(op.get("stagger", 0), "stagger", 0, 600000)
    if recipe == "line-boil":
        line_boil(project, op, targets, start, length)
        return
    before = {layer["id"]: _snapshot(settings, layer["id"]) for layer in targets}
    if recipe == "spin":
        turns = finite(op.get("turns", 1), "turns", -1000, 1000)
        symmetry = op.get("symmetry", 1)
        require(isinstance(symmetry, int) and not isinstance(symmetry, bool) and 1 <= symmetry <= 1000, "symmetry must be a whole number 1-1000", field="symmetry")
        if turns != int(turns):
            from .timeline import _note
            _note(project, f"spin turns {turns:g} is not a whole number, so the loop jumps at the seam; use a whole number of turns")
        sweep = 360 * turns / symmetry
        for index, layer in enumerate(targets):
            offset = start + round(stagger * index)
            base = static_value(project, layer["id"], "rotation")
            for time, value in ((offset, base), (offset + length, base + sweep)):
                execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": "rotation", "time": time, "value": value,
                                           "easing": op.get("easing", "linear"), "extend": op.get("extend", True)})
            if symmetry > 1:
                next(t for t in settings["tracks"] if t["target"] == layer["id"] and t["property"] == "rotation")["symmetry"] = symmetry
        _close_motion(project, settings, op, targets, before)
        return
    if recipe == "attach":
        ref = op.get("follow", op.get("to"))
        require(isinstance(ref, str), "attach needs follow (or to): the layer to ride on", field="follow")
        follow = project.layer(ref)["id"]
        require("samples" not in op or isinstance(op["samples"], int) and 2 <= op["samples"] <= 512,
                "Motion samples must be 2–512", field="samples")
        from .group_bake import attach
        for index, layer in enumerate(targets):
            attach(project, op, layer, follow, start + round(stagger * index), length)
        _close_motion(project, settings, op, targets, before)
        return
    samples = op.get("samples", min(120, max(16, math.ceil(length / 1000 * settings["fps"]))))
    require(isinstance(samples, int) and 2 <= samples <= 512, "Motion samples must be 2–512")
    amount = finite(op.get("amount", 12), "amount", -100000, 100000)
    period = finite(op.get("period", 1000), "period", 10, 600000)
    frequency = finite(op.get("frequency", 3), "frequency", 0.01, 60)
    if (recipe == "wiggle" and settings.get("loop_mode") == "seamless" and not stagger
            and start + length == settings["duration"]):
        # A wiggle that runs to the loop end closes only after whole cycles.
        cycles = max(1, round(frequency * length / 1000))
        if abs(cycles * 1000 / length - frequency) > 1e-9:
            from .timeline import _note
            _note(project, f"wiggle frequency {frequency:g} -> {cycles * 1000 / length:g} per second, so {cycles} whole "
                  f"cycle(s) close the {length} ms loop")
            frequency = cycles * 1000 / length
    damping = finite(op.get("damping", 6), "damping", 0.01, 100)
    phase = finite(op.get("phase", 0), "phase", -10000, 10000)
    follow = project.layer(op["follow"])["id"] if "follow" in op else None
    require(recipe not in ("look-at", "overlap") or follow, f"{recipe} needs follow")
    points = op.get("points", [])
    require(recipe != "follow-path" or len(points) >= 2, "follow-path needs at least two points")
    if points:
        for point in points:
            require(len(point) == 2, "Path points are [x,y]")
            for v in point:
                finite(v, "path coordinate", -1e6, 1e6)
        distances = [0.0]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + math.dist(a, b))
        require(distances[-1] > 0, "Path must have nonzero length")
    # Sample the unmodified source once; generated target keys cannot feed back into following.
    from copy import copy, deepcopy
    original = copy(project)
    original.state = deepcopy(project.state)
    total_keys = len(targets) * (samples + 1) * 3
    require(total_keys <= 8192, "Motion would generate too many keys; reduce samples or targets", "resource_limit")
    for index, layer in enumerate(targets):
        offset = start + round(stagger * index)
        prop = op.get("property", "rotation" if recipe in ("wiggle", "look-at") else "translate-x")
        base = static_value(project, layer["id"], prop) if recipe in ("spring", "wiggle") else 0
        steps = [(i / samples, None) for i in range(samples + 1)]
        if recipe == "bounce":
            # A key on each contact, moved to the nearest frame, so the ball is seen touching down.
            frame = 1000 / settings["fps"]
            for contact in bounce_contacts(abs(amount), finite(op.get("gravity", 980), "gravity", 0.01, 1e6),
                                           finite(op.get("restitution", 0.65), "restitution", 0, 0.99), length / 1000):
                snapped = round((offset + contact * 1000) / frame) * frame - offset
                if 0 <= snapped <= length:
                    steps.append((snapped / length, {"translate-y": 0.0}))
        for u, forced in steps:
            t = length * u / 1000
            angle = math.tau * (t * 1000 / period + phase)
            values = {}
            if recipe == "follow-path":
                from .timeline import easing_function
                distance = distances[-1] * easing_function(op.get("easing", "ease-in-out"))(u)
                segment = next((j for j in range(1, len(distances)) if distances[j] >= distance), len(distances) - 1)
                a, b = points[segment - 1:segment + 1]
                span = distances[segment] - distances[segment - 1]
                p = (distance - distances[segment - 1]) / span if span else 0
                values = {"x": a[0] + (b[0] - a[0]) * p, "y": a[1] + (b[1] - a[1]) * p}
            elif recipe == "orbit":
                radius = finite(op.get("radius", abs(amount)), "radius", 0, 1e6)
                cx, cy = op.get("center", [layer["x"], layer["y"]])
                values = {"x": cx + radius * math.cos(angle), "y": cy + radius * math.sin(angle)}
            elif recipe == "bounce":
                gravity = finite(op.get("gravity", 980), "gravity", 0.01, 1e6)
                restitution = finite(op.get("restitution", 0.65), "restitution", 0, 0.99)
                height = abs(amount)
                fall = math.sqrt(2 * height / gravity)
                if t <= fall:
                    y = -height + 0.5 * gravity * t * t
                else:
                    remaining, velocity = t - fall, math.sqrt(2 * gravity * height) * restitution
                    for _ in range(128):
                        flight = 2 * velocity / gravity
                        if remaining <= flight or flight < 0.001:
                            break
                        remaining -= flight
                        velocity *= restitution
                    y = min(0, -velocity * remaining + 0.5 * gravity * remaining * remaining)
                values = forced or {"translate-y": y}
            elif recipe == "spring":
                target = finite(op.get("to", base + amount), "to", -1e6, 1e6)
                # Damped response has zero initial velocity. No forced discontinuity at the end.
                w = math.tau * frequency
                response = 1 - math.exp(-damping * t) * (math.cos(w * t) + damping / w * math.sin(w * t))
                values = {prop: base + (target - base) * response}
            elif recipe in ("shake", "wiggle"):
                envelope = math.sin(math.pi * u) if recipe == "shake" else 1
                values = {prop: base + amount * envelope * math.sin(math.tau * frequency * t + phase)}
            elif recipe == "breathing":
                values = {"scale-y": 1 + abs(amount) / 100 * (1 - math.cos(angle)) / 2}
            elif recipe == "blink":
                # Short closures, held by actual stepped keys, rather than a whole-cycle flap.
                values = {"scale-y": 0.08 if (t * 1000 / period + phase) % 1 >= 0.9 else 1}
            elif recipe == "hover":
                values = {"translate-y": -amount * math.sin(angle)}
            elif recipe in ("look-at", "overlap"):
                lag = abs(amount) if recipe == "overlap" else 0
                frame = project_at(original, max(0, offset + t * 1000 - lag))
                from .spatial import canvas_boxes
                from .checks import group_matrix
                from .render import resolve_layout
                import numpy as np
                world = canvas_boxes(frame)
                source = world[follow]
                target_box = world[layer["id"]]
                index_by_id = {item["id"]: item for item in frame.state["layers"]}
                parent = group_matrix(frame.layer(layer["id"]), index_by_id, resolve_layout(frame))
                if recipe == "look-at":
                    delta = [source[0] + source[2] / 2 - target_box[0] - target_box[2] / 2,
                             source[1] + source[3] / 2 - target_box[1] - target_box[3] / 2]
                    dx, dy = np.linalg.inv(parent[:2, :2]) @ delta
                    values = {"rotation": math.degrees(math.atan2(dy, dx))}
                else:
                    source0 = canvas_boxes(original)[follow]
                    delta = [source[0] + source[2] / 2 - source0[0] - source0[2] / 2,
                             source[1] + source[3] / 2 - source0[1] - source0[3] / 2]
                    dx, dy = np.linalg.inv(parent[:2, :2]) @ delta
                    values = {"translate-x": float(dx), "translate-y": float(dy)}
            for key, value in values.items():
                execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": key,
                    "time": offset + round(length * u), "value": value, "easing": "hold" if recipe == "blink" else "linear", "extend": op.get("extend", True)})
    _close_motion(project, settings, op, targets, before)


def bounce_contacts(height, gravity, restitution, seconds, limit=64):
    """Seconds at which the bounce recipe's ball touches the ground, up to ``seconds``."""
    if height <= 0:
        return []
    time, velocity, contacts = math.sqrt(2 * height / gravity), math.sqrt(2 * gravity * height), []
    while time <= seconds and len(contacts) < limit:
        contacts.append(time)
        velocity *= restitution
        flight = 2 * velocity / gravity
        if flight < 0.001:
            break
        time += flight
    return contacts


def _close_motion(project, timeline, op, targets, before):
    if op.get("close"):
        from .timeline import _close_touched
        for layer in targets:
            _close_touched(project, timeline, layer["id"], before.get(layer["id"], {}), {"close": True}, None, False)


SAMPLE_STEP = 100  # ms between sampled frames
MAX_SAMPLES = 48
TEXT_HIDDEN_SHARE = 0.5  # a looping text layer hidden for more of the loop than this is reported
SEAM_PREVIEW = 160  # px, longest side of the frames compared at the loop seam


def seam_value_findings(project, timeline=None):
    """Loop-seam findings from the track values: a track that ends elsewhere than it starts, or
    changes speed there."""
    from .kinetic import seam_findings as text_seams
    from .timeline import animated, is_looping, seam_findings

    timeline = timeline or project.state.get("timeline")
    if not animated(timeline) or not is_looping(timeline):
        return []
    result = []
    for layer in text_seams(project, timeline):
        result.append({"check": "motion", "severity": "warning", "layer": layer["id"], "code": "loop-seam",
                       "message": f"Loop seam: the text animation on {layer['name']!r} poses its letters differently at the loop end "
                                  "than at t=0, so the loop jumps when it restarts. Use text-animate mode: in-out (or a repeating "
                                  "wave whose period divides the timeline)."})
    for item in seam_findings(project, timeline):
        track = item["track"]
        name = f"{track['property']} on {layer_label(project, track['target'])}"
        if item["kind"] == "value":
            first, last = seam_value(track["property"], item["first"]), seam_value(track["property"], item["last"])
            result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "loop-seam",
                           "property": track["property"],
                           "message": f"Loop seam: {name} ends at {last} but starts at {first}, so the loop jumps when it restarts. "
                                      "Add a closing key (close: true) or end the track where it began."})
        else:
            result.append({"check": "motion", "severity": "info", "layer": track["target"], "code": "loop-seam-speed",
                           "property": track["property"],
                           "message": f"Loop seam: {name} matches at the seam but its speed changes from {compact_number(item['first'], 1)} "
                                      f"to {compact_number(item['last'], 1)} units/s there; ease the first and last segments "
                                      "(ease-in-out) or use constant speed to hide the kink."})
    return result


def layer_label(project, target):
    """How findings name a track's target: the layer's name in quotes, or ``the canvas``."""
    if target == "canvas":
        return "the canvas"
    layer = next((item for item in project.state["layers"] if item["id"] == target), None)
    return repr(layer["name"]) if layer else target


def seam_value(prop, value):
    """A track value as findings print it: numbers to two decimals, visibility as shown/hidden."""
    if isinstance(value, bool):
        return "shown" if value else "hidden" if prop == "visible" else str(value).lower()
    if isinstance(value, (int, float)):
        return compact_number(value, 2)
    return repr(value)


def time_findings(project):
    """What a viewer sees over time: a loop that jumps at its seam (track values, and the rendered
    last and first frames), text missing from the poster frame, and from frames sampled every
    SAMPLE_STEP ms: moving layers crossing text, text hidden for most of a loop, and parts that
    start on one centre and drift apart."""
    from .timeline import animated, poster_findings

    timeline = project.state.get("timeline")
    if not animated(timeline):
        return []
    result = seam_value_findings(project, timeline)
    for code, message, layer in poster_findings(project, 0):
        result.append({"check": "motion", "severity": "warning", "layer": layer, "code": code, "message": message})
    result += sampled_findings(project, timeline)
    if not any(item["code"] == "loop-seam" for item in result):
        result += rendered_seam_findings(project, timeline)
    return result


def _sample_times(timeline):
    duration = timeline["duration"]
    step = max(SAMPLE_STEP, duration / MAX_SAMPLES)
    count = max(2, min(MAX_SAMPLES, math.floor(duration / step) + 1))
    return [round(i * step) for i in range(count) if i * step < duration] or [0]


def _centre(box):
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _intersects(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def sampled_findings(project, timeline):
    """Findings from layer boxes (text by its glyph ink) at frames sampled across the timeline."""
    from .spatial import canvas_boxes
    from .timeline import is_looping, project_at, visible_content

    times = _sample_times(timeline)
    frames = []
    for time in times:
        frame = project_at(project, time)
        frames.append((time, canvas_boxes(frame, "ink"), visible_content(frame)))
    layers = project.state["layers"]
    by_id = {layer["id"]: layer for layer in layers}
    order = {layer["id"]: i for i, layer in enumerate(layers)}
    c = project.state["canvas"]

    def related(a, b):
        def chain(ident):
            while ident in by_id:
                yield ident
                ident = by_id[ident].get("parent")
        return a in set(chain(b)) or b in set(chain(a))

    def moved(ident):
        seen = [found.get(ident) for _, found, _ in frames]
        return any(box and seen[0] and max(abs(p - q) for p, q in zip(box, seen[0])) > 1 for box in seen)

    leaves = [layer for layer in layers if layer["type"] not in ("group", "adjustment")]
    movers = [layer for layer in leaves if moved(layer["id"])]
    moving = {layer["id"] for layer in movers}
    texts = [layer for layer in leaves if layer["type"] == "text"]
    result = []
    for text in texts:
        for mover in movers:
            if mover["id"] == text["id"] or related(mover["id"], text["id"]) or order[mover["id"]] < order[text["id"]]:
                continue
            hits = []
            for time, boxes, shown in frames:
                a, b = boxes.get(text["id"]), boxes.get(mover["id"])
                if a and b and text["id"] in shown and mover["id"] in shown and _intersects(a, b):
                    if b[2] * b[3] < 0.9 * c["width"] * c["height"]:
                        hits.append(time)
            if hits:
                result.append({"check": "motion", "severity": "warning", "layer": mover["id"], "code": "moving-over-text",
                               "message": f"{mover['name']!r} moves over the text {text['name']!r} between {hits[0] / 1000:g}s and "
                                          f"{hits[-1] / 1000:g}s ({len(hits)} of {len(frames)} sampled frames); move its path, "
                                          "put it behind the text, or time it for when the text is hidden.",
                               "text": text["name"], "times": [hits[0], hits[-1]]})
    if is_looping(timeline):
        animated_text = {track["target"] for track in timeline["tracks"] if track["property"] == "text"}
        for text in texts:
            if text["id"] in animated_text:
                continue
            hidden = sum(1 for _, _, shown in frames if text["id"] not in shown)
            if 0 < hidden < len(frames) and hidden / len(frames) > TEXT_HIDDEN_SHARE:
                result.append({"check": "motion", "severity": "warning", "layer": text["id"], "code": "text-mostly-hidden",
                               "message": f"Text {text['name']!r} is hidden for {round(100 * hidden / len(frames))}% of the loop "
                                          f"({hidden} of {len(frames)} sampled frames), so most viewers catch it missing; "
                                          "hold it on screen longer."})
    first = frames[0][1]
    siblings = {}
    for layer in leaves:
        siblings.setdefault(layer.get("parent"), []).append(layer)
    for group in siblings.values():
        if len(group) > 64:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["id"] not in moving and b["id"] not in moving:
                    continue
                boxes_a, boxes_b = first.get(a["id"]), first.get(b["id"])
                if not boxes_a or not boxes_b:
                    continue
                if math.dist(_centre(boxes_a), _centre(boxes_b)) > 1:
                    continue
                limit = max(4.0, 0.05 * min(boxes_a[2], boxes_a[3], boxes_b[2], boxes_b[3]))
                worst = max(((math.dist(_centre(boxes[a["id"]]), _centre(boxes[b["id"]])), time)
                             for time, boxes, _ in frames if a["id"] in boxes and b["id"] in boxes), default=(0, 0))
                if worst[0] > limit:
                    result.append({"check": "motion", "severity": "warning", "layer": a["id"], "code": "parts-drift",
                                   "message": f"{a['name']!r} and {b['name']!r} share a centre at 0s but are {worst[0]:.0f} px apart "
                                              f"at {worst[1] / 1000:g}s; animate them together (group them and animate the group) "
                                              "or give them the same keys.",
                                   "other": b["name"], "time": worst[1]})
    return result


def rendered_seam_findings(project, timeline):
    """Compare the last and first frames at low resolution: a looping animation whose seam changes the
    picture far more than an ordinary frame step jumps when it restarts, whatever the cause
    (effects, particles, expressions) that the track values miss."""
    import numpy as np
    from .proxy import render_preview
    from .timeline import is_looping, project_at, sample_frame_times

    if not is_looping(timeline):
        return []
    last = dict(sample_frame_times(timeline))["last"]
    step = 1000 / timeline.get("fps", 30)
    if last < 2 * step:
        return []

    def picture(time):
        return np.asarray(render_preview(project_at(project, time), SEAM_PREVIEW, SEAM_PREVIEW).convert("RGBA"), dtype=float)

    first, end, before = picture(0), picture(last), picture(last - step)
    seam = float(np.mean(np.abs(first - end)))
    ordinary = float(np.mean(np.abs(end - before)))
    if seam > 2.0 and seam > 3 * ordinary + 1:
        return [{"check": "motion", "severity": "warning", "layer": None, "code": "loop-seam-render",
                 "message": f"Loop seam: the last frame differs from the first by {seam:.1f} (mean per channel, 0-255) against "
                            f"{ordinary:.1f} between ordinary frames, so the loop visibly jumps when it restarts. "
                            "End every animation where it began.", "seam_difference": round(seam, 2),
                 "frame_difference": round(ordinary, 2)}]
    return []


def _full_turns(track):
    """A rotation track that turns whole symmetry steps between its two keys: a spin, whose constant
    speed is the point."""
    keys = track["keys"]
    if track["property"] != "rotation" or len(keys) != 2:
        return False
    step = 360 / max(1, track.get("symmetry", 1))
    turns = abs(keys[1]["value"] - keys[0]["value"]) / step
    return turns >= 1 - 1e-6 and abs(turns - round(turns)) < 1e-6


def findings(project):
    """Heuristics only: constant speed can be intentional (camera travel/conveyors)."""
    result = []
    for track in project.state.get("timeline", {}).get("tracks", []):
        if track["property"] not in ("x", "y", "translate-x", "translate-y", "rotation"):
            continue
        keys = track["keys"]
        name = layer_label(project, track["target"])
        changed = [(a, b) for a, b in zip(keys, keys[1:]) if a["value"] != b["value"]]
        if len(keys) == 2 and changed and keys[0].get("easing", "linear") == "linear" and not _full_turns(track):
            result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "linear-motion",
                           "property": track["property"],
                           "message": f"Two-key linear {track['property']} on {name} starts and stops instantly; consider easing, "
                                      "anticipation and settling unless constant speed is intended."})
        velocities = [(b["value"] - a["value"]) * 1000 / (b["time"] - a["time"]) for a, b in zip(keys, keys[1:])]
        for i, (a, b) in enumerate(zip(velocities, velocities[1:])):
            dt = (keys[i + 2]["time"] - keys[i]["time"]) / 2000
            if dt and abs(b - a) / dt > 100000:
                result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "high-acceleration",
                               "property": track["property"],
                               "message": f"Abrupt acceleration of {track['property']} on {name} exceeds 100,000 units/s² at "
                                          f"{keys[i + 1]['time'] / 1000:g}s; inspect for a teleport or missing anticipation "
                                          "(impacts may be intentional)."})
                break
    return result + time_findings(project)
