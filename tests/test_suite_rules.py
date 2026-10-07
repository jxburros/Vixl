"""Measured check-suite rules (spacing, relation, contrast, color, ink, balance, hierarchy, count, focal),
the starter suites, suites=… on apply, and the testing guidance that tells an agent to use them."""

import asyncio
import json

import pytest

from vixl import Project
from vixl.assurance import RULE_FIELDS, validate_suite
from vixl.briefs import KINDS, TESTS, guide
from vixl.capabilities import lookup
from vixl.checks import apply_reviewed
from vixl.effect_workflows import SUITES
from vixl.errors import VixlError
from vixl.interfaces import mcp_server


def document():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "solid", "name": "bg", "color": "#fafafa"},
        {"type": "text", "name": "title", "text": "Big Title", "size": 48, "x": 40, "y": 40, "color": "#111111"},
        {"type": "text", "name": "sub", "text": "Subtitle", "size": 24, "x": 40, "y": 110, "color": "#999999"},
        {"type": "shape", "name": "a", "shape": "rectangle", "width": 40, "height": 40, "fill": "red", "x": 40, "y": 200},
        {"type": "shape", "name": "b", "shape": "rectangle", "width": 40, "height": 40, "fill": "red", "x": 100, "y": 200},
        {"type": "shape", "name": "c", "shape": "rectangle", "width": 40, "height": 40, "fill": "red", "x": 170, "y": 200},
    ])
    return p


def statuses(project, rules):
    report = project.check_suite({"rules": rules})
    return {item["id"]: item for item in report["results"]}


def test_measured_rules_pass_and_fail_on_what_they_measure():
    p = document()
    found = statuses(p, [
        {"id": "even", "kind": "spacing", "targets": ["a", "b", "c"], "axis": "horizontal"},
        {"id": "even-ab", "kind": "spacing", "targets": ["a", "b"], "axis": "horizontal", "expected": 20},
        {"id": "above", "kind": "relation", "target": "title", "to": "sub", "position": "above", "align": ["left"],
         "minimum": 8},
        {"id": "centred", "kind": "relation", "target": "title", "to": "sub", "align": ["center-x"]},
        {"id": "margin", "kind": "relation", "target": "title", "to": "canvas", "position": "inside", "minimum": 32},
        {"id": "wide-margin", "kind": "relation", "target": "title", "to": "canvas", "position": "inside", "minimum": 60},
        {"id": "apart", "kind": "relation", "target": "a", "to": "b", "position": "apart"},
        {"id": "dark", "kind": "contrast", "target": "title"},
        {"id": "grey", "kind": "contrast", "target": "sub", "minimum": 4.5},
        {"id": "red", "kind": "color", "point": [60, 220], "expected": "red"},
        {"id": "not-blue", "kind": "color", "region": [40, 200, 40, 40], "expected": "blue"},
        {"id": "quiet", "kind": "ink", "region": [300, 0, 100, 300], "maximum": 0.01},
        {"id": "busy", "kind": "ink", "region": [40, 200, 40, 40], "minimum": 0.9},
        {"id": "left-heavy", "kind": "balance", "tolerance": 0.1},
        {"id": "left-ok", "kind": "balance", "expected": [0.3, 0.55], "tolerance": 0.05},
        {"id": "steps", "kind": "hierarchy", "targets": ["title", "sub"], "ratio": 1.5},
        {"id": "steep", "kind": "hierarchy", "targets": ["title", "sub"], "ratio": 3},
        {"id": "three", "kind": "count", "target": "?", "layer_type": "shape", "minimum": 3, "maximum": 3},
        {"id": "no-text", "kind": "count", "target": "*", "layer_type": "text", "maximum": 0},
        {"id": "thirds", "kind": "focal", "target": "title", "grid": "thirds"},
        {"id": "thirds-loose", "kind": "focal", "target": "title", "grid": "thirds", "tolerance": 40},
    ])
    expected = {"even": "failed", "even-ab": "passed", "above": "passed", "centred": "failed", "margin": "passed",
                "wide-margin": "failed", "apart": "passed", "dark": "passed", "grey": "failed", "red": "passed",
                "not-blue": "failed", "quiet": "passed", "busy": "passed", "left-heavy": "failed", "left-ok": "passed",
                "steps": "passed", "steep": "failed", "three": "passed", "no-text": "failed", "thirds": "failed",
                "thirds-loose": "passed"}
    assert {key: found[key]["status"] for key in expected} == expected
    # Each result carries the measurement, so a failure says what to change.
    assert found["even"]["gaps"] == [20, 30]
    assert found["grey"]["actual"] < 4.5 and len(found["grey"]["weakest_region"]) == 4
    assert found["wide-margin"]["margins"]["left"] == 40
    assert found["centred"]["missing_alignments"] == ["center-x"]
    assert found["not-blue"]["actual"] == "#ff0000"
    assert found["left-heavy"]["center"][0] < 0.4
    assert found["three"]["layers"] == ["a", "b", "c"]


def test_ink_and_balance_ignore_the_backdrop_unless_a_background_colour_is_given():
    p = document()
    found = statuses(p, [
        {"id": "content", "kind": "ink", "maximum": 0.2},
        {"id": "against-white", "kind": "ink", "background": "white", "tolerance": 2, "minimum": 0.9},
    ])
    # The full-canvas #fafafa solid is a backdrop, not content; against white it differs everywhere.
    assert found["content"]["status"] == "passed" and found["content"]["ink_fraction"] < 0.2
    assert found["against-white"]["status"] == "passed"


def test_missing_layers_need_review_and_malformed_rules_are_refused():
    p = document()
    found = statuses(p, [{"id": "ghost", "kind": "contrast", "target": "nope"}])
    assert found["ghost"]["status"] == "needs_review"
    for rule in (
        {"id": "x", "kind": "relation", "target": "a", "to": "b"},
        {"id": "x", "kind": "relation", "target": "a", "to": "b", "position": "near"},
        {"id": "x", "kind": "relation", "target": "a", "to": "b", "align": ["middle"]},
        {"id": "x", "kind": "spacing", "targets": ["a"]},
        {"id": "x", "kind": "color", "expected": "red"},
        {"id": "x", "kind": "color", "point": [1, 1], "region": [0, 0, 2, 2], "expected": "red"},
        {"id": "x", "kind": "ink"},
        {"id": "x", "kind": "count", "target": "*"},
        {"id": "x", "kind": "balance", "expected": [2, 0.5]},
        {"id": "x", "kind": "focal", "target": "a", "grid": "fifths"},
        {"id": "x", "kind": "hierarchy", "targets": ["a", "b"], "colour": "red"},
    ):
        with pytest.raises(VixlError):
            validate_suite({"rules": [rule]})


def test_rules_hold_over_sampled_animation_times():
    p = document()
    p.apply([{"type": "keyframe", "target": "a", "property": "x", "time": 0, "value": 40},
             {"type": "keyframe", "target": "a", "property": "x", "time": 1000, "value": 380}])
    report = p.check_suite({"sampling": {"mode": "times", "times": [0, 1000]}, "rules": [
        {"id": "a-inside", "kind": "relation", "target": "a", "to": "canvas", "position": "inside"}]})
    assert [item["status"] for item in report["results"]] == ["passed", "failed"]


def test_starter_suites_validate_and_run_without_errors_of_their_own():
    p = document()
    for name, suite in SUITES.items():
        validate_suite(suite)
        if name in ("containers", "palette", "slide-deck"):
            continue  # These need a modular template, an applied palette or pages to measure.
        report = p.check_suite(suite)
        broken = [item for item in report["results"] if item["status"] == "needs_review" and "message" in item]
        assert not broken, (name, broken)


def test_apply_runs_attached_suites_with_the_batch():
    p = document()
    result, _ = apply_reviewed(p, [{"type": "suite-set", "name": "brief", "suite": {"rules": [
        {"id": "sub-reads", "kind": "contrast", "target": "sub", "minimum": 4.5},
        {"id": "steps", "kind": "hierarchy", "targets": ["title", "sub"], "ratio": 1.5}]}}], suites=True)
    brief = result["suites"]["brief"]
    assert brief["status"] == "failed" and [item["id"] for item in brief["not_passed"]] == ["sub-reads"]
    result, _ = apply_reviewed(p, [{"type": "text-set", "target": "sub", "color": "#333333"}], suites="brief")
    assert result["suites"]["brief"]["status"] == "passed" and result["suites"]["brief"]["not_passed"] == []
    with pytest.raises(VixlError, match="No attached suite"):
        apply_reviewed(p, [{"type": "move", "target": "a", "x": 41}], suites=["missing"])
    bare, _ = apply_reviewed(Project(10, 10), [{"type": "solid", "color": "red"}], suites=True)
    assert "suite-set" in bare["suites"]["note"]


def test_mcp_apply_takes_suites(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def call(name, arguments):
        result = await server.call_tool(name, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads("".join(getattr(item, "text", "") for item in content))

    asyncio.run(call("vixl_document_create", {"path": "a.vixl", "width": 200, "height": 100}))
    result = asyncio.run(call("vixl_operations_apply", {"suites": True, "operations": [
        {"type": "shape", "name": "dot", "shape": "ellipse", "width": 20, "height": 20, "x": 0, "y": 0, "fill": "red"},
        {"type": "suite-set", "name": "brief", "suite": {"rules": [
            {"id": "centred", "kind": "balance", "tolerance": 0.1}]}}]}))
    assert result["suites"]["brief"]["status"] == "failed"


def test_guide_gives_every_kind_a_test_plan_and_a_testing_guidance():
    assert set(TESTS) == set(KINDS)
    for kind in KINDS:
        plan = guide(kind)["tests"]
        assert plan["starter_suite"] in SUITES
        validate_suite({"rules": plan["rules_to_adapt"]})
    text = guide("testing")["text"]
    for word in ("Why", "When", "preview", "suite-set", "hierarchy", "relation", "never loosen"):
        assert word in text
    assert any("Preview after tests pass" in step for step in guide()["start_here"])
    found = lookup("testing")
    assert set(found["suite_rules"]) == set(RULE_FIELDS) and "testing" in found["guidance"]
    assert "suite-set" in found["operations"] and "check" in found["workflows"]
