"""Workflow actions for workspace-wide checks and edits, proofs, reproducibility and delivery."""

from pathlib import Path

from ...errors import require
from .package import FIELDS as PACKAGE_FIELDS, SUMMARY as PACKAGE_SUMMARY

REPRODUCE_FIELDS = {"reference", "tolerance", "max_fraction", "lock", "write_lock", "overwrite", "exports",
                    "verify_exports", "export_tolerance", "export_visual", "frames", "times", "variables", "report"}
ACTIONS = {
    "proof": ({"items", "output", "title", "check", "decisions", "max_size", "overwrite", "overlay"}, {"items", "output"}),
    "protected-edit": ({"operations", "protect", "regions", "tolerance", "structural", "pixels", "dry_run"},
                       {"operations"}),
    "reproduce": (REPRODUCE_FIELDS, set()),
    "package": (set(PACKAGE_FIELDS), {"output"}),
    "check-all": ({"documents", "group", "checks", "suite", "suites", "fail_on", "profile", "waivers", "workers",
                   "changed_since", "base",
                   "work", "since_last", "history", "group_checks", "reference", "facts", "outputs", "overwrite",
                   "notify"},
                  set()),
    "replace-across": ({"name", "documents", "replace", "dry_run", "suites", "accept", "reject", "decisions", "review",
                        "overwrite", "journal"}, {"replace"}),
}
FIELD_TYPES = {
    "reproduce": {
        "exports": {"type": "array", "minItems": 1, "maxItems": 16, "items": {"type": ["string", "object"]},
                    "description": "Exports to record in the lockfile that write_lock writes, or, with lock, "
                                   "requests to verify against the locked ones: 'png', 'jpg:quality=80', "
                                   "'mp4:fps=24' or {format, options}."},
        "verify_exports": {"type": "boolean", "default": False,
                           "description": "With lock: encode each locked export again and compare it, bytes for "
                                          "deterministic formats, decoded pixels within export_tolerance for lossy ones."},
        "export_tolerance": {"type": "integer", "minimum": 0, "maximum": 254, "default": 8,
                             "description": "How far a block average of a lossy export may move (of 255) and still be "
                                            "visually equivalent."},
        "export_visual": {"type": "boolean", "default": False,
                          "description": "Judge every export by its decoded pixels, even PNG, SVG and PDF whose "
                                         "bytes differ (a different zlib or PDF producer)."},
        "frames": {"type": "integer", "minimum": 0, "maximum": 32,
                   "description": "With write_lock: timeline frames to lock, spread over the duration (default 3 for "
                                  "an animated document)."},
        "times": {"type": "array", "maxItems": 32, "items": {"type": ["number", "string"]},
                  "description": "With write_lock: timeline times to lock instead: milliseconds, '1.5s', '50%' or a "
                                 "marker."},
        "variables": {"type": ["object", "array"], "description": "With write_lock or lock: the variable set or "
                      "campaign rows to hash into the lockfile (default: the document's variables)."},
        "report": {"type": "boolean", "default": False,
                   "description": "Return the compact, manifest-ready summary instead of the full result."},
    },
    "package": PACKAGE_FIELDS,
}
SUMMARIES = {
    "package": PACKAGE_SUMMARY,
    "reproduce": "Render and report renderable, environment-matched (lockfile) or reference-verified (reference image "
                 "or locked render hash), with located drift per page, artboard, frame, export setting and tool; a "
                 "lockfile can record exports, and verifying them reports byte_identical and visually_equivalent.",
}


def dispatch(session, action, request, document=None):
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
    if action == "package":
        from .package import build

        return build(session, request)
    if action == "protected-edit":
        from ...io_policy import service_check
        from .protected_edit import protected_edit

        for field in ("structural", "pixels"):
            require(type(request.get(field, True)) is bool, f"{field} must be boolean", field=field)
        dry_run = request.get("dry_run", False)
        with session.project(write=not dry_run, document=document) as project:
            return protected_edit(project, request["operations"], protect=request.get("protect", []),
                                  regions=request.get("regions", []), tolerance=request.get("tolerance", 0),
                                  structural=request.get("structural", True), pixels=request.get("pixels", True),
                                  dry_run=dry_run, validator=service_check)
    if action == "reproduce":
        from .reproduce import alias_notes, covers, read_lock, reproduce, write_lock

        for field in ("overwrite", "verify_exports", "export_visual", "report"):
            require(type(request.get(field, False)) is bool, f"{field} must be boolean", field=field)
        writing, verifying = request.get("write_lock"), request.get("lock")
        exports = request.get("exports")
        require(exports is None or writing or verifying, "exports are recorded by write_lock or verified against a "
                "lock; give one", field="exports")
        require(not (request.get("verify_exports") and not verifying), "verify_exports needs a lock", field="lock")
        require(not (("frames" in request or "times" in request) and not writing),
                "frames and times choose what write_lock records", field="frames")
        with session.project(document=document) as project:
            result = {}
            if writing:
                written = write_lock(project, session.resolve(writing), overwrite=request.get("overwrite", False),
                                     exports=exports, frames=request.get("frames"), times=request.get("times"),
                                     variables=request.get("variables"), resolve=session.resolve,
                                     limits=session.limits)
                result["lock_written"] = writing
                result["lock_covers"] = covers(written)
            outcome = reproduce(
                project, reference=session.resolve(request["reference"]) if request.get("reference") else None,
                tolerance=request.get("tolerance", 0), max_fraction=request.get("max_fraction", 0.0),
                locked=read_lock(session.resolve(verifying)) if verifying else None,
                exports=exports if verifying else None, verify_exports=bool(request.get("verify_exports")),
                export_tolerance=request.get("export_tolerance"), export_visual=request.get("export_visual", False),
                variables=request.get("variables") if verifying else None, resolve=session.resolve,
                limits=session.limits, report=request.get("report", False))
            result.update(outcome)
            if result.get("reference"):
                result["reference"]["path"] = request["reference"]
            if notes := alias_notes(exports):
                result["normalized"] = notes
            return result
    if action == "check-all":
        from .workspace_checks import run

        return run(session, request)
    from .replace_across import run

    return run(session, request)
