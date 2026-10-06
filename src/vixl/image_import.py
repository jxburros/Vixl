"""Image imports shared by MCP, REST, the CLI and the Python API, with provenance for attribution."""

import hashlib

from .assets import add_encoded
from .errors import require

ACCEPT = "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1"
TEXT_LIMIT = 1000


def attribution(credit=None, license=None):
    """Validated ``credit``/``license`` text, omitting empty values."""
    result = {}
    for key, value in (("credit", credit), ("license", license)):
        if value is None:
            continue
        require(isinstance(value, str), f"{key} must be text", field=key)
        value = value.strip()
        require(len(value) <= TEXT_LIMIT, f"{key} is limited to {TEXT_LIMIT} characters", field=key)
        if value:
            result[key] = value
    return result


def fetch_image(url, limits):
    """Download an image URL under the fetch policy (vixl.fetch). The bytes are not trusted to be
    an image here: ``import_image`` decodes them under the pixel limits, whatever the Content-Type said."""
    from .fetch import fetch_bounded

    return fetch_bounded(url, limits.max_asset_bytes, accept=ACCEPT, label="Image URL")


def import_image(project, data, name="image", *, source=None, credit=None, license=None):
    """Embed encoded image bytes as a new raster layer. ``source`` is a provenance record such as the
    ``info`` from :func:`fetch_image` or ``{"path": ...}``; its ``sha256`` is filled in from the bytes."""
    extra = attribution(credit, license)
    source = {**(source or {}), "sha256": hashlib.sha256(data).hexdigest()}
    candidate = project.clone()
    asset, _ = add_encoded(candidate, data)
    candidate.apply({"type": "add", "asset": asset, "name": name,
                     "provenance": {"type": "imported", "source": source}, **extra}, detail="compact")
    project.__dict__.update(candidate.__dict__)
    layer = project.inspect(project.state["active_layer"])
    return {
        "id": layer["id"],
        "name": layer["name"],
        "width": layer["width"],
        "height": layer["height"],
        "bounds": layer["resolved_bounds"],
        "asset": asset,
        "source": source,
        **extra,
    }


def import_image_from(project, *, path=None, data=None, url=None, name="image", credit=None, license=None,
                      read=None):
    """Import from exactly one of ``path``, ``data`` or ``url``. ``read(path, limit)`` reads a path
    (services confine it to the workspace); ``path`` is recorded as given."""
    require(sum(value is not None for value in (path, data, url)) == 1,
            "Provide exactly one of path, data or url", field="url")
    limit = project.limits.max_asset_bytes
    if url is not None:
        data, source = fetch_image(url, project.limits)
    elif path is not None:
        from .assets import read_bounded

        data, source = (read or read_bounded)(path, limit), {"path": str(path)}
    else:
        require(isinstance(data, (bytes, bytearray)), "data must be bytes", field="data")
        require(len(data) <= limit, "Image exceeds byte limit", "resource_limit", field="data")
        data, source = bytes(data), {}
    return import_image(project, data, name, source=source, credit=credit, license=license)
