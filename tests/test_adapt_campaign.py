"""Proportional adapt-layout output that needs no hand fixes (#210): safe zones, uniform decoration,
layers that move together, and a minimum text size."""

import pytest

from vixl import Project
from vixl.errors import VixlError


def campaign():
    """The T02/T09 post: kicker, headline with a coral rule under it, body, date and URL, and a wave band."""
    p = Project(1080, 1080, "#fdf6ec")
    p.apply([
        {"type": "text", "name": "kicker", "text": "SUMMER SERIES", "size": 36, "x": 80, "y": 90, "color": "#1d3557"},
        {"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 110, "x": 80, "y": 330, "color": "#1d3557"},
        {"type": "shape", "shape": "rectangle", "name": "rule", "x": 80, "y": 480, "width": 160, "height": 10,
         "fill": "#ff6b5b"},
        {"type": "text", "name": "body", "text": "Live music by the water every Friday", "size": 40, "x": 80, "y": 520,
         "color": "#1d3557"},
        {"type": "text", "name": "date", "text": "June 6 to August 29", "size": 30, "x": 80, "y": 820, "color": "#1d3557"},
        {"type": "text", "name": "url", "text": "tidepool.example", "size": 26, "x": 80, "y": 870, "color": "#1d3557"},
        {"type": "shape", "shape": "wave", "name": "waves", "x": 0, "y": 960, "width": 1080, "height": 60,
         "stroke": "#3a86ff", "stroke_width": 6},
        {"type": "layer-intent", "target": "url", "tags": ["optional"]},
    ])
    return p


def bounds(p, name):
    return p.inspect(name)["resolved_bounds"]


def test_story_keeps_content_out_of_the_bands_and_the_rule_under_its_headline():
    p = campaign()
    before = {name: bounds(p, name) for name in ("headline", "rule", "waves")}
    p.apply({"type": "adapt-layout", "size": "story"})
    for name in ("kicker", "headline", "rule", "body", "date", "url"):
        x, y, w, h = bounds(p, name)
        assert y >= 250 and y + h <= 1920 - 250, name  # out of the story's keep-out bands
    after = {name: bounds(p, name) for name in ("headline", "rule", "waves")}
    assert after["rule"][0] - after["headline"][0] == before["rule"][0] - before["headline"][0]
    assert after["rule"][1] > after["headline"][1]
    # The wave band is scaled, not stretched: its proportions survive.
    w0, h0 = before["waves"][2:]
    w1, h1 = after["waves"][2:]
    assert w1 >= 1070 and abs(w1 / h1 - w0 / h0) / (w0 / h0) < 0.05


def test_leaderboard_never_sets_text_at_3_px_and_drops_optional_lines():
    p = campaign()
    w0, h0 = bounds(p, "waves")[2:]
    report = p.apply({"type": "adapt-layout", "size": "leaderboard"}, detail="brief")["adapt_layout"][0]
    sizes = [layer["size"] for layer in p.state["layers"] if layer["type"] == "text" and layer["visible"]]
    assert min(sizes) >= 12
    assert report["dropped"] == ["url"] and not p.layer("url")["visible"]
    w2, h2 = bounds(p, "waves")[2:]
    assert abs(w2 / h2 - w0 / h0) / (w0 / h0) < 0.05
    email = campaign()
    email.apply({"type": "adapt-layout", "size": "email-header", "min_text": 14})
    assert min(layer["size"] for layer in email.state["layers"] if layer["type"] == "text" and layer["visible"]) >= 14


def test_layers_that_sit_together_move_together_unless_turned_off():
    p = campaign()
    report = p.apply({"type": "adapt-layout", "width": 1920, "height": 1080}, detail="brief")["adapt_layout"][0]
    assert any({"headline", "rule", "body"} <= set(unit) for unit in report["together"])
    loose = campaign()
    report = loose.apply({"type": "adapt-layout", "width": 1920, "height": 1080, "together": False},
                         detail="brief")["adapt_layout"][0]
    assert "together" not in report


def test_options_validate():
    p = campaign()
    for bad in ({"safe": "yes"}, {"together": 1}, {"min_text": -1}):
        with pytest.raises(VixlError):
            p.apply({"type": "adapt-layout", "size": "story", **bad})
