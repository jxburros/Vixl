"""Compact visual feedback (#526): finding boxes drawn over a preview, and detail crops of a finding.

An overlay is drawn on a copy of the returned preview only: the document and its exports never change.
Each box is labelled with the finding's rule and layer ID; ``overlay_entries`` reports the same boxes in
document pixels (``region``) and in preview pixels (``box``) so an agent can match what it sees.
"""

from .errors import require

OVERLAY_LIMIT = 20  # Boxes drawn on one preview; the rest are counted, not drawn.
COLORS = {"fix": (230, 30, 60, 255), "review": (240, 150, 0, 255)}


def finding_region(item):
    """The document-pixel box a finding is about: its measured region, else the layer bounds or box."""
    for key in ("region", "bounds", "box"):
        value = item.get(key)
        if isinstance(value, (list, tuple)) and len(value) == 4 and all(isinstance(v, (int, float)) for v in value):
            return [float(v) for v in value]
    return None


def focus_region(item, canvas, margin=0.5):
    """A detail crop around a finding: its region widened by ``margin`` of its size (at least 24 px) on each
    side and kept inside the canvas."""
    region = finding_region(item)
    require(region is not None, "This finding has no region to zoom to", field="focus")
    x, y, w, h = region
    pad_x, pad_y = max(24, w * margin), max(24, h * margin)
    left, top = max(0, x - pad_x), max(0, y - pad_y)
    right, bottom = min(canvas["width"], x + w + pad_x), min(canvas["height"], y + h + pad_y)
    require(right > left and bottom > top, "This finding lies outside the canvas", field="focus")
    return [round(left), round(top), max(1, round(right - left)), max(1, round(bottom - top))]


def overlay_entries(findings, scale, origin=(0, 0), size=None, actions=("fix",)):
    """Boxes for the findings whose action is in ``actions``: ``{index, rule, action, layers, layer_ids,
    region, box}`` with ``box`` in preview pixels (``region`` scaled by ``scale`` after subtracting ``origin``)."""
    entries = []
    for index, item in enumerate(findings):
        if item.get("action") not in actions:
            continue
        region = finding_region(item)
        if region is None:
            continue
        x, y, w, h = region
        box = [round((x - origin[0]) * scale), round((y - origin[1]) * scale),
               max(1, round(w * scale)), max(1, round(h * scale))]
        if size and (box[0] >= size[0] or box[1] >= size[1] or box[0] + box[2] <= 0 or box[1] + box[3] <= 0):
            continue  # outside this view
        entries.append({"index": index, "rule": item.get("rule", item.get("check")), "action": item.get("action"),
                        "layers": item.get("layers", []), "layer_ids": item.get("layer_ids", []),
                        "region": [round(v, 2) for v in region], "box": box})
    return entries


def draw_overlay(image, entries, limit=OVERLAY_LIMIT):
    """``image`` (a copy) with each entry's box outlined and labelled ``rule · layer ID``."""
    from PIL import ImageDraw, ImageFont

    image = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(10, min(14, image.width // 40)))
    shared = {}  # Findings on the same box share one outline and label.
    for entry in entries[:limit]:
        shared.setdefault(tuple(entry["box"]), []).append(entry)
    for group in shared.values():
        entry = group[0]
        x, y, w, h = entry["box"]
        ink = COLORS.get(entry["action"], COLORS["review"])
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=ink, width=2)
        label = f"{entry['index']} {entry['rule']}" + (f" · {entry['layer_ids'][0]}" if entry["layer_ids"] else "")
        if len(group) > 1:
            label += f" (+{', '.join(str(other['index']) for other in group[1:])})"
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        tx = min(max(0, x), max(0, image.width - (right - left) - 4))
        ty = y - (bottom - top) - 4 if y - (bottom - top) - 4 >= 0 else min(image.height - (bottom - top) - 4, y + h + 1)
        draw.rectangle([tx, ty, tx + right - left + 4, ty + bottom - top + 4], fill=ink)
        draw.text((tx + 2 - left, ty + 2 - top), label, fill=(255, 255, 255, 255), font=font)
    return image


def preview(project, findings, *, overlay=False, focus=None, max_width=512, max_height=None, max_bytes=524_288,
            region=None, **options):
    """``(PNG bytes, feedback)``: the preview (zoomed to finding ``focus`` when given), with the fix findings'
    boxes drawn when ``overlay`` is set. ``feedback`` holds the boxes, the scale and the byte budget."""
    from .checks import _box
    from .proxy import encode_png, render_preview

    canvas = project.state["canvas"]
    if focus is not None:
        require(type(focus) is int and 0 <= focus < len(findings),
                f"focus is the index of a listed finding (0-{len(findings) - 1})", field="focus")
        region = focus_region(findings[focus], canvas)
    elif region is not None:
        region = [round(v) for v in _box(region, canvas["width"], canvas["height"], "region")]
    image = render_preview(project, max_width, max_height or max_width, region=region, **options)
    origin = region[:2] if region else (0, 0)
    scale = image.width / (region[2] if region else canvas["width"])
    feedback = {"scale": round(scale, 4), "size": list(image.size), "max_bytes": max_bytes}
    if region:
        feedback["region"] = region
    if focus is not None:
        feedback["focus"] = focus
    if overlay:
        entries = overlay_entries(findings, scale, origin, image.size, actions=("fix", "review") if focus is not None
                                  else ("fix",))
        image = draw_overlay(image, entries)
        feedback["overlay"] = entries[:OVERLAY_LIMIT]
        if len(entries) > OVERLAY_LIMIT:
            feedback["overlay_omitted"] = len(entries) - OVERLAY_LIMIT
    data = encode_png(image, max_bytes)
    feedback["bytes"] = len(data)
    return data, feedback


BOUNDS_LIMIT = 40  # Layer boxes labelled on one preview; the rest are counted, not drawn.
RULER_STEPS = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000)


def ruler_step(span):
    """The grid step (document pixels) that puts about ten lines across ``span``."""
    return next((step for step in RULER_STEPS if span / step <= 12), RULER_STEPS[-1])


def _chip(draw, font, x, y, label, fill, size):
    """A label on a solid chip, kept inside the image; returns nothing."""
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    width, height = right - left + 4, bottom - top + 4
    x = min(max(0, x), max(0, size[0] - width))
    y = min(max(0, y), max(0, size[1] - height))
    draw.rectangle([x, y, x + width, y + height], fill=fill)
    draw.text((x + 2 - left, y + 2 - top), label, fill=(255, 255, 255, 255), font=font)


def draw_coordinates(image, project, scale, origin, rulers=None, bounds=None):
    """A placement aid drawn on a preview (a copy; the document and its exports never change, #802).

    ``rulers`` (true, or a step in document pixels) draws a grid with every line labelled by its document
    coordinate along the top and left edges, so a position can be read off the picture. ``bounds`` (true for
    every top-level visible layer, or layer names) outlines each layer's box labelled ``name x,y WxH``.
    ``scale``/``origin`` map document pixels to the image, so a zoomed ``region`` keeps absolute coordinates.
    Returns ``(image, info)``: ``info`` holds the step and the boxes in document pixels."""
    from PIL import ImageDraw, ImageFont

    from .geometry import compact_number as _compact

    def compact_number(value):
        return _compact(value, 1)

    image = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default(size=max(10, min(13, image.width // 45)))
    info = {}
    span = (image.width / scale, image.height / scale)
    if rulers:
        require(rulers is True or (isinstance(rulers, (int, float)) and not isinstance(rulers, bool) and rulers > 0),
                "rulers is true or a grid step in document pixels", field="rulers")
        step = ruler_step(max(span)) if rulers is True else rulers
        require(max(span) / step <= 200, f"A rulers step of {compact_number(step)} px draws more than 200 lines here; "
                "use a larger step or zoom with region", field="rulers")
        info["rulers"] = {"step": step, "from": [round(v, 1) for v in origin],
                          "to": [round(origin[0] + span[0], 1), round(origin[1] + span[1], 1)]}
        dark, light, chip = (0, 0, 0, 110), (255, 255, 255, 110), (20, 20, 20, 215)
        for axis in (0, 1):
            first = -(-origin[axis] // step) * step
            value = first
            while value <= origin[axis] + span[axis]:
                at = round((value - origin[axis]) * scale)
                # A dark and a light line side by side stay visible on any artwork.
                for offset, ink in ((0, dark), (1, light)):
                    line = (at + offset, 0, at + offset, image.height) if axis == 0 else (0, at + offset, image.width, at + offset)
                    draw.line(line, fill=ink, width=1)
                value += step
            value = first
            while value <= origin[axis] + span[axis]:
                at = round((value - origin[axis]) * scale)
                _chip(draw, font, *((at + 2, 0) if axis == 0 else (0, at + 2)), compact_number(value), chip, image.size)
                value += step
    if bounds:
        layers = project.state["layers"]
        if bounds is True:
            picked = [layer for layer in layers if not layer.get("parent") and layer.get("visible", True)]
        else:
            require(isinstance(bounds, (list, tuple)) and all(isinstance(name, str) for name in bounds),
                    "bounds is true or a list of layer names", field="bounds")
            picked = [project.layer(name) for name in bounds]
        ink = (200, 0, 160, 255)
        boxes = []
        for layer in picked:
            x, y, w, h = project.bounds(layer["id"])
            box = (round((x - origin[0]) * scale), round((y - origin[1]) * scale),
                   round((x + w - origin[0]) * scale), round((y + h - origin[1]) * scale))
            if box[2] <= 0 or box[3] <= 0 or box[0] >= image.width or box[1] >= image.height:
                continue  # outside this view
            boxes.append((layer, [x, y, w, h], box))
        for layer, _, box in boxes[:BOUNDS_LIMIT]:
            draw.rectangle([box[0], box[1], max(box[0], box[2] - 1), max(box[1], box[3] - 1)], outline=ink, width=1)
        for layer, (x, y, w, h), box in boxes[:BOUNDS_LIMIT]:
            label = f"{layer['name']} {compact_number(x)},{compact_number(y)} {compact_number(w)}x{compact_number(h)}"
            _chip(draw, font, box[0], box[1] - 14 if box[1] >= 14 else box[1] + 1, label, ink, image.size)
        info["bounds"] = [{"name": layer["name"], "bounds": [round(v, 2) for v in region]}
                          for layer, region, _ in boxes[:BOUNDS_LIMIT]]
        if len(boxes) > BOUNDS_LIMIT:
            info["bounds_omitted"] = len(boxes) - BOUNDS_LIMIT
    return image, info
