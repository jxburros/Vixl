"""Which fonts a service client (REST, MCP) may name in operations.

Service clients cannot make the server read a font file, so ``font`` accepts a font role
(``heading``, ``body`` or another typography role), a text stage (``h1``, ``caption`` …), the bundled proofing font, the name of a font already registered in the
document (``font-install``, ``font-pair`` or ``import-font`` register one), or the name of a font installed on the
server (``system_fonts``: found only in the host's font folders, never a client path; ``VIXL_SYSTEM_FONTS=off``
turns it off). An installed face whose licence restricts embedding is refused, since the client gets the document. The same
rule covers ``display_font``, the fonts set on rich-text spans and ``font=`` in rich-text Markdown.
"""

import difflib

from .constants import BUNDLED_FONTS
from .errors import VixlError

ROLES = ("heading", "body", *BUNDLED_FONTS[:2])
FIELDS = ("font", "display_font")
INSTALL = ("Install one with a font-install or font-pair step (or import a workspace font file with an "
           "import-font step), then pass the registered name or a role (heading, body); a font installed on the server "
           "is named by family, style or PostScript name")


def allowed_fonts(project):
    """Names a client may use in this document: roles, registered fonts and embedded font files."""
    from .type_roles import STAGES

    return {*ROLES, *STAGES, *(project.state.get("typography") or {}), *project.state.get("fonts", {}),
            *(name for name in project.assets if name.startswith("fonts/"))}


def named_fonts(operation):
    """``[(field, font)]`` for every font an operation names, including rich-text spans."""
    named = [(key, operation[key]) for key in FIELDS if key in operation]
    spans = operation.get("spans")
    if operation.get("type") == "rich-text":
        if isinstance(operation.get("markdown"), str):
            from .richtext import parse_markdown

            try:
                spans = parse_markdown(operation["markdown"])[0]
            except VixlError:
                spans = None  # Malformed markup is reported when the operation runs.
        for span in spans if isinstance(spans, list) else ():
            if isinstance(span, dict) and "font" in span:
                named.append(("spans.font", span["font"]))
    return named


def check_fonts(operation, allowed):
    """Reject a font that is not a role or registered in the document, pointing to the install path."""
    from .system_fonts import RESTRICTED, lookup

    for field, font in named_fonts(operation):
        if font in allowed:
            continue
        if not isinstance(font, str) or "/" in font or "\\" in font or font.startswith("."):
            raise VixlError(
                "forbidden",
                f"{field} {font!r} looks like a file path, which services cannot read. {INSTALL}.",
                field=field,
                allowed=sorted(name for name in allowed if not name.startswith("fonts/")),
            )
        face = lookup(font)
        if face is not None:
            if face["embedding"] in RESTRICTED:
                raise VixlError(
                    "forbidden",
                    f"{field} {font!r} is the installed font {face['family']} {face['style']}, whose embedding "
                    f"permission is {face['embedding']!r}: a service cannot embed it in a client's document. "
                    "Choose another installed family or an open-licensed one (font-install).",
                    field=field,
                )
            continue  # An installed face, by family, style or PostScript name: read from the host's font folders.
        raise missing_font(field, font, allowed)


def missing_font(field, font, allowed):
    """The ``missing_font`` error for a font name that is not a role, registered in the document or installed."""
    from .system_fonts import suggest

    close = difflib.get_close_matches(font, sorted(allowed), 3, 0.5)
    close += [name for name in suggest(font) if name not in close]
    return VixlError(
        "missing_font",
        f"{field} {font!r} is not registered in this document"
        + (f"; did you mean {' or '.join(map(repr, close))}?" if close else "")
        + f". Registered: {', '.join(sorted(n for n in allowed if not n.startswith('fonts/'))) or 'none'}. {INSTALL}.",
        field=field,
        allowed=sorted(name for name in allowed if not name.startswith("fonts/")),
        suggestions=close,
    )


def checker(project, check):
    """``check`` (the service operation check) bound to a document's fonts. A font registered by an
    earlier ``font-register`` in the same batch counts too."""
    allowed = allowed_fonts(project)

    def bound(operation):
        check(operation, allowed)
        if operation.get("type") == "font-register" and isinstance(operation.get("name"), str):
            allowed.add(operation["name"])

    return bound


def checked_font_map(project, font_map):
    """``font_map`` (``{source family: registered name}``, SVG and PDF import) validated: string keys, each value
    a font name ``project`` can use, as a service client may."""
    from .errors import require

    if not font_map:
        return {}
    require(isinstance(font_map, dict) and all(isinstance(key, str) and key.strip() and isinstance(value, str)
                                               for key, value in font_map.items()),
            "font_map maps source font family names to registered font names", field="font_map")
    allowed = allowed_fonts(project)
    for value in font_map.values():
        if value not in allowed:
            raise missing_font("font_map", value, allowed)
    return dict(font_map)
