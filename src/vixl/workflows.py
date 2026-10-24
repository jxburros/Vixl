"""One workspace-scoped production API shared by CLI, REST and MCP."""

from pathlib import Path
from .studio import ACTIONS as STUDIO_ACTIONS
from .emoji_workflows import ACTIONS as EMOJI_ACTIONS

from .automation import bounded_object
from .errors import require, VixlError
from .links import ACTIONS as LINK_ACTIONS
from . import natural_guidance, plugins, variations

ACTIONS = {
    "check": ({"suite", "suites", "mode", "variables", "artboard", "page", "comp", "artboards", "pages", "comps",
               "include_hidden"}, set()),
    "act": ({"operations", "suites", "dry_run", "repair"}, {"operations"}),
    "capture": ({"recipe", "bindings", "output"}, {"recipe", "output"}),
    "plan": ({"spec"}, {"spec"}),
    "run": ({"spec", "output"}, {"spec", "output"}),
    "preview": ({"output", "quality", "time"}, {"output"}),
    "library-save": ({"directory", "name", "description", "tags"}, {"directory", "name"}),
    "library-search": ({"directory", "query"}, {"directory"}),
    "library-open": ({"directory", "id", "output"}, {"directory", "id", "output"}),
    "library-place": ({"directory", "id", "name", "as"}, {"directory", "id", "name"}),
    "submit": ({"job", "start", "workers"}, {"job"}),
    "status": ({"id"}, {"id"}),
    "cancel": ({"id"}, {"id"}),
    "resume": ({"id"}, {"id"}),
    "work": ({"workers"}, set()),
    "start": ({"workers"}, set()),
    "form-fill": ({"data", "values", "output", "name", "format", "combine", "mode", "skip_invalid", "dry_run", "check",
                   "unknown", "dpi"}, set()),
    "adapt-sizes": ({"sizes", "directory", "name", "options", "formats", "overwrite", "report", "suites"}, {"sizes"}),
}


ACTIONS.update(EMOJI_ACTIONS)
ACTIONS.update(natural_guidance.ACTIONS)
ACTIONS.update(variations.ACTIONS)
ACTIONS.update(STUDIO_ACTIONS)
ACTIONS.update(LINK_ACTIONS)
# Built-in plugins (vixl.plugins) add their own workflow actions.
ACTIONS.update({action: spec for action, (_, spec) in plugins.workflow_actions().items()})
FILL_FORMATS = ("pdf", "png", "jpeg", "jpg", "webp", "tiff", "svg")

PATH = {"type": "string", "description": "Workspace-relative path."}
# Field types shown by describe(). workflow_schema holds every action's typed, described fields
# (shared names, per-action overrides, the check-suite object); ACTION_FIELD_TYPES below also
# drives form-fill's type checks, and takes precedence there.
ACTION_FIELD_TYPES = {
    "form-fill": {
        "values": {"type": "object", "description": "One copy: {field key: value}. Needs output (a file path). "
                   "Give values or data, not both."},
        "data": {**PATH, "description": "Batch: a CSV with a column per field key and a row per copy. Needs output "
                 "(a directory) or combine."},
        "output": {**PATH, "description": "With values: the filled file (.pdf, .png, …). With data: a new directory "
                   "for one file per row."},
        "combine": {"type": ["string", "boolean"], "description": "With data: one combined PDF with a page per row, "
                    "as a .pdf path; true writes <data name>-filled.pdf next to the CSV (or to output when it is "
                    "a .pdf). Replaces output as a directory."},
        "name": {"type": "string", "default": "{row}", "description": "With data and output: file name template "
                 "using {row} and {column} values."},
        "format": {"type": "string", "enum": list(FILL_FORMATS), "description": "Output format (default: pdf, or "
                   "from the output suffix for values)."},
        "mode": {"type": "string", "enum": ["flatten", "editable"], "default": "flatten",
                 "description": "flatten draws values into the artwork; editable writes a fillable PDF."},
        "skip_invalid": {"type": "boolean", "default": False, "description": "With data: skip bad rows instead of "
                         "failing the batch."},
        "check": {"type": "string", "enum": ["design"], "description": "With data: also run the design checks."},
        "unknown": {"type": "string", "enum": ["error", "ignore"], "default": "error",
                    "description": "What to do with keys that match no field."},
        "dpi": {"type": "number", "exclusiveMinimum": 0, "description": "Raster resolution."},
    },
}

for _module in (natural_guidance, variations):
    for _action in _module.ACTIONS:
        ACTION_FIELD_TYPES[_action] = _module.FIELD_TYPES



def field_types(action):
    from .workflow_schema import properties

    fields = ACTIONS[action][0]
    plugin_types = plugins.workflow_field_types(action) if action in plugins.workflow_actions() else {}
    types = {**properties(action, fields), **plugin_types, **ACTION_FIELD_TYPES.get(action, {})}
    return {field: types[field] for field in sorted(fields) if field in types}


def describe():
    from .workflow_schema import SUITE, summary

    return {
        "version": 1,
        "actions": {
            k: {"summary": summary(k), "fields": sorted(v[0]), "required": sorted(v[1]), "properties": field_types(k)}
            for k, v in ACTIONS.items()
        },
        "definitions": {"suite": SUITE},
        "help": "docs/guides/automation/production.md; all paths are workspace-relative; submit + start runs durable background work. "
                "definitions.suite is the check-suite object (attach it with the suite-set operation, or pass it "
                "inline to check).",
    }


def dispatch(session, action, request, document=None):
    from .production import Library, plan, run, capture_recipe, write_bytes

    require(action in ACTIONS, "Unknown workflow action", allowed=sorted(ACTIONS))
    allowed, required = ACTIONS[action]
    bounded_object(request, allowed, "Unknown workflow request field")
    require(required <= request.keys(), "Missing workflow fields", required=sorted(required))
    # replace-across's replace is its list of rules; elsewhere replace is a flag.
    for field in ("dry_run",) if action == "replace-across" else ("dry_run", "replace"):
        if field in request:
            require(type(request[field]) is bool, f"{field} must be boolean")
    if action in plugins.workflow_actions():
        return plugins.dispatch_workflow(session, action, request, document)
    if action in EMOJI_ACTIONS:
        from .emoji_workflows import dispatch as emoji_dispatch
        return emoji_dispatch(session, action, request, document)
    if action in natural_guidance.ACTIONS:
        return natural_guidance.dispatch(session, action, request, document)
    if action in variations.ACTIONS:
        return variations.dispatch(session, action, request, document)
    if action in LINK_ACTIONS:
        from .links import dispatch as links_dispatch

        return links_dispatch(session, request, document)
    if action in STUDIO_ACTIONS:
        from .studio import dispatch as studio_dispatch
        try:
            return studio_dispatch(session, action, request, document)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VixlError("invalid_request", f"Invalid {action} request: {exc}") from exc
    if action == "adapt-sizes":
        from .adapt import adapt_copies
        from .io_policy import export_file

        return adapt_copies(session, export_file, request["sizes"], request.get("directory", "."),
                            request.get("name", "{name}-{size}"), request.get("options"), document,
                            request.get("overwrite", False), request.get("formats"), request.get("report", "summary"),
                            request.get("suites", True))
    if action == "plan":
        return plan(request["spec"])
    if action == "form-fill":
        try:
            return form_fill(session, request, document)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VixlError("invalid_request", f"Invalid form-fill request: {exc}",
                            suggestions=["See vixl_reference('workflows') actions['form-fill'].properties"]) from exc
    if action in ("submit", "status", "cancel", "resume", "work", "start"):
        from .jobs import Queue

        queue = Queue(session.workspace, session.limits)
        if action == "submit":
            job = dict(request["job"])
            if job.get("kind") in ("production", "generate") and not job.get("source"):
                with session.project(document=document) as project:
                    job["source"] = session.relative(project.path)
            result = queue.submit(job)
            if request.get("start"):
                result["worker"] = queue.start(request.get("workers", 1))
            return result
        if action in ("status", "cancel", "resume"):
            return getattr(queue, action)(request["id"])
        value = getattr(queue, action)(request.get("workers", 1))
        return {"jobs": value} if action == "work" else value
    if action.startswith("library-"):
        library = Library(session.resolve(request["directory"]))
        if action == "library-search":
            return {"items": library.search(request.get("query", ""))}
        if action == "library-open":
            destination = session.resolve(request["output"])
            require(destination.suffix == ".vixl" and not destination.exists(), "Choose a new .vixl filename")
            project = library.load(request["id"], limits=session.limits)
            project.path, project._revision = None, None
            project.save(destination)
            return {"output": session.relative(destination)}
        with session.project(write=action == "library-place", document=document) as project:
            if action == "library-save":
                return library.save(
                    project, request["name"], request.get("description", ""), request.get("tags")
                )
            return library.place(project, request["id"], request["name"], request.get("as", "group"))
    if action == "act":
        from .io_policy import service_check

        with session.project(write=not request.get("dry_run", False), document=document) as project:
            return project.act(validator=service_check, **request)
    # Release the session/document lock before long read-only production runs.
    with session.project(document=document) as project:
        project = project.clone()
    if action == "check":
        return check_suites(project, request)
    if action == "run":
        return run(project, request["spec"], session.resolve(request["output"]))
    if action == "capture":
        destination = session.resolve(request["output"])
        require(destination.suffix == ".vixl" and not destination.exists(), "Choose a new .vixl filename")
        candidate = capture_recipe(project, request["recipe"], request.get("bindings", {}))
        candidate.path, candidate._revision = None, None
        candidate.save(destination)
        return {"output": session.relative(destination), "recipe": candidate.state["recipe"]}
    require(request.get("quality", "draft") in ("draft", "final"), "Quality must be draft or final")
    destination = session.resolve(request["output"])
    require(destination.suffix == ".png", "Preview output must be PNG")
    from .render_cache import enable

    enable(project, session.workspace / ".vixl-cache")
    if request.get("time") is not None:
        from .timeline import project_at

        project = project_at(project, request["time"])
    if request.get("quality", "draft") == "draft":
        from .proxy import render_preview

        image = render_preview(project, 640, 640)
    else:
        image = project.render()
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    write_bytes(destination, buffer.getvalue())
    return {
        "output": session.relative(destination),
        "quality": request.get("quality", "draft"),
        "size": list(image.size),
        "generation_calls": 0,
    }


def check_suites(project, request):
    """Workflow check: one suite (``suite``, a name or an inline object) returns its report; without one, every
    attached and inherited suite runs (``suites`` narrows them) and the reports come back under ``suites``."""
    from .assurance import effective

    request = dict(request)
    if "suite" in request:
        require("suites" not in request, "Give suite or suites, not both", field="suites")
        return project.check_suite(request.pop("suite"), **request)
    available = effective(project)
    names = request.pop("suites", None)
    if names is None:
        names = list(available)
    require(isinstance(names, list) and all(isinstance(name, str) for name in names),
            "suites is a list of suite names", field="suites")
    unknown = [name for name in names if name not in available]
    require(not unknown, f"Unknown suite(s) {unknown}; attached or inherited: {', '.join(available) or 'none'}",
            field="suites", suggestions=sorted(available))
    require(names, "No suites are attached or inherited; attach one with suite-set or pass suite", field="suite")
    reports = {name: project.check_suite(name, **request) for name in names}
    errors = sum(report["errors"] for report in reports.values())
    review = sum(report["needs_review"] for report in reports.values())
    return {"passed": all(report["passed"] for report in reports.values()),
            "status": "failed" if errors else "needs_review" if review else "passed",
            "errors": errors, "needs_review": review, "suites": reports}


def cli(args, options, limits):
    from .commands import Parser
    from .io_policy import read_json
    from .interfaces import Session

    parser = Parser(
        prog="vixl workflow",
        description="Portable checks, recipes, production, libraries and background jobs",
    )
    parser.add_argument("action", choices=["schema", "worker", *ACTIONS])
    parser.add_argument("--request", help="JSON request file (or - for stdin)")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument("--workers", type=int, default=1)
    a = parser.parse_args(args)
    if a.action == "schema":
        return describe()
    if a.action == "worker":
        from .jobs import worker

        worker(a.workspace, a.workers)
        return {"status": "idle"}
    request = read_json(a.request) if a.request else {}
    session = Session(options.project, limits, workspace=a.workspace)
    return dispatch(session, a.action, request)


def _check_types(action, request):
    """Reject a wrongly typed field with the expected type and an example, instead of a raw error."""
    for field, schema in ACTION_FIELD_TYPES.get(action, {}).items():
        if field not in request:
            continue
        value, expected = request[field], schema["type"]
        expected = expected if isinstance(expected, list) else [expected]
        checks = {"string": lambda v: isinstance(v, str), "boolean": lambda v: type(v) is bool,
                  "object": lambda v: isinstance(v, dict),
                  "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
        ok = any(checks[kind](value) for kind in expected)
        if ok and "enum" in schema:
            ok = (value.lower().lstrip(".") if field == "format" else value) in schema["enum"]
        if not ok:
            wanted = " or ".join(expected) + (f" (one of {', '.join(map(str, schema['enum']))})" if "enum" in schema else "")
            raise VixlError("invalid_request", f"{field} must be {wanted}; got {type(value).__name__} {value!r}",
                            field=field, expected=schema, suggestions=_examples(field, schema))


def _examples(field, schema):
    if "enum" in schema:
        return [{field: value} for value in schema["enum"]]
    return {"combine": [{"combine": "filled/all.pdf"}, {"combine": True}],
            "output": [{"output": "filled.pdf"}, {"output": "filled/"}],
            "data": [{"data": "rows.csv"}], "values": [{"values": {"full_name": "Ada"}}],
            "name": [{"name": "{row}-{full_name}"}], "dpi": [{"dpi": 150}]}.get(field, [])


def form_fill(session, request, document=None):
    """Fill the open form: ``values`` and ``output`` for one copy, or ``data`` (a CSV) with an
    ``output`` directory or a ``combine`` PDF (``combine: true`` picks the path). Nothing is
    written to the document."""
    from .forms import check_values, fill, fill_data

    _check_types("form-fill", request)
    require(("data" in request) != ("values" in request), "Give values (one copy) or data (a CSV), not both",
            field="data", suggestions=[{"values": {"full_name": "Ada"}, "output": "one.pdf"},
                                       {"data": "rows.csv", "combine": "all.pdf"}])
    if "values" in request:
        require(not request.get("combine"), "combine is for data (a CSV); with values give output",
                field="combine", suggestions=[{"output": "filled.pdf"}])
    with session.project(document=document) as project:
        options = {key: request[key] for key in ("mode", "unknown", "dpi") if key in request}
        if "values" in request:
            if request.get("dry_run"):
                _, _, errors = check_values(project, request["values"], unknown=request.get("unknown", "error"))
                return {"dry_run": True, "valid": not errors, "errors": errors}
            require(isinstance(request.get("output"), str), "Give an output path", field="output",
                    suggestions=[{"output": "filled.pdf"}])
            destination = session.resolve(request["output"])
            result = fill(project, request["values"], destination, format=request.get("format"), **options)
            return {**result, "output": session.relative(destination)}
        data = session.resolve(request["data"])
        combine, output = request.get("combine"), request.get("output")
        if combine is True:
            if output and Path(output).suffix.lower() == ".pdf":
                combine, output = output, None
            else:
                require(not output, "combine: true writes one PDF; give output as a .pdf path or omit it",
                        field="combine", suggestions=[{"combine": True, "output": "all.pdf"},
                                                      {"output": output}])
                combine = session.relative(data.with_name(f"{data.stem}-filled.pdf"))
        combine = session.resolve(combine) if combine else None
        directory = session.resolve(output) if output else None
        result = fill_data(project, data, directory, combine=combine,
                           name=request.get("name", "{row}"), format=request.get("format", "pdf"),
                           skip_invalid=request.get("skip_invalid", False), dry_run=request.get("dry_run", False),
                           check=request.get("check"), **options)
        if result.get("output"):
            result["output"] = session.relative(Path(result["output"]))
        for item in result.get("outputs", []):
            item["output"] = session.relative(Path(item["output"]))
        return result
