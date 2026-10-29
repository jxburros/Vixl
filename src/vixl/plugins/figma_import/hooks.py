"""Registry hooks for Figma import."""


def import_figma(project, data, format, *, page=1, **options):
    if format != "figma":
        return None
    from .figma_import import import_source

    return import_source(project, data, page=page, **options)


def export_figma(project, path, format, report, *, pages=None, page=None, artwork=False, variables=None, **options):
    if format != "figma":
        return None
    from ...errors import require
    from .figma_export import export_figma as write

    require(not artwork, "Figma export keeps editable RGB pages; profile, artboard, comp, proof, simulate and "
            "CMYK do not apply", field="format")
    # The dispatcher has already enforced its overwrite policy before invoking any plugin.
    return write(project, path, pages=pages, page=page, variables=variables, overwrite=True, report=report)
