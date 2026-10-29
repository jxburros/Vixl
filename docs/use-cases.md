# Use-case catalog

[Documentation home](README.md) · [Visual gallery](gallery.md) · [Coverage and limitations](reference/coverage.md)

A running list of the things people and agents make with Vixl, grouped by how much work each one
takes **today**. It grows with each release. Where each row's figures come from (measured runs or estimates) is in
[use-case evidence](project/use-case-evidence.md), which also says how to add and move rows.

Effort figures describe an AI agent working through the MCP server (`vixl mcp`)
unless a row says otherwise. A person driving the CLI or a Python script needs a similar number of
commands; a reproducible script is usually faster to re-run than to write.

## How to read it

### Tiers

Tiers are set by **tool calls** first, because wall time depends on the machine, the model and how
many clients share one server. Minutes are typical agent wall time on a shared container.

| Tier | Calls | Typical time | What it looks like |
| --- | ---: | --- | --- |
| **T0 · One-shot** | 1–3 | under 1 min | One operation, one command or one lookup. |
| **T1 · Quick** | 3–10 | 1–3 min | A small brief with exact instructions. The agent eval suite (`evals/tasks`) lives here. |
| **T2 · Standard** | 10–40 | 2–5 min | One finished design from a loose brief, or a revision of a larger one. |
| **T3 · Involved** | 40–70 | 4–8 min | Several parts or pages, data, print output, cleanup or motion. |
| **T4 · Large** | 70+ | 8–30 min | A kit or system: many related files, a film, a full deck. |
| **T5 · Project** | many sessions | hours | Multi-document, multi-format or scripted pipelines. |
| **Blocked** | – | – | Not possible yet, or only with a workaround outside Vixl. |

### Requirement tags

`[AI]` needs a configured provider ([providers](reference/providers.md)). `[ffmpeg]` needs ffmpeg on `PATH`
for MP4/WebM/audio mux. `[server]` needs the `server` extra (REST, live view). `[Figma]` needs the user's own read-only Figma token in `FIGMA_TOKEN` and network access. `[pdf]` needs the
`pdf` extra for PDF page import (editable or as an image). No tag means the core install, offline.

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

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DOC-01 | Create a blank document at a named size (letter, instagram-post, youtube-thumbnail …) | `vixl_document(action='create', size=…)`, `vixl new NAME` | 1 · <1 | 151 named sizes with trim/safe guides; `vixl_reference('sizes')` to browse. |
| DOC-33 | Start a designed document from only a purpose (or nothing): size, palette background, design defaults and real fonts | `vixl_document(action='create', purpose=…)`, `vixl new --purpose slides`, `Project(purpose=…)` | 1 · <1 | Since 0.23; same result on every surface for the same `seed`. Fonts install from the cache or network with the first text. |
| DOC-02 | Create a print document with bleed and dpi | `vixl new letter --bleed --dpi 300` | 1 · <1 | Print sizes carry physical units, bleed and safe area. |
| DOC-03 | Open and inspect a `.vixl` (layers, bounds, fonts, effects) | `vixl_document(action='open')`, `vixl_document(action='inspect')` | 2 · <1 | `--detail brief|compact|full` controls response size. |
| DOC-04 | Rename, hide, show, raise, lower, duplicate or delete a layer | `vixl_apply` | 1 · <1 | Works on `targets` lists in one atomic batch. |
| DOC-05 | Change canvas size or switch to another preset (portrait ↔ landscape) | `canvas resize`, `canvas size NAME --landscape` | 1 · <1 | Constrained layers follow their anchors. |
| DOC-06 | Add a solid or gradient background | `solid`, `gradient` operations | 1 · <1 | Linear, radial and multi-stop gradients. |
| DOC-45 | Fill a shape (a card, a button, a blob, a logo path) with a gradient | `shape` with `fill_gradient` | 1 · <1 | Spans the shape's box; the stroke keeps its colour. Vector in SVG, PDF and PPTX. |
| DOC-07 | Import an image, SVG or PDF page as a layer | `import-image`, `import-document` | 1 · <1 | PDF needs `[pdf]`. SVG and PDF import as editable layers (`svg_mode=auto` draws unsupported elements as images; `appearance` imports one image). |
| DOC-08 | Undo, redo or jump back in history | `vixl_document(action='history')`, `vixl undo N` | 1 · <1 | Delta history with checkpoints. |
| DOC-09 | Save a named checkpoint before a risky edit | `vixl checkpoint NAME` | 1 · <1 | Restore with `checkout`. |
| DOC-10 | Set a document variable and render with an override | `variable set`, `render --set NAME=VALUE` | 2 · <1 |  |
| DOC-11 | Close one of several open documents | `vixl_document(action='close')` | 1 · <1 | Multi-document sessions pass `document=`. |
| DOC-12 | List the files in the workspace | `vixl_document(action='list')` | 1 · <1 |  |
| DOC-13 | Inspect what a document depends on and check it reproduces | `vixl dependencies`, `vixl reproduce --check` | 1 · <1 | Since 0.25 `--reference PNG` verifies against an approved render and `--write-lock`/`--lock` record and check dependency, font, asset and render drift (#512); without them it only proves the document renders. A version 2 lockfile also covers every page, artboard and sampled frame and the exports you record with it (QA-44). |
| BLK-16 | Relink the links in a copied `.vixl` | `links-relink {from, to}` | 1 · <1 | Since 0.22; sources beside the document are stored relative to it. |
| DOC-31 | Import an image from a URL with its credit and licence | `import-image` step (`url`, `credit`, `license`) | 1 · <1 | Since 0.22; https only, private hosts refused. |
| DOC-32 | Merge layers into one, or flatten the page | `merge-layers`, `flatten` | 1 · <1 | Since 0.22; undo restores the originals. |
| DOC-34 | Import a camera photo above the pixel limit (108 MP) | `import-image`, or `add` with `max_pixels` | 1 · <2 | Since 0.23; downsampled to the limit, sources up to 4× it. |
| DOC-35 | Edit a document of thousands of layers one operation at a time, or send a 10,000-operation batch | `vixl_apply` | 1 · <1 | Since 0.23 an edit lays out only the layers it depends on; was seconds per edit and minutes per batch (#284, #300). |
| DOC-36 | Unpack a `.vixl` into a readable source folder for Git review, and pack it back | `vixl unpack`, `vixl pack`, `vixl.project_folder` | 1–2 · <1 | Since 0.24 (#511); current state and registered fonts only, no undo history; packing validates paths, sizes and hashes. |
| DOC-38 | Re-import Vixl's own SVG as the same editable document (layers, names, live text, groups, effects) | `import-document` svg | 1 · <1 | The SVG carries its document; an SVG edited elsewhere imports element by element ([SVG round trip](guides/output/exporting.md#svg-round-trip), #334). |
| DOC-39 | Import a third-party SVG (shapes, text, groups, gradients, images, class styles) as editable layers | `import-document` svg | 1 · <1 | `<text>` stays live; filters, masks and clip paths need `svg_mode=auto`, which draws just those elements as images. |
| DOC-40 | Import a PDF page as editable text, paths and images | `import-document` pdf | 1 · <1 | `[pdf]`. Vixl's own PDFs come back at their pixel size; shadings and clipped content become image layers. Fonts (SVG import takes `font_map` too): `font_map`, registered families, then (Vixl's own PDFs) the same face from the document or the font cache; `fonts` in the result says how each matched, only `default` warns (#712). |
| DOC-41 | Read, generate or validate a `.vixl` file without Vixl | [file format](reference/file-format.md), `vixl schema document` | 1 · <1 | JSON Schema of `project.json`, checked against every `.vixl` in the repository. |
| DOC-42 | Import a Figma frame or page as editable layers, live text and stacks `[Figma]` | `import-document` format=figma, `vixl import URL --format figma`, `import_document(format="figma")`, REST `POST /import?format=figma` | 1 · <1 | [Mapping and known losses](guides/images/figma.md); the `report` lists every unmapped feature. Export back to Figma: #662. |
| DOC-43 | Open a document saved by an earlier release (format 1, pre-0.21 lookups, house-style versions, inset strokes) with its old look | `vixl convert OLD.vixl -o NEW.vixl`, `vixl convert DIR --out OUTDIR`, `vixl.convert.convert_file` | 1 · <1 | [Conversion kit](reference/converting.md): `--look preserve` writes formerly implicit behaviour into fields, `--look current` reports what changes; the report lists every change and what was not converted. |
| DOC-37 | Capture the desktop, a rectangle or a Windows window to PNG | `vixl_apply(workflow='screen-capture')` | 1 · <1 | Since 0.24 (#259); interactive local desktop only; OS screen permission may be needed. |

### Text and typography

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| TXT-01 | Add a text layer with size, color and position | `text` operation | 1 · <1 | Registered font names work in the batch. |
| TXT-02 | Change the words of an existing text layer | `text-set` | 1 · <1 | Keeps rich-text lists and spacing (fixed in 0.20). |
| TXT-03 | Browse fonts by category or mood | `vixl_reference('fonts')` | 1 · <1 |  |
| TXT-04 | Install a curated heading/body font pairing | `font-pair` | 1–2 · <1 | Bundled Noto Sans is a proofing fallback only. Since 0.23 a new document installs its rolled pairing (0 extra calls) when the font cache or network is available: at its first text, not at creation. |
| TXT-05 | Install one Google font or import a local font file | `font-install`, `import-font` | 1 · <1 |  |
| TXT-26 | Use a font installed on this machine by family, style or PostScript name, and list them | `text` `font: "Georgia Bold"`, `vixl font system`, `vixl_reference('fonts', view='installed')` | 1 · <1 | The face is embedded (collections extracted, variable instances made static); fontconfig, the Windows registry or the font folders; restricted licences warn, and are refused through services. |
| TXT-06 | Generate a modular type scale | `type-scale --base 16 --ratio golden` | 1 · <1 |  |
| TXT-07 | Read text metrics (ink box, baseline, cap height, x-height) | `vixl_check(action='measure')`, `info --target TEXT` | 1 · <1 |  |
| TXT-08 | Warp text (arc, flag, wave …) or set it along a path | `text` with `warp` / polyline placement | 1 · <1 | Outlined warp presets export as vectors. |
| TXT-09 | Define and apply a linked character/paragraph style | `style-define`, `style-apply` | 2 · <1 |  |
| TXT-10 | Flow a very long text (100,000 characters, even one unbroken word) through columns | `text-flow` | 1 · <1 | Since 0.23; a 100,000-character word took about 6 minutes (#335). |
| BLK-08 | Place text by its baseline | `baseline_y` on text/move, `align` `baseline`, `snap` to a baseline grid | 1 · <1 | Since 0.22. |
| TXT-11 | Use emoji in text with editable art (complete Unicode 17 sequences, joiners and flags) | `text`, `emoji-mode` | 1 · <1 | Since 0.24; VIXL art by default, `emoji-mode font` prefers the font; PDF/PPTX use a reported raster fallback. The artwork pack downloads once on first use (`vixl emoji artwork --download` ahead of going offline). |
| TXT-12 | Find an emoji or extract it as an editable `.vixl` master | `vixl emoji list`/`get`, `vixl_apply(workflow=…)` emoji-list/emoji-get | 1 · <1 | Since 0.24; 3,953 Unicode sequences plus 100 originals. |
| TXT-13 | Brand tracking and caps on text that changes (keyed lyric lines, `${variable}` values) | `text-set` with `tracking`, `text_transform` | 1 · <1 | Layer properties (#603); before, tracking needed a `text-style` match on fixed text and caps a pre-cased copy of the source. |
| TXT-14 | Set mixed Latin, Greek, Cyrillic and symbol text (⏻ ⎈ ⧉ ∮ 𝔸) offline without tofu | `text` | 1 · <1 | Noto Sans is the proofing face, with DejaVu Sans, Noto Sans Symbols, Symbols 2 and Math behind it (#419; DejaVu Sans was the proofing face before); CJK, Devanagari and Thai are TXT-23. |
| TXT-23 | Set Devanagari, Chinese, Japanese, Korean or Thai text without empty boxes | `text`; `font-cover` step, `vixl font cover` to embed | 0–1 · <1 | Unreleased (#684, #419): text draws such characters from a matching face already on the machine (font cache, `VIXL_CJK_PACK`) with no call and no download, and the apply warns that the document does not embed it; otherwise it warns with the exact `font-cover` step. `font-cover` installs the catalog Noto face per script (cache first) and appends it to `font-fallbacks`. With an empty cache it needs the network (offline it refuses and names the families). |
| TXT-15 | Set text on a stage (display, h1–h3, subtitle, lead, body, caption, citation, label) and spread 2–4 fonts across the stages | `text` with `stage`, `font-register` with a role or stage | 1–2 · <1 | Stages follow heading/body until a stage or brand role gets its own face. |
| TXT-16 | Break a heading into lines of even width, or keep one word off a paragraph's last line | `text-layout` `wrap: balance` / `pretty` | 1 · <1 | Craft plan 4a (T09, T14). Headings and layout headlines balance by default; the breaks are shared by PNG, SVG, PDF and PPTX. Before, a runt needed a hand line break. |
| BLK-07 | Tab stops and dot leaders in text (menus, price lists, contents pages) | `text` `tabs: [{at, align, leader}]` with `\t`; `table` column `leader` | 1 · <1 | Moved from Blocked (craft plan 4b, #213; T16): left, right, centre and decimal stops with leaders in PNG, SVG and PDF; native tab stops in PPTX with the leader written as characters. Before, leaders were drawn by hand. |
| TXT-17 | Two-tone headline: one or two words of a headline in the accent color | `layout-apply` `accent_words`; `text`/`text-set` `accent_words`; rich-text `[word]{accent}` or `{accent-bg}` | 1 · <1 | Craft plan 4c (T03, T09); before, a `text-style` match per word after the layout, with the box height fixed by hand. Unreleased (#650): any text layer takes `accent_words`, and the Markdown flags accent one word. |
| TXT-24 | Small caps for an eyebrow, byline or acronym in running text | `text`/`text-set` `text_transform: "small-caps"`; span `small_caps` | 1 · <1 | Unreleased (#652): the font's own small capitals (OpenType `smcp`) or synthesized ones, the same in PNG, SVG, PDF and PPTX (`cap="small"`). Before, uppercase at a smaller size in a second span, drawn lighter than the capitals. |
| TXT-25 | Hang a pull quote's opening quote (or a bullet) outside the text edge so the letters line up | `hanging_punctuation: true` on `text`, `text-set` or `rich-text` | 1 · <1 | Unreleased (#652), opt-in: wrapping, `fit-text` and the bounds checks use the shifted marks. Before, a separate quote layer placed by hand. |
| TXT-21 | Export the font drawn in a document as TTF, OTF or WOFF, or embed it for its own text | `vixl_export` `.ttf`/`.otf`/`.woff`, `font-build` | 1 · <1 | Unreleased; see [making a font](guides/text/custom-fonts.md). WOFF2 needs `brotli`. |

### Color

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| CLR-01 | Convert a color between hex, OKLCH, CMYK, Lab … | `vixl_reference('color')`, `color convert` | 1 · <1 | CSS Color 4/5, `kelvin()`, `cmyk()`, xkcd names. |
| CLR-02 | Measure contrast between two colors | `color contrast FG BG` | 1 · <1 |  |
| CLR-03 | Build a harmony (triadic, analogous …) or a tint/shade scale | `color harmony`, `color scale` | 1 · <1 |  |
| CLR-04 | Generate and register a palette from one seed color | `palette-generate NAME COLOR` | 1 · <1 |  |
| CLR-05 | Apply one of the 74 built-in palettes | `palette apply` | 1 · <1 |  |
| CLR-06 | Define brand swatches and use `@swatch` references | `swatch` | 1 · <1 | Modifiers like `lighten(@brand, 10%)`. |
| CLR-07 | Find a color by name (CSS or xkcd) | `color names QUERY` | 1 · <1 |  |
| CLR-12 | Delete a stray swatch without breaking the layers that use it | `swatch` with `delete` (`detach` keeps their colors) | 1 · <1 | Unreleased; refused with the list of users unless `detach`; undo restores it. |
| CLR-13 | A design with two or three accent colours, or none, shared equally or led by one | a roll (`locks={accents: 2, accent_representation: "skewed"}`), or `layout-apply` `direction: {accent_count: 2}` | 1 · <1 | Unreleased (#404): rolls draw one accent usually, two often, none or three rarely; `@accent-2`/`@accent-3` are contrast-checked and spread over the layout's rules, dots, labels and motif. Before, extra swatches and recolouring layers by hand. |
| CLR-14 | A rolled palette that follows the brief's mood (a coffee brief leans warm and earthy) | `vixl_reference(brief)` | 1 · <1 | Unreleased (#654): the brief's motif themes and mood words weight the palette (never filter it); the direction reports `mood_words` and a `motif_suggestion`. Before, a palette lock chosen by hand. |

### Shapes, layout and placement

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| SHP-01 | Add a rectangle, ellipse, polygon, star, arrow or line | `shape` | 1 · <1 | Large catalog: seals, chevrons, technical shapes, ornaments. |
| SHP-02 | Round or chamfer corners individually | `shape` corner fields | 1 · <1 |  |
| SHP-03 | Dashed, multi-stroke, tapered or arrow-headed strokes | stroke fields | 1 · <1 | Caps, joins, alignment, markers, width profiles. Since 0.27 a stroke on a closed shape sits inside its outline and flush with it (`stroke_align: inside`); paths, arcs, lines and open shapes center it. Same place in PNG, SVG, PDF and PowerPoint. |
| SHP-04 | Center a layer or align several to an edge | `align` | 1 · <1 |  |
| SHP-05 | Distribute layers with equal gaps | `distribute` | 1 · <1 |  |
| SHP-06 | Move, resize, scale, rotate, flip or skew a layer | transform operations | 1 · <1 | Fractional sizes, named pivots, affine matrices. |
| SHP-07 | Group, ungroup, clip one layer to another | `group`, `ungroup`, `clip` | 1 · <1 |  |
| SHP-23 | Add a part drawn later to an existing (rotated, scaled) group, or lift a part out | `reparent` | 1 · <1 | Since 0.23 (#382); keeps the render and the group's settings. |
| SHP-08 | Combine shapes (union, subtract, intersect, exclude) | `pathfinder` | 1 · <1 |  |
| SHP-09 | Add guides, a column grid, baseline grid, golden or thirds grid | `guide`, `grid` | 1 · <1 | Polar, isometric, hex, oblique and perspective grids too. |
| SHP-10 | Place or snap layers onto a guide | `place`, `snap` | 1 · <1 |  |
| SHP-11 | Repeat a layer in a row/grid or blend between two | `repeat`, `repeat-blend` | 1 · <1 |  |
| SHP-12 | Repeat a motif around a centre (rosette, sunburst) | `radial-repeat` | 1 · <1 | `--mirror` for kaleidoscope symmetry. |
| SHP-13 | Make a hug-content pill, badge, button or code window | `stack` with padding/background | 1 · <1 | Since 0.24 `gap` also takes shared spacing units (`"2u"`). |
| SHP-14 | Find empty space, margins or a hit-test point | `vixl_check(action='spatial')` | 1 · <1 |  |
| SHP-15 | Set opacity or a blend mode | `opacity` (0–1), `blend` | 1 · <1 |  |
| SHP-24 | Draw a translucent pen stroke (a highlighter line, a soft overlay curve) | `pen` with `opacity` | 1 · <1 | Unreleased; `opacity` and `rotation` at creation or edit, same in PNG, SVG and PDF. |
| SHP-16 | Pin a layer to an edge or another layer | `constrain` | 1 · <1 | One anchor per axis; cycles rejected. |
| SHP-17 | Frame an image in an irregular silhouette (ellipse, star, hexagon, heart or an SVG outline) | `frame` with `frame_shape` or `outline` | 1 · <1 | Since 0.24 (#266); an embedded raster mask; the file stays rectangular with transparency outside. |
| SHP-18 | Recompose a layout-generated design at a new aspect ratio | `adapt-layout` (the default while the layout is unedited; `recompose: true` after edits) | 1 · <1 | Since 0.24; rebuilds generated layout layers from the saved recipe. Unreleased (#653): the default for an unedited `layout-apply` document, reported as `recomposed` with a reason; `recompose: true` replaces manual changes. |
| SHP-31 | Header row, full-width cards, a feature grid or a wrapping tag row that re-flows on its own | `stack` with `justify: "space-between"`, `align: "stretch"`, `grow`, `wrap`, `direction: "grid"` + `columns`/`span` | 1 · <1 | Unreleased (#653); the CSS flexbox and grid names (`justify_content`, `flex_grow`, `grid_template_columns` …) are accepted. |
| SHP-32 | Re-arrange a design for another format and keep the arrangement the checks score best | `adapt-layout` `arrangements` (with `layer-intent` `priority` and `focal`) | 1 · <1 | Unreleased (#519); `outcome` says `needs_review` when no arrangement passes; required copy is never hidden or cut off; a photo's `focal` point stays in a cover crop. |
| SHP-21 | QR code or barcode (Code 128, EAN-13) as a vector layer | `qr`, `barcode` | 1 · <1 | Since 0.22; `${variables}` re-encode per merge row; `codes` check. |
| SHP-22 | Center text in a shape's body (bubble, badge, frame) | `text` `within`, `place` `within`, `align` `box: "content"` | 1 · <1 | Since 0.22; shapes report `content_bounds`. |
| SHP-25 | A callout note, a header or footer band, or a divider rule with a label | `container-place` `callout`, `band`, `labelled-rule` | 1 · <1 | Unreleased (#650): palette-role colors, optional icon and detail hide when empty; never rolled. Before, three or four shapes and texts placed by hand. |

### Effects and finishing

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PHO-01 | Brightness, contrast, saturation, exposure, gamma or hue | effect operations | 1 · <1 | Nondestructive stack. |
| PHO-02 | Black and white, invert, posterize or threshold | effect operations | 1 · <1 |  |
| PHO-03 | Blur, sharpen or denoise a layer | `blur`, `sharpen`, `denoise` | 1 · <1 |  |
| PHO-04 | Auto tone, auto color, auto contrast | `auto-tone` … | 1 · <1 |  |
| PHO-05 | Apply a LUT | `lookup` | 1 · <1 | An ordinary stack effect since 0.21. |
| PHO-06 | Reorder, disable or remove an effect | `effect-move`, `effect disable` | 1 · <1 |  |
| ILL-01 | Add a finishing look: glow, neon, soft/hard shadow, outline, grain, paper, film, duotone, risograph, halftone, watercolor, sketch | `look` | 1 · <1 | 20 looks; some export to SVG as raster. |
| ILL-02 | Apply one of 19 artistic filters (oil paint, mosaic …) | `filter` | 1 · <1 | Seeded and deterministic. |
| ILL-03 | Make an edge look torn, or make vector art look hand-made | `tear`, `irregular` | 1 · <1 | `--remove` undoes. |
| ILL-04 | Grow an organic form (flower, tree, fern, shell, coral, mushroom …) | `organic PRESET` | 1 · <1 | 34 presets, editable paths, reseedable. |
| ILL-05 | Add paint drips and relief, each controlled on its own | `paint` with `settings.drip`, `relief`, `light_angle` | 1 · <1 | Since 0.24 (#258); deterministic visual simulation, not a fluid solver. |
| ILL-54 | Atmosphere in a scene: a glow behind a light, stars clear of the copy, string lights or lanterns along a sagging wire, out-of-focus discs | `haze`, `star-field`, `string-lights`, `bokeh` | 1 · <1 | Craft plan 6a. Editable seeded groups, vector in every export. Was a generator script writing hundreds of shapes (M:T03). |
| ILL-55 | Reflection of a scene in water below a horizon, with ripples and a fade | `reflection` | 1 · <1 | Craft plan 6a. One raster layer; `reflection --target` re-renders it after the scene changes. Was hand-placed dashes (M:T03). |
| ILL-56 | Filled layered water: sea, harbor or lake bands with crests | `organic` preset `water` | 1 · <1 | Craft plan 6c. Replaces stroked wave lines (M:T09, T12). |
| ILL-57 | The concrete motif a brief implies (a cup with steam, a lighthouse in the sea, strung lanterns, a loaf, a snowflake, a balloon) | `vixl_reference` motifs; shapes `cup`, `steam`, `lighthouse`, `lantern`, `microphone`, `snowflake`, `leaf`, `book`, `balloon` | 1–3 · <1 | Craft plan 6b. Sixteen themes (coffee, coast, lake, market, night city, night sky, music, bakery, garden, winter, sport, tech, wellness, travel, books, party), each answering what the object is, what it emits or reflects and what frames it. |
| ILL-59 | Mist or fog between hills, over water or in front of a skyline, lighter toward the horizon | `haze` with `form: "fog"` (`layers`, `density`, `behind`) | 1 · <1 | Stacked soft bands that wash out toward the horizon, seeded, behind the layers you name so the foreground stays crisp. An editable vector group, as the other atmosphere operations; light falloff stays the `lighting` operation. |
| ILL-58 | Fill a shape with a material or textile texture (marble, terrazzo, linen, denim, leather, cobblestone, topographic lines, leopard, camouflage …) | `pattern-fill` with a built-in pattern | 1 · <1 | 72 seeded seamless patterns in four families; `pattern-list` describes each. |
| ILL-60 | Scaffold an object of a kind (a dog, a guitar, a person holding a guitar) as named placeholder parts to refine | `vixl_apply(workflow='object-plan', request={kind, height, apply: true})`, `vixl object plan KIND --apply` | 1 · <1 | Unreleased (#380). Placed by the kind's placements, proportions at mid-range, grouped, declared and named; every kind that lists parts passes the object check as generated. `with` nests sub-objects; `figure-plan` is its person template. |
| ILL-66 | Flat vector illustration in the house style: thin ink part lines, one hard offset shadow, a slight wobble and now and then a double or triple line | `organic PRESET`, `vixl_apply(workflow='object-plan', …)` in a document with a house style; `illustration: plain` opts out | 1 · <1 | Unreleased (#427). The default for new organic forms and object-plan scaffolds (`craft.illustration`); `object` `outline_lines` draws the extra lines. |
| ILL-61 | Outline an object the illustrator's way: one line around the silhouette with thin or no lines inside, or every part outlined alike | `{type: object, action: outline}` (`outline`, `interior`, `outline_color`, `outline_width`, `outline_lines`) | 1 · <1 | Unreleased (#379). One generated outline layer that follows moved parts in the same undo step; the part strokes it replaced come back with `outline-remove`; same unfilled line in PNG, SVG, PDF and PowerPoint. |
| ILL-62 | Place a shared character in another document in a pose, with an expression and a motion (wave, confused, celebrate) | `vixl_apply(workflow='character-place', request={package, pose, expression, motion})` from a `.vixlchar` written by `character-package` | 1 · <1 | Unreleased (#521). New IDs and the rig kept, one undo step; `colors`/`outfit` recolour, only `scale_parts` changes proportions; unknown joints and motions the rig cannot drive are located errors. `character-discover` lists the workspace and user library. |

### Data and diagrams

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DAT-01 | Bar, stacked, 100 %, horizontal, line, area, pie or donut chart from inline data | `chart` | 1 · <1 | One editable vector group with axes and legend. A chart given no geometry fills the safe area with spacing-scale padding, so it passes `safe_area` as created (craft plan 7d). |
| DAT-02 | Chart straight from a CSV in the workspace | `chart --csv` | 1 · <1 |  |
| DAT-03 | Change one value, add a row or reload the CSV | `chart-data` | 1 · <1 | Same layer IDs survive. |
| DAT-51 | Table from rows or a workspace CSV: menu, price list, pricing table, schedule, spec sheet | `table` | 1 · <1 | Since #169: aligned columns (decimal for prices), header, zebra, rules; native PPTX table. |
| DAT-53 | Names, numbers and percentages paired in one aligned, ruled list: a share list, stats, a summary beside a chart | `key-value-list` (or the `key-value-list` container, or a chart's `legend_values`) | 1 · <1 | Craft plan 5a (T08): labels left, figures right-aligned on shared edges, rules between rows, spacing from the spacing scale; `shares: "auto"` computes the percentages. |
| DAT-52 | Change a price, add or remove a row or column, or reload the CSV of a table | `table-data` | 1 · <1 | Since #169; cells keep their positions and layer IDs. |
| DAT-04 | Flowchart from a line of text (`A -> B -> C`) | `diagram-from-text` | 1 · <1 | Layered, tree, radial, mindmap and grid layouts. Since 0.23 it follows the document palette and dark mode. |

### Export

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRD-53 | Show a design on a phone, laptop, browser, framed poster, business card or mug | `vixl_apply(workflow='mockup')` | 1 · <1 | Since #172: a live, corner-pinned link; editing the design updates the mockup. |
| PRD-54 | One design across several mockups, exported | `vixl_apply(workflow='mockup')` (list of templates, `export`) | 1 · <1 | Since #172. |
| PRD-55 | Merch mockup: a design on the named print areas of a tee, long-sleeve, crewneck, hoodie, tote, sticker, enamel pin, patch, button, cap, beanie or socks, in any garment colour and print finish | `vixl_apply(workflow='mockup')` (`place`, `garment_color`, `finish`) | 1 · <1 | Since #444: garments are vector flat lays (front and back); finishes are `screen`, `puff`, `embroidery`, `enamel` and `woven`; [guide](guides/output/merch-mockups.md). |
| PRD-56 | Print-ready art per placed area at its print size and dpi, with spot-colour separations and a white underbase for dark garments | `vixl_apply(workflow='print-art')` (`dpi`, `spot_colors`, `separations`, `underbase`) | 1 · <1 | Since #444: PNG at `print_size_mm` × dpi, editable sources, film positives per ink (PNG or PDF pages); no Pantone or overprint. |
| DEK-51 | Slide deck from a Markdown file (layouts, notes, tables, charts, images), checked and exported | `vixl_apply(workflow='deck-from-markdown')` | 1 · 1 | Since #170; re-running rebuilds only changed slides. Fonts need a pairing (`fonts`) for a clean font check. |
| PRN-51 | Sticker or label cut line around artwork | `die-cut` | 1 · <1 | Since #444 item 4: union outline offset by N px, stroked and unfilled. The sticker, pin and patch mockups cut around the placed design with it (PRD-55). |
| DRW-31 | Cut a traced or drawn shape into two parts along a line or polygon | `path-split` | 1 · <1 | Since #443; `overlap` keeps crossing shapes whole. |
| DOC-20 | Export PNG, JPEG, WebP or TIFF | `vixl_export` | 1 · <1 | RGB PNG by default since 0.20. |
| DOC-21 | Export at 2× or 3× for screens | `export --scale 2x`, `export-screens` | 1 · <1 |  |
| DOC-22 | Export editable SVG | `vixl_export` `.svg` | 1 · <1 | Strict mode rejects raster content. Since 0.24 supported blend modes stay vector as `mix-blend-mode` (#231). The SVG carries its document, so it re-imports losslessly (DOC-38). |
| DOC-23 | Export vector PDF with selectable text | `.pdf` | 1 · <1 |  |
| DOC-24 | Export a CMYK TIFF/JPEG/PDF for print | `export --cmyk [--icc …]` | 3 · <1 |  |
| DOC-25 | Soft-proof or simulate color-vision deficiency | `export --proof`, `--simulate deuteranopia` | 1 · <1 |  |
| DOC-26 | Favicon ICO or a full web/Apple/Android icon set | `export .ico`, `vixl_export(kind='icons')` | 1 · <1 |  |
| DOC-27 | Render a quick preview, or zoom on a region | `vixl_render(region=…)` | 1 · <1 | Draft proxies are fast. |
| DOC-28 | Export a self-contained HTML page of the design | `export FILE.html` | 1 · <1 |  |
| DOC-29 | Keep a still export under a byte budget | `export --max-bytes N` | 1 · <1 | Warns and names heavy grain/paper layers. |
| DOC-44 | Layered PSD for a designer | `vixl_export` `.psd` | 1 · <1 | Since 0.22; pixel layers with names, blend modes and groups; text is pixels. |

### Checks and discovery

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| QA-01 | Run design checks (bounds, overlap, contrast, safe area, legibility) | `vixl_check` | 1 · <1 | Fix-level vs review-level findings. Since 0.24 `passed` is false while any finding needs a fix, warnings included; `by_action` separates them (#464). Since 0.25 each finding has a stable `rule`, `layer_ids`, measured actual versus expected and a suggested `repair`, and `outcome` separates validation from review (#524, #525). |
| QA-02 | Check spacing is equal or matches an expected gap | `vixl_check(action='spacing')` | 1 · <1 |  |
| QA-03 | Sample a pixel or read a histogram | `vixl_check(action='pixels')`, `sample`, `histogram` | 1 · <1 |  |
| QA-04 | Validate against a named profile or inline assertions | `vixl_check(action='validate')` | 1 · <1 |  |
| QA-05 | Compare two revisions visually | `vixl_render(action='compare')` | 1 · <1 |  |
| QA-06 | Check print readiness (ink limit, effective ppi, bleed) | `check --checks print` | 1 · <1 |  |
| QA-07 | Check color-vision safety of text and chart series | `check --checks color_vision` | 1 · <1 | Other adjacent fills not compared yet. |
| QA-08 | Check a design against a named style (Swiss, Bauhaus …) | `check --checks style` | 1 · <1 | 28 styles. |
| QA-09 | Catch a wrapped headline that leaves one short word alone on its last line | `vixl_check` (legibility, `code: runt`) | 1 · <1 | Review finding for text 24 px and up (#532); before, only a look at the render caught it. The fix is `text-layout` `wrap: pretty` or `balance` (TXT-16). |
| QA-25 | Fix overflowing text, low contrast and safe-area findings automatically | `vixl_check(repair=true)`, `vixl_apply(repair=true)`, act / group-apply `repair` | 1 · <1 | Since 0.25 (#571); a repair is kept only when its finding is resolved and nothing new fails; one undoable step. Blanks are held. |
| QA-26 | Repair a layout (longer headline, overlap, uneven gaps) without touching the logo or going below a type size | `vixl_apply(workflow='repair-layout')` | 1–2 · <1 | Since 0.25 (#518); bounded candidates ranked by least disruption; infeasible leaves the document unchanged and lists what remains. |
| QA-27 | Replace the background but keep the subject's pixels and the headline wording | `vixl_apply(workflow='protected-edit')` | 1 · <1 | Since 0.25 (#520); structural and pixel guarantees, rolls back on any violation. |
| QA-28 | See check findings marked on the preview, or zoom to one | `vixl_apply(check, preview={overlay, focus})`, `vixl_render(overlay=true)` | 1 · <1 | Since 0.25 (#526); overlays never change the document or exports. |
| QA-32 | Accept a deliberate finding (faint watermark text, a bar in the margin) with a reason and expiry | `layer-intent waive`, `waiver` | 1 · <1 | Waived findings stay listed as informational; an expired waiver fails `--strict` (#531, #562). |
| QA-33 | Check a draft loosely and a final strictly | `check --profile` (draft, review, final), `.vixl-checks.json` | 1 · <1 | Also on production `run`, `group-apply`, `vixl check --all --profile` and the CI action (#563). |
| BRD-05 | Brand contrast floor with a large-text tier, so a display-only brand colour passes at 3:1 | `brand.json` `minimum_contrast: {text, large_text}` | 1 · <1 | #527; translucent black/white shadows no longer count as off-palette (#528). |
| QA-34 | Find leftover template copy: lorem ipsum, TODO/TBD, "Headline here", unresolved `${name}` | `vixl_check` (placeholders, on by default) | 1 · <1 | `{{name}}` from other tools is review only; `layer-intent literal_text` exempts intended text. |
| QA-41 | Find dead bands, two left margins, uneven gaps in a name block, a rule pressed onto the first row and a clumped scatter | `vixl_check` (composition, on by default), `check --checks composition` | 1 · <1 | Review findings with code, region, values and threshold; fail the `final` profile unless waived. Backtest on the round-1 documents: 12 of 21 judged composition defects caught, no false findings ([composition](guides/layout/guides.md#composition)). The hierarchy codes (`flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`) add no false finding there, but no judged defect of the reconstructions is of those kinds, so what they catch is untested. Before, only a critique of the render caught them. |
| QA-42 | Repair those composition findings: snap the drifting edge, even the name block, open the gap under the rule, close the dead band | `vixl_apply(workflow='repair-layout')` (composition in `checks`, as by default) | 1–2 · <1 | Craft plan 2b; candidates ranked by least disruption, each kept only if no finding of any check is new. Backtest: 18 of 23 findings resolved (16 of the 20 on judged defects); a scatter without a `pattern-scatter` recipe is not auto-repairable ([layout repair](reference/agent-trust.md#layout-repair)). Before, by hand. |
| QA-43 | Critique in the fix call: the composition findings and a real-size look at the two weakest regions | `vixl_apply(check=true, preview=true)` (`check.regions`) | 1 · <1 | Craft plan 3b; regions carry the most findings, else the densest text and the largest empty area; two crops of at most 512 px a side, `preview={regions: 0}` for none. Before, a `vixl_check` and two `vixl_render(region)` calls. |
| QA-35 | Check every artboard, page and comp in one call | `check --artboards all --pages all --comps …`, suite `sampling` | 1 · <1 | Findings name their variant; hidden pages need `include_hidden`. |
| AGT-01 | Ask what to make and with which tools for a brief | `vixl_reference(brief)` | 1 · <1 | 20 kinds: poster, logo, character, comic, form … |
| AGT-02 | Look up fields and gotchas for a topic | `vixl_reference('capabilities', name=TOPIC)` | 1 · <1 |  |
| AGT-03 | Read the JSON schema of one operation | `vixl_reference('operations')` | 1 · <1 |  |
| AGT-04 | Browse layouts, styles, brushes, resources or workflows | `vixl_reference('layouts')`, `vixl_reference('styles')`, `vixl_reference('brushes')`, `vixl_reference`, `vixl_reference('workflows')` | 1 · <1 |  |
| AGT-05 | Check the installed version and update it | `vixl --version`, `vixl update` | 1 · <1 | Verified Windows updater with rollback. |
| AGT-35 | Rewrite saved MCP calls, batches or an MCP client config for the seven-tool server | `vixl convert-batch OLD.json`, `vixl.convert.convert_batch` | 1 · <1 | Maps every 0.26 tool and its parameters (steps, `options`, `create`, `workflow`) and drops `--tools core\|compact`, `--schema`; unmapped names are reported. |
| AGT-36 | Read a short summary of a CLI result in a terminal, or the full JSON in a script | `vixl COMMAND` in a terminal; `--json`, `VIXL_JSON=1` or piped output for JSON | 1 · <1 | Since 0.27: `created a.vixl  800×600  bg #18283b`, `added text "title"`, `check passed (bounds, contrast) — 0 errors, 0 warnings`, a list of findings when a check fails. `VIXL_JSON=1` also turns errors into JSON. |
| AGT-37 | Keep an agent's context small: seven tools, terse results, rare options on demand | `vixl mcp`; `verbose: true` for a full result; `vixl_reference(TOOL)` for rare options | config · 1 | Since 0.27 ([MCP tool surface](reference/mcp-toolsets.md)): about 7,700 characters of tool list; imports, font installs, styles and rolls are steps in a `vixl_apply` batch; an unknown option fails with the exact schema. |
| AGT-41 | Open a document from someone else without obeying text written into it | `vixl_document` inspect; the `untrusted` paths in results, `GET /document` | 1 · <1 | Results name layer names, text, notes, guidance and provider metadata as data ([agent trust](reference/agent-trust.md#untrusted-document-text)); imported images open only with the PNG, JPEG, WebP, GIF, TIFF, BMP, AVIF and ICO decoders. |
| AGT-42 | Turn the house style off: new documents with no rolled direction and neutral layout defaults | `house_style: "off"` in `vixl_document` create and `vixl_apply(create=…)`, `vixl new --house-style off`, `.vixl/variety.json` | 1 · <1 | Craft rules still apply; the default stays on. |
| AGT-06 | Read the house style: craft rules, tiers, variety levels or one purpose's profile | `vixl_reference('house-style')`, `vixl house show PURPOSE` | 1 · <1 | Purposes: poster, social, slides, document, form, diagram, logo, motion. |
| BRD-53 | Validate a brand kit: missing font roles, unreadable fonts or logos, palette roles left to derivation, guidance colours the palette does not approve | `vixl brand validate`, `vixl brand show` | 1 · <1 |  |
| BRD-56 | Start, package and install a brand: brand.json from a palette and fonts, then one `.vixlbrand` with its templates, palettes, suites, guidance and images | `vixl brand init`, `vixl brand pack`, `vixl brand install [--preset-only]` | 1–3 · <1 | Unreleased (#436); install validates the whole package first, writes atomically and rolls back on failure. |
| BRD-57 | Place the right brand logo by purpose (icon, wordmark …) in a template, with only the automatic logo on other designs | `brand-logo`, logo `purpose`/`place`/`auto`, template `places_logo` | 1 · <1 | Unreleased (#436). |
| BRD-58 | Reuse a brand mascot or badge as an editable group, and enforce the brand's own style rules | `object-place` `brand:NAME`, `vixl brand element`, `style-set` `brand:NAME`, `check --checks style` | 1–2 · <1 | Unreleased (#436). |
| BRD-59 | Brand template that places a pack image and keeps a mark just after the last word of variable copy | `asset-place`, constraint `NAME.line[-1].end+0.25em`, `=` expressions | 1 · <1 | Unreleased (#529, #530); scales with `proportional`. |
| AGT-34 | Export the design catalogs (sizes, palettes, pairings, layouts, briefs, guidance, check IDs) for a host app | `vixl catalog export --out catalog.json` | 1 · <1 | Versioned JSON with a schema; also a release asset (#536). |

### Provider-backed (one call each)

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| AI-01 | Describe an image | `vixl ai describe` | 1 · <1 | [AI] |
| AI-02 | Read text from an image (OCR) | `vixl ocr` | 1 · <1 | [AI] |
| AI-03 | Detect objects or faces | `vixl detect objects|faces` | 1 · <1 | [AI] |
| AI-04 | Upscale an image | `vixl ai upscale` | 1 · <1 | [AI] |
| AI-05 | Remove a background | `vixl ai background-remove` | 1 · <1 | [AI] needs a mask-producing provider. |
| AI-06 | Generate an image from a prompt | `vixl generate --prompt` | 1 · <1 | [AI] Provenance is kept for regeneration. |

---

## T1 · Quick (3–10 calls, 1–3 minutes)

### Measured eval tasks

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DOC-30 | Copy the exact text of a layer from one document into another | two open documents, `text-set` | 3 · 1 |  |
| SHP-20 | Three squares in a row with exactly equal gaps | `shape` ×3, `distribute`, spacing check | 4 · 1 |  |
| QA-10 | Find and fix every layout error without rewording | `vixl_check` → fix → recheck | 6 · 2 |  |
| TXT-20 | Apply a named font pairing to a layout | `font-pair`, `layout-apply` | 5 · 1–2 |  |
| FRM-01 | Fill a badge form once per CSV row into one PDF | `vixl_apply(workflow='form-fill')` | 6 · 2 |  |
| FRM-02 | Build a letter-size registration form with labelled fields | `field` operations, fillable PDF | 7 · 2 |  |
| SOC-01 | Fill a named layout (hero-statement) with given copy | `layout-apply` | 3 · 1 |  |
| PHO-10 | Photo on top, caption panel below, for a 1080×1350 post | import, `scale`, `shape`, `text` | 7 · 2 |  |
| COL-01 | Restore a mistakenly deleted layer without losing later edits | `vixl_document(action='history')` | 5 · 1–2 |  |
| SOC-02 | Roll a design direction with locks and apply it | `vixl_reference('roll')`, `roll` step | 5 · 1–2 | Use `unfilled=omit` for empty slots. The roll is weighted by purpose (`purpose`, else the document size) and gated by `variety`; `locks={tier: "bold"}` explores one tier. |
| SOC-05 | Event or promo post with a pill call to action and the date on a highlight | `layout-apply` with `direction: {cta: "pill", date: "highlight"}`, or a roll | 3 · 1 | Craft plan 5c (T02, T09): a roll sets them per seed; `direction: {cta: "button", date: "plain"}` for the plain result. |
| SOC-03 | Story with gradient and an evenly spaced three-item list | `gradient`, `text` ×3, distribute | 5 · 1–2 |  |
| BRD-01 | Import an SVG logo as editable geometry, edit and re-export | `import-document` svg editable | 4 · 1 |  |
| SOC-04 | Start from a built-in template with title and subtitle | `vixl_document(action='create', template=NAME)` | 4 · 1 | 61 templates. |
| MOT-01 | Ball moving across the canvas over one second, exported as GIF | `timeline-set`, `animate`, `vixl_export(kind='timeline')` | 7 · 2 |  |
| PRD-01 | Banner with a variable-driven headline, rendered for several cities | `variable set`, `render --set` | 6 · 2 |  |
| QA-11 | Save a check suite and make an edit that only commits if it passes | `vixl_apply(workflow='act')` | 8 · 2 |  |
| QA-39 | Find and review the objects in an existing design | `vixl_document(action='inspect', object="*")`, `inspect object=NAME`, `isolate` `views: [parts]` | 2–4 · <1 | Lists kinds, parts and missing required parts. |
| QA-40 | Accessibility pass before handing off a deck, PDF or web graphic | `layer-intent alt`/`decorative`, `accessibility lang`, `check accessibility` | 4–10 · 1–2 | Alt and language reach HTML, SVG, PPTX and PDF; no tagged PDF structure tree. |
| QA-24 | Turn a brief into tests (hierarchy, spacing, margins, contrast, balance) and run them with every batch before previewing | `suite-set`, `vixl_apply(suites=true)`, `vixl_reference("testing")` | 3–5 · 1 | Starter suites per kind of work; `vixl_reference(kind)` lists one under `tests`. |

### Social, web and simple graphics

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| SOC-10 | Quote card | `layout-apply quote-card`, look | 4–6 · 1–2 |  |
| SOC-11 | Simple announcement or "we're hiring" post | template or `balanced-announcement` | 4–6 · 1–2 |  |
| SOC-12 | Open Graph / link preview image | size `og-image`, layout | 4–6 · 1–2 |  |
| SOC-13 | Profile picture or avatar with initials | `logo-avatar` size, `monogram` layout | 3–5 · 1 |  |
| SOC-14 | Email header or email signature banner | `email-header` size, `banner` layout | 4–6 · 1–2 |  |
| SOC-15 | Discord emoji or Twitch panel | named sizes, shape + text | 4–8 · 1–2 | Whole emoji packs with platform checks: BRD-11. |
| SOC-16 | Big-number stat card | `big-number` layout | 3–5 · 1 |  |
| SOC-17 | Phone or desktop wallpaper from gradients and organic forms | `gradient`, `organic`, look | 5–8 · 1–2 |  |
| SOC-18 | Text-only typographic poster for screen | `typographic-poster` layout, font pair | 5–8 · 2 |  |
| SOC-19 | Event promo from the social-event-promo template | `vixl_document(action='create', template=NAME)` | 4–6 · 1–2 |  |
| SOC-20 | Watermark or logo stamp on a photo | import, `opacity`, `align` | 4–5 · 1 |  |
| SOC-82 | A finished card in one call (create, layout, fonts, look, check, export) | `vixl_apply(create=…)` | 1–3 · 1 | Since 0.22; atomic, errors name the step. |
| SOC-83 | Meme from your own image (top/bottom, comparison, four-panel, reaction GIF) | `vixl_apply(create=…)` with a meme layout and `image`/`images` paths or URLs (or `layout-apply` with imported assets) | 1 · 1 | Since 0.22; bring your own images. One call since 0.23 (#368); the pictures bleed (`allow_crop`) and the captions stay in the safe area, so `check` passes on sized canvases. |
| SOC-47 | Compare a few rolled directions and pick one | `vixl_apply(workflow='variations')` (2–4 seeds, optional `locks`), then the chosen tile's `roll` step | 3–4 · 1–2 | Since 0.31: one contact sheet with the seed, layout and palette under each tile and its finding counts; the document is unchanged until the chosen step is applied (it replaces the previous layout). Before, one roll and one preview per direction (10–15 calls, T2). Estimated, not measured. |

### Print and stationery

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRN-01 | Business card from the template | `vixl_document(action='create', template='business-card')` | 4–6 · 1–2 |  |
| PRN-02 | Certificate from the template | `print-certificate` | 4–6 · 1–2 |  |
| PRN-03 | Simple flyer from the template | `print-flyer` | 4–6 · 1–2 |  |
| PRN-04 | Postcard or invitation from a template | `print-postcard`, `print-invitation` | 4–6 · 1–2 |  |
| PRN-05 | Event ticket, bookmark, label, sticker or door hanger | named size + layout | 5–8 · 2 |  |
| PRN-06 | Gallery or museum wall label | `gallery-label` layout | 3–5 · 1 |  |

### Brand, icons and color

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| BRD-02 | Monogram or minimal mark | `monogram`, `minimal-mark` layout | 4–6 · 1–2 |  |
| BRD-03 | Turn an existing logo into favicons and app icons | `vixl_export(kind='icons') --set all` | 2–3 · <1 |  |
| BRD-54 | Recreate a flat logo from an image as editable curves, one layer per part, with a fidelity number | `drawing import`, `vectorize` outline `curves` + `split: components`, `path-split`, `drawing report` | 4–8 · 1–2 | Since #443; `fidelity.iou` proves the match. |
| BRD-04 | Wordmark in a paired font | `wordmark` size, `text`, font pair | 4–6 · 1–2 |  |
| CLR-10 | Recolor a design to a different palette | `palette apply`, swatch edits | 3–5 · 1 |  |
| CLR-11 | Check how much of a design stays inside a palette | `vixl_apply(workflow='palette-check')` | 2–3 · <1 |  |
| BRD-51 | Logo package: colour/mono/reversed variants, lockups, SVG/PDF/PNG, icons, social images, usage sheet | `vixl_apply(workflow='logo-package')` | 1–3 · 1–3 | Since 0.22; recolouring is heuristic and reported; no EPS. |
| BRD-52 | Brand guidelines document: palette with contrast pairs, the text-stage ladder, logos with clear space, do/don't rules | `vixl_apply(workflow='brand-board')` | 1–2 · <1 | Drawn from `brand.json` (or a preset); PDF, PPTX, HTML or editable `.vixl`. |
| BRD-11 | Custom emoji pack: replace or add `:shortcodes:`, check platform requirements, export PNG/SVG with editable masters | `vixl emoji`, `emoji-replace`, `emoji-template`, `emoji-requirements`, `emoji-export` | 3–8 · 1–2 | Since 0.24; Discord/Slack upload instructions and an offline preview; CC BY-SA 4.0 licences travel with the pack. |
| BRD-55 | Icon font: drawn icons on Private Use Area code points (U+E001 …) | shapes or paths, `font-design`, `font-glyph` per icon, `vixl_export` `.ttf`/`.woff` | 4–8 · 1–2 | Unreleased; glyphs merge each icon's shapes into one monochrome outline. |

### Data and diagrams

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DAT-10 | Titled chart card for social | size, `chart`, `text`, check | 4–6 · 1–2 |  |
| DAT-11 | Mind map or org chart | `diagram --layout mindmap|tree` | 3–5 · 1 |  |
| DAT-12 | Edit diagram nodes, labels or remove a node | `diagram-set` | 2–3 · <1 |  |
| DAT-13 | Export a chart as a native PowerPoint chart with data | `export .pptx` | 2–3 · <1 |  |
| DAT-43 | Table-like comparison or spec sheet | `table` (columns, header, zebra), check | 3–8 · 1–2 | Moved from T3: one `table` operation since #169. |

### Illustration, effects and photo

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| ILL-10 | Mandala or rosette from one petal | `organic petal`/`shape`, `radial-repeat --mirror` | 3–5 · 1 |  |
| ILL-11 | Sunburst or rays background | `shape`, `radial-repeat` | 3–4 · 1 |  |
| ILL-12 | Simple flower or tree illustration | `organic`, gradient sky | 3–5 · 1 |  |
| ILL-13 | Apply a saved effect workflow to a new image | `vixl_apply(workflow='effect-run')` | 2–3 · <1 |  |
| ILL-14 | Speech, thought, shout or whisper bubble that follows a character | bubble layer | 2–3 · <1 | Sizes to its text. |
| PHO-11 | Crop, straighten and resize a photo | `crop`, `rotate`, `resize` | 3–4 · 1 |  |
| PHO-12 | Duotone or risograph poster from a photo | import, `look duotone|risograph` | 3–4 · 1 |  |
| PHO-13 | Vignette, grain or film finish on a photo | effects/looks | 2–4 · <1 |  |
| PHO-14 | Select by color, wand or lasso and adjust only that area | `select`, effect | 3–4 · 1 |  |
| PHO-15 | Clone-stamp a blemish | clone stamp | 2–4 · <1 |  |
| BLK-11 | Seamless random scatter for patterns | `pattern-scatter`, `pattern-fill` | 2–4 · 1 | Since 0.22; reports a seam score. |
| ILL-06 | Fewer motifs in a scattered pattern without re-rolling it | `pattern-scatter` `target` with a lower `count`, or `thin` | 1–2 · <1 | The surviving copies stay in place (T15 R2 kept 7 % of the ink on 0.26). |
| ILL-51 | Scatter motifs inside or along a shape, or fur on a mascot | `scatter` (`preset: fur`), `plush` look | 1–3 · 1 | Since 0.22. |
| ILL-52 | Object from its kind (dog, guitar, house …) | `vixl_reference(KIND)` → `object-plan` (or adapt `build.example`) → refine the placeholders → `object` `action: outline` → `vixl_check` and an isolated preview | 3–6 · 1–2 | The 15 seed kinds have tested examples; the default `object` check reports missing parts, gaps, proportions, mirrored pairs, layering and outline seams. Since #380 the scaffold is one call (ILL-60) and `with: ["guitar"]` nests a held sub-object; the refinement is the rest. |

### Motion and pixels

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| MOT-02 | Fade-in, slide-in or pop-in entrance on a finished still | `animate-preset` | 3–5 · 1 |  |
| MOT-03 | Pulse, spin or bob loop as a seamless GIF | `animate-preset`, `loop_mode: seamless` | 3–5 · 1 | `poster` frame option. |
| MOT-04 | Typewriter caption | caption with typewriter animation | 3–4 · 1 |  |
| MOT-05 | Preview poster, middle and last frames at phone width | `vixl_render(action='timeline', times=…)` | 1–2 · <1 |  |
| MOT-06 | Analyse an audio file (levels, clipping, silence, onsets) | `vixl_apply(workflow='audio-analyze')` | 1–2 · <1 |  |
| MOT-07 | Sample frames from a video as a contact sheet | `vixl_apply(workflow='video-sample')` | 1–2 · <1 | [ffmpeg] |
| MOT-08 | Plan a lyric video and see the timed lines without rendering | `vixl_apply(workflow='lyric-video-plan')` | 1–2 · <1 |  |
| PIX-01 | Small pixel-art icon from rows of palette indices | `pixel-art` | 2–4 · <1 |  |
| PIX-02 | Palette-swap an existing sprite | `pixel-palette` | 2 · <1 |  |
| PIX-03 | Export saved frames as GIF/APNG/sprite sheet at whole-number scale | `vixl_export(kind='animation')` | 1–2 · <1 |  |
| PIX-04 | Pixel sprite with a shading ramp and a 1 px outline from flat palette rows | `pixel-art` (`shading` and `outline`, on by default), `pixel-palette` | 2–4 · <1 | Since 0.27 (craft plan 7e, T13): within 16 opaque colours and binary alpha; a palette swap carries into the ramp; `shading: false` and `outline: false` keep the flat sprite. |
| BLK-12 | Per-character, per-word or per-line text animation | `text-animate` | 2–4 · 1 | Since 0.22; text stays one editable layer. |
| MOT-09 | Six-second square loop for a tip, launch or event | `vixl_document(action='create', template=NAME)` video-tip/video-launch/video-event, `vixl_export(kind='timeline')` | 3–5 · 1 | Since 0.24 (#179); fill title, subtitle and cta, then check a contact sheet and pick the poster time. |
| MOT-14 | Promo variations in square, portrait and widescreen | `vixl_document(action='create', template=NAME)` video-promo-{kinetic,editorial,neon,spotlight,split,stat}, `vixl_export(kind='timeline')` | 3–5 · 1 | Six distinct compositions, 18 templates; editable copy and palette roles, six-second loops. [Preview pack](https://github.com/jxburros/VixlExamples/blob/main/promo/variety/README.md). |
| MOT-13 | Pose a character over time with its joints kept attached | `character-pose` with `time` | 3–6 · 1 | Since 0.24 (#472); the rig is solved on every frame; do not also key position/rotation on the same limbs. |

### Production, forms and review

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRD-02 | Render one image per CSV row from a template | `render --data rows.csv` | 2–4 · 1 |  |
| PRD-03 | Place a saved library component into a document | `vixl_apply(workflow='library-place')` | 2–3 · <1 |  |
| BLK-24 | Placing a library component as an editable group | `library-place` (editable group; `as: image` for a snapshot) | 2–3 · <1 | Unblocked by #381: was a raster snapshot. |
| PRD-04 | Link another `.vixl` as a live layer and refresh it after edits | `link`, `link-refresh` | 2–3 · <1 |  |
| PRD-36 | Package a campaign run's passing outputs into one delivery zip with a manifest, checksums, check report and proof page | `vixl_apply(workflow='package')`, `vixl package --production out/production.json` | 2–4 · 1 | Held variants are listed and left out; identical files once; a name collision or an existing package is refused; the manifest records source revision, export settings, check state, SHA-256, dimensions, colour and codec/frame rate/duration. See [delivery packages](guides/automation/production.md#delivery-packages). |
| PRD-60 | Run the same steps over a group or folder: check, export, verify, approve, proof and package, holding the documents that fail | `resource-save` kind `pipelines`, `vixl_apply(workflow='pipeline-run')` | 2–3 · 1–2 | Since #568: the first call is a dry run; `.vixl-runs/RUN/run.json` records input digests, per-step logs and output checksums, and a re-run reuses every unchanged step. See [pipelines](guides/automation/production.md#pipelines). |
| PRD-61 | Update every document bound to a keyed CSV (a price list), re-checking and re-exporting only those whose rows changed | `vixl_apply(workflow='data-sync')` | 1–2 · 1 | Since #572: groups, campaign specs and merge sheets; row diff against the last snapshot; failing members are held. |
| PRD-62 | Upgrade a folder of old documents in place: convert, rename layers, set roles, re-apply a layout | `vixl_apply(workflow='bulk-upgrade')` | 2 · 1–2 | Since #578: before/after checks and render diff per document; dry run by default; journalled commit (`group-recover`). |
| PRD-64 | Keep a workspace checked while people save: re-check a saved document, the documents linking to a changed source, everything after a brand change, re-sync a changed CSV, run a pipeline nightly | `vixl watch` with `.vixl/watch.json` triggers, `vixl watch --once` from cron or CI | 1 · 0 | Since #569: save, source-change, brand-change, data-change and schedule triggers; debounced, one run per document; results in the check-all history and the completion webhook. See [watch mode](guides/automation/production.md#watch-mode). |
| AGT-45 | Be told when a job, check-all or pipeline run ends | `notify: {url, secret_env}`, `.vixl/notify.json` `allow` | 1 · <1 | Since #579: one signed POST with status and counts, never document content; retries; nothing offline. |
| FRM-03 | Fill one form with values into a flattened or editable PDF | `form fill --set` | 1–2 · <1 |  |
| FRM-04 | Check a form with worst-case sample values | `check --checks form --sample worst` | 1–2 · <1 |  |
| QA-12 | Leave, list and resolve review notes | `vixl_document(action='notes')` | 2–3 · <1 |  |
| QA-20 | Enforce a brand's rules (brand fonts only, palette within a tolerance, logo clear space and minimum size) | `brand.json` `fonts.allowed`, `colors.strict`, `logo`; `vixl_check` brand, or a suite `design` rule | 3–6 · 1 | Was 10–20 calls with hand-written suite rules. Approved logo variants on approved backgrounds are not checked. |
| COL-02 | Fork a branch, edit it and see its status | `vixl_apply(workflow=…)` branch-fork/branch-status | 3–4 · 1 |  |
| AGT-10 | Connect an MCP client to a workspace | `vixl mcp --workspace .` | config · 1–3 |  |
| AGT-11 | Display a design inline in a notebook | `Project.show()` | 1–2 · <1 |  |
| AGT-30 | Embed Vixl in another app through REST with auth | `vixl host --root DIR`: workspaces, documents by id with revisions, compose, check and export jobs | 3–10 · 1–3 | [server] Was T5 (1–3 days dev on `vixl serve`); since `vixl host` (#537–#543) the app calls a documented contract (`vixl host --schema`). |
| AGT-46 | Let a host application's own AI gateway do every AI step | `vixl host --provider studio --provider-url URL --provider-token-env ENV`; `POST /w/{ws}/documents/{id}/ai` | 1–2 · <1 | [server] Since #544; the gateway contract is Vixl's proposal until Studio publishes one. `X-Call-Context` is echoed for attribution. |
| AGT-48 | Run the host as a container next to a host application | `docker run --read-only --tmpfs /tmp -v data:/data -e VIXL_HOST_TOKEN ghcr.io/jxburros/vixl:VERSION` | config · <1 | [server] Since #546; offline, content packs built in, `-full` adds ffmpeg. |
| AGT-49 | Keep the host running on a Windows desktop for AI Server Studio | Installer task "Run Vixl host for AI Server Studio" (per-user scheduled task, `%LOCALAPPDATA%\Vixl\host.json`) | config · <1 | [server] Since #547; no admin rights. A machine-wide service is not built, and Studio's detection path is unconfirmed. |
| AGT-47 | Set a workspace's brand from a host app, as brand.json or a Design Profile | `PUT /w/{ws}/brand` | 1 · <1 | [server] Since #545; unmapped profile paths are listed, `if_digest` makes it conditional. |
| BLK-10 | Lookups or case changes inside a data merge | `${name\|upper}`, `${role\|map:colors}`, `variable-map` | 2–4 · 1 | Since 0.22. |
| QA-22 | Proof page for human sign-off with approve/reject | `vixl_apply(workflow='proof')` | 1–2 · 1 | Since 0.22; offline HTML, decisions download as JSON. |
| QA-23 | Check `.vixl` files in pull requests | GitHub Action (`action.yml`), `vixl diff` | 1 · CI | Since 0.22; see [CI](guides/automation/ci.md). Runs `vixl check --all`: annotations, JUnit and SARIF upload. |
| QA-29 | Check every document in a folder or project group into one report | `vixl_apply(workflow='check-all')`, `vixl check --all GLOB` / `--group NAME` | 1 · 1 | Parallel; JSON, Markdown, JUnit, SARIF, annotations, proof page. |
| QA-30 | List documents that newly fail after an upgrade or an edit | `vixl check --all --since-last` | 1 · 1 | Compares with the previous recorded run; scheduling is up to CI. |
| QA-31 | Check that a campaign's sizes agree: logo placement, type ratios, swatches, prices and names | `vixl_apply(workflow='group-check')`, facts in brand.json or the group | 1–3 · 1 | Majority or a reference member. |
| QA-44 | Lock a document's pages, artboards, animation frames and exports, and later learn what moved | `vixl reproduce --write-lock F --export png jpg mp4`, `reproduce --lock F --export` (`vixl_apply(workflow='reproduce')`) | 2–3 · 1 | Version 2 lockfile: drift is located by page, frame, `jpg.quality` or `mp4.ffmpeg`; per export `byte_identical` (PNG, SVG, PDF) and `visually_equivalent` (JPEG, WebP, GIF, video) are reported apart. Byte-exact output across machines is not promised ([limits](guides/automation/ci.md#the-limits-of-exact-reproduction)). |
| QA-47 | Approve a design (or a whole group) and later see which pages and artboards changed since | `vixl approve [--group NAME]` (`vixl_apply(workflow='approve')`), then any check | 2 · <1 | Unreleased (#559): a changed view is a review finding with the changed fraction and a diff image; group-apply and replace-across dry runs and campaign runs list `approved_members_changed` ([approved baselines](guides/automation/production.md#approved-baselines)). Before, a `reproduce` lockfile or a reference PNG kept by hand. |
| QA-48 | Before publishing a changed logo or tile, see which documents that link to it break, and refresh only those that still pass | `vixl links impact SOURCE.vixl [--apply]` (`vixl_apply(workflow='link-impact')`) | 1 · 1 | Unreleased (#560): nested links, failing rules and changed pixels per dependent; read-only unless `--apply`, which is journaled ([link impact](guides/output/linked-documents.md#link-impact)). Before, `links` and a check of each dependent by hand. |

### Provider-backed

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| AI-10 | Remove an object and fill the hole | `vixl ai remove`, `content-aware-fill` | 2–3 · <1 | [AI] |
| AI-11 | Select a subject or a named object and mask it | `vixl ai select-subject`, `select object LABEL` | 2–3 · <1 | [AI] |
| AI-12 | Extend the canvas (outpaint) | `vixl ai extend` | 2–3 · <1 | [AI] Freezes constraints at their positions. |
| AI-13 | Image-to-image restyle or inpaint a selection | `generate` with source/mask | 2–4 · 1 | [AI] |
| AI-14 | Regenerate a generated layer with a new seed | `vixl ai regenerate` | 1–2 · <1 | [AI] |
| AI-15 | Ask a planner to turn a sentence into operations | `vixl ask PROMPT --apply` | 1–2 · <1 | [AI] |

---

## T2 · Standard (10–40 calls, 2–5 minutes)

### Measured briefs

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| ILL-20 | A picture: an illustrated scene from a short brief | gradients, shapes, organic, looks | 20 · 3.2 | Round 2 sometimes moved elements it was told to keep. |
| SOC-30 | Social post with exact copy and layout | layout, fonts, check, preview | 29 · 2.4 |  |
| DAT-20 | Infographic from a small data table | `chart`, text, check | 18 · 1.4 | Totals and callouts are still typed by hand. |
| FRM-10 | Fillable PDF form with validation (email, range, date) | `field`, `form settings`, `export --fillable` | 25 · 3.4 |  |
| PIX-10 | Pixel-art sprite with named animations | `pixel-art`, `frame-save`, `animation-set` | 23 · 3.7 | One `frames-edit` recolors every frame. New sprites are shaded and outlined. |
| MOT-10 | Animated intro (logo/title reveal) | timeline, presets, stroke draw-on | 38 · 4.0 |  |
| PRN-10 | Print poster with bleed, CMYK PDF, TrimBox/BleedBox | print size, layout, `export --cmyk` | 38 · 6.3 | Fewer calls than T3 but slower: print checks. |
| SOC-31 | YouTube thumbnail with large headline and subtitle | size, `text`, shapes, check | 13 · 3 |  |

### Measured revisions (round 2 of a finished brief)

| ID | Use case | Calls · min | Notes |
| --- | --- | --- | --- |
| ILL-21 | Revise an illustrated scene | 25 · 3.3 |  |
| SOC-32 | Revise copy on a social post | 26 · 2.4 | Only edited rows change. |
| PRN-11 | Revise copy on a print poster | 25 · 2.6 |  |
| BRD-10 | Revise a logo and icon kit | 30 · 2.2 | Live links keep marks byte-identical. |
| DEK-10 | Revise a slide deck | 29 · 2.1 |  |
| FRM-11 | Revise a fillable form | 26 · 2.5 |  |
| PRD-10 | Add a person to a name-badge run | 20 · 1.5 | A CSV edit plus a re-run of the merge. |
| DAT-21 | Update an infographic's data | 24 · 1.5 | One `chart-data` cell. |
| PHO-20 | Revise a photo correction | 26 · 2.1 |  |
| DRW-10 | Revise cleaned-up hand drawing | 33 · 2.9 |  |
| MOT-11 | Revise an animated intro | 23 · 2.5 |  |
| PIX-11 | Recolor or retime a sprite | 28 · 2.8 |  |
| MOT-12 | Shift lyric timing in a lyric video | 30 · 5.4 | One `offset` field; time is the re-render. |
| ILL-22 | Revise a seamless pattern | 27 · 2.5 | Keeps 87 % of the original ink on 0.20 and 7 % on 0.26 (re-rolled scatter); progressive scatter keeps the surviving copies in place (ILL-06). |
| PRN-12 | Change prices on a café menu | 17 · 1.6 | Per-price layers make it a direct edit; in a `table` a price is one `table-data` set (#169). |

### Social, web and ads

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| SOC-40 | Product card with photo, price and CTA | `product-card` layout, import | 12–20 · 2–3 |  |
| SOC-41 | Web hero or landing-page header | `web-hero`, `split-screen` layout | 12–20 · 2–3 |  |
| SOC-42 | Blog featured image | `blog-featured` size, layout, look | 10–15 · 2 |  |
| SOC-43 | LinkedIn/X/Facebook/YouTube banner | named size, `banner` layout | 10–18 · 2–3 | Safe zones for platform UI. |
| SOC-44 | Podcast or album cover art | `album-art` size, illustration, type | 15–25 · 3 | `check` judges text at the 120 px app thumbnail (`use-size`). |
| SOC-45 | Pinterest pin with long layout | `pinterest-long` size, `f-pattern` | 12–20 · 2–3 |  |
| SOC-46 | Post in a named design style (Bauhaus, vaporwave, Memphis …) | `vixl_reference('styles')` apply + check | 15–25 · 3 |  |
| SOC-48 | Bento-grid feature summary | `bento-grid` layout | 12–20 · 2–3 |  |
| SOC-49 | Marketing pricing or testimonials block | `marketing-pricing`, `marketing-testimonials` templates | 10–18 · 2–3 |  |
| SOC-50 | Single display ad (medium rectangle, leaderboard) | IAB size, `banner` layout | 10–15 · 2 |  |
| SOC-51 | Twitch offline screen or stream overlay frame | named sizes, shapes, glow/neon | 12–20 · 2–3 |  |
| SOC-52 | Game cover or Steam-style banner | `game-cover`, illustration, title | 20–35 · 3–5 |  |
| SOC-53 | App Store or Play feature graphic | `play-feature-graphic`, screenshot import | 15–25 · 3 |  |

### Print

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRN-20 | Custom invitation (wedding, party) in Art Deco or minimal style | `centered-axis` / `quiet-invitation`, style | 15–25 · 3 |  |
| PRN-21 | Greeting card (front + inside as pages) | `greeting-card` size, pages | 15–25 · 3 |  |
| PRN-22 | Book cover (front only) | `book-6x9` (print) or `ebook-cover` (shops), typography, illustration | 15–30 · 3–4 | Spine/back wrap is T3. `check` judges `ebook-cover` text at a 160 px shop thumbnail. |
| PRN-23 | Letterhead and envelope | `letterhead`, `envelope-10` | 12–20 · 2–3 |  |
| PRN-24 | Business card front and back with bleed and CMYK PDF | pages, `--bleed`, `export --cmyk` | 15–25 · 3 | Vector DeviceCMYK pages. |
| PRN-25 | Rack card or one-page flyer with photo | `rack-card`, `photo-caption` | 15–25 · 3 |  |
| PRN-26 | T-shirt, tote or mug-wrap print | named sizes, transparent export | 10–20 · 2–3 |  |
| PRN-27 | CD or vinyl cover | `cd-cover`, `vinyl-cover` | 15–25 · 3 |  |
| PRN-28 | Certificate customised in a period style | template, style, ornaments | 12–20 · 2–3 |  |
| PRN-29 | Report or case-study cover page | `business-report-cover` template | 10–15 · 2 |  |

### Brand and icons

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| BRD-20 | Single app icon designed for 16–1024 px | `app-icon` kind, `ios-app-icon` size | 15–25 · 3 | Judge at 16 px and in one color. |
| BRD-21 | Emblem or badge logo | `emblem` layout, shapes, path text | 15–25 · 3 |  |
| BRD-22 | Simple logo (mark + wordmark, horizontal) | pen/shapes, pathfinder, `logo-horizontal` | 20–35 · 3–4 | Full kit is BRD-40. |
| BRD-23 | Logo lockup variants (stacked, horizontal, mark) via artboards | `artboard`, symbols | 15–25 · 3 |  |
| TXT-22 | A display typeface (A–Z, digits, punctuation) drawn as shapes and paths, kerned and exported | `font-design`, `font-grid`, batched shapes per glyph, `font-build` to proof, `vixl_export` `.otf` | 15–40 · 4–8 | Unreleased; a scan of hand lettering goes through `drawing vectorize` first. |

### Data, diagrams and documents

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DAT-30 | Process or swimlane-style flowchart with styled nodes | `diagram --nodes --edges`, check diagram | 10–20 · 2–3 |  |
| DAT-31 | Timeline infographic (milestones on a line) | shapes, `repeat`, `place` on guide | 15–25 · 3 |  |
| DAT-32 | KPI tiles / dashboard card | `stack`, `big-number`, small charts | 15–25 · 3 | No data binding between tiles and text. |
| DAT-33 | Comparison card (A vs B) | `slide-comparison` template or `split-screen` | 10–18 · 2–3 |  |
| DAT-34 | Isometric illustration on an isometric grid | `grid --kind isometric`, `snap` | 20–35 · 3–5 |  |
| DEK-20 | One-pager with title, body text and an image | `business-one-pager` template, rich text | 12–20 · 2–3 |  |
| DEK-21 | Open letter or long quote in a text box with Markdown | rich text, `open-letter` layout | 8–12 · 2 |  |

### Illustration and drawing

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| ILL-30 | Static character or mascot built from named parts | `character` kind, groups with pivots, `object` kind person + named parts, `inspect object=` | 20–35 · 3–5 | Missing required parts are listed; review with `isolate` `views: [parts]`. Built once, a rigged character is shared with `character-package` and placed again in one call (ILL-62). |
| ILL-31 | Landscape scene with depth (sky, sun, hills, plants) | `scene` kind, organic, gradients | 20–30 · 3–4 |  |
| ILL-32 | Botanical illustration with several organic forms | `organic` ×n, repeat, irregular, `object` kind (flower, tree, cactus …) | 10–18 · 2–3 | Every organic preset maps to a kind ([objects](guides/shapes/objects.md)). |
| ILL-53 | Reusable editable object (mascot placed recoloured in several documents) | `object-save`/`object-place` with `recolor`, or `vixl_export(isolate, path=….vixl)` + `object-place source` | 4–8 · 1–2 | Copies are independent, with new IDs. Saved characters live in the same object library (`character-save`); a rigged mascot travels as a `.vixlchar` package with its poses, expressions and motions (ILL-62). |
| ILL-33 | Painted texture or brush illustration (dozens of strokes) | `paint` with brushes | 15–30 · 3–4 | Strokes stay editable. |
| ILL-34 | Cut-paper style illustration | cut-paper guidance, `tear`, shadows | 20–35 · 3–5 |  |
| ILL-35 | Pencil, charcoal, ink-wash, stipple, hatch, cross-hatch, scribble, spatter, dry-brush, pastel, smudge or marker finish | `drawn-texture` | 5–10 · 1–2 |  |
| DRW-20 | Draw a custom vector icon with the pen and node edits | `pen`, path node ops, simplify/smooth | 15–30 · 3–4 | Path coordinates are literal local pixels. |
| DRW-21 | Envelope or corner-pin distortion of vector art | vector distortion | 5–10 · 1–2 | Animatable parameters. |
| DRW-22 | Outline a stroke or offset a path into a shape | outline/offset path | 3–6 · 1 |  |

### Photo

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PHO-30 | Portrait touch-up with a saved script | `run portrait-cleanup.vixlscript` | 3–10 · 1–2 | Script in `examples/`. |
| PHO-31 | Color-correct a cast with white balance, temperature and tint | `white-balance`, adjustments, histogram | 10–20 · 2–3 | Rescaled in 0.21. |
| PHO-32 | Non-destructive grade with adjustment layers and a LUT | adjustment layers, `lookup` | 10–15 · 2 |  |
| PHO-33 | Product photo on a new background | [AI] background-remove, gradient, shadow | 8–15 · 2 | [AI] |
| PHO-34 | Photo collage on a grid with image frames | `frame`, `replace-contents`, grid | 15–25 · 3 |  |
| PHO-35 | Before/after comparison image | checkpoints, `vixl_render(action='compare')` | 5–8 · 1–2 |  |

### Motion and audio

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| MOT-20 | Kinetic text: words arriving one by one with stagger | `animate` with `stagger`, presets | 10–20 · 2–3 | Per-character, per-word and per-line animation of one editable layer is `text-animate` (BLK-12). |
| MOT-21 | Animated social post (MP4) from a finished still | presets, `export_timeline .mp4` | 10–15 · 2–3 | [ffmpeg] |
| MOT-22 | Looping background (drifting particles, waves) | particles, seamless loop | 10–20 · 2–3 |  |
| MOT-23 | Animated chart (bars growing) | keyframes on chart layers | 10–20 · 2–3 |  |
| MOT-24 | Synthesize a beep/whoosh, mix it with music and export WAV | audio tracks, `vixl_export (.wav)` | 5–10 · 1–2 |  |
| MOT-25 | Character wave or nod using a reusable cycle | character cycles, pivots | 15–25 · 3 |  |
| MOT-26 | Brush-stroke timelapse of a painting | paint layer reveal, timeline | 10–20 · 2–3 |  |
| MOT-27 | App animation package: named states (idle, loading, success …) with light/dark themes for an app | state masters, `vixl_apply(workflow='app-animation-package')` | 15–30 · 3–5 | Since 0.24 (#510); 1 call once the masters exist; WebP/GIF/APNG, reduced-motion PNGs, versioned manifest and HTML consumer; sources must be embedded. |

### Forms, production and review

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| FRM-20 | Survey or feedback form with radio buttons and dropdowns | `field` (radio, dropdown, checkbox) | 15–25 · 3 |  |
| FRM-21 | Consent/waiver form with a required signature field | `field --kind signature --required` | 12–20 · 2–3 |  |
| PRD-20 | Capture a design as a recipe with typed inputs | `vixl_apply(workflow='capture')` | 5–10 · 1–2 |  |
| PRD-21 | Plan a production spec and list its variants without rendering | `vixl_apply(workflow='plan')` | 3–6 · 1 |  |
| PRD-22 | Save a design to a component library and reuse it elsewhere | library-save, library-search, library-place | 5–8 · 1–2 | Places an editable group (#381); `as: image` for a snapshot. |
| PRD-23 | Find and replace a product name, a hex color, a font or the logo image across a campaign | `vixl_apply(workflow='replace-across')` (dry run, then apply) | 2–4 · 1–2 | Journalled; `group-recover` undoes an interrupted run. |
| PRD-24 | Review a group change on a before/after page and publish only the approved members | group-apply or replace-across with `review`, then `decisions` | 2–3 · human review | Offline proof page; decisions JSON comes back. |
| QA-36 | Copy rules: headline length, a required disclaimer, banned words (brand.json `words`) | `text` suite rule | 3–6 · 1 | Measured after variables, per artboard and row. Dictionary spelling: `check --checks spelling` or `spelling: true` on the rule (English bundled; other languages need a content pack); `words.allow` holds brand names. |
| QA-37 | Production budgets: layers, fonts, file size, image ppi (too low or over-resolved), render time | `budget` suite rule, `check --checks budget` | 2–4 · 1 | Results list the worst offenders; render time is an advisory review, never a failure (#564). |
| QA-45 | Hold campaign documents to a master's colour, type scale or rule values | suite rules with `{ref: "master.vixl#layer.field"}` or `{ref: "master.vixl#suite:rule-id"}` | 2–4 · 1 | Read-only, at most 8 refs per run; a missing master needs review; `check --all --since-last` names a changed master as the cause (#558). |
| QA-46 | Verify a delivered file against a printer or platform spec: bleed boxes, embedded fonts, CMYK and ink, size, dpi, alpha, bytes, editable PowerPoint text, self-contained HTML | `vixl check-file FILE --spec print-letter-bleed`, `vixl_export(spec=…)`, campaign `export_check` | 1–2 · 1 | Read-only; presets are data (`print-letter-bleed`, `instagram-feed`, `web-banner` …) plus inline fields; a campaign holds an output that fails; PDF ink needs pypdfium2, else it needs review (#557). |
| QA-38 | Generate a starter suite from an approved design and review it | `vixl_apply(workflow='suite-infer')` | 2–4 · 1 | Each rule explains what it measured; `from_group` keeps rules every member passes. |
| QA-21 | Live human review in a browser while an agent edits | `vixl view` | setup · 1–2 | [server] |
| COL-10 | Three-way merge of a branch with explicit conflict resolution | branch-merge (dry run, then apply) | 5–12 · 2 |  |
| AGT-20 | Run a 1,000-operation batch from a JSONL file | `operations_path`, `--check`, `--preview` | 1–3 · 1–2 | Batches go up to 10,000 operations. |
| AGT-21 | Drive Vixl from Python: build, apply, save, export | `Project` API | 10–30 lines · 5–10 | Human-written script. |

---

## T3 · Involved (40–70 calls, 4–8 minutes)

### Measured briefs

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRN-30 | Café menu with sections, items and prices | `print-menu` / `price-list`, `table` with a decimal column and a dot `leader` column, or `tabs` | 41 · 4.5 | Measured before `table` (#169) aligned prices and before leaders (BLK-07); expect fewer calls now that leaders are not drawn by hand. |
| DEK-30 | Slide deck (title, content, chart, closing) to PPTX and PDF | pages, masters, notes, native PPTX chart | 47 · 4.5 |  |
| PRD-30 | Name badges from a spreadsheet, imposed on print sheets | `vixl_apply(workflow='merge-impose')` | 48 · 3.3 | Empty fields don't re-centre unless `stack --hide-if-empty`. |
| ILL-40 | Seamless repeating pattern | motifs, pattern-check, repeat | 61 · 7.5 | Measured on 0.20, before `pattern-scatter` (BLK-11): scatter positions were computed outside Vixl. Fewer calls now. |
| SOC-60 | One campaign in six sizes | `vixl_apply(workflow='adapt-sizes')`, per-size fixes | 63 · 4.4 | Measured before #210 (safe zones, uniform decoration, grouped content, `min_text`); re-measure. Revision: 44 calls, 1.8 min. |
| PHO-40 | Photo correction (tilt, cast, exposure, noise) | effects, denoise, white balance, links | 63 · 5.0 | Linked crops of the corrected master (Instagram, caption) show its denoised pixels even when enlarged. |
| DRW-30 | Hand drawing → clean vector art with fills | `drawing import/clean/vectorize/straighten/fill` | 64 · 5.7 | Facing curved ends get tangent-following gap bridges; centerline tracing smooths pixel stairs by default (`smooth: 0` preserves the raw trace). Sky and ground bounded by the drawing's edge fill with `settings.edge_closes` (was BLK-22), also when the ground line stops short of the edge (no extension strokes); fills register to their lines (no halo, no bulge at an open corner); `clean` keeps the paper's extent. |
| MOT-30 | Lyric video from a song, an LRC file and a template | `lyric-video-build/export` | 40 · 6.4 | [ffmpeg] Audio resampled to 24 kHz. |

### Social and marketing

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| SOC-61 | Instagram carousel (5–8 slides) with consistent master | pages, `social-carousel` template | 40–60 · 5–7 |  |
| SOC-62 | IAB display ad set (6–8 sizes) | `vixl_apply(workflow='adapt-sizes')`, per-size checks | 50–70 · 5–8 | Measured before #210 fixed the SOC-60 gaps; re-measure. |
| BLK-15 | Reliable multi-size adaptation from one master | `adapt-layout` / `vixl_apply(workflow='adapt-sizes')` (layout rebuild by default, `arrangements`, priorities, focal crops, safe zones, `min_text`), suites per copy | 40–60 · 4–6 | Moved from Blocked: #210 keeps content out of safe-area bands, scales decoration uniformly, keeps a rule with its headline and never sets text below `min_text`. Unreleased (#653, #519): unedited layouts are rebuilt per size, other documents can try arrangements scored by the checks, and each copy runs the document's suites with an `outcome`; re-measure. Extreme ratios (leaderboard) still want a review. |
| SOC-63 | Story + post + thumbnail set for one launch | linked master, `adapt-layout` | 40–60 · 5–7 |  |
| SOC-64 | Email campaign assets (header, banner, product tiles) | sizes, layouts, library components | 40–60 · 5–7 |  |
| SOC-65 | App store screenshot set with captions (5 screens) | `iphone-screenshot` size, pages, imports | 40–60 · 5–7 |  |

### Print and publishing

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRN-40 | Tri-fold or multi-panel brochure | pages, grids, text flow | 50–70 · 6–8 | No fold-mark helper; use guides. |
| PRN-41 | Newsletter with flowing columns across frames | `text-flow create/add-frame/link`, check flow | 40–60 · 5–7 | Orphans/widows control. |
| PRN-42 | Résumé or CV (two columns, rich text) | rich text, text flow, `offset-column` | 40–55 · 5–7 |  |
| PRN-43 | Stationery set: card, letterhead, envelope, compliments slip | linked swatches/styles, artboards | 50–70 · 6–8 |  |
| PRN-44 | Full book cover wrap (back, spine, front) with bleed | custom size, guides, CMYK PDF | 40–60 · 5–7 | Spine width computed by hand. |
| PRN-45 | Event poster series in three colorways | comps or variables, export per comp | 40–55 · 5–6 |  |
| PRN-46 | Personalised invitations or place cards from a guest CSV | merge-impose | 30–50 · 3–5 | Like PRD-30. |
| PRN-47 | Product label or packaging face with print checks | `label`, print checks, CMYK | 40–60 · 5–7 | No dielines or spot colors. |

### Data and documents

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| DAT-40 | Multi-chart infographic poster with callouts | several `chart` groups, grid, text | 40–60 · 5–7 | Callout numbers typed by hand (no chart→text binding). |
| DAT-41 | One-page annual-report spread | charts, text flow, `editorial-grid` | 50–70 · 6–8 |  |
| DAT-42 | Architecture or system diagram with grouped zones | `diagram`, groups, connectors | 40–60 · 5–7 |  |
| DEK-31 | Pitch or teaching deck of 8–12 slides with notes | pages, masters, slide templates | 50–70 · 6–8 |  |
| DEK-32 | HTML presenter deck with speaker notes and transitions | `export deck.html` | as DEK-30 + 2 |  |
| DEK-33 | Zine or small booklet (8–16 pages) | pages, masters, PDF | 50–70 · 6–8 | No imposition for saddle-stitch reading order. |
| DEK-34 | Comic page with panels, captions and dialogue | `comic` kind, panel layout, bubbles | 40–70 · 5–8 | Art per panel adds a lot. |
| FRM-30 | Multi-page application form with tab order and validation | pages, `field`, `form settings` | 40–60 · 5–7 |  |
| FRM-31 | Fill a form from a CSV with a bad row and get a per-row preflight | form-fill with jobs | 10–20 · 2–3 | Personal-data handling built in. |

### Illustration, game and motion

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| BRD-30 | Consistent icon set (8–12 glyphs on one grid) | shared grid, pen, symbols, `export-icons` | 50–80 · 6–10 | Borderline T4. |
| ILL-41 | Children's-book style spread | scene, character, rich text | 50–70 · 6–8 |  |
| ILL-42 | Generative abstract artwork (seeded shapes, blends) | repeat, organic rules, seeds | 30–50 · 4–6 |  |
| ILL-43 | Trading card front with frame, art slot, stats | template, variables, symbols | 40–60 · 5–7 | Series is PRD-40. |
| PIX-20 | Tileset and a small tile map | `pixel-art`, `repeat`, `tile-16/32` | 40–60 · 5–7 |  |
| PIX-21 | Sprite with idle, walk and attack animations | frames, named animations, sheet | 40–60 · 5–7 |  |
| PIX-22 | Pixel UI kit (buttons, panels, health bar) | pixel-draw, 9-slice by hand | 40–60 · 5–7 |  |
| MOT-31 | Rigged character walk cycle | rig, two-bone IK, cycles, motion check | 40–60 · 5–8 |  |
| MOT-32 | Parallax scene with a camera move | depth parallax, camera choreography | 40–60 · 5–8 |  |
| MOT-33 | Explainer GIF with three short scenes | timeline markers, presets, captions | 40–60 · 5–8 | No nested compositions. |
| MOT-34 | Talking character with viseme cues and audio | visemes, audio tracks, MP4 | 40–70 · 6–8 | [ffmpeg] |
| MOT-35 | Lyric video with a title card, an end card and animated template graphics | `lyric-video-*` with `lead_in`, `tail`, an `outro` layer, template keyframes, per-cue `cue_animation` | 45–65 · 6–8 + render | [ffmpeg] No audio padding or post-build keyframe script; `segments` makes the full render resumable. |

### Production

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| PRD-31 | Render a production matrix (sizes × languages × colorways) with suites | `vixl_apply(workflow=…)` plan/run | 10–20 · 5+ render | Resumable; time is the render. |
| PRD-32 | Apply a brand change to every document in a project group, gated by suites | group-define, group-apply | 10–20 · 3–5 | Dry run by default; journal recovery. |
| PRD-35 | Hold every document in a group or workspace to one library suite, inherited by reference | group-define / brand.json `suites`, `vixl_apply(workflow='check')` | 3–6 · 1 | A library edit reaches every member's next check; members override rules by `id` (`extends`). |
| PRD-33 | Install a plugin pack of palettes, templates and suites | `vixl_apply(workflow='plugin-install')` | 2–4 · 1 | Packs are trusted code. |
| PRD-34 | Rebuild a merge after the CSV changed | `merge --rerun sheets.vixl --data new.csv` | 2–4 · 1 |  |
| PRD-51 | Localised campaign in 10 languages with font fallbacks and checks | `locales-set` or a strings CSV, `vixl check --locales all`, `vixl_apply(workflow='localize')` | 10–20 · 5+ render | Estimate. Failing locales are held with a locale x finding matrix; RTL locales are mirrored; re-runs rebuild only changed locales. Moved from T5 (#565, #576). |

---

## T4 · Large (70+ calls, 8–30 minutes)

| ID | Use case | Main route | Calls · min | Notes |
| --- | --- | --- | --- | --- |
| BRD-40 | Logo and icon kit (mark, lockups, app icon, favicons, sheet) | pen, pathfinder, artboards, links, icon export | 104 · 7.8 | Was 169 calls on 0.18. |
| BRD-41 | Brand identity: palette, type, logo, business card, icons, ICO, HTML, palette suites | see exploration 02 | script 14 s | As an agent session: 150–250 calls, 20–40 min (estimate). |
| PRN-50 | Concert poster at tabloid size with warped/path text, soft proof, CMYK PDF/JPEG and SVG | see exploration 01 | script 1 min 17 s | Agent: 100–150 calls (estimate). |
| DEK-40 | Full pitch deck (15–20 slides) with charts, notes, PPTX/PDF/HTML | pages, masters, charts | 100–150 · 15–25 |  |
| DAT-50 | Data infographic with several charts, constraints, color-vision checks, SVG/HTML/PDF | see exploration 08 | script 38 s | Agent: 80–120 calls (estimate). |
| PRD-40 | Trading card series with variables, CSV render, comps, suites, CMYK print sheet | see exploration 07 | script 1 min 43 s |  |
| MOT-40 | Kinetic launch film with easings, staggers, animated effects; GIF/WebP/APNG/MP4/sheet | see exploration 03 | script 1 min 35 s | [ffmpeg] |
| PIX-40 | Pixel RPG asset pack: sprites, palette swaps, tileset, tile map, comps | see exploration 04 | script 25 s |  |
| ILL-50 | Generative painting with thousands of seeded strokes and a timelapse | see exploration 05 | script 2 min 41 s |  |
| PHO-50 | Non-destructive photo lab: every selection kind, masks, tonal stack, LUT, branches | see exploration 06 | script 26 s |  |
| SOC-70 | Collaborative campaign: brand.json, rolls, 7 sizes, adapt-layout, branch merge, suite-gated group apply | see exploration 09 | script 1 min 23 s |  |
| MOT-41 | Short character film: rig, walk/wave/jump, parallax, camera, crossfades, captions, audio | see exploration 10, `film-export` | script 1 min 57 s | [ffmpeg] Camera zoom softens the image. |
| DEK-41 | Multi-page comic (4–8 pages) | comic panels, characters, bubbles | 150+ · 30+ |  |
| DEK-42 | Picture book (12–24 spreads) | pages, scenes, characters, rich text | 200+ · 45+ | Usually T5 across sessions. |
| MOT-42 | Animated explainer (30–60 s) with voice-over and captions | film spec, captions, audio mix | 100–200 · 20–40 | [ffmpeg] |

---

## T5 · Project (multiple sessions or a scripted pipeline)

| ID | Use case | Main route | Effort | Notes |
| --- | --- | --- | --- | --- |
| SOC-80 | Product launch kit across print, social, web, email and motion | brand group, linked masters, production runs | several sessions |  |
| SOC-81 | Monthly social calendar (30 posts) from a content CSV | recipe capture + production run | 1 session setup, minutes per month | Cheap once the recipe exists. |
| BRD-50 | Brand system as a plugin pack with templates, palettes and check suites | resources, plugin pack, suites | 1–2 days | Building the templates and suites is the work; packaging and installing are one command each since brand packages (BRD-56). |
| PRD-50 | Personalised certificates or tickets for thousands of rows | merge-impose, durable jobs | setup 1 h, run unattended |  |
| PRD-52 | Data-driven report generator (Python) re-run on each new dataset | `Project` API, `chart --csv`, templates | 1–2 days dev |  |
| PRD-63 | Recurring checked delivery of a document family: checks, exports, export verification, approval and a package, resumed after an interruption | saved pipeline, `pipeline-run` or a `pipeline` job, `data-sync` for data changes | setup 1 h, then one call per run | Since #568; a `schedule` or `data-change` trigger of `vixl watch` runs it (PRD-64), or CI on a schedule. |
| AGT-31 | Gate pull requests on design checks in CI | `vixl validate`, suites, golden renders | 0.5–1 day | The bundled action covers checks and suites in one step (QA-23); this row is custom gates such as golden renders. |
| AGT-32 | Run the agent eval suite against a new model or schema mode | `python -m evals.run --agent claude` | 1–2 h | Needs an API key. |
| AGT-33 | Compare Vixl with other tools on the 16 briefs | [`evals/tool-comparison` kit](https://github.com/jxburros/VixlExamples/blob/main/evals/tool-comparison/README.md) in VixlExamples | 1 day |  |
| AGT-38 | Re-run the Vixl lane of the tool comparison and package it for blind judging | `python -m evals.craft_rerun` (`--dry-run` first) | 1 day with judges | Craft plan 1c; spends API credits; packaging needs the VixlExamples kit, Playwright, LibreOffice and ffmpeg ([evals](../evals/README.md#craft-re-run)). |
| AGT-39 | Score the composition checks and `repair-layout` against the defects the judges named | `python -m evals.craft_backtest` (`--repair`) | minutes | Craft plan 1b; offline, on the 16 reconstructed round-1 documents. |
| AGT-40 | Measure raster output against headless Chromium and exact references | `python -m evals.render_parity` | 1–2 h | Needs `pip install playwright`; findings in [render parity](project/render-parity.md). |
| PIX-50 | Complete small game art set (characters, tiles, UI, title screen) | pixel tools, timelines, sheets | days |  |
| MOT-50 | Music video beyond lyrics (scenes, characters, camera, audio) | film spec, rigs, parallax | days | No nested compositions or motion-path editor. |
| DEK-50 | Course slide library (100+ slides) on shared masters and components | pages, library components, group apply | days |  |

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
| BLK-09 | Bind chart values into text, or one chart into another | Missing (T08) | Type callouts by hand; a chart's `legend_values` lists its totals and shares beside it (DAT-53). |
| BLK-13 | Motion-path editor, nested compositions with their own timelines | Not implemented (group and child tracks compose; `attach` follows a moving layer since 0.22) | Keyframes per property; markers. |
| BLK-14 | Automatic discovery of fallback fonts for mixed scripts | Not implemented (fallbacks are listed by hand; weight- and slope-matched since 0.22) | Document-wide `font-fallbacks`. |
| BLK-17 | Video generation | Needs an explicitly configured gateway; no bundled model | [AI] |
| BLK-18 | Segmentation or background removal with OpenAI alone | Needs a mask-producing HTTP/ComfyUI provider | [AI] |
| BLK-19 | Branch merging by replay or real-time collaboration | Not implemented; shared-filesystem locks only | Branch fork/merge with explicit resolutions. |
| BLK-20 | Imposition for saddle-stitched booklets (reader → printer spreads) | Not implemented | Order pages by hand. |
| BLK-21 | Dielines, folds and packaging nets | Not implemented as a feature | Draw with guides and paths. |
| BLK-23 | Live (active/scripted) SVG content | Not implemented; static SVG only | – |
| BLK-25 | Hard memory cap or execution timeout per call | Partial: servers bound each call's megapixels, export pages and per-workspace concurrency, and detach calls over a timeout into jobs (#542); no hard memory cap or kill | [Per-call limits](reference/interfaces.md#per-call-limits); OS/container limits for memory. |
| BLK-26 | Export a Vixl design to Figma as editable layers | Not implemented (import only; export is tracked in #662) | Export SVG or PDF and open it in Figma; import back with `vixl import --format figma` (DOC-42). |

## Cost notes

- **Code is still cheaper per brief.** In the 0.20 tool comparison, writing HTML/SVG or Python took
  about a third of Vixl's calls (W 15, C 14 against V 41 median in round 1). Vixl wins on
  revisions that stay put, editable masters, print/PDF/PPTX/form output and built-in checks.
- **Revisions are where Vixl is cheapest.** Round 2 medians were 26 calls and 2.5 minutes, and
  several revisions became one data edit (`chart-data`, a CSV re-run, `frames-edit`, an `offset`).
- **One call can edit, check and preview.** Pass `check=true` and `preview=true` to
  `vixl_apply` to save two calls on every iteration.
- **Shared servers slow everything down.** The 0.18 run had about 15 agents on one stdio server
  and calls timed out at 60 s while the server still finished. Count calls, not minutes.
- **Heavy work goes to jobs.** Calls longer than about 40 s return a job; poll `vixl_job`.

## Interface and path authoring additions (0.26)

| Task | Interface | Calls | Notes |
| --- | --- | --- | --- |
| Place native-coordinate path art in a display box | `shape` with `path_view` | 1 | Preserves path data; shared render/export mapping (#610). |
| Choose an integration interface | [Capability matrix](reference/interfaces.md#capability-matrix) | 0 | Generated workflow registry and REST allow-list (#640). |
| Render final campaign outputs under a severity profile | workflow `run` | 1 | Explicit final quality selects final checks; profile override supported (#563). Held outputs are reported under `withheld` with a `message` naming the blocking rules (#701). |
