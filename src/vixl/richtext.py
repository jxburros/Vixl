"""Rich text inside one text box: styled spans, paragraphs, lists and spacing.

A text layer with a ``rich`` record draws several styles in one box. ``layer["text"]`` stays the
plain text (variables, search, checks and timelines read it); ``rich`` adds:

``spans``       ``[{"text", <character style overrides>}]`` whose texts concatenate to the text
``paragraphs``  one settings object per line of the text (lists, alignment, spacing, indent)
``line_height`` (default 1.2), ``paragraph_spacing`` (px after each paragraph), ``list_indent`` (px)
``font_variants`` ``{"bold", "italic", "bold_italic"}`` registered font names

Character styles override the layer's own font, size and color: ``bold``, ``italic``,
``underline``, ``strike``, ``color``, ``size``, ``font``, ``highlight``, ``baseline`` (super or
sub) and ``tracking`` (extra px between letters). Bold and italic use a registered variant when
one exists (``inter-700``, ``inter-400-italic``, or ``font_variants``) and are synthesized
otherwise. One shaped layout (``layout``) feeds PNG, SVG, PDF and PPTX output.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import io
import math
import re
import xml.etree.ElementTree as ET

from .errors import require
from .model import finite
from .notices import note

STYLE_KEYS = ("bold", "italic", "underline", "strike", "color", "size", "font", "highlight", "baseline", "tracking")
PARAGRAPH_KEYS = ("list", "level", "align", "space_before", "space_after", "indent", "line_height", "start")
ROOT_KEYS = ("spans", "paragraphs", "line_height", "paragraph_spacing", "list_indent", "font_variants")
BULLETS = ("•", "◦", "▪", "‣")
MAX_SPANS = 4000
SYNTHETIC_SKEW = math.tan(math.radians(12))
SVG = "{http://www.w3.org/2000/svg}"


# ---------------------------------------------------------------------------------------------
# Content: spans, paragraphs and Markdown


def plain(rich):
    return "".join(span["text"] for span in rich["spans"])


def paragraph_count(text):
    return text.count("\n") + 1


def normalize_spans(spans):
    """Merge neighbouring spans with identical styles and drop empty ones."""
    result = []
    for span in spans:
        if not span.get("text"):
            continue
        style = {k: v for k, v in span.items() if k != "text" and v not in (None, False)}
        if result and {k: v for k, v in result[-1].items() if k != "text"} == style:
            result[-1]["text"] += span["text"]
        else:
            result.append({"text": span["text"], **style})
    return result or [{"text": ""}]


INLINE = re.compile(
    r"\[(?P<btext>[^\]\n]*)\]\{(?P<battrs>[^}\n]*)\}"   # [text]{color=#f00 size=40 bold}
    r"|\*\*\*(?P<bolditalic>.+?)\*\*\*"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|__(?P<under>.+?)__"
    r"|~~(?P<strike>.+?)~~"
    r"|==(?P<mark>.+?)=="
    r"|\^(?P<sup>[^\^\s]+)\^"
    r"|~(?P<sub>[^~\s]+)~"
    r"|(?<![\w*])\*(?P<italic>[^*\n]+?)\*(?![\w*])"
    r"|(?<![\w_])_(?P<italic2>[^_\n]+?)_(?![\w_])"
)


def _attributes(text):
    """``color=#f00 size=40 font=heading bold italic`` → a style dict."""
    style = {}
    for token in re.findall(r'(\w+)=("[^"]*"|\S+)|(\w+)', text):
        key, value, flag = token
        if flag:
            require(flag in ("bold", "italic", "underline", "strike", "super", "sub"),
                    f"Unknown rich-text flag {flag!r}", field="markdown")
            if flag in ("super", "sub"):
                style["baseline"] = flag
            else:
                style[flag] = True
            continue
        value = value.strip('"')
        require(key in ("color", "size", "font", "highlight", "tracking", "baseline"),
                f"Unknown rich-text attribute {key!r}; use color, size, font, highlight, tracking or baseline",
                field="markdown")
        style[key] = float(value) if key in ("size", "tracking") and re.fullmatch(r"-?\d+(\.\d+)?", value) else value
    return style


def _inline(text, base=None):
    """Spans for one line of Markdown-like inline markup."""
    base = base or {}
    spans, cursor = [], 0
    for match in INLINE.finditer(text):
        if match.start() > cursor:
            spans.append({"text": text[cursor:match.start()], **base})
        if match.group("btext") is not None:
            spans.extend(_inline(match.group("btext"), {**base, **_attributes(match.group("battrs"))}))
        else:
            group = match.lastgroup
            inner = match.group(group)
            extra = {"bolditalic": {"bold": True, "italic": True}, "bold": {"bold": True}, "under": {"underline": True}, "strike": {"strike": True},
                     "mark": {"highlight": "#fff176"}, "sup": {"baseline": "super"}, "sub": {"baseline": "sub"},
                     "italic": {"italic": True}, "italic2": {"italic": True}}[group]
            spans.extend(_inline(inner, {**base, **extra}))
        cursor = match.end()
    if cursor < len(text):
        spans.append({"text": text[cursor:], **base})
    return spans


def parse_markdown(markdown):
    """Spans and paragraph settings from a small Markdown dialect. Each line is a paragraph.

    ``- item`` / ``* item`` / ``+ item`` bullets and ``1. item`` numbers (indent two spaces or a tab
    per level), ``# `` to ``### `` headings (bold, larger), ``**bold**``, ``*italic*``,
    ``__underline__``, ``~~strike~~``, ``==highlight==``, ``^super^``, ``~sub~`` and
    ``[text]{color=#e33 size=40 font=heading bold}``. A backslash escapes a marker character."""
    require(isinstance(markdown, str) and len(markdown) <= 100000, "markdown must be text up to 100000 characters",
            field="markdown")
    spans, paragraphs = [], []
    escapes = {}

    def protect(match):
        key = f"\ue000{len(escapes)}\ue001"
        escapes[key] = match.group(1)
        return key

    lines = re.sub(r"\\([*_~=^\[\]{}#\\-])", protect, markdown.replace("\r\n", "\n")).split("\n")
    for index, line in enumerate(lines):
        settings = {}
        expanded = line.replace("\t", "  ")
        indent = len(expanded) - len(expanded.lstrip(" "))
        body = expanded.lstrip(" ")
        heading = re.match(r"(#{1,3})\s+", body)
        bullet = re.match(r"[-*+]\s+", body)
        number = re.match(r"(\d{1,6})[.)]\s+", body)
        base = {}
        if heading:
            body = body[heading.end():]
            base = {"bold": True, "scale": (1.6, 1.3, 1.15)[len(heading.group(1)) - 1]}
        elif bullet:
            body = body[bullet.end():]
            settings = {"list": "bullet", "level": min(8, indent // 2)}
        elif number:
            body = body[number.end():]
            settings = {"list": "number", "level": min(8, indent // 2)}
            if int(number.group(1)) != 1:
                settings["start"] = int(number.group(1))
        line_spans = _inline(body, base)
        for key, value in escapes.items():
            for span in line_spans:
                span["text"] = span["text"].replace(key, value)
        if index:
            spans.append({"text": "\n"})
        spans.extend(line_spans)
        paragraphs.append(settings)
    return spans, paragraphs


def resolve_scale(spans, size):
    """Heading ``scale`` markers become concrete sizes relative to the base size."""
    for span in spans:
        if "scale" in span:
            factor = span.pop("scale")
            span.setdefault("size", round(size * factor, 2))
    return spans


def validate_rich(rich, state, text=None):
    """Validate a stored rich record (on load and on every commit)."""
    from .design import resolve_color
    from .render import color

    require(isinstance(rich, dict) and not set(rich) - set(ROOT_KEYS), "Invalid rich text record", "invalid_project")
    spans = rich.get("spans")
    require(isinstance(spans, list) and 1 <= len(spans) <= MAX_SPANS, f"Rich text needs 1–{MAX_SPANS} spans",
            "invalid_project")
    for span in spans:
        require(isinstance(span, dict) and isinstance(span.get("text"), str) and not set(span) - {"text", *STYLE_KEYS},
                "Invalid rich text span", "invalid_project")
        validate_style(span, state)
    joined = plain(rich)
    if text is not None:
        require(joined == text, "Rich text spans do not match the layer text", "invalid_project")
    paragraphs = rich.get("paragraphs", [])
    require(isinstance(paragraphs, list) and len(paragraphs) == paragraph_count(joined),
            "Rich text needs one paragraph entry per line", "invalid_project")
    for item in paragraphs:
        validate_paragraph(item)
    finite(rich.get("line_height", 1.2), "line_height", 0.5, 5)
    finite(rich.get("paragraph_spacing", 0), "paragraph_spacing", 0, 2000)
    finite(rich.get("list_indent", 0), "list_indent", 0, 2000)
    variants = rich.get("font_variants", {})
    require(isinstance(variants, dict) and not set(variants) - {"bold", "italic", "bold_italic"}
            and all(isinstance(v, str) for v in variants.values()), "Invalid font_variants", "invalid_project")
    for key in ("color", "highlight"):
        for span in spans:
            if key in span:
                color(resolve_color(span[key], state))


def validate_style(style, state):
    for key in ("bold", "italic", "underline", "strike"):
        if key in style:
            require(isinstance(style[key], bool), f"{key} must be true or false", field=key)
    if "size" in style:
        finite(style["size"], "size", 1, 4096)
    if "tracking" in style:
        finite(style["tracking"], "tracking", -1000, 1000)
    if "baseline" in style:
        require(style["baseline"] in ("super", "sub", "normal"), "baseline must be super, sub or normal", field="baseline")
    if "font" in style:
        require(isinstance(style["font"], str) and 0 < len(style["font"]) <= 300, "Invalid span font", field="font")


def validate_paragraph(item):
    require(isinstance(item, dict) and not set(item) - set(PARAGRAPH_KEYS), "Invalid paragraph settings",
            field="paragraphs")
    require(item.get("list", "none") in ("none", "bullet", "number"), "list must be none, bullet or number", field="list")
    level = item.get("level", 0)
    require(isinstance(level, int) and 0 <= level <= 8, "level must be 0–8", field="level")
    require(item.get("align", "left") in ("left", "center", "right", "justify"),
            "align must be left, center, right or justify", field="align")
    for key, high in (("space_before", 2000), ("space_after", 2000), ("indent", 4000)):
        if key in item:
            finite(item[key], key, 0, high)
    if "line_height" in item:
        finite(item["line_height"], "line_height", 0.5, 5)
    if "start" in item:
        require(isinstance(item["start"], int) and 0 <= item["start"] <= 999999, "start must be a whole number", field="start")


# ---------------------------------------------------------------------------------------------
# Fonts


def _registered_name(state, font):
    for name, asset in state.get("fonts", {}).items():
        if asset == font:
            return name
    return None


def variant_font(project, base_font, bold, italic, rich):
    """(font value, synthetic bold, synthetic italic) for a style."""
    if not bold and not italic:
        return base_font, False, False
    fonts = project.state.get("fonts", {})
    variants = rich.get("font_variants", {})
    key = "bold_italic" if bold and italic else "bold" if bold else "italic"
    if variants.get(key) in fonts:
        return fonts[variants[key]], False, False
    name = _registered_name(project.state, base_font)
    match = re.fullmatch(r"(.+)-(\d{3})(-italic)?", name or "")
    if match:
        family, weight, slanted = match[1], int(match[2]), bool(match[3])
        weights = [700, 800, 600, 900] if bold else [weight]
        for w in weights:
            candidate = f"{family}-{w}{'-italic' if italic or slanted else ''}"
            if candidate in fonts:
                return fonts[candidate], False, False
        if italic and not slanted:
            for w in weights:
                if f"{family}-{w}" in fonts:
                    return fonts[f"{family}-{w}"], False, True
        if bold:
            candidate = f"{family}-{weight}{'-italic' if italic else ''}"
            if candidate in fonts:
                return fonts[candidate], True, False
    return base_font, bold, italic


def style_font_data(project, font, text):
    """Font bytes for a font value, with document and bundled fallbacks when ``text`` needs them."""
    from .text import coverage, fallback_chain, primary_font_data, visible_char

    primary = primary_font_data(project, {"font": font, "size": 12})
    if all(not visible_char(c) or ord(c) in coverage(primary) for c in text):
        return primary
    names = [*project.state.get("font_fallbacks", []), "DejaVuSans.ttf"]
    return fallback_chain(primary, [primary_font_data(project, {"font": name, "size": 12}) for name in names])


# ---------------------------------------------------------------------------------------------
# Layout


@dataclass
class Placed:
    """One positioned glyph: ``x`` and ``y`` are its pen position (baseline) in box pixels."""

    data: bytes
    name: str
    x: float
    y: float
    size: float
    color: tuple
    text: str = ""
    bold: bool = False
    italic: bool = False


@dataclass
class Layout:
    width: int
    height: int
    glyphs: list = field(default_factory=list)
    rects: list = field(default_factory=list)  # (x, y, w, h, rgba, kind)
    box: tuple = (0, 0, 0, 0)
    lines: list = field(default_factory=list)  # [(top, baseline, height, paragraph, descent)] for PPTX
    size_scale: float = 1.0


def _metrics(data):
    from .text import face

    primary = data[0] if isinstance(data, tuple) else data
    outline = face(primary)[0]
    upem = outline["head"].unitsPerEm
    return outline["hhea"].ascent / upem, outline["hhea"].descent / upem


def styled_spans(project, layer, variables=None):
    """Spans with every style resolved against the layer: font value, size, color and flags."""
    from .design import resolve_color
    from .render import color, document_variables, substitute

    rich = layer["rich"]
    variables = {**document_variables(project), **(variables or {})}
    base_font = layer.get("font", "DejaVuSans.ttf")
    result = []
    for span in rich["spans"]:
        text = substitute(span["text"], variables)
        font = span.get("font", base_font)
        font, fake_bold, fake_italic = variant_font(project, font, span.get("bold", False), span.get("italic", False), rich)
        result.append({
            "text": text,
            "font": font,
            "size": float(span.get("size", layer.get("size", 48))),
            "color": color(resolve_color(span.get("color", layer.get("color", "white")), project.state, variables)),
            "highlight": color(resolve_color(span["highlight"], project.state, variables)) if span.get("highlight") else None,
            "underline": span.get("underline", False),
            "strike": span.get("strike", False),
            "baseline": span.get("baseline", "normal"),
            "tracking": float(span.get("tracking", 0)),
            "fake_bold": fake_bold,
            "fake_italic": fake_italic,
        })
    return result


def _paragraphs(spans):
    """Split styled spans into paragraphs at newlines."""
    paragraphs = [[]]
    column = 0
    for span in spans:
        parts = span["text"].split("\n")
        for i, part in enumerate(parts):
            if i:
                paragraphs.append([])
                column = 0
            if part:
                # Tabs use four-character stops, including text in preceding styled spans.
                expanded = (" " * (column % 4) + part).expandtabs(4)[column % 4:]
                paragraphs[-1].append({**span, "text": expanded})
                column += len(expanded)
    return paragraphs


def _marker(kind, level, number):
    if kind == "bullet":
        return BULLETS[level % len(BULLETS)]
    style = level % 3
    if style == 0:
        return f"{number}."
    if style == 1:
        letters = ""
        n = number
        while n > 0:
            n, r = divmod(n - 1, 26)
            letters = chr(97 + r) + letters
        return f"{letters}."
    numerals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out, n = "", number
    for value, letters in numerals:
        while n >= value:
            out, n = out + letters, n - value
    return f"{out}."


def _tokens(project, paragraph, scale):
    """Shaped words and spaces: [(kind, glyphs, width, style, ascent, descent)]."""
    from .text import shape

    tokens = []
    for span in paragraph:
        for piece in re.findall(r" +|[^ ]+", span["text"]):
            size = span["size"] * scale * (0.65 if span["baseline"] in ("super", "sub") else 1)
            data = style_font_data(project, span["font"], piece)
            glyphs, advance = shape(data, piece, size)
            tracking = span["tracking"] * scale
            if tracking:
                for i, glyph in enumerate(glyphs):
                    glyph.x += tracking * i
                advance += tracking * len(glyphs)
            ascent, descent = _metrics(data)
            tokens.append({"space": piece.isspace() and "\u00a0" not in piece, "glyphs": glyphs, "width": advance, "style": span, "size": size,
                           "ascent": ascent * span["size"] * scale, "descent": descent * span["size"] * scale,
                           "data": data, "text": piece})
    return tokens


def _split_word(project, token, width):
    """Break a word wider than the line at safe shaping boundaries."""
    from .text import clusters, shape

    primary = token["data"][0] if isinstance(token["data"], tuple) else token["data"]
    pieces, current = [], ""
    for cluster in clusters(primary, token["text"]):
        if current and shape(token["data"], current + cluster, token["size"])[1] > width:
            pieces.append(current)
            current = ""
        current += cluster
    if current:
        pieces.append(current)
    result = []
    for piece in pieces:
        glyphs, advance = shape(token["data"], piece, token["size"])
        result.append({**token, "glyphs": glyphs, "width": advance, "text": piece})
    return result


def layout(project, layer, *, width=None, scale=1.0, variables=None):
    """Lay out a rich text layer. ``width`` wraps lines (default: the text-layout box width);
    ``scale`` multiplies every size, indent and spacing (used to fit text to its box)."""
    from .text import shape

    rich = layer["rich"]
    spans = styled_spans(project, layer, variables)
    settings = rich.get("paragraphs") or []
    box = layer.get("text_layout") or {}
    if width is None and "width" in box:
        width = layer["width"]
    stroke = layer.get("stroke_width", 0)
    available = None if width is None else max(1.0, width - 2 * stroke)
    base_size = float(layer.get("size", 48)) * scale
    line_factor = float(rich.get("line_height", 1.2))
    spacing = float(layer.get("spacing", 0)) * scale
    after_default = float(rich.get("paragraph_spacing", 0)) * scale
    list_indent = float(rich["list_indent"]) * scale if rich.get("list_indent") else base_size * 1.4

    # Pass 1: break every paragraph into lines.
    rows, counters = [], {}
    for index, paragraph in enumerate(_paragraphs(spans)):
        para = settings[index] if index < len(settings) else {}
        kind = para.get("list", "none")
        level = para.get("level", 0)
        marker = None
        if kind != "none":
            for key in [k for k in counters if k[0] > level or (k[0] == level and k[1] != kind)]:
                counters.pop(key)
            counters[(level, kind)] = counters.get((level, kind), para.get("start", 1) - 1) + 1
            marker = _marker(kind, level, counters[(level, kind)])
        else:
            counters.clear()
        left = float(para.get("indent", 0)) * scale + (level * list_indent if kind != "none" or level else 0)
        text_left = left + (list_indent if marker else 0)
        factor = float(para.get("line_height", line_factor))
        before = float(para.get("space_before", 0)) * scale
        after = float(para["space_after"]) * scale if "space_after" in para else after_default
        tokens = _tokens(project, paragraph, scale)
        limit = None if available is None else max(1.0, available - text_left)
        lines, current, x = [], [], 0.0
        for token in tokens:
            if limit is not None and not token["space"] and current and x + token["width"] > limit:
                while current and current[-1]["space"]:
                    current.pop()
                lines.append(current)
                current, x = [], 0.0
            if limit is not None and not token["space"] and not current and token["width"] > limit:
                pieces = _split_word(project, token, limit)
                lines.extend([piece] for piece in pieces[:-1])
                token = pieces[-1]
            current.append(token)
            x += token["width"]
        if current:
            lines.append(current)
        lines = [line for line in lines if line] or [[]]
        for number, line in enumerate(lines):
            if line:
                ascent = max(t["ascent"] for t in line)
                descent = min(t["descent"] for t in line)
            else:
                data = style_font_data(project, layer.get("font", "DejaVuSans.ttf"), " ")
                a, d = _metrics(data)
                ascent, descent = a * base_size, d * base_size
            rows.append({
                "tokens": line, "ascent": ascent, "descent": descent, "factor": factor,
                "marker": marker if number == 0 else None, "left": left, "text_left": text_left,
                "align": para.get("align", layer.get("align", "left")), "limit": limit,
                "last": number == len(lines) - 1, "before": before if number == 0 else 0.0,
                "after": after if number == len(lines) - 1 else 0.0, "paragraph": index,
            })

    # Pass 2: the container width (the box, or the widest line for auto-sized text).
    contents = [sum(t["width"] for t in row["tokens"]) for row in rows]
    container = available if available is not None else max(
        [row["text_left"] + content for row, content in zip(rows, contents)] + [0.0])

    # Pass 3: place glyphs and decorations.
    result = Layout(0, 0, size_scale=scale)
    y = float(stroke)
    widest = 0.0
    for row, content in zip(rows, contents):
        y += row["before"]
        natural = row["ascent"] - row["descent"]
        height = natural * row["factor"]
        baseline = y + row["ascent"] + (height - natural) / 2
        span_width = container - row["text_left"]
        extra, offset = 0.0, 0.0
        gaps = sum(1 for t in row["tokens"] if t["space"])
        if row["align"] == "center":
            offset = (span_width - content) / 2
        elif row["align"] == "right":
            offset = span_width - content
        elif row["align"] == "justify" and available is not None and not row["last"] and gaps:
            extra = (span_width - content) / gaps
        cursor = stroke + row["text_left"] + max(0.0, offset)
        if row["marker"] and row["tokens"]:
            first = row["tokens"][0]
            mstyle = first["style"]
            data = style_font_data(project, mstyle["font"], row["marker"])
            glyphs, advance = shape(data, row["marker"], first["size"])
            mx = stroke + row["left"] + max(0.0, list_indent * 0.75 - advance)
            for glyph in glyphs:
                result.glyphs.append(Placed(glyph.data, glyph.name, mx + glyph.x, baseline + glyph.y, first["size"],
                                            mstyle["color"], glyph.text))
        for token in row["tokens"]:
            style = token["style"]
            shift = {"super": -0.35, "sub": 0.15}.get(style["baseline"], 0.0) * style["size"] * scale
            advance = token["width"] + (extra if token["space"] else 0)
            if style["highlight"]:
                result.rects.append((cursor, baseline - token["ascent"], advance, token["ascent"] - token["descent"],
                                     style["highlight"], "highlight"))
            # Space glyphs draw nothing, but PDF text extraction reads them as word breaks.
            for glyph in token["glyphs"]:
                result.glyphs.append(Placed(glyph.data, glyph.name, cursor + glyph.x, baseline + shift + glyph.y,
                                            token["size"], style["color"], glyph.text, style["fake_bold"],
                                            style["fake_italic"]))
            thickness = max(1.0, token["size"] * 0.06)
            if style["underline"]:
                result.rects.append((cursor, baseline + token["size"] * 0.12, advance, thickness, style["color"], "underline"))
            if style["strike"]:
                result.rects.append((cursor, baseline - token["size"] * 0.3, advance, thickness, style["color"], "strike"))
            cursor += advance
        widest = max(widest, cursor + stroke)
        result.lines.append((y, baseline, height, row["paragraph"], row["descent"]))
        y += height + spacing + row["after"]
    y -= spacing if rows else 0
    result.width = int(width) if width is not None else max(1, math.ceil(widest))
    result.height = max(1, math.ceil(y + stroke))
    result.box = (0, 0, widest, y + stroke)
    return result


def fitted(project, layer, variables=None):
    """The layout, shrunk when the text box has ``fit`` so everything fits its width and height."""
    box = layer.get("text_layout") or {}
    base = layout(project, layer, variables=variables)
    if not box.get("fit") or "width" not in box:
        return base
    height = layer["height"]
    if base.height <= height and _fits_width(base, layer["width"]):
        return base
    low, high, best = 0.05, 1.0, None
    for _ in range(14):
        middle = (low + high) / 2
        candidate = layout(project, layer, scale=middle, variables=variables)
        if candidate.height <= height and _fits_width(candidate, layer["width"]):
            low, best = middle, candidate
        else:
            high = middle
    return best or layout(project, layer, scale=low, variables=variables)


def _fits_width(result, width):
    return result.box[2] <= width + 0.5


def measure(project, layer, variables=None):
    """(width, height, box) for auto-sized rich text, like ``text_metrics``."""
    result = layout(project, layer, variables=variables)
    return result.width, result.height, (0, 0, result.width, result.height)


# ---------------------------------------------------------------------------------------------
# Drawing


def append_svg(parent, result, layer, project, *, node=None, motion=None):
    """Add the layout's highlights, glyph paths and decorations to an SVG element. ``motion``
    (kinetic type) gives each glyph a ``(matrix prefix, opacity, fill or None)``."""
    from .design import resolve_color
    from .render import color
    from .text import face, glyph_outline

    def add(kind, attrs):
        if node is not None:
            return node(parent, kind, **attrs)
        return ET.SubElement(parent, SVG + kind, {k.replace("_", "-"): str(v) for k, v in attrs.items()})

    def paint(rgba):
        return f"rgb({rgba[0]},{rgba[1]},{rgba[2]})", rgba[3] / 255

    for x, y, w, h, rgba, kind in result.rects:
        if kind == "highlight":
            fill, alpha = paint(rgba)
            add("rect", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}", "height": f"{h:.3f}", "fill": fill,
                         "fill_opacity": alpha})
    outline_width = layer.get("stroke_width", 0)
    outline_color = color(resolve_color(layer.get("stroke_color", "black"), project.state))
    for index, glyph in enumerate(result.glyphs):
        path, _ = glyph_outline(glyph.data, glyph.name)
        if not path:
            continue
        upem = face(glyph.data)[0]["head"].unitsPerEm
        f = glyph.size / upem
        skew = f * SYNTHETIC_SKEW if glyph.italic else 0
        fill, alpha = paint(glyph.color)
        transform = f"matrix({f:.6f} 0 {skew:.6f} {-f:.6f} {glyph.x:.3f} {glyph.y:.3f})"
        extra = {}
        if motion:
            from .kinetic import multiply

            prefix, opacity, override = motion[index]
            transform = "matrix(" + " ".join(f"{v:.6f}" for v in multiply(prefix, (f, 0, skew, -f, glyph.x, glyph.y))) + ")"
            if override:
                fill, alpha = paint(override)
            if opacity < 1:
                extra["opacity"] = f"{opacity:.4f}"
        attrs = {"d": path, "transform": transform, "fill": fill, "fill_opacity": alpha, **extra}
        width = 0.0
        stroke = fill
        stroke_alpha = alpha
        if glyph.bold:
            width = glyph.size * 0.045 / f
        if outline_width:
            width = max(width, 2 * outline_width / f)
            stroke, stroke_alpha = paint(outline_color)
        if width:
            attrs.update(stroke=stroke, stroke_opacity=stroke_alpha, stroke_width=f"{width:.3f}", stroke_linejoin="round",
                         paint_order="stroke fill")
        add("path", attrs)
    for x, y, w, h, rgba, kind in result.rects:
        if kind != "highlight":
            fill, alpha = paint(rgba)
            add("rect", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}", "height": f"{h:.3f}", "fill": fill,
                         "fill_opacity": alpha})


def render(project, layer):
    """The rich text layer as an RGBA image of its box (or natural size when auto-sized)."""
    import resvg_py
    from PIL import Image

    result = fitted(project, layer)
    width, height = (layer["width"], layer["height"]) if layer.get("text_layout") else (result.width, result.height)
    if layer.get("_kinetic"):
        from .kinetic import padding, rich_motion, svg_canvas

        moves, boxes = rich_motion(project, layer, result)
        margin = padding(boxes, [m[0] for m in moves], width, height, layer.get("stroke_width", 0) + 0.05 * layer.get("size", 48))
        size, attrs = svg_canvas(width, height, *margin)
        project.limits.size(*size)
        root = ET.Element(SVG + "svg", attrs)
        append_svg(root, result, layer, project, motion=moves)
        image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode")))).convert("RGBA")
        image.info["vixl_vector_overflow"] = True
        return image
    project.limits.size(width, height)
    root = ET.Element(SVG + "svg", {"width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}"})
    append_svg(root, result, layer, project)
    data = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode"))
    return Image.open(io.BytesIO(data)).convert("RGBA")


def active(layer):
    """Whether a text layer draws its rich record: the record must still match the text (a
    timeline that replaced the text falls back to plain drawing; text-set rewrites the record)."""
    rich = layer.get("rich")
    return bool(rich) and plain(rich) == layer.get("text")


def fonts_used(layer, fallback="DejaVuSans.ttf"):
    """The stored font of each run of visible text a text layer draws: the layer font for plain
    text, and for rich text each span's own font (``font`` on the span) or else the layer font."""
    base = layer.get("font", fallback)
    if not active(layer):
        return [base]
    used = [span.get("font", base) for span in layer["rich"]["spans"] if span["text"].strip()]
    return used or [base]


def glyph_coverage(project, layer):
    """``text.glyph_coverage`` for rich text: each span is checked against its own font, then the
    document and bundled fallbacks, the way it is drawn."""
    from .text import glyph_coverage as span_coverage

    missing, fallback = set(), set()
    for span in styled_spans(project, layer):
        report = span_coverage(project, {"font": span["font"], "text": span["text"]})
        missing.update(report["missing"])
        fallback.update(report["fallback"])
    return {"missing": sorted(missing), "fallback": sorted(fallback - missing)}


def fill_variables(rich, variables):
    """Fill ``${variable}`` references inside the spans of a resolved layer's rich record. The
    resolver substitutes the layer text the same way, so the record keeps matching it (``active``)
    and each substituted value inherits the formatting of the span it sits in."""
    from .render import substitute

    for span in rich["spans"]:
        span["text"] = substitute(span["text"], variables)


# ---------------------------------------------------------------------------------------------
# Operations


TYPES = ("rich-text", "text-style")


def schemas(add):
    from .schema import S, N, B, COORD, SIZE, FONT

    style = {"bold": B, "italic": B, "underline": B, "strike": B, "color": S, "size": N, "font": FONT, "highlight": S,
             "baseline": {"enum": ["super", "sub", "normal"]}, "tracking": N}
    para = {"list": {"enum": ["none", "bullet", "number"]}, "level": {"type": "integer", "minimum": 0, "maximum": 8},
            "align": {"enum": ["left", "center", "right", "justify"]}, "space_before": N, "space_after": N, "indent": N,
            "line_height": N, "start": {"type": "integer", "minimum": 0}}
    obj = {"type": "object"}
    add("rich-text", {"name": S, "markdown": S, "spans": {"type": "array", "items": obj, "maxItems": MAX_SPANS},
                      "paragraphs": {"type": "array", "items": obj}, "font": FONT, "size": N, "color": S,
                      "align": {"enum": ["left", "center", "right", "justify"]}, "line_height": N, "paragraph_spacing": N,
                      "list_indent": N, "font_variants": obj, "width": SIZE, "height": SIZE, "fit": B, "x": COORD,
                      "y": COORD}, anyOf=[{"required": ["markdown"]}, {"required": ["spans"]}])
    add("text-style", {"match": {**S, "description": "Style every occurrence of this text (see occurrence)."},
                       "occurrence": {"anyOf": [{"type": "integer", "minimum": 1}, {"enum": ["all"]}]},
                       "start": {"type": "integer", "minimum": 0, "description": "First character of a range (with end)."},
                       "end": {"type": "integer", "minimum": 0},
                       "paragraphs": {"anyOf": [{"type": "array", "items": {"type": "integer", "minimum": 0}}, {"enum": ["all"]}]},
                       "clear": B, **style, **{{"align": "paragraph_align", "start": "number_start"}.get(k, k): v
                                               for k, v in para.items()},
                       "paragraph_spacing": N, "list_indent": N, "font_variants": obj},
        description="Style part of a text layer: a matched phrase, a start/end character range or paragraphs. With no range "
        "it styles all the text; on a plain layer, color/size/font alone act as text-set. To change the layer's content "
        "or overall color/size/font use text-set. Plain text becomes rich text the first time.")


def _resolve_span_fonts(project, spans):
    from .operations import embed_font_file
    from .render import resolve_font

    for span in spans:
        if "font" in span:
            holder = {"font": resolve_font(project, span["font"])[0]}
            embed_font_file(project, holder)
            span["font"] = holder["font"]
    return spans


def _resolve_variants(project, variants):
    fonts = project.state.get("fonts", {})
    for key, name in (variants or {}).items():
        require(key in ("bold", "italic", "bold_italic"), "font_variants keys are bold, italic and bold_italic",
                field="font_variants")
        require(name in fonts, f"font_variants.{key} must name a registered font; registered: {', '.join(fonts) or 'none'}",
                field=f"font_variants.{key}")
    return dict(variants or {})


def _make_rich(project, op, size):
    if "markdown" in op:
        spans, paragraphs = parse_markdown(op["markdown"])
    else:
        spans = deepcopy(op["spans"])
        require(all(isinstance(s, dict) and isinstance(s.get("text"), str) for s in spans), "Each span needs text",
                field="spans")
        for span in spans:
            unknown = sorted(set(span) - {"text", *STYLE_KEYS})
            require(not unknown, f"Unknown span field(s) {', '.join(unknown)}; allowed: text, {', '.join(STYLE_KEYS)}",
                    field="spans")
        paragraphs = None
    spans = normalize_spans(resolve_scale(spans, size))
    count = paragraph_count(plain({"spans": spans}))
    if op.get("paragraphs") is not None:
        paragraphs = deepcopy(op["paragraphs"])
        require(len(paragraphs) == count, f"paragraphs needs {count} entries, one per line", field="paragraphs")
    paragraphs = paragraphs or [{} for _ in range(count)]
    for item in paragraphs:
        validate_paragraph(item)
    rich = {"spans": _resolve_span_fonts(project, spans), "paragraphs": paragraphs}
    for key in ("line_height", "paragraph_spacing", "list_indent"):
        if key in op:
            rich[key] = op[key]
    if op.get("font_variants"):
        rich["font_variants"] = _resolve_variants(project, op["font_variants"])
    return rich


def execute(project, op):
    from .operations import execute as apply

    if op["type"] == "rich-text":
        layer = project.layer(op["target"]) if op.get("target") else None
        if layer is None:
            base = {k: op[k] for k in ("name", "font", "size", "color", "x", "y") if k in op}
            align = op.get("align", "left")
            apply(project, {"type": "text", "text": "x", **base, "align": "center" if align == "center" else "right"
                            if align == "right" else "left"})
            layer = project.layer()
        else:
            require(layer["type"] == "text", "rich-text needs a text layer", field="target")
            for key in ("size", "color"):
                if key in op:
                    layer[key] = op[key]
            if "font" in op:
                apply(project, {"type": "text-set", "target": layer["id"], "font": op["font"]})
        rich = _make_rich(project, op, float(layer.get("size", 48)))
        if "align" in op:
            for item in rich["paragraphs"]:
                item.setdefault("align", op["align"])
        layer["rich"] = rich
        layer["text"] = plain(rich)
        if "width" in op or "height" in op:
            settings = layer.setdefault("text_layout", {})
            for key in ("width", "height"):
                if key in op:
                    settings[key] = op[key]
                    layer[key] = op[key]
            if "fit" in op:
                settings["fit"] = op["fit"]
            layer["auto_size"] = False
            if "height" not in op:
                layer["height"] = layout(project, layer).height
                settings["height"] = layer["height"]
        if not layer.get("text_layout"):
            layer["width"], layer["height"], _ = measure(project, layer)
            layer["auto_size"] = True
        if op.get("x") == "center" or op.get("y") == "center":
            c = project.state["canvas"]
            if op.get("x") == "center":
                layer["x"] = (c["width"] - layer["width"]) / 2
            if op.get("y") == "center":
                layer["y"] = (c["height"] - layer["height"]) / 2
        return
    layer = project.layer(op.get("target"))
    require(layer["type"] == "text", "text-style needs a text layer", field="target")
    whole = whole_layer_style(op) if not active(layer) else None
    if whole:
        # No range and nothing that needs spans: this is a layer-level change, which text-set makes
        # without turning the layer into rich text (where text-set could no longer recolour it).
        validate_style(whole, project.state)
        apply(project, {"type": "text-set", "target": layer["id"], **whole})
        note(project, f"text-style on {layer['name']!r} had no match, start/end or paragraphs, so it set the layer's "
                      f"{', '.join(whole)} as text-set does; give a range to style part of the text")
        return
    if not layer.get("rich") or plain(layer["rich"]) != layer["text"]:
        layer["rich"] = {"spans": [{"text": layer["text"]}], "paragraphs": [{} for _ in range(paragraph_count(layer["text"]))]}
    rich = layer["rich"]
    style = {k: op[k] for k in STYLE_KEYS if k in op}
    validate_style(style, project.state)
    if style.get("font"):
        style["font"] = _resolve_span_fonts(project, [{"font": style["font"]}])[0]["font"]
    text = layer["text"]
    ranges = []
    if "match" in op:
        require(isinstance(op["match"], str) and op["match"], "match needs text", field="match")
        positions = [m.start() for m in re.finditer(re.escape(op["match"]), text)]
        require(positions, f"{op['match']!r} does not appear in {layer['name']!r}", field="match")
        which = op.get("occurrence", "all")
        if which != "all":
            require(which <= len(positions), f"{op['match']!r} appears {len(positions)} time(s)", field="occurrence")
            positions = [positions[which - 1]]
        ranges = [(p, p + len(op["match"])) for p in positions]
    elif "start" in op or "end" in op:
        start, end = op.get("start", 0), op.get("end", len(text))
        require(0 <= start < end <= len(text), f"start and end must lie in 0–{len(text)}", field="start")
        ranges = [(start, end)]
    elif style or op.get("clear"):
        ranges = [(0, len(text))]
    if ranges and (style or op.get("clear")):
        chars = []
        for span in rich["spans"]:
            own = {k: v for k, v in span.items() if k != "text"}
            chars.extend((ch, own) for ch in span["text"])
        for start, end in ranges:
            for i in range(start, end):
                ch, own = chars[i]
                own = {} if op.get("clear") else dict(own)
                for key, value in style.items():
                    if value is False or value == "normal":
                        own.pop(key, None)
                    else:
                        own[key] = value
                chars[i] = (ch, own)
        rich["spans"] = normalize_spans([{"text": ch, **own} for ch, own in chars])
    para = {k: op[k] for k in ("list", "level", "space_before", "space_after", "indent") if k in op}
    if "paragraph_align" in op:
        para["align"] = op["paragraph_align"]
    if "number_start" in op:
        para["start"] = op["number_start"]
    if "line_height" in op and "paragraphs" in op:
        para["line_height"] = op["line_height"]
    if para:
        validate_paragraph(para)
        targets = op.get("paragraphs", "all")
        count = len(rich["paragraphs"])
        indices = range(count) if targets == "all" else targets
        for index in indices:
            require(0 <= index < count, f"Paragraph {index} does not exist; the text has {count}", field="paragraphs")
            rich["paragraphs"][index].update(para)
            if rich["paragraphs"][index].get("list") == "none":
                rich["paragraphs"][index].pop("list")
    for key in ("paragraph_spacing", "list_indent"):
        if key in op:
            rich[key] = op[key]
    if "line_height" in op and "paragraphs" not in op:
        rich["line_height"] = op["line_height"]
    if op.get("font_variants"):
        rich["font_variants"] = _resolve_variants(project, op["font_variants"])
    if layer.get("auto_size", True) and not (layer.get("text_layout") or {}).get("width"):
        layer["width"], layer["height"], _ = measure(project, layer)


TEXT_STYLE_FIELDS = ("match", "occurrence", "start", "end", "paragraphs", "clear", "bold", "italic", "underline", "strike",
                     "highlight", "baseline", "tracking", "list", "level", "paragraph_align", "space_before", "space_after",
                     "indent")
TEXT_SET_FIELDS = ("text", "spacing", "stroke_width", "stroke_color", "align", "content")


def field_hint(kind, extras):
    """A sentence (empty when none applies) steering a text-set or text-style that was given the other's fields."""
    if kind == "text-set" and any(k in TEXT_STYLE_FIELDS for k in extras):
        return (". text-set changes a whole layer (text, color, size, font, align, spacing, stroke); to style part of the "
                "text or set bold, italic, tracking, highlight or paragraph settings use text-style")
    if kind == "text-style" and any(k in TEXT_SET_FIELDS for k in extras):
        return (". text-style styles ranges and paragraphs of rich text; use text-set to change the layer's text, spacing, "
                "stroke or alignment, or rich-text to replace formatted content")
    return ""


def whole_layer_style(op):
    """The color, size and font of a text-style that styles a whole plain layer and nothing else
    (what text-set sets), or None when the operation needs rich text."""
    layer_level = {k: op[k] for k in ("color", "size", "font") if k in op}
    others = set(op) - {"type", "target", *layer_level}
    if not layer_level or others or ("size" in layer_level and layer_level["size"] != int(layer_level["size"])):
        return None
    return {k: int(v) if k == "size" else v for k, v in layer_level.items()}


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser

    p = Parser(prog=f"vixl {cmd}")
    if cmd == "rich-text":
        p.add_argument("markdown")
        p.add_argument("--name")
        p.add_argument("--target")
        p.add_argument("--font")
        p.add_argument("--color")
        p.add_argument("--align", choices=["left", "center", "right", "justify"])
        for key in ("size", "line-height", "paragraph-spacing", "list-indent", "x", "y"):
            p.add_argument("--" + key, type=float)
        for key in ("width", "height"):
            p.add_argument("--" + key, type=int)
        p.add_argument("--fit", action="store_true", default=None)
        data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
        data["markdown"] = data["markdown"].replace("\\n", "\n")
        return {"type": cmd, **data}
    p.add_argument("target")
    p.add_argument("--match")
    p.add_argument("--occurrence", type=lambda v: v if v == "all" else int(v))
    for key in ("start", "end", "level", "number-start"):
        p.add_argument("--" + key, type=int)
    for flag in ("bold", "italic", "underline", "strike", "clear"):
        p.add_argument("--" + flag, action="store_true", default=None)
    for key in ("color", "font", "highlight"):
        p.add_argument("--" + key)
    p.add_argument("--baseline", choices=["super", "sub", "normal"])
    for key in ("size", "tracking", "space-before", "space-after", "indent", "line-height", "paragraph-spacing", "list-indent"):
        p.add_argument("--" + key, type=float)
    p.add_argument("--list", choices=["none", "bullet", "number"])
    p.add_argument("--align", dest="paragraph_align", choices=["left", "center", "right", "justify"])
    p.add_argument("--paragraphs", type=lambda v: v if v == "all" else [int(x) for x in v.split(",")])
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
