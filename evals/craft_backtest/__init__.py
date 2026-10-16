"""Craft backtest: the composition check family against the defects the judges named in round 1.

Every builder in ``builders/`` recreates one round-1 Vixl document (see the README for how faithfully);
``manifest.json`` lists the judges' defects per test, the composition ones as expected findings with the region
they concern. ``run()`` builds every document, runs ``check --checks composition`` and scores each finding:

* **caught**: an expected defect with at least one finding of one of its codes whose region meets the defect's;
* **missed**: an expected defect with no such finding;
* **false**: a finding that meets no expected defect and no judged defect outside composition;
* **elsewhere**: a finding that lands on a defect the judges named but that is not a composition matter (it is
  real, so not counted as false, but not a catch either).

    python -m evals.craft_backtest           # the table
    python -m evals.craft_backtest --json    # the same as JSON
"""

import importlib
import json
from pathlib import Path

HERE = Path(__file__).parent
CODES = ("dead_band", "margin_drift", "uneven_rhythm", "crowding", "clumped_scatter")


def manifest():
    return json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))


def documents():
    """``{name: Project}`` for every backtest document, built fresh."""
    from .builders import TESTS

    built = {}
    for test in TESTS:
        built.update(importlib.import_module(f"{__name__}.builders.{test}").build())
    return built


def _meets(a, b):
    return (min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0])
            and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1]))


def run():
    """Score the composition family on the backtest set: totals per code and every finding and defect."""
    data = manifest()
    built = documents()
    findings = []
    for name, project in built.items():
        report = project.check(checks=["composition"], waivers=False)
        for item in report["issues"]:
            if item["check"] == "composition":
                findings.append({"document": name, "code": item["code"], "region": item["region"],
                                 "layers": item["layers"], "message": item["message"]})
    expected = [{**defect, "test": test} for test, entry in data["tests"].items() for defect in entry["expected"]]
    other = [{**defect, "test": test} for test, entry in data["tests"].items() for defect in entry["out_of_scope"]
             if defect.get("region")]
    missing = sorted({d["document"] for d in expected + other} - set(built))
    if missing:
        raise ValueError(f"manifest names documents no builder makes: {missing}")
    for defect in expected:
        defect["found_by"] = [i for i, f in enumerate(findings) if f["document"] == defect["document"]
                              and f["code"] in defect["codes"] and _meets(f["region"], defect["region"])]
    for i, finding in enumerate(findings):
        if any(i in d["found_by"] for d in expected):
            finding["verdict"] = "true"
        elif any(d["document"] == finding["document"] and _meets(finding["region"], d["region"]) for d in other):
            finding["verdict"] = "elsewhere"
        else:
            finding["verdict"] = "false"
    totals = {}
    for code in CODES:
        mine = [d for d in expected if d["codes"][0] == code]
        totals[code] = {
            "expected": len(mine),
            "caught": sum(1 for d in mine if d["found_by"]),
            "missed": sum(1 for d in mine if not d["found_by"]),
            "findings": sum(1 for f in findings if f["code"] == code),
            "false": sum(1 for f in findings if f["code"] == code and f["verdict"] == "false"),
            "elsewhere": sum(1 for f in findings if f["code"] == code and f["verdict"] == "elsewhere"),
        }
    totals["all"] = {key: sum(totals[code][key] for code in CODES) for key in totals[CODES[0]]}
    return {"documents": len(built), "tests": len(data["tests"]), "totals": totals,
            "expected": [{key: d[key] for key in ("id", "test", "document", "codes", "what")}
                         | {"caught": bool(d["found_by"])} for d in expected],
            "findings": findings,
            "out_of_scope": sum(len(entry["out_of_scope"]) for entry in data["tests"].values())}


def table(result):
    lines = [f"Craft backtest: {result['documents']} documents from {result['tests']} round-1 tests, "
             f"{len(result['expected'])} composition defects expected, {result['out_of_scope']} judged defects "
             "outside composition", "",
             "| Kind | expected | caught | missed | findings | false | on other judged defects |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for code, row in result["totals"].items():
        lines.append(f"| {code} | {row['expected']} | {row['caught']} | {row['missed']} | {row['findings']} "
                     f"| {row['false']} | {row['elsewhere']} |")
    lines += ["", "Expected defects:"]
    for d in result["expected"]:
        lines.append(f"- [{'x' if d['caught'] else ' '}] {d['id']} ({'/'.join(d['codes'])}): {d['what']}")
    flagged = [f for f in result["findings"] if f["verdict"] != "true"]
    if flagged:
        lines += ["", "Findings that match no expected defect:"]
        for f in flagged:
            lines.append(f"- {f['verdict']}: {f['document']} {f['code']} at {f['region']}: {f['message'][:110]}")
    return "\n".join(lines) + "\n"


def _keys(report):
    """The fix and review findings of a check report, by rule and layers."""
    return {(item["rule"], tuple(item.get("layer_ids") or item.get("layers") or ()))
            for item in report["issues"] if item.get("action") in ("fix", "review")}


def repair(checks=None, max_iterations=20, max_candidates=200, time_budget=300):
    """Run ``repair-layout`` on every backtest document that has composition findings and count the findings it
    resolves while adding no fix or review finding of any check. ``checks`` defaults to vixl_check's default set,
    so bounds, overlap, safe area and the rest guard every repair."""
    from vixl.plugins.layout_repair.layout_repair import repair_layout

    verdicts = {(f["document"], f["code"], tuple(f["layers"])): f["verdict"] for f in run()["findings"]}
    rows, totals = [], {"findings": 0, "resolved": 0, "caught": 0, "caught_resolved": 0, "new": 0}
    for name, project in documents().items():
        before = project.check(checks=checks, waivers=False)
        targets = [item for item in before["issues"] if item["check"] == "composition"]
        if not targets:
            continue
        result = repair_layout(project, checks=checks, max_iterations=max_iterations, max_candidates=max_candidates,
                               time_budget=time_budget, dry_run=True)
        # The reconstructions keep failures repair cannot fix (text in the safe-area margin as the originals set
        # it), which leave the whole plan uncommitted; its composition repairs are applied here, in plan order.
        planned = [op for item in result["selected"] for op in item["operations"]]
        if planned:
            project.apply(planned)
        after = project.check(checks=checks, waivers=False)
        new = sorted(_keys(after) - _keys(before))
        gone = _keys(before) - _keys(after)
        for item in targets:
            key = (item["rule"], tuple(item.get("layer_ids") or ()))
            caught = verdicts.get((name, item["code"], tuple(item["layers"]))) == "true"
            resolved = key in gone and not new
            rows.append({"document": name, "code": item["code"], "layers": item["layers"][:4], "caught": caught,
                         "resolved": resolved,
                         "candidate": next((s["candidate"] for s in result["selected"] if s["rule"] == item["rule"]
                                            and s["layers"] == item["layers"]), None),
                         "reason": next((r["reason"] for r in result.get("reviews_remaining", [])
                                         if r["rule"] == item["rule"] and r["layers"] == item["layers"]), None)})
            totals["findings"] += 1
            totals["resolved"] += resolved
            totals["caught"] += caught
            totals["caught_resolved"] += caught and resolved
        totals["new"] += len(new)
    by_code = {code: {"findings": sum(1 for r in rows if r["code"] == code),
                      "resolved": sum(1 for r in rows if r["code"] == code and r["resolved"])} for code in CODES}
    return {"totals": totals, "by_code": by_code, "findings": rows}


def repair_table(result):
    t = result["totals"]
    lines = [f"repair-layout on the backtest: {t['resolved']} of {t['findings']} composition findings resolved "
             f"({t['caught_resolved']} of the {t['caught']} that catch a judged defect), {t['new']} new findings", "",
             "| Kind | findings | resolved |", "|---|---:|---:|"]
    for code, row in result["by_code"].items():
        lines.append(f"| {code} | {row['findings']} | {row['resolved']} |")
    lines += ["", "Findings:"]
    for r in result["findings"]:
        how = r["candidate"] or r["reason"] or "-"
        lines.append(f"- [{'x' if r['resolved'] else ' '}] {r['document']} {r['code']} {', '.join(r['layers'])}: {how}")
    return "\n".join(lines) + "\n"
