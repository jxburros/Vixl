"""Workspace check report: design checks and suites over many documents, one result.

``check-all`` (``vixl check --all``) collects documents from globs, a project group or both,
optionally keeps only those changed since a git revision, and checks each one in a bounded pool of
worker threads (as production ``run`` does): ``vixl_check`` findings plus the document's attached
suites (and an optional inline suite). On a group it adds the cross-document group checks
(``group_consistency``). The result has a status per document (passed, failed, needs_review or
error), counts per check, the top findings and totals, and ``passed`` says whether any finding
reached ``fail_on`` (the CI action's levels: error, warning, fix, review, never). With ``profile`` (a check
profile, policy.py) each document is checked under that profile (its checks and suites), and ``fail_on``
defaults to the profile's own level; the document's waivers (waivers.py) apply unless ``waivers`` is false,
and waived findings stay listed as informational.

Every run appends a history entry under ``.vixl-checks/history``; ``since_last`` compares the run
with the previous one over the same scope (newly failing, newly passing, still failing) and notes
a Vixl version change between them. The same result renders as Markdown, JUnit XML, SARIF 2.1.0
and GitHub workflow annotations (``FORMATS``), written through ``outputs`` or printed by the CLI.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .errors import VixlError, require

LEVELS = ("error", "warning", "fix", "review", "never")
FORMATS = ("json", "markdown", "junit", "sarif", "github")
OUTPUTS = (*FORMATS, "proof")
MAX_DOCUMENTS = 1000
MAX_WORKERS = 8
TOP_FINDINGS = 10
HISTORY = ".vixl-checks/history"
KEEP_HISTORY = 200
SKIP_DIRS = (".vixl-groups", ".vixl-checks", ".vixl-ci", ".vixl-branches", ".vixl-cache", ".git")
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
REF = re.compile(r"^[\w./~^@{}+-]{1,200}$")


# Collecting documents ---------------------------------------------------------------------------

def _glob(session, pattern):
    require(isinstance(pattern, str) and pattern.strip(), "documents are globs or paths", field="documents")
    pattern = pattern.strip().replace("\\", "/")
    require(not Path(pattern).is_absolute() and ".." not in Path(pattern).parts,
            "Document globs are workspace-relative", "forbidden", field="documents")
    if not any(ch in pattern for ch in "*?["):
        path = session.resolve(pattern)
        require(path.is_file() and path.suffix == ".vixl", f"{pattern} is not a .vixl file", "not_found",
                field="documents")
        return [path]
    found = []
    for path in session.workspace.glob(pattern):
        if path.suffix != ".vixl" or not path.is_file():
            continue
        relative = path.relative_to(session.workspace)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(session.workspace):
            found.append(resolved)
    return found


def members(session, request, *, default_all=False, allow_empty=False):
    """``(paths, group)``: workspace paths from ``name``/``group`` (a project group) and ``documents``
    (globs or paths), in a stable order; ``group`` is the group definition or None."""
    from .production import read_json
    from .design import named

    group_name = request.get("group", request.get("name"))
    group, paths = None, []
    if group_name is not None:
        path = session.resolve(f".vixl-groups/{named(group_name)}.json")
        require(path.is_file(), f"Unknown project group {group_name!r}", "not_found", field="group",
                suggestions=["vixl_workflow group-list"])
        group = read_json(path)
        paths += [session.resolve(p) for p in group["documents"]]
    documents = request.get("documents")
    if documents is None and group is None and default_all:
        documents = ["**/*.vixl"]
    if isinstance(documents, str):
        documents = documents.split()
    if documents is not None:
        require(isinstance(documents, list) and documents, "documents is a list of globs or paths", field="documents")
        for pattern in documents:
            paths += _glob(session, pattern)
    require(paths or allow_empty, "No documents matched; give documents (globs) or a group", "not_found",
            field="documents")
    unique = sorted(dict.fromkeys(paths), key=lambda p: session.relative(p))
    require(len(unique) <= MAX_DOCUMENTS, f"At most {MAX_DOCUMENTS} documents per run", "resource_limit",
            field="documents")
    return unique, group


def load_projects(session, paths):
    from .project import Project

    projects = {}
    for path in paths:
        project = Project.load(path, limits=session.limits)
        project._workspace = session.workspace
        projects[session.relative(path)] = project
    return projects


# Git --------------------------------------------------------------------------------------------

def _git(workspace, *args, binary=False):
    try:
        done = subprocess.run(["git", "-C", str(workspace), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VixlError("missing_dependency", f"git is needed for this option: {exc}") from exc
    if done.returncode:
        return None
    return done.stdout if binary else done.stdout.decode("utf-8", "replace")


def _ref(value, field):
    require(isinstance(value, str) and REF.match(value) and not value.startswith("-"),
            f"{field} must be a git revision such as main, origin/main or HEAD~1", field=field)
    return value


def _toplevel(session, field):
    top = _git(session.workspace, "rev-parse", "--show-toplevel")
    require(top, f"{field} needs the workspace to be inside a git repository", field=field)
    return Path(top.strip()).resolve()


def changed_since(session, ref):
    """Workspace-relative .vixl paths that differ from ``ref`` (committed, staged or not) or are untracked."""
    _ref(ref, "changed_since")
    top = _toplevel(session, "changed_since")
    require(_git(top, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None,
            f"Unknown git revision {ref!r}", "not_found", field="changed_since")
    names = (_git(top, "diff", "--name-only", "-z", ref, "--") or "").split("\0")
    names += (_git(top, "ls-files", "--others", "--exclude-standard", "-z") or "").split("\0")
    changed = set()
    for name in names:
        if name.endswith(".vixl"):
            path = (top / name).resolve()
            if path.is_relative_to(session.workspace):
                changed.add(session.relative(path))
    return changed


def base_version(session, relative, ref):
    """The bytes of ``relative`` at git revision ``ref``, or None when it did not exist there."""
    top = _toplevel(session, "base")
    name = (session.workspace / relative).resolve().relative_to(top).as_posix()
    return _git(top, "show", f"{ref}:{name}", binary=True)


# Checking ---------------------------------------------------------------------------------------

def _finding_id(issue):
    return f"{issue.get('check')}:{','.join(map(str, issue.get('layers') or [issue.get('layer') or '']))}"


def failing(record, level):
    """Messages of the findings in ``record`` that reach ``level`` (error, warning, fix, review or never), or
    the reason the document could not be checked. The levels are the CI action's ``fail-on``. A waived finding
    is informational, so it reaches no level. Checked under a profile, a suite that needs review fails only
    at warning and review (as ``vixl check --profile`` decides)."""
    from .policy import suite_fails

    if record.get("error"):
        return [record["error"]]
    issues = record.get("issues", [])
    if level == "never":
        found = []
    elif level in ("fix", "review"):
        actions = ("fix",) if level == "fix" else ("fix", "review")
        found = [i for i in issues if i.get("action") in actions or i.get("severity") == "error"]
    else:
        wanted = ("error",) if level == "error" else ("error", "warning")
        found = [i for i in issues if i.get("severity") in wanted]
    messages = [f"{i.get('check')}: {i.get('message', '')}" for i in found]
    if level != "never":
        for name, suite in record.get("suites", {}).items():
            if suite["status"] in ("passed", "waived"):
                continue
            if record.get("profile") and suite["status"] != "missing" and not suite_fails(suite["status"], level):
                continue
            rules = [r["id"] for r in suite["rules"] if r["status"] not in ("passed", "waived")]
            messages.append(f"suite {name}: {suite['status']}" + (f" ({', '.join(rules)})" if rules else ""))
    return messages


def check_document(session, relative, request, suite=None, keep=False, group=None):
    """Check one document. Returns its record (and the loaded project when ``keep``). With ``profile`` in the
    request the profile picks the checks and the suites (``suites: false`` still skips attached suites)."""
    from .project import Project

    path = session.resolve(relative)
    record = {"path": relative}
    project = None
    profile = request.get("profile")
    try:
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        project = Project.load(path, limits=session.limits)
        project._workspace = session.workspace
        options = {"checks": request["checks"]} if request.get("checks") else {}
        if not request.get("waivers", True):
            options["waivers"] = False
        if profile:
            options.update(profile=profile, group=group)
        report = project.check(**options)
        suites = {}
        if profile:
            # The profile ran its own suites; keep their shape (not_passed are the rules that did not pass).
            if request.get("suites", True):
                for name, item in (report.get("profile") or {}).get("suites", {}).items():
                    suites[name] = {"status": item["status"], "errors": item.get("errors", 0),
                                    "needs_review": item.get("needs_review", 0),
                                    "results": item.get("not_passed", [])}
                    if item["status"] == "missing":
                        suites[name]["results"] = [{"id": name, "status": "missing", "message": item["note"]}]
        elif request.get("suites", True):
            from .assurance import effective

            # Attached suites and the library suites a project group or brand.json attaches by reference.
            for name in effective(project):
                suites[name] = project.check_suite(name)
        if suite is not None:
            suites[suite[0]] = project.check_suite(suite[1])
    except (VixlError, OSError, ValueError, KeyError) as exc:
        record.update(status="error", error=str(exc)[:500], issues=[], suites={})
        return (record, None) if keep else record
    issues = sorted(report.get("issues", []), key=lambda i: SEVERITY_ORDER.get(i.get("severity"), 3))
    record.update(
        errors=report.get("errors", 0), warnings=report.get("warnings", 0),
        fix=sum(1 for i in issues if i.get("action") == "fix"),
        by_check=dict(Counter(i.get("check") for i in issues)),
        checks_run=list(report.get("checked", {}).get("checks", [])),
        issues=[{key: issue[key] for key in ("check", "severity", "action", "message", "layers", "layer", "waived")
                 if key in issue} for issue in issues],
        suites={name: {"status": result["status"], "errors": result["errors"],
                       "needs_review": result["needs_review"],
                       "rules": [{key: rule.get(key) for key in ("id", "status", "severity", "message") if
                                  rule.get(key) is not None} for rule in result["results"]]}
                for name, result in suites.items()},
    )
    if report.get("waivers") and (report["waivers"].get("active") or report["waivers"].get("expired")):
        record["waivers"] = report["waivers"]
    if report.get("profile"):
        record["profile"] = {key: report["profile"][key] for key in ("name", "source", "fail_on")}
    suite_states = {"failed" if s["status"] == "missing" else s["status"] for s in record["suites"].values()}
    record["status"] = ("failed" if record["errors"] or "failed" in suite_states else
                        "needs_review" if record["warnings"] or record["fix"] or "needs_review" in suite_states
                        else "passed")
    return (record, project) if keep else record


def _diff(session, record, ref, work):
    from .image_diff import diff_images, load_visual

    data = base_version(session, record["path"], ref)
    if data is None:
        return {"new": True}
    try:
        before = load_visual(session.resolve(record["path"]), session.limits, data=data)
        after = load_visual(session.resolve(record["path"]), session.limits)
        image, stats = diff_images(before, after)
    except (VixlError, OSError, ValueError) as exc:
        return {"error": str(exc)[:300]}
    result = {key: stats[key] for key in ("changed_fraction", "changed_pixels", "changed_region")}
    if work is not None:
        import io

        from .production import write_bytes

        base = work / "base" / record["path"]
        write_bytes(base, data, replace=True)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        picture = work / "diff" / (record["path"].replace("/", "__") + ".png")
        write_bytes(picture, buffer.getvalue(), replace=True)
        result.update(before=session.relative(base), image=session.relative(picture))
    return result


def _summarize(record):
    """The compact per-document entry of the report."""
    entry = {key: record[key] for key in ("path", "status", "errors", "warnings", "fix", "by_check", "error", "diff",
                                          "failing", "checks_run", "sha256", "waivers") if key in record}
    entry["findings"] = record["issues"][:TOP_FINDINGS]
    if len(record["issues"]) > TOP_FINDINGS:
        entry["more_findings"] = len(record["issues"]) - TOP_FINDINGS
    entry["finding_ids"] = sorted({_finding_id(i) for i in record["issues"]})
    if record.get("suites"):
        entry["suites"] = record["suites"]
    return entry


def _suite(session, value):
    """The inline suite: an object, or a workspace .json file holding one (or {suite: ...})."""
    if value is None:
        return None
    if isinstance(value, str):
        from .production import read_json

        path = session.resolve(value)
        require(path.is_file(), f"No suite file at {value}", "not_found", field="suite")
        data = read_json(path)
        return Path(value).stem, data.get("suite", data) if isinstance(data, dict) else data
    require(isinstance(value, dict), "suite is a check-suite object or a .json file", field="suite")
    return "suite", value


def _group_failing(findings, level):
    if level == "never":
        return []
    if level in ("fix", "review"):
        actions = ("fix",) if level == "fix" else ("fix", "review")
        return [f for f in findings if f["action"] in actions or f["severity"] == "error"]
    wanted = ("error",) if level == "error" else ("error", "warning")
    return [f for f in findings if f["severity"] in wanted and f["action"] != "review"]


def run(session, request):
    """The ``check-all`` workflow action."""
    from . import __version__, calls
    from .group_consistency import compare, facts_for

    profile = request.get("profile")
    require(profile is None or (isinstance(profile, str) and profile), "profile is a check profile name",
            field="profile")
    for field in ("since_last", "history", "overwrite", "suites", "waivers"):
        require(type(request.get(field, True)) is bool, f"{field} must be boolean", field=field)
    paths, group = members(session, request, default_all=True, allow_empty=True)
    chosen = None
    if profile:
        from .policy import resolve

        chosen = resolve(profile, session.workspace, group)
    # No fail_on: the profile's own level, else error (an empty string from the CI action means the same).
    level = request.get("fail_on") or (chosen.get("fail_on", "fix") if chosen else "error")
    require(level in LEVELS, f"fail_on is one of {', '.join(LEVELS)}", field="fail_on", allowed=list(LEVELS))
    workers = request.get("workers", min(4, os.cpu_count() or 1))
    require(type(workers) is int and 1 <= workers <= MAX_WORKERS, f"workers must be 1-{MAX_WORKERS}", field="workers")
    if request.get("checks") is not None:
        require(isinstance(request["checks"], list) and all(isinstance(c, str) for c in request["checks"]),
                "checks is a list of check names", field="checks")
    outputs = request.get("outputs") or {}
    require(isinstance(outputs, dict) and set(outputs) <= set(OUTPUTS),
            f"outputs maps {', '.join(OUTPUTS)} to workspace paths", field="outputs", allowed=list(OUTPUTS))
    destinations = {}
    for key, value in outputs.items():
        require(isinstance(value, str) and value, f"outputs.{key} is a workspace path", field=f"outputs.{key}")
        destination = session.resolve(value)
        require(request.get("overwrite", False) or not destination.exists(),
                f"{value} already exists; set overwrite=true", field=f"outputs.{key}")
        if key == "proof":
            require(destination.suffix.lower() in (".html", ".htm"), "outputs.proof is an .html page",
                    field="outputs.proof")
        destinations[key] = destination
    documents = [session.relative(path) for path in paths]
    scope_documents = list(documents)
    if request.get("changed_since"):
        changed = changed_since(session, request["changed_since"])
        documents = [doc for doc in documents if doc in changed]
    base = _ref(request["base"], "base") if request.get("base") else None
    work = session.resolve(request.get("work", ".vixl-checks/work")) if base else None
    suite = _suite(session, request.get("suite"))
    group_checks = request.get("group_checks", group is not None)
    require(type(group_checks) is bool, "group_checks must be boolean", field="group_checks")
    keep = group_checks and len(documents) >= 2

    records, projects = {}, {}

    def one(relative):
        calls.check_cancelled()
        result = check_document(session, relative, request, suite, keep=keep, group=group)
        record, project = result if keep else (result, None)
        if base and record.get("status") != "error":
            record["diff"] = _diff(session, record, base, work)
        return record, project

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(one, doc): doc for doc in documents}
        for done, future in enumerate(as_completed(pending), 1):
            record, project = future.result()
            records[record["path"]] = record
            if project is not None:
                projects[record["path"]] = project
            calls.progress(done, len(documents), record["path"])
    entries = []
    for doc in documents:
        record = records[doc]
        record["failing"] = failing(record, level)
        entries.append(_summarize(record))
    totals = Counter(entry["status"] for entry in entries)
    by_check = Counter()
    for entry in entries:
        by_check.update(entry.get("by_check", {}))
    result = {
        "version": 1, "vixl_version": __version__,
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fail_on": level, "count": len(entries),
        **({"profile": {"name": chosen["name"], "source": chosen["source"], "fail_on": chosen.get("fail_on", "fix")}}
           if chosen else {}),
        "totals": {"passed": totals["passed"], "failed": totals["failed"], "needs_review": totals["needs_review"],
                   "error": totals["error"], "failing": sum(1 for e in entries if e["failing"]),
                   "errors": sum(e.get("errors", 0) for e in entries),
                   "warnings": sum(e.get("warnings", 0) for e in entries),
                   "fix": sum(e.get("fix", 0) for e in entries), "by_check": dict(by_check.most_common())},
        "documents": entries,
    }
    if request.get("changed_since"):
        result["changed_since"] = request["changed_since"]
        result["unchanged"] = len(scope_documents) - len(documents)
    if base:
        result["base"] = base
    if group is not None:
        result["group"] = group["name"]
    group_failing = []
    if keep and len(projects) >= 2:
        reference = request.get("reference")
        report = compare(projects, reference=session.relative(session.resolve(reference)) if reference else None,
                         facts=facts_for(session, group, request.get("facts")),
                         shared_swatches=((group or {}).get("shared") or {}).get("swatches"))
        group_failing = [f["message"] for f in _group_failing(report["findings"], level)]
        result["group_checks"] = {**report, "failing": group_failing}
    result["passed"] = not result["totals"]["failing"] and not group_failing
    if request.get("history", True):
        scope = _scope(request, scope_documents)
        previous = _previous(session, scope)
        if request.get("since_last", False):
            result["since_last"] = since_last(previous, result)
        result["history"] = _record_history(session, scope, result)
    elif request.get("since_last", False):
        result["since_last"] = since_last(_previous(session, _scope(request, scope_documents)), result)
    written = {}
    for key, destination in destinations.items():
        if key == "proof":
            continue
        text = render(result, key)
        from .production import write_bytes

        write_bytes(destination, text.encode("utf-8"), replace=True)
        written[key] = session.relative(destination)
    if "proof" in destinations and entries:
        from .proof import proof_page

        items = []
        for entry in entries:
            item = {"path": entry["path"], "note": f"{entry['status']}" + (
                f": {len(entry['failing'])} finding(s) reach {level}" if entry["failing"] else "")}
            if entry.get("diff", {}).get("before"):
                item["before"] = entry["diff"]["before"]
            items.append(item)
        proof = proof_page(items[:200], destinations["proof"], resolve=session.resolve, title="Vixl document check",
                           overwrite=request.get("overwrite", False), limits=session.limits)
        written["proof"] = session.relative(Path(proof["output"]))
    if written:
        result["outputs"] = written
    return result


# History ----------------------------------------------------------------------------------------

def _scope(request, documents):
    key = {"documents": sorted(documents), "checks": sorted(request.get("checks") or []),
           "fail_on": request.get("fail_on") or "error", "suites": request.get("suites", True),
           "suite": request.get("suite") if isinstance(request.get("suite"), str) else bool(request.get("suite"))}
    # Only when set, so runs without a profile keep comparing with history recorded before profiles existed.
    if request.get("profile"):
        key["profile"] = request["profile"]
    if request.get("waivers", True) is False:
        key["waivers"] = False
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _history_dir(session):
    return session.resolve(HISTORY)


def _previous(session, scope):
    from .production import read_json

    folder = _history_dir(session)
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob(f"*-{scope}.json"), reverse=True):
        try:
            return read_json(path)
        except VixlError:
            continue
    return None


def _record_history(session, scope, result):
    from .production import write_json

    folder = _history_dir(session)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = result["time"].replace(":", "").replace("-", "").replace("+0000", "Z")
    entry = {"version": 1, "vixl_version": result["vixl_version"], "time": result["time"], "scope": scope,
             "fail_on": result["fail_on"],
             "documents": {e["path"]: {"status": e["status"], "failing": bool(e["failing"]), "sha256": e.get("sha256"),
                                       "findings": e["finding_ids"]} for e in result["documents"]}}
    index = 0
    while True:
        path = folder / f"{stamp}-{index:03d}-{scope}.json"
        if not path.exists():
            break
        index += 1
    write_json(path, entry)
    entries = sorted(folder.glob("*.json"))
    for old in entries[:-KEEP_HISTORY]:
        old.unlink(missing_ok=True)
    return session.relative(path)


def since_last(previous, result):
    """Compare this run with the previous history entry of the same scope."""
    if previous is None:
        return {"previous": None, "message": "No earlier run over these documents with these settings"}
    before = previous["documents"]
    now = {e["path"]: e for e in result["documents"]}
    version_changed = previous.get("vixl_version") != result["vixl_version"]
    newly_failing, newly_passing, still_failing = [], [], []
    for path, entry in now.items():
        old = before.get(path)
        if old is None:
            continue
        if entry["failing"] and not old["failing"]:
            changed = old.get("sha256") != entry.get("sha256")
            newly_failing.append({
                "path": path, "status": entry["status"], "document_changed": changed,
                "cause": "document" if changed else "vixl version" if version_changed else "unknown",
                "new_findings": sorted(set(entry["finding_ids"]) - set(old.get("findings", [])))})
        elif old["failing"] and not entry["failing"]:
            newly_passing.append({"path": path, "status": entry["status"]})
        elif old["failing"] and entry["failing"]:
            still_failing.append({"path": path, "status": entry["status"]})
    return {"previous": {"time": previous.get("time"), "vixl_version": previous.get("vixl_version")},
            "version_changed": version_changed, "newly_failing": newly_failing, "newly_passing": newly_passing,
            "still_failing": still_failing, "added": sorted(set(now) - set(before)),
            "removed": sorted(set(before) - set(now))}


# Formats ----------------------------------------------------------------------------------------

def render(result, fmt):
    require(fmt in FORMATS, f"format is one of {', '.join(FORMATS)}", field="format", allowed=list(FORMATS))
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    return {"markdown": markdown, "junit": junit, "sarif": sarif, "github": annotations}[fmt](result)


def markdown(result):
    base = result.get("base")
    lines = ["## Vixl document check", ""]
    if not result["documents"]:
        lines += ["No documents matched." if "changed_since" not in result else
                  f"No documents changed since `{result['changed_since']}`.", ""]
        return "\n".join(lines)
    note = f"Fail on: `{result['fail_on']}`" + (f" · compared with `{base[:12]}`" if base else "")
    if result.get("profile"):
        note += f" · profile `{result['profile']['name']}`"
    if result.get("group"):
        note += f" · group `{result['group']}`"
    if result.get("changed_since"):
        note += f" · changed since `{result['changed_since']}` ({result['unchanged']} unchanged skipped)"
    totals = result["totals"]
    lines += [note, "", f"{result['count']} document(s): {totals['passed']} passed, {totals['needs_review']} need "
              f"review, {totals['failed']} failed" + (f", {totals['error']} could not be checked" if totals["error"]
                                                      else ""), "",
              "| Document | Errors | Warnings | Fix | Changed | Status |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for entry in result["documents"]:
        diff = entry.get("diff")
        changed = "" if not base else "new" if diff is None or diff.get("new") else (
            diff.get("error") or f"{diff['changed_fraction']:.2%}")
        status = "❌ " + str(len(entry["failing"])) if entry["failing"] else "✅"
        lines.append(f"| `{entry['path']}` | {entry.get('errors', '?')} | {entry.get('warnings', '?')} | "
                     f"{entry.get('fix', '?')} | {changed} | {status} {entry['status']} |")
    details = [entry for entry in result["documents"] if entry["failing"]]
    if details:
        lines += ["", "### Findings", ""]
        for entry in details:
            lines.append(f"**{entry['path']}**")
            lines += [f"- {message}" for message in entry["failing"][:20]]
            lines.append("")
    waived = [(entry["path"], item) for entry in result["documents"] for item in entry.get("waivers", {}).get("active", [])]
    expired = [(entry["path"], item) for entry in result["documents"]
               for item in entry.get("waivers", {}).get("expired", [])]
    if waived or expired:
        lines += ["", "### Waivers", ""]
        for path, item in waived[:50]:
            lines.append(f"- `{path}`: {item.get('check') or item.get('rule')} ({item['scope']}"
                         + (f", until {item['expires']}" if item.get("expires") else "") + ")"
                         + (f": {item['reason']}" if item.get("reason") else ""))
        for path, item in expired[:50]:
            lines.append(f"- `{path}`: **expired** {item.get('check') or item.get('rule')} ({item['scope']}, "
                         f"{item.get('expires')})")
    group = result.get("group_checks")
    if group and group["findings"]:
        lines += ["", "### Group consistency", ""]
        lines += [f"- {'**' + f['action'] + '**'} {f['message']}" for f in group["findings"][:50]]
    since = result.get("since_last")
    if since and since.get("previous"):
        lines += ["", "### Since the last run", "",
                  f"Previous run {since['previous']['time']} on Vixl {since['previous']['vixl_version']}"
                  + (" (a different version)" if since["version_changed"] else ""), ""]
        for key, label in (("newly_failing", "Newly failing"), ("newly_passing", "Newly passing"),
                           ("still_failing", "Still failing")):
            items = since[key]
            lines.append(f"- {label}: " + (", ".join(f"`{i['path']}`" + (f" ({i['cause']})" if i.get("cause") else "")
                                                       for i in items) or "none"))
    return "\n".join(lines) + "\n"


def _level(severity):
    return {"error": "error", "warning": "warning"}.get(severity, "note")


def _suite_findings(entry):
    for name, suite in entry.get("suites", {}).items():
        for rule in suite["rules"]:
            if rule["status"] not in ("passed", "waived"):
                severity = "error" if rule["status"] == "failed" and rule.get("severity", "error") == "error" else "warning"
                yield name, rule, severity


def junit(result):
    from xml.etree import ElementTree as ET

    level = result["fail_on"]
    root = ET.Element("testsuites", name="Vixl checks")
    total = failures = errors = 0
    for entry in result["documents"]:
        suite = ET.SubElement(root, "testsuite", name=entry["path"])
        cases = fails = errs = 0
        if entry["status"] == "error":
            case = ET.SubElement(suite, "testcase", classname=entry["path"], name="load")
            ET.SubElement(case, "error", message=entry.get("error", "")[:500], type="error")
            cases, errs = 1, 1
        else:
            issues = entry.get("findings", [])
            names = list(dict.fromkeys([*entry.get("checks_run", []), *entry.get("by_check", {})]))
            for name in names:
                case = ET.SubElement(suite, "testcase", classname=entry["path"], name=name)
                cases += 1
                # ``failing`` lists every finding that reaches fail_on, not only the top findings.
                failed = [m[len(name) + 2:] for m in entry.get("failing", []) if m.startswith(f"{name}: ")]
                found = [i["message"] for i in issues if i.get("check") == name]
                if failed:
                    fails += 1
                    node = ET.SubElement(case, "failure", message=failed[0][:500], type=name)
                    node.text = "\n".join(failed)
                elif found:
                    ET.SubElement(case, "system-out").text = "\n".join(found)
            for name, suite_result in entry.get("suites", {}).items():
                for rule in suite_result["rules"]:
                    case = ET.SubElement(suite, "testcase", classname=f"{entry['path']}.suite.{name}", name=rule["id"])
                    cases += 1
                    if rule["status"] not in ("passed", "waived") and level != "never":
                        fails += 1
                        node = ET.SubElement(case, "failure", message=(rule.get("message") or rule["status"])[:500],
                                             type=rule["status"])
                        node.text = json.dumps(rule)
        suite.set("tests", str(cases))
        suite.set("failures", str(fails))
        suite.set("errors", str(errs))
        total, failures, errors = total + cases, failures + fails, errors + errs
    group = result.get("group_checks")
    if group:
        suite = ET.SubElement(root, "testsuite", name=f"group:{result.get('group') or 'documents'}")
        reaching = {id(f) for f in _group_failing(group["findings"], level)}
        names = [f"group-{name}" for name in group["checks"]]
        fails = 0
        for name in names:
            case = ET.SubElement(suite, "testcase", classname="group", name=name)
            found = [f for f in group["findings"] if f["check"] == name]
            bad = [f for f in found if id(f) in reaching]
            if bad:
                fails += 1
                node = ET.SubElement(case, "failure", message=bad[0]["message"][:500], type=name)
                node.text = "\n".join(f["message"] for f in found)
            elif found:
                ET.SubElement(case, "system-out").text = "\n".join(f["message"] for f in found)
        suite.set("tests", str(len(names)))
        suite.set("failures", str(fails))
        suite.set("errors", "0")
        total, failures = total + len(names), failures + fails
    root.set("tests", str(total))
    root.set("failures", str(failures))
    root.set("errors", str(errors))
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def sarif(result):
    from . import __version__

    rules, results = {}, []

    def add(rule_id, description, level, message, path, layers=()):
        rules.setdefault(rule_id, {"id": rule_id, "shortDescription": {"text": description}})
        location = {"physicalLocation": {"artifactLocation": {"uri": path}, "region": {"startLine": 1}}}
        if layers:
            location["logicalLocations"] = [{"name": str(layer), "kind": "element",
                                             "fullyQualifiedName": f"{path}#{layer}"} for layer in layers]
        results.append({"ruleId": rule_id, "level": level, "message": {"text": message}, "locations": [location]})

    for entry in result["documents"]:
        if entry["status"] == "error":
            add("load", "The document could not be checked", "error", entry.get("error", "error"), entry["path"])
            continue
        for issue in entry.get("findings", []):
            add(issue["check"], f"Vixl {issue['check']} check", _level(issue.get("severity")), issue["message"],
                entry["path"], issue.get("layers") or ([issue["layer"]] if issue.get("layer") else []))
        for name, rule, severity in _suite_findings(entry):
            add(f"suite/{name}/{rule['id']}", f"Check-suite rule {rule['id']} ({name})", severity,
                rule.get("message") or f"Suite {name} rule {rule['id']}: {rule['status']}", entry["path"])
    for finding in (result.get("group_checks") or {}).get("findings", []):
        level = "note" if finding["action"] == "review" else _level(finding["severity"])
        for path in finding["documents"] or []:
            add(finding["check"], f"Vixl {finding['check']} (across documents)", level, finding["message"], path,
                [finding["layer"]] if finding.get("layer") else [])
    document = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Vixl", "version": __version__,
                                      "informationUri": "https://github.com/jxburros/Vixl",
                                      "rules": list(rules.values())}},
                  "results": results}],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _escape(value, property=False):
    value = str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(":", "%3A").replace(",", "%2C") if property else value


def annotations(result):
    """GitHub workflow commands: one ``::error``/``::warning``/``::notice`` line per finding."""
    kinds = {"error": "error", "warning": "warning"}
    lines = []
    for entry in result["documents"]:
        path = _escape(entry["path"], True)
        if entry["status"] == "error":
            lines.append(f"::error file={path},title=Vixl::{_escape(entry.get('error', ''))}")
        for issue in entry.get("findings", []):
            kind = kinds.get(issue.get("severity"), "notice")
            lines.append(f"::{kind} file={path},title={_escape('Vixl ' + issue['check'], True)}::"
                         f"{_escape(issue['message'])}")
        for name, rule, severity in _suite_findings(entry):
            title = _escape(f"Vixl suite {name}/{rule['id']}", True)
            lines.append(f"::{severity} file={path},title={title}::{_escape(rule.get('message') or rule['status'])}")
    for finding in (result.get("group_checks") or {}).get("findings", []):
        kind = "notice" if finding["action"] == "review" else kinds.get(finding["severity"], "notice")
        for path in finding["documents"] or []:
            lines.append(f"::{kind} file={_escape(path, True)},title={_escape('Vixl ' + finding['check'], True)}::"
                         f"{_escape(finding['message'])}")
    return "\n".join(lines) + ("\n" if lines else "")


# Command line -----------------------------------------------------------------------------------

class FormattedReport(str):
    """Text output of ``vixl check --all`` that still carries whether the run passed (the exit code)."""

    passed = True


def wants_cli(args):
    return any(arg in ("--all", "--group") or arg.startswith(("--all=", "--group=")) for arg in args)


def cli(args, options, limits):
    from .commands import Parser
    from .interfaces import Session

    p = Parser(prog="vixl check --all", description="Check many documents (globs or a project group) into one report")
    p.add_argument("--all", nargs="*", metavar="GLOB", dest="documents",
                   help="Globs or paths (default **/*.vixl); with --group, extra documents")
    p.add_argument("--group", help="Check the members of this project group, with the group consistency checks")
    p.add_argument("--checks", nargs="+", help="vixl check names (default: the standard checks)")
    p.add_argument("--suite", help="A check-suite JSON file run on every document")
    p.add_argument("--no-suites", action="store_true", help="Skip the suites attached to each document")
    p.add_argument("--fail-on", choices=LEVELS, help="Fail at this level (default: the profile's fail_on with "
                   "--profile, else error)")
    p.add_argument("--profile", help="Check every document under this check profile (draft, review, final or one "
                   "from .vixl-checks.json)")
    p.add_argument("--no-waivers", action="store_true", help="Report every finding as if no document had waivers")
    p.add_argument("--workers", type=int, help=f"Parallel workers (1-{MAX_WORKERS})")
    p.add_argument("--changed-since", metavar="REF", help="Only documents changed since this git revision")
    p.add_argument("--base", metavar="REF", help="Pixel-diff each document against this git revision")
    p.add_argument("--work", help="Folder for base copies and diff images (default .vixl-checks/work)")
    p.add_argument("--since-last", action="store_true", help="Report newly failing / passing since the last run")
    p.add_argument("--no-history", action="store_true", help="Do not record this run in .vixl-checks/history")
    p.add_argument("--reference", help="Group checks: compare against this member instead of the majority")
    p.add_argument("--format", choices=FORMATS, help="Print the report as json (default with --json), markdown "
                   "(default), junit, sarif or github (workflow annotations)")
    p.add_argument("--write", action="append", default=[], metavar="FORMAT=PATH",
                   help=f"Also write the report ({', '.join(OUTPUTS)}), e.g. --write sarif=vixl.sarif")
    p.add_argument("--overwrite", action="store_true", help="Replace existing --write files")
    p.add_argument("--workspace", default=".", help="Workspace folder (default: the current folder)")
    a = p.parse_args(args)
    request = {"suites": not a.no_suites, "history": not a.no_history,
               "since_last": a.since_last, "overwrite": a.overwrite}
    if a.fail_on:
        request["fail_on"] = a.fail_on
    if a.no_waivers:
        request["waivers"] = False
    if a.documents:
        request["documents"] = a.documents
    for key in ("group", "checks", "suite", "workers", "changed_since", "base", "work", "reference", "profile"):
        if getattr(a, key) is not None:
            request[key] = getattr(a, key)
    outputs = {}
    for item in a.write:
        key, _, path = item.partition("=")
        require(key in OUTPUTS and path, f"--write takes FORMAT=PATH with FORMAT one of {', '.join(OUTPUTS)}",
                field="write")
        outputs[key] = path
    if outputs:
        request["outputs"] = outputs
    session = Session(None, limits, workspace=Path(a.workspace).resolve())
    result = run(session, request)
    fmt = a.format or ("json" if options.json else "markdown")
    if fmt == "json":
        return result
    text = FormattedReport(render(result, fmt).rstrip("\n"))
    text.passed = result["passed"]
    return text

