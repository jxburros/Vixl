"""One workspace-scoped production API shared by CLI, REST and MCP."""

from pathlib import Path
from .studio import ACTIONS as STUDIO_ACTIONS
from .emoji_workflows import ACTIONS as EMOJI_ACTIONS

from .automation import bounded_object
from .errors import require, VixlError
from .imposition import ACTIONS as IMPOSITION_ACTIONS, FIELD_TYPES as IMPOSITION_FIELD_TYPES
from .links import ACTIONS as LINK_ACTIONS
from .lyrics import REQUEST_FIELDS as LYRIC_FIELDS
from . import media_analysis, natural_guidance
from .logo_package import FIELDS as LOGO_PACKAGE_FIELDS
from .screen_capture import FIELDS as CAPTURE_FIELDS
from .app_animation import FIELDS as APP_ANIMATION_FIELDS

ACTIONS = {
    "check": ({"suite", "mode", "variables", "artboard"}, {"suite"}),
    "act": ({"operations", "suites", "dry_run", "repair"}, {"operations"}),
    "capture": ({"recipe", "bindings", "output"}, {"recipe", "output"}),
    "plan": ({"spec"}, {"spec"}),
    "run": ({"spec", "output"}, {"spec", "output"}),
    "preview": ({"output", "quality", "time"}, {"output"}),
    "library-save": ({"directory", "name", "description", "tags"}, {"directory", "name"}),
    "library-search": ({"directory", "query"}, {"directory"}),
    "library-open": ({"directory", "id", "output"}, {"directory", "id", "output"}),
    "library-place": ({"directory", "id", "name"}, {"directory", "id", "name"}),
    "submit": ({"job", "start", "workers"}, {"job"}),
    "status": ({"id"}, {"id"}),
    "cancel": ({"id"}, {"id"}),
    "resume": ({"id"}, {"id"}),
    "work": ({"workers"}, set()),
    "start": ({"workers"}, set()),
    "film-plan": ({"spec"}, {"spec"}),
    "film-export": ({"spec", "output"}, {"spec", "output"}),
    "organic-catalog": (set(), set()),
    "lyric-video-plan": (LYRIC_FIELDS, {"audio", "lyrics", "template"}),
    "lyric-video-build": (LYRIC_FIELDS, {"audio", "lyrics", "template", "build"}),
    "lyric-video-export": (LYRIC_FIELDS, {"audio", "lyrics", "template", "build", "output"}),
    "form-fill": ({"data", "values", "output", "name", "format", "combine", "mode", "skip_invalid", "dry_run", "check",
                   "unknown", "dpi"}, set()),
    "drawing-report": ({"target"}, {"target"}),
    "drawing-compare": ({"target", "output"}, {"target", "output"}),
    "proof": ({"items", "output", "title", "check", "decisions", "max_size", "overwrite", "overlay"}, {"items", "output"}),
    "logo-package": (LOGO_PACKAGE_FIELDS, {"output"}),
    "repair-layout": ({"checks", "suites", "protected", "minimum_size", "max_candidates", "max_iterations",
                       "time_budget", "dry_run"}, set()),
    "protected-edit": ({"operations", "protect", "regions", "tolerance", "structural", "pixels", "dry_run"},
                       {"operations"}),
    "reproduce": ({"reference", "tolerance", "max_fraction", "lock", "write_lock", "overwrite"}, set()),
    "check-all": ({"documents", "group", "checks", "suite", "suites", "fail_on", "profile", "waivers", "workers",
                   "changed_since", "base",
                   "work", "since_last", "history", "group_checks", "reference", "facts", "outputs", "overwrite"},
                  set()),
    "replace-across": ({"name", "documents", "replace", "dry_run", "suites", "accept", "reject", "decisions", "review",
                        "overwrite", "journal"}, {"replace"}),
}


ACTIONS.update(EMOJI_ACTIONS)
ACTIONS["screen-capture"] = (set(CAPTURE_FIELDS), {"output"})
ACTIONS["app-animation-package"] = (set(APP_ANIMATION_FIELDS), {"states", "default_state", "output"})
ACTIONS.update(natural_guidance.ACTIONS)
ACTIONS.update(media_analysis.ACTIONS)
ACTIONS.update(STUDIO_ACTIONS)
ACTIONS.update(LINK_ACTIONS)
ACTIONS.update(IMPOSITION_ACTIONS)
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

ACTION_FIELD_TYPES["merge-impose"] = IMPOSITION_FIELD_TYPES
ACTION_FIELD_TYPES["screen-capture"] = CAPTURE_FIELDS
ACTION_FIELD_TYPES["app-animation-package"] = APP_ANIMATION_FIELDS
for _module in (media_analysis, natural_guidance):
    for _action in _module.ACTIONS:
        ACTION_FIELD_TYPES[_action] = _module.FIELD_TYPES


LYRIC_TYPES = {
    "build": {**PATH, "description": "The built timeline document (.vixl); an editable keyframed copy of the template. "
              "Export renders an existing build as it is, hand edits included, while it still matches the request."},
    "rebuild": {"type": "boolean", "description": "Export only: build the document again from the template and LRC, "
                "replacing an existing build and discarding hand edits in it."},
    "animation": {"type": "object", "description": "Lyric entry and exit: in, out, duration (ms), distance (px)."},
    "cue_animation": {"type": "object", "description": "How cue-* layers enter, leave and move while their words are sung: "
                      "in, out (as animation; default none, a cut), duration, distance, motion (none or sweep: a swing about "
                      "the layer's pivot), amount (degrees, default 12), period (ms for a back-and-forth, default 2800), "
                      "replay (true: the cue layer's own template keys restart at each window), and cues: per-layer "
                      "overrides of any of these keyed by cue layer name, e.g. {\"cue-cell\": {\"in\": \"slide-in-down\"}}."},
}
for _action in ("lyric-video-plan", "lyric-video-build", "lyric-video-export"):
    ACTION_FIELD_TYPES[_action] = LYRIC_TYPES


def field_types(action):
    from .workflow_schema import properties

    fields = ACTIONS[action][0]
    types = {**properties(action, fields), **ACTION_FIELD_TYPES.get(action, {})}
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
        "help": "docs/production.md; all paths are workspace-relative; submit + start runs durable background work. "
                "definitions.suite is the check-suite object (attach it with the suite-set operation, or pass it "
                "inline to check).",
    }


def dispatch(session, action, request, document=None):
    from .production import Library, plan, run, capture_recipe, write_bytes

    require(action in ACTIONS, "Unknown workflow action", allowed=sorted(ACTIONS))
    allowed, required = ACTIONS[action]
    bounded_object(request, allowed, "Unknown workflow request field")
    require(required <= request.keys(), "Missing workflow fields", required=sorted(required))
    if action == "screen-capture":
        from .screen_capture import capture
        return capture(session, request)
    if action == "app-animation-package":
        from .app_animation import package
        return package(session, request)
    # replace-across's replace is its list of rules; elsewhere replace is a flag.
    for field in ("dry_run",) if action == "replace-across" else ("dry_run", "replace"):
        if field in request:
            require(type(request[field]) is bool, f"{field} must be boolean")
    if action in EMOJI_ACTIONS:
        from .emoji_workflows import dispatch as emoji_dispatch
        return emoji_dispatch(session, action, request, document)
    if action in natural_guidance.ACTIONS:
        return natural_guidance.dispatch(session, action, request, document)
    if action in media_analysis.ACTIONS:
        return media_analysis.dispatch(session, action, request, document)
    if action in LINK_ACTIONS:
        from .links import dispatch as links_dispatch

        return links_dispatch(session, request, document)
    if action in IMPOSITION_ACTIONS:
        from .imposition import dispatch as merge_dispatch

        return merge_dispatch(session, request, document)
    if action in STUDIO_ACTIONS:
        from .studio import dispatch as studio_dispatch
        try:
            return studio_dispatch(session, action, request, document)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VixlError("invalid_request", f"Invalid {action} request: {exc}") from exc
    if action == "plan":
        return plan(request["spec"])
    if action == "organic-catalog":
        from .organic import catalog

        return catalog()
    if action == "form-fill":
        try:
            return form_fill(session, request, document)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VixlError("invalid_request", f"Invalid form-fill request: {exc}",
                            suggestions=["See vixl_workflow_schema actions['form-fill'].properties"]) from exc
    if action == "proof":
        from .proof import proof_page

        for field in ("check", "decisions", "overwrite", "overlay"):
            require(type(request.get(field, False)) is bool, f"{field} must be boolean", field=field)
        result = proof_page(request["items"], request["output"], resolve=session.resolve,
                            title=request.get("title"), check=request.get("check", True),
                            decisions=request.get("decisions", False), max_size=request.get("max_size", 1200),
                            overwrite=request.get("overwrite", False), limits=session.limits,
                            overlay=request.get("overlay", False))
        result["output"] = session.relative(Path(result["output"]))
        return result
    if action == "repair-layout":
        from .layout_repair import repair_layout

        dry_run = request.get("dry_run", True)
        with session.project(write=not dry_run, document=document) as project:
            return repair_layout(project, checks=request.get("checks"), suites=request.get("suites", []),
                                 protected=request.get("protected", []), minimum_size=request.get("minimum_size"),
                                 max_candidates=request.get("max_candidates", 24),
                                 max_iterations=request.get("max_iterations", 4),
                                 time_budget=request.get("time_budget", 20), dry_run=dry_run)
    if action == "protected-edit":
        from .interfaces import service_check
        from .protected_edit import protected_edit

        for field in ("structural", "pixels"):
            require(type(request.get(field, True)) is bool, f"{field} must be boolean", field=field)
        dry_run = request.get("dry_run", False)
        with session.project(write=not dry_run, document=document) as project:
            return protected_edit(project, request["operations"], protect=request.get("protect", []),
                                  regions=request.get("regions", []), tolerance=request.get("tolerance", 0),
                                  structural=request.get("structural", True), pixels=request.get("pixels", True),
                                  dry_run=dry_run, check=service_check)
    if action == "reproduce":
        from .reproduce import read_lock, reproduce, write_lock

        require(type(request.get("overwrite", False)) is bool, "overwrite must be boolean", field="overwrite")
        with session.project(document=document) as project:
            result = {}
            if request.get("write_lock"):
                write_lock(project, session.resolve(request["write_lock"]), overwrite=request.get("overwrite", False))
                result["lock_written"] = request["write_lock"]
            result.update(reproduce(
                project, reference=session.resolve(request["reference"]) if request.get("reference") else None,
                tolerance=request.get("tolerance", 0), max_fraction=request.get("max_fraction", 0.0),
                locked=read_lock(session.resolve(request["lock"])) if request.get("lock") else None,
                limits=session.limits))
            if result.get("reference"):
                result["reference"]["path"] = request["reference"]
            return result
    if action == "check-all":
        from .workspace_checks import run as check_all

        return check_all(session, request)
    if action == "replace-across":
        from .replace_across import run as replace_across

        return replace_across(session, request)
    if action == "logo-package":
        from .logo_package import build

        return build(session, request, document)
    if action in ("drawing-report", "drawing-compare"):
        from .drawing import compare, report

        with session.project(document=document) as project:
            result = report(project, request["target"])
            if action == "drawing-compare":
                destination = session.resolve(request["output"])
                require(destination.suffix.lower() == ".png" and not destination.exists(),
                        "Choose a new .png output", field="output")
                compare(project, request["target"]).save(destination)
                result["output"] = session.relative(destination)
            return result
    if action.startswith("lyric-video-"):
        from . import lyrics

        step = {"lyric-video-plan": lyrics.plan, "lyric-video-build": lyrics.build, "lyric-video-export": lyrics.export}[action]
        return step(request, session.workspace, session.limits)
    if action.startswith("film-"):
        from .film import plan as film_plan, export

        if action == "film-plan":
            return film_plan(request["spec"], session.limits)
        return export(
            request["spec"], session.workspace, session.resolve(request["output"]), limits=session.limits
        )
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
            return library.place(project, request["id"], request["name"])
    if action == "act":
        from .interfaces import service_check

        with session.project(write=not request.get("dry_run", False), document=document) as project:
            return project.act(check=service_check, **request)
    # Release the session/document lock before long read-only production runs.
    with session.project(document=document) as project:
        project = project.clone()
    if action == "check":
        return project.check_suite(**request)
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


def cli(args, options, limits):
    from .commands import Parser
    from .cli import read_json
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
