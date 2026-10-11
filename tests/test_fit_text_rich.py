"""fit-text measures text the way it is drawn and checked (#608): rich spans, tracking and leading."""

import pytest

from vixl import Project
from vixl.automation import text_fits
from vixl.checks import boxed_text_overflow
from vixl.errors import VixlError


def bounds_errors(project):
    return [issue for issue in project.check()["issues"] if issue["check"] == "bounds" and issue["severity"] == "error"]


def fitted(project, name, **box):
    project.apply({"type": "fit-text", "target": name, **box})
    layer = project.layer(name)
    assert boxed_text_overflow(project, layer) is None
    assert not bounds_errors(project)
    return layer


def text(project, name, value, size=57, **extra):
    project.apply({"type": "text", "name": name, "text": value, "size": size, "x": 10, "y": 10, **extra})


def test_tracked_text_fits_at_the_size_the_bounds_check_accepts():
    p = Project(1200, 400, "#000")
    text(p, "sample", "TRACKED DISPLAY TEXT FOR A LYRIC VIDEO")
    p.apply({"type": "text-style", "target": "sample", "tracking": 2.28})
    layer = fitted(p, "sample", width=1070, height=77, minimum=38, maximum=57)
    # The largest size that fits: one size up is cut off.
    assert not text_fits(p, layer, layer["size"] + 1, 1070, 77)


def test_mixed_span_sizes_are_measured():
    p = Project(1200, 600, "#000")
    p.apply({"type": "rich-text", "name": "head", "size": 40, "x": 0, "y": 0,
             "spans": [{"text": "Small then "}, {"text": "HUGE", "size": 120}, {"text": " words"}]})
    # A span's own size stays as it is while the layer size changes, as text-set leaves it.
    fitted(p, "head", width=600, height=170, minimum=10, maximum=40)


def test_wrapped_long_phrase_fits_a_fixed_height_box():
    p = Project(800, 600, "#000")
    text(p, "long", "A LONGER PHRASE THAT HAS TO WRAP ONTO A SECOND LINE IN THIS BOX", size=60,
         line_height=1.4)
    p.apply({"type": "text-style", "target": "long", "tracking": 4})
    fitted(p, "long", width=500, height=150, minimum=8, maximum=60)


def test_empty_text_fits():
    p = Project(400, 200, "#000")
    text(p, "blank", "", size=40)
    fitted(p, "blank", width=300, height=80, minimum=10, maximum=40)


def test_below_minimum_still_fails():
    p = Project(1200, 400, "#000")
    text(p, "sample", "TRACKED DISPLAY TEXT FOR A LYRIC VIDEO")
    p.apply({"type": "text-style", "target": "sample", "tracking": 6})
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "fit-text", "target": "sample", "width": 400, "height": 40, "minimum": 38, "maximum": 57})
    assert caught.value.code == "text_overflow"
