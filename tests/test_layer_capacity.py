"""Documents with thousands of layers: the limit, the indexed layer lookup and the overlap prefilter."""

import random

import pytest

from vixl import Project
from vixl.checks import _intersects, overlap_candidates
from vixl.errors import VixlError
from vixl.model import MAX_LAYERS, Limits
from vixl.schema import operation_schema
from vixl.targets import MAX_TARGETS


def shapes(count, start=0):
    return [{"type": "shape", "shape": "rectangle", "name": f"s{start + i}", "width": 4, "height": 4,
             "x": (start + i) % 200, "y": (start + i) // 200 * 5, "fill": "red"} for i in range(count)]


def test_layer_limit_is_4096_and_layer_lists_share_it():
    assert Limits().max_layers == MAX_LAYERS == MAX_TARGETS == 4096
    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    for kind in ("group", "distribute", "stack", "look", "cut-paper", "motion", "suite-capture", "opacity", "irregular"):
        assert variants[kind]["properties"]["targets"]["maxItems"] == MAX_LAYERS, kind


def test_more_than_512_layers_apply_save_and_load(tmp_path):
    p = Project(200, 200)
    p.apply(shapes(700))
    p.apply({"type": "group", "name": "all", "targets": [f"s{i}" for i in range(600)]})
    assert len(p.state["layers"]) == 701
    p.save(tmp_path / "many.vixl")
    loaded = Project.load(tmp_path / "many.vixl")
    assert len(loaded.state["layers"]) == 701
    assert loaded.layer("s650").get("parent") is None and loaded.layer("s5")["parent"] == loaded.layer("all")["id"]


def test_layer_limit_is_enforced():
    p = Project(200, 200, limits=Limits(max_layers=5))
    p.apply(shapes(5))
    with pytest.raises(VixlError, match="Layer limit"):
        p.apply(shapes(1, 5))


def test_indexed_lookup_follows_renames_reorders_and_removals():
    p = Project(200, 200)
    p.apply(shapes(6))
    first = p.layer("s1")
    p.apply({"type": "rename", "target": "s1", "name": "renamed"})
    assert p.layer("renamed")["id"] == first["id"]
    with pytest.raises(VixlError, match="does not exist"):
        p.layer("s1")
    p.apply([{"type": "top", "target": "s0"}, {"type": "remove", "target": "s3"}])
    assert p.layer("s0") is p.state["layers"][-1]
    assert p.layer(first["id"])["name"] == "renamed"
    with pytest.raises(VixlError):
        p.layer("s3")
    # Edits made directly to the list (as operations do) are seen too.
    p.state["layers"][0]["name"] = "direct"
    assert p.layer("direct") is p.state["layers"][0]
    p.state["layers"].reverse()
    assert p.layer("direct") is p.state["layers"][-1]
    with pytest.raises(VixlError, match="already exists"):
        p.apply({"type": "rename", "target": "s2", "name": "direct"})


def test_default_names_count_on_within_a_batch_and_fill_gaps_across_batches():
    p = Project(200, 200)
    p.apply([{"type": "shape", "shape": "rectangle", "width": 4, "height": 4}] * 4)
    assert [x["name"] for x in p.state["layers"]] == ["shape", "shape 2", "shape 3", "shape 4"]
    p.apply({"type": "remove", "target": "shape 2"})
    p.apply({"type": "shape", "shape": "rectangle", "width": 4, "height": 4})
    assert p.state["layers"][-1]["name"] == "shape 2"


def test_overlap_prefilter_finds_every_pair_brute_force_finds():
    rng = random.Random(3)
    boxes = [(rng.randint(-50, 400), rng.randint(-50, 400), rng.randint(1, 80), rng.randint(1, 80)) for _ in range(300)]
    texts = [rng.random() < 0.2 for _ in boxes]
    clamp = [(max(0, x), max(0, y), min(400, x + w) - max(0, x), min(400, y + h) - max(0, y)) for x, y, w, h in boxes]
    expected = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
                if (texts[i] or texts[j]) and clamp[i][2] > 0 and clamp[i][3] > 0 and clamp[j][2] > 0 and clamp[j][3] > 0
                and _intersects(clamp[i], clamp[j])]
    assert overlap_candidates(boxes, texts, 400, 400) == expected


def test_overlap_check_still_reports_text_over_a_shape_among_many_shapes():
    p = Project(400, 400)
    p.apply(shapes(800))
    p.apply({"type": "text", "name": "label", "text": "Hello", "size": 20, "x": 2, "y": 0})
    report = p.check(checks=["overlap"])
    assert any(issue["check"] == "overlap" and "label" in issue["layers"] for issue in report["issues"])
