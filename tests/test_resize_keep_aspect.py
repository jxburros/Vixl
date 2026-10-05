"""A resize with one dimension changes only that dimension unless keep_aspect says otherwise."""

import pytest

from vixl import Project, VixlError


def document():
    p = Project(200, 100, "white")
    p.apply(
        [
            {"type": "shape", "shape": "rectangle", "name": "bar", "x": 10, "y": 10, "width": 40, "height": 30,
             "fill": "#ff7f50"},
            {"type": "solid", "name": "panel", "color": "#112233", "x": 150, "y": 0, "width": 50, "height": 50},
        ]
    )
    return p



def size(p, name="bar"):
    layer = p.layer(name)
    return layer["width"], layer["height"]


def test_resize_with_only_a_height_leaves_the_width():
    p = document()
    result = p.apply({"type": "resize", "target": "bar", "height": 50})
    assert size(p) == (40, 50)
    assert any("only height" in note and "keep_aspect" in note for note in result["normalized"])
    p.apply({"type": "resize", "target": "panel", "height": 10})
    assert size(p, "panel") == (50, 10)


def test_resize_with_only_a_width_leaves_the_height():
    p = document()
    result = p.apply({"type": "resize", "target": "bar", "width": 100})
    assert size(p) == (100, 30)
    assert any("only width" in note for note in result["normalized"])


def test_resize_keep_aspect_scales_the_other_side_proportionally():
    p = document()
    result = p.apply({"type": "resize", "target": "bar", "height": 60, "keep_aspect": True})
    assert size(p) == (80, 60) and "normalized" not in result
    p.apply({"type": "resize", "target": "bar", "width": 40, "keep_aspect": True})
    assert size(p) == (40, 30)


def test_resize_with_both_dimensions_stretches_and_is_not_reported():
    p = document()
    result = p.apply({"type": "resize", "target": "bar", "width": 10, "height": 90})
    assert size(p) == (10, 90) and "normalized" not in result


def test_images_keep_their_aspect_ratio_unless_keep_aspect_is_false():
    from PIL import Image

    p = Project(200, 100, "white")
    from vixl.assets import add_image

    asset = add_image(p, Image.new("RGB", (40, 20), "red"))
    p.apply({"type": "add", "asset": asset, "name": "photo"})
    p.apply({"type": "resize", "target": "photo", "width": 80})
    assert size(p, "photo") == (80, 40)
    p.apply({"type": "resize", "target": "photo", "height": 10, "keep_aspect": False})
    assert size(p, "photo") == (80, 10)
    p.apply({"type": "resize", "target": "photo", "width": 20, "height": 20})
    assert size(p, "photo") == (20, 20)


def test_keep_aspect_needs_exactly_one_dimension():
    p = document()
    with pytest.raises(VixlError, match="keep_aspect"):
        p.apply({"type": "resize", "target": "bar", "width": 10, "height": 90, "keep_aspect": True})
    assert size(p) == (40, 30)


def test_keep_aspect_spellings_are_normalized():
    p = document()
    result = p.apply({"type": "resize", "target": "bar", "height": 60, "lock_aspect": True})
    assert size(p) == (80, 60) and any("keep_aspect" in note for note in result["normalized"])


def test_percent_height_alone_changes_only_the_height():
    p = document()
    p.apply({"type": "resize", "target": "bar", "height": "50%"})
    assert size(p) == (40, 50)


def test_cli_resize_keep_aspect_flag():
    from vixl.commands import compile_command

    assert compile_command("resize bar --height 60 --keep-aspect") == {
        "type": "resize", "target": "bar", "height": 60, "keep_aspect": True}
    assert compile_command("resize bar --height 60 --no-keep-aspect")["keep_aspect"] is False
    assert "keep_aspect" not in compile_command("resize bar --height 60")
