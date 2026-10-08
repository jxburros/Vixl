"""A check-suite-gated pipeline for the term-of-the-day cards.

Run from the repository root (after workflow 01, whose card template this reuses):

    python explorations/11-ai-packet/workflows/03-check-gated-pipeline/build.py

The story it replays, the way a small comms team would meet it:
  1. Baseline: the approved card template (v1) with its "card" suite attached. The gate passes.
  2. A teammate's change request: "make TRY IT teal, the definition smaller so long ones fit, and the
     network graphic bigger". Sent through `vixl workflow act`, which applies it to a candidate, runs
     the suites and commits only on a clean pass: it is refused, with the failing rules and numbers.
  3. The same change forced into a copy (v2-rejected.vixl) so the proof page can show what the gate saw.
  4. A fix that keeps the intent (teal TRY IT chip with white type, bigger graphic placed clear of the text,
     definition unchanged): `act` commits it (v3).
  5. `vixl diff` v1 → v2 and v1 → v3, with `--max-fraction` as a "small change only" gate.
  6. The data gate: a new CSV row with an over-long definition fails `render --data`'s per-row check;
     the edited row passes.
Exit code is 0 only when the final state passes every gate.
"""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W1 = HERE.parent / "01-term-of-the-day"
OUT = HERE / "output"
LOG = []


def vixl(*args, check=False):
    cmd = ["vixl", *map(str, args)]
    print("$", " ".join(cmd), flush=True)
    res = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True)
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        data = {"stdout": res.stdout[-1500:], "stderr": res.stderr[-1500:]}
    if check and res.returncode:
        raise SystemExit(f"failed: {cmd}\n{res.stderr[-1500:]}")
    return res.returncode, data


def gate(doc, label):
    """The gate: no `fix` design findings and every attached suite passes."""
    code, chk = vixl("-p", doc, "check", "--json")
    fixes = [i["message"] for i in chk.get("issues", []) if i.get("action") == "fix"]
    (OUT / "req-suite.json").write_text(json.dumps({"suite": "card"}))
    _, suite = vixl("-p", doc, "workflow", "check", "--request", "req-suite.json")
    failed = [{"id": r["id"], **{k: r[k] for k in ("actual", "expected", "positions", "distance") if k in r}}
              for r in suite.get("results", []) if r.get("status") != "passed"]
    ok = not fixes and suite.get("status") == "passed"
    LOG.append({"step": label, "document": doc, "pass": ok, "fix_findings": fixes, "suite_failed": failed})
    print(f"  GATE {label}: {'PASS' if ok else 'FAIL'} fix={fixes} suite_failed={[f['id'] for f in failed]}")
    return ok


def main():
    if not (W1 / "output" / "card.vixl").exists():
        subprocess.run([sys.executable, str(W1 / "build.py")], check=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in ("card.vixl", "brand.json"):
        shutil.copy(W1 / "output" / f, OUT / ("v1.vixl" if f == "card.vixl" else f))

    # 1. Baseline.
    gate("v1.vixl", "v1 baseline")
    vixl("-p", "v1.vixl", "export", "v1.png", check=True)

    # 2. The requested change, through the checked-action path.
    request = [
        {"type": "text-set", "target": "try-label", "color": "@accent-text"},
        {"type": "text-set", "target": "definition", "size": 32},
        {"type": "scale", "target": "motif", "value": 1.35},
        {"type": "move", "target": "motif", "x": 640, "y": 915},
    ]
    shutil.copy(OUT / "v1.vixl", OUT / "candidate.vixl")
    (OUT / "req-act-v2.json").write_text(json.dumps({"operations": request, "suites": ["card"]}))
    code, act2 = vixl("-p", "candidate.vixl", "workflow", "act", "--request", "req-act-v2.json")
    (OUT / "act-v2.json").write_text(json.dumps(act2, indent=1))
    LOG.append({"step": "v2 act (requested change)", "exit": code, "committed": act2.get("committed"),
                "failed": [r["id"] for r in act2.get("checks", {}).get("card", {}).get("results", [])
                           if r["status"] != "passed"]})

    # 3. Force it into a copy so the proof can show what the gate refused.
    shutil.copy(OUT / "v1.vixl", OUT / "v2-rejected.vixl")
    (OUT / "ops-v2.json").write_text(json.dumps(request))
    vixl("-p", "v2-rejected.vixl", "apply", "ops-v2.json", check=True)
    gate("v2-rejected.vixl", "v2 forced")
    vixl("-p", "v2-rejected.vixl", "export", "v2-rejected.png", check=True)

    # 4. A fix that keeps the intent. The first try was itself refused (the bigger graphic sat 2.4 px from
    #    the panel edge; the suite asks for 16), so the pipeline tries the corrected placement next.
    base = [
        {"type": "solid", "name": "try-chip", "x": 104, "y": 906, "width": 160, "height": 58, "color": "@accent"},
        {"type": "reorder", "target": "try-chip", "below": "try-label"},
        {"type": "text-set", "target": "try-label", "color": "@on-accent"},
        {"type": "move", "target": "try-label", "x": 124, "y": 920},
        {"type": "move", "target": "tryit", "y": 990},
    ]
    attempts = {"v3a": base + [{"type": "scale", "target": "motif", "value": 1.2},
                               {"type": "move", "target": "motif", "x": 760, "y": 912}],
                "v3b": base + [{"type": "scale", "target": "motif", "value": 1.15},
                               {"type": "move", "target": "motif", "x": 748, "y": 920}]}
    shutil.copy(OUT / "v1.vixl", OUT / "v3.vixl")
    committed = False
    for name, ops in attempts.items():
        (OUT / f"req-act-{name}.json").write_text(json.dumps({"operations": ops, "suites": ["card"]}))
        code, act = vixl("-p", "v3.vixl", "workflow", "act", "--request", f"req-act-{name}.json")
        (OUT / f"act-{name}.json").write_text(json.dumps(act, indent=1))
        failed = [r["id"] for r in act.get("checks", {}).get("card", {}).get("results", []) if r["status"] != "passed"]
        LOG.append({"step": f"{name} act (fix)", "exit": code, "committed": act.get("committed"), "failed": failed})
        print(f"  ACT {name}: committed={act.get('committed')} failed={failed}")
        if act.get("committed"):
            committed = True
            break
    final_ok = committed
    final_ok &= gate("v3.vixl", "v3 fixed")
    vixl("-p", "v3.vixl", "export", "v3.png", check=True)

    # 5. Visual diffs; v1 -> v3 must stay a small, local change.
    for a, b in (("v1.vixl", "v2-rejected.vixl"), ("v1.vixl", "v3.vixl")):
        out = f"diff-{Path(a).stem}-{Path(b).stem}.png"
        code, d = vixl("diff", a, b, "--out", out, "--mode", "side-by-side", "--max-fraction", "0.05", "--json")
        LOG.append({"step": f"diff {a} -> {b}", "exit": code, **{k: d.get(k) for k in
                    ("changed_pixels", "changed_fraction", "changed_region", "passed")}})
        print("  DIFF", a, b, code, d.get("changed_fraction"), d.get("changed_region"))
        if b == "v3.vixl":
            final_ok &= code == 0

    # 6. The data gate.
    rows = list(csv.DictReader(open(W1 / "terms.csv", encoding="utf-8")))
    new = {"NUM": "13", "term": "Retrieval-augmented generation", "category": "How it works",
           "definition": "A way of answering questions in which the system first searches a trusted collection of "
                         "documents, then passes the most relevant passages to a language model together with your "
                         "question, so that the answer can quote and point to real sources instead of relying only "
                         "on what the model absorbed in training.",
           "tryit": "Ask a tool that cites sources a question, then open two of the citations."}
    for name, row in (("rows-bad.csv", new), ("rows-fixed.csv", {**new, "term": "Retrieval (RAG)",
                      "definition": "The system first searches trusted documents, then gives the best passages to a "
                                    "language model with your question, so answers can cite real sources."})):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerow(row)
        out = name.replace(".csv", "")
        code, res = vixl("-p", "v3.vixl", "render", "--data", name, "--out", out)
        issues = [i["message"] for r in (res if isinstance(res, list) else []) for i in r["check"]["issues"]
                  if i.get("action") == "fix"]
        ok = not issues
        LOG.append({"step": f"render --data {name}", "exit": code, "pass": ok, "fix_findings": issues})
        print(f"  DATA {name}: {'PASS' if ok else 'FAIL'} {issues}")
        if name == "rows-fixed.csv":
            final_ok &= ok
            shutil.rmtree(OUT / out)  # a passing row needs no evidence image

    (OUT / "pipeline-log.json").write_text(json.dumps(LOG, indent=1))
    for p in OUT.glob("req-*.json"):
        p.unlink()
    (OUT / "candidate.vixl").unlink(missing_ok=True)
    print("PIPELINE", "PASS" if final_ok else "FAIL")
    return 0 if final_ok else 1


if __name__ == "__main__":
    sys.exit(main())
