"""Per-frame setup (#586): ``project_at`` shares the layers a frame does not change with the document instead of
deep-copying the whole state, and render paths leave out top-level subtrees that draw nothing at that time
(inactive lyric cues). Both must leave the document untouched and draw exactly the same pixels."""

import json

import numpy as np
import pytest

from vixl import Project
from vixl import render as R
from vixl.timeline import export_timeline, project_at, prune_hidden, render_at


def pixels(image):
    return np.asarray(image).astype(int)


def reference(p, time):
    """The frame without pruning, rendered with an empty cache."""
    frame = project_at(p, time)
    frame._cache = None
    return R.render(frame)


def lyric_film(cues=12, extra=0):
    """A lyric-film shape: a static background and header, then one group per cue that is shown only during its
    cue (stepped visibility) and whose words fade and drift while it is up."""
    p = Project(640, 360, "#101820")
    ops = [{"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 0, "width": 640, "height": 40,
            "fill": "#334"},
           {"type": "text", "name": "header", "text": "Friends", "size": 22, "x": 12, "y": 6, "color": "white"},
           {"type": "timeline-set", "duration": cues * 500}]
    for i in range(cues):
        ops += [{"type": "text", "name": f"line{i}", "text": f"Line number {i}", "size": 36, "x": 60, "y": 150,
                 "color": "#ffd"},
                {"type": "shape", "shape": "star", "name": f"star{i}", "x": 500, "y": 140, "width": 50, "height": 50,
                 "fill": "gold"}]
    ops += [{"type": "shape", "shape": "rectangle", "name": f"filler{i}", "x": 10 + (i % 20) * 30, "y": 300,
             "width": 20, "height": 20, "fill": "#246"} for i in range(extra)]
    p.apply(ops, detail="brief")
    p.apply([{"type": "group", "targets": [f"line{i}", f"star{i}"], "name": f"cue{i}"} for i in range(cues)],
            detail="brief")
    keys = []
    for i in range(cues):
        start = i * 500
        visible = [{"time": 0, "value": False}] if start else []
        visible += [{"time": start, "value": True}, {"time": start + 500, "value": False}]
        keys += [{"type": "keyframes", "target": f"cue{i}", "property": "visible", "keys": visible},
                 {"type": "keyframes", "target": f"star{i}", "property": "y",
                  "keys": [{"time": start, "value": 140}, {"time": start + 500, "value": 100}]},
                 {"type": "keyframes", "target": f"line{i}", "property": "opacity",
                  "keys": [{"time": start, "value": 0}, {"time": start + 250, "value": 1}]}]
    p.apply(keys, detail="brief")
    return p


def test_a_frame_shares_the_layers_it_does_not_change():
    p = lyric_film()
    frame = project_at(p, 260)
    shared = {layer["id"] for layer in frame.state["layers"]} & {layer["id"] for layer in p.state["layers"]}
    own = [layer for layer, base in zip(frame.state["layers"], p.state["layers"]) if layer is not base]
    assert len(shared) == len(p.state["layers"])
    # Only the animated layers (each cue's group, star and line) are the frame's own copies.
    assert {layer["name"] for layer in own} <= {f"{kind}{i}" for kind in ("cue", "star", "line") for i in range(12)}
    assert p.layer("band") is frame.layer("band")


def test_frames_never_change_the_document():
    p = lyric_film(4)
    p.apply([{"type": "text-animate", "target": "header", "preset": "fade-down", "unit": "char", "duration": 800},
             {"type": "keyframe", "target": "canvas", "property": "background", "time": 0, "value": "#000000"},
             {"type": "keyframe", "target": "canvas", "property": "background", "time": 2000, "value": "#203040"},
             {"type": "keyframe", "target": "header", "property": "rotation", "time": 0, "value": 0},
             {"type": "keyframe", "target": "header", "property": "rotation", "time": 2000, "value": 90},
             {"type": "keyframe", "target": "band", "property": "scale", "time": 0, "value": 1},
             {"type": "keyframe", "target": "band", "property": "scale", "time": 2000, "value": 0.5},
             {"type": "particles", "name": "sparks", "preset": "sparks", "count": 3, "x": 30, "y": 20,
              "spread": [0, 0], "velocity": [10, 0], "gravity": 100, "life": 2000, "duration": 1000,
              "turbulence": 0, "seed": 12},
             {"type": "character", "name": "hero", "x": 300, "y": 60},
             {"type": "character-lipsync", "target": "hero", "text": "anything", "duration": 1000,
              "cues": [{"time": 0, "viseme": "M"}, {"time": 500, "viseme": "O"}]}], detail="brief")
    before = json.dumps(p.state, sort_keys=True, default=str)
    for time in range(0, 2001, 125):
        render_at(p, time)
        project_at(p, time, prune=True)
    p.apply({"type": "camera", "from": [0, 0, 1], "to": [40, 0, 1], "duration": 1000}, detail="brief")
    before = json.dumps(p.state, sort_keys=True, default=str)
    for time in range(0, 2001, 250):
        render_at(p, time)
    assert json.dumps(p.state, sort_keys=True, default=str) == before


def test_pruned_frames_draw_the_same_pixels():
    p = lyric_film()
    for time in (0, 120, 260, 499, 500, 1730, 2900, 5999):
        frame = project_at(p, time, prune=True)
        assert len(frame.state["layers"]) < 10  # band, header and at most the one active cue (or two at a cut)
        assert np.array_equal(pixels(render_at(p, time)), pixels(reference(p, time)))


def test_a_hidden_layer_something_refers_to_is_not_left_out():
    p = lyric_film(3)
    # The band follows line0's top edge: line0 (hidden after its cue) still sets where the band is.
    p.apply({"type": "constrain", "target": "band", "constraints": {"top": "cue0.bottom+4"}}, detail="brief")
    frame = project_at(p, 1200, prune=True)
    assert frame.layer("cue0") is not None
    assert np.array_equal(pixels(render_at(p, 1200)), pixels(reference(p, 1200)))


def test_prune_keeps_documents_that_reselect_layers():
    p = lyric_film(3)
    state = dict(p.state, layers=list(p.state["layers"]), comps={"alt": {}})
    for layer in state["layers"]:
        if layer["name"] == "cue1":
            state["layers"][state["layers"].index(layer)] = {**layer, "visible": False}
    assert prune_hidden(state) == set()


@pytest.mark.perf
def test_sixty_frames_of_setup_on_a_large_document():
    import time

    p = lyric_film(cues=37, extra=600)
    times = [i * 300 for i in range(60)]
    from copy import deepcopy

    def best(work):
        runs = []
        for _ in range(3):
            start = time.perf_counter()
            for t in times:
                work(t)
            runs.append(time.perf_counter() - start)
        return min(runs)

    elapsed = best(lambda t: project_at(p, t, prune=True))
    copying = best(lambda t: deepcopy(p.state))
    # Each frame used to deep-copy the whole document and then sample and measure it: about 7x the cost of the copy
    # alone. Sharing and pruning keep setup near one copy (0.6x to 1.2x across CI runners); 2x leaves room for
    # machines where deepcopy is fast while still failing a return to copy-sample-measure.
    assert elapsed < 2 * copying and elapsed < 6


@pytest.mark.perf
def test_a_sixty_frame_export_matches_frame_by_frame_renders(tmp_path):
    import time

    from PIL import Image

    p = lyric_film(cues=6, extra=300)
    start = time.perf_counter()
    export_timeline(p, tmp_path / "frames.zip", format="frames", fps=20)
    elapsed = time.perf_counter() - start
    # About 4 s (7 s before frames shared their layers and left out inactive cues).
    assert elapsed < 40
    import zipfile

    with zipfile.ZipFile(tmp_path / "frames.zip") as archive:
        names = sorted(name for name in archive.namelist() if name.startswith("frame_"))
        assert len(names) == 60
        for index in (0, 13, 31, 59):
            with archive.open(names[index]) as stream:
                image = Image.open(stream).convert("RGBA")
                assert np.array_equal(pixels(image), pixels(reference(p, index * 50)))
