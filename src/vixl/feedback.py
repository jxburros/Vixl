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
