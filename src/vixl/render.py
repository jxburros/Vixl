"""Deterministic RGBA renderer with bounded layer caching and straight-alpha compositing."""

from collections import OrderedDict
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .assets import decode, read_bounded
from .constants import EFFECTS as EFFECTS
from .errors import VixlError, require
from .model import MAX_LAYERS, finite
from .variables import substitute as substitute, with_maps

BLENDS = ("normal", "multiply", "screen", "overlay", "darken", "lighten", "difference", "add", "subtract")
CANVAS_PRESETS = {
    "instagram-square": (1080, 1080),
    "instagram-post": (1080, 1080),
    "youtube-thumbnail": (1280, 720),
    "story": (1080, 1920),
    "discord": (512, 512),
}
EXPORT_PROFILES = {
    "instagram": {"size": (1080, 1080), "format": "JPEG", "quality": 90},
    "discord": {"size": (512, 512), "format": "PNG"},
    "print": {"format": "TIFF", "dpi": (300, 300)},
}


CSS_RGB = re.compile(
    r"rgba?\(\s*(\d+(?:\.\d+)?%?)[\s,]+(\d+(?:\.\d+)?%?)[\s,]+(\d+(?:\.\d+)?%?)"
    r"(?:\s*[,/]\s*(\d*(?:\.\d+)?%?))?\s*\)"
)


def _css_channel(text, alpha=False):
    if text.endswith("%"):
        return round(float(text[:-1]) * 2.55)
    value = float(text)
    return round(value * 255) if alpha and value <= 1 else round(value)


def color(value):
    if value == "transparent":
        return (0, 0, 0, 0)
    if isinstance(value, str):
        # CSS rgb()/rgba() with spaces or a 0–1 alpha, which models write constantly.
        match = CSS_RGB.fullmatch(value.strip().lower())
        if match:
            r, g, b = (min(255, _css_channel(match[i])) for i in (1, 2, 3))
            a = min(255, _css_channel(match[4], alpha=True)) if match[4] else 255
            return (r, g, b, a)
    try:
        return ImageColor.getcolor(value, "RGBA")
    except (ValueError, TypeError) as exc:
        if isinstance(value, str):
            # The full color language: lab/lch/oklab/oklch, color(display-p3 …), cmyk(),
            # kelvin(), color-mix(), lighten()/mix()/alpha() modifiers and xkcd names.
            from .colors import to_rgba8

            try:
                return to_rgba8(value)
            except VixlError as detailed:
                if "Invalid color syntax" not in str(detailed):
                    raise
        raise VixlError(
            "invalid_color",
            f"Invalid color {value!r}; use a name, #hex, rgb(), hsl(), oklch(), lab(), cmyk(), "
            "color(display-p3 …), color-mix() or a function such as lighten(@swatch, 10%)",
            requested=value,
        ) from exc


def font_for(project, layer):
    size = int(layer.get("size", 48))
    require(1 <= size <= 4096, "Font size must be 1–4096")
    font = layer.get("font", "DejaVuSans.ttf")
    font = project.state.get("fonts", {}).get(font, font)
    try:
        if font in project.assets:
            return ImageFont.truetype(io.BytesIO(project.assets[font]), size)
        # Only explicitly imported fonts or Pillow's bundled/system font lookup, never project paths.
        require("/" not in font and "\\" not in font, "Import custom fonts with text --font FILE")
        return ImageFont.truetype(
            str(Path(__file__).parent / "data" / font) if font == "DejaVuSans.ttf" else font, size
        )
    except OSError as exc:
        raise missing_font(project, layer.get("font", font)) from exc


def missing_font(project, name):
    fonts = sorted(project.state.get("fonts", {}))
    typography = project.state.get("typography") or {}
    roles = [role for role in ("heading", "body") if role in typography]
    known = ", ".join([*roles, *fonts]) if roles or fonts else "none yet"
    return VixlError(
        "missing_font",
        f"Font {name!r} not found. Registered fonts: {known}. Install one with "
        "vixl font install FAMILY --weight N or vixl font pair NAME, or import a font file; "
        "DejaVuSans.ttf is the proofing fallback.",
        field="font",
        allowed=[*roles, *fonts, "DejaVuSans.ttf"],
    )


def resolve_font(project, name):
    """A text layer's stored font and role for a requested font name, role or file."""
    if name is None:
        return "DejaVuSans.ttf", None
    typography = project.state.get("typography") or {}
    fonts = project.state.get("fonts", {})
    role = None
    if name in ("heading", "body"):
        # A role uses the proofing fallback until the document typography sets it.
        role, name = name, typography.get(name, "DejaVuSans.ttf")
        if name == "DejaVuSans.ttf":
            from .notices import warn

            warn(project, f"font role {role!r} has no typeface in this document, so text uses the bundled proofing "
                          "font (DejaVu Sans); choose type with vixl_fonts then vixl_font_pair (or vixl_font_install)")
    font = fonts.get(name, name)
    if font not in project.assets and Path(font).is_file():
        from .assets import read_bounded
        import hashlib
        data = read_bounded(font, project.limits.max_asset_bytes)
        font = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[font] = data
    if font in project.assets or font == "DejaVuSans.ttf":
        return font, role
    try:
        ImageFont.truetype(font, 12)
    except OSError as exc:
        raise missing_font(project, name) from exc
    return font, role


def document_variables(project):
    """The document's variables, plus each form field's current value under its key."""
    from .forms import current_values, has_fields

    maps = project.state.get("maps")
    if not has_fields(project):
        return with_maps(project.state.get("variables", {}), maps)
    fields = current_values(project)
    return with_maps({**{key: display for key, (_, display) in fields.items()}, **project.state.get("variables", {})},
                     maps)


def text_metrics(project, layer, variables=None):
    text = substitute(layer["text"], variables if variables is not None else document_variables(project))
    require(len(text) <= 100000, "Text exceeds length limit", "resource_limit")
    from .richtext import active

    if active(layer):
        from .richtext import measure as measure_rich

        return measure_rich(project, layer, variables)
    from .text import measure, font_data, UnsupportedText

    try:
        _, box = measure(font_data(project, layer), text, layer["size"], layer.get("spacing", 4), layer.get("align", "left"))
        stroke = layer.get("stroke_width", 0)
        box = (box[0] - stroke, box[1] - stroke, box[2] + stroke, box[3] + stroke)
        return max(1, math.ceil(box[2] - box[0])), max(1, math.ceil(box[3] - box[1])), box
    except UnsupportedText:
        pass
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font_for(project, layer),
        spacing=layer.get("spacing", 4),
        stroke_width=layer.get("stroke_width", 0),
    )
    return max(1, math.ceil(box[2] - box[0])), max(1, math.ceil(box[3] - box[1])), box


def rest_size(layer):
    if layer.get("repeat"):
        from .design_render import repeat_bounds

        return repeat_bounds(layer)
    return layer["width"], layer["height"]


def pivot_delta(layer):
    """Drawn-bounds origin minus stored x/y. Zero unless a ``pivot`` is set: then x/y place the
    unrotated box and rotation turns it about the pivot, which stays fixed on the canvas."""
    pivot = layer.get("pivot")
    if pivot is None:
        return 0.0, 0.0
    rw, rh = rest_size(layer)
    tw, th = transformed_size(layer)
    from .affine import linear, precise
    if precise(layer):
        v = np.array([(pivot[0] - .5) * rw, (pivot[1] - .5) * rh, 0])
        turned = linear(layer) @ v
        return (rw - tw) / 2 + v[0] - turned[0], (rh - th) / 2 + v[1] - turned[1]
    vx, vy = (pivot[0] - 0.5) * rw, (pivot[1] - 0.5) * rh
    angle = math.radians(layer.get("rotation", 0) % 360)
    co, si = math.cos(angle), math.sin(angle)
    return (rw - tw) / 2 + vx - (vx * co - vy * si), (rh - th) / 2 + vy - (vx * si + vy * co)


def stored_origin(layer, bounds):
    """The x/y that draws ``layer`` with its bounds' top-left at ``bounds[:2]``."""
    dx, dy = pivot_delta(layer)
    return bounds[0] - dx, bounds[1] - dy


def transformed_size(layer):
    w, h = rest_size(layer)
    from .affine import linear, precise
    if precise(layer):
        size = np.abs(linear(layer)[:2, :2]) @ [w, h]
        return float(size[0]), float(size[1])
    if layer.get("rotation", 0) % 360:
        # Pillow determines the exact expanded pixel bounds, without allocating the source raster.
        angle = math.radians(layer["rotation"] % 360)
        if layer["rotation"] % 90 == 0:
            return (h, w) if layer["rotation"] % 180 else (w, h)
        return math.ceil(abs(w * math.cos(angle)) + abs(h * math.sin(angle))) + 2, math.ceil(
            abs(w * math.sin(angle)) + abs(h * math.cos(angle))
        ) + 2
    return w, h


def resolved_layers(project, variables=None):
    from .design import resolve_color
    from .forms import current_values, has_fields

    fields = current_values(project) if has_fields(project) else {}
    # Each field's current value (its default, or a filled value) is also a ${key} variable.
    variables = {**document_variables(project), **(variables or {})}
    # Paint strokes can hold hundreds of thousands of points and are only read while rendering
    # and laying out, so the resolved copies share them instead of copying them each time.
    # Scalars are immutable, so only containers are copied (this runs for every layer on every resolve).
    layers = [
        {key: deepcopy(value) if key != "strokes" and isinstance(value, (dict, list, tuple)) else value
         for key, value in layer.items()}
        for layer in project.state["layers"]
    ]
    originals = {item["id"]: item for item in layers}
    for index, layer in enumerate(layers):
        if layer["type"] == "symbol":
            master = originals[project.state["symbols"][layer["symbol"]]]
            instance = deepcopy(master)
            for key in (
                "id",
                "name",
                "x",
                "y",
                "width",
                "height",
                "rotation",
                "pivot",
                "flip_x",
                "flip_y",
                "opacity",
                "blend",
                "visible",
                "constraints",
                "parent",
                "clip",
            ):
                if key in layer:
                    instance[key] = layer[key]
                elif key in ("parent", "clip", "pivot"):
                    instance.pop(key, None)
            instance["effects"] += layer["effects"]
            instance["styles"] = {**instance.get("styles", {}), **layer.get("styles", {})}
            instance["auto_size"] = False
            layer = layers[index] = instance
        for category in ("character", "paragraph"):
            if layer.get(category + "_style"):
                layer.update(deepcopy(project.state[category + "_styles"][layer[category + "_style"]]))
        for key in ("text", "asset"):
            if key in layer:
                layer[key] = substitute(layer[key], variables)
        if layer.get("code"):
            from .codes import resolve as resolve_code

            resolve_code(layer, variables)
        if layer["type"] == "text" and layer.get("rich"):
            from .richtext import fill_variables

            fill_variables(layer["rich"], variables)  # keeps the record matching the substituted text
        if layer.get("asset_variable"):
            name = layer["asset_variable"]
            require(name in variables, f"Undefined image variable: {name}", "missing_variable")
            layer["asset"] = str(variables[name])
            require(
                layer["asset"] in project.assets,
                "Image variables must reference embedded assets",
                "missing_asset",
            )
        for key in ("color", "fill", "start", "end", "stroke_color", "stroke"):
            if key in layer:
                layer[key] = resolve_color(layer[key], project.state, variables)
        blend = (layer.get("repeat") or {}).get("end", {})
        for key in ("fill", "color"):
            if key in blend:
                blend[key] = resolve_color(blend[key], project.state, variables)
        if layer["type"] == "text" and layer.get("auto_size", True):
            layer["width"], layer["height"], _ = text_metrics(project, layer, variables)
        if layer["type"] == "field":
            layer["value"] = list(fields.get(layer["field"]["key"], (None, "")))
        if layer.get("snap_to_pixel", project.state.get("snap_to_pixel", False)):
            layer["width"], layer["height"] = max(1, round(layer["width"])), max(1, round(layer["height"]))
        project.limits.size(layer["width"], layer["height"], vector=True)
    from .stacks import collapse

    collapse(layers)
    from .vector_paths import attach_ancestors
    attach_ancestors(layers)
    return layers


def resolve_layout(project, variables=None, layers=None):
    layers = layers if layers is not None else resolved_layers(project, variables)
    canvas = project.state["canvas"]
    bounds = {"canvas": (0, 0, canvas["width"], canvas["height"])}
    index = {key: layer for layer in layers for key in (layer["id"], layer["name"])}
    visiting = set()

    def edge(expression):
        if isinstance(expression, (int, float)):
            return finite(expression)
        match = re.fullmatch(
            r"(.+)\.(left|right|top|bottom|center-x|center-y)([+-]\d+(?:\.\d+)?)?", expression
        )
        require(match, f"Invalid constraint expression: {expression}")
        ref, anchor, offset = match.groups()
        if ref.startswith("guide:"):
            guide = project.state.get("guides", {}).get(ref[6:])
            require(guide is not None, f"Unknown guide: {ref}")
            from .guides import resolve_constraint

            return resolve_constraint(guide, anchor, ref) + float(offset or 0)
        b = bounds["canvas"] if ref == "canvas" else solve(ref)
        x, y, w, h = b
        return {
            "left": x,
            "right": x + w,
            "top": y,
            "bottom": y + h,
            "center-x": x + w / 2,
            "center-y": y + h / 2,
        }[anchor] + float(offset or 0)

    def solve(ref):
        require(ref in index, f"Unknown constraint target: {ref}")
        layer = index[ref]
        ident = layer["id"]
        if ident in bounds:
            return bounds[ident]
        require(ident not in visiting, "Layout constraints contain a cycle", "constraint_cycle")
        visiting.add(ident)
        w, h = transformed_size(layer)
        project.limits.size(w, h, vector=True)
        x, y = layer["x"], layer["y"]
        dx, dy = pivot_delta(layer)
        if layer.get("pivot") is not None:
            # Constraints place a pivoted layer's unrotated box.
            w, h = rest_size(layer)
        for anchor, expression in layer.get("constraints", {}).items():
            if isinstance(expression, str) and expression.startswith("canvas.") and layer.get("parent"):
                parent = index[layer["parent"]]
                old_canvas = bounds["canvas"]
                bounds["canvas"] = (0, 0, parent["content_width"], parent["content_height"])
                val = edge(expression)
                bounds["canvas"] = old_canvas
            else:
                val = edge(expression)
            if anchor == "left":
                x = val
            elif anchor == "right":
                x = val - w
            elif anchor == "top":
                y = val
            elif anchor == "bottom":
                y = val - h
            elif anchor == "center-x":
                x = val - w / 2
            elif anchor == "center-y":
                y = val - h / 2
            else:
                raise VixlError("invalid_constraint", f"Unknown anchor: {anchor}")
        snap = layer.get("snap_to_pixel", project.state.get("snap_to_pixel", False)) or layer["type"] in ("raster", "pixel", "paint", "field", "frame")
        bounds[ident] = (round(x + dx) if snap else x + dx, round(y + dy) if snap else y + dy, *transformed_size(layer))
        bounds[ident] = tuple(int(v) if float(v).is_integer() else v for v in bounds[ident])
        visiting.remove(ident)
        return bounds[ident]

    for layer in layers:
        solve(layer["id"])
    return {k: v for k, v in bounds.items() if k != "canvas"}


# Rec. 709 luma weights: temperature, tint and white balance keep a grey's luma as they shift it.
LUMA = np.array([0.2126, 0.7152, 0.0722])
# ln(gain) per mired of white-point shift, fitted to the blackbody locus near daylight (blue fixed).
MIRED_SLOPE = np.array([0.0045, 0.0025, 0.0])


def channel_gains(effect):
    """Per-channel multipliers for temperature, tint and white-balance, applied to encoded sRGB.

    Gains scale toward black, so shadows stay neutral. temperature moves the white point along
    the blackbody locus, 0.75 mired per unit: 100 is about 6500 K → 4400 K (warmer), -100 about
    6500 K → 12700 K (cooler). tint is the matching green–magenta shift: tint 100 reaches the same
    OKLab chroma on grey as temperature 100. Both keep a grey's luma. white-balance takes explicit
    ``gains`` [r, g, b] or a ``neutral`` color to turn grey (keeping its luma), and ``amount``
    (0–100, default 100) scales the correction."""
    from .constants import EFFECT_DEFAULTS

    name, value = effect["name"], effect.get("amount", EFFECT_DEFAULTS.get(effect["name"], 0))
    if name == "white-balance":
        if effect.get("gains") is not None:
            gains = np.array(effect["gains"], dtype=np.float64)
        elif effect.get("neutral") is not None:
            neutral = np.maximum(np.array(color(effect["neutral"])[:3], dtype=np.float64), 1) / 255
            gains = (LUMA @ neutral) / neutral
        else:
            gains = np.ones(3)
        return gains ** (value / 100)
    log = MIRED_SLOPE * 0.75 * value if name == "temperature" else np.array([0.0017, 0.0, 0.0017]) * value
    gains = np.exp(log)
    return gains / (LUMA @ gains)


def apply_effect(image, effect, project=None):
    from .constants import ARTISTIC_DEFAULTS

    if effect["name"] == "lookup":
        from .design_render import apply_lookup

        require(project is not None, "A lookup effect needs its document's LUTs")
        return apply_lookup(project, image, {"name": effect["lut"], "amount": effect.get("amount", 1)})
    if effect["name"] == "denoise":
        from .denoise import denoise_image

        return denoise_image(image, effect)
    if effect["name"] in ARTISTIC_DEFAULTS:
        from .artistic import artistic_filter

        return artistic_filter(image, effect)
    name = effect["name"]
    value = effect.get("amount", 0)
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    if name in ("auto-tone", "auto-color", "auto-contrast"):
        a = np.asarray(rgb, dtype=np.float32)
        visible = np.asarray(alpha) > 0
        if visible.any():
            samples = a[visible]
            if name == "auto-contrast":
                low, high = np.percentile(samples, (0.5, 99.5))
            else:
                low, high = np.percentile(samples, (0.5, 99.5), axis=0)
            span = high - low
            a = np.where(span > 0, (a - low) * 255 / np.maximum(span, 1), a)
            if name == "auto-color":
                means = a[visible].mean(axis=0)
                a *= np.mean(means) / np.maximum(means, 1)
            rgb = Image.fromarray(np.uint8(np.clip(a, 0, 255) + 0.5))
    elif name in ("brightness", "contrast", "saturation", "sharpen"):
        enhancer = {
            "brightness": ImageEnhance.Brightness,
            "contrast": ImageEnhance.Contrast,
            "saturation": ImageEnhance.Color,
            "sharpen": ImageEnhance.Sharpness,
        }[name]
        factor = max(0, 1 + value / 100) if name != "sharpen" else value
        rgb = enhancer(rgb).enhance(factor)
    elif name in ("blur", "gaussian-blur"):
        # Blur premultiplied alpha to avoid colored fringes around transparent pixels.
        return image.convert("RGBa").filter(ImageFilter.GaussianBlur(value)).convert("RGBA")
    elif name == "grayscale":
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    elif name == "invert":
        rgb = ImageOps.invert(rgb)
    elif name == "posterize":
        rgb = ImageOps.posterize(rgb, int(value))
    elif name == "threshold":
        rgb = ImageOps.grayscale(rgb).point(lambda x: 255 if x >= value else 0).convert("RGB")
    elif name == "hue":
        hsv = np.array(rgb.convert("HSV"))
        hsv[:, :, 0] = (hsv[:, :, 0].astype(float) + value * 255 / 360) % 256
        rgb = Image.fromarray(hsv, "HSV").convert("RGB")
    else:
        a = np.asarray(rgb, dtype=np.float32) / 255
        if name == "exposure":
            a *= 2**value
        elif name == "gamma":
            a = np.power(a, 1 / value)
        elif name in ("temperature", "tint", "white-balance"):
            a *= channel_gains(effect)
        elif name == "shadows":
            a += value / 100 * (1 - a) ** 2
        elif name == "highlights":
            a += value / 100 * a**2
        elif name == "levels":
            black, white = effect.get("black", 0), effect.get("white", 255)
            a = (a * 255 - black) / (white - black)
        elif name == "curves":
            points = effect["points"]
            a = np.interp(a, [p[0] / 255 for p in points], [p[1] / 255 for p in points])
        elif name in ("noise", "grain"):
            rng = np.random.default_rng(effect.get("seed", 0))
            a += rng.normal(0, value, (image.height, image.width, 1))
        elif name == "vignette":
            yy, xx = np.mgrid[-1 : 1 : complex(image.height), -1 : 1 : complex(image.width)]
            radius = effect.get("radius", 0.7)
            falloff = np.clip((np.sqrt(xx * xx + yy * yy) - radius) / max(0.01, 1.414 - radius), 0, 1)
            a *= 1 - effect.get("strength", value) * falloff[:, :, None]
        else:
            from .plugins import filter_plugin

            return filter_plugin(name)(image.copy(), deepcopy(effect))
        rgb = Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255))
    rgb.putalpha(alpha)
    return rgb


BLURS = ("blur", "gaussian-blur")
# Effects that change each pixel on its own, so giving a blur room around the layer leaves their
# result inside the layer's box unchanged.
PER_PIXEL = BLURS + (
    "brightness", "saturation", "hue", "exposure", "gamma", "temperature", "tint", "white-balance",
    "shadows", "highlights", "levels", "curves", "grayscale", "invert", "posterize", "threshold", "lookup",
)


def effect_margin(layer):
    """(x, y) pixels that the layer's enabled effects can move its content beyond its box.

    Blur spreads past the box when every effect from the first blur on is a blur or a per-pixel
    color change. A later effect that depends on the image's size or position (wave, noise,
    vignette, contrast, artistic filters) keeps the stack within the box, so it renders as it
    always has."""
    effects = [effect for effect in layer.get("effects") or [] if effect.get("enabled", True)]
    first = next((i for i, effect in enumerate(effects) if effect["name"] in BLURS), None)
    if first is None or any(effect["name"] not in PER_PIXEL for effect in effects[first:]):
        return 0, 0
    # Three standard deviations hold all but a fraction of a level of the spread.
    margin = sum(math.ceil(3 * abs(effect.get("amount") or 0)) for effect in effects[first:] if effect["name"] in BLURS)
    return margin, margin


def style_margin(layer):
    """(x, y) pixels that the layer's styles draw beyond its content."""
    mx = my = 0
    for name, settings in (layer.get("styles") or {}).items():
        if not settings.get("enabled", True):
            continue
        if name in ("drop-shadow", "outer-glow"):
            blur = math.ceil(3 * settings.get("blur", 8))
            dx, dy = (abs(settings.get("dx", 4)), abs(settings.get("dy", 4))) if name == "drop-shadow" else (0, 0)
            mx, my = max(mx, blur + math.ceil(dx)), max(my, blur + math.ceil(dy))
        elif name == "stroke":
            width = math.ceil(settings.get("width", 2))
            mx, my = max(mx, width), max(my, width)
    return mx, my


def extent(layer, bounds, children, memo):
    """(left, top, right, bottom) of everything a layer draws, in its parent's space: its box,
    widened by spreading effects and styles and by group children that reach past the box."""
    if layer["id"] in memo:
        return memo[layer["id"]]
    x, y, w, h = bounds[layer["id"]]
    left, top, right, bottom = x, y, x + w, y + h
    if layer["type"] == "group" and not layer.get("repeat"):
        cw, ch = layer["content_width"], layer["content_height"]
        u0, v0, u1, v1 = 0, 0, cw, ch
        for child in children.get(layer["id"], []):
            if child["visible"] and child["type"] != "adjustment":
                a, b, c, d = extent(child, bounds, children, memo)
                u0, v0, u1, v1 = min(u0, a), min(v0, b), max(u1, c), max(v1, d)
        if (u0, v0, u1, v1) != (0, 0, cw, ch):
            # Map the children's reach through the group's scale, flips and rotation about the
            # centre of its box, which is where the renderer turns it.
            from .affine import layer_matrix, matrix as affine_matrix
            transform = layer_matrix(layer, bounds[layer["id"]]) @ affine_matrix(layer["width"] / cw, 0, 0, layer["height"] / ch)
            for u, v in ((u0, v0), (u1, v0), (u0, v1), (u1, v1)):
                qx, qy, _ = transform @ [u, v, 1]
                left, top, right, bottom = min(left, qx), min(top, qy), max(right, qx), max(bottom, qy)
    ex, ey = effect_margin(layer)
    from .vector_strokes import margin as vector_margin
    vx, vy = vector_margin(layer)
    left, top, right, bottom = left-vx, top-vy, right+vx, bottom+vy
    sx, sy = style_margin(layer)
    memo[layer["id"]] = (left - ex - sx, top - ey - sy, right + ex + sx, bottom + ey + sy)
    return memo[layer["id"]]


def overflow(group, bounds, children, memo):
    """Symmetric (x, y) content pixels by which a group's children draw outside its content box.
    Groups do not clip: children that move, grow or rotate past the box stay visible."""
    if group.get("repeat"):
        return 0, 0
    ax = ay = 0
    for child in children.get(group["id"], []):
        if child["visible"] and child["type"] != "adjustment":
            left, top, right, bottom = extent(child, bounds, children, memo)
            ax = max(ax, -left, right - group["content_width"])
            ay = max(ay, -top, bottom - group["content_height"])
    return math.ceil(ax), math.ceil(ay)


def ink_margin(layer, bounds, children, memo):
    """(x, y) pixels a layer can draw beyond its layout box on each side, in its parent's space."""
    x, y, w, h = bounds[layer["id"]]
    left, top, right, bottom = extent(layer, bounds, children, memo)
    # One extra pixel covers resampling when an overflowing group is scaled or rotated.
    pad = 1 if layer["type"] == "group" and (left, top, right, bottom) != (x, y, x + w, y + h) else 0
    return math.ceil(max(x - left, right - x - w)) + pad, math.ceil(max(y - top, bottom - y - h)) + pad


def child_index(layers):
    children = {}
    for item in layers:
        children.setdefault(item.get("parent"), []).append(item)
    return children


def shift(bounds, layers, dx, dy):
    """Bounds with ``layers`` moved by (dx, dy): drawing a group's children onto a tile that
    includes the content they draw outside the group's box."""
    moved = dict(bounds)
    for item in layers:
        x, y, w, h = bounds[item["id"]]
        moved[item["id"]] = (x + dx, y + dy, w, h)
    return moved


def ink_origin(image, bounds):
    """Where a layer image lands: it is centred on the layer's box and may extend past it."""
    return math.floor(bounds[0] + (bounds[2] - image.width) / 2 + 1e-9), math.floor(bounds[1] + (bounds[3] - image.height) / 2 + 1e-9)


class LayerCache(OrderedDict):
    """Rendered layers by content key, least recently used first, bounded by count and bytes.
    Checks and timelines render a document many times; a cache smaller than the document's
    layers would evict each layer before it is reused."""

    def __init__(self, entries=2 * MAX_LAYERS, budget=384 * 1024 * 1024):
        super().__init__()
        self.entries, self.budget, self.bytes = entries, budget, 0

    def image(self, key):
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key].copy()

    def put(self, key, image):
        size = image.width * image.height * 4
        if size > self.budget // 4:
            return
        previous = self.pop(key, None)
        if previous is not None:
            self.bytes -= previous.width * previous.height * 4
        while self and (len(self) >= self.entries or self.bytes + size > self.budget):
            _, old = self.popitem(last=False)
            self.bytes -= old.width * old.height * 4
        self[key] = image.copy()
        self.bytes += size


def layer_image(project, layer, bounds):
    """The layer drawn within its layout box (blur and overflowing group children cropped)."""
    image = layer_ink(project, layer, bounds)
    if image.size != tuple(bounds[2:]):
        x, y = ink_origin(image, bounds)
        x, y = bounds[0] - x, bounds[1] - y
        image = image.crop((x, y, x + bounds[2], y + bounds[3]))
    return image


def layer_ink(project, layer, bounds):
    """The layer with everything it draws: centred on its box, larger where effects spread or
    group children reach past the box."""
    # The image depends on the layer's size, not on where it sits, so layers that only move
    # between frames reuse their cached image. Exceptions: an effect that reads a canvas
    # selection, and blur on a top-level layer, whose edge pixels continue at the canvas edge.
    placed = any(effect.get("selection") for effect in layer.get("effects") or []) or (
        not layer.get("parent") and any(effect_margin(layer))
    )
    content = layer if placed else {k: v for k, v in layer.items() if k not in ("x", "y", "constraints")}
    canvas = project.state["canvas"]
    extent_key = [*bounds, canvas["width"], canvas["height"]] if placed else list(bounds[2:])
    extent_key = [*extent_key, bounds[0] % 1, bounds[1] % 1]
    dependencies = [content, extent_key]
    if layer["type"] == "text":
        from .text import font_data
        data = font_data(project, layer)
        dependencies.append([hashlib.sha256(f).hexdigest() for f in (data if isinstance(data, tuple) else (data,))])
    elif layer["type"] == "paint":
        dependencies.append(project.state.get("brushes", {}))
    key = hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()
    linked = layer.get("linked")
    # A lookup effect reads its table from the document, which the key does not cover.
    cacheable = not linked and not any(e["name"] == "lookup" for e in layer.get("effects") or []) and not layer.get("_distort_groups") and layer["type"] not in ("group", "pathfinder", "link")
    cache = project._cache = project._cache if isinstance(project._cache, LayerCache) else LayerCache()
    if cacheable:
        cached = cache.image(key)
        if cached is not None:
            return cached
    disk = getattr(project, "_disk_cache", None)
    disk_key = None
    if disk and cacheable and layer["type"] != "symbol":
        from .render_cache import key_for
        disk_key = key_for(project, content, extent_key)
        cached = disk.get(disk_key, project.limits)
        if cached is not None:
            return cached
    kind = layer["type"]
    if layer.get("repeat"):
        from .design_render import repeat_image

        image = repeat_image(project, layer)
    elif kind in ("shape", "group", "frame", "pathfinder"):
        from .design_render import special_image

        image = special_image(project, layer)
    elif kind == "pixel":
        from .pixel import pixel_image

        image = pixel_image(project, layer)
    elif kind == "paint":
        from .brushes import paint_image

        image = paint_image(project, layer)
    elif kind == "raster":
        if linked:
            require(
                project.allow_linked,
                "Linked assets require --allow-linked or allow_linked=True",
                "linked_asset_disabled",
            )
            source = Path(linked)
            if not source.is_absolute():
                source = (project.path.parent if project.path else Path.cwd()) / source
            image = decode(read_bounded(source, project.limits.max_asset_bytes), project.limits)
        else:
            hint = None if layer.get("crop") else (layer["width"], layer["height"])
            image = project.image(layer["asset"], size_hint=hint)
        if layer.get("crop"):
            image = image.crop(tuple(layer["crop"]))
    elif kind == "text":
        from .design_render import text_image

        image = text_image(project, layer)
    elif kind == "solid":
        image = Image.new("RGBA", (math.ceil(layer["width"]), math.ceil(layer["height"])), color(layer["fill"]))
    elif kind == "field":
        from .forms import field_image

        image = field_image(project, layer)
    elif kind == "link":
        from .links import link_image

        image = link_image(project, layer)
    elif kind == "gradient":
        from .design_render import gradient_image

        image = gradient_image(project, layer, (math.ceil(layer["width"]), math.ceil(layer["height"])))
    else:
        raise VixlError("invalid_layer", f"Unsupported layer type: {kind}")
    from .scene import paper_image

    image = paper_image(image, layer)
    image = transform_layer_image(project, layer, bounds, image)
    if cacheable:
        cache.put(key, image)
    if disk:
        disk.put(disk_key, image)
    return image


def transform_layer_image(project, layer, bounds, image):
    """Apply the same geometry and appearance to a layer or an isolated group child."""
    kind = layer["type"]
    crisp = kind == "pixel" or (kind == "group" and pixel_group(project, layer))
    sampling = Image.Resampling.NEAREST if crisp else Image.Resampling.LANCZOS
    if kind == "group" and not layer.get("repeat") and image.size != (layer["content_width"], layer["content_height"]):
        # Children drawn outside the group's box scale and turn with the rest of it. Resample a
        # source box chosen so the scale is exactly the group's: its box lands where it would
        # without the overflow, which only adds whole output pixels around it.
        image = group_overflow_resize(layer, image, sampling)
    elif not layer.get("repeat") and not image.info.get("vixl_vector_overflow"):
        image = resize(image, (max(1, math.ceil(layer["width"])), max(1, math.ceil(layer["height"]))), sampling)
    from .affine import linear, precise
    # Effects run on the layer in its own frame, at its box size, before it is flipped, turned or
    # skewed: a blur, denoise or grain treats the content the same at any angle. Canvas-space
    # inputs (selections, the emboss light, canvas-edge blur room) are mapped into this frame.
    unturned = image.size
    image = layer_effects(project, layer, bounds, image)
    turn = Image.Resampling.NEAREST if crisp else Image.Resampling.BICUBIC
    if precise(layer):
        transform = linear(layer)
        out = np.abs(transform[:2, :2]) @ [image.width, image.height]
        size = tuple(max(1, math.ceil(v)) for v in out)
        transform[:2, 2] += np.array(size) / 2 - transform[:2, :2] @ [image.width / 2, image.height / 2]
        image = warp(image, size, tuple(np.linalg.inv(transform)[:2].ravel()), turn)
    if not precise(layer) and layer.get("flip_x"):
        image = ImageOps.mirror(image)
    if not precise(layer) and layer.get("flip_y"):
        image = ImageOps.flip(image)
    if not precise(layer) and layer.get("rotation", 0) % 360:
        image = rotate(image, -layer["rotation"], turn)
        # Match conservative layout bounds consistently, keeping anything drawn past them.
        target = (max(math.ceil(bounds[2]), image.width), max(math.ceil(bounds[3]), image.height))
        if image.size != target:
            padded = Image.new("RGBA", target)
            padded.alpha_composite(
                image, ((padded.width - image.width) // 2, (padded.height - image.height) // 2)
            )
            image = padded
    if any(effect_margin(layer)) and (precise(layer) or layer.get("rotation", 0) % 360):
        # Blur room added in the layer's frame turns into wider corners than the spread needs: the
        # blur reaches its margin past the turned box, which lies inside its bounds widened by it.
        m = effect_margin(layer)[0]
        reach = np.abs(linear(layer)[:2, :2]) @ unturned
        limit = [max(math.ceil(bounds[2 + i]), math.ceil(reach[i])) + 2 * m for i in (0, 1)]
        limit = [v + (image.size[i] - v) % 2 for i, v in enumerate(limit)]
        if limit[0] < image.width or limit[1] < image.height:
            left, top = max(0, (image.width - limit[0]) // 2), max(0, (image.height - limit[1]) // 2)
            image = image.crop((left, top, image.width - left, image.height - top))
    mask = layer.get("mask")
    if mask and mask.get("enabled", True):
        m = project.image(mask["asset"], "L").resize(tuple(math.ceil(v) for v in bounds[2:]), Image.Resampling.LANCZOS)
        if m.size != image.size:
            # The mask covers the layer's box; its edges continue over what is drawn past it.
            x, y = ink_origin(image, bounds)
            left, top = max(0, (image.width - m.width) // 2), max(0, (image.height - m.height) // 2)
            m = Image.fromarray(
                np.pad(
                    np.asarray(m),
                    ((top, image.height - m.height - top), (left, image.width - m.width - left)),
                    mode="edge",
                )
            )
        alpha = np.asarray(image.getchannel("A"), dtype=np.float32) * np.asarray(m, dtype=np.float32) / 255
        image.putalpha(Image.fromarray(np.uint8(alpha)))
    if layer["opacity"] != 1:
        image.putalpha(image.getchannel("A").point(lambda a: round(a * layer["opacity"])))
    # Carry fractional placement through rasterization instead of rounding the geometry.
    ox, oy = bounds[0] + (bounds[2] - image.width) / 2, bounds[1] + (bounds[3] - image.height) / 2
    # Use the same epsilon as ink_origin: affine arithmetic may land one ulp below an integer.
    fx, fy = max(0, ox - math.floor(ox + 1e-9)), max(0, oy - math.floor(oy + 1e-9))
    if not crisp and (fx > 1e-8 or fy > 1e-8):
        padded = Image.new("RGBA", (image.width + 2, image.height + 2))
        padded.paste(image, (1, 1))
        image = warp(padded, padded.size, (1, 0, -fx, 0, 1, -fy), Image.Resampling.BICUBIC)
    return image


def layer_effects(project, layer, bounds, image):
    """Run a layer's enabled effects, in stack order, on its image before the layer is flipped,
    turned or skewed. The image is centred on the layer's box."""
    from .affine import linear

    frame = linear(layer)[:2, :2]
    turned = not np.allclose(frame, np.eye(2))
    spread = effect_margin(layer)
    for effect in layer["effects"]:
        if not effect.get("enabled", True):
            continue
        if any(spread) and effect["name"] in BLURS:
            image, spread = blur_room(project, layer, bounds, image, spread), (0, 0)
        if effect["name"] == "emboss" and turned:
            # Keep the emboss light where it is on an upright layer, however this one is turned:
            # pass the canvas offset of the neighbour it subtracts (down-left) in the layer's frame.
            effect = {**effect, "_light": tuple(np.linalg.solve(frame, [-1.0, 1.0]))}
        changed = apply_effect(image, effect, project)
        if effect.get("selection"):
            mask = project.image(effect["selection"], "L")
            if turned:
                # Sample the canvas selection where each pixel of the layer's frame lands.
                centre = np.array([bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2])
                offset = centre - frame @ [image.width / 2, image.height / 2]
                data = (frame[0, 0], frame[0, 1], offset[0], frame[1, 0], frame[1, 1], offset[1])
                mask = mask.transform(image.size, Image.Transform.AFFINE, data, Image.Resampling.BILINEAR)
            else:
                x, y = ink_origin(image, bounds)
                mask = mask.crop((x, y, x + image.width, y + image.height))
            image = Image.composite(changed, image, mask)
        else:
            image = changed
    return image


def resize(image, size, sampling, box=None):
    """``Image.resize`` without the overshoot rim of Lanczos at hard edges (see ``antiring``)."""
    box = tuple(box or (0, 0, *image.size))
    result = image.resize(size, sampling, box=box)
    if sampling == Image.Resampling.NEAREST or result.size == image.size and box == (0, 0, *image.size):
        return result
    sx, sy = (box[2] - box[0]) / size[0], (box[3] - box[1]) / size[1]
    return antiring(image, result, (sx, 0, box[0], 0, sy, box[1]), max(sx, sy))


def warp(image, size, data, sampling):
    """An affine ``Image.transform`` (``data`` maps output to source) without overshoot."""
    result = image.transform(size, Image.Transform.AFFINE, data, sampling)
    if sampling == Image.Resampling.NEAREST:
        return result
    scale = float(np.linalg.svd(np.array(data).reshape(2, 3)[:, :2], compute_uv=False).max())
    return antiring(image, result, data, scale)


def rotate(image, angle, sampling):
    """``image.rotate(angle, sampling, expand=True)`` without overshoot: the same matrix and size."""
    w, h = image.size
    a = -math.radians(angle)
    co, si = round(math.cos(a), 15), round(math.sin(a), 15)

    def apply(x, y, c=0.0, f=0.0):
        return co * x + si * y + c, -si * x + co * y + f

    c, f = apply(-w / 2, -h / 2)
    c, f = c + w / 2, f + h / 2
    xs, ys = zip(*(apply(x, y, c, f) for x, y in ((0, 0), (w, 0), (w, h), (0, h))))
    nw, nh = math.ceil(max(xs)) - math.floor(min(xs)), math.ceil(max(ys)) - math.floor(min(ys))
    c, f = apply(-(nw - w) / 2, -(nh - h) / 2, c, f)
    return warp(image, (nw, nh), (co, si, c, -si, co, f), sampling)


def antiring(source, result, data, scale=1.0):
    """Clamp a resampled RGBA image to the colours and alphas of the source pixels under each
    output pixel's main kernel lobe. Lanczos and bicubic weights go negative beside a hard edge, so
    a flat shape gains a light or dark rim (in colours found nowhere in the source), and its
    translucent edge pixels, unpremultiplied, can come out brighter than the shape. ``data`` maps
    output pixels to source pixels; ``scale`` is source pixels per output pixel."""
    if source.mode != "RGBA" or result.mode != "RGBA":
        return result
    # Downscaling pools blocks of source pixels first, so the window stays a few cells wide.
    pool = max(1, int(scale))
    reach = max(1, math.ceil(scale / pool))
    pixels = np.asarray(source)
    # A transparent margin of cells (colour unknown: low 255, high 0) lets edges dilate outward.
    margin = reach + 2
    opaque = bool(pixels[..., 3].min())
    envelopes = []
    for blank, reduce in ((255, np.minimum), (0, np.maximum)):
        values = pixels
        if not opaque:
            values = pixels.copy()
            values[pixels[..., 3] == 0, :3] = blank
        for axis in (0, 1):
            pooled = values[::pool] if axis == 0 else values[:, ::pool]
            pooled = pooled.copy() if pool > 1 else pooled
            for k in range(1, pool):
                part = values[k::pool] if axis == 0 else values[:, k::pool]
                head = pooled[: len(part)] if axis == 0 else pooled[:, : part.shape[1]]
                reduce(head, part, out=head)
            values = pooled
        grid = np.full((values.shape[0] + 2 * margin, values.shape[1] + 2 * margin, 4), blank, np.uint8)
        grid[..., 3] = 0
        grid[margin:-margin, margin:-margin] = values
        spread = grid.copy()
        for axis in (0, 1):
            base = spread.copy()
            for step in range(1, reach + 1):
                spread = reduce(spread, np.roll(base, step, axis))
                spread = reduce(spread, np.roll(base, -step, axis))
        a, b, c, d, e, f = data
        cell = (a / pool, b / pool, c / pool + margin, d / pool, e / pool, f / pool + margin)
        envelopes.append(np.asarray(Image.fromarray(spread, "RGBA").transform(
            result.size, Image.Transform.AFFINE, cell, Image.Resampling.NEAREST, fillcolor=(blank, blank, blank, 0))))
    low, high = envelopes
    return Image.fromarray(np.minimum(np.maximum(np.asarray(result), low), high), "RGBA")


def blur_room(project, layer, bounds, image, margin):
    """Pad a layer image so blur spreads past its box: free edges fade into transparency, so a
    blurred shape keeps its outline. Where a top-level layer meets the canvas edge its edge pixels
    continue, as in an image editor, so a full-bleed photo does not fade at the canvas border."""
    mx, my = margin
    project.limits.size(image.width + 2 * mx, image.height + 2 * my)
    x, y = ink_origin(image, bounds)
    canvas = project.state["canvas"]
    from .affine import precise

    # The image is in the layer's own frame: a turned layer's edges are not the canvas's, and a
    # flipped layer's left edge lands on the right.
    left, top, right, bottom = (
        (x <= 0, y <= 0, x + image.width >= canvas["width"], y + image.height >= canvas["height"])
        if not layer.get("parent") and not precise(layer) and not layer.get("rotation", 0) % 360
        else (False, False, False, False)
    )
    if layer.get("flip_x"):
        left, right = right, left
    if layer.get("flip_y"):
        top, bottom = bottom, top
    pixels = np.pad(np.asarray(image), ((my, my), (mx, mx), (0, 0)))
    if left and mx:
        pixels[:, :mx] = pixels[:, mx : mx + 1]
    if right and mx:
        pixels[:, -mx:] = pixels[:, -mx - 1 : -mx]
    if top and my:
        pixels[:my] = pixels[my : my + 1]
    if bottom and my:
        pixels[-my:] = pixels[-my - 1 : -my]
    return Image.fromarray(pixels, "RGBA")


def group_overflow_resize(layer, image, sampling):
    """Scale a group tile that is larger than its content box (symmetric margins) to the group's
    size plus whole-pixel margins, at exactly the group's scale."""
    cw, ch = layer["content_width"], layer["content_height"]
    w, h = layer["width"], layer["height"]
    if (w, h) == (cw, ch):
        return image
    mx, my = (image.width - cw) / 2, (image.height - ch) / 2
    sx, sy = w / cw, h / ch
    ox, oy = math.ceil(mx * sx), math.ceil(my * sy)
    # The source box reaches ox / sx (≥ mx) beyond the content; pad so it lies inside the tile.
    px, py = math.ceil(ox / sx - mx), math.ceil(oy / sy - my)
    if px or py:
        padded = Image.new("RGBA", (image.width + 2 * px, image.height + 2 * py))
        padded.paste(image, (px, py))
        image, mx, my = padded, mx + px, my + py
    box = (mx - ox / sx, my - oy / sy, mx + cw + ox / sx, my + ch + oy / sy)
    return resize(image, (math.ceil(w + 2 * ox), math.ceil(h + 2 * oy)), sampling, box=box)


def pixel_group(project, group):
    """Whether a group holds only pixel layers, so scaling and rotating it stays nearest-neighbor."""
    from .design import descendants

    members = descendants(project, group["id"])
    kinds = {item["type"] for item in project.state["layers"] if item["id"] in members} - {"group"}
    return kinds == {"pixel"}


def composite(bottom, top, blend):
    if blend == "normal":
        return Image.alpha_composite(bottom, top)
    b, s = np.asarray(bottom, dtype=np.float32) / 255, np.asarray(top, dtype=np.float32) / 255
    cb, cs, ab, ass = b[:, :, :3], s[:, :, :3], b[:, :, 3:], s[:, :, 3:]
    if blend == "multiply":
        mixed = cb * cs
    elif blend == "screen":
        mixed = cb + cs - cb * cs
    elif blend == "overlay":
        mixed = np.where(cb <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))
    elif blend == "darken":
        mixed = np.minimum(cb, cs)
    elif blend == "lighten":
        mixed = np.maximum(cb, cs)
    elif blend == "difference":
        mixed = np.abs(cb - cs)
    elif blend == "add":
        mixed = np.minimum(1, cb + cs)
    elif blend == "subtract":
        mixed = np.maximum(0, cb - cs)
    else:
        raise VixlError("invalid_blend", f"Unknown blend mode: {blend}")
    alpha = ass + ab * (1 - ass)
    rgb = ((1 - ass) * ab * cb + (1 - ab) * ass * cs + ab * ass * mixed) / np.maximum(alpha, 1e-8)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((rgb, alpha), axis=2), 0, 1) * 255 + 0.5))


def layer_surface(project, layer, bounds, size, index, visiting=None):
    """Composite one layer and its clipping dependencies over transparent pixels."""
    from .design_render import styled_image
    from PIL import ImageChops

    visiting = set() if visiting is None else visiting
    ident = layer["id"]
    require(ident not in visiting, "Clipping contains a cycle")
    visiting.add(ident)
    tile = Image.new("RGBA", size)
    if layer["visible"]:
        b = bounds[ident]
        source = layer_ink(project, {**layer, "opacity": 1}, b)
        x, y = ink_origin(source, b)
        tile.alpha_composite(source, (x, y))
        if layer.get("styles"):
            # Styles reach a bounded distance from the layer; filter only that part of the tile.
            mx, my = (2 * margin + 4 for margin in style_margin(layer))
            box = (max(0, x - mx), max(0, y - my), min(size[0], x + source.width + mx), min(size[1], y + source.height + my))
            if box[0] < box[2] and box[1] < box[3]:
                tile.paste(styled_image(project, tile.crop(box), layer["styles"]), box[:2])
        if layer.get("clip"):
            mask = layer_surface(project, index[layer["clip"]], bounds, size, index, visiting)
            tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask.getchannel("A")))
        if layer["opacity"] != 1:
            tile.putalpha(tile.getchannel("A").point(lambda a: round(a * layer["opacity"])))
    visiting.remove(ident)
    return tile


def layer_canvas_surface(project, layer, bounds=None, index=None):
    """Render one drawable through its ancestors onto the document canvas.

    Used for diagnostic coverage: group clipping, scaling, rotation, opacity,
    masks and styles follow the normal renderer instead of assuming local
    coordinates are canvas coordinates.
    """
    from .design_render import styled_image
    from PIL import ImageChops

    index = index or {item["id"]: item for item in resolved_layers(project)}
    bounds = bounds or resolve_layout(project, layers=list(index.values()))
    canvas = project.state["canvas"]
    canvas_size = (canvas["width"], canvas["height"])
    children, memo = child_index(index.values()), {}

    def container(item):
        """The tile ``item`` is drawn on and the bounds placing it and its siblings there."""
        parent = index.get(item.get("parent"))
        if not parent:
            return canvas_size, bounds
        ax, ay = overflow(parent, bounds, children, memo)
        size = (math.ceil(parent["content_width"]) + 2 * ax, math.ceil(parent["content_height"]) + 2 * ay)
        return size, shift(bounds, children[parent["id"]], ax, ay) if ax or ay else bounds

    size, placed = container(layer)
    surface = layer_surface(project, layer, placed, size, index)
    parent = index.get(layer.get("parent"))
    while parent:
        ax, ay = overflow(parent, bounds, children, memo)
        if ax or ay:
            # The same tile the renderer transforms for this group.
            surface = trim_overflow(surface, (parent["content_width"], parent["content_height"]), ax, ay)
        size, placed = container(parent)
        tile = Image.new("RGBA", size)
        if parent["visible"]:
            b = placed[parent["id"]]
            if parent.get("repeat"):
                from .design_render import repeat_bounds, repeat_items

                repeated = Image.new("RGBA", repeat_bounds(parent))
                for item, x, y in repeat_items(parent, project.state):
                    source = transform_layer_image(project, item, (0, 0, item["width"], item["height"]), surface)
                    repeated.alpha_composite(source, (x, y))
                surface = repeated
            source = transform_layer_image(project, {**parent, "opacity": 1}, b, surface)
            tile.alpha_composite(source, ink_origin(source, b))
            if parent.get("styles"):
                tile = styled_image(project, tile, parent["styles"])
            if parent.get("clip"):
                mask = layer_surface(project, index[parent["clip"]], placed, size, index)
                tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask.getchannel("A")))
            if parent["opacity"] != 1:
                tile.putalpha(tile.getchannel("A").point(lambda a: round(a * parent["opacity"])))
        surface = tile
        parent = index.get(parent.get("parent"))
    return surface


def render_layers(project, parent=None, size=None, background="transparent", observe=None):
    """Composite the layers of ``parent`` (the canvas when None). ``observe`` maps layer IDs to
    callbacks that receive the layer's box region just before and just after it is drawn."""
    # Groups render their children through nested calls; resolve the document once per render.
    shared = getattr(project, "_resolution", None)
    if shared is not None and shared[0] is project.state:
        layers, bounds = shared[1], shared[2]
        outermost = False
    else:
        layers = resolved_layers(project)
        bounds = resolve_layout(project, layers=layers)
        project._resolution, outermost = (project.state, layers, bounds), True
    try:
        return _render_layers(project, layers, bounds, parent, size, background, observe)
    finally:
        if outermost:
            project._resolution = None


def render_members(project, members, region=None, background="transparent", include_hidden=False):
    """Composite the layers ``members`` (IDs sharing a parent) in document order, as the renderer
    draws them (styles, clipping, masks, opacity and blend modes among themselves), onto a tile.

    ``region`` is (left, top, width, height) in their parent's space, whole pixels; by default it is
    everything the members draw. Returns the tile and its (left, top). ``include_hidden`` draws
    hidden members too."""
    layers = resolved_layers(project)
    bounds = resolve_layout(project, layers=layers)
    members = set(members)
    picked = [item for item in layers if item["id"] in members]
    require(picked, "Nothing to draw")
    parent = picked[0].get("parent")
    require(all(item.get("parent") == parent for item in picked), "Layers must share a parent")
    if include_hidden:
        for item in picked:
            item["visible"] = True
    if region is None:
        children, memo, edges = child_index(layers), {}, []
        for item in picked:
            x, y, w, h = bounds[item["id"]]
            mx, my = ink_margin(item, bounds, children, memo)
            edges.append((x - mx, y - my, x + w + mx, y + h + my))
        # Two spare pixels hold antialiasing and rounding at the edges of styles and strokes.
        left, top = math.floor(min(e[0] for e in edges)) - 2, math.floor(min(e[1] for e in edges)) - 2
        right, bottom = math.ceil(max(e[2] for e in edges)) + 2, math.ceil(max(e[3] for e in edges)) + 2
        region = (left, top, right - left, bottom - top)
    left, top, width, height = region
    if parent is None and (left, top) != (0, 0) and any(
        any(effect_margin(item)) or any(effect.get("selection") for effect in item.get("effects") or []) for item in picked
    ):
        # Canvas-edge blur and selection-masked effects depend on where the layer sits on the canvas:
        # draw them in place, keeping what lies on the canvas.
        left, top = max(0, left), max(0, top)
        c = project.state["canvas"]
        right, bottom = min(c["width"], region[0] + width), min(c["height"], region[1] + height)
        require(left < right and top < bottom, "The layers draw nothing on the canvas")
        image, _ = render_members(project, [item["id"] for item in picked], (0, 0, right, bottom), background, include_hidden)
        return image.crop((left, top, right, bottom)), (left, top)
    placed = shift(bounds, [item for item in layers if item.get("parent") == parent], -left, -top)
    shared = getattr(project, "_resolution", None)
    project._resolution = (project.state, layers, bounds)
    try:
        image = _render_layers(project, layers, placed, parent, (width, height), background, None, members)
    finally:
        project._resolution = shared
    return image, (left, top)


def _render_layers(project, layers, bounds, parent, size, background, observe, members=None):
    c = project.state["canvas"]
    size = size or (c["width"], c["height"])
    index = {item["id"]: item for item in layers}
    children, memo = child_index(layers), {}
    ax = ay = 0
    if parent is not None and members is None:
        # A group's tile also holds whatever its children draw outside its box.
        ax, ay = overflow(index[parent], bounds, children, memo)
        if ax or ay:
            content = size
            size = (size[0] + 2 * ax, size[1] + 2 * ay)
            bounds = shift(bounds, children.get(parent, []), ax, ay)
            memo = {}  # Extents measured before the shift no longer match these bounds.
    size = tuple(math.ceil(v) for v in size)
    project.limits.size(*size)
    image = Image.new("RGBA", size, color(background))

    def surface(layer):
        return layer_surface(project, layer, bounds, size, index)

    def direct(layer):
        """Composite a plain layer only over its own bounds instead of a full-canvas tile."""
        b = bounds[layer["id"]]
        mx, my = ink_margin(layer, bounds, children, memo)
        if b[0] - mx >= size[0] or b[1] - my >= size[1] or b[0] + b[2] + mx <= 0 or b[1] + b[3] + my <= 0:
            return image
        source = layer_ink(project, {**layer, "opacity": 1}, b)
        x, y = ink_origin(source, b)
        left, top = max(0, x), max(0, y)
        right, bottom = min(size[0], x + source.width), min(size[1], y + source.height)
        if left >= right or top >= bottom:
            return image
        if (left, top, right, bottom) != (x, y, x + source.width, y + source.height):
            source = source.crop((left - x, top - y, right - x, bottom - y))
        if layer["opacity"] != 1:
            source.putalpha(source.getchannel("A").point(lambda a: round(a * layer["opacity"])))
        if layer["blend"] == "normal":
            image.alpha_composite(source, (left, top))
        else:
            box = (left, top, right, bottom)
            image.paste(composite(image.crop(box), source, layer["blend"]), box[:2])
        return image

    def draw(layer):
        nonlocal image
        if not layer.get("styles") and not layer.get("clip") and layer["type"] != "adjustment":
            return direct(layer)
        if layer["type"] == "adjustment":
            changed = image
            for effect in layer["effects"]:
                if effect.get("enabled", True):
                    filtered = apply_effect(changed, effect, project)
                    changed = (
                        Image.composite(
                            filtered, changed, project.image(effect["selection"], "L").resize(size)
                        )
                        if effect.get("selection")
                        else filtered
                    )
            mask = Image.new("L", size, round(255 * layer["opacity"]))
            if layer.get("mask") and layer["mask"].get("enabled", True):
                from PIL import ImageChops

                mask = ImageChops.multiply(mask, project.image(layer["mask"]["asset"], "L").resize(size))
            image = Image.composite(composite(image, changed, layer["blend"]), image, mask)
        else:
            tile = surface(layer)
            box = tile.getchannel("A").getbbox()
            if box:
                # Pixels the layer leaves transparent are unchanged by every blend mode.
                image.paste(composite(image.crop(box), tile.crop(box), layer["blend"]), box[:2])
        return image

    for layer in layers:
        if layer.get("parent") != parent or not layer["visible"] or (members is not None and layer["id"] not in members):
            continue
        if observe and layer["id"] in observe:
            box = pixel_box(bounds[layer["id"]], image.size)
            before = image.crop(box)
            image = draw(layer)
            observe[layer["id"]](before, image.crop(box))
        else:
            image = draw(layer)
    if ax or ay:
        image = trim_overflow(image, content, ax, ay)
    return image


def pixel_box(bounds, size):
    """The whole-pixel (left, top, right, bottom) box covering fractional layout ``bounds``, clamped
    to an image of ``size``. Every crop of a layer's pixels uses it so the images stay the same shape."""
    x, y, w, h = bounds
    return (max(0, math.floor(x + 1e-8)), max(0, math.floor(y + 1e-8)),
            min(size[0], math.ceil(x + w - 1e-8)), min(size[1], math.ceil(y + h - 1e-8)))


def trim_overflow(image, content, ax, ay):
    """Keep only the margin a group tile's pixels actually reach past its content box (symmetric),
    and none when they stay inside it. Layout bounds are conservative (a rotated child's box is
    padded), so a group whose members fit its box renders exactly as an unexpanded tile."""
    drawn = image.getchannel("A").getbbox()
    reach_x = max(0, ax - drawn[0], drawn[2] - ax - content[0]) if drawn else 0
    reach_y = max(0, ay - drawn[1], drawn[3] - ay - content[1]) if drawn else 0
    return image.crop((ax - reach_x, ay - reach_y, ax + content[0] + reach_x, ay + content[1] + reach_y))


def view_page(project, page=None):
    """The document as one page draws it (master layers underneath, page variables), or the
    document itself when it has no pages."""
    if project.state.get("pages") and not getattr(project, "_page_view", False):
        from .pages import page_project

        view = page_project(project, page)
        view._page_view = True
        return view
    return project


def render(project, variables=None, artboard=None, comp=None, page=None):
    from .design_render import artboard_project

    project = view_page(project, page)
    candidate = artboard_project(project, artboard, comp, variables)
    from .captions import prepare_bubbles

    candidate = prepare_bubbles(candidate)
    from .design import resolve_color

    disk = getattr(project, "_disk_cache", None)
    key = None
    if disk:
        from .render_cache import key_for
        key = key_for(candidate)
        cached = disk.get(key, project.limits)
        if cached is not None:
            return cached
    image = render_layers(
        candidate, background=resolve_color(candidate.state["canvas"]["background"], candidate.state)
    )
    from .scene import composite

    image = composite(image, candidate)
    if disk:
        disk.put(key, image)
    return image


def export(
    project,
    path=None,
    *,
    quality=None,
    scale=1,
    profile=None,
    variables=None,
    format=None,
    background="white",
    artboard=None,
    comp=None,
    sampling="smooth",
    svg_policy="appearance",
    color_space="rgb",
    icc_profile=None,
    intent="relative",
    black_generation=1.0,
    ink_limit=None,
    proof=False,
    simulate=None,
    dpi=None,
    icon_sizes=None,
    time=None,
    page=None,
    pages=None,
    pdf_content=None,
    report=None,
    fillable=False,
    values=None,
    fill_mode="flatten",
    alpha="auto",
    presenter=None,
    overwrite=False,
    width=480,
    columns=None,
    labels=True,
    title=None,
    max_bytes=None,
):
    """Render and encode. ``color_space='cmyk'`` separates JPEG/TIFF/PDF output (ICC profile
    bytes in ``icc_profile`` for press-accurate separation, else device-naive GCR with
    ``black_generation`` 0–1 and ``ink_limit`` in percent). ``proof`` soft-proofs RGB output
    through that separation; ``simulate`` previews a color-vision deficiency. ``alpha`` sets the
    channels of PNG, WEBP, TIFF and AVIF output: ``keep`` always writes RGBA, ``auto`` writes RGB
    when every pixel is opaque and RGBA otherwise (the file export default), and ``flatten``
    composites onto ``background`` and writes RGB (as JPEG and PDF always do). PDF is vector by
    default, RGB or CMYK: ``pdf_content='raster'`` writes one image per page instead, and ``report``
    receives ``content``, ``content_reason``, ``raster_fallbacks`` and ``page_size``. HTML output of a
    multi-page document is a self-contained slide presentation (see ``presenter.py``): ``presenter``
    is ``False`` for the plain single-image HTML, ``True`` for a presentation of any document, or
    a dict of options (theme, notes, slide_images, start, title). ``title`` is the PDF document title
    (default: the page's title layer, then the file name). ``max_bytes`` is a size budget: when the
    encoded file is larger, ``report['warnings']`` says so (the export still succeeds)."""
    require(isinstance(overwrite, bool), "overwrite must be true or false", field="overwrite")
    require(path is None or overwrite or not Path(path).exists(),
            "Export output already exists; pass overwrite=True to replace it", "output_exists", field="path")
    require(path is None or Path(path).suffix.lower() != ".vixl", "Cannot export over a Vixl project")
    quality_given = quality is not None  # None: not given (PDF images stay lossless, others use 90)
    quality = 90 if quality is None else quality
    require(alpha in ("auto", "keep", "flatten"), "alpha must be auto, keep or flatten", field="alpha")
    require(sampling in ("smooth", "nearest"), "Sampling must be smooth or nearest")
    require(color_space in ("rgb", "cmyk"), "Color space must be rgb or cmyk")
    if time is not None:
        # A single timeline frame: the document with every animated property applied at ``time``.
        from .timeline import default_timeline, parse_time, project_at

        timeline = project.state.get("timeline") or default_timeline()
        project = project_at(project, parse_time(time, timeline["duration"], timeline.get("markers")))
    require(svg_policy in ("appearance", "strict"), "SVG policy must be appearance or strict")
    from .pages import parse_pages

    pages = parse_pages(pages)
    if isinstance(page, str) and page.isdigit():
        page = int(page)
    suffix = Path(path).suffix.lower() if path else ""
    requested = (format or suffix.lstrip(".") or "PNG").upper()
    sheet = page == "all" or bool(pages) and requested not in ("PDF", "PPTX", "HTML", "HTM")
    require(page is None or not pages, "Pass page or pages, not both")
    if sheet:
        require(requested in ("PNG", "JPG", "JPEG", "WEBP", "TIFF", "TIF", "AVIF"),
                "Page contact sheets require a raster image format", field="page")
        require(not (artboard or comp or profile or time is not None),
                "Page contact sheets do not take artboard, comp, profile or time", field="page")
    require(fill_mode in ("flatten", "editable"), "fill_mode must be flatten or editable", field="fill_mode")
    if fillable or fill_mode == "editable":
        # A fillable PDF: Vixl's artwork with AcroForm fields on top (prefilled with ``values``).
        require((format or "").upper() == "PDF" or suffix == ".pdf" or (not format and not suffix),
                "Fillable forms export as PDF", field="fillable")
        require(color_space == "rgb", "Fillable PDFs are RGB; export CMYK without fillable", field="color_space")
        require(page is None or not pages, "Pass page or pages, not both")
        from .pdf_forms import export_fillable

        return export_fillable(project, path, pages=pages or ([page] if page is not None else None), values=values,
                               dpi=dpi, content=pdf_content or "vector", background=background, report=report)
    if variables:
        from .forms import all_fields, has_fields

        if has_fields(project):
            keys = {layer["field"]["key"] for _, layer in all_fields(project)} & set(variables)
            require(not keys, f"{', '.join(sorted(keys))} name form fields; pass field values in values, not variables",
                    field="variables")
    if values:
        # Flattened filling: the values are drawn into a throwaway copy that never touches the
        # document or the persistent render cache.
        from .forms import with_values

        project = with_values(project, values)
        if (format or "").upper() == "PDF" or suffix == ".pdf":
            pdf_content = pdf_content or "vector"
    from .presenter import export_presenter, wants_presenter

    html_name = (format or (suffix[1:] if suffix in (".html", ".htm") else "")).upper() in ("HTML", "HTM")
    # Options a presentation cannot honor keep a paged document's HTML export the single artwork page.
    artwork = bool(profile or artboard or comp or proof or simulate or icc_profile) or color_space != "rgb"
    if wants_presenter(False if presenter is None and artwork else presenter, html=html_name,
                       paged=bool(project.state.get("pages")), page=page):
        require(not artwork, "A presentation shows pages in RGB; profile, artboard, comp, proof, simulate and CMYK do not apply")
        require(page is None or not pages, "Pass page or pages, not both")
        data = export_presenter(project, pages=pages or ([page] if page is not None else None), options=presenter,
                                variables=variables, svg_policy=svg_policy, scale=scale, report=report)
        if path:
            Path(path).write_bytes(data)
        return data
    if (format or "").upper() == "PSD" or suffix == ".psd":
        require(not (pages or artwork), "PSD export writes one page in RGB; profile, artboard, "
                "comp, proof, simulate, CMYK and pages do not apply", field="format")
        from .psd_export import export_psd

        return export_psd(project, path, page=page, variables=variables, report=report)
    if (format or "").upper() == "PPTX" or suffix == ".pptx":
        require(not artwork, "PPTX keeps editable RGB slides; profile, artboard, comp, proof, simulate and CMYK do not "
                "apply (export a PNG or PDF to preview them)", field="format")
        from .pptx_export import export_pptx

        return export_pptx(project, path, pages=pages, dpi=dpi, report=report)
    wants_pdf = (format or "").upper() == "PDF" or suffix == ".pdf"
    paged = bool(project.state.get("pages"))
    requested_scale = scale
    raster_only = [name for name, used in (("profile", profile), ("artboard", artboard), ("comp", comp), ("proof", proof),
                                           ("simulate", simulate)) if used]
    if wants_pdf:
        require(pdf_content in (None, "vector", "raster"), "pdf_content must be vector or raster", field="pdf_content")
        require(not (raster_only and pdf_content == "vector"),
                f"pdf_content=vector cannot be combined with {', '.join(raster_only)}: those export the page as an image",
                field="pdf_content")
    if wants_pdf and not raster_only and (pdf_content or scale == 1):
        # Every PDF is written by Vixl's own writer: vector unless raster is asked for (exact physical
        # print pages, TrimBox and BleedBox, selectable text, CMYK). A scaled export is a larger
        # raster, so it keeps the image path below unless pdf_content says otherwise.
        require(page is None or not pages, "Pass page or pages, not both")
        from .pdf_export import export_pdf

        separation = None
        if color_space == "cmyk":
            from . import colors

            separation = dict(profile=colors.load_profile(icc_profile) if icc_profile is not None else None,
                              intent=intent, black=finite(black_generation, "black_generation", 0, 1),
                              ink_limit=None if ink_limit is None else ink_limit / 100, background=background)
        content = pdf_content or "vector"
        data = export_pdf(project, path, pages=pages or ([page] if page is not None else None), content=content,
                          dpi=dpi, background=background, color_space=color_space, separation=separation,
                          jpeg_quality=int(quality) if quality_given else None, title=title, report=report)
        if report is not None:
            report["content_reason"] = ("requested with pdf_content" if pdf_content else
                                        "default: vector, with images only for what PDF cannot draw (see raster_fallbacks)")
        return data
    if not sheet and (page is not None or paged):
        project = view_page(project, page)
    resample = Image.Resampling.NEAREST if sampling == "nearest" else Image.Resampling.LANCZOS
    require(path is None or Path(path).suffix.lower() != ".vixl", "Cannot export over a Vixl project")
    finite(scale, "scale", 0.01, 16)
    finite(quality, "quality", 1, 100)
    settings = {}
    if profile:
        require(profile in EXPORT_PROFILES, f"Unknown export profile: {profile}")
        settings = deepcopy(EXPORT_PROFILES[profile])
    requested_format = (
        format or settings.get("format") or (Path(path).suffix[1:] if path and Path(path).suffix.lower() in (".svg", ".html", ".htm") else "")
    ).upper()
    if requested_format in ("SVG", "HTML", "HTM"):
        require(not profile, "SVG export does not use raster export profiles")
        require(
            color_space == "rgb" and not (proof or simulate or icc_profile),
            "SVG export is RGB; use PDF, TIFF or JPEG for CMYK, and a raster or PDF export for proof and simulate",
        )
        from .svg import export_svg

        if requested_format in ("HTML", "HTM"):
            from .html_export import export_html
            export_svg = export_html
        data = export_svg(project, scale=scale, variables=variables, artboard=artboard, comp=comp, svg_policy=svg_policy)
        if path:
            Path(path).write_bytes(data)
        return data
    require(svg_policy == "appearance", "Strict SVG policy requires SVG output")
    if format:
        format = {"JPG": "JPEG", "TIF": "TIFF"}.get(format.upper(), format.upper())
    image = None
    if sheet:
        from .deck import contact_sheet

        image = contact_sheet(project, pages=pages, width=width, columns=columns, labels=labels, variables=variables)
    if image is None and scale > 1 and sampling != "nearest" and not (artboard or comp or settings.get("size")):
        # Enlarge by re-rendering a scaled copy, so text, shapes and vectors stay crisp.
        from .proxy import scaled_project

        project.limits.size(round(project.state["canvas"]["width"] * scale), round(project.state["canvas"]["height"] * scale))
        proxy = scaled_project(project, scale)
        if proxy is not None:
            image = render(proxy, variables)
            scale = 1
    if image is None:
        image = render(project, variables, artboard, comp)
    size = settings.pop("size", None)
    if size:
        image = ImageOps.contain(image, size, resample)
    target_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    project.limits.size(*target_size)
    if target_size != image.size:
        image = image.resize(target_size, resample)
    profile_format = settings.pop("format", None)
    fmt = (
        format
        or profile_format
        or (
            {
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".webp": "WEBP",
                ".tif": "TIFF",
                ".tiff": "TIFF",
                ".png": "PNG",
                ".avif": "AVIF",
                ".pdf": "PDF",
                ".ico": "ICO",
            }.get(Path(path).suffix.lower())
            if path
            else "PNG"
        )
    )
    require(fmt in ("PNG", "JPEG", "WEBP", "TIFF", "AVIF", "PDF", "ICO"),
            f"Unsupported export format {(Path(path).suffix if path and not format else format) or '(none)'!r}; use png, "
            "jpg, webp, tiff, avif, pdf, ico, svg, pptx, psd or html (audio: vixl_export_audio, or a .wav path on the "
            "CLI; animation: export-timeline)",
            field="format")
    from . import colors

    cms = None
    if icc_profile is not None:
        cms = colors.load_profile(icc_profile)
    require(ink_limit is None or 100 <= ink_limit <= 400, "Ink limit must be 100–400%")
    separation = dict(
        profile=cms,
        intent=intent,
        black=finite(black_generation, "black_generation", 0, 1),
        ink_limit=None if ink_limit is None else ink_limit / 100,
        background=background,
    )
    if simulate:
        image = colors.simulate_vision(image, simulate)
    if proof:
        image = colors.proof_image(image, **separation)
    canvas_dpi = project.state["canvas"].get("dpi")
    if dpi is not None:
        finite(dpi, "dpi", 36, 2400)
    effective_dpi = dpi or (canvas_dpi * scale if canvas_dpi else None)
    if effective_dpi and "dpi" not in settings:
        settings["dpi"] = (round(effective_dpi, 3), round(effective_dpi, 3))
    if color_space == "cmyk":
        require(fmt in ("JPEG", "TIFF", "PDF"), "CMYK export supports JPEG, TIFF and PDF" + (
            "; for an RGB soft proof of print colours drop --cmyk (color_space) and keep --proof" if proof else ""),
            field="color_space")
        require(not proof, "Choose either a CMYK separation or an RGB soft proof")
        image = colors.cmyk_image(image, **separation)
        if cms is not None:
            settings["icc_profile"] = cms.tobytes()
    elif icc_profile is not None:
        require(proof, "An ICC profile needs color_space='cmyk' or proof=True")
    if image.mode == "RGBA" and (fmt in ("JPEG", "PDF") or alpha == "flatten" and fmt != "ICO"):
        base = Image.new("RGBA", image.size, color(background))
        base.alpha_composite(image)
        image = base.convert("RGB")
    elif image.mode == "RGBA" and alpha == "auto" and fmt != "ICO" and image.getchannel("A").getextrema()[0] == 255:
        image = image.convert("RGB")  # an opaque canvas needs no alpha channel
    if fmt == "PDF":
        settings["resolution"] = settings.pop("dpi", (72, 72))[0]
        settings.pop("quality", None)
    if fmt == "ICO":
        sizes = icon_sizes or [16, 24, 32, 48, 64, 128, 256]
        require(
            isinstance(sizes, list) and 0 < len(sizes) <= 16 and all(isinstance(s, int) and 8 <= s <= 256 for s in sizes),
            "ICO sizes must be 1–16 integers from 8 to 256",
        )
        require(abs(image.width - image.height) <= 1, "ICO export needs a square canvas (try the favicon size)")
        settings = {"sizes": [(s, s) for s in sorted(set(sizes))]}
    else:
        require(icon_sizes is None, "icon_sizes applies to ICO export")
        settings.setdefault("quality", int(quality))
    stream = io.BytesIO()
    try:
        image.save(stream, format=fmt, **settings)
    except (OSError, KeyError) as exc:
        raise VixlError("codec_error", str(exc)) from exc
    data = stream.getvalue()
    if fmt == "PDF" and report is not None:
        report.update(content="raster", color_space=color_space, content_reason=(
            f"{', '.join(raster_only)} export the page as an image" if raster_only else
            f"scale {requested_scale:g} exports a larger image; pass pdf_content for a vector or raster PDF at its natural size"))
    if report is not None and fmt in ("PNG", "JPEG", "WEBP", "TIFF", "AVIF"):
        from .animation import still_size_warnings

        if warnings := still_size_warnings(project, fmt, len(data), max_bytes):
            report.setdefault("warnings", []).extend(warnings)
    if path:
        Path(path).write_bytes(data)
    return data
