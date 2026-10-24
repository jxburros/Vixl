"""A researched typeface catalog, curated pairings, explicit installs and seeded rolls.

Vixl bundles one fallback font for proofing, not for design. Real typefaces come from the
catalog (open-licensed Google Fonts families with classification, x-height, contrast, mood and
role notes) and are downloaded only when an agent asks: ``font install`` or ``font pair``.
Downloads are cached per user, validated, embedded in the document and registered by name, so a
saved ``.vixl`` file stays portable and later renders never touch the network.
"""

from functools import lru_cache
import json
import os
from pathlib import Path
import random
import re
import secrets
from urllib.parse import quote_plus, urlparse

import httpx

from . import house_style
from .errors import VixlError, require

DATA = Path(__file__).parent / "data"
CSS_API = "https://fonts.googleapis.com/css2"
FONT_HOST = "fonts.gstatic.com"
LIMIT = 16 * 1024 * 1024
# Mood words per palette, from the house style (every rollable palette has them).
PALETTE_MOODS = {name: set(meta.get("mood", [])) for name, meta in house_style.entries("palettes").items()}


@lru_cache(maxsize=1)
def fonts():
    return json.loads((DATA / "fonts.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def pairings():
    rows = json.loads((DATA / "font-pairings.json").read_text(encoding="utf-8"))
    return [{**entry, "tier": house_style.tier_of("pairings", entry["name"]),
             "safe": house_style.tier_of("pairings", entry["name"]) == "safe"} for entry in rows]


def principles():
    return (DATA / "font-principles.md").read_text(encoding="utf-8")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def find_font(family):
    wanted = slug(family)
    for entry in fonts():
        if slug(entry["family"]) == wanted:
            return entry
    return None


def _close(name, options):
    import difflib

    return difflib.get_close_matches(name, options, 3, 0.5)


def _matches(values, wanted):
    return not wanted or any(slug(w) in {slug(v) for v in values} for w in ([wanted] if isinstance(wanted, str) else wanted))


def list_fonts(category=None, role=None, mood=None, query=None):
    """Compact catalog rows, filtered; full detail comes from ``show_font``."""
    rows = []
    for entry in fonts():
        if category and slug(entry["category"]) != slug(category) and slug(entry["classification"]) != slug(category):
            continue
        if not _matches(entry.get("roles", []), role) or not _matches(entry.get("mood", []), mood):
            continue
        if query and slug(query) not in slug(" ".join([entry["family"], entry["classification"], entry.get("notes", "")])):
            continue
        rows.append(
            {
                "family": entry["family"],
                "classification": entry["classification"],
                "weights": entry["weights"],
                "roles": entry.get("roles", []),
                "mood": entry.get("mood", []),
            }
        )
    return {"fonts": rows, "count": len(rows), "categories": sorted({e["category"] for e in fonts()})}


def show_font(family):
    entry = find_font(family)
    if entry is None:
        close = _close(family, [e["family"] for e in fonts()])
        raise VixlError(
            "unknown_font",
            f"{family!r} is not in the curated catalog"
            + (f"; did you mean {', '.join(close)}?" if close else "")
            + " Any Google Fonts family can still be installed with font install.",
            suggestions=close,
        )
    used = [p["name"] for p in pairings() if entry["family"] in (p["heading"]["family"], p["body"]["family"])]
    return {**entry, "pairings": used}


def _brief(pairing):
    return {
        "name": pairing["name"],
        "heading": f"{pairing['heading']['family']} {pairing['heading']['weight']}",
        "body": f"{pairing['body']['family']} {pairing['body']['weight']}",
        "relationship": pairing.get("relationship"),
        "mood": pairing.get("mood", []),
        "tier": pairing.get("tier", "explicit"),
        "safe": pairing.get("safe", False),
    }


def list_pairings(mood=None, best_for=None, family=None, relationship=None, *, full=False):
    """Matching pairings; compact rows unless ``full`` (``get_pairing`` gives one in full)."""
    rows = [
        p if full else _brief(p)
        for p in pairings()
        if _matches(p.get("mood", []), mood)
        and _matches(p.get("best_for", []), best_for)
        and (not family or slug(family) in (slug(p["heading"]["family"]), slug(p["body"]["family"])))
        and (not relationship or p.get("relationship") == relationship)
    ]
    result = {"pairings": rows, "count": len(rows)}
    if not full:
        result["detail"] = "vixl font pairing NAME (vixl_reference('fonts') view=pairing) explains why a pairing works"
    return result


def get_pairing(name):
    for item in pairings():
        if item["name"] == name:
            return item
    close = _close(name, [p["name"] for p in pairings()])
    raise VixlError(
        "unknown_pairing",
        f"Unknown pairing {name!r}" + (f"; did you mean {', '.join(close)}?" if close else "; see vixl font pairings"),
        suggestions=close,
    )


def resolve_seed(seed):
    if seed is None or seed == "random":
        return secrets.randbelow(2**32)
    require(isinstance(seed, int) and 0 <= seed < 2**32, "seed must be a nonnegative 32-bit integer or 'random'", field="seed")
    return seed


def roll_pairing(seed=None, mood=None, best_for=None):
    """A seeded pick among pairings matching the filters (or all of them if none match)."""
    seed = resolve_seed(seed)
    pool = list_pairings(mood, best_for, full=True)["pairings"] or list(pairings())
    if mood is None:
        pool = [item for item in pool if item.get("safe")] or pool
    return random.Random(seed).choice(pool), seed


def _weighted_choice(rng, weights):
    names = sorted(name for name, value in weights.items() if value > 0)
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def roll(seed=None, *, purpose=None, mood=None, canvas=None, locks=None, variety="medium", recent=None,
         recommend=None, content=None):
    """Roll a coherent design direction from the house style: a tier, then pairing, mode, palette and layout.

    The variety level gates the tiers (low: safe only; medium: mostly safe; high: every tier) and the
    purpose (``house_style.purpose_for``: poster, social, slides, document, form, diagram, logo, motion,
    or a brief kind, named size or size category) weights each choice. ``mood`` favours entries with
    that mood and shifts expressive moods toward the bold tiers. ``recommend`` maps ``layouts``,
    ``looks`` and ``styles`` to names a brief recommends; they are favoured where the tier allows.
    ``content`` lists the copy slots that will be supplied (title, subtitle …): only layouts that place
    all of them are rolled. When none does, the roll keeps the layout it would pick with no content (the
    preview's), so applying it reports the slots it leaves out as ``unused_slot`` (#700); ``direction.pool``
    says which pool the layout came from. Every field that ``locks`` fixes is kept; the rest come from the seed, which is returned so
    a direction worth keeping can be reproduced exactly.
    """
    from .layouts import ACCENTS, DENSITY_CHOICES, IMAGE_KEYS, LAYOUTS, RATIOS, placeable, places, slot_spec
    from .resources import PALETTES
    from .variety import VARIETIES, choose, dimensions, orientation, pick_tier, tier_pool

    locks = dict(locks or {})
    contrast = locks.get("weight_contrast")
    require(contrast in (None, "moderate", "strong"), "weight_contrast must be moderate or strong", field="locks")
    require(variety in VARIETIES, "variety must be low, medium, high or fixed", field="variety")
    require(locks.get("tier") in (None, *house_style.TIERS), f"tier must be one of {', '.join(house_style.TIERS)}",
            field="locks")
    recent = recent or []
    recommend = recommend or {}
    if variety == "fixed" and seed is None:
        seed = 0
    seed = resolve_seed(seed)
    rng = random.Random(seed)
    goal = house_style.purpose_for(purpose)
    profile = house_style.profile(goal)
    tuning = house_style.moods()
    wanted = {slug(m) for m in ([mood] if isinstance(mood, str) else mood or [])}
    tier = locks.get("tier") or pick_tier(rng, variety, wanted)
    category = "mark" if goal == "logo" else "data" if goal in ("diagram", "form") else "design"
    weights = house_style.data()["taste"]["alignment"][category]
    alignment = locks.get("align") or random.Random(seed ^ 0xA11).choices(list(weights), weights=list(weights.values()))[0]

    def strength(meta):
        return tuning["match_weight"] if wanted & {slug(m) for m in meta.get("mood", [])} else 1

    def contrast_of(item):
        return "strong" if item["heading"]["weight"] - item["body"]["weight"] >= 300 else "moderate"

    if "pairing" in locks:
        pairing = get_pairing(locks.pop("pairing"))
    else:
        by_name = {item["name"]: item for item in pairings()}
        fits = (lambda name: contrast_of(by_name[name]) == contrast) if contrast else (lambda name: True)
        pool = tier_pool("pairings", tier, goal, lambda name: name in by_name and fits(name))
        require(pool, "No rollable pairing has the requested weight contrast", field="locks")
        prefer = set(profile["pairings"]["prefer"])
        weights = {name: (profile["pairings"]["weight"] if name in prefer else 1) * strength(by_name[name])
                   * (2 if goal is None and purpose and _matches(by_name[name].get("best_for", []), purpose) else 1)
                   for name in pool}
        pairing = by_name[rng.choices(pool, weights=[weights[name] for name in pool], k=1)[0]]
    actual_contrast = contrast_of(pairing)
    require(contrast is None or contrast == actual_contrast,
            "Locked pairing and weight_contrast conflict; unlock one choice", field="locks")
    mode = locks.get("mode") or ("dark" if rng.random() < profile["dark"] else "light")
    require(mode in ("light", "dark"), "mode must be light or dark", field="locks")
    moods = {slug(m) for m in pairing.get("mood", [])} | wanted
    palette_meta = house_style.entries("palettes")
    palettes = tier_pool("palettes", tier, goal, lambda name: name in PALETTES and mode in house_style.palette_modes(name))
    palette_weights = {name: tuning["match_weight"] if moods & {slug(m) for m in palette_meta[name].get("mood", [])} else 1
                       for name in palettes}
    shape = orientation(*canvas) if canvas else None
    layout_meta = house_style.entries("layouts")

    def layout_fits(name, content=content):
        if alignment and goal != "logo" and not LAYOUTS[name].get("safe_composition") and alignment not in LAYOUTS[name].get("aligns", ["left"]):
            return False
        meta = layout_meta.get(name, {})
        purposes = meta.get("purposes", [])
        if goal and goal not in purposes:
            return False
        if goal is None and not {"poster", "social", "slides", "document"} & set(purposes):
            return False
        if shape is not None and shape not in meta.get("orientations", [shape]):
            return False
        if content and not set(content) & set(IMAGE_KEYS) and set(slot_spec(LAYOUTS[name])) & set(IMAGE_KEYS):
            return False  # an image slot nobody fills would ship as a blank
        return not content or places(name, shape or "square", tuple(sorted(content)))

    def layout_pool(content):
        layouts = tier_pool("layouts", tier, goal, lambda name: name in LAYOUTS and layout_fits(name, content))
        if recent and layouts == [recent[-1].get("layout")]:
            alternatives = tier_pool("layouts", tier, goal, lambda name: name in LAYOUTS
                                     and name != recent[-1].get("layout") and layout_fits(name, content))
            layouts = alternatives or layouts
        return layouts

    layouts, pool = layout_pool(content), "content" if content else None
    if not layouts and content and "layout" not in locks:
        # No layout places all the copy: keep the preview's layout (the draws so far do not depend on content),
        # so applying it reports the slots it leaves out as unused_slot, with suggestions (#700).
        layouts, pool = layout_pool(None), "preview"
    if not layouts and "layout" not in locks:
        nearest = []
        if content:
            keys = tuple(sorted(content))
            candidates = tier_pool("layouts", tier, goal, lambda name: name in LAYOUTS) or [
                name for name in LAYOUTS if goal in layout_meta.get(name, {}).get("purposes", [])]
            for name in candidates:
                found = placeable(name, shape or "square", keys)
                if found:
                    nearest.append((-len(found), name, sorted(found)))
            nearest = [{"layout": name, "places": found} for _, name, found in sorted(nearest)[:3]]
        raise VixlError("invalid_operation",
                        f"No rollable layout{' for ' + goal if goal else ''} "
                        + (f"places all of {', '.join(content)} " if content else "fits ")
                        + "on this canvas; lock a layout (locks={layout: NAME}) or supply other slots",
                        field="slots", suggestions=nearest)
    layouts = layouts or [locks["layout"]]
    layout_prefer = set(profile["layouts"]["prefer"]) | set(recommend.get("layouts", []))
    layout_weights = {name: (profile["layouts"]["weight"] if name in layout_prefer else 1) * strength(layout_meta.get(name, {}))
                      for name in layouts}
    direction = {
        "layout": choose(rng, layouts, recent, "layout", layout_weights),
        "pairing": pairing["name"],
        "palette": choose(rng, palettes, recent, "palette", palette_weights),
        "mode": mode,
        "type_scale": rng.choice([name for name in profile["type_scales"] if name in RATIOS]),
        # Density usually follows the purpose (its profile's weights) but may deviate (decision E4).
        "density": _weighted_choice(rng, profile["density"]) if profile.get("density") else rng.choice(DENSITY_CHOICES),
        "accent": rng.choice(ACCENTS),
        "layout_seed": rng.randrange(2**32),
        **dimensions(rng, pairing, variety, tier=tier, purpose=goal, moods=wanted, recommend=recommend),
        **({"pool": pool} if pool else {}),
        "tier": tier,
        "purpose": goal,
    }
    # Bold and expressive rolls set the headline large; quiet ones keep the measured headline (#285).
    expressive = bool(wanted & {slug(m) for m in tuning["expressive"]})
    direction["headline"] = "large" if direction["tier"] != "safe" or expressive else "measured"
    direction["align"] = alignment
    # A separate stream, so these details never change what the seed rolls for the fields above.
    details, pick = house_style.details(), random.Random(seed ^ 0xC7A)
    style, corner = locks.get("style", direction["style"]), locks.get("corner", direction["corner"])
    pill = 1 if corner == "pill" else 0 if style in details["square_styles"] else details["cta_pill"][direction["tier"]]
    direction["cta"] = "pill" if pick.random() < pill else "button"
    direction["date"] = "highlight" if pick.random() < details["date_highlight"][direction["tier"]] else "plain"
    unknown = set(locks) - set(direction)
    require(not unknown, f"Unknown lock(s) {sorted(unknown)}; lockable: {', '.join(direction)}", field="locks")
    direction.update(locks)
    if "container" in locks:
        from .resources import get

        component = get("containers", direction["container"])
        variants = list(component.get("variants", {})) or ["default"]
        if "container_variant" not in locks:
            direction["container_variant"] = rng.choice(variants)
        require(direction["container_variant"] in ("default", *variants), "Unknown container variant", field="locks")
    direction["color_assignment"] = direction["mode"]
    if "look" in locks and "look_amount" not in locks:
        scale = house_style.level(variety)["look_scale"]
        direction["look_amount"] = 0 if direction["look"] == "none" else round(max(profile["look"]["amount"], 0.25) * scale, 3)
    if direction["style"] == "editorial" and direction["corner"] == "pill":
        require("corner" not in locks or "style" not in locks,
                "Editorial style and pill corners conflict; unlock one choice", field="locks")
        if "corner" in locks:
            direction["style"] = "minimalist"
        else:
            direction["corner"] = "sharp"
    require(direction["layout"] in LAYOUTS, f"Unknown layout {direction['layout']!r}")
    operation = {
        "type": "layout-apply",
        "name": direction["layout"],
        "seed": direction["layout_seed"],
        "palette": direction["palette"],
        "mode": direction["mode"],
        "type_scale": direction["type_scale"],
        "density": direction["density"],
        "accent": direction["accent"],
        "direction": {key: value for key, value in direction.items()
                      if key not in ("layout", "palette", "mode", "type_scale", "density", "accent", "layout_seed", "pairing",
                                     "tier", "purpose", "pool")},
    }
    if "container" in locks:
        operation["direction"]["place_container"] = True
    operation["align"] = direction["align"]
    tiers = {"pairing": house_style.tier_of("pairings", direction["pairing"], goal),
             "palette": house_style.tier_of("palettes", direction["palette"], goal),
             "layout": house_style.tier_of("layouts", direction["layout"], goal),
             "style": house_style.tier_of("styles", direction["style"], goal),
             "look": "safe" if direction["look"] == "none" else house_style.tier_of("looks", direction["look"], goal)}
    return {
        "seed": seed,
        "variety": variety,
        "purpose": goal,
        "tier": direction["tier"],
        "tiers": tiers,
        "direction": direction,
        "pairing": pairing,
        "steps": [
            f"vixl font pair {pairing['name']}",
            f"vixl layout apply {direction['layout']} --seed {direction['layout_seed']} --palette {direction['palette']} "
            f"--mode {direction['mode']} --type-scale {direction['type_scale']} --density {direction['density']} "
            f"--accent {direction['accent']} --set title=…",
        ],
        "operation": operation,
        "component": {"resource": direction["container"], "variant": direction["container_variant"],
                      "applied": "container" in locks,
                      "how": "Lock container to compose supplied content inside this component; otherwise use it in container-place."},
        "note": "One roll among many: roll again (new seed) for alternatives, lock what you like (--lock palette=sage, "
        "--lock tier=bold), and keep a direction by its seed.",
    }


def _cache_dir():
    return Path(os.environ.get("VIXL_FONT_CACHE", "~/.cache/vixl/fonts")).expanduser()


def _get(client, url):
    parsed = urlparse(url)
    require(parsed.scheme == "https", "Font downloads require HTTPS")
    with client.stream("GET", url) as response:
        require(response.status_code == 200, f"Font service returned HTTP {response.status_code}", "font_download_failed")
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            require(len(data) <= LIMIT, "Font exceeds byte limit", "resource_limit")
        return bytes(data)


def cache_location():
    """The font cache directory and what chose it: the ``VIXL_FONT_CACHE`` variable or the default."""
    return _cache_dir(), "VIXL_FONT_CACHE" if os.environ.get("VIXL_FONT_CACHE") else "default"


def cached_font(family, weight=400, italic=False):
    """The bytes of one Google Fonts style from the font cache, or None; never touches the network."""
    from .fonts import validate_font

    if not isinstance(family, str) or not re.fullmatch(r"[A-Za-z0-9 ]{1,80}", family):
        return None
    entry = find_font(family)
    family = entry["family"] if entry else family
    cached = _cache_dir() / f"{slug(family)}-{weight}{'-italic' if italic else ''}.ttf"
    try:
        data = cached.read_bytes()
        validate_font(data)
    except (OSError, VixlError):
        return None
    return data


def fetch_font(family, weight=400, italic=False, *, client=None, source=None):
    """Return TTF bytes for one static style of a Google Fonts family, using the user cache.
    A ``source`` dict is filled with where the bytes came from: ``origin`` (``cache`` or
    ``download``), the cache file, and for a download the stylesheet and font URLs."""
    from .fonts import validate_font

    require(isinstance(weight, int) and 100 <= weight <= 900 and weight % 100 == 0, "weight must be 100–900 in steps of 100", field="weight")
    require(isinstance(family, str) and re.fullmatch(r"[A-Za-z0-9 ]{1,80}", family), "Use a font family name such as 'Space Grotesk'", field="family")
    entry = find_font(family)
    family = entry["family"] if entry else family
    if entry and weight not in entry["weights"]:
        raise VixlError("unavailable_weight", f"{family} has weights {entry['weights']}, not {weight}", field="weight")
    cached = _cache_dir() / f"{slug(family)}-{weight}{'-italic' if italic else ''}.ttf"
    if cached.is_file():
        data = cached.read_bytes()
        try:
            validate_font(data)
            if source is not None:
                source.update(origin="cache", cache_file=str(cached))
            return data, family
        except VixlError:
            cached.unlink(missing_ok=True)
    axis = f"ital,wght@1,{weight}" if italic else f"wght@{weight}"
    url = f"{CSS_API}?family={quote_plus(family)}:{axis}"
    own = client is None
    if own:  # A caller's client is the caller's to gate (creation.network_client, or an offline stub).
        from .fetch import network_allowed

        network_allowed(f"Downloading {family} from Google Fonts")
    client = client or httpx.Client(timeout=30, follow_redirects=False, headers={"User-Agent": "vixl"})
    try:
        css = _get(client, url).decode("utf-8", "replace")
        sources = re.findall(r"url\((https://[^)]+)\)\s*format\('(?:truetype|opentype)'\)", css)
        require(sources, f"No TrueType source for {family} {weight}{' italic' if italic else ''}", "font_download_failed")
        parsed = urlparse(sources[0])
        # Names outside the Google Fonts library can still answer with a /l/ "kit" URL; only /s/ is a family.
        require(parsed.hostname == FONT_HOST and parsed.path.startswith("/s/"),
                f"Google Fonts has no family named {family!r}", "unknown_font")
        data = _get(client, sources[0])
    except httpx.HTTPError as exc:
        raise VixlError("font_download_failed", f"Font download failed ({type(exc).__name__}); check network access") from exc
    except VixlError as exc:
        if exc.code == "font_download_failed" and "HTTP 400" in str(exc):
            raise VixlError(
                "unknown_font",
                f"Google Fonts has no {family!r} at weight {weight}{' italic' if italic else ''}; "
                "check the family name (vixl font list) and its weights",
            ) from exc
        raise
    finally:
        if own:
            client.close()
    validate_font(data)
    stored = True
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    except OSError:
        stored = False  # A read-only cache only costs a re-download.
    if source is not None:
        source.update(origin="download", url=sources[0], stylesheet=url, cache_file=str(cached) if stored else None)
    return data, family


def install_font(project, family, weight=400, italic=False, name=None, role=None, *, client=None, body_italic=False):
    """Download (or reuse from cache), embed and register one style; optionally give it a role. With
    ``body_italic``, a body text face also brings its italic (see ``install_body_italic``)."""
    import hashlib

    from .design import named

    found = {}
    data, family = fetch_font(family, weight, italic, client=client, source=found)
    name = named(name or f"{slug(family)}-{weight}{'-italic' if italic else ''}")
    digest = hashlib.sha256(data).hexdigest()
    asset = f"fonts/{digest}.ttf"
    candidate = project.clone()
    candidate.assets[asset] = data
    op = {"type": "font-register", "name": name, "asset": asset, **({"role": role} if role else {})}
    candidate.apply(op, detail="compact")
    project.__dict__.update(candidate.__dict__)
    cache_dir, chosen_by = cache_location()
    result = {"name": name, "family": family, "weight": weight, "italic": italic, **({"role": role} if role else {}),
              "source": {**found, "cache_dir": str(cache_dir), "cache_dir_from": chosen_by, "bundled_fallback": False},
              "file": {"asset": asset, "bytes": len(data), "sha256": digest}}
    if body_italic and role == "body" and not italic:
        companion = install_body_italic(project, family, weight, name, client=client)
        if companion:
            result["body_italic"] = companion
    return result


def text_face(family):
    """Whether a catalog family is a text face that has an italic (role ``text``, ``italic`` true)."""
    entry = find_font(family)
    return bool(entry and entry.get("italic") and "text" in entry.get("roles", []))


def install_body_italic(project, family, weight, roman, *, client=None):
    """Also install the italic of a body text face, registered as ``<roman>-italic`` (``source-sans-3-400-italic``),
    so italic rich text draws the real italic instead of slanting the roman (one more file). Families that are not
    catalog text faces with an italic return None. A failed download changes nothing and is reported as
    ``{"skipped": reason}``. Only static files are fetched: optical sizes (``opsz``) are not used."""
    if not text_face(family):
        return None
    try:
        installed = install_font(project, family, weight, True, f"{roman}-italic", client=client)
    except VixlError as exc:
        if exc.code not in ("network_disabled", "font_download_failed", "unknown_font", "unavailable_weight"):
            raise
        return {"skipped": str(exc)}
    return {"name": installed["name"], "origin": installed["source"].get("origin")}


SCRIPT_ALIASES = {"devanagari": "Devanagari", "hindi": "Devanagari", "han": "Han", "chinese": "Han",
                  "hiragana/katakana": "Hiragana/Katakana", "hiragana": "Hiragana/Katakana",
                  "katakana": "Hiragana/Katakana", "kana": "Hiragana/Katakana", "japanese": "Hiragana/Katakana",
                  "hangul": "Hangul", "korean": "Hangul", "thai": "Thai", "arabic": "Arabic"}


def cover_fonts(project, text=None, scripts=None, weight=400, *, client=None):
    """Install the catalog Noto face for each script that no available font draws and append it to the document's
    font fallbacks. The scripts come from ``scripts`` (Devanagari, Han, Hiragana/Katakana, Hangul,
    Thai, Arabic, or a language name such as japanese), else from the characters of ``text`` the document cannot draw,
    else from every text layer's. Faces come from the font cache first; a download honours the network policy
    (``VIXL_OFFLINE``), and when one is not allowed or fails nothing is changed and the error names the families."""
    from .text import SCRIPT_FONTS, cover_families, glyph_coverage, scripts_of, uncovered

    if scripts:
        require(isinstance(scripts, (list, tuple)) and all(isinstance(item, str) for item in scripts),
                "scripts is a list of script names", field="scripts")
        unknown = [item for item in scripts if item.lower() not in SCRIPT_ALIASES]
        require(not unknown, f"Unknown script(s) {', '.join(map(repr, unknown))}; use "
                f"{', '.join(SCRIPT_FONTS)} (or japanese, chinese, korean, hindi)", field="scripts")
        wanted = list(dict.fromkeys(SCRIPT_ALIASES[item.lower()] for item in scripts))
        missing = []
    else:
        if text is not None:
            missing = glyph_coverage(project, {"text": text})["missing"]
        else:
            missing = sorted({char for layer in project.state["layers"] if layer["type"] == "text"
                              for char in uncovered(project, layer)})
        wanted = [name for name in scripts_of(missing) if name]
    families = cover_families(wanted)
    result = {"scripts": wanted, "families": families, "installed": [],
              "font_fallbacks": list(project.state.get("font_fallbacks", []))}
    other = scripts_of(missing).get(None)
    if other:
        result["uncovered"] = "".join(other[:24])
        result["note"] = ("Vixl has no catalog face for some characters; import a font that draws them and add it "
                          "with font-fallbacks")
    if not families:
        return result
    candidate = project.clone()
    registered = dict(candidate.state.get("fonts", {}))
    installed, unavailable, error = [], [], None
    for family in families:
        try:
            installed.append(install_font(candidate, family, weight, client=client))
        except VixlError as exc:
            if exc.code not in ("network_disabled", "font_download_failed"):
                raise
            unavailable.append(family)
            error = error or exc
    if unavailable:
        offline = error.code == "network_disabled"
        raise VixlError(error.code, f"font-cover needs {', '.join(unavailable)}, which "
                        f"{'is' if len(unavailable) == 1 else 'are'} not in the font cache, and "
                        + ("network access is off (VIXL_OFFLINE=1)" if offline else f"the download failed ({error})")
                        + "; nothing was changed", field="scripts", families=unavailable,
                        suggestions=[f"Allow the download once (vixl font install {unavailable[0]!r}) so the cache "
                                     "has it, or import a font file that covers these scripts and add it with "
                                     "font-fallbacks"])
    current = list(candidate.state.get("font_fallbacks", []))
    fallbacks = list(current)
    for item in installed:
        asset, previous = item["file"]["asset"], registered.get(item["name"])
        if asset in fallbacks:
            continue
        # A face installed again with other bytes (a newer upstream file) replaces its old entry, not a second one.
        if previous in fallbacks:
            fallbacks[fallbacks.index(previous)] = item["name"]
        else:
            fallbacks.append(item["name"])
    if fallbacks != current:
        candidate.apply({"type": "font-fallbacks", "fonts": fallbacks}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    result["installed"] = [{key: item[key] for key in ("name", "family", "weight")} | {
        "origin": item["source"].get("origin")} for item in installed]
    result["font_fallbacks"] = list(project.state.get("font_fallbacks", []))
    return result


def origin_of(*installed):
    """``cache``, ``download`` or ``mixed``: where a set of installed fonts came from."""
    origins = {item["source"].get("origin", "unknown") for item in installed}
    return origins.pop() if len(origins) == 1 else "mixed"


def pair_fonts(project, pairing=None, *, seed=None, mood=None, best_for=None, client=None, body_italic=False):
    """Install a pairing's heading and body styles and make them the document typography. With ``body_italic``
    (the font pair command), a body text face also brings its italic."""
    rolled = None
    if pairing in (None, "random"):
        item, rolled = roll_pairing(seed, mood, best_for)
    else:
        item = get_pairing(pairing)
    heading = install_font(project, item["heading"]["family"], item["heading"]["weight"], role="heading", client=client)
    body = install_font(project, item["body"]["family"], item["body"]["weight"], role="body", client=client,
                        body_italic=body_italic)
    result = {
        "pairing": item["name"],
        "heading": heading,
        "body": body,
        "why": item.get("why"),
        "caution": item.get("caution"),
        "typography": project.state.get("typography"),
        "origin": origin_of(heading, body),
        "note": "Layouts now use these fonts by default; pass font/display_font to override.",
    }
    if rolled is not None:
        result["seed"] = rolled
    return result



def pair_workspace(workspace, pairing=None, *, seed=None, mood=None, best_for=None, client=None):
    """Make a pairing the workspace default (``brand.json``) that new documents embed at creation.
    Both styles are fetched now, so a missing font fails here instead of at creation."""
    from .brand import save_font_default

    rolled = None
    if pairing in (None, "random"):
        item, rolled = roll_pairing(seed, mood, best_for)
    else:
        item = get_pairing(pairing)
    fonts = {}
    for role in ("heading", "body"):
        found = {}
        fetch_font(item[role]["family"], item[role]["weight"], client=client, source=found)
        fonts[role] = {"family": item[role]["family"], "weight": item[role]["weight"], "source": found}
    result = {"pairing": item["name"], **fonts, "why": item.get("why"), "caution": item.get("caution"),
              "workspace": save_font_default(workspace, pairing=item["name"])}
    if rolled is not None:
        result["seed"] = rolled
    return result


def install_workspace(workspace, family, weight=400, italic=False, name=None, role=None, *, client=None):
    """Make one style the workspace default font for ``role``: embedded in ``brand.json`` and in
    every document created afterwards. Without ``role`` it becomes the heading font, and the result says so."""
    from .brand import save_font_default
    from .design import named

    defaulted = role is None
    role = "heading" if defaulted else role
    require(isinstance(role, str) and role, "scope workspace needs a role (heading, body or another role name)",
            field="role")
    found = {}
    data, family = fetch_font(family, weight, italic, client=client, source=found)
    name = named(name or f"{slug(family)}-{weight}{'-italic' if italic else ''}")
    result = {"name": name, "family": family, "weight": weight, "italic": italic, "role": role, "source": found,
              "file": {"bytes": len(data)}, "workspace": save_font_default(workspace, role=role, name=name, data=data)}
    if defaulted:
        result["normalized"] = ["role defaulted to heading; pass role body (--role body) for the body font"]
    return result


def roll_document(project=None, *, workspace=None, seed=None, purpose=None, mood=None, canvas=None,
                  locks=None, apply=False, slots=None, unfilled=None, variety=None,
                  recommend=None, kind=None):
    """Choose brand defaults and optionally commit the whole direction in one undo step.

    Precedence: explicit ``locks`` > the workspace brand > the purpose profile > the document's stored
    ``design_defaults`` > the seeded roll. The purpose is ``purpose`` (a purpose, alias, brief kind or size),
    else the brief ``kind``, else the document's stored purpose, else its named size; ``purpose_source`` in
    the result says which.

    ``unfilled`` says what an unfilled layout slot becomes: ``omit`` leaves it out, so the applied
    direction is final and passes ``check``; ``blank`` shows a ``[Label]`` placeholder that ``check``
    rejects until it is filled. The default is ``omit`` when ``slots`` supplies copy and ``blank``
    when it supplies none (an all-omitted layout would be empty, so the placeholders show what to fill).
    """
    require(unfilled in (None, "blank", "omit"), "unfilled must be blank or omit", field="unfilled")
    from .layouts import CONTENT_KEYS

    require(isinstance(slots or {}, dict) and set(slots or {}) <= set(CONTENT_KEYS),
            f"slots must contain layout content fields ({', '.join(CONTENT_KEYS)})", field="slots")
    from .brand import for_project, load
    kit = for_project(project) if project else load(workspace)
    choices = dict(locks or {})
    if kit.get("pairing"):
        choices.setdefault("pairing", kit["pairing"])
    if kit.get("palette"):
        palette = list(kit["palette"].values())
        choices.setdefault("palette", palette if len(palette) > 1 else palette + ["#ffffff"])
    if project and canvas is None:
        c = project.state["canvas"]
        canvas = (c["width"], c["height"])
    from .variety import history, remember, seed_for

    workspace = workspace or (getattr(project, "_workspace", None) if project else None)
    explicit_seed = seed is not None and seed != "random"
    seed, variety = seed_for(project, seed, variety, workspace)
    recent = [] if explicit_seed or variety == "fixed" else history(workspace)
    goal, source = house_style.resolve_purpose(purpose, project=project, kind=kind)
    result = roll(seed, purpose=goal or purpose, mood=mood, canvas=canvas, locks=choices,
                  variety=variety, recent=recent, recommend=recommend, content=tuple(slots or ()))
    result["purpose_source"] = source
    if kit.get("palette") and not (locks or {}).get("palette"):
        result["operation"]["colors"] = kit["palette"]
    unfilled = unfilled or ("omit" if slots else "blank")
    if unfilled == "omit":
        result["operation"]["unfilled"] = unfilled
    embedded_pair = bool(kit.get("fonts")) and "pairing" not in (locks or {})
    if embedded_pair:
        result["brand_fonts"] = {role: spec["name"] for role, spec in kit["fonts"].items()}
        result["pairing"] = None
        result["direction"]["pairing"] = "workspace-brand"
    if apply:
        require(project is not None, "roll --apply needs a document")
        from .layouts import CONTENT_KEYS
        require(isinstance(slots or {}, dict) and set(slots or {}) <= set(CONTENT_KEYS), "slots must contain layout content fields")
        candidate = project.clone()
        own_transaction = candidate.transaction is None
        if own_transaction:
            candidate.begin()
        operation = {**result["operation"], **(slots or {})}
        if not embedded_pair:
            installed = pair_fonts(candidate, result["direction"]["pairing"])
            result["fonts"] = {key: installed[key] for key in ("origin", "heading", "body")}
            operation.update(font=candidate.state["typography"]["body"],
                             display_font=candidate.state["typography"]["heading"])
        applied = candidate.apply(operation, detail="compact")
        if own_transaction:
            candidate.commit()
        project.__dict__.update(candidate.__dict__)
        result["applied"] = applied
        result["check"] = project.check(checks=["contrast", "legibility"])
    if not explicit_seed and variety != "fixed":
        remember(workspace, result)
    return result
