"""Approved baselines (#559): approve records a document's look, the approval check flags later changes for review."""

import json

import pytest
from PIL import Image

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch
from vixl.plugins.workspace_qa import approval


def poster(path, *, x=20, color="#225588", artboards=()):
    p = Project(400, 240, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "box", "x": x, "y": 40, "width": 120, "height": 80,
              "fill": color},
             *({"type": "artboard", "name": name, "width": 200, "height": 240, "x": 200 * i}
               for i, name in enumerate(artboards))])
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path, overwrite=True)
    return path


def edit(path, operations):
    p = Project.load(path)
    p.apply(operations)
    p.save(path, overwrite=True)


def checked(session, relative, **options):
    p = Project.load(session.resolve(relative))
    p._workspace = session.workspace
    return p.check(**options)


def approval_issues(report):
    return [issue for issue in report["issues"] if issue["check"] == "approval"]


@pytest.fixture
def session(tmp_path):
    return Session(None, workspace=tmp_path)


def test_approve_then_edit_needs_review_with_a_diff_and_reapprove_is_clean(session, monkeypatch):
    monkeypatch.setenv("VIXL_AUTHOR", "Ada")
    poster(session.resolve("poster.vixl"))
    result = dispatch(session, "approve", {}, document="poster.vixl")
    assert result["who"] == "Ada" and result["views"] == [{"kind": "canvas", "name": "canvas", "size": [400, 240]}]
    folder = session.resolve("poster.vixl.approval")
    record = json.loads((folder / "approval.json").read_text())
    assert {"revision", "links", "views", "who", "when"} <= record.keys()
    assert len(record["views"][0]["render_hash"]) == 64
    with Image.open(folder / record["views"][0]["reference"]) as reference:
        assert max(reference.size) == approval.THUMBNAIL
    # Unchanged: the standard checks include the approval check, and it is clean.
    assert not approval_issues(checked(session, "poster.vixl"))

    edit(session.resolve("poster.vixl"), [{"type": "move", "target": "box", "x": 220, "y": 40}])
    found = approval_issues(checked(session, "poster.vixl"))
    assert len(found) == 1 and found[0]["severity"] == "warning" and found[0]["action"] == "review"
    assert found[0]["approval"] == "changed" and found[0]["approved_by"] == "Ada"
    assert 0 < found[0]["changed_fraction"] <= 1 and session.resolve(found[0]["diff"]).is_file()
    report = dispatch(session, "check-all", {"documents": ["poster.vixl"], "history": False, "fail_on": "review"})
    assert report["documents"][0]["status"] == "needs_review" and report["passed"] is False
    assert report["documents"][0]["by_check"]["approval"] == 1

    dispatch(session, "approve", {"author": "Grace"}, document="poster.vixl")
    assert not approval_issues(checked(session, "poster.vixl"))
    named = approval_issues(checked(session, "poster.vixl", checks=["approval"]))
    assert [(i["severity"], i["code"]) for i in named] == [("info", "approved")] and named[0]["approved_by"] == "Grace"
    assert not session.resolve("poster.vixl.approval/diff").exists()  # the new approval replaced the old folder


def test_never_approved_is_info_only_when_asked_and_clear_removes_the_data(session):
    poster(session.resolve("a.vixl"))
    assert not approval_issues(checked(session, "a.vixl"))
    asked = approval_issues(checked(session, "a.vixl", checks=["approval"]))
    assert [(i["severity"], i["code"]) for i in asked] == [("info", "never-approved")]
    dispatch(session, "approve", {}, document="a.vixl")
    assert session.resolve("a.vixl.approval").is_dir()
    assert dispatch(session, "approve", {"clear": True}, document="a.vixl")["cleared"] is True
    assert not session.resolve("a.vixl.approval").exists()


def test_group_approve_covers_every_member(session):
    for name in ("one", "two", "three"):
        poster(session.resolve(f"family/{name}.vixl"))
    dispatch(session, "group-define", {"name": "family", "documents": [f"family/{n}.vixl" for n in ("one", "two",
                                                                                                     "three")]})
    result = dispatch(session, "approve", {"group": "family", "author": "Lin"})
    assert [d["document"] for d in result["documents"]] == ["family/one.vixl", "family/two.vixl", "family/three.vixl"]
    assert result["folder"] == ".vixl-groups/family.approval" and result["views"] == 3
    for name in ("one", "two", "three"):
        found = approval.find(session.resolve(f"family/{name}.vixl"), session.workspace)
        assert found is not None and found.source == "group:family" and found.record["who"] == "Lin"
    edit(session.resolve("family/two.vixl"), [{"type": "move", "target": "box", "x": 240, "y": 100}])
    assert approval_issues(checked(session, "family/two.vixl"))
    assert not approval_issues(checked(session, "family/one.vixl"))
    # Without a workspace (a proof page), the group approval is found from the document's own location.
    assert approval.report(Project.load(session.resolve("family/two.vixl")))["state"] == "changed"
    dispatch(session, "approve", {"group": "family", "clear": True})
    assert approval.find(session.resolve("family/one.vixl"), session.workspace) is None


def test_size_bound_holds(session):
    boards = [f"b{i}" for i in range(approval.MAX_VIEWS + 1)]
    p = Project(400, 240, "white")
    p.apply([{"type": "artboard", "name": name, "width": 40, "height": 40} for name in boards])
    p.save(session.resolve("many.vixl"))
    with pytest.raises(VixlError) as error:
        dispatch(session, "approve", {}, document="many.vixl")
    assert error.value.code == "resource_limit" and not session.resolve("many.vixl.approval").exists()

    big = Project(1600, 900, "white")
    big.apply([{"type": "artboard", "name": "left", "width": 800, "height": 900},
               {"type": "artboard", "name": "right", "width": 800, "height": 900, "x": 800}])
    big.save(session.resolve("big.vixl"))
    result = dispatch(session, "approve", {}, document="big.vixl")
    assert [v["name"] for v in result["views"]] == ["left", "right"]
    for picture in sorted(session.resolve("big.vixl.approval/views").glob("*.png")):
        with Image.open(picture) as image:
            assert max(image.size) <= approval.THUMBNAIL
    with pytest.raises(VixlError):
        approval.author("x" * (approval.MAX_AUTHOR + 1))


def test_group_apply_and_replace_across_dry_runs_list_the_approved_members_they_change(session):
    for name in ("one", "two"):
        poster(session.resolve(f"{name}.vixl"))
    poster(session.resolve("three.vixl"), x=200)
    dispatch(session, "group-define", {"name": "family", "documents": ["one.vixl", "two.vixl", "three.vixl"]})
    dispatch(session, "approve", {}, document="one.vixl")
    dispatch(session, "approve", {}, document="two.vixl")
    move = [{"type": "move", "target": "box", "x": 30, "y": 40}]
    preview = dispatch(session, "group-apply", {"name": "family", "operations": move})
    changed = preview["approved_members_changed"]
    assert [item["document"] for item in changed] == ["one.vixl", "two.vixl"]  # three is changed but never approved
    assert changed[0]["views"] == ["canvas"] and changed[0]["changed_fraction"] > 0
    unused = dispatch(session, "group-apply", {"name": "family",
                                                "operations": [{"type": "variable", "name": "unused", "value": "x"}]})
    assert unused["approved_members_changed"] == []
    across = dispatch(session, "replace-across", {"documents": ["*.vixl"], "replace": [{"color": "#225588",
                                                                                        "with": "#aa2200"}]})
    assert [item["document"] for item in across["approved_members_changed"]] == ["one.vixl", "two.vixl"]


def test_campaign_run_lists_an_approved_template_that_changed(session, tmp_path):
    from vixl.production import run

    path = poster(session.resolve("card.vixl"))
    template = Project.load(path)
    template._workspace = session.workspace
    approval.approve(template)
    spec = {"version": 1, "rows": [{}], "format": "png"}
    assert run(template, spec, tmp_path / "out")["approved_members_changed"] == []
    template.apply({"type": "move", "target": "box", "x": 200, "y": 40})
    report = run(template, spec, tmp_path / "out2")
    assert report["approved_members_changed"][0]["views"] == ["canvas"]


def test_proof_page_shows_the_approval_badge(session):
    from vixl.plugins.workspace_qa.proof import proof_page

    poster(session.resolve("a.vixl"))
    poster(session.resolve("b.vixl"))
    dispatch(session, "approve", {"author": "Ada"}, document="a.vixl")
    dispatch(session, "approve", {"author": "Ada"}, document="b.vixl")
    edit(session.resolve("b.vixl"), [{"type": "move", "target": "box", "x": 250, "y": 40}])
    proof_page(["a.vixl", "b.vixl"], "proof.html", resolve=session.resolve)
    page = session.resolve("proof.html").read_text()
    assert 'data-approval="approved"' in page and 'data-approval="changed"' in page


def test_cli_approve_and_clear(session, monkeypatch, capsys):
    from vixl.cli import main

    poster(session.resolve("a.vixl"))
    monkeypatch.chdir(session.workspace)
    assert main(["-p", "a.vixl", "--json", "approve", "--author", "Ada"]) == 0
    assert json.loads(capsys.readouterr().out)["who"] == "Ada"
    assert session.resolve("a.vixl.approval/approval.json").is_file()
    assert main(["-p", "a.vixl", "--json", "approve", "--clear"]) == 0
    assert not session.resolve("a.vixl.approval").exists()
