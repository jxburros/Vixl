"""Rasterised SVG by content: layers that draw the same geometry (the same label in two layers, a path
shape copied or recoloured, a colour animated across frames) rasterise it once.

Single-colour fills are rasterised as a black stencil and painted afterwards, always, so the pixels do
not depend on what happens to be cached."""

from collections import OrderedDict
import hashlib
import io
import threading

from PIL import Image


class SvgCache(OrderedDict):
    """Rasterised SVGs by digest, least recently used first, bounded by bytes. One cache serves every document
    of the process, and documents render in parallel threads, so each lookup and insertion holds ``lock``."""

    def __init__(self, budget=96 * 1024 * 1024):
        super().__init__()
        self.budget, self.bytes = budget, 0
        self.hits = self.misses = 0
        self.lock = threading.RLock()

    def get_image(self, key):
        with self.lock:
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
        with self.lock:
            if key in self:
                self.bytes -= len(self[key].getbands()) * self[key].width * self[key].height
            while self and self.bytes + size > self.budget:
                _, old = self.popitem(last=False)
                self.bytes -= len(old.getbands()) * old.width * old.height
            self[key] = image
            self.bytes += size


CACHE = SvgCache()


def placed(root, matrix, ns="{http://www.w3.org/2000/svg}"):
    """A group in the SVG element ``root`` that maps box pixels by the affine ``matrix`` (SVG order):
    vector content drawn straight into its final place instead of resampling its box image there.
    Pair it with ``clip_to_box``."""
    import xml.etree.ElementTree as ET

    return ET.SubElement(root, ns + "g", {"transform": "matrix(" + " ".join(format(v, ".10g") for v in matrix) + ")"})


def clip_to_box(image, matrix, width, height):
    """Cut what a ``placed`` drawing put past its box (0, 0, ``width``, ``height``), as rasterizing the
    box on its own does. The cut runs a pixel outside the box, so its anti-aliased edge never dims ink
    that ends exactly on the box edge (the top of a glyph, a path's side); only content drawn past the
    box keeps up to a pixel more. A mask, not an SVG clip: resvg composites clipped groups separately,
    which moves the anti-aliasing of strokes over fills by several levels."""
    from PIL import ImageChops

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{image.width}" height="{image.height}">'
           f'<g transform="matrix({" ".join(format(v, ".10g") for v in matrix)})">'
           f'<rect x="-1" y="-1" width="{width + 2}" height="{height + 2}"/></g></svg>')
    mask = stencil(svg)
    if mask.getextrema()[0] == 255:
        return image
    image = image.copy()
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    return image


def rasterize(svg):
    """``svg`` (markup) as an RGBA image the caller may change."""
    import resvg_py

    key = hashlib.blake2b(svg.encode(), digest_size=20).digest()
    image = CACHE.get_image(key)
    if image is None:
        image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg)), formats=["PNG"]).convert("RGBA")
        CACHE.put(key, image)
    return image.copy()


def stencil(svg):
    """The coverage (alpha) of ``svg``, whose paint is opaque black."""
    import resvg_py

    key = b"stencil" + hashlib.blake2b(svg.encode(), digest_size=20).digest()
    mask = CACHE.get_image(key)
    if mask is None:
        mask = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg)), formats=["PNG"]).convert("RGBA").getchannel("A")
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
