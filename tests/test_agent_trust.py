"""The agent trust stack: outcome states (#525), actionable diagnostics (#524), visual feedback (#526),
built-in repairs (#571), bounded layout repair (#518), protected edits (#520) and reproducibility (#512)."""

import io
import json
from copy import deepcopy

import pytest
from PIL import Image

from vixl import Project
from vixl.checks import apply_reviewed
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.layout_repair import repair_layout
from vixl.outcomes import make, merge, summarize
from vixl.protected_edit import protected_edit
from vixl.reproduce import lock, reproduce
from vixl.schema import validate_operation
from vixl.workflows import dispatch

HEADLINE = "A much longer headline that will not fit"


def overflowing(width=400, height=300):
    p = Project(width, height, "white")
    p.apply([
        {"type": "text", "name": "headline", "text": HEADLINE, "x": 20, "y": 20, "size": 40, "color": "black"},
        {"type": "text-layout", "target": "headline", "width": 200, "height": 60},
    ])
    return p


def problems():
    p = overflowing()
    p.apply([
        {"type": "text", "name": "faint", "text": "Faint text", "x": 20, "y": 150, "size": 20, "color": "#dddddd"},
        {"type": "text", "name": "edge", "text": "Edge", "x": 370, "y": 250, "size": 20, "color": "black"},
        {"type": "text", "name": "one", "text": "Overlap", "x": 20, "y": 200, "size": 24, "color": "black"},
        {"type": "text", "name": "two", "text": "Overlap", "x": 30, "y": 205, "size": 24, "color": "black"},
    ])
    return p


def clean():
    p = Project(400, 300, "white")
    p.apply({"type": "text", "name": "title", "text": "Fine", "x": 40, "y": 40, "size": 32, "color": "black"})
    return p


def by_rule(report):
    return {item["rule"]: item for item in report["issues"]}


# --- #525 outcome states ---------------------------------------------------------------------------------------

def test_check_outcome_separates_validation_from_review():
    assert clean().check(checks=["bounds", "contrast"])["outcome"]["state"] == "validated"
    report = overflowing().check(checks=["bounds"])
    assert report["passed"] is False
    assert report["outcome"]["validation"] == "failed" and report["outcome"]["state"] == "validation_failed"
    # A review finding (a non-text layer cut off by the edge) does not fail validation but needs review.
    p = clean()
    p.apply({"type": "shape", "shape": "rectangle", "name": "tab", "x": 380, "y": 100, "width": 60, "height": 30,
             "fill": "black"})
    report = p.check(checks=["bounds"])
    assert report["passed"] is True
    assert report["outcome"]["state"] == "needs_review" and report["outcome"]["review"] == "required"
    assert any("tab" in reason for reason in report["outcome"]["review_reasons"])
    # A crop the document marks as deliberate is listed as accepted, with its reason.
    p.apply({"type": "layer-intent", "target": "tab", "allow_crop": True})
    report = p.check(checks=["bounds"])
    assert report["outcome"]["state"] == "validated"
    assert report["outcome"]["accepted"][0]["layers"] == ["tab"]


def test_apply_without_checks_is_completed_but_not_validated():
    p = clean()
    result, _ = apply_reviewed(p, [{"type": "move", "target": "title", "x": 1, "y": 0, "relative": True}])
    assert result["outcome"]["execution"] == "completed"
    assert result["outcome"]["validation"] == "not_run" and result["outcome"]["state"] == "unvalidated"
    result, _ = apply_reviewed(p, [{"type": "move", "target": "title", "x": 1, "y": 0, "relative": True}],
                               check=["bounds"])
    assert result["outcome"]["state"] == "validated"


def suite_report(rules):
    p = clean()
    p.apply({"type": "suite-set", "name": "s", "suite": {"rules": rules}})
    return p.check_suite("s")


def test_suite_outcomes_cover_failed_skipped_uncertain_and_clean():
    passed = suite_report([{"id": "fit", "kind": "text-fit", "target": "title"}])
    assert passed["outcome"]["state"] == "validated"
    failed = suite_report([{"id": "big", "kind": "property", "target": "title", "field": "size", "expected": 99}])
    assert failed["outcome"]["validation"] == "failed"
    uncertain = suite_report([{"id": "c", "kind": "contrast", "target": "missing-layer"}])
    assert uncertain["outcome"]["validation"] == "incomplete" and uncertain["outcome"]["state"] == "needs_review"
    assert "could not be measured" in uncertain["outcome"]["review_reasons"][0]
    warning = suite_report([{"id": "w", "kind": "property", "target": "title", "field": "size", "expected": 99,
                             "severity": "warning"}])
    assert warning["outcome"]["validation"] == "passed" and warning["outcome"]["state"] == "needs_review"
    # Failed required checks never merge into a validated result.
    assert merge(passed["outcome"], failed["outcome"])["state"] == "validation_failed"
    assert merge(make("completed"), passed["outcome"])["state"] == "validated"


def test_batch_summary_is_the_worst_item_with_counts():
    items = [make("completed", "passed"), make("completed"), make("failed")]
    summary = summarize(items)
    assert summary["state"] == "execution_failed"
    assert summary["counts"] == {"validated": 1, "unvalidated": 1, "execution_failed": 1}
    assert summarize([make("completed", "passed")])["validated"] is True


def test_production_without_suites_is_unvalidated(tmp_path):
    from vixl.production import run

    p = clean()
    report = run(p, {"rows": [{}]}, tmp_path)
    result = report["results"][0]
    assert result["status"] == "completed"
    assert result["outcome"]["state"] == "unvalidated"
    assert report["outcome"]["state"] == "unvalidated" and not report["outcome"]["validated"]


def test_job_outcome_reads_status_and_outputs():
    from vixl.jobs import job_outcome

    assert job_outcome({"status": "queued"})["state"] == "pending"
    assert job_outcome({"status": "failed"})["state"] == "execution_failed"
    uncertain = job_outcome({"status": "needs_review", "error": {"code": "remote_unknown", "message": "maybe"}})
    assert uncertain["execution"] == "failed" and "maybe" in uncertain["review_reasons"]
    done = job_outcome({"status": "completed", "result": {"outcome": summarize([make("completed", "passed")])}})
    assert done["state"] == "validated"


def test_exports_are_never_validated(tmp_path):
    from vixl.export_batch import export_batch
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    session.create("doc.vixl", 40, 30)
    single = export_file(session, "one.png")
    assert single["outcome"]["state"] == "unvalidated"
    batch = export_batch(session, export_file, [{"path": "two.png"}, {"path": "three.png", "document": "missing.vixl"}], None, False,
                         False, None)
    assert batch["results"][1]["outcome"]["state"] == "execution_failed"
    assert batch["outcome"]["state"] == "execution_failed"
    assert batch["outcome"]["counts"] == {"unvalidated": 1, "execution_failed": 1}


# --- #524 diagnostics -------------------------------------------------------------------------------------------

def test_findings_have_rules_layers_measurements_and_valid_repairs():
    p = problems()
    before = deepcopy(p.state)
    report = p.check(checks=["bounds", "overlap", "contrast", "safe_area"])
    assert p.state == before  # recommendations never mutate
    rules = {item["rule"]: item for item in report["issues"] if item["layers"][0] not in ("one", "two")}
    overflow = rules["bounds.text-overflow"]
    assert overflow["layer_ids"] == [p.layer("headline")["id"]]
    assert overflow["measured"]["expected"] == [200, 60] and overflow["measured"]["actual"][1] > 60
    overlap = by_rule(report)["overlap.text-text"]
    assert set(overlap["layer_ids"]) == {p.layer("one")["id"], p.layer("two")["id"]} and len(overlap["region"]) == 4
    assert overlap["repair"]["available"] is False and overlap["repair"]["reason"]
    contrast = rules["contrast.text-contrast"]
    assert contrast["measured"]["actual"] < contrast["measured"]["expected"] == contrast["required"]
    assert rules["safe_area.outside"]["measured"]["expected"] == rules["safe_area.outside"]["safe_area"]
    for rule in ("bounds.text-overflow", "contrast.text-contrast", "safe_area.outside"):
        repair = rules[rule]["repair"]
        assert repair["available"], (rule, repair)
        for operation in repair["operations"]:
            validate_operation(dict(operation))
        trial = p.clone()
        assert trial.apply(repair["operations"], dry_run=True)["success"]
        trial.apply(repair["operations"])
        after = trial.check(checks=[rule.split(".")[0]])["issues"]
        assert not [x for x in after if x["rule"] == rule and x["layer_ids"] == rules[rule]["layer_ids"]]


def test_unfilled_blank_is_held_not_guessed():
    from vixl.repair import suggest

    suggestion = suggest(clean(), {"rule": "blanks.unfilled", "layers": ["title"], "action": "fix"})
    assert suggestion["kind"] == "hold" and suggestion["available"] is False and not suggestion["operations"]


def test_check_pagination_keeps_the_overall_verdict():
    p = problems()
    full = p.check(checks=["bounds", "contrast", "safe_area"])
    page = p.check(checks=["bounds", "contrast", "safe_area"], limit=1, offset=1)
    assert len(page["issues"]) == 1 and page["issues"][0]["rule"] == full["issues"][1]["rule"]
    assert page["passed"] is False and page["errors"] == full["errors"]
    assert page["outcome"] == full["outcome"] and page["pagination"]["total"] == len(full["issues"])


def test_invalid_field_names_the_operation_and_field():
    p = clean()
    with pytest.raises(VixlError) as caught:
        p.apply([{"type": "move", "target": "title", "x": 1}, {"type": "text-set", "target": "title", "size": "big"}])
    error = caught.value.as_dict()
    detail = error.get("errors", [error])[0]
    assert detail.get("operation_index") == 1 and detail.get("field")


# --- #526 visual feedback ---------------------------------------------------------------------------------------

def test_preview_overlay_marks_findings_at_preview_scale_without_changing_the_document():
    p = overflowing()
    clean_png = p.render()
    state = deepcopy(p.state)
    result, image = apply_reviewed(p, [{"type": "move", "target": "headline", "x": 0, "y": 0, "relative": True}],
                                   dry_run=True, check=["bounds"], preview={"max_width": 200, "overlay": True})
    feedback = result["feedback"]
    assert feedback["scale"] == 0.5 and feedback["size"] == [200, 150] and feedback["bytes"] <= feedback["max_bytes"]
    entry = feedback["overlay"][0]
    assert entry["rule"] == "bounds.text-overflow" and entry["layer_ids"] == [p.layer("headline")["id"]]
    assert entry["box"] == [round(v * 0.5) for v in entry["region"]]
    marked = Image.open(io.BytesIO(image)).convert("RGB")
    x, y = entry["box"][:2]
    assert marked.getpixel((x, y + 2))[0] > 200 and marked.getpixel((x, y + 2))[1] < 80  # red outline
    _, plain = apply_reviewed(p, [{"type": "move", "target": "headline", "x": 0, "y": 0, "relative": True}],
                              dry_run=True, check=["bounds"], preview={"max_width": 200})
    assert plain != image
    assert p.state == state and p.render().tobytes() == clean_png.tobytes()


def test_focus_returns_a_detail_crop_of_one_finding():
    p = problems()
    result, image = apply_reviewed(p, [{"type": "move", "target": "edge", "x": 0, "y": 0, "relative": True}],
                                   dry_run=True, check=["safe_area"], preview={"focus": 0})
    region = result["feedback"]["region"]
    finding = result["check"]["issues"][0]
    x, y, w, h = finding["bounds"]
    assert region[0] <= x and region[1] <= y and region[2] < 400
    assert Image.open(io.BytesIO(image)).size == tuple(result["feedback"]["size"])
    with pytest.raises(VixlError):
        apply_reviewed(p, [{"type": "move", "target": "edge", "x": 0, "y": 0, "relative": True}], dry_run=True,
                       preview={"overlay": True})


def test_proof_page_overlay_and_outcome(tmp_path):
    from vixl.proof import proof_page

    overflowing().save(tmp_path / "doc.vixl")
    plain = proof_page(["doc.vixl"], "plain.html", resolve=lambda v: tmp_path / v)
    marked = proof_page(["doc.vixl"], "marked.html", resolve=lambda v: tmp_path / v, overlay=True)
    assert marked["checked"][0]["outcome"]["state"] == "validation_failed"
    assert marked["outcome"]["state"] == "validation_failed"
    assert (tmp_path / "plain.html").read_bytes() != (tmp_path / "marked.html").read_bytes()
    assert plain["outcome"]["counts"] == {"validation_failed": 1}


# --- #571 built-in repairs --------------------------------------------------------------------------------------

def test_repair_fixes_overflow_reports_operations_and_undoes():
    p = overflowing()
    report = p.repair(checks=["bounds"])
    assert report["passed"] and report["applied"][0]["kind"] == "fit-text"
    assert report["operations"] == report["applied"][0]["operations"]
    assert p.layer("headline")["size"] < 40 and p.check(checks=["bounds"])["passed"]
    p.undo()
    assert p.layer("headline")["size"] == 40


def test_repair_is_rejected_when_it_introduces_a_new_failure():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "text", "name": "edge", "text": "Edge", "x": 380, "y": 100, "size": 20, "color": "black"},
        {"type": "text", "name": "neighbour", "text": "Here", "x": 330, "y": 100, "size": 20, "color": "black"},
    ])
    state = deepcopy(p.state)
    report = p.repair(checks=["bounds", "overlap"])
    assert not report["applied"] and "introduced overlap" in report["unrepaired"][0]["reason"]
    assert p.state == state


def test_check_and_apply_repair_flags():
    session_project = overflowing()
    result, _ = apply_reviewed(session_project, [{"type": "move", "target": "headline", "x": 0, "y": 0,
                                                  "relative": True}], check=["bounds"], repair=True)
    assert result["repairs"]["applied"] and result["check"]["passed"]
    p = overflowing()
    report = p.check(checks=["bounds"], repair=["fit-text"])
    assert report["passed"] and report["repairs"]["applied"][0]["kind"] == "fit-text"
    p = overflowing()
    report = p.check(checks=["bounds"], repair=["contrast-ink"])
    assert not report["passed"] and report["repairs"]["unrepaired"][0]["reason"] == "fit-text repairs were not requested"


def test_act_repair_commits_when_suites_then_pass():
    p = overflowing()
    p.apply({"type": "suite-set", "name": "fit", "suite": {"rules": [
        {"id": "headline-fits", "kind": "text-fit", "target": "headline", "minimum": 16}]}})
    p.apply({"type": "text-layout", "target": "headline", "width": 200, "height": 60, "fit": False})
    rejected = p.act([{"type": "text-set", "target": "headline", "color": "navy"}], suites=["fit"])
    assert rejected["committed"] is False and rejected["outcome"]["state"] == "validation_failed"
    result = p.act([{"type": "text-set", "target": "headline", "color": "navy"}], suites=["fit"], repair=True)
    assert result["committed"] and result["outcome"]["state"] == "validated"
    assert result["repairs"]["applied"][0]["kind"] == "fit-text"
    assert result["repairs"]["applied"][0]["operations"][0]["minimum"] == 16
    assert p.layer("headline")["size"] >= 16


def test_group_apply_repair_fixes_one_overflowing_headline(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("good.vixl", 400, 300, "white")
    session.apply([{"type": "text", "name": "headline", "text": "Short", "x": 20, "y": 20, "size": 30,
                    "color": "black"}])
    overflowing().save(tmp_path / "long.vixl")
    dispatch(session, "group-define", {"name": "family", "documents": ["good.vixl", "long.vixl"]})
    result = dispatch(session, "group-apply", {"name": "family", "dry_run": False, "repair": True,
                                               "operations": [{"type": "text-set", "target": "headline",
                                                               "color": "#111111"}]})
    repairs = {entry["document"]: entry["repairs"] for entry in result["documents"]}
    assert not repairs["good.vixl"]["applied"]
    assert repairs["long.vixl"]["applied"][0]["rule"] == "bounds.text-overflow"
    assert repairs["long.vixl"]["operations"][0]["type"] == "fit-text"
    assert Project.load(tmp_path / "long.vixl").check(checks=["bounds"])["passed"]


def test_campaign_auto_repair_uses_the_same_map(tmp_path):
    from vixl.production import run

    p = overflowing()
    report = run(p, {"repair_actions": ["auto"]}, tmp_path)
    result = report["results"][0]
    assert result["status"] == "completed" and result["repairs"] == ["auto"]
    assert result["repair_operations"][0]["type"] == "fit-text"


# --- #518 bounded layout repair ---------------------------------------------------------------------------------

def headline_with_logo():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "logo", "x": 300, "y": 20, "width": 80, "height": 80,
         "fill": "#cc3300"},
        {"type": "text", "name": "headline", "text": "A much longer headline that needs room", "x": 20, "y": 20,
         "size": 36, "color": "black"},
        {"type": "text-layout", "target": "headline", "width": 260, "height": 50},
        {"type": "text", "name": "sub", "text": "Subline", "x": 30, "y": 30, "size": 24, "color": "black"},
    ])
    return p


def test_layout_repair_keeps_protected_layers_and_minimum_sizes():
    p = headline_with_logo()
    logo = deepcopy(p.layer("logo"))
    plan = repair_layout(p, checks=["bounds", "overlap"], protected=["logo"], minimum_size=28, dry_run=True)
    assert plan["feasible"] and not plan["committed"] and p.layer("logo") == logo
    assert {item["rule"] for item in plan["selected"]} == {"bounds.text-overflow", "overlap.text-text"}
    assert plan["selected"][0]["candidate"] != "map:fit-text" or plan["selected"][0]["operations"][0]["minimum"] >= 28
    assert all(attempt["result"] in ("selected", "valid", "rejected", "skipped") for attempt in plan["attempts"])
    again = repair_layout(p, checks=["bounds", "overlap"], protected=["logo"], minimum_size=28, dry_run=True)
    assert again["operations"] == plan["operations"]  # reproducible for fixed inputs
    committed = repair_layout(p, checks=["bounds", "overlap"], protected=["logo"], minimum_size=28, dry_run=False)
    assert committed["committed"] and p.layer("logo") == logo
    assert p.check(checks=["bounds", "overlap"])["passed"] and p.layer("headline")["size"] >= 28


def test_infeasible_layout_repair_leaves_the_document_unchanged():
    p = headline_with_logo()
    state = deepcopy(p.state)
    result = repair_layout(p, checks=["bounds"], protected=["headline"], dry_run=False)
    assert not result["feasible"] and not result["committed"] and p.state == state
    assert result["unsatisfied"][0]["rule"] == "bounds.text-overflow"
    assert result["outcome"]["state"] == "validation_failed"


def test_layout_repair_equalises_suite_spacing():
    p = Project(300, 300, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": f"bar{i}", "x": 20, "y": y, "width": 100, "height": 20,
         "fill": "black"} for i, y in enumerate((20, 60, 130))])
    p.apply({"type": "suite-set", "name": "rhythm", "suite": {"rules": [
        {"id": "even", "kind": "spacing", "targets": ["bar0", "bar1", "bar2"], "expected": 20, "tolerance": 1}]}})
    result = repair_layout(p, checks=False, suites=["rhythm"], dry_run=False)
    assert result["committed"] and result["selected"][0]["candidate"] == "equal-gaps:expected"
    assert p.check_suite("rhythm")["passed"]


def test_layout_repair_workflow_dry_run(tmp_path):
    session = Session(workspace=tmp_path)
    headline_with_logo().save(tmp_path / "doc.vixl")
    session.open("doc.vixl")
    before = (tmp_path / "doc.vixl").read_bytes()
    plan = dispatch(session, "repair-layout", {"checks": ["bounds", "overlap"], "protected": ["logo"]})
    assert plan["feasible"] and plan["dry_run"] and (tmp_path / "doc.vixl").read_bytes() == before


# --- #520 protected edits ---------------------------------------------------------------------------------------

def scene():
    p = Project(200, 200, "white")
    p.apply([
        {"type": "solid", "name": "bg", "color": "#336699"},
        {"type": "shape", "shape": "ellipse", "name": "subject", "x": 50, "y": 50, "width": 100, "height": 100,
         "fill": "#ffcc00"},
        {"type": "text", "name": "head", "text": "Hello", "x": 10, "y": 160, "size": 24, "color": "white"},
    ])
    return p


def test_background_replacement_keeps_protected_layers():
    p = scene()
    result = protected_edit(p, [{"type": "solid", "target": "bg", "color": "#993366"}], protect=["subject", "head"])
    assert result["committed"] and result["outcome"]["state"] == "validated"
    assert {g["kind"] for g in result["guarantees"]} == {"structure", "pixels"}
    assert all(g["status"] == "preserved" for g in result["guarantees"])


def test_structural_change_is_caught_and_rolled_back():
    p = scene()
    state = deepcopy(p.state)
    result = protected_edit(p, [{"type": "text-set", "target": "head", "text": "Hallo"}], protect=["head"],
                            pixels=False)
    assert not result["committed"] and p.state == state
    assert result["guarantees"][0]["changed_fields"] == ["text"]
    assert "Hello" not in json.dumps(result) and "Hallo" not in json.dumps(result)  # no layer contents


def test_indirect_pixel_change_is_caught_with_its_location():
    p = scene()
    state = deepcopy(p.state)
    # A provider that repaints the whole canvas, modelled as an opaque image over everything.
    from vixl.assets import add_image

    asset = add_image(p, Image.new("RGBA", (200, 200), (10, 200, 10, 255)))
    result = protected_edit(p, [{"type": "add", "name": "repaint", "asset": asset}],
                            protect=["subject"], regions=[[0, 0, 20, 20]])
    assert not result["committed"] and p.state["layers"] == state["layers"]
    pixels = [g for g in result["guarantees"] if g["kind"] == "pixels"]
    assert all(g["status"] == "violated" for g in pixels)
    assert pixels[0]["changed_region"] == [50, 50, 100, 100] or pixels[0]["changed_region"][2] <= 100
    assert result["outcome"]["state"] == "validation_failed"


def test_unmeasurable_protection_needs_review():
    p = scene()
    p.apply({"type": "shape", "shape": "rectangle", "name": "ghost", "x": 0, "y": 0, "width": 10, "height": 10,
             "fill": "transparent"})
    result = protected_edit(p, [{"type": "solid", "target": "bg", "color": "red"}], protect=["ghost"],
                            dry_run=True)
    pixel = next(g for g in result["guarantees"] if g["kind"] == "pixels")
    assert pixel["status"] == "unmeasured" and result["outcome"]["state"] == "needs_review"


# --- #512 reproducibility ---------------------------------------------------------------------------------------

def test_reference_verification(tmp_path):
    p = scene()
    p.render().save(tmp_path / "approved.png")
    assert reproduce(p)["reproduction"] == "renderable"
    assert reproduce(p)["outcome"]["state"] == "unvalidated"
    verified = reproduce(p, reference=tmp_path / "approved.png")
    assert verified["reproduction"] == "reference-verified" and verified["outcome"]["state"] == "validated"
    p.apply({"type": "move", "target": "subject", "x": 3, "y": 0, "relative": True})
    changed = reproduce(p, reference=tmp_path / "approved.png")
    assert changed["reproduction"] == "reference-mismatch" and changed["reference"]["changed_region"]
    assert changed["outcome"]["validation"] == "failed"
    assert reproduce(p, reference=tmp_path / "approved.png", max_fraction=0.05)["reproduction"] == "reference-verified"


def test_lockfile_reports_located_drift():
    p = scene()
    locked = lock(p)
    assert reproduce(p, locked=locked)["reproduction"] == "reference-verified"
    assert not json.dumps(locked).count("Hello")
    drifted = deepcopy(locked)
    drifted["dependencies"]["Pillow"] = "0.0.1"
    result = reproduce(p, locked=drifted)
    assert result["reproduction"] == "drifted"
    assert result["environment_drift"] == [{"kind": "dependencies", "name": "Pillow", "locked": "0.0.1",
                                            "current": locked["dependencies"]["Pillow"]}]
    p.apply({"type": "solid", "target": "bg", "color": "black"})
    moved = reproduce(p, locked=locked)
    assert [item["kind"] for item in moved["input_drift"]] == ["document"] and not moved["render_matches_lock"]


def test_reproduce_cli_exit_status(tmp_path):
    from vixl.cli import main

    p = scene()
    p.save(tmp_path / "doc.vixl")
    p.render().save(tmp_path / "approved.png")
    lock_path = tmp_path / "doc.lock.json"
    assert main(["--project", str(tmp_path / "doc.vixl"), "reproduce", "--reference", str(tmp_path / "approved.png"),
                 "--write-lock", str(lock_path)]) == 0
    assert json.loads(lock_path.read_text())["version"] == 1
    Image.new("RGBA", (200, 200), "red").save(tmp_path / "other.png")
    assert main(["--project", str(tmp_path / "doc.vixl"), "reproduce", "--reference", str(tmp_path / "other.png")]) == 1
    assert main(["--project", str(tmp_path / "doc.vixl"), "reproduce", "--lock", str(lock_path)]) == 0
