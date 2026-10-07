"""Design self-checks for agents that cannot look at every pixel.

``check_design`` reports only problems, including visible descendants of groups.
Layers marked ``role: background`` and non-text layers whose drawn geometry covers the
canvas are background and skipped; ``checked`` reports how many layers were checked of the total.
"""

import math
import re

import numpy as np

from .errors import require
from .model import finite
from .timeline import animated as timeline_animated

CHECKS = ("bounds", "overlap", "contrast", "safe_area", "legibility", "blanks", "fonts", "brand", "content", "form",
          "links", "diagram", "flow", "codes")
FALLBACK_FONT = "DejaVuSans.ttf"
OPTIONAL_CHECKS = ("print", "color_vision", "guides", "alignment", "drawing", "style", "motion", "character", "captions",
                   "connected")
# What to do about a finding. Errors and the warnings below need a design change ("fix"); other warnings
# are worth a look ("review"); notes and deliberate choices the document marked are "informational".
ACTIONS = ("fix", "review", "informational")
FIX_WARNINGS = ("legibility", "fonts", "content", "guides", "alignment", "blanks", "brand")
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
    """``fix``, ``review`` or ``informational`` for one finding."""
    if item.get("action") in ACTIONS:
        return item["action"]
    if item.get("intentional") or item["severity"] == "info" or item["check"] == "coverage":
        return "informational"
    if item["severity"] == "error" or item["check"] in FIX_WARNINGS:
        return "fix"
    return "review"


def tally(issues):
    """Counts by severity and the indexes of the findings grouped by action. Every finding gets an
    ``action``; ``passed`` ignores warnings and notes."""
    for item in issues:
        item["action"] = classify(item)
    errors = sum(1 for x in issues if x["severity"] == "error")
    return {
        "passed": errors == 0,
        "errors": errors,
        "warnings": sum(1 for x in issues if x["severity"] == "warning"),
        "info": sum(1 for x in issues if x["severity"] == "info"),
        "by_action": {action: [i for i, x in enumerate(issues) if x["action"] == action] for action in ACTIONS},
    }


def where(region):
    x, y, w, h = region
    return f"x {x}–{x + w - 1}, y {y}–{y + h - 1}"


def _intersects(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[0] + outer[2] >= inner[0] + inner[2]
        and outer[1] + outer[3] >= inner[1] + inner[3]
    )


def glyph_reports(project, layers):
    """``(layer, {"missing", "fallback"})`` for resolved text layers whose characters need a
    fallback font or that no available font covers. Text is read with the project's variables."""
    from .text import glyph_coverage
    from .render import document_variables
    from .richtext import active, glyph_coverage as rich_coverage
    from .variables import layer_text

    for item in layers:
        view = {**item, "text": layer_text(item, document_variables(project))}
        report = (rich_coverage if active(view) else glyph_coverage)(project, view)
        if report["missing"] or report["fallback"]:
            yield item, report


def boxed_text_overflow(project, layer):
    """For text set in a text-layout box, the (width, height) its wrapped lines need when that is
    more than the box (they are cut off), else None. Fitted, warped and path text are skipped:
    fit shrinks to the box, and warps and paths are laid out differently."""
    from .text import measure, font_data, UnsupportedText
    from .render import document_variables
    from .variables import layer_text

    settings = layer.get("text_layout") or {}
    if layer["type"] != "text" or "width" not in settings or settings.get("fit") or settings.get("path"):
        return None
    from .richtext import active

    if active(layer):
        from .richtext import layout as rich_layout

        result = rich_layout(project, layer)
        need = (math.ceil(result.box[2]), math.ceil(result.box[3]))
        return need if need[0] > layer["width"] + 1 or need[1] > layer["height"] + 1 else None
    if settings.get("warp", "none") != "none":
        return None
    text = layer_text(layer, document_variables(project))
    try:
        _, box = measure(font_data(project, layer), text, layer["size"], layer.get("spacing", 4),
                         layer.get("align", "left"), layer["width"])
    except UnsupportedText:
        return None
    stroke = 2 * layer.get("stroke_width", 0)
    need = (math.ceil(box[2] - box[0] + stroke), math.ceil(box[3] - box[1] + stroke))
    # A pixel of slack keeps antialiased glyph edges from counting as clipping.
    return need if need[0] > layer["width"] + 1 or need[1] > layer["height"] + 1 else None


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


def geometry_bounds(layer):
    """(left, top, right, bottom) of what the layer actually draws, in its own box's pixel space
    (the origin is the box's top-left corner). Shapes report their path geometry including stroke,
    every other layer fills its box. Checks use
    this instead of the layer box so a path drawn smaller than its (often full-canvas) box is judged
    by what it paints."""
    from .render import rest_size

    width, height = rest_size(layer)
    box = (0.0, 0.0, float(width), float(height))
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


def canvas_projection(resolved, local_bounds):
    """Canvas-space integer bounds, text scale factors and group matrices for every layer.
    Shared by the design checks, guide checks and fillable form export, so they agree."""
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
        gl, gt, gr, gb = geometry_bounds(item)
        drawn[item["id"]] = envelope(affine_corners((gl, gt, gr - gl, gb - gt), placed))
        scales[item["id"]] = float(np.linalg.norm(matrix[:2, 1]))
        matrices[item["id"]] = matrix
    return {"bounds": bounds, "scales": scales, "matrices": matrices, "exact_bounds": exact,
            "geometry_bounds": drawn}


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
):
    """Return ``{"passed", "errors", "warnings", "info", "issues", "by_action", "checked"}`` for the rendered
    design. Each issue has a ``severity`` (error, warning, info) and an ``action`` (fix, review or
    informational); ``by_action`` lists the issue indexes under each action. Layers marked as intentional
    crops (``layer-intent`` ``allow_crop``, or non-text decoration) report edge crops as info.
    In a multi-page document ``page`` picks the page (default: the active page); the ``deck``
    check family reviews every page and the deck as a whole (``deck`` holds its settings:
    ``min_font``, ``max_words``, ``pages``, ``include_hidden``). ``sample`` (``"worst"`` or a CSV
    path) fills the form's fields to find values that overflow their boxes. The ``style`` check
    evaluates the document's style tag (or ``style``, a name or list of names) rule by rule. The ``connected``
    check reports parts of a group that float free of its main body (gaps above ``connect_tolerance`` px)."""
    from .design_render import artboard_project
    from .render import layer_canvas_surface, resolve_layout, resolved_layers

    from .brand import for_project
    brand = for_project(project)
    if brand and "minimum_contrast" in brand:
        min_contrast = max(min_contrast or 0, brand["minimum_contrast"])
    # A document with animation is also checked over time (loop seam, poster frame) unless checks are named.
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
        return check_deck(project, checks=rest, safe_area=safe_area, min_contrast=min_contrast, **options)
    from .render import view_page

    project = view_page(project, page)
    unknown = sorted(set(checks) - set(CHECKS + OPTIONAL_CHECKS))
    require(not unknown, f"Unknown check(s) {unknown}; available: {', '.join(CHECKS + OPTIONAL_CHECKS)}", field="checks")
    candidate = artboard_project(project.clone(), artboard, comp, variables)
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
    projection = canvas_projection(resolved, local_bounds)
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
        if item["type"] == "shape" and item.get("shape") not in ("rectangle", "rounded-rectangle"):
            # A path or ellipse can span the canvas and still paint a sliver (a diagonal line).
            tile = layer_canvas_surface(candidate, resolved[item["id"]], local_bounds, resolved)
            return float((np.asarray(tile.getchannel("A")) > 32).mean()) >= 0.5
        return True

    content = [item for item in layers if not background(item)]
    issues = []

    def issue(check, severity, message, layers=(), **extra):
        issues.append(
            {"check": check, "severity": severity, "layers": [x["name"] for x in layers], "message": message, **extra}
        )

    for item in content:
        if any(parent.get("repeat") for parent in ancestors(item)) and set(checks) - {"contrast"}:
            issue("coverage", "warning",
                  f"{item['name']!r} is inside a repeated group; geometry checks cover its base instance. "
                  "Visually inspect the repeated instances.", [item])

    if "bounds" in checks:
        for item in content:
            x, y, w, h = geometry[item["id"]]
            if x >= width or y >= height or x + w <= 0 or y + h <= 0:
                issue("bounds", "error", f"{item['name']!r} is entirely outside the canvas", [item], bounds=[x, y, w, h])
            elif x < -1e-8 or y < -1e-8 or x + w > width + 1e-8 or y + h > height + 1e-8:
                crossed = sum((x < -1e-8, y < -1e-8, x + w > width + 1e-8, y + h > height + 1e-8))
                if intentional_crop(item) or (item["type"] in ("shape", "gradient") and crossed >= 2):
                    # Artwork that runs past two or more edges (a hill, a glow) is bleed by design.
                    issue("bounds", "info", f"{item['name']!r} bleeds off the canvas edge (" + (
                              "marked as an intentional crop)" if intentional_crop(item) else "artwork running past two edges)"),
                          [item], bounds=[x, y, w, h], intentional=True)
                else:
                    severity = "error" if is_text(item) else "warning"
                    issue("bounds", severity, f"{item['name']!r} is cut off by the canvas edge"
                          + ("" if is_text(item) else "; if the crop is deliberate, mark it with layer-intent allow_crop"),
                          [item], bounds=[x, y, w, h])
        for item in content:
            needed = boxed_text_overflow(candidate, resolved[item["id"]])
            if needed:
                layer = resolved[item["id"]]
                issue("bounds", "error",
                      f"{item['name']!r} does not fit its {layer['width']}×{layer['height']} text box at "
                      f"{layer['size']} px and is cut off (it needs {needed[0]}×{needed[1]}); enlarge the box "
                      "with text-layout or shrink the text with fit-text", [item], needs=list(needed))
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
            tile = layer_canvas_surface(candidate, resolved[item["id"]], local_bounds, resolved)
            x, y, w, h = ink(item)
            box = (max(0, x), max(0, y), min(width, x + w), min(height, y + h))
            alphas[item["id"]] = np.asarray(tile.getchannel("A").crop(box)) > 32
        return alphas[item["id"]]

    if "content" in checks:
        from .render import layer_image
        from .brushes import stroke_diagnostics
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

    # Characters no font can draw render as empty boxes (tofu), so they are reported by every
    # check run, whichever checks were selected; fallback-font warnings belong to "fonts".
    for item, report in glyph_reports(candidate, [item for item in layers if item["type"] == "text"]):
        if report["missing"]:
            issue("fonts", "error", f"{item['name']!r} has characters no font can draw ({''.join(report['missing'][:12])}); "
                  "they render as empty boxes. Import a font that covers them and add it with font-fallbacks", [item], **report)
        elif report["fallback"] and "fonts" in checks:
            issue("fonts", "warning", f"{item['name']!r} uses fallback glyphs", [item], **report)

    if "overlap" in checks:
        drawable = [item for item in content if item["type"] != "group"]
        for i, j in overlap_candidates([ink(item) for item in drawable], [is_text(item) for item in drawable], width, height):
            first, second = drawable[i], drawable[j]
            if second["id"] in first.get("allow_overlap", []) or first["id"] in second.get("allow_overlap", []):
                continue
            if (role(first) == "decoration" and not is_text(first)) or (role(second) == "decoration" and not is_text(second)):
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
                )

    # Empty text (a lyric between lines, a cleared label) draws nothing to measure.
    texts = [item for item in content if is_text(item) and resolved[item["id"]].get("text", "").strip()]
    if "contrast" in checks:
        from .measure import measure, top_level_contrast

        # Top-level text is measured from one shared render; grouped text renders its own.
        top = [item["id"] for item in texts if not item.get("parent")]
        try:
            measured = top_level_contrast(candidate, top) if top else {}
        except Exception:  # noqa: BLE001 - measure each layer separately and report its own failure.
            measured = {}
        from .charts import chart_contrast

        measured.update(chart_contrast(candidate, resolved, local_bounds, bounds, [x for x in texts if x.get("parent")]))
        for item in texts:
            result = measured.get(item["id"])
            try:
                if result is None or isinstance(result, Exception):
                    # The single-pass measurement failed for this layer: measure it on its own.
                    result = measure(candidate, target=item["id"])["contrast"]
            except Exception as exc:  # noqa: BLE001 - never a silent pass: an unmeasurable layer is an error.
                issue("contrast", "error", f"Could not measure the contrast of {item['name']!r}: {exc}", [item])
                continue
            large = resolved[item["id"]].get("size", 0) * text_scales[item["id"]] >= 24
            threshold = min_contrast or (3.0 if large else 4.5)
            # Outlined text reads through its outline when the fill blends into the backdrop.
            outline = result.get("outline")
            if result["p10"] < threshold and not (outline and outline["p10"] >= threshold):
                issue(
                    "contrast",
                    "error",
                    f"{item['name']!r} contrast is {result['p10']:.2f}:1 or lower for a tenth of its glyph pixels "
                    f"(minimum {result['minimum']:.2f}:1, weakest at {where(result['weakest_region'])})"
                    + (f" and {outline['p10']:.2f}:1 for its outline" if outline else "")
                    + f"; needs {threshold:g}:1",
                    [item],
                    region=result["weakest_region"],
                    contrast=result["p10"],
                    required=threshold,
                    **({"outline_contrast": outline["p10"]} if outline else {}),
                )

    # Without an explicit safe_area the canvas's own (size-preset) safe area applies, from the trim edge.
    from .sizes import safe_sides

    canvas_safe = tuple(c.get("bleed", 0) + v for v in safe_sides(c)) if any(safe_sides(c)) else None
    if "safe_area" in checks and (safe_area is not None or canvas_safe or avoid):
        if safe_area is not None or canvas_safe:
            left, top, right, bottom = _insets(safe_area, width, height) if safe_area is not None else canvas_safe
            safe = (left, top, width - left - right, height - top - bottom)
            for item in content:
                box = outward(geometry[item["id"]])
                if not _contains(safe, box):
                    x, y, w, h = geometry[item["id"]]
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
                    )

    physical = c.get("physical") and c.get("dpi")
    if "legibility" in checks and physical and thumbnail_width in ("auto", None):
        # Print is read at full size, not as a thumbnail: judge the printed point size.
        for item in texts:
            points = resolved[item["id"]].get("size", 0) * text_scales[item["id"]] * 72 / c["dpi"]
            if points < 6:
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
        if thumbnail_width == "auto":
            thumbnail_width = 600 if c.get("size") in ("og-image", "x-post") else 320
        finite(thumbnail_width, "thumbnail_width", 16, 16384)
        scale = thumbnail_width / width
        for item in texts:
            size = resolved[item["id"]].get("size", 0)
            if item.get("text_layout", {}).get("fit"):
                lines = max(1, resolved[item["id"]]["text"].count("\n") + 1)
                size = min(size, local_bounds[item["id"]][3] / lines)
            effective = size * text_scales[item["id"]] * scale
            if effective < min_thumbnail_text:
                issue(
                    "legibility",
                    "warning" if thumbnail_piece else "info",
                    f"{item['name']!r} is {effective:.1f} px tall at {thumbnail_width} px wide; "
                    f"aim for at least {min_thumbnail_text} px (font size {size * min_thumbnail_text / effective:.0f}+)"
                    + ("" if thumbnail_piece else "; only matters if this is shown as a thumbnail (thumbnail_width: null turns the test off)"),
                    [item],
                    thumbnail_size=round(effective, 2),
                )

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
                )

    if "fonts" in checks:
        from .richtext import fonts_used

        # The font each run of text is drawn in, so rich text with a font on every span is not flagged.
        fallback = [item for item in texts if FALLBACK_FONT in fonts_used(resolved[item["id"]], FALLBACK_FONT)]
        if fallback:
            names = ", ".join(repr(x["name"]) for x in fallback[:5]) + (" …" if len(fallback) > 5 else "")
            issue(
                "fonts",
                "warning",
                f"{len(fallback)} text layer(s) use the bundled fallback font, which is for proofing only ({names}). "
                "Choose typefaces: a font pairing (vixl_fonts and vixl_font_pair over MCP; vixl font pairings and "
                "vixl font pair on the CLI), or install a font.",
                fallback,
            )

    if "print" in checks:
        _print_checks(candidate, c, resolved, local_bounds, bounds, layers, content, texts, text_scales, issue, ink_limit, min_ppi)
    if "color_vision" in checks and texts:
        _color_vision(candidate, resolved, bounds, texts, min_contrast, text_scales, issue)
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

    if "connected" in checks:
        from .parts import check_connected

        check_connected(candidate, issue, connect_tolerance, targets, resolved)

    if "drawing" in checks:
        from .drawing import check_drawings

        check_drawings(candidate, list(resolved.values()), issue)

    if "diagram" in checks and candidate.state.get("diagrams"):
        from .diagrams import check_diagrams

        check_diagrams(candidate, resolved, local_bounds, projection, issue)

    if "flow" in checks and candidate.state.get("flows"):
        from .textflow import check_flows

        check_flows(candidate, resolved, issue)

    if "form" in checks:
        from .forms import check_form

        check_form(candidate, resolved, local_bounds, projection, layers, issue, sample=sample)

    if "codes" in checks:
        from .codes import check_codes

        check_codes(candidate, resolved, layers, issue)

    if "links" in checks:
        check_links(candidate, [resolved[i] for i in resolved if resolved[i]["type"] == "link" and visible(resolved[i])],
                    issue)

    for name in ("motion", "character", "captions"):
        if name in checks:
            if name == "motion":
                from .motion import findings
            elif name == "character":
                from .characters import findings
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
                              min_thumbnail_text=min_thumbnail_text, targets=targets)
        for item in poster["issues"]:
            if item["message"] not in known:
                issues.append({**item, "message": "At the poster frame (0 s): " + item["message"]})

    return {
        **tally(issues),
        "issues": issues,
        "checked": {"checks": checks, "layers_checked": len(content), "layers_total": len(layers), "text_layers": len(texts)},
        **({"style": style_report} if style_report is not None else {}),
    }


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
        layer = resolved[item["id"]]
        if layer["type"] not in ("raster", "frame") or layer.get("linked"):
            continue
        try:
            source = candidate.image(layer["asset"])
        except Exception:
            continue
        sw, sh = (layer["crop"][2] - layer["crop"][0], layer["crop"][3] - layer["crop"][1]) if layer.get("crop") else source.size
        _, _, w, h = bounds[item["id"]]
        ppi = dpi * min(sw / max(w, 1), sh / max(h, 1))
        if ppi < min_ppi:
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
    from .sizes import safe_sides

    bleed, sides = c.get("bleed", 0), safe_sides(c)
    if any(sides) or bleed:
        left, top, right, bottom = (bleed + v for v in sides)
        live = (left, top, width - left - right, height - top - bottom)
        inset = f"{left}px" if len({left, top, right, bottom}) == 1 else f"{left}/{top}/{right}/{bottom}px left/top/right/bottom"
        for item in texts:
            if not _contains(live, bounds[item["id"]]):
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


def _series_color_vision(candidate, resolved, issue):
    """Chart series (and the legend swatches that name them) told apart by color alone: pairs that look
    distinct to typical vision but merge under a color-vision deficiency. A chart that also labels its
    values or uses patterns can say so with ``layer-intent color_vision_safe``."""
    import math

    from PIL import Image

    from . import colors
    from .charts import series_colors

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


def _color_vision(candidate, resolved, bounds, texts, min_contrast, text_scales, issue):
    """Text whose contrast holds for typical vision but collapses for a color-vision deficiency."""
    from PIL import Image

    from . import colors
    from .design import resolve_color
    from .render import color as rgba

    hidden = candidate.clone()
    ids = {item["id"] for item in texts}
    for layer in hidden.state["layers"]:
        if layer["id"] in ids:
            layer["visible"] = False
    backdrop = np.asarray(hidden.render().convert("RGB"))
    for item in texts[:64]:
        layer = resolved[item["id"]]
        x, y, w, h = bounds[item["id"]]
        crop = backdrop[max(0, y): max(0, y + h), max(0, x): max(0, x + w)]
        if crop.size == 0:
            continue
        background = tuple(np.median(crop.reshape(-1, 3), axis=0) / 255)
        foreground = tuple(v / 255 for v in rgba(resolve_color(layer.get("color", "black"), candidate.state))[:3])
        large = layer.get("size", 0) * text_scales[item["id"]] >= 24
        threshold = min_contrast or (3.0 if large else 4.5)
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
APPLY_PREVIEW = ("page", "region", "max_width", "max_height", "time", "isolate")


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
    """vixl_check's summary with its issues limited to the touched layers plus every 'fix' finding (at most
    APPLY_ISSUES, fixes first). The counts and ``passed`` still describe the whole document."""
    report = check_design(project, checks=names)
    if "issues" not in report:
        return report

    def concerns(item):
        layers = item.get("layers") or ([item["layer"]] if item.get("layer") else [])
        return item["action"] == "fix" or bool(touched & set(layers))

    order = {action: index for index, action in enumerate(ACTIONS)}
    kept = sorted((item for item in report["issues"] if concerns(item)), key=lambda item: order[item["action"]])[:APPLY_ISSUES]
    summary = {key: report[key] for key in ("passed", "errors", "warnings", "info") if key in report}
    summary.update(issues=kept, by_action={action: [i for i, x in enumerate(kept) if x["action"] == action] for action in ACTIONS})
    if "checked" in report:
        summary["checked"] = report["checked"]
    if len(report["issues"]) > len(kept):
        summary["omitted"] = len(report["issues"]) - len(kept)
        summary["note"] = f"Only 'fix' findings and those on layers this batch touched are listed (at most {APPLY_ISSUES}); vixl_check lists all."
    return summary


def suite_summary(project, suites):
    """Run attached check suites (``True`` for all of them, a name or a list) and report each one's status
    with only the rules that did not pass, so a batch's result stays small."""
    attached = project.state.get("suites", {})
    if suites is True:
        names = list(attached)
    else:
        names = [suites] if isinstance(suites, str) else suites
        require(isinstance(names, list) and all(isinstance(name, str) for name in names),
                "suites is true, a suite name or a list of names", field="suites")
        missing = [name for name in names if name not in attached]
        require(not missing, f"No attached suite named {missing}; attached: {', '.join(attached) or 'none'}",
                field="suites")
    if not names:
        return {"note": "No suites are attached. Write one for this document's requirements with suite-set "
                        "(vixl_guide('testing') explains how) or attach a starter with workflow suite-use."}
    summary = {}
    for name in names:
        report = project.check_suite(name)
        open_rules = [item for item in report["results"] if item["status"] != "passed"]
        summary[name] = {"status": report["status"], "errors": report["errors"],
                         "needs_review": report["needs_review"], "rules": len(attached[name]["rules"]),
                         "not_passed": open_rules[:APPLY_ISSUES]}
        if len(open_rules) > APPLY_ISSUES:
            summary[name]["omitted"] = len(open_rules) - APPLY_ISSUES
    return summary


def apply_reviewed(project, operations, *, dry_run=False, detail="brief", check=None, preview=None, validate=None,
                   budget=None, suites=None):
    """Apply a batch and, on request, check and preview the result in the same call: one round trip instead of
    apply, vixl_check and vixl_render_preview. ``check`` is true (the default checks), a check name or a list;
    ``preview`` is true or {page, region, max_width (default 512), max_height, time}. A dry run checks and previews
    the candidate without saving it. ``budget`` (seconds) skips the review when the edit alone used it up, so a slow
    batch never also waits for a check. ``validate`` is Project.apply's per-operation ``check``. ``suites`` (true,
    a name or a list) also runs the document's attached check suites (``suite_summary``), including any the
    batch itself attached. Returns ``(result, PNG bytes or None)``."""
    import time
    from copy import deepcopy

    if not check and not preview and not suites:
        return project.apply(operations, dry_run=dry_run, detail=detail, check=validate), None
    names, options = _apply_options(check, preview)
    started = time.monotonic()
    before = {layer["id"]: layer for layer in deepcopy(project.state["layers"])}
    target = project.clone() if dry_run else project  # The candidate a dry run checks and previews, then drops.
    result = target.apply(operations, detail=detail, check=validate)
    result["dry_run"] = dry_run
    skipped, image = [], None
    for part, wanted in (("check", check), ("suites", suites), ("preview", preview)):
        if not wanted:
            continue
        if budget is not None and time.monotonic() - started > budget:
            skipped.append(part)
        elif part == "check":
            result["check"] = batch_findings(target, names, _touched(before, target))
        elif part == "suites":
            result["suites"] = suite_summary(target, suites)
        else:
            from .proxy import preview_png

            image = preview_png(target, max_bytes=524_288, **options)
    if skipped:
        result["review_skipped"] = (f"The edit took {time.monotonic() - started:.0f} s, so {' and '.join(skipped)} did not run; "
                                    "call vixl_check, vixl_workflow check or vixl_render_preview.")
    return result, image
