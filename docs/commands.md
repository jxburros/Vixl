# Command reference

For complete first-use workflows, see [getting started](getting-started.md) and the
[tutorial index](README.md#learn-by-making). Use `vixl COMMAND --help` for the installed
runtime's exact arguments, and pass `-p file.vixl` explicitly for editing commands.

## Pages, forms, drawing and workflow discovery (0.18)

These commands complement the earlier editing reference below. Examples assume an open
project with appropriate layers or input files. See each guide for complete creation steps.

| Task | Command | Reference |
| --- | --- | --- |
| Add/select/list pages | `page add NAME`, `page select NAME`, `pages` | [Pages and decks](slides.md) |
| Shared page artwork | `master add NAME`, `master select NAME` | [Masters](slides.md#masters) |
| Speaker notes | `page set NAME --notes 'Talking points'` | [Page settings](slides.md#how-pages-work) |
| Deck overview | `render --page all --out sheet.png` | [Seeing pages](slides.md#seeing-pages) |
| Presentation checks | `check --checks deck` | [Deck checks](slides.md#deck-checks) |
| Editable slides / page PDF | `export deck.pptx`, `export deck.pdf` | [Export guide](exporting.md) |
| Rich text | `rich-text 'A **bold** point' --name body --width 900` | [Rich text](rich-text.md) |
| Field layer | `field add email --kind text --label Email --required` | [Forms](forms.md) |
| Field inspection | `field list`, `render --show-fields --out fields.png` | [Forms](forms.md) |
| Fillable PDF | `export form.pdf --fillable` | [Forms](forms.md#the-fillable-pdf) |
| Filled copy | `form fill --set email=ada@example.com --out ada.pdf` | [Forms](forms.md#filling) |
| Validate CSV fills | `form fill --data rows.csv --dry-run` | [Form tutorial](tutorials/forms-and-decks.md) |
| Drawing cleanup | `drawing import sketch.jpg --name sketch`, `drawing straighten sketch` | [Drawing](drawing.md) |
| Drawing preservation | `drawing report sketch`, `drawing compare sketch --out compare.png` | [Drawing](drawing.md) |
| Organic shape | `organic sunflower --name bloom --seed 7` | [Organic shapes](organic.md) |
| Polar grid | `grid dial --kind polar --rings 3 --spokes 12` | [Guides and grids](guides.md) |
| Workflow contract | `workflow schema` | [Production](production.md), [studio](studio.md) |
| Lyric video | `workflow lyric-video-export --request request.json --workspace .` | [Lyric videos](lyric-video.md) |
| Whole piece in one call | `compose --request req.json [--preview p.png] [--workspace DIR]` | [Interfaces](interfaces.md#build-a-piece-in-one-call) |
| Pixel diff of two files | `diff before.vixl after.png [--out diff.png] [--mode diff\|side-by-side] [--threshold 8] [--max-fraction F] [--overwrite]` | [CI](ci.md#the-same-checks-locally) |
| Proof page | `workflow proof --request proof.json --workspace .` | [Proof pages](production.md#proof-pages) |
| Logo package | `workflow logo-package --request logo.json --workspace .` | [Logo packages](production.md#logo-packages) |

Since 0.19.0, `export --alpha auto|keep|flatten` controls supported image formats.
See [exporting](exporting.md#image-output-and-alpha) and the
[release notes](../CHANGELOG.md#0190).

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Checked automation and production: `workflow schema` lists the actions accepted by
`workflow ACTION --request FILE --workspace DIR`. See [production](production.md) for
check suites, recipes, matrices, libraries, jobs and films. New editing commands include
`suite-set`, `suite-capture`, `role-set`, `motion-define`, `motion-apply`, `action-define`,
`action-apply`, `fit-text`, `arrange-grid`, `adapt-layout` and `recipe-set`; each has `--help`.
`edit-layers --where JSON --do JSON [--expect N] [--dry-run]` runs an operation on every layer matching a selector, and
`adapt-layout --size story [--scale fit|fill|width|height|N] [--anchors JSON] [--where JSON] [--text keep]` (without
`--targets`) resizes the canvas and re-lays out every layer; see [operations](operations.md#bulk-edits-and-resizing-a-whole-layout-unreleased).

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

See [spacing checks and pixel animation](pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

Global options can appear before or after the command: `--project FILE` / `-p FILE`, `--json`, `--allow-linked`, `--plugins`, `--max-pixels N`, `--version`. The default project is stored in the current directory's `.vixl-session.json`. Use explicit paths in CI and concurrent workflows. `vixl COMMAND --help` prints syntax for editing commands.

## Installed application updates

For the Windows installer edition, these commands work without an open project:

| Command | Behavior |
| --- | --- |
| `update --check` | Check for a newer published stable release without downloading the runtime |
| `update` | Download, verify and activate the latest stable runtime before returning |
| `updates status` | Show current/previous/pending version, automatic-update setting and last error |
| `updates off` / `updates on` | Persist the preference; off also clears a queued activation |
| `update --rollback` | Select the previous runtime for future launches and turn automatic updates off |

Set `VIXL_NO_UPDATE=1` to suppress both automatic checks and pending activation for a process (useful in CI). Python/pip installations are never modified by this updater. See [releases](releases.md).

## Documents and output

| Command | Behavior |
| --- | --- |
| `new 1920x1080 -o poster.vixl --background '#111111'` | Create a project; refuses existing files |
| `open poster.vixl` | Select an existing project for this directory. A document saved before 0.21 reports, under `upgrade`, the layers that render differently now (effects on rotated/flipped/skewed layers, `temperature`/`tint`, open stroked shapes that were filled white) |
| `upgrade [poster.vixl] [--report] [--pin-fills]` | Accept the 0.21 rendering for an older document and stop the notice; `--pin-fills` first gives open stroked shapes the explicit white fill they used to render with (one undoable revision); `--report` only lists the affected layers |
| `save [copy.vixl]` | Save, or save as a new selected project |
| `status`, `inspect [LAYER]`, `describe`, `layers` | JSON state, including resolved bounds |
| `manifest`, `dependencies`, `reproduce --check` | List assets/fonts/providers; check current renderability |
| `render [project.vixl] --out preview.png --set title=Hello` | Render without persisting overrides |
| `export image.jpg --quality 90 --scale 2x` | Export, preserving the editable document. `--quality` also compresses PDF images; `--title` sets the PDF title (default: the title layer, then the file name); `--max-bytes N` warns when a raster file is larger, and a PNG over 1 MB warns, naming texture looks (grain, paper, film) as the likely cause |
| `export image.png --profile discord` | Contain in 512×512; Instagram contains in 1080×1080; print emits RGB/RGBA TIFF at 300 DPI |
| `canvas resize 1080x1080`, `canvas preset story` | Resize and reflow constraints |
| `canvas background transparent` | Set the canvas base color |

Exports support PNG, JPEG, WebP, TIFF; AVIF depends on the installed Pillow codec. JPEG flattens transparency onto white, configurable with `--background`. Explicit `--format` overrides a profile or filename. Profiles **contain**, not crop or stretch; `print` does not imply CMYK or color-managed prepress.

## Layers and editing

Layers are ordered bottom to top. A target is a unique layer name or immutable ID. Most editing commands accept an omitted target and use the active layer.

```bash
vixl layer add image.png --name hero
vixl add logo.png --name logo --linked
vixl add photo.jpg --name hero --credit "Photo: Ana Ruiz" --license "CC0"
vixl import https://images.example.com/cat.jpg --name cat --license "CC BY 4.0"
vixl select-layer hero
vixl layer rename hero portrait
vixl layer duplicate portrait copy
vixl layer hide copy
vixl layer show copy
vixl layer remove copy
vixl layer raise portrait
vixl layer lower portrait
vixl layer top logo
vixl layer bottom portrait
vixl layer reorder logo --above portrait
vixl move portrait 100 200
vixl move portrait --x 100 --y 200
vixl move x +20
vixl scale portrait 80%
vixl scale portrait --x -1              # negative factors mirror: --x/--y per axis, -1 both
vixl resize portrait 800x600
vixl resize portrait --width 800
vixl resize portrait --width 800 --keep-aspect       # explicit; --no-keep-aspect stretches one side of an image
vixl rotate portrait 15
vixl flip portrait horizontal
vixl crop portrait 0 0 300 400
vixl opacity portrait 0.75
vixl blend portrait multiply
vixl align logo top-right --margin 40
vixl align caption center --relative-to bubble --box content   # centre in a shape's content box
```

`add` and `import` take `--credit` and `--license`, kept in the layer's provenance for attribution; `import` also takes an `https://` image URL (fetch policy in [architecture](architecture.md#trust-and-security), more in [interfaces](interfaces.md#import-existing-artwork)). `layer` is an optional namespace. `rm` aliases remove and `mv` aliases move. Rotation is clockwise, expands the layer bounds, and anchors the expanded bounding box at its x/y position. Crop coordinates refer to the original embedded raster. Resize with one dimension changes only that dimension of a shape, text box, group or solid (the other side keeps its size, and the result reports it under `normalized`), but scales an imported image (raster layer) proportionally so a photo is not stretched. `--keep-aspect` (JSON `keep_aspect: true`) scales the other side proportionally on any layer; `--no-keep-aspect` (`keep_aspect: false`) changes just the given side of an image; give both dimensions to stretch. Numeric scale values are factors; `80%` is `0.8`; a negative factor (`-1`, or `--x -1` for one axis) mirrors the layer as `flip` does and scales by its size. Opacity is 0–1 (`opacity portrait 0.75`); `75%` is read as 0.75, and a bare `75` is an error. `pivot LAYER X Y --canvas` takes a document point; `group NAME A B --above LAYER` (or `--below`) chooses where the new group lands; `shape` takes `--opacity`, `--rotation` and, with `--target`, `--space canvas`.

Alignment supports center, center-x/y, left/right/top/bottom and corner pairs. Absolute moves and alignment clear constraints. `move x +20` and `--relative` add offsets.

```bash
vixl solid --name panel --width 400 --height 200 --color '#26344e'
vixl gradient --name sky --start '#152641' --end '#635e83' --direction vertical
vixl text add 'Hello' --name title --size 96 --font DejaVuSans.ttf --color white --x center --y 120
vixl text title --text 'Good evening' --size 80 --align center
vixl text title --stroke-width 2 --stroke-color black
vixl rasterize title
vixl merge-layers paper back disc --name art
vixl flatten --keep-hidden
```

Text remains editable until rasterized. `rasterize` bakes everything the layer draws into a raster layer: effects,
mask, layer styles (drop shadow, glow, stroke, overlays), clipping, opacity and transform; the blend mode stays.
`merge-layers` (JSON `{"type": "merge-layers", "targets": [...]}`; `merge` is accepted) draws the listed layers,
which must share a parent, into one raster layer at the topmost one's place in the stack, named after it unless
`--name` is given; a listed group brings its members, and hidden listed layers are discarded. Blend modes are
composited among the merged layers; how a merged layer blended with the layers below the merge (or with the canvas
background) cannot be kept in pixels, so the merged layer uses the normal blend mode and the result warns where that
can change the look. A layer clipped to a merged layer is clipped to the merged layer. `flatten` draws every visible
top-level layer of the page into one canvas-size raster layer named `flattened` (master-page layers are not part of
it, and pixels outside the canvas are dropped); hidden layers are discarded unless `--keep-hidden` keeps them in
place. The originals are kept in the new layer's `provenance` (`merged` / `flattened`), and each operation is one
history entry, so `undo` restores them. Custom `--font /path/to/font.ttf` imports and embeds a font. Other font names use Pillow's system-font lookup. Font substitution is never silent. HarfBuzz shaping and shared PNG/SVG outlines support ligatures, combining marks and scripts covered by the selected font, with multiline text, wrapping/fitting and path/warp layouts. Bitmap/color fonts and unsupported Unicode isolate controls retain appearance fallbacks. See [local artistic filters and SVG policies](artistic-filters.md).

## Selections, masks, effects

```bash
vixl select rect 0 0 500 300
vixl select ellipse 100 100 200 200 --mode add --feather 5
vixl select color '#ffffff' --tolerance 15
vixl select alpha portrait
vixl select all
vixl select invert
vixl select none
vixl mask create portrait
vixl mask from-selection portrait
vixl mask import portrait --path mask.png
vixl mask invert portrait
vixl mask disable portrait
vixl mask enable portrait
vixl mask delete portrait
```

Selection combination modes: replace, add (maximum), subtract, intersect (minimum). White means selected/visible; black means unselected/hidden. No selection means effects cover the whole layer. Each effect captures the selection as it existed when the effect was added; clearing the selection does not remove that boundary. Effect selection masks use canvas coordinates. Layer masks are mapped onto the transformed layer's bounding box and move/resize with it.

```bash
vixl brightness portrait +20
vixl contrast -10
vixl saturation +15
vixl hue 30
vixl exposure 0.5
vixl gamma 1.1
vixl temperature 30
vixl tint 10
vixl white-balance photo --neutral '#a08070'
vixl white-balance photo --gains '[1.1, 1, 0.9]'
vixl shadows 15
vixl highlights -10
vixl blur 8
vixl sharpen 2
vixl denoise photo --luminance 40 --chroma 60
vixl grayscale
vixl invert
vixl posterize 6
vixl threshold 128
vixl filter noise --amount 0.08 --seed 42
vixl filter vignette --radius 0.7 --strength 0.4
vixl filter levels --black 15 --white 240
vixl effects portrait
vixl effect disable portrait 1
vixl effect set portrait 2 --amount 20
vixl effect remove portrait 3
vixl effect move portrait grain --to top
vixl effect move portrait 3 --before blur
```

Effect indices start at 1; stable effect IDs also work, and so does an effect's name when the stack holds it once. Effects apply in stack order (top first); `effect move` reorders them (`--to N|top|bottom`, `--before EFFECT` or `--after EFFECT`), and a LUT added with `vixl lookup LAYER LUT` is an entry in the same stack. Curves use JSON `points: [[0,0],[128,160],[255,255]]`. Brightness/contrast/saturation are percentages relative to neutral; exposure is stops; gamma must be positive; hue is degrees; sharpen is a factor (1 is neutral); denoise takes `--luminance` and `--chroma` strengths 0–100 (see below); noise/grain are 0–1 standard deviations; posterize is 1–8 bits. Temperature, tint and white-balance multiply the channels, so black stays black: temperature (−100…100) moves the white point along the blackbody locus, 0.75 mired per unit (100 ≈ 6500 K → 4400 K, a strong warm cast; 10–30 is subtle), tint (−100…100, magenta positive) is the matching green–magenta shift (tint 100 is as strong as temperature 100), and both keep a grey's brightness. `white-balance` corrects a cast: `--neutral COLOR` turns that color grey (keeping its luma) or `--gains '[r, g, b]'` sets the multipliers; its amount (0–100, default 100) scales the correction. These are encoded-sRGB adjustments, not camera-calibrated raw controls; shadows/highlights are simple tonal curves.

Effects run on the layer in its own frame, at its box size, before it is flipped, rotated or skewed, so a blur, denoise, grain or vignette behaves the same at any angle and turns with the layer. Selections stay in canvas coordinates (mapped onto the turned layer), blur still spreads past the turned box, and emboss keeps its light at the canvas's top left. Scaled and rotated layers are resampled without the overshoot rim of Lanczos/bicubic filters: each resampled pixel stays within the colours and alpha of the source pixels under it. Noise is seeded (default 0).

**Denoise** (`denoise`) is an edge-preserving, non-destructive noise reduction for photos. Luminance (grain) is cleaned with non-local means: each pixel is averaged with the pixels around it whose 5 × 5 neighbourhoods look like its own, so flat areas and skies smooth out while edges and fine lines stay sharp (a Gaussian blur that removes as much grain flattens them). Chroma (colour blotches) is smoothed at reduced resolution, guided by the cleaned luminance, so colour does not bleed across an edge, and colour edges and fine colour detail stay as drawn. `--luminance` and `--chroma` are 0–100 strengths (default 50 each; a positional value or `amount` sets both) and are relative to the noise measured in the image itself, so one setting suits a clean and a grainy photo; 0 leaves that part alone. `--search` (1–10 px, default 5) is the search window radius. Cost: time grows with the number of window positions tried (every position within 2 px, then every other one farther out: 72 at the default, 124 at 7, at most 232 at 10); at the default it is about 1 second per megapixel (four threads, the same result whatever the thread count), so `--search 3` (36 positions) halves the cost on large photos. Previews render a reduced copy, so they are quick. It needs no dependencies beyond NumPy and Pillow, and exports to SVG rasterize the layer as for other pixel effects.

Blend modes: normal, multiply, screen, overlay, darken, lighten, difference, add, subtract.

## Layout, templates, validation

```bash
vixl variable set title 'Night Shift'
vixl variable delete unused
vixl constrain title --center-x canvas --below portrait 60
vixl constrain logo --right canvas.right-40 --top canvas.top+40
vixl unconstrain logo
vixl render --set title='Late Edition' --out variant.png
vixl assert canvas.width == 1920
vixl assert layer.logo.exists
vixl assert layer.logo.bounds within canvas
vixl assert text.title.font-size '>=' 48
vixl validate instagram-post
vixl validate --rules rules.json
vixl validate --rules 'text.title.font-size >= 120' --rules 'layer.logo.bounds within canvas'
```

A constraint uses `canvas` or a layer plus `.left`, `.right`, `.top`, `.bottom`, `.center-x`, `.center-y`, optionally followed by a numeric `+offset` or `-offset`. One constraint per axis is supported: `constrain` adds to a layer's existing constraints, so switching an axis from `left` to `center-x` needs `unconstrain` first (the error names both anchors). Cycles and dangling references fail atomically. Layer references become stable IDs, so renames do not break them. Delete dependents' constraints before deleting their target.

Variables use `${name}` interpolation in text, colors, gradient fills, and raster asset identifiers. Asset variables must refer to **embedded asset IDs**; render overrides never load arbitrary files. Text dimensions are recomputed when variables change. Undefined variables fail explicitly. Text with `hide_if_empty` is not drawn while it is empty after substitution, and a `stack` group re-flows around it ([empty content and stacks](design-tools.md#empty-content-and-stacks)).

Validation profiles: instagram-post / instagram-square (1:1; Instagram also checks PNG under 8 MB), story (9:16), youtube-thumbnail (16:9). All check layer bounds; artwork marked `layer-intent NAME --role decoration` that bleeds off the edge on purpose is a warning, not an error (unless it is text or entirely off the canvas). Text under 24 px is a warning. Font sizes, here and in `text.NAME.font-size` assertions, are the sizes text renders at: a linked character style's size takes precedence. Visible text with characters no font can draw fails validation. Rules files are JSON arrays of assertion strings; `--rules` also takes a single assertion and can repeat. Comparisons support `==`, `!=`, `>`, `<`, `>=`, `<=`; quote shell operators. Assertions are parsed, never evaluated as Python.

## Scripts, presets, history

A `.vixlscript` contains one editing command per line; blank lines and `#` comments are allowed. Quote colors and text. It is a bounded Vixl language, not a shell or Python. Files referenced in scripts resolve relative to the script. Project lifecycle, exports, AI calls, and history commands are invoked outside scripts. Use shell scripts or the Python API to orchestrate those steps.

```bash
vixl run cleanup.vixlscript
vixl apply operations.json --dry-run
vixl apply operations.json --check bounds contrast --preview preview.png   # findings and a preview in the same call
vixl apply operations.json --check --suites brief                         # also run the attached suite 'brief'
vixl each layer --type raster --name 'card-*' -- saturation -10
vixl preset save gritty portrait
vixl preset show gritty
vixl preset apply gritty other --set noise=0.03
vixl undo 3
vixl redo
vixl checkpoint clean
vixl branch vivid
vixl checkout clean
vixl history
vixl branches
vixl compare vivid clean --out comparison.png
vixl compact --dry-run   # what compacting would drop
vixl compact             # drop undo history and unused embedded files
```

Presets save the active/target layer's complete effect stack. Applying one assigns fresh effect IDs and captures the current selection. Branches name movable tips; checkpoints are fixed. Checking out a checkpoint detaches history; create a branch to name subsequent work. Undo/redo moves the current branch tip; alternate history nodes remain available by ID. Transactions allow provisional edits across processes and commit as one undoable history entry. They do not hide provisional state from other clients of the same project.

A document keeps every embedded file that some revision uses, so undo can restore a replaced image or an earlier font pairing; saving drops only files no revision references. `check` reports the files the current design does not use (an `info` finding of the `fonts` check, with `unused_assets`: each file's `asset`, `kind`, `bytes`, and `fonts` for a registered font no text, role or fallback uses). `vixl compact` (MCP `vixl_history(action="compact")`, REST `POST /history/compact`, Python `project.compact()`) is the explicit way to shed them: it discards all undo history, the redo stack, branches and checkpoints, unregisters unused fonts (`--keep-fonts` keeps them), and drops every embedded file the current design does not use. The design does not change. The result lists what went (`revisions_dropped`, `branches_dropped`, `checkpoints_dropped`, `fonts_unregistered`, `assets_dropped` with bytes, `bytes_dropped`); `--dry-run` (`dry_run: true`) reports without changing anything. Nothing compacts implicitly, and an open transaction must be committed or rolled back first.

`batch` refuses output collisions and existing destinations, reports each input's result, and exits nonzero if any fail. Earlier successful outputs remain if a later item fails.

## Agent resources and discovery (0.11)

`vixl commands --json` lists available CLI commands and `vixl shapes --json` lists shape shortcuts. `COMMAND --help` works without an open document. Editing results use compact changes by default; `--detail full` restores snapshots.

Use `palette list|show|add|apply`, `template list|show|add|new|apply`, `guidance list|show|add|apply|import|remove`, and `font list|import` for reusable design data. `providers list|add|refresh` and `models [--provider NAME] [--capability NAME] [--refresh]` discover available AI models. SVG joins PNG/JPEG/WebP/TIFF/AVIF export; PNG keeps transparency and JPEG uses `--background` for flattening. See [resource syntax and examples](agent-resources.md) and [model discovery](providers.md).

### Group checks and SVG assurance

`check` inspects visible group descendants, including nested text. Selecting a group includes its descendants; selecting a child checks that child. Bounds and safe areas use canvas coordinates (`bounds` also reports boxed text, with a `text-layout` width and height, that no longer fits its box and is cut off), overlap uses rendered coverage, and thumbnail legibility accounts for ancestor scaling. Contrast compares grouped text with its backdrop through ancestor transforms and opacity. Hidden or fully transparent ancestors exclude their children. Characters that no font can draw (they render as empty boxes) are a `fonts` error in every `check`, whichever checks are selected, and an automatic `missing-glyphs` result in every suite, so checked production and gated group edits catch them. Top-level text is contrast-checked from one shared render; grouped text renders its own backdrop. Outlined text (a `stroke` style at least 3 px wide and 2% of its font size) passes when either its fill or its outline contrasts with the backdrop. Text fails when a tenth of its glyph pixels fall below the required ratio; the issue's `region` (and `weakest_region` in `measure --target`) is where those weakest pixels are, often where the text crosses an outline or edge. Repeated groups emit a coverage warning because geometry checks assess the base instance; visually inspect the repeated copies. Text whose contrast cannot be measured (for example, it is wholly off the canvas) is an error, never a silent pass; `passed` means no errors, so also inspect `warnings` and `issues` and visually review the result. Checks judge what a layer draws, not its box: shapes use their path geometry including stroke (`geometry_bounds`), so a path on a full-canvas box is checked by its drawn shape, and overlap uses the ink of strokes, shadows and glows. Layers marked `role: background`, and non-text layers whose drawn geometry covers the canvas, are background and skipped; `checked` reports `layers_checked` and `layers_total`. Shapes and gradients that run past two or more canvas edges (a hill, a glow) are intentional bleed and report as informational. Safe area defaults to the canvas's own `safe` (a pixel inset, or a `{left, top, right, bottom}` object, measured from the trim edge); pass `safe_area` to override. The thumbnail legibility test (320 px wide; `thumbnail_width: null` or `--thumbnail-width off` disables it) is a warning only for social, icon and app-store sizes and informational elsewhere; a chart's small labels are one finding per chart (with `chart`), and on other pieces more than three small text layers are one note listing them all. `color_vision` also compares chart series colors and flags pairs that merge under a color-vision deficiency; mark a chart whose series also differ by labels or patterns with `layer-intent color_vision_safe`.

`connected` (opt-in: `check --checks connected`, `--connect-tolerance 2`) looks inside every visible group that is one object (a mascot, a character, a prop built from shapes; charts, drawings, repeats and speech bubbles are skipped). The drawn ink of each direct part is compared on the canvas: parts whose ink touches or overlaps within the tolerance form one piece, the piece with the most ink is the main body, and every other part is a `connected` warning with its `gap` in pixels and its `group`. Text parts are ignored. A document with a timeline is checked at its poster, middle and last frames (`frame` names the one where a part first comes loose). Mark a part that floats on purpose (a spark, a thrown ball), or a group whose parts are separate by design, with `layer-intent detached_ok`. To look at one object alone, preview it with `isolate` (`vixl_render_preview(isolate=["cat"])`).

Saved SVG exports report `svg.vector_only` and `svg.raster_fallbacks` in the CLI result so embedded bitmaps are visible without opening the SVG metadata. Use `export logo.svg --svg-policy strict` to reject all embedded raster content. Exporting to `-` still writes only SVG bytes. Supported grouped shapes and outlined text remain vectors; unsupported appearances may rasterize in the default appearance policy.

## Finish, styles and the guide

```bash
vixl guide                               # start-here recipe and every kind of work
vixl guide a mascot for a coffee brand   # approach, operations, layouts, looks, styles, example
vixl guide operations                    # every operation by purpose, with summaries
vixl looks                               # the finishing looks
vixl look LAYER glow [--color C] [--amount 0-1] [--remove]
vixl radial-repeat LAYER --count 12 [--cx 50%] [--cy 50%] [--sweep 360] [--start-angle D] [--mirror] [--no-group] [--name N]
vixl layer-intent LAYER --allow-crop     # a deliberate edge crop: checks report it as informational
vixl layout apply NAME --palette '["#0f172a","#1e293b","#38bdf8"]' --keep-order
vixl palette apply NAME --keep-order | --roles '{"background": 0, "accent": "#e11d48"}'
vixl styles [list [QUERY] | show NAME] | styles apply NAME [--palette] | styles check [NAME…]
vixl style-set NAME… [--options JSON]    # tag the document ('none' clears)
vixl check --checks style [--style NAME…]
```

## Sizes, layouts, color, print, brushes and timelines (0.13)

```bash
vixl sizes [--category print|stationery|social|icons|logos|…] [--search TEXT]
vixl sizes show NAME [--dpi N] [--landscape|--portrait] [--bleed]
vixl new [NAME|WxH] [--purpose social|poster|slides|print|logo|icon|favicon|…] [--seed N]
    [--variety low|medium|high|fixed] [--background COLOR] [--no-fonts] [--dpi N] [--landscape|--portrait]
    [--bleed [AMOUNT]] [-o FILE]   # e.g. new letter --bleed; no size: the purpose's size, else 1080x1080
vixl canvas size NAME [--dpi N] [--landscape] [--bleed] | canvas dpi N

vixl layout list | layout show NAME
vixl layout apply NAME [--seed N] [--set title=…] [--set subtitle=…] [--set body=…] [--set label=…]
    [--set cta=…] [--set caption=…] [--set items=…] [--set image=ASSET] [--palette NAME|JSON] [--colors JSON]
    [--mode light|dark] [--type-scale NAME|RATIO] [--base-size PX] [--density airy|balanced|dense]
    [--align left|center|right] [--accent rule|bar|dot|block|outline|none] [--font F] [--display-font F]
    [--transparent] [--prefix P] [--replace]
vixl type-scale [--base PX] [--ratio golden|perfect-fourth|…|1.3] [--prefix P] [--color C]

vixl color [info] COLOR… [--ink-limit 300] | color convert COLOR --to hex|rgb|hsl|hsv|hwb|cmyk|lab|lch|oklab|oklch|css
vixl color harmony COLOR --scheme complementary|analogous|triadic|split-complementary|tetradic|square|monochromatic|tints|shades|tones [--count N]
vixl color scale COLOR | color mix A B [--amount 0.5] [--space oklab] | color contrast FG BG | color names QUERY
vixl palette-generate NAME COLOR [--scheme scale|HARMONY] [--count N]

vixl export FILE.pdf|.tif|.jpg --cmyk [--icc PROFILE.icc] [--intent perceptual|relative|saturation|absolute]
    [--black-generation 0–1] [--ink-limit 100–400] [--dpi N]
vixl export FILE --proof [--icc PROFILE.icc] | --simulate protanopia|deuteranopia|tritanopia|achromatopsia
vixl export FILE.ico [--icon-sizes 16 32 48] | export-icons --out DIR [--set web|apple|android|windows|all]
vixl check --checks print color_vision [--ink-limit 300] [--min-ppi 200]

vixl brushes | brush-define NAME --base BRUSH [--settings JSON] [--description TEXT]
vixl paint-layer [--name N] [--width W] [--height H] [--x X] [--y Y]
vixl paint [LAYER] --brush NAME (--points JSON | --path SVG) [--pressure JSON] [--size N] [--color C]
    [--opacity 0–1] [--erase] [--seed N] [--space canvas|layer] [--settings JSON]
vixl paint-clear [LAYER] [--last N]

vixl easings | timeline | timeline set [--duration T] [--fps N] [--loop N] [--clear]
vixl keyframe LAYER|canvas PROPERTY TIME VALUE [--easing E] | keyframe-remove LAYER [--property P] [--time T]
vixl animate LAYER PROPERTY --to V [--from V] [--start T] [--end T | --duration T] [--easing E]
vixl animate-preset LAYER|canvas PRESET [--start T] [--duration T] [--easing E] [--amount N] [--distance N] [--to C] [--no-fade]
vixl text-animate TEXT PRESET [--unit char|word|line] [--start T] [--duration T] [--stagger T|N%] [--easing E]
    [--direction forward|reverse|center|edges|random] [--seed N] [--mode in|out|in-out] [--distance N] [--amount N]
    [--rotate DEG] [--from C] [--repeat] [--remove] [--no-extend]
vixl marker NAME TIME | marker NAME --delete
vixl render --time T --out FILE | timeline-sheet --out FILE [--count 8] [--columns N] [--times T…]
vixl export-timeline --out FILE.gif|.png|.webp|.zip|.mp4|.webm [--format sheet] [--fps N] [--scale F]
    [--start T] [--end T] [--background C] [--columns N] [--quality N] [--overwrite]
```

Times are milliseconds or `1.5s`, `250ms`, `50%` or a marker name. Details: [sizes and layouts](sizes-and-layouts.md), [color and print](color-and-print.md), [brushes and animation](brushes-and-animation.md).

## Linked documents and print merge (0.19)

```bash
vixl link FILE.vixl [--name N] [--x X] [--y Y] [--width W] [--height H] [--fit fill|fit|stretch]
    [--position top-left|0.5,0.5] [--crop X,Y,W,H] [--artboard NAME] [--source-page P] [--set NAME=VALUE]…
vixl link-set LAYER [--source F] [--fit …] [--position …] [--crop …] [--artboard …] [--source-page …]
    [--set NAME=VALUE]… [--clear artboard|source_page|variables|crop]…
vixl link-refresh [LAYER] | link-embed LAYER | links          # links: every link, ok / stale / missing / cycle

vixl merge [TEMPLATE.vixl] --data rows.csv --out sheets.pdf [--sheet-document sheets.vixl]
    [--size letter] [--cols 2] [--rows 3] [--gutter 0.125] [--margin 0.5] [--bleed template|0.125]
    [--no-crop-marks] [--registration] [--slug TEXT] [--copies N] [--set NAME=VALUE]…
    [--unknown warn|error|ignore] [--defaults error|warn|ignore] [--check design]
    [--skip-invalid] [--dry-run] [--replace]
vixl merge --rerun sheets.vixl [--data new.csv] [--out new.pdf]
```

[Linked documents](linked-documents.md) render another `.vixl` live (`--allow-linked` for sources outside the current
folder); [imposition](imposition.md) lays CSV rows out on print sheets with crop marks, as a vector-text PDF and an editable
sheet of links.
