"""Registry hooks for Figma import."""


def import_figma(project, data, format, *, page=1, **options):
    if format != "figma":
        return None
    from .figma_import import import_source

    return import_source(project, data, page=page, **options)
