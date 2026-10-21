"""Atomic file publication that honors the user's umask and keeps existing permissions."""

from contextlib import contextmanager, suppress
import os
from pathlib import Path
import stat
import uuid


def stamp(path):
    """What changes when a file is written or replaced: device, inode, size and the modification and change times
    (nanoseconds). Equal stamps let a writer skip re-reading the file to see whether someone else changed it."""
    info = os.stat(path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class HashingWriter:
    """A write-only stream that hashes everything written through it (``digest``), so a file's checksum is known
    without reading it back. It cannot seek, so ``zipfile`` writes each entry's sizes after its data."""

    def __init__(self, raw):
        import hashlib

        self.raw, self.hash, self.offset = raw, hashlib.sha256(), 0

    def write(self, data):
        self.raw.write(data)
        self.hash.update(data)
        self.offset += len(data)
        return len(data)

    def tell(self):
        return self.offset

    def seekable(self):
        return False

    def flush(self):
        self.raw.flush()

    def digest(self):
        return self.hash.hexdigest()


def temporary(directory, suffix=".tmp", like=None):
    """Create an exclusive temporary file in ``directory``; return ``(fd, path)``.

    ``tempfile.mkstemp`` always creates mode 0600, which silently made saved projects and
    exports private. Creating with 0666 lets the umask decide, and an existing destination's
    mode is preserved when ``like`` names it.
    """
    directory = Path(directory)
    while True:
        path = directory / f".vixl-{uuid.uuid4().hex}{suffix}"
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
def file_lock(path, timeout=10):
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
