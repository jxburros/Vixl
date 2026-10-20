"""Bounded SVG geometry and PDF page imports; unsupported SVG features fail explicitly."""

import math
import re
import xml.etree.ElementTree as ET

from fontTools.misc.transform import Transform, Identity

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


def svg_operations(data, project, name, *, namespace=True):
    """Operations that rebuild an SVG's elements as editable layers (see ``svg_import``); unsupported elements
    fail with ``unsupported_svg``. Every layer name starts with ``name``: the SVG's own labels become
    ``"<name> <label>"`` and unlabelled elements ``"<name>-<kind>"``, so the result can be concatenated with another
    call's (made with a different ``name``) and applied in one batch. ``namespace=False`` keeps the SVG's labels
    as they are."""
    from .svg_import import svg_operations as convert

    return convert(data, project, name, namespace=namespace)


def _gradient_rect(attrs, props, matrix, gradients, name, opacity):
    """Translate a native axis-aligned gradient rectangle without trusting private metadata."""
    from .colors import parse, hex_of
    ref = re.fullmatch(r"url\(#([^()]+)\)", props["fill"])
    gradient = gradients.get(ref.group(1)) if ref else None
    require(gradient is not None, "Unknown SVG gradient reference", "unsupported_svg")
    require(gradient.get("gradientUnits") == "userSpaceOnUse" and gradient.get("spreadMethod", "pad") == "pad",
            "Only user-space, padded gradients are editable", "unsupported_svg")
    require(props.get("stroke", "none") == "none" or float(props.get("stroke-opacity", 1)) == 0,
            "Stroked gradient rectangles require appearance import", "unsupported_svg")
    require(length(attrs.get("rx", "0")) == 0 and length(attrs.get("ry", "0")) == 0,
            "Rounded gradient rectangles require appearance import", "unsupported_svg")
    a, b, c, d, e, f = matrix
    require(abs(a - 1) < 1e-8 and abs(d - 1) < 1e-8 and abs(b) < 1e-8 and abs(c) < 1e-8,
            "Transformed gradient rectangles require appearance import", "unsupported_svg")
    x, y = length(attrs.get("x", "0")), length(attrs.get("y", "0"))
    w, h = length(attrs.get("width", "0")), length(attrs.get("height", "0"))
    require(w > 1 and h > 1, "Gradient rectangle must exceed one pixel", "unsupported_svg")
    stops = []
    for stop in gradient:
        require(stop.tag.rsplit("}", 1)[-1] == "stop" and not len(stop)
                and set(stop.attrib) <= {"offset", "stop-color", "stop-opacity"},
                "Unsupported SVG gradient stop", "unsupported_svg")
        offset = stop.get("offset", "0")
        offset = float(offset[:-1]) / 100 if offset.endswith("%") else float(offset)
        rgba = parse(stop.get("stop-color", "black"))
        alpha = float(stop.get("stop-opacity", 1))
        require(math.isfinite(offset) and 0 <= offset <= 1 and math.isfinite(alpha) and 0 <= alpha <= 1,
                "Invalid SVG gradient stop", "unsupported_svg")
        stops.append({"offset": offset, "color": hex_of((*rgba[:3], rgba[3] * alpha))})
    require(2 <= len(stops) <= 32, "Editable gradients need 2–32 stops", "unsupported_svg")
    result = {"type": "gradient", "name": attrs.get("id") or name + "-gradient", "x": x + e, "y": y + f,
              "width": w, "height": h, "stops": stops,
              "opacity": opacity * float(props.get("fill-opacity", 1))}
    if gradient.tag.rsplit("}", 1)[-1] == "linearGradient":
        require(set(gradient.attrib) <= {"id", "gradientUnits", "spreadMethod", "x1", "y1", "x2", "y2"},
                "Unsupported linear gradient attributes", "unsupported_svg")
        x1, y1, x2, y2 = [length(gradient.get(k, "0")) for k in ("x1", "y1", "x2", "y2")]
        require(abs((x1 + x2) / 2 - x - (w - 1) / 2) < 1e-5
                and abs((y1 + y2) / 2 - y - (h - 1) / 2) < 1e-5,
                "Off-centre linear gradients require appearance import", "unsupported_svg")
        square = (x2 - x1) ** 2 + (y2 - y1) ** 2
        require(square > 0, "Degenerate SVG gradient", "unsupported_svg")
        dx, dy = (x2 - x1) * (w - 1) / square, (y2 - y1) * (h - 1) / square
        require(abs(abs(dx) + abs(dy) - 1) < 1e-5, "Unsupported gradient extent", "unsupported_svg")
        result.update(direction="angled", angle=math.degrees(math.atan2(dy, dx)))
    else:
        require(set(gradient.attrib) <= {"id", "gradientUnits", "spreadMethod", "cx", "cy", "r", "gradientTransform"}
                and length(gradient.get("cx", "0")) == 0 and length(gradient.get("cy", "0")) == 0
                and length(gradient.get("r", "1")) == 1, "Unsupported radial gradient", "unsupported_svg")
        ga, gb, gc, gd, gx, gy = transform(gradient.get("gradientTransform", ""))
        require(abs(ga - w / 2) < 1e-5 and abs(gd - h / 2) < 1e-5 and abs(gb) < 1e-8 and abs(gc) < 1e-8,
                "Unsupported radial gradient extent", "unsupported_svg")
        result.update(direction="radial", center=[(gx - x) / w, (gy - y) / h])
    return result


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


def import_document(project, data, format, name="import", page=1, dpi=None, svg_mode="editable", **options):
    """Import an SVG or a PDF page into ``project`` as one revision.

    SVG: Vixl's own SVG gives back the document it carries (``svg_import``); other SVG becomes editable layers.
    ``svg_mode='auto'`` draws the elements Vixl cannot edit as image layers (and the whole SVG as one image when its
    stylesheet or structure cannot be read); ``'appearance'`` imports the whole SVG as one image with its source kept.
    PDF: see ``pdf_import``. Figma: ``data`` is a file URL or key, or exported file JSON; ``page`` is the Figma
    page (number or name) and ``options`` are ``node_id``, ``rasterize_unsupported`` and ``install_fonts``. For SVG,
    ``install_fonts`` (default true) lets the fonts of Vixl's own SVG, which it names instead of storing, be
    downloaded from Google Fonts when the font cache does not have them. For PDF, ``font_map`` maps the PDF's font
    families to registered fonts (``{"Literata": "literata-400"}``) and ``install_fonts`` (default false) lets a face
    that is neither in the document nor in the font cache be downloaded."""
    from .plugins import first as plugin_first

    if format.lower() == "figma":
        imported = plugin_first("import-format", project, data, "figma", page=page, **options)
        require(imported is not None, "Figma import is not available (plugin figma_import)", field="format")
        return imported
    pdf = format.lower() == "pdf"
    install_fonts = options.pop("install_fonts", True if format.lower() == "svg" else False)
    font_map = options.pop("font_map", None)
    require(not options, f"Unknown import option(s): {', '.join(sorted(options))}")
    require(pdf or not font_map, "font_map applies to PDF import", field="font_map")
    require(len(data) <= project.limits.max_asset_bytes, "Import exceeds byte limit", "resource_limit")
    require(svg_mode in ("editable", "appearance", "auto"), "SVG mode must be editable, appearance or auto",
            field="svg_mode")
    if format.lower() == "svg":
        return _import_svg(project, data, name, svg_mode, install_fonts)
    require(format.lower() == "pdf", "Import format must be svg, pdf or figma")
    imported = plugin_first("import-format", project, data, "pdf", name=name, page=page, dpi=dpi, mode=svg_mode,
                            font_map=font_map, install_fonts=bool(install_fonts))
    require(imported is not None, "PDF import is not available (plugin pdf_import)", field="format")
    return imported


def _import_svg(project, data, name, svg_mode, install_fonts=True):
    if svg_mode == "appearance":
        return svg_appearance(project, data, name)
    from .svg_import import embedded_payload, embedded_project, import_embedded, svg_operations as convert

    payload, warning = embedded_payload(data)
    warnings = [warning] if warning else []
    if payload is not None:
        try:
            document, report = embedded_project(payload, project, data, install_fonts=install_fonts)
        except VixlError as exc:
            warnings.append(f"The Vixl document this SVG carries could not be read ({exc}); imported its visible "
                            "elements instead")
        else:
            return import_embedded(project, document, name, report["warnings"], report["fonts"])
    candidate = project.clone()
    report = {}
    try:
        operations = convert(data, candidate, name, fallback=svg_mode == "auto", report=report)
        result = candidate.apply(operations, detail="compact")
    except VixlError as exc:
        if svg_mode == "auto" and exc.code == "unsupported_svg":
            result = svg_appearance(project, data, name)
            result["warnings"] = [*warnings, f"{exc}", *result["warnings"]]
            return result
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise VixlError("invalid_svg", f"Malformed SVG: {exc}") from exc
    project.__dict__.update(candidate.__dict__)
    result["mode"] = "editable"
    warnings += report.get("warnings", [])
    if report.get("rasterized"):
        result["rasterized"] = report["rasterized"]
        warnings.append(f"{len(report['rasterized'])} element(s) Vixl cannot edit were imported as image layers: "
                        + ", ".join(item["layer"] for item in report["rasterized"][:10]))
    if warnings:
        result["warnings"] = [*warnings, *result.get("warnings", [])]
    return result


def sanitize_svg(data, limits, *, byte_limit=None):
    """Parse untrusted SVG bytes and enforce the static-SVG rules: no DOCTYPE/ENTITY, no active content,
    no external ``href`` or ``url()``, bounded depth and node count, and declared pixel size within
    ``limits``. Returns ``(root, width, height)`` with the root's width/height set to those pixel sizes."""
    import base64
    from .assets import decode

    cap = limits.max_asset_bytes if byte_limit is None else min(limits.max_asset_bytes, byte_limit)
    require(len(data) <= cap, "SVG exceeds byte limit", "resource_limit")
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
                    decode(raw, limits)
                else:
                    require(value.startswith("#"), "SVG references must be internal or embedded raster images", "unsupported_svg")
        # Only style elements hold CSS text; the text of metadata, title and desc is inert (Vixl's own SVG keeps its
        # document as JSON in metadata).
        inert = tag in ("metadata", "title", "desc", "text", "tspan")
        css = " ".join(node.attrib.values()) + " " + ("" if inert else node.text or "")
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
    limits.size(width, height)
    root.set("width", str(width))
    root.set("height", str(height))
    if root.tag == "svg":
        root.set("xmlns", "http://www.w3.org/2000/svg")
    return root, width, height


def render_svg(root, width, height):
    """Rasterize a tree returned by ``sanitize_svg`` with the bundled font only; returns RGBA PIL image."""
    import io
    from pathlib import Path
    import resvg_py
    from PIL import Image

    try:
        encoded = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode"),
                    width=width, height=height, skip_system_fonts=True,
                    font_files=[str(Path(__file__).parent / "data" / "DejaVuSans.ttf")])
        return Image.open(io.BytesIO(encoded)).convert("RGBA")
    except Exception as exc:
        raise VixlError("invalid_svg", f"Cannot render SVG: {exc}") from exc


def svg_appearance(project, data, name):
    """Render self-contained static SVG through resvg; preserve source for future editing."""
    import hashlib
    from .assets import add_image

    root, width, height = sanitize_svg(data, project.limits, byte_limit=4 * 1024 * 1024)
    image = render_svg(root, width, height)
    candidate = project.clone()
    source = "sources/" + hashlib.sha256(data).hexdigest() + ".svg"
    candidate.assets[source] = data
    asset = add_image(candidate, image)
    result = candidate.apply({"type": "add", "asset": asset, "name": name,
        "provenance": {"kind": "svg-appearance", "source": source}}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {**result, "source": source, "mode": "appearance", "warnings": [
        "SVG imported as a rendered layer with original source embedded. Geometry is not individually editable; static resvg SVG features only."]}
