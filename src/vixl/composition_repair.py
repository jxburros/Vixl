"""Repair candidates for ``composition`` findings (craft plan 2b), tried by ``layout_repair.repair_layout``.

Each finding kind gets a few candidates in a fixed order, all relative moves except the scatter's rebuild:

- ``margin_drift``: snap the stray edges to the margin, or move the margin to the stray edge;
- ``uneven_rhythm``: move the middle line to its group (halfway, for lines of one size), close the stack up, or
  snap the gaps to whole spacing units;
- ``crowding``: open the gap under the rule, band or heading to one spacing unit (or just over half): push the text
  down, alone or with the rest of its column, or lift the rule, alone or with what is above it;
- ``dead_band``: between blocks, spread the band over the frame's other gaps, move the blocks below up (fully or
  halfway) or the blocks above down halfway; at an edge, spread the content into the band or centre it in its frame;
- ``clumped_scatter``: a ``pattern-scatter`` tile is thinned in place or re-seeded; any other scatter is not.

Layout repair applies every candidate to a copy, keeps it only when the finding is gone and nothing new appears
(no fix finding, no review finding of any check) and picks the least disruptive. Moving a line of text moves the
chip that hugs it (a highlight or pill) with it; a move never touches backgrounds or art that bleeds off the canvas.
"""

import math

from .composition import GROUND_SHARE, _inside, geometry_boxes, hugs

NOT_REPAIRABLE = ("this scatter has no pattern-scatter recipe to thin or re-seed; re-spread it by hand "
                  "(move the largest motifs into the gaps) or rebuild it with pattern-scatter")


def _overlaps(box, x0, x1):
    return min(box[0] + box[2], x1) - max(box[0], x0) > 0


class Scene:
    """The document's layer tree with the canvas boxes the composition family measures."""

    def __init__(self, project):
        self.project = project
        self.resolved, self.geo = geometry_boxes(project)
        canvas = project.state["canvas"]
        self.width, self.height = canvas["width"], canvas["height"]
        self.children = {}
        self.roots = []
        for item in self.resolved.values():
            (self.children.setdefault(item["parent"], []) if item.get("parent") in self.resolved
             else self.roots).append(item)

    def ancestors(self, ident):
        item = self.resolved.get(ident)
        while item is not None and item.get("parent") in self.resolved:
            item = self.resolved[item["parent"]]
            yield item["id"]

    def fixed(self, item):
        """Backgrounds and art that bleeds off the canvas stay where they are."""
        x, y, w, h = self.geo[item["id"]]
        if item.get("role") == "background" or any(
                self.resolved[a].get("role") == "background" for a in self.ancestors(item["id"])):
            return True
        if item["type"] == "text":
            return False
        return x < -0.5 or y < -0.5 or x + w > self.width + 0.5 or y + h > self.height + 0.5 or (
            w >= self.width - 1 and h >= self.height - 1)

    def select(self, wanted, exclude=()):
        """The topmost visible, movable layers whose box ``wanted`` accepts; groups that do not qualify as a
        whole (or hold an excluded layer) are searched inside."""
        exclude = set(exclude)
        holding = {a for ident in exclude for a in self.ancestors(ident)}
        out = []

        def visit(item):
            if not item.get("visible", True) or item.get("opacity", 1) <= 0 or item["type"] == "adjustment":
                return
            ident = item["id"]
            if ident in exclude:
                return
            box = self.geo.get(ident)
            if box is not None and box[2] > 0 and box[3] > 0 and ident not in holding and not self.fixed(item) \
                    and wanted(box):
                out.append(ident)
                return
            for child in self.children.get(ident, []):
                visit(child)

        for root in self.roots:
            visit(root)
        return self.whole(out)

    def descendants(self, ident):
        out = []
        for child in self.children.get(ident, []):
            out += [child["id"], *self.descendants(child["id"])]
        return out

    def whole(self, ids):
        """``ids`` without the layers that touch a layer left out (the base of a microphone drawn as three
        shapes, when only the base lies below a band): a drawing moves whole or not at all. A layer that holds
        another (a card under its text) is not a part of it, and glows that fade out touch everything."""
        ids = list(ids)
        inside = set(ids) | {d for ident in ids for d in self.descendants(ident)}
        holding = {a for ident in ids for a in self.ancestors(ident)}
        others = [x["id"] for x in self.resolved.values()
                  if x["id"] not in inside and x["id"] not in holding
                  and x["type"] not in ("group", "adjustment", "gradient")
                  and x.get("visible", True) and x.get("opacity", 1) > 0 and not self.background(x)]

        def touches(a, b):
            if _inside(a, b, 0) or _inside(b, a, 0):
                return False
            return (min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) >= -1
                    and min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) >= -1)

        changed = True
        while changed:
            changed = False
            for ident in list(ids):
                if any(touches(self.geo[ident], self.geo[other]) for other in others):
                    ids.remove(ident)
                    others.append(ident)
                    changed = True
        return ids

    def background(self, item):
        x, y, w, h = self.geo[item["id"]]
        return item.get("role") == "background" or (item["type"] != "text" and x <= 0.5 and y <= 0.5
                                                    and x + w >= self.width - 0.5 and y + h >= self.height - 0.5)

    def with_riders(self, ids):
        """``ids`` plus the chips that hug any text among them and the glows around any of them (even a glow that
        bleeds off the canvas), without layers whose group is also listed."""
        ids = list(dict.fromkeys(ids))
        for ident in list(ids):
            item = self.resolved.get(ident)
            if item is None:
                continue
            box = self.geo[ident]
            for other in self.resolved.values():
                glow = self.geo[other["id"]]
                if (other["type"] == "gradient" and other["id"] not in ids and other.get("visible", True)
                        and not self.background(other) and _inside(box, glow)
                        and glow[2] * glow[3] <= 16 * box[2] * box[3]):
                    ids.append(other["id"])
            if item["type"] != "text":
                continue
            for other in self.resolved.values():
                if (other["type"] == "shape" and other["id"] not in ids and other.get("visible", True)
                        and hugs(self.geo[ident], self.geo[other["id"]])):
                    ids.append(other["id"])
                    break
        chosen = set(ids)
        return [ident for ident in ids if not chosen & set(self.ancestors(ident))]

    def moves(self, shifts):
        """Relative moves for ``{id: (dx, dy)}``; None when every shift rounds to nothing."""
        operations = []
        for ident, (dx, dy) in shifts.items():
            if round(dx) or round(dy):
                operations.append({"type": "move", "target": ident, "x": round(dx), "y": round(dy), "relative": True})
        return operations or None

    def shift(self, ids, dx, dy):
        return self.moves({ident: (dx, dy) for ident in self.with_riders(ids)})


def _rows(scene, ids):
    """``ids`` clustered into rows that share vertical extent, top to bottom: ``[(top, bottom, [ids])]``. A glow
    spans the rows around it, so it joins the row its centre is in instead of merging them."""
    rows, glows = [], []
    for ident in sorted(ids, key=lambda i: scene.geo[i][1]):
        x, y, w, h = scene.geo[ident]
        if scene.resolved[ident]["type"] == "gradient":
            glows.append(ident)
        elif rows and y <= rows[-1][1] + 1:  # Touching parts of a drawing share a row.
            top, bottom, members = rows[-1]
            rows[-1] = (top, max(bottom, y + h), members + [ident])
        else:
            rows.append((y, y + h, [ident]))
    for ident in glows:
        centre = scene.geo[ident][1] + scene.geo[ident][3] / 2
        if rows:
            min(rows, key=lambda row: 0 if row[0] <= centre <= row[1] else min(abs(row[0] - centre),
                                                                               abs(row[1] - centre)))[2].append(ident)
    return rows


def _spread(scene, ids, band_top=None, excess=0.0, anchor="top"):
    """Shifts that change the gaps between the rows of ``ids``, each in proportion to its size so that equal gaps
    stay equal. With ``band_top`` the band's gap shrinks and the others grow until the band is no larger than the
    largest of them (the total height is kept); without, every gap grows by its share of ``excess`` (the content
    spreads into an edge band). The first row stays (the last for ``anchor="bottom"``)."""
    rows = _rows(scene, ids)
    gaps = [(i, rows[i + 1][0] - rows[i][1]) for i in range(len(rows) - 1) if rows[i + 1][0] - rows[i][1] > 0.5]
    band = [(i, gap) for i, gap in gaps if band_top is not None and abs(rows[i][1] - band_top) <= 1]
    others = [(i, gap) for i, gap in gaps if all(i != j for j, _ in band)]
    total = sum(gap for _, gap in others)
    if not others or total <= 0 or (band_top is not None and not band):
        return None
    if band:
        (index, height), widest = band[0], max(gap for _, gap in others)
        scale = (total + height) / (total + widest)
        grow = {i: gap * (scale - 1) for i, gap in others}
        grow[index] = widest * scale - height
    else:
        grow = {i: excess * gap / total for i, gap in others}
    # grow[i] is the change of the gap below row i.
    shifts, moved = {}, 0.0
    order = range(len(rows)) if anchor == "top" else reversed(range(len(rows)))
    for index in order:
        if anchor == "top":
            moved += grow.get(index - 1, 0)
        for ident in rows[index][2]:
            shifts[ident] = (0, moved)
        if anchor != "top":
            moved -= grow.get(index - 1, 0)
    return scene.moves({ident: shift for ident, shift in shifts.items()})


def _margin_drift(scene, finding):
    values = finding["values"]
    offset = values["offset"]
    strays = [i for i in values.get("stray_ids", []) if i in scene.resolved]
    anchors = [i for i in finding.get("layer_ids", []) if i not in strays and i in scene.resolved]
    out = []
    if strays:
        out.append(("snap-to-margin", scene.shift(strays, -offset, 0)))
    if anchors:
        out.append(("move-margin-to-edge", scene.shift(anchors, offset, 0)))
    return out


def _column(scene, ids):
    boxes = [scene.geo[i] for i in ids]
    return min(b[0] for b in boxes), max(b[0] + b[2] for b in boxes)


def _uneven_rhythm(scene, finding, unit):
    ids = finding.get("layer_ids", [])
    if len(ids) != 3 or any(i not in scene.resolved for i in ids):
        return []
    a, b, c = ids
    g1, g2 = finding["values"]["gaps"]
    sizes = finding["values"].get("sizes") or []
    siblings = len(sizes) == 3 and all(s and min(s, sizes[1]) / max(s, sizes[1]) > 0.95 for s in sizes)
    x0, x1 = _column(scene, ids)

    def below(ident):
        top = scene.geo[ident][1]
        return scene.select(lambda box: box[1] >= top - 1 and _overlaps(box, x0, x1), exclude=[a])

    out = []
    if g1 > g2:
        if siblings:
            out.append(("even-middle", scene.shift([b], 0, -(g1 - g2) / 2)))
        else:
            out.append(("middle-to-its-group", scene.shift([b], 0, -(g1 - g2))))
        out.append(("close-up-stack", scene.shift(below(b), 0, -(g1 - g2))))
    else:
        out.append(("even-middle", scene.shift([b], 0, (g2 - g1) / 2)))
        out.append(("close-up-stack", scene.shift(below(c), 0, -(g2 - g1))))
    if siblings:
        step = max(unit, round(min(g1, g2) / unit) * unit)
        first, second = step - g1, (step - g1) + (step - g2)
        shifts = {i: (0, first) for i in scene.with_riders([b])}
        shifts.update({i: (0, second) for i in scene.with_riders(below(c))})
        out.append(("spacing-scale", scene.moves(shifts)))
    return out


def _crowding(scene, finding, unit):
    ids = finding.get("layer_ids", [])
    if len(ids) != 2 or any(i not in scene.resolved for i in ids):
        return []
    upper, lower = ids
    gap = finding["values"]["gap"]
    x0, x1 = _column(scene, ids)
    out = []
    needs = sorted({math.ceil(unit - gap), math.ceil(finding["threshold"]["min_gap_px"] - gap)}, reverse=True)
    for need in (n for n in needs if n > 0):
        top, bottom = scene.geo[lower][1], scene.geo[upper][1] + scene.geo[upper][3]
        out.append((f"push-down:{need}", scene.shift([lower], 0, need)))
        out.append((f"lift:{need}", scene.shift([upper], 0, -need)))
        out.append((f"push-down-stack:{need}", scene.shift(scene.select(
            lambda box: box[1] >= top - 1 and _overlaps(box, x0, x1), exclude=[upper]), 0, need)))
        out.append((f"lift-stack:{need}", scene.shift(scene.select(
            lambda box: box[1] + box[3] <= bottom + 1 and _overlaps(box, x0, x1), exclude=[lower]), 0, -need)))
    return out


def _frame(scene, region):
    """The panel a band sits in (the smallest that holds it and covers a fifth of the canvas), or the canvas."""
    area = scene.width * scene.height
    best = None
    for item in scene.resolved.values():
        box = scene.geo[item["id"]]
        if (item["type"] not in ("shape", "image") or not item.get("visible", True) or scene.fixed(item)
                or box[2] * box[3] < GROUND_SHARE * area or not _inside(region, box)):
            continue
        if best is None or box[2] * box[3] < scene.geo[best][2] * scene.geo[best][3]:
            best = item["id"]
    return best, (scene.geo[best] if best else (0.0, 0.0, float(scene.width), float(scene.height)))


def _dead_band(scene, finding, unit):
    x, y, w, h = finding["region"]
    values = finding["values"]
    panel, frame = _frame(scene, finding["region"])
    members = scene.select(lambda box: _inside(box, frame), exclude=[panel] if panel else [])
    if not members:
        return []
    edge = values.get("edge")
    out = []
    if edge is None:
        target = max(values.get("typical_gap", 0), 2 * unit)
        excess = h - target
        if excess <= 0:
            return []
        lower = scene.whole([i for i in members if scene.geo[i][1] >= y + h - 1 and _overlaps(scene.geo[i], x, x + w)])
        out.append(("spread-into-gaps", _spread(scene, members, y)))
        upper = scene.whole([i for i in members if scene.geo[i][1] + scene.geo[i][3] <= y + 1
                             and _overlaps(scene.geo[i], x, x + w)])
        out.append(("move-lower-up", scene.shift(lower, 0, -excess)))
        out.append(("move-lower-up-half", scene.shift(lower, 0, -excess / 2)))
        out.append(("move-upper-down-half", scene.shift(upper, 0, excess / 2)))
        return out
    top = min(scene.geo[i][1] for i in members)
    bottom = max(scene.geo[i][1] + scene.geo[i][3] for i in members)
    opposite = top - frame[1] if edge == "bottom" else frame[1] + frame[3] - bottom
    excess = h - max(opposite, 0)
    if excess <= 0:
        return []
    sign = 1 if edge == "bottom" else -1
    anchor = "top" if edge == "bottom" else "bottom"
    out.append(("spread-content", _spread(scene, members, excess=excess, anchor=anchor)))
    out.append(("centre-content", scene.shift(members, 0, sign * excess / 2)))
    out.append(("spread-content-half", _spread(scene, members, excess=excess / 2, anchor=anchor)))
    return out


def _clumped_scatter(scene, finding):
    ids = finding.get("layer_ids", [])
    group = scene.project.layer(ids[0]) if ids else None
    recipe = (group or {}).get("pattern_scatter") or {}
    if not (recipe.get("source") or recipe.get("mark")):
        return []
    seed = int(recipe.get("seed", 0))
    out = [(f"thin:{keep}", [{"type": "pattern-scatter", "target": group["id"], "thin": keep}]) for keep in (0.85, 0.7)]
    out += [(f"reseed:{seed + k}", [{"type": "pattern-scatter", "target": group["id"], "seed": seed + k}])
            for k in (1, 2, 3)]
    return out


def candidates(project, finding):
    """``(candidates, reason)``: ``(name, operations)`` pairs in a fixed order for one composition finding, and
    why there are none when the list is empty."""
    code = finding.get("code")
    unit = float(finding.get("spacing_unit") or 1)
    scene = Scene(project)
    if code == "margin_drift":
        found = _margin_drift(scene, finding)
    elif code == "uneven_rhythm":
        found = _uneven_rhythm(scene, finding, unit)
    elif code == "crowding":
        found = _crowding(scene, finding, unit)
    elif code == "dead_band":
        found = _dead_band(scene, finding, unit)
    elif code == "clumped_scatter":
        found = _clumped_scatter(scene, finding)
        if not found:
            return [], NOT_REPAIRABLE
    else:
        found = []
    found = [(name, operations) for name, operations in found if operations]
    seen, unique = set(), []
    for name, operations in found:
        key = repr(sorted((op["target"], op.get("x"), op.get("y"), op.get("thin"), op.get("seed"))
                          for op in operations))
        if key not in seen:
            seen.add(key)
            unique.append((name, operations))
    return unique, None if unique else "no layer it concerns can be moved (backgrounds and bleeding art stay put)"
