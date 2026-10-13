"""Compact palette-indexed pixel layers and deterministic integer-coordinate drawing."""

from collections import deque
from copy import deepcopy

import numpy as np
from PIL import Image, ImageDraw

from .errors import require
from .model import new_layer

PIXEL_TYPES = ("pixel-art", "pixel-draw", "pixel-palette")
MAX_GRID = 256
LIGHTS = ("auto", "top-left", "top", "top-right")
SHADING = {"light": "auto", "colors": 16, "highlight": True}
RAMPED = 0.35  # a colour whose hand-drawn tones already cover this share of its area is left as drawn
# Tones as (OKLab lightness change, hue they turn toward, degrees turned): shadows go darker and toward
# violet (yellow turns orange, green turns teal), lights go lighter and toward warm yellow.
SHADOW, HIGHLIGHT, OUTLINE = (-0.13, 300.0, 22.0), (0.09, 90.0, 12.0), (-0.55, 300.0, 30.0)
DARK = 0.32  # OKLab lightness at or below which a colour reads as an outline


def validate_pixel(layer, state):
    from .render import color
    from .design import resolve_color

    rows, palette = layer["pixels"], layer["palette"]
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_GRID, "Pixel grid height must be 1–256")
    require(all(isinstance(row, str) for row in rows), "Pixel rows must be strings")
    width = len(rows[0])
    require(1 <= width <= MAX_GRID, f"Pixel rows need equal widths of 1–256; row 0 has {width} characters")
    for index, row in enumerate(rows):
        require(
            len(row) == width,
            f"Pixel rows need equal widths of 1–256; row {index} (counting from 0) has {len(row)} characters "
            f"but row 0 has {width}",
        )
    require(isinstance(palette, dict) and 1 <= len(palette) <= 94, "Palette needs 1–94 symbols")
    for symbol, value in palette.items():
        require(
            isinstance(symbol, str) and len(symbol) == 1 and 33 <= ord(symbol) <= 126,
            "Palette symbols must be single printable non-space ASCII characters",
        )
        color(resolve_color(value, state))
    require(set("".join(rows)) <= palette.keys(), "Every pixel must have a palette entry")


def validate_finish(layer):
    """The ``shading`` and ``outline`` settings of a pixel layer."""
    shading = layer.get("shading")
    if isinstance(shading, dict):
        unknown = sorted(set(shading) - set(SHADING))
        require(not unknown, f"Unknown shading setting(s) {unknown}; available: light, colors, highlight", field="shading")
        require(shading.get("light", "auto") in LIGHTS, f"shading light is one of {', '.join(LIGHTS)}", field="shading")
        colors = shading.get("colors", SHADING["colors"])
        require(isinstance(colors, int) and not isinstance(colors, bool) and 2 <= colors <= 64,
                "shading colors is the most opaque colours the sprite may use, 2-64", field="shading")
        require(isinstance(shading.get("highlight", True), bool), "shading highlight is true or false", field="shading")
    else:
        require(shading is None or isinstance(shading, bool), "shading is true, false or {light, colors, highlight}",
                field="shading")
    outline = layer.get("outline")
    require(outline is None or isinstance(outline, (bool, str)), "outline is true, false or a colour", field="outline")


def _lab(rgba):
    from .colors import srgb_to_oklab

    return srgb_to_oklab([c / 255 for c in rgba[:3]])


def tone(rgba, shift):
    """``rgba`` (0-255) moved by a tone ``(lightness change, hue to turn toward, degrees)``, as hex."""
    import math

    from .colors import gamut_map, hex_of

    lightness, a, b = _lab(rgba)
    chroma, hue = math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360
    change, toward, turn = shift
    delta = (toward - hue + 180) % 360 - 180
    hue = math.radians(hue + max(-turn, min(turn, delta)))
    chroma *= 1.05 if change < 0 else 0.9
    lab = (min(0.98, max(0.08, lightness + change)), chroma * math.cos(hue), chroma * math.sin(hue))
    return hex_of((*gamut_map(lab), 1.0))


def _runs(index, axis):
    """For each pixel: how many pixels of its own colour follow it along ``axis`` (before, after)."""
    grid = index if axis == 1 else index.T
    before, after = np.zeros(grid.shape, int), np.zeros(grid.shape, int)
    for x in range(1, grid.shape[1]):
        same = grid[:, x] == grid[:, x - 1]
        before[:, x] = np.where(same, before[:, x - 1] + 1, 0)
    for x in range(grid.shape[1] - 2, -1, -1):
        same = grid[:, x] == grid[:, x + 1]
        after[:, x] = np.where(same, after[:, x + 1] + 1, 0)
    return (before, after) if axis == 1 else (before.T, after.T)


def finished(project, layer):
    """The rows and palette a pixel layer draws with its ``shading`` and ``outline`` applied.

    The stored rows are never changed, so a palette swap or a redraw carries through. ``outline``
    rings the silhouette with a 1 px line on the transparent cells around it (in the darkest
    palette colour, or the given colour), unless most of the silhouette's edge is dark already.
    ``shading`` darkens the band of each colour area that faces away from the light and lights the
    band that faces it, in hue-shifted tones, largest areas first, while the sprite stays within
    ``colors`` opaque colours. Colours that already have a hand-drawn ramp, dark outline colours and
    areas thinner than 3 pixels are left as drawn."""
    rows, palette = layer["pixels"], dict(layer["palette"])
    shading, outline = layer.get("shading"), layer.get("outline")
    if not shading and not outline:
        return rows, palette
    from .design import resolve_color
    from .render import color

    symbols = list(palette)
    rgba = {key: color(resolve_color(value, project.state)) for key, value in palette.items()}
    index = np.array([[symbols.index(ch) for ch in row] for row in rows])
    alpha = np.array([rgba[key][3] for key in symbols])[index]
    solid = alpha == 255
    if not solid.any() or solid.all():
        return rows, palette
    lab = {key: _lab(rgba[key]) for key in symbols}
    used = [symbols[i] for i in np.unique(index[solid])]
    spare = [chr(c) for c in range(33, 127) if chr(c) not in palette]
    out = np.array([list(row) for row in rows])
    settings = {**SHADING, **(shading if isinstance(shading, dict) else {})}
    budget = settings["colors"] - len({rgba[key] for key in used})
    if outline:
        padded = np.pad(solid, 1)
        touching = padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]
        edge = solid & ~(padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:])
        dark = np.array([lab[key][0] <= DARK for key in symbols])[index]
        ring = touching & ~solid & (alpha == 0)
        if ring.any() and (dark & edge).sum() < 0.5 * edge.sum():
            if isinstance(outline, str):
                ink = color(resolve_color(outline, project.state))
            else:
                darkest = min(used, key=lambda key: lab[key][0])
                largest = max(used, key=lambda key: int((index == symbols.index(key)).sum()))
                # No dark colour to reuse: the largest area's colour taken almost to the shadow tone.
                ink = rgba[darkest] if lab[darkest][0] <= DARK else color(tone(rgba[largest], OUTLINE))
            existing = next((key for key in used if rgba[key] == ink), None)
            if existing is None and spare and budget > 0:
                existing = spare.pop(0)
                palette[existing] = "#%02x%02x%02x" % tuple(ink[:3])
                budget -= 1
            if existing is not None:
                out[ring] = existing
    if shading and budget > 0:
        left, right = _runs(index, 1)
        above, below = _runs(index, 0)
        width, height = left + right + 1, above + below + 1
        ramps = {key: _ramp(key, used, lab, index, symbols) for key in used}
        facing = settings["light"]
        if facing == "auto":
            # Follow the light the artist already drew: darker tones to the left mean light from the right.
            facing = "top-right" if sum(dx for _, dx in ramps.values()) < 0 else "top-left"
        if facing == "top-right":
            left, right = right, left
        areas = sorted(used, key=lambda key: -int((index == symbols.index(key))[solid].sum()))
        tones = []
        for key in areas:
            if lab[key][0] <= DARK or ramps[key][0] >= RAMPED:
                continue
            area = (index == symbols.index(key)) & solid
            if area.sum() < 6:
                continue
            thick = (width >= 3) & (height >= 3)
            side = (right < np.maximum(1, width // 3)) if facing != "top" else np.zeros(area.shape, bool)
            shadow = area & thick & (side | (below < np.maximum(1, height // 4)))
            light = area & thick & ~shadow & (above == 0) & (left < np.maximum(1, width // 2))
            tones.append((key, shadow, light))
        for kind in ("shadow", "light"):
            for key, shadow, light in tones:
                band = shadow if kind == "shadow" else light
                if not band.any() or budget <= 0 or not spare or (kind == "light" and not settings["highlight"]):
                    continue
                symbol = spare.pop(0)
                palette[symbol] = tone(rgba[key], SHADOW if kind == "shadow" else HIGHLIGHT)
                out[band & (out == key)] = symbol
                budget -= 1
    return ["".join(row) for row in out], palette


def _ramp(key, used, lab, index, symbols):
    """The hand-drawn tones ``key`` already has: (their area as a share of its own, how far right of it the
    darker ones sit on average, in pixels). A tone is a touching colour of about the same hue."""
    import math

    area = index == symbols.index(key)
    padded = np.pad(area, 1)
    near = (padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]) & ~area
    l0, a0, b0 = lab[key]
    tones, darker = 0, []
    columns = np.nonzero(area)[1]
    for other in set(symbols[i] for i in np.unique(index[near])) & set(used):
        l1, a1, b1 = lab[other]
        chroma = min(math.hypot(a0, b0), math.hypot(a1, b1))
        turn = abs((math.degrees(math.atan2(b0, a0) - math.atan2(b1, a1)) + 180) % 360 - 180)
        if chroma > 0.03 and turn < 25 and 0.05 <= abs(l1 - l0) and l1 > DARK:
            shade = index == symbols.index(other)
            tones += int(shade.sum())
            if l1 < l0:
                darker.append(float(np.nonzero(shade)[1].mean() - columns.mean()))
    return tones / max(1, int(area.sum())), (float(np.mean(darker)) if darker else 0.0)


def pixel_image(project, layer):
    from .render import color
    from .design import resolve_color

    rows, palette = finished(project, layer)
    palette = {key: color(resolve_color(value, project.state)) for key, value in palette.items()}
    image = Image.new("RGBA", (len(rows[0]), len(rows)))
    image.putdata([palette[symbol] for row in rows for symbol in row])
    return image


def inspect_pixels(project, target=None):
    layer = project.layer(target)
    require(layer["type"] == "pixel", "Target must be a pixel-art layer")
    return {
        "id": layer["id"],
        "name": layer["name"],
        "width": len(layer["pixels"][0]),
        "height": len(layer["pixels"]),
        "palette": deepcopy(layer["palette"]),
        "rows": list(layer["pixels"]),
        **({"shading": deepcopy(layer["shading"])} if layer.get("shading") else {}),
        **({"outline": layer["outline"]} if layer.get("outline") else {}),
        **({"drawn": dict(zip(("rows", "palette"), finished(project, layer)))}
           if layer.get("shading") or layer.get("outline") else {}),
    }


def execute_pixel(project, op):
    from .operations import append_layer, default_name

    if op["type"] == "pixel-art":
        rows = op.get("rows")
        palette = deepcopy(op.get("palette", {".": "transparent", "#": "black"}))
        if rows is None:
            width, height = op.get("width", 16), op.get("height", 16)
            require(1 <= width <= MAX_GRID and 1 <= height <= MAX_GRID, "Pixel grid dimensions must be 1–256")
            symbol = op.get("background", ".")
            require(symbol in palette, "Background symbol is not in the palette")
            rows = [symbol * width for _ in range(height)]
        else:
            require("background" not in op, "Rows specify their own background; omit background")
            if isinstance(rows, list) and rows and isinstance(rows[0], str):
                for key, expected in (("width", len(rows[0])), ("height", len(rows))):
                    require(key not in op or op[key] == expected,
                            f"Rows are {len(rows[0])}x{len(rows)}, so {key} must be {expected} (or omit it); "
                            f"got {op.get(key)}", field=key)
        require(isinstance(rows, list) and rows and isinstance(rows[0], str), "Provide pixel rows")
        layer = new_layer(
            op["name"] if "name" in op else default_name(project, "sprite"),
            "pixel",
            len(rows[0]),
            len(rows),
            pixels=deepcopy(rows),
            palette=palette,
            x=op.get("x", 0),
            y=op.get("y", 0),
        )
        for key in ("shading", "outline"):
            # Sprites get a shading ramp and an outline unless told not to.
            value = op.get(key, True)
            if value:
                layer[key] = deepcopy(value)
        validate_finish(layer)
        validate_pixel(layer, project.state)
        append_layer(project, layer)
        return
    layer = project.layer(op.get("target"))
    require(layer["type"] == "pixel", "Target must be a pixel-art layer")
    if op["type"] == "pixel-palette":
        require(any(key in op for key in ("colors", "shading", "outline")), "pixel-palette needs colors, shading or "
                "outline", field="colors")
        layer["palette"].update(deepcopy(op.get("colors", {})))
        for key in ("shading", "outline"):
            if key in op:
                if op[key]:
                    layer[key] = deepcopy(op[key])
                else:
                    layer.pop(key, None)
        validate_finish(layer)
        validate_pixel(layer, project.state)
        return
    rows = layer["pixels"]
    w, h = len(rows[0]), len(rows)
    symbol = op["color"]
    require(symbol in layer["palette"], "Color must be a palette symbol")
    x, y = op["x"], op["y"]
    require(0 <= x < w and 0 <= y < h, "Pixel coordinate outside grid")
    tool = op.get("tool", "pixel")
    mask = Image.new("1", (w, h))
    draw = ImageDraw.Draw(mask)
    if tool == "fill":
        require(not any(key in op for key in ("x2", "y2", "width", "height")), "Fill needs only X/Y")
        old = rows[y][x]
        pending = deque([(x, y)])
        seen = {(x, y)}
        while pending:
            px, py = pending.popleft()
            mask.putpixel((px, py), 1)
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and rows[ny][nx] == old:
                    seen.add((nx, ny))
                    pending.append((nx, ny))
    elif tool == "line":
        require("x2" in op and "y2" in op and "width" not in op and "height" not in op, "Line requires X2/Y2")
        require(0 <= op["x2"] < w and 0 <= op["y2"] < h, "Line endpoint outside grid")
        draw.line((x, y, op["x2"], op["y2"]), fill=1, width=1)
    elif tool == "rect":
        require(
            "width" in op and "height" in op and "x2" not in op and "y2" not in op,
            "Rectangle requires width/height",
        )
        require(x + op["width"] <= w and y + op["height"] <= h, "Rectangle outside grid")
        draw.rectangle((x, y, x + op["width"] - 1, y + op["height"] - 1), fill=1)
    else:
        require(
            tool == "pixel" and not any(key in op for key in ("x2", "y2", "width", "height")),
            "Pixel needs only X/Y",
        )
        draw.point((x, y), fill=1)
    layer["pixels"] = [
        "".join(symbol if mask.getpixel((px, py)) else rows[py][px] for px in range(w)) for py in range(h)
    ]
