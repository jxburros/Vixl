"""Brief apply results stay bounded however many layers a batch touches (#679)."""

import json

import pytest

from vixl import Project, VixlError
from vixl.cli_summary import edit


def _texts(count):
    return [{"type": "text", "text": f"Item {i}", "x": i % 700, "y": (i * 7) % 500, "size": 12} for i in range(count)]


def _floats(value):
    if isinstance(value, float):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _floats(item)
    elif isinstance(value, list):
        for item in value:
            yield from _floats(item)


def test_brief_apply_of_1000_layers_is_bounded():
    p = Project(800, 600)
    result = p.apply(_texts(1000), detail="brief")
    assert len(json.dumps(result)) < 15_000
    omitted = result["changes"]["layers_omitted"]
    assert omitted["count"] == 975 and omitted["by_parent"] == {"(top)": 975}
    assert len(omitted["sample"]) == 5 and "compact" in omitted["more"]
    assert sum(1 for entry in result["changes"]["layers"].values() if entry.get("added")) == 25
    assert len(result.get("defaults", [])) <= 25
    assert "added 975 more layers" in edit(result, "apply")


def test_brief_caps_changed_and_removed_layers():
    p = Project(400, 300)
    p.apply(_texts(80), detail="brief")
    moved = p.apply([{"type": "move", "targets": [layer["id"] for layer in p.state["layers"]], "dx": 3}], detail="brief")
    assert moved["changes"]["changed_omitted"]["count"] == 30
    assert sum(1 for entry in moved["changes"]["layers"].values() if "changed" in entry) == 50
    assert "changed 80 layers" in " ".join(edit(moved, "apply"))
    removed = p.apply([{"type": "delete", "targets": [layer["id"] for layer in p.state["layers"]]}], detail="brief")
    assert removed["changes"]["removed_omitted"]["count"] == 30


def test_brief_numbers_are_rounded_and_text_metrics_trimmed():
    p = Project(400, 300)
    result = p.apply(_texts(5), detail="brief")
    assert all(round(value, 2) == value for value in _floats(result["changes"]))
    entry = next(iter(result["changes"]["layers"].values()))
    assert "ink_bounds" in entry and "baseline" in entry
    assert not {"line_bounds", "baselines", "ascent", "descent", "cap_height", "x_height"} & set(entry)


def test_compact_detail_still_lists_everything():
    p = Project(800, 600)
    result = p.apply(_texts(60), detail="compact")
    assert len(result["changes"]["layers"]) == 60 and "layers_omitted" not in result["changes"]
    assert "line_bounds" in next(iter(result["changes"]["layers"].values()))


def _chart(name="c"):
    return {"type": "chart", "name": name, "kind": "bar", "x": 10, "y": 10, "width": 300, "height": 200,
            "data": {"categories": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]}}


def test_generated_children_are_summarised_at_the_parent():  # #615 item 32
    p = Project(400, 300)
    result = p.apply([_chart()], detail="brief")
    layers = result["changes"]["layers"]
    assert len(layers) == 1
    (parent,) = layers.values()
    assert parent["added"] and parent["generated"] == "chart" and parent["children_added"] == 16
    assert len(parent["children_sample"]) == 5
    regenerated = p.apply([{"type": "chart-data", "target": "c", "data": {
        "categories": ["a", "b", "c"], "series": [{"name": "s", "values": [1, 2, 3]}]}}], detail="brief")
    (parent,) = regenerated["changes"]["layers"].values()
    assert parent["generated"] == "chart" and parent["children_added"] == 7 and parent["children_changed"] == 14
    assert not any(entry.get("parent") for entry in regenerated["changes"]["layers"].values())


def test_ack_counts_every_changed_layer():  # #615 item 31
    from vixl.changes import ack

    p = Project(400, 300)
    result = ack(p.apply([_chart(), *_texts(3)], detail="brief"), head=p.head)
    assert set(result) == {"ok", "head", "changed", "warnings"}
    assert result["ok"] is True and result["head"] == p.head and result["changed"] == 20
    assert isinstance(result["warnings"], list)


def test_inspect_summary_trims_text_metrics_and_stays_under_budget():  # #615 (4.3)
    from vixl.changes import summarize

    p = Project(800, 600)
    p.apply([{"type": "text", "text": f"Line number {i} of some longer copy", "x": 20, "y": 10 + i * 14, "size": 12}
             for i in range(40)], detail="brief")
    summary = summarize(p)
    assert len(json.dumps(summary)) < 11_000  # 17,857 characters before the trim
    entry = summary["layers"][0]
    assert "ink_bounds" in entry and "baseline" in entry
    assert not {"line_bounds", "baselines", "ascent", "descent", "cap_height", "x_height", "metrics_space"} & set(entry)
    assert all(round(value, 2) == value for value in _floats(summary["layers"]))
    assert "line_bounds" in p.inspect()["layers"][0]  # the full metrics stay in the verbose inspect


def test_inspect_pagination_projection_collapse_and_filter():  # #615 items 33-35
    from vixl.changes import summarize

    p = Project(800, 600)
    p.apply([_chart(), *_texts(5), {"type": "shape", "shape": "rectangle", "name": "box", "width": 40, "height": 30}],
            detail="brief")
    everything = summarize(p)
    assert everything["layer_count"] == 23 and len(everything["layers"]) == 23 and everything["next_offset"] is None
    page = summarize(p, offset=20, limit=2)
    assert [x["name"] for x in page["layers"]] == [x["name"] for x in everything["layers"][20:22]]
    assert page["layer_count"] == 23 and page["next_offset"] == 22
    assert summarize(p, offset=22, limit=2)["next_offset"] is None
    collapsed = summarize(p, collapse=True)
    assert collapsed["layer_count"] == 7
    chart = next(x for x in collapsed["layers"] if x["name"] == "c")
    assert chart["generated"] == "chart" and chart["children"] == 16
    projected = summarize(p, fields=["bounds"], filter={"type": "text", "parent": "none"})
    assert len(projected["layers"]) == 5 and all(set(x) == {"id", "name", "type", "bounds"} for x in projected["layers"])
    assert [x["name"] for x in summarize(p, filter={"name": "c/bar*"})["layers"]] == ["c/bar s a", "c/bar s b"]
    assert len(summarize(p, filter={"parent": "c"})["layers"]) == 16
    assert summarize(p, filter={"type": "shape", "name": "box"})["layers"][0]["name"] == "box"


def test_inspect_since_lists_the_layers_changed_after_a_revision():  # #615 item 36
    from vixl.changes import summarize

    p = Project(400, 300)
    p.apply(_texts(3), detail="brief")
    head = p.head
    names = {layer["name"]: layer["id"] for layer in p.state["layers"]}
    p.apply([{"type": "move", "target": "text 2", "dx": 5}, {"type": "delete", "target": "text 3"},
             {"type": "shape", "shape": "rectangle", "name": "box", "width": 40, "height": 30}], detail="brief")
    diff = summarize(p, since=head)
    assert diff["since"] == head
    assert {x["name"]: x["change"] for x in diff["layers"]} == {"text 2": "changed", "box": "added"}
    assert diff["removed"] == [{"id": names["text 3"], "name": "text 3"}]
    assert summarize(p, since=p.head)["layers"] == [] and "removed" not in summarize(p, since=p.head)
    with pytest.raises(VixlError, match="Unknown revision"):
        summarize(p, since="rev_nope")
