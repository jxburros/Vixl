"""Curated broad-use defaults. Specialized catalog entries remain available explicitly."""

SAFE_PALETTES = {
    "chalk-indigo": ("cool", ["#f7f8fc", "#e6e9f4", "#20283d", "#5267aa", "#9faed5"]),
    "linen-teal": ("calm", ["#faf7f0", "#e8e2d7", "#203c3b", "#247b78", "#aacac2"]),
    "clay-navy": ("warm", ["#faf5ef", "#eedbcc", "#243649", "#a75c45", "#c99b85"]),
    "cloud-blue": ("corporate", ["#f8fbfd", "#e2edf5", "#193b57", "#346f9f", "#a0c0d7"]),
    "oat-olive": ("natural", ["#faf8ed", "#e5e2c8", "#303a27", "#687746", "#b5be96"]),
    "rose-charcoal": ("soft", ["#fff8f8", "#f1dddd", "#393239", "#9b5369", "#d3a1b0"]),
    "mist-pine": ("calm", ["#f3f9f6", "#dce9e2", "#1f3830", "#38745e", "#9ebfac"]),
    "ivory-cobalt": ("modern", ["#fffdf4", "#eeeadc", "#233048", "#375ead", "#abbce0"]),
    "sand-terracotta": ("earthy", ["#fcf7ef", "#eee0cc", "#433326", "#a4593c", "#cd9b7b"]),
    "pearl-plum": ("elegant", ["#fbf9fc", "#e9e1ed", "#35283e", "#785687", "#bea7c8"]),
    "frost-slate": ("minimal", ["#f9fbfc", "#e5ebef", "#28343d", "#536f85", "#adbfca"]),
    "warm-graphite": ("neutral", ["#fbf9f5", "#eae5dd", "#333230", "#796c5a", "#c4b8a5"]),
    "cream-marigold": ("friendly", ["#fffbed", "#f4e9c2", "#423b25", "#927019", "#ddbd62"]),
    "sea-glass": ("fresh", ["#f6fbfa", "#dcedea", "#214441", "#408980", "#a7cfca"]),
    "quiet-lilac": ("soft", ["#faf9ff", "#e9e5f5", "#353049", "#776b9f", "#beb5d8"]),
    "paper-rust": ("crafted", ["#fcf8f1", "#eee3d3", "#3c3028", "#955431", "#cba181"]),
    "porcelain-ink": ("editorial", ["#fffffb", "#eeeee7", "#23252b", "#485667", "#a9b2b8"]),
    "sky-umber": ("clean", ["#f6fafc", "#dfeaf1", "#32393e", "#826149", "#bec9cf"]),
    "stone-berry": ("modern", ["#faf8f6", "#e8e4e0", "#343039", "#895a73", "#c1a6b5"]),
    "almond-forest": ("natural", ["#fcf8ef", "#eae0cd", "#26372c", "#507157", "#aab99b"]),
}
SAFE_STYLES = {"minimalist", "corporate-flat", "editorial", "swiss", "material", "line-art"}
SAFE_LOOKS = {"soft-shadow", "grain", "paper", "outline", "gradient", "clean-flat", "subtle-grain", "light-paper"}
SAFE_PAIRINGS = {"source-serif-sans", "ibm-plex-serif-sans", "inter-single-ui", "public-sans-single",
                 "inter-tight-inter", "roboto-slab-roboto", "roboto-material", "work-sans-bitter",
                 "montserrat-open-sans", "rubik-karla", "poppins-lora", "lexend-atkinson",
                 "merriweather-source-sans-civic", "lora-source-sans", "zilla-slab-fira-sans",
                 "noto-serif-sans-global", "literata-single-reading", "eb-garamond-single"}


def safe_pairing(entry):
    """Plain serif/sans families at moderate weights; explicitly curated families first."""
    return entry["name"] in SAFE_PAIRINGS


def palette_metadata():
    from .resources import PALETTES

    return {name: {"safe": name in SAFE_PALETTES,
                   "mood": [SAFE_PALETTES[name][0]] if name in SAFE_PALETTES else [],
                   "criteria": "Restrained color roles; ink contrast verified after role assignment"}
            for name in PALETTES}


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
            "policy": "Fresh seeds by default; explicit seed reproduces choices and ignores recent history. "
                      "Explicit choices and brand defaults win. Fonts are recommended; installation remains explicit."}
