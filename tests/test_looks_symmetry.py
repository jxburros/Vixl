"""Finishing looks and radial repeat (issue #88)."""

import json
import math
import re

import numpy as np
import pytest

from vixl import Project, VixlError
from vixl.looks import LOOKS, catalog
from vixl.render import resolve_layout


def stage():
    project = Project(800, 600, "#f1f5f9")
    project.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 100, "y": 100, "width": 300, "height": 200, "radius": 24,
         "fill": "#6366f1"},
        {"type": "text", "text": "Hello", "name": "title", "size": 60, "color": "#111827", "x": 460, "y": 120},
        {"type": "solid", "name": "paper-bg", "color": "#f1f5f9", "width": 800, "height": 600},
    ])
    project.apply({"type": "bottom", "target": "paper-bg"})
    return project


def changed_pixels(before, after):
    a, b = np.asarray(before.convert("RGBA"), dtype=np.int16), np.asarray(after.convert("RGBA"), dtype=np.int16)
    return int((np.abs(a - b).max(axis=2) > 6).sum())


@pytest.mark.parametrize("look", sorted(LOOKS))
def test_every_look_applies_changes_pixels_and_removes_cleanly(look):
    project = stage()
    plain = project.render()
    before = json.dumps(project.state["layers"], sort_keys=True)
    project.apply({"type": "look", "target": "card", "look": look})
    assert look in project.layer("card")["looks"]
    if look == "clean-flat":
        assert changed_pixels(plain, project.render()) == 0
    else:
        assert changed_pixels(plain, project.render()) > 100, f"{look} changed nothing visible"
    # Applying again replaces rather than stacks.
    project.apply({"type": "look", "target": "card", "look": look, "amount": 0.9})
    card = project.layer("card")
    assert len(card["effects"]) == len(LOOKS[look][0](card, project.state, None, 0.5)[1])
    project.apply({"type": "look", "target": "card", "look": look, "remove": True})
    assert json.dumps(project.state["layers"], sort_keys=True).replace('"looks": {}, ', "") == before or \
        "looks" not in project.layer("card")
    assert not project.layer("card")["effects"] and not project.layer("card").get("styles")
    assert changed_pixels(plain, project.render()) == 0


def test_looks_use_the_layers_own_color_and_scale_with_amount():
    project = stage()
    project.apply({"type": "look", "target": "card", "look": "glow", "color": "#ff0000", "amount": 0.2})
    soft = project.layer("card")["styles"]["outer-glow"]
    project.apply({"type": "look", "target": "card", "look": "glow", "color": "#ff0000", "amount": 1})
    strong = project.layer("card")["styles"]["outer-glow"]
    assert strong["blur"] > soft["blur"] and strong["opacity"] > soft["opacity"] and strong["color"] == "#ff0000"
    project.apply({"type": "look", "target": "card", "look": "glow", "remove": True})
    project.apply({"type": "look", "target": "card", "look": "glow"})
    assert project.layer("card")["styles"]["outer-glow"]["color"] == "#6366f1"  # the fill


def test_looks_stack_without_disturbing_hand_made_styles_and_share_styles_by_ownership():
    project = stage()
    project.apply({"type": "layer-style", "target": "card", "name": "stroke", "settings": {"color": "#000000", "width": 3}})
    project.apply({"type": "look", "target": "card", "look": "soft-shadow"})
    project.apply({"type": "look", "target": "card", "look": "grain"})
    project.apply({"type": "look", "target": "card", "look": "hard-shadow"})  # takes the drop-shadow over
    card = project.layer("card")
    assert card["styles"]["drop-shadow"]["blur"] == 0 and "stroke" in card["styles"]
    assert set(card["looks"]) == {"soft-shadow", "grain", "hard-shadow"} and card["looks"]["soft-shadow"]["styles"] == []
    project.apply({"type": "look", "target": "card", "look": "soft-shadow", "remove": True})
    assert "drop-shadow" in project.layer("card")["styles"]  # still owned by hard-shadow
    project.apply({"type": "look", "target": "card", "look": "grain", "remove": True})
    assert not project.layer("card")["effects"]
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "look", "target": "card", "look": "paper", "remove": True})
    assert "no 'paper' look" in str(caught.value)


def test_look_validates_names_colors_and_targets():
    project = stage()
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "look", "target": "card", "look": "gloww"})
    assert "glow" in str(caught.value)
    with pytest.raises(VixlError):
        project.apply({"type": "look", "target": "card", "look": "glow", "color": "not-a-color"})
    with pytest.raises(VixlError):
        project.apply({"type": "look", "target": "card", "look": "glow", "amount": 3})
    project.apply({"type": "look", "targets": ["card", "title"], "look": "soft-shadow"})
    assert "looks" in project.layer("title")


def test_looks_survive_save_load_undo_and_the_svg_policy(tmp_path):
    project = stage()
    project.apply({"type": "look", "target": "card", "look": "neon", "color": "#22d3ee"})
    path = tmp_path / "d.vixl"
    project.save(path)
    again = Project.load(path)
    assert again.layer("card")["looks"]["neon"]["styles"] == ["stroke", "outer-glow"]
    svg = project.export(format="SVG", svg_policy="strict").decode()
    assert "feGaussianBlur" in svg and "<image" not in svg  # native filters, no raster fallback
    project.apply({"type": "look", "target": "card", "look": "grain"})
    assert LOOKS["grain"][2] == "raster"
    with pytest.raises(VixlError):
        project.export(format="SVG", svg_policy="strict")  # same policy as a hand-added grain effect
    assert b"<image" in project.export(format="SVG", svg_policy="appearance")
    project.undo()
    assert "grain" not in project.layer("card")["looks"]


def test_look_catalog_is_described_and_matches_the_operation_enum():
    from vixl.schema import operation_schema

    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    assert set(variants["look"]["properties"]["look"]["enum"]) == set(LOOKS)
    for name, row in catalog().items():
        assert row["summary"] and row["svg"] in ("native", "raster") and row["best_for"], name


# ---------------------------------------------------------------------------------------------
# Radial repeat


def centers(project, names):
    """Canvas-space centers of layers (layout bounds are local to a layer's group)."""
    from vixl.checks import canvas_projection
    from vixl.render import resolved_layers

    resolved = {item["id"]: item for item in resolved_layers(project)}
    bounds = canvas_projection(resolved, resolve_layout(project, layers=list(resolved.values())))["bounds"]
    out = []
    for name in names:
        x, y, w, h = bounds[project.layer(name)["id"]]
        out.append((x + w / 2, y + h / 2))
    return out


def test_radial_repeat_places_copies_on_a_circle_and_groups_them():
    project = Project(800, 600, "#ffffff")
    project.apply({"type": "shape", "shape": "ellipse", "name": "petal", "x": 380, "y": 100, "width": 40, "height": 120, "fill": "#7c3aed"})
    project.apply({"type": "radial-repeat", "target": "petal", "count": 8, "name": "ring"})
    names = ["petal"] + [f"petal-{i}" for i in range(2, 9)]
    assert project.layer("ring")["type"] == "group"
    assert project.layer("ring")["radial"] == {"count": 8, "center": [400.0, 300.0], "sweep": 360.0, "start_angle": 0.0, "mirror": False}
    points = centers(project, names)
    radii = [math.dist(point, (400, 300)) for point in points]
    assert max(radii) - min(radii) < 1.5  # a circle about the canvas center
    angles = sorted(math.degrees(math.atan2(y - 300, x - 400)) % 360 for x, y in points)
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    assert all(abs(gap - 45) < 1.5 for gap in gaps)
    # Each copy is turned to face outward: the rotation grows by 360/8 per copy.
    assert [project.layer(n)["rotation"] for n in names] == [i * 45 for i in range(8)]
    assert all(project.layer(n)["parent"] == project.layer("ring")["id"] for n in names)


def test_radial_repeat_matches_the_rendered_picture_of_a_rotated_copy():
    """Copy N drawn by the operation equals the original drawn by hand at the same angle about the center."""
    base = {"type": "shape", "shape": "rectangle", "name": "bar", "x": 380, "y": 60, "width": 30, "height": 140, "fill": "#dc2626"}
    project = Project(800, 800, "#ffffff")
    project.apply(base)
    project.apply({"type": "radial-repeat", "target": "bar", "count": 4, "cx": 400, "cy": 400})
    # The engine's own definition of turning about a point: a pivot at the circle's center, then rotate.
    expected = Project(800, 800, "#ffffff")
    for i in range(4):
        expected.apply({**base, "name": f"bar{i}"})
        expected.apply({"type": "pivot", "target": f"bar{i}", "value": [400 - 380, 400 - 60], "units": "px"})
        expected.apply({"type": "rotate", "target": f"bar{i}", "value": 90 * i})
    assert changed_pixels(project.render(), expected.render()) < 40


def test_radial_repeat_mirror_gives_reflection_symmetry():
    project = Project(800, 800, "#ffffff")
    project.apply({"type": "shape", "shape": "star", "name": "leaf", "x": 330, "y": 80, "width": 90, "height": 160, "fill": "#16a34a"})
    project.apply({"type": "radial-repeat", "target": "leaf", "count": 6, "mirror": True, "cx": "50%", "cy": "50%"})
    assert len([x for x in project.state["layers"] if x["type"] != "group"]) == 12
    image = np.asarray(project.render().convert("RGB"), dtype=np.int16)
    flipped = image[:, ::-1]
    assert (np.abs(image - flipped).max(axis=2) > 24).mean() < 0.01  # left-right mirror symmetric


def test_radial_repeat_sweep_fan_start_angle_and_ungrouped():
    project = Project(600, 600, "#ffffff")
    project.apply({"type": "shape", "shape": "rectangle", "name": "ray", "x": 290, "y": 40, "width": 20, "height": 120, "fill": "#000000"})
    project.apply({"type": "radial-repeat", "target": "ray", "count": 5, "sweep": 120, "start_angle": -60, "group": False})
    rotations = [project.layer(n)["rotation"] for n in ["ray"] + [f"ray-{i}" for i in range(2, 6)]]
    assert rotations == [300, 330, 0, 30, 60]  # -60 .. +60 degrees in four steps
    assert all(not x.get("parent") for x in project.state["layers"])
    with pytest.raises(VixlError):
        project.apply({"type": "radial-repeat", "target": "ray", "count": 3, "group": False, "name": "x"})


def test_radial_repeat_handles_existing_rotation_pivot_groups_and_limits():
    project = Project(600, 600, "#ffffff")
    project.apply({"type": "shape", "shape": "ellipse", "name": "dot", "x": 280, "y": 40, "width": 40, "height": 40, "fill": "#000000"})
    project.apply({"type": "pivot", "target": "dot", "value": "top-left"})
    project.apply({"type": "rotate", "target": "dot", "value": 30})
    project.apply({"type": "radial-repeat", "target": "dot", "count": 3})
    assert "pivot" not in project.layer("dot-2") and project.layer("dot-2")["rotation"] == 150  # 30 + 120
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "radial-repeat", "target": "dot-2", "count": 200, "mirror": True})
    assert "At most 360 copies" in str(caught.value)
    with pytest.raises(VixlError):
        project.apply({"type": "radial-repeat", "target": "dot-2", "count": 1})
    # Inside a group the center is measured in the group's own coordinates.
    inner = Project(600, 600, "#ffffff")
    inner.apply([{"type": "shape", "shape": "rectangle", "name": "a", "x": 100, "y": 100, "width": 40, "height": 40, "fill": "#000"},
                 {"type": "shape", "shape": "rectangle", "name": "b", "x": 300, "y": 300, "width": 40, "height": 40, "fill": "#000"},
                 {"type": "group", "name": "pair", "targets": ["a", "b"]}])
    inner.apply({"type": "radial-repeat", "target": "a", "count": 4, "group": False})
    assert all(x["parent"] == inner.layer("pair")["id"] for x in inner.state["layers"] if x["name"].startswith("a"))


def test_radial_repeat_cli(tmp_path, capsys, monkeypatch):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)

    def run(*argv):
        capsys.readouterr()
        assert main(list(argv)) in (0, None)
        return json.loads(capsys.readouterr().out)

    run("new", "400x400", "-o", "r.vixl")
    run("-p", "r.vixl", "shape", "ellipse", "--name", "p", "--x", "180", "--y", "20", "--width", "40", "--height", "100", "--fill", "red")
    result = run("-p", "r.vixl", "radial-repeat", "p", "--count", "6", "--mirror", "--name", "flower")
    assert result["success"]
    assert re.search(r"flower", json.dumps(result))
    looked = run("-p", "r.vixl", "look", "flower", "glow", "--amount", "0.8")
    assert looked["success"]
    assert "glow" in run("looks")["looks"]
