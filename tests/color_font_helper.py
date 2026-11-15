"""Small colour fonts built in memory, one per format (COLRv0, COLRv1, OpenType-SVG, CBDT/CBLC, sbix), for tests
that draw colour-font text without shipping or downloading a font.

Each font maps ``A`` (or ``char``) to a colour glyph 400 units wide and 700 tall standing on the baseline (the lower half red,
the upper half blue or a gradient) and ``B`` to a plain outline box, in a 1000-unit em with an 800/-200 line."""

import io

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables as ot
from PIL import Image

RED, BLUE = (255, 0, 0), (0, 0, 255)
NAMES = [".notdef", "A", "B", "space", "lower", "upper", "c1", "c2", "c3", "c4"]


def _box(x0, y0, x1, y1):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0))
    pen.lineTo((x0, y1))
    pen.lineTo((x1, y1))
    pen.lineTo((x1, y0))
    pen.closePath()
    return pen.glyph()


def _builder(family, outlines=True, empty_a=False, char="A", cmap=None):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(NAMES)
    builder.setupCharacterMap({ord(char): "A", ord("B"): "B", ord(" "): "space", **(cmap or {})})
    blank = TTGlyphPen(None).glyph()
    builder.setupGlyf({".notdef": _box(50, 0, 450, 700), "A": blank if empty_a else _box(50, 0, 450, 700),
                       "B": _box(50, 0, 450, 700), "space": blank, "lower": _box(50, 0, 450, 350),
                       "upper": _box(50, 350, 450, 700), **{name: blank for name in NAMES[6:]}})
    builder.setupHorizontalMetrics({name: (500, 50) for name in NAMES})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": family, "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200, fsType=0)
    builder.setupPost()
    if not outlines:
        del builder.font["glyf"], builder.font["loca"]
    return builder.font


def _saved(font):
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def _png(size=(40, 70)):
    """The colour glyph as a bitmap: red lower half, blue upper half."""
    image = Image.new("RGBA", size, (*BLUE, 255))
    image.paste((*RED, 255), (0, size[1] // 2, size[0], size[1]))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def colr_v0(foreground=False, char="A"):
    """Two flat layers: red below, blue above (or the text colour above, with ``foreground``)."""
    font = _builder("Vixl Test COLRv0", char=char)
    font["CPAL"] = buildCPAL([[(1, 0, 0, 1), (0, 0, 1, 1)]])
    font["COLR"] = buildCOLR({"A": [("lower", 0), ("upper", 0xFFFF if foreground else 1)]}, version=0)
    return _saved(font)


def colr_v1(char="A"):
    """A paint graph: a red layer below and a vertical red-to-blue linear gradient above."""
    font = _builder("Vixl Test COLRv1", char=char)
    font["CPAL"] = buildCPAL([[(1, 0, 0, 1), (0, 0, 1, 1)]])
    stops = [{"StopOffset": 0, "PaletteIndex": 0, "Alpha": 1}, {"StopOffset": 1, "PaletteIndex": 1, "Alpha": 1}]
    font["COLR"] = buildCOLR({"A": (ot.PaintFormat.PaintColrLayers, [
        {"Format": ot.PaintFormat.PaintGlyph, "Glyph": "lower",
         "Paint": {"Format": ot.PaintFormat.PaintSolid, "PaletteIndex": 0, "Alpha": 1.0}},
        {"Format": ot.PaintFormat.PaintGlyph, "Glyph": "upper",
         "Paint": {"Format": ot.PaintFormat.PaintLinearGradient, "ColorLine": {"Extend": "pad", "ColorStop": stops},
                   "x0": 50, "y0": 350, "x1": 50, "y1": 600, "x2": 450, "y2": 350}},
    ])}, version=1)
    return _saved(font)


def colr_v1_paints():
    """COLRv1 paints beyond flat layers, each filling the 400 x 700 box of ``B``: ``A`` a radial gradient (red at
    the centre, yellow, blue at radius 300), ``C`` a sweep gradient of the same stops over the full turn, ``D`` red
    kept only inside the box turned 45 degrees (composite src-in), ``E`` yellow moved by (100, 100) and multiplied
    onto half-transparent blue, cut by a clip box at y = 600, and ``F`` the glyph of ``A`` with a small box in the
    text colour on top."""
    paint = ot.PaintFormat
    font = _builder("Vixl Test COLRv1 Paints", cmap={ord("C"): "c1", ord("D"): "c2", ord("E"): "c3", ord("F"): "c4"})
    font["CPAL"] = buildCPAL([[(1, 0, 0, 1), (0, 0, 1, 1), (1, 1, 0, 1)]])
    line = {"Extend": "pad", "ColorStop": [{"StopOffset": 0, "PaletteIndex": 0, "Alpha": 1},
                                           {"StopOffset": 0.5, "PaletteIndex": 2, "Alpha": 1},
                                           {"StopOffset": 1, "PaletteIndex": 1, "Alpha": 1}]}

    def box(fill):
        return {"Format": paint.PaintGlyph, "Glyph": "B", "Paint": fill}

    def solid(index, alpha=1.0):
        return {"Format": paint.PaintSolid, "PaletteIndex": index, "Alpha": alpha}

    font["COLR"] = buildCOLR({
        "A": box({"Format": paint.PaintRadialGradient, "ColorLine": line, "x0": 250, "y0": 350, "r0": 0,
                  "x1": 250, "y1": 350, "r1": 300}),
        "c1": box({"Format": paint.PaintSweepGradient, "ColorLine": line, "centerX": 250, "centerY": 350,
                   "startAngle": 0, "endAngle": 360}),
        "c2": {"Format": paint.PaintComposite, "CompositeMode": "src_in", "SourcePaint": box(solid(0)),
               "BackdropPaint": {"Format": paint.PaintRotateAroundCenter, "angle": 45, "centerX": 250, "centerY": 350,
                                 "Paint": box(solid(1))}},
        "c3": {"Format": paint.PaintComposite, "CompositeMode": "multiply",
               "SourcePaint": {"Format": paint.PaintTranslate, "dx": 100, "dy": 100, "Paint": box(solid(2))},
               "BackdropPaint": box(solid(1, 0.5))},
        "c4": {"Format": paint.PaintColrLayers, "Layers": [
            {"Format": paint.PaintColrGlyph, "Glyph": "A"},
            {"Format": paint.PaintScaleUniformAroundCenter, "scale": 0.4, "centerX": 250, "centerY": 350,
             "Paint": box(solid(0xFFFF))}]},
    }, version=1, clipBoxes={"c2": (50, 0, 450, 700), "c3": (0, 0, 500, 600)})
    return _saved(font)


def svg(char="A"):
    """An SVG document for ``A`` (glyph 1): y down from the baseline, red below and blue above."""
    from fontTools.ttLib.tables.S_V_G_ import SVGDocument

    font = _builder("Vixl Test SVG", char=char)
    table = newTable("SVG ")
    table.docList = [SVGDocument(
        '<svg xmlns="http://www.w3.org/2000/svg"><g id="glyph1">'
        '<rect x="50" y="-350" width="400" height="350" fill="#ff0000"/>'
        '<rect x="50" y="-700" width="400" height="350" fill="#0000ff"/>'
        '<script>alert(1)</script></g></svg>', 1, 1, False)]
    font["SVG "] = table
    return _saved(font)


def sbix(ppems=(70,), char="A"):
    """Apple-style strikes: a PNG per size for ``A``, whose outline is empty."""
    from fontTools.ttLib.tables.sbixGlyph import Glyph
    from fontTools.ttLib.tables.sbixStrike import Strike

    font = _builder("Vixl Test sbix", char=char, empty_a=True)
    table = newTable("sbix")
    for ppem in ppems:
        strike = Strike(ppem=ppem, resolution=72)
        width, height = round(ppem * 0.4), round(ppem * 0.7)
        strike.glyphs["A"] = Glyph(glyphName="A", graphicType="png ", imageData=_png((width, height)),
                                   originOffsetX=round(ppem * 0.05), originOffsetY=0)
        table.strikes[ppem] = strike
    font["sbix"] = table
    return _saved(font)


CBDT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ttFont>
  <CBDT>
    <header version="3.0"/>
    <strikedata index="0">
      <cbdt_bitmap_format_17 name="A">
        <SmallGlyphMetrics>
          <height value="70"/><width value="40"/><BearingX value="5"/><BearingY value="70"/><Advance value="50"/>
        </SmallGlyphMetrics>
        <rawimagedata>%s</rawimagedata>
      </cbdt_bitmap_format_17>
    </strikedata>
  </CBDT>
  <CBLC>
    <header version="3.0"/>
    <strike index="0">
      <bitmapSizeTable>
        <sbitLineMetrics direction="hori">
          <ascender value="80"/><descender value="-20"/><widthMax value="50"/>
          <caretSlopeNumerator value="0"/><caretSlopeDenominator value="0"/><caretOffset value="0"/>
          <minOriginSB value="0"/><minAdvanceSB value="0"/><maxBeforeBL value="0"/><minAfterBL value="0"/>
          <pad1 value="0"/><pad2 value="0"/>
        </sbitLineMetrics>
        <sbitLineMetrics direction="vert">
          <ascender value="80"/><descender value="-20"/><widthMax value="50"/>
          <caretSlopeNumerator value="0"/><caretSlopeDenominator value="0"/><caretOffset value="0"/>
          <minOriginSB value="0"/><minAdvanceSB value="0"/><maxBeforeBL value="0"/><minAfterBL value="0"/>
          <pad1 value="0"/><pad2 value="0"/>
        </sbitLineMetrics>
        <colorRef value="0"/>
        <startGlyphIndex value="1"/>
        <endGlyphIndex value="1"/>
        <ppemX value="100"/>
        <ppemY value="100"/>
        <bitDepth value="32"/>
        <flags value="1"/>
      </bitmapSizeTable>
      <eblc_index_sub_table_1 imageFormat="17" firstGlyphIndex="1" lastGlyphIndex="1">
        <glyphLoc name="A"/>
      </eblc_index_sub_table_1>
    </strike>
  </CBLC>
</ttFont>"""


def cbdt(char="A"):
    """A Noto Color Emoji style font: one 100 px strike with a PNG for ``A`` and no outlines at all."""
    font = _builder("Vixl Test CBDT", char=char, outlines=False)
    font.importXML(io.StringIO(CBDT_XML % _png().hex()))
    return _saved(font)


FORMATS = {"COLRv0": colr_v0, "COLRv1": colr_v1, "SVG": svg, "CBDT": cbdt, "sbix": sbix}
