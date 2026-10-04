"""Workspace branches and three-way document merges with explicit conflict resolution."""

from contextlib import ExitStack
from copy import deepcopy

from .errors import require
from .fileio import file_lock
from .design import named
from .production import read_json, write_json, file_digest

MISSING = object()


def merge_states(base, ours, theirs, resolutions=None):
    """Merge by stable layer ID and field; never silently overwrite concurrent edits."""
    conflicts = []
    resolutions = resolutions or {}
    require(
        isinstance(resolutions, dict) and all(v in ("ours", "theirs") for v in resolutions.values()),
        "Resolutions map conflict paths to ours or theirs",
    )

    def merge(b, o, t, path):
        if o == t or t == b:
            return deepcopy(o) if o is not MISSING else MISSING
        if o == b:
            return deepcopy(t) if t is not MISSING else MISSING
        if b is MISSING and isinstance(o, dict) and isinstance(t, dict):
            b = {}
        if all(isinstance(v, dict) for v in (b, o, t)):
            result = {}
            for key in sorted(set(b) | set(o) | set(t)):
                value = merge(
                    b.get(key, MISSING),
                    o.get(key, MISSING),
                    t.get(key, MISSING),
                    path + "/" + key.replace("~", "~0").replace("/", "~1"),
                )
                if value is not MISSING:
                    result[key] = value
            return result
        choice = resolutions.get(path)
        if choice:
            value = o if choice == "ours" else t
            return deepcopy(value) if value is not MISSING else MISSING
        conflicts.append(
            {
                "path": path,
                "base": None if b is MISSING else b,
                "ours": None if o is MISSING else o,
                "theirs": None if t is MISSING else t,
                "deleted": {"base": b is MISSING, "ours": o is MISSING, "theirs": t is MISSING},
            }
        )
        return deepcopy(o) if o is not MISSING else MISSING

    documents = []
    for state in (base, ours, theirs):
        value = deepcopy(state)
        value.pop("active_layer", None)
        value["layers"] = {layer["id"]: layer for layer in value["layers"]}
        documents.append(value)
    result = merge(*documents, "")
    ids = set(result["layers"])
    orders = [
        [layer["id"] for layer in state["layers"] if layer["id"] in ids] for state in (base, ours, theirs)
    ]
    common = set(orders[0]) & set(orders[1]) & set(orders[2])
    shared = [[ident for ident in order if ident in common] for order in orders]
    order = merge(*shared, "/layer_order")
    # Insert additions beside their nearest surviving predecessor, preserving each branch's order.
    for sequence in orders[1:]:
        previous = None
        for ident in sequence:
            if ident not in order:
                index = order.index(previous) + 1 if previous in order else 0
                order.insert(index, ident)
            previous = ident
    result["layers"] = [result["layers"][ident] for ident in order]
    result["active_layer"] = (
        ours.get("active_layer") if ours.get("active_layer") in ids else (order[-1] if order else None)
    )
    return result, conflicts


def manifest_path(session, branch):
    named(branch)
    return session.resolve(f".vixl-branches/{branch}.json")


def dispatch(session, action, request, document=None):
    from .project import Project
    from .validation import check_state
    from .changes import compact_changes

    if action == "branch-list":
        directory = session.resolve(".vixl-branches")
        return {"branches": [read_json(session.resolve(path)) for path in sorted(directory.glob("*.json"))]}
    branch = request["branch"]
    path = manifest_path(session, branch)
    if action == "branch-fork":
        path.parent.mkdir(parents=True, exist_ok=True)
        output = session.resolve(request["output"])
        base_path = session.resolve(f".vixl-branches/{branch}.base.vixl")
        require(
            output.suffix == ".vixl" and output.parent.exists(),
            "Choose a .vixl output in an existing directory",
        )
        require(output != base_path, "Branch output cannot overwrite its merge base")
        with session._mutex, file_lock(str(path)):
            require(not path.exists() and not base_path.exists(), "Branch already exists")
            with session.project(document=document) as original:
                require(original.transaction is None, "Commit the transaction before branching")
                source = session.relative(original.path)
                base = original.clone()
            with file_lock(str(output)):
                require(not output.exists(), "Branch output already exists")
                base.path, base._revision = None, None
                base.save(base_path)
                base.path, base._revision = None, None
                base.save(output)
            manifest = {
                "version": 1,
                "branch": branch,
                "source": source,
                "base": session.relative(base_path),
                "base_hash": file_digest(base_path),
                "output": session.relative(output),
                "author": request.get("author", "agent"),
                "status": "open",
            }
            write_json(path, manifest)
            return manifest
    require(path.is_file(), "Unknown branch")
    with session._mutex, file_lock(str(path)):
        manifest = read_json(path)
        if action == "branch-status":
            return manifest
        require(manifest["status"] == "open", "Branch has already been merged; fork a new branch")
        if document:
            require(
                session.resolve(document) == session.resolve(manifest["source"]),
                "Branch belongs to a different source document",
            )
        source, output = session.resolve(manifest["source"]), session.resolve(manifest["output"])
        base_path = session.resolve(manifest["base"])
        require(len({source, output, base_path}) == 3, "Invalid branch paths")
        with ExitStack() as stack:
            for target in sorted([source, output, base_path]):
                stack.enter_context(file_lock(str(target)))
            require(
                file_digest(base_path) == manifest.get("base_hash"),
                "Branch merge base was changed",
                "stale_revision",
            )
            ours, theirs, base = (Project.load(p, limits=session.limits) for p in (source, output, base_path))
            require(
                ours.transaction is None and theirs.transaction is None, "Commit transactions before merging"
            )
            if branch in ours.state.get("merged_branches", []):
                manifest.update(status="merged", head=ours.head)
                write_json(path, manifest)
                return manifest
            merged, conflicts = merge_states(base.state, ours.state, theirs.state, request.get("resolutions"))
            result = {
                "branch": branch,
                "source_head": ours.head,
                "branch_head": theirs.head,
                "conflicts": conflicts,
                "can_merge": not conflicts,
                "success": not conflicts,
                "dry_run": request.get("dry_run", True),
            }
            if conflicts:
                return result
            candidate = ours.clone()
            candidate.state = merged
            for name, data in theirs.assets.items():
                require(
                    name not in candidate.assets or candidate.assets[name] == data,
                    "Conflicting asset bytes",
                    "merge_conflict",
                )
                candidate.assets[name] = data
            check_state(candidate, candidate.state)
            candidate.inspect()  # Validate constraints and combined layer references.
            result["changes"] = compact_changes(ours.inspect(), candidate.inspect())
            if not request.get("dry_run", True):
                if request.get("expected_head"):
                    require(
                        ours.head == request["expected_head"],
                        "Source changed since merge review",
                        "stale_revision",
                    )
                candidate.state.setdefault("merged_branches", []).append(branch)
                candidate._record([], f"Merge {branch} by {manifest['author']}")
                candidate.save()
                manifest.update(status="merged", head=candidate.head)
                write_json(path, manifest)
                result["head"] = candidate.head
            return result
