"""Proportional re-layout of a document at another size: ``adapt-layout`` without ``targets``.

``adapt-layout`` resizes the canvas (to a named size or a width and height) and re-lays out each
top-level layer by simple anchoring rules, then reports where every layer went:

* sizes scale uniformly (``scale``: ``fit`` keeps everything inside, ``fill`` covers, ``width`` or
  ``height`` follows one axis, or a number); text scales its font size and wrapping boxes;
* each axis is anchored from the layer's place in the old canvas: near an edge it keeps its
  margin (scaled), near the middle it keeps its relative position, and a layer that spans the
  canvas stretches with it. Only backgrounds and plain bands (solids, gradients, rectangles, lines)
  stretch: other decoration that spans one axis (a wave, a pattern strip) is scaled uniformly to span it,
  and a full-canvas photo or artwork is scaled to cover instead of being distorted;
* layers that sit together (a rule under its headline, a stack of lines) move as one unit, so their
  arrangement survives (``together``);
* content keeps out of the target size's safe area (``safe``: per-side insets such as a story's top and
  bottom 250 px), and text never shrinks below ``min_text``; text tagged ``optional`` that would is hidden;
* ``anchors`` overrides the inferred choice per layer name, role, kind or tag; layers that
  already have constraints keep them (numeric values and canvas offsets are scaled), so
  constraint-driven layouts stay constraint-driven.

``adapt_copies`` applies the same operation to copies of a document for several sizes at once.
"""

import difflib
import re

from .errors import VixlError, require
from .geometry import ANCHORS as BOX_ANCHORS, canonical_anchor
from .selectors import matcher, parse_where, record

SCALES = ("fit", "fill", "width", "height")
_MODE = {0: "start", 0.5: "center", 1: "end"}
ANCHORS = {
    **{name: (_MODE[fx], _MODE[fy]) for name, (fx, fy) in BOX_ANCHORS.items()},
    "stretch": ("stretch", "stretch"), "stretch-x": ("stretch", None), "stretch-y": (None, "stretch"),
    "keep": ("keep", "keep"), "cover": ("cover", "cover"),
}
NAMES = {0: {"start": "left", "center": "center-x", "end": "right", "stretch": "stretch-x", "span": "span-x"},
         1: {"start": "top", "center": "center-y", "end": "bottom", "stretch": "stretch-y", "span": "span-y"}}
# Layers that may stretch along one axis without looking distorted.
STRETCHABLE_SHAPES = ("rectangle", "rounded-rectangle", "line")
TOGETHER = 0.06  # Layers this close (a fraction of the old canvas's short side) move as one unit.
SPAN = 0.9  # A layer this large along an axis is treated as spanning it.
MAX_REPORTED = 60
OPTIONS = ("size", "width", "height", "orientation", "dpi", "bleed", "scale", "anchors", "where", "text", "report", "recompose",
           "safe", "min_text", "together")

SCHEMA = {
    "recompose": {"type": "boolean", "description": "Reapply a stored generated-layout recipe for this size (default false); replaces generated layer edits and IDs."},
    "size": {"type": "string", "description": "Named target size (vixl_sizes_list), e.g. story or a4; or give width "
             "and height."},
    "orientation": {"enum": ["portrait", "landscape"], "description": "With a named size."},
    "dpi": {"type": "number", "minimum": 36, "maximum": 2400, "description": "With a named print size."},
    "bleed": {"type": ["boolean", "number"], "description": "With a named print size."},
    "mode": {"enum": ["stack", "proportional"], "description": "stack (the default with targets): reflow the targets "
             "vertically and refuse what cannot fit. proportional (the default without targets): resize the canvas "
             "and re-lay out every layer by anchoring rules; the result lists where each layer went."},
    "scale": {"type": ["string", "number"], "description": "proportional: how sizes follow the canvas. fit (default) "
              "keeps everything inside, fill covers, width or height follow one axis, a number is a factor."},
    "anchors": {"type": "object", "description": "proportional: overrides the inferred anchor, {layer name glob | "
                "role:NAME | kind:TYPE | tag:NAME: top-left|top|top-right|left|center|right|bottom-left|bottom|"
                "bottom-right|stretch|stretch-x|stretch-y|keep|cover}. The first matching entry wins."},
    "where": {"type": "object", "description": "proportional: only layers matching this edit-layers selector are "
              "adapted; the others keep their place and size."},
    "text": {"enum": ["scale", "keep"], "description": "proportional: scale font sizes with the layout (default) or "
             "keep them."},
    "report": {"type": "boolean", "description": "proportional: list where each layer moved (default true)."},
    "safe": {"type": "boolean", "description": "proportional: keep content inside the new canvas's safe area (default "
             "true), e.g. out of a story's top and bottom 250 px."},
    "min_text": {"type": "number", "minimum": 0, "maximum": 400, "description": "proportional: smallest font size text "
                 "is scaled to, in pixels (default 1.2% of the new canvas's short side, at least 12; 0 turns it off). "
                 "Text tagged optional (layer-intent tags) that would fall below it is hidden instead."},
    "together": {"type": "boolean", "description": "proportional: move layers that sit together (a rule under its "
                 "headline, stacked lines) as one unit (default true)."},
}


def _anchor(value):
    return canonical_anchor(value) or value


def check_options(op):
    """Validate the proportional-mode fields; errors say what to change."""
    require(("size" in op) != ("width" in op or "height" in op),
            "Give a named size, or width and height, as the new canvas", field="size")
    require(("width" in op) == ("height" in op), "Give both width and height", field="width")
    scale = op.get("scale", "fit")
    require(scale in SCALES or (isinstance(scale, (int, float)) and not isinstance(scale, bool) and 0.01 <= scale <= 100),
            f"scale is one of {', '.join(SCALES)} or a number between 0.01 and 100", field="scale")
    require(op.get("text", "scale") in ("scale", "keep"), "text is scale or keep", field="text")
    for key in ("safe", "together"):
        require(type(op.get(key, True)) is bool, f"{key} must be true or false", field=key)
    if "min_text" in op:
        require(isinstance(op["min_text"], (int, float)) and not isinstance(op["min_text"], bool)
                and 0 <= op["min_text"] <= 400, "min_text is a font size in pixels from 0 to 400", field="min_text")
    anchors = op.get("anchors", {})
    require(isinstance(anchors, dict) and len(anchors) <= 100, "anchors is an object of up to 100 entries",
            field="anchors")
    for key, value in anchors.items():
        if _anchor(value) not in ANCHORS:
            close = difflib.get_close_matches(str(value), list(ANCHORS), 1, 0.5)
            raise VixlError("invalid_operation", f"anchors[{key!r}]: unknown anchor {value!r}; anchors: "
                            + ", ".join(ANCHORS) + (f". Did you mean {close[0]!r}?" if close else ""),
                            field="anchors", allowed=list(ANCHORS), suggestions=close)


def anchor_rules(project, anchors):
    """[(layer predicate, (x mode, y mode))] in the order given."""
    rules = []
    for key, value in anchors.items():
        prefix, _, rest = key.partition(":")
        where = {prefix: rest} if rest and prefix in ("role", "kind", "tag") else {"name": key}
        rules.append((matcher(project, parse_where(where)), ANCHORS[_anchor(value)]))
    return rules


def infer(start, size, length):
    """The anchor along one axis from where the layer sits in the old canvas."""
    if size >= SPAN * length:
        return "stretch"
    centre = (start + size / 2) / length
    return "start" if centre < 1 / 3 else "end" if centre > 2 / 3 else "center"


def stretchable(layer):
    """Backgrounds and plain bands stretch without looking distorted; other artwork does not."""
    return (layer["type"] in ("solid", "gradient", "adjustment") or layer.get("role") == "background"
            or (layer["type"] == "shape" and layer.get("shape") in STRETCHABLE_SHAPES))


def plan_layer(layer, box, explicit, old, new, s):
    """Anchors and the new visible size of one layer."""
    x, y, w, h = box
    old_w, old_h = old
    new_w, new_h = new
    ax, ay = explicit or (None, None)
    ax, ay = ax or infer(x, w, old_w), ay or infer(y, h, old_h)
    spans = w >= SPAN * old_w and h >= SPAN * old_h
    if explicit is None and layer["type"] in ("raster", "frame") and spans:
        ax = ay = "cover"
    if "cover" in (ax, ay):
        ax = ay = "cover"
    if "stretch" in (ax, ay) and explicit is None and (
        layer["type"] == "group" or layer.get("rotation", 0) % 360 or (layer["type"] == "text" and layer.get("auto_size", True))
    ):
        # Groups, rotated layers and auto-sized text are never distorted.
        ax = "center" if ax == "stretch" else ax
        ay = "center" if ay == "stretch" else ay
    if "keep" in (ax, ay):
        return {"anchor": ("keep", "keep"), "size": [w, h], "explicit": True}
    if explicit is None and "stretch" in (ax, ay) and not stretchable(layer):
        if ax == ay == "stretch":
            ax = ay = "cover"
        else:
            # Decoration spanning one axis (a wave, a strip of pattern) keeps its proportions: it is scaled
            # uniformly to span that axis of the new canvas, instead of being stretched.
            axis = 0 if ax == "stretch" else 1
            start, extent, length, new_length = ((x, w, old_w, new_w), (y, h, old_h, new_h))[axis]
            k = max(1e-6, new_length - start * s - (length - start - extent) * s) / max(1e-6, extent)
            other = infer((x, y)[1 - axis], (w, h)[1 - axis], (old_w, old_h)[1 - axis])
            other = "center" if other == "stretch" else other
            modes = ["span", other] if axis == 0 else [other, "span"]
            return {"anchor": tuple(modes), "size": [max(1, round(w * k)), max(1, round(h * k))], "explicit": False,
                    "scale": k}
    size = [max(1, round(w * s)), max(1, round(h * s))]
    if ax == "cover":
        k = max(new_w / w, new_h / h)
        size = [max(1, round(w * k)), max(1, round(h * k))]
    for axis, (mode, start, extent, length, new_length) in enumerate(((ax, x, w, old_w, new_w), (ay, y, h, old_h, new_h))):
        if mode == "stretch":
            size[axis] = max(1, round(new_length - start * s - (length - start - extent) * s))
    return {"anchor": (ax, ay), "size": size, "explicit": explicit is not None}


def new_start(mode, start, size, length, new_length, new_size, s, ratio, explicit):
    """Where a layer starts along one axis for its anchor."""
    if mode in ("start", "stretch", "span"):
        return start * s
    if mode == "end":
        return new_length - (length - start - size) * s - new_size
    middle = start + size / 2
    if mode == "cover":
        return min(0, max(new_length - new_size, middle * ratio - new_size / 2))
    # center: an explicit anchor keeps the (scaled) offset from the middle; an inferred one keeps the relative place.
    return (new_length / 2 + (middle - length / 2) * s if explicit else middle * ratio) - new_size / 2


def scale_constraint(expression, s, ratio):
    """A constraint for the new canvas: absolute numbers follow the axis, canvas offsets follow the scale."""
    if isinstance(expression, (int, float)):
        return expression * ratio
    match = re.fullmatch(r"(canvas\.[a-z-]+)([+-]\d+(?:\.\d+)?)?", expression)
    if match and match[2]:
        return f"{match[1]}{float(match[2]) * s:+g}"
    return expression  # Relative to another layer or a guide: it follows that reference.


def execute(project, op):
    from .operations import execute as apply_operation
    from .render import resolve_layout, stored_origin

    state = project.state
    check_options(op)
    require(not state.get("pages"), "adapt-layout does not support multi-page documents yet; use a document per "
            "page or the canvas operation", field="mode")
    old_w, old_h = state["canvas"]["width"], state["canvas"]["height"]
    before = resolve_layout(project)
    top = [layer for layer in state["layers"] if not layer.get("parent")]
    chosen = None
    if "where" in op:
        accepts = matcher(project, parse_where(op["where"]))
        chosen = {layer["id"] for layer in top if accepts(layer)}
    rules = anchor_rules(project, op.get("anchors", {}))
    apply_operation(project, {"type": "canvas", **{k: op[k] for k in ("size", "width", "height", "orientation", "dpi", "bleed")
                                                   if k in op}})
    if op.get("recompose"):
        from copy import deepcopy
        from .layouts import execute_layout
        from .schema import validate_operation

        recipe = deepcopy((state.get("layout") or {}).get("recipe"))
        require(recipe, "This document has no saved layout recipe; reapply layout-apply first", field="recompose")
        recipe.update(type="layout-apply", replace=True)
        # A target-specific size is derived afresh unless the recipe explicitly pinned it.
        execute_layout(project, validate_operation(recipe))
        record(project, "adapt_layout", {"mode": "recompose", "layout": recipe["name"],
                                         "from": [old_w, old_h],
                                         "to": [project.state["canvas"]["width"], project.state["canvas"]["height"]]})
        return
    new_w, new_h = state["canvas"]["width"], state["canvas"]["height"]
    rx, ry = new_w / old_w, new_h / old_h
    scale = op.get("scale", "fit")
    s = float({"fit": min(rx, ry), "fill": max(rx, ry), "width": rx, "height": ry}.get(scale, scale))
    keep_text = op.get("text", "scale") == "keep"
    short = min(new_w, new_h)
    min_text = op.get("min_text", max(12, round(short * 0.012)))
    plans, skipped, dropped = {}, [], []

    # Phase 1: sizes. Text re-measures itself; a wrapping box keeps wrapping inside its scaled box.
    for layer in top:
        if chosen is not None and layer["id"] not in chosen:
            continue
        if layer["type"] in ("pixel", "field"):
            skipped.append({"layer": layer["name"], "reason": f"{layer['type']} layers keep their size"})
            continue
        explicit = next((modes for accepts, modes in rules if accepts(layer)), None)
        plan = plans[layer["id"]] = plan_layer(layer, before[layer["id"]], explicit, (old_w, old_h), (new_w, new_h), s)
        if plan["anchor"][0] == "keep":
            continue
        ident, size = layer["id"], plan["size"]
        if layer["type"] == "text":
            if not keep_text:
                scaled = min(4096, max(1, round(layer["size"] * s)))
                if min_text and scaled < min(min_text, layer["size"]):
                    if "optional" in layer.get("tags", []) and layer["visible"]:
                        # An optional line too small to read is left out rather than set at 3 px.
                        layer["visible"] = False
                        dropped.append(layer["name"])
                        plans.pop(ident)
                        continue
                    scaled = min(min_text, layer["size"])
                apply_operation(project, {"type": "text-set", "target": ident, "size": scaled})
            box = layer.get("text_layout") or {}
            if "width" in box or "height" in box or not layer.get("auto_size", True):
                apply_operation(project, {"type": "text-layout", "target": ident, **box, "width": size[0], "height": size[1]})
        else:
            # The stored box is unrotated: scale it by the factor the visible box changed by.
            width, height = before[ident][2:]
            apply_operation(project, {"type": "resize", "target": ident,
                                      "width": max(1, round(layer["width"] * size[0] / max(1, width))),
                                      "height": max(1, round(layer["height"] * size[1] / max(1, height)))})

    # Phase 2: positions, from the sizes the layers ended up with.
    sized = resolve_layout(project)
    placed = {}
    for layer in top:
        plan = plans.get(layer["id"])
        if plan is None or plan["anchor"][0] == "keep":
            continue
        x, y, w, h = before[layer["id"]]
        origin = list(sized[layer["id"]][:2])
        free = [True, True]
        for axis, (start, extent, length, new_length, ratio) in enumerate(((x, w, old_w, new_w, rx), (y, h, old_h, new_h, ry))):
            names = (("left", "right", "center-x"), ("top", "bottom", "center-y"))[axis]
            constrained = [name for name in layer.get("constraints", {}) if name in names]
            for name in constrained:
                layer["constraints"][name] = scale_constraint(layer["constraints"][name], s, ratio)
            if constrained:
                free[axis] = False
            else:
                origin[axis] = new_start(plan["anchor"][axis], start, extent, length, new_length,
                                         sized[layer["id"]][2 + axis], s, ratio, plan["explicit"])
        placed[layer["id"]] = (origin, free)

    # Units: layers that sat together move together; each unit then keeps inside the safe area.
    units = movable_units(project, top, plans, before, placed, (old_w, old_h), op.get("together", True))
    together = []
    for unit in units:
        if len(unit) > 1:
            together.append([project.layer(ident)["name"] for ident in unit])
            box = union([before[ident] for ident in unit])
            new_extent = [max((before[i][axis] - box[axis]) * s + sized[i][2 + axis] for i in unit) for axis in (0, 1)]
            anchor = [infer(box[0], box[2], old_w), infer(box[1], box[3], old_h)]
            anchor = ["center" if mode == "stretch" else mode for mode in anchor]
            corner = [new_start(anchor[axis], box[axis], box[2 + axis], (old_w, old_h)[axis], (new_w, new_h)[axis],
                                new_extent[axis], s, (rx, ry)[axis], False) for axis in (0, 1)]
            for ident in unit:
                origin, free = placed[ident]
                for axis in (0, 1):
                    if free[axis]:
                        origin[axis] = corner[axis] + (before[ident][axis] - box[axis]) * s
    for ident, (origin, _) in placed.items():
        layer = project.layer(ident)
        layer["x"], layer["y"] = stored_origin(layer, (round(origin[0]), round(origin[1])))
    shifted = []
    if op.get("safe", True):
        shifted = keep_safe(project, units, placed)

    if op.get("report", True):
        after = resolve_layout(project)
        moved = []
        for layer in top:
            plan = plans.get(layer["id"])
            if plan is None:
                continue
            row = {"layer": layer["name"], "from": list(before[layer["id"]]), "to": list(after[layer["id"]]),
                   "anchor": plan["anchor"][0] if plan["anchor"][0] in ("cover", "keep")
                   else ", ".join(NAMES[i].get(m, m) for i, m in enumerate(plan["anchor"]))}
            if layer["type"] == "text" and not keep_text:
                row["font_size"] = layer["size"]
            if row["from"] != row["to"]:
                moved.append(row)
        record(project, "adapt_layout", {
            "canvas": {"from": [old_w, old_h], "to": [new_w, new_h]}, "scale": round(s, 4),
            "adapted": len(plans), "moved": len(moved), "layers": moved[:MAX_REPORTED],
            **({"more": len(moved) - MAX_REPORTED} if len(moved) > MAX_REPORTED else {}),
            **({"skipped": skipped} if skipped else {}),
            **({"together": together} if together else {}),
            **({"kept_safe": shifted} if shifted else {}),
            **({"dropped": dropped} if dropped else {}),
            **({"min_text": min_text} if min_text and not keep_text else {}),
        })
    elif skipped:
        record(project, "warnings", f"adapt-layout left {len(skipped)} layer(s) at their size: "
               + ", ".join(item["layer"] for item in skipped))


def union(boxes):
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def content(layer, plan):
    """True for a layer that is content: positioned by its own anchors, not a background, band or cover."""
    return (plan is not None and not plan["explicit"] and layer.get("role") not in ("background",)
            and not set(plan["anchor"]) & {"stretch", "cover", "span", "keep"})


def movable_units(project, top, plans, before, placed, old, together=True):
    """Lists of layer IDs that move and keep safe as one: content layers whose boxes sat within a small gap of
    each other, side by side or one above the other (a rule under its headline, lines of a stack)."""
    members = [layer["id"] for layer in top if layer["id"] in placed and content(layer, plans.get(layer["id"]))]
    parent = {ident: ident for ident in members}

    def find(ident):
        while parent[ident] != ident:
            parent[ident] = parent[parent[ident]]
            ident = parent[ident]
        return ident

    if together:
        gap = TOGETHER * min(old)
        for i, a in enumerate(members):
            ax, ay, aw, ah = before[a]
            for b in members[i + 1:]:
                bx, by, bw, bh = before[b]
                dx = max(0.0, max(ax, bx) - min(ax + aw, bx + bw))
                dy = max(0.0, max(ay, by) - min(ay + ah, by + bh))
                if (dx == 0 and dy <= gap) or (dy == 0 and dx <= gap):
                    parent[find(a)] = find(b)
    units = {}
    for ident in members:
        units.setdefault(find(ident), []).append(ident)
    return list(units.values())


def keep_safe(project, units, placed):
    """Shift each unit inside the canvas's safe area (``sizes.safe_sides`` plus bleed); returns the names moved."""
    from .render import resolve_layout
    from .sizes import safe_sides

    canvas = project.state["canvas"]
    bleed = canvas.get("bleed", 0)
    left, top, right, bottom = (bleed + side for side in safe_sides(canvas))
    if not any((left, top, right, bottom)):
        return []
    width, height = canvas["width"], canvas["height"]
    boxes = resolve_layout(project)
    moved = []
    for unit in units:
        if not all(ident in placed for ident in unit):
            continue
        x, y, w, h = union([boxes[ident] for ident in unit])
        shift = []
        for start, extent, low, high in ((x, w, left, width - right), (y, h, top, height - bottom)):
            if extent > high - low:
                shift.append(low - start if start < low else 0)  # too big to fit: start at the safe edge
            elif start < low:
                shift.append(low - start)
            elif start + extent > high:
                shift.append(high - (start + extent))
            else:
                shift.append(0)
        if any(round(v) for v in shift):
            for ident in unit:
                layer = project.layer(ident)
                layer["x"] += round(shift[0])
                layer["y"] += round(shift[1])
                moved.append(layer["name"])
    return moved


def size_spec(entry, index):
    """One ``sizes`` entry as adapt-layout fields: a named size, 'WxH', or an object."""
    where = f"sizes[{index}]"
    if isinstance(entry, str):
        match = re.fullmatch(r"(\d+)\s*[x×]\s*(\d+)", entry.strip())
        return {"width": int(match[1]), "height": int(match[2])} if match else {"size": entry.strip()}
    require(isinstance(entry, dict) and entry, f"{where} is a named size, 'WIDTHxHEIGHT' or an object", field=where)
    unknown = sorted(set(entry) - {"size", "width", "height", "orientation", "dpi", "bleed", "name"})
    require(not unknown, f"{where}: unknown field(s) {', '.join(unknown)}; use size or width+height, orientation, "
            "dpi, bleed, name", field=where)
    return dict(entry)


def adapt_copies(session, export_file, sizes, directory=".", name="{name}-{size}", options=None, document=None,
                 overwrite=False, formats=None, report="summary"):
    """Copy a document once per size, adapt each copy with ``adapt-layout`` and save it (and optionally
    export it): one call for a whole campaign. The source document is never changed."""
    from pathlib import Path

    from . import calls
    from .interfaces import service_check

    require(isinstance(sizes, list) and 0 < len(sizes) <= 16, "Give 1–16 sizes", field="sizes")
    require(report in ("summary", "layers"), "report is summary or layers", field="report")
    options = dict(options or {})
    bad = sorted(set(options) - {"scale", "anchors", "where", "text", "recompose", "safe", "min_text", "together"})
    require(not bad, f"options accepts scale, anchors, where, text, recompose, safe, min_text and together; got "
            f"{', '.join(bad)}", field="options")
    formats = [f.lower().lstrip(".") for f in (formats or [])]
    require(all(re.fullmatch(r"png|jpg|jpeg|webp|tif|tiff|avif|svg|pdf", f) for f in formats),
            "formats are png, jpg, webp, tiff, avif, svg or pdf", field="formats")
    folder = session.resolve(directory)
    with session.project(document=document) as source:
        base = source.clone()
        source_path = Path(source.path)
    base.path, base._revision = None, None
    plan = []
    for index, entry in enumerate(sizes):
        spec = size_spec(entry, index)
        label = spec.pop("name", None) or spec.get("size") or f"{spec['width']}x{spec['height']}"
        require(re.fullmatch(r"[\w.-]+", label), f"sizes[{index}]: name {label!r} may use letters, digits, _ . -",
                field=f"sizes[{index}]")
        stem = name.format(name=source_path.stem, size=label, index=index + 1,
                           **{k: spec.get(k, "") for k in ("width", "height")})
        require(re.fullmatch(r"[\w.@-]+", stem), f"name template gives {stem!r}; use letters, digits, _ . - @",
                field="name")
        destination = folder / (stem + ".vixl")
        require(destination != source_path, f"sizes[{index}] would overwrite the source document", field="name")
        require(overwrite or not destination.exists(),
                f"{session.relative(destination)} already exists; set overwrite=true or change name", field="name")
        plan.append((spec, label, destination))
    require(len({d for _, _, d in plan}) == len(plan),
            "Two sizes give the same file name; use {size} or {index} in name", field="name")
    results = []
    for index, (spec, label, destination) in enumerate(plan):
        calls.check_cancelled()
        candidate = base.clone()
        outcome = candidate.apply([{"type": "adapt-layout", **spec, **options}], detail="brief", check=service_check)
        report_row = outcome["adapt_layout"][0]
        session.make_parent(destination)
        candidate.save(destination, overwrite=overwrite)
        item = {"size": label, "path": session.relative(destination), "canvas": report_row["canvas"]["to"],
                "scale": report_row["scale"], "moved": report_row["moved"]}
        if report == "layers":
            item["layers"] = report_row["layers"]
        if outcome.get("warnings"):
            item["warnings"] = outcome["warnings"]
        if formats:
            item["exports"] = [
                export_file(session, session.relative(destination.with_suffix("." + f)), overwrite,
                            session.relative(destination), **({"alpha": "auto"} if f in ("png", "webp") else {}))
                for f in formats
            ]
        results.append(item)
        calls.progress(index + 1, len(plan), label)
    return {"source": session.relative(source_path), "count": len(results), "documents": results}
