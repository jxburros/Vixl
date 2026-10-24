"""Run the Vixl agent eval.

    python -m evals.run                         # offline reference agent (no API key)
    python -m evals.run --agent claude          # Claude via the Anthropic SDK
    python -m evals.run --agent claude --effort low --tasks "photo-*"
    python -m evals.run --agent claude --judge   # also score each craft task's document with a model (off by default)
"""

import argparse
import json
import os
from pathlib import Path
import sys

from evals.harness import ClaudeAgent, ReferenceAgent, load_tasks, markdown, over_budget, run


def craft_regressions(results, summary, baseline):
    """Tasks whose craft score is under their stored floor (``craft_scores``), and a mean under
    ``min_mean_craft_score``, as readable lines."""
    by_task = {r["task"]: r for r in results}
    found = []
    for name, floor in baseline.get("craft_scores", {}).items():
        score = by_task.get(name, {}).get("craft_score")
        if score is None or score < floor:
            found.append(f"{name} craft {score} < {floor}")
    floor = baseline.get("min_mean_craft_score")
    if floor is not None and summary.get("mean_craft_score", 0) < floor:
        found.append(f"mean craft {summary.get('mean_craft_score')} < {floor}")
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__.splitlines()[0])
    parser.add_argument("--agent", choices=["reference", "claude"], default="reference")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--baseline", help="Stored task acceptance baseline to compare")
    parser.add_argument("--tasks", default="*", help="glob over task ids, e.g. 'photo-*'")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallbacks")
    parser.add_argument("--out", default="eval-results", help="directory for results.json and report.md")
    parser.add_argument("--keep", action="store_true", help="copy each task's final workspace files into --out")
    parser.add_argument("--judge", action="store_true",
                        help="also score the document of each craft task against the rubric with a model (off by "
                             "default, one call per craft task, never part of the baseline; see evals/judge.py)")
    parser.add_argument("--judge-model", help="the judge's model (default: --model)")
    parser.add_argument("--judge-endpoint", help="base URL of an Anthropic Messages API server for the judge "
                                                 "(default: $VIXL_JUDGE_ENDPOINT, else the SDK's own)")
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
    judge = None
    if args.judge:
        from evals.judge import ENDPOINT_ENV, Judge

        judge = Judge(args.judge_model or args.model, args.judge_endpoint or os.environ.get(ENDPOINT_ENV),
                      save=out / "judge")
    results, summary = run(tasks, agent, keep=out / "workspaces" if args.keep else None, judge=judge)
    meta = {"agent": args.agent, "model": args.model if args.agent == "claude" else None, "effort": args.effort,
            **({"judge": judge.model} if judge else {})}
    (out / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "results": results}, indent=2, default=str), encoding="utf-8")
    regressions = []
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        by_task = {r["task"]: r for r in results}
        for name in baseline["required_passes"]:
            if name not in by_task or not by_task[name]["passed"]:
                regressions.append(name)
        # Calls per task are the cost measure: a task over its budget, or a higher mean, is a regression.
        regressions += over_budget(results, baseline.get("tool_call_budgets", {}))
        ceiling = baseline.get("max_mean_tool_calls")
        if ceiling is not None and summary["mean_tool_calls"] > ceiling:
            regressions.append(f"mean tool calls {summary['mean_tool_calls']} > {ceiling}")
        # Craft is the composition checks' score of the finished document: a drop below a task's floor, or below
        # the mean floor, is a regression (a default change that makes the reference solutions score worse).
        regressions += craft_regressions(results, summary, baseline)
    report = markdown(results, summary, meta)
    if args.baseline:
        report += "\nBaseline: " + ("regressions: " + ", ".join(regressions) if regressions else "all required tasks pass") + "\n"
    if judge:
        (out / "judge.json").write_text(json.dumps({r["task"]: r["judge"] for r in results if "judge" in r}, indent=2),
                                        encoding="utf-8")
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if summary["passed"] == summary["tasks"] and not regressions else 1


if __name__ == "__main__":
    sys.exit(main())
