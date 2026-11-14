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
    assert len(EXCEPTIONS) <= 0  # 71 of 204 pairs failed before #764; #803-#814 cleared the list: keep it empty
    for key, reason in EXCEPTIONS.items():
        assert key in CASES and "#" in reason, key


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name,size", CASES)
def test_layout_passes_the_checks_at_its_recommended_size(name, size, seed):
    if (name, size) in EXCEPTIONS:
        pytest.xfail(EXCEPTIONS[(name, size)])
    project = build(name, size, seed)
    assert findings(project) == []
