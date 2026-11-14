"""``target`` and ``targets``: how every operation that acts on existing layers names them.

Every such operation accepts ``target`` (one layer) and ``targets`` (a list). What a list means
depends on the operation, and the schema says which (``x-targets`` on each variant):

- ``each``: the operation is applied to every listed layer in turn, inside the same atomic batch
  (``opacity``, ``move``, ``layer-intent``, the effects ...). An error names the original operation.
- ``joint``: the layers are handled together (``group``, ``align``, ``distribute`` ...); a lone
  ``target`` is read as a one-item list where the operation requires ``targets``.
- ``one``: the operation takes a single layer (``rename``, ``select-layer`` ...); ``targets`` with
  one entry is read as ``target``, and a longer list is an error that says so.

A target can also be an address object that a plugin resolves to layers through the ``target-resolver``
hook, such as a chart mark ``{"chart": "sales", "series": "Tea", "category": "Dec"}``. An address stands
for the layers it names when the operation runs: every one of them for an ``each`` or ``joint`` operation,
and exactly one for an operation that takes a single layer.

The docs table in docs/reference/operations.md is generated from the schema by ``markdown_table``.
"""

from collections.abc import Callable
from typing import Any

from .errors import VixlError, require
from .model import MAX_LAYERS
from .constants import EFFECTS

MAX_TARGETS = MAX_LAYERS
ALIASES = ("layers", "layer_ids", "layerIds", "target_ids", "targetIds")

# Operations applied once per listed layer. Creation operations (shape, text, solid, gradient)
# take targets to edit several existing layers in place.
EACH = frozenset({
    "text-set", "text-style", "remove", "hide", "show", "raise", "lower", "top", "bottom", "rasterize", "unconstrain",
    "duplicate", "move", "resize", "scale", "rotate", "pivot", "opacity", "blend", "flip", "crop", "constrain",
    "effect", *EFFECTS, "effect-disable", "effect-enable", "effect-move", "effect-remove", "effect-set", "layer-style",
    "style-apply", "lut", "lookup", "layer-intent", "waiver", "fit-text", "path-fit", "shape-to-path", "path-simplify",
    "path-smooth", "offset-path", "outline-stroke", "round-corners", "distort", "skew", "transform", "fit",
    "snap-to-pixel", "keyframe-remove", "shape", "text", "solid", "gradient", "ungroup", "link-refresh",
    "link-embed", "replace-contents", "pattern-fill", "text-animate", "qr", "barcode", "object",
})
# Operations that already take targets themselves and apply to each listed layer.
OWN_EACH = frozenset({"keyframe", "animate", "animate-preset", "look", "irregular", "cut-paper", "motion", "snap",
                      "match-size"})
# Batch items that stand for several operations and take no layer list themselves: ``create-many`` is expanded
# by normalize.expand_batch into one ordinary operation per row (each semantics, one atomic batch) before the
# batch is validated, so a document never records it. Its mode is ``one``.
EXPANDED = frozenset({"create-many"})
# Operations that act on the listed layers together.
JOINT = frozenset({"align", "group", "reparent", "distribute", "artboard", "pathfinder", "suite-capture", "role-set",
                   "arrange-grid", "adapt-layout", "stack", "place", "merge-layers", "die-cut", "reflection",
                   "font-glyph"})

DESCRIPTION = ("Several layer IDs or names: the operation is applied to each in turn, in this order, within the "
               "same atomic batch. Pass target or targets, not both.")


def mode(kind: str) -> str:
    """``each``, ``joint`` or ``one`` (operations without a layer list)."""
    if kind in EACH or kind in OWN_EACH:
        return "each"
    return "joint" if kind in JOINT else "one"


def enrich(variants: list[dict[str, Any]]) -> None:
    """Give every ``each`` operation a ``targets`` field, so ``required: [target]`` becomes target or
    targets, and tag every variant with its ``x-targets`` mode."""
    for variant in variants:
        kind = variant["properties"]["type"]["const"]
        variant["x-targets"] = mode(kind)
        if kind not in EACH:
            continue
        variant["properties"]["targets"] = {
            "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_TARGETS, "uniqueItems": True,
            "description": DESCRIPTION,
        }
        for key in ("anyOf", "oneOf"):  # an alternative that names target accepts targets too
            options = variant.get(key, [])
            if {"required": ["target"]} in options:
                options.append({"required": ["targets"]})
        if "target" in variant["required"]:
            variant["required"] = [key for key in variant["required"] if key != "target"]
            either = {"anyOf": [{"required": ["target"]}, {"required": ["targets"]}]}
            if "anyOf" in variant:
                variant["allOf"] = [*variant.get("allOf", []), {"anyOf": variant.pop("anyOf")}, either]
            else:
                variant.update(either)


def normalize(op: dict[str, Any], kind: str, allowed: Any, required: Any,
              note: Callable[[str], None]) -> dict[str, Any]:
    """Read ``targets``/``target`` in the canonical form for ``kind`` (see the module docstring)."""
    for alias in ALIASES:
        if isinstance(op.get(alias), list) and "targets" not in op and alias not in allowed:
            op["targets"] = op.pop(alias)
            note(f"{alias!r} → 'targets'")
    if "targets" not in op:
        if kind in JOINT and "target" in op and "targets" in required:
            # group, distribute ... require a list; one layer named with target is that list.
            op["targets"] = [op.pop("target")]
            note("'target' → 'targets' (a one-layer list)")
        return op
    targets = op["targets"]
    if isinstance(targets, str):
        op["targets"] = targets = [targets]
        note("targets as a string → a one-layer list")
    if "targets" in allowed:
        if kind in EACH:
            require("target" not in op, f"{kind} takes target or targets, not both", field="targets")
        return op
    if isinstance(targets, list) and len(targets) == 1 and "target" not in op and "target" in allowed:
        op["target"] = op.pop("targets")[0]
        note("'targets' with one layer → 'target'")
        return op
    count = len(targets) if isinstance(targets, list) else 0
    raise VixlError("invalid_operation", f"{kind} takes one target; got targets with {count} layers. Use one "
                    f"{kind} operation per layer", field="targets", suggestions=["target"])


_ADDRESS = "\x00address:"


def lift_addresses(op: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    """Set address objects in ``target``/``targets`` aside while an operation is normalized and validated
    against its schema (where a target is a layer ID or name), and return the function that puts them back."""
    held: dict[str, dict[str, Any]] = {}

    def hold(value: Any, field: str) -> Any:
        if not isinstance(value, dict):
            return value
        require(0 < len(value) <= 8 and all(isinstance(k, str) and isinstance(v, (str, int, float))
                                            and not isinstance(v, bool) for k, v in value.items()),
                f"{field} as an address is a small object of names, such as a chart mark "
                '{"chart": "sales", "series": "Tea", "category": "Dec"}', field=field)
        token = f"{_ADDRESS}{len(held)}"
        held[token] = value
        return token

    for key in ("target", "targets"):
        if isinstance(op.get(key), dict):
            op[key] = hold(op[key], key)
        elif isinstance(op.get(key), list):
            op[key] = [hold(value, f"{key}[{index}]") for index, value in enumerate(op[key])]

    def restore(result: dict[str, Any]) -> None:
        if not held:
            return
        if result.get("target") in held:
            result["target"] = held[result["target"]]
        if isinstance(result.get("targets"), list):
            result["targets"] = [held.get(value, value) if isinstance(value, str) else value
                                 for value in result["targets"]]

    return restore


def resolve_addresses(project: Any, op: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    """``op`` with every address object in ``target``/``targets`` replaced by the layer IDs it names (the
    ``target-resolver`` plugin hook). An address that names several layers becomes ``targets`` where the
    operation takes a list, and is an error where it takes one layer."""
    single, listed = op.get("target"), op.get("targets")
    if not isinstance(single, dict) and not (isinstance(listed, list) and any(isinstance(t, dict) for t in listed)):
        return op
    from . import plugins

    def layers(address: dict[str, Any], field: str) -> list[str]:
        found = plugins.first("target-resolver", project, address)
        if found is None:
            raise VixlError("invalid_operation", f"{field} is an address no plugin resolves; a chart mark is "
                            '{"chart": NAME, "series": NAME, "category": NAME, "part": ...}, any other target a '
                            "layer ID or name", field=field)
        return list(found)

    op, kind = dict(op), kind or op.get("type")
    if isinstance(listed, list):
        flat: list[str] = []
        for index, value in enumerate(listed):
            for ident in layers(value, f"targets[{index}]") if isinstance(value, dict) else [value]:
                if ident not in flat:
                    flat.append(ident)
        op["targets"] = flat
    if isinstance(single, dict):
        found = layers(single, "target")
        if len(found) == 1:
            op["target"] = found[0]
        elif mode(str(kind)) != "one" and "targets" not in op:
            del op["target"]
            op["targets"] = found
        else:
            raise VixlError("invalid_operation", f"{kind} takes one layer; this address names {len(found)}. Narrow "
                            "it with series, category or part", field="target")
    return op


def fan_out(op: dict[str, Any]) -> list[dict[str, Any]]:
    """The single-layer operations an ``each`` operation with ``targets`` stands for."""
    if op.get("type") not in EACH or "targets" not in op:
        return [op]
    targets = op["targets"]
    require(isinstance(targets, list) and 1 <= len(targets) <= MAX_TARGETS,
            f"targets must list 1–{MAX_TARGETS} layers", field="targets")
    rest = {key: value for key, value in op.items() if key != "targets"}
    return [{**rest, "target": target} for target in targets]


def markdown_table(variants: list[dict[str, Any]] | None = None) -> str:
    """The docs table of which operations take target, targets, or both, generated from the schema."""
    if variants is None:
        from .schema import operation_schema

        variants = operation_schema()["properties"]["operations"]["items"]["oneOf"]
    groups: dict[str, list[str]] = {"each": [], "joint": [], "one": []}
    for variant in variants:
        groups[variant["x-targets"]].append(variant["properties"]["type"]["const"])
    rows = [
        ("each", "`target` or `targets`", "Applied to each listed layer in turn (one atomic batch)"),
        ("joint", "`targets` (where required, a lone `target` is a one-layer list)",
         "The listed layers are handled together"),
        ("one", "`target` (`targets` with one entry is accepted)", "One layer, or no layer at all"),
    ]
    lines = ["| Operations | Takes | A list means |", "| --- | --- | --- |"]
    for key, takes, meaning in rows:
        lines.append(f"| {', '.join(f'`{kind}`' for kind in sorted(groups[key]))} | {takes} | {meaning} |")
    return "\n".join(lines)
