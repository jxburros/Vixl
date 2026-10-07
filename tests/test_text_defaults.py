"""Text with no font or colour uses the document's body face and an ink that reads on the canvas."""

import io
from importlib import resources

import pytest
from fontTools.ttLib import TTFont

from vixl import Project
from vixl.checks import check_design


@pytest.mark.parametrize("background, ink", [("#ffffff", "#111111"), ("#fbf7f0", "#111111"),
                                             ("#101820", "#ffffff"), ("transparent", "#111111")])
def test_default_text_ink_reads_on_the_canvas(background, ink):
    project = Project(400, 200, background=background)
    project.apply([{"type": "text", "name": "t", "text": "Hi"}, {"type": "rich-text", "name": "r", "markdown": "**x**"}])
    assert project.layer("t")["color"] == project.layer("r")["color"] == ink
    contrast = [issue for issue in check_design(project, checks=["contrast"])["issues"] if issue.get("check") == "contrast"]
    assert not contrast


def test_default_text_ink_prefers_the_ink_swatch():
    project = Project(400, 200, background="#ffffff")
    project.apply([{"type": "swatch", "name": "ink", "color": "#203040"}, {"type": "text", "name": "t", "text": "Hi"}])
    assert project.layer("t")["color"] == "@ink"


def test_explicit_colour_wins():
    project = Project(400, 200, background="#ffffff")
    project.apply([{"type": "text", "name": "t", "text": "Hi", "color": "white"}])
    assert project.layer("t")["color"] == "white"


def test_plain_text_uses_the_body_face_when_typography_exists(tmp_path):
    from vixl.fonts import import_font

    font = TTFont(io.BytesIO(resources.files("vixl").joinpath("data/DejaVuSans.ttf").read_bytes()))
    font["name"].setName("Bodyface", 1, 3, 1, 0x409)
    font.save(tmp_path / "body.ttf")
    project = Project(400, 200, background="#ffffff")
    import_font(project, str(tmp_path / "body.ttf"), "bodyface")
    project.state["typography"] = {"heading": "bodyface", "body": "bodyface"}
    project.apply([{"type": "text", "name": "t", "text": "Hi"}])
    layer = project.layer("t")
    assert layer.get("font_role") == "body" and layer["font"] != "DejaVuSans.ttf"
    assert not [issue for issue in check_design(project, checks=["fonts"])["issues"] if issue.get("check") == "fonts"]


def test_python_export_defaults_to_the_same_alpha_as_cli_and_mcp(tmp_path):
    from PIL import Image

    from vixl.cli import main

    project = Project(40, 30, background="#ffffff")
    project.save(tmp_path / "doc.vixl")
    project.export(tmp_path / "py.png")
    assert main(["-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "cli.png")]) == 0
    assert Image.open(tmp_path / "py.png").mode == Image.open(tmp_path / "cli.png").mode == "RGB"
