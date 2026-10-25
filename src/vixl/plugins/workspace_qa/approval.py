"""Approved baselines: ``approve`` records how a document looks now, and the ``approval`` check reports what changed.

``approve`` renders every view of a document (each page and artboard, or the canvas) and stores, per view, its
render hash and a reference PNG of at most ``THUMBNAIL`` pixels, with the document's state digest, its linked
sources' revisions, who approved it and when. A document's approval lives beside it in ``<name>.vixl.approval/``;
``approve`` of a project group stores every member's in ``.vixl-groups/<group>.approval/``. Approving again
replaces the earlier approval, and ``clear`` removes it. At most ``MAX_VIEWS`` views are recorded.

The ``approval`` check (opt-in by name, and on by itself whenever the standard checks run on a document that has
approval data) reports each view as ``approved`` (the render matches), ``changed`` (a warning to review, with the
changed fraction of the reference and a diff image) or, when asked for by name, a document that was never
approved (info). An unchanged state digest and linked sources settle ``approved`` without rendering.
"""

from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import shutil

from ...errors import VixlError, require

VERSION = 1
MAX_VIEWS = 64
THUMBNAIL = 256
SUFFIX = ".approval"
RECORD = "approval.json"
GROUPS = ".vixl-groups"
MAX_AUTHOR = 100
ENV_AUTHOR = "VIXL_AUTHOR"
APPROVED, CHANGED, NEVER = "approved", "changed", "never-approved"


# Views and digests ------------------------------------------------------------------------------

def _views(project):
    pages = project.state.get("pages") or []
    found = [("page", f"page {number}", {"page": number}) for number in range(1, len(pages) + 1)]
    found += [("artboard", name, {"artboard": name}) for name in (project.state.get("artboards") or {})]
    return found or [("canvas", "canvas", {})]


def views(project):
    """[(kind, name, render options)]: every page, then every artboard, or the canvas alone (at most MAX_VIEWS)."""
    found = _views(project)
    require(len(found) <= MAX_VIEWS, f"An approval covers at most {MAX_VIEWS} pages and artboards; this document has "
            f"{len(found)}", "resource_limit", field="views", limit=MAX_VIEWS)
    return found


def digest(project):
    """The state digest of a document: equal digests draw the same, given the same linked sources."""
    from ...hashing import content_hash

    return content_hash(project.state, default=str)


def _links(project):
    from ...links import fingerprint

    try:
        return [list(item) for item in fingerprint(project)]
    except VixlError:
        return None


def _render(project, options):
    return project.render(**options).convert("RGBA")


def _thumbnail(image):
    from PIL import Image

    small = image.copy()
    small.thumbnail((THUMBNAIL, THUMBNAIL), Image.Resampling.LANCZOS)
    return small


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def author(value=None):
    """Who approves: the request's ``author``, else the ``VIXL_AUTHOR`` environment variable, else ``agent``."""
    value = value if value is not None else os.environ.get(ENV_AUTHOR, "").strip() or "agent"
    require(isinstance(value, str) and 0 < len(value.strip()) <= MAX_AUTHOR and not re.search(r"[\x00-\x1f\x7f]", value),
            f"author is a name of 1-{MAX_AUTHOR} printable characters", field="author")
    return value.strip()


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Recording --------------------------------------------------------------------------------------

def snapshot(project, folder):
    """Render every view of ``project`` and write its reference PNGs under ``folder``. Returns the member record
    (``revision``, ``links``, ``views``) whose ``reference`` paths are relative to ``folder``."""
    from ...production import write_bytes
    from .reproduce import render_hash

    found = []
    for index, (kind, name, options) in enumerate(views(project)):
        image = _render(project, options)
        reference = f"views/{index:03d}.png"
        write_bytes(folder / reference, _png(_thumbnail(image)), replace=True)
        found.append({"kind": kind, "name": name, "render_hash": render_hash(image), "size": list(image.size),
                      "reference": reference})
    return {"revision": digest(project), "links": _links(project), "views": found}


def _replace_folder(folder, build):
    """Build a new approval folder beside ``folder`` and swap it in, so a failed approve keeps the old one."""
    staging = folder.with_name(folder.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        result = build(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    old = folder.with_name(folder.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if folder.exists():
        folder.rename(old)
    staging.rename(folder)
    shutil.rmtree(old, ignore_errors=True)
    return result


def document_folder(path):
    path = Path(path)
    return path.with_name(path.name + SUFFIX)


def group_folder(workspace, name):
    return Path(workspace) / GROUPS / f"{name}{SUFFIX}"


def approve(project, *, who=None):
    """Approve the saved document ``project`` as it looks now (replacing an earlier approval). Returns a summary."""
    from ...production import write_json

    require(getattr(project, "path", None), "Save the document before approving it: the approval is stored beside "
            "the file", field="document")
    who = author(who)
    folder = document_folder(project.path)

    def build(staging):
        record = {"version": VERSION, "document": Path(project.path).name, "who": who, "when": _now(),
                  **snapshot(project, staging)}
        write_json(staging / RECORD, record)
        return record

    record = _replace_folder(folder, build)
    return _summary(record, folder)


def approve_group(session, name, *, who=None):
    """Approve every member of the project group ``name`` into ``.vixl-groups/<name>.approval/``."""
    from ...design import named
    from ...production import read_json, write_json
    from ...project import Project

    name = named(name)
    definition = session.resolve(f"{GROUPS}/{name}.json")
    require(definition.is_file(), f"Unknown project group {name!r}", "not_found", field="group")
    members = read_json(definition)["documents"]
    who = author(who)
    projects = []
    for member in members:
        project = Project.load(session.resolve(member), limits=session.limits)
        project._workspace = session.workspace
        projects.append((member, project))
    for _, project in projects:
        views(project)  # every member must fit the bound before anything is written

    def build(staging):
        record = {"version": VERSION, "group": name, "who": who, "when": _now(), "members": {}}
        for index, (member, project) in enumerate(projects):
            folder = f"m{index:03d}"
            record["members"][member] = {"folder": folder, **snapshot(project, staging / folder)}
        write_json(staging / RECORD, record)
        return record

    folder = session.resolve(f"{GROUPS}/{name}{SUFFIX}")
    record = _replace_folder(folder, build)
    return {"group": name, "who": record["who"], "when": record["when"], "folder": session.relative(folder),
            "documents": [{"document": member, "views": len(entry["views"])}
                          for member, entry in record["members"].items()],
            "views": sum(len(entry["views"]) for entry in record["members"].values())}


def clear(folder):
    """Remove an approval folder. Returns whether there was one."""
    folder = Path(folder)
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True


def _summary(record, folder):
    return {"document": record["document"], "who": record["who"], "when": record["when"],
            "folder": folder.name, "views": [{"kind": v["kind"], "name": v["name"], "size": v["size"]}
                                             for v in record["views"]]}


# Finding an approval ----------------------------------------------------------------------------

class Approval:
    """One document's approval: its record (``who``, ``when``, ``revision``, ``links``, ``views``), the folder its
    references are relative to, and where it came from (``document`` or ``group:NAME``)."""

    def __init__(self, record, folder, source):
        self.record, self.folder, self.source = record, Path(folder), source


def _read(path):
    from ...production import read_json

    try:
        record = read_json(path)
    except (VixlError, OSError):
        return None
    return record if isinstance(record, dict) and record.get("version") == VERSION else None


def _workspace_for(path, workspace):
    """The workspace whose project groups may hold the document's approval: ``workspace`` when the document is in
    it, else the nearest folder above the document with a ``.vixl-groups`` folder."""
    path = Path(path).resolve()
    if workspace and path.is_relative_to(Path(workspace).resolve()):
        return Path(workspace).resolve()
    for parent in list(path.parents)[:12]:
        if (parent / GROUPS).is_dir():
            return parent
    return None


def find(path, workspace=None):
    """The approval of the document at ``path``: its own beside it, else one of a project group it belongs to
    (the newest). None when it was never approved."""
    if not path:
        return None
    path = Path(path).resolve()
    folder = document_folder(path)
    record = _read(folder / RECORD) if (folder / RECORD).is_file() else None
    if record and isinstance(record.get("views"), list):
        return Approval(record, folder, "document")
    root = _workspace_for(path, workspace)
    if root is None or not (root / GROUPS).is_dir():
        return None
    try:
        key = path.relative_to(root).as_posix()
    except ValueError:
        return None
    best = None
    for candidate in sorted((root / GROUPS).glob(f"*{SUFFIX}/{RECORD}")):
        record = _read(candidate)
        entry = (record or {}).get("members", {}).get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("folder"), str):
            continue
        if best is None or record.get("when", "") > best[0].get("when", ""):
            best = (record, entry, candidate.parent)
    if best is None:
        return None
    record, entry, folder = best
    member_folder = (folder / entry["folder"]).resolve()
    if not member_folder.is_relative_to(folder.resolve()):
        return None
    return Approval({**entry, "who": record.get("who"), "when": record.get("when")}, member_folder,
                    f"group:{record.get('group')}")


# Comparing --------------------------------------------------------------------------------------

def _options(view):
    if view.get("kind") == "page":
        return {"page": int(str(view["name"]).split()[-1])}
    if view.get("kind") == "artboard":
        return {"artboard": view["name"]}
    return {}


def status(project, approval, *, only=None, write_diff=False, workspace=None):
    """How ``project`` compares with ``approval``: ``{state, views, changed_fraction, who, when, source}``. Each
    view is approved or changed (with ``changed_fraction`` of its reference and, with ``write_diff``, a ``diff``
    image under the approval's ``diff/`` folder). ``only`` keeps the views that match ``(kind, name)``."""
    from PIL import Image

    from ...image_diff import diff_images
    from .reproduce import render_hash

    record = approval.record
    result = {"who": record.get("who"), "when": record.get("when"), "source": approval.source}
    approved_views = [v for v in record.get("views", []) if only is None or only(v)]
    if record.get("revision") == digest(project) and record.get("links") == _links(project):
        return {"state": APPROVED, **result, "views": [{"name": v["name"], "state": APPROVED} for v in approved_views],
                "changed_fraction": 0.0}
    current = {(kind, name): options for kind, name, options in _views(project)}
    found = []
    for index, view in enumerate(approved_views):
        entry = {"name": view["name"], "kind": view["kind"]}
        if (view["kind"], view["name"]) not in current:
            found.append({**entry, "state": CHANGED, "removed": True, "changed_fraction": 1.0})
            continue
        image = _render(project, _options(view))
        if render_hash(image) == view.get("render_hash"):
            found.append({**entry, "state": APPROVED})
            continue
        entry.update(state=CHANGED)
        reference = (approval.folder / str(view.get("reference", ""))).resolve()
        try:
            require(reference.is_relative_to(approval.folder.resolve()), "approval reference outside its folder")
            with Image.open(reference) as stored:
                before = stored.convert("RGBA")
        except (OSError, ValueError, VixlError):
            found.append({**entry, "changed_fraction": 1.0, "note": "the approved reference image is missing"})
            continue
        picture, stats = diff_images(before, _thumbnail(image))
        entry["changed_fraction"] = round(stats["changed_fraction"], 6)
        if stats.get("changed_region"):
            entry["changed_region"] = stats["changed_region"]
        if write_diff:
            target = approval.folder / "diff" / f"{index:03d}.png"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_png(picture.convert("RGB")))
                entry["diff"] = _shown(target, workspace)
            except OSError:
                pass
        found.append(entry)
    if only is None:
        approved_names = {(v["kind"], v["name"]) for v in approved_views}
        found += [{"name": name, "kind": kind, "state": CHANGED, "added": True, "changed_fraction": 1.0}
                  for kind, name in current if (kind, name) not in approved_names]
    changed = [v for v in found if v["state"] == CHANGED]
    return {"state": CHANGED if changed else APPROVED, **result, "views": found,
            "changed_fraction": max((v.get("changed_fraction", 0.0) for v in changed), default=0.0)}


def _shown(path, workspace):
    if workspace:
        try:
            return Path(path).resolve().relative_to(Path(workspace).resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def report(project, *, workspace=None, write_diff=False):
    """The approval state of a saved document: ``{state: approved|changed|never-approved, ...}``."""
    workspace = workspace or getattr(project, "_workspace", None)
    found = find(getattr(project, "path", None), workspace)
    if found is None:
        return {"state": NEVER}
    return status(project, found, write_diff=write_diff, workspace=workspace)


# The check hook ---------------------------------------------------------------------------------

def check(checks, document=None, issue=None, artboard=None, page=None, **context):
    """The ``approval`` design check: by name, or with the standard checks when the document has approval data."""
    from ...checks import CHECKS

    named = "approval" in checks
    if not named and not set(CHECKS) <= set(checks):
        return
    path = getattr(document, "path", None)
    workspace = getattr(document, "_workspace", None)
    found = find(path, workspace) if document is not None else None
    if found is None:
        if named:
            issue("approval", "info", "This document has never been approved; vixl approve records how it looks "
                  "now so later changes are flagged for review", code=NEVER, approval=NEVER)
        return
    only = None
    if artboard is not None:
        only = lambda view: view["kind"] == "artboard" and view["name"] == artboard  # noqa: E731
    elif page is not None and isinstance(page, int):
        only = lambda view: view["kind"] == "page" and view["name"] == f"page {page}"  # noqa: E731
    try:
        result = status(document, found, only=only, write_diff=True, workspace=workspace)
    except VixlError as exc:
        issue("approval", "warning", f"The document could not be compared with its approval: {exc}", code="error",
              approval="error")
        return
    who, when = result.get("who"), result.get("when")
    if result["state"] == APPROVED:
        if named:
            issue("approval", "info", f"Approved by {who} on {when}; the render still matches", code=APPROVED,
                  approval=APPROVED, approved_by=who, approved_at=when)
        return
    for view in result["views"]:
        if view["state"] != CHANGED:
            continue
        what = ("was removed" if view.get("removed") else "is new" if view.get("added") else
                f"changed: {view.get('changed_fraction', 0):.1%} of its approved preview differs")
        issue("approval", "warning", f"{view['name']} {what} since {who} approved it on {when}; review it, then "
              "approve again (vixl approve) or revert", code=CHANGED, approval=CHANGED, view=view["name"],
              changed_fraction=view.get("changed_fraction", 1.0), approved_by=who, approved_at=when,
              **({"diff": view["diff"]} if view.get("diff") else {}),
              **({"changed_region": view["changed_region"]} if view.get("changed_region") else {}))


# Reports of other actions -----------------------------------------------------------------------

def approved_changes(session, candidates):
    """``approved_members_changed`` of a dry run: the approved members (``{path: candidate Project}``) whose
    candidate no longer matches its approval, with the views that changed."""
    found = []
    for path, candidate in candidates.items():
        approval = find(path, session.workspace)
        if approval is None:
            continue
        result = status(candidate, approval, workspace=session.workspace)
        if result["state"] == CHANGED:
            found.append({"document": session.relative(Path(path)), "approved_by": result["who"],
                          "approved_at": result["when"], "changed_fraction": result["changed_fraction"],
                          "views": [v["name"] for v in result["views"] if v["state"] == CHANGED]})
    return sorted(found, key=lambda item: item["document"])


def production_report(project, spec, report):
    """The ``production-report`` hook: a campaign run from an approved template lists the template's approved views
    that changed since approval, so outputs made from an unapproved template are visible."""
    approval = find(getattr(project, "path", None), getattr(project, "_workspace", None))
    if approval is None:
        return
    boards = spec.get("artboards")
    only = (lambda view: view["kind"] != "artboard" or view["name"] in boards) if boards else None
    try:
        result = status(project, approval, only=only, workspace=getattr(project, "_workspace", None))
    except VixlError as exc:
        report["approved_members_changed"] = [{"document": Path(project.path).name, "error": str(exc)[:300]}]
        return
    changed = [view["name"] for view in result["views"] if view["state"] == CHANGED]
    report["approved_members_changed"] = ([{"document": Path(project.path).name, "views": changed,
                                            "changed_fraction": result["changed_fraction"],
                                            "approved_by": result["who"], "approved_at": result["when"]}]
                                          if changed else [])


# Workflow action --------------------------------------------------------------------------------

def run(session, request, document=None):
    """The ``approve`` workflow action: the open document (or ``document``), or a project ``group``; ``clear``
    removes the approval instead."""
    from ...design import named

    require(type(request.get("clear", False)) is bool, "clear must be boolean", field="clear")
    group = request.get("group")
    if group is not None:
        require(isinstance(group, str) and group, "group is a project group name", field="group")
        if request.get("clear"):
            folder = session.resolve(f"{GROUPS}/{named(group)}{SUFFIX}")
            return {"group": named(group), "cleared": clear(folder), "folder": session.relative(folder)}
        return approve_group(session, group, who=request.get("author"))
    with session.project(document=document) as project:
        require(getattr(project, "path", None), "Save the document before approving it", field="document")
        if request.get("clear"):
            folder = document_folder(project.path)
            return {"document": Path(project.path).name, "cleared": clear(folder), "folder": folder.name}
        return approve(project, who=request.get("author"))
