"""CLI flags for the 0.24 fields that were reachable only through JSON, and help that matches the code."""

import json

import pytest

from vixl import Project
from vixl.cli import main
from vixl.commands import compile_command
from vixl.looks import LOOKS


def run(capsys, *argv):
    code = main(["--json", *argv])
    captured = capsys.readouterr()
    text = captured.out if captured.out.strip() else captured.err
    return code, (json.loads(text) if text.strip() else None)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["stack", "box", "--gap", "2u"], {"type": "stack", "target": "box", "gap": "2u"}),
        (["stack", "box", "--gap", "12"], {"type": "stack", "target": "box", "gap": 12.0}),
        (["layout", "apply", "hero-statement", "--gap", "1.5u"],
         {"type": "layout-apply", "name": "hero-statement", "gap": "1.5u"}),
        (["timeline", "set", "--loop-mode", "off", "--close"], {"type": "timeline-set", "loop_mode": "off", "close": True}),
        (["animate", "a", "opacity", "--to", "1", "--intent", "entrance"],
         {"type": "animate", "target": "a", "property": "opacity", "to": 1, "intent": "entrance"}),
        (["frame", "--path", "x.png", "--frame-shape", "heart"], {"type": "frame", "path": "x.png", "frame_shape": "heart"}),
        (["frame", "--path", "x.png", "--outline", "M0 0 L10 0 L5 8 Z"],
         {"type": "frame", "path": "x.png", "outline": "M0 0 L10 0 L5 8 Z"}),
        (["adapt-layout", "--size", "story", "--recompose"], {"type": "adapt-layout", "size": "story", "recompose": True}),
    ],
)
def test_flags_compile_to_the_operation_fields(command, expected):
    assert compile_command(command) == expected


def test_spacing_flag_rejects_other_words():
    with pytest.raises(Exception, match="2u"):
        compile_command(["stack", "box", "--gap", "wide"])


def test_stack_gap_units_resolve_to_pixels(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    p = Project(400, 400, "white")
    p.apply([{"type": "text", "name": n, "text": n, "size": 20, "x": 10, "y": 10, "color": "black"} for n in ("a", "b")])
    p.save(tmp_path / "doc.vixl")
    code, _ = run(capsys, "-p", "doc.vixl", "stack", "box", "--targets", "a", "b", "--gap", "2u")
    assert code == 0
    gap = Project.load(tmp_path / "doc.vixl").layer("box")["stack"]["gap"]
    assert isinstance(gap, (int, float)) and gap > 0


def test_adapt_layout_recompose_from_the_command_line(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    p = Project(1080, 1080, "white")
    p.apply([{"type": "layout-apply", "name": "hero-statement", "title": "Hello"}])
    p.save(tmp_path / "doc.vixl")
    code, result = run(capsys, "-p", "doc.vixl", "adapt-layout", "--size", "story", "--recompose")
    assert code == 0, result
    canvas = Project.load(tmp_path / "doc.vixl").state["canvas"]
    assert (canvas["width"], canvas["height"]) == (1080, 1920)
    assert result["adapt_layout"][0]["mode"] == "recompose"


def test_top_level_help_lists_every_look_and_house_style_versions(capsys):
    main(["--help"])
    text = capsys.readouterr().out
    for name in LOOKS:
        assert name in text, name
    assert "--house-style 1|2" in text


def test_command_inventory_includes_emoji_and_capabilities(capsys):
    code, result = run(capsys, "commands")
    assert code == 0 and {"emoji", "capabilities"} <= set(result["commands"])
