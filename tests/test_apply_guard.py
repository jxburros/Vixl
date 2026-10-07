"""Anything an apply accepts must still render, check and export; anything that cannot is refused at apply time."""

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl.design_schema import SHAPES


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "img.png"
    Image.new("RGB", (30, 20), "red").save(path)
    return str(path)


def roundtrip(project, tmp_path):
    """Save, reopen, render, check and export: what a later session does with the document."""
    project.save(tmp_path / "doc.vixl")
    reopened = Project.load(tmp_path / "doc.vixl")
    reopened.render()
    reopened.check()
    for suffix in ("png", "svg", "pdf", "pptx"):
        reopened.export(tmp_path / f"out.{suffix}")
    return reopened


def test_fractional_integer_fields_round_and_are_reported():
    project = Project(400, 200)
    result = project.apply([{"type": "text", "name": "t", "text": "Hi", "size": 25.6}])
    assert project.layer("t")["size"] == 26
    assert any("size 25.6 → 26" in note for note in result["normalized"])


def test_fractional_image_size_is_accepted(tmp_path, image):
    project = Project(600, 400)
    project.apply([{"type": "add", "path": image, "name": "i", "width": 487.3, "height": 302.1}])
    layer = project.layer("i")
    assert (layer["width"], layer["height"]) == (487, 302)
    roundtrip(project, tmp_path)


def test_fractional_rich_text_width_does_not_poison_the_document(tmp_path):
    project = Project(600, 400)
    project.apply([{"type": "rich-text", "name": "r", "markdown": "Hello **there**", "width": 300.5, "height": 80.25}])
    roundtrip(project, tmp_path)


@pytest.mark.parametrize("shape", sorted(set(SHAPES) - {"path"}))
def test_every_shape_renders_at_fractional_geometry(shape):
    project = Project(300, 200)
    project.apply([{"type": "shape", "shape": shape, "name": "s", "x": 10.5, "y": 7.25, "width": 120.5, "height": 80.75,
                    "stroke": "#000000", "stroke_width": 2.5}])
    project.render()


def test_mixed_fractional_document_survives_a_roundtrip(tmp_path, image):
    project = Project(400, 300)
    project.apply([
        {"type": "text", "name": "t", "text": "Hello", "size": 25.6, "x": 3.5, "y": 4.25},
        {"type": "text-layout", "target": "t", "width": 120.5, "height": 60.5},
        {"type": "add", "path": image, "name": "i", "width": 40.4, "height": 30.6},
        {"type": "resize", "target": "i", "width": 33.3, "height": 21.7},
        {"type": "gradient", "name": "g", "width": 100.5, "height": 50.5, "start": "red", "end": "blue"},
        {"type": "effect", "target": "g", "name": "blur", "amount": 2.5},
        {"type": "shape", "shape": "path", "name": "p", "path": "M 0 0 Q 100 200 200 0", "stroke": "#cc0000",
         "stroke_width": 6},
        {"type": "irregular", "target": "p", "seed": 3},
    ])
    roundtrip(project, tmp_path)


def test_a_blur_that_could_never_render_is_refused_and_leaves_the_document_alone():
    project = Project(4000, 4000)
    project.apply([{"type": "shape", "shape": "ellipse", "name": "e", "width": 2000, "height": 2000}])
    with pytest.raises(VixlError, match="working image") as caught:
        project.apply([{"type": "effect", "target": "e", "name": "blur", "amount": 1000}])
    assert caught.value.code == "resource_limit"
    assert project.layer("e")["effects"] == []
    project.apply([{"type": "effect", "target": "e", "name": "blur", "amount": 300}])


def test_oversized_text_names_the_layer_and_the_remedy():
    project = Project(800, 600)
    with pytest.raises(VixlError, match=r"Text layer 'long' would be .*text-flow") as caught:
        project.apply([{"type": "text", "name": "long", "text": "a" * 100_000, "size": 10}])
    assert caught.value.code == "resource_limit"
