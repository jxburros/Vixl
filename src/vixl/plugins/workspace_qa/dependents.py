"""The workspace dependency graph: who depends on what, read from each document's state without rendering.

An edge says a document depends on a target. Targets are workspace-relative POSIX paths, or ``suite:NAME`` for a
library suite. The kinds:

- ``link``: a link layer's source document (on any page or master);
- ``brand``: the workspace ``brand.json`` (every document reads it);
- ``group``: the definition of a project group the document belongs to (``.vixl-groups/NAME.json``);
- ``data`` and ``template``: the CSV and the template document a merged sheet was made from (``merge`` record);
- ``suite``: a library suite the document is held to, by ``extends`` or through a group or brand.json.

Other plugins add kinds with ``register(reader)``; a reader is ``fn(state, path, workspace) -> [(kind, target)]``,
optionally with ``reader.stamp(workspace)``: what its edges depend on besides the document (the pipelines plugin's
data-sync bindings), so the cache is read again when that changes. Each document's edges are cached by file size and mtime in ``.vixl-checks/links-index.json``, so a graph over a
large workspace re-reads only the documents that changed.

Public API (other plugins call these): ``graph(workspace, documents=None)``, ``dependents(workspace, target, ...)``,
``walk(...)`` (dependents with cycles), ``tree(workspace, target, ...)`` and ``register(reader)``. ``workspace`` is
a folder or a ``Session``.
"""

from collections import deque
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

from ...errors import VixlError, require
from ...links import MAX_DEPTH

INDEX = ".vixl-checks/links-index.json"
VERSION = 1
KINDS = ("link", "brand", "group", "data", "template", "suite")
NESTED = ("link", "template")  # edges along which a change propagates to the dependents' own dependents
SKIP_DIRS = (".vixl-groups", ".vixl-checks", ".vixl-ci", ".vixl-branches", ".vixl-cache", ".vixl-runs", ".git")
MAX_DOCUMENTS = 5000
_READERS = []


def register(reader):
    """Add an edge reader ``fn(state, path, workspace) -> [(kind, target)]`` (target workspace-relative or
    ``suite:NAME``). Returns the reader, so it works as a decorator."""
    if reader not in _READERS:
        _READERS.append(reader)
    return reader


def _root(workspace):
    return Path(getattr(workspace, "workspace", workspace)).resolve()


def _limits(workspace):
    from ...model import Limits

    return getattr(workspace, "limits", None) or Limits()


def _relative(root, path):
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return None


# Collecting documents ---------------------------------------------------------------------------

def collect(workspace, documents=None):
    """Workspace-relative .vixl paths matching ``documents`` (globs or paths; default every document)."""
    root = _root(workspace)
    patterns = documents.split() if isinstance(documents, str) else list(documents or ["**/*.vixl"])
    found = set()
    for pattern in patterns:
        require(isinstance(pattern, str) and pattern.strip(), "documents are globs or paths", field="documents")
        pattern = pattern.strip().replace("\\", "/")
        require(not Path(pattern).is_absolute() and ".." not in PurePosixPath(pattern).parts,
                "Document globs are workspace-relative", "forbidden", field="documents")
        for path in (root.glob(pattern) if any(ch in pattern for ch in "*?[") else [root / pattern]):
            if path.suffix != ".vixl" or not path.is_file():
                continue
            relative = _relative(root, path)
            if relative and not any(part in SKIP_DIRS for part in PurePosixPath(relative).parts[:-1]):
                found.add(relative)
    require(len(found) <= MAX_DOCUMENTS, f"At most {MAX_DOCUMENTS} documents in a dependency graph",
            "resource_limit", field="documents")
    return sorted(found)


def read_state(path, limits=None):
    """The ``state`` of a .vixl file, read from its project.json alone (no assets are decoded)."""
    from ...assets import read_bounded
    from ...model import Limits

    limits = limits or Limits()
    data = read_bounded(path, limits.max_project_bytes)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("project.json")
            require(info.file_size <= limits.max_project_bytes, "project.json exceeds the byte limit", "resource_limit")
            metadata = json.loads(archive.read(info))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise VixlError("invalid_project", f"Not a readable Vixl document: {exc}") from exc
    state = metadata.get("state") if isinstance(metadata, dict) else None
    require(isinstance(state, dict), "project.json has no state", "invalid_project")
    return state


# Edges ------------------------------------------------------------------------------------------

class _Located:
    """Enough of a Project for ``links.locate``: the document's path and the workspace, never outside files."""

    allow_linked = False

    def __init__(self, path, workspace):
        self.path, self._workspace = str(path), str(workspace)


def _document_edges(root, relative, state):
    from ...links import link_layers, locate

    path = root / relative
    host = _Located(path, root)
    edges = []
    for _, layer in link_layers(state):
        source = layer.get("source")
        try:
            target = _relative(root, locate(host, source))
        except VixlError:
            target = None
        edges.append(["link", target] if target else ["unresolved", str(source)])
    merge = state.get("merge") if isinstance(state.get("merge"), dict) else {}
    for key, kind in (("data", "data"), ("template", "template")):
        value = merge.get(key)
        if isinstance(value, str) and value:
            # merge-impose records workspace-relative paths.
            target = _relative(root, value if Path(value).is_absolute() else root / value)
            if target:
                edges.append([kind, target])
    for suite in (state.get("suites") or {}).values():
        if isinstance(suite, dict) and isinstance(suite.get("extends"), str):
            edges.append(["suite", f"suite:{suite['extends']}"])
    for reader in _READERS:
        for kind, target in reader(state, path, root) or ():
            edges.append([str(kind), str(target)])
    return [list(edge) for edge in dict.fromkeys(tuple(edge) for edge in edges)]


def _readers_key(root=None):
    """The readers, and what each reader's edges depend on besides the document (its ``stamp(workspace)``), so the
    cache is read again when a reader's own inputs change."""
    _load_readers()
    key = []
    for reader in _READERS:
        name = f"{reader.__module__}.{getattr(reader, '__qualname__', reader)}"
        stamp = getattr(reader, "stamp", None)
        key.append([name, stamp(root)] if stamp and root is not None else name)
    return key


def _load_readers():
    """Import every plugin's workflow modules once, so the readers they register are in place before a graph."""
    from ... import plugins

    plugins.modules("workflows")


def _load_index(root):
    path = root / INDEX
    try:
        index = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        index = None
    readers = json.loads(json.dumps(_readers_key(root)))
    if not isinstance(index, dict) or index.get("version") != VERSION or index.get("readers") != readers:
        return {"version": VERSION, "readers": readers, "documents": {}}
    return index


def _save_index(root, index):
    from ...production import write_json

    try:
        write_json(root / INDEX, index)
    except (OSError, VixlError):
        pass  # the cache is an optimization; a read-only workspace still gets a graph


def _groups(root):
    from ...production import read_json

    groups = {}
    folder = root / ".vixl-groups"
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".transaction.json"):
                continue
            try:
                group = read_json(path)
            except (VixlError, OSError):
                continue
            if isinstance(group, dict) and isinstance(group.get("documents"), list):
                groups[path.stem] = {"definition": _relative(root, path), "documents": list(group["documents"]),
                                     "suites": [s for s in group.get("suites", []) if isinstance(s, str)]}
    return groups


def _brand_suites(root):
    path = root / "brand.json"
    if not path.is_file():
        return None
    try:
        kit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in (kit.get("suites") or []) if isinstance(s, str)] if isinstance(kit, dict) else []


def graph(workspace, documents=None, *, cache=True):
    """The dependency graph of the documents ``documents`` selects (default every .vixl in the workspace):
    ``{documents: {path: {edges: [[kind, target]], error?}}, reverse: {target: [{document, kind}]}, groups,
    brand}``. Documents are read from their state (cached by size and mtime in ``.vixl-checks/links-index.json``
    unless ``cache`` is false)."""
    root = _root(workspace)
    limits = _limits(workspace)
    index = _load_index(root) if cache else {"version": VERSION, "readers": _readers_key(root), "documents": {}}
    known = index["documents"]
    chosen = collect(root, documents)
    dirty = False
    nodes = {}
    for relative in chosen:
        path = root / relative
        stat = path.stat()
        stamp = [stat.st_size, stat.st_mtime_ns]
        entry = known.get(relative)
        if not entry or entry.get("stamp") != stamp:
            try:
                entry = {"stamp": stamp, "edges": _document_edges(root, relative, read_state(path, limits))}
            except (VixlError, OSError) as exc:
                entry = {"stamp": stamp, "edges": [], "error": str(exc)[:300]}
            known[relative] = entry
            dirty = True
        nodes[relative] = {"edges": [list(edge) for edge in entry["edges"]],
                           **({"error": entry["error"]} if entry.get("error") else {})}
    groups = _groups(root)
    brand = _brand_suites(root)
    for relative, node in nodes.items():
        extra = []
        if brand is not None:
            extra.append(["brand", "brand.json"])
            extra += [["suite", f"suite:{name}"] for name in brand]
        for name, group in groups.items():
            if relative in group["documents"]:
                extra.append(["group", group["definition"]])
                extra += [["suite", f"suite:{suite}"] for suite in group["suites"]]
        node["edges"] = [list(edge) for edge in dict.fromkeys(tuple(edge) for edge in [*node["edges"], *extra])]
    if cache:
        stale = set(known) - set(collect(root))
        for relative in stale:
            known.pop(relative)
        if dirty or stale:
            _save_index(root, index)
    reverse = {}
    for relative, node in nodes.items():
        for kind, target in node["edges"]:
            if kind != "unresolved":
                reverse.setdefault(target, []).append({"document": relative, "kind": kind})
    for items in reverse.values():
        items.sort(key=lambda item: (item["document"], item["kind"]))
    return {"version": VERSION, "documents": nodes, "reverse": dict(sorted(reverse.items())),
            "groups": {name: {"definition": g["definition"], "documents": g["documents"]} for name, g in groups.items()},
            **({"brand": "brand.json"} if brand is not None else {})}


def _target(root, target):
    if isinstance(target, str) and target.startswith("suite:"):
        return target
    path = Path(target)
    relative = _relative(root, path if path.is_absolute() else root / path)
    require(relative is not None, f"{target} is outside the workspace", "forbidden", field="source")
    return relative


def dependents(workspace, target, *, kinds=None, nested=True, documents=None, max_depth=MAX_DEPTH, built=None,
               follow=NESTED):
    """Documents that depend on ``target`` (a path, or ``suite:NAME``): ``[{document, kind, depth, via}]`` in
    breadth-first order. ``kinds`` limits the first step (default every kind); with ``nested`` the documents that
    link to a dependent (or were merged from it: the ``follow`` kinds) follow, up to ``max_depth`` levels. ``via`` is
    the chain from the target. ``built`` reuses a ``graph`` result."""
    return walk(workspace, target, kinds=kinds, nested=nested, documents=documents, max_depth=max_depth,
                 built=built, follow=follow)["dependents"]


def walk(workspace, target, *, kinds=None, nested=True, documents=None, max_depth=MAX_DEPTH, built=None,
          follow=NESTED):
    """``{target, dependents, cycles}``: ``dependents`` and the chains that lead back to a document on them."""
    root = _root(workspace)
    built = built or graph(workspace, documents)
    start = _target(root, target)
    wanted = set(kinds or KINDS)
    found, seen, cycles = [], {start}, []
    queue = deque([(start, (start,), 0)])
    while queue:
        node, chain, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for item in built["reverse"].get(node, []):
            if depth == 0 and item["kind"] not in wanted:
                continue
            if depth > 0 and item["kind"] not in follow:
                continue
            document = item["document"]
            if document in chain:
                cycles.append([*chain, document])
                continue
            if document in seen:
                continue
            seen.add(document)
            found.append({"document": document, "kind": item["kind"], "depth": depth + 1, "via": list(chain)})
            if nested:
                queue.append((document, (*chain, document), depth + 1))
    return {"target": start, "dependents": found, "cycles": cycles}


def tree(workspace, target, *, kinds=("link",), documents=None, max_depth=MAX_DEPTH, built=None, follow=("link",)):
    """The dependents of ``target`` as a nested tree ``{document, kind?, dependents: [...]}`` with the ``cycles``
    found (each a chain that comes back to a document already on it)."""
    walked = walk(workspace, target, kinds=kinds, documents=documents, max_depth=max_depth, built=built,
                   follow=follow)
    nodes = {walked["target"]: {"document": walked["target"], "dependents": []}}
    for item in walked["dependents"]:
        node = {"document": item["document"], "kind": item["kind"], "dependents": []}
        nodes[item["via"][-1]]["dependents"].append(node)
        nodes[item["document"]] = node
    return {**nodes[walked["target"]], "cycles": walked["cycles"]}
