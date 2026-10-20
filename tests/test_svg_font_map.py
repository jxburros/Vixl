"""``font_map`` and ``install_fonts`` on SVG import (library and REST), checked like the PDF path (#712)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vixl
from vixl import Project
from vixl.errors import VixlError
from vixl.fonts import register_font_data
from vixl.imports import import_document
from vixl.interfaces import create_app

SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
       b'<text x="4" y="30" font-family="Obscura" font-size="20">Hello</text></svg>')


def registered(project):
    data = (Path(vixl.__file__).parent / "data" / "NotoSans-Regular.ttf").read_bytes()
    register_font_data(project, data, "mine")
    return project.state["fonts"]["mine"]


def text_font(project):
    return next(layer["font"] for layer in project.state["layers"] if layer["type"] == "text")


def test_svg_import_applies_font_map():
    target = Project(10, 10)
    asset = registered(target)
    unmapped = import_document(target.clone(), SVG, "svg")
    assert any("Obscura" in w for w in unmapped["warnings"])
    result = import_document(target, SVG, "svg", font_map={"Obscura": "mine"})
    assert not any("Obscura" in w for w in result.get("warnings", []))
    assert text_font(target) == asset


def test_svg_font_map_target_must_be_registered():
    with pytest.raises(VixlError) as caught:
        import_document(Project(10, 10), SVG, "svg", font_map={"Obscura": "nope"})
    assert caught.value.code == "missing_font" and caught.value.details["field"] == "font_map"


def test_rest_import_accepts_font_map_and_install_fonts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    project = Project(10, 10)
    asset = registered(project)
    path = tmp_path / "a.vixl"
    project.save(path)
    client = TestClient(create_app(path))
    bad = client.post("/import", params={"format": "svg", "font_map": "Obscura=nope"}, content=SVG)
    assert bad.status_code >= 400 and "missing_font" in bad.text and "font_map" in bad.text
    ok = client.post("/import", params={"format": "svg", "font_map": "Obscura=mine", "install_fonts": "true"},
                     content=SVG)
    assert ok.status_code == 200, ok.text
    assert text_font(Project.load(path)) == asset
    figma = client.post("/import", params={"format": "figma", "font_map": "A=mine"}, content=b"key")
    assert figma.status_code >= 400
