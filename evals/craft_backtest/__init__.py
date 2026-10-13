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
