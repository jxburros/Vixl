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

from .errors import VixlError, require

DATA = Path(__file__).parent / "data"
CSS_API = "https://fonts.googleapis.com/css2"
FONT_HOST = "fonts.gstatic.com"
LIMIT = 16 * 1024 * 1024
PALETTE_MOODS = {
    "midnight": {"minimal", "corporate", "modern", "calm", "serious"},
    "ocean": {"calm", "fresh", "clean", "friendly", "coastal"},
    "sunset": {"warm", "friendly", "energetic", "playful"},
    "forest": {"natural", "organic", "earthy", "calm"},
    "desert": {"warm", "earthy", "natural", "rustic", "vintage"},
    "berry": {"bold", "romantic", "dramatic", "luxurious"},
    "lavender": {"dreamy", "playful", "creative", "soft"},
    "pastel": {"playful", "soft", "friendly", "whimsical"},
    "neon": {"bold", "energetic", "futuristic", "tech", "loud"},
    "earth": {"natural", "earthy", "organic", "rustic"},
    "copper": {"warm", "vintage", "crafted", "luxurious"},
    "ice": {"cool", "clean", "tech", "fresh"},
    "rose": {"romantic", "elegant", "soft", "warm"},
    "mint": {"fresh", "energetic", "playful", "natural"},
    "gold": {"luxurious", "elegant", "classic", "formal"},
    "slate": {"minimal", "corporate", "neutral", "modern", "tech"},
    "coral": {"playful", "friendly", "energetic", "bold"},
    "autumn": {"warm", "rustic", "vintage", "cozy"},
    "spring": {"soft", "friendly", "romantic", "warm"},
    "summer": {"energetic", "friendly", "playful", "bold"},
    "winter": {"calm", "elegant", "soft", "muted"},
    "mono": {"minimal", "brutalist", "neutral", "editorial", "serious"},
    "accessible-blue": {"corporate", "trustworthy", "clean", "academic"},
    "accessible-green": {"natural", "trustworthy", "clean"},
    "accessible-red": {"bold", "urgent", "energetic"},
    "candy": {"playful", "bold", "loud", "youthful"},
    "retro": {"retro", "bold", "vintage", "editorial"},
    "nordic": {"calm", "minimal", "cool", "modern"},
    "coffee": {"warm", "cozy", "rustic", "crafted"},
    "plum": {"elegant", "creative", "dreamy", "luxurious"},
    "peach": {"warm", "friendly", "soft", "playful"},
    "sage": {"calm", "natural", "organic", "minimal"},
}


@lru_cache(maxsize=1)
def fonts():
    return json.loads((DATA / "fonts.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def pairings():
    return json.loads((DATA / "font-pairings.json").read_text(encoding="utf-8"))


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
        result["detail"] = "vixl font pairing NAME (vixl_fonts view=pairing) explains why a pairing works"
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
    return random.Random(seed).choice(pool), seed


def roll(seed=None, *, purpose=None, mood=None, canvas=None, locks=None):
    """Roll a coherent design direction: pairing first, then a mood-consistent palette and layout.

    Every field that ``locks`` fixes is kept; the rest come from the seed, which is returned so
    a direction worth keeping can be reproduced exactly.
    """
    from .layouts import ACCENTS, DENSITY_MARGIN, LAYOUTS, RATIOS
    from .resources import PALETTES

    locks = dict(locks or {})
    seed = resolve_seed(seed)
    rng = random.Random(seed)
    if "pairing" in locks:
        pairing = get_pairing(locks.pop("pairing"))
    else:
        pool = list_pairings(mood, purpose, full=True)["pairings"] or list_pairings(mood, full=True)["pairings"] or list(pairings())
        pairing = rng.choice(pool)
    moods = {slug(m) for m in pairing.get("mood", [])} | ({slug(mood)} if mood else set())
    palettes = sorted(PALETTES)
    fitting = [name for name in palettes if {slug(m) for m in PALETTE_MOODS.get(name, ())} & moods]
    layouts = sorted(LAYOUTS)
    if purpose:
        suited = [name for name in layouts if any(slug(purpose) in slug(b) for b in LAYOUTS[name]["best_for"])]
        layouts = suited or layouts
    if canvas:
        aspect = canvas[0] / canvas[1]
        if aspect < 0.87:
            layouts = [n for n in layouts if n not in ("banner", "letterhead", "business-card", "slide-title")] or layouts
        elif aspect > 1.6:
            layouts = [n for n in layouts if n not in ("story-vertical", "letterhead", "framed")] or layouts
    direction = {
        "layout": rng.choice(layouts),
        "pairing": pairing["name"],
        "palette": rng.choice(fitting or palettes),
        "mode": rng.choice(["light", "light", "dark"]),
        "type_scale": rng.choice([k for k in RATIOS if k != "augmented-fourth"]),
        "density": rng.choice(list(DENSITY_MARGIN)),
        "accent": rng.choice(ACCENTS),
        "layout_seed": rng.randrange(2**32),
    }
    unknown = set(locks) - set(direction)
    require(not unknown, f"Unknown lock(s) {sorted(unknown)}; lockable: {', '.join(direction)}", field="locks")
    direction.update(locks)
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
    }
    return {
        "seed": seed,
        "direction": direction,
        "pairing": pairing,
        "steps": [
            f"vixl font pair {pairing['name']}",
            f"vixl layout apply {direction['layout']} --seed {direction['layout_seed']} --palette {direction['palette']} "
            f"--mode {direction['mode']} --type-scale {direction['type_scale']} --density {direction['density']} "
            f"--accent {direction['accent']} --set title=…",
        ],
        "operation": operation,
        "note": "One roll among many: roll again (new seed) for alternatives, lock what you like (--lock palette=sage), "
        "and keep a direction by its seed.",
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


def install_font(project, family, weight=400, italic=False, name=None, role=None, *, client=None):
    """Download (or reuse from cache), embed and register one style; optionally give it a role."""
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
    return {"name": name, "family": family, "weight": weight, "italic": italic, **({"role": role} if role else {}),
            "source": {**found, "cache_dir": str(cache_dir), "cache_dir_from": chosen_by, "bundled_fallback": False},
            "file": {"asset": asset, "bytes": len(data), "sha256": digest}}


def origin_of(*installed):
    """``cache``, ``download`` or ``mixed``: where a set of installed fonts came from."""
    origins = {item["source"].get("origin", "unknown") for item in installed}
    return origins.pop() if len(origins) == 1 else "mixed"


def pair_fonts(project, pairing=None, *, seed=None, mood=None, best_for=None, client=None):
    """Install a pairing's heading and body styles and make them the document typography."""
    rolled = None
    if pairing in (None, "random"):
        item, rolled = roll_pairing(seed, mood, best_for)
    else:
        item = get_pairing(pairing)
    heading = install_font(project, item["heading"]["family"], item["heading"]["weight"], role="heading", client=client)
    body = install_font(project, item["body"]["family"], item["body"]["weight"], role="body", client=client)
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


def roll_document(project=None, *, workspace=None, seed=None, purpose=None, mood=None, canvas=None,
                  locks=None, apply=False, slots=None):
    """Choose brand defaults and optionally commit the whole direction in one undo step."""
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
    result = roll(seed, purpose=purpose, mood=mood, canvas=canvas, locks=choices)
    if kit.get("palette") and not (locks or {}).get("palette"):
        result["operation"]["colors"] = kit["palette"]
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
    return result
