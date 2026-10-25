"""Spelling: unknown words in drawn text against a bundled English word list or a language content pack."""

PLUGIN = {
    "name": "spelling",
    "title": "Spelling",
    "summary": "An optional spelling check of drawn text with suggestions; English is bundled, other languages are content packs.",
    "kind": "checks",
    "modules": ["spelling"],
    "hooks": {"check": ["spelling:check"], "spell": ["spelling:spell"]},
    "checks": ["spelling"],
}
