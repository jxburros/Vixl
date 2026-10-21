"""One canonical encoding for content hashes (#634)."""

import hashlib
import json
from pathlib import Path

import pytest

from vixl.hashing import canonical_json, content_hash, hasher, legacy_hash, update_json


def test_key_order_does_not_change_the_hash():
    assert content_hash({"a": 1, "b": [1, {"c": 2, "d": 3}]}) == content_hash({"b": [1, {"d": 3, "c": 2}], "a": 1})
    assert canonical_json({"b": 1, "a": "é"}) == b'{"a":"\\u00e9","b":1}'


def test_nan_and_unknown_types_are_refused():
    with pytest.raises(ValueError):
        content_hash({"x": float("nan")})
    with pytest.raises(TypeError, match="object is not hashable as content"):
        content_hash({"x": object()})
    assert content_hash({"x": object()}, default=lambda value: "obj") == content_hash({"x": "obj"})


def test_paths_tuples_sets_and_bytes_have_one_encoding():
    assert content_hash((1, 2)) == content_hash([1, 2])
    assert content_hash({"p": Path("a") / "b"}) == content_hash({"p": "a/b"})
    assert content_hash({3, 1, 2}) == content_hash([1, 2, 3])
    assert content_hash(b"abc") != content_hash(b"abd")


def test_incremental_and_sized_hashes():
    digest = hasher()
    update_json(digest, [1])
    update_json(digest, {"a": 2})
    assert digest.hexdigest() == hashlib.sha256(b'[1]{"a":2}').hexdigest()
    assert len(content_hash({"a": 1}, algo="blake2b", size=20)) == 40


def test_render_digest_is_the_canonical_blake2b():
    from vixl.render import digest

    value = {"layer": {"id": "x", "fill": "#fff"}, "box": [1, 2]}
    assert digest(value) == content_hash(value, algo="blake2b", size=20)


def test_stored_digests_keep_their_encoding():
    from vixl.assurance import digest

    value = {"b": [1, 2], "a": "x"}
    assert digest(value) == hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    assert legacy_hash(value, compact=True) == hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
