"""Colour glyphs of font files (COLR v0 and v1, OpenType-SVG, CBDT/CBLC and sbix) as SVG artwork.

A colour glyph is drawn like the artwork of the emoji library: ``text.glyph_outline`` returns a ``ColorGlyph`` (SVG
markup in the font's own units, y up, origin on the baseline) in place of an outline path, and every renderer that
places emoji artwork places it the same way. The palette's foreground colour is ``currentColor``, which the text
renderer sets to the layer's text colour. Glyphs of the same font that have no colour data keep their outline.
"""

import base64
from copy import deepcopy
import io
import math
import re
import xml.etree.ElementTree as ET

from fontTools.misc.transform import Identity
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen

from .emojis import EmojiArt

SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"
TABLES = ("COLR", "SVG ", "CBDT", "sbix")  # In the order a glyph present in several is taken from.
OUTLINES = ("glyf", "CFF ", "CFF2")
BITMAPS = ("CBDT", "sbix")
FOREGROUND = 0xFFFF
FAR = 32768  # Unbounded paints fill this square, in font units; the glyph or clip box around them cuts it.
MAX_DEPTH = 64
MAX_NODES = 20000
MAX_SVG_BYTES = 4 * 1024 * 1024
SWEEP_STEPS = 120
SOLID, LINEAR, RADIAL, SWEEP = (2, 3), (4, 5), (6, 7), (8, 9)
# PaintComposite modes SVG has as blend modes. Of the Porter-Duff modes, src-over, dest-over, src, dest, clear,
# src-in, dest-in, src-atop and dest-atop are drawn exactly; src-out, dest-out, xor and plus as source over backdrop.
BLENDS = {
    "screen": "screen", "overlay": "overlay", "darken": "darken", "lighten": "lighten", "color_dodge": "color-dodge",
    "color_burn": "color-burn", "hard_light": "hard-light", "soft_light": "soft-light", "difference": "difference",
    "exclusion": "exclusion", "multiply": "multiply", "hsl_hue": "hue", "hsl_saturation": "saturation",
    "hsl_color": "color", "hsl_luminosity": "luminosity",
}
REMOVED = frozenset(("script", "foreignObject", "a", "style", "text", "animate", "animateMotion", "animateTransform",
                     "set", "iframe", "audio", "video"))
GLYPH_ID = re.compile(r"glyph(\d+)")
REFERENCE = re.compile(r"url\(\s*#([^)\s]+)\s*\)")


class ColorGlyph(EmojiArt):
    """SVG markup (a ``<g>``) of one colour-font glyph in font units, y up, origin on the baseline.

    ``kind`` is its format ("COLRv0", "COLRv1", "SVG", "CBDT" or "sbix"), ``bounds`` its ink box in font units
    (y up) and ``layers`` the flat-colour outlines of a COLRv0 glyph, ``[(path, rgba or None for the text
    colour)]``, which a PDF draws as vector paths."""

    def __new__(cls, markup, kind, bounds, layers=None):
        self = super().__new__(cls, markup)
        self.kind, self.bounds, self.layers = kind, bounds, layers
        return self

    @property
    def bitmap(self):
        return self.kind in BITMAPS


def has_outlines(outline):
    return any(table in outline for table in OUTLINES)


def formats(outline):
    """The colour tables of a parsed font, as ("COLR", "SVG", "CBDT", "sbix") names."""
    return tuple(table.strip() for table in TABLES if table in outline and (table != "CBDT" or "CBLC" in outline))


def source(outline):
    """The colour-glyph reader of a parsed font, or None for a font without colour tables. It is kept on the
    font object, which ``text.face`` holds per thread."""
    found = outline.__dict__.get("_vixl_color", False)
    if found is False:
        found = outline.__dict__["_vixl_color"] = Source(outline) if formats(outline) else None
    return found


def strikes(outline):
    """The sizes (pixels per em) of a font's bitmap strikes, ascending; empty without bitmap glyphs."""
    reader = source(outline)
    return reader.ppems if reader else ()


def strike_for(ppems, size):
    """The strike to draw ``size`` pixels from: the smallest one at least that large, else the largest."""
    if not ppems:
        return None
    if size is None:
        return ppems[-1]
    return next((ppem for ppem in ppems if ppem >= size), ppems[-1])


def glyph(outline, name, strike=None):
    """The ``ColorGlyph`` of glyph ``name``, or None when the font has no colour data for it. ``strike`` picks
    the bitmap strike (see ``strike_for``)."""
    reader = source(outline)
    if reader is None:
        return None
    try:
        return reader.glyph(name, strike)
    except Exception:  # noqa: BLE001 - damaged colour data: the glyph keeps its outline
        return None


def _number(value):
    return f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def _enum(value):
    """The lower-case name of a fontTools enum value (``ExtendMode.PAD`` gives ``pad``)."""
    return str(getattr(value, "name", value)).rsplit(".", 1)[-1].lower()


def _matrix(t):
    return "matrix(" + " ".join(_number(float(v)) for v in t) + ")"


def _union(boxes):
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _transformed(box, transform):
    points = [transform.transformPoint(p) for p in ((box[0], box[1]), (box[0], box[3]), (box[2], box[1]), (box[2], box[3]))]
    return (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))


class Source:
    def __init__(self, outline):
        self.font = outline
        self.tables = formats(outline)
        self.upem = outline["head"].unitsPerEm
        self.glyphs = outline.getGlyphSet() if has_outlines(outline) else None
        self._paths = {}
        self.palette = self._palette()
        self.v0, self.v1, self.clips = self._colr() if "COLR" in self.tables else ({}, {}, {})
        self.documents = self._documents() if "SVG" in self.tables else {}
        self._parsed = {}
        self.bitmaps = self._strikes()  # {ppem: reader(name) -> (image bytes, left, bottom, width, height) or None}
        self.ppems = tuple(sorted(self.bitmaps))

    # Shared pieces.

    def _palette(self):
        if "CPAL" not in self.font or not self.font["CPAL"].palettes:
            return []
        return [(c.red, c.green, c.blue, c.alpha) for c in self.font["CPAL"].palettes[0]]

    def path(self, name):
        """``(SVG path, bounds)`` of the outline of glyph ``name``; ``("", None)`` when it has none."""
        if name not in self._paths:
            found = ("", None)
            if self.glyphs is not None and name in self.glyphs:
                pen, bounds = SVGPathPen(self.glyphs), BoundsPen(self.glyphs)
                self.glyphs[name].draw(pen)
                self.glyphs[name].draw(bounds)
                found = (pen.getCommands(), bounds.bounds)
            self._paths[name] = found
        return self._paths[name]

    def color(self, index, alpha=1.0):
        """``(rgba or None for the text colour, CSS colour, opacity)`` of a palette entry."""
        if index == FOREGROUND or index >= len(self.palette):
            return None, "currentColor", max(0.0, min(1.0, alpha))
        r, g, b, a = self.palette[index]
        opacity = max(0.0, min(1.0, a / 255 * alpha))
        return (r, g, b, round(opacity * 255)), f"rgb({r},{g},{b})", opacity

    def glyph(self, name, strike=None):
        for table in self.tables:
            if table == "COLR":
                found = self._colr_v1(name) if name in self.v1 else self._colr_v0(name) if name in self.v0 else None
            elif table == "SVG":
                found = self._svg(name)
            else:
                found = self._bitmap(name, strike, table)
            if found is not None:
                return found
        return None

    def _art(self, root, kind, bounds, layers=None):
        if bounds is None or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            return None
        return ColorGlyph(ET.tostring(root, encoding="unicode"), kind, tuple(float(v) for v in bounds), layers)

    # COLR.

    def _colr(self):
        colr = self.font["COLR"]
        v0, v1, clips = {}, {}, {}
        if hasattr(colr, "ColorLayers"):
            for name, layers in colr.ColorLayers.items():
                v0[name] = [(layer.name, layer.colorID) for layer in layers]
            return v0, v1, clips
        table = colr.table
        records = getattr(getattr(table, "BaseGlyphRecordArray", None), "BaseGlyphRecord", None) or []
        layers = getattr(getattr(table, "LayerRecordArray", None), "LayerRecord", None) or []
        for record in records:
            chosen = layers[record.FirstLayerIndex : record.FirstLayerIndex + record.NumLayers]
            v0[record.BaseGlyph] = [(layer.LayerGlyph, layer.PaletteIndex) for layer in chosen]
        for record in getattr(getattr(table, "BaseGlyphList", None), "BaseGlyphPaintRecord", None) or []:
            v1[record.BaseGlyph] = record.Paint
        for name, box in (getattr(getattr(table, "ClipList", None), "clips", None) or {}).items():
            clips[name] = (box.xMin, box.yMin, box.xMax, box.yMax)
        return v0, v1, clips

    def _colr_v0(self, name):
        root = ET.Element(SVG + "g")
        layers, boxes = [], []
        for layer, index in self.v0[name]:
            path, bounds = self.path(layer)
            if not path:
                continue
            rgba, css, opacity = self.color(index)
            attrs = {"d": path, "fill": css}
            if opacity < 1:
                attrs["fill-opacity"] = _number(opacity)
            ET.SubElement(root, SVG + "path", attrs)
            layers.append((path, rgba))
            boxes.append(bounds)
        return self._art(root, "COLRv0", _union(boxes), layers) if layers else None

    def _colr_v1(self, name):
        painter = Painter(self)
        root = ET.Element(SVG + "g")
        body = painter.base(name, Identity, 0)
        if body is None:
            return None
        if len(painter.defs):
            root.append(painter.defs)
        root.append(body)
        return self._art(root, "COLRv1", self.clips.get(name) or _union(painter.boxes))

    # OpenType-SVG.

    def _documents(self):
        ranges = {}
        for index, document in enumerate(self.font["SVG "].docList):
            for gid in range(document.startGlyphID, document.endGlyphID + 1):
                ranges[gid] = index
        return ranges

    def _document(self, index):
        if index not in self._parsed:
            if len(self._parsed) >= 8:
                self._parsed.clear()
            data = self.font["SVG "].docList[index].data
            raw = data.encode() if isinstance(data, str) else data
            root = None
            if len(raw) <= MAX_SVG_BYTES and b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper():
                root = ET.fromstring(raw)
                root = root if root.tag == SVG + "svg" and sum(1 for _ in root.iter()) <= MAX_NODES else None
            self._parsed[index] = root
        return self._parsed[index]

    def _svg(self, name):
        gid = self.font.getGlyphID(name)
        if gid not in self.documents:
            return None
        document = self._document(self.documents[gid])
        if document is None:
            return None
        ident = f"glyph{gid}"
        by_id = {node.get("id"): node for node in document.iter() if node.get("id")}
        if ident not in by_id:
            return None
        # The other glyphs of the document are left out, except the ones this glyph refers to, which become
        # definitions: a document may hold every glyph of the font.
        needed, queue = {ident}, [by_id[ident]]
        while queue:
            for node in queue.pop().iter():
                for key, value in node.attrib.items():
                    found = REFERENCE.findall(value)
                    if key.rsplit("}", 1)[-1] == "href" and value.startswith("#"):
                        found.append(value[1:])
                    for other in found:
                        if other in by_id and other not in needed:
                            needed.add(other)
                            queue.append(by_id[other])
        body = ET.Element(SVG + "g", {k: v for k, v in document.attrib.items()
                                      if k.rsplit("}", 1)[-1] not in ("width", "height", "viewBox", "x", "y", "version",
                                                                      "id", "preserveAspectRatio", "baseProfile")})
        held = ET.Element(SVG + "defs")
        for child in document:
            other = child.get("id") or ""
            if GLYPH_ID.fullmatch(other) and other != ident:
                if other in needed:
                    held.append(deepcopy(child))
                continue
            body.append(deepcopy(child))
        if len(held):
            body.insert(0, held)
        _inert(body)
        root = ET.Element(SVG + "g")
        ET.SubElement(root, SVG + "g", {"transform": "scale(1 -1)"}).append(body)  # SVG glyphs are drawn y down.
        bounds = self.path(name)[1]
        if bounds is None:
            # No outline to measure: the glyph's em box, which is what an SVG glyph is designed in.
            hhea = self.font["hhea"]
            bounds = (0, hhea.descent, self.font["hmtx"][name][0] or self.upem, hhea.ascent)
        return self._art(root, "SVG", bounds)

    # Bitmap strikes.

    def _strikes(self):
        found = {}
        if "sbix" in self.tables:
            for ppem, strike in self.font["sbix"].strikes.items():
                if ppem > 0:
                    found[ppem] = ("sbix", strike)
        if "CBDT" in self.tables:
            for strike, data in zip(self.font["CBLC"].strikes, self.font["CBDT"].strikeData):
                size = strike.bitmapSizeTable
                if size.ppemX > 0 and size.ppemY > 0:
                    found.setdefault(size.ppemY, ("CBDT", (strike, data)))
        return found

    def _bitmap(self, name, ppem, table):
        chosen = [p for p in self.ppems if self.bitmaps[p][0] == table]
        ppem = ppem if ppem in chosen else strike_for(chosen, None)
        # A glyph missing from the chosen strike is taken from the nearest larger one, then the nearest smaller.
        order = [p for p in chosen if p >= ppem] + [p for p in reversed(chosen) if p < ppem] if chosen else []
        for candidate in order:
            _, strike = self.bitmaps[candidate]
            found = self._sbix(strike, name) if table == "sbix" else self._cbdt(strike, name)
            if found is not None:
                image, left, bottom, width, height = found
                uri = _data_uri(image)
                if uri is None:
                    continue
                root = ET.Element(SVG + "g")
                flipped = ET.SubElement(root, SVG + "g", {"transform": "scale(1 -1)"})
                ET.SubElement(flipped, SVG + "image", {
                    "x": _number(float(left)), "y": _number(float(-(bottom + height))), "width": _number(float(width)),
                    "height": _number(float(height)), "preserveAspectRatio": "none", "href": uri})
                return self._art(root, table, (left, bottom, left + width, bottom + height))
        return None

    def _sbix(self, strike, name, depth=0):
        record = strike.glyphs.get(name)
        if record is None or not record.imageData or depth > 4:
            return None
        if record.graphicType == "dupe":
            target = self.font.getGlyphName(int.from_bytes(record.imageData[:2], "big"))
            return self._sbix(strike, target, depth + 1)
        size = _image_size(record.imageData)
        if size is None:
            return None
        scale = self.upem / strike.ppem
        return (record.imageData, record.originOffsetX * scale, record.originOffsetY * scale, size[0] * scale,
                size[1] * scale)

    def _cbdt(self, strike, name):
        table, data = strike
        record = data.get(name)
        if record is None:
            return None
        metrics = getattr(record, "metrics", None)
        if metrics is None:  # Format 19: one set of metrics for the whole index subtable.
            holder = next((sub for sub in table.indexSubTables if name in sub.names), None)
            metrics = getattr(holder, "metrics", None)
        image = getattr(record, "imageData", None)
        if metrics is None or not image or _image_size(image) is None:
            return None
        sx, sy = self.upem / table.bitmapSizeTable.ppemX, self.upem / table.bitmapSizeTable.ppemY
        left = getattr(metrics, "BearingX", None)
        top = getattr(metrics, "BearingY", None)
        if left is None:
            left, top = metrics.horiBearingX, metrics.horiBearingY
        return image, left * sx, (top - metrics.height) * sy, metrics.width * sx, metrics.height * sy


def _image_size(data):
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.size if 0 < image.size[0] <= 4096 and 0 < image.size[1] <= 4096 else None
    except Exception:  # noqa: BLE001 - not an image this strike can be drawn from
        return None


def _data_uri(data):
    """A PNG or JPEG data URI of a strike's image; other formats (TIFF) are converted to PNG."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif data.startswith(b"\xff\xd8"):
        kind = "jpeg"
    else:
        from PIL import Image

        try:
            with Image.open(io.BytesIO(data)) as image:
                buffer = io.BytesIO()
                image.convert("RGBA").save(buffer, format="PNG")
        except Exception:  # noqa: BLE001
            return None
        data, kind = buffer.getvalue(), "png"
    return f"data:image/{kind};base64," + base64.b64encode(data).decode()


def _inert(root):
    """Remove what must not run or load from an SVG glyph: scripts, links, styles, animation, event handlers and
    references outside the document."""
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
            if not tag or tag in REMOVED:
                parent.remove(child)
    for node in root.iter():
        for key, value in list(node.attrib.items()):
            attr = key.rsplit("}", 1)[-1]
            external = attr in ("href", "src") and not value.startswith(("#", "data:image/png;base64,",
                                                                         "data:image/jpeg;base64,"))
            outside = any(not ref.strip().startswith("#") for ref in re.findall(r"url\(([^)]*)\)", value))
            if attr.lower().startswith("on") or external or outside or attr == "style" and "url(" in value:
                del node.attrib[key]


class Painter:
    """Draws a COLRv1 paint graph as SVG elements in font units, y up."""

    def __init__(self, reader):
        self.reader = reader
        self.colr = reader.font["COLR"].table
        self.defs = ET.Element(SVG + "defs")
        self.boxes = []
        self.count = 0
        self.nodes = 0

    def ident(self, prefix):
        self.count += 1
        return f"{prefix}{self.count}"

    def base(self, name, transform, depth):
        paint = self.reader.v1.get(name)
        if paint is None:
            return None
        body = self.paint(paint, transform, depth)
        clip = self.reader.clips.get(name)
        if body is None or clip is None:
            return body
        ident = self.ident("b")
        holder = ET.SubElement(self.defs, SVG + "clipPath", {"id": ident})
        ET.SubElement(holder, SVG + "rect", {"x": _number(clip[0]), "y": _number(clip[1]),
                                             "width": _number(clip[2] - clip[0]), "height": _number(clip[3] - clip[1])})
        group = ET.Element(SVG + "g", {"clip-path": f"url(#{ident})"})
        group.append(body)
        return group

    def paint(self, paint, transform, depth):
        """The element drawing ``paint``, or None for nothing. ``transform`` (font units to the glyph's frame)
        is only used to measure the glyph."""
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            return None
        kind = int(paint.Format)
        if kind == 1:
            group = ET.Element(SVG + "g")
            for child in paint.getChildren(self.colr):
                drawn = self.paint(child, transform, depth + 1)
                if drawn is not None:
                    group.append(drawn)
            return group if len(group) else None
        if kind in SOLID + LINEAR + RADIAL + SWEEP:
            # A paint with no glyph around it fills everything; whatever encloses it cuts it to shape.
            return self.fill(paint, {"x": str(-FAR), "y": str(-FAR), "width": str(2 * FAR), "height": str(2 * FAR)}, "rect")
        if kind == 10:
            path, bounds = self.reader.path(paint.Glyph)
            if not path:
                return None
            if bounds:
                self.boxes.append(_transformed(bounds, transform))
            child = paint.Paint
            if int(child.Format) in SOLID + LINEAR + RADIAL:
                return self.fill(child, {"d": path}, "path")
            drawn = self.paint(child, transform, depth + 1)
            if drawn is None:
                return None
            ident = self.ident("c")
            ET.SubElement(ET.SubElement(self.defs, SVG + "clipPath", {"id": ident}), SVG + "path", {"d": path})
            group = ET.Element(SVG + "g", {"clip-path": f"url(#{ident})"})
            group.append(drawn)
            return group
        if kind == 11:
            return self.base(paint.Glyph, transform, depth + 1)
        if 12 <= kind <= 31:
            change = paint.getTransform()
            drawn = self.paint(paint.Paint, transform.transform(change), depth + 1)
            if drawn is None:
                return None
            group = ET.Element(SVG + "g", {"transform": _matrix(change)})
            group.append(drawn)
            return group
        if kind == 32:
            return self.composite(paint, transform, depth)
        return None

    def composite(self, paint, transform, depth):
        mode = _enum(paint.CompositeMode)
        backdrop = None if mode in ("clear", "src") else self.paint(paint.BackdropPaint, transform, depth + 1)
        over = None if mode in ("clear", "dest") else self.paint(paint.SourcePaint, transform, depth + 1)
        group = ET.Element(SVG + "g")

        def masked(content, by):
            ident = self.ident("m")
            holder = ET.SubElement(self.defs, SVG + "mask", {
                "id": ident, "mask-type": "alpha", "maskUnits": "userSpaceOnUse", "x": str(-FAR), "y": str(-FAR),
                "width": str(2 * FAR), "height": str(2 * FAR)})
            holder.append(deepcopy(by))
            wrapper = ET.Element(SVG + "g", {"mask": f"url(#{ident})"})
            wrapper.append(content)
            return wrapper

        if mode in ("src_in", "src_atop", "dest_in", "dest_atop"):
            if backdrop is None or over is None:
                # Nothing to cut by: only the uncut side of an atop mode is left.
                kept = backdrop if mode == "src_atop" else over if mode == "dest_atop" else None
                return kept
            if mode == "src_in":
                return masked(over, backdrop)
            if mode == "dest_in":
                return masked(backdrop, over)
            if mode == "src_atop":
                group.append(backdrop)
                group.append(masked(over, backdrop))
            else:
                group.append(over)
                group.append(masked(backdrop, over))
            return group
        if mode == "dest_over":
            backdrop, over = over, backdrop
        if backdrop is not None:
            group.append(backdrop)
        if over is not None:
            if mode in BLENDS and backdrop is not None:
                group.set("style", "isolation:isolate")
                wrapper = ET.SubElement(group, SVG + "g", {"style": f"mix-blend-mode:{BLENDS[mode]}"})
                wrapper.append(over)
            else:
                group.append(over)
        return group if len(group) else None

    def fill(self, paint, attrs, tag):
        kind = int(paint.Format)
        if kind in SOLID:
            _, css, opacity = self.reader.color(paint.PaletteIndex, paint.Alpha)
            attrs["fill"] = css
            if opacity < 1:
                attrs["fill-opacity"] = _number(opacity)
            return ET.Element(SVG + tag, attrs)
        if kind in SWEEP:
            return self.sweep(paint)
        stops = sorted(((stop.StopOffset, stop.PaletteIndex, stop.Alpha) for stop in paint.ColorLine.ColorStop),
                       key=lambda stop: stop[0])
        if not stops:
            return None
        low, high = stops[0][0], stops[-1][0]
        if high <= low:
            _, css, opacity = self.reader.color(stops[-1][1], stops[-1][2])
            attrs.update({"fill": css, "fill-opacity": _number(opacity)})
            return ET.Element(SVG + tag, attrs)
        ident = self.ident("g")
        spread = {"repeat": "repeat", "reflect": "reflect"}.get(_enum(paint.ColorLine.Extend), "pad")
        if kind in LINEAR:
            x0, y0, x1, y1, x2, y2 = paint.x0, paint.y0, paint.x1, paint.y1, paint.x2, paint.y2
            # The gradient runs along the normal of the line from p0 to p2: p1 is projected onto it.
            nx, ny = y2 - y0, x0 - x2
            length = nx * nx + ny * ny
            if length:
                k = ((x1 - x0) * nx + (y1 - y0) * ny) / length
                x1, y1 = x0 + k * nx, y0 + k * ny
            dx, dy = x1 - x0, y1 - y0
            # Stops outside 0-1 are legal in COLR and not in SVG: the end points move to the first and last stop.
            gradient = ET.SubElement(self.defs, SVG + "linearGradient", {
                "id": ident, "gradientUnits": "userSpaceOnUse", "spreadMethod": spread,
                "x1": _number(float(x0 + dx * low)), "y1": _number(float(y0 + dy * low)),
                "x2": _number(float(x0 + dx * high)), "y2": _number(float(y0 + dy * high))})
        else:
            x0, y0, r0, x1, y1, r1 = paint.x0, paint.y0, paint.r0, paint.x1, paint.y1, paint.r1
            at = lambda a, b, t: a + (b - a) * t  # noqa: E731
            gradient = ET.SubElement(self.defs, SVG + "radialGradient", {
                "id": ident, "gradientUnits": "userSpaceOnUse", "spreadMethod": spread,
                "fx": _number(float(at(x0, x1, low))), "fy": _number(float(at(y0, y1, low))),
                "fr": _number(float(max(0.0, at(r0, r1, low)))),
                "cx": _number(float(at(x0, x1, high))), "cy": _number(float(at(y0, y1, high))),
                "r": _number(float(max(0.0, at(r0, r1, high))))})
        for offset, index, alpha in stops:
            _, css, opacity = self.reader.color(index, alpha)
            ET.SubElement(gradient, SVG + "stop", {"offset": _number(float((offset - low) / (high - low))),
                                                   "stop-color": css, "stop-opacity": _number(opacity)})
        attrs["fill"] = f"url(#{ident})"
        return ET.Element(SVG + tag, attrs)

    def sweep(self, paint):
        """A sweep (conic) gradient, which SVG lacks, as ``SWEEP_STEPS`` flat wedges around its centre."""
        stops = sorted(((stop.StopOffset, *self.reader.color(stop.PaletteIndex, stop.Alpha)[1:])
                        for stop in paint.ColorLine.ColorStop), key=lambda stop: stop[0])
        if not stops:
            return None
        extend = _enum(paint.ColorLine.Extend)
        start, end = paint.startAngle % 360, paint.endAngle % 360
        if end <= start:
            end += 360
        low, high = stops[0][0], stops[-1][0]

        def at(t):
            if high > low and extend == "repeat":
                t = low + (t - low) % (high - low)
            elif high > low and extend == "reflect":
                t = (t - low) % (2 * (high - low))
                t = low + (t if t <= high - low else 2 * (high - low) - t)
            if t <= low:
                return stops[0][1:]
            if t >= high:
                return stops[-1][1:]
            for (a, css_a, alpha_a), (b, css_b, alpha_b) in zip(stops, stops[1:]):
                if a <= t <= b:
                    k = (t - a) / (b - a) if b > a else 1.0
                    if css_a == "currentColor" or css_b == "currentColor":
                        return (css_a, alpha_a) if k < 0.5 else (css_b, alpha_b)
                    ca, cb = (tuple(map(int, css[4:-1].split(","))) for css in (css_a, css_b))
                    mixed = tuple(round(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
                    return f"rgb({mixed[0]},{mixed[1]},{mixed[2]})", alpha_a + (alpha_b - alpha_a) * k
            return stops[-1][1:]

        group = ET.Element(SVG + "g")
        cx, cy, step, reach = paint.centerX, paint.centerY, 360 / SWEEP_STEPS, 8 * self.reader.upem
        for i in range(SWEEP_STEPS):
            a0, a1 = start + i * step, start + (i + 1) * step
            css, opacity = at(((a0 + a1) / 2 - start) / (end - start))
            if opacity >= 1 and i + 1 < SWEEP_STEPS:
                a1 += step / 2  # Opaque wedges reach under the next one, which hides the seams between them.
            points = [(cx + reach * math.cos(math.radians(a)), cy + reach * math.sin(math.radians(a))) for a in (a0, a1)]
            attrs = {"d": f"M{_number(float(cx))},{_number(float(cy))} L{points[0][0]:.1f},{points[0][1]:.1f} "
                          f"L{points[1][0]:.1f},{points[1][1]:.1f} Z", "fill": css}
            if opacity < 1:
                attrs["fill-opacity"] = _number(opacity)
            ET.SubElement(group, SVG + "path", attrs)
        return group


def layer_kinds(project, layer):
    """The colour-font formats a text layer's glyphs are drawn from ("COLRv0", "COLRv1", "SVG", "CBDT",
    "sbix"), in first-drawn order; empty for ordinary outline text."""
    from .richtext import active
    from .text import glyph_outline, plan

    if active(layer):
        from .richtext import fitted

        arts = (glyph_outline(g.data, g.name, g.size)[0] for g in fitted(project, layer).glyphs)
    else:
        from .emojis import is_context, is_glyph
        from .text import face, font_data

        data = font_data(project, layer)
        fonts = [f for f in (data if isinstance(data, tuple) else (data,)) if not is_context(f) and not is_glyph(f)]
        if all(source(face(f)[0]) is None for f in fonts):
            return []
        arts = (path for path, _ in plan(project, layer).paths)
    return list(dict.fromkeys(art.kind for art in arts if isinstance(art, ColorGlyph)))
