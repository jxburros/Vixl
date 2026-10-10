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


# Imaging, shaping and encoding packages whose versions change rendered pixels (also the render lockfile's).
PACKAGES = (
    ("Pillow", "PIL"),
    ("numpy", "numpy"),
    ("fonttools", "fontTools"),
    ("uharfbuzz", "uharfbuzz"),
    ("resvg-py", "resvg_py"),
    ("python-bidi", "bidi"),
)


@lru_cache(maxsize=1)
def environment():
    from . import __version__

    modules = b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
    if getattr(sys, "frozen", False):
        # Frozen code can have virtual .py paths. Include the shipped engine binary instead.
        from .production import file_digest

        modules += file_digest(sys.executable).encode()
    versions = []
    for package, module in PACKAGES:
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
    if any(x.get("linked") or x["type"] == "link" or any(e["name"] not in EFFECTS for e in x.get("effects", []))
           for x in layers):
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
        self._bytes = 0

    def _signature(self):
        stat = self.directory.stat()
        return [stat.st_dev, stat.st_ino, stat.st_mtime_ns]

    def _read_usage(self):
        try:
            with open(str(self.directory) + ".usage.json", "rb") as stream:
                usage = json.loads(stream.read(1024))
            if (isinstance(usage, dict) and usage.get("version") == 1 and usage.get("dirty") is False
                    and type(usage.get("bytes")) is int and 0 <= usage["bytes"] < 2**63
                    and usage.get("directory") == self._signature()):
                return usage["bytes"]
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _write_usage(self, *, dirty):
        """The lock protects both PNGs and this small, atomically replaced ledger.

        Mark it dirty before touching PNGs, so interruption or write failure causes
        the next writer to rebuild the count instead of trusting stale usage.
        """
        usage = {"version": 1, "dirty": dirty}
        if not dirty:
            usage.update(bytes=self._bytes, directory=self._signature())
        fd, staged = temporary(self.directory.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps(usage).encode())
            os.replace(staged, str(self.directory) + ".usage.json")
        finally:
            if os.path.exists(staged):
                os.unlink(staged)

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
            # Cache entries are written once and only decoded later; fast compression keeps renders quick.
            image.save(buffer, format="PNG", compress_level=1)
            data = buffer.getvalue()
            if len(data) > min(self.budget // 4, 64 * 1024 * 1024):
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            # Keep the lock beside the directory: creating/removing it inside would
            # change the directory mtime on every call and defeat change detection.
            with file_lock(str(self.directory) + ".usage"):
                # Read each writer's committed count, even when the filesystem gives
                # consecutive directory changes the same timestamp. The signature
                # additionally detects ordinary external additions/deletions.
                usage = self._read_usage()
                self._bytes = usage if usage is not None else sum(
                    path.stat().st_size for path in self.directory.glob("*.png")
                )
                self._write_usage(dirty=True)
                destination = self.directory / (key + ".png")
                previous = destination.stat().st_size if destination.exists() else 0
                fd, temp = temporary(self.directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                os.replace(temp, destination)
                self._bytes += len(data) - previous
                if self._bytes > self.budget:
                    entries = [(path, path.stat()) for path in self.directory.glob("*.png")]
                    for path, stat in sorted(entries, key=lambda entry: entry[1].st_mtime_ns):
                        if self._bytes <= self.budget:
                            break
                        path.unlink()
                        self._bytes -= stat.st_size
                self._write_usage(dirty=False)
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
