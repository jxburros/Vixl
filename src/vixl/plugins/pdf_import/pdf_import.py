"""PDF page import: editable layers (live text, vector paths, images), or one image of the page.

The editable import reads the page's objects through pdfium (``pypdfium2``, the ``pdf`` extra):

* text objects become text layers with their text, size, colour, position and rotation; consecutive lines of one
  style that share a left edge, centre or right edge become one multi-line layer. A font the document has registered
  under the PDF font's family name (or a bundled face) is used, else the default face, with a warning.
* path objects become path shape layers with their fill (nonzero or even-odd), stroke, width, caps, joins and dashes;
  a stroke drawn right after a fill of the same path joins that layer.
* image objects become image layers at their place, size and rotation.
* what Vixl cannot represent (shadings, clipped objects, patterns, mirrored text, Type 3 text …) is drawn, run by run
  in stacking order, as image layers of just those objects.

A page Vixl exported maps back to the pixels it was made at (the PDF records ``VixlDPI``); other PDFs map one point to
one pixel. Into an empty document the import takes the page size as the canvas and a full-page backdrop as the
background. ``mode='appearance'`` imports the page as one image at ``dpi`` instead."""

import ctypes
import math

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen

from ...errors import VixlError, require

TEXT, PATH, IMAGE, SHADING, FORM = 1, 2, 3, 4, 5
LINETO, BEZIERTO, MOVETO = 0, 1, 2
FILL_NONE, FILL_EVENODD, FILL_NONZERO = 0, 1, 2
MAX_OBJECTS = 20000
MAX_RUNS = 64


def _pdfium():
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[pdf] for PDF import") from exc
    return pdfium, raw


def import_pdf(project, data, *, name="import", page=1, dpi=None, mode="editable"):
    """``mode``: ``editable`` (the default) or ``auto`` read the page as layers; ``appearance`` renders it as one image
    at ``dpi`` (default 144). ``dpi`` applies to the image import only: vector content keeps its own scale."""
    require(isinstance(page, int) and page >= 1, "PDF page must be positive", field="page")
    require(dpi is None or (isinstance(dpi, (int, float)) and 36 <= dpi <= 600), "dpi must be 36–600", field="dpi")
    if mode == "appearance":
        return raster_page(project, data, name=name, page=page, dpi=dpi or 144)
    return PageReader(project, data, name, page).run()


def raster_page(project, data, *, name, page, dpi, warnings=()):
    """The page rendered at ``dpi`` as one image layer."""
    pdfium, _ = _pdfium()
    candidate = project.clone()
    try:
        with pdfium.PdfDocument(data) as document:
            require(page <= len(document), "PDF page is out of range", field="page")
            source = document[page - 1]
            try:
                w, h = source.get_size()
                candidate.limits.size(math.ceil(w * dpi / 72), math.ceil(h * dpi / 72))
                bitmap = source.render(scale=dpi / 72)
                try:
                    from ...assets import add_image

                    asset = add_image(candidate, bitmap.to_pil())
                finally:
                    bitmap.close()
            finally:
                source.close()
    except pdfium.PdfiumError as exc:
        raise VixlError("invalid_pdf", f"Cannot open PDF: {exc}") from exc
    result = candidate.apply({"type": "add", "asset": asset, "name": name}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {**result, "page": page, "dpi": dpi, "mode": "appearance",
            "warnings": [*warnings, "PDF page imported as one image layer (svg_mode='appearance')."]}


def _matrix(raw, obj):
    m = raw.FS_MATRIX()
    if not raw.FPDFPageObj_GetMatrix(obj, m):
        return Transform()
    return Transform(m.a, m.b, m.c, m.d, m.e, m.f)


def _bounds(raw, obj):
    values = [ctypes.c_float() for _ in range(4)]
    if not raw.FPDFPageObj_GetBounds(obj, *values):
        return None
    return tuple(v.value for v in values)


def _color(raw, getter, obj):
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if not getter(obj, r, g, b, a):
        return None
    return r.value, g.value, b.value, a.value


def _hex(rgba):
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")


def _string(raw, function, *args, utf16=False):
    size = function(*args, None, 0)
    if size <= (2 if utf16 else 1):
        return ""
    buffer = ctypes.create_string_buffer(size)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort) if utf16 else ctypes.c_char_p)
    function(*args, pointer, size)
    data = buffer.raw[:size]
    return data.decode("utf-16-le", "replace").rstrip("\x00") if utf16 else data.rstrip(b"\x00").decode("utf-8",
                                                                                                         "replace")


def _segments(raw, obj, count_function, segment_function, *path_index):
    count = count_function(obj, *path_index)
    points = []
    for index in range(max(0, count)):
        segment = segment_function(obj, *path_index, index)
        x, y = ctypes.c_float(), ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(segment, x, y)
        points.append((raw.FPDFPathSegment_GetType(segment), (x.value, y.value),
                       bool(raw.FPDFPathSegment_GetClose(segment))))
    return points


def _pen(points, matrix):
    """Recording-pen commands of pdfium path segments, transformed by ``matrix``."""
    pen = RecordingPen()
    curve, open_contour = [], False
    for kind, point, close in points:
        point = matrix.transformPoint(point)
        if kind == MOVETO:
            if open_contour:
                pen.endPath()
            pen.moveTo(point)
            open_contour = True
        elif kind == LINETO:
            pen.lineTo(point)
        elif kind == BEZIERTO:
            curve.append(point)
            if len(curve) == 3:
                pen.curveTo(*curve)
                curve = []
        else:
            raise VixlError("unsupported_pdf", "Unknown PDF path segment")
        if close and open_contour:
            pen.closePath()
            open_contour = False
    if open_contour:
        pen.endPath()
    return pen


class Fallback(Exception):
    """An object Vixl cannot represent as an editable layer."""


class PageReader:
    def __init__(self, project, data, name, page):
        self.project, self.data, self.name, self.page_number = project, data, name, page
        self.candidate = project.clone()
        self.operations, self.warnings, self.rasterized, self.anchored = [], [], [], []
        self.used = {layer["name"] for layer in project.state["layers"]} | {layer["id"] for layer in
                                                                             project.state["layers"]}
        self.adopt = not project.state["layers"] and not project.state.get("pages")
        self.pending = []  # top-level object indices waiting to be drawn as one image (a run)
        self.counts = {"text": 0, "path": 0, "image": 0}
        self.sequence = 0
        self.previous_path = None

    def unique(self, base):
        candidate, index = base, 2
        while candidate in self.used:
            candidate = f"{base}-{index}"
            index += 1
        self.used.add(candidate)
        return candidate

    # --- reading ---------------------------------------------------------------------------------------------------

    def run(self):
        pdfium, raw = _pdfium()
        self.raw = raw
        try:
            with pdfium.PdfDocument(self.data) as document:
                require(self.page_number <= len(document), "PDF page is out of range", field="page")
                page = document[self.page_number - 1]
                try:
                    if page.get_rotation() % 360:
                        return raster_page(self.project, self.data, name=self.name, page=self.page_number, dpi=144,
                                           warnings=["Rotated PDF pages import as one image"])
                    self.read(document, page)
                finally:
                    page.close()
        except pdfium.PdfiumError as exc:
            raise VixlError("invalid_pdf", f"Cannot open PDF: {exc}") from exc
        from ...svg_import import anchor_text

        require(any(op["type"] != "canvas" for op in self.operations) or self.background, "The PDF page draws nothing",
                field="page")
        operations = anchor_text(self.candidate, self.operations, self.anchored)
        require(len(operations) <= self.project.limits.max_operations, "PDF page has too many objects",
                "resource_limit")
        result = self.candidate.apply(operations, detail="compact") if operations else {"success": True}
        self.project.__dict__.update(self.candidate.__dict__)
        result.update(page=self.page_number, mode="editable", scale=round(self.k, 6),
                      layers={key: value for key, value in self.counts.items() if value})
        if self.rasterized:
            result["rasterized"] = self.rasterized
            self.warnings.append(f"{len(self.rasterized)} group(s) of PDF objects Vixl cannot edit (shadings, clipped "
                                 "or patterned content) were imported as image layers")
        warnings = list(dict.fromkeys(self.warnings))
        if warnings:
            result["warnings"] = [*warnings, *result.get("warnings", [])]
        return result

    def read(self, document, page):
        raw = self.raw
        self.document_raw, self.page_raw = document.raw, page.raw
        recorded = _string(raw, raw.FPDF_GetMetaText, document.raw, b"VixlDPI", utf16=True)
        try:
            dpi = float(recorded) if recorded else 72.0
        except ValueError:
            dpi = 72.0
        self.k = (dpi if 36 <= dpi <= 2400 else 72.0) / 72
        left, bottom, right, top = page.get_cropbox()
        self.to_pixels = Transform(self.k, 0, 0, -self.k, -left * self.k, top * self.k)
        width, height = round((right - left) * self.k), round((top - bottom) * self.k)
        self.size = (width, height)
        self.background = None
        self.textpage = page.get_textpage()
        try:
            count = raw.FPDFPage_CountObjects(page.raw)
            require(count <= MAX_OBJECTS, "PDF page has too many objects", "resource_limit")
            objects = [raw.FPDFPage_GetObject(page.raw, i) for i in range(count)]
            start = 0
            if self.adopt:
                self.candidate.limits.size(width, height)
                start = self.backdrop(objects)
                # A PDF page is paper: white unless the page paints a backdrop of its own.
                canvas = {"type": "canvas", "width": width, "height": height,
                          "background": self.background or "#ffffff"}
                self.operations.append(canvas)
            for index in range(start, count):
                # Read into a buffer: an object that falls back leaves nothing behind, and a pending run of
                # fallback objects is drawn before the next readable object, keeping the stacking order.
                main, self.operations = self.operations, []
                lines = len(self.lines)
                self.sequence += 1
                try:
                    self.read_object(objects[index], self.to_pixels, index)
                except Fallback as exc:
                    del self.lines[lines:]
                    self.pending.append((index, str(exc)))
                    self.previous_path = None
                    self.operations = main
                    continue
                buffered, self.operations = self.operations, main
                self.flush()
                self.operations.extend(buffered)
            self.flush()
            self.merge_lines()
        finally:
            self.textpage.close()

    def backdrop(self, objects):
        """How many leading objects are full-page opaque fills (Vixl's canvas background); the last one's colour
        becomes the canvas background."""
        raw = self.raw
        width, height = self.size
        skipped = 0
        for obj in objects[:2]:
            if raw.FPDFPageObj_GetType(obj) != PATH:
                break
            box = self.pixel_box(obj, self.to_pixels)
            fill = _color(raw, raw.FPDFPageObj_GetFillColor, obj)
            mode, stroke = ctypes.c_int(), ctypes.c_int()
            raw.FPDFPath_GetDrawMode(obj, mode, stroke)
            if (box is None or fill is None or fill[3] != 255 or mode.value == FILL_NONE or stroke.value
                    or raw.FPDFPath_CountSegments(obj) > 6
                    or not (box[0] <= 0.5 and box[1] <= 0.5 and box[2] >= width - 0.5 and box[3] >= height - 0.5)):
                break
            self.background = _hex(fill)
            skipped += 1
        return skipped

    def pixel_box(self, obj, matrix):
        bounds = _bounds(self.raw, obj)
        if bounds is None:
            return None
        x0, y0, x1, y1 = bounds
        xs, ys = zip(*(matrix.transformPoint(p) for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))))
        return min(xs), min(ys), max(xs), max(ys)

    def clipped(self, obj, matrix):
        """True when the object has a clip path that cuts into it."""
        raw = self.raw
        clip = raw.FPDFPageObj_GetClipPath(obj)
        if not clip:
            return False
        box = self.pixel_box(obj, matrix)
        for index in range(raw.FPDFClipPath_CountPaths(clip)):
            points = _segments(raw, clip, raw.FPDFClipPath_CountPathSegments, raw.FPDFClipPath_GetPathSegment, index)
            if not points:
                continue
            bounds = BoundsPen(None)
            _pen(points, self.to_pixels).replay(bounds)
            if bounds.bounds is None:
                return True
            x0, y0, x1, y1 = bounds.bounds
            if box and (box[0] < x0 - 0.75 or box[1] < y0 - 0.75 or box[2] > x1 + 0.75 or box[3] > y1 + 0.75):
                return True
        return False

    def read_object(self, obj, matrix, index):
        raw = self.raw
        kind = raw.FPDFPageObj_GetType(obj)
        if kind == FORM:
            inner = matrix.transform(_matrix(raw, obj))
            count = raw.FPDFFormObj_CountObjects(obj)
            require(count <= MAX_OBJECTS, "PDF form has too many objects", "resource_limit")
            children = [raw.FPDFFormObj_GetObject(obj, i) for i in range(count)]
            if any(raw.FPDFPageObj_GetType(child) in (SHADING,) for child in children) or self.clipped(obj, matrix):
                raise Fallback("form content")
            for child in children:
                self.read_object(child, inner, index)
            return
        if kind not in (TEXT, PATH, IMAGE):
            raise Fallback("shading" if kind == SHADING else "unsupported object")
        if self.clipped(obj, matrix):
            raise Fallback("clipped")
        if kind == PATH:
            self.path(obj, matrix)
        elif kind == TEXT:
            self.previous_path = None
            self.text(obj, matrix)
        else:
            self.previous_path = None
            self.image(obj, matrix)

    # --- paths -----------------------------------------------------------------------------------------------------

    def path(self, obj, matrix):
        from ...svg_import import _similarity, evenodd_to_nonzero, path_commands

        raw = self.raw
        mode, stroke_flag = ctypes.c_int(), ctypes.c_int()
        raw.FPDFPath_GetDrawMode(obj, mode, stroke_flag)
        total = matrix.transform(_matrix(raw, obj))
        points = _segments(raw, obj, raw.FPDFPath_CountSegments, raw.FPDFPath_GetPathSegment)
        require(len(points) <= 100000, "PDF path exceeds limits", "resource_limit")
        if not points:
            return
        fill = _color(raw, raw.FPDFPageObj_GetFillColor, obj) if mode.value != FILL_NONE else None
        stroke = _color(raw, raw.FPDFPageObj_GetStrokeColor, obj) if stroke_flag.value else None
        if fill is None and mode.value != FILL_NONE or stroke is None and stroke_flag.value:
            raise Fallback("pattern paint")
        if (fill is None or fill[3] == 0) and (stroke is None or stroke[3] == 0):
            return
        width = ctypes.c_float()
        raw.FPDFPageObj_GetStrokeWidth(obj, width)
        similar, scale = _similarity(total)
        stroke_width = width.value * scale if stroke else 0
        if stroke and not similar:
            raise Fallback("nonuniform stroke")
        if stroke and stroke_width <= 0:
            stroke_width = 1  # a zero-width PDF stroke is the thinnest line the device can draw
        pen = _pen(points, total)
        value = evenodd_to_nonzero(pen.value) if mode.value == FILL_EVENODD else pen.value
        bounds = BoundsPen(None)
        pen.replay(bounds)
        if bounds.bounds is None:
            return
        merged = self.join_stroke(points, matrix, obj, stroke, stroke_width, fill)
        if merged:
            return
        pad = stroke_width / 2 if stroke else 0
        x0, y0, x1, y1 = bounds.bounds
        left, top = math.floor(x0 - pad), math.floor(y0 - pad)
        w, h = max(1, math.ceil(x1 + pad) - left), max(1, math.ceil(y1 + pad) - top)
        self.candidate.limits.size(w, h)
        recorded = RecordingPen()
        recorded.value = value
        self.counts["path"] += 1
        operation = {"type": "shape", "shape": "path", "name": self.unique(f"{self.name}-shape"),
                     "path": path_commands(recorded, left, top), "width": w, "height": h, "x": left, "y": top,
                     "fill": _hex(fill) if fill else "transparent", "stroke": _hex(stroke) if stroke else "transparent",
                     "stroke_width": stroke_width if stroke else 1}
        if stroke:
            self.stroke_details(obj, operation, scale)
        self.operations.append(operation)
        self.previous_path = (points, matrix.transform(_matrix(raw, obj)), operation, left, top)

    def join_stroke(self, points, matrix, obj, stroke, stroke_width, fill):
        """A stroke-only path drawn right after a fill-only path with the same geometry is that shape's outline: add
        it to the fill's layer (PDF writers, Vixl among them, often paint fill and stroke as two objects)."""
        previous = self.previous_path
        if not previous or fill is not None or not stroke:
            return False
        points0, matrix0, operation, left, top = previous
        if operation["stroke"] != "transparent":
            return False
        same = points0 == points and tuple(matrix0) == tuple(matrix.transform(_matrix(self.raw, obj)))
        pad = stroke_width / 2
        if not same and self.inside_outline(operation, _pen(points, matrix.transform(_matrix(self.raw, obj))), pad):
            # The stroke runs half its width inside the fill's outline (Vixl's own inside strokes):
            # the layer keeps the fill's outline and strokes inside it.
            operation["stroke"], operation["stroke_width"], operation["stroke_align"] = _hex(stroke), stroke_width, "inside"
            self.stroke_details(obj, operation, _similarity_scale(matrix.transform(_matrix(self.raw, obj))))
            self.previous_path = None
            return True
        if not same:
            return False
        x0, y0 = operation["x"], operation["y"]
        # Grow the box by the stroke's half width; the path keeps its place.
        grow = math.ceil(pad)
        operation["x"], operation["y"] = x0 - grow, y0 - grow
        operation["width"] += 2 * grow
        operation["height"] += 2 * grow
        from ...geometry import parse_path

        shifted = []
        for command, values in parse_path(operation["path"]):
            shifted.append(command + " ".join(f"{v + grow:.6g}" for v in values))
        operation["path"] = " ".join(shifted)
        operation["stroke"], operation["stroke_width"] = _hex(stroke), stroke_width
        self.stroke_details(obj, operation, _similarity_scale(matrix.transform(_matrix(self.raw, obj))))
        self.previous_path = None
        return True

    @staticmethod
    def inside_outline(operation, pen, pad):
        """Whether the closed stroke path ``pen`` (page pixels) runs ``pad`` inside the outline of the
        fill-only path ``operation``: grown by ``pad`` with mitred corners, it covers the fill's area."""
        from shapely import BufferJoinStyle
        from ...geometry import path_polygons
        from ...svg_import import path_commands
        from ...vector_boolean import filled_region

        if pad <= 0:
            return False
        fill = path_polygons(operation["path"])
        line = path_polygons(path_commands(pen, operation["x"], operation["y"]))
        if not fill or not line or not all(len(c) > 3 and c[0] == c[-1] for c in fill + line):
            return False
        outer, centre = filled_region(fill), filled_region(line)
        if outer.is_empty or centre.is_empty:
            return False
        grown = centre.buffer(pad, join_style=BufferJoinStyle.mitre, mitre_limit=16)
        return grown.symmetric_difference(outer).area <= 0.1 * outer.length

    def stroke_details(self, obj, operation, scale):
        raw = self.raw
        cap = {1: "round", 2: "square"}.get(raw.FPDFPageObj_GetLineCap(obj))
        join = {1: "round", 2: "bevel"}.get(raw.FPDFPageObj_GetLineJoin(obj))
        if cap:
            operation["line_cap"] = cap
        if join:
            operation["line_join"] = join
        count = raw.FPDFPageObj_GetDashCount(obj)
        if count > 0:
            values = (ctypes.c_float * count)()
            if raw.FPDFPageObj_GetDashArray(obj, values, count):
                dash = [v * scale for v in values]
                if len(dash) % 2:
                    dash *= 2
                if any(dash) and all(v >= 0 for v in dash):
                    operation["dash"] = dash
                    operation["dash_fit"] = False  # PDF dash arrays are exact lengths from the path's start
                    phase = ctypes.c_float()
                    if raw.FPDFPageObj_GetDashPhase(obj, phase) and phase.value:
                        operation["dash_offset"] = phase.value * scale

    # --- images ----------------------------------------------------------------------------------------------------

    def image(self, obj, matrix):
        from ...assets import add_image

        pdfium, raw = _pdfium()
        total = matrix.transform(_matrix(raw, obj))
        # Image space: the unit square, its first row at y=1.
        top_left, top_right, bottom_left = (total.transformPoint(p) for p in ((0, 1), (1, 1), (0, 0)))
        ux, uy = top_right[0] - top_left[0], top_right[1] - top_left[1]
        vx, vy = bottom_left[0] - top_left[0], bottom_left[1] - top_left[1]
        width, height = math.hypot(ux, uy), math.hypot(vx, vy)
        if width < 0.5 or height < 0.5:
            return
        if abs(ux * vx + uy * vy) > 1e-3 * width * height:
            raise Fallback("skewed image")
        mirrored = ux * vy - uy * vx < 0
        try:
            image = self.image_pixels(obj)
        except pdfium.PdfiumError as exc:
            raise Fallback(f"image: {exc}") from exc
        if image is None:
            raise Fallback("image")
        if mirrored:
            from PIL import ImageOps

            image = ImageOps.flip(image)
            # The flipped image's first row is the old last row: measure from there.
            top_left = bottom_left
            vx, vy = -vx, -vy
        angle = math.degrees(math.atan2(uy, ux))
        centre = (top_left[0] + (ux + vx) / 2, top_left[1] + (uy + vy) / 2)
        self.candidate.limits.size(*image.size)
        asset = add_image(self.candidate, image)
        self.counts["image"] += 1
        operation = {"type": "add", "asset": asset, "name": self.unique(f"{self.name}-image"),
                     "x": centre[0] - width / 2, "y": centre[1] - height / 2, "width": width, "height": height}
        if abs(angle) > 1e-6:
            operation["rotation"] = angle
        self.operations.append(operation)

    def image_pixels(self, obj):
        """The image's own pixels with its mask and colour space applied (RGBA)."""
        raw = self.raw
        size_w, size_h = ctypes.c_uint(), ctypes.c_uint()
        if hasattr(raw, "FPDFImageObj_GetImagePixelSize") and raw.FPDFImageObj_GetImagePixelSize(obj, size_w, size_h):
            self.candidate.limits.size(max(1, size_w.value), max(1, size_h.value))
        handle = raw.FPDFImageObj_GetRenderedBitmap(self.document_raw, self.page_raw, obj)
        if not handle:
            handle = raw.FPDFImageObj_GetBitmap(obj)
        if not handle:
            return None
        import pypdfium2 as pdfium

        bitmap = pdfium.PdfBitmap.from_raw(handle)
        try:
            return bitmap.to_pil().convert("RGBA")
        finally:
            bitmap.close()

    # --- text ------------------------------------------------------------------------------------------------------

    def text(self, obj, matrix):
        raw = self.raw
        mode = raw.FPDFTextObj_GetTextRenderMode(obj)
        if mode in (3, 7):  # invisible (OCR layers) or clip only
            return
        text = _string(raw, raw.FPDFTextObj_GetText, obj, self.textpage.raw, utf16=True)
        # pdfium ends a text object's text with a generated space; leading spaces keep their place in a run.
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\x02", "").rstrip()
        total = matrix.transform(_matrix(raw, obj))
        a, b, c, d, e, f = total
        sx, sy = math.hypot(a, b), math.hypot(c, d)
        if abs(a * c + b * d) > 1e-3 * sx * sy or abs(sx - sy) > 1e-3 * max(sx, sy):
            raise Fallback("skewed or stretched text")
        if a * d - b * c > 0:
            raise Fallback("mirrored text")
        size = ctypes.c_float()
        raw.FPDFTextObj_GetFontSize(obj, size)
        pixels = size.value * sx
        if pixels < 0.5:
            return
        paint = _color(raw, raw.FPDFPageObj_GetStrokeColor if mode == 1 else raw.FPDFPageObj_GetFillColor, obj)
        if paint is None:
            raise Fallback("pattern text")
        previous = self.lines[-1] if self.lines else None
        # The fill pass over an outline pass of the same text (pdfium's text page reports the second of two runs
        # drawn over each other as empty).
        fill_pass = (previous is not None and previous.get("outline") and previous["sequence"] == self.sequence - 1
                     and mode != 1 and text in ("", previous["text"]) and abs(previous["origin"][0] - e) < 0.5
                     and abs(previous["origin"][1] - f) < 0.5)
        if fill_pass:
            previous["color"] = _hex(paint) if paint[3] else "#00000000"
            previous["key"] = (*previous["key"][:2], previous["color"], previous["key"][3], previous["outline"])
            previous["sequence"] = self.sequence
            return
        if paint[3] == 0 or not text.strip():
            return
        outline = None
        if mode == 1:
            width = ctypes.c_float()
            raw.FPDFPageObj_GetStrokeWidth(obj, width)
            # A centred text stroke: the half outside the glyphs is the layer's outline width.
            outline = (_hex(paint), round(max(0.5, width.value * sx / 2), 4))
        font = raw.FPDFTextObj_GetFont(obj)
        family, base, weight, italic = self.font_names(font)
        from ...svg_import import font_warning, match_font

        bold = weight >= 600 or mode == 2 or "bold" in base.lower()
        name, unknown = match_font(self.candidate, [n for n in (family, base) if n], bold, italic)
        if unknown:
            self.warnings.append(font_warning(unknown))
        rotation = math.degrees(math.atan2(b, a))
        box = self.pixel_box(obj, matrix)
        self.counts["text"] += 1
        # A placeholder keeps the stacking order; merge_lines fills it in.
        slot = {"type": "_text"}
        color = "#00000000" if outline else _hex(paint)
        self.lines.append({"text": text, "origin": (e, f), "size": pixels, "color": color, "font": name,
                           "rotation": rotation, "box": box, "outline": outline,
                           "key": (name, round(pixels, 2), color, round(rotation, 3), outline),
                           "sequence": self.sequence, "slot": slot})
        self.operations.append(slot)

    @property
    def lines(self):
        return self.__dict__.setdefault("_lines", [])

    def font_names(self, font):
        raw = self.raw
        family = base = ""
        if font:
            if hasattr(raw, "FPDFFont_GetFamilyName"):
                family = _string(raw, raw.FPDFFont_GetFamilyName, font)
            getter = getattr(raw, "FPDFFont_GetBaseFontName", None) or getattr(raw, "FPDFFont_GetFontName", None)
            if getter:
                base = _string(raw, getter, font)
        if "+" in base[:7]:
            base = base.split("+", 1)[1]
        weight = raw.FPDFFont_GetWeight(font) if font and hasattr(raw, "FPDFFont_GetWeight") else 400
        angle = ctypes.c_int()
        italic = bool(font and hasattr(raw, "FPDFFont_GetItalicAngle") and raw.FPDFFont_GetItalicAngle(font, angle)
                      and angle.value != 0) or "italic" in base.lower() or "oblique" in base.lower()
        stem = base.split("-")[0].split(",")[0]
        embedded = bool(font and hasattr(raw, "FPDFFont_GetIsEmbedded") and raw.FPDFFont_GetIsEmbedded(font))
        # A font the PDF does not embed is named by its BaseFont; pdfium's family name is then its substitute's.
        names = (family, stem) if embedded else (stem, family)
        return names[0] or names[1], names[1], weight or 400, italic

    def merge_lines(self):
        """Consecutive lines of one style, one under the other with a shared left edge, centre or right edge, become
        one multi-line text layer; each other line is a layer of its own."""
        groups, current = [], []
        for number, line in enumerate(self.lines):
            if current and self.continues(current, line):
                current.append(line)
            else:
                if current:
                    groups.append(current)
                current = [line]
        if current:
            groups.append(current)
        replacements = {}
        for group in groups:
            first = group[0]
            align = self.alignment(group)
            text = "\n".join(line["text"].strip() if len(group) > 1 else line["text"] for line in group)
            origin = first["origin"]
            name = self.unique(f"{self.name}-text")
            inset = first["outline"][1] if first["outline"] else 0  # an outline grows the box around the glyphs
            operation = {"type": "text", "name": name, "text": text, "size": max(1, round(first["size"])),
                         "color": first["color"], "x": origin[0] - inset, "baseline_y": origin[1] - inset}
            if first["font"]:
                operation["font"] = first["font"]
            if len(group) > 1:
                gaps = [math.hypot(b["origin"][0] - a["origin"][0], b["origin"][1] - a["origin"][1])
                        for a, b in zip(group, group[1:])]
                operation["line_height"] = min(5, max(0.5, sum(gaps) / len(gaps) / max(1, round(first["size"]))))
            if align != "left" or abs(first["rotation"]) > 1e-6:
                operation["align"] = align
                box = first["box"]
                anchor = origin
                if align != "left" and box:
                    edge = (box[0] + box[2]) / 2 if align == "center" else box[2]
                    anchor = (edge, origin[1])
                self.anchored.append({"name": name, "anchor": anchor, "align": align, "rotation": first["rotation"]})
            if first["outline"]:
                outline = {"type": "text-set", "target": name, "stroke_color": first["outline"][0],
                           "stroke_width": first["outline"][1]}
                replacements[id(group[0]["slot"])] = [operation, outline]
            else:
                replacements[id(group[0]["slot"])] = [operation]
            for line in group[1:]:
                replacements[id(line["slot"])] = []
        self.operations = [item for op in self.operations
                           for item in (replacements.get(id(op), []) if op["type"] == "_text" else [op])]

    @staticmethod
    def continues(group, line):
        last = group[-1]
        if line["key"] != last["key"] or abs(line["rotation"]) > 1e-6 or line["sequence"] != last["sequence"] + 1:
            return False
        step = line["origin"][1] - last["origin"][1]
        if not 0.9 * line["size"] <= step <= 2.6 * line["size"]:
            return False
        if len(group) > 1:
            previous = last["origin"][1] - group[-2]["origin"][1]
            if abs(step - previous) > 0.15 * line["size"]:
                return False
        return PageReader.alignment([*group, line]) is not None

    @staticmethod
    def alignment(group):
        if len(group) == 1:
            return "left"
        boxes = [line["box"] for line in group]
        if all(abs(line["origin"][0] - group[0]["origin"][0]) <= 0.75 for line in group):
            return "left"
        if all(boxes):
            centres = [(box[0] + box[2]) / 2 for box in boxes]
            if max(centres) - min(centres) <= 1.5:
                return "center"
            rights = [box[2] for box in boxes]
            if max(rights) - min(rights) <= 1.5:
                return "right"
        return None

    # --- objects drawn as images -----------------------------------------------------------------------------------

    def flush(self):
        """Draw the pending run of objects as one image layer, in stacking order."""
        if not self.pending:
            return
        run, self.pending = self.pending, []
        if len(self.rasterized) >= MAX_RUNS:
            # Too many separate runs: merge into the last image (stacking within the merged run is kept).
            raise VixlError("unsupported_pdf", "The PDF page has too many objects Vixl cannot edit; import it with "
                            "svg_mode='appearance'")
        from ...assets import add_image

        pdfium, raw = _pdfium()
        indices = {index for index, _ in run}
        with pdfium.PdfDocument(self.data) as document:
            page = document[self.page_number - 1]
            try:
                objects = [raw.FPDFPage_GetObject(page.raw, i) for i in range(raw.FPDFPage_CountObjects(page.raw))]
                for index, obj in enumerate(objects):
                    if index not in indices:
                        raw.FPDFPage_RemoveObject(page.raw, obj)
                        raw.FPDFPageObj_Destroy(obj)
                raw.FPDFPage_GenerateContent(page.raw)
                width, height = self.size
                self.candidate.limits.size(max(1, width), max(1, height))
                bitmap = page.render(scale=self.k, fill_color=(0, 0, 0, 0), may_draw_forms=False)
                try:
                    image = bitmap.to_pil().convert("RGBA")
                finally:
                    bitmap.close()
            finally:
                page.close()
        box = image.getchannel("A").getbbox()
        if not box:
            return
        crop = image.crop(box)
        asset = add_image(self.candidate, crop)
        name = self.unique(f"{self.name}-image")
        self.counts["image"] += 1
        self.operations.append({"type": "add", "asset": asset, "name": name, "x": box[0], "y": box[1],
                                "provenance": {"type": "pdf-objects", "reason": ", ".join(sorted({r for _, r in run}))}})
        self.rasterized.append({"layer": name, "objects": len(run), "reason": sorted({r for _, r in run})})


def _similarity_scale(matrix):
    a, b, c, d, _, _ = matrix
    return math.sqrt(abs(a * d - b * c))
