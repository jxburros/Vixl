"""A cheap critique (craft plan 3b): apply with check returns the composition findings, wherever they are, and the
two weakest regions; with preview, real-size crops of those regions follow the preview."""

import asyncio
import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from vixl import Project
from vixl.checks import apply_reviewed
from vixl.critique import weakest_regions
from vixl.interfaces import create_app, mcp_server

from test_composition import doc, text

NUDGE = [{"type": "move", "target": "note", "x": 0, "y": 0, "relative": True}]


def drifting():
    """A title and subtitle two margins apart, and an untouched note far below them."""
    return doc(text("title", 60, 60), text("subtitle", 72, 100), text("note", 600, 800, 20))


def size(png):
    return Image.open(io.BytesIO(png)).size


def test_check_lists_composition_findings_on_untouched_layers_and_the_weakest_regions():
    p = drifting()
    result, image = apply_reviewed(p, NUDGE, check=True)
    assert image is None
    issues = result["check"]["issues"]
    (drift,) = [i for i, x in enumerate(issues) if x["check"] == "composition"]
    assert issues[drift]["code"] == "margin_drift" and "note" not in issues[drift]["layers"]
    first, second = result["check"]["regions"]
    assert drift in first["findings"] and "composition.margin_drift" in first["why"]
    x, y, w, h = issues[drift]["region"]
    assert first["region"][0] <= x and first["region"][1] <= y  # padded around the finding
    assert second["why"] in ("the densest block of text", "the largest empty area") and second["findings"] == []
    assert "preview" not in first  # no crops without a preview


def test_preview_brings_real_size_crops_of_the_regions():
    p = drifting()
    result, image = apply_reviewed(p, NUDGE, check=True, preview=True)
    regions = result["check"]["regions"]
    assert image.startswith(b"\x89PNG") and all(entry["preview"].startswith(b"\x89PNG") for entry in regions)
    first = regions[0]
    # One canvas pixel per image pixel (the region is under the 512 px side).
    assert size(first["preview"]) == tuple(first["region"][2:])
    assert max(size(regions[1]["preview"])) <= 512
    quiet, _ = apply_reviewed(drifting(), NUDGE, check=True, preview={"regions": 0})
    assert all("preview" not in entry for entry in quiet["check"]["regions"])
    one, _ = apply_reviewed(drifting(), NUDGE, check=True, preview={"regions": 1})
    assert ["preview" in entry for entry in one["check"]["regions"]] == [True, False]
    with pytest.raises(Exception, match="regions"):
        apply_reviewed(drifting(), NUDGE, check=True, preview={"regions": 3})


def test_without_findings_the_regions_are_the_densest_text_and_the_largest_space():
    p = Project(800, 600, "white")
    p.apply([{"type": "text", "name": "a", "text": "Hello there", "x": 50, "y": 50, "size": 30, "color": "#111111"}])
    regions = weakest_regions(p, [])
    assert [entry["why"] for entry in regions] == ["the densest block of text", "the largest empty area"]
    x, y, w, h = regions[0]["region"]
    assert x <= 50 and y <= 50 and w < 300 and h < 100
    assert regions[1]["region"][2] * regions[1]["region"][3] > 0.5 * 800 * 600


def test_the_most_and_most_severe_findings_come_first():
    p = Project(1000, 1000, "white")
    issues = [
        {"check": "overlap", "severity": "warning", "action": "review", "box": [700, 700, 50, 50]},
        {"check": "composition", "severity": "warning", "action": "review", "region": [100, 100, 200, 50]},
        {"check": "bounds", "severity": "error", "action": "fix", "box": [120, 110, 30, 30]},
        {"check": "fonts", "severity": "warning", "action": "fix", "box": [700, 700, 50, 50]},
        {"check": "composition", "severity": "warning", "action": "informational", "region": [700, 700, 50, 50]},
    ]
    first, second = weakest_regions(p, issues)
    assert first["findings"] == [1, 2] and first["score"] == 6
    assert second["findings"] == [0] and second["score"] == 2


def test_mcp_rest_and_cli_return_the_region_crops(tmp_path):
    from vixl.cli import main

    drifting().save(tmp_path / "a.vixl")
    server = mcp_server(workspace=tmp_path)

    async def run():
        result = await server.call_tool("vixl_apply", {"operations": NUDGE, "check": True, "preview": True,
                                                                  "document": "a.vixl"})
        return result[0] if isinstance(result, tuple) else result

    content = asyncio.run(run())
    body = json.loads(content[0].text)
    assert len(content) == 4 and all(part.type == "image" for part in content[1:])
    # The first image is the preview; the crops follow in the order of the regions.
    assert [entry["preview"] for entry in body["check"]["regions"]] == ["image 2 of 3", "image 3 of 3"]

    rest = TestClient(create_app(tmp_path / "a.vixl")).post("/operations", json={
        "operations": NUDGE, "check": True, "preview": True}).json()
    assert all(base64.b64decode(entry["preview_base64"]).startswith(b"\x89PNG") for entry in rest["check"]["regions"])

    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps(NUDGE))
    assert main(["--project", str(tmp_path / "a.vixl"), "apply", str(ops), "--check", "--preview",
                 str(tmp_path / "p.png")]) == 0
    assert (tmp_path / "p-region1.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "p-region2.png").exists()
