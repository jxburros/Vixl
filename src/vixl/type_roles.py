"""Font roles and text stages.

A **font role** names a typeface in the document typography (``state["typography"]``: role → registered
font). ``heading`` and ``body`` always exist as roles; a brand or ``font-register role=NAME`` can add any
other (``accent``, ``hand``, ``mono`` …).

A **text stage** is a rung of the type ladder: display, h1, h2, h3, subtitle, lead, body, caption,
citation and label. Each stage has a font role, a type-scale step, a line-height entry and an optional
case (craft ``type_stages`` in the house style). A document may override them in ``state["type_stages"]``
(a workspace brand's ``stages`` are copied there), and a stage may get its own typeface by registering a
font with that stage as the role. Without either, display and h1–h3 inherit ``heading`` and the rest
inherit ``body``, so two fonts cover the whole ladder and up to four can be spread across it.
"""

from copy import deepcopy
import math
import re

from . import house_style
from .errors import require

ROLE_NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")
CASES = ("upper", "lower", "title")
STAGE_FIELDS = ("font", "step", "line_height", "case")
# Stages a plain text layer is matched to by its size (B2: heading faces from the title step up).
_LARGE = ("h2", "h1", "display")
_SMALL = ("body", "lead", "caption")


def stages():
    return tuple(house_style.rule("type_stages"))


STAGES = stages()


def role_name(name, field="role"):
    require(isinstance(name, str) and ROLE_NAME.fullmatch(name),
            f"{field} must be a lowercase role name such as heading, body, accent or h2 (letters, digits, hyphens)",
            field=field)
    return name


def validate_stages(value, field="stages"):
    """``{stage: role}`` or ``{stage: {font, step, line_height, case}}`` overrides; returns the normalized dict."""
    from .layouts import ROLE_STEPS

    require(isinstance(value, dict), f"{field} maps text stages to a font role or settings", field=field)
    out = {}
    for stage, spec in value.items():
        require(stage in STAGES, f"Unknown text stage {stage!r}; stages: {', '.join(STAGES)}", field=field,
                allowed=list(STAGES))
        spec = {"font": spec} if isinstance(spec, str) else spec
        require(isinstance(spec, dict) and set(spec) <= set(STAGE_FIELDS),
                f"{field}.{stage} takes a font role or an object with {', '.join(STAGE_FIELDS)}", field=field)
        if "font" in spec:
            role_name(spec["font"], f"{field}.{stage}.font")
        if "step" in spec:
            require(spec["step"] in ROLE_STEPS, f"{field}.{stage}.step must be one of {', '.join(ROLE_STEPS)}",
                    field=field)
        if "line_height" in spec:
            value_ = spec["line_height"]
            require(value_ in house_style.rule("line_height") or (isinstance(value_, (int, float))
                                                                  and not isinstance(value_, bool)
                                                                  and 0.5 <= value_ <= 5),
                    f"{field}.{stage}.line_height is a multiple (0.5–5) or one of "
                    f"{', '.join(house_style.rule('line_height'))}", field=field)
        if spec.get("case") is not None:
            require(spec["case"] in CASES, f"{field}.{stage}.case must be upper, lower, title or null", field=field)
        out[stage] = dict(spec)
    return out


def stage_table(project=None):
    """Every stage's settings: the house defaults with the document's ``type_stages`` overrides."""
    table = deepcopy(house_style.rule("type_stages"))
    overrides = (project.state.get("type_stages") or {}) if project is not None else {}
    for stage, spec in overrides.items():
        if stage in table and isinstance(spec, dict):
            table[stage].update(spec)
    return table


def is_role(project, name):
    """Whether a font name refers to a role or stage (resolved through the typography) rather than a font.
    A registered font that happens to share a stage's name keeps meaning that font."""
    if not isinstance(name, str):
        return False
    typography = project.state.get("typography") or {}
    if name in ("heading", "body") or name in typography:
        return True
    return name in STAGES and name not in project.state.get("fonts", {})


def role_font(project, role, _seen=None):
    """The registered font a role or stage uses, following stage inheritance; None when nothing sets it."""
    typography = project.state.get("typography") or {}
    if typography.get(role):
        return typography[role]
    seen = (_seen or set()) | {role}
    if role in STAGES:
        default = house_style.rule("type_stages")[role]["font"]
        for parent in (stage_table(project)[role].get("font"), default):
            if parent and parent not in seen:
                found = role_font(project, parent, seen)
                if found:
                    return found
    return None


def roles(project):
    """Role names the document knows: heading, body, its typography roles and the stages."""
    typography = project.state.get("typography") or {}
    return list(dict.fromkeys(["heading", "body", *typography, *STAGES]))


def stage_size(project, stage):
    """A stage's size in pixels: its type-scale step from the document's character styles, else from the
    body size and the house scale (perfect fourth)."""
    from .craft import body_size
    from .layouts import RATIOS, ROLE_STEPS

    step = stage_table(project)[stage]["step"]
    style = (project.state.get("character_styles") or {}).get(step) or {}
    size = style.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0:
        return max(1, round(size))
    return max(1, round(body_size(project) * RATIOS["perfect-fourth"] ** ROLE_STEPS[step]))


def stage_line_height(project, stage):
    value = stage_table(project)[stage]["line_height"]
    return value if isinstance(value, (int, float)) else house_style.rule("line_height")[value]


def stage_for_size(project, size):
    """The stage a size reads as: from the title step (h2) up a heading stage, below it lead, body or caption."""
    sizes = {stage: stage_size(project, stage) for stage in (*_LARGE, *_SMALL)}
    pool = _LARGE if size >= sizes["h2"] else _SMALL
    return min(pool, key=lambda stage: abs(math.log(max(size, 1) / sizes[stage])))


def apply_case(text, case):
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return text.title()
    return text


def expand(project, op, new):
    """Read ``stage`` on a text or text-set operation: the stage's font (when the document has one for it),
    size, line height and case fill whatever the operation leaves out. A new text layer without font or
    stage takes the stage its size reads as once the document has typography."""
    if "stage" not in op and not (new and "font" not in op):
        return op
    op = dict(op)
    stage = op.pop("stage", None)
    typography = project.state.get("typography") or {}
    if stage is None:
        if typography.get("body"):
            from .craft import body_size

            op["font"] = stage_for_size(project, op.get("size", body_size(project)))
        return op
    require(stage in STAGES, f"Unknown text stage {stage!r}; stages: {', '.join(STAGES)}", field="stage",
            allowed=list(STAGES))
    spec = stage_table(project)[stage]
    if "font" not in op and role_font(project, stage):
        op["font"] = stage
    if "size" not in op:
        op["size"] = stage_size(project, stage)
    if "line_height" not in op and "spacing" not in op:
        op["line_height"] = stage_line_height(project, stage)
    if spec.get("case") and isinstance(op.get("text"), str):
        op["text"] = apply_case(op["text"], spec["case"])
    return op


def refont(project):
    """After the typography changed: give every text layer that follows a role its role's current font."""
    from .render import text_metrics

    fonts = project.state.get("fonts", {})
    for layer in project.state["layers"]:
        role = layer.get("font_role")
        if layer["type"] != "text" or not role:
            continue
        name = role_font(project, role)
        if name and fonts.get(name) and layer.get("font") != fonts[name]:
            layer["font"] = fonts[name]
            if layer.get("auto_size", True):
                layer["width"], layer["height"], _ = text_metrics(project, layer)


def describe(project=None):
    """The stage ladder for docs and inspect: each stage's font role, the font it resolves to, size and line height."""
    table = stage_table(project)
    out = {}
    for stage, spec in table.items():
        item = {"font_role": spec["font"], "step": spec["step"], "line_height": spec["line_height"]}
        if spec.get("case"):
            item["case"] = spec["case"]
        if project is not None:
            item["font"] = role_font(project, stage)
            item["size"] = stage_size(project, stage)
        out[stage] = item
    return out
