import json
import math
import zipfile

from PIL import Image
import numpy as np
import pytest

from vixl import Project, VixlError
from vixl.brushes import BRUSHES
from vixl.timeline import easing_function, parse_time, project_at, render_at


def wave(x0=10, y0=50, length=180, count=30):
    return [[x0 + length * i / count, y0 + 15 * math.sin(i / count * 6)] for i in range(count + 1)]


@pytest.mark.parametrize("brush", sorted(BRUSHES))
def test_every_brush_paints_deterministically(brush):
    p = Project(200, 100, "white")
    p.apply({"type": "paint", "brush": brush, "points": wave(), "size": 14, "color": "navy", "seed": 4})
    first = np.asarray(p.render())
    again = np.asarray(p.render())
    assert np.array_equal(first, again)
    assert (first[:, :, :3] < 200).any(), brush


def test_paint_layers_keep_editable_strokes_and_erase():
    p = Project(120, 80, "white")
    p.apply({"type": "paint-layer", "name": "sketch"})
    p.apply({"type": "paint", "target": "sketch", "brush": "round", "points": [[10, 40], [110, 40]], "size": 20, "color": "black"})
    p.apply({"type": "paint", "target": "sketch", "points": [[60, 0], [60, 80]], "size": 16, "mode": "erase"})
    layer = p.layer("sketch")
    assert len(layer["strokes"]) == 2 and layer["strokes"][1]["mode"] == "erase"
    image = p.render()
    assert image.getpixel((20, 40))[:3] == (0, 0, 0)
    assert image.getpixel((60, 40))[:3] == (255, 255, 255)  # erased
    p.apply({"type": "paint-clear", "target": "sketch", "last": 1})
    assert p.render().getpixel((60, 40))[:3] == (0, 0, 0)
    # Strokes are stored relative to the layer surface, so moving and resizing keep them attached.
    p.apply([{"type": "move", "target": "sketch", "x": 0, "y": 10}, {"type": "resize", "target": "sketch", "width": 60, "height": 40}])
    assert p.render().getpixel((10, 30))[:3] != (255, 255, 255)


def test_paint_accepts_svg_paths_pressure_and_custom_brushes():
    p = Project(160, 120, "white")
    p.apply({"type": "brush-define", "name": "soft-ink", "base": "ink", "settings": {"hardness": 0.4, "taper": [0.3, 0.3]}})
    p.apply({"type": "paint", "brush": "soft-ink", "path": "M10 100 C40 10 120 10 150 100", "size": 10, "color": "#222"})
    p.apply({"type": "paint", "brush": "round", "points": [[10, 10], [80, 10], [150, 10]], "pressure": [0.1, 1, 0.1], "size": 12})
    strokes = p.layer("paint")["strokes"]
    assert len(strokes[0]["points"]) > 10 and len(strokes[1]["points"][0]) == 3
    assert "soft-ink" in p.state["brushes"]
    with pytest.raises(VixlError, match="Unknown brush"):
        p.apply({"type": "paint", "brush": "crayola", "points": [[1, 1], [2, 2]]})
    with pytest.raises(VixlError, match="Unknown brush setting"):
        p.apply({"type": "paint", "points": [[1, 1], [2, 2]], "settings": {"softness": 1}})
    with pytest.raises(VixlError, match="paint layer"):
        p.apply([{"type": "solid", "name": "fill", "color": "red"}, {"type": "paint", "target": "fill", "points": [[1, 1]]}])


def test_paint_layer_round_trips_and_exports_svg_fallback(tmp_path):
    p = Project(80, 60, "white")
    p.apply({"type": "paint", "brush": "watercolor", "points": wave(5, 30, 70, 10), "size": 12, "color": "teal"})
    p.save(tmp_path / "paint.vixl")
    loaded = Project.load(tmp_path / "paint.vixl")
    assert np.array_equal(np.asarray(loaded.render()), np.asarray(p.render()))
    svg = p.export(format="SVG").decode()
    assert "<image" in svg and "raster_fallbacks" in svg


def test_easing_and_time_parsing():
    assert easing_function("linear")(0.25) == 0.25
    assert easing_function("hold")(0.99) == 0 and easing_function("hold")(1) == 1
    assert easing_function("ease-in")(0.5) < 0.5 < easing_function("ease-out")(0.5)
    assert easing_function("ease-out-back")(0.7) > 1
    assert abs(easing_function("bounce-out")(1) - 1) < 1e-9
    assert easing_function("steps(4)")(0.3) == 0.25
    assert abs(easing_function("cubic-bezier(0.42, 0, 0.58, 1)")(0.5) - 0.5) < 0.01
    with pytest.raises(VixlError, match="did you mean"):
        easing_function("ease-inn")
    assert parse_time("1.5s") == 1500 and parse_time("250ms") == 250 and parse_time("50%", 2000) == 1000
    assert parse_time("intro", 1000, {"intro": 400}) == 400


def animated():
    p = Project(200, 100, "white")
    p.apply(
        [
            {"type": "shape", "name": "ball", "shape": "ellipse", "fill": "red", "width": 20, "height": 20, "x": 0, "y": 40},
            {"type": "text", "name": "label", "text": "Hi", "size": 20, "color": "black", "x": 150, "y": 10},
            {"type": "timeline-set", "duration": "1s", "fps": 10},
            {"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 180, "easing": "linear"},
            {"type": "animate", "target": "ball", "property": "fill", "to": "blue", "start": 0, "end": "1s"},
            {"type": "animate-preset", "target": "label", "preset": "fade-in", "duration": "0.5s"},
            {"type": "keyframe", "target": "canvas", "property": "background", "time": 0, "value": "white"},
            {"type": "keyframe", "target": "canvas", "property": "background", "time": "1s", "value": "#eeeeee"},
            {"type": "marker", "name": "middle", "time": "50%"},
        ]
    )
    return p


def test_timeline_interpolates_properties_colors_and_presets():
    p = animated()
    start, middle, end = (project_at(p, t) for t in (0, 500, 1000))
    assert start.layer("ball")["x"] == 0 and middle.layer("ball")["x"] == 90 and end.layer("ball")["x"] == 180
    assert start.layer("label")["opacity"] == 0 and end.layer("label")["opacity"] == 1
    assert start.layer("ball")["fill"] == "red" and end.layer("ball")["fill"] == "blue"  # keys hold as written
    assert middle.layer("ball")["fill"].startswith("#")  # in-between colors are mixed in OKLab
    assert p.layer("ball")["x"] == 0  # the document itself is never changed by sampling
    frame = render_at(p, "middle")
    assert frame.getpixel((100, 50))[:3] != (255, 255, 255)
    assert p.state["timeline"]["markers"]["middle"] == 500


def test_timeline_scale_translate_and_constrained_layers():
    p = Project(200, 200, "white")
    p.apply(
        [
            {"type": "shape", "name": "box", "shape": "rectangle", "fill": "black", "width": 40, "height": 40, "x": "center", "y": "center"},
            {"type": "constrain", "target": "box", "constraints": {"center-x": "canvas.center-x"}},
            {"type": "animate-preset", "target": "box", "preset": "pop-in", "duration": "0.5s"},
            {"type": "animate-preset", "target": "box", "preset": "shake", "start": "0.6s", "duration": "0.3s"},
        ]
    )
    half = project_at(p, 0)
    assert half.layer("box")["width"] == 24  # pop-in starts at 60% scale, centered
    bounds = half.inspect("box")["resolved_bounds"]
    assert abs(bounds[0] + bounds[2] / 2 - 100) <= 1
    later = project_at(p, 700)
    assert later.layer("box")["x"] != 80


def test_timeline_validation_and_layer_removal_prunes_tracks():
    p = animated()
    with pytest.raises(VixlError, match="Cannot animate"):
        p.apply({"type": "keyframe", "target": "ball", "property": "wobble", "time": 0, "value": 1})
    with pytest.raises(VixlError):
        p.apply({"type": "keyframe", "target": "ball", "property": "opacity", "time": 0, "value": 3})
    with pytest.raises(VixlError, match="Unknown animation preset"):
        p.apply({"type": "animate-preset", "target": "ball", "preset": "explode"})
    p.apply({"type": "remove", "target": "ball"})
    assert all(track["target"] != "ball" for track in p.state["timeline"]["tracks"])
    p.apply({"type": "keyframe-remove", "target": "label"})
    assert all(track["target"] == "canvas" for track in p.state["timeline"]["tracks"])


def test_typewriter_blink_and_effect_tracks():
    p = Project(120, 60, "white")
    p.apply(
        [
            {"type": "text", "name": "t", "text": "Hello", "size": 20, "color": "black"},
            {"type": "animate-preset", "target": "t", "preset": "typewriter", "duration": "1s"},
            {"type": "shape", "name": "s", "shape": "rectangle", "fill": "red", "width": 10, "height": 10},
            {"type": "blur", "target": "s", "value": 0},
            {"type": "animate-preset", "target": "s", "preset": "blink", "duration": "1s", "amount": 2},
        ]
    )
    effect = p.layer("s")["effects"][0]["id"]
    p.apply({"type": "animate", "target": "s", "property": f"effect:{effect}", "to": 4, "duration": "1s"})
    assert project_at(p, 0).layer("t")["text"] == ""
    assert project_at(p, 1000).layer("t")["text"] == "Hello"
    assert project_at(p, 300).layer("s")["visible"] is False
    assert project_at(p, 500).layer("s")["effects"][0]["amount"] == pytest.approx(2)


def test_timeline_exports_stream_formats(tmp_path):
    p = animated()
    gif = p_export(p, tmp_path / "a.gif")
    assert gif["frames"] == 10 and Image.open(tmp_path / "a.gif").n_frames == 10
    webp = p_export(p, tmp_path / "a.webp", fps=5)
    assert webp["frames"] == 5 and Image.open(tmp_path / "a.webp").n_frames == 5
    p_export(p, tmp_path / "a.png")
    assert Image.open(tmp_path / "a.png").n_frames == 10
    sheet = p_export(p, tmp_path / "s.png", format="sheet", columns=5)
    assert json.loads((tmp_path / "s.json").read_text())["frames"][5]["y"] == 100 and sheet["size"] == [200, 100]
    p_export(p, tmp_path / "f.zip", scale=0.5)
    with zipfile.ZipFile(tmp_path / "f.zip") as archive:
        assert len([n for n in archive.namelist() if n.endswith(".png")]) == 10
        assert Image.open(archive.open("frame_00000.png")).size == (100, 50)
    with pytest.raises(VixlError, match="already exists"):
        p_export(p, tmp_path / "a.gif")
    part = p_export(p, tmp_path / "part.gif", start="middle", end="1s")
    assert part["frames"] == 5


def p_export(project, path, **options):
    from vixl.timeline import export_timeline

    return export_timeline(project, path, **options)


def test_timeline_cli_round_trip(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["new", "200x100", "--background", "white", "-o", "m.vixl"]) == 0
    assert main(["shape", "ellipse", "--name", "dot", "--width", "20", "--height", "20", "--fill", "red"]) == 0
    assert main(["timeline", "set", "--duration", "1s", "--fps", "8"]) == 0
    assert main(["animate", "dot", "x", "--to", "180", "--duration", "1s", "--easing", "ease-in-out"]) == 0
    assert main(["keyframe", "dot", "opacity", "0.5s", "0.4"]) == 0
    assert main(["animate-preset", "dot", "pulse", "--start", "0", "--duration", "1s"]) == 0
    capsys.readouterr()
    assert main(["timeline"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["frames"] == 8 and {t["property"] for t in info["tracks"]} == {"x", "opacity", "scale"}
    assert main(["export-timeline", "--out", "m.gif"]) == 0
    assert main(["render", "--time", "0.5s", "--out", "frame.png"]) == 0
    assert main(["timeline-sheet", "--out", "sheet.png", "--count", "4"]) == 0
    assert (tmp_path / "m.gif").exists() and (tmp_path / "frame.png").exists() and (tmp_path / "sheet.png").exists()
    assert main(["paint", "--brush", "chalk", "--points", "[[10,10],[100,50]]", "--size", "8", "--settings", '{"hardness": 0.5}']) == 0
    assert main(["undo"]) == 0


def test_mcp_tools_cover_new_features(tmp_path):
    import asyncio

    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_connected_server_and_client_session

    from vixl.interfaces import mcp_server

    async def run():
        server = mcp_server(workspace=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            client: ClientSession

            async def call(name, arguments):
                result = await client.call_tool(name, arguments)
                assert not result.isError, result.content[0].text
                return result

            await call("vixl_document_create", {"path": "post.vixl", "size": "instagram-portrait"})
            sizes = json.loads((await call("vixl_sizes_list", {"category": "logos"})).content[0].text)
            assert any(item["name"] == "logo-horizontal" for item in sizes["sizes"])
            colors = json.loads((await call("vixl_color", {"action": "harmony", "colors": ["#2563eb"], "scheme": "triadic"})).content[0].text)
            assert len(colors["colors"]) == 3
            layouts = json.loads((await call("vixl_layouts_list", {})).content[0].text)
            assert "golden-section" in layouts["layouts"]
            await call("vixl_operations_apply", {"operations": [{"type": "layout-apply", "name": "hero-statement", "title": "Hello", "seed": 1}]})
            await call("vixl_operations_apply", {"operations": [{"type": "paint", "brush": "marker", "points": [[10, 10], [300, 60]], "size": 20, "color": "@accent"}]})
            await call("vixl_operations_apply", {"operations": [{"type": "animate-preset", "target": "headline", "preset": "slide-in-left", "duration": "0.5s"}, {"type": "timeline-set", "duration": "1s", "fps": 4}]})
            preview = await call("vixl_timeline_preview", {"count": 4, "max_width": 400})
            assert preview.content[0].type == "image"
            await call("vixl_render_preview", {"time": "0.25s", "simulate": "deuteranopia", "max_width": 200})
            exported = json.loads((await call("vixl_export_timeline", {"path": "post.gif", "scale": 0.2})).content[0].text)
            assert exported["frames"] == 4
            pdf = json.loads((await call("vixl_export_file", {"path": "post.pdf", "color_space": "cmyk", "ink_limit": 300})).content[0].text)
            assert pdf["format"] == "PDF"
            icons = json.loads((await call("vixl_export_icons", {"directory": "icons"})).content[0].text)
            assert "favicon.ico" in icons["files"]
            report = json.loads((await call("vixl_check", {"checks": ["print"]})).content[0].text)
            assert any("dpi" in issue["message"] for issue in report["issues"])
            brushes = json.loads((await call("vixl_brushes_list", {})).content[0].text)
            assert "watercolor" in brushes["brushes"]

    asyncio.run(run())
