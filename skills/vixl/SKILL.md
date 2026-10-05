---
name: vixl
description: Create and edit layered, editable images with Vixl (the `vixl` CLI, its MCP server, REST API, or Python API). Use whenever a task involves making or changing a poster, flyer, letterhead, business card, social graphic, thumbnail, banner, logo, icon or favicon set, photo edit, template, CSV-driven image variants, brush painting, pixel-art sprite, keyframe animation (GIF/WebP/MP4), print-ready CMYK PDF, slide deck or PowerPoint, carousel, fillable PDF form or form filling from CSV, lyric video, cleaning up and building on a hand drawing, organic shapes (plants, creatures), rich text, guides and grids, color palette, or checking an image's layout, spacing, contrast, print readiness or dimensions — and whenever `vixl_*` MCP tools, `.vixl` files, `.vixlscript` files, or the `vixl` command are available or mentioned. Covers named sizes, principled layouts, the color language, every operation type, CLI command, MCP tool, REST route, AI-provider feature, and the verify-by-preview loop.
---

# Vixl for agents

Vixl is a headless, programmable image-document engine designed for autonomous AI agents; humans can use the same interfaces. A `.vixl` file is a ZIP holding a layer
stack (raster images, text, shapes, groups, pixel grids, adjustment layers…), effects, masks,
constraints, variables, styles, artboards, animation frames and a full branching history. Every
interface — CLI, `.vixlscript`, Python, REST, MCP, AI planner — compiles to the **same canonical
JSON operations**, so anything you learn in one transfers to the others.

Key properties to rely on:

- **Everything stays editable.** Text is text until `rasterize`; effects are a stack you can
  disable/edit/remove; masks and styles are attachments. Prefer editing over re-creating.
- **Batches are atomic.** A list of operations either fully applies or changes nothing.
- **Every successful edit autosaves** and is undoable (CLI and MCP).
- **Layers are addressed by unique name or immutable ID** (`lyr_…`). IDs survive renames;
  prefer them in long sessions. Omitting `target` uses the *active* layer (the last one added/selected).
- **Coordinates are integer-ish pixels, origin top-left**, layers ordered bottom→top.
- **Errors are structured and fail loudly** (`layer_not_found`, `invalid_operation`,
  `validation_failed`, `resource_limit`, `spacing_mismatch`…). Nothing fails silently — except
  the one gotcha listed below.

## Creative and collaborative studio

Read [studio workflows](references/studio.md) for wand/lasso selections, pen handles and
freehand paths, strict/custom palettes and rendered-pixel palette tests, modular containers,
saved shapes, shared project groups, plugin packs, SVG appearance import and HTML export.
Use `vixl_workflow_schema` to discover the consolidated resource/test/effect/group/branch APIs.
For small tool context use `--tools compact --schema slim` (12 tools).

For each new brief, inspect starter suites with resource-list/get and create a custom suite
for its actual requirements. Run it after edits and before export. Freeze allowed colors in
palette regression rules; choose antialias tolerances before checking, not to hide violations.
Use container-reflow after changing copy, then check container-layout. Fork one document per
agent, edit independently, preview branch-merge, resolve conflicts explicitly, then merge.

## New since 0.17

- **Slides and decks** — `page`/`master` operations, speaker notes, `vixl_render_preview(page="all")`,
  `vixl_check(checks=["deck"])`, export `.pdf` (vector, selectable text) or `.pptx` (editable).
- **Forms** — `field` layers, `export_file(fillable=true)`, filling with `values` or the
  `form-fill` workflow, `check form` with `sample="worst"`.
- **Hand drawings** — `drawing` import/clean/vectorize/straighten/fill/stroke; keep the person's
  lines and measure it with `drawing-report` (`preserved`) and `drawing-compare`.
- **Rich text** — `rich-text` (Markdown) and `text-style` for mixed styles and lists in one box.
- **Organic shapes** — `organic` presets and composable generators for living things.
- **Guides beyond right angles** — angled/curved guides, compositional and perspective grids,
  `place`, `snap`, `guides`/`alignment` checks.
- **Lyric videos** — `lyric-video-plan/build/export` workflow actions (song + LRC + template).

Read [documents](references/documents.md) (rich text, pages, forms) and
[drawing, shapes and guides](references/drawing-shapes-guides.md); lyric videos and form-fill jobs
are in [production](references/production.md).

## New in 0.13

The production extension adds `vixl_workflow_schema` and `vixl_workflow` (CLI:
`vixl workflow`). Use them for saved design suites, typed recipes, checked actions,
variation matrices, reusable motion, draft/final renders, component libraries, durable
jobs and shot-based films. Read [production workflows](references/production.md)
for the schemas and limits. View the initial design; use saved suites on routine edits
and inspect failed/uncertain checks and material visual changes. A clean check report
certifies only its explicit rules and time coverage. Never weaken a suite as a repair.
Use submit/start/status for long jobs. An uncertain external generation request must
not be blindly repeated; preserve its remote job identity.

- **Named sizes** — `vixl_document_create(size="letter", bleed=true)` / `vixl new business-card --bleed`; 150 print, social, web, ad, video, slide, icon and logo sizes with dpi, bleed, safe area and guides.
- **Layouts** — 33 principled, seed-varied layouts (`layout-apply`) that adapt to the canvas and set up contrast-checked color roles, a type scale and grids. Use them when a brief gives you free rein. They are fill-in-the-blank forms: `vixl layout show NAME` / `vixl_layouts_list` lists each layout's slots and what each needs. Fill them all; an unfilled slot renders as a `[Label]` blank that `check` reports as an error, and a slot the layout doesn't use is rejected rather than silently dropped. Templates work the same way.
- **Typefaces** — the bundled font is a proofing fallback (`check` warns about it). Pick real type from a researched catalog of open-licensed families and curated heading/body pairings: `vixl font pairings --mood editorial` / `vixl_fonts`, then `vixl font pair NAME|random` / `vixl_font_pair` downloads, embeds and sets them as the document typography that layouts use. `vixl font principles` explains how to combine fonts.
- **Dice** — when the brief is thin, roll instead of defaulting: `vixl roll --for poster` / `vixl_roll` picks a pairing, a mood-consistent palette, a layout and its parameters from one seed; layouts and templates accept `seed: "random"`. Roll a few, preview, keep the seed you like, and `--lock` choices you want fixed.
- **Color language** — `oklch()`, `lab()`, `cmyk()`, `color(display-p3 …)`, `kelvin()`, `color-mix()`, `lighten(@brand, 10%)` … everywhere; `vixl_color` for harmonies, scales and contrast; `palette-generate`.
- **Print** — CMYK PDF/TIFF/JPEG (ICC profile or GCR + ink limit), PDF, ICO, icon sets, dpi, soft proofs, color-blindness simulation, `print` and `color_vision` checks.
- **Brushes** — editable paint layers with 17 brushes (`paint`, `paint-layer`, `brush-define`).
- **Timelines** — keyframes, easing, presets and markers on any layer property; preview a frame or a contact sheet; export GIF/APNG/WebP/sheet/PNG frames/MP4.

See [design-system.md](references/design-system.md) (sizes, layouts, color, print), [typography.md](references/typography.md) (catalog, pairings, installs, rolls) and [brushes-timeline.md](references/brushes-timeline.md).

## New in 0.11

Discover commands with `vixl commands --json` and shape shortcuts with `vixl shapes`. Command help works without an open document. CLI edits now default to compact results; add `--detail full` for snapshots. Use named palettes, built-in/custom templates, overall/style guidance, explicit HTTPS/local fonts, expanded shapes and Bézier paths. SVG retains supported shapes, gradients, groups, pixels, boolean silhouettes and shaped Unicode text and common effects/styles as vectors; strict SVG policy rejects embedded raster content with layer/effect details. See [local artistic filters](references/artistic-filters.md) for 19 deterministic treatments, defaults and ranges; no AI provider is needed. PNG preserves transparency; JPG flattens against an explicit background.

See [resources](references/resources.md) for the new MCP tools and CLI/operation examples. Discover authenticated provider models with `vixl models --refresh` or `vixl_models_list`; native Anthropic/Gemini and OpenAI-compatible Mistral/Meta join the existing providers. Midjourney requires an authorized HTTP gateway, not a fabricated official API.

## Workspace review and brands

Prefer `vixl mcp --workspace . --tools core --schema slim`; fetch operation details with
`vixl_operation_schema`. HTTP clients can use `--http` at `/mcp` with the configured bearer token.
Read `vixl_review_notes` before revising a document and resolve notes after addressing them.
Humans can follow progress with `vixl -p DOCUMENT view`.

Workspace `brand.json` provides default palette roles, pairing/embedded fonts, embedded logos,
minimum contrast, and required layer names. Layouts, templates, rolls and checks honor it.
Use `vixl_roll(apply=true, slots={...})` or `roll --apply --set title=...` to apply a whole direction;
`layout apply` returns unfilled slots immediately. Check and fill them before export.
`vixl_import_document` imports editable SVG paths or a raster PDF page. Unsupported SVG
features return an error; convert them to plain paths before retrying.

## 1. Pick the interface

| You have… | Use | Reference |
| --- | --- | --- |
| `vixl_*` tools in your tool list | **MCP** — typed tools, compact diffs, inline previews | [references/mcp-rest-python.md](references/mcp-rest-python.md) |
| A shell with `vixl` on PATH | **CLI** (add `--json` for machine errors) or `vixl apply ops.json` | [references/cli.md](references/cli.md) |
| Python with `vixl` importable | `from vixl import Project` | [references/mcp-rest-python.md](references/mcp-rest-python.md) |
| A running `vixl serve` | REST (`POST /operations`, `GET /render`) | [references/mcp-rest-python.md](references/mcp-rest-python.md) |

Whatever the interface, the edit payload is the operation list in
[references/operations.md](references/operations.md). Load that file before composing
non-trivial batches. Ready-made multi-step workflows are in [references/recipes.md](references/recipes.md).
AI-provider features (generate, inpaint, segmentation, OCR, plan) are in
[references/ai.md](references/ai.md).

Check availability first: `vixl --version` (CLI) or call `vixl_workspace_list` (MCP). Install from
source with `pip install -e ".[server,mcp]"` (Python ≥ 3.11); Windows users use the installer.
Set `VIXL_NO_UPDATE=1` in automation so the Windows auto-updater never runs mid-task.

**`vixl` not found? Look before asking the user.** A session started before installation keeps
its old PATH. Try, in order: `%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe` (Git Bash:
`"$LOCALAPPDATA/Programs/Vixl/bin/vixl.exe" --version`; PowerShell:
`& "$env:LOCALAPPDATA\Programs\Vixl\bin\vixl.exe" --version`), the alias
`%LOCALAPPDATA%\Microsoft\WindowsApps\vixl.exe`, then `python -m vixl --version` (pip installs).
If found, prepend its folder to PATH for this session — see
[references/cli.md](references/cli.md#finding-vixl).

## 2. The core loop (do this every time)

0. **Start right** — for a new piece, create it from a named size (`size="instagram-portrait"`,
   `"letter"` with `bleed`, `"favicon"`, `"logo-horizontal"` …) rather than guessed pixels. If the brief
   is open-ended, apply a fitting layout (`layout-apply`) and refine it instead of improvising a
   composition from scratch. Choose a font pairing first (`font pair`), fill every slot the layout
   lists with real copy, and when the brief leaves the look open, roll (`roll`, `seed: "random"`) a few
   times and compare previews. To fill blanks after a first pass, re-apply with the copy,
   `replace: true` and the reported `seed` so the composition stays the same.
1. **Orient** — inspect before editing. MCP: `vixl_document_inspect()` returns a compact summary
   (one line per layer with `bounds`; `detail="full"` for every field, `target=` for one layer).
   CLI: `vixl -p F.vixl inspect --json` / `vixl layers`. Note canvas size, layer names/IDs and
   bounds (`[x, y, width, height]` after constraints).
2. **Plan a batch** of canonical operations. Group related edits into one atomic call.
3. **Dry-run anything risky** (`dry_run: true` / `vixl apply ops.json --dry-run`). It returns the
   changes without saving.
4. **Apply.** Read the returned change summary — new layers come back with ID, name, type and
   `bounds`; changed layers list only their new values. If it contains `normalized`, note the
   canonical spelling it reports and use that next time.
5. **Check without looking:** `vixl_check` / `vixl check` reports content cut off by the canvas,
   overlapping text, low WCAG contrast, safe-area or reserved-zone violations (`safe_area="5%"`,
   `avoid=[[x,y,w,h]]`) and text too small at thumbnail width (on print sizes: below 6 pt). It lists only problems.
6. **Look at the result.** MCP: `vixl_render_preview()` returns an image (≤1024 px, ≤1 MiB by
   default; `region=[x,y,w,h]` zooms in). `vixl_render_compare()` shows previous vs current.
   CLI: `vixl render --out /tmp/preview.png` then view the file. Never declare a visual
   task done without looking.
7. **Measure, don't eyeball,** when precision matters: `vixl_measure` / `vixl info` (colors,
   WCAG contrast of a text layer), `vixl_measure_spacing` / `vixl spacing` (gaps),
   `vixl_validate` / `vixl validate` (bounds, aspect ratios, assertions).
8. **Fix with targeted edits or `undo`**, then **export** (`vixl_export_file` / `vixl export`).

## 3. Minimal examples

**MCP**

```text
vixl_workspace_list()                                   # see files; paths are relative to the workspace
vixl_document_create(path="poster.vixl", width=1080, height=1350, background="#101828")
vixl_import_image(path="photos/portrait.jpg", name="portrait")
vixl_operations_apply(operations=[
  {"type":"resize","target":"portrait","width":1080},
  {"type":"align","target":"portrait","alignment":"top"},
  {"type":"gradient","name":"fade","width":1080,"height":600,"y":750,
   "stops":[{"offset":0,"color":"#10182800"},{"offset":1,"color":"#101828"}]},
  {"type":"text","name":"title","text":"AFTER HOURS","size":120,"color":"#f6ecd7"},
  {"type":"constrain","target":"title","constraints":{"center-x":"canvas.center-x","bottom":"canvas.bottom-120"}},
  {"type":"layer-style","target":"title","name":"drop-shadow","settings":{"blur":8,"dy":6,"opacity":0.6}}
])
vixl_check(safe_area="5%")                              # overlap, contrast, bounds, legibility
vixl_render_preview()
vixl_export_file(path="poster.png")
```

**MCP, from a brief** ("make a launch post for our spring collection")

```text
vixl_document_create(path="spring.vixl", size="instagram-portrait")
vixl_font_pair(pairing="random", mood="friendly")             # heading + body fonts become the document typography
vixl_operations_apply(operations=[{"type":"layout-apply","name":"split-screen","title":"Spring collection",
  "subtitle":"New colors, same perfect fit.","label":"Just landed","cta":"Shop now","palette":"spring","seed":11}])
vixl_import_image(path="photos/hero.jpg", name="hero")       # returns {"asset": "assets/…", …}
vixl_operations_apply(operations=[{"type":"replace-contents","target":"image","asset":"assets/…"},
  {"type":"remove","target":"hero"}])                         # the photo now fills the layout's frame
vixl_check() ; vixl_render_preview() ; vixl_export_file(path="spring.png")   # check fails while blanks remain
```

**CLI** (quote `#` colors; every edit autosaves)

```bash
vixl new 1080x1350 --background '#101828' -o poster.vixl
vixl -p poster.vixl add photos/portrait.jpg --name portrait
vixl -p poster.vixl resize portrait --width 1080
vixl -p poster.vixl text add 'AFTER HOURS' --name title --size 120 --color '#f6ecd7'
vixl -p poster.vixl constrain title --center-x canvas --bottom canvas.bottom-120
vixl -p poster.vixl layer-style title drop-shadow --settings '{"blur":8,"dy":6,"opacity":0.6}'
vixl -p poster.vixl render --out preview.png
vixl -p poster.vixl export poster.png
```

Or put the operations in a file and run `vixl -p poster.vixl apply ops.json` (atomic, one undo step).

## 4. Rules and gotchas that save retries

- **Always pass the project explicitly in the CLI** (`-p file.vixl`). `vixl open` stores a
  per-directory default in `.vixl-session.json`, which is fragile across concurrent work.
- **CLI edits default to compact output** with changed values and layer IDs. Use `--detail full`
  for complete before/after snapshots. MCP/REST also default to `detail:"compact"`.
- **CLI JSON is ASCII-escaped UTF-8**, so Unicode names and normalization notes survive Windows
  redirected output. Parse JSON normally; escapes decode to the original text.
- **Errors are structured.** MCP tool errors and CLI `--json` failures are
  `{"error": CODE, "message", "field", "operation_index", "operation_type", "allowed"?, "suggestions"?}`.
  Fix the named operation and field (try a suggestion) and retry; a failed batch changed nothing.
- **Common spellings are accepted and reported** under `normalized`: `rect`/`circle`/`triangle`,
  `font_size`, `fill`/`color`, camelCase keys, `drop_shadow`, CSS `rgba(…, 0.5)`, blur `radius`.
  `x`/`y` take pixels, `"center"` or `"50%"`; `width`/`height` take pixels or `"25%"` (of the canvas,
  or of the parent group).
- **Blur strength is `amount`** (`{"type":"effect","name":"blur","amount":4}`); `radius` on blur is
  read as `amount`. `radius` is its own field for `vignette` (0–1.4) and `rounded-rectangle` corners.
- **Opacity is 0–1; values from 1 to 100 are read as a percentage** in every interface (`50` = 0.5).
- **Scale `value` is a factor** (`0.8`); CLI accepts `80%`.
- **Absolute `move` and `align`/`distribute` clear constraints** on that layer. Use `constrain`
  when layout should survive canvas resizes, artboards or text changes; use `align` for a one-off.
- **One constraint per axis** (e.g. `left` *or* `center-x` *or* `right`). Anchors: `canvas`, a layer
  name/ID, or `guide:NAME`, plus `.left/.right/.top/.bottom/.center-x/.center-y` and `+N`/`-N`.
- **Effects capture the selection that exists when they are added.** Clear it
  (`{"type":"select","shape":"none"}`) before adding whole-layer effects.
- **Palettes and fonts recolor/re-font by role:** `palette-apply` sets `@background`/`@ink`/`@accent`…,
  and `font pair` updates text whose `font` is `heading`/`body` (templates use roles). Literal colors
  and named fonts stay as they are.
- **Text auto-sizes** to its rendered bounds; an explicit `resize` turns that off, editing text turns it back on.
  For wrapping use `text-layout` with `width`/`height` (optionally `fit: true`).
- **Variables:** `${name}` works in text, colors, gradient fills and image-asset IDs. Undefined
  variables are errors. Swatches are `@name` in color fields.
- **Through MCP/REST, operation `path` and `linked` fields are rejected, and `font` takes only a registered
  font name or role (`heading`/`body`; install with `font pair`/`font install` first).** Import files with
  `vixl_import_image(path=…)` or, when you only have the bytes, `vixl_import_image(data_base64=…)`
  (MCP) or `POST /assets` (REST); reuse already-embedded images via `asset` IDs.
- **MCP may run as two servers:** `vixl` (`--tools core`) for editing and export, `vixl-ai`
  (`--tools ai`) for provider-backed `vixl_ai_*` tools. They share the workspace; edits made in one are
  seen by the other on its next call.
- **Several documents can be open over MCP.** Pass `document="other.vixl"` to any tool to address one
  without changing the active document.
- **MCP paths are relative to the server's `--workspace`**, must stay inside it, and subdirectories
  must already exist. Exports refuse to overwrite unless `overwrite: true`, and never overwrite `.vixl`.
- **CLI `new` and `export`/`render --out` refuse existing destinations** in batch/data/animation
  workflows; choose fresh names.
- **Pixel art:** export with `--sampling nearest` (`sampling:"nearest"` in MCP) or it will be smoothed.
- **AI features need a configured provider** (`~/.config/vixl/providers.json`). There is no
  offline fallback; if no provider is configured, say so instead of retrying.
- **Small accent text uses `@accent-text`**, not `@accent` (fills and large type only need 3:1; small
  text needs 4.5:1). Layouts already do this.
- **Character rigs:** set each limb's `pivot` at its joint (`{"type":"pivot","target":"arm","value":"top"}`)
  before animating `rotation`; group parts that move together; give several parts the same keys with
  `targets`. Keep GIFs small with `colors` and a lower `fps`.
- **Animate with `translate-x/y` and `scale`** so constrained layouts keep working; the saved document
  is the frame at rest, and `time=` previews or exports a moment.
- **CMYK is an export setting** (`color_space="cmyk"` for PDF/TIFF/JPEG). Pass the printer's ICC profile
  when exact separations matter; without one Vixl uses a GCR approximation with an optional ink limit.
- **Limits:** 40 MP per canvas/layer, 16 384 px per side, 512 layers, 256 effects/layer,
  1 000 operations per batch. History keeps 2 000 revisions; older unreferenced ones are squashed
  automatically, so long sessions never lock. Pixel-art frames ≤ 256×256, ≤ 256 frames; timelines
  ≤ 10 min, 60 fps, 3 600 frames; 4 096 strokes per paint layer.
- **Not supported** (don't promise them): arbitrary SVG import, path arcs/multiple contours,
  skew/perspective, CMYK *editing* or spot colors, live tablet input, audio, RAW, PSD/XCF import, GUI.

## 5. Feature map (where to look)

| Need | Operations / commands |
| --- | --- |
| Start | named sizes (`canvas` `size`, `vixl new NAME`, `vixl_document_create(size=)`), `layout-apply`, `type-scale`, `palette-generate`, `guidance` |
| New layers | `add` (image), `solid`, `gradient` (linear/angled/radial, multi-stop), `text`, `shape`, `frame` (image box with fill/fit), `pixel-art`, `paint-layer`, `adjustment`, `symbol-instance` |
| Transform | `move`, `resize`, `scale`, `rotate`, `flip`, `crop`, `opacity`, `blend`, `hide`/`show` |
| Stacking | `raise`, `lower`, `top`, `bottom`, `reorder` (`above`/`below`), `group`/`ungroup`, `clip` |
| Layout | `align` (to canvas/selection/layer), `distribute`, `constrain`/`unconstrain`, `guide`, `grid`, `canvas` (resize/preset), `artboard` |
| Color & filters | 25 built-in effects (brightness … auto-contrast), `effect-set/enable/disable/remove`, `lut` + `lookup`, `preset-save/apply` |
| Selections & masks | `select` (rect/ellipse/color/alpha/all/none/invert, add/subtract/intersect, feather), `mask` (create/from-selection/import/invert/enable/disable/delete) |
| Typography | `text`, `text-set`, `text-layout` (box, fit, warp, path), `style-define`/`style-apply`, `swatch` |
| Decoration | `layer-style` (drop-shadow, stroke, outer-glow, color-overlay, gradient-overlay), `repeat`, `repeat-blend`, `pathfinder` |
| Templates | `variable`, `replace-contents`, `comp-save`/`comp-apply`, CSV `render --data`, `export-screens` |
| Painting | `paint` (17 brushes, points or SVG path, pressure, erase), `paint-clear`, `brush-define` |
| Motion | `timeline-set`, `keyframe`, `keyframe-remove`, `animate`, `animate-preset`, `marker`; `vixl_timeline_preview`, `vixl_export_timeline` |
| Pixel art & sprite frames | `pixel-art`, `pixel-draw`, `pixel-palette`, `frame-save/apply/delete`, `animation-set`, `export-animation` |
| Color & print | color language in every color field, `vixl_color`, CMYK/PDF/ICO export, `vixl_export_icons`, proof/simulate previews, `print`/`color_vision` checks |
| History | undo/redo, checkpoint, branch, checkout, compare, transactions |
| QA | check (bounds/overlap/contrast/safe area/legibility; opt-in print, color_vision), inspect, measure (sample/histogram/contrast), spacing, validate/assert, render preview (zoomable, time, proof, simulate), compare revisions |
| AI (provider) | generate/inpaint/img2img, extend (outpaint), upscale, regenerate, background-remove, select object/subject, remove, content-aware-fill, describe/detect/OCR, natural-language plan |

When unsure of a field, get the authoritative schema: MCP embeds it in `vixl_operations_apply`'s
input schema (also resource `vixl://operations`); CLI `vixl schema`; REST `GET /schema`; per-command
syntax via `vixl COMMAND --help`.
