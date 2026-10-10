"""Reduced-resolution proxy rendering for previews.

Agents look at previews capped around 1024 px. Rendering a 24-megapixel document at full size
and then shrinking it wastes most of the work, so previews render a geometrically scaled copy
of the document instead (JPEG sources also decode at a reduced DCT scale). Features whose
inputs are fixed-size canvas rasters (effect selections) fall back to a full render.
"""

from copy import copy, deepcopy
import re

from .constants import ARTISTIC_DEFAULTS
from .design_render import repeat_items

# Layer types drawn into a box of their own size, whose edges can sit on whole preview pixels.
SNAPPED = ("raster", "solid", "gradient", "shape", "frame", "group")
CONSTRAINT = re.compile(r"^(.+\.(?:left|right|top|bottom|center-x|center-y))([+-]\d+(?:\.\d+)?)?$")


def _size(value, s):
    return max(1, round(value * s))


def _scale_layer(layer, s):
    from .stacks import scale_settings

    scale_settings(layer, s)
    if "bubble" in layer:
        for key in ("tail_width", "padding"):
            if key in layer["bubble"]:
                layer["bubble"][key] *= s
    for key in ("x", "y"):
        if key in layer:
            layer[key] = layer[key] * s
    for key in ("width", "height", "content_width", "content_height"):
        if key in layer:
            layer[key] = _size(layer[key], s)
    if "size" in layer and layer.get("type") == "text":
        layer["size"] = _size(layer["size"], s)
    if layer.get("type") == "field":
        from .forms import scale_field

        scale_field(layer, s)
    for key in ("spacing", "radius"):
        if key in layer and isinstance(layer[key], (int, float)):
            layer[key] = layer[key] * s
    if "spacing" in layer:
        layer["spacing"] = round(layer["spacing"])
    if "stroke_width" in layer:
        value = layer["stroke_width"] * s
        layer["stroke_width"] = round(value) if layer.get("type") == "text" else value
    rich = layer.get("rich")
    if rich:
        for span in rich["spans"]:
            for key in ("size", "tracking"):
                if key in span:
                    span[key] = span[key] * s
        for key in ("paragraph_spacing", "list_indent"):
            if key in rich:
                rich[key] = rich[key] * s
        for item in rich.get("paragraphs", []):
            for key in ("space_before", "space_after", "indent"):
                if key in item:
                    item[key] = item[key] * s
    layout = layer.get("text_layout")
    if layout:
        for key in ("width", "height"):
            if key in layout:
                layout[key] = _size(layout[key], s)
        if "path" in layout:
            layout["path"] = [[x * s, y * s] for x, y in layout["path"]]
    repeat = layer.get("repeat")
    if repeat:
        for key in ("dx", "dy", "dw", "dh"):
            if key in repeat:
                repeat[key] = repeat[key] * s
        for key in ("width", "height"):
            if key in repeat.get("end", {}):
                repeat["end"][key] = _size(repeat["end"][key], s)
    for name, settings in layer.get("styles", {}).items():
        for key in ("dx", "dy", "blur", "width"):
            if key in settings:
                settings[key] = settings[key] * s
    for effect in layer.get("effects", []):
        name = effect.get("name")
        if name in ("blur", "gaussian-blur"):
            effect["amount"] = effect.get("amount", 0) * s
        elif name in ("pixelate", "halftone", "crosshatch"):
            effect["amount"] = max(1, round(effect.get("amount", ARTISTIC_DEFAULTS[name]) * s))
        elif name in ("ripple", "wave", "glass"):
            effect["amount"] = effect.get("amount", ARTISTIC_DEFAULTS[name]) * s
            effect["radius"] = effect.get("radius", 12 if name == "glass" else 32) * s
    constraints = layer.get("constraints", {})
    for anchor, expression in list(constraints.items()):
        if isinstance(expression, (int, float)):
            constraints[anchor] = expression * s
        elif isinstance(expression, str):
            match = CONSTRAINT.match(expression)
            if match and match[2]:
                constraints[anchor] = f"{match[1]}{float(match[2]) * s:+g}"
    for operand in layer.get("operands", []):
        _scale_layer(operand, s)


def _snap_edges(layer, source, s):
    """Put the edges of a scaled layer on whole pixels of the scaled canvas.

    Rounding a layer's position and its size separately leaves a one-pixel gap (or overlap)
    between layers that meet at an edge, which shows as a faint seam the full-size render does
    not have (tiles placed side by side, bands, grids). Each edge goes to the nearest pixel
    instead, so two layers that share an edge still share it."""
    if source.get("pivot") is not None or source.get("rotation", 0) % 360 or source["type"] not in SNAPPED:
        return
    numeric = all(isinstance(source.get(key), (int, float)) for key in ("x", "y", "width", "height"))
    if not numeric:
        return
    if "repeat" in source:
        # Each copy's edges too, measured from the layer's own snapped corner, so the copies of a
        # repeated tile still meet.
        x0, y0 = round(source["x"] * s), round(source["y"] * s)
        layer["x"], layer["y"] = x0, y0
        layer["repeat"]["snapped"] = [
            [round((source["x"] + x) * s) - x0, round((source["y"] + y) * s) - y0,
             max(1, round((source["x"] + x + item["width"]) * s) - round((source["x"] + x) * s)),
             max(1, round((source["y"] + y + item["height"]) * s) - round((source["y"] + y) * s))]
            for item, x, y in repeat_items(source, colors=False)
        ]
        return
    for position, size in (("x", "width"), ("y", "height")):
        start = round(source[position] * s)
        layer[position], layer[size] = start, max(1, round((source[position] + source[size]) * s) - start)


def supported(state):
    for layer in state["layers"]:
        if any(effect.get("selection") or effect.get("name") in ("halftone", "crosshatch", "pixelate")
               for effect in layer.get("effects", [])):
            return False
        if layer.get("linked"):
            return False
    return True


def scaled_project(project, s):
    """Return a render-only copy of ``project`` scaled by ``s``, or None if unsupported."""
    if not supported(project.state):
        return None
    candidate = copy(project)
    state = deepcopy(project.state)
    canvas = state["canvas"]
    canvas["width"], canvas["height"] = _size(canvas["width"], s), _size(canvas["height"], s)
    if canvas.get("dpi") and any(layer.get("type") == "field" for layer in state["layers"]):
        # Fields size their values in points (dpi / 72): keep a point the same fraction of the page.
        canvas["dpi"] = canvas["dpi"] * s
    # Light positions/radii live in canvas pixels, just like the layers below.
    # Scale omitted defaults too, or a default 200px radius grows in a draft preview.
    for light in state.get("lighting", {}).get("lights", []):
        for key, default in (("x", 0), ("y", 0), ("radius", 200)):
            light[key] = light.get(key, default) * s
    for layer, source in zip(state["layers"], project.state["layers"]):
        _scale_layer(layer, s)
        _snap_edges(layer, source, s)
    from .guides import transform_guide

    for guide in state.get("guides", {}).values():
        transform_guide(guide, s)
    for style in state.get("character_styles", {}).values():
        for key in ("size", "stroke_width"):
            if key in style:
                style[key] = _size(style[key], s) if key == "size" else round(style[key] * s)
    for style in state.get("paragraph_styles", {}).values():
        if "spacing" in style:
            style["spacing"] = round(style["spacing"] * s)
    candidate.state = state
    return candidate


def isolated(project, refs, missing_ok=False):
    """A render copy that shows only the layers ``refs`` name (a group with everything inside it) on the
    canvas background. Their ancestor groups still transform them, and the clipping bases they use still
    clip them; every other layer is hidden, so constraints and layout resolve as in the document."""
    from .design import descendants
    from .errors import require

    require(isinstance(refs, list) and 0 < len(refs) <= 256 and all(isinstance(r, str) for r in refs),
            "isolate is a list of 1-256 layer IDs or names", field="isolate")
    roots = []
    for ref in refs:
        try:
            roots.append(project.layer(ref)["id"])
        except Exception:
            if not missing_ok:
                raise
    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    layers = {layer["id"]: layer for layer in candidate.state["layers"]}
    shown = set()
    for ident in roots:
        shown |= {ident} | descendants(candidate, ident)
    for ident in list(shown):
        base = layers[ident].get("clip")
        if base in layers:
            shown |= {base} | descendants(candidate, base)
    keep = set(shown)
    for ident in shown:
        parent = layers[ident].get("parent")
        while parent in layers:
            keep.add(parent)
            parent = layers[parent].get("parent")
    for ident, layer in layers.items():
        if ident not in keep:
            layer["visible"] = False
    candidate._isolated = roots
    return candidate


def ink_region(project, refs, padding=None):
    """[x, y, w, h] around everything ``refs`` draw on the canvas, padded (4% of the larger side, at
    least 4 px), or None when they draw nothing."""
    from .spatial import canvas_boxes

    boxes = canvas_boxes(project, "ink")
    found = [boxes[project.layer(ref)["id"]] for ref in refs if project.layer(ref)["id"] in boxes]
    found = [b for b in found if b[2] > 0 and b[3] > 0]
    if not found:
        return None
    x0, y0 = min(b[0] for b in found), min(b[1] for b in found)
    x1, y1 = max(b[0] + b[2] for b in found), max(b[1] + b[3] for b in found)
    pad = max(4.0, 0.04 * max(x1 - x0, y1 - y0)) if padding is None else padding
    return [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad]


def isolated_pair(before, after, refs):
    """Two revisions isolated to ``refs`` and one canvas region around their ink in either."""
    from .errors import require

    views = [isolated(side, refs, True) for side in (before, after)]
    require(any(view._isolated for view in views), f"No layer named {refs} in either revision", field="isolate")
    boxes = [box for view in views if (box := ink_region(view, view._isolated))]
    require(boxes, "The isolated layers draw nothing in either revision", field="isolate")
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    region = clamp_region([x0, y0, x1 - x0, y1 - y0], views[1].state["canvas"])
    require(region[2] > 0 and region[3] > 0, "The isolated layers are outside the canvas", field="isolate")
    return views[0], views[1], region


def clamp_region(region, canvas):
    import math

    x, y, w, h = region
    left, top = max(0, math.floor(x)), max(0, math.floor(y))
    right, bottom = min(canvas["width"], math.ceil(x + w)), min(canvas["height"], math.ceil(y + h))
    return [left, top, max(0, right - left), max(0, bottom - top)]


def render_preview(
    project, max_width, max_height, *, variables=None, artboard=None, comp=None, region=None, time=None, proof=False, simulate=None,
    guides=None, page=None, values=None, show_fields=False, isolate=None,
):
    """Render at roughly the preview size. ``region`` [x, y, w, h] (document pixels) zooms in;
    zoomed regions may be enlarged up to 8x so small details stay legible. ``time`` previews a
    timeline frame; ``proof`` soft-proofs CMYK; ``simulate`` previews color-vision deficiency."""
    from PIL import Image

    from .design_render import artboard_project
    from .errors import require

    from .render import view_page

    if page == "all":
        from .deck import contact_sheet

        count = len(project.state.get("pages") or [])
        columns = max(1, min(4, count))
        tile = max(64, min(800, (max_width - 16 * (columns + 1)) // columns))
        sheet = contact_sheet(project, width=tile, columns=columns)
        sheet.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        return sheet
    if isinstance(page, str) and page.isdigit():
        page = int(page)
    if values:
        from .forms import with_values

        project = with_values(project, values, complete=False)
    project = view_page(project, page)
    if time is not None:
        from .timeline import default_timeline, parse_time, project_at

        timeline = project.state.get("timeline") or default_timeline()
        project = project_at(project, parse_time(time, timeline["duration"], timeline.get("markers")), prune=True)
    candidate = artboard_project(project, artboard, comp, variables)
    c = candidate.state["canvas"]
    if isolate is not None:
        candidate = isolated(candidate, isolate)
        if region is None:
            region = ink_region(candidate, candidate._isolated)
            require(region is not None, "The isolated layers draw nothing here; check visibility or pass region",
                    field="isolate")
            region = clamp_region(region, c)
            require(region[2] > 0 and region[3] > 0, "The isolated layers are outside the canvas", field="isolate")
    if region is not None:
        x, y, w, h = region
        require(w > 0 and h > 0, "Region width and height must be positive", field="region")
        x, y = max(0, x), max(0, y)
        w, h = min(w, c["width"] - x), min(h, c["height"] - y)
        require(w > 0 and h > 0, "Region is outside the canvas", field="region")
    else:
        x, y, w, h = 0, 0, c["width"], c["height"]
    fit = min(max_width / w, max_height / h)
    scale = min(1.0, fit)
    image = None
    if scale < 0.75:
        proxy = scaled_project(candidate, scale)
        if proxy is not None:
            pc = proxy.state["canvas"]
            box = (round(x * scale), round(y * scale), round((x + w) * scale), round((y + h) * scale))
            if box[0] < box[2] <= pc["width"] and box[1] < box[3] <= pc["height"]:
                image = proxy.render(region=(box[0], box[1], box[2] - box[0], box[3] - box[1]))
            else:
                image = proxy.render().crop(box)
    if image is None:
        # Only the region is drawn (layers outside it are skipped) when nothing reads the whole canvas.
        image = candidate.render(region=(x, y, w, h))
    target = (max(1, min(max_width, round(w * fit))), max(1, min(max_height, round(h * fit))))
    if region is not None and fit > 1:
        target = (max(1, round(w * min(fit, 8))), max(1, round(h * min(fit, 8))))
        image = image.resize(target, Image.Resampling.LANCZOS)
    elif image.size != target and (image.width > target[0] or image.height > target[1]):
        image = image.resize(target, Image.Resampling.LANCZOS)
    if proof or simulate:
        from . import colors

        if simulate:
            image = colors.simulate_vision(image, simulate)
        if proof:
            image = colors.proof_image(image, ink_limit=None if proof is True else proof / 100)
    if guides:
        from .guides import draw_overlay

        image = image.convert("RGBA")
        draw_overlay(image, candidate, image.width / w, (x, y), None if guides is True else list(guides))
    if show_fields:
        from .forms import draw_overlay as draw_fields

        image = image.convert("RGBA")
        draw_fields(image, candidate, image.width / w, (x, y))
    return image


def encode_png(image, max_bytes):
    """PNG bytes of ``image``, shrunk by quarters until they fit ``max_bytes``."""
    from io import BytesIO

    from PIL import Image

    while True:
        # Previews are read once: try fast compression first, and the default level before shrinking.
        for level in (1, 6):
            stream = BytesIO()
            image.save(stream, format="PNG", compress_level=level)
            data = stream.getvalue()
            if len(data) <= max_bytes:
                return data
        image = image.resize(
            (max(1, image.width * 3 // 4), max(1, image.height * 3 // 4)), Image.Resampling.LANCZOS
        )


def preview_png(project, max_width=1024, max_height=1024, max_bytes=1_048_576, *, region=None, **options):
    """The preview PNG every interface returns (vixl_render_preview, REST /preview, apply's ``preview``):
    ``region`` accepts pixels or percentages; ``options`` are render_preview's."""
    from .errors import require

    require(1 <= max_width <= 4096 and 1 <= max_height <= 4096, "Preview dimensions must be 1–4096")
    require(65_536 <= max_bytes <= 4_194_304, "Preview byte limit must be 65536–4194304")
    if region is not None:
        from .checks import _box

        c = project.state["canvas"]
        region = [round(v) for v in _box(region, c["width"], c["height"], "region")]
    return encode_png(render_preview(project, max_width, max_height, region=region, **options), max_bytes)
