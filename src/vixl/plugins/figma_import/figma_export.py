"""Offline Figma interchange: editable nodes, embedded images and explicit loss reports.

The document tree follows Figma's REST file shape. ``images`` carries bounded base64 PNGs
so the local import plugin and Vixl's importer need neither a token nor external URLs.
"""

import base64
from copy import copy, deepcopy
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

from ...errors import require
from ...geometry import default_fill, placed_path, shape_path, stroke_align
from ...render import color, resolve_layout, resolved_layers, rest_size
from .figma_import import BLENDS, MAX_IMAGES

VERSION = "vixl-figma-1"
BLEND = {value: key for key, value in BLENDS.items() if key != "PASS_THROUGH"}


def absolute_bounds(document):
    """Publish world bounds after all group scales and artboard placements are known.

    Figma's importer uses these bounds to distinguish group-local from frame-local coordinates;
    giving it a child-local box would make an otherwise correct transform look inconsistent.
    """
    pending = [(document, np.eye(3))]
    while pending:
        node, parent = pending.pop()
        local = np.eye(3)
        if "relativeTransform" in node:
            local[:2] = node["relativeTransform"]
        world = parent @ local
        if "size" in node:
            w, h = node["size"]["x"], node["size"]["y"]
            points = world @ np.array([[0, w, w, 0], [0, 0, h, h], [1, 1, 1, 1]])
            node["absoluteBoundingBox"] = {
                "x": float(points[0].min()), "y": float(points[1].min()),
                "width": float(np.ptp(points[0])), "height": float(np.ptp(points[1]))}
        pending.extend((child, world) for child in node.get("children", []))


def rgba(value, project):
    from ...design import resolve_color

    channels = color(resolve_color(value, project.state)) if isinstance(value, str) else value
    return {name: float(channel) / 255 for name, channel in zip("rgba", channels)}


def solid(value, project):
    paint = rgba(value, project)
    return [{"type": "SOLID", "color": {key: paint[key] for key in "rgb"}, "opacity": paint.get("a", 1)}] \
        if paint.get("a", 1) else []


def gradient(settings, project):
    direction = settings.get("direction", "vertical")
    if direction == "radial":
        x, y = settings.get("center", [0.5, 0.5])
        handles = [(x, y), (x + 0.5, y), (x, y + 0.5)]
    else:
        angle = settings.get("angle", 0) if direction == "angled" else (0 if direction == "horizontal" else 90)
        x, y = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        span = abs(x) + abs(y)
        dx, dy = x * span, y * span
        origin = (0.5 - dx / 2, 0.5 - dy / 2)
        handles = [origin, (origin[0] + dx, origin[1] + dy), (origin[0] - dy, origin[1] + dx)]
    a, b, c = np.array(handles)
    transform = np.eye(3)
    transform[:2, 0], transform[:2, 1], transform[:2, 2] = b - a, c - a, a - (c - a) * 0.5
    stops = settings.get("stops") or [{"offset": 0, "color": settings.get("start", "black")},
                                       {"offset": 1, "color": settings.get("end", "white")}]
    return {"type": "GRADIENT_RADIAL" if direction == "radial" else "GRADIENT_LINEAR",
            "gradientHandlePositions": [{"x": float(x), "y": float(y)} for x, y in handles],
            "gradientTransform": np.linalg.inv(transform)[:2].tolist(),
            "gradientStops": [{"position": stop["offset"], "color": rgba(stop["color"], project)} for stop in stops]}


def font_style(project, layer):
    from ...text import font_style as identity, primary_font_data
    from fontTools.ttLib import TTFont

    data = primary_font_data(project, layer)
    family, weight, italic = identity(data)
    with TTFont(io.BytesIO(data), lazy=True) as font:
        name = font["name"].getDebugName(17) or font["name"].getDebugName(2) or "Regular"
    return {"fontFamily": family, "fontStyle": name, "fontWeight": weight, "italic": italic,
            "fontSize": layer.get("size", 48), "letterSpacing": layer.get("tracking", 0)}


class Writer:
    def __init__(self, project, images, report, prefix):
        self.project, self.images, self.report, self.prefix = project, images, report, prefix
        self.layers = resolved_layers(project)
        self.bounds = resolve_layout(project, layers=self.layers)
        self.index = {layer["id"]: layer for layer in self.layers}
        self.children = {}
        for layer in self.layers:
            self.children.setdefault(layer.get("parent"), []).append(layer)
        self.counter = 0

    def ident(self):
        self.counter += 1
        return f"{self.prefix}:{self.counter}"

    def lost(self, layer, reason):
        self.report["unmapped"].append({"layer": layer["name"], "id": layer["id"], "reason": reason})

    def image(self, image):
        stream = io.BytesIO()
        image.save(stream, "PNG")
        data = stream.getvalue()
        require(len(data) <= self.project.limits.max_asset_bytes,
                "A Figma raster fallback exceeds the asset limit", "resource_limit", field="images")
        ref = hashlib.sha256(data).hexdigest()
        if ref not in self.images:
            require(len(self.images) < MAX_IMAGES, f"Figma interchange holds at most {MAX_IMAGES} images",
                    "resource_limit", field="images")
            encoded = base64.b64encode(data).decode("ascii")
            require(sum(len(item["base64"]) for item in self.images.values()) + len(encoded)
                    <= self.project.limits.max_project_bytes,
                    "Embedded Figma images exceed the project limit", "resource_limit", field="images")
            self.images[ref] = {"mime": "image/png", "base64": encoded}
        return [{"type": "IMAGE", "imageRef": ref, "scaleMode": "FILL"}]

    def base(self, layer, kind, transform=None, size=None):
        from ...affine import layer_matrix

        w, h = size or rest_size(layer)
        m = layer_matrix(layer, self.bounds[layer["id"]]) if transform is None else transform
        points = m @ np.array([[0, w, w, 0], [0, 0, h, h], [1, 1, 1, 1]])
        return {"id": self.ident(), "name": layer["name"], "type": kind,
                "size": {"x": float(w), "y": float(h)}, "relativeTransform": m[:2].tolist(),
                "absoluteBoundingBox": {"x": float(points[0].min()), "y": float(points[1].min()),
                                        "width": float(np.ptp(points[0])), "height": float(np.ptp(points[1]))},
                "opacity": layer["opacity"], "visible": layer["visible"],
                "blendMode": BLEND.get(layer["blend"], "NORMAL")}

    def fallback(self, layer, reasons):
        from ...render import layer_patch

        for reason in reasons:
            self.lost(layer, reason)
        # The transformed patch includes effects, masks and group overflow in parent coordinates.
        patch, origin = layer_patch(self.project, {**layer, "visible": True, "opacity": 1}, self.bounds,
                                    (1, 1), self.index, limit=(-1000000, -1000000, 1000000, 1000000))
        if patch is None:
            from PIL import Image

            patch, origin = Image.new("RGBA", (1, 1)), self.bounds[layer["id"]][:2]
        m = np.eye(3)
        m[:2, 2] = origin
        node = self.base(layer, "RECTANGLE", m, patch.size)
        node.update(name="RASTER: " + layer["name"], fills=self.image(patch))
        return node

    def unsupported(self, layer):
        reasons = []
        for key in ("mask", "repeat", "distort", "cut_paper", "export_fallback"):
            if layer.get(key):
                reasons.append(f"{key} rasterized")
        for effect in layer.get("effects", []):
            if effect.get("enabled", True) and effect["name"] != "blur":
                reasons.append(f"effect {effect['name']} rasterized")
        for name, settings in layer.get("styles", {}).items():
            if settings.get("enabled", True) and name not in ("drop-shadow", "inner-shadow"):
                reasons.append(f"style {name} rasterized")
        if layer["blend"] not in BLEND:
            reasons.append(f"blend {layer['blend']} has no Figma equivalent; rendered over transparency")
        paint = layer if layer["type"] == "gradient" else layer.get("fill_gradient", {})
        if paint.get("falloff", "linear") != "linear":
            reasons.append("non-linear gradient falloff rasterized")
        if layer["type"] == "text":
            layout = layer.get("text_layout") or {}
            if layout.get("path") or layout.get("warp", "none") != "none" or any(layer.get(key) for key in
                    ("stroke_width", "hanging_punctuation", "small_caps")):
                reasons.append("special text appearance rasterized")
        if layer["type"] not in ("shape", "solid", "gradient", "group", "text", "raster", "frame"):
            reasons.append(f"{layer['type']} layer rasterized")
        return reasons

    def effects(self, layer):
        effects = []
        for effect in layer.get("effects", []):
            if effect.get("enabled", True) and effect["name"] == "blur":
                effects.append({"type": "LAYER_BLUR", "radius": 2 * effect.get("amount", 1), "visible": True})
        for name, settings in layer.get("styles", {}).items():
            if name in ("drop-shadow", "inner-shadow") and settings.get("enabled", True):
                ink = rgba(settings.get("color", "black"), self.project)
                ink["a"] *= settings.get("opacity", 0.5)
                effects.append({"type": "DROP_SHADOW" if name == "drop-shadow" else "INNER_SHADOW",
                                "color": ink, "offset": {"x": settings.get("dx", 4), "y": settings.get("dy", 4)},
                                "radius": settings.get("blur", 8) * 2, "spread": 0,
                                "blendMode": "NORMAL", "visible": True})
        return effects

    def text(self, layer):
        from ...variables import layer_text
        from ...render import document_variables
        from ...text import primary_font_data
        from ...text_metrics import font_metrics

        node = self.base(layer, "TEXT")
        style = font_style(self.project, layer)
        metrics = font_metrics(primary_font_data(self.project, layer), layer.get("size", 48))
        pitch = metrics["ascent"] + metrics["descent"]
        rich = layer.get("rich") or {}
        line_height = (rich.get("line_height", 1.2) * layer.get("size", 48) if rich.get("line_basis") == "size"
                       else pitch * rich.get("line_height", 1) + layer.get("spacing", 0))
        style.update(textAlignHorizontal={"justify": "JUSTIFIED"}.get(layer.get("align"), layer.get("align", "left").upper()),
                     textAlignVertical="TOP",
                     textAutoResize="WIDTH_AND_HEIGHT" if layer.get("auto_size", True) else "NONE",
                     lineHeightPx=line_height)
        if rich.get("paragraph_spacing"):
            style["paragraphSpacing"] = rich["paragraph_spacing"]
        if any(para for para in rich.get("paragraphs", [])):
            self.lost(layer, "per-paragraph alignment, lists, indentation and spacing need review in Figma")
        node.update(characters=layer_text(layer, document_variables(self.project)), style=style,
                    fills=solid(layer.get("color", "black"), self.project))
        if layer.get("rich"):
            from ...richtext import styled_spans

            overrides, table, characters = [], {}, []
            for index, span in enumerate(styled_spans(self.project, layer), 1):
                entry = font_style(self.project, {**layer, **span})
                entry.update(fills=solid(span["color"], self.project), fontSize=span["size"],
                             letterSpacing=span["tracking"])
                span_metrics = font_metrics(primary_font_data(self.project, {**layer, **span}), span["size"])
                entry["lineHeightPx"] = (rich.get("line_height", 1.2) * span["size"]
                                         if rich.get("line_basis") == "size" else
                                         (span_metrics["ascent"] + span_metrics["descent"]) * rich.get("line_height", 1)
                                         + layer.get("spacing", 0))
                if span["fake_bold"]:
                    entry.update(fontWeight=700, fontStyle="Bold Italic" if span["fake_italic"] else "Bold")
                elif span["fake_italic"]:
                    entry.update(italic=True, fontStyle="Italic")
                if span["underline"] or span["strike"]:
                    entry["textDecoration"] = "UNDERLINE" if span["underline"] else "STRIKETHROUGH"
                if span["highlight"] or span["baseline"] != "normal" or span["small_caps"]:
                    self.lost(layer, "rich-text highlight, baseline shift or small caps is not editable in Figma")
                table[str(index)] = entry
                characters.append(span["text"])
                overrides.extend([index] * (len(span["text"].encode("utf-16-le")) // 2))
            node.update(characters="".join(characters), characterStyleOverrides=overrides, styleOverrideTable=table)
        if "\t" in node["characters"]:
            self.lost(layer, "tab characters kept; custom tab stops and leaders need review in Figma")
        return node

    def shape(self, layer):
        kind = layer["type"]
        shape = layer.get("shape", "rectangle")
        native = {"rectangle": "RECTANGLE", "rounded-rectangle": "RECTANGLE", "capsule": "RECTANGLE",
                  "ellipse": "ELLIPSE"}
        node = self.base(layer, native.get(shape, "VECTOR"))
        w, h = rest_size(layer)
        if kind == "solid":
            node["fills"] = solid(layer.get("color", "black"), self.project)
        elif kind == "gradient":
            node["fills"] = [gradient(layer, self.project)]
        else:
            node["fills"] = [gradient(layer["fill_gradient"], self.project)] if layer.get("fill_gradient") \
                else solid(default_fill(layer), self.project)
        if shape in ("rounded-rectangle", "capsule"):
            radius = layer.get("radius", min(w, h) / (2 if shape == "capsule" else 5))
            if not isinstance(radius, (int, float)):
                return self.fallback(layer, ["non-uniform rounded corners rasterized"])
            node["cornerRadius"] = min(radius, w / 2, h / 2)
        if node["type"] == "VECTOR":
            if shape == "line":
                from ...geometry import compact_number, stroke_inset

                stroke = rgba(layer.get("stroke", "transparent"), self.project)
                inset, _ = stroke_inset(layer, stroke.get("a", 1) > 0)
                path = "M{} {} L{} {}".format(*(compact_number(value, 6) for value in (inset, inset, w - inset, h - inset)))
                view = (w, h)
            else:
                path, view = shape_path(layer)
            node["fillGeometry"] = [{"path": placed_path(path, view, (0, 0, w, h)), "windingRule": "NONZERO"}]
        if kind == "shape" and layer.get("stroke"):
            node.update(strokes=solid(layer["stroke"], self.project), strokeWeight=layer.get("stroke_width", 1),
                        strokeAlign=stroke_align(layer).upper(),
                        strokeCap={"butt": "NONE", "round": "ROUND", "square": "SQUARE"}[layer.get("line_cap", "butt")],
                        strokeJoin=layer.get("line_join", "miter").upper())
            if isinstance(layer.get("dash"), list):
                node["strokeDashes"] = layer["dash"]
        special = ("strokes", "width_profile", "taper_start", "taper_end", "marker_start", "marker_end",
                   "trim_start", "trim_end", "dash_offset")
        if any(layer.get(key) for key in special) or isinstance(layer.get("dash"), str):
            from ...vector_strokes import primitives

            node["type"] = "GROUP"
            node.pop("fills", None)
            node.pop("strokes", None)
            node["children"] = [{"id": self.ident(), "name": f"{layer['name']} outline {index}", "type": "VECTOR",
                                 "size": {"x": w, "y": h}, "relativeTransform": [[1, 0, 0], [0, 1, 0]],
                                 "fillGeometry": [{"path": path, "windingRule": "NONZERO"}],
                                 "fills": [gradient(paint.gradient, self.project)] if getattr(paint, "gradient", None)
                                 else solid(paint, self.project)}
                                for index, (path, paint) in enumerate(primitives(layer, self.project), 1) if path]
            self.lost(layer, "special strokes exported as editable outlines; stroke parameters are not retained")
        return node

    def emit(self, layer, *, clipped=True):
        if clipped and layer.get("clip"):
            base = self.emit(self.index[layer["clip"]])
            base.update(id=self.ident(), isMask=True, name=base["name"] + " mask")
            target = self.emit({**layer, "clip": None}, clipped=False)
            w, h = rest_size(layer)
            return {"id": self.ident(), "name": layer["name"] + " clipped", "type": "GROUP",
                    "size": {"x": w, "y": h}, "relativeTransform": [[1, 0, 0], [0, 1, 0]],
                    "children": [base, target]}
        reasons = self.unsupported(layer)
        if reasons:
            return self.fallback(layer, reasons)
        kind = layer["type"]
        if kind == "text":
            node = self.text(layer)
        elif kind == "group":
            node = self.base(layer, "FRAME" if layer.get("stack") else "GROUP")
            node.update(clipsContent=False, fills=[], children=[self.emit(child)
                        for child in self.children.get(layer["id"], [])
                        if not (layer.get("stack") and child.get("stack_background") == layer["id"])])
            # A resized group maps content coordinates into its current box.
            sx, sy = layer["width"] / layer["content_width"], layer["height"] / layer["content_height"]
            for child in node["children"]:
                matrix = np.array(child["relativeTransform"])
                matrix[0] *= sx
                matrix[1] *= sy
                child["relativeTransform"] = matrix.tolist()
            if layer.get("stack"):
                from ...stacks import padding_sides

                stack = layer["stack"]
                if stack.get("background"):
                    node["fills"] = solid(stack["background"], self.project)
                    node["cornerRadius"] = stack.get("radius", 0)
                if stack.get("stroke"):
                    node.update(strokes=solid(stack["stroke"], self.project), strokeWeight=stack.get("stroke_width", 1),
                                strokeAlign="INSIDE")
                if stack["direction"] == "grid" or stack.get("wrap") or not np.allclose((sx, sy), (1, 1)) \
                        or stack.get("justify") in ("space-around", "space-evenly") or stack.get("align") == "stretch" \
                        or any(child.get("stack_grow") for child in self.children.get(layer["id"], [])):
                    self.lost(layer, "grid, wrapping, resized, growing or evenly spaced stack kept as an editable frame with fixed positions")
                else:
                    top, right, bottom, left = padding_sides(stack.get("padding", 0))
                    node.update(layoutMode=stack["direction"].upper(), itemSpacing=stack.get("gap", 0),
                                paddingTop=top, paddingRight=right, paddingBottom=bottom, paddingLeft=left,
                                primaryAxisSizingMode="AUTO" if stack.get("size") == "hug" else "FIXED",
                                counterAxisSizingMode="AUTO" if stack.get("size") == "hug" else "FIXED",
                                primaryAxisAlignItems={"start": "MIN", "center": "CENTER", "end": "MAX",
                                                       "space-between": "SPACE_BETWEEN"}.get(stack.get("justify"), "MIN"),
                                counterAxisAlignItems={"start": "MIN", "center": "CENTER", "end": "MAX"}.get(
                                    stack.get("align"), "MIN"))
        elif kind in ("raster", "frame"):
            from ...render import layer_ink

            plain = {**layer, "rotation": 0, "flip_x": False, "flip_y": False, "opacity": 1,
                     "affine": None, "skew_x": 0, "skew_y": 0, "effects": [], "styles": {}, "clip": None}
            plain.pop("affine")
            image = layer_ink(self.project, plain, (0, 0, *rest_size(layer)))
            node = self.base(layer, "RECTANGLE")
            node["fills"] = self.image(image)
        else:
            node = self.shape(layer)
        node["effects"] = self.effects(layer)
        return node

    def frame(self, name):
        canvas = self.project.state["canvas"]
        root = {"id": self.ident(), "name": name, "type": "FRAME",
                "size": {"x": canvas["width"], "y": canvas["height"]},
                "relativeTransform": [[1, 0, 0], [0, 1, 0]], "clipsContent": False,
                "fills": solid(canvas["background"], self.project),
                "children": [self.emit(layer) for layer in self.children.get(None, [])]}
        if self.project.state.get("timeline"):
            self.report["unmapped"].append({"page": name, "reason": "timeline omitted; nodes show the selected static frame"})
        return root


def export_figma(project, path=None, *, pages=None, page=None, variables=None, overwrite=False, report=None):
    """Return UTF-8 interchange JSON; all visible pages by default, without mutating the project."""
    from ...pages import page_list, page_project

    require(path is None or overwrite or not Path(path).exists(),
            "Export output already exists; pass overwrite=True to replace it", "output_exists", field="path")
    report = report if report is not None else {}
    report.update(format="FIGMA", unmapped=[])
    records = page_list(project, include_hidden=False)
    refs = pages or ([page] if page is not None and page != "all" else [item["id"] for item in records] or [None])
    images, children = {}, []
    for number, ref in enumerate(refs, 1):
        view = page_project(project, ref)
        if variables:
            view = copy(view)
            view.state = {**view.state, "variables": {**view.state.get("variables", {}), **variables}}
        name = next((item["name"] for item in records if item["id"] == view.state.get("page")), "Page 1")
        writer = Writer(view, images, report, number)
        boards = view.state.get("artboards") or {}
        if boards:
            from ...design_render import artboard_project

            frames, position = [], 0
            for board_name in boards:
                board_writer = Writer(artboard_project(view, board_name), images, report, number)
                board_writer.counter = writer.counter
                frame = board_writer.frame(board_name)
                writer.counter = board_writer.counter
                frame["relativeTransform"][0][2] = position
                position += frame["size"]["x"] + 80
                frames.append(frame)
        else:
            frames = [writer.frame(name)]
        children.append({"id": writer.ident(), "name": name, "type": "CANVAS", "children": frames})
    report.update(pages=len(children), images=len(images))
    document = {"format": VERSION, "name": Path(path).name.removesuffix(".figma.json") if path else "Vixl document",
                "document": {"id": "0:0", "type": "DOCUMENT", "children": children}, "images": images,
                "report": deepcopy(report)}
    absolute_bounds(document["document"])
    data = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(data) <= project.limits.max_project_bytes, "Figma interchange exceeds the project size limit",
            "resource_limit", field="output")
    if path:
        Path(path).write_bytes(data)
    return data
