"""Link impact (#560): check every document that links to a changed source on a refreshed candidate."""

import json

import pytest

from vixl import Project
from vixl.interfaces import Session
from vixl.workflows import dispatch
from vixl.plugins.workspace_qa.workspace_checks import render


def logo(path, width=100):
    p = Project(width, 40, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "mark", "x": 0, "y": 0, "width": width, "height": 40,
             "fill": "#ff6a00"})
    p.save(path, overwrite=True)


def host(path, source, x, *, size=(400, 200), suite=True):
    p = Project(*size, "white", workspace=path.parent)
    p.path = str(path)
    p.apply([{"type": "text", "name": "headline", "text": "Launch", "size": 28, "x": 20, "y": 20,
              "color": "#111111"},
             {"type": "link", "source": source, "name": "logo", "x": x, "y": 140}])
    if suite:
        p.apply({"type": "suite-set", "name": "placement", "suite": {"rules": [
            {"id": "logo-inside", "kind": "relation", "target": "logo", "to": "canvas", "position": "inside"}]}})
    p.save(path, overwrite=True)


@pytest.fixture
def workspace(tmp_path):
    logo(tmp_path / "logo.vixl")
    host(tmp_path / "page.vixl", "logo.vixl", 280)   # a wider logo runs off the right edge
    host(tmp_path / "wide.vixl", "logo.vixl", 20)    # room to grow
    host(tmp_path / "nested.vixl", "page.vixl", 0, size=(500, 400), suite=False)
    logo(tmp_path / "logo.vixl", width=160)
    return Session(None, workspace=tmp_path)


def stamps(session):
    return {path.name: path.stat().st_mtime_ns for path in session.workspace.glob("*.vixl")}


def test_widening_a_linked_logo_fails_the_dependent_relation_rule_and_is_read_only(workspace):
    before = stamps(workspace)
    result = dispatch(workspace, "link-impact", {"source": "logo.vixl"})
    assert stamps(workspace) == before and result["apply"] == "never" and "published" not in result
    assert result["passed"] is False
    assert sorted(result["passes"]) == ["nested.vixl", "wide.vixl"]
    failed = {item["document"]: item for item in result["fails"]}
    assert set(failed) == {"page.vixl"}
    rule = failed["page.vixl"]["rules"]["placement"][0]
    assert rule["id"] == "logo-inside" and rule["status"] == "failed"
    entries = {entry["path"]: entry for entry in result["documents"]}
    assert entries["page.vixl"]["links"][0]["resized"] == {"from": [100, 40], "to": [160, 40]}
    assert entries["page.vixl"]["links"][0]["stale"] is True
    assert {item["document"] for item in result["changed"]} >= {"page.vixl", "wide.vixl"}
    # Every report format renders it.
    assert "Vixl link impact: logo.vixl" in render(result, "markdown")
    assert "logo-inside" in render(result, "junit") and json.loads(render(result, "sarif"))["runs"]


def test_nested_links_are_found_through_the_tree(workspace):
    result = dispatch(workspace, "link-impact", {"source": "logo.vixl", "suites": False, "checks": ["links"]})
    entries = {entry["path"]: entry for entry in result["documents"]}
    assert entries["nested.vixl"]["depth"] == 2 and entries["nested.vixl"]["via"] == ["logo.vixl", "page.vixl"]
    tree = result["tree"]
    assert tree["document"] == "logo.vixl"
    children = {child["document"]: child for child in tree["dependents"]}
    assert set(children) == {"page.vixl", "wide.vixl"}
    assert [child["document"] for child in children["page.vixl"]["dependents"]] == ["nested.vixl"]


def test_apply_saves_only_the_passing_dependents_through_a_journal(workspace):
    before = stamps(workspace)
    result = dispatch(workspace, "link-impact", {"source": "logo.vixl", "apply": "if-passing"})
    assert result["published"] == ["wide.vixl"] and result["journal"] == "link-impact"
    after = stamps(workspace)
    assert after["page.vixl"] == before["page.vixl"] and after["nested.vixl"] == before["nested.vixl"]
    assert after["wide.vixl"] != before["wide.vixl"]
    saved = Project.load(workspace.resolve("wide.vixl"))
    layer = saved.layer("logo")
    assert (layer["width"], layer["height"]) == (160, 40) and layer["source_size"] == [160, 40]
    assert not workspace.resolve(".vixl-groups/link-impact.transaction.json").exists()
    # Applying again finds nothing stale to publish in wide.vixl.
    again = dispatch(workspace, "link-impact", {"source": "logo.vixl", "apply": True})
    assert again["published"] == []


def test_scope_by_glob_and_group(workspace):
    only = dispatch(workspace, "link-impact", {"source": "logo.vixl", "documents": ["wide.vixl"]})
    assert [entry["path"] for entry in only["documents"]] == ["wide.vixl"] and only["passed"] is True
    dispatch(workspace, "group-define", {"name": "pages", "documents": ["page.vixl"]})
    grouped = dispatch(workspace, "link-impact", {"source": "logo.vixl", "group": "pages"})
    assert [entry["path"] for entry in grouped["documents"]] == ["page.vixl"]


def test_a_cycle_on_disk_is_reported_and_fails(tmp_path):
    logo(tmp_path / "a.vixl")
    logo(tmp_path / "c.vixl")
    host(tmp_path / "b.vixl", "a.vixl", 20, suite=False)
    # Link a back to b behind the engine's back (the link operation refuses a cycle): a -> b -> a.
    a = Project.load(tmp_path / "a.vixl")
    a.apply({"type": "link", "source": "c.vixl", "name": "back", "x": 0, "y": 0})
    a.layer("back")["source"] = "b.vixl"
    a.save(tmp_path / "a.vixl", overwrite=True)
    session = Session(None, workspace=tmp_path)
    result = dispatch(session, "link-impact", {"source": "a.vixl", "checks": ["links"]})
    assert result["cycles"] == [["a.vixl", "b.vixl", "a.vixl"]]
    assert result["passed"] is False and [item["document"] for item in result["fails"]] == ["b.vixl"]


def test_cli_links_impact(workspace, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(workspace.workspace)
    assert main(["links", "impact", "logo.vixl", "--glob", "wide.vixl", "--format", "markdown"]) == 0
    assert "Vixl link impact: logo.vixl" in capsys.readouterr().out
    assert main(["--json", "links", "impact", "logo.vixl"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert [item["document"] for item in report["fails"]] == ["page.vixl"]
    assert main(["links", "impact", "logo.vixl", "--format", "sarif", "--write", "junit=impact.xml"]) == 1
    assert workspace.resolve("impact.xml").is_file()
