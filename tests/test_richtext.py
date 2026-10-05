"""Rich text: Markdown, spans, paragraphs and lists, layout, rendering and editing."""

import hashlib

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.richtext import layout, parse_markdown, plain

LIBERATION = "/usr/share/fonts/truetype/liberation/"


def ink(image, box=None):
    region = image.crop(box) if box else image
    return int((np.asarray(region.convert("L")) < 128).sum())


def test_markdown_dialect():
    spans, paragraphs = parse_markdown(
        "# Title\nplain **bold** *it* _it2_ ***both*** __under__ ~~gone~~ ==mark== x^2^ H~2~O \\*star\\*\n"
        "- one\n  - nested\n3. three\n4. four\n[red words]{color=#d22 size=30 italic}")
    text = plain({"spans": spans})
    assert text.split("\n") == ["Title", "plain bold it it2 both under gone mark x2 H2O *star*", "one", "nested", "three",
                                "four", "red words"]
    styled = {span["text"]: {k: v for k, v in span.items() if k != "text"} for span in spans}
    assert styled["Title"]["bold"] and styled["Title"]["scale"] == 1.6
    assert styled["bold"] == {"bold": True} and styled["it"] == {"italic": True} and styled["it2"] == {"italic": True}
    assert styled["both"] == {"bold": True, "italic": True} and styled["under"] == {"underline": True}
    assert styled["gone"] == {"strike": True} and styled["mark"]["highlight"]
    assert styled["red words"] == {"color": "#d22", "size": 30.0, "italic": True}
    assert paragraphs[2:6] == [{"list": "bullet", "level": 0}, {"list": "bullet", "level": 1},
                               {"list": "number", "level": 0, "start": 3}, {"list": "number", "level": 0, "start": 4}]


def test_rich_text_creates_wrapped_and_auto_sized_layers():
    p = Project(600, 400)
    p.apply([{"type": "rich-text", "name": "auto", "markdown": "Hello **world**", "size": 30},
             {"type": "rich-text", "name": "box", "markdown": "a long line of words that must wrap " * 3, "size": 24,
              "width": 220}])
    auto, box = p.layer("auto"), p.layer("box")
    assert auto["text"] == "Hello world" and auto["auto_size"] and auto["rich"]["spans"][1] == {"text": "world", "bold": True}
    assert box["width"] == 220 and box["text_layout"]["height"] == box["height"] > 100
    result = layout(p, box)
    assert len(result.lines) >= 4 and result.box[2] <= 220


def test_fit_shrinks_to_the_box():
    p = Project(400, 200)
    p.apply([{"type": "rich-text", "name": "f", "markdown": "A **fitted** headline that is far too large", "size": 90,
              "width": 300, "height": 100, "fit": True}])
    from vixl.richtext import fitted

    result = fitted(p, p.layer("f"))
    assert result.size_scale < 1 and result.box[3] <= 100 and result.box[2] <= 300.5


def test_lists_number_and_nest():
    p = Project(500, 400)
    p.apply([{"type": "rich-text", "name": "l", "size": 20, "markdown": "1. a\n2. b\n  - x\n  - y\n3. c\n   1. deep"}])
    markers = "".join(g.text for g in layout(p, p.layer("l")).glyphs)
    assert markers.startswith("1.a2.b") and "◦x◦y" in markers and "3.c" in markers and "a.deep" in markers


def test_text_style_ranges_paragraphs_and_clearing():
    p = Project(500, 200, "white")
    p.apply([{"type": "text", "name": "t", "text": "red here and red there\nsecond line", "size": 24, "color": "black"},
             {"type": "text-style", "target": "t", "match": "red", "occurrence": 2, "color": "#ff0000"},
             {"type": "text-style", "target": "t", "start": 0, "end": 3, "bold": True},
             {"type": "text-style", "target": "t", "paragraphs": [1], "list": "bullet", "paragraph_align": "right"}])
    rich = p.layer("t")["rich"]
    assert [s for s in rich["spans"] if s.get("color")] == [{"text": "red", "color": "#ff0000"}]
    assert rich["spans"][0] == {"text": "red", "bold": True}
    assert rich["paragraphs"][1] == {"list": "bullet", "align": "right"}
    p.apply([{"type": "text-style", "target": "t", "clear": True}])
    assert p.layer("t")["rich"]["spans"] == [{"text": "red here and red there\nsecond line"}]
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "text-style", "target": "t", "match": "blue", "bold": True}])
    assert error.value.details["field"] == "match"


def test_text_set_keeps_styles_for_base_changes_and_drops_them_for_new_text():
    p = Project(300, 100)
    p.apply([{"type": "rich-text", "name": "t", "markdown": "keep **this**"},
             {"type": "text-set", "target": "t", "color": "blue", "size": 30}])
    assert p.layer("t")["rich"]
    p.apply([{"type": "text-set", "target": "t", "text": "fresh words"}])
    assert "rich" not in p.layer("t")


def test_rendering_draws_styles():
    p = Project(700, 120, "white")
    p.apply([{"type": "rich-text", "name": "a", "markdown": "Weight test", "size": 40, "color": "black", "x": 10, "y": 10},
             {"type": "rich-text", "name": "b", "markdown": "**Weight test**", "size": 40, "color": "black", "x": 360, "y": 10},
             {"type": "rich-text", "name": "c", "markdown": "==glow==", "size": 30, "color": "black", "x": 10, "y": 70}])
    image = p.render()
    assert ink(image, (360, 0, 700, 70)) > ink(image, (0, 0, 350, 70)) * 1.15
    pixels = np.asarray(image.convert("RGB").crop((10, 70, 120, 115))).reshape(-1, 3)
    assert ((pixels[:, 0] > 240) & (pixels[:, 1] > 230) & (pixels[:, 2] < 150)).any()  # the yellow highlight
    svg = p.export(format="SVG")
    assert b"<image" not in svg and b'fill="rgb(255,241,118)"' in svg


def test_justify_fills_lines_but_not_the_last():
    p = Project(400, 300)
    p.apply([{"type": "rich-text", "name": "j", "size": 20, "width": 300, "align": "justify",
              "markdown": "words that wrap across several lines so justification spreads them evenly to both edges here"}])
    result = layout(p, p.layer("j"))
    rights = {}
    for glyph in result.glyphs:
        line = min(range(len(result.lines)), key=lambda i: abs(result.lines[i][1] - glyph.y))
        rights[line] = max(rights.get(line, 0), glyph.x)
    assert all(rights[i] > 280 for i in range(len(result.lines) - 1)) and rights[len(result.lines) - 1] < 280


def test_validation_and_variables():
    p = Project(300, 100)
    p.apply([{"type": "variable", "name": "who", "value": "Ada"},
             {"type": "rich-text", "name": "t", "markdown": "Hi **${who}**"}])
    assert "Ada" in "".join(g.text for g in layout(p, p.layer("t")).glyphs)
    with pytest.raises(VixlError):
        p.apply([{"type": "rich-text", "name": "bad", "spans": [{"text": "x", "weight": 700}]}])
    from vixl.validation import check_state

    state = p.state
    state["layers"][-1]["rich"]["spans"][0]["text"] = "changed"
    with pytest.raises(VixlError):
        check_state(p, state)


@pytest.mark.skipif(not __import__("os").path.exists(LIBERATION + "LiberationSerif-Bold.ttf"), reason="no system fonts")
def test_registered_bold_and_italic_variants_are_used():
    from vixl.richtext import styled_spans

    p = Project(400, 100)
    assets = {}
    for name, file in (("serif-400", "LiberationSerif-Regular.ttf"), ("serif-700", "LiberationSerif-Bold.ttf"),
                       ("serif-400-italic", "LiberationSerif-Italic.ttf")):
        data = open(LIBERATION + file, "rb").read()
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        p.assets[asset] = data
        assets[name] = asset
        p.apply([{"type": "font-register", "name": name, "asset": asset}])
    p.apply([{"type": "rich-text", "name": "t", "font": "serif-400", "markdown": "a **b** *c* ***d***"}])
    spans = {s["text"]: s for s in styled_spans(p, p.layer("t"))}
    assert spans["b"]["font"] == assets["serif-700"] and not spans["b"]["fake_bold"]
    assert spans["c"]["font"] == assets["serif-400-italic"] and not spans["c"]["fake_italic"]
    assert spans["d"]["font"] == assets["serif-700"] and spans["d"]["fake_italic"]


def test_preview_scaling_and_overflow_check():
    from vixl.proxy import scaled_project

    p = Project(800, 400, "white")
    p.apply([{"type": "rich-text", "name": "t", "markdown": "Big **and** small", "size": 60, "list_indent": 40,
              "width": 700, "height": 90}])
    half = scaled_project(p, 0.5)
    assert half.layer("t")["rich"]["list_indent"] == 20
    p.apply([{"type": "text-layout", "target": "t", "width": 120, "height": 40}])
    issues = p.check(checks=["bounds"])["issues"]
    assert any("does not fit" in issue["message"] for issue in issues)


def test_cli_compiles_rich_text_commands():
    from vixl.commands import compile_command

    assert compile_command(["rich-text", "Hi **there**\\n- one", "--name", "t", "--width", "300"]) == {
        "type": "rich-text", "markdown": "Hi **there**\n- one", "name": "t", "width": 300}
    assert compile_command(["text-style", "t", "--match", "there", "--bold", "--color", "red"]) == {
        "type": "text-style", "target": "t", "match": "there", "bold": True, "color": "red"}
    assert compile_command(["text-style", "t", "--paragraphs", "0,2", "--list", "number", "--number-start", "5"]) == {
        "type": "text-style", "target": "t", "paragraphs": [0, 2], "list": "number", "number_start": 5}
