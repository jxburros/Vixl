"""Font maker: draw a typeface as layers and export it as TTF, OTF, WOFF or WOFF2."""

PLUGIN = {
    "name": "fontmaker",
    "title": "Font maker",
    "summary": "Design a font in a document (metrics, glyph grid, kerning) and export TTF, OTF, WOFF and WOFF2.",
    "kind": "operations",
    "modules": ["fontmaker", "hooks"],
    "operations": ["fontmaker"],
    "hooks": {"validate-state": ["hooks:validate_state"], "export-format": ["hooks:export"]},
}
