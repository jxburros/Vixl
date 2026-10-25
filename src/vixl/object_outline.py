"""Outline policy of a declared object: one outline around its silhouette, or every part outlined alike.

The policy lives on the object record: ``outline`` (``silhouette``, ``parts`` or ``none``; absent means the kind's
default, from the taxonomy's ``outline`` entry: ``silhouette: true`` reads silhouette, ``internal`` thin, none and
same read ``interior`` thin, hide and show), ``interior`` (``hide``, ``thin`` or ``show``: the part strokes inside a
silhouette), ``outline_color`` and ``outline_width``. A part may override it on its ``object_part``: ``outline:
none`` leaves the part out (not in the silhouette, its stroke untouched), ``outline: parts`` gives it the full
outline, and ``interior`` picks its own interior.

``outline_lines`` adds thin lines inside the outline, parallel to it (``[{gap, width}]``: a double or triple line): one
generated ``NAME/outline-N`` path layer each, inset from the silhouette by the outline's inner edge, the gaps and the
widths before them, and drawn again with the outline.

``{type: object, action: outline}`` applies the policy. Under silhouette it writes one ``NAME/outline`` path layer,
the object's top child, marked ``generated: {by: object-outline}``: the union of the filled areas the object's
layers draw (sub-objects included, generated outlines not) with holes filled, stroked and unfilled. Line work (an
open shape, or a shape without a fill: ``geometry.default_fill``) adds no area and keeps its stroke. The strokes of
the object's other shape layers are stored on the record (``outlined.strokes``) and replaced: cleared (hide),
thinned to 40% of the outline width (thin) or set to the outline (show, and every part under parts). A pathfinder
layer has no stroke; only the silhouette outlines it. ``outline: none`` and ``action: outline-remove`` put the
strokes back and delete the layer.

``outlined.hash`` is the hash of the object's geometry: its subtree without paint (fills, strokes, effects) and
without generated outlines. After every apply ``refresh`` re-applies the policy to an object whose hash changed,
in the same history step, so the outline follows a moved, resized or added part and undo takes both back. While a
policy is applied it owns the part strokes: a part styled by hand keeps its stroke only with ``outline: none``.
The object check reports part strokes that show inside a silhouette (``object.outline-seam``), part outlines that
differ by more than 25% under parts (``object.outline-weight``) and an outline drawn for other geometry
(``object.outline-stale``).
"""

from copy import deepcopy
import math

import numpy as np

from .errors import VixlError, require

POLICIES = ("silhouette", "parts", "none", "inherit")
INTERIORS = ("hide", "thin", "show")
FIELDS = ("outline", "interior", "outline_color", "outline_width", "outline_lines")
GENERATED = "object-outline"
MAX_LINES = 3
THIN = 0.4
WEIGHT_TOLERANCE = 0.25
DEFAULT_COLOR = "#1d1d24"
INTERNAL = {"thin": "thin", "none": "hide", "same": "show"}
# The stroke fields a policy replaces and restoring puts back.
STROKE_KEYS = ("stroke", "stroke_width", "stroke_align", "dash", "dash_offset", "dash_fit", "line_cap", "line_join",
               "miter_limit", "strokes", "width_profile", "taper_start", "taper_end")
# Fields that change how a layer is painted or named, not where it draws: left out of the geometry hash. ``object``
# holds the outline state itself.
PAINT_KEYS = frozenset(STROKE_KEYS + ("fill", "fill_gradient", "blend", "effects", "styles", "name", "role",
                                      "allow_overlap", "allow_crop", "detached_ok", "alt", "decorative", "object"))
# Layer types that draw no area of their own (a text label inside an object is not part of its outline).
NO_AREA = ("group", "text", "adjustment")
MAX_NODES = 8192
MIN_HOLE = 16


def generated(layer):
    return (layer.get("generated") or {}).get("by") == GENERATED


def default_policy(kind, kinds):
    """``(outline, interior)`` the kind's taxonomy ``outline`` entry stands for."""
    from .objects import merged

    entry = merged(kind, kinds).get("outline", {}) if kind in kinds else {}
    interior = INTERNAL.get(entry.get("internal"), "thin")
    if entry.get("silhouette"):
        return "silhouette", interior
    return ("parts" if entry.get("internal") in ("thin", "same") else "none"), interior


def policy(project, group):
    """``(outline, interior)`` for an object: its record's choices over its kind's default."""
    from .objects import registry

    record = group["object"]
    outline, interior = default_policy(record["kind"], registry(getattr(project, "_workspace", None)))
    return record.get("outline", outline), record.get("interior", interior)


def _children(project):
    children = {}
    for layer in project.state["layers"]:
        children.setdefault(layer.get("parent"), []).append(layer)
    return children


def _subtree(group, children):
    found, pending = [], [group["id"]]
    while pending:
        for child in children.get(pending.pop(), []):
            found.append(child)
            pending.append(child["id"])
    return found


def owned(project, group, children=None):
    """The object's own layers: below its group and not inside a sub-object, generated outlines left out."""
    from .objects import record

    children = children if children is not None else _children(project)
    found, pending = [], [group["id"]]
    while pending:
        for child in children.get(pending.pop(), []):
            if record(child) or generated(child):
                continue
            found.append(child)
            pending.append(child["id"])
    return found


def override(layer, index, group):
    """The outline override of the nearest part at or above ``layer`` inside ``group``: ``{outline?, interior?}``."""
    item = layer
    while item is not None and item is not group:
        part = item.get("object_part")
        if part:
            return {key: part[key] for key in ("outline", "interior") if key in part}
        item = index.get(item.get("parent"))
    return {}


def line_work(layer, state):
    """Whether a shape layer is drawn by its stroke alone: an open shape or a shape whose fill is transparent."""
    from .design import resolve_color
    from .geometry import default_fill
    from .render import color

    if layer["type"] != "shape" or layer.get("fill_gradient"):
        return False
    try:
        return color(resolve_color(default_fill(layer), state))[3] == 0
    except VixlError:
        return False


def stroke_width(layer, state):
    """The width of the stroke a shape layer draws (0 for none or a transparent one)."""
    from .design import resolve_color
    from .render import color

    paint = layer.get("stroke", "transparent")
    try:
        visible = color(resolve_color(paint, state))[3] > 0
    except VixlError:
        visible = False
    return float(layer.get("stroke_width", 1)) if visible else 0.0


def strokable(project, group, children=None):
    """The object's shape layers whose strokes the policy sets: not line work, not left out by ``outline: none``."""
    index = {layer["id"]: layer for layer in project.state["layers"]}
    return [layer for layer in owned(project, group, children)
            if layer["type"] == "shape" and not line_work(layer, project.state)
            and override(layer, index, group).get("outline") != "none"]


def mode(outline, interior, part):
    """How one part's stroke is drawn: hide, thin or show."""
    if part.get("outline") == "parts" or outline == "parts":
        return "show"
    return part.get("interior", interior)


def geometry_hash(project, group, children=None):
    from .hashing import content_hash

    children = children if children is not None else _children(project)
    return content_hash([{key: value for key, value in layer.items() if key not in PAINT_KEYS}
                         for layer in _subtree(group, children) if not generated(layer)])


# ---------------------------------------------------------------------------------------------------------------
# The silhouette


def _flatten(contour, transform):
    """A closed point list (first point repeated last) for a contour of line and cubic segments."""
    from .geometry import bezier_points

    points = [tuple(contour[0][0])]
    for segment in contour:
        if len(segment) == 2:
            points.append(tuple(segment[1]))
            continue
        length = sum(math.dist(a, b) for a, b in zip(segment, segment[1:]))
        steps = max(2, min(64, math.ceil(length / 2)))
        points.extend(map(tuple, bezier_points(segment, [i / steps for i in range(1, steps + 1)]).tolist()))
    if points[-1] != points[0]:
        points.append(points[0])
    moved = transform @ np.vstack([np.asarray(points, float).T, np.ones(len(points))])
    return [(float(x), float(y)) for x, y in moved[:2].T]


def filled_area(item, transform, state):
    """The area ``item`` fills (no stroke), mapped by ``transform``, as a shapely geometry; None for line work, text,
    groups and adjustments. A layer whose outline cannot be traced (an image, a pathfinder with strokes) is its box."""
    from .booleans import Unsupported
    from .pathfinder_geometry import _close, pathfinder_outline, shape_contours
    from .render import rest_size
    from .vector_boolean import filled_region

    if item["type"] in NO_AREA or (item["type"] == "shape" and line_work(item, state)):
        return None
    w, h = rest_size(item)
    box = [_close([(0, 0), (w, 0), (w, h), (0, h)])]
    try:
        contours = (shape_contours(item) if item["type"] == "shape" else
                    pathfinder_outline(item, state) if item["type"] == "pathfinder" else box)
    except (Unsupported, VixlError, ValueError, KeyError):
        contours = box
    rings = [_flatten(contour, transform) for contour in contours if contour]
    rings = [ring for ring in rings if len(ring) > 3]
    if not rings:
        return None
    try:
        region = filled_region(rings)
    except ValueError:
        return None
    return None if region.is_empty else region


def _shown(item, index, stop):
    while item is not None and item["id"] != stop:
        if not item["visible"] or item["opacity"] <= 0:
            return False
        item = index.get(item.get("parent"))
    return True


def silhouette(project, group, children=None):
    """The object's outline in its group's content space: the union of what its layers fill. A hole the background
    shows through (a cup handle's) stays; a sliver smaller than ``MIN_HOLE`` square pixels between parts is filled."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from .affine import layer_matrix
    from .checks import group_matrix
    from .render import resolve_layout, resolved_layers

    children = children if children is not None else _children(project)
    state_index = {layer["id"]: layer for layer in project.state["layers"]}
    left_out = set()
    for layer in _subtree(group, children):
        if override(layer, state_index, group).get("outline") == "none":
            left_out.add(layer["id"])
    wanted = {layer["id"] for layer in _subtree(group, children) if not generated(layer)} - left_out
    layers = resolved_layers(project)
    local = resolve_layout(project, layers=layers)
    index = {item["id"]: item for item in layers}
    inner = np.linalg.inv(group_matrix({"parent": group["id"]}, index, local))
    regions = []
    for item in layers:
        if item["id"] not in wanted or not _shown(item, index, group["id"]):
            continue
        transform = inner @ group_matrix(item, index, local) @ layer_matrix(item, local[item["id"]])
        region = filled_area(item, transform, project.state)
        if region is not None:
            regions.append(region)
    if not regions:
        return None
    merged = unary_union(regions)
    pieces = list(merged.geoms) if merged.geom_type in ("MultiPolygon", "GeometryCollection") else [merged]
    return unary_union([Polygon(piece.exterior, [ring for ring in piece.interiors if Polygon(ring).area >= MIN_HOLE])
                        for piece in pieces if piece.geom_type == "Polygon"])


def _rings(piece):
    return [list(ring.coords)[:-1] for ring in (piece.exterior, *piece.interiors)]


def _path(region):
    """``(x, y, width, height, path data)`` of a silhouette: one closed subpath per ring, in its own box."""
    from .geometry import compact_number

    pieces = [piece for piece in (list(region.geoms) if region.geom_type == "MultiPolygon" else [region])
              if not piece.is_empty]
    rings = [ring for piece in pieces for ring in _rings(piece)]
    if sum(len(ring) for ring in rings) > MAX_NODES:
        rings = [ring for piece in pieces for ring in _rings(piece.simplify(0.25))]
    minx, miny, maxx, maxy = region.bounds
    x0, y0 = math.floor(minx), math.floor(miny)
    width, height = max(1, math.ceil(maxx - x0)), max(1, math.ceil(maxy - y0))
    data = " ".join("M" + " L".join(f"{compact_number(x - x0, 2)} {compact_number(y - y0, 2)}" for x, y in ring)
                    + " Z" for ring in rings if len(ring) > 2)
    return x0, y0, width, height, data


def outline_layer(project, group, children=None):
    children = children if children is not None else _children(project)
    return next((child for child in children.get(group["id"], [])
                 if generated(child) and "line" not in child["generated"]), None)


def check_lines(value, field="outline_lines"):
    """``outline_lines`` is at most ``MAX_LINES`` of ``{gap, width}``, both positive pixel numbers."""
    from .model import is_number

    require(isinstance(value, list) and len(value) <= MAX_LINES
            and all(isinstance(line, dict) and set(line) == {"gap", "width"}
                    and all(is_number(line[key]) and 0 < line[key] <= 100 for key in line) for line in value),
            f"{field} is up to {MAX_LINES} lines of {{gap, width}} in pixels (each above 0, up to 100)", field=field)


def _write(project, group, region, color, width, children):
    """Write or update the object's outline layer; it stays the top child of the group."""
    from .model import new_layer
    from .operations import append_layer, default_name

    x, y, w, h, data = _path(region)
    require(data, f"{group['name']!r} has no filled area to outline", field="target")
    existing = outline_layer(project, group, children)
    if existing is not None:
        existing.update(x=x, y=y, width=w, height=h, path=data, path_view=[w, h])
        return existing
    layer = new_layer(default_name(project, f"{group['name']}/outline"), "shape", w, h, shape="path", path=data,
                      path_view=[w, h], fill="transparent", stroke=color, stroke_width=width, x=x, y=y, parent=group["id"], role="decoration", generated={"by": GENERATED})
    append_layer(project, layer)
    _on_top(project, group, layer)
    return layer


def _on_top(project, group, layer):
    layers = project.state["layers"]
    siblings = [i for i, item in enumerate(layers) if item.get("parent") == group["id"] and item is not layer]
    if siblings:
        layers.remove(layer)
        layers.insert(max(siblings) + 1, layer)


def _drop(project, group, children=None, *, outline=True, lines=True):
    """Delete the generated layers of an object: its outline and its extra lines (either can be left out)."""
    from .operations import forget_layers

    children = children if children is not None else _children(project)
    gone = {child["id"] for child in children.get(group["id"], [])
            if generated(child) and (lines if "line" in child["generated"] else outline)}
    if gone:
        project.state["layers"][:] = [layer for layer in project.state["layers"] if layer["id"] not in gone]
        forget_layers(project, gone)
        if project.state.get("active_layer") in gone:
            project.state["active_layer"] = group["id"]


def insets(lines, edge):
    """``[(inset, width)]`` for extra lines: the distance of each line's centre from the silhouette, given where the
    outline's ink ends (``edge``) and each line's ``gap`` from the ink before it."""
    found, at = [], float(edge)
    for line in lines:
        at += line["gap"] + line["width"] / 2
        found.append((round(at, 3), line["width"]))
        at += line["width"] / 2
    return found


def draw_lines(project, group, region, color, lines, edge):
    """Write the extra lines inside ``region`` (the group's silhouette): one unfilled path layer per line on top of the
    group's layers, ``generated`` so the geometry hash and the outline policy leave it alone. A line the shape is too
    thin for ends the series. Returns the layers drawn."""
    from .model import new_layer
    from .operations import append_layer, default_name

    made = []
    for number, (inset, width) in enumerate(insets(lines, edge), 1):
        inner = region.buffer(-inset, join_style=1)
        if inner.is_empty:
            break
        x, y, w, h, data = _path(inner)
        if not data:
            break
        layer = new_layer(default_name(project, f"{group['name']}/outline-{number}"), "shape", w, h, shape="path",
                          path=data, path_view=[w, h], fill="transparent", stroke=color, stroke_width=width, x=x, y=y,
                          parent=group["id"], role="decoration", generated={"by": GENERATED, "line": number})
        append_layer(project, layer)
        _on_top(project, group, layer)
        made.append(layer)
    return made


# ---------------------------------------------------------------------------------------------------------------
# Applying and removing


def _paint(layer, how, color, width):
    for key in STROKE_KEYS:
        layer.pop(key, None)
    if how != "hide":
        # Plain stroke fields only: a vector-stroke field (line_join, dash …) would make every export expand the
        # stroke into a filled outline.
        layer.update(stroke=color, stroke_width=round(width * (THIN if how == "thin" else 1), 2))


def _restore_strokes(project, record):
    index = {layer["id"]: layer for layer in project.state["layers"]}
    for ident, original in (record.get("outlined") or {}).get("strokes", {}).items():
        layer = index.get(ident)
        if layer is None:
            continue
        for key in STROKE_KEYS:
            layer.pop(key, None)
        layer.update(deepcopy(original))


def default_width(group, outline="silhouette"):
    """The outline width of an object that sets none, to half a pixel and at least 1 px: the house illustration's part
    line (``craft.illustration.outline.width_share``) of the object's larger side under ``parts``, and its
    ``silhouette_share`` under ``silhouette``."""
    from . import house_style

    rule = house_style.rule("illustration")["outline"]
    side = max(float(group.get("content_width", group["width"])), float(group.get("content_height", group["height"])))
    return max(1.0, round(side * rule["width_share" if outline == "parts" else "silhouette_share"] * 2) / 2)


def _apply(project, group, outline, interior, color, width, lines=()):
    children = _children(project)
    index = {layer["id"]: layer for layer in project.state["layers"]}
    region = None
    if outline == "silhouette" or lines:
        # Measured before any stroke changes, so a refusal leaves the parts as they were.
        region = silhouette(project, group, children)
    if outline == "silhouette":
        require(region is not None and not region.is_empty, f"{group['name']!r} has no filled area to outline; draw "
                "its parts with fills (line work keeps its own strokes)", field="target")
    strokes = {}
    for layer in strokable(project, group, children):
        strokes[layer["id"]] = {key: deepcopy(layer[key]) for key in STROKE_KEYS if key in layer}
        _paint(layer, mode(outline, interior, override(layer, index, group)), color, width)
    layer = None
    if outline == "silhouette":
        layer = _write(project, group, region, color, width, children)
    else:
        _drop(project, group, children, lines=False)
    _drop(project, group, children, outline=False)
    drawn = []
    if lines and region is not None and not region.is_empty:
        drawn = draw_lines(project, group, region, color, lines, width / 2 if outline == "silhouette" else width)
    group["object"]["outlined"] = {"outline": outline, "interior": interior, "color": color, "width": width,
                                   "strokes": strokes, "hash": geometry_hash(project, group),
                                   **({"lines": deepcopy(list(lines))} if lines else {})}
    return layer, strokes, drawn


def remove(project, group):
    """Put the stored part strokes back and delete the outline layer."""
    record = group["object"]
    _restore_strokes(project, record)
    record.pop("outlined", None)
    _drop(project, group)


def apply(project, group, op):
    """``{type: object, action: outline}``: store the policy fields on the record and apply the policy."""
    from .design import resolve_color
    from .render import color as parse_color
    from .selectors import record as report

    record = group["object"]
    for key in FIELDS:
        if key not in op:
            continue
        if key == "outline" and op[key] == "inherit":
            record.pop("outline", None)
        elif key == "outline_lines":
            check_lines(op[key])
            if op[key]:
                record[key] = deepcopy(op[key])
            else:
                record.pop(key, None)
        else:
            record[key] = op[key]
    if "outline_color" in op:
        parse_color(resolve_color(op["outline_color"], project.state))
    if record.get("outlined"):
        remove(project, group)
    outline, interior = policy(project, group)
    summary = {"object": group["name"], "outline": outline}
    if outline != "none":
        color = record.get("outline_color", DEFAULT_COLOR)
        width = float(record.get("outline_width") or default_width(group, outline))
        layer, strokes, drawn = _apply(project, group, outline, interior, color, width, record.get("outline_lines", ()))
        summary.update(interior=interior, color=color, width=width, parts=len(strokes),
                       **({"layer": layer["name"]} if layer is not None else {}),
                       **({"lines": len(drawn)} if record.get("outline_lines") else {}))
    report(project, "outlines", summary)


def refresh(project):
    """Re-apply the outline of every object whose geometry changed since its outline was drawn."""
    children = None
    for group in [layer for layer in project.state["layers"] if (layer.get("object") or {}).get("outlined")]:
        children = children or _children(project)
        stored = group["object"]["outlined"]
        if stored.get("hash") == geometry_hash(project, group, children):
            continue
        _restore_strokes(project, group["object"])
        try:
            _apply(project, group, stored["outline"], stored["interior"], stored["color"], stored["width"],
                   stored.get("lines", ()))
        except VixlError:
            # Every part was removed or hidden: nothing is left to outline, so the outline goes with them.
            group["object"].pop("outlined", None)
            _drop(project, group)
        children = None


def remap(record, mapping):
    """Point a copied object's stored strokes at the copies of its layers (``duplicate``)."""
    stored = (record or {}).get("outlined")
    if stored and stored.get("strokes"):
        stored["strokes"] = {mapping.get(ident, ident): value for ident, value in stored["strokes"].items()}


# ---------------------------------------------------------------------------------------------------------------
# Object check findings


def findings(context, subject):
    """``object.outline-stale``, ``object.outline-seam`` and ``object.outline-weight`` for an outlined object."""
    from .object_check import Finding

    stored = subject.record.get("outlined")
    if not stored:
        return
    project, group = context.project, context.state_index[subject.group["id"]]
    target = f"{{type: object, action: outline, target: {subject.path}}}"
    children = _children(project)
    missing = stored["outline"] == "silhouette" and outline_layer(project, group, children) is None
    current = geometry_hash(project, group, children)
    if missing or current != stored.get("hash"):
        yield Finding("outline-stale", f"{subject.path}: its outline was drawn for other geometry"
                      + (" and its outline layer is gone" if missing else " (parts moved, changed or were added "
                         "outside an apply)"), [subject.group], "fix",
                      {"actual": "missing" if missing else current, "expected": stored.get("hash"), "unit": "hash"},
                      f"{target} draws it again; action outline-remove takes it away", extra={"outline": stored["outline"]})
    index = context.state_index
    layers = [(layer, stroke_width(layer, project.state)) for layer in strokable(project, group, children)]
    if stored["outline"] == "silhouette":
        width = stored["width"]
        seams = []
        for layer, drawn in layers:
            how = mode("silhouette", stored["interior"], override(layer, index, group))
            if (how == "hide" and drawn > 0) or (how == "thin" and drawn > width * THIN * (1 + WEIGHT_TOLERANCE)):
                seams.append((layer, drawn, how))
        if seams:
            names = ", ".join(f"{context.path(layer)} {drawn:g} px" for layer, drawn, _ in seams[:4])
            how = seams[0][2]
            expected = 0 if how == "hide" else round(width * THIN, 2)
            yield Finding("outline-seam", f"{subject.path}: {len(seams)} part stroke{'s' if len(seams) > 1 else ''} "
                          f"show{'' if len(seams) > 1 else 's'} inside the silhouette ({names}); its outline policy "
                          + ("hides part strokes" if how == "hide" else f"draws interior lines at {expected:g} px"),
                          [context.index.get(layer["id"], layer) for layer, _, _ in seams], "review",
                          {"actual": max(drawn for _, drawn, _ in seams), "expected": expected, "unit": "px"},
                          f"{target} re-applies the policy; a part meant to keep its own stroke takes outline: none "
                          "({type: object, action: part, target: LAYER, part: NAME, outline: none})",
                          extra={"outline": "silhouette", "interior": stored["interior"]})
    elif stored["outline"] == "parts" and len(layers) > 1:
        thinnest = min(layers, key=lambda item: item[1])
        thickest = max(layers, key=lambda item: item[1])
        ratio = thickest[1] / thinnest[1] if thinnest[1] > 0 else math.inf
        if ratio > 1 + WEIGHT_TOLERANCE:
            yield Finding("outline-weight", f"{subject.path}: part outlines range from {thinnest[1]:g} px "
                          f"({context.path(thinnest[0])}) to {thickest[1]:g} px ({context.path(thickest[0])}); under "
                          f"outline parts they match within {WEIGHT_TOLERANCE:.0%}",
                          [context.index.get(item[0]["id"], item[0]) for item in (thinnest, thickest)], "review",
                          {"actual": round(ratio, 3) if math.isfinite(ratio) else None,
                           "expected": 1 + WEIGHT_TOLERANCE, "unit": "ratio"},
                          f"{target} sets every part to {stored['width']:g} px", extra={"outline": "parts"})
