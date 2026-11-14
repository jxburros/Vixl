"""Templates filled from data (#772): an image slot keeps a default picture, and a strict batch refuses failing rows."""

import hashlib
import io
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image
import pytest

from vixl import Project
from vixl.cli import main
from vixl.errors import VixlError


def pictures(folder):
    Image.new("RGB", (40, 20), "red").save(folder / "red.png")
    Image.new("RGB", (20, 40), "blue").save(folder / "blue.png")


def test_binding_an_image_slot_to_a_new_variable_keeps_its_picture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pictures(tmp_path)
    project = Project(20, 20, workspace=str(tmp_path))
    project.apply([{"type": "frame", "name": "photo", "path": "red.png", "width": 20, "height": 20, "fit": "fill"},
                   {"type": "replace-contents", "target": "photo", "variable": "picture"}])
    asset = project.layer("photo")["asset"]
    assert project.state["variables"] == {"picture": asset}
    assert project.render().getpixel((10, 10)) == (255, 0, 0, 255)  # was: Undefined image variable: picture
    (tmp_path / "rows.csv").write_text("picture\nblue.png\nred.png\n", encoding="utf-8")
    first, second = project.render_data(tmp_path / "rows.csv", tmp_path / "out")
    assert Image.open(first["output"]).convert("RGB").getpixel((10, 10)) == (0, 0, 255)
    assert Image.open(second["output"]).convert("RGB").getpixel((10, 10)) == (255, 0, 0)
    assert project.state["variables"] == {"picture": asset}

    # A variable that already exists keeps its value.
    other = Project(20, 20, workspace=str(tmp_path))
    other.apply([{"type": "frame", "name": "photo", "path": "red.png", "width": 20, "height": 20, "fit": "fill"},
                 {"type": "frame", "name": "second", "path": "blue.png", "width": 20, "height": 20, "fit": "fill"}])
    blue = other.layer("second")["asset"]
    other.apply([{"type": "variable", "name": "picture", "value": blue},
                 {"type": "replace-contents", "target": "photo", "variable": "picture"}])
    assert other.state["variables"]["picture"] == blue


def card_face():
    """The proofing font under another family name: the fonts check refuses the bundled face itself."""
    font = TTFont(io.BytesIO((Path(__file__).parents[1] / "src/vixl/data/DejaVuSans.ttf").read_bytes()))
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = "Card Face"
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def template(tmp_path):
    project = Project(400, 200, "#ffffff", workspace=str(tmp_path))
    data = card_face()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply([{"type": "font-register", "name": "card-face", "asset": asset},
                   {"type": "variable", "name": "title", "value": "Short"},
                   {"type": "text", "name": "title", "text": "${title}", "x": 40, "y": 60, "size": 48,
                    "color": "#111111", "font": "card-face"}])
    assert project.check()["passed"], project.check()["issues"]
    (tmp_path / "rows.csv").write_text(
        "title\nShort\nA title that runs far past the right edge of this small card\n", encoding="utf-8")
    return project


def test_strict_data_rendering_refuses_the_batch_when_a_row_fails_its_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = template(tmp_path)
    with pytest.raises(VixlError) as refused:
        project.render_data(tmp_path / "rows.csv", tmp_path / "strict", strict=True)
    assert refused.value.code == "design_check_failed" and refused.value.details["rows"] == [2]
    assert "row(s) 2" in str(refused.value) and not (tmp_path / "strict").exists()
    results = project.render_data(tmp_path / "rows.csv", tmp_path / "loose")
    assert [result.get("check", {}).get("passed", True) for result in results] == [True, False]
    assert len(list((tmp_path / "loose").glob("*.png"))) == 2


def test_cli_render_data_strict_names_the_failing_rows(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VIXL_JSON", "1")
    template(tmp_path).save(tmp_path / "card.vixl")
    assert main(["-p", "card.vixl", "render", "--data", "rows.csv", "--out", "strict", "--strict"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "design_check_failed" and "row(s) 2" in error["message"]
    assert not (tmp_path / "strict").exists()
    assert main(["-p", "card.vixl", "render", "--data", "rows.csv", "--out", "loose"]) == 0
    assert len(list((tmp_path / "loose").glob("*.png"))) == 2
