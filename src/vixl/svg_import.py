"""SVG import as editable layers.

Two paths:

* **Vixl's own SVG** carries the document it shows in ``<metadata id="vixl-document">`` (``svg.embedded_document``).
  When the SVG is unchanged since export (its digest matches), importing it gives back that document: the same
  layers, names, groups, live text, effects and styles. Into an empty document the import takes the embedded canvas
  and resources as well (an exact copy); into a document with layers it places them as one editable group.
* **Any other SVG** (or a Vixl SVG edited elsewhere) is read element by element: rect, circle, ellipse, line,
  polyline, polygon and path become shape layers (fill, stroke, opacity, dashes, transforms baked into the
  geometry), ``<text>``/``<tspan>`` become live text layers, ``<g>`` becomes a group, linear and radial gradients
  become gradient layers or shape gradient fills, embedded ``<image>`` data becomes an image layer, ``<use>`` is
  expanded and ``<style>`` class rules apply. In ``auto`` mode an element Vixl cannot represent (a filter, mask,
  clip path, pattern …) becomes an image layer of just that element, so the rest stays editable.
"""

import base64
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from fontTools.misc.transform import Identity
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path

from .errors import VixlError, require
from .imports import _gradient_rect, length, numbers, transform

SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
MAX_ELEMENTS = 20000
# Untrusted SVG work caps. ``<use>`` re-walks its target for every reference, so a small file can fan out
# exponentially; the walk is charged as it goes (up to ``EXPANSION`` times the operation budget). Each raster fallback
# renders the whole canvas, so ``auto`` mode draws at most ``MAX_RASTERIZED`` elements as images.
EXPANSION = 4
MAX_RASTERIZED = 64

# ---------------------------------------------------------------------------------------------------------------
# Vixl's own SVG: the embedded document


def embedded_payload(data):
    """``(payload, warning)``: the Vixl document an SVG carries, or None and why it cannot be used (None when the
    SVG simply has none)."""
    from .svg import DOCUMENT_FORMAT, METADATA

    match = METADATA.search(data)
    if not match:
        return None, None
    try:
        payload = json.loads(ET.fromstring(match.group(0)).text or "")["vixl"]
    except (ET.ParseError, ValueError, KeyError, TypeError):
        return None, "The SVG's Vixl metadata is unreadable; imported its visible elements instead"
    if not isinstance(payload, dict) or "document" not in payload:
        return None, None
    if payload.get("format") != "vixl-svg-document" or payload.get("version") != DOCUMENT_FORMAT:
        return None, "The SVG carries a Vixl document in a format this version cannot read; imported its visible elements"
    if hashlib.sha256(data[:match.start()] + data[match.end():]).hexdigest() != payload.get("digest"):
        return None, ("The SVG was changed after Vixl exported it, so the Vixl document it carries no longer matches "
                      "what it shows; imported its visible elements instead")
    if payload.get("omitted_assets"):
        return None, (f"The SVG's Vixl document leaves out {len(payload['omitted_assets'])} large file(s); imported "
                      "its visible elements instead")
    return payload, None


def embedded_project(payload, project, data=b"", *, install_fonts=True):
    """``(document, report)``: the embedded document as a Project, through the same checks as opening a .vixl file.
    Images the payload points at in the SVG body are read from there (``data``); fonts are found again by
    identity (``resolve_fonts``), and ``report`` says how (``fonts``) and what fell back (``warnings``)."""
    from . import __version__
    from .project import ASSET_REFERENCE, Project

    document = payload["document"]
    require(isinstance(document, dict) and isinstance(document.get("state"), dict), "Invalid embedded Vixl document",
            "invalid_svg")
    encoded, images, fonts = (payload.get(key) or {} for key in ("assets", "images", "fonts"))
    require(all(isinstance(group, dict) for group in (encoded, images, fonts))
            and len(encoded) + len(images) + len(fonts) <= 10000, "Invalid embedded assets", "invalid_svg")
    require(all(isinstance(name, str) and ASSET_REFERENCE.fullmatch(name.encode())
                for name in (*encoded, *images, *fonts)), "Invalid embedded asset", "invalid_svg")

    def checked(name, text):
        require(isinstance(text, str), "Invalid embedded asset", "invalid_svg")
        try:
            raw = base64.b64decode(text, validate=True)
        except ValueError as exc:
            raise VixlError("invalid_svg", "Invalid embedded asset") from exc
        require(name.split("/")[1].startswith(hashlib.sha256(raw).hexdigest() + "."),
                "Embedded asset checksum mismatch", "invalid_svg")
        return raw

    assets = {name: checked(name, text) for name, text in encoded.items()}
    if images:
        hrefs = {element.get("id"): element.get("href") or element.get(XLINK) or ""
                 for element in ET.fromstring(data).iter() if local(element.tag) == "image" and element.get("id")}
        for name, ident in images.items():
            href = hrefs.get(ident) if isinstance(ident, str) else None
            require(href and href.startswith("data:") and ";base64," in href,
                    f"The SVG has no image {ident!r} for {name}", "invalid_svg")
            assets[name] = checked(name, href.split(",", 1)[1])
    state = document["state"]
    report = {"fonts": {}, "warnings": []}
    renamed = resolve_fonts(fonts, project, assets, report, install=install_fonts)
    if renamed:
        # Asset names are content hashes, so a font found again as other bytes has another name everywhere.
        text = json.dumps(state, ensure_ascii=False)
        for old, new in renamed.items():
            text = text.replace(old, new)
        state = json.loads(text)
    root ={"id": "rev_svg_import", "parent": None, "operations": [], "label": "Import", "state": state}
    manifest = {"format_version": document.get("format_version"), "vixl_version": __version__, "state": state,
                "nodes": {root["id"]: root}, "head": root["id"], "branches": {"main": root["id"]}, "checkpoints": {},
                "current_branch": "main", "redo_stack": [], "transaction": None,
                "asset_hashes": {name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()}}
    with tempfile.TemporaryDirectory(prefix="vixl-svg-") as folder:
        path = Path(folder) / "embedded.vixl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("project.json", json.dumps(manifest, allow_nan=False))
            for name, raw in assets.items():
                archive.writestr(name, raw)
        document = Project.load(path, limits=project.limits, workspace=getattr(project, "_workspace", None))
    document.path = None
    return document, report


def resolve_fonts(fonts, project, assets, report, *, install=True):
    """Find each font the payload names by identity (``svg.font_identity``) and add its bytes to ``assets``. In
    order: the same file already in ``project`` (by hash), the bundled file, a font ``project`` registers under
    the same name or with the same family and style, the Google Fonts style from the font cache, then (with
    ``install``) from Google Fonts. A font none of these has falls back to the bundled DejaVu Sans with a warning;
    the import never fails for a font. Returns ``{old: new}`` asset names for fonts found as other bytes;
    ``report["fonts"]`` says how each registered font resolved."""
    from .text import BUNDLED_FONTS, font_style

    folder = Path(__file__).parent / "data"
    targets = {name: raw for name, raw in project.assets.items() if name.startswith("fonts/")}
    registry = project.state.get("fonts") or {}
    renamed, missing = {}, []
    for name, record in fonts.items():
        require(isinstance(record, dict), "Invalid embedded font", "invalid_svg")
        family, weight = str(record.get("family", "")), record.get("weight")
        weight = weight if isinstance(weight, int) and not isinstance(weight, bool) else 400
        italic = bool(record.get("italic"))
        registered = [key for key in record.get("registered") or [] if isinstance(key, str)]
        raw, how = targets.get(name), "document"
        if raw is None and record.get("source") == "bundled" and record.get("file") in BUNDLED_FONTS:
            raw, how = (folder / record["file"]).read_bytes(), "bundled"
        if raw is None:
            wanted = (family.casefold(), weight, italic)
            same = [registry[key] for key in registered if registry.get(key) in targets]
            same += [other for other in targets if font_style(targets[other])[1:] == wanted[1:]]
            raw = next((targets[other] for other in same if font_style(targets[other])[0].casefold() == wanted[0]),
                       None)
        if raw is None and record.get("source") == "google":
            raw, how = google_font(family, weight, italic, install)
        if raw is None:
            raw, how = (folder / "DejaVuSans.ttf").read_bytes(), "fallback"
            missing.append(f"{family} {weight}{' italic' if italic else ''}"
                           + (f" ({', '.join(registered)})" if registered else ""))
        new = f"fonts/{hashlib.sha256(raw).hexdigest()}.ttf"
        assets[new] = raw
        if new != name:
            renamed[name] = new
        for key in registered or [family]:
            report["fonts"][key] = how
    if missing:
        report["warnings"].append(
            f"SVG does not store font files, and these were not found again: {'; '.join(missing)}. Their text uses the "
            "bundled DejaVu Sans; import the font and register it under the same name to restore it."
            + ("" if install else " Font installs were off, so Google Fonts were looked for in the font cache only."))
    return renamed


def google_font(family, weight, italic, install):
    """``(bytes, how)`` for a Google Fonts style at its nearest available weight: from the font cache (``font
    cache``), else, with ``install``, downloaded (``downloaded``); ``(None, None)`` when neither works."""
    import httpx

    from .typefaces import fetch_font, find_font

    entry = find_font(family)
    weights = (entry or {}).get("weights") or [min(900, max(100, round(weight / 100) * 100))]
    wanted = min(weights, key=lambda w: (abs(w - weight), w))

    def refuse(request):
        raise httpx.ConnectError("font installs are off", request=request)

    found = {}
    client = None if install else httpx.Client(transport=httpx.MockTransport(refuse))
    try:
        data, _ = fetch_font(family, wanted, italic, client=client, source=found)
    except VixlError:
        return None, None
    finally:
        if client is not None:
            client.close()
    return data, "downloaded" if found.get("origin") == "download" else "font cache"


MERGED_RESOURCES = ("swatches", "palettes", "luts", "patterns", "character_styles", "paragraph_styles", "brushes", "maps",
                    "variables", "fonts")


def import_embedded(project, document, name, warnings=(), fonts=None):
    """Bring ``document`` into ``project`` as one revision: its whole state into an empty document, else its layers
    as one editable group at their original positions. ``fonts`` (registered name: how it was found) goes into the
    result."""
    from .validation import check_state

    candidate = project.clone()
    adopt = not candidate.state["layers"] and not candidate.state.get("pages")
    if adopt:
        candidate.state = deepcopy(document.state)
        candidate.assets.update(document.assets)
        placed = [layer["name"] for layer in candidate.state["layers"] if not layer.get("parent")]
    else:
        from .objects import from_document, place
        from .operations import taken

        tops = [layer for layer in document.state["layers"] if not layer.get("parent")]
        require(tops, "The SVG's Vixl document has no layers", "invalid_svg")
        root_name = tops[0]["name"] if len(tops) == 1 and tops[0]["type"] == "group" else name
        item, assets = from_document(document, name)
        originals = [layer["name"] for layer in item["layers"]]
        before = {layer["id"] for layer in candidate.state["layers"]}
        for key in MERGED_RESOURCES:
            # Named resources the layers may refer to; a name the document already uses keeps its own value.
            if isinstance(document.state.get(key), dict):
                target = candidate.state.setdefault(key, {})
                for entry, value in document.state[key].items():
                    target.setdefault(entry, deepcopy(value))
        for asset in document.assets:
            candidate.assets.setdefault(asset, document.assets[asset])
        root = place(candidate, {"name": root_name}, (item, assets))
        new = [layer for layer in candidate.state["layers"] if layer["id"] not in before]
        for layer, original in zip(new, originals):
            # Children keep their own names when the document has no layer by that name.
            if layer is not root and taken(candidate, original) is None:
                layer["name"] = original
        placed = [root["name"]]
    check_state(candidate, candidate.state)
    if candidate.transaction is None:
        candidate._record([], f"Import {name}")
    candidate._inspected = None
    project.__dict__.update(candidate.__dict__)
    result = {"success": True, "committed": True, "mode": "document", "layers": placed,
              "layer_count": len(document.state["layers"]),
              "canvas": "adopted" if adopt else "kept",
              "message": "Imported the Vixl document this SVG carries: its layers, text, groups and effects are "
                         "editable as they were." + ("" if adopt else " They are placed as one group.")}
    if fonts:
        result["fonts"] = dict(fonts)
    if warnings:
        result["warnings"] = list(warnings)
    return result


# ---------------------------------------------------------------------------------------------------------------
# Any SVG: element by element


class Unsupported(VixlError):
    """An element Vixl cannot represent as editable layers (auto mode draws it as an image instead)."""

    def __init__(self, message):
        super().__init__("unsupported_svg", message)


INHERITED = {"fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "fill-rule", "visibility",
             "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset",
             "font-family", "font-size", "font-weight", "font-style", "text-anchor", "letter-spacing", "color",
             "paint-order"}
OWN = {"opacity", "display", "transform"}
# Attributes that do not change what an element looks like, or only marginally (rendering hints).
IGNORED = {"id", "class", "style", "version", "baseProfile", "enable-background", "shape-rendering", "text-rendering",
           "image-rendering", "color-rendering", "color-interpolation", "color-interpolation-filters",
           "pointer-events", "cursor", "tabindex", "focusable", "role", "font-stretch", "font-variant",
           "word-spacing", "xmlns", "x-overflow", "dominant-baseline", "alignment-baseline", "text-decoration",
           "writing-mode", "direction", "unicode-bidi", "font-kerning", "isolation", "mix-blend-mode", "lengthAdjust"}
GEOMETRY = {
    "path": {"d", "pathLength"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"},
    "polygon": {"points"},
    "polyline": {"points"},
    "image": {"x", "y", "width", "height", "href", "preserveAspectRatio"},
    "text": {"x", "y", "dx", "dy", "textLength", "rotate"},
    "tspan": {"x", "y", "dx", "dy", "textLength", "rotate"},
    "use": {"x", "y", "width", "height", "href"},
    "svg": {"x", "y", "width", "height", "viewBox", "preserveAspectRatio", "overflow"},
    "g": set(),
    "a": {"href", "target"},
}
DEFINITIONS = {"title", "desc", "metadata", "defs", "style", "linearGradient", "radialGradient", "clipPath", "mask",
               "pattern", "filter", "marker", "symbol", "font", "font-face", "script"}
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polygon", "polyline"}
GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
                    "ui-serif", "ui-monospace"}


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def foreign(tag):
    return isinstance(tag, str) and tag.startswith("{") and not tag.startswith("{" + SVG_NS + "}")


def parse_css(text):
    """Simple stylesheet rules: ``[(specificity, order, selector, declarations)]``. Selectors may be a type,
    ``.class``, ``#id``, ``type.class`` or ``*``, comma-separated; anything else is unsupported."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if "@" in text:
        raise Unsupported("SVG stylesheets with @-rules are not editable")
    rules = []
    remainder = re.sub(r"[^{}]+\{[^{}]*\}", "", text)
    if remainder.strip():
        raise Unsupported("Unsupported SVG stylesheet syntax")
    for order, (selectors, body) in enumerate(re.findall(r"([^{}]+)\{([^{}]*)\}", text)):
        declarations = declarations_of(body)
        for selector in selectors.split(","):
            selector = selector.strip()
            match = re.fullmatch(r"(\*|[A-Za-z][\w-]*)?((?:\.[\w-]+)*)(#[\w-]+)?", selector)
            if not selector or not match:
                raise Unsupported(f"Unsupported SVG stylesheet selector {selector!r}")
            tag, classes, ident = match.groups()
            classes = [c for c in classes.split(".") if c]
            specificity = (100 if ident else 0) + 10 * len(classes) + (1 if tag and tag != "*" else 0)
            rules.append((specificity, order, (tag if tag != "*" else None, set(classes), ident[1:] if ident else None),
                          declarations))
    return sorted(rules, key=lambda rule: rule[:2])


def declarations_of(text):
    result = {}
    for declaration in text.split(";"):
        if declaration.strip():
            require(":" in declaration, "Invalid SVG style", "invalid_svg")
            key, value = declaration.split(":", 1)
            value = re.sub(r"\s*!important\s*$", "", value.strip())
            result[key.strip()] = value
    return result


def path_commands(pen, x0, y0):
    commands = []
    for command, points in pen.value:
        if command in ("closePath", "endPath"):
            if command == "closePath":
                commands.append("Z")
        else:
            letter = {"moveTo": "M", "lineTo": "L", "curveTo": "C", "qCurveTo": "Q"}[command]
            commands.append(letter + " ".join(f"{x - x0:.6g} {y - y0:.6g}" for x, y in points))
    return " ".join(commands)


class _Flatten(BasePen):
    def __init__(self):
        super().__init__(None)
        self.points = []

    def _moveTo(self, p):
        self.points.append(p)

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        for i in range(1, 9):
            t = i / 8
            s = 1 - t
            self.points.append((s ** 3 * p0[0] + 3 * s * s * t * p1[0] + 3 * s * t * t * p2[0] + t ** 3 * p3[0],
                                s ** 3 * p0[1] + 3 * s * s * t * p1[1] + 3 * s * t * t * p2[1] + t ** 3 * p3[1]))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        for i in range(1, 9):
            t = i / 8
            s = 1 - t
            self.points.append((s * s * p0[0] + 2 * s * t * p1[0] + t * t * p2[0],
                                s * s * p0[1] + 2 * s * t * p1[1] + t * t * p2[1]))


def _contours(value):
    contours, current = [], []
    for command, points in value:
        if command == "moveTo" and current:
            contours.append(current)
            current = []
        current.append((command, points))
        if command in ("closePath", "endPath"):
            contours.append(current)
            current = []
    if current:
        contours.append(current)
    return contours


def _polygon(contour):
    pen = _Flatten()
    for command, points in contour:
        getattr(pen, command)(*points)
    return pen.points


def _inside(point, polygon):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _area(polygon):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1])) / 2


def evenodd_to_nonzero(value):
    """Recording-pen commands filled even-odd, rewound so a nonzero fill draws the same: a contour inside an odd
    number of others winds against the outer ones (exact for contours that do not cross each other)."""
    contours = _contours(value)
    polygons = [_polygon(contour) for contour in contours]
    result = []
    for index, (contour, polygon) in enumerate(zip(contours, polygons)):
        if len(polygon) < 3:
            result.extend(contour)
            continue
        depth = sum(_inside(polygon[0], other) for j, other in enumerate(polygons) if j != index and len(other) >= 3)
        if (_area(polygon) > 0) != (depth % 2 == 0):
            pen = RecordingPen()
            reverse = ReverseContourPen(pen)
            for command, points in contour:
                getattr(reverse, command)(*points)
            result.extend(pen.value)
        else:
            result.extend(contour)
    return result


def _font_key(text):
    return re.sub(r"[\s_\-'\"]", "", text).lower()


def match_font(project, families, bold=False, italic=False, *, font_map=None, resolver=None, report=None):
    """``(font, unknown family)``: the first of ``families`` the document has registered (a bold or italic
    registration of it when asked, such as ``Inter Bold``), else the bundled DejaVu Sans for that family, else None and the
    first family that is not a generic one.

    ``font_map`` (``{source family: registered name}``) is tried first, with the same style suffixes, so
    ``{"Literata": "literata-400", "Literata Bold": "literata-700"}`` maps bold text to the bold face. ``resolver``,
    ``resolver(families, bold, italic) -> (name, how) | None``, can find a face elsewhere (the font cache, a download)
    and register it; it is asked after a registration of the exact style and before one of the plain family.
    ``report``, a dict, is filled with ``how`` the font was chosen: ``mapped``, ``registered``, the resolver's ``how``,
    or ``default``."""
    report = {} if report is None else report
    named = [f for f in families if f.lower() not in GENERIC_FAMILIES]
    suffixes = ((["bolditalic"] if bold and italic else []) + (["bold"] if bold else [])
                + (["italic"] if italic else []))
    if font_map:
        keyed = {_font_key(key): value for key, value in font_map.items()}
        for candidate in named:
            for suffix in [*suffixes, ""]:
                if _font_key(candidate) + suffix in keyed:
                    report["how"] = "mapped"
                    return keyed[_font_key(candidate) + suffix], None
    registered = {}
    for name, asset in project.state.get("fonts", {}).items():
        registered.setdefault(_font_key(name), name)
        for family in _families(project.assets.get(asset)):
            registered.setdefault(_font_key(family), name)
    bundled = {"dejavusans": "DejaVuSans.ttf"}  # the bundled face text layers can name directly

    def lookup(plain):
        for candidate in named:
            base = _font_key(candidate)
            for suffix in suffixes + ([""] if plain else []):
                if base + suffix in registered:
                    return registered[base + suffix]
            if plain and base in bundled:
                return bundled[base]
        return None

    # Without a resolver this is one pass in the order above; with one, a registration of the exact style comes
    # first, then the resolver, then a registration of the plain family (another weight or slope).
    found = lookup(plain=resolver is None or not suffixes)
    if found is None and resolver is not None:
        resolved = resolver(named, bold, italic)
        if resolved:
            report["how"] = resolved[1]
            return resolved[0], None
        found = lookup(plain=True)
    if found is not None:
        report["how"] = "registered"
        return found, None
    report["how"] = "default"
    return None, named[0] if named else None


def _families(data):
    """The family names a font file declares (typographic family, family, full name)."""
    if not data:
        return ()
    try:
        from .text import face

        names = face(data)[0]["name"]
        return tuple(dict.fromkeys(str(names.getDebugName(i)) for i in (16, 1, 4) if names.getDebugName(i)))
    except Exception:  # an unreadable name table only means the font cannot be matched by family
        return ()


def font_warning(family):
    return (f"Font {family!r} is not registered in this document; the text uses the document's default face "
            "(install or import the font, then set font on the layer)")


def anchor_text(project, operations, anchored):
    """Text whose anchor is not its left edge, or that is rotated: measure it in a scratch copy and move it so the
    anchor point (the start, middle or end of its first baseline) lands where the source puts it. ``anchored``
    holds ``{name, anchor (x, y), align, rotation}`` for text operations placed with ``x`` and ``baseline_y``."""
    if not anchored:
        return operations
    scratch = project.clone()
    scratch.apply(deepcopy(operations), detail="brief")
    by_name = {op.get("name"): op for op in operations if op["type"] == "text"}
    for record in anchored:
        layer = scratch.layer(record["name"])
        op = by_name[record["name"]]
        w, h = layer["width"], layer["height"]
        baseline = op["baseline_y"] - layer["y"]  # first baseline below the box top
        fx = {"left": 0, "center": 0.5, "right": 1}[record["align"]]
        px, py = fx * w - w / 2, baseline - h / 2  # the anchor relative to the box centre
        angle = math.radians(record["rotation"])
        rx, ry = px * math.cos(angle) - py * math.sin(angle), px * math.sin(angle) + py * math.cos(angle)
        cx, cy = record["anchor"][0] - rx, record["anchor"][1] - ry
        op.pop("baseline_y", None)
        op["x"], op["y"] = cx - w / 2, cy - h / 2
        if abs(record["rotation"]) > 1e-6:
            op["rotation"] = record["rotation"]
    return operations


def _similarity(matrix):
    a, b, c, d, _, _ = matrix
    sx, sy = math.hypot(a, b), math.hypot(c, d)
    return abs(sx - sy) < 1e-6 * max(1, sx) and abs(a * c + b * d) < 1e-6 * max(1, sx * sy), sx


class Converter:
    def __init__(self, data, project, name, *, fallback=False, namespace=False, font_map=None):
        self.project, self.name, self.fallback, self.namespace = project, name, fallback, namespace
        self.font_map = font_map or {}
        self.operations, self.warnings, self.rasterized = [], [], []
        self.budget, self.expanded, self.rasters = project.limits.max_operations, 0, 0
        self._definitions = None  # the SVG's defs and stylesheets, copied once for every raster fallback
        self._sizes = {}  # element -> elements it expands to, <use> references included
        self.used = {layer["name"] for layer in project.state["layers"]} | {layer["id"] for layer in
                                                                             project.state["layers"]}
        self.anchored = []  # text operations whose x depends on their measured width (text-anchor, rotation)
        self.data = data
        self.root = ET.fromstring(data)
        require(local(self.root.tag) == "svg", "Expected an SVG root")
        self.ids = {}
        count = 0
        for node in self.root.iter():
            count += 1
            require(count <= MAX_ELEMENTS, "SVG structure exceeds limits", "resource_limit")
            if node.get("id"):
                self.ids.setdefault(node.get("id"), node)
        self.rules = []
        for node in self.root.iter():
            if local(node.tag) == "style" and not foreign(node.tag):
                require(node.get("type", "text/css") == "text/css", "Unsupported SVG stylesheet type",
                        "unsupported_svg")
                self.rules += parse_css("".join(node.itertext()))
        self.rules.sort(key=lambda rule: rule[:2])
        self.base, self.size = self.viewport()
        box = numbers(self.root.get("viewBox", "")) if self.root.get("viewBox") else []
        self.user_size = (box[2], box[3]) if len(box) == 4 else self.size

    def viewport(self):
        root = self.root
        width = height = None
        if "viewBox" in root.attrib:
            box = numbers(root.attrib["viewBox"])
            require(len(box) == 4 and box[2] > 0 and box[3] > 0, "Invalid SVG viewBox")
            width = length(root.get("width", str(box[2])))
            height = length(root.get("height", str(box[3])))
            require(width > 0 and height > 0, "SVG dimensions must be positive")
            preserve = root.get("preserveAspectRatio", "xMidYMid meet")
            require(preserve in ("none", "xMidYMid", "xMidYMid meet"), "Unsupported preserveAspectRatio",
                    "unsupported_svg")
            sx, sy = width / box[2], height / box[3]
            if preserve != "none":
                sx = sy = min(sx, sy)
            base = (Identity.translate((width - box[2] * sx) / 2, (height - box[3] * sy) / 2)
                    .scale(sx, sy).translate(-box[0], -box[1]))
        else:
            base = Identity
            width = length(root.get("width", "0")) if root.get("width") else None
            height = length(root.get("height", "0")) if root.get("height") else None
        c = self.project.state["canvas"]
        return base, (math.ceil(width or c["width"]), math.ceil(height or c["height"]))

    # --- names, styles -------------------------------------------------------------------------------------------

    def unique(self, base):
        base = (base or self.name).strip()[:180] or self.name
        candidate, index = base, 2
        while candidate in self.used:
            candidate = f"{base}-{index}"
            index += 1
        self.used.add(candidate)
        return candidate

    def label(self, node):
        return (node.get("data-layer") or node.get("{http://www.inkscape.org/namespaces/inkscape}label")
                or node.get("id"))

    def layer_label(self, node):
        """The node's label as a layer name: prefixed with ``name`` under ``namespace``, so operation lists built
        separately (before any of them is applied) cannot collide."""
        label = self.label(node)
        return f"{self.name} {label}" if label and self.namespace else label

    def attributes(self, node):
        """Presentation attributes, then matching stylesheet rules, then the style attribute (CSS cascade)."""
        attrs = {}
        for key, value in node.attrib.items():
            if key.startswith("{"):
                if key == XLINK:
                    attrs["href"] = value
                continue
            if key.startswith(("data-", "aria-")):
                continue
            attrs[key] = value
        if self.rules:
            tag, classes, ident = local(node.tag), set(node.get("class", "").split()), node.get("id")
            for _, _, (rule_tag, rule_classes, rule_id), declarations in self.rules:
                if ((rule_tag is None or rule_tag == tag) and rule_classes <= classes
                        and (rule_id is None or rule_id == ident)):
                    attrs.update(declarations)
        attrs.update(declarations_of(node.get("style", "")))
        attrs.pop("style", None)
        return attrs

    def check_attributes(self, tag, attrs):
        allowed = INHERITED | OWN | IGNORED | GEOMETRY.get(tag, set())
        for key, value in attrs.items():
            if key in ("clip-path", "mask", "filter", "marker-start", "marker-mid", "marker-end", "marker"):
                if value.strip() != "none":
                    raise Unsupported(f"SVG {key} is not editable; use svg_mode='auto' (draws that element as an "
                                      "image) or 'appearance'")
            elif key == "vector-effect":
                if value.strip() != "none":
                    raise Unsupported("SVG vector-effect is not editable")
            elif key not in allowed:
                raise Unsupported(f"Unsupported SVG attributes: [{key!r}]; use svg_mode='appearance' or 'auto'")

    # --- walking ---------------------------------------------------------------------------------------------------

    def convert(self):
        names = self.walk(self.root, self.base, {}, 0, ())
        require(names or self.operations, "SVG contains no visible geometry")
        return self.operations

    def walk(self, node, matrix, inherited, depth, clips, use_depth=0):
        tag = local(node.tag)
        if foreign(node.tag) or not isinstance(node.tag, str) or tag in DEFINITIONS:
            return []
        require(depth <= 64, "SVG structure exceeds limits", "resource_limit")
        self.charge(1)
        before, anchored = len(self.operations), len(self.anchored)
        try:
            return self._walk(node, tag, matrix, inherited, depth, clips, use_depth)
        except VixlError as exc:
            if exc.code != "unsupported_svg" or not self.fallback or depth == 0:
                raise
            del self.operations[before:]
            del self.anchored[anchored:]
            return self.rasterize(node, matrix, inherited, str(exc))

    def charge(self, count, ahead=0):
        """Count elements walked (``<use>`` expansion included) and fail as soon as the import outgrows its budget,
        or would with ``ahead`` more. ``resource_limit`` is never caught by the raster fallback."""
        self.expanded += count
        limit = EXPANSION * self.budget
        if self.expanded + ahead > limit or len(self.operations) > self.budget:
            raise VixlError("resource_limit", f"SVG expands to more than {limit} elements or {self.budget} layers; "
                            "flatten its <use> references or import with svg_mode='appearance'", field="svg")

    def expansion(self, node, depth=0, active=frozenset()):
        """How many elements walking ``node`` visits, ``<use>`` targets expanded. Memoized and capped just past the
        budget, so it costs at most one pass over the tree; a reference cycle is left to the walk, which refuses it."""
        if node in self._sizes:
            return self._sizes[node]
        limit = EXPANSION * self.budget + 1
        total = 1
        if depth <= 64:
            if local(node.tag) == "use":
                href = (node.get("href") or node.get(XLINK) or "").strip()
                target = self.ids.get(href[1:]) if href.startswith("#") else None
                if target is not None and target not in active:
                    total += self.expansion(target, depth + 1, active | {target})
            for child in node:
                if total > limit:
                    break
                total += self.expansion(child, depth + 1, active)
        self._sizes[node] = total = min(total, limit)
        return total

    def _walk(self, node, tag, matrix, inherited, depth, clips, use_depth):
        if tag not in GEOMETRY:
            raise Unsupported(f"Unsupported SVG element {tag!r}; simplify it to paths or import with "
                              "svg_mode='appearance' or 'auto'")
        attrs = self.attributes(node)
        self.check_attributes(tag, attrs)
        props = {**inherited, **{k: v for k, v in attrs.items() if k in INHERITED}}
        if attrs.get("display") == "none" or props.get("visibility") in ("hidden", "collapse"):
            return []
        if depth:
            matrix = matrix.transform(transform(attrs.get("transform", "")))
        opacity = float(attrs.get("opacity", 1))
        require(math.isfinite(opacity) and 0 <= opacity <= 1, "SVG opacity must be 0–1")
        if tag == "svg" and depth:
            matrix, clips = self.nested_viewport(attrs, matrix, clips)
        if tag in ("svg", "g", "a"):
            names = []
            for child in node:
                names += self.walk(child, matrix, props, depth + 1, clips, use_depth)
            return self.group(node, names, opacity, depth)
        if tag == "use":
            return self.use(node, attrs, matrix, props, depth, clips, opacity, use_depth)
        if tag == "image":
            return self.image(node, attrs, matrix, clips, opacity)
        if tag == "text":
            return self.text(node, attrs, matrix, props, clips, opacity)
        if tag == "tspan":
            raise Unsupported("A tspan outside a text element is not editable")
        return self.shape(node, tag, attrs, matrix, props, clips, opacity)

    def nested_viewport(self, attrs, matrix, clips):
        viewbox = numbers(attrs["viewBox"]) if "viewBox" in attrs else [0, 0, length(attrs.get("width", "0")),
                                                                         length(attrs.get("height", "0"))]
        require(len(viewbox) == 4 and viewbox[2] > 0 and viewbox[3] > 0, "Invalid nested SVG viewBox", "unsupported_svg")
        w, h = length(attrs.get("width", str(viewbox[2]))), length(attrs.get("height", str(viewbox[3])))
        require(w > 0 and h > 0, "Nested SVG dimensions must be positive", "unsupported_svg")
        matrix = matrix.translate(length(attrs.get("x", "0")), length(attrs.get("y", "0")))
        overflow = attrs.get("overflow", "hidden")
        require(overflow in ("hidden", "visible"), "Unsupported SVG viewport overflow", "unsupported_svg")
        if overflow == "hidden":
            clips = (*clips, (matrix.inverse(), w, h))
        preserve = attrs.get("preserveAspectRatio", "xMidYMid meet")
        require(preserve in ("none", "xMidYMid", "xMidYMid meet"), "Unsupported preserveAspectRatio", "unsupported_svg")
        sx, sy = w / viewbox[2], h / viewbox[3]
        if preserve != "none":
            sx = sy = min(sx, sy)
        matrix = matrix.translate((w - viewbox[2] * sx) / 2, (h - viewbox[3] * sy) / 2).scale(sx, sy).translate(
            -viewbox[0], -viewbox[1])
        return matrix, clips

    def group(self, node, names, opacity, depth):
        """A labelled ``<g>`` (id, data-layer, inkscape:label) of several layers, or any group with opacity, becomes
        a group layer; one layer keeps the label as its name and takes the opacity."""
        if not names:
            return []
        label = self.layer_label(node) if depth else None
        if len(names) == 1:
            if label and depth and self.renamable(names[0]):
                self.rename(names[0], self.unique(label))
                names = [self.renamed]
            if opacity != 1:
                self.operations.append({"type": "opacity", "target": names[0], "value": self.opacity_of(names[0])
                                        * opacity})
            return names
        if not depth or (not label and opacity == 1):
            return names
        group = self.unique(label or f"{self.name}-group")
        self.operations.append({"type": "group", "name": group, "targets": names})
        if opacity != 1:
            self.operations.append({"type": "opacity", "target": group, "value": opacity})
        return [group]

    def renamable(self, name):
        return name in self.auto_named

    @property
    def auto_named(self):
        return self.__dict__.setdefault("_auto", set())

    def rename(self, old, new):
        for op in self.operations:
            if op.get("name") == old:
                op["name"] = new
            if op.get("target") == old:
                op["target"] = new
            if "targets" in op:
                op["targets"] = [new if t == old else t for t in op["targets"]]
        for record in self.anchored:
            if record["name"] == old:
                record["name"] = new
        self.used.discard(old)
        self.auto_named.discard(old)
        self.renamed = new

    def opacity_of(self, name):
        for op in self.operations:
            if op.get("name") == name and "opacity" in op:
                return op["opacity"]
        return 1

    def new_name(self, node, kind):
        label = self.layer_label(node)
        name = self.unique(label or f"{self.name}-{kind}")
        if not label:
            self.auto_named.add(name)
        return name

    def use(self, node, attrs, matrix, props, depth, clips, opacity, use_depth):
        href = attrs.get("href", "")
        require(href.startswith("#"), "SVG references must be internal", "unsupported_svg")
        target = self.ids.get(href[1:])
        if target is None:
            raise Unsupported(f"Unknown SVG reference {href!r}")
        if use_depth >= 8:
            raise Unsupported("SVG use references nest too deeply")
        matrix = matrix.translate(length(attrs.get("x", "0")), length(attrs.get("y", "0")))
        if local(target.tag) == "symbol":
            symbol = dict(target.attrib)
            if "width" in attrs:
                symbol["width"] = attrs["width"]
            if "height" in attrs:
                symbol["height"] = attrs["height"]
            proxy = ET.Element(f"{{{SVG_NS}}}svg", {k: v for k, v in symbol.items() if k in ("viewBox", "width",
                               "height", "preserveAspectRatio", "overflow", "class", "style", "id")})
            proxy.extend(list(target))
            target = proxy
        self.charge(0, ahead=self.expansion(target))
        names = self.walk(target, matrix, props, depth + 1, clips, use_depth + 1)
        return self.group(node, names, opacity, depth)

    # --- paint ---------------------------------------------------------------------------------------------------

    def color(self, value, alpha, props, keep=False):
        """A hex colour (``transparent`` when fully clear, unless ``keep``: gradient stops keep their RGB)."""
        from .colors import hex_of, parse

        value = value.strip()
        if value == "none" or value == "transparent":
            return "transparent"
        if value == "currentColor":
            value = props.get("color", "black")
        try:
            rgba = parse(value)
        except (VixlError, ValueError) as exc:
            raise Unsupported(f"Unsupported SVG colour {value!r}") from exc
        require(math.isfinite(alpha) and 0 <= alpha <= 1, "SVG paint opacity must be 0–1")
        if rgba[3] * alpha == 0 and not keep:
            return "transparent"
        return hex_of((*rgba[:3], rgba[3] * alpha))

    def paint(self, props, key):
        value = props.get(key, "black" if key == "fill" else "none").strip()
        alpha = float(props.get(key + "-opacity", 1))
        if value.startswith("url("):
            raise Unsupported(f"Referenced SVG {key} paints are not editable; use svg_mode='appearance' or 'auto'")
        return self.color(value, alpha, props)

    def gradient(self, value):
        match = re.fullmatch(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)(?:\s+.*)?", value.strip())
        node = self.ids.get(match.group(1)) if match else None
        if node is None or local(node.tag) not in ("linearGradient", "radialGradient"):
            raise Unsupported("Referenced SVG paints other than gradients are not editable (patterns, unknown IDs)")
        attrs, stops, seen = {}, [], set()
        cursor = node
        while cursor is not None and id(cursor) not in seen:
            seen.add(id(cursor))
            for key, item in cursor.attrib.items():
                key = "href" if key == XLINK else key
                attrs.setdefault(key, item)
            if not stops:
                stops = [child for child in cursor if local(child.tag) == "stop"]
            href = cursor.get("href") or cursor.get(XLINK) or ""
            cursor = self.ids.get(href[1:]) if href.startswith("#") else None
        if not stops:
            raise Unsupported("An SVG gradient without stops is not editable; use svg_mode='appearance' or 'auto'")
        if attrs.get("spreadMethod", "pad") != "pad":
            raise Unsupported("Repeating SVG gradients are not editable")
        parsed = []
        last = 0
        for stop in stops:
            style = {**{k: v for k, v in stop.attrib.items()}, **declarations_of(stop.get("style", ""))}
            offset = style.get("offset", "0").strip()
            offset = float(offset[:-1]) / 100 if offset.endswith("%") else float(offset)
            offset = max(last, min(1, max(0, offset)))
            last = offset
            color = self.color(style.get("stop-color", "black"), float(style.get("stop-opacity", 1)), {}, keep=True)
            parsed.append((offset, color))
        return local(node.tag), attrs, parsed

    # --- shapes ----------------------------------------------------------------------------------------------------

    def shape(self, node, tag, attrs, matrix, props, clips, opacity):
        require(not [child for child in node if not foreign(child.tag) and local(child.tag) not in ("title", "desc")],
                "SVG shape children are unsupported", "unsupported_svg")
        fill_value = props.get("fill", "black").strip()
        name = self.new_name(node, tag if tag != "path" else "shape")
        if fill_value.startswith("url(") and tag == "rect" and not clips:
            gradients = {k: v for k, v in self.ids.items() if local(v.tag) in ("linearGradient", "radialGradient")}
            try:
                operation = _gradient_rect(attrs, props, matrix, gradients, name, opacity)
            except VixlError:
                pass  # not one of Vixl's own exact gradient rectangles: a path with a gradient fill below
            else:
                operation["name"] = name
                self.operations.append(operation)
                return [name]

        def get(key, default=0):
            return length(attrs.get(key, str(default)))

        if tag == "path":
            d = attrs.get("d", "")
        elif tag == "rect":
            x, y, w, h = get("x"), get("y"), get("width"), get("height")
            require(w >= 0 and h >= 0, "SVG rectangle dimensions must be nonnegative")
            if w == 0 or h == 0:
                return []
            rx = attrs.get("rx", attrs.get("ry", "0"))
            ry = attrs.get("ry", attrs.get("rx", "0"))
            rx, ry = min(length(rx), w / 2), min(length(ry), h / 2)
            if rx > 0 and ry > 0:
                d = (f"M{x + rx} {y} H{x + w - rx} A{rx} {ry} 0 0 1 {x + w} {y + ry} V{y + h - ry} "
                     f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h} H{x + rx} A{rx} {ry} 0 0 1 {x} {y + h - ry} "
                     f"V{y + ry} A{rx} {ry} 0 0 1 {x + rx} {y} Z")
            else:
                d = f"M{x} {y} L{x + w} {y} L{x + w} {y + h} L{x} {y + h} Z"
        elif tag in ("circle", "ellipse"):
            cx, cy = get("cx"), get("cy")
            rx, ry = (get("r"), get("r")) if tag == "circle" else (get("rx"), get("ry"))
            if rx <= 0 or ry <= 0:
                return []
            d = f"M{cx - rx} {cy} A{rx} {ry} 0 1 0 {cx + rx} {cy} A{rx} {ry} 0 1 0 {cx - rx} {cy} Z"
        elif tag == "line":
            d = f"M{get('x1')} {get('y1')} L{get('x2')} {get('y2')}"
        else:
            points = numbers(attrs.get("points", ""))
            if len(points) % 2:
                points = points[:-1]
            if len(points) < 4:
                return []
            d = "M" + " L".join(f"{x} {y}" for x, y in zip(points[::2], points[1::2])) + (" Z" if tag == "polygon"
                                                                                          else "")
        require(0 < len(d) <= 262144, "SVG path exceeds limits", "resource_limit")
        local_pen, pen = RecordingPen(), RecordingPen()
        try:
            parse_path(d, local_pen)
        except (ValueError, IndexError, AssertionError) as exc:
            raise VixlError("invalid_svg", f"Invalid SVG path: {exc}") from exc
        require(len(local_pen.value) <= 8192, "SVG path exceeds command limit", "resource_limit")
        local_pen.replay(TransformPen(pen, matrix))
        bounds = BoundsPen(None)
        pen.replay(bounds)
        if bounds.bounds is None:
            return []
        stroke_width = length(props.get("stroke-width", "1").strip() or "1")
        similar, scale = _similarity(matrix)
        stroke = self.paint(props, "stroke") if not props.get("stroke", "none").startswith("url(") else None
        if stroke is None:
            raise Unsupported("Gradient strokes are not editable; use svg_mode='appearance' or 'auto'")
        stroked = stroke != "transparent" and stroke_width > 0
        if not stroked and props.get("fill", "black").strip() in ("none", "transparent"):
            return []
        if stroked:
            if not similar:
                raise Unsupported("Nonuniform SVG strokes must be outlined before import")
        order = props.get("paint-order", "normal").split()
        stroke_first = stroked and bool(order) and order[0] == "stroke"
        pad = stroke_width * scale / 2 if stroked else 0
        for inverse, viewport_w, viewport_h in clips:
            box = BoundsPen(None)
            pen.replay(TransformPen(box, inverse))
            if box.bounds:
                left, top, right, bottom = box.bounds
                a, b, c, d2, _, _ = inverse
                dx, dy = pad * math.hypot(a, c), pad * math.hypot(b, d2)
                if not (left - dx >= -1e-6 and top - dy >= -1e-6 and right + dx <= viewport_w + 1e-6
                        and bottom + dy <= viewport_h + 1e-6):
                    raise Unsupported("Clipped nested SVG geometry requires svg_mode='appearance' or 'auto'")
        rule = props.get("fill-rule", "nonzero").strip()
        require(rule in ("nonzero", "evenodd"), "Invalid SVG fill-rule", "invalid_svg")
        value = evenodd_to_nonzero(pen.value) if rule == "evenodd" else pen.value
        x0, y0, x1, y1 = bounds.bounds
        left, top = math.floor(x0 - pad), math.floor(y0 - pad)
        w, h = max(1, math.ceil(x1 + pad) - left), max(1, math.ceil(y1 + pad) - top)
        self.project.limits.size(w, h)
        recorded = RecordingPen()
        recorded.value = value
        operation = {"type": "shape", "shape": "path", "name": name, "path": path_commands(recorded, left, top),
                     "width": w, "height": h, "x": left, "y": top, "stroke": stroke, "stroke_width": stroke_width * scale}
        if opacity != 1:
            operation["opacity"] = opacity
        if fill_value.startswith("url("):
            operation["fill"], style = self.gradient_fill(fill_value, local_pen, matrix, (left, top, w, h), props)
            axis_aligned = abs(matrix[1]) < 1e-9 and abs(matrix[2]) < 1e-9
            if style and not stroked and tag in ("rect", "circle", "ellipse") and axis_aligned \
                    and self.boxed(tag, attrs, style):
                # A plain rectangle, or a radial glow on a circle or ellipse: an editable gradient layer, which
                # keeps translucent stops.
                gradient = {"type": "gradient", "name": name, "x": left, "y": top, "width": w, "height": h,
                            "stops": style["stops"], "direction": style["direction"],
                            **{k: style[k] for k in ("angle", "center") if k in style}}
                if opacity != 1:
                    gradient["opacity"] = opacity
                self.operations.append(gradient)
                return [name]
            if style:
                # The gradient spans the layer's box, as the settings were timed: the shape keeps it as its fill.
                del operation["fill"]
                operation["fill_gradient"] = style
        else:
            operation["fill"] = self.paint(props, "fill")
        if stroked:
            self.stroke_details(operation, props, scale)
        names = [name]
        if stroke_first:
            # paint-order: stroke under the fill, as two layers.
            outline = {**operation, "name": self.unique(f"{name} stroke"), "fill": "transparent"}
            outline.pop("fill_gradient", None)
            operation["stroke"] = "transparent"
            for key in ("line_cap", "line_join", "dash", "dash_offset"):
                operation.pop(key, None)
            self.operations.append(outline)
            names.insert(0, outline["name"])
        self.operations.append(operation)
        return names

    @staticmethod
    def boxed(tag, attrs, style):
        if tag == "rect":
            return length(attrs.get("rx", "0")) == 0 and length(attrs.get("ry", "0")) == 0
        last = style["stops"][-1]["color"]
        return style["direction"] == "radial" and len(last) == 9 and last.endswith("00")

    def stroke_details(self, operation, props, scale):
        cap = props.get("stroke-linecap", "butt").strip()
        join = props.get("stroke-linejoin", "miter").strip()
        if cap != "butt":
            operation["line_cap"] = cap
        if join not in ("miter", "miter-clip", "arcs"):
            operation["line_join"] = join
        dashes = props.get("stroke-dasharray", "none").strip()
        if dashes not in ("none", ""):
            values = [length(v) * scale for v in re.split(r"[\s,]+", dashes) if v]
            if len(values) % 2:
                values *= 2
            if any(values) and all(v >= 0 for v in values):
                operation["dash"] = values
                operation["dash_fit"] = False  # SVG dash arrays are exact lengths from the path's start
                offset = length(props.get("stroke-dashoffset", "0")) * scale
                if offset:
                    operation["dash_offset"] = offset

    def gradient_fill(self, value, local_pen, matrix, box, props):
        """(flat fill, gradient settings) for a gradient-filled shape: its ``fill_gradient`` spans the layer's box,
        so stops are re-timed to where the SVG gradient crosses it. The settings are None (and the fill the
        gradient's last colour) for a gradient with no extent."""
        kind, attrs, stops = self.gradient(value)
        alpha = float(props.get("fill-opacity", 1))
        if alpha != 1:
            stops = [(offset, self.color(color, alpha, {}, keep=True)) for offset, color in stops]
        units = attrs.get("gradientUnits", "objectBoundingBox")
        gradient_matrix = transform(attrs.get("gradientTransform", ""))
        if units == "objectBoundingBox":
            bounds = BoundsPen(None)
            local_pen.replay(bounds)
            bx0, by0, bx1, by1 = bounds.bounds
            space = matrix.transform(Identity.translate(bx0, by0).scale(max(bx1 - bx0, 1e-9), max(by1 - by0, 1e-9)))
        else:
            space = matrix

        def number(key, default, axis):
            text = attrs.get(key, default).strip()
            if text.endswith("%"):
                # A percentage is of the bounding box, or of the SVG's viewport in user space.
                return float(text[:-1]) / 100 * (1 if units == "objectBoundingBox" else self.user_size[axis])
            return float(text) if units == "objectBoundingBox" else length(text)

        space = space.transform(gradient_matrix)
        x, y, w, h = box
        if kind == "linearGradient":
            p1 = space.transformPoint((number("x1", "0", 0), number("y1", "0", 1)))
            p2 = space.transformPoint((number("x2", "100%", 0), number("y2", "0", 1)))
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            length_squared = dx * dx + dy * dy
            if length_squared <= 1e-12:
                return stops[-1][1], None
            angle = math.atan2(dy * max(1, h - 1), dx * max(1, w - 1))
            ux, uy = math.cos(angle), math.sin(angle)
            norm = abs(ux) + abs(uy)
            qx, qy = ux / max(1, w - 1) / norm, uy / max(1, h - 1) / norm
            square = qx * qx + qy * qy
            cx, cy = x + (w - 1) / 2, y + (h - 1) / 2
            ends = [(cx - qx / (2 * square), cy - qy / (2 * square)), (cx + qx / (2 * square), cy + qy / (2 * square))]
            s0, s1 = [((ex - p1[0]) * dx + (ey - p1[1]) * dy) / length_squared for ex, ey in ends]
            settings = {"direction": "angled", "angle": round(math.degrees(angle), 6)}
        else:
            cx, cy = number("cx", "50%", 0), number("cy", "50%", 1)
            r = number("r", "50%", 0)
            centre = space.transformPoint((cx, cy))
            edge = space.transformPoint((cx + r, cy))
            radius = math.hypot(edge[0] - centre[0], edge[1] - centre[1])
            if radius <= 1e-9:
                return stops[-1][1], None
            # A Vixl radial gradient reaches t=1 at the box's half width: re-time SVG offsets to that.
            s0, s1 = 0, (w / 2) / radius
            settings = {"direction": "radial", "center": [min(1, max(0, (centre[0] - x) / w)),
                                                          min(1, max(0, (centre[1] - y) / h))]}
        settings["stops"] = self.retime(stops, s0, s1)
        return settings["stops"][0]["color"], settings

    @staticmethod
    def retime(stops, s0, s1):
        """Stops of a gradient between SVG offsets s0 (t=0) and s1 (t=1), padded beyond the SVG gradient's ends."""
        from .colors import hex_of, parse

        def at(s):
            if s <= stops[0][0]:
                return stops[0][1]
            for (o1, c1), (o2, c2) in zip(stops, stops[1:]):
                if o1 <= s <= o2:
                    f = 0 if o2 == o1 else (s - o1) / (o2 - o1)
                    a, b = parse(c1), parse(c2)
                    return hex_of(tuple(a[i] + (b[i] - a[i]) * f for i in range(4)))
            return stops[-1][1]

        span = s1 - s0 if abs(s1 - s0) > 1e-12 else 1e-12
        result = [{"offset": 0, "color": at(s0)}]
        for offset, color in stops:
            t = (offset - s0) / span
            if 0 < t < 1:
                result.append({"offset": round(t, 6), "color": color})
        result.append({"offset": 1, "color": at(s1)})
        result.sort(key=lambda stop: stop["offset"])
        return result[:32]

    # --- images ----------------------------------------------------------------------------------------------------

    def image(self, node, attrs, matrix, clips, opacity):
        from .assets import add_image, decode

        href = attrs.get("href", "")
        match = re.match(r"data:image/(png|jpeg|jpg|webp);base64,", href)
        if not match:
            raise Unsupported("Only embedded PNG, JPEG or WebP SVG images import (data: URIs)")
        try:
            raw = base64.b64decode(href[match.end():], validate=True)
        except ValueError as exc:
            raise VixlError("invalid_svg", "Invalid embedded SVG image") from exc
        image = decode(raw, self.project.limits)
        x, y = length(attrs.get("x", "0")), length(attrs.get("y", "0"))
        w = length(attrs["width"]) if "width" in attrs else image.width
        h = length(attrs["height"]) if "height" in attrs else image.height
        if w <= 0 or h <= 0:
            return []
        preserve = attrs.get("preserveAspectRatio", "xMidYMid meet").split()
        if preserve and preserve[0] != "none":
            if len(preserve) > 1 and preserve[1] == "slice":
                raise Unsupported("Sliced SVG images are not editable")
            k = min(w / image.width, h / image.height)
            fw, fh = image.width * k, image.height * k
            align = preserve[0]
            fx = {"xMin": 0, "xMid": 0.5, "xMax": 1}[align[:4]] if align[:4] in ("xMin", "xMid", "xMax") else 0.5
            fy = {"YMin": 0, "YMid": 0.5, "YMax": 1}.get(align[4:], 0.5)
            x, y, w, h = x + (w - fw) * fx, y + (h - fh) * fy, fw, fh
        a, b, c, d, e, f = matrix
        sx, sy = math.hypot(a, b), math.hypot(c, d)
        if abs(a * c + b * d) > 1e-6 * max(1, sx * sy) or a * d - b * c <= 0:
            raise Unsupported("Skewed or mirrored SVG images are not editable")
        centre = matrix.transformPoint((x + w / 2, y + h / 2))
        rotation = math.degrees(math.atan2(b, a))
        width, height = w * sx, h * sy
        if clips:
            raise Unsupported("Clipped nested SVG images require svg_mode='appearance' or 'auto'")
        asset = add_image(self.project, image)
        name = self.new_name(node, "image")
        operation = {"type": "add", "asset": asset, "name": name, "x": centre[0] - width / 2,
                     "y": centre[1] - height / 2, "width": max(1, width), "height": max(1, height)}
        if abs(rotation) > 1e-6:
            operation["rotation"] = rotation
        if opacity != 1:
            operation["opacity"] = opacity
        self.operations.append(operation)
        return [name]

    # --- text ------------------------------------------------------------------------------------------------------

    def text(self, node, attrs, matrix, props, clips, opacity):
        if clips:
            raise Unsupported("Clipped nested SVG text requires svg_mode='appearance' or 'auto'")
        similar, scale = _similarity(matrix)
        a, b, c, d, _, _ = matrix
        if not similar or a * d - b * c <= 0:
            raise Unsupported("Skewed, stretched or mirrored SVG text is not editable")
        for key in ("textLength", "rotate"):
            if key in attrs:
                raise Unsupported(f"SVG text {key} is not editable")
        lines = []
        state = {"x": None, "y": None, "props": props}

        def first(value):
            values = numbers(value) if value else []
            return values[0] if values else None

        def start(x, y, style):
            lines.append({"x": x, "y": y, "text": "", "props": style, "styles": set()})

        def visit(element, style, own):
            x, y = first(own.get("x")), first(own.get("y"))
            dx, dy = first(own.get("dx")) or 0, first(own.get("dy")) or 0
            new_x = x if x is not None else state["x"]
            new_y = (y if y is not None else state["y"]) + dy
            if dx and lines and lines[-1]["text"]:
                raise Unsupported("SVG text with dx shifts inside a line is not editable")
            if not lines or y is not None or dy or (x is not None and lines[-1]["text"]):
                start((new_x or 0) + dx, new_y, style)
            state["x"], state["y"] = new_x, new_y
            if element.text:
                lines[-1]["text"] += element.text
                if element.text.strip():
                    lines[-1]["styles"].add(self.text_style(style))
            for child in element:
                if foreign(child.tag) or local(child.tag) in ("title", "desc"):
                    pass
                elif local(child.tag) == "tspan":
                    child_attrs = self.attributes(child)
                    self.check_attributes("tspan", child_attrs)
                    child_style = {**style, **{k: v for k, v in child_attrs.items() if k in INHERITED}}
                    if child_attrs.get("display") == "none":
                        continue
                    visit(child, child_style, child_attrs)
                else:
                    raise Unsupported(f"SVG text containing {local(child.tag)!r} is not editable")
                if child.tail:
                    lines[-1]["text"] += child.tail
                    if child.tail.strip():
                        lines[-1]["styles"].add(self.text_style(style))

        state["y"] = 0
        visit(node, props, attrs)
        preserve = node.get(XML_NS + "space") == "preserve"
        for line in lines:
            line["text"] = line["text"] if preserve else re.sub(r"\s+", " ", line["text"].replace("\n", " "))
        if not preserve:
            for line in lines:
                line["text"] = line["text"].strip()
        lines = [line for line in lines if line["text"].strip()]
        if not lines:
            return []
        styles = set().union(*(line["styles"] for line in lines))
        if len(styles) > 1:
            self.warnings.append(f"Text {self.label(node) or lines[0]['text'][:20]!r} mixes styles; it was imported "
                                 "with the style of its first line")
        names = []
        groups = [[lines[0]]]
        for line in lines[1:]:
            previous = groups[-1][-1]
            if abs(line["x"] - previous["x"]) < 0.5 and line["y"] > previous["y"]:
                groups[-1].append(line)
            else:
                groups.append([line])
        label = self.layer_label(node)
        for index, group in enumerate(groups):
            names.append(self.text_layer(node, label if index == 0 else None, group, matrix, scale, opacity))
        if len(names) > 1 and label:
            group_name = self.unique(label)
            self.operations.append({"type": "group", "name": group_name, "targets": names})
            return [group_name]
        return names

    @staticmethod
    def text_style(props):
        return tuple(props.get(key) for key in ("font-family", "font-size", "font-weight", "font-style", "fill",
                                                "text-anchor", "letter-spacing"))

    def font(self, family, weight, style):
        families = [f.strip().strip("'\"") for f in (family or "").split(",") if f.strip()]
        bold = str(weight).strip() in ("bold", "bolder", "600", "700", "800", "900")
        italic = str(style).strip() in ("italic", "oblique")
        name, unknown = match_font(self.project, families, bold, italic, font_map=self.font_map)
        if unknown:
            self.warnings.append(font_warning(unknown))
        return name

    def text_layer(self, node, label, lines, matrix, scale, opacity):
        props = lines[0]["props"]
        size_text = props.get("font-size", "16").strip()
        if size_text.endswith("pt"):
            size = float(size_text[:-2]) * 96 / 72
        else:
            size = length(size_text)
        require(size > 0, "SVG font size must be positive", "invalid_svg")
        size *= scale
        if props.get("fill", "black").strip().startswith("url("):
            raise Unsupported("Gradient-filled SVG text is not editable")
        if props.get("stroke", "none").strip() not in ("none", ""):
            self.warnings.append("SVG text outlines (stroke) are not imported")
        color = self.paint(props, "fill")
        anchor = props.get("text-anchor", "start").strip()
        align = {"start": "left", "middle": "center", "end": "right"}.get(anchor, "left")
        origin = matrix.transformPoint((lines[0]["x"], lines[0]["y"]))
        name = self.unique(label or f"{self.name}-text")
        if not label:
            self.auto_named.add(name)
        operation = {"type": "text", "name": name, "text": "\n".join(line["text"] for line in lines),
                     "size": max(1, round(size)), "color": color, "x": origin[0], "baseline_y": origin[1]}
        if align != "left":
            operation["align"] = align
        if len(lines) > 1:
            gaps = [b["y"] - a["y"] for a, b in zip(lines, lines[1:])]
            operation["line_height"] = min(5, max(0.5, sum(gaps) / len(gaps) * scale / max(1, size)))
        spacing = props.get("letter-spacing", "normal").strip()
        if spacing not in ("normal", "", "0"):
            operation["tracking"] = length(spacing) * scale
        font = self.font(props.get("font-family"), props.get("font-weight", "normal"), props.get("font-style", "normal"))
        if font:
            operation["font"] = font
        if opacity != 1:
            operation["opacity"] = opacity
        rotation = math.degrees(math.atan2(matrix[1], matrix[0]))
        # Rotation is set after measuring (place_anchored): baseline_y places upright text only.
        if align != "left" or abs(rotation) > 1e-6:
            self.anchored.append({"name": name, "anchor": origin, "align": align, "rotation": rotation})
        self.operations.append(operation)
        return name

    def place_anchored(self):
        return anchor_text(self.project, self.operations, self.anchored)

    # --- raster fallback -------------------------------------------------------------------------------------------

    def rasterize(self, node, matrix, inherited, reason):
        """An element Vixl cannot represent, drawn on its own (with the SVG's definitions and stylesheet) into an
        image layer at its place in the stack."""
        from .assets import add_image
        from .imports import render_svg, sanitize_svg

        self.rasters += 1
        if self.rasters > MAX_RASTERIZED:
            raise VixlError("resource_limit", f"SVG has more than {MAX_RASTERIZED} elements Vixl cannot edit; import "
                            "it with svg_mode='appearance' (one image layer)", field="svg", limit=MAX_RASTERIZED)
        width, height = self.size
        root = ET.Element(f"{{{SVG_NS}}}svg", {"width": str(width), "height": str(height),
                                               "viewBox": f"0 0 {width} {height}"})
        if self._definitions is None:
            self._definitions = ET.Element(f"{{{SVG_NS}}}defs")
            for element in self.root.iter():
                if local(element.tag) in ("style",) or (element.get("id") and local(element.tag) in DEFINITIONS
                                                        and local(element.tag) not in ("title", "desc", "metadata")):
                    self._definitions.append(deepcopy(element))
        root.append(self._definitions)
        a, b, c, d, e, f = matrix
        wrapper = ET.SubElement(root, f"{{{SVG_NS}}}g", {
            "transform": f"matrix({a:.12g} {b:.12g} {c:.12g} {d:.12g} {e:.12g} {f:.12g})",
            **{k: v for k, v in inherited.items() if k in INHERITED}})
        copy = deepcopy(node)
        if local(copy.tag) == "svg" and copy is not None:
            copy.tag = f"{{{SVG_NS}}}svg"
        wrapper.append(copy)
        data = ET.tostring(root, encoding="utf-8")
        tree, w, h = sanitize_svg(data, self.project.limits, byte_limit=16 * 1024 * 1024)
        image = render_svg(tree, w, h)
        box = image.getchannel("A").getbbox()
        if not box:
            return []
        crop = image.crop(box)
        asset = add_image(self.project, crop)
        name = self.new_name(node, "image")
        self.operations.append({"type": "add", "asset": asset, "name": name, "x": box[0], "y": box[1],
                                "provenance": {"type": "svg-element", "reason": reason[:300]}})
        self.rasterized.append({"layer": name, "element": local(node.tag), "reason": reason})
        return [name]


def svg_operations(data, project, name, *, fallback=False, report=None, namespace=False, font_map=None):
    """Operations that rebuild an SVG's elements as editable layers (images it embeds are added to ``project``'s
    assets). ``fallback`` draws an unsupported element as an image layer instead of failing; ``report`` (a dict)
    receives ``warnings`` and ``rasterized`` elements. ``namespace`` prefixes the SVG's own layer labels with
    ``name`` (unlabelled elements are always named ``name-kind``). ``font_map`` maps font families the SVG
    names to fonts registered in ``project`` (see ``match_font``)."""
    require(len(data) <= min(project.limits.max_asset_bytes, 16 * 1024 * 1024), "SVG exceeds byte limit",
            "resource_limit")
    try:
        data = data.decode("utf-8-sig").encode("utf-8")
    except UnicodeError as exc:
        raise VixlError("unsupported_svg", "Save SVG as UTF-8 before importing") from exc
    require(b"\x00" not in data, "Save SVG as UTF-8 before importing", "unsupported_svg")
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
            "SVG declarations/entities are unsupported", "unsupported_svg")
    try:
        converter = Converter(data, project, name, fallback=fallback, namespace=namespace, font_map=font_map)
    except ET.ParseError as exc:
        raise VixlError("invalid_svg", str(exc)) from exc
    converter.convert()
    operations = converter.place_anchored()
    require(len(operations) <= project.limits.max_operations, "SVG has too many shapes", "resource_limit")
    if report is not None:
        report["warnings"] = list(dict.fromkeys(converter.warnings))
        report["rasterized"] = converter.rasterized
    return operations
