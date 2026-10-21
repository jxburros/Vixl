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


def test_composition_check_on_scattered_labels():
    import random

    rng = random.Random(1)
    p = Project(4000, 4000, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": "Label", "size": 14, "color": "black",
              "x": rng.randint(0, 3800), "y": rng.randint(0, 3900)} for i in range(1500)], detail="brief")
    # The first version took over 10 minutes: free rectangles split by every scattered label, and every pair of
    # labels compared for drift (now under half a second, with at most 12 findings of each kind).
    elapsed, report = timed(lambda: p.check(checks=["composition"]))
    drift = [x for x in report["issues"] if x.get("code") == "margin_drift"]
    assert len(drift) == 12 and drift[-1].get("omitted", 0) > 0
    assert elapsed < 8


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


def test_rendering_styled_layers_on_a_large_canvas_after_a_move():
    p = Project(4000, 4000, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"c{i}", "x": (i % 10) * 380 + 100,
              "y": (i // 10) * 380 + 100, "width": 120, "height": 120, "fill": "#e63"} for i in range(80)],
            detail="brief")
    p.apply({"type": "look", "look": "soft-shadow", "targets": [f"c{i}" for i in range(80)]}, detail="brief")
    p.render()
    p.apply({"type": "move", "target": "c0", "x": 140, "y": 150}, detail="brief")
    # Before this change: about 3 s, a canvas-sized tile styled again for every styled layer (now under 0.1 s: the
    # styled pixels are cached and only the moved layer's neighbourhood is composited again).
    elapsed, _ = timed(p.render)
    assert elapsed < 1


def test_full_canvas_opaque_multiply():
    from PIL import Image
    from vixl.render import composite

    bottom = Image.new('RGBA', (2048, 2048), (210, 130, 20, 255))
    top = Image.new('RGBA', bottom.size, (130, 200, 240, 255))
    elapsed, results = timed(lambda: [composite(bottom, top, 'multiply') for _ in range(4)])
    assert all(result.getpixel((0, 0))[3] == 255 for result in results)
    assert elapsed < 1.5


def test_full_canvas_dithered_linear_gradient():
    from vixl.design_render import gradient_image

    p = Project(2400, 2400, "white")
    for direction in ("vertical", "horizontal"):
        layer = {"type": "gradient", "direction": direction, "start": "#20242a", "end": "#2c3138"}
        # Dithering every pixel took about 0.1 s; a linear ramp is one row of colours and a 64 px dither period,
        # now under 10 ms.
        elapsed, image = timed(lambda: gradient_image(p, layer, (2400, 2400)))
        assert image.size == (2400, 2400)
        assert elapsed < 0.1


def test_small_edit_on_2000_layers_through_session(tmp_path, monkeypatch):  # #630
    import hashlib
    from pathlib import Path

    from vixl.interfaces import Session

    p = Project(4000, 3000)
    p.apply([{"type": "shape", "shape": "rectangle", "name": f"r{i}", "x": i % 400 * 10, "y": i // 400 * 10,
              "width": 8, "height": 8, "fill": "red"} for i in range(2000)], detail="brief")
    import io

    from PIL import Image

    noise = io.BytesIO()
    Image.effect_noise((64, 64), 60).convert("RGB").save(noise, format="PNG")
    p.import_image(data=noise.getvalue(), name="logo")
    p.save(tmp_path / "big.vixl")
    session = Session(workspace=tmp_path)
    move = [{"type": "move", "target": "r5", "x": 1, "relative": True}]
    session.apply(move, document="big.vixl", detail="brief")
    reads, hashed = [], []
    real_read, real_sha = Path.read_bytes, hashlib.sha256

    def read_bytes(self):
        reads.append(self.name)
        return real_read(self)

    def sha256(data=b"", **kwargs):
        hashed.append(len(data))
        return real_sha(data, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(hashlib, "sha256", sha256)
    elapsed, _ = timed(lambda: session.apply(move, document="big.vixl", detail="brief"))
    # The save neither reads the file back to hash it nor re-hashes the unchanged image asset.
    assert "big.vixl" not in reads and not any(size > 1000 for size in hashed)
    assert elapsed < 2.5  # About 0.5 s; before #630 about 0.9 s.
