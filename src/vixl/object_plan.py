"""``object-plan``: a scaffold of placeholder parts for an object kind, to refine into the drawing.

The build loop is reference → object-plan → refine → outline → check. ``plan`` reads the kind merged down its chain
(``objects.merged``) and returns one batch of ordinary operations:

- **parts**: with a ``build.example``, the parts it draws (as many layers of each, with their sides and depths);
  otherwise every required part and every part ``build.placements`` places, ``count`` of each (an optional pair seen
  from the side is one: the far eye is hidden; a pair of limbs is a far and a near one);
- **shapes and sizes**: each part's shape, box, rotation and fill from the example, else a shape from ``build.shapes``
  and a size relative to the part it attaches to. A part the kind's ``proportions`` measure is sized at the middle of
  its range (``seed`` picks a value inside it and varies the other parts by up to 8%);
- **positions**: the ``at`` point of the part (default: the opposite anchor) on the ``anchor`` point of another part's
  box or of ``object``, several spaced along the edge by ``spread``, a far limb half its width behind the near one,
  the petals of a radial kind in a ring. A part with no placement attaches to the part it connects to. Each part is
  then pushed toward the part it attaches to until they overlap by ``OVERLAP`` pixels, and every pair the kind says
  must touch is checked again, so the scaffold passes the object check's connections as generated;
- **order**: back to front as the example draws them, else by the kind's ``layering`` (a part it does not name sits
  just above the part it attaches to);
- then ``group``, ``object`` and one ``object`` ``action: part`` per part and side; ``with`` nests sub-objects,
  planned the same way, in front of the parts.

Animals and vehicles are side views facing right, everything else a front view; ``view`` names the one the kind has.
A person (and the kinds below it) comes from head units (``person_layout``): ``head_units`` (default 7.5, or the
middle of the kind's head proportion) and ``width_ratio`` place the 17 standard parts, and a head outside the kind's
range declares the object ``stylized``. ``template: "figure-plan"`` returns the blocking figure of the
``figure-plan`` workflow instead (``figure_template``), which is what that workflow now runs.

``FINISHERS`` add operations after the parts are named, in the same batch: each is called as
``finish(plan, project, request, depth)`` (the plan with its ``kind``, ``name``, ``box``, ``parts`` and ``operations``;
the open document or None; the request; 0 for the object and above for a sub-object) and returns a list of operations.
``illustration_finish`` is the one registered: in a document with a house style (``craft.illustration_on``) every
plan, sub-objects included, ends with the house illustration finish (see its docstring); ``illustration: "plain"``
(or ``outline: false``) leaves the scaffold as the parts left it. The ``figure-plan`` template returns before any
finisher runs, so its output never changes.
"""

from dataclasses import dataclass, field
import math
import random
import zlib

from .errors import require
from .model import finite

FIELDS = ("kind", "name", "box", "x", "y", "height", "view", "with", "seed", "apply", "head_units", "width_ratio",
          "color", "template", "illustration")
ACTIONS = {"object-plan": (set(FIELDS), {"kind"})}
VIEWS = ("side", "front")
SIDE_VIEW = ("animal", "vehicle")
PAIRED_LIMBS = ("leg", "wing", "arm")
OVERLAP = 2
DEFAULT_HEIGHT = 400
FAR_SHIFT = 0.5
SEED_RANGE = 0.2  # a seeded proportion keeps this share of its range clear at each end
SEED_SIZE = 0.08
MAX_WITH = 8
MAX_NESTING = 3
MAX_STEPS = 4000
# Parts that sit inside the part they attach to when the kind has no placement for them.
INNER = ("eye", "nose", "mouth", "label", "screen", "camera", "keyboard", "nucleus", "detail", "highlight", "door",
         "window", "spots", "spot", "facet", "sound-hole", "keys", "soil", "snow-cap", "shadow-side", "border", "motto")
ROUND = ("head", "body", "eye", "nose", "center", "cap", "bell", "mantle", "membrane", "nucleus", "disc", "puff",
         "wheel", "thorax", "abdomen", "segment", "shell", "pad", "canopy")
LIMB = ("leg", "arm", "tail", "antenna", "tentacle", "stalk", "neck", "stem", "branch", "root", "ray", "shaft",
        "handle", "mast", "frond", "eye-stalk", "spine", "ossicone")
FINISHERS = []

NUMBER = {"type": "number"}
FIELD_TYPES = {
    "kind": {"type": "string", "description": "The object kind or an alias (dog, guitar, person, puppy …); vixl objects "
             "lists them."},
    "name": {"type": "string", "description": "Name of the object group (default: the kind); part layers are NAME-PART, "
             "made unique in the document."},
    "box": {"type": "array", "items": NUMBER, "minItems": 4, "maxItems": 4, "description": "[x, y, width, height]: fit "
            "the object inside this box, centred (instead of x, y and height)."},
    "x": {**NUMBER, "description": "Left edge of the object (default: centred on the canvas; 0 without a document)."},
    "y": {**NUMBER, "description": "Top edge of the object (default: centred on the canvas; 0 without a document)."},
    "height": {"type": "number", "exclusiveMinimum": 0, "description": "Height of the object in pixels. Without box, "
               "x, y or height the object fits a centred box of 80% of the canvas width and 60% of its height (400 "
               "px tall without a document)."},
    "view": {"type": "string", "enum": list(VIEWS), "description": "The view the kind is drawn in: side for animals and "
             "vehicles (facing right), front for everything else; another view is refused."},
    "with": {"type": "array", "maxItems": MAX_WITH, "description": "Sub-objects nested inside the object, each planned "
             "the same way: a kind name, or {kind, name?, height?, anchor?, at?}.",
             "items": {"anyOf": [
                 {"type": "string", "description": "A kind: placed at the object's centre at half its height."},
                 {"type": "object", "description": "A sub-object with its own name, height and anchor.", "properties": {
                     "kind": {"type": "string", "description": "The sub-object's kind."},
                     "name": {"type": "string", "description": "Its group name (default OBJECT-KIND)."},
                     "height": {"type": "number", "exclusiveMinimum": 0, "description": "Its height in pixels "
                                "(default half the object's)."},
                     "anchor": {"type": "string", "description": "Where it goes: PART.ANCHOR on the object's parts or "
                                "object.ANCHOR (default object.center)."},
                     "at": {"type": "string", "description": "The anchor of the sub-object that sits there (default "
                            "the opposite one, center for center)."},
                 }, "required": ["kind"]},
             ]}},
    "seed": {"type": "integer", "description": "Vary the scaffold: each proportion anywhere inside the kind's range and "
             "part sizes by up to 8%. Omitted, every proportion sits at the middle of its range."},
    "apply": {"type": "boolean", "default": False, "description": "true applies the batch to the open document as one "
              "undo step; false (default) returns it with per-part next steps and changes nothing."},
    "head_units": {"type": "number", "description": "person: the figure's height in heads, 3.7-12 (default 7.5, or the "
                   "middle of the kind's head proportion); outside the kind's range the object is declared stylized."},
    "width_ratio": {"type": "number", "description": "person: horizontal scale of the body, 0.5-2 (default 1)."},
    "color": {"type": "string", "description": "One colour for the placeholders, shaded per part (default: the colours "
              "of the kind's example, else its palette)."},
    "illustration": {"type": "string", "enum": ["house", "plain"], "description": "house adds the house style's "
                     "illustration finish after the parts (ink part lines under outline parts, thin extra lines "
                     "now and then, a slight wobble, a hard offset shadow cast away from the light); plain leaves the "
                     "scaffold as it is. Default: house in a document with a house style, plain without one. "
                     "outline: false is read as plain."},
    "template": {"type": "string", "enum": ["figure-plan"], "description": "person: figure-plan returns the blocking "
                 "figure of the figure-plan workflow (seven separated head-unit masses and a parts map, no object "
                 "declaration) instead of the named parts."},
}


def figure_template(spec):
    """The blocking figure: head, torso, pelvis, two arms and two legs from head units, side-separated so the
    silhouette reads, with a parts map. Its output is kept exactly as the figure-plan workflow always returned it."""
    from .automation import bounded_object

    bounded_object(spec, {"name", "height", "head_units", "width_ratio", "x", "y", "color"}, "Unknown figure setting")
    name = spec.get("name", "figure")
    require(isinstance(name, str) and name and len(name) <= 64, "Invalid figure name")
    height = finite(spec.get("height", 600), "height", 40, 10000)
    heads = finite(spec.get("head_units", 7.5), "head_units", 3, 12)
    width = finite(spec.get("width_ratio", 1), "width_ratio", .5, 2)
    x, y = finite(spec.get("x", 0), "x", -1e6, 1e6), finite(spec.get("y", 0), "y", -1e6, 1e6)
    head = height / heads
    parts = {"head": (.95, .0, .9, 1, "ellipse"), "torso": (.45, 1.1, 1.9, 1.65, "rectangle"),
             "pelvis": (.6, 2.8, 1.6, .8, "rectangle"), "left-arm": (.05, 1.25, .35, 2.7, "rectangle"),
             "right-arm": (2.4, 1.25, .35, 2.7, "rectangle"), "left-leg": (.62, 3.65, .65, heads - 3.65, "rectangle"),
             "right-leg": (1.55, 3.65, .65, heads - 3.65, "rectangle")}
    require(heads > 3.65, "Head units must exceed 3.65 for this separated-limb template")
    operations = []
    for part, (px, py, pw, ph, shape) in parts.items():
        operations.append({"type": "shape", "name": f"{name}-{part}", "shape": shape, "x": x + px * head * width,
                           "y": y + py * head, "width": max(1, round(pw * head * width)),
                           "height": max(1, round(ph * head)), "fill": spec.get("color", "#916b56")})
    operations.append({"type": "group", "name": name, "targets": [o["name"] for o in operations]})
    return {"operations": operations, "parts": {part: f"{name}-{part}" for part in parts}, "head_units": heads,
            "next_steps": "Adjust gesture/proportions from references, split articulated limbs, then define the "
                          "character rig pivots."}


def figure_alias(spec):
    """``figure-plan``: object-plan with kind person and template figure-plan, reported under ``normalized``."""
    require(isinstance(spec, dict), "spec is an object of figure settings", field="spec")
    result = plan({"kind": "person", "template": "figure-plan", **spec})
    result["normalized"] = [{"field": "workflow", "from": "figure-plan", "to": "object-plan",
                             "reason": "figure-plan is object-plan with kind person and template figure-plan"}]
    return result


# ---------------------------------------------------------------------------------------------------------------
# Pieces: one placeholder layer each


@dataclass
class Piece:
    part: str
    shape: str
    w: float
    h: float
    rotation: float = 0.0
    extra: dict = field(default_factory=dict)
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float | None = None
    stroke_base: float | None = None
    side: str | None = None
    depth: str | None = None
    order: float | None = None
    scale: float = 1.0
    name: str = ""
    x: int = 0
    y: int = 0
    width: int = 1
    height: int = 1
    anchor: tuple | None = None  # (target part or "object", anchor, at, fraction, mirrored)
    partner: "Piece | None" = None
    ring: float | None = None  # radial: the angle of this piece around its anchor


def _box(piece):
    """The piece's drawn box (its rotated envelope) as (x0, y0, x1, y1)."""
    w, h = piece.width, piece.height
    angle = math.radians(piece.rotation)
    ew = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
    eh = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
    cx, cy = piece.x + w / 2, piece.y + h / 2
    return cx - ew / 2, cy - eh / 2, cx + ew / 2, cy + eh / 2


def _envelope(piece):
    x0, y0, x1, y1 = _box(piece)
    return x1 - x0, y1 - y0


_SHAPES = {}
_BLANK = []


def _blank_state():
    """A new document's state: what placeholder colours and shapes resolve against before any document exists."""
    if not _BLANK:
        from .project import Project

        _BLANK.append(Project(1, 1).state)
    return _BLANK[0]


def _outline(piece):
    """The piece's drawn area as a shapely geometry centred on (0, 0): its fill, or its stroke for line work."""
    from shapely import affinity
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    from .geometry import path_polygons
    from .object_outline import filled_area

    key = (piece.shape, piece.width, piece.height, piece.rotation, repr(sorted(piece.extra.items())),
           piece.stroke_width if piece.stroke else None)
    if key not in _SHAPES:
        import numpy as np

        w, h = piece.width, piece.height
        if piece.stroke and piece.shape == "path":
            view = piece.extra.get("path_view") or [w, h]
            lines = [LineString([(x * w / view[0] - w / 2, y * h / view[1] - h / 2) for x, y in points])
                     for points in path_polygons(piece.extra["path"]) if len(points) > 1]
            region = unary_union([line.buffer(max(piece.stroke_width or 1, 1) / 2) for line in lines])
        else:
            layer = {"type": "shape", "shape": piece.shape, "width": w, "height": h, "fill": "#000000",
                     **piece.extra}
            centred = np.array([[1, 0, -w / 2], [0, 1, -h / 2], [0, 0, 1]], float)
            region = filled_area(layer, centred, _blank_state())
            if region is None:
                from shapely.geometry import box

                region = box(-w / 2, -h / 2, w / 2, h / 2)
        _SHAPES[key] = affinity.rotate(region, piece.rotation, origin=(0, 0))
        if len(_SHAPES) > 4096:
            _SHAPES.clear()
    return _SHAPES[key]


def _placed(piece):
    from shapely import affinity

    return affinity.translate(_outline(piece), piece.x + piece.width / 2, piece.y + piece.height / 2)


def _overlaps(a, b, overlap):
    """Whether two drawn areas overlap by ``overlap`` pixels (both still meet when each is inset by half of it)."""
    inner_a, inner_b = a.buffer(-overlap / 2), b.buffer(-overlap / 2)
    if inner_a.is_empty or inner_b.is_empty:
        return a.intersection(b).area > 0
    return inner_a.intersects(inner_b)


def _nudge(piece, partners, direction, overlap):
    """Move ``piece`` along ``direction`` in whole pixels until it overlaps one of ``partners`` by ``overlap``."""
    from shapely import affinity
    from shapely.prepared import prep

    targets = [_placed(partner) for partner in partners]
    if any(_overlaps(_placed(piece), target, overlap) for target in targets):
        return
    dx, dy = direction
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    dx, dy = dx / length, dy / length
    shape = _outline(piece)
    inner = shape.buffer(-overlap / 2)
    insets = [target.buffer(-overlap / 2) for target in targets]
    # A part thinner than the overlap (a stroke, a whisker) has no inset: it only has to reach into its partner.
    moving = shape if inner.is_empty else inner
    fixed = [prep(target if inner.is_empty or inset.is_empty else inset) for target, inset in zip(targets, insets)]
    last = None
    for step in range(1, MAX_STEPS):
        mx, my = round(dx * step), round(dy * step)
        if (mx, my) == last:
            continue
        last = (mx, my)
        moved = affinity.translate(moving, piece.x + piece.width / 2 + mx, piece.y + piece.height / 2 + my)
        if any(target.intersects(moved) for target in fixed):
            piece.x += mx
            piece.y += my
            return


def _toward(piece, partner):
    ax0, ay0, ax1, ay1 = _box(partner)
    bx0, by0, bx1, by1 = _box(piece)
    return (ax0 + ax1) / 2 - (bx0 + bx1) / 2, (ay0 + ay1) / 2 - (by0 + by1) / 2


# ---------------------------------------------------------------------------------------------------------------
# What the kind says: pieces from the example or from the parts


SHAPE_KEYS = ("path", "path_view", "radius", "sides", "inner_radius", "start_angle", "end_angle", "closed")


def _example_pieces(example, parts, primitive):
    """Pieces for each of the kind's ``parts`` the example names, with the example's shapes, boxes, rotations,
    fills, sides, depths and draw order, and the size of the example's object box."""
    from .geometry import path_box

    boxes, specs, order = {}, {}, []
    objects = {op.get("target") for op in example if op.get("type") == "object" and op.get("action", "set") == "set"}
    for op in example:
        kind = op.get("type")
        if op.get("name") in objects:
            continue
        if kind == "shape" and op.get("name"):
            w, h = op.get("width"), op.get("height")
            if op.get("shape") == "path" and (w is None or h is None):
                w, h = path_box(op["path"])
            boxes[op["name"]] = (op.get("x", 0), op.get("y", 0), w, h)
            specs[op["name"]] = op
            order.append(op["name"])
        elif kind in ("pathfinder", "group") and op.get("name") and op.get("targets"):
            inside = [name for name in op["targets"] if name in boxes]
            if inside:
                x0, y0 = min(boxes[n][0] for n in inside), min(boxes[n][1] for n in inside)
                x1 = max(boxes[n][0] + boxes[n][2] for n in inside)
                y1 = max(boxes[n][1] + boxes[n][3] for n in inside)
                boxes[op["name"]] = (x0, y0, x1 - x0, y1 - y0)
                # A merged or grouped part becomes one placeholder: the shape and colour of its largest piece.
                largest = max(inside, key=lambda n: boxes[n][2] * boxes[n][3])
                specs[op["name"]] = {"type": kind, "fill": specs[largest].get("fill"),
                                     "shape": specs[largest].get("shape")}
                position = min(order.index(name) for name in inside if name in order)
                order = [name for name in order if name not in inside]
                order.insert(position, op["name"])
    pieces, used = {}, []
    for op in example:
        if op.get("type") != "object" or op.get("action") != "part" or op.get("part") not in parts:
            continue
        for name in op.get("targets") or [op.get("target")]:
            if name not in boxes or name not in order:
                continue
            spec, (_, _, w, h) = specs[name], boxes[name]
            if spec["type"] == "shape":
                extra = {key: spec[key] for key in SHAPE_KEYS if key in spec}
                if spec.get("shape") == "path" and "path_view" not in extra:
                    extra["path_view"] = [w, h]
                stroke = spec.get("stroke") if str(spec.get("fill", "")).lower() in ("none", "transparent") else None
                piece = Piece(op["part"], spec.get("shape", "rectangle"), float(w), float(h),
                              float(spec.get("rotation", 0)), extra, None if stroke else spec.get("fill"), stroke,
                              float(spec.get("stroke_width", 1)) if stroke else None)
            else:
                shape = spec.get("shape") if spec.get("shape") not in (None, "path") else primitive
                piece = Piece(op["part"], shape, float(w), float(h), fill=spec.get("fill"))
            piece.side, piece.depth, piece.order = op.get("side"), op.get("depth"), order.index(name)
            pieces.setdefault(op["part"], []).append(piece)
            used.append(boxes[name])
    if not used:
        return {}, None
    x0, y0 = min(b[0] for b in used), min(b[1] for b in used)
    x1, y1 = max(b[0] + b[2] for b in used), max(b[1] + b[3] for b in used)
    return pieces, (x1 - x0, y1 - y0)


def _default_shape(name, build, organic):
    shapes = [shape for shape in build.get("shapes", []) if shape != "path"]
    if name in ROUND:
        return "ellipse"
    if name in LIMB:
        return "capsule" if organic else "rectangle"
    if shapes:
        return shapes[0]
    return "ellipse" if organic else "rounded-rectangle"


def _part_pieces(merged, view, organic):
    """Pieces for a kind without an example: required parts and placed parts, ``count`` of each."""
    build = merged.get("build", {})
    placed = {item["part"] for item in build.get("placements", [])}
    pieces = {}
    for part in merged.get("parts", []):
        name, count = part["name"], part.get("count", 1)
        if not part.get("required") and name not in placed:
            continue
        shape = _default_shape(name, build, organic)
        spread = any(item.get("spread") for item in build.get("placements", []) if item["part"] == name)
        if view == "side" and name in PAIRED_LIMBS and count % 2 == 0:
            made = [Piece(name, shape, 0, 0, depth=depth) for _ in range(count // 2) for depth in ("far", "near")]
            if part.get("side"):
                for piece in made:
                    piece.side = "right" if piece.depth == "far" else "left"
        elif part.get("side") and count == 2 and view == "front":
            made = [Piece(name, shape, 0, 0, side=side) for side in ("left", "right")]
        elif count > 1 and not part.get("required") and not spread:
            made = [Piece(name, shape, 0, 0)]
        else:
            made = [Piece(name, shape, 0, 0) for _ in range(count)]
        pieces[name] = made
    return pieces


def _connections(merged):
    return [tuple(pair) for pair in merged.get("connections", [])]


def _root(pieces, merged):
    """The part the others attach to: no placement of its own and the most connections. None when every part has a
    placement (a cloud's puffs sit on the object's box)."""
    placed = {item["part"] for item in merged.get("build", {}).get("placements", [])}
    degree = {}
    for a, b in _connections(merged):
        for name in (a, b):
            degree[name] = degree.get(name, 0) + 1
    candidates = [name for name in pieces if name not in placed]
    if not candidates:
        return None
    return max(candidates, key=lambda name: (degree.get(name, 0), -list(pieces).index(name)))


def _fallback_anchor(name, root, merged, view):
    """(target, anchor, at, spread) for a part without a placement: the part it connects to, nearest the root."""
    partners = [b if a == name else a for a, b in _connections(merged) if name in (a, b) and a != b]
    target = partners[0] if partners else root
    if root in partners:
        target = root
    count = next((part.get("count", 1) for part in merged.get("parts", []) if part["name"] == name), 1)
    if name in INNER:
        return target, "center", "center", "0.3-0.7" if count > 1 else None
    if count > 1:
        return target, "bottom", "top", "0.15-0.85"
    if name == "head" and view == "side":
        return target, "top-right", "bottom-left", None
    return target, "top", "bottom", None


def _sizes(pieces, root, view):
    """Sizes for pieces with no example box (``w`` and ``h`` still 0): the root a body-sized box (upright for a
    trunk or torso in a front view), the rest a share of the longer side of the part they attach to."""
    def unit(name, seen=()):
        made = pieces[name]
        if made[0].w and made[0].h:
            return max(made[0].w, made[0].h)
        if name == root or not made[0].anchor or made[0].anchor[0] in ("object", name) or name in seen:
            return 100.0
        return unit(made[0].anchor[0], (*seen, name)) if made[0].anchor[0] in pieces else 100.0

    for name in sorted(pieces, key=lambda name: name != root):
        made = pieces[name]
        if made[0].w and made[0].h:
            continue
        if name == root:
            upright = view == "front" and name in ("torso", "trunk", "stem", "shaft", "body")
            w, h = (60, 100) if upright else (100, 60)
        else:
            base = unit(made[0].anchor[0]) if made[0].anchor and made[0].anchor[0] in pieces else 100.0
            share = ((0.18, 0.14) if name in INNER else (0.3, 0.3) if name in ROUND and len(made) > 1 else
                     (0.12, 0.5) if len(made) > 1 or name in LIMB else (0.5, 0.4))
            w, h = share[0] * base, share[1] * base
        for piece in made:
            piece.w, piece.h = float(w), float(h)


# ---------------------------------------------------------------------------------------------------------------
# Layout


def _anchor_point(box, anchor, fraction):
    from .geometry import ANCHORS

    fx, fy = ANCHORS[anchor]
    x0, y0, x1, y1 = box
    if fraction is not None:
        if anchor in ("left", "right"):
            fy = fraction
        else:
            fx = fraction
    return x0 + fx * (x1 - x0), y0 + fy * (y1 - y0), (fx, fy)


def _opposite(anchor):
    from .geometry import ANCHORS

    fx, fy = ANCHORS[anchor]
    return next(name for name, value in ANCHORS.items() if value == (1 - fx, 1 - fy))


def _assign(pieces, root, merged, view):
    """Give every piece what it attaches to: its placement (side-specific first), else a fallback anchor."""
    from .objects import placement_anchor, spread

    placements = merged.get("build", {}).get("placements", [])
    radial = merged.get("symmetry") == "radial"
    for name, made in pieces.items():
        if name == root:
            continue
        options = [item for item in placements if item["part"] == name]
        far = [piece for piece in made if piece.depth == "far"]
        near = [piece for piece in made if piece.depth != "far"]
        slots = max(len(far), len(near)) if far else len(made)
        for piece in made:
            mine = next((item for item in options if item.get("side") == piece.side), None) or next(
                (item for item in options if item.get("side") is None or item.get("mirror")), None)
            if mine:
                target, anchor = placement_anchor(mine["anchor"])
                at, span = mine.get("at") or _opposite(anchor), spread(mine.get("spread"))
                mirrored = bool(mine.get("mirror") and mine.get("side") and piece.side and piece.side != mine["side"])
            else:
                target, anchor, at, span_text = _fallback_anchor(name, root, merged, view)
                span, mirrored = spread(span_text), False
            if target != "object" and target not in pieces:
                target = root or "object"
            index = (far.index(piece) if piece in far else near.index(piece)) if far else made.index(piece)
            fraction = None
            if span and slots > 1:
                fraction = span[0] + (span[1] - span[0]) * index / (slots - 1)
            elif span:
                fraction = (span[0] + span[1]) / 2
            piece.anchor = (target, anchor, at, fraction, mirrored)
            if radial and anchor == "center" and len(made) > 2:
                piece.ring = 360 * made.index(piece) / len(made)


def _rank(pieces, merged):
    """Back-to-front order for pieces the example does not order: by the kind's ``layering`` hints (read as the
    object check reads them), else just above the part they attach to."""
    from .object_check import FAMILIES

    loose = [piece for made in pieces.values() for piece in made if piece.order is None]
    if not loose:
        return
    if len(loose) == sum(len(made) for made in pieces.values()):
        for index, hint in enumerate(merged.get("layering", [])):
            words = hint.casefold().split()
            depth = words.pop(0) if len(words) > 1 and words[0] in ("far", "near") else None
            word = words[-1] if words else ""
            names = set(FAMILIES.get(word, ())) | {word, word[:-1] if word.endswith("s") else word,
                                                    word[:-2] if word.endswith("es") else word,
                                                    word[:-3] + "f" if word.endswith("ves") else word}
            for piece in loose:
                if piece.order is None and piece.part in names and (depth is None or piece.depth == depth):
                    piece.order = index * 10

    def order(piece, seen=()):
        if piece.order is not None:
            return piece.order
        partner = _partner(piece, pieces) if piece.anchor and piece.anchor[0] != "object" else None
        if partner is None or partner is piece or id(partner) in seen:
            return 0
        return order(partner, (*seen, id(piece))) + 0.5

    for piece in loose:
        piece.order = order(piece)


def _partner(piece, pieces):
    target = piece.anchor[0]
    if target == "object":
        return None
    made = pieces[target]
    if len(made) == 1:
        return made[0]
    same = [other for other in made if other.side and other.side == piece.side]
    if same:
        return same[0]
    mine = pieces[piece.part]
    if len(mine) == len(made):
        return made[mine.index(piece)]
    return made[0]


def _layout(pieces, root, merged, k, object_size, overlap):
    """Place every piece at scale ``k``: the root at the origin, then each piece once what it attaches to is placed."""
    for made in pieces.values():
        for piece in made:
            piece.width = max(1, round(piece.w * piece.scale * k))
            piece.height = max(1, round(piece.h * piece.scale * k))
            if piece.stroke:
                piece.stroke_base = piece.stroke_base or piece.stroke_width
                piece.stroke_width = max(0.5, round(piece.stroke_base * piece.scale * k, 2))
    object_box = (0, 0, object_size[0] * k, object_size[1] * k)
    done = set()
    if root in pieces:
        for piece in pieces[root]:
            ew, eh = _envelope(piece)
            piece.x, piece.y = round(ew / 2 - piece.width / 2), round(eh / 2 - piece.height / 2)
        done.add(root)
        rx0, ry0, rx1, ry1 = _box(pieces[root][0])
        object_box = (rx0 + (rx1 - rx0) / 2 - object_box[2] / 2, ry0 + (ry1 - ry0) / 2 - object_box[3] / 2,
                      rx0 + (rx1 - rx0) / 2 + object_box[2] / 2, ry0 + (ry1 - ry0) / 2 + object_box[3] / 2)
    waiting = [name for name in pieces if name not in done]
    while waiting:
        ready = [name for name in waiting if all(piece.anchor[0] in done or piece.anchor[0] == "object"
                                                 for piece in pieces[name])]
        if not ready:
            ready = waiting[:1]
            for piece in pieces[ready[0]]:
                piece.anchor = (root if root in done else "object", *piece.anchor[1:])
        for name in ready:
            for piece in pieces[name]:
                _place(piece, pieces, object_box, overlap)
            done.add(name)
        waiting = [name for name in waiting if name not in done]


def _place(piece, pieces, object_box, overlap):
    target, anchor, at, fraction, mirrored = piece.anchor
    partner = _partner(piece, pieces)
    box = _box(partner) if partner is not None else object_box
    if mirrored:
        from .geometry import ANCHORS

        flip = {value: name for name, value in ANCHORS.items()}
        anchor = flip[(1 - ANCHORS[anchor][0], ANCHORS[anchor][1])]
        at = flip[(1 - ANCHORS[at][0], ANCHORS[at][1])]
        fraction = None if fraction is None else 1 - fraction
    ew, eh = _envelope(piece)
    if piece.ring is not None:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        reach = piece.height / 2 + max(box[2] - box[0], box[3] - box[1]) / 2 * 0.4
        angle = math.radians(piece.ring)
        piece.rotation = piece.ring
        ew, eh = _envelope(piece)
        cx, cy = cx + reach * math.sin(angle), cy - reach * math.cos(angle)
        direction = (-math.sin(angle), math.cos(angle))
    else:
        from .geometry import ANCHORS

        px, py, (fx, fy) = _anchor_point(box, anchor, fraction)
        ax, ay = ANCHORS[at]
        cx, cy = px - (ax - 0.5) * ew, py - (ay - 0.5) * eh
        if at == anchor and partner is not None:
            # A part placed by the same anchor on both sides (a window at body.top, its top there) sits inside.
            if ew <= box[2] - box[0]:
                cx = min(max(cx, box[0] + ew / 2), box[2] - ew / 2)
            if eh <= box[3] - box[1]:
                cy = min(max(cy, box[1] + eh / 2), box[3] - eh / 2)
        if piece.depth == "far" and any(other.depth == "near" for other in pieces[piece.part]):
            cx -= FAR_SHIFT * ew  # side views face right: the far limb shows behind and to the left
        direction = (0.5 - fx, 0.5 - fy)
    piece.x, piece.y = round(cx - piece.width / 2), round(cy - piece.height / 2)
    piece.partner = partner
    if partner is not None:
        if abs(direction[0]) < 1e-9 and abs(direction[1]) < 1e-9:
            direction = _toward(piece, partner)
        _nudge(piece, [partner], direction, overlap)


def _connect(pieces, merged, overlap):
    """Every pair the kind says must touch, checked once more and closed by moving the dependent part (and what
    hangs from it) toward its partner; a part that must touch itself (cloud puffs) closes up on its largest piece."""
    for a, b in _connections(merged):
        if a not in pieces or b not in pieces:
            continue
        if a == b:
            made = sorted(pieces[a], key=lambda piece: -piece.width * piece.height)
            joined = [made[0]]
            for piece in made[1:]:
                if not any(_overlaps(_placed(piece), _placed(other), overlap) for other in joined):
                    _shift(piece, pieces, joined, overlap)
                joined.append(piece)
            continue
        for piece in pieces[a]:
            partners = [other for other in pieces[b] if not other.side or not piece.side or other.side == piece.side]
            partners = partners or pieces[b]
            if any(_overlaps(_placed(piece), _placed(other), overlap) for other in partners):
                continue
            _shift(piece, pieces, partners, overlap)


def _shift(piece, pieces, partners, overlap):
    nearest = min(partners, key=lambda other: _placed(piece).distance(_placed(other)))
    before = (piece.x, piece.y)
    _nudge(piece, [nearest], _toward(piece, nearest), overlap)
    dx, dy = piece.x - before[0], piece.y - before[1]
    if dx or dy:
        for made in pieces.values():
            for other in made:
                if _hangs_from(other, piece):
                    other.x += dx
                    other.y += dy


def _hangs_from(piece, parent):
    seen = set()
    cursor = piece.partner
    while cursor is not None and id(cursor) not in seen:
        if cursor is parent:
            return True
        seen.add(id(cursor))
        cursor = cursor.partner
    return False


def _bounds(pieces):
    boxes = [_box(piece) for made in pieces.values() for piece in made]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _proportions(pieces, merged, rng):
    """Scale each measured part to its target ratio of another part's length; returns ``(part, ratio)`` for the
    ratios of the object's height, which ``_fit`` meets."""
    targets = []
    for item in merged.get("proportions", []):
        if item["part"] not in pieces:
            continue
        low, high = item["min"], item["max"]
        value = (low + high) / 2 if rng is None else rng.uniform(low + (high - low) * SEED_RANGE,
                                                                   high - (high - low) * SEED_RANGE)
        reference = item.get("of", "height")
        if reference == "height":
            targets.append((item["part"], value))
            continue
        if reference not in pieces:
            continue
        size = max(max(p.w * p.scale, p.h * p.scale) for p in pieces[item["part"]])
        base = max(max(p.w * p.scale, p.h * p.scale) for p in pieces[reference])
        for piece in pieces[item["part"]]:
            piece.scale *= value * base / size
    return targets


def _fit(pieces, root, merged, height, object_size, targets):
    """Lay out at the scale that makes the object ``height`` pixels tall, with every height proportion met."""
    k = 1.0
    for _ in range(8):
        _layout(pieces, root, merged, k, object_size, OVERLAP)
        x0, y0, x1, y1 = _bounds(pieces)
        changed = False
        for part, value in targets:
            tallest = max(_box(piece)[3] - _box(piece)[1] for piece in pieces[part])
            want = value * (y1 - y0)
            if abs(tallest - want) > 1:
                for piece in pieces[part]:
                    piece.scale *= want / tallest
                changed = True
        if not changed and abs((y1 - y0) - height) <= 1:
            break
        if not changed:
            k *= height / (y1 - y0)
    _connect(pieces, merged, OVERLAP)


# ---------------------------------------------------------------------------------------------------------------
# The person: head units


# (cx, top, width, height) in head units: x from the figure's centre line, the top from the top of the head. Measured
# from the person kind's example; the body below the head stretches with the head count.
PERSON = {
    "head": (0, 0, .875, 1), "eye": (.1875, .375, .125, .156), "mouth": (0, .719, .3125, .094),
    "torso": (0, .906, 1.5625, 2.75), "upper-arm": (.875, 1.031, .375, 1.75), "lower-arm": (.883, 2.625, .328, 1.625),
    "hand": (.89, 4.094, .406, .531), "upper-leg": (.39, 3.5, .594, 2.031), "lower-leg": (.39, 5.44, .5, 1.875),
    "foot": (.47, 7.19, .75, .3125),
}
PERSON_ORDER = ("upper-leg", "lower-leg", "foot", "upper-arm", "lower-arm", "hand", "torso", "head", "eye", "mouth")
PERSON_FACE = ("eye", "mouth")


def _person_heads(merged, request):
    head = next((item for item in merged.get("proportions", [])
                 if item["part"] == "head" and item.get("of", "height") == "height"), None)
    default = 7.5 if head is None or head["min"] <= 1 / 7.5 <= head["max"] else 2 / (head["min"] + head["max"])
    heads = finite(request.get("head_units", min(12, max(3.7, default))), "head_units", 3.7, 12)
    stylized = head is not None and not head["min"] - 1e-9 <= 1 / heads <= head["max"] + 1e-9
    return heads, stylized


def person_layout(merged, request):
    """Pieces for a person from head units: the 17 standard parts in a front view."""
    heads, stylized = _person_heads(merged, request)
    width = finite(request.get("width_ratio", 1), "width_ratio", .5, 2)
    stretch = (heads - 1) / 6.5
    pieces = {}
    for rank, part in enumerate(PERSON_ORDER):
        cx, top, w, h = PERSON[part]
        if part not in PERSON_FACE and part != "head":
            top, h = 1 + (top - 1) * stretch, h * stretch
        shape = "ellipse" if part in ("head", "eye", "mouth", "hand") else (
            "rounded-rectangle" if part in ("torso", "upper-leg", "lower-leg") else "capsule")
        sides = ("left", "right") if cx else (None,)
        for side in sides:
            centre = -cx if side == "left" else cx
            if part in PERSON_FACE:
                scale_x = 1
            else:
                scale_x = width
            piece = Piece(part, shape, w * scale_x, h, side=side, order=rank)
            piece.extra = {"cx": centre * scale_x, "top": top}
            pieces.setdefault(part, []).append(piece)
    return pieces, heads, stylized


def _person_fit(pieces, merged, height):
    unit = height / max(piece.extra["top"] + piece.h for made in pieces.values() for piece in made)
    for made in pieces.values():
        for piece in made:
            cx, top = piece.extra.pop("cx"), piece.extra.pop("top")
            piece.width, piece.height = max(1, round(piece.w * unit)), max(1, round(piece.h * unit))
            piece.x, piece.y = round(cx * unit - piece.width / 2), round(top * unit)
    for name, made in pieces.items():
        for piece in made:
            partner_part = {"head": "torso", "eye": "head", "mouth": "head", "upper-arm": "torso",
                            "lower-arm": "upper-arm", "hand": "lower-arm", "upper-leg": "torso",
                            "lower-leg": "upper-leg", "foot": "lower-leg"}.get(name)
            if partner_part:
                partners = pieces[partner_part]
                piece.partner = next((p for p in partners if p.side == piece.side), partners[0])
    _connect(pieces, merged, OVERLAP)


# ---------------------------------------------------------------------------------------------------------------
# Colours


def _ramp(color):
    from .colors import hex_of, mix, parse

    base = parse(color)
    return [hex_of(mix(base, parse("#000000"), 0.45)), hex_of(mix(base, parse("#000000"), 0.2)), hex_of(base),
            hex_of(mix(base, parse("#ffffff"), 0.25)), hex_of(mix(base, parse("#ffffff"), 0.5))]


def _palette(build, request):
    if request.get("color"):
        return _ramp(request["color"])
    name = build.get("palette") or ""
    if name.startswith("natural:"):
        from .natural_guidance import PALETTES

        colors = PALETTES.get(name[8:])
        if colors:
            return colors[:5] if len(colors) >= 5 else (colors * 5)[:5]
    if name:
        from .resources import PALETTES

        found = PALETTES.get(name)
        values = list(found.values()) if isinstance(found, dict) else list(found or [])
        values = [value for value in values if isinstance(value, str)]
        if len(values) >= 3:
            return (values * 5)[:5]
    return ["#3d405b", "#6b6f8a", "#9a9db5", "#c4c6d6", "#e4e5ee"]


def _color(piece, depth, ramp, features):
    if piece.part in features:
        return ramp[0]
    index = (2, 3, 1)[depth % 3]
    if piece.depth == "far":
        index = max(0, index - 1)
    return ramp[index]


# ---------------------------------------------------------------------------------------------------------------
# The plan


def kind_view(kind, kinds):
    from .objects import descends

    return "side" if any(descends(kind, ancestor, kinds) for ancestor in SIDE_VIEW) else "front"


def _names(pieces, name):
    """Layer names NAME-PART, numbered when a part has several pieces, with -far/-near or -left/-right."""
    for part, made in pieces.items():
        counts = {}
        for piece in made:
            tag = piece.depth or piece.side
            counts[tag] = counts.get(tag, 0) + 1
        seen = {}
        for piece in made:
            tag = piece.depth or piece.side
            seen[tag] = seen.get(tag, 0) + 1
            suffix = (f"-{seen[tag]}" if counts[tag] > 1 else "") + (f"-{tag}" if tag else "")
            piece.name = f"{name}-{part}{suffix}"


def _free(project, name, others=()):
    """``name``, or ``name-2``, ``name-3`` … when the document (or this plan) already has a layer of that name."""
    def taken(candidate):
        return candidate in others or (project is not None and project.find_layer(candidate) is not None) or any(
            layer["name"].startswith(candidate + "-") for layer in (project.state["layers"] if project else []))

    if not taken(name):
        return name
    index = 2
    while taken(f"{name}-{index}"):
        index += 1
    return f"{name}-{index}"


def _frame(request, project, aspect):
    """``(x, y, height)`` for an object ``aspect`` wide per pixel of height, from box | x, y, height. Without any
    of them it fits a centred box of 80% of the canvas width and 60% of its height (400 px tall at the origin
    without a document); with a height and no x, y it is centred on the canvas."""
    canvas = project.state["canvas"] if project is not None else None
    box = request.get("box")
    if box is None and canvas and not any(key in request for key in ("x", "y", "height")):
        box = [canvas["width"] * 0.1, canvas["height"] * 0.2, canvas["width"] * 0.8, canvas["height"] * 0.6]
        request = {**request, "box": box}
    if box is not None:
        require(isinstance(box, list) and len(box) == 4, "box is [x, y, width, height]", field="box")
        bx, by, bw, bh = (finite(value, "box", -1e6, 1e6) for value in box)
        require(bw > 0 and bh > 0, "box needs a positive width and height", field="box")
        require(not any(key in request for key in ("x", "y", "height")), "Give box, or x, y and height, not both",
                field="box")
        height = min(bh, bw / aspect) if aspect > 0 else bh
        return bx + (bw - height * aspect) / 2, by + (bh - height) / 2, height
    height = finite(request.get("height", canvas["height"] * 0.6 if canvas else DEFAULT_HEIGHT), "height", 8, 16000)
    width = height * aspect
    x = finite(request["x"], "x", -1e6, 1e6) if "x" in request else ((canvas["width"] - width) / 2 if canvas else 0)
    y = finite(request["y"], "y", -1e6, 1e6) if "y" in request else ((canvas["height"] - height) / 2 if canvas else 0)
    return x, y, height


def plan(request, project=None, depth=0, taken=()):
    """The scaffold for one object (see the module docstring): ``{kind, name, view, box, operations, parts,
    next_steps}``; nothing is applied."""
    from .automation import bounded_object
    from .normalize import illustration_alias
    from .objects import descends, merged as merge, registry, resolve_kind

    require(isinstance(request, dict), "object-plan takes an object of fields", field="request")
    notes = []
    request = illustration_alias(request, notes.append)
    bounded_object(request, set(FIELDS), "Unknown object-plan field")
    require(request.get("illustration") in (None, "house", "plain"), "illustration is house or plain",
            field="illustration", allowed=["house", "plain"])
    require(isinstance(request.get("kind"), str), "object-plan needs kind (dog, guitar, person …); vixl objects lists "
            "them", field="kind")
    kinds = registry(getattr(project, "_workspace", None))
    kind = resolve_kind(request["kind"], kinds)
    fields = merge(kind, kinds)
    require(not fields.get("texture"), f"{kind} is a texture (a surface pattern for parts), not an object to plan",
            field="kind")
    person = descends(kind, "person", kinds)
    if request.get("template") is not None:
        require(request["template"] == "figure-plan" and person, "template figure-plan is the person blocking figure; "
                "it takes kind person", field="template")
        spec = {key: value for key, value in request.items() if key not in ("kind", "template", "apply")}
        return figure_template(spec)
    view = kind_view(kind, kinds)
    require(request.get("view", view) == view, f"A {kind} is planned in a {view} view"
            + (" (facing right)" if view == "side" else "") + f"; object-plan has no {request.get('view')} view of it",
            field="view", allowed=[view])
    build = fields.get("build", {})
    seed = request.get("seed")
    require(seed is None or (isinstance(seed, int) and not isinstance(seed, bool)), "seed is a whole number",
            field="seed")
    ramp = _palette(build, request)
    organic = descends(kind, "organic", kinds)
    name = request.get("name") or kind
    require(isinstance(name, str) and 0 < len(name) <= 64, "name is 1-64 characters", field="name")
    name = _free(project, name, taken)
    parts = {part["name"] for part in fields.get("parts", [])}

    def lay(height):
        """Fresh pieces laid out ``height`` pixels tall: ``(pieces, root, head units, stylized)``."""
        rng = random.Random(seed) if seed is not None else None
        if person:
            pieces, heads, stylized = person_layout(fields, request)
            _person_fit(pieces, fields, height)
            return pieces, "torso", heads, stylized
        primitive = "ellipse" if organic else "rounded-rectangle"
        pieces, object_size = _example_pieces(build.get("example") or [], parts, primitive)
        missing = [part for part in fields.get("parts", []) if part.get("required") and part["name"] not in pieces]
        if pieces and missing:
            pieces.update(_part_pieces({**fields, "parts": missing}, view, organic))
        if not pieces:
            pieces = _part_pieces(fields, view, organic)
        if not pieces and fields.get("parts"):
            # Every part is optional and unplaced (a coral's branches): plan them all.
            pieces = _part_pieces({**fields, "parts": [{**part, "required": True} for part in fields["parts"]]},
                                  view, organic)
        below = sorted(name for name, entry in kinds.items() if entry.get("parent") == kind)
        require(pieces, f"The {kind} kind lists no parts to plan" + (
            f"; plan one of its kinds ({', '.join(below[:8])})" if below else
            "; draw it and declare it with {type: object, target: GROUP, kind: KIND}"), field="kind",
            suggestions=below[:8])
        root = _root(pieces, fields)
        _assign(pieces, root, fields, view)
        _rank(pieces, fields)
        _sizes(pieces, root, view)
        if rng is not None:
            for made in pieces.values():
                factor = rng.uniform(1 - SEED_SIZE, 1 + SEED_SIZE)
                for piece in made:
                    piece.scale *= factor
        targets = _proportions(pieces, fields, rng)
        size = object_size or ((pieces[root][0].w, pieces[root][0].h) if root else (100.0, 60.0))
        _fit(pieces, root, fields, height, size, targets)
        return pieces, root, None, False

    _, _, height = _frame(request, project, 1.0)
    pieces, root, heads, stylized = lay(height)
    x0, y0, x1, y1 = _bounds(pieces)
    x, y, final = _frame(request, project, (x1 - x0) / max(1e-9, y1 - y0))
    if abs(final - height) > 1:
        pieces, root, heads, stylized = lay(final)
        x0, y0, x1, y1 = _bounds(pieces)
    dx, dy = round(x - x0), round(y - y0)
    for made in pieces.values():
        for piece in made:
            piece.x += dx
            piece.y += dy
    _names(pieces, name)
    _paint(pieces, root, fields, ramp, request)
    result = _operations(kind, name, pieces, fields, stylized)
    x0, y0, x1, y1 = _bounds(pieces)
    result.update(view=view, box=[round(x0), round(y0), round(x1 - x0), round(y1 - y0)])
    if heads is not None:
        result["head_units"] = heads
    _nest(result, request, project, depth, pieces, taken)
    for finish in FINISHERS:
        result["operations"] += list(finish(result, project, request, depth))
    if notes:
        result["normalized"] = [{"field": "outline", "reason": text} for text in notes]
    return result


def illustration_finish(result, project, request, depth):
    """The house illustration finish (``craft.illustration_style``) as operations after the parts: parts too small for a
    line of that width are left out of the outline (``outline: none``, as a flat illustration draws an eye), the
    wobble (``irregular``) on the object's own filled parts, then one ``outline`` with the policy, ink colour and width
    of the house style and its occasional extra lines, so the outline follows the wobbled parts, and last a hard
    ``drop-shadow`` on the object (a sub-object leaves it to its object, which casts one shadow for everything).
    Nothing without a document with a house style, or with ``illustration: plain``."""
    from . import craft

    if project is None or not craft.illustration_on(project, request.get("illustration")):
        return []
    name = result["name"]
    own = {layer for layers in result["parts"].values() for layer in layers}
    key = f"illustration/{result['kind']}/{name}/{request.get('seed')}"
    style = craft.illustration_style(project, result["box"], random.Random(key))
    shapes = {op["name"]: op for op in result["operations"] if op["type"] == "shape" and op["name"] in own}
    operations = []
    for op in [op for op in result["operations"] if op["type"] == "object" and op.get("action") == "part"
               and set(op["targets"]) <= own]:
        size = max(min(shapes[layer]["width"], shapes[layer]["height"]) for layer in op["targets"])
        if craft.illustration_small(style["stroke_width"], size):
            operations.append({**op, "outline": "none"})
    solid = [layer for layer, op in shapes.items() if op.get("fill", "transparent") != "transparent"]
    if solid and style["irregular"]:
        seed = request["seed"] if isinstance(request.get("seed"), int) and request["seed"] >= 0 else zlib.crc32(key.encode())
        operations.append({"type": "irregular", "targets": solid, "seed": seed, **style["irregular"]})
    operations.append({"type": "object", "action": "outline", "target": name, "outline": style["policy"],
                       "outline_color": style["stroke"], "outline_width": style["stroke_width"],
                       **({"outline_lines": style["strokes"]} if style["strokes"] else {})})
    if depth == 0 and style["shadow"]:
        operations.append({"type": "layer-style", "target": name, "name": "drop-shadow", "settings": style["shadow"]})
    return operations


FINISHERS.append(illustration_finish)


def _paint(pieces, root, fields, ramp, request):
    from .object_check import FAMILIES

    features = set(FAMILIES["features"]) | set(PERSON_FACE)
    levels = {}

    def level(piece):
        if id(piece) not in levels:
            levels[id(piece)] = 0 if piece.partner is None or piece.partner is piece else level(piece.partner) + 1
        return levels[id(piece)]

    for made in pieces.values():
        for piece in made:
            if piece.stroke:
                continue
            if piece.fill is None or request.get("color"):
                piece.fill = _color(piece, level(piece), ramp, features)


def _operations(kind, name, pieces, fields, stylized):
    ordered = sorted((piece for made in pieces.values() for piece in made), key=lambda piece: piece.order)
    operations = []
    for piece in ordered:
        op = {"type": "shape", "shape": piece.shape, "name": piece.name, "x": piece.x, "y": piece.y,
              "width": piece.width, "height": piece.height}
        if piece.rotation:
            op["rotation"] = round(piece.rotation, 2)
        op.update({key: value for key, value in piece.extra.items() if key not in ("cx", "top")})
        if piece.stroke:
            op.update(fill="transparent", stroke=piece.stroke, stroke_width=piece.stroke_width)
        else:
            op["fill"] = piece.fill
        operations.append(op)
    operations.append({"type": "group", "name": name, "targets": [piece.name for piece in ordered]})
    operations.append({"type": "object", "target": name, "kind": kind, **({"stylized": True} if stylized else {})})
    named = {}
    for piece in ordered:
        named.setdefault((piece.part, piece.side, piece.depth), []).append(piece.name)
    for (part, side, depth), layers in named.items():
        operations.append({"type": "object", "action": "part", "targets": layers, "part": part,
                           **({"side": side} if side else {}), **({"depth": depth} if depth else {})})
    parts = {}
    for piece in ordered:
        parts.setdefault(piece.part, []).append(piece.name)
    return {"kind": kind, "name": name, "operations": operations, "parts": parts,
            "next_steps": _next_steps(kind, name, pieces, fields)}


def _next_steps(kind, name, pieces, fields):
    build = fields.get("build", {})
    steps = []
    for part, made in pieces.items():
        placement = next((item for item in build.get("placements", []) if item["part"] == part), None)
        where = ""
        if placement:
            where = f" at {placement['anchor']}" + (f", its {placement['at']} there" if placement.get("at") else "") + (
                f", spread {placement['spread']}" if placement.get("spread") else "") + (
                f" ({placement['note']})" if placement.get("note") else "")
        partner = made[0].partner
        steps.append({"part": part, "layers": [piece.name for piece in made], "placeholder": made[0].shape,
                      "do": f"Draw the {part}{where} over the {made[0].shape} placeholder (edit it in place with "
                            f"{{type: shape, target: {made[0].name}, …}} or replace it and name the new layer with "
                            f"{{type: object, action: part, part: {part}}})"
                            + (f", keeping it overlapping the {partner.part} by a few pixels" if partner else "")})
    approach = list(build.get("approach", []))[:3]
    return {"approach": approach, "parts": steps,
            "then": [f"{{type: object, action: outline, target: {name}}} applies the {kind}'s outline policy",
                     f"vixl_check(checks=['object']) measures {name} against the kind; "
                     f"vixl_render(isolate=['{name}'], views=['parts']) shows each part"]}


def _nest(result, request, project, depth, pieces, taken):
    """Plan each ``with`` sub-object and put it in the object's group, in front of the parts."""
    items = request.get("with") or []
    require(isinstance(items, list) and len(items) <= MAX_WITH, f"with is a list of at most {MAX_WITH} sub-objects",
            field="with")
    if not items:
        return
    require(depth < MAX_NESTING, f"Sub-objects nest at most {MAX_NESTING} deep", field="with")
    from .objects import placement_anchor

    group = next(op for op in result["operations"] if op["type"] == "group" and op["name"] == result["name"])
    position = result["operations"].index(group)
    used = set(taken) | {result["name"], *(piece.name for made in pieces.values() for piece in made)}
    x0, y0, w, h = result["box"]
    result["sub_objects"] = []
    for item in items:
        item = {"kind": item} if isinstance(item, str) else item
        require(isinstance(item, dict) and isinstance(item.get("kind"), str)
                and set(item) <= {"kind", "name", "height", "anchor", "at"},
                "with entries are a kind or {kind, name?, height?, anchor?, at?}", field="with")
        size = finite(item.get("height", h / 2), "with.height", 8, 16000)
        anchor = placement_anchor(item.get("anchor", "object.center"))
        require(anchor is not None, "with.anchor is PART.ANCHOR or object.ANCHOR (object.center …)", field="with")
        target, point = anchor
        if target == "object":
            box = (x0, y0, x0 + w, y0 + h)
        else:
            require(target in pieces, f"with.anchor names {target!r}, which the plan has no part for; parts: "
                    f"{', '.join(pieces)}", field="with")
            box = _box(pieces[target][0])
        from .geometry import ANCHORS, canonical_anchor

        at = canonical_anchor(item.get("at") or _opposite(point))
        require(at is not None, "with.at is an anchor (top, center, bottom-left …)", field="with")
        sub_name = item.get("name") or f"{result['name']}-{resolve(item['kind'], project)}"
        sub = plan({"kind": item["kind"], "name": sub_name, "x": 0, "y": 0, "height": size,
                    **({"illustration": request["illustration"]} if "illustration" in request else {})},
                   project, depth + 1, tuple(used))
        sw, sh = sub["box"][2], sub["box"][3]
        px, py = box[0] + ANCHORS[point][0] * (box[2] - box[0]), box[1] + ANCHORS[point][1] * (box[3] - box[1])
        ox, oy = round(px - ANCHORS[at][0] * sw), round(py - ANCHORS[at][1] * sh)
        for op in sub["operations"]:
            if op["type"] == "shape":
                op["x"] += ox
                op["y"] += oy
        sub["box"] = [sub["box"][0] + ox, sub["box"][1] + oy, sw, sh]
        used |= {op.get("name") for op in sub["operations"] if op.get("name")}
        result["operations"][position:position] = sub["operations"]
        position += len(sub["operations"])
        group["targets"].append(sub["name"])
        result["sub_objects"].append({key: sub[key] for key in ("kind", "name", "box", "parts")})


def resolve(kind, project):
    from .objects import registry, resolve_kind

    return resolve_kind(kind, registry(getattr(project, "_workspace", None)), field="with")


def run(project, request):
    """Plan and, with ``apply: true``, apply the batch to ``project`` as one undo step."""
    result = plan(request, project)
    if request.get("apply"):
        applied = project.apply(result["operations"])
        result["applied"] = True
        for key in ("warnings", "normalized"):
            if applied.get(key):
                result[key] = applied[key]
    return result


def dispatch(session, request, document=None):
    """The ``object-plan`` workflow: reads the open document (when there is one) for its canvas and free names."""
    require(type(request.get("apply", False)) is bool, "apply must be true or false", field="apply")
    if request.get("apply"):
        with session.project(write=True, document=document) as project:
            return run(project, request)
    if document is None and getattr(session, "path", None) is None:
        return plan(request)
    with session.project(document=document) as project:
        return plan(request, project)


def command(project, request):
    """``vixl object plan`` (parsed by the CLI into ``request``): ``(result, changed)``."""
    if request.get("apply"):
        require(project is not None, "--apply needs a document: vixl new FILE or -p FILE", "no_project")
        return run(project, request), True
    return plan(request, project), False
