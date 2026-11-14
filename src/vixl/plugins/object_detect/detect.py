"""Propose objects in an existing document: which layers form one, and of what kind.

Nothing here draws or guesses from pixels. The signals are, from certain to uncertain:

1. **Recipe groups.** An ``organic`` group is the kind its preset maps to (``objects.organic_presets``), a
   ``character`` group a person, a ``drawing`` group the kind its name says. Collections (``parts.COLLECTIONS``:
   charts, tables, diagrams, containers, repeats) are not objects and nothing inside them is looked at.
2. **Named groups.** A plain group whose name is a kind or alias (``objects.find``), or whose children name the
   parts of one kind better than any other.
3. **Loose siblings.** Layers that share a kind as name prefix (``guitar-body``, ``guitar-neck``), and layers named
   after parts whose ink touches (the ``parts.components`` union-find), become a proposed ``group`` plus ``object``.
   Grouping moves the layers to one place in the stack, so each such batch is tried on a copy first: a proposal
   that would change the render is marked ``changes_render`` and never applied.
4. **Raster images**, only when the caller names a provider: its ``detect`` labels that are kinds of the taxonomy.

Every proposal is ``{source, layers, proposed_kind, confidence, reasons, parts, batch}`` where ``batch`` is ordinary
``group`` and ``object`` operations. ``detect`` returns them and changes nothing unless ``apply`` is true.
"""

import re

import numpy as np

from ... import objects
from ...errors import VixlError, require
from ...parts import COLLECTIONS, components, part_mask

DEFAULT_CONFIDENCE = 0.7
DEFAULT_TOLERANCE = 2
# Layer types that can be a loose part of an object; text, fills, frames, fields and adjustments are not.
LEAVES = ("shape", "pathfinder", "raster", "pixel", "paint", "symbol")
SIDE_WORDS = {"l": "left", "left": "left", "r": "right", "right": "right"}
MAX_LOOSE = 300
MAX_IMAGES = 8
MAX_LABEL = 60
PROVIDER_CONFIDENCE = 0.6
REGION_CONFIDENCE = 0.4
PLURAL_CONFIDENCE = 0.5
# The largest 8-bit channel difference that still counts as the same picture (see Detector.difference).
ROUNDING = 1


def words(name):
    """The lower-case words of a layer name: ``cat/ear-L 2`` and ``catEarL`` both read ``cat ear l``."""
    return re.findall(r"[a-z]+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(name)).casefold())


class Taxonomy:
    """The kinds an object may be proposed as (not a domain, not a texture) and the part names of each."""

    def __init__(self, kinds):
        self.kinds = kinds
        self.parts, self.usable = {}, set()
        for name, entry in kinds.items():
            fields = objects.merged(name, kinds)
            if entry.get("parent") is None or fields.get("texture"):
                continue
            self.usable.add(name)
            self.parts[name] = {part["name"]: part for part in fields.get("parts", [])}
        self.part_names = {part for parts in self.parts.values() for part in parts}
        self.exact = set(kinds) | {objects.slug(alias) for entry in kinds.values() for alias in entry.get("aliases", [])}

    def plural(self, tokens, named):
        """Whether the words that name the kind are its plural (``clouds``): the layers may hold several."""
        return "-".join(tokens[named[1]:named[2]]) not in self.exact

    def named(self, tokens):
        """``(kind, start, end)`` for the longest run of words that is a kind or alias, or None."""
        for size in (3, 2, 1):
            for start in range(len(tokens) - size + 1):
                phrase = "-".join(tokens[start:start + size])
                if len(phrase) < 3 or phrase in objects.STOP_WORDS:
                    continue
                found = objects.find(phrase, self.kinds)
                if found in self.usable:
                    return found, start, start + size
        return None

    def part(self, tokens, names):
        """``(part, side)`` for the longest run of words that is one of ``names`` (singular or plural)."""
        side = next((SIDE_WORDS[token] for token in tokens if token in SIDE_WORDS), None)
        plain = [token for token in tokens if token not in SIDE_WORDS]
        for size in range(len(plain), 0, -1):
            for start in range(len(plain) - size + 1):
                phrase = "-".join(plain[start:start + size])
                for candidate in (phrase, phrase[:-1] if phrase.endswith("s") else None):
                    if candidate and candidate in names:
                        return candidate, side
        return None

    def fit(self, kind, items):
        """How well the word lists ``items`` name the parts of ``kind``: ``{matched: [(index, part, side)], parts,
        required, missing, share}``."""
        names = self.parts.get(kind, {})
        matched = []
        for position, tokens in enumerate(items):
            found = self.part(tokens, names)
            if found:
                matched.append((position, *found))
        named = {part for _, part, _ in matched}
        required = [name for name, part in names.items() if part.get("required")]
        missing = [name for name in required if name not in named]
        return {"matched": matched, "parts": sorted(named), "missing": missing,
                "required": (len(required) - len(missing)) / len(required) if required else 1.0,
                "share": len(matched) / len(items) if items else 0.0}

    def by_parts(self, items):
        """The kind whose parts the word lists name best, as ``(kind, confidence, fit, tied)``, or ``(None, 0, None,
        tied)`` when fewer than two parts are named or unrelated kinds fit equally. Kinds that fit equally well
        under one class give that class (head, body, ear, leg and tail are a mammal, not yet a dog or a cat)."""
        scored = []
        for kind in self.parts:
            fit = self.fit(kind, items)
            if len(fit["parts"]) < 2:
                continue
            evidence = 0.45 + 0.1 * min(len(fit["parts"]), 5)
            scored.append((min(0.9, (0.5 * fit["required"] + 0.5 * fit["share"]) * evidence), kind, fit))
        if not scored:
            return None, 0.0, None, []
        best = max(score for score, _, _ in scored)
        tied = [(score, kind, fit) for score, kind, fit in scored if best - score < 1e-9]
        names = sorted(kind for _, kind, _ in tied)
        if len(tied) == 1:
            return tied[0][1], best, tied[0][2], names
        chains = [objects.chain(kind, self.kinds) for kind in names]
        common = []
        for level in zip(*chains):
            if len(set(level)) > 1:
                break
            common.append(level[0])
        shared = common[-1] if common else None
        if shared not in self.usable:
            return None, 0.0, None, names
        for score, kind, fit in scored:
            if kind == shared:
                return shared, score, fit, names
        return shared, best * 0.8, self.fit(shared, items), names


def _is_collection(layer):
    return any(layer.get(key) for key in COLLECTIONS if key != "drawing")


def _strip(tokens, prefix):
    return tokens[len(prefix):] if prefix and tokens[:len(prefix)] == prefix and len(tokens) > len(prefix) else tokens


def _part_operations(matched, layers):
    """``object`` part operations for ``[(index, part, side)]``, one per part and side."""
    grouped = {}
    for position, part, side in matched:
        grouped.setdefault((part, side), []).append(layers[position]["name"])
    operations = []
    for (part, side), names in grouped.items():
        target = {"target": names[0]} if len(names) == 1 else {"targets": names}
        operations.append({"type": "object", "action": "part", **target, "part": part, **({"side": side} if side else {})})
    return operations


def _parts(matched, layers):
    return [{"layer": layers[position]["name"], "part": part, **({"side": side} if side else {})}
            for position, part, side in matched]


def _fit_reasons(kind, fit, count):
    reasons = []
    if fit["matched"]:
        reasons.append(f"{len(fit['matched'])} of {count} layers name {kind} parts ({', '.join(fit['parts'])})")
    if fit["missing"]:
        reasons.append(f"no layer names the required {', '.join(fit['missing'])}: the object check will ask for "
                       + ("it" if len(fit["missing"]) == 1 else "them"))
    return reasons


class Detector:
    def __init__(self, project, targets, tolerance):
        self.project = project
        self.tolerance = tolerance
        self.layers = project.state["layers"]
        self.index = {layer["id"]: layer for layer in self.layers}
        self.children = {}
        for layer in self.layers:
            self.children.setdefault(layer.get("parent"), []).append(layer)
        self.taxonomy = Taxonomy(objects.registry(getattr(project, "_workspace", None)))
        self.presets = objects.organic_presets()
        self.wanted = None
        if targets:
            self.wanted = set()
            for ref in targets:
                stack = [project.layer(ref)]
                while stack:
                    layer = stack.pop()
                    self.wanted.add(layer["id"])
                    stack.extend(self.children.get(layer["id"], []))
        self.names = {layer["name"] for layer in self.layers}
        self.proposals, self.notes, self.unclassified, self.images = [], [], [], []
        self._base = self._frame = None

    # -- helpers

    def selected(self, layer):
        return self.wanted is None or layer["id"] in self.wanted

    def unique(self, name):
        candidate, count = name, 1
        while candidate in self.names:
            count += 1
            candidate = f"{name}-{count}"
        self.names.add(candidate)
        return candidate

    def shown(self, layer):
        while layer:
            if not layer.get("visible", True) or layer.get("opacity", 1) <= 0:
                return False
            layer = self.index.get(layer.get("parent"))
        return True

    def base(self):
        if self._base is None:
            self._base = np.asarray(self.project.render())
        return self._base

    def difference(self, trial):
        """The largest 8-bit channel difference between the document's render and ``trial``'s. A group is composited
        on its own surface first, which can round an antialiased pixel where two of its parts overlap one level
        differently; a restacking that shows is far larger."""
        other = np.asarray(trial.render())
        if other.shape != self.base().shape:
            return 255
        return int(np.abs(other.astype(np.int16) - self.base().astype(np.int16)).max())

    def pieces(self, layers):
        """The layers split into sets whose ink touches within the tolerance; layers that draw nothing are left out."""
        from ...render import resolve_layout, resolved_layers

        if self._frame is None:
            resolved = resolved_layers(self.project)
            self._frame = ({item["id"]: item for item in resolved}, resolve_layout(self.project, layers=resolved))
        index, local = self._frame
        masks, kept = [], []
        for layer in layers:
            mask = part_mask(self.project, index[layer["id"]], local, index)
            if mask.any():
                masks.append(mask)
                kept.append(layer)
        if len(kept) < 2:
            return [kept] if kept else []
        union = np.any(masks, axis=0)
        rows, cols = np.flatnonzero(union.any(axis=1)), np.flatnonzero(union.any(axis=0))
        pad = int(np.ceil(self.tolerance)) + 1
        top, left = max(0, rows[0] - pad), max(0, cols[0] - pad)
        masks = [mask[top:rows[-1] + pad + 1, left:cols[-1] + pad + 1] for mask in masks]
        return [[kept[i] for i in piece] for piece in components(masks, self.tolerance)]

    def add(self, source, layers, kind, confidence, reasons, parts, batch, **extra):
        """Record a proposal once its batch has run on a copy; a batch that fails is reported and dropped."""
        proposal = {"source": source, "layers": [layer["name"] for layer in layers], "proposed_kind": kind,
                    "confidence": round(min(1.0, max(0.0, confidence)), 2), "reasons": reasons, "parts": parts,
                    "batch": batch, **extra}
        if batch:
            trial = self.project.clone()
            try:
                trial.apply(batch, detail="compact")
            except VixlError as error:
                self.notes.append(f"{', '.join(proposal['layers'])}: not proposed as a {kind}, its batch would fail "
                                  f"({error})")
                return None
            if batch[0]["type"] == "group" and self.difference(trial) > ROUNDING:
                proposal["changes_render"] = True
                proposal["confidence"] = min(proposal["confidence"], 0.4)
                reasons.append("grouping these layers would change the picture (layers between them in the stack "
                               "overlap them): reorder first, or group by hand")
        self.proposals.append(proposal)
        return proposal

    # -- groups

    def group(self, layer, part_of_owner=False):
        """Propose for one group, then look inside it."""
        if layer["type"] != "group" or _is_collection(layer):
            return
        nested = self.children.get(layer["id"], [])
        if layer.get("object"):
            for child in nested:
                self.group(child, bool(child.get("object_part")))
            return
        if not self.selected(layer):
            if not any(layer.get(key) for key in ("character", "organic", "drawing")):
                self.container(layer["id"])
            return
        if layer.get("character"):
            self.add("recipe", [layer], "person", 1.0,
                     ["a character group: its standard parts already read as person parts"], [],
                     [{"type": "object", "target": layer["name"], "kind": "person"}])
            return
        tokens = words(layer["name"])
        organic = layer.get("organic") if isinstance(layer.get("organic"), dict) else {}
        kind = self.presets.get(organic.get("preset"))
        if kind in self.taxonomy.usable:
            self.existing("recipe", layer, kind, 1.0, [f"organic preset {organic['preset']} is the kind {kind}"], tokens)
            return
        if kind:
            return  # a texture preset (fur, spots, scales): a surface, not an object
        if layer.get("organic") or layer.get("drawing"):
            recipe = "an organic" if layer.get("organic") else "a drawing"
            named = self.taxonomy.named(tokens)
            if named:
                self.existing("recipe", layer, named[0], 0.8,
                              [f"{recipe} group whose name {layer['name']!r} names the kind {named[0]}"], tokens)
            else:
                self.unclassified.append({"layers": [layer["name"]], "reason": f"{recipe} group whose name names no "
                                          "kind: declare it with {type: object, target, kind}"})
            return
        if part_of_owner:  # a part of the object above it, not an object of its own
            for child in nested:
                self.group(child)
            return
        items = [child for child in nested if not child.get("generated") and child["type"] != "adjustment"]
        lists = [_strip(words(child["name"]), tokens) for child in items]
        named = self.taxonomy.named(tokens)
        claimed = set()
        if named:
            kind = named[0]
            fit = self.taxonomy.fit(kind, lists)
            confidence = 0.8 + (0.15 * fit["share"] if self.taxonomy.parts[kind] else 0)
            reasons = [f"group name {layer['name']!r} names the kind {kind}", *_fit_reasons(kind, fit, len(items))]
            if self.taxonomy.plural(tokens, named) and not fit["matched"]:
                confidence = PLURAL_CONFIDENCE
                reasons.append("the name is a plural: the group may hold several, each an object of its own")
            self.add("group", [layer], kind, confidence, reasons, _parts(fit["matched"], items),
                     [{"type": "object", "target": layer["name"], "kind": kind}, *_part_operations(fit["matched"], items)])
            claimed = {items[position]["id"] for position, _, _ in fit["matched"]}
        elif len(items) >= 2:
            kind, confidence, fit, tied = self.taxonomy.by_parts(lists)
            if kind:
                reasons = _fit_reasons(kind, fit, len(items))
                if len(tied) > 1:
                    reasons.append(f"the names fit {', '.join(tied)} equally: declared as their class; set a closer "
                                   "kind if you know it")
                self.add("group", [layer], kind, confidence, reasons, _parts(fit["matched"], items),
                         [{"type": "object", "target": layer["name"], "kind": kind},
                          *_part_operations(fit["matched"], items)])
                claimed = {items[position]["id"] for position, _, _ in fit["matched"]}
            else:
                if tied:
                    self.unclassified.append({"layers": [layer["name"]], "reason": "its part names fit "
                                              f"{', '.join(tied)} equally"})
                self.container(layer["id"])
                return
        for child in nested:
            self.group(child, child["id"] in claimed)

    def existing(self, source, layer, kind, confidence, reasons, tokens):
        """A proposal that declares a recipe group, naming the children whose names are parts of the kind."""
        items = [child for child in self.children.get(layer["id"], []) if not child.get("generated")]
        fit = self.taxonomy.fit(kind, [_strip(words(child["name"]), tokens) for child in items])
        if fit["missing"]:
            reasons.append(f"its layers do not name the required {', '.join(fit['missing'])}: the object check will "
                           "ask for " + ("it" if len(fit["missing"]) == 1 else "them"))
        self.add(source, [layer], kind, confidence, reasons, _parts(fit["matched"], items),
                 [{"type": "object", "target": layer["name"], "kind": kind}, *_part_operations(fit["matched"], items)])

    # -- loose siblings

    def container(self, parent):
        """Look at the direct children of the page (``parent`` None) or of a plain group: groups first, then the
        loose layers between them."""
        siblings = self.children.get(parent, [])
        for layer in siblings:
            self.group(layer)
        loose = [layer for layer in siblings if layer["type"] in LEAVES and self.selected(layer) and self.shown(layer)
                 and not layer.get("generated") and not layer.get("object_part")]
        self.images.extend(layer for layer in loose if layer["type"] == "raster")
        if len(loose) < 2:
            return
        if len(loose) > MAX_LOOSE:
            self.notes.append(f"{len(loose)} loose layers in one place: only the first {MAX_LOOSE} were compared; "
                              "pass targets to look at the rest")
            loose = loose[:MAX_LOOSE]
        order = {layer["id"]: position for position, layer in enumerate(siblings)}
        prefixed, pool = {}, []
        for layer in loose:
            tokens = words(layer["name"])
            named = self.taxonomy.named(tokens)
            if named and named[1] == 0 and named[2] < len(tokens):
                prefixed.setdefault((named[0], tuple(tokens[:named[2]])), []).append((layer, tokens[named[2]:]))
            else:
                pool.append((layer, tokens))
        for (kind, prefix), members in prefixed.items():
            if len(members) < 2:
                pool.extend((layer, [*prefix, *tokens]) for layer, tokens in members)
                continue
            layers = [layer for layer, _ in members]
            fit = self.taxonomy.fit(kind, [tokens for _, tokens in members])
            pieces = self.pieces(layers)
            confidence = 0.75 + (0.15 * fit["share"] if self.taxonomy.parts[kind] else 0)
            reasons = [f"{len(layers)} layer names start with {'-'.join(prefix)!r}, the kind {kind}",
                       *_fit_reasons(kind, fit, len(layers))]
            if len(pieces) <= 1:
                confidence += 0.05
                reasons.append(f"their ink touches (within {self.tolerance:g} px)")
            else:
                confidence -= 0.15
                reasons.append(f"their ink falls into {len(pieces)} separate pieces: the connected check will flag "
                               "the floating ones")
            self.loose(layers, kind, min(confidence, 0.95), reasons, fit, order, "-".join(prefix))
        named = [(layer, tokens) for layer, tokens in pool if self.taxonomy.part(tokens, self.taxonomy.part_names)]
        if len(named) < 2:
            return
        tokens_of = {layer["id"]: tokens for layer, tokens in named}
        for piece in self.pieces([layer for layer, _ in named]):
            if len(piece) < 2:
                continue
            kind, confidence, fit, tied = self.taxonomy.by_parts([tokens_of[layer["id"]] for layer in piece])
            if not kind:
                if tied:
                    self.unclassified.append({"layers": [layer["name"] for layer in piece], "reason": "touching layers "
                                              f"whose part names fit {', '.join(tied)} equally"})
                continue
            reasons = [*_fit_reasons(kind, fit, len(piece)), f"their ink touches (within {self.tolerance:g} px)"]
            if len(tied) > 1:
                reasons.append(f"the names fit {', '.join(tied)} equally: proposed as their class; set a closer kind "
                               "if you know it")
            self.loose(piece, kind, confidence, reasons, fit, order, kind)

    def loose(self, layers, kind, confidence, reasons, fit, order, name):
        positions = sorted(order[layer["id"]] for layer in layers)
        reasons.append("they are adjacent in the stack" if positions[-1] - positions[0] == len(positions) - 1
                       else "other layers sit between them in the stack")
        group = self.unique(name)
        self.add("loose", layers, kind, confidence, reasons, _parts(fit["matched"], layers),
                 [{"type": "group", "name": group, "targets": [layer["name"] for layer in layers]},
                  {"type": "object", "target": group, "kind": kind}, *_part_operations(fit["matched"], layers)],
                 group=group)

    # -- raster images through a provider

    def provider(self, name):
        images = [layer for layer in self.images if not layer.get("object_part")]
        if not images:
            return
        if not name:
            self.notes.append(f"{len(images)} loose raster image" + ("s were" if len(images) != 1 else " was")
                              + " not examined: names and geometry say nothing about pixels. Pass provider (a "
                              "configured AI provider) to offer its detections as candidates")
            return
        from ...render import layer_canvas_surface, resolve_layout, resolved_layers
        from ..ai.ai import encoded, normalize_vision
        from ..ai.models import route

        try:
            backend = route("detect", None if name is True else name)
        except VixlError as error:
            require(error.code in ("provider_not_configured", "unsupported_capability", "network_disabled"),
                    str(error), error.code, field="provider")
            self.notes.append(f"No provider offers detect, so raster images were not examined ({error})")
            return
        if len(images) > MAX_IMAGES:
            self.notes.append(f"Only the first {MAX_IMAGES} of {len(images)} raster images were sent to the provider")
        resolved = resolved_layers(self.project)
        index, local = {item["id"]: item for item in resolved}, resolve_layout(self.project, layers=resolved)
        canvas = self.project.state["canvas"]
        for layer in images[:MAX_IMAGES]:
            surface = layer_canvas_surface(self.project, index[layer["id"]], local, index)
            box = surface.getchannel("A").getbbox()
            if not box:
                continue
            source = getattr(backend, "name", "provider")
            answer = normalize_vision("detect", backend.invoke("detect", {
                "source_image": encoded(surface), "query": "", "width": canvas["width"], "height": canvas["height"]}))
            found = []
            for item in answer["objects"]:
                label = item["label"][:MAX_LABEL]
                named = self.taxonomy.named(words(label))
                if named and item["box"][2] > 0 and item["box"][3] > 0:
                    found.append((named[0], label, item["box"]))
            area = (box[2] - box[0]) * (box[3] - box[1])
            whole = [entry for entry in found if entry[2][2] * entry[2][3] >= 0.5 * area]
            if len(found) == 1 and whole:
                kind, label, region = found[0]
                group = self.unique(kind)
                self.add("provider", [layer], kind, PROVIDER_CONFIDENCE,
                         [f"provider {source} labels the image {label!r} (an unverified label)"], [],
                         [{"type": "group", "name": group, "targets": [layer["name"]]},
                          {"type": "object", "target": group, "kind": kind}], group=group, box=region)
                continue
            for kind, label, region in found:
                self.add("provider", [layer], kind, REGION_CONFIDENCE,
                         [f"provider {source} labels a region {label!r}, one of {len(found)} in this image: "
                          "cut it into its own layer to declare it"], [], [], box=region)


def propose(project, *, targets=None, tolerance=DEFAULT_TOLERANCE, provider=None):
    """The ``Detector`` holding ``proposals``, ``notes`` and ``unclassified`` for the current page; nothing is
    changed."""
    detector = Detector(project, targets, tolerance)
    detector.container(None)
    detector.provider(provider)
    return detector


def detect(project, *, targets=None, apply=False, min_confidence=DEFAULT_CONFIDENCE, tolerance=DEFAULT_TOLERANCE,
           provider=None):
    """The object-detect workflow: proposals for the undeclared objects of ``project``. With ``apply`` the batches
    of the proposals at or above ``min_confidence`` run as one undo step, unless the picture would change."""
    from ...model import finite

    require(type(apply) is bool, "apply must be boolean", field="apply")
    require(provider is None or type(provider) is bool or (isinstance(provider, str) and provider.strip()),
            "provider is a provider name or true", field="provider")
    require(targets is None or (isinstance(targets, list) and all(isinstance(t, str) for t in targets)),
            "targets is a list of layer names", field="targets")
    min_confidence = finite(min_confidence, "min_confidence", 0, 1)
    tolerance = finite(tolerance, "tolerance", 0, 100)
    found = propose(project, targets=targets, tolerance=tolerance, provider=provider or None)
    result = {"proposals": found.proposals, "count": len(found.proposals), "applied": [],
              **({"unclassified": found.unclassified} if found.unclassified else {}),
              **({"notes": found.notes} if found.notes else {})}
    if not apply:
        result["dry_run"] = True
        if found.proposals:
            result["next"] = ("Nothing was changed. Apply a proposal's batch with vixl_apply(operations=batch), or "
                              "rerun with apply: true to apply every proposal at or above min_confidence "
                              f"({min_confidence:g})")
        return result
    chosen, skipped = [], []
    for proposal in found.proposals:
        reason = ("it has no batch" if not proposal["batch"]
                  else "grouping would change the picture" if proposal.get("changes_render")
                  else f"confidence {proposal['confidence']:g} is below {min_confidence:g}"
                  if proposal["confidence"] < min_confidence else None)
        if reason:
            skipped.append({"layers": proposal["layers"], "proposed_kind": proposal["proposed_kind"], "reason": reason})
        else:
            chosen.append(proposal)
    if skipped:
        result["skipped"] = skipped
    if not chosen:
        return result
    operations = [operation for proposal in chosen for operation in proposal["batch"]]
    trial = project.clone()
    trial.apply(operations, detail="compact")
    difference = found.difference(trial)
    if difference > ROUNDING:
        result.setdefault("notes", []).append("Nothing was applied: together the batches would change the picture. "
                                              "Apply them one at a time and look at each")
        return result
    project.apply(operations, detail="compact")
    names = [proposal.get("group") or proposal["layers"][0] for proposal in chosen]
    result["applied"] = [{"object": name, "kind": proposal["proposed_kind"]} for name, proposal in zip(names, chosen)]
    result["render_unchanged"] = True
    result["render_difference"] = difference
    report = project.check(checks=["object"], targets=names)
    findings = report.get("issues", report.get("findings", []))
    result["check"] = {"passed": report.get("passed"), "count": len(findings),
                       "findings": [{key: finding[key] for key in ("code", "severity", "message") if key in finding}
                                    for finding in findings[:20]]}
    return result
