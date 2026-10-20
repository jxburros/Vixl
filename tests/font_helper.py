"""Small TrueType fonts built in memory, for tests that need a face covering given characters or carrying a given
family, weight and style, without shipping or downloading one."""

import io

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def _box(width=500, height=700):
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, height))
    pen.lineTo((width - 50, height))
    pen.lineTo((width - 50, 0))
    pen.closePath()
    return pen.glyph()


def make_font(chars, family="Test Sans", weight=400, italic=False):
    """TTF bytes of a face named ``family`` that draws each of ``chars`` (and the space) as a filled box."""
    chars = sorted(set(chars) | {" "})
    names = [".notdef", *(f"uni{ord(c):04X}" for c in chars)]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})
    builder.setupGlyf({name: _box() for name in names})
    builder.setupHorizontalMetrics({name: (500, 50) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    style = ("Bold " if weight >= 700 else "") + ("Italic" if italic else "")
    style = style.strip() or "Regular"
    builder.setupNameTable({"familyName": family, "styleName": style,
                            "uniqueFontIdentifier": f"{family}-{weight}-{italic}",
                            "fullName": f"{family} {style}", "psName": f"{family.replace(' ', '')}-{style.replace(' ', '')}"})
    builder.setupOS2(usWeightClass=weight, fsSelection=(0x01 if italic else 0) | (0x20 if weight >= 700 else 0)
                     | (0x40 if style == "Regular" else 0), sTypoAscender=800, sTypoDescender=-200, usWinAscent=800,
                     usWinDescent=200, fsType=0)
    builder.setupPost(italicAngle=-12 if italic else 0)
    builder.font["head"].macStyle = (0x01 if weight >= 700 else 0) | (0x02 if italic else 0)
    buffer = io.BytesIO()
    builder.save(buffer)
    return buffer.getvalue()
