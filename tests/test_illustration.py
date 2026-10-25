"""The house illustration finish (#427): flat vector with thin ink part lines, a hard offset shadow, a slight wobble and
now and then a double or triple line. Both halves read ``craft.illustration`` through ``craft.illustration_style``: new
organic forms and ``object-plan`` scaffolds in a document that has a house style."""

import random

import pytest

from vixl import Project, craft, house_style, objects
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.object_plan import plan
from vixl.workflows import dispatch

SEEDS = ("person", "dog", "cat", "bird", "fish", "tree", "flower", "leaf", "mushroom", "guitar", "car", "house", "cup",
         "rock", "cloud")


def house(seed=3, size=400):
    return Project(size, size, seed=seed, workspace_fonts=False)


def group_layers(p, name):
    group = p.layer(name)
    return group, [layer for layer in p.state["layers"] if layer.get("parent") == group["id"]]


def line_seed(wanted, preset_box=(0, 0, 360, 360)):
    """The first organic seed whose illustration draws extra lines (or does not, with ``wanted`` false)."""
    for seed in range(400):
        style = craft.illustration_style(house(), preset_box, random.Random(f"illustration/{seed}"))
        if bool(style["strokes"]) == wanted:
            return seed
    raise AssertionError("no such seed")


# --- the data and the helper ------------------------------------------------------------------------------------


def test_the_illustration_finish_is_house_style_data():
    rule = house_style.illustration()
    assert rule["outline"]["policy"] == "parts" and rule["outline"]["width_share"] == 0.012
    assert rule["shadow"] == {"kind": "offset", "distance_share": 0.03, "angle_from": "light", "opacity": 0.35}
    assert rule["light"] == "top-left" and rule["irregular"]["strength"] == "subtle"
    assert rule["extra_lines"]["probability"] == 0.15 and rule["extra_lines"]["count"] == [1, 2]
    assert house_style.craft()["illustration"] == rule


def test_illustration_style_gives_the_stroke_width_a_hard_shadow_cast_from_the_light_and_no_lines_by_default():
    p = house()
    style = craft.illustration_style(p, [10, 20, 300, 400], random.Random(line_seed(False)))
    assert style["policy"] == "parts" and style["stroke"] == "@ink"
    assert style["stroke_width"] == pytest.approx(0.012 * 400)  # the larger side, 1.2%
    # Light from the top left: the shadow falls to the bottom right, 3% of the larger side, blur 0, in ink.
    assert style["shadow"] == {"color": "@ink", "dx": 12.0, "dy": 12.0, "blur": 0, "opacity": 0.35}
    assert style["irregular"] == {"strength": "subtle", "only": ["wobble"]} and style["strokes"] == []
    assert style["wobble_element"] == pytest.approx(12 * style["stroke_width"])


def test_extra_lines_appear_about_one_form_in_seven_and_are_one_or_two_thin_gaps():
    p, box = house(), [0, 0, 400, 400]
    found = [craft.illustration_style(p, box, random.Random(f"illustration/{seed}"))["strokes"] for seed in range(200)]
    with_lines = [lines for lines in found if lines]
    assert 0.09 <= len(with_lines) / 200 <= 0.21  # 15%
    assert {len(lines) for lines in with_lines} == {1, 2}
    width = craft.illustration_style(p, box, random.Random(0))["stroke_width"]
    for line in with_lines[0]:
        assert line["gap"] == pytest.approx(0.006 * 400) and line["width"] == pytest.approx(width * 0.5)
    same = craft.illustration_style(p, box, random.Random("illustration/1"))
    assert same == craft.illustration_style(p, box, random.Random("illustration/1"))


def test_a_document_has_a_house_style_unless_it_is_plain_or_the_house_style_is_off():
    assert craft.illustration_on(house()) is True
    assert craft.illustration_on(Project(200, 200)) is False  # a bare canvas has no design defaults
    assert craft.illustration_on(Project(200, 200, house_style="off")) is False
    assert craft.illustration_on(house(), "plain") is False and craft.illustration_on(Project(200, 200), "house") is True


# --- organic ----------------------------------------------------------------------------------------------------


def flower(p, **fields):
    p.apply({"type": "organic", "preset": "flower", "name": "bloom", "seed": 4, "width": 360, "height": 360,
             "x": 20, "y": 20, **fields})
    return group_layers(p, "bloom")


def test_a_preset_in_a_house_style_document_gets_ink_part_lines_a_hard_shadow_and_a_subtle_wobble():
    p = house()
    group, layers = flower(p)
    petals = next(layer for layer in layers if layer["name"].endswith("petals"))
    assert petals["stroke"] == "@ink" and petals["stroke_width"] == pytest.approx(0.012 * 360, abs=0.01)
    assert petals["irregular"]["recipe"]["strength"] == "subtle"
    seeds = next(layer for layer in layers if layer["name"].endswith("center"))
    assert seeds["stroke_width"] < petals["stroke_width"] / 3  # a part of small elements keeps a finer line
    assert "irregular" not in seeds  # and is not scrambled by a wobble sized for the whole form
    shadow = group["styles"]["drop-shadow"]
    assert shadow["blur"] == 0 and shadow["color"] == "@ink" and shadow["dx"] == shadow["dy"] == pytest.approx(10.8)
    assert group["organic"]["illustration"] == "house"
    assert p.render().getbbox() is not None


def test_house_style_off_and_plain_documents_draw_the_preset_as_before():
    plain = Project(400, 400, "#f1faee")
    _, before = flower(plain)
    for p in (Project(400, 400, "#f1faee", house_style="off", workspace_fonts=False), house()):
        extra = {"illustration": "plain"} if p is not None and p.state.get("design_defaults", {}).get("house_style") != "off" else {}
        group, layers = flower(p, **extra)
        assert "styles" not in group and not any("irregular" in layer for layer in layers)
        assert [(layer["stroke"], layer["stroke_width"], layer["fill"], layer["path"]) for layer in layers] == \
               [(layer["stroke"], layer["stroke_width"], layer["fill"], layer["path"]) for layer in before]
    assert "illustration" not in plain.layer("bloom")["organic"]


def test_outline_false_is_plain_and_reported_and_explicit_strokes_win():
    p = house()
    result = p.apply({"type": "organic", "preset": "flower", "name": "bloom", "seed": 4, "outline": False})
    assert any("outline false → illustration: 'plain'" in note for note in result["normalized"])
    group, layers = group_layers(p, "bloom")
    assert "styles" not in group and all(layer["stroke"] != "@ink" for layer in layers)
    q = house()
    group, layers = flower(q, stroke="#336699", stroke_width=2)
    petals = next(layer for layer in layers if layer["name"].endswith("petals"))
    assert petals["stroke"] == "#336699" and petals["stroke_width"] == 2 and "drop-shadow" in group["styles"]
    with pytest.raises(VixlError, match="illustration"):
        q.apply({"type": "organic", "preset": "leaf", "illustration": "loud"})


def test_surfaces_and_line_forms_get_no_outline_shadow_or_wobble():
    p = house()
    p.apply({"type": "organic", "preset": "spots", "name": "coat", "seed": 2})
    assert "styles" not in p.layer("coat") and "irregular" not in p.layer("coat")
    p.apply({"type": "organic", "preset": "fern", "name": "fern", "seed": 2})
    fern = p.layer("fern")
    assert "styles" not in fern and "irregular" not in fern and fern["organic"]["illustration"] == "house"
    p.apply({"type": "organic", "preset": "leaf", "name": "plain-leaf", "seed": 2, "illustration": "plain"})
    assert "styles" not in p.layer("plain-leaf")
    forced = Project(300, 300)
    forced.apply({"type": "organic", "preset": "leaf", "name": "leaf", "seed": 2, "illustration": "house"})
    assert "drop-shadow" in forced.layer("leaf").get("styles", {}) or "drop-shadow" in group_layers(forced, "leaf")[0]["styles"]


def test_extra_lines_are_generated_path_layers_inside_the_form_for_a_seed_that_draws_them():
    drawn, quiet = line_seed(True), line_seed(False)
    p = house()
    group, layers = flower(p, seed=drawn)
    lines = [layer for layer in layers if layer["name"].startswith("bloom/outline-")]
    assert 1 <= len(lines) <= 2 and all(layer["generated"]["by"] == "object-outline" for layer in lines)
    assert all(layer["fill"] == "transparent" and layer["stroke"] == "@ink" for layer in lines)
    assert lines[0]["stroke_width"] == pytest.approx(0.012 * 360 * 0.5, abs=0.01)
    assert p.render().getbbox() is not None
    q = house()
    _, layers = flower(q, seed=quiet)
    assert not any(layer["name"].startswith("bloom/outline-") for layer in layers)
    # Growing the form again draws the same decision again, and keeps one shadow.
    p.apply({"type": "organic", "target": "bloom", "seed": drawn})
    group, layers = group_layers(p, "bloom")
    assert [layer["name"] for layer in layers if "outline-" in layer["name"]] == [layer["name"] for layer in lines]
    assert list(group["styles"]) == ["drop-shadow"]


def test_regrowing_a_form_keeps_the_finish_and_a_form_from_before_stays_plain():
    p = house()
    flower(p)
    p.apply({"type": "organic", "target": "bloom", "seed": 9})
    group, layers = group_layers(p, "bloom")
    petals = next(layer for layer in layers if layer["name"].endswith("petals"))
    assert petals["irregular"]["recipe"]["seed"] == 9 and petals["stroke"] == "@ink" and "drop-shadow" in group["styles"]
    old = Project(300, 300)
    old.apply({"type": "organic", "preset": "leaf", "name": "leaf", "seed": 1, "width": 200, "height": 200})
    old.state["design_defaults"] = {"seed": 1, "variety": "medium"}  # the document gained a house style since
    old.apply({"type": "organic", "target": "leaf", "seed": 2})
    assert "illustration" not in old.layer("leaf")["organic"] and "irregular" not in old.layer("leaf")


# --- objects ----------------------------------------------------------------------------------------------------


def operations(result, kind):
    return [op for op in result["operations"] if op["type"] == kind]


def test_object_plan_in_a_house_style_document_ends_with_the_illustration_finish():
    p = house()
    result = plan({"kind": "dog", "height": 300}, p)
    box = result["box"]
    kinds = [(op["type"], op.get("action")) for op in result["operations"]]
    assert kinds[-3:] == [("irregular", None), ("object", "outline"), ("layer-style", None)]
    outline = result["operations"][-2]
    assert outline["outline"] == "parts" and outline["outline_color"] == "@ink"
    assert outline["outline_width"] == pytest.approx(0.012 * max(box[2], box[3]), abs=0.01)
    shadow = result["operations"][-1]
    assert shadow["name"] == "drop-shadow" and shadow["settings"]["blur"] == 0
    assert shadow["settings"]["dx"] == shadow["settings"]["dy"] > 0
    wobble = operations(result, "irregular")[0]
    assert wobble["strength"] == "subtle" and wobble["only"] == ["wobble"] and "dog-body" in wobble["targets"]
    # An eye is too small for a line of that width: it is left out of the outline, as a flat illustration draws it.
    person = plan({"kind": "person", "height": 400}, p)["operations"]
    left_out = {op["part"] for op in person if op.get("action") == "part" and op.get("outline") == "none"}
    assert left_out == {"eye", "mouth"}
    assert not [op for op in result["operations"] if op.get("outline") == "none"]  # the dog's parts are all big enough
    assert plan({"kind": "dog", "height": 300}, p) == result  # deterministic
    assert operations(plan({"kind": "dog", "height": 300, "seed": 7}, p), "irregular")[0]["seed"] == 7


def test_object_plan_without_a_house_style_or_with_plain_is_unchanged():
    place = {"x": 20, "y": 20, "height": 300}
    base = plan({"kind": "dog", **place}, Project(400, 400))["operations"]
    assert base == plan({"kind": "dog", **place})["operations"]
    assert not [op for op in base if op["type"] in ("irregular", "layer-style") or op.get("action") == "outline"]
    p = house()
    assert plan({"kind": "dog", "illustration": "plain", **place}, p)["operations"] == base
    muted = plan({"kind": "dog", "outline": False, **place}, p)
    assert muted["operations"] == base
    assert muted["normalized"] == [{"field": "outline", "reason": "outline false → illustration: 'plain'"}]
    assert plan({"kind": "dog", "illustration": "house", **place}, Project(400, 400))["operations"][-1]["name"] \
        == "drop-shadow"
    with pytest.raises(VixlError, match="illustration"):
        plan({"kind": "dog", "illustration": "sketchy"}, p)
    off = Project(400, 400, house_style="off", workspace_fonts=False)
    assert plan({"kind": "dog", **place}, off)["operations"] == base


def test_the_figure_plan_template_is_left_alone_in_a_house_style_document(tmp_path):
    p = house()
    result = plan({"kind": "person", "template": "figure-plan", "height": 500}, p)
    assert not [op for op in result["operations"] if op.get("type") in ("irregular", "layer-style", "object")]
    session = Session(workspace=tmp_path)
    assert dispatch(session, "figure-plan", {"spec": {"height": 500}})["operations"] == result["operations"]


@pytest.mark.parametrize("kind", SEEDS)
def test_every_seed_kind_scaffold_with_the_finish_passes_the_object_check(kind):
    p = house()
    result = plan({"kind": kind}, p)
    p.apply(result["operations"])
    issues = [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"]
    assert issues == []
    group = p.layer(result["name"])
    assert group["object"]["outline"] == "parts" and group["object"]["outlined"]["outline"] == "parts"
    assert "drop-shadow" in group["styles"] and objects.missing_parts(p, group) == []
    assert p.render().getbbox() is not None


def test_a_sub_object_is_outlined_and_the_object_casts_the_only_shadow():
    p = house()
    result = plan({"kind": "person", "height": 400, "with": [{"kind": "guitar", "anchor": "torso.center"}]}, p)
    shadows = operations(result, "layer-style")
    assert [op["target"] for op in shadows] == ["person"]
    outlines = [op["target"] for op in operations(result, "object") if op.get("action") == "outline"]
    assert outlines == ["person-guitar", "person"]
    p.apply(result["operations"])
    assert "styles" not in p.layer("person-guitar") and p.layer("person-guitar")["object"]["outlined"]
    assert [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"] == []
    plain = plan({"kind": "person", "height": 400, "illustration": "plain",
                  "with": [{"kind": "guitar", "anchor": "torso.center"}]}, p)
    assert not [op for op in plain["operations"] if op.get("action") == "outline" or op["type"] == "layer-style"]


def test_apply_true_applies_the_finish_as_one_undo_step():
    p = house()
    from vixl.object_plan import run

    before = len(p.nodes)
    result = run(p, {"kind": "cup", "apply": True})
    assert result["applied"] is True and len(p.nodes) == before + 1
    assert p.layer("cup")["object"]["outlined"]["width"] == result["operations"][-2]["outline_width"]
    p.undo()
    assert not any(layer["name"].startswith("cup") for layer in p.state["layers"])


# --- outline lines ----------------------------------------------------------------------------------------------


def mushroom(extra=()):
    p = Project(320, 280, "#f4efe6")
    p.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "shroom-stem", "x": 100, "y": 110, "width": 50,
         "height": 120, "fill": "#f1e3d3"},
        {"type": "shape", "shape": "semicircle", "name": "shroom-cap", "x": 40, "y": 30, "width": 170, "height": 100,
         "fill": "#d62828"},
        {"type": "group", "name": "shroom", "targets": ["shroom-stem", "shroom-cap"]},
        {"type": "object", "target": "shroom", "kind": "mushroom"},
        {"type": "object", "action": "part", "target": "shroom-stem", "part": "stem"},
        {"type": "object", "action": "part", "target": "shroom-cap", "part": "cap"},
        *extra,
    ])
    return p


def test_outline_lines_draw_thin_generated_lines_inside_the_outline_and_follow_the_parts():
    lines = [{"gap": 3, "width": 1.5}, {"gap": 3, "width": 1.5}]
    p = mushroom([{"type": "object", "action": "outline", "target": "shroom", "outline": "parts", "outline_width": 4,
                   "outline_lines": lines}])
    group = p.layer("shroom")
    drawn = [layer for layer in p.state["layers"] if layer.get("parent") == group["id"] and layer.get("generated")]
    assert [layer["name"] for layer in drawn] == ["shroom/outline-1", "shroom/outline-2"]
    assert [layer["generated"] for layer in drawn] == [{"by": "object-outline", "line": 1},
                                                      {"by": "object-outline", "line": 2}]
    assert all(layer["fill"] == "transparent" and layer["stroke_width"] == 1.5 for layer in drawn)
    assert group["object"]["outlined"]["lines"] == lines
    assert [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"] == []
    first = drawn[0]["path"]
    p.apply({"type": "move", "target": "shroom-cap", "x": 60, "y": 30})  # a moved part redraws the lines with it
    redrawn = [layer for layer in p.state["layers"] if layer.get("parent") == group["id"] and layer.get("generated")]
    assert len(redrawn) == 2 and redrawn[0]["path"] != first
    p.apply({"type": "object", "action": "outline", "target": "shroom", "outline_lines": []})
    assert not [layer for layer in p.state["layers"] if layer.get("generated")]
    record = p.layer("shroom")["object"]
    assert "lines" not in record["outlined"] and "outline_lines" not in record


def test_outline_lines_work_under_silhouette_and_go_with_outline_remove():
    p = mushroom([{"type": "object", "action": "outline", "target": "shroom", "outline": "silhouette",
                   "outline_width": 4, "outline_lines": [{"gap": 3, "width": 1.5}]}])
    names = [layer["name"] for layer in p.state["layers"] if layer.get("generated")]
    assert names == ["shroom/outline", "shroom/outline-1"]
    assert [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"] == []
    p.apply({"type": "object", "action": "outline-remove", "target": "shroom"})
    assert not [layer for layer in p.state["layers"] if layer.get("generated")]
    assert "outline_lines" not in p.layer("shroom")["object"]


def test_outline_lines_are_validated():
    p = mushroom()
    for bad in ([{"gap": 3}], [{"gap": 0, "width": 1}], [{"gap": 1, "width": 1}] * 4, "thin"):
        with pytest.raises(VixlError):
            p.apply({"type": "object", "action": "outline", "target": "shroom", "outline_lines": bad})
    with pytest.raises(VixlError, match="outline_lines to action outline"):
        p.apply({"type": "object", "action": "part", "target": "shroom-cap", "part": "cap",
                 "outline_lines": [{"gap": 1, "width": 1}]})


def test_the_cli_spells_outline_lines_and_the_plain_illustration():
    from vixl.cli import object_plan_command
    from vixl.objects import compile_command
    from vixl.plugins.organic.organic import compile_command as organic_command

    assert compile_command("object", ["outline", "dog", "--outline-lines", '[{"gap": 2, "width": 1}]'])[
        "outline_lines"] == [{"gap": 2, "width": 1}]
    assert organic_command("organic", ["leaf", "--illustration", "plain"])["illustration"] == "plain"
    p = house()
    result, changed = object_plan_command(p, ["cup", "--illustration", "plain"])
    assert not changed and not operations(result, "irregular")
    result, changed = object_plan_command(p, ["cup"])
    assert not changed and operations(result, "layer-style")


def test_the_default_outline_width_is_the_house_part_line_under_parts_and_one_percent_under_silhouette():
    p = mushroom()
    [parts] = p.apply({"type": "object", "action": "outline", "target": "shroom", "outline": "parts"})["outlines"]
    [silhouette] = p.apply({"type": "object", "action": "outline", "target": "shroom",
                            "outline": "silhouette"})["outlines"]
    assert parts["width"] == 2.5 and silhouette["width"] == 2.0  # 1.2% and 1% of the 200 px group, to half a pixel
    big = Project(1000, 1000)
    big.apply([{"type": "shape", "shape": "ellipse", "name": "a", "x": 0, "y": 0, "width": 800, "height": 800,
                "fill": "#ccc"}, {"type": "group", "name": "g", "targets": ["a"]},
               {"type": "object", "target": "g", "kind": "rock"}])
    assert big.apply({"type": "object", "action": "outline", "target": "g", "outline": "parts"})["outlines"][0]["width"] \
        == 9.5
    assert big.apply({"type": "object", "action": "outline", "target": "g", "outline": "silhouette"})["outlines"][0][
        "width"] == 8.0
