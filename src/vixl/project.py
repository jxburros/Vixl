"""Portable project storage, atomic operation batches and a persistent history DAG."""

from collections import OrderedDict
from copy import copy, deepcopy
import difflib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import zipfile

from . import __version__, calls
from .assets import decode, read_bounded
from .errors import VixlError, require
from .history import diff, patch
from .model import Limits, new_state, uid
from .render import LayerCache

# Every Nth revision on a chain stores a full snapshot; the others store a delta from the parent.
SNAPSHOT_INTERVAL = 32
FORMAT_VERSION = 2
DECODED_BUDGET = 256 * 1024 * 1024
NODE_KEYS = {"id", "parent", "operations", "label", "state", "delta", "squashed"}
ASSET_REFERENCE = re.compile(rb"(?:assets|masks|fonts|sources)/[0-9a-f]{64}\.[a-z0-9]{2,5}")


def upgrade_state(state):
    """Bring a state saved by an earlier Vixl up to date in place (and return it): a layer's
    ``lookup`` field becomes a ``lookup`` entry at the end of its effect stack, where it rendered."""
    for layer in state.get("layers", []):
        old = layer.pop("lookup", None)
        if old:
            layer.setdefault("effects", []).append({
                "id": f"fx_lut_{layer['id']}", "name": "lookup", "lut": old["name"],
                "amount": old.get("amount", 1), "enabled": True, "selection": None,
            })
    return state


def swatch_user(error, operations, index):
    """For an unknown-swatch error, the first operation that uses the swatch: colors resolve when
    a later operation (or the final state check) reads them, not where the reference was written."""
    match = re.match(r"Unknown swatch: @([\w-]+)$", str(error))
    if not match or "operation_index" in error.details:
        return index
    pattern = re.compile("@" + re.escape(match[1]) + r"(?![\w-])")
    for position, operation in enumerate(operations[: len(operations) if index is None else index + 1]):
        if pattern.search(json.dumps(operation, ensure_ascii=False, default=str)):
            return position
    return index


def located(error, index, operation, count):
    """Attach which operation failed, so an agent can fix one entry of a batch."""
    if "operation_index" not in error.details:
        kind = operation.get("type", operation.get("operation")) if isinstance(operation, dict) else None
        error.details["operation_index"] = index
        error.details["operation_type"] = kind
        if count > 1:
            error.args = (f"operations[{index}] ({kind}): {error}",)
    return error


# Error codes of a malformed operation: the schema phase collects every one of them in a batch.
INVALID_CODES = ("invalid_operation", "unknown_operation", "invalid_property", "invalid_path", "invalid_color")
MAX_REPORTED = 50


def batch_error(errors):
    """One error for every invalid operation of a batch. The top-level fields describe the first
    error; ``errors`` lists each one (operation_index, field, message, suggestions ...)."""
    first = errors[0]
    if len(errors) == 1:
        return first
    keep = ("operation_index", "operation_type", "field", "suggestions")  # long field lists stay on the first error
    entries = [{"error": e.code, "message": str(e), **{k: e.details[k] for k in keep if k in e.details}}
               for e in errors[:MAX_REPORTED]]
    more = f"\n... and {len(errors) - MAX_REPORTED} more" if len(errors) > MAX_REPORTED else ""
    message = (f"{len(errors)} operations are invalid; nothing was applied. Fix them all and resend:\n"
               + "\n".join(f"- {entry['message']}" for entry in entries) + more)
    return VixlError(first.code, message, **first.details, errors=entries, error_count=len(errors))


class Project:
    # The older Vixl version that saved this document, kept across saves until the upgrade is accepted
    # (vixl upgrade); see upgrade.py.
    upgraded_from = None

    def __init__(self, width=None, height=None, background=None, *, purpose=None, seed=None, variety=None,
                 workspace_fonts=True, limits=None, workspace=None):
        """A new document.

        ``Project(width, height)`` alone is a plain transparent canvas, as before. Leaving out the size, or
        passing ``purpose``, ``seed`` or ``variety``, creates a design document exactly as ``vixl new`` and
        ``vixl_document_create`` do (``creation.py``): the purpose's size (else 1080×1080), rolled
        ``design_defaults``, the palette background (transparent for marks) and the rolled font pairing
        (``workspace_fonts=False`` skips fonts). An unseeded roll is recorded in the workspace history
        only when ``workspace`` is given."""
        designed = (width is None and height is None) or any(v is not None for v in (purpose, seed, variety))
        size, source = None, "argument"
        if designed:
            from .creation import resolve_size

            width, height, size, source = resolve_size(width, height, None, purpose)
            if size is not None:
                from .sizes import resolve

                info = resolve(size)
                width, height = info["width"], info["height"]
        require(width is not None and height is not None, "Give width and height together", field="width")
        self._init_blank(width, height, "transparent" if background is None else background, limits, workspace)
        if designed:
            from .creation import design

            if size is not None:
                self._apply_size({"type": "canvas", "size": size}, f"Create {size} document")
            design(self, size=size, size_from=source, purpose=purpose, background=background, seed=seed,
                   variety=variety, workspace=workspace, remember=workspace is not None,
                   workspace_fonts=workspace_fonts)

    def _init_blank(self, width, height, background, limits, workspace):
        self.limits = limits or Limits()
        self.limits.size(width, height)
        from .render import color

        color(background)
        self.state = new_state(width, height, background)
        self.assets = {}
        self.nodes = {}
        self.head = None
        self.branches = {}
        self.checkpoints = {}
        self.current_branch = "main"
        self.redo_stack = []
        self.transaction = None
        self.path = None
        self._workspace = str(Path(workspace or Path.cwd()).resolve())
        self.allow_linked = False
        self._revision = None
        self._cache = LayerCache()
        self._paint_cache = OrderedDict()  # Painted stroke prefixes, shared by clones (brushes.py).
        self._decoded = {}
        self._head_state = None
        self._verified = set()
        self._record([], "Create document")

    @classmethod
    def sized(cls, size, background=None, *, limits=None, dpi=None, orientation=None, bleed=False, workspace=None,
              purpose=None, seed=None, variety=None, workspace_fonts=True, design=True):
        """Create a document from a named size (``letter``, ``instagram-portrait``, ``favicon`` …),
        recording its dpi, bleed, safe area and trim/safe guides in the first revision.

        Like ``vixl new SIZE`` it rolls ``design_defaults`` and, without ``background``, uses the palette
        background (transparent for logo and icon sizes) and installs the rolled pairing. ``design=False``
        gives a plain canvas (transparent unless ``background`` is given)."""
        from .sizes import resolve

        info = resolve(size, dpi=dpi, orientation=orientation, bleed=bleed)
        blank = "transparent" if background is None or design else background
        project = cls(info["width"], info["height"], blank, limits=limits, workspace=workspace)
        op = {"type": "canvas", "size": info["size"], "orientation": orientation, "dpi": dpi, "bleed": bleed}
        project._apply_size({k: v for k, v in op.items() if v not in (None, False)}, f"Create {info['size']} document")
        if design:
            from .creation import design as finish

            finish(project, size=info["size"], purpose=purpose, background=background, seed=seed, variety=variety,
                   workspace=workspace, remember=workspace is not None, workspace_fonts=workspace_fonts)
        return project

    @classmethod
    def new(cls, size=None, *, width=None, height=None, purpose=None, background=None, dpi=None, orientation=None,
            bleed=False, seed=None, variety=None, workspace=None, workspace_fonts=True, limits=None, report=None):
        """The one creation path with every option ``vixl new`` and ``vixl_document_create`` take; ``report``
        receives what creation chose (``creation``, ``workspace_fonts``)."""
        from .creation import create

        return create(width, height, background, size=size, purpose=purpose, dpi=dpi, orientation=orientation,
                      bleed=bleed, seed=seed, variety=variety, workspace=workspace, remember=workspace is not None,
                      workspace_fonts=workspace_fonts, limits=limits, report=report)

    def _apply_size(self, op, label):
        from .operations import execute
        from .validation import check_state

        execute(self, op)
        check_state(self, self.state)
        self.nodes, self.head, self._head_state, self.branches = {}, None, None, {}
        self._verified = set()
        self._record([], label)

    def find_layer(self, target):
        """The layer whose ID or name is ``target``, or None.

        IDs and names are unique across a page's layers, so a remembered position that still holds
        a matching layer is the answer. Layers are edited in place everywhere, so the index is only
        a hint: a stale entry rebuilds it, and a name it does not know is looked up in the list."""
        layers = self.state["layers"]
        if not isinstance(target, str):
            return next((layer for layer in layers if target in (layer["id"], layer["name"])), None)
        cached = getattr(self, "_layer_index", None)
        if cached is None or cached[0] is not layers:
            cached = self._index_layers()
        position = cached[1].get(target)
        if position is None:
            position = next((i for i, layer in enumerate(layers) if target in (layer["id"], layer["name"])), None)
            if position is None:
                return None
            cached[1][target] = position
        elif position >= len(layers) or target not in (layers[position]["id"], layers[position]["name"]):
            position = self._index_layers()[1].get(target)
            if position is None:
                return None
        return layers[position]

    def _index_layers(self):
        layers, index = self.state["layers"], {}
        for position, layer in enumerate(layers):
            index.setdefault(layer["id"], position)
            index.setdefault(layer["name"], position)
        self._layer_index = (layers, index)
        return self._layer_index

    def _indexed(self, layer):
        """Record a layer just appended to the list (see ``find_layer``)."""
        cached = getattr(self, "_layer_index", None)
        layers = self.state["layers"]
        if cached is not None and cached[0] is layers and layers and layers[-1] is layer:
            cached[1].setdefault(layer["id"], len(layers) - 1)
            cached[1].setdefault(layer["name"], len(layers) - 1)

    def layer(self, target=None):
        target = target or self.state["active_layer"]
        found = self.find_layer(target)
        if found is not None:
            return found
        names = [x["name"] for x in self.state["layers"]]
        folded = [name for name in names if name.casefold() == str(target).casefold()]
        suggestions = folded or difflib.get_close_matches(str(target), names, 3, 0.5)
        message = f"Layer {target!r} does not exist" if target else "No active layer; pass target"
        if suggestions:
            message += f"; did you mean {' or '.join(map(repr, suggestions))}?"
        elif names:
            message += f". Layers: {', '.join(map(repr, names[-20:]))}"
        raise VixlError(
            "layer_not_found",
            message,
            field="target",
            requested=target,
            suggestions=suggestions,
            available=names[-50:],
        )

    def image(self, asset, mode="RGBA", size_hint=None):
        """Decode an embedded asset through a small byte-bounded LRU shared by edit candidates."""
        require(asset in self.assets, f"Missing embedded asset: {asset}", "missing_asset")
        key = (asset, mode, tuple(size_hint) if size_hint else None)
        cache = self._decoded
        if key in cache:
            cache[key] = cache.pop(key)
            return cache[key].copy()
        image = decode(self.assets[asset], self.limits, mode, size_hint)
        size = image.width * image.height * len(image.getbands())
        if size <= DECODED_BUDGET // 2:
            while (
                cache
                and sum(i.width * i.height * len(i.getbands()) for i in cache.values()) + size
                > DECODED_BUDGET
            ):
                cache.pop(next(iter(cache)))
            cache[key] = image.copy()
        return image

    def clone(self):
        """Copy-on-write candidate. History nodes are immutable once recorded, so they are shared
        instead of deep-copied on every edit; the render cache is content-addressed and shared."""
        clone = copy(self)
        clone.state = deepcopy(self.state)
        clone.assets = dict(self.assets)
        clone.nodes = dict(self.nodes)
        clone.branches = dict(self.branches)
        clone.checkpoints = dict(self.checkpoints)
        clone.redo_stack = list(self.redo_stack)
        clone.transaction = deepcopy(self.transaction)
        clone._verified = set(self._verified)
        return clone

    def spatial(self, **options):
        """Measure relationships, hit tests, guides, grids and free space in canvas coordinates."""
        from .spatial import query

        return query(self, **options)

    def inspect(self, target=None):
        from .render import child_index, extent, resolve_layout, resolved_layers

        state = {key: deepcopy(value) for key, value in self.state.items() if key not in ("pages", "masters")}
        if self.state.get("pages"):
            from .pages import summary

            info = summary(self)
            state["pages"], state["masters"] = info["pages"], info["masters"]
        layers = resolved_layers(self)
        resolved = resolve_layout(self, layers=layers)
        from .spatial import canvas_boxes

        content_bounds = {}
        canvas_bounds = canvas_boxes(self, content=content_bounds)
        children, memo = child_index(layers), {}
        shown = {item["id"]: item["visible"] for item in layers}
        for layer in state["layers"]:
            box = layer["resolved_bounds"] = resolved[layer["id"]]
            layer["canvas_bounds"] = canvas_bounds[layer["id"]]
            if layer["id"] in content_bounds:
                # The usable inner area of a shape (a bubble's body, a badge's centre, a device screen).
                layer["content_bounds"] = [round(v, 2) for v in content_bounds[layer["id"]]]
            layer["coordinate_space"] = "parent" if layer.get("parent") else "canvas"
            if layer["type"] == "shape" and layer.get("shape") == "path":
                from .vector_paths import inspect_nodes

                layer["path_nodes"] = inspect_nodes(layer)
            if layer["type"] == "text":
                from .text_metrics import inspect_text

                effective = next(item for item in layers if item["id"] == layer["id"])
                layer.update(inspect_text(self, effective, box))
            if layer["visible"] and not shown[layer["id"]]:
                layer["collapsed"] = True  # Hidden by hide_if_empty or an empty stack, not by the user.
            left, top, right, bottom = extent(layer, resolved, children, memo)
            left, top = math.floor(left + 1e-6), math.floor(top + 1e-6)
            drawn = (left, top, math.ceil(right - 1e-6) - left, math.ceil(bottom - 1e-6) - top)
            if drawn != tuple(box):
                # Blur, styles and group children that reach past the box still draw.
                layer["drawn_bounds"] = drawn
        if target:
            ident = self.layer(target)["id"]
            return next(x for x in state["layers"] if x["id"] == ident)
        from .forms import has_fields

        if has_fields(self):
            from .forms import summary as field_summary

            state["fields"] = field_summary(self)
        from .links import link_layers, status as link_status

        if link_layers(self.state):
            state["links"] = link_status(self)
        from .variables import listing as placeholder_listing

        placeholders = placeholder_listing(self)
        if placeholders:
            state["placeholders"] = placeholders
        return {
            **state,
            "version": __version__,
            "head": self.head,
            "branch": self.current_branch,
            "history_count": len(self.nodes),
            "transaction": self.transaction is not None,
        }

    def _delta_depth(self, ident):
        depth = 0
        while "state" not in self.nodes[ident]:
            depth += 1
            ident = self.nodes[ident]["parent"]
            require(
                ident is not None and depth <= len(self.nodes), "Invalid history chain", "invalid_project"
            )
        return depth

    def _state_at(self, ident):
        """Reconstruct a revision's state from its nearest snapshot. Returns a private copy."""
        if ident == self.head and self._head_state is not None:
            return deepcopy(self._head_state)
        chain = []
        cursor = ident
        while "state" not in self.nodes[cursor]:
            chain.append(self.nodes[cursor]["delta"])
            cursor = self.nodes[cursor]["parent"]
            require(
                cursor is not None and len(chain) <= len(self.nodes),
                "Invalid history chain",
                "invalid_project",
            )
        state = deepcopy(self.nodes[cursor]["state"])
        for delta in reversed(chain):
            state = patch(state, delta)
        return state

    def _node(self, ident, parent, operations, label, state, parent_state):
        node = {"id": ident, "parent": parent, "operations": deepcopy(operations), "label": label}
        if parent is None or parent_state is None or self._delta_depth(parent) + 1 >= SNAPSHOT_INTERVAL:
            node["state"] = deepcopy(state)
        else:
            node["delta"] = diff(parent_state, state)
        return node

    def _record(self, operations, label=None):
        if len(self.nodes) >= self.limits.max_history:
            self._prune()
        ident = uid("rev")
        self.nodes[ident] = self._node(ident, self.head, operations, label, self.state, self._head_state)
        self.head = ident
        self._head_state = deepcopy(self.state)
        self._verified.add(ident)
        if self.current_branch:
            self.branches[self.current_branch] = ident
        self.redo_stack = []

    def _amend_head(self):
        """Replace the head revision's stored state with the current state (same operations)."""
        node = self.nodes[self.head]
        parent = node["parent"]
        parent_state = self._state_at(parent) if parent else None
        self.nodes[self.head] = {
            **self._node(self.head, parent, node["operations"], node["label"], self.state, parent_state),
            **({"squashed": True} if node.get("squashed") else {}),
        }
        self._head_state = deepcopy(self.state)

    def _prune(self):
        """Squash the oldest unreferenced revisions instead of refusing further edits.

        Branch tips, checkpoints, the head and redo entries are kept. A removed revision's
        children become full snapshots attached to its parent, so later states are unchanged."""
        target = self.limits.max_history - max(1, self.limits.max_history // 10)
        protected = {self.head, *self.branches.values(), *self.checkpoints.values(), *self.redo_stack}
        children = {}
        for node in self.nodes.values():
            children.setdefault(node["parent"], []).append(node["id"])
        for ident in list(self.nodes):
            if len(self.nodes) <= target:
                break
            if ident in protected:
                continue
            node = self.nodes[ident]
            for child in children.pop(ident, []):
                state = self._state_at(child)
                replacement = {k: v for k, v in self.nodes[child].items() if k not in ("state", "delta")}
                replacement.update(parent=node["parent"], state=state, squashed=True)
                self.nodes[child] = replacement
                children.setdefault(node["parent"], []).append(child)
            siblings = children.get(node["parent"], [])
            if ident in siblings:
                siblings.remove(ident)
            del self.nodes[ident]
        require(
            len(self.nodes) < self.limits.max_history,
            "History limit reached and every revision is protected by a branch, checkpoint or redo entry",
            "resource_limit",
        )

    def apply(self, operations, *, dry_run=False, detail="full", check=None):
        require(detail in ("brief", "compact", "full"), "Unknown response detail; use brief, compact or full")
        from .operations import execute

        if isinstance(operations, dict):
            # A {"operations": [...]} wrapper; one operation may carry its own list (frames-edit).
            single = "type" in operations or "operation" in operations
            operations = [operations] if single else operations.get("operations", [operations])
        require(isinstance(operations, list) and operations, "Expected a nonempty list of operations")
        require(
            len(operations) <= self.limits.max_operations,
            f"A batch holds at most {self.limits.max_operations} operations, got {len(operations)}; split it "
            "into several apply calls",
            "resource_limit",
        )
        from .schema import validate_operation
        from .normalize import apply_centering, resolve_geometry
        from .targets import fan_out

        notes = []
        validated = []
        invalid = []  # Every schema error of the batch, so one round trip fixes them all.
        for index, operation in enumerate(operations):
            try:
                validated.append(validate_operation(operation, notes, index if len(operations) > 1 else None))
                if check:
                    check(validated[-1])
            except VixlError as exc:
                if exc.code not in INVALID_CODES:
                    raise located(exc, index, operation, len(operations)) from exc
                invalid.append(located(exc, index, operation, len(operations)))
        if invalid:
            raise batch_error(invalid)
        operations = validated
        candidate = self.clone()
        candidate._service = bool(check)
        candidate._resource_budget = self.limits.max_operations - len(operations)
        from . import notices

        notices.start(candidate)
        candidate._reports = {}  # What operations such as edit-layers and adapt-layout report back.
        candidate._name_hints = {}  # Default layer names handed out in this batch (operations.default_name).
        before = candidate.inspect()
        for index, operation in enumerate(operations):
            calls.check_cancelled()  # A cancelled batch leaves the document untouched: nothing is committed yet.
            calls.progress(index, len(operations), operation["type"])
            try:
                if "page" in operation and operation["type"] != "page":
                    from .pages import select

                    select(candidate.state, page=operation["page"])
                    operation = {k: v for k, v in operation.items() if k != "page"}
                if operation["type"] in ("layout-apply", "template-apply"):
                    from .brand import prepare
                    operation = prepare(candidate, operation)
                for single in fan_out(operation):  # targets on a per-layer operation: once per layer
                    resolved, centered = resolve_geometry(candidate, single)
                    execute(candidate, deepcopy(resolved))
                    if single["type"] in ("layout-apply", "template-apply"):
                        from .brand import finish
                        finish(candidate)
                    apply_centering(candidate, centered, single)
            except VixlError as exc:
                index = swatch_user(exc, operations, index)
                raise located(exc, index, operations[index], len(operations)) from exc
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                error = VixlError("invalid_operation", f"Malformed operation: {exc}")
                raise located(error, index, operation, len(operations)) from exc
        calls.progress(len(operations), len(operations), "checking")
        if candidate.state.get("diagrams"):
            from .diagrams import refresh as refresh_diagrams

            refresh_diagrams(candidate)
        reflowed = []
        if candidate.state.get("flows"):
            from .textflow import refresh as refresh_flows

            reflowed = refresh_flows(candidate)
        from .validation import check_state

        try:
            check_state(candidate, candidate.state)
        except VixlError as exc:
            index = swatch_user(exc, operations, None)
            if index is not None:
                raise located(exc, index, operations[index], len(operations)) from exc
            raise
        candidate.__dict__.pop("_resource_budget", None)
        candidate.__dict__.pop("_name_hints", None)
        candidate.__dict__.pop("_service", None)
        warned, interpreted = notices.finish(candidate)
        reports = candidate.__dict__.pop("_reports", {})
        after = candidate.inspect()  # Also resolves constraints, rejecting cycles atomically.
        changes = {
            key: {"before": before.get(key), "after": after.get(key)}
            for key in candidate.state
            if before.get(key) != after.get(key)
        }
        if detail in ("brief", "compact"):
            from .changes import brief_changes, compact_changes

            changes = (brief_changes if detail == "brief" else compact_changes)(before, after)
        if not dry_run:
            if candidate.transaction is not None:
                candidate.transaction["operations"].extend(deepcopy(operations))
            else:
                candidate._record(operations)
            self.__dict__.update(candidate.__dict__)
        result = {"success": True, "dry_run": dry_run, "operations": len(operations), "changes": changes}
        if any(op["type"] == "template-apply" for op in operations):
            result["template"] = deepcopy(candidate.state.get("template", {}))
        if any(op["type"].startswith("container-") for op in operations):
            result["containers"] = [{"id": layer["id"], "name": layer["name"], **deepcopy(layer["container"])}
                                    for layer in candidate.state["layers"] if "container" in layer]
        if any(op["type"] == "comic-layout" for op in operations):
            result["comic"] = deepcopy(candidate.state.get("comic", {}))
        if any(op["type"] == "layout-apply" for op in operations):
            result["layout"] = deepcopy(candidate.state.get("layout", {}))
            if detail == "brief":
                for key in ("layers", "principles"):
                    result["layout"].pop(key, None)
            result["unfilled_slots"] = list(dict.fromkeys(b["slot"] for b in result["layout"].get("blanks", [])))
            from .layouts import next_steps

            if result["unfilled_slots"]:
                result["next_steps"] = next_steps(candidate)
        if any(op["type"].startswith("diagram") for op in operations):
            from .diagrams import report as diagram_report

            result["diagram"] = diagram_report(candidate, operations)
        if candidate.state.get("flows") and (reflowed or any(op["type"] == "text-flow" for op in operations)):
            from .textflow import report as flow_report, warnings as flow_warnings

            result["text_flow"] = flow_report(candidate, operations, reflowed)
            if flow_warnings(candidate, result["text_flow"]):
                result.setdefault("warnings", []).extend(flow_warnings(candidate, result["text_flow"]))
        if any(op["type"] == "paint" for op in operations):
            from .brushes import stroke_diagnostics
            from .render import layer_image, resolve_layout
            bounds = resolve_layout(candidate)
            painted = [layer for layer in candidate.state["layers"] if layer["type"] == "paint" and layer.get("strokes")]
            result["paint"] = [{"layer": layer["name"], "strokes": stroke_diagnostics(layer),
                                "visible_pixels": layer_image(candidate, layer, bounds[layer["id"]]).getchannel("A").getbbox() is not None}
                               for layer in painted]
            if any(not item["visible_pixels"] for item in result["paint"]):
                result["warnings"] = ["Paint has no visible pixels; check --space canvas versus --space layer and resolved bounds."]
        from .advisories import advise

        warnings = [*warned, *reports.pop("warnings", []), *advise(candidate, before, after, operations)]
        if warnings:
            result["warnings"] = [*result.get("warnings", []), *warnings]
        notes = [*notes, *interpreted, *reports.pop("normalized", [])]
        result.update(reports)
        if notes:
            result["normalized"] = notes
        return result

    def undo(self, count=1):
        """Step back ``count`` revisions, or as far as the history goes; returns how many steps were undone."""
        require(self.transaction is None, "Commit or roll back the transaction first")
        require(isinstance(count, int) and not isinstance(count, bool) and count > 0, "Undo count must be a positive "
                "whole number", field="count")
        cursor = self.head
        stack = list(self.redo_stack)
        done = 0
        while done < count and self.nodes[cursor]["parent"] is not None:
            stack.append(cursor)
            cursor = self.nodes[cursor]["parent"]
            done += 1
        require(done, "Nothing more to undo", "history_boundary")
        self.redo_stack = stack
        self._restore(cursor)
        return done

    def redo(self, count=1):
        """Step forward ``count`` undone revisions, or as many as there are; returns how many were redone."""
        require(self.transaction is None, "Commit or roll back the transaction first")
        require(isinstance(count, int) and not isinstance(count, bool) and count > 0, "Redo count must be a positive "
                "whole number", field="count")
        require(self.redo_stack, "Nothing more to redo", "history_boundary")
        done = min(count, len(self.redo_stack))
        target = self.redo_stack[-done]
        del self.redo_stack[-done:]
        # Only the revision landed on is restored, so redoing many steps costs one restore, as undo does.
        self._restore(target)
        return done

    def _restore(self, node):
        # The head state stays as stored, so new deltas patch the stored revisions; the live state
        # is brought up to date.
        stored = self._state_at(node)
        state = upgrade_state(deepcopy(stored))
        if node not in self._verified:
            # Archived history is untrusted until a revision is actually used.
            from .validation import check_state

            try:
                check_state(self, state)
            except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
                raise VixlError("invalid_project", f"Malformed history revision: {exc}") from exc
            self._verified.add(node)
        self.head = node
        self.state = state
        self._head_state = stored
        if self.current_branch:
            self.branches[self.current_branch] = node

    def resolve_ref(self, ref="head"):
        """Resolve head, previous, a branch, checkpoint or revision ID, optionally with ~N."""
        require(isinstance(ref, str) and ref, "History reference must be a non-empty string", field="ref")
        if ref in ("previous", "prev", "parent"):
            ref = "head~1"
        base, _, back = ref.partition("~")
        require(not back or back.isdigit(), "Use REF~N with a whole number N", field="ref")
        node = (
            self.head
            if base in ("head", "HEAD", "current")
            else self.branches.get(base, self.checkpoints.get(base, base))
        )
        require(
            node in self.nodes,
            f"Unknown history reference {ref!r}; use head, previous, head~N, a branch, checkpoint or revision ID",
            field="ref",
            branches=sorted(self.branches),
            checkpoints=sorted(self.checkpoints),
        )
        for _ in range(int(back or 0)):
            node = self.nodes[node]["parent"]
            require(node is not None, f"History has no revision {ref!r}", "history_boundary", field="ref")
        return node

    def at(self, ref="head"):
        """A read-only view of the document at a revision, for rendering and comparison."""
        node = self.resolve_ref(ref)
        if node == self.head:
            return self
        view = copy(self)
        view.state = upgrade_state(self._state_at(node))
        if node not in self._verified:
            from .validation import check_state

            try:
                check_state(view, view.state)
            except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
                raise VixlError("invalid_project", f"Malformed history revision: {exc}") from exc
        return view

    def branch(self, name):
        require(isinstance(name, str) and 0 < len(name) <= 200, "History name must be 1–200 characters")
        require(self.transaction is None, "Commit or roll back the transaction first")
        require(
            name and name not in self.branches and name not in self.checkpoints,
            "Name already exists or is empty",
        )
        self.branches[name] = self.head
        self.current_branch = name

    def checkpoint(self, name):
        require(isinstance(name, str) and 0 < len(name) <= 200, "History name must be 1–200 characters")
        require(self.transaction is None, "Commit or roll back the transaction first")
        require(
            name and name not in self.checkpoints and name not in self.branches,
            "Name already exists or is empty",
        )
        self.checkpoints[name] = self.head

    def checkout(self, ref):
        require(isinstance(ref, str), "History reference must be a string")
        require(self.transaction is None, "Commit or roll back the transaction first")
        node = self.branches.get(ref, self.checkpoints.get(ref, ref))
        require(node in self.nodes, f"Unknown history reference: {ref}")
        self.current_branch = ref if ref in self.branches else None
        self.redo_stack = []
        self._restore(node)

    def begin(self):
        require(self.transaction is None, "Transaction already open")
        self.transaction = {"state": deepcopy(self.state), "operations": []}

    def commit(self):
        require(self.transaction is not None, "No transaction open")
        operations = self.transaction["operations"]
        self._record(operations, "Transaction")
        self.transaction = None

    def rollback(self):
        require(self.transaction is not None, "No transaction open")
        self.state = self.transaction["state"]
        self.transaction = None

    def render(self, variables=None, *, artboard=None, comp=None, page=None):
        from .render import render

        return render(self, variables, artboard, comp, page=page)

    def show(self, page=None, region=None):
        """The rendered document as a PIL image, for notebooks and scripts. ``page`` is a page number or name;
        ``region`` crops to ``[x, y, width, height]`` in document pixels."""
        image = self.render(page=page)
        if region is not None:
            require(len(region) == 4, "region is [x, y, width, height]", field="region")
            x, y, w, h = (float(v) for v in region)
            require(w > 0 and h > 0, "region needs a positive width and height", field="region")
            image = image.crop((round(x), round(y), round(x + w), round(y + h)))
        return image

    def _repr_png_(self):
        """Jupyter shows a Project as its rendered PNG."""
        import io

        buffer = io.BytesIO()
        self.render().save(buffer, "PNG")
        return buffer.getvalue()

    def export(self, path=None, **options):
        from .render import export

        return export(self, path, **options)

    def measure_spacing(self, **options):
        from .spacing import measure_spacing

        return measure_spacing(self, **options)

    def import_image(self, path=None, *, url=None, data=None, name="image", credit=None, license=None):
        """Embed an image from a file, bytes or an https URL as a new layer, recording its source
        (url, fetched_at, sha256) and optional credit and license in the layer's provenance."""
        from .image_import import import_image_from

        return import_image_from(self, path=path, url=url, data=data, name=name, credit=credit, license=license)

    def inspect_pixels(self, target=None):
        from .pixel import inspect_pixels

        return inspect_pixels(self, target)

    def inspect_animation(self):
        from .animation import inspect_animation

        return inspect_animation(self)

    def render_frame(self, name, scale=1, sampling="nearest"):
        from .animation import render_frame

        return render_frame(self, name, scale, sampling)

    def export_animation(self, path, **options):
        from .animation import export_animation

        return export_animation(self, path, **options)

    def check(self, **options):
        from .checks import check_design

        report = check_design(self, **options)
        if not options.get("checks") or "fonts" in options["checks"]:
            from .compaction import check_note

            check_note(self, report)
        return report

    def compact(self, *, fonts=True, dry_run=False):
        """Drop undo history and the embedded files the current design does not use (see
        ``compaction.compact``); returns what was dropped. Save afterwards to shrink the file."""
        from .compaction import compact

        return compact(self, fonts=fonts, dry_run=dry_run)

    def check_suite(self, suite, **options):
        from .assurance import run_suite
        return run_suite(self, suite, **options)

    def act(self, operations, *, suites=None, dry_run=False, check=None):
        """Apply and measure one candidate. Failed contracts leave the document unchanged."""
        candidate = self.clone()
        result = candidate.apply(operations, detail="compact", check=check)
        require(candidate.state.get("suites", {}) == self.state.get("suites", {}),
                "Checked actions cannot rewrite suites; edit contracts explicitly with apply")
        reports = {name: candidate.check_suite(name) for name in (suites or [])}
        accepted = all(report["passed"] for report in reports.values())
        if accepted and not dry_run:
            self.__dict__.update(candidate.__dict__)
        return {**result, "success": accepted, "dry_run": dry_run, "committed": accepted and not dry_run,
                "checks": reports, "bounds": {x["name"]: x["resolved_bounds"] for x in candidate.inspect()["layers"]}}

    def measure(self, **options):
        from .measure import measure

        return measure(self, **options)

    def export_screens(self, directory, **options):
        from .exports import export_screens

        return export_screens(self, directory, **options)

    def render_data(self, csv_path, directory, **options):
        from .exports import render_data

        return render_data(self, csv_path, directory, **options)

    def manifest(self):
        return {
            "format_version": FORMAT_VERSION,
            "vixl_version": __version__,
            **({"upgraded_from": self.upgraded_from} if self.upgraded_from else {}),
            "state": self.state,
            "nodes": self.nodes,
            "head": self.head,
            "branches": self.branches,
            "checkpoints": self.checkpoints,
            "current_branch": self.current_branch,
            "redo_stack": self.redo_stack,
            "transaction": self.transaction,
            "asset_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in self.assets.items()},
        }

    def _rebase_links(self, path):
        """Saving into another folder keeps relative link sources pointing at the same files (one history entry)."""
        from .links import link_layers, rebase

        if not self.path or not link_layers(self.state):
            return
        ops = rebase(self, path)
        if not ops:
            return
        previous = self.path
        self.path = path
        try:
            self.apply(ops)
        finally:
            self.path = previous

    def save(self, path=None):
        from .fileio import file_lock
        from .fileio import temporary

        require(path or self.path, "Provide a .vixl project path")
        path = Path(path or self.path).resolve()
        require(path.suffix == ".vixl", "Project filenames must end in .vixl")
        self._rebase_links(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(str(path)):
            if self.path == path and self._revision and path.exists():
                require(
                    self._revision == hashlib.sha256(path.read_bytes()).hexdigest(),
                    "Project changed on disk; reload before saving",
                    "write_conflict",
                )
            manifest = self.manifest()
            manifest.pop("asset_hashes")
            body = json.dumps(manifest, allow_nan=False, separators=(",", ":")).encode()
            # Drop assets no revision references any more (for example after history pruning).
            referenced = {name.decode() for name in ASSET_REFERENCE.findall(body)}
            self.assets = {k: v for k, v in self.assets.items() if k in referenced}
            manifest["asset_hashes"] = {k: hashlib.sha256(v).hexdigest() for k, v in self.assets.items()}
            encoded = json.dumps(manifest, allow_nan=False, separators=(",", ":")).encode()
            require(
                len(encoded) + sum(map(len, self.assets.values())) <= self.limits.max_project_bytes,
                "Project exceeds byte limit",
                "resource_limit",
            )
            fd, temporary_path = temporary(path.parent, like=path if path.exists() else None)
            try:
                with os.fdopen(fd, "wb") as stream:
                    with zipfile.ZipFile(stream, "w") as archive:
                        archive.writestr("project.json", encoded, zipfile.ZIP_DEFLATED)
                        # Image assets are already compressed; recompressing them on every
                        # autosave cost far more time than it saved space.
                        for name, data in sorted(self.assets.items()):
                            archive.writestr(
                                name,
                                data,
                                zipfile.ZIP_DEFLATED if name.startswith("fonts/") else zipfile.ZIP_STORED,
                            )
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, path)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)
            self.path = path
            self._revision = hashlib.sha256(path.read_bytes()).hexdigest()
        return str(path)

    @classmethod
    def load(cls, path, *, limits=None, allow_linked=False, workspace=None):
        from .validation import check_document

        limits = limits or Limits()
        path = Path(path).resolve()
        require(
            path.stat().st_size <= limits.max_project_bytes, "Project exceeds byte limit", "resource_limit"
        )
        try:
            data = read_bounded(path, limits.max_project_bytes)
            revision = hashlib.sha256(data).hexdigest()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                require(len(entries) <= 10000, "Too many archive entries", "resource_limit")
                require(
                    sum(x.file_size for x in entries) <= limits.max_project_bytes,
                    "Expanded project exceeds byte limit",
                    "resource_limit",
                )
                names = [x.filename for x in entries]
                require(len(set(names)) == len(names), "Duplicate archive members", "invalid_project")
                require("project.json" in names, "Not a Vixl document: the archive has no project.json",
                        "invalid_project")
                require(
                    all(
                        n == "project.json"
                        or (
                            len(n.split("/")) == 2
                            and n.split("/")[0] in ("assets", "masks", "fonts", "sources")
                            and n.split("/")[1] not in ("", ".", "..")
                            and "\\" not in n
                        )
                        for n in names
                    ),
                    "Unsafe or unsupported archive member",
                    "invalid_project",
                )
                metadata = json.loads(archive.read("project.json"))
                require(
                    metadata.get("format_version") in (1, FORMAT_VERSION),
                    "Unsupported project format",
                    "invalid_project",
                )
                project = cls(1, 1, limits=limits, workspace=workspace)
                for key in (
                    "state",
                    "nodes",
                    "head",
                    "branches",
                    "checkpoints",
                    "current_branch",
                    "redo_stack",
                    "transaction",
                ):
                    setattr(project, key, metadata[key])
                from .upgrade import predates_render_changes

                saved = metadata.get("vixl_version")
                project.upgraded_from = metadata.get("upgraded_from") or (
                    (saved or "unknown") if predates_render_changes(saved) else None)
                project.assets = {n: archive.read(n) for n in names if n != "project.json"}
                hashes = metadata["asset_hashes"]
                require(set(hashes) == set(project.assets), "Asset manifest mismatch", "invalid_project")
                for name, data in project.assets.items():
                    require(
                        hashlib.sha256(data).hexdigest() == hashes[name],
                        "Asset checksum mismatch",
                        "invalid_project",
                    )
                    if name.startswith("sources/"):
                        require(name.endswith(".svg") and len(data) <= min(limits.max_asset_bytes, 4 * 1024 * 1024),
                                "Invalid embedded SVG source", "invalid_project")
                        # Inert provenance only: never render or execute source while opening an archive.
                    elif name.startswith("fonts/"):
                        from PIL import ImageFont

                        ImageFont.truetype(io.BytesIO(data), 12)
                    elif name.startswith("assets/") and name.endswith(".wav"):
                        from .audio import read_audio

                        read_audio(data)
                    else:
                        decode(data, limits)
                project.allow_linked = allow_linked
                project.path = path
                project._head_state = None
                project._verified = set()
                upgrade_state(project.state)
                check_document(project)
                project._revision = revision
                return project
        except KeyError as exc:
            raise VixlError("invalid_project", f"Malformed Vixl archive: a record is missing its {exc.args[0]!r} "
                            "field") from exc
        except zipfile.BadZipFile as exc:
            raise VixlError("invalid_project", "Not a Vixl document: the file is not a ZIP archive") from exc
        except (TypeError, ValueError, RecursionError) as exc:
            raise VixlError("invalid_project", f"Malformed Vixl archive: {exc}") from exc
