"""Proof page: one offline HTML page that gathers the whole AI packet for review.

Run from the repository root (best after the other workflows and the sibling folders are built):

    python explorations/11-ai-packet/workflows/04-proof-page/build.py

It scans the packet folders *at run time*, so rerunning it after more work lands picks that up:
  workflows/*/output   -> the cards, the contact sheet, the size comparison, the gate's before/after, the variety sheet
  illustrations/, creative/, documents/, animations/   -> image, GIF, PDF and SVG exports plus .vixl sources
.vixl items get `vixl check` findings on the page; the gated card shows a before/after diff against v1.
The page has approve/reject buttons that download <page>-decisions.json for the reviewer to send back.
"""

import json
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent.parent  # explorations/11-ai-packet (the workflow's workspace)
OUT = HERE / "output"
IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".pdf"}
SIBLINGS = ["illustrations", "creative", "documents", "animations"]
SKIP_PARTS = {"__pycache__", "logo-package", ".cache", "docs", "quick-proof", "reports", "sample", "png", "frames"}
MAX_PER_FOLDER = 5


def rel(p):
    return str(p.relative_to(PACKET))


def items():
    wf = PACKET / "workflows"
    chosen = [
        {"path": "workflows/01-term-of-the-day/output/contact-sheet.jpg", "label": "Term of the day: all 12 cards",
         "note": "Production run: reflow action + 'card' suite on every card."},
        {"path": "workflows/01-term-of-the-day/output/cards/08-hallucination.png", "label": "Card 08 · Hallucination"},
        {"path": "workflows/01-term-of-the-day/output/card.vixl", "label": "Card template (.vixl)"},
        {"path": "workflows/03-check-gated-pipeline/output/v3.png", "label": "Card after the gated change",
         "before": "workflows/03-check-gated-pipeline/output/v1.png",
         "note": "The requested change was refused by the suite; this accessible version was committed."},
        {"path": "workflows/03-check-gated-pipeline/output/v2-rejected.png", "label": "The refused change (for reference)",
         "note": "4.14:1 label, 32 px definition, graphic over the text: refused by workflow act."},
        {"path": "workflows/02-one-message-many-sizes/output/comparison-sheet.jpg",
         "label": "One message, six sizes: adapt vs recompose"},
        {"path": "workflows/02-one-message-many-sizes/output/recompose/linkedin-post.vixl", "label": "LinkedIn post (.vixl)"},
        {"path": "workflows/02-one-message-many-sizes/output/recompose/story.vixl", "label": "Story (.vixl)",
         "note": "Weakest size: the layout's column is 493 px wide on a 1080 px canvas."},
        {"path": "workflows/05-variety-study/output/variety-sheet.jpg", "label": "Variety study: house style 1 vs 2"},
    ]
    chosen = [c for c in chosen if (PACKET / c["path"]).exists()]
    for folder in SIBLINGS:
        root = PACKET / folder
        found = []
        for p in sorted(root.rglob("*")):
            if not p.is_file() or SKIP_PARTS & set(p.relative_to(root).parts[:-1]):
                continue
            if p.suffix.lower() in IMAGE or p.suffix == ".vixl":
                found.append(p)
        # Prefer exports and sheets, then sources; cap per folder so the page stays reviewable.
        found.sort(key=lambda p: (p.suffix == ".vixl", "sheet" not in p.name, p.name))
        for p in found[:MAX_PER_FOLDER]:
            chosen.append({"path": rel(p), "label": f"{folder} / {p.name}"})
    return chosen


def main():
    OUT.mkdir(exist_ok=True)
    request = {"items": items(), "output": "workflows/04-proof-page/output/ai-packet-proof.html",
               "title": "AI Field Guide packet: review", "decisions": True, "overwrite": True,
               "max_size": 256}  # PNG data URIs: 1200 px (the default) made a 39 MB page
    (OUT / "proof-request.json").write_text(json.dumps(request, indent=1))
    print(f"{len(request['items'])} items")
    # One unreadable item (e.g. a .vixl whose linked source is missing) aborts the whole page, so drop the
    # item the error names and try again, recording what was left out.
    dropped, t = [], time.perf_counter()
    for _ in range(8):
        (OUT / "proof-request.json").write_text(json.dumps(request, indent=1))
        res = subprocess.run(["vixl", "--json", "workflow", "proof", "--request", str(OUT / "proof-request.json"),
                              "--workspace", str(PACKET)], capture_output=True, text=True)
        m = re.search(r"items\[(\d+)\]", res.stderr)
        if res.returncode == 0 or not m:
            break
        bad = request["items"].pop(int(m.group(1)))
        dropped.append({"item": bad["path"], "error": res.stderr.strip()[-400:]})
        print("dropped", bad["path"])
    dt = round(time.perf_counter() - t, 2)
    print(res.stdout[-800:], res.stderr[-800:])
    page = OUT / "ai-packet-proof.html"
    info = {"items": len(request["items"]), "seconds": dt, "exit": res.returncode,
            "bytes": page.stat().st_size if page.exists() else None, "dropped": dropped}
    (OUT / "proof-run.json").write_text(json.dumps(info, indent=1))
    print(info)


if __name__ == "__main__":
    main()
