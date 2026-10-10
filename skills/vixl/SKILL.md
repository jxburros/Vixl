---
name: vixl
description: Create and edit layered, editable images with Vixl (the `vixl` CLI, its MCP server, REST API, or Python API). Use whenever a task involves making or changing a poster, flyer, letterhead, business card, social graphic, thumbnail, banner, logo, icon or favicon set, photo edit, template, CSV-driven image variants, brush painting, pixel-art sprite, keyframe animation (GIF/WebP/MP4), print-ready CMYK PDF, slide deck or PowerPoint, carousel, fillable PDF form or form filling from CSV, lyric video, cleaning up and building on a hand drawing, organic shapes (plants, creatures), charts and infographics from data, mascots, illustrations, scenes, patterns or mandalas, design styles (swiss, brutalist, art deco, kawaii …), finishing looks (glow, shadow, grain), rich text, guides and grids, color palette, or checking an image's layout, spacing, contrast, print readiness or dimensions — and whenever `vixl_*` MCP tools, `.vixl` files, `.vixlscript` files, or the `vixl` command are available or mentioned. Covers named sizes, principled layouts, the color language, every operation type, CLI command, MCP tool, REST route, AI-provider feature, and the verify-by-preview loop.
---

# Vixl for agents

Vixl is a headless, programmable image-document engine designed for autonomous AI agents; humans can use the same interfaces. A `.vixl` file is a ZIP holding a layer
stack (raster images, text, shapes, groups, pixel grids, adjustment layers…), effects, masks,
constraints, variables, styles, artboards, animation frames and a full branching history. Every
interface — CLI, `.vixlscript`, Python, REST, MCP, AI planner — compiles to the **same canonical
JSON operations**, so anything you learn in one transfers to the others.

Key properties to rely on:

- **Everything stays editable.** Text is text until `rasterize` (or `merge-layers` / `flatten`, which
  bake several layers into one); effects are a stack you can disable/edit/remove; masks and styles are
  attachments. Prefer editing over re-creating.
- **Batches are atomic.** A list of operations either fully applies or changes nothing.
- **Every successful edit autosaves** and is undoable (CLI and MCP).
- **Layers are addressed by unique name or immutable ID** (`lyr_…`). IDs survive renames;
  prefer them in long sessions. Omitting `target` uses the *active* layer (the last one added/selected).
- **Coordinates are integer-ish pixels, origin top-left**, layers ordered bottom→top.
- **Errors are structured and fail loudly** (`layer_not_found`, `invalid_operation`,
  `validation_failed`, `resource_limit`, `spacing_mismatch`…). Nothing fails silently — except
  the one gotcha listed below.

## Start here (the default path)

For any new piece, and above all an open-ended brief ("make a few cool things"), follow this order
instead of improvising freehand shapes:

1. **What am I making?** `vixl_guide(brief)` (CLI `vixl guide a mascot for a coffee brand`) maps a brief
   to its kind (poster, social card, logo, icon, character, scene, pattern, mandala, diagram, slides …)
   and returns the operations, layouts, looks and styles that suit it, with a working example.
   `vixl_guide(brief="operations")` lists every operation by purpose. Layouts are *text compositions*:
   ten requests for different things are not ten posters. Icons, characters, scenes and patterns are
   built from `shape`, `pen`, `pathfinder`, `organic` and `radial-repeat`; characters are grouped parts
   with a `pivot` at each joint, patterns scatter motifs rather than tile a grid, and animation loops
   are `motion` recipes (`period`, several `targets`, `stagger`). A kind names the guidance to read:
   `vixl_guide(brief="looping-motion")` (or `natural-motion`, `character-rigging`, `imperfection` …)
   returns the text.
2. **Layout** — `vixl_sizes_list` → `vixl_document_create(size=…)` (or `purpose="social"|"slides"|"logo"…`, which
   picks the size; with neither it is 1080×1080). For anything with text,
   `vixl_layouts_list` → `layout-apply`, filling every slot it lists. An unfilled image slot comes back
   with `next_steps` (import, resource, draw, or AI) and its bounds.
3. **Fonts** — creation installs the rolled pairing when the font cache or network is available (`creation.fonts`
   says so); otherwise, or to choose, `vixl_fonts` → `vixl_font_pair` (the bundled font is a proofing fallback).
4. **Finish** — apply a `look` (glow, soft-shadow, hard-shadow, gradient, grain, paper …) so flat shapes
   read as finished work; when the brief names a style (swiss, brutalist, art-deco, kawaii …) use
   `vixl_styles` and `style-set`, then `check --checks style`.
5. **Test, then look** — write the brief's requirements as a check suite before you build (below), run
   it with `vixl_check` while you build, and only preview a design that passes: `vixl_check` (fix the
   `fix` findings, glance at `review`, accept `informational` ones; mark a deliberate edge crop with
   `layer-intent` `allow_crop`) plus your suite, then `vixl_render_preview` → `vixl_export_file`.
   `vixl_operations_apply(..., check=true, suites=true, preview=true)` returns the findings (the
   batch's layers plus every `fix`), the suite rules that did not pass and a small preview with the edit
   itself, so the loop is one call.

## Tests: why, when and how

A preview is a small, downsampled picture; you cannot see a 1 px crop, a 4.2:1 contrast or gaps of 20
and 24 px in it, and the next batch can quietly undo a fix. Tests measure those exactly and keep
measuring as edits pile up. Use them for what can be measured and the preview for what cannot (taste,
likeness, mood). `vixl_guide("testing")` is the full method; every `vixl_guide(kind)` answer has a
`tests` plan (a starter suite and rules to adapt).

1. **Before building**, turn each requirement of the brief into a rule and attach the suite in the
   first batch (`suite-set`), or start from a starter suite (`vixl_workflow("suite-use", {name})`):
   `social-card`, `composition`, `slide-deck`, `logo`, `motion-loop`, `character`, `fillable-form`,
   `diagram`, `print-ready`, `accessible`, `delivery`, `palette`, `opaque`, `no-placeholders`, `containers`.
2. **While building**, pass `check=true, suites=true` to `vixl_operations_apply`; fix failures as they appear.
3. **Before every preview and export**, run `vixl_check` and `vixl_workflow("check", {suite: NAME})`
   (or an inline suite object); preview once they pass.
4. **A failing rule means change the design.** Never loosen a rule or its tolerance to pass; pick
   tolerances when you write the rule. Use `severity: "warning"` for preferences.

| Requirement | Rule |
| --- | --- |
| Headline clearly dominates | `{kind: hierarchy, targets: [title, subtitle, body], ratio: 1.25}` |
| Text readable | `{kind: contrast, target: title, minimum: 4.5}`, `{kind: text-fit, target, minimum}` |
| Evenly spaced cards | `{kind: spacing, targets: [card-1, card-2, card-3], axis: horizontal}` (`expected` for an exact gap) |
| Logo 48 px from the edges | `{kind: relation, target: logo, to: canvas, position: inside, minimum: 48}` |
| Caption under the photo, left-aligned | `{kind: relation, target: caption, to: photo, position: below, align: [left], maximum: 24}` |
| Price never touches the product | `{kind: relation, target: price, to: product, position: apart, minimum: 8}` |
| Quiet area for the headline | `{kind: ink, region: [x, y, w, h], maximum: 0.02}` |
| Balanced / subject on a thirds point | `{kind: balance, tolerance: 0.1}`, `{kind: focal, target: subject, grid: thirds}` |
| Brand colour exact | `{kind: color, point: [x, y], expected: "@brand"}` or `palette` |
| Exactly three bullets, no text on an icon | `{kind: count, target: "bullet-*", minimum: 3, maximum: 3}`, `{kind: count, layer_type: text, maximum: 0}` |
| A finished part must not change | `suite-capture` (unchanged and pixels rules) |
| Holds through an animation | add `sampling: {mode: sampled, count: 8}` |

Each result carries the measurement (gaps, margins, ratio, centre, colour), so a failure says what to
change. A rule that cannot be measured (a missing layer) is `needs_review`, never a pass, and a
passing suite proves only its own rules. Rule fields: `vixl_workflow_schema().definitions.suite`.

**One call for a new piece.** When you already know the size, layout slots, look and operations,
`vixl_compose(path, size=…, font_pairing=…, layout={name, …slots}, style=…, look={…}, operations=[…],
check=true, preview=true, exports=[…])` (CLI `vixl compose --request req.json --preview p.png`) runs steps 1–5
atomically: nothing is saved or exported unless every step succeeds, and an error carries `step`
(request, create, fonts, layout, style, look, operations, check, preview, save, export). `strict=true` refuses to
save while `check` has `fix` findings; `dry_run=true` builds, checks and previews without writing. Layout `image`/`images`
take workspace paths or https URLs (one-call memes); `background` survives the layout; `style` sets the layout's
alignment and palette and installs its font pairing where you left them open. Keep editing the result with
`vixl_operations_apply`.

## Creative and collaborative studio

Read [studio workflows](references/studio.md) for wand/lasso selections, pen handles and
freehand paths, strict/custom palettes and rendered-pixel palette tests, modular containers,
saved shapes, shared project groups, plugin packs, SVG appearance import and HTML export.
Use `vixl_workflow_schema` to discover the consolidated resource/test/effect/group/branch APIs.
For small tool context use `--tools compact --schema slim` (13 tools).

For each new brief, inspect starter suites with resource-list/get and create a custom suite
for its actual requirements (see Tests above). Run it with every batch (`suites=true`), before every
preview and before export. Freeze allowed colors in
palette regression rules; choose antialias tolerances before checking, not to hide violations.
Use container-reflow after changing copy, then check container-layout. Fork one document per
agent, edit independently, preview branch-merge, resolve conflicts explicitly, then merge.

## Emoji artwork

Read [emoji workflows](references/emojis.md) for the offline Unicode 17 catalog, editable source masters, custom replacements and shortcodes, templates and destination-ready image packs. Use `vixl_workflow` actions `emoji-list`, `emoji-get`, `emoji-template`, `emoji-replace`, `emoji-pack-install`, `emoji-settings`, `emoji-reset`, `emoji-requirements`, `emoji-destinations` and `emoji-export`; their typed fields come from `vixl_workflow_schema`. Bundled VIXL artwork is the default; `mode: "font"` (operation `emoji-mode` or workflow `emoji-settings`) prefers the font, with bundled art for sequences it cannot shape.

## New in 0.24: reliability and reusable delivery

- **Checks** — `passed` is false while any finding has action `fix`, warnings included; `by_action` lists the issue
  indexes under fix / review / informational. An explicit `checks` list replaces the default set, so narrow it only on purpose.
- **Text and layout** — width-only text boxes regrow after edits and variable substitution (fixed-height boxes still need
  an overflow check). `adapt-layout` with `recompose: true` rebuilds a stored layout recipe at the new size and may
  replace manual edits and generated layer IDs; proportional adaptation stays the default.
- **Source folders** — `vixl unpack design.vixl design-source` writes the current state as stable JSON (`project.json`,
  with asset hashes) plus asset files (no history; registered fonts kept); `vixl pack design-source out.vixl` validates and rebuilds it. See
  [cli](references/cli.md).
- **App delivery** — `vixl_workflow("app-animation-package", {states, default_state, output, themes?, transitions?, format?})`
  writes named states, light/dark variables, transitions, reduced-motion PNGs, editable masters, a manifest and an HTML
  consumer. `screen-capture` (`{output, bbox? | window?, all_screens?}`) is an explicit local desktop capture, not
  rendering. See [production](references/production.md).
- **Motion** — `character-pose` with `time` (and `easing`) keys joint angles and solves the rig every frame; don't add
  separate limb x/y/rotation keys. In house-style-3 documents a new timeline of 10 s or less is a seamless loop: pass
  `loop_mode: "off"` or `loop: 1` for play-once. `animate` `intent` (entrance, exit, loop, emphasis) picks the house
  easing. Templates `video-tip`, `video-launch`, `video-event` build editable six-second loops (title/subtitle/cta).
  See [brushes and timeline](references/brushes-timeline.md).
- **House style 3** — 16 more font pairings (76), weighted alignment, saturated backgrounds kept. Documents keep the
  version they were created with; replay 0.23 rolls with `vixl roll --house-style 2` or `{"house_style": 2}` in
  `.vixl/variety.json`. Explicit fields and saved geometry win. Minor social/poster text must be at least 2.2 % of
  the short side; bold text counts as large from 18.66 px (regular from 24 px).
- **Spacing units** — `stack` and `layout-apply` `gap` accept `"2u"` (CLI `--gap 2u`; 1u = half the body size); new house-style
  stacks default to 2u.
- **Brushes and frames** — paint `settings` `drip` (0–4 brush sizes), `relief` (0–1) and `light_angle` (degrees,
  default -45); `frame` `frame_shape` (rectangle, ellipse, star, hexagon, heart) or a closed SVG `outline` in
  frame-local pixels; keep the canvas transparent for a shaped image.

## New in 0.22

- **`vixl_compose`** — the whole start-here chain in one atomic call (above); REST `POST /compose` is a dry run.
- **Logo packages** — `vixl_workflow("logo-package", {output, mark?, wordmark?, …})` turns a logo (open document,
  `.vixl`, PNG/JPEG/WEBP or SVG; `trace: true` vectorizes a raster) into full-colour, mono black, mono white,
  on-light and on-dark variants, optional mark/horizontal/stacked lockups, strict SVG, RGB (+ CMYK) PDF, PNG at
  1x/2x/3x, icons with favicon, social avatar and Open Graph images, `usage.html` and an optional zip. Recolouring is
  heuristic: read `report`. There is no EPS export: hand over the PDF or SVG.
- **Proof pages** — `vixl_workflow("proof", {items, output, decisions?})` writes one offline HTML page to review
  documents and exports (thumbnails, metadata, check findings, before/after, approve/reject saved as a JSON download).
- **`vixl diff A B --out d.png`** — pixel-diff two documents or images (changed pixels, fraction, region).
- **Memes** — `meme-top-bottom`, `meme-caption-above`, `meme-comparison`, `meme-labelled`, `meme-reaction`,
  `meme-four-panel` layouts (`images` takes one asset per panel); `vixl_guide("meme")`. Bring your own images.
- **CI** — the repository's GitHub Action checks `.vixl` files on pull requests (`docs/ci.md` in the Vixl repository).

## New since 0.17

- **Slides and decks** — `page`/`master` operations, speaker notes, `vixl_render_preview(page="all")`,
  `vixl_check(checks=["deck"])`, export `.pdf` (vector, selectable text), `.pptx` (editable) or
  `.html` (a one-file presentation with speaker view).
- **Forms** — `field` layers (rules such as `format`, `pattern`, `max_length` become PDF actions),
  `export_file(fillable=true)`, filling with `values` or the `form-fill` workflow, `check form` with
  `sample="worst"` (each overflow reports what it measured).
- **Hand drawings** — `drawing` import/clean/vectorize/straighten/fill/stroke; keep the person's
  lines and measure it with `drawing-report` (`preserved`) and `drawing-compare`.
- **Rich text** — `rich-text` (Markdown) and `text-style` for mixed styles and lists in one box. `text-set` changes the
  whole layer (text, color, size, font) and keeps bullets and span styles that still apply; read the result's `warnings`.
- **Baselines** — `baseline_y` on `text`/`text-set`/`move` places the first line's baseline; `align` with
  `alignment: "baseline"` and `snap` with `anchors: ["baseline"]` (onto a baseline grid) line text up by baseline.
- **Text flow** — `text-flow` threads a long text through linked frames (columns, pages, shapes); results report `overflow`.
- **Diagrams** — `diagram-from-text` / `diagram` / `diagram-set` draw flowcharts, dependency graphs, org charts and mind maps
  as editable layers (swimlanes, auto-fit, `check diagram`).
- **Organic shapes** — `organic` presets and composable generators for living things.
- **Scatter and seamless tiles** — `scatter` (Poisson-disc copies inside or along a layer's outline, seeded jitter,
  `merge` for one path per tone, `preset: fur`), `pattern-scatter` (wrap-around tile with a seam score), per-step
  and jittered `repeat`/`radial-repeat` (`vixl_guide("scatter")`).
- **Imperfection** — opt-in `irregular` (seeded wobble, stroke weight, color drift, micro placement)
  and `tear` (torn edges) for characters, stickers, scenes, scattered patterns, hand-made looks and
  ripped paper; never for logos, charts, text or anything that must align (`vixl_guide("imperfection")`). `arc` shapes draw pie wedges and donut segments; `closed: false` draws just the stroked curve.
- **Shape parameters and content boxes** — shortcut shapes take their own parameters (heart `apex`/`cleft`/`tip`,
  speech-bubble `pointer_side`/`pointer_position`/`pointer_size`/`body`, shield `depth`, `slant`, chevron
  `thickness`; `vixl_capabilities("shapes")` lists all). Shapes report `content_bounds` (a bubble's body, a
  badge's centre, a screen): put text there with `text` `within`, `place` `within` or `align` `box: "content"`.
- **Charts** — `chart` (bar, stacked, 100 %, horizontal, line, area, pie, donut) from a table or workspace CSV, `chart-data` to fix
  a value on stable layer IDs, native PPTX charts; see [charts](references/charts.md) before drawing any chart by hand.
- **Guides beyond right angles** — angled/curved guides, compositional and perspective grids,
  `place`, `snap`, `guides`/`alignment` checks.
- **Lyric videos** — `lyric-video-plan/build/export` workflow actions (song + LRC + template).
- **Linked documents** — `link` layers render another `.vixl` live (derived crops, pattern previews, sheets); `links` reports
  stale/missing sources, `link-embed` freezes one. See [production](references/production.md).
- **Print merge** — `merge-impose` lays CSV rows out on print sheets with crop marks: vector-text PDF plus an editable sheet.
  Placeholders take filters: `${name|upper}`, `${company|default:Independent}`, `${state|map:states}` (`variable-map`).
  `$${name}` writes a literal `${name}`.
- **QR codes and barcodes** — `qr` and `barcode` (Code 128, EAN-13) are vector shapes in every export; `data` may use
  `${variables}` for merges; `check codes` flags small modules, low contrast and ink in the quiet zone.

Read [documents](references/documents.md) (rich text, pages, forms), [charts](references/charts.md) and
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
- **New documents** — every surface (`vixl new`, `Project()`, `vixl_document_create`, compose) rolls and stores `design_defaults` (`seed`/`--seed`, `variety`/`--variety` reproduce them), gives the canvas the palette background (transparent for logos, icons and favicons; pass `background` to choose) and installs the rolled pairing. A `layout-apply` without `seed` then follows the whole stored direction.
- **Layouts** — 53 principled, seed-varied layouts (`layout-apply`) that adapt to the canvas and set up contrast-checked color roles, a type scale and grids. Use them when a brief gives you free rein. They are fill-in-the-blank forms: `vixl layout show NAME` / `vixl_layouts_list` lists each layout's slots and what each needs. Fill them all; an unfilled slot renders as a `[Label]` blank that `check` reports as an error, and a slot the layout doesn't use is rejected rather than silently dropped. Templates work the same way.
- **Typefaces** — the bundled font is a proofing fallback (`check` warns about it). Pick real type from a researched catalog of open-licensed families and curated heading/body pairings: `vixl font pairings --mood editorial` / `vixl_fonts`, then `vixl font pair NAME|random` / `vixl_font_pair` downloads, embeds and sets them as the document typography that layouts use; the result's `source` says whether each font came from the cache or a download (URL). `vixl font principles` explains how to combine fonts. Text without `font` uses the body face once the document has typography, text without `color` uses `@ink` (or black or white, whichever reads on the canvas), text without `size` uses the body size of the type scale (proportional to the canvas), and leading follows one line-height table (body 1.45, headings 1.1, display 1.0; `spacing` may be negative).
- **Dice** — when the brief is thin, roll instead of defaulting: `vixl roll --for poster` / `vixl_roll` picks a pairing, a mood-consistent palette, a layout and its parameters from one seed, weighted by purpose (poster, social, slides, document, form, diagram, logo, motion; else the document's size) and gated by `variety` (low: safe pools only; medium: mostly safe, sometimes bold; high: every tier); layouts and templates accept `seed: "random"`. Roll a few, preview, keep the seed you like, and `--lock` choices you want fixed (`--lock tier=bold` explores a tier). `vixl house show PURPOSE` prints the purpose profile.
- **Color language** — `oklch()`, `lab()`, `cmyk()`, `color(display-p3 …)`, `kelvin()`, `color-mix()`, `lighten(@brand, 10%)` … everywhere; `vixl_color` for harmonies, scales and contrast; `palette-generate`.
- **Print** — CMYK PDF/TIFF/JPEG (ICC profile or GCR + ink limit), PDF, ICO, icon sets, dpi, soft proofs, color-blindness simulation, `print` and `color_vision` checks.
- **Brushes** — editable paint layers with 17 brushes (`paint`, `paint-layer`, `brush-define`).
- **Timelines** — keyframes, easing, presets and markers on any layer property; preview a frame or a contact sheet; export GIF/APNG/WebP/sheet/PNG frames/MP4.

See [design-system.md](references/design-system.md) (sizes, layouts, color, print), [typography.md](references/typography.md) (catalog, pairings, installs, rolls) and [brushes-timeline.md](references/brushes-timeline.md).

## New in 0.11

Discover commands with `vixl commands --json` and shape shortcuts with `vixl shapes`. Command help works without an open document. CLI edits now default to compact results; add `--detail full` for snapshots. Use named palettes, built-in/custom templates, overall/style guidance, explicit HTTPS/local fonts, expanded shapes and Bézier paths. SVG retains supported shapes, gradients, groups, pixels, boolean silhouettes and shaped Unicode text and common effects/styles as vectors; strict SVG policy rejects embedded raster content with layer/effect details. See [local artistic filters](references/artistic-filters.md) for 19 deterministic treatments, defaults and ranges; no AI provider is needed. PNG preserves transparency; JPG flattens against an explicit background.

See [resources](references/resources.md) for the new MCP tools and CLI/operation examples. Discover authenticated provider models with `vixl models --refresh` or `vixl_models_list`; native Anthropic/Gemini and OpenAI-compatible Mistral/Meta join the existing providers. Midjourney requires an authorized HTTP gateway, not a fabricated official API.

## Workspace review and brands

`vixl mcp --workspace .` serves `--tools core --schema slim` by default; fetch operation details with
`vixl_operation_schema`. HTTP clients can use `--http` at `/mcp` with the configured bearer token.
Read `vixl_review_notes` before revising a document and resolve notes after addressing them.
When `vixl_document_open` returns `upgrade`, the document predates 0.21: review the listed layers and
open it again with `upgrade="pin-fills"` (old white fills) or `"accept"`.
Humans can follow progress with `vixl -p DOCUMENT view`.

Workspace `brand.json` provides default palette roles, pairing/embedded fonts, embedded logos,
minimum contrast, and required layer names. Layouts, templates, rolls and checks honor it, and new
documents embed its fonts at creation (`workspace_fonts` in the result; `workspace_fonts: false` skips).
Set the workspace typography with `vixl_font_pair`/`vixl_font_install(role=...)` and `scope: "workspace"`.
Use `vixl_roll(apply=true, slots={...})` or `roll --apply --set title=...` to apply a whole direction;
`layout apply` returns unfilled slots immediately. Check and fill them before export. A roll with `slots` omits the slots you did not fill (`unfilled: "omit"`), so it passes `check`; pass `unfilled: "blank"` to keep `[Label]` placeholders instead.
`vixl_import_document` imports editable SVG paths or a raster PDF page. With the default
`svg_mode="editable"` unsupported SVG features return an error; `"appearance"` keeps the look as a raster layer
(with the SVG source stored) and `"auto"` falls back to it.

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

0. **Start right** (see *Start here* above: guide → layout → fonts → finish → check) — for a new piece, create it from a named size (`size="instagram-portrait"`,
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
   Then run your own suite (`vixl_workflow("check", {suite: NAME})`, or `suites=true` on the apply) for
   this brief's requirements; see "Tests: why, when and how" above. Fix failures before step 6.
6. **Look at the result.** MCP: `vixl_render_preview()` returns an image (≤1024 px, ≤1 MiB by
   default; `region=[x,y,w,h]` zooms in; `isolate=["mascot"]` shows one object alone, cropped to it).
   `vixl_render_compare()` shows previous vs current (also with `isolate`).
   CLI: `vixl render --out /tmp/preview.png` then view the file. Never declare a visual
   task done without looking.
7. **Measure, don't eyeball,** when precision matters: `vixl_measure` / `vixl info` (colors,
   WCAG contrast of a text layer), `vixl_measure_spacing` / `vixl spacing` (gaps),
   `vixl_validate` / `vixl validate` (bounds, aspect ratios, assertions).
8. **Fix with targeted edits or `undo`**, then **export** (`vixl_export_file` / `vixl export`).
   A `.psd` path writes a layered Photoshop handoff file (one pixel layer per layer, groups kept, text as pixels).

## 3. Minimal examples

**MCP**

```text
vixl_workspace_list()                                   # see files; paths are relative to the workspace
vixl_document_create(path="poster.vixl", width=1080, height=1350, background="#101828")
vixl_import_image(path="photos/portrait.jpg", name="portrait")
vixl_operations_apply(operations=[
  {"type":"resize","target":"portrait","width":1080,"keep_aspect":true},
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
# or check and look in the same call as an edit:
vixl_operations_apply(operations=[{"type":"move","target":"title","y":900}], check=true, preview=true)
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
  for complete before/after snapshots. REST also defaults to `detail:"compact"`; MCP defaults to the
  leaner `detail:"brief"` (IDs, names and bounds of changed layers, plus `warnings`).
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
- **Opacity is 0–1 everywhere**; `"50%"` is read as 0.5, and a bare number above 1 is an error (never guessed as a percentage).
- **Scale `value` is a factor** (`0.8`); CLI accepts `80%`.
- **Absolute `move` and `align`/`distribute` clear constraints** on that layer. Use `constrain`
  when layout should survive canvas resizes, artboards or text changes; use `align` for a one-off.
- **One constraint per axis** (e.g. `left` *or* `center-x` *or* `right`). Anchors: `canvas`, a layer
  name/ID, or `guide:NAME`, plus `.left/.right/.top/.bottom/.center-x/.center-y` and `+N`/`-N`.
- **Effects capture the selection that exists when they are added.** Clear it
  (`{"type":"select","shape":"none"}`) before adding whole-layer effects.
- **Palette roles follow light/dark mode, not the order you pass.** `palette-apply` and `layout-apply palette=[…]` give the
  lightest color to the background in light mode and the darkest in dark mode. The result explains every role
  (`palette_roles` / `layout.roles`: color, source, reason). Pass `keep_order: true` to use the colors as
  background, surface, then accents, or set roles yourself (`roles: {background: 0, accent: "#e11"}` on `palette-apply`, `colors: {…}` on `layout-apply`).
- **Palettes and fonts recolor/re-font by role:** `palette-apply` sets `@background`/`@ink`/`@accent`…,
  and `font pair` updates text whose `font` is `heading`/`body` (templates use roles). Literal colors
  and named fonts stay as they are.
- **Text auto-sizes** to its rendered bounds; an explicit `resize` turns that off, editing text turns it back on.
  For wrapping use `text-layout` with `width` (the height grows to the wrapped lines) or `width`/`height` (optionally `fit: true`).
- **Variables:** `${name}` works in text, colors, gradient fills and image-asset IDs. Undefined
  variables are errors. Swatches are `@name` in color fields.
- **Through MCP/REST, operation `path` and `linked` fields are rejected, and `font` takes only a registered
  font name or role (`heading`/`body`; install with `font pair`/`font install` first).** Import files with
  `vixl_import_image(path=…)` or, when you only have the bytes, `vixl_import_image(data_base64=…)`
  (MCP) or `POST /assets` (REST); reuse already-embedded images via `asset` IDs.
- **Images from the web:** `vixl_import_image(url="https://…", credit="Photo: Ana Ruiz / Unsplash",
  license="Unsplash License")` (CLI `vixl import URL --credit … --license …`). HTTPS only, no private
  hosts, size-capped; the layer's provenance keeps the source URL, fetch time and sha256 with your credit
  and license, and inspect shows them. Use only images you have the rights to (guidance `image-rights`).
- **MCP may run as two servers:** `vixl` (`--tools core`) for editing and export, `vixl-ai`
  (`--tools ai`) for provider-backed `vixl_ai_*` tools. They share the workspace; edits made in one are
  seen by the other on its next call.
- **Several documents can be open over MCP.** Pass `document="other.vixl"` to any tool to address one
  without changing the active document.
- **MCP paths are relative to the server's `--workspace`** and must stay inside it; missing
  subdirectories are created by `vixl_document_create` and the exports. Exports refuse to overwrite
  unless `overwrite: true`, and never overwrite `.vixl`. `vixl_export_batch` writes several files
  (sizes, formats, documents) in one call.
- **Subagents sharing one MCP server share its active document**: pass `document=` on every call
  (results echo `document`). A slow call returns a `job` id instead of timing out: poll
  `vixl_job(action="result", id, wait=30)` and never resend it; use `request_id` on mutating calls so
  a retry cannot apply twice.
- **Many similar layers, or another size, are one call each**: `edit-layers` applies an operation to every
  layer matching a `where` selector (`name` glob, `kind`, `role`, `tag`, `group`, `text_contains`, `page`;
  add `expect: N` to guard the count); `adapt-layout` (without `targets`) re-lays out a document at a new
  size and reports where each layer went; `vixl_adapt_layout` does it for a list of sizes and saves/exports
  each copy. MCP apply results are `brief` by default: pass `detail: "compact"` for new field values.
- **Read `warnings` in apply results**: text cut off by the canvas or its box, and fields that were
  accepted but change nothing (`radius` on a plain rectangle). Unknown fields are errors with the
  accepted field names and a `vixl_operation_schema(types=[…])` pointer.
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
- **Kinetic type** is `text-animate` on the text layer (`unit: char|word|line`, `preset: fade-up|pop|wave|typewriter|color-sweep …`,
  `stagger`, `direction`), not one layer per letter: the text stays editable and stills show it at rest.
- **Draw a line on** with `animate-preset draw-on` (or animate `trim_end` 0→100 on a `shape`/`pen` stroke;
  `line_cap: "round"` for a round tip). **Swing a layer over** with a negative `scale-x`/`scale-y`
  (`1` → `-1`). A key past the timeline end lengthens it and the result's `warnings` say so
  (`extend: false` keeps the duration).
- **CMYK is an export setting** (`color_space="cmyk"` for PDF/TIFF/JPEG). Pass the printer's ICC profile
  when exact separations matter; without one Vixl uses a GCR approximation with an optional ink limit.
  A CMYK PDF keeps real text and vector shapes (colours as DeviceCMYK); only effects and images are
  CMYK images. Every PDF is vector by default; the result's `content`/`content_reason` say what was written.
- **Limits:** 40 MP per canvas/layer, 16 384 px per side, 4 096 layers, 256 effects/layer,
  10 000 operations per batch. History keeps 2 000 revisions; older unreferenced ones are squashed
  automatically, so long sessions never lock. Pixel-art frames ≤ 256×256, ≤ 256 frames; timelines
  ≤ 10 min, 60 fps, 3 600 frames; 4 096 strokes per paint layer.
- **Not supported** (don't promise them): editable import of arbitrary SVG (appearance import rasterizes it),
  CMYK *editing* or spot colors, live tablet input, RAW, PSD/XCF import (PSD *export* is layered pixels: text is not
  editable type), a GUI editor.

## 5. Feature map (where to look)

| Need | Operations / commands |
| --- | --- |
| Start | named sizes (`canvas` `size`, `vixl new NAME`, `vixl_document_create(size=)`), `layout-apply`, `type-scale`, `palette-generate`, `guidance` |
| New layers | `add` (image), `solid`, `gradient` (linear/angled/radial, multi-stop, `falloff` curves for soft halos), `text`, `shape` (`solid`/`gradient`/`shape`/`text` with `target` edit that layer in place instead of adding one), `frame` (image box with fill/fit), `pixel-art`, `paint-layer`, `adjustment`, `symbol-instance` |
| Transform | `move`, `resize`, `scale`, `rotate`, `skew`, `transform` (affine), `distort` (envelope, corner-pin), `flip`, `crop`, `opacity`, `blend`, `hide`/`show` |
| Stacking | `raise`, `lower`, `top`, `bottom`, `reorder` (`above`/`below`), `group`/`ungroup`, `reparent` (into/out of a group, keeps position), `clip` |
| Layout | `align` (to canvas/selection/layer), `distribute`, `constrain`/`unconstrain`, `stack` (auto-layout column/row that re-flows around hidden or empty members; text `hide_if_empty`), `guide`, `grid`, `canvas` (resize/preset), `artboard` |
| Color & filters | 27 built-in effects (brightness … white-balance … auto-contrast), `effect-set/enable/disable/remove/move`, `lut` + `lookup` (a stack effect), `preset-save/apply` |
| Selections & masks | `select` (rect/ellipse/color/alpha/all/none/invert, add/subtract/intersect, feather), `mask` (create/from-selection/import/invert/enable/disable/delete) |
| Typography | `text`, `text-set`, `text-layout` (box, fit, warp, path), `style-define`/`style-apply`, `swatch` |
| Decoration | `layer-style` (drop-shadow, stroke, outer-glow, color-overlay, gradient-overlay), `look` (named finishes: clean-flat, subtle-grain, light-paper, glow, neon, soft-shadow, hard-shadow, outline, gradient, soft-halo, grain, paper, film, duotone, risograph, sketch, watercolor, halftone, hand-made, plush), `repeat`, `repeat-blend`, `radial-repeat` (copies around a center, optional mirror, per-step/jitter, `merge`), `scatter`, `pattern-scatter`, `pathfinder` |
| Templates | `variable`, `replace-contents`, `comp-save`/`comp-apply`, CSV `render --data`, `export-screens` |
| Painting | `paint` (17 brushes, points or SVG path, pressure, erase), `paint-clear`, `brush-define` |
| Motion | `timeline-set` (`loop_mode`), `keyframe`, `keyframes` (or `sample` a wave), `keyframe-remove`, `animate`, `animate-preset`, `text-animate` (per char/word/line), `motion` (wiggle, line-boil …), `character-pose` (`time` keys), `audio-track`, `marker`; `vixl_timeline_preview`, `vixl_export_timeline` |
| Pixel art & sprite frames | `pixel-art`, `pixel-draw`, `pixel-palette`, `frame-save/apply/delete`, `animation-set` (`name`+`order`: named animations, each exportable alone with `animation=`), `frames-edit` (one edit applied to every saved frame), `export-animation` (GIF/APNG/WebP/MP4/sheet) |
| Color & print | color language in every color field, `vixl_color`, CMYK/PDF/ICO export, `vixl_export_icons`, proof/simulate previews, `print`/`color_vision` checks |
| History | undo/redo (a count larger than the history goes as far as it can and says so), checkpoint, branch, checkout, compare, transactions |
| Styles | `vixl_styles` (28 design styles: principles, palettes, type, layout, imagery, do/don't), `style-set` tags the document, `check --checks style` evaluates the style's premade rules |
| QA | check (bounds/overlap/contrast/safe area/legibility; opt-in print, color_vision, style, connected (floating parts of a grouped object); every finding has an `action`: fix / review / informational), inspect, measure (sample/histogram/contrast), spacing, validate/assert, render preview (zoomable, time, proof, simulate, isolate one object), compare revisions |
| AI (provider) | generate/inpaint/img2img, extend (outpaint), upscale, regenerate, background-remove, select object/subject, remove, content-aware-fill, describe/detect/OCR, natural-language plan |

When unsure of a field, get the authoritative schema: MCP embeds it in `vixl_operations_apply`'s
input schema (also resource `vixl://operations`); CLI `vixl schema`; REST `GET /schema`; per-command
syntax via `vixl COMMAND --help`.
