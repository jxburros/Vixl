"""Re-run the Vixl lane of the tool comparison and package it for blind judging.

    python -m evals.craft_rerun --dry-run                       # the plan; no API calls, nothing written
    python -m evals.craft_rerun                                 # all 16 briefs, both rounds (spends API credits)
    python -m evals.craft_rerun --tests T02,T08 --model claude-opus-5-5 --effort high
    python -m evals.craft_rerun --package-only --runs PATH      # package a finished re-run again

The kit lives in VixlExamples (`evals/tool-comparison/`): pass --examples PATH, set VIXL_EXAMPLES, or clone
VixlExamples beside this repository. Each brief runs in a fresh workspace that mirrors the repository paths the
brief names (the brief, its fixtures, `skills/vixl/`), through the agent harness (`evals/harness.py`) and the
in-process MCP server, with the kit's own kickoff and round-2 prompts. The run folder, every `.vixl` document the
agent left in the workspace and its operation batches are copied to `runs-<date>-<version>/<test>/claude-V/`;
the other lanes come unchanged from the last blind re-judging; `rejudge.py` packages them all; and the judging
prompt is printed with the package paths.
"""

import argparse
import csv
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import zipfile

from evals.harness import Tools

ROOT = Path(__file__).resolve().parents[1]
KIT = Path("evals/tool-comparison")
LANE = "claude-V"
TESTS = [f"T{i:02d}" for i in range(1, 17)]
SOURCES = "src"  # rejudge.py never takes deliverables from a src/ folder
RULE_ADDITION = "Save your .vixl document(s) in the workspace."
HARNESS_NOTE = (
    "(This run has no shell. Your tools are Vixl's MCP tools plus read_text_file and write_text_file, which read "
    "inputs and write text files such as REPORT.md. Every path is relative to the workspace root, which stands for "
    "the repository root.)"
)
SYSTEM_PROMPT = (
    "You are an agent working in a sandboxed copy of a repository through the tools you are given. Work on your own "
    "until the task is done, then reply with a short summary."
)
READABLE = {".md", ".csv", ".lrc", ".txt", ".json", ".srt", ".vtt"}
WRITABLE = {".md", ".txt", ".json", ".csv"}
FILE_TOOLS = [
    {"name": "read_text_file", "description": "Read a text file in the workspace (.md, .csv, .lrc, .txt, .json, "
     ".srt, .vtt), such as a brief, a CSV or lyrics.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description":
                      "Workspace-relative path"}}, "required": ["path"]}},
    {"name": "write_text_file", "description": "Write a text file in the workspace (.md, .txt, .json, .csv), such as "
     "REPORT.md. Overwrites the file.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Workspace-relative path"},
         "text": {"type": "string", "description": "The whole file content"}}, "required": ["path", "text"]}},
]


# --- the kit ---------------------------------------------------------------------------------------------------


def find_examples(path=None):
    """The VixlExamples checkout: --examples, then VIXL_EXAMPLES, then a sibling of this repository."""
    candidates = [Path(path)] if path else []
    if not path and os.environ.get("VIXL_EXAMPLES"):
        candidates.append(Path(os.environ["VIXL_EXAMPLES"]))
    if not candidates:
        candidates.append(ROOT.parent / "VixlExamples")
    for candidate in candidates:
        if (candidate / KIT / "rejudge.py").is_file():
            return candidate.resolve()
    raise SystemExit(f"No tool-comparison kit at {candidates[0] / KIT}: pass --examples PATH or set VIXL_EXAMPLES "
                     "to a VixlExamples checkout.")


def load_module(name, path):
    """A kit script as a module, without leaving bytecode in the kit (it is another repository's checkout)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def load_rejudge(kit):
    """The kit's rejudge.py (it needs Pillow to import; Playwright, pdftoppm, LibreOffice and ffmpeg to build)."""
    return load_module("tool_comparison_rejudge", kit / "rejudge.py")


def brief_file(kit, test):
    found = sorted((kit / "briefs").glob(f"{test}-*.md"))
    if not found:
        raise SystemExit(f"No brief for {test} in {kit / 'briefs'}")
    return found[0]


def lane_rule(kit):
    """The V lane rule from the kit's README, plus the rule that keeps the lane's sources."""
    lines = (kit / "README.md").read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("- **V:**")), None)
    if start is None:
        raise SystemExit(f"No '- **V:**' lane rule in {kit / 'README.md'}")
    rule = [lines[start][len("- **V:**"):].strip()]
    for line in lines[start + 1:]:
        if not line.startswith("  ") or not line.strip():
            break
        rule.append(line.strip())
    return " ".join(rule) + " " + RULE_ADDITION


def kickoff_prompts(kit):
    """The round-1 and round-2 prompt templates, as the kit's README gives them."""
    text = (kit / "README.md").read_text(encoding="utf-8")

    def block(marker):
        at = text.find(marker)
        if at < 0:
            raise SystemExit(f"No {marker!r} in {kit / 'README.md'}")
        match = re.search(r"```text\n(.*?)```", text[at:], re.S)
        return match.group(1).strip()

    return block("**Round 1 (agent lanes).**"), block("**Round 2: the revision.**")


def prompts(kit, rejudge, test):
    """Round 1 and round 2 prompts for one test, filled in as the README says."""
    first, second = kickoff_prompts(kit)
    fill = {"<CODE>": "V", "<LANE RULE>": lane_rule(kit), "<BRIEF FILE>": brief_file(kit, test).name, "<TEST>": test,
            "<AGENT>": "claude", "<ROUND 2 TEXT>": rejudge.round2_request(test)}
    out = []
    for template in (first, second):
        for key, value in fill.items():
            template = template.replace(key, value)
        out.append(template + "\n\n" + HARNESS_NOTE)
    return out


def fixed_source(kit, path=None):
    """The other lanes' fixed deliverables: a rejudge folder (packages/ and sealed/key.csv) or a runs/ folder."""
    if path:
        return Path(path).resolve()
    folders = sorted(d for d in kit.glob("rejudge-*") if (d / "sealed" / "key.csv").is_file() and (d / "packages").is_dir())
    if not folders:
        raise SystemExit(f"No rejudge-*/ folder with packages/ and sealed/key.csv in {kit}; pass --fixed")
    return folders[-1].resolve()


def fixed_lanes(source, test):
    """{lane: description} of the other lanes the fixed source holds for a test."""
    if (source / "sealed" / "key.csv").is_file():
        with open(source / "sealed" / "key.csv", newline="", encoding="utf-8") as handle:
            return {row["lane"]: f"{source.name}/packages/{test}.zip code {row['code']}"
                    for row in csv.DictReader(handle) if row["test"] == test and row["lane"] != LANE}
    lanes = source / test
    return {d.name: str(d) for d in sorted(lanes.iterdir()) if d.is_dir() and d.name != LANE} if lanes.is_dir() else {}


def copy_fixed(source, test, runs):
    """Put the other lanes' deliverables for one test under runs/<test>/<lane>/ (round 2 in round2/)."""
    copied = []
    if (source / "sealed" / "key.csv").is_file():
        with open(source / "sealed" / "key.csv", newline="", encoding="utf-8") as handle:
            codes = {row["code"]: row["lane"] for row in csv.DictReader(handle) if row["test"] == test
                     and row["lane"] != LANE}
        package = source / "packages" / f"{test}.zip"
        if not package.is_file():
            return copied
        with zipfile.ZipFile(package) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if name.endswith("/") or len(parts) < 5 or parts[2] not in ("r1", "r2") or parts[3] != "files":
                    continue
                lane = codes.get(parts[1])
                if not lane:
                    continue
                target = runs / test / lane / ("round2" if parts[2] == "r2" else "") / Path(*parts[4:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                if lane not in copied:
                    copied.append(lane)
        return copied
    for lane in fixed_lanes(source, test):
        shutil.copytree(source / test / lane, runs / test / lane, dirs_exist_ok=True)
        copied.append(lane)
    return copied


# --- the workspace -----------------------------------------------------------------------------------------------


def prepare_workspace(workspace, examples, test):
    """The brief, its fixtures (generated ones made here, never in the kit) and the Vixl skill, at repo paths."""
    kit = examples / KIT
    (workspace / KIT / "briefs").mkdir(parents=True)
    shutil.copy(brief_file(kit, test), workspace / KIT / "briefs")
    fixtures = workspace / KIT / "fixtures"
    shutil.copytree(kit / "fixtures", fixtures, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
    if not (fixtures / "lighthouse.wav").exists():
        load_module("tool_comparison_fixtures", kit / "fixtures" / "make_fixtures.py").song(fixtures / "lighthouse.wav")
    photo = examples / "explorations" / "06-photo-lab" / "photos" / "coast-raw.jpg"
    if not (fixtures / "coast-raw.jpg").exists() and photo.is_file():
        shutil.copy(photo, fixtures / "coast-raw.jpg")
    shutil.copytree(ROOT / "skills" / "vixl", workspace / "skills" / "vixl")
    run = workspace / KIT / "runs" / test / LANE
    run.mkdir(parents=True)
    return run


class LaneTools(Tools):
    """The MCP server plus two text-file tools, so a run with no shell can read its inputs and write REPORT.md."""

    def __init__(self, workspace, **options):
        super().__init__(workspace, **options)
        self.workspace = Path(workspace).resolve()

    def definitions(self):
        return super().definitions() + FILE_TOOLS

    def call(self, name, arguments):
        if name not in {tool["name"] for tool in FILE_TOOLS}:
            return super().call(name, arguments)
        self.calls += 1
        try:
            path = (self.workspace / str(arguments["path"])).resolve()
            if not path.is_relative_to(self.workspace):
                raise ValueError("path must stay inside the workspace")
            if name == "read_text_file":
                if path.suffix.lower() not in READABLE:
                    raise ValueError(f"read_text_file reads {', '.join(sorted(READABLE))} files")
                text = path.read_text(encoding="utf-8")[:200_000]
            else:
                if path.suffix.lower() not in WRITABLE:
                    raise ValueError(f"write_text_file writes {', '.join(sorted(WRITABLE))} files; make images "
                                     "with Vixl")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(arguments["text"]), encoding="utf-8")
                text = f"wrote {path.relative_to(self.workspace).as_posix()}"
        except (OSError, ValueError, KeyError, UnicodeDecodeError) as error:
            self.errors += 1
            text = f"{type(error).__name__}: {error}"
            self.result_chars += len(text)
            return True, [{"type": "text", "text": text}]
        self.result_chars += len(text)
        return False, [{"type": "text", "text": text}]


def digest(folder, skip=()):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and not p.name.endswith(".lock")
            and not set(p.relative_to(folder).parts) & set(skip)}


def run_round(agent, prompt, workspace, run, number, schema, tool_set):
    """One fresh session: the agent works on the prompt; returns its stats and trace."""
    tools = LaneTools(workspace, schema=schema, tools=tool_set)
    started, error = time.monotonic(), None
    try:
        outcome = agent.run({"id": f"{run.parent.name}-r{number}", "prompt": prompt}, tools)
    except Exception as exc:  # A crashed run is a result to record, not a crashed re-run.
        outcome, error = {"round_trips": 0, "usage": {}, "trace": []}, f"{type(exc).__name__}: {exc}"
    finally:
        tools.close()
    folder = run if number == 1 else run / "round2"
    report = folder / "REPORT.md"
    if not report.exists() and outcome.get("final"):
        folder.mkdir(parents=True, exist_ok=True)
        report.write_text("<!-- craft_rerun: the agent wrote no REPORT.md; this is its final reply. -->\n\n"
                          + outcome["final"] + "\n", encoding="utf-8")
    return {"round": number, "round_trips": outcome.get("round_trips", 0), "tool_calls": tools.calls,
            "tool_errors": tools.errors, "usage": outcome.get("usage", {}), "seconds": round(time.monotonic() - started, 1),
            "stop_reason": outcome.get("stop_reason"), "error": error, "final": outcome.get("final")}, outcome.get("trace", [])


def keep_sources(workspace, run, trace, destination):
    """Every .vixl document outside the run folder, the operation batches and the trace, into destination/src/."""
    sources = destination / SOURCES
    sources.mkdir(parents=True, exist_ok=True)
    kept = []
    for path in sorted(workspace.rglob("*.vixl")):
        if not path.is_file() or path.is_relative_to(run):
            continue  # the run folder is copied whole; .vixl/ is the workspace's settings folder
        target = sources / path.relative_to(workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        kept.append(target.relative_to(destination).as_posix())
    batches = [{"call": index, "tool": step["tool"], **{key: step["input"][key] for key in ("document", "path")
                                                          if key in step.get("input", {})},
                "operations": step["input"]["operations"], "error": step.get("error", False)}
               for index, step in enumerate(trace) if isinstance(step.get("input"), dict) and "operations" in step["input"]]
    (sources / "batches.json").write_text(json.dumps(batches, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (sources / "trace.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return kept


def copy_tree(source, destination, skip=()):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or path.name.endswith(".lock") or set(relative.parts) & set(skip):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def run_test(test, agent, examples, runs, *, rounds=2, schema="slim", tool_set="core", meta=None):
    """Both rounds of one brief in a fresh workspace; the lane lands in runs/<test>/claude-V/."""
    kit = examples / KIT
    rejudge = load_rejudge(kit)
    first, second = prompts(kit, rejudge, test)
    destination = runs / test / LANE
    record = {**(meta or {}), "test": test, "brief": brief_file(kit, test).name, "rounds": []}
    with tempfile.TemporaryDirectory(prefix=f"vixl-craft-{test}-") as directory:
        workspace = Path(directory)
        run = prepare_workspace(workspace, examples, test)
        stats, trace = run_round(agent, first, workspace, run, 1, schema, tool_set)
        copy_tree(run, destination, skip=("round2",))
        stats["sources"] = keep_sources(workspace, run, trace, destination)
        stats["missing"] = missing(rejudge, test, destination, round2=False)
        record["rounds"].append(stats)
        if rounds > 1:
            before = digest(run, skip=("round2",))
            stats, trace = run_round(agent, second, workspace, run, 2, schema, tool_set)
            if (run / "round2").is_dir():
                copy_tree(run / "round2", destination / "round2")
            stats["sources"] = keep_sources(workspace, run, trace, destination / "round2")
            stats["missing"] = missing(rejudge, test, destination / "round2", round2=True)
            after = digest(run, skip=("round2",))
            # Round 2 must change nothing outside round2/; what it did change is part of the result.
            stats["changed_outside_round2"] = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
            record["rounds"].append(stats)
    (destination / SOURCES / "run.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


def missing(rejudge, test, folder, round2):
    names = rejudge.deliverable_names(test, round2=round2)
    found = rejudge.find_deliverables(folder, names) if folder.is_dir() else []
    return [name for name in names if not any(Path(str(f.relative_to(folder))).match(name) for f in found)]


# --- packaging -----------------------------------------------------------------------------------------------------


def package(examples, runs, out, tests, seed=None):
    """rejudge.py's blind packages for these tests, zipped per test like the 2026-10-12 set."""
    rejudge = load_rejudge(examples / KIT)
    rejudge.build(runs, out, tests, seed)
    zips = out / "packages"
    zips.mkdir(parents=True, exist_ok=True)
    for test in tests:
        folder = out / "package" / test
        if not folder.is_dir():
            continue
        with zipfile.ZipFile(zips / f"{test}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                archive.write(path, path.relative_to(out / "package").as_posix())
    return zips


def judge_prompt(examples, out, tests):
    """JUDGING.md's prompt (everything below its line), headed with where each package is."""
    text = (examples / KIT / "JUDGING.md").read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[1].strip() if "\n---\n" in text else text.strip()
    where = "\n".join(f"- {test}: {out / 'packages' / f'{test}.zip'} (unzipped: {out / 'package' / test})"
                      for test in tests)
    return ("Judge each test in a fresh session, with three judges, and never show a judge another judge's scores. "
            f"The key is {out / 'sealed' / 'key.csv'}: don't open it until every form is in.\n\nPackages:\n{where}\n\n"
            "Prompt (paste into the judging session with one package):\n\n" + body + "\n")


# --- command line -------------------------------------------------------------------------------------------------


def plan(examples, runs, out, tests, fixed, args, version):
    kit = examples / KIT
    rejudge = load_rejudge(kit)
    lines = [f"Craft re-run of the Vixl lane, Vixl {version}", f"kit: {kit}",
             f"agent: claude {args.model}" + (f", effort {args.effort}" if args.effort else "")
             + f", schema {args.schema}, tools {args.tools}, max {args.max_turns} turns, {args.rounds} round(s)",
             f"runs: {runs}", f"package: {out}", f"fixed lanes: {fixed}", ""]
    for test in tests:
        others = fixed_lanes(fixed, test)
        lines.append(f"{test} {brief_file(kit, test).name}: {LANE} re-run; fixed: "
                     + (", ".join(sorted(others)) or "none"))
    first, second = prompts(kit, rejudge, tests[0])
    lines += ["", f"Round 1 prompt ({tests[0]}):", first, "", f"Round 2 prompt ({tests[0]}):", second, "",
              f"Then: rejudge.py {runs} {out} --tests {' '.join(tests)}, zip each package, print JUDGING.md's prompt."]
    return "\n".join(lines)


def main(argv=None, agent=None):
    parser = argparse.ArgumentParser(prog="python -m evals.craft_rerun", description=__doc__.splitlines()[0])
    parser.add_argument("--examples", help="VixlExamples checkout (default: $VIXL_EXAMPLES, then ../VixlExamples)")
    parser.add_argument("--tests", default=",".join(TESTS), help="comma-separated tests, e.g. T02,T08")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--schema", choices=["full", "slim"], default="slim")
    parser.add_argument("--tools", choices=["all", "core"], default="core")
    parser.add_argument("--max-turns", type=int, default=60)
    parser.add_argument("--rounds", type=int, choices=[1, 2], default=2)
    parser.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallbacks")
    parser.add_argument("--runs", help="run folder (default: <kit>/runs-<date>-<version>)")
    parser.add_argument("--out", help="package folder (default: <kit>/rejudge-<date>-<version>)")
    parser.add_argument("--fixed", help="the other lanes: a rejudge folder or a runs folder (default: the latest "
                                        "<kit>/rejudge-*)")
    parser.add_argument("--seed", type=int, help="seed for the package's random codes")
    parser.add_argument("--overwrite", action="store_true", help="replace a test's existing claude-V run")
    parser.add_argument("--no-package", action="store_true", help="run the lane only")
    parser.add_argument("--package-only", action="store_true", help="package an existing --runs folder")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no API calls, nothing written")
    args = parser.parse_args(argv)

    from vixl import __version__

    examples = find_examples(args.examples)
    kit = examples / KIT
    tests = [t.strip().upper() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in tests if t not in TESTS]
    if unknown:
        parser.error(f"Unknown tests {', '.join(unknown)}; use T01 to T16")
    stamp = f"{datetime.date.today().isoformat()}-{__version__}"
    runs = Path(args.runs).resolve() if args.runs else kit / f"runs-{stamp}"
    out = Path(args.out).resolve() if args.out else kit / f"rejudge-{stamp}"
    fixed = fixed_source(kit, args.fixed)
    if args.dry_run:
        print(plan(examples, runs, out, tests, fixed, args, __version__))
        return 0
    if not args.package_only:
        taken = [t for t in tests if (runs / t / LANE).exists()]
        if taken and not args.overwrite:
            parser.error(f"{runs} already holds {LANE} for {', '.join(taken)}; pass --overwrite or another --runs")
        if agent is None:
            from evals.harness import ClaudeAgent

            agent = ClaudeAgent(args.model, args.effort, args.max_turns, fallbacks=not args.no_fallbacks,
                                system=SYSTEM_PROMPT)
        meta = {"vixl_version": __version__, "model": args.model, "effort": args.effort, "schema": args.schema,
                "tools": args.tools, "date": datetime.date.today().isoformat()}
        for test in tests:
            shutil.rmtree(runs / test / LANE, ignore_errors=True)
            record = run_test(test, agent, examples, runs, rounds=args.rounds, schema=args.schema,
                              tool_set=args.tools, meta=meta)
            others = copy_fixed(fixed, test, runs)
            calls = ", ".join(f"r{r['round']} {r['tool_calls']} calls" + (f" ({r['error']})" if r["error"] else "")
                              + (f", missing {', '.join(r['missing'])}" if r["missing"] else "")
                              for r in record["rounds"])
            print(f"{test}: {calls}; fixed lanes: {', '.join(others) or 'none'}", flush=True)
    if args.no_package:
        return 0
    package(examples, runs, out, tests, args.seed)
    print()
    print(judge_prompt(examples, out, tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
