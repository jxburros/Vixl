# Command reference

For complete first-use workflows, see [getting started](../getting-started.md) and the
[tutorial index](../README.md#learn-by-making). Use `vixl COMMAND --help` for the installed
runtime's exact arguments, and pass `-p file.vixl` explicitly for editing commands.

## Pages, forms, drawing and workflow discovery (0.18)

These commands complement the earlier editing reference below. Examples assume an open
project with appropriate layers or input files. See each guide for complete creation steps.

| Task | Command | Reference |
| --- | --- | --- |
| Add/select/list pages | `page add NAME`, `page select NAME`, `pages` | [Pages and decks](../guides/output/slides.md) |
| Shared page artwork | `master add NAME`, `master select NAME` | [Masters](../guides/output/slides.md#masters) |
| Speaker notes | `page set NAME --notes 'Talking points'` | [Page settings](../guides/output/slides.md#how-pages-work) |
| Deck overview | `render --page all --out sheet.png` | [Seeing pages](../guides/output/slides.md#seeing-pages) |
| Presentation checks | `check --checks deck` | [Deck checks](../guides/output/slides.md#deck-checks) |
| Editable slides / page PDF | `export deck.pptx`, `export deck.pdf` | [Export guide](../guides/output/exporting.md) |
| Rich text | `rich-text 'A **bold** point' --name body --width 900` | [Rich text](../guides/text/rich-text.md) |
| Field layer | `field add email --kind text --label Email --required` | [Forms](../guides/output/forms.md) |
| Field inspection | `field list`, `render --show-fields --out fields.png` | [Forms](../guides/output/forms.md) |
| Fillable PDF | `export form.pdf --fillable` | [Forms](../guides/output/forms.md#the-fillable-pdf) |
| Filled copy | `form fill --set email=ada@example.com --out ada.pdf` | [Forms](../guides/output/forms.md#filling) |
| Validate CSV fills | `form fill --data rows.csv --dry-run` | [Form tutorial](../tutorials/forms-and-decks.md) |
| Drawing cleanup | `drawing import sketch.jpg --name sketch`, `drawing straighten sketch` | [Drawing](../guides/images/drawing.md) |
| Drawing preservation | `drawing report sketch`, `drawing compare sketch --out compare.png` | [Drawing](../guides/images/drawing.md) |
| Organic shape | `organic sunflower --name bloom --seed 7` | [Organic shapes](../guides/shapes/organic.md) |
| Polar grid | `grid dial --kind polar --rings 3 --spokes 12` | [Guides and grids](../guides/layout/guides.md) |
| Workflow contract | `workflow schema` | [Production](../guides/automation/production.md), [studio](../guides/automation/studio.md) |
| Lyric video | `workflow lyric-video-export --request request.json --workspace .` | [Lyric videos](../guides/motion/lyric-video.md) |
| Whole piece in one call | `compose --request req.json [--preview p.png] [--workspace DIR]` | [Interfaces](interfaces.md#build-a-piece-in-one-call) |
| Pixel diff of two files | `diff before.vixl after.png [--out diff.png] [--mode diff\|side-by-side] [--threshold 8] [--max-fraction F] [--overwrite]` | [CI](../guides/automation/ci.md#the-same-checks-locally) |
| Proof page | `workflow proof --request proof.json --workspace .` | [Proof pages](../guides/automation/production.md#proof-pages) |
| Logo package | `workflow logo-package --request logo.json --workspace .` | [Logo packages](../guides/automation/production.md#logo-packages) |
| Delivery package | `package (--production out/production.json \| --files GLOB…) --out delivery.zip [--source DOC.vixl] [--name TEMPLATE] [--layout by-format\|by-artboard] [--lock FILE] [--decisions FILE] [--no-check] [--no-proof] [--dry-run] [--overwrite]` | [Delivery packages](../guides/automation/production.md#delivery-packages) |
| Brand guidelines | `workflow brand-board --request board.json --workspace .`; `brand validate`, `brand show [--preset NAME]` | [Brands](../guides/layout/brands.md#brand-board) |
| Mockups and merch | `workflow mockup --request mock.json --workspace .`; `workflow mockup-list --request '{}' --workspace .` | [Merch mockups](../guides/output/merch-mockups.md) |
| Print-ready art per area | `workflow print-art --request print.json --workspace .` | [Print-ready art](../guides/output/merch-mockups.md#print-ready-art) |
| Brand packages | `brand init [--name N] [--palette P] [--pairing P] [--font ROLE=FILE]`, `brand pack OUT.vixlbrand`, `brand install FILE.vixlbrand [--preset-only [--as NAME]] [--overwrite]`, `brand element NAME --from FILE.vixl [--object GROUP]` | [Brand packages](../guides/layout/brands.md#brand-packages) |
| App animation package | `workflow app-animation-package --request package.json --workspace .` | [App animation packages](../guides/motion/animation-authoring.md#app-animation-packages) |
| Character packages | `workflow character-package --request char.json --workspace .` (writes `.vixlchar`); `workflow character-discover --request '{}' --workspace .`; `workflow character-inspect`, `workflow character-place --request place.json --workspace .` | [Character packages](../guides/motion/animation-authoring.md#character-packages) |
| Six-second loop | `template new video-tip -o tip.vixl --set title=… --set subtitle=… --set cta=…` (also `video-launch`, `video-event`) | [Short templates](../guides/motion/animation-authoring.md#joint-pose-keys-and-short-templates) |
| Readable source folder | `unpack design.vixl design-source`, `pack design-source design.vixl [--overwrite]` | [Reviewing in Git](#reviewing-editable-projects-in-git) |
| Documents and tool calls from earlier releases | `convert OLD.vixl -o NEW.vixl [--look preserve\|current] [--dry-run] [--report R.json]`, `convert DIR --out OUTDIR`, `convert-batch OLD-CALLS.json` | [Converting](converting.md) |
| Import SVG, PDF or a Figma file as editable layers | `import artwork.svg [--svg-mode editable\|auto\|appearance]`, `import flyer.pdf --page 1`, `import KEY --format figma [--node 1:2] [--rasterize-unsupported]` | [Interfaces](interfaces.md#import-existing-artwork), [Figma import](../guides/images/figma.md) |
| Schema of a `.vixl` file | `schema document` (`schema OPERATION…` for operations) | [File format](file-format.md) |
| Composition check | `check --checks composition` (on by default; `--profile final` gates on it) | [Composition](../guides/layout/guides.md#composition) |
| Emoji catalog and packs | `emoji list --query wave`, `emoji template face --out smile.vixl`, `emoji export --destination discord --emojis 👋 --out pack.zip` | [Emoji](#emoji-024) |

Since 0.19.0, `export --alpha auto|keep|flatten` controls supported image formats.
See [exporting](../guides/output/exporting.md#image-output-and-alpha) and the
[release notes](../../CHANGELOG.md#0190).

[Documentation home](../README.md) · [Getting started](../getting-started.md) · [Visual gallery](../gallery.md)

Checked automation and production: `workflow schema` lists the actions accepted by
`workflow ACTION --request FILE --workspace DIR`. See [production](../guides/automation/production.md) for
check suites, recipes, matrices, libraries, jobs and films. New editing commands include
`suite-set`, `suite-capture`, `role-set`, `motion-define`, `motion-apply`, `action-define`,
`action-apply`, `fit-text`, `arrange-grid`, `adapt-layout` and `recipe-set`; each has `--help`.
`edit-layers --where JSON --do JSON [--expect N] [--dry-run]` runs an operation on every layer matching a selector, and
`adapt-layout --size story [--scale fit|fill|width|height|N] [--anchors JSON] [--where JSON] [--text keep] [--min-text N] [--no-safe] [--no-together] [--[no-]recompose] [--arrangements stack-vertical side-by-side hero-top proportional]` (without
`--targets`) resizes the canvas and re-composes the document: an unedited `layout-apply` design is rebuilt from its recipe, `--arrangements` keeps the arrangement the checks score best, anything else is re-laid out proportionally; see [operations](operations.md#bulk-edits-and-resizing-a-whole-layout-unreleased).

Vixl is a headless design engine for AI agents; people can drive the same interfaces.

See [spacing checks and pixel animation](../guides/motion/pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](../guides/shapes/design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

Global options can appear before or after the command: `--project FILE` / `-p FILE`, `--json`, `--allow-linked`, `--plugins`, `--max-pixels N`, `--detail brief|compact|full`, `--version`. The default project is stored in the current directory's `.vixl-session.json` (written by `vixl new` and `vixl open`); a command without `-p` edits it, its terminal summary starts with the file name (`hello.vixl: added text "Hi"`), the first such command prints `note: editing hello.vixl` on stderr, and edit, check, render and export results carry its `path`. `vixl new` needs `-o FILE` (or `-p FILE`). Use explicit paths in CI and concurrent workflows. A mistyped command or option is answered with the closest real ones (`vixl rendr`: did you mean render?; `--colour`: did you mean --color?). `vixl COMMAND --help` prints syntax for editing commands.

**Output.** In a terminal a command prints a short human summary (`created a.vixl  800×600  bg #18283b`, `added text "title"`, `check failed (16 checks) — 1 error, 0 warnings` with one line per finding, `exported hello.png (16.2 KB)`); a result with no dedicated summary lists its main fields. When stdout is not a terminal (a pipe, a file, CI), or `--json` is given, or `VIXL_JSON=1` is set, the command prints the full JSON result exactly as before. Exit codes do not change. Errors are one `ERROR:` line on stderr (with suggestions appended in a terminal), or the JSON error with `--json` or `VIXL_JSON=1`.

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

## Render cache and profiling

`render` and `export` of a saved document keep its rendered layers and frame in the per-user disk cache, so the
next export of the unchanged document, in a new process, reads the frame back instead of drawing it.

| Command or variable | Behavior |
| --- | --- |
| `cache info` | The cache directory, `entries`, `bytes`, the size cap (`budget_bytes`, `max_mb`) and whether it is `enabled` |
| `cache clear` | Delete the cached PNGs and their ledgers; reports `removed` and `bytes` |
| `VIXL_RENDER_CACHE=DIR` / `=off` | Use another cache directory (default `~/.cache/vixl/render`), or no disk cache |
| `VIXL_CACHE_MAX_MB=256` | The cache's size cap in megabytes; the least recently used PNGs are removed past it |
| `VIXL_PROFILE=1` | Return a `render_profile` (per-layer times, cache hits and misses, incremental renders) with every result; see [troubleshooting](../troubleshooting.md#find-out-why-a-render-is-slow) |

## Documents and output

| Command | Behavior |
| --- | --- |
| `new 1920x1080 -o poster.vixl --background '#111111'` | Create a project; refuses existing files unless `--overwrite` |
| `open poster.vixl` | Select an existing project for this directory |
| `save [copy.vixl]` | Save, or save as a new selected project |
| `status`, `inspect [LAYER]`, `describe`, `layers [--full]` | JSON state, including resolved bounds; `layers` abbreviates long path data and point lists (`--full` or `inspect LAYER` shows them) |
| `manifest`, `dependencies`, `reproduce --check` | List assets/fonts/providers; check current renderability |
| `reproduce --reference PNG [--tolerance N] [--max-fraction F]`, `reproduce --write-lock FILE`, `reproduce --lock FILE` | Verify a render against an approved reference or a lockfile; reports `renderable`, `environment-matched` or `reference-verified` and located drift ([reproduction](agent-trust.md#reproduction)) |
| `reproduce --write-lock FILE --export png jpg:quality=80 mp4:fps=24 [--frames N \| --times T…]`, `reproduce --lock FILE --export [FORMAT[:OPTION=VALUE,…]…] [--export-tolerance N] [--export-visual] [--report]` | Record exports (and sampled timeline frames) in a version 2 lockfile, then encode them again: `byte_identical` and `visually_equivalent` per export, `page`, `artboard`, `frame`, `export-setting` and `toolchain` drift located by name; `--report` prints the compact manifest-ready summary |
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
vixl import artwork.svg --svg-mode auto    # SVG as editable layers; a Vixl SVG restores its document
vixl import flyer.pdf --page 1             # a PDF page as editable text, paths and images
vixl import KEY --format figma --node 1:2  # a Figma file URL or key (one frame, or --rasterize-unsupported for unmappable nodes); needs FIGMA_TOKEN, see figma.md
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

`add` and `import` take `--credit` and `--license`, kept in the layer's provenance for attribution; `import` also takes an `https://` image URL (fetch policy in [architecture](architecture.md#trust-and-security), more in [interfaces](interfaces.md#import-existing-artwork)). `layer` is an optional namespace. `rm` aliases remove and `mv` aliases move. Rotation is clockwise and expands the layer bounds; it turns about the layer's pivot, by default its centre, which stays where it was (stored x/y are the expanded bounds' top-left, so they move by half the growth). JSON `about` keeps another point fixed: an anchor name such as `top-left`, `[x, y]` fractions of the unrotated box, or `pivot`. Crop coordinates refer to the original embedded raster. Resize with one dimension changes only that dimension of a shape, text box, group or solid (the other side keeps its size, and the result reports it under `normalized`), but scales an imported image (raster layer) proportionally so a photo is not stretched. `--keep-aspect` (JSON `keep_aspect: true`) scales the other side proportionally on any layer; `--no-keep-aspect` (`keep_aspect: false`) changes just the given side of an image; give both dimensions to stretch. Numeric scale values are factors; `80%` is `0.8`; a negative factor (`-1`, or `--x -1` for one axis) mirrors the layer as `flip` does and scales by its size. Opacity is 0–1 (`opacity portrait 0.75`); `75%` is read as 0.75, and a bare `75` is an error. `pivot LAYER X Y --canvas` takes a document point; `group NAME A B --above LAYER` (or `--below`) chooses where the new group lands; `shape` takes `--opacity`, `--rotation` and, with `--target`, `--space canvas`.

Alignment supports center, center-x/y, left/right/top/bottom and corner pairs. Absolute moves and alignment clear constraints. `move x +20` and `--relative` add offsets.

```bash
vixl solid --name panel --width 400 --height 200 --color '#26344e'
vixl gradient --name sky --start '#152641' --end '#635e83' --direction vertical
vixl text add 'Hello' --name title --size 96 --font NotoSans-Regular.ttf --color white --x center --y 120
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
history entry, so `undo` restores them. Custom `--font /path/to/font.ttf` imports and embeds a font. Other font names use Pillow's system-font lookup. Font substitution is never silent. HarfBuzz shaping and shared PNG/SVG outlines support ligatures, combining marks and scripts covered by the selected font, with multiline text, wrapping/fitting and path/warp layouts. Bitmap/color fonts and unsupported Unicode isolate controls retain appearance fallbacks. See [local artistic filters and SVG policies](../guides/images/artistic-filters.md).

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
vixl mask gradient beam --start white --end black --direction horizontal   # fade the layer out
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

**Denoise** (`denoise`) is an edge-preserving, non-destructive noise reduction for photos. Luminance (grain) is cleaned with non-local means: each pixel is averaged with the pixels around it whose 5 × 5 neighbourhoods look like its own, so flat areas and skies smooth out while edges and fine lines stay sharp (a Gaussian blur that removes as much grain flattens them). Chroma (colour blotches) is smoothed at reduced resolution, guided by the cleaned luminance, so colour does not bleed across an edge, and colour edges and fine colour detail stay as drawn. `--luminance` and `--chroma` are 0–100 strengths (default 50 each; a positional value or `amount` sets both) and are relative to the noise measured in the image itself, so one setting suits a clean and a grainy photo; 0 leaves that part alone. `--search` (1–10 px, default 5) is the search window radius. Cost: time grows with the number of window positions tried (every position within 2 px, then every other one farther out: 72 at the default, 124 at 7, at most 232 at 10); at the default it is about 1 second per megapixel (four threads, the same result whatever the thread count), so `--search 3` (36 positions) halves the cost on large photos. Previews render a reduced copy, so they are quick. A photo shown larger than its own pixels (scaled up in its document, or a linked crop of a corrected master enlarged for an Instagram or caption size) is denoised at its own pixels before it is scaled up, so the enlargement shows the cleaned master instead of grain that upsampling smoothed past the noise estimate. It needs no dependencies beyond NumPy and Pillow, and exports to SVG rasterize the layer as for other pixel effects.

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

Variables use `${name}` interpolation in text, colors, gradient fills, and raster asset identifiers. Asset variables must refer to **embedded asset IDs**; render overrides never load arbitrary files. Text dimensions are recomputed when variables change. Undefined variables fail explicitly; `$${name}` draws the literal text `${name}`. Text with `hide_if_empty` is not drawn while it is empty after substitution, and a `stack` group re-flows around it ([empty content and stacks](../guides/shapes/design-tools.md#empty-content-and-stacks)).

Validation profiles: instagram-post / instagram-square (1:1; Instagram also checks PNG under 8 MB), story (9:16), youtube-thumbnail (16:9). All check layer bounds; artwork marked `layer-intent NAME --role decoration` that bleeds off the edge on purpose is a warning, not an error (unless it is text or entirely off the canvas). Text under 24 px is a warning. Font sizes, here and in `text.NAME.font-size` assertions, are the sizes text renders at: a linked character style's size takes precedence. Visible text with characters no font can draw fails validation. Rules files are JSON arrays of assertion strings; `--rules` also takes a single assertion and can repeat. Comparisons support `==`, `!=`, `>`, `<`, `>=`, `<=`; quote shell operators. Assertions are parsed, never evaluated as Python.

## Scripts, presets, history

A `.vixlscript` contains one editing command per line; blank lines and `#` comments are allowed. Quote colors and text. It is a bounded Vixl language, not a shell or Python. Files referenced in scripts resolve relative to the script. Project lifecycle, exports, AI calls, and history commands are invoked outside scripts. Use shell scripts or the Python API to orchestrate those steps.

```bash
vixl run cleanup.vixlscript
vixl apply operations.json --dry-run
vixl apply operations.json --check bounds contrast --preview preview.png   # findings and a preview in the same call; also check.regions and real-size crops preview-region1.png, preview-region2.png
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
vixl save --prune-fonts  # keep undo history; leave out fonts no revision draws
```

Presets save the active/target layer's complete effect stack. Applying one assigns fresh effect IDs and captures the current selection. Branches name movable tips; checkpoints are fixed. Checking out a checkpoint detaches history; create a branch to name subsequent work. Undo/redo moves the current branch tip; alternate history nodes remain available by ID. Transactions allow provisional edits across processes and commit as one undoable history entry. They do not hide provisional state from other clients of the same project.

A document keeps every embedded file that some revision uses, so undo can restore a replaced image or an earlier font pairing; saving drops only files no revision references. `check` reports the files the current design does not use (an `info` finding of the `fonts` check, with `unused_assets`: each file's `asset`, `kind`, `bytes`, and `fonts` for a registered font no text, role or fallback uses). `vixl compact` (MCP `vixl_document(action='compact')`, REST `POST /history/compact`, Python `project.compact()`) is the explicit way to shed them: it discards all undo history, the redo stack, branches and checkpoints, unregisters unused fonts (`--keep-fonts` keeps them), and drops every embedded file the current design does not use. The design does not change. The result lists what went (`revisions_dropped`, `branches_dropped`, `checkpoints_dropped`, `fonts_unregistered`, `assets_dropped` with bytes, `bytes_dropped`); `--dry-run` (`dry_run: true`) reports without changing anything. Nothing compacts implicitly, and an open transaction must be committed or rolled back first.

To shed unused fonts without losing undo, save with `vixl save --prune-fonts` (Python
`project.save(prune_fonts=True)`, or `project.prune_fonts(dry_run=True)` to see what would go). It unregisters the
fonts that no revision (the current design, undo and redo history, branches and checkpoints) draws from a layer, role,
style, fallback list, master or page, removes them from every revision so undo restores the same design, and leaves
their files out; the CLI result lists them under `pruned` (`fonts_unregistered`, `assets_dropped`, `bytes_dropped`).
A font drawn only in an earlier revision stays until `compact`. It is opt-in because a font chosen only from outside
the document (an export-time variable, a data-merge column, a recipe input or a document that links this one) looks
unused from inside it.

`batch` refuses output collisions and existing destinations, reports each input's result, and exits nonzero if any fail. Earlier successful outputs remain if a later item fails.

## Agent resources and discovery (0.11)

`vixl commands --json` lists available CLI commands and `vixl shapes --json` lists shape shortcuts. `COMMAND --help` works without an open document. Editing results use compact changes by default; `--detail full` restores snapshots.

Use `palette list|show|add|apply`, `template list|show|add|new|apply`, `guidance list|show|add|apply|import|remove`, and `font list|import` for reusable design data. `providers list|add|refresh` and `models [--provider NAME] [--capability NAME] [--refresh]` discover available AI models. SVG joins PNG/JPEG/WebP/TIFF/AVIF export; PNG keeps transparency and JPEG uses `--background` for flattening. See [resource syntax and examples](../guides/layout/agent-resources.md) and [model discovery](providers.md).

### Group checks and SVG assurance

`check` inspects visible group descendants, including nested text. Selecting a group includes its descendants; selecting a child checks that child. Bounds and safe areas use canvas coordinates (`bounds` also reports boxed text, with a `text-layout` width and height, that no longer fits its box and is cut off), overlap uses rendered coverage, and thumbnail legibility accounts for ancestor scaling. Contrast compares grouped text with its backdrop through ancestor transforms and opacity. Hidden or fully transparent ancestors exclude their children.

Characters that no font can draw (they render as empty boxes) are a `fonts` error in every `check`, whichever checks are selected, and an automatic `missing-glyphs` result in every suite, so checked production and gated group edits catch them.

Top-level text is contrast-checked from one shared render; grouped text renders its own backdrop. Outlined text (a `stroke` style at least 3 px wide and 2% of its font size) passes when either its fill or its outline contrasts with the backdrop. Text fails when a tenth of its glyph pixels fall below the required ratio; the issue's `region` (and `weakest_region` in `measure --target`) is where those weakest pixels are, often where the text crosses an outline or edge.

Repeated groups emit a coverage warning because geometry checks assess the base instance; visually inspect the repeated copies. Text whose contrast cannot be measured (for example, it is wholly off the canvas) is an error, never a silent pass; `passed` means no errors and no finding whose `action` is `fix`, so also inspect `review` findings (`by_action`) and visually review the result.

Checks judge what a layer draws, not its box: shapes use their path geometry including stroke (`geometry_bounds`), so a path on a full-canvas box is checked by its drawn shape, and overlap uses the ink of strokes, shadows and glows. Decoration (`role: decoration`) may overlap shapes and sit around text, but where its pixels fall inside a text layer's glyph area (each line's ink box plus a 10% halo) the overlap check adds a `review` warning, `overlap.decoration-text`; decoration that encloses the text (a panel, a frame) is not reported, and `layer-intent allow_overlap` accepts a deliberate pair. Text on a shape or image painted beneath it is not an `overlap.text-object` when the other layer's box holds the text's box, or when at least 98% of the text's glyph pixels land on that layer's pixels (a centred label whose wide text box overhangs its button); text that crosses only part of a button, or that a layer painted above it covers, is still reported.

Layers marked `role: background`, and non-text layers whose drawn geometry covers the canvas, are background and skipped; `checked` reports `layers_checked` and `layers_total`. Shapes and gradients that run past two or more canvas edges (a hill, a glow) are intentional bleed and report as informational.

Safe area defaults to the canvas's own `safe` (a pixel inset, or a `{left, top, right, bottom}` object, measured from the trim edge); pass `safe_area` to override. The thumbnail legibility test (320 px wide; `thumbnail_width: null` or `--thumbnail-width off` disables it) is a warning only for social, icon and app-store sizes and informational elsewhere; a chart's small labels are one finding per chart (with `chart`), and on other pieces more than three small text layers are one note listing them all.

Display text (24 px or larger) in a `text-layout` box whose wrapped paragraph ends in a line under 20% of its longest line, or in one word under half of it when the paragraph has more words than lines, is a `legibility` review finding with `code: runt` (`line` is the last line, `share` its width as a fraction of the longest): set `text-layout` `wrap` to `pretty` (`balance` for a heading), widen the box, add an explicit line break or run `fit-text`. Lines you break yourself are not judged.

`color_vision` also compares chart series colors and flags pairs that merge under a color-vision deficiency; mark a chart whose series also differ by labels or patterns with `layer-intent color_vision_safe`. The default `composition` family adds review findings for dead bands, margin drift, uneven rhythm, crowding under a rule or heading, clumped scatters, flat hierarchy, a single weight, no focal point and an unused accent, each with its `code`, `region`, measured values and threshold; `check --checks composition` runs it alone ([composition](../guides/layout/guides.md#composition)).

`placeholders` (on by default) finds leftover template copy in what text draws, after variables: lorem ipsum, `TODO`/`TBD`/`XXX` markers, slot text such as "Your headline here" or "Headline goes here", and a `${name}` merge field that drew literally are `fix` warnings; a variable nothing defines is an error naming it (and, in production, the variant and input `row`); `{{name}}`, `[[name]]` or `<<name>>` from another tool's template is only `review`. `$${name}`, the escape for a literal `${name}`, is never flagged. brand.json `placeholders` adds regular expressions; mark intended text that only looks like a placeholder with `layer-intent LAYER --literal-text`. Unfilled layout and template slots stay the `blanks` check's. `check --artboards all --pages all --comps light dark` (or lists of names) checks every combination in one report: each finding names its `variant` and its message starts with it (`[artboard story] …`), `variants` gives each one's status and `coverage` what was checked; pages hidden from export need `--include-hidden`. With deck checks `--pages` keeps its meaning (the pages the deck review covers).

`connected` (opt-in: `check --checks connected`, `--connect-tolerance 2`) looks inside every visible group that is one object (a mascot, a character, a prop built from shapes; charts, drawings, repeats and speech bubbles are skipped). The drawn ink of each direct part is compared on the canvas: parts whose ink touches or overlaps within the tolerance form one piece, the piece with the most ink is the main body, and every other part is a `connected` warning with its `gap` in pixels and its `group`. Text parts are ignored. A document with a timeline is checked at its poster, middle and last frames (`frame` names the one where a part first comes loose). Mark a part that floats on purpose (a spark, a thrown ball), or a group whose parts are separate by design, with `layer-intent detached_ok`. To look at one object alone, preview it with `isolate` (`vixl_render(isolate=["cat"])`). When the `object` check runs, `connected` leaves declared objects to it, so a gap is reported once.

`object` (on by default when the page declares an [object](../guides/shapes/objects.md#the-object-check); `check --checks object`) measures each object and sub-object against its kind: required parts missing or miscounted (`object.part-missing`, `object.part-count`, both `fix`), paired parts without a side or twice on one side, and part names the kind does not list (`review`); a `fix` gap between parts the kind says touch (`object.gap`, with `gap`, `pair`, both paths and, on a timeline, the `frame`; `--connect-tolerance` applies); proportions outside the kind's range (`object.proportion`, silenced by `stylized: true` or `proportions: ignore` on the object); mirrored pairs that differ in size by more than 15% or sit on one side of the part they attach to (`object.symmetry-size`, `object.symmetry-side`); and parts stacked against the kind's back-to-front layering where they overlap (`object.layering`). With an [outline policy](../guides/shapes/objects.md#outline-policy) applied (`vixl object outline GROUP`) it also reports part strokes showing inside the silhouette (`object.outline-seam`), part outlines more than 25% apart in width under `outline: parts` (`object.outline-weight`) and an outline drawn for other geometry or whose layer is gone (`object.outline-stale`, `fix`). Every finding has `layer_ids`, `box`, `measured`, `object`, `kind` and a `hint` naming the kind's build placement. A standard character without its own object record is left to `character`.

`cost` (opt-in: `check --checks cost`) draws the document once with empty caches and times every layer (a group's time excludes its children). A layer that takes over 10× the median layer and at least 50 ms is a `cost` warning with action `review`, its `ms`, the `median_ms`, the slowest `stage` (`draw`, `effects`, `transform`) and `causes` read from its fields (the largest blur radius, other effects, paint stroke and point counts, soft style blurs, very long text, repeated copies, a very large box). It does not fail a check; it says which layer to simplify or rasterize when renders, previews and timeline frames are slow.

`accessibility` (opt-in: `check --checks accessibility`) adds `contrast` and `color_vision` to its own findings: the
document language (fix), meaningful images, frames, links and charts without alt text (fix), small text (review),
charts told apart by colour alone (review) and text whose export order jumps against its visual order (review). See
[accessibility](../guides/output/accessibility.md). Declared [objects](../guides/shapes/objects.md) are inspected with `vixl inspect --object NAME`
(`*` lists them all), exported alone with `vixl export dog.svg --isolate dog [--padding 8]` (a `.vixl` output
writes a portable object) and listed by `vixl manifest`. `vixl object plan KIND [--height N] [--x X --y Y | --box X
Y W H] [--name N] [--with KIND] [--seed N] [--illustration house|plain] [--apply]` scaffolds an object of a kind as
named placeholder parts (the `object-plan` workflow; without a document it prints the batch; in a document with a house
style it ends with the flat vector illustration finish unless `--illustration plain`), and `vixl object outline GROUP
[--outline silhouette|parts|none|inherit] [--interior hide|thin|show] [--outline-color C] [--outline-width W]
[--outline-lines JSON]` and `vixl object outline-remove GROUP` apply and remove its outline policy.

Saved SVG exports report `svg.vector_only` and `svg.raster_fallbacks` in the CLI result so embedded bitmaps are visible without opening the SVG metadata. Use `export logo.svg --svg-policy strict` to reject all embedded raster content. Exporting to `-` still writes only SVG bytes. Supported grouped shapes and outlined text remain vectors; unsupported appearances may rasterize in the default appearance policy. Every SVG export also carries its document in `<metadata id="vixl-document">` (fonts named, not stored), so `vixl import FILE.svg` restores the editable layers ([exporting](../guides/output/exporting.md#svg-round-trip)).

## Finish, styles and the guide

```bash
vixl guide                               # start-here recipe and every kind of work
vixl guide a mascot for a coffee brand   # approach, operations, layouts, looks, styles, example
vixl guide operations                    # every operation by purpose, with summaries
vixl looks                               # the finishing looks
vixl house [show PURPOSE]                # the house style: craft, tiers, levels; or one purpose's profile
vixl roll --for slides --variety high --lock tier=bold  # a tiered, purpose-weighted direction
vixl look LAYER glow [--color C] [--amount 0-1] [--remove]
vixl radial-repeat LAYER --count 12 [--cx 50%] [--cy 50%] [--sweep 360] [--start-angle D] [--mirror] [--no-group] [--name N]
vixl layer-intent LAYER --allow-crop     # a deliberate edge crop: checks report it as informational
vixl layer-intent LAYER --waive contrast # accept this layer's contrast findings (listed as waived)
vixl waiver contrast --target LAYER --reason "watermark, approved" --expires 2030-12-31
vixl waiver fonts --reason "proofing font for now"     # document-wide; --remove deletes; --rule ID for a suite rule
vixl check --profile final               # draft | review | final | a .vixl-checks.json profile; --no-waivers
vixl layer-intent LAYER [--role content|decoration|background|title] [--allow-overlap L…] [--tags T…]
                        [--[no-]detached-ok] [--[no-]color-vision-safe] [--[no-]literal-text]   # compact inspect shows what is set
                        [--priority required|optional|decorative] [--focal X Y]   # what adapt-layout may hide; the photo point it keeps
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
    [--variety low|medium|high|fixed] [--house-style on|off] [--background COLOR] [--no-fonts] [--dpi N]
    [--landscape|--portrait] [--bleed [AMOUNT]] -o FILE [--overwrite]   # e.g. new letter --bleed -o a.vixl; no size: the
    # purpose's size, else 1080x1080; --house-style off: no rolled direction (white canvas, neutral layout defaults)
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
vixl color scale COLOR | color scale A B [C…] [--count 5] [--space oklab] | color mix A B [--amount 0.5] [--space oklab] | color contrast FG BG | color names QUERY
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

vixl easings | timeline | timeline set [--duration T] [--fps N] [--loop N] [--loop-mode seamless|off] [--close] [--clear]
vixl keyframe LAYER|canvas PROPERTY TIME VALUE [--easing E] | keyframe-remove LAYER [--property P] [--time T]
vixl animate LAYER PROPERTY --to V [--from V] [--start T] [--end T | --duration T] [--easing E] [--intent entrance|exit|loop|emphasis]
vixl animate-preset LAYER|canvas PRESET [--start T] [--duration T] [--easing E] [--amount N] [--distance N] [--to C] [--no-fade]
vixl text-animate TEXT PRESET [--unit char|word|line] [--start T] [--duration T] [--stagger T|N%] [--easing E]
    [--direction forward|reverse|center|edges|random] [--seed N] [--mode in|out|in-out] [--distance N] [--amount N]
    [--rotate DEG] [--from C] [--repeat] [--remove] [--no-extend]
vixl marker NAME TIME | marker NAME --delete
vixl render --time T --out FILE | timeline-sheet --out FILE [--count 8] [--columns N] [--times T…]
vixl export-timeline --out FILE.gif|.png|.webp|.zip|.mp4|.webm [--format sheet] [--fps N] [--scale F]
    [--start T] [--end T] [--background C] [--columns N] [--quality N] [--colors N] [--dither auto|none|ordered|floyd]
    [--max-bytes N] [--target-bytes N] [--preset chat|web|email] [--poster T] [--overwrite]
```

Times are milliseconds or `1.5s`, `250ms`, `50%` or a marker name. Details: [sizes and layouts](../guides/layout/sizes-and-layouts.md), [color and print](../guides/finishing/color-and-print.md), [brushes and animation](../guides/motion/brushes-and-animation.md).

## Linked documents and print merge (0.19)

```bash
vixl link FILE.vixl [--name N] [--x X] [--y Y] [--width W] [--height H] [--fit fill|fit|stretch]
    [--position top-left|0.5,0.5] [--crop X,Y,W,H] [--artboard NAME] [--source-page P] [--set NAME=VALUE]…
    [--corner-pin '[[x,y],[x,y],[x,y],[x,y]]']
vixl link-set LAYER [--source F] [--fit …] [--position …] [--crop …] [--artboard …] [--source-page …]
    [--set NAME=VALUE]… [--corner-pin …] [--clear artboard|source_page|variables|crop|corner_pin]…
vixl link-refresh [LAYER] | link-embed LAYER | links          # links: every link, ok / stale / missing / cycle

vixl merge [TEMPLATE.vixl] --data rows.csv --out sheets.pdf [--sheet-document sheets.vixl]
    [--size letter] [--cols 2] [--rows 3] [--gutter 0.125] [--margin 0.5] [--bleed template|0.125]
    [--no-crop-marks] [--registration] [--slug TEXT] [--copies N] [--set NAME=VALUE]…
    [--unknown warn|error|ignore] [--defaults error|warn|ignore] [--check design]
    [--skip-invalid] [--dry-run] [--replace]
vixl merge --rerun sheets.vixl [--data new.csv] [--out new.pdf]
```

[Linked documents](../guides/output/linked-documents.md) render another `.vixl` live (`--allow-linked` for sources outside the current
folder); [imposition](../guides/output/imposition.md) lays CSV rows out on print sheets with crop marks, as a vector-text PDF and an editable
sheet of links.

## Catalog export for host applications

`vixl catalog export --out catalog.json` writes one JSON bundle of Vixl's design catalogs for an application that embeds or mirrors Vixl (Python: `vixl.catalog.export_catalog()` returns it as a dict, `write_catalog(path)` writes it). `--json` without `--out` prints it; `--section NAME` (repeatable) exports only some sections; an existing `--out` file is refused unless `--overwrite` is given. `vixl catalog schema [--out FILE]` gives the [JSON Schema](../../src/vixl/data/catalog.schema.json) the bundle follows. Every GitHub release attaches both as `vixl-catalog.json` and `vixl-catalog.schema.json`. See [the catalog bundle](../guides/layout/agent-resources.md#catalog-bundle-for-host-applications) for what it holds.

```bash
vixl catalog export --out catalog.json --section sizes --section checks
```

## Large batches and focused schemas

`vixl apply operations.json` accepts JSON input up to 64 MiB; the same bound applies to inline JSON and stdin. Operation-count and document resource limits still apply, and a failing batch is atomic. `vixl --json schema text shape` returns only the requested operation schemas (a misspelt name suggests the closest ones). Bare `schema` lists every operation by purpose with a one-line summary (about 16 KB); `vixl schema --all` returns the full JSON Schema (about 900 KB); `vixl schema document` returns the JSON Schema of a `.vixl` file's `project.json` ([file format](file-format.md)).

Workflow request arguments accept a JSON file, `-` for stdin, or an inline JSON object. CLI workspace resources resolve from the current directory. Add `.vixl-session.json` to your repository's `.gitignore`; it records the local current-document session and is not a project source file. Shared MCP servers require an explicit document when closing a session with several documents open.

`vixl -p master.vixl adapt-layout --sizes instagram-post story --directory out --formats png` exports copies at several sizes. It does not overwrite the master. Each copy reports `recomposed` and `reason`, and the document's attached check suites run on every copy (`suites` and `outcome` per copy; `--no-suites` skips them). A document built with `layout-apply` and not edited since is rebuilt from its stored layout at each size by default (earlier releases needed `--recompose`); it rebuilds the generated layers and their IDs. After an edit, the copies are re-laid out proportionally unless `--options '{"recompose": true}'` (single size: `vixl adapt-layout --size story --recompose`) asks for the rebuild anyway, replacing those edits; `--no-recompose` (`{"recompose": false}`) always adapts proportionally. Proportional adaptation is not a replacement for recomposing long copy into a radically different aspect ratio: `--options '{"arrangements": ["stack-vertical", "side-by-side", "hero-top"]}'` re-places the content in each candidate arrangement, keeps the one the composition, legibility, bounds and overlap checks score best and reports its `outcome` (`needs_review` when none passes).


## Reviewing editable projects in Git

Run `vixl unpack design.vixl design-source` to create a readable `project.json` with separate content-addressed assets. Commit that folder alongside application code. Edit a text string or layer property in `project.json`, review the ordinary Git diff, then run `vixl pack design-source reviewed.vixl`. Python exposes the same functions in `vixl.project_folder`.

The source format stores only the current state, so undo history, branches and session timestamps do not bury copy edits in noise. Keep the original `.vixl` when history matters. Stable key order, indentation, asset hashes and ZIP timestamps make unchanged serialization deterministic. Packing checks file bounds, checksums, references and the full document schema and refuses missing assets, unsafe paths and symlinks. Linked external files remain external; links are rebased on conversion, so commit the linked source documents alongside the design as well. Packing never replays remote inference.

## Emoji (0.24)

```bash
vixl emoji list [--query TEXT] [--group G] [--offset N] [--limit N]
vixl emoji get EMOJI [--out FILE] [--format vixl|svg|png] [--overwrite]   # inspect, or extract the editable source
vixl emoji template [blank|face|symbol|sheet] --out FILE [--destination images|discord|slack] [--overwrite]
vixl emoji destinations | emoji requirements [--destination D] [--emojis E…]
vixl emoji export [--destination images|discord|slack] [--emojis E…] --out FILE [--size N] [--no-sources] [--overwrite]
vixl -p doc.vixl emoji settings [--mode vixl|font]          # bundled art (default) or the font first
vixl -p doc.vixl emoji replace EMOJI|:custom_name: SOURCE [--name N] [--license L]
vixl -p doc.vixl emoji install PACK | emoji reset [--emoji EMOJI]
```

`vixl emoji` takes `--workspace DIR` (default: the current directory). The document edits are the operations
`emoji-mode`, `emoji-set` and `emoji-reset`, and every subcommand is also an `emoji-*` workflow action. See
[emojis](../guides/text/emojis.md).

## Local desktop capture

`vixl workflow screen-capture --request '{"output":"screen.png"}' --workspace .` captures the interactive local desktop explicitly. Optional `bbox` is `[left, top, right, bottom]`; negative monitor coordinates are allowed. On Windows, `window` is an HWND (for example a process's MainWindowHandle) and `all_screens` includes other monitors. Use `bbox` or `window`, not both. PNG output refuses replacement unless `overwrite: true`. MCP desktop capture is disabled by default. Start the server with `--allow-screen-capture` or `VIXL_ALLOW_SCREEN_CAPTURE=1` to enable it for that server; this grants connected agents access to the interactive desktop. Capture output paths are relative to the workspace. Headless sessions or denied OS screen permissions return an actionable capture error; normal rendering never captures the desktop.

## Servers

`vixl mcp --workspace DIR` serves the seven MCP tools over stdio (`--http` for Streamable HTTP at `/mcp`, with `--host`, `--port` and `--token-env`). `vixl mcp --tools ai` serves the provider-backed `vixl_ai_*` tools and `vixl_models_list` as a second server (`--planner` adds `vixl_ai_plan`). `--require-document` (or `VIXL_REQUIRE_DOCUMENT=1`) makes `document=` mandatory on every document tool, and `--allow-screen-capture` enables desktop capture. `vixl serve` runs the REST API and `vixl view` the live viewer; `serve`, `view` and `mcp` share the per-call limits `--call-timeout`, `--call-hard-timeout`, `--max-megapixels`, `--max-pages` and `--max-concurrent` (with defaults when other machines can reach the server; `--no-call-limits` drops them). See [MCP tool surface](mcp-toolsets.md) and [interfaces](interfaces.md#mcp).

`vixl host --root DIR` serves documents in many workspaces to a host application such as AI Server Studio: a bearer token is always required (`VIXL_HOST_TOKEN`, `--token-env` or `--token-file`), `--offline` turns network access off, `--bind ADDR` and `--port` (default 8767) set the address, and it takes the same per-call limit flags. `vixl host --schema` prints its API contract. See [hosting Vixl](interfaces.md#hosting-vixl).

## Output destinations and help

Use `--out FILE` or `-o FILE` for render, export, save, pack/unpack, batch, comparisons, timeline/animation
exports and other commands with a primary output option. `batch --output DIR` remains accepted and reports
its canonical spelling under `normalized`; positional destinations for export, save and pack/unpack remain
accepted. Supplying both a positional destination and `--out` is an error.

`vixl --help` lists command groups. Use `vixl COMMAND --help` for options, `vixl commands --json` for the
machine-readable inventory, or `vixl help --full` for the detailed overview.
