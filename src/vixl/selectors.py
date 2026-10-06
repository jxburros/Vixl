"""Bulk edits by selector: one ``edit-layers`` operation changes every layer that matches.

Data-driven and repetitive designs (menus, badge sheets, price tags) cost one tool call per layer
when each edit names its target. ``edit-layers`` selects layers by role, name, kind, tag, group,
text or page and runs the same operations on each match, atomically with the rest of the batch.
The ``where`` selector is checked strictly (unknown keys are errors with did-you-mean), the
result reports how many layers matched, and a selector that matches nothing warns instead of
silently doing nothing.
"""

from copy import deepcopy
import difflib
import fnmatch
import re

from .errors import VixlError, require

TYPES = ("edit-layers",)
WHERE_KEYS = ("role", "name", "name_regex", "kind", "shape", "tag", "group", "text_contains", "text_regex",
              "id", "visible", "page", "not")
LAYER_KINDS = ("raster", "text", "solid", "gradient", "shape", "group", "frame", "adjustment", "pathfinder",
               "symbol", "pixel", "paint", "field")
KIND_ALIASES = {"image": "raster", "photo": "raster", "picture": "raster", "rect": "shape", "rectangle": "shape"}
ROLES = ("content", "decoration", "background", "title")
# Operations that create layers or change the whole document: they make no sense once per match.
NOT_PER_LAYER = {
    "edit-layers", "adapt-layout", "canvas", "page", "master", "layout-apply", "template-apply", "select",
    "text", "solid", "gradient", "shape", "add", "frame", "pen", "symbol-instance", "organic-shape", "variable",
    "palette-define", "palette-apply", "palette-generate", "swatch", "font-register", "guidance", "preset-save",
}
MAX_STEPS = 20
MAX_REGEX = 200
TEXT_WINDOW = 2000  # Regexes read at most this much text, so a pathological pattern stays bounded.
REPORT_NAMES = 40

DESCRIPTION = (
    "Layers to change; every given key must match (AND). role: content|decoration|background|title or a role-set name; "
    "name: glob like 'badge-*' (or a list); name_regex; kind: text|shape|raster|group|… (or a list); shape: "
    "rectangle|ellipse|…; tag: a tag set with layer-intent; group: layer or group whose descendants match; "
    "text_contains / text_regex: text layers; id: exact IDs or names; visible: true|false; page: a page number or "
    "name, a list, or 'all' (default: the active page); not: a where object to exclude. Values may be lists "
    "(any of)."
)


def schemas(add):
    from .schema import B

    add(
        "edit-layers",
        {
            "where": {"type": "object", "description": DESCRIPTION},
            "do": {
                "type": ["object", "array"],
                "description": "An operation (or up to 20) applied to every matched layer, in order, with target set "
                "to the layer; e.g. {type: text-set, color: '#fff'}. No target, no page. Creating and document-wide "
                "operations are refused.",
            },
            "dry_run": {**B, "description": "Only count and name the matches; change nothing."},
            "expect": {"type": "integer", "minimum": 0, "description": "Fail unless exactly this many layers match."},
        },
        ["where", "do"],
    )


def many(value, field):
    """A string or a list of strings as a list; anything else is an error that names the field."""
    items = value if isinstance(value, list) else [value]
    require(items and all(isinstance(item, str) for item in items),
            f"where.{field} must be a string or a list of strings", field=f"where.{field}")
    return items


def parse_where(where, path="where"):
    """Validate a selector and return it normalized (lists everywhere). Unknown keys are errors."""
    require(isinstance(where, dict) and where, f"{path} must be an object like {{kind: 'text', name: 'price-*'}}",
            field=path)
    where = dict(where)
    if "type" in where and "kind" not in where:
        where["kind"] = where.pop("type")  # "type" is what layers call it everywhere else
    unknown = [key for key in where if key not in WHERE_KEYS]
    if unknown:
        close = {key: difflib.get_close_matches(key, WHERE_KEYS, 1, 0.5) for key in unknown}
        hints = [f"{found[0]!r} instead of {key!r}" for key, found in close.items() if found]
        raise VixlError(
            "invalid_operation",
            f"Unknown {path} key(s) {', '.join(map(repr, unknown))}. Keys: {', '.join(WHERE_KEYS)}"
            + (f". Did you mean {', '.join(hints)}?" if hints else ""),
            field=f"{path}.{unknown[0]}", allowed=list(WHERE_KEYS),
            suggestions={key: found[0] for key, found in close.items() if found},
        )
    parsed = {}
    for key, value in where.items():
        if key == "not":
            parsed[key] = parse_where(value, f"{path}.not")
        elif key == "page":
            items = value if isinstance(value, list) else [value]
            require(items and all(isinstance(i, (str, int)) and not isinstance(i, bool) for i in items),
                    f"{path}.page must be a page number or name, a list of them, or 'all'", field=f"{path}.page")
            parsed[key] = items
        elif key == "visible":
            require(isinstance(value, bool), f"{path}.visible must be true or false", field=f"{path}.visible")
            parsed[key] = value
        else:
            items = many(value, key)
            if key == "kind":
                items = [KIND_ALIASES.get(item.lower(), item.lower()) for item in items]
                bad = [item for item in items if item not in LAYER_KINDS]
                if bad:
                    close = difflib.get_close_matches(bad[0], LAYER_KINDS, 1, 0.5)
                    raise VixlError(
                        "invalid_operation",
                        f"Unknown layer kind {bad[0]!r}; kinds: {', '.join(LAYER_KINDS)}"
                        + (f". Did you mean {close[0]!r}?" if close else ""),
                        field=f"{path}.kind", allowed=list(LAYER_KINDS), suggestions=close,
                    )
            if key in ("name_regex", "text_regex"):
                for pattern in items:
                    require(len(pattern) <= MAX_REGEX, f"{path}.{key} patterns are at most {MAX_REGEX} characters",
                            field=f"{path}.{key}")
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        raise VixlError("invalid_operation", f"{path}.{key} {pattern!r} is not a valid regex: {exc}",
                                        field=f"{path}.{key}") from exc
            parsed[key] = items
    return parsed


def matcher(project, where):
    """A predicate ``layer -> bool`` for a parsed selector, evaluated on the active page."""
    from .design import descendants

    roles = project.state.get("roles", {})
    groups = set()
    for ref in where.get("group", []):
        layer = project.layer(ref)
        require(layer["type"] == "group", f"{ref!r} is not a group", field="where.group")
        groups |= descendants(project, layer["id"])
    ids = {project.layer(ref)["id"] for ref in where.get("id", [])}
    names = [pattern.casefold() for pattern in where.get("name", [])]
    name_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in where.get("name_regex", [])]
    text_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in where.get("text_regex", [])]
    contains = [text.casefold() for text in where.get("text_contains", [])]
    excluded = matcher(project, where["not"]) if "not" in where else None

    def accepts(layer):
        if "role" in where and not any(
            role == layer.get("role", "content") or layer["id"] in roles.get(role, ()) for role in where["role"]
        ):
            return False
        if names and not any(fnmatch.fnmatchcase(layer["name"].casefold(), pattern) for pattern in names):
            return False
        if name_regexes and not any(rx.search(layer["name"]) for rx in name_regexes):
            return False
        if "kind" in where and layer["type"] not in where["kind"]:
            return False
        if "shape" in where and layer.get("shape") not in where["shape"]:
            return False
        if "tag" in where and not set(where["tag"]) & set(layer.get("tags") or ()):
            return False
        if "group" in where and layer["id"] not in groups:
            return False
        if "id" in where and layer["id"] not in ids:
            return False
        if "visible" in where and layer["visible"] != where["visible"]:
            return False
        if contains or text_regexes:
            if layer["type"] != "text":
                return False
            text = layer.get("text", "")
            if contains and not any(piece in text.casefold() for piece in contains):
                return False
            if text_regexes and not any(rx.search(text[:TEXT_WINDOW]) for rx in text_regexes):
                return False
        return not (excluded and excluded(layer))

    return accepts


def match_layers(project, where):
    """The layers of the active page matching a parsed selector, in stacking order (ids)."""
    accepts = matcher(project, where)
    return [layer["id"] for layer in project.state["layers"] if accepts(layer)]


def pages_of(project, where):
    """The page references a selector spans: None for the active page, else each named page."""
    if "page" not in where:
        return [None]
    if "all" in where["page"]:
        require(project.state.get("pages"), "where.page: this document has no pages", field="where.page")
        return list(range(1, len(project.state["pages"]) + 1))
    return where["page"]


def record(project, key, value):
    """Add a per-call report that Project.apply returns beside ``changes`` (a no-op elsewhere)."""
    reports = getattr(project, "_reports", None)
    if reports is not None:
        reports.setdefault(key, []).append(value)


def execute(project, op):
    from .interfaces import service_check
    from .normalize import apply_centering, resolve_geometry
    from .operations import execute as apply_operation
    from .schema import validate_operation

    where = parse_where(op["where"])
    steps = op["do"] if isinstance(op["do"], list) else [op["do"]]
    require(0 < len(steps) <= MAX_STEPS and all(isinstance(step, dict) for step in steps),
            f"do is an operation object or a list of 1–{MAX_STEPS}", field="do")
    templates, notes = [], []
    for number, step in enumerate(steps):
        require("target" not in step and "page" not in step,
                f"do[{number}]: leave out target and page; edit-layers sets the target to each match "
                "(select pages with where.page)", field=f"do[{number}]")
        try:
            template = validate_operation({**step, "target": "$"}, notes)
            service_check(template)
        except VixlError as exc:
            exc.args = (f"do[{number}]: {exc}",)
            raise
        require(template["type"] not in NOT_PER_LAYER,
                f"do[{number}]: {template['type']!r} creates layers or changes the whole document, so it cannot run "
                "once per matched layer; use it as its own operation", field=f"do[{number}].type")
        templates.append(template)
    if notes:
        for text in notes:
            record(project, "normalized", f"edit-layers do: {text.split(': ', 1)[-1]}")
    from . import pages

    original = project.state.get("page")
    matched, names, visited, switched = 0, [], [], False
    try:
        for ref in pages_of(project, where):
            if ref is not None:
                pages.select(project.state, page=ref)
                switched = True
                visited.append(pages.active_page(project.state)["name"])
            ids = match_layers(project, {k: v for k, v in where.items() if k != "page"})
            matched += len(ids)
            names.extend(project.layer(ident)["name"] for ident in ids)
            if op.get("dry_run"):
                continue
            remaining = getattr(project, "_resource_budget", project.limits.max_operations) - len(ids) * len(templates)
            require(remaining >= 0, f"edit-layers would run {len(ids) * len(templates)} operations, over the "
                    f"batch budget; narrow the selector or split the edit", "resource_limit")
            project._resource_budget = remaining
            for ident in ids:
                if not any(layer["id"] == ident for layer in project.state["layers"]):
                    continue  # An earlier step removed it (for example with its group).
                for template in templates:
                    operation = {**template, "target": ident}
                    resolved, centered = resolve_geometry(project, operation)
                    apply_operation(project, deepcopy(resolved))
                    apply_centering(project, centered, operation)
    finally:
        if switched and original and project.state.get("page") != original:
            _restore(project, original)
    expect = op.get("expect")
    require(expect is None or matched == expect,
            f"edit-layers matched {matched} layer(s) but expect is {expect}: {', '.join(map(repr, names[:20]))}"
            + (f" … and {len(names) - 20} more" if len(names) > 20 else ""),
            "selector_mismatch", field="expect", matched=matched, layers=names[:REPORT_NAMES])
    entry = {"matched": matched, "layers": names[:REPORT_NAMES],
             **({"more": len(names) - REPORT_NAMES} if len(names) > REPORT_NAMES else {}),
             **({"dry_run": True} if op.get("dry_run") else {}),
             **({"pages": visited} if visited else {})}
    record(project, "edit_layers", entry)
    if not matched:
        record(project, "warnings", "edit-layers matched no layers: check where (names are case-insensitive globs; "
               "kind is the layer type; vixl_document_inspect lists the layers)")


def _restore(project, original):
    from . import pages

    if original.startswith(pages.MASTER_PREFIX):
        pages.select(project.state, master=original[len(pages.MASTER_PREFIX):])
    else:
        pages.select(project.state, page=original)


def compile_command(cmd, args):
    """``vixl edit-layers --where JSON --do JSON [--expect N] [--dry-run]``."""
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    parser = Parser(prog="vixl edit-layers", description="Run an operation on every layer matching a selector")
    parser.add_argument("--where", type=json.loads, required=True,
                        help='Selector JSON, e.g. \'{"kind":"text","name":"price-*"}\'')
    parser.add_argument("--do", type=json.loads, required=True,
                        help='Operation JSON (or an array of them) run on each match, e.g. \'{"type":"hide"}\'')
    parser.add_argument("--expect", type=int, help="Fail unless exactly this many layers match")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Count and name the matches only")
    return {"type": cmd, **{k: v for k, v in vars(parser.parse_args(args)).items() if v is not None}}
