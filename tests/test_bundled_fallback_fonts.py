"""Bundled Noto fallback faces draw the Latin, Greek, Cyrillic and symbol characters DejaVu Sans lacks (#419)."""

from pathlib import Path

import pytest

from vixl import Project
from vixl.text import BUNDLED_FALLBACKS, coverage, file_bytes, glyph_coverage

DATA = Path(__file__).resolve().parents[1] / "src" / "vixl" / "data"
# Each character is missing from DejaVu Sans: power symbol, helm, alchemical air, ⟁, ⧉, a Cyrillic letter
# from Extended-C and a Latin letter from Extended-D.
MIXED = "Ελληνικά Кириллица ⏻ ⎈ 🜁 ⟁ ⧉ ᲀ Ꟁ"


def test_dejavu_lacks_the_sample_characters():
    dejavu = coverage(file_bytes(DATA / "DejaVuSans.ttf"))
    assert all(ord(c) not in dejavu for c in MIXED.split(" ", 2)[2].replace(" ", ""))


def test_mixed_script_and_symbol_text_has_no_tofu_offline():
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": MIXED, "size": 40, "color": "black"})
    layer = p.layer("t")
    report = glyph_coverage(p, layer)
    assert report["missing"] == []
    assert not [i for i in p.check()["issues"] if i["check"] == "fonts" and i.get("missing")]


@pytest.mark.parametrize("kind", ["svg", "pdf", "pptx"])
def test_exports_draw_fallback_glyphs(tmp_path, kind):
    p = Project(900, 200, "#fff")
    p.apply({"type": "text", "name": "t", "text": MIXED, "size": 40, "color": "black"})
    p.export(tmp_path / f"t.{kind}")
    if kind == "pdf":
        import pypdfium2

        text = pypdfium2.PdfDocument(str(tmp_path / "t.pdf"))[0].get_textpage().get_text_range()
        assert "⏻" in text and "⧉" in text
    if kind == "pptx":
        import zipfile

        slide = zipfile.ZipFile(tmp_path / "t.pptx").read("ppt/slides/slide1.xml").decode()
        assert 'typeface="Noto Sans Symbols 2"' in slide


def test_bundled_files_and_licence_ship_together():
    total = sum((DATA / name).stat().st_size for name in BUNDLED_FALLBACKS)
    assert total < 6 * 1024 * 1024
    licence = (DATA / "NOTO-LICENSE.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert all(name in licence for name in BUNDLED_FALLBACKS)
