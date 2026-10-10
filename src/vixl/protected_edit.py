"""Protected edits (#520): apply a batch only if named layers and regions come through it unchanged.

Two kinds of protection are checked separately:

- structural: each protected layer (and everything inside a protected group) keeps every field, so a
  changed word, font, position or effect is caught even when it looks almost the same;
- pixels: the rendered pixels the protected layer covers fully (alpha 255 when drawn alone), and
  each protected ``region`` ([x, y, width, height] in document pixels), stay within ``tolerance`` (the
  largest change of any RGBA channel, 0-255). This catches changes from effects, parents, layers drawn on
  top or blending, which the structure alone does not show.

The baseline is taken from the document before the edit and held in memory only; the report names layers,
fields and measurements, never layer contents or provider settings. The edit commits only when every
guarantee holds (and not ``dry_run``); otherwise the document is unchanged. A protection that cannot be
measured (a layer that draws no opaque pixels) is reported as needing review, never as preserved.
"""

import numpy as np

from .errors import VixlError, require


def _subtree(project, refs):
    ids = [project.layer(ref)["id"] for ref in refs]
    found = list(dict.fromkeys(ids))
    while True:
        more = [x["id"] for x in project.state["layers"] if x.get("parent") in found and x["id"] not in found]
        if not more:
            return ids, found
        found += more


def _coverage(project, ident):
    """Pixels ``ident`` (with its descendants) covers opaquely when drawn alone on a transparent canvas."""
    alone = project.clone()
    alone.state["canvas"]["background"] = "transparent"
    index = {x["id"]: x for x in alone.state["layers"]}
    keep = {ident}
    parent = index[ident].get("parent")
    while parent in index:  # ancestors carry the transforms and opacity the layer is drawn with
        keep.add(parent)
        parent = index[parent].get("parent")
    for layer in alone.state["layers"]:
        chain, node = [], layer
        while node is not None:
            chain.append(node["id"])
            node = index.get(node.get("parent"))
        if layer["id"] not in keep and ident not in chain:
            layer["visible"] = False
    return np.asarray(alone.render().getchannel("A")) == 255


def _fields(before, after):
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _pixels(before, after, mask, tolerance):
    delta = np.abs(after.astype(np.int16) - before.astype(np.int16)).max(axis=2)
    changed = (delta > tolerance) & mask
    count = int(changed.sum())
    detail = {"max_delta": int(delta[mask].max()) if mask.any() else 0, "changed_pixels": count,
              "checked_pixels": int(mask.sum()), "tolerance": tolerance}
    if count:
        ys, xs = np.nonzero(changed)
        detail["changed_region"] = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    return detail


def protected_edit(project, operations, *, protect=(), regions=(), tolerance=0, structural=True, pixels=True,
                   dry_run=False, check=None):
    """Apply ``operations`` to a copy, verify the protections and commit only when all hold. Returns
    ``{committed, dry_run, guarantees, violations, outcome, changed_layers}``."""
    from .assurance import region_box
    from .outcomes import make

    protect, regions = list(protect), list(regions)
    require(protect or regions,
            "Name layers to protect or regions to keep", field="protect")
    require(type(tolerance) is int and 0 <= tolerance <= 255, "tolerance is 0-255 (largest channel change)",
            field="tolerance")
    require(structural or pixels, "Check structure, pixels or both", field="structural")
    named, protected = _subtree(project, protect)
    boxes = [region_box(project, region) for region in regions]
    baseline = {ident: project.layer(ident) for ident in protected}
    from copy import deepcopy

    baseline = deepcopy(baseline)
    before = np.asarray(project.render().convert("RGBA")) if pixels else None
    masks = {ident: _coverage(project, ident) for ident in named} if pixels else {}
    candidate = project.clone()
    result = candidate.apply(operations, detail="compact", check=check)
    guarantees, review = [], []
    if structural:
        for ident, snapshot in baseline.items():
            try:
                now = candidate.layer(ident)
            except VixlError:
                guarantees.append({"kind": "structure", "layer": snapshot["name"], "id": ident, "status": "violated",
                                   "reason": "the layer was deleted"})
                continue
            fields = _fields(snapshot, now)
            guarantees.append({"kind": "structure", "layer": snapshot["name"], "id": ident,
                               "status": "violated" if fields else "preserved",
                               **({"changed_fields": fields} if fields else {})})
    if pixels:
        after = np.asarray(candidate.render().convert("RGBA"))
        if after.shape != before.shape:
            guarantees.append({"kind": "pixels", "status": "violated", "reason": "the canvas size changed"})
        else:
            for ident, mask in masks.items():
                entry = {"kind": "pixels", "layer": baseline[ident]["name"], "id": ident}
                if not mask.any():
                    entry.update(status="unmeasured", reason="the layer draws no opaque pixels to compare")
                    review.append(f"pixels of {baseline[ident]['name']!r} could not be measured")
                else:
                    detail = _pixels(before, after, mask, tolerance)
                    entry.update(status="violated" if detail["changed_pixels"] else "preserved", **detail)
                guarantees.append(entry)
            for box in boxes:
                x, y, w, h = box
                mask = np.zeros(before.shape[:2], dtype=bool)
                mask[y:y + h, x:x + w] = True
                detail = _pixels(before, after, mask, tolerance)
                guarantees.append({"kind": "pixels", "region": list(box),
                                   "status": "violated" if detail["changed_pixels"] else "preserved", **detail})
    violations = [item for item in guarantees if item["status"] == "violated"]
    committed = not violations and not dry_run
    if committed:
        project.__dict__.update(candidate.__dict__)
    reasons = [f"{item['kind']} of {item.get('layer') or item.get('region')} changed" for item in violations] + review
    return {
        "committed": committed, "dry_run": dry_run, "guarantees": guarantees, "violations": len(violations),
        "outcome": make("completed", "failed" if violations else "passed", reasons, validated_by=["protected edit"]),
        "changed_layers": sorted(result.get("changes", {}).get("layers", {})),
        **({"note": "Not applied: a protection was violated, so the document is unchanged."} if violations else {}),
    }
