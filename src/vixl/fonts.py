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


def embedding(data):
    """The OS/2 ``fsType`` embedding permission of a font file: ``installable``, ``editable``,
    ``preview-print`` or ``restricted`` (``unknown`` when the table is unreadable). When a font
    sets several bits, the least restrictive one applies (OpenType spec)."""
    from fontTools.ttLib import TTFont

    try:
        fs_type = TTFont(BytesIO(data[0] if isinstance(data, tuple) else data), lazy=True)["OS/2"].fsType
    except Exception:  # noqa: BLE001 - a font without a readable OS/2 table has no stated permission
        return "unknown"
    if not fs_type & 0x000E:
        return "installable"
    if fs_type & 0x0008:
        return "editable"
    if fs_type & 0x0004:
        return "preview-print"
    return "restricted"


def license_name(data):
    """``OFL`` or ``Apache-2.0`` when the font's name table says so (Google Fonts families), else None."""
    from fontTools.ttLib import TTFont

    try:
        names = TTFont(BytesIO(data[0] if isinstance(data, tuple) else data), lazy=True)["name"]
        text = " ".join(record.toUnicode() for record in names.names if record.nameID in (13, 14)).lower()
    except Exception:  # noqa: BLE001
        return None
    if "open font license" in text or "scripts.sil.org/ofl" in text or "openfontlicense" in text:
        return "OFL"
    if "apache license" in text:
        return "Apache-2.0"
    return None
