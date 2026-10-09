"""Time budgets for the paths that used to grow with the size of the document (``pytest -m perf``).

Each budget is several times what the current code needs on a loaded CI runner, and far below what the old,
pathological code took, so a regression to it fails without the test being flaky."""

import time

import pytest

from vixl import Project

pytestmark = pytest.mark.perf


def timed(function):
    start = time.perf_counter()
    result = function()
    return time.perf_counter() - start, result


def test_one_move_on_4096_layers():  # #284, #300
    p = Project(4000, 4000, "white")
    ops = []
    for i in range(4096):
        x, y = (i % 64) * 60, (i // 64) * 60
        if i % 4 == 0:
            ops.append({"type": "text", "name": f"t{i}", "text": f"Label {i}", "size": 14, "x": x, "y": y,
                        "color": "black"})
        else:
            ops.append({"type": "shape", "shape": "rectangle", "name": f"s{i}", "x": x, "y": y, "width": 40,
                        "height": 40, "fill": "#336699"})
    p.apply(ops, detail="brief")
    # Before 0.23: about 9 s (now under 1 s). Every apply re-measured each text layer several times, each time
    # scanning every layer for form fields, and inspected the whole document twice.
    elapsed, result = timed(lambda: p.apply({"type": "move", "target": "s1", "x": 5, "y": 5}, detail="brief"))
    assert set(result["changes"]["layers"]) == {p.layer("s1")["id"]}
    assert elapsed < 4


def test_a_batch_of_moves_costs_no_full_layout_per_operation():  # #284
    p = Project(4000, 4000, "white")
    ops = [{"type": "shape", "shape": "rectangle", "name": f"s{i}", "x": (i % 64) * 60, "y": (i // 64) * 60,
            "width": 40, "height": 40} for i in range(1000)]
    ops += [{"type": "move", "target": f"s{i % 1000}", "x": i % 3000, "y": 7} for i in range(3000)]
    # Before 0.23: about 50 s, each move resolving all 1,000 layers (now about 1 s).
    elapsed, _ = timed(lambda: p.apply(ops, detail="brief"))
    assert elapsed < 8


def test_overlap_check_on_dense_text():  # #327
    p = Project(6000, 6000, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": f"Overlapping label {i}", "size": 20, "color": "black",
              "x": (i % 15) * 100, "y": (i // 15) * 18} for i in range(300)], detail="brief")
    # Before 0.23: about 30 s, a 6000×6000 surface for every text layer (now about 1 s).
    elapsed, report = timed(lambda: p.check(checks=["overlap"]))
    assert any(issue["check"] == "overlap" for issue in report["issues"])
    assert elapsed < 6


def test_a_100k_character_text_flow():  # #335
    p = Project(1900, 1900, "white")
    # Before 0.23: about 5 minutes for one 100,000-character word (now about 6 s).
    elapsed, _ = timed(lambda: p.apply({"type": "text-flow", "name": "s", "text": "a" * 100000, "size": 8,
                                         "x": 0, "y": 0, "width": 1900, "height": 1900, "columns": 4},
                                        detail="brief"))
    assert len(p.state["layers"]) == 4
    assert elapsed < 40


def test_poster_design_check_budget():  # #504
    p = Project(1080, 1920, 'white')
    p.apply({'type': 'layout-apply', 'name': 'quiet-editorial', 'seed': 1,
             'title': 'One useful idea to share', 'subtitle': 'A clear explanation of the main point',
             'body': 'Supporting information for everyone. ' * 8})
    elapsed, report = timed(p.check)
    assert 'contrast' in report['checked']['checks']
    assert elapsed < 4
