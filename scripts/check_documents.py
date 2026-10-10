"""Check Vixl documents in CI: the engine behind the repository's GitHub Action (action.yml).

For every document matching the globs it runs ``vixl check --strict --json`` (plus an attached-suite
check when ``--suite`` is given), optionally renders the base version (``git show BASE:path``) and
pixel-diffs it with ``vixl diff``, writes a Markdown summary (to $GITHUB_STEP_SUMMARY when set) and
optionally a proof page. It exits non-zero when a finding reaches ``--fail-on``. With ``--profile`` the
check runs under that check profile (``vixl check --profile``), and without ``--fail-on`` the profile's own
``fail_on`` and suites decide.

Only the ``vixl`` command line (``python -m vixl``) is used, so the script works with any installed vixl-engine that has
``check``, ``diff`` and ``workflow proof``.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LEVELS = ("never", "error", "warning", "fix", "review", "profile")
VIXL = [sys.executable, "-m", "vixl"]  # the interpreter running this script has vixl-engine installed


def run(command):
    process = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    text = process.stdout.strip() or process.stderr.strip()
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {"error": "unreadable_output", "message": text[-2000:]}
    return process.returncode, data


def check(path, checks, suite, profile=""):
    command = [*VIXL, "--json", "-p", path, "check", "--strict"] + (["--checks", *checks] if checks else []) + (
        ["--profile", profile] if profile else [])
    code, data = run(command)
    report = data.get("report", data) if code else data
    result = {"report": report, "error": None if code == 0 or "report" in data else data.get("message")}
    if suite:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as stream:
            json.dump({"suite": json.loads(Path(suite).read_text(encoding="utf-8"))}, stream)
        try:
            code, data = run([*VIXL, "--json", "-p", path, "workflow", "check", "--request", stream.name])
        finally:
            os.unlink(stream.name)
        result["suite"] = data
    return result


def failing(result, level):
    """The findings that reach ``level`` (error, warning or fix), or the reason the check could not run."""
    if result["error"]:
        return [result["error"]]
    issues = result["report"].get("issues", [])
    if level == "never":
        found = []
    elif level == "profile":
        profile = result["report"].get("profile") or {}
        found = [issues[i] for i in profile.get("failing", []) if i < len(issues)]
        found += [{"message": f"suite {name}: {profile['suites'][name]['status']}"}
                  for name in profile.get("failed_suites", [])]
    elif level in ("fix", "review"):
        actions = ("fix",) if level == "fix" else ("fix", "review")
        found = [i for i in issues if i.get("action") in actions or i.get("severity") == "error"]
    else:
        wanted = ("error",) if level == "error" else ("error", "warning")
        found = [i for i in issues if i.get("severity") in wanted]
    suite = result.get("suite")
    if suite is not None and level != "never" and not suite.get("passed", False):
        found.append({"message": f"suite: {suite.get('message') or 'failed'}"})
    return [i.get("message", str(i)) if isinstance(i, dict) else str(i) for i in found]


def base_diff(path, base, folder):
    """Render ``path`` at ``base`` and diff it with the working copy; None when it is new."""
    shown = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True)
    if shown.returncode != 0:
        return None
    before = Path(folder) / "base" / path
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_bytes(shown.stdout)
    image = Path(folder) / "diff" / (path.replace("/", "__") + ".png")
    image.parent.mkdir(parents=True, exist_ok=True)
    code, data = run([*VIXL, "--json", "diff", str(before), path, "--out", str(image), "--overwrite"])
    if code:
        return {"error": data.get("message", "diff failed")}
    return {**data, "image": str(image), "before_path": str(before)}


def summary(rows, level, base):
    lines = ["## Vixl document check", "",
             f"Fail on: `{level}`" + (f" · compared with `{base[:12]}`" if base else ""), "",
             "| Document | Errors | Warnings | Fix | Changed | Status |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        report = row["result"]["report"] or {}
        issues = report.get("issues", [])
        fixes = sum(1 for i in issues if i.get("action") == "fix")
        diff = row.get("diff")
        changed = "new" if base and diff is None else ("" if not base else
                                                       diff.get("error") or f"{diff['changed_fraction']:.2%}")
        status = "❌ " + str(len(row["failing"])) if row["failing"] else "✅"
        lines.append(f"| `{row['path']}` | {report.get('errors', '?')} | {report.get('warnings', '?')} | {fixes} | "
                     f"{changed} | {status} |")
    details = [row for row in rows if row["failing"]]
    if details:
        lines += ["", "### Findings", ""]
        for row in details:
            lines.append(f"**{row['path']}**")
            lines += [f"- {message}" for message in row["failing"][:20]]
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", default="**/*.vixl", help="Globs, separated by spaces or newlines")
    parser.add_argument("--checks", default="", help="vixl check names (default: the standard checks)")
    parser.add_argument("--suite", default="", help="A check-suite JSON file to run on every document")
    parser.add_argument("--fail-on", choices=(*LEVELS, ""), default="",
                        help="default: the profile's fail_on with --profile, else error")
    parser.add_argument("--profile", default="", help="Check profile (draft, review, final or from .vixl-checks.json)")
    parser.add_argument("--base", default="", help="Git revision to compare with (empty: no comparison)")
    parser.add_argument("--proof", default="", help="Write a proof page here (.html)")
    parser.add_argument("--work", default=".vixl-ci", help="Folder for base renders and diff images")
    a = parser.parse_args(argv)
    a.fail_on = a.fail_on or ("profile" if a.profile else "error")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a Windows console cannot print every finding
    # Forward slashes on every platform: the summary shows them and `git show BASE:path` needs them.
    paths = sorted({Path(path).as_posix() for pattern in a.paths.split() for path in glob.glob(pattern, recursive=True)
                    if path.endswith(".vixl") and Path(path).is_file()
                    and not Path(path).resolve().is_relative_to(Path(a.work).resolve())})
    rows = []
    for path in paths:
        result = check(path, a.checks.split(), a.suite, a.profile)
        row = {"path": path, "result": result, "failing": failing(result, a.fail_on)}
        if a.base:
            row["diff"] = base_diff(path, a.base, a.work)
        rows.append(row)
    text = summary(rows, a.fail_on, a.base) if paths else "## Vixl document check\n\nNo documents matched.\n"
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(text)
    print(text)
    if a.proof and rows:
        items = []
        for row in rows:
            item = {"path": row["path"]}
            if row.get("diff") and row["diff"].get("before_path"):
                item["before"] = row["diff"]["before_path"]
            items.append(item)
        request = Path(a.work) / "proof-request.json"
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text(json.dumps({"items": items, "output": a.proof, "title": "Vixl document check",
                                       "overwrite": True}), encoding="utf-8")
        code, data = run([*VIXL, "--json", "workflow", "proof", "--request", str(request), "--workspace", "."])
        if code:
            print(f"Proof page failed: {data.get('message')}", file=sys.stderr)
    return 1 if any(row["failing"] for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
