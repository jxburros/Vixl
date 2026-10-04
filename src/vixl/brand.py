"""Workspace brand policy. JSON contains data only; embedded assets never read server paths."""

from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path

from .assets import read_bounded
from .errors import VixlError, require


def load(workspace=None):
    path = Path(workspace or Path.cwd()) / "brand.json"
    require(
        path.resolve().is_relative_to(path.parent.resolve()),
        "brand.json must stay inside the workspace",
        "forbidden",
    )
    if not path.exists():
        return {}
    try:
        kit = json.loads(read_bounded(path, 16 * 1024 * 1024))
        require(isinstance(kit, dict), "brand.json must be an object")
        require(
            set(kit)
            <= {"name", "palette", "pairing", "fonts", "logos", "minimum_contrast", "required_elements"},
            "Unknown brand.json field",
        )
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
    from .fonts import validate_font

    op = deepcopy(operation)
    palette = kit.get("palette", {})
    project.state.setdefault("swatches", {}).update(palette)
    if kit.get("pairing") and not kit.get("fonts"):
        from .typefaces import fetch_font, get_pairing, slug

        pair = get_pairing(kit["pairing"])
        for role in ("heading", "body"):
            if ("display_font" if role == "heading" else "font") in op:
                continue
            spec = pair[role]
            name = f"{slug(spec['family'])}-{spec['weight']}"
            if name not in project.state.get("fonts", {}):
                data, _ = fetch_font(spec["family"], spec["weight"])
                asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
                project.assets[asset] = data
                execute(project, {"type": "font-register", "name": name, "asset": asset, "role": role})
            else:
                execute(project, {"type": "font-register", "name": name, "role": role})
    for role, spec in kit.get("fonts", {}).items():
        if ("display_font" if role == "heading" else "font") in op:
            continue
        data = embedded(spec["data_base64"])
        validate_font(data)
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[asset] = data
        execute(project, {"type": "font-register", "name": spec["name"], "asset": asset, "role": role})
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
