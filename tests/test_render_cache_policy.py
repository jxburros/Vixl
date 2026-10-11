"""Render caches across processes and calls (#592) and the whole-frame write policy of sequences (#607)."""

import json

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl import render as R
from vixl import render_cache
from vixl.cli import main


def pixels(image):
    return np.asarray(image.convert("RGBA")).astype(int)


def moving(path):
    """A saved document with a static full-frame grain background, a header and a symbol that never stops."""
    p = Project(320, 180, "#203040")
    p.apply([{"type": "solid", "name": "paper", "color": "#e8e0d0"},
             {"type": "grain", "target": "paper", "amount": 0.08},
             {"type": "text", "name": "header", "text": "Header", "size": 20, "x": 10, "y": 8, "color": "black"},
             {"type": "shape", "shape": "star", "name": "spark", "x": 20, "y": 90, "width": 40, "height": 40,
              "fill": "tomato"},
             {"type": "timeline-set", "duration": 1000},
             {"type": "keyframe", "target": "spark", "property": "x", "time": 0, "value": 20},
             {"type": "keyframe", "target": "spark", "property": "x", "time": 1000, "value": 260},
             {"type": "keyframe", "target": "spark", "property": "scale", "time": 0, "value": 1},
             {"type": "keyframe", "target": "spark", "property": "scale", "time": 1000, "value": 1.5}],
            detail="brief")
    p.save(path)
    return Project.load(path)


def frame_pixels(path):
    import zipfile

    with zipfile.ZipFile(path) as archive:
        names = sorted(name for name in archive.namelist() if name.startswith("frame_"))
        return [pixels(Image.open(archive.open(name))) for name in names]


def pngs(directory):
    return sorted(directory.glob("*.png")) if directory.exists() else []


def test_a_reloaded_document_keeps_its_render_caches(tmp_path):
    from vixl.interfaces import Session

    p = Project(200, 120, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "a", "x": 10, "y": 10, "width": 80, "height": 60,
              "fill": "#c30"},
             {"type": "shape", "shape": "star", "name": "b", "x": 100, "y": 30, "width": 60, "height": 60}],
            detail="brief")
    p.save(tmp_path / "doc.vixl")
    session = Session(workspace=tmp_path)
    session.open("doc.vixl")
    with session.project() as first:
        first.render()
        cache = first._cache
        assert len(cache) > 0
    # Another process changes the file: the session reloads it, with the caches it had.
    other = Project.load(tmp_path / "doc.vixl")
    other.apply({"type": "move", "target": "b", "x": 120, "y": 40}, detail="brief")
    other.save()
    drawn = []
    original = R.transform_layer_image
    try:
        R.transform_layer_image = lambda project, layer, bounds, image: drawn.append(layer["name"]) or original(
            project, layer, bounds, image)
        with session.project() as second:
            assert second is not first and second._cache is cache
            image = second.render()
    finally:
        R.transform_layer_image = original
    assert drawn == []  # Both layers came from the carried cache (the star only moved).
    fresh = Project.load(tmp_path / "doc.vixl")
    fresh._cache = None
    assert np.array_equal(pixels(image), pixels(R.render(fresh)))
    # A failed call drops the document; the next call reloads it, still with the same caches.
    with pytest.raises(RuntimeError):
        with session.project():
            raise RuntimeError("provider failed")
    with session.project() as third:
        assert third._cache is cache


def test_a_second_cli_export_reads_the_saved_render(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RENDER_CACHE", str(tmp_path / "cache"))
    moving(tmp_path / "doc.vixl")
    assert main(["-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "a.png")]) == 0
    assert pngs(tmp_path / "cache")
    drawn = []
    original = R.render_incremental
    monkeypatch.setattr(R, "render_incremental", lambda *a: drawn.append(1) or original(*a))
    assert main(["-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "b.png")]) == 0
    assert drawn == []  # The whole frame came back from the disk cache.
    assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()


def test_the_disk_cache_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RENDER_CACHE", "off")
    moving(tmp_path / "doc.vixl")
    assert render_cache.user_cache_dir() is None
    assert main(["-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "a.png")]) == 0
    assert render_cache.enable(Project(10, 10), render_cache.user_cache_dir())._disk_cache is None


def test_the_disk_cache_stays_under_its_size_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RENDER_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VIXL_CACHE_MAX_MB", "0.5")
    for i in range(6):
        p = Project(128, 128)
        noise = np.random.default_rng(i).integers(0, 255, (128, 128, 4), dtype=np.uint8)
        from vixl.assets import add_image

        p.apply({"type": "add", "asset": add_image(p, Image.fromarray(noise, "RGBA")), "name": "noise"}, detail="brief")
        p.save(tmp_path / f"d{i}.vixl")
        assert main(["-p", str(tmp_path / f"d{i}.vixl"), "export", str(tmp_path / f"d{i}.png")]) == 0
    assert 0 < sum(path.stat().st_size for path in pngs(tmp_path / "cache")) <= 0.5 * 1024 * 1024


def test_cache_info_and_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIXL_RENDER_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VIXL_CACHE_MAX_MB", "64")
    moving(tmp_path / "doc.vixl")
    main(["-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "a.png")])
    capsys.readouterr()
    assert main(["--json", "cache", "info"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["enabled"] and info["entries"] == len(pngs(tmp_path / "cache")) > 0
    assert info["budget_bytes"] == 64 * 1024 * 1024 and info["directory"] == str(tmp_path / "cache")
    assert main(["--json", "cache", "clear"]) == 0
    cleared = json.loads(capsys.readouterr().out)
    assert cleared["removed"] == info["entries"] and not pngs(tmp_path / "cache")


def test_moving_frames_are_stored_only_when_requested_again(tmp_path, monkeypatch):
    from vixl.timeline import export_timeline, render_at

    monkeypatch.setenv("VIXL_RENDER_CACHE", str(tmp_path / "cache"))
    caches = []
    original = render_cache.enable
    monkeypatch.setattr(render_cache, "enable", lambda *a, **k: caches.append(original(*a, **k)) or caches[-1])
    outputs = []
    for run in range(3):
        export_timeline(Project.load(tmp_path / "doc.vixl") if run else moving(tmp_path / "doc.vixl"),
                        tmp_path / f"run{run}.zip", format="frames", fps=12)
        outputs.append(frame_pixels(tmp_path / f"run{run}.zip"))
    first, second, third = (cache._disk_cache.stats() for cache in caches)
    # The first export draws every moving frame once and stores none of them; static layers are stored.
    assert first["frame_writes"] == 0 and first["frame_writes_skipped"] == 12 and first["layer_writes"] > 0
    # The re-export requests the same frames again and keeps them; the third reads them back.
    assert second["frame_writes"] == 12
    assert third["frame_hits"] == 12 and third["frame_writes"] == 0
    assert all(np.array_equal(a, b) and np.array_equal(a, c) for a, b, c in zip(*outputs))
    reference = Project.load(tmp_path / "doc.vixl")
    reference._cache = None
    assert np.array_equal(outputs[2][5], pixels(render_at(reference, 5 * 1000 / 12)))


def test_film_frames_share_one_source_cache_and_store_no_one_use_frames(tmp_path, monkeypatch):
    import vixl.film as film

    moving(tmp_path / "doc.vixl")
    spec = {"width": 320, "height": 180, "fps": 12, "shots": [{"source": "doc.vixl", "duration": 1000}]}
    drawn = []
    original = R.transform_layer_image
    monkeypatch.setattr(R, "transform_layer_image", lambda project, layer, bounds, image: drawn.append(layer["name"])
                        or original(project, layer, bounds, image))
    frames = [pixels(image) for image in film.frames(spec, tmp_path)]
    assert len(frames) == 12
    # The grain background and the header are drawn once for the whole shot.
    assert drawn.count("paper") == 1 and drawn.count("header") == 1
    # The grain layer is stored once; no frame (each a mostly unique grain picture) is.
    large = [path for path in pngs(tmp_path / ".vixl-cache") if path.stat().st_size > 40_000]
    assert len(large) == 1
    # Same pixels as frames drawn with fresh caches.
    reference = Project.load(tmp_path / "doc.vixl")
    from vixl.proxy import render_preview
    from vixl.timeline import project_at

    for index in (0, 5, 11):
        frame = project_at(reference, index * 1000 / 12)
        frame._cache = None
        expected = pixels(render_preview(frame, 320, 180))
        assert np.array_equal(frames[index], expected)


def test_frames_share_the_documents_cache_even_when_it_had_none():
    from vixl.timeline import project_at

    p = Project(100, 100, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "dot", "x": 0, "y": 0, "width": 20, "height": 20},
             {"type": "keyframe", "target": "dot", "property": "x", "time": 0, "value": 0},
             {"type": "keyframe", "target": "dot", "property": "x", "time": 1000, "value": 80}], detail="brief")
    p._cache = None
    frame = project_at(p, 500)
    assert isinstance(p._cache, R.LayerCache) and frame._cache is p._cache
    frame.render()
    assert len(p._cache) > 0 and project_at(p, 900)._cache is p._cache


@pytest.mark.perf
def test_a_continuously_moving_film_writes_no_frame_pngs(tmp_path):
    """The lyric-film workload of #607: a full-frame grain layer under a fixed header and moving symbols. Before
    the adaptive frame policy every frame was stored as a mostly-unique grain PNG."""
    import time

    import vixl.film as film

    moving(tmp_path / "doc.vixl")
    spec = {"width": 320, "height": 180, "fps": 24, "shots": [{"source": "doc.vixl", "duration": 2000}]}
    start = time.perf_counter()
    count = sum(1 for _ in film.frames(spec, tmp_path))
    elapsed = time.perf_counter() - start
    assert count == 48
    stored = sum(path.stat().st_size for path in pngs(tmp_path / ".vixl-cache"))
    assert stored < 1_000_000  # 48 grain frames took several megabytes
    assert elapsed < 20


@pytest.mark.parametrize("region", [(95, 82, 73, 56), (100, 80, 100, 60), (96, 81, 70, 57), (1, 1, 318, 178)])
def test_regions_of_fractionally_placed_layers_match_the_full_render(region, tmp_path):
    """A layer whose box sits half a pixel off once centred (a scaled star at x 115.8333) was resampled one
    rounding step differently when the region moved its box by whole pixels; frame 5 of a moving export differed."""
    from vixl.design import resolve_color
    from vixl.timeline import project_at

    p = moving(tmp_path / "doc.vixl")
    frame = project_at(p, 5 * 1000 / 12)
    frame._cache = None
    full = pixels(R.render(frame))
    frame._cache = None
    tile = pixels(R.render_region(frame, region, resolve_color(frame.state["canvas"]["background"], frame.state)))
    left, top, width, height = region
    assert np.array_equal(tile, full[top:top + height, left:left + width])
