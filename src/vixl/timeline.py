"""Keyframed animation timelines: tracks of layer properties over time, with easing.

A timeline animates ordinary document layers. Each track targets one layer property (``x``,
``opacity``, ``scale``, ``color``, ``text`` …) and holds keys ``{time, value, easing}``; the
easing on a key shapes the segment that starts at that key. Rendering a time copies the
document, applies interpolated values and renders it normally, so every layer type, effect
and style animates. Exports stream frames to GIF, APNG, animated WebP, sprite sheets, PNG
sequences, or MP4/WebM when ffmpeg is installed.
"""

import bisect
from copy import copy, deepcopy
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image

from .errors import VixlError, require
from .model import finite

TIMELINE_TYPES = ("timeline-set", "keyframe", "keyframe-remove", "animate", "animate-preset", "marker")
NUMERIC = ("x", "y", "translate-x", "translate-y", "opacity", "rotation", "scale", "scale-x", "scale-y", "width", "height", "size", "spacing",
           "trim_start", "trim_end")
COLORS = ("color", "fill", "start", "end", "stroke_color", "stroke", "background")
STEPPED = ("text", "visible")
MIRRORING = ("scale", "scale-x", "scale-y")
TRIM = ("trim_start", "trim_end")  # Stroke trim, percent of a shape's outline (trim.py).
PROPERTY_ALIASES = {"trim-start": "trim_start", "trim-end": "trim_end"}
MAX_DURATION = 600_000
MAX_FRAMES = 3600
# MP4/WebM stream one frame at a time into ffmpeg, so only the 10-minute duration bounds them.
MAX_STREAMED_FRAMES = MAX_DURATION * 60 // 1000
STREAMED = ("mp4", "webm")
MAX_TRACKS = 1024
MAX_KEYS = 8192

NAMED_BEZIER = {
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
    "ease-in-sine": (0.12, 0, 0.39, 0),
    "ease-out-sine": (0.61, 1, 0.88, 1),
    "ease-in-out-sine": (0.37, 0, 0.63, 1),
    "ease-in-quad": (0.11, 0, 0.5, 0),
    "ease-out-quad": (0.5, 1, 0.89, 1),
    "ease-in-out-quad": (0.45, 0, 0.55, 1),
    "ease-in-cubic": (0.32, 0, 0.67, 0),
    "ease-out-cubic": (0.33, 1, 0.68, 1),
    "ease-in-out-cubic": (0.65, 0, 0.35, 1),
    "ease-in-quart": (0.5, 0, 0.75, 0),
    "ease-out-quart": (0.25, 1, 0.5, 1),
    "ease-in-out-quart": (0.76, 0, 0.24, 1),
    "ease-in-expo": (0.7, 0, 0.84, 0),
    "ease-out-expo": (0.16, 1, 0.3, 1),
    "ease-in-out-expo": (0.87, 0, 0.13, 1),
    "ease-in-back": (0.36, 0, 0.66, -0.56),
    "ease-out-back": (0.34, 1.56, 0.64, 1),
    "ease-in-out-back": (0.68, -0.6, 0.32, 1.6),
}
EASINGS = ("linear", "hold", *NAMED_BEZIER, "bounce-out", "bounce-in", "elastic-out", "spring", "cubic-bezier(x1,y1,x2,y2)", "steps(n)")
PRESETS = (
    "fade-in",
    "fade-out",
    "slide-in-left",
    "slide-in-right",
    "slide-in-up",
    "slide-in-down",
    "slide-out-left",
    "slide-out-right",
    "slide-out-up",
    "slide-out-down",
    "pop-in",
    "pop-out",
    "zoom-in",
    "zoom-out",
    "spin",
    "pulse",
    "shake",
    "bounce",
    "float",
    "blink",
    "typewriter",
    "color-shift",
    "draw-on",
    "draw-off",
)


def _bezier(x1, y1, x2, y2):
    def sample(a, b, t):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t * t + t**3

    def ease(progress):
        low, high = 0.0, 1.0
        for _ in range(32):
            middle = (low + high) / 2
            if sample(x1, x2, middle) < progress:
                low = middle
            else:
                high = middle
        return sample(y1, y2, (low + high) / 2)

    return ease


def _bounce_out(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def easing_function(name):
    """Map an easing name to f(progress 0–1) → eased progress (may overshoot for back/elastic)."""
    require(isinstance(name, str), "Easing must be a string")
    key = name.strip().lower()
    if key == "linear":
        return lambda t: t
    if key in ("hold", "step", "step-end"):
        return lambda t: 0.0 if t < 1 else 1.0
    if key in NAMED_BEZIER:
        return _bezier(*NAMED_BEZIER[key])
    if key == "bounce-out":
        return _bounce_out
    if key == "bounce-in":
        return lambda t: 1 - _bounce_out(1 - t)
    if key == "elastic-out":
        return lambda t: 0 if t <= 0 else 1 if t >= 1 else 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if key == "spring":
        return lambda t: 1 - math.exp(-6 * t) * math.cos(12 * t) if t < 1 else 1.0
    match = re.fullmatch(r"cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)", key)
    if match:
        x1, y1, x2, y2 = map(float, match.groups())
        require(0 <= x1 <= 1 and 0 <= x2 <= 1, "cubic-bezier x values must be 0–1")
        require(all(abs(v) <= 10 for v in (y1, y2)), "cubic-bezier y values must be within ±10")
        return _bezier(x1, y1, x2, y2)
    match = re.fullmatch(r"steps\(\s*(\d+)\s*\)", key)
    if match:
        count = int(match[1])
        require(1 <= count <= 1000, "steps() needs 1–1000 steps")
        return lambda t: min(math.floor(t * count) / count, 1.0) if t < 1 else 1.0
    import difflib

    close = difflib.get_close_matches(key, [*NAMED_BEZIER, "linear", "hold", "bounce-out", "elastic-out", "spring"], 3, 0.5)
    raise VixlError("invalid_easing", f"Unknown easing {name!r}" + (f"; did you mean {', '.join(close)}?" if close else ""), suggestions=close)


def parse_time(value, duration=None, markers=None):
    """Milliseconds from 1200, '1.2s', '1200ms', '50%' (of duration) or a marker name."""
    if isinstance(value, bool):
        raise VixlError("invalid_time", "Time must be a number or string")
    if isinstance(value, (int, float)):
        finite(value, "time", 0, MAX_DURATION)
        return int(round(value))
    require(isinstance(value, str), "Time must be milliseconds or a string such as '1.5s'")
    text = value.strip().lower()
    if markers and value in markers:
        return markers[value]
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(ms|s|%)?", text)
    require(match, f"Invalid time {value!r}; use ms, '1.5s', '500ms', '50%' or a marker name", "invalid_time")
    number, unit = float(match[1]), match[2] or "ms"
    if unit == "%":
        require(duration, "Percent times need a timeline duration")
        number = duration * number / 100
    elif unit == "s":
        number *= 1000
    finite(number, "time", 0, MAX_DURATION)
    return int(round(number))


def default_timeline():
    return {"duration": 3000, "fps": 30, "loop": 0, "tracks": [], "markers": {}}


def _timeline(project):
    return project.state.setdefault("timeline", default_timeline())


def _property_kind(name):
    if name in NUMERIC or name.startswith("effect:"):
        return "number"
    if name in COLORS:
        return "color"
    if name in STEPPED:
        return "step"
    raise VixlError(
        "invalid_property",
        f"Cannot animate {name!r}; use {', '.join(NUMERIC + COLORS + STEPPED)} or effect:EFFECT_ID",
        field="property",
    )


def _check_value(project, prop, value):
    kind = _property_kind(prop)
    if kind == "number":
        finite(value, prop, -1e6, 1e6)
        if prop == "opacity":
            finite(value, "opacity", 0, 1)
        if prop in ("width", "height", "size"):
            finite(value, prop, 0, 1e5)
        if prop in MIRRORING:
            finite(value, prop, -1e5, 1e5)  # A negative scale mirrors the layer on that axis.
        if prop in TRIM:
            finite(value, prop, 0, 100)
    elif kind == "color":
        from .design import resolve_color
        from .render import color

        require(isinstance(value, str), f"{prop} keyframes need a color string")
        color(resolve_color(value, project.state))
    elif prop == "text":
        require(isinstance(value, str) and len(value) <= 100000, "text keyframes need a string")
    else:
        require(isinstance(value, bool), "visible keyframes need true or false")


def _check_mirror(layer, prop, value):
    """Negative scale mirrors a layer; PDF form fields are upright rectangles and cannot flip."""
    if prop in MIRRORING and isinstance(value, (int, float)) and value < 0:
        require(layer["type"] != "field", f"{prop} cannot be negative on field {layer['name']!r}: PDF form fields cannot be mirrored",
                field="value")


def _track(timeline, target, prop, create=True):
    for track in timeline["tracks"]:
        if track["target"] == target and track["property"] == prop:
            return track
    if not create:
        return None
    require(len(timeline["tracks"]) < MAX_TRACKS, "Timeline track limit reached", "resource_limit")
    track = {"target": target, "property": prop, "keys": []}
    timeline["tracks"].append(track)
    return track


def _set_key(track, time, value, easing, written=None):
    keys = track["keys"]
    keys[:] = [k for k in keys if k["time"] != time]
    key = {"time": time, "value": deepcopy(value)}
    if easing and easing != "linear":
        easing_function(easing)
        key["easing"] = easing
    keys.append(key)
    keys.sort(key=lambda k: k["time"])
    require(len(keys) <= MAX_KEYS, "Track keyframe limit reached", "resource_limit")
    if written is not None:
        written.append(time)


def _note(project, message):
    """Tell the caller about something an operation did that was not asked for. ``Project.apply``
    returns these as ``warnings``; direct callers without a collector skip them."""
    notices = getattr(project, "notices", None)
    if notices is not None:
        notices.append(message)


def _target_id(project, target):
    if target == "canvas":
        return "canvas"
    return project.layer(target)["id"]


def static_value(project, target, prop):
    """The document's current value of an animatable property (before animation)."""
    if target == "canvas":
        require(prop == "background", "The canvas animates only its background")
        return project.state["canvas"]["background"]
    layer = project.layer(target)
    if prop.startswith("effect:"):
        effect = _effect(layer, prop[7:])
        return effect.get("amount", 0)
    if prop in TRIM:
        from .trim import require_shape

        require_shape(layer, prop)
        return layer.get(prop, 0 if prop == "trim_start" else 100)
    if prop in ("scale", "scale-x", "scale-y"):
        return 1.0
    if prop in ("translate-x", "translate-y"):
        return 0.0
    if prop in ("x", "y"):
        from .render import resolve_layout, pivot_delta

        if layer.get("pivot") is not None:
            # A pivoted layer's x/y is its unrotated box, which rotation does not move.
            if not layer["constraints"]:
                return layer[prop]
            bounds = resolve_layout(project)[layer["id"]]
            return bounds[0 if prop == "x" else 1] - pivot_delta(layer)[0 if prop == "x" else 1]
        return resolve_layout(project)[layer["id"]][0 if prop == "x" else 1]
    if prop == "fill" and "fill" not in layer and "color" in layer:
        prop = "color"
    require(prop in layer or prop == "spacing", f"Layer {layer['name']!r} has no {prop!r} to animate")
    return deepcopy(layer.get(prop, 4))


def _effect(layer, ref):
    if ref.isdigit():
        index = int(ref) - 1
        require(0 <= index < len(layer["effects"]), "Effect index out of range (starts at 1)")
        return layer["effects"][index]
    effect = next((e for e in layer["effects"] if e["id"] == ref or e["name"] == ref), None)
    require(effect is not None, f"Effect {ref!r} not found on {layer['name']!r}")
    return effect


def execute_timeline(project, op):
    if op.get("property") in PROPERTY_ALIASES:
        op = {**op, "property": PROPERTY_ALIASES[op["property"]]}
    timeline = _timeline(project)
    kind = op["type"]
    duration = timeline["duration"]
    markers = timeline.setdefault("markers", {})
    if kind == "timeline-set":
        if "duration" in op:
            timeline["duration"] = parse_time(op["duration"])
            require(10 <= timeline["duration"] <= MAX_DURATION, "Duration must be 10 ms – 10 minutes")
        if "fps" in op:
            fps = op["fps"]
            require(isinstance(fps, (int, float)) and 1 <= fps <= 60, "fps must be 1–60")
            timeline["fps"] = fps
        if "loop" in op:
            require(isinstance(op["loop"], int) and 0 <= op["loop"] <= 65535, "loop must be 0 (forever)–65535")
            timeline["loop"] = op["loop"]
        if op.get("clear"):
            timeline["tracks"] = []
            timeline["markers"] = {}
        past = sum(1 for t in timeline["tracks"] for k in t["keys"] if k["time"] > timeline["duration"])
        if "duration" in op and past:
            _note(project, f"{past} keyframe(s) now lie past the timeline end ({timeline['duration']} ms): they stay on "
                  "their tracks and shape the last frames, but their own moment is not played; keyframe-remove deletes them")
        return
    if kind == "marker":
        from .design import named

        name = named(op["name"])
        if op.get("delete"):
            markers.pop(name, None)
        else:
            markers[name] = parse_time(op["time"], duration, markers)
        return
    if kind == "keyframe-remove":
        target = _target_id(project, op.get("target") or project.state["active_layer"])
        kept = []
        for track in timeline["tracks"]:
            if track["target"] != target or ("property" in op and track["property"] != op["property"]):
                kept.append(track)
                continue
            if "time" in op:
                time = parse_time(op["time"], duration, markers)
                track["keys"] = [k for k in track["keys"] if k["time"] != time]
                if track["keys"]:
                    kept.append(track)
        timeline["tracks"] = kept
        return
    if "targets" in op:
        # One call, shared timing: the same keys land on every listed part.
        require(kind in ("keyframe", "animate", "animate-preset"), f"{kind} takes a single target")
        require("target" not in op, "Pass target or targets, not both")
        targets = op["targets"]
        require(isinstance(targets, list) and 1 <= len(targets) <= 256, "targets must list 1–256 layers")
        for target in targets:
            execute_timeline(project, {**{k: v for k, v in op.items() if k != "targets"}, "target": target})
        return
    target_ref = op.get("target") or project.state["active_layer"]
    require(target_ref, "Pass target (a layer or 'canvas')")
    target = _target_id(project, target_ref)
    written = []  # Times of the keys this operation sets.
    if kind == "keyframe":
        prop = op["property"]
        _check_value(project, prop, op["value"])
        static_value(project, target, prop)
        if target != "canvas":
            _check_mirror(project.layer(target), prop, op["value"])
        _set_key(_track(timeline, target, prop), parse_time(op["time"], duration, markers), op["value"], op.get("easing"), written)
    elif kind == "animate":
        prop = op["property"]
        start = parse_time(op.get("start", 0), duration, markers)
        if "end" in op:
            end = parse_time(op["end"], duration, markers)
        else:
            end = start + parse_time(op.get("duration", duration - start), duration, markers)
        require(end > start, "Animation end must be after its start")
        begin = op["from"] if "from" in op else _value_at(project, timeline, target, prop, start)
        _check_value(project, prop, begin)
        _check_value(project, prop, op["to"])
        if prop in MIRRORING and target != "canvas":
            _check_mirror(project.layer(target), prop, min(begin, op["to"]))
        track = _track(timeline, target, prop)
        _set_key(track, start, begin, op.get("easing", "ease-in-out"), written)
        _set_key(track, end, op["to"], None, written)
    else:
        _apply_preset(project, timeline, target, op, written)
    # A key past the end lengthens the timeline, and the result says so. Only the keys this
    # operation set count: a key left past the end by an earlier operation (or kept there with
    # extend: false) never stretches a duration that was set back since. Pass extend: false to
    # keep the duration and leave the key past the end, where it shapes the last frames.
    latest = max(written, default=0)
    if latest > timeline["duration"]:
        name = "the canvas" if target == "canvas" else repr(project.layer(target)["name"])
        if op.get("extend", True):
            old = timeline["duration"]
            timeline["duration"] = latest
            require(latest <= MAX_DURATION, "Timeline exceeds 10 minutes")
            _note(project, f"timeline duration changed {old} -> {latest} ms: a keyframe on {name} sits at {latest} ms, "
                  f"past the end. Pass extend: false to keep {old} ms, or timeline-set duration to choose the length")
        else:
            _note(project, f"a keyframe on {name} sits at {latest} ms, past the timeline end ({timeline['duration']} ms): "
                  "it shapes the last frames but its own moment is not played")


def _apply_preset(project, timeline, target, op, written):
    preset = op["preset"]
    require(preset in PRESETS, f"Unknown animation preset {preset!r}; use {', '.join(PRESETS)}")
    duration = timeline["duration"]
    markers = timeline.get("markers", {})
    start = parse_time(op.get("start", 0), duration, markers)
    length = parse_time(op.get("duration", 600), duration, markers)
    require(length >= 10, "Preset duration must be at least 10 ms")
    end = start + length
    easing = op.get("easing")
    layer = None if target == "canvas" else project.layer(target)
    require(layer is not None or preset == "color-shift", "Only color-shift applies to the canvas")
    c = project.state["canvas"]

    def keys(prop, values, ease):
        track = _track(timeline, target, prop)
        for i, value in enumerate(values):
            time = start + round(length * i / (len(values) - 1))
            _set_key(track, time, value, ease if i < len(values) - 1 else None, written)

    if preset in ("fade-in", "fade-out"):
        current = layer.get("opacity", 1)
        keys("opacity", [0.0, current] if preset == "fade-in" else [current, 0.0], easing or "ease-out")
    elif preset.startswith(("slide-in", "slide-out")):
        # slide-in-left enters from the left edge; slide-in-up rises from below (animate.css
        # convention). slide-out-left leaves through the left edge; slide-out-up through the top.
        direction = preset.rsplit("-", 1)[1]
        entering = preset.startswith("slide-in")
        from .render import resolve_layout

        bx, by, bw, bh = resolve_layout(project)[layer["id"]]
        offscreen = {
            "left": -(bx + bw),
            "right": c["width"] - bx,
            "up": (c["height"] - by) if entering else -(by + bh),
            "down": -(by + bh) if entering else (c["height"] - by),
        }[direction]
        if "distance" in op:
            finite(op["distance"], "distance", 0, 1e6)
            offscreen = math.copysign(op["distance"], offscreen)
        axis = "translate-x" if direction in ("left", "right") else "translate-y"
        values = [float(offscreen), 0.0] if entering else [0.0, float(offscreen)]
        keys(axis, values, easing or ("ease-out-cubic" if entering else "ease-in-cubic"))
        if op.get("fade", True):
            current = layer.get("opacity", 1)
            keys("opacity", [0.0, current] if entering else [current, 0.0], "ease-out" if entering else "ease-in")
    elif preset in ("pop-in", "pop-out"):
        values = [0.6, 1.0] if preset == "pop-in" else [1.0, 0.6]
        keys("scale", values, easing or ("ease-out-back" if preset == "pop-in" else "ease-in-back"))
        current = layer.get("opacity", 1)
        keys("opacity", [0.0, current] if preset == "pop-in" else [current, 0.0], "ease-out")
    elif preset in ("zoom-in", "zoom-out"):
        amount = op.get("amount", 1.15)
        finite(amount, "amount", 0.01, 100)
        keys("scale", [1.0, amount] if preset == "zoom-in" else [amount, 1.0], easing or "ease-in-out")
    elif preset == "spin":
        turns = op.get("amount", 1)
        finite(turns, "amount", -100, 100)
        base = layer.get("rotation", 0)
        keys("rotation", [base, base + 360 * turns], easing or "linear")
    elif preset == "pulse":
        amount = op.get("amount", 1.08)
        keys("scale", [1.0, amount, 1.0], easing or "ease-in-out-sine")
    elif preset == "shake":
        amount = op.get("amount", 12)
        keys("translate-x", [0.0, -amount, amount, -amount * 0.6, amount * 0.6, -amount * 0.3, 0.0], easing or "ease-in-out")
    elif preset == "bounce":
        height = op.get("amount", 60)
        track = _track(timeline, target, "translate-y")
        _set_key(track, start, -float(height), easing or "bounce-out", written)
        _set_key(track, end, 0.0, None, written)
    elif preset == "float":
        amount = op.get("amount", 10)
        keys("translate-y", [0.0, -float(amount), 0.0], easing or "ease-in-out-sine")
    elif preset == "blink":
        track = _track(timeline, target, "visible")
        count = max(1, int(op.get("amount", 3)))
        for i in range(count * 2 + 1):
            _set_key(track, start + round(length * i / (count * 2)), i % 2 == 0, None, written)
    elif preset in ("draw-on", "draw-off"):
        from .trim import require_shape

        require_shape(layer, preset)
        # Draw on: the stroke's end runs 0 -> 100%. Draw off: its start follows, erasing it the way it was drawn.
        keys("trim_end" if preset == "draw-on" else "trim_start", [0.0, 100.0], easing or "ease-in-out")
    elif preset == "typewriter":
        require(layer["type"] == "text", "typewriter animates a text layer")
        text = layer["text"]
        require(len(text) <= 2000, "typewriter supports at most 2000 characters")
        track = _track(timeline, target, "text")
        for i in range(len(text) + 1):
            _set_key(track, start + round(length * i / max(len(text), 1)), text[:i], None, written)
    else:
        require("to" in op, "color-shift needs a 'to' color")
        prop = "background" if target == "canvas" else next((k for k in ("fill", "color", "start") if k in layer), None)
        require(prop, "color-shift needs a layer with a fill or color")
        begin = project.state["canvas"]["background"] if target == "canvas" else layer[prop]
        _check_value(project, prop, op["to"])
        keys(prop, [begin, op["to"]], easing or "ease-in-out")


# ---------------------------------------------------------------------------------------------
# Sampling


def _segment(keys, time):
    if time <= keys[0]["time"]:
        return keys[0], keys[0], 0.0
    if time >= keys[-1]["time"]:
        return keys[-1], keys[-1], 0.0
    # Long tracks (a lyric video holds thousands of keys) are searched, not scanned.
    index = bisect.bisect_right(keys, time, key=lambda k: k["time"])
    left, right = keys[index - 1], keys[index]
    return left, right, (time - left["time"]) / (right["time"] - left["time"])


def sample_track(project, track, time):
    keys = track["keys"]
    left, right, progress = _segment(keys, time)
    if left is right:
        return deepcopy(left["value"])
    kind = _property_kind(track["property"])
    eased = easing_function(left.get("easing", "linear"))(progress)
    if kind == "step":
        return deepcopy(right["value"] if eased >= 1 else left["value"])
    if kind == "number":
        return left["value"] + (right["value"] - left["value"]) * eased
    from .colors import hex_of, mix
    from .design import resolve_color
    from .render import color

    a = tuple(v / 255 for v in color(resolve_color(left["value"], project.state)))
    b = tuple(v / 255 for v in color(resolve_color(right["value"], project.state)))
    return hex_of(mix(a, b, min(max(eased, 0.0), 1.0), "oklab"))


def _value_at(project, timeline, target, prop, time):
    track = _track(timeline, target, prop, create=False)
    if track and track["keys"]:
        return sample_track(project, track, time)
    return static_value(project, target, prop)


def project_at(project, time):
    """A render-only copy of the document with every track applied at ``time`` (ms)."""
    from .render import resolve_layout, text_metrics

    timeline = project.state.get("timeline")
    if not isinstance(time, (int, float)) or isinstance(time, bool):
        settings = timeline or default_timeline()
        time = parse_time(time, settings["duration"], settings.get("markers"))
    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    if not timeline or not timeline.get("tracks"):
        return candidate
    state = candidate.state
    layers = {layer["id"]: layer for layer in state["layers"]}
    geometry = {}
    for track in timeline["tracks"]:
        if not track["keys"]:
            continue
        value = sample_track(project, track, time)
        prop, target = track["property"], track["target"]
        if target == "canvas":
            state["canvas"]["background"] = value
            continue
        layer = layers.get(target)
        if layer is None:
            continue
        if prop in ("x", "y", "translate-x", "translate-y", "scale", "scale-x", "scale-y"):
            geometry.setdefault(target, {})[prop] = value
        elif prop.startswith("effect:"):
            _effect(layer, prop[7:])["amount"] = value
        elif prop in ("width", "height"):
            layer[prop] = max(1, int(round(value)))
            layer["auto_size"] = False
        elif prop == "size":
            layer["size"] = max(1, int(round(value)))
        elif prop == "fill" and "fill" not in layer and "color" in layer:
            layer["color"] = value
        elif prop == "visible":
            layer["visible"] = bool(value)
        elif prop == "opacity":
            layer["opacity"] = min(max(value, 0.0), 1.0)
        elif prop in TRIM:
            layer[prop] = min(max(value, 0.0), 100.0)  # Easings that overshoot stay on the outline.
        elif prop == "rotation":
            layer["rotation"] = value % 360
            geometry.setdefault(target, {})["rotation"] = value
        else:
            layer[prop] = value
    for layer in state["layers"]:
        if layer["type"] == "text" and layer.get("auto_size", True):
            layer["width"], layer["height"], _ = text_metrics(candidate, layer)
    if geometry:
        from .render import pivot_delta, rest_size, transformed_size

        bounds = resolve_layout(candidate)
        rest = {}
        spinning = [ident for ident, v in geometry.items() if "rotation" in v and layers[ident].get("pivot") is None]
        if spinning:
            # Bounds at the document's own rotation (other animated geometry applied) give the
            # center a rotating layer turns about.
            original = {layer["id"]: layer.get("rotation", 0) for layer in project.state["layers"]}
            frame = {ident: layers[ident]["rotation"] for ident in spinning}
            for ident in spinning:
                layers[ident]["rotation"] = original[ident]
            rest = resolve_layout(candidate)
            for ident in spinning:
                layers[ident]["rotation"] = frame[ident]
        for ident, values in geometry.items():
            layer = layers[ident]
            x, y, w, h = bounds[ident]
            sx = values.get("scale", 1) * values.get("scale-x", 1)
            sy = values.get("scale", 1) * values.get("scale-y", 1)
            # A negative scale mirrors the layer about its pivot (its center without one), on top
            # of any flip the document already has, so animating through zero swings it over.
            flip_x, flip_y = sx < 0, sy < 0
            sx, sy = abs(sx), abs(sy)
            resized = sx != 1 or sy != 1
            if round(layer["width"] * sx) < 1 or round(layer["height"] * sy) < 1:
                # Scaled to nothing (a wipe or pop that starts at 0): draw nothing this frame,
                # instead of the 1 px sliver the smallest box would leave.
                layer["opacity"] = 0
            layer["flip_x"] = bool(layer.get("flip_x")) != flip_x
            layer["flip_y"] = bool(layer.get("flip_y")) != flip_y
            if layer.get("pivot") is not None:
                # x/y place the unrotated box; rotation and scale keep the pivot point fixed.
                if layer.get("constraints"):
                    dx, dy = pivot_delta(layer)
                    x, y = x - dx, y - dy
                else:
                    x, y = layer["x"], layer["y"]
                x, y = values.get("x", x), values.get("y", y)
                if resized or flip_x or flip_y:
                    (rw, rh), (px, py) = rest_size(layer), layer["pivot"]
                    anchor = x + px * rw, y + py * rh
                    if resized:
                        layer.update(width=max(1, int(round(layer["width"] * sx))), height=max(1, int(round(layer["height"] * sy))), auto_size=False)
                    # The pivot is a point of the artwork, so mirroring moves it to the other side
                    # of the box while it stays fixed on the canvas.
                    px, py = (1 - px if flip_x else px), (1 - py if flip_y else py)
                    layer["pivot"] = [px, py]
                    rw, rh = rest_size(layer)
                    x, y = anchor[0] - px * rw, anchor[1] - py * rh
            else:
                # Scale and animated rotation keep the layer's center (the document pose's center
                # while rotating, so spins do not drift as the expanded bounds grow).
                if "rotation" in values and ident in rest:
                    rx, ry, rw, rh = rest[ident]
                    cx, cy = rx + rw / 2, ry + rh / 2
                else:
                    cx, cy = x + w / 2, y + h / 2
                if "x" in values:
                    cx = values["x"] + w / 2
                if "y" in values:
                    cy = values["y"] + h / 2
                if resized:
                    layer.update(width=max(1, int(round(layer["width"] * sx))), height=max(1, int(round(layer["height"] * sy))), auto_size=False)
                tw, th = transformed_size(layer)
                x, y = cx - tw / 2, cy - th / 2
            # Animated geometry freezes this layer's constraints for the frame; layers anchored
            # to it still follow, because they resolve against its new bounds.
            layer.update(
                x=x + values.get("translate-x", 0), y=y + values.get("translate-y", 0), constraints={}
            )
    candidate._cache = project._cache
    return candidate


def render_at(project, time, **options):
    from .render import render

    return render(project_at(project, time), **options)


def render_scaled(project, scale, sampling="smooth"):
    """Render at ``scale`` × canvas size. Smooth sampling re-renders a geometrically scaled copy so
    vectors, text and shapes stay crisp; raster content and unsupported features resample with
    LANCZOS, and nearest sampling enlarges the canvas-size render pixel by pixel."""
    from .proxy import scaled_project
    from .render import render

    c = project.state["canvas"]
    size = (max(1, round(c["width"] * scale)), max(1, round(c["height"] * scale)))
    project.limits.size(*size)
    proxy = scaled_project(project, scale) if scale != 1 and sampling == "smooth" else None
    image = render(proxy if proxy is not None else project)
    if image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST if sampling == "nearest" else Image.Resampling.LANCZOS)
    return image


def frame_times(project, fps=None, start=0, end=None, streamed=False):
    """Frame times from ``start`` to ``end``. Buffered formats (GIF, APNG, WebP, sheets, PNG
    sequences) hold at most 3,600 frames; ``streamed`` video is bounded only by its duration."""
    timeline = project.state.get("timeline") or default_timeline()
    fps = fps or timeline["fps"]
    require(isinstance(fps, (int, float)) and 1 <= fps <= 60, "fps must be 1–60")
    end = timeline["duration"] if end is None else end
    require(0 <= start < end <= MAX_DURATION, "Invalid frame range")
    count = max(1, math.ceil((end - start) * fps / 1000))
    limit = MAX_STREAMED_FRAMES if streamed else MAX_FRAMES
    require(count <= limit, f"Timeline exports at most {limit} frames"
            + ("; lower fps or duration" if streamed else "; lower fps or duration, or export mp4/webm, which have no frame cap"),
            "resource_limit")
    return [start + i * 1000 / fps for i in range(count)], fps


# ---------------------------------------------------------------------------------------------
# Validation and inspection


def validate_timeline(project, state):
    if "timeline" not in state:
        return
    timeline = state["timeline"]
    require(
        isinstance(timeline, dict) and set(timeline) <= {"duration", "fps", "loop", "tracks", "markers"},
        "Invalid timeline",
        "invalid_project",
    )
    duration = timeline.get("duration", 3000)
    require(isinstance(duration, int) and 10 <= duration <= MAX_DURATION, "Invalid timeline duration")
    fps = timeline.get("fps", 30)
    require(isinstance(fps, (int, float)) and not isinstance(fps, bool) and 1 <= fps <= 60, "Invalid timeline fps")
    require(isinstance(timeline.get("loop", 0), int) and 0 <= timeline.get("loop", 0) <= 65535, "Invalid timeline loop")
    markers = timeline.get("markers", {})
    require(isinstance(markers, dict), "Invalid timeline markers")
    from .design import named

    for name, time in markers.items():
        named(name)
        require(isinstance(time, int) and 0 <= time <= MAX_DURATION, "Invalid marker time")
    tracks = timeline.get("tracks", [])
    require(isinstance(tracks, list) and len(tracks) <= MAX_TRACKS, "Invalid timeline tracks")
    ids = {layer["id"]: layer for layer in state["layers"]}
    seen = set()
    candidate = copy(project)
    candidate.state = state
    for track in tracks:
        require(isinstance(track, dict) and set(track) == {"target", "property", "keys"}, "Invalid timeline track")
        target, prop = track["target"], track["property"]
        require(target == "canvas" or target in ids, "Timeline track targets a missing layer", "invalid_project")
        require((target, prop) not in seen, "Duplicate timeline track")
        seen.add((target, prop))
        _property_kind(prop)
        if prop.startswith("effect:"):
            _effect(ids[target], prop[7:])
        keys = track["keys"]
        require(isinstance(keys, list) and len(keys) <= MAX_KEYS, "Invalid keyframes")
        times = []
        for key in keys:
            require(isinstance(key, dict) and set(key) <= {"time", "value", "easing"} and {"time", "value"} <= set(key), "Invalid keyframe")
            require(isinstance(key["time"], int) and 0 <= key["time"] <= MAX_DURATION, "Invalid keyframe time")
            times.append(key["time"])
            _check_value(candidate, prop, key["value"])
            if target != "canvas":
                _check_mirror(ids[target], prop, key["value"])
            if "easing" in key:
                easing_function(key["easing"])
        require(times == sorted(set(times)), "Keyframes must have increasing, unique times")


def prune_targets(state, removed):
    timeline = state.get("timeline")
    if timeline:
        timeline["tracks"] = [t for t in timeline.get("tracks", []) if t["target"] not in removed]


def inspect_timeline(project):
    timeline = project.state.get("timeline") or default_timeline()
    names = {layer["id"]: layer["name"] for layer in project.state["layers"]}
    return {
        "duration": timeline["duration"],
        "fps": timeline["fps"],
        "frames": max(1, math.ceil(timeline["duration"] * timeline["fps"] / 1000)),
        "loop": timeline.get("loop", 0),
        "markers": timeline.get("markers", {}),
        "tracks": [
            {
                "target": track["target"],
                "layer": names.get(track["target"], track["target"]),
                "property": track["property"],
                "keys": [
                    {"time": k["time"], "value": k["value"] if not isinstance(k["value"], str) or len(k["value"]) <= 60 else k["value"][:57] + "...", **({"easing": k["easing"]} if "easing" in k else {})}
                    for k in track["keys"][:64]
                ],
                **({"truncated_keys": len(track["keys"])} if len(track["keys"]) > 64 else {}),
            }
            for track in timeline.get("tracks", [])
        ],
    }


# ---------------------------------------------------------------------------------------------
# Export

FORMATS = ("gif", "apng", "webp", "sheet", "frames", "mp4", "webm")


def cached(project):
    """A render copy of a saved document that keeps unchanged layers and frames in the bounded
    per-user render cache, so brush-heavy frames are not repainted on every export."""
    if getattr(project, "_disk_cache", None) is not None or not getattr(project, "path", None):
        return project
    from copy import copy
    from .render_cache import enable, user_cache_dir

    return enable(copy(project), user_cache_dir())


def contact_sheet(project, count=8, columns=None, max_width=1600, times=None):
    """A grid of evenly spaced frames, labelled by time, for checking motion at a glance."""
    from PIL import ImageDraw

    project = cached(project)

    timeline = project.state.get("timeline") or default_timeline()
    if times is None:
        require(isinstance(count, int) and 2 <= count <= 48, "Contact sheets show 2–48 frames")
        times = [round(timeline["duration"] * i / (count - 1)) for i in range(count)]
    else:
        times = [parse_time(t, timeline["duration"], timeline.get("markers")) for t in times]
        require(1 <= len(times) <= 48, "Contact sheets show 1–48 frames")
    columns = columns or min(4, len(times))
    rows = math.ceil(len(times) / columns)
    c = project.state["canvas"]
    cell_w = max(32, min(c["width"], (max_width - 8 * (columns + 1)) // columns))
    cell_h = max(16, round(c["height"] * cell_w / c["width"]))
    sheet = Image.new("RGBA", (columns * (cell_w + 8) + 8, rows * (cell_h + 26) + 8), (245, 245, 245, 255))
    draw = ImageDraw.Draw(sheet)
    for i, time in enumerate(times):
        frame = render_at(project, time).resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        x, y = 8 + (i % columns) * (cell_w + 8), 8 + (i // columns) * (cell_h + 26)
        sheet.alpha_composite(frame, (x, y))
        draw.rectangle((x - 1, y - 1, x + cell_w, y + cell_h), outline=(200, 200, 200, 255))
        draw.text((x, y + cell_h + 4), f"{time / 1000:.2f}s", fill=(60, 60, 60, 255))
    return sheet


def _frames(project, times, scale, preview=False, cancelled=None, progress=None):
    c = project.state["canvas"]
    size = (max(1, round(c["width"] * scale)), max(1, round(c["height"] * scale)))
    project.limits.size(*size)
    for index, time in enumerate(times):
        require(not cancelled or not cancelled(), "Timeline cancelled", "cancelled")
        if preview:
            from .proxy import render_preview
            image = render_preview(project, *size, time=time)
        else:
            image = render_scaled(project_at(project, time), scale)
        if progress:
            progress({"done": index + 1, "total": len(times)})
        yield image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)


def export_timeline(project, path, *, format=None, fps=None, scale=1.0, start=None, end=None, background=None, columns=None, quality=90, colors=256, overwrite=False, preview=False, cancelled=None, progress=None):
    """Write the timeline as an animation, sheet or frame sequence. Never clobbers by default.
    Frames render at the target resolution (``scale`` 0.05–16, bounded by the pixel budget);
    ``colors`` (2–256) caps the GIF palette."""
    from .animation import check_colors, gif_bytes, size_warnings

    project = cached(project)
    path = Path(path)
    suffix = path.suffix.lower()
    format = format or {".gif": "gif", ".png": "apng", ".apng": "apng", ".webp": "webp", ".zip": "frames", ".mp4": "mp4", ".webm": "webm"}.get(suffix)
    require(format in FORMATS, f"Timeline format must be one of {', '.join(FORMATS)}")
    expected = {"gif": (".gif",), "apng": (".png", ".apng"), "webp": (".webp",), "sheet": (".png",), "frames": (".zip",), "mp4": (".mp4",), "webm": (".webm",)}[format]
    require(suffix in expected, f"Use a {' or '.join(expected)} filename for {format}")
    finite(scale, "scale", 0.05, 16)
    require(colors == 256 or format == "gif", "colors applies to GIF export", field="colors")
    check_colors(colors)
    timeline = project.state.get("timeline") or default_timeline()
    markers = timeline.get("markers", {})
    first = parse_time(start, timeline["duration"], markers) if start is not None else 0
    last = parse_time(end, timeline["duration"], markers) if end is not None else timeline["duration"]
    times, fps = frame_times(project, fps, first, last, streamed=format in STREAMED)
    destinations = [path] + ([path.with_suffix(".json")] if format == "sheet" else [])
    require(overwrite or not any(p.exists() for p in destinations), "Animation output already exists")
    c = project.state["canvas"]
    w, h = max(1, round(c["width"] * scale)), max(1, round(c["height"] * scale))
    if format in ("gif", "apng", "webp", "sheet"):
        require(w * h * len(times) <= project.limits.max_pixels * 4, "Animation exceeds the in-memory pixel budget; lower fps, scale or duration, or export frames/mp4", "resource_limit")
    quantum = 10 if format == "gif" else 1
    boundaries = [round((t - first) / quantum) * quantum for t in times] + [round((last - first) / quantum) * quantum]
    durations = [b - a for a, b in zip(boundaries, boundaries[1:])]
    require(all(d >= quantum for d in durations), "Frame rate exceeds the animation format timing resolution; lower fps")
    loop = timeline.get("loop", 0)
    frames = _frames(project, times, scale, preview, cancelled, progress)
    if background is not None:
        from .render import color

        base_color = color(background)

        def flattened(source):
            for image in source:
                base = Image.new("RGBA", image.size, base_color)
                base.alpha_composite(image)
                yield base

        frames = flattened(frames)
    metadata = None
    if format in ("mp4", "webm"):
        return _video(path, frames, fps, format, quality, overwrite, len(times), (w, h))
    stream = io.BytesIO()
    if format == "frames":
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as archive:
            for i, image in enumerate(frames):
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                archive.writestr(f"frame_{i:05d}.png", buffer.getvalue())
            archive.writestr("timing.json", json.dumps({"fps": fps, "frame_ms": 1000 / fps, "frames": len(times), "width": w, "height": h, "durations": durations}))
    elif format == "sheet":
        columns = columns or math.ceil(math.sqrt(len(times)))
        require(isinstance(columns, int) and 1 <= columns <= len(times), "Invalid sprite-sheet column count")
        rows = math.ceil(len(times) / columns)
        project.limits.size(w * columns, h * rows)
        sheet = Image.new("RGBA", (w * columns, h * rows))
        metadata = {"width": sheet.width, "height": sheet.height, "fps": fps, "loop": loop, "frames": []}
        for i, image in enumerate(frames):
            x, y = i % columns * w, i // columns * h
            sheet.paste(image, (x, y))
            metadata["frames"].append({"time": round(times[i]), "duration": durations[i], "x": x, "y": y, "width": w, "height": h})
        sheet.save(stream, format="PNG")
    else:
        images = list(frames)
        if format == "gif":
            stream.write(gif_bytes(images, durations, loop, colors))
        elif format == "apng":
            images[0].save(stream, format="PNG", save_all=True, append_images=images[1:], duration=durations, loop=loop + 1 if loop else 0, disposal=0, blend=0)
        else:
            images[0].save(stream, format="WEBP", save_all=True, append_images=images[1:], duration=durations, loop=loop, quality=quality, method=4)
    data = stream.getvalue()
    mode = "wb" if overwrite else "xb"
    with path.open(mode) as output:
        output.write(data)
    if metadata is not None:
        with destinations[1].open("w" if overwrite else "x", encoding="utf-8") as output:
            json.dump(metadata, output, indent=2)
    return {
        "output": str(path),
        "format": format,
        "frames": len(times),
        "fps": fps,
        "duration": sum(durations),
        "frame_durations": durations,
        "requested_duration": round(last - first),
        "size": [w, h],
        "bytes": len(data),
        **({"metadata": str(destinations[1])} if metadata is not None else {}),
        **({"warnings": warnings} if (warnings := size_warnings(format, data)) else {}),
    }


def _video(path, frames, fps, format, quality, overwrite, count, size):
    """Encode frames with ffmpeg as they arrive. Frames are piped as raw pixels, one at a time,
    so memory does not grow with the video's length."""
    ffmpeg = shutil.which("ffmpeg")
    require(ffmpeg, "MP4/WebM export needs ffmpeg on PATH; export gif, webp, apng or frames instead", "missing_dependency")
    require(overwrite or not path.exists(), "Animation output already exists")
    w, h = size
    even = (w + w % 2, h + h % 2)
    crf = str(max(0, min(51, round(51 - quality * 0.33))))
    codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", crf, "-movflags", "+faststart"] if format == "mp4" else ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", crf, "-b:v", "0"]
    pixels = "rgb24" if format == "mp4" else "rgba"
    with tempfile.TemporaryDirectory(prefix="vixl-video-") as staging, tempfile.TemporaryFile() as errors:
        staged = Path(staging) / ("out" + path.suffix)
        command = [ffmpeg, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", pixels, "-s", f"{w}x{h}",
                   "-framerate", str(fps), "-i", "-", "-vf", f"pad={even[0]}:{even[1]}", *codec, str(staged)]
        # stderr goes to a file: a pipe nobody reads would fill up and stall a long encode.
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        written = 0
        try:
            for image in frames:
                if image.size != (w, h):
                    image = image.resize((w, h), Image.Resampling.LANCZOS)
                if format == "mp4":
                    base = Image.new("RGBA", image.size, (255, 255, 255, 255))
                    base.alpha_composite(image.convert("RGBA"))
                    image = base.convert("RGB")
                else:
                    image = image.convert("RGBA")
                process.stdin.write(image.tobytes())
                written += 1
            process.stdin.close()
            code = process.wait(timeout=600)
        except BrokenPipeError:
            code = process.wait(timeout=60)
        except BaseException:
            process.kill()
            process.wait()
            raise
        errors.seek(0)
        error = errors.read().decode("utf-8", "replace")
        require(code == 0, f"ffmpeg failed: {error.strip()[:500]}", "codec_error")
        from .production import publish_file
        byte_count = staged.stat().st_size
        publish_file(path, staged, replace=overwrite)
    return {"output": str(path), "format": format, "frames": written or count, "fps": fps, "duration": round((written or count) * 1000 / fps), "size": [w, h], "bytes": byte_count}


def schemas(add):
    from .schema import S, N, B

    time = {"type": ["number", "string"]}  # ms, "1.5s", "500ms", "50%" or a marker name
    value = {"type": ["number", "string", "boolean"]}
    prop = {"type": "string", "description": "Animatable property: " + ", ".join(NUMERIC + COLORS + STEPPED) + ", or effect:ID. "
            "scale, scale-x and scale-y accept negative values: -1 mirrors the layer on that axis, so animating "
            "scale-x from 1 to -1 swings it over about its pivot (center by default). trim_start and trim_end (0-100, percent of a "
            "shape's or path's outline) draw its stroke on or off: animate trim_end from 0 to 100."}
    extend = {"type": "boolean", "description": "Default true: a key past the timeline end lengthens the duration, and the result's "
              "warnings say so (timeline duration changed 8000 -> 8400 ms). False keeps the duration; the key stays past the end, "
              "shaping the last frames, and is not played."}
    add("timeline-set", {"duration": time, "fps": {"type": "number", "minimum": 1, "maximum": 60}, "loop": {"type": "integer", "minimum": 0, "maximum": 65535}, "clear": B})
    targets = {"type": "array", "items": S, "minItems": 1, "uniqueItems": True}
    add("keyframe", {"property": prop, "time": time, "value": value, "easing": S, "targets": targets, "extend": extend}, ["property", "time", "value"])
    add("keyframe-remove", {"property": S, "time": time})
    add("animate", {"property": prop, "from": value, "to": value, "start": time, "end": time, "duration": time, "easing": S, "targets": targets, "extend": extend}, ["property", "to"])
    add("animate-preset", {"preset": S, "start": time, "duration": time, "easing": S, "distance": N, "amount": N, "fade": B, "to": S, "targets": targets, "extend": extend}, ["preset"])
    add("marker", {"name": S, "time": time, "delete": B}, ["name"], anyOf=[{"required": ["time"]}, {"required": ["delete"]}])

