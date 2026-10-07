"""Inspectable text geometry in unrotated parent coordinates, shared by both text kinds."""

from collections import OrderedDict
from functools import lru_cache
import threading

from .text import advance, face, font_data, glyph_outline, lines, plan


@lru_cache(maxsize=256)
def font_metrics(data, size):
    outline = face(data)[0]
    factor = size / outline["head"].unitsPerEm
    cmap = outline.getBestCmap() or {}
    os2 = outline.get("OS/2")

    def height(field, character):
        value = getattr(os2, field, 0)
        if not value and ord(character) in cmap:
            box = glyph_outline(data, cmap[ord(character)])[1]
            value = box[3] if box else 0
        return value * factor

    return {"ascent": outline["hhea"].ascent * factor,
            "descent": -outline["hhea"].descent * factor,
            "cap_height": height("sCapHeight", "H"), "x_height": height("sxHeight", "x")}


@lru_cache(maxsize=4096)
def path_commands(path):
    """The pen calls an SVG glyph path makes, parsed once per glyph: replaying them draws exactly what parsing the
    path again would, and a long text repeats the same few glyphs thousands of times."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.svgLib.path import parse_path

    pen = RecordingPen()
    parse_path(path, pen)
    return tuple(pen.value)


def inspect_text(project, layer, bounds):
    """Return actual outline ink, typographic line boxes, and baseline(s), in pixels.

    Resolved layer bounds retain their historical sizing behavior. These additional boxes
    distinguish ink from line spacing without moving existing artwork. Rotation and group
    transforms are deliberately excluded (``metrics_space`` documents this).
    """
    from .richtext import active, fitted
    from .text import UnsupportedText

    x, y = bounds[:2]
    data = font_data(project, layer)
    primary = data[0] if isinstance(data, tuple) else data
    try:
        rich = active(layer)
        key = None if rich else _plain_key(project, layer, data)
        with _LOCK:
            cached = _PLAIN.get(key) if key is not None else None
            if cached is not None:
                _PLAIN.move_to_end(key)
        if cached is not None:
            metrics, ink_box, line_box, baselines = cached
            return _placed(x, y, metrics, ink_box, line_box, baselines)
        metrics = font_metrics(primary, layer["size"])
        boxes = []
        if rich:
            result = fitted(project, layer)
            for glyph in result.glyphs:
                box = glyph_outline(glyph.data, glyph.name)[1]
                if box:
                    f = glyph.size / face(glyph.data)[0]["head"].unitsPerEm
                    boxes.append((glyph.x + box[0] * f, glyph.y - box[3] * f,
                                  glyph.x + box[2] * f, glyph.y - box[1] * f))
            baselines = [row[1] for row in result.lines]
            line_box = (0, 0, result.width, result.height)
            metrics = font_metrics(primary, layer["size"] * result.size_scale)
        else:
            from fontTools.misc.transform import Transform
            from fontTools.pens.boundsPen import BoundsPen
            from fontTools.pens.transformPen import TransformPen

            result = plan(project, layer)
            metrics = font_metrics(primary, result.size)
            for path, matrix in result.paths:
                pen = BoundsPen(None)
                transformed = TransformPen(pen, Transform(*matrix))
                for command, points in path_commands(path):
                    getattr(transformed, command)(*points)
                if pen.bounds:
                    boxes.append(pen.bounds)
            wrapped = lines(data, layer["text"], result.size,
                            layer["width"] if "width" in layer.get("text_layout", {}) else None)
            step = metrics["ascent"] + metrics["descent"] + layer.get("spacing", 4)
            baselines = [metrics["ascent"] + index * step - result.box[1] for index in range(len(wrapped))]
            width = max((advance(data, line, result.size) for line in wrapped), default=0)
            line_box = (result.offset - result.box[0], -result.box[1], width,
                        len(wrapped) * step - layer.get("spacing", 4))
        if boxes:
            left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
            ink_box = (left, top, max(b[2] for b in boxes) - left, max(b[3] for b in boxes) - top)
        else:
            ink_box = (0, 0, 0, 0)
        if key is not None:
            with _LOCK:
                _PLAIN[key] = (dict(metrics), ink_box, tuple(line_box), tuple(baselines))
                while len(_PLAIN) > PLAIN_ENTRIES:
                    _PLAIN.popitem(last=False)
        return _placed(x, y, metrics, ink_box, line_box, baselines)
    except UnsupportedText:
        return {"metrics_unavailable": "This font requires raster text layout"}


# Plain-text measurements, keyed by everything they read: the font data (the primary font and its fallback chain,
# so a changed font file, import or fallback list is a new key), every layer field except its position, and the
# size limits ``plan`` enforces. Every inspect measures every text layer, so an edit to one layer of a large
# document re-measures only that layer. Rich text reads styles and variables from the document and is not cached.
PLAIN_ENTRIES = 8192
_PLAIN = OrderedDict()
_LOCK = threading.Lock()  # Production and job workers measure in parallel threads.


def _plain_key(project, layer, data):
    fields = repr(sorted((key, value) for key, value in layer.items() if key not in ("x", "y")))
    return data, fields, project.limits.max_dimension, project.limits.max_pixels


def _placed(x, y, metrics, ink_box, line_box, baselines):
    return {**metrics, "ink_bounds": [x + ink_box[0], y + ink_box[1], *ink_box[2:]],
            "line_bounds": [x + line_box[0], y + line_box[1], *line_box[2:]],
            "baseline": y + baselines[0] if baselines else None,
            "baselines": [y + b for b in baselines], "metrics_space": "unrotated-parent"}


def first_baseline(project, layer):
    """Distance from the top of a text layer's unrotated box to its first line's baseline, in pixels, for the
    resolved ``layer`` (rich text with mixed fonts uses the measured first line)."""
    from .errors import require

    require(layer["type"] == "text", f"{layer['name']!r} is a {layer['type']} layer; baselines belong to text layers "
            "(use a box anchor such as top or bottom)", field="target")
    info = inspect_text(project, layer, (0, 0, layer["width"], layer["height"]))
    require(info.get("baseline") is not None, f"{layer['name']!r} has no measurable baseline (empty text or a font "
            "drawn as raster text)", field="target")
    return info["baseline"]


def resolved_text(project, target):
    """(stored layer, resolved layer, local bounds) of a text layer."""
    from .render import resolve_layout, resolved_layers

    layer = project.layer(target)
    layers = resolved_layers(project)
    resolved = next(item for item in layers if item["id"] == layer["id"])
    return layer, resolved, resolve_layout(project, layers=layers)[layer["id"]]


def place_baseline(project, operation):
    """``baseline_y``: move the text layer so its first baseline sits at that y, in the same space as ``y``."""
    from .errors import require
    from .inplace import IN_PLACE_TYPES
    from .model import finite
    from .render import stored_origin

    value = finite(operation["baseline_y"], "baseline_y", -1e6, 1e6)
    kind = operation.get("type")
    require("y" not in operation, "Give y (the top of the box) or baseline_y (the first baseline), not both",
            field="baseline_y")
    require(not operation.get("relative"), "baseline_y is an absolute position; drop relative", field="baseline_y")
    edits = kind == "move" or kind == "text-set" or kind in IN_PLACE_TYPES
    layer, resolved, bounds = resolved_text(project, operation.get("target") if edits else None)
    require(not layer.get("rotation") % 360 and not layer.get("skew_x") and not layer.get("skew_y"),
            f"{layer['name']!r} is rotated or skewed; baseline_y positions upright text", field="baseline_y")
    offset = first_baseline(project, resolved)
    require(not (layer.get("parent") and (operation.get("space") == "canvas" or operation.get("absolute"))),
            "baseline_y on a grouped layer is in the group's coordinates; drop space: canvas", field="baseline_y")
    _, layer["y"] = stored_origin(layer, (bounds[0], value - offset))
    if isinstance(layer["y"], float) and layer["y"].is_integer():
        layer["y"] = int(layer["y"])
    layer["constraints"] = {key: v for key, v in layer.get("constraints", {}).items()
                            if key not in ("top", "bottom", "center-y")}
