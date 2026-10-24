"""Content packs: large data Vixl downloads on first use instead of shipping in the package.

A pack is data only (no code runs from it). Each one is pinned to a commit of the VixlPacks
repository and checked by SHA-256, so a changed or tampered file is refused. Downloads go to the
per-user pack directory (``VIXL_PACK_DIR``, default ``~/.cache/vixl/packs``).

``VIXL_<NAME>_PACK`` (for example ``VIXL_EMOJIS_PACK``) points at a local copy instead, and
``VIXL_PACK_DOWNLOAD=off`` forbids downloads (offline machines, sandboxes); ``install`` with a
source file still works then.

``cjk`` has no entry yet, only its override: ``VIXL_CJK_PACK`` names a font file, or a zip of font files named
like the font cache (``noto-sans-sc-400.ttf``), that text draws CJK, Devanagari or Thai from when no document font
covers them (``typefaces.local_script_faces``; renders never download it). A published pack adds an entry here
in the shape of the others, a zip of the Noto Sans SC, TC, JP and KR regular styles under those names:

    "cjk": {"file": "cjk.zip", "path": "fonts/cjk.zip", "commit": "<VixlPacks commit>",
            "sha256": "<sha256 of cjk.zip>", "bytes": <size>,
            "description": "Noto Sans CJK faces text falls back to when no document font draws a character.",
            "install": "Download {url} and install it with `vixl.packs.install('cjk', FILE)`."},
"""

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .errors import VixlError, require

REPOSITORY = "https://raw.githubusercontent.com/jxburros/VixlPacks"
PACKS = {
    "emojis": {
        "file": "artwork.zip",
        "path": "emojis/artwork.zip",
        "commit": "fa2632ed0fd0443cfe5e7c4e878afc7ddda56adf",
        "sha256": "3971e02a07f70557470b4e01c0c74328f0d613182df85a59ee9949c2695f438f",
        "bytes": 20466816,
        "description": "VIXL Line emoji artwork: SVG and editable .vixl masters for every catalog entry.",
        "install": "Run `vixl emoji artwork --download`, or download {url} and run `vixl emoji artwork --from FILE`.",
    },
    "fonts": {
        "file": "fonts.zip",
        "path": "fonts/fonts.zip",
        "commit": "ad7b72479569c906110bf8f89181548a58c4cc64",
        "sha256": "eefb01e73539f97bc6b7054b1890d7b2abb5ca6a2d4b5c4f3bfa0e8066c0954d",
        "bytes": 81431,
        "description": "Third-party fonts the Vixl examples use (Press Start 2P, Space Mono), named like the font cache.",
        "install": "Download {url} and install it with `vixl.packs.install('fonts', FILE)`.",
    },
}
OFF = {"0", "off", "false", "no"}
_failed = {}


def _spec(name):
    require(name in PACKS, f"Unknown content pack {name!r}; known: {', '.join(PACKS)}", "invalid_request")
    return PACKS[name]


def directory():
    return Path(os.environ.get("VIXL_PACK_DIR", "").strip() or "~/.cache/vixl/packs").expanduser()


def url(name):
    spec = _spec(name)
    return f"{REPOSITORY}/{spec['commit']}/{spec['path']}"


def _cached(name):
    spec = _spec(name)
    return directory() / f"{name}-{spec['sha256'][:12]}" / spec["file"]


def _override(name):
    value = os.environ.get(f"VIXL_{name.upper()}_PACK", "").strip()
    return Path(value).expanduser() if value else None


def downloads_allowed():
    return os.environ.get("VIXL_PACK_DOWNLOAD", "").strip().lower() not in OFF


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def status(name):
    """Where the pack is (if present) and how it would be obtained, without downloading."""
    spec, override = _spec(name), _override(name)
    found = override if override and override.is_file() else _cached(name) if _cached(name).is_file() else None
    return {
        "pack": name,
        "installed": found is not None,
        "path": str(found) if found else None,
        "source": "override" if found is not None and found == override else "cache" if found else None,
        "url": url(name),
        "sha256": spec["sha256"],
        "bytes": spec["bytes"],
        "downloads": "allowed" if downloads_allowed() else "off",
        "description": spec["description"],
    }


def _store(name, data_path):
    spec, target = _spec(name), _cached(name)
    digest = _digest(data_path)
    require(digest == spec["sha256"], f"Content pack {name} does not match its pinned SHA-256 "
            f"(got {digest[:12]}…, expected {spec['sha256'][:12]}…)", "pack_mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
        with open(data_path, "rb") as source:
            shutil.copyfileobj(source, staged)
    Path(staged.name).replace(target)
    return target


def install(name, source=None):
    """Put the pack in the per-user pack directory, from ``source`` (a local file) or by downloading it."""
    spec = _spec(name)
    if source is not None:
        source = Path(source).expanduser()
        require(source.is_file(), f"No pack file at {source}", "missing_file")
        path = _store(name, source)
        _failed.pop(name, None)
        return {**status(name), "path": str(path), "installed": True, "source": "cache"}
    require(downloads_allowed(), f"Downloads are off (VIXL_PACK_DOWNLOAD); install the {name} pack from a file: "
            f"download {url(name)} and pass it as the source", "pack_unavailable")
    from .fetch import fetch_bounded

    data, _ = fetch_bounded(url(name), spec["bytes"] + 1024 * 1024, label=f"{name} pack", allow_list=False)
    with tempfile.NamedTemporaryFile(delete=False) as staged:
        staged.write(data)
    try:
        path = _store(name, staged.name)
    finally:
        Path(staged.name).unlink(missing_ok=True)
    _failed.pop(name, None)
    return {**status(name), "path": str(path), "installed": True, "source": "cache"}


def local(name):
    """The local file for ``name`` when it is already on this machine (``VIXL_<NAME>_PACK`` or the pack directory),
    else None. It never downloads, so render paths may call it, and it answers for a pack that so far has only an
    override and no ``PACKS`` entry (``cjk``)."""
    override = _override(name)
    if override is not None:
        return override if override.is_file() else None
    return _cached(name) if name in PACKS and _cached(name).is_file() else None


def path(name, download=True):
    """The local file for ``name``, downloading it once if allowed. Raises ``pack_unavailable`` otherwise.

    A failed download is remembered for the rest of the process so a render does not retry it per glyph."""
    override = _override(name)
    if override is not None:
        require(override.is_file(), f"VIXL_{name.upper()}_PACK points at a missing file: {override}",
                "pack_unavailable")
        return override
    cached = _cached(name)
    if cached.is_file():
        return cached
    hint = f"The {name} content pack is not installed. " + _spec(name)["install"].format(url=url(name))
    require(download and name not in _failed, _failed.get(name, hint), "pack_unavailable")
    try:
        return Path(install(name)["path"])
    except VixlError as exc:
        _failed[name] = f"{hint} ({exc})"
        raise VixlError("pack_unavailable", _failed[name]) from exc
