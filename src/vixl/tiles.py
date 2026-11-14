"""Tiled compositing: a large canvas drawn as tiles on the render pool, each one a region render.

A tile is exactly the crop of the whole canvas (``render.render_region``), so the tiles put together are the
pixels of a single-canvas render. Tiles are composited in parallel, and a consumer that takes them band by band
(``bands``, the streamed PNG export) never holds the canvas.

Layers too large for the layer cache would be drawn again for every tile they cross. ``plan`` deals with them
before the first tile: a plain fill or gradient is drawn per tile, cropped (``region_ink``); any other is drawn
once and held for the render; and when holding them would cost more than two canvases, the document is not
tiled (the single-canvas path draws them one at a time)."""

from __future__ import annotations

from collections import deque
import math

from PIL import Image

TILE = 1024
# The size at which a layer is drawn both ways to see whether a crop of it can be drawn alone.
PROBE = (96, 80)


def tileable(project):
    """Whether the document's canvas is large enough to tile and its regions render alone."""
    from .render import TILED_PIXELS, region_renders_alone

    c = project.state["canvas"]
    return c["width"] * c["height"] > TILED_PIXELS and region_renders_alone(project)


def boxes(width, height, tile=TILE, strips=False):
    """The tile boxes (left, top, right, bottom) of a canvas, row by row. ``strips`` gives tiles as wide as the
    canvas with about the area of a square tile (at least 64 rows): a consumer of whole rows needs no assembly."""
    if strips:
        rows = max(min(64, tile), min(tile, tile * tile // width))
        return [(0, top, width, min(height, top + rows)) for top in range(0, height, rows)]
    return [(left, top, min(width, left + tile), min(height, top + tile))
            for top in range(0, height, tile) for left in range(0, width, tile)]


def regional(project, layer, bounds):
    """How a crop of ``layer`` can be drawn without drawing the layer: "fill" (one colour), "gradient", or None.
    The layer sits unturned on whole pixels with nothing that reads its neighbours; and a small copy of it drawn
    by the renderer must equal the same copy drawn this way, so anything else the renderer does to a layer
    (now or later) keeps it out."""
    import numpy as np

    from .affine import precise
    from .render import draw_ink

    kind = layer["type"]
    if kind not in ("solid", "gradient", "shape") or (kind == "shape" and layer.get("shape") != "rectangle"):
        return None
    mask = layer.get("mask")
    whole = all(isinstance(layer[k], int) and not isinstance(layer[k], bool) for k in ("width", "height"))
    if (not whole or precise(layer) or layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y")
            or layer.get("repeat") or layer.get("linked") or (mask and mask.get("enabled", True))
            or any(effect.get("enabled", True) for effect in layer.get("effects") or [])
            or bounds[0] % 1 or bounds[1] % 1 or tuple(bounds[2:]) != (layer["width"], layer["height"])):
        return None
    small = {**layer, "width": PROBE[0], "height": PROBE[1], "opacity": 1}
    drawn = draw_ink(project, small, (0, 0, *PROBE))
    if drawn.size != PROBE or drawn.mode != "RGBA":
        return None
    pixels = np.asarray(drawn)
    if kind == "gradient":
        from .design_render import gradient_image

        return "gradient" if np.array_equal(pixels, np.asarray(gradient_image(project, small, PROBE))) else None
    return "fill" if bool((pixels == pixels[0, 0]).all()) else None


def region_ink(project, layer, bounds, size, kind):
    """The part of a ``regional`` layer that lies on a ``size`` tile, and the tile box (left, top, right, bottom)
    of the whole layer. The part is None when the layer misses the tile."""
    from .render import draw_ink

    x, y = math.floor(bounds[0]), math.floor(bounds[1])
    whole = (x, y, x + layer["width"], y + layer["height"])
    left, top, right, bottom = max(0, x), max(0, y), min(size[0], whole[2]), min(size[1], whole[3])
    if left >= right or top >= bottom:
        return None, whole
    if kind == "gradient":
        from .design_render import gradient_image

        return gradient_image(project, layer, (layer["width"], layer["height"]),
                              (left - x, top - y, right - x, bottom - y)), whole
    part = {**layer, "width": right - left, "height": bottom - top, "opacity": 1}
    return draw_ink(project, part, (0, 0, right - left, bottom - top)), whole


def plan(project, layers, bounds):
    """What a tiled render does with the top-level layers too large for the layer cache: (regions, held), where
    ``regions`` maps the ink key of each layer drawn per tile to its kind and ``held`` lists (key, layer, bounds)
    of those drawn once. None when the document should not be tiled: such a layer cannot be held (it reads a file
    or a lookup table), or holding them would take more memory than two canvases (the single-canvas path keeps
    the canvas, its snapshot and one such layer at a time)."""
    from .render import child_index, ink_identity, ink_margin, layer_cache

    c = project.state["canvas"]
    limit = layer_cache(project).budget // 4
    children, memo = child_index(layers), {}
    clips = {layer["clip"] for layer in layers if layer.get("clip")}
    regions, held, total = {}, [], 0
    for layer in layers:
        if layer.get("parent") or layer["type"] == "adjustment":
            continue
        if not layer["visible"] and layer["id"] not in clips:
            continue
        b = bounds[layer["id"]]
        mx, my = ink_margin(layer, bounds, children, memo)
        if b[0] - mx >= c["width"] or b[1] - my >= c["height"] or b[0] + b[2] + mx <= 0 or b[1] + b[3] + my <= 0:
            continue
        size = (math.ceil(b[2]) + 2 * math.ceil(mx)) * (math.ceil(b[3]) + 2 * math.ceil(my)) * 4
        if size <= limit:
            continue
        key, _, _, cacheable = ink_identity(project, {**layer, "opacity": 1}, b)
        kind = None
        if not layer.get("styles") and not layer.get("clip") and layer["id"] not in clips:
            kind = regional(project, layer, b)
        if kind:
            regions[key] = kind
        elif cacheable:
            held.append((key, layer, b))
            total += size
        else:
            return None
    if total > 2 * c["width"] * c["height"] * 4:
        return None
    return regions, held


def tiles(project, layers, bounds, background, *, tile=TILE, workers=None, drawn=None, planned=None, strips=False):
    """Draw the canvas tile by tile: yields ((left, top, right, bottom), image) row by row, the tiles of a row
    left to right. ``layers`` and ``bounds`` are the document's resolution (``project._resolution`` is set by the
    caller). ``drawn``, a dict, receives each top-level layer's canvas box as ``_render_layers`` reports it.
    Yields nothing when ``plan`` refuses the document; check ``plan`` first."""
    import contextvars

    from . import render as R

    c = project.state["canvas"]
    width, height = c["width"], c["height"]
    planned = planned or plan(project, layers, bounds)
    if planned is None:
        return
    regions, held = planned
    cache = R.layer_cache(project)
    top_level = [item for item in layers if not item.get("parent")]
    threads = R.render_threads()
    workers = threads if workers is None else max(1, int(workers))
    pool = None
    if workers > 1 and not getattr(R._IN_POOL, "active", False) and R.PROFILE.get() is None:
        pool = R.render_pool()

    # Where each top-level layer can draw (as ``_render_layers`` decides it, a pixel wider), found once: asking
    # every layer again for every tile cost more than compositing the tiles.
    children, memo = R.child_index(layers), {}
    always, reach = set(), []
    for layer in top_level:
        if layer["type"] == "adjustment":
            always.add(layer["id"])
            continue
        b = bounds[layer["id"]]
        mx, my = R.ink_margin(layer, bounds, children, memo)
        if layer.get("styles"):
            mx, my = (m + 2 * s + 4 for m, s in zip((mx, my), R.style_margin(layer)))
        reach.append((layer["id"], b[0] - mx - 1, b[1] - my - 1, b[0] + b[2] + mx + 1, b[1] + b[3] + my + 1))

    def job(box):
        left, top, right, bottom = box
        members = always | {ident for ident, x0, y0, x1, y1 in reach
                            if x0 < right and y0 < bottom and x1 > left and y1 > top}
        outer = getattr(R._IN_POOL, "active", False)
        R._IN_POOL.active = True  # A tile draws its own layers; drawing ahead belongs to whole-canvas renders.
        try:
            seen = {} if drawn is not None else None
            placed = R.shift(bounds, top_level, -left, -top)
            image = R._render_layers(project, layers, placed, None, (right - left, bottom - top), background, None,
                                     members, limit=(-left, -top, width - left, height - top), drawn=seen)
            return image, seen
        finally:
            R._IN_POOL.active = outer

    def report(box, seen):
        for ident, (x0, y0, x1, y1) in (seen or {}).items():
            moved = (x0 + box[0], y0 + box[1], x1 + box[0], y1 + box[1])
            before = drawn.get(ident)
            drawn[ident] = moved if before is None else (min(before[0], moved[0]), min(before[1], moved[1]),
                                                         max(before[2], moved[2]), max(before[3], moved[3]))

    pending = deque()
    try:
        for key, layer, b in held:
            image = R.layer_ink(project, {**layer, "opacity": 1}, b)
            image.info["vixl_held"] = True  # Shared by every tile: the compositor crops it and never changes it.
            cache.held[key] = image
        cache.regions.update(regions)
        todo = iter(boxes(width, height, tile, strips))
        if pool is None:
            for box in todo:
                image, seen = job(box)
                report(box, seen)
                yield box, image
            return
        # In flight: tiles being drawn and tiles waiting their turn, so memory stays a few tiles.
        window = workers if workers < threads else threads + 1

        def refill():
            while len(pending) < window:
                box = next(todo, None)
                if box is None:
                    return
                pending.append((box, pool.submit(contextvars.copy_context().run, job, box)))

        refill()
        while pending:
            box, future = pending.popleft()
            image, seen = future.result()
            refill()
            report(box, seen)
            yield box, image
    finally:
        from concurrent.futures import wait

        for _, future in pending:
            future.cancel()
        wait([future for _, future in pending])
        for key, _, _ in held:
            cache.held.pop(key, None)
        for key in regions:
            cache.regions.pop(key, None)


def render(project, layers, bounds, background, *, tile=TILE, workers=None, drawn=None):
    """The whole canvas, composited as tiles. None when ``plan`` refuses the document."""
    c = project.state["canvas"]
    planned = plan(project, layers, bounds)
    if planned is None:
        return None
    project.limits.size(c["width"], c["height"])
    canvas = Image.new("RGBA", (c["width"], c["height"]))
    for box, image in tiles(project, layers, bounds, background, tile=tile, workers=workers, drawn=drawn,
                            planned=planned):
        canvas.paste(image, box[:2])
    return canvas


def bands(project, background, *, tile=TILE, workers=None, lit=True):
    """The canvas as row bands, top to bottom: yields (top, image), each band the canvas width and the height of
    a strip tile (``boxes``). With ``lit`` the document's lighting is applied to each band by its place on the
    canvas. Only the bands in flight are in memory. Yields nothing when the document is not tiled (``plan``)."""
    from . import render as R
    from .scene import composite as light

    with R.resolving(project):
        layers, bounds = R.resolved(project)
        shared = getattr(project, "_resolution", None)
        project._resolution = (project.state, layers, bounds)
        try:
            for box, image in tiles(project, layers, bounds, background, tile=tile, workers=workers, strips=True):
                yield box[1], (light(image, project, box) if lit else image)
        finally:
            project._resolution = shared


def png(project, variables=None, artboard=None, comp=None, *, alpha="auto", background="white", dpi=None,
        tile=TILE, workers=None):
    """The document as PNG bytes, composited and encoded band by band: the canvas is never held whole, so a large
    export costs a band, the tiles in flight and the layer cache instead of several canvas-sized images. The
    decoded pixels, the channels (``alpha``: auto, keep or flatten onto ``background``) and the resolution are
    those of the single-canvas export. None when the document is not tiled (``tileable``, ``plan``)."""
    import io

    from . import render as R
    from .design import resolve_color
    from .fileio import PngWriter
    from .links import draw_scope

    candidate = R.view(R.view_page(project), variables, artboard, comp)
    if getattr(project, "_disk_cache", None) or not tileable(candidate):
        return None
    c = candidate.state["canvas"]
    size = (c["width"], c["height"])
    canvas_color = resolve_color(c["background"], candidate.state)
    if alpha == "keep":
        modes = ["RGBA"]
    elif alpha == "flatten" or R.color(canvas_color)[3] == 255:
        modes = ["RGB"]
    else:
        modes = ["RGB", "RGBA"]  # Both until a band shows transparency: an opaque canvas is written without alpha.
    pool = None if getattr(R._IN_POOL, "active", False) else R.render_pool()
    writers = {mode: PngWriter(io.BytesIO(), size, mode, dpi, pool) for mode in modes}
    under = R.color(background) if alpha == "flatten" else None
    profile = R.PROFILE.get()
    if profile is not None:
        import time

        started = time.perf_counter()
    count = 0
    with draw_scope():
        stream = bands(candidate, canvas_color, tile=tile, workers=workers)
        try:
            for _, band in stream:
                count += 1
                if under is not None:
                    base = Image.new("RGBA", band.size, under)
                    base.alpha_composite(band)
                    band = base
                elif "RGB" in writers and band.getchannel("A").getextrema()[0] != 255:
                    if "RGBA" not in writers:
                        # Transparent pixels on an opaque canvas colour (a blend can do it): start again with alpha.
                        stream.close()
                        return png(project, variables, artboard, comp, alpha="keep", dpi=dpi, tile=tile,
                                   workers=workers)
                    del writers["RGB"]
                for writer in writers.values():
                    writer.write(band)
        finally:
            stream.close()
    if not count:
        return None
    if profile is not None:
        profile.phase("render", time.perf_counter() - started)
        profile.render(incremental=False, tiled=True)
    writer = writers.get("RGB") or writers["RGBA"]
    writer.close()
    return writer.stream.getvalue()
