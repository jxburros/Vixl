"""Registry hooks for the font maker."""

from ...errors import require
from .fontmaker import FORMATS


def validate_state(project, state):
    from .fontmaker import validate

    validate(project, state)


def export(project, path, format, report, *, pages=None, page=None, artwork=False, isolate=None, **options):
    if format not in FORMATS:
        return None
    require(not (pages or page is not None or artwork or isolate), "A font export writes the document's font "
            "design (font-design, font-glyph); page, pages, isolate, profile, artboard, comp, proof, simulate and "
            "CMYK do not apply", field="format")
    from .fontmaker import export_font

    return export_font(project, path, format, report)
