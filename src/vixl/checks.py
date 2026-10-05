"""Design self-checks for agents that cannot look at every pixel.

``check_design`` reports only problems, including visible descendants of groups.
Full-canvas non-text layers are treated as background.
"""

import math
import re

import numpy as np

from .errors import require
from .model import finite

CHECKS = ("bounds", "overlap", "contrast", "safe_area", "legibility", "blanks", "fonts", "brand", "content", "form", "links")
FALLBACK_FONT = "DejaVuSans.ttf"
OPTIONAL_CHECKS = ("print", "color_vision", "guides", "alignment", "drawing")
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
    from .render import document_variables, substitute

    for item in layers:
        report = glyph_coverage(project, {**item, "text": substitute(item["text"], document_variables(project))})
        if report["missing"] or report["fallback"]:
            yield item, report


def boxed_text_overflow(project, layer):
    """For text set in a text-layout box, the (width, height) its wrapped lines need when that is
    more than the box (they are cut off), else None. Fitted, warped and path text are skipped:
    fit shrinks to the box, and warps and paths are laid out differently."""
    from .text import measure, font_data, UnsupportedText
    from .render import document_variables, substitute

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
    text = substitute(layer["text"], document_variables(project))
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
        x, y, w, h = local_bounds[parent["id"]]
        angle = math.radians(parent["rotation"])
        co, si = math.cos(angle), math.sin(angle)
        sx = parent["width"] / parent["content_width"] * (-1 if parent["flip_x"] else 1)
        sy = parent["height"] / parent["content_height"] * (-1 if parent["flip_y"] else 1)
        transform = np.array([[co * sx, -si * sy, 0], [si * sx, co * sy, 0], [0, 0, 1]])
        center = transform @ [parent["content_width"] / 2, parent["content_height"] / 2, 1]
        transform[:2, 2] = [x + w / 2 - center[0], y + h / 2 - center[1]]
        matrix = transform @ matrix
        parent = resolved.get(parent.get("parent"))
    return matrix


def canvas_projection(resolved, local_bounds):
    """Canvas-space integer bounds, text scale factors and group matrices for every layer.
    Shared by the design checks, guide checks and fillable form export, so they agree."""
    bounds, scales, matrices = {}, {}, {}
    for item in resolved.values():
        matrix = group_matrix(item, resolved, local_bounds)
        x, y, w, h = local_bounds[item["id"]]
        corners = matrix @ np.array([[x, x + w, x, x + w], [y, y, y + h, y + h], [1, 1, 1, 1]])
        left, top = np.floor(corners[:2].min(axis=1) + 1e-8).astype(int)
        right, bottom = np.ceil(corners[:2].max(axis=1) - 1e-8).astype(int)
        bounds[item["id"]] = tuple(map(int, (left, top, right - left, bottom - top)))
        scales[item["id"]] = float(np.linalg.norm(matrix[:2, 1]))
        matrices[item["id"]] = matrix
    return {"bounds": bounds, "scales": scales, "matrices": matrices}


def check_design(
    project,
    *,
    checks=None,
    targets=None,
    safe_area=None,
    avoid=None,
    thumbnail_width=None,
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
):
    """Return ``{"passed", "errors", "warnings", "issues", "checked"}`` for the rendered design.
    In a multi-page document ``page`` picks the page (default: the active page); the ``deck``
    check family reviews every page and the deck as a whole (``deck`` holds its settings:
    ``min_font``, ``max_words``, ``pages``, ``include_hidden``). ``sample`` (``"worst"`` or a CSV
    path) fills the form's fields to find values that overflow their boxes."""
    from .design_render import artboard_project
    from .render import layer_canvas_surface, resolve_layout, resolved_layers

    from .brand import for_project
    brand = for_project(project)
    if brand and "minimum_contrast" in brand:
        min_contrast = max(min_contrast or 0, brand["minimum_contrast"])
    checks = list(checks or CHECKS)
    from .deck import DECK_CHECKS

    if "deck" in checks or set(checks) & set(DECK_CHECKS):
        from .deck import check_deck

        rest = [c for c in checks if c != "deck"]
        if "deck" in checks:
            # "deck" means every deck check, with the named design checks (default: the deck set).
            rest = [c for c in rest if c not in DECK_CHECKS]
            rest = rest + list(DECK_CHECKS) if rest else None
        return check_deck(project, checks=rest, safe_area=safe_area, min_contrast=min_contrast, **(deck or {}))
    from .render import view_page

    project = view_page(project, page)
    unknown = sorted(set(checks) - set(CHECKS + OPTIONAL_CHECKS))
    require(not unknown, f"Unknown check(s) {unknown}; available: {', '.join(CHECKS + OPTIONAL_CHECKS)}", field="checks")
    candidate = artboard_project(project.clone(), artboard, comp, variables)
    c = candidate.state["canvas"]
    width, height = c["width"], c["height"]
    resolved = {item["id"]: item for item in resolved_layers(candidate)}
    local_bounds = resolve_layout(candidate, layers=list(resolved.values()))

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

    def background(item):
        return item["type"] != "text" and _contains(bounds[item["id"]], (0, 0, width, height))

    content = [item for item in layers if not background(item)]
    issues = []

    def is_text(item):
        return resolved[item["id"]]["type"] == "text"


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
            x, y, w, h = bounds[item["id"]]
            if x >= width or y >= height or x + w <= 0 or y + h <= 0:
                issue("bounds", "error", f"{item['name']!r} is entirely outside the canvas", [item], bounds=[x, y, w, h])
            elif x < 0 or y < 0 or x + w > width or y + h > height:
                severity = "error" if is_text(item) else "warning"
                issue("bounds", severity, f"{item['name']!r} is cut off by the canvas edge", [item], bounds=[x, y, w, h])
        for item in content:
            needed = boxed_text_overflow(candidate, resolved[item["id"]])
            if needed:
                layer = resolved[item["id"]]
                issue("bounds", "error",
                      f"{item['name']!r} does not fit its {layer['width']}×{layer['height']} text box at "
                      f"{layer['size']} px and is cut off (it needs {needed[0]}×{needed[1]}); enlarge the box "
                      "with text-layout or shrink the text with fit-text", [item], needs=list(needed))

    alphas = {}

    def alpha(item):
        if item["id"] not in alphas:
            tile = layer_canvas_surface(candidate, resolved[item["id"]], local_bounds, resolved)
            x, y, w, h = bounds[item["id"]]
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

    def role(item):
        return next((x["role"] for x in (item, *ancestors(item)) if x.get("role")), "content")

    if "overlap" in checks:
        drawable = [item for item in content if item["type"] != "group"]
        for i, first in enumerate(drawable):
            for second in drawable[i + 1 :]:
                if second["id"] in first.get("allow_overlap", []) or first["id"] in second.get("allow_overlap", []):
                    continue
                if (role(first) == "decoration" and not is_text(first)) or (role(second) == "decoration" and not is_text(second)):
                    continue
                a, b = bounds[first["id"]], bounds[second["id"]]
                if not _intersects(a, b):
                    continue
                texts = [x for x in (first, second) if is_text(x)]
                if not texts:
                    continue  # Overlapping images and shapes are ordinary composition.
                if len(texts) == 1:
                    other = second if texts[0] is first else first
                    if _contains(bounds[other["id"]], bounds[texts[0]["id"]]):
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
        for item in texts:
            try:
                result = measured.get(item["id"]) or measure(candidate, target=item["id"])["contrast"]
                if isinstance(result, Exception):
                    raise result
            except Exception as exc:  # A text layer without visible pixels has no contrast.
                issue("contrast", "warning", f"Could not measure {item['name']!r}: {exc}", [item])
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

    if "safe_area" in checks and (safe_area is not None or avoid):
        if safe_area is not None:
            left, top, right, bottom = _insets(safe_area, width, height)
            safe = (left, top, width - left - right, height - top - bottom)
            for item in content:
                if not _contains(safe, bounds[item["id"]]):
                    issue(
                        "safe_area",
                        "error" if is_text(item) else "warning",
                        f"{item['name']!r} extends outside the safe area",
                        [item],
                        bounds=list(bounds[item["id"]]),
                        safe_area=[round(v, 2) for v in safe],
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
    if "legibility" in checks and physical and thumbnail_width is None:
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
    elif "legibility" in checks:
        thumbnail_width = 320 if thumbnail_width is None else thumbnail_width
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
                    "warning",
                    f"{item['name']!r} is {effective:.1f} px tall at {thumbnail_width} px wide; "
                    f"aim for at least {min_thumbnail_text} px (font size {size * min_thumbnail_text / effective:.0f}+)",
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
        fallback = [item for item in texts if resolved[item["id"]].get("font", FALLBACK_FONT) == FALLBACK_FONT]
        if fallback:
            names = ", ".join(repr(x["name"]) for x in fallback[:5]) + (" …" if len(fallback) > 5 else "")
            issue(
                "fonts",
                "warning",
                f"{len(fallback)} text layer(s) use the bundled fallback font, which is for proofing only ({names}). "
                "Choose typefaces: vixl font pairings / font pair, or font install.",
                fallback,
            )

    if "print" in checks:
        _print_checks(candidate, c, resolved, local_bounds, bounds, layers, content, texts, text_scales, issue, ink_limit, min_ppi)
    if "color_vision" in checks and texts:
        _color_vision(candidate, resolved, bounds, texts, min_contrast, text_scales, issue)

    if "guides" in checks or "alignment" in checks:
        from .guides import check_alignment, check_guides

        if "guides" in checks:
            check_guides(candidate, resolved, local_bounds, projection, content, issue)
        if "alignment" in checks:
            check_alignment(candidate, resolved, local_bounds, projection, content, issue)

    if brand and "brand" in checks:
        from .brand import check as check_brand
        check_brand(candidate, brand, issue)

    if "drawing" in checks:
        from .drawing import check_drawings

        check_drawings(candidate, list(resolved.values()), issue)

    if "form" in checks:
        from .forms import check_form

        check_form(candidate, resolved, local_bounds, projection, layers, issue, sample=sample)

    if "links" in checks:
        check_links(candidate, [resolved[i] for i in resolved if resolved[i]["type"] == "link" and visible(resolved[i])],
                    issue)

    errors = sum(1 for x in issues if x["severity"] == "error")
    return {
        "passed": errors == 0,
        "errors": errors,
        "warnings": len(issues) - errors,
        "issues": issues,
        "checked": {"checks": checks, "layers": len(content), "text_layers": len(texts)},
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
    bleed, safe = c.get("bleed", 0), c.get("safe", 0)
    if safe or bleed:
        inset = bleed + safe
        live = (inset, inset, width - 2 * inset, height - 2 * inset)
        for item in texts:
            if not _contains(live, bounds[item["id"]]):
                issue("print", "error", f"{item['name']!r} is outside the live area ({inset}px from the edge) and may be trimmed", [item], live_area=list(live))
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


def compare(project, before="previous", after="head", *, max_width=1024, max_height=1024, mode="side-by-side"):
    """Render two revisions for an at-a-glance review. Returns ``(image, summary)``."""
    from PIL import Image, ImageChops

    from .proxy import render_preview

    require(mode in ("side-by-side", "diff"), "mode must be side-by-side or diff", field="mode")
    left_project, right_project = project.at(before), project.at(after)
    half = max_width // 2 if mode == "side-by-side" else max_width
    left = render_preview(left_project, half, max_height).convert("RGBA")
    right = render_preview(right_project, half, max_height).convert("RGBA")
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS) if mode == "diff" else right
    summary = {"before": project.resolve_ref(before), "after": project.resolve_ref(after)}
    if left.size == right.size:
        difference = ImageChops.difference(left, right).convert("L").point(lambda v: 255 if v > 8 else 0)
        box = difference.getbbox()
        changed = int(np.count_nonzero(np.asarray(difference)))
        scale = project.at(after).state["canvas"]["width"] / right.width
        summary.update(
            changed_fraction=round(changed / (right.width * right.height), 4),
            changed_region=[round(v * scale) for v in (box[0], box[1], box[2] - box[0], box[3] - box[1])]
            if box
            else None,
        )
    else:
        difference = None
        summary["changed_region"] = "canvas size changed"
    if mode == "diff" and difference is not None:
        dimmed = Image.blend(Image.new("RGBA", right.size, "black"), right, 0.35)
        highlight = Image.new("RGBA", right.size, (255, 40, 40, 255))
        return Image.composite(highlight, dimmed, difference), summary
    canvas = Image.new("RGBA", (left.width + right.width + 8, max(left.height, right.height)), (128, 128, 128, 255))
    canvas.alpha_composite(left, (0, 0))
    canvas.alpha_composite(right, (left.width + 8, 0))
    return canvas, summary
