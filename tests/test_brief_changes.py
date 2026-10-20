"""Brief apply results stay bounded however many layers a batch touches (#679)."""

import json

from vixl import Project
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
