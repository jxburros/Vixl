"""A small deterministic PDF object writer.

Objects are written to a binary stream as they are added, so long documents (a deck, a 1,000-row
merge) do not sit in memory. Output is byte-identical for identical input: no timestamps, objects
in the order they were added, and a file ``/ID`` derived from a hash of the content.

Every text string is written as hex UTF-16BE with a byte-order mark (``<FEFF…>``) and every byte
string as hex, so user text can never escape into PDF syntax. Names use ``#xx`` escaping.
The writer adds no actions, JavaScript or links of its own (``pdf_forms`` supplies field validation scripts).
"""

import hashlib
import math
import zlib

from .errors import require
from .geometry import compact_number


class Name(str):
    """A PDF name (written ``/Value`` with ``#xx`` escapes)."""


class Text(str):
    """A PDF text string (written as hex UTF-16BE with a byte-order mark)."""


class Raw(str):
    """Already-serialized PDF syntax (used for small fixed fragments only)."""


class Ref:
    __slots__ = ("number",)

    def __init__(self, number):
        self.number = number

    def __repr__(self):
        return f"Ref({self.number})"


REGULAR = set(range(33, 127)) - set(b"#()<>[]{}/%")


def name_bytes(value):
    data = str(value).encode("utf-8")
    require(data, "PDF names cannot be empty")
    return b"/" + b"".join(bytes([c]) if c in REGULAR else f"#{c:02X}".encode() for c in data)


def number(value):
    if isinstance(value, bool):
        return b"true" if value else b"false"
    if isinstance(value, int):
        return str(value).encode()
    require(math.isfinite(value), "PDF numbers must be finite")
    return compact_number(value, 5).encode()


def serialize(value):
    if value is None:
        return b"null"
    if isinstance(value, Ref):
        return f"{value.number} 0 R".encode()
    if isinstance(value, Name):
        return name_bytes(value)
    if isinstance(value, Raw):
        return value.encode("latin-1")
    if isinstance(value, Text):
        return b"<FEFF" + value.encode("utf-16-be").hex().upper().encode() + b">"
    if isinstance(value, str):
        # Plain Python strings are names unless wrapped in Text.
        return name_bytes(value)
    if isinstance(value, (bytes, bytearray)):
        return b"<" + bytes(value).hex().upper().encode() + b">"
    if isinstance(value, (bool, int, float)):
        return number(value)
    if isinstance(value, (list, tuple)):
        return b"[" + b" ".join(serialize(v) for v in value) + b"]"
    if isinstance(value, dict):
        parts = [name_bytes(k) + b" " + serialize(v) for k, v in value.items() if v is not None]
        return b"<<" + b" ".join(parts) + b">>"
    raise TypeError(f"Cannot write {type(value).__name__} to PDF")


class Writer:
    """Write indirect objects to ``stream`` and finish with a cross-reference table."""

    def __init__(self, stream):
        self.stream = stream
        self.offsets = {}
        self.count = 0
        self.position = 0
        self.digest = hashlib.sha256()
        self._write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")

    def _write(self, data):
        self.stream.write(data)
        self.digest.update(data)
        self.position += len(data)

    def reserve(self):
        self.count += 1
        return Ref(self.count)

    def add(self, value, ref=None):
        ref = ref or self.reserve()
        require(ref.number not in self.offsets, "PDF object written twice")
        self.offsets[ref.number] = self.position
        self._write(f"{ref.number} 0 obj\n".encode() + serialize(value) + b"\nendobj\n")
        return ref

    def add_stream(self, dictionary, data, ref=None, compress=True):
        ref = ref or self.reserve()
        require(ref.number not in self.offsets, "PDF object written twice")
        dictionary = dict(dictionary)
        if compress and "Filter" not in dictionary:
            data = zlib.compress(data, 9)
            dictionary["Filter"] = Name("FlateDecode")
        dictionary["Length"] = len(data)
        self.offsets[ref.number] = self.position
        self._write(f"{ref.number} 0 obj\n".encode() + serialize(dictionary) + b"\nstream\n" + data + b"\nendstream\nendobj\n")
        return ref

    def finish(self, root, info=None):
        missing = [n for n in range(1, self.count + 1) if n not in self.offsets]
        require(not missing, f"PDF objects reserved but never written: {missing[:5]}")
        start = self.position
        lines = [f"xref\n0 {self.count + 1}\n".encode(), b"0000000000 65535 f \n"]
        lines += [f"{self.offsets[n]:010d} 00000 n \n".encode() for n in range(1, self.count + 1)]
        identifier = self.digest.digest()[:16]
        trailer = {"Size": self.count + 1, "Root": root, "Info": info, "ID": [identifier, identifier]}
        self._write(b"".join(lines) + b"trailer\n" + serialize(trailer) + f"\nstartxref\n{start}\n%%EOF\n".encode())


def image_xobject(writer, image, *, jpeg_quality=None, alpha=None):
    """An image XObject (with an SMask for transparency). RGB(A), L, LA and CMYK images; ``alpha``
    (an L image) is the transparency of an image that has no alpha channel of its own, such as a
    separated CMYK tile."""

    mode = image.mode
    smask = None
    if mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        image = rgba.convert("RGB")
    elif mode not in ("RGB", "L", "CMYK"):
        image = image.convert("RGB")
    if alpha is not None and alpha.getextrema() != (255, 255):
        smask = writer.add_stream({"Type": Name("XObject"), "Subtype": Name("Image"), "Width": alpha.width,
                                   "Height": alpha.height, "ColorSpace": Name("DeviceGray"), "BitsPerComponent": 8},
                                  alpha.tobytes())
    space = {"RGB": "DeviceRGB", "L": "DeviceGray", "CMYK": "DeviceCMYK"}[image.mode]
    dictionary = {"Type": Name("XObject"), "Subtype": Name("Image"), "Width": image.width, "Height": image.height,
                  "ColorSpace": Name(space), "BitsPerComponent": 8, "SMask": smask}
    if jpeg_quality:
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=int(jpeg_quality), optimize=False)
        dictionary["Filter"] = Name("DCTDecode")
        if image.mode == "CMYK":
            # Pillow writes Adobe-style inverted CMYK JPEGs.
            dictionary["Decode"] = [1, 0, 1, 0, 1, 0, 1, 0]
        return writer.add_stream(dictionary, buffer.getvalue(), compress=False)
    return writer.add_stream(dictionary, image.tobytes())


_DIGESTS = {}  # id(data) -> (data, sha256): a few font programs are used for every glyph, so each is hashed once


def font_digest(data):
    held = _DIGESTS.get(id(data))
    if held is None or held[0] is not data:
        if len(_DIGESTS) > 64:
            _DIGESTS.clear()
        held = _DIGESTS[id(data)] = (data, hashlib.sha256(data).hexdigest())
    return held[1]


class FontSet:
    """Embedded TrueType fonts for one document: each font file becomes a Type0/CIDFontType2 font
    with Identity encoding (codes are glyph IDs), a subset font program and a ToUnicode map."""

    def __init__(self):
        self.fonts = {}  # sha256 → {"data", "name", "glyphs": {gid: text}, "ref"}

    @staticmethod
    def embeddable(data):
        from fontTools.ttLib import TTFont
        import io

        try:
            font = TTFont(io.BytesIO(data), lazy=True)
            return "glyf" in font and "CFF " not in font
        except Exception:  # noqa: BLE001 - an unreadable font is drawn as outlines instead
            return False

    def use(self, data, glyph_name, text, writer):
        """Register a glyph; returns (resource name, glyph id)."""
        from .text import face

        key = font_digest(data)
        entry = self.fonts.get(key)
        if entry is None:
            entry = self.fonts[key] = {"data": data, "name": f"F{len(self.fonts) + 1}", "glyphs": {}, "ref": writer.reserve()}
        outline = face(data)[0]
        gid = outline.getGlyphID(glyph_name)
        if text and not entry["glyphs"].get(gid):
            entry["glyphs"][gid] = text
        else:
            entry["glyphs"].setdefault(gid, "")
        return entry["name"], gid

    def resources(self):
        return {entry["name"]: entry["ref"] for entry in self.fonts.values()}

    def write(self, writer):
        for entry in self.fonts.values():
            _write_font(writer, entry)


def _postscript_name(font):
    name = font["name"].getDebugName(6) or font["name"].getDebugName(4) or "Font"
    return "".join(c for c in name if c.isalnum() or c in "-_")[:60] or "Font"


def _write_font(writer, entry):
    import io
    import logging

    from fontTools import subset

    logging.getLogger("fontTools.subset").setLevel(logging.WARNING)  # it reports every table at INFO
    from fontTools.ttLib import TTFont

    data = entry["data"]
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    gids = sorted(entry["glyphs"]) or [0]
    tag = "".join(chr(65 + b % 26) for b in hashlib.sha256((data[:64] + str(gids).encode())).digest()[:6])
    base = f"{tag}+{_postscript_name(font)}"
    options = subset.Options()
    options.retain_gids = True
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.layout_features = []
    options.hinting = False
    options.drop_tables += ["GSUB", "GPOS", "GDEF", "DSIG", "FFTM"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(gids=[0, *gids])
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    program = buffer.getvalue()
    head, hhea, hmtx = font["head"], font["hhea"], font["hmtx"]
    scale = 1000 / head.unitsPerEm
    order = font.getGlyphOrder()
    widths = []
    for gid in gids:
        if gid < len(order):
            widths += [gid, [round(hmtx[order[gid]][0] * scale)]]
    os2 = font["OS/2"] if "OS/2" in font else None
    file_ref = writer.add_stream({"Length1": len(program)}, program)
    descriptor = writer.add({
        "Type": Name("FontDescriptor"), "FontName": Name(base), "Flags": 4,
        "FontBBox": [round(head.xMin * scale), round(head.yMin * scale), round(head.xMax * scale), round(head.yMax * scale)],
        "ItalicAngle": float(font["post"].italicAngle) if "post" in font else 0,
        "Ascent": round(hhea.ascent * scale), "Descent": round(hhea.descent * scale),
        "CapHeight": round((getattr(os2, "sCapHeight", 0) or hhea.ascent * 0.7) * scale),
        "StemV": 80, "FontFile2": file_ref,
    })
    cid = writer.add({
        "Type": Name("Font"), "Subtype": Name("CIDFontType2"), "BaseFont": Name(base),
        "CIDSystemInfo": {"Registry": b"Adobe", "Ordering": b"Identity", "Supplement": 0},
        "FontDescriptor": descriptor, "W": widths, "DW": 1000, "CIDToGIDMap": Name("Identity"),
    })
    mapping = [(gid, text) for gid, text in sorted(entry["glyphs"].items()) if text]
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
             "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def", "1 begincodespacerange", "<0000> <FFFF>",
             "endcodespacerange"]
    for start in range(0, len(mapping), 100):
        chunk = mapping[start:start + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        lines += [f"<{gid:04X}> <{text.encode('utf-16-be').hex().upper()}>" for gid, text in chunk]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    unicode_ref = writer.add_stream({}, "\n".join(lines).encode("ascii"))
    writer.add({"Type": Name("Font"), "Subtype": Name("Type0"), "BaseFont": Name(base), "Encoding": Name("Identity-H"),
                "DescendantFonts": [cid], "ToUnicode": unicode_ref}, entry["ref"])
