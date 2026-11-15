"""Registry hooks for PSD import."""


def import_psd(project, data, format, *, name="import", mode="editable", **options):
    if format != "psd":
        return None
    from .psd_import import import_psd as run

    return run(project, data, name=name, mode=mode)
