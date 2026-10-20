"""Unused embedded assets and explicit compaction.

A document keeps every asset some revision references, so undo can bring it back: a replaced
image, or a font from an earlier pairing, stays in the file until history no longer needs it.
``unused_assets`` reports what the current state does not use; ``compact`` is the explicit,
reported way to drop it. It discards undo history, so nothing calls it implicitly.
``prune_fonts`` keeps the history and drops only fonts no revision draws (opt-in at save).
"""

from copy import deepcopy
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
                   f"design{fonts}; the rest are kept so undo can restore them. Compacting (vixl_document(action='history') "
                   "action='compact', CLI vixl compact) drops them together with the undo history.",
        "unused_assets": found["assets"], "bytes": found["bytes"]})
    # An info finding changes no verdict: keep passed and outcome, which a check profile may have set from
    # its own fail_on (recomputing them here turned a failing final profile into a pass).
    counts = tally(report["issues"])
    report.update({key: counts[key] for key in ("errors", "warnings", "info", "by_action")})
    return report


def prune_fonts(project, *, dry_run=False):
    """Unregister the fonts no revision draws and drop their files, keeping undo history.

    A font counts as drawn when any revision (the current state, undo and redo history, branches and
    checkpoints) uses it from a layer, role, style, fallback list, master or page, as ``unused_assets`` measures
    it. Such fonts are removed from every revision, so undo still restores the same design and the font files
    lose their last reference. Fonts drawn only in an earlier revision stay; ``compact`` drops those together
    with the history. Names used from outside the document (export-time variables, data rows, recipe inputs,
    documents that link this one) are invisible here, which is why nothing calls this implicitly:
    ``save(prune_fonts=True)`` or ``vixl save --prune-fonts`` asks for it."""
    from .history import diff
    from .project import ASSET_REFERENCE

    require(not project.transaction, "Commit or roll back the open transaction before pruning fonts",
            field="prune_fonts")
    states = {ident: project._state_at(ident) for ident in project.nodes}
    registered, drawn = {}, set()
    for state in (*states.values(), project.state):
        registered.update(state.get("fonts", {}))
        drawn |= _current_references(state)[1]
    unused = set(registered) - drawn

    def strip(state):
        if not unused & set(state.get("fonts", {})):
            return state
        fonts = {name: asset for name, asset in state["fonts"].items() if name not in unused}
        return {**{k: v for k, v in state.items() if k != "fonts"}, **({"fonts": fonts} if fonts else {})}

    stripped = {ident: strip(state) for ident, state in states.items()}
    current = strip(project.state)
    # A file another name, a layer or any other revision still refers to stays.
    body = json.dumps([current, list(stripped.values())], separators=(",", ":")).encode()
    referenced = {name.decode() for name in ASSET_REFERENCE.findall(body)}
    dropped = sorted({registered[name] for name in unused} - referenced)
    report = {"dry_run": dry_run, "fonts_unregistered": sorted(unused),
              "assets_dropped": [{"asset": asset, "kind": "font", "bytes": len(project.assets[asset])}
                                 for asset in dropped if asset in project.assets]}
    report["bytes_dropped"] = sum(item["bytes"] for item in report["assets_dropped"])
    if dry_run or not unused:
        return report
    # Parents before children, so each delta is taken against the parent's rewritten state.
    order, seen = [], set()
    for ident in project.nodes:
        chain = []
        while ident is not None and ident not in seen:
            chain.append(ident)
            ident = project.nodes[ident]["parent"]
        seen.update(chain)
        order.extend(reversed(chain))
    nodes = {}
    for ident in order:
        node = project.nodes[ident]
        replacement = {k: v for k, v in node.items() if k not in ("state", "delta")}
        if "state" in node:
            replacement["state"] = stripped[ident]
        else:
            replacement["delta"] = diff(stripped[node["parent"]], stripped[ident])
        nodes[ident] = replacement
    # New objects only: a save works on a shallow copy, and a refused save must leave the document intact.
    project.nodes = {ident: nodes[ident] for ident in project.nodes}
    project.state = current
    if project.head is not None:
        project._head_state = deepcopy(stripped[project.head])
    project.assets = {asset: data for asset, data in project.assets.items() if asset not in dropped}
    return report
