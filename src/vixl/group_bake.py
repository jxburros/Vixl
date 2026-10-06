"""Layer matrices through nested groups, sampled over a timeline.

``ungroup`` uses this to move a group's own animation onto its children, and the ``attach``
motion recipe uses it to pin a layer to a point of another layer as that layer moves.
"""

from copy import copy, deepcopy
import math

import numpy as np

from .errors import VixlError

# Group tracks whose effect on a child can be rewritten as the child's own keys.
BAKEABLE = ("x", "y", "translate-x", "translate-y", "rotation", "scale", "scale-x", "scale-y", "width", "height",
            "opacity", "visible")
TOLERANCE = 0.5  # px: the most any corner of a baked child may move at a sampled frame.


def snapshot(project):
    """A detached copy to sample from while ``project`` is being changed."""
    original = copy(project)
    original.state = deepcopy(project.state)
    return original


def placement(frame, ident):
    """``(parent, full, rest, local)`` for a layer of a rendered frame: the matrix from its parent's
    coordinates to the canvas, the matrix from its own unrotated box to the canvas, its rest size and
    its bounds in parent coordinates."""
    from .affine import layer_matrix
    from .checks import group_matrix
    from .render import resolve_layout, resolved_layers, rest_size

    layers = resolved_layers(frame)
    index = {item["id"]: item for item in layers}
    local = resolve_layout(frame, layers=layers)
    item = index[ident]
    parent = group_matrix(item, index, local)
    return parent, parent @ layer_matrix(item, local[ident]), rest_size(item), local[ident]


def apply_point(matrix, point):
    x, y, _ = matrix @ np.array([float(point[0]), float(point[1]), 1.0])
    return float(x), float(y)


def corners(matrix, rest):
    w, h = rest
    return np.array([apply_point(matrix, p) for p in ((0, 0), (w, 0), (w, h), (0, h))])


def angle(matrix):
    return math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))


def sample_times(project, times=None):
    """Whole-millisecond key times: every frame of the timeline, its end, and ``times``."""
    from .timeline import frame_times

    duration = project.state["timeline"]["duration"]
    frames = {int(round(t)) for t in frame_times(project)[0]} | {duration} | set(times or ())
    return sorted(t for t in frames if 0 <= t <= duration)


def track_value(project, target, prop, time):
    """The value of ``prop`` on ``target`` at ``time``: its track's, else the static value."""
    from .timeline import _track, sample_track, static_value

    track = _track(project.state["timeline"], target, prop, create=False)
    if track and track["keys"]:
        return sample_track(project, track, time)
    return static_value(project, target, prop)


def write_keys(project, target, prop, keys, easing=None):
    from .timeline import MAX_KEYS, _track

    from .errors import require

    require(len(keys) <= MAX_KEYS, "Too many keys to bake; shorten the timeline or lower its fps", "resource_limit")
    track = _track(project.state["timeline"], target, prop)
    track["keys"] = [{"time": t, "value": v, **({"easing": easing} if easing else {})} for t, v in keys]
    return track


def _refuse(group, tracks, reason):
    names = ", ".join(sorted(t["property"] for t in tracks))
    return VixlError(
        "invalid_operation",
        f"Cannot ungroup {group['name']!r} with its animation: its {names} track(s) {reason}. Remove those tracks "
        "(keyframe-remove), animate the children instead, or keep the group",
        field="target",
        tracks=sorted(t["property"] for t in tracks),
    )


def ungroup_tracks(project, group, children, offset):
    """Prepare ``ungroup`` for a timeline: sample the group's animation now, before the group is
    dissolved, and return a function that, run after it, rewrites the children's tracks so every
    frame looks the same. Raises before anything changes when the animation cannot move."""
    timeline = project.state.get("timeline")
    if not timeline or not timeline.get("tracks"):
        return lambda: None
    own = [t for t in timeline["tracks"] if t["target"] == group["id"]]
    keyed = [t for t in own if t["keys"]]
    ids = [child["id"] for child in children]
    if keyed:
        unsupported = [t for t in keyed if t["property"] not in BAKEABLE]
        if unsupported:
            raise _refuse(group, unsupported, "have no equivalent on the children")
        fading = [t for t in keyed if t["property"] == "opacity" and any(k["value"] != 1 for k in t["keys"])]
        if fading and len(children) > 1:
            raise _refuse(group, fading, "fade the group as one picture, and fading each overlapping child would not "
                          "look the same")
    original = snapshot(project) if keyed else None
    samples = []
    if keyed:
        times = sample_times(project, (k["time"] for t in keyed for k in t["keys"]))
        rotation = next((t for t in keyed if t["property"] == "rotation"), None)
        for time in times:
            from .timeline import project_at, sample_track

            frame = project_at(original, time)
            gparent, gfull, grest, _ = placement(frame, group["id"])
            content = np.linalg.inv(gparent) @ gfull @ np.diag([grest[0] / group["content_width"],
                                                               grest[1] / group["content_height"], 1.0])
            linear = content[:2, :2]
            if np.linalg.det(linear) < 0:
                raise _refuse(group, [t for t in keyed if t["property"].startswith("scale")],
                              "mirror the group (a negative scale)")
            record = {"time": time, "sx": float(np.linalg.norm(linear[:, 0])), "sy": float(np.linalg.norm(linear[:, 1])),
                      "rotation": sample_track(original, rotation, time) if rotation else 0.0,
                      "opacity": frame.layer(group["id"])["opacity"], "visible": frame.layer(group["id"])["visible"],
                      "children": {}}
            inverse = np.linalg.inv(gparent)
            for ident in ids:
                _, full, rest, _ = placement(frame, ident)
                record["children"][ident] = {"centre": apply_point(inverse @ full, (rest[0] / 2, rest[1] / 2)),
                                             "corners": corners(full, rest)}
            samples.append(record)

    def finish():
        # The children's own x/y keys were local to the group; the group's box sat at ``offset``.
        for track in timeline["tracks"]:
            if track["target"] in ids and track["property"] in ("x", "y"):
                shift = offset[0 if track["property"] == "x" else 1]
                for key in track["keys"]:
                    key["value"] += shift
        from .timeline import prune_targets

        prune_targets(project.state, {group["id"]})
        if not keyed:
            return
        from .timeline import project_at

        props = {t["property"] for t in keyed}
        scaled = any(abs(s["sx"] - 1) > 1e-9 or abs(s["sy"] - 1) > 1e-9 for s in samples)
        for ident in ids:
            if "rotation" in props:
                write_keys(project, ident, "rotation",
                           [(s["time"], track_value(original, ident, "rotation", s["time"]) + s["rotation"]) for s in samples])
            if scaled:
                xs, ys = [], []
                for s in samples:
                    turned = round((track_value(original, ident, "rotation", s["time"]) % 180) / 90) % 2 == 1
                    sx, sy = (s["sy"], s["sx"]) if turned else (s["sx"], s["sy"])
                    xs.append((s["time"], track_value(original, ident, "scale-x", s["time"]) * sx))
                    ys.append((s["time"], track_value(original, ident, "scale-y", s["time"]) * sy))
                write_keys(project, ident, "scale-x", xs)
                write_keys(project, ident, "scale-y", ys)
            if "opacity" in props:
                write_keys(project, ident, "opacity",
                           [(s["time"], track_value(original, ident, "opacity", s["time"]) * s["opacity"]) for s in samples])
            if "visible" in props:
                write_keys(project, ident, "visible",
                           [(s["time"], bool(track_value(original, ident, "visible", s["time"]) and s["visible"]))
                            for s in samples], "hold")
        moves = {ident: ([], []) for ident in ids}
        for s in samples:
            frame = project_at(project, s["time"])
            for ident in ids:
                _, _, _, (x, y, w, h) = placement(frame, ident)
                cx, cy = s["children"][ident]["centre"]
                moves[ident][0].append((s["time"], track_value(project, ident, "translate-x", s["time"]) + cx - x - w / 2))
                moves[ident][1].append((s["time"], track_value(project, ident, "translate-y", s["time"]) + cy - y - h / 2))
        for ident, (xs, ys) in moves.items():
            write_keys(project, ident, "translate-x", xs)
            write_keys(project, ident, "translate-y", ys)
        for s in samples:
            frame = project_at(project, s["time"])
            for ident in ids:
                _, full, rest, _ = placement(frame, ident)
                error = float(np.abs(corners(full, rest) - s["children"][ident]["corners"]).max())
                if error > TOLERANCE:
                    raise _refuse(group, [t for t in keyed if t["property"] not in ("opacity", "visible")],
                                  f"cannot be rewritten exactly on {project.layer(ident)['name']!r} (off by "
                                  f"{error:.1f} px at {s['time']} ms; uneven scaling of a rotated child needs skew)")
        from .timeline import _note

        _note(project, f"ungroup moved the animation of {group['name']!r} ({', '.join(sorted(props))}) onto its "
              f"{len(ids)} child layer(s) as per-frame keys")

    return finish


def _anchor_point(op, rest):
    """The attach point in the followed layer's own box: an anchor name, [fx, fy] fractions of its
    box (units: fraction, the default) or [x, y] pixels from its top-left corner (units: px)."""
    from .errors import require
    from .geometry import ANCHORS, canonical_anchor
    from .model import finite

    value = op["anchor"]
    if isinstance(value, str):
        name = canonical_anchor(value)
        require(name, f"Unknown anchor {value!r}; use {', '.join(ANCHORS)} or [x, y]", field="anchor")
        value, units = list(ANCHORS[name]), "fraction"
    else:
        require(isinstance(value, list) and len(value) == 2, "anchor is [x, y] or an anchor name", field="anchor")
        units = op.get("units", "fraction")
        require(units in ("fraction", "px"), "attach units are fraction or px", field="units")
    x, y = (finite(v, "anchor", -1e6, 1e6) for v in value)
    return (x * rest[0], y * rest[1]) if units == "fraction" else (x, y)


def _held_point(frame, ident, rest):
    """Where a follower is held: its pivot when it has one, else its centre (in its own box)."""
    pivot = frame.layer(ident).get("pivot")
    return (pivot[0] * rest[0], pivot[1] * rest[1]) if pivot is not None else (rest[0] / 2, rest[1] / 2)


def attach(project, op, layer, follow, start, length):
    """The ``attach`` motion recipe: keys that keep ``layer`` (its pivot, else its centre) on a point
    of ``follow`` in every frame from ``start`` for ``length`` ms, through the groups both sit in,
    and, with ``rotation``, turning as ``follow`` turns. Returns the attachment record."""
    from .errors import require
    from .model import finite
    from .timeline import _timeline, _track, execute_timeline, project_at

    require(follow != layer["id"], "A layer cannot attach to itself", field="follow")
    settings = _timeline(project)
    end = start + length
    if "samples" in op:
        times = sorted({start + round(length * i / op["samples"]) for i in range(op["samples"] + 1)})
    else:
        step = 1000 / settings["fps"]
        times = sorted({*(start + round(i * step) for i in range(int(length / step) + 1)), end})
    require(len(times) <= 4096, "attach would write too many keys; shorten it or pass samples", "resource_limit")
    original = snapshot(project)
    frame = project_at(original, start)
    _, followed, frest, _ = placement(frame, follow)
    _, held, hrest, _ = placement(frame, layer["id"])
    if "anchor" in op:
        anchor = _anchor_point(op, frest)
    else:
        # Without an anchor the layer stays where it is now, relative to what it follows.
        anchor = apply_point(np.linalg.inv(followed), apply_point(held, _held_point(frame, layer["id"], hrest)))
    offset = op.get("offset", [0, 0])
    require(isinstance(offset, list) and len(offset) == 2, "offset is [dx, dy] pixels", field="offset")
    anchor = (anchor[0] + finite(offset[0], "offset", -1e6, 1e6), anchor[1] + finite(offset[1], "offset", -1e6, 1e6))
    turn = op.get("rotation", True)
    require(isinstance(turn, bool), "rotation is true or false", field="rotation")
    relative = angle(held) - angle(followed)
    keys = {"translate-x": [], "translate-y": [], **({"rotation": []} if turn else {})}
    previous = None
    for time in times:
        frame = project_at(original, time)
        parent, held, hrest, _ = placement(frame, layer["id"])
        _, followed, _, _ = placement(frame, follow)
        want, have = apply_point(followed, anchor), apply_point(held, _held_point(frame, layer["id"], hrest))
        dx, dy = np.linalg.inv(parent[:2, :2]) @ np.array([want[0] - have[0], want[1] - have[1]])
        keys["translate-x"].append((time, track_value(original, layer["id"], "translate-x", time) + float(dx)))
        keys["translate-y"].append((time, track_value(original, layer["id"], "translate-y", time) + float(dy)))
        if turn:
            delta = (angle(followed) + relative - angle(held) + 180) % 360 - 180
            value = track_value(original, layer["id"], "rotation", time) + delta
            if previous is not None:
                value += 360 * round((previous - value) / 360)  # Keep turning the short way between keys.
            keys["rotation"].append((time, value))
            previous = value
    record = {"to": follow, "anchor": [round(float(v), 3) for v in anchor], "rotation": turn, "start": start, "end": end}
    timeline = project.state["timeline"]
    for prop, values in keys.items():
        track = _track(timeline, layer["id"], prop, create=False)
        if track:
            track["keys"] = [k for k in track["keys"] if not start <= k["time"] <= end]
        for time, value in values:
            execute_timeline(project, {"type": "keyframe", "target": layer["id"], "property": prop, "time": time,
                                       "value": value, "extend": op.get("extend", True)})
        _track(timeline, layer["id"], prop)["attach"] = record
    return record
