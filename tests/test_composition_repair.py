"""repair-layout for composition findings (craft plan 2b): one synthetic document per finding kind, repaired
with the finding gone and nothing new, plus dry runs, protected layers and what is not auto-repairable."""

import pytest

from vixl import Project
from vixl.plugins.layout_repair.layout_repair import repair_layout

from test_composition import HIERARCHY, card, doc, scatter, text

CHECKS = ["bounds", "overlap", "safe_area", "composition"]


def findings(p, checks=CHECKS):
    """Every fix and review finding, by rule and layers."""
    return {(x["rule"], tuple(x.get("layer_ids") or ())) for x in p.check(checks=checks)["issues"]
            if x["action"] in ("fix", "review")}


def codes(p):
    return sorted(x["code"] for x in p.check(checks=["composition"])["issues"]
                  if x["check"] == "composition" and x["code"] not in HIERARCHY)


def repaired(p, code, checks=CHECKS, **options):
    """Repair ``p`` in place; the composition finding ``code`` is gone and no finding is new."""
    assert code in codes(p)
    before = findings(p, checks)
    result = repair_layout(p, checks=checks, dry_run=False, **options)
    assert result["feasible"] and result["committed"], result
    assert code not in codes(p)
    assert findings(p, checks) <= before
    (chosen,) = [x for x in result["selected"] if x["rule"] == f"composition.{code}"]
    return result, chosen


def test_margin_drift_snaps_the_stray_edge_to_the_margin():
    p = doc(text("title", 60, 60), text("subtitle", 72, 100))
    _, chosen = repaired(p, "margin_drift")
    assert chosen["candidate"] == "snap-to-margin"
    assert p.layer("subtitle")["x"] == 60 and p.layer("title")["x"] == 60


def test_margin_drift_moves_the_chip_with_its_text():
    chip = {"type": "shape", "name": "pill", "shape": "rectangle", "x": 70, "y": 52, "width": 96, "height": 40,
            "fill": "#ffcc00"}
    p = doc(chip, text("date", 82, 60), text("headline", 60, 140, size=48), text("subtitle", 60, 220))
    repaired(p, "margin_drift")
    assert (p.layer("pill")["x"], p.layer("date")["x"]) == (60, 72)


def test_uneven_rhythm_moves_the_middle_line_to_its_group():
    p = doc(text("first", 100, 100, 80), text("last", 100, 222, 60), text("company", 100, 280, 30))
    _, chosen = repaired(p, "uneven_rhythm")
    assert [op["target"] for op in chosen["operations"]] == [p.layer("last")["id"]]
    assert p.layer("company")["y"] == 280


def test_crowding_opens_the_gap_under_a_rule():
    p = doc(text("heading", 100, 100, 40),
            {"type": "shape", "name": "rule", "shape": "rectangle", "x": 100, "y": 150, "width": 600, "height": 4,
             "fill": "#cc8800"},
            text("item", 100, 156, 24))
    _, chosen = repaired(p, "crowding")
    rule, item = p.layer("rule"), p.layer("item")
    assert item["y"] - (rule["y"] + rule["height"]) >= 5  # half a spacing unit of 10 px


def test_dead_band_is_spread_over_the_other_gaps():
    p = doc(*card("a", 50), *card("b", 230), *card("c", 410), *card("d", 800))
    _, chosen = repaired(p, "dead_band")
    assert chosen["candidate"] == "spread-into-gaps"
    assert p.layer("a")["y"] == 50 and p.layer("d")["y"] == 800  # the first and last rows stay
    gaps = [p.layer(b)["y"] - p.layer(a)["y"] - 150 for a, b in (("a", "b"), ("b", "c"), ("c", "d"))]
    assert max(gaps) - min(gaps) <= 2


def clumped_tile():
    p = Project(1024, 1024, "white")
    p.apply([{"type": "type-scale", "base": 20},
             {"type": "shape", "name": "m", "shape": "ellipse", "x": 0, "y": 0, "width": 60, "height": 60,
              "fill": "#123456"},
             {"type": "pattern-scatter", "name": "tile", "source": ["m"], "width": 1024, "height": 1024, "count": 16,
              "seed": 3}])
    copies = [x for x in p.state["layers"] if x.get("parent") == p.layer("tile")["id"]]
    p.apply([{"type": "move", "target": x["id"], "x": 20 + 70 * (i % 4), "y": 20 + 70 * (i // 4)}
             for i, x in enumerate(copies)])
    return p


def test_clumped_pattern_scatter_is_rebuilt_from_its_recipe():
    p = clumped_tile()
    # A seamless tile wraps copies across its edges, so the safe area is not one of its checks.
    _, chosen = repaired(p, "clumped_scatter", checks=["bounds", "overlap", "composition"])
    assert chosen["operations"][0]["type"] == "pattern-scatter"
    assert set(chosen["operations"][0]) & {"thin", "seed"}


def test_a_scatter_without_a_recipe_is_not_auto_repairable():
    p = scatter([(20 + 70 * (i % 4), 20 + 70 * (i // 4)) for i in range(16)])
    result = repair_layout(p, checks=CHECKS, dry_run=False)
    assert result["feasible"] and not result["committed"] and not result["selected"]
    (left,) = result["reviews_remaining"]
    assert left["rule"] == "composition.clumped_scatter" and left["reason"].startswith("not auto-repairable")
    assert codes(p) == ["clumped_scatter"]


def test_dry_run_plans_without_changing_the_document():
    p = doc(text("title", 60, 60), text("subtitle", 72, 100))
    state = p.state["layers"]
    plan = repair_layout(p, checks=CHECKS)
    assert plan["dry_run"] and not plan["committed"] and p.state["layers"] == state
    assert plan["operations"] == [{"type": "move", "target": p.layer("subtitle")["id"], "x": -12, "y": 0,
                                   "relative": True}]
    assert {"rule": "composition.margin_drift", "layers": ["subtitle", "title"]} in plan["initial"]
    again = repair_layout(p, checks=CHECKS)
    assert (again["selected"], again["attempts"]) == (plan["selected"], plan["attempts"])  # the same plan
    p.apply(plan["operations"])
    assert codes(p) == []


def test_protected_layers_and_checks_without_composition():
    p = doc(text("title", 60, 60), text("subtitle", 72, 100))
    result = repair_layout(p, checks=CHECKS, protected=["subtitle"], dry_run=False)
    assert result["selected"][0]["candidate"] == "move-margin-to-edge" and p.layer("title")["x"] == 72
    q = doc(text("title", 60, 60), text("subtitle", 72, 100))
    plain = repair_layout(q, checks=["bounds", "overlap"], dry_run=False)
    assert not plain["selected"] and "reviews_remaining" not in plain and codes(q) == ["margin_drift"]


def test_composition_repair_never_adds_a_failure():
    from vixl.spatial import canvas_boxes

    p = doc(text("title", 100, 60), text("body", 100, 140), text("subtitle", 88, 100))
    ink = canvas_boxes(p, "ink")[p.layer("subtitle")["id"]]
    # A mark just right of the stray: snapping it to the margin would run the text into the mark.
    p.apply({"type": "shape", "name": "mark", "shape": "rectangle", "x": round(ink[0] + ink[2] + 4), "y": 100,
             "width": 40, "height": 24, "fill": "#222222"})
    result, chosen = repaired(p, "margin_drift")
    (snap,) = [a for a in result["attempts"] if a["candidate"] == "snap-to-margin"]
    assert snap["result"] == "rejected" and snap["reason"] == "it introduces overlap.text-object"
    assert chosen["candidate"] == "move-margin-to-edge"
    assert p.layer("title")["x"] == p.layer("body")["x"] == p.layer("subtitle")["x"] == 88


@pytest.mark.parametrize("dry_run", [True, False])
def test_workflow_repair_layout_repairs_composition(tmp_path, dry_run):
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    doc(text("title", 60, 60), text("subtitle", 72, 100)).save(tmp_path / "a.vixl")
    session = Session(tmp_path / "a.vixl")
    result = dispatch(session, "repair-layout", {"checks": CHECKS, "dry_run": dry_run})
    assert result["selected"][0]["rule"] == "composition.margin_drift" and result["committed"] is not dry_run
    assert (Project.load(tmp_path / "a.vixl").layer("subtitle")["x"] == 72) is dry_run
