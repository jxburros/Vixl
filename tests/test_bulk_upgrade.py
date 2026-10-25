"""Bulk structure upgrades (#578): convert, rename and re-role many documents with before/after checks and a render
diff; dry run by default, journalled commit."""

import json
from pathlib import Path
import shutil
import zipfile

import pytest

from vixl import Project, __version__
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "convert"
MAP = {"title": {"rename": "headline", "role": "headline"}, "card*": {"role": "panel"}}


@pytest.fixture
def old(tmp_path):
    chosen = sorted(FIXTURES.glob("v0.*/*.vixl"))[:10]
    assert len(chosen) == 10
    (tmp_path / "old").mkdir()
    for path in chosen:
        shutil.copy(path, tmp_path / "old" / f"{path.parent.name}-{path.stem}.vixl")
    return Session(None, workspace=tmp_path)


def snapshot(session):
    return {p.name: p.read_bytes() for p in session.resolve("old").glob("*.vixl")}


def test_a_dry_run_over_old_documents_reports_every_change_and_writes_nothing(old):
    before = snapshot(old)
    result = dispatch(old, "bulk-upgrade", {"documents": ["old/*.vixl"], "map": MAP})
    assert result["dry_run"] and result["written"] is False and result["count"] == 10
    assert snapshot(old) == before and not old.resolve(".vixl-groups").exists()
    entries = {entry["document"]: entry for entry in result["documents"]}
    text = entries["old/v0.10.0-text.vixl"]
    assert "text-box-height" in text["conversion"]["changes"] and text["before"]["status"] == "error"
    assert text["renamed"] == [{"from": "title", "to": "headline"}] and text["roles"] == {"headline": 1}
    # The original cannot be opened by this release, so findings of the upgraded copy hold it for a look.
    assert text["status"] == "held" and text["newly_failing"] and "could not be checked" in text["reason"]
    effects = entries["old/v0.20.0-effects.vixl"]
    assert effects["status"] == "upgraded" and effects["roles"] == {"panel": 1}
    assert effects["before"]["status"] == effects["after"]["status"] == "passed"
    assert {"changed_fraction", "changed_pixels"} <= set(effects["diff"])
    assert all(entry["status"] in ("upgraded", "unchanged", "held") for entry in result["documents"])


def test_the_upgrade_is_published_through_a_journal_and_an_interrupted_one_is_recoverable(old, monkeypatch):
    before = snapshot(old)
    request = {"documents": ["old/*.vixl"], "map": MAP, "dry_run": False}
    import vixl.plugins.teamwork.project_groups as groups

    publish = groups.publish_file

    def interrupted(path, source, **kwargs):
        if str(source).endswith(".before.vixl") or path.name == "v0.20.0-shapes.vixl":
            raise OSError("Simulated crash")
        return publish(path, source, **kwargs)

    monkeypatch.setattr(groups, "publish_file", interrupted)
    with pytest.raises(OSError):
        dispatch(old, "bulk-upgrade", request)
    monkeypatch.setattr(groups, "publish_file", publish)
    with pytest.raises(VixlError, match="Recover"):
        dispatch(old, "bulk-upgrade", request)
    dispatch(old, "group-recover", {"name": "bulk-upgrade"})
    assert snapshot(old) == before
    applied = dispatch(old, "bulk-upgrade", request)
    assert applied["written"] and len(applied["published"]) == applied["counts"]["upgraded"]
    assert applied["recover"] == {"workflow": "group-recover", "request": {"name": "bulk-upgrade"}}
    assert "old/v0.10.0-text.vixl" not in applied["published"]  # held: left as it was
    assert old.resolve("old/v0.10.0-text.vixl").read_bytes() == before["v0.10.0-text.vixl"]
    upgraded = Project.load(old.resolve("old/v0.10.0-effects.vixl"))
    assert upgraded.state["roles"]["panel"] == [upgraded.layer("card")["id"]]
    with zipfile.ZipFile(old.resolve("old/v0.10.0-effects.vixl")) as archive:
        assert json.loads(archive.read("project.json"))["vixl_version"] == __version__


def test_a_template_is_re_applied_keeping_the_copy_of_its_roles(tmp_path):
    p = Project(1080, 1080, "#ffffff")
    p.apply([{"type": "layout-apply", "name": "hero-statement", "title": "Old headline", "subtitle": "Old line",
              "label": "News", "cta": "Read more", "seed": 4}])
    title = next(layer for layer in p.state["layers"] if layer.get("text") == "Old headline")
    title["name"] = "Title text"
    p.save(tmp_path / "hero.vixl")
    session = Session(None, workspace=tmp_path)
    result = dispatch(session, "bulk-upgrade", {"documents": ["hero.vixl"], "convert": False, "dry_run": False,
                                                "map": {"Title*": {"role": "headline"}},
                                                "template": "hero-statement"})
    entry = result["documents"][0]
    assert entry["status"] == "upgraded" and entry["template"] == {"name": "hero-statement",
                                                                   "slots": ["cta", "label", "subtitle", "title"]}
    texts = [layer.get("text") for layer in Project.load(tmp_path / "hero.vixl").state["layers"]]
    assert {"old headline", "old line", "news", "read more"} <= {t.lower() for t in texts if t}


def test_a_request_needs_documents_and_known_fields(old):
    with pytest.raises(VixlError, match="documents"):
        dispatch(old, "bulk-upgrade", {})
    with pytest.raises(VixlError, match="Unknown workflow request field"):
        dispatch(old, "bulk-upgrade", {"documents": ["old/*.vixl"], "rename": {}})
