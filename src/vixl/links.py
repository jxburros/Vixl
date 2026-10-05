"""Linked documents: a layer that shows another .vixl document, live.

A ``link`` layer stores a path to a ``.vixl`` file instead of pixels. At every render the source is
opened (cached by the file's content hash), the chosen page or artboard is drawn with the link's
variables, and the result is placed in the layer's box like an image layer: ``fit`` (``fill`` crops,
``fit`` letterboxes, ``stretch`` distorts), ``position`` (where the content sits when it does not
fill the box) and ``crop`` (a region of the source, in source pixels), then the layer's rotation,
flips, effects, mask and opacity. Edit the source and every link shows the change at its next
render. PDF and PPTX/SVG keep the artwork vector where they can: a plain link in a PDF draws the
source's shapes and real text, not a picture.

``link-refresh`` records the revision of each source you have seen, so ``links`` can report a link
as ``stale`` (the source changed since) or ``missing``; ``link-embed`` freezes a link into an
ordinary image layer.

Links are opt-in and confined. A relative source resolves against the workspace (the service's
workspace, or the CLI's folder), then the document's own folder. A source outside both needs
``--allow-linked`` (CLI/Python only: services never allow it, so REST and MCP links stay inside the
workspace). A chain of links is limited to ``MAX_DEPTH`` levels, and a link back to a document that
is being drawn is an error that names the chain.
"""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import threading

from .errors import VixlError, require
from .model import finite, new_layer

TYPES = ("link", "link-set", "link-refresh", "link-embed")
ACTIONS = {"links": (set(), set())}
FITS = ("fill", "fit", "stretch")
MAX_DEPTH = 4
MAX_SOURCE_PATH = 500
MAX_RENDER_SCALE = 8
ANCHORS = {
    "top-left": [0, 0], "top": [0.5, 0], "top-right": [1, 0],
    "left": [0, 0.5], "center": [0.5, 0.5], "right": [1, 0.5],
    "bottom-left": [0, 1], "bottom": [0.5, 1], "bottom-right": [1, 1],
}
OK, STALE, MISSING, ERROR, CYCLE, FORBIDDEN = "ok", "stale", "missing", "error", "cycle", "forbidden"
BROKEN = (MISSING, ERROR, CYCLE, FORBIDDEN)

_LOCK = threading.RLock()
_SOURCES = OrderedDict()  # (path, allow_linked) -> (stamp, revision, Project)
_RENDERS = []  # one LayerCache of drawn sources, created on first use (render.py imports this module lazily)
_CHAIN = ContextVar("vixl_link_chain", default=())


# ---------------------------------------------------------------------------------------------
# Operations


def schemas(add):
    from .schema import N, S, SIZE, COORD, enum

    position = {"type": ["array", "string"], "items": N, "description": "Where content that does not fill the box sits: "
                "[x, y] fractions (0 = left/top, 1 = right/bottom) or an anchor such as 'top-left'."}
    crop = {"type": "object", "description": "A region of the source, in the source's pixels.",
            "properties": {"x": N, "y": N, "width": {"type": "number", "exclusiveMinimum": 0},
                           "height": {"type": "number", "exclusiveMinimum": 0}},
            "required": ["x", "y", "width", "height"], "additionalProperties": False}
    settings = {
        "fit": enum(*FITS),
        "position": position,
        "crop": crop,
        "artboard": S,
        "source_page": {"type": ["string", "integer"], "description": "The source's page (a name or number); "
                        "'page' on an operation names the page of this document that it edits."},
        "variables": {"type": "object", "description": "Overrides for the source's variables; a ${name} in a value "
                      "reads this document's variable."},
    }
    add("link", {"name": S, "source": S, "x": COORD, "y": COORD, "width": SIZE, "height": SIZE, **settings}, ["source"])
    nullable = {key: {**value, "type": [*(value["type"] if isinstance(value["type"], list) else [value["type"]]), "null"]}
                for key, value in settings.items() if key in ("crop", "artboard", "source_page", "variables")}
    add("link-set", {"source": S, **settings, **nullable})
    add("link-refresh")
    add("link-embed")


def execute(project, op):
    kind = op["type"]
    if kind == "link":
        return _add(project, op)
    if kind == "link-refresh":
        return _refresh(project, op)
    layer = project.layer(op.get("target"))
    require(layer["type"] == "link", f"{layer['name']!r} is not a linked document layer", field="target")
    if kind == "link-embed":
        return _embed(project, layer)
    return _set(project, layer, op)


def _add(project, op):
    from .operations import append_layer, default_name

    path = locate(project, op["source"])
    settings = _settings(op)
    child, revision = open_source(project, path, op["source"])
    size = _canvas_size(child, settings.get("source_page"), settings.get("artboard"), op["source"])
    check_cycle(project, path, op["source"])
    region = settings.get("crop") or [0, 0, *size]
    _crop_within(region, size, op["source"])
    rw, rh = region[2] - region[0], region[3] - region[1]
    width, height = op.get("width"), op.get("height")
    if width is None and height is None:
        width, height = max(1, round(rw)), max(1, round(rh))
    elif width is None:
        width = max(1, round(height * rw / rh))
    elif height is None:
        height = max(1, round(width * rh / rw))
    name = op["name"] if "name" in op else default_name(project, Path(op["source"]).stem)
    layer = new_layer(name, "link", width, height, source=stored_source(project, path), fit=op.get("fit", "fill"),
                      **settings)
    layer.update(source_hash=revision, source_size=list(size))
    layer["x"], layer["y"] = finite(op.get("x", 0), "x"), finite(op.get("y", 0), "y")
    append_layer(project, layer)


def _set(project, layer, op):
    settings = _settings(op, nullable=True)
    require(settings or "source" in op or "fit" in op, "link-set needs something to change: source, artboard, "
            "source_page, variables, fit, position or crop", field="source")
    if "source" in op:
        layer["source"] = stored_source(project, locate(project, op["source"]))
    for key, value in settings.items():
        if value is None:
            layer.pop(key, None)
        else:
            layer[key] = value
    if "fit" in op:
        layer["fit"] = op["fit"]
    # A new source is a new link: record it. Other changes only have to still fit the source.
    _record(project, layer, accept="source" in op)


def _refresh(project, op):
    if op.get("target"):
        layer = project.layer(op["target"])
        require(layer["type"] == "link", f"{layer['name']!r} is not a linked document layer", field="target")
        layers = [layer]
    else:
        layers = [item for item in project.state["layers"] if item["type"] == "link"]
        require(layers, "This document has no linked document layers to refresh")
    for layer in layers:
        _record(project, layer)


def _record(project, layer, accept=True):
    """Check that a link still fits its source (it exists, has the page and artboard, holds the crop and
    does not lead back here) and, when ``accept``, record the revision and canvas size it was seen at."""
    path = locate(project, layer["source"])
    child, revision = open_source(project, path, layer["source"])
    size = _canvas_size(child, layer.get("source_page"), layer.get("artboard"), layer["source"])
    if layer.get("crop"):
        _crop_within(layer["crop"], size, layer["source"])
    check_cycle(project, path, layer["source"])
    if accept:
        layer.update(source_hash=revision, source_size=list(size))


def _embed(project, layer):
    from .assets import add_image
    from .render import ink_origin, layer_ink, resolve_layout

    require(not layer.get("styles") and not layer.get("clip"), "Remove layer styles/clipping before embedding a link")
    bounds = resolve_layout(project)[layer["id"]]
    # Everything the link draws: its fit and crop, rotation, effects, mask and opacity, at the layer's size.
    image = layer_ink(project, layer, bounds)
    x, y = ink_origin(image, bounds)
    provenance = {"type": "linked-document", **{key: deepcopy(layer[key]) for key in
                                                ("source", "source_hash", "artboard", "source_page", "variables") if key in layer}}
    layer.update(type="raster", asset=add_image(project, image), width=image.width, height=image.height, x=x, y=y,
                 rotation=0, flip_x=False, flip_y=False, effects=[], mask=None, opacity=1, constraints={},
                 provenance=provenance)
    for key in ("source", "source_hash", "source_size", "artboard", "source_page", "variables", "fit", "position", "crop"):
        layer.pop(key, None)


def _settings(op, nullable=False):
    """The validated page, artboard, variables, position and crop of a link operation. ``None`` (when
    ``nullable``) clears a setting."""
    settings = {}
    for key in ("artboard", "source_page", "variables", "position", "crop"):
        if key not in op:
            continue
        value = op[key]
        if value is None:
            require(nullable, f"{key} cannot be null when linking a document", field=key)
            settings[key] = None
            continue
        if key == "artboard":
            require(isinstance(value, str) and 0 < len(value) <= 200, "artboard must be a name", field=key)
        elif key == "source_page":
            require(isinstance(value, (str, int)) and not isinstance(value, bool),
                    "source_page must be a name or number", field=key)
        elif key == "variables":
            value = _variables(value)
        elif key == "position":
            value = _position(value)
        else:
            value = _crop(value)
        settings[key] = value
    return settings


def _variables(value):
    require(isinstance(value, dict) and len(value) <= 256, "variables maps up to 256 names to values", field="variables")
    for key, item in value.items():
        require(isinstance(key, str) and re.fullmatch(r"[\w-]+", key), f"Invalid variable name {key!r}", field="variables")
        require(isinstance(item, (str, int, float, bool)) and not (isinstance(item, str) and len(item) > 10000),
                f"Variable {key!r} must be a short string, number or boolean", field="variables")
        if isinstance(item, float):
            finite(item, key)
    return deepcopy(value)


def _position(value):
    if isinstance(value, str):
        require(value in ANCHORS, f"Unknown position {value!r}; use {', '.join(ANCHORS)} or [x, y] fractions", field="position")
        return list(ANCHORS[value])
    require(isinstance(value, list) and len(value) == 2, "position is [x, y] fractions or an anchor", field="position")
    return [finite(v, "position", 0, 1) for v in value]


def _crop(value):
    require(isinstance(value, dict) and set(value) == {"x", "y", "width", "height"},
            "crop is {x, y, width, height} in source pixels", field="crop")
    x, y = finite(value["x"], "crop x", 0), finite(value["y"], "crop y", 0)
    width, height = finite(value["width"], "crop width", 1e-6), finite(value["height"], "crop height", 1e-6)
    # Whole pixels stay integers; a fractional crop (an imposed sheet maps trim boxes exactly) is kept.
    return [int(v) if float(v).is_integer() else round(v, 6) for v in (x, y, x + width, y + height)]


def _crop_within(region, size, source):
    require(0 <= region[0] < region[2] <= size[0] and 0 <= region[1] < region[3] <= size[1],
            f"The crop exceeds the {size[0]}×{size[1]} canvas of {source!r}", field="crop")


def validate(layer, state):
    """Structure of a stored link layer (document load and every edit)."""
    source = layer.get("source")
    require(isinstance(source, str) and 0 < len(source) <= MAX_SOURCE_PATH, "Invalid link source", "invalid_project")
    require(layer.get("fit", "fill") in FITS, "Invalid link fit", "invalid_project")
    if "position" in layer:
        position = layer["position"]
        require(isinstance(position, list) and len(position) == 2, "Invalid link position", "invalid_project")
        for value in position:
            finite(value, "link position", 0, 1)
    if "crop" in layer:
        crop = layer["crop"]
        require(isinstance(crop, list) and len(crop) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                                  for v in crop), "Invalid link crop", "invalid_project")
        for value in crop:
            finite(value, "link crop", 0, 1e7)
        require(crop[2] > crop[0] and crop[3] > crop[1], "Invalid link crop", "invalid_project")
    if "variables" in layer:
        _variables(layer["variables"])
    if "artboard" in layer:
        require(isinstance(layer["artboard"], str), "Invalid link artboard", "invalid_project")
    if "source_page" in layer:
        require(isinstance(layer["source_page"], (str, int)) and not isinstance(layer["source_page"], bool),
                "Invalid link source page", "invalid_project")
    if "source_hash" in layer:
        require(isinstance(layer["source_hash"], str) and re.fullmatch(r"[0-9a-f]{64}", layer["source_hash"]),
                "Invalid link source hash", "invalid_project")
    if "source_size" in layer:
        size = layer["source_size"]
        require(isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size),
                "Invalid link source size", "invalid_project")


# ---------------------------------------------------------------------------------------------
# Finding and opening sources


def bases(project):
    """Folders a relative source resolves against, in order: the workspace, then the document's folder."""
    found = []
    workspace = getattr(project, "_workspace", None)
    if workspace:
        found.append(Path(workspace).resolve())
    if getattr(project, "path", None):
        found.append(Path(project.path).resolve().parent)
    return list(dict.fromkeys(found)) or [Path.cwd().resolve()]


def locate(project, source, suffix=".vixl"):
    """The absolute path of a linked file, which must lie in the workspace (or next to the document)
    unless the project allows linked files (CLI/Python ``allow_linked``; never true for services)."""
    require(isinstance(source, str) and source.strip() and len(source) <= MAX_SOURCE_PATH and "\0" not in source,
            "A link needs a source path", field="source")
    require(not suffix or source.lower().endswith(suffix), f"Linked sources are {suffix} documents; got {source!r}",
            field="source")
    roots = bases(project)
    given = Path(source)
    candidates = [given.resolve()] if given.is_absolute() else [(root / given).resolve() for root in roots]
    path = next((item for item in candidates if item.exists()), candidates[0])
    inside = any(path.is_relative_to(root) for root in roots)
    require(inside or getattr(project, "allow_linked", False),
            f"Linked file {source!r} is outside the workspace; keep linked files inside it (the CLI can opt in to "
            "outside files with --allow-linked)", "forbidden", field="source")
    return path


def stored_source(project, path):
    """A workspace-relative POSIX path when the file is inside a base folder, else the absolute path."""
    for root in bases(project):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


def open_source(project, path, source):
    """``(Project, revision)`` of a linked document: the revision is the SHA-256 of the exact bytes that
    were parsed. The loaded document is cached until the file changes."""
    from .project import Project

    try:
        stat = path.stat()
    except OSError as exc:
        raise VixlError("link_missing", f"Linked document not found: {source} (looked for {path})", source=source,
                        path=str(path)) from exc
    require(path.is_file(), f"Linked document {source!r} is not a file: {path}", "link_missing", source=source)
    stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    key = (str(path), bool(getattr(project, "allow_linked", False)))
    with _LOCK:
        hit = _SOURCES.get(key)
        if hit and hit[0] == stamp:
            _SOURCES.move_to_end(key)
            return hit[2], hit[1]
    try:
        child = Project.load(path, limits=project.limits, allow_linked=getattr(project, "allow_linked", False))
    except VixlError as exc:
        raise VixlError("link_invalid", f"Linked document {source!r} cannot be opened: {exc}", source=source,
                        path=str(path)) from exc
    child._workspace = getattr(project, "_workspace", None)
    revision = child._revision
    with _LOCK:
        _SOURCES[key] = (stamp, revision, child)
        while len(_SOURCES) > 8:
            _SOURCES.popitem(last=False)
    return child, revision


def _canvas_size(child, page, artboard, source):
    """(width, height) of a source's chosen page and artboard, checking that they exist."""
    from .pages import active_page, find_page, page_content

    state = child.state
    boards = state.get("artboards", {})
    if state.get("pages"):
        try:
            record = find_page(state, page) if page is not None else (active_page(state) or state["pages"][0])
        except VixlError as exc:
            raise VixlError("link_invalid", f"Linked document {source!r}: {exc}", source=source, field="source_page") from exc
        boards = page_content(child, record).get("artboards", {})
    else:
        require(page is None, f"Linked document {source!r} has no pages, so a link cannot choose page {page!r}",
                "link_invalid", source=source, field="source_page")
    if artboard is not None:
        require(artboard in boards, f"Linked document {source!r} has no artboard {artboard!r}"
                + (f"; artboards: {', '.join(sorted(boards))}" if boards else ""), "link_invalid", source=source,
                field="artboard")
        return boards[artboard]["width"], boards[artboard]["height"]
    return state["canvas"]["width"], state["canvas"]["height"]


# ---------------------------------------------------------------------------------------------
# Cycles


def link_layers(state):
    """[(page or master name or None, layer)] for every link layer: the active content and the content
    of inactive pages and masters."""
    from .pages import active_page, MASTER_PREFIX

    active = active_page(state)
    found = [(active["name"] if active else None, layer) for layer in state.get("layers", []) if layer["type"] == "link"]
    for page in state.get("pages") or []:
        found += [(page["name"], layer) for layer in (page.get("content") or {}).get("layers", [])
                  if layer["type"] == "link"]
    for name, master in (state.get("masters") or {}).items():
        found += [(MASTER_PREFIX + name, layer) for layer in (master.get("content") or {}).get("layers", [])
                  if layer["type"] == "link"]
    return found


def check_cycle(project, path, source):
    """Reject a link that would lead back to this document, directly or through other links, or that
    nests too deeply."""
    here = Path(project.path).resolve() if getattr(project, "path", None) else None
    require(here is None or path != here, "A document cannot link to itself", "link_cycle", source=source)
    _check_chain(project, path, source, (here,))


def _check_chain(project, path, source, chain):
    """Raise ``link_cycle`` when ``path`` or anything it links to (through nested links) is already in
    ``chain``, and ``link_depth`` when the nesting passes ``MAX_DEPTH``. The check is static, so it
    does not depend on what happens to be cached."""

    def fail(code, message, stack):
        names = " → ".join(item.name for item in stack if item)
        raise VixlError(code, message.format(names=names), source=source, chain=[str(item) for item in stack if item])

    def walk(host, stack):
        if len(stack) - 1 > MAX_DEPTH:
            fail("link_depth", f"Linked documents nest more than {MAX_DEPTH} levels deep: {{names}}", stack)
        try:
            child, _ = open_source(host, stack[-1], source)
        except VixlError:
            return  # a missing or unreadable source is reported when it is drawn
        for _, layer in link_layers(child.state):
            try:
                target = locate(child, layer["source"])
            except VixlError:
                continue
            if target in stack:
                fail("link_cycle", "Linked documents form a cycle: {names}", (*stack, target))
            walk(child, (*stack, target))

    if path in chain:
        fail("link_cycle", "Linked documents form a cycle: {names}", (*chain, path))
    walk(project, (*chain, path))


@contextmanager
def entering(project, path, source):
    """Track the documents being drawn (the chain of links from the document being rendered)."""
    chain = _CHAIN.get()
    if not chain:
        chain = (Path(project.path).resolve() if getattr(project, "path", None) else None,)
    _check_chain(project, path, source, chain)
    token = _CHAIN.set((*chain, path))
    try:
        yield
    finally:
        _CHAIN.reset(token)


# ---------------------------------------------------------------------------------------------
# Rendering


class Prepared:
    """A link's source ready to draw: its page, artboard and variables applied."""

    def __init__(self, path, revision, view, size, key):
        self.path, self.revision, self.view, self.size, self.key = path, revision, view, size, key


def overrides(project, layer):
    """The link's variables with ``${name}`` references to this document's variables filled in."""
    from .render import document_variables, substitute

    values = layer.get("variables") or {}
    if not values:
        return {}
    known = document_variables(project)
    return {name: substitute(value, known) if isinstance(value, str) else value for name, value in values.items()}


def state_layers(state):
    """Every layer of a document state: the active content and inactive pages' and masters'."""
    yield from state.get("layers", [])
    for page in state.get("pages") or []:
        yield from (page.get("content") or {}).get("layers", [])
    for master in (state.get("masters") or {}).values():
        yield from (master.get("content") or {}).get("layers", [])


def _image_variables(project, view, values, source):
    """Values for image variables name an image file in the workspace; embed them in the private copy of
    the source and return (name, file stamp) pairs for the cache key."""
    from .assets import add_encoded, read_bounded

    stamps = []
    names = {item["asset_variable"] for item in state_layers(view.state) if item.get("asset_variable")}
    for name in sorted(names & values.keys()):
        value = values[name]
        if not isinstance(value, str) or value in view.assets:
            continue
        path = locate(project, value, suffix="")
        if not path.is_file():
            raise VixlError("not_found", f"Image for variable {name!r} not found: {value} (linked from {source})",
                            field=name, path=str(path))
        stat = path.stat()
        values[name], _ = add_encoded(view, read_bounded(path, view.limits.max_asset_bytes))
        stamps.append((name, value, stat.st_size, stat.st_mtime_ns))
    return stamps


def prepare(project, layer):
    """Open a link's source and return it as a :class:`Prepared` view (a private copy, so rendering never
    touches the cached document)."""
    from .design_render import artboard_project
    from .render import view_page

    source = layer["source"]
    path = locate(project, source)
    child, revision = open_source(project, path, source)
    size = _canvas_size(child, layer.get("source_page"), layer.get("artboard"), source)
    values = overrides(project, layer)
    view = child.clone()
    view._workspace = getattr(project, "_workspace", None)
    view.allow_linked = getattr(project, "allow_linked", False)
    stamps = _image_variables(project, view, values, source)
    candidate = artboard_project(view_page(view, layer.get("source_page")), layer.get("artboard"), None, values or None)
    project.limits.size(*size)
    # Nested links change what a source draws without changing its own file: they are part of the key.
    key = (revision, tuple(fingerprint(child)), layer.get("source_page"), layer.get("artboard"),
           json.dumps(values, sort_keys=True), tuple(stamps))
    return Prepared(path, revision, candidate, size, key)


def placement(layer, size):
    """How the linked region lands in the layer's box: ``(dest, source box, scale)``. ``dest`` is the
    (x, y, width, height) the content fills in the box, the box is the part of the source to draw, in
    source pixels, and the scale is the source-to-layer pixel ratio."""
    sw, sh = size
    left, top, right, bottom = layer.get("crop") or (0, 0, sw, sh)
    left, top = min(max(0, left), sw - 1), min(max(0, top), sh - 1)
    right, bottom = max(left + 1, min(sw, right)), max(top + 1, min(sh, bottom))
    rw, rh = right - left, bottom - top
    w, h = layer["width"], layer["height"]
    px, py = layer.get("position") or (0.5, 0.5)
    fit = layer.get("fit", "fill")
    if fit == "stretch":
        return (0, 0, w, h), (left, top, right, bottom), max(w / rw, h / rh)
    if fit == "fit":
        scale = min(w / rw, h / rh)
        dw, dh = max(1, round(rw * scale)), max(1, round(rh * scale))
        return (round((w - dw) * px), round((h - dh) * py), dw, dh), (left, top, right, bottom), scale
    scale = max(w / rw, h / rh)
    visible_w, visible_h = w / scale, h / scale
    x0, y0 = left + (rw - visible_w) * px, top + (rh - visible_h) * py
    return (0, 0, w, h), (x0, y0, x0 + visible_w, y0 + visible_h), scale


def link_image(project, layer):
    """The linked document drawn into the layer's box (before the layer's own transform)."""
    from PIL import Image

    prepared = prepare(project, layer)
    dest, box, scale = placement(layer, prepared.size)
    with entering(project, prepared.path, layer["source"]):
        image = _rendered(project, prepared, scale)
    sx, sy = image.width / prepared.size[0], image.height / prepared.size[1]
    region = (max(0.0, box[0] * sx), max(0.0, box[1] * sy), min(float(image.width), box[2] * sx),
              min(float(image.height), box[3] * sy))
    x, y, width, height = dest
    if region[2] - region[0] < 1e-3 or region[3] - region[1] < 1e-3:
        region = (0.0, 0.0, float(image.width), float(image.height))
    part = image.resize((width, height), Image.Resampling.LANCZOS, box=region)
    out = Image.new("RGBA", (layer["width"], layer["height"]))
    out.alpha_composite(part, (x, y))
    return out


def _rendered(project, prepared, scale):
    """The source drawn at ``scale`` (re-rendered, so text and shapes stay crisp), cached by revision."""
    from .proxy import scaled_project
    from .render import LayerCache, render

    if not _RENDERS:
        _RENDERS.append(LayerCache(entries=24, budget=256 * 1024 * 1024))
    cache = _RENDERS[0]
    width, height = prepared.size
    scale = min(scale, MAX_RENDER_SCALE, math.sqrt(project.limits.max_pixels / (width * height)))
    scale = 1.0 if abs(scale - 1) < 0.01 else round(scale, 4)
    key = (*prepared.key, scale)
    with _LOCK:
        cached = cache.image(key)
    if cached is not None:
        return cached
    image = None
    if scale != 1:
        proxy = scaled_project(prepared.view, scale)
        if proxy is not None:
            image = render(proxy)
    if image is None:
        image = render(prepared.view)
    with _LOCK:
        cache.put(key, image)
    return image




def pdf_link(builder, layer, bounds, matrix):
    """Draw a link into a PDF page as vector artwork. Returns ``None`` when drawn, or the reason the
    link has to be an image instead (opacity, or a source with layers that depend on their backdrop)."""
    from .pdf_export import PageBuilder, _fmt, affine, layer_matrix, matrix_ops
    from .render import color, resolve_layout, resolved_layers
    from .design import resolve_color
    import numpy as np

    if layer["opacity"] != 1:
        return "linked document with opacity"
    prepared = prepare(builder.view, layer)
    view = prepared.view
    layers = resolved_layers(view)
    if any(item["visible"] and (item["type"] == "adjustment" or item.get("blend", "normal") != "normal") for item in layers):
        return "linked document with blend modes or adjustment layers"
    (dx, dy, dw, dh), (left, top, right, bottom), scale = placement(layer, prepared.size)
    fit = layer.get("fit", "fill")
    w, h = layer["width"], layer["height"]
    if fit == "stretch":
        sx, sy = w / (right - left), h / (bottom - top)
    else:
        sx = sy = scale
    # Source pixels → layer pixels, then clip to the area the content covers.
    content = affine(sx, 0, 0, sy, dx - left * sx, dy - top * sy)
    bounds_in_view = resolve_layout(view, layers=layers)
    sub = PageBuilder(builder.document, view, builder.writer, builder.fonts, builder.images)
    sub.ops, sub.xobjects, sub.states, sub.shadings = builder.ops, builder.xobjects, builder.states, builder.shadings
    sub.fallbacks = builder.fallbacks
    for name in ("k", "ky", "fillable"):
        if hasattr(builder, name):
            setattr(sub, name, getattr(builder, name))
    first = len(builder.fallbacks)
    with entering(builder.view, prepared.path, layer["source"]):
        builder.ops += ["q", matrix_ops(matrix @ layer_matrix(layer, bounds)),
                        f"{_fmt(dx)} {_fmt(dy)} {_fmt(dw)} {_fmt(dh)} re W n", matrix_ops(content)]
        canvas = view.state["canvas"]
        background = color(resolve_color(canvas["background"], view.state))
        sub.fill_ops([f"0 0 {_fmt(canvas['width'])} {_fmt(canvas['height'])} re"], background, 1)
        sub.draw(layers, bounds_in_view, None, np.eye(3))
        builder.ops.append("Q")
    for entry in builder.fallbacks[first:]:
        entry["layer"] = f"{layer['name']}/{entry['layer']}"
    return None


# ---------------------------------------------------------------------------------------------
# Status


def status(project):
    """One record per link layer: its source, ``state`` (ok, stale, missing, error, cycle or forbidden) and
    what is wrong. ``stale`` means the source changed since ``link-refresh`` last recorded it; the layer
    still draws the current source."""
    items = []
    for where, layer in link_layers(project.state):
        item = {"layer": layer["name"], "id": layer["id"], "source": layer["source"], "state": OK,
                **({"on_page": where} if where else {})}
        try:
            path = locate(project, layer["source"])
            item["path"] = str(path)
            child, revision = open_source(project, path, layer["source"])
            size = _canvas_size(child, layer.get("source_page"), layer.get("artboard"), layer["source"])
            item.update(revision=revision[:12], size=list(size))
            recorded = layer.get("source_hash")
            if recorded:
                item["recorded"] = recorded[:12]
            if layer.get("source_size"):
                item["recorded_size"] = layer["source_size"]
            check_cycle(project, path, layer["source"])
            if recorded and recorded != revision:
                item.update(state=STALE, message=f"{layer['source']} changed since it was last refreshed; the layer "
                            "draws the current version (link-refresh records it)")
            if layer.get("source_size") and list(size) != layer["source_size"]:
                item["size_changed"] = True
        except VixlError as exc:
            item.update(state={"link_missing": MISSING, "link_cycle": CYCLE, "forbidden": FORBIDDEN}.get(exc.code, ERROR),
                        message=str(exc))
        items.append(item)
    return items


def report(project):
    items = status(project)
    counts = {state: sum(1 for item in items if item["state"] == state) for state in (OK, STALE, *BROKEN)}
    return {"links": items, **{key: value for key, value in counts.items() if value}, "count": len(items)}


def broken_links(project, ids):
    """{layer id: message} for the links among ``ids`` whose source cannot be drawn."""
    if not ids:
        return {}
    return {item["id"]: item["message"] for item in status(project) if item["state"] in BROKEN and item["id"] in ids}


def check_links(project, layers, issue):
    """``check_design``'s ``links`` check: broken links are errors, changed sources are warnings."""
    wanted = {item["id"]: item for item in layers if item["type"] == "link"}
    for item in status(project):
        layer = wanted.get(item["id"])
        if layer is None:
            continue
        if item["state"] in BROKEN:
            issue("links", "error", f"{layer['name']!r} links to {item['source']!r}, which cannot be drawn: "
                  f"{item['message']}", [layer], source=item["source"])
        elif item["state"] == STALE:
            issue("links", "warning", f"{layer['name']!r}: {item['message']}", [layer], source=item["source"])
        if item.get("size_changed"):
            issue("links", "warning", f"{layer['name']!r}: {item['source']!r} is now {item['size'][0]}×{item['size'][1]}, "
                  f"was {item['recorded_size'][0]}×{item['recorded_size'][1]}; check how it fits", [layer],
                  source=item["source"])


def fingerprint(project):
    """[(source, revision)] of every document the project links to, through nested links: for caches and
    manifests that must notice a changed source."""
    found = {}

    def walk(host, depth):
        for _, layer in link_layers(host.state):
            try:
                path = locate(host, layer["source"])
                child, revision = open_source(host, path, layer["source"])
            except VixlError:
                found.setdefault(layer["source"], None)
                continue
            name = stored_source(host, path)
            if name in found or depth >= MAX_DEPTH:
                continue
            found[name] = revision
            walk(child, depth + 1)

    walk(project, 0)
    return sorted(found.items())


# ---------------------------------------------------------------------------------------------
# Workflow action and CLI


def dispatch(session, request, document=None):
    """The ``links`` workflow action: every link of the open document with its state."""
    with session.project(document=document) as project:
        return report(project)


def compile_command(cmd, args):
    """``vixl link SOURCE …``, ``link-set TARGET …``, ``link-refresh [TARGET]`` and ``link-embed TARGET``
    (``vixl links`` lists links and is a document command)."""
    if cmd not in TYPES:
        return None
    from .commands import Parser, pairs

    p = Parser(prog=f"vixl {cmd}")
    if cmd == "link":
        p.add_argument("source", help="The linked .vixl file (workspace-relative)")
        p.add_argument("--name")
        for key in ("x", "y", "width", "height"):
            p.add_argument("--" + key, help="pixels, 'center' or N%% (x, y); pixels or N%% (width, height)")
    elif cmd == "link-set":
        p.add_argument("target")
        p.add_argument("--source")
        p.add_argument("--clear", action="append", choices=["artboard", "source_page", "variables", "crop"],
                       help="Remove a setting (repeat)")
    else:
        p.add_argument("target", nargs="?", help="The link layer" + (" (default: every link)" if cmd == "link-refresh" else ""))
    if cmd in ("link", "link-set"):
        p.add_argument("--fit", choices=FITS)
        p.add_argument("--position", help="'0.5,0.5' fractions or an anchor such as top-left")
        p.add_argument("--crop", help="x,y,width,height in source pixels")
        p.add_argument("--artboard")
        p.add_argument("--source-page", dest="source_page", help="The source's page (name or number)")
        p.add_argument("--set", action="append", metavar="NAME=VALUE", help="Override a source variable (repeat)")
    a = vars(p.parse_args(args))
    op = {"type": cmd}
    clear = a.pop("clear", None) or []
    values = pairs(a.pop("set", None))
    if values:
        op["variables"] = values
    for key, value in a.items():
        if value is None:
            continue
        if key in ("x", "y", "width", "height"):
            value = value if value == "center" or value.endswith("%") else (float(value) if "." in value else int(value))
        elif key == "position" and re.fullmatch(r"-?[\d.]+\s*,\s*-?[\d.]+", value):
            value = [float(part) for part in value.split(",")]
        elif key == "crop":
            parts = [float(part) for part in value.split(",")]
            require(len(parts) == 4, "--crop is x,y,width,height in source pixels", "usage_error")
            value = dict(zip(("x", "y", "width", "height"), parts))
        elif key == "source_page" and value.isdigit():
            value = int(value)
        op[key] = value
    for key in clear:
        op[key] = None
    return op
