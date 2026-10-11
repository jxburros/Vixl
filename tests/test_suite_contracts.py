"""Suite rules that read the copy (text) and production budgets (budget), the placeholders check and brand word lists,
coverage over artboards/pages/comps, library suites inherited by groups and the workspace, and suite-infer."""

import json

import pytest

from vixl import Project
from vixl.assurance import RULE_FIELDS, validate_suite
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import describe, dispatch


def statuses(project, rules, **options):
    report = project.check_suite({"rules": rules}, **options)
    return {item["id"]: item for item in report["results"]}


def copy_document():
    p = Project(600, 400, "white")
    p.apply([
        {"type": "variable", "name": "offer", "value": "Spring sale"},
        {"type": "text", "name": "headline", "text": "${offer} starts today", "size": 40, "x": 20, "y": 20,
         "color": "#111111"},
        {"type": "text", "name": "legal", "text": "Terms apply. See store for details.", "size": 14, "x": 20,
         "y": 340, "color": "#111111"},
    ])
    return p


# --- text rule (#552) ---------------------------------------------------------------------------------------------

def test_text_rule_measures_drawn_copy_after_variables():
    p = copy_document()
    found = statuses(p, [
        {"id": "short", "kind": "text", "target": "headline", "max_characters": 40},
        {"id": "too-short", "kind": "text", "target": "headline", "max_characters": 10},
        {"id": "words", "kind": "text", "target": "headline", "min_words": 2, "max_words": 4},
        {"id": "disclaimer", "kind": "text", "contains": "Terms apply"},
        {"id": "missing", "kind": "text", "contains": ["Terms apply", "Offer ends"]},
        {"id": "no-free", "kind": "text", "forbid": r"(?i)\bfree\b"},
        {"id": "pattern", "kind": "text", "target": "headline", "pattern": "^Spring"},
        {"id": "case", "kind": "text", "target": "legal", "contains": "TERMS APPLY", "case": "insensitive"},
        {"id": "case-sensitive", "kind": "text", "target": "legal", "contains": "TERMS APPLY"},
    ])
    expected = {"short": "passed", "too-short": "failed", "words": "passed", "disclaimer": "passed",
                "missing": "failed", "no-free": "passed", "pattern": "passed", "case": "passed",
                "case-sensitive": "failed"}
    assert {key: found[key]["status"] for key in expected} == expected
    # Results carry the drawn text (variables resolved) and its counts.
    assert found["short"]["layers"] == [{"layer": "headline", "text": "Spring sale starts today", "characters": 24,
                                         "words": 4}]
    assert found["missing"]["missing"] == ["Offer ends"]


def test_text_rule_checks_each_row_and_artboard_with_its_own_copy():
    p = copy_document()
    p.apply({"type": "artboard", "name": "story", "width": 300, "height": 500, "variables": {"offer": "FREE gift"}})
    rule = [{"id": "no-free", "kind": "text", "forbid": r"(?i)\bfree\b"},
            {"id": "short", "kind": "text", "target": "headline", "max_characters": 24}]
    assert statuses(p, rule)["no-free"]["status"] == "passed"
    story = statuses(p, rule, artboard="story")
    assert story["no-free"]["status"] == "failed" and story["no-free"]["forbidden"][0]["match"] == "FREE"
    row = statuses(p, rule, variables={"offer": "Our biggest summer clearance"})
    assert row["short"]["status"] == "failed" and row["short"]["layers"][0]["characters"] > 24


def test_text_rule_fields_are_validated_and_described():
    for bad in ({"id": "a", "kind": "text"}, {"id": "a", "kind": "text", "forbid": "(unclosed"},
                {"id": "a", "kind": "text", "max_words": 2.5}, {"id": "a", "kind": "text", "contains": [],},
                {"id": "a", "kind": "text", "contains": "x", "case": "upper"}):
        with pytest.raises(VixlError):
            validate_suite({"rules": [bad]})
    suite = describe()["definitions"]["suite"]
    assert {"text", "budget"} <= set(suite["properties"]["rules"]["items"]["properties"]["kind"]["enum"])
    properties = suite["properties"]["rules"]["items"]["properties"]
    for kind in ("text", "budget"):
        for field in RULE_FIELDS[kind]:
            assert properties[field]["description"], field


def test_unknown_text_target_needs_review_rather_than_passing():
    p = copy_document()
    assert statuses(p, [{"id": "x", "kind": "text", "target": "nope", "max_words": 3}])["x"]["status"] == "needs_review"


def test_budget_rule_counts_layers_fonts_bytes_and_image_ppi():
    from PIL import Image
    from vixl.assets import add_image

    p = copy_document()
    p.apply({"type": "canvas", "dpi": 300})
    asset = add_image(p, Image.new("RGBA", (60, 60), "red"))
    p.apply({"type": "add", "name": "photo", "asset": asset, "x": 300, "y": 100, "width": 240, "height": 240})
    found = statuses(p, [
        {"id": "ok", "kind": "budget", "max_layers": 3, "max_fonts": 1, "max_bytes": 10_000_000},
        {"id": "layers", "kind": "budget", "max_layers": 2},
        {"id": "bytes", "kind": "budget", "max_bytes": 100},
        {"id": "ppi", "kind": "budget", "min_ppi": 150},
    ])
    assert {key: item["status"] for key, item in found.items() if key != "missing-glyphs"} == {
        "ok": "passed", "layers": "failed", "bytes": "failed", "ppi": "failed"}
    assert found["ok"]["layers"] == 3 and len(found["ok"]["fonts"]) == 1
    assert found["ppi"]["low_resolution"] == [{"layer": "photo", "effective_ppi": 75}]
    with pytest.raises(VixlError):
        validate_suite({"rules": [{"id": "b", "kind": "budget"}]})


# --- placeholders check and brand words (#553) ----------------------------------------------------------------------

def placeholder_issues(project, **options):
    return [item for item in project.check(checks=["placeholders"], **options)["issues"]]


def test_placeholders_flags_leftover_template_copy_but_not_escapes_or_marked_text():
    p = Project(600, 400, "white")
    p.apply([
        {"type": "text", "name": "lorem", "text": "Lorem ipsum dolor sit amet", "x": 10, "y": 10},
        {"type": "text", "name": "todo", "text": "Price TBD", "x": 10, "y": 60},
        {"type": "text", "name": "slot", "text": "Your headline here", "x": 10, "y": 110},
        {"type": "text", "name": "escaped", "text": "Write $${name} to merge", "x": 10, "y": 160},
        {"type": "text", "name": "foreign", "text": "Hello {{first_name}}", "x": 10, "y": 210},
        {"type": "text", "name": "fine", "text": "A todo list for spring", "x": 10, "y": 260},
        {"type": "text", "name": "form", "text": "Sign your name here", "x": 10, "y": 310},
        {"type": "layer-intent", "target": "form", "literal_text": True},
    ])
    issues = placeholder_issues(p)
    by_layer = {item["layers"][0]: item for item in issues}
    assert set(by_layer) == {"lorem", "todo", "slot", "foreign"}
    assert all(by_layer[name]["action"] == "fix" for name in ("lorem", "todo", "slot"))
    # {{...}} is another tool's syntax: worth a look, not a failure.
    assert by_layer["foreign"]["action"] == "review"
    assert not p.check(checks=["placeholders"])["passed"]


def test_layout_slot_left_unfilled_is_a_fix_naming_the_slot():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "event-poster", "title": "Night Market", "seed": 4})
    report = p.check()
    unfilled = [item for item in report["issues"] if item["check"] == "blanks"]
    assert {item["slot"] for item in unfilled} == {"label", "body", "cta", "caption"}
    assert all(item["action"] == "fix" for item in unfilled)
    # The [Label] slot text is the blanks check's to report; placeholders does not report it twice.
    assert not [item for item in report["issues"] if item["check"] == "placeholders"]


def test_undefined_variables_are_reported_instead_of_failing_the_check():
    p = copy_document()
    # A link variable or deleted document variable can leave a placeholder that nothing defines.
    p.state["layers"][0]["text"] = "${offer} for ${audience}"
    report = p.check(checks=["placeholders"])
    undefined = [item for item in report["issues"] if item.get("code") == "undefined-variable"]
    assert [item["variable"] for item in undefined] == ["audience"] and undefined[0]["severity"] == "error"


def test_production_row_missing_a_variable_names_the_row(tmp_path):
    from vixl.production import run

    p = Project(300, 200, "white")
    p.apply([{"type": "variable", "name": "headline", "value": "Headline here"},
             {"type": "text", "name": "title", "text": "${headline}", "size": 24, "x": 10, "y": 10}])
    report = run(p, {"rows": [{"headline": "Spring sale"}, {"other": "x"}], "format": "png"}, tmp_path / "out")
    first, second = report["results"]
    assert first["status"] == "completed"
    assert second["status"] == "needs_review" and second["row"] == 2
    finding = second["checks"]["placeholders"]["issues"][0]
    assert finding["variant"] == second["id"] and "row 2" in finding["message"]


def test_brand_words_and_placeholder_patterns(tmp_path):
    (tmp_path / "brand.json").write_text(json.dumps({
        "words": {"forbid": ["cheap"], "prefer": {"utilize": "use"}},
        "placeholders": [r"\bCOPY TK\b"],
    }))
    p = Project(600, 300, "white")
    p._workspace = tmp_path
    p.apply([
        {"type": "text", "name": "a", "text": "Cheap deals that utilize magic", "x": 10, "y": 10},
        {"type": "text", "name": "b", "text": "COPY TK", "x": 10, "y": 100},
    ])
    issues = p.check(checks=["brand", "placeholders"])["issues"]
    codes = {(item["check"], item.get("code"), item["action"]) for item in issues}
    assert ("brand", "forbidden-word", "fix") in codes and ("brand", "preferred-word", "review") in codes
    assert any(item["check"] == "placeholders" and item["layers"] == ["b"] for item in issues)
    found = statuses(p, [{"id": "brand-words", "kind": "text", "brand": True}])
    assert found["brand-words"]["status"] == "failed" and found["brand-words"]["forbidden"][0]["match"] == "Cheap"
    (tmp_path / "brand.json").write_text(json.dumps({"words": {"prefer": {"x": 3}}}))
    with pytest.raises(VixlError):
        p.check(checks=["brand"])


# --- coverage (#556) --------------------------------------------------------------------------------------------------

def boards_document():
    p = Project(800, 400, "white")
    p.apply([
        {"type": "text", "name": "title", "text": "Launch", "size": 60, "x": 40, "y": 40, "color": "#111111"},
        {"type": "artboard", "name": "square", "width": 800, "height": 400},
        {"type": "artboard", "name": "story", "width": 200, "height": 400},
    ])
    return p


def test_suite_rule_failing_on_one_artboard_names_it():
    p = boards_document()
    suite = {"rules": [{"id": "inside", "kind": "relation", "target": "title", "to": "canvas", "position": "inside"}],
             "sampling": {"artboards": "all"}}
    report = p.check_suite(suite)
    assert report["status"] == "failed" and report["coverage"]["artboards"] == ["square", "story"]
    failed = [item for item in report["results"] if item["status"] == "failed"]
    assert [item["variant"] for item in failed] == [{"artboard": "story"}]
    assert {group["artboard"]: group["status"] for group in report["groups"]} == {"square": "passed", "story": "failed"}
    # The same coverage can be asked for at run time, and the workload cap counts every variant.
    assert p.check_suite({"rules": suite["rules"]}, artboards=["square"])["status"] == "passed"


def test_design_check_covers_every_artboard_in_one_report():
    p = boards_document()
    report = p.check(checks=["bounds"], artboards="all")
    assert report["coverage"] == {"variants": 2, "artboards": ["square", "story"]}
    cut = [item for item in report["issues"] if item["check"] == "bounds"]
    assert cut and all(item["variant"] == {"artboard": "story"} and item["message"].startswith("[artboard story]")
                       for item in cut)
    assert {v["artboard"]: v["passed"] for v in report["variants"]} == {"square": True, "story": False}


def test_coverage_over_pages_skips_hidden_pages_unless_asked():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "page", "action": "add", "name": "One"},
        {"type": "text", "name": "t1", "text": "Fine", "size": 30, "x": 20, "y": 20},
        {"type": "page", "action": "add", "name": "Two"},
        {"type": "text", "name": "t2", "text": "Lorem ipsum", "size": 30, "x": 20, "y": 20},
        {"type": "page", "action": "add", "name": "Notes", "hidden": True},
        {"type": "text", "name": "t3", "text": "TODO", "size": 30, "x": 20, "y": 20},
    ])
    report = p.check(checks=["placeholders"], pages="all")
    assert report["coverage"]["pages"] == ["One", "Two"]
    assert [item["variant"]["page"] for item in report["issues"]] == ["Two"]
    hidden = p.check(checks=["placeholders"], pages="all", include_hidden=True)
    assert sorted(item["variant"]["page"] for item in hidden["issues"]) == ["Notes", "Two"]
    suite = p.check_suite({"rules": [{"id": "copy", "kind": "text", "forbid": "(?i)lorem"}]}, pages="all")
    assert [group["status"] for group in suite["groups"]] == ["passed", "failed"]


def test_coverage_cli_flags(tmp_path, capsys):
    from vixl.cli import main

    path = tmp_path / "boards.vixl"
    boards_document().save(path)
    main(["-p", str(path), "check", "--checks", "bounds", "--artboards", "all"])
    report = json.loads(capsys.readouterr().out)
    assert report["coverage"]["artboards"] == ["square", "story"]
    main(["-p", str(path), "check", "--checks", "bounds", "--artboards", "square"])
    assert json.loads(capsys.readouterr().out)["passed"]


# --- library suites inherited by groups and the workspace (#574) ------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    session = Session(workspace=tmp_path)
    for name in ("a.vixl", "b.vixl"):
        session.create(name, 400, 200)
        session.apply([{"type": "text", "name": "title", "text": "Hello", "size": 40, "x": 20, "y": 20,
                        "color": "#111111"}])
    dispatch(session, "resource-save", {"kind": "suites", "name": "delivery", "value": {"rules": [
        {"id": "short", "kind": "text", "target": "title", "max_characters": 10},
        {"id": "big", "kind": "hierarchy", "targets": ["title", "title"], "ratio": 1},
    ]}})
    dispatch(session, "group-define", {"name": "family", "documents": ["a.vixl", "b.vixl"], "suites": ["delivery"]})
    return session


def test_group_members_inherit_library_suites_by_reference(workspace):
    report = dispatch(workspace, "check", {})
    assert report["passed"] and set(report["suites"]) == {"delivery"}
    inherited = report["suites"]["delivery"]
    assert inherited["source"] == "group:family" and inherited["library"] == "delivery" and inherited["library_hash"]
    # Editing the library changes every member's next check without touching member files.
    before = workspace.resolve("a.vixl").read_bytes()
    dispatch(workspace, "resource-save", {"kind": "suites", "name": "delivery", "value": {"rules": [
        {"id": "short", "kind": "text", "target": "title", "max_characters": 3}]}})
    changed = dispatch(workspace, "check", {"suite": "delivery"})
    assert changed["status"] == "failed" and changed["contract_changed"]["last_passed_hash"] == inherited["library_hash"]
    assert workspace.resolve("a.vixl").read_bytes() == before
    # group-apply runs the inherited suites by default: a dry run reports them, publishing refuses.
    move = [{"type": "move", "target": "title", "x": 5}]
    preview = dispatch(workspace, "group-apply", {"name": "family", "operations": move})
    assert not preview["passed"] and preview["documents"][0]["checks"][0]["status"] == "failed"
    with pytest.raises(VixlError) as caught:
        dispatch(workspace, "group-apply", {"name": "family", "operations": move, "dry_run": False})
    assert caught.value.code == "check_failed"


def test_check_all_runs_inherited_library_suites_and_rule_waivers_apply(workspace):
    result = dispatch(workspace, "check-all", {"group": "family", "checks": ["bounds"], "history": False,
                                               "group_checks": False})
    assert all(set(entry["suites"]) == {"delivery"} for entry in result["documents"]) and result["passed"]
    dispatch(workspace, "resource-save", {"kind": "suites", "name": "delivery", "value": {"rules": [
        {"id": "short", "kind": "text", "target": "title", "max_characters": 3}]}})
    assert not dispatch(workspace, "check-all", {"group": "family", "checks": ["bounds"], "history": False,
                                                 "group_checks": False})["passed"]
    # A document waiver of the inherited rule makes it waived, so the outcome is validated again.
    workspace.apply({"type": "waiver", "rule": "short", "suite": "delivery", "reason": "long title approved"})
    report = dispatch(workspace, "check", {"suite": "delivery"})
    assert report["results"][0]["status"] == "waived" and report["outcome"]["validation"] == "passed"


def test_member_override_by_id_is_listed_in_the_report(workspace):
    workspace.apply({"type": "suite-set", "name": "local", "suite": {"extends": "delivery", "rules": [
        {"id": "short", "kind": "text", "severity": "warning"},
        {"id": "has-cta", "kind": "count", "target": "cta", "minimum": 1}]}})
    report = dispatch(workspace, "check", {})
    assert set(report["suites"]) == {"local"}  # The extending suite stands in for the inherited one.
    local = report["suites"]["local"]
    assert local["overrides"] == [{"id": "short", "fields": ["severity"]}] and local["added"] == ["has-cta"]
    assert {item["id"]: item["status"] for item in local["results"]}["has-cta"] == "failed"
    # An override must keep the library rule's kind.
    workspace.apply({"type": "suite-set", "name": "bad", "suite": {"extends": "delivery", "rules": [
        {"id": "short", "kind": "count", "minimum": 1}]}})
    with pytest.raises(VixlError):
        dispatch(workspace, "check", {"suite": "bad"})


def test_workspace_brand_suites_and_suite_use_by_reference(workspace, tmp_path):
    (tmp_path / "brand.json").write_text(json.dumps({"suites": ["delivery"]}))
    workspace.create("c.vixl", 100, 100)
    workspace.apply({"type": "text", "name": "title", "text": "Hi", "size": 20})
    report = dispatch(workspace, "check", {})
    assert report["suites"]["delivery"]["source"] == "workspace"
    dispatch(workspace, "suite-use", {"name": "delivery", "as": "contract", "reference": True})
    with workspace.project() as project:
        assert project.state["suites"]["contract"] == {"version": 1, "extends": "delivery", "rules": []}
    assert dispatch(workspace, "check", {"suite": "contract"})["library"] == "delivery"


# --- suite-infer (#580) ---------------------------------------------------------------------------------------------

def poster(session, path, width, height, title_size=None):
    scale = width / 800
    session.create(path, width, height)
    session.apply([
        {"type": "solid", "name": "bg", "color": "#f4efe6"},
        {"type": "text", "name": "headline", "text": "Summer Festival", "size": round((title_size or 96) * scale),
         "x": "center", "y": round(120 * scale), "color": "#1b1b1b"},
        {"type": "text", "name": "body", "text": "Live music all weekend", "size": round(40 * scale),
         "x": "center", "y": round(320 * scale), "color": "#1b1b1b"},
        {"type": "shape", "shape": "rectangle", "name": "logo", "width": round(160 * scale),
         "height": round(80 * scale), "fill": "#c0392b", "x": "center", "y": round(820 * scale)},
    ])


def test_suite_infer_proposes_explained_rules_that_carry_to_sibling_sizes(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    session = Session(workspace=tmp_path)
    poster(session, "small.vixl", 400, 500)
    poster(session, "broken.vixl", 400, 500, title_size=30)
    poster(session, "approved.vixl", 800, 1000)
    result = dispatch(session, "suite-infer", {"name": "festival"})
    suite = result["suite"]
    validate_suite(suite)
    kinds = {rule["kind"] for rule in suite["rules"]}
    assert {"hierarchy", "relation", "contrast", "text", "count", "palette"} <= kinds
    assert all(entry["measured"] for entry in result["explanations"])
    assert not result["applied"]
    with session.project() as project:
        assert "festival" not in project.state.get("suites", {})  # Never attached automatically.
    small = Project.load(tmp_path / "small.vixl").check_suite(suite)
    assert small["passed"], [r for r in small["results"] if r["status"] != "passed"]
    broken = Project.load(tmp_path / "broken.vixl").check_suite(suite)
    failed = {item["id"] for item in broken["results"] if item["status"] == "failed"}
    passed = {item["id"] for item in broken["results"] if item["status"] == "passed"}
    assert "hierarchy" in failed and passed  # Meaningful: neither all-pass nor all-fail.


def test_suite_infer_apply_saves_a_library_suite_and_from_group_keeps_shared_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    session = Session(workspace=tmp_path)
    poster(session, "small.vixl", 400, 500)
    poster(session, "approved.vixl", 800, 1000)
    dispatch(session, "group-define", {"name": "posters", "documents": ["approved.vixl", "small.vixl"]})
    saved = dispatch(session, "suite-infer", {"name": "festival", "apply": True, "group": "posters"})
    assert saved["applied"] and saved["group"]["suites"] == ["festival"]
    with pytest.raises(VixlError):
        dispatch(session, "suite-infer", {"name": "festival", "apply": True})
    assert dispatch(session, "check", {})["suites"]["festival"]["source"] == "group:posters"
    family = dispatch(session, "suite-infer", {"name": "family", "from_group": "posters"})
    assert family["members"] == 2
    validate_suite(family["suite"])
    for name in ("approved.vixl", "small.vixl"):
        member = Project.load(tmp_path / name)
        assert member.check_suite(family["suite"])["passed"]
