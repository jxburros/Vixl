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


from .errors import require
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


def _count(name, amount=1):
    from .profiling import current

    profile = current()
    if profile is not None:
        profile.count(name, amount)


DEFAULT_BUDGET_MB = 256
OFF = ("off", "0", "false", "no", "none")
# Whole frames a sequence has requested once, remembered (by key prefix) so the second request stores it.
SEEN_ENTRIES = 16384
SEEN_PREFIX = 20
FRAME_POLICIES = ("always", "adaptive", "never")


def budget_bytes():
    """The disk cache's size cap: ``VIXL_CACHE_MAX_MB`` megabytes (default 256)."""
    value = os.environ.get("VIXL_CACHE_MAX_MB", "").strip()
    try:
        megabytes = float(value) if value else DEFAULT_BUDGET_MB
    except ValueError:
        megabytes = DEFAULT_BUDGET_MB
    return max(0, int(megabytes * 1024 * 1024))


class RenderCache:
    """PNGs of rendered layers (``kind="layer"``) and whole frames (``kind="frame"``) under content keys.

    ``frames`` is the whole-frame write policy: ``always`` stores each frame (a still export: one frame,
    and the next export of the unchanged document reads it back), ``never`` stores none, and ``adaptive``
    (timeline and film sequences) stores a frame only the second time it is requested, in this run or an
    earlier one: frames that keep moving are each drawn once and would fill the cache with one-use PNGs,
    while held frames and re-exports of unchanged stretches are kept. Layers are always stored, so static
    layers are reused either way. Counters say what happened (``stats``)."""

    def __init__(self, directory, budget=None, frames="always"):
        require(frames in FRAME_POLICIES, f"frames must be one of {', '.join(FRAME_POLICIES)}")
        self.directory = Path(directory).resolve()
        self.budget = budget_bytes() if budget is None else budget
        self.frames = frames
        self.hits = self.misses = 0
        self.counts = {"frame_hits": 0, "frame_misses": 0, "layer_writes": 0, "frame_writes": 0,
                       "frame_writes_skipped": 0, "evictions": 0, "bytes_written": 0}
        self._bytes = 0
        self._seen = None
        self._sightings = []

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

    def get(self, key, limits, kind="layer"):
        if key is None:
            return None
        path = self.directory / (key + ".png")
        try:
            from .assets import decode, read_bounded

            image = decode(read_bounded(path, limits.max_asset_bytes), limits)
            os.utime(path, None)
            self.hits += 1
            if kind == "frame":
                self.counts["frame_hits"] += 1
            _count("disk_frame_hits" if kind == "frame" else "disk_hits")
            return image
        except Exception:
            self.misses += 1
            if kind == "frame":
                self.counts["frame_misses"] += 1
            _count("disk_frame_misses" if kind == "frame" else "disk_misses")
            return None

    def admit(self, key, kind):
        """Whether to store this entry under the frame policy."""
        if kind != "frame" or self.frames == "always":
            return True
        if self.frames == "never":
            return False
        if self._seen is None:
            self._seen = self._read_seen()
        prefix = key[:SEEN_PREFIX]
        if prefix in self._seen:
            return True
        self._seen.add(prefix)
        self._sightings.append(prefix)
        if len(self._sightings) >= 256:
            self.flush()
        return False

    def _seen_path(self):
        return str(self.directory) + ".seen"

    def _read_seen(self):
        try:
            with open(self._seen_path(), "rb") as stream:
                text = stream.read(SEEN_ENTRIES * (SEEN_PREFIX + 1) + 1).decode("ascii", "replace")
            return {line for line in text.split() if len(line) == SEEN_PREFIX}
        except OSError:
            return set()

    def flush(self):
        """Remember this run's one-time frames for the next run (adaptive policy). Never raises."""
        if not self._sightings:
            return
        pending, self._sightings = self._sightings, []
        try:
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            with file_lock(self._seen_path()):
                try:
                    with open(self._seen_path(), "rb") as stream:
                        known = stream.read().decode("ascii", "replace").split()
                except OSError:
                    known = []
                merged = list(dict.fromkeys(known + pending))[-SEEN_ENTRIES:]
                fd, staged = temporary(self.directory.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write("\n".join(merged).encode("ascii", "replace"))
                    os.replace(staged, self._seen_path())
                finally:
                    if os.path.exists(staged):
                        os.unlink(staged)
        except OSError:  # Includes a lock timeout: the ledger is only a hint.
            pass

    def put(self, key, image, kind="layer"):
        if key is None:
            return
        if not self.admit(key, kind):
            self.counts["frame_writes_skipped"] += 1
            _count("disk_frame_writes_skipped")
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
                self.counts["frame_writes" if kind == "frame" else "layer_writes"] += 1
                self.counts["bytes_written"] += len(data)
                _count("disk_frame_writes" if kind == "frame" else "disk_writes")
                _count("disk_bytes_written", len(data))
                if self._bytes > self.budget:
                    entries = [(path, path.stat()) for path in self.directory.glob("*.png")]
                    for path, stat in sorted(entries, key=lambda entry: entry[1].st_mtime_ns):
                        if self._bytes <= self.budget:
                            break
                        path.unlink()
                        self._bytes -= stat.st_size
                        self.counts["evictions"] += 1
                        _count("disk_evictions")
                self._write_usage(dirty=False)
        except OSError:
            pass
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)

    def stats(self):
        return {"directory": str(self.directory), "frames": self.frames, "budget_bytes": self.budget,
                "hits": self.hits, "misses": self.misses, **self.counts}


def user_cache_dir():
    """The per-user persistent render cache (``VIXL_RENDER_CACHE`` overrides it; ``off`` turns the disk cache
    off). Keys are content-addressed and include the engine fingerprint, so documents can share it safely."""
    value = os.environ.get("VIXL_RENDER_CACHE", "").strip()
    if value.lower() in OFF:
        return None
    return Path(value or "~/.cache/vixl/render").expanduser()


def enable(project, directory, frames="always"):
    """Give ``project`` a disk cache in ``directory`` (none when it is None, or the size cap is 0)."""
    budget = budget_bytes()
    project._disk_cache = RenderCache(directory, budget, frames) if directory is not None and budget > 0 else None
    return project


def info(directory=None):
    """Where the disk cache is, how much it holds and its cap (``vixl cache info``)."""
    directory = user_cache_dir() if directory is None else Path(directory)
    result = {"enabled": directory is not None and budget_bytes() > 0, "budget_bytes": budget_bytes(),
              "max_mb": round(budget_bytes() / 1024 / 1024, 2)}
    if directory is None:
        return {**result, "directory": None, "entries": 0, "bytes": 0}
    entries = total = 0
    try:
        for path in directory.glob("*.png"):
            entries += 1
            total += path.stat().st_size
    except OSError:
        pass
    return {**result, "directory": str(directory), "entries": entries, "bytes": total,
            "mb": round(total / 1024 / 1024, 2)}


def clear(directory=None):
    """Delete the disk cache's PNGs and ledgers (``vixl cache clear``); returns what was removed."""
    directory = user_cache_dir() if directory is None else Path(directory)
    if directory is None:
        return {"directory": None, "removed": 0, "bytes": 0}
    removed = total = 0
    if directory.is_dir():
        with file_lock(str(directory) + ".usage"):
            for path in directory.glob("*.png"):
                try:
                    size = path.stat().st_size
                    path.unlink()
                except OSError:
                    continue
                removed += 1
                total += size
            for suffix in (".usage.json", ".seen"):
                try:
                    os.unlink(str(directory) + suffix)
                except OSError:
                    pass
    return {"directory": str(directory), "removed": removed, "bytes": total}
