"""Secondary text is judged at the size the piece is really seen: cover art at 120 px, a book cover at a
160 px shop thumbnail, a slide projected, a poster across a room; light weights and faint colours need more."""

import hashlib
import io
from pathlib import Path

import pytest

from vixl import Project
from vixl.checks import contrast_factor, weight_factor
from vixl.sizes import use_size

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def weighted(project, weight):
    """Register DejaVu Sans as a face of ``weight`` and return its font name."""
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    font["OS/2"].usWeightClass = weight
    buffer = io.BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": f"sans-{weight}", "asset": asset})
    return f"sans-{weight}"


def text(project, name, size, y, **extra):
    project.apply({"type": "text", "name": name, "text": "Secondary line", "x": 40, "y": y, "size": size,
                   "color": "#111111", **extra})


def use_findings(project, **options):
    return [x for x in project.check(checks=["legibility", "contrast"], **options)["issues"]
            if x.get("code") == "use-size"]


def canvas(width, height, purpose=None):
    project = Project(width, height, "white")
    if purpose:
        project.state["design_defaults"] = {"purpose": purpose}
    return project


def test_cover_art_is_read_at_120_px():
    project = Project.sized("album-art", "white", design=False)
    text(project, "title", 560, 400)
    text(project, "tagline", 118, 1400)
    [finding] = use_findings(project)
    assert finding["layers"] == ["tagline"] and finding["action"] == "review"
    assert finding["use"]["width"] == 120 and finding["use"]["source"] == "size album-art"
    assert "120 px wide" in finding["message"] and "font size 250+" in finding["message"]
    assert finding["needed_size"] == pytest.approx(250, abs=1)
    assert finding["measured"] == {"actual": 118, "expected": finding["needed_size"], "unit": "px"}


def test_custom_canvas_with_cover_pixels_is_judged_as_cover_art():
    # A 3000 × 3000 social document is podcast art: the pixels name the size even with another purpose.
    project = canvas(3000, 3000, "social")
    text(project, "tagline", 118, 1400)
    assert use_findings(project)[0]["use"]["source"] == "pixels of album-art"
    # A square shared by sizes with different uses (instagram-square, video-square) keeps its purpose.
    assert use_size({"width": 1080, "height": 1080}, "social")["source"] == "purpose social"


def test_book_cover_author_is_read_at_a_160_px_shop_thumbnail():
    project = canvas(1600, 2560, "poster")
    text(project, "author", 58, 2300)
    text(project, "big-author", 120, 2000)
    [finding] = use_findings(project)
    assert finding["layers"] == ["author"] and finding["use"]["width"] == 160
    assert "shop thumbnail" in finding["message"]


def test_slide_text_is_judged_projected():
    project = canvas(1920, 1080, "slides")
    text(project, "event", 26, 100, font=weighted(project, 600))
    text(project, "subtitle", 46, 300)
    [finding] = use_findings(project)
    assert finding["layers"] == ["event"] and "1080 px tall slide" in finding["message"]
    assert finding["weight"] == 600 and finding["needed_size"] == pytest.approx(30.7, abs=0.1)
    # The generic "only matters as a thumbnail" note gives way to the projected reading.
    assert not [x for x in project.check(checks=["legibility"])["issues"] if "thumbnail" in x["message"]]


def test_landscape_diagram_is_a_slide_and_a_tall_one_an_infographic():
    assert use_size({"width": 1920, "height": 1080}, "diagram")["seen"] == "projected"
    assert use_size({"width": 1200, "height": 1600}, "diagram") | {"source": None} == {
        "seen": "thumbnail", "width": 400, "as": "an infographic thumbnail", "source": None}


def test_poster_secondary_text_scales_with_the_sheet_and_weight():
    project = canvas(3508, 4961, "poster")
    text(project, "venue", 96, 4000, font=weighted(project, 400))
    text(project, "tickets", 96, 4200, font=weighted(project, 600))
    text(project, "date", 112, 3800, font=weighted(project, 600))
    [finding] = use_findings(project)
    assert finding["layers"] == ["venue"] and "across a room" in finding["message"]
    assert finding["heavier_weight"] == 600 and "weight of 600+" in finding["message"]
    assert finding["needed_size"] == pytest.approx(0.03 * 3508, abs=0.5)


def test_light_weights_need_more_size():
    assert weight_factor(300) == pytest.approx(1.2) and weight_factor(100) == pytest.approx(1.6)
    assert weight_factor(400) == 1 and weight_factor(700) == pytest.approx(18.66 / 24)
    project = canvas(1920, 1080, "slides")
    text(project, "regular", 40, 100, font=weighted(project, 400))
    text(project, "light", 40, 300, font=weighted(project, 300))
    [finding] = use_findings(project)
    assert finding["layers"] == ["light"] and finding["weight"] == 300 and "weight 300" in finding["message"]


def test_faint_secondary_colour_needs_more_size():
    assert contrast_factor(7) == 1 and contrast_factor(4.6) == 1
    assert contrast_factor(3.0) == pytest.approx(1.24)
    project = canvas(1920, 1080, "slides")
    text(project, "dark", 40, 100)
    text(project, "faint", 40, 300, color="#949494")
    [finding] = use_findings(project)
    assert finding["layers"] == ["faint"] and finding["contrast"] < 4.6 and ":1 contrast" in finding["message"]


def test_decorative_and_waived_text_and_other_sizes_are_respected():
    project = canvas(1920, 1080, "slides")
    text(project, "ghost", 20, 100)
    text(project, "note", 20, 300)
    project.apply([{"type": "layer-intent", "target": "ghost", "decorative": True},
                   {"type": "layer-intent", "target": "note", "waive": ["legibility"]}])
    report = project.check(checks=["legibility"])
    findings = [x for x in report["issues"] if x.get("code") == "use-size"]
    assert [x["layers"] for x in findings] == [["note"]] and findings[0]["action"] == "informational"
    # A phone wallpaper made for a poster purpose is not read across a room; documents have no use size.
    assert use_size({"size": "phone-wallpaper", "width": 1290, "height": 2796}, "poster") is None
    assert use_size({"width": 2550, "height": 3300}, "document") is None


def test_many_small_layers_are_one_finding_and_thumbnail_null_turns_thumbnails_off():
    project = canvas(1200, 1600, "diagram")
    for index in range(5):
        text(project, f"label-{index}", 18, 100 + index * 60)
    [finding] = use_findings(project)
    assert len(finding["layers"]) == 5 and "5 text layers" in finding["message"]
    assert not use_findings(project, thumbnail_width=None)


@pytest.mark.parametrize("size", ["slide", "poster-18x24", "album-art", "instagram-portrait"])
def test_layouts_set_minor_text_at_the_use_size(size, monkeypatch):
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    project = Project.new(size, seed=1, workspace_fonts=False)
    project.apply({"type": "layout-apply", "name": "hero-statement", "seed": 1})
    assert not use_findings(project), [x["message"] for x in use_findings(project)]
    if size == "instagram-portrait":
        return  # Rolled social layouts keep their older thumbnail floor whatever the base size.
    # An explicit base_size wins over the use-size floor.
    small = Project.new(size, seed=1, workspace_fonts=False)
    small.apply({"type": "layout-apply", "name": "hero-statement", "seed": 1, "base_size": 6})
    assert use_findings(small)
