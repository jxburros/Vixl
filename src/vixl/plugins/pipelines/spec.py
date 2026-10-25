"""The pipeline resource: ``{version: 1, targets, steps: [...]}``, saved like suites with ``resource-save`` (kind
``pipelines``) or given inline to ``pipeline-run``.

``targets`` is ``{documents: [globs or paths]}``, ``{group: NAME}`` or both. Each step is an object with one key, the
step kind, holding its options (plus an optional ``id``):

- per document, in order: ``act`` (operations on the run's working copy), ``check`` (design checks and suites),
  ``repair`` (repair-layout on the working copy), ``export`` (export targets with ``{doc}`` path templates),
  ``export_check`` (verify each export of the document) and ``approve`` (a proof page's decisions);
- once per run, after every document: ``proof`` (a proof page of the outputs) and ``package`` (a delivery zip).

``on_fail`` is ``hold`` (default: a document whose step fails is held and the others continue) or ``stop`` (the
first held document stops the run).
"""

from copy import deepcopy

from ...errors import require

DOCUMENT_STEPS = ("act", "check", "repair", "export", "export_check", "approve")
RUN_STEPS = ("proof", "package")
STEPS = DOCUMENT_STEPS + RUN_STEPS
MUTATING = ("act", "repair")
MAX_STEPS = 32
ON_FAIL = ("hold", "stop")
FAIL_LEVELS = ("error", "warning", "fix", "review", "never")
TOKENS = ("doc", "dir", "run", "name")
KEYS = {"version", "description", "targets", "steps", "on_fail", "inputs"}

STEP_FIELDS = {
    "act": ({"operations", "suites"}, {"operations"}),
    "check": ({"checks", "suites", "suite", "profile", "fail_on", "waivers"}, set()),
    "repair": ({"checks", "suites", "protected", "minimum_size", "max_candidates", "max_iterations", "time_budget"},
               set()),
    "export": ({"targets", "defaults", "overwrite"}, {"targets"}),
    "export_check": ({"spec"}, set()),
    "approve": ({"decisions"}, set()),
    "proof": ({"output", "title", "max_size", "overwrite"}, {"output"}),
    "package": ({"output", "name", "brand", "locale", "layout", "check", "proof", "decisions", "export_settings",
                 "overwrite"}, {"output"}),
}


def _strings(value, field):
    require(isinstance(value, list) and value and all(isinstance(item, str) and item for item in value),
            f"{field} is a list of strings", field=field)


def validate_targets(targets, field="targets"):
    require(isinstance(targets, dict) and targets and set(targets) <= {"documents", "group"},
            f"{field} is {{documents: [globs]}}, {{group: NAME}} or both", field=field)
    if "documents" in targets:
        _strings(targets["documents"], f"{field}.documents")
    if "group" in targets:
        require(isinstance(targets["group"], str) and targets["group"], f"{field}.group is a group name",
                field=f"{field}.group")


def step_kind(step, index):
    where = f"steps[{index}]"
    require(isinstance(step, dict), f"{where} is an object with one step kind: {', '.join(STEPS)}", field=where)
    kinds = [key for key in step if key != "id"]
    require(len(kinds) == 1 and kinds[0] in STEPS and set(step) <= {kinds[0], "id"},
            f"{where} needs exactly one step kind ({', '.join(STEPS)}) and an optional id", field=where,
            allowed=list(STEPS))
    return kinds[0]


def validate_step(kind, options, where):
    require(isinstance(options, dict), f"{where}.{kind} is an object of options", field=f"{where}.{kind}")
    allowed, required = STEP_FIELDS[kind]
    unknown = sorted(set(options) - allowed)
    require(not unknown, f"{where}.{kind}: unknown field(s) {unknown}; fields: {', '.join(sorted(allowed))}",
            field=f"{where}.{kind}", allowed=sorted(allowed))
    missing = sorted(required - set(options))
    require(not missing, f"{where}.{kind} needs {', '.join(missing)}", field=f"{where}.{kind}")
    for flag in ("overwrite", "check", "proof", "waivers"):
        if flag in options:
            require(type(options[flag]) is bool, f"{where}.{kind}.{flag} must be boolean", field=f"{where}.{kind}")
    if kind == "act":
        require(isinstance(options["operations"], list) and options["operations"]
                and all(isinstance(op, dict) and isinstance(op.get("type"), str) for op in options["operations"]),
                f"{where}.act.operations is a list of operations", field=f"{where}.act.operations")
    if kind in ("act", "repair") and "suites" in options:
        _strings(options["suites"], f"{where}.{kind}.suites")
    if kind == "check":
        if "fail_on" in options:
            require(options["fail_on"] in FAIL_LEVELS, f"{where}.check.fail_on is one of {', '.join(FAIL_LEVELS)}",
                    field=f"{where}.check.fail_on")
        if "checks" in options:
            _strings(options["checks"], f"{where}.check.checks")
        if "suites" in options:
            require(type(options["suites"]) is bool, f"{where}.check.suites is true (run attached suites) or false",
                    field=f"{where}.check.suites")
    if kind == "export":
        targets = options["targets"]
        require(isinstance(targets, list) and 0 < len(targets) <= 16
                and all(isinstance(t, dict) and isinstance(t.get("path"), str) and "document" not in t for t in targets),
                f"{where}.export.targets is a list of 1-16 export targets {{path, ...options}} (path may use "
                f"{', '.join('{' + t + '}' for t in TOKENS)})", field=f"{where}.export.targets")
        require(isinstance(options.get("defaults", {}), dict), f"{where}.export.defaults is an object",
                field=f"{where}.export.defaults")
    if kind == "export_check" and "spec" in options:
        require(isinstance(options["spec"], (dict, str)), f"{where}.export_check.spec is a delivery spec preset name "
                "or an object of spec fields", field=f"{where}.export_check.spec")
        from ...export_checks import resolve_spec

        resolve_spec(options["spec"])  # a misspelled preset or field fails before the run starts
    if kind == "approve" and "decisions" in options:
        require(isinstance(options["decisions"], str) and options["decisions"],
                f"{where}.approve.decisions is the path of a proof page's decisions JSON",
                field=f"{where}.approve.decisions")
    if kind in RUN_STEPS:
        require(isinstance(options["output"], str) and options["output"], f"{where}.{kind}.output is a workspace path",
                field=f"{where}.{kind}.output")


def validate(value):
    """Validate a pipeline (raises ``VixlError`` naming the field); returns it."""
    require(isinstance(value, dict), "A pipeline is an object {version: 1, targets, steps}", field="pipeline")
    unknown = sorted(set(value) - KEYS)
    require(not unknown, f"Unknown pipeline field(s) {unknown}; fields: {', '.join(sorted(KEYS))}", field="pipeline",
            allowed=sorted(KEYS))
    require(value.get("version", 1) == 1, "Pipeline version must be 1", field="version")
    if "targets" in value:
        validate_targets(value["targets"])
    require(value.get("on_fail", "hold") in ON_FAIL, f"on_fail is one of {', '.join(ON_FAIL)}", field="on_fail")
    if "description" in value:
        require(isinstance(value["description"], str) and len(value["description"]) <= 2000,
                "description is text of up to 2000 characters", field="description")
    if "inputs" in value:
        _strings(value["inputs"], "inputs")
    steps = value.get("steps")
    require(isinstance(steps, list) and 0 < len(steps) <= MAX_STEPS, f"steps is a list of 1-{MAX_STEPS} steps",
            field="steps")
    seen_run_step, ids = False, set()
    for index, step in enumerate(steps):
        kind = step_kind(step, index)
        validate_step(kind, step[kind], f"steps[{index}]")
        if "id" in step:
            require(isinstance(step["id"], str) and step["id"] and step["id"] not in ids,
                    f"steps[{index}].id is a unique name", field=f"steps[{index}].id")
            ids.add(step["id"])
        if kind in RUN_STEPS:
            seen_run_step = True
        else:
            require(not seen_run_step, f"steps[{index}]: {kind} runs per document, so it comes before proof and "
                    "package (which run once over every output)", field=f"steps[{index}]")
    return value


def resolve(session, value):
    """``(name, pipeline)`` for a saved pipeline name or an inline pipeline object."""
    if isinstance(value, str):
        from ...resources import get

        return value, deepcopy(get("pipelines", value, workspace=session.workspace))
    return None, deepcopy(validate(value))


def resource_kind(kind):
    """The ``resource-kind`` hook: the ``pipelines`` resource category."""
    return {"builtins": {}, "validate": validate} if kind == "pipelines" else None


resource_kind.KINDS = ("pipelines",)
