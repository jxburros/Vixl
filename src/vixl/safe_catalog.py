"""Curated broad-use defaults, read from the house style (``house_style``). Specialized entries remain available by name."""

from . import house_style

# Version 1 safe palettes (name: (mood, colors)): the pool that layout-apply without a palette, templates
# and house-style version 1 rolls draw from. Version 2 rolls draw from the tiered pools in the house style.
SAFE_PALETTES = {name: (house_style.entries("palettes")[name]["mood"][0], house_style.palette_colors()[name])
                 for name in house_style.legacy(1)["palettes"]}
SAFE_STYLES = set(house_style.names("styles", "safe"))
SAFE_LOOKS = set(house_style.names("looks", "safe"))
SAFE_PAIRINGS = set(house_style.names("pairings", "safe"))


def safe_pairing(entry):
    """Plain serif/sans families at moderate weights; explicitly curated families first."""
    return entry["name"] in SAFE_PAIRINGS


def palette_metadata():
    from .resources import PALETTES

    meta = house_style.entries("palettes")
    rows = {}
    for name in PALETTES:
        item = meta.get(name, {})
        tier = item.get("tier", "explicit")
        rows[name] = {"tier": tier, "safe": tier == "safe", "mood": item.get("mood", []),
                      **({"family": item["family"]} if "family" in item else {}),
                      "modes": list(house_style.palette_modes(name)),
                      "criteria": "Color roles assigned with contrast checks: ink 7:1, muted and accent text 4.5:1"}
    return rows


def catalog():
    from .layouts import catalog as layouts
    from .looks import catalog as looks
    from .resources import catalog as resources
    from .styles import listing
    from .typefaces import list_pairings

    return {"palettes": palette_metadata(), "pairings": list_pairings()["pairings"],
            "layouts": layouts()["layouts"], "looks": looks(), "styles": listing()["styles"],
            "containers": {name: {"safe": item.get("safe", False), "description": item.get("description")}
                           for name, item in resources("containers").items()},
            "templates": {name: {"safe": item.get("safe", False), "description": item.get("description")}
                          for name, item in resources("templates").items()},
            "tiers": {tier: house_style.data()["taste"]["tier_notes"][tier] for tier in (*house_style.TIERS, "explicit")},
            "levels": {name: house_style.level(name)["summary"] for name in ("low", "medium", "high", "fixed")},
            "policy": "Fresh seeds by default; explicit seed reproduces choices and ignores recent history. "
                      "Precedence: explicit field > brand.json > purpose profile > document design_defaults > seeded roll. "
                      "The variety level gates the tiers (low: safe only; medium: mostly safe; high: every tier). "
                      "Fonts are recommended; installation remains explicit."}
