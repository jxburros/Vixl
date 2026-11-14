"""Photoshop type layers: the type-tool block (``TySh``) that keeps a text layer's copy editable.

A PSD type layer is an ordinary pixel layer with one additional layer information block, ``TySh``:
a version, a 2x3 transform that places the text's origin on the canvas, a ``TxLr`` descriptor (the
text, its bounds and an ``EngineData`` blob) and a ``warp`` descriptor. ``EngineData`` is a
PostScript-like dictionary holding the editor's text, the paragraph and style runs and the font list.

The writer covers one style run: a PostScript font name, size, colour, tracking, leading, alignment and
point or box text. The reader parses the same structures back (and a third party's), bounded: nesting
depth, item counts and the bytes read are limited, and it never allocates from a declared length before
checking that the bytes exist.

Format reference: Adobe Photoshop File Format Specification ("Type tool object setting", "Descriptor
structure"). ``EngineData`` is not specified there; its layout follows what Photoshop writes.
"""

import math
import struct

from .errors import VixlError

MAX_DEPTH = 32
MAX_ITEMS = 20000  # descriptor items and EngineData tokens read from one block
JUSTIFICATION = {"left": 0, "right": 1, "center": 2, "justify": 3}
ALIGNMENTS = {value: key for key, value in JUSTIFICATION.items()}
# Layer fields a native type layer carries (or that do not change how the text draws). A field outside
# this set with a value keeps the layer as pixels, so a text feature added later is never dropped.
PLAIN_FIELDS = frozenset({
    "id", "name", "type", "parent", "x", "y", "width", "height", "rotation", "flip_x", "flip_y", "opacity", "blend",
    "visible", "effects", "mask", "constraints", "text", "font", "color", "align", "auto_size", "size", "line_height",
    "spacing", "tracking", "text_layout", "text_transform", "rich", "alt", "locked", "role", "notes", "provenance", "lang",
    "hide_if_empty", "stage",
})
LAYOUT_FIELDS = frozenset({"width", "height", "wrap", "fit"})
NEUTRAL = (None, False, 0, "", "none", "normal", "top", [], {})


class Malformed(ValueError):
    """The block does not follow the format (or exceeds the reader's bounds)."""


# ------------------------------------------------------------------------------------------- descriptors

def _unicode(text):
    raw = (text + "\0").encode("utf-16-be")  # the count includes the terminator
    return struct.pack(">I", len(raw) // 2) + raw


def _key(key):
    return struct.pack(">I", 0 if len(key) == 4 else len(key)) + key


def text_value(value):
    return b"TEXT" + _unicode(value)


def enum_value(kind, value):
    return b"enum" + _key(kind) + _key(value)


def unit_value(value, unit=b"#Pnt"):
    return b"UntF" + unit + struct.pack(">d", value)


def double_value(value):
    return b"doub" + struct.pack(">d", value)


def long_value(value):
    return b"long" + struct.pack(">i", value)


def data_value(value):
    return b"tdta" + struct.pack(">I", len(value)) + value


def descriptor(class_id, items):
    """A descriptor: an empty name, the class ID and ``[(key, encoded value)]``."""
    return _unicode("") + _key(class_id) + struct.pack(">I", len(items)) + b"".join(_key(k) + v for k, v in items)


def object_value(class_id, items):
    return b"Objc" + descriptor(class_id, items)


class Reader:
    """A cursor over bytes that refuses to read past the end."""

    def __init__(self, data, pos=0, end=None):
        self.data, self.pos, self.end = data, pos, len(data) if end is None else end
        self.items = 0

    def take(self, count):
        if count < 0 or self.pos + count > self.end:
            raise Malformed("truncated data")
        start, self.pos = self.pos, self.pos + count
        return bytes(self.data[start:self.pos])

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def count(self, amount=1):
        self.items += amount
        if self.items > MAX_ITEMS:
            raise Malformed("too many items")


def _read_unicode(reader):
    (count,) = reader.unpack(">I")
    return reader.take(2 * count).decode("utf-16-be", "replace").rstrip("\0")


def _read_key(reader):
    (length,) = reader.unpack(">I")
    return reader.take(length or 4)


def read_descriptor(reader, depth=0):
    """``{key: value}`` of a descriptor; nested objects are dicts, lists are lists, enums their value key."""
    if depth > MAX_DEPTH:
        raise Malformed("descriptor nesting is too deep")
    _read_unicode(reader)
    _read_key(reader)
    (count,) = reader.unpack(">I")
    result = {}
    for _ in range(count):
        reader.count()
        key = _read_key(reader).decode("latin-1")
        result[key] = _read_value(reader, depth)
    return result


def _read_value(reader, depth):
    kind = reader.take(4)
    if kind == b"TEXT":
        return _read_unicode(reader)
    if kind == b"enum":
        _read_key(reader)
        return _read_key(reader).decode("latin-1")
    if kind in (b"Objc", b"GlbO"):
        return read_descriptor(reader, depth + 1)
    if kind == b"UntF":
        reader.take(4)
        return reader.unpack(">d")[0]
    if kind == b"doub":
        return reader.unpack(">d")[0]
    if kind == b"long":
        return reader.unpack(">i")[0]
    if kind == b"comp":
        return reader.unpack(">q")[0]
    if kind == b"bool":
        return bool(reader.unpack(">B")[0])
    if kind in (b"tdta", b"alis"):
        (length,) = reader.unpack(">I")
        return reader.take(length)
    if kind == b"VlLs":
        if depth >= MAX_DEPTH:
            raise Malformed("descriptor nesting is too deep")
        (count,) = reader.unpack(">I")
        values = []
        for _ in range(count):
            reader.count()
            values.append(_read_value(reader, depth + 1))
        return values
    if kind in (b"type", b"GlbC"):
        _read_unicode(reader)
        return _read_key(reader).decode("latin-1")
    raise Malformed(f"unsupported descriptor value {kind!r}")


# -------------------------------------------------------------------------------------------- EngineData

def _number(value):
    if isinstance(value, bool):
        return b"true" if value else b"false"
    if isinstance(value, int):
        return str(value).encode()
    text = f"{value:.5f}".rstrip("0")
    return (text + "0" if text.endswith(".") else text).encode()  # a float keeps its decimal point


def _string(value):
    raw = b"\xfe\xff" + value.encode("utf-16-be")
    for char in (b"\\", b"(", b")"):
        raw = raw.replace(char, b"\\" + char)
    return b"(" + raw + b")"


def _engine(value, indent):
    tabs = b"\t" * indent
    if isinstance(value, dict):
        out = [tabs + b"<<"]
        for key, item in value.items():
            name = tabs + b"\t/" + key.encode()
            if isinstance(item, dict):
                out += [name, _engine(item, indent + 1)]
            elif isinstance(item, list) and item and isinstance(item[0], dict):
                out += [name + b" [", *(_engine(entry, indent + 1) for entry in item), tabs + b"\t]"]
            else:
                out.append(name + b" " + _engine(item, indent + 1))
        out.append(tabs + b">>")
        return b"\n".join(out)
    if isinstance(value, list):
        return b"[ " + b"".join(_engine(item, indent) + b" " for item in value) + b"]"
    if isinstance(value, str):
        return _string(value)
    return _number(value)


def engine_data(value):
    """``value`` (dicts, lists, strings, numbers, booleans) in the EngineData syntax."""
    return b"\n\n" + _engine(value, 0)


def parse_engine_data(data):
    """The dictionary an EngineData blob holds; strings are decoded from UTF-16."""
    pos, size = 0, len(data)
    stack, key, root, tokens = [], [], None, 0

    def put(value):
        nonlocal root
        if not stack:
            root = value if root is None else root
        elif isinstance(stack[-1], list):
            stack[-1].append(value)
        elif key[-1] is not None:
            stack[-1][key[-1]] = value
            key[-1] = None

    while pos < size:
        char = data[pos:pos + 1]
        if char.isspace() or char == b"\0":
            pos += 1
            continue
        tokens += 1
        if tokens > MAX_ITEMS * 8:
            raise Malformed("EngineData is too large")
        if data[pos:pos + 2] == b"<<" or char == b"[":
            if len(stack) >= MAX_DEPTH:
                raise Malformed("EngineData nesting is too deep")
            value = {} if char == b"<" else []
            put(value)
            stack.append(value)
            key.append(None)
            pos += 2 if char == b"<" else 1
        elif data[pos:pos + 2] == b">>" or char == b"]":
            if not stack or isinstance(stack[-1], list) != (char == b"]"):
                raise Malformed("unbalanced EngineData")
            stack.pop()
            key.pop()
            pos += 2 if char == b">" else 1
        elif char == b"(":
            pos += 1
            raw = bytearray()
            while True:
                if pos >= size:
                    raise Malformed("unterminated EngineData string")
                byte = data[pos]
                pos += 1
                if byte == 0x29:
                    break
                if byte == 0x5C:
                    if pos >= size:
                        raise Malformed("unterminated EngineData string")
                    byte = data[pos]
                    pos += 1
                raw.append(byte)
            if raw[:2] == b"\xfe\xff":
                put(bytes(raw[2:]).decode("utf-16-be", "replace"))
            else:
                put(bytes(raw).decode("latin-1"))
        else:
            end = pos
            while end < size and not data[end:end + 1].isspace() and data[end:end + 1] not in (b"[", b"]", b"(", b"<", b">"):
                end += 1
            if end == pos:
                raise Malformed("unexpected character in EngineData")
            word = bytes(data[pos:end])
            pos = end
            if word.startswith(b"/"):
                if not stack or isinstance(stack[-1], list):
                    put(word[1:].decode("latin-1"))
                else:
                    key[-1] = word[1:].decode("latin-1")
            elif word in (b"true", b"false"):
                put(word == b"true")
            else:
                try:
                    number = float(word) if b"." in word or b"e" in word.lower() else int(word)
                except ValueError as exc:
                    raise Malformed("invalid EngineData token") from exc
                if not math.isfinite(number):
                    raise Malformed("invalid EngineData number")
                put(number)
    if stack or not isinstance(root, dict):
        raise Malformed("unbalanced EngineData")
    return root


# -------------------------------------------------------------------------------------------- type block

def _paragraph(justification):
    return {
        "Justification": justification, "FirstLineIndent": 0.0, "StartIndent": 0.0, "EndIndent": 0.0,
        "SpaceBefore": 0.0, "SpaceAfter": 0.0, "AutoHyphenate": False, "HyphenatedWordSize": 6, "PreHyphen": 2,
        "PostHyphen": 2, "ConsecutiveHyphens": 8, "Zone": 36.0, "WordSpacing": [0.8, 1.0, 1.33],
        "LetterSpacing": [0.0, 0.0, 0.0], "GlyphSpacing": [1.0, 1.0, 1.0], "AutoLeading": 1.2, "LeadingType": 0,
        "Hanging": False, "Burasagari": False, "KinsokuOrder": 0, "EveryLineComposer": False,
    }


def _style(size, leading, tracking, rgb):
    black = {"Type": 1, "Values": [1.0, 0.0, 0.0, 0.0]}
    return {
        "Font": 0, "FontSize": float(size), "FauxBold": False, "FauxItalic": False, "AutoLeading": False,
        "Leading": float(leading), "HorizontalScale": 1.0, "VerticalScale": 1.0, "Tracking": int(tracking),
        "AutoKerning": True, "Kerning": 0, "BaselineShift": 0.0, "FontCaps": 0, "FontBaseline": 0,
        "Underline": False, "Strikethrough": False, "Ligatures": True, "DLigatures": False, "BaselineDirection": 2,
        "Tsume": 0.0, "StyleRunAlignment": 2, "Language": 0, "NoBreak": False,
        "FillColor": {"Type": 1, "Values": [1.0, *(float(round(v / 255, 5)) for v in rgb)]}, "StrokeColor": black,
        "FillFlag": True, "StrokeFlag": False, "FillFirst": True, "YUnderline": 1, "OutlineWidth": 1.0,
        "CharacterDirection": 0, "HindiNumbers": False, "Kashida": 1, "DiacriticPos": 2,
    }


def type_block(text, *, font, size, color=(0, 0, 0), tracking=0, leading=None, align="left",
               transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), box=None, bounds=(0.0, 0.0, 0.0, 0.0)):
    """The data of a ``TySh`` block.

    ``text`` uses ``\\n`` between lines; ``font`` is a PostScript name; ``size`` and ``leading`` are in pixels;
    ``tracking`` is in thousandths of an em; ``transform`` (xx, xy, yx, yy, tx, ty) maps the text's origin (the
    first baseline's start, centre or end for point text; the box's top-left for box text) onto the canvas; ``box``
    is the (width, height) of box text, None for point text; ``bounds`` (left, top, right, bottom) is the text's
    extent around that origin."""
    content = text.replace("\r\n", "\n").replace("\n", "\r")
    length = len((content + "\r").encode("utf-16-be")) // 2
    leading = float(size * 1.2 if leading is None else leading)
    paragraph = _paragraph(JUSTIFICATION[align])
    style = _style(size, leading, tracking, color[:3])
    shape = 1 if box else 0
    cookie = {"ShapeType": shape}
    if box:
        cookie["BoxBounds"] = [0.0, 0.0, float(box[0]), float(box[1])]
    else:
        cookie["PointBase"] = [0.0, 0.0]
    cookie["Base"] = {"ShapeType": shape, "TransformPoint0": [1.0, 0.0], "TransformPoint1": [0.0, 1.0],
                      "TransformPoint2": [0.0, 0.0]}
    grid = {"Type": 1, "Values": [0.0, 0.0, 0.0, 1.0]}
    resources = {
        "KinsokuSet": [], "MojiKumiSet": [], "TheNormalStyleSheet": 0, "TheNormalParagraphSheet": 0,
        "ParagraphSheetSet": [{"Name": "Normal RGB", "DefaultStyleSheet": 0, "Properties": _paragraph(0)}],
        "StyleSheetSet": [{"Name": "Normal RGB", "StyleSheetData": _style(12, 14.4, 0, (0, 0, 0))}],
        "FontSet": [{"Name": font, "Script": 0, "FontType": 0, "Synthetic": 0}],
        "SuperscriptSize": 0.583, "SuperscriptPosition": 0.333, "SubscriptSize": 0.583, "SubscriptPosition": 0.333,
        "SmallCapSize": 0.7,
    }
    adjustments = {"Axis": [1.0, 0.0, 1.0], "XY": [0.0, 0.0]}
    engine = engine_data({
        "EngineDict": {
            "Editor": {"Text": content + "\r"},
            "ParagraphRun": {
                "DefaultRunData": {"ParagraphSheet": {"DefaultStyleSheet": 0, "Properties": {}},
                                   "Adjustments": adjustments},
                "RunArray": [{"ParagraphSheet": {"DefaultStyleSheet": 0, "Properties": paragraph},
                              "Adjustments": adjustments}],
                "RunLengthArray": [length], "IsJoinable": 1,
            },
            "StyleRun": {
                "DefaultRunData": {"StyleSheet": {"StyleSheetData": {}}},
                "RunArray": [{"StyleSheet": {"StyleSheetData": style}}],
                "RunLengthArray": [length], "IsJoinable": 2,
            },
            "GridInfo": {"GridIsOn": False, "ShowGrid": False, "GridSize": 18.0, "GridLeading": 22.0,
                         "GridColor": grid, "GridLeadingFillColor": grid, "AlignLineHeightToGridFlags": False},
            "AntiAlias": 4, "UseFractionalGlyphWidths": True,
            "Rendered": {"Version": 1, "Shapes": {"WritingDirection": 0, "Children": [{
                "ShapeType": shape, "Procession": 0, "Lines": {"WritingDirection": 0, "Children": []},
                "Cookie": {"Photoshop": cookie}}]}},
        },
        "ResourceDict": resources,
        "DocumentResources": resources,
    })

    def rectangle(class_id):
        return object_value(class_id, [(b"Left", unit_value(bounds[0])), (b"Top ", unit_value(bounds[1])),
                                       (b"Rght", unit_value(bounds[2])), (b"Btom", unit_value(bounds[3]))])

    text_descriptor = descriptor(b"TxLr", [
        (b"Txt ", text_value(content)),
        (b"textGridding", enum_value(b"textGridding", b"None")),
        (b"Ornt", enum_value(b"Ornt", b"Hrzn")),
        (b"AntA", enum_value(b"Annt", b"antiAliasSharp")),
        (b"bounds", rectangle(b"bounds")),
        (b"boundingBox", rectangle(b"boundingBox")),
        (b"TextIndex", long_value(0)),
        (b"EngineData", data_value(engine)),
    ])
    warp = descriptor(b"warp", [
        (b"warpStyle", enum_value(b"warpStyle", b"warpNone")),
        (b"warpValue", double_value(0.0)),
        (b"warpPerspective", double_value(0.0)),
        (b"warpPerspectiveOther", double_value(0.0)),
        (b"warpRotate", enum_value(b"Ornt", b"Hrzn")),
    ])
    return (struct.pack(">H6d", 1, *transform) + struct.pack(">HI", 50, 16) + text_descriptor
            + struct.pack(">HI", 1, 16) + warp
            # The closing rectangle (left, top, right, bottom): four 4-byte values in the files Photoshop writes
            # (the specification's table says 4 * 8); readers skip it, so it is zeros.
            + bytes(16))


def parse_type_block(data):
    """What a ``TySh`` block says: ``{text, font, size, color, tracking, leading, align, transform, box}``
    (``text`` with ``\\n`` between lines; keys the block does not carry are absent). Raises ``Malformed``."""
    reader = Reader(data)
    try:
        version, *transform = reader.unpack(">H6d")
        text_version, descriptor_version = reader.unpack(">HI")
        if version != 1 or text_version != 50 or descriptor_version != 16:
            raise Malformed("unsupported type-tool version")
        fields = read_descriptor(reader)
    except (struct.error, UnicodeError) as exc:
        raise Malformed("invalid type-tool block") from exc
    require_finite(transform)
    result = {"text": str(fields.get("Txt ", "")).replace("\r", "\n"), "transform": tuple(transform)}
    blob = fields.get("EngineData")
    if not isinstance(blob, bytes):
        return result
    try:
        engine = parse_engine_data(blob)
    except Malformed:
        return result  # The descriptor's own copy of the text is still good.
    try:
        sheet = engine["EngineDict"]["StyleRun"]["RunArray"][0]["StyleSheet"]["StyleSheetData"]
    except (KeyError, IndexError, TypeError):
        sheet = {}
    if not isinstance(sheet, dict):
        sheet = {}
    resources = engine.get("ResourceDict") or engine.get("DocumentResources")
    fonts = resources.get("FontSet") if isinstance(resources, dict) else None
    index = sheet.get("Font", 0)
    if (isinstance(fonts, list) and isinstance(index, int) and 0 <= index < len(fonts)
            and isinstance(fonts[index], dict) and isinstance(fonts[index].get("Name"), str)):
        result["font"] = fonts[index]["Name"]
    for key, name in (("FontSize", "size"), ("Tracking", "tracking"), ("Leading", "leading")):
        if isinstance(sheet.get(key), (int, float)) and math.isfinite(sheet[key]):
            result[name] = sheet[key]
    values = (sheet.get("FillColor") or {}).get("Values") if isinstance(sheet.get("FillColor"), dict) else None
    if isinstance(values, list) and len(values) == 4 and all(isinstance(v, (int, float)) for v in values):
        result["color"] = "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in values[1:])
    try:
        paragraph = engine["EngineDict"]["ParagraphRun"]["RunArray"][0]["ParagraphSheet"]["Properties"]
        result["align"] = ALIGNMENTS.get(paragraph.get("Justification", 0), "left")
        cookie = engine["EngineDict"]["Rendered"]["Shapes"]["Children"][0]["Cookie"]["Photoshop"]
        bounds = cookie.get("BoxBounds")
        if cookie.get("ShapeType") == 1 and isinstance(bounds, list) and len(bounds) == 4:
            result["box"] = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    except (KeyError, IndexError, TypeError, AttributeError):
        pass  # A block without paragraph or shape data still has its text and font.
    return result


def require_finite(values):
    if not all(math.isfinite(v) for v in values):
        raise Malformed("non-finite transform")


# ------------------------------------------------------------------------------------- from a Vixl layer

def _postscript_name(data):
    from .text import face

    names = face(data)[0]["name"]
    return names.getDebugName(6) or (names.getDebugName(4) or "").replace(" ", "") or None


def pixel_reason(project, stored, layer):
    """Why a text layer cannot be a native type layer (it stays pixels), or None when it can."""
    from .affine import precise
    from .richtext import active

    if stored is None:
        return "the layer is generated when the document is drawn"
    if active(stored):
        return "rich text (styled spans or paragraph settings)"
    if stored.get("flip_x") or stored.get("flip_y") or precise(stored):
        return "flipped or skewed"
    if any(effect.get("enabled", True) for effect in stored.get("effects") or []):
        return "effects"
    if stored.get("mask") and stored["mask"].get("enabled", True):
        return "a layer mask"
    if stored.get("text_transform", "none") == "small-caps":
        return "small capitals"
    for key, value in stored.items():
        if key not in PLAIN_FIELDS and not key.startswith("_") and value not in NEUTRAL:
            return f"{key.replace('_', ' ')} has no type-layer equivalent"
    for key, value in (stored.get("text_layout") or {}).items():
        if key not in LAYOUT_FIELDS and value not in NEUTRAL:
            return f"text layout {key.replace('_', ' ')}"
    if not isinstance(layer.get("color"), str):
        return "a gradient or image fill"
    if not layer.get("text", "").strip():
        return "no visible text"
    return None


def layer_block(project, stored, layer, bounds, ancestors):
    """``(TySh data, None)`` for a resolved plain text layer, or ``(None, reason)`` when it has to stay
    pixels. ``bounds`` is the resolved layout and ``ancestors`` the ids of the (untransformed) groups it is in."""
    from .design import resolve_color
    from .render import color as rgba
    from .text import UnsupportedText, face, line_edges, placed_glyphs, plan, primary_font_data

    reason = pixel_reason(project, stored, layer)
    if reason:
        return None, reason
    try:
        data = primary_font_data(project, layer)
        layout = plan(project, layer)
        glyphs = placed_glyphs(project, layer, layout)
        name = _postscript_name(data)
        edges = line_edges(project, layer)
        fill = rgba(resolve_color(layer["color"], project.state))
    except (UnsupportedText, VixlError, ValueError, KeyError) as exc:
        return None, f"its font or colour could not be read ({str(exc)[:80]})"
    if not name:
        return None, "the font has no PostScript name"
    if "fvar" in face(data)[0]:
        return None, "a variable font"
    if glyphs is None or any(glyph[0] != data for glyph in glyphs):
        return None, "fallback fonts or emoji"
    if any(glyph[1] == ".notdef" for glyph in glyphs):
        return None, "characters its font lacks"
    if fill[3] < 255:
        return None, "a translucent colour"
    if not edges:
        return None, "no visible text"
    # A rotated layer's bounds are the box around the turned layer: the same centre, not the same size.
    x, y, width, height = bounds[layer["id"]]
    centre = [x + width / 2, y + height / 2]
    for ident in ancestors:
        centre = [centre[0] + bounds[ident][0], centre[1] + bounds[ident][1]]
    if (layer.get("rotation", 0) or 0) % 360:
        width, height = layer["width"], layer["height"]
    outline = face(data)[0]
    pitch = (outline["hhea"].ascent - outline["hhea"].descent) * layout.size / outline["head"].unitsPerEm
    leading = edges[1][2] - edges[0][2] if len(edges) > 1 else pitch + layer.get("spacing", 4)
    align = layer.get("align", "left")
    if align not in ("left", "center", "right"):
        return None, f"{align} alignment"
    box = None
    if "width" in (layer.get("text_layout") or {}):
        box, origin = (width, height), (0.0, 0.0)
    else:
        start, end, baseline = edges[0]
        origin = ({"left": start, "center": (start + end) / 2, "right": end}[align], baseline)
    angle = math.radians(layer.get("rotation", 0) or 0)
    cos, sin = math.cos(angle), math.sin(angle)
    dx, dy = origin[0] - width / 2, origin[1] - height / 2
    transform = (cos, sin, -sin, cos, centre[0] + cos * dx - sin * dy, centre[1] + sin * dx + cos * dy)
    block = type_block(
        layer["text"], font=name, size=layout.size, color=fill, leading=leading, align=align, box=box,
        tracking=round(1000 * layer.get("tracking", 0) / layout.size), transform=transform,
        bounds=(-origin[0], -origin[1], width - origin[0], height - origin[1]))
    return block, None
