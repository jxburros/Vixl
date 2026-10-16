"""PDF import: a PDF page becomes editable vector, text and image layers."""

PLUGIN = {
    "name": "pdf_import",
    "title": "PDF import",
    "summary": "Import a PDF page as editable layers (needs the optional pypdfium2 package).",
    "kind": "importer",
    "modules": ["pdf_import", "hooks"],
    "hooks": {"import-format": ["hooks:import_pdf"]},
}
