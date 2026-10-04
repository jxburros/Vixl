import io
import json
import math
import re

from PIL import Image, ImageSequence
import numpy as np
import pytest

from vixl import Project, VixlError
from vixl.animation import size_warnings
from vixl.timeline import export_timeline, project_at, render_at


def character():
    p = Project(200, 200, "white")
    p.apply(
        [
            {"type": "shape", "name": "body", "shape": "rectangle", "fill": "blue", "width": 60, "height": 90, "x": 70, "y": 60},
            {"type": "shape", "name": "arm", "shape": "rectangle", "fill": "red", "width": 16, "height": 60, "x": 126, "y": 64},
            {"type": "shape", "name": "shoulder", "shape": "rectangle", "fill": "black", "width": 4, "height": 4, "x": 132, "y": 64},
            {"type": "pivot", "target": "arm", "value": [0.5, 0.0]},
        ]
    )
    return p


def test_pivot_rotation_keeps_the_pivot_pixel_fixed():
    p = character()
    p.apply({"type": "rotate", "target": "arm", "value": -70})
    assert p.layer("arm")["pivot"] == [0.5, 0.0] and (p.layer("arm")["x"], p.layer("arm")["y"]) == (126, 64)
    image = p.render()
    assert image.getpixel((134, 66))[:3] == (0, 0, 0)
    # The arm swung out to the right about the shoulder; the rest pose below it is empty.
    assert image.getpixel((160, 74))[:3] == (255, 0, 0)
    assert image.getpixel((134, 110))[:3] == (255, 255, 255)
    bounds = p.inspect("arm")["resolved_bounds"]
    assert bounds[0] <= 134 <= bounds[0] + bounds[2] and bounds[1] <= 64 <= bounds[1] + bounds[3]
    # Animated rotation keeps the shoulder fixed in every frame as well.
    p.apply({"type": "animate", "target": "arm", "property": "rotation", "from": -90, "to": 90, "duration": "1s"})
    for time in (0, 250, 500, 1000):
        frame = render_at(p, time)
        x, y, w, h = project_at(p, time).inspect("arm")["resolved_bounds"]
        red = np.argwhere(np.all(np.asarray(frame)[:, :, :3] == (255, 0, 0), axis=2))
        assert len(red) and abs(red[:, 1].mean() - 134) + abs(red[:, 0].mean() - 64) > 5
        assert x - 1 <= 134 <= x + w + 1 and y - 1 <= 64 <= y + h + 1
        center = (x + w / 2, y + h / 2)
        angle = math.radians(project_at(p, time).layer("arm")["rotation"])
        expected = (134 + 30 * -math.sin(angle), 64 + 30 * math.cos(angle))
        assert math.dist(center, expected) <= 1.5


def test_pivot_anchor_px_clear_and_move_keep_drawn_pose():
    p = character()
    p.apply({"type": "rotate", "target": "arm", "value": 30})
    before = p.inspect("arm")["resolved_bounds"]
    p.apply({"type": "pivot", "target": "arm", "value": "bottom-right"})
    assert p.layer("arm")["pivot"] == [1, 1] and p.inspect("arm")["resolved_bounds"] == before
    p.apply({"type": "pivot", "target": "arm", "value": [8, 0], "units": "px"})
    assert p.layer("arm")["pivot"] == [0.5, 0.0] and p.inspect("arm")["resolved_bounds"] == before
    p.apply({"type": "move", "target": "arm", "x": 5, "relative": True})
    assert p.inspect("arm")["resolved_bounds"][0] == before[0] + 5
    p.apply({"type": "pivot", "target": "arm", "clear": True})
    assert "pivot" not in p.layer("arm") and p.inspect("arm")["resolved_bounds"][0] == before[0] + 5
    with pytest.raises(VixlError, match="anchor"):
        p.apply({"type": "pivot", "target": "arm", "value": "middle"})
    with pytest.raises(VixlError):
        p.apply({"type": "pivot", "target": "arm", "value": [50, 0]})


def test_pivot_scale_about_pivot_in_timeline():
    p = character()
    p.apply({"type": "animate", "target": "arm", "property": "scale", "from": 1, "to": 2, "duration": "1s"})
    x, y, w, h = project_at(p, 1000).inspect("arm")["resolved_bounds"]
    assert (w, h) == (32, 120) and abs(x + w / 2 - 134) <= 1 and y == 64


def test_rotated_group_rotates_its_children_as_a_unit():
    p = character()
    p.apply({"type": "group", "name": "kid", "targets": ["body", "arm", "shoulder"]})
    upright = p.render()
    p.apply([{"type": "pivot", "target": "kid", "value": "center"}, {"type": "rotate", "target": "kid", "value": 90}])
    turned = np.asarray(p.render())[:, :, :3]
    # The 60×90 body becomes 90×60 about the group's center: blue pixels widen and shorten.
    blue = np.argwhere(np.all(turned == (0, 0, 255), axis=2))
    span = blue.max(axis=0) - blue.min(axis=0)
    assert span[1] > span[0]
    assert np.ptp(np.argwhere(np.all(np.asarray(upright)[:, :, :3] == (0, 0, 255), axis=2)), axis=0)[0] > 80
    # Keyframed translate, rotation and scale move the whole group together.
    p.apply(
        [
            {"type": "rotate", "target": "kid", "value": 0},
            {"type": "keyframe", "target": "kid", "property": "translate-x", "time": "1s", "value": 20},
            {"type": "keyframe", "target": "kid", "property": "translate-x", "time": 0, "value": 0},
            {"type": "animate", "target": "kid", "property": "rotation", "from": 0, "to": 180, "duration": "1s"},
        ]
    )
    final = np.asarray(render_at(p, 1000))[:, :, :3]
    black = np.argwhere(np.all(final == (0, 0, 0), axis=2)).mean(axis=0)
    gx, gy, gw, gh = p.inspect("kid")["resolved_bounds"]
    cx, cy = gx + gw / 2, gy + gh / 2
    # The shoulder marker (top right of the group) ends rotated 180° about the center, shifted 20 px.
    assert abs(black[1] - (2 * cx - 134 + 20)) <= 2 and abs(black[0] - (2 * cy - 66)) <= 2


def test_spinning_layer_does_not_drift():
    p = Project(200, 200, "white")
    p.apply(
        [
            {"type": "shape", "name": "box", "shape": "rectangle", "fill": "black", "width": 60, "height": 20, "x": 70, "y": 90},
            {"type": "animate-preset", "target": "box", "preset": "spin", "duration": "1s"},
        ]
    )
    for time in (0, 125, 250, 400):
        x, y, w, h = project_at(p, time).inspect("box")["resolved_bounds"]
        assert abs(x + w / 2 - 100) <= 1 and abs(y + h / 2 - 100) <= 1


def test_multi_target_animate_creates_tracks_for_each_target():
    p = character()
    p.apply(
        [
            {"type": "animate", "targets": ["arm", "body"], "property": "translate-y", "to": -10, "duration": "0.5s"},
            {"type": "animate-preset", "targets": ["arm", "shoulder"], "preset": "fade-in", "duration": "0.3s"},
            {"type": "keyframe", "targets": ["body", "shoulder"], "property": "opacity", "time": "1s", "value": 0.5},
        ]
    )
    tracks = {(t["target"], t["property"]) for t in p.state["timeline"]["tracks"]}
    ids = {name: p.layer(name)["id"] for name in ("arm", "body", "shoulder")}
    assert {(ids["arm"], "translate-y"), (ids["body"], "translate-y"), (ids["arm"], "opacity"), (ids["shoulder"], "opacity"), (ids["body"], "opacity")} <= tracks
    keys = [t["keys"] for t in p.state["timeline"]["tracks"] if t["property"] == "translate-y"]
    assert keys[0] == keys[1]
    with pytest.raises(VixlError, match="not both"):
        p.apply({"type": "animate", "target": "arm", "targets": ["body"], "property": "x", "to": 1})
    from vixl.commands import compile_command

    assert compile_command("animate arm,body rotation --to 20")["targets"] == ["arm", "body"]
    assert compile_command("animate-preset arm,body pulse")["targets"] == ["arm", "body"]
    assert compile_command("pivot arm 0.5 0") == {"type": "pivot", "target": "arm", "value": [0.5, 0.0]}
    assert compile_command("pivot arm 8 2 --px")["units"] == "px"
    assert compile_command("pivot top-left") == {"type": "pivot", "value": "top-left"}


def test_svg_export_honours_pivot():
    p = character()
    p.apply({"type": "rotate", "target": "arm", "value": -70})
    svg = p.export(format="SVG").decode()
    match = re.search(r'data-layer="arm"><g transform="translate\(([-\d.]+) ([-\d.]+)\) rotate\(([-\d.]+)\) scale\(1 1\) translate\(([-\d.]+) ([-\d.]+)\)"', svg)
    assert match, svg[:400]
    tx, ty, angle, ox, oy = map(float, match.groups())
    a = math.radians(angle)
    px, py = 8 + ox, 0 + oy  # the pivot in the arm's local box, relative to its center
    canvas = (tx + px * math.cos(a) - py * math.sin(a), ty + px * math.sin(a) + py * math.cos(a))
    assert math.dist(canvas, (134, 64)) <= 1
    assert "raster_fallbacks" not in svg


def test_timeline_export_renders_at_target_resolution(tmp_path):
    p = Project(80, 40, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hi", "size": 24, "color": "black"}, {"type": "animate-preset", "target": "t", "preset": "fade-in", "duration": "0.2s"}, {"type": "timeline-set", "duration": "0.2s", "fps": 5}])
    export_timeline(p, tmp_path / "f.zip", scale=4)
    import zipfile

    with zipfile.ZipFile(tmp_path / "f.zip") as archive:
        frame = Image.open(archive.open("frame_00000.png")).convert("RGBA")
        last = Image.open(archive.open(sorted(n for n in archive.namelist() if n.endswith(".png"))[-1])).convert("RGBA")
    assert frame.size == (320, 160)
    upscaled = render_at(p, 200).resize((320, 160), Image.Resampling.LANCZOS)
    # A crisp render has far more fully black or white pixels than an enlarged bitmap.
    def hard(image):
        gray = np.asarray(image.convert("L"))
        return ((gray < 20) | (gray > 235)).mean()

    assert hard(last) > hard(upscaled)
    with pytest.raises(VixlError):
        export_timeline(p, tmp_path / "big.zip", scale=20)


def test_gif_size_controls_are_lossless_by_default(tmp_path):
    p = Project(240, 60, "white")
    p.apply(
        [
            {"type": "gradient", "name": "bg", "width": 240, "height": 60, "start": "#1e3a8a", "end": "#7c3aed", "direction": "horizontal"},
            {"type": "shape", "name": "dot", "shape": "ellipse", "fill": "orange", "width": 20, "height": 20, "x": 10, "y": 20},
            {"type": "timeline-set", "duration": "1s", "fps": 10},
            {"type": "animate", "target": "dot", "property": "x", "to": 200, "duration": "1s"},
        ]
    )
    from vixl.animation import gif_frame
    from vixl.timeline import frame_times

    default = export_timeline(p, tmp_path / "a.gif")
    small = export_timeline(p, tmp_path / "b.gif", colors=32)
    assert small["bytes"] < default["bytes"] and "warnings" not in default
    # Opaque sequences are frame-differenced, but every decoded frame matches a full-frame encoding.
    times, _ = frame_times(p)
    expected = [gif_frame(render_at(p, t)).convert("RGBA") for t in times]
    decoded = [frame.convert("RGBA") for frame in ImageSequence.Iterator(Image.open(tmp_path / "a.gif"))]
    assert len(decoded) == len(expected)
    assert all(np.array_equal(np.asarray(a), np.asarray(b)) for a, b in zip(decoded, expected))
    assert size_warnings("gif", b"x" * (1024 * 1024 + 1)) and not size_warnings("webp", b"x" * (2 << 20))
    with pytest.raises(VixlError, match="colors"):
        export_timeline(p, tmp_path / "c.webp", colors=32)
    with pytest.raises(VixlError, match="colors"):
        export_timeline(p, tmp_path / "c.gif", colors=1)


def test_frame_animation_smooth_scaling_and_large_frames(tmp_path):
    p = Project(1080, 1080, "white")
    p.apply(
        [
            {"type": "shape", "name": "ball", "shape": "ellipse", "fill": "red", "width": 300, "height": 300, "x": 100, "y": 100},
            {"type": "frame-save", "name": "a"},
            {"type": "move", "target": "ball", "x": 600, "y": 600},
            {"type": "frame-save", "name": "b"},
        ]
    )
    half = p.render_frame("b", 0.5, "smooth")
    assert half.size == (540, 540) and half.getpixel((375, 375))[:3] == (255, 0, 0)
    with pytest.raises(VixlError, match="integer"):
        p.render_frame("b", 0.5)
    result = p.export_animation(tmp_path / "a.gif", scale=0.25, sampling="smooth", colors=16)
    assert result["size"] == [270, 270] and Image.open(tmp_path / "a.gif").n_frames == 2
    pixel = Project(16, 16, "white")
    pixel.apply([{"type": "frame-save", "name": "a"}])
    assert pixel.render_frame("a", 2).size == (32, 32)
    assert pixel.export_animation(tmp_path / "p.png", format="apng", scale=1.5, sampling="smooth")["size"] == [24, 24]
    # The pixel budget still bounds frame snapshots.
    from vixl.model import Limits

    tight = Project(1080, 1080, "white", limits=Limits(max_pixels=2_000_000))
    tight.apply({"type": "frame-save", "name": "a"})
    with pytest.raises(VixlError, match="pixel budget"):
        tight.apply({"type": "frame-save", "name": "b"})


def test_new_options_reach_cli_mcp_and_rest(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["new", "120x60", "--background", "white", "-o", "m.vixl"]) == 0
    assert main(["shape", "rectangle", "--name", "arm", "--width", "10", "--height", "40", "--fill", "red"]) == 0
    assert main(["pivot", "arm", "top"]) == 0
    assert main(["frame-save", "a"]) == 0
    assert main(["animate", "arm", "rotation", "--to", "45", "--duration", "0.5s"]) == 0
    capsys.readouterr()
    assert main(["export-timeline", "--out", "m.gif", "--colors", "16", "--scale", "1.5"]) == 0
    assert json.loads(capsys.readouterr().out)["size"] == [180, 90]
    assert main(["export-animation", "--out", "a.png", "--format", "apng", "--scale", "0.5", "--sampling", "smooth"]) == 0
    assert Image.open("a.png").size == (60, 30)

    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    client = TestClient(create_app(tmp_path / "m.vixl"))
    assert client.post("/timeline/export", json={"format": "gif", "colors": 8}).content.startswith(b"GIF")
    frame = client.get("/animation/frame/a", params={"scale": 0.5, "sampling": "smooth"})
    assert Image.open(io.BytesIO(frame.content)).size == (60, 30)
    exported = client.post("/animation/export", json={"format": "gif", "scale": 2, "colors": 4})
    assert Image.open(io.BytesIO(exported.content)).size == (240, 120)

    from vixl.mcp_tools import service_operation_schema

    assert any("pivot" in v["properties"]["type"]["enum"] for v in service_operation_schema()["oneOf"])
