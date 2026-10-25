"""Workspace brand policy. JSON contains data only; embedded assets never read server paths.

``brand.json`` holds the palette roles (plus ``palette.extra`` approved colours), typography (a pairing and
fonts under any role name, ``fonts.allowed`` families, text ``stages``), logos, the contrast floor, required
elements, compliance rules (``colors.strict``/``tolerance``, ``logo.clear_space``/``min_size``) and named
``presets`` that override parts of the base brand (``extends`` chains one preset onto another). A document
selects a preset with the ``brand-preset`` operation.
"""

from copy import deepcopy
import base64
import hashlib
import json
import re
from pathlib import Path

from .assets import open_image, read_bounded
from .constants import PROOFING_FONT
from .errors import VixlError, require

FIELDS = ("name", "palette", "pairing", "fonts", "logos", "minimum_contrast", "required_elements", "stages",
          "colors", "logo", "facts", "words", "placeholders", "suites", "elements", "styles", "presets")
# Fields a preset may override; ``extends`` names the preset it builds on.
PRESET_FIELDS = tuple(field for field in FIELDS if field != "presets") + ("extends",)
# Dict fields merge key by key when a preset overrides them; every other field is replaced.
MERGED = ("palette", "fonts", "stages", "colors", "logo", "words", "elements", "styles")
LENGTH = re.compile(r"^(\d+(?:\.\d+)?)\s*(px|mm|cm|in|pt)?$")
UNIT_INCHES = {"mm": 1 / 25.4, "cm": 1 / 2.54, "in": 1, "pt": 1 / 72}
LOGO_NAME = re.compile(r"(^|[-_ /])logo([-_ /]|$)", re.IGNORECASE)
LOGO_FIELDS = ("name", "data_base64", "purpose", "place", "auto", "x", "y", "width", "height")
LOGO_PURPOSES = ("icon", "wordmark", "avatar", "lockup")
PLACE_FIELDS = ("anchor", "margin", "width_fraction", "safe")
# A logo placed by ``place`` without its own numbers: a fifth of the canvas width, 5 % of the shorter side in.
PLACE_DEFAULTS = {"anchor": "top-left", "margin": 0.05, "width_fraction": 0.2, "safe": True}
ELEMENT_NAME = re.compile(r"[A-Za-z0-9][\w-]{0,63}")


def load(workspace=None, preset=None):
    """The workspace brand, with ``preset`` (a name in ``presets``) applied; {} without brand.json."""
    raw = load_raw(workspace)
    return resolve(raw, preset) if raw else {}


def load_raw(workspace=None):
    path = brand_path(workspace)
    if not path.exists():
        return {}
    try:
        return validate(json.loads(read_bounded(path, 16 * 1024 * 1024)))
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", f"Invalid brand.json: {exc}") from exc


def brand_path(workspace):
    path = Path(workspace or Path.cwd()) / "brand.json"
    require(
        path.resolve().is_relative_to(path.parent.resolve()),
        "brand.json must stay inside the workspace",
        "forbidden",
    )
    return path


def merge(base, override):
    """``override`` (a preset) on ``base``: dict fields merge per key, the rest replace."""
    out = deepcopy(base)
    for key, value in override.items():
        if key == "extends":
            continue
        if key in MERGED and isinstance(value, dict) and isinstance(out.get(key), dict):
            merged = {**out[key], **deepcopy(value)}
            if key == "palette" and isinstance(out[key].get("extra"), dict) and isinstance(value.get("extra"), dict):
                merged["extra"] = {**out[key]["extra"], **deepcopy(value["extra"])}
            out[key] = merged
        else:
            out[key] = deepcopy(value)
    return out


def preset_chain(kit, name):
    """Preset names from the outermost ancestor to ``name``, following ``extends``."""
    presets = kit.get("presets") or {}
    chain = []
    while name is not None:
        require(name in presets, f"Unknown brand preset {name!r}; presets: {', '.join(presets) or 'none'}",
                field="preset", allowed=sorted(presets))
        require(name not in chain, f"Brand presets extend each other in a cycle: {' → '.join([*chain, name])}",
                field="preset")
        chain.append(name)
        name = presets[name].get("extends")
    return chain[::-1]


def resolve(kit, preset=None):
    """The brand a document uses: the base, then each preset of the chain ending at ``preset``."""
    if not preset:
        return kit
    out = {key: value for key, value in kit.items() if key != "presets"}
    for name in preset_chain(kit, preset):
        out = merge(out, kit["presets"][name])
    out["preset"] = preset
    try:
        return _validate(out, preset=True)
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", f"Invalid brand.json preset {preset!r}: {exc}") from exc


def font_specs(kit):
    """``{role: spec}`` for the embedded or named fonts (``fonts.allowed`` is a family list, not a role)."""
    return {role: spec for role, spec in (kit.get("fonts") or {}).items() if role != "allowed"}


def extra_colors(kit):
    """``{name: {"color", "max_fraction"?}}`` for ``palette.extra`` (a list is named extra-1, extra-2 …)."""
    extra = (kit.get("palette") or {}).get("extra") or {}
    if isinstance(extra, list):
        extra = {f"extra-{index + 1}": value for index, value in enumerate(extra)}
    return {name: value if isinstance(value, dict) else {"color": value} for name, value in extra.items()}


def role_colors(kit):
    return {role: value for role, value in (kit.get("palette") or {}).items() if role != "extra"}


def length_px(value, dpi=None):
    """A logo size in pixels: a number is pixels; ``"12mm"``, ``"0.5in"``, ``"24pt"`` use the canvas dpi (96 without one)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = LENGTH.match(value.strip()) if isinstance(value, str) else None
    require(match, "Logo sizes are pixels or a length such as 12mm, 0.5in or 24pt", field="logo.min_size")
    number, unit = float(match.group(1)), match.group(2) or "px"
    return number if unit == "px" else number * UNIT_INCHES[unit] * (dpi or 96)


# Copy and contract policy (words, placeholder patterns, inherited suites); validated by validate_policy.
POLICY_FIELDS = {"words", "placeholders", "suites"}


def validate_policy(kit):
    from .copy_checks import validate_brand
    from .assurance import validate_library_names

    validate_brand(kit)
    if "suites" in kit:
        validate_library_names(kit["suites"], "brand.json suites")


def validate(kit):
    try:
        require(isinstance(kit, dict), "brand.json must be an object")
        kit = _validate(kit)
        for name, preset in (kit.get("presets") or {}).items():
            resolve(kit, name)
        return kit
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", f"Invalid brand.json: {exc}") from exc


CONTRAST_FIELDS = ("text", "large_text", "large_text_px", "large_bold_text_px")


def _ratio(value, name):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 21,
            f"Brand {name} must be a contrast ratio 1–21")


def validate_contrast(value):
    """``minimum_contrast`` is one ratio for all text, or ``{text, large_text, large_text_px,
    large_bold_text_px}``: a floor for body text and one for large text (WCAG asks 3:1 for 24 px+, or
    18.66 px+ bold)."""
    if not isinstance(value, dict):
        _ratio(value, "minimum_contrast")
        return
    unknown = sorted(set(value) - set(CONTRAST_FIELDS))
    require(not unknown, f"Unknown minimum_contrast field(s) {unknown}; use {', '.join(CONTRAST_FIELDS)}")
    require("text" in value, "minimum_contrast needs text (the floor for body text)")
    for name in ("text", "large_text"):
        if name in value:
            _ratio(value[name], f"minimum_contrast.{name}")
    for name in ("large_text_px", "large_bold_text_px"):
        if name in value:
            require(isinstance(value[name], (int, float)) and not isinstance(value[name], bool)
                    and 1 <= value[name] <= 10000, f"Brand minimum_contrast.{name} must be 1–10000 px")


def contrast_floor(kit, requested=None):
    """The contrast text needs: ``{text, large_text, large_text_px, large_bold_text_px}``. A caller's
    ``requested`` ratio applies to both tiers (default WCAG 4.5:1 and 3:1); a brand floor raises each tier and
    is kept even when a caller asks for less. A bare brand number is the floor for both tiers."""
    from .house_style import rule

    sizes = rule("minimum_text")
    floor = {"text": requested or 4.5, "large_text": requested or 3.0,
             "large_text_px": sizes["large_text_px"], "large_bold_text_px": sizes["large_bold_text_px"]}
    value = (kit or {}).get("minimum_contrast")
    if value is None:
        return floor
    if not isinstance(value, dict):
        value = {"text": value, "large_text": value}
    floor["text"] = max(requested or 0, value["text"])
    floor["large_text"] = max(requested or 0, value.get("large_text", value["text"]))
    if "large_text_px" in value:
        floor["large_text_px"] = value["large_text_px"]
        floor["large_bold_text_px"] = value.get(
            "large_bold_text_px", value["large_text_px"] * sizes["large_bold_text_px"] / sizes["large_text_px"])
    elif "large_bold_text_px" in value:
        floor["large_bold_text_px"] = value["large_bold_text_px"]
    return floor


def required_contrast(floor, size_px, bold=False):
    """The ratio a text of ``size_px`` canvas pixels needs under ``floor`` (from ``contrast_floor``)."""
    large = size_px >= floor["large_bold_text_px" if bold else "large_text_px"]
    return floor["large_text" if large else "text"]


def _validate(kit, preset=False):
    from .colors import parse
    from .layouts import ROLES
    from .palette_roles import EXTRA_ROLES
    from .type_roles import role_name, validate_stages

    require(isinstance(kit, dict), "brand.json must be an object")
    unknown = sorted(set(kit) - set(FIELDS) - ({"preset"} if preset else set()))
    require(not unknown, f"Unknown brand.json field {', '.join(unknown)}; fields: {', '.join(FIELDS)}")
    palette = kit.get("palette", {})
    require(
        isinstance(palette, dict) and set(palette) <= {*ROLES, *EXTRA_ROLES, "extra"},
        "Brand palette maps layout roles to colors (accent-2 and accent-3 for rolls with two or three accents; "
        "plus extra: approved colors without a role)",
    )
    for value in role_colors(kit).values():
        parse(value)
    extra = palette.get("extra", {})
    require(isinstance(extra, (dict, list)), "palette.extra is a list of colors or {name: color}")
    for name, spec in extra_colors(kit).items():
        require(isinstance(name, str) and name and isinstance(spec.get("color"), str)
                and set(spec) <= {"color", "max_fraction"},
                "Each palette.extra entry is a color or {color, max_fraction}")
        parse(spec["color"])
        if "max_fraction" in spec:
            fraction = spec["max_fraction"]
            require(isinstance(fraction, (int, float)) and 0 <= fraction <= 1,
                    "palette.extra max_fraction is a share of the canvas, 0–1")
    validate_contrast(kit.get("minimum_contrast", 4.5))
    require(
        isinstance(kit.get("required_elements", []), list)
        and all(isinstance(x, str) and x for x in kit.get("required_elements", [])),
        "required_elements must be layer names",
    )
    fonts = kit.get("fonts", {})
    require(isinstance(fonts, dict), "Brand fonts map role names to font specifications")
    allowed = fonts.get("allowed", [])
    require(isinstance(allowed, list) and all(isinstance(x, str) and x for x in allowed),
            "fonts.allowed is a list of font family names")
    for role, spec in font_specs(kit).items():
        role_name(role, f"fonts.{role}")
        require(isinstance(spec, dict), f"fonts.{role} is a font specification")
        if "data_base64" in spec:
            require(isinstance(spec.get("name"), str) and isinstance(spec.get("data_base64"), str),
                    "Each embedded brand font needs name and data_base64")
        else:
            require(isinstance(spec.get("family"), str) and spec["family"]
                    and isinstance(spec.get("weight", 400), int) and isinstance(spec.get("name", ""), str),
                    f"fonts.{role} needs name and data_base64 (embedded) or family and weight (fetched)")
    if "stages" in kit:
        validate_stages(kit["stages"])
    logos = kit.get("logos", [])
    require(
        isinstance(logos, list) and len(logos) <= 20,
        "Brand logos must be a list of at most 20 embedded images",
    )
    for spec in logos:
        validate_logo(spec)
    validate_elements(kit.get("elements", {}))
    if "styles" in kit:
        from .styles import validate_brand_styles

        validate_brand_styles(kit["styles"])
    colors = kit.get("colors", {})
    require(isinstance(colors, dict) and set(colors) <= {"strict", "tolerance"},
            "Brand colors takes strict (true/false) and tolerance (0–255)")
    require(isinstance(colors.get("strict", False), bool), "colors.strict is true or false")
    tolerance = colors.get("tolerance", 0)
    require(isinstance(tolerance, (int, float)) and 0 <= tolerance <= 255, "colors.tolerance is 0–255")
    logo = kit.get("logo", {})
    require(isinstance(logo, dict) and set(logo) <= {"clear_space", "min_size", "min_width", "layers"},
            "Brand logo takes clear_space, min_size, min_width and layers")
    if "clear_space" in logo:
        require(isinstance(logo["clear_space"], (int, float)) and 0 <= logo["clear_space"] <= 4,
                "logo.clear_space is a fraction of the logo height, 0–4")
    for key in ("min_size", "min_width"):
        if key in logo:
            length_px(logo[key])
    require(isinstance(logo.get("layers", []), list) and all(isinstance(x, str) and x for x in logo.get("layers", [])),
            "logo.layers lists the layer names that are logos")
    presets = kit.get("presets", {})
    require(isinstance(presets, dict), "presets maps preset names to partial brands")
    for name, item in presets.items():
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][\w-]{0,63}", name) and name != "none",
                "Preset names are 1–64 letters, numbers, underscores or hyphens (not none)")
        require(isinstance(item, dict) and set(item) <= set(PRESET_FIELDS),
                f"Preset {name!r} may set {', '.join(PRESET_FIELDS)}")
        require(item.get("extends") is None or isinstance(item["extends"], str),
                f"Preset {name!r} extends another preset by name")
    if "pairing" in kit:
        from .typefaces import get_pairing

        get_pairing(kit["pairing"])
    validate_policy(kit)
    if "facts" in kit:
        from .group_consistency import validate_facts

        validate_facts(kit["facts"], "brand.json facts")
    return kit


def _fraction(value, low, high, name, *, open_low=False):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and (low < value if open_low else low <= value) and value <= high,
            f"{name} is a number {'above' if open_low else 'from'} {low:g} {'up ' if open_low else ''}to {high:g}")


def validate_logo(spec):
    """One ``logos`` entry: ``{name, data_base64, purpose?, place?, auto?, x?, y?, width?, height?}``."""
    from .geometry import ANCHORS, canonical_anchor

    require(isinstance(spec, dict) and isinstance(spec.get("name"), str) and spec["name"]
            and isinstance(spec.get("data_base64"), str), "Each brand logo needs name and data_base64")
    unknown = sorted(set(spec) - set(LOGO_FIELDS))
    require(not unknown, f"Logo {spec['name']!r}: unknown field(s) {unknown}; fields: {', '.join(LOGO_FIELDS)}")
    require(spec.get("purpose", "icon") in LOGO_PURPOSES,
            f"Logo {spec['name']!r}: purpose is one of {', '.join(LOGO_PURPOSES)}")
    require(isinstance(spec.get("auto", True), bool), f"Logo {spec['name']!r}: auto is true or false")
    for key in ("x", "y", "width", "height"):
        if key in spec:
            require(isinstance(spec[key], (int, float)) and not isinstance(spec[key], bool)
                    and (key in ("x", "y") or spec[key] > 0), f"Logo {spec['name']!r}: {key} is a number of pixels")
    place = spec.get("place")
    if place is None:
        return
    require(isinstance(place, dict) and set(place) <= set(PLACE_FIELDS),
            f"Logo {spec['name']!r}: place takes {', '.join(PLACE_FIELDS)}")
    if "anchor" in place:
        require(canonical_anchor(place["anchor"]), f"Logo {spec['name']!r}: place.anchor is one of "
                f"{', '.join(ANCHORS)}")
    if "margin" in place:
        _fraction(place["margin"], 0, 0.5, f"Logo {spec['name']!r}: place.margin (a share of the shorter canvas side)")
    if "width_fraction" in place:
        _fraction(place["width_fraction"], 0, 1, f"Logo {spec['name']!r}: place.width_fraction (a share of the "
                  "canvas width)", open_low=True)
    require(isinstance(place.get("safe", True), bool), f"Logo {spec['name']!r}: place.safe is true or false")


def auto_logos(kit):
    """The logos every layout and template gets: those with ``auto``, which defaults to true only when the brand
    has a single logo (several logos are variants to choose from with ``brand-logo``)."""
    logos = kit.get("logos") or []
    return [spec for spec in logos if spec.get("auto", len(logos) == 1)]


def choose_logo(kit, purpose=None):
    """The logo ``brand-logo`` places: the first of ``purpose``, else the first automatic logo, else the first."""
    logos = kit.get("logos") or []
    require(logos, "Brand logo not found: brand.json has no logos; add logos to place one with brand-logo", "not_found",
            field="purpose")
    if purpose is None:
        return (auto_logos(kit) or logos)[0]
    found = [spec for spec in logos if spec.get("purpose", "icon") == purpose]
    require(found, f"Brand logo not found: brand.json has no {purpose} logo; purposes: "
            f"{', '.join(sorted({spec.get('purpose', 'icon') for spec in logos}))}", "not_found", field="purpose",
            allowed=sorted({spec.get("purpose", "icon") for spec in logos}))
    return found[0]


def logo_geometry(project, spec, size, override=None):
    """``{x, y, width, height}`` for a logo whose image is ``size``: its ``place`` (with ``override`` from
    brand-logo) inside the canvas, or the fixed ``x``/``y``/``width``/``height`` a logo without ``place`` gives."""
    from .geometry import ANCHORS, canonical_anchor
    from .sizes import live_insets

    override = {key: value for key, value in (override or {}).items() if value is not None}
    if spec.get("place") is None and not override:
        box = {"x": spec.get("x", 0), "y": spec.get("y", 0)}
        box.update({key: spec[key] for key in ("width", "height") if key in spec})
        return box
    place = {**PLACE_DEFAULTS, **(spec.get("place") or {}), **override}
    canvas = project.state["canvas"]
    width, height = canvas["width"], canvas["height"]
    margin = place["margin"] * min(width, height)
    # The margin is measured from the canvas edge; safe keeps the logo inside the live (safe) area as well.
    left, top, right, bottom = (max(margin, inset) for inset in (live_insets(canvas) if place["safe"] else (0,) * 4))
    area = (left, top, max(1.0, width - left - right), max(1.0, height - top - bottom))
    fraction_given = "width_fraction" in override or "width_fraction" in (spec.get("place") or {})
    logo_w = spec["width"] if "width" in spec and not fraction_given else width * place["width_fraction"]
    logo_h = logo_w * size[1] / size[0]
    if logo_h > area[3]:
        logo_w, logo_h = logo_w * area[3] / logo_h, area[3]
    fx, fy = ANCHORS[canonical_anchor(place["anchor"])]
    return {"x": round(area[0] + (area[2] - logo_w) * fx), "y": round(area[1] + (area[3] - logo_h) * fy),
            "width": max(1, round(logo_w)), "height": max(1, round(logo_h))}


def place_logo(project, spec, override=None, name=None):
    """Add (or move, when a layer of that name exists) the logo ``spec`` as a raster layer."""
    from .assets import add_encoded
    from .operations import execute

    asset, image = add_encoded(project, embedded(spec["data_base64"]))
    box = logo_geometry(project, spec, image.size, override)
    name = name or spec["name"]
    provenance = {"type": "brand-logo", "logo": spec["name"], "purpose": spec.get("purpose", "icon")}
    existing = next((layer for layer in project.state["layers"] if layer["name"] == name), None)
    if existing is None:
        execute(project, {"type": "add", "name": name, "asset": asset, "provenance": provenance, **box})
        return
    require(existing["type"] == "raster", f"{name!r} is a {existing['type']} layer; brand-logo places the logo as "
            "an image layer (pass name for another layer)", field="name")
    from .render import stored_origin

    existing.update(asset=asset, provenance=provenance, constraints={},
                    width=box.get("width", image.size[0]), height=box.get("height", image.size[1]))
    existing["x"], existing["y"] = stored_origin(existing, (box["x"], box["y"]))
    project.state["active_layer"] = existing["id"]


def schemas(add):
    from .geometry import ANCHORS
    from .schema import S, field

    add("brand-logo", {
        "purpose": {"enum": list(LOGO_PURPOSES), "description": "Which brand logo: the first with this purpose "
                    "(icon, wordmark, avatar, lockup); default the brand's automatic logo, else its first."},
        "anchor": {"enum": list(ANCHORS), "description": "Where on the canvas: overrides the logo's place.anchor "
                   "(default its own, else top-left)."},
        "width_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1, "description": "Logo width as a "
                           "share of the canvas width (default the logo's place.width_fraction, else 0.2)."},
        "margin": {"type": "number", "minimum": 0, "maximum": 0.5, "description": "Distance from the canvas edge as a "
                   "share of the shorter side (default the logo's place.margin, else 0.05); the logo also stays inside "
                   "the safe area unless its place.safe is false."},
        "name": field(S, "Layer name; default the logo's name. A layer of that name is moved, not duplicated."),
    })


def execute(project, op):
    kit = for_project(project)
    require(kit, "brand.json not found in the workspace; brand-logo places one of its logos", "not_found",
            field="purpose")
    spec = choose_logo(kit, op.get("purpose"))
    place_logo(project, spec, {key: op.get(key) for key in ("anchor", "margin", "width_fraction")}, op.get("name"))


def validate_elements(elements):
    """``elements``: ``{name: portable object}``, the record ``object-save`` keeps, plus ``assets`` (the embedded
    files its layers name, base64). The shape is checked on every read; the files decode when placed and in
    ``brand validate``."""
    from .objects import ASSET_REFERENCE

    require(isinstance(elements, dict) and len(elements) <= 100, "elements maps up to 100 names to portable objects")
    for name, item in elements.items():
        require(isinstance(name, str) and ELEMENT_NAME.fullmatch(name),
                "Element names are 1–64 letters, numbers, underscores or hyphens")
        require(isinstance(item, dict) and isinstance(item.get("layers"), list) and item["layers"]
                and all(isinstance(layer, dict) and isinstance(layer.get("id"), str) for layer in item["layers"])
                and isinstance(item.get("root"), str)
                and any(layer["id"] == item["root"] for layer in item["layers"]),
                f"Element {name!r} is a portable object: {{root, layers, fonts?, assets?}} (object-save's record)")
        assets = item.get("assets", {})
        require(isinstance(assets, dict) and len(assets) <= 64
                and all(isinstance(key, str) and ASSET_REFERENCE.fullmatch(key)
                        and key.split("/")[0] in ("assets", "fonts", "masks") and isinstance(value, str)
                        for key, value in assets.items()),
                f"Element {name!r}: assets maps asset names (assets/<sha256>.png …) to base64 file bytes")


def element_assets(item, limits):
    """The decoded files of an element, each checked against the SHA-256 in its name and decoded."""
    from .assets import decode
    from .fonts import validate_font

    found = {}
    for key, value in (item.get("assets") or {}).items():
        data = embedded(value)
        require(len(data) <= limits.max_asset_bytes, f"Element asset {key} exceeds the byte limit", "resource_limit")
        require(hashlib.sha256(data).hexdigest() == key.split("/")[1].split(".")[0],
                f"Element asset {key} does not match its SHA-256", "invalid_brand")
        if key.startswith("fonts/"):
            validate_font(data)
        else:
            decode(data, limits)
        found[key] = data
    return found


def element(project, name):
    """``(record, assets)`` of the brand element ``name`` for ``object-place brand:NAME``."""
    kit = for_project(project)
    elements = kit.get("elements") or {}
    require(name in elements, f"Brand element {name!r} not found" + (f"; elements: {', '.join(sorted(elements))}"
            if elements else "; brand.json has no elements"), "not_found", field="name",
            suggestions=sorted(elements)[:10])
    item = deepcopy(elements[name])
    assets = element_assets(item, project.limits)
    item.pop("assets", None)
    return item, assets


def element_from_document(other, ref=None):
    """A brand element from a document: the object ``ref`` (default the whole document as one group), with the
    files its layers use embedded as base64."""
    from .objects import from_document, snapshot

    if ref is None:
        item, assets = from_document(other)
    else:
        from .objects import ASSET_REFERENCE

        root = other.layer(ref)
        require(root["type"] == "group", f"{root['name']!r} is not a group; an element is a group (an object)",
                field="object")
        item = snapshot(other, root["id"])
        assets = {key: other.assets[key] for key in set(ASSET_REFERENCE.findall(json.dumps(item)))
                  if key in other.assets}
    item["assets"] = {key: base64.b64encode(data).decode("ascii") for key, data in sorted(assets.items())
                      if key.split("/")[0] in ("assets", "fonts", "masks")}
    return item


def for_project(project):
    workspace = getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None)
    preset = project.state.get("brand_preset")
    if not preset:
        return load(workspace)
    raw = load_raw(workspace)
    if raw and preset in (raw.get("presets") or {}):
        return resolve(raw, preset)
    if raw:
        from .notices import warn

        warn(project, f"brand preset {preset!r} is not in this workspace's brand.json; the base brand applies")
    return raw


def embedded(value):
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", "Invalid embedded brand asset") from exc


def install_kit(project, kit, skip=(), logos=True):
    """Swatches, fonts, stages and the automatic logos of ``kit`` into the document (inside an apply's
    candidate). A logo is added once, by layer name; ``logos=False`` leaves them to the caller (a template that
    places its own with ``brand-logo``)."""
    palette = role_colors(kit)
    swatches = project.state.setdefault("swatches", {})
    swatches.update(palette)
    swatches.update({name: spec["color"] for name, spec in extra_colors(kit).items()})
    register_fonts(project, kit, skip=skip)
    for spec in auto_logos(kit) if logos else ():
        if not any(layer["name"] == spec["name"] for layer in project.state["layers"]):
            place_logo(project, spec)


def prepare(project, operation):
    """Apply defaults inside Project.apply's copy-on-write candidate."""
    kit = for_project(project)
    if not kit:
        return operation
    op = deepcopy(operation)
    palette = role_colors(kit)
    logos = True
    if op["type"] == "template-apply":
        from .resources import get

        logos = not get("templates", op["name"], workspace=getattr(project, "_workspace", None)).get("places_logo")
    install_kit(project, kit, skip={role for role, field in ROLE_FIELDS.items() if field in op}, logos=logos)
    if op["type"] == "layout-apply" and "palette" not in op:
        if palette:
            op["palette"] = list(palette.values()) if len(palette) > 1 else [*palette.values(), "#ffffff"]
            op["colors"] = {**palette, **op.get("colors", {})}
    return op


ROLE_FIELDS = {"heading": "display_font", "body": "font"}


def _register(project, role, name, data):
    from .fonts import validate_font
    from .operations import execute

    if data is None:
        execute(project, {"type": "font-register", "name": name, "role": role})
        return
    validate_font(data)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    execute(project, {"type": "font-register", "name": name, "asset": asset, "role": role})


def register_fonts(project, kit, skip=()):
    """Embed and register the kit's fonts as the document typography, one per role, and copy its text stages.

    An embedded ``fonts`` entry wins for its role and a ``family`` entry is fetched like a pairing; the
    ``pairing`` supplies heading or body when ``fonts`` leaves them open. Returns ``{role: {name, from}}``."""
    from .typefaces import fetch_font, get_pairing, slug

    applied, pair = {}, None
    specs = font_specs(kit)
    for role in dict.fromkeys(["heading", "body", *specs]):
        if role in skip:
            continue
        spec = specs.get(role)
        if spec and "data_base64" in spec:
            _register(project, role, spec["name"], embedded(spec["data_base64"]))
            applied[role] = {"name": spec["name"], "from": "fonts"}
            continue
        if spec:
            family, weight = spec["family"], spec.get("weight", 400)
        elif kit.get("pairing") and role in ("heading", "body"):
            pair = pair or get_pairing(kit["pairing"])
            family, weight = pair[role]["family"], pair[role]["weight"]
        else:
            continue
        name = (spec or {}).get("name") or f"{slug(family)}-{weight}"
        data = None if name in project.state.get("fonts", {}) else fetch_font(family, weight)[0]
        _register(project, role, name, data)
        applied[role] = {"name": name, "from": "fonts" if spec else "pairing", "family": family, "weight": weight}
    from .type_roles import refont, validate_stages

    # The brand owns the document's stage map: a preset without stages returns them to the house defaults.
    stages = validate_stages(kit["stages"]) if kit.get("stages") else None
    if stages != project.state.get("type_stages"):
        if stages:
            project.state["type_stages"] = stages
        else:
            project.state.pop("type_stages", None)
        refont(project)
    return applied


def apply_workspace_fonts(project, workspace=None):
    """Give a new document the workspace's default typography (``brand.json`` pairing/fonts).

    Fonts are embedded, so the document stays portable. Returns a report for the creation result,
    or None when the workspace sets no default fonts. A failed download leaves the document as it
    was and is reported under ``error`` rather than failing the creation."""
    kit = load(workspace) if workspace is not None else for_project(project)
    if not (kit.get("pairing") or font_specs(kit) or kit.get("stages")):
        return None
    report = {"source": "brand.json", **({"pairing": kit["pairing"]} if kit.get("pairing") else {})}
    candidate = project.clone()
    try:
        report["applied"] = register_fonts(candidate, kit)
    except VixlError as exc:
        report["error"] = str(exc)
        report["hint"] = "Run font-pair (or vixl font pair) once the font cache or network is available"
        return report
    project.__dict__.update(candidate.__dict__)
    from .variety import record_as_creation

    record_as_creation(project, "Apply workspace fonts")
    return report


def save_font_default(workspace, *, pairing=None, role=None, name=None, data=None):
    """Write a workspace font default into ``brand.json``: a pairing (which replaces embedded
    heading/body fonts) or one role's embedded font (which overrides the pairing for that role)."""
    from .type_roles import role_name

    path = brand_path(workspace)
    load_raw(workspace)  # refuse to rewrite an invalid brand.json
    raw = json.loads(read_bounded(path, 16 * 1024 * 1024)) if path.exists() else {}
    replaced = []
    if pairing is not None:
        raw["pairing"] = pairing
        fonts = raw.get("fonts", {})
        replaced = [f"fonts.{r}" for r in ("heading", "body") if r in fonts]
        for role in ("heading", "body"):
            fonts.pop(role, None)
        if not fonts:
            raw.pop("fonts", None)
    else:
        require(role, "scope workspace needs a role (heading, body or another role name)", field="role")
        role_name(role)
        require(role != "allowed", "allowed is the fonts.allowed family list, not a role", field="role")
        fonts = raw.setdefault("fonts", {})
        if role in fonts:
            replaced = [f"fonts.{role}"]
        fonts[role] = {"name": name, "data_base64": base64.b64encode(data).decode("ascii")}
    validate(deepcopy(raw))
    write_raw(path, raw)
    return {"path": "brand.json", "scope": "workspace", **({"pairing": pairing} if pairing else {"role": role, "name": name}),
            **({"replaced": replaced} if replaced else {}),
            "note": "New documents in this workspace get these fonts embedded at creation; existing documents are unchanged."}


def encoded(raw):
    return (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_raw(path, raw):
    """Replace ``brand.json`` at ``path`` in one step (a temporary file renamed over it)."""
    tmp = Path(path).with_name(".brand.json.tmp")
    try:
        tmp.write_bytes(encoded(raw))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def use_preset(project, name):
    """The ``brand-preset`` operation: select a preset of the workspace brand for this document (``none``
    returns to the base brand) and install its swatches, fonts and stages."""
    if name == "none":
        project.state.pop("brand_preset", None)
    else:
        workspace = getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None)
        raw = load_raw(workspace)
        require(raw, "brand.json not found in the workspace; brand-preset selects one of its presets", field="name")
        preset_chain(raw, name)
        project.state["brand_preset"] = name
    kit = for_project(project)
    if kit:
        install_kit(project, kit)


def font_family(project, font):
    """The family name stored in a font file (``Noto Sans`` for the proofing fallback), or None."""
    from .text import face, primary_font_data

    try:
        names = face(primary_font_data(project, {"font": font, "text": "x"}))[0]["name"]
    except Exception:  # noqa: BLE001 - An unreadable font has no family to compare; the fonts check reports it.
        return None
    for name_id in (16, 1):
        value = names.getDebugName(name_id)
        if value:
            return value
    return None


def logo_layers(project, kit):
    """Layers the brand treats as logos: ``logo.layers``, else its embedded logos' names, else layers named
    logo (``logo``, ``logo-mark``, ``brand logo`` …). Children of a logo group belong to the group."""
    names = set((kit.get("logo") or {}).get("layers") or []) or {spec["name"] for spec in kit.get("logos", [])}
    layers = project.state["layers"]
    found = [layer for layer in layers if layer["name"] in names or placed_logo(layer)]
    if not names and not found:
        found = [layer for layer in layers if LOGO_NAME.search(layer["name"])]
    ids = {layer["id"] for layer in found}
    by_id = {layer["id"]: layer for layer in layers}

    def inside(layer):
        parent = by_id.get(layer.get("parent"))
        while parent:
            if parent["id"] in ids:
                return True
            parent = by_id.get(parent.get("parent"))
        return False

    return [layer for layer in found if not inside(layer)]


def _gap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(bx - (ax + aw), ax - (bx + bw), 0)
    dy = max(by - (ay + ah), ay - (by + bh), 0)
    return (dx * dx + dy * dy) ** 0.5


def _contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1] and outer[0] + outer[2] >= inner[0] + inner[2]
            and outer[1] + outer[3] >= inner[1] + inner[3])


def check_logos(project, kit, issue, visible):
    """Clear space around each logo and its minimum size (``logo.clear_space``, ``min_size``, ``min_width``)."""
    rules = kit.get("logo") or {}
    if not rules:
        return
    from .design import descendants
    from .render import resolve_layout

    bounds = resolve_layout(project)
    dpi = project.state["canvas"].get("dpi")
    by_id = {layer["id"]: layer for layer in project.state["layers"]}
    for logo in logo_layers(project, kit):
        if not visible(logo) or logo["id"] not in bounds:
            continue
        box = bounds[logo["id"]]
        for key, axis, label in (("min_size", 3, "tall"), ("min_width", 2, "wide")):
            if key in rules:
                minimum = length_px(rules[key], dpi)
                if box[axis] + 0.5 < minimum:
                    issue("brand", "error", f"Logo {logo['name']!r} is {box[axis]:g} px {label}; the brand minimum is "
                          f"{minimum:g} px ({rules[key]})", [logo], measured=box[axis], minimum=round(minimum, 2))
        if not rules.get("clear_space"):
            continue
        space = rules["clear_space"] * box[3]
        zone = (box[0] - space, box[1] - space, box[2] + 2 * space, box[3] + 2 * space)
        family = {logo["id"], *descendants(project, logo["id"])}
        ancestor = by_id.get(logo.get("parent"))
        while ancestor:
            family.add(ancestor["id"])
            ancestor = by_id.get(ancestor.get("parent"))
        for other in project.state["layers"]:
            if (other["id"] in family or other["type"] == "group" or other.get("role") == "background"
                    or not visible(other) or other["id"] not in bounds):
                continue
            rect = bounds[other["id"]]
            # A backdrop that holds the whole clear-space zone is the ground the logo sits on, not a crowding element.
            if _contains(rect, zone):
                continue
            gap = _gap(box, rect)
            if gap + 0.5 < space:
                issue("brand", "error", f"{other['name']!r} is {gap:.0f} px from logo {logo['name']!r}; the brand clear "
                      f"space is {space:.0f} px ({rules['clear_space']:g} × logo height)", [logo, other],
                      gap=round(gap, 1), required=round(space, 1))


def check_fonts(project, kit, issue, layers):
    """``fonts.allowed``: every visible text layer's family must be one of them (or a brand font)."""
    allowed = (kit.get("fonts") or {}).get("allowed")
    if not allowed:
        return False
    families = {family.casefold() for family in allowed}
    families |= {spec["family"].casefold() for spec in font_specs(kit).values() if spec.get("family")}
    for spec in font_specs(kit).values():
        if "data_base64" in spec:
            from .text import face

            try:
                name = face(embedded(spec["data_base64"]))[0]["name"]
                families.add((name.getDebugName(16) or name.getDebugName(1) or "").casefold())
            except Exception:  # noqa: BLE001 - brand validate reports an unreadable embedded font
                pass
    seen = {}
    for layer in layers:
        if layer["type"] != "text":
            continue
        fonts = [layer.get("font", PROOFING_FONT)]
        fonts += [span["font"] for span in (layer.get("rich") or {}).get("spans", []) if span.get("font")]
        for font in dict.fromkeys(fonts):
            if font not in seen:
                seen[font] = font_family(project, font)
            family = seen[font]
            if family is None or family.casefold() not in families:
                issue("brand", "error", f"Font {family or font!r} is not a brand font; allowed families: "
                      f"{', '.join(allowed)}", [layer], font=family or font, allowed=list(allowed))
                break
    return True


def check_fractions(project, kit, issue):
    """``palette.extra`` colours with ``max_fraction``: their share of the drawn canvas."""
    limited = {name: spec for name, spec in extra_colors(kit).items() if "max_fraction" in spec}
    if not limited:
        return
    import numpy as np

    from .render import color

    pixels = np.asarray(project.render().convert("RGBA")).reshape(-1, 4)
    pixels = pixels[pixels[:, 3] > 0, :3].astype(np.int16)
    if not len(pixels):
        return
    for name, spec in limited.items():
        rgb = np.array(color(spec["color"])[:3], dtype=np.int16)
        share = float((np.abs(pixels - rgb).max(axis=1) <= 8).mean())
        if share > spec["max_fraction"]:
            issue("brand", "warning", f"Extra brand color {name} ({spec['color']}) covers {share:.0%} of the design; "
                  f"the brand allows at most {spec['max_fraction']:.0%}", fraction=round(share, 4),
                  max_fraction=spec["max_fraction"])


def check(project, kit, issue):
    from .colors import parse
    from .design_render import resolve_color

    named = [*role_colors(kit).values(), *(spec["color"] for spec in extra_colors(kit).values())]
    # A colour matches the palette by its RGB: a translucent brand colour is still that ink.
    allowed = {parse(c)[:3] for c in named}
    rules = kit.get("colors") or {}
    strict, tolerance = rules.get("strict", False), rules.get("tolerance", 0)
    font_names = {s["name"] for s in font_specs(kit).values() if s.get("name")}
    from .typefaces import slug

    font_names |= {f"{slug(s['family'])}-{s.get('weight', 400)}"
                   for s in font_specs(kit).values() if s.get("family") and not s.get("name")}
    if kit.get("pairing"):
        from .typefaces import get_pairing

        pair = get_pairing(kit["pairing"])
        font_names.update(f"{slug(pair[r]['family'])}-{pair[r]['weight']}" for r in ("heading", "body"))
    font_assets = {project.state.get("fonts", {}).get(n) for n in font_names} - {None}
    all_layers = {layer["id"]: layer for layer in project.state["layers"]}

    def visible(layer):
        while layer:
            if not layer.get("visible", True) or layer.get("opacity", 1) <= 0:
                return False
            layer = all_layers.get(layer.get("parent"))
        return True

    def paints(value):
        if isinstance(value, dict):
            for field, item in value.items():
                if field in (
                    "fill",
                    "stroke",
                    "color",
                    "stroke_color",
                    "background",
                    "start",
                    "end",
                ) and isinstance(item, str):
                    yield field, item
                elif isinstance(item, (dict, list)):
                    yield from paints(item)
        elif isinstance(value, list):
            for item in value:
                yield from paints(item)

    def distance(color):
        # Maximum channel difference on the 0–255 scale, as the palette suite rule measures it.
        return round(min((max(abs(a - b) for a, b in zip(color[:3], other[:3])) for other in allowed), default=1) * 255)

    def check_colors(value, layer=None, effect=False):
        if not allowed:
            return
        for field, value in paints(value):
            color = parse(resolve_color(value, project.state))
            if not color[3] or color[:3] in allowed or distance(color) <= tolerance:
                continue
            if effect and color[3] < 1 and len(set(color[:3])) == 1 and color[0] in (0, 1):
                # A translucent black or white shadow or glow darkens or lightens what is under it;
                # it adds no ink of its own.
                continue
            if strict:
                issue("brand", "error", f"{field} {value} is not a brand palette color (nearest is "
                      f"{distance(color)} away; tolerance {tolerance})", [layer] if layer else [],
                      field=field, color=value)
            else:
                issue("brand", "warning", f"{field} is outside the brand palette", [layer] if layer else [],
                      color=value)

    check_colors({"background": project.state["canvas"]["background"]})
    layers = [layer for layer in project.state["layers"] if visible(layer)]
    allowed_fonts = check_fonts(project, kit, issue, layers)
    for layer in layers:
        # Inspect only visual paint fields; provenance/animation metadata is not a color policy input.
        paint_fields = {
            key: layer[key]
            for key in ("fill", "stroke", "color", "stroke_color", "stops", "strokes", "fill_gradient")
            if key in layer
        }
        if layer["type"] == "gradient":
            paint_fields.update({key: layer[key] for key in ("start", "end") if key in layer})
        check_colors(paint_fields, layer)
        check_colors({key: layer[key] for key in ("styles", "effects") if key in layer}, layer, effect=True)
        if (font_names and not allowed_fonts and layer["type"] == "text"
                and layer.get("font") not in font_assets):
            issue("brand", "warning", "Font is outside the brand font pairing", [layer])
    # A required element is a layer name, or an asset resource placed with asset-place (its provenance).
    names = {layer["name"] for layer in layers}
    names |= {(layer.get("provenance") or {}).get("resource") for layer in layers} - {None}
    for name in kit.get("required_elements", []):
        if name not in names:
            issue("brand", "error", f"Required brand element is missing: {name}")
    check_logos(project, kit, issue, visible)
    check_fractions(project, kit, issue)


def placed_logo(layer):
    """True for a layer brand-logo (or an automatic logo) placed."""
    return (layer.get("provenance") or {}).get("type") == "brand-logo"


def finish(project):
    """Keep embedded logo layers visible above generated backgrounds."""
    kit = for_project(project)
    names = {spec["name"] for spec in kit.get("logos", [])}
    layers = project.state["layers"]

    def logo(layer):
        return layer["name"] in names or placed_logo(layer)

    layers[:] = [layer for layer in layers if not logo(layer)] + [layer for layer in layers if logo(layer)]


HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def report(workspace=None, preset=None):
    """``vixl brand validate``: whether brand.json (and each preset) is valid and complete, without changing
    anything. Errors make it unusable or point at missing pieces (a stage naming a font role the brand does
    not define, an embedded font or logo that does not decode); warnings flag gaps (palette roles left to
    derivation, written guidance naming colours the palette does not approve)."""
    from .layouts import ROLES

    errors, warnings = [], []
    if not brand_path(workspace).exists():
        return {"valid": False, "path": "brand.json", "errors": ["No brand.json in the workspace"], "warnings": []}
    try:
        raw = load_raw(workspace)
    except VixlError as exc:
        return {"valid": False, "path": "brand.json", "errors": [str(exc)], "warnings": []}
    checked = {}
    for name in ([None, *(raw.get("presets") or {})] if preset is None else [preset]):
        try:
            kit = resolve(raw, name)
        except VixlError as exc:
            errors.append(str(exc))
            continue
        _report_kit(kit, f"preset {name}: " if name else "", errors, warnings)
        checked[name or "base"] = summary(kit)
    _report_guidance(raw, workspace, warnings)
    missing = [role for role in ROLES if role not in role_colors(raw)]
    if missing:
        warnings.append(f"palette leaves {', '.join(missing)} to derivation; list all seven roles for predictable colors")
    return {"valid": not errors, "path": "brand.json", "errors": list(dict.fromkeys(errors)),
            "warnings": list(dict.fromkeys(warnings)), "brands": checked}


def _report_kit(kit, where, errors, warnings):


    from .fonts import validate_font
    from .type_roles import STAGES

    specs = font_specs(kit)
    roles = {"heading", "body", *specs} if kit.get("pairing") else set(specs)
    for role, spec in specs.items():
        if "data_base64" in spec:
            try:
                validate_font(embedded(spec["data_base64"]))
            except VixlError:
                errors.append(f"{where}fonts.{role} ({spec.get('name')}) is not a readable TrueType/OpenType font")
    if not {"heading", "body"} <= roles:
        warnings.append(f"{where}no font for {' and '.join(sorted({'heading', 'body'} - roles))}; set a pairing or "
                        "fonts.heading/fonts.body")
    for stage, spec in (kit.get("stages") or {}).items():
        role = spec if isinstance(spec, str) else spec.get("font")
        if role and role not in roles and role not in STAGES:
            errors.append(f"{where}stages.{stage} uses font role {role!r}, which fonts does not define")
    allowed = (kit.get("fonts") or {}).get("allowed")
    if allowed:
        families = {family.casefold() for family in allowed}
        for role, spec in specs.items():
            if spec.get("family") and spec["family"].casefold() not in families:
                warnings.append(f"{where}fonts.{role} ({spec['family']}) is not in fonts.allowed; brand fonts are "
                                "allowed anyway")
    logo_names = set()
    for spec in kit.get("logos", []):
        logo_names.add(spec["name"])
        try:
            with open_image(embedded(spec["data_base64"])) as image:
                image.verify()
        except Exception:  # noqa: BLE001 - Any decoder failure means the embedded logo is unusable.
            errors.append(f"{where}logo {spec['name']!r} is not a readable image")
    for name in (kit.get("logo") or {}).get("layers", []):
        if kit.get("logos") and name not in logo_names:
            warnings.append(f"{where}logo.layers names {name!r}, which is not one of the embedded logos")
    if (kit.get("logo") or {}) and not (kit.get("logos") or (kit.get("logo") or {}).get("layers")):
        warnings.append(f"{where}logo rules apply to layers named logo (logo, logo-mark …); embed logos or list "
                        "logo.layers to name them")
    if (kit.get("colors") or {}).get("strict") and not role_colors(kit):
        errors.append(f"{where}colors.strict needs a palette")
    from .model import Limits

    for name, item in (kit.get("elements") or {}).items():
        try:
            element_assets(item, Limits())
        except VixlError as exc:
            errors.append(f"{where}element {name!r}: {exc}")
    approved = {parse_rgb(color) for color in role_colors(kit).values()}
    approved |= {parse_rgb(spec["color"]) for spec in extra_colors(kit).values()}
    for name, style in (kit.get("styles") or {}).items():
        stray = [value for value in dict.fromkeys(HEX.findall(style.get("guidance", "")))
                 if approved and parse_rgb(value) not in approved]
        if stray:
            warnings.append(f"{where}styles.{name} guidance names {', '.join(stray)}, which the palette does not "
                            "approve; add them to palette.extra or correct the guidance")


def parse_rgb(value):
    from .colors import parse

    return parse(value)[:3]


def _report_guidance(raw, workspace, warnings):
    """Written guidance in the workspace resource library that names hex colours the brand does not approve."""
    from .colors import parse
    from .resources import resource_path

    try:
        path = resource_path(workspace)
        library = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
    except (VixlError, ValueError, OSError):
        return
    approved, roles = set(), set()
    for kit in [raw, *(merge(raw, item) for item in (raw.get("presets") or {}).values())]:
        approved |= {parse(c)[:3] for c in role_colors(kit).values()}
        approved |= {parse(spec["color"])[:3] for spec in extra_colors(kit).values()}
        roles |= set(font_specs(kit)) | ({"heading", "body"} if kit.get("pairing") else set())
    _report_template_fonts(library, roles, warnings)
    if not approved:
        return
    for name, text in (library.get("guidance") or {}).items():
        if not isinstance(text, str):
            continue
        stray = [value for value in dict.fromkeys(HEX.findall(text)) if parse(value)[:3] not in approved]
        if stray:
            warnings.append(f"guidance {name!r} names {', '.join(stray)}, which brand.json does not approve; add "
                            "them to palette.extra or correct the guidance")


def _report_template_fonts(library, roles, warnings):
    """Workspace templates whose text names a font role that is neither a text stage nor defined by the brand."""
    from .type_roles import STAGES

    if not roles:
        return
    for name, item in (library.get("templates") or {}).items():
        operations = item.get("operations") if isinstance(item, dict) else None
        named_roles = {op["font"] for op in operations or [] if isinstance(op, dict) and isinstance(op.get("font"), str)
                       and "${" not in op["font"]}
        for role in sorted(named_roles - roles - set(STAGES)):
            warnings.append(f"template {name!r} sets font {role!r}, which is not a text stage or a brand.json font "
                            "role; define it under fonts or use heading, body or a stage")


def summary(kit):
    """What a brand defines, for ``vixl brand show``, ``brand validate`` and the brand board."""
    from types import SimpleNamespace

    from .type_roles import STAGES, stage_table, validate_stages

    view = SimpleNamespace(state={"type_stages": validate_stages(kit["stages"]) if kit.get("stages") else {}})
    table = stage_table(view)
    return {
        "name": kit.get("name"),
        **({"preset": kit["preset"]} if kit.get("preset") else {}),
        "palette": role_colors(kit),
        "extra": {name: spec["color"] for name, spec in extra_colors(kit).items()},
        "fonts": {role: spec.get("name") or spec.get("family") for role, spec in font_specs(kit).items()},
        **({"pairing": kit["pairing"]} if kit.get("pairing") else {}),
        **({"allowed_fonts": kit["fonts"]["allowed"]} if (kit.get("fonts") or {}).get("allowed") else {}),
        "stages": {stage: table[stage]["font"] for stage in STAGES},
        "logos": [spec["name"] for spec in kit.get("logos", [])],
        **({"logo_purposes": {spec["name"]: spec.get("purpose", "icon") for spec in kit["logos"]},
            "auto_logos": [spec["name"] for spec in auto_logos(kit)]} if kit.get("logos") else {}),
        **({"elements": sorted(kit["elements"])} if kit.get("elements") else {}),
        **({"styles": [f"brand:{name}" for name in sorted(kit["styles"])]} if kit.get("styles") else {}),
        "minimum_contrast": kit.get("minimum_contrast", 4.5),
        **({"colors": kit["colors"]} if kit.get("colors") else {}),
        **({"logo": kit["logo"]} if kit.get("logo") else {}),
        **({"required_elements": kit["required_elements"]} if kit.get("required_elements") else {}),
        "presets": sorted(kit.get("presets") or {}),
    }


def cli(args):
    """``vixl brand validate|show|init|pack|install|element … [--workspace DIR]``."""
    from . import brand_pack
    from .commands import Parser

    parser = Parser(prog="vixl brand", description="Check, summarize, start, package and install the workspace "
                    "brand.json")
    parser.add_argument("action", choices=["validate", "show", "init", "pack", "install", "element"])
    parser.add_argument("target", nargs="?", help="pack: the .vixlbrand file to write; install: the package to "
                        "install; element: the element name")
    parser.add_argument("--preset", help="validate/show: a preset name from brand.json presets")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument("--name", help="init: the brand name (default the workspace folder name)")
    parser.add_argument("--pairing", help="init: a font pairing (vixl font pairings)")
    parser.add_argument("--font", action="append", default=[], help="init: ROLE=FILE embeds a TTF/OTF font for a role "
                        "(heading, body or another role name); repeatable")
    parser.add_argument("--palette", help="init: a palette resource whose colours become the seven palette roles")
    parser.add_argument("--mode", choices=["light", "dark"], default="light", help="init: palette roles for a light "
                        "or dark brand")
    parser.add_argument("--preset-only", action="store_true", help="install: add the package's brand to the "
                        "existing brand.json as a preset; resources are left alone")
    parser.add_argument("--as", dest="as_name", help="install --preset-only: the preset name (default from the "
                        "package's brand name)")
    parser.add_argument("--from", dest="source", help="element: the .vixl document in the workspace to take it from")
    parser.add_argument("--object", help="element: the object group in that document (default the whole document)")
    parser.add_argument("--overwrite", action="store_true", help="init/pack/install/element: replace what exists")
    a = parser.parse_args(args)
    if a.action in ("pack", "install", "element"):
        require(a.target, f"vixl brand {a.action} needs " + {"pack": "OUT.vixlbrand", "install": "FILE.vixlbrand",
                                                             "element": "NAME --from FILE.vixl"}[a.action],
                field="target")
    if a.action == "init":
        fonts = []
        for value in a.font:
            role, sep, source = value.partition("=")
            require(sep and role and source, "--font takes ROLE=FILE, e.g. --font heading=Brand-Bold.ttf",
                    field="font")
            fonts.append((role, source))
        return brand_pack.init(a.workspace, name=a.name, pairing=a.pairing, fonts=fonts, palette=a.palette,
                               mode=a.mode, overwrite=a.overwrite)
    if a.action == "pack":
        return brand_pack.pack(a.workspace, a.target, overwrite=a.overwrite)
    if a.action == "install":
        return brand_pack.install(a.workspace, a.target, preset_only=a.preset_only, as_name=a.as_name,
                                  overwrite=a.overwrite)
    if a.action == "element":
        require(a.source, "vixl brand element NAME --from FILE.vixl [--object GROUP]", field="from")
        return brand_pack.add_element(a.workspace, a.target, a.source, ref=a.object, overwrite=a.overwrite)
    if a.action == "validate":
        return report(a.workspace, a.preset)
    kit = load(a.workspace, a.preset)
    require(kit, "No brand.json in the workspace", field="workspace")
    return summary(kit)
