"""Shared Unicode shaping, layout and glyph outlines for PNG and SVG text."""

from dataclasses import dataclass
from functools import lru_cache
import io
import math
import re
import unicodedata
from pathlib import Path
import threading
import xml.etree.ElementTree as ET

from bidi import algorithm as bidi
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.unicodedata import script
import uharfbuzz as hb

from .errors import require
from .model import finite


class UnsupportedText(ValueError):
    """A font or layout cannot be outlined without changing its appearance."""


@dataclass
class Glyph:
    name: str
    x: float
    y: float
    advance: float
    data: bytes = b""
    text: str = ""  # The characters this glyph starts (its HarfBuzz cluster), for text extraction.
    scale: float = 1.0  # Its size as a multiple of the shaped size: below 1 for synthesized small capitals.


@dataclass
class Plan:
    width: int
    height: int
    paths: list
    box: tuple
    size: float = 0.0  # the size drawn (after fitting)
    offset: float = 0.0  # horizontal alignment offset inside a text box
    shaped: bool = True  # False for warped or path text (outlines only)


_local = threading.local()


def face(data):
    """The parsed font and HarfBuzz font for ``data``. fontTools loads tables lazily and is not
    thread-safe, so each thread (production and job workers render in parallel) keeps its own."""
    from .emojis import is_glyph, EMOJI_FACE

    if is_glyph(data):
        return EMOJI_FACE, None
    loader = getattr(_local, "face", None)
    if loader is None:
        loader = _local.face = lru_cache(maxsize=16)(_face)
    return loader(data)


def _face(data):
    data = data[0] if isinstance(data, tuple) else data
    outline = TTFont(io.BytesIO(data))
    if not any(table in outline for table in ("glyf", "CFF ", "CFF2")) or any(
        table in outline for table in ("COLR", "CBDT", "sbix", "SVG ")
    ):
        raise UnsupportedText("bitmap/color fonts require appearance-preserving raster export")
    native = hb.Face(data)
    font = hb.Font(native)
    font.scale = (native.upem, native.upem)
    hb.ot_font_set_funcs(font)
    return outline, font


def primary_font_data(project, layer):
    from .render import font_for

    name = project.state.get("fonts", {}).get(layer.get("font"), layer.get("font"))
    if name in project.assets:
        return project.assets[name]
    path = _font_path(name or "DejaVuSans.ttf") if 1 <= int(layer.get("size", 48)) <= 4096 else None
    if path is not None:
        try:
            return file_bytes(path)
        except OSError:
            _font_path.cache_clear()  # Uninstalled since it was found: font_for reports it.
    font = font_for(project, layer)
    path = font.path
    return path.getvalue() if hasattr(path, "getvalue") else file_bytes(path)


# Bundled outline faces that draw the characters the default face (DejaVu Sans) lacks, after the
# document's own font-fallbacks: more Latin, Greek and Cyrillic, symbols, dingbats, arrows and math.
# CJK is not bundled (install a CJK face and list it in font-fallbacks).
BUNDLED_FALLBACKS = ("NotoSans-Regular.ttf", "NotoSansSymbols-Regular.ttf", "NotoSansSymbols2-Regular.ttf",
                     "NotoSansMath-Regular.ttf")
BUNDLED_FONTS = ("DejaVuSans.ttf", *BUNDLED_FALLBACKS)


@lru_cache(maxsize=64)
def _font_path(font):
    """The file behind a bundled or system font name, found once instead of opening the font on every
    measurement; None when ``font_for`` must decide (and report) instead."""
    if font in BUNDLED_FONTS:
        return str(Path(__file__).parent / "data" / font)
    if "/" in font or "\\" in font:
        return None
    from PIL import ImageFont

    try:
        path = ImageFont.truetype(font, 12).path
    except OSError:
        return None
    return path if isinstance(path, str) else None


def file_bytes(path):
    """A font file's bytes, the same object on every call while the file is unchanged, so the caches keyed by font data
    (coverage, parsed faces, PDF font programs) are hit by identity instead of by hashing the whole file again."""
    stat = Path(path).stat()
    return _file_bytes(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=16)
def _file_bytes(path, mtime, size):
    return Path(path).read_bytes()


@lru_cache(maxsize=32)
def font_sha256(data):
    """Hex SHA-256 of one font file, computed once per font instead of once per drawn layer."""
    import hashlib

    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=32)
def coverage(data):
    return frozenset(TTFont(io.BytesIO(data)).getBestCmap() or {})


def visible_char(char):
    return (
        not char.isspace()
        and unicodedata.category(char) not in ("Cf", "Cc")
        and not (0xFE00 <= ord(char) <= 0xFE0F)
    )


@lru_cache(maxsize=64)
def font_style(data):
    """(family, weight, italic) of a font file from its name and OS/2 tables."""
    try:
        font = TTFont(io.BytesIO(data), lazy=True)
        names = font["name"]
        family = names.getDebugName(16) or names.getDebugName(1) or ""
        os2 = font["OS/2"] if "OS/2" in font else None
        weight = getattr(os2, "usWeightClass", 400) or 400
        italic = bool(os2 and os2.fsSelection & 1) or bool(font["head"].macStyle & 2)
        return family, weight, italic
    except Exception:  # noqa: BLE001 - unreadable metadata: treat as a regular face of its own family
        return str(len(data)), 400, False


def fallback_chain(primary, fallbacks):
    """``primary`` followed by ``fallbacks`` with each family's faces ordered by how well they
    match the primary's slope, then weight (as CSS font matching does), so a bold heading falls
    back to the bold face of a fallback family. The order of families is kept."""
    _, weight, italic = font_style(primary)
    families, order = {}, []
    for data in fallbacks:
        if data == primary or data in families.get(font_style(data)[0], ()):
            continue
        family = font_style(data)[0]
        if family not in families:
            order.append(family)
        families.setdefault(family, []).append(data)

    def distance(data):
        _, w, slanted = font_style(data)
        return (slanted != italic) * 1000 + abs(w - weight)

    chain = [primary]
    for family in order:
        chain += [data for data in sorted(families[family], key=distance) if data not in chain]
    return tuple(chain)


def font_data(project, layer):
    from .render import document_variables
    from .variables import layer_text

    text = layer_text(layer, document_variables(project))
    memo = getattr(project, "_resolving", None)
    if memo is None:
        return _font_data(project, layer, text)
    # Within a read-only pass the fonts, fallbacks and emoji settings are fixed: each layer that sets the
    # same text in the same font shares one lookup (coverage scans and emoji spans) per render.
    key = ("font_data", layer.get("font"), 1 <= int(layer.get("size", 48)) <= 4096, text)
    if key not in memo:
        memo[key] = _font_data(project, layer, text)
    return memo[key]


def _font_data(project, layer, text):
    primary = primary_font_data(project, layer)
    if all(not visible_char(c) or ord(c) in coverage(primary) for c in text):
        from .emojis import with_emojis

        return with_emojis(project, primary, text)
    names = [*project.state.get("font_fallbacks", []), *BUNDLED_FONTS]
    from .emojis import with_emojis

    return with_emojis(
        project,
        fallback_chain(primary, [primary_font_data(project, {**layer, "font": name}) for name in names]),
        text,
    )


def glyph_coverage(project, layer):
    data = font_data(project, layer)
    from .emojis import is_context, scan

    fonts = tuple(f for f in (data if isinstance(data, tuple) else (data,)) if not is_context(f))
    text = layer.get("text", "")
    spans = scan(text, project.state.get("emojis", {}).get("overrides"))
    handled = {i for a, b, _ in spans for i in range(a, b)}
    chars = sorted({c for i, c in enumerate(text) if i not in handled and visible_char(c)})
    return {
        "missing": [c for c in chars if not any(ord(c) in coverage(f) for f in fonts)],
        "fallback": [
            c
            for c in chars
            if ord(c) not in coverage(fonts[0]) and any(ord(c) in coverage(f) for f in fonts[1:])
        ],
    }


def layer_coverage(project, layer):
    """``glyph_coverage`` of a text layer as it is drawn: its text with the document's variables filled in, and
    rich text checked span by span against each span's font. Shared by the checks and the apply-time advisory."""
    from .render import document_variables
    from .richtext import active, glyph_coverage as rich_coverage
    from .variables import layer_text

    view = {**layer, "text": layer_text(layer, document_variables(project))}
    return (rich_coverage if active(view) else glyph_coverage)(project, view)


def uncovered(project, layer):
    """The characters of a text layer that no available font draws (they render as empty boxes, tofu)."""
    return layer_coverage(project, layer)["missing"]


# Scripts the bundled fonts do not cover, with the catalog family that does (vixl font show "Noto Sans JP").
# Han alone is ambiguous between Chinese and Japanese; with kana present it is Japanese.
SCRIPT_FONTS = {
    "Devanagari": "Noto Sans Devanagari", "Han": "Noto Sans SC", "Hiragana/Katakana": "Noto Sans JP",
    "Hangul": "Noto Sans KR", "Thai": "Noto Sans Thai", "Arabic": "Noto Sans Arabic",
}
SCRIPT_RANGES = (
    ("Devanagari", 0x0900, 0x097F), ("Devanagari", 0xA8E0, 0xA8FF), ("Thai", 0x0E00, 0x0E7F),
    ("Hangul", 0x1100, 0x11FF), ("Hangul", 0x3130, 0x318F), ("Hangul", 0xA960, 0xA97F), ("Hangul", 0xAC00, 0xD7FF),
    ("Hiragana/Katakana", 0x3040, 0x30FF), ("Hiragana/Katakana", 0x31F0, 0x31FF),
    ("Hiragana/Katakana", 0xFF66, 0xFF9F), ("Han", 0x2E80, 0x2FDF), ("Han", 0x3000, 0x303F),
    ("Han", 0x3400, 0x4DBF), ("Han", 0x4E00, 0x9FFF), ("Han", 0xF900, 0xFAFF), ("Han", 0xFF00, 0xFF65),
    ("Han", 0x20000, 0x3134F), ("Arabic", 0x0600, 0x06FF), ("Arabic", 0x0750, 0x077F), ("Arabic", 0xFB50, 0xFDFF),
    ("Arabic", 0xFE70, 0xFEFF),
)


def script_of(char):
    """The script name of ``char`` from ``SCRIPT_RANGES``, or None for a script Vixl has no catalog face for."""
    code = ord(char)
    return next((name for name, low, high in SCRIPT_RANGES if low <= code <= high), None)


def scripts_of(chars):
    """``{script: [chars]}`` for ``chars``, in first-seen order; characters of other scripts go under ``None``."""
    found = {}
    for char in chars:
        found.setdefault(script_of(char), []).append(char)
    return found


def cover_families(scripts):
    """The catalog families that draw ``scripts`` (a Japanese face covers Han when kana are present too)."""
    scripts = [name for name in scripts if name in SCRIPT_FONTS]
    if "Hiragana/Katakana" in scripts and "Han" in scripts:
        scripts.remove("Han")
    return list(dict.fromkeys(SCRIPT_FONTS[name] for name in scripts))


def font_runs(fonts, content):
    if len(fonts) == 1:
        return [(fonts[0], content)] if content else []  # One font draws every cluster.
    # Keep combining marks, selectors and joiner sequences with their base glyph.
    clusters = []
    for char in content:
        if clusters and (
            unicodedata.combining(char)
            or char == "\u200d"
            or clusters[-1].endswith("\u200d")
            or 0xFE00 <= ord(char) <= 0xFE0F
        ):
            clusters[-1] += char
        else:
            clusters.append(char)
    result = []
    for cluster in clusters:
        font = next(
            (f for f in fonts if all(not visible_char(c) or ord(c) in coverage(f) for c in cluster)), fonts[0]
        )
        if result and result[-1][0] == font:
            result[-1] = (font, result[-1][1] + cluster)
        else:
            result.append((font, cluster))
    return result


# Bidi classes that can put a character above level 0 or remove it from the text (explicit controls and boundary
# neutrals are dropped by rule X9). Text without any of them is one left-to-right level, so runs() can skip the
# bidi algorithm, which is written in Python and dominated the cost of shaping long lines.
LEVEL_CHANGING = frozenset(
    ("R", "AL", "AN", "RLE", "RLO", "LRE", "LRO", "PDF", "RLI", "LRI", "FSI", "PDI", "BN")
)
INHERITED_SCRIPTS = ("Zyyy", "Zinh", "Zzzz")


def runs(text):
    """Resolve bidi levels, shape logical script runs, then order runs visually."""
    if not text:
        return []
    if not any(unicodedata.bidirectional(char) in LEVEL_CHANGING for char in text):
        result = []
        for char, tag in zip(text, script_tags(text)):
            if result and result[-1][0][1] == tag:
                result[-1][1].append(char)
            else:
                result.append(((0, tag), [char]))
        return [(key, "".join(chars)) for key, chars in result]
    return bidi_runs(text)


def bidi_runs(text):
    """``runs`` through the full bidi algorithm."""
    storage = bidi.get_empty_storage()
    storage["base_level"] = bidi.get_base_level(text)
    storage["base_dir"] = ("L", "R")[storage["base_level"]]
    bidi.get_embedding_levels(text, storage)
    for index, char in enumerate(storage["chars"]):
        char["index"] = index
    try:
        for stage in (
            bidi.explicit_embed_and_overrides,
            bidi.resolve_weak_types,
            bidi.resolve_neutral_types,
            bidi.resolve_implicit_levels,
        ):
            stage(storage, False)
    except AssertionError as exc:
        raise UnsupportedText("Unicode isolate controls require raster text layout") from exc
    logical = list(storage["chars"])
    tags = script_tags([char["ch"] for char in logical])
    result = []
    for char, tag in zip(logical, tags):
        key = (char["level"], tag)
        if not result or result[-1][0] != key:
            result.append((key, []))
        result[-1][1].append(char)
        char["run"] = len(result) - 1
    bidi.reorder_resolved_levels(storage, False)
    order = list(dict.fromkeys(char["run"] for char in storage["chars"]))
    return [(result[i][0], "".join(c["ch"] for c in result[i][1])) for i in order]


char_script = lru_cache(maxsize=4096)(script)  # One lookup per distinct character, not per character.


def script_tags(chars):
    """Each character's script; common and inherited characters (spaces, digits, marks) take the script before
    them, or after them at the start, or Latin."""
    tags = [char_script(char) for char in chars]
    for i, tag in enumerate(tags):
        if tag in INHERITED_SCRIPTS:
            # Everything before i is resolved already, so the nearest script on the left is the previous one.
            left = tags[i - 1] if i else None
            tags[i] = (
                left
                or next((tags[j] for j in range(i + 1, len(tags)) if tags[j] not in INHERITED_SCRIPTS), None)
                or "Latn"
            )
    return tags


@lru_cache(maxsize=64)
def has_feature(data, tag):
    """Whether the font ``data`` has the OpenType substitution feature ``tag`` (such as ``smcp``)."""
    from .emojis import is_glyph

    if is_glyph(data):
        return False
    outline = face(data)[0]
    if "GSUB" not in outline or outline["GSUB"].table.FeatureList is None:
        return False
    return any(record.FeatureTag == tag for record in outline["GSUB"].table.FeatureList.FeatureRecord)


# Small capitals for a font without its own (no OpenType smcp): each lowercase letter is drawn as its capital at
# this share of the size, with this share of the size added after it, since shrunken capitals look light and tight.
SMALL_CAPS_SCALE = 0.7
SMALL_CAPS_TRACKING = 0.05


def _lowered(char):
    """Whether small caps draw ``char`` as a small capital: a lowercase letter whose capital is one character."""
    upper = char.upper()
    return upper != char and len(upper) == 1


def _synthesized_small_caps(font_data, segment, size, rtl, tag):
    """``(glyphs, advance)`` of one font run in synthesized small caps: runs of lowercase letters are shaped as
    capitals at ``SMALL_CAPS_SCALE`` of the size and spaced by ``SMALL_CAPS_TRACKING``, the rest as it is. A small
    capital's glyph carries the capital as its text, which is what it draws (and what a PDF maps it to)."""
    pieces = []
    for char in segment:
        lowered = _lowered(char) or (bool(pieces) and pieces[-1][0] and unicodedata.category(char).startswith("M"))
        if pieces and pieces[-1][0] == lowered:
            pieces[-1][1].append(char)
        else:
            pieces.append((lowered, [char]))
    if rtl:
        pieces.reverse()
    glyphs, cursor = [], 0.0
    for lowered, chars in pieces:
        text = "".join(chars)
        if not lowered:
            found, width = _shape_run(font_data, text, size, rtl, tag)
        else:
            found, width = _shape_run(font_data, text.upper(), size * SMALL_CAPS_SCALE, rtl, tag)
            extra = size * SMALL_CAPS_TRACKING
            count = 0
            for glyph in found:
                glyph.scale = SMALL_CAPS_SCALE
                if glyph.text:
                    count += 1
                glyph.x += extra * (count - 1)
            width += extra * count
        for glyph in found:
            glyph.x += cursor
        glyphs.extend(found)
        cursor += width
    return glyphs, cursor


def _shape_run(font_data, segment, size, rtl, tag, features=None):
    """``(glyphs, advance)`` of one run of one script and direction in one font."""
    outline, font = face(font_data)
    names, factor = outline.getGlyphOrder(), size / font.face.upem
    buffer = hb.Buffer()
    buffer.add_str(segment)
    buffer.direction = "rtl" if rtl else "ltr"
    buffer.script = tag
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features)
    starts = sorted({info.cluster for info in buffer.glyph_infos})
    ends = dict(zip(starts, starts[1:] + [len(segment)]))
    seen, glyphs, cursor = set(), [], 0.0
    for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions):
        first = info.cluster not in seen
        seen.add(info.cluster)
        glyphs.append(
            Glyph(
                names[info.codepoint],
                cursor + pos.x_offset * factor,
                -pos.y_offset * factor,
                pos.x_advance * factor,
                font_data,
                segment[info.cluster : ends[info.cluster]] if first else "",
            )
        )
        cursor += pos.x_advance * factor
    return glyphs, cursor


def shape(data, text, size, small_caps=False):
    """``(glyphs, advance)`` of ``text`` at ``size``. ``small_caps`` sets lowercase letters as small capitals: the
    font's own (OpenType ``smcp``) in each font that has them, synthesized in the others."""
    from .emojis import split_context

    fonts, protected, placeholders = split_context(data, text)
    if placeholders:
        glyphs, cursor = [], 0.0
        for (level, tag), content in runs(protected):
            pieces, ordinary = [], ""
            for char in content:
                if char in placeholders:
                    if ordinary:
                        pieces.append(ordinary)
                        ordinary = ""
                    pieces.append(placeholders[char])
                else:
                    ordinary += char
            if ordinary:
                pieces.append(ordinary)
            if level % 2:
                pieces.reverse()
            for piece in pieces:
                if isinstance(piece, tuple):
                    original, art = piece
                    glyphs.append(Glyph("emoji", cursor, 0, size, art, original))
                    cursor += size
                else:
                    found, width = shape(fonts, piece, size, small_caps)
                    for glyph in found:
                        glyph.x += cursor
                    glyphs.extend(found)
                    cursor += width
        return glyphs, cursor
    glyphs, cursor = [], 0.0
    for (level, tag), content in runs(text):
        segments = font_runs(fonts, content)
        if level % 2:
            segments.reverse()
        for font_data, segment in segments:
            rtl = bool(level % 2)
            if not small_caps or not any(_lowered(char) for char in segment):
                found, width = _shape_run(font_data, segment, size, rtl, tag)
            elif has_feature(font_data, "smcp"):
                found, width = _shape_run(font_data, segment, size, rtl, tag, {"smcp": True})
            else:
                found, width = _synthesized_small_caps(font_data, segment, size, rtl, tag)
            for glyph in found:
                glyph.x += cursor
            glyphs.extend(found)
            cursor += width
    return glyphs, cursor


@lru_cache(maxsize=2048)
def glyph_outline(data, name):
    from .emojis import is_glyph, GLYPH, EmojiArt

    if is_glyph(data):
        return EmojiArt(data[len(GLYPH) :].decode()), (0, -14, 72, 58)
    glyphs = face(data)[0].getGlyphSet()
    pen = SVGPathPen(glyphs)
    glyphs[name].draw(pen)
    bounds = BoundsPen(glyphs)
    glyphs[name].draw(bounds)
    return pen.getCommands(), bounds.bounds


UNSAFE_TO_BREAK = int(hb.GlyphFlags.UNSAFE_TO_BREAK)  # As a plain int: enum arithmetic per glyph is slow.


def clusters(data, word):
    """Wrap only at safe shaping boundaries, preserving marks and conjuncts."""
    if not word:
        return []
    from .emojis import split_context

    fonts, protected, placeholders = split_context(data, word)
    if placeholders:
        pieces, ordinary = [], ""
        for char in protected:
            if char in placeholders:
                if ordinary:
                    pieces.extend(clusters(fonts[0], ordinary))
                    ordinary = ""
                pieces.append(placeholders[char][0])
            else:
                ordinary += char
        if ordinary:
            pieces.extend(clusters(fonts[0], ordinary))
        return pieces
    data = fonts[0]
    buffer = hb.Buffer()
    buffer.add_str(word)
    buffer.guess_segment_properties()
    hb.shape(face(data)[1], buffer)
    boundaries = sorted(
        {0, len(word)}
        | {info.cluster for info in buffer.glyph_infos if not int(info.flags) & UNSAFE_TO_BREAK}
    )
    return [word[a:b] for a, b in zip(boundaries, boundaries[1:])]


SEPARATORS = frozenset("·•–—|/")


def words_of(paragraph):
    """A paragraph's words and runs of spaces, with a lone separator (· – — | …) and the space after it glued to
    the next word, so a line never ends in one."""
    tokens = re.findall(r" +|[^ ]+", paragraph)
    glued, i = [], 0
    while i < len(tokens):
        token = tokens[i]
        if (
            not token.isspace()
            and set(token) <= SEPARATORS
            and i + 2 < len(tokens)
            and tokens[i + 1].isspace()
            and not tokens[i + 2].isspace()
        ):
            token += tokens[i + 1] + tokens[i + 2]
            i += 2
        glued.append(token)
        i += 1
    return glued


WRAPS = ("greedy", "balance", "pretty")


def wrap_mode(layer):
    """How a boxed text layer breaks its lines: ``greedy`` (fill each line), ``balance`` (lines of near-equal width,
    same line count) or ``pretty`` (greedy, but no one-word last line)."""
    return (layer.get("text_layout") or {}).get("wrap", "greedy")


HEADING_ROLES = ("heading", "display", "h1", "h2", "h3")


def is_heading(project, layer):
    """Whether a text layer is a heading: it follows a heading font role or stage, or its size reads as one (the
    title step, h2, and up)."""
    from .type_roles import stage_for_size

    if layer.get("font_role") in HEADING_ROLES:
        return True
    return not layer.get("font_role") and stage_for_size(project, float(layer.get("size", 0))) in HEADING_ROLES


def document_wrap(project, heading):
    """The wrap a new boxed text layer takes when none is given: the house style's heading wrap for headings,
    else greedy."""
    from . import house_style

    rule = house_style.rule("wrap")
    return rule["heading"] if heading else "greedy"


def validate_tabs(tabs, field="tabs"):
    """Check a text layer's ``tabs``: ``[{at, align?, leader?}]`` in increasing ``at``."""
    require(isinstance(tabs, list) and len(tabs) <= 32, f"{field} must be a list of at most 32 tab stops", field=field)
    for i, stop in enumerate(tabs):
        where = f"{field}[{i}]"
        require(isinstance(stop, dict) and "at" in stop and not set(stop) - {"at", "align", "leader"},
                f"{where} must be {{at, align?, leader?}}", field=where)
        at = stop["at"]
        if isinstance(at, str):
            require(re.fullmatch(r"\d+(\.\d+)?%", at.strip()) is not None,
                    f"{where}.at must be pixels or a percentage such as '100%'", field=f"{where}.at")
        else:
            finite(at, f"{where}.at", 0, 16384)
        require(stop.get("align", "left") in TAB_ALIGNS, f"{where}.align is one of {', '.join(TAB_ALIGNS)}",
                field=f"{where}.align", allowed=list(TAB_ALIGNS))
        leader = stop.get("leader", "")
        require(isinstance(leader, str) and len(leader) <= 4 and "\t" not in leader and "\n" not in leader,
                f"{where}.leader must be up to 4 characters, such as '.'", field=f"{where}.leader")


def lines(data, text, size, width=None, wrap="greedy", tabs=None):
    """The lines ``text`` sets in: its own line breaks, then wrapped at ``width``. With tab stops, tabs stay in the
    text and a paragraph holding one is set on one line; without, a tab is four spaces."""
    result = []
    for paragraph in (text if tabs else text.expandtabs(4)).split("\n"):
        if width is None or (tabs and "\t" in paragraph):
            result.append(paragraph)
            continue
        found = _greedy(data, paragraph, size, width)
        if wrap != "greedy" and len(found) > 1:
            found = _rewrap(data, paragraph, size, width, found, wrap)
        result.extend(found)
    return result


def _greedy(data, paragraph, size, width):
    result = []
    line = ""
    for word in words_of(paragraph):
        proposed = line + word
        if advance(data, proposed, size) <= width:
            line = proposed
            continue
        if word.isspace():
            # Preserve authored indentation; separators at a soft wrap belong to the
            # preceding line and are trimmed when the following word wraps.
            line = proposed
            continue
        if line:
            result.append(line.rstrip(" "))
        line = break_word(data, clusters(data, word), size, width, result)
    result.append(line)
    return result


def _rewrap(data, paragraph, size, width, greedy, wrap):
    """Balance or de-runt a paragraph that greedy wrapping set on ``greedy`` lines. A paragraph with a word wider
    than the box keeps its greedy lines (that word is broken, and moving lines around it helps nothing)."""
    words = [token for token in words_of(paragraph) if not token.isspace()]
    widest = max((advance(data, word, size) for word in words), default=0)
    if widest > width:
        return greedy
    if wrap == "balance":
        narrowest = narrowest_width(lambda limit: len(_greedy(data, paragraph, size, limit)), widest, width)
        return _greedy(data, paragraph, size, narrowest) if narrowest < width else greedy
    last = [token for token in words_of(greedy[-1]) if not token.isspace()]
    before = words_of(greedy[-2])
    kept = [token for token in before if not token.isspace()]
    if len(last) != 1 or len(kept) < 3:
        return greedy
    moved = before[-1]
    joined = moved + " " + greedy[-1]
    if advance(data, joined, size) > width:
        return greedy
    return [*greedy[:-2], "".join(before[:-1]).rstrip(" "), joined]


def narrowest_width(count_at, lowest, width):
    """The narrowest wrapping width in [``lowest``, ``width``] that keeps the line count ``count_at(width)`` gives,
    to half a pixel: wrapping there evens the lines out (balanced wrap). ``count_at(limit)`` counts the lines at a
    width; line counts only grow as the width shrinks."""
    target = count_at(width)
    if target < 2 or lowest >= width:
        return width
    low, high = lowest, width
    if count_at(low) <= target:
        return low
    while high - low > 0.5:
        middle = (low + high) / 2
        if count_at(middle) <= target:
            high = middle
        else:
            low = middle
    return high


def break_word(data, pieces, size, width, result):
    """Break a word wider than ``width`` between its clusters: each line takes clusters while the line still fits,
    and always at least one. Full lines go to ``result``; the unfinished last line is returned.

    Measuring every candidate line again made a long word cost its length times the line length, so a
    100,000-character word took minutes. A line's prefixes are measured from one shaping of a window of clusters
    instead, which gives exactly the widths ``shape`` gives each prefix when the window is one left-to-right run in
    one font (clusters are safe break points, so shaping a prefix does not change its glyphs). Each line's break is
    checked against ``shape`` itself, and any other text is measured cluster by cluster as before."""
    start, window, line = 0, 64, ""
    while start < len(pieces):
        end = min(len(pieces), start + window)
        offsets, total = [], 0
        for piece in pieces[start:end]:
            total += len(piece)
            offsets.append(total)
        text = "".join(pieces[start:end])
        widths = _prefix_widths(data, text, size, tuple(offsets))
        if widths is None:
            break
        # widths[m - 1] is the width of the first m clusters; the line ends before the first one that overflows.
        overflow = next((m for m in range(2, len(widths) + 1) if widths[m - 1] > width), None)
        if overflow is None:
            if end < len(pieces):
                window *= 2
                continue
            return text
        fitted, spill = text[: offsets[overflow - 2]], text[: offsets[overflow - 1]]
        if (
            advance(data, fitted, size) != widths[overflow - 2]
            or advance(data, spill, size) != widths[overflow - 1]
        ):
            break
        result.append(fitted)
        start += overflow - 1
        window = max(64, 2 * (overflow - 1))
    for char in pieces[start:]:
        if line and advance(data, line + char, size) > width:
            result.append(line)
            line = ""
        line += char
    return line


@lru_cache(maxsize=8192)
def advance(data, text, size):
    """``shape(data, text, size)[1]``, cached: wrapping measures each candidate line, and text-flow wraps the same
    lines again for every slice of the story it tries in a frame."""
    return shape(data, text, size)[1]


@lru_cache(maxsize=4096)
def _prefix_widths(data, text, size, offsets):
    """``shape(data, text[:b], size)[1]`` for each cluster boundary ``b`` in ``offsets`` (increasing, ending at
    ``len(text)``), from a single shaping of ``text``; None unless ``text`` is one left-to-right run in one font."""
    from .emojis import is_context

    fonts = data if isinstance(data, tuple) else (data,)
    if is_context(fonts[-1]):
        return None
    found = runs(text)
    if len(found) != 1 or found[0][0][0] % 2 or len(font_runs(fonts, found[0][1])) != 1:
        return None
    glyphs, _ = shape(data, text, size)
    widths, cursor, start, index = [], 0.0, 0, 0
    for glyph in [*glyphs, None]:
        if glyph is None or glyph.text:
            # A glyph that starts a cluster: every boundary up to here is complete.
            while index < len(offsets) and offsets[index] <= start:
                if offsets[index] != start:
                    return None  # A boundary inside a cluster of this shaping.
                widths.append(cursor)
                index += 1
            if glyph is None:
                break
            start += len(glyph.text)
        cursor += glyph.advance
    return tuple(widths) if index == len(offsets) else None


TAB_ALIGNS = ("left", "right", "center", "decimal")


def tab_stops(layer, project=None):
    """A text layer's tab stops as a hashable ``((at, align, leader), …)`` in pixels from its left edge, sorted, or
    None. A percentage ``at`` is a share of the text box's width, or of the canvas width for text without a box."""
    stops = layer.get("tabs")
    if not stops:
        return None
    found = []
    for stop in stops:
        at = stop["at"]
        if isinstance(at, str):
            boxed = "width" in (layer.get("text_layout") or {})
            basis = layer["width"] if boxed else project.state["canvas"]["width"] if project is not None else 0
            at = float(at.strip().rstrip("%")) / 100 * float(basis)
        found.append((float(at), stop.get("align", "left"), stop.get("leader", "")))
    return tuple(sorted(found))


def decimal_point(text):
    """Characters before a figure's decimal point (a point followed by a digit), else the whole text."""
    match = re.search(r"\.(?=\d)", text)
    return match.start() if match else len(text)


def set_line(data, line, size, tabs=None, leaders=None):
    """``(glyphs, advance)`` of one line. Each tab moves the text after it to the next tab stop past the pen
    (left, right, center or decimal aligned on the stop, never back over earlier text), and a stop's leader
    repeats in the gap. Leaders sit on a grid from the line start, so the dots of stacked lines line up. Past
    the last stop a tab advances to the next multiple of four spaces. ``leaders``, a list, receives each tab's
    leader and how many times it repeats."""
    if not tabs or "\t" not in line:
        return shape(data, line, size)
    segments = line.split("\t")
    glyphs, pen = shape(data, segments[0], size)
    interval = advance(data, "    ", size) or size
    for segment in segments[1:]:
        found, width = shape(data, segment, size)
        stop = next((stop for stop in tabs if stop[0] > pen + 0.01), None)
        at, align, leader = stop or ((math.floor(pen / interval) + 1) * interval, "left", "")
        lead = {"left": 0.0, "right": width, "center": width / 2,
                "decimal": advance(data, segment[:decimal_point(segment)], size)}[align]
        start = max(pen, at - lead)
        count = 0
        if leader:
            unit = advance(data, leader, size)
            if unit > 0:
                gap = size * 0.25
                position = math.ceil((pen + gap) / unit) * unit
                while position + unit <= start - gap + 0.01:
                    dots, _ = shape(data, leader, size)
                    for glyph in dots:
                        glyph.x += position
                    glyphs.extend(dots)
                    position += unit
                    count += 1
        if leaders is not None:
            leaders.append((leader, count))
        for glyph in found:
            glyph.x += start
        glyphs.extend(found)
        pen = start + width
    return glyphs, pen


def leadered(data, line, size, tabs):
    """``line`` for an application that sets tab stops itself but draws no leaders (PowerPoint): each leader
    Vixl draws is written out as characters before its tab, one repeat short so the tab still reaches its stop."""
    if not tabs or "\t" not in line:
        return line
    leaders = []
    set_line(data, line, size, tabs, leaders)
    segments = line.split("\t")
    out = segments[0]
    for segment, (leader, count) in zip(segments[1:], leaders):
        if count > 1:
            out += " " + leader * (count - 1)
        out += "\t" + segment
    return out


@lru_cache(maxsize=4096)
def measure(data, text, size, spacing=4, align="left", width=None, wrap="greedy", tabs=None):
    """Glyph paths and ink box of shaped text. Cached: every render and check re-measures each
    text layer (auto-sized boxes, constraints), usually with the same font, text and size."""
    finite(size, "font size", 1, 4096)
    outline = face(data)[0]
    factor = size / outline["head"].unitsPerEm
    ascent = outline["hhea"].ascent * factor
    line_height = (outline["hhea"].ascent - outline["hhea"].descent) * factor + spacing
    shaped = [set_line(data, line, size, tabs) for line in lines(data, text, size, width, wrap, tabs)]
    widest = max((advance for _, advance in shaped), default=0)
    paths, bounds = [], []
    for i, (glyphs, advance) in enumerate(shaped):
        offset = (widest - advance) / 2 if align == "center" else widest - advance if align == "right" else 0
        for glyph in glyphs:
            factor = size / face(glyph.data)[0]["head"].unitsPerEm
            path, box = glyph_outline(glyph.data, glyph.name)
            if path:
                x, y = glyph.x + offset, glyph.y + ascent + i * line_height
                paths.append((path, (factor, 0, 0, -factor, x, y)))
                if box:
                    bounds.append(
                        (box[0] * factor + x, -box[3] * factor + y, box[2] * factor + x, -box[1] * factor + y)
                    )
    box = (
        min(0, min((b[0] for b in bounds), default=0)),
        min((b[1] for b in bounds), default=0),
        max(widest, max((b[2] for b in bounds), default=0)),
        max((b[3] for b in bounds), default=ascent) if bounds else ascent,
    )
    return paths, box


def plan_glyphs(project, layer, layout=None):
    """Positioned glyphs ``[(font data, glyph name, x, y, size, text)]`` in the layer image's
    pixels, exactly where ``plan`` draws them (baseline origin, y down). None for warped or path
    text, whose glyphs are bent."""
    placed = placed_glyphs(project, layer, layout)
    return None if placed is None else [item[:6] for item in placed]


def placed_glyphs(project, layer, layout=None):
    """``plan_glyphs`` with each glyph's line index appended: ``(data, name, x, y, size, text, line)``."""
    layout = layout or plan(project, layer)
    if not layout.shaped:
        return None
    data = font_data(project, layer)
    settings = layer.get("text_layout", {})
    width = layer["width"] if "width" in settings else None
    size, spacing, align = layout.size, layer.get("spacing", 4), layer.get("align", "left")
    outline = face(data)[0]
    factor = size / outline["head"].unitsPerEm
    ascent = outline["hhea"].ascent * factor
    line_height = (outline["hhea"].ascent - outline["hhea"].descent) * factor + spacing
    tabs = tab_stops(layer, project)
    shaped = [set_line(data, line, size, tabs) for line in lines(data, layer["text"], size, width, wrap_mode(layer), tabs)]
    widest = max((advance for _, advance in shaped), default=0)
    result = []
    for i, (glyphs, advance) in enumerate(shaped):
        offset = (widest - advance) / 2 if align == "center" else widest - advance if align == "right" else 0
        for glyph in glyphs:
            x = glyph.x + offset - layout.box[0] + layout.offset
            y = glyph.y + ascent + i * line_height - layout.box[1]
            result.append((glyph.data, glyph.name, x, y, size, glyph.text, i))
    return result


def line_edges(project, layer):
    """``[(start, end, baseline)]`` for each line a resolved text layer draws, in its box's pixels: where the line's
    pen starts and ends (after alignment) and its baseline, from the layout the renderer draws (after ``fit``).
    Constraint refs such as ``lyric.line[-1].end`` read these."""
    from .richtext import active, fitted

    settings = layer.get("text_layout") or {}
    require(not settings.get("path") and settings.get("warp", "none") == "none",
            f"{layer['name']!r} is set on a path or warped; line and baseline refs need straight text",
            "invalid_constraint", field="constraints")
    if active(layer):
        result = fitted(project, layer)
        rows = [[None, None, row[1]] for row in result.lines]
        for glyph in result.glyphs:
            outline = face(glyph.data)[0]
            advance = outline["hmtx"][glyph.name][0] * glyph.size / outline["head"].unitsPerEm
            row = rows[glyph.line]
            row[0] = glyph.x if row[0] is None else min(row[0], glyph.x)
            row[1] = glyph.x + advance if row[1] is None else max(row[1], glyph.x + advance)
        return [(start or 0.0, end if end is not None else (start or 0.0), baseline) for start, end, baseline in rows]
    layout = plan(project, layer)
    data = font_data(project, layer)
    outline = face(data)[0]  # the same metrics text.measure lays the lines out with
    factor = layout.size / outline["head"].unitsPerEm
    ascent = outline["hhea"].ascent * factor
    pitch = (outline["hhea"].ascent - outline["hhea"].descent) * factor + layer.get("spacing", 4)
    tabs = tab_stops(layer, project)
    width = layer["width"] if "width" in settings else None
    advances = [set_line(data, line, layout.size, tabs)[1]
                for line in lines(data, layer["text"], layout.size, width, wrap_mode(layer), tabs)]
    widest = max(advances, default=0)
    align = layer.get("align", "left")
    edges = []
    for index, advance in enumerate(advances):
        offset = (widest - advance) / 2 if align == "center" else widest - advance if align == "right" else 0
        start = offset - layout.box[0] + layout.offset
        edges.append((start, start + advance, ascent + index * pitch - layout.box[1]))
    return edges


def fit_ceiling(data, text, size, width):
    """The largest size up to ``size`` at which every word fits on a line of ``width``, so fitting
    shrinks a long word instead of breaking it across lines. Advances scale linearly with size;
    a word too wide even at size 1 leaves the ceiling at 1 and is broken as before."""
    words = {word for paragraph in text.expandtabs(4).split("\n") for word in paragraph.split(" ") if word}
    if not words:
        return size
    longest = max(words, key=lambda word: shape(data, word, 1)[1])
    advance = shape(data, longest, 1)[1]
    if advance <= 0 or advance * size <= width:
        return size
    ceiling = max(1, min(size, int(width / advance)))
    while ceiling > 1 and shape(data, longest, ceiling)[1] > width:
        ceiling -= 1
    return ceiling


def plan(project, layer):
    require(len(layer["text"]) <= 100000, "Text exceeds length limit", "resource_limit")
    data = font_data(project, layer)
    settings = layer.get("text_layout", {})
    size, spacing, align = layer["size"], layer.get("spacing", 4), layer.get("align", "left")
    width = layer["width"] if "width" in settings else None
    wrap, tabs = settings.get("wrap", "greedy"), tab_stops(layer, project)
    stroke = layer.get("stroke_width", 0)
    if settings.get("fit") and width:
        low, high = 1, fit_ceiling(data, layer["text"], size, width - 2 * stroke)
        while low < high:
            middle = (low + high + 1) // 2
            _, box = measure(data, layer["text"], middle, spacing, align, width, wrap, tabs)
            if box[2] - box[0] + 2 * stroke <= width and box[3] - box[1] + 2 * stroke <= layer["height"]:
                low = middle
            else:
                high = middle - 1
        size = low
    paths, box = measure(data, layer["text"], size, spacing, align, width, wrap, tabs)
    box = (box[0] - stroke, box[1] - stroke, box[2] + stroke, box[3] + stroke)
    tw, th = max(1, math.ceil(box[2] - box[0])), max(1, math.ceil(box[3] - box[1]))
    limits = project.limits
    require(
        tw <= limits.max_dimension and th <= limits.max_dimension and tw * th <= limits.max_pixels,
        f"Text {layer.get('name', '')!r} at size {size} measures {tw}×{th} px, over the {limits.max_dimension} px / "
        f"{limits.max_pixels:,}-pixel limit; wrap it with text-layout, flow it with text-flow, or use a smaller size",
        "resource_limit",
        field="text",
    )
    target_w, target_h = (layer["width"], layer["height"]) if settings else (tw, th)
    offset = (target_w - tw) / 2 if align == "center" else target_w - tw if align == "right" else 0
    positioned = [(p, (*m[:4], m[4] - box[0] + (offset if settings else 0), m[5] - box[1])) for p, m in paths]
    if settings.get("path"):
        positioned = path_layout(data, layer["text"], size, settings["path"])
    if settings.get("warp", "none") != "none":
        from .emojis import EmojiArt
        require(not any(isinstance(path, EmojiArt) for path, _ in positioned),
                "Emoji artwork cannot be bent with text warp; use unwarped text or font mode", "unsupported_text")
        positioned = warped(positioned, target_w, target_h, settings)
        # A warp moves glyphs by a fraction of the box height, which can push them past the
        # top (flag, arc) or bottom of the box; move the warped line back inside it.
        ys = [float(y) for path, _ in positioned for y in WARPED_Y.findall(path)]
        if ys:
            dy = fit_span(min(ys) - stroke, max(ys) + stroke, target_h)
            positioned = [(path, (1, 0, 0, 1, 0, dy)) for path, _ in positioned]
    return Plan(
        target_w,
        target_h,
        positioned,
        box,
        size,
        offset if settings else 0.0,
        not settings.get("path") and settings.get("warp", "none") == "none",
    )


WARPED_Y = re.compile(r"[ML]-?[\d.]+,(-?[\d.]+)")


def fit_span(top, bottom, height):
    """The vertical shift that brings [top, bottom] inside [0, height] with the least movement.
    Content taller than the box keeps its top visible."""
    if top < 0:
        return -top
    if bottom > height:
        return -min(top, bottom - height)
    return 0


def path_layout(data, text, size, points):
    segments = [(a, b, math.dist(a, b)) for a, b in zip(points, points[1:]) if a != b]
    require(segments, "Text path must have nonzero length")
    glyphs, _ = shape(data, text.replace("\n", " "), size)
    factor = size / face(data)[0]["head"].unitsPerEm
    result = []
    for glyph in glyphs:
        center, offset = glyph.x + glyph.advance / 2, 0
        for a, b, length in segments:
            if center <= offset + length:
                t = (center - offset) / length
                dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                factor = size / face(glyph.data)[0]["head"].unitsPerEm
                path, _ = glyph_outline(glyph.data, glyph.name)
                if not path:
                    break
                x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                result.append(
                    (
                        path,
                        (
                            factor * dx,
                            factor * dy,
                            factor * dy,
                            -factor * dx,
                            x - dx * glyph.advance / 2 - dy * glyph.y,
                            y - dy * glyph.advance / 2 + dx * glyph.y,
                        ),
                    )
                )
                break
            offset += length
    return result


def warped(paths, width, height, settings):
    from fontTools.pens.basePen import BasePen
    from fontTools.svgLib.path import parse_path

    class Pen(BasePen):
        def __init__(self, matrix):
            super().__init__(None)
            self.matrix, self.commands = matrix, []

        def point(self, p):
            a, b, c, d, e, f = self.matrix
            x, y = a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f
            t, amount = 2 * x / max(1, width - 1) - 1, settings.get("amount", 0.2)
            kind = settings["warp"]
            if kind == "bulge":
                factor = max(0.01, 1 - abs(amount) + amount * (1 - t * t))
                y = height / 2 + (y - height / 2) * factor
            else:
                y += amount * height * ((t * t - 0.5) if kind == "arc" else math.sin(t * math.pi))
            return f"{x:.5f},{y:.5f}"

        def _moveTo(self, p):
            self.commands.append("M" + self.point(p))

        def _lineTo(self, p):
            self.commands.append("L" + self.point(p))

        def _curveToOne(self, p1, p2, p3):
            from .geometry import bezier_points

            p0 = self._getCurrentPoint()
            for point in bezier_points((p0, p1, p2, p3), [i / 24 for i in range(1, 25)]).tolist():
                self._lineTo(tuple(point))

        def _qCurveToOne(self, p1, p2):
            p0 = self._getCurrentPoint()
            for i in range(1, 17):
                t = i / 16
                self._lineTo(
                    tuple((1 - t) ** 2 * p0[j] + 2 * (1 - t) * t * p1[j] + t * t * p2[j] for j in (0, 1))
                )

        def _closePath(self):
            self.commands.append("Z")

        def _endPath(self):
            pass

    result = []
    for path, matrix in paths:
        pen = Pen(matrix)
        parse_path(path, pen)
        result.append((" ".join(pen.commands), (1, 0, 0, 1, 0, 0)))
    return result


def append_paths(parent, layout, layer, project, motion=None):
    """Glyph paths as SVG. ``motion`` (kinetic type) gives each path a ``(matrix prefix, opacity,
    fill or None)`` applied on top of its own matrix."""
    from .render import color
    from .design import resolve_color

    fill, stroke = [
        color(resolve_color(layer.get(key, default), project.state))
        for key, default in (("color", "white"), ("stroke_color", "black"))
    ]
    stroked = layer.get("stroke_width", 0) > 0 and stroke[3] > 0  # no-op stroke attributes are left out
    for index, (path, matrix) in enumerate(layout.paths):
        paint, extra = fill, {}
        if motion:
            from .kinetic import multiply

            prefix, opacity, override = motion[index]
            matrix = multiply(prefix, matrix)
            paint = override or fill
            if opacity < 1:
                extra["opacity"] = f"{opacity:.4f}"
        from .emojis import EmojiArt, append_art

        if isinstance(path, EmojiArt):
            append_art(parent, path, matrix, float(extra.get("opacity", 1)))
            continue
        attrs = {
            "d": path,
            "transform": "matrix(" + " ".join(map(str, matrix)) + ")",
            "fill": f"rgb{paint[:3]}",
            "fill-opacity": str(paint[3] / 255),
            **extra,
        }
        if stroked:
            attrs.update(
                {
                    "stroke": f"rgb{stroke[:3]}",
                    "stroke-opacity": str(stroke[3] / 255),
                    "stroke-width": str(
                        2 * layer.get("stroke_width", 0) / max(1e-6, math.hypot(matrix[0], matrix[1]))
                    ),
                    "paint-order": "stroke fill",
                }
            )
        ET.SubElement(parent, "{http://www.w3.org/2000/svg}path", attrs)


def render_text(project, layer, size=None, matrix=None):
    """The text layer as an RGBA image of its box. ``size`` and ``matrix`` draw the same glyphs into an
    image of ``size`` instead, mapped by the affine ``matrix`` (SVG order, from box pixels): the final
    placement of a layer at a fractional position or angle, drawn from the outlines instead of resampled."""
    layout = plan(project, layer)
    if layer.get("_kinetic") and layout.shaped:
        from .kinetic import render_plain

        return render_plain(project, layer, layout, placed_glyphs(project, layer, layout))
    width, height = size or (layout.width, layout.height)
    root = ET.Element(
        "{http://www.w3.org/2000/svg}svg",
        {"width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}"},
    )
    from .emojis import EmojiArt
    from .vector_raster import painted, placed, rasterize

    parent = root if matrix is None else placed(root, matrix)

    stroked = layer.get("stroke_width", 0) > 0 and color_of(project, layer, "stroke_color", "black")[3] > 0
    if not stroked and not any(isinstance(path, EmojiArt) for path, _ in layout.paths):
        # One paint: rasterise the glyphs once as a stencil and paint it, so a recoloured label reuses them.
        append_paths(parent, layout, {**layer, "color": "black"}, project)
        return painted(ET.tostring(root, encoding="unicode"), color_of(project, layer, "color", "white"))
    append_paths(parent, layout, layer, project)
    return rasterize(ET.tostring(root, encoding="unicode"))


def color_of(project, layer, key, default):
    from .render import color
    from .design import resolve_color

    return color(resolve_color(layer.get(key, default), project.state))


def font_digest(data):
    import hashlib

    fonts = data if isinstance(data, tuple) else (data,)
    return hashlib.sha256(b"".join(hashlib.sha256(f).digest() for f in fonts)).hexdigest()
