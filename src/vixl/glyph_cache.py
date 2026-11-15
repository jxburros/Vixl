"""Rasterised glyphs by outline and exact place: labels that share glyphs at the same place in their box
("Label 1", "Label 2", a counter across frames) rasterise those glyphs once.

The pixels are those of the whole-layer SVG, not an approximation of them. A glyph is cached under its outline
and its exact matrix (no subpixel rounding), rasterised alone with that matrix in a canvas that starts at the
box origin, which gives the coverage it has in the whole layer; and a layer is assembled from cached glyphs only
when no pixel takes partial coverage from two of them (where the rasteriser would blend them). Anything else is
drawn as one SVG, as before: a first-seen glyph (so text that never repeats costs one rasteriser call per layer,
as it did), coverage that mixes, a glyph whose canvas would be large. ``VIXL_GLYPH_CACHE=off`` turns it off."""

from collections import OrderedDict
from functools import lru_cache
import io
import math
import os
import re
import threading

from PIL import Image, ImageChops

# A glyph is rasterised in a canvas from the box origin to its far corner; past this many pixels the whole
# layer is drawn instead (the rasteriser's time grows with the canvas).
MAX_CANVAS = 32768
COMMAND = re.compile(r"([A-Za-z])([^A-Za-z]*)")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
EMPTY, LARGE = "empty", "large"


class GlyphCache(OrderedDict):
    """(outline, matrix) -> (coverage cropped to its ink, its box), ``EMPTY`` or ``LARGE``; least recently used
    first, bounded by bytes. ``seen`` holds the keys met once: a glyph is rasterised on its own only when it
    comes up again."""

    def __init__(self, budget=32 * 1024 * 1024, remembered=200_000):
        super().__init__()
        self.budget, self.bytes, self.remembered = budget, 0, remembered
        self.seen = set()
        self.lock = threading.RLock()

    def put(self, key, value):
        size = value[0].width * value[0].height if isinstance(value, tuple) else 0
        with self.lock:
            previous = self.pop(key, None)
            if isinstance(previous, tuple):
                self.bytes -= previous[0].width * previous[0].height
            while self and self.bytes + size > self.budget:
                _, old = self.popitem(last=False)
                if isinstance(old, tuple):
                    self.bytes -= old[0].width * old[0].height
            self[key] = value
            self.bytes += size

    def reset(self):
        with self.lock:
            self.clear()
            self.seen.clear()
            self.bytes = 0


CACHE = GlyphCache()


def enabled():
    return os.environ.get("VIXL_GLYPH_CACHE", "").strip().lower() not in ("off", "0", "false", "no")


@lru_cache(maxsize=8192)
def outline_box(d):
    """The box (left, top, right, bottom) of an outline's points in its own units (control points included), or
    None for an outline with no points or with commands other than the absolute ones glyph outlines use."""
    xs, ys = [], []
    for command, rest in COMMAND.findall(d):
        values = [float(v) for v in NUMBER.findall(rest)]
        if command == "H":
            xs += values
        elif command == "V":
            ys += values
        elif command in "MLQCTS" and len(values) % 2 == 0:
            xs += values[0::2]
            ys += values[1::2]
        elif command != "Z":
            return None
    return (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None


def draw(d, matrix):
    """The cache value of one glyph: rasterised alone, with its exact matrix, as the whole-layer SVG states it."""
    import resvg_py

    if not d.strip():
        return EMPTY
    box = outline_box(d)
    if box is None or not all(math.isfinite(v) for v in matrix):
        return LARGE
    a, b, c, e, tx, ty = matrix
    right = max(a * x + c * y + tx for x in (box[0], box[2]) for y in (box[1], box[3]))
    bottom = max(b * x + e * y + ty for x in (box[0], box[2]) for y in (box[1], box[3]))
    width, height = max(1, math.ceil(right) + 2), max(1, math.ceil(bottom) + 2)
    if width * height > MAX_CANVAS:
        return LARGE
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
           f'<path d="{d}" transform="matrix({" ".join(map(str, matrix))})" fill="rgb(0, 0, 0)" fill-opacity="1.0"/>'
           '</svg>')
    mask = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg)), formats=["PNG"]).convert("RGBA").getchannel("A")
    ink = mask.getbbox()
    return (mask.crop(ink), ink) if ink else EMPTY


def stencil(paths, width, height, whole=None):
    """The coverage of glyph ``paths`` ((outline, matrix) pairs in a ``width`` x ``height`` box) put together from
    cached glyphs, or None when the layer has to be drawn as one SVG. ``whole()`` gives the layer's coverage when
    the whole-layer SVG is already rasterised (else None): it is asked before any glyph is drawn alone, so a
    label repeated word for word still costs nothing."""
    if not enabled() or not (isinstance(width, int) and isinstance(height, int)):
        return None  # A fractional box is sized by the rasteriser.
    from .profiling import ACTIVE

    cache = CACHE
    values, missing, fresh = [], [], False
    with cache.lock:
        for d, matrix in paths:
            if not isinstance(d, str):
                return None
            key = (d, tuple(matrix))
            value = cache.get(key)
            if value is None:
                if key in cache.seen:
                    missing.append((len(values), key))
                else:
                    fresh = True
                    if len(cache.seen) >= cache.remembered:
                        cache.seen.clear()
                    cache.seen.add(key)
            else:
                cache.move_to_end(key)
            values.append(value)
    profile = ACTIVE.get()
    if profile is not None:
        absent = sum(1 for value in values if value is None)
        profile.count("glyph_hits", len(values) - absent)
        profile.count("glyph_misses", absent)
    if fresh:
        return None
    if missing and whole is not None:
        ready = whole()
        if ready is not None:
            return ready
    for index, key in missing:
        values[index] = draw(*key)
        cache.put(key, values[index])
    if LARGE in values:
        return None
    canvas = Image.new("L", (width, height))
    right = -1
    for value in values:
        if value == EMPTY:
            continue
        mask, (x0, y0, x1, y1) = value
        if x1 > width or y1 > height:
            x1, y1 = min(x1, width), min(y1, height)
            if x0 >= x1 or y0 >= y1:
                continue
            mask = mask.crop((0, 0, x1 - x0, y1 - y0))
        if x0 >= right:
            canvas.paste(mask, (x0, y0))
        else:
            under = canvas.crop((x0, y0, x1, y1))
            joined = ImageChops.lighter(under, mask)
            # Where both cover a pixel partly the rasteriser blends them; the larger of the two is that blend
            # only when one of them is empty or full. The clipped sum tells the two cases apart.
            if ImageChops.add(under, mask).tobytes() != joined.tobytes():
                return None
            canvas.paste(joined, (x0, y0))
        right = max(right, x1)
    return canvas
