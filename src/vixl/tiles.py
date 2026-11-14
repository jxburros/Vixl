"""The streamed PNG export of a large canvas: composited as tiles (``render.render_bands``) and encoded band by
band (``fileio.PngWriter``), so the canvas is never held whole."""

from __future__ import annotations

from PIL import Image


def tileable(project):
    """Whether the document's canvas is large enough to tile and its regions render alone."""
    from .render import TILED_PIXELS, region_renders_alone

    c = project.state["canvas"]
    return c["width"] * c["height"] > TILED_PIXELS and region_renders_alone(project)


def png(project, variables=None, artboard=None, comp=None, *, alpha="auto", background="white", dpi=None,
        tile=None, workers=None):
    """The document as PNG bytes, composited and encoded band by band: the canvas is never held whole, so a large
    export costs a band, the tiles in flight and the layer cache instead of several canvas-sized images. The
    decoded pixels, the channels (``alpha``: auto, keep or flatten onto ``background``) and the resolution are
    those of the single-canvas export. None when the document is not tiled (``tileable``, ``render.tile_plan``)."""
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
        stream = R.render_bands(candidate, canvas_color, tile=tile or R.TILE, workers=workers)
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
