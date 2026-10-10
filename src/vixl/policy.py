"""Check policy for a workspace: severity profiles and shared waivers (``.vixl-checks.json``).

A profile says how strict a check run is, so the same document can be sketched and shipped under one set of
checks::

    {"profiles": {"final": {"fail_on": "review", "optional": ["color_vision", "print"], "suites": "all"}},
     "waivers": [{"check": "safe_area", "target": "title-bar", "reason": "...", "expires": "2026-12-31"}]}

- ``fail_on``: the findings that fail the run: ``error`` (severity error), ``warning`` (errors and warnings),
  ``fix`` (any finding whose action is fix, the default verdict), ``review`` (fix or review findings) or
  ``never``.
- ``checks``: the check names to run (default: the standard checks); ``optional``: opt-in checks added to them.
- ``suites``: ``"all"`` attached suites, ``"none"``, or a list of suite names; a failed suite fails the run
  (a suite needing review fails it at ``warning`` and ``review``).

Built-in profiles ``draft``, ``review`` and ``final`` always exist; the workspace file adds profiles or
overrides their fields, and a project group's ``profiles`` override both for that group's documents.
"""

import json
from copy import deepcopy
from pathlib import Path

from .assets import read_bounded
from .errors import VixlError, require

FILE = ".vixl-checks.json"
LEVELS = ("never", "error", "warning", "fix", "review")
PROFILE_FIELDS = {"fail_on", "checks", "optional", "suites", "description"}
BUILTIN = {
    "draft": {"fail_on": "error", "suites": "none",
              "description": "Sketching: only errors fail; suites do not run."},
    "review": {"fail_on": "fix", "suites": "all",
               "description": "Work in progress: findings that need a fix fail, and every attached suite runs."},
    "final": {"fail_on": "review", "optional": ["color_vision"], "suites": "all",
              "description": "Shipping: fix and review findings fail, color-vision is checked and every suite runs."},
}


def path(workspace):
    root = Path(workspace or Path.cwd()).resolve()
    target = (root / FILE).resolve()
    require(target.is_relative_to(root), f"{FILE} must stay inside the workspace", "forbidden")
    return target


def load(workspace=None):
    target = path(workspace)
    if not target.exists():
        return {}
    try:
        return validate(json.loads(read_bounded(target, 1024 * 1024)))
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_policy", f"Invalid {FILE}: {exc}") from exc


def for_project(project):
    workspace = getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None)
    return load(workspace)


def validate_profile(name, profile, field="profiles"):
    from .checks import CHECKS, OPTIONAL_CHECKS

    where = f"{field}.{name}"
    require(isinstance(name, str) and name, f"{field}: profile names are text", field=field)
    require(isinstance(profile, dict), f"{where} must be an object", field=where)
    unknown = sorted(set(profile) - PROFILE_FIELDS)
    require(not unknown, f"{where}: unknown field(s) {unknown}; use {', '.join(sorted(PROFILE_FIELDS))}", field=where)
    require(profile.get("fail_on", "fix") in LEVELS, f"{where}.fail_on is one of {', '.join(LEVELS)}",
            field=f"{where}.fail_on")
    known = set(CHECKS + OPTIONAL_CHECKS)
    for key in ("checks", "optional"):
        values = profile.get(key, [])
        require(isinstance(values, list) and all(isinstance(v, str) for v in values),
                f"{where}.{key} is a list of check names", field=f"{where}.{key}")
        bad = sorted(set(values) - known)
        require(not bad, f"{where}.{key}: unknown check(s) {bad}; use {', '.join(CHECKS + OPTIONAL_CHECKS)}",
                field=f"{where}.{key}")
    suites = profile.get("suites", "none")
    require(suites in ("all", "none") or (isinstance(suites, list) and all(isinstance(s, str) for s in suites)),
            f"{where}.suites is 'all', 'none' or a list of suite names", field=f"{where}.suites")
    require(isinstance(profile.get("description", ""), str), f"{where}.description is text", field=where)
    return profile


def validate_profiles(profiles, field="profiles"):
    require(isinstance(profiles, dict) and len(profiles) <= 32, f"{field} maps up to 32 names to profiles",
            field=field)
    for name, profile in profiles.items():
        validate_profile(name, profile, field)
    return profiles


def validate(config):
    from .waivers import records

    require(isinstance(config, dict), f"{FILE} must be an object")
    unknown = sorted(set(config) - {"profiles", "waivers"})
    require(not unknown, f"Unknown {FILE} field(s) {unknown}; use profiles and waivers")
    validate_profiles(config.get("profiles", {}))
    records(config.get("waivers", []), scope="workspace", field="waivers")
    return config


def profiles(workspace=None, group=None):
    """Every profile available here: built-in ones, overridden field by field by the workspace file and then
    by the group's own ``profiles``. Each carries ``source``."""
    result = {name: {**deepcopy(value), "source": "built-in"} for name, value in BUILTIN.items()}
    for source, layer in (("workspace", load(workspace).get("profiles", {})),
                          ("group", (group or {}).get("profiles", {}))):
        for name, value in layer.items():
            result[name] = {**result.get(name, {}), **deepcopy(value), "source": source}
    return result


def resolve(name, workspace=None, group=None):
    available = profiles(workspace, group)
    require(name in available, f"Unknown check profile {name!r}; available: {', '.join(available)}", field="profile")
    return {"name": name, **available[name]}


def failing(report, fail_on):
    """Indexes of the findings that fail a run at ``fail_on``."""
    issues = report.get("issues", [])
    if fail_on == "never":
        return []
    if fail_on == "error":
        return [i for i, x in enumerate(issues) if x["severity"] == "error"]
    if fail_on == "warning":
        return [i for i, x in enumerate(issues) if x["severity"] in ("error", "warning")]
    actions = ("fix",) if fail_on == "fix" else ("fix", "review")
    return [i for i, x in enumerate(issues) if x.get("action") in actions or x["severity"] == "error"]


def suite_fails(status, fail_on):
    if fail_on == "never" or status == "passed":
        return False
    return status == "failed" or fail_on in ("warning", "review")


def run(project, profile, *, group=None, **options):
    """``check_design`` under a profile: the profile's checks and suites run, and ``passed`` follows its
    ``fail_on``. The report gains ``profile`` (name, fail_on, the failing finding indexes and suites)."""
    from .checks import CHECKS, check_design
    from .timeline import animated

    workspace = getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None)
    chosen = resolve(profile, workspace, group)
    if options.get("checks") is None and (chosen.get("checks") or chosen.get("optional")):
        names = list(chosen.get("checks") or CHECKS)
        names += [name for name in chosen.get("optional", []) if name not in names]
        if animated(project.state.get("timeline")) and "motion" not in names:
            names.append("motion")
        options["checks"] = names
    report = check_design(project, **options)
    fail_on = chosen.get("fail_on", "fix")
    blocking = failing(report, fail_on)
    attached = project.state.get("suites", {})
    wanted = chosen.get("suites", "none")
    names = list(attached) if wanted == "all" else [] if wanted == "none" else wanted
    suites = {}
    for name in names:
        if name not in attached:
            suites[name] = {"status": "missing", "note": f"The profile names suite {name!r}, which is not attached"}
            continue
        result = project.check_suite(name)
        suites[name] = {"status": result["status"], "errors": result["errors"], "needs_review": result["needs_review"],
                        "not_passed": [r for r in result["results"] if r["status"] not in ("passed", "waived")][:20]}
        if result.get("waivers"):
            suites[name]["waivers"] = result["waivers"]
    failed_suites = [name for name, item in suites.items()
                     if (item["status"] == "missing" and fail_on != "never") or suite_fails(item["status"], fail_on)]
    report["profile"] = {
        "name": chosen["name"], "source": chosen["source"], "fail_on": fail_on,
        "checks": report.get("checked", {}).get("checks"), "failing": blocking,
        **({"suites": suites} if suites else {}), **({"failed_suites": failed_suites} if failed_suites else {}),
    }
    report["passed"] = not blocking and not failed_suites
    # The outcome follows the profile: what it fails on fails validation; other fix/review findings and
    # suites that need a look stay review reasons, so a draft pass is never read as validated-for-final.
    from .outcomes import describe, make

    issues = report.get("issues", [])
    stop = set(blocking)
    reasons = [describe(x) for i, x in enumerate(issues) if i not in stop and x.get("action") in ("fix", "review")]
    reasons += [f"suite {name}: {item['status']}" for name, item in suites.items()
                if item["status"] != "passed" and name not in failed_suites]
    report["outcome"] = make("completed", "failed" if blocking or failed_suites else "passed", reasons,
                             (report.get("outcome") or {}).get("accepted", ()),
                             [f"profile {chosen['name']}", *(f"suite {name}" for name in suites)])
    return report
