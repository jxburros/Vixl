"""The craft backtest (craft plan 1b): the composition family on reconstructions of the round-1 Vixl documents.

The numbers are pinned: a change that catches fewer of the judges' defects, or adds findings that match no
judged defect, fails here. When a change improves them, update the pins, the README table and the changelog."""

import json

from evals.craft_backtest import CODES, manifest, run, table

PINNED = {
    # code: (expected, caught, false findings)
    "dead_band": (10, 5, 0),
    "margin_drift": (5, 4, 0),
    "uneven_rhythm": (4, 2, 0),
    "crowding": (1, 1, 0),
    "clumped_scatter": (1, 0, 0),
}


def test_backtest_numbers_are_pinned():
    result = run()
    assert result["documents"] == 20 and result["tests"] == 16
    for code, (expected, caught, false) in PINNED.items():
        row = result["totals"][code]
        assert (row["expected"], row["caught"], row["false"]) == (expected, caught, false), (code, row)
        assert row["caught"] + row["missed"] == row["expected"]
    assert result["totals"]["all"]["caught"] == 12 and result["totals"]["all"]["false"] == 0
    text = table(result)
    assert "| all | 21 | 12 | 9 |" in text
    json.dumps(result)


def test_manifest_is_complete_and_honest():
    data = manifest()
    assert sorted(data["tests"]) == [f"T{i:02d}" for i in range(1, 17)]
    for test, entry in data["tests"].items():
        assert entry["lane_code"] and entry["documents"]
        for defect in entry["expected"]:
            assert set(defect["codes"]) <= set(CODES) and defect["judges"] and defect["what"]
            assert defect["document"] in entry["documents"] and len(defect["region"]) == 4
        for defect in entry["out_of_scope"]:
            assert defect["kind"] and defect["what"] and defect["judges"]


def test_repair_layout_resolves_composition_findings_on_the_backtest():
    """Craft plan 2b: repair-layout on every backtest document with composition findings (default checks)."""
    from evals.craft_backtest import repair, repair_table

    result = repair()
    totals = result["totals"]
    assert (totals["findings"], totals["resolved"], totals["caught"], totals["caught_resolved"]) == (22, 19, 20, 17)
    assert totals["new"] == 0
    assert {code: row["resolved"] for code, row in result["by_code"].items()} == {
        "dead_band": 3, "margin_drift": 9, "uneven_rhythm": 2, "crowding": 5, "clumped_scatter": 0}
    assert "19 of 22 composition findings resolved" in repair_table(result)
