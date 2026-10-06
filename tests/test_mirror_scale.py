"""Negative scale mirrors a layer, statically and as animated keyframe values."""

import io
import json
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project
from vixl.errors import VixlError
from vixl.timeline import project_at


def dark(image):
    return np.asarray(image.convert("L")) < 128


def box(image):
    ys, xs = np.where(dark(image))
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else None


def svg_image(project):
    data = project.export(format="SVG")
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=data.decode()))).convert("RGBA"), ET.fromstring(data)


def overlap(first, second):
    a, b = dark(first), dark(second)
    return (a & b).sum() / max(1, (a | b).sum())


def wedge(pivot="left", **extra):
    """A 160×60 wedge whose point is at the middle of its left edge, drawn at x=120."""
    p = Project(400, 200, "white")
    p.apply([
        {"type": "shape", "shape": "path", "path": "M0 30 L160 0 L160 60 Z", "name": "wedge", "width": 160,
         "height": 60, "x": 120, "y": 70, "fill": "black", **extra},
    ])
    if pivot:
        p.apply({"type": "pivot", "target": "wedge", "value": pivot})
    return p


def test_negative_scale_x_keyframes_swing_the_layer_over_its_pivot():
    p = wedge()
    p.apply([
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 0, "value": 1},
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 1000, "value": -1},
    ])
    rest = box(p.render())
    assert rest[0] == pytest.approx(120, abs=2) and rest[2] == pytest.approx(280, abs=2)
    assert box(project_at(p, 0).render()) == rest
    # The point stays at x=120 on the canvas; the body flips from the right of it to the left.
    half = project_at(p, 250)
    assert not half.layer("wedge")["flip_x"] and half.layer("wedge")["width"] == 80
    assert box(half.render())[0] == pytest.approx(120, abs=2) and box(half.render())[2] == pytest.approx(200, abs=2)
    assert box(project_at(p, 500).render()) is None  # edge on: nothing to draw
    mirrored = project_at(p, 1000)
    layer = mirrored.layer("wedge")
    assert layer["flip_x"] and layer["width"] == 160 and layer["pivot"] == [1, 0.5]
    image = mirrored.render()
    assert box(image)[0] == pytest.approx(0, abs=1) and box(image)[2] == pytest.approx(120, abs=2)
    # The mirror image of the rest pose about x=120: compare pixels of the two renders.
    mine = dark(image)[:, :120]
    theirs = dark(p.render())[:, 120:240][:, ::-1]
    assert (mine & theirs).sum() / max(1, (mine | theirs).sum()) > 0.97
    assert project_at(p, 750).layer("wedge")["flip_x"] and not project_at(p, 249).layer("wedge")["flip_x"]


def test_animate_negative_values_and_zero_crossing_easings():
    p = wedge(pivot=None)
    p.apply({"type": "animate", "target": "wedge", "property": "scale-x", "from": 1, "to": -1, "duration": "1s"})
    keys = [k["value"] for t in p.state["timeline"]["tracks"] for k in t["keys"]]
    assert keys == [1, -1]
    # Without a pivot the mirror is about the center: the box stays put as the artwork flips.
    rest, flipped = box(project_at(p, 0).render()), box(project_at(p, 1000).render())
    assert flipped[0] == pytest.approx(rest[0], abs=2) and flipped[2] == pytest.approx(rest[2], abs=2)
    assert not project_at(p, 100).layer("wedge")["flip_x"] and project_at(p, 900).layer("wedge")["flip_x"]
    # Row 75 is above the point: the tall end of the wedge is dark there, the thin end is not. Mirrored
    # artwork has its point on the right, so the tall end is on the left.
    assert dark(p.render())[75, 270] and not dark(p.render())[75, 125]
    mirrored = dark(project_at(p, 1000).render())
    assert mirrored[75, 125] and not mirrored[75, 270]


def test_scale_y_and_uniform_scale_mirror_vertically_and_both_ways():
    p = wedge(pivot=None)
    p.apply([
        {"type": "keyframe", "target": "wedge", "property": "scale-y", "time": 0, "value": -1},
        {"type": "keyframe", "target": "wedge", "property": "scale", "time": 0, "value": -0.5},
    ])
    frame = project_at(p, 0)
    layer = frame.layer("wedge")
    assert layer["flip_x"] and layer["flip_y"] is False  # -0.5 * -1 on y cancels; scale alone flips x
    assert (layer["width"], layer["height"]) == (80, 30)
    q = wedge(pivot=None)
    q.apply({"type": "keyframe", "target": "wedge", "property": "scale", "time": 0, "value": -1})
    flipped = project_at(q, 0).layer("wedge")
    assert flipped["flip_x"] and flipped["flip_y"] and (flipped["width"], flipped["height"]) == (160, 60)


def test_keyframes_compose_with_a_static_flip_and_rotation_stays_about_the_pivot():
    p = wedge()
    p.apply({"type": "flip", "target": "wedge", "direction": "horizontal"})
    assert p.layer("wedge")["flip_x"]
    p.apply({"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 0, "value": -1})
    assert not project_at(p, 0).layer("wedge")["flip_x"]  # -1 on a flipped layer flips it back
    # Rotating a mirrored layer turns it about the same canvas point as the unmirrored one.
    r = wedge()
    r.apply([
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 0, "value": -1},
        {"type": "keyframe", "target": "wedge", "property": "rotation", "time": 0, "value": 30},
    ])
    frame = project_at(r, 0)
    mirrored = frame.layer("wedge")
    pivot_x = mirrored["x"] + mirrored["pivot"][0] * mirrored["width"]
    assert pivot_x == pytest.approx(120, abs=1)
    ink = dark(frame.render())
    assert ink.any() and not ink[:, 130:].any()  # the whole wedge lies left of the point


def test_exports_agree_for_a_mirrored_animation_frame():
    p = wedge()
    p.apply([
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 0, "value": 1},
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 1000, "value": -1},
        {"type": "keyframe", "target": "wedge", "property": "rotation", "time": 0, "value": 0},
        {"type": "keyframe", "target": "wedge", "property": "rotation", "time": 1000, "value": 25},
    ])
    for t in (250, 750, 1000):
        frame = project_at(p, t)
        image, root = svg_image(frame)
        assert not root.findall(".//{*}image")
        assert overlap(frame.render(), image) > 0.95
        # Native SVG carries the mirror as a scale(-1 …) in the layer transform.
        mirrored = frame.layer("wedge")["flip_x"]
        assert ("scale(-1 1)" in ET.tostring(root, encoding="unicode")) == mirrored


def test_frames_export_matches_still_renders(tmp_path):
    from vixl.timeline import export_timeline
    import zipfile

    p = wedge()
    p.apply([
        {"type": "timeline-set", "duration": 500, "fps": 4},
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 0, "value": 1},
        {"type": "keyframe", "target": "wedge", "property": "scale-x", "time": 500, "value": -1},
    ])
    result = export_timeline(p, tmp_path / "f.zip")
    with zipfile.ZipFile(tmp_path / "f.zip") as archive:
        frames = sorted(n for n in archive.namelist() if n.endswith(".png"))
        assert len(frames) == result["frames"] == 2
        for i, name in enumerate(frames):
            exported = Image.open(io.BytesIO(archive.read(name))).convert("RGBA")
            still = project_at(p, i * 250).render()
            assert np.array_equal(np.asarray(exported), np.asarray(still))


def test_static_scale_operation_accepts_negative_and_per_axis_factors():
    p = Project(100, 100, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "bar", "width": 40, "height": 20, "x": 10, "y": 10, "fill": "black"})
    p.apply({"type": "scale", "target": "bar", "value": -2})
    bar = p.layer("bar")
    assert (bar["width"], bar["height"]) == (80, 40) and bar["flip_x"] and bar["flip_y"]
    p.apply({"type": "scale", "target": "bar", "x": -0.5})
    bar = p.layer("bar")
    assert (bar["width"], bar["height"]) == (40, 40) and not bar["flip_x"] and bar["flip_y"]
    p.apply({"type": "scale", "target": "bar", "y": 0.5, "x": 1})
    assert (p.layer("bar")["width"], p.layer("bar")["height"]) == (40, 20)
    for bad in ({"value": 0}, {"value": -1000}, {"x": 0}):
        with pytest.raises(VixlError, match="0.001"):
            p.apply({"type": "scale", "target": "bar", **bad})
    with pytest.raises(VixlError, match="requires at least one of"):
        p.apply({"type": "scale", "target": "bar"})
    # A flipped layer renders mirrored: the point of the wedge moves to the other side.
    q = wedge(pivot=None)
    q.apply({"type": "scale", "target": "wedge", "x": -1})
    assert dark(q.render())[75, 125] and not dark(q.render())[75, 270]


def test_fields_cannot_be_mirrored():
    p = Project(100, 100, "white")
    p.apply({"type": "field", "name": "email", "kind": "text", "label": "Email", "width": 60, "height": 16, "x": 5, "y": 5})
    with pytest.raises(VixlError, match="field"):
        p.apply({"type": "scale", "target": "email", "x": -1})
    with pytest.raises(VixlError, match="cannot be negative"):
        p.apply({"type": "keyframe", "target": "email", "property": "scale-x", "time": 0, "value": -1})
    p.apply({"type": "keyframe", "target": "email", "property": "scale-x", "time": 0, "value": 0.5})


def test_schema_documents_negative_scale_and_cli_compiles_it():
    from vixl.commands import compile_command
    from vixl.schema import operation_schema

    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    assert "mirror" in variants["scale"]["properties"]["value"]["description"]
    assert "mirror" in variants["scale"]["properties"]["x"]["description"]
    assert "negative" in variants["keyframe"]["properties"]["property"]["description"]
    assert "scale-x" in variants["animate"]["properties"]["property"]["description"]
    assert compile_command("scale beam -1") == {"type": "scale", "target": "beam", "value": -1.0}
    assert compile_command("scale -0.5") == {"type": "scale", "value": -0.5}
    assert compile_command("scale beam --x -1") == {"type": "scale", "target": "beam", "x": -1.0}
    assert compile_command("keyframe beam scale-x 1s -1")["value"] == -1
    assert json.dumps(compile_command("scale beam 80%")) == json.dumps({"type": "scale", "target": "beam", "value": 0.8})
