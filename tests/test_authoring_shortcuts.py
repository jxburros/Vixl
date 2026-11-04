"""Authoring shortcuts (roadmap 4.7 items 48, 57 and 58) produce the same document as their long form."""

import pytest

from vixl import Project, VixlError
from vixl.model import seeded_ids


def _canon(value):
    """``value`` as JSON with every layer id replaced by its order of first appearance, so two documents built the
    same way compare equal whatever ids they drew."""
    import json
    import re

    seen = {}
    renumber = lambda m: seen.setdefault(m.group(0), f"lyr_{len(seen)}")  # noqa: E731
    # Number the ids in layer order first: dicts keyed by id would otherwise sort differently per document.
    re.sub(r"lyr_[0-9a-f]{16}", renumber, json.dumps(value.get("layers", []) if isinstance(value, dict) else value))
    text = re.sub(r"lyr_[0-9a-f]{16}", renumber, json.dumps(value, sort_keys=True))
    return json.dumps(json.loads(text), sort_keys=True)


def _same_document(a, b):
    drop = ("history", "revision", "modified", "updated", "created")
    return _canon({k: v for k, v in a.state.items() if k not in drop}) == _canon(
        {k: v for k, v in b.state.items() if k not in drop})


# --- item 57: entrance, hold and exit presets on motion-define -----------------------------------------------


def _animated(motion):
    with seeded_ids(7):
        p = Project(400, 300)
        p.apply([
            {"type": "shape", "shape": "rectangle", "name": "card-1", "x": 20, "y": 20, "width": 100, "height": 60, "fill": "#345"},
            {"type": "shape", "shape": "rectangle", "name": "card-2", "x": 140, "y": 20, "width": 100, "height": 60, "fill": "#345"},
            {"type": "role-set", "name": "cards", "targets": ["card-1", "card-2"]},
            {"type": "motion-define", "name": "reveal", "motion": motion},
            {"type": "motion-apply", "name": "reveal"},
        ])
    return p


LONG = {"steps": [
    {"id": "entrance", "role": "cards", "preset": "fade-in", "duration": "400ms", "stagger": "100ms"},
    {"id": "exit", "role": "cards", "preset": "fade-out", "duration": "400ms", "stagger": "100ms", "after": "entrance", "start": "2s"},
]}
SHORT = {"role": "cards", "entrance": "fade-in", "hold": "2s", "exit": "fade-out", "duration": "400ms", "stagger": "100ms"}


def test_motion_entrance_hold_exit_shorthand_matches_explicit_steps():
    short, long = _animated(SHORT), _animated(LONG)
    assert short.state["motions"]["reveal"] == LONG  # saved as the long form, no shorthand record
    assert _same_document(short, long)
    times = sorted({k["time"] for k in t["keys"]} for t in short.state["timeline"]["tracks"])
    assert {0, 400, 2500, 2900} <= times[0] and {100, 500, 2600, 3000} <= times[1]  # entrance, 2 s hold, staggered exit


def test_motion_hold_preset_plays_between_entrance_and_exit():
    short = _animated({"role": "cards", "entrance": "pop-in", "hold": {"preset": "pulse", "duration": "1s"},
                       "exit": "pop-out", "duration": "300ms"})
    long = _animated({"steps": [
        {"id": "entrance", "role": "cards", "preset": "pop-in", "duration": "300ms"},
        {"id": "hold", "role": "cards", "preset": "pulse", "duration": "1s", "after": "entrance"},
        {"id": "exit", "role": "cards", "preset": "pop-out", "duration": "300ms", "after": "hold"},
    ]})
    assert short.state["motions"]["reveal"] == long.state["motions"]["reveal"]
    assert _same_document(short, long)
    short = _animated({"role": "cards", "entrance": "fade-in", "hold": "float", "exit": "fade-out"})
    assert [s["id"] for s in short.state["motions"]["reveal"]["steps"]] == ["entrance", "hold", "exit"]
    assert short.state["motions"]["reveal"]["steps"][1]["preset"] == "float"


def test_motion_shorthand_rejects_wrong_presets_and_needs_a_role():
    with pytest.raises(VixlError, match="entrance is one of"):
        _animated({"role": "cards", "entrance": "fade-out"})
    with pytest.raises(VixlError, match="exit is one of"):
        _animated({"role": "cards", "exit": "fade-in"})
    with pytest.raises(VixlError, match="needs a role"):
        _animated({"entrance": "fade-in"})
    # Explicit steps may follow the shorthand ones and depend on them.
    p = _animated({"role": "cards", "entrance": "fade-in", "hold": "1s", "exit": "fade-out",
                   "steps": [{"role": "cards", "property": "translate-y", "from": 0, "to": -10, "after": "exit"}]})
    assert [s["id"] for s in p.state["motions"]["reveal"]["steps"][:2]] == ["entrance", "exit"]
    assert len(p.state["motions"]["reveal"]["steps"]) == 3 and p.state["motions"]["reveal"]["steps"][1]["start"] == "1s"


# --- item 48: one container per data row ---------------------------------------------------------------------

ROWS = [{"title": "Doors open", "body": "Seven o'clock sharp."}, {"title": "Music", "body": "Two bands, one stage."},
        {"title": "Food", "body": "Six trucks on the pier."}]


def _rows(operations):
    with seeded_ids(3):
        p = Project(1200, 900)
        p.apply([{"type": "palette-apply", "name": "slate"}, *operations])
    return p


def test_container_rows_matches_one_container_place_per_row():
    short = _rows([{"type": "container-rows", "name": "note", "resource": "callout", "rows": ROWS, "x": 60, "y": 40,
                    "gap": 24, "seed": 5, "variables": {"icon": "!"}}])
    item = short.layer("note-1")["container"]["base_size"]
    long = _rows([{"type": "container-place", "name": f"note-{i + 1}", "resource": "callout", "seed": 5, "x": 60,
                   "y": 40 + i * (item[1] + 24), "variables": {"icon": "!", **row}} for i, row in enumerate(ROWS)])
    assert _same_document(short, long)
    assert [layer["name"] for layer in short.inspect()["layers"] if layer["type"] == "group"] == ["note-1", "note-2", "note-3"]
    assert short.layer("note-3/title")["text"] == "Food"
    assert "container-rows" not in str(short.inspect()["layers"])  # expanded: only ordinary containers remain


def test_container_rows_run_horizontally_and_wrap_into_a_grid():
    p = _rows([{"type": "container-rows", "name": "card", "resource": "callout", "rows": ROWS, "direction": "horizontal",
                "columns": 2, "gap": 10, "seed": 1, "width": 300, "height": 200}])
    bounds = [p.layer(f"card-{i}")["x"] for i in (1, 2, 3)], [p.layer(f"card-{i}")["y"] for i in (1, 2, 3)]
    assert bounds == ([0, 310, 0], [0, 0, 210])
    with pytest.raises(VixlError, match="direction"):
        _rows([{"type": "container-rows", "name": "c", "resource": "callout", "rows": ROWS, "direction": "diagonal"}])
    with pytest.raises(VixlError, match="rows"):
        _rows([{"type": "container-rows", "name": "c", "resource": "callout", "rows": []}])


# --- item 58: pixel-art run-length rows, mirror and frame deltas ---------------------------------------------

PALETTE = {".": "transparent", "g": "#ffc44d", "s": "#9c5f22"}
COIN = ["..ssss..", ".sggggs.", "sggggggs", "sggggggs", "sggggggs", "sggggggs", ".sggggs.", "..ssss.."]


def _sprite(operations):
    with seeded_ids(11):
        p = Project(8, 8, "transparent")
        p.apply(operations)
    return p


def test_run_length_rows_expand_to_the_literal_rows():
    short = _sprite([{"type": "pixel-art", "name": "coin", "palette": PALETTE,
                      "rows": ["2.4s2.", ".s4gs.", "s6gs", "s6gs", "s6gs", "s6gs", ".s4gs.", "2.4s2."]}])
    long = _sprite([{"type": "pixel-art", "name": "coin", "palette": PALETTE, "rows": COIN}])
    assert short.layer("coin")["pixels"] == COIN and _same_document(short, long)
    # A palette that uses digits as symbols keeps its rows literal.
    p = _sprite([{"type": "pixel-art", "name": "digits", "palette": {"1": "#111", "2": "#222"}, "rows": ["12", "21"]}])
    assert p.layer("digits")["pixels"] == ["12", "21"]
    with pytest.raises(VixlError, match="run count needs a palette symbol"):
        _sprite([{"type": "pixel-art", "name": "bad", "palette": PALETTE, "rows": ["3"]}])


def test_mirror_completes_the_other_half():
    half = [row[:4] for row in COIN]
    short = _sprite([{"type": "pixel-art", "name": "coin", "palette": PALETTE, "rows": half, "mirror": "x"}])
    long = _sprite([{"type": "pixel-art", "name": "coin", "palette": PALETTE, "rows": COIN}])
    assert short.layer("coin")["pixels"] == COIN and _same_document(short, long)
    quarter = [row[:4] for row in COIN[:4]]
    both = _sprite([{"type": "pixel-art", "name": "coin", "palette": PALETTE, "rows": quarter, "mirror": "xy"}])
    assert both.layer("coin")["pixels"] == COIN
    # An odd width: the last given column is the centre line.
    odd = _sprite([{"type": "pixel-art", "name": "arrow", "palette": PALETTE, "rows": ["..g", ".gg", "ggg"],
                    "mirror": "x", "width": 5}])
    assert odd.layer("arrow")["pixels"] == ["..g..", ".ggg.", "ggggg"]
    with pytest.raises(VixlError, match="width is 8 or 7"):
        _sprite([{"type": "pixel-art", "name": "bad", "palette": PALETTE, "rows": half, "mirror": "x", "width": 6}])


def test_frame_delta_matches_drawing_the_changed_cells():
    base = [{"type": "pixel-art", "name": "coin", "palette": PALETTE, "rows": COIN, "shading": False, "outline": False},
            {"type": "frame-save", "name": "idle", "duration": 150}]
    short = _sprite([*base, {"type": "pixel-draw", "target": "coin", "rows": {"2": "sggssggs"},
                             "cells": [[3, 4, "s"], [4, 4, "s"]]},
                     {"type": "frame-save", "name": "glint", "duration": 100}])
    long = _sprite([*base, {"type": "pixel-draw", "target": "coin", "tool": "pixel", "x": 3, "y": 2, "color": "s"},
                    {"type": "pixel-draw", "target": "coin", "tool": "pixel", "x": 4, "y": 2, "color": "s"},
                    {"type": "pixel-draw", "target": "coin", "tool": "line", "x": 3, "y": 4, "x2": 4, "y2": 4, "color": "s"},
                    {"type": "frame-save", "name": "glint", "duration": 100}])
    assert short.layer("coin")["pixels"][2] == "sggssggs" and short.layer("coin")["pixels"][4] == "sggssggs"
    assert _same_document(short, long)
    # Run-length rows work in a delta too, and bad indexes or symbols are refused.
    p = _sprite([*base, {"type": "pixel-draw", "target": "coin", "rows": {"0": "8s"}}])
    assert p.layer("coin")["pixels"][0] == "ssssssss"
    with pytest.raises(VixlError, match="outside the grid"):
        _sprite([*base, {"type": "pixel-draw", "target": "coin", "rows": {"8": "8s"}}])
    with pytest.raises(VixlError, match="palette entry"):
        _sprite([*base, {"type": "pixel-draw", "target": "coin", "cells": [[0, 0, "?"]]}])
    with pytest.raises(VixlError, match="replace tool"):
        _sprite([*base, {"type": "pixel-draw", "target": "coin", "cells": [[0, 0, "s"]], "x": 1, "y": 1, "color": "s"}])
