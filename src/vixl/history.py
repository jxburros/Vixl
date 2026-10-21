"""Compact structural deltas between document states for the persistent history DAG.

A delta is always a tagged object, so raw document values are never mistaken for deltas:
  {"$": "v", "v": VALUE}                       replace with VALUE
  {"$": "o", "s": {KEY: DELTA}, "x": [KEY]}    patch an object: set/patch keys, delete keys
  {"$": "l", "k": FIELD, "o": [KEY], "s": {KEY: DELTA}}
                                               patch a list of objects keyed by a unique FIELD
"""

from collections.abc import Callable
from typing import Any

from .errors import VixlError
from .model import MAX_LAYERS, copy_tree as deepcopy

KEY_FIELDS = ("id", "name")


def _ordered_equal(before: Any, after: Any) -> bool:
    if type(before) is not type(after):
        return False
    if isinstance(before, dict):
        return list(before) == list(after) and all(_ordered_equal(v, after[k]) for k, v in before.items())
    if isinstance(before, list):
        return len(before) == len(after) and all(_ordered_equal(a, b) for a, b in zip(before, after))
    return bool(before == after)


def _keyed(items: Any) -> str | None:
    if not isinstance(items, list) or not items:
        return None
    for field in KEY_FIELDS:
        if all(isinstance(item, dict) and isinstance(item.get(field), str) for item in items):
            keys = [item[field] for item in items]
            if len(set(keys)) == len(keys):
                return field
    return None


def diff(before: Any, after: Any) -> dict[str, Any] | None:
    """Return a delta turning ``before`` into ``after``; None means unchanged."""
    if _ordered_equal(before, after):
        return None
    if isinstance(before, dict) and isinstance(after, dict):
        changes: dict[str, Any] = {}
        for key, value in after.items():
            if key not in before:
                changes[key] = {"$": "v", "v": deepcopy(value)}
            else:
                child = diff(before[key], value)
                if child is not None:
                    changes[key] = child
        removed = [key for key in before if key not in after]
        result: dict[str, Any] = {"$": "o", "s": changes}
        if removed:
            result["x"] = removed
        natural_order = [key for key in before if key in after] + [key for key in after if key not in before]
        if natural_order != list(after):
            result["o"] = list(after)
        return result
    if isinstance(before, list) and isinstance(after, list):
        field = _keyed(before)
        if field and _keyed(after) == field:
            old = {item[field]: item for item in before}
            changes = {}
            for item in after:
                key = item[field]
                if key not in old:
                    changes[key] = {"$": "v", "v": deepcopy(item)}
                else:
                    child = diff(old[key], item)
                    if child is not None:
                        changes[key] = child
            return {"$": "l", "k": field, "o": [item[field] for item in after], "s": changes}
    return {"$": "v", "v": deepcopy(after)}


def patch(value: Any, delta: dict[str, Any] | None, *, max_items: int = MAX_LAYERS, share: bool = False) -> Any:
    """Apply a delta produced by ``diff``. Malformed deltas raise invalid_project.

    ``max_items`` bounds every keyed list a delta builds (layers, children), checked before anything is copied.
    The result never shares data with ``delta``. With ``share=True`` it shares what the delta leaves unchanged
    with ``value`` (only the changed path is copied): for a caller that owns ``value`` and discards it, such as
    a chain of patches from one private snapshot."""
    keep: Callable[[Any], Any] = (lambda item: item) if share else deepcopy
    try:
        return _patch(value, delta, max_items, keep)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
        raise VixlError("invalid_project", f"Malformed history delta: {exc}") from exc


def _patch(value: Any, delta: Any, max_items: int, keep: Callable[[Any], Any]) -> Any:
    if delta is None:
        return keep(value)
    if not isinstance(delta, dict):
        raise ValueError("delta must be an object")
    tag = delta["$"]
    if tag == "v":
        return deepcopy(delta["v"])
    if tag == "o":
        if not isinstance(value, dict) or not isinstance(delta["s"], dict):
            raise TypeError("object delta requires objects")
        removed = delta.get("x", [])
        if not isinstance(removed, list):
            raise TypeError("deleted keys must be a list")
        removed = set(removed)
        result = {k: keep(v) for k, v in value.items() if k not in removed}
        for key, child in delta["s"].items():
            result[key] = (_patch(value[key], child, max_items, keep) if key in value and child["$"] != "v"
                           else _patch(None, child, max_items, keep))
        if "o" in delta:
            order = delta["o"]
            if not isinstance(order, list) or len(order) != len(result) or set(order) != set(result):
                raise ValueError("object key order must name each key exactly once")
            result = {key: result[key] for key in order}
        return result
    if tag == "l":
        field, order, changes = delta["k"], delta["o"], delta["s"]
        if field not in KEY_FIELDS or not isinstance(order, list) or not isinstance(changes, dict):
            raise TypeError("invalid list delta")
        if not isinstance(value, list):
            raise TypeError("list delta requires a list")
        old = {item[field]: item for item in value}
        # A crafted delta could name one key many times and make each name a fresh copy; check the
        # whole order before copying anything.
        if len(order) > max_items:
            raise ValueError(f"invalid list delta: more than {max_items} items")
        keys = set(order)
        if len(keys) != len(order):
            raise ValueError("invalid list delta: list delta repeats a key")
        if not set(changes) <= keys:
            raise ValueError("invalid list delta: a change names a key not in the order")
        if any(key not in old and key not in changes for key in order):
            raise ValueError("invalid list delta: a key is neither kept nor added")
        items: list[Any] = []
        for key in order:
            if key in changes:
                child = changes[key]
                items.append(_patch(old[key], child, max_items, keep) if child["$"] != "v"
                              else _patch(None, child, max_items, keep))
            else:
                items.append(keep(old[key]))
        return items
    raise ValueError(f"unknown delta tag {tag!r}")
