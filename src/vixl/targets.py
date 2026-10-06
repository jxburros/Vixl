"""``target`` and ``targets``: how every operation that acts on existing layers names them.

Every such operation accepts ``target`` (one layer) and ``targets`` (a list). What a list means
depends on the operation, and the schema says which (``x-targets`` on each variant):

- ``each``: the operation is applied to every listed layer in turn, inside the same atomic batch
  (``opacity``, ``move``, ``layer-intent``, the effects ...). An error names the original operation.
- ``joint``: the layers are handled together (``group``, ``align``, ``distribute`` ...); a lone
  ``target`` is read as a one-item list where the operation requires ``targets``.
- ``one``: the operation takes a single layer (``rename``, ``select-layer`` ...); ``targets`` with
  one entry is read as ``target``, and a longer list is an error that says so.

The docs table in docs/operations.md is generated from the schema by ``markdown_table``.
"""

from .errors import VixlError, require
from .render import EFFECTS

MAX_TARGETS = 512
ALIASES = ("layers", "layer_ids", "layerIds", "target_ids", "targetIds")

# Operations applied once per listed layer. Creation operations (shape, text, solid, gradient)
# take targets to edit several existing layers in place.
EACH = frozenset({
    "text-set", "text-style", "remove", "hide", "show", "raise", "lower", "top", "bottom", "rasterize", "unconstrain",
    "duplicate", "move", "resize", "scale", "rotate", "pivot", "opacity", "blend", "flip", "crop", "constrain",
    "effect", *EFFECTS, "effect-disable", "effect-enable", "effect-move", "effect-remove", "effect-set", "layer-style",
    "style-apply", "lut", "lookup", "layer-intent", "fit-text", "path-fit", "shape-to-path", "path-simplify",
    "path-smooth", "offset-path", "outline-stroke", "round-corners", "distort", "skew", "transform", "fit",
    "snap-to-pixel", "keyframe-remove", "shape", "text", "solid", "gradient", "ungroup", "link-refresh",
    "link-embed", "replace-contents", "pattern-fill", "text-animate",
})
# Operations that already take targets themselves and apply to each listed layer.
OWN_EACH = frozenset({"keyframe", "animate", "animate-preset", "look", "irregular", "cut-paper", "motion", "snap",
                      "match-size"})
# Operations that act on the listed layers together.
JOINT = frozenset({"align", "group", "distribute", "artboard", "pathfinder", "suite-capture", "role-set",
                   "arrange-grid", "adapt-layout", "stack", "place"})

DESCRIPTION = ("Several layer IDs or names: the operation is applied to each in turn, in this order, within the "
               "same atomic batch. Pass target or targets, not both.")


def mode(kind):
    """``each``, ``joint`` or ``one`` (operations without a layer list)."""
    if kind in EACH or kind in OWN_EACH:
        return "each"
    return "joint" if kind in JOINT else "one"


def enrich(variants):
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


def normalize(op, kind, allowed, required, note):
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


def fan_out(op):
    """The single-layer operations an ``each`` operation with ``targets`` stands for."""
    if op.get("type") not in EACH or "targets" not in op:
        return [op]
    targets = op["targets"]
    require(isinstance(targets, list) and 1 <= len(targets) <= MAX_TARGETS,
            f"targets must list 1–{MAX_TARGETS} layers", field="targets")
    rest = {key: value for key, value in op.items() if key != "targets"}
    return [{**rest, "target": target} for target in targets]


def markdown_table(variants=None):
    """The docs table of which operations take target, targets, or both, generated from the schema."""
    if variants is None:
        from .schema import operation_schema

        variants = operation_schema()["properties"]["operations"]["items"]["oneOf"]
    groups = {"each": [], "joint": [], "one": []}
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
