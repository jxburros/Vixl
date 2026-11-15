"""Layered PSD import: pixel layers, groups, visibility, opacity, blend modes and layer masks.

The file is read by ``vixl.psd_reader`` (8-bit RGB, raw or RLE channels, bounded by the document's
``Limits``). Each pixel layer becomes an image layer at its place, each layer group a group, in the same
order, with its name, visibility, opacity and blend mode (the modes Vixl has; others draw as normal and
are reported). A layer mask becomes the layer's mask. Type layers, smart objects and shape layers import
as the pixels the file stores for them; a type layer's text, font and size are listed in the result.

What the file's pixels do not carry is not applied and is reported under ``not_applied``: adjustment
layers, fill layers without pixels, layer effects, clipping to the layer below, vector masks, mask
density or feather, a group's mask and pass-through blending. ``mode='appearance'`` imports the file's
merged image as one layer instead, which looks as it did in Photoshop.

Into an empty document the import takes the PSD's canvas size; into a document with layers, the PSD's
layers arrive as one group at their own coordinates.
"""

import re

import numpy as np
from PIL import Image

from ... import psd_reader as reader
from ...errors import VixlError, require


def import_psd(project, data, *, name="import", mode="editable"):
    document = reader.read(data, project.limits)
    candidate = project.clone()
    adopt = not candidate.state["layers"] and not candidate.state.get("pages")
    operations = []
    if adopt:
        canvas = {"type": "canvas", "width": document.width, "height": document.height, "background": "transparent"}
        if document.dpi and 36 <= document.dpi <= 2400:
            canvas["dpi"] = round(document.dpi, 3)
        operations.append(canvas)
    warnings = []
    if mode != "appearance" and not any(layer.section is None and all(layer.size) for layer in document.layers):
        warnings.append("The PSD has no pixel layers; imported its merged image as one layer")
        mode = "appearance"
    if mode == "appearance":
        return _merged(project, candidate, document, operations, name, adopt, warnings)
    return Builder(project, candidate, document, operations, name, adopt, warnings).run()


def _commit(project, candidate, operations):
    require(len(operations) <= project.limits.max_operations, "PSD has too many layers", "resource_limit")
    return candidate.apply(operations, detail="compact")


def _merged(project, candidate, document, operations, name, adopt, warnings):
    from ...assets import add_image
    from ...operations import taken

    asset = add_image(candidate, Image.fromarray(reader.composite(document), "RGBA"))
    require(taken(candidate, name) is None, f"Layer name already exists: {name}", field="name")
    operations.append({"type": "add", "asset": asset, "name": name, "x": 0, "y": 0})
    result = _commit(project, candidate, operations)
    project.__dict__.update(candidate.__dict__)
    return {**result, "mode": "appearance", "canvas": "adopted" if adopt else "kept",
            "size": [document.width, document.height],
            "warnings": [*warnings, "PSD imported as one image layer (its merged image).",
                         *result.get("warnings", [])]}


class Builder:
    def __init__(self, project, candidate, document, operations, name, adopt, warnings):
        self.project, self.candidate, self.document = project, candidate, document
        self.operations, self.name, self.adopt, self.warnings = operations, name, adopt, warnings
        self.used = set()
        self.masks = {}  # layer name: (mask image, enabled)
        self.not_applied, self.texts = [], []
        self.counts = {"image": 0, "group": 0}

    def unique(self, text, fallback="Layer"):
        from ...operations import taken

        base = re.sub(r"\s+", " ", str(text or "")).strip()[:190] or fallback
        name, index = base, 2
        while name in self.used or taken(self.candidate, name) is not None:
            name, index = f"{base} {index}", index + 1
        self.used.add(name)
        return name

    def lost(self, name, reason):
        self.not_applied.append({"layer": name, "reason": reason})

    def finish(self, layer, name, opacity):
        """Operations on the layer just made (the active one): opacity, blend mode and visibility."""
        if opacity < 0.9995:
            self.operations.append({"type": "opacity", "value": round(opacity, 4)})
        blend = reader.BLENDS.get(layer.blend.encode("latin-1"))
        if blend is None:
            self.lost(name, f"blend mode {layer.blend.strip()!r} has no Vixl equivalent; drawn as normal")
        elif blend != "normal":
            self.operations.append({"type": "blend", "value": blend})
        if not layer.visible:
            self.operations.append({"type": "hide"})
        if layer.clipping:
            self.lost(name, "clipped to the layer below in Photoshop; imported unclipped")
        if any(tag in reader.EFFECTS for tag in layer.blocks):
            self.lost(name, "layer effects are not imported")
        if any(tag in reader.VECTOR_MASKS for tag in layer.blocks):
            self.lost(name, "the vector mask is not applied")

    def mask(self, layer, name):
        mask = layer.mask
        pixels = reader.mask_pixels(self.document, layer)
        if pixels is None:
            return
        left, top, right, bottom = layer.box
        full = np.full((bottom - top, right - left), mask.default, np.uint8)
        x0, y0 = max(left, mask.box[0]), max(top, mask.box[1])
        x1, y1 = min(right, mask.box[2]), min(bottom, mask.box[3])
        if x1 > x0 and y1 > y0:
            full[y0 - top:y1 - top, x0 - left:x1 - left] = pixels[y0 - mask.box[1]:y1 - mask.box[1],
                                                                x0 - mask.box[0]:x1 - mask.box[0]]
        if full.min() == 255:
            return  # A mask that shows every pixel (some writers add one to each layer) is no mask.
        self.masks[name] = (Image.fromarray(full, "L"), not mask.disabled)
        if mask.parameters:
            self.lost(name, "mask density or feather is not applied")

    def pixel_layer(self, layer):
        from ... import calls
        from ...assets import add_image

        calls.check_cancelled()
        adjustment = next((reader.ADJUSTMENTS[tag] for tag in layer.blocks if tag in reader.ADJUSTMENTS), None)
        if adjustment:
            self.lost(layer.name, f"{adjustment} adjustment layer is not applied")
            return None
        if not all(layer.size):
            fill = next((reader.FILLS[tag] for tag in layer.blocks if tag in reader.FILLS), None)
            self.lost(layer.name, f"{fill} layer has no pixels in the file; skipped" if fill
                      else "empty layer skipped")
            return None
        name = self.unique(layer.name)
        asset = add_image(self.candidate, Image.fromarray(reader.layer_pixels(self.document, layer), "RGBA"))
        self.operations.append({"type": "add", "asset": asset, "name": name, "x": layer.box[0], "y": layer.box[1]})
        self.counts["image"] += 1
        self.finish(layer, name, layer.opacity * layer.fill_opacity)
        self.mask(layer, name)
        if layer.type_data is not None:
            from ...psd_text import Malformed, parse_type_block

            try:
                parsed = parse_type_block(layer.type_data)
            except (Malformed, ValueError):
                self.lost(name, "the type layer's text could not be read; imported as an image")
            else:
                self.texts.append({"layer": name, **{key: parsed[key] for key in ("text", "font", "size", "color")
                                                     if parsed.get(key) is not None}})
        return name

    def run(self):
        stack, blended = [[]], [False]  # per open group: its members, and whether one has a blend mode
        for layer in self.document.layers:  # bottom to top
            if layer.section is None and all(layer.size) and reader.BLENDS.get(
                    layer.blend.encode("latin-1"), "normal") != "normal":
                blended[-1] = True
            if layer.section == 3:
                stack.append([])
                blended.append(False)
            elif layer.section in (1, 2):
                if len(stack) < 2:
                    raise VixlError("invalid_psd", "Malformed PSD: a layer group has no end marker")
                members, inner = stack.pop(), blended.pop()
                if layer.blend == "pass":
                    blended[-1] = blended[-1] or inner  # those layers reach through this group too
                if not members:
                    self.lost(layer.name, "empty group skipped")
                    continue
                name = self.unique(layer.name, "Group")
                self.operations.append({"type": "group", "name": name, "targets": members})
                self.counts["group"] += 1
                self.finish(layer, name, layer.opacity)
                if layer.mask is not None and layer.mask.data is not None:
                    self.lost(name, "the group's mask is not applied")
                if layer.blend == "pass" and inner:
                    self.lost(name, "a pass-through group in Photoshop: here its layers' blend modes apply inside "
                              "the group only")
                stack[-1].append(name)
            else:
                name = self.pixel_layer(layer)
                if name:
                    stack[-1].append(name)
        if len(stack) != 1:
            raise VixlError("invalid_psd", "Malformed PSD: a layer group is not closed")
        tops = stack[0]
        require(tops, "Nothing in the PSD could be imported as layers; svg_mode='appearance' imports its merged "
                "image", "invalid_psd")
        root = None
        if not self.adopt:
            root = self.unique(self.name, "import")
            self.operations.append({"type": "group", "name": root, "targets": tops})
        result = _commit(self.project, self.candidate, self.operations)
        self.apply_masks()
        self.project.__dict__.update(self.candidate.__dict__)
        result.update(mode="layers", canvas="adopted" if self.adopt else "kept",
                      size=[self.document.width, self.document.height],
                      layers={key: value for key, value in self.counts.items() if value})
        if root:
            result["group"] = root
        warnings = self.warnings
        if self.texts:
            result["text"] = self.texts
            warnings.append(f"{len(self.texts)} type layer(s) were imported as images of their text; the text, font "
                            "and size are listed under text")
        if self.not_applied:
            result["not_applied"] = self.not_applied
            warnings.append(f"{len(self.not_applied)} Photoshop feature(s) were not applied (see not_applied); "
                            "svg_mode='appearance' imports the file's merged image instead")
        if warnings:
            result["warnings"] = [*warnings, *result.get("warnings", [])]
        return result

    def apply_masks(self):
        """Attach the layer masks to the layers the batch made, inside the same revision."""
        if not self.masks:
            return
        from ...assets import add_image
        from ...validation import check_state

        candidate = self.candidate
        for name, (image, enabled) in self.masks.items():
            layer = candidate.find_layer(name)
            layer["mask"] = {"asset": add_image(candidate, image, "masks"), "enabled": enabled}
        check_state(candidate, candidate.state)
        if candidate.transaction is None:
            candidate._amend_head()
        candidate._inspected = None
