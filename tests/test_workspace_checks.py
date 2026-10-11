"""Checks across many documents: the workspace report, its formats and history, group consistency,
find and replace across documents, and reviewed group edits."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch
from vixl.workspace_checks import render

ROOT = Path(__file__).resolve().parents[1]


def document(path, width=400, height=300, *, logo="bottom-right", price="$49", product="Vixl Pro", faint=False):
    """A small campaign member; its logo keeps the same placement relative to the short side."""
    p = Project(width, height, "white")
    short = min(width, height)
    size, margin = (round(short * 0.15), round(short * 0.1)), round(short * 0.08)
    x = margin if logo == "top-left" else width - margin - size[0]
    y = margin if logo == "top-left" else height - margin - size[1]
    p.apply([
        {"type": "swatch", "name": "accent", "color": "#006d77"},
        {"type": "text", "name": "headline", "text": f"{product} launch", "size": 30, "x": 30, "y": 30,
         "color": "#f4f4f4" if faint else "#111111"},
        {"type": "text", "name": "body", "text": f"Only {price} this week", "size": 16, "x": 30, "y": 90,
         "color": "#111111"},
        {"type": "shape", "shape": "rectangle", "name": "logo", "width": size[0], "height": size[1],
         "fill": "#ff6a00", "x": x, "y": y},
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path, overwrite=True)
    return path


@pytest.fixture
def workspace(tmp_path):
    return Session(None, workspace=tmp_path)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "ci", "GIT_AUTHOR_EMAIL": "ci@example.com",
                        "GIT_COMMITTER_NAME": "ci", "GIT_COMMITTER_EMAIL": "ci@example.com"})


# Workspace report (#566) -------------------------------------------------------------------------

def test_one_call_over_fifty_documents_returns_one_result(workspace):
    for index in range(50):
        p = Project(60, 40, "white")
        p.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 20, "y": 10, "width": 20, "height": 20,
                 "fill": "#123456"})
        if index == 7:
            p.apply({"type": "text", "name": "faint", "text": "x", "size": 12, "x": 5, "y": 5, "color": "#fafafa"})
        p.save(workspace.resolve(f"designs/d{index:02d}.vixl"))
    result = dispatch(workspace, "check-all", {"documents": ["designs/*.vixl"], "workers": 4, "history": False})
    assert result["count"] == 50 and len(result["documents"]) == 50
    statuses = {entry["path"]: entry["status"] for entry in result["documents"]}
    assert statuses["designs/d07.vixl"] == "failed"
    assert all(status != "failed" for path, status in statuses.items() if path != "designs/d07.vixl")
    assert result["totals"]["failing"] == 1 and result["passed"] is False
    assert result["totals"]["by_check"]["contrast"] == 1
    failing = next(entry for entry in result["documents"] if entry["path"] == "designs/d07.vixl")
    assert failing["findings"][0]["check"] == "contrast" and failing["failing"]


def test_fail_on_levels_match_the_ci_action(workspace):
    document(workspace.resolve("warn.vixl"))  # fallback-font warning, no errors
    levels = {level: dispatch(workspace, "check-all", {"documents": ["warn.vixl"], "fail_on": level,
                                                       "history": False})["passed"]
              for level in ("error", "warning", "fix", "never")}
    assert levels == {"error": True, "warning": False, "fix": False, "never": True}


def test_attached_suites_run_and_fail_the_report(workspace):
    path = document(workspace.resolve("suite.vixl"))
    p = Project.load(path)
    p.apply({"type": "suite-set", "name": "brand", "suite": {"version": 1, "rules": [
        {"id": "wide", "kind": "assert", "expression": "canvas.width >= 1000"}]}})
    p.save()
    result = dispatch(workspace, "check-all", {"documents": ["suite.vixl"], "history": False})
    entry = result["documents"][0]
    assert entry["suites"]["brand"]["status"] == "failed" and not result["passed"]
    assert any("suite brand" in message for message in entry["failing"])
    assert dispatch(workspace, "check-all", {"documents": ["suite.vixl"], "suites": False,
                                             "history": False})["passed"]


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_changed_since_keeps_only_documents_changed_against_a_revision(workspace, tmp_path):
    for name in ("a", "b", "c"):
        document(workspace.resolve(f"{name}.vixl"))
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    document(workspace.resolve("b.vixl"), price="$59")
    document(workspace.resolve("new.vixl"))
    result = dispatch(workspace, "check-all", {"changed_since": "HEAD", "history": False})
    assert [entry["path"] for entry in result["documents"]] == ["b.vixl", "new.vixl"]
    assert result["unchanged"] == 2
    with pytest.raises(VixlError):
        dispatch(workspace, "check-all", {"changed_since": "--output=x", "history": False})


def test_report_formats_annotations_junit_and_sarif(workspace):
    document(workspace.resolve("ok.vixl"))
    document(workspace.resolve("bad.vixl"), faint=True)
    result = dispatch(workspace, "check-all", {"documents": ["*.vixl"], "history": False, "outputs": {
        "github": "out/annotations.txt", "junit": "out/junit.xml", "sarif": "out/vixl.sarif", "markdown": "out/r.md",
        "json": "out/r.json"}})
    assert set(result["outputs"]) == {"github", "junit", "sarif", "markdown", "json"}
    lines = workspace.resolve("out/annotations.txt").read_text().splitlines()
    assert any(line.startswith("::error file=bad.vixl,title=Vixl contrast::") for line in lines)
    assert not any(line.startswith("::error file=ok.vixl") for line in lines)
    root = ET.fromstring(workspace.resolve("out/junit.xml").read_bytes())
    suites = {suite.get("name"): suite for suite in root.iter("testsuite")}
    assert set(suites) == {"bad.vixl", "ok.vixl"}
    contrast = suites["bad.vixl"].find("testcase[@name='contrast']")
    assert contrast.find("failure") is not None and suites["ok.vixl"].get("failures") == "0"
    assert int(root.get("failures")) >= 1
    sarif = json.loads(workspace.resolve("out/vixl.sarif").read_text())
    assert sarif["version"] == "2.1.0" and sarif["$schema"].endswith("sarif-schema-2.1.0.json")
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "Vixl"
    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    for item in run["results"]:
        assert item["ruleId"] in rule_ids and item["level"] in ("error", "warning", "note")
        assert item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith(".vixl")
    contrast = next(item for item in run["results"] if item["ruleId"] == "contrast")
    assert contrast["level"] == "error" and contrast["locations"][0]["logicalLocations"][0]["name"] == "headline"
    assert json.loads(workspace.resolve("out/r.json").read_text())["count"] == 2
    with pytest.raises(VixlError, match="already exists"):
        dispatch(workspace, "check-all", {"documents": ["*.vixl"], "outputs": {"json": "out/r.json"}})


def test_annotation_values_are_escaped():
    from vixl.workspace_checks import annotations

    text = annotations({"documents": [{"path": "a,b:c.vixl", "status": "failed", "findings": [
        {"check": "bounds", "severity": "error", "message": "50% off\nnext line"}]}]})
    assert text == "::error file=a%2Cb%3Ac.vixl,title=Vixl bounds::50%25 off%0Anext line\n"


# History and since-last (#577) ------------------------------------------------------------------

def test_second_run_names_exactly_the_changed_document_as_newly_failing(workspace):
    for name in ("a", "b", "c"):
        document(workspace.resolve(f"{name}.vixl"))
    first = dispatch(workspace, "check-all", {"documents": ["*.vixl"], "since_last": True})
    assert first["since_last"]["previous"] is None and first["history"].startswith(".vixl-checks/history/")
    document(workspace.resolve("b.vixl"), faint=True)
    second = dispatch(workspace, "check-all", {"documents": ["*.vixl"], "since_last": True})
    since = second["since_last"]
    assert [item["path"] for item in since["newly_failing"]] == ["b.vixl"]
    assert since["newly_failing"][0]["cause"] == "document" and since["newly_failing"][0]["new_findings"]
    assert not since["newly_passing"] and not since["still_failing"] and since["version_changed"] is False
    document(workspace.resolve("b.vixl"))
    third = dispatch(workspace, "check-all", {"documents": ["*.vixl"], "since_last": True})
    assert [item["path"] for item in third["since_last"]["newly_passing"]] == ["b.vixl"]


def test_version_change_is_reported_as_the_cause(workspace):
    from vixl.workspace_checks import since_last

    previous = {"time": "t", "vixl_version": "0.1.0",
                "documents": {"a.vixl": {"status": "passed", "failing": False, "sha256": "x", "findings": []}}}
    current = {"vixl_version": "0.2.0", "documents": [{"path": "a.vixl", "status": "failed", "failing": ["bounds"],
                                                       "sha256": "x", "finding_ids": ["bounds:box"]}]}
    since = since_last(previous, current)
    assert since["version_changed"] and since["newly_failing"][0]["cause"] == "vixl version"


# Group consistency (#550) and copy facts (#551) -------------------------------------------------

def campaign(workspace, **overrides):
    document(workspace.resolve("square.vixl"), 400, 400)
    document(workspace.resolve("wide.vixl"), 600, 300)
    document(workspace.resolve("story.vixl"), 300, 530, **overrides)
    dispatch(workspace, "group-define", {"name": "launch", "documents": ["square.vixl", "wide.vixl", "story.vixl"],
                                         "facts": {"price": {"pattern": r"\$\d+"}, "product": {"values": ["Vixl Pro"]}}})


def test_moved_logo_yields_one_finding_with_the_expected_placement(workspace):
    campaign(workspace, logo="top-left")
    result = dispatch(workspace, "group-check", {"name": "launch", "checks": ["layout"]})
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["document"] == "story.vixl" and finding["layer"] == "logo" and finding["action"] == "fix"
    assert finding["expected"]["anchor"] == "bottom-right" and finding["value"]["anchor"] == "top-left"
    assert not result["passed"]


def test_reference_member_changes_the_comparison(workspace):
    campaign(workspace, logo="top-left")
    result = dispatch(workspace, "group-check", {"name": "launch", "checks": ["layout"], "reference": "story.vixl"})
    assert sorted(f["document"] for f in result["findings"]) == ["square.vixl", "wide.vixl"]
    assert all(f["expected"]["anchor"] == "top-left" for f in result["findings"])
    with pytest.raises(VixlError, match="not one of the members"):
        dispatch(workspace, "group-check", {"name": "launch", "reference": "other.vixl"})


def test_consistent_group_passes(workspace):
    campaign(workspace)
    result = dispatch(workspace, "group-check", {"name": "launch"})
    assert result["passed"] and not result["findings"], result["findings"]


def test_price_difference_is_one_finding_listing_values_and_documents(workspace):
    campaign(workspace, price="$59")
    result = dispatch(workspace, "group-check", {"name": "launch", "checks": ["copy"]})
    price = [f for f in result["findings"] if f["property"] == "price"]
    assert len(price) == 1
    assert price[0]["values"] == {"$49": ["square.vixl", "wide.vixl"], "$59": ["story.vixl"]}
    assert "$49" in price[0]["message"] and "$59" in price[0]["message"] and "story.vixl" in price[0]["message"]


def test_misspelled_product_name_is_flagged_with_a_suggestion(workspace):
    campaign(workspace, product="Vixel Pro")
    result = dispatch(workspace, "group-check", {"name": "launch", "checks": ["copy"]})
    miss = [f for f in result["findings"] if f["property"] == "product"]
    assert len(miss) == 1 and miss[0]["suggestion"] == "Vixl Pro" and miss[0]["value"] == "Vixel Pro"
    assert miss[0]["document"] == "story.vixl"


def test_facts_from_brand_json_variables_and_date_formats(workspace):
    from vixl.group_consistency import date_pattern

    import re

    assert re.search(date_pattern("MMM D"), "Opens Oct 12 at noon").group(0) == "Oct 12"
    workspace.resolve("brand.json").write_text(json.dumps({"facts": {"price": {"value": "$49"}}}))
    for name, price in (("a", "$49"), ("b", "$45")):
        p = Project(200, 100, "white")
        p.apply({"type": "variable", "name": "price", "value": price})
        p.save(workspace.resolve(f"{name}.vixl"))
    result = dispatch(workspace, "group-check", {"documents": ["*.vixl"], "checks": ["copy"]})
    assert [f["documents"] for f in result["findings"]] == [["b.vixl"]]
    workspace.resolve("brand.json").write_text(json.dumps({"facts": {"price": {"pattern": "("}}}))
    with pytest.raises(VixlError, match="regex"):
        dispatch(workspace, "group-check", {"documents": ["*.vixl"], "checks": ["copy"]})


def test_type_color_and_structure_differences(workspace):
    campaign(workspace)
    p = Project.load(workspace.resolve("story.vixl"))
    p.apply([{"type": "swatch", "name": "accent", "color": "#ff0000"}, {"type": "remove", "target": "body"},
             {"type": "text-set", "target": "headline", "size": 90}])
    p.save()
    result = dispatch(workspace, "group-check", {"name": "launch", "checks": ["color", "structure"],
                                                 "required": ["logo"]})
    props = {(f["property"], f["document"]) for f in result["findings"]}
    assert ("swatch.accent", "story.vixl") in props and ("layers", "story.vixl") in props
    swatch = next(f for f in result["findings"] if f["property"] == "swatch.accent")
    assert swatch["fix"] == {"type": "swatch", "name": "accent", "color": "#006d77"}


def test_workspace_report_on_a_group_includes_group_checks(workspace):
    campaign(workspace, price="$59")
    result = dispatch(workspace, "check-all", {"group": "launch", "history": False, "fail_on": "never"})
    assert result["group"] == "launch" and result["count"] == 3
    assert any(f["property"] == "price" for f in result["group_checks"]["findings"])
    assert result["passed"]  # fail_on never
    failing = dispatch(workspace, "check-all", {"group": "launch", "history": False, "checks": ["bounds"]})
    assert not failing["passed"] and failing["group_checks"]["failing"]
    sarif = json.loads(render(failing, "sarif"))
    assert any(r["ruleId"] == "group-copy" for r in sarif["runs"][0]["results"])


# Find and replace across documents (#570) -------------------------------------------------------

def test_replace_dry_run_lists_every_match_and_apply_is_recoverable(workspace, monkeypatch):
    for index in range(10):
        document(workspace.resolve(f"docs/d{index}.vixl"), product="Vixl Pro" if index % 3 else "Vixl Studio")
    before = {p: p.read_bytes() for p in workspace.resolve("docs").glob("*.vixl")}
    request = {"documents": ["docs/*.vixl"], "replace": [{"text": "Vixl Pro", "with": "Vixl Studio", "match": "word"},
                                                        {"color": "#ff6a00", "with": "@accent", "tolerance": 4}]}
    dry = dispatch(workspace, "replace-across", request)
    assert dry["dry_run"] and {p: p.read_bytes() for p in before} == before
    by_doc = {entry["document"]: entry for entry in dry["documents"]}
    assert len(by_doc) == 10 and dry["matches"] == 6 + 10
    assert [m["after"] for m in by_doc["docs/d1.vixl"]["matches"] if m["kind"] == "text"] == ["Vixl Studio launch"]
    assert by_doc["docs/d0.vixl"]["count"] == 1  # only the color
    import vixl.project_groups as groups

    publish = groups.publish_file

    def interrupted(path, source, **kwargs):
        if str(source).endswith(".before.vixl") or path.name == "d5.vixl":
            raise OSError("Simulated crash")
        return publish(path, source, **kwargs)

    monkeypatch.setattr(groups, "publish_file", interrupted)
    with pytest.raises(OSError):
        dispatch(workspace, "replace-across", {**request, "dry_run": False})
    monkeypatch.setattr(groups, "publish_file", publish)
    with pytest.raises(VixlError, match="Recover"):
        dispatch(workspace, "replace-across", {**request, "dry_run": False})
    dispatch(workspace, "group-recover", {"name": "replace-across"})
    assert {p: p.read_bytes() for p in before} == before
    applied = dispatch(workspace, "replace-across", {**request, "dry_run": False})
    assert len(applied["published"]) == 10
    p = Project.load(workspace.resolve("docs/d1.vixl"))
    assert p.layer("headline")["text"] == "Vixl Studio launch" and p.layer("logo")["fill"] == "@accent"
    p.undo()
    p.undo()
    assert p.layer("headline")["text"] == "Vixl Pro launch" and p.layer("logo")["fill"] == "#ff6a00"


def test_replace_with_suites_publishes_only_clean_documents(workspace):
    for name in ("a", "b"):
        document(workspace.resolve(f"{name}.vixl"))
    p = Project.load(workspace.resolve("b.vixl"))
    p.apply({"type": "suite-set", "name": "copy", "suite": {"version": 1, "rules": [
        {"id": "short", "kind": "assert", "expression": "text.headline.font-size <= 20"}]}})
    p.save()
    original = workspace.resolve("b.vixl").read_bytes()
    result = dispatch(workspace, "replace-across", {"documents": ["*.vixl"], "suites": True, "dry_run": False,
                                                    "replace": [{"text": "launch", "with": "sale"}]})
    statuses = {entry["document"]: entry["status"] for entry in result["documents"]}
    assert statuses == {"a.vixl": "changed", "b.vixl": "needs_review"}
    assert result["published"] == ["a.vixl"] and workspace.resolve("b.vixl").read_bytes() == original


def test_replace_font_and_asset_keep_box(workspace, tmp_path):
    import hashlib

    from PIL import Image

    Image.new("RGBA", (40, 20), "red").save(tmp_path / "logo-2025.png")
    Image.new("RGBA", (30, 30), "blue").save(tmp_path / "logo-2026.png")
    p = Project(300, 200, "white")
    data = (ROOT / "src" / "vixl" / "data" / "DejaVuSans.ttf").read_bytes()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    p.apply([{"type": "font-register", "name": "old-sans", "asset": asset},
             {"type": "font-register", "name": "new-sans", "asset": asset},
             {"type": "add", "name": "logo", "path": str(tmp_path / "logo-2025.png"), "x": 10, "y": 10, "width": 80,
              "height": 40},
             {"type": "text", "name": "t", "text": "Hi", "x": 10, "y": 100, "size": 20, "font": "old-sans"}])
    p.save(tmp_path / "a.vixl")
    result = dispatch(workspace, "replace-across", {"documents": ["a.vixl"], "dry_run": False, "replace": [
        {"asset": "logo-2025.png", "with": "logo-2026.png"}, {"font": "old-sans", "with": "new-sans"}]})
    kinds = sorted(m["kind"] for m in result["documents"][0].get("matches", []))
    assert kinds == ["asset", "font"] and result["published"] == ["a.vixl"], result
    saved = Project.load(tmp_path / "a.vixl")
    layer = saved.layer("logo")
    assert (layer["x"], layer["y"], layer["width"], layer["height"]) == (30, 10, 40, 40)
    assert saved.layer("t")["font"] == saved.state["fonts"]["new-sans"]
    again = dispatch(workspace, "replace-across", {"documents": ["a.vixl"], "replace": [
        {"asset": "logo-2025.png", "with": "logo-2026.png"}]})
    assert again["matches"] == 0  # the layer's image no longer comes from the old file
    missing = dispatch(workspace, "replace-across", {"documents": ["a.vixl"], "replace": [
        {"font": "new-sans", "with": "nonexistent-grotesk"}]})
    assert missing["documents"][0]["status"] == "failed" and "nonexistent" in missing["documents"][0]["error"]["message"]


def test_replace_rules_are_validated(workspace):
    document(workspace.resolve("a.vixl"))
    for rule, message in (({"text": "a", "color": "b", "with": "c"}, "exactly one"),
                          ({"text": "a"}, "with must be"), ({"text": "(", "with": "x", "match": "regex"}, "regex"),
                          ({"color": "nonsense-color", "with": "#000"}, "not a color")):
        with pytest.raises(VixlError, match=message):
            dispatch(workspace, "replace-across", {"documents": ["a.vixl"], "replace": [rule]})
    # A swatch the document lacks fails that document only.
    result = dispatch(workspace, "replace-across", {"documents": ["a.vixl"], "replace": [
        {"color": "#ff6a00", "with": "@missing"}]})
    assert result["documents"][0]["status"] == "failed" and "not a color" in result["documents"][0]["error"]["message"]


# Group change review (#575) ---------------------------------------------------------------------

def five_members(workspace):
    names = [f"m{index}.vixl" for index in range(5)]
    for name in names:
        document(workspace.resolve(name))
    dispatch(workspace, "group-define", {"name": "five", "documents": names})
    return names


def test_dry_run_review_sheet_and_rejected_member_left_untouched(workspace):
    names = five_members(workspace)
    move = [{"type": "move", "target": "logo", "x": 10, "y": 10}]
    dry = dispatch(workspace, "group-apply", {"name": "five", "operations": move, "review": "review.png"})
    assert dry["review"] == "review.png" and workspace.resolve("review.png").stat().st_size > 1000
    assert all(entry["changed_fraction"] > 0 and entry["changed_region"] for entry in dry["documents"])
    page = dispatch(workspace, "group-apply", {"name": "five", "operations": move, "review": "review.html"})
    html = workspace.resolve("review.html").read_text()
    assert page["decision_file"] == "review-decisions.json" and html.count('data-path="m') == 5
    assert "Download decisions" in html
    rejected = workspace.resolve("m3.vixl").read_bytes()
    result = dispatch(workspace, "group-apply", {"name": "five", "operations": move, "dry_run": False,
                                                 "reject": ["m3.vixl"]})
    assert result["published"] == [n for n in names if n != "m3.vixl"] and result["untouched"] == ["m3.vixl"]
    assert workspace.resolve("m3.vixl").read_bytes() == rejected
    assert Project.load(workspace.resolve("m0.vixl")).layer("logo")["x"] == 10


def test_proof_decisions_feed_back_into_group_apply(workspace):
    five_members(workspace)
    decisions = {"proof": "review", "items": [{"id": "item-1", "path": "m0.vixl", "decision": "approved"},
                                              {"id": "item-2", "path": "m1.vixl", "decision": "rejected"},
                                              {"id": "item-3", "path": "m2.vixl", "decision": "pending"}]}
    workspace.resolve("review-decisions.json").write_text(json.dumps(decisions))
    result = dispatch(workspace, "group-apply", {"name": "five", "dry_run": False, "decisions": "review-decisions.json",
                                                 "operations": [{"type": "move", "target": "logo", "x": 5}]})
    assert result["published"] == ["m0.vixl"]
    with pytest.raises(VixlError, match="not a member"):
        dispatch(workspace, "group-apply", {"name": "five", "reject": ["other.vixl"],
                                            "operations": [{"type": "move", "target": "logo", "x": 5}]})


def test_dry_run_reports_failing_suites_instead_of_refusing(workspace):
    five_members(workspace)
    p = Project.load(workspace.resolve("m1.vixl"))
    p.apply({"type": "suite-set", "name": "pos", "suite": {"version": 1, "rules": [
        {"id": "x", "kind": "assert", "expression": "layer.logo.x >= 100"}]}})
    p.save()
    for name in ("m0.vixl", "m2.vixl", "m3.vixl", "m4.vixl"):
        q = Project.load(workspace.resolve(name))
        q.apply({"type": "suite-set", "name": "pos", "suite": p.state["suites"]["pos"]})
        q.save()
    request = {"name": "five", "suites": ["pos"], "operations": [{"type": "move", "target": "logo", "x": 10}]}
    dry = dispatch(workspace, "group-apply", request)
    assert dry["passed"] is False and not any(entry["passed"] for entry in dry["documents"])
    with pytest.raises(VixlError, match="Group checks failed"):
        dispatch(workspace, "group-apply", {**request, "dry_run": False})


# Command line and CI -------------------------------------------------------------------------

def test_cli_check_all_prints_formats_and_sets_the_exit_code(tmp_path):
    document(tmp_path / "ok.vixl")
    document(tmp_path / "bad.vixl", faint=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    command = [sys.executable, "-m", "vixl", "check", "--all", "*.vixl", "--no-history"]
    done = subprocess.run([*command, "--format", "sarif"], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 1 and json.loads(done.stdout)["version"] == "2.1.0"
    done = subprocess.run([*command[:-2], "ok.vixl", "--no-history", "--fail-on", "error"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0 and "| `ok.vixl` |" in done.stdout
    done = subprocess.run([sys.executable, "-m", "vixl", "--json", "check", "--all", "--no-history"], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 1 and json.loads(done.stdout)["count"] == 2


def action_step_script(step_id):
    """The ``run: |`` block of the action.yml step with ``id: step_id`` (no YAML dependency)."""
    lines = (ROOT / "action.yml").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"id: {step_id}")
    head = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[head]) - len(lines[head].lstrip()) + 2
    body = []
    for line in lines[head + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).rstrip() + "\n"


# On Windows runners `bash` is often the WSL stub, not a POSIX shell; the script runs on the Linux and macOS jobs.
@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None or shutil.which("git") is None,
                    reason="needs a POSIX bash and git")
def test_action_check_step_runs_the_engine(tmp_path):
    step = {"run": action_step_script("check")}
    document(tmp_path / "designs" / "good.vixl")
    document(tmp_path / "designs" / "bad.vixl", faint=True)
    output, summary = tmp_path / "github-output", tmp_path / "summary.md"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY":
           str(summary), "VIXL_PATHS": "designs/**/*.vixl", "VIXL_FAIL_ON": "error", "VIXL_ANNOTATIONS": "true",
           "VIXL_FORMATS": "json junit", "VIXL_SARIF": "true", "VIXL_PROOF": "false"}
    for key in ("VIXL_GROUP", "VIXL_CHECKS", "VIXL_SUITE", "VIXL_BASE", "VIXL_CHANGED"):
        env[key] = ""
    script = step["run"].replace("python -m vixl", f'"{sys.executable}" -m vixl')
    done = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, done.stderr
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert outputs["status"] == "1" and outputs["sarif"] == ".vixl-ci/vixl.sarif"
    assert "::error file=designs/bad.vixl" in done.stdout and "`designs/good.vixl`" in summary.read_text()
    for name in ("report.json", "junit.xml", "vixl.sarif"):
        assert (tmp_path / ".vixl-ci" / name).is_file()
