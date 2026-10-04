"""Regressions for friction found while building ten designs end to end."""

from pathlib import Path

import pytest

from vixl import Project, VixlError
from vixl.exports import export_icons
from vixl.fonts import import_font
from vixl.resources import create_template

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def text_layers(p):
    return {layer["name"]: layer for layer in p.state["layers"] if layer["type"] == "text"}


def test_palette_apply_sets_role_swatches_and_recolors_templates():
    p = create_template("social-square", {"title": "Spring", "subtitle": "Out Friday"})
    assert text_layers(p)["title"]["color"] == "@ink"
    before = p.render().getpixel((2, 2))
    p.apply({"type": "palette-apply", "name": "ocean"})
    swatches = p.state["swatches"]
    assert {"background", "ink", "accent", "accent-text", "on-accent", "ocean-1"} <= set(swatches)
    assert p.render().getpixel((2, 2)) != before
    p.apply({"type": "shape", "shape": "ellipse", "name": "dot", "width": 20, "height": 20, "fill": "@accent"})
    p.apply({"type": "palette-apply", "name": "sunset", "roles": False})
    assert p.state["swatches"]["accent"] == swatches["accent"]


def test_template_text_follows_document_typography():
    p = create_template("social-square", {"title": "Spring", "subtitle": "Out Friday"})
    assert {t["font_role"] for t in text_layers(p).values()} == {"heading", "body"}
    import_font(p, FONT, "display")
    p.apply({"type": "font-register", "name": "display", "role": "heading"})
    title = text_layers(p)["title"]
    assert title["font"] == p.state["fonts"]["display"]
    assert text_layers(p)["subtitle"]["font"] == "DejaVuSans.ttf"


def test_text_set_changes_font_and_missing_font_lists_registered_fonts():
    p = Project(400, 200)
    import_font(p, FONT, "brand")
    p.apply({"type": "text", "name": "t", "text": "Hello", "size": 40})
    p.apply({"type": "text-set", "target": "t", "font": "brand"})
    assert p.state["layers"][0]["font"] == p.state["fonts"]["brand"]
    with pytest.raises(VixlError) as error:
        p.apply({"type": "text-set", "target": "t", "font": "brand-700"})
    assert error.value.code == "missing_font" and "brand" in str(error.value)
    assert "brand" in error.value.details["allowed"]


def test_print_legibility_is_judged_in_points_not_thumbnails():
    p = Project.sized("poster-18x24")
    p.apply({"type": "text", "name": "detail", "text": "Riverside Park", "size": 60})
    assert not [i for i in p.check()["issues"] if i["check"] == "legibility"]
    p.apply({"type": "text", "name": "tiny", "text": "fine print", "size": 8, "y": 200})
    issues = [i for i in p.check()["issues"] if i["check"] == "legibility"]
    assert [i["layers"] for i in issues] == [["tiny"]] and "pt" in issues[0]["message"]
    assert [i for i in p.check(thumbnail_width=320)["issues"] if i["check"] == "legibility"]


@pytest.mark.parametrize("size", ["poster-18x24", "letter", "instagram-post", "story"])
def test_event_poster_uses_the_page(size):
    p = Project.sized(size)
    p.apply(
        {
            "type": "layout-apply", "name": "event-poster", "seed": 4, "palette": "sunset",
            "title": "Lantern Night Market", "label": "Sat · Oct 18",
            "body": "6 pm – 11 pm\nRiverside Park, Pier 4\nFree entry", "cta": "lanternmarket.org", "caption": "All ages",
        }
    )
    report = p.check()
    assert report["errors"] == 0
    assert not [i for i in report["issues"] if "cut off" in i["message"] or "overlap" in i["message"]]
    bounds = {layer["name"]: p.inspect(layer["name"])["resolved_bounds"] for layer in p.state["layers"]}
    date = bounds["date"]
    assert date[3] < bounds["date-block"][3]  # the date sits on one line inside its block
    details = bounds["detail-3"]
    assert details[1] + details[3] > p.state["canvas"]["height"] * 0.55


def test_render_data_reports_per_row_checks(tmp_path):
    p = Project(400, 200, background="white")
    import_font(p, FONT, "brand")
    p.apply(
        [
            {"type": "variable", "name": "ink", "value": "#111111"},
            {"type": "text", "name": "t", "text": "Readable", "size": 40, "color": "${ink}", "font": "brand"},
        ]
    )
    data = tmp_path / "rows.csv"
    data.write_text("ink\n#111111\n#fefefe\n")
    rows = p.render_data(data, tmp_path / "out")
    assert "check" not in rows[0]
    assert rows[1]["check"]["errors"] >= 1 and rows[1]["check"]["issues"][0]["check"] == "contrast"
    assert "check" not in p.render_data(data, tmp_path / "out2", check=False)[1]


def test_icon_sets_warn_when_enlarging_the_design(tmp_path):
    p = Project.sized("favicon")
    p.apply({"type": "shape", "shape": "ellipse", "width": 400, "height": 400, "fill": "teal"})
    result = export_icons(p, tmp_path / "icons", icon_set="all")
    assert "1024px" in result["warnings"][0]
    assert "warnings" not in export_icons(p, tmp_path / "web", icon_set="web")


def test_cli_inspect_target_and_text_help(tmp_path, monkeypatch, capsys):
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    p = Project(200, 100)
    p.apply({"type": "text", "name": "title", "text": "Hi"})
    p.save("doc.vixl")
    result, _ = dispatch(["-p", "doc.vixl", "inspect", "--target", "title"])
    assert result["name"] == "title"
    with pytest.raises(SystemExit):
        dispatch(["text", "--help"])
    out = capsys.readouterr().out
    assert "vixl text add" in out and "text-set" in out
