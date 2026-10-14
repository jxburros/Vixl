"""The two weakest regions of a design, for the finishing look (craft plan 3b).

``weakest_regions`` picks, from a check's findings, the two regions that carry the most and the most severe
findings, composition first: each finding's region scores the findings that meet it (an error 3, a warning 2, a
note 1, a composition finding one more), and the second region is the best one that does not mostly repeat the
first. Findings about the whole document (fonts, links, brand) have no place. Where the findings name fewer
places, the rest are places worth a look anyway: the densest block of text and the largest empty area.
``crops`` renders them at real size (never enlarged; reduced only to fit ``max_side``), which is what
``vixl_apply`` returns with ``check`` and ``preview``.
"""

from .composition import _inside, _overlap_share, free_rectangles, geometry_boxes

COUNT = 2
MAX_SIDE = 512
CROP_BYTES = 262_144
WEIGHTS = {"error": 3, "warning": 2, "info": 1}
# Findings about the document as a whole: their box is only their first layer's.
UNPLACED = ("fonts", "links", "brand")


def _clamp(box, width, height, pad=0.0, minimum=48.0):
    x, y, w, h = box
    grow_w, grow_h = max(pad, (minimum - w) / 2), max(pad, (minimum - h) / 2)
    x0, y0 = max(0.0, x - grow_w), max(0.0, y - grow_h)
    x1, y1 = min(float(width), x + w + grow_w), min(float(height), y + h + grow_h)
    return [round(x0), round(y0), max(1, round(x1 - x0)), max(1, round(y1 - y0))]


def _meets(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def _located(item):
    box = item.get("region") or item.get("box") or item.get("bounds")
    return box if isinstance(box, (list, tuple)) and len(box) == 4 and box[2] > 0 and box[3] > 0 else None


def _visible(item, resolved):
    while item is not None:
        if not item.get("visible", True) or item.get("opacity", 1) <= 0:
            return False
        item = resolved.get(item.get("parent"))
    return True


def _fallback(project, width, height, pad):
    """The densest block of text and the largest empty area, when there are no findings to look at."""
    resolved, geo = geometry_boxes(project)
    content, texts = [], []
    for item in resolved.values():
        box = geo[item["id"]]
        if item["type"] in ("group", "adjustment") or not _visible(item, resolved) or box[2] <= 0 or box[3] <= 0:
            continue
        if item["type"] != "text" and (item.get("role") == "background" or _inside((0, 0, width, height), box)):
            continue
        content.append(box)
        if item["type"] == "text":
            texts.append(box)
    out = []
    if texts:
        side_w, side_h = width / 3, height / 3
        best, densest = 0.0, None
        for i in range(5):
            for j in range(5):
                window = (i * width / 6, j * height / 6, side_w, side_h)
                covered = 0.0
                for x, y, w, h in texts:
                    dx = min(x + w, window[0] + side_w) - max(x, window[0])
                    dy = min(y + h, window[1] + side_h) - max(y, window[1])
                    covered += max(0.0, dx) * max(0.0, dy)
                if covered > best:
                    best, densest = covered, window
        if densest is not None:
            inked = [b for b in texts if _meets(b, densest)]
            x0 = max(densest[0], min(b[0] for b in inked))
            y0 = max(densest[1], min(b[1] for b in inked))
            x1 = min(densest[0] + side_w, max(b[0] + b[2] for b in inked))
            y1 = min(densest[1] + side_h, max(b[1] + b[3] for b in inked))
            out.append({"region": _clamp((x0, y0, x1 - x0, y1 - y0), width, height, pad), "score": 0,
                        "why": "the densest block of text", "findings": []})
    if content:
        empty = free_rectangles((0.0, 0.0, float(width), float(height)), content, limit=1)
        if empty and empty[0][2] * empty[0][3] >= 0.02 * width * height:
            out.append({"region": _clamp(empty[0], width, height), "score": 0, "why": "the largest empty area",
                        "findings": []})
    return out


def weakest_regions(project, issues, count=COUNT):
    """Up to ``count`` regions ``{region, score, why, findings}`` (indexes into ``issues``), weakest first."""
    from .composition import unit_of

    canvas = project.state["canvas"]
    width, height = canvas["width"], canvas["height"]
    pad = float(unit_of(project))
    located = []
    for index, item in enumerate(issues):
        box = _located(item)
        if box is None or item.get("action") == "informational" or item.get("check") in UNPLACED:
            continue
        weight = WEIGHTS.get(item.get("severity"), 1) + (1 if item.get("check") == "composition" else 0)
        located.append((index, box, weight, item.get("check") == "composition"))
    if not located:
        return _fallback(project, width, height, pad)[:count]
    scored = []
    for index, box, _, composition in located:
        hits = [(i, w) for i, other, w, _ in located if _meets(box, other)]
        scored.append((sum(w for _, w in hits), composition, -index, box, [i for i, _ in hits]))
    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
    picked = []
    for score, _, _, box, hits in scored:
        if any(_overlap_share(box, other["_box"]) > 0.5 for other in picked):
            continue
        rules = list(dict.fromkeys(issues[i].get("rule") or issues[i].get("check") for i in hits))
        picked.append({"region": _clamp(box, width, height, pad), "score": score, "why": ", ".join(rules[:4]),
                       "findings": hits, "_box": box})
        if len(picked) == count:
            break
    # Too few distinct places: the fallback fills the rest with a place that does not repeat one already picked.
    for entry in _fallback(project, width, height, pad) if len(picked) < count else []:
        if len(picked) < count and not any(_overlap_share(entry["region"], other["_box"]) > 0.5 for other in picked):
            picked.append({**entry, "_box": entry["region"]})
    for entry in picked:
        del entry["_box"]
    return picked


def take_previews(result):
    """Remove the region PNGs ``apply_reviewed`` put under ``check.regions[i].preview`` and return them in order,
    so an interface can send them its own way (images, base64, files)."""
    out = []
    for entry in (result.get("check") or {}).get("regions") or []:
        if isinstance(entry.get("preview"), bytes):
            out.append(entry.pop("preview"))
    return out


def crops(project, regions, max_side=MAX_SIDE, max_bytes=CROP_BYTES):
    """Real-size PNGs of ``regions`` (each ``{region, ...}``): one canvas pixel per image pixel, reduced only to
    fit ``max_side``."""
    from .proxy import preview_png

    out = []
    for entry in regions:
        x, y, w, h = entry["region"]
        out.append(preview_png(project, max_width=min(max_side, w), max_height=min(max_side, h),
                               max_bytes=max_bytes, region=[x, y, w, h]))
    return out
