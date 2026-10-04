# Changelog

## Unreleased

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
