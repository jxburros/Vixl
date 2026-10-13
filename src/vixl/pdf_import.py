"""PDF page import: one image of the page."""

import math

from .errors import VixlError, require


def _pdfium():
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[pdf] for PDF import") from exc
    return pdfium, raw


def import_pdf(project, data, *, name="import", page=1, dpi=None, mode="editable"):
    """``mode``: ``editable`` (the default) or ``auto`` read the page as layers; ``appearance`` renders it as one image
    at ``dpi`` (default 144). ``dpi`` applies to the image import only: vector content keeps its own scale."""
    require(isinstance(page, int) and page >= 1, "PDF page must be positive", field="page")
    require(dpi is None or (isinstance(dpi, (int, float)) and 36 <= dpi <= 600), "dpi must be 36–600", field="dpi")
    if mode == "appearance":
        return raster_page(project, data, name=name, page=page, dpi=dpi or 144)
    return raster_page(project, data, name=name, page=page, dpi=dpi or 144)


def raster_page(project, data, *, name, page, dpi, warnings=()):
    """The page rendered at ``dpi`` as one image layer."""
    pdfium, _ = _pdfium()
    candidate = project.clone()
    try:
        with pdfium.PdfDocument(data) as document:
            require(page <= len(document), "PDF page is out of range", field="page")
            source = document[page - 1]
            try:
                w, h = source.get_size()
                candidate.limits.size(math.ceil(w * dpi / 72), math.ceil(h * dpi / 72))
                bitmap = source.render(scale=dpi / 72)
                try:
                    from .assets import add_image

                    asset = add_image(candidate, bitmap.to_pil())
                finally:
                    bitmap.close()
            finally:
                source.close()
    except pdfium.PdfiumError as exc:
        raise VixlError("invalid_pdf", f"Cannot open PDF: {exc}") from exc
    result = candidate.apply({"type": "add", "asset": asset, "name": name}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return {**result, "page": page, "dpi": dpi, "mode": "appearance",
            "warnings": [*warnings, "PDF page imported as one image layer (svg_mode='appearance')."]}


