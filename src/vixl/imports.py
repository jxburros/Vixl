"""Bounded SVG geometry and PDF page imports; unsupported SVG features fail explicitly."""

import math
import re
import xml.etree.ElementTree as ET

from fontTools.misc.transform import Transform, Identity
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path

from .errors import VixlError, require

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def numbers(value):
    require(not re.sub(NUMBER + r"|[\s,]", "", value), "Invalid SVG number list", "unsupported_svg")
    result = list(map(float, re.findall(NUMBER, value)))
    require(
        all(math.isfinite(x) and abs(x) <= 1e6 for x in result),
        "SVG coordinates exceed limits",
        "resource_limit",
    )
    return result


def transform(value):
    result = Identity
    remainder = re.sub(r"([A-Za-z]+)\s*\(([^()]*)\)", "", value)
    require(not remainder.strip(" ,\t\r\n"), "Invalid SVG transform", "unsupported_svg")
    for name, args in re.findall(r"([A-Za-z]+)\s*\(([^()]*)\)", value):
        a = numbers(args)
        if name == "matrix" and len(a) == 6:
            item = Transform(*a)
        elif name == "translate" and len(a) in (1, 2):
            item = Identity.translate(a[0], a[1] if len(a) == 2 else 0)
        elif name == "scale" and len(a) in (1, 2):
            item = Identity.scale(a[0], a[-1])
        elif name == "rotate" and len(a) in (1, 3):
            cx, cy = a[1:] if len(a) == 3 else (0, 0)
            item = Identity.translate(cx, cy).rotate(math.radians(a[0])).translate(-cx, -cy)
        else:
            raise VixlError("unsupported_svg", f"Unsupported SVG transform: {name}")
        result = result.transform(item)
    return result


def svg_operations(data, project, name):
    require(
        len(data) <= min(project.limits.max_asset_bytes, 4 * 1024 * 1024),
        "SVG exceeds byte limit",
        "resource_limit",
    )
    try:
        data = data.decode("utf-8-sig").encode("utf-8")
    except UnicodeError as exc:
        raise VixlError("unsupported_svg", "Save SVG as UTF-8 before importing") from exc
    require(b"\x00" not in data, "Save SVG as UTF-8 before importing", "unsupported_svg")
    require(
        b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
        "SVG declarations/entities are unsupported",
        "unsupported_svg",
    )
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise VixlError("invalid_svg", str(exc)) from exc
    require(root.tag in ("svg", "{http://www.w3.org/2000/svg}svg"), "Expected an SVG root")
    operations = []
    seen = 0
    base = Identity
    if "viewBox" in root.attrib:
        box = numbers(root.attrib["viewBox"])
        require(len(box) == 4 and box[2] > 0 and box[3] > 0, "Invalid SVG viewBox")
        width = length(root.get("width", str(box[2])))
        height = length(root.get("height", str(box[3])))
        require(width > 0 and height > 0, "SVG dimensions must be positive")
        preserve = root.get("preserveAspectRatio", "xMidYMid meet")
        require(
            preserve in ("none", "xMidYMid", "xMidYMid meet"),
            "Unsupported preserveAspectRatio",
            "unsupported_svg",
        )
        sx, sy = width / box[2], height / box[3]
        if preserve != "none":
            sx = sy = min(sx, sy)
        base = (
            Identity.translate((width - box[2] * sx) / 2, (height - box[3] * sy) / 2)
            .scale(sx, sy)
            .translate(-box[0], -box[1])
        )
    inherited_keys = {
        "fill",
        "stroke",
        "stroke-width",
        "fill-opacity",
        "stroke-opacity",
        "fill-rule",
        "display",
        "visibility",
    }
    common = inherited_keys | {"id", "transform", "style", "opacity"}
    geometry_keys = {
        "path": {"d"},
        "rect": {"x", "y", "width", "height", "rx", "ry"},
        "circle": {"cx", "cy", "r"},
        "ellipse": {"cx", "cy", "rx", "ry"},
        "line": {"x1", "y1", "x2", "y2"},
        "polygon": {"points"},
        "polyline": {"points"},
    }

    def walk(node, matrix, inherited, depth=0):
        nonlocal seen
        seen += 1
        require(
            seen <= project.limits.max_operations * 4 and depth <= 64,
            "SVG structure exceeds limits",
            "resource_limit",
        )
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in ("title", "desc", "metadata"):
            return
        require(
            tag in {*geometry_keys, "svg", "g"},
            f"Unsupported SVG element {tag!r}; simplify it to paths before importing",
            "unsupported_svg",
        )
        require(tag != "svg" or depth == 0, "Nested SVG viewports are unsupported", "unsupported_svg")
        attrs = dict(node.attrib)
        style = attrs.pop("style", "")
        for declaration in style.split(";"):
            if declaration.strip():
                require(":" in declaration, "Invalid SVG style")
                k, v = declaration.split(":", 1)
                require(k.strip() in common, f"Unsupported SVG style: {k}", "unsupported_svg")
                attrs[k.strip()] = v.strip()
        allowed = common | geometry_keys.get(tag, set())
        if tag == "svg":
            allowed |= {"width", "height", "viewBox", "version", "preserveAspectRatio"}
        require(
            not set(attrs) - allowed,
            f"Unsupported SVG attributes: {sorted(set(attrs) - allowed)}",
            "unsupported_svg",
        )
        props = {**inherited, **{k: v for k, v in attrs.items() if k in inherited_keys}}
        matrix = matrix.transform(transform(attrs.get("transform", "")))
        if props.get("display") == "none" or props.get("visibility") == "hidden":
            return
        opacity = float(attrs.get("opacity", 1))
        require(math.isfinite(opacity) and 0 <= opacity <= 1, "SVG opacity must be 0–1")
        if tag in ("svg", "g"):
            require(opacity == 1, "Group opacity must be flattened before editable import", "unsupported_svg")
            for child in node:
                walk(child, matrix, props, depth + 1)
            return
        require(not len(node), "SVG shape children are unsupported", "unsupported_svg")

        def get(k, default=0):
            return length(attrs.get(k, str(default)))

        if tag == "path":
            d = attrs.get("d", "")
        elif tag == "rect":
            x, y, w, h = get("x"), get("y"), get("width"), get("height")
            require(
                get("rx") == 0 and get("ry") == 0,
                "Convert rounded rectangles to paths before import",
                "unsupported_svg",
            )
            require(w >= 0 and h >= 0, "SVG rectangle dimensions must be nonnegative")
            d = f"M{x} {y} L{x + w} {y} L{x + w} {y + h} L{x} {y + h} Z"
        elif tag in ("circle", "ellipse"):
            cx, cy = get("cx"), get("cy")
            rx, ry = (get("r"), get("r")) if tag == "circle" else (get("rx"), get("ry"))
            require(rx > 0 and ry > 0, "SVG radii must be positive")
            d = f"M{cx - rx} {cy} A{rx} {ry} 0 1 0 {cx + rx} {cy} A{rx} {ry} 0 1 0 {cx - rx} {cy} Z"
        elif tag == "line":
            d = f"M{get('x1')} {get('y1')} L{get('x2')} {get('y2')}"
        else:
            pts = numbers(attrs.get("points", ""))
            require(len(pts) >= 4 and len(pts) % 2 == 0, "Invalid SVG points")
            d = (
                "M"
                + " L".join(f"{x} {y}" for x, y in zip(pts[::2], pts[1::2]))
                + (" Z" if tag == "polygon" else "")
            )
        require(0 < len(d) <= 32768, "SVG path exceeds limits", "resource_limit")
        pen = RecordingPen()
        try:
            parse_path(d, TransformPen(pen, matrix))
        except (ValueError, IndexError, AssertionError) as exc:
            raise VixlError("invalid_svg", f"Invalid SVG path: {exc}") from exc
        require(len(pen.value) <= 1024, "SVG path exceeds command limit", "resource_limit")
        bounds = BoundsPen(None)
        pen.replay(bounds)
        if bounds.bounds is None:
            return
        x0, y0, x1, y1 = bounds.bounds
        stroke_width = get("stroke-width", props.get("stroke-width", 1))
        # Stroke width is representable only under a similarity transform.
        a, b, c, d, _, _ = matrix
        scale = math.hypot(a, b)
        stroke = props.get("stroke", "none")
        if stroke != "none":
            require(
                abs(scale - math.hypot(c, d)) < 1e-6 and abs(a * c + b * d) < 1e-6,
                "Nonuniform SVG strokes must be outlined before import",
                "unsupported_svg",
            )
        pad = stroke_width * scale / 2 if stroke != "none" else 0
        x0, y0 = math.floor(x0 - pad), math.floor(y0 - pad)
        w, h = max(1, math.ceil(x1 + pad) - x0), max(1, math.ceil(y1 + pad) - y0)
        project.limits.size(w, h)
        commands = []
        for command, points in pen.value:
            if command in ("closePath", "endPath"):
                if command == "closePath":
                    commands.append("Z")
            else:
                letter = {"moveTo": "M", "lineTo": "L", "curveTo": "C", "qCurveTo": "Q"}[command]
                commands.append(letter + " ".join(f"{x - x0:.6g} {y - y0:.6g}" for x, y in points))
        from .colors import parse, hex_of

        def paint(key):
            value = props.get(key, "black" if key == "fill" else "none")
            if value == "none":
                return "transparent"
            rgba = parse(value)
            alpha = float(props.get(key + "-opacity", 1))
            require(math.isfinite(alpha) and 0 <= alpha <= 1, "SVG paint opacity must be 0–1")
            return hex_of((*rgba[:3], rgba[3] * alpha))

        require(
            props.get("fill-rule", "nonzero") == "nonzero",
            "Convert evenodd fill rules to nonzero paths before import",
            "unsupported_svg",
        )
        operations.append(
            {
                "type": "shape",
                "shape": "path",
                "name": attrs.get("id") or f"{name}-{len(operations) + 1}",
                "path": " ".join(commands),
                "width": w,
                "height": h,
                "x": x0,
                "y": y0,
                "fill": paint("fill"),
                "stroke": paint("stroke"),
                "stroke_width": stroke_width * scale,
            }
        )
        if opacity != 1:
            operations.append({"type": "opacity", "value": opacity})
        require(len(operations) <= project.limits.max_operations, "SVG has too many shapes", "resource_limit")

    walk(root, base, {})
    require(operations, "SVG contains no visible geometry")
    return operations


def length(value):
    value = re.sub(r"px$", "", value.strip())
    require(
        re.fullmatch(NUMBER, value) is not None,
        "SVG lengths must use pixels; convert percentages and physical units before import",
        "unsupported_svg",
    )
    number = float(value)
    require(math.isfinite(number) and abs(number) <= 1e6, "SVG length exceeds limits", "resource_limit")
    return number


def import_document(project, data, format, name="import", page=1, dpi=144, svg_mode="editable"):
    require(len(data) <= project.limits.max_asset_bytes, "Import exceeds byte limit", "resource_limit")
    if format.lower() == "svg":
        require(svg_mode in ("editable", "appearance", "auto"), "SVG mode must be editable, appearance or auto")
        if svg_mode == "appearance":
            return svg_appearance(project, data, name)
        try:
            return project.apply(svg_operations(data, project, name), detail="compact")
        except VixlError as exc:
            if svg_mode == "auto" and exc.code == "unsupported_svg":
                return svg_appearance(project, data, name)
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise VixlError("invalid_svg", f"Malformed SVG: {exc}") from exc
    require(format.lower() == "pdf", "Import format must be svg or pdf")
    require(
        isinstance(page, int) and page >= 1 and 36 <= dpi <= 600,
        "PDF page must be positive and dpi must be 36–600",
    )
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[pdf] for PDF import") from exc
    candidate = project.clone()
    try:
        with pdfium.PdfDocument(data) as document:
            require(page <= len(document), "PDF page is out of range")
            source = document[page - 1]
            try:
                w, h = source.get_size()
                candidate.limits.size(math.ceil(w * dpi / 72), math.ceil(h * dpi / 72))
                bitmap = source.render(scale=dpi / 72)
                try:
                    from .assets import add_image

                    asset = add_image(candidate, bitmap.to_pil())
                finally:
                    bitmap.close()
            finally:
                source.close()
    except pdfium.PdfiumError as exc:
        raise VixlError("invalid_pdf", f"Cannot open PDF: {exc}") from exc
    result = candidate.apply({"type": "add", "asset": asset, "name": name}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {
        **result,
        "page": page,
        "dpi": dpi,
        "warnings": ["PDF page imported as a raster layer; use SVG for editable vector geometry."],
    }


def svg_appearance(project, data, name):
    """Render self-contained static SVG through resvg; preserve source for future editing."""
    import base64
    import hashlib
    import io
    import resvg_py
    from PIL import Image
    from .assets import add_image, decode

    require(len(data) <= min(project.limits.max_asset_bytes, 4 * 1024 * 1024), "SVG exceeds byte limit", "resource_limit")
    try:
        text = data.decode("utf-8-sig")
        require("\x00" not in text and "<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(),
                "SVG entities and declarations are unsupported", "unsupported_svg")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as exc:
        raise VixlError("invalid_svg", "Expected UTF-8 SVG XML") from exc
    require(root.tag in ("svg", "{http://www.w3.org/2000/svg}svg"), "Expected SVG root")
    pending, count = [(root, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        require(depth <= 64 and count <= 10000, "SVG structure exceeds limits", "resource_limit")
        pending.extend((child, depth + 1) for child in node)
        tag = node.tag.rsplit("}", 1)[-1]
        require(tag not in ("script", "foreignObject", "animate", "animateMotion", "animateTransform", "set"),
                f"Active SVG element {tag} is unsupported", "unsupported_svg")
        for key, value in node.attrib.items():
            local = key.rsplit("}", 1)[-1]
            require(not local.lower().startswith("on") and local != "base", "Active SVG attributes are unsupported", "unsupported_svg")
            if local == "href":
                if value.startswith("data:image/"):
                    require(tag == "image" and re.match(r"data:image/(png|jpeg|webp);base64,", value), "Embed images as PNG/JPEG/WebP", "unsupported_svg")
                    try:
                        raw = base64.b64decode(value.split(",", 1)[1], validate=True)
                    except ValueError as exc:
                        raise VixlError("invalid_svg", "Invalid embedded image") from exc
                    decode(raw, project.limits)
                else:
                    require(value.startswith("#"), "SVG references must be internal or embedded raster images", "unsupported_svg")
        css = " ".join(node.attrib.values()) + " " + (node.text or "")
        require("@import" not in css.lower() and "\\" not in css, "External or escaped CSS is unsupported", "unsupported_svg")
        for url in re.findall(r"url\s*\((.*?)\)", css, re.I | re.S):
            require(url.strip(" \t\r\n\"'").startswith("#"), "SVG URLs must reference internal IDs", "unsupported_svg")
    box = numbers(root.get("viewBox", "0 0 300 150"))
    require(len(box) == 4 and box[2] > 0 and box[3] > 0, "Invalid viewBox")
    def dimension(value, fallback):
        if value is None or value.endswith("%"):
            return math.ceil(fallback)
        match = re.fullmatch(r"(" + NUMBER + r")(px|pt|pc|in|cm|mm)?", value.strip())
        require(match, "Unsupported SVG dimensions")
        return math.ceil(float(match[1]) * {None: 1, "px": 1, "pt": 96 / 72, "pc": 16, "in": 96, "cm": 96 / 2.54, "mm": 96 / 25.4}[match[2]])
    width, height = dimension(root.get("width"), box[2]), dimension(root.get("height"), box[3])
    project.limits.size(width, height)
    root.set("width", str(width))
    root.set("height", str(height))
    if root.tag == "svg":
        root.set("xmlns", "http://www.w3.org/2000/svg")
    from pathlib import Path
    try:
        encoded = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode"),
                    width=width, height=height, skip_system_fonts=True,
                    font_files=[str(Path(__file__).parent / "data" / "DejaVuSans.ttf")])
        image = Image.open(io.BytesIO(encoded)).convert("RGBA")
    except Exception as exc:
        raise VixlError("invalid_svg", f"Cannot render SVG: {exc}") from exc
    candidate = project.clone()
    source = "sources/" + hashlib.sha256(data).hexdigest() + ".svg"
    candidate.assets[source] = data
    asset = add_image(candidate, image)
    result = candidate.apply({"type": "add", "asset": asset, "name": name,
        "provenance": {"kind": "svg-appearance", "source": source}}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {**result, "source": source, "mode": "appearance", "warnings": [
        "SVG imported as a rendered layer with original source embedded. Geometry is not individually editable; static resvg SVG features only."]}
