"""Content hashes of JSON-shaped values: one canonical encoding for every cache key, digest and revision id.

``canonical_json`` sorts keys, uses compact separators, escapes non-ASCII text and refuses NaN and infinity, so
equal values always give equal bytes. Paths, tuples, sets and bytes have one explicit encoding; any other type is an
error unless the caller passes ``default`` (for example ``default=str`` for a key that may hold arbitrary objects),
so nothing is hashed through an accidental ``repr``.
"""

from collections.abc import Callable
import hashlib
import json
from pathlib import PurePath
from typing import Any, Protocol

Default = Callable[[Any], Any] | None


class Hash(Protocol):
    def update(self, data: bytes, /) -> None: ...
    def digest(self) -> bytes: ...
    def hexdigest(self) -> str: ...


def _encode(value: Any) -> Any:
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    if isinstance(value, (bytes, bytearray)):
        return {"$bytes": hashlib.sha256(value).hexdigest()}
    raise TypeError(f"{type(value).__name__} is not hashable as content")


def canonical_json(value: Any, *, default: Default = None) -> bytes:
    """``value`` as canonical UTF-8 JSON bytes (tuples encode as lists)."""
    encode: Callable[[Any], Any] = _encode
    if default is not None:
        def encode(item: Any) -> Any:
            try:
                return _encode(item)
            except TypeError:
                return default(item)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=encode).encode()


def hasher(algo: str = "sha256", size: int | None = None) -> Hash:
    """A new hash object: ``sha256``, or ``blake2b`` with an optional ``size`` in bytes."""
    if algo == "blake2b":
        return hashlib.blake2b(digest_size=size or 64)
    return hashlib.new(algo)


def update_json(digest: Hash, value: Any, *, default: Default = None) -> Hash:
    """Feed ``value``'s canonical JSON to an incremental ``digest``."""
    digest.update(canonical_json(value, default=default))
    return digest


def content_hash(value: Any, *, algo: str = "sha256", size: int | None = None, default: Default = None) -> str:
    """The hex digest of ``value``'s canonical JSON."""
    return update_json(hasher(algo, size), value, default=default).hexdigest()


def legacy_hash(value: Any, *, compact: bool = False, allow_nan: bool = True, default: Default = None) -> str:
    """The SHA-256 hex digest of ``json.dumps(value, sort_keys=True)`` as earlier releases computed it, for
    digests that are stored and compared later (suite and library hashes, pack-folder revision ids, workspace
    check history keys, lyric build fingerprints): a new encoding would make every stored one look changed.
    New keys use ``content_hash``."""
    separators = (",", ":") if compact else None
    text = json.dumps(value, sort_keys=True, separators=separators, allow_nan=allow_nan, default=default)
    return hashlib.sha256(text.encode()).hexdigest()
