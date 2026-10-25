"""Built-in plugins: optional features that join the core through this registry.

Each plugin is a package ``vixl.plugins.<name>`` whose ``__init__`` holds a ``PLUGIN`` manifest (data only).
The manifest names the plugin's modules by role, and the core reaches them only through the functions
below, so a plugin can later ship separately without core changes:

- ``operations``: modules with ``TYPES``, ``schemas(add)`` and ``execute(project, op)``.
- ``commands``: modules with ``compile_command(cmd, args)`` for the operation shorthand in ``vixl apply``.
- ``workflows``: modules with ``ACTIONS`` ({action: (fields, required)}), ``dispatch(session, action,
  request, document)`` and optionally ``FIELD_TYPES`` ({action: {field: schema}}) and ``SUMMARIES``.
- ``hooks``: {hook point: ["module:function", ...]}; see ``HOOKS`` for each point's call signature.
- ``requires``: other plugins this one imports.
- ``checks``: optional design check names the plugin adds (``checks.OPTIONAL_CHECKS``); its ``check`` hook runs them.
- ``capabilities``: {topic: (words that select it, [guidance names])}, merged into the topics of
  ``vixl_reference('capabilities')``; the guidance texts live in the core registry, ``vixl.guidance``.

All plugins are built in for now: ``BUILTIN`` lists them in registration order. ``docs/reference/plugins.md`` has the
criteria for making a new feature a plugin, and ``tests/test_plugins.py`` holds the core to the boundary
(the remaining direct imports are listed there with the reason for each).

Third-party Python extensions (entry points) and declarative packs live in ``external`` and are re-exported
here, so ``vixl.plugins.enable_plugins`` and friends keep working.
"""

from functools import lru_cache
from importlib import import_module

from .external import discover, enable_plugins, filter_plugin, load, package, run  # noqa: F401

BUILTIN = (
    "charts",
    "drawing",
    "diagrams",
    "comics",
    "atmosphere",
    "organic",
    "characters",
    "fontmaker",
    "film",
    "lyrics",
    "imposition",
    "brand_kit",
    "deck_markdown",
    "teamwork",
    "workspace_qa",
    "layout_repair",
    "app_animation",
    "screen_capture",
    "localization",
    "figma_import",
    "pdf_import",
    "ai",
    "spelling",
)

ROLES = ("operations", "commands", "workflows")
HOOKS = {
    "normalize": "fn(kind, op, note) -> op: rewrite forgiving input for an operation before validation",
    "validate-layer": "fn(layer, state, project): raise VixlError for an invalid layer the plugin owns",
    "validate-state": "fn(project, state): raise VixlError for invalid document-level plugin state",
    "check": "fn(name, checks, **context): add design findings with context['issue'] when name is in checks",
    "brand-format": "fn(data) -> (brand.json kit, unmapped paths) or None: read a brand in another format "
                    "(a Design Profile)",
    "spell": "fn(project, texts) -> {lang, available, message?, words: [{layer, word, suggestions}]} or None: "
             "unknown words in {layer id: drawn text}",
    "after-apply": "fn(project): refresh derived plugin state once a batch has applied",
    "apply-report": "fn(project, operations, result): add plugin keys to the apply result",
    "export-format": "fn(project, path, format, report, **options) -> data, or None when the format is not the plugin's",
    "import-format": "fn(project, data, format, **options) -> result, or None when the format is not the plugin's",
    "job-kind": "fn(kind) -> {validate: fn(queue, payload, output), run: fn(queue, job, limits, progress, cancelled) "
                "-> result}, or None when the durable job kind is not the plugin's; list the kinds in fn.KINDS",
    "job-complete": "fn(event) -> delivery record or None: called once when a durable job, check-all or pipeline run "
                    "ends; event is {event, kind, id, status, state, counts, report, workspace, notify, error}",
    "check-variants": "fn(project, request) -> report, or None when the request names none of the plugin's variant "
                      "axes (such as locales)",
}
MANIFEST_KEYS = {"name", "title", "summary", "kind", "modules", "requires", *ROLES, "hooks", "capabilities", "checks"}
KINDS = ("operations", "workflows", "importer", "provider", "checks")


@lru_cache(maxsize=None)
def manifest(name):
    data = import_module(f"{__name__}.{name}").PLUGIN
    if data.get("name") != name:
        raise ValueError(f"Plugin package {name} declares the name {data.get('name')!r}")
    return data


def manifests():
    return [manifest(name) for name in BUILTIN]


def module(plugin, name):
    return import_module(f"{__name__}.{plugin}.{name}")


def _resolve(plugin, reference):
    name, _, attribute = reference.partition(":")
    return getattr(module(plugin, name), attribute)


@lru_cache(maxsize=None)
def modules(role):
    """The modules that fill ``role`` (operations, commands or workflows), in registration order."""
    return tuple(module(m["name"], name) for m in manifests() for name in m.get(role, ()))


@lru_cache(maxsize=None)
def hooks(point):
    """The functions registered for a hook point, in registration order."""
    if point not in HOOKS:
        raise KeyError(f"Unknown plugin hook point {point!r}")
    return tuple(_resolve(m["name"], ref) for m in manifests() for ref in m.get("hooks", {}).get(point, ()))


@lru_cache(maxsize=1)
def operation_types():
    """{operation type: owning module} for every plugin operation."""
    owners = {}
    for owner in modules("operations"):
        for kind in owner.TYPES:
            if kind in owners:
                raise ValueError(f"Operation {kind} is registered twice ({owners[kind].__name__}, {owner.__name__})")
            owners[kind] = owner
    return owners


def execute(project, op, kind):
    return operation_types()[kind].execute(project, op)


def schemas(add):
    for owner in modules("operations"):
        owner.schemas(add)


def compile_command(cmd, args):
    for owner in modules("commands"):
        compiled = owner.compile_command(cmd, args)
        if compiled is not None:
            return compiled
    return None


@lru_cache(maxsize=1)
def workflow_actions():
    """{action: (owning module, (fields, required))} for every plugin workflow action."""
    actions = {}
    for owner in modules("workflows"):
        for action, spec in owner.ACTIONS.items():
            if action in actions:
                raise ValueError(f"Workflow action {action} is registered twice")
            actions[action] = (owner, spec)
    return actions


def workflow_field_types(action):
    owner, _ = workflow_actions()[action]
    return getattr(owner, "FIELD_TYPES", {}).get(action, {})


def workflow_summary(action):
    owner, _ = workflow_actions()[action]
    return getattr(owner, "SUMMARIES", {}).get(action)


def dispatch_workflow(session, action, request, document=None):
    owner, _ = workflow_actions()[action]
    return owner.dispatch(session, action, request, document)


def normalize(kind, op, note):
    for fn in hooks("normalize"):
        op = fn(kind, op, note)
    return op


def optional_checks():
    """Optional design check names the plugins declare (manifest ``checks``), run through their ``check`` hook."""
    return tuple(name for m in manifests() for name in m.get("checks", ()))


def first(point, *args, **kwargs):
    """The first non-None result of a hook point, or None."""
    for fn in hooks(point):
        result = fn(*args, **kwargs)
        if result is not None:
            return result
    return None


def describe():
    """Each built-in plugin and what it contributes, for ``vixl plugins`` and the docs."""
    rows = []
    for m in manifests():
        rows.append({
            "name": m["name"],
            "title": m["title"],
            "summary": m["summary"],
            "kind": m["kind"],
            "builtin": True,
            "modules": list(m["modules"]),
            "operations": sorted(kind for owner in (module(m["name"], n) for n in m.get("operations", ()))
                                 for kind in owner.TYPES),
            "workflows": sorted(action for owner in (module(m["name"], n) for n in m.get("workflows", ()))
                                for action in owner.ACTIONS),
            "hooks": sorted(m.get("hooks", {})),
            "requires": list(m.get("requires", ())),
        })
    return rows


def markdown_table():
    """The docs table of built-in plugins (docs/reference/plugins.md), generated from the manifests."""
    lines = ["| Plugin | Kind | What it adds | Operations and workflow actions |", "| --- | --- | --- | --- |"]
    for row in describe():
        names = [f"`{name}`" for name in row["operations"] + row["workflows"]]
        if not names:
            names = [f"hooks: {', '.join(row['hooks'])}"] if row["hooks"] else ["none: the core calls it directly"]
        lines.append(f"| `{row['name']}` ({row['title']}) | {row['kind']} | {row['summary']} | {', '.join(names)} |")
    return "\n".join(lines)
