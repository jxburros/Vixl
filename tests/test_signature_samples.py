"""Signature fields accept a sample (text or an image) for flattened fills, never as a PDF value."""

import base64
import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.errors import VixlError
from vixl.forms import FieldValueError, coerce, fill, signature_font, with_values

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"
BOX = (225, 600, 1200, 160)


def signed_form():
    p = Project.sized("letter", "#ffffff")
    x, y, w, h = BOX
    p.apply([{"type": "field", "name": "signature", "kind": "signature", "label": "Signature", "required": True,
              "x": x, "y": y, "width": w, "height": h},
             {"type": "field", "name": "full_name", "kind": "text", "label": "Name", "x": 225, "y": 1000, "width": 1200,
              "height": 125}])
    return p


def ink(image):
    x, y, w, h = BOX
    return (np.asarray(image.convert("L"))[y + 5:y + h - 20, x + 5:x + w - 5] < 128).sum()


def png_uri(color=(10, 20, 200, 255)):
    image = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    image.paste(color, (20, 40, 280, 60))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_text_sample_is_drawn_in_flattened_fills():
    p = signed_form()
    assert coerce({"kind": "signature"}, "Ada Lovelace") == ("Ada Lovelace", "Ada Lovelace")
    assert ink(p.render()) == 0
    view = with_values(p, {"signature": "Ada Lovelace"})
    assert ink(view.render()) > 200
    data = p.export(format="PDF", values={"signature": "Ada Lovelace"})
    pypdf = pytest.importorskip("pypdf")
    assert "Ada Lovelace" in pypdf.PdfReader(io.BytesIO(data)).pages[0].extract_text()
    svg = p.export(format="SVG", values={"signature": "Ada Lovelace"}).decode()
    assert "<text" in svg or "<path" in svg


def test_image_sample_is_drawn_in_raster_svg_and_pdf(tmp_path):
    p = signed_form()
    uri = png_uri()
    assert coerce({"kind": "signature"}, uri) == (uri, "")
    image = with_values(p, {"signature": uri}).render().convert("RGB")
    x, y, w, h = BOX
    region = np.asarray(image)[y:y + h, x:x + w]
    assert ((region[..., 2] > 150) & (region[..., 0] < 80)).sum() > 500, "the blue stroke is drawn"
    svg = p.export(format="SVG", values={"signature": uri}).decode()
    assert "data:image/png;base64," in svg
    pdfium = pytest.importorskip("pypdfium2")
    pdf = pdfium.PdfDocument(fill(p, {"signature": uri, "full_name": "Ada"}, tmp_path / "signed.pdf")["output"])
    page = np.asarray(pdf[0].render(scale=300 / 72).to_pil().convert("RGB"))[y:y + h, x:x + w]
    assert ((page[..., 2] > 150) & (page[..., 0] < 80)).sum() > 500


def test_samples_never_become_acroform_values():
    p = signed_form()
    with pytest.raises(VixlError, match="flattened fills"):
        p.export(format="PDF", fillable=True, values={"signature": "Ada"})
    with pytest.raises(VixlError, match="flattened fills"):
        fill(p, {"signature": "Ada", "full_name": "Ada"}, None, format="PDF", mode="editable")
    pypdf = pytest.importorskip("pypdf")
    fields = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", fillable=True))).get_fields()
    assert fields["signature"]["/FT"] == "/Sig" and "/V" not in fields["signature"]


@pytest.mark.parametrize("raw", ["line\nbreak", "x" * 201, "data:image/png;base64,bm90IGFuIGltYWdl",
                                 "data:text/plain;base64,aGk=", 42])
def test_bad_samples_are_rejected(raw):
    with pytest.raises(FieldValueError):
        coerce({"kind": "signature"}, raw)


def test_a_registered_script_font_draws_text_samples():
    from fontTools.ttLib import TTFont

    p = signed_form()
    font = TTFont(FONT)
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = "Dancing Script"
    buffer = io.BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    p.apply({"type": "font-register", "name": "dancing-script-400", "asset": asset})
    assert signature_font(p, p.layer("signature")) == "dancing-script-400"
    # A font set on the field itself wins.
    p.apply({"type": "field-set", "target": "signature", "font": "dancing-script-400"})
    assert signature_font(p, p.layer("signature")) == p.layer("signature")["font"]
