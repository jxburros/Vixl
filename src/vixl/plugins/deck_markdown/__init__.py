"""Markdown to deck: a Markdown file becomes a checked slide deck in one call."""

PLUGIN = {
    "name": "deck_markdown",
    "title": "Markdown to deck",
    "summary": "Turn a Markdown outline into a checked slide deck with charts, tables and speaker notes.",
    "kind": "workflows",
    "modules": ["deck_markdown", "workflow"],
    "workflows": ["workflow"],
    "requires": ["charts"],
}
