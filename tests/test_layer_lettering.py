"""Layer-level tracking and text case (#603): they apply to whatever text the layer holds."""

import re
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.lettering import cased_pieces
from vixl.timeline import project_at


def pixels(project):
    return np.asarray(project.render())


def text_project(text, **fields):
    p = Project(700, 200, "#000")
    p.apply({"type": "text", "name": "t", "text": text, "size": 40, "x": 10, "y": 10, "color": "white", **fields})
    return p


def test_text_transform_draws_like_the_cased_text_and_keeps_the_stored_text():
    cased = text_project("hello world", text_transform="uppercase")
    typed = text_project("HELLO WORLD")
    assert cased.layer("t")["text"] == "hello world"
    assert (cased.layer("t")["width"], cased.layer("t")["height"]) == (typed.layer("t")["width"], typed.layer("t")["height"])
    assert np.array_equal(pixels(cased), pixels(typed))


def test_tracking_widens_the_layer_and_zero_removes_it():
    plain = text_project("TRACKED")
    tracked = text_project("TRACKED", tracking=8)
    assert tracked.layer("t")["width"] >= plain.layer("t")["width"] + 8 * 6
    tracked.apply({"type": "text-set", "target": "t", "tracking": 0})
    assert "tracking" not in tracked.layer("t")
    assert tracked.layer("t")["width"] == plain.layer("t")["width"]


def test_tracking_and_case_apply_to_keyed_text():
    p = text_project("first", tracking=10, text_transform="uppercase")
    p.apply({"type": "keyframe", "target": "t", "property": "text", "time": 1000, "value": "second words"})
    later = project_at(p, 1500)
    keyed = next(layer for layer in later.state["layers"] if layer["name"] == "t")
    reference = text_project("SECOND WORDS", tracking=10)
    assert keyed["width"] == reference.layer("t")["width"]
    assert np.array_equal(np.asarray(later.render()), pixels(reference))
    untracked = text_project("SECOND WORDS")
    assert keyed["width"] > untracked.layer("t")["width"]


def test_case_applies_to_variable_values():
    p = Project(700, 200, "#000")
    p.apply([{"type": "variable", "name": "who", "value": "big world"},
             {"type": "text", "name": "t", "text": "hi ${who}", "size": 40, "x": 10, "y": 10, "color": "white",
              "text_transform": "uppercase"}])
    assert np.array_equal(pixels(p), pixels(text_project("HI BIG WORLD")))


def test_capitalize_treats_spans_as_one_text():
    assert cased_pieces(["hel", "lo wor", "ld, don't"], "capitalize") == ["Hel", "lo Wor", "ld, Don't"]
    p = Project(700, 200, "#000")
    p.apply({"type": "rich-text", "name": "r", "size": 40, "spans": [{"text": "hel"}, {"text": "lo world", "bold": True}]})
    p.apply({"type": "text-set", "target": "r", "text_transform": "capitalize"})
    from vixl.render import resolved_layers

    assert resolved_layers(p)[0]["text"] == "Hello World"
    assert p.layer("r")["text"] == "hello world"


def test_layer_tracking_is_the_default_for_rich_spans():
    p = Project(900, 200, "#000")
    p.apply({"type": "rich-text", "name": "r", "size": 40, "spans": [{"text": "AB "}, {"text": "CD", "tracking": 2}]})
    before = p.layer("r")["width"]
    p.apply({"type": "text-set", "target": "r", "tracking": 12})
    after = p.layer("r")["width"]
    # Three characters of "AB " take the layer tracking; "CD" keeps its own 2.
    assert after - before == pytest.approx(36, abs=1)


def test_exports_carry_case_and_tracking(tmp_path):
    p = text_project("hello world", tracking=6, text_transform="capitalize")
    p.export(tmp_path / "t.pptx")
    p.export(tmp_path / "t.pdf")
    p.export(tmp_path / "t.svg")
    slide = zipfile.ZipFile(tmp_path / "t.pptx").read("ppt/slides/slide1.xml").decode()
    assert "Hello World" in re.findall(r"<a:t>([^<]*)</a:t>", slide)
    assert re.search(r'spc="\d+"', slide)
    import pypdfium2

    assert "Hello World" in pypdfium2.PdfDocument(str(tmp_path / "t.pdf"))[0].get_textpage().get_text_range()
    tracked_svg = (tmp_path / "t.svg").read_text()
    text_project("Hello World").export(tmp_path / "plain.svg")
    assert tracked_svg != (tmp_path / "plain.svg").read_text()


def test_fit_text_and_bounds_use_layer_tracking():
    p = text_project("TRACKED DISPLAY TEXT FOR A LYRIC VIDEO", size=57, tracking=4)
    p.apply({"type": "fit-text", "target": "t", "width": 600, "height": 80, "minimum": 8, "maximum": 57})
    assert not [i for i in p.check()["issues"] if i["check"] == "bounds" and i["severity"] == "error"]


def test_aliases_are_normalized_and_reported():
    p = Project(700, 200, "#000")
    result = p.apply({"type": "text", "name": "t", "text": "x", "letter_spacing": 3, "textTransform": "caps"})
    layer = p.layer("t")
    assert layer["tracking"] == 3 and layer["text_transform"] == "uppercase"
    notes = " ".join(result["normalized"])
    assert "'letter_spacing' → 'tracking'" in notes and "'caps' → 'uppercase'" in notes
    result = p.apply({"type": "text-set", "target": "t", "text-transform": "title"})
    assert p.layer("t")["text_transform"] == "capitalize"


def test_invalid_values_are_rejected():
    p = Project(700, 200, "#000")
    with pytest.raises(VixlError):
        p.apply({"type": "text", "text": "x", "text_transform": "shouty"})
    with pytest.raises(VixlError):
        p.apply({"type": "text", "text": "x", "tracking": 5000})


def test_cli_flags():
    op = compile_command(["text", "hi", "--tracking", "4", "--text-transform", "uppercase"])
    assert op["tracking"] == 4 and op["text_transform"] == "uppercase"
    op = compile_command(["text-set", "t", "--tracking", "0"])
    assert op["tracking"] == 0
