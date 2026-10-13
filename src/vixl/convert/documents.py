"""Convert ``.vixl`` archives saved by older releases: the archive, the history and every revision's state."""

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .. import __version__
from ..errors import VixlError, require
from . import rules as rule_table
from .strokes import engine_model

LOOKS = ("preserve", "current")
FOLDERS = ("assets", "masks", "fonts", "sources", "emoji-sources")
MANIFEST_KEYS = ("format_version", "vixl_version", "state", "nodes", "head", "branches", "checkpoints",
                 "current_branch", "redo_stack", "transaction", "asset_hashes")


def read_archive(path, limits=None):
    """``(manifest, assets)`` of a ``.vixl`` file of any format version, with the same member and size checks as
    opening one."""
    from ..model import Limits

    limits = limits or Limits()
    path = Path(path)
    require(path.is_file(), f"Document does not exist: {path}", "not_found", field="path")
    require(path.stat().st_size <= limits.max_project_bytes, "Project exceeds byte limit", "resource_limit")
    try:
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            entries = archive.infolist()
            require(len(entries) <= 10000, "Too many archive entries", "resource_limit")
            require(sum(entry.file_size for entry in entries) <= limits.max_project_bytes,
                    "Expanded project exceeds byte limit", "resource_limit")
            names = [entry.filename for entry in entries]
            require("project.json" in names, "Not a Vixl document: the archive has no project.json", "invalid_project")
            for name in names:
                parts = name.split("/")
                require(name == "project.json" or (len(parts) == 2 and parts[0] in FOLDERS
                                                   and parts[1] not in ("", ".", "..") and "\\" not in name),
                        f"Unsafe or unsupported archive member: {name}", "invalid_project")
            manifest = json.loads(archive.read("project.json"))
            assets = {name: archive.read(name) for name in names if name != "project.json"}
    except zipfile.BadZipFile as exc:
        raise VixlError("invalid_project", "Not a Vixl document: the file is not a ZIP archive") from exc
    except json.JSONDecodeError as exc:
        raise VixlError("invalid_project", f"project.json is not JSON: {exc}") from exc
    require(isinstance(manifest, dict) and isinstance(manifest.get("state"), dict),
            "project.json has no document state", "invalid_project")
    return manifest, assets


def scratch(state, assets):
    """A project over ``state`` for colour, font and text measurement (never saved)."""
    from ..project import Project

    project = Project(1, 1)
    project.state = state
    project.assets = dict(assets)
    return project


def convert_state(state, assets, *, look="preserve", saved=None, stroke_model=None, quiet=False):
    """Convert one document state in place; returns the rules' context (its ``changes`` and ``warnings``)."""
    require(look in LOOKS, f"look is one of {', '.join(LOOKS)}", field="look")
    ctx = rule_table.Context(look, saved, scratch(state, assets), stroke_model or engine_model(), quiet=quiet)
    for _, rule in rule_table.RULES:
        rule(ctx, state)
    return ctx


def _states(nodes):
    """Every revision's full state, rebuilt from its nearest snapshot."""
    from ..history import patch

    states = {}
    for ident in nodes:
        chain, cursor = [], ident
        while cursor not in states and "state" not in nodes[cursor]:
            chain.append(cursor)
            cursor = nodes[cursor].get("parent")
            require(cursor in nodes and len(chain) <= len(nodes), "Invalid history chain", "invalid_project")
        if cursor not in states:
            states[cursor] = deepcopy(nodes[cursor]["state"])
        state = states[cursor]
        for node in reversed(chain):
            state = patch(state, nodes[node]["delta"])
            states[node] = state
    return states


def _rebuild(nodes, states):
    """Nodes holding ``states``: a snapshot every SNAPSHOT_INTERVAL revisions, deltas between them."""
    from ..history import diff
    from ..project import SNAPSHOT_INTERVAL

    order, placed = [], set()
    pending = list(nodes)
    while pending:
        remaining = []
        for ident in pending:
            parent = nodes[ident].get("parent")
            if parent is None or parent in placed:
                order.append(ident)
                placed.add(ident)
            else:
                remaining.append(ident)
        require(len(remaining) < len(pending), "Invalid or cyclic history", "invalid_project")
        pending = remaining
    rebuilt, depth = {}, {}
    for ident in order:
        old = nodes[ident]
        node = {key: deepcopy(value) for key, value in old.items() if key not in ("state", "delta")}
        parent = old.get("parent")
        if parent is None or depth[parent] + 1 >= SNAPSHOT_INTERVAL:
            node["state"] = deepcopy(states[ident])
            depth[ident] = 0
        else:
            node["delta"] = diff(states[parent], states[ident])
            depth[ident] = depth[parent] + 1
        rebuilt[ident] = node
    return {ident: rebuilt[ident] for ident in nodes}


def convert_manifest(manifest, assets, *, look="preserve", history="keep", saved_by=None, stroke_model=None):
    """``(new_manifest, report)`` for a ``project.json`` value saved by any earlier release."""
    require(history in ("keep", "drop"), "history is keep or drop", field="history")
    manifest = deepcopy(manifest)
    version = saved_by or manifest.get("vixl_version")
    saved = rule_table.parse_version(version)
    model = stroke_model or engine_model()
    changes, warnings = [], []
    current = saved is not None and saved >= rule_table.CURRENT_SINCE
    fmt = manifest.get("format_version")
    from ..project import FORMAT_VERSION

    require(fmt in (1, FORMAT_VERSION), f"Unknown archive format {fmt!r}; this kit reads formats 1 and "
            f"{FORMAT_VERSION}", "invalid_project")
    if fmt != FORMAT_VERSION:
        changes.append({"change": "archive-format", "field": "format_version", "before": fmt,
                        "after": FORMAT_VERSION, "reason": f"Archives are format {FORMAT_VERSION}; the layout of "
                        "project.json is otherwise the same"})
    for key in sorted(set(manifest) - set(MANIFEST_KEYS)):
        value = manifest.pop(key)
        changes.append({"change": "manifest-fields", "field": key, "before": value,
                        "reason": "upgraded_from belonged to the removed vixl upgrade command" if key == "upgraded_from"
                        else "Not part of the current file format"})

    transaction = manifest.get("transaction")
    if isinstance(transaction, dict) and isinstance(transaction.get("state"), dict):
        manifest["state"] = transaction["state"]  # what rollback restores: the last committed state
    state = manifest["state"]
    if not current:
        # A document saved by a current release needs no state rule; its archive is still normalized.
        ctx = convert_state(state, assets, look=look, saved=saved, stroke_model=model)
        changes += ctx.changes
        warnings += ctx.warnings

    nodes, head = manifest.get("nodes") or {}, manifest.get("head")
    kept = history == "keep" and head in nodes
    if kept:
        try:
            states = {}
            # Revisions rebuilt from deltas can share parts, so each one is converted on its own copy.
            for ident, revision in _states(nodes).items():
                revision = deepcopy(revision)
                if ident != head and not current:
                    convert_state(revision, assets, look=look, saved=saved, stroke_model=model, quiet=True)
                states[ident] = revision
            states[head] = deepcopy(state)
            nodes = _rebuild(nodes, states)
        except (VixlError, KeyError, TypeError, ValueError, AttributeError) as exc:
            kept = False
            warnings.append({"change": "history", "reason": f"The undo history could not be converted ({exc}); "
                             "the document starts a new history at its current state"})
    revisions = {"revisions": len(nodes), "kept": kept}
    if kept:
        redo_stack = [ref for ref in manifest.get("redo_stack") or [] if ref in nodes]
        branches = {k: v for k, v in (manifest.get("branches") or {}).items() if v in nodes}
        checkpoints = {k: v for k, v in (manifest.get("checkpoints") or {}).items() if v in nodes}
        current_branch = manifest.get("current_branch")
    else:
        head = head if isinstance(head, str) and head.startswith("rev_") else "rev_converted"
        nodes = {head: {"id": head, "parent": None, "operations": [], "label": "Converted", "state":
                        deepcopy(state)}}
        redo_stack, checkpoints = [], {}
        branches, current_branch = {"main": head}, "main"
    if transaction is not None:
        warnings.append({"change": "transaction", "reason": "The document was saved inside an open transaction; "
                         "it was rolled back to the last committed state"})
    new = {
        "format_version": FORMAT_VERSION,
        "vixl_version": __version__,
        "state": state,
        "nodes": nodes,
        "head": head,
        "branches": branches,
        "checkpoints": checkpoints,
        "current_branch": current_branch,
        "redo_stack": redo_stack,
        "transaction": None,
        "asset_hashes": {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()},
    }
    report = {"saved_by": version, "look": look, "stroke_model": model, "history": revisions, "changes": changes,
              "warnings": warnings}
    return new, report


def write_archive(path, manifest, assets):
    encoded = json.dumps(manifest, allow_nan=False, separators=(",", ":")).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", encoded)
        for name, data in sorted(assets.items()):
            archive.writestr(name, data)


def verify(path):
    """Open the converted file with the current code and check it against the published schema."""
    from ..document_schema import validate_manifest
    from ..project import Project

    Project.load(path)
    with zipfile.ZipFile(path) as archive:
        errors = validate_manifest(json.loads(archive.read("project.json")))
    require(not errors, "The converted document does not match the file format schema: " + "; ".join(errors[:5]),
            "invalid_project")


def convert_file(source, output=None, *, look="preserve", dry_run=False, overwrite=False, history="keep",
                 saved_by=None, stroke_model=None):
    """Convert one ``.vixl`` file. ``output`` defaults to ``NAME-converted.vixl`` beside the source; an existing
    output is replaced only with ``overwrite``. ``dry_run`` converts and checks without writing. Returns the report:
    ``{source, output, saved_by, look, changes, warnings, counts}``."""
    source = Path(source)
    output = Path(output) if output else source.with_name(source.stem + "-converted.vixl")
    require(output.suffix == ".vixl", "The converted document's name must end in .vixl", field="output")
    if not dry_run:
        require(overwrite or not output.exists(), f"{output} exists; pass overwrite=True (--overwrite) to replace it",
                "output_exists", field="output")
        require(output.resolve() != source.resolve(), "Write the converted document to a new file", "output_exists",
                field="output")
    manifest, assets = read_archive(source)
    converted, report = convert_manifest(manifest, assets, look=look, history=history, saved_by=saved_by,
                                         stroke_model=stroke_model)
    folder = output.parent if not dry_run else None
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(suffix=".vixl", dir=folder)
    os.close(handle)
    try:
        write_archive(temporary, converted, assets)
        verify(temporary)
        if not dry_run:
            os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"source": str(source), "output": None if dry_run else str(output), "dry_run": dry_run, **report,
            "counts": {"changes": len(report["changes"]), "warnings": len(report["warnings"])}}


def convert_project(source, **options):
    """A converted :class:`vixl.project.Project` for an old ``.vixl`` file, without writing anything (the report is
    on ``project.conversion``)."""
    from ..project import Project

    handle, temporary = tempfile.mkstemp(suffix=".vixl")
    os.close(handle)
    os.unlink(temporary)
    try:
        report = convert_file(source, temporary, **{**options, "dry_run": False, "overwrite": False})
        project = Project.load(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    project.path = None
    project._revision = None
    report["output"] = None
    project.conversion = report
    return project


def convert_directory(source, out, *, look="preserve", dry_run=False, overwrite=False, history="keep",
                      saved_by=None, stroke_model=None):
    """Convert every ``.vixl`` under ``source`` into the same relative path under ``out``. A file that fails is
    reported and the others still convert."""
    source, out = Path(source), Path(out)
    require(source.is_dir(), f"Not a folder: {source}", "not_found", field="path")
    require(out.resolve() != source.resolve() and source.resolve() not in out.resolve().parents,
            "Write converted documents to a folder outside the source folder", field="out")
    reports, failed = [], []
    for path in sorted(source.rglob("*.vixl")):
        target = out / path.relative_to(source)
        try:
            reports.append(convert_file(path, target, look=look, dry_run=dry_run, overwrite=overwrite,
                                        history=history, saved_by=saved_by, stroke_model=stroke_model))
        except VixlError as exc:
            failed.append({"source": str(path), "error": exc.code, "message": str(exc)})
    settings = source / ".vixl" / "variety.json"
    extra = []
    if settings.is_file():
        extra.append(convert_settings(settings, out / ".vixl" / "variety.json", dry_run=dry_run, overwrite=overwrite))
    return summarize(reports, failed, extra)


def convert_settings(source, output, *, dry_run=False, overwrite=False):
    """``.vixl/variety.json`` without the removed ``house_style`` key."""
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    report = {"source": str(source), "output": None if dry_run else str(output), "changes": [], "warnings": []}
    if isinstance(data, dict) and "house_style" in data:
        report["changes"].append({"change": "house-style-version", "field": "house_style",
                                  "before": data.pop("house_style"),
                                  "reason": "Workspaces no longer pin a house-style version"})
    if not dry_run:
        output = Path(output)
        require(overwrite or not output.exists(), f"{output} exists; pass --overwrite to replace it", "output_exists",
                field="output")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    report["counts"] = {"changes": len(report["changes"]), "warnings": 0}
    return report


def summarize(reports, failed=(), extra=()):
    """The result of converting several files: each file's report and totals by change ID."""
    reports = [*reports, *extra]
    by_change = {}
    for report in reports:
        for entry in report["changes"]:
            by_change[entry["change"]] = by_change.get(entry["change"], 0) + 1
    return {
        "converted": reports,
        "failed": list(failed),
        "summary": {"files": len(reports) + len(failed), "converted": len(reports), "failed": len(failed),
                    "changes": sum(len(r["changes"]) for r in reports),
                    "warnings": sum(len(r["warnings"]) for r in reports),
                    "by_change": dict(sorted(by_change.items()))},
    }
