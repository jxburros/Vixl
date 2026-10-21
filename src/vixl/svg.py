"""Self-contained SVG with vector logo geometry and explicit raster fallbacks."""

import base64
import hashlib
import json
import math
import re
from xml.sax.saxutils import escape
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
# Asset formats an <image> can show as they are, by asset file extension.
SHARED_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


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
        self.with_ids = True
        self.shared = {}

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

    def identity(self, layer):
        """``data-vixl-id``, the layer ID, on SVG that carries its document (IDs are random per document, so SVG
        without one, such as HTML exports, leaves them out and stays deterministic)."""
        return {"data-vixl-id": layer["id"]} if self.with_ids else {}

    def ident(self, prefix):
        self.counter += 1
        return f"vixl-{prefix}-{self.counter}"

    def share(self, parent, layer, image, bounds):
        """Draw an image layer with its asset's own bytes when it shows them pixel for pixel (native size, no
        effects), so the embedded document can point at this ``<image>`` instead of carrying the bytes again
        (``self.shared``: asset name to element id). Only SVG that carries its document does this; others keep
        the re-encoded PNG and stay byte-for-byte as before."""
        asset = layer.get("asset") if layer["type"] == "raster" and not layer.get("linked") else None
        mime = SHARED_TYPES.get(asset.rsplit(".", 1)[-1]) if isinstance(asset, str) else None
        if not (self.with_ids and mime and asset in self.project.assets and not layer.get("crop")):
            return False
        if asset not in self.shared:
            try:
                decoded = self.project.image(asset)
            except VixlError:
                return False
            if decoded.size != image.size or decoded.tobytes() != image.tobytes():
                return False
            self.shared[asset] = self.ident("asset")
            x, y = ink_origin(image, bounds)
            node(parent, "image", id=self.shared[asset], x=x, y=y, width=image.width, height=image.height,
                 href=f"data:{mime};base64," + base64.b64encode(self.project.assets[asset]).decode())
            return True
        return False

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
        if layer.get("fill_gradient") and (geometry["fill"] or (geometry["line"] and not attrs["stroke_opacity"])):
            w, h = layer["width"], layer["height"]
            attrs = {**attrs, "fill_opacity": 1, "fill": self.gradient(
                layer["fill_gradient"], (0, 0, w, h), (view[0] / w, view[1] / h) if view else None)}
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
        from .vector_strokes import NATIVE_MITER_LIMIT, active as stroke_active, inside_centre_line, primitives
        from .geometry import PATH_SHAPES, ROUNDED_BOXES, native_stroke_box, placed_path, stroke_inset

        sw, sh = layer["width"], layer["height"]
        shape = layer.get("shape", "rectangle")
        # A closed shape strokes inside its outline (geometry.stroke_inset), as PNG, PDF and PowerPoint
        # draw it: a native stroke along the outline shrunk by half a stroke where that is exact, else
        # the stroke band as a filled path.
        inset, pad = stroke_inset(layer, attrs["stroke_opacity"] > 0)
        styled = catalog_active(layer) or stroke_active(layer) or layer.get("distort") or layer.get("_distort_groups")
        inside = not styled and pad and shape not in (*PATH_SHAPES, "line") and not trim_range(layer)
        centre = None
        if inside:
            centre = native_stroke_box(layer, pad) if shape in ROUNDED_BOXES else inside_centre_line(layer, pad)
        if styled or (inside and centre is None):
            for path, color in primitives(layer, self.project):
                fill, alpha = paint(color, self.project.state)
                if path and getattr(color, "gradient", None):
                    fill, alpha = self.gradient(color.gradient, (0, 0, sw, sh)), 1
                if path and alpha:
                    node(parent, "path", d=path, fill=fill, fill_opacity=alpha)
            return
        if trim_range(layer):
            return self.trimmed(parent, layer, attrs)
        if layer.get("fill_gradient") and (shape != "line" or not attrs["stroke_opacity"]):
            # The gradient spans the shape's box; a path draws in its view box's units.
            scale = None
            if shape in PATH_SHAPES:
                view = shape_path(layer)[1]
                scale = (view[0] / sw, view[1] / sh)
            attrs.update(fill=self.gradient(layer["fill_gradient"], (0, 0, sw, sh), scale), fill_opacity=1)
        if inside:
            # The fill covers the whole shape, under the stroke.
            fill_only = {"fill": attrs["fill"], "fill_opacity": attrs["fill_opacity"]}
            stroke_only = {**attrs, "fill": "none"}
            del stroke_only["fill_opacity"]
            filled = attrs["fill_opacity"] > 0
            if shape == "ellipse":
                if filled:
                    node(parent, "ellipse", cx=sw / 2, cy=sh / 2, rx=sw / 2, ry=sh / 2, **fill_only)
                node(parent, "ellipse", cx=sw / 2, cy=sh / 2, rx=centre[2] / 2, ry=centre[3] / 2, **stroke_only)
            elif shape in ROUNDED_BOXES:
                x, y, w, h, rx = centre
                if filled:
                    node(parent, "rect", width=sw, height=sh, rx=0 if shape == "rectangle" else rx + pad, **fill_only)
                node(parent, "rect", x=x, y=y, width=w, height=h, rx=rx, **stroke_only)
            else:
                if filled:
                    path, view = shape_path(layer)
                    node(parent, "path", d=placed_path(path, view, (0, 0, sw, sh)), **fill_only)
                node(parent, "path", d=centre, stroke_miterlimit=NATIVE_MITER_LIMIT, **stroke_only)
        elif shape in ("rectangle", "rounded-rectangle", "capsule"):
            radius = layer.get("radius", min(sw, sh) / (2 if shape == "capsule" else 5)) if shape != "rectangle" else 0
            node(parent, "rect", width=sw, height=sh, rx=radius, **attrs)
        elif shape == "ellipse":
            node(parent, "ellipse", cx=sw / 2, cy=sh / 2, rx=sw / 2, ry=sh / 2, **attrs)
        elif shape == "line":
            attrs.update(
                stroke=attrs["stroke"] if attrs["stroke_opacity"] else attrs["fill"],
                stroke_opacity=attrs["stroke_opacity"] or attrs["fill_opacity"],
            )
            node(parent, "line", x1=inset, y1=inset, x2=sw - inset, y2=sh - inset, **attrs)
        elif shape not in PATH_SHAPES:
            # An unstroked polygon, star or shortcut, in pixels.
            path, view = shape_path(layer)
            node(parent, "path", d=placed_path(path, view, (0, 0, sw, sh)), **attrs)
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
            from .richtext import append_svg, fitted, ink_overhang, layout_box

            # The layout fills the layer's box (auto-sized text is stretched to it, as in PNG), widened by
            # the ink that reaches past it, so swashes and slants are not cut off.
            result = fitted(self.project, layer)
            width, height = layout_box(layer, result)
            left, top, right, bottom = (v + 1 if v > 0 else 0.0
                                        for v in ink_overhang(self.project, layer, result, (width, height)))
            sx, sy = layer["width"] / max(1e-6, width), layer["height"] / max(1e-6, height)
            nested = node(parent, "svg", x=f"{-left * sx:.6g}", y=f"{-top * sy:.6g}",
                          width=f"{(width + left + right) * sx:.6g}", height=f"{(height + top + bottom) * sy:.6g}",
                          viewBox=f"{-left:.6g} {-top:.6g} {width + left + right:.6g} {height + top + bottom:.6g}",
                          preserveAspectRatio="none", overflow="hidden")
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

    def gradient(self, settings, box, scale=None):
        """A gradient spanning ``box`` in the current user space; ``scale`` (sx, sy) maps that box into a user
        space drawn at another scale (a path's view box)."""
        ident = self.ident("gradient")
        x, y, w, h = box
        direction = settings.get("direction", "vertical")
        prefix = f"scale({scale[0]} {scale[1]}) " if scale else ""
        if direction == "radial":
            gradient = node(
                self.defs,
                "radialGradient",
                id=ident,
                gradientUnits="userSpaceOnUse",
                cx=0,
                cy=0,
                r=1,
                gradientTransform=prefix + f"translate({x + w * settings.get('center', [0.5, 0.5])[0]} {y + h * settings.get('center', [0.5, 0.5])[1]}) scale({w / 2} {h / 2})",
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
                **({"gradientTransform": prefix.strip()} if prefix else {}),
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
            from .pixel import finished

            rows, palette = finished(self.project, layer)
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
                    fill, alpha = paint(palette[row[x]], self.project.state)
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
        group = ET.Element(f"{{{NS}}}g", {"opacity": str(layer["opacity"]), "data-layer": layer["name"],
                                         **self.identity(layer)})
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
                parent = node(parent, "g", data_layer=layer["name"], **self.identity(layer))
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
                if not self.share(parent, layer, image, b):
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


def export_svg(project, *, scale=1, variables=None, artboard=None, comp=None, svg_policy="appearance", document=True):
    """The SVG bytes of one page. With ``document`` (the default) the SVG carries the Vixl document it shows in a
    ``<metadata id="vixl-document">`` element (``embedded_document``), so importing it gives back the same editable
    layers; every layer's group also names its layer ID in ``data-vixl-id``."""
    candidate = artboard_project(project, artboard, comp, variables)
    shown = candidate
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
    exporter.with_ids = document
    from .accessibility import page_language, resolved_title_alt

    lang = page_language(candidate.state)
    if lang:
        root.set("{http://www.w3.org/XML/1998/namespace}lang", lang)
    title, summary = resolved_title_alt(candidate)
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
    if not document:
        if exporter.fallbacks:
            node(root, "metadata").text = json.dumps({"vixl": {"raster_fallbacks": exporter.fallbacks}})
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    payload = embedded_document(shown, exporter.shared)
    payload["digest"] = hashlib.sha256(body).hexdigest()
    if exporter.fallbacks:
        payload = {"raster_fallbacks": exporter.fallbacks, **payload}
    text = escape(json.dumps({"vixl": payload}, ensure_ascii=False, separators=(",", ":")))
    end = body.rindex(b"</svg>")
    return body[:end] + f'<metadata id="{METADATA_ID}">{text}</metadata>'.encode() + body[end:]


METADATA_ID = "vixl-document"
METADATA = re.compile(rb'<metadata id="' + METADATA_ID.encode() + rb'">(.*?)</metadata>', re.S)
# Embedded archive members beyond this many bytes in total are left out of the SVG; the import then reads the SVG's
# own elements instead and says why.
EMBED_BUDGET = 32 * 1024 * 1024
DOCUMENT_FORMAT = 2


def embedded_document(project, shared=None):
    """The JSON payload that makes an exported SVG a lossless carrier of ``project`` (one page): the document state
    (a paged document's page view becomes a single-page state) and the archive members it references.

    * ``images``: members the SVG body already shows byte for byte, by the id of their ``<image>`` (``shared``,
      from ``Exporter.share``). The import reads them from there, so they are not stored twice.
    * ``fonts``: each font by identity (family, weight, italic, and where it comes from: ``bundled`` with the file
      name, ``google`` for a Google Fonts family, else ``file``), never its bytes. Font files are large and their
      licences rarely allow redistribution in a published SVG; the import finds the face again
      (``svg_import.resolve_fonts``).
    * ``assets``: every other member as base64. These are the ones with no element of their own in the body:
      images of hidden layers, images drawn with effects, crops or resizing, masks, brushes, patterns, LUTs.
    * ``omitted_assets`` when the ``assets`` exceed ``EMBED_BUDGET``."""
    from copy import deepcopy
    from .project import ASSET_REFERENCE, FORMAT_VERSION

    shared = shared or {}
    state = deepcopy(project.state)
    for key in ("pages", "page", "masters"):
        state.pop(key, None)
    text = json.dumps(state, ensure_ascii=False).encode()
    names = sorted(set(name.decode() for name in ASSET_REFERENCE.findall(text)) & set(project.assets),
                   key=lambda name: (len(project.assets[name]), name))
    assets, images, fonts, omitted, used = {}, {}, {}, [], 0
    for name in names:
        if name.startswith("fonts/"):
            fonts[name] = font_identity(project.assets[name], state.get("fonts") or {}, name)
            continue
        if name in shared:
            images[name] = shared[name]
            continue
        size = len(project.assets[name])
        if used + size > EMBED_BUDGET:
            omitted.append(name)
            continue
        used += size
        assets[name] = base64.b64encode(project.assets[name]).decode("ascii")
    payload = {"format": "vixl-svg-document", "version": DOCUMENT_FORMAT,
               "document": {"format_version": FORMAT_VERSION, "state": state}, "assets": dict(sorted(assets.items()))}
    if images:
        payload["images"] = dict(sorted(images.items()))
    if fonts:
        payload["fonts"] = dict(sorted(fonts.items()))
    if omitted:
        payload["omitted_assets"] = sorted(omitted)
    return payload


def font_identity(data, registry, name):
    """What the import needs to find a font file again without its bytes: family, weight, italic, the names the
    document registers it under, and its source."""
    from pathlib import Path

    from .text import BUNDLED_FONTS, font_style

    family, weight, italic = font_style(data)
    record = {"family": family, "weight": weight, "italic": italic,
              "registered": sorted(key for key, value in registry.items() if value == name)}
    digest = hashlib.sha256(data).hexdigest()
    folder = Path(__file__).parent / "data"
    bundled = next((file for file in BUNDLED_FONTS if hashlib.sha256((folder / file).read_bytes()).hexdigest() == digest),
                   None) if len(data) in {(folder / file).stat().st_size for file in BUNDLED_FONTS} else None
    if bundled:
        return {**record, "source": "bundled", "file": bundled}
    google = google_family(family, weight, italic, data)
    return {**record, "source": "google", "family": google} if google else {**record, "source": "file"}


STYLE_WORDS = {"thin", "hairline", "extralight", "ultralight", "light", "regular", "book", "normal", "medium",
               "semibold", "demibold", "bold", "extrabold", "ultrabold", "black", "heavy", "italic", "oblique"}


def google_family(family, weight, italic, data):
    """The Google Fonts family a font file is a style of, or None: a catalog family, or one whose style sits in the
    font cache with these bytes. Static styles from Google often name the style in the family ("Poppins
    SemiBold"), so trailing style words are tried away."""
    from .typefaces import _cache_dir, find_font, slug

    words = family.split()
    candidates = [family]
    while len(words) > 1 and words[-1].lower() in STYLE_WORDS:
        words.pop()
        candidates.append(" ".join(words))
    for candidate in candidates:
        entry = find_font(candidate)
        if entry:
            return entry["family"]
        cached = _cache_dir() / f"{slug(candidate)}-{weight}{'-italic' if italic else ''}.ttf"
        try:
            if cached.is_file() and cached.read_bytes() == data:
                return candidate
        except OSError:
            continue
    return None
