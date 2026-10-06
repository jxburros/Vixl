"""Bounded, deterministic motion recipes compiled to ordinary editable timeline keys.

Coordinates and gravity use pixels and seconds; operation times use milliseconds.
"""
import math
from .errors import require
from .model import finite

TYPES = ("motion", "keyframes")
RECIPES = ("follow-path", "orbit", "bounce", "shake", "wiggle", "spring", "look-at", "overlap", "breathing", "blink", "hover", "spin",
           "line-boil")
SAMPLE_FUNCTIONS = ("sin", "cos", "triangle", "saw", "square", "noise")
BOIL_STRENGTHS = ("subtle", "natural", "rough")


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N, B
    from .timeline import easing_schema
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    time = {"type": ["number", "string"]}
    add("motion", {"recipe": {"enum": list(RECIPES)}, "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": 256},
        "start": time, "duration": time, "period": N, "amount": N, "frequency": N, "damping": N,
        "gravity": N, "restitution": N, "radius": N, "center": point, "points": {"type": "array", "items": point, "minItems": 2, "maxItems": 256},
        "to": N, "property": S, "follow": S, "stagger": N, "children": B, "samples": {"type": "integer", "minimum": 2, "maximum": 512},
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
            for j in range(frames):
                execute_timeline(project, {"type": "keyframe", "target": ident, "property": "visible",
                                           "time": start + round(j * 1000 / fps), "value": j % variants == k,
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
    # A spin fills the rest of the timeline by default: one operation, one seamless loop.
    length = parse_time(op.get("duration", settings["duration"] - start if op.get("recipe") == "spin" else 1000), settings["duration"], settings.get("markers"))
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
    samples = op.get("samples", min(120, max(16, math.ceil(length / 1000 * settings["fps"]))))
    require(isinstance(samples, int) and 2 <= samples <= 512, "Motion samples must be 2–512")
    amount = finite(op.get("amount", 12), "amount", -100000, 100000)
    period = finite(op.get("period", 1000), "period", 10, 600000)
    frequency = finite(op.get("frequency", 3), "frequency", 0.01, 60)
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
        for i in range(samples + 1):
            u, t = i / samples, length * i / samples / 1000
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
                values = {"translate-y": y}
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


def _close_motion(project, timeline, op, targets, before):
    if op.get("close"):
        from .timeline import _close_touched
        for layer in targets:
            _close_touched(project, timeline, layer["id"], before.get(layer["id"], {}), {"close": True}, None, False)


def time_findings(project):
    """What a viewer sees over time, from the frames the shared sampler picks (poster, middle, last):
    a loop that jumps at its seam, and text missing from the poster frame."""
    from .timeline import is_looping, poster_findings, seam_findings

    timeline = project.state.get("timeline")
    if not timeline or not timeline.get("tracks"):
        return []
    result = []
    if is_looping(timeline):
        for item in seam_findings(project, timeline):
            track = item["track"]
            name = f"{track['property']} on {track['target']}"
            if item["kind"] == "value":
                result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "loop-seam",
                               "message": f"Loop seam: {name} ends at {item['last']!r} but starts at {item['first']!r}, so the loop jumps when it restarts. "
                                          "Add a closing key (close: true) or end the track where it began."})
            else:
                result.append({"check": "motion", "severity": "info", "layer": track["target"], "code": "loop-seam-speed",
                               "message": f"Loop seam: {name} matches at the seam but its speed changes from {item['first']} to {item['last']} units/s there; "
                                          "ease the first and last segments (ease-in-out) or use constant speed to hide the kink."})
    for code, message, layer in poster_findings(project, 0):
        result.append({"check": "motion", "severity": "warning", "layer": layer, "code": code, "message": message})
    return result


def findings(project):
    """Heuristics only: constant speed can be intentional (camera travel/conveyors)."""
    result = []
    for track in project.state.get("timeline", {}).get("tracks", []):
        if track["property"] not in ("x", "y", "translate-x", "translate-y", "rotation"):
            continue
        keys = track["keys"]
        changed = [(a, b) for a, b in zip(keys, keys[1:]) if a["value"] != b["value"]]
        if len(keys) == 2 and changed and keys[0].get("easing", "linear") == "linear":
            result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "linear-motion", "message": "Two-key linear movement starts and stops instantly; consider easing, anticipation and settling unless constant speed is intended."})
        velocities = [(b["value"] - a["value"]) * 1000 / (b["time"] - a["time"]) for a, b in zip(keys, keys[1:])]
        for i, (a, b) in enumerate(zip(velocities, velocities[1:])):
            dt = (keys[i + 2]["time"] - keys[i]["time"]) / 2000
            if dt and abs(b - a) / dt > 100000:
                result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "high-acceleration", "message": "Abrupt acceleration exceeds 100,000 units/s²; inspect for a teleport or missing anticipation (impacts may be intentional)."})
                break
    return result + time_findings(project)
