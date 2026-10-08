"""Throughput: 100 term cards four ways, plus a REST server smoke test (compose dry run, render with variables).

Run from the repository root after workflow 01 (it reuses that card template):

    python explorations/11-ai-packet/workflows/06-throughput-and-rest/build.py

Writes timings.json and rest.json; the 100-card folders are deleted after timing (only a sample is kept).
"""

import base64
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
W1 = HERE.parent / "01-term-of-the-day"
OUT = HERE / "output"
N = 100


def run(cmd, label, timings):
    t = time.perf_counter()
    res = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True)
    timings[label] = round(time.perf_counter() - t, 2)
    print(f"{label}: {timings[label]} s (exit {res.returncode})", flush=True)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"stderr": res.stderr[-1500:]}


def rows100():
    terms = list(csv.DictReader(open(W1 / "terms.csv", encoding="utf-8")))
    return [{**terms[i % len(terms)], "NUM": f"{i + 1:03d}"} for i in range(N)]


def main():
    if not (W1 / "output" / "card.vixl").exists():
        subprocess.run([sys.executable, str(W1 / "build.py")], check=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copy(W1 / "output" / "card.vixl", OUT / "card.vixl")
    shutil.copy(W1 / "output" / "brand.json", OUT / "brand.json")
    rows = rows100()
    with open(OUT / "rows100.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    timings = {"cards": N, "cpu_count": os.cpu_count()}

    # 1. CSV merge with the per-row design check (the default) and without it.
    merged = run(["vixl", "-p", "card.vixl", "render", "--data", "rows100.csv", "--out", "merge-checked"],
                 "render --data, checked", timings)
    timings["render --data rows with fix findings"] = sum(
        any(i.get("action") == "fix" for i in r["check"]["issues"]) for r in merged) if isinstance(merged, list) else None
    run(["vixl", "-p", "card.vixl", "render", "--data", "rows100.csv", "--out", "merge-fast", "--no-check"],
        "render --data --no-check", timings)

    # 2. Checked production runs (reflow action + card suite on every output), 1 and 4 workers.
    for workers in (1, 4):
        req = {"output": f"prod-w{workers}", "spec": {"version": 1, "rows": rows, "format": "png",
                                                      "workers": workers, "actions": ["reflow"], "suites": ["card"]}}
        (OUT / f"req-w{workers}.json").write_text(json.dumps(req))
        res = run(["vixl", "-p", "card.vixl", "workflow", "run", "--request", f"req-w{workers}.json"],
                  f"workflow run, {workers} worker(s)", timings)
        timings[f"workflow run, {workers} worker(s), statuses"] = {
            s: sum(r["status"] == s for r in res.get("results", [])) for s in ("completed", "needs_review", "failed")}
    # A rerun in the same folder reuses verified outputs (fingerprints).
    run(["vixl", "-p", "card.vixl", "workflow", "run", "--request", "req-w4.json"], "workflow run rerun (cached)", timings)

    # 3. In-process Python: load once, render each row with variables.
    from vixl import Project
    t = time.perf_counter()
    p = Project.load(str(OUT / "card.vixl"))
    (OUT / "python").mkdir()
    for r in rows:
        p.render(variables=r).convert("RGB").save(OUT / "python" / f"{r['NUM']}.jpg", quality=85)
    timings["python Project.render loop (JPEG)"] = round(time.perf_counter() - t, 2)
    print("python loop:", timings["python Project.render loop (JPEG)"])

    for label in ("render --data, checked", "render --data --no-check", "workflow run, 1 worker(s)",
                  "workflow run, 4 worker(s)", "python Project.render loop (JPEG)"):
        timings[f"{label}: ms per card"] = round(1000 * timings[label] / N)

    # Keep a sample, drop the rest (100 PNGs per folder).
    (OUT / "sample").mkdir()
    for i in (1, 50, 100):
        shutil.copy(OUT / "python" / f"{i:03d}.jpg", OUT / "sample" / f"python-{i:03d}.jpg")
    for d in ("merge-checked", "merge-fast", "prod-w1", "prod-w4", "python"):
        shutil.rmtree(OUT / d, ignore_errors=True)
    for f in OUT.glob("req-*.json"):
        f.unlink()
    (OUT / "timings.json").write_text(json.dumps(timings, indent=1))

    rest(timings)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def post(port, route, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data, code, ctype = resp.read(), resp.status, resp.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        data, code, ctype = e.read(), e.code, e.headers.get("Content-Type")
    return code, ctype, data, round(time.perf_counter() - t, 2)


def rest(timings):
    """`vixl -p card.vixl serve`, then POST /check, /render with variables, /compose (dry run) and /preview."""
    port = free_port()
    server = subprocess.Popen(["vixl", "-p", "card.vixl", "serve", "--port", str(port)], cwd=OUT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    report = {"port": port}
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/document", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        code, _, data, dt = post(port, "/check", {})
        report["POST /check"] = {"status": code, "s": dt, "passed": json.loads(data).get("passed")}
        code, ctype, data, dt = post(port, "/render", {"variables": {"NUM": "07", "term": "Prompt", "category": "Use it well",
                                     "definition": "The instructions and context you give an AI tool.",
                                     "tryit": "Ask the same question twice, once with an example."}})
        (OUT / "rest-render.png").write_bytes(data) if code == 200 else None
        report["POST /render (variables)"] = {"status": code, "s": dt, "content_type": ctype, "bytes": len(data)}
        body = {"size": "linkedin-post", "seed": 5,
                "layout": {"name": "modern-bulletin", "title": "Understand the AI you use.",
                           "subtitle": "12 key terms, hands-on activities, honest limits.",
                           "label": "AI Field Guide", "cta": "Get the packet", "direction": {"look": "none"}},
                "check": True, "preview": True}
        code, ctype, data, dt = post(port, "/compose", body)
        res = json.loads(data)
        if res.get("preview_base64"):
            (OUT / "rest-compose-preview.png").write_bytes(base64.b64decode(res["preview_base64"]))
        report["POST /compose (dry run)"] = {"status": code, "s": dt, "keys": sorted(res)[:20],
                                             "check_passed": (res.get("check") or {}).get("passed"),
                                             "error": res.get("error"), "message": res.get("message")}
        code, ctype, data, dt = post(port, "/preview", {"max_width": 400})
        report["POST /preview"] = {"status": code, "s": dt, "content_type": ctype, "bytes": len(data)}
    finally:
        server.terminate()
        try:
            out, _ = server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            out = ""
        report["server_log_tail"] = (out or "")[-1200:]
    (OUT / "rest.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "server_log_tail"}, indent=1))


if __name__ == "__main__":
    main()
