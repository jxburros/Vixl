"""Canonical operation dispatcher. CLI, scripts, REST and MCP use this same boundary."""

from .design_schema import TYPES as DESIGN_TYPES
from .pixel import PIXEL_TYPES
from .animation import ANIMATION_TYPES
from .resources import RESOURCE_TYPES
from .brushes import BRUSH_TYPES
from .timeline import TIMELINE_TYPES
from .layouts import LAYOUT_TYPES
from .automation import TYPES as AUTOMATION_TYPES
from .authoring import TYPES as AUTHORING_TYPES
from .creative import TYPES as CREATIVE_TYPES
from .containers import TYPES as CONTAINER_TYPES
from .inplace import IN_PLACE_TYPES
from .stacks import TYPES as STACK_TYPES, POSITIONING as STACK_POSITIONING
from .organic import TYPES as ORGANIC_TYPES
from .irregular import TYPES as IRREGULAR_TYPES
from .guides import TYPES as GUIDE_TYPES
from .richtext import TYPES as RICH_TYPES
from .pages import TYPES as PAGE_TYPES
from .forms import TYPES as FORM_TYPES
from .drawing import TYPES as DRAWING_TYPES
from .selectors import TYPES as SELECTOR_TYPES
from .links import TYPES as LINK_TYPES
from .codes import TYPES as CODE_TYPES
from .charts import TYPES as CHART_TYPES
from .finishing import TYPES as FINISHING_TYPES
from .diagrams import TYPES as DIAGRAM_TYPES
from .textflow import TYPES as FLOW_TYPES
from .transforms import TYPES as TRANSFORM_TYPES
from .motion import TYPES as MOTION_TYPES
from .characters import TYPES as CHARACTER_TYPES
from .comics import TYPES as COMIC_TYPES
from .textures import TYPES as TEXTURE_TYPES
from .audio import TYPES as AUDIO_TYPES
from .captions import TYPES as CAPTION_TYPES
from .scene import TYPES as SCENE_TYPES
from .vector_paths import TYPES as VECTOR_TYPES

from copy import deepcopy
import hashlib
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .assets import add_encoded, add_image, decode, read_bounded
from .denoise import KEYS as DENOISE_KEYS, validate as denoise_valid
from .errors import VixlError, require
from .model import finite, new_layer, uid
from .render import (
    BLENDS,
    EFFECTS,
    color,
    layer_image,
    layer_ink,
    ink_origin,
    resolve_font,
    resolve_layout,
    text_metrics,
)

COLOR_TYPES = ("palette-generate",)


OPERATION_TYPES = list(DESIGN_TYPES + PIXEL_TYPES + ANIMATION_TYPES + RESOURCE_TYPES + BRUSH_TYPES + TIMELINE_TYPES + LAYOUT_TYPES + COLOR_TYPES + AUTOMATION_TYPES + CREATIVE_TYPES + CONTAINER_TYPES + AUTHORING_TYPES + ORGANIC_TYPES + IRREGULAR_TYPES + GUIDE_TYPES + RICH_TYPES + PAGE_TYPES + FORM_TYPES + DRAWING_TYPES + STACK_TYPES + SELECTOR_TYPES + LINK_TYPES + CODE_TYPES + CHART_TYPES + FINISHING_TYPES + DIAGRAM_TYPES + FLOW_TYPES + TRANSFORM_TYPES + MOTION_TYPES + CHARACTER_TYPES + COMIC_TYPES + TEXTURE_TYPES + AUDIO_TYPES + VECTOR_TYPES + CAPTION_TYPES + SCENE_TYPES) + [
    "add",
    "solid",
    "gradient",
    "text",
    "text-set",
    "remove",
    "rename",
    "duplicate",
    "move",
    "resize",
    "scale",
    "rotate",
    "pivot",
    "flip",
    "crop",
    "opacity",
    "blend",
    "hide",
    "show",
    "reorder",
    "raise",
    "lower",
    "top",
    "bottom",
    "select-layer",
    "align",
    "constrain",
    "unconstrain",
    "canvas",
    "select",
    "mask",
    "effect",
    "effect-set",
    "effect-disable",
    "effect-enable",
    "effect-remove",
    "effect-move",
    "rasterize",
    "variable",
    "variable-map",
    "preset-save",
    "preset-apply",
]


def _align_baselines(project, op, targets, ref):
    """Move text layers vertically so their first baselines line up with the reference's: a text layer named in
    relative_to, or the first target."""
    from .render import stored_origin
    from .text_metrics import first_baseline, resolved_text

    require(ref != "canvas", "Baseline alignment lines text up with another text layer: give targets (the first sets "
            "the baseline) or relative_to a text layer", field="relative_to")

    def baseline(item):
        layer, resolved, bounds = resolved_text(project, item["id"])
        require(not layer.get("rotation") % 360 and not layer.get("skew_x") and not layer.get("skew_y"),
                f"{layer['name']!r} is rotated or skewed; baselines align on upright text", field="targets")
        return bounds, first_baseline(project, resolved)

    reference = project.layer(ref) if ref != "selection" else targets[0]
    require(reference.get("parent") == targets[0].get("parent"), "Alignment targets must share a parent")
    bounds, offset = baseline(reference)
    line = bounds[1] + offset + finite(op.get("margin", 0), "margin", 0)
    for item in targets:
        box, offset = baseline(item)
        item.update(constraints={})
        item["x"], item["y"] = stored_origin(item, (box[0], line - offset))


def embed_font_file(project, layer):
    if layer["font"] not in project.assets and Path(layer["font"]).is_file():
        data = read_bounded(layer["font"], project.limits.max_asset_bytes)
        name = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[name] = data
        layer["font"] = name


# Settings an effect operation copies onto the stack entry (amount and value are handled apart).
EFFECT_KEYS = ("seed", "radius", "strength", "black", "white", "points", "shadow_color", "highlight_color",
               "gains", "neutral", "lut", *DENOISE_KEYS)


def effect_ref(layer, ref, field):
    """The effect in ``layer``'s stack named by ``ref``: a position starting at 1, an effect ID, or
    an effect name used once in the stack."""
    effects = layer["effects"]
    if isinstance(ref, int) and not isinstance(ref, bool) or str(ref).isdigit():
        index = int(ref) - 1
        require(0 <= index < len(effects), "Effect index out of range (starts at 1)", field=field)
        return effects[index]
    found = next((x for x in effects if x["id"] == ref), None)
    if found is None:
        named = [x for x in effects if x["name"] == ref]
        require(len(named) < 2, f"{len(named)} effects are named {ref}; use a position or ID", field=field)
        found = named[0] if named else None
    require(found, "Effect not found", field=field,
            allowed=[f"{i}: {x['name']} ({x['id']})" for i, x in enumerate(effects, 1)])
    return found


def effect_valid(effect):
    from .constants import ARTISTIC_DEFAULTS

    name = effect["name"]
    value = finite(effect.get("amount", ARTISTIC_DEFAULTS.get(name, 0)), "amount", -100000, 100000)
    if name in ARTISTIC_DEFAULTS:
        ranges = {
            "solarize": (0, 255), "ink-blot": (0, 255), "stamp": (0, 255), "photocopy": (0, 255),
            "pixelate": (1, 256), "halftone": (2, 128), "crosshatch": (2, 128), "oil-paint": (1, 6),
            "swirl": (-720, 720), "ripple": (0, 64), "wave": (0, 64), "glass": (0, 64),
        }
        finite(value, "amount", *ranges.get(name, (0, 100)))
        if name in ("pixelate", "halftone", "crosshatch", "oil-paint"):
            require(value == int(value), f"{name} amount must be an integer")
        if "radius" in effect:
            bounds = (0.01, 1) if name == "swirl" else (1, 256) if name in ("ripple", "wave", "glass") else (0, 20)
            finite(effect["radius"], "radius", *bounds)
        for key in ("shadow_color", "highlight_color"):
            if key in effect:
                require(color(effect[key])[3] == 255, "Duotone colors must be opaque")
    elif name in ("blur", "gaussian-blur"):
        finite(value, "radius", 0, 1000)
    elif name == "sharpen":
        finite(value, "amount", 0, 100)
    elif name == "denoise":
        denoise_valid(effect)
    elif name in ("temperature", "tint"):
        finite(value, name, -100, 100)
    elif name == "white-balance":
        finite(value, "amount", 0, 100)
        require(not ("gains" in effect and "neutral" in effect), "white-balance takes gains or neutral, not both",
                field="gains")
        if "gains" in effect:
            gains = effect["gains"]
            require(isinstance(gains, (list, tuple)) and len(gains) == 3, "gains is [red, green, blue]", field="gains")
            for gain in gains:
                finite(gain, "gain", 0, 16)
        if "neutral" in effect:
            color(effect["neutral"])
    elif name == "lookup":
        finite(value, "amount", 0, 1)
        require(isinstance(effect.get("lut"), str), "A lookup effect names its LUT in lut", field="lut")
    elif name == "gamma":
        finite(value, "gamma", 0.01, 100)
    elif name == "exposure":
        finite(value, "exposure", -32, 32)
    elif name == "posterize":
        require(int(value) == value and 1 <= value <= 8, "Posterize bits must be 1–8")
    elif name == "threshold":
        finite(value, "threshold", 0, 255)
    elif name in ("grain", "noise"):
        finite(value, "noise", 0, 1)
    elif name == "vignette":
        finite(effect.get("strength", value), "strength", 0, 1)
        finite(effect.get("radius", 0.7), "radius", 0, 1.4)
    elif name == "levels":
        finite(effect.get("black", 0), "black", 0, 254)
        finite(effect.get("white", 255), "white", 1, 255)
        require(effect.get("black", 0) < effect.get("white", 255), "Levels white must exceed black")
    elif name == "curves":
        points = effect.get("points", [])
        require(
            2 <= len(points) <= 256 and all(len(p) == 2 for p in points),
            "Curves require 2–256 [input,output] points",
        )
        for x, y in points:
            finite(x, "input", 0, 255)
            finite(y, "output", 0, 255)
        require(
            all(points[i][0] < points[i + 1][0] for i in range(len(points) - 1)), "Curve inputs must increase"
        )
    if "seed" in effect:
        require(isinstance(effect["seed"], int) and effect["seed"] >= 0, "Seed must be a nonnegative integer")


def unique_name(project, proposed):
    require(isinstance(proposed, str) and 0 < len(proposed) <= 200, "Layer name must be 1–200 characters")
    require(
        not any(proposed in (x["name"], x["id"]) for x in project.state["layers"]),
        f"Layer name already exists: {proposed}",
    )
    return proposed


def default_name(project, base):
    """A free name for a layer the operation left unnamed: ``base``, then ``base 2``, ``base 3``…
    Explicit names must still be unique."""
    taken = {x["name"] for x in project.state["layers"]} | {x["id"] for x in project.state["layers"]}
    name, index = base, 2
    while name in taken:
        name, index = f"{base} {index}", index + 1
    return name


def append_layer(project, layer):
    require(len(project.state["layers"]) < project.limits.max_layers, "Layer limit reached", "resource_limit")
    unique_name(project, layer["name"])
    from .transforms import VECTOR_TYPES
    project.limits.size(layer["width"], layer["height"], vector=layer["type"] in VECTOR_TYPES)
    project.state["layers"].append(layer)
    project.state["active_layer"] = layer["id"]
    return layer


def selection_image(project):
    selection = project.state["selection"]
    require(selection is not None, "No selection exists")
    return project.image(selection, "L")


def _select(project, op):
    c = project.state["canvas"]
    size = (c["width"], c["height"])
    shape = op.get("shape", "all")
    if shape == "none":
        project.state["selection"] = None
        return
    if shape == "invert":
        mask = ImageOps.invert(selection_image(project))
    elif shape == "all":
        mask = Image.new("L", size, 255)
    elif shape in ("rect", "ellipse"):
        x, y = finite(op.get("x", 0), "x"), finite(op.get("y", 0), "y")
        w, h = finite(op["width"], "width", 1), finite(op["height"], "height", 1)
        mask = Image.new("L", size)
        draw = ImageDraw.Draw(mask)
        getattr(draw, "rectangle" if shape == "rect" else "ellipse")((x, y, x + w - 1, y + h - 1), fill=255)
    elif shape == "alpha":
        layer = project.layer(op.get("target"))
        b = resolve_layout(project)[layer["id"]]
        rendered = layer_image(project, layer, b)
        mask = Image.new("L", size)
        mask.paste(rendered.getchannel("A"), (b[0], b[1]))
    elif shape == "color":
        rgb = np.asarray(project.render().convert("RGB"), dtype=np.int16)
        target = np.array(color(op["color"])[:3])
        tolerance = finite(op.get("tolerance", 15), "tolerance", 0, 255)
        mask = Image.fromarray(np.uint8(np.max(np.abs(rgb - target), axis=2) <= tolerance) * 255)
    elif shape in ("wand", "lasso", "path"):
        from .creative import selection
        mask = selection(project, op)
    elif shape == "asset":
        mask = project.image(op["asset"], "L")
        require(mask.size == size, "Selection mask must match canvas size")
    else:
        raise VixlError("invalid_selection", f"Unknown selection shape: {shape}")
    mode = op.get("mode", "replace")
    require(mode in ("replace", "add", "subtract", "intersect"), "Unknown selection combination")
    if mode != "replace" and project.state["selection"]:
        old, new = np.asarray(selection_image(project), dtype=np.int16), np.asarray(mask, dtype=np.int16)
        result = {
            "add": lambda: np.maximum(old, new),
            "subtract": lambda: np.maximum(0, old - new),
            "intersect": lambda: np.minimum(old, new),
        }[mode]()
        mask = Image.fromarray(np.uint8(result))
    if op.get("feather"):
        from PIL import ImageFilter

        radius = finite(op["feather"], "feather", 0, 1000)
        mask = mask.filter(ImageFilter.GaussianBlur(radius))
    project.state["selection"] = add_image(project, mask, "masks")


def execute(project, op):
    kind = op.get("type", op.get("operation"))
    from .normalize import _canonical_type

    kind = _canonical_type(kind, set(OPERATION_TYPES))
    require(isinstance(kind, str), "Operation requires a type")
    from .targets import EACH, fan_out

    if kind in EACH and "targets" in op:  # Nested batches (actions, edit-layers ...) fan out here.
        for single in fan_out({**op, "type": kind}):
            execute(project, single)
        return None
    target = op.get("target", op.get("layer"))
    from .schema import LAYER_FINISH

    if kind in LAYER_FINISH and ("opacity" in op or "rotation" in op):
        # Creation fields that stand for the rotate and opacity operations on the new (or edited) layer.
        result = execute(project, {k: v for k, v in op.items() if k not in ("opacity", "rotation")})
        ident = project.layer(target)["id"] if target is not None else project.state["active_layer"]
        if "rotation" in op:
            execute(project, {"type": "rotate", "target": ident, "value": op["rotation"]})
        if "opacity" in op:
            execute(project, {"type": "opacity", "target": ident, "value": op["opacity"]})
        return result
    if kind in SCENE_TYPES:
        from .scene import execute as execute_scene
        return execute_scene(project, op)
    if kind in CAPTION_TYPES:
        from .captions import execute as execute_caption
        return execute_caption(project, op)
    if kind in VECTOR_TYPES:
        from .vector_paths import execute as execute_vector
        return execute_vector(project, op)
    if kind in AUDIO_TYPES:
        from .audio import execute as execute_audio
        return execute_audio(project, op)
    if kind in COMIC_TYPES:
        from .comics import execute as execute_comic
        return execute_comic(project, op)
    if kind in TEXTURE_TYPES:
        from .textures import execute as execute_texture
        return execute_texture(project, op)
    if kind in MOTION_TYPES:
        from .motion import execute as execute_motion
        return execute_motion(project, op)
    if kind in CHARACTER_TYPES:
        from .characters import execute as execute_character
        return execute_character(project, op)
    if target is not None and kind in IN_PLACE_TYPES:
        from .inplace import execute as execute_in_place

        return execute_in_place(project, {**op, "type": kind, "target": target})
    if kind in STACK_POSITIONING:
        from .stacks import guard

        guard(project, op, target)
    from .transforms import execute as execute_transform
    if kind in (*TRANSFORM_TYPES, "move", "resize", "scale"):
        return execute_transform(project, op)
    if kind in STACK_TYPES:
        from .stacks import execute as execute_stack

        return execute_stack(project, op)
    if kind in SELECTOR_TYPES:
        from .selectors import execute as execute_selectors
        return execute_selectors(project, op)
    if kind in CHART_TYPES:
        from .charts import execute as execute_charts
        return execute_charts(project, op)
    if kind in PAGE_TYPES:
        from .pages import execute as execute_pages
        return execute_pages(project, op)
    if kind in FORM_TYPES:
        from .forms import execute as execute_forms
        return execute_forms(project, op)
    if kind in LINK_TYPES:
        from .links import execute as execute_links
        return execute_links(project, op)
    if kind in CODE_TYPES:
        from .codes import execute as execute_codes
        return execute_codes(project, op)
    if kind in FINISHING_TYPES:
        from .finishing import execute as execute_finishing
        return execute_finishing(project, op)
    if kind in DRAWING_TYPES:
        from .drawing import execute as execute_drawing
        return execute_drawing(project, op)
    if kind in DIAGRAM_TYPES:
        from .diagrams import execute as execute_diagram
        return execute_diagram(project, op)
    if kind in FLOW_TYPES:
        from .textflow import execute as execute_flow
        return execute_flow(project, op)
    if kind in RICH_TYPES:
        from .richtext import execute as execute_rich
        return execute_rich(project, op)
    if kind in GUIDE_TYPES:
        from .guides import execute as execute_guides
        return execute_guides(project, op)
    if kind in ORGANIC_TYPES:
        from .organic import execute as execute_organic
        return execute_organic(project, op)
    if kind in IRREGULAR_TYPES:
        from .irregular import execute as execute_irregular
        return execute_irregular(project, op)
    if kind in AUTHORING_TYPES:
        from .authoring import execute as execute_authoring
        return execute_authoring(project, op)
    if kind in CONTAINER_TYPES:
        from .containers import execute as execute_container
        return execute_container(project, op)
    if kind in CREATIVE_TYPES:
        from .creative import execute as execute_creative
        return execute_creative(project, op)
    if kind in AUTOMATION_TYPES:
        from .automation import execute as execute_automation
        execute_automation(project, op)
        return
    if kind in RESOURCE_TYPES:
        from .resources import execute_resource

        execute_resource(project, op)
        return
    if kind in PIXEL_TYPES:
        from .pixel import execute_pixel

        execute_pixel(project, op)
        return
    if kind in ANIMATION_TYPES:
        from .animation import execute_animation

        execute_animation(project, op)
        return
    if kind in BRUSH_TYPES:
        from .brushes import execute_brush

        execute_brush(project, op)
        return
    if kind in TIMELINE_TYPES:
        from .timeline import execute_timeline

        execute_timeline(project, op)
        return
    if kind in LAYOUT_TYPES:
        from .layouts import execute_layout

        execute_layout(project, op)
        return
    if kind == "palette-generate":
        from .colors import generate_swatches
        from .design import resolve_color as resolve

        resolved = {**op, "color": resolve(op["color"], project.state)}
        project.state.setdefault("swatches", {}).update(generate_swatches(resolved))
        return
    from .design import execute_design, resolve_color

    if kind in DESIGN_TYPES:
        execute_design(project, op)
        return
    if kind == "add":
        original_size = None
        if "asset" in op:
            image = project.image(op["asset"])
            asset = op["asset"]
            provenance = deepcopy(op.get("provenance", {"type": "embedded"}))
            data = project.assets[asset]
        else:
            source = Path(op["path"]).resolve()
            data = read_bounded(source, project.limits.max_asset_bytes)
            asset, image = add_encoded(project, data)
            provenance = {
                "type": "imported",
                "original_filename": source.name,
                "original_path": str(source),
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        original_size = image.size
        width, height = op.get("width", image.width), op.get("height", image.height)
        if op.get("max_pixels") is not None or op.get("downsample"):
            require(not op.get("linked"), "Downsampling requires an embedded image, not linked=True", field="downsample")
            require(op.get("downsample") in (None, "placed@2x"), "downsample must be placed@2x", field="downsample")
            asset, image = add_encoded(project, data, max_pixels=op.get("max_pixels"),
                                       placed_size=(width * 2, height * 2) if op.get("downsample") else None,
                                       fit=op.get("fit", "fill"))
            provenance.update(original_size=list(original_size), embedded_size=list(image.size))
            provenance.update({key: op[key] for key in ("downsample", "max_pixels") if key in op})
        from .image_import import attribution

        provenance.update(attribution(op.get("credit"), op.get("license")))
        layer = new_layer(
            op["name"] if "name" in op else default_name(project, Path(op.get("path", "image")).stem),
            "raster",
            width, height,
            asset=asset,
            provenance=provenance,
        )
        if op.get("linked"):
            require("path" in op, "Linked layers require a path")
            layer["linked"] = str(source)
            project.allow_linked = True
        layer["x"], layer["y"] = finite(op.get("x", 0), "x"), finite(op.get("y", 0), "y")
        append_layer(project, layer)
        return
    if kind in ("solid", "gradient", "text"):
        c = project.state["canvas"]
        w, h = op.get("width", c["width"]), op.get("height", c["height"])
        layer = new_layer(op["name"] if "name" in op else default_name(project, kind), kind, w, h)
        if kind == "solid":
            color(resolve_color(op.get("color", "white"), project.state))
            layer["fill"] = op.get("color", "white")
        elif kind == "gradient":
            for key, default in (("start", "black"), ("end", "white")):
                color(resolve_color(op.get(key, default), project.state))
                layer[key] = op.get(key, default)
            layer["direction"] = op.get("direction", "vertical")
            layer.update({k: deepcopy(op[k]) for k in ("stops", "angle") if k in op})
        else:
            font, role = resolve_font(project, op.get("font"))
            layer.update(
                {
                    "text": op["text"],
                    "font": font,
                    "size": op.get("size", 48),
                    "color": op.get("color", "white"),
                    "align": op.get("align", "left"),
                    "spacing": op.get("spacing", 4),
                    "auto_size": True,
                }
            )
            if role:
                layer["font_role"] = role
            if op.get("hide_if_empty"):
                layer["hide_if_empty"] = True
            embed_font_file(project, layer)
            layer["width"], layer["height"], _ = text_metrics(project, layer)
            color(resolve_color(layer["color"], project.state))
        layer["x"] = finite(op.get("x", 0), "x") if op.get("x") != "center" else (c["width"] - layer["width"]) / 2
        layer["y"] = (
            finite(op.get("y", 0), "y") if op.get("y") != "center" else (c["height"] - layer["height"]) / 2
        )
        append_layer(project, layer)
        if "within" in op:
            from .guides import place_within

            require(not {"x", "y"} & set(op), "within positions the text; drop x and y (or use place with within "
                    "and an anchor)", field="within")
            place_within(project, layer["id"], op["within"])
        return
    if kind == "canvas":
        c = project.state["canvas"]
        if "size" in op or "preset" in op:
            from .sizes import apply_size

            require(not ("width" in op or "height" in op), "Use either a named size or width/height")
            apply_size(project, op)
            w, h = c["width"], c["height"]
        else:
            require(not any(k in op for k in ("orientation", "bleed")), "orientation and bleed need a named size")
            w, h = op.get("width", c["width"]), op.get("height", c["height"])
            project.limits.size(w, h)
            background = op.get("background", c["background"])
            color(resolve_color(background, project.state))
            if (w, h) != (c["width"], c["height"]):
                # A custom size no longer matches the named size's trim, bleed and safe area.
                for key in ("size", "bleed", "safe", "physical"):
                    c.pop(key, None)
                from .sizes import replace_generated_guides

                replace_generated_guides(project.state, {})
            c.update(width=w, height=h, background=background)
        if "dpi" in op:
            finite(op["dpi"], "dpi", 36, 2400)
            c["dpi"] = op["dpi"]
        if project.state["selection"]:
            old = selection_image(project)
            mask = Image.new("L", (w, h))
            mask.paste(old, (0, 0))
            project.state["selection"] = add_image(project, mask, "masks")
        return
    if kind == "select":
        _select(project, op)
        return
    if kind == "variable":
        require(isinstance(op["name"], str) and re.fullmatch(r"[\w-]+", op["name"]), "Invalid variable name")
        if op.get("delete"):
            project.state["variables"].pop(op["name"], None)
        else:
            require(isinstance(op["value"], (str, int, float, bool)), "Variables must be scalar values")
            project.state["variables"][op["name"]] = op["value"]
        return
    if kind == "variable-map":
        from .variables import execute_map

        execute_map(project, op)
        return
    layer = project.layer(target)
    layers = project.state["layers"]
    if kind == "select-layer":
        project.state["active_layer"] = layer["id"]
    elif kind == "remove":
        from .design import descendants

        removed = descendants(project, layer["id"]) | {layer["id"]}
        layers[:] = [item for item in layers if item["id"] not in removed]
        for item in layers:
            if item.get("clip") in removed:
                item.pop("clip")
            if item["type"] == "field" and item["field"].get("label_layer") in removed:
                item["field"].pop("label_layer")  # the form check reports the missing label
        project.state["symbols"] = {
            k: v for k, v in project.state.get("symbols", {}).items() if v not in removed
        }
        for board in project.state.get("artboards", {}).values():
            if "targets" in board:
                board["targets"] = [ident for ident in board["targets"] if ident not in removed]
        if project.state["active_layer"] in removed:
            project.state["active_layer"] = layers[-1]["id"] if layers else None
        from .timeline import prune_targets

        prune_targets(project.state, removed)
    elif kind == "rename":
        layer["name"] = unique_name(project, op["name"])
    elif kind == "duplicate":
        duplicate = deepcopy(layer)
        duplicate["id"] = uid("lyr")
        duplicate["name"] = op["name"] if "name" in op else default_name(project, layer["name"] + " copy")
        if duplicate["type"] == "field":
            from .forms import fresh_key

            fresh_key(project, duplicate)
        append_layer(project, duplicate)
        if layer["type"] == "group":
            from .design import descendants

            children = descendants(project, layer["id"])
            copies = [deepcopy(item) for item in layers if item["id"] in children]
            mapping = {layer["id"]: duplicate["id"], **{item["id"]: uid("lyr") for item in copies}}
            for item in copies:
                original_id = item["id"]
                item["id"] = mapping[original_id]
                item["name"] = duplicate["name"] + "/" + original_id
                item["parent"] = mapping[item["parent"]]
                if item.get("clip") in mapping:
                    item["clip"] = mapping[item["clip"]]
                for anchor, expression in item["constraints"].items():
                    if isinstance(expression, str):
                        for old, new in mapping.items():
                            expression = expression.replace(old + ".", new + ".")
                        item["constraints"][anchor] = expression
                if item["type"] == "field":
                    from .forms import fresh_key

                    fresh_key(project, item)
                    if item["field"].get("label_layer") in mapping:
                        item["field"]["label_layer"] = mapping[item["field"]["label_layer"]]
                append_layer(project, item)
            project.state["active_layer"] = duplicate["id"]
    elif kind == "text-set":
        require(layer["type"] == "text", "Layer is not editable text")
        dropped = []
        if "text" in op and layer.get("rich") and op["text"] != layer["text"]:
            from .richedit import replace_text

            dropped = replace_text(layer, op["text"])  # keeps list, alignment and span formatting that still apply
        for key in ("text", "size", "color", "align", "spacing", "stroke_width", "stroke_color", "hide_if_empty"):
            if key in op:
                layer[key] = op[key]
        if "font" in op:
            layer["font"], role = resolve_font(project, op["font"])
            layer.pop("font_role", None)
            if role:
                layer["font_role"] = role
            embed_font_file(project, layer)
        require(layer["align"] in ("left", "center", "right"), "Invalid text alignment")
        finite(layer.get("spacing", 4), "spacing", 0, 1000)
        finite(layer.get("stroke_width", 0), "stroke_width", 0, 100)
        color(resolve_color(layer["color"], project.state))
        if layer.get("rich"):
            from .richedit import override_warnings, report

            report(project, layer, dropped, override_warnings(layer, op))
        box = layer.get("text_layout") or {}
        if "width" not in box and "height" not in box:
            # A text-layout box keeps its wrapping dimensions; plain text re-fits its content.
            layer["width"], layer["height"], _ = text_metrics(project, layer)
            layer["auto_size"] = True
    elif kind in ("rotate", "pivot", "flip") and layer["type"] == "field":
        raise VixlError("invalid_operation", f"{kind} does not apply to fields: PDF form fields are upright rectangles",
                        field="target")
    elif kind == "rotate":
        layer["rotation"] = finite(op["value"], "angle") % 360
    elif kind == "pivot":
        from .render import rest_size, stored_origin

        bounds = resolve_layout(project)[layer["id"]]
        if op.get("clear"):
            layer.pop("pivot", None)
        else:
            require("value" in op, "Pass value: [x, y] or an anchor such as 'top-left'", field="value")
            value = op["value"]
            if isinstance(value, str):
                from .geometry import ANCHORS, canonical_anchor

                name = canonical_anchor(value)
                require(name, f"Unknown pivot anchor {value!r}; use {', '.join(ANCHORS)}", field="value")
                value = list(ANCHORS[name])
            else:
                require(isinstance(value, list) and len(value) == 2, "Pivot value must be [x, y]", field="value")
                if op.get("units") == "px":
                    rw, rh = rest_size(layer)
                    for axis, v, size in (("x", value[0], rw), ("y", value[1], rh)):
                        finite(v, f"pivot {axis}")
                        require(
                            abs(v) <= 10 * size,
                            f"pivot {axis} of {v:g} px is more than 10 box sizes from the layer's corner "
                            f"(at most ±{10 * size:g} px for this {rw}×{rh} layer)",
                            field="value",
                        )
                    value = [value[0] / rw, value[1] / rh]
                elif op.get("units") == "canvas":
                    # A point on the canvas, taken back through the parent groups and the layer's own transform.
                    from .affine import layer_matrix
                    from .checks import group_matrix
                    from .render import resolved_layers

                    rw, rh = rest_size(layer)
                    index = {item["id"]: item for item in resolved_layers(project)}
                    full = group_matrix(index[layer["id"]], index, resolve_layout(project)) @ layer_matrix(layer, bounds)
                    local = np.linalg.inv(full) @ [finite(value[0], "pivot x"), finite(value[1], "pivot y"), 1]
                    value = [float(local[0] / rw), float(local[1] / rh)]
            layer["pivot"] = [finite(value[0], "pivot x", -10, 10), finite(value[1], "pivot y", -10, 10)]
        if not layer["constraints"]:
            # Keep the drawn pose; only the origin of later rotation and scaling moves.
            layer["x"], layer["y"] = stored_origin(layer, bounds)
    elif kind == "flip":
        require(op["direction"] in ("horizontal", "vertical"), "Flip must be horizontal or vertical")
        key = "flip_x" if op["direction"] == "horizontal" else "flip_y"
        layer[key] = not layer[key]
    elif kind == "crop":
        require(layer["type"] == "raster", "Crop applies to raster layers")
        x, y, w, h = (int(op[k]) for k in ("x", "y", "width", "height"))
        project.limits.size(w, h)
        source = project.image(layer["asset"])
        require(
            x >= 0 and y >= 0 and x + w <= source.width and y + h <= source.height,
            "Crop exceeds source bounds",
        )
        layer.update(crop=[x, y, x + w, y + h], width=w, height=h)
    elif kind == "opacity":
        layer["opacity"] = finite(op["value"], "opacity", 0, 1)
    elif kind == "blend":
        require(op["value"] in BLENDS, "Unknown blend mode")
        layer["blend"] = op["value"]
    elif kind in ("hide", "show"):
        layer["visible"] = kind == "show"
    elif kind in ("raise", "lower", "top", "bottom", "reorder"):
        siblings = [item for item in layers if item.get("parent") == layer.get("parent")]
        index = siblings.index(layer)
        if kind == "reorder":
            other = project.layer(op.get("above", op.get("below")))
            require(
                other != layer and other.get("parent") == layer.get("parent"),
                "Reorder requires another layer in the same group",
            )
            layers.remove(layer)
            dest = layers.index(other) + (1 if "above" in op else 0)
        else:
            target_index = {
                "raise": min(index + 1, len(siblings) - 1),
                "lower": max(index - 1, 0),
                "top": len(siblings) - 1,
                "bottom": 0,
            }[kind]
            other = siblings[target_index]
            if other == layer:
                return
            layers.remove(layer)
            dest = layers.index(other) + (1 if target_index > index else 0)
        layers.insert(dest, layer)
    elif kind == "align":
        from .design import selected, union_bounds
        from .render import stored_origin

        targets = selected(project, op.get("targets", [layer["id"]]))
        layout = resolve_layout(project)
        ref = op.get("relative_to", "selection" if "targets" in op else "canvas")
        if ref == "selection":
            box = union_bounds([layout[item["id"]] for item in targets])
        elif ref == "canvas":
            parent = targets[0].get("parent")
            c = project.layer(parent) if parent else project.state["canvas"]
            box = (0, 0, c.get("content_width", c["width"]), c.get("content_height", c["height"]))
        else:
            other = project.layer(ref)
            require(other.get("parent") == targets[0].get("parent"), "Alignment targets must share a parent")
            box = layout[other["id"]]
            if op.get("box", "bounds") == "content":
                from .affine import layer_matrix
                from .spatial import content_rect

                box = content_rect(other, layer_matrix(other, box)) or box
        require(op.get("box", "bounds") == "bounds" or ref not in ("selection", "canvas"),
                "box: content needs relative_to naming a layer (its content box is the target area)", field="box")
        margin = finite(op.get("margin", 0), "margin", 0)
        alignment = op["alignment"]
        if alignment == "baseline":
            return _align_baselines(project, op, targets, ref)
        for item in targets:
            x, y, w, h = layout[item["id"]]
            bx, by, bw, bh = box
            if "left" in alignment:
                x = bx + margin
            if "right" in alignment:
                x = bx + bw - w - margin
            if "top" in alignment:
                y = by + margin
            if "bottom" in alignment:
                y = by + bh - h - margin
            if alignment in ("center", "center-x"):
                x = bx + (bw - w) / 2
            if alignment in ("center", "center-y"):
                y = by + (bh - h) / 2
            item.update(constraints={})
            item["x"], item["y"] = stored_origin(item, (x, y))
    elif kind == "constrain":
        constraints = op["constraints"]
        require(isinstance(constraints, dict), "Constraints must be an object")
        for anchor, expression in constraints.items():
            require(
                anchor in ("left", "right", "top", "bottom", "center-x", "center-y"),
                "Unknown constraint anchor",
            )
            if isinstance(expression, str):
                match = re.fullmatch(
                    r"(.+)\.(left|right|top|bottom|center-x|center-y)([+-]\d+(?:\.\d+)?)?", expression
                )
                require(match, "Invalid constraint expression")
                if match[1] != "canvas" and not match[1].startswith("guide:"):
                    expression = project.layer(match[1])["id"] + "." + match[2] + (match[3] or "")
            layer["constraints"][anchor] = expression
        for axes in (("left", "right", "center-x"), ("top", "bottom", "center-y")):
            present = [x for x in axes if x in layer["constraints"]]
            require(
                len(present) <= 1,
                f"Use one constraint per axis: {layer['name']!r} would have both {' and '.join(present)}; "
                "unconstrain it first to switch anchors",
            )
    elif kind == "unconstrain":
        from .render import stored_origin

        b = resolve_layout(project)[layer["id"]]
        layer["x"], layer["y"] = stored_origin(layer, b)
        layer["constraints"] = {}
    elif kind == "mask":
        action = op.get("action", "create")
        b = resolve_layout(project)[layer["id"]]
        if action in ("create", "from-selection", "import"):
            if action == "create":
                mask = Image.new("L", tuple(b[2:]), 255)
            elif action == "from-selection":
                mask = selection_image(project).crop((b[0], b[1], b[0] + b[2], b[1] + b[3]))
            else:
                mask = decode(read_bounded(op["path"], project.limits.max_asset_bytes), project.limits, "L")
            layer["mask"] = {"asset": add_image(project, mask, "masks"), "enabled": True}
        elif action == "delete":
            layer["mask"] = None
        else:
            require(layer["mask"], "Layer has no mask")
            if action in ("enable", "disable"):
                layer["mask"]["enabled"] = action == "enable"
            elif action == "invert":
                layer["mask"]["asset"] = add_image(
                    project, ImageOps.invert(project.image(layer["mask"]["asset"], "L")), "masks"
                )
            else:
                raise VixlError("invalid_mask", f"Unknown mask action: {action}")
    elif kind in ("effect", *EFFECTS):
        from .constants import EFFECT_DEFAULTS, STACK_EFFECTS

        name = op["name"] if kind == "effect" else kind
        require(len(layer["effects"]) < 256, "Effect limit reached", "resource_limit")
        effect = {
            "id": uid("fx"),
            "name": name,
            "amount": op.get("amount", op.get("value", EFFECT_DEFAULTS.get(name, 0))),
            "enabled": True,
            "selection": project.state["selection"],
        }
        for key in EFFECT_KEYS:
            if key in op:
                effect[key] = op[key]
        effect_valid(effect)
        if name == "lookup":
            require("lut" in effect, "A lookup effect names its LUT in lut", field="lut")
            require(effect["lut"] in project.state.get("luts", {}), f"Unknown LUT: {effect['lut']}", field="lut")
        if name not in STACK_EFFECTS:
            from .plugins import filter_plugin

            filter_plugin(name)
        layer["effects"].append(effect)
    elif kind.startswith("effect-"):
        effect = effect_ref(layer, op["effect"], "effect")
        if kind == "effect-remove":
            layer["effects"].remove(effect)
        elif kind == "effect-move":
            effects = layer["effects"]
            places = [key for key in ("to", "before", "after") if key in op]
            require(len(places) == 1, "effect-move takes exactly one of to, before or after", field="to")
            effects.remove(effect)
            if "to" in op:
                to = op["to"]
                if to in ("top", "first"):
                    index = 0
                elif to in ("bottom", "last"):
                    index = len(effects)
                else:
                    require(
                        isinstance(to, int) and not isinstance(to, bool) or str(to).isdigit(),
                        "to is a position (starting at 1), top or bottom",
                        field="to",
                    )
                    index = int(to) - 1
                    require(0 <= index <= len(effects), "Effect position out of range (starts at 1)", field="to")
            else:
                place = places[0]
                anchor = effect_ref({"effects": effects}, op[place], place)
                index = effects.index(anchor) + (place == "after")
            effects.insert(index, effect)
        elif kind in ("effect-enable", "effect-disable"):
            effect["enabled"] = kind == "effect-enable"
        elif kind == "effect-set":
            if "value" in op and "amount" not in op:
                op["amount"] = op["value"]
            for key in ("amount", *EFFECT_KEYS):
                if key in op:
                    effect[key] = op[key]
            effect_valid(effect)
            if effect["name"] == "lookup":
                require(effect["lut"] in project.state.get("luts", {}), f"Unknown LUT: {effect['lut']}", field="lut")
        else:
            raise VixlError("unknown_operation", f"Unknown operation: {kind}")
    elif kind == "rasterize":
        require(
            not layer.get("styles") and not layer.get("clip"),
            "Remove layer styles/clipping before rasterizing",
        )
        b = resolve_layout(project)[layer["id"]]
        # Bake everything the layer draws, including blur and group children past its box.
        image = layer_ink(project, layer, b)
        x, y = ink_origin(image, b)
        layer.update(
            type="raster",
            asset=add_image(project, image),
            width=image.width,
            height=image.height,
            x=x,
            y=y,
            rotation=0,
            flip_x=False,
            flip_y=False,
            effects=[],
            mask=None,
            opacity=1,
            constraints={},
            provenance={"type": "rasterized", "original": deepcopy(layer)},
        )
        if layer["provenance"]["original"]["type"] == "group":
            from .design import descendants

            removed = descendants(project, layer["id"])
            layers[:] = [item for item in layers if item["id"] not in removed]
        for key in ("text", "font", "size", "auto_size", "crop", "linked", "repeat"):
            layer.pop(key, None)
    elif kind == "preset-save":
        project.state["presets"][op["name"]] = deepcopy(layer["effects"])
    elif kind == "preset-apply":
        require(op["name"] in project.state["presets"], "Preset not found")
        saved = {item["name"] for item in project.state["presets"][op["name"]]}
        extra = sorted(set(op.get("overrides") or {}) - saved)
        require(not extra, f"overrides for {', '.join(map(repr, extra))} match no effect in preset {op['name']!r} "
                f"(it has {', '.join(sorted(saved)) or 'none'})", field="overrides", allowed=sorted(saved))
        for item in project.state["presets"][op["name"]]:
            item = deepcopy(item)
            item["id"] = uid("fx")
            item["selection"] = project.state["selection"]
            if item["name"] in op.get("overrides", {}):
                item["amount"] = float(op["overrides"][item["name"]])
            effect_valid(item)
            layer["effects"].append(item)
        require(len(layer["effects"]) <= 256, "Effect limit reached", "resource_limit")
    else:
        raise VixlError("unknown_operation", f"Unknown operation: {kind}")
