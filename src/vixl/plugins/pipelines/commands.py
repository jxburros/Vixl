"""Command-line shorthands of the pipelines actions, through the ``cli-command`` hook: ``vixl watch`` and
``vixl pipeline run NAME``."""

from pathlib import Path


def command(cmd, args, options, limits):
    if cmd == "watch":
        from .watch import cli

        return cli(args, options, limits)
    if cmd == "pipeline":
        return pipeline_cli(args, options, limits)
    return None


class Report(dict):
    """The JSON result of ``vixl pipeline run``; ``passed`` sets the exit code."""

    passed = True


def pipeline_cli(args, options, limits):
    from ...commands import Parser
    from ...errors import require
    from ...interfaces import Session
    from .runner import run

    p = Parser(prog="vixl pipeline", description="Run a saved pipeline (resource-save kind pipelines) over its "
               "documents; the first run of an id is a dry run unless --execute")
    p.add_argument("action", choices=["run"], help="run: plan or run the pipeline")
    p.add_argument("name", metavar="NAME", help="The saved pipeline")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List the planned steps and outputs; write nothing")
    mode.add_argument("--execute", action="store_true", help="Run it, even when the run has no record yet")
    p.add_argument("--run", metavar="ID", help="Run id: the record .vixl-runs/ID/run.json, resumed when it exists "
                   "(default: the pipeline name)")
    p.add_argument("--glob", nargs="+", metavar="GLOB", dest="documents", help="Run over these documents instead of "
                   "the pipeline's targets")
    p.add_argument("--group", help="Run over this project group instead of the targets")
    p.add_argument("--workspace", default=".", help="Workspace folder (default: the current folder)")
    a = p.parse_args(args)
    require(a.name.strip(), "Give the pipeline name", "usage_error", field="name")
    request = {"pipeline": a.name}
    if a.dry_run or a.execute:
        request["dry_run"] = a.dry_run
    for key in ("run", "documents", "group"):
        if getattr(a, key) is not None:
            request[key] = getattr(a, key)
    result = Report(run(Session(None, limits, workspace=Path(a.workspace).resolve()), request))
    result.passed = result.get("dry_run", False) or result.get("status") == "completed"
    return result
