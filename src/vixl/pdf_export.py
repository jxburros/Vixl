"""Multi-page PDF export: vector pages with real, selectable text, or raster pages.

``vector`` content draws solids, shapes and paths, gradients (as PDF shadings), plain and rich
text (embedded TrueType subsets with ToUnicode maps, so text can be selected and searched) and
plain groups as PDF graphics; image layers are images. Anything PDF cannot draw the same way
(effects, layer styles, masks, clipping, blend modes, adjustment layers, paint and pixel layers)
is embedded as an image of exactly what the renderer draws, and listed under ``raster_fallbacks``.
``raster`` content writes each page as one image, which also supports CMYK separation.

Every page of a multi-page document becomes a PDF page (hidden pages are left out unless named).
"""

import io
import math
from pathlib import Path

import numpy as np

from .errors import require
from .model import finite
from .pdf_writer import FontSet, Name, Text, Writer, image_xobject

VECTOR_LEAVES = ("solid", "shape", "gradient", "text")


def _fmt(value):
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def matrix_ops(m):
    """``a b c d e f cm`` for a 3×3 affine matrix."""
    return f"{_fmt(m[0, 0])} {_fmt(m[1, 0])} {_fmt(m[0, 1])} {_fmt(m[1, 1])} {_fmt(m[0, 2])} {_fmt(m[1, 2])} cm"


def affine(a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
    return np.array([[a, c, e], [b, d, f], [0, 0, 1]], dtype=float)


def layer_matrix(layer, bounds):
    """Local layer pixels (0…rest width/height) → parent pixels, as the renderer places them."""
    from .render import rest_size

    x, y, w, h = bounds
    rw, rh = rest_size(layer)
    angle = math.radians(layer.get("rotation", 0))
    co, si = math.cos(angle), math.sin(angle)
    flip = affine(-1 if layer.get("flip_x") else 1, 0, 0, -1 if layer.get("flip_y") else 1)
    return affine(1, 0, 0, 1, x + w / 2, y + h / 2) @ affine(co, si, -si, co) @ flip @ affine(1, 0, 0, 1, -rw / 2, -rh / 2)


def path_ops(commands):
    """PDF path operators for parsed SVG path commands (M L C Q Z)."""
    out, current = [], (0.0, 0.0)
    start = (0.0, 0.0)
    for command, values in commands:
        if command == "M":
            current = start = (values[0], values[1])
            out.append(f"{_fmt(values[0])} {_fmt(values[1])} m")
        elif command == "L":
            current = (values[0], values[1])
            out.append(f"{_fmt(values[0])} {_fmt(values[1])} l")
        elif command == "C":
            current = (values[4], values[5])
            out.append(" ".join(_fmt(v) for v in values) + " c")
        elif command == "Q":
            # A quadratic Bézier as the equivalent cubic (several control points for TrueType runs).
            points = list(zip(values[0::2], values[1::2]))
            controls, end = points[:-1], points[-1]
            implied = []
            for i, ctrl in enumerate(controls):
                nxt = controls[i + 1] if i + 1 < len(controls) else None
                target = ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2) if nxt else end
                implied.append((ctrl, target))
            for ctrl, target in implied:
                c1 = (current[0] + 2 / 3 * (ctrl[0] - current[0]), current[1] + 2 / 3 * (ctrl[1] - current[1]))
                c2 = (target[0] + 2 / 3 * (ctrl[0] - target[0]), target[1] + 2 / 3 * (ctrl[1] - target[1]))
                out.append(" ".join(_fmt(v) for v in (*c1, *c2, *target)) + " c")
                current = target
        elif command == "Z":
            out.append("h")
            current = start
    return out


def ellipse_ops(x, y, w, h):
    k = 0.5522847498
    rx, ry = w / 2, h / 2
    cx, cy = x + rx, y + ry
    return [f"{_fmt(cx + rx)} {_fmt(cy)} m",
            f"{_fmt(cx + rx)} {_fmt(cy + k * ry)} {_fmt(cx + k * rx)} {_fmt(cy + ry)} {_fmt(cx)} {_fmt(cy + ry)} c",
            f"{_fmt(cx - k * rx)} {_fmt(cy + ry)} {_fmt(cx - rx)} {_fmt(cy + k * ry)} {_fmt(cx - rx)} {_fmt(cy)} c",
            f"{_fmt(cx - rx)} {_fmt(cy - k * ry)} {_fmt(cx - k * rx)} {_fmt(cy - ry)} {_fmt(cx)} {_fmt(cy - ry)} c",
            f"{_fmt(cx + k * rx)} {_fmt(cy - ry)} {_fmt(cx + rx)} {_fmt(cy - k * ry)} {_fmt(cx + rx)} {_fmt(cy)} c", "h"]


def rounded_ops(x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    if r <= 0:
        return [f"{_fmt(x)} {_fmt(y)} {_fmt(w)} {_fmt(h)} re"]
    k = 0.5522847498 * r
    x1, y1 = x + w, y + h
    return [f"{_fmt(x + r)} {_fmt(y)} m", f"{_fmt(x1 - r)} {_fmt(y)} l",
            f"{_fmt(x1 - r + k)} {_fmt(y)} {_fmt(x1)} {_fmt(y + r - k)} {_fmt(x1)} {_fmt(y + r)} c",
            f"{_fmt(x1)} {_fmt(y1 - r)} l",
            f"{_fmt(x1)} {_fmt(y1 - r + k)} {_fmt(x1 - r + k)} {_fmt(y1)} {_fmt(x1 - r)} {_fmt(y1)} c",
            f"{_fmt(x + r)} {_fmt(y1)} l",
            f"{_fmt(x + r - k)} {_fmt(y1)} {_fmt(x)} {_fmt(y1 - r + k)} {_fmt(x)} {_fmt(y1 - r)} c",
            f"{_fmt(x)} {_fmt(y + r)} l",
            f"{_fmt(x)} {_fmt(y + r - k)} {_fmt(x + r - k)} {_fmt(y)} {_fmt(x + r)} {_fmt(y)} c", "h"]


class PageBuilder:
    """Content stream and resources for one PDF page, in canvas pixels (y down)."""

    def __init__(self, document, view, writer, fonts, images):
        self.document, self.view, self.writer, self.fonts, self.images = document, view, writer, fonts, images
        self.ops = []
        self.xobjects, self.states, self.shadings = {}, {}, {}
        self.fallbacks = []

    # -- resources ----------------------------------------------------------------------------

    def alpha(self, fill=1.0, stroke=1.0):
        fill, stroke = round(fill, 4), round(stroke, 4)
        if fill >= 1 and stroke >= 1:
            return None
        key = (fill, stroke)
        if key not in self.states:
            name = f"Gs{len(self.states) + 1}"
            self.states[key] = (name, self.writer.add({"Type": Name("ExtGState"), "ca": fill, "CA": stroke}))
        return self.states[key][0]

    def place_image(self, image, matrix, box):
        """Draw ``image`` filling ``box`` (x, y, w, h) in the space ``matrix`` maps to the page."""
        import hashlib

        key = hashlib.sha256(image.mode.encode() + str(image.size).encode() + image.tobytes()).hexdigest()
        if key not in self.images:
            self.images[key] = image_xobject(self.writer, image)
        name = next((n for n, ref in self.xobjects.items() if ref is self.images[key]), None)
        if name is None:
            name = f"Im{len(self.xobjects) + 1}"
            self.xobjects[name] = self.images[key]
        x, y, w, h = box
        self.ops += ["q", matrix_ops(matrix), matrix_ops(affine(w, 0, 0, -h, x, y + h)), f"/{name} Do", "Q"]

    def shading(self, layer, w, h):
        """An axial or radial shading for an opaque gradient layer, in unit-square coordinates."""
        from .design import resolve_color
        from .render import color

        state = self.view.state
        stops = layer.get("stops") or [{"offset": 0, "color": layer.get("start", "black")},
                                       {"offset": 1, "color": layer.get("end", "white")}]
        colors = [(s["offset"], color(resolve_color(s["color"], state))) for s in stops]
        if any(rgba[3] < 255 for _, rgba in colors):
            return None
        if colors[0][0] > 0:
            colors.insert(0, (0.0, colors[0][1]))
        if colors[-1][0] < 1:
            colors.append((1.0, colors[-1][1]))
        functions = [{"FunctionType": 2, "Domain": [0, 1], "C0": [c / 255 for c in a[:3]], "C1": [c / 255 for c in b[:3]], "N": 1}
                     for (_, a), (_, b) in zip(colors, colors[1:])]
        if len(functions) == 1:
            function = functions[0]
        else:
            function = {"FunctionType": 3, "Domain": [0, 1], "Functions": functions,
                        "Bounds": [offset for offset, _ in colors[1:-1]], "Encode": [0, 1] * len(functions)}
        direction = layer.get("direction", "vertical")
        if direction == "radial":
            shading = {"ShadingType": 3, "ColorSpace": Name("DeviceRGB"), "Coords": [0.5, 0.5, 0, 0.5, 0.5, 0.5],
                       "Function": function, "Extend": [True, True]}
        else:
            if direction == "horizontal":
                coords = [0, 0, 1, 0]
            elif direction == "vertical":
                coords = [0, 0, 0, 1]
            else:
                a = math.radians(layer.get("angle", 0))
                u = np.array([math.cos(a), math.sin(a)]) / (abs(math.cos(a)) + abs(math.sin(a)))
                v = u / max(float(u @ u), 1e-12)
                coords = [0.5 - 0.5 * v[0], 0.5 - 0.5 * v[1], 0.5 + 0.5 * v[0], 0.5 + 0.5 * v[1]]
            shading = {"ShadingType": 2, "ColorSpace": Name("DeviceRGB"), "Coords": coords, "Function": function,
                       "Extend": [True, True]}
        name = f"Sh{len(self.shadings) + 1}"
        self.shadings[name] = self.writer.add(shading)
        return name

    # -- drawing ------------------------------------------------------------------------------

    def fallback(self, layer, reason):
        if layer["type"] not in ("raster", "frame") or reason != "image":  # an image layer is an image anyway
            self.fallbacks.append({"layer": layer["name"], "reason": reason})

    def draw(self, layers, bounds, parent=None, matrix=None):
        from .render import ink_origin, layer_ink, layer_surface

        matrix = np.eye(3) if matrix is None else matrix
        index = {item["id"]: item for item in layers}
        for layer in layers:
            if layer.get("parent") != parent or not layer["visible"] or layer["opacity"] <= 0:
                continue
            b = bounds[layer["id"]]
            reason = self.raster_reason(layer)
            if reason is None and layer["type"] == "group":
                inner = matrix @ layer_matrix(layer, b) @ affine(layer["width"] / layer["content_width"], 0, 0,
                                                                 layer["height"] / layer["content_height"])
                self.draw(layers, bounds, layer["id"], inner)
                continue
            if reason is None:
                try:
                    self.leaf(layer, b, matrix)
                    continue
                except Unsupported as exc:
                    reason = str(exc)
            self.fallback(layer, reason)
            if layer.get("styles") or layer.get("clip"):
                parent_layer = index.get(parent)
                size = ((parent_layer["content_width"], parent_layer["content_height"]) if parent_layer else
                        (self.view.state["canvas"]["width"], self.view.state["canvas"]["height"]))
                tile = layer_surface(self.view, layer, bounds, size, index)
                box = tile.getchannel("A").getbbox()
                if box:
                    crop = tile.crop(box)
                    self.place_image(crop, matrix, (box[0], box[1], crop.width, crop.height))
            else:
                image = layer_ink(self.view, layer, b)
                if layer["opacity"] != 1:
                    image.putalpha(image.getchannel("A").point(lambda a: round(a * layer["opacity"])))
                x, y = ink_origin(image, b)
                self.place_image(image, matrix, (x, y, image.width, image.height))

    @staticmethod
    def raster_reason(layer):
        if layer["type"] == "adjustment":
            return "adjustment layers change what is beneath them"
        if layer.get("blend", "normal") != "normal":
            return f"{layer['blend']} blending"
        if any(e.get("enabled", True) for e in layer.get("effects") or []):
            return "effects"
        if any(s.get("enabled", True) for s in (layer.get("styles") or {}).values()):
            return "layer styles"
        if layer.get("mask") and layer["mask"].get("enabled", True):
            return "mask"
        if layer.get("clip"):
            return "clipping"
        if layer.get("lookup"):
            return "lookup table"
        if layer.get("repeat"):
            return "repeat"
        if layer["type"] == "group":
            return "group opacity" if layer["opacity"] != 1 else None
        if layer["type"] == "field":
            return None
        from .trim import trim_range

        if trim_range(layer):
            return "trimmed stroke"
        if layer["type"] not in VECTOR_LEAVES:
            return {"raster": "image", "frame": "image", "paint": "brush strokes", "pixel": "pixel art",
                    "pathfinder": "pathfinder"}.get(layer["type"], layer["type"])
        return None

    def leaf(self, layer, bounds, matrix):
        from .render import color

        local = matrix @ layer_matrix(layer, bounds)
        w, h = layer["width"], layer["height"]
        opacity = layer["opacity"]
        kind = layer["type"]
        self.ops += ["q", matrix_ops(local)]
        if kind == "solid":
            rgba = color(layer["fill"])
            self.fill_ops([f"0 0 {_fmt(w)} {_fmt(h)} re"], rgba, opacity)
        elif kind == "gradient":
            name = self.shading(layer, w, h)
            if name is None:
                self.ops.pop()
                self.ops.pop()
                raise Unsupported("translucent gradient stops")
            state_name = self.alpha(opacity, opacity)
            self.ops += ([f"/{state_name} gs"] if state_name else []) + [
                matrix_ops(affine(w, 0, 0, h)), "0 0 1 1 re W n", f"/{name} sh"]
        elif kind == "shape":
            self.shape(layer, w, h, opacity)
        elif kind == "field":
            from .forms import pdf_field_appearance

            pdf_field_appearance(self, layer, w, h)
        else:
            self.text(layer, opacity)
        self.ops.append("Q")

    def fill_ops(self, geometry, rgba, opacity, rule="f"):
        if rgba[3] == 0:
            return
        state_name = self.alpha(rgba[3] / 255 * opacity, 1)
        self.ops += (["q", f"/{state_name} gs"] if state_name else ["q"]) + [
            f"{_fmt(rgba[0] / 255)} {_fmt(rgba[1] / 255)} {_fmt(rgba[2] / 255)} rg", *geometry, rule, "Q"]

    def stroke_ops(self, geometry, rgba, width, opacity, cap=0, join=0):
        if rgba[3] == 0 or width <= 0:
            return
        state_name = self.alpha(1, rgba[3] / 255 * opacity)
        self.ops += (["q", f"/{state_name} gs"] if state_name else ["q"]) + [
            f"{_fmt(rgba[0] / 255)} {_fmt(rgba[1] / 255)} {_fmt(rgba[2] / 255)} RG", f"{_fmt(width)} w", f"{cap} J",
            f"{join} j", *geometry, "S", "Q"]

    def shape(self, layer, w, h, opacity):
        from .design import resolve_color
        from .geometry import parse_path, shape_path
        from .render import color

        state = self.view.state
        fill = color(resolve_color(layer.get("fill", "white"), state))
        stroke = color(resolve_color(layer.get("stroke", "transparent"), state))
        width = layer.get("stroke_width", 1)
        shape = layer["shape"]
        if shape == "path":
            path, view = shape_path(layer)
            scale = affine(w / view[0], 0, 0, h / view[1])
            geometry = path_ops(parse_path(path))
            cap = {"round": 1, "square": 2}.get(layer.get("line_cap"), 0)
            self.ops += ["q", matrix_ops(scale)]
            self.fill_ops(geometry, fill, opacity)
            self.stroke_ops(geometry, stroke, width, opacity, cap, 1 if cap == 1 else 0)
            self.ops.append("Q")
            return
        pad = width / 2 if stroke[3] else 0
        if pad and shape != "line" and 2 * pad >= min(w, h) - 1:
            return
        x0, y0, bw, bh = pad, pad, w - 2 * pad, h - 2 * pad
        # Pillow strokes rectangles and ellipses inside their (already inset) box, while PDF strokes
        # centre on the path: inset the path another half stroke so the two match.
        ix, iy, iw, ih = x0 + pad, y0 + pad, bw - 2 * pad, bh - 2 * pad
        if shape == "rectangle":
            geometry = [f"{_fmt(ix)} {_fmt(iy)} {_fmt(iw)} {_fmt(ih)} re"]
        elif shape in ("rounded-rectangle", "capsule"):
            radius = layer.get("radius", min(w, h) / (2 if shape == "capsule" else 5))
            geometry = rounded_ops(ix, iy, iw, ih, radius - pad)
        elif shape == "ellipse":
            geometry = ellipse_ops(ix, iy, iw, ih)
        elif shape == "line":
            self.stroke_ops([f"{_fmt(x0)} {_fmt(y0)} m", f"{_fmt(w - pad)} {_fmt(h - pad)} l"],
                            stroke if stroke[3] else fill, max(1, width), opacity)
            return
        else:
            path, view = shape_path(layer)
            from .geometry import path_polygons

            geometry = []
            for polygon in path_polygons(path):
                points = [(x0 + px / view[0] * bw, y0 + py / view[1] * bh) for px, py in polygon]
                if len(points) >= 2:
                    geometry.append(f"{_fmt(points[0][0])} {_fmt(points[0][1])} m")
                    geometry += [f"{_fmt(px)} {_fmt(py)} l" for px, py in points[1:]]
                    geometry.append("h")
        self.fill_ops(geometry, fill, opacity)
        self.stroke_ops(geometry, stroke, width, opacity, 1, 1)

    def text(self, layer, opacity):
        """Draw a text layer's glyphs as embedded-font text (or outlines when a font cannot be
        embedded, or for warped and path text)."""
        from .design import resolve_color
        from .render import color
        from .richtext import active

        state = self.view.state
        stroke_width = layer.get("stroke_width", 0)
        stroke_color = color(resolve_color(layer.get("stroke_color", "black"), state))
        if active(layer):
            from .richtext import fitted

            result = fitted(self.view, layer)
            if not layer.get("text_layout"):
                # Auto-sized rich text draws at its natural size, stretched to the layer if resized.
                self.ops.append(matrix_ops(affine(layer["width"] / max(1, result.width), 0, 0,
                                                  layer["height"] / max(1, result.height))))
            for x, y, w, h, rgba, kind in result.rects:
                if kind == "highlight":
                    self.fill_ops([f"{_fmt(x)} {_fmt(y)} {_fmt(w)} {_fmt(h)} re"], rgba, opacity)
            glyphs = [(g.data, g.name, g.x, g.y, g.size, g.text, g.color, g.bold, g.italic) for g in result.glyphs]
            self.glyph_runs(glyphs, opacity, stroke_width, stroke_color)
            for x, y, w, h, rgba, kind in result.rects:
                if kind != "highlight":
                    self.fill_ops([f"{_fmt(x)} {_fmt(y)} {_fmt(w)} {_fmt(h)} re"], rgba, opacity)
            return
        from .text import UnsupportedText, plan, plan_glyphs

        try:
            layout = plan(self.view, layer)
        except UnsupportedText as exc:
            raise Unsupported(str(exc)) from exc
        fill = color(resolve_color(layer.get("color", "white"), state))
        self.ops.append(matrix_ops(affine(layer["width"] / max(1, layout.width), 0, 0, layer["height"] / max(1, layout.height))))
        glyphs = plan_glyphs(self.view, layer, layout)
        if glyphs is None:
            # Warped or path text: its outlines, as filled paths.
            from .geometry import parse_path

            for path, m in layout.paths:
                geometry = path_ops(parse_path(path))
                self.ops += ["q", matrix_ops(affine(*m))]
                if stroke_width:
                    scale = math.hypot(m[0], m[1]) or 1
                    self.stroke_ops(geometry, stroke_color, 2 * stroke_width / scale, opacity, 1, 1)
                self.fill_ops(geometry, fill, opacity)
                self.ops.append("Q")
            return
        self.glyph_runs([(d, n, x, y, s, t, fill, False, False) for d, n, x, y, s, t in glyphs], opacity, stroke_width,
                        stroke_color)

    def glyph_runs(self, glyphs, opacity, stroke_width, stroke_color):
        from .text import face, glyph_outline
        from .geometry import parse_path

        passes = [("stroke", stroke_color)] if stroke_width else []
        passes.append(("fill", None))
        for mode, override in passes:
            block, current, run = [], None, None

            def flush():
                # One text object per line run: a Tm at the first glyph, then TJ with kerning
                # adjustments so viewers place every glyph exactly and read the run as a line.
                if not run:
                    return
                size, skew, x0, y0, width_op, items = run
                if width_op:
                    block.append(width_op)
                parts, hexes = [], []
                for i, (gid, gx, advance) in enumerate(items):
                    hexes.append(f"{gid:04X}")
                    if i + 1 < len(items):
                        adjust = round(advance - (items[i + 1][1] - gx) / size * 1000, 2)
                        if abs(adjust) >= 0.01:
                            parts += [f"<{''.join(hexes)}>", _fmt(adjust)]
                            hexes = []
                if hexes:
                    parts.append(f"<{''.join(hexes)}>")
                block.extend([f"{_fmt(size)} 0 {_fmt(skew)} {_fmt(-size)} {_fmt(x0)} {_fmt(y0)} Tm",
                              f"[{' '.join(parts)}] TJ"])

            for data, name, x, y, size, text, rgba, bold, italic in glyphs:
                paint = override or rgba
                if not self.fonts.embeddable_cached(data):
                    path, _ = glyph_outline(data, name)
                    if not path:
                        continue
                    upem = face(data)[0]["head"].unitsPerEm
                    f = size / upem
                    skew = f * 0.2126 if italic else 0
                    geometry = path_ops(parse_path(path))
                    self.ops += ["q", matrix_ops(affine(f, 0, skew, -f, x, y))]
                    if mode == "stroke":
                        self.stroke_ops(geometry, paint, 2 * stroke_width / f, opacity, 1, 1)
                    else:
                        self.fill_ops(geometry, paint, opacity)
                    self.ops.append("Q")
                    continue
                resource, gid = self.fonts.use(data, name, text, self.writer)
                key = (resource, paint, bold, mode)
                if key != current:
                    flush()
                    run = None
                    if block:
                        self.ops += block + ["ET", "Q"]
                    current = key
                    state_name = self.alpha(paint[3] / 255 * opacity, paint[3] / 255 * opacity)
                    rgb = f"{_fmt(paint[0] / 255)} {_fmt(paint[1] / 255)} {_fmt(paint[2] / 255)}"
                    setup = ["q"] + ([f"/{state_name} gs"] if state_name else []) + [f"{rgb} rg", f"{rgb} RG", "BT",
                                                                                      f"/{resource} 1 Tf"]
                    if mode == "stroke":
                        setup += ["1 Tr", "1 j"]
                    elif bold:
                        setup += ["2 Tr", "1 j"]
                    else:
                        setup += ["0 Tr"]
                    block = setup
                skew = size * 0.2126 if italic else 0
                width = (2 * stroke_width / size) if mode == "stroke" else 0.045 if bold else None
                width_op = f"{_fmt(width)} w" if width else None
                advance = self.fonts.advance(data, name)
                if run and run[0] == size and run[1] == skew and abs(run[3] - y) < 1e-3 and run[4] == width_op:
                    run[5].append((gid, x, advance))
                else:
                    flush()
                    run = [size, skew, x, y, width_op, [(gid, x, advance)]]
            flush()
            if block:
                self.ops += block + ["ET", "Q"]

    def resources(self):
        result = {}
        fonts = self.fonts.resources()
        if fonts:
            result["Font"] = fonts
        if self.xobjects:
            result["XObject"] = dict(self.xobjects)
        if self.states:
            result["ExtGState"] = {name: ref for name, ref in self.states.values()}
        if self.shadings:
            result["Shading"] = dict(self.shadings)
        return result


class Unsupported(Exception):
    """A layer feature the vector writer draws as an image instead."""


class Fonts(FontSet):
    def __init__(self):
        super().__init__()
        self._embeddable = {}

    def advance(self, data, name):
        """A glyph's advance in thousandths of the size, as written to the font's /W array."""
        from .text import face

        outline = face(data)[0]
        return round(outline["hmtx"][name][0] * 1000 / outline["head"].unitsPerEm)

    def embeddable_cached(self, data):
        import hashlib

        key = hashlib.sha256(data).hexdigest()
        if key not in self._embeddable:
            self._embeddable[key] = self.embeddable(data)
        return self._embeddable[key]


def page_views(project, pages=None):
    """(label, render view) for each page to export."""
    from .pages import find_page, page_list
    from .render import view_page

    if not project.state.get("pages"):
        require(pages in (None, [], [1], ["1"]), "This document has no pages", field="pages")
        return [("1", project)]
    records = [find_page(project.state, ref, "pages") for ref in pages] if pages else page_list(project, include_hidden=False)
    require(records, "No pages to export (every page is hidden)", field="pages")
    return [(record["name"], view_page(project, record["id"])) for record in records]


def page_geometry(canvas, dpi):
    """(width, height, kx, ky, bleed) of a page in points for a canvas exported at ``dpi``.

    Print sizes keep their physical trim and bleed (``canvas.physical``), so the page measures
    exactly trim + 2 × bleed even when the bleed is a fractional number of pixels (0.125 in at
    300 dpi is 37.5 px, stored as 38): the pixels then stretch by a hair to fill the page. Other
    canvases map pixels to points at ``dpi``."""
    from .sizes import PX, UNIT_INCHES, to_pixels

    k = 72 / dpi
    w, h, bleed = canvas["width"], canvas["height"], canvas.get("bleed", 0)
    physical = canvas.get("physical")
    if physical and physical.get("unit", PX) != PX and canvas.get("dpi") == dpi:
        unit, amount = physical["unit"], physical.get("bleed", 0)
        pixels = [round(to_pixels(physical[key], unit, dpi)) + 2 * round(to_pixels(amount, unit, dpi))
                  for key in ("width", "height")]
        if pixels == [w, h] and round(to_pixels(amount, unit, dpi)) == bleed:
            points = 72 * UNIT_INCHES[unit]
            width, height = (physical["width"] + 2 * amount) * points, (physical["height"] + 2 * amount) * points
            return width, height, width / w, height / h, amount * points
    return w * k, h * k, k, k, bleed * k


def export_pdf(project, path=None, *, pages=None, content="vector", dpi=None, background="white", color_space="rgb",
               jpeg_quality=None, title=None, lang=None, annotations=None, acroform=None, fillable=False, separation=None,
               report=None, views=None):
    """Write a PDF with one page per document page. Returns the bytes (and writes ``path``).

    ``views`` [(label, page view)] replaces the document's pages (combined form fills).
    ``annotations(view, page_index, builder) -> [annotation refs]`` and ``acroform(writer) ->
    dict`` let form export add fields; with ``fillable`` the page artwork leaves field values to
    the widgets. ``report`` (a dict) receives raster fallbacks per page."""
    require(content in ("vector", "raster"), "pdf content must be vector or raster", field="content")
    require(color_space in ("rgb", "cmyk"), "Color space must be rgb or cmyk")
    require(color_space == "rgb" or content == "raster", "CMYK PDF pages are raster; use content raster", field="content")
    canvas = project.state["canvas"]
    dpi = finite(dpi or canvas.get("dpi") or 72, "dpi", 36, 2400)
    views = views if views is not None else page_views(project, pages)
    stream = io.BytesIO()
    writer = Writer(stream)
    fonts = Fonts()
    images = {}
    pages_ref = writer.reserve()
    kids = []
    fallbacks = {}
    from .design import resolve_color
    from .render import color, render

    for number, (label, view) in enumerate(views):
        c = view.state["canvas"]
        width, height, kx, ky, bleed = page_geometry(c, dpi)
        builder = PageBuilder(project, view, writer, fonts, images)
        builder.k, builder.ky, builder.fillable = kx, ky, fillable
        builder.ops.append(f"{_fmt(kx)} 0 0 {_fmt(-ky)} 0 {_fmt(height)} cm")
        if content == "raster":
            image = render(view)
            base = np.zeros((image.height, image.width, 4), dtype=np.uint8)
            base[:] = color(background)
            from PIL import Image

            flat = Image.fromarray(base, "RGBA")
            flat.alpha_composite(image)
            if color_space == "cmyk":
                from . import colors

                flat = colors.cmyk_image(flat, **(separation or {}))
            else:
                flat = flat.convert("RGB")
            if jpeg_quality:
                ref = image_xobject(writer, flat, jpeg_quality=jpeg_quality)
            else:
                ref = image_xobject(writer, flat)
            builder.xobjects["Im1"] = ref
            builder.ops += ["q", f"{_fmt(c['width'])} 0 0 {_fmt(-c['height'])} 0 {_fmt(c['height'])} cm", "/Im1 Do", "Q"]
        else:
            rgba = color(resolve_color(c["background"], view.state))
            back = color(background)
            if rgba[3] < 255:
                builder.fill_ops([f"0 0 {_fmt(c['width'])} {_fmt(c['height'])} re"], back, 1)
            builder.fill_ops([f"0 0 {_fmt(c['width'])} {_fmt(c['height'])} re"], rgba, 1)
            from .render import resolve_layout, resolved_layers

            layers = resolved_layers(view)
            bounds = resolve_layout(view, layers=layers)
            if any(item["type"] == "adjustment" or item.get("blend", "normal") != "normal" for item in layers
                   if item["visible"]):
                # Backdrop-dependent layers: the whole page as one image.
                builder.fallback({"name": "page"}, "blend modes or adjustment layers depend on the backdrop")
                image = render(view)
                builder.place_image(image, np.eye(3), (0, 0, image.width, image.height))
            else:
                builder.draw(layers, bounds)
        annots = annotations(view, number, builder) if annotations else []
        content_ref = writer.add_stream({}, "\n".join(builder.ops).encode("latin-1"))
        page = {"Type": Name("Page"), "Parent": pages_ref, "MediaBox": [0, 0, round(width, 4), round(height, 4)],
                "Resources": builder.resources(), "Contents": content_ref}
        if bleed:
            page["TrimBox"] = [round(bleed, 4), round(bleed, 4), round(width - bleed, 4), round(height - bleed, 4)]
            page["BleedBox"] = [0, 0, round(width, 4), round(height, 4)]
        if annots:
            page["Annots"] = annots  # in tab order
        extra = getattr(builder, "page_extra", None)
        if extra:
            page.update(extra)
        kids.append(writer.add(page))
        if builder.fallbacks:
            fallbacks[label] = builder.fallbacks
    fonts.write(writer)
    writer.add({"Type": Name("Pages"), "Kids": kids, "Count": len(kids)}, pages_ref)
    texts = []
    if title is None:
        for _, view in views[:1]:
            texts = [layer.get("text", "") for layer in view.state["layers"] if layer["type"] == "text" and layer["visible"]]
        title = (texts[0] if texts else "")[:200]
    info = writer.add({"Title": Text(title) if title else None, "Producer": Text("Vixl")})
    catalog = {"Type": Name("Catalog"), "Pages": pages_ref}
    if title:
        catalog["ViewerPreferences"] = {"DisplayDocTitle": True}
    if lang:
        catalog["Lang"] = Text(lang)
    if acroform is not None:
        catalog["AcroForm"] = acroform(writer)
    root = writer.add(catalog)
    writer.finish(root, info)
    data = stream.getvalue()
    if report is not None:
        report.update(pages=len(kids), raster_fallbacks=fallbacks, fonts=len(fonts.fonts))
    if path:
        Path(path).write_bytes(data)
    return data
