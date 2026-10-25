"""Link impact: what a changed source document does to every document that links to it (``link-impact``).

The workspace dependency graph (``dependents``) finds the documents that link to ``source``, directly or through
other linked documents (up to ``links.MAX_DEPTH`` levels). Each one is evaluated as a candidate (``candidate``):
its links to the source (and to the documents between) are refreshed on a copy, a link whose source changed size
keeps its scale (so a widened logo is drawn wider), and the copy runs ``vixl check`` and its suites and is diffed
against its current render. The report lists the ``passes``, the ``fails`` with their findings and rule results,
what ``changed`` and by how much, and the dependency ``tree``; it renders as JSON, Markdown, JUnit XML or SARIF.

Nothing is written unless ``apply`` is ``if-passing``: then the refreshed dependents that pass are saved together
through the journal ``link-impact`` (``group-recover link-impact`` undoes an interrupted run). A link cycle on disk
is reported, and the documents on it fail.
"""

from pathlib import Path

from ...errors import VixlError, require

JOURNAL = "link-impact"
FIELDS = {"source", "documents", "group", "apply", "checks", "suites", "profile", "fail_on", "waivers", "resize",
          "outputs", "overwrite"}
FIELD_TYPES = {
    "source": {"type": "string", "description": "The changed source document (workspace-relative .vixl)."},
    "documents": {"type": ["array", "string"], "items": {"type": "string"},
                  "description": "Globs or paths to look for dependents in (default every document; with group, "
                                 "extra documents)."},
    "group": {"type": "string", "description": "Look for dependents among this project group's members."},
    "apply": {"type": ["string", "boolean"], "enum": ["never", "if-passing", True, False], "default": "never",
              "description": "if-passing (or true) saves the refreshed dependents that pass, journaled like "
                             "group-apply; never (default) writes nothing."},
    "checks": {"type": "array", "items": {"type": "string"},
               "description": "vixl_check names for each dependent (default the standard checks)."},
    "suites": {"type": "boolean", "default": True, "description": "Run each dependent's attached suites."},
    "profile": {"type": "string", "description": "Check each dependent under this check profile."},
    "fail_on": {"type": "string", "enum": ["error", "warning", "fix", "review", "never"],
                "description": "A dependent fails when a finding reaches this level (default: the profile's, else "
                               "error) or a suite does not pass."},
    "waivers": {"type": "boolean", "default": True, "description": "Apply each dependent's waivers."},
    "resize": {"type": "boolean", "default": True,
               "description": "A link whose source changed size keeps its scale (false keeps its box)."},
    "outputs": {"type": "object", "description": "Write the report: {json, markdown, junit, sarif, github: "
                "workspace path}.",
                "properties": {key: {"type": "string", "description": f"Where to write the {key} report."}
                               for key in ("json", "markdown", "junit", "sarif", "github")}},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace existing output files."},
}
SUMMARY = ("Check every document that links to a changed source (directly or through nested links) on a refreshed "
           "candidate: passes, fails with findings and rule results, changed pixels and the dependency tree; "
           "read-only unless apply is if-passing, which saves the passing dependents through a journal.")


def refresh(project, sources, *, resize=True):
    """Record the current revision of every link in ``project`` whose resolved source is in ``sources`` (paths).
    With ``resize`` a link whose source changed size (and has no crop) keeps its scale. Returns what changed."""
    from ...links import _canvas_size, _record, link_layers, locate, open_source
    from ...validation import check_state

    done = []
    for where, layer in link_layers(project.state):
        try:
            path = locate(project, layer["source"])
        except VixlError:
            continue  # a link this source does not reach; the links check reports it
        if path not in sources:
            continue
        child, revision = open_source(project, path, layer["source"])
        size = list(_canvas_size(child, layer.get("source_page"), layer.get("artboard"), layer["source"]))
        entry = {"layer": layer["name"], "source": layer["source"], "stale": layer.get("source_hash") != revision,
                 **({"on_page": where} if where else {})}
        before = layer.get("source_size")
        if resize and before and before != size and not layer.get("crop") and all(before):
            width = max(1, round(layer["width"] * size[0] / before[0]))
            height = max(1, round(layer["height"] * size[1] / before[1]))
            entry["resized"] = {"from": [layer["width"], layer["height"]], "to": [width, height]}
            layer["width"], layer["height"] = width, height
        _record(project, layer)
        done.append(entry)
    if done:
        check_state(project, project.state)
        project._record([], "Refresh linked documents")
    return done


def _entry(evaluation, item):
    """The per-document entry: check-all's shape (so the report formats render it) plus depth, via and diff."""
    from .workspace_checks import _summarize

    report = evaluation.report
    record = report.get("check")
    if record is None:
        error = report.get("error") or {}
        message = error.get("message") or error.get("error") or "the candidate could not be evaluated"
        entry = {"path": report["document"], "status": "error", "error": message, "failing": [message],
                 "findings": [], "finding_ids": []}
    else:
        entry = _summarize(record)
        entry["failing"] = report["failing"]
    entry.update(depth=item["depth"], via=item["via"], verdict="passes" if report["status"] == "passed" else "fails")
    if report.get("diff"):
        entry["diff"] = report["diff"]
    links = (report.get("result") or {}).get("links") if isinstance(report.get("result"), dict) else None
    if links:
        entry["links"] = links
    return entry


def _scope(session, request):
    from .workspace_checks import members

    if request.get("group") is None and request.get("documents") is None:
        return None
    paths, _ = members(session, request, allow_empty=True)
    return [session.relative(path) for path in paths]


def run(session, request):
    """The ``link-impact`` workflow action."""
    from ... import __version__
    from datetime import datetime, timezone

    from . import dependents as graphs
    from .approval import approved_changes
    from .candidate import evaluate_all
    from .workspace_checks import LEVELS, render

    source = request.get("source")
    require(isinstance(source, str) and source, "source is the changed .vixl document", field="source")
    source_path = session.resolve(source)
    require(source_path.is_file() and source_path.suffix == ".vixl", f"{source} is not a .vixl document",
            "not_found", field="source")
    apply = request.get("apply", "never")
    apply = {True: "if-passing", False: "never"}.get(apply, apply) if isinstance(apply, bool) else apply
    require(apply in ("never", "if-passing"), "apply is never or if-passing", field="apply")
    for field in ("suites", "waivers", "resize", "overwrite"):
        require(type(request.get(field, True)) is bool, f"{field} must be boolean", field=field)
    level = request.get("fail_on") or "error"
    if request.get("profile") and not request.get("fail_on"):
        from ...policy import resolve

        level = resolve(request["profile"], session.workspace, None).get("fail_on", "fix")
    require(level in LEVELS, f"fail_on is one of {', '.join(LEVELS)}", field="fail_on", allowed=list(LEVELS))
    outputs = request.get("outputs") or {}
    require(isinstance(outputs, dict) and set(outputs) <= {"json", "markdown", "junit", "sarif", "github"},
            "outputs maps json, markdown, junit, sarif or github to workspace paths", field="outputs")
    destinations = {}
    for key, value in outputs.items():
        destination = session.resolve(value)
        require(request.get("overwrite", False) or not destination.exists(),
                f"{value} already exists; set overwrite=true", field=f"outputs.{key}")
        destinations[key] = destination
    if request.get("checks") is not None:
        require(isinstance(request["checks"], list) and all(isinstance(c, str) for c in request["checks"]),
                "checks is a list of check names", field="checks")

    relative = session.relative(source_path)
    scope = _scope(session, request)
    built = graphs.graph(session, documents=scope)
    walked = graphs.walk(session, relative, kinds=("link",), built=built, follow=("link",))
    found = walked["dependents"]
    tree = graphs.tree(session, relative, built=built)
    impacted = {session.resolve(relative), *(session.resolve(item["document"]) for item in found)}
    resize = request.get("resize", True)

    def change(candidate, document):
        return {"links": refresh(candidate, impacted, resize=resize)}

    check_request = {key: request[key] for key in ("checks", "suites", "profile", "waivers") if key in request}
    summary, evaluations = evaluate_all(session, [item["document"] for item in found], change, request=check_request,
                                        fail_on=level, apply=apply, journal=JOURNAL)
    entries = [_entry(evaluation, item) for evaluation, item in zip(evaluations, found)]
    approved = approved_changes(session, {e.path: e.candidate for e in evaluations if e.candidate is not None})
    counts = {status: sum(1 for entry in entries if entry["status"] == status)
              for status in ("passed", "failed", "needs_review", "error")}
    result = {
        "version": 1, "vixl_version": __version__, "title": f"Vixl link impact: {relative}",
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": relative, "fail_on": level, "apply": apply, "count": len(entries),
        "totals": {**counts, "failing": sum(1 for entry in entries if entry["failing"]),
                   "errors": sum(entry.get("errors", 0) for entry in entries),
                   "warnings": sum(entry.get("warnings", 0) for entry in entries),
                   "fix": sum(entry.get("fix", 0) for entry in entries), "by_check": {}},
        "documents": entries,
        "passes": summary["passes"],
        "fails": [{"document": entry["path"], "failing": entry["failing"],
                   **({"findings": entry["findings"]} if entry.get("findings") else {}),
                   **({"rules": {name: [rule for rule in suite["rules"]
                                        if rule["status"] not in ("passed", "waived", "not_applicable")]
                                 for name, suite in entry["suites"].items()}} if entry.get("suites") else {})}
                  for entry in entries if entry["verdict"] == "fails"],
        "changed": [{"document": entry["path"], "changed_fraction": entry["diff"]["changed_fraction"]}
                    for entry in entries if (entry.get("diff") or {}).get("changed_pixels")],
        "tree": tree,
        "cycles": walked["cycles"],
        "approved_members_changed": approved,
        "passed": all(entry["verdict"] == "passes" for entry in entries),
    }
    if apply == "if-passing":
        result.update(published=summary["published"], journal=JOURNAL)
    written = {}
    for key, destination in destinations.items():
        from ...production import write_bytes

        write_bytes(destination, render(result, key).encode("utf-8"), replace=True)
        written[key] = session.relative(destination)
    if written:
        result["outputs"] = written
    return result


# Command line -----------------------------------------------------------------------------------

class Report(dict):
    """The JSON report of ``vixl links impact``; ``passed`` sets the exit code."""

    passed = True


def cli(args, options, limits):
    from ...commands import Parser
    from ...interfaces import Session
    from .workspace_checks import FORMATS, FormattedReport, LEVELS, render

    p = Parser(prog="vixl links impact", description="Check every document that links to SOURCE on a refreshed "
               "copy; read-only unless --apply")
    p.add_argument("source", metavar="SOURCE.vixl", help="The changed source document")
    p.add_argument("--group", help="Look for dependents among this project group's members")
    p.add_argument("--glob", nargs="+", metavar="GLOB", dest="documents", help="Look for dependents in these "
                   "documents (default every .vixl in the workspace)")
    p.add_argument("--apply", action="store_true", help="Save the refreshed dependents that pass (journaled; "
                   "group-recover link-impact undoes an interrupted run)")
    p.add_argument("--checks", nargs="+", help="vixl check names (default: the standard checks)")
    p.add_argument("--no-suites", action="store_true", help="Skip the suites attached to each dependent")
    p.add_argument("--profile", help="Check each dependent under this check profile")
    p.add_argument("--fail-on", choices=LEVELS, help="Fail a dependent at this level (default error)")
    p.add_argument("--keep-size", action="store_true", help="Keep link boxes when a source changed size")
    p.add_argument("--format", choices=FORMATS, help="json (default with --json), markdown (default), junit, sarif "
                   "or github")
    p.add_argument("--write", action="append", default=[], metavar="FORMAT=PATH", help="Also write the report")
    p.add_argument("--overwrite", action="store_true", help="Replace existing --write files")
    p.add_argument("--workspace", default=".", help="Workspace folder (default: the current folder)")
    a = p.parse_args(args)
    request = {"source": a.source, "apply": "if-passing" if a.apply else "never", "suites": not a.no_suites,
               "resize": not a.keep_size, "overwrite": a.overwrite}
    for key in ("group", "documents", "checks", "profile", "fail_on"):
        if getattr(a, key) is not None:
            request[key] = getattr(a, key)
    outputs = {}
    for item in a.write:
        key, _, path = item.partition("=")
        require(key in FORMATS and path, f"--write takes FORMAT=PATH with FORMAT one of {', '.join(FORMATS)}",
                field="write")
        outputs[key] = path
    if outputs:
        request["outputs"] = outputs
    workspace = Path(a.workspace).resolve()
    session = Session(None, limits, workspace=workspace)
    result = run(session, {**request, "source": session.relative(Path(a.source).resolve())
                           if Path(a.source).is_absolute() else a.source})
    fmt = a.format or ("json" if options.json else "markdown")
    if fmt == "json":
        report = Report(result)
        report.passed = result["passed"]
        return report
    text = FormattedReport(render(result, fmt).rstrip("\n"))
    text.passed = result["passed"]
    return text

