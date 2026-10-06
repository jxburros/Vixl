"""Design styles: guidance on demand, a style tag on the document, and premade optional checks.

``style_catalog`` holds the curated catalog (principles, palettes, type, layout, imagery, do/don't
lists and rules). This module serves it (``listing``, ``describe``, ``guidance_text``), tags a
document with a style (the ``style-set`` operation, stored as ``state["style"]``), and evaluates a
style's rules on the rendered document through the same machinery as the other design checks:
``check --checks style`` adds one finding per failed rule (check ``style``), and the report lists
every rule with its measurement, so a passing rule is visible too.

Rules are advisory. Each is an evaluator in ``RULES`` taking measured facts about the document
and the rule's parameters; a document can relax any of them in its tag's ``options``.
"""

import colorsys
import difflib
import math
import re

import numpy as np

from .errors import VixlError, require
from .style_catalog import STYLES

TYPES = ("style-set",)
MAX_NAMES = 3
SEVERITIES = ("error", "warning", "info")
WEIGHT_NAME = re.compile(r"^(.+?)(?:-(\d{3}))?(-italic)?$")


# ---------------------------------------------------------------------------------------------
# Catalog access


def names():
    return sorted(STYLES)


def resolve(name):
    """The catalog key for ``name`` (case and spacing forgiving), or a helpful error."""
    require(isinstance(name, str) and name.strip(), "Style name must be a non-empty string", field="style")
    key = re.sub(r"[\s_/]+", "-", name.strip().lower())
    if key in STYLES:
        return key
    for style, entry in STYLES.items():
        if key == re.sub(r"[\s_/]+", "-", entry["title"].lower()) or key in [re.sub(r"[\s_/]+", "-", a.lower()) for a in entry.get("aka", [])]:
            return style
    close = difflib.get_close_matches(key, STYLES, 3, 0.5)
    matches = [s for s, entry in STYLES.items() if key in " ".join(entry["keywords"])]
    raise VixlError("unknown_style", f"Unknown style {name!r}"
                    + (f"; did you mean {' or '.join(map(repr, close))}?" if close else "; see vixl_styles")
                    + (f" Styles tagged {key!r}: {', '.join(matches)}." if matches else ""),
                    field="style", suggestions=close or matches[:3], allowed=names())


def listing(query=None):
    """Every style in one line each; ``query`` narrows by name, summary, keywords or use."""
    words = [w for w in re.split(r"\W+", (query or "").lower()) if w]
    rows = []
    for name in names():
        entry = STYLES[name]
        text = " ".join([name, entry["title"], entry["summary"], *entry["keywords"], *entry["best_for"]]).lower()
        if all(w in text for w in words):
            rows.append({"name": name, "title": entry["title"], "summary": entry["summary"], "era": entry["era"],
                         "keywords": entry["keywords"], "best_for": entry["best_for"],
                         "checks": [rule["id"] for rule in entry["checks"]]})
    return {"count": len(rows), "styles": rows,
            "next": "vixl_styles(action='get', name=…) for the full guidance; action='apply' tags the document; "
                    "vixl_check(checks=['style']) evaluates its rules"}


def describe(name):
    """The full guidance for one style, with each check's parameters."""
    key = resolve(name)
    entry = STYLES[key]
    return {"name": key, **{k: v for k, v in entry.items() if k != "checks"},
            "checks": [{"id": f"{key}/{rule['id']}", "kind": rule["kind"], "severity": rule["severity"],
                        "summary": rule["summary"], "fix": rule["fix"], "params": rule["params"]}
                       for rule in entry["checks"]],
            "how_to_use": [f"{{type: style-set, style: {key}}} tags the document", "check --checks style evaluates the rules",
                           f"options relax a rule: {{type: style-set, style: {key}, options: {{{entry['checks'][0]['id']}: false}}}}"]}


def guidance_text(name):
    """A compact brief for the document's design guidance (what ``apply`` stores)."""
    key = resolve(name)
    e = STYLES[key]
    palette = e["palettes"][0]
    lines = [f"Style: {e['title']}. {e['summary']}", "Principles: " + " ".join(e["principles"]),
             f"Palette ({palette['name']}): {', '.join(palette['swatches'])}. "
             f"Type: {', '.join(e['type']['categories'])}; suggested families {', '.join(e['type']['families'][:4])}. "
             f"{e['type']['weights']} {e['type']['case']}",
             f"Layout: {e['layout']['grid']} Alignment: {e['layout']['alignment']} Space: {e['layout']['negative_space']}",
             "Do: " + "; ".join(e["do"]) + ". Don't: " + "; ".join(e["dont"]) + ".",
             "Checks: " + "; ".join(rule["summary"] for rule in e["checks"]) + "."]
    return "\n".join(lines)


def palette_roles(swatches):
    """Background, ink and accent picked from a style palette: the first swatch is the background, ink is
    the swatch that contrasts most with it, accent the most colorful of the rest."""
    from .colors import contrast_ratio, parse, srgb_to_hsl

    colors = [parse(c)[:3] for c in swatches]
    background = colors[0]
    rest = list(range(1, len(colors)))
    ink = max(rest, key=lambda i: contrast_ratio(colors[i], background))
    others = [i for i in rest if i != ink]
    roles = {"background": swatches[0], "ink": swatches[ink]}
    if others:
        roles["accent"] = swatches[max(others, key=lambda i: srgb_to_hsl(colors[i])[1])]
    return roles


def apply_operations(name, palette=False, guidance=True):
    """The operations that tag a document with a style and store its brief (and optionally palette)."""
    key = resolve(name)
    ops = [{"type": "style-set", "style": key}]
    if guidance:
        ops.append({"type": "guidance", "name": key, "text": guidance_text(key), "style": "style"})
    if palette:
        swatches = STYLES[key]["palettes"][0]["swatches"]
        ops += [{"type": "palette-define", "name": key, "colors": swatches},
                {"type": "palette-apply", "name": key, "roles": palette_roles(swatches)}]
    return ops


# ---------------------------------------------------------------------------------------------
# The document tag


def schemas(add):
    from .schema import S

    add("style-set", {
        "style": {"type": ["string", "array", "null"], "items": S},
        "options": {"type": "object"},
    }, ["style"])


def _rules(key):
    return {rule["id"]: rule for rule in STYLES[key]["checks"]}


def _validated_options(keys, options):
    require(isinstance(options, dict), "options must be an object {rule: false | {param: value}}", field="options")
    known = {}
    for key in keys:
        for rule_id, rule in _rules(key).items():
            known.setdefault(rule_id, []).append(rule)
            known[f"{key}/{rule_id}"] = [rule]
    for ref, change in options.items():
        require(ref in known, f"Unknown rule {ref!r}; this style's rules: {', '.join(sorted(r for r in known if '/' not in r))}",
                field="options", allowed=sorted(r for r in known if "/" not in r))
        require(change is False or isinstance(change, dict), f"options.{ref} must be false or an object of settings",
                field="options")
        if isinstance(change, dict):
            allowed = {"enabled", "severity", *{p for rule in known[ref] for p in rule["params"]}}
            extra = sorted(set(change) - allowed)
            require(not extra, f"Unknown setting(s) {extra} for rule {ref!r}; allowed: {', '.join(sorted(allowed))}",
                    field=f"options.{ref}", allowed=sorted(allowed))
            if "severity" in change:
                require(change["severity"] in SEVERITIES, f"severity must be one of {', '.join(SEVERITIES)}",
                        field=f"options.{ref}.severity")
            if "enabled" in change:
                require(isinstance(change["enabled"], bool), "enabled must be true or false", field=f"options.{ref}.enabled")
    return options


def execute(project, op):
    value = op.get("style")
    if value is None:
        project.state.pop("style", None)
        return
    raw = [value] if isinstance(value, str) else value
    require(isinstance(raw, list) and 0 < len(raw) <= MAX_NAMES and all(isinstance(v, str) for v in raw),
            f"style is a style name or a list of up to {MAX_NAMES} names (null clears it)", field="style")
    keys = list(dict.fromkeys(resolve(v) for v in raw))
    options = _validated_options(keys, op.get("options", {}))
    project.state["style"] = {"names": keys, **({"options": options} if options else {})}


def validate_style_tag(state):
    tag = state.get("style")
    if tag is None:
        return
    require(isinstance(tag, dict) and set(tag) <= {"names", "options"} and isinstance(tag.get("names"), list)
            and 0 < len(tag["names"]) <= MAX_NAMES and all(n in STYLES for n in tag["names"]),
            "Invalid style tag", "invalid_project")
    _validated_options(tag["names"], tag.get("options", {}))


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    p = Parser(prog="vixl style-set", description="Tag the document with a design style (vixl styles lists them)")
    p.add_argument("style", nargs="+", help="style name(s); 'none' clears the tag")
    p.add_argument("--options", type=json.loads, help='JSON: {"rule-id": false | {"param": value}}')
    a = p.parse_args(args)
    style = None if a.style == ["none"] else a.style
    return {"type": cmd, "style": style[0] if style and len(style) == 1 else style,
            **({"options": a.options} if a.options else {})}


# ---------------------------------------------------------------------------------------------
# Measurements


def _rgb(value):
    from .render import color

    return color(value)[:3]


def _distance(a, b):
    return math.dist(a, b)


class Facts:
    """Lazily measured facts about the checked document (text, color, shape, render and effects)."""

    def __init__(self, project, resolved, projection, layers, content):
        self.content = content
        self.project = project
        self.state = project.state
        self.canvas = project.state["canvas"]
        self.resolved = resolved
        self.bounds = projection["bounds"]
        self.scales = projection["scales"]
        self.layers = [item for item in layers if item["type"] != "group"]
        self.leaves = [item for item in content if item["type"] != "group"]
        self._memo = {}

    def memo(self, key, make):
        if key not in self._memo:
            self._memo[key] = make()
        return self._memo[key]

    # -- text
    def texts(self):
        return [item for item in self.leaves if item["type"] == "text" and item.get("text", "").strip()]

    def size(self, item):
        return item.get("size", 0) * self.scales[item["id"]]

    def headline(self, scope="headline"):
        texts = self.texts()
        if not texts:
            return []
        top = max(self.size(item) for item in texts)
        if scope == "headline":
            return [item for item in texts if self.size(item) >= top * 0.8]
        if scope == "body":
            body = [item for item in texts if self.size(item) < top * 0.6]
            return body or texts
        return texts

    def font(self, item):
        """(family slug, weight or None, registered name or None) for a text layer."""
        fonts = self.state.get("fonts", {})
        asset = item.get("font")
        inverse = {}
        for name, path in fonts.items():
            inverse.setdefault(path, name)
        name = inverse.get(asset)
        if name is None:
            return ("bundled" if asset in (None, "DejaVuSans.ttf") else str(asset), None, None)
        match = WEIGHT_NAME.match(name)
        return match[1], (int(match[2]) if match[2] else None), name

    def category(self, item):
        from . import typefaces

        family = self.font(item)[0]
        entry = typefaces.find_font(family)
        return entry["category"] if entry else None

    # -- color
    def colors(self, distance=30):
        """Clusters of the declared colors: ``[{"rgb", "hex", "layers", "count"}]``, merged within ``distance``."""
        def build():
            found = []
            canvas = self.canvas.get("background", "transparent")
            found.append((canvas, "canvas"))
            for item in self.layers:
                if item.get("visible", True):
                    for key in ("fill", "color", "start", "end", "stroke_color", "stroke"):
                        if isinstance(item.get(key), str):
                            found.append((item[key], item["name"]))
                    for stop in item.get("stops") or []:
                        if isinstance(stop, dict) and isinstance(stop.get("color"), str):
                            found.append((stop["color"], item["name"]))
            clusters = []
            for value, source in found:
                try:
                    rgba = _rgb(value) + (self._alpha(value),)
                except VixlError:
                    continue
                if rgba[3] < 8:
                    continue
                rgb = rgba[:3]
                for cluster in clusters:
                    if _distance(cluster["rgb"], rgb) <= distance:
                        cluster["count"] += 1
                        cluster["layers"].add(source)
                        break
                else:
                    clusters.append({"rgb": rgb, "count": 1, "layers": {source}})
            for cluster in clusters:
                cluster["hex"] = "#%02x%02x%02x" % tuple(cluster["rgb"])
                cluster["layers"] = sorted(cluster["layers"])
            return clusters

        return self.memo(("colors", distance), build)

    @staticmethod
    def _alpha(value):
        from .render import color

        return color(value)[3]

    @staticmethod
    def hsv(rgb):
        return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))

    @staticmethod
    def hls(rgb):
        return colorsys.rgb_to_hls(*(c / 255 for c in rgb))

    def chromatic(self, distance=30):
        """Colors that read as a hue (not black, white or gray)."""
        return [c for c in self.colors(distance) if self.hsv(c["rgb"])[1] >= 0.25 and self.hsv(c["rgb"])[2] >= 0.15]

    # -- render
    def image(self):
        def build():
            image = self.project.render()
            image.thumbnail((256, 256))
            return np.asarray(image.convert("RGBA"), dtype=np.int32)

        return self.memo("image", build)

    def background(self):
        """The ground (the document drawn without its content layers) and the mask of pixels that are still ground
        in the full render, so a large flat shape counts as content, not as empty space."""
        def build():
            full = self.image()
            hidden = self.project.clone()
            drawn = {item["id"] for item in self.content}
            for layer in hidden.state["layers"]:
                if layer["id"] in drawn:
                    layer["visible"] = False
            from PIL import Image

            image = hidden.render()
            image = image.resize((full.shape[1], full.shape[0]), Image.Resampling.BILINEAR)
            ground = np.asarray(image.convert("RGBA"), dtype=np.int32)
            mask = np.abs(full - ground).max(axis=2) <= 12
            transparent = ground[:, :, 3] < 16
            color = None if transparent.mean() > 0.5 else tuple(float(v) for v in np.median(ground[:, :, :3].reshape(-1, 3), axis=0))
            return color, mask

        return self.memo("background", build)

    def negative_space(self):
        ground, mask = self.background()
        return float(mask.mean())

    def symmetry(self, axis="vertical"):
        ground, mask = self.background()
        a = self.image()[:, :, :3]
        ink = ~mask
        if not ink.any():
            return None
        flip = (lambda x: x[:, ::-1]) if axis == "vertical" else (lambda x: x[::-1])
        other = flip(ink)
        similar = np.sqrt(((a - flip(a)) ** 2).sum(axis=2)) <= 48
        both = ink & other & similar
        return float(both.sum() / max(1, (ink | other).sum()))

    # -- shapes and effects
    def shapes(self):
        return [item for item in self.leaves if item["type"] == "shape"]

    def styles(self, name):
        return [(item, item["styles"][name]) for item in self.layers
                if item.get("styles", {}).get(name) and item["styles"][name].get("enabled", True)]

    def effects(self):
        return [(item, e["name"]) for item in self.layers for e in item.get("effects", []) if e.get("enabled", True)]


# ---------------------------------------------------------------------------------------------
# Rule evaluators: (facts, params) -> {"status": passed|failed|skipped, "measured": {...}, "detail": str, "layers": [names]}


def passed(measured=None, **extra):
    return {"status": "passed", "measured": measured or {}, "detail": "", "layers": [], **extra}


def failed(detail, layers=(), measured=None):
    return {"status": "failed", "measured": measured or {}, "detail": detail, "layers": list(layers)}


def skipped(reason):
    return {"status": "skipped", "measured": {}, "detail": reason, "layers": []}


def _names(items, limit=8):
    return list(dict.fromkeys(item["name"] for item in items))[:limit]


def rule_max_typefaces(f, p):
    texts = f.texts()
    if not texts:
        return skipped("no text")
    families = sorted({f.font(item)[0] for item in texts})
    measured = {"typefaces": families, "count": len(families)}
    if len(families) > p["max"]:
        return failed(f"{len(families)} typefaces in use ({', '.join(families)}); this style holds to {p['max']}",
                      _names(texts), measured)
    return passed(measured)


def rule_type_categories(f, p):
    texts = f.texts()
    known = [(item, f.category(item)) for item in texts]
    known = [(item, cat) for item, cat in known if cat]
    if not known:
        return skipped("typefaces are not in the catalog (install them with vixl_font_pair / vixl_font_install)")
    found = sorted({cat for _, cat in known})
    measured = {"categories": found}
    if p.get("allowed"):
        bad = [item for item, cat in known if cat not in p["allowed"]]
        if bad:
            return failed(f"type in {', '.join(sorted({c for _, c in known if c not in p['allowed']}))} "
                          f"(this style uses {', '.join(p['allowed'])})", _names(bad), measured)
    if p.get("required") and not set(p["required"]) & set(found):
        return failed(f"none of {', '.join(p['required'])} in use (found {', '.join(found)})", _names(texts), measured)
    return passed(measured)


def rule_text_align(f, p):
    pool = f.headline(p.get("scope", "all"))
    if not pool:
        return skipped("no text")
    bad = [item for item in pool if item.get("align", "left") not in p["allowed"]]
    measured = {"aligned": sorted({item.get("align", "left") for item in pool})}
    if bad:
        return failed(f"{len(bad)} text layer(s) are {'/'.join(sorted({i.get('align', 'left') for i in bad}))}-aligned; "
                      f"use {' or '.join(p['allowed'])}", _names(bad), measured)
    return passed(measured)


def rule_edge_alignment(f, p):
    items = [item for item in f.leaves if item.get("role") != "decoration" and not item.get("allow_crop")]
    if len(items) < 3:
        return skipped("fewer than three elements")
    tol = p.get("tolerance", 3)
    edges = {}
    for item in items:
        x, y, w, h = f.bounds[item["id"]]
        edges[item["id"]] = {"l": x, "r": x + w, "cx": x + w / 2, "t": y, "b": y + h, "cy": y + h / 2}
    aligned = []
    for item in items:
        mine = edges[item["id"]]
        if any(abs(mine[k] - edges[o["id"]][k]) <= tol for o in items if o is not item for k in mine):
            aligned.append(item)
    fraction = len(aligned) / len(items)
    measured = {"aligned_fraction": round(fraction, 2), "elements": len(items)}
    if fraction < p["min_fraction"]:
        loose = [item for item in items if item not in aligned]
        return failed(f"{len(loose)} of {len(items)} elements share no edge or center with another "
                      f"({fraction:.0%} aligned; this style wants {p['min_fraction']:.0%})", _names(loose), measured)
    return passed(measured)


def rule_tilt(f, p):
    items = [item for item in f.leaves if item["type"] != "adjustment"]
    if not items:
        return skipped("no elements")
    tolerance = p.get("tolerance", 2)
    tilted = [item for item in items if min(item.get("rotation", 0) % 90, 90 - item.get("rotation", 0) % 90) > tolerance]
    fraction = len(tilted) / len(items)
    measured = {"tilted": len(tilted), "fraction": round(fraction, 2)}
    if "max_fraction" in p and fraction > p["max_fraction"] + 1e-9:
        return failed(f"{len(tilted)} element(s) are rotated off the grid", _names(tilted), measured)
    if "min_fraction" in p and fraction + 1e-9 < p["min_fraction"]:
        return failed(f"only {len(tilted)} of {len(items)} elements are tilted; this style wants about "
                      f"{p['min_fraction']:.0%} rotated", [], measured)
    return passed(measured)


def rule_shadows(f, p):
    mode = p.get("mode", "none")
    shadows = f.styles("drop-shadow")
    soft = [item for item, s in shadows if s.get("blur", 8) > 0]
    hard = [item for item, s in shadows if s.get("blur", 8) == 0]
    measured = {"soft": len(soft), "hard": len(hard)}
    allow_soft, allow_hard = mode.startswith("soft"), mode.startswith("hard")
    require_any = mode in ("hard", "soft")
    if mode == "none" and shadows:
        return failed(f"{len(shadows)} layer(s) have a drop shadow; this style uses none", _names([i for i, _ in shadows]), measured)
    if soft and not allow_soft:
        return failed(f"{len(soft)} layer(s) have a soft (blurred) shadow; this style uses hard offset shadows only"
                      if allow_hard else f"{len(soft)} layer(s) have a soft shadow", _names(soft), measured)
    if hard and not allow_hard:
        return failed(f"{len(hard)} layer(s) have a hard offset shadow; this style uses soft shadows", _names(hard), measured)
    if require_any and not shadows:
        return failed(f"no {mode} shadows; this style is recognized by them (look {'hard-shadow' if mode == 'hard' else 'soft-shadow'})",
                      [], measured)
    return passed(measured)


def rule_glow(f, p):
    glows = f.styles("outer-glow")
    measured = {"glows": len(glows)}
    if p.get("mode", "none") == "none" and glows:
        return failed(f"{len(glows)} layer(s) have an outer glow", _names([i for i, _ in glows]), measured)
    if p.get("mode") == "required" and not glows:
        return failed("no layer has a glow (look glow or neon)", [], measured)
    return passed(measured)


def _gradient_layers(f):
    return [item for item in f.layers if item["type"] == "gradient" or item.get("styles", {}).get("gradient-overlay")
            and item["styles"]["gradient-overlay"].get("enabled", True)]


def rule_gradients(f, p):
    found = _gradient_layers(f)
    measured = {"gradients": len(found)}
    if p.get("mode", "none") == "none" and found:
        return failed(f"{len(found)} gradient(s) in use; this style keeps fills flat", _names(found), measured)
    if p.get("mode") == "required" and not found:
        return failed("no gradients; this style is recognized by them", [], measured)
    return passed(measured)


def _hue_families(f, gap=30):
    hues = sorted(f.hsv(c["rgb"])[0] * 360 for c in f.chromatic())
    families = []
    for hue in hues:
        if families and hue - families[-1][-1] <= gap:
            families[-1].append(hue)
        else:
            families.append([hue])
    if len(families) > 1 and families[0][0] + 360 - families[-1][-1] <= gap:
        families[0] = families.pop() + families[0]
    return families


def rule_hue_count(f, p):
    if not f.chromatic():
        return passed({"hues": 0}) if "max" in p else skipped("no colored elements")
    families = _hue_families(f)
    measured = {"hues": len(families), "hex": [c["hex"] for c in f.chromatic()]}
    if "max" in p and len(families) > p["max"]:
        return failed(f"{len(families)} distinct hues ({', '.join(measured['hex'])}); this style allows {p['max']}", [], measured)
    if "min" in p and len(families) < p["min"]:
        return failed(f"only {len(families)} distinct hue(s); this style wants {p['min']} or more", [], measured)
    return passed(measured)


def rule_hue_range(f, p):
    colors = f.chromatic()
    if not colors:
        return skipped("no colored elements")
    inside = [c for c in colors if any(lo <= f.hsv(c["rgb"])[0] * 360 <= hi for lo, hi in p["hues"])]
    fraction = len(inside) / len(colors)
    measured = {"fraction": round(fraction, 2), "colors": [c["hex"] for c in colors]}
    if fraction < p["min_fraction"]:
        return failed(f"only {fraction:.0%} of the colors fall in the style's hue ranges "
                      f"({', '.join(f'{lo}-{hi} deg' for lo, hi in p['hues'])})", [], measured)
    return passed(measured)


def rule_saturation(f, p):
    colors = f.chromatic() or [c for c in f.colors() if f.hsv(c["rgb"])[1] > 0.08]
    if not colors:
        return skipped("no colored elements")
    mean = sum(f.hsv(c["rgb"])[1] for c in colors) / len(colors)
    measured = {"mean_saturation": round(mean, 2)}
    if "max" in p and mean > p["max"]:
        return failed(f"colors average {mean:.0%} saturation; this style is capped at {p['max']:.0%}", [], measured)
    if "min" in p and mean < p["min"]:
        return failed(f"colors average {mean:.0%} saturation; this style wants at least {p['min']:.0%}", [], measured)
    return passed(measured)


def rule_lightness(f, p):
    colors = f.colors()
    if not colors:
        return skipped("no colors")
    mean = sum(f.hls(c["rgb"])[1] for c in colors) / len(colors)
    measured = {"mean_lightness": round(mean, 2)}
    if "min" in p and mean < p["min"]:
        return failed(f"colors average {mean:.0%} lightness; this style wants at least {p['min']:.0%}", [], measured)
    if "max" in p and mean > p["max"]:
        return failed(f"colors average {mean:.0%} lightness; this style wants at most {p['max']:.0%}", [], measured)
    return passed(measured)


def _weight_rule(f, p, bad, wanted):
    pool = f.headline(p.get("scope", "headline"))
    if not pool:
        return skipped("no text")
    known = [(item, f.font(item)[1]) for item in pool]
    known = [(item, weight) for item, weight in known if weight]
    if not known:
        return skipped("font weights are unknown (register fonts with weights, e.g. vixl_font_install weight=700)")
    off = [item for item, weight in known if bad(weight)]
    measured = {"weights": sorted({weight for _, weight in known})}
    if off:
        return failed(f"text weights {measured['weights']}; this style wants {wanted}", _names(off), measured)
    return passed(measured)


def rule_min_weight(f, p):
    return _weight_rule(f, p, lambda w: w < p["weight"], f"{p['weight']} or heavier")


def rule_max_weight(f, p):
    return _weight_rule(f, p, lambda w: w > p["weight"], f"{p['weight']} or lighter")


def rule_design_check(f, p):
    from .checks import check_design

    view = f.project
    view._page_view = True
    report = check_design(view, checks=list(p["checks"]), **p.get("options", {}))
    problems = [i for i in report["issues"] if i["severity"] in ("error", "warning") and i["check"] != "coverage"
                and not i["message"].startswith("Could not measure")]
    measured = {"checks": list(p["checks"]), "findings": len(problems)}
    if problems:
        first = problems[0]
        return failed(f"{len(problems)} finding(s) from the {', '.join(p['checks'])} check: {first['message']}",
                      first["layers"], measured)
    return passed(measured)


def _rounded(item):
    return item.get("shape") == "rounded-rectangle" or (item.get("shape") == "rectangle" and item.get("radius", 0) > 0)


def rule_no_rounded_corners(f, p):
    shapes = f.shapes()
    if not shapes:
        return skipped("no shapes")
    bad = [item for item in shapes if _rounded(item) or (item.get("shape") == "ellipse" and not p.get("allow_circles", True))]
    measured = {"rounded": len(bad), "shapes": len(shapes)}
    if bad:
        return failed(f"{len(bad)} shape(s) have rounded corners; this style keeps hard edges", _names(bad), measured)
    return passed(measured)


def rule_rounded_corners(f, p):
    boxes = [item for item in f.shapes() if item.get("shape") in ("rectangle", "rounded-rectangle", "ellipse")]
    if not boxes:
        return skipped("no box shapes")
    round_ = [item for item in boxes if _rounded(item) or item.get("shape") == "ellipse"]
    fraction = len(round_) / len(boxes)
    measured = {"rounded_fraction": round(fraction, 2), "shapes": len(boxes)}
    if fraction < p["min_fraction"]:
        sharp = [item for item in boxes if item not in round_]
        return failed(f"{len(sharp)} of {len(boxes)} boxes have sharp corners; this style rounds them", _names(sharp), measured)
    return passed(measured)


def rule_min_negative_space(f, p):
    if not f.leaves:
        return skipped("no content")
    value = f.negative_space()
    measured = {"negative_space": round(value, 2)}
    if value < p["fraction"]:
        return failed(f"{value:.0%} of the canvas is empty; this style wants at least {p['fraction']:.0%}", [], measured)
    return passed(measured)


def rule_max_negative_space(f, p):
    if not f.leaves:
        return skipped("no content")
    value = f.negative_space()
    measured = {"negative_space": round(value, 2)}
    if value > p["fraction"]:
        return failed(f"{value:.0%} of the canvas is empty; this style fills the canvas (at most {p['fraction']:.0%})",
                      [], measured)
    return passed(measured)


def rule_max_colors(f, p):
    colors = f.colors(p.get("distance", 30))
    measured = {"colors": len(colors), "hex": [c["hex"] for c in colors]}
    if len(colors) > p["max"]:
        return failed(f"{len(colors)} distinct colors ({', '.join(measured['hex'])}); this style allows {p['max']}", [], measured)
    return passed(measured)


def rule_min_colors(f, p):
    colors = f.colors(p.get("distance", 30))
    measured = {"colors": len(colors), "hex": [c["hex"] for c in colors]}
    if len(colors) < p["min"]:
        return failed(f"{len(colors)} color(s); this style wants {p['min']} or more", [], measured)
    return passed(measured)


def rule_symmetry(f, p):
    if not f.leaves:
        return skipped("no content")
    score = f.symmetry(p.get("axis", "vertical"))
    if score is None:
        return skipped("nothing is drawn")
    measured = {"symmetry": round(score, 2)}
    if score < p["min"]:
        return failed(f"{score:.0%} symmetric about the {p.get('axis', 'vertical')} axis; this style wants {p['min']:.0%}",
                      [], measured)
    return passed(measured)


def rule_max_words(f, p):
    words = sum(len(re.findall(r"\w+", item["text"])) for item in f.texts())
    measured = {"words": words}
    if words > p["max"]:
        return failed(f"{words} words; this style keeps copy to {p['max']} or fewer", _names(f.texts()), measured)
    return passed(measured)


def rule_margins(f, p):
    items = [item for item in f.leaves if item.get("role") != "decoration" and not item.get("allow_crop")
             and item["type"] != "adjustment"]
    if not items:
        return skipped("no content")
    short = min(f.canvas["width"], f.canvas["height"])
    W, H = f.canvas["width"], f.canvas["height"]
    gaps = {}
    for item in items:
        x, y, w, h = f.bounds[item["id"]]
        gaps[item["id"]] = min(x, y, W - (x + w), H - (y + h)) / short
    # A layer that fills the canvas is a ground, not content.
    tight = [item for item in items if gaps[item["id"]] < p["min_fraction"]
             and f.bounds[item["id"]][2] * f.bounds[item["id"]][3] < 0.9 * W * H]
    measured = {"tightest_margin": round(min(gaps.values()), 3)}
    if tight:
        return failed(f"{len(tight)} element(s) sit within {p['min_fraction']:.0%} of the short side from an edge "
                      f"(tightest {measured['tightest_margin']:.1%})", _names(tight), measured)
    return passed(measured)


def rule_type_scale_ratio(f, p):
    sizes = [f.size(item) for item in f.texts()]
    if len(sizes) < 2:
        return skipped("fewer than two text layers")
    ratio = max(sizes) / max(min(sizes), 0.01)
    measured = {"ratio": round(ratio, 1), "largest": round(max(sizes)), "smallest": round(min(sizes))}
    if "min" in p and ratio < p["min"]:
        return failed(f"largest text is {ratio:.1f}x the smallest; this style wants {p['min']}x or more", [], measured)
    if "max" in p and ratio > p["max"]:
        return failed(f"largest text is {ratio:.1f}x the smallest; this style keeps it under {p['max']}x", [], measured)
    return passed(measured)


def rule_effects(f, p):
    present = sorted({name for _, name in f.effects()})
    measured = {"effects": present}
    if p.get("require_any") and not set(p["require_any"]) & set(present):
        return failed(f"none of the effects {', '.join(p['require_any'][:5])} … is applied", [], measured)
    banned = [item for item, name in f.effects() if name in p.get("forbid", [])]
    if banned:
        return failed(f"effects {sorted({n for _, n in f.effects() if n in p['forbid']})} are not used by this style", _names(banned), measured)
    return passed(measured)


def _stroked(item):
    value = item.get("stroke")
    return isinstance(value, str) and f_alpha(value) > 0 and item.get("stroke_width", 1) > 0


def f_alpha(value):
    return Facts._alpha(value)


def rule_min_stroke_width(f, p):
    shapes = f.shapes()
    if not shapes:
        return skipped("no shapes")
    stroked = [item for item in shapes if _stroked(item)]
    measured = {"outlined": len(stroked), "shapes": len(shapes)}
    if not stroked:
        return failed("no shape has an outline; this style outlines its shapes", _names(shapes), measured)
    thin = [item for item in stroked if item.get("stroke_width", 1) < p["width"]]
    if thin:
        return failed(f"{len(thin)} outline(s) are thinner than {p['width']} px", _names(thin), measured)
    return passed(measured)


def rule_stroke_style(f, p):
    shapes = f.shapes()
    if not shapes:
        return skipped("no shapes")
    filled = [item for item in shapes if isinstance(item.get("fill"), str) and f_alpha(item["fill"]) > 0]
    bare = [item for item in shapes if not _stroked(item)]
    measured = {"filled": len(filled), "unstroked": len(bare)}
    bad = list({item["id"]: item for item in filled + bare}.values())
    if bad:
        return failed(f"{len(bad)} shape(s) are filled or have no outline; this style draws outlines only", _names(bad), measured)
    return passed(measured)


def rule_uniform_stroke(f, p):
    widths = {item["name"]: item.get("stroke_width", 1) for item in f.shapes() + [i for i in f.leaves if i["type"] == "pen"] if _stroked(item)}
    if len(widths) < 2:
        return skipped("fewer than two outlined shapes")
    spread = max(widths.values()) - min(widths.values())
    measured = {"widths": sorted(set(widths.values()))}
    if spread > p.get("tolerance", 0.5):
        return failed(f"stroke widths vary from {min(widths.values()):g} to {max(widths.values()):g} px; "
                      "use one weight", list(widths)[:8], measured)
    return passed(measured)


def rule_dark_background(f, p):
    ground, mask = f.background()
    if ground is None:
        return skipped("the canvas is transparent")
    from .colors import relative_luminance

    luminance = relative_luminance(tuple(v / 255 for v in ground))
    measured = {"luminance": round(luminance, 3), "background": "#%02x%02x%02x" % tuple(round(v) for v in ground)}
    if luminance > p["max_luminance"]:
        return failed(f"the ground {measured['background']} is light (luminance {luminance:.2f}); this style is dark", [], measured)
    return passed(measured)


def rule_min_layers(f, p):
    count = len([item for item in f.leaves if item["type"] != "adjustment"])
    measured = {"elements": count}
    if count < p["min"]:
        return failed(f"{count} element(s); this style layers {p['min']} or more", [], measured)
    return passed(measured)


def rule_min_text_size(f, p):
    texts = f.texts()
    if not texts:
        return skipped("no text")
    small = [item for item in texts if f.size(item) < p["size"]]
    measured = {"smallest": round(min(f.size(item) for item in texts), 1)}
    if small:
        return failed(f"{len(small)} text layer(s) are under {p['size']} px", _names(small), measured)
    return passed(measured)


RULES = {name[5:]: fn for name, fn in globals().items() if name.startswith("rule_")}


# ---------------------------------------------------------------------------------------------
# Evaluation and the check hook


def selected(style, state):
    """The (style names, options) to check: an explicit ``style`` argument, else the document's tag."""
    if style is not None:
        raw = [style] if isinstance(style, str) else list(style)
        keys = list(dict.fromkeys(resolve(v) for v in raw))
        return keys, state.get("style", {}).get("options", {}) if set(keys) <= set(state.get("style", {}).get("names", [])) else {}
    tag = state.get("style")
    return (list(tag["names"]), tag.get("options", {})) if tag else ([], {})


def evaluate(facts, keys, options):
    """Every rule of the styles in ``keys`` evaluated: ``[{id, style, rule, severity, status, …}]``."""
    results = []
    for key in keys:
        for rule in STYLES[key]["checks"]:
            ref = f"{key}/{rule['id']}"
            change = options.get(ref, options.get(rule["id"]))
            if change is False or (isinstance(change, dict) and change.get("enabled") is False):
                results.append({"id": ref, "style": key, "rule": rule["id"], "summary": rule["summary"],
                                "status": "disabled", "severity": rule["severity"]})
                continue
            params = {**rule["params"], **{k: v for k, v in (change or {}).items() if k not in ("enabled", "severity")}}
            severity = (change or {}).get("severity", rule["severity"])
            outcome = RULES[rule["kind"]](facts, params)
            results.append({"id": ref, "style": key, "rule": rule["id"], "summary": rule["summary"],
                            "fix": rule["fix"], "severity": severity, **outcome})
    return results


def check_style(candidate, resolved, projection, layers, content, issue, style=None):
    """Add one finding per failed rule of the document's style (or ``style``); returns the rule report."""
    keys, options = selected(style, candidate.state)
    if not keys:
        issue("style", "warning", "No style is set: tag the document with style-set (vixl_styles lists the styles) or "
              "pass style=…", [])
        return {"styles": [], "rules": []}
    facts = Facts(candidate, resolved, projection, layers, content)
    by_name = {item["name"]: item for item in resolved.values()}
    results = evaluate(facts, keys, options)
    for result in results:
        if result["status"] != "failed":
            continue
        issue("style", result["severity"], f"{result['style']}: {result['summary']}: {result['detail']}. {result['fix']}.",
              [by_name[n] for n in result["layers"] if n in by_name], rule=result["id"], style=result["style"],
              measured=result["measured"], fix=result["fix"])
    counts = {status: sum(1 for r in results if r["status"] == status) for status in ("passed", "failed", "skipped", "disabled")}
    return {"styles": keys, "summary": counts,
            "rules": [{k: v for k, v in r.items() if k in ("id", "status", "severity", "measured", "detail", "layers")}
                      for r in results]}
