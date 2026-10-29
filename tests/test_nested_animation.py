"""Linked animation instances keep timing and edits local to their parent."""

from copy import deepcopy
import io
import zipfile

import numpy as np
from PIL import Image
import pytest

from vixl import Project, links
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.model import Limits
from vixl.timeline import export_timeline, project_at, render_at


def source(path):
    child = Project(80, 40, "white")
    child.apply([
        {"type": "shape", "name": "dot", "shape": "rectangle", "width": 10, "height": 10,
         "fill": "red", "x": 0, "y": 10},
        {"type": "timeline-set", "duration": 1000, "fps": 20, "loop": 1},
        {"type": "animate", "target": "dot", "property": "x", "from": 0, "to": 60,
         "start": 0, "end": 1000, "easing": "linear"},
    ])
    child.save(path)
    return child


def host(path, width=80):
    parent = Project(width, 40, "transparent")
    parent.save(path)
    return parent


def test_instances_map_offsets_speeds_and_cache_without_mutating_sources(tmp_path):
    child = source(tmp_path / "child.vixl")
    original_bytes = (tmp_path / "child.vixl").read_bytes()
    original_state = deepcopy(child.state)
    parent = host(tmp_path / "host.vixl", 160)
    parent.apply([
        {"type": "link", "source": "child.vixl", "name": "first", "time": {"offset": 0}},
        {"type": "animation-instance", "source": "child.vixl", "name": "second", "x": 80,
         "time": {"offset": 300, "speed": 2}},
    ])
    state = deepcopy(parent.state)
    for now, expected in ((500, (500, 400)), (600, (600, 600)), (500, (500, 400))):
        frame = render_at(parent, now)
        for index, at in enumerate(expected):
            assert frame.crop((80 * index, 0, 80 * (index + 1), 40)).tobytes() == render_at(child, at).tobytes()
    assert parent.state == state and child.state == original_state
    assert (tmp_path / "child.vixl").read_bytes() == original_bytes
    assert all("_time" not in layer for layer in parent.state["layers"])
    assert parent.inspect()["links"][1]["timing"]["window"] == [300, 800]
    assert parent.inspect()["links"][1]["timing"]["source_duration"] == 1000


@pytest.mark.parametrize("loop,times", [
    ("none", [(0, 200), (300, 400), (700, 800), (900, 800)]),
    ("loop", [(0, 200), (300, 400), (700, 200), (900, 400)]),
    ("pingpong", [(0, 200), (300, 400), (700, 800), (900, 600), (1300, 200)]),
])
def test_trim_loop_and_pingpong_boundaries(tmp_path, loop, times):
    child = source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl")
    parent.apply({"type": "link", "source": "child.vixl", "time": {
        "offset": 100, "trim_start": 200, "trim_end": 800, "loop": loop}})
    for now, expected in times:
        assert render_at(parent, now).tobytes() == render_at(child, expected).tobytes()


def test_hidden_before_and_after_has_no_source_background_and_pdf_matches(tmp_path):
    source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl")
    parent.apply({"type": "link", "source": "child.vixl", "time": {
        "offset": 100, "before": "hidden", "after": "hidden"}})
    for now in (0, 1150):
        assert render_at(parent, now).getbbox() is None
    assert render_at(parent, 100).getbbox() == (0, 0, 80, 40)
    assert render_at(parent, 1100).getbbox() == (0, 0, 80, 40)
    pdf = tmp_path / "hidden.pdf"
    parent.export(pdf)
    import pypdfium2

    doc = pypdfium2.PdfDocument(str(pdf))
    assert np.asarray(doc[0].render(scale=1).to_pil().convert("RGB")).min() == 255
    doc.close()


def test_link_settings_are_atomic_and_validated_on_load(tmp_path):
    source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl")
    parent.apply({"type": "link", "name": "child", "source": "child.vixl"})
    before = deepcopy(parent.state)
    for settings in ({"speed": 0}, {"speed": 11}, {"speed": True}, {"trim_start": -1},
                     {"trim_start": 1000}, {"trim_end": 1200}, {"trim_start": 600, "trim_end": 500},
                     {"loop": "forever"}, {"before": True}, {"offset": float("inf")}, {"unknown": 1}):
        with pytest.raises(VixlError):
            parent.apply({"type": "link", "target": "child", "time": settings})
        assert parent.state == before
    parent.apply({"type": "link", "target": "child", "time": {"speed": 2}})
    parent.save()
    assert Project.load(tmp_path / "host.vixl").layer("child")["time"] == {"speed": 2}
    parent.apply({"type": "link", "target": "child", "time": None})
    assert "time" not in parent.layer("child")
    parent.layer("child")["time"] = {"speed": -1}
    from vixl.validation import check_state

    with pytest.raises(VixlError, match="time.speed"):
        check_state(parent, parent.state)


def test_source_refresh_updates_every_instance_and_keeps_timing(tmp_path):
    child = source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl", 160)
    parent.apply([
        {"type": "link", "source": "child.vixl", "name": "a", "time": {"offset": 100}},
        {"type": "link", "source": "child.vixl", "name": "b", "x": 80, "time": {"speed": 2}},
    ])
    original = render_at(parent, 300).tobytes()
    child.apply({"type": "shape", "target": "dot", "fill": "blue"})
    child.save()
    parent.apply({"type": "link-refresh"})
    assert render_at(parent, 300).tobytes() != original
    assert parent.layer("a")["time"] == {"offset": 100}
    assert parent.layer("b")["time"] == {"speed": 2}
    assert all(item["state"] == "ok" for item in links.status(parent))


def test_nested_time_mapping_and_frame_budget_survive_warm_cache(tmp_path):
    child = source(tmp_path / "child.vixl")
    middle = host(tmp_path / "middle.vixl")
    middle.apply([
        {"type": "timeline-set", "duration": 1000, "fps": 20, "loop": 1},
        {"type": "link", "source": "child.vixl", "time": {"speed": 2}},
    ])
    middle.save()
    parent = host(tmp_path / "host.vixl", 160)
    parent.apply([
        {"type": "link", "source": "middle.vixl", "name": "nested", "time": {"offset": 100}},
        {"type": "link", "source": "child.vixl", "name": "other", "x": 80},
    ])
    assert render_at(parent, 300).crop((0, 0, 80, 40)).tobytes() == render_at(child, 400).tobytes()
    parent.limits = Limits(max_nested_frames=1)
    with pytest.raises(VixlError) as caught:
        render_at(parent, 300)
    assert caught.value.code == "resource_limit"
    assert caught.value.details["field"] == "max_nested_frames"
    parent.limits = Limits()
    assert render_at(parent, 300).size == (160, 40)


def test_static_pdf_and_timeline_frames_sample_the_same_child(tmp_path):
    child = source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl")
    parent.apply([
        {"type": "timeline-set", "duration": 1000, "fps": 20, "loop": 1},
        {"type": "link", "name": "child", "source": "child.vixl", "time": {"offset": -500}},
    ])
    assert parent.render().tobytes() == render_at(child, 500).tobytes()
    snapshot = project_at(parent, 200)
    snapshot.export(tmp_path / "sample.pdf")
    import pypdfium2

    doc = pypdfium2.PdfDocument(str(tmp_path / "sample.pdf"))
    actual = np.asarray(doc[0].render(scale=1).to_pil().convert("RGB"), dtype=int)
    expected = np.asarray(render_at(child, 700).convert("RGB"), dtype=int)
    assert np.abs(actual - expected).mean() < 2
    doc.close()
    export_timeline(parent, tmp_path / "frames.zip", fps=5)
    with zipfile.ZipFile(tmp_path / "frames.zip") as archive:
        frames = sorted(name for name in archive.namelist() if name.endswith(".png"))
        assert len(frames) == 5
        for index, name in enumerate(frames):
            actual = Image.open(io.BytesIO(archive.read(name))).convert("RGBA")
            assert actual.tobytes() == render_at(child, min(1000, 500 + index * 200)).tobytes()


def test_link_cli_accepts_timing_and_can_clear_it():
    assert compile_command("link child.vixl --time '{\"offset\":300,\"loop\":\"loop\"}'")["time"] == {
        "offset": 300, "loop": "loop"}
    assert compile_command("link-set child --clear time")["time"] is None


def test_selected_source_page_artboard_and_variables_sample_before_cropping(tmp_path):
    child = source(tmp_path / "child.vixl")
    child.apply([
        {"type": "variable", "name": "ink", "value": "red"},
        {"type": "shape", "target": "dot", "fill": "${ink}"},
        {"type": "artboard", "name": "crop", "width": 40, "height": 40, "x": 20, "y": 0,
         "background": "white"},
        {"type": "page", "action": "add", "name": "still"},
        {"type": "page", "action": "select", "page": 1},
    ])
    child.save()
    parent = host(tmp_path / "host.vixl", 40)
    parent.apply({"type": "link", "source": "child.vixl", "source_page": 1, "artboard": "crop",
                  "variables": {"ink": "blue"}, "time": {"offset": -500}})
    assert parent.render().tobytes() == project_at(child, 500).render(page=1, artboard="crop", variables={"ink": "blue"}).tobytes()
    parent.apply({"type": "link", "target": parent.state["layers"][0]["id"], "time": {"offset": 100, "before": "hidden"}})
    assert parent.render().getbbox() is None


def test_static_wrapper_passes_parent_time_to_animated_descendant(tmp_path):
    child = source(tmp_path / "child.vixl")
    wrapper = host(tmp_path / "wrapper.vixl")
    wrapper.apply({"type": "link", "source": "child.vixl"})
    wrapper.save()
    parent = host(tmp_path / "parent.vixl")
    parent.apply({"type": "link", "source": "wrapper.vixl"})
    assert render_at(parent, 350).tobytes() == render_at(child, 350).tobytes()


def test_nested_animation_cycle_is_refused(tmp_path):
    child = source(tmp_path / "child.vixl")
    parent = host(tmp_path / "host.vixl")
    parent.apply({"type": "link", "source": "child.vixl", "time": {"loop": "loop"}})
    parent.save()
    with pytest.raises(VixlError) as caught:
        child.apply({"type": "link", "source": "host.vixl", "time": {"speed": 2}})
    assert caught.value.code == "link_cycle"


@pytest.mark.perf
def test_sixty_frames_with_four_instances_stay_close_to_flattened_cost(tmp_path, monkeypatch):
    from time import perf_counter

    monkeypatch.setenv("VIXL_FRAME_WORKERS", "1")
    child = Project(160, 120, "white")
    child.apply([{"type": "shape", "name": f"dot{i}", "shape": "ellipse", "width": 12, "height": 12,
                  "x": 10 + i % 8 * 18, "y": 10 + i // 8 * 22, "fill": "red"} for i in range(24)])
    child.apply([
        {"type": "group", "name": "motion", "targets": [f"dot{i}" for i in range(24)]},
        {"type": "timeline-set", "duration": 1000, "fps": 60, "loop": 1},
        {"type": "animate", "target": "motion", "property": "rotation", "from": 0, "to": 20,
         "start": 0, "end": 1000, "easing": "linear"},
    ])
    child.save(tmp_path / "child.vixl")
    nested = Project(640, 120, "white")
    nested.save(tmp_path / "nested.vixl")
    nested.apply([{"type": "timeline-set", "duration": 1000, "fps": 60, "loop": 1},
                  *[{"type": "link", "source": "child.vixl", "name": f"instance{i}", "x": i * 160}
                    for i in range(4)]])
    flat = Project(640, 120, "white")
    flat.apply({"type": "timeline-set", "duration": 1000, "fps": 60, "loop": 1})
    for instance in range(4):
        names = [f"dot{instance}_{i}" for i in range(24)]
        flat.apply([{"type": "shape", "name": names[i], "shape": "ellipse", "width": 12, "height": 12,
                     "x": instance * 160 + 10 + i % 8 * 18, "y": 10 + i // 8 * 22, "fill": "red"}
                    for i in range(24)])
        flat.apply([
            {"type": "group", "name": f"motion{instance}", "targets": names},
            {"type": "animate", "target": f"motion{instance}", "property": "rotation", "from": 0, "to": 20,
             "start": 0, "end": 1000, "easing": "linear"},
        ])
    elapsed = []
    for name, project in (("nested", nested), ("flat", flat)):
        start = perf_counter()
        result = export_timeline(project, tmp_path / f"{name}.zip")
        elapsed.append(perf_counter() - start)
        assert result["frames"] == 60
    assert elapsed[0] < 5
    assert elapsed[0] <= 2 * elapsed[1] + 0.1
