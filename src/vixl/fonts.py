"""Explicit, bounded font imports with portable embedding and no implicit network access."""

import hashlib
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import ImageFont

from .assets import read_bounded
from .errors import VixlError


def validate_font(data):
    try:
        ImageFont.truetype(BytesIO(data), 16)
    except (OSError, ValueError) as exc:
        raise VixlError(
            "invalid_font", "Use a valid TrueType/OpenType font file; CSS and WOFF are not supported"
        ) from exc


def import_font(project, source, name):
    from .design import named

    named(name)
    limit = min(project.limits.max_asset_bytes, 16 * 1024 * 1024)
    if urlparse(str(source)).scheme in ("http", "https"):
        from .fetch import fetch_bounded

        try:
            data, _ = fetch_bounded(str(source), limit, label="Font")
        except VixlError as exc:
            if exc.code == "fetch_failed":
                raise VixlError("font_download_failed", str(exc), **exc.details) from exc
            raise
    else:
        data = read_bounded(Path(source), limit)
    validate_font(data)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    candidate = project.clone()
    candidate.assets[asset] = data
    result = candidate.apply({"type": "font-register", "name": name, "asset": asset}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    return result
