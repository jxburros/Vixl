"""Figma interchange preserves world geometry across groups, paths and fallbacks."""

import json

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.model import Limits
from vixl.plugins.figma_import.figma_export import export_figma
from vixl.plugins.figma_import.figma_import import import_figma_document


def roundtrip(project):
    document = json.loads(export_figma(project))
    imported = Project(1, 1)
    report = import_figma_document(imported, document)
    return document, imported, report


def nodes(document):
    pending = [document["document"]]
    found = {}
    while pending:
        node = pending.pop()
        found[node.get("name")] = node
        pending.extend(node.get("children", []))
    return found


def scene():
    project = Project(400, 300, "white")
    project.apply([
        {"type": "shape", "name": "a", "shape": "rectangle", "width": 50, "height": 30,
         "x": 100, "y": 100, "fill": "red"},
        {"type": "shape", "name": "b", "shape": "ellipse", "width": 30, "height": 20,
         "x": 180, "y": 140, "fill": "blue"},
    ])
    return project


def test_rotated_group_exports_world_bounding_boxes_for_its_children():
    project = scene()
    project.apply([{"type": "group", "name": "g", "targets": ["a", "b"]},
                   {"type": "rotate", "target": "g", "value": 30}])
    document, imported, _ = roundtrip(project)
    exported = nodes(document)
    for name in ("a", "b"):
        expected = project.inspect(name)["canvas_bounds"]
        box = exported[name]["absoluteBoundingBox"]
        assert np.allclose(list(box.values()), expected, atol=0.01)
        assert np.allclose(imported.inspect(name)["canvas_bounds"], expected, atol=1)


def test_nested_scaled_and_mirrored_group_keeps_child_geometry():
    project = scene()
    project.apply([
        {"type": "group", "name": "inner", "targets": ["a", "b"]},
        {"type": "resize", "target": "inner", "width": 170, "height": 100},
        {"type": "flip", "target": "inner", "direction": "horizontal"},
        {"type": "group", "name": "outer", "targets": ["inner"]},
        {"type": "rotate", "target": "outer", "value": 15},
    ])
    _, imported, _ = roundtrip(project)
    for name in ("a", "b"):
        assert np.allclose(imported.inspect(name)["canvas_bounds"], project.inspect(name)["canvas_bounds"], atol=1)


def test_resized_stack_keeps_fixed_positions_and_reports_auto_layout_loss():
    project = scene()
    project.apply([
        {"type": "stack", "name": "stack", "targets": ["a", "b"], "direction": "horizontal",
         "gap": 15, "padding": 10},
        {"type": "resize", "target": "stack", "width": 240, "height": 100},
    ])
    document, imported, _ = roundtrip(project)
    assert "layoutMode" not in nodes(document)["stack"]
    assert any("fixed positions" in item["reason"] for item in document["report"]["unmapped"])
    for name in ("a", "b"):
        assert np.allclose(imported.inspect(name)["canvas_bounds"], project.inspect(name)["canvas_bounds"], atol=1)


def test_diagonal_line_stays_a_diagonal_editable_path():
    project = Project(140, 100, "white")
    project.apply({"type": "shape", "name": "line", "shape": "line", "width": 100, "height": 60,
                   "x": 20, "y": 20, "stroke": "red", "stroke_width": 4})
    document, imported, _ = roundtrip(project)
    line = nodes(document)["line"]
    assert line["type"] == "VECTOR" and line["strokeCap"] == "NONE"
    assert "L98 58" in line["fillGeometry"][0]["path"]
    assert np.abs(np.asarray(imported.render(), dtype=int) - np.asarray(project.render(), dtype=int)).mean() < 1


def test_transformed_raster_fallback_keeps_its_opacity_once():
    project = Project(160, 120, "white")
    project.apply([
        {"type": "shape", "name": "paint", "shape": "rectangle", "width": 80, "height": 50,
         "x": 40, "y": 30, "fill": "red"},
        {"type": "grain", "target": "paint", "amount": 0.1},
        {"type": "rotate", "target": "paint", "value": 15},
        {"type": "opacity", "target": "paint", "value": 0.5},
    ])
    document, imported, _ = roundtrip(project)
    node = nodes(document)["RASTER: paint"]
    assert node["opacity"] == 0.5
    assert document["report"]["unmapped"]
    assert np.abs(np.asarray(imported.render(), dtype=int) - np.asarray(project.render(), dtype=int)).mean() < 1


@pytest.mark.parametrize("direction,fields", [("angled", {"angle": 35}), ("radial", {"center": [0.3, 0.4]})])
def test_gradient_handles_roundtrip_without_changing_the_ramp(direction, fields):
    project = Project(120, 80, "white")
    project.apply({"type": "gradient", "name": "ramp", "direction": direction,
                   "start": "red", "end": "blue", **fields})
    _, imported, report = roundtrip(project)
    assert report["report"] == []
    assert np.abs(np.asarray(imported.render(), dtype=int) - np.asarray(project.render(), dtype=int)).mean() < 1


def test_rich_leading_and_paragraph_spacing_are_explicit():
    project = Project(200, 200, "white")
    project.apply({"type": "rich-text", "name": "text", "markdown": "one\ntwo", "size": 24,
                   "line_height": 2, "paragraph_spacing": 10,
                   "paragraphs": [{}, {"align": "center", "space_before": 6}]})
    document = json.loads(export_figma(project))
    node = nodes(document)["text"]
    assert node["style"]["lineHeightPx"] == 48
    assert node["style"]["paragraphSpacing"] == 10
    assert any("per-paragraph" in item["reason"] for item in document["report"]["unmapped"])


def test_text_on_a_path_uses_a_reported_raster_fallback():
    project = Project(200, 100, "white")
    project.apply([
        {"type": "text", "name": "curved", "text": "Along the curve", "size": 18, "color": "black"},
        {"type": "text-layout", "target": "curved", "width": 180, "height": 80,
         "path": [[0, 40], [80, 0], [160, 40]]},
    ])
    document = json.loads(export_figma(project))
    assert nodes(document)["RASTER: curved"]["fills"][0]["type"] == "IMAGE"
    assert any("special text" in item["reason"] for item in document["report"]["unmapped"])


def test_raster_and_total_interchange_size_limits_are_enforced():
    project = scene()
    project.apply({"type": "grain", "target": "a", "amount": 0.1})
    project.limits = Limits(max_asset_bytes=10)
    with pytest.raises(VixlError) as image_error:
        export_figma(project)
    assert image_error.value.code == "resource_limit"
    project = scene()
    project.limits = Limits(max_project_bytes=100)
    with pytest.raises(VixlError) as file_error:
        export_figma(project)
    assert file_error.value.code == "resource_limit"
