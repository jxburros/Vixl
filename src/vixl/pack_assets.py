"""Image assets carried by resource packs (the ``assets`` resource kind) and the ``asset-place`` operation.

A pack or ``resource-save`` gives an asset as ``{data_base64, media_type: png|jpeg|svg|webp, credit?, license?}``.
Saving validates the bytes before anything is written: the base64, the file signature of the stated type, at most
``MAX_ASSET_BYTES`` each (``MAX_PACK_BYTES`` for all assets of one plugin pack), a still image whose decoded size is
within ``Limits``, and SVG through the static-SVG sanitizer the importers use. The bytes are then stored
content-addressed beside the resource library (``.vixl-resources-assets/`` in a workspace), so the JSON library keeps
only a small record ``{sha256, media_type, bytes, width, height, credit?, license?}`` and stays under its size cap.

``asset-place`` reads no file named by the caller, so templates may use it: it embeds the asset in the document
through the content-addressed asset store (placing it twice keeps one copy) and records the resource and its
SHA-256 in the layer's provenance, which the brand check's ``required_elements`` and brand packs read.
"""

import base64
import hashlib
import os
from pathlib import Path
import re
import tempfile
import warnings

from .errors import VixlError, require

TYPES = ("asset-place",)
MEDIA_TYPES = ("png", "jpeg", "svg", "webp")
EXTENSIONS = {"png": "png", "jpeg": "jpg", "svg": "svg", "webp": "webp"}
PILLOW_FORMATS = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_PACK_BYTES = 20 * 1024 * 1024
# All assets one resource library keeps; packs and saves past it are refused, not silently dropped.
MAX_LIBRARY_BYTES = 200 * 1024 * 1024
TEXT_LIMIT = 1000
INPUT_FIELDS = {"data_base64", "media_type", "credit", "license"}
STORED_FIELDS = {"sha256", "media_type", "bytes", "width", "height", "credit", "license"}
SHA256 = re.compile(r"[0-9a-f]{64}")


def _signature_matches(data, media_type):
    if media_type == "png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if media_type == "jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if media_type == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    head = data[:512].lstrip(b"\xef\xbb\xbf").lstrip()
    return head.startswith((b"<?xml", b"<svg", b"<!--"))


def check_bytes(data, media_type, limits=None):
    """``(width, height)`` of asset bytes after every install-time check, else a VixlError."""
    from .model import Limits

    limits = limits or Limits()
    require(media_type in MEDIA_TYPES, f"media_type must be one of {', '.join(MEDIA_TYPES)}", "invalid_asset",
            field="media_type", allowed=list(MEDIA_TYPES))
    require(0 < len(data) <= MAX_ASSET_BYTES, f"A pack asset holds 1 byte to {MAX_ASSET_BYTES // (1024 * 1024)} MiB",
            "resource_limit", field="data_base64")
    require(_signature_matches(data, media_type), f"The bytes are not a {media_type} file (wrong file signature)",
            "invalid_asset", field="media_type")
    if media_type == "svg":
        from .imports import sanitize_svg

        _, width, height = sanitize_svg(data, limits, byte_limit=MAX_ASSET_BYTES)
        return width, height
    from PIL import Image

    from .assets import decode_message, open_image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with open_image(data, (PILLOW_FORMATS[media_type],)) as image:
                width, height = image.size
                limits.size(width, height)
                require(width * height <= limits.max_pixels, f"The image is {width}×{height}, above the "
                        f"{limits.max_pixels:,}-pixel limit", "resource_limit", field="data_base64")
                require(getattr(image, "n_frames", 1) == 1, "Pack assets are still images (one frame)",
                        "invalid_asset", field="data_base64")
                image.load()
    except Image.DecompressionBombError as exc:
        raise VixlError("resource_limit", "The image is far above the pixel limit", field="data_base64") from exc
    except (OSError, ValueError) as exc:
        raise VixlError("invalid_asset", decode_message(exc), field="data_base64") from exc
    return width, height


def _text(value, key):
    require(isinstance(value, str) and len(value) <= TEXT_LIMIT, f"{key} is text of at most {TEXT_LIMIT} characters",
            "invalid_asset", field=key)


def decode_input(value, limits=None):
    """``(bytes, stored record)`` for an asset given as ``{data_base64, media_type, credit?, license?}``."""
    require(isinstance(value, dict), "An asset is {data_base64, media_type, credit?, license?}", "invalid_asset")
    unknown = sorted(set(value) - INPUT_FIELDS)
    require(not unknown, f"Unknown asset field(s) {unknown}; use data_base64, media_type, credit, license",
            "invalid_asset", allowed=sorted(INPUT_FIELDS))
    encoded = value.get("data_base64")
    require(isinstance(encoded, str) and encoded, "An asset needs data_base64 (the file bytes, base64)",
            "invalid_asset", field="data_base64")
    require(len(encoded) <= (MAX_ASSET_BYTES * 4) // 3 + 8, "A pack asset holds at most 2 MiB", "resource_limit",
            field="data_base64")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise VixlError("invalid_asset", "data_base64 is not valid base64", field="data_base64") from exc
    media_type = value.get("media_type")
    width, height = check_bytes(data, media_type, limits)
    record = {"sha256": hashlib.sha256(data).hexdigest(), "media_type": media_type, "bytes": len(data),
              "width": width, "height": height}
    for key in ("credit", "license"):
        if key in value:
            _text(value[key], key)
            if value[key].strip():
                record[key] = value[key].strip()
    return data, record


def validate_record(value):
    """A stored asset record is well formed (the bytes are checked against its SHA-256 when read)."""
    require(isinstance(value, dict) and set(value) <= STORED_FIELDS and isinstance(value.get("sha256"), str)
            and SHA256.fullmatch(value["sha256"]) and value.get("media_type") in MEDIA_TYPES,
            "Invalid stored asset record", "invalid_asset")
    for key in ("bytes", "width", "height"):
        number = value.get(key)
        require(isinstance(number, int) and not isinstance(number, bool) and number > 0,
                f"Invalid stored asset record ({key})", "invalid_asset")
    require(value["bytes"] <= MAX_ASSET_BYTES, "Invalid stored asset record (bytes)", "invalid_asset")
    for key in ("credit", "license"):
        if key in value:
            _text(value[key], key)


def validate(value):
    """Either form: an asset to save (``data_base64``) or a stored record."""
    if isinstance(value, dict) and "data_base64" in value:
        decode_input(value)
    else:
        validate_record(value)


def blob_dir(library):
    """Where the asset bytes of the resource library file ``library`` live."""
    library = Path(library)
    return library.with_name(library.stem + "-assets")


def blob_name(record):
    return f"{record['sha256']}.{EXTENSIONS[record['media_type']]}"


def write_blob(library, record, data):
    """Store ``data`` content-addressed (an existing copy is kept); returns True when a new file was written."""
    directory = blob_dir(library)
    require(not directory.is_symlink(), "The resource asset folder must not be a symbolic link", "forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / blob_name(record)
    if target.is_file() and not target.is_symlink():
        return False
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".asset-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def collect(library, data):
    """Delete stored asset files that no record of the library ``data`` names (after a removal or replacement)."""
    directory = blob_dir(library)
    if not directory.is_dir() or directory.is_symlink():
        return
    kept = {blob_name(record) for record in (data.get("assets") or {}).values()
            if isinstance(record, dict) and "sha256" in record and record.get("media_type") in EXTENSIONS}
    for path in directory.iterdir():
        if path.is_file() and not path.name.startswith(".") and path.name not in kept:
            path.unlink(missing_ok=True)


def library_bytes(data):
    return sum(record.get("bytes", 0) for record in (data.get("assets") or {}).values() if isinstance(record, dict))


def store(library, value, data):
    """Validate an asset to save and write its bytes; returns the record the library keeps. ``data`` is the
    library as it will be written (for the library-wide cap)."""
    raw, record = decode_input(value)
    require(library_bytes(data) + record["bytes"] <= MAX_LIBRARY_BYTES,
            f"The resource library keeps at most {MAX_LIBRARY_BYTES // (1024 * 1024)} MiB of assets", "resource_limit")
    write_blob(library, record, raw)
    return record


def read(record, workspace=None):
    """The bytes of a stored asset record: from the workspace library's folder, then the user library's."""
    from .assets import read_bounded
    from .resources import resource_path

    validate_record(record)
    libraries = [resource_path(workspace)] if workspace is not None else []
    libraries.append(resource_path())
    for library in libraries:
        path = blob_dir(library) / blob_name(record)
        if path.is_file() and not path.is_symlink():
            data = read_bounded(path, MAX_ASSET_BYTES)
            if hashlib.sha256(data).hexdigest() == record["sha256"]:
                return data
    raise VixlError("missing_asset", "The asset's stored bytes are missing or changed; save or install the asset "
                    "again", field="resource")


def resolved(name, workspace=None):
    """``(record, bytes)`` of the asset resource ``name``."""
    from .resources import get

    record = get("assets", name, workspace=workspace)
    return record, read(record, workspace)


def schemas(add):
    from .schema import COORD, SIZE, S, field
    from .geometry import ANCHORS

    add("asset-place", {
        "resource": field(S, "Name of an assets resource (saved with resource-save kind assets, or installed by a "
                          "plugin or brand pack)."),
        "name": field(S, "Layer name; default the resource name (made unique)."),
        "x": {**COORD, "description": "Where the anchor point goes: pixels, 'center' or a percentage such as '50%' "
              "(default 0)."},
        "y": {**COORD, "description": "Where the anchor point goes: pixels, 'center' or a percentage such as '50%' "
              "(default 0)."},
        "width": {**SIZE, "description": "Placed width; with only one of width and height the other keeps the "
                  "asset's aspect ratio (default the asset's own size)."},
        "height": {**SIZE, "description": "Placed height; with only one of width and height the other keeps the "
                   "asset's aspect ratio (default the asset's own size)."},
        "anchor": {"enum": list(ANCHORS), "description": "Which point of the placed image x and y name (default "
                   "top-left; center puts the image's centre at x, y)."},
    }, ["resource"])


def _workspace(project):
    return getattr(project, "_workspace", None) or (Path(project.path).parent if project.path else None)


def execute(project, op):
    from .geometry import ANCHORS, canonical_anchor
    from .image_import import attribution
    from .model import finite
    from .operations import default_name, execute as apply

    name = op["resource"]
    record, data = resolved(name, _workspace(project))
    native = (record["width"], record["height"])
    width, height = op.get("width"), op.get("height")
    if width is None and height is None:
        width, height = native
    elif width is None:
        width = finite(height, "height", 0.0001) * native[0] / native[1]
    elif height is None:
        height = finite(width, "width", 0.0001) * native[1] / native[0]
    width, height = max(1, round(finite(width, "width"))), max(1, round(finite(height, "height")))
    anchor = canonical_anchor(op.get("anchor", "top-left"))
    require(anchor, f"anchor must be one of {', '.join(ANCHORS)}", field="anchor", allowed=list(ANCHORS))
    fx, fy = ANCHORS[anchor]
    x = finite(op.get("x", 0), "x") - fx * width
    y = finite(op.get("y", 0), "y") - fy * height
    provenance = {"type": "pack-asset", "resource": name, "sha256": record["sha256"],
                  "media_type": record["media_type"]}
    if record["media_type"] == "svg":
        asset, source = _svg_asset(project, data, width, height)
        provenance["source"] = source
    else:
        from .assets import add_encoded

        asset, _ = add_encoded(project, data)
    apply(project, {"type": "add", "asset": asset, "name": op.get("name") or default_name(project, name),
                    "x": x, "y": y, "width": width, "height": height, "provenance": provenance,
                    **attribution(record.get("credit"), record.get("license"))})


def _svg_asset(project, data, width, height):
    """(raster asset, source asset) for an SVG rendered at the placed size; the SVG source is kept inert."""
    from .assets import add_image
    from .imports import render_svg, sanitize_svg

    root, native_w, native_h = sanitize_svg(data, project.limits, byte_limit=MAX_ASSET_BYTES)
    scale = max(width / native_w, height / native_h)
    size = (max(1, round(native_w * scale)), max(1, round(native_h * scale)))
    project.limits.size(*size)
    require(size[0] * size[1] <= project.limits.max_pixels, "The placed SVG exceeds the pixel limit",
            "resource_limit", field="width")
    source = f"sources/{hashlib.sha256(data).hexdigest()}.svg"
    project.assets[source] = data
    return add_image(project, render_svg(root, *size)), source
