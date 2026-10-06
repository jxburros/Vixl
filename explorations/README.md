# Vixl explorations

Ten complex projects, each designed to stretch a different part of the engine. They were first built with Vixl 0.16.0 to find its limits; the committed outputs are now rebuilt with Vixl 0.20.0. Every project has a reproducible `build.py`, which you run from the repo root with `python explorations/NN-name/build.py`. Each also has its outputs and a README with the features it used and its findings. `python explorations/build_gallery.py` recomposes `gallery.jpg` from the outputs.

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

## Caveats on the outputs

- **The poster is at 150 dpi.** 01 builds at 150 dpi to keep the committed files small. For press resolution, set `DPI = 300` at the top of its `build.py`; every coordinate scales with the canvas.
- **The infographic's data is invented.** 08's renewable-share figures were made up to exercise the layout, and its README says so. Don't cite them.
- **The infographic's validate run passes; its contrast check does not.** The decorative sun and rays that bleed off the top edge are marked as decoration, so `validate` reports both datasets valid. Checking every text layer (it used to check 12 to save time) found one real error: the white "98.6%" label inside the first green bar is 3.42:1, below 4.5:1. The design is left as it was.
- **Build times with 0.20.0.** Each build ran on its own on a shared 4-core container, with downloaded fonts and the ICC profile already cached: 01 1 min 56 s, 02 25 s, 03 2 min 7 s, 04 36 s, 05 3 min 55 s, 06 40 s, 07 2 min 36 s to 3 min 9 s (two runs), 08 1 min 2 s, 09 2 min 7 s, 10 about 2 min 5 s. With 0.16.0 the longest builds took 8 to 14 minutes, mostly in the design check.
- **What changed in the rebuild.** Most designs are pixel-identical or nearly so. The visible differences are the fixes themselves (blur spreading past its box in 03 and 10, `oil-paint` without false colours in 05, uncut wing tips on the 07 creatures, card 009 left off the 07 print sheet for missing glyphs) and 0.20.0's new `roll` catalogue in 09, which rolls different directions. Each project README lists its differences and the workarounds removed from `build.py`.
- **0.20.0 bugs the rebuild found.** The 01 and 09 builds work around the first and third; see their READMEs.
  - A vector PDF export of a page with blend modes or adjustment layers crashes (`KeyError: 'type'` in the PDF writer's page fallback). 01 asks for `--pdf-content raster`.
  - `--quality` is ignored for PDF: Vixl's own PDF writer stores images with Flate, so the 01 poster PDF is 7.5 MB instead of 2.4 MB.
  - The contrast check cannot measure text whose box lands on a half pixel, which 0.20.0's fractional positions produce when text is centred on an odd-sized difference (`Could not measure 'cta': boolean index did not match ...`). It reports a warning instead of a ratio, and a suite then reports `needs_review`. Five text layers of the 01 poster are affected; 09 nudges its centred button labels by half a pixel so its group publish can pass.

## Cross-project findings

Each project README has repro details. These are the issues the explorations found in Vixl 0.16.0 that showed up most often or matter most. Items marked **Fixed** shipped in 0.18.0 ("Fixes from the explorations" in the [changelog](../CHANGELOG.md)) unless another release is named. The 0.20.0 rebuild, with most of the workarounds removed, exercises most of them.

### Bugs
- **Fixed: group bounds are frozen.** A group kept the bounds it had when created, so resized or rotated children got clipped (04, 10). Groups no longer clip their members, and `inspect` reports `drawn_bounds` for anything drawn past the box. Group `scale` no longer smooths pixel art (04).
- **Fixed: effects are clipped to the layer box.** A blurred shape rendered as a soft rectangle (03, 10). Blur now spreads past the box.
- **Fixed: stroke wider than its box crashes rendering.** A stroke wider than a small shape's box raised a raw PIL `ValueError` at render time, even though apply succeeded (03).
- **Fixed: swatch references break in some paths.**
  - `repeat`/`repeat-blend` rejected an `@swatch` fill (01).
  - A swatch whose value is `${var}` made every later `@swatch` use fail (07).
- **Text fitting is unreliable.**
  - **Fixed:** `fit:true` broke a word mid-word ("SOLSTI / CE") instead of shrinking it (01).
  - **Fixed:** `text-fit` rules always failed on auto-sized text (09).
  - **Fixed:** warped text was clipped at the top of its box (01).
- **Fixed: artboard `x`/`y` are accepted but ignored** (08). An artboard with `x`/`y` is now a viewport onto that region of the canvas.
- **Fixed: assertions read the wrong value.** `text.*.font-size` assertions ignored linked styles (08).
- **Fixed: `roll` previews and applies different directions.** Without `--size`, the preview and `--apply` picked different layouts (09).
- **Fixed: production with `workers:2` races** on the shared font cache (07).
- **Fixed: `--ink-limit` is silently ignored** when an ICC profile is given (01).
- **Fixed: outlined text fails the contrast check.** The 01 SIGNAL headline (dark fill, yellow `stroke` style) was flagged at 1.13:1; outlined text now passes when its outline contrasts with the backdrop.
- **Fixed: missing glyphs pass every check.** Tofu boxes went unreported (06, 07). They are now an error in every `check`, every suite and `validate`.
- **Fixed: boxed text clipped silently.** Raising the size of layout text cut it off at its `text-layout` box and `check` said nothing (09). The `bounds` check now reports it with the size the text needs.
- **Fixed: `oil-paint` adds false colours** to thin dark strokes on light ground (05). It now only uses colours already in the image.
- **Fixed: pen layers ignore their nodes' extent.** Without `width`/`height` a pen was canvas-sized, and a box smaller than the nodes clipped them silently (02, 08). The box now fits the nodes and stroke, and a too-small box is rejected.
- **Fixed: `scale` 0 leaves a 1-pixel sliver** (03).
- **Fixed: recipe input defaults override artboard variables** (07).
- **Not a bug: the 07 single-digit contrast "false positive".** The "7" really touches the stat pill's outline. The contrast message now gives the share of pixels and where they are.

### Performance
- **Fixed: the contrast check is the bottleneck.** It re-rendered the whole document per text layer, at 12–137 s per layer on large posters (01, 02, 07, 08). Top-level text is now measured from one shared render, with identical results, and nested renders, text measurement, styles and the layer cache are much cheaper. The full `check` on the 01 poster takes about 17 s instead of more than 10 minutes.
- **Fixed: painting slows quadratically** as strokes are added to a layer (05). A batch now costs time in proportion to its strokes (400 strokes: 9.8 s to 1.6 s), adding one stroke to a 3,000-stroke layer takes about 0.3 s instead of 10.7 s, and renders are pixel-identical.
- **Fixed: timeline export skips the persistent render cache.** Brush-heavy frames took about 14 s each without the cache and under 1 s with it (05, 10). Layers that only move are no longer redrawn per frame, and timeline exports of saved documents use the persistent cache.

### Rough edges
- **Fixed: vague errors.** Ragged pixel rows (04), constraint conflicts (08), the batch limit (05), far `px` pivots (03) and undefined swatches (02) now name the row, layers, anchors, numbers or operation involved. `validate --rules` takes inline assertions (08), and unnamed layers are numbered instead of colliding (09).
- **No effect reorder operation** (06).
- **`lookup` isn't a real effect.** It can't be disabled, reordered or limited to a selection (06).
- **Fixed in 0.19.0: CMYK PDFs are single raster pages** with no TrimBox or BleedBox (01, 02). The 02 business cards are now vector DeviceCMYK pages with embedded fonts, and the print PDFs of 01, 02 and 07 have a TrimBox and BleedBox. The 01 poster is still one image, because its blend modes need the backdrop.
- **Blend modes force raster fallbacks in SVG** (01): the full 01 poster is still one embedded image. Repeats of vector shapes did too in 0.16.0 (01, 08), but export as vectors since 0.17.0, so the 01 `vector` comp and the 08 poster now export strict SVG with no images.
- **`color_vision` checks only text,** not chart fills (08).
- **Fixed in 0.19.0: `animation-set` can't export a subset of frames** (04). Named animations replace the clone-and-delete workaround in 04.
- **Film captions have no font field,** and film camera zoom softens the image (10). 0.20.0 adds a caption font and style; 10 does not use it, so this rebuild does not confirm it. Camera zoom still crops and enlarges with bicubic resampling.

### Worked well
Atomic batches with precise, structured errors. Pivots on deep rigs. Markers used as times. Three-way branch merges with explicit resolutions and `expected_head`. Suite-gated group publishing. Symbols and artboards. Font pairing and embedding. The print, contrast, bleed and spacing checks caught real problems.
