import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image
import pytest

from vixl import Project
from vixl.cli import dispatch, project_command
from vixl.errors import VixlError


@pytest.mark.parametrize("kind", ["rose", "leaf", "petal", "blob"])
def test_organic_paths_are_deterministic_editable_and_vector(kind, tmp_path):
    p = Project(200, 200)
    op = {"type": "organic-shape", "kind": kind, "seed": 4, "name": "flower", "width": 180, "height": 180}
    p.apply(op)
    original = p.layer()["path"]
    p.apply({"type": "organic-shape", "target": "flower", "seed": 4})
    assert p.layer()["path"] == original
    assert p.render().getchannel("A").getbbox()
    root = ET.fromstring(p.export(format="SVG"))
    assert root.findall(".//{*}path") and not root.findall(".//{*}image")
    p.apply({"type": "path-fit", "target": "flower", "padding": 12})
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.svgLib.path import parse_path
    pen = BoundsPen(None)
    parse_path(p.layer()["path"], pen)
    assert all(v >= 11.99 for v in pen.bounds[:2])
    assert all(v <= 168.01 for v in pen.bounds[2:])
    p.save(tmp_path / "flower.vixl")
    assert Project.load(tmp_path / "flower.vixl").layer()["organic"]["kind"] == kind


def test_invisible_paint_warns_and_layer_space_corrects_it():
    p = Project(200, 200)
    p.apply({"type": "paint-layer", "name": "gesture", "x": 50, "y": 150, "width": 100, "height": 30})
    p.apply({"type": "paint", "points": [[5, 10], [80, 20]], "size": 3})
    assert any(x["check"] == "content" for x in p.check(checks=["content"])["issues"])
    p.apply({"type": "paint-clear"})
    p.apply({"type": "paint", "points": [[5, 10], [80, 20]], "size": 3, "space": "layer"})
    assert not p.check(checks=["content"])["issues"]


def test_glyph_fallback_is_shared_by_png_svg_and_qa(tmp_path):
    import vixl
    font = TTFont(Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf")
    sub = subset.Subsetter()
    sub.populate(text="ABC ")
    sub.subset(font)
    file = tmp_path / "limited.ttf"
    font.save(file)
    p = Project(200, 100)
    p.apply({"type": "text", "text": "ABC ↗", "font": str(file), "size": 32})
    from vixl.text import font_data, shape
    glyphs, _ = shape(font_data(p, p.layer()), "ABC ↗", 32)
    assert all(g.name != ".notdef" for g in glyphs)
    assert p.check(checks=["fonts"])["issues"][0]["fallback"] == ["↗"]
    assert p.render().getchannel("A").getbbox()
    assert not ET.fromstring(p.export(format="SVG")).findall(".//{*}image")
    p.apply({"type": "text-set", "text": "\U0010ffff"})
    assert p.check(checks=["fonts"])["errors"] == 1


def test_layout_font_paths_mode_and_preview(tmp_path):
    import vixl
    font = str(Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf")
    p = Project(600, 800, "#080808")
    result, changed = project_command(p, "layout", ["preview", "event-poster", "--set", "title=FLOWERS", "--font", font, "--predictable"])
    assert not changed and not p.state["layers"]
    assert result["layout"]["mode"] == "dark"
    assert result["layout"]["align"] == "left"


def test_repeat_svg_matches_png_geometry():
    p = Project(100, 80)
    p.apply([{ "type": "shape", "shape": "rectangle", "name": "stripe", "width": 5, "height": 40, "x": 12, "y": 8, "fill": "red"},
             {"type": "repeat", "target": "stripe", "count": 5, "dx": 12}])
    import resvg_py
    svg = p.export(format="SVG")
    assert not ET.fromstring(svg).findall(".//{*}image")
    rendered = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode())))
    assert rendered.getchannel("A").getbbox() == p.render().getchannel("A").getbbox()


def test_repeat_strokes_are_clipped_like_png():
    import resvg_py
    p = Project(100, 80)
    p.apply([{ "type": "shape", "shape": "rectangle", "width": 20, "height": 30, "x": 40, "y": 10, "fill": "transparent", "stroke": "red", "stroke_width": 5},
             {"type": "repeat", "count": 3, "dx": 25}])
    svg = p.export(format="SVG")
    rendered = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode())))
    assert rendered.getchannel("A").getbbox() == p.render().getchannel("A").getbbox()


def test_hidden_stroke_is_reported_inside_visible_paint_layer():
    p = Project(100, 100)
    p.apply([{ "type": "paint-layer", "width": 100, "height": 100},
             {"type": "paint", "points": [[5, 5], [50, 50]], "space": "layer"},
             {"type": "paint", "points": [[500, 500], [550, 550]], "space": "layer"}])
    issues = p.check(checks=["content"])["issues"]
    assert len(issues) == 1 and issues[0]["stroke"]["index"] == 1


@pytest.mark.parametrize("format", ["gif", "webp", "apng"])
def test_encoded_timing_preserves_four_seconds(format, tmp_path):
    from vixl.timeline import export_timeline
    p = Project(16, 16)
    p.apply([{ "type": "shape", "shape": "rectangle", "width": 3, "height": 3, "fill": "red"},
             {"type": "timeline-set", "duration": 4000, "fps": 12},
             {"type": "animate", "property": "x", "to": 12, "duration": 4000}])
    path = tmp_path / ("motion.png" if format == "apng" else "motion." + format)
    report = export_timeline(p, path, format=format)
    assert sum(report["frame_durations"]) == report["duration"] == 4000
    image = Image.open(path)
    durations = []
    for i in range(image.n_frames):
        image.seek(i)
        image.load()
        durations.append(image.info["duration"])
    assert sum(durations) == 4000


def test_session_is_atomic_and_recovers_after_bad_request(tmp_path):
    from vixl.session import run
    p = Project(100, 100)
    p.save(tmp_path / "session.vixl")
    requests = [{"id": 1, "operations": [{"type": "solid", "name": "a", "color": "red"}]},
                {"id": 2, "operations": [{"type": "rename", "target": "a", "name": "b"}, {"type": "remove", "target": "absent"}]},
                {"id": 3, "command": ["layers"]}]
    out = io.StringIO()
    run(p, io.StringIO("\n".join(json.dumps(r) for r in requests)), out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["success"] for r in responses] == [True, False, True]
    assert p.layer("a") and Project.load(p.path).layer("a")


def test_new_requires_explicit_overwrite(tmp_path):
    path = str(tmp_path / "new.vixl")
    dispatch(["new", "32x32", "--out", path])
    with pytest.raises(VixlError):
        dispatch(["new", "40x40", "--out", path])
    dispatch(["new", "40x40", "--out", path, "--overwrite"])
    assert Project.load(path).state["canvas"]["width"] == 40


def test_explicit_overlap_intent_survives_rename():
    p = Project(240, 120)
    p.apply([{ "type": "text", "name": "a", "text": "FLOW", "size": 40, "x": 10, "y": 10},
             {"type": "text", "name": "b", "text": "FLOW", "size": 40, "x": 20, "y": 10}])
    assert p.check(checks=["overlap"])["errors"] == 1
    p.apply({"type": "layer-intent", "target": "a", "allow_overlap": ["b"]})
    p.apply({"type": "rename", "target": "b", "name": "renamed"})
    assert not p.check(checks=["overlap"])["issues"]
    p.apply({"type": "layer-intent", "target": "a", "allow_overlap": []})
    assert p.check(checks=["overlap"])["errors"] == 1


def test_no_update_launch_never_takes_write_lock(tmp_path, monkeypatch):
    from vixl import updater
    root = tmp_path / "install"
    exe = updater.executable(root, "0.17.0")
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"engine")
    state = {"protocol": updater.PROTOCOL, "current": "0.17.0", "pending": "0.18.0", "auto": True}
    updater.atomic_json(root / "install.json", state)
    monkeypatch.setattr(updater, "locked", lambda _: pytest.fail("read-only launch obtained a lock"))
    assert updater.prepare_launch(root, allow_updates=False) == (exe, False)
    assert updater.read_state(root) == state


def test_fallback_operation_cannot_import_arbitrary_paths():
    p = Project(20, 20)
    with pytest.raises(VixlError):
        p.apply({"type": "font-fallbacks", "fonts": ["private.ttf"]})


def test_runtime_install_retries_transient_windows_file_lock(tmp_path, monkeypatch):
    from vixl import updater
    stage, destination = tmp_path / "stage", tmp_path / "runtime"
    stage.mkdir()
    (stage / "engine").write_bytes(b"verified")
    replace = updater.os.replace
    calls, waits = [], []
    def busy_once(source, target):
        calls.append((source, target))
        if len(calls) == 1:
            exc = PermissionError("scanner is holding the probe executable")
            exc.winerror = 5
            raise exc
        replace(source, target)
    monkeypatch.setattr(updater.os, "replace", busy_once)
    monkeypatch.setattr(updater.time, "sleep", waits.append)
    updater.install_runtime(stage, destination)
    assert len(calls) == 2 and waits
    assert (destination / "engine").read_bytes() == b"verified"


def test_runtime_install_lock_failure_is_bounded_and_keeps_source(tmp_path, monkeypatch):
    from vixl import updater
    stage = tmp_path / "stage"
    stage.mkdir()
    calls = []
    def always_busy(*args):
        calls.append(args)
        exc = PermissionError("still locked")
        exc.winerror = 32
        raise exc
    monkeypatch.setattr(updater.os, "replace", always_busy)
    monkeypatch.setattr(updater.time, "sleep", lambda _: None)
    with pytest.raises(updater.UpdateError, match="current version is kept"):
        updater.install_runtime(stage, tmp_path / "runtime")
    assert stage.is_dir() and len(calls) < 10


def test_session_help_is_json_and_does_not_end_session(tmp_path):
    from vixl.session import run
    p = Project(32, 32)
    p.save(tmp_path / "help.vixl")
    out = io.StringIO()
    run(p, io.StringIO('{"command":["shape","--help"]}\n{"command":["layers"]}\n'), out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len(responses) == 2 and all(r["success"] for r in responses)
    assert "--fill" in responses[0]["result"]["help"]
