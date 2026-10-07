"""House-style version 1: the 0.20-0.22 roll, kept so documents and tests pinned to it reproduce exactly.

Version 1 draws every dimension from the safe pools only: 20 light, low-chroma palettes, the 15
quiet safe compositions and 18 plain pairings, two light rolls in three for every purpose, and a
finishing look applied at amount 0.1. Pin it with ``house_style: 1`` (``roll``, ``document_defaults``,
or ``.vixl/variety.json``) to restore the old look. Do not change this module: it is a record.
"""

import random

from .errors import require
from .typefaces import get_pairing, list_pairings, pairings, resolve_seed, slug

V1_PAIRINGS = frozenset({
    "source-serif-sans", "ibm-plex-serif-sans", "inter-single-ui", "public-sans-single", "inter-tight-inter",
    "roboto-slab-roboto", "roboto-material", "work-sans-bitter", "montserrat-open-sans", "rubik-karla", "poppins-lora",
    "lexend-atkinson", "merriweather-source-sans-civic", "lora-source-sans", "zilla-slab-fira-sans",
    "noto-serif-sans-global", "literata-single-reading", "eb-garamond-single"})


def _safe(pairing):
    return pairing["name"] in V1_PAIRINGS


def dimensions_v1(rng, pairing, variety="medium"):
    from .resources import catalog

    entries = catalog("containers")
    containers = sorted(name for name, item in entries.items() if item.get("safe")) or sorted(entries)
    editorial = bool({"editorial", "academic", "classic"} & set(pairing.get("mood", [])))
    container = rng.choice(containers)
    variants = entries[container].get("variants") or {"default": {}}
    return {"container": container, "container_variant": rng.choice(sorted(variants)),
            "motif": rng.choice(["none", "rule", "ellipse", "rectangle"] if variety == "high" else ["none", "rule", "ellipse"]),
            "look": rng.choice(["none", "soft-shadow"] if variety in ("low", "fixed") else ["none", "soft-shadow", "subtle-grain", "light-paper"]),
            "style": "editorial" if editorial else rng.choice(["minimalist", "corporate-flat"]),
            "weight_contrast": "strong" if pairing["heading"]["weight"] - pairing["body"]["weight"] >= 300 else "moderate",
            "margin": rng.choice([0.07, 0.085, 0.10]),
            "corner": rng.choice(["sharp", "soft"] if editorial else ["sharp", "soft", "round", "pill"]),
            "background_treatment": rng.choice(["flat", "gradient"] if variety != "high" else ["flat", "gradient", "split", "pattern"]),
            "color_assignment": rng.choice(["light", "light", "dark"])}


def roll_v1(seed=None, *, purpose=None, mood=None, canvas=None, locks=None, variety="medium", recent=None):
    """Roll a coherent design direction: pairing first, then a mood-consistent palette and layout.

    Every field that ``locks`` fixes is kept; the rest come from the seed, which is returned so
    a direction worth keeping can be reproduced exactly.
    """
    from .layouts import ACCENTS, DENSITY_MARGIN, LAYOUTS, RATIOS, SAFE_COMPOSITIONS
    from .resources import PALETTES
    from .safe_catalog import SAFE_PALETTES
    from .variety import VARIETIES, choose

    locks = dict(locks or {})
    contrast = locks.get("weight_contrast")
    require(contrast in (None, "moderate", "strong"), "weight_contrast must be moderate or strong", field="locks")
    require(variety in VARIETIES, "variety must be low, medium, high or fixed", field="variety")
    recent = recent or []
    if variety == "fixed" and seed is None:
        seed = 0
    seed = resolve_seed(seed)
    rng = random.Random(seed)
    if "pairing" in locks:
        pairing = get_pairing(locks.pop("pairing"))
    else:
        pool = list_pairings(mood, purpose, full=True)["pairings"] or list_pairings(mood, full=True)["pairings"] or list(pairings())
        pool = [p for p in pool if _safe(p)] or [p for p in pairings() if _safe(p)]
        if contrast:
            pool = [p for p in pool if ("strong" if p["heading"]["weight"] - p["body"]["weight"] >= 300 else "moderate") == contrast]
            if not pool:
                pool = [p for p in pairings() if _safe(p) and ("strong" if p["heading"]["weight"] - p["body"]["weight"] >= 300 else "moderate") == contrast]
            require(pool, "No safe pairing has the requested weight contrast", field="locks")
        pairing = rng.choice(pool)
    actual_contrast = "strong" if pairing["heading"]["weight"] - pairing["body"]["weight"] >= 300 else "moderate"
    require(contrast is None or contrast == actual_contrast,
            "Locked pairing and weight_contrast conflict; unlock one choice", field="locks")
    moods = {slug(m) for m in pairing.get("mood", [])} | ({slug(mood)} if mood else set())
    palettes = sorted(name for name in PALETTES if name in SAFE_PALETTES)
    fitting = [name for name in palettes if {slug(SAFE_PALETTES[name][0])} & moods]
    if len(fitting) < 3:
        fitting = palettes
    layouts = sorted(SAFE_COMPOSITIONS)
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
        "layout": choose(rng, layouts, recent, "layout"),
        "pairing": pairing["name"],
        "palette": choose(rng, fitting or palettes, recent, "palette"),
        "mode": rng.choice(["light", "light", "dark"]),
        "type_scale": rng.choice([k for k in RATIOS if k != "augmented-fourth"]),
        "density": rng.choice(list(DENSITY_MARGIN)),
        "accent": rng.choice(ACCENTS),
        "layout_seed": rng.randrange(2**32),
        **dimensions_v1(rng, pairing, variety),
    }
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
    if "mode" in locks:
        direction["color_assignment"] = direction["mode"]
    else:
        direction["mode"] = direction["color_assignment"]
    if direction["style"] == "editorial" and direction["corner"] == "pill":
        require("corner" not in locks or "style" not in locks,
                "Editorial style and pill corners conflict; unlock one choice", field="locks")
        if "corner" in locks:
            direction["style"] = "minimalist"
        else:
            direction["corner"] = "soft"
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
        "direction": {key: value for key, value in direction.items() if key not in ("layout", "palette", "mode", "type_scale", "density", "accent", "layout_seed", "pairing")},
    }
    if "container" in locks:
        operation["direction"]["place_container"] = True
    return {
        "seed": seed,
        "variety": variety,
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
        "note": "One roll among many: roll again (new seed) for alternatives, lock what you like (--lock palette=sage), "
        "and keep a direction by its seed.",
    }
