"""Content-addressed, normalized image assets; imports never execute project content."""

import hashlib
import io
import math
import warnings
from pathlib import Path

from PIL import Image, ImageOps

from .errors import VixlError, require


def decode(data, limits, mode="RGBA", size_hint=None):
    """Decode a bounded image. ``size_hint`` lets JPEG decode at a reduced DCT scale when the
    caller only needs at least that many pixels (previews, downsized layers)."""
    require(len(data) <= limits.max_asset_bytes, "Asset exceeds byte limit", "resource_limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                limits.size(*image.size)
                if size_hint and image.format == "JPEG" and image.mode != "CMYK":
                    # Orientation may swap axes, so request the larger side on both.
                    side = max(size_hint)
                    image.draft("RGB", (side, side))
                image.load()
                if image.getexif().get(0x0112, 1) != 1:
                    image = ImageOps.exif_transpose(image)
                image = to_srgb(image)
                return image.convert(mode) if image.mode != mode else image.copy()
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise VixlError("invalid_image", f"Cannot decode image: {exc}") from exc


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
    except Exception:  # an unreadable or mismatched profile falls back to the plain conversion
        return image


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=6)
    return stream.getvalue()


def read_bounded(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "File exceeds byte limit", "resource_limit")
    return data


SOURCE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def add_encoded(project, data, category="assets", *, max_pixels=None, placed_size=None, fit="fill"):
    """Embed an imported file. Compact still-image formats keep their original bytes (a JPEG
    photo stays a JPEG instead of growing ~10x as PNG); anything else is normalized to PNG.
    Returns ``(asset_name, decoded_image)``."""
    image = decode(data, project.limits)
    original_size = image.size
    ratio = 1.0
    if max_pixels is not None:
        require(isinstance(max_pixels, int) and not isinstance(max_pixels, bool) and max_pixels > 0,
                "max_pixels must be a positive integer", field="max_pixels")
        ratio = min(ratio, math.sqrt(max_pixels / (image.width * image.height)))
    if placed_size is not None:
        choose = min if fit == "fit" else max
        ratio = min(ratio, choose(placed_size[0] / image.width, placed_size[1] / image.height))
    if ratio < 1:
        image = image.resize((max(1, math.floor(image.width * ratio)), max(1, math.floor(image.height * ratio))),
                             Image.Resampling.LANCZOS)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            frames = getattr(probe, "n_frames", 1)
    except (OSError, ValueError) as exc:
        raise VixlError("invalid_image", f"Cannot decode image: {exc}") from exc
    if image.size != original_size:
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
