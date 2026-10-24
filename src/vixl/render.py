"""Deterministic RGBA renderer with bounded layer caching and straight-alpha compositing."""

from collections import OrderedDict
from copy import deepcopy
import io
import math
from pathlib import Path
import re
import threading

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .assets import decode, read_bounded
from .constants import BLENDS as BLENDS, EFFECTS as EFFECTS
from .errors import VixlError, require
from .hashing import content_hash
from .model import MAX_LAYERS, finite
from .profiling import ACTIVE as PROFILE
from .variables import RESOLVED, layer_text, substitute as substitute, with_maps

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
    roles = [role for role in typography if typography[role]]
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
    from .type_roles import is_role, role_font

    fonts = project.state.get("fonts", {})
    role = None
    if is_role(project, name):
        # A role or text stage uses the proofing fallback until the document typography sets it.
        role, name = name, role_font(project, name) or "DejaVuSans.ttf"
        if name == "DejaVuSans.ttf":
            from .notices import warn

            warn(project, f"font role {role!r} has no typeface in this document, so text uses the bundled proofing "
                          "font (DejaVu Sans); choose type with vixl_reference('fonts') then font-pair (or font-install)")
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


class resolving:
    """A read-only pass over the document (inspect, check, a full resolve): the document's variables are
    computed once for the whole pass instead of once per text layer, which scanned every layer for form
    fields and made measuring N text layers cost O(N²). Nothing may edit the document inside the pass."""

    def __init__(self, project):
        self.project = project

    def __enter__(self):
        self.owner = getattr(self.project, "_resolving", None) is None
        if self.owner:
            self.project._resolving = {}
        return self.project

    def __exit__(self, *exc):
        if self.owner:
            self.project.__dict__.pop("_resolving", None)


def document_variables(project):
    """The document's variables, plus each form field's current value under its key."""
    memo = getattr(project, "_resolving", None)
    if memo is None:
        return _document_variables(project)
    if "variables" not in memo:
        memo["variables"] = _document_variables(project)
    return dict(memo["variables"])


def _document_variables(project):
    from .forms import current_values, has_fields

    maps = project.state.get("maps")
    if not has_fields(project):
        return with_maps(project.state.get("variables", {}), maps)
    fields = current_values(project)
    return with_maps({**{key: display for key, (_, display) in fields.items()}, **project.state.get("variables", {})},
                     maps)


def text_metrics(project, layer, variables=None):
    from .lettering import view

    layer = view(project, layer, variables)
    text = layer_text(layer, variables if variables is not None else document_variables(project))
    require(len(text) <= 100000, "Text exceeds length limit", "resource_limit")
    from .richtext import active

    if active(layer):
        from .richtext import measure as measure_rich

        return measure_rich(project, layer, variables)
    from .text import measure, font_data, tab_stops, UnsupportedText

    try:
        # The same arguments as text.plan, so drawing the layer reuses this cached measurement.
        _, box = measure(font_data(project, layer), text, layer["size"], layer.get("spacing", 4),
                         layer.get("align", "left"), None, "greedy", tab_stops(layer, project))
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
    with resolving(project):
        return _resolved_layers(project, variables)


COLOR_KEYS = ("color", "fill", "start", "end", "stroke_color", "stroke")


def _needs_variables(layer):
    """Whether resolving ``layer`` can read the document's variables or form fields."""
    return (layer["type"] in ("text", "field", "symbol") or layer.get("code") or layer.get("asset_variable")
            or layer.get("character_style") or layer.get("paragraph_style")
            or any(isinstance(layer.get(key), str) and "${" in layer[key] for key in ("asset", "alt", *COLOR_KEYS))
            or (layer.get("repeat") and "${" in repr(layer["repeat"]))
            or (layer.get("fill_gradient") and "${" in repr(layer["fill_gradient"])))


def _resolved_layers(project, variables=None, subset=None):
    from .design import resolve_color
    from .forms import current_values, has_fields

    stored = project.state["layers"] if subset is None else subset
    if subset is None or variables or any(_needs_variables(layer) for layer in stored):
        fields = current_values(project) if has_fields(project) else {}
        # Each field's current value (its default, or a filled value) is also a ${key} variable.
        variables = {**document_variables(project), **(variables or {})}
    else:
        fields, variables = {}, {}
    # Paint strokes can hold hundreds of thousands of points and are only read while rendering
    # and laying out, so the resolved copies share them instead of copying them each time.
    # Scalars are immutable, so only containers are copied (this runs for every layer on every resolve).
    layers = [
        {key: deepcopy(value) if key != "strokes" and isinstance(value, (dict, list, tuple)) else value
         for key, value in layer.items()}
        for layer in stored
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
        for key in ("text", "asset", "alt"):
            if key in layer:
                layer[key] = substitute(layer[key], variables)
        if layer.get("code"):
            from .codes import resolve as resolve_code

            resolve_code(layer, variables)
        if layer["type"] == "text" and layer.get("rich"):
            from .richtext import fill_variables

            fill_variables(layer["rich"], variables)  # keeps the record matching the substituted text
        if layer["type"] == "text":
            layer[RESOLVED] = True
            from .lettering import apply as apply_lettering

            apply_lettering(layer)
        if layer.get("asset_variable"):
            name = layer["asset_variable"]
            require(name in variables, f"Undefined image variable: {name}", "missing_variable")
            layer["asset"] = str(variables[name])
            require(
                layer["asset"] in project.assets,
                "Image variables must reference embedded assets",
                "missing_asset",
            )
        for key in COLOR_KEYS:
            if key in layer:
                layer[key] = resolve_color(layer[key], project.state, variables)
        gradient = layer.get("fill_gradient")
        if isinstance(gradient, dict):
            for key in ("start", "end"):
                if key in gradient:
                    gradient[key] = resolve_color(gradient[key], project.state, variables)
            for stop in gradient.get("stops") or []:
                stop["color"] = resolve_color(stop["color"], project.state, variables)
        blend = (layer.get("repeat") or {}).get("end", {})
        for key in ("fill", "color"):
            if key in blend:
                blend[key] = resolve_color(blend[key], project.state, variables)
        if layer["type"] == "text" and layer.get("auto_size", True):
            layer["width"], layer["height"], _ = text_metrics(project, layer, variables)
        elif layer["type"] == "text" and "width" in layer.get("text_layout", {}) and "height" not in layer["text_layout"]:
            from .checks import boxed_text_need

            need = boxed_text_need(project, layer)
            if need:
                layer["height"] = max(1, need[1])
        if layer["type"] == "field":
            layer["value"] = list(fields.get(layer["field"]["key"], (None, "")))
        if layer.get("snap_to_pixel", project.state.get("snap_to_pixel", False)):
            layer["width"], layer["height"] = max(1, round(layer["width"])), max(1, round(layer["height"]))
        project.limits.size(layer["width"], layer["height"], vector=True)
    from .stacks import collapse

    collapse(layers, project)
    from .vector_paths import attach_ancestors
    attach_ancestors(layers)
    return layers


CONSTRAINT_REF = re.compile(r"(.+)\.(?:left|right|top|bottom|center-x|center-y)(?:[+-]\d+(?:\.\d+)?)?")


def layer_box(project, layer):
    """``resolve_layout(project)[layer["id"]]`` without resolving unrelated layers: only the layer, the layers its
    constraints refer to (and theirs), its parent when it is placed against the parent's canvas, and a symbol's
    master. A stack lays out its whole group, so a stack or a stack member among those resolves the document in
    full. Per-layer edits (move, resize, rotate ...) call this once per operation, so a batch no longer costs
    operations × layers."""
    layers = project.state["layers"]
    symbols = project.state.get("symbols", {})
    wanted, pending = {}, [layer]
    while pending:
        item = pending.pop()
        if item["id"] in wanted:
            continue
        wanted[item["id"]] = item
        parent = project.find_layer(item["parent"]) if item.get("parent") else None
        if "stack" in item or (parent is not None and "stack" in parent):
            return resolve_layout(project)[layer["id"]]
        refs = []
        for expression in item.get("constraints", {}).values():
            match = CONSTRAINT_REF.fullmatch(expression) if isinstance(expression, str) else None
            if match is None or match[1].startswith("guide:"):
                continue
            if match[1] != "canvas":
                refs.append(match[1])
            elif item.get("parent"):
                refs.append(item["parent"])  # canvas.* inside a group is the parent's content box.
        if item["type"] == "symbol":
            refs.append(symbols.get(item.get("symbol")))
        for ref in refs:
            found = project.find_layer(ref) if isinstance(ref, str) else None
            if found is None:
                return resolve_layout(project)[layer["id"]]  # Reports the broken reference as before.
            pending.append(found)
    subset = [item for item in layers if item["id"] in wanted] if len(wanted) > 1 else [layer]
    with resolving(project):
        resolved = _resolved_layers(project, subset=subset)
    return resolve_layout(project, layers=resolved)[layer["id"]]


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
    return tuple(math.floor(bounds[i]) + math.floor(offset + 1e-9) for i, offset in enumerate(placement(image, bounds)))


def placement(image, bounds):
    """The (x, y) offset of a layer image's corner from its box's whole-pixel corner. Computed from the box's
    fraction (exact for any whole-pixel shift), so a region or incremental tile, whose boxes are the canvas
    boxes moved by whole pixels, places and resamples each layer exactly as the whole canvas does."""
    return bounds[0] % 1 + (bounds[2] - image.width) / 2, bounds[1] % 1 + (bounds[3] - image.height) / 2


class LayerCache(OrderedDict):
    """Rendered layers by content key, least recently used first, bounded by count and bytes.
    Checks and timelines render a document many times; a cache smaller than the document's
    layers would evict each layer before it is reused."""

    def __init__(self, entries=2 * MAX_LAYERS, budget=384 * 1024 * 1024):
        super().__init__()
        self.entries, self.budget, self.bytes = entries, budget, 0
        self.lock = threading.RLock()  # Layers are drawn in parallel (render_pool).

    def image(self, key):
        with self.lock:
            cached = self.get(key)
            if cached is None:
                return None
            self.move_to_end(key)
        return cached.copy()

    def put(self, key, image):
        size = image.width * image.height * 4
        if size > self.budget // 4:
            return
        stored = image.copy()
        profile = PROFILE.get()
        with self.lock:
            previous = self.pop(key, None)
            if previous is not None:
                self.bytes -= previous.width * previous.height * 4
            while self and (len(self) >= self.entries or self.bytes + size > self.budget):
                _, old = self.popitem(last=False)
                self.bytes -= old.width * old.height * 4
                if profile is not None:
                    profile.count("layer_evictions")
            self[key] = stored
            self.bytes += size
        if profile is not None:
            profile.count("layer_writes")


def digest(value):
    """A short content key for ``value`` (JSON-serialisable)."""
    return content_hash(value, algo="blake2b", size=20)


def layer_cache(project):
    if not isinstance(project._cache, LayerCache):
        project._cache = LayerCache()
    return project._cache


def ink_identity(project, layer, bounds):
    """(key, content, extent, cacheable) of ``layer_ink``: what its pixels depend on."""
    # The image depends on the layer's size, not on where it sits, so layers that only move
    # between frames reuse their cached image. Exceptions: an effect that reads a canvas
    # selection, and blur on a top-level layer, whose edge pixels continue at the canvas edge.
    placed = any(effect.get("selection") for effect in layer.get("effects") or []) or (
        not layer.get("parent") and any(effect_margin(layer))
    )
    content = layer if placed else {k: v for k, v in layer.items() if k not in ("x", "y", "constraints")}
    canvas = project.state["canvas"]
    extent_key = [*bounds, canvas["width"], canvas["height"]] if placed else list(bounds[2:])
    extent_key = [*extent_key, bounds[0] % 1, bounds[1] % 1, *(["snapped"] if snap_placement(project) else [])]
    dependencies = [content, extent_key, *ink_inputs(project, layer)]
    cacheable = self_contained(layer) and layer["type"] != "link"
    if cacheable and layer["type"] in ("group", "pathfinder"):
        # A group's pixels are its children's: key it on the whole subtree, or leave it uncached.
        subtree = subtree_key(project, layer)
        cacheable = subtree is not None
        dependencies.append(subtree)
    key = digest(dependencies)
    return key, content, extent_key, cacheable


def ink_inputs(project, layer):
    """What a layer's pixels read from the document besides its own fields: its fonts or brushes."""
    if layer["type"] == "text":
        from .text import font_data, font_sha256
        data = font_data(project, layer)
        return [[font_sha256(f) for f in (data if isinstance(data, tuple) else (data,))]]
    if layer["type"] == "paint":
        return [project.state.get("brushes", {})]
    return []


def self_contained(layer):
    """Whether a layer's pixels follow from its fields and ``ink_inputs``: not a linked file, a lookup
    effect (its table lives in the document) or a shape warped by distorting groups above it."""
    return (not layer.get("linked") and not any(e["name"] == "lookup" for e in layer.get("effects") or [])
            and not layer.get("_distort_groups"))


def subtree_key(project, layer):
    """A digest of everything a group's (or pathfinder's) children draw: each descendant's resolved
    fields, its box in its parent's space and its ``ink_inputs``, in stacking order, plus the colours
    styles can name. None when the subtree cannot be cached (a descendant reads a linked file or a
    lookup table, clips to a layer outside the group, or the render has no shared resolution)."""
    state = project.state
    shared_state = [state.get("variables"), state.get("maps"), state.get("swatches")]
    memo = None
    try:
        if layer["type"] == "pathfinder":
            operands = layer.get("operands") or []
            if not all(self_contained(item) and item["type"] not in ("group", "link") for item in operands):
                return None
            return digest(["pathfinder", [ink_inputs(project, item) for item in operands], shared_state])
        shared = getattr(project, "_resolution", None)
        if shared is None or shared[0] is not state:
            return None
        layers, bounds = shared[1], shared[2]
        memo = project.__dict__.get("_subtree_memo")
        if memo is None or memo[0] is not layers:
            memo = project._subtree_memo = (layers, {}, child_index(layers))
        if layer["id"] in memo[1]:
            return memo[1][layer["id"]]
        children, members, pending = memo[2], set(), [layer["id"]]
        while pending:
            for child in children.get(pending.pop(), []):
                if child["id"] not in members:
                    members.add(child["id"])
                    pending.append(child["id"])
        parts = []
        for item in layers:
            if item["id"] not in members:
                continue
            if not self_contained(item) or item["type"] == "link" or (item.get("clip") and item["clip"] not in members):
                parts = None
                break
            parts.append([item, bounds.get(item["id"]), ink_inputs(project, item)])
        key = None if parts is None else digest(["group", parts, shared_state])
    except (TypeError, ValueError):
        key = None
    if memo is not None:
        memo[1][layer["id"]] = key
    return key


def ink_key(project, layer, bounds):
    """The key ``layer_ink`` caches ``layer`` under, or None when it is not cached."""
    key, _, _, cacheable = ink_identity(project, layer, bounds)
    return key if cacheable else None


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
    key, content, extent_key, cacheable = ink_identity(project, layer, bounds)
    cache = layer_cache(project)
    profile = PROFILE.get()
    if cacheable:
        cached = cache.image(key)
        if profile is not None:
            profile.count("layer_hits" if cached is not None else "layer_misses")
        if cached is not None:
            return cached
    elif profile is not None:
        profile.count("layer_uncacheable")
    disk = getattr(project, "_disk_cache", None)
    disk_key = None
    # Composited groups stay in memory: their key covers children the disk key does not read.
    if disk and cacheable and layer["type"] not in ("symbol", "group", "pathfinder"):
        from .render_cache import key_for
        disk_key = key_for(project, content, extent_key)
        cached = disk.get(disk_key, project.limits)
        if cached is not None:
            return cached
    if profile is None:
        image = draw_ink(project, layer, bounds)
    else:
        profile.enter()
        try:
            image = draw_ink(project, layer, bounds, profile)
        finally:
            profile.leave(layer)
    if cacheable:
        cache.put(key, image)
    if disk:
        disk.put(disk_key, image)
    return image


def draw_ink(project, layer, bounds, profile=None):
    """``layer_ink`` without its caches: draw the layer, then give it its geometry and appearance."""
    import time

    started = time.perf_counter() if profile is not None else 0
    linked = layer.get("linked")
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
    if profile is None:
        return transform_layer_image(project, layer, bounds, image)
    drawn = time.perf_counter()
    stages = profile.stack[-1][2]
    effects = stages["effects"]
    image = transform_layer_image(project, layer, bounds, image)
    profile.stage("draw", drawn - started)
    profile.stage("transform", time.perf_counter() - drawn - (stages["effects"] - effects))
    return image


def denoised_first(project, layer, bounds, image):
    """Run the denoise effects that open an enlarged photo's stack on its own pixels, before it is
    scaled up: upsampling smooths grain into blobs the noise estimate reads as detail, so a crop
    shown larger kept its grain. Returns the image and the layer with the rest of its stack."""
    effects = layer.get("effects", [])
    lead = 0
    while lead < len(effects) and (not effects[lead].get("enabled", True)
                                   or (effects[lead]["name"] == "denoise" and not effects[lead].get("selection"))):
        lead += 1
    if not any(effect.get("enabled", True) for effect in effects[:lead]):
        return image, layer
    image = layer_effects(project, {**layer, "effects": effects[:lead]}, bounds, image)
    return image, {**layer, "effects": effects[lead:]}


def transform_layer_image(project, layer, bounds, image):
    """Apply the same geometry and appearance to a layer or an isolated group child."""
    kind = layer["type"]
    crisp = kind == "pixel" or (kind == "group" and pixel_group(project, layer))
    sampling = Image.Resampling.NEAREST if crisp else Image.Resampling.LANCZOS
    stretched = False
    if kind == "group" and not layer.get("repeat") and image.size != (layer["content_width"], layer["content_height"]):
        # Children drawn outside the group's box scale and turn with the rest of it. Resample a
        # source box chosen so the scale is exactly the group's: its box lands where it would
        # without the overflow, which only adds whole output pixels around it.
        image = group_overflow_resize(layer, image, sampling)
    elif not layer.get("repeat") and not image.info.get("vixl_vector_overflow"):
        size = (max(1, math.ceil(layer["width"])), max(1, math.ceil(layer["height"])))
        if kind == "raster" and size[0] > image.width and size[1] > image.height:
            image, layer = denoised_first(project, layer, bounds, image)
        stretched = image.size != size
        image = resize(image, size, sampling)
    from .affine import linear, precise
    # Effects run on the layer in its own frame, at its box size, before it is flipped, turned or
    # skewed: a blur, denoise or grain treats the content the same at any angle. Canvas-space
    # inputs (selections, the emboss light, canvas-edge blur room) are mapped into this frame.
    unturned = image.size
    profile = PROFILE.get()
    if profile is None:
        image = layer_effects(project, layer, bounds, image)
    else:
        import time

        started = time.perf_counter()
        image = layer_effects(project, layer, bounds, image)
        profile.stage("effects", time.perf_counter() - started)
    turn = Image.Resampling.NEAREST if crisp else Image.Resampling.BICUBIC
    # Vector content (text, path shapes, ellipses, rounded rectangles) that is turned, skewed or moved to a
    # fractional place is drawn there from its outlines: resampling the drawn box softens every edge.
    # ``drawing`` maps the drawn image's pixels to the current image's while every step so far was exact
    # or redrawn; None once a step resampled or the layer has no outlines to redraw.
    drawing, redraw = (None if crisp or stretched else np.eye(3)), None

    def redrawn_to(size, transform):
        nonlocal drawing, redraw
        if drawing is not None and redraw is None:
            redraw = vector_redraw(project, layer)
        drawn = None if drawing is None else redrawn(redraw, size, svg_matrix(transform @ drawing), unturned)
        drawing = None if drawn is None else transform @ drawing
        return drawn

    if precise(layer):
        transform = linear(layer)
        out = np.abs(transform[:2, :2]) @ [image.width, image.height]
        size = tuple(max(1, math.ceil(v)) for v in out)
        transform[:2, 2] += np.array(size) / 2 - transform[:2, :2] @ [image.width / 2, image.height / 2]
        drawn = redrawn_to(size, transform)
        image = drawn if drawn is not None else warp(image, size, tuple(np.linalg.inv(transform)[:2].ravel()), turn)
    if not precise(layer) and layer.get("flip_x"):
        image = ImageOps.mirror(image)
        if drawing is not None:
            drawing = np.array([[-1.0, 0, image.width], [0, 1, 0], [0, 0, 1]]) @ drawing
    if not precise(layer) and layer.get("flip_y"):
        image = ImageOps.flip(image)
        if drawing is not None:
            drawing = np.array([[1.0, 0, 0], [0, -1, image.height], [0, 0, 1]]) @ drawing
    folded = False
    if not precise(layer) and layer.get("rotation", 0) % 360:
        turned = _turn(*image.size, -layer["rotation"])[4:]
        # Match conservative layout bounds consistently, keeping anything drawn past them. Pad evenly
        # on both sides: an odd margin would put the turned image half a pixel off its centre.
        target = (max(math.ceil(bounds[2]), turned[0]), max(math.ceil(bounds[3]), turned[1]))
        target = tuple(t + (t - s) % 2 for t, s in zip(target, turned))
        ox, oy = bounds[0] + (bounds[2] - target[0]) / 2, bounds[1] + (bounds[3] - target[1]) / 2
        fx, fy = max(0, ox - math.floor(ox + 1e-9)), max(0, oy - math.floor(oy + 1e-9))
        if snap_placement(project):
            fx, fy = round(fx), round(fy)
        mask = layer.get("mask")
        if not crisp and (fx > 1e-8 or fy > 1e-8) and not (mask and mask.get("enabled", True)):
            # Turn and place in one resampling, as the canvas grid sees the layer: the same layer drawn
            # at another place in its group's tile (a reparented layer, a grown group) gives the same pixels.
            size, shift = (target[0] + 2, target[1] + 2), (fx, fy)
            folded = True
        else:
            size, shift = target, (0.0, 0.0)
        a, b, c, d, e, f = _turn_data(*image.size, -layer["rotation"], size, shift)
        drawn = redrawn_to(size, np.linalg.inv(np.array([[a, b, c], [d, e, f], [0.0, 0.0, 1.0]])))
        image = drawn if drawn is not None else rotate(image, -layer["rotation"], turn, size, shift)
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
    # Carry fractional placement through rasterization instead of rounding the geometry.
    ox, oy = placement(image, bounds)
    # Use the same epsilon as ink_origin: affine arithmetic may land one ulp below an integer.
    fx, fy = max(0, ox - math.floor(ox + 1e-9)), max(0, oy - math.floor(oy + 1e-9))
    placed = None
    if not folded and (fx > 1e-8 or fy > 1e-8):
        placed = redrawn_to((image.width + 2, image.height + 2), np.array([[1.0, 0, 1 + fx], [0, 1, 1 + fy], [0, 0, 1]]))
    if placed is not None:
        image = placed
    if layer["opacity"] != 1:
        image = with_opacity(image, layer["opacity"])
    if not crisp and not folded and placed is None and (fx > 1e-8 or fy > 1e-8):
        padded = Image.new("RGBA", (image.width + 2, image.height + 2))
        if snap_placement(project):
            # A reduced preview: round to the nearest whole pixel instead of resampling the layer.
            padded.paste(image, (1 + round(fx), 1 + round(fy)))
            return padded
        padded.paste(image, (1, 1))
        image = warp(padded, padded.size, (1, 0, -fx, 0, 1, -fy), Image.Resampling.BICUBIC)
    return image


def vector_redraw(project, layer):
    """``design_render.vector_drawing`` for a layer whose drawn image reaches its place changed only by
    geometry (flip, turn, skew, placement) and opacity: no effects, mask, paper texture or repeat; else None."""
    mask = layer.get("mask")
    if (snap_placement(project) or layer.get("repeat") or layer.get("cut_paper") or (mask and mask.get("enabled", True))
            or any(effect.get("enabled", True) for effect in layer.get("effects") or [])):
        return None
    from .design_render import vector_drawing

    return vector_drawing(project, layer)


def redrawn(redraw, size, matrix, box):
    """The layer's vector content drawn into ``size`` by ``matrix`` from its drawn image of size ``box``
    (and cut a pixel past that box), or None to resample instead."""
    if redraw is None:
        return None
    from .text import UnsupportedText
    from .vector_raster import clip_to_box

    matrix = tuple(float(v) for v in matrix)
    try:
        return clip_to_box(redraw(size, matrix), matrix, *box)
    except UnsupportedText:
        return None


def svg_matrix(m):
    """A 3 x 3 affine matrix in SVG's order (a, b, c, d, e, f)."""
    return m[0, 0], m[1, 0], m[0, 1], m[1, 1], m[0, 2], m[1, 2]


def snap_placement(project):
    """Whether layers land on whole pixels instead of being resampled to their fractional place. Only
    reduced previews (``proxy.scaled_project(..., snap=True)``) set it; exports keep exact placement."""
    return getattr(project, "snap_placement", False)


def layer_effects(project, layer, bounds, image):
    """Run a layer's enabled effects, in stack order, on its image before the layer is flipped,
    turned or skewed. The image is centred on the layer's box."""
    if not any(effect.get("enabled", True) for effect in layer["effects"]):
        return image
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
        if effect["name"] == "watercolor" and not turned:
            # The canvas edge is not the edge of the wash: tell the filter which sides of the box reach it.
            canvas = project.state["canvas"]
            effect = {**effect, "_open": (bounds[0] <= 0, bounds[1] <= 0,
                                          bounds[0] + bounds[2] >= canvas["width"],
                                          bounds[1] + bounds[3] >= canvas["height"])}
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


def rotate(image, angle, sampling, size=None, shift=(0.0, 0.0)):
    """``image.rotate(angle, sampling, expand=True)`` without overshoot: the same matrix and size.
    ``size`` gives a larger output instead, with the image's centre ``shift`` pixels right of and below
    the output's centre (a fractional placement folded into the same resampling)."""
    w, h = image.size
    size = size or _turn(w, h, angle)[4:]
    co, si, c, _, _, f = _turn_data(w, h, angle, size, shift)
    if sampling != Image.Resampling.NEAREST:
        # The filter clamps to the image's edge pixels: art touching the edge would turn with a harder
        # edge than the same art drawn with room around it. Give it transparent room.
        padded = Image.new(image.mode, (w + 4, h + 4))
        padded.paste(image, (2, 2))
        image, c, f = padded, c + 2, f + 2
    return warp(image, size, (co, si, c, -si, co, f), sampling)


def _turn_data(w, h, angle, size, shift=(0.0, 0.0)):
    """The ``Image.transform`` affine data of ``rotate``: output pixels of ``size`` to source pixels."""
    co, si, c, f, _, _ = _turn(w, h, angle)

    def apply(x, y, c=0.0, f=0.0):
        return co * x + si * y + c, -si * x + co * y + f

    c, f = apply(-(size[0] - w) / 2 - shift[0], -(size[1] - h) / 2 - shift[1], c, f)
    return co, si, c, -si, co, f


def _turn(w, h, angle):
    """The rotation terms of ``rotate`` and the expanded size it gives a ``w`` × ``h`` image."""
    a = -math.radians(angle)
    co, si = round(math.cos(a), 15), round(math.sin(a), 15)

    def apply(x, y, c=0.0, f=0.0):
        return co * x + si * y + c, -si * x + co * y + f

    c, f = apply(-w / 2, -h / 2)
    c, f = c + w / 2, f + h / 2
    xs, ys = zip(*(apply(x, y, c, f) for x, y in ((0, 0), (w, 0), (w, h), (0, h))))
    return co, si, c, f, math.ceil(max(xs)) - math.floor(min(xs)), math.ceil(max(ys)) - math.floor(min(ys))


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
    if px > image.width or py > image.height:
        # Near-zero scale: the padding grows as 1 / scale. The group covers a pixel or two here, so
        # shrink the whole tile and centre it instead of padding it to an unbounded size.
        small = resize(image, (max(1, math.ceil(image.width * sx)), max(1, math.ceil(image.height * sy))), sampling)
        out = Image.new("RGBA", (math.ceil(w + 2 * ox), math.ceil(h + 2 * oy)))
        out.alpha_composite(small, ((out.width - small.width) // 2, (out.height - small.height) // 2))
        return out
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
    from PIL import ImageChops

    opaque_modes = {"multiply": ImageChops.multiply, "screen": ImageChops.screen,
                    "darken": ImageChops.darker, "lighten": ImageChops.lighter,
                    "difference": ImageChops.difference, "add": ImageChops.add,
                    "subtract": ImageChops.subtract}
    if (blend in opaque_modes and bottom.getchannel("A").getextrema() == (255, 255)
            and top.getchannel("A").getextrema() == (255, 255)):
        # Opaque inputs need no alpha equation. Pillow uses bounded C loops; multiply/screen
        # round at most one channel step differently from the float implementation below.
        return opaque_modes[blend](bottom.convert("RGB"), top.convert("RGB")).convert("RGBA")
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
    tile = Image.new("RGBA", size)
    patch, origin = layer_patch(project, layer, bounds, size, index, visiting)
    if patch is not None:
        tile.paste(patch, origin)
    return tile


def layer_patch(project, layer, bounds, size, index, visiting=None, limit=None):
    """``layer_surface`` without the transparent rest of the tile: the part of a ``size`` tile the layer,
    its styles and its clipping can change, and its (left, top), or (None, None) when it draws nothing.
    A full-size tile for each styled or clipped layer made them cost the whole canvas every time.
    ``limit`` (left, top, right, bottom) is where the tile's edge cuts the layer off when that is not the
    tile itself: a region of the canvas is styled as the whole canvas would be, then cropped."""
    from .design_render import styled_image
    from PIL import ImageChops

    visiting = set() if visiting is None else visiting
    ident = layer["id"]
    require(ident not in visiting, "Clipping contains a cycle")
    if not layer["visible"] or layer["opacity"] <= 0:
        return None, None
    visiting.add(ident)
    try:
        b = bounds[ident]
        source = layer_ink(project, {**layer, "opacity": 1}, b)
        x, y = ink_origin(source, b)
        mx, my = (2 * margin + 4 for margin in style_margin(layer)) if layer.get("styles") else (0, 0)
        limit = limit or (0, 0, *size)
        box = (max(limit[0], x - mx), max(limit[1], y - my),
               min(limit[2], x + source.width + mx), min(limit[3], y + source.height + my))
        if box[0] >= box[2] or box[1] >= box[3]:
            return None, None
        if layer.get("styles"):
            key = styled_key(project, layer, b, box, (x, y))
            cache = layer_cache(project)
            patch = cache.image(key) if key else None
            profile = PROFILE.get()
            if profile is not None:
                profile.count("styled_hits" if patch is not None else "styled_misses")
            if patch is None:
                import time

                started = time.perf_counter()
                patch = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
                patch.alpha_composite(source, (x - box[0], y - box[1]))
                patch = styled_image(project, patch, layer["styles"])
                if key:
                    cache.put(key, patch)
                if profile is not None:
                    profile.phase("styles", time.perf_counter() - started)
        else:
            patch = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
            patch.alpha_composite(source, (x - box[0], y - box[1]))
        if layer.get("clip"):
            clip, at = layer_patch(project, index[layer["clip"]], bounds, size, index, visiting, limit)
            mask = Image.new("L", patch.size)
            if clip is not None:
                mask.paste(clip.getchannel("A"), (at[0] - box[0], at[1] - box[1]))
            patch.putalpha(ImageChops.multiply(patch.getchannel("A"), mask))
        patch = with_opacity(patch, layer["opacity"])
    finally:
        visiting.remove(ident)
    return patch, box[:2]


def styled_key(project, layer, bounds, box, origin):
    """The cache key of a styled patch: the layer's pixels, its styles and the colours they can name,
    and where the patch sits around the pixels (the canvas edge clips it)."""
    ink = ink_key(project, {**layer, "opacity": 1}, bounds)
    if ink is None:
        return None
    state = project.state
    return digest(["styled", ink, layer["styles"], [box[0] - origin[0], box[1] - origin[1], box[2] - box[0], box[3] - box[1]],
                   state.get("variables"), state.get("maps"), state.get("swatches")])


def opacity_table(opacity):
    """The 256-entry table that scales an alpha channel by ``opacity`` (as ``round(a * opacity)``)."""
    table = OPACITY_TABLES.get(opacity)
    if table is None:
        table = [round(a * opacity) for a in range(256)]
        with OPACITY_LOCK:  # Documents render in parallel threads.
            if len(OPACITY_TABLES) >= 4096:
                OPACITY_TABLES.clear()
            OPACITY_TABLES[opacity] = table
    return table


OPACITY_TABLES = {}
OPACITY_LOCK = threading.Lock()


def with_opacity(image, opacity):
    """``image`` (RGBA, changed in place) with its alpha scaled by ``opacity``."""
    if opacity != 1:
        image.putalpha(image.getchannel("A").point(opacity_table(opacity)))
    return image


def layer_canvas_alpha(project, layer, box, bounds, index):
    """``layer_canvas_surface(...).getchannel("A").crop(box)`` for ``box`` inside the canvas, without drawing a
    canvas-sized surface when the layer is drawn straight onto the canvas (no group, styles or clipping): the
    overlap check asks this of every text layer, and a full-canvas surface each made it slow on large canvases."""
    if layer.get("parent") or layer.get("styles") or layer.get("clip"):
        return layer_canvas_surface(project, layer, bounds, index).getchannel("A").crop(box)
    left, top, right, bottom = box
    alpha = Image.new("L", (right - left, bottom - top))
    if not layer["visible"]:
        return alpha
    b = bounds[layer["id"]]
    source = layer_ink(project, {**layer, "opacity": 1}, b)
    x, y = ink_origin(source, b)
    # The part of the source inside the box, where the full surface would have composited it.
    crop = (max(left, x), max(top, y), min(right, x + source.width), min(bottom, y + source.height))
    if crop[0] < crop[2] and crop[1] < crop[3]:
        # Composited over transparent pixels, the surface's alpha is the source's own.
        part = source.crop((crop[0] - x, crop[1] - y, crop[2] - x, crop[3] - y))
        alpha.paste(part.getchannel("A") if part.mode == "RGBA" else part.convert("RGBA").getchannel("A"),
                    (crop[0] - left, crop[1] - top))
    if layer["opacity"] != 1:
        alpha = alpha.point(opacity_table(layer["opacity"]))
    return alpha


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
                tile = with_opacity(tile, parent["opacity"])
        surface = tile
        parent = index.get(parent.get("parent"))
    return surface


def resolved(project):
    """``resolved_layers`` and ``resolve_layout`` of a render, timed when a profile is recording."""
    profile = PROFILE.get()
    if profile is None:
        layers = resolved_layers(project)
        return layers, resolve_layout(project, layers=layers)
    import time

    started = time.perf_counter()
    layers = resolved_layers(project)
    laid = time.perf_counter()
    bounds = resolve_layout(project, layers=layers)
    profile.phase("resolve", laid - started)
    profile.phase("layout", time.perf_counter() - laid)
    return layers, bounds


def render_layers(project, parent=None, size=None, background="transparent", observe=None):
    """Composite the layers of ``parent`` (the canvas when None). ``observe`` maps layer IDs to
    callbacks that receive the layer's box region just before and just after it is drawn."""
    # Groups render their children through nested calls; resolve the document once per render.
    shared = getattr(project, "_resolution", None)
    if shared is not None and shared[0] is project.state:
        layers, bounds = shared[1], shared[2]
    else:
        # Drawing is a read-only pass too: text layers look up the document's variables, which
        # otherwise rescans every layer for form fields once per text layer.
        with resolving(project):
            layers, bounds = resolved(project)
            project._resolution = (project.state, layers, bounds)
            try:
                return _render_layers(project, layers, bounds, parent, size, background, observe)
            finally:
                project._resolution = None
    return _render_layers(project, layers, bounds, parent, size, background, observe)


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
        with resolving(project):
            image = _render_layers(project, layers, placed, parent, (width, height), background, None, members)
    finally:
        project._resolution = shared
    return image, (left, top)


PREFETCH_MIN_PIXELS = 1_000_000  # Summed area of the layers worth drawing ahead before a pool pays for itself.
_POOL = [None, 0]  # The render pool and its size.
_POOL_LOCK = threading.Lock()
_IN_POOL = threading.local()


def render_threads():
    """Threads that draw layers ahead of the compositor: ``VIXL_RENDER_THREADS`` (0 or 1 turns it off), else up to
    8, one per core."""
    import os

    value = os.environ.get("VIXL_RENDER_THREADS", "").strip()
    try:
        return max(0, int(value)) if value else min(8, os.cpu_count() or 1)
    except ValueError:
        return 0


def render_pool():
    """The process's layer-drawing pool, or None when it is off."""
    from concurrent.futures import ThreadPoolExecutor

    threads = render_threads()
    if threads < 2:
        return None
    with _POOL_LOCK:
        if _POOL[0] is None or _POOL[1] != threads:
            if _POOL[0] is not None:
                _POOL[0].shutdown(wait=False)
            _POOL[0], _POOL[1] = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="vixl-render"), threads
        return _POOL[0]


def worth_prefetching(layer):
    """Whether drawing ``layer`` is mostly work that releases the GIL (Pillow filters for effects and styles, image
    decoding and resampling, numpy gradients), so drawing it on another thread overlaps with the rest. Plain
    vector shapes and text rasterise through resvg, which holds the GIL: threads would only add overhead."""
    if layer["type"] in ("adjustment", "link") or layer["opacity"] <= 0:
        return False
    if layer.get("styles") or any(effect.get("enabled", True) for effect in layer.get("effects") or []):
        return True
    return layer["type"] in ("raster", "gradient", "paint", "pixel", "frame") or bool(layer.get("fill_gradient"))


class Prefetch:
    """Draws the next layers worth drawing ahead (``worth_prefetching``) on the render pool while the compositor
    works through the stack in order; at most two per thread are in flight, so memory stays bounded. Only the
    drawing is parallel: compositing keeps the document order, so the pixels are those of a sequential render."""

    def __init__(self, work, candidates):
        self.work, self.queue, self.pending = work, list(reversed(candidates)), {}
        self.pool = render_pool() if candidates else None
        self.window = 2 * render_threads()

    def refill(self):
        import contextvars

        while self.pool is not None and self.queue and len(self.pending) < self.window:
            layer = self.queue.pop()
            context = contextvars.copy_context()
            self.pending[layer["id"]] = self.pool.submit(context.run, self.run, layer)

    def run(self, layer):
        _IN_POOL.active = True
        try:
            return self.work(layer)
        finally:
            _IN_POOL.active = False

    def take(self, layer):
        """The drawn layer, if it was drawn ahead; ``None`` otherwise (the caller draws it)."""
        future = self.pending.pop(layer["id"], None)
        if future is None:
            return None
        try:
            return future.result()
        finally:
            self.refill()

    def close(self):
        for future in self.pending.values():
            future.cancel()


def _render_layers(project, layers, bounds, parent, size, background, observe, members=None, limit=None, drawn=None):
    """``drawn``, a dict, receives each layer's (left, top, right, bottom) tile box that it drew into, before
    the tile's edge cut it."""
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

    def patch_of(layer):
        b = bounds[layer["id"]]
        mx, my = ink_margin(layer, bounds, children, memo)
        if layer.get("styles"):
            mx, my = (m + 2 * s + 4 for m, s in zip((mx, my), style_margin(layer)))
        if b[0] - mx >= size[0] or b[1] - my >= size[1] or b[0] + b[2] + mx <= 0 or b[1] + b[3] + my <= 0:
            return None, (0, 0)  # Nothing it draws (its styles included) reaches the tile.
        patch, origin = layer_patch(project, layer, bounds, size, index, limit=limit)
        if patch is not None and drawn is not None:
            drawn[layer["id"]] = (*origin, origin[0] + patch.width, origin[1] + patch.height)
        if patch is not None and limit:
            # Styled past the tile, as on the whole canvas; keep the part on the tile.
            left, top = max(0, origin[0]), max(0, origin[1])
            right, bottom = min(size[0], origin[0] + patch.width), min(size[1], origin[1] + patch.height)
            if left >= right or top >= bottom:
                return None, (0, 0)
            patch = patch.crop((left - origin[0], top - origin[1], right - origin[0], bottom - origin[1]))
            origin = (left, top)
        return (patch, origin) if patch is not None else (None, (0, 0))

    def covering(asset):
        """A selection or mask image stretched over the canvas (or the group tile), and cut to this tile when the
        tile is a region of the canvas (``limit``)."""
        if not limit:
            return project.image(asset, "L").resize(size)
        whole = (limit[2] - limit[0], limit[3] - limit[1])
        return project.image(asset, "L").resize(whole).crop((-limit[0], -limit[1], size[0] - limit[0],
                                                             size[1] - limit[1]))

    def reaches(layer):
        """Whether what the layer draws (its styles included) reaches the tile."""
        b = bounds[layer["id"]]
        mx, my = ink_margin(layer, bounds, children, memo)
        if layer.get("styles"):
            mx, my = (m + 2 * s + 4 for m, s in zip((mx, my), style_margin(layer)))
        return not (b[0] - mx >= size[0] or b[1] - my >= size[1] or b[0] + b[2] + mx <= 0 or b[1] + b[3] + my <= 0)

    def plain(layer):
        return not layer.get("styles") and not layer.get("clip") and layer["type"] != "adjustment"

    def ahead(layer):
        """What compositing ``layer`` needs that does not read the tile: its ink, or its styled patch."""
        if plain(layer):
            return layer_ink(project, {**layer, "opacity": 1}, bounds[layer["id"]])
        return patch_of(layer)

    def direct(layer):
        """Composite a plain layer only over its own bounds instead of a full-canvas tile."""
        b = bounds[layer["id"]]
        if not reaches(layer):
            return image
        source = prefetch.take(layer)
        if source is None:
            source = layer_ink(project, {**layer, "opacity": 1}, b)
        x, y = ink_origin(source, b)
        if drawn is not None:
            drawn[layer["id"]] = (x, y, x + source.width, y + source.height)
        left, top = max(0, x), max(0, y)
        right, bottom = min(size[0], x + source.width), min(size[1], y + source.height)
        if left >= right or top >= bottom:
            return image
        if (left, top, right, bottom) != (x, y, x + source.width, y + source.height):
            source = source.crop((left - x, top - y, right - x, bottom - y))
        if layer["opacity"] != 1:
            source = with_opacity(source, layer["opacity"])
        if layer["blend"] == "normal":
            image.alpha_composite(source, (left, top))
        else:
            box = (left, top, right, bottom)
            image.paste(composite(image.crop(box), source, layer["blend"]), box[:2])
        return image

    def draw(layer):
        nonlocal image
        if layer["opacity"] <= 0:
            # Fully transparent (a layer or group scaled to nothing is drawn this way): nothing to
            # composite, and resampling a zero-size group tile would ask for an unbounded raster.
            return image
        if plain(layer):
            return direct(layer)
        if layer["type"] == "adjustment":
            changed = image
            for effect in layer["effects"]:
                if effect.get("enabled", True):
                    filtered = apply_effect(changed, effect, project)
                    changed = (
                        Image.composite(filtered, changed, covering(effect["selection"]))
                        if effect.get("selection")
                        else filtered
                    )
            mask = Image.new("L", size, round(255 * layer["opacity"]))
            if layer.get("mask") and layer["mask"].get("enabled", True):
                from PIL import ImageChops

                mask = ImageChops.multiply(mask, covering(layer["mask"]["asset"]))
            image = Image.composite(composite(image, changed, layer["blend"]), image, mask)
        else:
            drawn_ahead = prefetch.take(layer)
            patch, (left, top) = drawn_ahead if drawn_ahead is not None else patch_of(layer)
            if patch is not None:
                # Pixels the layer leaves transparent are unchanged by every blend mode.
                box = (left, top, left + patch.width, top + patch.height)
                if layer["blend"] == "normal":
                    image.alpha_composite(patch, box[:2])
                elif (drawn := patch.getchannel("A").getbbox()):
                    patch = patch.crop(drawn)
                    box = (left + drawn[0], top + drawn[1], left + drawn[2], top + drawn[3])
                    image.paste(composite(image.crop(box), patch, layer["blend"]), box[:2])
        return image

    from .calls import check_cancelled

    shown = [layer for layer in layers if layer.get("parent") == parent and layer["visible"]
             and (members is None or layer["id"] in members)]
    candidates = []
    if not getattr(_IN_POOL, "active", False) and PROFILE.get() is None and render_threads() > 1:
        candidates = [layer for layer in shown if worth_prefetching(layer) and reaches(layer)]
        if sum(bounds[layer["id"]][2] * bounds[layer["id"]][3] for layer in candidates) < PREFETCH_MIN_PIXELS:
            candidates = []
    prefetch = Prefetch(ahead, candidates)
    prefetch.refill()
    try:
        for layer in shown:
            check_cancelled()
            if observe and layer["id"] in observe:
                box = pixel_box(bounds[layer["id"]], image.size)
                before = image.crop(box)
                image = draw(layer)
                observe[layer["id"]](before, image.crop(box))
            else:
                image = draw(layer)
    finally:
        prefetch.close()
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


# Document state that does not change pixels: edits to it keep the previous canvas usable.
UNDRAWN_STATE = {"layers", "timeline", "animation", "suites", "roles", "motions", "actions", "recipe", "active_layer",
                 "design_guidance", "presets"}
# Canvases up to this many pixels keep their last render for the next one.
INCREMENTAL_PIXELS = 40_000_000


class Snapshot:
    """The last canvas a document view rendered, with what each top-level layer depended on and where it drew.
    ``lit`` is that canvas after scene lighting (``scene.composite``), when the document has lighting."""

    def __init__(self, document, assets, order, layers, image, lit=None):
        self.document, self.assets, self.order, self.layers, self.image = document, assets, order, layers, image
        self.lit = lit


def layer_fingerprints(project, layers, bounds):
    """Top-level layer ID → (digest of everything its pixels depend on, the canvas box it can draw in),
    or None when some layer reads outside the document (linked files)."""
    children, memo, index = child_index(layers), {}, {item["id"]: item for item in layers}
    c = project.state["canvas"]
    subtree = {}

    def contents(item):
        if item["id"] not in subtree:
            nested = [contents(child) for child in children.get(item["id"], [])]
            subtree[item["id"]] = [item, bounds.get(item["id"]), nested]
        return subtree[item["id"]]

    digests, visiting = {}, set()

    def fingerprint(item):
        if item["id"] not in digests:
            require(item["id"] not in visiting, "Clipping contains a cycle")
            visiting.add(item["id"])
            clip = index.get(item.get("clip"))
            digests[item["id"]] = digest([contents(item), fingerprint(clip) if clip else None])
            visiting.discard(item["id"])
        return digests[item["id"]]

    result = {}
    for item in layers:
        if item.get("linked") or item["type"] == "link":
            return None
        if item.get("parent"):
            continue
        box = None
        if item["visible"] and item["type"] == "adjustment":
            box = (0, 0, c["width"], c["height"])  # It filters everything below it, wherever its own box is.
        elif item["visible"]:
            x, y, w, h = bounds[item["id"]]
            mx, my = ink_margin(item, bounds, children, memo)
            # Styles are drawn on a patch reaching past their margin (layer_patch); two pixels hold
            # antialiasing and fractional placement.
            sx, sy = (2 * margin + 4 for margin in style_margin(item)) if item.get("styles") else (0, 0)
            mx, my = mx + sx + 2, my + sy + 2
            box = (max(0, math.floor(x - mx)), max(0, math.floor(y - my)),
                   min(c["width"], math.ceil(x + w + mx)), min(c["height"], math.ceil(y + h + my)))
            if box[0] >= box[2] or box[1] >= box[3]:
                box = None
        result[item["id"]] = (fingerprint(item), box)
    return result


def dirty_box(previous, current):
    """The canvas box (left, top, right, bottom) to composite again so that a render whose top-level layers are
    ``current`` matches a full one, starting from the ``previous`` snapshot: where changed layers drew, and where
    they are estimated to draw now. (0, 0, 0, 0) when nothing changed, None when the stacking order did."""
    shared = [ident for ident in previous.order if ident in current]
    if shared != [ident for ident in current if ident in previous.layers]:
        return None
    boxes = []
    for ident, (fingerprint, estimate) in current.items():
        before = previous.layers.get(ident)
        if before is None or before[0] != fingerprint:
            boxes += [estimate, before[1] if before else None]
    boxes += [previous.layers[ident][1] for ident in previous.order if ident not in current]
    return union(boxes)


def union(boxes):
    boxes = [box for box in boxes if box]
    if not boxes:
        return (0, 0, 0, 0)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def render_incremental(project, background):
    """``render_layers`` for a document whose regions render alone, reusing the canvas the same view drew last:
    only the box covering the layers that changed (where they drew and where they draw now) is composited again.
    Edits, previews and timeline frames that move or restyle a few layers stop costing the whole canvas. Scene
    lighting is applied here too (it is a function of each pixel and its place), and to the same box only."""
    from .scene import composite as light

    c = project.state["canvas"]
    cache = layer_cache(project)
    lit = bool(project.state.get("lighting"))
    if c["width"] * c["height"] > INCREMENTAL_PIXELS:
        return light(render_layers(project, background=background), project)

    def on_canvas(box, left=0, top=0):
        if box is None:
            return None
        box = (max(0, box[0] + left), max(0, box[1] + top), min(c["width"], box[2] + left), min(c["height"], box[3] + top))
        return box if box[0] < box[2] and box[1] < box[3] else None

    profile = PROFILE.get()
    with resolving(project):
        layers, bounds = resolved(project)
        project._resolution = (project.state, layers, bounds)
        try:
            try:
                document = digest([{k: v for k, v in project.state.items() if k not in UNDRAWN_STATE}, background,
                                   snap_placement(project)])
                current = layer_fingerprints(project, layers, bounds)
            except (TypeError, ValueError):
                current = None
            if current is None:
                if profile is not None:
                    profile.render(incremental=False, reason="a layer reads a linked file")
                return light(_render_layers(project, layers, bounds, None, None, background, None), project)
            assets = dict(project.assets)
            previous = getattr(cache, "snapshot", None)
            box = None
            if (previous is not None and previous.document == document and previous.assets.keys() == assets.keys()
                    and all(previous.assets[name] is data for name, data in assets.items())):
                box = dirty_box(previous, current)
            top_level = [item for item in layers if not item.get("parent")]
            changed = {ident for ident, (fingerprint, _) in current.items()
                       if previous is None or previous.layers.get(ident, (None,))[0] != fingerprint}
            image = lit_image = None
            relight = previous is not None and (previous.lit is not None) == lit
            for _ in range(3):
                if box is None or not relight:
                    break
                left, top, right, bottom = box
                if left >= right or top >= bottom:
                    # Only layers that draw nothing changed (hidden, or off the canvas).
                    image, drawn = previous.image.copy(), {ident: None for ident in changed}
                    lit_image = previous.lit.copy() if lit else None
                    break
                drawn = {}
                placed = shift(bounds, top_level, -left, -top)
                tile = _render_layers(project, layers, placed, None, (right - left, bottom - top), background, None,
                                      limit=(-left, -top, c["width"] - left, c["height"] - top), drawn=drawn)
                # Estimates can fall short (kinetic glyphs draw past their layer's box): grow and draw again.
                reach = union([box] + [on_canvas(drawn.get(ident), left, top) for ident in changed])
                if reach == box:
                    image = previous.image.copy()
                    image.paste(tile, (left, top))
                    if lit:
                        lit_image = previous.lit.copy()
                        lit_image.paste(light(tile, project, box), (left, top))
                    drawn = {ident: on_canvas(drawn.get(ident), left, top) for ident in changed}
                    break
                box = reach
            if profile is not None:
                dirty = None if image is None else list(box)
                profile.render(incremental=image is not None, dirty_box=dirty,
                               dirty_pixels=(max(0, dirty[2] - dirty[0]) * max(0, dirty[3] - dirty[1]) if dirty
                                             else c["width"] * c["height"]),
                               canvas_pixels=c["width"] * c["height"], changed_layers=len(changed))
            if image is None:
                drawn = {}
                image = _render_layers(project, layers, bounds, None, None, background, None, drawn=drawn)
                drawn = {ident: on_canvas(drawn.get(ident)) for ident in current}
                lit_image = light(image, project) if lit else None
            layers_now = {ident: (fingerprint, drawn[ident] if ident in drawn else previous.layers[ident][1])
                          for ident, (fingerprint, _) in current.items()}
            # The snapshot holds the asset bytes it compared, so an identical id cannot be a reused one.
            cache.snapshot = Snapshot(document, assets, list(current), layers_now, image.copy(),
                                      lit_image.copy() if lit else None)
            return lit_image if lit else image
        finally:
            project._resolution = None


def region_renders_alone(project):
    """Whether a region of the canvas can be drawn by itself, matching the same crop of a full render.
    Not when something reads the whole canvas: an adjustment layer with a filter that sees past each pixel (blur,
    contrast, sharpen, noise, artistic filters), canvas-edge blur on a top-level layer, or an effect on an ordinary
    layer masked by a canvas selection. Scene lighting and per-pixel adjustments (levels, curves, hue, LUTs ...,
    their masks and selections cut to the region) give a region the same pixels as the whole canvas."""
    for layer in project.state["layers"]:
        if layer.get("parent") or not layer.get("visible", True):
            continue
        effects = [effect for effect in layer.get("effects") or [] if effect.get("enabled", True)]
        if layer["type"] == "adjustment":
            if any(effect["name"] not in PER_PIXEL or effect["name"] in BLURS for effect in effects):
                return False
            continue
        if any(effect_margin(layer)) or any(effect.get("selection") for effect in effects):
            return False
    return True


def render_region(project, region, background="transparent"):
    """Composite only ``region`` (left, top, width, height, whole pixels inside the canvas): layers that
    miss it are skipped and every tile is region-sized. Same pixels as ``render_layers(...).crop``."""
    left, top, width, height = region
    c = project.state["canvas"]
    with resolving(project):
        layers, bounds = resolved(project)
        project._resolution = (project.state, layers, bounds)
        try:
            placed = shift(bounds, [item for item in layers if not item.get("parent")], -left, -top)
            return _render_layers(project, layers, placed, None, (width, height), background, None,
                                  limit=(-left, -top, c["width"] - left, c["height"] - top))
        finally:
            project._resolution = None


def render(project, variables=None, artboard=None, comp=None, page=None, region=None):
    """The document as an image; ``region`` (left, top, width, height, whole pixels inside the canvas)
    returns that crop, drawing only that part when nothing in the document reads the whole canvas."""
    from .links import draw_scope

    profile = PROFILE.get()
    with draw_scope():
        if profile is None:
            return _render(project, variables, artboard, comp, page, region)
        import time

        started = time.perf_counter()
        try:
            return _render(project, variables, artboard, comp, page, region)
        finally:
            profile.phase("render", time.perf_counter() - started)


def _render(project, variables=None, artboard=None, comp=None, page=None, region=None):
    from .design_render import artboard_project

    project = view_page(project, page)
    candidate = artboard_project(project, artboard, comp, variables)
    from .captions import prepare_bubbles

    candidate = prepare_bubbles(candidate)
    from .design import resolve_color

    if region is not None:
        left, top, width, height = (int(v) for v in region)
        c = candidate.state["canvas"]
        require(width > 0 and height > 0 and left >= 0 and top >= 0 and left + width <= c["width"]
                and top + height <= c["height"], "Region must lie inside the canvas", field="region")
        if (left, top, width, height) != (0, 0, c["width"], c["height"]):
            if region_renders_alone(candidate):
                if PROFILE.get() is not None:
                    PROFILE.get().render(incremental=False, region=[left, top, width, height])
                from .scene import composite as light

                tile = render_region(candidate, (left, top, width, height),
                                     resolve_color(candidate.state["canvas"]["background"], candidate.state))
                return light(tile, candidate, (left, top, left + width, top + height))
            return _render(project, variables, artboard, comp, page).crop((left, top, left + width, top + height))
    disk = getattr(project, "_disk_cache", None)
    key = None
    if disk:
        from .render_cache import key_for
        key = key_for(candidate)
        cached = disk.get(key, project.limits, kind="frame")
        if cached is not None:
            if PROFILE.get() is not None:
                PROFILE.get().render(incremental=False, from_disk=True)
            return cached
    background = resolve_color(candidate.state["canvas"]["background"], candidate.state)
    if region_renders_alone(candidate):
        image = render_incremental(candidate, background)  # lit there
    else:
        if PROFILE.get() is not None:
            PROFILE.get().render(incremental=False, reason="the document reads the whole canvas")
        from .scene import composite

        image = composite(render_layers(candidate, background=background), candidate)
    if disk:
        disk.put(key, image, kind="frame")
    return image
