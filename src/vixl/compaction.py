"""Unused embedded assets and explicit compaction.

A document keeps every asset some revision references, so undo can bring it back: a replaced
image, or a font from an earlier pairing, stays in the file until history no longer needs it.
``unused_assets`` reports what the current state does not use; ``compact`` is the explicit,
reported way to drop it. It discards undo history, so nothing calls it implicitly.
"""

import json

from .errors import require

KINDS = {"fonts": "font", "assets": "image", "masks": "mask", "sources": "source", "emoji-sources": "source"}


def _current_references(state):
    """Assets the current state uses, and the registered font names it refers to."""
    from .project import ASSET_REFERENCE

    fonts = state.get("fonts", {})
    rest = json.dumps({key: value for key, value in state.items() if key != "fonts"}, separators=(",", ":"))
    used = {name.decode() for name in ASSET_REFERENCE.findall(rest.encode())}
    # Layers name a font by its registered name (roles go through typography) or by its file.
    names = {name for name, asset in fonts.items() if json.dumps(name) in rest or asset in used}
    # Rich text selects registered weight/slant siblings without storing their names in spans.
    from types import SimpleNamespace
    from .richtext import variant_font

    view = SimpleNamespace(state=state)
    variants = {variant_font(view, fonts[name], bold, italic, {})[0]
                for name in names for bold, italic in ((True, False), (False, True), (True, True))}
    names |= {name for name, asset in fonts.items() if asset in variants}
    used |= {fonts[name] for name in names}
    return used, names


def unused_assets(project):
    """``{"assets": [...], "bytes", "fonts"}``: embedded files the current state does not use.
    Each entry has ``asset``, ``kind``, ``bytes`` and the registered ``fonts`` names for a font
    registered but drawn by no text, role or fallback (``reason``: ``unused-font``); other
    entries are kept only so undo can restore them (``history``)."""
    used, _ = _current_references(project.state)
    fonts = project.state.get("fonts", {})
    items = []
    for asset, data in sorted(project.assets.items()):
        if asset in used:
            continue
        names = sorted(name for name, path in fonts.items() if path == asset)
        items.append({"asset": asset, "kind": KINDS.get(asset.split("/")[0], "asset"), "bytes": len(data),
                      "reason": "unused-font" if names else "history", **({"fonts": names} if names else {})})
    return {"assets": items, "bytes": sum(item["bytes"] for item in items),
            "fonts": sorted(name for item in items for name in item.get("fonts", []))}


def compact(project, *, fonts=True, dry_run=False):
    """Squash history to the current state and drop the assets it does not use.

    Discards every other revision, the redo stack, branches and checkpoints (all reported). With
    ``fonts``, registered fonts no text, role or fallback uses are unregistered first, so their
    files go too. The document's appearance does not change. ``dry_run`` reports without changing
    anything; the caller saves the compacted document."""
    require(not project.transaction, "Commit or roll back the open transaction before compacting", field="action")
    candidate = project.clone()
    _, names = _current_references(candidate.state)
    unregistered = sorted(name for name in candidate.state.get("fonts", {}) if name not in names) if fonts else []
    for name in unregistered:
        del candidate.state["fonts"][name]
    if not candidate.state.get("fonts", True):
        candidate.state.pop("fonts")
    used, _ = _current_references(candidate.state)
    used |= set(candidate.state.get("fonts", {}).values())  # still registered (fonts=False): keep the files
    dropped = {asset: data for asset, data in candidate.assets.items() if asset not in used}
    before = sum(map(len, project.assets.values()))
    report = {
        "dry_run": dry_run,
        "revisions_dropped": max(0, len(project.nodes) - 1),
        "branches_dropped": sorted(name for name in project.branches if name != project.current_branch),
        "checkpoints_dropped": sorted(project.checkpoints),
        "redo_dropped": len(project.redo_stack),
        "fonts_unregistered": unregistered,
        "assets_dropped": [{"asset": asset, "kind": KINDS.get(asset.split("/")[0], "asset"), "bytes": len(data)}
                           for asset, data in sorted(dropped.items())],
        "bytes_dropped": sum(map(len, dropped.values())),
        "asset_bytes_before": before,
        "asset_bytes_after": before - sum(map(len, dropped.values())),
        "note": "Undo history before this point is gone; the current design is unchanged.",
    }
    if dry_run:
        return report
    candidate.assets = {asset: data for asset, data in candidate.assets.items() if asset in used}
    candidate.nodes, candidate.head, candidate._head_state, candidate.branches = {}, None, None, {}
    candidate.checkpoints, candidate.redo_stack, candidate._verified = {}, [], set()
    candidate._record([], "Compact document")
    project.__dict__.update(candidate.__dict__)
    report["head"] = project.head
    return report


def check_note(project, report):
    """Add an info finding about unused embedded assets to a check report (in place)."""
    from .checks import tally

    if "issues" not in report:
        return report
    found = unused_assets(project)
    if not found["assets"]:
        return report
    fonts = f" (fonts registered but unused: {', '.join(found['fonts'])})" if found["fonts"] else ""
    report["issues"].append({
        "check": "fonts", "severity": "info", "layers": [],
        "message": f"{len(found['assets'])} embedded file(s), {found['bytes']:,} bytes, are not used by the current "
                   f"design{fonts}; the rest are kept so undo can restore them. Compacting (vixl_history "
                   "action='compact', CLI vixl compact) drops them together with the undo history.",
        "unused_assets": found["assets"], "bytes": found["bytes"]})
    report.update(tally(report["issues"]))
    return report
