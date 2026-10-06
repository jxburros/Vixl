"""The generated operation schema: no shared constant is mutated, descriptions stay with their field,
and closed vocabularies (easings, presets, anchors, patterns) are listed."""

from collections import defaultdict

import jsonschema
import pytest

from vixl import Project, VixlError, schema as schema_module
from vixl.geometry import ANCHORS, canonical_anchor
from vixl.timeline import EASINGS, NAMED_BEZIER, PRESETS


def variants():
    return {v["properties"]["type"]["const"]: v for v in schema_module.operation_schema()["properties"]["operations"]["items"]["oneOf"]}


def test_shared_schema_constants_carry_no_description():
    variants()
    for constant in (schema_module.S, schema_module.N, schema_module.B, schema_module.POSITIVE_INT):
        assert "description" not in constant
    assert schema_module.S == {"type": "string"} and schema_module.N == {"type": "number"}


def walk(node, kind, found):
    if isinstance(node, dict):
        for name, prop in (node.get("properties") or {}).items():
            if isinstance(prop, dict) and "description" in prop:
                found[prop["description"]].add((kind, name))
        for value in node.values():
            walk(value, kind, found)
    elif isinstance(node, list):
        for value in node:
            walk(value, kind, found)


def test_no_description_leaks_between_unrelated_fields():
    found = defaultdict(set)
    for kind, variant in variants().items():
        walk(variant, kind, found)
    for text, uses in found.items():
        names = {name for _, name in uses}
        # Legitimately shared: coordinates, targets, arrow points, frame references, shape-specific fallbacks.
        if len(names) > 5 or (len(names) > 2 and not text.startswith(("Pixels", "Stable", "Arrow", "A frame", "Shape-specific"))):
            pytest.fail(f"{text!r} is attached to unrelated fields {sorted(names)}")
    for text in ("Reference layer name or ID.", "Dash offset."):
        assert {n for _, n in found.get(text, ())} <= {"to", "dash_offset"}


def test_fields_named_in_the_issue_have_their_own_descriptions():
    v = variants()

    def desc(kind, field):
        return v[kind]["properties"][field].get("description", "")

    assert "Dash offset" not in str(v["gradient"]["properties"]["angle"])
    assert "Degrees" in desc("gradient", "angle")
    assert "color" in desc("gradient", "start").lower() and "color" in desc("gradient", "end").lower()
    assert "Reference layer" not in desc("gradient", "name")
    assert "color" in desc("shape", "fill").lower() and "color" in desc("shape", "stroke").lower()
    assert "SVG" in desc("shape", "path")
    assert "color" in desc("text", "color").lower() and "Reference layer" not in desc("text", "text")
    for kind in ("shape", "text", "character", "particles", "motion"):
        for field in ("x", "y", "period", "amount", "frequency", "damping", "gravity", "angle"):
            prop = v[kind]["properties"].get(field)
            assert prop is None or "Dash offset" not in prop.get("description", ""), (kind, field)
    for kind, field in (("pivot", "clear"), ("motion", "children"), ("motion", "extend"), ("cut-paper", "children"), ("cut-paper", "clear")):
        assert "Shape-specific" not in v[kind]["properties"][field].get("description", "")
    for kind in ("keyframe", "animate", "animate-preset"):
        assert "Reference layer" not in str(v[kind]["properties"]["easing"])


def test_easings_presets_anchors_and_patterns_are_listed():
    v = variants()
    for kind in ("keyframe", "animate", "animate-preset"):
        easing = v[kind]["properties"]["easing"]
        names = easing["anyOf"][0]["enum"]
        assert {"hold", "spring", "bounce-out", "elastic-out", "ease-in-out-back", *NAMED_BEZIER} <= set(names)
        assert {e for e in EASINGS if "(" not in e} <= set(names)
        assert any("cubic-bezier" in str(b) for b in easing["anyOf"]) and any("steps" in str(b) for b in easing["anyOf"])
        jsonschema.Draft202012Validator(v[kind]).is_valid({"type": kind, "easing": "steps(4)"})
    assert v["animate-preset"]["properties"]["preset"]["enum"] == list(PRESETS)
    assert list(ANCHORS) == v["pivot"]["properties"]["value"]["anyOf"][1]["enum"]
    assert "stripes" in v["pattern-fill"]["properties"]["pattern"]["examples"]


def test_pivot_accepts_anchor_synonyms_and_reports_them():
    p = Project(200, 200, "white")
    p.apply({"type": "solid", "name": "box", "width": 40, "height": 40, "color": "red"})
    for synonym, canonical in (("bottom-center", "bottom"), ("top-center", "top"), ("center-left", "left"), ("middle-right", "right"), ("Top_Center", "top")):
        assert canonical_anchor(synonym) == canonical
        result = p.apply({"type": "pivot", "target": "box", "value": synonym})
        assert p.layer("box")["pivot"] == list(ANCHORS[canonical])
        assert any(synonym in note for note in result["normalized"]), result
    with pytest.raises(VixlError, match="Unknown pivot anchor"):
        p.apply({"type": "pivot", "target": "box", "value": "nowhere"})


def test_keyframe_easing_is_case_insensitive_and_keyframe_text_states_semantics():
    p = Project(200, 200, "white")
    p.apply({"type": "solid", "name": "box", "width": 40, "height": 40, "color": "red"})
    result = p.apply({"type": "keyframe", "target": "box", "property": "opacity", "time": 0, "value": 0, "easing": "Ease-Out"})
    assert any("easing" in note for note in result["normalized"])
    v = variants()
    text = v["keyframe"]["properties"]["easing"]["description"] + v["keyframe"]["properties"]["extend"]["description"]
    assert "STARTS at this key" in text and "extends the timeline" in text and "holds" in text
