"""Content-addressed, normalized image assets; imports never execute project content."""

import hashlib
import io
import math
import os
import warnings
from pathlib import Path

from PIL import Image, ImageOps

from .errors import VixlError, require
from .model import Limits


# A downsampling import may read a source this many times larger than the pixel limit (a 108 MP camera file under the
# default 40 MP limit) and shrinks it before anything else sees it.
SOURCE_FACTOR = 4

# The decoders Vixl opens image bytes with, the raster formats it imports (docs/reference/coverage.md). Every other
# Pillow plugin (EPS/PostScript through Ghostscript, PSD, JPEG 2000, the many legacy formats) stays unloaded, so a
# hostile file cannot reach a decoder Vixl never needed. Multi-picture camera JPEGs (MPO) open through JPEG.
RASTER_FORMATS = ("PNG", "JPEG", "WEBP", "GIF", "TIFF", "BMP", "AVIF", "ICO")
_PLUGINS = {"PNG": "PngImagePlugin", "JPEG": "JpegImagePlugin", "WEBP": "WebPImagePlugin", "GIF": "GifImagePlugin",
            "TIFF": "TiffImagePlugin", "BMP": "BmpImagePlugin", "AVIF": "AvifImagePlugin", "ICO": "IcoImagePlugin"}

# Pillow's decompression-bomb guard is one process-wide number (89 MP by default). It is raised once, here, to the
# largest source any Limits can read (SOURCE_FACTOR times a full max_dimension square), and never changed at run time;
# decode and image_size check each image against the caller's own limits right after the header is read.
PILLOW_PIXEL_CAP = SOURCE_FACTOR * Limits.max_dimension ** 2
if Image.MAX_IMAGE_PIXELS is not None and Image.MAX_IMAGE_PIXELS < PILLOW_PIXEL_CAP:
    Image.MAX_IMAGE_PIXELS = PILLOW_PIXEL_CAP


def source_limit(limits):
    return limits.max_pixels * SOURCE_FACTOR


def _registered(formats):
    """``formats`` whose Pillow plugin is loaded. Importing each plugin up front matters: ``Image.open`` calls
    ``Image.init()``, which imports every decoder Pillow ships, as soon as one requested format is unregistered."""
    import importlib

    ready = []
    for name in formats:
        name = name.upper()
        if name not in Image.OPEN and name in _PLUGINS:
            try:
                importlib.import_module(f"PIL.{_PLUGINS[name]}")
            except ImportError:  # a Pillow build without this codec
                continue
        if name in Image.OPEN:
            ready.append(name)
    return tuple(ready)


def open_image(source, formats=RASTER_FORMATS):
    """``Image.open`` restricted to ``formats`` (the raster formats Vixl imports by default). ``source`` is encoded
    bytes, a binary stream or a path. Bytes in any other format raise ``Image.UnidentifiedImageError``."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        source = io.BytesIO(source)
    return Image.open(source, formats=_registered(formats))


def too_large(width, height, limits, allowed=None):
    """The resource_limit error for an image above the pixel limit, naming both remedies."""
    allowed = allowed or limits.max_pixels
    return VixlError("resource_limit", f"The image is {width}×{height} ({width * height / 1e6:.1f} MP), above the "
                     f"{allowed:,}-pixel limit. Downsample it on import with max_pixels (for example "
                     f"max_pixels={limits.max_pixels}) or raise the limit (--max-pixels).", field="max_pixels",
                     limit=allowed, size=[width, height])


def image_size(data, limits):
    """``(width, height)`` of encoded image bytes from the header, after EXIF orientation, without decoding pixels."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with open_image(data) as image:
                width, height = image.size
                if image.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                    width, height = height, width
                return width, height
    except Image.DecompressionBombError as exc:
        raise VixlError(
            "resource_limit", f"The image is more than {SOURCE_FACTOR}× the {limits.max_pixels:,}-pixel limit; "
            "raise the limit (--max-pixels) or downsample it before importing", field="max_pixels") from exc
    except (OSError, ValueError) as exc:
        raise VixlError("invalid_image", decode_message(exc)) from exc


def decode(data, limits, mode="RGBA", size_hint=None, target_pixels=None):
    """Decode a bounded image. ``size_hint`` lets JPEG decode at a reduced DCT scale when the
    caller only needs at least that many pixels (previews, downsized layers). With ``target_pixels`` the source may be
    up to ``SOURCE_FACTOR`` times the pixel limit and is reduced towards that many pixels while decoding (the caller
    resizes it exactly)."""
    require(len(data) <= limits.max_asset_bytes, "Asset exceeds byte limit", "resource_limit")
    allowed = source_limit(limits) if target_pixels else limits.max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with open_image(data) as image:
                width, height = image.size
                if width * height > allowed:
                    raise too_large(width, height, limits, allowed)
                if target_pixels:
                    require(max(width, height) <= limits.max_dimension * SOURCE_FACTOR,
                            f"Dimensions must be 1–{limits.max_dimension * SOURCE_FACTOR} to downsample",
                            "resource_limit")
                else:
                    limits.size(width, height)
                reduce = math.floor(math.sqrt(width * height / target_pixels)) if target_pixels else 1
                if size_hint and image.format == "JPEG" and image.mode != "CMYK":
                    # Orientation may swap axes, so request the larger side on both.
                    side = max(size_hint)
                    image.draft("RGB", (side, side))
                elif reduce >= 2 and image.format == "JPEG" and image.mode != "CMYK":
                    image.draft("RGB", (width // reduce, height // reduce))
                image.load()
                if reduce >= 2 and image.width * image.height > target_pixels * 4:
                    image = image.reduce(max(1, math.floor(math.sqrt(image.width * image.height / target_pixels))))
                if image.getexif().get(0x0112, 1) != 1:
                    image = ImageOps.exif_transpose(image)
                image = to_srgb(image)
                return image.convert(mode) if image.mode != mode else image.copy()
    except Image.DecompressionBombError as exc:
        raise VixlError("resource_limit", f"The image is more than twice the {allowed:,}-pixel limit; raise the limit "
                        "(--max-pixels) or downsample it before importing", field="max_pixels") from exc
    except (OSError, ValueError) as exc:
        raise VixlError("invalid_image", decode_message(exc)) from exc


def to_srgb(image):
    """``image`` in sRGB (or its own mode when it has no usable profile). An embedded ICC profile, and the
    profile of a CMYK JPEG or TIFF, is applied rather than ignored, so print images keep their colors;
    CMYK without a profile converts the naive way."""
    profile = image.info.get("icc_profile")
    if not profile or image.mode not in ("RGB", "RGBA", "L", "LA", "CMYK"):
        return image
    try:
        from PIL import ImageCms

        source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
        if "srgb" in (ImageCms.getProfileDescription(source) or "").lower() and image.mode != "CMYK":
            return image
        target = ImageCms.createProfile("sRGB")
        alpha = image.getchannel("A") if image.mode in ("RGBA", "LA") else None
        base = image.convert({"RGBA": "RGB", "LA": "L"}.get(image.mode, image.mode))
        out = ImageCms.profileToProfile(base, source, target, renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                        outputMode="RGB", flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
        if alpha is not None:
            out.putalpha(alpha)
        return out
    except Exception:  # noqa: BLE001 - an unreadable or mismatched profile falls back to the plain conversion
        return image


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=6)
    return stream.getvalue()


READ_CHUNK = 1 << 20


def read_bounded(path, limit):
    """The bytes of ``path``, refused once they pass ``limit``. A regular file larger than the limit is refused
    from its size before anything is read; pipes and files that grow while read are read in chunks and stopped
    one chunk past the limit, so a refusal never costs a limit-sized buffer."""
    with Path(path).open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        require(size <= limit, "File exceeds byte limit", "resource_limit")
        chunks, total = [], 0
        while chunk := stream.read(min(READ_CHUNK, limit + 1 - total)):
            chunks.append(chunk)
            total += len(chunk)
            require(total <= limit, "File exceeds byte limit", "resource_limit")
    return b"".join(chunks)


SOURCE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def add_encoded(project, data, category="assets", *, max_pixels=None, placed_size=None, fit="fill"):
    """Embed an imported file. Compact still-image formats keep their original bytes (a JPEG
    photo stays a JPEG instead of growing ~10x as PNG); anything else is normalized to PNG.
    Returns ``(asset_name, decoded_image)``."""
    if max_pixels is not None:
        require(isinstance(max_pixels, int) and not isinstance(max_pixels, bool) and max_pixels > 0,
                "max_pixels must be a positive integer", field="max_pixels")
    target = None
    if max_pixels is not None or placed_size is not None:
        # A downsampled import may read a source above the pixel limit; the result is checked against it below.
        width, height = image_size(data, project.limits)
        target = min(max_pixels or width * height, width * height)
        if placed_size is not None:
            choose = min if fit == "fit" else max
            scale = min(1.0, choose(placed_size[0] / width, placed_size[1] / height))
            target = min(target, max(1, math.ceil(width * scale) * math.ceil(height * scale)))
    image = decode(data, project.limits, target_pixels=target)
    original_size = image.size
    ratio = 1.0
    if max_pixels is not None:
        ratio = min(ratio, math.sqrt(max_pixels / (image.width * image.height)))
    if placed_size is not None:
        choose = min if fit == "fit" else max
        ratio = min(ratio, choose(placed_size[0] / image.width, placed_size[1] / image.height))
    if ratio < 1:
        image = image.resize((max(1, math.floor(image.width * ratio)), max(1, math.floor(image.height * ratio))),
                             Image.Resampling.LANCZOS)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with open_image(data) as probe:
                fmt = probe.format
                frames = getattr(probe, "n_frames", 1)
    except (OSError, ValueError) as exc:
        raise VixlError("invalid_image", decode_message(exc)) from exc
    project.limits.size(*image.size)
    if image.size != original_size or target is not None and (image.width, image.height) != (width, height):
        stream = io.BytesIO()
        if fmt == "JPEG":
            image.convert("RGB").save(stream, format="JPEG", quality=90)
        elif fmt == "WEBP":
            image.save(stream, format="WEBP", quality=90)
        else:
            fmt = "PNG"
            image.save(stream, format=fmt)
        data, frames = stream.getvalue(), 1
    if fmt in SOURCE_FORMATS and frames == 1:
        name = f"{category}/{hashlib.sha256(data).hexdigest()}.{SOURCE_FORMATS[fmt]}"
        project.assets[name] = data
        return name, image
    return add_image(project, image, category), image


def add_image(project, image, category="assets"):
    project.limits.size(*image.size)
    data = png_bytes(image)
    require(len(data) <= project.limits.max_asset_bytes, "Asset exceeds byte limit", "resource_limit")
    name = f"{category}/{hashlib.sha256(data).hexdigest()}.png"
    project.assets[name] = data
    return name


def decode_message(exc):
    """What went wrong decoding image bytes, without the decoder's object reprs."""
    import re

    if isinstance(exc, Image.UnidentifiedImageError):
        return "Cannot decode image: not a supported image format (PNG, JPEG, WebP, GIF, TIFF, AVIF, BMP or ICO)"
    return "Cannot decode image: " + re.sub(r"\s*<[^<>]* at 0x[0-9a-f]+>", "", str(exc)).strip()


def local_path(root, value):
    """``value`` resolved inside the workspace ``root`` (media sources, job outputs); refuses paths outside it."""
    require(isinstance(value, str) and value, "Expected workspace path")
    path = (Path(root) / value).resolve()
    require(path.is_relative_to(Path(root).resolve()), "Film source is outside workspace", "forbidden")
    return path
