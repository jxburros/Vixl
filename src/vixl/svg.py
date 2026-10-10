"""Self-contained SVG with vector logo geometry and explicit raster fallbacks."""

import base64
import json
import math
import xml.etree.ElementTree as ET

from .assets import png_bytes
from .design import resolve_color
from .design_render import artboard_project
from .geometry import default_fill, shape_path
from .render import color, effect_margin, ink_origin, layer_image, layer_ink, render, resolved_layers, resolve_layout
from .errors import VixlError
from .svg_effects import supported, native_styles, effect_filter, style_filter

NS = "http://www.w3.org/2000/svg"
NATIVE_BLENDS = frozenset(("normal", "multiply", "screen", "overlay", "darken", "lighten",
                         "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "exclusion",
                         "hue", "saturation", "color", "luminosity"))
ET.register_namespace("", NS)


def node(parent, kind, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{kind}", {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def paint(value, state):
    r, g, b, a = color(resolve_color(value, state))
    return f"rgb({r},{g},{b})", a / 255


def bitmap(root, image, x=0, y=0):
    node(
        root,
        "image",
        x=x,
        y=y,
        width=image.width,
        height=image.height,
        href="data:image/png;base64," + base64.b64encode(png_bytes(image)).decode(),
    )


def styles(layer):
    return {
        name: settings for name, settings in layer.get("styles", {}).items() if settings.get("enabled", True)
    }


def vector_overlay(layer, state):
    return native_styles(layer, state)


def fallback_reason(layer):
    if layer.get("export_fallback") or layer.get("cut_paper"):
        return layer.get("export_fallback", "cut-paper grain and edge texture")
    if layer["type"] == "link":
        return "linked documents are exported as images"
    if layer.get("repeat"):
        return "repeat is not exported as vectors"
    if any(e["name"] == "lookup" and e.get("enabled", True) for e in layer.get("effects") or []):
        return "lookup tables are not exported as vectors"
    if layer.get("mask") and layer["mask"].get("enabled", True):
        return "raster masks are not exported as vectors"
    return "unsupported vector appearance"


class Exporter:
    def __init__(self, project, root):
        self.project, self.root = project, root
        self.layers = resolved_layers(project)
        self.bounds = resolve_layout(project, layers=self.layers)
        self.index = {item["id"]: item for item in self.layers}
        self.children = {}
        for layer in self.layers:
            self.children.setdefault(layer.get("parent"), []).append(layer)
        self.defs = node(root, "defs")
        self.counter = 0
        self.fallbacks = []
        self.text_reasons = {}
        self.used_ids = set()

    def describe(self, element, layer):
        """Object identity (id, data-vixl-object/kind/part) and accessibility (title, role, aria-hidden) of a
        layer's outer group."""
        from .accessibility import decorative
        from .objects import export_identity, svg_ident

        identity = export_identity(layer, self.index)
        title = layer.get("alt")
        if identity:
            element.set("id", svg_ident(identity["path"].replace("/", "--"), self.used_ids))
            if "kind" in identity:
                element.set("data-vixl-object", identity["path"])
                element.set("data-vixl-kind", identity["kind"])
                title = title or identity["label"]
            if "part" in identity:
                element.set("data-vixl-part", identity["part"])
                if identity.get("side"):
                    element.set("data-vixl-side", identity["side"])
        if layer.get("alt"):
            element.set("role", "img")
        elif decorative(layer) and layer["type"] != "text":
            element.set("aria-hidden", "true")
        if title:
            heading = ET.Element(f"{{{NS}}}title")
            heading.text = title
            element.insert(0, heading)

    def ident(self, prefix):
        self.counter += 1
        return f"vixl-{prefix}-{self.counter}"

    def visible(self, layer):
        while layer:
            if not layer["visible"] or layer["opacity"] == 0:
                return False
            layer = self.index.get(layer.get("parent"))
        return True

    def transform(self, layer, bounds):
        from .affine import layer_matrix, precise
        if not precise(layer):
            from .render import rest_size
            x, y, w, h = bounds
            rw, rh = rest_size(layer)
            return (f"translate({x + w / 2} {y + h / 2}) rotate({layer['rotation']}) "
                    f"scale({-1 if layer['flip_x'] else 1} {-1 if layer['flip_y'] else 1}) "
                    f"translate({-rw / 2} {-rh / 2})")
        m = layer_matrix(layer, bounds)
        values = (m[0, 0], m[1, 0], m[0, 1], m[1, 1], m[0, 2], m[1, 2])
        return "matrix(" + " ".join(format(v, ".12g") for v in values) + ")"

    def attrs(self, layer):
        fill, alpha = paint(default_fill(layer), self.project.state)
        stroke, sa = paint(layer.get("stroke", "transparent"), self.project.state)
        return dict(
            fill=fill,
            fill_opacity=alpha,
            stroke=stroke,
            stroke_opacity=sa,
            stroke_width=layer.get("stroke_width", 1),
        )

    def trimmed(self, parent, layer, attrs):
        """A shape whose stroke is trimmed: the fill whole, and one dashed stroke per contour."""
        from .trim import trim_geometry

        geometry = trim_geometry(layer, attrs["stroke_opacity"] > 0)
        view = geometry["view"]
        target = parent
        if view:
            target = node(parent, "svg", width=layer["width"], height=layer["height"], viewBox=f"0 0 {view[0]} {view[1]}",
                          preserveAspectRatio="none", overflow="visible")
        if geometry["fill"] and attrs["fill_opacity"] > 0:
            node(target, "path", d=geometry["fill"], fill=attrs["fill"], fill_opacity=attrs["fill_opacity"], stroke="none")
        stroke, opacity = attrs["stroke"], attrs["stroke_opacity"]
        if geometry["line"] and not opacity:
            stroke, opacity = attrs["fill"], attrs["fill_opacity"]
        if opacity > 0 and geometry["width"] > 0:
            for d, dash, offset in geometry["strokes"]:
                node(target, "path", d=d, fill="none", stroke=stroke, stroke_opacity=opacity, stroke_width=geometry["width"],
                     stroke_dasharray=dash, stroke_dashoffset=offset, stroke_linecap=geometry["cap"],
                     stroke_linejoin=geometry["join"])

    def shape(self, parent, layer):
        from .trim import trim_range

        attrs = self.attrs(layer)
        from .shape_catalog import active as catalog_active
        from .vector_strokes import active as stroke_active, primitives
        if catalog_active(layer) or stroke_active(layer) or layer.get("distort") or layer.get("_distort_groups"):
            for path, color in primitives(layer, self.project):
                fill, alpha = paint(color, self.project.state)
                if path and alpha:
                    node(parent, "path", d=path, fill=fill, fill_opacity=alpha)
            return
        if trim_range(layer):
            return self.trimmed(parent, layer, attrs)
        sw, sh = layer["width"], layer["height"]
        shape = layer.get("shape", "rectangle")
        if shape in ("rectangle", "rounded-rectangle", "capsule"):
            node(
                parent,
                "rect",
                width=sw,
                height=sh,
                rx=layer.get("radius", min(sw, sh) / (2 if shape == "capsule" else 5))
                if shape != "rectangle"
                else 0,
                **attrs,
            )
        elif shape == "ellipse":
            node(parent, "ellipse", cx=sw / 2, cy=sh / 2, rx=sw / 2, ry=sh / 2, **attrs)
        elif shape == "line":
            attrs.update(
                stroke=attrs["stroke"] if attrs["stroke_opacity"] else attrs["fill"],
                stroke_opacity=attrs["stroke_opacity"] or attrs["fill_opacity"],
            )
            node(parent, "line", x1=0, y1=0, x2=sw, y2=sh, **attrs)
        else:
            from .geometry import path_overflows

            path, view = shape_path(layer)
            nested = node(
                parent,
                "svg",
                width=sw,
                height=sh,
                viewBox=f"0 0 {view[0]} {view[1]}",
                preserveAspectRatio="none",
                # Paths use their box as a coordinate frame, not a clip, for fill and stroke alike.
                **({"overflow": "visible"} if path_overflows(layer) or (attrs["stroke_opacity"] > 0 and layer.get("stroke_width", 1) > 0) else {}),
            )
            if layer.get("line_cap"):
                attrs.update(stroke_linecap=layer["line_cap"],
                             stroke_linejoin="round" if layer["line_cap"] == "round" else "miter")
            node(nested, "path", d=path, **attrs)

    def text(self, parent, layer):
        from .text import plan, append_paths, UnsupportedText
        from .richtext import active

        if active(layer):
            from .richtext import append_svg, fitted

            result = fitted(self.project, layer)
            nested = node(parent, "svg", width=layer["width"], height=layer["height"],
                          viewBox=f"0 0 {layer['width']} {layer['height']}", overflow="hidden")
            append_svg(nested, result, layer, self.project, node=node)
            return True

        try:
            layout = plan(self.project, layer)
            nested = node(
                parent,
                "svg",
                width=layer["width"],
                height=layer["height"],
                viewBox=f"0 0 {layout.width} {layout.height}",
                preserveAspectRatio="none",
                overflow="hidden",
            )
            append_paths(nested, layout, layer, self.project)
            return True
        except UnsupportedText as exc:
            self.text_reasons[layer["id"]] = str(exc)
            return False

    def gradient(self, settings, box):
        ident = self.ident("gradient")
        x, y, w, h = box
        direction = settings.get("direction", "vertical")
        if direction == "radial":
            gradient = node(
                self.defs,
                "radialGradient",
                id=ident,
                gradientUnits="userSpaceOnUse",
                cx=0,
                cy=0,
                r=1,
                gradientTransform=f"translate({x + w * settings.get('center', [0.5, 0.5])[0]} {y + h * settings.get('center', [0.5, 0.5])[1]}) scale({w / 2} {h / 2})",
            )
        else:
            a = math.radians(settings.get("angle", 0))
            dx, dy = (
                (math.cos(a), math.sin(a))
                if direction == "angled"
                else ((1, 0) if direction == "horizontal" else (0, 1))
            )
            norm = abs(dx) + abs(dy)
            qx, qy = dx / max(1, w - 1) / norm, dy / max(1, h - 1) / norm
            square = qx * qx + qy * qy
            cx, cy = x + (w - 1) / 2, y + (h - 1) / 2
            gradient = node(
                self.defs,
                "linearGradient",
                id=ident,
                gradientUnits="userSpaceOnUse",
                x1=cx - qx / (2 * square),
                y1=cy - qy / (2 * square),
                x2=cx + qx / (2 * square),
                y2=cy + qy / (2 * square),
            )
        from .design import gradient_stops

        for stop in gradient_stops(settings, self.project.state):
            fill, alpha = paint(stop["color"], self.project.state)
            node(gradient, "stop", offset=stop["offset"], stop_color=fill, stop_opacity=alpha)
        return f"url(#{ident})"

    def pathfinder(self, parent, layer):
        """A boolean operation as one compound path: real geometry that every renderer fills the same
        way. (Alpha masks were drawn wrongly by renderers without ``mask-type``, such as Inkscape.)
        What cannot be combined as geometry is drawn as an image and listed as a raster fallback."""
        from .pathfinder_geometry import Unsupported, path_data, pathfinder_commands

        try:
            commands = pathfinder_commands(layer, self.project.state)
        except Unsupported as exc:
            self.text_reasons[layer["id"]] = f"pathfinder cannot be exported as path geometry: {exc}"
            return False
        if commands:
            fill, _ = paint(layer.get("fill", "white"), self.project.state)
            node(parent, "path", d=path_data(commands), fill=fill, fill_rule="evenodd")
        return True

    def geometry(self, parent, layer):
        if layer.get("repeat"):
            from .design_render import repeat_items, repeat_bounds
            if layer["type"] == "group" or styles(layer):
                return False
            rw, rh = repeat_bounds(layer)
            parent = node(parent, "svg", width=rw, height=rh, viewBox=f"0 0 {rw} {rh}", overflow="hidden")
            for item, x, y in repeat_items(layer, self.project.state):
                w, h = item["width"], item["height"]
                group = node(parent, "svg", x=x, y=y, width=w, height=h, viewBox=f"0 0 {w} {h}", overflow="hidden")
                if not self.geometry(group, item):
                    return False
            return True
        kind = layer["type"]
        if kind in ("shape", "solid"):
            self.shape(parent, layer)
        elif kind == "text":
            return self.text(parent, layer)
        elif kind == "gradient":
            node(
                parent,
                "rect",
                width=layer["width"],
                height=layer["height"],
                fill=self.gradient(layer, (0, 0, layer["width"], layer["height"])),
            )
        elif kind == "pathfinder":
            return self.pathfinder(parent, layer)
        elif kind == "field":
            from .forms import svg_field

            return svg_field(self, parent, layer)
        elif kind == "pixel":
            rows = layer["pixels"]
            group = node(
                parent,
                "g",
                transform=f"scale({layer['width'] / len(rows[0])} {layer['height'] / len(rows)})",
                shape_rendering="crispEdges",
            )
            for y, row in enumerate(rows):
                x = 0
                while x < len(row):
                    end = x + 1
                    while end < len(row) and row[end] == row[x]:
                        end += 1
                    fill, alpha = paint(layer["palette"][row[x]], self.project.state)
                    if alpha:
                        node(group, "rect", x=x, y=y, width=end - x, height=1, fill=fill, fill_opacity=alpha)
                    x = end
        elif kind == "group":
            # Groups do not clip their children, matching raster rendering.
            cw, ch = layer["content_width"], layer["content_height"]
            group = node(parent, "g", transform=f"scale({layer['width'] / cw} {layer['height'] / ch})",
                         **({"style": "isolation:isolate"} if any(x["blend"] != "normal" for x in self.layers) else {}))
            for child in self.children.get(layer["id"], []):
                self.layer(group, child)
        else:
            return False
        return True

    def layer(self, parent, layer):
        if not layer["visible"] or layer["opacity"] == 0:
            return
        if layer["type"] == "adjustment":
            parent_layer = self.index.get(layer.get("parent"))
            w, h = (
                (parent_layer["content_width"], parent_layer["content_height"])
                if parent_layer
                else (self.project.state["canvas"]["width"], self.project.state["canvas"]["height"])
            )
            previous = list(parent)
            wrapper = node(parent, "g", filter=effect_filter(self, layer["effects"], (0, 0, w, h)))
            for child in previous:
                if child is not self.defs:
                    parent.remove(child)
                    wrapper.append(child)
            return
        if layer.get("blend", "normal") != "normal":
            parent = node(parent, "g", style=f"mix-blend-mode:{layer['blend']}")
        b = self.bounds[layer["id"]]
        simple = (
            not (layer.get("mask") and layer["mask"].get("enabled", True))
            and not layer.get("cut_paper")
            and not layer.get("export_fallback")
            and supported(layer)
            and vector_overlay(layer, self.project.state)
        )
        group = ET.Element(f"{{{NS}}}g", {"opacity": str(layer["opacity"]), "data-layer": layer["name"]})
        geometry = node(group, "g", transform=self.transform(layer, b))
        self.describe(group, layer)
        if simple and self.geometry(geometry, layer):
            effects = [dict(e) for e in layer.get("effects", []) if e.get("enabled", True)]
            if effects:
                from PIL import ImageStat, ImageOps

                for index, effect in enumerate(effects):
                    if effect["name"] == "contrast":
                        image = layer_image(
                            self.project, {**layer, "effects": effects[:index], "styles": {}, "opacity": 1}, b
                        )
                        effect["_mean"] = (
                            round(ImageStat.Stat(ImageOps.grayscale(image.convert("RGB"))).mean[0]) / 255
                        )
                mx, my = effect_margin(layer)
                region = (b[0] - mx, b[1] - my, b[2] + 2 * mx, b[3] + 2 * my)
                wrapper = node(group, "g", filter=effect_filter(self, effects, region))
                group.remove(geometry)
                wrapper.append(geometry)
                geometry = wrapper
            overlay = styles(layer)
            if "gradient-overlay" in overlay:
                alpha = layer_image(self.project, {**layer, "styles": {}, "opacity": 1}, b).getchannel("A")
                box = alpha.getbbox()
                if box:
                    ident = self.ident("overlay-mask")
                    mask = node(
                        self.defs,
                        "mask",
                        id=ident,
                        maskUnits="userSpaceOnUse",
                        x=b[0],
                        y=b[1],
                        width=b[2],
                        height=b[3],
                        mask_type="alpha",
                    )
                    group.remove(geometry)
                    mask.append(geometry)
                    x, y = b[0] + box[0], b[1] + box[1]
                    w, h = box[2] - box[0], box[3] - box[1]
                    fill = (
                        self.gradient(overlay["gradient-overlay"], (x, y, w, h))
                        if "gradient-overlay" in overlay
                        else paint(overlay["color-overlay"].get("color", "white"), self.project.state)[0]
                    )
                    node(group, "rect", x=x, y=y, width=w, height=h, fill=fill, mask=f"url(#{ident})")
            appearance = style_filter(self, layer, b)
            if layer.get("clip"):
                ident = self.ident("clip-mask")
                mask = node(
                    self.defs,
                    "mask",
                    id=ident,
                    maskUnits="userSpaceOnUse",
                    x=0,
                    y=0,
                    width=self.project.state["canvas"]["width"],
                    height=self.project.state["canvas"]["height"],
                    mask_type="alpha",
                )
                self.layer(mask, self.index[layer["clip"]])
                # Clip after styles, before overall layer opacity.
                wrapper = ET.Element(
                    f"{{{NS}}}g", {"opacity": group.attrib.pop("opacity"), "mask": f"url(#{ident})"}
                )
                wrapper.append(group)
                if appearance:
                    group.set("filter", appearance)
                parent.append(wrapper)
            elif appearance:
                group.set("filter", appearance)
                # Vixl applies opacity after layer styles.
                opacity = group.attrib.pop("opacity")
                outer = node(parent, "g", opacity=opacity)
                outer.append(group)
            else:
                parent.append(group)
        else:
            from .accessibility import decorative
            from .objects import export_identity

            if layer.get("alt") or decorative(layer) or export_identity(layer, self.index):
                # An image (or a layer drawn as one) that is described, decorative or part of an object keeps a
                # group of its own to carry that.
                parent = node(parent, "g", data_layer=layer["name"])
                self.describe(parent, layer)
            if layer.get("styles") or layer.get("clip"):
                from .render import layer_surface

                parent_layer = self.index.get(layer.get("parent"))
                size = (
                    (parent_layer["content_width"], parent_layer["content_height"])
                    if parent_layer
                    else (self.project.state["canvas"]["width"], self.project.state["canvas"]["height"])
                )
                bitmap(parent, layer_surface(self.project, layer, self.bounds, size, self.index))
            else:
                image = layer_ink(self.project, layer, b)
                bitmap(parent, image, *ink_origin(image, b))
            self.fallbacks.append(
                {
                    "layer": layer["name"],
                    "reason": self.text_reasons.get(layer["id"], fallback_reason(layer)),
                    "effects": [
                        e["name"]
                        for e in layer.get("effects", [])
                        if e.get("enabled", True) and (not supported({"effects": [e]}))
                    ],
                    "styles": list(styles(layer)) if not native_styles(layer, self.project.state) else [],
                }
            )


def export_svg(project, *, scale=1, variables=None, artboard=None, comp=None, svg_policy="appearance"):
    candidate = artboard_project(project, artboard, comp, variables)
    from .export_appearance import prepare

    candidate = prepare(candidate)
    c = candidate.state["canvas"]
    root = ET.Element(
        f"{{{NS}}}svg",
        {
            "width": str(c["width"] * scale),
            "height": str(c["height"] * scale),
            "viewBox": f"0 0 {c['width']} {c['height']}",
        },
    )
    exporter = Exporter(candidate, root)
    from .accessibility import document_title, page_alt, page_language

    lang = page_language(candidate.state)
    if lang:
        root.set("{http://www.w3.org/XML/1998/namespace}lang", lang)
    title, summary = document_title(candidate.state), page_alt(candidate.state)
    for position, (tag, text) in enumerate((("title", title), ("desc", summary))):
        if text:
            element = ET.Element(f"{{{NS}}}{tag}")
            element.text = text
            root.insert(len([c for c in list(root)[:position] if c.tag.endswith(("title", "desc"))]), element)
    if summary:
        root.set("role", "img")
    backdrop = [
        item
        for item in exporter.layers
        if exporter.visible(item)
        and (
            item["blend"] not in NATIVE_BLENDS
            or (
                item["type"] == "adjustment"
                and (
                    not supported(item)
                    or item["opacity"] != 1
                    or item.get("mask")
                    or item.get("clip")
                    or any(e["name"] == "contrast" and e.get("enabled", True) for e in item["effects"])
                )
            )
        )
    ]
    if backdrop:
        bitmap(root, render(candidate))
        exporter.fallbacks.extend(
            {
                "layer": item["name"],
                "reason": "backdrop-dependent blend or adjustment requires document rasterization",
                "effects": [e["name"] for e in item.get("effects", []) if e.get("enabled", True)],
            }
            for item in backdrop
        )
    else:
        fill, alpha = paint(c["background"], candidate.state)
        if alpha:
            node(root, "rect", width=c["width"], height=c["height"], fill=fill, fill_opacity=alpha)
        for layer in exporter.children.get(None, []):
            exporter.layer(root, layer)
    if exporter.fallbacks:
        if svg_policy == "strict":
            raise VixlError(
                "svg_raster_required",
                "SVG requires raster content; see fallback details",
                fallbacks=exporter.fallbacks,
            )
        node(root, "metadata").text = json.dumps({"vixl": {"raster_fallbacks": exporter.fallbacks}})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
