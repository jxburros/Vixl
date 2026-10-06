from PIL import Image
import pytest

from vixl import Project
from vixl.assets import add_image
from vixl.briefs import guide
from vixl.errors import VixlError
from vixl.layouts import LAYOUTS, describe
from vixl.render import resolve_layout

MEMES = {
    "meme-top-bottom": ({"title": "When the build passes", "caption": "on the first try and nobody was watching"}, 1),
    "meme-caption-above": ({"title": "Me explaining why the meeting could have been an email"}, 1),
    "meme-comparison": ({"items": "Writing docs by hand\nGenerating them from the schema"}, 2),
    "meme-labelled": ({"items": "Me\nNew framework\nWorking code"}, 1),
    "meme-reaction": ({"caption": "Me reading my own code from last year"}, 1),
    "meme-four-panel": ({"items": "Idea\nPrototype\nScope creep\nRewrite everything from scratch again"}, 4),
}


def build(name, size=(1080, 1080)):
    slots, count = MEMES[name]
    project = Project(*size)
    assets = [add_image(project, Image.new("RGB", (320, 320), color)) for color in ("#c96", "#69c", "#9c6", "#c69")[:count]]
    images = {"images": assets} if count > 1 else {"image": assets[0]}
    project.apply({"type": "layout-apply", "name": name, "seed": 1, **slots, **images})
    return project, assets


@pytest.mark.parametrize("name", sorted(MEMES))
@pytest.mark.parametrize("size", [(1080, 1080), (1080, 1920), (1600, 900)])
def test_meme_layout_fills_every_slot_and_its_text_fits(name, size):
    project, assets = build(name, size)
    assert not project.state["layout"].get("blanks")
    frames = [layer for layer in project.state["layers"] if layer["type"] == "frame"]
    assert sorted(layer["asset"] for layer in frames) == sorted(assets)
    bounds = resolve_layout(project)
    for layer in project.state["layers"]:
        if layer["type"] == "text":
            x, y, w, h = bounds[layer["id"]]
            assert x >= 0 and y >= 0 and x + w <= size[0] and y + h <= size[1], layer["name"]
            assert "\n" not in layer["text"]
    report = project.check()
    assert report["errors"] == 0, [issue["message"] for issue in report["issues"] if issue["severity"] == "error"]


def test_stroked_captions_are_uppercase_white_with_a_black_outline():
    project, _ = build("meme-top-bottom")
    top = project.layer("top-text")
    assert top["text"] == "WHEN THE BUILD PASSES" and top["color"] == "#ffffff"
    assert top["styles"]["stroke"]["color"] == "#000000" and top["styles"]["stroke"]["width"] >= 3
    keep_case = Project(1080, 1080)
    keep_case.apply({"type": "layout-apply", "name": "meme-top-bottom", "title": "Hello there", "uppercase": False,
                     "unfilled": "omit", "seed": 1})
    assert keep_case.layer("top-text")["text"] == "Hello there"


def test_long_words_shrink_instead_of_breaking():
    project = Project(600, 600)
    project.apply({"type": "layout-apply", "name": "meme-four-panel", "seed": 1, "unfilled": "omit",
                   "items": "Supercalifragilistic\nb\nc\nd"})
    bounds = resolve_layout(project)
    first = project.layer("caption-1")
    assert bounds[first["id"]][2] <= 300 and first["size"] < 60


def test_unfilled_meme_slots_are_blanks_with_next_steps():
    project = Project(1080, 1080)
    result = project.apply({"type": "layout-apply", "name": "meme-four-panel", "seed": 1})
    blanks = project.state["layout"]["blanks"]
    assert {blank["slot"] for blank in blanks} == {"items", "images"}
    assert sum(blank["slot"] == "images" for blank in blanks) == 4
    assert project.check()["errors"]  # blanks never ship silently
    assert describe("meme-comparison")["slots"]["images"]["blank_if_unfilled"]
    assert "next_steps" in str(result) or project.state["layout"]["notes"]
    with pytest.raises(VixlError):
        Project(200, 200).apply({"type": "layout-apply", "name": "meme-comparison", "images": ["a", "b", "c"]})


def test_meme_brief_guidance_and_catalog():
    assert set(MEMES) <= set(LAYOUTS)
    found = guide("make a meme with top text and bottom text")
    assert found["matched"] == "meme" and {item["name"] for item in found["layouts"]} == set(MEMES)
    text = guide("meme")["principles"]
    assert "Anton" in text and "OFL" in text and "vixl_export_timeline" in text
