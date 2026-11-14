"""The ``guides-import`` and ``guide-set-save`` workflow actions.

``guides-import`` reads a printer's template (a PNG or other image, or a PSD) and writes its lines into the open
document as role guides: the caller maps each line colour to a role, and for a PSD may also name guide layers and
take the ruler guides. ``guide-set-save`` saves a document's role guides as a reusable guide set.
"""

from pathlib import Path

from ...errors import VixlError, require
from ...guides import REGION_ROLES, ROLES, rect_path
from . import detect
from .guide_sets import FITS, KIND, scale_for, scaled, validate

PATH = {"type": "string", "description": "Workspace-relative path."}
ACTIONS = {
    "guides-import": ({"source", "colors", "layers", "ruler_guides", "tolerance", "gap", "min_length",
                       "max_thickness", "fit", "name", "replace", "save", "description", "dry_run"}, {"source"}),
    "guide-set-save": ({"name", "guides", "description"}, {"name"}),
}
SUMMARIES = {
    "guides-import": "Read a printer's template (PNG or PSD) into role guides: safe areas, keep-outs, folds, trim.",
    "guide-set-save": "Save the document's role guides as a reusable guide set (a guide-sets resource).",
}
ROLE = {"type": "string", "enum": list(ROLES)}
FIELD_TYPES = {
    "guides-import": {
        "source": {**PATH, "description": "The template: a PNG, JPEG, WEBP or TIFF image, or a PSD (8-bit RGB)."},
        "colors": {"type": "object", "additionalProperties": ROLE,
                   "description": "Line colour to role, e.g. {\"#00ff00\": \"safe\", \"#ff0000\": \"keep-out\", "
                   "\"#0000ff\": \"fold\", \"#ff00ff\": \"trim\"}. Dashed or solid horizontal and vertical lines of "
                   "that colour are read; lines that close an outline become one closed guide. Leave colors, layers "
                   "and ruler_guides out to list the colours and layers the template has, changing nothing."},
        "layers": {"type": "object", "additionalProperties": ROLE,
                   "description": "PSD only: layer name to role, e.g. {\"Safe Area\": \"safe\"}. Whatever the layer "
                   "draws (any colour) is read as lines."},
        "ruler_guides": {"type": "string", "enum": ["fold", "trim", "bleed", "plain"],
                         "description": "PSD only: also take the file's ruler guides, as axis guides with this role "
                         "(plain: no role)."},
        "tolerance": {"type": "integer", "minimum": 0, "maximum": 128, "default": 40,
                      "description": "How far a pixel's red, green or blue may be from the colour (0-255)."},
        "gap": {"type": "integer", "minimum": 0, "maximum": 512,
                "description": "The widest dash gap bridged, in template pixels (default: 1% of the longer side, "
                "6 to 40)."},
        "min_length": {"type": "integer", "minimum": 2, "maximum": 16384,
                       "description": "The shortest line read, in template pixels (default: three gaps, at least 16)."},
        "max_thickness": {"type": "integer", "minimum": 1, "maximum": 512,
                          "description": "Anything thicker is not a line: lettering or a patch in the line colour "
                          "(default: 0.6% of the longer side, at least 6)."},
        "fit": {"type": "string", "enum": list(FITS), "default": "scale",
                "description": "How template pixels map to the canvas: scale (same proportions, any size), stretch "
                "(each axis on its own) or none (pixel for pixel)."},
        "name": {"type": "string", "description": "Prefix for the guide names (NAME-safe-1); default: role-number "
                 "(safe-1, fold-2), numbered left to right, then top to bottom."},
        "replace": {"type": "boolean", "default": False,
                    "description": "Remove the document's existing role guides first."},
        "save": {"type": "string", "description": "Also save the guides as a guide set with this name, to apply to "
                 "other documents with the guide-set operation."},
        "description": {"type": "string", "description": "With save: what the set is (the printer and product)."},
        "dry_run": {"type": "boolean", "default": False, "description": "Report the guides without changing the "
                    "document or saving a set."},
    },
    "guide-set-save": {
        "name": {"type": "string", "description": "The guide set's name."},
        "guides": {"type": "array", "items": {"type": "string"},
                   "description": "Guide names to save (default: every guide that carries a role)."},
        "description": {"type": "string", "description": "What the set is (the printer and product)."},
    },
}


def _roles(mapping, field):
    require(isinstance(mapping, dict) and mapping and all(isinstance(key, str) for key in mapping),
            f"{field} maps names to roles, e.g. {{...: 'safe'}}", field=field)
    for role in mapping.values():
        require(role in ROLES, f"Unknown role {role!r} in {field}; roles: {', '.join(ROLES)}", field=field,
                allowed=list(ROLES))
    return mapping


def _number(request, field, default):
    spec = FIELD_TYPES["guides-import"][field]
    value = request.get(field, default)
    require(isinstance(value, int) and not isinstance(value, bool) and spec["minimum"] <= value <= spec["maximum"],
            f"{field} is a whole number from {spec['minimum']} to {spec['maximum']}", field=field)
    return value


def read_template(session, source):
    """``(path, bytes, is_psd)`` of a template file, read within the session's limits."""
    from ...assets import read_bounded

    require(isinstance(source, str) and source, "source is a workspace-relative path to the template", field="source")
    path = session.resolve(source)
    require(path.is_file(), f"Template not found: {source}", "not_found", field="source")
    limits = session.limits
    if path.suffix.lower() in (".psd", ".psb"):
        return path, read_bounded(path, limits.max_project_bytes), True
    return path, read_bounded(path, limits.max_asset_bytes), False


def find(pixels, mapping, options, masks=None):
    """Guides in template pixels for a colour → role mapping (and layer masks → role): ``(guides, warnings)`` where
    guides is a list of ``(role, guide, (left, top))``."""
    from ...render import color

    height, width = pixels.shape[:2]
    longer = max(width, height)
    gap = _number(options, "gap", max(6, min(40, round(longer * 0.01))))
    minimum = _number(options, "min_length", max(16, 3 * gap))
    explicit = "min_length" in options
    thickness = _number(options, "max_thickness", max(6, round(longer * 0.006)))
    tolerance = _number(options, "tolerance", 40)
    sources = []
    for name, role in (mapping or {}).items():
        rgba = color(name)
        sources.append((name, role, detect.color_mask(pixels, rgba[:3], tolerance)))
    for name, (role, mask) in (masks or {}).items():
        sources.append((f"layer {name!r}", role, mask))
    found, warnings, ignored = [], [], 0
    # A line that closes no outline is a fold or an edge, and those are long; short strays are the tops of
    # lettering in the line colour.
    open_minimum = minimum if explicit else max(3 * minimum, round(0.08 * longer))
    for label, role, mask in sources:
        horizontal, vertical = detect.lines(mask, gap, minimum, thickness)
        closed, loose = detect.outlines(horizontal, vertical, gap + thickness, minimum)
        if not closed and not any(end - start >= open_minimum for _, _, start, end in loose):
            warnings.append(f"No lines found for {label} ({role}): check the colour (leave colors out to list the "
                            "template's colours), raise tolerance, or lower min_length")
        for polygon in closed:
            d = " ".join(f"{'M' if i == 0 else 'L'} {x} {y}" for i, (x, y) in enumerate(polygon)) + " Z"
            xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
            if len(polygon) == 4:
                d = rect_path(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            found.append((role, {"kind": "path", "d": d, "role": role}, (min(xs), min(ys))))
        for kind, at, start, end in loose:
            if end - start < open_minimum:
                ignored += 1
                continue
            full = end - start >= 0.9 * (width if kind == "h" else height)
            if full:
                guide = {"axis": "y" if kind == "h" else "x", "position": at}
            else:
                guide = {"kind": "segment",
                         "points": [[start, at], [end, at]] if kind == "h" else [[at, start], [at, end]]}
            if role in REGION_ROLES:
                warnings.append(f"A {role} line for {label} at {'y' if kind == 'h' else 'x'} {at} does not close an "
                                f"outline, so it is kept as a plain guide: a {role} guide is an area. Raise gap if "
                                "its corners are open, or draw the area with guide rect")
            else:
                guide["role"] = role
            found.append((role, guide, (start, at) if kind == "h" else (at, start)))
    if ignored:
        warnings.append(f"{ignored} short stray line(s) under {open_minimum} px that close no outline were left out "
                        "(lettering in a line colour reads like that); pass min_length to keep shorter open lines")
    return found, warnings


def named_guides(found, sx, sy, prefix):
    """{name: guide} on the canvas: numbered per role, left to right and then top to bottom."""
    guides, counters = {}, {}
    for role, guide, _ in sorted(found, key=lambda item: (item[0], item[2])):
        counters[role] = counters.get(role, 0) + 1
        plain = "role" not in guide and role is not None
        name = f"{role or 'guide'}{'-line' if plain else ''}-{counters[role]}"
        guides[f"{prefix}-{name}" if prefix else name] = scaled(guide, sx, sy)
    return guides


def guides_import(session, request, document=None):
    from ...assets import decode
    from ...design import named

    for field in ("colors", "layers"):
        if request.get(field) is not None:
            _roles(request[field], field)
    ruler = request.get("ruler_guides")
    require(ruler in (None, "fold", "trim", "bleed", "plain"), "ruler_guides is fold, trim, bleed or plain",
            field="ruler_guides")
    for field in ("name", "save"):
        if request.get(field) is not None:
            named(request[field])
    fit = request.get("fit", "scale")
    require(fit in FITS, f"fit must be one of {', '.join(FITS)}", field="fit", allowed=list(FITS))
    path, data, psd = read_template(session, request["source"])
    layers, ruler_lines, layer_names = {}, [], []
    if psd:
        from .psd_guides import read

        template = read(data, session.limits, list(request.get("layers") or {}))
        pixels, ruler_lines, layer_names = template["image"], template["guides"], template["layer_names"]
        by_name = {name.casefold(): mask for name, mask in template["layers"].items()}
        for name, role in (request.get("layers") or {}).items():
            require(name.casefold() in by_name, f"The PSD has no layer {name!r} with pixels; layers: "
                    f"{', '.join(repr(n) for n in layer_names[:40]) or 'none'}", "not_found", field="layers")
            layers[name] = (role, by_name[name.casefold()])
    else:
        require(not request.get("layers") and not ruler, "layers and ruler_guides read a PSD; an image template "
                "takes colors", field="layers" if request.get("layers") else "ruler_guides")
        import numpy as np

        pixels = np.asarray(decode(data, session.limits, "RGBA"))
    height, width = pixels.shape[:2]
    result = {"source": session.relative(path), "size": [width, height]}
    if not request.get("colors") and not layers and not ruler:
        # Nothing mapped yet: say what the template offers.
        result.update(colors_found=detect.line_colors(pixels), applied=False,
                      next="Map the line colours to roles: colors: {'#rrggbb': 'safe' | 'keep-out' | 'fold' | "
                           "'trim' | 'bleed'}")
        if psd:
            result.update(layers_found=layer_names, ruler_guides_found=len(ruler_lines))
        return result
    found, warnings = find(pixels, request.get("colors"), request, layers)
    for axis, position in ruler_lines if ruler else ():
        guide = {"axis": axis, "position": round(position)}
        role = None if ruler == "plain" else ruler
        if role:
            guide["role"] = role
        found.append((role or "ruler", guide, (guide["position"], 0) if axis == "x" else (0, guide["position"])))
    require(found, "No guide lines were found in the template. " + " ".join(warnings), "not_found", field="colors")
    dry = bool(request.get("dry_run"))
    with session.project(write=not dry, document=document) as project:
        canvas = project.state["canvas"]
        sx, sy = scale_for((width, height), canvas, fit, "The template")
        guides = named_guides(found, sx, sy, request.get("name"))
        if not dry:
            operations = [{"type": "guide", "name": name, "delete": True}
                          for name, guide in project.state.get("guides", {}).items()
                          if request.get("replace") and guide.get("role") in ROLES and name not in guides]
            operations += [{"type": "guide", "name": name, **_operation(guide)} for name, guide in guides.items()]
            project.apply(operations)
        size = [canvas["width"], canvas["height"]]
    counts = {}
    for guide in guides.values():
        counts[guide.get("role", "plain")] = counts.get(guide.get("role", "plain"), 0) + 1
    result.update(canvas=size, scale=[round(sx, 6), round(sy, 6)], guides=guides, counts=counts, applied=not dry)
    if warnings:
        result["warnings"] = warnings
    if request.get("save"):
        value = {"width": size[0], "height": size[1], "guides": guides,
                 "description": request.get("description") or f"Guides from {Path(request['source']).name}",
                 "source": Path(request["source"]).name}
        validate(value)
        if not dry:
            from ...resources import register

            register(KIND, request["save"], value, workspace=session.workspace)
            result["saved"] = {"kind": KIND, "name": request["save"]}
    result["next"] = ("vixl_check(checks=['safe_area']) reports ink outside a safe guide, inside a keep-out and text "
                      "crossing a fold; vixl_render(guides=true) shows the guides")
    return result


def _operation(guide):
    """The ``guide`` operation fields that recreate a guide record."""
    return {key: value for key, value in guide.items() if key not in ("grid", "generated")}


def guide_set_save(session, request, document=None):
    from ...design import named
    from ...resources import register

    name = named(request["name"])
    wanted = request.get("guides")
    require(wanted is None or (isinstance(wanted, list) and wanted and all(isinstance(n, str) for n in wanted)),
            "guides is a list of guide names", field="guides")
    with session.project(document=document) as project:
        current = project.state.get("guides", {})
        if wanted is None:
            chosen = {key: guide for key, guide in current.items() if guide.get("role") in ROLES}
            require(chosen, "The document has no guides with a role; give a guide a role (guide … role: safe), "
                    "import a template with guides-import, or name the guides to save", "not_found", field="guides")
        else:
            missing = [key for key in wanted if key not in current]
            require(not missing, f"Unknown guide(s): {', '.join(missing)}", "not_found", field="guides",
                    allowed=sorted(current))
            chosen = {key: current[key] for key in wanted}
        canvas = project.state["canvas"]
        value = {"width": canvas["width"], "height": canvas["height"],
                 "guides": {key: _operation(guide) for key, guide in chosen.items()}}
    if request.get("description"):
        value["description"] = request["description"]
    register(KIND, name, value, workspace=session.workspace)
    return {"saved": {"kind": KIND, "name": name}, "guides": sorted(value["guides"]),
            "size": [value["width"], value["height"]],
            "apply": f"{{type: guide-set, name: {name!r}}} puts it on another document"}


def dispatch(session, action, request, document=None):
    try:
        if action == "guides-import":
            return guides_import(session, request, document)
        return guide_set_save(session, request, document)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise VixlError("invalid_request", f"Invalid {action} request: {exc!r}",
                        suggestions=[f"See vixl_reference('workflows') actions['{action}'].properties"]) from exc
