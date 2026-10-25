"""Candidate evaluation (step 7 foundation F4): change a copy, check and diff it, commit only if clean."""

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch
from vixl.plugins.workspace_qa import candidate


def card(path, x=20):
    p = Project(300, 160, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "box", "x": x, "y": 20, "width": 100, "height": 60,
              "fill": "#225588"},
             {"type": "suite-set", "name": "inside", "suite": {"rules": [
                 {"id": "box-inside", "kind": "relation", "target": "box", "to": "canvas", "position": "inside"}]}}])
    p.save(path, overwrite=True)


@pytest.fixture
def session(tmp_path):
    card(tmp_path / "a.vixl")
    card(tmp_path / "b.vixl", x=150)
    return Session(None, workspace=tmp_path)


def test_evaluate_changes_a_copy_checks_suites_and_diffs_without_saving(session):
    before = session.resolve("a.vixl").read_bytes()
    clean = candidate.evaluate(session, "a.vixl", [{"type": "move", "target": "box", "x": 40, "y": 20}])
    assert clean.passed and clean.changed and clean.report["check"]["suites"]["inside"]["status"] == "passed"
    assert 0 < clean.report["diff"]["changed_fraction"] < 1 and clean.candidate.layer("box")["x"] == 40
    off = candidate.evaluate(session, "a.vixl", lambda project: project.apply(
        {"type": "move", "target": "box", "x": 260, "y": 20}) and {"moved": True})
    assert off.report["status"] == "failed" and off.report["result"] == {"moved": True}
    assert any("box-inside" in message for message in off.report["failing"])
    assert session.resolve("a.vixl").read_bytes() == before
    untouched = candidate.evaluate(session, "a.vixl")
    assert untouched.passed and not untouched.changed and untouched.report["diff"]["identical"]
    broken = candidate.evaluate(session, "a.vixl", [{"type": "move", "target": "missing", "x": 1, "y": 1}])
    assert broken.report["status"] == "error" and not broken.passed
    with pytest.raises(VixlError):
        candidate.load(session, "nope.vixl")


def test_evaluate_all_commits_only_passers_through_a_recoverable_journal(session):
    def push(project, document):
        project.apply({"type": "move", "target": "box", "x": project.layer("box")["x"] + 100, "y": 20})

    before = {name: session.resolve(name).read_bytes() for name in ("a.vixl", "b.vixl")}
    summary, evaluations = candidate.evaluate_all(session, ["a.vixl", "b.vixl"], push)
    assert summary["passes"] == ["a.vixl"] and summary["fails"] == ["b.vixl"] and summary["published"] == []
    assert all(session.resolve(n).read_bytes() == data for n, data in before.items())
    summary, _ = candidate.evaluate_all(session, ["a.vixl", "b.vixl"], push, apply="if-passing", journal="nudge")
    assert summary["published"] == ["a.vixl"]
    assert Project.load(session.resolve("a.vixl")).layer("box")["x"] == 120
    assert session.resolve("b.vixl").read_bytes() == before["b.vixl"]
    with pytest.raises(VixlError):
        candidate.evaluate_all(session, ["a.vixl"], push, apply="always")


def test_commit_is_the_group_journal(session, monkeypatch):
    from vixl.plugins.teamwork import project_groups

    evaluation = candidate.evaluate(session, "a.vixl", [{"type": "move", "target": "box", "x": 30, "y": 20}])
    original = project_groups.publish_file
    calls = []

    def interrupted(target, source, replace=False):
        if replace and not calls:
            calls.append(target)
            raise OSError("disk full")  # the first publication fails: the journal rolls everything back
        return original(target, source, replace=replace)

    monkeypatch.setattr(project_groups, "publish_file", interrupted)
    with pytest.raises(OSError):
        candidate.commit(session, "evaluate", [evaluation])
    monkeypatch.setattr(project_groups, "publish_file", original)
    assert calls and not session.resolve(".vixl-groups/evaluate.transaction.json").exists()
    assert Project.load(session.resolve("a.vixl")).layer("box")["x"] == 20
    assert candidate.commit(session, "evaluate", [evaluation]) == ["a.vixl"]
    assert Project.load(session.resolve("a.vixl")).layer("box")["x"] == 30
    assert dispatch(session, "group-list", {})["groups"] == []
