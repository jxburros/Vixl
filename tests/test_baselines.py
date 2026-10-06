"""Baseline positioning: baseline_y, the baseline anchor for align/snap, and baseline grids (#186)."""

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.geometry import ANCHORS, canonical_anchor


def baseline(project, name):
    return project.inspect(name)["baseline"]


def test_baseline_y_places_the_first_baseline_on_create_edit_and_move():
    p = Project(600, 400, "white")
    p.apply({"type": "text", "name": "t", "text": "Hello\nWorld", "size": 40, "x": 20, "baseline_y": 100})
    assert baseline(p, "t") == pytest.approx(100, abs=0.01)
    lines = p.inspect("t")["baselines"]
    assert len(lines) == 2 and lines[1] > lines[0]  # the first line is the one placed
    p.apply({"type": "text-set", "target": "t", "size": 72, "baseline_y": 150})
    assert baseline(p, "t") == pytest.approx(150, abs=0.01)
    p.apply({"type": "move", "target": "t", "baseline_y": 200})
    assert baseline(p, "t") == pytest.approx(200, abs=0.01) and p.layer("t")["x"] == 20
    p.apply({"type": "text", "target": "t", "text": "Changed", "baseline_y": 220})
    assert baseline(p, "t") == pytest.approx(220, abs=0.01)


def test_baseline_y_with_mixed_fonts_uses_the_measured_first_line():
    p = Project(600, 300, "white")
    p.apply({"type": "rich-text", "name": "r", "markdown": "small **BIG** text", "size": 30, "x": 10, "y": 10})
    p.apply({"type": "text-style", "target": "r", "match": "BIG", "size": 70})
    p.apply({"type": "move", "target": "r", "baseline_y": 180})
    assert baseline(p, "r") == pytest.approx(180, abs=0.01)


def test_baseline_y_rejects_conflicts_and_non_text_layers():
    p = Project(400, 200, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hi", "size": 30},
             {"type": "shape", "shape": "rectangle", "name": "box", "width": 40, "height": 40}])
    with pytest.raises(VixlError, match="not both"):
        p.apply({"type": "move", "target": "t", "y": 10, "baseline_y": 50})
    with pytest.raises(VixlError, match="baselines belong to text layers"):
        p.apply({"type": "move", "target": "box", "baseline_y": 50})
    with pytest.raises(VixlError, match="relative"):
        p.apply({"type": "move", "target": "t", "x": 5, "relative": True, "baseline_y": 50})


def test_align_baselines_of_different_sizes():
    p = Project(800, 300, "white")
    p.apply([{"type": "text", "name": "big", "text": "Big", "size": 90, "x": 10, "y": 40},
             {"type": "text", "name": "small", "text": "small", "size": 24, "x": 300, "y": 10},
             {"type": "shape", "shape": "rectangle", "name": "box", "x": 500, "y": 10, "width": 40, "height": 40}])
    p.apply({"type": "align", "targets": ["big", "small"], "alignment": "baseline"})
    assert baseline(p, "small") == pytest.approx(baseline(p, "big"), abs=0.01)
    assert p.layer("big")["y"] == 40 and p.layer("small")["x"] == 300  # the first target sets the line
    p.apply({"type": "align", "target": "big", "alignment": "baseline", "relative_to": "small"})
    assert baseline(p, "small") == pytest.approx(baseline(p, "big"), abs=0.01)
    with pytest.raises(VixlError, match="baselines belong to text layers"):
        p.apply({"type": "align", "targets": ["big", "box"], "alignment": "baseline"})
    with pytest.raises(VixlError, match="relative_to a text layer"):
        p.apply({"type": "align", "target": "big", "alignment": "baseline"})


def test_snap_baselines_to_a_baseline_grid():
    p = Project(600, 600, "white")
    p.apply([{"type": "grid", "kind": "baseline", "name": "base", "spacing": 24, "offset": 24},
             {"type": "text", "name": "t", "text": "Grid", "size": 30, "x": 20, "baseline_y": 101}])
    p.apply({"type": "snap", "targets": ["t"], "anchors": ["baseline"], "tolerance": 6})
    assert baseline(p, "t") == pytest.approx(96, abs=0.01)
    p.apply({"type": "move", "target": "t", "baseline_y": 140})
    p.apply({"type": "snap", "targets": ["t"], "anchors": ["first-baseline"], "tolerance": 6})
    assert baseline(p, "t") == pytest.approx(144, abs=0.01)
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 300, "width": 30, "height": 30})
    with pytest.raises(VixlError, match="baselines belong to text layers"):
        p.apply({"type": "snap", "targets": ["box"], "anchors": ["baseline"]})


def test_baseline_is_not_a_box_anchor():
    assert "baseline" not in ANCHORS and canonical_anchor("baseline") is None
    assert canonical_anchor("Baseline", baseline=True) == "baseline"
    p = Project(200, 200, "white")
    p.apply({"type": "text", "name": "t", "text": "Hi", "size": 30})
    with pytest.raises(VixlError):
        p.apply({"type": "pivot", "target": "t", "value": "baseline"})
