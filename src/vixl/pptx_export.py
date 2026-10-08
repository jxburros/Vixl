"""PowerPoint (.pptx) export: one editable slide per page, with speaker notes.

Shapes become native PowerPoint shapes (preset geometry where it matches, custom geometry for
polygons, stars and paths), solid and gradient fills and outlines; text becomes text boxes with
real runs (font, size, color, bold, italic, underline, strike, highlight, super/subscript),
paragraph alignment and spacing, and bullets or numbering; plain groups become groups. Layers
PowerPoint cannot draw the same way (effects, styles, masks, clipping, blend modes, skew and affine
transforms, paint and pixel art) become pictures of exactly what Vixl renders, listed under ``raster_fallbacks``; image layers
are pictures anyway.
Master-page layers are drawn on every slide that uses them. Fonts are referenced by family name and
are not embedded (see ``Exporter.font_warnings``); the report lists them, and warns about each one
that is not a font every Office installation has, so they can be installed where the deck is shown.
"""

import io
import math
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape, quoteattr

from .errors import require

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
# Families PowerPoint, Keynote and Google Slides all have, so a deck using only these needs no warning.
COMMON_FONTS = frozenset({"Arial", "Calibri", "Calibri Light", "Cambria", "Consolas", "Courier New", "Georgia", "Helvetica",
                          "Impact", "Segoe UI", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana"})
TRANSITIONS = {"fade": "<p:fade/>", "push": '<p:push dir="u"/>', "wipe": "<p:wipe/>", "cover": "<p:cover/>",
               "split": "<p:split/>", "zoom": "<p:zoom/>"}


def _attr(value):
    return quoteattr(str(value))


def _text(value):
    # XML 1.0 forbids most control characters; drop them rather than writing an invalid part.
    return escape("".join(c for c in value if c in "\t\n\r" or ord(c) >= 32))


def family_name(data):
    """The typographic family name of a font file (for PowerPoint's typeface attribute)."""
    from .text import face

    try:
        names = face(data[0] if isinstance(data, tuple) else data)[0]["name"]
        return names.getDebugName(16) or names.getDebugName(1) or "Calibri"
    except Exception:  # noqa: BLE001 - unreadable font metadata falls back to a common family
        return "Calibri"


class Slide:
    def __init__(self, exporter, view, number):
        self.exporter, self.view, self.number = exporter, view, number
        self.shapes = []
        self.next_id = 2
        self.images = []  # (rId, media path)
        self.charts = []  # (rId, chart part path)
        self.fallbacks = []
        self.chart_info = []

    def ident(self):
        self.next_id += 1
        return self.next_id - 1

    def color(self, value, opacity=1.0):
        from .design import resolve_color
        from .render import color

        rgba = color(resolve_color(value, self.view.state)) if isinstance(value, str) else value
        alpha = round(rgba[3] / 255 * opacity * 100000)
        hexa = "".join(f"{c:02X}" for c in rgba[:3])
        return f'<a:srgbClr val="{hexa}">' + (f'<a:alpha val="{alpha}"/>' if alpha < 100000 else "") + "</a:srgbClr>", alpha

    def fill(self, value, opacity=1.0):
        xml, alpha = self.color(value, opacity)
        return "<a:noFill/>" if alpha <= 0 else f"<a:solidFill>{xml}</a:solidFill>"

    def xfrm(self, layer, bounds, emu, tag="a:xfrm", child=None, frame=None):
        """Position, size and rotation. ``frame`` = (dx, dy, width, height) places a box other than
        the layer's own, in the layer's unrotated coordinates (a text frame around its ink)."""
        from .render import rest_size

        x, y, w, h = bounds
        rw, rh = rest_size(layer)
        cx, cy = x + w / 2, y + h / 2
        if frame:
            dx, dy, fw, fh = frame
            ox, oy = dx + fw / 2 - rw / 2, dy + fh / 2 - rh / 2
            ox, oy = (-ox if layer.get("flip_x") else ox), (-oy if layer.get("flip_y") else oy)
            angle = math.radians(layer.get("rotation", 0))
            cx += ox * math.cos(angle) - oy * math.sin(angle)
            cy += ox * math.sin(angle) + oy * math.cos(angle)
            rw, rh = fw, fh
        attrs = ""
        if layer.get("rotation", 0) % 360:
            attrs += f' rot="{round(layer["rotation"] % 360 * 60000)}"'
        if layer.get("flip_x"):
            attrs += ' flipH="1"'
        if layer.get("flip_y"):
            attrs += ' flipV="1"'
        inner = (f'<a:off x="{round((cx - rw / 2) * emu)}" y="{round((cy - rh / 2) * emu)}"/>'
                 f'<a:ext cx="{max(1, round(rw * emu))}" cy="{max(1, round(rh * emu))}"/>')
        if child:
            inner += f'<a:chOff x="0" y="0"/><a:chExt cx="{max(1, round(child[0] * emu))}" cy="{max(1, round(child[1] * emu))}"/>'
        return f"<{tag}{attrs}>{inner}</{tag}>"

    def layers(self, layers, bounds, parent, emu, index):
        out = []
        for layer in layers:
            if layer.get("parent") != parent or not layer["visible"] or layer["opacity"] <= 0:
                continue
            from .affine import precise
            from .pdf_export import PageBuilder

            reason = PageBuilder.raster_reason(layer)
            if reason is None and precise(layer):
                # DrawingML transforms hold only rotation and flips; a skewed or affine layer is drawn as a picture.
                reason = "skew" if layer.get("skew_x") or layer.get("skew_y") else "affine transform"
            if reason is None and layer["type"] == "group":
                if "chart" in layer:
                    from .chart_pptx import shapes as chart_shapes

                    native = chart_shapes(self, layer, bounds, emu, layers, index)
                    if native is not None:
                        out.extend(native)
                        continue
                children = self.layers(layers, bounds, layer["id"], emu, index)
                ident = self.ident()
                out.append(f'<p:grpSp><p:nvGrpSpPr><p:cNvPr id="{ident}" name={_attr(layer["name"])}/><p:cNvGrpSpPr/>'
                           f'<p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
                           f'{self.xfrm(layer, bounds[layer["id"]], emu, child=(layer["content_width"], layer["content_height"]))}'
                           f'</p:grpSpPr>{"".join(children)}</p:grpSp>')
                continue
            xml = None
            if reason is None:
                try:
                    xml = self.leaf(layer, bounds[layer["id"]], emu)
                except Unsupported as exc:
                    reason = str(exc)
            if xml is None:
                xml = self.picture(layer, bounds, emu, index, parent, reason)
            if xml:
                out.append(xml)
        return out

    def picture(self, layer, bounds, emu, index, parent, reason):
        from .render import ink_origin, layer_ink, layer_surface

        if layer["type"] not in ("raster", "frame") or reason != "image":
            self.fallbacks.append({"layer": layer["name"], "reason": reason})
        if layer.get("styles") or layer.get("clip"):
            parent_layer = index.get(parent)
            size = ((parent_layer["content_width"], parent_layer["content_height"]) if parent_layer else
                    (self.view.state["canvas"]["width"], self.view.state["canvas"]["height"]))
            tile = layer_surface(self.view, layer, bounds, size, index)
            box = tile.getchannel("A").getbbox()
            if not box:
                return None
            image, (x, y) = tile.crop(box), box[:2]
        else:
            image = layer_ink(self.view, layer, bounds[layer["id"]])
            x, y = ink_origin(image, bounds[layer["id"]])
        rid = self.exporter.media(self, image)
        ident = self.ident()
        return (f'<p:pic><p:nvPicPr><p:cNvPr id="{ident}" name={_attr(layer["name"])} descr={_attr(layer["name"])}/>'
                f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                f'<p:spPr><a:xfrm><a:off x="{round(x * emu)}" y="{round(y * emu)}"/>'
                f'<a:ext cx="{max(1, round(image.width * emu))}" cy="{max(1, round(image.height * emu))}"/></a:xfrm>'
                f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')

    def leaf(self, layer, bounds, emu):
        frame = None
        kind = layer["type"]
        ident = self.ident()
        opacity = layer["opacity"]
        name = _attr(layer["name"])
        if kind == "text":
            return self.text(layer, bounds, emu, ident)
        if kind == "solid":
            geometry, fill, line = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>', self.fill(layer["fill"], opacity), "<a:ln><a:noFill/></a:ln>"
        elif kind == "gradient":
            geometry = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            fill, line = self.gradient(layer, opacity), "<a:ln><a:noFill/></a:ln>"
        elif kind == "field":
            raise Unsupported("form field")
        elif kind == "pathfinder":
            from .design import resolve_color
            from .pathfinder_geometry import Unsupported as NoGeometry, pathfinder_commands
            from .render import color

            try:
                commands = pathfinder_commands(layer, self.view.state)
            except NoGeometry as exc:
                raise Unsupported(f"pathfinder: {exc}") from exc
            geometry = self.custom_geometry(commands, (layer["width"], layer["height"]))
            fill = self.fill((*color(resolve_color(layer.get("fill", "white"), self.view.state))[:3], 255), opacity)
            line = "<a:ln><a:noFill/></a:ln>"
        else:
            from .geometry import default_fill
            from .render import rest_size

            stroke_xml, stroke_alpha = self.color(layer.get("stroke", "transparent"), opacity)
            width = layer.get("stroke_width", 1)
            # Vixl pads a stroked shape's box by half the stroke and strokes inside the padded box;
            # PowerPoint centres strokes on the outline, so inset the outline to match (as the PDF
            # writer does).
            pad = width / 2 if stroke_alpha > 0 else 0
            inset = {"rectangle": 2 * pad, "rounded-rectangle": 2 * pad, "capsule": 2 * pad, "ellipse": 2 * pad,
                     "path": 0, "arc": 0}.get(layer["shape"], pad)
            rw, rh = rest_size(layer)
            if inset and min(rw, rh) - 2 * inset >= 1:
                frame = (inset, inset, rw - 2 * inset, rh - 2 * inset)
            geometry = self.geometry(layer, pad)
            fill = self.fill(default_fill(layer), opacity)
            if layer["shape"] == "line":
                fill = "<a:noFill/>"
                if stroke_alpha <= 0:
                    stroke_xml, stroke_alpha = self.color(layer.get("fill", "white"), opacity)
            if stroke_alpha > 0 and width > 0:
                cap = {"round": ' cap="rnd"', "square": ' cap="sq"'}.get(layer.get("line_cap"), "")
                if layer["shape"] == "path":
                    view = layer.get("path_view", (layer["width"], layer["height"]))
                    width = width * min(layer["width"] / view[0], layer["height"] / view[1])
                line = f'<a:ln w="{max(1, round(width * emu))}"{cap}><a:solidFill>{stroke_xml}</a:solidFill>' + (
                    "<a:round/>" if cap == ' cap="rnd"' else "") + "</a:ln>"
            else:
                line = "<a:ln><a:noFill/></a:ln>"
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="{ident}" name={name}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
                f'<p:spPr>{self.xfrm(layer, bounds, emu, frame=frame)}{geometry}{fill}{line}</p:spPr></p:sp>')

    def geometry(self, layer, pad=0.0):
        from .geometry import parse_path, shape_path

        shape = layer["shape"]
        w, h = layer["width"], layer["height"]
        if shape == "rectangle":
            return '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        if shape in ("rounded-rectangle", "capsule"):
            radius = layer.get("radius", min(w, h) / (2 if shape == "capsule" else 5)) - pad
            adj = max(0, min(50000, round(radius / max(1e-9, min(w, h) - 4 * pad) * 100000)))
            return f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val {adj}"/></a:avLst></a:prstGeom>'
        if shape == "ellipse":
            return '<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
        if shape == "line":
            return '<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        path, view = shape_path(layer)
        return self.custom_geometry(parse_path(path), view)

    @staticmethod
    def custom_geometry(parsed, view):
        """Custom geometry for path commands (M L C Q Z) in a ``view`` box; subpaths share one path."""
        scale = 100
        commands = []
        current = (0.0, 0.0)
        for command, values in parsed:
            pts = [(round(x * scale), round(y * scale)) for x, y in zip(values[0::2], values[1::2])]
            if command == "M":
                commands.append(f'<a:moveTo><a:pt x="{pts[0][0]}" y="{pts[0][1]}"/></a:moveTo>')
                current = (values[0], values[1])
            elif command == "L":
                commands.append(f'<a:lnTo><a:pt x="{pts[0][0]}" y="{pts[0][1]}"/></a:lnTo>')
                current = (values[0], values[1])
            elif command == "C":
                commands.append("<a:cubicBezTo>" + "".join(f'<a:pt x="{x}" y="{y}"/>' for x, y in pts) + "</a:cubicBezTo>")
                current = (values[4], values[5])
            elif command == "Q":
                raw = list(zip(values[0::2], values[1::2]))
                controls, end = raw[:-1], raw[-1]
                for i, ctrl in enumerate(controls):
                    nxt = controls[i + 1] if i + 1 < len(controls) else None
                    target = ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2) if nxt else end
                    c1 = (current[0] + 2 / 3 * (ctrl[0] - current[0]), current[1] + 2 / 3 * (ctrl[1] - current[1]))
                    c2 = (target[0] + 2 / 3 * (ctrl[0] - target[0]), target[1] + 2 / 3 * (ctrl[1] - target[1]))
                    commands.append("<a:cubicBezTo>" + "".join(f'<a:pt x="{round(x * scale)}" y="{round(y * scale)}"/>'
                                                               for x, y in (c1, c2, target)) + "</a:cubicBezTo>")
                    current = target
            elif command == "Z":
                commands.append("<a:close/>")
        return (f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/><a:pathLst>'
                f'<a:path w="{round(view[0] * scale)}" h="{round(view[1] * scale)}">{"".join(commands)}</a:path>'
                f'</a:pathLst></a:custGeom>')

    def gradient(self, layer, opacity):
        from .design import gradient_stops

        stops = gradient_stops(layer, self.view.state)
        direction = layer.get("direction", "vertical")
        if direction == "radial":
            # A circle path gradient reaches 100% at the ellipse through the box corners, which is
            # sqrt(2) times the inscribed ellipse every other renderer ends at (for any aspect ratio).
            # Scaling the stops in and padding with the last color makes PowerPoint end where they do.
            stops = [{**stop, "offset": stop["offset"] / math.sqrt(2)} for stop in stops]
            stops.append({"offset": 1, "color": stops[-1]["color"]})
        items = "".join(f'<a:gs pos="{round(stop["offset"] * 100000)}">{self.color(stop["color"], opacity)[0]}</a:gs>'
                        for stop in stops)
        if direction == "radial":
            shade = '<a:path path="circle"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/></a:path>'
        else:
            angle = {"vertical": 90, "horizontal": 0}.get(direction, layer.get("angle", 0)) % 360
            shade = f'<a:lin ang="{round(angle * 60000)}" scaled="0"/>'
        return f'<a:gradFill rotWithShape="1"><a:gsLst>{items}</a:gsLst>{shade}</a:gradFill>'

    def text(self, layer, bounds, emu, ident):
        from .richtext import active

        if (layer.get("text_layout") or {}).get("warp", "none") != "none" or (layer.get("text_layout") or {}).get("path"):
            raise Unsupported("warped text")
        pt = emu / 12700
        boxed = "width" in (layer.get("text_layout") or {})
        paragraphs, first_top, pen_left = (self.rich_paragraphs(layer, pt) if active(layer) else self.plain_paragraphs(layer, pt))
        from .render import rest_size

        w, h = rest_size(layer)
        title = self.exporter.title_ids.get(self.number) == layer["id"]
        left, width = 0.0, w
        if not boxed:
            # Unboxed text gets a wrapping frame with room to spare on the side its alignment grows
            # toward: applications disagree on where unwrapped text sits inside a wider frame
            # (LibreOffice centres it), but all of them honour alignment in a wrapping one.
            extra = max(w * 0.25, float(layer.get("size", 48)) * 1.5)
            align = layer.get("align", "left")
            left -= extra / 2 if align == "center" else extra if align == "right" else pen_left
            width += extra
        xfrm = self.xfrm(layer, bounds, emu, frame=(left, first_top, width, max(1.0, h - first_top)))
        ph = '<p:nvPr><p:ph type="title"/></p:nvPr>' if title else "<p:nvPr/>"
        locks = '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>' if title else '<p:cNvSpPr txBox="1"/>'
        stroke = ""
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="{ident}" name={_attr(layer["name"])}/>{locks}{ph}</p:nvSpPr>'
                f'<p:spPr>{xfrm}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>{stroke}</p:spPr>'
                f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" anchor="t">'
                f'<a:noAutofit/></a:bodyPr><a:lstStyle/>{"".join(paragraphs)}</p:txBody></p:sp>')

    def run(self, text, size_pt, rgba, font, style, opacity):
        attrs = f' lang="en-US" sz="{max(100, min(400000, round(size_pt * 100)))}"'
        if style.get("bold"):
            attrs += ' b="1"'
        if style.get("italic"):
            attrs += ' i="1"'
        if style.get("underline"):
            attrs += ' u="sng"'
        if style.get("strike"):
            attrs += ' strike="sngStrike"'
        if style.get("baseline") == "super":
            attrs += ' baseline="30000"'
        elif style.get("baseline") == "sub":
            attrs += ' baseline="-25000"'
        if style.get("tracking"):
            attrs += f' spc="{round(style["tracking"] * 100)}"'
        fill_xml, _ = self.color(rgba, opacity)
        highlight = f"<a:highlight>{self.color(style['highlight'])[0]}</a:highlight>" if style.get("highlight") else ""
        face = _attr(font)
        return (f'<a:r><a:rPr{attrs} dirty="0"><a:solidFill>{fill_xml}</a:solidFill>{highlight}'
                f'<a:latin typeface={face}/><a:ea typeface={face}/><a:cs typeface={face}/></a:rPr>'
                f'<a:t>{_text(text)}</a:t></a:r>')

    def font_runs(self, text, data, size_pt, rgba, style, opacity):
        """Runs for ``text``, split where characters fall back to another font of ``data`` (a
        fallback chain), so each run names the face that draws it, as PNG, SVG and PDF do."""
        from .text import font_runs

        pieces = font_runs(data, text) if isinstance(data, tuple) else [(data, text)]
        return "".join(self.run(piece, size_pt, rgba, self.exporter.font(font), style, opacity) for font, piece in pieces)

    def plain_paragraphs(self, layer, pt):
        from .design import resolve_color
        from .render import color
        from .text import face, font_data, plan

        data = font_data(self.view, layer)
        self.exporter.font(data)
        rgba = color(resolve_color(layer.get("color", "white"), self.view.state))
        layout = plan(self.view, layer)
        size = layout.size
        outline = face(data[0] if isinstance(data, tuple) else data)[0]
        upem = outline["head"].unitsPerEm
        natural = (outline["hhea"].ascent - outline["hhea"].descent) * size / upem
        line = natural + layer.get("spacing", 4)
        # Exact line spacing puts the extra leading above each line, so a frame's first baseline
        # sits one line pitch minus the descent below its top. The layer's box starts at the ink
        # top, box[1] below the line top where Vixl puts the first baseline one ascent down.
        first_top = -layout.box[1] - layer.get("spacing", 4)
        pen_left = layout.box[0] if layer.get("align", "left") == "left" else 0
        align = {"left": "l", "center": "ctr", "right": "r"}[layer.get("align", "left")]
        # A bold or italic registered face (inter-700, inter-400-italic) is the style of plain text too.
        font = layer.get("font", "DejaVuSans.ttf")
        span = {"font": self.view.state.get("fonts", {}).get(font, font)}
        style = {"bold": self.exporter.is_bold(span), "italic": self.exporter.is_italic(span)}
        out = []
        for text in layer["text"].split("\n"):
            run = self.font_runs(text, data, size * pt, rgba, style, layer["opacity"]) if text else ""
            out.append(f'<a:p><a:pPr algn="{align}"><a:lnSpc><a:spcPts val="{round(line * pt * 100)}"/></a:lnSpc>'
                       f'<a:buNone/></a:pPr>{run}<a:endParaRPr lang="en-US" sz="{round(size * pt * 100)}" dirty="0"/></a:p>')
        return out, first_top, pen_left

    def rich_paragraphs(self, layer, pt):
        from .richtext import _paragraphs, fitted, styled_spans

        result = fitted(self.view, layer)
        scale = result.size_scale
        spans = styled_spans(self.view, layer)
        settings = layer["rich"].get("paragraphs") or []
        rich = layer["rich"]
        base = float(layer.get("size", 48)) * scale
        list_indent = float(rich["list_indent"]) * scale if rich.get("list_indent") else base * 1.4
        # Size-based leading (line_basis "size") is the whole pitch; the layer's pixel spacing does not add.
        gap = 0.0 if rich.get("line_basis") == "size" else float(layer.get("spacing", 0)) * scale
        out = []
        counters = {}
        for index, paragraph in enumerate(_paragraphs(spans)):
            para = settings[index] if index < len(settings) else {}
            kind, level = para.get("list", "none"), para.get("level", 0)
            align = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}[para.get("align", layer.get("align", "left"))]
            left = float(para.get("indent", 0)) * scale + (level * list_indent if kind != "none" or level else 0)
            attrs = f' algn="{align}"'
            bullet = "<a:buNone/>"
            if kind != "none":
                attrs += f' marL="{round((left + list_indent) * pt * 12700)}" indent="{-round(list_indent * pt * 12700)}" lvl="{level}"'
                if kind == "bullet":
                    from .richtext import BULLETS

                    bullet = f'<a:buFont typeface="Arial"/><a:buChar char={_attr(BULLETS[level % len(BULLETS)])}/>'
                else:
                    scheme = ("arabicPeriod", "alphaLcPeriod", "romanLcPeriod")[level % 3]
                    start = para.get("start", 1) if (level, kind) not in counters else None
                    counters[(level, kind)] = True
                    bullet = f'<a:buAutoNum type="{scheme}"' + (f' startAt="{start}"' if start and start != 1 else "") + "/>"
            elif left:
                attrs += f' marL="{round(left * pt * 12700)}"'
            row = next((line for line in result.lines if line[3] == index), None)
            pitch = (row[2] if row else base * 1.2) + gap
            spacing = f'<a:lnSpc><a:spcPts val="{round(pitch * pt * 100)}"/></a:lnSpc>'
            before = float(para.get("space_before", 0)) * scale
            after = float(para["space_after"]) * scale if "space_after" in para else float(rich.get("paragraph_spacing", 0)) * scale
            spacing += f'<a:spcBef><a:spcPts val="{round(before * pt * 100)}"/></a:spcBef>'
            spacing += f'<a:spcAft><a:spcPts val="{round(after * pt * 100)}"/></a:spcAft>'
            runs = []
            for span in paragraph:
                style = {"bold": span["fake_bold"] or self.exporter.is_bold(span), "italic": span["fake_italic"] or self.exporter.is_italic(span),
                         "underline": span["underline"], "strike": span["strike"], "baseline": span["baseline"],
                         "tracking": span["tracking"] * pt,
                         "highlight": span["highlight"]}
                from .richtext import style_font_data

                data = style_font_data(self.view, self.exporter.base_font(span["font"]), span["text"])
                runs.append(self.font_runs(span["text"], data, span["size"] * scale * pt, span["color"], style, layer["opacity"]))
            out.append(f'<a:p><a:pPr{attrs}>{spacing}{bullet}</a:pPr>{"".join(runs)}'
                       f'<a:endParaRPr lang="en-US" sz="{round(base * pt * 100)}" dirty="0"/></a:p>')
        first_top = 0.0
        if result.lines:
            top, baseline, height, first, descent = result.lines[0]
            before = float((settings[first] if first < len(settings) else {}).get("space_before", 0)) * scale
            first_top = baseline - (height + gap) - descent - before
        return out, first_top, 0.0


class Unsupported(Exception):
    """A layer PowerPoint draws as a picture instead."""


class Exporter:
    def __init__(self, project):
        self.project = project
        self.media_files = {}
        self.charts = []  # (chart XML, embedded workbook) per native chart, numbered from 1
        self.fonts_used = set()
        self.title_ids = {}
        self._families = {}
        self._family_data = {}  # family name -> font bytes, for the embedding report
        self._styles = {}

    def media(self, slide, image):
        import hashlib

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        data = buffer.getvalue()
        key = hashlib.sha256(data).hexdigest()
        if key not in self.media_files:
            self.media_files[key] = (f"ppt/media/image{len(self.media_files) + 1}.png", data)
        target = self.media_files[key][0]
        existing = next((rid for rid, path in slide.images if path == target), None)
        if existing:
            return existing
        rid = f"rId{len(slide.images) + 3}"
        slide.images.append((rid, target))
        return rid

    def chart(self, slide, xml, workbook):
        """Register a native chart part for ``slide``; returns the slide relationship ID."""
        self.charts.append((xml, workbook))
        rid = f"rIdChart{len(self.charts)}"
        slide.charts.append((rid, f"ppt/charts/chart{len(self.charts)}.xml"))
        return rid

    def font(self, data):
        import hashlib

        primary = data[0] if isinstance(data, tuple) else data
        key = hashlib.sha256(primary).hexdigest()
        if key not in self._families:
            self._families[key] = family_name(primary)
            self._family_data.setdefault(self._families[key], primary)
        self.fonts_used.add(self._families[key])
        return self._families[key]

    def font_warnings(self):
        """(families, warnings) for the fonts a deck needs that its viewers may not have.

        PowerPoint embeds fonts as Embedded OpenType parts (``ppt/fonts/*.fntdata`` listed in
        ``p:embeddedFontLst``). Vixl does not write them: only PowerPoint itself decides whether such
        a part is acceptable (python-pptx ignores it), and a malformed one makes PowerPoint offer to
        repair the file. A missing font is substituted, which moves text, so each one is named, with
        its OS/2 embedding permission and, for open-licensed fonts, the license that allows installing it."""
        from .fonts import embedding, license_name

        families = sorted(self.fonts_used - COMMON_FONTS)
        details, warnings = {}, []
        for family in families:
            data = self._family_data.get(family)
            info = {"embedding": embedding(data) if data else "unknown"}
            if data and (found := license_name(data)):
                info["license"] = found
            details[family] = info
            hint = ("it is open-licensed (" + info["license"] + "), so install it on the presenting machine (Google Fonts) "
                    if "license" in info else "install it wherever the deck is opened ")
            warnings.append(f"Font {family!r} is not embedded in the PPTX (Vixl cannot embed fonts in PowerPoint files; "
                            f"embedding: {info['embedding']}): {hint}or share the PDF, which embeds its fonts")
        return families, warnings, details

    def _registered(self, font):
        from .richtext import _registered_name

        return _registered_name(self.project.state, font) or ""

    def face_style(self, font):
        """(weight, italic) read from the font file itself, for faces imported under any name."""
        from .text import face, primary_font_data

        try:
            outline = face(primary_font_data(self.project, {"font": font}))[0]
        except Exception:  # noqa: BLE001 - an unreadable face is treated as regular
            return 400, False
        if "OS/2" in outline:
            return outline["OS/2"].usWeightClass, bool(outline["OS/2"].fsSelection & 1)
        return 400, bool("post" in outline and outline["post"].italicAngle)

    def is_bold(self, span):
        import re

        match = re.fullmatch(r".+-(\d{3})(-italic)?", self._registered(span["font"]))
        if match:
            return int(match[1]) >= 600
        return self.face_style(span["font"])[0] >= 600

    def is_italic(self, span):
        import re

        name = self._registered(span["font"])
        if re.fullmatch(r".+-\d{3}(-italic)?", name):
            return name.endswith("-italic")
        return self.face_style(span["font"])[1]

    def base_font(self, font):
        """The regular face of a registered bold/italic variant (PowerPoint applies b/i itself)."""
        import re

        name = self._registered(font)
        match = re.fullmatch(r"(.+)-(\d{3})(-italic)?", name)
        fonts = self.project.state.get("fonts", {})
        if match:
            for candidate in (f"{match[1]}-400", f"{match[1]}-{match[2]}"):
                if candidate in fonts:
                    return fonts[candidate]
        return font


def emu_per_pixel(canvas, dpi=None):
    """EMU per canvas pixel: an explicit ``dpi``, else the canvas dpi, else a screen document is a
    standard slide, 7.5 inches tall (``deck_dpi``; the PDF of a multi-page document uses the same)."""
    from .pdf_export import deck_dpi

    return 914400 / (dpi or canvas.get("dpi") or deck_dpi(canvas))


def export_pptx(project, path=None, *, pages=None, dpi=None, report=None):
    """Write a .pptx with one slide per page. Returns the bytes. ``dpi`` sets the pixels per inch
    of the slides (default: the canvas dpi, or 7.5 inches tall for a screen canvas)."""
    from .deck import title_layer
    from .model import finite
    from .pdf_export import page_views
    from .render import resolve_layout, resolved_layers

    canvas = project.state["canvas"]
    emu = emu_per_pixel(canvas, finite(dpi, "dpi", 36, 2400) if dpi else None)
    cx, cy = round(canvas["width"] * emu), round(canvas["height"] * emu)
    require(914400 <= cx <= 51206400 and 914400 <= cy <= 51206400,
            "PowerPoint slides must be 1–56 inches on each side; give the canvas a dpi", field="canvas")
    exporter = Exporter(project)
    records = []
    if project.state.get("pages"):
        from .pages import find_page, page_list

        records = [find_page(project.state, ref, "pages") for ref in pages] if pages else page_list(project)
    views = page_views(project, [r["id"] for r in records] if records else pages)
    slides, notes = [], []
    for number, (label, view) in enumerate(views, 1):
        from .export_appearance import prepare

        view = prepare(view)
        slide = Slide(exporter, view, number)
        layers = resolved_layers(view)
        bounds = resolve_layout(view, layers=layers)
        title = title_layer(view, layers)
        if title:
            exporter.title_ids[number] = title["id"]
        index = {item["id"]: item for item in layers}
        shapes = slide.layers(layers, bounds, None, emu, index)
        record = records[number - 1] if records else {}
        background = view.state["canvas"]["background"]
        from .design import resolve_color
        from .render import color

        rgba = color(resolve_color(background, view.state))
        bg = (f"<p:bg><p:bgPr>{slide.fill(rgba if rgba[3] else (255, 255, 255, 255))}<a:effectLst/></p:bgPr></p:bg>")
        transition = TRANSITIONS.get(record.get("transition", ""), "")
        show = ' show="0"' if record.get("hidden") else ""
        xml = (f"{XML}<p:sld {NS}{show}><p:cSld name={_attr(label)}>{bg}<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/>"
               f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
               f"<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>{''.join(shapes)}</p:spTree></p:cSld>"
               f"<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>"
               + (f'<p:transition spd="med">{transition}</p:transition>' if transition else "") + "</p:sld>")
        slides.append((xml, slide))
        notes.append(record.get("notes", ""))
    files = package(project, exporter, slides, notes, cx, cy)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    data = stream.getvalue()
    if report is not None:
        report.update(slides=len(slides), page_size={"width": round(cx / 914400, 3), "height": round(cy / 914400, 3),
                                                    "unit": "in"},
                      fonts=sorted(exporter.fonts_used),
                      raster_fallbacks={str(i): s.fallbacks for i, (_, s) in enumerate(slides, 1) if s.fallbacks},
                      notes=sum(1 for n in notes if n))
        families, warnings, details = exporter.font_warnings()
        if warnings:
            report.update(fonts_not_embedded=families, font_embedding=details, warnings=warnings)
        charts = {str(i): s.chart_info for i, (_, s) in enumerate(slides, 1) if s.chart_info}
        if charts:
            report["charts"] = charts
    if path:
        Path(path).write_bytes(data)
    return data


def package(project, exporter, slides, notes, cx, cy):
    """Every part of the package, in a fixed order."""
    count = len(slides)
    files = []
    overrides = [
        ("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
        ("/ppt/slideLayouts/slideLayout1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
        ("/ppt/notesMasters/notesMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
        ("/ppt/theme/theme2.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
        ("/ppt/presProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"),
        ("/ppt/viewProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"),
        ("/ppt/tableStyles.xml", "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    ]
    for i in range(1, count + 1):
        overrides.append((f"/ppt/slides/slide{i}.xml", "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"))
        overrides.append((f"/ppt/notesSlides/notesSlide{i}.xml",
                          "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"))
    from .chart_pptx import content_types as chart_types, files as chart_files

    chart_default, chart_overrides = chart_types(exporter)
    types = (f'{XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
             + chart_default + "".join(f'<Override PartName="{name}" ContentType="{kind}"/>' for name, kind in overrides)
             + chart_overrides + "</Types>")
    files.append(("[Content_Types].xml", types))
    files.append(("_rels/.rels", rels([
        ("rId1", f"{REL}/officeDocument", "ppt/presentation.xml"),
        ("rId2", f"{DOC_REL}/metadata/core-properties", "docProps/core.xml"),
        ("rId3", f"{REL}/extended-properties", "docProps/app.xml")])))
    title = ""
    for layer in project.state["layers"]:
        if layer["type"] == "text" and layer.get("visible", True):
            title = layer.get("text", "")[:200]
            break
    files.append(("docProps/core.xml", f'{XML}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                  'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                  'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                  f"<dc:title>{_text(title)}</dc:title><dc:creator>Vixl</dc:creator></cp:coreProperties>"))
    files.append(("docProps/app.xml", f'{XML}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                  f"<Application>Vixl</Application><Slides>{count}</Slides><Notes>{sum(1 for n in notes if n)}</Notes></Properties>"))
    presentation_rels = [("rId1", f"{REL}/slideMaster", "slideMasters/slideMaster1.xml"),
                         ("rId2", f"{REL}/notesMaster", "notesMasters/notesMaster1.xml"),
                         ("rId3", f"{REL}/theme", "theme/theme1.xml"),
                         ("rId4", f"{REL}/presProps", "presProps.xml"),
                         ("rId5", f"{REL}/viewProps", "viewProps.xml"),
                         ("rId6", f"{REL}/tableStyles", "tableStyles.xml")]
    presentation_rels += [(f"rId{10 + i}", f"{REL}/slide", f"slides/slide{i}.xml") for i in range(1, count + 1)]
    files.append(("ppt/_rels/presentation.xml.rels", rels(presentation_rels)))
    slide_ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{10 + i}"/>' for i in range(1, count + 1))
    files.append(("ppt/presentation.xml", f"{XML}<p:presentation {NS} saveSubsetFonts=\"1\">"
                  '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                  '<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>'
                  f"<p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx=\"{cx}\" cy=\"{cy}\"/>"
                  '<p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr>'
                  "</p:defaultTextStyle></p:presentation>"))
    files.append(("ppt/presProps.xml", f"{XML}<p:presentationPr {NS}/>"))
    files.append(("ppt/viewProps.xml", f"{XML}<p:viewPr {NS}><p:normalViewPr><p:restoredLeft sz=\"15620\"/>"
                  '<p:restoredTop sz="94660"/></p:normalViewPr><p:gridSpacing cx="76200" cy="76200"/></p:viewPr>'))
    files.append(("ppt/tableStyles.xml", f'{XML}<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                  'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'))
    files.append(("ppt/theme/theme1.xml", THEME))
    files.append(("ppt/theme/theme2.xml", THEME))
    files.append(("ppt/slideMasters/slideMaster1.xml", master_xml(cx, cy)))
    files.append(("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels([
        ("rId1", f"{REL}/slideLayout", "../slideLayouts/slideLayout1.xml"), ("rId2", f"{REL}/theme", "../theme/theme1.xml")])))
    files.append(("ppt/slideLayouts/slideLayout1.xml", layout_xml(cx, cy)))
    files.append(("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels([
        ("rId1", f"{REL}/slideMaster", "../slideMasters/slideMaster1.xml")])))
    files.append(("ppt/notesMasters/notesMaster1.xml", notes_master_xml()))
    files.append(("ppt/notesMasters/_rels/notesMaster1.xml.rels", rels([("rId1", f"{REL}/theme", "../theme/theme2.xml")])))
    for i, ((xml, slide), text) in enumerate(zip(slides, notes), 1):
        files.append((f"ppt/slides/slide{i}.xml", xml))
        slide_rels = [("rId1", f"{REL}/slideLayout", "../slideLayouts/slideLayout1.xml"),
                      ("rId2", f"{REL}/notesSlide", f"../notesSlides/notesSlide{i}.xml")]
        slide_rels += [(rid, f"{REL}/image", "../" + target[4:]) for rid, target in slide.images]
        slide_rels += [(rid, f"{REL}/chart", "../" + target[4:]) for rid, target in slide.charts]
        files.append((f"ppt/slides/_rels/slide{i}.xml.rels", rels(slide_rels)))
        files.append((f"ppt/notesSlides/notesSlide{i}.xml", notes_xml(text)))
        files.append((f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", rels([
            ("rId1", f"{REL}/notesMaster", "../notesMasters/notesMaster1.xml"),
            ("rId2", f"{REL}/slide", f"../slides/slide{i}.xml")])))
    for target, data in exporter.media_files.values():
        files.append((target, data))
    files.extend(chart_files(exporter))
    return files


def rels(items):
    body = "".join(f'<Relationship Id="{rid}" Type="{kind}" Target="{target}"/>' for rid, kind, target in items)
    return f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'


def _placeholder(ident, name, kind, x, y, w, h, extra=""):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{ident}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr><p:ph type="{kind}"{extra}/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>')


EMPTY_TREE = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
              '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


def master_xml(cx, cy):
    margin = cx // 16
    title = _placeholder(2, "Title Placeholder 1", "title", margin, cy // 16, cx - 2 * margin, cy // 6)
    body = _placeholder(3, "Text Placeholder 2", "body", margin, cy // 4, cx - 2 * margin, cy // 2, ' idx="1"')
    level = '<a:defRPr sz="{size}" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+{f}-lt"/></a:defRPr>'
    return (f"{XML}<p:sldMaster {NS}><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg>"
            f"<p:spTree>{EMPTY_TREE}{title}{body}</p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
            'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            f'<p:txStyles><p:titleStyle><a:lvl1pPr algn="l">{level.format(size=4400, f="mj")}</a:lvl1pPr></p:titleStyle>'
            f'<p:bodyStyle><a:lvl1pPr marL="228600" indent="-228600">{level.format(size=2800, f="mn")}</a:lvl1pPr></p:bodyStyle>'
            f'<p:otherStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr></p:otherStyle></p:txStyles></p:sldMaster>')


def layout_xml(cx, cy):
    return (f'{XML}<p:sldLayout {NS} type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>{EMPTY_TREE}</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')


def notes_master_xml():
    image = _placeholder(2, "Slide Image Placeholder 1", "sldImg", 381000, 685800, 6096000, 3429000, ' idx="2"')
    body = _placeholder(3, "Notes Placeholder 2", "body", 685800, 4343400, 5486400, 4114800, ' idx="1"')
    return (f"{XML}<p:notesMaster {NS}><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg>"
            f"<p:spTree>{EMPTY_TREE}{image}{body}</p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
            'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:notesStyle><a:lvl1pPr marL="0" algn="l"><a:defRPr sz="1200" kern="1200"><a:solidFill><a:schemeClr val="tx1"/>'
            '</a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:notesStyle></p:notesMaster>')


def notes_xml(text):
    paragraphs = "".join(f'<a:p><a:r><a:rPr lang="en-US" dirty="0"/><a:t>{_text(line)}</a:t></a:r></a:p>' if line else
                         '<a:p><a:endParaRPr lang="en-US" dirty="0"/></a:p>' for line in (text or "").split("\n"))
    return (f"{XML}<p:notes {NS}><p:cSld><p:spTree>{EMPTY_TREE}"
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" '
            'noChangeAspect="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            f"{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>")


def _theme():
    colors = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "1F2937", "lt2": "F3F4F6", "accent1": "2563EB", "accent2": "DB2777",
              "accent3": "059669", "accent4": "D97706", "accent5": "7C3AED", "accent6": "0891B2", "hlink": "2563EB",
              "folHlink": "7C3AED"}
    scheme = "".join(f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k, v in colors.items())
    font = '<a:latin typeface="{f}"/><a:ea typeface=""/><a:cs typeface=""/>'
    fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    line = '<a:ln w="{w}"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    return (f'{XML}<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Vixl">'
            f'<a:themeElements><a:clrScheme name="Vixl">{scheme}</a:clrScheme>'
            f'<a:fontScheme name="Vixl"><a:majorFont>{font.format(f="Calibri Light")}</a:majorFont>'
            f'<a:minorFont>{font.format(f="Calibri")}</a:minorFont></a:fontScheme>'
            f'<a:fmtScheme name="Vixl"><a:fillStyleLst>{fill * 3}</a:fillStyleLst>'
            f'<a:lnStyleLst>{line.format(w=6350)}{line.format(w=12700)}{line.format(w=19050)}</a:lnStyleLst>'
            '<a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3 + '</a:effectStyleLst>'
            f'<a:bgFillStyleLst>{fill * 3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements>'
            '<a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')


THEME = _theme()
