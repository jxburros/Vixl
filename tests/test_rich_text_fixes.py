"""Rich text: variables keep span formatting, fonts checks follow span fonts, text-set keeps formatting."""

import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from fontTools import subset
from fontTools.ttLib import TTFont

import vixl
from vixl import Project

DEJAVU = Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf"
LIBERATION = "/usr/share/fonts/truetype/liberation/"


def register(project, name, data=None):
    """Embed a font under a name; the bundled font's bytes stand in for a real typeface."""
    data = data or DEJAVU.read_bytes()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": name, "asset": asset})
    return asset


def limited_font(tmp_path, text="ABC "):
    font = TTFont(DEJAVU)
    sub = subset.Subsetter()
    sub.populate(text=text)
    sub.subset(font)
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def fonts_issues(project):
    return [issue for issue in project.check(checks=["fonts"])["issues"] if issue["check"] == "fonts"]


# --- #60: variables inside a span keep the span's formatting -------------------------------------


def test_variable_in_a_span_renders_with_the_span_style():
    p = Project(320, 200, "white")
    p.apply([{"type": "variable", "name": "n", "value": "42"},
             {"type": "rich-text", "name": "var", "markdown": "Page [${n}]{color=#ff0000 size=60}", "size": 20,
              "color": "black", "x": 10, "y": 10},
             {"type": "rich-text", "name": "lit", "markdown": "Page [42]{color=#ff0000 size=60}", "size": 20,
              "color": "black", "x": 10, "y": 100}])
    image = p.render().convert("RGB")
    var, lit = (np.asarray(image.crop((0, top, 320, top + 90))) for top in (0, 90))
    assert (var[..., 0] > 200).any() and ((var[..., 1] < 60) & (var[..., 0] > 200)).any()  # red digits drawn
    assert np.array_equal(var, lit)
    # The resolved layer still matches its rich record, so every renderer draws the spans.
    from vixl.render import resolved_layers
    from vixl.richtext import active

    layer = next(item for item in resolved_layers(p) if item["name"] == "var")
    assert active(layer) and layer["text"] == "Page 42"
    assert layer["rich"]["spans"][1] == {"text": "42", "color": "#ff0000", "size": 60.0}
    assert p.layer("var")["text"] == "Page ${n}"  # the stored document keeps the variable


@pytest.mark.skipif(not Path(LIBERATION + "LiberationSerif-Regular.ttf").exists(), reason="no system fonts")
def test_master_page_number_keeps_its_font_in_pdf_and_pptx():
    pypdf = pytest.importorskip("pypdf")
    pptx = pytest.importorskip("pptx")
    p = Project(960, 540, "white")
    register(p, "footer", Path(LIBERATION + "LiberationSerif-Regular.ttf").read_bytes())
    p.apply([{"type": "master", "action": "add", "name": "std"},
             {"type": "rich-text", "name": "num", "markdown": "[${page} / ${pages}]{font=footer size=40}", "size": 14,
              "color": "black", "x": 700, "y": 400},
             {"type": "page", "action": "add", "name": "cover", "master": "std"}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF")))
    names = {str(font.get_object()["/BaseFont"]) for page in reader.pages
             for font in (page["/Resources"].get("/Font") or {}).values()}
    assert len(names) == 1 and "LiberationSerif" in names.pop()
    deck = pptx.Presentation(io.BytesIO(p.export(format="PPTX")))
    runs = [run for slide in deck.slides for shape in slide.shapes if shape.has_text_frame
            for para in shape.text_frame.paragraphs for run in para.runs]
    assert [run.text for run in runs] == ["1 / 1"] and "Liberation Serif" in runs[0].font.name
    assert runs[0].font.size.pt > 30  # the span's size (40), not the layer's 14


# --- #54: the fonts check follows span-level fonts -------------------------------------------------


def test_fonts_check_resolves_span_fonts():
    p = Project(600, 300, "white")
    register(p, "copy")
    p.apply([{"type": "rich-text", "name": "spans", "markdown": "[Hello]{font=copy} [world]{font=copy}", "color": "black"},
             {"type": "rich-text", "name": "mixed", "markdown": "[Hello]{font=copy} plain words", "color": "black",
              "y": 100},
             {"type": "text", "name": "plain", "text": "Bundled", "color": "black", "y": 200}])
    flagged = fonts_issues(p)
    assert [issue["layers"] for issue in flagged] == [["mixed", "plain"]]
    assert "2 text layer(s) use the bundled fallback font" in flagged[0]["message"]
    # Whitespace-only separator spans do not count as text drawn in the fallback font.
    p.apply([{"type": "rich-text", "name": "lines", "markdown": "[one]{font=copy}\n[two]{font=copy}", "y": 0,
              "color": "black"}])
    assert "lines" not in sum((issue["layers"] for issue in fonts_issues(p)), [])
    p.apply([{"type": "remove", "target": "mixed"}, {"type": "remove", "target": "plain"}])
    assert fonts_issues(p) == []


def test_layer_font_still_counts_when_a_span_has_none():
    p = Project(300, 100, "white")
    register(p, "copy")
    p.apply([{"type": "rich-text", "name": "t", "font": "copy", "markdown": "all [x]{bold} body", "color": "black"}])
    assert fonts_issues(p) == []


def test_glyph_fallback_uses_the_span_font(tmp_path):
    p = Project(400, 100, "white")
    register(p, "limited", limited_font(tmp_path, "ABC "))
    p.apply({"type": "rich-text", "name": "t", "markdown": "[ABC ↗]{font=limited}", "color": "black"})
    issue = next(i for i in fonts_issues(p) if "fallback glyphs" in i["message"])
    assert issue["fallback"] == ["↗"] and issue["layers"] == ["t"]
    assert not any("bundled fallback font" in i["message"] for i in fonts_issues(p))
