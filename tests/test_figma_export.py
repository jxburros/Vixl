"""Offline editable Figma exports across the Python, file and REST interfaces."""

from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess

from jsonschema import Draft202012Validator
from PIL import Image
import pytest

from vixl import Project
from vixl.assets import add_encoded
from vixl.errors import VixlError
from vixl.plugins.figma_import.figma_import import import_figma_document, import_source

ROOT = Path(__file__).resolve().parents[1]


def nodes(document):
    pending, found = [document["document"]], {}
    while pending:
        node = pending.pop()
        found[node.get("name")] = node
        pending.extend(node.get("children", []))
    return found


def mixed():
    project = Project(400, 300, "white")
    project.apply([
        {"type": "shape", "name": "card", "shape": "rounded-rectangle", "width": 100, "height": 50,
         "x": 20, "y": 20, "fill_gradient": {"start": "red", "end": "blue", "direction": "horizontal"}},
        {"type": "text", "name": "label", "text": "Hello world", "size": 20, "x": 20, "y": 90, "color": "black"},
        {"type": "text-style", "target": "label", "start": 6, "end": 11, "color": "red", "bold": True},
        {"type": "shape", "name": "texture", "shape": "rectangle", "width": 60, "height": 40,
         "x": 180, "y": 20, "fill": "green"},
        {"type": "grain", "target": "texture", "amount": 0.15},
        {"type": "shape", "name": "line", "shape": "path", "path": "M5 5 C20 30 40 30 55 5",
         "width": 60, "height": 40, "x": 200, "y": 100, "stroke": "black", "stroke_width": 2},
    ])
    png = io.BytesIO()
    Image.new("RGB", (16, 12), (250, 100, 20)).save(png, "PNG")
    asset, _ = add_encoded(project, png.getvalue())
    project.apply({"type": "add", "asset": asset, "name": "photo", "x": 270, "y": 180})
    return project


def test_mixed_export_validates_and_keeps_editable_fields_with_explicit_losses():
    project = mixed()
    before = deepcopy(project.state)
    report = {}
    document = json.loads(project.export(format="FIGMA", report=report))
    schema = json.loads((ROOT / "src/vixl/data/figma-interchange.schema.json").read_text())
    Draft202012Validator(schema).validate(document)
    found = nodes(document)
    assert found["card"]["type"] == "RECTANGLE"
    assert found["card"]["fills"][0]["type"] == "GRADIENT_LINEAR"
    assert found["label"]["characters"] == "Hello world"
    assert found["label"]["styleOverrideTable"]["2"]["fontWeight"] == 700
    assert found["line"]["type"] == "VECTOR" and not found["line"]["fills"]
    assert found["photo"]["fills"][0]["type"] == "IMAGE"
    assert found["RASTER: texture"]["fills"][0]["imageRef"] in document["images"]
    assert any("grain" in item["reason"] for item in report["unmapped"])
    assert project.state == before


def test_exported_images_and_text_import_offline_without_missing_assets():
    project = mixed()
    imported = Project(1, 1)
    result = import_source(imported, project.export(format="FIGMA"), install_fonts=False)
    assert result["figma"]["images_missing"] == 0
    assert imported.layer("label")["text"] == "Hello world"
    assert imported.layer("label")["rich"]["spans"][-1]["color"] == "#ff0000"
    assert imported.layer("photo")["asset"] in imported.assets
    assert imported.layer("RASTER: texture")["asset"] in imported.assets


def test_suffix_inference_and_overwrite_refusal(tmp_path):
    project = mixed()
    path = tmp_path / "poster.figma.json"
    project.export(path)
    assert json.loads(path.read_bytes())["format"] == "vixl-figma-1"
    with pytest.raises(VixlError) as caught:
        project.export(path)
    assert caught.value.code == "output_exists"
    project.export(path, overwrite=True)


def test_all_pages_and_page_selection():
    project = mixed()
    project.apply({"type": "page", "action": "add", "name": "second"})
    project.apply({"type": "text", "name": "title", "text": "Second", "size": 24})
    all_pages = json.loads(project.export(format="FIGMA", pages="all"))
    assert len(all_pages["document"]["children"]) == 2
    one = json.loads(project.export(format="FIGMA", page="second"))
    assert [page["name"] for page in one["document"]["children"]] == ["second"]
    assert "title" in nodes(one) and "card" not in nodes(one)


def test_artboards_become_separate_frames():
    project = mixed()
    project.apply([
        {"type": "artboard", "name": "square", "width": 200, "height": 200},
        {"type": "artboard", "name": "wide", "width": 400, "height": 200},
    ])
    document = json.loads(project.export(format="FIGMA"))
    frames = document["document"]["children"][0]["children"]
    assert [(frame["name"], frame["size"]) for frame in frames] == [
        ("square", {"x": 200, "y": 200}), ("wide", {"x": 400, "y": 200})]


def test_native_stack_and_clipping_mask_group():
    project = Project(300, 200)
    project.apply([
        {"type": "shape", "name": "a", "shape": "rectangle", "width": 40, "height": 30},
        {"type": "shape", "name": "b", "shape": "ellipse", "width": 30, "height": 30},
        {"type": "stack", "name": "row", "targets": ["a", "b"], "direction": "horizontal", "gap": 12,
         "padding": 8, "size": "hug", "background": "red"},
        {"type": "shape", "name": "mask", "shape": "ellipse", "width": 60, "height": 60, "x": 180},
        {"type": "shape", "name": "clipped", "shape": "rectangle", "width": 80, "height": 40, "x": 160},
        {"type": "clip", "target": "clipped", "base": "mask"},
    ])
    found = nodes(json.loads(project.export(format="FIGMA")))
    assert found["row"]["layoutMode"] == "HORIZONTAL" and found["row"]["itemSpacing"] == 12
    assert [child["name"] for child in found["row"]["children"]] == ["a", "b"]
    assert found["row"]["fills"][0]["color"] == {"r": 1.0, "g": 0.0, "b": 0.0}
    group = found["clipped clipped"]
    assert group["children"][0]["isMask"] is True and group["children"][1]["name"] == "clipped"


@pytest.mark.parametrize("damage", ["base64", "version", "transform"])
def test_invalid_interchange_refuses_atomically(damage):
    document = json.loads(mixed().export(format="FIGMA"))
    if damage == "base64":
        next(iter(document["images"].values()))["base64"] = "not-base64!"
    elif damage == "version":
        document["format"] = "vixl-figma-999"
    else:
        document["document"]["children"][0]["children"][0]["relativeTransform"] = [[1]]
    project = Project(10, 10)
    before = deepcopy(project.state)
    with pytest.raises(VixlError) as caught:
        import_figma_document(project, document)
    assert caught.value.code == "invalid_figma_document"
    assert project.state == before


def test_rest_exports_figma_json(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    path = tmp_path / "source.vixl"
    mixed().save(path)
    response = TestClient(create_app(path)).post("/export", json={"format": "FIGMA"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["format"] == "vixl-figma-1"


def test_figma_plugin_imports_the_interchange_with_a_mock_api(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the offline Figma plugin contract test")
    exported = tmp_path / "source.figma.json"
    mixed().export(exported)
    result = subprocess.run([node, str(ROOT / "tests/fixtures/figma/plugin_mock.cjs"),
                             str(ROOT / "integrations/figma-plugin/code.js"), str(exported)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["pages"] == 1 and any("grain" in message for message in report["warnings"])
