"""Relative placement and arithmetic for templates and workflows: text line refs in constraints, ``=``
expressions, the ``calc`` filter and the motif pattern (#529)."""

import pytest

from vixl import Project, VixlError
from vixl import resources
from vixl.expressions import evaluate
from vixl.render import parse_constraint, resolve_layout
from vixl.text import line_edges


def lyric_scene(text, width=None):
    p = Project(1200, 600)
    p.apply([{"type": "variable", "name": "lyric", "value": text},
             {"type": "text", "name": "lyric", "text": "${lyric}", "size": 40, "x": 50, "y": 100}])
    if width:
        p.apply({"type": "text-layout", "target": "lyric", "width": width})
    p.apply([{"type": "shape", "shape": "star", "name": "flame", "width": 30, "height": 30},
             {"type": "constrain", "target": "flame",
              "constraints": {"left": "lyric.line[-1].end + 0.25em", "bottom": "lyric.baseline[-1]"}}])
    return p


def placed(p):
    bounds = resolve_layout(p)
    lyric = p.layer("lyric")
    resolved = next(layer for layer in p.inspect()["layers"] if layer["id"] == lyric["id"])
    return bounds[p.layer("flame")["id"]], bounds[lyric["id"]], resolved


def test_flame_follows_the_end_of_a_longer_variable_lyric():
    p = lyric_scene("Burn")
    flame, lyric, _ = placed(p)
    p.apply({"type": "variable", "name": "lyric", "value": "Burn it all down tonight"})
    longer, lyric_after, _ = placed(p)
    # The mark sits a quarter em (10 px at size 40) past where the last line's pen ends.
    assert longer[0] > flame[0] + 200
    from vixl.render import resolved_layers

    layer = next(item for item in resolved_layers(p) if item["name"] == "lyric")
    start, end, baseline = line_edges(p, layer)[-1]
    assert longer[0] == pytest.approx(lyric_after[0] + end + 10, abs=0.01)
    assert longer[1] + longer[3] == pytest.approx(lyric_after[1] + baseline, abs=0.01)
    assert p.layer("flame")["constraints"]["left"] == f"{p.layer('lyric')['id']}.line[-1].end+0.25em"


def test_line_refs_read_the_wrapped_last_line_and_the_first_line():
    p = lyric_scene("one two three four five six seven", width=260)
    from vixl.render import resolved_layers

    layer = next(item for item in resolved_layers(p) if item["name"] == "lyric")
    edges = line_edges(p, layer)
    assert len(edges) > 1 and edges[-1][2] > edges[0][2]
    p.apply({"type": "constrain", "target": "flame", "constraints": {"left": "lyric.line[0].start-40"}})
    flame, lyric, _ = placed(p)
    assert flame[0] == pytest.approx(lyric[0] + edges[0][0] - 40, abs=0.01)


@pytest.mark.parametrize("constraints, match", [
    ({"top": "lyric.line[-1].end"}, "horizontal position"),
    ({"left": "lyric.baseline[0]"}, "vertical position"),
    ({"left": "box.line[0].end"}, "text layer"),
    ({"left": "lyric.line[5].end"}, "has 1 line"),
    ({"left": "box.right+1em"}, "text layer"),
    ({"left": "lyric.line[x].end"}, "Invalid constraint expression"),
])
def test_line_refs_are_checked(constraints, match):
    p = lyric_scene("Burn")
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "width": 10, "height": 10})
    with pytest.raises(VixlError, match=match):
        p.apply({"type": "constrain", "target": "flame", "constraints": constraints})


def test_parse_constraint_round_trips_and_keeps_box_refs():
    assert parse_constraint("a.b.left+8").ref == "a.b"
    assert parse_constraint("canvas.right-40").text() == "canvas.right-40"
    ref = parse_constraint(" lyric.line[-1].end + 0.25em ")
    assert (ref.anchor, ref.line, ref.offset, ref.unit) == ("line-end", -1, 0.25, "em")
    assert ref.text("lyr_1") == "lyr_1.line[-1].end+0.25em"
    assert parse_constraint("lyric.baseline[2]-4px").text() == "lyric.baseline[2]-4"
    assert parse_constraint("lyric.line[-1]") is None


def test_preview_proxy_scales_pixel_offsets_but_not_em():
    from vixl.proxy import _scale_layer

    layer = {"type": "shape", "x": 0, "y": 0, "width": 10, "height": 10,
             "constraints": {"left": "lyr_1.line[-1].end+0.25em", "top": "lyr_1.bottom+20"}}
    _scale_layer(layer, 0.5)
    assert layer["constraints"] == {"left": "lyr_1.line[-1].end+0.25em", "top": "lyr_1.bottom+10"}


# --- expressions --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, value", [
    ("1 + 2 * 3", 7), ("(1 + 2) * 3", 9), ("7 // 2", 3), ("7 % 4", 3), ("-3 + +2", -1), ("10 / 4", 2.5),
    ("min(4, 2, 8)", 2), ("max(1, 2)", 2), ("round(2.567, 2)", 2.57), ("round(2.5)", 2), ("abs(-3.5)", 3.5),
    ("76.34 * 2", 152.68),
])
def test_expressions_evaluate_arithmetic(text, value):
    assert evaluate(text) == pytest.approx(value)


@pytest.mark.parametrize("text, match", [
    ("x + 1", "names 'x'"),
    ("__import__('os').system('true')", "calls something other"),
    ("().__class__", "Attribute"),
    ("(1).real", "Attribute"),
    ("open('/etc/passwd')", "calls something other"),
    ("min(1, 2, key=abs)", "plain arguments"),
    ("[1, 2][0]", "Subscript"),
    ("'a' * 3", "not a number"),
    ("2 ** 10", "exponents"),
    ("lambda: 1", "Lambda"),
    ("1 if 1 else 2", "IfExp"),
    ("1 < 2", "Compare"),
    ("1 / 0", "divides by zero"),
    ("5 // (2 - 2)", "divides by zero"),
    ("1 % 0", "divides by zero"),
    ("1e308 * 10", "beyond"),
    ("9" * 400, "too large|beyond"),
    ("1 + " * 150 + "1", "longer than|more than"),
    ("(" * 240 + "1" + ")" * 240, "not arithmetic|more than"),
    ("", "empty"),
    ("1 +", "not arithmetic"),
])
def test_expressions_refuse_anything_but_bounded_arithmetic(text, match):
    with pytest.raises(VixlError, match=match):
        evaluate(text)


def test_evaluator_never_reaches_eval(monkeypatch):
    import builtins

    def forbidden(*args, **kwargs):
        raise AssertionError("eval/exec must not run")

    monkeypatch.setattr(builtins, "eval", forbidden)
    monkeypatch.setattr(builtins, "exec", forbidden)
    assert evaluate("round(10 / 3, 2) + max(1, 2)") == pytest.approx(5.33)


def test_template_expressions_scale_proportionally_and_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    resources.register("templates", "offsets", {
        "width": 1000, "height": 1000, "proportional": True, "defaults": {"pad": 40, "k": 2},
        "operations": [
            {"type": "shape", "shape": "rectangle", "name": "bar", "x": "=${pad} + 76.34 * ${k}", "y": "=${pad}",
             "width": "=max(${pad} * 5, 100)", "height": 20, "fill": "#123456"},
            {"type": "text", "name": "note", "text": "==not evaluated", "size": 30, "x": 10, "y": 900},
        ],
    }, workspace=tmp_path)
    boxes = {}
    for size in (1000, 500):
        p = Project(size, size)
        p._workspace = tmp_path
        result = p.apply({"type": "template-apply", "name": "offsets"}, detail="compact")
        layer = p.layer("bar")
        boxes[size] = (layer["x"], layer["y"], layer["width"])
        assert any("'=${pad} + 76.34 * ${k}' → 192.68" in text for text in result["normalized"])
        assert p.layer("note")["text"] == "=not evaluated"
    assert boxes[1000] == (193, 40, 200)
    assert boxes[500] == (96, 20, 100)
    with pytest.raises(VixlError, match="names 'pad'"):
        resources.register("templates", "broken", {"width": 100, "height": 100, "operations": [
            {"type": "shape", "shape": "rectangle", "name": "bar", "x": "=pad + 1", "width": 10, "height": 10}]},
            workspace=tmp_path)


def test_workflow_expressions_are_reported_under_normalized():
    from vixl.effect_workflows import apply

    p = Project(200, 200)
    p.apply({"type": "shape", "shape": "rectangle", "name": "artwork", "width": 50, "height": 50})
    workflow = {"defaults": {"target": "artwork", "step": 12},
                "operations": [{"type": "move", "target": "${target}", "x": "=${step} * 3", "y": "=${step} / 4"}]}
    result = apply(p, workflow, {"step": 10})
    assert (p.layer("artwork")["x"], p.layer("artwork")["y"]) == (30, 2.5)
    assert any("x: '=${step} * 3' → 30" in text for text in result["normalized"])


def test_calc_filter_does_arithmetic_inside_text():
    p = Project(600, 200)
    p.apply([{"type": "variable", "name": "price", "value": 25},
             {"type": "variable", "name": "sum", "value": "3 * 4"},
             {"type": "text", "name": "t", "text": "Now ${price|calc:x*0.8|number:2}, was ${price}; ${sum|calc}"}])
    from vixl.render import resolved_layers

    text = next(item for item in resolved_layers(p) if item["name"] == "t")["text"]
    assert text == "Now 20.00, was 25; 12"
    with pytest.raises(VixlError, match="names 'y'"):
        p.apply({"type": "text-set", "target": "t", "text": "${price|calc:y+1}"})
