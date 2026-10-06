"""hide_if_empty text and auto-layout stacks that reflow and re-centre around hidden or empty members."""

import numpy as np
import pytest

from vixl import Project, VixlError

# The name area of a 1200x900 badge: group "names" sits at (100, 200) and is 1000x400.
AREA = (100, 200, 1000, 400)


def badge(company="Port Ellery Maritime", stack=True, **options):
    """First name, last name and company as stacked text; the last two are optional."""
    p = Project(1200, 900, "white")
    p.apply(
        [
            {"type": "variable", "name": "first", "value": "Sam"},
            {"type": "variable", "name": "last", "value": "Okafor"},
            {"type": "variable", "name": "company", "value": company},
            {"type": "text", "name": "first", "text": "${first}", "size": 120, "color": "black", "x": 100, "y": 200},
            {"type": "text", "name": "last", "text": "${last}", "size": 80, "color": "black", "x": 100, "y": 330,
             "hide_if_empty": True},
            {"type": "text", "name": "company", "text": "${company}", "size": 40, "color": "black", "x": 100,
             "y": 420, "hide_if_empty": True},
        ]
    )
    if stack:
        p.apply(
            [
                {"type": "group", "name": "names", "targets": ["first", "last", "company"]},
                {"type": "stack", "target": "names", "width": AREA[2], "height": AREA[3],
                 **{"gap": 20, "align": "center", "justify": "center", **options}},
            ]
        )
    return p


def bounds(p, name):
    """Resolved bounds: canvas pixels, or pixels inside the group for a group member."""
    return tuple(p.inspect(name)["resolved_bounds"])


def on_canvas(p, name):
    x, y, w, h = bounds(p, name)
    return (x + AREA[0], y + AREA[1], w, h)


def ink(image, box):
    x, y, w, h = box
    return (np.asarray(image.convert("L").crop((x, y, x + w, y + h))) < 128).sum()


# hide_if_empty --------------------------------------------------------------------------------


def test_empty_variable_text_with_hide_if_empty_is_not_drawn():
    p = badge(stack=False)
    box = bounds(p, "company")
    assert ink(p.render(), box) > 0
    p.apply({"type": "variable", "name": "company", "value": ""})
    assert ink(p.render(), box) == 0
    assert p.inspect("company")["visible"] is True  # The layer is kept; it is just collapsed.
    assert p.inspect("company")["collapsed"] is True


def test_variables_passed_at_render_time_hide_empty_text_too():
    p = badge(stack=False)
    box = bounds(p, "company")
    assert ink(p.render(), box) > 0
    assert ink(p.render({"company": ""}), box) == 0
    assert ink(p.render({"company": "   "}), box) == 0  # Whitespace counts as empty.
    assert ink(p.render({"company": "Acme"}), box) > 0


def test_text_with_several_variables_is_empty_only_when_all_are():
    p = Project(300, 100, "white")
    p.apply(
        [
            {"type": "variable", "name": "a", "value": "x"},
            {"type": "variable", "name": "b", "value": "y"},
            {"type": "text", "name": "t", "text": "${a} ${b}", "size": 30, "color": "black", "hide_if_empty": True},
        ]
    )
    box = (0, 0, 300, 100)
    assert ink(p.render({"a": "", "b": ""}), box) == 0
    assert ink(p.render({"a": "x", "b": ""}), box) > 0


def test_text_without_hide_if_empty_is_unchanged_and_the_option_toggles():
    p = Project(300, 100, "white")
    p.apply([{"type": "variable", "name": "a", "value": ""},
             {"type": "text", "name": "t", "text": "${a}", "size": 30, "color": "black"}])
    assert "hide_if_empty" not in p.layer("t") and "collapsed" not in p.inspect("t")
    p.apply({"type": "text-set", "target": "t", "hide_if_empty": True})
    assert p.layer("t")["hide_if_empty"] is True and p.inspect("t")["collapsed"] is True
    p.apply({"type": "text-set", "target": "t", "hide_if_empty": False})
    assert p.layer("t")["hide_if_empty"] is False and "collapsed" not in p.inspect("t")
    p.apply({"type": "text", "target": "t", "hide_if_empty": True})  # In-place edit through text.
    assert p.layer("t")["hide_if_empty"] is True


def test_hidden_empty_text_is_ignored_by_check_and_exports():
    p = badge(stack=False)
    p.apply({"type": "variable", "name": "company", "value": ""})
    assert all("company" not in issue["layers"] for issue in p.check()["issues"])
    assert b"Port Ellery" not in p.export(format="SVG")


def test_hide_if_empty_is_rejected_on_layers_that_cannot_be_empty():
    p = Project(100, 100)
    p.apply({"type": "solid", "name": "s"})
    p.layer("s")["hide_if_empty"] = True
    with pytest.raises(VixlError, match="hide_if_empty"):
        p.apply({"type": "opacity", "target": "s", "value": 0.5})


def test_cli_stack_command(tmp_path, monkeypatch):
    from vixl.cli import dispatch
    from vixl.commands import compile_command

    assert compile_command("stack names --targets a b --gap 20 --align center --justify center --width 100") == {
        "type": "stack", "name": "names", "targets": ["a", "b"], "gap": 20.0, "align": "center",
        "justify": "center", "width": 100}
    assert compile_command("stack names --remove") == {"type": "stack", "target": "names", "remove": True}
    assert compile_command("stack names --no-hide-if-empty")["hide_if_empty"] is False
    monkeypatch.chdir(tmp_path)
    badge().save(tmp_path / "badge.vixl")
    result, _ = dispatch(["-p", "badge.vixl", "stack", "names", "--direction", "horizontal", "--padding", "4"])
    assert result["success"]
    assert Project.load(tmp_path / "badge.vixl").layer("names")["stack"]["direction"] == "horizontal"


def test_cli_text_flags_and_aliases():
    from vixl.commands import compile_command

    assert compile_command("text add ${a} --name t --hide-if-empty")["hide_if_empty"] is True
    assert compile_command("text t --hide-if-empty")["hide_if_empty"] is True
    assert compile_command("text t --no-hide-if-empty")["hide_if_empty"] is False
    p = Project(100, 50)
    p.apply({"type": "variable", "name": "a", "value": "x"})
    result = p.apply({"type": "text", "name": "t", "text": "${a}", "collapse_if_empty": True})
    assert p.layer("t")["hide_if_empty"] is True and any("hide_if_empty" in n for n in result["normalized"])


# stacks ---------------------------------------------------------------------------------------


def test_stack_centres_its_members_in_the_group_box():
    p = badge()
    boxes = [bounds(p, name) for name in ("first", "last", "company")]
    total = sum(b[3] for b in boxes) + 2 * 20
    assert abs(boxes[0][1] - (AREA[3] - total) / 2) <= 1
    assert boxes[1][1] == boxes[0][1] + boxes[0][3] + 20
    assert boxes[2][1] == boxes[1][1] + boxes[1][3] + 20
    for b in boxes:  # Centred on the cross axis.
        assert abs(b[0] + b[2] / 2 - AREA[2] / 2) <= 1
    assert bounds(p, "names") == AREA


def test_empty_member_collapses_and_the_rest_re_centre():
    p = badge()
    full = {name: bounds(p, name) for name in ("first", "last", "company")}
    p.apply({"type": "variable", "name": "company", "value": ""})
    first, last = bounds(p, "first"), bounds(p, "last")
    assert abs(first[1] - (AREA[3] - (first[3] + last[3] + 20)) / 2) <= 1
    assert last[1] == first[1] + first[3] + 20
    assert first[1] > full["first"][1]  # The block moved down to stay centred.
    # Collapsing a member looks exactly like deleting it from the stack.
    q = badge()
    q.apply({"type": "remove", "target": "company"})
    assert np.array_equal(np.asarray(p.render()), np.asarray(q.render()))
    p.apply({"type": "variable", "name": "company", "value": "Port Ellery Maritime"})
    assert {name: bounds(p, name) for name in full} == full


def test_each_export_re_centres_for_its_own_variables():
    p = badge()
    short = p.render({"company": ""})
    full = p.render()
    area = (AREA[0], AREA[1], AREA[0] + AREA[2], AREA[1] + AREA[3])

    def rows(image):
        return np.nonzero((np.asarray(image.convert("L").crop(area)) < 128).any(axis=1))[0]

    top_short, bottom_short = rows(short)[[0, -1]]
    top_full, bottom_full = rows(full)[[0, -1]]
    assert bottom_short < bottom_full and top_short > top_full
    # The ink of both blocks is centred in the area, within font-metric slack.
    assert abs((top_short + bottom_short) / 2 - AREA[3] / 2) < 45
    assert abs((top_full + bottom_full) / 2 - AREA[3] / 2) < 45


def test_hiding_a_member_also_reflows_the_stack():
    p = badge()
    p.apply({"type": "hide", "target": "company"})
    first, last = bounds(p, "first"), bounds(p, "last")
    assert abs(first[1] - (AREA[3] - (first[3] + last[3] + 20)) / 2) <= 1
    p.apply({"type": "show", "target": "company"})
    assert bounds(p, "first")[1] < first[1]


def test_stack_justify_align_and_padding_options():
    p = badge(justify="start", align="start", padding=10)
    first, last = bounds(p, "first"), bounds(p, "last")
    assert (first[0], first[1]) == (10, 10)
    assert last[0] == 10 and last[1] == first[1] + first[3] + 20
    p.apply({"type": "stack", "target": "names", "justify": "end", "align": "end"})
    company = bounds(p, "company")
    assert company[1] + company[3] == AREA[3] - 10 and company[0] + company[2] == AREA[2] - 10


def test_horizontal_stack_reflows_left_to_right():
    p = Project(600, 200, "white")
    p.apply(
        [
            {"type": "variable", "name": "b", "value": "Beta"},
            {"type": "text", "name": "a", "text": "Alpha", "size": 30, "color": "black"},
            {"type": "text", "name": "b", "text": "${b}", "size": 30, "color": "black", "hide_if_empty": True},
            {"type": "text", "name": "c", "text": "Gamma", "size": 30, "color": "black", "x": 400},
            {"type": "stack", "name": "row", "targets": ["a", "b", "c"], "direction": "horizontal", "gap": 10,
             "width": 600, "justify": "center", "align": "center"},
        ]
    )
    a, b, c = (bounds(p, n) for n in "abc")
    assert b[0] == a[0] + a[2] + 10 and c[0] == b[0] + b[2] + 10
    p.apply({"type": "variable", "name": "b", "value": ""})
    a, c = bounds(p, "a"), bounds(p, "c")
    assert c[0] == a[0] + a[2] + 10
    assert abs(a[0] - (600 - (c[0] + c[2]))) <= 1  # Equal space left and right.


def test_nested_stack_with_hide_if_empty_disappears_with_its_members():
    p = Project(400, 400, "white")
    p.apply(
        [
            {"type": "variable", "name": "who", "value": ""},
            {"type": "text", "name": "head", "text": "Title", "size": 40, "color": "black"},
            {"type": "text", "name": "label", "text": "By:", "size": 20, "color": "black", "hide_if_empty": True},
            {"type": "text", "name": "name", "text": "${who}", "size": 20, "color": "black", "hide_if_empty": True},
            {"type": "stack", "name": "credit", "targets": ["label", "name"], "direction": "horizontal", "gap": 8,
             "hide_if_empty": True},
            {"type": "stack", "name": "page", "targets": ["head", "credit"], "gap": 12, "width": 400,
             "height": 400, "justify": "center", "align": "center"},
        ]
    )
    # "By:" is static text, so the credit row still has a visible member.
    assert "collapsed" not in p.inspect("credit")
    head = bounds(p, "head")
    assert head[1] + head[3] + 12 <= bounds(p, "credit")[1]
    p.apply({"type": "text-set", "target": "label", "text": ""})
    assert p.inspect("credit")["collapsed"] is True
    head = bounds(p, "head")
    assert abs(head[1] + head[3] / 2 - 200) <= 1  # With the credit gone, the title is centred alone.


def test_fit_text_frames_keep_their_box_but_collapse_when_empty():
    p = Project(1200, 900, "white")
    p.apply(
        [
            {"type": "variable", "name": "company", "value": ""},
            {"type": "text", "name": "first", "text": "Sam", "size": 100, "color": "black", "align": "center"},
            {"type": "text-layout", "target": "first", "width": 1000, "height": 180, "fit": True},
            {"type": "text", "name": "company", "text": "${company}", "size": 40, "color": "black", "align": "center",
             "hide_if_empty": True},
            {"type": "text-layout", "target": "company", "width": 1000, "height": 72, "fit": True},
            {"type": "stack", "name": "names", "targets": ["first", "company"], "gap": 10, "width": 1200,
             "height": 900, "justify": "center", "align": "center"},
        ]
    )
    first = bounds(p, "first")
    assert first[3] == 180 and abs(first[1] + first[3] / 2 - 450) <= 1
    p.apply({"type": "variable", "name": "company", "value": "Acme"})
    assert bounds(p, "first")[1] == (900 - (180 + 10 + 72)) // 2


def test_stack_box_size_accepts_percentages_and_rejects_scaled_groups():
    p = badge(stack=False)
    p.apply({"type": "stack", "name": "names", "targets": ["first", "last", "company"], "width": "50%",
             "height": "25%"})
    assert bounds(p, "names")[2:] == (600, 225)
    p.apply({"type": "resize", "target": "names", "width": 100, "height": 100})
    with pytest.raises(VixlError, match="scaled"):
        p.apply({"type": "stack", "target": "names", "width": 300})


# template containers ---------------------------------------------------------------------------


def test_container_reflow_closes_the_gap_of_a_hidden_member():
    from vixl.resources import create_template

    p = create_template("modular-card")
    assert p.check_suite("container-layout")["passed"]
    title, body = p.layer("slot-1/title"), p.layer("slot-1/body")
    assert body["y"] > title["y"]
    p.apply({"type": "hide", "target": "slot-1/title"})
    p.apply({"type": "container-reflow", "target": "slot-1"})
    assert p.layer("slot-1/body")["y"] == title["y"] and p.check_suite("container-layout")["passed"]
    p.apply({"type": "show", "target": "slot-1/title"})
    p.apply({"type": "container-reflow", "target": "slot-1"})
    assert p.layer("slot-1/body")["y"] == body["y"] and p.layer("slot-1/title")["y"] == title["y"]


def test_container_placement_skips_empty_hide_if_empty_members(tmp_path):
    from vixl.resources import create_template, register

    p = create_template("modular-card", workspace=tmp_path)
    note = {
        "width": 480, "height": 320, "description": "note",
        "rules": {"layout": "vertical", "padding": 32, "gap": 18, "max_items": 4},
        "defaults": {"title": "Hello", "body": "More"},
        "operations": [
            {"type": "text", "name": "title", "text": "${title}", "size": 32},
            {"type": "text", "name": "mid", "text": "${body}", "size": 18, "hide_if_empty": True},
            {"type": "text", "name": "foot", "text": "end", "size": 18},
        ],
    }
    register("containers", "note", note, workspace=tmp_path)
    p.apply({"type": "container-place", "name": "full", "resource": "note", "x": 480})
    p.apply({"type": "container-place", "name": "short", "resource": "note", "x": 960, "variables": {"body": ""}})
    full, short = (p.layer(f"{name}/foot")["y"] for name in ("full", "short"))
    assert full - short == p.layer("full/mid")["height"] + 18
    assert p.inspect("short/mid")["collapsed"] is True
    assert p.check_suite("container-layout")["passed"]
    p.apply({"type": "text-set", "target": "short/mid", "text": "Filled in"})
    p.apply({"type": "container-reflow", "target": "short"})
    assert p.layer("short/foot")["y"] > short and p.check_suite("container-layout")["passed"]


def test_a_container_that_is_a_stack_follows_its_stack_settings():
    from vixl.resources import create_template

    p = create_template("modular-card")
    p.apply({"type": "stack", "target": "slot-1", "justify": "center", "gap": 18, "padding": 32})
    with pytest.raises(VixlError, match="stack"):
        p.apply({"type": "container-reflow", "target": "slot-1"})
    assert p.check_suite("container-layout")["passed"]  # The stack replaces the container's layout rule.


# editing stacks -------------------------------------------------------------------------------


def test_stack_members_cannot_be_positioned_by_hand():
    p = badge()
    for operation in (
        {"type": "move", "target": "first", "x": 5, "y": 5},
        {"type": "align", "target": "first", "alignment": "left"},
        {"type": "constrain", "target": "first", "constraints": {"left": 10}},
        {"type": "unconstrain", "target": "first"},
        {"type": "distribute", "targets": ["first", "last", "company"], "axis": "vertical"},
    ):
        with pytest.raises(VixlError, match="stack") as caught:
            p.apply(operation)
        assert caught.value.as_dict()["error"] == "stack_managed"
    p.apply({"type": "move", "target": "names", "x": 0, "y": 0})  # The stack itself can move.
    p.apply({"type": "resize", "target": "first", "height": 90})  # Sizes feed the layout.
    assert bounds(p, "first")[3] == 90


def test_removing_a_stack_keeps_the_current_positions():
    p = badge()
    p.apply({"type": "variable", "name": "company", "value": ""})
    before = {name: bounds(p, name) for name in ("first", "last", "company")}
    p.apply({"type": "stack", "target": "names", "remove": True})
    assert "stack" not in p.layer("names")
    assert {name: bounds(p, name) for name in before} == before
    p.apply({"type": "move", "target": "first", "x": 5, "y": 5})  # Free again.
    with pytest.raises(VixlError, match="not a stack"):
        p.apply({"type": "stack", "target": "names", "remove": True})


def test_stack_creates_its_group_and_updates_settings_in_place():
    p = badge(stack=False)
    p.apply({"type": "stack", "name": "names", "targets": ["first", "last", "company"], "gap": 4})
    assert p.layer("names")["stack"] == {"direction": "vertical", "gap": 4, "padding": 0, "align": "start",
                                         "justify": "start"}
    p.apply({"type": "stack", "target": "names", "justify": "center"})
    assert p.layer("names")["stack"]["justify"] == "center" and p.layer("names")["stack"]["gap"] == 4


def test_stack_needs_a_group_and_valid_settings():
    p = badge(stack=False)
    with pytest.raises(VixlError, match="group"):
        p.apply({"type": "stack", "target": "first"})
    with pytest.raises(VixlError, match="name"):
        p.apply({"type": "stack", "targets": ["first", "last"]})
    for bad in ({"direction": "diagonal"}, {"gap": -1}, {"align": "middle"}, {"padding": -2}):
        with pytest.raises(VixlError):
            p.apply({"type": "stack", "name": "s", "targets": ["first", "last"], **bad})
    assert not any(layer["type"] == "group" for layer in p.state["layers"])


def test_stack_survives_save_load_duplicate_and_ungroup(tmp_path):
    p = badge()
    p.apply({"type": "variable", "name": "company", "value": ""})
    p.save(tmp_path / "badge.vixl")
    q = Project.load(tmp_path / "badge.vixl")
    assert bounds(q, "first") == bounds(p, "first")
    q.apply({"type": "duplicate", "target": "names", "name": "names2"})
    assert q.layer("names2")["stack"] == q.layer("names")["stack"]
    expected = {name: on_canvas(q, name) for name in ("first", "last")}
    q.apply({"type": "remove", "target": "names2"})
    q.apply({"type": "ungroup", "target": "names"})
    assert {name: bounds(q, name) for name in expected} == expected  # Ungrouping keeps the stacked positions.


def test_render_data_batch_re_centres_each_row(tmp_path):
    from PIL import Image

    p = badge()
    csv = tmp_path / "rows.csv"
    csv.write_text("first,last,company\nAda,Lovelace,Analytical Engines\nSam,Okafor,\n")
    results = p.render_data(csv, tmp_path / "out", check=False)
    full, short = (Image.open(r["output"]) for r in results)
    assert not np.array_equal(np.asarray(full), np.asarray(short))
    area = (AREA[0], AREA[1], AREA[0] + AREA[2], AREA[1] + AREA[3])

    def spread(image):
        rows = np.nonzero((np.asarray(image.convert("L").crop(area)) < 128).any(axis=1))[0]
        return rows[0], AREA[3] - 1 - rows[-1]

    for image in (full, short):
        above, below = spread(image)
        assert abs(above - below) < 45  # Equal space above and below the name block.
