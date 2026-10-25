"""Which palette color became which role, and why.

``layout-apply`` and ``palette-apply`` turn a list of colors into role swatches (``@background``,
``@surface``, ``@ink``, ``@muted``, ``@accent``, ``@accent-text``, ``@on-accent``; a direction with two or three
accents adds ``@accent-2`` and ``@accent-3`` with their ``-text`` variants). By default the
roles come from luminance and chroma and follow light or dark mode, so a palette passed as
"background, surface, accents" can come back rearranged. These helpers record the decision so
it can be echoed in the result: for every role the color, whether it is a palette entry (and
which) or derived, and a one-line reason. ``keep_order`` and explicit role maps are the ways to
take the decision back.
"""

from .errors import VixlError, require

ROLES = ("background", "surface", "ink", "muted", "accent", "accent-text", "on-accent")
# Added by a direction with two or three accents (accent_count), only for the accents its layout draws.
EXTRA_ROLES = ("accent-2", "accent-2-text", "accent-3", "accent-3-text")


def accent_roles(count):
    """The fill roles of ``count`` accents, first accent first: ``["accent", "accent-2", …]``."""
    return ["accent", *(f"accent-{n}" for n in range(2, count + 1))]


def hue_distance(a, b):
    """The angle between two hues in degrees (0-180)."""
    turn = abs(a - b) % 360
    return min(turn, 360 - turn)


def extra_accents(candidates, accent, count, *, derive=True, ordered=False):
    """``[(rgba, source)]`` for accent-2 … accent-``count``: the most colourful of ``candidates`` (the first, when
    ``ordered``) whose OKLCH hue is at least ``min_hue_distance`` degrees from every accent chosen so far, else, when
    ``derive``, the first ``accent`` turned at the same lightness and chroma by the first ``rotation`` that lands as
    far from every chosen accent. ``source``
    is ``palette`` or ``derived``. Without ``derive`` (colours the caller fixed) the list can come back shorter."""
    from . import house_style
    from .colors import from_polar, gamut_map, srgb_to_oklab, to_polar

    rules = house_style.accents()

    def lch(color):
        return to_polar(srgb_to_oklab(color[:3]))

    chosen, result = [lch(accent)], []
    for index in range(count - 1):
        pool = [c for c in candidates if lch(c)[1] >= rules["min_chroma"] and all(c != r for r, _ in result)
                and all(hue_distance(lch(c)[2], hue) >= rules["min_hue_distance"] for _, _, hue in chosen)]
        if pool:
            pick, source = (pool[0] if ordered else max(pool, key=lambda c: lch(c)[1])), "palette"
        elif derive and chosen[0][1] < rules["min_chroma"]:
            # A grey turned in hue stays the same grey: its next accents are lighter tones (darker on a light grey).
            light, chroma, hue = chosen[0]
            step = rules["tone_step"] * (index + 1) * (1 if light < 0.5 else -1)
            pick, source = gamut_map(from_polar((min(max(light + step, 0.1), 0.95), chroma, hue))) + (1.0,), "toned"
        elif derive:
            light, chroma, hue = chosen[0]

            def apart(turn):
                return min(hue_distance((hue + turn) % 360, other) for _, _, other in chosen)

            turns = rules["rotation"]
            turn = next((t for t in turns if apart(t) >= rules["min_hue_distance"]), max(turns, key=apart))
            pick, source = gamut_map(from_polar((light, chroma, (hue + turn) % 360))) + (1.0,), "derived"
        else:
            break
        chosen.append(lch(pick))
        result.append((pick, source))
    return result


def accent_reasons(count, sources=(), adjusted=()):
    """Reasons for the roles an accent count changes: none (accents take ink and muted) or accent-2/accent-3."""
    if count == 0:
        return {"accent": "no accent rolled (accent_count 0): accent shapes take the ink color",
                "accent-text": "no accent rolled (accent_count 0): accent text takes the muted color",
                "on-accent": "whichever of background, ink, white or black reads best on the ink-colored accent"}
    from . import house_style

    rules = house_style.accents()
    reasons = {}
    for index, source in enumerate(sources):
        role = f"accent-{index + 2}"
        reasons[role] = {"palette": f"next most colorful palette color whose hue is at least "
                                    f"{rules['min_hue_distance']}° from the accents before it",
                         "derived": f"the accent turned in hue at the same lightness and chroma (no palette color is "
                                    f"{rules['min_hue_distance']}° from the accents before it)",
                         "toned": "a lighter or darker tone of the grey accent, which has no hue to turn",
                         "explicit": "set in colors"}[source]
        if role in adjusted:
            reasons[role] += ", nudged until it reads 3:1 on the background and surface"
        reasons[f"{role}-text"] = (f"{role} adjusted until small text in it reads 4.5:1" if f"{role}-text" in adjusted
                                   else f"{role} itself already reads on the background")
    return reasons


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


def describe(colors, roles, *, mode, mode_source, keep_order=False, policy="accessible", explicit_roles=(), adjusted=(),
             reasons=None):
    """The role mapping with a source and reason per role. ``adjusted`` lists roles nudged for contrast; ``reasons``
    replaces the reason of some roles (``accent_reasons``) and lists the extra accent roles present in ``roles``."""
    from .colors import hex_of, parse

    palette = [hex_of(parse(c)) for c in colors]

    def source(role):
        try:
            value = hex_of(parse(roles[role]))
        except VixlError:  # an @swatch or expression: not a palette entry
            return "derived"
        return f"palette[{palette.index(value)}]" if value in palette else "derived"

    extreme = "darkest" if mode == "light" else "lightest"
    table = {
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
    table.update(reasons or {})
    entries = []
    for role in (*ROLES, *(role for role in EXTRA_ROLES if role in roles)):
        mine = role in explicit_roles
        entries.append({"role": role, "color": roles[role], "source": "explicit" if mine else source(role),
                        "reason": "set by you in roles/colors" if mine else table.get(role, "")})
    return entries


def notes(*, keep_order, mode, mode_source, explicit_roles):
    result = [f"mode is {mode} ({mode_source}); light mode puts the lightest palette color behind the work and dark mode "
              "the darkest, whatever order the palette was given in"] if not keep_order else []
    if not keep_order and not explicit_roles:
        result.append("To keep your order, pass keep_order: true (colors are used as background, surface, then accents) "
                      "or set roles yourself with colors/roles: {background: '#…', accent: '#…'}")
    return result
