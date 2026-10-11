"""Font fallbacks pick the face of a fallback family whose weight and slope match the primary."""

import hashlib
import io
from pathlib import Path

import pytest

from vixl import Project
from vixl.text import font_data, font_style

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"
CYRILLIC = "Жж"


def face(family, weight, *, italic=False, latin_only=False):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    if latin_only:
        options = subset.Options()
        options.name_IDs = ["*"]
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=range(32, 127))
        subsetter.subset(font)
    style = ("Bold" if weight >= 600 else "Regular") + (" Italic" if italic else "")
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = family
        elif record.nameID in (2, 17):
            record.string = style
        elif record.nameID in (4, 6):
            record.string = f"{family.replace(' ', '')}-{style.replace(' ', '')}"
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~1) | (1 if italic else 0)
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def register(project, name, data):
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": name, "asset": asset})


@pytest.fixture
def document():
    p = Project(800, 400, "white")
    register(p, "primary-700", face("Primary Sans", 700, latin_only=True))
    register(p, "primary-400", face("Primary Sans", 400, latin_only=True))
    for weight in (400, 700, 300):
        register(p, f"fallback-{weight}", face("Fallback Sans", weight))
    register(p, "fallback-700-italic", face("Fallback Sans", 700, italic=True))
    p.apply({"type": "font-fallbacks", "fonts": ["fallback-400", "fallback-300", "fallback-700-italic", "fallback-700"]})
    return p


@pytest.mark.parametrize("primary, expected", [("primary-700", (700, False)), ("primary-400", (400, False))])
def test_fallback_face_follows_the_primary_weight(document, primary, expected):
    document.apply({"type": "text", "name": "t", "text": "Hi " + CYRILLIC, "font": primary, "size": 40, "color": "black"})
    chain = font_data(document, document.layer("t"))
    assert font_style(chain[1])[1:] == expected
    assert [font_style(data)[0] for data in chain[1:5]] == ["Fallback Sans"] * 4
    # Family order is kept; the bundled fonts stay last.
    assert [font_style(data)[0] for data in chain[-5:]] == [
        "DejaVu Sans", "Noto Sans", "Noto Sans Symbols", "Noto Sans Symbols 2", "Noto Sans Math"]


def test_pdf_and_rich_text_embed_the_matching_face(document):
    pypdf = pytest.importorskip("pypdf")
    document.apply({"type": "text", "name": "t", "text": "Bold " + CYRILLIC, "font": "primary-700", "size": 40,
                    "color": "black"})
    reader = pypdf.PdfReader(io.BytesIO(document.export(format="PDF")))
    fonts = reader.pages[0]["/Resources"]["/Font"]
    names = {str(fonts[key].get_object()["/BaseFont"]).split("+")[-1] for key in fonts}
    assert "FallbackSans-Bold" in names and "FallbackSans-Regular" not in names
    from vixl.richtext import style_font_data

    chain = style_font_data(document, document.state["fonts"]["primary-700"], CYRILLIC)
    assert font_style(chain[1])[1] == 700


def test_pptx_runs_name_the_fallback_family_for_fallback_characters(document):
    import zipfile

    pytest.importorskip("pptx")
    document.apply({"type": "text", "name": "t", "text": "Bold " + CYRILLIC, "font": "primary-700", "size": 40,
                    "color": "black"})
    report = {}
    data = document.export(format="PPTX", report=report)
    slide = zipfile.ZipFile(io.BytesIO(data)).read("ppt/slides/slide1.xml").decode()
    assert '<a:latin typeface="Primary Sans"/>' in slide and f"<a:t>{CYRILLIC}</a:t>" in slide
    assert slide.index('typeface="Fallback Sans"') > slide.index("<a:t>Bold </a:t>")
    assert {"Primary Sans", "Fallback Sans"} <= set(report["fonts"])


def test_italic_primary_prefers_an_italic_fallback(document):
    register(document, "primary-italic", face("Primary Sans", 700, italic=True, latin_only=True))
    document.apply({"type": "text", "name": "t", "text": CYRILLIC, "font": "primary-italic", "size": 40, "color": "black"})
    assert font_style(font_data(document, document.layer("t"))[1])[1:] == (700, True)
