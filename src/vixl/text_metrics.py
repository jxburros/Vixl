"""Inspectable text geometry in unrotated parent coordinates, shared by both text kinds."""

from functools import lru_cache

from .text import face, font_data, glyph_outline, lines, plan, shape


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
        metrics = font_metrics(primary, layer["size"])
        boxes = []
        if active(layer):
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
            from fontTools.svgLib.path import parse_path

            result = plan(project, layer)
            metrics = font_metrics(primary, result.size)
            for path, matrix in result.paths:
                pen = BoundsPen(None)
                parse_path(path, TransformPen(pen, Transform(*matrix)))
                if pen.bounds:
                    boxes.append(pen.bounds)
            wrapped = lines(data, layer["text"], result.size,
                            layer["width"] if "width" in layer.get("text_layout", {}) else None)
            step = metrics["ascent"] + metrics["descent"] + layer.get("spacing", 4)
            baselines = [metrics["ascent"] + index * step - result.box[1] for index in range(len(wrapped))]
            width = max((shape(data, line, result.size)[1] for line in wrapped), default=0)
            line_box = (result.offset - result.box[0], -result.box[1], width,
                        len(wrapped) * step - layer.get("spacing", 4))
        if boxes:
            left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
            ink_box = (left, top, max(b[2] for b in boxes) - left, max(b[3] for b in boxes) - top)
        else:
            ink_box = (0, 0, 0, 0)
        return {**metrics, "ink_bounds": [x + ink_box[0], y + ink_box[1], *ink_box[2:]],
                "line_bounds": [x + line_box[0], y + line_box[1], *line_box[2:]],
                "baseline": y + baselines[0] if baselines else None,
                "baselines": [y + b for b in baselines], "metrics_space": "unrotated-parent"}
    except UnsupportedText:
        return {"metrics_unavailable": "This font requires raster text layout"}
