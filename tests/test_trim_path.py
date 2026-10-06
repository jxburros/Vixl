"""Trim path: trim_start / trim_end draw a shape's or path's stroke partway along its outline."""

import io
import json
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project
from vixl.errors import VixlError
from vixl.timeline import export_timeline, project_at


def ink(image):
    return np.asarray(image.convert("L")) < 128


def svg_image(project):
    data = project.export(format="SVG")
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=data.decode()))).convert("RGBA"), ET.fromstring(data)


def overlap(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def line(**extra):
    """A 160 px horizontal stroke from x=20 to x=180 on a 200×100 canvas."""
    p = Project(200, 100, "white")
    p.apply({"type": "shape", "shape": "path", "path": "M20 50 L180 50", "name": "wave", "width": 200, "height": 100,
             "fill": "transparent", "stroke": "black", "stroke_width": 8, **extra})
    return p


def columns(mask, row=50):
    xs = np.where(mask[row])[0]
    return (int(xs.min()), int(xs.max()) + 1) if len(xs) else None


def test_trim_end_and_start_pick_the_visible_part_of_a_path():
    assert columns(ink(line().render())) == (20, 180)
    assert columns(ink(line(trim_end=50).render())) == (20, 100)
    assert columns(ink(line(trim_start=25, trim_end=75).render())) == (60, 140)
    assert columns(ink(line(trim_start=50).render())) == (100, 180)
    # A start past the end swaps them, so crossing animated values stay continuous.
    assert columns(ink(line(trim_start=75, trim_end=25).render())) == (60, 140)
    assert not ink(line(trim_end=0).render()).any()
    assert not ink(line(trim_start=100).render()).any()


def test_only_the_stroke_is_trimmed_and_round_caps_round_the_ends():
    p = Project(200, 100, "white")
    p.apply({"type": "shape", "shape": "path", "path": "M20 20 L180 20 L180 80 L20 80 Z", "name": "box", "width": 200,
             "height": 100, "fill": "#ff0000", "stroke": "black", "stroke_width": 6, "trim_end": 40})
    image = np.asarray(p.render().convert("RGB")).astype(int)
    assert tuple(image[50, 100]) == (255, 0, 0)  # the fill stays whole
    assert (image[20, 100] < 60).all()           # the top edge is stroked (40% of 440 reaches past its end)...
    assert (image[30, 180] < 60).all() and not (image[70, 180] < 60).all()  # ...and 16 px down the right edge
    assert (image[80, 100] > 200).any() and not (image[80, 100] < 60).all()  # the bottom edge is not
    round_caps = line(trim_end=50, line_cap="round")
    butt = line(trim_end=50)
    assert columns(ink(round_caps.render())) == (16, 104) and columns(ink(butt.render())) == (20, 100)


def test_closed_shapes_start_top_left_or_top_and_run_clockwise():
    rect = Project(100, 100, "white")
    rect.apply({"type": "shape", "shape": "rectangle", "name": "r", "width": 100, "height": 100, "fill": "transparent",
                "stroke": "black", "stroke_width": 4, "trim_end": 25})
    mask = ink(rect.render())
    assert mask[4, 10:90].all() and not mask[50, 4] and not mask[90:, :].any()  # top edge drawn, left and bottom not
    ring = Project(100, 100, "white")
    ring.apply({"type": "shape", "shape": "ellipse", "name": "e", "width": 100, "height": 100, "fill": "transparent",
                "stroke": "black", "stroke_width": 4, "trim_end": 25})
    arc = ink(ring.render())
    assert arc[4, 50] and arc[46, 95] and arc[30, 90] and not arc[50, 4] and not arc[94, 50]  # 12 o'clock to 3 o'clock


@pytest.mark.parametrize("shape", ["rectangle", "rounded-rectangle", "ellipse", "polygon", "star", "line", "heart", "capsule"])
def test_trimmed_shapes_draw_a_part_of_the_untrimmed_stroke(shape):
    fields = {"type": "shape", "shape": shape, "name": "s", "width": 100, "height": 80, "x": 10, "y": 20,
              "fill": "transparent", "stroke": "black", "stroke_width": 6}
    whole, half = Project(120, 120, "white"), Project(120, 120, "white")
    whole.apply(fields)
    half.apply({**fields, "trim_end": 50})
    full, part = ink(whole.render()), ink(half.render())
    assert 0.4 < part.sum() / full.sum() < 0.6
    assert (part & ~full).sum() < 0.04 * full.sum()  # the trimmed stroke sits on the full one
    # Nearly all the way drawn is nearly the finished shape (a closed outline has no join at its start yet).
    almost = Project(120, 120, "white")
    almost.apply({**fields, "trim_end": 99.5})
    assert overlap(ink(almost.render()), full) > 0.9


def test_draw_on_preset_animates_a_stroke_that_grows_to_the_finished_line():
    p = line(stroke_width=8)
    result = p.apply({"type": "animate-preset", "target": "wave", "preset": "draw-on", "start": 0, "duration": "1s",
                      "easing": "linear"})
    assert "warnings" not in result
    tracks = {t["property"]: t["keys"] for t in p.state["timeline"]["tracks"]}
    assert [k["value"] for k in tracks["trim_end"]] == [0.0, 100.0] and "trim_start" not in tracks
    assert not ink(project_at(p, 0).render()).any()
    widths = [columns(ink(project_at(p, t).render())) for t in (250, 500, 750)]
    assert [w[0] for w in widths] == [20, 20, 20] and [w[1] for w in widths] == [60, 100, 140]
    assert columns(ink(project_at(p, 1000).render())) == (20, 180)
    assert np.array_equal(ink(project_at(p, 1000).render()), ink(line().render()))
    # Draw off erases from the start, the way the line was drawn.
    q = line()
    q.apply({"type": "animate-preset", "target": "wave", "preset": "draw-off", "duration": "1s", "easing": "linear"})
    assert columns(ink(project_at(q, 500).render())) == (100, 180) and not ink(project_at(q, 1000).render()).any()
    # Start and end together slide a worm of stroke along the line.
    r = line()
    r.apply([
        {"type": "animate", "target": "wave", "property": "trim_end", "from": 0, "to": 100, "start": 0, "end": 1000, "easing": "linear"},
        {"type": "animate", "target": "wave", "property": "trim-start", "from": 0, "to": 100, "start": 500, "end": 1500, "easing": "linear"},
    ])
    assert columns(ink(project_at(r, 750).render())) == (60, 140)
    assert columns(ink(project_at(r, 1000).render())) == (100, 180)
    assert columns(ink(project_at(r, 1250).render())) == (140, 180)


def test_overshooting_easings_stay_on_the_outline():
    p = line()
    p.apply({"type": "animate", "target": "wave", "property": "trim_end", "from": 0, "to": 100, "duration": "1s", "easing": "ease-out-back"})
    values = {project_at(p, t).layer("wave")["trim_end"] for t in range(0, 1001, 50)}
    assert all(0 <= v <= 100 for v in values) and max(values) == 100.0


def test_property_validation_and_defaults():
    p = line()
    p.apply({"type": "solid", "name": "plain", "color": "red", "width": 5, "height": 5})
    with pytest.raises(VixlError, match="0 or more|at most 100"):
        p.apply({"type": "keyframe", "target": "wave", "property": "trim_end", "time": 0, "value": 120})
    with pytest.raises(VixlError, match="at least 0"):
        p.apply({"type": "keyframe", "target": "wave", "property": "trim_start", "time": 0, "value": -5})
    with pytest.raises(VixlError, match="shape or path"):
        p.apply({"type": "keyframe", "target": "plain", "property": "trim_end", "time": 0, "value": 50})
    with pytest.raises(VixlError, match="shape or path"):
        p.apply({"type": "animate-preset", "target": "plain", "preset": "draw-on"})
    with pytest.raises(VixlError):
        p.apply({"type": "shape", "shape": "rectangle", "name": "bad", "trim_end": 150})
    # An animate without `from` starts from the layer's own trim, 100 for the end.
    p.apply({"type": "animate", "target": "wave", "property": "trim_end", "to": 20, "duration": "1s"})
    assert p.state["timeline"]["tracks"][0]["keys"][0]["value"] == 100
    p.apply({"type": "animate", "target": "wave", "property": "trim-start", "to": 30, "duration": "1s"})
    assert {t["property"] for t in p.state["timeline"]["tracks"]} == {"trim_end", "trim_start"}


def test_pen_and_shape_operations_store_trim_and_caps():
    p = Project(200, 100, "white")
    p.apply({"type": "pen", "name": "swoosh", "points": [[20, 80], [100, 20], [180, 80]], "stroke_width": 6,
             "trim_end": 40, "line_cap": "round"})
    layer = p.layer("swoosh")
    assert layer["trim_end"] == 40 and layer["line_cap"] == "round"
    full = Project(200, 100, "white")
    full.apply({"type": "pen", "name": "swoosh", "points": [[20, 80], [100, 20], [180, 80]], "stroke_width": 6})
    assert ink(p.render()).sum() < 0.6 * ink(full.render()).sum()
    # Editing the pen path takes the trim along; at 100% the stroke is the plain one again.
    p.apply({"type": "pen", "target": "swoosh", "points": [[20, 80], [100, 20], [180, 80]], "trim_end": 100})
    assert p.layer("swoosh")["trim_end"] == 100
    assert overlap(ink(p.render()), ink(full.render())) > 0.97


def test_svg_export_draws_the_same_trim_natively():
    p = Project(200, 120, "white")
    p.apply([
        {"type": "shape", "shape": "path", "path": "M20 100 C60 0 140 0 180 100", "name": "arc", "width": 200, "height": 120,
         "fill": "transparent", "stroke": "black", "stroke_width": 10, "line_cap": "round"},
        {"type": "shape", "shape": "ellipse", "name": "ring", "width": 60, "height": 60, "x": 70, "y": 50, "fill": "#f4c430",
         "stroke": "#10b4a0", "stroke_width": 6},
        {"type": "animate", "target": "arc", "property": "trim_end", "from": 0, "to": 100, "duration": "1s", "easing": "linear"},
        {"type": "animate", "target": "ring", "property": "trim_end", "from": 0, "to": 100, "duration": "1s", "easing": "linear"},
    ])
    for t in (200, 500, 900):
        frame = project_at(p, t)
        image, root = svg_image(frame)
        assert not root.findall(".//{*}image") and "raster_fallbacks" not in ET.tostring(root, encoding="unicode")
        assert root.findall(".//{*}path[@stroke-dasharray]")
        assert overlap(ink(frame.render()), ink(image)) > 0.99
        assert np.abs(np.asarray(frame.render()).astype(int) - np.asarray(image).astype(int)).mean() < 1.0
    # Untrimmed layers keep their original SVG elements.
    plain = Project(100, 100, "white")
    plain.apply({"type": "shape", "shape": "rectangle", "name": "r", "width": 50, "height": 50, "stroke": "black", "stroke_width": 4})
    assert b"stroke-dasharray" not in plain.export(format="svg")


def test_pdf_and_pptx_fall_back_to_a_raster_for_trimmed_strokes():
    p = line(trim_end=50)
    for name in ("PDF", "PPTX"):
        report = {}
        p.export(format=name, pdf_content="vector", report=report)
        flat = [item for value in report["raster_fallbacks"].values() for item in value]
        assert any(item["layer"] == "wave" and item["reason"] == "trimmed stroke" for item in flat), (name, report)
    untrimmed = {}
    line().export(format="PDF", pdf_content="vector", report=untrimmed)
    assert untrimmed["raster_fallbacks"] == {}


def test_frames_export_and_video_match_still_renders(tmp_path):
    p = line()
    p.apply([
        {"type": "timeline-set", "duration": 1000, "fps": 4},
        {"type": "animate-preset", "target": "wave", "preset": "draw-on", "duration": "1s", "easing": "linear"},
    ])
    result = export_timeline(p, tmp_path / "f.zip")
    with zipfile.ZipFile(tmp_path / "f.zip") as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".png"))
        assert len(names) == result["frames"] == 4
        counts = []
        for i, name in enumerate(names):
            exported = Image.open(io.BytesIO(archive.read(name))).convert("RGBA")
            assert np.array_equal(np.asarray(exported), np.asarray(project_at(p, i * 250).render()))
            counts.append(int(ink(exported).sum()))
    assert counts[0] == 0 and counts == sorted(counts) and counts[-1] > counts[1]
    gif = export_timeline(p, tmp_path / "f.gif")
    assert gif["frames"] == 4
    import shutil

    if shutil.which("ffmpeg"):
        video = export_timeline(p, tmp_path / "f.mp4")
        assert video["frames"] == 4 and (tmp_path / "f.mp4").stat().st_size > 0


def test_schema_documents_trim_and_cli_exposes_it(tmp_path, monkeypatch, capsys):
    from vixl.cli import main
    from vixl.schema import operation_schema

    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    for kind in ("shape", "pen"):
        properties = variants[kind]["properties"]
        assert properties["trim_end"]["maximum"] == 100 and "draw a line on" in properties["trim_end"]["description"]
        assert properties["trim_start"]["minimum"] == 0 and properties["line_cap"]["enum"] == ["butt", "round", "square"]
    assert "trim_end" in variants["keyframe"]["properties"]["property"]["description"]
    monkeypatch.chdir(tmp_path)
    assert main(["new", "200x100", "--background", "white", "-o", "t.vixl"]) == 0
    assert main(["shape", "path", "--path", "M20 50 L180 50", "--width", "200", "--height", "100", "--stroke", "black",
                 "--stroke-width", "8", "--trim-end", "40", "--line-cap", "round", "--fill", "transparent"]) == 0
    assert main(["animate-preset", "shape", "draw-on", "--duration", "1s"]) == 0
    capsys.readouterr()
    assert main(["easings"]) == 0
    assert {"draw-on", "draw-off"} <= set(json.loads(capsys.readouterr().out)["presets"])
    layer = Project.load(tmp_path / "t.vixl").layer("shape")
    assert layer["trim_end"] == 40 and layer["line_cap"] == "round"


def test_trim_survives_save_load_and_validation(tmp_path):
    p = line(trim_start=10, trim_end=60)
    p.apply({"type": "animate", "target": "wave", "property": "trim_end", "to": 90, "duration": "1s"})
    p.save(tmp_path / "t.vixl")
    loaded = Project.load(tmp_path / "t.vixl")
    assert loaded.layer("wave")["trim_start"] == 10
    assert np.array_equal(np.asarray(project_at(loaded, 500).render()), np.asarray(project_at(p, 500).render()))
    state = json.loads(json.dumps(loaded.state))
    state["layers"][0]["trim_end"] = 400
    from vixl.validation import check_state

    with pytest.raises(VixlError):
        check_state(loaded, state)
