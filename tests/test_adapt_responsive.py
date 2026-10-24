"""Responsive adaptation (#519): priorities, focal crops, arrangements scored by the checks, required copy that is
never truncated, and check suites run on every adapted copy."""

import numpy as np
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session

RED = (230, 40, 40)


def photo(path, size=(600, 400), subject=(0.8, 0.5)):
    """A blue picture with a red square subject centred at ``subject`` (fractions)."""
    image = Image.new("RGB", size, "#3a86ff")
    cx, cy = subject[0] * size[0], subject[1] * size[1]
    image.paste(RED, (int(cx - 30), int(cy - 30), int(cx + 30), int(cy + 30)))
    image.save(path)
    return str(path)


def master(tmp_path):
    p = Project(1200, 900, "#fdf6ec")
    p.apply([
        {"type": "add", "path": photo(tmp_path / "photo.png"), "name": "photo", "x": 80, "y": 80, "width": 540,
         "height": 360},
        {"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 90, "x": 80, "y": 500,
         "color": "#1d3557"},
        {"type": "text", "name": "body", "text": "Live music by the water every Friday in June", "size": 36,
         "x": 80, "y": 620, "color": "#1d3557"},
        {"type": "text", "name": "url", "text": "tidepool.example", "size": 24, "x": 80, "y": 800,
         "color": "#1d3557"},
        {"type": "layer-intent", "target": "url", "priority": "optional"},
        {"type": "layer-intent", "target": "headline", "priority": "required"},
    ])
    return p


ARRANGE = ["stack-vertical", "side-by-side", "hero-top", "proportional"]


@pytest.mark.parametrize("size", [{"width": 1080, "height": 1080}, {"size": "story"}, {"width": 1920, "height": 1080}],
                         ids=["square", "portrait", "landscape"])
def test_one_master_gives_square_portrait_and_landscape_variants_with_the_required_copy(tmp_path, size):
    p = master(tmp_path)
    report = p.apply({"type": "adapt-layout", **size, "arrangements": ARRANGE}, detail="brief")["adapt_layout"][0]
    assert report["recomposed"] is True and report["arrangement"] in ARRANGE
    assert {item["arrangement"] for item in report["candidates"]} == set(ARRANGE)
    assert "requirements" not in report
    width, height = p.state["canvas"]["width"], p.state["canvas"]["height"]
    for name in ("headline", "body"):
        layer = p.inspect(name)
        x, y, w, h = layer["resolved_bounds"]
        assert layer["visible"] and layer["text"] == p.layer(name)["text"]
        assert p.layer(name)["size"] >= report["min_text"]
        assert x >= 0 and y >= 0 and x + w <= width and y + h <= height, name
    assert report["outcome"]["state"] in ("validated", "needs_review")
    assert report["outcome"]["validated_by"] == ["design checks", "adapt-layout requirements"]


def test_the_best_arrangement_wins_and_a_landscape_one_passes(tmp_path):
    p = master(tmp_path)
    report = p.apply({"type": "adapt-layout", "width": 1920, "height": 1080, "arrangements": ARRANGE},
                     detail="brief")["adapt_layout"][0]
    best = next(item for item in report["candidates"] if item["arrangement"] == report["arrangement"])
    assert best["passed"] and report["outcome"]["state"] == "validated"
    assert "passed" in report["reason"]
    # The photo and the copy no longer overlap and the copy sits beside or below the photo.
    photo_box = p.inspect("photo")["resolved_bounds"]
    head = p.inspect("headline")["resolved_bounds"]
    assert head[0] >= photo_box[0] + photo_box[2] or head[1] >= photo_box[1] + photo_box[3]


def test_when_no_arrangement_passes_the_closest_needs_review(tmp_path):
    p = master(tmp_path)
    report = p.apply({"type": "adapt-layout", "size": "leaderboard", "arrangements": ARRANGE},
                     detail="brief")["adapt_layout"][0]
    assert not any(item.get("passed") for item in report["candidates"])
    assert report["outcome"]["state"] == "needs_review" and report["outcome"]["review"] == "required"
    assert report["findings"] and "needs review" in report["reason"]


def test_an_impossible_fit_reports_the_required_copy_and_never_truncates_it():
    p = Project(1080, 1080, "white")
    words = "Every Friday in June the harbour fills with music, food stalls and lanterns until late at night " * 3
    p.apply([{"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 90, "x": 80, "y": 80,
              "color": "black"},
             {"type": "text", "name": "body", "text": words, "size": 40, "x": 80, "y": 260, "color": "black"},
             {"type": "text-layout", "target": "body", "width": 900, "height": 700}])
    report = p.apply({"type": "adapt-layout", "width": 320, "height": 100, "min_text": 14,
                      "arrangements": ["stack-vertical", "proportional"]}, detail="brief")["adapt_layout"][0]
    failed = {item["layer"]: item for item in report["requirements"]["failed"]}
    assert "body" in failed and failed["body"]["font_size"] >= 14
    assert report["outcome"]["state"] != "validated" and report["outcome"]["validation"] == "failed"
    body = p.layer("body")
    assert body["visible"] and body["text"] == words and body["size"] >= 14
    from vixl.checks import boxed_text_overflow
    assert not boxed_text_overflow(p, body)  # its box holds every line: nothing is cut off


def test_proportional_mode_never_cuts_required_copy_off_in_its_box():
    p = Project(1080, 1080, "white")
    p.apply([{"type": "text", "name": "body", "text": "Live music by the water every Friday in June and July",
              "size": 40, "x": 80, "y": 80, "color": "black"},
             {"type": "text-layout", "target": "body", "width": 400, "height": 120}])
    p.apply({"type": "adapt-layout", "size": "leaderboard"})
    from vixl.checks import boxed_text_overflow
    assert not boxed_text_overflow(p, p.layer("body"))


def test_optional_and_decorative_copy_give_way_but_required_copy_never_does():
    p = Project(1080, 1080, "white")
    p.apply([{"type": "text", "name": name, "text": text, "size": 30, "x": 80, "y": y, "color": "black"}
             for name, text, y in (("must", "Doors at 8", 80), ("maybe", "Free entry", 200),
                                   ("ornament", "* * *", 320), ("legacy", "tidepool.example", 440))])
    p.apply([{"type": "layer-intent", "target": "maybe", "priority": "optional"},
             {"type": "layer-intent", "target": "ornament", "priority": "decorative"}])
    p.layer("legacy")["tags"] = ["optional"]  # how documents saved before priorities marked optional copy
    report = p.apply({"type": "adapt-layout", "size": "leaderboard", "min_text": 20},
                     detail="brief")["adapt_layout"][0]
    assert sorted(report["dropped"]) == ["legacy", "maybe", "ornament"]
    assert p.layer("must")["visible"] and p.layer("must")["size"] == 20


def test_the_optional_tag_is_an_alias_for_priority_optional():
    p = Project(200, 200, "white")
    p.apply({"type": "text", "name": "t", "text": "x", "size": 20, "color": "black"})
    result = p.apply({"type": "layer-intent", "target": "t", "tags": ["optional", "promo"]}, detail="brief")
    assert p.layer("t")["priority"] == "optional" and p.layer("t")["tags"] == ["promo"]
    assert any("priority" in note for note in result["normalized"])
    with pytest.raises(VixlError, match="image and frame"):
        p.apply({"type": "layer-intent", "target": "t", "focal": [0.5, 0.5]})


def test_a_focal_subject_stays_inside_the_crop(tmp_path):
    def poster(focal=None):
        p = Project(1080, 1080, "white")
        p.apply({"type": "add", "path": photo(tmp_path / "wide.png", (1080, 1080), (0.88, 0.5)), "name": "photo",
                 "x": 0, "y": 0, "width": 1080, "height": 1080})
        if focal:
            p.apply({"type": "layer-intent", "target": "photo", "focal": focal})
        return p

    def subject_visible(p):
        pixels = np.asarray(p.render().convert("RGB")).astype(int)
        return bool((np.abs(pixels - RED).sum(axis=2) < 40).any())

    plain = poster()
    report = plain.apply({"type": "adapt-layout", "size": "story"}, detail="brief")["adapt_layout"][0]
    assert not subject_visible(plain)  # centred cover crop: the subject near the right edge is cut off
    assert report["crops"][0]["kept"] is None
    kept = poster([0.88, 0.5])
    report = kept.apply({"type": "adapt-layout", "size": "story"}, detail="brief")["adapt_layout"][0]
    assert subject_visible(kept)
    crop = report["crops"][0]
    assert crop["layer"] == "photo" and crop["kept"] == [0.88, 0.5]
    left, top, right, bottom = crop["lost_px"]
    assert left > 0 and right == 0 and top == bottom == 0  # the crop moved as far right as the image allows
    x, y, w, h = kept.inspect("photo")["resolved_bounds"]
    assert x + w == 1080 and h == 1920


def test_arrangement_options_validate():
    p = Project(400, 300, "white")
    p.apply({"type": "text", "name": "t", "text": "Hello", "size": 30, "color": "black"})
    with pytest.raises(VixlError, match="stack-vertical"):
        p.apply({"type": "adapt-layout", "size": "story", "arrangements": ["stack-vertcal"]})
    with pytest.raises(VixlError, match="one or the other"):
        p.apply({"type": "adapt-layout", "size": "story", "arrangements": ["hero-top"], "recompose": True})
    with pytest.raises(VixlError, match="image"):
        p.apply({"type": "adapt-layout", "size": "story", "arrangements": ["side-by-side", "hero-top"]})
    report = p.apply({"type": "adapt-layout", "size": "story", "arrangements": ["hero-top", "stack-vertical"]},
                     detail="brief")["adapt_layout"][0]
    assert report["arrangement"] == "stack-vertical"
    assert report["candidates"][0] == {"arrangement": "hero-top", "skipped": "needs an image layer"}


def test_adapt_copies_run_the_documents_suites_on_every_variant(tmp_path):
    from vixl.adapt import adapt_copies
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    session.create("post.vixl", 1080, 1080, "white")
    session.apply([{"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 90, "x": 80, "y": 80,
                    "color": "black"},
                   {"type": "suite-set", "name": "legible", "suite": {"rules": [
                       {"id": "headline-size", "kind": "text-fit", "target": "headline", "minimum": 40}]}}])
    result = adapt_copies(session, export_file, ["story", "leaderboard"], directory="out", document="post.vixl")
    story, banner = result["documents"]
    assert story["suites"]["legible"]["status"] == "passed" and story["outcome"]["state"] == "validated"
    assert banner["suites"]["legible"]["status"] == "failed" and banner["outcome"]["state"] == "validation_failed"
    assert story["recomposed"] is False and story["reason"] == "no layout-apply recipe to rebuild"
    quiet = adapt_copies(session, export_file, ["story"], directory="quiet", document="post.vixl", suites=False)
    assert "suites" not in quiet["documents"][0]
    with pytest.raises(VixlError, match="attached"):
        adapt_copies(session, export_file, ["story"], directory="x", document="post.vixl", suites=["missing"])


def test_adapt_copies_accept_arrangements(tmp_path):
    from vixl.adapt import adapt_copies
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    session.create("post.vixl", 1080, 1080, "white")
    session.apply([{"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 90, "x": 80, "y": 80,
                    "color": "black"}])
    result = adapt_copies(session, export_file, ["1920x1080"], directory="out", document="post.vixl",
                          options={"arrangements": ["stack-vertical", "proportional"]})
    item = result["documents"][0]
    assert item["arrangement"] in ("stack-vertical", "proportional") and item["recomposed"] in (True, False)
    assert item["outcome"]["state"] in ("validated", "needs_review")
