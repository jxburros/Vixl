"""Which palette color became which role, and why.

``layout-apply`` and ``palette-apply`` turn a list of colors into role swatches (``@background``,
``@surface``, ``@ink``, ``@muted``, ``@accent``, ``@accent-text``, ``@on-accent``). By default the
roles come from luminance and chroma and follow light or dark mode, so a palette passed as
"background, surface, accents" can come back rearranged. These helpers record the decision so
it can be echoed in the result: for every role the color, whether it is a palette entry (and
which) or derived, and a one-line reason. ``keep_order`` and explicit role maps are the ways to
take the decision back.
"""

from .errors import VixlError, require

ROLES = ("background", "surface", "ink", "muted", "accent", "accent-text", "on-accent")


def role_schema():
    """JSON Schema for an explicit role map: role name to a #color/@swatch or a palette index."""
    return {"type": "object", "minProperties": 1, "description": f"Role ({', '.join(ROLES)}) to a color or palette index.",
            "additionalProperties": {"type": ["string", "integer"], "description": "A color, or a palette index (0-based)."}}


def explicit(colors, spec):
    """``{role: hex}`` for an explicit role map whose values are palette indexes or colors."""
    from .colors import hex_of, parse

    require(isinstance(spec, dict) and spec, "roles must map role names to colors or palette indexes", field="roles")
    result = {}
    for role, value in spec.items():
        require(role in ROLES, f"Unknown role {role!r}; roles are {', '.join(ROLES)}", field="roles", allowed=list(ROLES))
        if isinstance(value, int) and not isinstance(value, bool):
            require(0 <= value < len(colors), f"roles.{role}: palette index {value} is out of range (0-{len(colors) - 1})",
                    field="roles")
            value = colors[value]
        require(isinstance(value, str), f"roles.{role} must be a color or a palette index", field="roles")
        result[role] = hex_of(parse(value))
    return result


def describe(colors, roles, *, mode, mode_source, keep_order=False, policy="accessible", explicit_roles=(), adjusted=()):
    """The role mapping with a source and reason per role. ``adjusted`` lists roles nudged for contrast."""
    from .colors import hex_of, parse

    palette = [hex_of(parse(c)) for c in colors]

    def source(role):
        try:
            value = hex_of(parse(roles[role]))
        except VixlError:  # an @swatch or expression: not a palette entry
            return "derived"
        return f"palette[{palette.index(value)}]" if value in palette else "derived"

    extreme = "darkest" if mode == "light" else "lightest"
    reasons = {
        "background": (f"{'first' if keep_order else extreme} palette color" +
                       ("" if keep_order else f" because mode is {mode} ({mode_source})")),
        "surface": ("second palette color" if keep_order and source("surface") != "derived" else
                    "background nudged toward ink for panels"),
        "ink": ("derived from the background for 7:1 contrast (ink is not part of the palette order)" if keep_order
                else f"{'darkest' if mode == 'light' else 'lightest'} palette color, nudged until it reads 7:1 on the background"),
        "muted": "ink blended toward the background, kept at 4.5:1 for secondary text",
        "accent": ("first accent in the palette order" if keep_order else "most colorful palette color that is not the background or ink"),
        "accent-text": "accent adjusted until small text in it reads 4.5:1" if "accent-text" in adjusted or source("accent-text") == "derived"
                       else "the accent itself already reads on the background",
        "on-accent": "whichever of background, ink, white or black reads best on the accent",
    }
    entries = []
    for role in ROLES:
        mine = role in explicit_roles
        entries.append({"role": role, "color": roles[role], "source": "explicit" if mine else source(role),
                        "reason": "set by you in roles/colors" if mine else reasons[role]})
    return entries


def notes(*, keep_order, mode, mode_source, explicit_roles):
    result = [f"mode is {mode} ({mode_source}); light mode puts the lightest palette color behind the work and dark mode "
              "the darkest, whatever order the palette was given in"] if not keep_order else []
    if not keep_order and not explicit_roles:
        result.append("To keep your order, pass keep_order: true (colors are used as background, surface, then accents) "
                      "or set roles yourself with colors/roles: {background: '#…', accent: '#…'}")
    return result
