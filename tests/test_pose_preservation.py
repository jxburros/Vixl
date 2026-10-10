"""Edits that should keep a layer where it appears: default rotation turns about the centre (#449),
``about`` picks another fixed point, and reparenting leaves the rendered pixels in place (#468)."""

import numpy as np
import pytest
from PIL import Image, ImageFilter

from vixl import Project
from vixl.group_bake import corners, placement


def where(p, name):
    _, full, rest, _ = placement(p, p.layer(name)["id"])
    return corners(full, rest)


def centre(p, name):
    return where(p, name).mean(axis=0)


def ink_centroid(image, select):
    pixels = np.asarray(image.convert("RGB"), dtype=np.float64)
    weight = select(pixels)
    ys, xs = np.indices(weight.shape)
    return np.array([(xs * weight).sum(), (ys * weight).sum()]) / weight.sum()


def black(pixels):
    return (255 - pixels.mean(axis=2)) / 255


def bar(**extra):
    p = Project(400, 400, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "r", "x": 150, "y": 175, "width": 100, "height": 50,
             "fill": "black", **extra})
    return p


@pytest.mark.parametrize("angle", [45, 30, 90, 13.5, 270])
def test_rotate_without_a_pivot_turns_about_the_centre(angle):
    p = bar()
    before = ink_centroid(p.render(), black)
    p.apply({"type": "rotate", "target": "r", "value": angle})
    assert np.allclose(centre(p, "r"), (200, 200))
    assert np.abs(ink_centroid(p.render(), black) - before).max() < 0.05


def test_rotating_back_restores_the_stored_position():
    p = bar()
    for angle in (45, 17, 300, 0):
        p.apply({"type": "rotate", "target": "r", "value": angle})
    assert (p.layer("r")["x"], p.layer("r")["y"]) == pytest.approx((150, 175))


def test_rotation_at_creation_keeps_the_unrotated_box_centre():
    p = bar(rotation=45)
    assert np.allclose(centre(p, "r"), (200, 200))


def test_about_keeps_a_named_anchor_or_fraction_fixed():
    p = bar()
    p.apply({"type": "rotate", "target": "r", "value": 90, "about": "top-left"})
    assert np.allclose(where(p, "r")[0], (150, 175))
    q = bar()
    q.apply({"type": "rotate", "target": "r", "value": 30, "about": [1, 0.5]})
    assert np.allclose(where(q, "r")[[1, 2]].mean(axis=0), (250, 200))  # the right edge's midpoint
    # The old alias anchor reads as about and is reported.
    result = bar().apply({"type": "rotate", "target": "r", "value": 90, "anchor": "bottom-right"})
    assert any("'anchor' → 'about'" in note for note in result["normalized"])


def test_about_pivot_and_another_point_on_a_pivoted_layer():
    p = bar()
    p.apply([{"type": "pivot", "target": "r", "value": "left"}, {"type": "rotate", "target": "r", "value": 90, "about": "pivot"}])
    assert np.allclose(where(p, "r")[[0, 3]].mean(axis=0), (150, 200))  # the left edge's midpoint stays put
    q = bar()
    q.apply([{"type": "pivot", "target": "r", "value": "left"}, {"type": "rotate", "target": "r", "value": 90, "about": "center"}])
    assert np.allclose(centre(q, "r"), (200, 200)) and q.layer("r")["pivot"] == [0, 0.5]


def test_scale_about_reads_as_anchor_and_takes_pivot():
    p = bar()
    result = p.apply({"type": "scale", "target": "r", "value": 2, "about": "center"})
    assert any("'about' → 'anchor'" in note for note in result["normalized"])
    assert np.allclose(centre(p, "r"), (200, 200))
    q = bar()
    q.apply([{"type": "pivot", "target": "r", "value": "bottom-right"}, {"type": "move", "target": "r", "x": 10, "y": 10},
             {"type": "scale", "target": "r", "value": 0.5, "anchor": "pivot"}])
    assert np.allclose(where(q, "r")[2], (110, 60))


def test_unknown_about_is_a_field_error():
    with pytest.raises(Exception) as caught:
        bar().apply({"type": "rotate", "target": "r", "value": 10, "about": "middle-ish"})
    assert "about" in str(caught.value)


def rotated_dog():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "shape", "name": "body", "shape": "rectangle", "x": 120, "y": 100, "width": 120, "height": 70,
         "fill": "#884422"},
        {"type": "shape", "name": "head", "shape": "ellipse", "x": 230, "y": 70, "width": 60, "height": 50,
         "fill": "#aa6633"},
        {"type": "group", "name": "dog", "targets": ["body", "head"]},
        {"type": "rotate", "target": "dog", "value": 20},
        {"type": "shape", "name": "eye", "shape": "ellipse", "x": 60.3, "y": 120.7, "width": 37.4, "height": 21.9,
         "fill": "#113355", "rotation": 33.3},
    ])
    return p


def blue(pixels):
    return (pixels[:, :, 2] > pixels[:, :, 0] + 40) * (255 - pixels[:, :, 0]) / 255


def test_reparent_into_a_rotated_group_keeps_the_rendered_pixels():
    p = rotated_dog()
    shape = where(p, "eye")
    before = p.render()
    p.apply({"type": "reparent", "targets": ["eye"], "into": "dog"})
    after = p.render()
    assert np.abs(where(p, "eye") - shape).max() < 1e-6
    # The group grew around the eye; its own artwork is drawn on exactly the same pixels.
    a, b = (np.asarray(image.convert("RGB"), dtype=np.int16) for image in (before, after))
    eye = Image.fromarray(np.uint8((a[:, :, 2] > a[:, :, 0] + 20) | (b[:, :, 2] > b[:, :, 0] + 20)) * 255)
    near = np.asarray(eye.filter(ImageFilter.MaxFilter(5))) > 0
    assert (np.abs(a - b).max(axis=2)[~near] > 3).sum() == 0
    # The eye itself is resampled twice now (in the group, then with it) but does not move.
    assert np.abs(ink_centroid(after, blue) - ink_centroid(before, blue)).max() < 0.1
    p.apply({"type": "reparent", "targets": ["eye"], "into": None})
    assert np.abs(ink_centroid(p.render(), blue) - ink_centroid(before, blue)).max() < 0.1
