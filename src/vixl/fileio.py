"""Atomic file publication that honors the user's umask and keeps existing permissions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
import os
from pathlib import Path
import stat
from typing import IO, TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from filelock import BaseFileLock

StrPath = str | os.PathLike[str]


def stamp(path: StrPath) -> tuple[int, int, int, int, int]:
    """What changes when a file is written or replaced: device, inode, size and the modification and change times
    (nanoseconds). Equal stamps let a writer skip re-reading the file to see whether someone else changed it."""
    info = os.stat(path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class HashingWriter:
    """A write-only stream that hashes everything written through it (``digest``), so a file's checksum is known
    without reading it back. It cannot seek, so ``zipfile`` writes each entry's sizes after its data."""

    def __init__(self, raw: IO[bytes]) -> None:
        import hashlib

        self.raw, self.hash, self.offset = raw, hashlib.sha256(), 0

    def write(self, data: bytes) -> int:
        self.raw.write(data)
        self.hash.update(data)
        self.offset += len(data)
        return len(data)

    def tell(self) -> int:
        return self.offset

    def seekable(self) -> bool:
        return False

    def flush(self) -> None:
        self.raw.flush()

    def digest(self) -> str:
        return self.hash.hexdigest()


def temporary(directory: StrPath, suffix: str = ".tmp", like: StrPath | None = None) -> tuple[int, str]:
    """Create an exclusive temporary file in ``directory``; return ``(fd, path)``.

    ``tempfile.mkstemp`` always creates mode 0600, which silently made saved projects and
    exports private. Creating with 0666 lets the umask decide, and an existing destination's
    mode is preserved when ``like`` names it.
    """
    folder = Path(directory)
    while True:
        path = folder / f".vixl-{uuid.uuid4().hex}{suffix}"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
            break
        except FileExistsError:
            continue
    if like is not None:
        try:
            os.chmod(path, stat.S_IMODE(os.stat(like).st_mode))
        except OSError:
            pass
    return fd, str(path)


@contextmanager
def file_lock(path: StrPath, timeout: float = 10) -> Iterator[BaseFileLock]:
    """Hold the advisory ``PATH.lock`` used by every Vixl writer, removing the file afterwards.

    Windows filelock already deletes the file on release. On POSIX the outermost holder unlinks
    it while still holding the lock; filelock 3.21+ waiters notice the unlinked inode and retry
    on a fresh file, so no empty ``.lock`` files are left beside projects.
    """
    from filelock import FileLock

    lock = FileLock(str(path) + ".lock", timeout=timeout, is_singleton=True)
    with lock:
        try:
            yield lock
        finally:
            if os.name != "nt" and lock.lock_counter == 1:
                with suppress(OSError):
                    os.unlink(lock.lock_file)


def adler32_combine(first: int, second: int, length: int) -> int:
    """The Adler-32 of two byte strings joined, from the checksum of each and the length of the second (zlib's
    ``adler32_combine``, which Python does not expose)."""
    base = 65521
    rem = length % base
    low = first & 0xFFFF
    high = (rem * low) % base
    low += (second & 0xFFFF) + base - 1
    high += ((first >> 16) & 0xFFFF) + ((second >> 16) & 0xFFFF) + base - rem
    return (low % base) | ((high % base) << 16)


def png_rows(rows: Any, above: Any, bpp: int, level: int = 6) -> tuple[bytes, int, int]:
    """One block of a PNG's image data: ``rows`` (a uint8 array, one row of pixel bytes per line) filtered against
    the row ``above`` it and deflated as a byte-aligned piece of a raw stream. The block takes the PNG filter
    (none, sub or up) that compresses its first rows best: flat artwork is smallest unfiltered, photographs
    with a filter. Returns (the compressed piece, the Adler-32 of the filtered bytes, their length)."""
    import zlib

    import numpy as np

    def filtered(kind: int, count: int) -> bytes:
        out = np.empty((count, rows.shape[1] + 1), dtype=np.uint8)
        out[:, 0] = kind
        out[:, 1:] = rows[:count]
        if kind == 1:
            out[:, 1 + bpp:] -= rows[:count, :-bpp]
        elif kind == 2:
            out[0, 1:] -= above
            out[1:, 1:] -= rows[:count - 1]
        return bytes(out.tobytes())

    sample = min(len(rows), 6)
    kind = min((0, 1, 2), key=lambda kind: len(zlib.compress(filtered(kind, sample), 1)))
    data = filtered(kind, len(rows))
    deflate = zlib.compressobj(level, zlib.DEFLATED, -15)
    return deflate.compress(data) + deflate.flush(zlib.Z_SYNC_FLUSH), zlib.adler32(data), len(data)


class PngWriter:
    """Writes a PNG from bands of rows as they arrive, so the image never has to exist whole: 8-bit RGB or RGBA,
    not interlaced. Each block of ``BLOCK`` rows is filtered and deflated on its own (on ``pool``, a thread pool,
    when given: numpy and zlib release the GIL) and the pieces are joined into one zlib stream."""

    BLOCK = 32

    def __init__(self, stream: IO[bytes], size: tuple[int, int], mode: str = "RGBA",
                 dpi: tuple[float, float] | None = None, pool: Any = None, level: int = 6) -> None:
        import struct

        if mode not in ("RGB", "RGBA"):
            raise ValueError(f"Unsupported PNG mode: {mode}")
        self.stream, self.size, self.mode, self.pool, self.level = stream, size, mode, pool, level
        self.bpp = len(mode)
        self.rows, self.adler = 0, 1
        self.above: Any = None
        stream.write(b"\x89PNG\r\n\x1a\n")
        self.chunk(b"IHDR", struct.pack(">IIBBBBB", size[0], size[1], 8, 2 if mode == "RGB" else 6, 0, 0, 0))
        if dpi:
            self.chunk(b"pHYs", struct.pack(">IIB", int(dpi[0] / 0.0254 + 0.5), int(dpi[1] / 0.0254 + 0.5), 1))
        self.pending = b"\x78\x9c"  # The zlib header; the next piece of image data follows it.

    def chunk(self, kind: bytes, data: bytes) -> None:
        import struct
        import zlib

        self.stream.write(struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data)))

    def write(self, image: Any) -> None:
        """Append a band: a Pillow image as wide as the PNG, in the writer's mode (an RGB writer also takes RGBA
        and drops the alpha, as ``convert("RGB")`` does, without copying the band)."""
        import numpy as np

        if (image.mode not in (self.mode, "RGBA") or image.width != self.size[0]
                or self.rows + image.height > self.size[1]):
            raise ValueError("The band does not fit the PNG")
        stride = image.width * self.bpp
        if self.above is None:
            self.above = np.zeros(stride, dtype=np.uint8)

        def block(top: int) -> tuple[bytes, int, int]:
            # A few rows at a time: an array of the whole band would be a second copy of it.
            start = max(0, top - 1)
            pixels = np.asarray(image.crop((0, start, image.width, min(image.height, top + self.BLOCK))))
            pixels = pixels[:, :, :self.bpp].reshape(len(pixels), stride)
            return png_rows(pixels[top - start:], pixels[0] if top else self.above, self.bpp, self.level)

        tops = range(0, image.height, self.BLOCK)
        for piece, adler, length in (self.pool.map(block, tops) if self.pool is not None else map(block, tops)):
            self.adler = adler32_combine(self.adler, adler, length)
            self.chunk(b"IDAT", self.pending + piece)
            self.pending = b""
        last = np.asarray(image.crop((0, image.height - 1, image.width, image.height)))
        self.above = last[:, :, :self.bpp].reshape(stride).copy()
        self.rows += image.height

    def close(self) -> None:
        import struct

        if self.rows != self.size[1]:
            raise ValueError("The PNG is missing rows")
        # An empty final block ends the deflate stream; the checksum of everything filtered follows it.
        self.chunk(b"IDAT", self.pending + b"\x03\x00" + struct.pack(">I", self.adler))
        self.chunk(b"IEND", b"")
