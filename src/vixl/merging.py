"""Merging layers into pixels: ``merge-layers`` (the listed layers) and ``flatten`` (the whole page).

Both draw their layers with the renderer (styles, clipping, masks, opacity and the blend modes
between the merged layers) into one raster layer that keeps the originals in its provenance; one
operation is one history entry, so undo restores them. A merged layer is drawn with the normal
blend mode: how a merged layer blended with layers below the merge (or with the canvas background)
cannot be kept in its pixels, and the result warns when that may change the look.
"""

from copy import deepcopy
import math

from .errors import require

TYPES = ("merge-layers", "flatten")


def schemas(add):
    from .model import MAX_LAYERS
    from .schema import B, S

    add("merge-layers", {
        "targets": {"type": "array", "items": S, "minItems": 2, "maxItems": MAX_LAYERS, "uniqueItems": True,
                    "description": "Layers to merge (IDs or names, sharing a parent; a group brings its members). "
                                   "Hidden layers are discarded."},
        "name": {**S, "description": "Name of the merged layer. Default: the topmost merged layer's name."},
    }, ["targets"])
    add("flatten", {
        "name": {**S, "description": "Name of the flattened layer. Default: flattened."},
        "keep_hidden": {**B, "description": "true keeps hidden top-level layers as they are, in place (merge visible); "
                                            "false (default) discards them."},
    })


def _merge(project, members, removed, region, name, default, provenance):
    """Replace the layers ``removed`` (IDs, including ``members`` and their descendants) by one raster
    layer of ``members`` drawn over ``region``, at the topmost member's place in the stack."""
    from .assets import add_image
    from .design import resolve_color
    from .model import new_layer
    from .notices import warn
    from .operations import default_name, forget_layers, unique_name
    from .render import color, render_members, resolve_layout

    layers = project.state["layers"]
    drawn = [item for item in layers if item["id"] in members]
    image, (left, top) = render_members(project, [item["id"] for item in drawn], region)
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    require(box, "The layers draw no pixels to merge", field="targets")
    blended = [item for item in drawn if item["blend"] != "normal" or item["type"] == "adjustment"]
    background = color(resolve_color(project.state["canvas"]["background"], project.state))[3]
    if blended and (layers.index(drawn[0]) > 0 or background):
        # Where the merged pixels are opaque, nothing below showed through to be blended with.
        bounds = resolve_layout(project)
        blended = [item["name"] for item in blended if _shows_through(alpha, bounds[item["id"]], left, top)]
    else:
        blended = []
    image = image.crop(box)
    if blended:
        listed = ", ".join(repr(text) for text in blended[:5])
        warn(project, f"{listed} blend with the layers merged with them, but not with what lies below the merge: the "
                      "merged layer uses the normal blend mode, so it may look different there")
    originals = [deepcopy(item) for item in layers if item["id"] in removed]
    topmost = drawn[-1]
    merged = new_layer("merged", "raster", image.width, image.height, x=left + box[0], y=top + box[1],
                       asset=add_image(project, image), provenance={"type": provenance, "originals": originals})
    if topmost.get("parent"):
        merged["parent"] = topmost["parent"]
    position = layers.index(topmost)
    spot = position - sum(1 for item in layers[:position] if item["id"] in removed)
    layers[:] = [item for item in layers if item["id"] not in removed]
    merged["name"] = unique_name(project, name) if name else default_name(project, default or topmost["name"])
    layers.insert(spot, merged)
    forget_layers(project, removed, merged["id"])
    return merged


def _within(layers, roots):
    """The IDs of every layer nested (at any depth) in the layers ``roots``."""
    children = {}
    for item in layers:
        if item.get("parent"):
            children.setdefault(item["parent"], []).append(item["id"])
    found, pending = set(), list(roots)
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _shows_through(alpha, bounds, left, top):
    x, y, w, h = bounds
    box = (max(0, math.floor(x) - left), max(0, math.floor(y) - top),
           min(alpha.width, math.ceil(x + w) - left), min(alpha.height, math.ceil(y + h) - top))
    return box[0] < box[2] and box[1] < box[3] and alpha.crop(box).getextrema()[0] < 255


def execute(project, op):
    from .notices import warn

    layers = project.state["layers"]
    if op["type"] == "merge-layers":
        picked = [project.layer(t) for t in op["targets"]]
        ids = {item["id"] for item in picked}
        require(len(ids) == len(picked), "Duplicate layer references", field="targets")
        inner = _within(layers, ids)
        picked = [item for item in picked if item["id"] not in inner]  # a member of a merged group comes along
        require(len({item.get("parent") for item in picked}) == 1,
                "Layers to merge must share a parent; group them first, or merge inside their group", field="targets")
        visible = {item["id"] for item in picked if item["visible"]}
        require(visible, "Every listed layer is hidden; show the layers to merge", field="targets")
        hidden = [repr(item["name"]) for item in picked if not item["visible"]]
        if hidden:
            warn(project, f"hidden layer(s) {', '.join(hidden[:5])} were discarded by the merge")
        removed = ids | inner
        merged = _merge(project, visible, removed, None, op.get("name"), None, "merged")
        return {"layer": merged["id"]}
    top = [item for item in layers if not item.get("parent")]
    visible = {item["id"] for item in top if item["visible"]}
    require(visible, "There are no visible layers to flatten")
    dropped = {item["id"] for item in top if not item["visible"] and not op.get("keep_hidden")}
    if dropped:
        warn(project, f"{len(dropped)} hidden layer(s) were discarded by flatten (keep_hidden: true keeps them)")
    removed = visible | dropped
    removed |= _within(layers, removed)
    canvas = project.state["canvas"]
    merged = _merge(project, visible, removed, (0, 0, canvas["width"], canvas["height"]), op.get("name"), "flattened",
                    "flattened")
    return {"layer": merged["id"]}


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog=f"vixl {cmd}")
    if cmd == "merge-layers":
        p.add_argument("targets", nargs="+", help="layers to merge (sharing a parent), bottom to top in any order")
    else:
        p.add_argument("--keep-hidden", action="store_true", default=None, help="keep hidden layers instead of discarding them")
    p.add_argument("--name", help="name of the resulting raster layer")
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
