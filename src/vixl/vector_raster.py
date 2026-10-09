"""Rasterised SVG by content: layers that draw the same geometry (the same label in two layers, a path
shape copied or recoloured, a colour animated across frames) rasterise it once.

Single-colour fills are rasterised as a black stencil and painted afterwards, always, so the pixels do
not depend on what happens to be cached."""

from collections import OrderedDict
import hashlib
import io

from PIL import Image


class SvgCache(OrderedDict):
    """Rasterised SVGs by digest, least recently used first, bounded by bytes."""

    def __init__(self, budget=96 * 1024 * 1024):
        super().__init__()
        self.budget, self.bytes = budget, 0
        self.hits = self.misses = 0

    def get_image(self, key):
        image = self.get(key)
        if image is None:
            self.misses += 1
            return None
        self.hits += 1
        self.move_to_end(key)
        return image

    def put(self, key, image):
        size = len(image.getbands()) * image.width * image.height
        if size > self.budget // 8:
            return
        while self and self.bytes + size > self.budget:
            _, old = self.popitem(last=False)
            self.bytes -= len(old.getbands()) * old.width * old.height
        self[key] = image
        self.bytes += size


CACHE = SvgCache()


def rasterize(svg):
    """``svg`` (markup) as an RGBA image the caller may change."""
    import resvg_py

    key = hashlib.blake2b(svg.encode(), digest_size=20).digest()
    image = CACHE.get_image(key)
    if image is None:
        image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA")
        CACHE.put(key, image)
    return image.copy()


def stencil(svg):
    """The coverage (alpha) of ``svg``, whose paint is opaque black."""
    import resvg_py

    key = b"stencil" + hashlib.blake2b(svg.encode(), digest_size=20).digest()
    mask = CACHE.get_image(key)
    if mask is None:
        mask = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA").getchannel("A")
        CACHE.put(key, mask)
    return mask


def painted(svg, rgba):
    """``svg`` drawn in opaque black, painted in ``rgba``: coverage times the paint's alpha, and fully
    transparent pixels left black like a direct rasterisation."""
    from .render import opacity_table

    mask = stencil(svg)
    alpha = mask.point(opacity_table(rgba[3] / 255)) if rgba[3] != 255 else mask
    image = Image.new("RGBA", mask.size, (*rgba[:3], 255))
    image.putalpha(alpha)
    blank = Image.new("RGBA", mask.size)
    return Image.composite(image, blank, alpha.point([0] + [255] * 255))
