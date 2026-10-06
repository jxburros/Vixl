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
PIVOT_ANCHORS = {
    "top-left": [0, 0], "top": [0.5, 0], "top-right": [1, 0],
    "left": [0, 0.5], "center": [0.5, 0.5], "right": [1, 0.5],
    "bottom-left": [0, 1], "bottom": [0.5, 1], "bottom-right": [1, 1],
}
ALIASES = {
    "set_opacity": "opacity",
    "set_blend": "blend",
    "add_layer": "add",
    "remove_layer": "remove",
    "move_layer": "move",
    "set_effect": "effect",
    "make_selection": "select",
}

OPERATION_TYPES = list(DESIGN_TYPES + PIXEL_TYPES + ANIMATION_TYPES + RESOURCE_TYPES + BRUSH_TYPES + TIMELINE_TYPES + LAYOUT_TYPES + COLOR_TYPES + AUTOMATION_TYPES + CREATIVE_TYPES + CONTAINER_TYPES + AUTHORING_TYPES + ORGANIC_TYPES + IRREGULAR_TYPES + GUIDE_TYPES + RICH_TYPES + PAGE_TYPES + FORM_TYPES + DRAWING_TYPES + STACK_TYPES + SELECTOR_TYPES + LINK_TYPES) + [
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
    "rasterize",
    "variable",
    "preset-save",
    "preset-apply",
]


def embed_font_file(project, layer):
    if layer["font"] not in project.assets and Path(layer["font"]).is_file():
        data = read_bounded(layer["font"], project.limits.max_asset_bytes)
        name = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[name] = data
        layer["font"] = name


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
    project.limits.size(layer["width"], layer["height"])
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
    kind = ALIASES.get(kind, kind)
    require(isinstance(kind, str), "Operation requires a type")
    target = op.get("target", op.get("layer"))
    if target is not None and kind in IN_PLACE_TYPES:
        from .inplace import execute as execute_in_place

        return execute_in_place(project, {**op, "type": kind, "target": target})
    if kind in STACK_POSITIONING:
        from .stacks import guard

        guard(project, op, target)
    if kind in STACK_TYPES:
        from .stacks import execute as execute_stack

        return execute_stack(project, op)
    if kind in SELECTOR_TYPES:
        from .selectors import execute as execute_selectors
        return execute_selectors(project, op)
    if kind in PAGE_TYPES:
        from .pages import execute as execute_pages
        return execute_pages(project, op)
    if kind in FORM_TYPES:
        from .forms import execute as execute_forms
        return execute_forms(project, op)
    if kind in LINK_TYPES:
        from .links import execute as execute_links
        return execute_links(project, op)
    if kind in DRAWING_TYPES:
        from .drawing import execute as execute_drawing
        return execute_drawing(project, op)
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
        if "asset" in op:
            image = project.image(op["asset"])
            asset = op["asset"]
            provenance = op.get("provenance", {"type": "embedded"})
        else:
            source = Path(op["path"]).resolve()
            data = read_bounded(source, project.limits.max_asset_bytes)
            asset, image = add_encoded(project, data)
            provenance = {
                "type": "imported",
                "original_filename": source.name,
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        layer = new_layer(
            op["name"] if "name" in op else default_name(project, Path(op.get("path", "image")).stem),
            "raster",
            *image.size,
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
    elif kind == "move":
        from .render import stored_origin

        bounds = resolve_layout(project)[layer["id"]]
        origin = list(bounds[:2])
        for i, axis in enumerate(("x", "y")):
            if axis in op:
                origin[i] = finite(op[axis], axis) + (bounds[i] if op.get("relative") else 0)
        layer["x"], layer["y"] = stored_origin(layer, origin)
        layer["constraints"] = {}
    elif kind in ("resize", "scale"):
        w, h = layer["width"], layer["height"]
        if kind == "scale":
            # A negative factor mirrors that axis (value: both axes) and scales by its size.
            require(any(key in op for key in ("value", "x", "y")), "Scale requires value, x or y", field="value")
            both = op.get("value", 1)
            factors = {"value": both, "x": op.get("x", both), "y": op.get("y", both)}
            for name, factor in factors.items():
                finite(factor, f"scale {name}")
                require(0.001 <= abs(factor) <= 100, f"scale {name} must be 0.001–100 in size (negative mirrors); got {factor}", field=name)
            if factors["x"] < 0 or factors["y"] < 0:
                require(layer["type"] != "field", "Negative scale mirrors the layer; PDF form fields are upright rectangles", field="target")
            for axis, key in (("x", "flip_x"), ("y", "flip_y")):
                if factors[axis] < 0:
                    layer[key] = not layer[key]
            w, h = max(1, round(w * abs(factors["x"]))), max(1, round(h * abs(factors["y"])))
        else:
            require("width" in op or "height" in op, "Resize requires width or height")
            one_side = ("width" in op) != ("height" in op)
            require(one_side or not op.get("keep_aspect"),
                    "keep_aspect scales the other side proportionally: give width or height, not both",
                    field="keep_aspect")
            # A side that is not given keeps its size, except on photos, where stretching one axis is
            # rarely meant: image layers scale proportionally unless keep_aspect is false.
            if one_side and op.get("keep_aspect", layer["type"] == "raster"):
                if "width" in op:
                    w, h = op["width"], max(1, round(h * op["width"] / w))
                else:
                    w, h = max(1, round(w * op["height"] / h)), op["height"]
            else:
                w, h = op.get("width", w), op.get("height", h)
        project.limits.size(w, h)
        layer.update(width=w, height=h, auto_size=False)
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
                require(value in PIVOT_ANCHORS, f"Unknown pivot anchor {value!r}; use {', '.join(PIVOT_ANCHORS)}", field="value")
                value = PIVOT_ANCHORS[value]
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
        margin = finite(op.get("margin", 0), "margin", 0)
        alignment = op["alignment"]
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
        from .constants import ARTISTIC_DEFAULTS

        name = op["name"] if kind == "effect" else kind
        require(len(layer["effects"]) < 256, "Effect limit reached", "resource_limit")
        effect = {
            "id": uid("fx"),
            "name": name,
            "amount": op.get("amount", op.get("value", ARTISTIC_DEFAULTS.get(name, 0))),
            "enabled": True,
            "selection": project.state["selection"],
        }
        for key in ("seed", "radius", "strength", "black", "white", "points", "shadow_color", "highlight_color",
                    *DENOISE_KEYS):
            if key in op:
                effect[key] = op[key]
        effect_valid(effect)
        if name not in EFFECTS:
            from .plugins import filter_plugin

            filter_plugin(name)
        layer["effects"].append(effect)
    elif kind.startswith("effect-"):
        ref = op["effect"]
        if isinstance(ref, int) or str(ref).isdigit():
            index = int(ref) - 1
            require(0 <= index < len(layer["effects"]), "Effect index out of range (starts at 1)")
            effect = layer["effects"][index]
        else:
            effect = next((x for x in layer["effects"] if x["id"] == ref), None)
            require(effect, "Effect not found")
        if kind == "effect-remove":
            layer["effects"].remove(effect)
        elif kind in ("effect-enable", "effect-disable"):
            effect["enabled"] = kind == "effect-enable"
        elif kind == "effect-set":
            if "value" in op and "amount" not in op:
                op["amount"] = op["value"]
            for key in ("amount", "seed", "radius", "strength", "black", "white", "points", "shadow_color", "highlight_color",
                        *DENOISE_KEYS):
                if key in op:
                    effect[key] = op[key]
            effect_valid(effect)
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
        for key in ("text", "font", "size", "auto_size", "crop", "linked", "repeat", "lookup"):
            layer.pop(key, None)
    elif kind == "preset-save":
        project.state["presets"][op["name"]] = deepcopy(layer["effects"])
    elif kind == "preset-apply":
        require(op["name"] in project.state["presets"], "Preset not found")
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

