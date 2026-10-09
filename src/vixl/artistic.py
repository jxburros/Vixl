"""Deterministic, local artistic treatments. No models or network calls."""

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .constants import ARTISTIC_DEFAULTS


def blend(original, changed, amount):
    return Image.blend(original, changed, amount / 100)


def luminance(image):
    # Use Pillow's grayscale weights, also used by SVG component filters.
    return np.asarray(ImageOps.grayscale(image), dtype=np.float32)


def edge_filter(image, kernel):
    """Extend edge pixels before convolution; avoid an artificial picture frame."""
    values = np.asarray(image)
    padding = ((1, 1), (1, 1)) + (((0, 0),) if values.ndim == 3 else ())
    padded = Image.fromarray(np.pad(values, padding, mode="edge"))
    return padded.filter(kernel).crop((1, 1, image.width + 1, image.height + 1))


def emboss_kernel(offset):
    """Pillow's EMBOSS (each pixel minus its down-left neighbour, on mid grey) with the neighbour
    at ``offset`` (dx, dy, y down) instead, spread bilinearly over the 3×3 ring."""
    dx, dy = offset
    reach = max(abs(dx), abs(dy), 1e-9)
    dx, dy = dx / reach, dy / reach
    weights = [0.0] * 9
    weights[4] = 1.0
    x0, y0 = math.floor(dx), math.floor(dy)
    for x in (x0, x0 + 1):
        for y in (y0, y0 + 1):
            share = max(0.0, 1 - abs(dx - x)) * max(0.0, 1 - abs(dy - y))
            if share and -1 <= x <= 1 and -1 <= y <= 1:
                # Pillow's kernel rows run bottom to top.
                weights[(1 - y) * 3 + x + 1] -= share
    return ImageFilter.Kernel((3, 3), weights, 1, 128)


def mode_colors(rgb, radius):
    """Each pixel takes the color of a nearby pixel with the most common brightness in its
    (2r+1)² window, nearest first. A mode filter run on each channel separately can combine red
    from one group of pixels with green from another, painting colors that are not in the image."""
    size = 2 * radius + 1
    key = np.asarray(ImageOps.grayscale(rgb).filter(ImageFilter.ModeFilter(size)))
    gray = np.pad(np.asarray(ImageOps.grayscale(rgb)), radius, mode="edge")
    colors = np.pad(np.asarray(rgb), ((radius, radius), (radius, radius), (0, 0)), mode="edge")
    h, w = key.shape
    result = np.asarray(rgb).copy()
    found = np.zeros((h, w), bool)
    offsets = sorted(((dy, dx) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)),
                     key=lambda o: (o[0] ** 2 + o[1] ** 2, o))
    for dy, dx in offsets:
        window = (slice(radius + dy, radius + dy + h), slice(radius + dx, radius + dx + w))
        match = ~found & (gray[window] == key)
        result[match] = colors[window][match]
        found |= match
    return Image.fromarray(result)


def remap(image, coordinates):
    """Bilinear spatial filters, chunked and premultiplied to protect alpha edges."""
    source = np.asarray(image)
    output = np.empty_like(source)
    h, w = source.shape[:2]
    for first in range(0, h, 128):
        yy, xx = np.mgrid[first : min(first + 128, h), :w].astype(np.float32)
        x, y = coordinates(xx, yy)
        x, y = np.clip(x, 0, w - 1), np.clip(y, 0, h - 1)
        x0, y0 = x.astype(np.int32), y.astype(np.int32)
        x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        result = np.zeros((*x.shape, 4), dtype=np.float32)
        for ix, iy, weight in (
            (x0, y0, (1 - fx) * (1 - fy)),
            (x1, y0, fx * (1 - fy)),
            (x0, y1, (1 - fx) * fy),
            (x1, y1, fx * fy),
        ):
            pixel = source[iy, ix].astype(np.float32)
            pixel[..., :3] *= pixel[..., 3:] / 255
            result += pixel * weight
        result[..., :3] *= 255 / np.maximum(result[..., 3:], 1e-6)
        output[first : first + len(x)] = np.uint8(np.clip(result, 0, 255) + 0.5)
    return Image.fromarray(output)


def _blur(values, radius, pad=0):
    """Gaussian blur of 0-255 values. ``pad`` is the value assumed beyond the edges (Pillow alone
    repeats the edge pixels, which hides the boundary of a layer that fills its own box)."""
    reach = math.ceil(3 * radius) + 1
    padded = np.pad(np.uint8(np.clip(values, 0, 255) + 0.5), reach, mode="constant", constant_values=pad)
    blurred = np.asarray(Image.fromarray(padded, "L").filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    return blurred[reach:-reach, reach:-reach]


def pencil_sketch(gray, alpha, radius):
    """Graphite on paper: dodge lines along tone edges plus hatching whose weight follows the tone.

    Transparent pixels count as white paper, so the outline of a flat shape draws, and the hatching
    keeps the value of a flat fill instead of washing it out to white."""
    coverage = np.asarray(alpha, dtype=np.float32) / 255
    tone = np.asarray(gray, dtype=np.float32) * coverage + 255 * (1 - coverage)
    blurred = _blur(tone, max(radius, 0.5), pad=255)
    lines = np.clip(tone * 255 / np.maximum(blurred, 1), 0, 255)
    h, w = tone.shape
    spacing = max(4, min(10, round(min(w, h) / 30)))
    y, x = np.arange(h, dtype=np.int32)[:, None], np.arange(w, dtype=np.int32)[None, :]
    darkness = 1 - tone / 255
    hatch = ((x + y) % spacing) < max(1, spacing * 0.25)
    cross = (((x - y) % spacing) < max(1, spacing * 0.25)) & (darkness > 0.5)
    grain = 0.75 + 0.5 * np.random.default_rng(0).random((h, w), dtype=np.float32)
    shade = darkness * (0.15 + 0.6 * (hatch | cross) * grain)
    return Image.fromarray(np.uint8(np.clip(lines * (1 - np.clip(shade, 0, 0.85)), 0, 255) + 0.5)).convert("RGB")


def watercolor(rgb, alpha, seed):
    """A translucent wash: simplified colors lifted toward the paper, pigment pooled in a darker rim
    inside every edge (shape outlines and color boundaries), blotchy density and paper grain. Pixels
    outside the layer's box count as paper, so a shape that fills its box still gets its rim."""
    h, w = rgb.height, rgb.width
    simple = ImageOps.posterize(rgb.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.SMOOTH_MORE), 4)
    values = np.asarray(simple, dtype=np.float32)
    reach = max(2.0, min(w, h) * 0.035)
    opacity = np.asarray(alpha, dtype=np.float32)
    rim = np.clip((opacity - _blur(opacity, reach)) / 255 * 2.5, 0, 1)
    coverage = opacity / 255
    lum = np.asarray(ImageOps.grayscale(simple), dtype=np.float32) * coverage + 255 * (1 - coverage)
    rim = np.maximum(rim, np.clip((_blur(lum, reach, pad=255) - lum) / 64, 0, 1) * (coverage > 0))
    rng = np.random.default_rng(seed)
    cells = (max(2, h // 24 + 2), max(2, w // 24 + 2))
    blots = Image.fromarray(rng.standard_normal(cells).astype(np.float32), "F").resize((w, h), Image.Resampling.BICUBIC)
    density = 1 + 0.08 * np.asarray(blots, dtype=np.float32)
    wash = values * 0.78 + 255 * 0.22
    pigment = 255 - (255 - wash) * (density * (1 + 0.9 * rim))[..., None]
    paper = rng.integers(-6, 7, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.uint8(np.clip(pigment + paper, 0, 255) + 0.5))


def artistic_filter(image, effect):
    name = effect["name"]
    amount = effect.get("amount", ARTISTIC_DEFAULTS[name])
    radius = effect.get("radius")
    rgb, alpha = image.convert("RGB"), image.getchannel("A")
    gray = ImageOps.grayscale(rgb)
    w, h = image.size
    if name in ("swirl", "ripple", "wave", "glass"):
        if amount == 0:
            return image.copy()
        if name == "glass":
            rng = np.random.default_rng(effect.get("seed", 0))
            cell = max(1, int(radius or 12))
            displacement = []
            for _ in range(2):
                noise = Image.fromarray(
                    rng.integers(
                        0, 256, (max(2, math.ceil(h / cell)), max(2, math.ceil(w / cell))), dtype=np.uint8
                    )
                ).resize((w, h), Image.Resampling.BICUBIC)
                displacement.append(np.asarray(noise, dtype=np.float32) / 127.5 - 1)

        def coordinates(x, y):
            if name == "wave":
                return x + amount * np.sin(y * 2 * np.pi / (radius or 32)), y
            if name == "glass":
                iy, ix = y.astype(int), x.astype(int)
                return x + displacement[0][iy, ix] * amount, y + displacement[1][iy, ix] * amount
            cx, cy = (w - 1) / 2, (h - 1) / 2
            dx, dy = x - cx, y - cy
            distance = np.hypot(dx, dy)
            if name == "swirl":
                extent = max(1, min(w, h) * (radius or 0.8) / 2)
                angle = np.arctan2(dy, dx) - math.radians(amount) * np.maximum(0, 1 - distance / extent) ** 2
                return cx + distance * np.cos(angle), cy + distance * np.sin(angle)
            offset = amount * np.sin(distance * 2 * np.pi / (radius or 32))
            factor = (distance + offset) / np.maximum(distance, 1e-6)
            return cx + dx * factor, cy + dy * factor

        return remap(image, coordinates)
    if name == "sepia":
        a = np.asarray(rgb, dtype=np.float32)
        a = a @ np.array([[0.393, 0.349, 0.272], [0.769, 0.686, 0.534], [0.189, 0.168, 0.131]])
        changed = Image.fromarray(np.uint8(np.clip(a, 0, 255)))
        result = blend(rgb, changed, amount)
    elif name == "duotone":
        from .render import color

        low = np.array(color(effect.get("shadow_color", "#172544"))[:3], dtype=float)
        high = np.array(color(effect.get("highlight_color", "#ffe6ac"))[:3], dtype=float)
        t = luminance(rgb)[..., None] / 255
        changed = Image.fromarray(np.uint8(low + (high - low) * t + 0.5))
        result = blend(rgb, changed, amount)
    elif name == "solarize":
        result = ImageOps.solarize(rgb, int(amount))
    elif name == "pixelate":
        cell = int(amount)
        # Average colors in premultiplied space so transparent colored pixels do
        # not contaminate visible blocks. Spatial filters transform alpha too.
        size = (max(1, math.ceil(w / cell)), max(1, math.ceil(h / cell)))
        return (
            image.convert("RGBa")
            .resize(size, Image.Resampling.BOX)
            .resize((w, h), Image.Resampling.NEAREST)
            .convert("RGBA")
        )
    elif name in ("halftone", "crosshatch"):
        from .render import color

        ink = color(effect.get("color", "black"))[:3]
        cell = int(amount)
        result = Image.new("RGB", image.size, "white")
        draw = ImageDraw.Draw(result)
        values = np.asarray(gray)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                darkness = 1 - float(values[y : y + cell, x : x + cell].mean()) / 255
                if name == "halftone":
                    r = cell * math.sqrt(darkness / math.pi)
                    cx, cy = x + cell / 2, y + cell / 2
                    if r:
                        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ink)
                else:
                    if darkness > 0.2:
                        draw.line((x, y + cell - 1, x + cell - 1, y), fill="black")
                    if darkness > 0.45:
                        draw.line((x, y, x + cell - 1, y + cell - 1), fill="black")
                    if darkness > 0.7:
                        draw.line((x, y + cell // 2, x + cell - 1, y + cell // 2), fill="black", width=2)
    elif name in ("ink-blot", "stamp", "photocopy"):
        if name == "ink-blot":
            size = round(radius if radius is not None else 2)
            softened = gray.filter(ImageFilter.GaussianBlur(size / 2))
            ink = softened.point(lambda p: 255 if p < amount else 0)
            if size:
                ink = ink.filter(ImageFilter.MaxFilter(2 * size + 1)).filter(
                    ImageFilter.MinFilter(2 * size + 1)
                )
            result = ImageOps.invert(ink).convert("RGB")
        elif name == "stamp":
            result = gray.point(lambda p: 255 if p >= amount else 0).convert("RGB")
        else:
            edges = edge_filter(gray, ImageFilter.FIND_EDGES)
            result = (
                ImageChops.subtract(gray, edges).point(lambda p: 255 if p >= amount else 0).convert("RGB")
            )
    elif name == "pencil-sketch":
        changed = pencil_sketch(gray, alpha, radius if radius is not None else 12)
        result = blend(rgb, changed, amount)
    elif name == "charcoal":
        blur = gray.filter(ImageFilter.GaussianBlur(radius if radius is not None else 2))
        b = np.asarray(blur, dtype=np.float32)
        edge = np.asarray(edge_filter(gray, ImageFilter.FIND_EDGES), dtype=np.float32)
        changed = Image.fromarray(np.uint8(np.clip(255 - edge * 2 - (255 - b) * 0.4, 0, 255))).convert("RGB")
        result = blend(rgb, changed, amount)
    elif name in ("find-edges", "emboss"):
        kernel = ImageFilter.FIND_EDGES if name == "find-edges" else emboss_kernel(effect.get("_light", (-1, 1)))
        changed = edge_filter(rgb, kernel)
        result = blend(rgb, changed, amount)
    elif name == "oil-paint":
        result = ImageOps.posterize(mode_colors(rgb, int(amount)), 5)
    elif name == "watercolor":
        result = blend(rgb, watercolor(rgb, alpha, effect.get("seed", 0)), amount)
    else:
        raise ValueError(f"Unknown artistic filter: {name}")
    result = result.convert("RGBA")
    result.putalpha(alpha)
    return result
