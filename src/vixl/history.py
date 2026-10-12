"""Compact structural deltas between document states for the persistent history DAG.

A delta is always a tagged object, so raw document values are never mistaken for deltas:
  {"$": "v", "v": VALUE}                       replace with VALUE
  {"$": "o", "s": {KEY: DELTA}, "x": [KEY]}    patch an object: set/patch keys, delete keys
  {"$": "l", "k": FIELD, "o": [KEY], "s": {KEY: DELTA}}
                                               patch a list of objects keyed by a unique FIELD
"""

from copy import deepcopy

from .errors import VixlError

KEY_FIELDS = ("id", "name")


def _ordered_equal(before, after):
    if type(before) is not type(after):
        return False
    if isinstance(before, dict):
        return list(before) == list(after) and all(_ordered_equal(v, after[k]) for k, v in before.items())
    if isinstance(before, list):
        return len(before) == len(after) and all(_ordered_equal(a, b) for a, b in zip(before, after))
    return before == after


def _keyed(items):
    if not isinstance(items, list) or not items:
        return None
    for field in KEY_FIELDS:
        if all(isinstance(item, dict) and isinstance(item.get(field), str) for item in items):
            keys = [item[field] for item in items]
            if len(set(keys)) == len(keys):
                return field
    return None


def diff(before, after):
    """Return a delta turning ``before`` into ``after``; None means unchanged."""
    if _ordered_equal(before, after):
        return None
    if isinstance(before, dict) and isinstance(after, dict):
        changes = {}
        for key, value in after.items():
            if key not in before:
                changes[key] = {"$": "v", "v": deepcopy(value)}
            else:
                child = diff(before[key], value)
                if child is not None:
                    changes[key] = child
        removed = [key for key in before if key not in after]
        result = {"$": "o", "s": changes}
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


def patch(value, delta):
    """Apply a delta produced by ``diff``. Malformed deltas raise invalid_project."""
    try:
        return _patch(value, delta)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
        raise VixlError("invalid_project", f"Malformed history delta: {exc}") from exc


def _patch(value, delta):
    if delta is None:
        return deepcopy(value)
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
        result = {k: deepcopy(v) for k, v in value.items() if k not in removed}
        for key, child in delta["s"].items():
            result[key] = _patch(value[key], child) if key in value and child["$"] != "v" else _patch(None, child)
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
        result = []
        for key in order:
            if key in changes:
                child = changes[key]
                result.append(_patch(old[key], child) if child["$"] != "v" else _patch(None, child))
            else:
                result.append(deepcopy(old[key]))
        return result
    raise ValueError(f"unknown delta tag {tag!r}")
