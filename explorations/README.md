# Vixl explorations

Ten complex projects built with Vixl 0.16.0, each designed to stretch a different part of the engine. Every project has a reproducible `build.py`, which you run from the repo root with `python explorations/NN-name/build.py`. Each also has its outputs and a README with the features it used and its findings.

![Gallery](gallery.jpg)

| # | Project | What it pushes on |
| --- | --- | --- |
| 01 | [SOLSTICE SIGNAL print poster](01-print-concert-poster/) | Tabloid with bleed and safe guides, gradients, repeat-blend, clip, warped and path text, print/color-vision checks, SWOP soft proof, CMYK PDF/JPEG, SVG |
| 02 | [Morrow Coffee brand identity](02-brand-identity/) | Pen Béziers, pathfinder, palette-generate/define, symbols, artboards, business card, strict SVG, ICO and icon sets, HTML, palette suites |
| 03 | [HALO kinetic launch film](03-kinetic-launch/) | Timeline keys and easings, presets, markers, staggers, animated effects, motion-define/apply, GIF/WebP/APNG/MP4/sheet |
| 04 | [Vixl Quest pixel RPG pack](04-pixel-rpg/) | pixel-art/pixel-draw, frames, palette swaps, tileset, tile map via repeat, comps, nearest-sampled exports |
| 05 | [Generative mountain-lake painting](05-generative-painting/) | 3,700+ seeded strokes, all 17 brushes and custom brushes, masks, blends, adjustment grading, artistic-filter variants, timelapse |
| 06 | [Non-destructive photo lab](06-photo-lab/) | Every selection kind, masks, tonal stack, LUT, adjustment layers, presets, history branches and compare, all 19 filters and 5 effect workflows |
| 07 | [Aetherling Spirits trading cards](07-trading-cards/) | Variables, CSV `render --data`, comps, suites, recipe capture, plan/run matrix, durable jobs, CMYK print sheet |
| 08 | [The Great Green Switch infographic](08-infographic/) | Charts from data with shapes/paths/repeat, grids and constraints, spacing/validate QA, color-vision checks, SVG/HTML/PDF |
| 09 | [Loop collaborative campaign](09-collab-campaign/) | brand.json, rolls, layouts across 7 sizes, adapt-layout, branch fork/merge with conflict resolution, group-apply gated by suites |
| 10 | [Pip the robot film](10-character-film/) | Nested rig with pivots, walk/wave/jump, parallax, painted texture, film-plan with camera, crossfades, captions and audio to MP4 |

## Cross-project findings

Each project README has repro details. These are the issues that showed up most often or matter most.

### Bugs
- **Group bounds are frozen.** A group keeps the bounds it had when created, so resized or rotated children get clipped (04, 10). Group `scale` also smooths pixel art (04).
- **Effects are clipped to the layer box.** A blurred shape renders as a soft rectangle (03, 10).
- **Stroke wider than its box crashes rendering.** A stroke wider than a small shape's box raises a raw PIL `ValueError` at render time, even though apply succeeded (03).
- **Swatch references break in some paths.**
  - `repeat`/`repeat-blend` reject an `@swatch` fill (01).
  - A swatch whose value is `${var}` makes every later `@swatch` use fail (07).
- **Text fitting is unreliable.**
  - `fit:true` broke a word mid-word ("SOLSTI / CE") instead of shrinking it (01).
  - `text-fit` rules always fail on auto-sized text (09).
  - Warped text is clipped at the top of its box (01).
- **Artboard `x`/`y` are accepted but ignored** (08).
- **Assertions read the wrong value.** `text.*.font-size` assertions ignore linked styles (08).
- **`roll` previews and applies different directions.** Without `--size`, the preview and `--apply` pick different layouts (09).
- **Production with `workers:2` races** on the shared font cache (07).
- **`--ink-limit` is silently ignored** when an ICC profile is given (01).
- **Missing glyphs pass every check.** Tofu boxes go unreported (06, 07).

### Performance
- **The contrast check is the bottleneck.** It re-renders the whole document per text layer, at 12–137 s per layer on large posters (01, 02, 07, 08).
- **Painting slows quadratically** as strokes are added to a layer (05).
- **Timeline export skips the persistent render cache.** Brush-heavy frames take about 14 s each without the cache and under 1 s with it (05, 10).

### Rough edges
- **No effect reorder operation** (06).
- **`lookup` isn't a real effect.** It can't be disabled, reordered or limited to a selection (06).
- **CMYK PDFs are single raster pages** with no TrimBox or BleedBox (01, 02).
- **Repeats and blend modes force raster fallbacks in SVG** (01, 08).
- **`color_vision` checks only text,** not chart fills (08).
- **`animation-set` can't export a subset of frames** (04).
- **Film captions have no font field,** and film camera zoom softens the image (10).

### Worked well
Atomic batches with precise, structured errors. Pivots on deep rigs. Markers used as times. Three-way branch merges with explicit resolutions and `expected_head`. Suite-gated group publishing. Symbols and artboards. Font pairing and embedding. The print, contrast, bleed and spacing checks caught real problems.
