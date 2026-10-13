"""Combine the blind judges' forms into scores of record, disagreements and calibration.

    python evals/tool-comparison/rejudge-2026-10-12/analyze.py > analysis.json

Reads scores/<test>.<judge>.json (judges 1, 2 and 3; "human" for the calibration set),
sealed/key.csv and resolutions.json (how each flagged disagreement was settled). The score of record for each code is the median of the three judges.

The human calibration set is used for craft, its sub-scores and the pairwise calls only: fidelity and
revision are checkable facts, and the person scoring did not review them closely.
"""

import csv
import json
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
JUDGES = ("1", "2", "3")
CALIBRATED = ("craft",)
MAIN = ("fidelity", "craft", "revision")
SUBS = ("hierarchy", "spacing", "type", "colour", "finish", "motif")


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load():
    key = {}
    with open(HERE / "sealed" / "key.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key[(row["test"], row["code"])] = row["lane"].removeprefix("claude-")
    forms = {}
    for path in sorted((HERE / "scores").glob("T*.*.json")):
        test, judge = path.stem.split(".", 1)
        forms[(test, judge)] = json.loads(path.read_text(encoding="utf-8"))
    return key, forms


def analyse():
    key, forms = load()
    drops = {(r["test"], r["code"], r["field"]): set(r["drop"])
             for r in json.loads((HERE / "resolutions.json").read_text(encoding="utf-8"))}
    tests = sorted({t for t, _ in key})
    lanes, pairs, flags, calibration = [], [], [], []
    for test in tests:
        codes = sorted(c for t, c in key if t == test)
        for code in codes:
            row = {"test": test, "code": code, "lane": key[(test, code)], "by_judge": {}}
            for judge in JUDGES + ("human",):
                form = forms.get((test, judge))
                if not form:
                    continue
                entry = form["lanes"][code]
                row["by_judge"][judge] = {k: number(entry.get(k)) for k in MAIN} | {
                    "sub": {k: number(entry.get("craft_sub", {}).get(k)) for k in SUBS}}
            judged = [row["by_judge"][j] for j in JUDGES if j in row["by_judge"]]
            for k in MAIN:
                values = [j[k] for j in judged if j[k] is not None]
                kept = [row["by_judge"][j][k] for j in JUDGES if j in row["by_judge"]
                        and j not in drops.get((test, code, k), set()) and row["by_judge"][j][k] is not None]
                row[k] = median(kept) if kept else None
                if values and max(values) - min(values) >= 2:
                    flags.append({"test": test, "code": code, "lane": row["lane"], "field": k,
                                  "values": {j: row["by_judge"][j][k] for j in JUDGES if j in row["by_judge"]},
                                  "resolved": (test, code, k) in drops, "score": row[k]})
            row["sub"] = {}
            for k in SUBS:
                values = [j["sub"][k] for j in judged if j["sub"][k] is not None]
                row["sub"][k] = median(values) if values else None
            lanes.append(row)
        for judge in JUDGES + ("human",):
            form = forms.get((test, judge))
            for pair in (form or {}).get("pairwise_round1", []):
                pick = {"a": pair["a"], "b": pair["b"]}.get(pair.get("publish"), "tie")
                pairs.append({"test": test, "judge": judge, "a": key[(test, pair["a"])], "b": key[(test, pair["b"])],
                              "winner": key[(test, pick)] if pick != "tie" else "tie", "margin": pair.get("margin")})
    # Calibration: each judge against the human on the tests the human scored.
    for judge in JUDGES + ("median",):
        diffs = {k: [] for k in CALIBRATED}
        sub_diffs = []
        for row in lanes:
            human = row["by_judge"].get("human")
            if not human:
                continue
            other = row if judge == "median" else row["by_judge"].get(judge)
            for k in CALIBRATED:
                if human[k] is not None and other.get(k) is not None:
                    diffs[k].append(other[k] - human[k])
            for k in SUBS:
                h, o = human["sub"][k], (other["sub"] if judge == "median" else other["sub"])[k]
                if h is not None and o is not None:
                    sub_diffs.append(o - h)
        human_picks = {(p["test"], p["a"], p["b"]): p["winner"] for p in pairs if p["judge"] == "human"}
        if judge == "median":
            agree = None
        else:
            matched = [p["winner"] == human_picks[(p["test"], p["a"], p["b"])] for p in pairs
                       if p["judge"] == judge and (p["test"], p["a"], p["b"]) in human_picks]
            agree = f"{sum(matched)}/{len(matched)}" if matched else None
        calibration.append({"judge": judge} | {
            k: {"bias": round(mean(v), 2), "mean_abs": round(mean(abs(x) for x in v), 2), "n": len(v)}
            for k, v in diffs.items() if v} | {
            "sub": {"bias": round(mean(sub_diffs), 2), "mean_abs": round(mean(abs(x) for x in sub_diffs), 2),
                    "n": len(sub_diffs)} if sub_diffs else None,
            "pairwise_agrees_with_human": agree})
    return {"lanes": lanes, "pairwise": pairs, "disagreements": flags, "calibration": calibration}


if __name__ == "__main__":
    print(json.dumps(analyse(), indent=1, ensure_ascii=False))
