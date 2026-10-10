# Use-case catalog

[Documentation home](README.md) · [Visual gallery](gallery.md) · [Coverage and limitations](coverage.md)

A running list of the things people and agents make with Vixl, grouped by how much work each one
takes **today**. It is meant to grow: add a row whenever you find a new use case, and move a row
when a release makes it cheaper or a measurement says it costs more. See [Maintaining this list](#maintaining-this-list).

Effort figures describe an AI agent working through the MCP server (`vixl mcp --tools core --schema slim`)
unless a row says otherwise. A person driving the CLI or a Python script needs a similar number of
commands; a reproducible script is usually faster to re-run than to write.

## How to read it

### Tiers

Tiers are set by **tool calls** first, because wall time depends on the machine, the model and how
many clients share one server. Minutes are typical agent wall time on a shared container.

| Tier | Calls | Typical time | What it looks like |
| --- | ---: | --- | --- |
| **T0 · One-shot** | 1–3 | under 1 min | One operation, one command or one lookup. |
| **T1 · Quick** | 3–10 | 1–3 min | A small brief with exact instructions. The 18-task eval suite lives here. |
| **T2 · Standard** | 10–40 | 2–5 min | One finished design from a loose brief, or a revision of a larger one. |
| **T3 · Involved** | 40–70 | 4–8 min | Several parts or pages, data, print output, cleanup or motion. |
| **T4 · Large** | 70+ | 8–30 min | A kit or system: many related files, a film, a full deck. |
| **T5 · Project** | many sessions | hours | Multi-document, multi-format or scripted pipelines. |
| **Blocked** | – | – | Not possible yet, or only with a workaround outside Vixl. |

### Evidence

| Code | Meaning |
| --- | --- |
| **M:T01…T16** | Measured: Vixl lane of the [tool comparison](../eval-results/2026-10-06-vixl-0.20-tool-comparison.md) on 0.20.0, round 1 (all tool calls, including reads and file checks; median-style single runs). **R2** marks the round-2 revision of the same brief. |
| **M:eval:name** | Measured: live agent run of [`evals/tasks/name.json`](../evals/tasks) on 0.18.0 ([results](../eval-results/2026-10-05-full-evaluation.md)). Counts are Vixl calls only, so add 1–3 for file reads. |
| **M:X01…X10** | Measured: [exploration](../explorations/README.md) build script on 0.21.0. The time is the *script's* run time; writing such a script by hand is T5. |
| **E** | Estimate from the operations involved and the nearest measured case. Replace with a measurement when you have one. |

### Requirement tags

`[AI]` needs a configured provider ([providers](providers.md)). `[ffmpeg]` needs ffmpeg on `PATH`
for MP4/WebM/audio mux. `[server]` needs the `server` extra (REST, live view). `[pdf]` needs the
`pdf` extra for PDF page import. No tag means the core install, offline.

### Domain prefixes

IDs are stable: a row keeps its ID when it moves to another tier.

| Prefix | Domain | Prefix | Domain |
| --- | --- | --- | --- |
| DOC | Documents, layers, history | PHO | Photo editing |
| TXT | Text and typography | ILL | Illustration, painting, organic, patterns |
| CLR | Color and palettes | DRW | Hand drawings and vector paths |
| SHP | Shapes, layout and placement | PIX | Pixel art, sprites, game assets |
| SOC | Social, web, ads, email | MOT | Motion, animation, video, audio |
| PRN | Print and stationery | PRD | Production, variants, data merge |
| BRD | Logos, icons, brand | QA | Checks, measurement, review |
| DAT | Charts, diagrams, infographics | COL | History, branches, collaboration |
| DEK | Slides, carousels, booklets | AGT | Agent, API and integration |
| FRM | Forms | AI | Provider-backed generation and vision |

---

## T0 · One-shot (1–3 calls, under 1 minute)

### Documents and layers

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DOC-01 | Create a blank document at a named size (letter, instagram-post, youtube-thumbnail …) | `vixl_document_create(size=…)`, `vixl new NAME` | 1 · <1 | E | 150 named sizes with trim/safe guides; `vixl_sizes_list` to browse. |
| DOC-33 | Start a designed document from only a purpose (or nothing): size, palette background, design defaults and real fonts | `vixl_document_create(purpose=…)`, `vixl new --purpose slides`, `Project(purpose=…)` | 1 · <1 | E | Since 0.23; same result on every surface for the same `seed`. Fonts install from the cache or network. |
| DOC-02 | Create a print document with bleed and dpi | `vixl new letter --bleed --dpi 300` | 1 · <1 | E | Print sizes carry physical units, bleed and safe area. |
| DOC-03 | Open and inspect a `.vixl` (layers, bounds, fonts, effects) | `vixl_document_open`, `vixl_document_inspect` | 2 · <1 | E | `--detail brief|compact|full` controls response size. |
| DOC-04 | Rename, hide, show, raise, lower, duplicate or delete a layer | `vixl_operations_apply` | 1 · <1 | E | Works on `targets` lists in one atomic batch. |
| DOC-05 | Change canvas size or switch to another preset (portrait ↔ landscape) | `canvas resize`, `canvas size NAME --landscape` | 1 · <1 | E | Constrained layers follow their anchors. |
| DOC-06 | Add a solid or gradient background | `solid`, `gradient` operations | 1 · <1 | E | Linear, radial and multi-stop gradients. |
| DOC-07 | Import an image, SVG or PDF page as a layer | `vixl_import_image`, `vixl_import_document` | 1 · <1 | E | PDF needs `[pdf]`; SVG editable or appearance mode. Since 0.24 Vixl's own simple gradient rectangles and stroked paths re-import editably (#334). |
| DOC-08 | Undo, redo or jump back in history | `vixl_history`, `vixl undo N` | 1 · <1 | E | Delta history with checkpoints. |
| DOC-09 | Save a named checkpoint before a risky edit | `vixl checkpoint NAME` | 1 · <1 | E | Restore with `checkout`. |
| DOC-10 | Set a document variable and render with an override | `variable set`, `render --set NAME=VALUE` | 2 · <1 | E | |
| DOC-11 | Close one of several open documents | `vixl_document_close` | 1 · <1 | E | Multi-document sessions pass `document=`. |
| DOC-12 | List the files in the workspace | `vixl_workspace_list` | 1 · <1 | E | |
| DOC-13 | Inspect what a document depends on and check it reproduces | `vixl dependencies`, `vixl reproduce --check` | 1 · <1 | E | |
| BLK-16 | Relink the links in a copied `.vixl` | `links-relink {from, to}` | 1 · <1 | E | Since 0.22; sources beside the document are stored relative to it. |
| DOC-31 | Import an image from a URL with its credit and licence | `vixl_import_image(url=…, credit, license)` | 1 · <1 | E | Since 0.22; https only, private hosts refused. |
| DOC-32 | Merge layers into one, or flatten the page | `merge-layers`, `flatten` | 1 · <1 | E | Since 0.22; undo restores the originals. |
| DOC-34 | Import a camera photo above the pixel limit (108 MP) | `vixl_import_image`, or `add` with `max_pixels` | 1 · <2 | E | Since 0.23; downsampled to the limit, sources up to 4× it. |
| DOC-35 | Edit a document of thousands of layers one operation at a time, or send a 10,000-operation batch | `vixl_operations_apply` | 1 · <1 | E | Since 0.23 an edit lays out only the layers it depends on; was seconds per edit and minutes per batch (#284, #300). |
| DOC-36 | Unpack a `.vixl` into a readable source folder for Git review, and pack it back | `vixl unpack`, `vixl pack`, `vixl.project_folder` | 1–2 · <1 | E | Since 0.24 (#511); current state and registered fonts only, no undo history; packing validates paths, sizes and hashes. |
| DOC-37 | Capture the desktop, a rectangle or a Windows window to PNG | `vixl_workflow` screen-capture | 1 · <1 | E | Since 0.24 (#259); interactive local desktop only; OS screen permission may be needed. |

### Text and typography

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| TXT-01 | Add a text layer with size, color and position | `text` operation | 1 · <1 | E | Registered font names work in the batch. |
| TXT-02 | Change the words of an existing text layer | `text-set` | 1 · <1 | E | Keeps rich-text lists and spacing (fixed in 0.20). |
| TXT-03 | Browse fonts by category or mood | `vixl_fonts` | 1 · <1 | E | |
| TXT-04 | Install a curated heading/body font pairing | `vixl_font_pair` | 1–2 · <1 | E | Bundled DejaVu is a proofing fallback only. Since 0.23 creation installs the rolled pairing (0 extra calls) when the font cache or network is available. |
| TXT-05 | Install one Google font or import a local font file | `vixl_font_install`, `vixl_import_font` | 1 · <1 | E | |
| TXT-06 | Generate a modular type scale | `type-scale --base 16 --ratio golden` | 1 · <1 | E | |
| TXT-07 | Read text metrics (ink box, baseline, cap height, x-height) | `vixl_measure`, `info --target TEXT` | 1 · <1 | E | |
| TXT-08 | Warp text (arc, flag, wave …) or set it along a path | `text` with `warp` / polyline placement | 1 · <1 | E | Outlined warp presets export as vectors. |
| TXT-09 | Define and apply a linked character/paragraph style | `style-define`, `style-apply` | 2 · <1 | E | |
| TXT-10 | Flow a very long text (100,000 characters, even one unbroken word) through columns | `text-flow` | 1 · <1 | E | Since 0.23; a 100,000-character word took about 6 minutes (#335). |
| BLK-08 | Place text by its baseline | `baseline_y` on text/move, `align` `baseline`, `snap` to a baseline grid | 1 · <1 | E | Since 0.22. |
| TXT-11 | Use emoji in text with bundled, editable art (complete Unicode 17 sequences, joiners and flags) | `text`, `emoji-mode` | 1 · <1 | E | Since 0.24; bundled art by default, `emoji-mode font` prefers the font; PDF/PPTX use a reported raster fallback. |
| TXT-12 | Find an emoji or extract it as an editable `.vixl` master | `vixl emoji list`/`get`, `vixl_workflow` emoji-list/emoji-get | 1 · <1 | E | Since 0.24; 3,953 Unicode sequences plus 100 originals. |

### Color

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| CLR-01 | Convert a color between hex, OKLCH, CMYK, Lab … | `vixl_color`, `color convert` | 1 · <1 | E | CSS Color 4/5, `kelvin()`, `cmyk()`, xkcd names. |
| CLR-02 | Measure contrast between two colors | `color contrast FG BG` | 1 · <1 | E | |
| CLR-03 | Build a harmony (triadic, analogous …) or a tint/shade scale | `color harmony`, `color scale` | 1 · <1 | E | |
| CLR-04 | Generate and register a palette from one seed color | `palette-generate NAME COLOR` | 1 · <1 | E | |
| CLR-05 | Apply one of the 74 built-in palettes | `palette apply` | 1 · <1 | E | |
| CLR-06 | Define brand swatches and use `@swatch` references | `swatch` | 1 · <1 | E | Modifiers like `lighten(@brand, 10%)`. |
| CLR-07 | Find a color by name (CSS or xkcd) | `color names QUERY` | 1 · <1 | E | |

### Shapes, layout and placement

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| SHP-01 | Add a rectangle, ellipse, polygon, star, arrow or line | `shape` | 1 · <1 | E | Large catalog: seals, chevrons, technical shapes, ornaments. |
| SHP-02 | Round or chamfer corners individually | `shape` corner fields | 1 · <1 | E | |
| SHP-03 | Dashed, multi-stroke, tapered or arrow-headed strokes | stroke fields | 1 · <1 | E | Caps, joins, alignment, markers, width profiles. |
| SHP-04 | Center a layer or align several to an edge | `align` | 1 · <1 | E | |
| SHP-05 | Distribute layers with equal gaps | `distribute` | 1 · <1 | E | |
| SHP-06 | Move, resize, scale, rotate, flip or skew a layer | transform operations | 1 · <1 | E | Fractional sizes, named pivots, affine matrices. |
| SHP-07 | Group, ungroup, clip one layer to another | `group`, `ungroup`, `clip` | 1 · <1 | E | |
| SHP-23 | Add a part drawn later to an existing (rotated, scaled) group, or lift a part out | `reparent` | 1 · <1 | E | Since 0.23 (#382); keeps the render and the group's settings. |
| SHP-08 | Combine shapes (union, subtract, intersect, exclude) | `pathfinder` | 1 · <1 | E | |
| SHP-09 | Add guides, a column grid, baseline grid, golden or thirds grid | `guide`, `grid` | 1 · <1 | E | Polar, isometric, hex, oblique and perspective grids too. |
| SHP-10 | Place or snap layers onto a guide | `place`, `snap` | 1 · <1 | E | |
| SHP-11 | Repeat a layer in a row/grid or blend between two | `repeat`, `repeat-blend` | 1 · <1 | E | |
| SHP-12 | Repeat a motif around a centre (rosette, sunburst) | `radial-repeat` | 1 · <1 | E | `--mirror` for kaleidoscope symmetry. |
| SHP-13 | Make a hug-content pill, badge, button or code window | `stack` with padding/background | 1 · <1 | E | Since 0.24 `gap` also takes shared spacing units (`"2u"`). |
| SHP-14 | Find empty space, margins or a hit-test point | `vixl_spatial` | 1 · <1 | E | |
| SHP-15 | Set opacity or a blend mode | `opacity` (0–1), `blend` | 1 · <1 | E | |
| SHP-16 | Pin a layer to an edge or another layer | `constrain` | 1 · <1 | E | One anchor per axis; cycles rejected. |
| SHP-17 | Frame an image in an irregular silhouette (ellipse, star, hexagon, heart or an SVG outline) | `frame` with `frame_shape` or `outline` | 1 · <1 | E | Since 0.24 (#266); an embedded raster mask; the file stays rectangular with transparency outside. |
| SHP-18 | Recompose a layout-generated design at a new aspect ratio | `adapt-layout` with `recompose: true` | 1 · <1 | E | Since 0.24; rebuilds generated layout layers from the saved recipe, replacing manual changes to them. |
| SHP-21 | QR code or barcode (Code 128, EAN-13) as a vector layer | `qr`, `barcode` | 1 · <1 | E | Since 0.22; `${variables}` re-encode per merge row; `codes` check. |
| SHP-22 | Center text in a shape's body (bubble, badge, frame) | `text` `within`, `place` `within`, `align` `box: "content"` | 1 · <1 | E | Since 0.22; shapes report `content_bounds`. |

### Effects and finishing

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PHO-01 | Brightness, contrast, saturation, exposure, gamma or hue | effect operations | 1 · <1 | E | Nondestructive stack. |
| PHO-02 | Black and white, invert, posterize or threshold | effect operations | 1 · <1 | E | |
| PHO-03 | Blur, sharpen or denoise a layer | `blur`, `sharpen`, `denoise` | 1 · <1 | E | |
| PHO-04 | Auto tone, auto color, auto contrast | `auto-tone` … | 1 · <1 | E | |
| PHO-05 | Apply a LUT | `lookup` | 1 · <1 | E | An ordinary stack effect since 0.21. |
| PHO-06 | Reorder, disable or remove an effect | `effect-move`, `effect disable` | 1 · <1 | E | |
| ILL-01 | Add a finishing look: glow, neon, soft/hard shadow, outline, grain, paper, film, duotone, risograph, halftone, watercolor, sketch | `look` | 1 · <1 | E | 20 looks; some export to SVG as raster. |
| ILL-02 | Apply one of 19 artistic filters (oil paint, mosaic …) | `filter` | 1 · <1 | E | Seeded and deterministic. |
| ILL-03 | Make an edge look torn, or make vector art look hand-made | `tear`, `irregular` | 1 · <1 | E | `--remove` undoes. |
| ILL-04 | Grow an organic form (flower, tree, fern, shell, coral, mushroom …) | `organic PRESET` | 1 · <1 | E | 33 presets, editable paths, reseedable. |
| ILL-05 | Add paint drips and relief, each controlled on its own | `paint` with `settings.drip`, `relief`, `light_angle` | 1 · <1 | E | Since 0.24 (#258); deterministic visual simulation, not a fluid solver. |

### Data and diagrams

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DAT-01 | Bar, stacked, 100 %, horizontal, line, area, pie or donut chart from inline data | `chart` | 1 · <1 | E | One editable vector group with axes and legend. |
| DAT-02 | Chart straight from a CSV in the workspace | `chart --csv` | 1 · <1 | E | |
| DAT-03 | Change one value, add a row or reload the CSV | `chart-data` | 1 · <1 | M:T08 R2 | Same layer IDs survive. |
| DAT-04 | Flowchart from a line of text (`A -> B -> C`) | `diagram-from-text` | 1 · <1 | E | Layered, tree, radial, mindmap and grid layouts. Since 0.23 it follows the document palette and dark mode. |

### Export

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DOC-20 | Export PNG, JPEG, WebP or TIFF | `vixl_export_file` | 1 · <1 | E | RGB PNG by default since 0.20. |
| DOC-21 | Export at 2× or 3× for screens | `export --scale 2x`, `export-screens` | 1 · <1 | E | |
| DOC-22 | Export editable SVG | `vixl_export_file` `.svg` | 1 · <1 | E | Strict mode rejects raster content. Since 0.24 supported blend modes stay vector as `mix-blend-mode` (#231). |
| DOC-23 | Export vector PDF with selectable text | `.pdf` | 1 · <1 | E | |
| DOC-24 | Export a CMYK TIFF/JPEG/PDF for print | `export --cmyk [--icc …]` | 3 · <1 | M:eval:print-cmyk | |
| DOC-25 | Soft-proof or simulate color-vision deficiency | `export --proof`, `--simulate deuteranopia` | 1 · <1 | E | |
| DOC-26 | Favicon ICO or a full web/Apple/Android icon set | `export .ico`, `vixl_export_icons` | 1 · <1 | E | |
| DOC-27 | Render a quick preview, or zoom on a region | `vixl_render_preview(region=…)` | 1 · <1 | E | Draft proxies are fast. |
| DOC-28 | Export a self-contained HTML page of the design | `export FILE.html` | 1 · <1 | E | |
| DOC-29 | Keep a still export under a byte budget | `export --max-bytes N` | 1 · <1 | E | Warns and names heavy grain/paper layers. |
| DOC-30 | Layered PSD for a designer | `vixl_export_file` `.psd` | 1 · <1 | E | Since 0.22; pixel layers with names, blend modes and groups; text is pixels. |

### Checks and discovery

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| QA-01 | Run design checks (bounds, overlap, contrast, safe area, legibility) | `vixl_check` | 1 · <1 | E | Fix-level vs review-level findings. Since 0.24 `passed` is false while any finding needs a fix, warnings included; `by_action` separates them (#464). |
| QA-02 | Check spacing is equal or matches an expected gap | `vixl_measure_spacing` | 1 · <1 | E | |
| QA-03 | Sample a pixel or read a histogram | `vixl_pixels_inspect`, `sample`, `histogram` | 1 · <1 | E | |
| QA-04 | Validate against a named profile or inline assertions | `vixl_validate` | 1 · <1 | E | |
| QA-05 | Compare two revisions visually | `vixl_render_compare` | 1 · <1 | E | |
| QA-06 | Check print readiness (ink limit, effective ppi, bleed) | `check --checks print` | 1 · <1 | E | |
| QA-07 | Check color-vision safety of text and chart series | `check --checks color_vision` | 1 · <1 | E | Other adjacent fills not compared yet. |
| QA-08 | Check a design against a named style (Swiss, Bauhaus …) | `check --checks style` | 1 · <1 | E | 28 styles. |
| AGT-01 | Ask what to make and with which tools for a brief | `vixl_guide(brief)` | 1 · <1 | E | 20 kinds: poster, logo, character, comic, form … |
| AGT-02 | Look up fields and gotchas for a topic | `vixl_capabilities(topic)` | 1 · <1 | E | |
| AGT-03 | Read the JSON schema of one operation | `vixl_operation_schema` | 1 · <1 | E | |
| AGT-04 | Browse layouts, styles, brushes, resources or workflows | `vixl_layouts_list`, `vixl_styles`, `vixl_brushes_list`, `vixl_resources_list`, `vixl_workflow_schema` | 1 · <1 | E | |
| AGT-05 | Check the installed version and update it | `vixl --version`, `vixl update` | 1 · <1 | E | Verified Windows updater with rollback. |
| AGT-06 | Read the house style: craft rules, tiers, variety levels or one purpose's profile | `vixl_resource_get(kind="house-style")`, `vixl house show PURPOSE` | 1 · <1 | E | Purposes: poster, social, slides, document, form, diagram, logo, motion. |

### Provider-backed (one call each)

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| AI-01 | Describe an image | `vixl ai describe` | 1 · <1 | E | [AI] |
| AI-02 | Read text from an image (OCR) | `vixl ocr` | 1 · <1 | E | [AI] |
| AI-03 | Detect objects or faces | `vixl detect objects|faces` | 1 · <1 | E | [AI] |
| AI-04 | Upscale an image | `vixl ai upscale` | 1 · <1 | E | [AI] |
| AI-05 | Remove a background | `vixl ai background-remove` | 1 · <1 | E | [AI] needs a mask-producing provider. |
| AI-06 | Generate an image from a prompt | `vixl generate --prompt` | 1 · <1 | E | [AI] Provenance is kept for regeneration. |

---

## T1 · Quick (3–10 calls, 1–3 minutes)

### Measured eval tasks

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DOC-30 | Copy the exact text of a layer from one document into another | two open documents, `text-set` | 3 · 1 | M:eval:copy-between-documents | |
| SHP-20 | Three squares in a row with exactly equal gaps | `shape` ×3, `distribute`, spacing check | 4 · 1 | M:eval:equal-spacing | |
| QA-10 | Find and fix every layout error without rewording | `vixl_check` → fix → recheck | 6 · 2 | M:eval:fix-layout | |
| TXT-20 | Apply a named font pairing to a layout | `vixl_font_pair`, `layout-apply` | 5 · 1–2 | M:eval:font-pairing | |
| FRM-01 | Fill a badge form once per CSV row into one PDF | `vixl_workflow` form-fill | 6 · 2 | M:eval:form-batch-fill | |
| FRM-02 | Build a letter-size registration form with labelled fields | `field` operations, fillable PDF | 7 · 2 | M:eval:form-registration | |
| SOC-01 | Fill a named layout (hero-statement) with given copy | `layout-apply` | 3 · 1 | M:eval:layout-filled | |
| PHO-10 | Photo on top, caption panel below, for a 1080×1350 post | import, `scale`, `shape`, `text` | 7 · 2 | M:eval:photo-caption | |
| COL-01 | Restore a mistakenly deleted layer without losing later edits | `vixl_history` | 5 · 1–2 | M:eval:restore-deleted | |
| SOC-02 | Roll a design direction with locks and apply it | `vixl_roll` | 5 · 1–2 | M:eval:roll-applied | Use `unfilled=omit` for empty slots. The roll is weighted by purpose (`purpose`, else the document size) and gated by `variety`; `locks={tier: "bold"}` explores one tier. |
| SOC-03 | Story with gradient and an evenly spaced three-item list | `gradient`, `text` ×3, distribute | 5 · 1–2 | M:eval:story-list | |
| BRD-01 | Import an SVG logo as editable geometry, edit and re-export | `vixl_import_document` svg editable | 4 · 1 | M:eval:svg-logo-import | |
| SOC-04 | Start from a built-in template with title and subtitle | `vixl_template_create` | 4 · 1 | M:eval:template-creation | 43 templates. |
| MOT-01 | Ball moving across the canvas over one second, exported as GIF | `timeline-set`, `animate`, `vixl_export_timeline` | 7 · 2 | M:eval:timeline-motion | |
| PRD-01 | Banner with a variable-driven headline, rendered for several cities | `variable set`, `render --set` | 6 · 2 | M:eval:variable-variants | |
| QA-11 | Save a check suite and make an edit that only commits if it passes | `vixl_workflow` act | 8 · 2 | M:eval:workflow-checked-edit | |
| QA-24 | Turn a brief into tests (hierarchy, spacing, margins, contrast, balance) and run them with every batch before previewing | `suite-set`, `vixl_operations_apply(suites=true)`, `vixl_guide("testing")` | 3–5 · 1 | E | Starter suites per kind of work; `vixl_guide(kind)` lists one under `tests`. |

### Social, web and simple graphics

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| SOC-10 | Quote card | `layout-apply quote-card`, look | 4–6 · 1–2 | E | |
| SOC-11 | Simple announcement or "we're hiring" post | template or `balanced-announcement` | 4–6 · 1–2 | E | |
| SOC-12 | Open Graph / link preview image | size `og-image`, layout | 4–6 · 1–2 | E | |
| SOC-13 | Profile picture or avatar with initials | `logo-avatar` size, `monogram` layout | 3–5 · 1 | E | |
| SOC-14 | Email header or email signature banner | `email-header` size, `banner` layout | 4–6 · 1–2 | E | |
| SOC-15 | Discord emoji or Twitch panel | named sizes, shape + text | 4–8 · 1–2 | E | Whole emoji packs with platform checks: BRD-11. |
| SOC-16 | Big-number stat card | `big-number` layout | 3–5 · 1 | E | |
| SOC-17 | Phone or desktop wallpaper from gradients and organic forms | `gradient`, `organic`, look | 5–8 · 1–2 | E | |
| SOC-18 | Text-only typographic poster for screen | `typographic-poster` layout, font pair | 5–8 · 2 | E | |
| SOC-19 | Event promo from the social-event-promo template | `vixl_template_create` | 4–6 · 1–2 | E | |
| SOC-20 | Watermark or logo stamp on a photo | import, `opacity`, `align` | 4–5 · 1 | E | |
| SOC-82 | A finished card in one call (create, layout, fonts, look, check, export) | `vixl_compose` | 1–3 · 1 | E | Since 0.22; atomic, errors name the step. |
| SOC-83 | Meme from your own image (top/bottom, comparison, four-panel, reaction GIF) | `vixl_compose` with a meme layout and `image`/`images` paths or URLs (or `layout-apply` with imported assets) | 1 · 1 | E | Since 0.22; bring your own images. One call since 0.23 (#368); the pictures bleed (`allow_crop`) and the captions stay in the safe area, so `check` passes on sized canvases. |

### Print and stationery

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRN-01 | Business card from the template | `vixl_template_create business-card` | 4–6 · 1–2 | E | |
| PRN-02 | Certificate from the template | `print-certificate` | 4–6 · 1–2 | E | |
| PRN-03 | Simple flyer from the template | `print-flyer` | 4–6 · 1–2 | E | |
| PRN-04 | Postcard or invitation from a template | `print-postcard`, `print-invitation` | 4–6 · 1–2 | E | |
| PRN-05 | Event ticket, bookmark, label, sticker or door hanger | named size + layout | 5–8 · 2 | E | |
| PRN-06 | Gallery or museum wall label | `gallery-label` layout | 3–5 · 1 | E | |

### Brand, icons and color

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| BRD-02 | Monogram or minimal mark | `monogram`, `minimal-mark` layout | 4–6 · 1–2 | E | |
| BRD-03 | Turn an existing logo into favicons and app icons | `vixl_export_icons --set all` | 2–3 · <1 | E | |
| BRD-04 | Wordmark in a paired font | `wordmark` size, `text`, font pair | 4–6 · 1–2 | E | |
| CLR-10 | Recolor a design to a different palette | `palette apply`, swatch edits | 3–5 · 1 | E | |
| CLR-11 | Check how much of a design stays inside a palette | `vixl_workflow` palette-check | 2–3 · <1 | E | |
| BRD-51 | Logo package: colour/mono/reversed variants, lockups, SVG/PDF/PNG, icons, social images, usage sheet | `vixl_workflow` logo-package | 1–3 · 1–3 | E | Since 0.22; recolouring is heuristic and reported; no EPS. |
| BRD-11 | Custom emoji pack: replace or add `:shortcodes:`, check platform requirements, export PNG/SVG with editable masters | `vixl emoji`, `emoji-replace`, `emoji-template`, `emoji-requirements`, `emoji-export` | 3–8 · 1–2 | E | Since 0.24; Discord/Slack upload instructions and an offline preview; CC BY-SA 4.0 licences travel with the pack. |

### Data and diagrams

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DAT-10 | Titled chart card for social | size, `chart`, `text`, check | 4–6 · 1–2 | E | |
| DAT-11 | Mind map or org chart | `diagram --layout mindmap|tree` | 3–5 · 1 | E | |
| DAT-12 | Edit diagram nodes, labels or remove a node | `diagram-set` | 2–3 · <1 | E | |
| DAT-13 | Export a chart as a native PowerPoint chart with data | `export .pptx` | 2–3 · <1 | E | |

### Illustration, effects and photo

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| ILL-10 | Mandala or rosette from one petal | `organic petal`/`shape`, `radial-repeat --mirror` | 3–5 · 1 | E | |
| ILL-11 | Sunburst or rays background | `shape`, `radial-repeat` | 3–4 · 1 | E | |
| ILL-12 | Simple flower or tree illustration | `organic`, gradient sky | 3–5 · 1 | E | |
| ILL-13 | Apply a saved effect workflow to a new image | `vixl_workflow` effect-run | 2–3 · <1 | E | |
| ILL-14 | Speech, thought, shout or whisper bubble that follows a character | bubble layer | 2–3 · <1 | E | Sizes to its text. |
| PHO-11 | Crop, straighten and resize a photo | `crop`, `rotate`, `resize` | 3–4 · 1 | E | |
| PHO-12 | Duotone or risograph poster from a photo | import, `look duotone|risograph` | 3–4 · 1 | E | |
| PHO-13 | Vignette, grain or film finish on a photo | effects/looks | 2–4 · <1 | E | |
| PHO-14 | Select by color, wand or lasso and adjust only that area | `select`, effect | 3–4 · 1 | E | |
| PHO-15 | Clone-stamp a blemish | clone stamp | 2–4 · <1 | E | |
| BLK-11 | Seamless random scatter for patterns | `pattern-scatter`, `pattern-fill` | 2–4 · 1 | E | Since 0.22; reports a seam score. |
| ILL-51 | Scatter motifs inside or along a shape, or fur on a mascot | `scatter` (`preset: fur`), `plush` look | 1–3 · 1 | E | Since 0.22. |

### Motion and pixels

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| MOT-02 | Fade-in, slide-in or pop-in entrance on a finished still | `animate-preset` | 3–5 · 1 | E | |
| MOT-03 | Pulse, spin or bob loop as a seamless GIF | `animate-preset`, `loop_mode: seamless` | 3–5 · 1 | E | `poster` frame option. |
| MOT-04 | Typewriter caption | caption with typewriter animation | 3–4 · 1 | E | |
| MOT-05 | Preview poster, middle and last frames at phone width | `vixl_timeline_preview(times=…)` | 1–2 · <1 | E | |
| MOT-06 | Analyse an audio file (levels, clipping, silence, onsets) | `vixl_workflow` audio-analyze | 1–2 · <1 | E | |
| MOT-07 | Sample frames from a video as a contact sheet | `vixl_workflow` video-sample | 1–2 · <1 | E | [ffmpeg] |
| MOT-08 | Plan a lyric video and see the timed lines without rendering | `vixl_workflow` lyric-video-plan | 1–2 · <1 | E | |
| PIX-01 | Small pixel-art icon from rows of palette indices | `pixel-art` | 2–4 · <1 | E | |
| PIX-02 | Palette-swap an existing sprite | `pixel-palette` | 2 · <1 | E | |
| PIX-03 | Export saved frames as GIF/APNG/sprite sheet at whole-number scale | `vixl_export_animation` | 1–2 · <1 | E | |
| BLK-12 | Per-character, per-word or per-line text animation | `text-animate` | 2–4 · 1 | E | Since 0.22; text stays one editable layer. |
| MOT-09 | Six-second square loop for a tip, launch or event | `vixl_template_create` video-tip/video-launch/video-event, `vixl_export_timeline` | 3–5 · 1 | E | Since 0.24 (#179); fill title, subtitle and cta, then check a contact sheet and pick the poster time. |
| MOT-13 | Pose a character over time with its joints kept attached | `character-pose` with `time` | 3–6 · 1 | E | Since 0.24 (#472); the rig is solved on every frame; do not also key position/rotation on the same limbs. |

### Production, forms and review

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRD-02 | Render one image per CSV row from a template | `render --data rows.csv` | 2–4 · 1 | E | |
| PRD-03 | Place a saved library component into a document | `vixl_workflow` library-place | 2–3 · <1 | E | |
| PRD-04 | Link another `.vixl` as a live layer and refresh it after edits | `link`, `link-refresh` | 2–3 · <1 | E | |
| FRM-03 | Fill one form with values into a flattened or editable PDF | `form fill --set` | 1–2 · <1 | E | |
| FRM-04 | Check a form with worst-case sample values | `check --checks form --sample worst` | 1–2 · <1 | E | |
| QA-12 | Leave, list and resolve review notes | `vixl_review_notes` | 2–3 · <1 | E | |
| COL-02 | Fork a branch, edit it and see its status | `vixl_workflow` branch-fork/branch-status | 3–4 · 1 | E | |
| AGT-10 | Connect an MCP client to a workspace | `vixl mcp --workspace . --tools core --schema slim` | config · 1–3 | E | |
| AGT-11 | Display a design inline in a notebook | `Project.show()` | 1–2 · <1 | E | |
| BLK-10 | Lookups or case changes inside a data merge | `${name\|upper}`, `${role\|map:colors}`, `variable-map` | 2–4 · 1 | E | Since 0.22. |
| QA-22 | Proof page for human sign-off with approve/reject | `vixl_workflow` proof | 1–2 · 1 | E | Since 0.22; offline HTML, decisions download as JSON. |
| QA-23 | Check `.vixl` files in pull requests | GitHub Action (`action.yml`), `vixl diff` | 1 · CI | E | Since 0.22; see [CI](ci.md). |

### Provider-backed

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| AI-10 | Remove an object and fill the hole | `vixl ai remove`, `content-aware-fill` | 2–3 · <1 | E | [AI] |
| AI-11 | Select a subject or a named object and mask it | `vixl ai select-subject`, `select object LABEL` | 2–3 · <1 | E | [AI] |
| AI-12 | Extend the canvas (outpaint) | `vixl ai extend` | 2–3 · <1 | E | [AI] Freezes constraints at their positions. |
| AI-13 | Image-to-image restyle or inpaint a selection | `generate` with source/mask | 2–4 · 1 | E | [AI] |
| AI-14 | Regenerate a generated layer with a new seed | `vixl ai regenerate` | 1–2 · <1 | E | [AI] |
| AI-15 | Ask a planner to turn a sentence into operations | `vixl ask PROMPT --apply` | 1–2 · <1 | E | [AI] |

---

## T2 · Standard (10–40 calls, 2–5 minutes)

### Measured briefs

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| ILL-20 | A picture: an illustrated scene from a short brief | gradients, shapes, organic, looks | 20 · 3.2 | M:T01 | Round 2 sometimes moved elements it was told to keep. |
| SOC-30 | Social post with exact copy and layout | layout, fonts, check, preview | 29 · 2.4 | M:T02 | |
| DAT-20 | Infographic from a small data table | `chart`, text, check | 18 · 1.4 | M:T08 | Totals and callouts are still typed by hand. |
| FRM-10 | Fillable PDF form with validation (email, range, date) | `field`, `form settings`, `export --fillable` | 25 · 3.4 | M:T06 | |
| PIX-10 | Pixel-art sprite with named animations | `pixel-art`, `frame-save`, `animation-set` | 23 · 3.7 | M:T13 | One `frames-edit` recolors every frame. |
| MOT-10 | Animated intro (logo/title reveal) | timeline, presets, stroke draw-on | 38 · 4.0 | M:T12 | |
| PRN-10 | Print poster with bleed, CMYK PDF, TrimBox/BleedBox | print size, layout, `export --cmyk` | 38 · 6.3 | M:T03 | Fewer calls than T3 but slower: print checks. |
| SOC-31 | YouTube thumbnail with large headline and subtitle | size, `text`, shapes, check | 13 · 3 | M:eval:youtube-thumbnail | |

### Measured revisions (round 2 of a finished brief)

| ID | Use case | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- |
| ILL-21 | Revise an illustrated scene | 25 · 3.3 | M:T01 R2 | |
| SOC-32 | Revise copy on a social post | 26 · 2.4 | M:T02 R2 | Only edited rows change. |
| PRN-11 | Revise copy on a print poster | 25 · 2.6 | M:T03 R2 | |
| BRD-10 | Revise a logo and icon kit | 30 · 2.2 | M:T04 R2 | Live links keep marks byte-identical. |
| DEK-10 | Revise a slide deck | 29 · 2.1 | M:T05 R2 | |
| FRM-11 | Revise a fillable form | 26 · 2.5 | M:T06 R2 | |
| PRD-10 | Add a person to a name-badge run | 20 · 1.5 | M:T07 R2 | A CSV edit plus a re-run of the merge. |
| DAT-21 | Update an infographic's data | 24 · 1.5 | M:T08 R2 | One `chart-data` cell. |
| PHO-20 | Revise a photo correction | 26 · 2.1 | M:T10 R2 | |
| DRW-10 | Revise cleaned-up hand drawing | 33 · 2.9 | M:T11 R2 | |
| MOT-11 | Revise an animated intro | 23 · 2.5 | M:T12 R2 | |
| PIX-11 | Recolor or retime a sprite | 28 · 2.8 | M:T13 R2 | |
| MOT-12 | Shift lyric timing in a lyric video | 30 · 5.4 | M:T14 R2 | One `offset` field; time is the re-render. |
| ILL-22 | Revise a seamless pattern | 27 · 2.5 | M:T15 R2 | Keeps 87 % of the original ink. |
| PRN-12 | Change prices on a café menu | 17 · 1.6 | M:T16 R2 | Per-price layers make it a direct edit. |

### Social, web and ads

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| SOC-40 | Product card with photo, price and CTA | `product-card` layout, import | 12–20 · 2–3 | E | |
| SOC-41 | Web hero or landing-page header | `web-hero`, `split-screen` layout | 12–20 · 2–3 | E | |
| SOC-42 | Blog featured image | `blog-featured` size, layout, look | 10–15 · 2 | E | |
| SOC-43 | LinkedIn/X/Facebook/YouTube banner | named size, `banner` layout | 10–18 · 2–3 | E | Safe zones for platform UI. |
| SOC-44 | Podcast or album cover art | `album-art` size, illustration, type | 15–25 · 3 | E | |
| SOC-45 | Pinterest pin with long layout | `pinterest-long` size, `f-pattern` | 12–20 · 2–3 | E | |
| SOC-46 | Post in a named design style (Bauhaus, vaporwave, Memphis …) | `vixl_styles` apply + check | 15–25 · 3 | E | |
| SOC-47 | Compare a few rolled directions and pick one | `vixl_roll` ×3–5, previews | 10–15 · 2–3 | E | |
| SOC-48 | Bento-grid feature summary | `bento-grid` layout | 12–20 · 2–3 | E | |
| SOC-49 | Marketing pricing or testimonials block | `marketing-pricing`, `marketing-testimonials` templates | 10–18 · 2–3 | E | |
| SOC-50 | Single display ad (medium rectangle, leaderboard) | IAB size, `banner` layout | 10–15 · 2 | E | |
| SOC-51 | Twitch offline screen or stream overlay frame | named sizes, shapes, glow/neon | 12–20 · 2–3 | E | |
| SOC-52 | Game cover or Steam-style banner | `game-cover`, illustration, title | 20–35 · 3–5 | E | |
| SOC-53 | App Store or Play feature graphic | `play-feature-graphic`, screenshot import | 15–25 · 3 | E | |

### Print

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRN-20 | Custom invitation (wedding, party) in Art Deco or minimal style | `centered-axis` / `quiet-invitation`, style | 15–25 · 3 | E | |
| PRN-21 | Greeting card (front + inside as pages) | `greeting-card` size, pages | 15–25 · 3 | E | |
| PRN-22 | Book cover (front only) | `book-6x9`, typography, illustration | 15–30 · 3–4 | E | Spine/back wrap is T3. |
| PRN-23 | Letterhead and envelope | `letterhead`, `envelope-10` | 12–20 · 2–3 | E | |
| PRN-24 | Business card front and back with bleed and CMYK PDF | pages, `--bleed`, `export --cmyk` | 15–25 · 3 | E | Vector DeviceCMYK pages. |
| PRN-25 | Rack card or one-page flyer with photo | `rack-card`, `photo-caption` | 15–25 · 3 | E | |
| PRN-26 | T-shirt, tote or mug-wrap print | named sizes, transparent export | 10–20 · 2–3 | E | |
| PRN-27 | CD or vinyl cover | `cd-cover`, `vinyl-cover` | 15–25 · 3 | E | |
| PRN-28 | Certificate customised in a period style | template, style, ornaments | 12–20 · 2–3 | E | |
| PRN-29 | Report or case-study cover page | `business-report-cover` template | 10–15 · 2 | E | |

### Brand and icons

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| BRD-20 | Single app icon designed for 16–1024 px | `app-icon` kind, `ios-app-icon` size | 15–25 · 3 | E | Judge at 16 px and in one color. |
| BRD-21 | Emblem or badge logo | `emblem` layout, shapes, path text | 15–25 · 3 | E | |
| BRD-22 | Simple logo (mark + wordmark, horizontal) | pen/shapes, pathfinder, `logo-horizontal` | 20–35 · 3–4 | E | Full kit is BRD-40. |
| BRD-23 | Logo lockup variants (stacked, horizontal, mark) via artboards | `artboard`, symbols | 15–25 · 3 | E | |

### Data, diagrams and documents

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DAT-30 | Process or swimlane-style flowchart with styled nodes | `diagram --nodes --edges`, check diagram | 10–20 · 2–3 | E | |
| DAT-31 | Timeline infographic (milestones on a line) | shapes, `repeat`, `place` on guide | 15–25 · 3 | E | |
| DAT-32 | KPI tiles / dashboard card | `stack`, `big-number`, small charts | 15–25 · 3 | E | No data binding between tiles and text. |
| DAT-33 | Comparison card (A vs B) | `slide-comparison` template or `split-screen` | 10–18 · 2–3 | E | |
| DAT-34 | Isometric illustration on an isometric grid | `grid --kind isometric`, `snap` | 20–35 · 3–5 | E | |
| DEK-20 | One-pager with title, body text and an image | `business-one-pager` template, rich text | 12–20 · 2–3 | E | |
| DEK-21 | Open letter or long quote in a text box with Markdown | rich text, `open-letter` layout | 8–12 · 2 | E | |

### Illustration and drawing

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| ILL-30 | Static character or mascot built from named parts | `character` kind, groups with pivots | 25–40 · 4–5 | E | |
| ILL-31 | Landscape scene with depth (sky, sun, hills, plants) | `scene` kind, organic, gradients | 20–30 · 3–4 | E | |
| ILL-32 | Botanical illustration with several organic forms | `organic` ×n, repeat, irregular | 12–20 · 2–3 | E | |
| ILL-33 | Painted texture or brush illustration (dozens of strokes) | `paint` with brushes | 15–30 · 3–4 | E | Strokes stay editable. |
| ILL-34 | Cut-paper style illustration | cut-paper guidance, `tear`, shadows | 20–35 · 3–5 | E | |
| ILL-35 | Pencil, charcoal, ink-wash, stipple or hatch finish | material finishes | 5–10 · 1–2 | E | |
| DRW-20 | Draw a custom vector icon with the pen and node edits | `pen`, path node ops, simplify/smooth | 15–30 · 3–4 | E | Path coordinates are literal local pixels. |
| DRW-21 | Envelope or corner-pin distortion of vector art | vector distortion | 5–10 · 1–2 | E | Animatable parameters. |
| DRW-22 | Outline a stroke or offset a path into a shape | outline/offset path | 3–6 · 1 | E | |

### Photo

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PHO-30 | Portrait touch-up with a saved script | `run portrait-cleanup.vixlscript` | 3–10 · 1–2 | E | Script in `examples/`. |
| PHO-31 | Color-correct a cast with white balance, temperature and tint | `white-balance`, adjustments, histogram | 10–20 · 2–3 | E | Rescaled in 0.21. |
| PHO-32 | Non-destructive grade with adjustment layers and a LUT | adjustment layers, `lookup` | 10–15 · 2 | E | |
| PHO-33 | Product photo on a new background | [AI] background-remove, gradient, shadow | 8–15 · 2 | E | [AI] |
| PHO-34 | Photo collage on a grid with image frames | `frame`, `replace-contents`, grid | 15–25 · 3 | E | |
| PHO-35 | Before/after comparison image | checkpoints, `vixl_render_compare` | 5–8 · 1–2 | E | |

### Motion and audio

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| MOT-20 | Kinetic text: words arriving one by one with stagger | `animate` with `stagger`, presets | 10–20 · 2–3 | E | Per-character beyond typewriter is not supported. |
| MOT-21 | Animated social post (MP4) from a finished still | presets, `export_timeline .mp4` | 10–15 · 2–3 | E | [ffmpeg] |
| MOT-22 | Looping background (drifting particles, waves) | particles, seamless loop | 10–20 · 2–3 | E | |
| MOT-23 | Animated chart (bars growing) | keyframes on chart layers | 10–20 · 2–3 | E | |
| MOT-24 | Synthesize a beep/whoosh, mix it with music and export WAV | audio tracks, `vixl_export_audio` | 5–10 · 1–2 | E | |
| MOT-25 | Character wave or nod using a reusable cycle | character cycles, pivots | 15–25 · 3 | E | |
| MOT-26 | Brush-stroke timelapse of a painting | paint layer reveal, timeline | 10–20 · 2–3 | E | |
| MOT-27 | App animation package: named states (idle, loading, success …) with light/dark themes for an app | state masters, `vixl_workflow` app-animation-package | 15–30 · 3–5 | E | Since 0.24 (#510); 1 call once the masters exist; WebP/GIF/APNG, reduced-motion PNGs, versioned manifest and HTML consumer; sources must be embedded. |

### Forms, production and review

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| FRM-20 | Survey or feedback form with radio buttons and dropdowns | `field` (radio, dropdown, checkbox) | 15–25 · 3 | E | |
| FRM-21 | Consent/waiver form with a required signature field | `field --kind signature --required` | 12–20 · 2–3 | E | |
| PRD-20 | Capture a design as a recipe with typed inputs | `vixl_workflow` capture | 5–10 · 1–2 | E | |
| PRD-21 | Plan a production spec and list its variants without rendering | `vixl_workflow` plan | 3–6 · 1 | E | |
| PRD-22 | Save a design to a component library and reuse it elsewhere | library-save, library-search, library-place | 5–8 · 1–2 | E | Placement is a raster snapshot. |
| QA-20 | Write a custom check suite for a brand (fonts, palette, logo clear space) | suite rules, `vixl_workflow` check | 10–20 · 2–3 | E | |
| QA-21 | Live human review in a browser while an agent edits | `vixl view` | setup · 1–2 | E | [server] |
| COL-10 | Three-way merge of a branch with explicit conflict resolution | branch-merge (dry run, then apply) | 5–12 · 2 | E | |
| AGT-20 | Run a 1,000-operation batch from a JSONL file | `operations_path`, `--check`, `--preview` | 1–3 · 1–2 | E | Batches go up to 10,000 operations. |
| AGT-21 | Drive Vixl from Python: build, apply, save, export | `Project` API | 10–30 lines · 5–10 | E | Human-written script. |

---

## T3 · Involved (40–70 calls, 4–8 minutes)

### Measured briefs

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRN-30 | Café menu with sections, items and prices | `print-menu` / `price-list`, per-price layers | 41 · 4.5 | M:T16 | No tab stops or dot leaders; baseline placement missing. |
| DEK-30 | Slide deck (title, content, chart, closing) to PPTX and PDF | pages, masters, notes, native PPTX chart | 47 · 4.5 | M:T05 | |
| PRD-30 | Name badges from a spreadsheet, imposed on print sheets | `vixl_workflow` merge-impose | 48 · 3.3 | M:T07 | Empty fields don't re-centre unless `stack --hide-if-empty`. |
| ILL-40 | Seamless repeating pattern | motifs, pattern-check, repeat | 61 · 7.5 | M:T15 | Scatter positions computed outside Vixl; no seamless scatter. |
| SOC-60 | One campaign in six sizes | `vixl_adapt_layout`, per-size fixes | 63 · 4.4 | M:T09 | adapt-layout output often needs every layer redone. Revision: 44 calls, 1.8 min. |
| PHO-40 | Photo correction (tilt, cast, exposure, noise) | effects, denoise, white balance, links | 63 · 5.0 | M:T10 | |
| DRW-30 | Hand drawing → clean vector art with fills | `drawing import/clean/vectorize/straighten/fill` | 64 · 5.7 | M:T11 | Gap closing bridges curves with straight lines. |
| MOT-30 | Lyric video from a song, an LRC file and a template | `lyric-video-build/export` | 40 · 6.4 | M:T14 | [ffmpeg] Audio resampled to 24 kHz. |

### Social and marketing

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| SOC-61 | Instagram carousel (5–8 slides) with consistent master | pages, `social-carousel` template | 40–60 · 5–7 | E | |
| SOC-62 | IAB display ad set (6–8 sizes) | `vixl_adapt_layout`, per-size checks | 50–70 · 5–8 | E | Same gaps as SOC-60. |
| SOC-63 | Story + post + thumbnail set for one launch | linked master, `adapt-layout` | 40–60 · 5–7 | E | |
| SOC-64 | Email campaign assets (header, banner, product tiles) | sizes, layouts, library components | 40–60 · 5–7 | E | |
| SOC-65 | App store screenshot set with captions (5 screens) | `iphone-screenshot` size, pages, imports | 40–60 · 5–7 | E | |

### Print and publishing

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRN-40 | Tri-fold or multi-panel brochure | pages, grids, text flow | 50–70 · 6–8 | E | No fold-mark helper; use guides. |
| PRN-41 | Newsletter with flowing columns across frames | `text-flow create/add-frame/link`, check flow | 40–60 · 5–7 | E | Orphans/widows control. |
| PRN-42 | Résumé or CV (two columns, rich text) | rich text, text flow, `offset-column` | 40–55 · 5–7 | E | |
| PRN-43 | Stationery set: card, letterhead, envelope, compliments slip | linked swatches/styles, artboards | 50–70 · 6–8 | E | |
| PRN-44 | Full book cover wrap (back, spine, front) with bleed | custom size, guides, CMYK PDF | 40–60 · 5–7 | E | Spine width computed by hand. |
| PRN-45 | Event poster series in three colorways | comps or variables, export per comp | 40–55 · 5–6 | E | |
| PRN-46 | Personalised invitations or place cards from a guest CSV | merge-impose | 30–50 · 3–5 | E | Like PRD-30. |
| PRN-47 | Product label or packaging face with print checks | `label`, print checks, CMYK | 40–60 · 5–7 | E | No dielines or spot colors. |

### Data and documents

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| DAT-40 | Multi-chart infographic poster with callouts | several `chart` groups, grid, text | 40–60 · 5–7 | E | Callout numbers typed by hand (no chart→text binding). |
| DAT-41 | One-page annual-report spread | charts, text flow, `editorial-grid` | 50–70 · 6–8 | E | |
| DAT-42 | Architecture or system diagram with grouped zones | `diagram`, groups, connectors | 40–60 · 5–7 | E | |
| DAT-43 | Table-like comparison or spec sheet | text + shapes on a grid | 40–70 · 5–8 | E | No table object; see Blocked. |
| DEK-31 | Pitch or teaching deck of 8–12 slides with notes | pages, masters, slide templates | 50–70 · 6–8 | E | |
| DEK-32 | HTML presenter deck with speaker notes and transitions | `export deck.html` | as DEK-30 + 2 | E | |
| DEK-33 | Zine or small booklet (8–16 pages) | pages, masters, PDF | 50–70 · 6–8 | E | No imposition for saddle-stitch reading order. |
| DEK-34 | Comic page with panels, captions and dialogue | `comic` kind, panel layout, bubbles | 40–70 · 5–8 | E | Art per panel adds a lot. |
| FRM-30 | Multi-page application form with tab order and validation | pages, `field`, `form settings` | 40–60 · 5–7 | E | |
| FRM-31 | Fill a form from a CSV with a bad row and get a per-row preflight | form-fill with jobs | 10–20 · 2–3 | E | Personal-data handling built in. |

### Illustration, game and motion

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| BRD-30 | Consistent icon set (8–12 glyphs on one grid) | shared grid, pen, symbols, `export-icons` | 50–80 · 6–10 | E | Borderline T4. |
| ILL-41 | Children's-book style spread | scene, character, rich text | 50–70 · 6–8 | E | |
| ILL-42 | Generative abstract artwork (seeded shapes, blends) | repeat, organic rules, seeds | 30–50 · 4–6 | E | |
| ILL-43 | Trading card front with frame, art slot, stats | template, variables, symbols | 40–60 · 5–7 | E | Series is PRD-40. |
| PIX-20 | Tileset and a small tile map | `pixel-art`, `repeat`, `tile-16/32` | 40–60 · 5–7 | E | |
| PIX-21 | Sprite with idle, walk and attack animations | frames, named animations, sheet | 40–60 · 5–7 | E | |
| PIX-22 | Pixel UI kit (buttons, panels, health bar) | pixel-draw, 9-slice by hand | 40–60 · 5–7 | E | |
| MOT-31 | Rigged character walk cycle | rig, two-bone IK, cycles, motion check | 40–60 · 5–8 | E | |
| MOT-32 | Parallax scene with a camera move | depth parallax, camera choreography | 40–60 · 5–8 | E | |
| MOT-33 | Explainer GIF with three short scenes | timeline markers, presets, captions | 40–60 · 5–8 | E | No nested compositions. |
| MOT-34 | Talking character with viseme cues and audio | visemes, audio tracks, MP4 | 40–70 · 6–8 | E | [ffmpeg] |
| MOT-35 | Lyric video with a title card, an end card and animated template graphics | `lyric-video-*` with `lead_in`, `tail`, an `outro` layer, template keyframes, per-cue `cue_animation` | 45–65 · 6–8 + render | E | [ffmpeg] No audio padding or post-build keyframe script; `segments` makes the full render resumable. |

### Production

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| PRD-31 | Render a production matrix (sizes × languages × colorways) with suites | `vixl_workflow` plan/run | 10–20 · 5+ render | E | Resumable; time is the render. |
| PRD-32 | Apply a brand change to every document in a project group, gated by suites | group-define, group-apply | 10–20 · 3–5 | E | Dry run by default; journal recovery. |
| PRD-33 | Install a plugin pack of palettes, templates and suites | `vixl_workflow` plugin-install | 2–4 · 1 | E | Packs are trusted code. |
| PRD-34 | Rebuild a merge after the CSV changed | `merge --rerun sheets.vixl --data new.csv` | 2–4 · 1 | E | |

---

## T4 · Large (70+ calls, 8–30 minutes)

| ID | Use case | Main route | Calls · min | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| BRD-40 | Logo and icon kit (mark, lockups, app icon, favicons, sheet) | pen, pathfinder, artboards, links, icon export | 104 · 7.8 | M:T04 | Was 169 calls on 0.18. |
| BRD-41 | Brand identity: palette, type, logo, business card, icons, ICO, HTML, palette suites | see exploration 02 | script 14 s | M:X02 | As an agent session: 150–250 calls, 20–40 min (E). |
| PRN-50 | Concert poster at tabloid size with warped/path text, soft proof, CMYK PDF/JPEG and SVG | see exploration 01 | script 1 min 17 s | M:X01 | Agent: 100–150 calls (E). |
| DEK-40 | Full pitch deck (15–20 slides) with charts, notes, PPTX/PDF/HTML | pages, masters, charts | 100–150 · 15–25 | E | |
| DAT-50 | Data infographic with several charts, constraints, color-vision checks, SVG/HTML/PDF | see exploration 08 | script 38 s | M:X08 | Agent: 80–120 calls (E). |
| PRD-40 | Trading card series with variables, CSV render, comps, suites, CMYK print sheet | see exploration 07 | script 1 min 43 s | M:X07 | |
| MOT-40 | Kinetic launch film with easings, staggers, animated effects; GIF/WebP/APNG/MP4/sheet | see exploration 03 | script 1 min 35 s | M:X03 | [ffmpeg] |
| PIX-40 | Pixel RPG asset pack: sprites, palette swaps, tileset, tile map, comps | see exploration 04 | script 25 s | M:X04 | |
| ILL-50 | Generative painting with thousands of seeded strokes and a timelapse | see exploration 05 | script 2 min 41 s | M:X05 | |
| PHO-50 | Non-destructive photo lab: every selection kind, masks, tonal stack, LUT, branches | see exploration 06 | script 26 s | M:X06 | |
| SOC-70 | Collaborative campaign: brand.json, rolls, 7 sizes, adapt-layout, branch merge, suite-gated group apply | see exploration 09 | script 1 min 23 s | M:X09 | |
| MOT-41 | Short character film: rig, walk/wave/jump, parallax, camera, crossfades, captions, audio | see exploration 10, `film-export` | script 1 min 57 s | M:X10 | [ffmpeg] Camera zoom softens the image. |
| DEK-41 | Multi-page comic (4–8 pages) | comic panels, characters, bubbles | 150+ · 30+ | E | |
| DEK-42 | Picture book (12–24 spreads) | pages, scenes, characters, rich text | 200+ · 45+ | E | Usually T5 across sessions. |
| MOT-42 | Animated explainer (30–60 s) with voice-over and captions | film spec, captions, audio mix | 100–200 · 20–40 | E | [ffmpeg] |

---

## T5 · Project (multiple sessions or a scripted pipeline)

| ID | Use case | Main route | Effort | Ev. | Notes |
| --- | --- | --- | --- | --- | --- |
| SOC-80 | Product launch kit across print, social, web, email and motion | brand group, linked masters, production runs | several sessions | E | |
| SOC-81 | Monthly social calendar (30 posts) from a content CSV | recipe capture + production run | 1 session setup, minutes per month | E | Cheap once the recipe exists. |
| BRD-50 | Brand system as a plugin pack with templates, palettes and check suites | resources, plugin pack, suites | 1–2 days | E | |
| PRD-50 | Personalised certificates or tickets for thousands of rows | merge-impose, durable jobs | setup 1 h, run unattended | E | |
| PRD-51 | Localised campaign in 10 languages with font fallbacks and checks | variables, `font-fallbacks`, suites | several hours | E | Automatic multi-font fallback is not implemented. |
| PRD-52 | Data-driven report generator (Python) re-run on each new dataset | `Project` API, `chart --csv`, templates | 1–2 days dev | E | |
| AGT-30 | Embed Vixl in another app through REST with auth | `vixl serve` | 1–3 days dev | E | [server] |
| AGT-31 | Gate pull requests on design checks in CI | `vixl validate`, suites, golden renders | 0.5–1 day | E | |
| AGT-32 | Run the agent eval suite against a new model or schema mode | `python -m evals.run --agent claude` | 1–2 h | E | Needs an API key. |
| AGT-33 | Compare Vixl with other tools on the 16 briefs | `evals/tool-comparison` kit | 1 day | E | |
| PIX-50 | Complete small game art set (characters, tiles, UI, title screen) | pixel tools, timelines, sheets | days | E | |
| MOT-50 | Music video beyond lyrics (scenes, characters, camera, audio) | film spec, rigs, parallax | days | E | No nested compositions or motion-path editor. |
| DEK-50 | Course slide library (100+ slides) on shared masters and components | pages, library components, group apply | days | E | |

---

## Blocked or only with a workaround

Each row names what is missing today. When a release closes a gap, move the row into a tier and
note the version.

| ID | Use case | Status | Workaround |
| --- | --- | --- | --- |
| BLK-01 | Edit in CMYK, use spot colors, control overprint or trapping | Out of scope (CMYK is export-only) | Design in sRGB, export CMYK with an ICC profile. |
| BLK-02 | Open Photoshop PSD or GIMP XCF projects, or save editable PSD type/vector layers | Not implemented (layered PSD export of pixel layers since 0.22) | Import flattened PNG/TIFF, or SVG/PDF; export `.psd` for pixel handoff. |
| BLK-03 | Develop camera RAW files or keep camera metadata | Not implemented | Develop elsewhere, import TIFF/JPEG. |
| BLK-04 | High-bit-depth (16/32-bit) editing | Not implemented (RGBA8) | – |
| BLK-05 | Draw live with a pressure tablet | No live input; pressure is explicit or simulated | Send stroke points with pressure values. |
| BLK-06 | Use a desktop GUI, TUI or web editor | Headless only | `vixl view` for live review. [server] |
| BLK-07 | Tables with tab stops, decimal tabs or dot leaders | Missing (T16) | One text layer per cell or price. |
| BLK-09 | Bind chart values into text, or one chart into another | Missing (T08) | Type totals and callouts by hand. |
| BLK-13 | Motion-path editor, nested compositions with their own timelines | Not implemented (group and child tracks compose; `attach` follows a moving layer since 0.22) | Keyframes per property; markers. |
| BLK-14 | Automatic discovery of fallback fonts for mixed scripts | Not implemented (fallbacks are listed by hand; weight- and slope-matched since 0.22) | Document-wide `font-fallbacks`. |
| BLK-15 | Reliable multi-size adaptation from one master | Partial: proportional `adapt-layout` leaves story text in bands, stretches decoration, can set banner text tiny (T02, T09); since 0.24 `recompose: true` rebuilds layout-generated designs (SHP-18) | Recompose layout-generated masters; fix other sizes after adapting. |
| BLK-17 | Video generation | Needs an explicitly configured gateway; no bundled model | [AI] |
| BLK-18 | Segmentation or background removal with OpenAI alone | Needs a mask-producing HTTP/ComfyUI provider | [AI] |
| BLK-19 | Branch merging by replay or real-time collaboration | Not implemented; shared-filesystem locks only | Branch fork/merge with explicit resolutions. |
| BLK-20 | Imposition for saddle-stitched booklets (reader → printer spreads) | Not implemented | Order pages by hand. |
| BLK-21 | Dielines, folds and packaging nets | Not implemented as a feature | Draw with guides and paths. |
| BLK-22 | Drawing fill bounded by the canvas edge | Missing (T11); strokes in a moved group's own coordinates work since 0.22 (`space: "group"`) | Add a boundary path. |
| BLK-23 | Live (active/scripted) SVG content | Not implemented; static SVG only | – |
| BLK-24 | Placing a library component as an editable group | Placement is a raster snapshot | Open the component as its own document and link it. |
| BLK-25 | Hard memory cap or execution timeout per call | Not implemented | Use OS/container limits. |

## Cost notes

- **Code is still cheaper per brief.** In the 0.20 tool comparison, writing HTML/SVG or Python took
  about a third of Vixl's calls (W 15, C 14 against V 41 median in round 1). Vixl wins on
  revisions that stay put, editable masters, print/PDF/PPTX/form output and built-in checks.
- **Revisions are where Vixl is cheapest.** Round 2 medians were 26 calls and 2.5 minutes, and
  several revisions became one data edit (`chart-data`, a CSV re-run, `frames-edit`, an `offset`).
- **One call can edit, check and preview.** Pass `check=true` and `preview=true` to
  `vixl_operations_apply` to save two calls on every iteration.
- **Shared servers slow everything down.** The 0.18 run had about 15 agents on one stdio server
  and calls timed out at 60 s while the server still finished. Count calls, not minutes.
- **Heavy work goes to jobs.** Calls longer than about 40 s return a job; poll `vixl_job`.

## Maintaining this list

- **Add a row** whenever you find a use case that isn't here: a user request, an issue, a new
  operation, a template, a size, a guide kind or a workflow action. Pick the domain prefix, take
  the next free number, and put it in the tier you expect. Mark it `E` until measured.
- **Measure when you can.** An eval run, a tool-comparison brief, an exploration build or a
  timed session all count. Replace `E` with the source and the version, and move the row if it
  lands in another tier.
- **Never renumber.** IDs stay attached to the use case so links and issues keep working.
- **Move blocked rows** into a tier when a release fixes them, and say so in the notes ("since 0.22").
- **Re-check after releases** that change the agent surface, schemas or defaults; the cost notes
  above came from the 0.20.0 tool comparison and the 0.21.0 exploration rebuild.

### Row template

```markdown
| PRE-NN | What someone wants to make or do | main operations or tools | calls · min | E | requirements, gaps, links |
```

### Ideas not yet placed

Add new ideas here when you are unsure of the tier, then move them into a table.

- Recipe card or cookbook page
- Real-estate listing flyer with a photo grid
- Sports team roster or match-day graphic
- Wedding seating chart
- Restaurant table tent
- Conference schedule (multi-track agenda)
- Floor plan or seating map on a grid
- Periodic-table style grid of tiles
- Calendar page or year planner
- Coupon or gift voucher with a unique code per row
- QR-code poster (needs a QR source image)
- Meme template with variable top/bottom text
- Book interior pages with running heads
- Map-style illustration with labelled regions
- Infographic for accessibility (color-vision-safe palette)
- Animated emoji or sticker pack
- Tarot or playing-card deck from a CSV
- Album lyric booklet
- Sign-up sheet or attendance form as a fillable PDF
