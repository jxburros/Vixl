"""Device and print mockups: a design shown on a phone, a laptop, in a browser, framed on a wall, as a business card,
on a mug, or printed on a tee, hoodie, tote bag, sticker or enamel pin.

A mockup template is a scene (built from ordinary operations, or a workspace ``.vixl`` document) plus **placements**:
``slots`` (four corner points; a screen, a sheet of paper) and named print ``areas`` (four corners and the physical
``print_size_mm``, optionally a ``clip_path``). The ``mockup`` workflow builds the scene and places a design into
each placement as a live ``link`` layer warped by its ``corner_pin``, clipped to a surface shape, with optional
shading (multiply), gloss (screen) and a print ``finish`` (screen, puff, embroidery, enamel, woven) over it. Because
the design is linked, editing it updates every mockup on its next render. A template can name ``base`` layers and a
``garment_color``: the request's ``garment_color`` recolours only those layers, whose shading sits in separate
layers above. The built-in templates are drawn as vector paths (``products.py``), so they are licence-clean;
users add their own to the workspace resource catalog (``mockup-save``).

A mug or any curved surface is a flat slot under cylindrical shading: the design is not bent.
"""

from copy import deepcopy
import math
from pathlib import Path
import re

from ...errors import VixlError, require
from . import finishes, products

ACTIONS = {
    "mockup": ({"design", "mockup", "output", "fit", "shade", "gloss", "source_page", "artboard", "export",
                "overwrite", "place", "finish", "garment_color"}, {"mockup", "output"}),
    "mockup-list": (set(), set()),
    "mockup-save": ({"name", "value"}, {"name", "value"}),
}
MAX_SLOTS = 8
MAX_PLACEMENTS = 12
AREA_NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")
# The standard garment areas; a template may name others.
GARMENT_AREAS = ("front-chest", "full-front", "back", "sleeve-l", "sleeve-r", "hem-tag", "inside-neck")

FIELD_TYPES = {
    "design": {"type": "string", "description": "The design to place: a workspace .vixl document (linked, so edits "
               "to it show in the mockup). It fills every slot, or the template's main area when it has only areas; "
               "use place to name areas."},
    "mockup": {"type": ["string", "array"], "items": {"type": "string"},
               "description": "Template name (mockup-list), or a list of names for one mockup each."},
    "output": {"type": "string", "description": "The mockup document (.vixl); with several mockups, a folder that "
               "receives NAME.vixl per template."},
    "fit": {"type": "string", "enum": ["fill", "fit", "stretch"], "default": "fill",
            "description": "How the design fills each slot or area: fill crops to cover it, fit shows all of it, "
                           "stretch distorts."},
    "shade": {"type": "boolean", "default": True, "description": "Add each slot's shading layer (multiply)."},
    "gloss": {"type": "boolean", "default": True, "description": "Add each slot's gloss layer (screen)."},
    "source_page": {"type": ["string", "integer"], "description": "Page of the design to show (default: the first)."},
    "artboard": {"type": "string", "description": "Artboard of the design to show."},
    "export": {"type": "array", "items": {"type": "string"},
               "description": "Image formats to export each mockup to, next to it (png, jpg, webp, pdf …), through "
                              "the export_batch path."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace existing mockup files."},
    "place": {"type": "object", "additionalProperties": {"anyOf": [
        {"type": "string"}, {"type": "object", "additionalProperties": False, "properties": {
            "design": {"type": "string", "description": "The design: a workspace .vixl document."},
            "fit": {"type": "string", "enum": ["fill", "fit", "stretch"],
                    "description": "How this design fills its area (default: the request's fit)."},
            "finish": {"type": "string", "enum": [*finishes.FINISHES, "none"],
                       "description": "The print finish of this area (default: the request's, else the area's own)."},
            "source_page": {"type": ["string", "integer"], "description": "Page of this design to show."},
            "artboard": {"type": "string", "description": "Artboard of this design to show."}},
                                                  "required": ["design"]}]},
        "description": "Designs by placement: {area name: design.vixl} or {area name: {design, fit?, finish?, "
                       "source_page?, artboard?}}. Names are the template's areas (mockup-list), for a tee "
                       "front-chest, full-front, back, sleeve-l, sleeve-r, hem-tag and inside-neck; sleeve-l is the "
                       "wearer's left."},
    "finish": {"type": "string", "enum": [*finishes.FINISHES, "none"],
               "description": "How the print looks on the product: " + "; ".join(
                   f"{name}: {info['summary']}" for name, info in finishes.FINISHES.items()) + "; none leaves the print flat, "
               "even where the product has a default finish. Applies to every placed design; a place entry can choose "
               "its own."},
    "garment_color": {"type": "string", "description": "A colour (name, #hex …) for the template's base layers: the "
                      "garment, bag or sheet itself, with its shading kept. Only templates with a garment colour "
                      "take it (mockup-list shows each default)."},
    "name": {"type": "string", "description": "mockup-save: the template name."},
    "value": {"type": "object", "description": "mockup-save: {description, document (a workspace .vixl) or width, "
              "height, background and operations, slots: [{name, corners: [[x, y] ×4], surface, radius, shade, "
              "gloss}], areas: {name: {corners, print_size_mm: [w, h], clip_path, surface, finish, cut}}, "
              "base: [layer names], garment_color, overlay (operations drawn above the placements)}."},
}
SLOT_KEYS = {"name", "corners", "surface", "radius", "shade", "gloss", "clip_path", "print_size_mm", "cut", "finish"}
AREA_KEYS = SLOT_KEYS - {"name"}
CUT_KEYS = {"mode", "border_mm", "color"}
CUT_MODES = ("die", "kiss", "pin", "patch")
TEMPLATE_KEYS = {"description", "document", "width", "height", "background", "operations", "slots", "overlay", "areas",
                 "base", "garment_color"}

DARK_SCREEN = "#0b0d12"

BUILTINS = {}


def _rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _shadow(name, x, y, w, h, radius, amount=18, opacity=0.35):
    return [{"type": "shape", "shape": "rounded-rectangle", "name": name, "x": x, "y": y, "width": w, "height": h,
             "radius": radius, "fill": "#000000", "opacity": opacity},
            {"type": "blur", "target": name, "amount": amount}]


BUILTINS.update({
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
        "description": "A framed portrait A3 poster (297 × 420 mm) with a white mat on a plain wall.",
        "width": 1600, "height": 1200, "background": "#ece6dc",
        "operations": [
            *_shadow("shadow", 498, 168, 640, 880, 4, amount=20, opacity=0.3),
            {"type": "shape", "shape": "rectangle", "name": "frame", "x": 480, "y": 140, "width": 640, "height": 880,
             "fill": "#1f1f1f"},
            {"type": "shape", "shape": "rectangle", "name": "mat", "x": 504, "y": 164, "width": 592, "height": 832,
             "fill": "#fbfaf7"},
        ],
        "slots": [{"name": "poster", "corners": _rect(552, 230, 496, 701), "radius": 0, "surface": "#ffffff",
                   "shade": True, "gloss": True, "print_size_mm": [297, 420]}],
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
})
BUILTINS.update(products.PRODUCTS)


def catalog(workspace=None):
    """Every mockup template: the built-ins, then the workspace's own (``mockups`` in its resource library)."""
    from ...resources import catalog as resource_catalog

    return {**deepcopy(BUILTINS), **resource_catalog("mockups", workspace=workspace)}


def placements(spec):
    """Every placement of a template as ``{name: record}``: its slots, then its areas (``area`` is True)."""
    found = {slot["name"]: {**slot, "area": False} for slot in spec.get("slots", [])}
    found.update({name: {**area, "name": name, "area": True} for name, area in (spec.get("areas") or {}).items()})
    return found


def main_placements(spec):
    """The placements a bare ``design`` fills: every slot, or the first area of a template that has only areas."""
    every = placements(spec)
    slots = [name for name, record in every.items() if not record["area"]]
    return slots or list(every)[:1]


def _colour(value, field):
    from ...render import color

    try:
        return color(value)
    except VixlError as exc:
        raise VixlError(exc.code, f"{field}: {exc}", field=field) from exc


def _validate_placement(record, where):
    from ...links import corner_pin

    corner_pin(record.get("corners"))
    if "print_size_mm" in record:
        size = record["print_size_mm"]
        require(isinstance(size, list) and len(size) == 2 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and 1 <= v <= 5000 for v in size),
            f"{where}.print_size_mm is [width, height] in millimetres, 1-5000", field=f"{where}.print_size_mm")
    if "clip_path" in record:
        from ...geometry import parse_path

        require(isinstance(record["clip_path"], str), f"{where}.clip_path is SVG path data", field=f"{where}.clip_path")
        parse_path(record["clip_path"])
    if "surface" in record:
        require(isinstance(record["surface"], str), f"{where}.surface is a colour, 'base' or 'none'",
                field=f"{where}.surface")
        if record["surface"] not in ("base", "none"):
            _colour(record["surface"], f"{where}.surface")
    if "finish" in record:
        require(record["finish"] in finishes.FINISHES, f"{where}.finish is one of {', '.join(finishes.FINISHES)}",
                field=f"{where}.finish", allowed=list(finishes.FINISHES))
    if "cut" in record:
        cut = record["cut"]
        require(isinstance(cut, dict) and set(cut) <= CUT_KEYS and cut.get("mode") in CUT_MODES,
                f"{where}.cut is {{mode: {'|'.join(CUT_MODES)}, border_mm?, color?}}", field=f"{where}.cut")
        if "color" in cut:
            require(isinstance(cut["color"], str), f"{where}.cut.color is a colour", field=f"{where}.cut")
            _colour(cut["color"], f"{where}.cut.color")
        require(isinstance(cut.get("border_mm", 3), (int, float)) and 0 <= cut.get("border_mm", 3) <= 50,
                f"{where}.cut.border_mm is 0-50 millimetres", field=f"{where}.cut")


def validate(value):
    """A user template: a workspace document or operations, 1–8 slots and/or 1–12 named areas of four corners."""
    from ...schema import validate_operation

    require(isinstance(value, dict), "A mockup template is an object", field="value")
    unknown = sorted(set(value) - TEMPLATE_KEYS)
    require(not unknown, f"Unknown mockup template field(s): {', '.join(unknown)}", field="value")
    if "document" in value:
        require(isinstance(value["document"], str) and value["document"].endswith(".vixl"),
                "document is a workspace .vixl path", field="value.document")
        require("operations" not in value, "Give a document or operations, not both", field="value")
    else:
        from ...model import Limits

        require("width" in value and "height" in value, "A template built from operations needs width and height",
                field="value")
        Limits().size(value["width"], value["height"])
    names = set()
    for key in ("operations", "overlay"):
        ops = value.get(key, [])
        require(isinstance(ops, list) and len(ops) <= 500, f"{key} is a list of up to 500 operations", field=f"value.{key}")
        for op in ops:
            validate_operation(op)
            reads = op["type"] in ("link", "template-apply", "font-register", "add", "frame", "drawing") or (
                "path" in op and op["type"] != "shape")
            require(not reads, "Mockup templates draw with operations; they cannot read files", field=f"value.{key}")
            if op.get("name"):
                names.add(op["name"])
    slots = value.get("slots", [])
    areas = value.get("areas", {})
    require(isinstance(slots, list) and len(slots) <= MAX_SLOTS, f"slots lists up to {MAX_SLOTS} slots",
            field="value.slots")
    require(isinstance(areas, dict) and len(areas) <= MAX_PLACEMENTS,
            f"areas maps up to {MAX_PLACEMENTS} area names to their corners and print size", field="value.areas")
    require(slots or areas, f"A template needs 1–{MAX_SLOTS} slots or named areas to place designs in",
            field="value.slots")
    taken = []
    for i, slot in enumerate(slots):
        require(isinstance(slot, dict) and set(slot) <= SLOT_KEYS and isinstance(slot.get("name"), str),
                f"slots[{i}] is {{name, corners, surface?, radius?, shade?, gloss?, print_size_mm?}}",
                field=f"value.slots[{i}]")
        _validate_placement(slot, f"slots[{i}]")
        taken.append(slot["name"])
    for name, area in areas.items():
        require(isinstance(name, str) and AREA_NAME.fullmatch(name),
                f"Area name {name!r}: lowercase letters, digits and hyphens (front-chest, back, sleeve-l …)",
                field="value.areas")
        require(isinstance(area, dict) and set(area) <= AREA_KEYS and "print_size_mm" in area,
                f"areas.{name} is {{corners, print_size_mm, clip_path?, surface?, radius?, shade?, gloss?, finish?, "
                "cut?}", field=f"value.areas.{name}")
        _validate_placement(area, f"areas.{name}")
        taken.append(name)
    require(len(set(taken)) == len(taken), "Slot and area names must be unique", field="value.slots")
    if "base" in value:
        base = value["base"]
        require(isinstance(base, list) and len(base) <= 64 and all(isinstance(n, str) for n in base),
                "base lists the names of the layers a garment colour recolours", field="value.base")
        missing = [n for n in base if "document" not in value and n not in names]
        require(not missing, f"base names layers the template does not draw: {', '.join(missing)}", field="value.base")
    if "garment_color" in value:
        _colour(value["garment_color"], "value.garment_color")
        require("base" in value or any(p.get("surface") == "base" for p in (*slots, *areas.values())),
                "garment_color needs base layers (base) or a placement whose surface is 'base'", field="value.base")


def _local_path(path, x0, y0):
    """``path`` shifted by (-x0, -y0): absolute canvas path data as the local path of a layer at (x0, y0)."""
    from ...geometry import parse_path
    from ...pathfinder_geometry import path_data

    return path_data([(command, [v - (x0 if i % 2 == 0 else y0) for i, v in enumerate(values)])
                      for command, values in parse_path(path)])


def placement_operations(slot, design, settings, name):
    """The layers one placement adds: the surface it is clipped to (its quad, or its ``clip_path``), the linked design
    (corner-pinned), the finish, then shading and gloss clipped to the surface, and a cut shape for stickers and
    pins."""
    corners = slot["corners"]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    w, h = int(max(xs)) + 2 - x0, int(max(ys)) + 2 - y0
    local = [[round(px - x0, 3), round(py - y0, 3)] for px, py in corners]
    rectangle = (local[0][1] == local[1][1] and local[2][1] == local[3][1] and local[0][0] == local[3][0]
                 and local[1][0] == local[2][0])
    surface = f"{name}-surface"
    colour = slot.get("surface", "#ffffff")
    if colour == "base":
        colour = settings.get("garment_color") or "#ffffff"
    ops = []
    if colour == "none":
        surface = None
    elif slot.get("clip_path"):
        from ...geometry import path_extents

        ex0, ey0, ex1, ey1 = path_extents(slot["clip_path"])
        sx, sy = math.floor(ex0) - 1, math.floor(ey0) - 1
        ops.append({"type": "shape", "shape": "path", "name": surface, "x": sx, "y": sy,
                    "width": math.ceil(ex1) + 2 - sx, "height": math.ceil(ey1) + 2 - sy,
                    "path": _local_path(slot["clip_path"], sx, sy), "fill": colour})
    elif rectangle:
        ops.append({"type": "shape", "shape": "rounded-rectangle" if slot.get("radius") else "rectangle", "name": surface,
                    "x": x0 + local[0][0], "y": y0 + local[0][1], "width": local[1][0] - local[0][0],
                    "height": local[3][1] - local[0][1], "fill": colour,
                    **({"radius": slot["radius"]} if slot.get("radius") else {})})
    else:
        path = "M" + " L".join(f"{px:g} {py:g}" for px, py in local) + " Z"
        ops.append({"type": "shape", "shape": "path", "name": surface, "x": x0, "y": y0, "width": w, "height": h,
                    "path": path, "fill": colour})
    ops.append({"type": "link", "name": name, "source": design, "x": x0, "y": y0, "width": w, "height": h,
                "fit": settings["fit"], "corner_pin": local,
                **{k: settings[k] for k in ("source_page", "artboard") if settings.get(k) is not None}})
    if surface:
        ops.append({"type": "clip", "target": name, "base": surface})
    finish = settings.get("finish") or slot.get("finish")
    if finish and finish != "none":
        ops += finishes.operations(finish, name, (x0, y0, w, h), surface, slot.get("print_size_mm"))
    cut = slot.get("cut")
    if cut:
        ops += _cut_operations(cut, name, slot)
    base = f"{name}-cut" if cut else surface
    if base and settings["shade"] and slot.get("shade", True):
        ops += [{"type": "gradient", "name": f"{name}-shade", "x": x0, "y": y0, "width": w, "height": h,
                 "direction": "angled", "angle": 60,
                 "stops": [{"offset": 0, "color": "rgba(255,255,255,0)"}, {"offset": 1, "color": "rgba(0,0,0,0.22)"}]},
                {"type": "blend", "target": f"{name}-shade", "value": "multiply"},
                {"type": "clip", "target": f"{name}-shade", "base": base}]
    if base and settings["gloss"] and slot.get("gloss", True):
        ops += [{"type": "gradient", "name": f"{name}-gloss", "x": x0, "y": y0, "width": w, "height": h,
                 "direction": "angled", "angle": 35,
                 "stops": [{"offset": 0, "color": "rgba(255,255,255,0.22)"}, {"offset": 0.45, "color": "rgba(255,255,255,0.06)"},
                           {"offset": 0.46, "color": "rgba(255,255,255,0)"}, {"offset": 1, "color": "rgba(255,255,255,0)"}]},
                {"type": "blend", "target": f"{name}-gloss", "value": "screen"},
                {"type": "clip", "target": f"{name}-gloss", "base": base}]
    return ops


def _cut_operations(cut, name, slot):
    """A cut shape around the placed design's ink (``die-cut``): a white border for a die-cut sticker, a thin cut line
    for a kiss-cut one, a metal rim for an enamel pin. It goes under the design and carries a soft shadow."""
    xs = [p[0] for p in slot["corners"]]
    size = slot.get("print_size_mm") or [max(xs) - min(xs), 1]
    per_mm = (max(xs) - min(xs)) / size[0]
    mode = cut["mode"]
    border = cut.get("border_mm", {"die": 3, "kiss": 3, "pin": 1.2, "patch": 2.5}[mode])
    layer = f"{name}-cut"
    look = {"die": {"fill": "#ffffff", "stroke": "#ffffff", "stroke_width": 1},
            "kiss": {"fill": "#ffffff", "stroke": "#9aa1ad", "stroke_width": max(1.5, per_mm * 0.25)},
            "pin": {"fill": "#d9b45a", "stroke": "#8f6d1f", "stroke_width": max(1.5, per_mm * 0.35)},
            "patch": {"fill": cut.get("color", "#1f1f1f"), "stroke": "#8e9298", "stroke_width": max(1.5, per_mm * 0.3)}}[mode]
    ops = [{"type": "die-cut", "targets": [name], "distance": round(border * per_mm, 2), "name": layer,
            "stroke": look["stroke"], "stroke_width": round(look["stroke_width"], 2), "smooth": 1.5},
           {"type": "shape", "target": layer, "fill": look["fill"]},
           {"type": "lower", "target": layer}]
    if mode == "patch":
        # The merrow edge: a dashed thread line along the middle of the border.
        ops.append({"type": "shape", "target": layer, "dash": [round(per_mm * 0.5, 2), round(per_mm * 0.4, 2)],
                    "stroke_align": "inside"})
    if mode == "pin":
        ops.append({"type": "shape", "target": layer, "fill_gradient": {
            "direction": "angled", "angle": 40,
            "stops": [{"offset": 0, "color": "#f4dc8e"}, {"offset": 0.45, "color": "#c9a13f"},
                      {"offset": 0.7, "color": "#e9cf7c"}, {"offset": 1, "color": "#9c7a28"}]}})
    shadow = {"die": (0.016, 0.3), "kiss": (0.006, 0.18), "pin": (0.02, 0.4), "patch": (0.012, 0.35)}[mode]
    unit = per_mm * size[0] * shadow[0]
    ops.append({"type": "layer-style", "target": layer, "name": "drop-shadow",
                "settings": {"color": "#000000", "dx": round(unit * 0.4, 2), "dy": round(unit, 2),
                             "blur": round(unit * 1.8, 2), "opacity": shadow[1]}})
    return ops


def _recolour(operations, base, colour):
    """``operations`` with the ``fill`` of the base layers set to ``colour``."""
    return [{**op, "fill": colour} if op.get("name") in base and "fill" in op else op for op in operations]


def build(session, name, spec, designs, destination, settings):
    """The mockup document for template ``spec``, with ``designs`` ({placement: {design, fit, finish, ...}}) linked and
    saved at ``destination``."""
    from ...project import Project

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
    colour = settings.get("garment_color") or spec.get("garment_color")
    if colour and spec.get("base"):
        operations = _recolour(operations, set(spec["base"]), colour)
    taken = {layer["name"] for layer in project.state["layers"]} | {op["name"] for op in operations if op.get("name")}
    every = placements(spec)
    layer_names = {}
    for key, entry in designs.items():
        layer_names[key] = key if key not in taken else f"design-{key}"
        record = every[key]
        # A placement's own settings override the request's.
        local = {**settings, **{k: v for k, v in entry.items() if k != "design" and v is not None}, "garment_color": colour}
        operations += placement_operations(record, str(entry["design"]), local, layer_names[key])
    operations += list(spec.get("overlay", []))
    project.apply(operations)
    first = next(iter(designs.values()))["design"]
    project.state["mockup"] = {
        "template": name, "design": session.relative(first), "slots": list(layer_names.values()),
        "placed": {key: session.relative(entry["design"]) for key, entry in designs.items()},
        **({"garment_color": colour} if colour and (spec.get("base") or any(
            every[key].get("surface") == "base" for key in designs)) else {}),
        **({"areas": {key: every[key]["print_size_mm"] for key in designs if every[key].get("print_size_mm")}}
           if any(every[key].get("print_size_mm") for key in designs) else {})}
    return project


def listing(spec, builtin):
    every = placements(spec)
    return {"description": spec.get("description", ""),
            "slots": [name for name, record in every.items() if not record["area"]],
            "areas": {name: {"print_size_mm": record.get("print_size_mm"),
                             **({"finish": record["finish"]} if record.get("finish") else {})}
                      for name, record in every.items() if record["area"]},
            "size": [spec["width"], spec["height"]] if "width" in spec else None,
            **({"garment_color": spec["garment_color"]} if spec.get("garment_color") else {}),
            "builtin": builtin}


def resolve_templates(session, request, available):
    """The template names of a request, each checked against the catalog."""
    names = request["mockup"] if isinstance(request["mockup"], list) else [request["mockup"]]
    require(names and all(isinstance(n, str) for n in names) and len(names) <= 16,
            "mockup is a template name or a list of up to 16", field="mockup")
    for item in names:
        if item not in available:
            import difflib

            close = difflib.get_close_matches(item, list(available), 3, 0.5)
            raise VixlError("invalid_request", f"Unknown mockup {item!r}; templates: {', '.join(available)}",
                            field="mockup", allowed=list(available), suggestions=close)
    return names


def request_settings(request):
    """The fit, shade, gloss, page, artboard, finish and garment colour of a request, checked."""
    settings = {"fit": request.get("fit", "fill"), "shade": request.get("shade", True),
                "gloss": request.get("gloss", True), "source_page": request.get("source_page"),
                "artboard": request.get("artboard"), "finish": request.get("finish"),
                "garment_color": request.get("garment_color")}
    require(settings["fit"] in ("fill", "fit", "stretch"), "fit is fill, fit or stretch", field="fit")
    for key in ("shade", "gloss", "overwrite"):
        require(type(request.get(key, True)) is bool, f"{key} must be true or false", field=key)
    require(settings["finish"] is None or settings["finish"] in (*finishes.FINISHES, "none"),
            f"finish is one of {', '.join(finishes.FINISHES)} or none", field="finish",
            allowed=[*finishes.FINISHES, "none"])
    if settings["garment_color"] is not None:
        require(isinstance(settings["garment_color"], str), "garment_color is a colour", field="garment_color")
        _colour(settings["garment_color"], "garment_color")
    return settings


def plan_designs(session, spec, name, request):
    """``{placement: {design (a path), fit?, finish?, source_page?, artboard?}}`` for one template: the bare ``design``
    fills the slots (or the main area), ``place`` names areas and wins over it."""
    every = placements(spec)
    chosen = {}

    def resolved(value, field):
        path = session.resolve(value)
        require(isinstance(value, str) and path.suffix.lower() == ".vixl" and path.is_file(),
                f"design must be a .vixl document in the workspace; {value!r} is not one", field=field)
        return path

    if request.get("design") is not None:
        design = resolved(request["design"], "design")
        for key in main_placements(spec):
            chosen[key] = {"design": design}
    place = request.get("place")
    if place is not None:
        require(isinstance(place, dict) and place, "place is {area name: design.vixl}", field="place")
        for key, value in place.items():
            if key not in every:
                import difflib

                raise VixlError("invalid_request", f"Mockup {name!r} has no area {key!r}; its areas: "
                                f"{', '.join(every)}", field="place", allowed=list(every),
                                suggestions=difflib.get_close_matches(key, list(every), 3, 0.5))
            entry = {"design": value} if isinstance(value, str) else dict(value) if isinstance(value, dict) else None
            require(entry is not None and "design" in entry and set(entry) <= {"design", "fit", "finish", "source_page",
                                                                                "artboard"},
                    f"place.{key} is a design path or {{design, fit?, finish?, source_page?, artboard?}}",
                    field=f"place.{key}")
            if "fit" in entry:
                require(entry["fit"] in ("fill", "fit", "stretch"), "fit is fill, fit or stretch", field=f"place.{key}.fit")
            if "finish" in entry:
                require(entry["finish"] in (*finishes.FINISHES, "none"),
                        f"finish is one of {', '.join(finishes.FINISHES)} or none", field=f"place.{key}.finish",
                        allowed=[*finishes.FINISHES, "none"])
            entry["design"] = resolved(entry["design"], f"place.{key}")
            chosen[key] = entry
    require(chosen, "Give a design (it fills the template's slots or main area) or place: {area: design}",
            field="design")
    return {key: chosen[key] for key in every if key in chosen}


def check_garment_color(name, spec, settings):
    if settings.get("garment_color") is not None:
        require(spec.get("garment_color") and (spec.get("base") or any(
            p.get("surface") == "base" for p in placements(spec).values())),
            f"Mockup {name!r} has no garment colour; garment_color recolours the base layers of garments and bags "
            "(mockup-list shows the templates that have one)", field="garment_color")


def dispatch(session, action, request, document=None):
    workspace = session.workspace
    if action == "mockup-list":
        return {"mockups": {name: listing(spec, name in BUILTINS) for name, spec in catalog(workspace).items()}}
    if action == "mockup-save":
        from ...resources import register

        validate(request["value"])
        require(request["name"] not in BUILTINS, f"{request['name']!r} is a built-in template; choose another name",
                field="name")
        return register("mockups", request["name"], request["value"], workspace=workspace)
    available = catalog(workspace)
    names = resolve_templates(session, request, available)
    settings = request_settings(request)
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
    planned = {}
    for item, destination in plan:
        spec = available[item]
        if item not in BUILTINS:
            validate(spec)
        check_garment_color(item, spec, settings)
        planned[item] = plan_designs(session, spec, item, request)
        for entry in planned[item].values():
            require(destination != entry["design"], "output would overwrite the design", field="output")
        require(overwrite or not destination.exists(), f"{session.relative(destination)} already exists; set "
                "overwrite=true or choose another output", field="output")
    results = []
    for item, destination in plan:
        project = build(session, item, available[item], planned[item], destination, settings)
        session.make_parent(destination)
        project.save(destination, overwrite=overwrite)
        results.append({"mockup": item, "path": session.relative(destination),
                        "slots": project.state["mockup"]["slots"],
                        **({"garment_color": project.state["mockup"]["garment_color"]}
                           if "garment_color" in project.state["mockup"] else {})})
    if formats:
        from ...export_batch import export_batch
        from ...io_policy import export_file

        targets = [{"path": session.relative(Path(session.resolve(row["path"])).with_suffix("." + f)),
                    "document": row["path"]} for row in results for f in formats]
        batch = export_batch(session, export_file, targets, overwrite=overwrite)
        for row in results:
            row["exports"] = [item for item in batch["results"] if item.get("document") == row["path"]
                              or item.get("path", "").startswith(row["path"][:-5])]
    designs = sorted({session.relative(entry["design"]) for item in planned.values() for entry in item.values()})
    return {"design": designs[0] if len(designs) == 1 else designs, "count": len(results), "mockups": results}
