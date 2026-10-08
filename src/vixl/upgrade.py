"""What renders differently when a document saved by an older Vixl is opened, and the one change
that can be undone automatically (pinning the white fill open shapes used to get)."""

import re

from . import __version__

# 0.21.0 changed how effects, temperature/tint and open shapes render.
RENDER_CHANGES = (0, 21, 0)
AFFECTED_EFFECTS = ("temperature", "tint")


def parse_version(text):
    match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text or ""))
    return tuple(int(part or 0) for part in match.groups()) if match else None


def predates_render_changes(version):
    """True for a version older than 0.21.0, or for a document that recorded no version at all."""
    parsed = parse_version(version)
    return parsed is None or parsed < RENDER_CHANGES


def _stroked(layer):
    return str(layer.get("stroke", "transparent")).strip().lower() not in ("", "none", "transparent")


def unpinned_open_shapes(state):
    """Open shapes with a stroke and no explicit fill: white before 0.21.0, unfilled since."""
    from .geometry import is_open_shape

    return [layer for layer in state.get("layers", [])
            if layer.get("type") == "shape" and "fill" not in layer and _stroked(layer) and is_open_shape(layer)]


def _transformed(layer):
    return bool(layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y")
                or layer.get("skew_x") or layer.get("skew_y") or layer.get("affine"))


def _ref(layer):
    return {"id": layer["id"], "name": layer.get("name")}


def report(state, saved_version):
    """The upgrade notice for a document saved by ``saved_version``, or None when nothing it holds
    renders differently now."""
    if not predates_render_changes(saved_version):
        return None
    layers = state.get("layers", [])
    changes = []
    moved = [_ref(x) for x in layers if _transformed(x) and any(e.get("enabled", True) for e in x.get("effects", []))]
    if moved:
        changes.append({
            "change": "effects-before-transform",
            "message": "Effects now run in the layer's own frame before rotate, flip and skew, so these "
                       "rotated, flipped or skewed layers with effects render differently (blur room, "
                       "shadows and spatial filters turn with the layer). Review them; there is no automatic fix.",
            "layers": moved,
        })
    rescaled = [_ref(x) for x in layers if any(e.get("name") in AFFECTED_EFFECTS for e in x.get("effects", []))]
    if rescaled:
        changes.append({
            "change": "temperature-tint-scale",
            "message": "temperature and tint use a new multiplicative -100...100 scale: temperature looks "
                       "stronger and tint weaker than before. Re-tune the values on these layers.",
            "layers": rescaled,
        })
    unfilled = [_ref(x) for x in unpinned_open_shapes(state)]
    if unfilled:
        changes.append({
            "change": "open-shape-fill",
            "message": "Open paths and open shape kinds with a stroke and no fill now render unfilled; they "
                       "used to be filled white. Pin the old white fill with pin_fills.",
            "layers": unfilled,
            "fix": "pin-fills",
        })
    if not changes:
        return None
    return {
        "from_version": saved_version, "to_version": __version__, "changes": changes,
        "hint": "Run `vixl upgrade DOC --pin-fills` (MCP: vixl_document_open(path, upgrade='pin-fills')) to "
                "restore white fills, or `vixl upgrade DOC` (upgrade='accept') to accept the new rendering "
                "and stop this notice.",
    }


def upgrade(project, *, pin_fills=False, accept=True):
    """Report what renders differently in ``project``; optionally pin open-shape fills and record the
    document as upgraded (the caller saves it). Returns the report with what was done."""
    found = report(project.state, project.upgraded_from) if project.upgraded_from else None
    result = {"upgraded_from": project.upgraded_from, "report": found, "pinned": []}
    if pin_fills and project.upgraded_from:
        targets = [layer["id"] for layer in unpinned_open_shapes(project.state)]
        if targets:
            project.apply([{"type": "shape", "target": target, "fill": "white"} for target in targets])
        result["pinned"] = targets
    if accept and project.upgraded_from:
        project.upgraded_from = None
        result["accepted"] = True
    return result
