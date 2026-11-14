"""Guide sets: a printer product's guides saved as a ``guide-sets`` resource, and the operation that applies one.

A guide set is ``{width, height, guides: {name: guide}, description?, source?}``: the role guides read from a
template (``guides-import … save``) or saved from a document (``guide-set-save``), with the canvas size they were
made for. ``guide-set`` puts them on another document, scaled when it has the same proportions at another size.
"""

from copy import deepcopy

from ...errors import require
from ...guides import MAX_GUIDES, ROLES, validate_guide

TYPES = ("guide-set",)
KIND = "guide-sets"
FITS = ("scale", "stretch", "none")
ASPECT_TOLERANCE = 0.01


def schemas(add):
    from ...schema import B, S, field

    add("guide-set", {
        "name": field(S, "The saved guide set (a guide-sets resource: guides-import with save, or guide-set-save)."),
        "fit": {"enum": list(FITS), "description": "How the set's guides meet this canvas: scale (default) keeps "
                "them as they are on a canvas of the set's size and scales them on one with the same proportions; "
                "stretch scales each axis on its own; none keeps the set's pixel positions."},
        "prefix": field(S, "Put this before every guide name (PREFIX-safe-1), to hold two sets side by side."),
        "replace": field(B, "Remove the document's guides that carry a role first (default false: guides with the "
                            "same names are replaced, others stay)."),
    }, ["name"], description="Put a saved guide set (a printer product's safe areas, keep-outs, folds and trim) on "
                             "this document; the safe_area check then enforces it.")


def validate(value):
    """A guide-sets resource value."""
    from ...model import Limits

    require(isinstance(value, dict) and set(value) <= {"width", "height", "guides", "description", "source"},
            "A guide set is {width, height, guides, description?, source?}", field="value")
    require(all(isinstance(value.get(key), int) and not isinstance(value.get(key), bool) for key in ("width", "height")),
            "A guide set needs the width and height (whole pixels) of the canvas it was made for", field="value")
    Limits().size(value["width"], value["height"])
    guides = value.get("guides")
    require(isinstance(guides, dict) and 0 < len(guides) <= MAX_GUIDES, f"A guide set holds 1 to {MAX_GUIDES} guides",
            field="value")
    for name, guide in guides.items():
        validate_guide(name, guide)
    for key in ("description", "source"):
        require(isinstance(value.get(key, ""), str) and len(value.get(key, "")) <= 500,
                f"A guide set's {key} is text of at most 500 characters", field="value")
    return value


def resource_kind(kind):
    """The ``resource-kind`` hook: the ``guide-sets`` resource category."""
    return {"builtins": {}, "validate": validate} if kind == KIND else None


resource_kind.KINDS = (KIND,)


def scale_for(size, canvas, fit, what="The guide set"):
    """(sx, sy) from a set or template of ``size`` to ``canvas`` under ``fit``."""
    require(fit in FITS, f"fit must be one of {', '.join(FITS)}", field="fit", allowed=list(FITS))
    sx, sy = canvas["width"] / size[0], canvas["height"] / size[1]
    if fit == "none" or (sx == 1 and sy == 1):
        return 1.0, 1.0
    if fit == "scale":
        require(abs(sx / sy - 1) <= ASPECT_TOLERANCE,
                f"{what} is {size[0]}×{size[1]} and this canvas is {canvas['width']}×{canvas['height']}: the "
                "proportions differ. Make the document at the template's proportions, or pass fit: 'stretch' "
                "(scale each axis) or fit: 'none' (keep the pixel positions)", field="fit")
    return sx, sy


def scaled(guide, sx, sy):
    """``guide`` scaled to another canvas and snapped to whole pixels."""
    guide = deepcopy(guide)
    if (sx, sy) == (1.0, 1.0):
        return guide
    kind = guide.get("kind", "axis")
    if kind == "axis":
        guide["position"] = round(guide["position"] * (sx if guide["axis"] == "x" else sy))
    elif kind == "segment":
        guide["points"] = [[round(x * sx), round(y * sy)] for x, y in guide["points"]]
    elif kind == "path":
        from ...geometry import compact_number, parse_path

        parts = []
        for command, values in parse_path(guide["d"]):
            moved = [round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(values)]
            part = " ".join([command, *(compact_number(v, 3) for v in moved)])
            if command == "Z" and len(parts) > 1 and parts[-1][1:] == parts[0][1:]:
                parts.pop()  # the parser spells out the closing line back to the start
            parts.append(part)
        guide["d"] = " ".join(parts)
    else:
        guide["x"], guide["y"] = guide["x"] * sx, guide["y"] * sy
        if kind == "circle":
            guide["radius"] = guide["radius"] * (sx * sy) ** 0.5
    return guide


def place(project, guides, *, prefix=None, replace=False):
    """Write ``guides`` into the document (inside an apply batch). Returns their names."""
    from ...design import named

    current = project.state.setdefault("guides", {})
    if replace:
        for name in [name for name, guide in current.items() if guide.get("role") in ROLES]:
            del current[name]
    names = []
    for name, guide in guides.items():
        name = named(f"{prefix}-{name}" if prefix else name)
        validate_guide(name, guide)
        current[name] = deepcopy(guide)
        names.append(name)
    require(len(current) <= MAX_GUIDES, f"A document holds at most {MAX_GUIDES} guides", "resource_limit")
    return names


def execute(project, op):
    from ...resources import get

    value = get(KIND, op["name"], workspace=getattr(project, "_workspace", None))
    sx, sy = scale_for((value["width"], value["height"]), project.state["canvas"], op.get("fit", "scale"),
                       f"Guide set {op['name']!r}")
    guides = {name: scaled(guide, sx, sy) for name, guide in value["guides"].items()}
    place(project, guides, prefix=op.get("prefix"), replace=bool(op.get("replace")))


def compile_command(cmd, args):
    """``vixl guide-set NAME [--fit scale|stretch|none] [--prefix P] [--replace]``."""
    if cmd not in TYPES:
        return None
    from ...commands import Parser

    p = Parser(prog="vixl guide-set")
    p.add_argument("name")
    p.add_argument("--fit", choices=list(FITS))
    p.add_argument("--prefix")
    p.add_argument("--replace", action="store_true", default=None)
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
