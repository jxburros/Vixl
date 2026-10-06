"""Bounded, deterministic motion recipes compiled to ordinary editable timeline keys.

Coordinates and gravity use pixels and seconds; operation times use milliseconds.
"""
import math
from .errors import require
from .model import finite

TYPES = ("motion", "keyframes")
RECIPES = ("follow-path", "orbit", "bounce", "shake", "wiggle", "spring", "look-at", "overlap", "breathing", "blink", "hover")


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
        "phase": N, "easing": easing_schema(), "extend": B}, ["recipe"])
    add("keyframes", {"property": S, "keys": {"type": "array", "minItems": 1, "maxItems": 8192,
        "items": {"type": "object", "properties": {"time": time, "value": {}, "easing": easing_schema()}, "required": ["time", "value"], "additionalProperties": False}}, "extend": B}, ["property", "keys"])


def execute(project, op):
    from .timeline import execute_timeline, _timeline, parse_time, static_value, project_at
    if op["type"] == "keyframes":
        for key in op["keys"]:
            execute_timeline(project, {"type": "keyframe", "target": op.get("target"), "property": op["property"], "extend": op.get("extend", True), **key})
        return
    settings = _timeline(project)
    start = parse_time(op.get("start", 0), settings["duration"], settings.get("markers"))
    length = parse_time(op.get("duration", 1000), settings["duration"], settings.get("markers"))
    require(length >= 10, "Motion duration must be at least 10 ms")
    recipe = op["recipe"]
    require(recipe in RECIPES, "Unknown motion recipe")
    targets = [project.layer(ref) for ref in op.get("targets", [op.get("target")])]
    if op.get("children"):
        roots = {layer["id"] for layer in targets}
        targets = [layer for layer in project.state["layers"] if layer.get("parent") in roots]
    require(targets, "Motion needs at least one target")
    samples = op.get("samples", min(120, max(16, math.ceil(length / 1000 * settings["fps"]))))
    require(isinstance(samples, int) and 2 <= samples <= 512, "Motion samples must be 2–512")
    amount = finite(op.get("amount", 12), "amount", -100000, 100000)
    period = finite(op.get("period", 1000), "period", 10, 600000)
    frequency = finite(op.get("frequency", 3), "frequency", 0.01, 60)
    damping = finite(op.get("damping", 6), "damping", 0.01, 100)
    stagger = finite(op.get("stagger", 0), "stagger", 0, 600000)
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
    return result
