"""How the picture and copy layouts share the canvas height at their recommended sizes (#803-#808).

`tests/test_layout_quality.py` is the gate (no fix or composition finding); these pin the behaviour behind it."""
import pytest
from PIL import Image

from vixl import Project
from vixl.assets import add_image
from vixl.composition import THRESHOLDS, geometry_boxes
from vixl.layouts import IMAGE_LAYOUTS, describe

STEP = THRESHOLDS["hierarchy_ratio"]


def build(name, size, seed, **fields):
    project = Project.sized(size, seed=seed)
    copy = {key: slot["example"] for key, slot in describe(name)["slots"].items() if "example" in slot}
    op = {"type": "layout-apply", "name": name, "seed": seed, **copy, **fields}
    if name in IMAGE_LAYOUTS:
        op["image"] = add_image(project, Image.new("RGBA", (400, 300), "#88aa66"))
    project.apply(op)
    return project


def boxes(project):
    resolved, geometry = geometry_boxes(project)
    return {layer["name"]: geometry[ident] for ident, layer in resolved.items()}


def sizes(project):
    return {layer["name"]: layer["size"] for layer in project.state["layers"] if layer["type"] == "text"}


def overlap(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


@pytest.mark.parametrize("size", ["instagram-post", "instagram-story", "poster-18x24", "photo-5x7"])
@pytest.mark.parametrize("seed", range(1, 7))
def test_rule_of_thirds_copy_never_crosses_the_focal_point(size, seed):
    placed = boxes(build("rule-of-thirds", size, seed))
    focal = placed.get("image") or placed["focal"]
    for name in ("label", "headline", "subtitle", "cta-button"):
        assert not overlap(placed[name], focal), name


@pytest.mark.parametrize("seed", range(1, 7))
def test_split_screen_story_keeps_minor_text_at_its_minimum_on_a_panel(seed):
    project = build("split-screen", "instagram-story", seed)
    placed, text = boxes(project), sizes(project)
    # The picture gives up height instead of the type: label, body and button keep the story's minimum size.
    assert text["label"] == text["body"] == text["cta"] >= 34
    assert text["headline"] >= STEP * text["body"]
    panel, image = placed["panel"], placed["image"]
    assert image[3] >= 0.3 * 1920 and abs(panel[3] + image[3] - 1920) <= 1
    for name in ("label", "headline", "body", "cta-button"):
        assert panel[1] <= placed[name][1] and placed[name][1] + placed[name][3] <= panel[1] + panel[3], name


@pytest.mark.parametrize("seed", range(1, 7))
def test_split_screen_square_headline_keeps_its_step_over_the_body(seed):
    text = sizes(build("split-screen", "instagram-post", seed))
    assert text["headline"] >= STEP * text["body"]


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_golden_section_copy_fills_the_minor_section_on_a_page(seed):
    project = build("golden-section", "letter", seed)
    placed, canvas = boxes(project), project.state["canvas"]
    margin = placed["label"][0]
    image, button = placed["image"], placed["cta-button"]
    assert abs(canvas["height"] - (button[1] + button[3]) - margin) <= 2  # the copy ends on the bottom margin
    assert abs(placed["label"][1] - (image[1] + image[3]) - margin) <= margin * 0.1  # and starts one margin under it
    assert 0.55 * canvas["height"] <= image[3] <= 0.7 * canvas["height"]


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_golden_section_story_sets_the_copy_on_a_panel_over_the_safe_inset(seed):
    placed = boxes(build("golden-section", "instagram-story", seed))
    panel, button = placed["panel"], placed["cta-button"]
    assert panel[1] + panel[3] == 1920 and button[1] + button[3] <= 1920 - 250
    top, bottom = placed["label"][1] - panel[1], 1920 - (button[1] + button[3])
    assert bottom < THRESHOLDS["edge_band_ratio"] * top


@pytest.mark.parametrize("size", ["instagram-post", "og-image", "web-banner", "instagram-story"])
@pytest.mark.parametrize("seed", range(1, 7))
def test_z_pattern_leaves_no_hole_between_headline_and_body(size, seed):
    project = build("z-pattern", size, seed)
    placed, text, height = boxes(project), sizes(project), project.state["canvas"]["height"]
    headline, body = placed["headline"], placed["body"]
    assert 0 < body[1] - (headline[1] + headline[3]) < THRESHOLDS["dead_band_hole"] * height
    assert text["body"] == text["label"]  # the body box is sized to its copy, not the copy to a fixed box
    # A shallow banner has room for one step: the headline is capped by the height it shares with the body.
    assert text["headline"] >= (1.3 if size == "web-banner" else STEP) * text["body"]


@pytest.mark.parametrize("name,size", [("banner", "x-header"), ("banner", "email-banner"),
                                       ("photo-caption", "ebook-cover")])
@pytest.mark.parametrize("seed", (1, 2, 3))
def test_headline_keeps_a_step_over_the_subtitle_where_minimums_flatten_the_scale(name, size, seed):
    text = sizes(build(name, size, seed))
    # The step asked for is the hierarchy ratio; the headline's measure may cap it a little under on a cover.
    assert text["headline"] >= 1.4 * text["subtitle"]


@pytest.mark.parametrize("size", ["letter", "poster-18x24"])
@pytest.mark.parametrize("seed", (1, 2, 3))
def test_editorial_grid_column_ends_on_the_bottom_margin(size, seed):
    project = build("editorial-grid", size, seed)
    placed, canvas = boxes(project), project.state["canvas"]
    margin, body = placed["label"][0], placed["body"]
    assert canvas["height"] - (body[1] + body[3]) <= margin * 1.15
    assert placed["image"][3] >= 0.42 * (canvas["height"] - 2 * margin - placed["headline"][3]) * 0.9


def test_editorial_grid_long_body_keeps_the_picture_at_its_share():
    long = "\n".join(["Body copy that runs on for the length of a real article paragraph, line after line."] * 30)
    project = build("editorial-grid", "letter", 1, body=long)
    placed, canvas = boxes(project), project.state["canvas"]
    assert placed["image"][3] <= 0.42 * canvas["height"]
    assert placed["body"][1] + placed["body"][3] <= canvas["height"]
