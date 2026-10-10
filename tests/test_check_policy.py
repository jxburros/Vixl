"""Check policy: waivers (#562, #531), severity profiles (#563) and the brand contrast and palette rules
(#527, #528)."""

import json
from pathlib import Path

import pytest

from vixl import Project, VixlError
from vixl.commands import compile_command
from vixl.interfaces import Session
from vixl.workflows import dispatch

PAST, FUTURE = "2001-01-01", "2999-12-31"


def ghost(workspace=None):
    """The reproduction of #531: a faint step numeral behind a slide title."""
    p = Project(1080, 1350, "#09090B", workspace=workspace)
    p.apply({"type": "text", "name": "ghost", "text": "01", "x": 88, "y": 210, "size": 300, "color": "#FF2D5533"})
    return p


def contrast(report):
    return [item for item in report["issues"] if item["check"] == "contrast"]


def test_low_contrast_decorative_text_is_reported_as_a_fix_without_a_waiver(tmp_path):
    report = ghost(tmp_path).check(checks=["contrast"])
    assert not report["passed"] and contrast(report)[0]["action"] == "fix"
    assert "layer-intent waive" in contrast(report)[0]["message"]


def test_layer_waiver_keeps_the_finding_listed_as_informational(tmp_path):
    p = ghost(tmp_path)
    p.apply({"type": "layer-intent", "target": "ghost", "role": "decoration",
             "waive": [{"check": "contrast", "reason": "ghost numeral", "expires": FUTURE}]})
    report = p.check(checks=["contrast"])
    item = contrast(report)[0]
    assert report["passed"] and item["severity"] == "info" and item["action"] == "informational"
    assert item["waived"] == {"scope": "layer", "check": "contrast", "reason": "ghost numeral", "expires": FUTURE,
                              "layer": "ghost", "severity": "error", "action": "fix"}
    assert report["by_action"]["informational"] == [0]
    assert report["waivers"]["active"][0]["matched"] == 1 and report["waivers"]["expired"] == []
    # waivers=False shows the finding as if nothing were waived.
    assert not p.check(checks=["contrast"], waivers=False)["passed"]


def test_allow_low_contrast_is_an_alias_for_a_contrast_waiver(tmp_path):
    p = ghost(tmp_path)
    result = p.apply({"type": "layer-intent", "target": "ghost", "allow_low_contrast": True})
    assert any("allow_low_contrast" in note for note in result.get("normalized", []))
    assert p.layer("ghost")["waive"] == [{"check": "contrast"}]
    assert p.check(checks=["contrast"])["passed"]
    p.apply({"type": "layer-intent", "target": "ghost", "waive": []})
    assert "waive" not in p.layer("ghost")


def test_a_group_waiver_covers_the_text_inside_it(tmp_path):
    p = ghost(tmp_path)
    p.apply([{"type": "group", "name": "backdrop", "targets": ["ghost"]},
             {"type": "layer-intent", "target": "backdrop", "waive": ["contrast"]}])
    assert p.check(checks=["contrast"])["passed"]


def test_expired_waiver_turns_the_finding_back_on_and_asks_for_a_decision(tmp_path):
    p = ghost(tmp_path)
    p.apply({"type": "waiver", "check": "contrast", "target": "ghost", "reason": "launch week only", "expires": PAST})
    report = p.check(checks=["contrast"])
    original, note = contrast(report)
    assert original["severity"] == "error" and original["waiver_expired"]["expires"] == PAST
    assert note["code"] == "waiver-expired" and note["action"] == "fix" and "renew" in note["message"]
    assert not report["passed"] and report["waivers"]["expired"][0]["reason"] == "launch week only"


def test_strict_check_fails_on_an_expired_waiver_even_without_other_findings(tmp_path):
    p = Project(400, 300, "white", workspace=tmp_path)
    p.apply([{"type": "text", "name": "title", "text": "Hello", "x": 40, "y": 40, "size": 40, "color": "black"},
             {"type": "waiver", "check": "contrast", "reason": "old exception", "expires": PAST}])
    path = tmp_path / "doc.vixl"
    p.save(path)
    from vixl.cli import main

    assert main(["-p", str(path), "check", "--checks", "contrast", "--strict"]) != 0
    p.apply({"type": "waiver", "check": "contrast", "remove": True})
    assert "waivers" not in p.state
    p.save(path)
    assert main(["-p", str(path), "check", "--checks", "contrast", "--strict"]) == 0


def test_document_waiver_operation_needs_a_reason_and_validates_its_fields(tmp_path):
    p = ghost(tmp_path)
    with pytest.raises(VixlError, match="reason"):
        p.apply({"type": "waiver", "check": "contrast"})
    with pytest.raises(VixlError, match="unknown check"):
        p.apply({"type": "waiver", "check": "contrasts", "reason": "typo"})
    with pytest.raises(VixlError, match="expires"):
        p.apply({"type": "waiver", "check": "contrast", "reason": "x", "expires": "next week"})
    with pytest.raises(VixlError, match="rule"):
        p.apply({"type": "layer-intent", "target": "ghost", "waive": [{"rule": "r1"}]})
    p.apply({"type": "waiver", "check": "contrast", "reason": "whole cover is a mood piece"})
    item = contrast(p.check(checks=["contrast"]))[0]
    assert item["waived"]["scope"] == "document" and item["waived"]["reason"] == "whole cover is a mood piece"
    p.save(tmp_path / "w.vixl")
    reopened = Project.load(tmp_path / "w.vixl")
    assert reopened.state["waivers"] == p.state["waivers"]


def test_overlap_waiver_with_partners_only_covers_those_partners(tmp_path):
    p = Project(600, 300, "white", workspace=tmp_path)
    p.apply([{"type": "text", "name": "a", "text": "OVERLAP", "x": 20, "y": 20, "size": 80, "color": "black"},
             {"type": "text", "name": "b", "text": "OVERLAP", "x": 40, "y": 40, "size": 80, "color": "black"},
             {"type": "text", "name": "c", "text": "OVERLAP", "x": 60, "y": 60, "size": 80, "color": "black"},
             {"type": "layer-intent", "target": "a", "waive": [{"check": "overlap", "with": ["b"]}]}])
    report = p.check(checks=["overlap"])
    waived = {tuple(x["layers"]) for x in report["issues"] if x.get("waived")}
    open_ = {tuple(x["layers"]) for x in report["issues"] if not x.get("waived")}
    assert ("a", "b") in waived and ("a", "c") in open_ and ("b", "c") in open_
    assert report["issues"][0]["waived"]["with"] == ["b"]


def test_suite_rule_waiver_marks_the_result_waived_and_expires(tmp_path):
    p = Project(400, 300, "white", workspace=tmp_path)
    p.apply([{"type": "text", "name": "title", "text": "Hi", "x": 10, "y": 10, "size": 20},
             {"type": "suite-set", "name": "brief", "suite": {"version": 1, "rules": [
                 {"id": "big-title", "kind": "property", "target": "title", "field": "size", "expected": 64}]}}])
    assert p.check_suite("brief")["status"] == "failed"
    p.apply({"type": "waiver", "rule": "big-title", "suite": "brief", "reason": "client asked for a small title",
             "expires": FUTURE})
    report = p.check_suite("brief")
    assert report["passed"] and report["results"][0]["status"] == "waived"
    assert report["results"][0]["waived"]["reason"] == "client asked for a small title"
    assert report["waivers"]["active"][0]["matched"] == 1
    p.apply({"type": "waiver", "rule": "big-title", "suite": "brief", "reason": "expired", "expires": PAST})
    report = p.check_suite("brief")
    assert report["status"] == "failed" and report["results"][0]["waiver_expired"]["expires"] == PAST


def test_workspace_waivers_apply_to_every_document(tmp_path):
    (tmp_path / ".vixl-checks.json").write_text(json.dumps(
        {"waivers": [{"check": "contrast", "target": "ghost", "reason": "house watermark style"}]}))
    item = contrast(ghost(tmp_path).check(checks=["contrast"]))[0]
    assert item["waived"]["scope"] == "workspace" and item["waived"]["target"] == "ghost"
    (tmp_path / ".vixl-checks.json").write_text(json.dumps({"waivers": [{"check": "nope"}]}))
    with pytest.raises(VixlError, match="unknown check"):
        from vixl.policy import load

        load(tmp_path)


def test_waiver_command_line(tmp_path):
    assert compile_command(["waiver", "contrast", "--target", "ghost", "--reason", "faint on purpose",
                            "--expires", FUTURE]) == {
        "type": "waiver", "check": "contrast", "target": "ghost", "reason": "faint on purpose", "expires": FUTURE}
    assert compile_command(["layer-intent", "ghost", "--waive", "contrast", "bounds"])["waive"] == ["contrast", "bounds"]


def test_proof_page_lists_waivers(tmp_path):
    from vixl.proof import proof_page

    p = ghost(tmp_path)
    p.apply({"type": "waiver", "check": "contrast", "target": "ghost", "reason": "ghost numeral", "expires": FUTURE})
    p.save(tmp_path / "ghost.vixl")
    result = proof_page(["ghost.vixl"], "proof.html", resolve=lambda value: tmp_path / value)
    page = Path(result["output"]).read_text(encoding="utf-8")
    assert "Waivers" in page and "ghost numeral" in page and FUTURE in page and "<b>waived</b>" in page


def session_with(tmp_path, names):
    session = Session(workspace=tmp_path)
    for name in names:
        p = Project(400, 300, "white", workspace=tmp_path)
        p.apply([{"type": "text", "name": "title", "text": "Hi", "x": 20, "y": 20, "size": 40, "color": "black"},
                 {"type": "shape", "name": "bar", "shape": "rectangle", "x": -20, "y": 200, "width": 100,
                  "height": 20, "fill": "#333333"}])
        p.save(tmp_path / name)
    return session


def test_same_document_passes_draft_and_fails_final_on_a_review_finding(tmp_path):
    session_with(tmp_path, ["a.vixl"])
    p = Project.load(tmp_path / "a.vixl")
    p._workspace = str(tmp_path)
    p.apply({"type": "waiver", "check": "fonts", "reason": "proofing font until the brand fonts arrive"})
    plain = p.check()
    assert plain["passed"] and any(x["action"] == "review" for x in plain["issues"])
    draft, final = p.check(profile="draft"), p.check(profile="final")
    assert draft["passed"] and draft["profile"]["name"] == "draft" and draft["profile"]["fail_on"] == "error"
    assert not final["passed"] and final["profile"]["fail_on"] == "review" and final["profile"]["failing"]
    assert "color_vision" in final["checked"]["checks"]
    # A waiver accepts the bar's crop; the final profile then passes.
    p.apply({"type": "waiver", "check": "bounds", "target": "bar", "reason": "bar bleeds on purpose"})
    assert p.check(profile="final")["passed"]
    with pytest.raises(VixlError, match="Unknown check profile"):
        p.check(profile="ship-it")


def test_workspace_and_group_profiles_override_the_built_in_ones(tmp_path):
    session = session_with(tmp_path, ["a.vixl", "b.vixl"])
    (tmp_path / ".vixl-checks.json").write_text(json.dumps(
        {"profiles": {"final": {"fail_on": "error"}, "strict": {"fail_on": "warning", "checks": ["bounds"]}}}))
    p = Project.load(tmp_path / "a.vixl")
    p._workspace = str(tmp_path)
    report = p.check(profile="final")
    assert report["passed"] and report["profile"]["source"] == "workspace"
    assert "color_vision" in report["checked"]["checks"]  # fields the workspace leaves out stay built-in
    strict = p.check(profile="strict")
    assert not strict["passed"] and strict["checked"]["checks"] == ["bounds"]
    dispatch(session, "group-define", {"name": "covers", "documents": ["a.vixl", "b.vixl"],
                                       "profiles": {"final": {"fail_on": "review"}},
                                       "shared": {"waivers": [{"check": "fonts", "reason": "proofing font for now"}]}})
    # A dry run reports each member against the group's final profile; publishing refuses.
    preview = dispatch(session, "group-apply", {"name": "covers", "profile": "final"})
    assert not preview["passed"] and preview["outcome"]["validation"] == "failed"
    assert preview["documents"][0]["checks"][-1]["profile"]["fail_on"] == "review"
    with pytest.raises(VixlError, match="Group checks failed"):
        dispatch(session, "group-apply", {"name": "covers", "profile": "final", "dry_run": False})
    dispatch(session, "group-apply", {"name": "covers", "profile": "draft", "dry_run": False})
    shown = dispatch(session, "group-show", {"name": "covers"})
    assert shown["profiles"]["final"]["fail_on"] == "review"
    assert shown["waivers"]["a.vixl"]["active"][0]["reason"] == "proofing font for now"
    with pytest.raises(VixlError, match="fail_on"):
        dispatch(session, "group-define", {"name": "bad", "documents": ["a.vixl"],
                                           "profiles": {"x": {"fail_on": "sometimes"}}})


def test_check_command_line_profile(tmp_path):
    session_with(tmp_path, ["a.vixl"])
    from vixl.cli import main

    path = str(tmp_path / "a.vixl")
    assert main(["-p", path, "check", "--profile", "draft", "--strict"]) == 0
    assert main(["-p", path, "check", "--profile", "final", "--strict"]) != 0


def test_check_all_fails_at_the_profile_level_and_review():
    from vixl.workspace_checks import failing

    record = {"issues": [{"check": "bounds", "severity": "warning", "action": "review", "message": "bar is cut off"},
                         {"check": "contrast", "severity": "info", "action": "informational", "message": "faint",
                          "waived": {"scope": "layer", "reason": "on purpose"}}],
              "profile": {"name": "final"},
              "suites": {"brief": {"status": "failed", "rules": [{"id": "size", "status": "failed"}]},
                         "copy": {"status": "needs_review", "rules": [{"id": "tone", "status": "needs_review"}]}}}
    assert failing(record, "review") == ["bounds: bar is cut off", "suite brief: failed (size)",
                                         "suite copy: needs_review (tone)"]
    # Under a profile a suite that needs review fails only at warning and review, as vixl check --profile does.
    assert failing(record, "fix") == ["suite brief: failed (size)"]


def test_check_all_profile_sets_the_level_and_the_ci_script_passes_it(tmp_path, monkeypatch):
    import importlib.util

    session_with(tmp_path, ["a.vixl"])
    session = Session(workspace=tmp_path)
    draft = dispatch(session, "check-all", {"profile": "draft", "history": False})
    final = dispatch(session, "check-all", {"profile": "final", "history": False})
    assert draft["passed"] and draft["fail_on"] == "error" and draft["profile"]["name"] == "draft"
    assert not final["passed"] and final["fail_on"] == "review"
    assert dispatch(session, "check-all", {"profile": "final", "fail_on": "error", "history": False})["passed"]
    spec = importlib.util.spec_from_file_location("check_documents",
                                                  Path(__file__).parents[1] / "scripts/check_documents.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    assert module.main(["--paths", "a.vixl", "--profile", "draft"]) == 0
    assert module.main(["--paths", "a.vixl", "--profile", "final"]) == 1


def test_production_variants_must_pass_the_profile(tmp_path):
    session_with(tmp_path, ["a.vixl"])
    session = Session(workspace=tmp_path)
    session.open("a.vixl")
    final = dispatch(session, "run", {"spec": {"rows": [{}], "profile": "final"}, "output": "out-final"})
    draft = dispatch(session, "run", {"spec": {"rows": [{}], "profile": "draft"}, "output": "out-draft"})
    assert final["profile"] == "final" and final["results"][0]["status"] == "needs_review"
    assert draft["results"][0]["status"] in ("completed", "reused")


def brand(workspace, **extra):
    kit = {"name": "Flames", "palette": {"background": "#efe6d2", "accent": "#d4241c", "ink": "#b51d16"}, **extra}
    (workspace / "brand.json").write_text(json.dumps(kit))


def cover(workspace, size):
    p = Project(1200, 800, "#efe6d2", workspace=workspace)
    p.apply({"type": "text", "name": "title", "text": "FIRE", "x": 40, "y": 100, "size": size, "color": "#d4241c"})
    return p


def test_brand_contrast_floor_has_a_large_text_tier(tmp_path):
    brand(tmp_path, minimum_contrast={"text": 4.5, "large_text": 3.0, "large_text_px": 24})
    assert not contrast(cover(tmp_path, 200).check(checks=["contrast"]))
    small = contrast(cover(tmp_path, 16).check(checks=["contrast"]))
    assert small and small[0]["required"] == 4.5
    # A caller cannot go below the brand floor; a higher request raises both tiers.
    assert contrast(cover(tmp_path, 200).check(checks=["contrast"], min_contrast=5))[0]["required"] == 5
    assert contrast(cover(tmp_path, 16).check(checks=["contrast"], min_contrast=2))[0]["required"] == 4.5


def test_brand_contrast_bare_number_still_applies_to_every_size(tmp_path):
    brand(tmp_path, minimum_contrast=4.5)
    assert contrast(cover(tmp_path, 200).check(checks=["contrast"]))[0]["required"] == 4.5


def test_brand_large_text_threshold_is_configurable(tmp_path):
    brand(tmp_path, minimum_contrast={"text": 4.5, "large_text": 3.0, "large_text_px": 400})
    assert contrast(cover(tmp_path, 200).check(checks=["contrast"]))[0]["required"] == 4.5


@pytest.mark.parametrize("value", [{"large_text": 3}, {"text": 30}, {"text": 4.5, "huge": 1}, "4.5"])
def test_brand_contrast_floor_is_validated(tmp_path, value):
    from vixl.brand import load

    brand(tmp_path, minimum_contrast=value)
    with pytest.raises(VixlError, match="minimum_contrast"):
        load(tmp_path)


def test_brand_contrast_tiers_reach_the_color_vision_check():
    from vixl.brand import contrast_floor, required_contrast

    floor = contrast_floor({"minimum_contrast": {"text": 7, "large_text": 4.5}})
    assert required_contrast(floor, 30) == 4.5 and required_contrast(floor, 20) == 7
    assert required_contrast(floor, 20, bold=True) == 4.5
    assert contrast_floor({}, None)["text"] == 4.5 and contrast_floor({}, None)["large_text"] == 3.0


def test_translucent_layer_style_shadows_are_not_off_brand(tmp_path):
    # #528: a 40% black drop shadow darkens what is under it; it is not a new ink.
    brand(tmp_path)
    p = Project(600, 600, "#efe6d2", workspace=tmp_path)
    p.apply([{"type": "text", "name": "a", "text": "HELLO", "x": 50, "y": 200, "size": 120, "color": "#d4241c"},
             {"type": "layer-style", "target": "a", "name": "drop-shadow",
              "settings": {"color": "#00000066", "dx": 10, "dy": 12, "blur": 0}},
             {"type": "shape", "name": "tint", "shape": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100,
              "fill": "#d4241c80"}])
    assert not p.check(checks=["brand"])["issues"]
    p.apply({"type": "layer-style", "target": "a", "name": "outer-glow", "settings": {"color": "#00ff0066"}})
    found = p.check(checks=["brand"])["issues"]
    assert found and found[0]["layers"] == ["a"] and found[0]["color"] == "#00ff0066"


def test_check_all_applies_waivers_and_outcome_accepts_them(tmp_path):
    from vixl.workspace_checks import markdown

    p = ghost(tmp_path)
    p.apply({"type": "waiver", "check": "contrast", "target": "ghost", "reason": "ghost numeral", "expires": FUTURE})
    report = p.check(checks=["contrast"])
    assert report["outcome"]["state"] == "validated"
    assert report["outcome"]["accepted"][0]["reason"] == "ghost numeral" and report["outcome"]["accepted"][0]["waived"]
    p.save(tmp_path / "a.vixl")
    session = Session(workspace=tmp_path)
    result = dispatch(session, "check-all", {"checks": ["contrast"], "history": False})
    entry = result["documents"][0]
    assert result["passed"] and entry["findings"][0]["waived"]["reason"] == "ghost numeral"
    assert entry["waivers"]["active"][0]["matched"] == 1 and "ghost numeral" in markdown(result)
    assert not dispatch(session, "check-all", {"checks": ["contrast"], "history": False, "waivers": False})["passed"]
