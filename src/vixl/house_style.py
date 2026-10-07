"""Vixl's house style as data: the built-in default brand that sparse briefs fall back to.

``data/house-style.json`` is shaped like a brand and holds three things:

* **craft**: fixed rules that are the same everywhere (contrast floors, the spacing scale, the
  line-height table, line length, minimum text sizes, corners, shadows, label case). Vixl's
  signature lives here only: sharp corners, thin part lines, offset shadows, uppercase labels and
  one line-height rule.
* **taste**: the pools a roll draws from (palettes, pairings, layouts, styles, looks), each entry
  in a tier (``safe``, ``bold``, ``avant-garde``, or ``explicit`` for name-only entries), plus the
  variety levels that gate the tiers.
* **purposes**: one profile per purpose (poster, social, slides, document, form, diagram, logo,
  motion) that weights the taste: dark-mode share, type-scale ratios, preferred pairings, layouts
  and styles, the finishing look and background treatments.

Precedence, highest first: an explicit field, the workspace ``brand.json``, the purpose profile,
the document's stored ``design_defaults``, then a fresh seeded roll. The file is read-only at run
time; changing it changes new documents only, because each document stores the rolled direction
and the ``house_style_version`` that made it (see docs/house-style.md, "Changing defaults").

This module only reads the data. The rolls that use it live in ``typefaces.roll`` and
``variety``. Other modules should call the small API here rather than copying values:

``profile(purpose)``          the merged profile for a purpose (or the general one for None)
``purpose_for(value)``        a purpose from a purpose name, alias, brief kind, size name or size category
``resolve_purpose(...)``      the purpose plus where it came from (explicit, brief kind, size)
``craft(key=None)``           the fixed craft rules
``tier_of(kind, name, purpose=None)`` and ``entries(kind)``  tier and metadata of pool entries
``level(variety)``            the settings of a variety level
"""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

PATH = Path(__file__).parent / "data" / "house-style.json"
PURPOSES = ("poster", "social", "slides", "document", "form", "diagram", "logo", "motion")
TIERS = ("safe", "bold", "avant-garde")
KINDS = ("palettes", "pairings", "layouts", "styles", "looks")


@lru_cache(maxsize=1)
def _data():
    return json.loads(PATH.read_text(encoding="utf-8"))


def data():
    """A copy of the whole house-style document."""
    return deepcopy(_data())


VERSION = _data()["version"]


def craft(key=None):
    """The fixed craft rules, or one of them (``contrast``, ``line_height``, ``corner_scale`` …)."""
    rules = _data()["craft"]
    return deepcopy(rules if key is None else rules[key])


def level(variety):
    """Settings of a variety level: tier weights, look scale, motifs and background treatments."""
    levels = _data()["taste"]["levels"]
    entry = levels.get(variety or "medium", levels["medium"])
    if "like" in entry:
        entry = {**levels[entry["like"]], **{k: v for k, v in entry.items() if k != "like"}}
    return deepcopy(entry)


def moods():
    return deepcopy(_data()["taste"]["moods"])


def entries(kind):
    """``{name: metadata}`` for one pool: palettes, pairings, layouts, styles or looks. Every entry has a tier."""
    taste = _data()["taste"]
    if kind == "pairings":
        return {name: {"tier": tier} for tier, names in taste["pairings"].items() for name in names}
    return deepcopy(taste[kind])


@lru_cache(maxsize=None)
def _tiers(kind):
    return {name: meta["tier"] for name, meta in entries(kind).items()}


def tier_of(kind, name, purpose=None):
    """The tier of ``name`` in pool ``kind`` for ``purpose``. A purpose may promote an entry (slides
    treat slide-title as safe); an entry the data does not list is ``explicit`` (by name only), and a
    value that is not a name (a brand's colour list) is ``brand``."""
    if not isinstance(name, str):
        return "brand"
    if purpose:
        promoted = _data()["purposes"].get(purpose, {}).get(kind, {}).get("tiers", {})
        if name in promoted:
            return promoted[name]
    return _tiers(kind).get(name, "explicit")


def names(kind, tier):
    """Entries of one tier, sorted."""
    return sorted(name for name, value in _tiers(kind).items() if value == tier)


def palette_colors():
    """``{name: colors}`` for the palettes the house style defines (legacy palettes keep their own colors)."""
    return {name: list(meta["colors"]) for name, meta in _data()["taste"]["palettes"].items() if "colors" in meta}


def palette_modes(name):
    return tuple(_data()["taste"]["palettes"].get(name, {}).get("modes", ("light", "dark")))


@lru_cache(maxsize=1)
def _purpose_index():
    from .sizes import SIZES

    index = {}
    purposes = _data()["purposes"]
    for purpose, item in purposes.items():
        for category in item.get("size_categories", []):
            index.setdefault(("category", category), purpose)
        for kind in item.get("kinds", []):
            index.setdefault(("kind", kind), purpose)
        for alias in item.get("aliases", []):
            index.setdefault(("alias", alias), purpose)
    for size, entry in SIZES.items():
        purpose = index.get(("category", entry["category"]))
        if purpose:
            index.setdefault(("size", size), purpose)
    return index


def _key(value):
    import re

    return re.sub(r"[\s_]+", "-", str(value).strip().lower())


def purpose_for(value):
    """The purpose a value names, or None. ``value`` can be a purpose (``poster``), an alias (``web``,
    ``print``), a brief kind (``social-card``, ``stationery``), a named size (``instagram-post``) or a
    size category (``slides``, ``icons``)."""
    if not value:
        return None
    key = _key(value)
    if key in PURPOSES:
        return key
    index = _purpose_index()
    for kind in ("kind", "alias", "size", "category"):
        if (kind, key) in index:
            return index[(kind, key)]
    if key.endswith("s") and key[:-1] in PURPOSES:
        return key[:-1]
    return None


def resolve_purpose(purpose=None, *, project=None, kind=None, size=None):
    """``(purpose, source)``: an explicit purpose first, then the brief kind, then the document's stored
    purpose, then its named size. ``source`` is ``explicit``, ``brief kind``, ``document``, ``size`` or None."""
    if purpose:
        found = purpose_for(purpose)
        if found:
            return found, "explicit"
    if kind:
        found = purpose_for(kind)
        if found:
            return found, "brief kind"
    if project is not None:
        stored = project.state.get("design_defaults", {}).get("purpose")
        if stored in PURPOSES:
            return stored, "document"
        size = size or project.state.get("canvas", {}).get("size")
    if size:
        found = purpose_for(size)
        if found:
            return found, "size"
    return None, None


def profile(purpose=None):
    """The merged profile for ``purpose`` (one of ``PURPOSES``, or anything ``purpose_for`` resolves);
    None or an unknown purpose gives the general profile. Keys: ``purpose``, ``summary``, ``dark``
    (share of dark-mode rolls), ``type_scales``, ``pairings``/``layouts``/``styles`` (``prefer`` lists
    with a ``weight``), ``look`` (``amount`` and ``weights``) and ``treatments`` (per variety level)."""
    resolved = purpose_for(purpose) if purpose else None
    merged = deepcopy(_data()["default_profile"])
    merged.update(deepcopy(_data()["purposes"].get(resolved, {})))
    merged["purpose"] = resolved
    for key in ("pairings", "layouts", "styles"):
        merged.setdefault(key, {"prefer": [], "weight": 1})
    merged.setdefault("treatments", {})
    return merged


def legacy(version):
    """What an earlier house-style version rolled from, for documents and tests pinned to it."""
    return deepcopy(_data()["legacy"].get(str(version)))


def versions():
    return sorted([int(v) for v in _data()["legacy"]] + [VERSION])


def show(purpose=None):
    """A readable summary for ``vixl house show`` and ``vixl_resource_get(kind='house-style')``."""
    item = _data()
    if purpose:
        found = purpose_for(purpose)
        from .errors import require

        require(found, f"Unknown purpose {purpose!r}; purposes: {', '.join(PURPOSES)}", field="purpose",
                allowed=list(PURPOSES))
        return {"purpose": found, "version": VERSION, "profile": profile(found), "craft": craft(),
                "levels": {name: level(name) for name in item["taste"]["levels"]}}
    pools = {kind: {tier: len(names(kind, tier)) for tier in (*TIERS, "explicit")} for kind in KINDS}
    return {"name": item["name"], "version": VERSION, "description": item["description"],
            "precedence": item["precedence"], "craft": craft(),
            "levels": {name: level(name) for name in item["taste"]["levels"]},
            "pools": pools,
            "purposes": {name: item["purposes"][name]["summary"] for name in PURPOSES},
            "versions": versions(),
            "detail": "vixl house show PURPOSE (vixl_resource_get kind=house-style name=PURPOSE) gives one purpose profile"}
