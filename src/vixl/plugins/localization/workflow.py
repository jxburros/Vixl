"""Workflow actions for localization: the locale check, localize fan-out and group locale tables."""

from pathlib import Path

from ...errors import require

LOCALE_FIELDS = {"locales", "strings", "key_column", "languages", "source", "same_ok", "fonts", "rtl", "mirror",
                 "fit", "min_size", "checks", "suites", "suite", "fail_on"}
ACTIONS = {
    "locale-check": (LOCALE_FIELDS | {"variables", "format", "output", "overwrite"}, set()),
    "localize": (LOCALE_FIELDS | {"output_dir", "documents", "formats", "spec", "overwrite"}, set()),
    "group-locales": ({"name", "locales", "replace"}, {"name", "locales"}),
}

CODE = {"type": "string", "description": "A locale code such as de, ja or pt-BR."}
TABLE = {"type": "object", "description": "{locale code: {variable: value}}; a null table removes a locale, a null "
                                          "value removes a key.",
         "additionalProperties": {"type": ["object", "null"], "description": "One locale's variable values.",
                                  "additionalProperties": {"type": ["string", "number", "boolean", "null"],
                                                           "description": "The value in this locale."}}}
COMMON = {
    "locales": {"type": ["string", "array"], "items": CODE,
                "description": "all (every locale but the source; the default), a comma-separated list such as "
                               "de,ja, or a list of codes."},
    "strings": {"type": "string", "description": "Workspace-relative strings CSV: one row per key, one column per "
                                                 "locale. Its values win over the document's; an empty cell is a "
                                                 "missing key."},
    "key_column": {"type": "string", "default": "key", "description": "The strings CSV column holding the keys."},
    "languages": {"type": "array", "items": CODE, "description": "The strings CSV columns to read (default every "
                                                                 "column whose header is a locale code)."},
    "source": {**CODE, "description": "The source locale (default the document's, else en)."},
    "same_ok": {"type": "array", "items": {"type": "string"}, "description": "Keys or values that may equal the "
                                                                            "source without counting as untranslated."},
    "fonts": {"type": "object", "description": "{locale code: [font names]}: fallbacks tried first for that locale.",
              "additionalProperties": {"type": "array", "items": {"type": "string"},
                                       "description": "Registered font names in order."}},
    "rtl": {"type": "array", "items": CODE, "description": "Locales mirrored right to left (default ar, he and fa)."},
    "mirror": {"type": "boolean", "default": True, "description": "Mirror right-to-left locales."},
    "fit": {"type": ["string", "object"], "description": "shrink (fit-text down to min_size) or flag (report) text that "
                                                         "does not fit; or {layer name: shrink|flag, \"*\": default}."},
    "min_size": {"type": "integer", "minimum": 1, "description": "Smallest size shrink may set, in pixels (default 12)."},
    "checks": {"type": "array", "items": {"type": "string"}, "description": "Design check names (default the standard "
                                                                            "checks)."},
    "suites": {"type": ["boolean", "array"], "items": {"type": "string"},
               "description": "Attached or inherited suites to run per locale: true (all; the default), false or "
                              "names."},
    "suite": {"type": ["string", "object"], "description": "An extra suite (a name or an inline suite object) run per "
                                                           "locale."},
    "fail_on": {"type": "string", "enum": ["error", "warning", "never"], "default": "error",
                "description": "The finding level that fails a locale (and holds it in localize)."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace existing files this action did not "
                                                                      "write."},
}
FIELD_TYPES = {
    "locale-check": {
        **COMMON,
        "variables": {"type": "object", "description": "Variable overrides applied before the locales."},
        "format": {"type": "string", "enum": ["json", "markdown"], "default": "json",
                   "description": "markdown adds the report as a Markdown matrix under markdown."},
        "output": {"type": "string", "description": "Workspace-relative .md or .json file to write the report to."},
    },
    "localize": {
        **COMMON,
        "output_dir": {"type": "string", "default": "localized", "description": "Workspace-relative folder for the "
                                                                                "outputs and localize.json."},
        "documents": {"type": "boolean", "default": True, "description": "Write each locale's derived document "
                                                                        "<master>.<code>.vixl."},
        "formats": {"type": "array", "items": {"type": "string", "enum": ["png", "jpg", "webp", "svg", "pdf"]},
                    "description": "Also export each locale as <master>.<code>.<format>."},
        "spec": {"type": "object", "description": "A campaign spec (the run action's spec) run on each localized "
                                                  "document into <output_dir>/<code>/: a locale axis over its rows."},
    },
    "group-locales": {
        "name": {"type": "string", "description": "Project group (group-define) whose locale table to change."},
        "locales": TABLE,
        "replace": {"type": "boolean", "default": False, "description": "Replace the group's table instead of "
                                                                        "merging."},
    },
}
SUMMARIES = {
    "locale-check": "Check every locale of a document (its values, a strings CSV, group locales) on candidate copies "
                    "and report a locale x finding matrix: overflow, missing glyphs, untranslated and missing keys, "
                    "line-count changes that break a hierarchy rule.",
    "localize": "Build a checked variant per locale (derived documents, exports or a campaign run) with fit-text "
                "shrink, RTL mirroring and font fallbacks; failing locales are held, re-runs rebuild only what changed.",
    "group-locales": "Set the locale table a project group gives its members.",
}


def dispatch(session, action, request, document=None):
    if action == "group-locales":
        from .locales import set_group_locales

        return set_group_locales(session, request)
    with session.project(document=document) as project:
        path = project.path
        project = project.clone()
    relative = session.relative(Path(path)) if path else None
    if action == "localize":
        from .localize import localize

        return localize(session, project, request, relative)
    from .locale_check import check_locales, markdown

    fmt = request.get("format", "json")
    require(fmt in ("json", "markdown"), "format is json or markdown", field="format")
    report = check_locales(project, {**request, "locales": request.get("locales", "all")})
    if relative:
        report["document"] = relative
    text = markdown(report) if fmt == "markdown" or str(request.get("output", "")).endswith(".md") else None
    if fmt == "markdown":
        report["markdown"] = text
    if request.get("output"):
        import json

        from ...production import write_bytes

        destination = session.resolve(request["output"])
        require(destination.suffix in (".md", ".json"), "output is a .md or .json file", field="output")
        require(request.get("overwrite", False) or not destination.exists(),
                f"{request['output']} exists; pass overwrite=true to replace it", "output_exists", field="output")
        data = text if destination.suffix == ".md" else json.dumps(report, indent=2)
        write_bytes(destination, data.encode(), replace=True)
        report["output"] = session.relative(destination)
    return report
