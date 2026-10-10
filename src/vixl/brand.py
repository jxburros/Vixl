"""Workspace brand policy. JSON contains data only; embedded assets never read server paths."""

from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path

from .assets import read_bounded
from .errors import VixlError, require


def load(workspace=None):
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
        require(
            set(kit)
            <= {"name", "palette", "pairing", "fonts", "logos", "minimum_contrast", "required_elements"} | POLICY_FIELDS,
            "Unknown brand.json field",
        )
        validate_policy(kit)
        from .layouts import ROLES
        from .colors import parse

        palette = kit.get("palette", {})
        require(
            isinstance(palette, dict) and set(palette) <= set(ROLES),
            "Brand palette maps layout roles to colors",
        )
        for value in palette.values():
            parse(value)
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
        require(
            isinstance(fonts, dict) and set(fonts) <= {"heading", "body"},
            "Brand fonts must map heading/body roles to embedded font specifications",
        )
        for spec in fonts.values():
            require(
                isinstance(spec, dict)
                and isinstance(spec.get("name"), str)
                and isinstance(spec.get("data_base64"), str),
                "Each brand font needs name and data_base64",
            )
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
        if "pairing" in kit:
            from .typefaces import get_pairing

            get_pairing(kit["pairing"])
        return kit
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", f"Invalid brand.json: {exc}") from exc


def for_project(project):
    return load(getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None))


def embedded(value):
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_brand", "Invalid embedded brand asset") from exc


def prepare(project, operation):
    """Apply defaults inside Project.apply's copy-on-write candidate."""
    kit = for_project(project)
    if not kit:
        return operation
    from .operations import execute

    op = deepcopy(operation)
    palette = kit.get("palette", {})
    project.state.setdefault("swatches", {}).update(palette)
    register_fonts(project, kit, skip={role for role, field in ROLE_FIELDS.items() if field in op})
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
    if op["type"] == "layout-apply" and "palette" not in op:
        if palette:
            op["palette"] = list(palette.values()) if len(palette) > 1 else [*palette.values(), "#ffffff"]
            op["colors"] = {**palette, **op.get("colors", {})}
    return op


ROLE_FIELDS = {"heading": "display_font", "body": "font"}


def register_fonts(project, kit, skip=()):
    """Embed and register the kit's heading/body fonts as the document typography.

    An embedded ``fonts`` entry wins for its role; the ``pairing`` supplies any role it leaves
    open. Returns ``{role: {name, from}}`` for the roles it set."""
    from .fonts import validate_font
    from .operations import execute

    applied, pair = {}, None
    for role in ("heading", "body"):
        if role in skip:
            continue
        spec = kit.get("fonts", {}).get(role)
        if spec:
            data = embedded(spec["data_base64"])
            validate_font(data)
            asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
            project.assets[asset] = data
            execute(project, {"type": "font-register", "name": spec["name"], "asset": asset, "role": role})
            applied[role] = {"name": spec["name"], "from": "fonts"}
        elif kit.get("pairing"):
            from .typefaces import fetch_font, get_pairing, slug

            pair = pair or get_pairing(kit["pairing"])
            family, weight = pair[role]["family"], pair[role]["weight"]
            name = f"{slug(family)}-{weight}"
            if name not in project.state.get("fonts", {}):
                data, _ = fetch_font(family, weight)
                asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
                project.assets[asset] = data
                execute(project, {"type": "font-register", "name": name, "asset": asset, "role": role})
            else:
                execute(project, {"type": "font-register", "name": name, "role": role})
            applied[role] = {"name": name, "from": "pairing", "family": family, "weight": weight}
    return applied


def apply_workspace_fonts(project, workspace=None):
    """Give a new document the workspace's default typography (``brand.json`` pairing/fonts).

    Fonts are embedded, so the document stays portable. Returns a report for the creation result,
    or None when the workspace sets no default fonts. A failed download leaves the document as it
    was and is reported under ``error`` rather than failing the creation."""
    kit = load(workspace) if workspace is not None else for_project(project)
    if not (kit.get("pairing") or kit.get("fonts")):
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
    path = brand_path(workspace)
    load(workspace)  # refuse to rewrite an invalid brand.json
    raw = json.loads(read_bounded(path, 16 * 1024 * 1024)) if path.exists() else {}
    replaced = []
    if pairing is not None:
        raw["pairing"] = pairing
        replaced = [f"fonts.{r}" for r in raw.pop("fonts", {})]
    else:
        require(role in ROLE_FIELDS, "scope workspace needs role heading or body", field="role")
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


def check(project, kit, issue):
    from .colors import parse
    from .design_render import resolve_color

    allowed = {parse(c) for c in kit.get("palette", {}).values()}
    font_names = {s["name"] for s in kit.get("fonts", {}).values()}
    if kit.get("pairing"):
        from .typefaces import get_pairing, slug

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

    def check_colors(value, layer=None):
        if not allowed:
            return
        for field, value in paints(value):
            color = parse(resolve_color(value, project.state))
            if color[3] and color not in allowed:
                issue("brand", "warning", f"{field} is outside the brand palette", [layer] if layer else [])

    check_colors({"background": project.state["canvas"]["background"]})
    layers = [layer for layer in project.state["layers"] if visible(layer)]
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
        if font_names and layer["type"] == "text" and layer.get("font") not in font_assets:
            issue("brand", "warning", "Font is outside the brand font pairing", [layer])
    names = {layer["name"] for layer in layers}
    for name in kit.get("required_elements", []):
        if name not in names:
            issue("brand", "error", f"Required brand element is missing: {name}")


def finish(project):
    """Keep embedded logo layers visible above generated backgrounds."""
    kit = for_project(project)
    names = {spec["name"] for spec in kit.get("logos", [])}
    layers = project.state["layers"]
    layers[:] = [layer for layer in layers if layer["name"] not in names] + [
        layer for layer in layers if layer["name"] in names
    ]
