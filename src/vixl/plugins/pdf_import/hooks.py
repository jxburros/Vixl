"""Registry hooks for PDF import."""


def import_pdf(project, data, format, *, name="import", page=1, dpi=None, mode="editable", font_map=None,
               install_fonts=False, **options):
    if format != "pdf":
        return None
    from .pdf_import import import_pdf as run

    return run(project, data, name=name, page=page, dpi=dpi, mode=mode, font_map=font_map, install_fonts=install_fonts)
