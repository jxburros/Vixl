"""Registry hooks for PDF import."""


def import_pdf(project, data, format, *, name="import", page=1, dpi=None, mode="editable", **options):
    if format != "pdf":
        return None
    from .pdf_import import import_pdf as run

    return run(project, data, name=name, page=page, dpi=dpi, mode=mode)
