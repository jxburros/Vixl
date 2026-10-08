"""Fillable PDFs with entry_font embed: the field's own font is typed in, Helvetica is the fallback."""

import hashlib
import io
from pathlib import Path

import numpy as np
import pytest

from vixl import Project

pypdf = pytest.importorskip("pypdf")
pdfium = pytest.importorskip("pypdfium2")
FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def font_bytes(fs_type=0):
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = "Form Sans"
        elif record.nameID in (4, 6):
            record.string = "FormSans-Regular"
    font["OS/2"].fsType = fs_type
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def entry_form(fs_type=0, entry_font="embed"):
    p = Project.sized("letter", "#ffffff")
    data = font_bytes(fs_type)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    p.apply([
        {"type": "font-register", "name": "form-sans", "asset": asset},
        {"type": "form", "entry_font": entry_font},
        {"type": "field", "name": "full_name", "kind": "text", "label": "Full name", "font": "form-sans",
         "x": 225, "y": 580, "width": 2100, "height": 125, "size": 42},
        {"type": "field", "name": "notes", "kind": "multiline", "label": "Notes", "font": "form-sans",
         "x": 225, "y": 900, "width": 2100, "height": 400, "size": 42},
        {"type": "field", "name": "size", "kind": "dropdown", "label": "Size", "font": "form-sans", "options": ["S", "M"],
         "x": 225, "y": 1500, "width": 600, "height": 125, "size": 42},
    ])
    return p


def appearances(reader):
    """{field name: /DA} from the page's widgets."""
    annots = (a.get_object() for a in reader.pages[0]["/Annots"])
    return {a["/T"]: a["/DA"] for a in annots if "/T" in a and "/DA" in a}


def acroform(data):
    reader = pypdf.PdfReader(io.BytesIO(data))
    return reader, reader.trailer["/Root"]["/AcroForm"]


def test_embedded_entry_font_is_in_da_and_dr_and_draws_values():
    p = entry_form()
    report = {}
    data = p.export(format="PDF", fillable=True, values={"full_name": "Ada Lovelace", "notes": "Gärten und Straße"},
                    report=report)
    assert report["entry_font"] == {"mode": "embed", "embedded": ["Form Sans"]}
    assert not report.get("warnings")
    reader, form = acroform(data)
    font = form["/DR"]["/Font"]["/VxE1"].get_object()
    assert font["/Subtype"] == "/TrueType" and font["/Encoding"] == "/WinAnsiEncoding"
    assert font["/BaseFont"] == "/FormSans-Regular" and "/FontFile2" in font["/FontDescriptor"]
    assert len(font["/Widths"]) == 224
    das = appearances(reader)
    for key in ("full_name", "notes", "size"):
        assert das[key].startswith("/VxE1 ")
    annot = reader.pages[0]["/Annots"][0].get_object()
    assert "/VxE1" in annot["/AP"]["/N"]["/Resources"]["/Font"]
    document = pdfium.PdfDocument(data)
    document.init_forms()
    page = np.asarray(document[0].render(scale=1, may_draw_forms=True).to_pil().convert("L"))
    assert page[145:164, 60:300].min() < 128, "the prefilled value shows in the embedded font"
    # A viewer filling the field types with the same font resource.
    writer = pypdf.PdfWriter(clone_from=reader)
    writer.update_page_form_field_values(writer.pages[0], {"full_name": "Grace Hopper"})
    buffer = io.BytesIO()
    writer.write(buffer)
    filled = pdfium.PdfDocument(buffer.getvalue())
    filled.init_forms()
    after = np.asarray(filled[0].render(scale=1, may_draw_forms=True).to_pil().convert("L"))
    assert after[145:164, 60:300].min() < 128


def test_appearance_is_laid_out_with_the_embedded_metrics():
    from vixl.pdf_forms import HELV, text_width

    p = entry_form()
    data = p.export(format="PDF", fillable=True, values={"full_name": "WWWW"})
    reader, _ = acroform(data)
    stream = reader.pages[0]["/Annots"][0].get_object()["/AP"]["/N"].get_data().decode("latin-1")
    assert "/VxE1" in stream and "/Helv" not in stream
    # DejaVu Sans is wider than Helvetica: right-aligned text starts further left than Helvetica metrics would put it.
    p.apply({"type": "field-set", "target": "full_name", "align": "right"})
    stream = acroform(p.export(format="PDF", fillable=True, values={"full_name": "WWWW"}))[0].pages[0]["/Annots"][0] \
        .get_object()["/AP"]["/N"].get_data().decode("latin-1")
    x = float(stream.split(" Tm")[0].split()[-2])
    helvetica_x = 2100 * 0.24 - text_width(b"WWWW", 42 * 0.24, HELV)
    assert x < helvetica_x - 1


@pytest.mark.parametrize("fs_type", [2, 4])
def test_restricted_fonts_fall_back_to_helvetica_with_a_warning(fs_type):
    p = entry_form(fs_type)
    report = {}
    data = p.export(format="PDF", fillable=True, report=report)
    assert report["entry_font"]["embedded"] == []
    assert {item["field"] for item in report["entry_font"]["helvetica_fallback"]} == {"full_name", "notes", "size"}
    assert any("Helvetica" in warning and "embedding permission" in warning for warning in report["warnings"])
    reader, form = acroform(data)
    assert appearances(reader)["full_name"].startswith("/Helv ")
    assert "/VxE1" not in form["/DR"]["/Font"]
    issues = p.check(checks=["form"])["issues"]
    assert any("typed in Helvetica" in issue["message"] for issue in issues)


def test_prefilled_embedded_appearance_matches_the_flattened_render():
    from vixl.forms import with_values

    p = entry_form()
    values = {"full_name": "Ada Lovelace", "notes": "Gärten und Straße"}
    document = pdfium.PdfDocument(p.export(format="PDF", fillable=True, values=values))
    document.init_forms()
    pdf = document[0].render(scale=300 / 72, may_draw_forms=True).to_pil().convert("RGB").crop((0, 0, 2550, 3300))
    png = with_values(p, values).render().convert("RGB")
    assert np.abs(np.asarray(pdf, float) - np.asarray(png, float)).mean() < 1


def test_standard_entry_font_is_unchanged():
    p = entry_form(entry_font="standard")
    report = {}
    data = p.export(format="PDF", fillable=True, report=report)
    assert "entry_font" not in report
    reader, form = acroform(data)
    assert set(form["/DR"]["/Font"]) == {"/Helv", "/ZaDb"}
    assert appearances(reader)["full_name"].startswith("/Helv ")
