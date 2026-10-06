"""Proportional re-layout of a document at another size: ``adapt-layout`` without ``targets``.

Resizing a canvas used to leave every layer where it was. ``adapt-layout`` resizes the canvas (to a
named size or a width and height) and re-lays out each top-level layer by simple anchoring rules,
then reports where every layer went:

* sizes scale uniformly (``scale``: ``fit`` keeps everything inside, ``fill`` covers, ``width`` or
  ``height`` follows one axis, or a number); text scales its font size and wrapping boxes;
* each axis is anchored from the layer's place in the old canvas: near an edge it keeps its
  margin (scaled), near the middle it keeps its relative position, and a layer that spans the
  canvas stretches with it (a full-canvas photo is scaled to cover instead of being distorted);
* ``anchors`` overrides the inferred choice per layer name, role, kind or tag; layers that
  already have constraints keep them (numeric values and canvas offsets are scaled), so
  constraint-driven layouts stay constraint-driven.

``adapt_copies`` applies the same operation to copies of a document for several sizes at once.
"""

import difflib
import re

from .errors import VixlError, require
from .selectors import matcher, parse_where, record

SCALES = ("fit", "fill", "width", "height")
ANCHORS = {
    "top-left": ("start", "start"), "top": ("center", "start"), "top-right": ("end", "start"),
    "left": ("start", "center"), "center": ("center", "center"), "right": ("end", "center"),
    "bottom-left": ("start", "end"), "bottom": ("center", "end"), "bottom-right": ("end", "end"),
    "stretch": ("stretch", "stretch"), "stretch-x": ("stretch", None), "stretch-y": (None, "stretch"),
    "keep": ("keep", "keep"), "cover": ("cover", "cover"),
}
NAMES = {0: {"start": "left", "center": "center-x", "end": "right", "stretch": "stretch-x"},
         1: {"start": "top", "center": "center-y", "end": "bottom", "stretch": "stretch-y"}}
SPAN = 0.9  # A layer this large along an axis is treated as spanning it.
MAX_REPORTED = 60
OPTIONS = ("size", "width", "height", "orientation", "dpi", "bleed", "scale", "anchors", "where", "text", "report")

SCHEMA = {
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
}


def check_options(op):
    """Validate the proportional-mode fields; errors say what to change."""
    require(("size" in op) != ("width" in op or "height" in op),
            "Give a named size, or width and height, as the new canvas", field="size")
    require(("width" in op) == ("height" in op), "Give both width and height", field="width")
    scale = op.get("scale", "fit")
    require(scale in SCALES or (isinstance(scale, (int, float)) and not isinstance(scale, bool) and 0.01 <= scale <= 100),
            f"scale is one of {', '.join(SCALES)} or a number between 0.01 and 100", field="scale")
    require(op.get("text", "scale") in ("scale", "keep"), "text is scale or keep", field="text")
    anchors = op.get("anchors", {})
    require(isinstance(anchors, dict) and len(anchors) <= 100, "anchors is an object of up to 100 entries",
            field="anchors")
    for key, value in anchors.items():
        if value not in ANCHORS:
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
        rules.append((matcher(project, parse_where(where)), ANCHORS[value]))
    return rules


def infer(start, size, length):
    """The anchor along one axis from where the layer sits in the old canvas."""
    if size >= SPAN * length:
        return "stretch"
    centre = (start + size / 2) / length
    return "start" if centre < 1 / 3 else "end" if centre > 2 / 3 else "center"


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
    if mode in ("start", "stretch"):
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
    new_w, new_h = state["canvas"]["width"], state["canvas"]["height"]
    rx, ry = new_w / old_w, new_h / old_h
    scale = op.get("scale", "fit")
    s = float({"fit": min(rx, ry), "fill": max(rx, ry), "width": rx, "height": ry}.get(scale, scale))
    keep_text = op.get("text", "scale") == "keep"
    plans, skipped = {}, []

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
                apply_operation(project, {"type": "text-set", "target": ident,
                                          "size": min(4096, max(1, round(layer["size"] * s)))})
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
    for layer in top:
        plan = plans.get(layer["id"])
        if plan is None or plan["anchor"][0] == "keep":
            continue
        x, y, w, h = before[layer["id"]]
        origin = list(sized[layer["id"]][:2])
        for axis, (start, extent, length, new_length, ratio) in enumerate(((x, w, old_w, new_w, rx), (y, h, old_h, new_h, ry))):
            names = (("left", "right", "center-x"), ("top", "bottom", "center-y"))[axis]
            constrained = [name for name in layer.get("constraints", {}) if name in names]
            for name in constrained:
                layer["constraints"][name] = scale_constraint(layer["constraints"][name], s, ratio)
            if not constrained:
                origin[axis] = new_start(plan["anchor"][axis], start, extent, length, new_length,
                                         sized[layer["id"]][2 + axis], s, ratio, plan["explicit"])
        layer["x"], layer["y"] = stored_origin(layer, (round(origin[0]), round(origin[1])))

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
        })
    elif skipped:
        record(project, "warnings", f"adapt-layout left {len(skipped)} layer(s) at their size: "
               + ", ".join(item["layer"] for item in skipped))


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
    bad = sorted(set(options) - {"scale", "anchors", "where", "text"})
    require(not bad, f"options accepts scale, anchors, where and text; got {', '.join(bad)}", field="options")
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
        candidate.save(destination)
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
