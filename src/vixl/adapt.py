"""Re-layout of a document at another size: ``adapt-layout`` without ``targets``.

``adapt-layout`` resizes the canvas (to a named size or a width and height) and re-composes the document there,
in one of three ways, and says which under ``recomposed`` and ``reason``:

* **recipe**: a document built by ``layout-apply`` is rebuilt from its stored recipe at the new size. This is the
  default when nothing has been edited since the layout was applied (the layout record keeps a fingerprint of the
  layers it made); ``recompose: true`` forces it, ``recompose: false`` never does it.
* **arrangements**: ``arrangements`` (stack-vertical, side-by-side, hero-top, proportional) re-place the content of
  any document: each candidate is built, scored with the composition, legibility, bounds and overlap checks, and
  the best one kept. ``outcome`` (``outcomes.make``) says whether it passed; when none did it needs review.
* **proportional** (otherwise): each top-level layer is re-laid out by simple anchoring rules, and the result
  reports where every layer went:

  * sizes scale uniformly (``scale``: ``fit`` keeps everything inside, ``fill`` covers, ``width`` or ``height``
    follows one axis, or a number); text scales its font size and wrapping boxes;
  * each axis is anchored from the layer's place in the old canvas: near an edge it keeps its margin (scaled), near
    the middle it keeps its relative position, and a layer that spans the canvas stretches with it. Only
    backgrounds and plain bands (solids, gradients, rectangles, lines) stretch: other decoration that spans one axis
    (a wave, a pattern strip) is scaled uniformly to span it, and a full-canvas photo or artwork is scaled to cover
    instead of being distorted, keeping its ``focal`` point (layer-intent) in view; cover crops are listed under
    ``crops``;
  * layers that sit together (a rule under its headline, a stack of lines) move as one unit, so their arrangement
    survives (``together``);
  * content keeps out of the target size's safe area (``safe``: per-side insets such as a story's top and bottom
    250 px), and text never shrinks below ``min_text``;
  * ``anchors`` overrides the inferred choice per layer name, role, kind or tag; layers that already have
    constraints keep them (numeric values and canvas offsets are scaled), so constraint-driven layouts stay
    constraint-driven.

Layer priorities (layer-intent ``priority``) decide what may give way: ``optional`` and ``decorative`` text that
would fall below ``min_text`` (or that an arrangement has no room for) is hidden; ``required`` copy (the default)
is never hidden or cut off, and copy that still does not fit is listed under ``requirements``.

``adapt_copies`` applies the same operation to copies of a document for several sizes at once and runs the
document's attached check suites on each copy.
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
PRIORITIES = ("required", "optional", "decorative")
ARRANGEMENTS = ("proportional", "stack-vertical", "side-by-side", "hero-top")
NEEDS_IMAGE = ("side-by-side", "hero-top")
# What an arrangement candidate is scored with: composition and legibility, plus the checks that catch content an
# arrangement pushed off the canvas or onto other content.
SCORE_CHECKS = ("composition", "legibility", "bounds", "overlap")
# Options that only the proportional rules read: giving one asks for them instead of a recipe recompose.
PROPORTIONAL_OPTIONS = ("scale", "anchors", "where", "text", "together")
OPTIONS = ("size", "width", "height", "orientation", "dpi", "bleed", "scale", "anchors", "where", "text", "report", "recompose",
           "safe", "min_text", "together", "arrangements")

SCHEMA = {
    "recompose": {"type": "boolean", "description": "true rebuilds the stored layout-apply recipe at the new size "
                  "(replacing the generated layers and their IDs); false never does. Default: rebuild when the "
                  "document was made by layout-apply and nothing was edited since; otherwise adapt proportionally. "
                  "The result says recomposed and why."},
    "arrangements": {"type": "array", "items": {"enum": list(ARRANGEMENTS)}, "minItems": 1,
                     "maxItems": len(ARRANGEMENTS), "uniqueItems": True,
                     "description": "Arrangements of the content (logo, image, headline and copy, call to action) "
                     "to try at the new size: stack-vertical (one centred column), side-by-side (image beside the "
                     "copy), hero-top (image above the copy), proportional (the anchoring rules). Each is scored "
                     "with the composition, legibility, bounds and overlap checks; the best is kept and outcome "
                     "says whether it passed (needs_review when none did)."},
    "size": {"type": "string", "description": "Named target size (vixl_reference('sizes')), e.g. story or a4; or give width "
             "and height."},
    "orientation": {"enum": ["portrait", "landscape"], "description": "With a named size."},
    "dpi": {"type": "number", "minimum": 36, "maximum": 2400, "description": "With a named print size."},
    "bleed": {"type": ["boolean", "number"], "description": "With a named print size."},
    "mode": {"enum": ["stack", "proportional"], "description": "stack (the default with targets): reflow the targets "
             "vertically and refuse what cannot fit. proportional (the default without targets): resize the canvas "
             "and re-compose the document (a layout recipe, arrangements or the anchoring rules); the result says "
             "how and where each layer went."},
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
                 "Text with layer-intent priority optional or decorative that would fall below it is hidden instead; "
                 "required copy is never hidden or cut off."},
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
    require(op.get("recompose") is None or type(op["recompose"]) is bool, "recompose must be true or false",
            field="recompose")
    if "min_text" in op:
        require(isinstance(op["min_text"], (int, float)) and not isinstance(op["min_text"], bool)
                and 0 <= op["min_text"] <= 400, "min_text is a font size in pixels from 0 to 400", field="min_text")
    if "arrangements" in op:
        names = op["arrangements"]
        require(isinstance(names, list) and 0 < len(names) <= len(ARRANGEMENTS), "arrangements is a list of "
                f"arrangement names: {', '.join(ARRANGEMENTS)}", field="arrangements", allowed=list(ARRANGEMENTS))
        for name in names:
            if name not in ARRANGEMENTS:
                close = difflib.get_close_matches(str(name), ARRANGEMENTS, 1, 0.5)
                raise VixlError("invalid_operation", f"Unknown arrangement {name!r}; arrangements: "
                                + ", ".join(ARRANGEMENTS) + (f". Did you mean {close[0]!r}?" if close else ""),
                                field="arrangements", allowed=list(ARRANGEMENTS), suggestions=close)
        require(op.get("recompose") is not True, "recompose: true rebuilds the layout recipe; arrangements re-place "
                "the content instead: give one or the other", field="arrangements")
    anchors = op.get("anchors", {})
    require(isinstance(anchors, dict) and len(anchors) <= 100, "anchors is an object of up to 100 entries",
            field="anchors")
    for key, value in anchors.items():
        if _anchor(value) not in ANCHORS:
            close = difflib.get_close_matches(str(value), list(ANCHORS), 1, 0.5)
            raise VixlError("invalid_operation", f"anchors[{key!r}]: unknown anchor {value!r}; anchors: "
                            + ", ".join(ANCHORS) + (f". Did you mean {close[0]!r}?" if close else ""),
                            field="anchors", allowed=list(ANCHORS), suggestions=close)


def priority(layer):
    """required, optional or decorative (layer-intent ``priority``); a layer without one is required. Documents
    saved before priorities existed marked optional text with the ``optional`` tag, which still counts."""
    return layer.get("priority") or ("optional" if "optional" in layer.get("tags", ()) else "required")


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


def new_start(mode, start, size, length, new_length, new_size, s, ratio, explicit, focal=None):
    """Where a layer starts along one axis for its anchor. A cover crop with a ``focal`` fraction centres that point
    in the canvas as far as the image still covers it, so the subject stays in view."""
    if mode in ("start", "stretch", "span"):
        return start * s
    if mode == "end":
        return new_length - (length - start - size) * s - new_size
    middle = start + size / 2
    if mode == "cover":
        wanted = new_length / 2 - focal * new_size if focal is not None else middle * ratio - new_size / 2
        return min(0, max(new_length - new_size, wanted))
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


def fingerprint(state):
    """A short digest of the canvas size and every layer: the layout record keeps the one taken when layout-apply
    finished, so a later difference means the document was edited since. Layer IDs are numbered in order of
    appearance, so the same layout built twice has the same fingerprint."""
    from .hashing import canonical_json, hasher

    text = canonical_json({"canvas": [state["canvas"]["width"], state["canvas"]["height"]],
                           "layers": state["layers"]}).decode()
    numbers = {}
    text = re.sub(r"lyr_[0-9a-f]{16}", lambda match: numbers.setdefault(match[0], f"#{len(numbers)}"), text)
    digest = hasher("blake2b", 8)
    digest.update(text.encode())
    return digest.hexdigest()


def choose(project, op):
    """``(how, reason)``: rebuild the layout ``recipe``, try ``arrange``\\ ments or adapt ``proportional``\\ ly."""
    layout = project.state.get("layout") or {}
    if op.get("recompose") is True:
        require(layout.get("recipe"), "This document has no saved layout recipe; reapply layout-apply first",
                field="recompose")
        return "recipe", "recompose: true"
    fallback = "arrange" if op.get("arrangements") else "proportional"
    if op.get("recompose") is False:
        return fallback, "recompose: false"
    if op.get("arrangements"):
        return fallback, "arrangements were given"
    if not layout.get("recipe"):
        return fallback, "no layout-apply recipe to rebuild"
    given = [key for key in PROPORTIONAL_OPTIONS if key in op]
    if given:
        return fallback, f"proportional options were given ({', '.join(given)})"
    created = set(layout.get("layers", []))
    foreign = [layer["name"] for layer in project.state["layers"] if layer["id"] not in created]
    if foreign:
        return fallback, (f"layers not made by the layout ({', '.join(foreign[:5])}) would keep their old place; "
                          "recompose: true rebuilds the layout anyway")
    if "fingerprint" not in layout:
        return fallback, "the layout was applied before edits were tracked; recompose: true rebuilds it"
    if layout["fingerprint"] != fingerprint(project.state):
        return fallback, ("the layout's layers were edited since layout-apply; recompose: true would replace those "
                          "edits")
    return "recipe", f"made by layout-apply ({layout['name']}) and not edited since"


def execute(project, op):
    state = project.state
    check_options(op)
    require(not state.get("pages"), "adapt-layout does not support multi-page documents yet; use a document per "
            "page or the canvas operation", field="mode")
    how, reason = choose(project, op)
    if how == "recipe":
        report = recompose(project, op)
    elif how == "arrange":
        report = arrange(project, op)
    else:
        context = proportional(project, op)
        if not op.get("report", True):
            if context["skipped"]:
                record(project, "warnings", f"adapt-layout left {len(context['skipped'])} layer(s) at their size: "
                       + ", ".join(item["layer"] for item in context["skipped"]))
            return
        report = summary(project, context)
    report.setdefault("recomposed", how != "proportional")
    report.setdefault("reason", reason)
    record(project, "adapt_layout", report)


def resize_canvas(project, op):
    from .operations import execute as apply_operation

    apply_operation(project, {"type": "canvas", **{k: op[k] for k in ("size", "width", "height", "orientation", "dpi",
                                                                      "bleed") if k in op}})


def recompose(project, op):
    """Rebuild the stored layout-apply recipe at the new size."""
    from copy import deepcopy
    from .layouts import execute_layout
    from .schema import validate_operation

    old = [project.state["canvas"]["width"], project.state["canvas"]["height"]]
    resize_canvas(project, op)
    recipe = deepcopy(project.state["layout"]["recipe"])
    recipe.update(type="layout-apply", replace=True)
    # A target-specific size is derived afresh unless the recipe explicitly pinned it.
    execute_layout(project, validate_operation(recipe))
    return {"mode": "recompose", "layout": recipe["name"], "from": old,
            "to": [project.state["canvas"]["width"], project.state["canvas"]["height"]]}


def proportional(project, op, legible=False):
    """Resize the canvas and re-lay out every top-level layer by the anchoring rules; returns what ``summary``
    reports. ``legible`` (arrangements) raises the default ``min_text`` to the size the legibility check asks of
    a social or poster piece, so a candidate is not scored down for copy it could have hidden or enlarged."""
    from .checks import boxed_text_overflow
    from .operations import execute as apply_operation
    from .render import resolve_layout, stored_origin

    state = project.state
    old_w, old_h = state["canvas"]["width"], state["canvas"]["height"]
    before = resolve_layout(project)
    top = [layer for layer in state["layers"] if not layer.get("parent")]
    chosen = None
    if "where" in op:
        accepts = matcher(project, parse_where(op["where"]))
        chosen = {layer["id"] for layer in top if accepts(layer)}
    rules = anchor_rules(project, op.get("anchors", {}))
    resize_canvas(project, op)
    new_w, new_h = state["canvas"]["width"], state["canvas"]["height"]
    rx, ry = new_w / old_w, new_h / old_h
    scale = op.get("scale", "fit")
    s = float({"fit": min(rx, ry), "fill": max(rx, ry), "width": rx, "height": ry}.get(scale, scale))
    keep_text = op.get("text", "scale") == "keep"
    short = min(new_w, new_h)
    min_text = op.get("min_text", max(12, round(short * 0.012)))
    if legible and "min_text" not in op:
        from .repair import legible_minimum

        min_text = max(min_text, legible_minimum(project))
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
                    if priority(layer) != "required" and layer["visible"]:
                        # Optional or decorative copy too small to read is left out rather than set at 3 px.
                        layer["visible"] = False
                        dropped.append(layer["name"])
                        plans.pop(ident)
                        continue
                    scaled = min(min_text, layer["size"])
                apply_operation(project, {"type": "text-set", "target": ident, "size": scaled})
            box = layer.get("text_layout") or {}
            if "width" in box or "height" in box or not layer.get("auto_size", True):
                apply_operation(project, {"type": "text-layout", "target": ident, **box, "width": size[0], "height": size[1]})
                if priority(layer) == "required" and boxed_text_overflow(project, project.layer(ident)):
                    # Required copy is never cut off: its box grows to the lines it needs instead.
                    box = {key: value for key, value in project.layer(ident)["text_layout"].items() if key != "height"}
                    apply_operation(project, {"type": "text-layout", "target": ident, **box})
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
        focal = layer.get("focal") if plan["anchor"][0] == "cover" else None
        for axis, (start, extent, length, new_length, ratio) in enumerate(((x, w, old_w, new_w, rx), (y, h, old_h, new_h, ry))):
            names = (("left", "right", "center-x"), ("top", "bottom", "center-y"))[axis]
            constrained = [name for name in layer.get("constraints", {}) if name in names]
            for name in constrained:
                layer["constraints"][name] = scale_constraint(layer["constraints"][name], s, ratio)
            if constrained:
                free[axis] = False
            else:
                origin[axis] = new_start(plan["anchor"][axis], start, extent, length, new_length,
                                         sized[layer["id"]][2 + axis], s, ratio, plan["explicit"],
                                         focal[axis] if focal else None)
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
    return {"old": (old_w, old_h), "new": (new_w, new_h), "scale": s, "before": before, "plans": plans, "top": top,
            "skipped": skipped, "together": together, "shifted": shifted, "dropped": dropped,
            "min_text": min_text if min_text and not keep_text else None, "keep_text": keep_text}


def summary(project, context):
    """The ``adapt_layout`` report of a proportional (or arranged) adaptation from the document as it is now."""
    from .render import resolve_layout

    after = resolve_layout(project)
    before, plans = context["before"], context["plans"]
    moved = []
    for layer in context["top"]:
        plan = plans.get(layer["id"])
        if plan is None:
            continue
        row = {"layer": layer["name"], "from": list(before[layer["id"]]), "to": list(after[layer["id"]]),
               "anchor": plan.get("placed") or (plan["anchor"][0] if plan["anchor"][0] in ("cover", "keep")
                                                else ", ".join(NAMES[i].get(m, m) for i, m in enumerate(plan["anchor"])))}
        if layer["type"] == "text" and not context["keep_text"]:
            row["font_size"] = layer["size"]
        if row["from"] != row["to"]:
            moved.append(row)
    cropped = crops(project, context, after)
    failed = unmet(project, context, after)
    old_w, old_h = context["old"]
    new_w, new_h = context["new"]
    return {
        "canvas": {"from": [old_w, old_h], "to": [new_w, new_h]}, "scale": round(context["scale"], 4),
        "adapted": len(plans), "moved": len(moved), "layers": moved[:MAX_REPORTED],
        **({"more": len(moved) - MAX_REPORTED} if len(moved) > MAX_REPORTED else {}),
        **({"skipped": context["skipped"]} if context["skipped"] else {}),
        **({"together": context["together"]} if context["together"] else {}),
        **({"kept_safe": context["shifted"]} if context["shifted"] else {}),
        **({"dropped": context["dropped"]} if context["dropped"] else {}),
        **({"crops": cropped} if cropped else {}),
        **({"requirements": {"failed": failed}} if failed else {}),
        **({"min_text": context["min_text"]} if context["min_text"] else {}),
    }


def crops(project, context, after):
    """Layers the new canvas crops because they cover it: ``{layer, kept, lost_px}``, where ``kept`` is the focal
    point held in view (null without one) and ``lost_px`` the pixels cut off at the left, top, right and bottom."""
    width, height = context["new"]
    found = []
    for layer in context["top"]:
        plan = context["plans"].get(layer["id"])
        if plan is None or plan["anchor"][0] != "cover" or not layer["visible"]:
            continue
        x, y, w, h = after[layer["id"]]
        lost = [max(0, round(-x)), max(0, round(-y)), max(0, round(x + w - width)), max(0, round(y + h - height))]
        if any(lost):
            found.append({"layer": layer["name"], "kept": layer.get("focal"), "lost_px": lost})
    return found


def unmet(project, context, after):
    """Required copy that does not fit: not wholly on the canvas, or cut off by its box, at ``min_text`` or
    above. Such copy is never truncated or hidden, so it is reported here instead."""
    from .checks import boxed_text_overflow
    from .render import resolved_layers

    width, height = context["new"]
    resolved = {item["id"]: item for item in resolved_layers(project)}
    failed = []
    for layer in context["top"]:
        if layer["type"] != "text" or not layer["visible"] or priority(layer) != "required":
            continue
        item = resolved[layer["id"]]
        if not item["visible"]:
            continue
        x, y, w, h = after[layer["id"]]
        problem = None
        if x < -0.5 or y < -0.5 or x + w > width + 0.5 or y + h > height + 0.5:
            problem = "on the canvas"
        elif boxed_text_overflow(project, item):
            problem = "inside its text box"
        if problem:
            failed.append({"layer": layer["name"], "requirement": problem, "font_size": layer["size"],
                           "box": [round(v) for v in (x, y, w, h)],
                           "message": f"{layer['name']!r} does not fit {problem} at {layer['size']} px; shorten it, "
                                      "give it more room or choose another arrangement"})
    return failed


# Arrangements -----------------------------------------------------------------------------------------------------


def arrange(project, op):
    """Build each arrangement on a copy, score it with ``SCORE_CHECKS`` and keep the best (fewest failed
    requirements, then fix findings, then review findings; the first listed wins a tie)."""
    from .outcomes import describe, from_findings, make, merge

    rest = {key: value for key, value in op.items() if key != "arrangements"}
    snapshot = project.clone()
    budget = getattr(project, "_resource_budget", project.limits.max_operations)
    candidates, scored = [], []
    for name in op["arrangements"]:
        trial = snapshot.clone()
        trial._resource_budget = budget
        context = proportional(trial, rest, legible=True)
        if name != "proportional":
            placed = compose(trial, name, context)
            if placed is None:
                candidates.append({"arrangement": name, "skipped": "needs an image layer"})
                continue
        report = summary(trial, context)
        found = trial.check(checks=list(SCORE_CHECKS))
        issues = [item for item in found["issues"] if item["action"] in ("fix", "review")]
        failed = report.get("requirements", {}).get("failed", [])
        fixes = sum(1 for item in issues if item["action"] == "fix")
        score = (len(failed), fixes, len(issues) - fixes)
        candidates.append({"arrangement": name, "passed": score == (0, 0, 0), "requirements_failed": len(failed),
                           "fix": fixes, "review": len(issues) - fixes})
        scored.append((score, len(scored), name, trial, report, issues))
    require(scored, "No arrangement applies to this document: side-by-side and hero-top need an image layer; add "
            "stack-vertical or proportional", field="arrangements")
    score, _, name, trial, report, issues = min(scored, key=lambda item: item[:2])
    project.state, project.assets = trial.state, trial.assets
    project._resource_budget = trial._resource_budget
    failed = report.get("requirements", {}).get("failed", [])
    requirement = make("completed", "failed" if failed else "passed",
                       [f"{item['layer']}: does not fit {item['requirement']}" for item in failed],
                       validated_by=["adapt-layout requirements"])
    outcome = merge(from_findings(issues), requirement)
    report.update(arrangement=name, candidates=candidates, outcome=outcome, recomposed=name != "proportional",
                  reason=(f"arrangement {name} passed the composition, legibility, bounds and overlap checks"
                          if score == (0, 0, 0) else
                          f"no arrangement passed; {name} came closest, so it needs review"))
    if issues:
        report["findings"] = [describe(item) for item in issues[:10]]
    return report


def backdrop(layer, box, canvas):
    """Layers an arrangement leaves where the anchoring rules put them: backgrounds, decoration, solids and
    gradients, and anything but text that spans the canvas along an axis (a band, a cover photo)."""
    x, y, w, h = box
    return (layer.get("role") in ("background", "decoration") or layer["type"] in ("solid", "gradient", "adjustment")
            or (layer["type"] != "text" and (w >= SPAN * canvas[0] or h >= SPAN * canvas[1])))


def kind_of(layer):
    words = " ".join([layer["name"].lower(), *layer.get("tags", [])])
    if "logo" in words:
        return "logo"
    if re.search(r"\bcta|button", words):
        return "cta"
    return "image" if layer["type"] in ("raster", "frame", "link") else "content"


def compose(project, name, context):
    """Re-place the content of a proportionally adapted document in arrangement ``name``; None when the
    arrangement needs an image the document does not have."""
    from .craft import body_size, space
    from .house_style import rule
    from .render import resolve_layout
    from .sizes import live_insets

    state = project.state
    canvas = (state["canvas"]["width"], state["canvas"]["height"])
    bounds = resolve_layout(project)
    groups = {"logo": [], "image": [], "content": [], "cta": []}
    for layer in context["top"]:
        if not layer["visible"] or layer["id"] not in context["plans"] or backdrop(layer, bounds[layer["id"]], canvas):
            continue
        groups[kind_of(layer)].append(layer)
    if name in NEEDS_IMAGE and not groups["image"]:
        return None
    for members in groups.values():
        members.sort(key=lambda layer: (context["before"][layer["id"]][1], context["before"][layer["id"]][0]))
    margin = round(rule("margins")[1] * min(canvas))
    left, top, right, bottom = (max(margin, side) for side in live_insets(state["canvas"]))
    box = [left, top, canvas[0] - left - right, canvas[1] - top - bottom]
    body = body_size(project)
    gap, apart = space(2, body), space(5, body)
    texts = [layer for layer in groups["content"] + groups["cta"] if layer["type"] == "text"]
    centred = sum(layer.get("align", "left") == "center" for layer in texts) * 2 > len(texts)
    align = "center" if centred else "start"
    column = box
    if name == "side-by-side":
        image_left = (context["before"][groups["image"][0]["id"]][0]
                      <= min((context["before"][layer["id"]][0] for layer in groups["content"]), default=canvas[0]))
        half = (box[2] - apart) / 2
        image_box = [box[0] if image_left else box[0] + half + apart, box[1], half, box[3]]
        column = [box[0] + half + apart if image_left else box[0], box[1], half, box[3]]
        place_images(project, groups["image"], image_box, gap, middle=True)
    elif name == "hero-top":
        image_box = [box[0], box[1], box[2], box[3] * 0.5]
        used = place_images(project, groups["image"], image_box, gap, middle=False)
        column = [box[0], box[1] + used + apart, box[2], box[3] - used - apart]
    segments = [groups["logo"], (groups["image"] if name == "stack-vertical" else []) + groups["content"], groups["cta"]]
    fit_column(project, context, segments, column, gap, apart, name == "stack-vertical")
    place_column(project, segments, column, gap, apart, align, "center", centre=name == "stack-vertical")
    for layer in groups["logo"] + groups["image"] + groups["content"] + groups["cta"]:
        if layer["id"] in context["plans"]:
            context["plans"][layer["id"]]["placed"] = name
    return True


def scale_to(project, layer, factor):
    """Scale a non-text layer uniformly by ``factor`` of its visible size."""
    from .operations import execute as apply_operation

    apply_operation(project, {"type": "resize", "target": layer["id"], "width": max(1, round(layer["width"] * factor)),
                              "height": max(1, round(layer["height"] * factor))})


def place_images(project, images, region, gap, middle):
    """Fit images inside ``region`` (side by side when there are several), keeping their proportions, at its top
    or its ``middle``; returns the height they use."""
    from .render import resolve_layout, stored_origin
    from .stacks import cross, distribute

    if not images:
        return 0
    bounds = resolve_layout(project)
    width = (region[2] - gap * (len(images) - 1)) / len(images)
    for layer in images:
        w, h = bounds[layer["id"]][2:]
        scale_to(project, layer, min(width / max(1, w), region[3] / max(1, h)))
    bounds = resolve_layout(project)
    sizes = [bounds[layer["id"]][2:] for layer in images]
    used = max(size[1] for size in sizes)
    offsets = distribute([size[0] for size in sizes], region[2], gap, "center", region[0])
    top = region[1] + (cross(used, region[3], "center") if middle else 0)
    for layer, size, x in zip(images, sizes, offsets):
        layer["x"], layer["y"] = stored_origin(layer, (round(x), round(top + cross(size[1], used, "center"))))
    return used


def column_height(bounds, segments, gap, apart):
    heights = [sum(bounds[layer["id"]][3] for layer in segment) + gap * max(0, len(segment) - 1)
               for segment in segments if segment]
    return sum(heights) + apart * max(0, len(heights) - 1)


def fit_column(project, context, segments, column, gap, apart, images_in_column):
    """Make the column's content fit its box: wrap text to the column width and shrink images to at most 40% of
    the height; then, while it is too tall, hide decorative and then optional layers (bottom first) and set text
    smaller, never below ``min_text``. Required copy that still does not fit is reported by ``unmet``."""
    from .operations import execute as apply_operation
    from .render import resolve_layout

    width, height = column[2], column[3]
    min_text = context["min_text"] or 1

    def wrap():
        bounds = resolve_layout(project)
        for segment in segments:
            for layer in segment:
                w, h = bounds[layer["id"]][2:]
                if layer["type"] == "text" and w > width + 0.5:
                    settings = {key: value for key, value in (layer.get("text_layout") or {}).items()
                                if key not in ("height", "fit")}
                    settings.setdefault("wrap", "balance")  # Re-wrapped copy keeps even lines, never a runt.
                    apply_operation(project, {"type": "text-layout", "target": layer["id"], **settings, "width": width})
                elif layer["type"] != "text" and (w > width + 0.5 or (images_in_column and layer["type"] in
                                                                     ("raster", "frame", "link") and h > height * 0.4)):
                    scale_to(project, layer, min(width / max(1, w), (height * 0.4 if images_in_column else height) / max(1, h)))
        return resolve_layout(project)

    bounds = wrap()
    for level in ("decorative", "optional"):
        for layer in reversed([layer for segment in segments for layer in segment]):
            if column_height(bounds, segments, gap, apart) <= height:
                break
            if priority(layer) == level and layer["visible"]:
                layer["visible"] = False
                context["dropped"].append(layer["name"])
                context["plans"].pop(layer["id"], None)
                for segment in segments:
                    if layer in segment:
                        segment.remove(layer)
                bounds = resolve_layout(project)
    for _ in range(8):
        if column_height(bounds, segments, gap, apart) <= height:
            break
        smaller = False
        for segment in segments:
            for layer in segment:
                if layer["type"] == "text" and layer["size"] > min_text:
                    apply_operation(project, {"type": "text-set", "target": layer["id"],
                                              "size": max(min_text, round(layer["size"] * 0.88))})
                    smaller = True
        if not smaller:
            break
        bounds = wrap()


def place_column(project, segments, column, gap, apart, align, justify, centre=False):
    """Stack the segments (logo, main content, call to action) in the column: members ``gap`` apart, segments
    ``apart`` (spread to the column's ends when there are several and ``justify`` is center). Members line up
    on ``align`` inside the block they make; ``centre`` centres that block in the column."""
    from .render import resolve_layout, stored_origin
    from .stacks import cross, distribute

    bounds = resolve_layout(project)
    filled = [segment for segment in segments if segment]
    if not filled:
        return
    heights = [sum(bounds[layer["id"]][3] for layer in segment) + gap * (len(segment) - 1) for segment in filled]
    how = "space-between" if len(filled) > 1 and justify == "center" else justify
    if how == "space-between" and sum(heights) + apart * (len(filled) - 1) < column[3] * 0.6:
        how = "center"  # A short column spread to both ends would leave a hole in the middle.
    starts = distribute(heights, column[3], apart, how, column[1])
    block = max(bounds[layer["id"]][2] for segment in filled for layer in segment)
    left = column[0] + (cross(block, column[2], "center") if centre else 0)
    for segment, start in zip(filled, starts):
        y = start
        for layer in segment:
            w, h = bounds[layer["id"]][2:]
            x = left + cross(w, block, align)
            layer["x"], layer["y"] = stored_origin(layer, (round(x), round(y)))
            y += h + gap


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


COPY_OPTIONS = ("scale", "anchors", "where", "text", "recompose", "safe", "min_text", "together", "arrangements")


def adapt_copies(session, export_file, sizes, directory=".", name="{name}-{size}", options=None, document=None,
                 overwrite=False, formats=None, report="summary", suites=True):
    """Copy a document once per size, adapt each copy with ``adapt-layout`` and save it (and optionally
    export it): one call for a whole campaign. The source document is never changed. ``suites`` (true: every
    attached suite, a name or a list, false: none) runs the document's check suites on each copy and attaches
    their results and outcome."""
    from pathlib import Path

    from . import calls
    from .checks import suite_names, suite_summary
    from .io_policy import service_check
    from .outcomes import merge

    require(isinstance(sizes, list) and 0 < len(sizes) <= 16, "Give 1–16 sizes", field="sizes")
    require(report in ("summary", "layers"), "report is summary or layers", field="report")
    options = dict(options or {})
    bad = sorted(set(options) - set(COPY_OPTIONS))
    require(not bad, f"options accepts {', '.join(COPY_OPTIONS[:-1])} and {COPY_OPTIONS[-1]}; got "
            f"{', '.join(bad)}", field="options")
    formats = [f.lower().lstrip(".") for f in (formats or [])]
    require(all(re.fullmatch(r"png|jpg|jpeg|webp|tif|tiff|avif|svg|pdf", f) for f in formats),
            "formats are png, jpg, webp, tiff, avif, svg or pdf", field="formats")
    folder = session.resolve(directory)
    with session.project(document=document) as source:
        base = source.clone()
        source_path = Path(source.path)
    base.path, base._revision = None, None
    # The copies are checked as the source document: its project groups and workspace attach suites by its path.
    base._document = source
    checked = suite_names(base, suites) if suites is not False else []
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
        outcome = candidate.apply([{"type": "adapt-layout", **spec, **options}], detail="brief", validator=service_check)
        report_row = outcome["adapt_layout"][0]
        session.make_parent(destination)
        candidate.save(destination, overwrite=overwrite)
        item = {"size": label, "path": session.relative(destination)}
        if report_row.get("mode") == "recompose":
            # Recomposition rebuilds the layers from the recipe: there is no uniform scale or per-layer move.
            item.update(canvas=report_row["to"], scale=None, moved="recomposed", layout=report_row["layout"])
        else:
            item.update(canvas=report_row["canvas"]["to"], scale=report_row["scale"], moved=report_row["moved"])
            if report == "layers":
                item["layers"] = report_row["layers"]
            for key in ("arrangement", "dropped", "crops", "requirements"):
                if key in report_row:
                    item[key] = report_row[key]
        item.update(recomposed=report_row["recomposed"], reason=report_row["reason"])
        outcomes = [report_row["outcome"]] if "outcome" in report_row else []
        if checked:
            item["suites"] = suite_summary(candidate, checked)
            outcomes += [entry["outcome"] for entry in item["suites"].values()]
        if outcomes:
            item["outcome"] = merge(*outcomes)
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
