"""What service and agent callers may read and write: the operation policy (``service_check``), export
destinations inside a workspace (``export_file``), uploads (``decode_upload``) and JSON input (``read_json``).

Domain modules (workflows, compose, adapt, plugins) apply these policies too, so they live here rather than in
the CLI, REST or MCP modules that first needed them.
"""

import base64
import binascii
import json
import os
import sys

from .assets import read_bounded
from .errors import VixlError, require
from .fileio import file_lock


def service_check(operation, fonts=None):
    """Restrictions for remote/agent callers, applied after normalization so aliases such as
    ``font_family`` cannot bypass them. Service clients import images explicitly; they cannot
    read arbitrary server files, enable plugins, or resolve linked assets or font files.
    ``fonts`` (the names a document allows, see ``service_fonts``) lets operations on a document
    name a registered font or role; without it any ``font`` is refused."""
    from .constants import EFFECTS
    from .operations import OPERATION_TYPES

    kind = operation.get("type")
    blocked = ("linked",) if fonts is not None else ("linked", "font", "display_font")
    require(
        not any(k in operation for k in blocked)
        and ("path" not in operation or (kind in ("text-layout", "shape", "paint") or (kind == "select" and operation.get("shape") == "path"))),
        "Filesystem fields (path, linked, font files) are unavailable through services; "
        "import images with import-image and reference the returned asset"
        + ("" if fonts is not None else "; fonts are named only in operations applied to a document, by registered name or role"),
        "forbidden",
        field=next((k for k in ("path", *blocked) if k in operation), None),
    )
    if fonts is not None:
        from .service_fonts import check_fonts

        check_fonts(operation, fonts)
    require(kind in set(OPERATION_TYPES) | set(EFFECTS), "Unsupported service operation", field="type")
    if kind == "effect":
        import difflib

        name = operation.get("name")
        close = difflib.get_close_matches(str(name), EFFECTS, 2, 0.5)
        require(
            name in EFFECTS,
            f"Unknown effect {name!r}"
            + (f"; did you mean {' or '.join(map(repr, close))}?" if close else "; see allowed for built-in effects"),
            "forbidden",
            field="name",
            allowed=list(EFFECTS),
            suggestions=close,
        )
    if kind == "mask":
        require(operation.get("action") != "import", "Import masks using embedded assets", "forbidden")


EXPORT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".avif", ".svg", ".pdf", ".ico", ".html", ".htm", ".pptx", ".psd",
                   ".ttf", ".otf", ".woff", ".woff2",
                   ".vixl")


def export_file(session, path, overwrite=False, document=None, **options):
    from .fileio import temporary

    destination = session.resolve(path)
    require(
        destination.suffix.lower() in EXPORT_SUFFIXES,
        "Choose a PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML, PPTX or PSD filename, a TTF, OTF, WOFF or WOFF2 "
        "font (the document's font design), or .vixl with isolate",
        field="path",
    )
    require(destination.suffix.lower() != ".vixl" or options.get("isolate"),
            "A .vixl export writes a portable object document: pass isolate=[OBJECT]", field="path")
    require(destination.suffix.lower() != ".vixl" or not (options.get("check") or options.get("spec") is not None),
            "check and spec verify delivered files (image, PDF, PowerPoint, HTML, SVG), not .vixl objects",
            field="check")
    if options.get("dry_run"):
        from .call_limits import of, quote

        with session.project(document=document) as project:
            return quote(project, destination.suffix[1:], options, of(session))
    with file_lock(str(destination)):
        require(
            overwrite or not destination.exists(),
            "Destination already exists; set overwrite=true",
            field="path",
        )
        fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".pdf": "PDF", ".ico": "ICO"}.get(
            destination.suffix.lower(), destination.suffix[1:].upper()
        )
        report = {}
        with session.project(document=document) as project:
            from .call_limits import check_export, of

            if destination.suffix.lower() == ".vixl":
                from .objects import portable_bytes

                from .check_results import delivery

                options.pop("dry_run", None)
                delivery(project, report, strict=options.pop("strict", False),
                         check_status=options.pop("check_status", None))
                data = portable_bytes(project, options, report)
                fmt = "VIXL"
            else:
                check_export(of(session), project, fmt, options)
                data = project.export(format=fmt, report=report, **options)
        session.make_parent(destination)
        fd, temporary_path = temporary(
            destination.parent, like=destination if destination.exists() else None
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                os.replace(temporary_path, destination)
            else:
                # Atomic no-clobber publication, including non-Vixl writers.
                os.link(temporary_path, destination)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
    if report.get("export_check"):
        report["export_check"] = {"path": session.relative(destination), **report["export_check"]}
    return {"path": session.relative(destination), "format": fmt, "bytes": len(data), **report,
            "outcome": export_outcome(report)}


def export_outcome(report):
    """A written export executed. Without ``check``/``spec`` it is not validated and its warnings need review; with
    them the export check (export_checks.verify) validates the file, while the design still needs vixl_check."""
    from .outcomes import make

    warnings = [str(item) for item in report.get("warnings", [])]
    verified = report.get("export_check")
    if verified:
        outcome = verified["outcome"]
        return make("completed", outcome["validation"],
                    [*outcome["review_reasons"], "the export check read the file back; design checks and suites "
                     "are separate (vixl_check)", *warnings], validated_by=outcome.get("validated_by", ()))
    status = report.get("last_check")
    reason = (f"last design check: {status['fix']} fix, {status['review']} review; export file not verified"
              if isinstance(status, dict) else "no current design check: run vixl_check and the suites first")
    return make("completed", "not_run", [reason, *warnings])


def decode_upload(data_base64, limit):
    require(isinstance(data_base64, str) and data_base64, "data_base64 must be a non-empty string")
    payload = data_base64.split(",", 1)[1] if data_base64.startswith("data:") else data_base64
    payload = "".join(payload.split())
    require(len(payload) <= limit * 4 // 3 + 8, "Image exceeds byte limit", "resource_limit")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VixlError("invalid_image", "data_base64 is not valid base64", field="data_base64") from exc


def read_json(path):
    limit = 64 * 1024 * 1024
    inline = isinstance(path, str) and path.lstrip().startswith(("{", "["))
    text = path if inline else sys.stdin.read(limit + 1) if path == "-" else read_bounded(path, limit).decode()
    require(len(text.encode("utf-8")) <= limit, "JSON input exceeds the 64 MiB batch limit", "resource_limit")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        source = "inline JSON" if inline else "stdin" if path == "-" else str(path)
        raise VixlError("invalid_json", f"{source}: line {exc.lineno} column {exc.colno}: {exc.msg}",
                        **({} if inline or path == "-" else {"path": str(path)})) from exc
    except ValueError as exc:
        raise VixlError("invalid_json", str(exc)) from exc
