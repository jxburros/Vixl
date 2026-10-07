"""Apply cost independent of unrelated layers (#284, #300): remembered inspections, cached text metrics and
partial layout must give exactly the results of a full, uncached pass."""

import hashlib
import io
from pathlib import Path

import pytest

from vixl import Project
from vixl import text_metrics
from vixl.render import layer_box, resolve_layout

FONT = Path(__file__).resolve().parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def wide_font(scale=2, latin_only=False):
    """DejaVu Sans with every advance ``scale`` times wider: same glyphs, different text metrics."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    if latin_only:
        options = subset.Options()
        options.name_IDs = ["*"]
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=range(32, 127))
        subsetter.subset(font)
    metrics = font["hmtx"].metrics
    for name, (advance, lsb) in list(metrics.items()):
        metrics[name] = (advance * scale, lsb)
    font["hhea"].advanceWidthMax *= scale
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def register(project, name, data):
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": name, "asset": asset})


def uncached_inspect(project):
    """inspect() with every text measurement recomputed from scratch."""
    saved = dict(text_metrics._PLAIN)
    text_metrics._PLAIN.clear()
    try:
        return project.inspect()
    finally:
        text_metrics._PLAIN.update(saved)


def text_info(project, name):
    layer = project.inspect(name)
    return {key: layer.get(key) for key in ("ink_bounds", "line_bounds", "baselines", "resolved_bounds")}


def test_text_metrics_follow_every_input_they_read():
    p = Project(900, 400, "white")
    register(p, "brand", wide_font(1))
    register(p, "latin", wide_font(1, latin_only=True))
    p.apply([{"type": "variable", "name": "who", "value": "Ada"},
              {"type": "text", "name": "t", "text": "Hello ${who}", "size": 30, "color": "black", "x": 20, "y": 20,
               "font": "brand"},
              {"type": "text", "name": "u", "text": "éclair", "size": 30, "color": "black", "x": 20, "y": 200,
               "font": "latin"}])
    history = [text_info(p, "t")]
    seen_u = [text_info(p, "u")]
    edits = [
        {"type": "move", "target": "t", "x": 40, "y": 60},
        {"type": "text-set", "target": "t", "text": "Hello there ${who}"},
        {"type": "text-set", "target": "t", "size": 44},
        {"type": "variable", "name": "who", "value": "Grace Hopper"},
        {"type": "text-set", "target": "t", "spacing": 12, "text": "two\nlines ${who}"},
    ]
    for edit in edits:
        p.apply(edit)
        assert p.inspect() == uncached_inspect(p)
        history.append(text_info(p, "t"))
        assert history[-1] != history[-2], edit
    # A wider font file: every measurement of "t" must change.
    register(p, "wide", wide_font(2))
    p.apply({"type": "text-set", "target": "t", "font": "wide"})
    assert p.inspect() == uncached_inspect(p)
    wider = text_info(p, "t")
    assert wider["ink_bounds"][2] > history[-1]["ink_bounds"][2] * 1.5
    # "é" is not in the latin-only font, so it comes from the fallback chain; changing that chain re-measures.
    register(p, "fallback", wide_font(3))
    p.apply({"type": "font-fallbacks", "fonts": ["fallback"]})
    assert p.inspect() == uncached_inspect(p)
    seen_u.append(text_info(p, "u"))
    assert seen_u[-1]["ink_bounds"] != seen_u[0]["ink_bounds"]


def test_remembered_inspection_matches_a_fresh_one():
    p = Project(600, 400, "white")
    p.apply([{"type": "text", "name": "t", "text": "Title", "size": 40, "color": "black"},
              {"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 50, "height": 50}])
    p.apply({"type": "move", "target": "box", "x": 30})
    remembered = p._remembered_inspect()
    assert remembered is not None and remembered == p.inspect()
    # Edits outside apply invalidate it.
    p.state["layers"][1]["x"] = 99
    assert p._remembered_inspect() is None
    result = p.apply({"type": "move", "target": "t", "x": 5}, detail="compact")
    assert set(result["changes"]["layers"]) == {p.layer("t")["id"]}
    p.undo()
    assert p._remembered_inspect() is None
    box = p.layer("box")
    assert p.apply({"type": "move", "target": "box", "x": box["x"]}, detail="compact")["changes"] == {}
    # A new asset invalidates it too (an image or font may change what inspect reports).
    p.apply({"type": "move", "target": "box", "x": 1})
    p.assets["fonts/x.ttf"] = FONT.read_bytes()
    assert p._remembered_inspect() is None


def test_reported_changes_do_not_alias_the_remembered_inspection():
    p = Project(600, 400, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 50, "height": 50})
    result = p.apply({"type": "move", "target": "box", "x": 30})
    result["changes"]["layers"]["after"][0]["x"] = -1000
    result["changes"]["layers"]["after"][0]["effects"].append({"name": "blur"})
    assert p._remembered_inspect() == p.inspect()


def test_moves_in_a_batch_match_one_move_per_apply():
    ops = [{"type": "shape", "shape": "rectangle", "name": f"s{i}", "x": i * 3, "y": i, "width": 20, "height": 20}
           for i in range(30)]
    moves = [{"type": "move", "target": f"s{i % 30}", "x": i * 7 % 400, "y": i % 9, "relative": i % 2 == 0}
             for i in range(90)]
    batch, single = Project(800, 600, "white"), Project(800, 600, "white")
    batch.apply([*ops, *moves])
    single.apply(ops)
    for move in moves:
        single.apply(move)
    def placed(project):
        return [{key: value for key, value in layer.items() if key != "id"} for layer in project.state["layers"]]

    assert placed(batch) == placed(single)


def constrained_document():
    p = Project(1200, 800, "white")
    p.apply([
        {"type": "variable", "name": "label", "value": "Wide label text"},
        {"type": "text", "name": "title", "text": "${label}", "size": 40, "color": "black", "x": 30, "y": 30},
        {"type": "shape", "shape": "rectangle", "name": "under", "x": 0, "y": 0, "width": 80, "height": 10},
        {"type": "constrain", "target": "under", "constraints": {"left": "title.left", "top": "title.bottom+8"}},
        {"type": "shape", "shape": "rectangle", "name": "corner", "x": 0, "y": 0, "width": 40, "height": 40},
        {"type": "constrain", "target": "corner", "constraints": {"right": "canvas.right-20", "bottom": "under.bottom"}},
        {"type": "shape", "shape": "ellipse", "name": "a", "x": 400, "y": 300, "width": 60, "height": 60},
        {"type": "shape", "shape": "rectangle", "name": "b", "x": 480, "y": 300, "width": 60, "height": 60,
         "rotation": 30},
        {"type": "group", "name": "pair", "targets": ["a", "b"]},
        {"type": "shape", "shape": "rectangle", "name": "inner", "x": 0, "y": 0, "width": 30, "height": 30},
        {"type": "group", "name": "holder", "targets": ["inner"]},
        {"type": "constrain", "target": "inner", "constraints": {"right": "canvas.right"}},
        {"type": "shape", "shape": "star", "name": "master", "x": 700, "y": 500, "width": 50, "height": 50},
        {"type": "symbol", "name": "logo", "target": "master"},
        {"type": "symbol-instance", "symbol": "logo", "name": "copy", "x": 800, "y": 520},
        {"type": "text", "name": "s1", "text": "One", "size": 20, "color": "black", "x": 0, "y": 0},
        {"type": "text", "name": "s2", "text": "Two", "size": 20, "color": "black", "x": 0, "y": 40},
        {"type": "group", "name": "stacked", "targets": ["s1", "s2"]},
        {"type": "stack", "target": "stacked", "width": 300, "height": 200, "gap": 10, "align": "center"},
    ])
    return p


def test_partial_layout_matches_the_full_layout_for_every_layer():
    p = constrained_document()
    full = resolve_layout(p)
    for layer in p.state["layers"]:
        assert layer_box(p, layer) == full[layer["id"]], layer["name"]


def test_moves_follow_constraints_groups_symbols_and_stacks_as_before():
    p = constrained_document()
    p.apply({"type": "unconstrain", "target": "under"})
    for name in ("title", "under", "corner", "b", "inner", "copy", "stacked"):
        p.apply({"type": "move", "target": name, "x": 11, "y": 7, "relative": True})
    full = resolve_layout(p)
    assert all(layer_box(p, layer) == full[layer["id"]] for layer in p.state["layers"])


def test_inspect_measures_the_document_variables_once(monkeypatch):
    from vixl import forms

    p = Project(800, 600, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": f"Label {i}", "size": 12, "color": "black", "y": i * 12}
             for i in range(40)])
    calls = []
    original = forms.has_fields
    monkeypatch.setattr(forms, "has_fields", lambda project: calls.append(1) or original(project))
    p.inspect()
    assert len(calls) <= 3  # Was several calls per text layer, each scanning every layer (O(N²)).


@pytest.mark.parametrize("detail", ["brief", "compact", "full"])
def test_changes_are_the_same_with_and_without_the_remembered_inspection(detail):
    p = Project(600, 400, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hi", "size": 30, "color": "black"},
              {"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 50, "height": 50}])

    def run(remember):
        q = p.clone()
        if not remember:
            q._inspected = None
        return q.apply([{"type": "move", "target": "box", "x": 70}, {"type": "text-set", "target": "t", "size": 50}],
                       detail=detail)

    assert run(True) == run(False)
