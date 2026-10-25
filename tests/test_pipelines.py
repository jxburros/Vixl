"""Pipelines (#568, foundation F1): saved pipelines, the per-document run with holds, the resumable run record and
the durable pipeline job kind."""

import json
import zipfile

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.pipelines import runner
from vixl.workflows import dispatch

SUITE = {"version": 1, "rules": [{"id": "logo", "kind": "assert", "expression": "layer.logo.bounds within canvas"}]}
PIPELINE = {"version": 1, "targets": {"group": "launch"}, "steps": [
    {"check": {}},
    {"export": {"targets": [{"path": "out/{doc}.png"}]}},
    {"proof": {"output": "out/proof.html"}},
    {"package": {"output": "out/delivery.zip", "name": "{doc}.{ext}"}},
]}


def poster(path, title="Launch", logo_x=140):
    p = Project(160, 100, "#102030")
    p.apply([{"type": "text", "name": "title", "text": title, "size": 20, "x": 10, "y": 10, "color": "#ffffff"},
             {"type": "shape", "name": "logo", "shape": "rectangle", "width": 10, "height": 10, "fill": "#ff0000",
              "x": logo_x, "y": 80},
             {"type": "suite-set", "name": "quality", "suite": SUITE}])
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path)


@pytest.fixture
def workspace(tmp_path):
    poster(tmp_path / "a.vixl", "Alpha")
    poster(tmp_path / "b.vixl", "Beta")
    poster(tmp_path / "c.vixl", "Gamma", logo_x=400)  # the logo is off the canvas: its suite fails
    session = Session(None, workspace=tmp_path)
    dispatch(session, "group-define", {"name": "launch", "documents": ["a.vixl", "b.vixl", "c.vixl"]})
    dispatch(session, "resource-save", {"kind": "pipelines", "name": "launch", "value": PIPELINE})
    return session


def files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".lock" not in p.name)


def real(session, **request):
    return dispatch(session, "pipeline-run", {"pipeline": "launch", "dry_run": False, **request})


def record(session, run="launch"):
    return json.loads(session.resolve(f".vixl-runs/{run}/run.json").read_text())


def test_a_saved_pipeline_is_a_resource_and_a_bad_one_is_refused(workspace):
    assert dispatch(workspace, "resource-list", {"kind": "pipelines"})["names"] == ["launch"]
    assert dispatch(workspace, "resource-get", {"kind": "pipelines", "name": "launch"})["value"]["steps"][0] == {"check": {}}
    with pytest.raises(VixlError, match="exactly one step kind"):
        dispatch(workspace, "resource-save", {"kind": "pipelines", "name": "bad",
                                              "value": {"version": 1, "steps": [{"check": {}, "export": {}}]}})
    with pytest.raises(VixlError, match="comes before proof and package"):
        dispatch(workspace, "resource-save", {"kind": "pipelines", "name": "bad", "value": {
            "version": 1, "steps": [{"proof": {"output": "p.html"}}, {"check": {}}]}})


def test_a_group_run_exports_proofs_and_packages_and_holds_the_failing_document(workspace):
    result = real(workspace)
    assert result["status"] == "needs_review"
    assert result["counts"]["passed"] == 2 and result["counts"]["held"] == 1
    held = next(d for d in result["documents"] if d["outcome"] == "held")
    assert held["path"] == "c.vixl" and "logo" in " ".join(held["findings"])
    out = workspace.resolve("out")
    assert sorted(p.name for p in out.iterdir()) == ["a.png", "b.png", "delivery.zip", "proof.html"]
    with zipfile.ZipFile(out / "delivery.zip") as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert {"a.png", "b.png", "manifest.json"} <= names and "c.png" not in names
    assert manifest["inputs"]["kind"] == "run" and [h["path"] for h in manifest["held"]] == ["c.vixl"]
    assert [step["status"] for step in result["run_steps"]] == ["passed", "passed"]
    data = record(workspace)
    assert data["vixl_version"] and data["format"] == "vixl-pipeline-run"
    a = data["documents"]["a.vixl"]
    assert a["input"]["document"] and "brand.json" in a["input"] and "links" in a["input"]
    export = a["steps"][1]
    assert export["outputs"][0]["path"] == "out/a.png" and len(export["outputs"][0]["sha256"]) == 64
    assert workspace.resolve(export["log"]).is_file()
    assert data["documents"]["c.vixl"]["outcome"] == "held" and len(data["documents"]["c.vixl"]["steps"]) == 1


def test_the_first_run_is_a_dry_run_that_lists_the_outputs_and_writes_nothing(workspace):
    before = files(workspace.workspace)
    plan = dispatch(workspace, "pipeline-run", {"pipeline": "launch"})
    assert plan["dry_run"] and plan["written"] is False and "note" in plan
    assert {"out/a.png", "out/b.png", "out/c.png", "out/proof.html", "out/delivery.zip"} == set(plan["outputs"])
    assert all(step["plan"] == "run" for doc in plan["documents"] for step in doc["steps"])
    assert files(workspace.workspace) == before


def test_resume_after_an_interrupt_runs_only_the_incomplete_steps(workspace):
    first = workspace.resolve("out/a.png")
    stopped = runner.run(workspace, {"pipeline": "launch", "dry_run": False}, cancelled=first.exists)
    assert stopped["status"] == "cancelled"
    assert [d["outcome"] for d in stopped["documents"]] == ["passed", "pending", "pending"]
    stamp = first.stat().st_mtime_ns
    resumed = real(workspace)
    a, b = resumed["documents"][0], resumed["documents"][1]
    assert all(step.get("reused") for step in a["steps"])
    assert not any(step.get("reused") for step in b["steps"]) and b["outcome"] == "passed"
    assert first.stat().st_mtime_ns == stamp
    # Run again with nothing changed: every step, the proof and the package are reused.
    again = real(workspace)
    assert all(step.get("reused") for doc in again["documents"] for step in doc["steps"])
    assert all(step.get("reused") for step in again["run_steps"])


def test_a_changed_input_invalidates_the_steps_that_depend_on_it(workspace):
    real(workspace)
    p = Project.load(workspace.resolve("b.vixl"))
    p.apply({"type": "text-set", "target": "title", "text": "Beta two"})
    p.save()
    changed = real(workspace)
    by_path = {d["path"]: d for d in changed["documents"]}
    assert all(step.get("reused") for step in by_path["a.vixl"]["steps"])
    assert not any(step.get("reused") for step in by_path["b.vixl"]["steps"])
    assert not changed["run_steps"][0].get("reused")  # the proof and package see a new b.png
    # A changed export step re-runs the export (replacing the file this run wrote) but reuses the check before it.
    value = json.loads(json.dumps(PIPELINE))
    value["steps"][1]["export"]["targets"][0]["scale"] = 2
    dispatch(workspace, "resource-save", {"kind": "pipelines", "name": "launch", "value": value})
    rescaled = real(workspace)
    a = next(d for d in rescaled["documents"] if d["path"] == "a.vixl")
    assert [bool(step.get("reused")) for step in a["steps"]] == [True, False]
    from PIL import Image

    assert Image.open(workspace.resolve("out/a.png")).size == (320, 200)
    # brand.json is an input of every document.
    workspace.resolve("brand.json").write_text(json.dumps({"name": "Acme"}))
    branded = real(workspace)
    assert not any(step.get("reused") for doc in branded["documents"] for step in doc["steps"])


def test_an_existing_file_the_run_did_not_write_is_never_replaced(workspace):
    workspace.resolve("out").mkdir()
    workspace.resolve("out/a.png").write_bytes(b"not mine")
    plan = dispatch(workspace, "pipeline-run", {"pipeline": "launch"})
    assert plan["refused"] == ["out/a.png"]
    result = real(workspace)
    a = next(d for d in result["documents"] if d["path"] == "a.vixl")
    assert a["outcome"] == "failed" and "overwrite" in a["reason"]
    assert workspace.resolve("out/a.png").read_bytes() == b"not mine"


def test_act_changes_a_working_copy_and_resumes_without_applying_twice(workspace):
    pipeline = {"version": 1, "targets": {"documents": ["a.vixl"]}, "steps": [
        {"act": {"operations": [{"type": "move", "target": "title", "x": 15}]}},
        {"export": {"targets": [{"path": "out/{doc}-moved.png"}]}}]}
    source = workspace.resolve("a.vixl").read_bytes()
    first = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "moved", "dry_run": False})
    assert first["status"] == "completed" and workspace.resolve("out/a-moved.png").is_file()
    assert workspace.resolve("a.vixl").read_bytes() == source
    work = Project.load(workspace.resolve(".vixl-runs/moved/work/a.vixl"))
    assert work.layer("title")["x"] == 15
    again = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "moved", "dry_run": False})
    assert all(step.get("reused") for step in again["documents"][0]["steps"])
    assert Project.load(workspace.resolve(".vixl-runs/moved/work/a.vixl")).layer("title")["x"] == 15
    # Working copies are run state, not workspace documents: check-all leaves them out.
    checked = dispatch(workspace, "check-all", {"history": False})
    assert not any(entry["path"].startswith(".vixl-runs") for entry in checked["documents"])


def test_on_fail_stop_ends_the_run_at_the_first_held_document(workspace):
    poster(workspace.resolve("d.vixl"), "Delta")
    pipeline = {**PIPELINE, "on_fail": "stop", "targets": {"documents": ["b.vixl", "c.vixl", "d.vixl"]}}
    result = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "strict", "dry_run": False})
    assert result["stopped"] and result["status"] == "needs_review"
    assert {d["path"]: d["outcome"] for d in result["documents"]} == {"b.vixl": "passed", "c.vixl": "held",
                                                                      "d.vixl": "pending"}
    assert not workspace.resolve("out/d.png").exists() and result["run_steps"] == []


def test_approval_holds_review_until_decided(workspace):
    pipeline = {"version": 1, "targets": {"documents": ["a.vixl"]}, "steps": [
        {"export": {"targets": [{"path": "out/{doc}.png"}]}}, {"approve": {"decisions": "review.json"}}]}
    pending = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "ok", "dry_run": False})
    assert pending["documents"][0]["outcome"] == "visual-review-needed"
    workspace.resolve("review.json").write_text(json.dumps({"items": [{"path": "out/a.png", "decision": "approved"}]}))
    approved = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "ok", "dry_run": False})
    assert approved["documents"][0]["outcome"] == "passed" and approved["status"] == "completed"
    assert approved["documents"][0]["steps"][0].get("reused")


def export_check_pipeline():
    return {"version": 1, "targets": {"documents": ["a.vixl"]}, "steps": [
        {"export": {"targets": [{"path": "out/{doc}.png"}]}}, {"export_check": {"spec": {"formats": ["png"]}}}]}


def test_the_export_check_step_verifies_each_export(workspace):
    result = dispatch(workspace, "pipeline-run", {"pipeline": export_check_pipeline(), "run": "verify",
                                                  "dry_run": False})
    step = record(workspace, "verify")["documents"]["a.vixl"]["steps"][1]
    assert step["status"] == "passed" and result["documents"][0]["outcome"] == "passed"
    log = json.loads(workspace.resolve(step["log"]).read_text())
    assert log["result"]["verdicts"]["out/a.png"]["passed"] is True


def test_a_failed_export_check_holds_the_document(workspace):
    pipeline = export_check_pipeline()
    pipeline["steps"][1]["export_check"]["spec"] = {"formats": ["pdf"]}
    result = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "verify-pdf", "dry_run": False})
    assert result["documents"][0]["outcome"] == "held" and "export check failed" in result["documents"][0]["reason"]


def test_a_misspelled_export_check_spec_is_refused_before_the_run(workspace):
    pipeline = export_check_pipeline()
    pipeline["steps"][1]["export_check"]["spec"] = {"format": "png"}
    with pytest.raises(VixlError, match="formats"):
        dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "verify-bad", "dry_run": False})


def test_the_pipeline_job_kind_runs_through_submit_and_work(workspace):
    job = dispatch(workspace, "submit", {"job": {"kind": "pipeline", "output": ".vixl-runs/nightly",
                                                 "request": {"pipeline": "launch"}}})
    with pytest.raises(VixlError, match="run folder"):
        dispatch(workspace, "submit", {"job": {"kind": "pipeline", "output": "elsewhere",
                                               "request": {"pipeline": "launch"}}})
    done = dispatch(workspace, "work", {})["jobs"]
    status = dispatch(workspace, "status", {"id": job["id"]})
    assert status["status"] == "needs_review" and status["result"]["counts"] == {"passed": 2, "held": 1}
    assert done and record(workspace, "nightly")["counts"]["held"] == 1
    assert workspace.resolve("out/delivery.zip").is_file()


def test_two_documents_never_write_the_same_export_file(workspace):
    poster(workspace.resolve("x/a.vixl"), "Ex")
    poster(workspace.resolve("y/a.vixl"), "Why")
    pipeline = {"version": 1, "targets": {"documents": ["x/a.vixl", "y/a.vixl"]},
                "steps": [{"export": {"targets": [{"path": "out/{doc}.png"}], "overwrite": True}}]}
    plan = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "same"})
    assert plan["refused"] == ["out/a.png"]
    result = dispatch(workspace, "pipeline-run", {"pipeline": pipeline, "run": "same", "dry_run": False})
    outcomes = {d["path"]: d for d in result["documents"]}
    assert outcomes["x/a.vixl"]["outcome"] == "passed"
    assert outcomes["y/a.vixl"]["outcome"] == "failed" and "x/a.vixl" in outcomes["y/a.vixl"]["reason"]
    assert [item["path"] for item in result["outputs"]] == ["out/a.png"]


def test_a_change_two_links_away_invalidates_the_document(workspace):
    poster(workspace.resolve("c2.vixl"), "Deep")
    for name, source in (("b2", "c2.vixl"), ("a2", "b2.vixl")):
        p = Project(320, 200, "#ffffff", workspace=workspace.workspace)
        p.path = str(workspace.resolve(f"{name}.vixl"))
        p.apply({"type": "link", "source": source, "name": "linked", "x": 0, "y": 0})
        p.save(p.path, overwrite=True)
    pipeline = {"version": 1, "targets": {"documents": ["a2.vixl"]},
                "steps": [{"export": {"targets": [{"path": "out/{doc}.png"}]}}]}
    request = {"pipeline": pipeline, "run": "nested", "dry_run": False}
    dispatch(workspace, "pipeline-run", request)
    assert "c2.vixl" in record(workspace, "nested")["documents"]["a2.vixl"]["input"]["links"]
    deep = Project.load(workspace.resolve("c2.vixl"))
    deep.apply({"type": "text-set", "target": "title", "text": "Deeper"})
    deep.save()
    again = dispatch(workspace, "pipeline-run", request)
    assert not again["documents"][0]["steps"][0].get("reused")


def test_an_edited_suite_file_re_runs_the_check(workspace):
    workspace.resolve("rules.json").write_text(json.dumps(SUITE))
    pipeline = {"version": 1, "targets": {"documents": ["a.vixl"]}, "steps": [{"check": {"suite": "rules.json"}}]}
    request = {"pipeline": pipeline, "run": "rules", "dry_run": False}
    assert dispatch(workspace, "pipeline-run", request)["documents"][0]["outcome"] == "passed"
    assert dispatch(workspace, "pipeline-run", request)["documents"][0]["steps"][0].get("reused")
    strict = {"version": 1, "rules": [{"id": "title", "kind": "text", "target": "title", "max_characters": 2}]}
    workspace.resolve("rules.json").write_text(json.dumps(strict))
    changed = dispatch(workspace, "pipeline-run", request)["documents"][0]
    assert not changed["steps"][0].get("reused") and changed["outcome"] == "held"
