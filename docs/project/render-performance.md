# Render performance

[Documentation home](../README.md) · [Development plan](roadmap.md) · [Render parity](render-parity.md)

Where rendering time goes after the step 4 speed work (#590, #595, parallel frame ranges), measured on a 4-core
Linux container with `cProfile` and wall-clock best-of-three runs, and what that means for the open speed issues
(#584, #588, #591, #593). Re-measure before acting on a number here: they are from one machine.

## Profiles

| Document | Cold render | Where the time goes |
| --- | --- | --- |
| 2,000 ellipses, rectangles and rounded rectangles, 80% opacity, 6000 × 6000 | 15.1 s | `resvg_py.svg_to_bytes` 7.6 s (1,309 calls), PNG decode of its output 0.8 s, `alpha_composite` 1.2 s |
| The same, caches warm, no snapshot | 3.2 s | `alpha_composite` 1.5 s, image copies and crops 0.5 s, the gradient background 0.2 s |
| 1,500 text labels, 3000 × 2000 | 3.0 s | `resvg_py.svg_to_bytes` 1.5 s (one call per label, about 1 ms each) |
| 80 soft-shadowed ellipses, 4000 × 4000 | 1.6 s | `alpha_composite` 0.5 s, Gaussian blur 0.5 s (both release the GIL) |
| 144 timeline frames of a 640 × 360 lyric film, 324 layers | 10.8 s | Python layout per frame: resolving layers, extents, stroke margins, cache keys (`json` encoding) |

Two facts decide most of what follows:

- **resvg_py holds the GIL and returns PNG.** Four threads calling `svg_to_bytes` take as long as one. Its time
  grows with pixels at about 170 ns per pixel (a 200 × 200 ellipse: 6.7 ms; 1000 × 1000: 130 ms), which is mostly
  the PNG encode in the binding and the decode on our side, not rasterisation; a tiny SVG costs about 0.25 ms.
  `skip_system_fonts` saves under 10% (our SVGs hold paths, not text).
- **Pillow and numpy release the GIL.** Blur, compositing, resampling and image decoding run in parallel threads
  (a 1500 × 1500 Gaussian blur: 1.8× on four threads).

## What shipped

- **#590 render pool.** Only layers whose drawing releases the GIL (effects, styles, placed images, large
  gradients, gradient-filled shapes) are drawn ahead on threads; plain vector shapes and text are not, because
  threads would only add overhead. About a quarter faster on the soft-shadow document; byte-identical output.
- **#595, lighting part.** A lit scene keeps its canvas before lighting and relights only the dirty box.
- **Parallel frame ranges (#717).** Worker processes (not threads) render chunks of timeline frames; per-frame cost
  is Python layout, which processes do parallelise. Byte-identical frames.

## Decisions

- **#588 tiled compositing: deferred.** Tiles would parallelise the warm compositing (`alpha_composite`, 1.5 s of
  3.2 s above), but a layer larger than a quarter of the layer cache (96 MiB, a 24-megapixel layer) is not cached,
  so every tile it crosses would draw it again: a full-canvas gradient on 36 tiles is drawn 36 times. Tiling is
  worth doing only together with region drawing in `draw_ink` (solid, gradient, shape rectangles and rasters
  cropped before effects) and a streamed PNG writer; that is the issue's steps 3 and 4 and stays C4. Incremental
  renders already cover the common case (an edit re-composites a box, not the canvas).
- **#584 glyph cache: worth doing next, behind a switch.** Labels cost one resvg call each (1 ms); a glyph atlas
  would make 1,500 labels cost about one call and save roughly half of a cold label-heavy render. The risk is
  parity: compositing per-glyph coverage with `max` differs from resvg's single-pass antialiasing where glyphs
  overlap, so it needs the issue's fallback for overlapping clusters, `VIXL_GLYPH_CACHE=off`, and a visual review.
- **#591 Skia backend: an exploration, not adopted.** The measured bottleneck is the resvg_py binding (GIL held,
  PNG round trip), not resvg's rasteriser. A binding that returns the RGBA buffer and releases the GIL would cut
  vector and text raster time severalfold with no change in pixels; ask upstream (resvg_py) first, or carry a
  small binding as an optional extra. A Skia backend changes every golden and adds about 30 MB; it stays a note.
- **#593 native kernels: close with numbers.** The numpy loops it names are no longer where time goes: blur and
  compositing are Pillow C, and lighting is now relit per dirty box. numba would add about 50 MB to the frozen
  build for no measured gain on these documents.
