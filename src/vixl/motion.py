"""Bounded, deterministic motion recipes compiled to ordinary editable timeline keys.

Coordinates and gravity use pixels and seconds; operation times use milliseconds.
"""
import math
from .errors import require
from .geometry import compact_number
from .model import MAX_LAYERS, finite

TYPES = ("motion", "keyframes")
RECIPES = ("follow-path", "orbit", "bounce", "shake", "wiggle", "spring", "look-at", "overlap", "breathing", "blink", "hover", "spin",
           "attach", "line-boil", "scroll")
SAMPLE_FUNCTIONS = ("sin", "cos", "triangle", "saw", "square", "noise")
BOIL_STRENGTHS = ("subtle", "natural", "rough")
# Recipes whose duration defaults to the rest of the timeline rather than one second.
FILL_RECIPES = ("spin", "attach", "wiggle", "line-boil", "scroll")
WRAPPED_RECIPES = ("spin", "wiggle", "orbit", "breathing", "blink", "hover")  # periodic: stagger becomes a phase


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
        "wrap": {"type": "number", "exclusiveMinimum": 0, "description": "scroll: the distance after which the artwork repeats, "
                 "in px (default: the size of amount). amount must be a whole multiple of it."},
        "close": B,
        "fps": {"type": "number", "minimum": 1, "maximum": 30, "description": "line-boil: redraws per second, each "
                "held until the next (default 10; 8-12 reads as hand-drawn boil)."},
        "variants": {"type": "integer", "minimum": 2, "maximum": 8, "description": "line-boil: how many wobbled "
                     "drawings cycle (default 3); each is a copy of the layer, so this multiplies its layers."},
        "seed": {"type": "integer", "minimum": 0, "description": "line-boil: seed of the first drawing; the others use "
                 "the next seeds."},
        "strength": {"enum": list(BOIL_STRENGTHS), "description": "line-boil: wobble strength (default subtle)."}},
        ["recipe"])
    window = {"type": "object", "description": "A blend window: {start (ms), duration (ms), poses: [{at, value, easing}], "
              "easing}. Inside it the wave's keys are replaced: the track eases from the wave's value at start through "
              "each pose (at is 0-1 across the window) and back to the wave's value at the window end, so the wave "
              "continues exactly where it would have been.",
              "properties": {"start": {"type": "number", "minimum": 0}, "duration": {"type": "number", "exclusiveMinimum": 0},
                             "poses": {"type": "array", "minItems": 1, "maxItems": 64, "items": {
                                 "type": "object", "properties": {"at": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
                                                                  "value": N, "easing": easing_schema()},
                                 "required": ["at", "value"], "additionalProperties": False}},
                             "easing": easing_schema()},
              "required": ["start", "duration", "poses"], "additionalProperties": False}
    segment = {"type": "object",
               "properties": {"fn": {"enum": list(SAMPLE_FUNCTIONS)}, "period": {"type": "number", "exclusiveMinimum": 0},
                              "amplitude": N, "offset": N, "phase": N,
                              "step_ms": {"type": "number", "minimum": 1}, "samples": {"type": "integer", "minimum": 1,
                                                                                     "maximum": 8192},
                              "duration": {"type": "number", "exclusiveMinimum": 0}, "start": N,
                              "seed": {"type": "integer", "minimum": 0},
                              "blend": {"anyOf": [window, {"type": "array", "items": window, "minItems": 1, "maxItems": 16}],
                                        "description": "One blend window or a list of them (see docs/guides/motion/animation-authoring.md): "
                                        "a one-off pose sequence the wave hands over to and returns from."}},
               "required": ["fn"], "additionalProperties": False}
    sample = {**segment, "type": ["object", "array"], "items": segment, "minItems": 1, "maxItems": 32,
              "description": "Generate the keys from a periodic function instead of listing them: "
              "{fn: sin|cos|triangle|saw|square|noise, period (ms), amplitude, offset, phase (cycles), step_ms or "
              "samples, duration (ms), start (ms), seed (noise), blend}. value = offset + amplitude * fn(phase + t/period). "
              "blend: {start, duration, poses: [{at, value}], easing} replaces a window of the wave with eased poses and "
              "returns to the wave. A list of such objects is a piecewise sample: each segment starts where the one before "
              "ended (start defaults to that time) and is shifted so its first value equals the previous segment's last."}
    from .timeline import ADD_LAYER, MODE, SYMMETRY, WRAP
    add("keyframes", {"property": S, "keys": {"type": "array", "minItems": 1, "maxItems": 8192,
        "items": {"type": "object", "properties": {"time": time, "value": {}, "easing": easing_schema()}, "required": ["time", "value"], "additionalProperties": False}},
        "sample": sample, "extend": B, "mode": MODE, "additive": ADD_LAYER, "wrap": WRAP, "symmetry": SYMMETRY,
        "blend": {"anyOf": [window, {"type": "array", "items": window, "minItems": 1, "maxItems": 16}],
                  "description": "Hand the property's existing motion over to one-off poses and back: {start (ms), duration (ms), "
                  "poses: [{at, value, easing}], easing}, or a list of such windows. Inside the window the track's keys are replaced "
                  "by an ease from its value at start through each pose (at is 0-1 across the window) back to its value at the "
                  "window end, so a cycle written earlier (a gallop, a character-cycle joint) continues where it would have been. "
                  "With sample, put blend inside sample instead."}},
        ["property"], anyOf=[{"required": ["keys"]}, {"required": ["sample"]}, {"required": ["blend"]}])


def sampled_keys(project, spec):
    """Keys from a ``sample`` spec: a periodic function sampled every ``step_ms`` (or ``samples``
    times) over ``duration``. Square waves hold between keys; the rest are linear. A list of specs is a
    piecewise sample: each segment begins where the one before ended, shifted to the value reached there."""
    from .timeline import _timeline

    if not isinstance(spec, list):
        return _wave_keys(project, spec)
    require(1 <= len(spec) <= 32, "sample takes 1-32 segments", field="sample")
    keys, total = [], _timeline(project)["duration"]
    for index, part in enumerate(spec):
        last = index == len(spec) - 1
        begin = keys[-1]["time"] if keys else 0
        require(part.get("start", begin) >= begin, f"sample segment {index + 1} starts before the previous one ends "
                f"({begin:g} ms)", field="sample")
        require(last or "duration" in part, f"sample segment {index + 1} needs a duration (only the last runs to the "
                "timeline end)", field="sample")
        start = part.get("start", begin)
        piece = _wave_keys(project, {**part, "start": start, "duration": part.get("duration", max(1, total - start))},
                           keys[-1]["value"] if keys else None)
        if keys and piece[0]["time"] == keys[-1]["time"]:
            keys.pop()  # The joint is one key, with the easing of the segment leaving it.
        keys += piece
    return keys


def _wave_keys(project, spec, join=None):
    """One sample segment. ``join`` is the value the previous segment ended on: the whole segment is
    shifted so it starts there."""
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
    wave = None
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
    shift = 0 if join is None else join - (offset + amplitude * values[0])
    easing = "hold" if fn == "square" else "linear"

    def at(time):
        """The (shifted) wave's value at ``time``: exact for the functions, interpolated for noise."""
        if wave:
            return offset + shift + amplitude * wave(phase + (time - start) / period)
        position = min(count, max(0, (time - start) / duration * count))
        low = min(count - 1, int(position))
        return offset + shift + amplitude * (values[low] + (values[low + 1] - values[low]) * (position - low))

    keys = [{"time": round(t, 3), "value": round(offset + shift + amplitude * v, 6), "easing": easing} for t, v in zip(times, values)]
    reach = start
    for field, window in blend_windows(spec.get("blend", []), "sample.blend"):
        begin, finish = window_span(window, field)
        require(begin >= reach and finish <= start + duration + 1e-9, f"blend window {begin:g}-{finish:g} ms must lie inside "
                f"the sampled span ({start:g}-{start + duration:g} ms) and not overlap another window", field=field)
        reach = finish
        inside = window_keys(window, field, at(begin), at(finish), easing)
        keys = [key for key in keys if key["time"] < begin or key["time"] > finish] + inside
    keys.sort(key=lambda key: key["time"])
    return keys


def blend_windows(value, field):
    """``[(field, window)]`` for one blend window or a list of them, in time order."""
    windows = value if isinstance(value, list) else [value]
    for window in windows:
        require(isinstance(window, dict) and {"start", "duration", "poses"} <= set(window), "blend needs start, duration "
                "and poses", field=field)
    windows = sorted(windows, key=lambda window: window["start"])
    return [(f"{field}.{number}" if len(windows) > 1 else field, window) for number, window in enumerate(windows)]


def window_span(window, field):
    begin = finite(window["start"], "blend.start", 0, 600000)
    return begin, begin + finite(window["duration"], "blend.duration", 1, 600000)


def window_keys(window, field, before, after, resume=None):
    """The keys of a blend window: ``before`` (the motion's value where the window starts), each pose at
    its share of the window, and ``after`` (the motion's value where the window ends), eased from one to
    the next. ``resume`` is the easing of the motion leaving the window."""
    begin, finish = window_span(window, field)
    poses = window["poses"]
    require(isinstance(poses, list) and 1 <= len(poses) <= 64, "blend.poses lists 1-64 poses", field=field + ".poses")
    fractions = [finite(pose.get("at"), "blend pose at", 0, 1) for pose in poses]
    require(fractions == sorted(set(fractions)) and 0 < fractions[0] and fractions[-1] < 1,
            "blend poses need increasing at values strictly between 0 and 1", field=field + ".poses")
    ease = window.get("easing", "ease-in-out")
    keys = [{"time": round(begin, 3), "value": round(before, 6), "easing": ease}]
    for pose in poses:
        keys.append({"time": round(begin + (finish - begin) * pose["at"], 3),
                     "value": finite(pose["value"], "blend pose value", -1e6, 1e6), "easing": pose.get("easing", ease)})
    keys.append({"time": round(finish, 3), "value": round(after, 6), **({"easing": resume} if resume else {})})
    return keys


def blend_track(project, target, prop, blend, extend=True):
    """Hand a property's existing motion over to a one-off pose sequence and back (keyframes ``blend``).
    Inside each window the track's keys are replaced: it eases from its own value at the window start
    through the poses and back to its own value at the window end, so a cycle written earlier (a gallop)
    carries on where it would have been. A property without keys leaves from and returns to its current
    value. Additive layers on the track are not touched."""
    from .timeline import _property_kind, _sample_keys, _segment, _target_id, _timeline, _track, execute_timeline, static_value

    require(_property_kind(prop) == "number", f"blend eases numbers; {prop!r} is not numeric", field="blend")
    timeline = _timeline(project)
    ident = _target_id(project, target or project.state["active_layer"])
    reach = 0
    for field, window in blend_windows(blend, "blend"):
        begin, finish = (round(v) for v in window_span(window, field))
        require(begin >= reach, "blend windows must not overlap", field=field)
        reach = finish
        track = _track(timeline, ident, prop, create=False)
        resume = None
        if track and track["keys"]:
            keys = track["keys"]
            left, right, _ = _segment(keys, finish)
            resume = left.get("easing") if left is not right else None
            before, after = _sample_keys(project, prop, keys, begin), _sample_keys(project, prop, keys, finish)
            track["keys"] = [key for key in keys if not begin <= key["time"] <= finish]
        else:
            before = after = static_value(project, ident, prop)
        for key in window_keys(window, field, before, after, resume):
            execute_timeline(project, {"type": "keyframe", "target": ident, "property": prop, "extend": extend, **key})


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
    queue = getattr(project, "_warnings", None)
    seen = len(queue) if queue is not None else 0
    try:
        _execute(project, op)
    finally:
        if queue is not None:
            merge_growth(queue, seen)


GROWTH = "timeline duration changed "


def merge_growth(queue, seen):
    """One motion or keyframes operation writes many keys past the timeline end; say once how far the
    timeline grew (2400 -> 3000 ms) instead of once per key (2400 -> 2410, 2410 -> 2452 …)."""
    grown = [i for i in range(seen, len(queue)) if queue[i].startswith(GROWTH)]
    if len(grown) < 2:
        return
    first, last = queue[grown[0]], queue[grown[-1]]
    old = first[len(GROWTH):].split(" ", 1)[0]
    merged = GROWTH + old + " -> " + last[len(GROWTH):].split(" -> ", 1)[1]
    merged = merged.replace(f"to keep {last[len(GROWTH):].split(' ', 1)[0]} ms", f"to keep {old} ms")
    for i in reversed(grown):
        del queue[i]
    queue.insert(grown[0], merged)


def _execute(project, op):
    from .timeline import execute_timeline, _timeline, parse_time, static_value, project_at, _snapshot
    if op["type"] == "keyframes":
        if "blend" in op:
            require("sample" not in op and "keys" not in op and op.get("mode", "set") == "set",
                    "blend reshapes the property's existing keys: pass it alone (with sample, put blend inside sample)", field="blend")
            blend_track(project, op.get("target"), op["property"], op["blend"], op.get("extend", True))
            if "wrap" in op or "symmetry" in op:
                from .timeline import _mark_period, _target_id, _track
                _mark_period(_track(_timeline(project), _target_id(project, op.get("target") or project.state["active_layer"]),
                                    op["property"]), op)
            return
        keys = (sampled_keys(project, op["sample"]) if "sample" in op else []) + list(op.get("keys", []))
        require(len(keys) <= 8192, "keyframes writes at most 8192 keys", "resource_limit", field="sample")
        shared = {k: op[k] for k in ("mode", "additive", "wrap", "symmetry") if k in op}
        for key in keys:
            execute_timeline(project, {"type": "keyframe", "target": op.get("target"), "property": op["property"],
                                       "extend": op.get("extend", True), **shared, **key})
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
    # In a seamless loop a repeating motion's stagger is a phase offset: each target runs the same cycle a little
    # later, wrapped around the loop, instead of starting later and pushing keys past the end of the timeline.
    wrap = bool(stagger) and recipe in WRAPPED_RECIPES and settings.get("loop_mode") == "seamless"
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
            offset = start + (0 if wrap else round(stagger * index))
            base = static_value(project, layer["id"], "rotation") - (sweep * stagger * index / length if wrap else 0)
            for time, value in ((offset, base), (offset + length, base + sweep)):
                execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": "rotation", "time": time, "value": value,
                                           "easing": op.get("easing", "linear"), "extend": op.get("extend", True)})
            if symmetry > 1:
                next(t for t in settings["tracks"] if t["target"] == layer["id"] and t["property"] == "rotation")["symmetry"] = symmetry
        _close_motion(project, settings, op, targets, before)
        return
    if recipe == "scroll":
        # A strip whose artwork repeats every ``wrap`` px moves a whole number of repeats at constant speed:
        # the last frame flows into the first with nothing to close.
        prop = op.get("property", "translate-x")
        require("amount" in op, "scroll needs amount: the distance moved per loop in px (negative moves left or up)", field="amount")
        distance = finite(op["amount"], "amount", -1e6, 1e6)
        require(distance != 0, "scroll amount must not be 0", field="amount")
        repeat = finite(op.get("wrap", abs(distance)), "wrap", 1e-6, 1e6)
        whole = abs(distance) / repeat
        require(whole >= 1 - 1e-6 and abs(whole - round(whole)) < 1e-6, f"scroll amount {distance:g} is not a whole multiple of "
                f"wrap {repeat:g}, so the loop would jump at the seam", field="amount")
        for index, layer in enumerate(targets):
            offset = start + round(stagger * index)
            base = static_value(project, layer["id"], prop)
            for time, value in ((offset, base), (offset + length, base + distance)):
                execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": prop, "time": time, "value": value,
                                           "easing": "linear", "wrap": repeat, "extend": op.get("extend", True)})
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
    if (recipe == "wiggle" and settings.get("loop_mode") == "seamless" and (wrap or not stagger)
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
        offset = start + (0 if wrap else round(stagger * index))
        delay = stagger * index if wrap else 0
        # The cycle offset of this target: turns for period-based recipes, radians for wiggle and shake.
        turn = phase - delay / period
        radians = phase - math.tau * frequency * delay / 1000
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
            angle = math.tau * (t * 1000 / period + turn)
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
                values = {prop: base + amount * envelope * math.sin(math.tau * frequency * t + radians)}
            elif recipe == "breathing":
                values = {"scale-y": 1 + abs(amount) / 100 * (1 - math.cos(angle)) / 2}
            elif recipe == "blink":
                # Short closures, held by actual stepped keys, rather than a whole-cycle flap.
                values = {"scale-y": 0.08 if (t * 1000 / period + turn) % 1 >= 0.9 else 1}
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
    from .timeline import animated, is_looping, seam_findings, visible_content, project_at

    timeline = timeline or project.state.get("timeline")
    if not animated(timeline) or not is_looping(timeline):
        return []
    result = []
    endpoints = [project_at(project, time) for time in (0, timeline["duration"])]
    visible = set().union(*(visible_content(frame) for frame in endpoints))
    for frame in endpoints:
        by_id = {item["id"]: item for item in frame.state["layers"]}
        for ident in list(visible):
            item = by_id.get(ident, {})
            while item.get("parent") in by_id:
                visible.add(item["parent"])
                item = by_id[item["parent"]]
    for layer in text_seams(project, timeline):
        result.append({"check": "motion", "severity": "warning", "layer": layer["id"], "code": "loop-seam",
                       "message": f"Loop seam: the text animation on {layer['name']!r} poses its letters differently at the loop end "
                                  "than at t=0, so the loop jumps when it restarts. Use text-animate mode: in-out (or a repeating "
                                  "wave whose period divides the timeline)."})
    for item in seam_findings(project, timeline):
        track = item["track"]
        if track["target"] != "canvas" and track["target"] not in visible:
            continue
        name = f"{track['property']} on {layer_label(project, track['target'])}"
        if item["kind"] == "value":
            first, last = seam_value(track["property"], item["first"]), seam_value(track["property"], item["last"])
            hint = repeat_hint(project, track, timeline)
            result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "loop-seam",
                           "property": track["property"],
                           "message": f"Loop seam: {name} ends at {last} but starts at {first}"
                                      + (f". {hint} Otherwise the loop jumps when it restarts: add" if hint
                                         else ", so the loop jumps when it restarts. Add")
                                      + " a closing key (close: true) or end the track where it began."})
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


def constant_speed(track):
    """The change per loop of a track that moves at one constant speed from its first key to its last
    (linear segments on one line), or None."""
    keys = track["keys"]
    if len(keys) < 2 or track.get("add") or any(key.get("easing", "linear") != "linear" for key in keys[:-1]):
        return None
    if not all(isinstance(key["value"], (int, float)) and not isinstance(key["value"], bool) for key in keys):
        return None
    span = keys[-1]["time"] - keys[0]["time"]
    total = keys[-1]["value"] - keys[0]["value"]
    if not span or not total:
        return None
    for key in keys[1:-1]:
        expected = keys[0]["value"] + total * (key["time"] - keys[0]["time"]) / span
        if abs(key["value"] - expected) > 1e-6 * max(1, abs(total)):
            return None
    return total


def whole_repeats(track, timeline=None):
    """A constant-speed track that moves a whole number of its repeats: a spin by whole turns (or whole
    symmetry steps), or a scroll by whole ``wrap`` distances that runs the length of the loop. Its
    constant speed is the point, and its end flows into its start."""
    from .timeline import track_period

    total, period = constant_speed(track), track_period(track)
    if not total or not period:
        return False
    repeats = abs(total) / period
    if repeats < 1 - 1e-6 or abs(repeats - round(repeats)) > 1e-6:
        return False
    if track["property"] == "rotation" and not track.get("wrap"):
        return True
    keys = track["keys"]
    return timeline is None or (keys[0]["time"] <= 0 and keys[-1]["time"] >= timeline["duration"])


def child_repeat(project, track, distance):
    """The spacing at which a group's children repeat along the track's axis, when ``distance`` is a
    whole multiple of it: the group is a strip of repeated tiles, so moving it that far lands on itself."""
    axis = {"x": 0, "translate-x": 0, "y": 1, "translate-y": 1}.get(track["property"])
    layers = project.state["layers"]
    group = next((layer for layer in layers if layer["id"] == track["target"]), None)
    if axis is None or not group or group["type"] != "group":
        return None
    kinds = {}
    for child in layers:
        if child.get("parent") == group["id"]:
            box = (child["x"], child["y"], child["width"], child["height"])
            kinds.setdefault((child["type"], round(box[2], 2), round(box[3], 2), round(box[1 - axis], 2)), []).append(box[axis])
    found = None
    for positions in kinds.values():
        positions.sort()
        gaps = [b - a for a, b in zip(positions, positions[1:])]
        if not gaps or gaps[0] <= 0 or any(abs(gap - gaps[0]) > 0.01 for gap in gaps):
            continue
        whole = abs(distance) / gaps[0]
        if whole >= 1 - 1e-6 and abs(whole - round(whole)) < 1e-6:
            found = gaps[0] if found is None else min(found, gaps[0])
    return found


def repeat_hint(project, track, timeline):
    """What to say about a constant-speed track that ends away from its start: closing it would snap it
    back, while a strip of repeated artwork or a symmetric shape needs only its period marked."""
    total = constant_speed(track)
    keys = track["keys"]
    if not total or keys[0]["time"] > 0 or keys[-1]["time"] < timeline["duration"]:
        return ""
    distance = compact_number(abs(total), 2)
    if track["property"] == "rotation":
        steps = 360 / abs(total)
        if steps >= 2 and abs(steps - round(steps)) < 1e-6:
            return (f"If the shape has {round(steps)}-fold symmetry (it looks the same every {distance} degrees), mark the track "
                    f"with symmetry: {round(steps)} (keyframes, keyframe or animate) and the loop is seamless.")
        return ""
    if track["property"] not in ("x", "y", "translate-x", "translate-y"):
        return ""
    repeat = child_repeat(project, track, total)
    if repeat:
        return (f"Its children repeat every {compact_number(repeat, 2)} px, so the move is a whole repeat: mark the track "
                f"with wrap: {compact_number(repeat, 2)} (keyframes, keyframe or animate) and the loop is seamless.")
    return (f"If the artwork repeats every {distance} px (a seamless scroll), mark the track with wrap: {distance} "
            "(keyframes, keyframe or animate) and the loop is seamless; closing it would snap it back.")


def findings(project):
    """Heuristics only: constant speed can be intentional (camera travel/conveyors)."""
    from .timeline import summed_keys

    result = []
    timeline = project.state.get("timeline", {})
    for track in timeline.get("tracks", []):
        if track["property"] not in ("x", "y", "translate-x", "translate-y", "rotation"):
            continue
        keys = summed_keys(project, track)
        name = layer_label(project, track["target"])
        changed = [(a, b) for a, b in zip(keys, keys[1:]) if a["value"] != b["value"]]
        if (len(keys) == 2 and changed and not track.get("add") and keys[0].get("easing", "linear") == "linear"
                and not whole_repeats(track, timeline)):
            result.append({"check": "motion", "severity": "warning", "layer": track["target"], "code": "linear-motion",
                           "property": track["property"],
                           "message": f"Two-key linear {track['property']} on {name} starts and stops instantly; consider easing, "
                                      "anticipation and settling unless constant speed is intended (a seamless scroll or "
                                      "spin: mark the track with wrap or symmetry)."})
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
