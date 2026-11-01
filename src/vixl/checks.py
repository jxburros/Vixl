"""Design self-checks for agents that cannot look at every pixel.

``check_design`` reports only problems, including visible descendants of groups.
Layers marked ``role: background`` and non-text layers whose drawn geometry covers the
canvas are background and skipped; ``checked`` reports how many layers were checked of the total.
"""

import math
import re

import numpy as np

from .constants import BUNDLED_FONTS, PROOFING_FONT
from .errors import VixlError, require
from .geometry import compact_number
from .model import finite
from .plugins import optional_checks as plugin_checks
from .timeline import animated as timeline_animated

CHECKS = ("bounds", "overlap", "contrast", "safe_area", "legibility", "blanks", "placeholders", "fonts", "brand", "content",
          "form", "links", "diagram", "flow", "codes", "composition", "object")
FALLBACK_FONT = PROOFING_FONT
OPTIONAL_CHECKS = ("print", "color_vision", "guides", "alignment", "drawing", "style", "motion", "character", "captions",
                   "connected", "cost", "accessibility", "budget", "approval") + plugin_checks()
# The accessibility check bundles these with its own findings (alt text, language, text size, colour-only
# charts, reading order).
ACCESSIBILITY_BUNDLE = ("contrast", "color_vision")
# What to do about a finding. Errors and the warnings below need a design change ("fix"); other warnings
# are worth a look ("review"); notes and deliberate choices the document marked are "informational".
ACTIONS = ("fix", "review", "informational")
FIX_WARNINGS = ("legibility", "fonts", "content", "guides", "alignment", "blanks", "placeholders", "brand")
PERCENT = re.compile(r"^(-?\d+(?:\.\d+)?)%$")


def _length(value, base, name):
    if isinstance(value, str):
        match = PERCENT.match(value)
        require(match, f"{name} must be pixels or a percentage like '5%'", field=name)
        return float(match[1]) * base / 100
    return finite(value, name, 0, 1e6)


def _insets(safe_area, width, height):
    if isinstance(safe_area, dict):
        allowed = {"left", "top", "right", "bottom"}
        require(not set(safe_area) - allowed, "safe_area keys are left, top, right, bottom", field="safe_area")
        return tuple(
            _length(safe_area.get(k, 0), width if k in ("left", "right") else height, f"safe_area.{k}")
            for k in ("left", "top", "right", "bottom")
        )
    left = _length(safe_area, width, "safe_area")
    top = _length(safe_area, height, "safe_area")
    return left, top, left, top


def _box(value, width, height, name):
    require(isinstance(value, (list, tuple)) and len(value) == 4, f"{name} must be [x, y, width, height]")
    x, y, w, h = (_length(v, width if i % 2 == 0 else height, name) for i, v in enumerate(value))
    return x, y, w, h


def classify(item):
    """``fix``, ``review`` or ``informational`` for one finding. A waived finding is informational."""
    if item.get("waived"):
        return "informational"
    if item.get("action") in ACTIONS:
        return item["action"]
    if item.get("intentional") or item["severity"] == "info" or item["check"] == "coverage":
        return "informational"
    if item["severity"] == "error" or item["check"] in FIX_WARNINGS:
        return "fix"
    return "review"


def rule_id(item):
    """The stable rule ID of a finding: ``check.code`` (``bounds.text-overflow``), or the check name."""
    return f"{item['check']}.{item['code']}" if item.get("code") else item["check"]


def tally(issues):
    """Counts by severity and the indexes of the findings grouped by action. Every finding gets an
    ``action`` and a stable ``rule``; ``passed`` requires no fix findings (review and informational findings
    do not fail). ``outcome`` separates validation (the fix findings) from review (outcomes.from_findings)."""
    from .outcomes import from_findings

    for item in issues:
        item["action"] = classify(item)
        item.setdefault("rule", rule_id(item))
    from .check_results import summarize

    errors = sum(1 for x in issues if x["severity"] == "error")
    return {
        "passed": errors == 0 and not any(x["action"] == "fix" for x in issues),
        "errors": errors,
        "warnings": sum(1 for x in issues if x["severity"] == "warning"),
        "info": sum(1 for x in issues if x["severity"] == "info"),
        "by_action": {action: [i for i, x in enumerate(issues) if x["action"] == action] for action in ACTIONS},
        "outcome": from_findings(issues),
        **summarize(issues),
    }


def where(region):
    x, y, w, h = region
    return f"x {x}–{x + w - 1}, y {y}–{y + h - 1}"


def _intersects(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _tolerant(box, amount):
    """``box`` grown by ``amount`` on every side, then out to whole pixels, the grid layer bounds are measured on:
    with the 0.5 px live-area tolerance, a layer on an old half-pixel guide (93.5, measured from 93) still fits."""
    x, y, w, h = box
    left, top = math.floor(x - amount + 1e-6), math.floor(y - amount + 1e-6)
    return left, top, math.ceil(x + w + amount - 1e-6) - left, math.ceil(y + h + amount - 1e-6) - top


def _contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[0] + outer[2] >= inner[0] + inner[2]
        and outer[1] + outer[3] >= inner[1] + inner[3]
    )


def glyph_area(mask, origin, halo=0.1):
    """Canvas boxes ``(left, top, right, bottom)`` of the glyph area of a text alpha ``mask`` placed at
    ``origin``: one box per line of ink (a run of inked rows, ascenders to descenders, first to last inked
    column), widened by ``halo`` of the line height. A mark in a line's descender band or between its words
    reads as touching the text even where it misses every glyph pixel."""
    rows = np.flatnonzero(mask.any(axis=1))
    if not rows.size:
        return []
    boxes = []
    for run in np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1):
        top, bottom = int(run[0]), int(run[-1]) + 1
        columns = np.flatnonzero(mask[top:bottom].any(axis=0))
        pad = max(1, round((bottom - top) * halo))
        boxes.append((origin[0] + int(columns[0]) - pad, origin[1] + top - pad,
                      origin[0] + int(columns[-1]) + 1 + pad, origin[1] + bottom + pad))
    return boxes


def glyph_reports(project, layers):
    """``(layer, {"missing", "fallback"})`` for resolved text layers whose characters need a
    fallback font or that no available font covers. Text is read with the project's variables."""
    from .text import layer_coverage

    for item in layers:
        report = layer_coverage(project, item)
        if report["missing"] or report["fallback"]:
            yield item, report


def boxed_text_need(project, layer):
    """For text set in a text-layout box, the (width, height) its lines need when wrapped at the
    box width, else None. Fitted, warped and path text are skipped: fit shrinks to the box, and
    warps and paths are laid out differently."""
    from .text import font_data, ink_right, measure, tab_stops, UnsupportedText
    from .render import document_variables
    from .variables import layer_text

    settings = layer.get("text_layout") or {}
    if layer["type"] != "text" or "width" not in settings or settings.get("fit") or settings.get("path"):
        return None
    from .lettering import view
    from .richtext import active

    layer = view(project, layer)

    if active(layer):
        from .richtext import layout as rich_layout

        result = rich_layout(project, layer)
        return math.ceil(result.box[2]), math.ceil(result.box[3])
    if settings.get("warp", "none") != "none":
        return None
    text = layer_text(layer, document_variables(project))
    args = (font_data(project, layer), text, layer["size"], layer.get("spacing", 4), layer.get("align", "left"),
            layer["width"], settings.get("wrap", "greedy"), tab_stops(layer, project))
    try:
        _, box = measure(*args)
    except UnsupportedText:
        return None
    stroke = 2 * layer.get("stroke_width", 0)
    # Lines wrap by advance, so only ink can leave the box: a glyph starting left of its origin (the tail of J) moves
    # the lines right by its overhang, which cuts nothing off unless the ink of a line then reaches past the edge.
    right = ink_right(*args) if box[0] < 0 else box[2]
    return math.ceil(right - box[0] + stroke), math.ceil(box[3] - box[1] + stroke)


def boxed_text_overflow(project, layer):
    """For text set in a text-layout box, the (width, height) its wrapped lines need when that is
    more than the box (they are cut off), else None."""
    need = boxed_text_need(project, layer)
    # A pixel of slack keeps antialiased glyph edges from counting as clipping.
    return need if need and (need[0] > layer["width"] + 1 or need[1] > layer["height"] + 1) else None


def missing_glyphs(project):
    """Visible text layers with characters that no available font covers (they draw as tofu)."""
    from .render import resolved_layers

    layers = resolved_layers(project)
    index = {item["id"]: item for item in layers}

    def shown(item):
        while item:
            if not item["visible"] or item["opacity"] <= 0:
                return False
            item = index.get(item.get("parent"))
        return True

    text = [item for item in layers if item["type"] == "text" and shown(item)]
    return [{"layer": item["name"], "missing": report["missing"]}
            for item, report in glyph_reports(project, text) if report["missing"]]


def group_matrix(item, resolved, local_bounds):
    """The 3×3 matrix taking ``item``'s local (parent group) coordinates to canvas coordinates,
    through each ancestor's centred scale, flips and rotation, as the renderer draws them."""
    matrix = np.eye(3)
    parent = resolved.get(item.get("parent"))
    while parent is not None:
        from .affine import layer_matrix, matrix as affine_matrix
        transform = layer_matrix(parent, local_bounds[parent["id"]]) @ affine_matrix(
            parent["width"] / parent["content_width"], 0, 0, parent["height"] / parent["content_height"])
        matrix = transform @ matrix
        parent = resolved.get(parent.get("parent"))
    return matrix


def gradient_edges(project, layer, box, width, height, opacity=1.0, threshold=0.12):
    """The sides of a fade-to-transparent gradient layer's box that are inside the canvas but still
    visibly painted: a hard rectangular edge the fade was meant to hide."""
    from .design import gradient_stops, resolve_color
    from .design_render import gradient_image
    from .render import color

    # Rotated, masked or effected (blurred, feathered) layers have other edges; they are left out.
    if (layer["type"] != "gradient" or layer.get("rotation", 0) or layer.get("skew_x") or layer.get("skew_y")
            or layer.get("mask") or any(effect.get("enabled", True) for effect in layer.get("effects", []))):
        return []
    stops = gradient_stops(layer, project.state)
    if all(color(resolve_color(stop["color"], project.state))[3] for stop in stops):
        return []
    x, y, w, h = box
    inside = {"top": 0.5 < y < height, "bottom": 0 < y + h < height - 0.5,
              "left": 0.5 < x < width, "right": 0 < x + w < width - 0.5}
    if not any(inside.values()):
        return []
    size = (max(2, min(256, math.ceil(layer["width"]))), max(2, min(256, math.ceil(layer["height"]))))
    alpha = np.asarray(gradient_image(project, layer, size).getchannel("A"), dtype=float) / 255 * opacity
    edges = {"top": alpha[0], "bottom": alpha[-1], "left": alpha[:, 0], "right": alpha[:, -1]}
    return [side for side in ("top", "bottom", "left", "right") if inside[side] and edges[side].max() > threshold]


def geometry_bounds(layer, project=None):
    """(left, top, right, bottom) of what the layer actually draws, in its own box's pixel space
    (the origin is the box's top-left corner). Shapes report their path geometry including stroke,
    text set with hanging punctuation (given the ``project``) its box widened by the hung marks,
    every other layer fills its box. Checks use
    this instead of the layer box so a path drawn smaller than its (often full-canvas) box is judged
    by what it paints."""
    from .render import rest_size

    width, height = rest_size(layer)
    box = (0.0, 0.0, float(width), float(height))
    if layer["type"] == "text" and project is not None and layer.get("hanging_punctuation"):
        from .richtext import hung_reach
        from .text import UnsupportedText

        try:
            reach = hung_reach(project, layer)
        except UnsupportedText:
            reach = None
        return (-reach[0], 0.0, float(width) + reach[1], float(height)) if reach else box
    if layer["type"] != "shape" or layer.get("repeat"):
        return box
    try:
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.svgLib.path import parse_path

        from .geometry import PATH_SHAPES
        from .shape_catalog import active as catalog_active
        from .vector_paths import pixel_path
        from .vector_strokes import active as stroke_active, primitives

        free = bool(catalog_active(layer) or stroke_active(layer) or layer.get("distort") or layer.get("_distort_groups"))
        pen = BoundsPen(None)
        if free:
            for path, paint in primitives(layer):
                if path and paint != "transparent":
                    parse_path(path, pen)
        elif layer.get("shape") in PATH_SHAPES:
            parse_path(pixel_path(layer), pen)
        else:
            return box
        if pen.bounds is None:
            return box
        x0, y0, x1, y1 = pen.bounds
        if not free and layer.get("stroke", "transparent") != "transparent" and layer.get("stroke_width", 1) > 0:
            pad = layer.get("stroke_width", 1) / 2
            x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        return (float(x0), float(y0), float(x1), float(y1))
    except Exception:  # noqa: BLE001 - geometry that cannot be read falls back to the box.
        return box


def clipped_geometry(project, layer, bounds, tolerance=2.0):
    """The box edges (``top``, ``right``, ``bottom``, ``left``) past which a ``path`` or ``arc`` shape's own
    geometry runs while its rendered image does not: the renderer cut it off (or squeezed it) at its box.
    Shapes draw past their box by design, so this finds a drawing that comes out flattened, else []."""
    if layer["type"] != "shape" or layer.get("repeat") or layer["visible"] is False:
        return []
    from .geometry import PATH_SHAPES

    if layer.get("shape") not in PATH_SHAPES or layer.get("distort") or layer.get("_distort_groups"):
        return []
    from .vector_strokes import geometry_reach

    reach = geometry_reach(layer)
    if reach is None:
        return []
    x0, y0, x1, y1 = reach
    w, h = layer["width"], layer["height"]
    past = {"top": -y0, "right": x1 - w, "bottom": y1 - h, "left": -x0}
    if max(past.values()) <= tolerance:
        return []
    from .render import layer_ink

    image = layer_ink(project, layer, bounds)
    room_x, room_y = (image.width - math.ceil(w)) / 2, (image.height - math.ceil(h)) / 2
    return [side for side in ("top", "right", "bottom", "left") if past[side] > tolerance
            and (room_y if side in ("top", "bottom") else room_x) < past[side] - tolerance]


def canvas_projection(resolved, local_bounds, project=None):
    """Canvas-space integer bounds, text scale factors and group matrices for every layer.
    Shared by the design checks, guide checks and fillable form export, so they agree. With the
    ``project``, the geometry bounds of text count its hung punctuation."""
    bounds, scales, matrices, exact, drawn = {}, {}, {}, {}, {}
    for item in resolved.values():
        matrix = group_matrix(item, resolved, local_bounds)
        x, y, w, h = local_bounds[item["id"]]
        corners = matrix @ np.array([[x, x + w, x, x + w], [y, y, y + h, y + h], [1, 1, 1, 1]])
        left, top = np.floor(corners[:2].min(axis=1) + 1e-8).astype(int)
        right, bottom = np.ceil(corners[:2].max(axis=1) - 1e-8).astype(int)
        bounds[item["id"]] = tuple(map(int, (left, top, right - left, bottom - top)))
        from .affine import layer_matrix, corners as affine_corners, envelope
        from .render import rest_size
        rw, rh = rest_size(item)
        placed = matrix @ layer_matrix(item, local_bounds[item["id"]])
        exact[item["id"]] = envelope(affine_corners((0, 0, rw, rh), placed))
        gl, gt, gr, gb = geometry_bounds(item, project)
        drawn[item["id"]] = envelope(affine_corners((gl, gt, gr - gl, gb - gt), placed))
        scales[item["id"]] = float(np.linalg.norm(matrix[:2, 1]))
        matrices[item["id"]] = matrix
    return {"bounds": bounds, "scales": scales, "matrices": matrices, "exact_bounds": exact,
            "geometry_bounds": drawn}


def member_geometry(resolved, geometry):
    """``geometry`` with every group's box replaced by the union of what its visible members draw, clipped to
    the group's own box. Path shapes in absolute canvas coordinates keep a box from (0, 0), and so does the group
    fitted around them; judged by that box, the group would reach the canvas corner however small its ink."""
    children = {}
    for item in resolved.values():
        if item.get("parent") in resolved and item["visible"] and item["opacity"] > 0 and item["type"] != "adjustment":
            children.setdefault(item["parent"], []).append(item["id"])

    def measure(ident, seen=()):
        layer = resolved[ident]
        if layer["type"] != "group" or layer.get("repeat") or ident in seen or not children.get(ident):
            return geometry[ident]
        boxes = [measure(child, (*seen, ident)) for child in children[ident]]
        gx, gy, gw, gh = geometry[ident]
        left, top = max(gx, min(b[0] for b in boxes)), max(gy, min(b[1] for b in boxes))
        right, bottom = min(gx + gw, max(b[0] + b[2] for b in boxes)), min(gy + gh, max(b[1] + b[3] for b in boxes))
        return geometry[ident] if right <= left or bottom <= top else (left, top, right - left, bottom - top)

    return {ident: measure(ident) for ident in geometry}


def overlap_candidates(boxes, texts, width, height):
    """Index pairs (i < j), in order, whose boxes meet on the canvas and of which at least one is
    text: a sweep along x, so a document of thousands of shapes is not compared pair by pair."""
    starts = []
    for index, (x, y, w, h) in enumerate(boxes):
        left, top, right, bottom = max(0, x), max(0, y), min(width, x + w), min(height, y + h)
        if left < right and top < bottom:
            starts.append((left, right, top, bottom, index))
    starts.sort()
    pairs, open_all, open_text = [], [], []
    for left, right, top, bottom, index in starts:
        # Every box is compared with the open text boxes; text is also compared with the rest.
        open_text = [item for item in open_text if item[0] > left]
        if texts[index]:
            open_all = [item for item in open_all if item[0] > left]
        for other_right, other_top, other_bottom, other in (open_all if texts[index] else open_text):
            if other_top < bottom and top < other_bottom:
                pairs.append((min(index, other), max(index, other)))
        entry = (right, top, bottom, index)
        open_all.append(entry)
        if texts[index]:
            open_text.append(entry)
    return sorted(set(pairs))


# Text whose glyphs lie at least this much on a shape or image painted beneath it sits on that panel, even when
# the text box overhangs it; a caption that crosses only part of a button stays an overlap.
INK_INSIDE = 0.98


def paint_order(resolved):
    """Each layer's position in the order the renderer paints them: siblings in document order, and a
    group's children at the group's own place in its parent's stack."""
    children = {}
    for item in resolved.values():
        children.setdefault(item.get("parent"), []).append(item["id"])
    order = {}
    stack = list(reversed(children.get(None, [])))
    while stack:
        ident = stack.pop()
        order[ident] = len(order)
        stack.extend(reversed(children.get(ident, [])))
    return order


def hidden_text(project, resolved, layers, bounds, ink, alpha, is_text, issue, width, height):
    """Report text that a layer painted above it covers: contrast measures text against what lies beneath it,
    so a panel, band or image stacked on top of the words (often after a reorder) would hide them unseen."""
    from .render import layer_canvas_alpha

    order = paint_order(resolved)
    covers = [item for item in layers if item["type"] != "group" and not is_text(item)
              and item.get("blend", "normal") == "normal"]
    opaque = {}

    def solid(item, box):
        key = (item["id"], box)
        if key not in opaque:
            opaque[key] = np.asarray(layer_canvas_alpha(project, resolved[item["id"]], box, bounds, resolved)) >= 224
        return opaque[key]

    for text in layers:
        if not is_text(text) or not resolved[text["id"]].get("text", "").strip():
            continue
        x, y, w, h = ink(text)
        box = (max(0, x), max(0, y), min(width, x + w), min(height, y + h))
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        glyphs = alpha(text)
        total = int(glyphs.sum())
        if total == 0:
            continue
        covered = np.zeros_like(glyphs)
        culprits = []
        for item in covers:
            if order.get(item["id"], -1) <= order[text["id"]]:
                continue
            ix, iy, iw, ih = ink(item)
            if ix >= box[2] or iy >= box[3] or ix + iw <= box[0] or iy + ih <= box[1]:
                continue
            mask = np.logical_and(solid(item, box), glyphs)
            if mask.any():
                covered |= mask
                culprits.append(item)
        share = float(covered.sum()) / total
        if share >= 0.25:
            issue("overlap", "error",
                  f"{text['name']!r} is {share:.0%} hidden under {', '.join(repr(x['name']) for x in culprits[:3])}, "
                  "painted above it. Move the text above them (reorder) or move them off it",
                  [text, *culprits[:3]], code="hidden-text", hidden=round(share, 3))


class Checkpoints(list):
    """The check names of one ``check_design`` run. Each check family starts with an ``in`` test on this list,
    which is also where a cancelled call stops (``calls.check_cancelled``)."""

    def __contains__(self, name):
        from .calls import check_cancelled

        check_cancelled()
        return super().__contains__(name)


def check_design(
    project,
    *,
    checks=None,
    targets=None,
    safe_area=None,
    avoid=None,
    thumbnail_width="auto",
    min_thumbnail_text=10,
    min_contrast=None,
    artboard=None,
    comp=None,
    variables=None,
    ink_limit=300,
    min_ppi=200,
    page=None,
    deck=None,
    sample=None,
    style=None,
    connect_tolerance=2,
    repairs=True,
    waivers=True,
):
    """Return ``{"passed", "errors", "warnings", "info", "issues", "by_action", "checked", "outcome"}`` for the rendered
    design. Each issue has a ``severity`` (error, warning, info) and an ``action`` (fix, review or
    informational); ``by_action`` lists the issue indexes under each action. Layers marked as intentional
    crops (``layer-intent`` ``allow_crop``, or non-text decoration) report edge crops as info.
    In a multi-page document ``page`` picks the page (default: the active page); the ``deck``
    check family reviews every page and the deck as a whole (``deck`` holds its settings:
    ``min_font``, ``max_words``, ``pages``, ``include_hidden``). ``sample`` (``"worst"`` or a CSV
    path) fills the form's fields to find values that overflow their boxes. The ``style`` check
    evaluates the document's style tag (or ``style``, a name or list of names) rule by rule. The ``connected``
    check reports parts of a group that float free of its main body (gaps above ``connect_tolerance`` px); the
    ``object`` check measures declared objects against their kind (``object_check``), and ``connected`` then leaves
    those groups to it.
    The document's waivers (see ``waivers.py``) turn the findings they cover into informational ones listed
    as ``waived``; ``waivers=False`` reports every finding as if there were none."""
    from .design_render import artboard_project
    from .render import layer_canvas_alpha, layer_canvas_surface, resolve_layout, resolved_layers, resolving

    # A document with animation is also checked over time (loop seam, poster frame) unless checks are named.
    document = project  # the document as saved, before a page view or the checks' own candidate copy
    animated = not checks and timeline_animated(project.state.get("timeline"))
    checks = list(checks or CHECKS) + (["motion"] if animated else [])
    from .deck import DECK_CHECKS

    if "deck" in checks or set(checks) & set(DECK_CHECKS):
        from .deck import check_deck

        rest = [c for c in checks if c != "deck"]
        if "deck" in checks:
            # "deck" means every deck check, with the named design checks (default: the deck set).
            rest = [c for c in rest if c not in DECK_CHECKS]
            rest = rest + list(DECK_CHECKS) if rest else None
        options = {"thumbnail_width": None if thumbnail_width == "auto" else thumbnail_width, "min_thumbnail_text": min_thumbnail_text, **(deck or {})}
        if "deck" in checks and "type_scale" not in checks and rest and options.get("profile") in ("screen", "phone"):
            rest = [c for c in rest if c != "type_scale"]
        report = check_deck(project, checks=rest, safe_area=safe_area, min_contrast=min_contrast, **options)
        if waivers:
            from .waivers import apply as apply_waivers

            apply_waivers(project, report)
        return report
    from .render import view_page

    page_ref = None
    if project.state.get("pages") and not getattr(project, "_page_view", False):
        from .pages import active_page, find_page, page_number

        record = find_page(project.state, page) if page is not None else (
            active_page(project.state) or project.state["pages"][0])
        page_ref = page_number(project.state, record)
    project = view_page(project, page)
    from .brand import contrast_floor, for_project, required_contrast

    brand = for_project(project)
    floor = contrast_floor(brand, min_contrast)
    unknown = sorted(set(checks) - set(CHECKS + OPTIONAL_CHECKS))
    require(not unknown, f"Unknown check(s) {unknown}; available: {', '.join(CHECKS + OPTIONAL_CHECKS)}", field="checks")
    if "accessibility" in checks:
        checks = checks + [name for name in ACCESSIBILITY_BUNDLE if name not in checks]
    checks = Checkpoints(checks)
    candidate = artboard_project(project.clone(), artboard, comp, variables)
    undefined = []
    if "placeholders" in checks:
        from .copy_checks import stand_in, undefined_variables

        undefined = undefined_variables(candidate)
        stand_in(candidate, undefined)
    c = candidate.state["canvas"]
    width, height = c["width"], c["height"]
    resolved = {item["id"]: item for item in resolved_layers(candidate)}
    local_bounds = resolve_layout(candidate, layers=list(resolved.values()))

    def is_text(item):
        return resolved[item["id"]]["type"] == "text"

    def ancestors(item):
        while item.get("parent"):
            item = resolved[item["parent"]]
            yield item

    def visible(item):
        return all(x["visible"] and x["opacity"] > 0 for x in (item, *ancestors(item)))

    # Layout bounds are local to the immediate group; project them onto the canvas.
    projection = canvas_projection(resolved, local_bounds, candidate)
    bounds = projection["bounds"]
    text_scales = projection["scales"]
    layers = [
        item
        for item in resolved.values()
        if visible(item) and item["type"] != "adjustment"
    ]
    if targets:
        wanted = {candidate.layer(t)["id"] for t in targets}
        layers = [item for item in layers if any(x["id"] in wanted for x in (item, *ancestors(item)))]

    from .links import broken_links, check_links

    # A link whose source cannot be drawn is reported by the links check and left out of the rest.
    unreadable = broken_links(candidate, {item["id"] for item in layers if item["type"] == "link"})
    layers = [item for item in layers if item["id"] not in unreadable]

    def role(item):
        explicit = next((x["role"] for x in (item, *ancestors(item)) if x.get("role")), None)
        if explicit:
            return explicit
        from .design import resolve_color
        from .render import color

        # A fade to transparency has no hard visual edge: it is normally a decorative
        # glow/background. Explicit content intent always overrides this inference.
        if item["type"] == "gradient":
            stops = item.get("stops") or [{"color": item.get("start", "black")}, {"color": item.get("end", "white")}]
            edge = [stops[-1]] if item.get("direction") == "radial" else [stops[0], stops[-1]]
            if any(color(resolve_color(stop["color"], candidate.state))[3] == 0 for stop in edge):
                return "decoration"
        return "content"

    def intentional_crop(item):
        """A deliberate edge crop: the layer (or a group above it) is marked allow_crop, or it is non-text decoration."""
        chain = (item, *ancestors(item))
        return any(x.get("allow_crop") for x in chain) or (
            not is_text(item) and role(item) == "decoration"
        )

    # Particles groups (every child a particle), as the particles operation makes them.
    kinds = {}
    for x in resolved.values():
        if x.get("parent"):
            kinds.setdefault(x["parent"], set()).add("particle" in x)
    emitters_ids = {ident for ident, kind in kinds.items() if kind == {True}}

    def emitter(item):
        return item["id"] in emitters_ids

    geometry = projection["geometry_bounds"]

    def outward(box):
        x, y, w, h = box
        left, top = math.floor(x + 1e-6), math.floor(y + 1e-6)
        return left, top, math.ceil(x + w - 1e-6) - left, math.ceil(y + h - 1e-6) - top

    def background(item):
        """Marked ``role: background``, or a non-text layer whose drawn geometry (not its box) covers the canvas."""
        if is_text(item):
            return False
        if role(item) == "background":
            return True
        if not _contains(outward(geometry[item["id"]]), (0, 0, width, height)):
            return False
        if item["type"] == "link" or (item["type"] == "shape" and item.get("shape") not in ("rectangle", "rounded-rectangle")):
            # A path or ellipse can span the canvas and still paint a sliver (a diagonal line).
            tile = layer_canvas_surface(candidate, resolved[item["id"]], local_bounds, resolved)
            return float((np.asarray(tile.getchannel("A")) > 32).mean()) >= 0.5
        return True

    content = [item for item in layers if not background(item)]
    issues = []

    def issue(check, severity, message, layers=(), **extra):
        # Layer IDs and the first layer's canvas box locate the finding (diagnostics.annotate adds the rest).
        located = {"layer_ids": [x["id"] for x in layers]} if layers else {}
        if layers and layers[0]["id"] in bounds:
            located["box"] = list(bounds[layers[0]["id"]])
        issues.append(
            {"check": check, "severity": severity, "layers": [x["name"] for x in layers], "message": message,
             **located, **extra}
        )

    for item in content:
        if any(parent.get("repeat") for parent in ancestors(item)) and set(checks) - {"contrast"}:
            issue("coverage", "warning",
                  f"{item['name']!r} is inside a repeated group; geometry checks cover its base instance. "
                  "Visually inspect the repeated instances.", [item])

    if "bounds" in checks:
        emitters = {}
        for item in content:
            x, y, w, h = geometry[item["id"]]
            if "particle" in item or emitter(item):
                # Particles are born and die past the canvas edge on purpose: one note per emitter, not one per particle.
                if x < -1e-8 or y < -1e-8 or x + w > width + 1e-8 or y + h > height + 1e-8:
                    group = item if emitter(item) else resolved.get(item.get("parent"))
                    if group is not None:
                        emitters.setdefault(group["id"], (group, []))[1].append(item)
                continue
            if x >= width or y >= height or x + w <= 0 or y + h <= 0:
                intentional = any(parent.get("pattern_scatter") for parent in ancestors(item))
                issue("bounds", "info" if intentional else "error",
                      f"{item['name']!r} is entirely outside the canvas" + (" (intentional crop or tile wrap)" if intentional else ""),
                      [item], bounds=[x, y, w, h], code="off-canvas", **({"intentional": True} if intentional else {}))
            elif x < -1e-8 or y < -1e-8 or x + w > width + 1e-8 or y + h > height + 1e-8:
                crossed = sum((x < -1e-8, y < -1e-8, x + w > width + 1e-8, y + h > height + 1e-8))
                if any(parent.get("pattern_scatter") for parent in ancestors(item)):
                    # A seamless tile's motifs cross its edge on purpose: the wrapped copy completes them.
                    issue("bounds", "info", f"{item['name']!r} wraps across the edge of a seamless pattern tile",
                          [item], bounds=[x, y, w, h], intentional=True, code="tile-wrap")
                elif intentional_crop(item) or (item["type"] in ("shape", "gradient") and crossed >= 2):
                    # Artwork that runs past two or more edges (a hill, a glow) is bleed by design.
                    issue("bounds", "info", f"{item['name']!r} bleeds off the canvas edge (" + (
                              "marked as an intentional crop)" if intentional_crop(item) else "artwork running past two edges)"),
                          [item], bounds=[x, y, w, h], intentional=True, code="bleed")
                else:
                    severity = "error" if is_text(item) else "warning"
                    issue("bounds", severity, f"{item['name']!r} is cut off by the canvas edge"
                          + ("" if is_text(item) else "; if the crop is deliberate, mark it with layer-intent allow_crop"),
                          [item], bounds=[x, y, w, h], code="cut-off")
        for group, items in emitters.values():
            particles = [item for item in items if "particle" in item]
            issue("bounds", "info", f"Particle emitter {group['name']!r} reaches past the canvas edge"
                  + (f" ({len(particles)} particles at this frame)" if particles else "")
                  + "; particles that start or end off the canvas are expected", [group], intentional=True,
                  code="particles-off-canvas")
        for item in layers:
            sides = clipped_geometry(candidate, resolved[item["id"]], local_bounds[item["id"]])
            if sides:
                layer = resolved[item["id"]]
                issue("bounds", "error",
                      f"{item['name']!r} is a path whose geometry runs past the {', '.join(sides)} edge"
                      f"{'s' if len(sides) > 1 else ''} of its {compact_number(layer['width'], 2)}×{compact_number(layer['height'], 2)} box, "
                      "but it is drawn cut off at the box, so the shape comes out flattened. Scale it into the box with "
                      "path-fit, or give it a box that holds the whole path", [item], code="geometry-clipped", sides=sides)
        for item in content:
            needed = boxed_text_overflow(candidate, resolved[item["id"]])
            if needed:
                layer = resolved[item["id"]]
                issue("bounds", "error",
                      f"{item['name']!r} does not fit its {layer['width']}×{layer['height']} text box at "
                      f"{layer['size']} px and is cut off (it needs {needed[0]}×{needed[1]}); enlarge the box "
                      "with text-layout or shrink the text with fit-text", [item], needs=list(needed),
                      code="text-overflow")
        for item in layers:
            sides = gradient_edges(candidate, resolved[item["id"]], geometry[item["id"]], width, height,
                                   math.prod(x["opacity"] for x in (item, *ancestors(item))))
            if sides:
                issue("bounds", "warning",
                      f"{item['name']!r} fades to transparent but its "
                      f"{' and '.join([', '.join(sides[:-1]), sides[-1]] if len(sides) > 1 else sides)} edge"
                      f"{'s are' if len(sides) > 1 else ' is'} not transparent, so its box shows as a visible "
                      "rectangle. End the fade at the box edge (a radial gradient ends at its inscribed ellipse), "
                      "enlarge the box, or run it past the canvas edge", [item], code="gradient-edge", sides=sides)

    alphas, inks = {}, {}

    def ink(item):
        """Integer canvas box of everything the layer paints: its drawn geometry widened by strokes,
        shadows, glows and blurs (which draw past the layer's box)."""
        if item["id"] not in inks:
            from .render import effect_margin, style_margin

            layer = resolved[item["id"]]
            x, y, w, h = geometry[item["id"]]
            sx, sy = style_margin(layer)
            ex, ey = effect_margin(layer)
            stroke = layer.get("stroke_width", 0) if layer["type"] == "text" else 0
            scale = text_scales[item["id"]]
            mx, my = (sx + ex + stroke) * scale, (sy + ey + stroke) * scale
            inks[item["id"]] = outward((x - mx, y - my, w + 2 * mx, h + 2 * my))
        return inks[item["id"]]

    def alpha(item):
        if item["id"] not in alphas:
            x, y, w, h = ink(item)
            box = (max(0, x), max(0, y), min(width, x + w), min(height, y + h))
            alphas[item["id"]] = np.asarray(layer_canvas_alpha(candidate, resolved[item["id"]], box, local_bounds,
                                                               resolved)) > 32
        return alphas[item["id"]]

    if "content" in checks:
        from .render import layer_image
        from .brushes import stroke_diagnostics
        if height / width >= 1.6:
            foreground = [item for item in content if item["type"] != "group" and role(item) == "content"]
            if foreground:
                boxes = [bounds[item["id"]] for item in foreground]
                extent_w = max(x + w for x, y, w, h in boxes) - min(x for x, y, w, h in boxes)
                extent_h = max(y + h for x, y, w, h in boxes) - min(y for x, y, w, h in boxes)
                if extent_w < width * 0.55 and extent_h < height * 0.4:
                    issue("content", "warning", "Content occupies a small block on this tall canvas; enlarge or "
                          "recompose it for the target format, or review intentional whitespace", foreground,
                          code="underfill", action="review", width_fraction=round(extent_w / width, 3),
                          height_fraction=round(extent_h / height, 3))
        for item in layers:
            if item["type"] == "group" or (item["type"] == "paint" and not item.get("strokes")):
                continue
            if item["type"] == "text" and not item.get("text", "").strip():
                continue
            if item["type"] == "paint":
                strokes = stroke_diagnostics(item, candidate)
                for stroke in strokes:
                    if not stroke["intersects_surface"]:
                        issue("content", "warning", f"{item['name']!r} stroke {stroke['index']} has no coverage on its paint surface; check coordinates, pressure, and brush settings", [item], stroke=stroke)
            image = layer_image(candidate, item, local_bounds[item["id"]])
            if image.getchannel("A").getbbox() is None:
                issue("content", "warning", f"{item['name']!r} has no visible pixels", [item],
                      **({"strokes": stroke_diagnostics(item)} if item["type"] == "paint" else {}))

    # Text layers are measured and drawn many times below: compute the document variables once.
    with resolving(candidate):
        # Characters no font can draw render as empty boxes (tofu), so they are reported by every
        # check run, whichever checks were selected; fallback-font warnings belong to "fonts".
        for item, report in glyph_reports(candidate, [item for item in layers if item["type"] == "text"]):
            if report["missing"]:
                from .advisories import cover_fix
                from .text import scripts_of

                issue("fonts", "error", f"{item['name']!r} has characters no font can draw ({''.join(report['missing'][:12])}); "
                      f"they render as empty boxes. {cover_fix(scripts_of(report['missing']))}", [item], **report)
            elif report.get("local") and "fonts" in checks:
                from .advisories import cover_fix
                from .text import scripts_of

                issue("fonts", "warning", f"{item['name']!r} draws {''.join(report['local'][:12])} with "
                      f"{', '.join(report['local_fonts'])} from this machine, which the document does not embed: "
                      f"elsewhere they render as empty boxes. {cover_fix(scripts_of(report['local']), local=True)}",
                      [item], **report)
            elif report["fallback"] and "fonts" in checks:
                issue("fonts", "warning", f"{item['name']!r} uses fallback glyphs", [item], **report)

        if "overlap" in checks:
            drawable = [item for item in content if item["type"] != "group"]
            stacked = paint_order(resolved)

            def ink_within(inner, outer):
                """The fraction of ``inner``'s drawn pixels that land on ``outer``'s drawn pixels."""
                mi, mo = alpha(inner), alpha(outer)
                total = int(mi.sum())
                if not total:
                    return 0.0
                ix, iy = max(0, ink(inner)[0]), max(0, ink(inner)[1])
                ox, oy = max(0, ink(outer)[0]), max(0, ink(outer)[1])
                left, top = max(ix, ox), max(iy, oy)
                right = min(ix + mi.shape[1], ox + mo.shape[1])
                bottom = min(iy + mi.shape[0], oy + mo.shape[0])
                if left >= right or top >= bottom:
                    return 0.0
                covered = np.logical_and(mi[top - iy:bottom - iy, left - ix:right - ix],
                                         mo[top - oy:bottom - oy, left - ox:right - ox])
                return int(covered.sum()) / total

            def decoration_over_text(decor, text):
                """Decoration may sit under or around text (a panel, a frame, a rule), but its painted pixels
                should not run through the text's glyph area: a review warning, not a fix. Only layers marked
                decoration count (a glow inferred from its fade sits behind text by design), and chart internals
                (gridlines under value labels) are skipped."""
                if not any(x.get("role") == "decoration" for x in (decor, *ancestors(decor))):
                    return
                if any(x.get("chart") for x in (*ancestors(decor), *ancestors(text))):
                    return
                if _contains(outward(geometry[decor["id"]]), outward(geometry[text["id"]])):
                    return  # A panel or frame around the text.
                dx, dy, _, _ = ink(decor)
                mask = alpha(decor)
                origin = (max(0, dx), max(0, dy))
                tx, ty, _, _ = ink(text)
                inside = np.zeros_like(mask)
                for left, top, right, bottom in glyph_area(alpha(text), (max(0, tx), max(0, ty))):
                    inside[max(0, top - origin[1]):max(0, bottom - origin[1]),
                           max(0, left - origin[0]):max(0, right - origin[0])] = True
                pixels = int(np.logical_and(mask, inside).sum())
                smaller = max(1, min(int(mask.sum()), int(alpha(text).sum())))
                if pixels > 4 and pixels / smaller > 0.005:
                    ys, xs = np.nonzero(np.logical_and(mask, inside))
                    region = [origin[0] + int(xs.min()), origin[1] + int(ys.min()),
                              int(xs.max() - xs.min()) + 1, int(ys.max() - ys.min()) + 1]
                    issue("overlap", "warning",
                          f"Decoration {decor['name']!r} runs through the glyphs of {text['name']!r} "
                          f"({pixels} px at {where(region)}); move it clear of the text, or mark the pair "
                          "with layer-intent allow_overlap if it is deliberate", [decor, text], region=region,
                          code="decoration-text", action="review", pixels=pixels)

            for i, j in overlap_candidates([ink(item) for item in drawable], [is_text(item) for item in drawable], width, height):
                first, second = drawable[i], drawable[j]
                if second["id"] in first.get("allow_overlap", []) or first["id"] in second.get("allow_overlap", []):
                    continue
                decor = [x for x in (first, second) if role(x) == "decoration" and not is_text(x)]
                if decor:
                    if len(decor) == 1 and any(is_text(x) for x in (first, second)):
                        decoration_over_text(decor[0], second if decor[0] is first else first)
                    continue
                a, b = ink(first), ink(second)
                if not _intersects(a, b):
                    continue
                texts = [x for x in (first, second) if is_text(x)]
                if not texts:
                    continue  # Overlapping images and shapes are ordinary composition.
                if len(texts) == 1:
                    other = second if texts[0] is first else first
                    if _contains(outward(geometry[other["id"]]), outward(geometry[texts[0]["id"]])):
                        continue  # A label inside its button or panel.
                    if stacked.get(other["id"], -1) < stacked.get(texts[0]["id"], -1) and \
                            ink_within(texts[0], other) >= INK_INSIDE:
                        continue  # Its box overhangs the panel beneath it, but the glyphs sit inside it.
                left, top = max(0, a[0], b[0]), max(0, a[1], b[1])
                right = min(width, a[0] + a[2], b[0] + b[2])
                bottom = min(height, a[1] + a[3], b[1] + b[3])
                if left >= right or top >= bottom:
                    continue
                ax, ay, bx, by = max(0, a[0]), max(0, a[1]), max(0, b[0]), max(0, b[1])
                ma = alpha(first)[top - ay:bottom - ay, left - ax:right - ax]
                mb = alpha(second)[top - by:bottom - by, left - bx:right - bx]
                pixels = int(np.logical_and(ma, mb).sum())
                smaller = max(1, min(int(alpha(first).sum()), int(alpha(second).sum())))
                if pixels > 4 and pixels / smaller > 0.005:
                    severity = "error" if len(texts) == 2 else "warning"
                    issue(
                        "overlap",
                        severity,
                        f"{first['name']!r} and {second['name']!r} overlap by {pixels} px "
                        f"({pixels / smaller:.1%} of the smaller layer)",
                        [first, second],
                        region=[left, top, right - left, bottom - top],
                        code="text-text" if len(texts) == 2 else "text-object",
                        pixels=pixels,
                    )

            hidden_text(candidate, resolved, layers, local_bounds, ink, alpha, is_text, issue, width, height)

    # Empty text (a lyric between lines, a cleared label) draws nothing to measure.
    texts = [item for item in content if is_text(item) and resolved[item["id"]].get("text", "").strip()]
    if "legibility" in checks:
        from .richtext import active, fitted
        from .text import plan

        for item in texts:
            layer = resolved[item["id"]]
            layout = fitted(candidate, layer) if active(layer) else plan(candidate, layer)
            if layout.word_breaks:
                issue("legibility", "warning", f"{item['name']!r} wraps inside a word; use fit-text or a wider box",
                      [item], code="word-break", lines=list(layout.word_breaks))
    contrasts = {}  # Text contrast (p10) by layer ID, measured once and shared with the use-size legibility test.
    if "contrast" in checks:
        from .measure import measure, top_level_contrast

        # Top-level text is measured from one shared render; grouped text renders its own.
        top = [item["id"] for item in texts if not item.get("parent")]
        try:
            measured = top_level_contrast(candidate, top) if top else {}
        except Exception:  # noqa: BLE001 - measure each layer separately and report its own failure.
            measured = {}
        from .plugins.charts.charts import chart_contrast

        measured.update(chart_contrast(candidate, resolved, local_bounds, bounds, [x for x in texts if x.get("parent")]))
        for item in texts:
            result = measured.get(item["id"])
            try:
                if result is None or isinstance(result, Exception):
                    # The single-pass measurement failed for this layer: measure it on its own.
                    result = measure(candidate, target=item["id"])["contrast"]
            except Exception as exc:  # noqa: BLE001 - never a silent pass: an unmeasurable layer is an error.
                if any(x.get("code") == "cut-off" and item["name"] in x.get("layers", []) for x in issues):
                    continue
                issue("contrast", "error", f"Could not measure the contrast of {item['name']!r}: {exc}", [item],
                      code="unmeasurable")
                continue
            threshold = required_contrast(floor, resolved[item["id"]].get("size", 0) * text_scales[item["id"]],
                                          _bold(candidate, resolved[item["id"]]))
            # Outlined text reads through its outline when the fill blends into the backdrop.
            outline = result.get("outline")
            contrasts[item["id"]] = max(result["p10"], outline["p10"] if outline else 0)
            if result["p10"] < threshold and not (outline and outline["p10"] >= threshold):
                issue(
                    "contrast",
                    "error",
                    f"{item['name']!r} contrast is {result['p10']:.2f}:1 or lower for a tenth of its glyph pixels "
                    f"(minimum {result['minimum']:.2f}:1, weakest at {where(result['weakest_region'])})"
                    + (f" and {outline['p10']:.2f}:1 for its outline" if outline else "")
                    + f"; needs {threshold:g}:1. If the faint text is deliberate (a watermark, a ghost numeral), "
                    "waive it with layer-intent waive",
                    [item],
                    region=result["weakest_region"],
                    contrast=result["p10"],
                    required=threshold,
                    code="text-contrast",
                    **({"outline_contrast": outline["p10"]} if outline else {}),
                )

    # Without an explicit safe_area the canvas's own (size-preset) safe area applies, from the trim edge.
    from .sizes import LIVE_TOLERANCE, live_insets, safe_sides

    canvas_safe = live_insets(c) if any(safe_sides(c)) else None
    if "safe_area" in checks and (safe_area is not None or canvas_safe or avoid):
        if safe_area is not None or canvas_safe:
            left, top, right, bottom = _insets(safe_area, width, height) if safe_area is not None else canvas_safe
            safe = (left, top, width - left - right, height - top - bottom)
            # The canvas's own safe area allows the live-area tolerance; an explicit safe_area is exact.
            within = _tolerant(safe, LIVE_TOLERANCE) if safe_area is None else safe
            drawn = member_geometry(resolved, geometry)
            for item in content:
                box = outward(drawn[item["id"]])
                if not _contains(within, box):
                    x, y, w, h = drawn[item["id"]]
                    # Artwork running off the canvas is bleed, not a safe-area mistake.
                    crop = intentional_crop(item) or (
                        item["type"] in ("shape", "gradient") and (x < 0 or y < 0 or x + w > width or y + h > height))
                    issue(
                        "safe_area",
                        "info" if crop else "error" if is_text(item) else "warning",
                        f"{item['name']!r} extends outside the safe area" + (" (intentional crop or bleed)" if crop else ""),
                        [item],
                        bounds=list(box),
                        safe_area=[round(v, 2) for v in safe],
                        code="outside",
                        **({"intentional": True} if crop else {}),
                    )
        for zone in avoid or []:
            box = _box(zone, width, height, "avoid")
            for item in content:
                if _intersects(box, bounds[item["id"]]):
                    issue(
                        "safe_area",
                        "error",
                        f"{item['name']!r} intrudes on a reserved zone",
                        [item],
                        zone=[round(v, 2) for v in box],
                        code="reserved-zone",
                    )

    if "legibility" in checks:
        from .craft import body_size, stage_for
        from .text import font_data, lines, wrap_mode
        from .house_style import rule

        for item in texts:
            effective = resolved[item["id"]]
            if stage_for(effective.get("size", 0), body_size(candidate)) != "body":
                continue
            wrapped = lines(font_data(candidate, effective), effective.get("text", ""), effective["size"],
                            (effective.get("text_layout") or {}).get("width"), wrap_mode(effective))
            lengths = [len(line) for line in wrapped if line.strip()]
            if lengths and (max(lengths) > rule("line_length")["max"] or (len(lengths) > 2 and max(lengths[:-1]) < 30)):
                issue("legibility", "warning", f"{item['name']!r} body measure is {max(lengths)} characters; "
                      "aim for 30–75 characters per line", [item], code="measure", action="review",
                      characters=max(lengths))
        from .text_metrics import runt_line

        for item in texts:
            effective = resolved[item["id"]]
            runt = runt_line(candidate, effective, effective.get("size", 0) * text_scales[item["id"]])
            if runt:
                issue("legibility", "warning",
                      f"{item['name']!r} wraps with {runt['text']!r} alone on its last line ({runt['share']:.0%} of "
                      "the longest line); set text-layout wrap 'pretty' (or 'balance' for a heading), widen the box, add an "
                      "explicit line break or run fit-text", [item],
                      code="runt", action="review", line=runt["text"], share=runt["share"])

    physical = c.get("physical") and c.get("dpi")
    from .house_style import purpose_for, rule
    purpose = candidate.state.get("design_defaults", {}).get("purpose") or purpose_for(c.get("size"))
    scale_minimum = (rule("minimum_text")["minor_share_of_short_side"] * min(width, height)
                     if purpose in ("social", "poster") and not physical else None)
    from .sizes import use_size

    requested_width, requested_minimum = thumbnail_width, min_thumbnail_text
    use = use_size(c, purpose) if "legibility" in checks else None
    if "legibility" in checks and physical and thumbnail_width in ("auto", None):
        # Print is read at full size, not as a thumbnail: judge the printed point size.
        for item in texts:
            points = resolved[item["id"]].get("size", 0) * text_scales[item["id"]] * 72 / c["dpi"]
            if points < rule("minimum_text")["print_points"]:
                issue(
                    "legibility",
                    "warning",
                    f"{item['name']!r} prints at {points:.1f} pt; most print needs 6 pt or more",
                    [item],
                    points=round(points, 2),
                )
    elif "legibility" in checks and thumbnail_width is not None:  # ``None`` switches the thumbnail test off.
        from .sizes import SIZES

        # Only pieces that are really seen as thumbnails (social posts, icons, store listings) fail the test;
        # anywhere else small text at thumbnail size is worth a look, not a fix.
        category = SIZES.get(c.get("size"), {}).get("category")
        thumbnail_piece = category in ("social", "icons", "app-store")
        if thumbnail_width == "auto" and scale_minimum:
            # Use one canvas-relative minimum for social/poster work. Explicit thumbnail sizes
            # retain the caller's stricter viewing-context test.
            thumbnail_width = width
            min_thumbnail_text = scale_minimum
            thumbnail_piece = True
        elif thumbnail_width == "auto":
            thumbnail_width = 600 if c.get("size") in ("og-image", "x-post") else 320
        finite(thumbnail_width, "thumbnail_width", 16, 16384)
        scale = thumbnail_width / width
        small = []
        for item in texts:
            size = resolved[item["id"]].get("size", 0)
            if item.get("text_layout", {}).get("fit"):
                lines = max(1, resolved[item["id"]]["text"].count("\n") + 1)
                size = min(size, local_bounds[item["id"]][3] / lines)
            effective = size * text_scales[item["id"]] * scale
            if effective < min_thumbnail_text:
                small.append((item, size, effective))
        if not thumbnail_piece and use is not None and requested_width == "auto":
            # The generic "if shown as a thumbnail" note gives way to the use-size test below.
            small = []
        # One finding per chart: its labels share one size, so they are one fix (the chart's font_size).
        charts, single = {}, []
        for entry in small:
            chart = next((x for x in ancestors(entry[0]) if x.get("chart")), None)
            if chart is not None:
                charts.setdefault(chart["id"], (chart, []))[1].append(entry)
            else:
                single.append(entry)
        hint = "" if thumbnail_piece else "; only matters if this is shown as a thumbnail (thumbnail_width: null turns the test off)"
        severity = "warning" if thumbnail_piece else "info"
        for chart, entries in charts.values():
            least = min(effective for _, _, effective in entries)
            issue("legibility", severity,
                  f"chart {chart['name']!r}: {len(entries)} label(s) are {least:.1f} px tall or less at {thumbnail_width} px "
                  f"wide; aim for at least {min_thumbnail_text} px (raise the chart's font_size){hint}",
                  [item for item, _, _ in entries], thumbnail_size=round(least, 2), chart=chart["name"])
        if not thumbnail_piece and len(single) > 3:
            # Not a thumbnail piece: one note for the whole document rather than one per text layer.
            least = min(single, key=lambda entry: entry[2])
            issue("legibility", "info",
                  f"{len(single)} text layers are under {min_thumbnail_text} px tall at {thumbnail_width} px wide "
                  f"(the smallest, {least[0]['name']!r}, is {least[2]:.1f} px){hint}",
                  [item for item, _, _ in single], thumbnail_size=round(least[2], 2))
            single = []
        for item, size, effective in single:
            issue(
                "legibility",
                severity,
                f"{item['name']!r} is {effective:.1f} px tall at {thumbnail_width} px wide; "
                f"aim for at least {min_thumbnail_text} px (font size {size * min_thumbnail_text / effective:.0f}+){hint}",
                [item],
                thumbnail_size=round(effective, 2),
            )

    if use is not None and not (use["seen"] == "thumbnail" and requested_width is None):
        _use_size(candidate, use, texts, resolved, local_bounds, text_scales, ancestors, contrasts, issues, issue,
                  requested_width, requested_minimum)

    if "blanks" in checks:
        registry = candidate.state.get("blanks", {})
        for item in layers:
            entry = registry.get(item["id"])
            if not entry:
                continue
            layer = resolved[item["id"]]
            unfilled = layer.get("text") == entry["text"] if "text" in entry else layer.get("asset") == entry.get("asset")
            if unfilled:
                issue(
                    "blanks",
                    "error",
                    f"{item['name']!r} is an unfilled {entry['slot']!r} blank ({entry['hint']}); supply the copy "
                    "or remove the layer",
                    [item],
                    slot=entry["slot"],
                    code="unfilled",
                )

    if "placeholders" in checks:
        from .copy_checks import check_placeholders

        check_placeholders(candidate, resolved, layers, issue, undefined=undefined)

    if "fonts" in checks:
        from .richtext import fonts_used

        # The font each run of text is drawn in, so rich text with a font on every span is not flagged.
        # Any bundled face counts: documents saved before Noto Sans became the proofing face name DejaVu Sans.
        fallback = [item for item in texts
                    if any(font in BUNDLED_FONTS for font in fonts_used(resolved[item["id"]], FALLBACK_FONT))]
        if fallback:
            names = ", ".join(repr(x["name"]) for x in fallback[:5]) + (" …" if len(fallback) > 5 else "")
            issue(
                "fonts",
                "warning",
                f"{len(fallback)} text layer(s) use the bundled fallback font, which is for proofing only ({names}). "
                "Choose typefaces: a font pairing (vixl_reference('fonts') and font-pair over MCP; vixl font pairings and "
                "vixl font pair on the CLI), or install a font.",
                fallback,
            )

    if "print" in checks:
        _print_checks(candidate, c, resolved, local_bounds, bounds, layers, content, texts, text_scales, issue, ink_limit, min_ppi)
    if "color_vision" in checks and texts:
        _color_vision(candidate, resolved, bounds, texts, floor, text_scales, issue)
    if "color_vision" in checks:
        _series_color_vision(candidate, resolved, issue)

    if "guides" in checks or "alignment" in checks:
        from .guides import check_alignment, check_guides

        if "guides" in checks:
            check_guides(candidate, resolved, local_bounds, projection, content, issue)
        if "alignment" in checks:
            check_alignment(candidate, resolved, local_bounds, projection, content, issue)

    style_report = None
    if "style" in checks:
        from .styles import check_style

        style_report = check_style(candidate, resolved, projection, layers, content, issue, style=style)

    if brand and "brand" in checks:
        from .brand import check as check_brand
        check_brand(candidate, brand, issue)
        from .copy_checks import check_brand_words

        check_brand_words(candidate, brand, resolved, layers, issue)

    if "accessibility" in checks:
        from .accessibility import check as check_accessibility

        check_accessibility(candidate, resolved, layers, texts, bounds, text_scales, issue)

    measured_objects = set()
    if "object" in checks:
        from .object_check import check as check_objects

        measured_objects = check_objects(candidate, issue, tolerance=connect_tolerance, targets=targets,
                                         resolved=resolved, local=local_bounds)

    if "connected" in checks:
        from .parts import check_connected

        check_connected(candidate, issue, connect_tolerance, targets, resolved, skip=measured_objects)

    from .plugins import hooks as plugin_hooks

    for check_plugin in plugin_hooks("check"):
        check_plugin(checks, candidate=candidate, resolved=resolved, local_bounds=local_bounds,
                     projection=projection, issue=issue, document=document, artboard=artboard, page=page)

    if "flow" in checks and candidate.state.get("flows"):
        from .textflow import check_flows

        check_flows(candidate, resolved, issue)

    if "composition" in checks:
        from .composition import check as check_composition

        check_composition(candidate, resolved, geometry, content, role, ancestors, issue, local_bounds=local_bounds)

    if "cost" in checks:
        from .profiling import cost_findings

        for finding in cost_findings(candidate):
            target = resolved.get(finding.pop("layer"))
            issue("cost", "warning", finding.pop("message"), [target] if target else [], **finding)

    if "budget" in checks:
        from .assurance import budget_findings

        for finding in budget_findings(candidate):
            message, targets = finding.pop("message"), [resolved[i] for i in finding.pop("layers") if i in resolved]
            issue("budget", "warning", message, targets, **finding)

    if "form" in checks:
        from .forms import check_form

        check_form(candidate, resolved, local_bounds, projection, layers, issue, sample=sample)

    if "codes" in checks:
        from .codes import check_codes

        check_codes(candidate, resolved, layers, issue)

    if "links" in checks:
        check_links(candidate, [resolved[i] for i in resolved if resolved[i]["type"] == "link" and visible(resolved[i])],
                    issue)

    for name in ("motion", "captions"):
        if name in checks:
            if name == "motion":
                from .motion import findings
            else:
                from .captions import findings
            for finding in findings(candidate):
                target = resolved.get(finding.get("layer"))
                issue(name, finding["severity"], finding["message"], [target] if target else [],
                      **{k: v for k, v in finding.items() if k not in ("check", "severity", "message", "layer")})

    if "legibility" in checks and timeline_animated(project.state.get("timeline")):
        # Many apps show only frame 0: read the legibility of the poster frame too.
        from .timeline import project_at

        known = {x["message"] for x in issues}
        frame = project_at(project, 0)
        frame.state.pop("timeline", None)  # A render-only copy: the nested check must not time-check again.
        poster = check_design(frame, checks=["legibility"], thumbnail_width=thumbnail_width,
                              min_thumbnail_text=min_thumbnail_text, targets=targets, repairs=False, waivers=False)
        for item in poster["issues"]:
            if item["message"] not in known:
                issues.append({**item, "message": "At the poster frame (0 s): " + item["message"]})

    report = {
        **tally(issues),
        "issues": issues,
        "checked": {"checks": checks, "layers_checked": len(content), "layers_total": len(layers), "text_layers": len(texts)},
        **({"style": style_report} if style_report is not None else {}),
    }
    if waivers:
        from .waivers import apply as apply_waivers

        apply_waivers(project, report, checks)
    from .diagnostics import annotate

    # Stable rules, measurements, page and (for fix findings left after waivers) a suggested repair; nothing
    # is applied.
    annotate(candidate, issues, page=page_ref, min_thumbnail_text=min_thumbnail_text, repairs=repairs)
    from .check_results import summarize

    report.update(summarize(issues))
    return report


def _bold(project, layer):
    """Whether a text layer's primary font is bold (700+), for the large-text contrast tier."""
    from .text import font_data, font_style

    data = font_data(project, layer)
    return font_style(data[0] if isinstance(data, tuple) else data)[1] >= 700


def _weight(project, layer):
    from .text import font_data, font_style

    data = font_data(project, layer)
    return font_style(data[0] if isinstance(data, tuple) else data)[1]


def weight_factor(weight):
    """How much larger than a regular (400) face text in ``weight`` must be to read as well. Bold earns the
    credit WCAG gives large bold text (18.66 / 24 px), reached at 700; light and thin faces need
    ``light_weight_step`` more for every 100 below 400."""
    from .house_style import rule

    sizes = rule("minimum_text")
    if weight >= 400:
        credit = 1 - sizes["large_bold_text_px"] / sizes["large_text_px"]
        return 1 - credit * (min(weight, 700) - 400) / 300
    return 1 + sizes["light_weight_step"] * (400 - weight) / 100


def contrast_factor(contrast):
    """How much larger text of this contrast must be: none at the house secondary-text target (4.6:1) and
    above, ``contrast_step`` more for every point below it."""
    from .house_style import rule

    target = rule("contrast")["secondary_text_target"]
    return 1 + rule("minimum_text")["contrast_step"] * max(0.0, target - contrast)


def use_scale(canvas, use, requested_width="auto", min_thumbnail_text=10):
    """``(scale, minimum, context)`` for a use (``sizes.use_size``): a canvas font size times ``scale`` is its
    size at the use, which a regular face at good contrast needs to be ``minimum``. A thumbnail is measured in
    px at its width, a projected slide in px at 1080p, a sheet read across a room as a share of its short side."""
    from .house_style import rule

    sizes = rule("minimum_text")
    width, height = canvas["width"], canvas["height"]
    if use["seen"] == "thumbnail":
        shown = use["width"]
        if isinstance(requested_width, (int, float)) and not isinstance(requested_width, bool):
            shown = requested_width
        elif shown == "auto":
            shown = 600 if canvas.get("size") in ("og-image", "x-post") else 320
        return shown / width, min_thumbnail_text, f"at {shown:g} px wide ({use['as']})"
    if use["seen"] == "projected":
        # Slides export 540 pt tall (deck.points_per_pixel), so a 1080 px slide has two pixels to the point.
        return 1080 / height, sizes["projected_points"] * 2, f"on a 1080 px tall slide ({use['as']})"
    return 1 / min(width, height), sizes["distance_share_of_short_side"], f"of the sheet's short side ({use['as']})"


def _use_size(candidate, use, texts, resolved, local_bounds, text_scales, ancestors, contrasts, issues, issue,
              requested_width, min_thumbnail_text):
    """Review findings for text that is too small, too light or too faint at the size the piece is really seen
    (``sizes.use_size``): a thumbnail ``width`` px wide, a slide projected (px at 1080p) or a sheet read across a
    room (a share of its short side). The minimum is scaled by ``weight_factor`` and ``contrast_factor``.
    Decorative text and layers another legibility finding already names are skipped."""
    from .accessibility import decorative
    from .house_style import rule

    sizes = rule("minimum_text")
    seen = use["seen"]
    scale, base, context = use_scale(candidate.state["canvas"], use, requested_width, min_thumbnail_text)

    def shown_as(value):
        return f"{value:.1%}" if seen == "distance" else f"{value:.1f} px"

    earlier = [x for x in issues if x["check"] == "legibility" and x.get("code") not in ("measure", "runt")]
    named = {name for x in earlier for name in x.get("layer_ids", ())}
    # A chart with a finding already has its one fix (its font_size); its other labels are not reported again.
    named_charts = {x["chart"] for x in earlier if x.get("chart")}
    flagged = []
    for item in texts:
        layer = resolved[item["id"]]
        if item["id"] in named or decorative(layer, resolved):
            continue
        if named_charts and any(x.get("chart") and x["name"] in named_charts for x in ancestors(item)):
            continue
        size = layer.get("size", 0)
        if item.get("text_layout", {}).get("fit"):
            size = min(size, local_bounds[item["id"]][3] / max(1, layer["text"].count("\n") + 1))
        size *= text_scales[item["id"]]
        at = size * scale
        if at >= base * sizes["most_extra"]:
            continue
        weight = _weight(candidate, layer)
        contrast = contrasts.get(item["id"])
        if contrast is None and at < base * weight_factor(weight) * sizes["most_extra"]:
            from .measure import measure

            try:
                contrast = contrasts[item["id"]] = measure(candidate, target=item["id"])["contrast"]["p10"]
            except Exception:  # noqa: BLE001 - an unmeasurable layer is the contrast check's finding, not this one's.
                contrast = None
        extra = contrast_factor(contrast) if contrast is not None else 1.0
        needed = base * min(sizes["most_extra"], weight_factor(weight) * extra)
        if at < needed - 1e-9:
            heavier = next((w for w in (500, 600, 700, 800, 900) if w > weight
                            and base * min(sizes["most_extra"], weight_factor(w) * extra) <= at), None)
            flagged.append((item, size, at, needed, weight, contrast, heavier))
    if not flagged:
        return
    info = {k: v for k, v in use.items() if k != "by_pixels"}

    def why(weight, contrast):
        return f"weight {weight}" + (f" and {contrast:.1f}:1 contrast" if contrast is not None
                                     and contrast_factor(contrast) > 1 else "")

    charts, single = {}, []
    for entry in flagged:
        chart = next((x for x in ancestors(entry[0]) if x.get("chart")), None)
        if chart is not None:
            charts.setdefault(chart["id"], (chart, []))[1].append(entry)
        else:
            single.append(entry)
    groups = [(f"chart {chart['name']!r} labels", entries, " (raise the chart's font_size)")
              for chart, entries in charts.values()]
    if len(single) > 3:
        groups.append((f"{len(single)} text layers", single, ""))
        single = []
    for label, entries, fix in groups:
        item, size, at, needed, weight, contrast, _ = min(entries, key=lambda entry: entry[2] / entry[3])
        names = ", ".join(repr(entry[0]["name"]) for entry in entries[:6]) + (" …" if len(entries) > 6 else "")
        issue("legibility", "warning",
              f"{label} are too small to read {context}: the smallest, {item['name']!r}, is {shown_as(at)} "
              f"where its {why(weight, contrast)} needs {shown_as(needed)} (font size {size * needed / at:.0f}+){fix}; "
              f"{names}", [entry[0] for entry in entries], code="use-size", action="review", use=info,
              font_size=round(size, 2), needed_size=round(size * needed / at, 2), at_use=round(at, 4),
              needed_at_use=round(needed, 4))
    for item, size, at, needed, weight, contrast, heavier in single:
        issue("legibility", "warning",
              f"{item['name']!r} is {shown_as(at)} {context}; at {why(weight, contrast)} it needs {shown_as(needed)} "
              f"there: font size {size * needed / at:.0f}+"
              + (f", or a weight of {heavier}+ at this size" if heavier else ""),
              [item], code="use-size", action="review", use=info, font_size=round(size, 2),
              needed_size=round(size * needed / at, 2), at_use=round(at, 4), needed_at_use=round(needed, 4),
              weight=weight, **({"contrast": round(contrast, 2)} if contrast is not None else {}),
              **({"heavier_weight": heavier} if heavier else {}))


def _print_checks(candidate, c, resolved, local_bounds, bounds, layers, content, texts, text_scales, issue, ink_limit, min_ppi):
    """Prepress problems: ink coverage, image resolution, tiny type, bleed and live area."""
    from . import colors

    finite(ink_limit, "ink_limit", 100, 400)
    finite(min_ppi, "min_ppi", 36, 2400)
    width, height = c["width"], c["height"]
    dpi = c.get("dpi")
    if not dpi:
        issue("print", "warning", "Canvas has no dpi; create it from a print size (vixl new letter) or set canvas dpi. Assuming 300.")
        dpi = 300
    image = candidate.render()
    coverage = colors.ink_coverage(colors.cmyk_image(image))
    over = coverage["values"] > ink_limit + 0.5
    if over.any():
        ys, xs = np.nonzero(over)
        issue(
            "print",
            "warning",
            f"Ink coverage reaches {coverage['max']:.0f}% (limit {ink_limit:g}%) on {over.mean():.1%} of the page; "
            "use a lighter rich black or export with ink_limit",
            [],
            ink_max=coverage["max"],
            region=[int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)],
        )
    for item in layers:
        ppi = effective_ppi(candidate, resolved[item["id"]], bounds[item["id"]], dpi)
        if ppi is not None and ppi < min_ppi:
            issue(
                "print",
                "error" if ppi < min_ppi / 2 else "warning",
                f"{item['name']!r} prints at about {ppi:.0f} ppi (aim for {min_ppi:g}+); use a larger image or place it smaller",
                [item],
                effective_ppi=round(ppi),
            )
    for item in texts:
        points = resolved[item["id"]].get("size", 0) * text_scales[item["id"]] * 72 / dpi
        if points < 6:
            issue("print", "warning", f"{item['name']!r} is {points:.1f} pt; most print needs 6 pt or more", [item], points=round(points, 2))
    from .sizes import LIVE_TOLERANCE, live_insets, safe_sides

    bleed, sides = c.get("bleed", 0), safe_sides(c)
    if any(sides) or bleed:
        left, top, right, bottom = live_insets(c)
        live = (left, top, width - left - right, height - top - bottom)
        inset = f"{left}px" if len({left, top, right, bottom}) == 1 else f"{left}/{top}/{right}/{bottom}px left/top/right/bottom"
        for item in texts:
            if not _contains(_tolerant(live, LIVE_TOLERANCE), bounds[item["id"]]):
                issue("print", "error", f"{item['name']!r} is outside the live area ({inset} from the edge) and may be trimmed", [item], live_area=list(live))
    if bleed:
        for item in layers:
            x, y, w, h = bounds[item["id"]]
            edges = []
            for name, edge, trim, outer in (
                ("left", x, bleed, 0),
                ("top", y, bleed, 0),
                ("right", x + w, width - bleed, width),
                ("bottom", y + h, height - bleed, height),
            ):
                if abs(edge - trim) <= 2 and edge != outer:
                    edges.append(name)
            if edges:
                issue(
                    "print",
                    "warning",
                    f"{item['name']!r} stops at the trim on the {', '.join(edges)} edge; extend it into the {bleed}px bleed",
                    [item],
                )


def effective_ppi(project, layer, box, dpi):
    """Pixels per inch a placed raster or frame image prints at in its canvas box ``[x, y, w, h]``, or None
    for a layer that places no readable embedded image."""
    if layer["type"] not in ("raster", "frame") or layer.get("linked"):
        return None
    try:
        source = project.image(layer["asset"])
    except (KeyError, OSError, ValueError, VixlError):  # A missing or unreadable image places nothing to print.
        return None
    sw, sh = (layer["crop"][2] - layer["crop"][0], layer["crop"][3] - layer["crop"][1]) if layer.get("crop") else source.size
    _, _, w, h = box
    return dpi * min(sw / max(w, 1), sh / max(h, 1))


def _series_color_vision(candidate, resolved, issue):
    """Chart series (and the legend swatches that name them) told apart by color alone: pairs that look
    distinct to typical vision but merge under a color-vision deficiency. A chart that also labels its
    values or uses patterns can say so with ``layer-intent color_vision_safe``."""
    import math

    from PIL import Image

    from . import colors
    from .plugins.charts.charts import series_colors

    def distance(a, b):
        return math.dist(colors.srgb_to_oklab(tuple(v / 255 for v in a)), colors.srgb_to_oklab(tuple(v / 255 for v in b)))

    def simulate(rgb, kind):
        return colors.simulate_vision(Image.new("RGB", (1, 1), tuple(rgb)), kind).convert("RGB").getpixel((0, 0))

    for group, series in series_colors(candidate, resolved):
        if group.get("color_vision_safe") or len(series) < 2:
            continue
        for kind in ("protanopia", "deuteranopia", "tritanopia"):
            seen = [simulate(rgb, kind) for _, rgb, _ in series]
            for i in range(len(series)):
                for j in range(i + 1, len(series)):
                    normal, simulated = distance(series[i][1], series[j][1]), distance(seen[i], seen[j])
                    if normal >= 0.1 and simulated < 0.07 and simulated < normal * 0.5:
                        marks = series[i][2][:1] + series[j][2][:1]
                        issue("color_vision", "warning",
                              f"{group['name']!r} series {series[i][0]!r} and {series[j][0]!r} look alike with {kind}; "
                              "tell them apart by lightness, direct labels or patterns, or mark the chart with "
                              "layer-intent color_vision_safe if it does", [group, *marks],
                              vision=kind, distance=round(simulated, 3))


def backdrop_colors(project, hidden, boxes):
    """The colour drawn behind each canvas box once the ``hidden`` layer IDs are hidden: the median sRGB (0-1) of
    one shared render, or None for a box off the canvas. The color-vision check and the brand logo variants use it."""
    view = project.clone()
    for layer in view.state["layers"]:
        if layer["id"] in hidden:
            layer["visible"] = False
    backdrop = np.asarray(view.render().convert("RGB"))
    found = []
    for x, y, w, h in boxes:
        x, y = int(math.floor(x)), int(math.floor(y))
        w, h = int(math.ceil(w)), int(math.ceil(h))
        crop = backdrop[max(0, y): max(0, y + h), max(0, x): max(0, x + w)]
        found.append(None if crop.size == 0 else tuple(np.median(crop.reshape(-1, 3), axis=0) / 255))
    return found


def _color_vision(candidate, resolved, bounds, texts, floor, text_scales, issue):
    """Text whose contrast holds for typical vision but collapses for a color-vision deficiency."""
    from PIL import Image

    from . import colors
    from .design import resolve_color
    from .render import color as rgba

    sampled = texts[:64]
    backgrounds = backdrop_colors(candidate, {item["id"] for item in texts},
                                  [bounds[item["id"]] for item in sampled])
    for item, background in zip(sampled, backgrounds):
        layer = resolved[item["id"]]
        if background is None:
            continue
        foreground = tuple(v / 255 for v in rgba(resolve_color(layer.get("color", "black"), candidate.state))[:3])
        from .brand import required_contrast

        threshold = required_contrast(floor, layer.get("size", 0) * text_scales[item["id"]], _bold(candidate, layer))
        normal = colors.contrast_ratio(foreground, background)
        pair = Image.new("RGB", (2, 1))
        pair.putdata([tuple(round(v * 255) for v in foreground), tuple(round(v * 255) for v in background)])
        for kind in ("protanopia", "deuteranopia", "tritanopia"):
            seen = colors.simulate_vision(pair, kind).convert("RGB")
            a, b = (tuple(v / 255 for v in seen.getpixel((i, 0))) for i in (0, 1))
            ratio = colors.contrast_ratio(a, b)
            if ratio < threshold <= normal or ratio < normal * 0.6 and ratio < threshold * 1.2:
                issue(
                    "color_vision",
                    "error" if ratio < threshold else "warning",
                    f"{item['name']!r} contrast drops from {normal:.2f}:1 to {ratio:.2f}:1 with {kind}; "
                    "differ in lightness, not just hue",
                    [item],
                    vision=kind,
                    contrast=round(ratio, 2),
                )


def compare(project, before="previous", after="head", *, max_width=1024, max_height=1024, mode="side-by-side",
            isolate=None):
    """Render two revisions for an at-a-glance review. Returns ``(image, summary)``. ``isolate`` (layer
    IDs or names) shows only those layers, both sides cropped to the same box around their ink."""
    from PIL import Image

    from .proxy import isolated_pair, render_preview

    require(mode in ("side-by-side", "diff"), "mode must be side-by-side or diff", field="mode")
    left_project, right_project = project.at(before), project.at(after)
    half = max_width // 2 if mode == "side-by-side" else max_width
    region = None
    if isolate is not None:
        left_project, right_project, region = isolated_pair(left_project, right_project, isolate)
    left = render_preview(left_project, half, max_height, region=region).convert("RGBA")
    right = render_preview(right_project, half, max_height, region=region).convert("RGBA")
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS) if mode == "diff" else right
    summary = {"before": project.resolve_ref(before), "after": project.resolve_ref(after)}
    if left.size == right.size:
        difference, stats = pixel_diff(left, right)
        origin = region[:2] if region else (0, 0)
        scale = (region[2] if region else project.at(after).state["canvas"]["width"]) / right.width
        box = stats["changed_region"]
        summary.update(
            changed_fraction=stats["changed_fraction"],
            changed_region=[round(origin[0] + box[0] * scale), round(origin[1] + box[1] * scale),
                            round(box[2] * scale), round(box[3] * scale)] if box else None,
        )
        if region:
            summary["region"] = region
    else:
        difference = None
        summary["changed_region"] = "canvas size changed"
    if mode == "diff" and difference is not None:
        return diff_highlight(right, difference), summary
    return side_by_side(left, right), summary


def pixel_diff(left, right, threshold=8):
    """Changed pixels between two same-size images: ``(mask, stats)``. A pixel changes when any RGBA channel
    moves by more than ``threshold``; ``stats`` has changed_pixels, changed_fraction and changed_region
    ([x, y, w, h] or None)."""
    from PIL import Image, ImageChops

    require(left.size == right.size, "Images must be the same size to compare")
    channels = np.asarray(ImageChops.difference(left.convert("RGBA"), right.convert("RGBA")))
    changed_mask = channels.max(axis=2) > threshold
    mask = Image.fromarray((changed_mask * 255).astype(np.uint8), "L")
    box = mask.getbbox()
    changed = int(np.count_nonzero(changed_mask))
    return mask, {
        "changed_pixels": changed,
        "changed_fraction": round(changed / max(1, left.width * left.height), 4),
        "changed_region": [box[0], box[1], box[2] - box[0], box[3] - box[1]] if box else None,
    }


def diff_highlight(image, mask):
    """``image`` dimmed, with the pixels in ``mask`` painted red."""
    from PIL import Image

    image = image.convert("RGBA")
    dimmed = Image.blend(Image.new("RGBA", image.size, "black"), image, 0.35)
    return Image.composite(Image.new("RGBA", image.size, (255, 40, 40, 255)), dimmed, mask)


def side_by_side(left, right, gap=8):
    from PIL import Image

    canvas = Image.new("RGBA", (left.width + right.width + gap, max(left.height, right.height)), (128, 128, 128, 255))
    canvas.alpha_composite(left.convert("RGBA"), (0, 0))
    canvas.alpha_composite(right.convert("RGBA"), (left.width + gap, 0))
    return canvas


APPLY_ISSUES = 20  # Findings an apply call returns; vixl_check lists them all.
APPLY_PREVIEW = ("page", "region", "max_width", "max_height", "time", "isolate", "overlay", "focus", "regions")
APPLY_PREVIEW_BYTES = 524_288


def _apply_options(check, preview):
    """Validate apply's ``check`` and ``preview`` before anything is applied."""
    from .deck import DECK_CHECKS

    if check is True or not check:
        names = None
    elif isinstance(check, str):
        names = [check]
    else:
        require(isinstance(check, list) and all(isinstance(name, str) for name in check),
                "check is true, a check name or a list of check names", field="check")
        names = check
    unknown = sorted(set(names or ()) - {*CHECKS, *OPTIONAL_CHECKS, "deck", *DECK_CHECKS})
    require(not unknown, f"Unknown check(s) {unknown}; available: {', '.join(CHECKS + OPTIONAL_CHECKS)}", field="check")
    options = {}
    if preview:
        options = {} if preview is True else preview
        require(isinstance(options, dict) and not set(options) - set(APPLY_PREVIEW),
                f"preview is true or an object with {', '.join(APPLY_PREVIEW)}", field="preview")
        require(not (options.get("overlay") or options.get("focus") is not None) or check,
                "preview overlay and focus mark check findings: pass check as well", field="preview")
        regions = options.get("regions", 2)
        require(type(regions) is int and 0 <= regions <= 2, "preview regions is 0, 1 or 2", field="preview")
        options = {"max_width": 512, **options}
        options.setdefault("max_height", options["max_width"])
    return names, options


def _touched(before, project):
    """Names of the layers a batch added or changed, with the groups around them and the layers inside them."""
    layers = {layer["id"]: layer for layer in project.state["layers"]}
    changed = {ident for ident, layer in layers.items() if before.get(ident) != layer}
    ids = set(changed)
    for ident, layer in layers.items():
        parent = layer.get("parent")
        while parent in layers:
            if parent in changed:
                ids.add(ident)
            parent = layers[parent].get("parent")
    for ident in changed:
        parent = layers[ident].get("parent")
        while parent in layers:
            ids.add(parent)
            parent = layers[parent].get("parent")
    return {layers[ident]["name"] for ident in ids}


def batch_findings(project, names, touched):
    """vixl_check's summary with its issues limited to every 'fix' finding, every composition finding and those on
    the touched layers (at most APPLY_ISSUES: fixes, then composition, then the rest), plus the two weakest
    ``regions`` (critique.weakest_regions). The counts, ``passed`` and ``outcome`` still describe the whole
    document."""
    report = check_design(project, checks=names)
    from .check_results import remember

    remember(project, report)
    if "issues" not in report:
        return report

    def concerns(item):
        layers = item.get("layers") or ([item["layer"]] if item.get("layer") else [])
        return item["action"] == "fix" or (item["check"] == "composition" and item["action"] == "review") or bool(
            touched & set(layers))

    order = {action: index for index, action in enumerate(ACTIONS)}
    kept = sorted((item for item in report["issues"] if concerns(item)),
                  key=lambda item: (order[item["action"]], item["check"] != "composition"))[:APPLY_ISSUES]
    summary = {key: report[key] for key in ("passed", "errors", "warnings", "info", "outcome") if key in report}
    summary.update(issues=kept, by_action={action: [i for i, x in enumerate(kept) if x["action"] == action] for action in ACTIONS})
    if "checked" in report:
        summary["checked"] = report["checked"]
    if len(report["issues"]) > len(kept):
        summary["omitted"] = len(report["issues"]) - len(kept)
        summary["note"] = (f"Only 'fix' findings, composition findings and those on layers this batch touched are listed "
                           f"(at most {APPLY_ISSUES}); vixl_check lists all.")
    from .critique import weakest_regions

    summary["regions"] = weakest_regions(project, kept)
    return summary


def suite_names(project, suites):
    """The suites ``suites`` names: true for every attached and inherited one (library suites a project group or
    brand.json attaches by reference), a name or a list."""
    from .assurance import effective

    attached = effective(project)
    if suites is True or suites == "all":
        return list(attached)
    if suites is False or suites == "none":
        return []
    names = [suites] if isinstance(suites, str) else suites
    require(isinstance(names, list) and all(isinstance(name, str) for name in names),
            "suites is true, a suite name or a list of names", field="suites")
    from .assurance import resolve

    for name in names:
        try:
            resolve(project, name)
        except VixlError as exc:
            if exc.code == "not_found":
                raise VixlError(exc.code, f"No attached suite or library suite named {name!r}", **exc.details) from exc
            raise
    return names


def suite_summary(project, suites):
    """Run check suites (``True`` for every attached and inherited one, a name or a list) and report each one's
    status with only the rules that did not pass, so a batch's result stays small."""
    names = suite_names(project, suites)
    if not names:
        return {"note": "No suites are attached. Write one for this document's requirements with suite-set "
                        "(vixl_reference('testing') explains how) or attach a starter with workflow suite-use."}
    summary = {}
    for name in names:
        report = project.check_suite(name)
        open_rules = [item for item in report["results"] if item["status"] != "passed"]
        summary[name] = {"status": report["status"], "errors": report["errors"],
                         "needs_review": report["needs_review"], "rules": len({item["id"] for item in report["results"]
                                                                               if not item.get("automatic")}),
                         "not_passed": open_rules[:APPLY_ISSUES], "outcome": report["outcome"]}
        for key in ("source", "library", "overrides", "contract_changed"):
            if key in report and report[key] != "document":
                summary[name][key] = report[key]
        if len(open_rules) > APPLY_ISSUES:
            summary[name]["omitted"] = len(open_rules) - APPLY_ISSUES
    return summary


def apply_outcome(result):
    """The batch's outcome: it executed; validation is what its check and suites found (not run without them)."""
    from .outcomes import make, merge

    parts = [result.get("check", {}).get("outcome")]
    parts += [value.get("outcome") for value in (result.get("suites") or {}).values() if isinstance(value, dict)]
    parts = [part for part in parts if part]
    if not parts:
        reasons = ["no check or suites ran"] + (["review was skipped: the edit used the time budget"]
                                                 if result.get("review_skipped") else [])
        return make("completed", "not_run", reasons)
    return merge(*parts)


def apply_reviewed(project, operations, *, dry_run=False, detail="brief", check=None, preview=None, validate=None,
                   budget=None, suites=None, repair=None):
    """Apply a batch and, on request, check and preview the result in the same call: one round trip instead of
    apply, vixl_check and vixl_render. ``check`` is true (the default checks), a check name or a list;
    ``preview`` is true or {page, region, max_width (default 512), max_height, time, isolate, overlay, focus}:
    ``overlay`` draws the fix findings' boxes labelled with rule and layer ID, ``focus`` (an index into the
    listed findings) zooms to one. A dry run checks and previews the candidate without saving it. ``budget``
    (seconds) skips the review when the edit alone used it up, so a slow batch never also waits for a check.
    ``validate`` is Project.apply's per-operation ``validator``. ``suites`` (true, a name or a list) also runs the
    document's attached check suites (``suite_summary``), including any the batch itself attached. ``repair``
    (true or a list of repair kinds) applies the built-in repair map after the batch (repair.auto_repair) as a
    second, separately undoable history entry. Every result has an ``outcome``. Returns
    ``(result, PNG bytes or None)``."""
    import time
    from copy import deepcopy

    if not check and not preview and not suites and not repair:
        # An empty list is the review of a batch whose items were all session steps (Session.apply_steps).
        result = project.apply(operations, dry_run=dry_run, detail=detail, validator=validate) if operations else \
            {"success": True}
        result["outcome"] = apply_outcome(result)
        return result, None
    names, options = _apply_options(check, preview)
    started = time.monotonic()
    before = {layer["id"]: layer for layer in deepcopy(project.state["layers"])}
    target = project.clone() if dry_run else project  # The candidate a dry run checks and previews, then drops.
    result = target.apply(operations, detail=detail, validator=validate) if operations else {"success": True}
    result["dry_run"] = dry_run
    skipped, image = [], None
    for part, wanted in (("repair", repair), ("check", check), ("suites", suites), ("preview", preview)):
        if not wanted:
            continue
        if budget is not None and time.monotonic() - started > budget:
            skipped.append(part)
        elif part == "repair":
            from .repair import auto_repair

            repair_suites = suite_names(target, suites) if suites else []
            result["repairs"] = auto_repair(target, checks=names, suites=repair_suites, kinds=repair)
        elif part == "check":
            result["check"] = batch_findings(target, names, _touched(before, target))
        elif part == "suites":
            result["suites"] = suite_summary(target, suites)
        else:
            count = options.pop("regions", 2)
            if options.get("overlay") or options.get("focus") is not None:
                from .feedback import preview as feedback_preview

                image, result["feedback"] = feedback_preview(target, result["check"]["issues"], **options,
                                                             max_bytes=APPLY_PREVIEW_BYTES)
            else:
                from .proxy import preview_png

                image = preview_png(target, max_bytes=APPLY_PREVIEW_BYTES, **options)
            regions = (result.get("check") or {}).get("regions") or []
            if count and regions and options.get("page") is None and options.get("time") is None:
                from .critique import crops

                # Real-size looks at the weakest regions ride along with the preview (Python: PNG bytes under
                # "preview"; the interfaces turn them into images, base64 or files).
                for entry, png in zip(regions[:count], crops(target, regions[:count])):
                    entry["preview"] = png
    if skipped:
        result["review_skipped"] = (f"The edit took {time.monotonic() - started:.0f} s, so {' and '.join(skipped)} did not run; "
                                    "call vixl_check, vixl_apply(workflow='check') or vixl_render.")
    result["outcome"] = apply_outcome(result)
    if dry_run and operations:
        from .outcomes import proposed

        result["outcome"] = proposed(result["outcome"])
    return result, image


def remember_check(project, report):
    from .check_results import remember

    remember(project, report)
