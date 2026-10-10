"""``vixl catalog export``: one versioned JSON bundle of the design catalogs, for host applications.

Everything is read from the registries that drive Vixl itself (``sizes``, ``resources``, ``typefaces``,
``layouts``, ``briefs``, ``guidance``, ``looks``, ``style_catalog``, ``checks``), never copied, so a
host that syncs the bundle stays in step with the engine release that wrote it. Only built-in entries
are exported (no user-library additions), so the bundle is the same on every machine. Fonts appear
as metadata only; no font file is ever embedded.

``CATALOG_SCHEMA_VERSION`` changes when a field is removed or changes meaning; adding a field or an
entry does not change it. ``data/catalog.schema.json`` describes the bundle.
"""

import json
from pathlib import Path

from .errors import require

CATALOG_SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).parent / "data" / "catalog.schema.json"
SECTIONS = ("sizes", "palettes", "typefaces", "layouts", "briefs", "guidance", "looks", "styles", "checks")

# Layout slot proportions are measured by applying each layout to this canvas with fixed options.
REFERENCE_CANVAS = (1000, 1000)
REFERENCE_OPTIONS = {"seed": 0, "palette": "midnight", "mode": "light", "density": "balanced",
                     "type_scale": "major-third", "unfilled": "blank"}

# What each check looks for and the severities its findings can carry. A finding's ``check`` field is
# its stable ID; ``tests/test_catalog.py`` scans the source so a new check or severity cannot go unlisted.
CHECK_INFO = {
    "bounds": ("Layers cut off by, or lying outside, the canvas edge (deliberate crops and bleed are info).",
               ("error", "warning", "info")),
    "overlap": ("Visible pixels of two layers overlapping (two text layers: error).", ("error", "warning")),
    "contrast": ("Text contrast against what is actually behind it: 4.5:1, or 3:1 for large text.", ("error",)),
    "safe_area": ("Content outside the safe area (canvas size preset or safe_area) or inside an avoid zone.",
                  ("error", "warning", "info")),
    "legibility": ("Body measure, and text too small to read at thumbnail width.", ("warning", "info")),
    "blanks": ("Layout or template placeholders ([Label]) that were never filled.", ("error",)),
    "placeholders": ("Leftover template copy (lorem ipsum, TODO/TBD, 'Headline here'), unresolved or undefined "
                     "${variables}.", ("error", "warning")),
    "fonts": ("Characters no font can draw, fallback glyphs, and the proofing fallback font.",
              ("error", "warning", "info")),
    "brand": ("Colors, fonts and minimum contrast from the workspace brand kit.", ("error", "warning")),
    "content": ("Layers that draw nothing, strokes without coverage, content huddled on a large canvas.",
                ("warning",)),
    "form": ("Form fields: labels, names, overlap, tab order and values that overflow their boxes.",
             ("error", "warning")),
    "links": ("Linked documents that are missing, stale or unreadable.", ("error", "warning", "info")),
    "diagram": ("Diagram nodes and edges: overlaps, crossings, labels and routing.", ("error", "warning")),
    "flow": ("Text flows: overset text, widows, orphans and broken frame chains.", ("error", "warning")),
    "codes": ("QR codes and barcodes: quiet zone, size, contrast and decodability.", ("error", "warning")),
    "print": ("Print readiness: dpi, image resolution, ink limit, small type and the live area.",
              ("error", "warning")),
    "color_vision": ("Text and chart series that become hard to tell apart under color-vision deficiencies.",
                     ("error", "warning")),
    "guides": ("Layers that nearly, but do not quite, sit on a guide.", ("warning",)),
    "alignment": ("Edges and centres that nearly, but do not quite, line up.", ("warning",)),
    "drawing": ("Imported hand drawings: lost strokes, gaps and unfilled regions.", ("warning",)),
    "style": ("The premade rules of the document's style tag (see style_rules).", ("error", "warning")),
    "motion": ("Animation: loop seam, poster frame and motion that leaves the canvas.", ("warning", "info")),
    "character": ("Character rigs: detached parts and joints that tear apart in poses.", ("error", "warning")),
    "captions": ("Timed captions: overlap, reading speed and placement.", ("error", "warning")),
    "connected": ("Parts of a group that float free of its main body.", ("warning",)),
    "cost": ("Layers that take over 10× the median layer to draw, with the blur, effects or strokes behind it.",
             ("warning",)),
    "suite": ("A failed check-suite rule restated as a finding so the built-in repairs (repair-layout, "
              "repair=true) can act on it.", ("error", "warning")),
    "coverage": ("Checks that could not inspect part of the document (reported, never a failure).", ("warning",)),
    "title_position": ("Deck: slide titles that jump between pages.", ("warning",)),
    "type_scale": ("Deck: too many distinct type sizes across the deck.", ("warning",)),
    "words": ("Deck: pages with more words than max_words.", ("warning",)),
    "min_font": ("Deck: text smaller than min_font on the projected, screen or phone slide.", ("warning",)),
    "notes": ("Deck: pages without speaker notes.", ("warning",)),
    "empty": ("Deck: pages with nothing on them.", ("warning",)),
}


def _sizes():
    from .sizes import ALIASES, CATEGORIES, PX, SIDES, SIZES, resolve

    items = []
    for name, entry in SIZES.items():
        info = resolve(name)
        unit = entry["unit"]
        safe = entry.get("safe", 0)
        safe_unit = {side: safe.get(side, 0) for side in SIDES} if isinstance(safe, dict) else dict.fromkeys(SIDES, safe)
        safe_px = info["safe"] if isinstance(info["safe"], dict) else dict.fromkeys(SIDES, info["safe"])
        item = {"name": name, "category": entry["category"], "description": entry["description"],
                "unit": unit, "width": entry["width"], "height": entry["height"], "pixels": info["trim"],
                "safe": {"unit": unit, **safe_unit}, "safe_pixels": safe_px}
        if unit != PX:
            bled = resolve(name, bleed=True)
            item.update(dpi=entry["dpi"], bleed={"unit": unit, "amount": entry.get("bleed", 0),
                                                 "pixels": bled["bleed"]})
        items.append(item)
    return {"categories": list(CATEGORIES), "items": items, "aliases": dict(ALIASES)}


def _palettes():
    import random

    from . import house_style
    from .colors import contrast_ratio, parse
    from .layouts import assign_roles
    from .resources import PALETTES

    def ratio(a, b):
        return round(contrast_ratio(parse(a)[:3], parse(b)[:3]), 2)

    meta = house_style.entries("palettes")
    items = []
    for name, colors in PALETTES.items():
        modes = {}
        for mode in house_style.palette_modes(name):
            roles = assign_roles({"palette": name, "mode": mode, "_house_style_version": house_style.VERSION},
                                 random.Random(0))
            roles = {key: value for key, value in roles.items() if not key.startswith("_")}
            modes[mode] = {"roles": roles, "contrast": {
                "ink_on_background": ratio(roles["ink"], roles["background"]),
                "muted_on_background": ratio(roles["muted"], roles["background"]),
                "accent_text_on_background": ratio(roles["accent-text"], roles["background"]),
                "accent_on_background": ratio(roles["accent"], roles["background"]),
                "on_accent_on_accent": ratio(roles["on-accent"], roles["accent"]),
            }}
        tier = house_style.tier_of("palettes", name)
        items.append({"name": name, "colors": list(colors), "tier": tier, "safe": tier == "safe",
                      "mood": list(meta.get(name, {}).get("mood", [])), "modes": modes})
    from .palette_roles import ROLES

    return {"roles": list(ROLES), "house_style_version": house_style.VERSION,
            "contrast_targets": house_style.craft("contrast"), "items": items}


def _typefaces():
    from .layouts import RATIOS, ROLE_STEPS
    from .typefaces import fonts, list_pairings

    return {"families": fonts(), "pairings": list_pairings(full=True)["pairings"],
            "type_scales": [{"name": name, "ratio": ratio} for name, ratio in RATIOS.items()],
            "type_scale_steps": dict(ROLE_STEPS)}


def _proportions(name):
    """Each filled slot's box as fractions of the reference canvas."""
    from . import Project

    width, height = REFERENCE_CANVAS
    project = Project(width, height)
    project.apply({"type": "layout-apply", "name": name, **REFERENCE_OPTIONS})
    boxes = {}
    for blank in project.state.get("layout", {}).get("blanks", []):
        x, y, w, h = project.inspect(blank["layer"])["canvas_bounds"]
        boxes[blank["slot"]] = [round(x / width, 3), round(y / height, 3), round(w / width, 3), round(h / height, 3)]
    return boxes


def _layouts():
    from .layouts import LAYOUTS, describe

    items = []
    for name in LAYOUTS:
        info = describe(name)
        items.append({"name": name, "description": info["description"], "tier": info["tier"],
                      "safe": info.get("safe", False), "best_for": info["best_for"],
                      "principles": info.get("principles", []),
                      "slots": {key: {"label": slot["label"], "hint": slot.get("hint", "")}
                                for key, slot in info["slots"].items()},
                      "also_accepts": info.get("also_accepts", []),
                      "proportions": _proportions(name)})
    return {"reference": {"canvas": list(REFERENCE_CANVAS), "options": dict(REFERENCE_OPTIONS),
                          "note": "proportions are [x, y, width, height] fractions of the reference canvas for the slots "
                                  "the layout draws when unfilled (optional slots it omits have none); layouts adapt "
                                  "to the real canvas, so treat them as a sketch"},
            "items": items}


def _briefs():
    from .briefs import KINDS, START_HERE, tests
    from .sizes import SIZES, canonical

    items = []
    for kind, item in KINDS.items():
        sizes = list(item.get("sizes", []))
        category = SIZES[canonical(sizes[0])]["category"] if sizes else None
        plan = tests(kind)
        items.append({"kind": kind, "title": item["title"], "summary": item["summary"],
                      "keywords": item.get("keywords", []), "approach": item.get("approach", []),
                      "operations": item.get("operations", []), "size_category": category, "sizes": sizes,
                      "layouts": item.get("layouts", []), "looks": item.get("looks", []),
                      "styles": item.get("styles", []), "guidance": item.get("guidance", []),
                      "checks": {"starter_suite": plan["starter_suite"], "rules": plan["rules_to_adapt"]},
                      "example": item.get("example", [])})
    return {"start_here": list(START_HERE), "items": items}


def _summary(text):
    first = text.strip().split("\n\n", 1)[0].replace("\n", " ")
    if len(first) <= 280:
        return first
    cut = first[:280].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + " …"


def _guidance():
    from .guidance import GUIDANCE

    return {"items": [{"name": name, "summary": _summary(text), "text": text} for name, text in GUIDANCE.items()]}


def _looks():
    from .looks import catalog

    return {"items": [{"name": name, "summary": item["summary"], "best_for": item["best_for"],
                       "tier": item["tier"], "safe": item["safe"]} for name, item in catalog().items()]}


def _styles():
    from .style_catalog import STYLES

    return {"items": [{"name": name, "title": item["title"], "summary": item["summary"],
                       "keywords": item.get("keywords", []), "best_for": item.get("best_for", []),
                       "palette_names": item.get("palette_names", []),
                       "pairings": item.get("type", {}).get("pairings", []),
                       "layouts": item.get("layout", {}).get("layouts", []),
                       "rules": [rule["id"] for rule in item.get("checks", [])]}
                      for name, item in STYLES.items()]}


def _checks():
    import inspect

    from .checks import ACTIONS, CHECKS, OPTIONAL_CHECKS, check_design, classify
    from .deck import DECK_CHECKS
    from .resources import SUITES
    from .style_catalog import STYLES
    from .workflow_schema import RULE_KINDS, RULE_PROPERTIES

    def family(name):
        return ("default" if name in CHECKS else "optional" if name in OPTIONAL_CHECKS
                else "deck" if name in DECK_CHECKS else "report")

    checks = []
    for name, (description, severities) in CHECK_INFO.items():
        checks.append({"id": name, "family": family(name), "description": description,
                       "severities": list(severities),
                       "actions": {s: classify({"check": name, "severity": s}) for s in severities}})
    defaults = {key: param.default for key, param in inspect.signature(check_design).parameters.items()
                if isinstance(param.default, (int, float, str)) and not isinstance(param.default, bool)}

    def thresholds(rule):
        return {k: v for k, v in rule.items() if k not in ("id", "kind", "severity", "description")}

    suites = [{"name": name, "description": suite.get("description", ""),
               "rules": [{"id": rule.get("id", rule["kind"]), "kind": rule["kind"],
                          "severity": rule.get("severity", RULE_PROPERTIES["severity"]["default"]),
                          "thresholds": thresholds(rule)} for rule in suite.get("rules", [])]}
              for name, suite in SUITES.items()]
    style_rules = [{"style": style, "id": rule["id"], "kind": rule["kind"], "severity": rule["severity"],
                    "summary": rule["summary"], "fix": rule["fix"], "thresholds": rule["params"]}
                   for style, item in STYLES.items() for rule in item.get("checks", [])]
    return {"actions": list(ACTIONS),
            "default": list(CHECKS), "optional": list(OPTIONAL_CHECKS), "deck": list(DECK_CHECKS),
            "items": checks, "defaults": defaults,
            "suite_rule_kinds": list(RULE_KINDS),
            "suite_rule_kind_description": RULE_PROPERTIES["kind"]["description"],
            "suites": suites, "style_rules": style_rules}


BUILDERS = {"sizes": _sizes, "palettes": _palettes, "typefaces": _typefaces, "layouts": _layouts,
            "briefs": _briefs, "guidance": _guidance, "looks": _looks, "styles": _styles, "checks": _checks}


def export_catalog(sections=None):
    """The catalog bundle as a dict: ``catalog_schema_version``, ``vixl_version``, ``counts`` and one
    entry per section (all of ``SECTIONS`` by default)."""
    from . import __version__

    sections = list(sections or SECTIONS)
    unknown = sorted(set(sections) - set(SECTIONS))
    require(not unknown, f"Unknown catalog section(s) {unknown}; sections are {', '.join(SECTIONS)}",
            field="sections", allowed=list(SECTIONS))
    bundle = {"catalog_schema_version": CATALOG_SCHEMA_VERSION, "vixl_version": __version__,
              "schema": "https://github.com/jxburros/Vixl/blob/v" + __version__ + "/src/vixl/data/catalog.schema.json"}
    body = {name: BUILDERS[name]() for name in SECTIONS if name in sections}
    counts = {}
    for name, value in body.items():
        if name == "typefaces":
            counts.update(families=len(value["families"]), pairings=len(value["pairings"]),
                          type_scales=len(value["type_scales"]))
        else:
            counts[name] = len(value["items"])
    return {**bundle, "counts": counts, **body}


def schema():
    """The JSON Schema the bundle conforms to."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def write_catalog(path, *, overwrite=False, sections=None):
    """Write the bundle to ``path`` as UTF-8 JSON; refuses an existing file unless ``overwrite``."""
    target = Path(path)
    require(overwrite or not target.exists(), f"{target} exists; pass overwrite=True (--overwrite) to replace it",
            field="out")
    bundle = export_catalog(sections)
    data = json.dumps(bundle, indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    return {"written": str(target), "bytes": len(data.encode("utf-8")),
            "catalog_schema_version": CATALOG_SCHEMA_VERSION, "vixl_version": bundle["vixl_version"],
            "counts": bundle["counts"]}


def cli(args):
    """``vixl catalog export [--out FILE] [--overwrite] [--section NAME …] [--schema]``."""
    from .commands import Parser

    p = Parser(prog="vixl catalog")
    p.add_argument("action", choices=["export", "schema"],
                   help="export: the catalog bundle (to --out, or printed); schema: the bundle's JSON Schema")
    p.add_argument("--out", "-o", help="Write the bundle to this file instead of printing it")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing --out file")
    p.add_argument("--section", action="append", choices=list(SECTIONS),
                   help="Export only this section (repeatable; default all)")
    a = p.parse_args(args)
    if a.action == "schema":
        if a.out:
            target = Path(a.out)
            require(a.overwrite or not target.exists(), f"{target} exists; pass --overwrite to replace it",
                    field="out")
            target.write_text(SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            return {"written": str(target)}
        return schema()
    if a.out:
        return write_catalog(a.out, overwrite=a.overwrite, sections=a.section)
    return export_catalog(a.section)
