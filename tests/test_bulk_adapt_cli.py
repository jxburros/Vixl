"""The command line reaches edit-layers and both modes of adapt-layout (issue #86)."""

import json

import pytest

from vixl import Project
from vixl.cli import main


def run(capsys, *argv):
    code = main(["--json", *argv])
    captured = capsys.readouterr()
    text = captured.out if captured.out.strip() else captured.err  # Errors are JSON on stderr.
    return code, (json.loads(text) if text.strip() else None)


@pytest.fixture
def poster(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Project(400, 400, "white")
    p.apply([{"type": "text", "name": f"price-{i}", "text": "$5", "size": 20, "x": 10, "y": 10 + i * 40, "color": "black"}
             for i in range(1, 4)]
            + [{"type": "shape", "shape": "ellipse", "name": "logo", "width": 40, "height": 40, "x": 340, "y": 340,
                "fill": "red"}])
    p.save(tmp_path / "poster.vixl")
    return tmp_path / "poster.vixl"


def test_edit_layers_from_the_command_line(poster, capsys):
    code, result = run(capsys, "-p", str(poster), "edit-layers", "--where", '{"name": "price-*"}',
                       "--do", '{"type": "text-set", "color": "#c00"}', "--expect", "3")
    assert code == 0 and result["edit_layers"][0]["matched"] == 3
    saved = Project.load(poster)
    assert all(saved.layer(f"price-{i}")["color"] == "#c00" for i in (1, 2, 3))
    code, result = run(capsys, "-p", str(poster), "edit-layers", "--where", '{"kind": "shape"}',
                       "--do", '{"type": "hide"}', "--dry-run")
    assert result["edit_layers"][0]["dry_run"] is True and Project.load(poster).layer("logo")["visible"]
    code, result = run(capsys, "-p", str(poster), "edit-layers", "--where", '{"kind": "txt"}', "--do", '{"type": "hide"}')
    assert code != 0 and "Did you mean 'text'" in result["message"]


def test_adapt_layout_from_the_command_line_in_both_modes(poster, capsys):
    code, result = run(capsys, "-p", str(poster), "adapt-layout", "--size", "story", "--anchors",
                       '{"logo": "bottom-right"}', "--detail", "brief")
    assert code == 0 and result["adapt_layout"][0]["canvas"]["to"] == [1080, 1920]
    assert Project.load(poster).state["canvas"]["size"] == "story"
    code, result = run(capsys, "-p", str(poster), "adapt-layout", "--targets", "price-1", "price-2", "--width", "300",
                       "--height", "500", "--margin", "10")
    assert code == 0 and "adapt_layout" not in result
    code, result = run(capsys, "-p", str(poster), "adapt-layout", "--scale", "fit")
    assert code != 0 and "requires at least one of" in result["message"]
