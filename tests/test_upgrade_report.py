import json
from pathlib import Path
import shutil
import zipfile

import pytest

from vixl import cli
from vixl.interfaces import Session
from vixl.project import Project
from vixl.upgrade import predates_render_changes

FIXTURE = Path(__file__).parent / "fixtures" / "saved-by-0.20.vixl"


@pytest.fixture
def old_doc(tmp_path):
    path = tmp_path / "old.vixl"
    shutil.copy(FIXTURE, path)
    return path


def names(change):
    return sorted(layer["name"] for layer in change["layers"])


def by_change(report):
    return {change["change"]: change for change in report["changes"]}


def saved_metadata(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("project.json"))


def test_versions_before_0_21_need_a_report():
    assert predates_render_changes("0.20.3") and predates_render_changes(None)
    assert not predates_render_changes("0.21.0") and not predates_render_changes("1.0")


def test_open_lists_layers_per_render_change(old_doc, tmp_path):
    result = Session(workspace=tmp_path).open("old.vixl")
    notice = result["upgrade"]
    assert notice["from_version"] == "0.20.0"
    changes = by_change(notice)
    assert names(changes["effects-before-transform"]) == ["tilted card"]
    assert names(changes["temperature-tint-scale"]) == ["warm sun"]
    assert names(changes["open-shape-fill"]) == ["open path", "squiggle rule"]
    assert "pin-fills" in notice["hint"]


def test_notice_survives_ordinary_saves_until_accepted(old_doc, tmp_path):
    project = Project.load(old_doc)
    project.apply({"type": "shape", "shape": "rectangle", "x": 0, "y": 0, "width": 5, "height": 5})
    project.save()
    assert saved_metadata(old_doc)["upgraded_from"] == "0.20.0"
    assert "upgrade" in Session(workspace=tmp_path).open("old.vixl")
    result, _ = cli.dispatch(["upgrade", str(old_doc)])
    assert result["accepted"] and result["pinned"] == []
    assert "upgraded_from" not in saved_metadata(old_doc)
    assert "upgrade" not in Session(workspace=tmp_path).open("old.vixl")


def test_report_only_changes_nothing(old_doc):
    before = old_doc.read_bytes()
    result, _ = cli.dispatch(["upgrade", str(old_doc), "--report"])
    assert "open-shape-fill" in by_change(result["report"])
    assert old_doc.read_bytes() == before


def test_pin_fills_restores_white_open_shapes(old_doc):
    result, _ = cli.dispatch(["upgrade", str(old_doc), "--pin-fills"])
    project = Project.load(old_doc)
    layers = {layer["name"]: layer for layer in project.state["layers"]}
    assert len(result["pinned"]) == 2
    assert layers["squiggle rule"]["fill"] == "white" and layers["open path"]["fill"] == "white"
    assert "fill" not in layers["closed path"]
    assert project.upgraded_from is None
    project.undo()
    assert "fill" not in {layer["name"]: layer for layer in project.state["layers"]}["open path"]


def test_mcp_open_can_pin_fills(old_doc, tmp_path):
    result = Session(workspace=tmp_path).open("old.vixl", upgrade="pin-fills")
    assert len(result["upgrade"]["pinned"]) == 2 and result["upgrade"]["accepted"]
    assert "upgrade" not in Session(workspace=tmp_path).open("old.vixl")


def test_current_documents_have_no_notice(tmp_path):
    Project(10, 10).save(tmp_path / "new.vixl")
    assert "upgrade" not in Session(workspace=tmp_path).open("new.vixl")
    assert "upgraded_from" not in saved_metadata(tmp_path / "new.vixl")
