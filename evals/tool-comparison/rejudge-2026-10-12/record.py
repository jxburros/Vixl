"""Write the re-judged scores into scoresheet.csv and runs/<test>/scores.csv.

    python evals/tool-comparison/rejudge-2026-10-12/record.py

Fidelity, craft and revision are the blind three-judge medians (analyze.py). Hard checks, report
honesty and editability come from nonblind/<test>.json, corrected by nonblind-resolutions.json.
Run dates, minutes and nudges are facts of the original runs and are kept.
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
JUDGED = "2026-10-13"


def number(value):
    return f"{value:g}" if isinstance(value, (int, float)) else ""


def nonblind():
    results = {}
    for path in sorted((HERE / "nonblind").glob("T*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for lane, entry in data["lanes"].items():
            results[(data["test"], lane)] = entry
    for fix in json.loads((HERE / "nonblind-resolutions.json").read_text(encoding="utf-8")):
        for lane in fix["lanes"]:
            entry = results[(fix["test"], lane)]
            if fix["field"] == "hard":
                for check in entry["hard"]:
                    if fix["check"].lower() in check["check"].lower():
                        if check["pass"] != fix["set"]:
                            check["pass"] = fix["set"]
                            check["evidence"] += f" [corrected: {fix['reason']}]"
                entry["hard_passed"] = sum(1 for c in entry["hard"] if c["pass"])
            else:
                entry[fix["field"]] = fix["set"]
    return results


def main():
    import importlib.util

    spec = importlib.util.spec_from_file_location("analyze", HERE / "analyze.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    blind = {(row["test"], row["lane"]): row for row in module.analyse()["lanes"]}
    checks = nonblind()

    with open(KIT / "scoresheet.csv", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        key = (row["test"], row["lane"])
        if key not in blind:
            for name in ("blind_code", "hard_passed", "hard_total", "fidelity", "craft", "report_honest",
                         "editability", "revision"):
                row[name] = ""
            row["notes"] = f"Not judged in the {JUDGED} re-judging: its source was never committed, so the deliverables can't be rebuilt."
            continue
        scores, facts = blind[key], checks.get(key, {})
        crafts = "/".join(str(scores["by_judge"][j]["craft"]) for j in ("1", "2", "3"))
        failed = [c["check"] for c in facts.get("hard", []) if not c["pass"]]
        row.update({
            "blind_code": scores["code"],
            "hard_passed": str(facts.get("hard_passed", "")), "hard_total": str(facts.get("hard_total", "")),
            "fidelity": number(scores["fidelity"]), "craft": number(scores["craft"]),
            "revision": number(scores["revision"]),
            "report_honest": facts.get("report_honest", ""), "editability": str(facts.get("editability", "")),
            "notes": f"Re-judged {JUDGED}: blind three-judge median (craft {crafts}); hard checks, honesty and "
                     f"editability re-verified on rebuilt files"
                     + (f"; failed: {'; '.join(failed)}" if failed else "")
                     + (f"; editability: {facts['editability_notes']}" if facts.get("editability_notes") else ""),
        })
    with open(KIT / "scoresheet.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for test in sorted({row["test"] for row in rows}):
        path = KIT / "runs" / test / "scores.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(r for r in rows if r["test"] == test)
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main()
