"""Run the Vixl agent eval.

    python -m evals.run                         # offline reference agent (no API key)
    python -m evals.run --agent claude          # Claude via the Anthropic SDK
    python -m evals.run --agent claude --schema slim --effort low --tasks "photo-*"
"""

import argparse
import json
from pathlib import Path
import sys

from evals.harness import ClaudeAgent, ReferenceAgent, load_tasks, markdown, run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__.splitlines()[0])
    parser.add_argument("--agent", choices=["reference", "claude"], default="reference")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--schema", choices=["full", "slim"], default="full", help="MCP schema mode under test")
    parser.add_argument("--tools", choices=["all", "core"], default="all")
    parser.add_argument("--baseline", help="Stored task acceptance baseline to compare")
    parser.add_argument("--tasks", default="*", help="glob over task ids, e.g. 'photo-*'")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallbacks")
    parser.add_argument("--out", default="eval-results", help="directory for results.json and report.md")
    parser.add_argument("--keep", action="store_true", help="copy each task's final workspace files into --out")
    args = parser.parse_args(argv)

    tasks = load_tasks(pattern=args.tasks)
    if not tasks:
        parser.error(f"No tasks match {args.tasks!r}")
    if args.agent == "claude":
        agent = ClaudeAgent(args.model, args.effort, args.max_turns, fallbacks=not args.no_fallbacks)
    else:
        agent = ReferenceAgent()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results, summary = run(tasks, agent, schema=args.schema, keep=out / "workspaces" if args.keep else None, tool_set=args.tools)
    meta = {"agent": args.agent, "model": args.model if args.agent == "claude" else None, "effort": args.effort, "schema": args.schema, "tools": args.tools}
    (out / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "results": results}, indent=2, default=str))
    regressions = []
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text())
        by_task = {r["task"]: r for r in results}
        for name in baseline["required_passes"]:
            if name not in by_task or not by_task[name]["passed"]:
                regressions.append(name)
    report = markdown(results, summary, meta)
    if args.baseline:
        report += "\nBaseline: " + ("regressions: " + ", ".join(regressions) if regressions else "all required tasks pass") + "\n"
    (out / "report.md").write_text(report)
    print(report)
    return 0 if summary["passed"] == summary["tasks"] and not regressions else 1


if __name__ == "__main__":
    sys.exit(main())
