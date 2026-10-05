"""One workspace-scoped production API shared by CLI, REST and MCP."""

from pathlib import Path
from .studio import ACTIONS as STUDIO_ACTIONS

from .automation import bounded_object
from .errors import require, VixlError
from .lyrics import REQUEST_FIELDS as LYRIC_FIELDS

ACTIONS = {
    "check": ({"suite", "mode", "variables", "artboard"}, {"suite"}),
    "act": ({"operations", "suites", "dry_run"}, {"operations"}),
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
}


ACTIONS.update(STUDIO_ACTIONS)

def describe():
    return {
        "version": 1,
        "actions": {k: {"fields": sorted(v[0]), "required": sorted(v[1])} for k, v in ACTIONS.items()},
        "help": "docs/production.md; all paths are workspace-relative; submit + start runs durable background work",
    }


def dispatch(session, action, request, document=None):
    from .production import Library, plan, run, capture_recipe, write_bytes

    require(action in ACTIONS, "Unknown workflow action", allowed=sorted(ACTIONS))
    allowed, required = ACTIONS[action]
    bounded_object(request, allowed, "Unknown workflow request field")
    require(required <= request.keys(), "Missing workflow fields", required=sorted(required))
    for field in ("dry_run", "replace"):
        if field in request:
            require(type(request[field]) is bool, f"{field} must be boolean")
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
        return form_fill(session, request, document)
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


def form_fill(session, request, document=None):
    """Fill the open form: ``values`` and ``output`` for one copy, or ``data`` (a CSV) with an
    ``output`` directory or a ``combine`` PDF. Nothing is written to the document."""
    from .forms import check_values, fill, fill_data

    for field in ("skip_invalid",):
        if field in request:
            require(type(request[field]) is bool, f"{field} must be boolean")
    require(("data" in request) != ("values" in request), "Give values (one copy) or data (a CSV), not both",
            field="data")
    with session.project(document=document) as project:
        options = {key: request[key] for key in ("mode", "unknown", "dpi") if key in request}
        if "values" in request:
            if request.get("dry_run"):
                _, _, errors = check_values(project, request["values"], unknown=request.get("unknown", "error"))
                return {"dry_run": True, "valid": not errors, "errors": errors}
            require(isinstance(request.get("output"), str), "Give an output path", field="output")
            destination = session.resolve(request["output"])
            result = fill(project, request["values"], destination, format=request.get("format"), **options)
            return {**result, "output": session.relative(destination)}
        combine = session.resolve(request["combine"]) if request.get("combine") else None
        directory = session.resolve(request["output"]) if request.get("output") else None
        result = fill_data(project, session.resolve(request["data"]), directory, combine=combine,
                           name=request.get("name", "{row}"), format=request.get("format", "pdf"),
                           skip_invalid=request.get("skip_invalid", False), dry_run=request.get("dry_run", False),
                           check=request.get("check"), **options)
        if result.get("output"):
            result["output"] = session.relative(Path(result["output"]))
        for item in result.get("outputs", []):
            item["output"] = session.relative(Path(item["output"]))
        return result
