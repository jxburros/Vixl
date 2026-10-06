"""The ``connected`` check: parts of a grouped object that float free of its main body.

Within each visible group (a mascot, a character, a prop built from shapes), the drawn ink of every
direct child is compared on the canvas. Parts whose ink touches or overlaps (within ``tolerance``
pixels) form one piece; the piece with the most ink is the main body, and every other part is
reported with its gap. Groups that are collections rather than objects (charts, drawings, repeats)
are skipped, and so are text parts. ``layer-intent detached_ok`` marks a part that floats on purpose,
or a group whose parts are separate by design. A document with a timeline is checked at its poster,
middle and last frames, since a swinging limb can come loose mid-animation.
"""

import numpy as np

# Groups that hold a set of separate things by design, not one object.
COLLECTIONS = ("chart", "drawing", "repeat", "container", "diagram", "bubble")
ALPHA = 32
MAX_POINTS = 1500


def _shown(item, index):
    while item:
        if not item["visible"] or item["opacity"] <= 0:
            return False
        item = index.get(item.get("parent"))
    return True


def _edge(mask):
    from .drawing import erode

    return mask & ~erode(mask, 1)


def _gap(a, b):
    """The shortest distance in pixels between the ink of two masks."""
    pa, pb = np.argwhere(_edge(a)), np.argwhere(_edge(b))
    if not len(pa) or not len(pb):
        return 0.0
    pa = pa[:: max(1, len(pa) // MAX_POINTS)].astype(float)
    pb = pb[:: max(1, len(pb) // MAX_POINTS)].astype(float)
    best = np.inf
    for start in range(0, len(pa), 256):
        chunk = pa[start:start + 256]
        best = min(best, float(np.sqrt(((chunk[:, None, :] - pb[None, :, :]) ** 2).sum(-1)).min()))
    return best


def _components(masks, tolerance):
    from .drawing import dilate

    count = len(masks)
    parent = list(range(count))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grown = [dilate(mask, int(np.ceil(tolerance))) if tolerance > 0 else mask for mask in masks]
    for i in range(count):
        for j in range(i + 1, count):
            if find(i) != find(j) and (grown[i] & masks[j]).any():
                parent[find(i)] = find(j)
    groups = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def floating_parts(frame, tolerance=2, targets=None):
    """``[(group, part, gap_px)]`` for every visible part of a group that floats free of its main body."""
    from .render import layer_canvas_surface, resolve_layout, resolved_layers

    layers = resolved_layers(frame)
    index = {item["id"]: item for item in layers}
    local = resolve_layout(frame, layers=layers)
    wanted = None
    if targets:
        wanted = {frame.layer(t)["id"] for t in targets}

    def selected(group):
        item = group
        while item:
            if item["id"] in wanted:
                return True
            item = index.get(item.get("parent"))
        return False

    result = []
    for group in layers:
        if (group["type"] != "group" or group.get("detached_ok") or any(group.get(key) for key in COLLECTIONS)
                or not _shown(group, index) or (wanted is not None and not selected(group))):
            continue
        parts = [item for item in layers if item.get("parent") == group["id"] and _shown(item, index)
                 and item["type"] not in ("text", "adjustment")]
        if len(parts) < 2:
            continue
        masks, kept = [], []
        for part in parts:
            alpha = np.asarray(layer_canvas_surface(frame, part, local, index).getchannel("A")) > ALPHA
            if alpha.any():
                masks.append(alpha)
                kept.append(part)
        if len(kept) < 2:
            continue
        union = np.any(masks, axis=0)
        rows, cols = np.any(union, axis=1), np.any(union, axis=0)
        pad = int(np.ceil(tolerance)) + 1
        top, bottom = max(0, int(np.argmax(rows)) - pad), min(len(rows), len(rows) - int(np.argmax(rows[::-1])) + pad)
        left, right = max(0, int(np.argmax(cols)) - pad), min(len(cols), len(cols) - int(np.argmax(cols[::-1])) + pad)
        masks = [mask[top:bottom, left:right] for mask in masks]
        pieces = _components(masks, tolerance)
        if len(pieces) < 2:
            continue
        main = max(pieces, key=lambda piece: sum(int(masks[i].sum()) for i in piece))
        body = np.any([masks[i] for i in main], axis=0)
        for piece in pieces:
            if piece is main:
                continue
            for i in piece:
                if not kept[i].get("detached_ok"):
                    result.append((group, kept[i], round(_gap(masks[i], body), 1)))
    return result


def check_connected(project, issue, tolerance=2, targets=None, resolved=None):
    """Report floating parts as ``connected`` warnings, at each sampled frame of a timeline."""
    from .model import finite

    tolerance = finite(tolerance, "connect_tolerance", 0, 100)
    timeline = project.state.get("timeline")
    frames = [(None, project)]
    if timeline and timeline.get("tracks"):
        from .timeline import project_at, sample_frame_times

        frames = [(label, project_at(project, time)) for label, time in sample_frame_times(timeline)]
    seen = set()
    for label, frame in frames:
        for group, part, gap in floating_parts(frame, tolerance, targets):
            if part["id"] in seen:
                continue
            seen.add(part["id"])
            when = f" at the {label} frame" if label else ""
            layer = (resolved or {}).get(part["id"], part)
            issue("connected", "warning",
                  f"{part['name']!r} floats free of the rest of {group['name']!r}{when}: {gap:g} px from its main body. "
                  "Overlap it with the part it belongs to (joints overlap a few pixels), or mark it with layer-intent "
                  "detached_ok if it floats on purpose", [layer], group=group["name"], gap=gap,
                  **({"frame": label} if label else {}))
