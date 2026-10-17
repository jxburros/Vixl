"""Crafted inputs must be refused before the work they ask for is done: untrusted input is charged while it is
processed, so a small hostile file fails fast instead of running long."""

import json
import time
import tracemalloc
import zipfile

import pytest

from vixl import Project, VixlError
from vixl.history import patch
from vixl.model import Limits
from vixl.project import MAX_DELTA_CHAIN
from vixl.svg_import import MAX_RASTERIZED, svg_operations

def rewritten(tmp_path, project, edit):
    project.save(tmp_path / "doc.vixl")
    with zipfile.ZipFile(tmp_path / "doc.vixl") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    data = json.loads(files["project.json"])
    edit(data)
    files["project.json"] = json.dumps(data).encode()
    with zipfile.ZipFile(tmp_path / "bad.vixl", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return tmp_path / "bad.vixl"


def boxed():
    p = Project(16, 16)
    p.apply({"type": "solid", "name": "box", "color": "red", "width": 4, "height": 4})
    p.apply({"type": "move", "target": "box", "x": 1, "y": 0})
    return p


def list_delta(order, changes=None):
    return {"$": "o", "s": {"layers": {"$": "l", "k": "id", "o": order, "s": changes or {}}}}


def test_repeated_key_list_delta_is_refused_before_copying(tmp_path):
    p = boxed()
    box = p.layer("box")["id"]
    path = rewritten(tmp_path, p, lambda data: data["nodes"][data["head"]].update(delta=list_delta([box] * 200_000)))
    tracemalloc.start()
    start = time.perf_counter()
    try:
        with pytest.raises(VixlError) as error:
            # A small byte limit keeps the reader's own buffer (sized by the limit) out of the peak.
            Project.load(path, limits=Limits(max_project_bytes=8 * 1024 * 1024))
        elapsed = time.perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert error.value.code == "invalid_project"
    assert "invalid list delta" in str(error.value)
    # Copying the layer 200,000 times takes seconds and hundreds of megabytes.
    assert elapsed < 2.0
    assert peak < 50 * 1024 * 1024


def test_list_delta_key_that_is_neither_kept_nor_added_is_invalid(tmp_path):
    p = boxed()
    path = rewritten(tmp_path, p, lambda data: data["nodes"][data["head"]].update(delta=list_delta(["missing"])))
    with pytest.raises(VixlError) as error:
        Project.load(path)
    assert error.value.code == "invalid_project"
    assert "neither kept nor added" in str(error.value)


def test_list_delta_bounds_and_changes_outside_the_order():
    before = [{"id": "a"}, {"id": "b"}]
    with pytest.raises(VixlError, match="more than 1 items"):
        patch(before, {"$": "l", "k": "id", "o": ["a", "b"], "s": {}}, max_items=1)
    with pytest.raises(VixlError, match="repeats a key"):
        patch(before, {"$": "l", "k": "id", "o": ["a", "a"], "s": {}})
    with pytest.raises(VixlError, match="not in the order"):
        patch(before, {"$": "l", "k": "id", "o": ["a"], "s": {"b": {"$": "o", "s": {}}}})
    assert patch(before, {"$": "l", "k": "id", "o": ["b", "a"], "s": {}}) == before[::-1]


def test_over_long_delta_chain_is_invalid(tmp_path):
    p = Project(16, 16)
    p.apply({"type": "solid", "name": "box", "color": "red", "width": 4, "height": 4})

    def lengthen(data):
        # Turn every snapshot after the root into an empty delta, making one chain of every revision.
        parent = None
        for ident in list(data["nodes"]):
            node = data["nodes"][ident]
            if parent is not None:
                node.pop("state", None)
                node["delta"] = node.get("delta") or {"$": "o", "s": {}}
            parent = ident
        root = next(iter(data["nodes"]))
        last = root
        for index in range(MAX_DELTA_CHAIN + 1):
            ident = f"rev_crafted{index:04d}"
            data["nodes"][ident] = {"id": ident, "parent": last, "operations": [], "label": None,
                                    "delta": {"$": "o", "s": {}}}
            last = ident
        data["head"] = last
        data["redo_stack"] = []
        for name in data.get("branches", {}):
            data["branches"][name] = last

    with pytest.raises(VixlError) as error:
        Project.load(rewritten(tmp_path, p, lengthen))
    assert error.value.code == "invalid_project"
    assert "delta chain" in str(error.value)


def test_oversized_history_snapshot_is_refused_before_reconstruction(tmp_path):
    p = boxed()
    box = p.state["layers"][0]

    def grow(data):
        root = next(iter(data["nodes"].values()))
        root["state"]["layers"] = [dict(box, id=f"lay_{i:06d}") for i in range(5000)]

    with pytest.raises(VixlError) as error:
        Project.load(rewritten(tmp_path, p, grow))
    assert error.value.code == "invalid_project"
    assert "snapshot" in str(error.value)


SVG = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="40" height="40">'


def use_fanout(levels=5, ways=10):
    """A ~1 KB SVG whose ``<use>`` tree expands to ``ways ** levels`` shapes."""
    parts = [SVG, '<defs><rect id="l0" width="1" height="1" fill="#000"/>']
    for level in range(1, levels + 1):
        uses = "".join(f'<use xlink:href="#l{level - 1}"/>' for _ in range(ways))
        parts.append(f'<g id="l{level}">{uses}</g>')
    parts.append(f'</defs><use xlink:href="#l{levels}"/></svg>')
    return "".join(parts).encode()


@pytest.mark.parametrize("fallback", [False, True])
def test_svg_use_fanout_fails_fast(fallback):
    data = use_fanout()
    assert len(data) < 1600
    start = time.perf_counter()
    with pytest.raises(VixlError) as caught:
        svg_operations(data, Project(40, 40), "art", fallback=fallback)
    assert caught.value.code == "resource_limit"
    assert caught.value.details.get("field") == "svg"
    assert time.perf_counter() - start < 5  # it ran for minutes before the expansion was charged


def test_svg_use_within_budget_still_expands():
    operations = svg_operations(use_fanout(levels=2, ways=10), Project(40, 40), "art")
    assert sum(op["type"] == "shape" for op in operations) == 100


def unsupported(count):
    shapes = "".join(f'<rect x="{i % 40}" y="{i // 40}" width="1" height="1" filter="url(#f)"/>' for i in range(count))
    return (f'{SVG}<defs><filter id="f"><feGaussianBlur stdDeviation="0.1"/></filter></defs>{shapes}</svg>').encode()


def test_svg_raster_fallback_is_capped():
    report = {}
    svg_operations(unsupported(MAX_RASTERIZED), Project(40, 40), "art", fallback=True, report=report)
    assert len(report["rasterized"]) == MAX_RASTERIZED
    with pytest.raises(VixlError) as caught:
        svg_operations(unsupported(100), Project(40, 40), "art", fallback=True)
    assert caught.value.code == "resource_limit"
    assert "svg_mode='appearance'" in str(caught.value)
