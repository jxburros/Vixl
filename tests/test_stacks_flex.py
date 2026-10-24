"""Flexbox and grid parity for stacks (#653): justify distribution, stretch, grow, wrapping rows and grid stacks."""

import numpy as np
import pytest

from vixl import Project, VixlError
from vixl.commands import compile_command
from vixl.guides import tracks


def boxes(p, *names):
    return [tuple(p.inspect(name)["resolved_bounds"]) for name in names]


def column(**stack):
    """Three 100x50 rectangles stacked in a 400x1000 box."""
    p = Project(600, 1200, "white")
    p.apply([*({"type": "shape", "shape": "rectangle", "name": name, "width": 100, "height": 50, "fill": color}
               for name, color in (("a", "red"), ("b", "green"), ("c", "blue"))),
             {"type": "stack", "name": "col", "targets": ["a", "b", "c"], "width": 400, "height": 1000, "gap": 10,
              **stack}])
    return p


def test_space_between_puts_the_first_and_last_member_at_the_ends():
    p = column(justify="space-between")
    a, b, c = boxes(p, "a", "b", "c")
    assert a[1] == 0 and c[1] + c[3] == 1000
    assert b[1] - (a[1] + a[3]) == c[1] - (b[1] + b[3])  # the free space is shared equally


def test_space_around_and_space_evenly_share_the_free_space_like_css():
    free = 1000 - 150 - 20  # the box minus the members and the two gaps
    a, b, c = boxes(column(justify="space-evenly"), "a", "b", "c")
    assert abs(a[1] - free / 4) <= 1 and abs(1000 - (c[1] + c[3]) - free / 4) <= 1
    a, b, c = boxes(column(justify="space-around"), "a", "b", "c")
    assert abs(a[1] - free / 6) <= 1 and abs((b[1] - a[1] - a[3] - 10) - free / 3) <= 1
    # A single member: space-between packs it at the start, the others centre it.
    p = Project(300, 300, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 100, "height": 50},
             {"type": "stack", "name": "one", "targets": ["a"], "width": 300, "height": 300, "justify": "space-between"}])
    assert boxes(p, "a")[0][1] == 0
    p.apply({"type": "stack", "target": "one", "justify": "space-evenly"})
    assert boxes(p, "a")[0][1] == 125


def test_stretch_fills_the_box_across_and_text_wraps_to_its_width():
    p = column(align="stretch")
    assert [box[2] for box in boxes(p, "a", "b", "c")] == [400, 400, 400]
    assert p.layer("a")["width"] == 100  # the stored member keeps its size: the stack sizes the resolved copy
    t = Project(800, 600, "white")
    t.apply([{"type": "text", "name": "copy", "text": "A fairly long line of text that will need to wrap", "size": 30,
              "color": "black"},
             {"type": "shape", "shape": "rectangle", "name": "rule", "width": 100, "height": 10, "fill": "red"},
             {"type": "stack", "name": "s", "targets": ["copy", "rule"], "width": 300, "height": 500, "align": "stretch",
              "gap": 12}])
    copy, rule = boxes(t, "copy", "rule")
    assert copy[2] == 300 and copy[3] > 60  # wrapped onto several lines
    assert rule == (0, copy[3] + 12, 300, 10)
    ink = np.asarray(t.render().convert("L")) < 128
    assert ink[:, 300:].sum() == 0 and ink[:, :300].sum() > 0  # nothing drawn past the box


def test_stretch_reaches_every_export(tmp_path):
    p = column(align="stretch")
    p.export(tmp_path / "col.svg")
    svg = (tmp_path / "col.svg").read_text()
    assert svg.count('width="400"') >= 3


def test_grow_shares_the_free_space_by_weight_and_keeps_photos_undistorted():
    p = column(grow={"a": 1, "c": 2})
    a, b, c = boxes(p, "a", "b", "c")
    free = 1000 - 150 - 20
    assert abs(a[3] - (50 + free / 3)) <= 1 and abs(c[3] - (50 + 2 * free / 3)) <= 1 and b[3] == 50
    assert c[1] + c[3] == 1000
    assert p.layer("a").get("stack_grow") == 1
    p.apply({"type": "stack", "target": "col", "grow": {"a": 0, "c": 0}})
    assert "stack_grow" not in p.layer("a") and boxes(p, "c")[0][3] == 50
    # A group cannot grow without scaling its contents, so it keeps its size and the space stays after it.
    g = Project(600, 1200, "white")
    g.apply([{"type": "shape", "shape": "rectangle", "name": "inner", "width": 100, "height": 50},
             {"type": "group", "name": "pair", "targets": ["inner"]},
             {"type": "shape", "shape": "rectangle", "name": "last", "width": 100, "height": 50},
             {"type": "stack", "name": "col", "targets": ["pair", "last"], "width": 400, "height": 1000, "gap": 10,
              "grow": {"pair": 1}}])
    pair, last = boxes(g, "pair", "last")
    assert pair[3] == 50 and last[1] + last[3] == 1000


def test_grow_in_a_row_widens_text_and_shapes():
    p = Project(1000, 200, "white")
    p.apply([{"type": "text", "name": "label", "text": "Total", "size": 30, "color": "black"},
             {"type": "shape", "shape": "rectangle", "name": "bar", "width": 50, "height": 20, "fill": "red"},
             {"type": "text", "name": "price", "text": "$12", "size": 30, "color": "black"},
             {"type": "stack", "name": "row", "targets": ["label", "bar", "price"], "direction": "horizontal",
              "width": 800, "height": 60, "gap": 10, "grow": {"bar": 1}, "align": "center"}])
    label, bar, price = boxes(p, "label", "bar", "price")
    assert price[0] + price[2] == 800 and bar[0] == label[0] + label[2] + 10
    assert bar[2] == price[0] - 10 - bar[0]


def test_wrap_breaks_a_row_and_hugs_the_rows():
    p = Project(600, 600, "white")
    names = [f"tag{i}" for i in range(5)]
    p.apply([*({"type": "shape", "shape": "rectangle", "name": name, "width": 100, "height": 40} for name in names),
             {"type": "stack", "name": "tags", "targets": names, "direction": "horizontal", "wrap": True,
              "width": 350, "height": 100, "gap": 10, "row_gap": 20, "size": "hug"}])
    found = boxes(p, *names)
    assert [box[1] for box in found] == [0, 0, 0, 60, 60]  # two rows: three that fit in 350 px, then two
    assert [box[0] for box in found[:3]] == [0, 110, 220]
    assert tuple(p.inspect("tags")["resolved_bounds"][2:]) == (350, 100)  # width kept, height hugs the rows
    p.apply({"type": "stack", "target": "tags", "justify": "center"})
    assert boxes(p, "tag3")[0][0] == (350 - 210) // 2  # each row is justified on its own


def test_grid_places_members_in_fr_columns_with_spans_and_wraps_text_to_its_cell():
    p = Project(800, 800, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "hero", "width": 100, "height": 80, "fill": "red"},
             {"type": "shape", "shape": "rectangle", "name": "left", "width": 60, "height": 50, "fill": "green"},
             {"type": "text", "name": "right", "text": "Words that are far too wide for one grid cell", "size": 24,
              "color": "black"},
             {"type": "stack", "name": "grid", "targets": ["hero", "left", "right"], "direction": "grid",
              "columns": ["1fr", "2fr"], "width": 310, "height": 600, "gap": 10, "row_gap": 20,
              "span": {"hero": 2}}])
    hero, left, right = boxes(p, "hero", "left", "right")
    assert hero[:2] == (0, 0) and p.layer("hero")["stack_span"] == 2
    assert left[:2] == (0, 100) and right[:2] == (110, 100)  # 1fr = 100 px, 2fr = 200 px after the 10 px gap
    assert right[2] <= 200 and right[3] > 30  # wrapped at the cell's width
    p.apply({"type": "stack", "target": "grid", "align": "stretch"})
    hero, left, right = boxes(p, "hero", "left", "right")
    assert hero[2] == 310 and left[2] == 100 and left[3] == right[3]  # filled their cells and the row height
    p.apply({"type": "stack", "target": "grid", "columns": 3, "span": {"hero": 1}, "align": "start",
             "justify": "end", "size": "hug", "width": 320})
    hero, left, right = boxes(p, "hero", "left", "right")
    assert {hero[1], left[1], right[1]} == {0}  # three equal 100 px columns on one row
    assert left[0] + left[2] == 210  # justify end: on the right edge of its cell
    assert p.inspect("grid")["resolved_bounds"][3] == max(hero[3], left[3], right[3])


def test_tracks_split_columns_like_css_grid_and_column_guides_are_unchanged():
    assert tracks(310, ["1fr", "2fr"], 10) == [(0.0, 100.0), (110.0, 200.0)]
    assert tracks(500, [100, "1fr"], 20) == [(0.0, 100.0), (120.0, 380.0)]
    assert tracks(320, 3, 10) == [(0, 100.0), (110.0, 100.0), (220.0, 100.0)]
    p = Project(1000, 500, "white")
    p.apply({"type": "grid", "name": "cols", "kind": "columns", "columns": 4, "margin": 40, "gutter": 20})
    guides = p.state["guides"]
    assert guides["cols-x1-start"]["position"] == 40 and guides["cols-x4-end"]["position"] == 960
    assert guides["cols-x2-start"]["position"] == 40 + (920 - 60) / 4 + 20


def test_remove_keeps_stretched_and_grown_sizes():
    p = column(align="stretch", grow={"b": 1})
    before = boxes(p, "a", "b", "c")
    p.apply({"type": "stack", "target": "col", "remove": True})
    assert boxes(p, "a", "b", "c") == before
    assert p.layer("b")["width"] == 400 and "stack_grow" not in p.layer("b")


def test_invalid_flex_and_grid_settings_say_what_to_change():
    p = column()
    for bad, words in (({"wrap": True}, "horizontal"), ({"columns": 3}, "grid"),
                       ({"direction": "grid"}, "columns"),
                       ({"direction": "grid", "columns": 2, "justify": "space-between"}, "cells"),
                       ({"direction": "grid", "columns": ["1fr", "wide"]}, "fr"),
                       ({"grow": {"canvas-art": 1}}, "canvas-art"), ({"span": {"a": 0}}, "span")):
        with pytest.raises(VixlError, match=words):
            p.apply({"type": "stack", "target": "col", **bad})
    p.apply({"type": "shape", "shape": "rectangle", "name": "loose", "width": 10, "height": 10})
    with pytest.raises(VixlError, match="not a member"):
        p.apply({"type": "stack", "target": "col", "grow": {"loose": 1}})


def test_css_property_names_and_values_are_accepted():
    p = column()
    result = p.apply({"type": "stack", "target": "col", "flex_direction": "row", "justify_content": "flex-end",
                      "align_items": "middle", "flex_wrap": "wrap", "flex_grow": {"a": 1}}, detail="brief")
    stack = p.layer("col")["stack"]
    assert (stack["direction"], stack["justify"], stack["align"], stack["wrap"]) == ("horizontal", "end", "center", True)
    assert p.layer("a")["stack_grow"] == 1
    assert any("justify_content" in note for note in result["normalized"])
    p.apply({"type": "stack", "target": "col", "direction": "grid", "grid_template_columns": ["1fr", "1fr"]})
    assert p.layer("col")["stack"]["columns"] == ["1fr", "1fr"] and "wrap" not in p.layer("col")["stack"]


def test_cli_flags_compile_to_the_stack_operation():
    op = compile_command("stack row --direction grid --columns 1fr,2fr,240 --row-gap 2u --span hero=2 "
                         "--grow body=1.5 --justify end --align stretch --no-wrap")
    assert op == {"type": "stack", "target": "row", "direction": "grid", "columns": ["1fr", "2fr", 240.0],
                  "row_gap": "2u", "span": {"hero": 2}, "grow": {"body": 1.5}, "justify": "end", "align": "stretch",
                  "wrap": False}
    assert compile_command("stack row --columns 3")["columns"] == 3


def test_a_space_between_column_on_a_tall_canvas_passes_the_composition_check():
    def poster(justify):
        p = Project(1080, 1920, "#fdf6ec")
        p.apply([
            {"type": "text", "name": "kicker", "text": "SUMMER SERIES", "size": 40, "color": "#1d3557"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "picture", "width": 920, "height": 760,
             "fill": "#3a86ff", "radius": 24},
            {"type": "text", "name": "headline", "text": "Tide Pool Nights", "size": 110, "color": "#1d3557"},
            {"type": "text", "name": "date", "text": "Fridays in June at the harbour", "size": 48, "color": "#1d3557"},
            {"type": "text", "name": "url", "text": "tidepool.example", "size": 40, "color": "#1d3557"},
            {"type": "stack", "name": "title", "targets": ["headline", "date"], "size": "hug", "gap": 24},
            {"type": "stack", "name": "column", "targets": ["kicker", "picture", "title", "url"],
             "width": 920, "height": 1600, "justify": justify},
            {"type": "move", "target": "column", "x": 80, "y": 160},
        ])
        return p

    packed = poster("start").check(checks=["composition"])
    assert any(item["rule"] == "composition.dead_band" for item in packed["issues"])
    spread = poster("space-between")
    assert spread.check(checks=["composition"])["issues"] == []
    url = spread.inspect("url")["resolved_bounds"]
    assert url[1] + url[3] == 1600  # the last member sits on the bottom of the box
