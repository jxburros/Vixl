"""Every built-in layout passes the checks at its recommended sizes with its own example copy (#764).

Each layout × recommended size × seed is built in a fresh document with the layout's example copy (stub images
for image slots) on two stable bundled fonts, and must give no fix finding and no composition review finding.
Known exceptions are listed in ``EXCEPTIONS`` with a reason and an issue; keep that list short."""
import hashlib
from pathlib import Path

import pytest

from vixl import Project
from vixl.layouts import IMAGE_LAYOUTS, LAYOUTS, MULTI_IMAGE_LAYOUTS, describe, recommended_sizes
from vixl.sizes import SIZES

SEEDS = (1, 2, 3)
FONTS = Path(__file__).resolve().parents[1] / "src" / "vixl" / "data"

# (layout, size): "reason, #issue". Issue numbers refer to jxburros/vixl.
EXCEPTIONS = {
    ("rule-of-thirds", "instagram-post"): "dead band under the copy below the focal point; subtitle crosses it, #803",
    ("rule-of-thirds", "instagram-story"): "small band between the copy blocks, #803",
    ("rule-of-thirds", "poster-18x24"): "bands between the focal image and the edge and between blocks, #803",
    ("rule-of-thirds", "photo-5x7"): "bands between the focal image and the edge and between blocks, #803",
    ("golden-section", "letter"): "bottom band in the minor section, #804",
    ("golden-section", "instagram-story"): "bottom band in the minor section, #804",
    ("z-pattern", "instagram-post"): "band between the headline and the body, #805",
    ("z-pattern", "og-image"): "band between the headline and the body, #805",
    ("z-pattern", "web-banner"): "body overflows its box; band between the headline and the body, #805",
    ("z-pattern", "instagram-story"): "band between the headline and the body, #805",
    ("split-screen", "instagram-story"): "edge bands in the text half; minor text under the thumbnail minimum, #806",
    ("split-screen", "instagram-post"): "headline under 1.6 times the body at seed 2, #806",
    ("banner", "x-header"): "headline and subtitle weigh the same, #807",
    ("banner", "email-banner"): "headline and subtitle weigh the same at seed 2, #807",
    ("photo-caption", "ebook-cover"): "headline and subtitle weigh the same at seed 2, #807",
    ("editorial-grid", "letter"): "short example body leaves the lower third empty, #808",
    ("editorial-grid", "poster-18x24"): "short example body leaves a band at the foot, #808",
    ("emblem", "sticker"): "tagline and initials drift from the badge axis, #809",
    ("price-list", "menu"): "centred title drifts from the subtitle at seed 2, #809",
    ("price-list", "letter"): "centred title drifts from the subtitle at seed 2, #809",
    ("big-number", "slide"): "centred body drifts from the label and subtitle, #809",
    ("minimal-mark", "poster-18x24"): "headline under 1.6 times the body at seed 2, #810",
    ("minimal-mark", "instagram-post"): "headline under 1.6 times the body at seed 2, #810",
    ("minimal-mark", "instagram-story"): "headline under 1.6 times the body at seed 2, #810",
    ("slide-content", "slide"): "band between the last point and the footer, #811",
    ("asymmetric-balance", "og-image"): "top edge band over the copy, #812",
    ("asymmetric-balance", "instagram-post"): "top edge band over the copy at seed 2, #812",
    ("hero-statement", "instagram-post"): "band inside the block accent at seed 3, #812",
    ("photo-caption", "instagram-story"): "the scrim is taller than its copy, #813",
    ("business-card", "business-card"): "bottom band at seed 1, #814",
    ("typographic-poster", "ebook-cover"): "caption overflows its box at seed 2, #814",
}

CASES = [(name, size) for name in LAYOUTS for size in recommended_sizes(name)]


def _register(project, name, filename):
    data = (FONTS / filename).read_bytes()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": name, "asset": asset})


def build(name, size, seed):
    from PIL import Image

    from vixl.assets import add_image

    project = Project.sized(size, seed=seed)
    _register(project, "quality-body", "DejaVuSans.ttf")
    _register(project, "quality-heading", "NotoSans-Regular.ttf")
    copy = {key: slot["example"] for key, slot in describe(name)["slots"].items() if "example" in slot}
    op = {"type": "layout-apply", "name": name, "seed": seed, "font": "quality-body", "display_font": "quality-heading",
          **copy}
    if name in IMAGE_LAYOUTS:
        op["image"] = add_image(project, Image.new("RGBA", (400, 300), "#88aa66"))
    if name in MULTI_IMAGE_LAYOUTS:
        panels = 2 if name == "meme-comparison" else 4
        op["images"] = [add_image(project, Image.new("RGBA", (400, 300), colour))
                        for colour in ("#88aa66", "#aa6688", "#6688aa", "#aaaa66")[:panels]]
    project.apply(op)
    return project


def findings(project):
    report = project.check()
    return [f"{issue['check']}.{issue.get('code')}: {issue['message'][:90]}" for issue in report["issues"]
            if issue.get("action") == "fix" or issue["severity"] == "error" or issue["check"] == "composition"]


def test_every_layout_recommends_named_sizes_in_its_description():
    for name in LAYOUTS:
        sizes = recommended_sizes(name)
        assert sizes and all(size in SIZES for size in sizes), name
        assert describe(name)["sizes"] == sizes


def test_exceptions_are_short_and_explained():
    assert len(EXCEPTIONS) <= 35  # 71 of 204 pairs failed before #764; keep this list shrinking
    for key, reason in EXCEPTIONS.items():
        assert key in CASES and "#" in reason, key


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name,size", CASES)
def test_layout_passes_the_checks_at_its_recommended_size(name, size, seed):
    if (name, size) in EXCEPTIONS:
        pytest.xfail(EXCEPTIONS[(name, size)])
    project = build(name, size, seed)
    assert findings(project) == []
