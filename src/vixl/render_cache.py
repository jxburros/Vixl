"""Optional bounded persistent PNG cache. A cache failure must never lose artwork."""

from functools import lru_cache
import hashlib
from importlib import import_module
from importlib.metadata import version, PackageNotFoundError
import io
import json
import os
from pathlib import Path
import sys


from .fileio import file_lock, temporary


@lru_cache(maxsize=1)
def environment():
    from . import __version__

    modules = b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
    if getattr(sys, "frozen", False):
        # Frozen code can have virtual .py paths. Include the shipped engine binary instead.
        from .production import file_digest

        modules += file_digest(sys.executable).encode()
    versions = []
    for package, module in (
        ("Pillow", "PIL"),
        ("numpy", "numpy"),
        ("fonttools", "fontTools"),
        ("uharfbuzz", "uharfbuzz"),
        ("resvg-py", "resvg_py"),
        ("python-bidi", "bidi"),
    ):
        try:
            versions.append(version(package))
        except PackageNotFoundError:
            imported = import_module(module)
            value = getattr(imported, "__version__", getattr(imported, "VERSION", None))
            if value is None:
                # Conservatively fingerprint native dependencies when metadata is omitted by a freezer.
                files = sorted(Path(imported.__file__).parent.glob("*.pyd")) + [Path(imported.__file__)]
                value = hashlib.sha256(b"".join(p.read_bytes() for p in files if p.is_file())).hexdigest()
            versions.append(str(value))
    return [
        __version__,
        hashlib.sha256(modules).hexdigest(),
        versions,
    ]


def key_for(project, layer=None, bounds=None):
    from .text import font_data, font_digest
    from .render import EFFECTS

    layers = [layer] if layer else project.state["layers"]
    if any(x.get("linked") or any(e["name"] not in EFFECTS for e in x.get("effects", [])) for x in layers):
        return None
    fonts = [font_digest(font_data(project, x)) for x in layers if x["type"] == "text"]
    if layer:
        state = [layer, bounds, project.state.get("brushes", {}), fonts]
    else:
        # Frame state already contains sampled values; future keyframes are not render dependencies.
        state = {
            k: v
            for k, v in project.state.items()
            if k
            not in {
                "timeline",
                "animation",
                "suites",
                "roles",
                "motions",
                "actions",
                "recipe",
                "active_layer",
                "design_guidance",
                "presets",
            }
        }
        state = [state, fonts]
    return hashlib.sha256(
        json.dumps([environment(), state], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


class RenderCache:
    def __init__(self, directory, budget=256 * 1024 * 1024):
        self.directory = Path(directory).resolve()
        self.budget = budget
        self.hits = self.misses = 0

    def get(self, key, limits):
        if key is None:
            return None
        path = self.directory / (key + ".png")
        try:
            from .assets import decode, read_bounded

            image = decode(read_bounded(path, limits.max_asset_bytes), limits)
            os.utime(path, None)
            self.hits += 1
            return image
        except Exception:
            self.misses += 1
            return None

    def put(self, key, image):
        if key is None:
            return
        temp = None
        try:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            data = buffer.getvalue()
            if len(data) > min(self.budget // 4, 64 * 1024 * 1024):
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            with file_lock(str(self.directory / "cache")):
                fd, temp = temporary(self.directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                os.replace(temp, self.directory / (key + ".png"))
                entries = sorted(self.directory.glob("*.png"), key=lambda p: p.stat().st_mtime_ns)
                total = sum(p.stat().st_size for p in entries)
                for path in entries:
                    if total <= self.budget:
                        break
                    total -= path.stat().st_size
                    path.unlink()
        except OSError:
            pass
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)


def user_cache_dir():
    """The per-user persistent render cache (``VIXL_RENDER_CACHE`` overrides it). Keys are
    content-addressed and include the engine fingerprint, so documents can share it safely."""
    return Path(os.environ.get("VIXL_RENDER_CACHE", "~/.cache/vixl/render")).expanduser()


def enable(project, directory):
    project._disk_cache = RenderCache(directory)
    return project

