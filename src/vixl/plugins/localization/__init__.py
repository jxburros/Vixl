"""Localization: per-locale variable tables, a locale check matrix and localized variants of a master."""

PLUGIN = {
    "name": "localization",
    "title": "Localization",
    "summary": "Locale variable tables and strings CSVs, a locale x finding check matrix, and localize fan-out with "
               "fit, RTL mirroring and font fallbacks.",
    "kind": "workflows",
    "modules": ["locales", "locale_check", "mirror", "localize", "workflow", "hooks"],
    "operations": ["locales"],
    "workflows": ["workflow"],
    "hooks": {"validate-state": ["hooks:validate_state"], "check-variants": ["hooks:check_variants"]},
    "requires": ["workspace_qa"],
}
