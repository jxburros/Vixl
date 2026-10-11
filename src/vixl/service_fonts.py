"""Which fonts a service client (REST, MCP) may name in operations.

Service clients cannot make the server read a font file, so ``font`` accepts a font role
(``heading``, ``body`` or another typography role), a text stage (``h1``, ``caption`` …), the bundled proofing font, or the name of a font already registered in the
document (``vixl_font_install``, ``vixl_font_pair`` or ``vixl_import_font`` register one). The same
rule covers ``display_font``, the fonts set on rich-text spans and ``font=`` in rich-text Markdown.
"""

import difflib

from .errors import VixlError

ROLES = ("heading", "body", "DejaVuSans.ttf")
FIELDS = ("font", "display_font")
INSTALL = ("Install one with vixl_font_install or vixl_font_pair (or import a workspace font file with "
           "vixl_import_font), then pass the registered name or a role (heading, body)")


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
        close = difflib.get_close_matches(font, sorted(allowed), 3, 0.5)
        raise VixlError(
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
