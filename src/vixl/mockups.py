"""Device and print mockups: a design shown on a phone, a laptop, in a browser, framed on a wall, as a
business card or on a mug.

A mockup template is a scene (built from ordinary operations, or a workspace ``.vixl`` document) plus one
or more **slots**, each four corner points. The ``mockup`` workflow builds the scene and places the design
into every slot as a live ``link`` layer warped by its ``corner_pin``, clipped to a surface shape, with
optional shading (multiply) and gloss (screen) layers over it. Because the design is linked, editing it
updates every mockup on its next render. The built-in templates below are drawn procedurally, so they are
licence-clean; users add their own to the workspace resource catalog (``mockup-save``).

A mug or any curved surface is a flat slot under cylindrical shading: the design is not bent.
"""

from copy import deepcopy
from pathlib import Path

from .errors import VixlError, require

ACTIONS = {
    "mockup": ({"design", "mockup", "output", "fit", "shade", "gloss", "source_page", "artboard", "export",
                "overwrite"}, {"design", "mockup", "output"}),
    "mockup-list": (set(), set()),
    "mockup-save": ({"name", "value"}, {"name", "value"}),
}
MAX_SLOTS = 8

FIELD_TYPES = {
    "design": {"type": "string", "description": "The design to place: a workspace .vixl document (linked, so edits "
               "to it show in the mockup)."},
    "mockup": {"type": ["string", "array"], "items": {"type": "string"},
               "description": "Template name (mockup-list), or a list of names for one mockup each."},
    "output": {"type": "string", "description": "The mockup document (.vixl); with several mockups, a folder that "
               "receives NAME.vixl per template."},
    "fit": {"type": "string", "enum": ["fill", "fit", "stretch"], "default": "fill",
            "description": "How the design fills each slot: fill crops to cover it, fit shows all of it, stretch distorts."},
    "shade": {"type": "boolean", "default": True, "description": "Add each slot's shading layer (multiply)."},
    "gloss": {"type": "boolean", "default": True, "description": "Add each slot's gloss layer (screen)."},
    "source_page": {"type": ["string", "integer"], "description": "Page of the design to show (default: the first)."},
    "artboard": {"type": "string", "description": "Artboard of the design to show."},
    "export": {"type": "array", "items": {"type": "string"},
               "description": "Image formats to export each mockup to, next to it (png, jpg, webp, pdf …), through "
                              "the export_batch path."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace existing mockup files."},
    "name": {"type": "string", "description": "mockup-save: the template name."},
    "value": {"type": "object", "description": "mockup-save: {description, document (a workspace .vixl) or width, "
              "height, background and operations, slots: [{name, corners: [[x, y] ×4], surface, radius, shade, "
              "gloss}], overlay (operations drawn above the slots)}."},
}
SLOT_KEYS = {"name", "corners", "surface", "radius", "shade", "gloss"}

DARK_SCREEN = "#0b0d12"


def _rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _shadow(name, x, y, w, h, radius, amount=18, opacity=0.35):
    return [{"type": "shape", "shape": "rounded-rectangle", "name": name, "x": x, "y": y, "width": w, "height": h,
             "radius": radius, "fill": "#000000", "opacity": opacity},
            {"type": "blur", "target": name, "amount": amount}]


BUILTINS = {
    "phone": {
        "description": "A phone held upright: dark body and a 9:19.5 screen with rounded corners.",
        "width": 1200, "height": 1600, "background": "#e7eaee",
        "operations": [
            *_shadow("shadow", 362, 300, 520, 1060, 72),
            {"type": "shape", "shape": "rounded-rectangle", "name": "body", "x": 340, "y": 270, "width": 520,
             "height": 1060, "radius": 72, "fill": "#1b1c20"},
        ],
        "slots": [{"name": "screen", "corners": _rect(364, 294, 472, 1012), "radius": 52, "surface": DARK_SCREEN,
                   "shade": False, "gloss": True}],
        "overlay": [{"type": "shape", "shape": "capsule", "name": "camera", "x": 545, "y": 312, "width": 110,
                     "height": 30, "fill": "#05060a"}],
    },
    "laptop": {
        "description": "An open laptop seen from the front: a 16:10 screen in a dark lid on a light base.",
        "width": 1600, "height": 1100, "background": "#eceff3",
        "operations": [
            *_shadow("shadow", 220, 820, 1160, 70, 30, amount=24, opacity=0.3),
            {"type": "shape", "shape": "rounded-rectangle", "name": "lid", "x": 290, "y": 150, "width": 1020,
             "height": 670, "radius": 26, "fill": "#24262b"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "base", "x": 190, "y": 812, "width": 1220,
             "height": 42, "radius": 18, "fill": "#c8ccd2"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "notch", "x": 720, "y": 812, "width": 160,
             "height": 14, "radius": 7, "fill": "#a9aeb6"},
        ],
        "slots": [{"name": "screen", "corners": _rect(320, 180, 960, 600), "radius": 4, "surface": DARK_SCREEN,
                   "shade": False, "gloss": True}],
    },
    "browser": {
        "description": "A desktop browser window: title bar, three window buttons and an address bar over the page.",
        "width": 1600, "height": 1100, "background": "#dde2ea",
        "operations": [
            *_shadow("shadow", 130, 120, 1340, 900, 18, amount=22, opacity=0.25),
            {"type": "shape", "shape": "rounded-rectangle", "name": "window", "x": 120, "y": 100, "width": 1360,
             "height": 900, "radius": 16, "fill": "#ffffff"},
            {"type": "shape", "shape": "rectangle", "name": "title-bar", "x": 120, "y": 116, "width": 1360,
             "height": 56, "fill": "#f1f3f5"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "title-top", "x": 120, "y": 100, "width": 1360,
             "height": 40, "radius": 16, "fill": "#f1f3f5"},
            {"type": "shape", "shape": "ellipse", "name": "close", "x": 150, "y": 128, "width": 18, "height": 18,
             "fill": "#ff5f57"},
            {"type": "shape", "shape": "ellipse", "name": "minimize", "x": 180, "y": 128, "width": 18, "height": 18,
             "fill": "#febc2e"},
            {"type": "shape", "shape": "ellipse", "name": "zoom", "x": 210, "y": 128, "width": 18, "height": 18,
             "fill": "#28c840"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "address-bar", "x": 420, "y": 122, "width": 760,
             "height": 30, "radius": 15, "fill": "#ffffff"},
        ],
        "slots": [{"name": "page", "corners": _rect(120, 172, 1360, 828), "radius": 0, "surface": "#ffffff",
                   "shade": False, "gloss": False}],
    },
    "poster-wall": {
        "description": "A framed portrait poster (about A-series proportions) with a white mat on a plain wall.",
        "width": 1600, "height": 1200, "background": "#ece6dc",
        "operations": [
            *_shadow("shadow", 498, 168, 640, 880, 4, amount=20, opacity=0.3),
            {"type": "shape", "shape": "rectangle", "name": "frame", "x": 480, "y": 140, "width": 640, "height": 880,
             "fill": "#1f1f1f"},
            {"type": "shape", "shape": "rectangle", "name": "mat", "x": 504, "y": 164, "width": 592, "height": 832,
             "fill": "#fbfaf7"},
        ],
        "slots": [{"name": "poster", "corners": _rect(552, 214, 496, 732), "radius": 0, "surface": "#ffffff",
                   "shade": True, "gloss": True}],
    },
    "business-card": {
        "description": "A 3.5 × 2 in business card lying on a desk, seen at an angle (a perspective slot).",
        "width": 1600, "height": 1100, "background": "#b89b7a",
        "operations": [
            {"type": "shape", "shape": "path", "name": "shadow", "x": 0, "y": 0, "width": 1600, "height": 1100,
             "path": "M418 360 L1192 304 L1262 760 L398 832 Z", "fill": "#000000", "opacity": 0.35},
            {"type": "blur", "target": "shadow", "amount": 16},
        ],
        "slots": [{"name": "card", "corners": [[400, 330], [1170, 276], [1236, 724], [380, 798]], "radius": 0,
                   "surface": "#ffffff", "shade": True, "gloss": True}],
    },
    "mug": {
        "description": "A white mug with a handle; the print area is shaded like the curve of the cup (the design "
                       "itself is not bent).",
        "width": 1400, "height": 1200, "background": "#f1ece4",
        "operations": [
            *_shadow("shadow", 390, 900, 560, 70, 35, amount=22, opacity=0.25),
            {"type": "shape", "shape": "ellipse", "name": "handle", "x": 860, "y": 430, "width": 260, "height": 320,
             "fill": "transparent", "stroke": "#f7f7f5", "stroke_width": 46},
            {"type": "shape", "shape": "rounded-rectangle", "name": "body", "x": 380, "y": 300, "width": 560,
             "height": 640, "radius": 40, "fill": "#fbfbf9"},
            {"type": "shape", "shape": "ellipse", "name": "rim", "x": 380, "y": 270, "width": 560, "height": 64,
             "fill": "#e9e7e2"},
        ],
        "slots": [{"name": "print", "corners": _rect(450, 400, 420, 420), "radius": 0, "surface": "#fbfbf9",
                   "shade": True, "gloss": False}],
        "overlay": [{"type": "gradient", "name": "curve", "x": 380, "y": 300, "width": 560, "height": 640,
                     "direction": "horizontal",
                     "stops": [{"offset": 0, "color": "rgba(0,0,0,0.22)"}, {"offset": 0.18, "color": "rgba(0,0,0,0.02)"},
                               {"offset": 0.45, "color": "rgba(255,255,255,0)"},
                               {"offset": 0.82, "color": "rgba(0,0,0,0.04)"}, {"offset": 1, "color": "rgba(0,0,0,0.28)"}]}],
    },
}
def catalog(workspace=None):
    """Every mockup template: the built-ins, then the workspace's own (``mockups`` in its resource library)."""
    from .resources import catalog as resource_catalog

    return {**deepcopy(BUILTINS), **resource_catalog("mockups", workspace=workspace)}


def validate(value):
    """A user template: a workspace document or operations, and 1–8 slots of four corners each."""
    from .schema import validate_operation

    require(isinstance(value, dict), "A mockup template is an object", field="value")
    unknown = sorted(set(value) - {"description", "document", "width", "height", "background", "operations", "slots",
                                   "overlay"})
    require(not unknown, f"Unknown mockup template field(s): {', '.join(unknown)}", field="value")
    if "document" in value:
        require(isinstance(value["document"], str) and value["document"].endswith(".vixl"),
                "document is a workspace .vixl path", field="value.document")
        require("operations" not in value, "Give a document or operations, not both", field="value")
    else:
        from .model import Limits

        require("width" in value and "height" in value, "A template built from operations needs width and height",
                field="value")
        Limits().size(value["width"], value["height"])
    for key in ("operations", "overlay"):
        ops = value.get(key, [])
        require(isinstance(ops, list) and len(ops) <= 500, f"{key} is a list of up to 500 operations", field=f"value.{key}")
        for op in ops:
            validate_operation(op)
            reads = op["type"] in ("link", "template-apply", "font-register", "add", "frame", "drawing") or (
                "path" in op and op["type"] != "shape")
            require(not reads, "Mockup templates draw with operations; they cannot read files", field=f"value.{key}")
    slots = value.get("slots")
    require(isinstance(slots, list) and 1 <= len(slots) <= MAX_SLOTS, f"slots lists 1–{MAX_SLOTS} slots",
            field="value.slots")
    names = []
    for i, slot in enumerate(slots):
        require(isinstance(slot, dict) and set(slot) <= SLOT_KEYS and isinstance(slot.get("name"), str),
                f"slots[{i}] is {{name, corners, surface?, radius?, shade?, gloss?}}", field=f"value.slots[{i}]")
        from .links import corner_pin

        corner_pin(slot.get("corners"))
        names.append(slot["name"])
    require(len(set(names)) == len(names), "Slot names must be unique", field="value.slots")


def slot_operations(slot, design, settings, index_name):
    """The layers one slot adds: the surface it is clipped to, the linked design (corner-pinned), then shading
    and gloss clipped to the surface."""
    corners = slot["corners"]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    w, h = int(max(xs)) + 2 - x0, int(max(ys)) + 2 - y0
    local = [[round(px - x0, 3), round(py - y0, 3)] for px, py in corners]
    name = index_name
    rectangle = (local[0][1] == local[1][1] and local[2][1] == local[3][1] and local[0][0] == local[3][0]
                 and local[1][0] == local[2][0])
    surface = f"{name}-surface"
    if rectangle:
        shape = {"type": "shape", "shape": "rounded-rectangle" if slot.get("radius") else "rectangle", "name": surface,
                 "x": x0 + local[0][0], "y": y0 + local[0][1], "width": local[1][0] - local[0][0],
                 "height": local[3][1] - local[0][1], "fill": slot.get("surface", "#ffffff"),
                 **({"radius": slot["radius"]} if slot.get("radius") else {})}
    else:
        path = "M" + " L".join(f"{px:g} {py:g}" for px, py in local) + " Z"
        shape = {"type": "shape", "shape": "path", "name": surface, "x": x0, "y": y0, "width": w, "height": h,
                 "path": path, "fill": slot.get("surface", "#ffffff")}
    ops = [shape,
           {"type": "link", "name": name, "source": design, "x": x0, "y": y0, "width": w, "height": h,
            "fit": settings["fit"], "corner_pin": local,
            **{k: settings[k] for k in ("source_page", "artboard") if settings.get(k) is not None}},
           {"type": "clip", "target": name, "base": surface}]
    if settings["shade"] and slot.get("shade", True):
        ops += [{"type": "gradient", "name": f"{name}-shade", "x": x0, "y": y0, "width": w, "height": h,
                 "direction": "angled", "angle": 60,
                 "stops": [{"offset": 0, "color": "rgba(255,255,255,0)"}, {"offset": 1, "color": "rgba(0,0,0,0.22)"}]},
                {"type": "blend", "target": f"{name}-shade", "value": "multiply"},
                {"type": "clip", "target": f"{name}-shade", "base": surface}]
    if settings["gloss"] and slot.get("gloss", True):
        ops += [{"type": "gradient", "name": f"{name}-gloss", "x": x0, "y": y0, "width": w, "height": h,
                 "direction": "angled", "angle": 35,
                 "stops": [{"offset": 0, "color": "rgba(255,255,255,0.22)"}, {"offset": 0.45, "color": "rgba(255,255,255,0.06)"},
                           {"offset": 0.46, "color": "rgba(255,255,255,0)"}, {"offset": 1, "color": "rgba(255,255,255,0)"}]},
                {"type": "blend", "target": f"{name}-gloss", "value": "screen"},
                {"type": "clip", "target": f"{name}-gloss", "base": surface}]
    return ops


def build(session, name, spec, design, destination, settings):
    """The mockup document for template ``spec``, linked to ``design`` and saved at ``destination``."""
    from .project import Project

    if "document" in spec:
        source = session.resolve(spec["document"])
        require(source.is_file(), f"Mockup template {name!r}: {spec['document']} not found in the workspace",
                "not_found", field="mockup")
        project = Project.load(source, limits=session.limits)
    else:
        project = Project(spec["width"], spec["height"], spec.get("background", "#ffffff"), limits=session.limits)
    project._workspace = session.workspace
    project.path, project._revision = destination, None
    operations = list(spec.get("operations", [])) if "document" not in spec else []
    taken = {layer["name"] for layer in project.state["layers"]}
    for slot in spec["slots"]:
        slot_name = slot["name"] if slot["name"] not in taken else f"design-{slot['name']}"
        operations += slot_operations(slot, str(design), settings, slot_name)
    operations += list(spec.get("overlay", []))
    project.apply(operations)
    project.state["mockup"] = {"template": name, "design": session.relative(design),
                               "slots": [slot["name"] for slot in spec["slots"]]}
    return project


def dispatch(session, action, request, document=None):
    workspace = session.workspace
    if action == "mockup-list":
        return {"mockups": {name: {"description": spec.get("description", ""),
                                   "slots": [slot["name"] for slot in spec["slots"]],
                                   "size": [spec["width"], spec["height"]] if "width" in spec else None,
                                   "builtin": name in BUILTINS}
                            for name, spec in catalog(workspace).items()}}
    if action == "mockup-save":
        from .resources import register

        validate(request["value"])
        require(request["name"] not in BUILTINS, f"{request['name']!r} is a built-in template; choose another name",
                field="name")
        return register("mockups", request["name"], request["value"], workspace=workspace)
    names = request["mockup"] if isinstance(request["mockup"], list) else [request["mockup"]]
    require(names and all(isinstance(n, str) for n in names) and len(names) <= 16,
            "mockup is a template name or a list of up to 16", field="mockup")
    available = catalog(workspace)
    for item in names:
        if item not in available:
            import difflib

            close = difflib.get_close_matches(item, list(available), 3, 0.5)
            raise VixlError("invalid_request", f"Unknown mockup {item!r}; templates: {', '.join(available)}",
                            field="mockup", allowed=list(available), suggestions=close)
    settings = {"fit": request.get("fit", "fill"), "shade": request.get("shade", True),
                "gloss": request.get("gloss", True), "source_page": request.get("source_page"),
                "artboard": request.get("artboard")}
    require(settings["fit"] in ("fill", "fit", "stretch"), "fit is fill, fit or stretch", field="fit")
    for key in ("shade", "gloss", "overwrite"):
        require(type(request.get(key, True)) is bool, f"{key} must be true or false", field=key)
    design = session.resolve(request["design"])
    require(design.suffix.lower() == ".vixl" and design.is_file(),
            f"design must be a .vixl document in the workspace; {request['design']!r} is not one", field="design")
    output = session.resolve(request["output"])
    if len(names) == 1 and output.suffix.lower() == ".vixl":
        plan = [(names[0], output)]
    else:
        require(output.suffix == "", "With several mockups, output is a folder", field="output")
        plan = [(item, output / f"{item}.vixl") for item in names]
    overwrite = request.get("overwrite", False)
    formats = [f.lower().lstrip(".") for f in request.get("export", [])]
    require(all(f in ("png", "jpg", "jpeg", "webp", "tiff", "avif", "pdf", "svg") for f in formats),
            "export lists image formats: png, jpg, webp, tiff, avif, pdf or svg", field="export")
    for _, destination in plan:
        require(destination != design, "output would overwrite the design", field="output")
        require(overwrite or not destination.exists(), f"{session.relative(destination)} already exists; set "
                "overwrite=true or choose another output", field="output")
    results = []
    for item, destination in plan:
        spec = available[item]
        if item not in BUILTINS:
            validate(spec)
        project = build(session, item, spec, design, destination, settings)
        session.make_parent(destination)
        project.save(destination, overwrite=overwrite)
        results.append({"mockup": item, "path": session.relative(destination),
                        "slots": project.state["mockup"]["slots"]})
    if formats:
        from .export_batch import export_batch
        from .mcp_tools import export_file

        targets = [{"path": session.relative(Path(session.resolve(row["path"])).with_suffix("." + f)),
                    "document": row["path"]} for row in results for f in formats]
        batch = export_batch(session, export_file, targets, overwrite=overwrite)
        for row in results:
            row["exports"] = [item for item in batch["results"] if item.get("document") == row["path"]
                              or item.get("path", "").startswith(row["path"][:-5])]
    return {"design": session.relative(design), "count": len(results), "mockups": results}
