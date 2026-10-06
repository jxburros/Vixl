"""Colour for PDF content: the operators, gradient functions and images of a page in one colour space.

``RGBPaint`` writes colours as they are drawn (DeviceRGB). ``CMYKPaint`` writes the same colours
as DeviceCMYK, separated exactly like a CMYK raster export (``colors.cmyk_image``: the ICC profile
or device-naive gray-component replacement, rendering intent, black generation and ink limit), so
a vector page and a raster page of one document print the same ink. Pure black stays 100% K when
a profile is used, as press people expect for text.
"""

from . import colors
from .pdf_writer import image_xobject


def _num(value):
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


class RGBPaint:
    """Colours as sRGB (DeviceRGB)."""

    space = "DeviceRGB"
    steps = 1  # gradient samples per colour-stop interval

    def components(self, rgba):
        return [c / 255 for c in rgba[:3]]

    def fill(self, rgba):
        return " ".join(_num(c) for c in self.components(rgba)) + " rg"

    def stroke(self, rgba):
        return " ".join(_num(c) for c in self.components(rgba)) + " RG"

    def image(self, writer, image, jpeg_quality=None):
        return image_xobject(writer, image, jpeg_quality=jpeg_quality)


class CMYKPaint(RGBPaint):
    """Colours separated to DeviceCMYK with the document's separation settings."""

    space = "DeviceCMYK"
    steps = 8

    def __init__(self, *, profile=None, intent="relative", black=1.0, ink_limit=None, background="white"):
        self.profile = profile
        self.options = dict(profile=profile, intent=intent, black=black, ink_limit=ink_limit, background=background)
        # An ICC profile is built into a transform once, not for every colour.
        self.transform = colors.separation_transform(profile, intent) if profile is not None else None
        self.cache = {}

    def components(self, rgba):
        rgb = tuple(int(round(c)) for c in rgba[:3])
        if rgb not in self.cache:
            if rgb == (0, 0, 0) and self.profile is not None:
                self.cache[rgb] = (0.0, 0.0, 0.0, 1.0)
            else:
                from PIL import Image

                pixel = colors.cmyk_image(Image.new("RGB", (1, 1), rgb), **self.options, transform=self.transform)
                self.cache[rgb] = tuple(v / 255 for v in pixel.getpixel((0, 0)))
        return list(self.cache[rgb])

    def fill(self, rgba):
        return " ".join(_num(c) for c in self.components(rgba)) + " k"

    def stroke(self, rgba):
        return " ".join(_num(c) for c in self.components(rgba)) + " K"

    def image(self, writer, image, jpeg_quality=None):
        rgba = image.convert("RGBA")
        separated = colors.cmyk_image(rgba.convert("RGB"), **self.options, transform=self.transform)
        return image_xobject(writer, separated, alpha=rgba.getchannel("A"), jpeg_quality=jpeg_quality)


def ramp(paint, stops):
    """A PDF function that blends ``stops`` [(offset 0–1, rgba)] in ``paint``'s colour space.

    DeviceRGB interpolates the stops directly. A separated space samples each interval several
    times and interpolates between the separated samples, so a gradient follows the RGB blend the
    renderer draws (a profile's separation is not linear)."""
    points = []
    for (o0, a), (o1, b) in zip(stops, stops[1:]):
        steps = paint.steps if o1 > o0 else 1
        for i in range(steps):
            t = i / steps
            mixed = tuple(x + (y - x) * t for x, y in zip(a[:3], b[:3]))
            points.append((o0 + (o1 - o0) * t, paint.components(mixed)))
    points.append((stops[-1][0], paint.components(stops[-1][1])))
    functions = [{"FunctionType": 2, "Domain": [0, 1], "C0": a, "C1": b, "N": 1}
                 for (_, a), (_, b) in zip(points, points[1:])]
    if len(functions) == 1:
        return functions[0]
    return {"FunctionType": 3, "Domain": [0, 1], "Functions": functions, "Bounds": [offset for offset, _ in points[1:-1]],
            "Encode": [0, 1] * len(functions)}
