"""vixl_check must not wrongly pass (#195, #196, #197) nor cry wolf (#219, #250)."""

import pytest

from vixl import Project


def contrast_issues(result):
    return [i for i in result["issues"] if i["check"] == "contrast"]


@pytest.mark.parametrize("x", [100, 100.5, 101, 101.5])
@pytest.mark.parametrize("text", ["Hi", "Hello", "Odd one"])
def test_contrast_measures_text_at_fractional_positions(x, text):
    p = Project(400, 200, "white")
    p.apply([{"type": "text", "name": "t", "text": text, "size": 30, "x": x, "y": 60.5, "color": "#eeeeee"}])
    result = p.check(checks=["contrast"])
    issues = contrast_issues(result)
    assert issues and all("Could not measure" not in i["message"] for i in issues)
    assert issues[0]["contrast"] < 2 and not result["passed"]


def test_contrast_passes_cleanly_at_half_pixel():
    p = Project(401, 200, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hello", "size": 30, "x": "center", "y": 60, "color": "#111111"}])
    assert p.check(checks=["contrast"])["issues"] == []


def test_unmeasurable_contrast_is_an_error(monkeypatch):
    from vixl import measure as m

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(m, "top_level_contrast", boom)
    monkeypatch.setattr(m, "measure", boom)
    p = Project(400, 200, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hello", "size": 30, "x": 10, "y": 10, "color": "#111111"}])
    issues = contrast_issues(p.check(checks=["contrast"]))
    assert issues and issues[0]["severity"] == "error"


def scene():
    p = Project(800, 600, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "sky", "x": 0, "y": 0, "width": 800, "height": 600, "fill": "#88aacc"},
        {"type": "shape", "shape": "path", "name": "tower", "path": "M100 100 L200 100 L150 400 Z", "x": 0, "y": 0,
         "width": 800, "height": 600, "fill": "#222222"},
    ])
    return p


def test_full_canvas_path_is_checked_and_counted():  # #196
    p = scene()
    p.apply({"type": "text", "name": "caption", "text": "Overlapping the tower", "size": 40, "x": 60, "y": 120, "color": "#ffffff"})
    result = p.check()
    assert result["checked"]["layers_total"] == 3 and result["checked"]["layers_checked"] == 2
    assert any(i["check"] == "overlap" and "tower" in i["layers"] for i in result["issues"])


def test_full_canvas_path_running_off_canvas_is_reported():  # #196
    p = scene()
    p.apply({"type": "shape", "shape": "path", "name": "wing", "path": "M700 100 L900 100 L800 250 Z", "x": 0, "y": 0,
             "width": 800, "height": 600, "fill": "#222222"})
    assert any(i["check"] == "bounds" and "wing" in i["layers"] for i in p.check()["issues"])


def test_role_background_is_skipped_explicitly():  # #196
    p = scene()
    p.apply({"type": "layer-intent", "target": "tower", "role": "background"})
    assert p.check()["checked"]["layers_checked"] == 0


def test_moved_path_with_off_canvas_box_but_visible_geometry_is_fine():  # #197
    p = Project(800, 600, "white")
    p.apply({"type": "shape", "shape": "path", "name": "boat", "path": "M1100 100 L1300 100 L1200 250 Z", "x": -700,
             "y": 0, "width": 2400, "height": 1600, "fill": "#222222"})
    assert [i for i in p.check()["issues"] if i["check"] == "bounds"] == []


def test_hill_ellipse_bleed_is_informational_but_text_is_not():  # #250
    p = Project(800, 600, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "hill", "x": -200, "y": 400, "width": 1200, "height": 500, "fill": "#22aa77"},
        {"type": "text", "name": "title", "text": "Hello", "size": 40, "x": 700, "y": 100, "color": "#000000"},
    ])
    bounds = [i for i in p.check(checks=["bounds"])["issues"] if i["check"] == "bounds"]
    hill = [i for i in bounds if i["layers"] == ["hill"]]
    assert all(i["severity"] == "info" for i in hill)
    assert any(i["layers"] == ["title"] and i["severity"] == "error" for i in bounds)


def test_bleed_is_not_an_advisory_warning():  # #250
    p = Project(800, 600, "white")
    result = p.apply({"type": "shape", "shape": "ellipse", "name": "hill", "x": -200, "y": 400, "width": 1200,
                      "height": 500, "fill": "#22aa77"})
    assert "cut off" not in str(result)


def test_canvas_safe_area_is_checked_by_default():  # #211
    p = Project(1080, 1920, "white")
    p.apply({"type": "canvas", "size": "story"})
    p.apply([{"type": "text", "name": "top", "text": "Hi", "size": 60, "x": 100, "y": 100, "color": "#000000"},
             {"type": "text", "name": "side", "text": "Hi", "size": 60, "x": 100, "y": 900, "color": "#000000"}])
    flagged = {n for i in p.check(checks=["safe_area"])["issues"] for n in i["layers"]}
    assert flagged == {"top"}  # the 250 px bands are top and bottom only


def test_us_letter_text_017_in_from_edge_is_flagged():  # #211
    p = Project(100, 100, "white")
    p.apply({"type": "canvas", "size": "letter"})
    px = round(0.17 * 300)
    p.apply({"type": "text", "name": "footer", "text": "Footer", "size": 30, "x": 600, "y": 3300 - px - 40, "color": "#000000"})
    p.apply({"type": "text", "name": "ok", "text": "Fine", "size": 30, "x": 600, "y": 1000, "color": "#000000"})
    flagged = {n for i in p.check(checks=["safe_area"])["issues"] for n in i["layers"]}
    assert flagged == {"footer"}


def test_print_size_presets_default_to_a_quarter_inch_safe_margin():  # #211
    from vixl import sizes

    assert sizes.resolve("letter")["safe"] == 75 and sizes.resolve("a4")["safe"] == 71


def test_legibility_thumbnail_test_is_review_outside_thumbnail_pieces():  # #219
    p = Project(1200, 1800, "white")
    p.apply({"type": "text", "name": "t", "text": "Small label", "size": 20, "x": 40, "y": 40, "color": "#000000"})
    issues = [i for i in p.check(checks=["legibility"])["issues"] if i["check"] == "legibility"]
    assert issues and all(i["action"] != "fix" for i in issues)


def test_legibility_thumbnail_test_still_fails_on_social_posts_and_can_be_disabled():  # #219
    p = Project(100, 100, "white")
    p.apply({"type": "canvas", "size": "instagram-post"})
    p.apply({"type": "text", "name": "t", "text": "Small label", "size": 14, "x": 100, "y": 400, "color": "#000000"})
    issues = [i for i in p.check(checks=["legibility"])["issues"] if i["check"] == "legibility"]
    assert issues and all(i["action"] == "fix" for i in issues)
    assert p.check(checks=["legibility"], thumbnail_width=None)["issues"] == []


def test_stroked_text_covering_a_neighbours_descender_is_an_overlap():  # #249
    p = Project(900, 400, "white")
    p.apply({"type": "text", "name": "greeting", "text": "gggg", "size": 100, "x": 50, "y": 20, "color": "#000000"})
    box = p.layer("greeting")
    p.apply({"type": "text", "name": "name", "text": "Daddy", "size": 100, "x": 50, "y": box["y"] + box["height"] + 2,
             "color": "#ffffff"})
    assert not [i for i in p.check(checks=["overlap"])["issues"] if i["check"] == "overlap"]
    p.apply({"type": "layer-style", "target": "name", "name": "stroke", "settings": {"color": "#ffffff", "width": 24}})
    found = [i for i in p.check(checks=["overlap"])["issues"] if i["check"] == "overlap"]
    assert found and set(found[0]["layers"]) == {"greeting", "name"}


def chart(colors, **options):
    p = Project(900, 560, "#ffffff")
    series = [{"name": n, "values": v, "color": c} for (n, v), c in zip((("Wins", [3, 4, 5]), ("Losses", [4, 3, 2])), colors)]
    p.apply({"type": "chart", "name": "Record", "kind": "bar", "categories": ["A", "B", "C"], "series": series, **options})
    return p


def test_chart_series_red_and_green_are_flagged_under_deuteranopia():  # #230
    issues = [i for i in chart(["#d62728", "#2ca02c"]).check(checks=["color_vision"])["issues"] if "series" in i["message"]]
    assert any(i["vision"] == "deuteranopia" for i in issues)


def test_chart_with_distinct_series_or_marked_safe_is_not_flagged():  # #230
    assert not [i for i in chart(["#0072b2", "#d55e00"]).check(checks=["color_vision"])["issues"] if "series" in i["message"]]
    p = chart(["#d62728", "#2ca02c"])
    p.apply({"type": "layer-intent", "target": "Record", "color_vision_safe": True})
    assert not [i for i in p.check(checks=["color_vision"])["issues"] if "series" in i["message"]]


def test_moved_path_with_box_partly_off_canvas_but_visible_geometry_is_fine():  # #197
    p = Project(800, 600, "white")
    p.apply([{"type": "text", "name": "t", "text": "x", "size": 20, "x": 10, "y": 10, "color": "#000000"},
             {"type": "shape", "shape": "path", "name": "boat", "path": "M300 100 L500 100 L400 250 Z", "x": -200,
              "y": 0, "width": 700, "height": 400, "fill": "#222222"}])
    assert [i for i in p.check()["issues"] if i["check"] == "bounds"] == []
    p.apply({"type": "move", "target": "boat", "x": -450})
    assert [i for i in p.check()["issues"] if i["check"] == "bounds" and "boat" in i["layers"]]
