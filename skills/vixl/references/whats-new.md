# What's new, by release

Agent-facing summaries of the larger additions since 0.11, kept from the skill entry point. The
[changelog](../../../CHANGELOG.md) has the complete release notes; the topic references hold the current details.

## New in 0.24: reliability and reusable delivery

- **Checks** — `passed` is false while any finding has action `fix`, warnings included; `by_action` lists the issue
  indexes under fix / review / informational. An explicit `checks` list replaces the default set, so narrow it only on purpose.
- **Text and layout** — width-only text boxes regrow after edits and variable substitution (fixed-height boxes still need
  an overflow check). `adapt-layout` with `recompose: true` rebuilds a stored layout recipe at the new size and may
  replace manual edits and generated layer IDs; proportional adaptation stays the default.
- **Source folders** — `vixl unpack design.vixl design-source` writes the current state as stable JSON (`project.json`,
  with asset hashes) plus asset files (no history; registered fonts kept); `vixl pack design-source out.vixl` validates and rebuilds it. See
  [cli](cli.md).
- **Documents from earlier releases** — this release opens only current documents: run `vixl convert OLD.vixl -o NEW.vixl`
  once (`--look preserve` keeps the old look, `--look current` lists what changes; the report names every change), and
  `vixl convert-batch OLD.json` for saved tool calls from the 51-tool server. See `docs/reference/converting.md`.
- **App delivery** — `vixl_apply(workflow='app-animation-package', request={states, default_state, output, themes?, transitions?, format?})`
  writes named states, light/dark variables, transitions, reduced-motion PNGs, editable masters, a manifest and an HTML
  consumer. `screen-capture` (`{output, bbox? | window?, all_screens?}`) is an explicit local desktop capture, not
  rendering. MCP requires the server owner to enable `--allow-screen-capture` or `VIXL_ALLOW_SCREEN_CAPTURE=1`; paths are workspace-relative. See [production](production.md).
- **Motion** — `character-pose` with `time` (and `easing`) keys joint angles and solves the rig every frame; don't add
  separate limb x/y/rotation keys. A new timeline of 10 s or less is a seamless loop: pass
  `loop_mode: "off"` or `loop: 1` for play-once. `animate` `intent` (entrance, exit, loop, emphasis) picks the house
  easing. Templates `video-tip`, `video-launch`, `video-event` build editable six-second loops (title/subtitle/cta).
  See [brushes and timeline](brushes-timeline.md).
- **House style** — 76 font pairings, weighted alignment, saturated backgrounds kept. Explicit fields and saved
  geometry win. Minor social/poster text must be at least 2.2 % of
  the short side; bold text counts as large from 18.66 px (regular from 24 px).
- **Spacing units** — `stack` and `layout-apply` `gap` accept `"2u"` (CLI `--gap 2u`; 1u = half the body size); stacks default
  to 2u.
- **Brushes and frames** — paint `settings` `drip` (0–4 brush sizes), `relief` (0–1) and `light_angle` (degrees,
  default -45); `frame` `frame_shape` (rectangle, ellipse, star, hexagon, heart) or a closed SVG `outline` in
  frame-local pixels; keep the canvas transparent for a shaped image.

## New in 0.22

- **`vixl_apply(create=…)`** — the whole start-here chain in one atomic call ([workflow](workflow.md#one-call-for-a-new-piece)); REST `POST /compose` is a dry run.
- **Logo packages** — `vixl_apply(workflow='logo-package', request={output, mark?, wordmark?, …})` turns a logo (open document,
  `.vixl`, PNG/JPEG/WEBP or SVG; `trace: true` vectorizes a raster) into full-colour, mono black, mono white,
  on-light and on-dark variants, optional mark/horizontal/stacked lockups, strict SVG, RGB (+ CMYK) PDF, PNG at
  1x/2x/3x, icons with favicon, social avatar and Open Graph images, `usage.html` and an optional zip. Recolouring is
  heuristic: read `report`. There is no EPS export: hand over the PDF or SVG.
- **Proof pages** — `vixl_apply(workflow='proof', request={items, output, decisions?})` writes one offline HTML page to review
  documents and exports (thumbnails, metadata, check findings, before/after, approve/reject saved as a JSON download).
- **`vixl diff A B --out d.png`** — pixel-diff two documents or images (changed pixels, fraction, region).
- **Memes** — `meme-top-bottom`, `meme-caption-above`, `meme-comparison`, `meme-labelled`, `meme-reaction`,
  `meme-four-panel` layouts (`images` takes one asset per panel); `vixl_reference("meme")`. Bring your own images.
- **CI** — the repository's GitHub Action checks `.vixl` files on pull requests (`docs/guides/automation/ci.md` in the Vixl repository).

## New since 0.17

- **Slides and decks** — `page`/`master` operations, speaker notes, `vixl_render(page="all")`,
  `vixl_check(checks=["deck"])`, export `.pdf` (vector, selectable text), `.pptx` (editable) or
  `.html` (a one-file presentation with speaker view).
- **Forms** — `field` layers (rules such as `format`, `pattern`, `max_length` become PDF actions),
  `vixl_export(fillable=true)`, filling with `values` or the `form-fill` workflow, `vixl_check(checks=["form"],
  sample="worst")` (each overflow reports what it measured).
- **Hand drawings** — `drawing` import/clean/vectorize/straighten/fill/stroke; keep the person's
  lines and measure it with `drawing-report` (`preserved`) and `drawing-compare`.
- **Rich text** — `rich-text` (Markdown) and `text-style` for mixed styles and lists in one box. `text-set` changes the
  whole layer (text, color, size, font) and keeps bullets and span styles that still apply; read the result's `warnings`.
- **Baselines** — `baseline_y` on `text`/`text-set`/`move` places the first line's baseline; `align` with
  `alignment: "baseline"` and `snap` with `anchors: ["baseline"]` (onto a baseline grid) line text up by baseline.
- **Text flow** — `text-flow` threads a long text through linked frames (columns, pages, shapes); results report `overflow`.
- **Diagrams** — `diagram-from-text` / `diagram` / `diagram-set` draw flowcharts, dependency graphs, org charts and mind maps
  as editable layers (swimlanes, auto-fit, `check diagram`).
- **Organic shapes** — `organic` presets and composable generators for living things; preset `water` draws filled
  layered sea or lake bands.
- **Scene atmosphere** — `haze`, `star-field` (keeps clear of text), `string-lights`, `bokeh` and `reflection`, one
  operation each and seeded; catalog shapes `cup`, `steam`, `lighthouse`, `lantern` for common motifs.
- **Scatter and seamless tiles** — `scatter` (Poisson-disc copies inside or along a layer's outline, seeded jitter,
  `merge` for one path per tone, `preset: fur`), `pattern-scatter` (wrap-around tile with a seam score; a lower
  `count` or `thin` keeps the surviving copies in place), per-step
  and jittered `repeat`/`radial-repeat` (`vixl_reference("scatter")`).
- **Imperfection** — opt-in `irregular` (seeded wobble, stroke weight, color drift, micro placement)
  and `tear` (torn edges) for characters, stickers, scenes, scattered patterns, hand-made looks and
  ripped paper; never for logos, charts, text or anything that must align (`vixl_reference("imperfection")`). `arc` shapes draw pie wedges and donut segments; `closed: false` draws just the stroked curve.
- **Shape parameters and content boxes** — shortcut shapes take their own parameters (heart `apex`/`cleft`/`tip`,
  speech-bubble `pointer_side`/`pointer_position`/`pointer_size`/`body`, shield `depth`, `slant`, chevron
  `thickness`; `vixl_reference('capabilities', name="shapes")` lists all). Shapes report `content_bounds` (a bubble's body, a
  badge's centre, a screen): put text there with `text` `within`, `place` `within` or `align` `box: "content"`.
- **Charts** — `chart` (bar, stacked, 100 %, horizontal, line, area, pie, donut) from a table or workspace CSV, `chart-data` to fix
  a value on stable layer IDs, native PPTX charts; see [charts](charts.md) before drawing any chart by hand.
- **Tables** — `table` (rows or a workspace CSV; aligned columns including `decimal` for prices, dot `leader`s, header,
  zebra, rules) and `table-data` for cell and row edits; native PPTX tables; see [charts](charts.md#tables).
- **Key-value lists** — `key-value-list` pairs labels with right-aligned values and shares in ruled columns
  (`shares: "auto"` computes percentages); a chart's `legend_values` legend is the same list. See
  [charts](charts.md#key-value-lists).
- **Guides beyond right angles** — angled/curved guides, compositional and perspective grids,
  `place`, `snap`, `guides`/`alignment` checks.
- **Lyric videos** — `lyric-video-plan/build/export` workflow actions (song + LRC + template). The template's own
  keyframes survive the build; `lead_in`/`tail` make room for an `intro` title card and an `outro` end card; the plan
  returns cue and section windows; `segments` makes long renders resumable.
- **Linked documents** — `link` layers render another `.vixl` live (derived crops, pattern previews, sheets); `links` reports
  stale/missing sources, `link-embed` freezes one; `corner_pin` warps a link into four corners. See [production](production.md).
- **Decks from Markdown** — the `deck-from-markdown` workflow builds a checked deck (layouts, rich text, tables,
  charts, images, speaker notes, one master) from a Markdown file in one call; re-running rebuilds only changed slides.
- **Mockups** — the `mockup` workflow places a design in phone, laptop, browser, poster-wall, business-card or mug
  templates (or the workspace's own, `mockup-save`) as a live, corner-pinned link; one call per design, `export` renders them.
- **Print merge** — `merge-impose` lays CSV rows out on print sheets with crop marks: vector-text PDF plus an editable sheet.
  Placeholders take filters: `${name|upper}`, `${company|default:Independent}`, `${state|map:states}` (`variable-map`).
  `$${name}` writes a literal `${name}`.
- **QR codes and barcodes** — `qr` and `barcode` (Code 128, EAN-13) are vector shapes in every export; `data` may use
  `${variables}` for merges; `check codes` flags small modules, low contrast and ink in the quiet zone.

Read [documents](documents.md) (rich text, pages, forms), [charts](charts.md) and
[drawing, shapes and guides](drawing-shapes-guides.md); lyric videos and form-fill jobs
are in [production](production.md).

## New in 0.13

The production extension adds `vixl_reference('workflows')` and `vixl_apply(workflow=…)` (CLI:
`vixl workflow`). Use them for saved design suites, typed recipes, checked actions,
variation matrices, reusable motion, draft/final renders, component libraries, durable
jobs and shot-based films. Read [production workflows](production.md)
for the schemas and limits. View the initial design; use saved suites on routine edits
and inspect failed/uncertain checks and material visual changes. A clean check report
certifies only its explicit rules and time coverage. Never weaken a suite as a repair.
Use submit/start/status for long jobs. An uncertain external generation request must
not be blindly repeated; preserve its remote job identity.

- **Named sizes** — `vixl_document(action='create', size="letter", bleed=true)` / `vixl new business-card --bleed`; 151 print, social, web, ad, video, slide, icon and logo sizes with dpi, bleed, safe area and guides.
- **New documents** — every creation surface (`vixl new`, `Project.new()`, `vixl_document(action='create')`, compose) rolls and stores `design_defaults` (`seed`/`--seed`, `variety`/`--variety` reproduce them), gives the canvas the palette background (transparent for logos, icons and favicons; pass `background` to choose) and records the rolled pairing, which the first batch with text installs (nothing is downloaded at creation). A `layout-apply` without `seed` then follows the whole stored direction. `house_style: "off"` (`--house-style off`, or `{"house_style": "off"}` in `.vixl/variety.json`) rolls nothing: a white canvas (transparent for marks), the workspace fonts else the bundled font, and a neutral direction (mono palette, light, no accent, motif, look or style) that layout-apply follows; craft rules still apply, and a roll still rolls on request.
- **Layouts** — 53 principled, seed-varied layouts (`layout-apply`) that adapt to the canvas and set up contrast-checked color roles, a type scale and grids. Use them when a brief gives you free rein. They are fill-in-the-blank forms: `vixl layout show NAME` / `vixl_reference('layouts')` lists each layout's slots and what each needs. Fill them all; an unfilled slot renders as a `[Label]` blank that `check` reports as an error, and a slot the layout doesn't use is rejected rather than silently dropped. Templates work the same way.
- **Typefaces** — the bundled font is a proofing fallback (`check` warns about it). Pick real type from a researched catalog of open-licensed families and curated heading/body pairings: `vixl font pairings --mood editorial` / `vixl_reference('fonts')`, then `vixl font pair NAME|random` / `font-pair` downloads, embeds and sets them as the document typography that layouts use; the result's `source` says whether each font came from the cache or a download (URL). `vixl font principles` explains how to combine fonts. Devanagari, CJK and Thai text draws as empty boxes until a face covers it (the apply warns): a `font-cover` step (`vixl font cover`) installs the Noto fallbacks. Text without `font` uses the body face once the document has typography, text without `color` uses `@ink` (or black or white, whichever reads on the canvas), text without `size` uses the body size of the type scale (proportional to the canvas), and leading follows one line-height table (body 1.45, headings 1.1, display 1.0; `spacing` is line spacing and may be negative). Letter spacing is the layer's `tracking` (pixels), and `text_transform` (`uppercase`, `lowercase`, `capitalize`) cases the drawn text; both apply to keyed and `${variable}` text.
- **Dice** — when the brief is thin, roll instead of defaulting: `vixl roll --for poster` / `vixl_reference('roll')` picks a pairing, a mood-consistent palette, a layout and its parameters from one seed, weighted by purpose (poster, social, slides, document, form, diagram, logo, motion; else the document's size) and gated by `variety` (low: safe pools only; medium: mostly safe, sometimes bold; high: every tier); layouts and templates accept `seed: "random"`. Roll a few, preview, keep the seed you like, and `--lock` choices you want fixed (`--lock tier=bold` explores a tier). `vixl house show PURPOSE` prints the purpose profile.
- **Color language** — `oklch()`, `lab()`, `cmyk()`, `color(display-p3 …)`, `kelvin()`, `color-mix()`, `lighten(@brand, 10%)` … everywhere; `vixl_reference('color')` for harmonies, scales and contrast; `palette-generate`.
- **Print** — CMYK PDF/TIFF/JPEG (ICC profile or GCR + ink limit), PDF, ICO, icon sets, dpi, soft proofs, color-blindness simulation, `print` and `color_vision` checks.
- **Brushes** — editable paint layers with 17 brushes (`paint`, `paint-layer`, `brush-define`).
- **Timelines** — keyframes, easing, presets and markers on any layer property; preview a frame or a contact sheet; export GIF/APNG/WebP/sheet/PNG frames/MP4.

See [design-system.md](design-system.md) (sizes, layouts, color, print), [typography.md](typography.md) (catalog, pairings, installs, rolls) and [brushes-timeline.md](brushes-timeline.md).

## New in 0.11

Discover commands with `vixl commands --json` and shape shortcuts with `vixl shapes`. Command help works without an open document. CLI edits now default to compact results; add `--detail full` for snapshots. Use named palettes, built-in/custom templates, overall/style guidance, explicit HTTPS/local fonts, expanded shapes and Bézier paths. SVG retains supported shapes, gradients, groups, pixels, boolean silhouettes and shaped Unicode text and common effects/styles as vectors; strict SVG policy rejects embedded raster content with layer/effect details. See [local artistic filters](artistic-filters.md) for 19 deterministic treatments, defaults and ranges; no AI provider is needed. PNG preserves transparency; JPG flattens against an explicit background.

See [resources](resources.md) for resource calls and CLI/operation examples. Discover authenticated provider models with `vixl models --refresh` or `vixl_models_list`; native Anthropic/Gemini and OpenAI-compatible Mistral/Meta join the existing providers. Midjourney requires an authorized HTTP gateway, not a fabricated official API.
