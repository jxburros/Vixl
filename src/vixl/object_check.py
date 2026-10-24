"""The ``object`` check: each declared object measured against what its kind says it is made of.

It runs on groups with an ``object`` record (``objects.all_objects`` minus implicit characters, which the
``character`` check covers) and on every sub-object, against the kind merged down its chain (``objects.merged``):

- **parts**: a required part no layer names, fewer layers than a required part's ``count``, a paired part (``side``
  in the kind) with more than two layers, without a side or twice on one side, and part names the kind does not list;
- **connections**: each pair of parts the kind says must touch, measured on the parts' rendered ink (the masks and
  dilation of the ``connected`` check) and reported with the gap and both paths (``guitar/neck ↔ guitar/body: 6 px
  gap``). A document with a timeline is sampled at the frames ``connected`` samples;
- **proportions**: a part's size against the object's height or another part outside the kind's range; an object
  marked ``stylized: true`` or ``proportions: "ignore"`` has none;
- **symmetry**: a left/right pair whose sizes differ by more than 15%, or that sits on one side of the axis of the
  part it attaches to. A pair marked ``depth`` far/near is a side view and is not mirrored;
- **layering**: parts that overlap stacked against the kind's back-to-front ``layering``;
- **outline**: for an object with an applied outline policy (``object_outline``), part strokes that show inside its
  silhouette, part outlines of uneven width under ``parts``, and an outline drawn for other geometry.

Each finding has ``rule`` ``object.<code>``, ``layer_ids``, ``box`` (canvas pixels), ``measured``, ``action`` and a
``hint``, which names the kind's build placement for the part when it has one. More findings plug in through
``FINDERS``: a finder takes the shared ``Context`` and one ``Subject`` and yields ``Finding`` values; measurements it
needs (rendered masks, boxes in the object's frame, paint order) come from the context, which computes each once.
"""

from dataclasses import dataclass, field
import math

import numpy as np

SYMMETRY_TOLERANCE = 0.15
# Layering hints that name a family of parts rather than one part.
FAMILIES = {
    "limbs": ("arm", "upper-arm", "lower-arm", "hand", "leg", "upper-leg", "lower-leg", "foot", "paw", "wing", "fin"),
    "features": ("eye", "brow", "mouth", "nose", "whiskers", "cheek"),
}


@dataclass
class Subject:
    """One declared object: its group, kind, merged kind fields and the layers that name its parts."""
    group: dict
    kind: str
    path: str
    fields: dict
    record: dict
    parts: list
    subs: list
    named: dict = field(default_factory=dict)

    def present(self, name):
        """Layers that stand for part ``name``: its part layers, or a sub-object of the part's ``sub_object`` kind."""
        if self.named.get(name):
            return self.named[name]
        from .objects import record

        spec = next((p for p in self.fields.get("parts", []) if p["name"] == name), {})
        wanted = {name, spec.get("sub_object")} - {None}
        return [sub for sub in self.subs if record(sub)["kind"] in wanted or record(sub).get("label") in wanted]


@dataclass
class Finding:
    code: str
    message: str
    layers: list
    action: str = "review"
    measured: dict | None = None
    hint: str | None = None
    box: list | None = None
    extra: dict = field(default_factory=dict)


class Context:
    """What the finders share: the document, its resolved layers, and measurements computed once per check."""

    def __init__(self, project, resolved, kinds, tolerance, frames, local=None):
        from .render import child_index, resolved_layers
        from .spatial import canvas_boxes

        self.project, self.kinds, self.tolerance, self.frames = project, kinds, tolerance, frames
        self.static = frames[0][1]
        self.resolved = resolved or {item["id"]: item for item in resolved_layers(project)}
        self._views = {}
        if self.static is project and resolved and local is not None:
            # The calling check's resolved layers and layout already describe this frame.
            self._views[frames[0][0]] = (list(resolved.values()), local, resolved)
        layers, self.local, self.index = self.view(frames[0][0])
        self.children = child_index(layers)
        self.canvas = canvas_boxes(self.static, layers=layers, local=self.local)
        self.state_index = {item["id"]: item for item in project.state["layers"]}
        self._masks, self._frame_boxes, self._order, self._paths = {}, {}, None, {}
        self._regions, self._ink = {}, {}

    def view(self, label):
        """(resolved layers, local layout, layers by ID) of the frame ``label``."""
        if label not in self._views:
            from .render import resolve_layout, resolved_layers

            frame = dict(self.frames)[label]
            layers = resolved_layers(frame)
            self._views[label] = (layers, resolve_layout(frame, layers=layers), {item["id"]: item for item in layers})
        return self._views[label]

    def region(self, subject, label=None):
        """``(left, top, width, height)``: the canvas pixels around the object's ink at frame ``label``, which its
        masks cover."""
        label = self.frames[0][0] if label is None else label
        key = (label, subject.group["id"])
        if key not in self._regions:
            from .spatial import canvas_boxes

            layers, local, _ = self.view(label)
            frame = dict(self.frames)[label]
            if label not in self._ink:
                self._ink[label] = canvas_boxes(frame, "ink", layers=layers, local=local)
            x, y, w, h = self._ink[label][subject.group["id"]]
            pad, canvas = int(math.ceil(self.tolerance)) + 2, frame.state["canvas"]
            left, top = max(0, math.floor(x) - pad), max(0, math.floor(y) - pad)
            right = min(canvas["width"], math.ceil(x + w) + pad)
            bottom = min(canvas["height"], math.ceil(y + h) + pad)
            self._regions[key] = (left, top, max(1, right - left), max(1, bottom - top))
        return self._regions[key]

    def mask(self, subject, layer, label=None):
        """The ink mask of ``layer`` at the frame ``label`` (the first frame by default) over the object's
        ``region``: each part is drawn once per frame onto a tile the size of its object, not of the canvas."""
        from copy import copy

        from .parts import part_mask

        label = self.frames[0][0] if label is None else label
        key = (label, subject.group["id"], layer["id"])
        if key not in self._masks:
            _, local, index = self.view(label)
            if layer["id"] not in index:
                self._masks[key] = None
                return None
            left, top, width, height = self.region(subject, label)
            root = index[layer["id"]]
            while root.get("parent") in index:
                root = index[root["parent"]]
            frame = dict(self.frames)[label]
            tile = copy(frame)
            tile.state = {**frame.state, "canvas": {**frame.state["canvas"], "width": width, "height": height}}
            x, y, *size = local[root["id"]]
            bounds = {**local, root["id"]: (x - left, y - top, *size)}
            self._masks[key] = part_mask(tile, index[layer["id"]], bounds, index)
        return self._masks[key]

    def frame_box(self, subject, layer):
        """``(x, y, w, h)`` of ``layer`` in its object's own frame (the group's content space, before the group's
        rotation, scale or flip), so proportions and mirroring read the same on a turned object."""
        from .affine import corners, envelope, layer_matrix
        from .checks import group_matrix
        from .render import rest_size

        key = (subject.group["id"], layer["id"])
        if key not in self._frame_boxes:
            inner = group_matrix({"parent": subject.group["id"]}, self.index, self.local)
            item = self.index[layer["id"]]
            transform = np.linalg.inv(inner) @ group_matrix(item, self.index, self.local) @ layer_matrix(
                item, self.local[item["id"]])
            self._frame_boxes[key] = envelope(corners((0, 0, *rest_size(item)), transform))
        return self._frame_boxes[key]

    def object_box(self, subject):
        """The object's drawn extent in its own frame: the union of its visible direct children."""
        boxes = [self.frame_box(subject, child) for child in self.children.get(subject.group["id"], [])
                 if shown(child, self.index)]
        return union(boxes) if boxes else (0, 0, 0, 0)

    def order(self):
        """``{layer id: paint rank}``: a layer with a higher rank draws over one with a lower rank."""
        if self._order is None:
            ranks, stack = {}, list(reversed(self.children.get(None, [])))
            while stack:
                item = stack.pop()
                ranks[item["id"]] = len(ranks)
                stack.extend(reversed(self.children.get(item["id"], [])))
            self._order = ranks
        return self._order

    def path(self, layer):
        """``dog/leg[left]``; a path that names several layers (four legs without sides) adds the layer's name."""
        if layer["id"] not in self._paths:
            from .errors import VixlError
            from .objects import path_of, resolve_all

            item = self.state_index[layer["id"]]
            text = path_of(self.project, item, self.state_index) or layer["name"]
            try:
                same = resolve_all(self.project, text) if "/" in text else None
            except VixlError:
                same = None
            if same and len(same) > 1:
                text += f" ({item['name'].rsplit('/', 1)[-1]})"
            self._paths[layer["id"]] = text
        return self._paths[layer["id"]]

    def box(self, layers):
        boxes = [self.canvas[item["id"]] for item in layers if item["id"] in self.canvas]
        return [round(v, 2) for v in union(boxes)] if boxes else None


def union(boxes):
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return x0, y0, x1 - x0, y1 - y0


def shown(item, index):
    while item:
        if not item["visible"] or item["opacity"] <= 0:
            return False
        item = index.get(item.get("parent"))
    return True


def placement_hint(subject, name):
    """The kind's build placement for part ``name`` as text, or None."""
    for item in subject.fields.get("build", {}).get("placements", []):
        if item["part"] == name:
            text = f"build placement: {name} at {item['anchor']}"
            if item.get("at"):
                text += f" (its {item['at']} there)"
            if item.get("spread"):
                text += f", spread {item['spread']} along it"
            if item.get("side"):
                text += f", side {item['side']}"
            return text + (f": {item['note']}" if item.get("note") else "")
    return None


def _label(subject, name, count=None):
    return f"{subject.path}/{name}" + (f" ×{count}" if count and count > 1 else "")


# ---------------------------------------------------------------------------------------------------------------
# Finders


def parts(context, subject):
    kind, spec = subject.kind, subject.fields.get("parts", [])
    declare = "{type: object, action: part, target: LAYER, part: NAME}"
    for part in spec:
        name, count = part["name"], part.get("count", 1)
        found = subject.present(name)
        if part.get("required") and not found:
            yield Finding("part-missing", f"{subject.path} has no {name} (a {kind} needs {name}"
                          + (f" ×{count}" if count > 1 else "") + f"): draw it and name it with {declare}",
                          [subject.group], "fix", {"actual": 0, "expected": count, "unit": "parts"},
                          placement_hint(subject, name) or f"vixl_reference('objects', name={kind!r}) lists its parts",
                          extra={"part": name})
            continue
        layers = subject.named.get(name, [])
        if part.get("required") and layers and len(layers) < count:
            yield Finding("part-count", f"{subject.path} has {len(layers)} {name} part"
                          + ("s" if len(layers) != 1 else "") + f"; a {kind} has {count}", layers, "fix",
                          {"actual": len(layers), "expected": count, "unit": "parts"},
                          placement_hint(subject, name) or "draw the missing ones and name them as the same part",
                          extra={"part": name})
        if not part.get("side") or len(layers) < 2:
            continue
        if len(layers) > count:
            yield Finding("part-count", f"{subject.path} has {len(layers)} {name} parts; a {kind} has {count}",
                          layers, "review", {"actual": len(layers), "expected": count, "unit": "parts"},
                          "remove the extra one or name it as another part", extra={"part": name})
        sides = [_side(layer) for layer in layers]
        if None in sides or len(set(sides)) < len(sides):
            missing = sum(1 for side in sides if side is None)
            yield Finding("part-side", f"{subject.path} has {len(layers)} {name} parts "
                          + (f"and {missing} without a side" if missing else "on the same side")
                          + ": name them side left and right", layers, "review",
                          {"actual": sides, "expected": ["left", "right"], "unit": "sides"},
                          f"{{type: object, action: part, target: LAYER, part: {name}, side: left|right}}",
                          extra={"part": name})
    known = {part["name"] for part in spec}
    for name, layers in subject.named.items():
        if known and name not in known:
            yield Finding("part-unknown", f"{name!r} is not a part of a {kind} (parts: {', '.join(sorted(known))}); "
                          "rename it to one of them, or keep it as free text", layers, "review",
                          {"actual": name, "expected": sorted(known), "unit": "part name"},
                          f"vixl_reference('objects', name={kind!r}) lists the parts", extra={"part": name})


def _side(layer):
    from .objects import part_of

    return (part_of(layer) or {}).get("side")


def connections(context, subject):
    from .parts import _components, _gap, touches

    if subject.group.get("detached_ok"):
        return
    reported = set()
    for first, second in subject.fields.get("connections", []):
        # A part marked detached_ok floats on purpose (a thrown ball); it still anchors the parts that join it.
        a = [layer for layer in subject.present(first) if shown(layer, context.index) and not layer.get("detached_ok")]
        b = [layer for layer in subject.present(second) if shown(layer, context.index)]
        if not a or not b:
            continue
        for label, _ in context.frames:
            when = f" at the {label} frame" if label else ""
            masks = {layer["id"]: context.mask(subject, layer, label) for layer in {x["id"]: x for x in a + b}.values()}
            masks = {key: value for key, value in masks.items() if value is not None and value.any()}
            region = _region([masks[key] for key in masks], context.tolerance)
            if region is None:
                continue
            crop = {key: value[region[1]:region[3], region[0]:region[2]] for key, value in masks.items()}
            if first == second:
                kept = [layer for layer in a if layer["id"] in crop]
                if len(kept) < 2:
                    continue
                pieces = _components([crop[layer["id"]] for layer in kept], context.tolerance)
                main = max(pieces, key=lambda piece: sum(int(crop[kept[i]["id"]].sum()) for i in piece))
                body = np.any([crop[kept[i]["id"]] for i in main], axis=0)
                partners = [kept[i] for i in main]
                loose = [(kept[i], round(_gap(crop[kept[i]["id"]], body), 1), partners) for piece in pieces
                         if piece is not main for i in piece]
            else:
                loose = []
                for layer in a:
                    # A sided part joins the part on its own side when there is one (hand[left] to lower-arm[left]).
                    side = _side(layer)
                    mine = [other for other in b if other["id"] in crop and side and _side(other) == side]
                    mine = mine or [other for other in b if other["id"] in crop]
                    if layer["id"] not in crop or not mine:
                        continue
                    body = np.any([crop[other["id"]] for other in mine], axis=0)
                    if not touches(crop[layer["id"]], body, context.tolerance):
                        loose.append((layer, round(_gap(crop[layer["id"]], body), 1), mine))
            for layer, gap, partners in loose:
                key = (layer["id"], first, second)
                if key in reported:
                    continue
                reported.add(key)
                ink = _ink_box([masks[layer["id"]], *(masks[p["id"]] for p in partners)], context.region(subject, label))
                yield Finding("gap", f"{context.path(layer)} ↔ {_names(context, partners, second, subject)}: "
                              f"{gap:g} px gap{when}. A {subject.kind}'s {first} touches its {second}: overlap them a "
                              "few pixels (tuck the joint under)", [layer, *partners], "fix",
                              {"actual": gap, "expected": context.tolerance, "unit": "px"},
                              placement_hint(subject, first) or placement_hint(subject, second)
                              or f"move {first} onto {second} so their ink overlaps",
                              box=ink, extra={"gap": gap, "pair": [first, second], **({"frame": label} if label else {})})


def _names(context, layers, name, subject):
    paths = [context.path(layer) for layer in layers]
    return paths[0] if len(paths) == 1 else f"{subject.path}/{name} ({len(paths)} parts)"


def _region(masks, tolerance):
    if not masks:
        return None
    union_mask = np.any(masks, axis=0)
    rows, cols = np.any(union_mask, axis=1), np.any(union_mask, axis=0)
    if not rows.any():
        return None
    pad = int(math.ceil(tolerance)) + 1
    top, bottom = max(0, int(np.argmax(rows)) - pad), min(len(rows), len(rows) - int(np.argmax(rows[::-1])) + pad)
    left, right = max(0, int(np.argmax(cols)) - pad), min(len(cols), len(cols) - int(np.argmax(cols[::-1])) + pad)
    return left, top, right, bottom


def _ink_box(masks, region):
    """The canvas box around the ink of ``masks`` drawn over ``region``."""
    masks = [m for m in masks if m is not None and m.any()]
    if not masks:
        return None
    union_mask = np.any(masks, axis=0)
    rows, cols = np.flatnonzero(union_mask.any(axis=1)), np.flatnonzero(union_mask.any(axis=0))
    return [region[0] + int(cols[0]), region[1] + int(rows[0]), int(cols[-1] - cols[0] + 1),
            int(rows[-1] - rows[0] + 1)]


def proportions(context, subject):
    if subject.record.get("stylized") or subject.record.get("proportions") == "ignore":
        return
    whole = context.object_box(subject)
    for item in subject.fields.get("proportions", []):
        layers = [layer for layer in subject.present(item["part"]) if shown(layer, context.index)]
        if not layers:
            continue
        boxes = [context.frame_box(subject, layer) for layer in layers]
        reference = item.get("of", "height")
        if reference == "height":
            size, base, against = max(b[3] for b in boxes), whole[3], f"the {subject.kind}'s height"
            measure = "height"
        else:
            others = [layer for layer in subject.present(reference) if shown(layer, context.index)]
            if not others:
                continue
            size = max(max(b[2], b[3]) for b in boxes)
            base = max(max(b[2], b[3]) for b in (context.frame_box(subject, layer) for layer in others))
            against, measure = f"{subject.path}/{reference}", "length"
            layers = layers + others
        if base <= 0:
            continue
        ratio = size / base
        if item["min"] - 1e-6 <= ratio <= item["max"] + 1e-6:
            continue
        middle = (item["min"] + item["max"]) / 2
        note = f" ({item['note']})" if item.get("note") else ""
        yield Finding("proportion", f"{_label(subject, item['part'])} {measure} is {ratio:.2f} of {against}; a "
                      f"{subject.kind}'s is {item['min']:g}–{item['max']:g}{note}", layers, "review",
                      {"actual": round(ratio, 3), "expected": [item["min"], item["max"]], "unit": "ratio"},
                      f"scale {item['part']} toward {middle:.2f} of {'the height' if reference == 'height' else reference}, "
                      "or declare the object stylized: true if the exaggeration is deliberate",
                      extra={"part": item["part"]})


def symmetry(context, subject):
    if subject.fields.get("symmetry", "none") == "none":
        return
    for name in dict.fromkeys(_part_name(layer) for layer in subject.parts):
        layers = [layer for layer in subject.named.get(name, []) if shown(layer, context.index)]
        left = [layer for layer in layers if _side(layer) == "left"]
        right = [layer for layer in layers if _side(layer) == "right"]
        if not left or not right:
            continue
        axis = _axis(context, subject, name)

        def position(layer):
            x, y, w, h = context.frame_box(subject, layer)
            return y + h / 2, x + w / 2

        for a, b in zip(sorted(left, key=position), sorted(right, key=position)):
            if _depth(a) or _depth(b):
                continue  # a side view: perspective changes size and position
            ba, bb = context.frame_box(subject, a), context.frame_box(subject, b)
            sa, sb = math.sqrt(max(ba[2] * ba[3], 0)), math.sqrt(max(bb[2] * bb[3], 0))
            difference = abs(sa - sb) / max(sa, sb, 1e-9)
            if difference > SYMMETRY_TOLERANCE:
                yield Finding("symmetry-size", f"{context.path(a)} and {context.path(b)} differ in size by "
                              f"{difference:.0%}; mirrored parts of a {subject.kind} match within "
                              f"{SYMMETRY_TOLERANCE:.0%}", [a, b], "review",
                              {"actual": round(difference, 3), "expected": SYMMETRY_TOLERANCE, "unit": "ratio"},
                              "resize one to match the other, or flip a duplicate of it (flip horizontal)",
                              extra={"part": name})
            if axis is None:
                continue
            centre, partner = axis
            ends = [(box[0], box[0] + box[2]) for box in (ba, bb)]
            same = "left" if all(end <= centre + 0.5 for _, end in ends) else (
                "right" if all(start >= centre - 0.5 for start, _ in ends) else None)
            if same:
                yield Finding("symmetry-side", f"{context.path(a)} and {context.path(b)} both sit {same} of the centre "
                              f"of {partner}; a mirrored pair straddles it", [a, b], "review",
                              {"actual": same, "expected": "either side", "unit": "side"},
                              (placement_hint(subject, name) or f"mirror {name} about {partner}'s centre")
                              + "; in a side view mark the pair depth far and near instead",
                              extra={"part": name})


def _part_name(layer):
    from .objects import part_of

    return (part_of(layer) or {}).get("name")


def _depth(layer):
    return (layer.get("object_part") or {}).get("depth")


def _axis(context, subject, name):
    """(centre x in the object's frame, label) of what part ``name`` mirrors about: the part it connects to, else the
    object."""
    for pair in subject.fields.get("connections", []):
        if name in pair and pair[0] != pair[1]:
            other = pair[1] if pair[0] == name else pair[0]
            layers = [layer for layer in subject.present(other) if shown(layer, context.index)]
            if layers:
                x, _, w, _ = union([context.frame_box(subject, layer) for layer in layers])
                return x + w / 2, f"{subject.path}/{other}"
    x, _, w, _ = context.object_box(subject)
    return (x + w / 2, subject.path) if w > 0 else None


def hint_parts(subject, hint):
    """The part layers a layering hint names: a part ('body'), a plural ('windows'), a family ('limbs',
    'features'), optionally far or near ('far limbs': parts marked depth far)."""
    words = hint.casefold().split()
    depth = words.pop(0) if words and words[0] in ("far", "near") and len(words) > 1 else None
    if len(words) != 1:
        return []
    word = words[0]
    names = set(FAMILIES.get(word, ()))
    for candidate in (word, word[:-1] if word.endswith("s") else None, word[:-2] if word.endswith("es") else None,
                      word[:-3] + "f" if word.endswith("ves") else None):
        if candidate:
            names.add(candidate)
    layers = [layer for name in subject.named if name in names for layer in subject.named[name]]
    if depth:
        layers = [layer for layer in layers if _depth(layer) == depth]
    return layers


def layering(context, subject):
    order, seen, groups = context.order(), set(), []
    for hint in subject.fields.get("layering", []):
        layers = [layer for layer in hint_parts(subject, hint)
                  if layer["id"] not in seen and shown(layer, context.index) and layer["id"] in order]
        seen |= {layer["id"] for layer in layers}
        if layers:
            groups.append((hint, layers))
    pairs = []
    for i, (back_hint, backs) in enumerate(groups):
        for front_hint, fronts in groups[i + 1:]:
            for back in backs:
                for front in fronts:
                    if order[back["id"]] > order[front["id"]] and not _nested(context, back, front) \
                            and _overlap(context, subject, back, front):
                        pairs.append((back, back_hint, front, front_hint))
    while pairs:
        counts = {}
        for back, _, front, _ in pairs:
            counts[back["id"]] = counts.get(back["id"], 0) + 1
            counts[front["id"]] = counts.get(front["id"], 0) + 1
        worst = max(counts, key=lambda ident: (counts[ident], order[ident]))
        mine = [pair for pair in pairs if worst in (pair[0]["id"], pair[2]["id"])]
        pairs = [pair for pair in pairs if pair not in mine]
        layer = context.index[worst]
        behind = [pair for pair in mine if pair[0]["id"] == worst]
        if behind:
            hint = behind[0][1]
            others = [pair[2] for pair in behind]
            message = (f"{context.path(layer)} ({hint}) draws over {_list(context, others)}; a {subject.kind} layers "
                       f"{hint} behind {behind[0][3]}")
            fix = f"lower {context.path(layer)} behind {context.path(others[0])} (lower or bottom with a target)"
            actual = [context.path(other) for other in others] + [context.path(layer)]
        else:
            hint = mine[0][3]
            others = [pair[0] for pair in mine]
            message = (f"{context.path(layer)} ({hint}) draws under {_list(context, others)}; a {subject.kind} layers "
                       f"{hint} in front of {mine[0][1]}")
            fix = f"raise {context.path(layer)} above {context.path(others[0])} (raise or top with a target)"
            actual = [context.path(layer)] + [context.path(other) for other in others]
        yield Finding("layering", message, [layer, *others], "review",
                      {"actual": actual, "expected": [h for h, _ in groups], "unit": "back to front"}, fix,
                      extra={"part": _part_name(layer)})


def _list(context, layers):
    names = [context.path(layer) for layer in layers]
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _nested(context, a, b):
    for inner, outer in ((a, b), (b, a)):
        item = context.index.get(inner.get("parent"))
        while item is not None:
            if item["id"] == outer["id"]:
                return True
            item = context.index.get(item.get("parent"))
    return False


def _overlap(context, subject, a, b):
    ma, mb = context.mask(subject, a), context.mask(subject, b)
    if ma is not None and mb is not None:
        return bool((ma & mb).any())
    return False


def outline(context, subject):
    """The outline policy's findings (``object_outline.findings``): seams, uneven part outlines, a stale outline."""
    from .object_outline import findings

    yield from findings(context, subject)


FINDERS = [parts, connections, proportions, symmetry, layering, outline]


# ---------------------------------------------------------------------------------------------------------------
# Running the check


def declared(project):
    """The groups the check measures: every object with its own record (a character without one is checked by
    the ``character`` check)."""
    from .objects import all_objects

    return [layer for layer in all_objects(project) if layer.get("object")]


def subjects(project, kinds, targets=None):
    from .objects import _children, merged, object_parts, part_of, path_of, sub_objects

    layers = project.state["layers"]
    index = {item["id"]: item for item in layers}
    children = _children(layers)
    wanted = {project.layer(t)["id"] for t in targets} if targets else None
    found = []
    for group in declared(project):
        kind = group["object"]["kind"]
        if kind not in kinds or (wanted is not None and not _selected(group, wanted, index, project)):
            continue
        owned = object_parts(project, group, children)
        subject = Subject(group, kind, path_of(project, group, index) or group["name"], merged(kind, kinds),
                          group["object"], owned, sub_objects(project, group, children))
        for layer in owned:
            subject.named.setdefault(part_of(layer)["name"], []).append(layer)
        found.append(subject)
    return found


def _selected(group, wanted, index, project):
    from .design import descendants

    item = group
    while item:
        if item["id"] in wanted:
            return True
        item = index.get(item.get("parent"))
    return bool(wanted & descendants(project, group["id"]))


def frames_of(project):
    """``[(label, frame)]``: the document itself, or the frames the ``connected`` check samples on a timeline."""
    timeline = project.state.get("timeline")
    if timeline and timeline.get("tracks"):
        from .timeline import project_at, sample_frame_times

        return [(label, project_at(project, time)) for label, time in sample_frame_times(timeline)]
    return [(None, project)]


def check(project, issue, *, tolerance=2, targets=None, resolved=None, local=None):
    """Report every finding of every ``FINDERS`` entry for each declared object (``issue`` as in ``check_design``;
    ``resolved`` and ``local`` are its resolved layers and layout when it has them). Returns the IDs of the object
    groups measured."""
    from .model import finite
    from .objects import registry

    tolerance = finite(tolerance, "connect_tolerance", 0, 100)
    kinds = registry(getattr(project, "_workspace", None))
    found = subjects(project, kinds, targets)
    if not found:
        return set()
    context = Context(project, resolved, kinds, tolerance, frames_of(project), local)
    for subject in found:
        if subject.group["id"] not in context.index or not shown(context.index[subject.group["id"]], context.index):
            continue
        # The part records live on the document's layers; measurements use the resolved ones.
        subject.parts = [context.index.get(layer["id"], layer) for layer in subject.parts]
        subject.subs = [context.index.get(layer["id"], layer) for layer in subject.subs]
        subject.named = {name: [context.index.get(layer["id"], layer) for layer in layers]
                         for name, layers in subject.named.items()}
        for finder in FINDERS:
            for finding in finder(context, subject):
                layers = [context.resolved.get(layer["id"], layer) for layer in finding.layers]
                box = finding.box or context.box(finding.layers)
                issue("object", "warning", finding.message, layers, code=finding.code, action=finding.action,
                      object=subject.path, kind=subject.kind, **({"box": box} if box else {}),
                      **({"measured": finding.measured} if finding.measured is not None else {}),
                      **({"hint": finding.hint} if finding.hint else {}), **finding.extra)
    return {subject.group["id"] for subject in found}
