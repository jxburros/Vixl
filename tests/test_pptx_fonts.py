"""PPTX export does not embed fonts, and says so: every font a viewer may lack is named in the result."""

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from vixl import Project

pptx = pytest.importorskip("pptx")
FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def _renamed_font(family):
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = family
        elif record.nameID == 6:
            record.string = family.replace(" ", "") + "-Regular"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def _deck_with_fonts(*families):
    p = Project(1920, 1080, "white")
    operations = []
    for family in families:
        data = _renamed_font(family)
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        p.assets[asset] = data
        operations.append({"type": "font-register", "name": family.lower().replace(" ", "-"), "asset": asset})
    p.apply(operations)
    for number, family in enumerate(families):
        p.apply({"type": "text", "name": f"t{number}", "text": f"Set in {family}", "size": 60, "x": 100, "y": 100 + 200 * number,
                 "color": "black", "font": family.lower().replace(" ", "-")})
    return p


def test_fonts_a_deck_needs_are_named_in_warnings():
    p = _deck_with_fonts("Young Serif", "Rubik")
    report = {}
    data = p.export(format="PPTX", report=report)
    assert report["fonts"] == ["Rubik", "Young Serif"] and report["fonts_not_embedded"] == ["Rubik", "Young Serif"]
    assert len(report["warnings"]) == 2
    for family, warning in zip(report["fonts_not_embedded"], report["warnings"]):
        assert f"'{family}'" in warning and "not embedded" in warning and "install" in warning and "PDF" in warning
    # The file itself is an ordinary PPTX that python-pptx opens, without any font part or list a viewer could reject.
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert not [n for n in names if n.startswith("ppt/fonts/") or n.endswith(".fntdata")]
    assert b"embeddedFontLst" not in zipfile.ZipFile(io.BytesIO(data)).read("ppt/presentation.xml")
    assert len(pptx.Presentation(io.BytesIO(data)).slides) == 1


def test_standard_office_fonts_need_no_warning():
    p = _deck_with_fonts("Arial", "Times New Roman")
    report = {}
    p.export(format="PPTX", report=report)
    assert report["fonts"] == ["Arial", "Times New Roman"]
    assert "warnings" not in report and "fonts_not_embedded" not in report


def test_default_proofing_font_is_warned_about():
    p = Project(1920, 1080, "white")
    p.apply({"type": "text", "name": "t", "text": "Plain", "size": 60, "x": 100, "y": 100, "color": "black"})
    report = {}
    p.export(format="PPTX", report=report)
    assert report["fonts_not_embedded"] == ["DejaVu Sans"] and "DejaVu Sans" in report["warnings"][0]


def test_mcp_export_file_returns_the_warnings(tmp_path):
    from vixl.interfaces import Session
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    session.create("deck.vixl", 1920, 1080, "white")
    session.apply([{"type": "text", "name": "t", "text": "Hi", "size": 60, "x": 100, "y": 100, "color": "black"}],
                  document="deck.vixl")
    result = export_file(session, "deck.pptx", document="deck.vixl")
    assert result["format"] == "PPTX" and result["slides"] == 1 and result["warnings"]
    assert result["fonts_not_embedded"] == result["fonts"] == ["DejaVu Sans"]
