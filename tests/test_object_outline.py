"""Outline policy per object and part (#379): the outline action, its regeneration and its check findings."""

import io

import pytest

from vixl import Project, objects
from vixl.errors import VixlError
from vixl.object_outline import THIN, default_policy, geometry_hash


def shroom(p=None, name="shroom", x=40, y=30, stem_stroke=None):
    """A three-part mushroom: a stem, a cap over it and a spot on the cap."""
    p = p or Project(320, 280, "#f4efe6")
    stroke = {"stroke": stem_stroke[0], "stroke_width": stem_stroke[1]} if stem_stroke else {}
    p.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-stem", "x": x + 60, "y": y + 80,
         "width": 50, "height": 120, "fill": "#f1e3d3", **stroke},
        {"type": "shape", "shape": "semicircle", "name": f"{name}-cap", "x": x, "y": y, "width": 170,
         "height": 100, "fill": "#d62828"},
        {"type": "shape", "shape": "ellipse", "name": f"{name}-spot", "x": x + 70, "y": y + 30, "width": 30,
         "height": 24, "fill": "#fdf0d5"},
        {"type": "group", "name": name, "targets": [f"{name}-stem", f"{name}-cap", f"{name}-spot"]},
        {"type": "object", "target": name, "kind": "mushroom"},
        {"type": "object", "action": "part", "target": f"{name}-stem", "part": "stem"},
        {"type": "object", "action": "part", "target": f"{name}-cap", "part": "cap"},
        {"type": "object", "action": "part", "target": f"{name}-spot", "part": "spots"},
    ])
    return p


def outline(p, name="shroom", **fields):
    return p.apply({"type": "object", "action": "outline", "target": name, **fields})


def found(p, rule=None):
    issues = [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"]
    return [i for i in issues if rule is None or i["rule"] == rule]


def test_kinds_default_policies_come_from_the_taxonomy_outline_entry():
    kinds = objects.registry()
    assert default_policy("dog", kinds) == ("silhouette", "thin")
    assert default_policy("guitar", kinds) == ("silhouette", "thin")
    assert default_policy("rock", kinds) == ("none", "hide")
    assert default_policy("icon", kinds)[0] == "silhouette" and default_policy("icon", kinds)[1] == "show"
    assert objects.describe("dog")["outline_policy"] == {"outline": "silhouette", "interior": "thin"}


def test_the_silhouette_is_one_generated_layer_around_the_union_of_the_parts():
    p = shroom()
    result = outline(p, outline="silhouette", interior="hide")
    [summary] = result["outlines"]
    assert summary["layer"] == "shroom/outline" and summary["parts"] == 3 and summary["width"] == 2.0
    layer, group = p.layer("shroom/outline"), p.layer("shroom")
    assert layer["generated"] == {"by": "object-outline"} and layer["parent"] == group["id"]
    assert layer["fill"] == "transparent" and layer["stroke"] == "#1d1d24" and layer["role"] == "decoration"
    children = [item for item in p.state["layers"] if item.get("parent") == group["id"]]
    assert children[-1] is layer  # the top child: drawn over the parts
    # The union of cap (0..170 × 0..100) and stem (60..110 × 80..200) in the group's frame.
    assert (layer["x"], layer["y"]) == (0, 0) and abs(layer["width"] - 170) <= 1 and abs(layer["height"] - 200) <= 1
    assert layer["path"].count("M") == 1
    assert found(p) == []


def test_interior_hide_thin_and_show_and_restoring_the_original_strokes():
    p = shroom(stem_stroke=("#ff0000", 5))
    outline(p, outline="silhouette", interior="hide", outline_width=4)
    stem, cap = p.layer("shroom-stem"), p.layer("shroom-cap")
    assert "stroke" not in stem and "stroke" not in cap
    outline(p, interior="thin")
    stem = p.layer("shroom-stem")
    assert stem["stroke_width"] == pytest.approx(4 * THIN) and stem["stroke"] == "#1d1d24"
    outline(p, interior="show", outline_color="#2b2d42")
    stem = p.layer("shroom-stem")
    assert stem["stroke_width"] == 4 and stem["stroke"] == "#2b2d42"
    assert p.layer("shroom")["object"]["outlined"]["strokes"][stem["id"]] == {"stroke": "#ff0000", "stroke_width": 5}
    p.apply({"type": "object", "action": "outline-remove", "target": "shroom"})
    stem, cap = p.layer("shroom-stem"), p.layer("shroom-cap")
    assert (stem["stroke"], stem["stroke_width"]) == ("#ff0000", 5) and "stroke" not in cap
    assert p.find_layer("shroom/outline") is None
    assert set(p.layer("shroom")["object"]) == {"version", "kind"}


def test_parts_outlines_every_part_alike_and_none_restores():
    p = shroom(stem_stroke=("#ff0000", 5))
    outline(p, outline="parts", outline_width=3)
    assert p.find_layer("shroom/outline") is None
    assert {p.layer(n)["stroke_width"] for n in ("shroom-stem", "shroom-cap", "shroom-spot")} == {3}
    outline(p, outline="none")
    assert p.layer("shroom-stem")["stroke"] == "#ff0000" and "stroke" not in p.layer("shroom-cap")
    assert p.layer("shroom")["object"]["outline"] == "none" and "outlined" not in p.layer("shroom")["object"]


def test_inherit_uses_the_kind_and_a_natural_kind_draws_none():
    p = shroom()
    outline(p)
    assert p.layer("shroom")["object"]["outlined"]["outline"] == "silhouette"
    assert p.layer("shroom")["object"]["outlined"]["interior"] == "thin"
    rock = Project(420, 420)
    rock.apply(objects.merged("rock")["build"]["example"])
    result = rock.apply({"type": "object", "action": "outline", "target": "rock"})
    assert result["outlines"] == [{"object": "rock", "outline": "none"}]
    assert rock.find_layer("rock/outline") is None


def test_moving_a_part_redraws_the_outline_in_the_same_history_step():
    p = shroom()
    outline(p, outline="silhouette")
    before = p.layer("shroom/outline")["path"]
    steps = len(p.nodes)
    p.apply({"type": "move", "target": "shroom/stem", "x": 30, "y": 95})
    moved = p.layer("shroom/outline")
    assert moved["path"] != before and moved["height"] == 215 and len(p.nodes) == steps + 1
    assert p.layer("shroom")["object"]["outlined"]["hash"] == geometry_hash(p, p.layer("shroom"))
    p.undo()
    assert p.layer("shroom/outline")["path"] == before
    p.redo()
    assert p.layer("shroom/outline")["path"] == moved["path"]
    assert found(p) == []


def test_a_new_part_takes_the_policy_and_joins_the_silhouette():
    p = shroom()
    outline(p, outline="silhouette", interior="thin", outline_width=5)
    p.apply([{"type": "shape", "shape": "ellipse", "name": "gills", "x": 40, "y": 120, "width": 100, "height": 40,
              "fill": "#c9ada7"},
             {"type": "reparent", "targets": ["gills"], "into": "shroom"},
             {"type": "object", "action": "part", "target": "gills", "part": "gills"}])
    assert p.layer("gills")["stroke_width"] == pytest.approx(5 * THIN)
    assert p.layer("gills")["id"] in p.layer("shroom")["object"]["outlined"]["strokes"]


def test_line_work_keeps_its_stroke_and_adds_no_area():
    p = shroom()
    p.apply([{"type": "shape", "shape": "path", "name": "whisker", "x": 150, "y": 60, "path": "M0 0 L120 30",
              "stroke": "#264653", "stroke_width": 3},
             {"type": "reparent", "targets": ["whisker"], "into": "shroom"}])
    outline(p, outline="silhouette", interior="hide")
    whisker, layer = p.layer("whisker"), p.layer("shroom/outline")
    assert (whisker["stroke"], whisker["stroke_width"]) == ("#264653", 3)
    assert layer["x"] + layer["width"] <= 171


def test_part_overrides_leave_a_part_out_or_give_it_the_full_outline():
    p = shroom()
    p.apply([{"type": "move", "target": "shroom-spot", "x": 200, "y": 0},
             {"type": "object", "action": "part", "target": "shroom-spot", "part": "spots", "outline": "none"},
             {"type": "object", "action": "part", "target": "shroom-stem", "part": "stem", "outline": "parts"}])
    outline(p, outline="silhouette", interior="hide", outline_width=4)
    layer = p.layer("shroom/outline")
    assert layer["width"] <= 171  # the spot, moved clear of the cap, is not in the silhouette
    assert "stroke" not in p.layer("shroom-spot") and p.layer("shroom-stem")["stroke_width"] == 4
    assert "stroke" not in p.layer("shroom-cap")
    assert p.layer("shroom-spot")["object_part"] == {"name": "spots", "outline": "none"}


def test_seam_weight_and_stale_findings():
    p = shroom()
    outline(p, outline="silhouette", interior="hide")
    p.apply({"type": "shape", "target": "shroom-stem", "stroke": "#000000", "stroke_width": 3})
    [seam] = found(p, "object.outline-seam")
    assert seam["action"] == "review" and seam["measured"] == {"actual": 3, "expected": 0, "unit": "px"}
    assert "shroom/stem" in seam["message"] and "outline: none" in seam["hint"]
    outline(p, outline="parts", outline_width=2)
    assert found(p) == []
    p.apply({"type": "shape", "target": "shroom-cap", "stroke_width": 6})
    [weight] = found(p, "object.outline-weight")
    assert weight["measured"]["actual"] == 3 and len(weight["layer_ids"]) == 2
    outline(p, outline="silhouette")
    p.layer("shroom-stem")["x"] += 40  # edited outside an apply: nothing redraws the outline
    [stale] = found(p, "object.outline-stale")
    assert stale["action"] == "fix" and "action: outline" in stale["hint"]
    p.apply({"type": "object", "action": "outline", "target": "shroom"})
    p.apply({"type": "remove", "target": "shroom/outline"})
    [gone] = found(p, "object.outline-stale")
    assert "gone" in gone["message"] and gone["measured"]["actual"] == "missing"


def test_the_outline_layer_does_not_bridge_a_gap_for_either_check():
    p = shroom()
    outline(p, outline="silhouette")
    p.apply({"type": "move", "target": "shroom-stem", "x": 60, "y": 150})
    [gap] = found(p, "object.gap")
    assert "shroom/stem" in gap["message"]
    connected = [i for i in p.check(checks=["connected"])["issues"] if i["check"] == "connected"]
    assert [i["layers"] for i in connected] == [["shroom-stem"]]


def test_duplicate_and_unset_carry_the_outline_state():
    p = shroom(stem_stroke=("#ff0000", 5))
    outline(p, outline="silhouette", interior="hide")
    p.apply({"type": "duplicate", "target": "shroom", "name": "twin"})
    twin = p.layer("twin")
    copies = {layer["id"] for layer in objects.subtree(p, twin["id"])}
    assert set(twin["object"]["outlined"]["strokes"]) <= copies
    assert sum(1 for layer in p.state["layers"] if layer.get("generated")) == 2
    p.apply({"type": "object", "action": "outline-remove", "target": "twin"})
    stems = [layer for layer in p.state["layers"] if layer["id"] in copies and layer.get("object_part", {}).get("name") == "stem"]
    assert stems[0]["stroke"] == "#ff0000" and "stroke" not in p.layer("shroom-stem")
    p.apply({"type": "object", "action": "unset", "target": "shroom"})
    assert p.layer("shroom-stem")["stroke"] == "#ff0000" and p.find_layer("shroom/outline") is None


def test_svg_pdf_and_pptx_draw_the_outline_unfilled():
    p = shroom(stem_stroke=("#ff0000", 5))
    outline(p, outline="silhouette", interior="hide", outline_color="#00ff00", outline_width=3)
    svg = p.export(format="SVG", svg_document=False).decode()
    start = svg.index('data-layer="shroom/outline"')
    path = svg[svg.index("<path", start):]
    path = path[:path.index(">")]
    assert ('fill="none"' in path or 'fill-opacity="0.0"' in path) and 'stroke="rgb(0,255,0)"' in path
    assert 'stroke-width="3' in path
    pdf = p.export(format="PDF", pdf_content="vector")
    pypdf = pytest.importorskip("pypdf")
    content = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].get_contents().get_data()
    drawn = content.split(b"0 1 0 RG\n", 1)[1].split(b"Q", 1)[0]
    assert b"\nS\n" in drawn and b"\nf\n" not in drawn and b"B\n" not in drawn
    pptx = pytest.importorskip("pptx")
    from lxml import etree

    shapes = {shape.name: shape for shape in pptx.Presentation(io.BytesIO(p.export(format="PPTX"))).slides[0].shapes}
    group = shapes["shroom"]
    [line] = [shape for shape in group.shapes if shape.name == "shroom/outline"]
    paint = etree.tostring(line._element).decode().split("</a:custGeom>")[1]
    assert paint.startswith("<a:noFill/><a:ln w=") and "00FF00" in paint.split("</a:ln>")[0]


def test_outline_needs_a_declared_object_and_its_own_fields():
    p = shroom()
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 20, "height": 20, "fill": "red"},
             {"type": "shape", "shape": "rectangle", "name": "b", "x": 10, "width": 20, "height": 20, "fill": "red"},
             {"type": "group", "name": "plain", "targets": ["a", "b"]}])
    with pytest.raises(VixlError, match="not a declared object"):
        outline(p, name="plain")
    with pytest.raises(VixlError, match="belong to action outline"):
        p.apply({"type": "object", "target": "shroom", "outline_width": 3})
    with pytest.raises(VixlError, match="takes only target"):
        p.apply({"type": "object", "action": "outline-remove", "target": "shroom", "outline": "parts"})
    with pytest.raises(VixlError):
        outline(p, outline_color="not-a-colour")


def test_cli_spelling_compiles_to_the_operation():
    from vixl.objects import compile_command

    assert compile_command("object", ["outline", "dog", "--outline", "parts", "--outline-width", "2"]) == {
        "type": "object", "action": "outline", "target": "dog", "outline": "parts", "outline_width": 2.0}
    assert compile_command("object", ["outline-remove", "dog"]) == {"type": "object", "action": "outline-remove",
                                                                     "target": "dog"}
    assert compile_command("object", ["part", "ear", "--part", "ear", "--outline", "none"])["outline"] == "none"


def test_inspect_reports_the_applied_policy():
    p = shroom()
    outline(p, outline="parts", outline_width=2)
    assert objects.tree(p, "shroom")["outline"] == {"outline": "parts", "interior": "thin", "color": "#1d1d24",
                                                    "width": 2.0}
