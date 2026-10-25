"""Brand kit <-> Design Profile: map a Design Profile (``schemaVersion: 2``) to brand.json and back.

There is no published Design Profile schema; the mapping follows this shape, and every path it cannot map is
listed in ``unmapped`` (dotted paths), never dropped silently:

- ``name``;
- ``typography``: {role: {family, weight}} -> brand ``fonts`` (camelCase roles become kebab-case);
- ``colours`` (or ``colors``): the seven palette roles (``background``, ``surface``, ``ink``, ``muted``, ``accent``,
  ``accentText``, ``onAccent``); any other colour is a ``palette.extra`` entry;
- ``page.background`` -> palette ``background`` and ``docText.color`` -> palette ``ink`` where they agree with
  ``colours`` (or fill a role it leaves out);
- ``docText``: ``font`` and ``lineHeight`` -> the ``body`` text stage, ``minContrast``/``largeMinContrast`` ->
  ``minimum_contrast``.
"""

from copy import deepcopy
import re

from ...errors import require

SCHEMA_VERSION = 2
TYPOGRAPHY_FIELDS = ("family", "weight")
DOC_TEXT_FIELDS = ("font", "color", "lineHeight", "minContrast", "largeMinContrast")


def is_profile(data):
    """Whether ``data`` is a Design Profile rather than a brand.json."""
    return isinstance(data, dict) and data.get("schemaVersion") == SCHEMA_VERSION


def kebab(name):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name).lower()


def camel(name):
    head, *rest = name.split("-")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _same(a, b):
    from ...colors import parse

    try:
        return parse(a)[:3] == parse(b)[:3]
    except Exception:  # noqa: BLE001 - an unreadable colour is never the same colour; validation reports it.
        return False


def to_brand(profile):
    """(brand.json kit, unmapped paths) for a Design Profile. The kit is validated (``brand.validate``)."""
    from ...brand import validate
    from ...layouts import ROLES

    require(isinstance(profile, dict), "A Design Profile is a JSON object", "invalid_brand")
    require(profile.get("schemaVersion") == SCHEMA_VERSION,
            f"Only Design Profile schemaVersion {SCHEMA_VERSION} is supported", "invalid_brand", field="schemaVersion")
    kit, unmapped = {}, []
    for key, value in profile.items():
        if key == "schemaVersion":
            continue
        if key == "name" and isinstance(value, str):
            kit["name"] = value
        elif key == "typography" and isinstance(value, dict):
            for role, spec in value.items():
                if not isinstance(spec, dict) or not isinstance(spec.get("family"), str):
                    unmapped.append(f"typography.{role}")
                    continue
                kit.setdefault("fonts", {})[kebab(role)] = {"family": spec["family"], "weight": spec.get("weight", 400)}
                unmapped += [f"typography.{role}.{field}" for field in spec if field not in TYPOGRAPHY_FIELDS]
        elif key in ("colours", "colors") and isinstance(value, dict):
            for name, color in value.items():
                if not isinstance(color, str):
                    unmapped.append(f"{key}.{name}")
                    continue
                role = kebab(name)
                palette = kit.setdefault("palette", {})
                if role in ROLES:
                    palette[role] = color
                else:
                    palette.setdefault("extra", {})[role] = color
        elif key not in ("page", "docText"):
            unmapped.append(key)
    palette = kit.get("palette", {})

    def role_from(path, role, color):
        if not isinstance(color, str):
            unmapped.append(path)
        elif role not in palette:
            kit.setdefault("palette", palette)[role] = color
        elif not _same(palette[role], color):
            unmapped.append(path)  # It disagrees with colours: the explicit role wins.

    page = profile.get("page")
    if page is not None:
        if isinstance(page, dict):
            for field, value in page.items():
                if field == "background":
                    role_from("page.background", "background", value)
                else:
                    unmapped.append(f"page.{field}")
        else:
            unmapped.append("page")
    text = profile.get("docText")
    if text is not None:
        if isinstance(text, dict):
            for field in text:
                if field not in DOC_TEXT_FIELDS:
                    unmapped.append(f"docText.{field}")
            if "color" in text:
                role_from("docText.color", "ink", text["color"])
            body = {}
            if isinstance(text.get("font"), str):
                body["font"] = kebab(text["font"])
            if "lineHeight" in text:
                body["line_height"] = text["lineHeight"]
            if body:
                kit["stages"] = {"body": body}
            if "minContrast" in text:
                kit["minimum_contrast"] = text["minContrast"]
                if "largeMinContrast" in text:
                    kit["minimum_contrast"] = {"text": text["minContrast"], "large_text": text["largeMinContrast"]}
            elif "largeMinContrast" in text:
                unmapped.append("docText.largeMinContrast")
        else:
            unmapped.append("docText")
    return validate(kit), unmapped


def from_brand(kit):
    """(Design Profile, unmapped brand.json paths) for a resolved brand kit."""
    from ...brand import extra_colors, font_specs, role_colors

    kit = deepcopy(kit)
    profile, unmapped = {"schemaVersion": SCHEMA_VERSION}, []
    if kit.get("name"):
        profile["name"] = kit["name"]
    typography = {}
    for role, spec in font_specs(kit).items():
        if spec.get("family"):
            typography[camel(role)] = {"family": spec["family"], "weight": spec.get("weight", 400)}
            if spec.get("name"):
                unmapped.append(f"fonts.{role}.name")
        else:
            unmapped.append(f"fonts.{role}")  # An embedded font has no family to name in a profile.
    if (kit.get("fonts") or {}).get("allowed"):
        unmapped.append("fonts.allowed")
    if kit.get("pairing"):
        from ...typefaces import get_pairing

        pairing = get_pairing(kit["pairing"])
        for role in ("heading", "body"):
            typography.setdefault(role, {"family": pairing[role]["family"], "weight": pairing[role]["weight"]})
    if typography:
        profile["typography"] = typography
    colours = {camel(role): color for role, color in role_colors(kit).items()}
    for name, spec in extra_colors(kit).items():
        colours[camel(name)] = spec["color"]
        if "max_fraction" in spec:
            unmapped.append(f"palette.extra.{name}.max_fraction")
    if colours:
        profile["colours"] = colours
    text = {}
    stages = kit.get("stages") or {}
    for stage, spec in stages.items():
        spec = {"font": spec} if isinstance(spec, str) else spec
        if stage != "body":
            unmapped.append(f"stages.{stage}")
            continue
        if "font" in spec:
            text["font"] = camel(spec["font"])
        if "line_height" in spec and isinstance(spec["line_height"], (int, float)):
            text["lineHeight"] = spec["line_height"]
        for field in spec:
            if field != "font" and not (field == "line_height" and "lineHeight" in text):
                unmapped.append(f"stages.body.{field}")
    if "minimum_contrast" in kit:
        floor = kit["minimum_contrast"]
        if isinstance(floor, dict):
            text["minContrast"] = floor["text"]
            if "large_text" in floor:
                text["largeMinContrast"] = floor["large_text"]
            unmapped += [f"minimum_contrast.{field}" for field in floor if field not in ("text", "large_text")]
        else:
            text["minContrast"] = floor
    if text:
        profile["docText"] = text
    for field in ("logos", "required_elements", "colors", "logo", "facts", "words", "placeholders", "suites",
                  "elements", "styles", "presets", "preset"):
        if kit.get(field):
            unmapped.append(field)
    return profile, unmapped


def load_brand_or_profile(data):
    """(validated brand.json kit, unmapped paths) for ``data``: a Design Profile (``schemaVersion: 2``) or a
    brand.json object. The core ``vixl.brand.load_brand_or_profile`` reaches it through the ``brand-format`` hook."""
    from ...brand import validate

    if is_profile(data):
        return to_brand(data)
    return validate(deepcopy(data)), []


def brand_format(data):
    """The ``brand-format`` hook: a Design Profile as (kit, unmapped), or None for any other shape."""
    return to_brand(data) if is_profile(data) else None
