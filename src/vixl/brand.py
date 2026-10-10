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

from .assets import read_bounded
from .errors import VixlError, require

FIELDS = ("name", "palette", "pairing", "fonts", "logos", "minimum_contrast", "required_elements", "stages",
          "colors", "logo", "presets")
# Fields a preset may override; ``extends`` names the preset it builds on.
PRESET_FIELDS = tuple(field for field in FIELDS if field != "presets") + ("extends",)
# Dict fields merge key by key when a preset overrides them; every other field is replaced.
MERGED = ("palette", "fonts", "stages", "colors", "logo")
LENGTH = re.compile(r"^(\d+(?:\.\d+)?)\s*(px|mm|cm|in|pt)?$")
UNIT_INCHES = {"mm": 1 / 25.4, "cm": 1 / 2.54, "in": 1, "pt": 1 / 72}
LOGO_NAME = re.compile(r"(^|[-_ /])logo([-_ /]|$)", re.IGNORECASE)


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


def validate(kit):
    try:
        require(isinstance(kit, dict), "brand.json must be an object")
        kit = _validate(kit)
        for name, preset in (kit.get("presets") or {}).items():
            resolve(kit, name)
        return kit
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", f"Invalid brand.json: {exc}") from exc


def _validate(kit, preset=False):
    from .colors import parse
    from .layouts import ROLES
    from .type_roles import role_name, validate_stages

    require(isinstance(kit, dict), "brand.json must be an object")
    unknown = sorted(set(kit) - set(FIELDS) - ({"preset"} if preset else set()))
    require(not unknown, f"Unknown brand.json field {', '.join(unknown)}; fields: {', '.join(FIELDS)}")
    palette = kit.get("palette", {})
    require(
        isinstance(palette, dict) and set(palette) <= {*ROLES, "extra"},
        "Brand palette maps layout roles to colors (plus extra: approved colors without a role)",
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
    contrast = kit.get("minimum_contrast", 4.5)
    require(
        isinstance(contrast, (int, float)) and 1 <= contrast <= 21, "Brand minimum_contrast must be 1–21"
    )
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
        require(
            isinstance(spec, dict)
            and isinstance(spec.get("name"), str)
            and isinstance(spec.get("data_base64"), str),
            "Each brand logo needs name and data_base64",
        )
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
    return kit


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


def install_kit(project, kit, skip=()):
    """Swatches, fonts, stages and logos of ``kit`` into the document (inside an apply's candidate)."""
    from .operations import execute

    palette = role_colors(kit)
    swatches = project.state.setdefault("swatches", {})
    swatches.update(palette)
    swatches.update({name: spec["color"] for name, spec in extra_colors(kit).items()})
    register_fonts(project, kit, skip=skip)
    for spec in kit.get("logos", []):
        if any(layer["name"] == spec["name"] for layer in project.state["layers"]):
            continue
        from .assets import add_encoded

        asset, _ = add_encoded(project, embedded(spec["data_base64"]))
        execute(
            project,
            {
                "type": "add",
                "name": spec["name"],
                "asset": asset,
                **{k: spec[k] for k in ("x", "y", "width", "height") if k in spec},
            },
        )


def prepare(project, operation):
    """Apply defaults inside Project.apply's copy-on-write candidate."""
    kit = for_project(project)
    if not kit:
        return operation
    op = deepcopy(operation)
    palette = role_colors(kit)
    install_kit(project, kit, skip={role for role, field in ROLE_FIELDS.items() if field in op})
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
        report["hint"] = "Run vixl_font_pair (or vixl font pair) once the font cache or network is available"
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
    tmp = path.with_name(".brand.json.tmp")
    try:
        tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"path": "brand.json", "scope": "workspace", **({"pairing": pairing} if pairing else {"role": role, "name": name}),
            **({"replaced": replaced} if replaced else {}),
            "note": "New documents in this workspace get these fonts embedded at creation; existing documents are unchanged."}


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
    """The family name stored in a font file (``DejaVu Sans`` for the proofing fallback), or None."""
    from .text import face, primary_font_data

    try:
        names = face(primary_font_data(project, {"font": font, "text": "x"}))[0]["name"]
    except Exception:  # An unreadable font has no family to compare; the fonts check reports it.
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
    found = [layer for layer in layers if layer["name"] in names]
    if not names:
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
            except Exception:  # brand validate reports an unreadable embedded font
                pass
    seen = {}
    for layer in layers:
        if layer["type"] != "text":
            continue
        fonts = [layer.get("font", "DejaVuSans.ttf")]
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
    allowed = {parse(c) for c in named}
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

    def check_colors(value, layer=None):
        if not allowed:
            return
        for field, value in paints(value):
            color = parse(resolve_color(value, project.state))
            if color[3] and color not in allowed and distance(color) > tolerance:
                if strict:
                    issue("brand", "error", f"{field} {value} is not a brand palette color (nearest is "
                          f"{distance(color)} away; tolerance {tolerance})", [layer] if layer else [],
                          field=field, color=value)
                else:
                    issue("brand", "warning", f"{field} is outside the brand palette", [layer] if layer else [])

    check_colors({"background": project.state["canvas"]["background"]})
    layers = [layer for layer in project.state["layers"] if visible(layer)]
    allowed_fonts = check_fonts(project, kit, issue, layers)
    for layer in layers:
        # Inspect only visual paint fields; provenance/animation metadata is not a color policy input.
        paint_fields = {
            key: layer[key]
            for key in ("fill", "stroke", "color", "stroke_color", "styles", "effects", "stops", "strokes")
            if key in layer
        }
        if layer["type"] == "gradient":
            paint_fields.update({key: layer[key] for key in ("start", "end") if key in layer})
        check_colors(paint_fields, layer)
        if (font_names and not allowed_fonts and layer["type"] == "text"
                and layer.get("font") not in font_assets):
            issue("brand", "warning", "Font is outside the brand font pairing", [layer])
    names = {layer["name"] for layer in layers}
    for name in kit.get("required_elements", []):
        if name not in names:
            issue("brand", "error", f"Required brand element is missing: {name}")
    check_logos(project, kit, issue, visible)
    check_fractions(project, kit, issue)


def finish(project):
    """Keep embedded logo layers visible above generated backgrounds."""
    kit = for_project(project)
    names = {spec["name"] for spec in kit.get("logos", [])}
    layers = project.state["layers"]
    layers[:] = [layer for layer in layers if layer["name"] not in names] + [
        layer for layer in layers if layer["name"] in names
    ]


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
    import io

    from PIL import Image

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
            with Image.open(io.BytesIO(embedded(spec["data_base64"]))) as image:
                image.verify()
        except Exception:  # Any decoder failure means the embedded logo is unusable.
            errors.append(f"{where}logo {spec['name']!r} is not a readable image")
    for name in (kit.get("logo") or {}).get("layers", []):
        if kit.get("logos") and name not in logo_names:
            warnings.append(f"{where}logo.layers names {name!r}, which is not one of the embedded logos")
    if (kit.get("logo") or {}) and not (kit.get("logos") or (kit.get("logo") or {}).get("layers")):
        warnings.append(f"{where}logo rules apply to layers named logo (logo, logo-mark …); embed logos or list "
                        "logo.layers to name them")
    if (kit.get("colors") or {}).get("strict") and not role_colors(kit):
        errors.append(f"{where}colors.strict needs a palette")


def _report_guidance(raw, workspace, warnings):
    """Written guidance in the workspace resource library that names hex colours the brand does not approve."""
    from .colors import parse
    from .resources import resource_path

    try:
        path = resource_path(workspace)
        library = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
    except (VixlError, ValueError, OSError):
        return
    approved = set()
    for kit in [raw, *(merge(raw, item) for item in (raw.get("presets") or {}).values())]:
        approved |= {parse(c)[:3] for c in role_colors(kit).values()}
        approved |= {parse(spec["color"])[:3] for spec in extra_colors(kit).values()}
    if not approved:
        return
    for name, text in (library.get("guidance") or {}).items():
        if not isinstance(text, str):
            continue
        stray = [value for value in dict.fromkeys(HEX.findall(text)) if parse(value)[:3] not in approved]
        if stray:
            warnings.append(f"guidance {name!r} names {', '.join(stray)}, which brand.json does not approve; add "
                            "them to palette.extra or correct the guidance")


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
        "minimum_contrast": kit.get("minimum_contrast", 4.5),
        **({"colors": kit["colors"]} if kit.get("colors") else {}),
        **({"logo": kit["logo"]} if kit.get("logo") else {}),
        **({"required_elements": kit["required_elements"]} if kit.get("required_elements") else {}),
        "presets": sorted(kit.get("presets") or {}),
    }


def cli(args):
    """``vixl brand validate|show [--preset NAME] [--workspace DIR]``."""
    from .commands import Parser

    parser = Parser(prog="vixl brand", description="Check and summarize the workspace brand.json")
    parser.add_argument("action", choices=["validate", "show"])
    parser.add_argument("--preset", help="A preset name from brand.json presets")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    a = parser.parse_args(args)
    if a.action == "validate":
        return report(a.workspace, a.preset)
    kit = load(a.workspace, a.preset)
    require(kit, "No brand.json in the workspace", field="workspace")
    return summary(kit)
