# Changelog

## Unreleased

### Fixes

- `irregular` no longer fails with "Dimensions must be integers" on a `path` shape created without width/height; its box comes from the path's reach, which is fractional for curves.

## 0.21.0

A breaking "correctness and consolidation" release. Duplicate concepts are gone (one opacity scale, one anchor table, one guidance registry, one place for LUTs), checks report what is actually drawn, and renderers agree with each other. Old saved documents, field names and render output may change; forgiving input aliases (camelCase, `rect`, `font_size`, `"50%"`) stay.

### Breaking changes

- **Opacity is 0-1 everywhere** (the `opacity` operation, creation fields, layer styles, captions, paint/pattern, keyframe/animate/motion values; CLI `opacity 75` too). Write `0.7` or `"70%"`; a bare number above 1 is an error with a suggestion instead of being guessed.
- **`vixl_text_add` is removed.** Use the `text` operation in `vixl_operations_apply` (registered font names work there too).
- **`vixl_guide("capabilities ...")` is removed.** Use `vixl_capabilities(topic)` or `vixl capabilities TOPIC`. `vixl_guide(brief=NAME)` for a guidance name returns `{guidance, text, kinds}`; art-kind guides no longer include `direction`.
- **`temperature` and `tint` have a new scale.** Both are multiplicative, keep grey brightness and run -100...100 (100 is about 6500 K to 4400 K for temperature); out-of-range values from the old scale are rejected. The paper look is warmer, temperature is visible and tint is weaker. New `white-balance` effect (gains or a neutral colour).
- **LUT lookups are ordinary stack effects.** The `lookup` operation appends a `lookup` effect that can be enabled, disabled, reordered, selected and removed; the old layer `lookup` field is converted on load.
- **Effects apply before rotate, flip and skew** in the layer's own frame, so blur room, selections and spatial filters (halftone, wave, pixelate, vignette, grain) turn with the layer. Rotated layers render differently from before.
- **Open paths and open shape kinds (line, wave, zigzag ...) with a stroke and no explicit fill render unfilled** in raster, SVG, PDF and PPTX (they were white). A `path` shape without width/height now gets its box from the path's reach from the layer origin, not the whole canvas.
- **Checks:** `checked.layers` is replaced by `checked.layers_checked` and `layers_total`. A contrast the checker cannot measure is an error, not a warning. The canvas safe area is checked by default; story/reel presets use per-side bands and print presets default to 0.25 in (6 mm metric). Pass `safe_area=` to override.
- **Batch errors:** a batch is validated as a whole and one error lists every invalid operation (`errors`, `error_count`). Unknown `adjustment` effect fields and unmatched `preset-apply` overrides are errors, not warnings. Passing both `target` and `targets` to a per-layer operation is an error, and single-layer operations reject `targets` with more than one entry.
- **Export:** `quality` defaults to none; PDF images stay lossless unless it is given (other formats still default to 90). Sheet exports report the sheet's size as `size` and the cell size as `frame_size`. GIF dithering defaults to `auto`.
- **Schema enums:** easing, `animate-preset` preset and pivot values are enums, so bad names fail validation; pivot arrays must have exactly two numbers. `operations.PIVOT_ANCHORS` and the per-module anchor tables are removed in favour of `geometry.ANCHORS`. `font-fallbacks` rejects `target` (fallbacks are document-wide).
- Deck, PPTX and PDF title detection no longer matches layer-name substrings or the first text layer; see the new `title` role below.

### Agent interface and validation

- Every operation schema carries `x-targets`. About 90 per-layer operations take `targets` and fan out over them in one atomic batch with one history entry and the original `operation_index` on errors; group, align, distribute and pathfinder keep joint semantics (#188). The table in `docs/operations.md` is generated and tested.
- `vixl_operations_apply`, REST `/operations` and the CLI take `operations_path` (a workspace-relative `.json` or `.jsonl`; JSONL errors cite line numbers), `check` and `preview` options, so one call can edit, check and look (#184, #180). Findings are bounded to fix-level findings and touched layers.
- Schema descriptions are no longer overwritten by shared constants (#224). Anchor synonyms (`bottom-center`, `top-center`, `center-left` ...) normalize and are reported. `"none"` is accepted for fills, strokes and colours and stored as `transparent`.
- New fields: `opacity` and `rotation` at creation and on edits of shape/text/solid/gradient/add; `space: "canvas"` on shape/text/solid/gradient edits of grouped layers; pivot `units: "canvas"`; group `above`/`below` (#244, partial).
- `effect-move` reorders effects (`to`: position/top/bottom, `before`, `after`; CLI `vixl effect move`); effect operations accept an effect name (#164). Pixel-art with `rows` accepts a matching width/height (#227).
- `vixl_document_create` takes `font_pairing`; applying heading/body roles without typography warns about the proofing fallback and points to `vixl_fonts` and `vixl_font_pair` (#248). Advisories resolve the shape from the targeted layer and stop firing radius/sides hints for shapes that read other fields (#229).
- Tool descriptions are sharper where tools overlap (animation vs timeline, validate vs check, measure_spacing vs spatial, guide vs capabilities). Stale `vixl_*` names in docs and skills are fixed, and a test fails on unknown ones (#252).
- `Project.show(page, region)` and `Project._repr_png_` display designs in notebooks (#176).

### Checks you can trust

- Contrast, before/after crops and coverage share one whole-pixel box, so half-pixel positions and odd widths are measured instead of failing (#195).
- Background detection, bounds, safe area and overlap use tight drawn geometry (stroke included, in canvas space through groups and transforms) rather than layer boxes; `role: background` is honoured, and a canvas-spanning box must actually paint at least half the canvas to count (#196, #197). Overlap uses ink bounds widened by stroke, shadow and glow (#249). On the repo examples, fix-level findings dropped from 44 to 5 with errors unchanged.
- Shapes and gradients crossing two or more canvas edges are intentional bleed (info) (#250). Thumbnail legibility is a warning only for social, icon and app-store sizes (info elsewhere); `thumbnail_width` null/`"off"` disables it (#219). Canvas `safe` may be given per side (#211).
- `color_vision` compares chart series colours under protan/deutan/tritan simulation; the layer intent `color_vision_safe` opts a layer out (#230, partial).
- `vixl_check` with no checks adds `motion` when a timeline exists: loop seams, seam speed, empty posters, text hidden at the poster frame, and legibility at frame 0 (#237, partial).

### Rendering and effects

- Resampling of rotated and scaled rasters is clamped to the colour and alpha range of the contributing pixels, which removes ringing and halos (#204). Denoise on a rotated layer matches the upright result within 15% (#203).
- Text lines never end after a lone separator (`·`, `•`, `–`, `—`, `|`, `/`) (#226). The event-poster date is capped at 60% of the headline size; octopus arms are connected with tip widths (#225); chart axis maxima are tighter and a warning notes series colours that override `colors` (#214, partial).
- Imported images honour embedded ICC profiles; CMYK JPEG/TIFF convert to sRGB (#194, partial).

### Export

- Vector PDF no longer fails on pages with blend modes or adjustment layers; the page is exported as a raster fallback with a complete descriptor (#201). PPTX plain text keeps bold and italic from the registered face (#198). SVG omits stroke attributes when width or alpha is 0 (#228).
- PDF `quality` JPEG-compresses images when given (#202). PDF Title is the explicit `title` (export, CLI `--title`, MCP, batch), then the page's title layer, then the file stem (#209). Title detection uses `role: title`, then exact title/heading/headline names, then the largest top text; there is a new `title` layer-intent role (#220).
- Still exports over 1 MB warn and name grain, paper, film, halftone and noise layers; an optional `max_bytes` budget (CLI `--max-bytes`) warns when exceeded (#190).
- Form tooltips drop required markers (`*`, "(required)"), and a `tooltip` field sets one explicitly (#222, partial).

### Animation and loops

- `timeline-set loop_mode: "seamless"` and `close: true` / `loop_safe` on keyframe, animate, animate-preset and motion append the start value so loops close. Entrance/exit presets hold then play back in seamless timelines; seams are compared modulo 360 and symmetry, and speed jumps are reported as `loop-seam-speed` notes (#238).
- `animate` and `animate-preset` take `repeat`/`until`, `period` and `stagger`; the `spin` motion recipe takes `turns` and `symmetry` (#185).
- `export_timeline` takes `poster` (time, marker, `"end"` or a percentage) for GIF/APNG/WebP and rotates frames so the poster is first while the loop stays seamless (#189). `vixl_timeline_preview(times=[...], thumbnail=360)` shows poster, middle and last frames at phone width (#253); `timeline-sheet --thumbnail` on the CLI.
- GIF `dither` (`auto`, `none`, `ordered`, `floyd`) on a shared palette and a soft `max_bytes`; big or gradient GIFs suggest MP4 or WebP (#246, partial). Sheet results report the real sheet size, and GIF/WebP/APNG report frames and durations read from the written file (#208).
- Keyframe easing, extend, hold and trim semantics are documented in the schema descriptions and `docs/brushes-and-animation.md` (#254); easing and presets are enums (#243).

### Guidance

- Animation and character guides are rewritten as checklists (one gesture, loop first, readable at frame 0, joints with pivots, motion check, first/middle/last preview) with worked mascot and loop examples; art briefs no longer get the poster layout block (#236). Looping guidance covers period, stagger, seamless mode, close, spin and repeat, and `vixl_capabilities("loop")` lists it (#185).
- The pattern recipe scatters motifs instead of tiling a grid (#216, partial). Irregular/tear edges are recommended in character, scene, pattern and hand-drawing guides, and a new `imperfection` entry covers hand-made looks (#256, phase 1).

### Consolidation

- One guidance registry (`guidance.py`) feeds `vixl_guide`, `vixl_resource_get` and `vixl_capabilities`. One anchor table, one Bezier evaluator and one number formatter replace several copies (#255, partial); open-shape fill rules come from `geometry.OPEN_SHAPES` and `default_fill`.
- Operation classification lives in `targets.py`; shared schema constants are copied, never mutated.

### Testing

- A golden-image suite in `tests/visual` renders fixture documents (shapes, paths, text, gradients, effects, rotated rasters, blends, groups, charts, organic shapes) and compares PNG renders, SVG/PPTX structure snapshots and PDF renders with references. Run it with `pytest -m visual`; regenerate with `VIXL_UPDATE_GOLDEN=1`. A CI job runs it on Linux.
- New regression suites cover the agent surface, check trust, effect stack, export correctness, geometry consolidation, loops and posters, the operation API and docs table, and schema descriptions.
- `CLAUDE.md` gives agent contributors the test, schema and documentation conventions.

## 0.20.0

### Editable vector drawing and placement

- Expand the parametric shape catalog with configurable arrows, per-corner rounding/chamfers, rounded stars and seals, geometric/technical shapes, symbols and ornaments.
- Add complete stroke controls: dashes, offsets, caps, joins, alignment, multiple strokes, width profiles and markers, with shared vector geometry for SVG/PDF output.
- Convert shapes to editable path nodes; move/insert/delete/reverse/round nodes, simplify and smooth paths, offset paths, outline strokes and use additional pathfinder modes. Non-destructive vector distortion supports envelopes and corner pinning, including animated parameters.
- Preserve fractional vector sizes and positions. Resize/scale from named or fractional anchors, skew/shear, apply affine matrices, resize relatively, match sizes and fit/fill regions. Optional pixel snapping remains available.
- `move` explicitly supports canvas coordinates for grouped layers. Inspect reports parent/canvas bounds and coordinate semantics. `vixl_spatial` measures relationships, margins, alignment, grid/guide offsets, compositional positions, hit tests, empty regions and applicable snap suggestions.

### Containers, templates and design variety

- Hug-content stacks support padding and backgrounds for pills, badges, buttons and code windows. Containers support image slots, focal cropping, masks, adaptive min/max sizing, reflow and content-preserving layout variants.
- Expand the container and use-case template libraries, with palette/style/light/dark variants and a reproducible preview gallery. Comic layouts provide editable panels, reading order, gutters, artwork slots, captions and dialogue.
- Sparse briefs choose from curated safe palettes, layouts, pairings and understated finishes. Choices and seeds are reported; explicit seeds, fixed variety and user/brand locks preserve reproducibility.
- Rolls vary additional coherent dimensions and keep a bounded workspace history to reduce repeats. Low/medium/high variety controls the choice pool.

### Motion, characters, sound and film review

- Procedural motion, compact keyframe arrays, character part standards, reusable character assets, constrained rigs, two-bone IK, reusable cycles and viseme cues reduce handwritten keyframes.
- Add depth-based parallax, camera choreography, deterministic particles, compositing light/color controls and cut-paper texture/cadence. New motion and character checks report suspicious timing or invalid rigs.
- Speech/thought/shout/whisper bubbles size to their text and follow their target; captions support font/style/background and fade/typewriter animation.
- Import, synthesize and mix audio tracks with timing, gain and fades; export WAV and mux timeline/film video. Video sampling returns visible frames; audio analysis reports levels, clipping, silence, onset timing and optional spectrograms.
- Preview a film frame, shot or interval with camera/transitions applied before a full render. Draft previews, seeking and cached unchanged frames make review faster.

### Materials and visual guidance

- Built-in repeatable patterns and custom tiles, pattern-filled artwork/strokes, pencil/charcoal/crayon/ink-wash/stipple/hatch finishes and an undoable clone stamp with aligned and merged-source sampling.
- On-demand references and recipes cover motion, natural color/light, anatomy, illustration and perspective. Natural palette and figure/perspective helpers include advisory checks based on explicit scene measurements.

### Text, preview and export corrections

- Preserve leading whitespace, including non-breaking spaces, in text and rich text. Inspection exposes ink/line bounds, baselines, ascent/descent and cap/x heights.
- Re-import Vixl SVGs with empty definitions; prevent zero-size allocations in reduced previews of tiny repeated shapes; keep links rooted consistently before and after saving.
- Support raster `Project.export(page="all")` contact sheets. Export methods consistently refuse existing files unless `overwrite=True` is explicit.
- Deck checks respect thumbnail width and projected/screen/phone profiles. Decorative glows/gradients and explicit crop intent avoid false crop/overlap findings.
- Opt-in downsampling keeps placed image assets compact while preserving source-resolution defaults. Existing PPTX font warnings, deterministic form measurements and bulk editing regressions remain covered.

### Agent interfaces and release discipline

- Atomic batches now allow 10,000 operations. Canonical alias handling and factored schema constraints keep interfaces aligned; new CLI operations derive their flags from the same schema.
- `vixl_capabilities` provides task-aware fields, workflows and gotchas. Schema help explicitly documents registered fonts and literal-pixel path coordinates. Workflow errors identify unknown fields, valid fields and likely corrections.
- Validation and timeline inspection return bounded summaries by default, with filters, pagination and full-detail opt-in. Intentional bleed can be marked or individual validation rules suppressed.
- Document the measured full/core/compact/slim MCP tradeoffs and keep generated repository artifacts free of model signatures. Update release metadata to 0.20.0.

## 0.19.0

### Print and raster export

- **RGB PNGs.** Exports take `alpha`: `auto` writes RGB when every pixel is opaque and RGBA otherwise, `keep` always writes RGBA, and `flatten` composites onto `background` and writes RGB, as JPEG and PDF already do. `vixl_export_file` and `vixl export` default to `auto` (`--alpha` on the CLI); `Project.export` keeps RGBA by default. Applies to PNG, WEBP, TIFF and AVIF.
- **Exact print PDF pages with TrimBox and BleedBox.** Single-page documents created from a print size now export through Vixl's own PDF writer, like multi-page documents, so they get a TrimBox and BleedBox (Pillow's PDF encoder wrote neither). The page measures exactly trim + 2 × bleed from the size's physical dimensions even when the bleed is a fractional number of pixels: an 11 × 17 in poster with 0.125 in bleed at 300 dpi is 810 × 1242 pt with a 9 pt TrimBox inset, not 810.24 × 1242.24 pt. An explicit `dpi` other than the canvas dpi still maps pixels to points at that dpi.
- `form-fill` accepts `combine: true` (writes `<data>-filled.pdf` beside the CSV, or to `output` when it is a `.pdf`) and rejects wrongly typed fields with a structured error naming the field, the expected type and example values, instead of a raw Python error.
- `vixl_workflow_schema` reports each action's field `properties` (types, enums, descriptions; fully for `form-fill`), and the `field`, `field-set` and `form` operations' schemas give every setting a type and description.
- **CMYK PDFs keep vectors.** Text, shapes, paths and gradients stay vector in DeviceCMYK through the same separation as CMYK images; only effects and images become CMYK images.
- Deck PDF pages match PPTX slides (7.5 in tall for a screen canvas) and `dpi` sizes both. A PPTX names the fonts it does not embed (`warnings`, `fonts_not_embedded`); the fonts themselves are not embedded.
- Pathfinder booleans export as real geometry in SVG, PDF and PPTX (one compound path with `evenodd` fill, no alpha masks), so they render the same in browsers and Inkscape.

### Behavior changes

- **PDF export is vector by default for every document** (it was a single image for plain single-page documents). `pdf_content="raster"` still flattens, and the export result reports `content`, `content_reason`, `color_space` and `page_size`. Photo-heavy pages are larger than the old JPEG output because images are stored with Flate.
- **MCP `vixl_operations_apply` and `vixl_text_add` return `detail: brief` by default** (IDs, names, bounds and warnings of changed layers). `compact` and `full` still return more; CLI, REST and Python defaults are unchanged.
- **`resize` with only a width or only a height changes only that side** (imported images stay proportional by default; `keep_aspect` chooses explicitly).
- **Drawing `straighten` keeps each line at its drawn angle** by default (`angles: "drawn"`); pass `"axes"`, `"45"`, `"guides"` or a list to snap.
- **A keyframe past the end of the timeline reports the change** (`timeline duration changed 8000 -> 8400 ms`) instead of lengthening it silently.

### Text, fonts and rich text

- Operation batches over MCP and REST accept `font` (a registered name or the `heading`/`body` role) on `text`, `text-set`, `layout-apply`, fields and rich-text spans; a file path is refused with a pointer to `vixl_font_install`, `vixl_font_pair` and `vixl_import_font`.
- `text-set` on a rich-text layer keeps bullets, spacing and span styles where they still apply and reports what it dropped under `warnings`. `text-set` and `text-style` explain their split in the schema and tool help, and a rangeless `text-style` that only sets color, size or font acts as `text-set`.
- The `fonts` check no longer flags rich text whose spans set their own font, and checks fallback glyphs against each span's font. `${variables}` inside a rich-text span (page numbers, for example) keep that span's font and formatting in PNG, SVG, PDF and PPTX.
- `font_install` and `font_pair` results report where a font came from (cache or download, URLs, cache file, whether `VIXL_FONT_CACHE` chose it) and the embedded file.

### Layers, layouts and variable content

- `shape`, `solid`, `gradient` and `text` given a `target` edit that layer in place (same ID, order and effects); a target of the wrong kind is rejected naming the operation to use.
- Text takes `hide_if_empty`, and the new `stack` operation lays a group out as a row or column that reflows and re-centres around hidden or empty members, so a CSV row without a company line no longer leaves a gap.
- `roll`/`vixl_roll` take `unfilled` (default `omit` when slots are given), so an applied roll passes `check` without a second layout pass.
- `edit-layers` applies a change or an operation to every layer matching a selector (role, name, kind, tag, text); `layer-intent` takes `tags`. `adapt-layout` without `targets` re-lays a document out at another size (proportional, reports each layer's move), and `vixl_adapt_layout` does several sizes in one call.

### Animation, timeline and lyric videos

- Named animations: `animation-set` with `name`, `order`, `duration`/`durations`, `loop` and `delete` defines subsets of saved frames with their own order and timing; `export-animation --animation NAME` exports one on its own, and sprite-sheet JSON lists `animations`. `export-animation` also writes `webp`, `mp4` and `webm` (`quality`).
- `frames-edit` applies a list of operations to every saved frame, a named animation's frames or chosen frames, atomically (a shared recolour is one call; frames are still stored as full snapshots).
- Keyframes accept `extend: false` to keep the duration. Negative `scale`, `scale-x` and `scale-y` mirror a layer and animate (a beam can swing through a flip); `scale` takes per-axis `x` and `y`.
- Animatable `trim_start` and `trim_end` (0-100 %) and `line_cap` on shape and pen strokes, with `draw-on` and `draw-off` presets: stills, GIF/MP4 and SVG draw the stroke on; PDF and PPTX rasterize the layer and say so.
- Lyric video: an empty timestamp also clears the next-line preview, identical consecutive lines hold instead of re-fading, `cue_animation` fades, slides or sweeps `cue-*` layers, and `lyric-video-export` keeps hand edits to an existing build (`rebuild: true` rebuilds; `build_stale` is raised if the options changed under hand edits).

### Shapes, organic forms and imperfection

- `organic` presets follow `stroke` and `stroke_width` on every output (shell chambers, leaf veins, feather barbs), including when regrowing, and take `fill`.
- `shape: arc` draws pie wedges, donut segments and rings (`start_angle`, `end_angle`, `inner_radius`) in PNG, SVG, vector PDF and PPTX; `vixl.wedge.wedge_path` is the reusable geometry.
- Opt-in imperfection ([docs](docs/irregular.md)): `irregular` (seeded wobble, vertex jitter, stroke-weight and pressure variation, color drift, micro placement) and `tear` (fractal torn edge with a paper rim and fibres, as a mask, clip or path), for characters, hand-made looks and ripped paper, not for logos or anything that must align.
- `look` applies one of 14 named finishes (glow, drop shadow, grain, paper texture ...) in one operation; `radial-repeat` makes rosettes and mandalas in one step.

### Photos, drawings and previews

- `denoise` effect: edge-preserving non-local-means noise reduction with separate luminance and chroma strengths and a `search` window; non-destructive, NumPy and Pillow only (about 1 s per megapixel at the default).
- Drawing import flattens a page photographed at an angle (paper detection and perspective correction; `perspective: false` skips it) and takes `color` for the line colour (default `#1d1d1f`, now documented). Gap closing runs after straightening and makes sharp corners and T joins (`close_gaps` accepts `"auto"`), and `vectorize`/`restyle` take `width: "uniform"` or a number; stroke widths are measured from ink area.
- Reduced previews snap layer and repeat edges to whole pixels, so repeated tiles no longer show seams the export lacks.

### Forms

- Signature fields can be `required` (signed in the viewer; fills never need them) and multiline fields take `max_length`. Validation rules (`format` email, digits, number decimals and range, date display, and a text `pattern` with `message`) are exported to fillable PDFs as AFNumber/AFRange/AFDate and JavaScript field actions, and every page with fields declares `/Tabs /S`.
- `vixl_render_preview(values=...)`, enlarged exports and page contact sheets draw field values like the filled export (they were oversized and clipped). The `vixl_check` form worst-case reports what it measured (`measured`, plus `max_length_that_fits`), and its multiline sample now wraps so an unfixable overflow can no longer appear.

### Diagrams and text flow

- `diagram`, `diagram-set` and `diagram-from-text` ([docs](docs/diagrams.md)) draw flowcharts, dependency graphs, org charts and mind maps as editable vector layers: layered, tree, radial, mind-map and grid layouts, orthogonal, curved or straight routing, swimlanes, fit-to-canvas, and node kinds (process, decision, terminator, I/O, note, group). Re-layout keeps layer IDs stable; `diagram-from-text` takes `A -> B: label`, `A{Question?}`, indentation hierarchies and `group Lane: A, B`; `check --checks diagram` reports overlapping nodes, edges through nodes and unreadable labels.
- `text-flow` ([docs](docs/text-flow.md)) flows one story through linked text frames (columns, pages, shape-following bands) with keep-together, orphan and widow rules, rich-text spans preserved, automatic reflow when the text or frames change, overflow reported in results (`remaining_chars`) and a `flow` check. Frames are ordinary text layers holding their slice, so every export works unchanged. Limits: lanes do not nest, `${variables}` are not expanded while flowing, and a direct edit to a frame's text is overwritten at the next reflow.

### Charts

- `chart` and `chart-data` ([docs](docs/charts.md)): bar, stacked, 100 %, horizontal, line, area, pie and donut charts from an inline table or a workspace CSV, drawn as a group of vector layers. Editing the data keeps layer IDs (the group stores totals, shares and scale), `check` sees inside charts, and PPTX export writes native, editable charts with an embedded data table.

### Linked documents and data merge

- Linked-document layers ([docs](docs/linked-documents.md)): `link`, `link-refresh`, `link-embed`, `vixl links` and the `links` check draw another `.vixl` live with fit, position, crop, artboard, page and variables. Changes to the source show at the next render, with stale and missing reporting, cycle and depth checks, vector text in PDF, and links confined to the workspace over MCP and REST.
- `merge-impose` / `vixl merge` ([docs](docs/imposition.md)): CSV rows laid out on print sheets with gutters, bleed, crop and registration marks and slug text, as a vector-text PDF and an editable sheet of live links. Rows are validated first and the merge can be rerun. Vector PDF export with many glyphs is several times faster.

### HTML presenter

- `export deck.html` of a multi-page document is a self-contained slide presentation ([docs](docs/presenter.md)) with inline vector slides, keyboard, click, swipe and `#3` navigation, an overview grid, CSS transitions from the page settings, one-slide-per-page printing and a speaker view with notes and timer. `--presenter`, `--no-presenter`, `--presenter-theme`, `--slide-images svg|png`, `--start-slide` and `--no-notes` configure it; slides SVG cannot express are listed under `raster_fallbacks`.

### MCP server and agent experience

- Every MCP tool runs in a worker thread. A call still running after 40 s (`VIXL_MCP_INLINE_SECONDS`) becomes a job, `as_job` starts one at once, and `vixl_job` polls, waits, returns results or cancels. Operation batches, timeline frames and export targets send progress notifications, and `request_id` on mutating tools makes a retried call replay the recorded result instead of applying twice.
- The active document is per MCP client session (a stdio server has one session, so subagents sharing one still share it); `vixl mcp --require-document` / `VIXL_REQUIRE_DOCUMENT=1` makes `document=` mandatory, every result names its document, and arguments a tool does not take are reported.
- Apply results carry `warnings` for text cut off by the canvas or overflowing its box and for fields that were accepted but changed nothing; schema errors end with a pointer to `vixl_operation_schema` and list the accepted fields. `document_create` and exports create missing directories; `vixl_export_batch` writes several targets in one call.
- Every operation has a one-line description, typed and described fields and, for the common ones, examples; every workflow action has a summary and typed, described fields, and the check-suite object is typed. A lint test enforces this. The MCP `tools/list` inline operation schema grew from about 35.7k to about 49k characters with the new operations (`--schema slim` advertises names only).
- `vixl_guide` maps a brief (icon, character, scene, pattern, mandala, logo, diagram ...) to operations, layouts, looks and styles, and the server instructions and skill open with a start-here recipe. Image slots list `fill_with` options and `layout-apply` returns `next_steps`; `layout-apply` and `palette-apply` explain how roles were assigned and take `keep_order` and `roles`; check findings carry `action` (`fix`, `review`, `informational`) and `layer-intent allow_crop` marks an intentional crop.
- Design styles ([docs](docs/styles.md)): 28 styles (swiss, brutalist, art deco, kawaii ...) with guidance and premade checks, `style-set`, `check --checks style` and `vixl_styles`.

## 0.18.0

### Digital Shift identity

- Preserve the complete Digital Shift logo kit, including usage guidance, SVG/PNG/PDF artwork, icons and editable Vixl masters.
- Apply light/dark README logos, a branded browser review header and favicon, and the app icon to the Windows launcher, runtime, installer and Claude Desktop bundle.
- Synchronize the package, plugin and versioned MCP source URL at 0.18.0. This release also includes the previously unreleased features below.

### Lyric videos

- **`lyric-video` workflow** ([docs](docs/lyric-video.md)): a song, a user-timed LRC file and a styled template become a synced MP4/WebM. `lyric-video-plan` validates and returns the timed lines, sections, frame count and warnings; `lyric-video-build` writes an ordinary, editable keyframed document; `lyric-video-export` renders it with the song as the audio track. Sections switch `bg-<section>` layers, `cue-<words>` layers appear while a line contains those words, and `lyric-next`, `section-label` and `intro` are filled in. Available through the CLI, MCP, the `lyric-video` durable job kind (inputs frozen at submission) and REST (`lyric-video-plan`). `vixl.lyrics` exposes `parse_lrc`, `plan`, `build` and `export`.
- **MP4/WebM have no 3,600-frame cap.** Streamed video is bounded only by the 10-minute duration; buffered formats (GIF, APNG, WebP, sheets, PNG sequences, film ZIPs) keep the cap. Frames are piped to ffmpeg as raw pixels instead of PNG, film frames whose animated state is unchanged reuse the previous render, and keyframe tracks hold up to 8,192 keys with binary-search sampling.
- `vixl.film.audio_duration` reads an audio file's length with ffprobe. Design checks skip empty text layers instead of warning that they cannot be measured.

### Organic shapes

- **`organic`** ([docs](docs/organic.md)): living forms as ordered parts, each a **generator** (superformula, blob, leaf with margins and venation, petal, log/Archimedean spiral, Raup shell, tapered tentacle with curl, wave and elbow joints, Honda/Leonardo branching, L-systems, Vogel phyllotaxis, relaxed Voronoi cells, Gray–Scott reaction–diffusion, scales, segmented bodies, feather, ellipse/egg/teardrop, growth rings, any SVG path) followed by composable **rules** (radial symmetry with alternating whorls and fans, mirroring with fluctuating asymmetry, placement along a spine or at another part's anchors, Poisson-disc scatter, golden-angle and grid placement, noise, D'Arcy Thompson warps, jitter, smoothing, clipping, size gradients, and pixel-space smooth union, paint-order occlusion and intersection). 32 presets (flower, sunflower, rose, tree, pine, fern, vine, starfish, jellyfish, octopus, shell, snail, caterpillar, mushroom, feather, coral, cactus, giraffe, spots …) take parameters and per-part colors. Results are vector path layers that regrow in place with a new seed. `vixl organics` and the `organic-catalog` workflow action list everything.
- Path layers accept up to 8,192 commands and 256 KiB, and `line_cap` (round caps and joins for organic strokes).

### Guides, grids and placement

- **Guides beyond right angles** ([docs](docs/guides.md)): guides can be angled `line`s, `ray`s, `segment`s, `point`s, `circle`s and curved `path`s. `grid --kind` generates baseline, thirds, golden-section, harmonic-armature, golden-spiral, polar, isometric, triangular, hex, oblique and 1–3 point perspective systems (each also takes a `region`); grids and guides can be deleted.
- **`place`** puts layers on any guide: at a fraction along it, spread evenly or at a fixed spacing, at intersections of two guides, with an anchor of the layer on the guide, turned to the tangent or normal. It works inside scaled and rotated groups. **`snap`** moves near misses onto guides, points and intersections and straightens near-miss angles.
- **`guides` and `alignment` checks** report anchors a few pixels off a guide (with the fixing move), rotations a few degrees off a guide's angle, and sibling layers almost aligned or almost parallel. Previews draw guides (`render_preview(guides=True)`, MCP `guides`, CLI `render --show-guides`); `vixl guides` lists them. Constraints read point and circle guides and horizontal/vertical lines.
- `checks.canvas_projection` is the shared canvas-space projection of layer bounds (design checks, guide checks and form export use it).

### Rich text

- **Rich text in one text box** ([docs](docs/rich-text.md)): `rich-text` creates or replaces content from Markdown (bold, italic, underline, strike, highlight, super/subscript, `[text]{color=… size=… font=…}`, headings, nested bullet and numbered lists) or explicit spans and paragraph settings; `text-style` styles a matched word, a character range or whole paragraphs of any text layer. Paragraphs carry list type and level, alignment including justify, spacing before and after, indent and line height; wrapped list lines hang under their text. Bold and italic use installed variants (`inter-700`, `inter-400-italic`, or `font_variants`) and are synthesized otherwise. Fit-to-box shrinks every size together. The same shaped layout draws PNG and vector SVG (and feeds PDF and PPTX export).
- Shaped glyphs record the characters they come from (ligatures included), for text extraction.

### Pages, slides and decks

- **Multi-page documents** ([docs](docs/slides.md)): `page add|select|remove|move|set` turns a document into ordered pages with their own layers (sharing canvas, fonts, swatches, styles and guides), speaker notes, per-page backgrounds and variables, hidden pages and transitions; `master add|select|remove|set` holds layers drawn underneath every page that uses them. Any operation takes a `page` field. `${page}`, `${pages}` and `${page_name}` are built in. Undo, save/load, validation and `inspect` cover pages.
- **Vector PDF export** for paged documents (and any document with `--pdf-content vector`): real, selectable and searchable text in embedded TrueType subsets with Unicode maps (plain and rich text, synthetic bold and italic), vector shapes, paths and gradient shadings, images as images, and per-layer raster fallbacks for what PDF cannot draw the same way, listed with reasons. Text runs are written one line at a time so viewers extract lines and words correctly. TrimBox/BleedBox for bleed, raster pages and CMYK on request, byte-identical output.
- **PowerPoint export** (`export deck.pptx`): one editable slide per page with text boxes and real runs (fonts, sizes, colours, bold/italic/underline/strike/highlight, super/subscript, bullets and numbering, spacing), title placeholders, preset and custom-geometry shapes with fills, gradients and outlines, groups, pictures, speaker notes, hidden slides and transitions. Positions match Vixl's render, checked against LibreOffice.
- **Deck checks** (`check --checks deck`): the design checks on every page (repeated findings merged) plus title placement across pages, a consistent type scale, words per page, minimum projected type size in points, missing speaker notes and empty pages.
- `render --page N` / `--page all` (a labelled contact sheet, also `vixl_render_preview(page="all")`), `export x.png --pages all` (numbered files for carousels), `--pages 1-3,intro` for PDF and PPTX, and `vixl pages`. MCP `vixl_export_file`, `vixl_check` and `vixl_render_preview` and the REST export and preview routes take `page`/`pages`.

### Forms

- **Fillable forms** ([docs](docs/forms.md)): `field` layers (text, multiline, number, date, checkbox, radio, dropdown, signature) with keys, accessible labels, required/read-only flags, defaults, formats, options, comb cells, overflow rules and a drawn appearance; `field-set` and `form` (tab order, title, language). Fields render in PNG, SVG, PDF and previews with their current values, and `render --show-fields` / `show_fields` outlines them with keys and tab numbers.
- **Fillable PDF export** (`export form.pdf --fillable`, `fillable=True`): AcroForm text, button, choice and signature fields over the vector page artwork, with generated appearances (no `NeedAppearances`), `/TU` names, `/DA` Helvetica entry, reading or explicit tab order, title and language — no actions, hex strings only, byte-identical output, multi-page forms.
- **Filling**: `form fill --set …` or `--data rows.csv` (one file per row with name templates, or `--combine` into one PDF), `vixl.forms.fill` / `fill_data`, MCP `vixl_export_file(values=…, fill_mode=…)`, the `form-fill` workflow action and durable job. Every row is validated first (`missing_required`, `unknown_key`, `invalid_option`, `invalid_number`, `invalid_date`, `too_long`, `invalid_format`, `overflow`), with `--dry-run` and `--skip-invalid`; editable mode prefills a fillable PDF. Filled values never reach the document, its history, the render cache or error messages, and jobs delete their copy of the data. Field values are `${key}` variables in text layers.
- **`form` checks** (a default check): names, overlaps, rotation, page and trim bounds, tab order, encodable defaults, box and mark sizes, non-text contrast, layers above fields, and `--sample worst|rows.csv` overflow checks. `inspect`, `field list` and MCP inspect summarize fields with their rectangles in points.
- Agent evaluations `form-registration` and `form-batch-fill`, with a `pdf_fields` grading check; `pypdf` and `python-pptx` join the dev dependencies for tests.

### Hand drawings

- **Build on a hand drawing** ([docs](docs/drawing.md)): `drawing import` turns a photo or scan into clean lines — the sheet of paper found and the desk around it left out (its edge is never traced as ink), paper lighting and shadows divided out, dust removed, a tilted page corrected, cropped, the pencil's grain and (optionally) colour kept — over a hidden, aligned copy of the photo. `vectorize` traces editable centre-line strokes with each line's width (or outline shapes that keep pressure); `straighten` makes nearly straight lines straight, keeps drawn corners but sharpens them, keeps curves (lobes, arcs, waves) as drawn — in a stroke with both, only the straight sides change — rounds nearly round shapes into circles, snaps sides to angles or the document's guides and joins ends that nearly meet; `smooth`, `restyle` and `stroke` (new lines in the same hand) edit strokes; `fill` colours enclosed regions under the lines, bridging small breaks without crossing a line.
- **Preservation is measured**: `drawing report` / the `drawing-report` workflow action give the share of the original lines still covered and the share that is new, `drawing compare` overlays the original on the result, and the opt-in `drawing` check warns when original line work is lost. `ai drawing-color` adds image-to-image colouring under the drawing's own lines.

### Tool comparison kit

- **`evals/tool-comparison/`** ([guide](evals/tool-comparison/README.md)): 16 hand-run briefs (picture, social post, print poster, logo kit, deck, fillable form, CSV badges, infographic, multi-size campaign, photo correction, hand drawing, animated intro, pixel sprite, lyric video, seamless pattern, menu) for comparing Vixl with HTML/SVG, Python libraries, free desktop tools, image generation and Claude Design under the same model. Judging notes give lanes, hard checks, round-2 revisions and answer keys; `inspect_outputs.py` reports tool-neutral facts (sizes, color modes, PDF boxes, color spaces and form fields, PPTX text and notes, video timing, tile seams) and makes blind copies; `fixtures/` holds the inputs.

### Fixes from the explorations

Fixes for the problems found while building the ten projects in `explorations/`.

- **Groups no longer clip their members.** A member that is resized, moved or rotated past the group's box (a sprite scaled up, an animated limb in a nested rig) still draws, and scales, flips and turns with the group in PNG and SVG. The box itself is unchanged for layout; `inspect` reports `drawn_bounds` for anything drawn past it. Scaling a group of pixel layers stays nearest-neighbor.
- **Blur spreads past the layer's box**, so a blurred shape keeps its outline instead of becoming a soft rectangle; at the canvas edge the layer's edge pixels continue, so full-bleed photos do not fade. A later size- or position-dependent effect (wave, noise, vignette, contrast, artistic filters) keeps its stack within the box, unchanged. SVG filter regions and `rasterize` include the spread.
- A stroke wider than its shape no longer crashes rendering with a raw Pillow error; the visible ring shrinks to nothing as the box approaches the stroke width.
- `@swatch` colors work in `repeat`/`repeat-blend` fills and endpoints, and swatches defined from variables (`"${brand}"`) resolve everywhere, including per-row render variables.
- `text-layout fit` shrinks until the longest word fits on a line instead of breaking it ("SOLSTI / CE"). The `text-fit` suite rule measures auto-sized text as drawn, so it no longer always fails.
- Artboard `x`/`y` are kept: such a board is a viewport onto that region of the document canvas.
- Characters no font can draw are a `fonts` error in every `check` (whichever checks are selected), an automatic `missing-glyphs` failure in every suite (so production and gated group edits catch them) and a `validate` failure.
- Text shaping keeps per-thread font objects, fixing production runs with `workers: 2` that failed with `TTLibError`. Unexpected production errors record their message.
- `validate` grades decorative layers (`layer-intent --role decoration`) that bleed off the edge as warnings.
- Warped text (`flag`, `arc`) is moved back inside its text box instead of losing the tops of lifted letters, in outlines, SVG and the raster fallback.
- `text.NAME.font-size` assertions and `validate`'s size warnings use a linked character style's size.
- `vixl -p DOC roll` previews read the document's canvas and brand (as does a session's current document), so they pick the same direction as `roll --apply`.
- `--ink-limit` applies after ICC separation too, instead of being silently ignored with `--icc`.
- Contrast checks credit outlines: text with a `stroke` style at least 3 px wide (and 2% of its font size) passes when its outline contrasts with the backdrop, and `measure --target` reports the outline's contrast.
- The `bounds` check reports boxed text (a `text-layout` width and height) that no longer fits its box, such as after `text-set` raises the size, with the size it needs.
- `oil-paint` takes the mode of a luminance key and copies that pixel's color, so thin dark strokes no longer get green, magenta or blue fringes.
- A layer scaled below one pixel on either axis (a `scale`/`scale-x` key of 0) draws nothing instead of a 1-pixel sliver.
- A recipe input's default only fills a variable the document and artboard leave unset: row values beat artboard variables, which beat input defaults.
- `pen` without `width`/`height` fits its layer box to the path, its stroke (including mitred corners) and its handles instead of spanning the canvas; node coordinates stay canvas positions, `x`/`y` offset them, `x:"center"` centers the box, and editing by `target` keeps the frame. A box smaller than the nodes is rejected instead of clipping them.
- Contrast issues say what share of the glyph pixels fail and where (`weakest_region`, also in `measure --target`), instead of "for most glyph pixels".
- Clearer errors: ragged pixel rows name the row and both widths; constraint errors name the layers or the conflicting anchors; the batch-size error gives the limit; a `units:"px"` pivot that is too far is reported in pixels; an undefined swatch is reported at the operation that uses it.
- `vixl validate --rules` also takes a single assertion and can repeat. Unnamed layers are numbered (`shape`, `shape 2`) instead of failing on the second one.
- **Faster checks.** Top-level text is contrast-checked from one shared render instead of three renders per layer; nested group renders reuse the document's resolved layout; text measurement is cached; styles and blends are computed over the layer's region instead of the whole canvas; the in-memory layer cache is least-recently-used and sized for real documents. The 01 poster's full `check` went from more than 10 minutes to about 17 s with identical results.
- **Faster painting.** Strokes rasterize over their own footprint, a layer's painted strokes are cached so adding strokes renders only the new ones, a paint operation validates only its new stroke, and layout no longer copies every stroke. 400 strokes in one batch: 9.8 s to 1.6 s; one more stroke on a 3,000-stroke layer: 10.7 s to 0.3 s. Output is pixel-identical.
- **Faster timelines.** Cached layer images are keyed by size rather than position, so layers that only move are not redrawn each frame, and timeline exports and contact sheets of saved documents use the persistent render cache (per user: `~/.cache/vixl/render`, or `VIXL_RENDER_CACHE`). A brush-heavy test went from 3.9 s to 0.7 s per frame (0.2 s when exported again).
- The ten exploration builds, which took up to 14 minutes, now finish in 13 s to about 4 minutes.

## 0.17.0

- Seeded editable rose, leaf, petal, and blob paths; path fitting; adjustable pen tension and corner anchors.
- Paint coordinate-space guidance and resolved stroke diagnostics; content QA warns about completely invisible layers.
- Consistent font-file handling for layouts and text. Automatic bundled glyph fallback, explicit document fallback stacks, and missing-glyph QA use the same PNG/SVG shaping pipeline.
- Layouts inherit the document's light/dark mode, with predictable defaults and a non-mutating preview command.
- Explicit `new --overwrite`, persistent NDJSON CLI sessions with atomic requests, runtime diagnostics, and export progress on stderr.
- Decoration roles and explicit overlap allowances make composition intent available to QA.
- Repeated vector primitives remain vectors in SVG. Unsupported repeated groups retain explicit raster fallback.
- Distributed GIF/WebP/APNG frame durations preserve requested timing; export reports include encoded durations.
- Version/help/no-update launches avoid installation write locks and pending activation.
- Runtime installation retries transient Windows scanner/probe file locks with a bounded wait and keeps the active version on failure.
- Fully verified version changes merged to main can publish releases; publication remains gated by Linux tests, Windows tests, bundled runtime, installer, and installation checks.

## 0.16.0

- Local contiguous/global wand, polygon/path lasso, pen handles/freehand curves and full SVG path syntax.
- Portable custom palettes, strict role assignment and full-resolution palette compliance rules.
- Eight modular templates, interchangeable fixed-size containers with rules/reflow/tests, and reusable saved shapes.
- Seven starter design suites, custom suite scaffolding, five saved multi-tool effects and an offline studio tour.
- Workspace project groups with checked bulk edits and durable rollback recovery; independent agent branches with field-level three-way merges and explicit conflicts.
- Versioned declarative plugin packs with namespaces, dependency/cycle validation, atomic upgrades/removal; opt-in trusted Python operation extensions.
- Static SVG appearance/auto import with original-source retention, and standalone responsive HTML export.
- Consolidated workflow actions and a 12-tool compact MCP profile; existing profiles/tools remain available.

## 0.15.0

- Cross-platform agent distribution: base-package MCP dependency, PyPI Trusted Publishing workflow,
  Claude Code plugin/marketplace and Claude Desktop MCPB build artifacts with the complete skill.
- Streamable HTTP MCP with the REST bearer-token policy and loopback protection; stdio remains available.
- Live `view` page for renders, layers, history and persistent review notes shared with CLI/MCP agents.
- Workspace `brand.json` defaults for layouts, templates and rolls, embedded fonts/logos, and brand checks.
- `roll --apply` applies fonts and a layout atomically; layout results expose unfilled slots directly.
- Editable SVG shape/path import, compound-path rendering, and optional raster PDF page import.
- Sixteen offline agent briefs, stored acceptance baseline, weekly full/slim live comparisons when configured,
  and a documented core/slim setup that reduces tool schema context by approximately 46%.

## 0.14.0

- **Character animation and sharper motion.** A new `pivot` operation (`vixl pivot arm 0.5 0.05`,
  anchor names, `--px`, `--clear`) makes rotation and scale turn about a joint that stays fixed in
  renders, timeline frames, layout bounds and SVG; animated rotation no longer drifts; group
  `translate`/`rotation`/`scale` keyframes carry their children; `animate`, `animate-preset` and
  `keyframe` accept `targets` (CLI `a,b`). `export-timeline --scale` (now up to 16) renders frames at
  full resolution instead of enlarging them, and `export --scale` and large icon-set sizes re-render
  text, shapes and vectors the same way. `export-animation` gains `--sampling smooth|nearest` with
  fractional smooth scales, and frame animation works at any canvas size within the pixel budget (the
  256×256 cap is gone). GIFs are much smaller with no visual change (frame differencing for opaque
  animations), accept `--colors 2–256`, and the export result warns above 1 MB; a 728×90 4 s banner
  went from 929 KB to 190 KB (76 KB at 64 colors). New REST `POST /animation/export`.
- **MCP as two servers.** `vixl mcp --tools core` serves editing, rendering, checks, export and the
  catalogs; `--tools ai` serves the provider-backed tools plus workspace/open/inspect/preview. Both
  share the workspace and see each other's saved edits. The default (`all`) is unchanged.
- **Windows: `vixl` works in already-open sessions.** The installer also places the launcher in
  `%LOCALAPPDATA%\Microsoft\WindowsApps` (already on the user PATH of running programs) when that
  folder is on PATH, never over another program's `vixl.exe`, and removes it on uninstall. The copy
  finds the installation through `VIXL_HOME`, the installer's `HKCU\Software\Vixl\InstallRoot`
  record, or `%LOCALAPPDATA%\Programs\Vixl`. The agent skill tells agents to check the standard
  install locations and `python -m vixl` before asking where Vixl is, and the MCP docs now give the
  correct install path.
- **Palettes, fonts and templates.** `palette apply` also sets the role swatches (`@background`,
  `@ink`, `@accent` …), recoloring layouts and templates (`roles: false` adds only numbered swatches).
  Templates roll their colors into role swatches and give text `heading`/`body` font roles, so
  `font pair` re-fonts them. `text`/`text-set` accept `font` as a registered name, role or file, and
  `missing_font` lists the registered fonts.
- **Checks and layouts.** On print sizes, legibility is judged in printed points (below 6 pt) instead
  of at thumbnail width. `event-poster` grows its type on large formats, keeps the date on one line
  and sets the facts at the foot. `render --data` checks every row and attaches a `check` report to
  outputs with problems (`--no-check` skips it). Icon sets warn when they enlarge embedded images.
  `vixl text --help` shows `text add` usage, and `inspect` accepts `--target`.
- **Fixes from a ten-design hands-on pass.** Stroked polygons, stars and closed paths now join
  their first vertex instead of leaving a notch. `text-set` keeps a `text-layout` box, so changing
  the color, size or copy of wrapped text no longer collapses it to one long line. SVG export now
  names the cause of a `repeat`, lookup-table or raster-mask fallback instead of reporting a
  generic "unsupported vector appearance".

- **Fill-in-the-blank layouts and templates.** Layouts and built-in templates no longer render
  invented sample copy. Unfilled slots appear as visible `[Label]` placeholders recorded in
  `state.blanks`, and the new default `blanks` check reports them as errors. `unfilled: "omit"`
  leaves them out instead. Copy for a slot a layout doesn't use now fails with `unused_slot` and
  lists the slots it does use, instead of being silently dropped. `layout show` / `vixl_layouts_list`
  describe each layout's slots. Built-in templates roll their colors from a seeded palette unless
  colors are supplied; custom templates can declare `blanks` and `roll`.
- **Typefaces.** A researched catalog of open-licensed Google Fonts families (classification,
  weights, x-height, width, contrast, era, mood, roles, misuse cautions), curated heading/body
  pairings with the reasoning behind each, and a pairing-principles guide (`vixl fonts`,
  `font show`, `font pairings`, `font principles`, MCP `vixl_fonts`, REST `/typefaces`).
  `font install FAMILY --weight N` and `font pair NAME|random` download on request, cache per user,
  embed and register fonts, and set the document typography (`font-register` gains `role`) that
  layouts use by default. The bundled font is now a proofing fallback, and a new default `fonts`
  check warns when text uses it.
- **Dice.** `vixl roll` / `vixl_roll` / `GET /roll` rolls a coherent direction from one seed: a
  pairing, a mood-consistent palette, a layout suited to the purpose and canvas, and its parameters,
  returned as a ready `layout-apply` operation. Choices can be locked. Layouts and templates accept
  `seed: "random"`, record which choices were rolled, and suggest exploring when parameters were thin.

- Add persistent design check suites with structural/pixel baselines, explicit time coverage,
  measured failures and needs-review outcomes. Checked actions commit only when suites pass;
  reusable repairs cannot modify their contracts.
- Add typed template metadata, portable document recipes with example validation, named
  actions, minimum-size text fitting, grid arrangement, explicit vertical reflow, semantic
  layer roles and staggered/relative motion recipes.
- Add bounded variant matrices, draft/final production, per-output checks/repairs,
  contact sheets, checksum-verified resume and selective rebuilding.
- Add versioned editable component libraries and optional persistent layer/frame caching
  with font/runtime invalidation and corrupt-cache fallback.
- Add durable background production/image/video/film jobs with frozen inputs, worker locks,
  cooperative cancellation and recovery without blindly repeating external inference.
- Add shot sequences for stills, document timelines and video clips, camera movement,
  crossfades, captions, explicit audio mixing and staged ZIP/MP4/WebM exports. Generated
  video uses an opt-in HTTP job gateway; live service calls are not part of offline tests.
- Expose production through `vixl workflow`, Python and workspace MCP, with fixed-project
  REST checks/actions/planning. Keep the inline MCP operation schema below its existing
  size budget by hoisting shared constraints and moving field prose to schema discovery.
- Add an offline production example and [workflow reference](docs/production.md).

## 0.13.0
- **Color language.** Every color field accepts CSS Color 4/5 notations (`lab()`, `lch()`, `oklab()`, `oklch()`, `hwb()`, `color(display-p3|rec2020|srgb-linear|xyz …)`, `color-mix()`), `cmyk()`/`device-cmyk()`, `gray()`, `kelvin()`, 148 CSS and 938 public-domain (CC0) xkcd survey color names, and modifiers (`lighten`, `darken`, `saturate`, `desaturate`, `mix`, `tint`, `shade`, `tone`, `alpha`, `rotate`, `complement`, `invert`, `grayscale`, `readable`). Swatches work inside expressions and may build on other swatches. Out-of-gamut colors are mapped by OKLCH chroma reduction.
- **Color tools.** `vixl color` / `vixl_color` / `POST /color` describe, convert, harmonize (10 schemes), build 50–950 scales, mix and check WCAG contrast; `palette-generate` stores scales and harmonies as swatches.
- **Print output.** CMYK JPEG/TIFF/PDF export via a supplied ICC profile (LittleCMS, rendering intents, embedded profile) or device-naive GCR with black generation and total ink limits; PDF and ICO export; `export-icons` for web/Apple/Android/Windows icon sets; dpi metadata from the canvas; soft proofing; color-vision simulation (Machado 2009). Opt-in `print` (ink coverage, effective image ppi, type under 6 pt, live area, bleed) and `color_vision` checks.
- **Named sizes.** 150 sizes across print, stationery, photo, posters, packaging, social, web, ads, email, video, slides, screens, app stores, icons, logos and games. Print sizes keep physical units, dpi, bleed and a safe area with generated trim/safe guides. `vixl new NAME`, `canvas size`, `Project.sized()`, `vixl_document_create(size=…)`, and named artboard presets.
- **Principled layouts.** 33 `layout-apply` composition systems (hero statement, editorial grid, split screen, rule of thirds, golden section, Z/F patterns, asymmetric balance, big number, quote, framed, diagonal band, typographic poster, product card, event poster, banner, letterhead, business card, slides, logo lockups, emblem, monogram, app icon, thumbnail, vertical story, price list, photo caption, minimal mark, bento grid). They adapt to the canvas and vary by seed (or content): contrast-checked color roles, a modular type scale, margins, alignment, accents and grids. Type is shrunk to fit small formats, and the choices are recorded in `state.layout`. `type-scale` defines character styles; new guidance covers typography, color, layout, accessibility, print, icons, motion and brushes.
- **Brushes.** Editable paint layers store strokes and render them deterministically with 17 brushes (round, soft-round, airbrush, pencil, ink, fineliner, brush-pen, marker, highlighter, calligraphy, chalk, charcoal, crayon, watercolor, dry-brush, spray, splatter). Strokes support explicit or simulated pressure, tapers, paper/grain/canvas textures, wet edges, bristles, spray, erase, SVG-path input, per-stroke overrides and `brush-define`.
- **Animation timelines.** `timeline-set`, `keyframe`, `keyframe-remove`, `animate`, `animate-preset` (22 presets) and `marker` animate any layer property (position, translate, scale, rotation, opacity, size, colors in OKLab, text, visibility, effect amounts) and the canvas background with 30+ easings. Frames render with `render --time`, contact sheets show motion at a glance, and `export-timeline` writes GIF, APNG, animated WebP, sprite sheets, PNG-sequence ZIPs, or MP4/WebM with ffmpeg.
- **Interfaces.** New MCP tools `vixl_sizes_list`, `vixl_layouts_list`, `vixl_brushes_list`, `vixl_color`, `vixl_timeline_inspect`, `vixl_timeline_preview`, `vixl_export_timeline` and `vixl_export_icons`; preview/export/check tools gain time, proof, simulation and print options. REST adds `/sizes`, `/layouts`, `/brushes`, `/color`, `/timeline`, `/timeline/frame` and `/timeline/export`.
- **Fixes.** Project lock files are removed after use (filelock 3.21+ is now required). Model routing consults a saved catalog before loading an optional SDK, and the native Anthropic adapter test skips without the `anthropic` extra. CSS color names keep priority even after Pillow caches parsed names. Swatch definitions may reference other swatches.
- **Docs.** The provider documentation records that the adapters have been used successfully against real services. New guides cover [sizes and layouts](docs/sizes-and-layouts.md), [color and print](docs/color-and-print.md) and [brushes and animation](docs/brushes-and-animation.md), and the agent skill gains matching references.

## 0.12.1
- Reject inaccessible pending runtimes without crashing the launcher, including Windows access-denied errors during file inspection. Preserve the active runtime even when no previous version exists, retain the underlying error/path in update status, and keep update settings available without starting the engine.
- Activate explicit `vixl update` commands before returning, with a final installed-path health check, accurate active/previous version reporting, and rollback retention. Background updates still stage without disrupting running sessions.
- Handle update/check/rollback in the stable Windows launcher even when the active engine cannot import. Existing launchers gain these controls by running the new installer.
- Inspect visible nested group content in design checks and contrast measurements, accounting for group transforms, opacity, clipping and child targeting instead of reporting zero text layers.
- Report vector-only status and raster fallback reasons in saved SVG CLI results; retain strict SVG rejection and vector group/text regressions.
- Document same-session PATH setup, multiple-install/version diagnosis, and migration from older staged updaters.

## 0.12.0
- Add 19 local, editable artistic filters: sepia, duotone, solarize, pixelate, halftone, crosshatch, ink-blot, stamp, photocopy, pencil-sketch, charcoal, find-edges, emboss, oil-paint, watercolor, swirl, ripple, wave and glass. No AI provider/model is used; seeded treatments are repeatable.
- Share HarfBuzz shaping, bidi/script runs, layout and outlined glyph geometry between PNG and SVG, including ligatures, combining characters, supported Unicode scripts, wrapping/fitting, multiline/path text and warp presets. Outline rendering can slightly change text spacing/antialiasing from earlier versions.
- Keep common color adjustments, blur, drop shadow, glow, stroke, color overlays, vector clipping and supported adjustment layers native in SVG. Preserve unaffected vector layers around unsupported raster appearances.
- Add strict SVG export policy through CLI, Python, REST and MCP, with responsible layer/effect details and no output overwrite on rejection. SVG filters are allowed; bitmap sources and unsupported appearances remain explicit limitations.
- Add visual/filter/history/parameter regression tests and frozen Windows checks for the new shaping and rendering dependencies.

## 0.11.1
- Fix Windows CLI normalization/Unicode response encoding, including frozen executables and redirected output; successful saved edits no longer fail while printing normalization notes.
- Correct native SVG rotation to use the same clockwise direction as PNG.
- Preserve scalable logo groups, gradients, pixel grids, opaque boolean silhouettes and outlined plain ASCII wordmarks in SVG. Report remaining raster fallbacks in SVG metadata; complex text and unsupported appearances remain faithful raster fallbacks.
- Compress embedded fonts again while retaining original compressed image bytes without recompression; restore compact font-heavy logo project sizes.
- Load the image engine lazily for version/global-help commands, reducing startup overhead on discovery paths.
- Reconcile agent skill/output/blur/path documentation, and add independent SVG rendering plus frozen Windows workflow regressions.

## 0.11.0

- Position Vixl and its documentation as a headless application designed for autonomous AI agents.
- Add self-contained SVG exports with native simple shapes/Bézier paths and documented raster fallbacks; expose export formats through CLI, Python, REST and MCP. Verify transparent PNG and JPEG background flattening.
- Add 16 shape/path shortcuts, editable single-contour Bézier paths, and geometry guidance for rotated logo construction.
- Add 32 palettes, six reusable design templates, custom resource registration, and portable overall/style design guidance included in AI planning.
- Add explicit local/HTTPS TTF/OTF font imports, registered document fonts, and workspace font tools.
- Add document-independent command discovery/help and compact CLI edit responses with `--detail full` opt-in.
- Add authenticated model discovery, capability routing, and native Anthropic/Gemini plus OpenAI-compatible Mistral/Meta adapters. Midjourney is supported only through a user-configured HTTP gateway.
- Cover new features with offline regression tests; live paid-provider inference requires user credentials and is not exercised by CI.


Vixl's main users are AI agents; this release targets long agent sessions, fewer round trips and fewer tokens.

**Long sessions**
- History stores structural deltas with a full snapshot every 32 revisions (`.vixl` format 2; format 1 still loads). Historical revisions are validated when restored.
- Reaching `max_history` squashes the oldest unreferenced revisions instead of making the document read-only.
- Edits no longer deep-copy the whole history: edit latency stays flat (≈20 ms after hundreds of edits instead of growing past 100 ms).
- Imported PNG/JPEG/WebP files keep their original bytes and image assets are stored without recompression: a 24 MP JPEG document is 2.8 MB instead of 25 MB and an edit autosaves in ≈0.04 s instead of ≈1.1 s. Unreferenced assets are dropped on save.
- Saving preserves an existing file's permissions (it used to force 0600) and new files honor the umask.

**Agent ergonomics**
- A shared normalizer accepts common model guesses in every interface (shape/type aliases, camelCase keys, `font_size`, `fill`/`color`, opacity 0–100, CSS `rgba()`, style shorthands, `"N%"` and `"center"` geometry) and reports each rewrite under `normalized`. Blur `radius` is read as `amount` (it was previously accepted and silently ignored). The command line no longer divides opacity separately.
- Errors carry `operation_index`, `operation_type`, `field`, `allowed` and `suggestions`; MCP now passes this structure through instead of a flat string.
- MCP results are minified JSON without duplicated structured content; advertised schemas drop pydantic titles and Optional wrappers. Compact diffs return new values only; new layers return name/type/bounds; `vixl_document_inspect` defaults to a compact summary; measurements summarize histograms unless `histogram: "full"`.
- `vixl mcp --schema slim` plus `vixl_operation_schema` for on-demand field lookup. `vixl_ai_plan` is opt-in (`--planner`).
- New: `vixl_check` / `vixl check` / `Project.check` / `POST /check` (bounds, text overlap, WCAG contrast, safe area and reserved zones, thumbnail legibility); `vixl_render_compare` / `POST /compare` (side-by-side or diff of revisions, `head~N`, `previous`); zoomable previews (`region`); `vixl_document_close`; `Project.at(ref)` and `Project.resolve_ref(ref)`.
- Sessions keep up to 8 documents open; every MCP tool accepts `document`. `vixl_import_image` accepts base64 or data URLs. `vixl_import_image` now returns a compact layer summary.

**Speed**
- Plain layers composite only over their own bounds (12 MP, 30 layers: 8.5 s → 0.09 s). Decoded images are cached; JPEGs decode at reduced scale when shown smaller.
- Previews render a scaled proxy of the document: a 24 MP preview takes ≈0.25 s instead of ≈2.7 s.

**AI providers**
- New Gemini (`gemini-3.1-flash-image`, `gemini-3.8-flash`), Black Forest Labs FLUX (`flux-2-pro`, `flux-pro-1.0-fill`) and Anthropic (`claude-opus-5-5`, official SDK via the `anthropic` extra, server-side refusal fallbacks) adapters.
- OpenAI defaults to `gpt-image-2.5-flare` with multiple-of-16 sizes and `gpt-5-mini` for vision/planning.
- Preset-size providers' images are fitted to the canvas and the original size recorded as `resized_from`. Detection results share one shape. AI plan safety checks run after normalization.

**Evaluation**
- `evals/`: eight design briefs with programmatic checks and reference solutions, a harness that drives the real MCP server, a Claude agent (official SDK), and a manual GitHub workflow for live runs.

**Documentation**
- Add the `skills/vixl` agent skill covering MCP tools, CLI commands, REST routes, the Python API, every operation type, AI providers and tested recipes, updated for this release (check/compare/zoom tools, structured errors, normalization, multi-document sessions, new providers).

**Packaging**
- The version is single-sourced from `vixl.__version__`.

## 0.10.0

- Rename the application to Vixl throughout: `vixl` CLI, `vixl-engine` distribution, `vixl` Python API, and `VixlError`.
- Use `.vixl` documents, `.vixlscript` scripts, `vixl_*` MCP tools, `VIXL_*` environment variables, and Vixl configuration/session paths.
- Brand Windows installers, bundled executables, update manifests, release assets, repository links, documentation, and examples as Vixl.
- Start a distinct Windows installation identity; no legacy command, import, or file-format compatibility aliases are provided.

## 0.9.0

- Add opt-in spacing analysis for equal gaps, expected distances and balanced space before/after an object, with tolerances and structured measurements.
- Add compact palette-indexed pixel layers, integer pixel/line/rectangle/flood-fill tools, named animation frames with timing, and nearest-neighbor GIF/APNG/sprite-sheet export.
- Expose compact pixel/frame inspection and spacing tools through CLI, Python, REST and typed MCP tools; keep frame-save responses free of full snapshots by default in MCP.

- Add editable design operations: groups/clipping, procedural shapes, layer styles, linked typography and swatches, frames, repeats/blends, guides/grids, pathfinder and symbols.
- Add artboards, CSV data-set rendering, layer comps and multi-scale screen exports.
- Add richer gradients, adjustment layers, histogram-based automatic corrections, named 3D LUTs, text box/warp/polyline layout, and read-only pixel/histogram/contrast measurements.
- Expose shared operations through CLI/Python/REST/MCP and AI plans, plus provider-backed Remove, Content-Aware Fill and Select Subject.
- Rebuild the example poster with one repeated stripe clipped to a live ellipse.

## 0.8.0

- Expose canonical operation schemas directly in MCP tools/list, including required fields and enums; no resource fetch needed.
- Return changed layer fields by default; opt into full snapshots with `detail: "full"`. Paginate MCP history and allow inspection of one layer.
- Bound MCP PNG previews to 1024×1024 and 1 MiB by default, with explicit dimension/byte controls and aspect-preserving resizing.
- Add workspace browsing, document creation/opening, path-based image import, and full-resolution file export. Start with `vixl mcp --workspace DIR` without an existing project.
- Replace MCP CLI-string AI dispatch with typed tools for generation, background removal, selection, planning, analysis, upscale, regeneration, and outpainting.
- Keep service projects loaded between calls, detect external file changes, and serialize edits across threads/processes without losing updates. Discard cached state after failed operations/saves.
- MCP migration: `vixl_import_image` now accepts `path` instead of `image_base64`; `vixl_ai` is replaced by the typed `vixl_ai_*` tools. Existing `--project FILE mcp` launch configurations still work, with the project's parent as workspace. CLI/Python AI interfaces remain compatible.

## 0.7.0

- Add a per-user Windows installer with bundled Python, font, REST and MCP dependencies.
- Register a stable `vixl` command in the Windows user PATH; uninstall without removing user projects.
- Check published stable GitHub releases in the background once per day when Vixl starts.
- Verify downloaded runtime checksums, validate archive paths, and health-check side-by-side runtimes before activation.
- Preserve existing sessions and the previous runtime; add manual check/update, opt-out/status, and rollback commands.
- Build installer/update/Python artifacts and publish complete GitHub releases from matching version tags.
- Add Python 3.14 CI and native Windows installer/update/uninstall tests.

## 0.6.0

- Initial programmable image engine with editable projects, CLI/shell, automation, AI provider adapters, REST, and MCP.
