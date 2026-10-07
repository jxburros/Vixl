"""``reparent``: move existing layers into a group, between groups or out to the page without
ungrouping, keeping where they appear on the canvas.

Each target's drawn box is mapped through its old parents to the canvas and back through its new
parents (``keep: appearance``): a translation only moves x/y; a rotation or mirror of the new parent
becomes the layer's own rotation, skew and flips; anything else (scaling, skew) is held in the
layer's ``affine`` matrix. Animated targets keep their tracks, and the move is refused, naming the
tracks, when a sampled frame would not look the same.
"""

import math

import numpy as np

from .errors import VixlError, require

KEEP = ("appearance", "local")
POSITION_TRACKS = ("x", "y", "translate-x", "translate-y")
# Tracks whose values are coordinates of the parent: they move only under a translation.
PARENT_SPACE = (*POSITION_TRACKS, "width", "height")
GEOMETRY_TRACKS = (*PARENT_SPACE, "rotation", "scale", "scale-x", "scale-y", "skew-x", "skew-y")
TOLERANCE = 0.5  # px: the most a corner of an animated target may move at a sampled frame.
PAGE = ("page", "canvas", "root", "none", "")


def schema(add):
    from .schema import S, B, enum
    from .model import MAX_LAYERS

    refs = {"type": "array", "items": S, "minItems": 1, "maxItems": MAX_LAYERS, "uniqueItems": True}
    add("reparent", {
        "targets": refs,
        "into": {"type": ["string", "null"],
                 "description": "The group to move the targets into, or null (or \"page\") for the top level."},
        "above": {**S, "description": "Place the targets directly above this layer, a child of the new parent."},
        "below": {**S, "description": "Place the targets directly below this layer, a child of the new parent."},
        "index": {"type": "integer", "minimum": 0,
                  "description": "Stacking position among the new parent's children, 0 at the bottom "
                                 "(default: on top)."},
        "keep": {**enum(*KEEP), "description": "appearance (default) keeps each target where it is drawn on the "
                                               "canvas; local keeps its x, y and transform values as they are."},
        "fit": {**B, "description": "Grow the group's content box to include the moved layers (default true); "
                                    "nothing moves on the canvas."},
    }, ["targets", "into"])


def _parent_ref(project, value):
    """The new parent layer, or None for the top level."""
    if value is None or (isinstance(value, str) and value.strip().lower() in PAGE):
        return None
    group = project.layer(value)
    require(group["type"] == "group", f"into must name a group; {group['name']!r} is a {group['type']} layer",
            field="into")
    require(not group.get("repeat"), f"{group['name']!r} repeats its content; layers moved into it would be "
            "drawn many times. Choose another group or remove the repeat first", field="into")
    return group


def _matrices(project):
    """(index, local bounds) of the resolved document, as the renderer places it."""
    from .render import resolve_layout, resolved_layers

    layers = resolved_layers(project)
    return {item["id"]: item for item in layers}, resolve_layout(project, layers=layers)


def _parent_matrix(parent_id, index, local):
    """The matrix from the coordinates of ``parent_id``'s content (the canvas for None) to the canvas."""
    from .checks import group_matrix

    return group_matrix({"parent": parent_id}, index, local)


def _orthonormal(m, sign):
    return abs(np.linalg.det(m) - sign) < 1e-9 and np.allclose(m @ m.T, np.eye(2), atol=1e-9)


def _keyed(project, ident):
    timeline = project.state.get("timeline") or {}
    return [t for t in timeline.get("tracks", []) if t["target"] == ident and t["keys"]]


def _relinearize(layer, q, keyed):
    """Give ``layer`` the linear transform ``q`` @ its current one, in the cleanest fields that hold it."""
    from .affine import matrix

    if np.allclose(q, np.eye(2), atol=1e-9):
        return
    names = {t["property"] for t in keyed}
    affine = matrix(*layer.get("affine", [1, 0, 0, 1, 0, 0]))
    plain = not layer.get("affine") and not names & {"rotation", "skew-x", "skew-y"}
    if plain and _orthonormal(q, 1):
        turn = math.degrees(math.atan2(q[1, 0], q[0, 0]))
        layer["rotation"] = _angle(layer.get("rotation", 0) + turn)
        return
    if plain and _orthonormal(q, -1):
        # q = R(turn) · mirror(y): the mirror passes through the layer's rotation and skew, reversing them.
        turn = math.degrees(math.atan2(q[1, 0], q[0, 0]))
        layer["rotation"] = _angle(turn - layer.get("rotation", 0))
        for key in ("skew_x", "skew_y"):
            if layer.get(key):
                layer[key] = -layer[key]
        layer["flip_y"] = not layer.get("flip_y")
        return
    extra = np.eye(3)
    extra[:2, :2] = q
    combined = extra @ affine
    if np.allclose(combined, np.eye(3), atol=1e-9):
        layer.pop("affine", None)
    else:
        layer["affine"] = [_clean(v) for v in (combined[0, 0], combined[1, 0], combined[0, 1], combined[1, 1],
                                               combined[0, 2], combined[1, 2])]


def _clean(value):
    value = float(value)
    rounded = round(value)
    return float(rounded) if abs(value - rounded) < 1e-9 else round(value, 12)


def _angle(value):
    value = (value + 180) % 360 - 180
    return _clean(0.0 if abs(value) < 1e-9 else value)


def _set_parent(layer, parent_id):
    if parent_id is None:
        layer.pop("parent", None)
    else:
        layer["parent"] = parent_id


def _place(layer, centre):
    """Set ``layer``'s x/y so its drawn box is centred on ``centre`` (parent coordinates)."""
    from .render import stored_origin, transformed_size

    tw, th = transformed_size(layer)
    x, y = stored_origin(layer, (centre[0] - tw / 2, centre[1] - th / 2))
    layer["x"], layer["y"] = _clean(x), _clean(y)


def _insert(state, moved, parent, op, project, old_parents):
    """Put ``moved`` (in document order) at their stacking place among ``parent``'s children."""
    layers = state["layers"]
    ids = {layer["id"] for layer in moved}
    for layer in moved:
        layers.remove(layer)
    parent_id = parent["id"] if parent else None
    siblings = [item for item in layers if item.get("parent") == parent_id]
    if "above" in op or "below" in op:
        require(not ("above" in op and "below" in op), "reparent takes above, below or index, not several",
                field="above")
        where = "above" if "above" in op else "below"
        other = project.layer(op[where])
        require(other["id"] not in ids and other.get("parent") == parent_id,
                f"{where} must name a layer that is already a child of the new parent", field=where)
        position = layers.index(other) + (1 if where == "above" else 0)
    elif "index" in op:
        require("above" not in op and "below" not in op, "reparent takes above, below or index, not several",
                field="index")
        slot = min(op["index"], len(siblings))
        if slot < len(siblings):
            position = layers.index(siblings[slot])
        elif siblings:
            position = layers.index(siblings[-1]) + 1
        else:
            position = layers.index(parent) if parent else len(layers)
    elif parent is not None:
        # On top of the group's children; a group comes after its children in the document.
        position = layers.index(siblings[-1]) + 1 if siblings else layers.index(parent)
    else:
        # Lifted to the page: directly above the group they left.
        lifted = [layers.index(item) for item in old_parents if item in layers and item.get("parent") is None]
        position = max(lifted) + 1 if lifted else len(layers)
    layers[position:position] = moved


def _grow(project, group, notes):
    """Grow ``group``'s content box to include every child, keeping the canvas picture unchanged."""
    from .affine import linear
    from .render import resolve_layout

    state = project.state
    children = [item for item in state["layers"] if item.get("parent") == group["id"]]
    bounds = resolve_layout(project)
    cw, ch = group["content_width"], group["content_height"]
    boxes = [bounds[item["id"]] for item in children if item["type"] != "adjustment"]
    if not boxes:
        return None
    # Whole pixels keep an untransformed group's children on the pixel grid they were drawn on.
    u0 = math.floor(min(0.0, *(b[0] for b in boxes)))
    v0 = math.floor(min(0.0, *(b[1] for b in boxes)))
    u1 = max(cw, math.ceil(max(b[0] + b[2] for b in boxes)))
    v1 = max(ch, math.ceil(max(b[1] + b[3] for b in boxes)))
    if (u0, v0, u1, v1) == (0, 0, cw, ch):
        return None
    animated = {t["property"] for t in _keyed(project, group["id"])} & set(GEOMETRY_TRACKS)
    reason = ("it is animated (" + ", ".join(sorted(animated)) + ")" if animated
              else "it has constraints" if group.get("constraints")
              else "a child has constraints" if any(item.get("constraints") for item in children) else None)
    if reason:
        notes.append(f"The content box of {group['name']!r} was not grown because {reason}; groups do not clip, so "
                     "the moved layers still show")
        return None
    ox, oy = -u0, -v0
    for item in children:
        item["x"], item["y"] = _clean(item["x"] + ox), _clean(item["y"] + oy)
    timeline = state.get("timeline") or {}
    ids = {item["id"] for item in children}
    for track in timeline.get("tracks", []):
        if track["target"] in ids and track["property"] in ("x", "y"):
            for key in track["keys"]:
                key["value"] += ox if track["property"] == "x" else oy
    gx, gy, gw, gh = bounds[group["id"]]
    centre = np.array([gx + gw / 2, gy + gh / 2])
    sx, sy = group["width"] / cw, group["height"] / ch
    new_cw, new_ch = u1 - u0, v1 - v0
    width, height = group["width"] * new_cw / cw, group["height"] * new_ch / ch
    shift = np.array([sx * ox - (width - group["width"]) / 2, sy * oy - (height - group["height"]) / 2])
    centre = centre - linear(group)[:2, :2] @ shift
    group.update(content_width=_clean(new_cw), content_height=_clean(new_ch), width=_clean(width),
                 height=_clean(height))
    _place(group, centre)
    return [_clean(new_cw), _clean(new_ch)]


def execute(project, op):
    from .design import descendants
    from .group_bake import corners, placement, sample_times, snapshot

    state = project.state
    keep = op.get("keep", "appearance")
    require(keep in KEEP, f"keep is {' or '.join(KEEP)}", field="keep")
    targets = [project.layer(ref) for ref in op["targets"]]
    require(len({item["id"] for item in targets}) == len(targets), "Duplicate layer references", field="targets")
    parent = _parent_ref(project, op.get("into"))
    parent_id = parent["id"] if parent else None
    ids = {item["id"] for item in targets}
    for item in targets:
        require(item["id"] != parent_id, f"{item['name']!r} cannot be moved into itself", field="into")
        if parent_id and item["type"] == "group":
            require(parent_id not in descendants(project, item["id"]),
                    f"{item['name']!r} contains {parent['name']!r}; moving it there would put the group inside "
                    "itself", field="into")
    for layer in state["layers"]:
        if layer.get("clip") in ids and layer["id"] not in ids and layer.get("parent") != parent_id:
            raise VixlError("invalid_operation", f"{layer['name']!r} is clipped to "
                            f"{project.layer(layer['clip'])['name']!r}; move them together or release the clip",
                            field="targets")
    for item in targets:
        if item.get("clip") and item["clip"] not in ids and project.layer(item["clip"]).get("parent") != parent_id:
            raise VixlError("invalid_operation", f"{item['name']!r} is clipped to "
                            f"{project.layer(item['clip'])['name']!r}; move them together or release the clip "
                            "(clip release)", field="targets")
    if parent is not None:
        from .design import nest_depth

        above, cursor = 1, parent.get("parent")
        while cursor:
            above += 1
            cursor = project.layer(cursor).get("parent")
        deepest = max(nest_depth(state, item["id"]) for item in targets)
        require(above + deepest <= 16, f"Moving these layers into {parent['name']!r} would nest {above + deepest - 1} "
                "groups inside each other; the limit is 15", "resource_limit", field="into")
    targets.sort(key=state["layers"].index)
    old_parents = [project.layer(item["parent"]) for item in targets if item.get("parent")]
    original = snapshot(project) if keep == "appearance" else None
    animated = {item["id"]: _keyed(project, item["id"]) for item in targets}
    notes = []
    if keep == "appearance":
        from .affine import layer_matrix
        from .render import rest_size

        index, local = _matrices(project)
        destination = np.linalg.inv(_parent_matrix(parent_id, index, local))
        plans = []
        for item in targets:
            resolved = index[item["id"]]
            source = _parent_matrix(item.get("parent"), index, local)
            full = destination @ source @ layer_matrix(resolved, local[item["id"]])
            q = (destination @ source)[:2, :2]
            rest = rest_size(resolved)
            plans.append((item, q, full @ np.array([rest[0] / 2, rest[1] / 2, 1.0]),
                          (destination @ source)[:2, 2]))
        for item, q, centre, offset in plans:
            keyed = animated[item["id"]]
            if keyed and not np.allclose(q, np.eye(2), atol=1e-9):
                fixed = sorted(t["property"] for t in keyed if t["property"] in PARENT_SPACE)
                if fixed:
                    raise VixlError(
                        "invalid_operation",
                        f"Cannot move {item['name']!r} into {parent['name'] if parent else 'the page'!r} keeping its "
                        f"animation: its {', '.join(fixed)} track(s) are in its parent's coordinates, and the new "
                        "parent is rotated, mirrored or scaled differently. Remove those tracks (keyframe-remove), "
                        "use keep: local, or move it into a group with the same orientation and scale",
                        field="targets", tracks=fixed)
            _relinearize(item, q, keyed)
            _set_parent(item, parent_id)
            item["constraints"] = {}
            _place(item, centre[:2])
            if keyed and np.allclose(q, np.eye(2), atol=1e-9):
                for track in keyed:
                    if track["property"] in ("x", "y"):
                        for key in track["keys"]:
                            key["value"] += float(offset[0 if track["property"] == "x" else 1])
    else:
        for item in targets:
            _set_parent(item, parent_id)
    _insert(state, targets, parent, op, project, old_parents)
    grown = _grow(project, parent, notes) if parent is not None and op.get("fit", True) else None
    if original is not None and any(animated.values()):
        from .timeline import project_at

        keyed = [t for tracks in animated.values() for t in tracks]
        for time in sample_times(project, (k["time"] for t in keyed for k in t["keys"])):
            before, after = project_at(original, time), project_at(project, time)
            for item in targets:
                if not animated[item["id"]]:
                    continue
                _, was, rest, _ = placement(before, item["id"])
                _, now, rest_now, _ = placement(after, item["id"])
                error = float(np.abs(corners(now, rest_now) - corners(was, rest)).max())
                if error > TOLERANCE:
                    names = sorted(t["property"] for t in animated[item["id"]])
                    raise VixlError(
                        "invalid_operation",
                        f"Cannot move {item['name']!r} keeping its animation: at {time} ms it would be off by "
                        f"{error:.1f} px (tracks: {', '.join(names)}). Remove those tracks, use keep: local, or "
                        "choose a parent with the same orientation and scale", field="targets", tracks=names)
    state["active_layer"] = targets[-1]["id"]
    from .selectors import record

    report = {"into": parent["name"] if parent else None, "layers": [item["name"] for item in targets],
              "keep": keep}
    if grown:
        report["content_size"] = grown
    if notes:
        report["notes"] = notes
        from .notices import warn

        for note in notes:
            warn(project, note)
    record(project, "reparent", report)
    return report

