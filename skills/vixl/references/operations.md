# Canonical operations reference

Vixl is headless and designed for autonomous AI agents; humans can use the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

Every edit in Vixl is a JSON object with a `type`. Send a single object, an array, or
`{"operations": [...]}` to: MCP `vixl_operations_apply(operations=[...])`, CLI `vixl apply FILE|-`,
REST `POST /operations`, or Python `Project.apply(...)`. Common alternative spellings (`rect`,
`circle`, `font_size`, `fill`/`color`, camelCase keys, opacity `"70%"`, blur `radius`) are normalized
and reported under `normalized`; other unknown fields, invalid values, unknown types, malformed sizes and
non-finite numbers are rejected with the operation index, field and suggestions. The whole batch is
validated first and every invalid operation is reported in one error (`errors: [{operation_index, field,
message, suggestions}]`; top-level fields = the first). Max 10 000 operations per batch; the batch is atomic.

**Opacity is 0–1 everywhere** (`opacity`, creation `opacity`, `layer-style` settings, keyframe/animate
values of `opacity`): `"70%"` is read as 0.7; a bare `70` is an error suggesting `0.7` or `"70%"`.

**`target` / `targets`.** Every operation on existing layers takes `target` (one) or `targets` (a list).
Per-layer operations (`opacity`, `move`, `rotate`, `hide`, `layer-intent`, `layer-style`, effects, `shape`/`text`
edits …) apply to each listed layer within the batch; joint ones (`group`, `align`, `distribute`, `pathfinder`
…) treat the list together; single-layer ones (`rename` …) accept a one-item list only. The full table is in
docs/operations.md (`x-targets` in the schema).

Conventions used below: **bold** = required. `target` is a layer name or `lyr_…` ID and, when
omitted, defaults to the active layer. Colors accept CSS names, `#rgb`, `#rrggbb`, `#rrggbbaa`,
`rgb()`/`rgba()` (alpha 0–1), `hsl()`, `transparent`, `@swatch`, and `${variable}`. Geometry: `x`/`y`
accept pixels, `"center"` or `"N%"`; `width`/`height` accept pixels or `"N%"` (of the canvas, or of
the parent group) on creation ops, `move`, `resize`, `select` and `text-layout`.

The authoritative schema is always `vixl schema` / `GET /schema` / `vixl://operations`.

## Creating layers

| type | fields | notes |
| --- | --- | --- |
| `add` | **`path`** *or* **`asset`**, `name`, `x`, `y`, `linked` | `path` is CLI/Python only (MCP: use `vixl_import_image`). `asset` = an embedded ID like `assets/<sha256>.png`. `linked` keeps an external reference (needs `--allow-linked`). |
| `solid` | `name`, `width`, `height`, `color`, `x`, `y`, `target` | Defaults to canvas size. With `target`, edits that solid in place. |
| `gradient` | `name`, `width`, `height`, `start`, `end`, `direction`, `stops`, `angle`, `x`, `y`, `target` | `direction`: `vertical` (default), `horizontal`, `angled` (`angle` 0°=left→right, 90°=top→bottom), `radial`. `stops`: 2–64 `{"offset":0..1,"color":…}` strictly increasing. |
| `text` | **`text`** *or* `target`, `name`, `size`, `hide_if_empty`, `color`, `align` (`left`/`center`/`right`), `spacing` (line spacing px), `font`, `x`, `y`, `baseline_y` | `x`/`y` may be `"center"` or `"N%"`. `baseline_y` (instead of `y`) puts the first line's baseline at that y. `font`: a registered name, `heading`/`body` (follows the document typography), or a file path (CLI/Python only); default font DejaVu Sans is the proofing fallback. Multiline via `\n`. With `target`, edits that text layer in place (like `text-set`; `text` is then optional). |
| `shape` | **`shape`** *or* `target`, `name`, `width`, `height`, `x`, `y`, `fill`, `stroke`, `stroke_width`, `line_cap`, `trim_start`, `trim_end`, `radius`, `sides`, `inner_radius`, `start_angle`, `end_angle`, `opacity`, `rotation`, `space` | `shape`: `rectangle`, `rounded-rectangle` (`radius`), `ellipse`, `polygon` (`sides`), `star` (`sides`, `inner_radius` 0.01–1), `arc`, `line`. `arc` is a pie wedge or donut segment of the ellipse filling the box: angles in degrees, 0 = 3 o'clock, clockwise (-90 = 12 o'clock), `inner_radius` 0–0.99 of the outer radius (0 = wedge, 0.6 = donut), no angles = full disc/ring. Wedges sharing a box and differing in angles make a pie/donut chart. Procedural, redrawn crisply on resize. `trim_start`/`trim_end` (0–100 %) draw only that part of the stroke, and are animatable (draw-on); `line_cap`: `butt`/`round`/`square`. `pen` takes the same three. Fill: a closed shape with no `fill` is white; an open one (`line`, or a `path` with no closing `Z`) that has a `stroke` and no `fill` is unfilled in every output (render, SVG, PDF, PPTX). `fill: "none"` means `transparent`. `path`: literal local pixels from x/y; without width/height the box reaches the path's farthest point (never the canvas); negative coordinates draw outside the box. `opacity` (0–1) and `rotation` (degrees) apply at creation or edit; with `target`, `space: "canvas"` reads x/y as document coordinates for a grouped layer. |
| `frame` | `name`, `width`, `height`, `x`, `y`, `path` *or* `asset`, `fit` (`fill`/`fit`) | Image placed in a fixed box; `fill` crops, `fit` letterboxes. |
| `pixel-art` | `name`, `width`, `height`, `x`, `y`, `palette`, `background`, **or** `rows` | Character-grid sprite (1–256 per side). See *Pixel art* below. |
| `adjustment` | **`effects`** (list of effect objects), `name` | Adjustment layer: filters the composited stack *below it* in its parent. |
| `symbol-instance` | **`symbol`**, `name`, `x`, `y`, `width`, `height` | Live copy of a symbol master. |
| `duplicate` | `target`, `name` | |
| `link` | **`source`** (workspace `.vixl`; or `target` to edit one), `name`, `x`, `y`, `width`, `height`, `fit` (`fill`/`fit`/`stretch`), `position`, `crop` `{x,y,width,height}`, `artboard`, `source_page`, `variables` | Another document, drawn live: edits to the source show at the next render. Sources stay in the workspace; cycles and depth > 4 are errors. `link` with a `target` edits it (`null` clears), `link-refresh` records the seen revision (see `links` in `vixl_workflow`), `link-embed` freezes it into an image. Sources resolve beside the document first, then in the workspace (a source in the document's folder is stored relative to it, so the folder can be copied). |
| `qr` | **`data`** (may use `${var}`), `error` (`L`/`M`/`Q`/`H`), `quiet` (modules, default 4), `module` (px) or `size`, `color`, `background` (`none` = no group), `name`, `x`, `y`; `target` edits | Vector QR code: one merged path layer (`NAME code`) grouped with `NAME background`. Re-encoded at render for merges. `check codes`: module size at dpi, contrast, clear quiet zone. See `docs/codes.md`. |
| `barcode` | **`data`**, `symbology` (`code128`/`ean13`), `module` or `width`, `height`, `quiet`, `color`, `background`, `name`, `x`, `y`; `target` edits | Code 128 (printable ASCII) or EAN-13 (12 digits, or 13 with a valid check digit) as vector bars. |
| `links-relink` | **`from`**, **`to`** | Rewrites every link source starting with `from` (a file or folder, whole segments) on every page; the new files must exist. |

**Empty fields.** Text with `hide_if_empty: true` (also on `text-set`) is not drawn, checked or exported while its `${variable}` text is empty or blank, and takes no space in a stack. Put the layers of a block in a `stack` (`{"type":"stack","name":"names","targets":["first","last","company"],"gap":20,"align":"center","justify":"center","width":1000,"height":400}`): hidden and empty members take no space and the rest re-flow and stay centred, at render/export time too (CSV rows, `variables`). `inspect` shows `collapsed: true` on such layers. Overlapping artwork goes in a sub-group that is the stack member.

**Changing a layer you already made.** `solid`, `gradient`, `shape` and `text` take `target`: with the name or ID of an existing layer of the same kind they edit it in place (same ID, order, effects, constraints; only the fields you pass change) instead of adding a layer. Recolour a bar with `{"type":"shape","target":"bar","fill":"#6b3f69"}`; change its height with `{"type":"shape","target":"bar","height":120}`; recolour a sky with `{"type":"gradient","target":"sky","start":"#01030a","end":"#3a3058"}` (on a multi-stop gradient, `start`/`end` set the first and last stop; `stops` replaces them); resize text with `{"type":"text","target":"headline","size":190}`. `name` renames and `x`/`y` move. A target of a different kind (or `target` on `add`, `frame`, `adjustment`, `symbol-instance`) is an error that names the operation to use — never a silent new layer. CLI: `vixl shape --target bar --fill '#6b3f69'`.

## Layer management

| type | fields |
| --- | --- |
| `rename` | `target`, **`name`** |
| `remove`, `hide`, `show` | `target` |
| `raise`, `lower`, `top`, `bottom` | `target` |
| `reorder` | `target`, `above` *or* `below` (layer) |
| `select-layer` | `target` — makes it the active layer |
| `rasterize` | `target` — bakes text/shape/etc. to pixels (remove styles/clip first) |
| `group` | **`name`**, **`targets`** (list), `above`/`below` (a layer: the new group's z-slot; default its topmost member's) — children keep local coordinates; nest ≤16. Edit a member by canvas coordinates with `space: "canvas"` on `move` or `shape`/`text` with `target`. |
| `ungroup` | `target` |
| `clip` | `target`, `base` (sibling) — multiplies target alpha by base alpha; `release: true` removes |

## Transform and appearance

| type | fields | notes |
| --- | --- | --- |
| `move` | `target`, `x`, `y`, `relative`, `baseline_y` | Absolute move clears constraints; `relative: true` adds offsets. `baseline_y` (text only) places the first baseline. |
| `resize` | `target`, `width`, `height`, `keep_aspect` | One dimension changes only that side of shapes, text, groups and solids (reported under `normalized`) but scales imported images (raster) proportionally; `keep_aspect: true` scales the other side proportionally on any layer, `false` changes only the given side; two dimensions stretch. Turns off text auto-size. |
| `scale` | `target`, **`value`** or `x`/`y` | Factor (0.8 = 80 %), 0.001–100. Negative mirrors: `value` flips both axes, `x: -1` flips horizontally (like `flip`) and keeps the size. |
| `rotate` | `target`, **`value`** | Degrees clockwise about the layer's pivot (default: center); bounds expand. |
| `pivot` | `target`, **`value`** (`[x, y]` fractions of the unrotated box, or `top-left`…`bottom-right`/`center`), `units` (`fraction`/`px`/`canvas` — a document point, through parent groups), or `clear` | Point that rotation and scale turn about; stays fixed on the canvas (stills, timeline, SVG). Keeps the drawn pose. A pivoted layer's stored `x`/`y` is its unrotated box. |
| `flip` | `target`, **`direction`** | `horizontal` / `vertical`. |
| `crop` | `target`, **`x`, `y`, `width`, `height`** | In the original embedded raster's coordinates. |
| `opacity` | `target`/`targets`, **`value`** | 0–1, or `"N%"`; a bare number above 1 is an error. |
| `blend` | `target`, **`value`** | `normal`, `multiply`, `screen`, `overlay`, `darken`, `lighten`, `difference`, `add`, `subtract`. |
| `text-set` | `target`, `text`, `size`, `color`, `align`, `spacing`, `stroke_width`, `stroke_color`, `font`, `baseline_y` | Edit a whole text layer (content, colour, size, font); keeps a `text-layout` box and, on rich text, the formatting that still applies (`warnings` lists what was dropped). Partial styling is `text-style`. `font`: registered name, `heading`/`body` role, or a file (CLI/Python). |
| `text-layout` | `target`, `width`, `height`, `fit`, `warp`, `amount`, `path` | Box wrapping; `fit: true` shrinks font to fit; `warp`: `none`/`arc`/`flag`/`bulge` with `amount` −1..1; `path`: polyline `[[x,y],…]` in local px. Replaces previous layout. |
| `layer-style` | `target`, **`name`**, `settings`, `remove` | See *Layer styles*. |
| `replace-contents` | `target`, `path` *or* `asset` *or* `variable`, `fit` | Swap image, keep ID/box/effects/mask/styles. |

## Layout

| type | fields | notes |
| --- | --- | --- |
| `align` | **`alignment`**, `target`, `targets`, `margin`, `relative_to` | `alignment`: `center`, `center-x`, `center-y`, `top`, `bottom`, `left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, `baseline` (text only: first baselines match the first target's or a `relative_to` text layer's). `relative_to`: `canvas` (default for one target), `selection` (default for several; union bounds) or a sibling. Bakes positions, clears constraints. |
| `distribute` | **`targets`** (≥3 siblings), **`axis`** (`horizontal`/`vertical`), `gap` | Without `gap`: equal edge-to-edge spacing between outer items. |
| `constrain` | `target`, **`constraints`** | e.g. `{"center-x":"canvas.center-x","top":"logo.bottom+40"}`. Keys `left/right/center-x` (one per axis) and `top/bottom/center-y`. Values: `canvas`, layer name/ID, or `guide:NAME`, then `.edge` and optional `+N`/`-N`. Cycles rejected. Siblings only inside groups. |
| `unconstrain` | `target` | |
| `canvas` | `width`, `height`, `background`, `preset` | Presets: `instagram-square`/`instagram-post` 1080², `story` 1080×1920, `youtube-thumbnail` 1280×720, `discord` 512². Constraints reflow. |
| `guide` | **`name`**, **`axis`** (`x`/`y`), **`position`** | Named, never rendered; use in constraints as `guide:NAME.left+8`. |
| `grid` | **`name`**, `columns`, `rows`, `margin`, `gutter` | Generates guides `NAME-x1-start`, `NAME-x1-end`, `NAME-y1-start`, … |
| `artboard` | **`name`**, `preset` *or* `width`/`height`, `x`, `y`, `background`, `variables`, `targets`, `delete` | Named alternate canvas sizes in one document. `targets` = top-level layer IDs shown (absent = all). |
| `edit-layers` | **`where`**, **`do`**, `dry_run`, `expect` | Bulk edit: runs the operation(s) in `do` on every layer matching `where` (`role`, `name` glob, `name_regex`, `kind`, `shape`, `tag`, `group`, `text_contains`, `text_regex`, `id`, `visible`, `page`, `not`; keys AND together, values may be lists). Result `edit_layers: [{matched, layers}]`; `expect` fails unless exactly that many match; no match warns. `do` must not set `target` or create layers. Tag layers with `layer-intent` `tags`. |
| `adapt-layout` | `size` *or* `width`+`height`, `scale` (`fit`/`fill`/`width`/`height`/number), `anchors`, `where`, `text` (`scale`/`keep`), `report`; or with `targets`: `targets`, `width`, `height`, `margin`, `gap` | Without `targets`: resize the canvas and re-lay out every layer proportionally (edge margins kept, middle content keeps its relative place, backgrounds stretch, photos cover, text scales); result `adapt_layout` lists where each layer moved. With `targets`: vertical reflow. For several sizes at once use `vixl_adapt_layout`. |

## Selections and masks

| type | fields | notes |
| --- | --- | --- |
| `select` | **`shape`**, `x`, `y`, `width`, `height`, `color`, `tolerance`, `target`, `asset`, `mode`, `feather` | `shape`: `rect`, `ellipse` (x,y,w,h), `color` (`color`, `tolerance`), `alpha` (`target` layer), `asset` (grayscale mask asset), `all`, `none`, `invert`. `mode`: `replace`/`add`/`subtract`/`intersect`. Canvas coordinates. |
| `mask` | `target`, **`action`**, `path` | `action`: `create` (white), `from-selection`, `import` (`path`; CLI/Python only), `invert`, `enable`, `disable`, `delete`. White = visible. Masks follow the layer's transform. |

New effects are limited to the selection active **when they are added**. Select `none` first for whole-layer effects.

## Effects (non-destructive filter stack)

Add with `{"type":"effect","name":NAME,...}` or the shorthand `{"type":NAME,...}`. Field `amount`
(alias `value`) unless noted.

| name | meaning of `amount` |
| --- | --- |
| `brightness`, `contrast`, `saturation` | % relative to neutral (−100…; 0 = none) |
| `hue` | degrees |
| `exposure` | stops (−32…32) |
| `gamma` | > 0 (1 = none) |
| `temperature` | warm(+)/cool(−) white-point shift, −100…100 (100 ≈ 6500 K → 4400 K; 10–30 subtle); multiplicative, black stays black |
| `tint` | magenta(+)/green(−), −100…100, matched to temperature |
| `white-balance` | strength 0–100 (default 100) of `gains` `[r,g,b]` **or** `neutral` (a color to turn grey) |
| `shadows`, `highlights` | % lift(+)/cut(−) |
| `blur`, `gaussian-blur` | **radius in px via `amount`** (0–1000). `radius` is normalized to `amount` and reported |
| `sharpen` | factor (1 = none, 0–100) |
| `denoise` | edge-preserving noise reduction (non-local means): `luminance` and `chroma` strength 0–100 (default 50 each; `amount` sets both), `search` window radius 1–10 px (default 5 = 72 positions tried, roughly 1 s per megapixel; time grows with its square). Strength is relative to the grain measured in the image |
| `grayscale`, `invert` | — |
| `posterize` | bits 1–8 |
| `threshold` | 0–255 |
| `noise`, `grain` | std-dev 0–1, plus `seed` (default 0) |
| `vignette` | `strength` 0–1 (or `amount`), `radius` 0–1.4 (default 0.7) |
| `levels` | `black` 0–254, `white` 1–255 |
| `curves` | `points`: `[[0,0],[128,160],[255,255]]` |
| `auto-tone`, `auto-color`, `auto-contrast` | — (percentile stretch) |

Effects run in stack order on the layer's own frame (before rotation/flip/skew; selections stay in canvas space).
Manage the stack (effect = stable `fx_…` ID, 1-based index, **or** its name when used once):

| type | fields |
| --- | --- |
| `effect-set` | `target`, **`effect`**, `amount`/`value`, `seed`, `radius`, `strength`, `black`, `white`, `points`, `luminance`, `chroma`, `search` |
| `effect-enable` / `effect-disable` / `effect-remove` | `target`, **`effect`** |
| `effect-move` | `target`, **`effect`**, one of `to` (1-based position, `top`, `bottom`), `before`, `after` (another effect) |
| `preset-save` | **`name`**, `target` — saves the layer's effect stack |
| `preset-apply` | **`name`**, `target`, `overrides` |
| `lut` | **`name`**, **`size`** (2–33), **`values`** (`size³` RGB triples 0–1, red fastest) |
| `lookup` | `target`, **`name`** (LUT), `amount` (0–1 mix) — adds a `lookup` entry to the effect stack (toggle/move/remove like any effect; `{"type":"effect","name":"lookup","lut":…}` also works) |

Plugin filters (enabled with `--plugins`) are also addressed by `name`.

## Layer styles (`layer-style`)

`{"type":"layer-style","target":"title","name":"drop-shadow","settings":{...}}`; `remove: true`
deletes it. One style per kind; all accept `enabled` (bool) and `opacity` (0–1).

| name | settings |
| --- | --- |
| `drop-shadow` | `color`, `dx`, `dy` (±4096), `blur` (0–100) |
| `outer-glow` | `color`, `blur` |
| `stroke` | `color`, `width` (0–100) — outer stroke |
| `color-overlay` | `color` |
| `gradient-overlay` | `start`, `end`, `stops`, `direction`, `angle` (same as `gradient`) |

## Text styles, swatches, variables, comps, symbols

| type | fields | notes |
| --- | --- | --- |
| `swatch` | **`name`**, **`color`** | Use as `@name`; redefining updates every use. |
| `style-define` | **`name`**, **`settings`**, `kind` | `character`: `size`, `color`, `stroke_width`, `stroke_color` (ints). `paragraph`: `align`, `spacing`. |
| `style-apply` | **`name`**, `target`, `kind` | Linked: redefining the style updates layers. |
| `variable` | **`name`**, `value`, or `delete: true` | `${name}` in text/colors/gradients/asset IDs. Filters: `${name|upper}`, `lower`, `title`, `default:TEXT`, `map:NAME`, `number[:DECIMALS]`, `format:SPEC`, chained left to right; unknown filters are errors. |
| `variable-map` | **`name`**, **`values`** (`{value: replacement}`, `"*"` = fallback), `merge`, or `delete: true` | Named lookup table for `${var|map:NAME}` (e.g. state codes to names, tiers to colours). |
| `stack` | `target` (a group) *or* **`name`** + **`targets`**, `direction` (`vertical`/`horizontal`), `gap`, `padding`, `align`, `justify` (`start`/`center`/`end`), `width`, `height`, `hide_if_empty`, `remove` | Auto-layout: lays the group's members out in a column or row inside its box, re-flowing around members that are hidden or empty (see below). Members cannot be moved/aligned/constrained by hand (`stack_managed`). |
| `comp-save` | **`name`** | Captures visibility/position/rotation/opacity/blend/constraints/styles. |
| `comp-apply` | **`name`** | Undoable; `render --comp NAME` previews read-only. |
| `symbol` | **`name`**, `target` | Turn a drawable layer into a master. |
| `pathfinder` | **`name`**, **`targets`** (shapes), **`mode`** (`union`/`subtract`/`intersect`) | New layer; hides originals; uses first operand's fill. Exports to SVG/PDF/PPTX as one compound path (real geometry, no masks); a stroked, translucent or effect-carrying operand cannot be geometry and becomes a listed raster fallback (rejected by `svg_policy="strict"`). |
| `repeat` | `target`, **`count`** (≤512, includes original), `dx`, `dy` (≥0), `dw`, `dh` | Stays one layer; re-applying replaces settings. |
| `repeat-blend` | as `repeat` plus **`end`** `{width,height,fill,color}` | Interpolates size/color to the last copy. |
| `radial-repeat` | `target`, **`count`** (2–360), `cx`, `cy` (pixels, `"50%"`, `"center"`; default canvas center), `sweep` (degrees, default 360), `start_angle`, `mirror`, `group` (default true), `name` | N copies of a layer around a center, each turned to face outward; `mirror` adds a reflection of every copy (kaleidoscope symmetry). Copies are ordinary layers inside one group. |
| `look` | **`look`** (`glow`, `neon`, `soft-shadow`, `hard-shadow`, `outline`, `gradient`, `grain`, `paper`, `film`, `duotone`, `risograph`, `sketch`, `watercolor`, `halftone`), `target`/`targets`, `color`, `amount` (0–1, default 0.5), `remove` | One-step finish built from layer styles and effects; reapplying replaces, `remove` takes only that look off. Styles and blur-like looks export as native SVG filters; grain/paper/film/etc. use the raster fallback under `svg_policy`. |
| `layer-intent` | `target`, `role` (`content`/`decoration`/`background`/`title`), `allow_overlap`, `allow_crop` | `role: title` marks the heading that names a page (deck checks, PPTX title, PDF title; otherwise a layer named exactly `title`/`heading`/`headline`, then the largest top text). `allow_crop: true` marks a deliberate edge crop or bleed: checks report it as informational. |
| `style-set` | **`style`** (name, up to three names, or `null` to clear), `options` (`{rule: false | {param: value, severity, enabled}}`) | Tags the document with a design style; `check --checks style` evaluates its premade rules. See [styles](../../../docs/styles.md). |

## Pixel art and animation

| type | fields | notes |
| --- | --- | --- |
| `pixel-art` | `name`, `width`, `height`, `palette`, `background`, `x`, `y` — **or** `rows` (+`palette`) | `rows`: list of equal-length strings, one char per pixel. `palette`: `{"symbol":"color"}` (1–94 printable ASCII symbols). Default palette `.`=transparent, `#`=black. |
| `pixel-draw` | `target`, **`x`**, **`y`**, **`color`** (palette symbol), `tool`, `x2`, `y2`, `width`, `height` | `tool`: `pixel` (default), `line` (to `x2`,`y2`), `rect` (`width`×`height` filled), `fill` (4-way flood). Native grid coordinates. |
| `pixel-palette` | `target`, **`colors`** | Recolor symbols everywhere. |
| `frame-save` | **`name`**, `duration` (10–60 000 ms, multiple of 10; default 100) | Snapshot the current scene as an animation frame (any canvas size; frames × canvas pixels ≤ pixel budget). |
| `frame-apply` | **`name`** | Restore a frame for editing. |
| `frame-delete` | **`name`** | |
| `animation-set` | `order` (frame names), `loop` (extra repeats; 0 = infinite); with **`name`** also `duration` (ms for every entry), `durations` (one per entry), `delete` | Without `name`: reorder the default animation (every saved frame exactly once). With `name`: define/replace a **named animation**, any subset of saved frames in any order (repeats allowed), own timing and loop; update only `loop`/`duration`/`durations` of an existing one; `delete: true` removes it. Export one with `vixl_export_animation(animation=NAME)`. `frame-delete` refuses frames a named animation uses. |
| `frames-edit` | **`operations`** (1–200 normal operations), `animation` (named animation's frames) *or* `frames` (names), `scene` (also edit the working scene; default false) | Apply the same edit to every saved frame (default), e.g. `{"type":"pixel-palette","target":"upper","colors":{"Y":"#d93a2b"}}` to recolour all poses. Atomic; errors name the frame. No animation ops, layouts, templates, pages or filesystem fields inside. |

## Sizes, layouts and color (0.13)

| type | fields | notes |
| --- | --- | --- |
| `canvas` | **`size`** (or `preset`), `orientation`, `bleed` (true/amount), `dpi`, `background` — or `width`/`height` — or `dpi` | Named sizes record dpi/bleed/safe and `trim-*`/`safe-*` guides. |
| `layout-apply` | **`name`**, `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items`, `image` (asset), `seed`, `palette`, `colors`, `keep_order`, `mode`, `type_scale`, `base_size`, `density`, `align`, `accent`, `mark`, `font`, `display_font`, `transparent`, `uppercase_labels`, `prefix`, `replace` | Creates layers, role swatches, type scale and grid. The result lists `unfilled_slots` and `next_steps` (how to fill an image slot) and `layout.roles` (which color became which role, and why). `keep_order: true` uses `palette` as background, surface, accents. See design-system.md. |
| `type-scale` | `base` (px, default 16), `ratio` (name or 1.05–2), `prefix`, `color` | Character styles caption/body/lead/subhead/title/headline/display. |
| `palette-generate` | **`name`**, **`color`**, `scheme` (`scale` default or a harmony), `count` | Swatches `NAME-50…950` or `NAME-1…n`. |

## Painting and timelines (0.13)

| type | fields | notes |
| --- | --- | --- |
| `paint-layer` | `name`, `width`, `height`, `x`, `y` | Empty paint layer (canvas-sized by default). |
| `paint` | `target`, `brush`, **`points`** or **`path`**, `pressure`, `space`, `size`, `color`, `opacity`, `mode` (`paint`/`erase`), `seed`, `settings` | Adds one editable stroke. No target → active paint layer or a new `paint` layer. |
| `paint-clear` | `target`, `last` | Remove the last N (or all) strokes. |
| `brush-define` | **`name`**, `base`, `settings`, `description` | Custom brush in the document. |
| `timeline-set` | `duration`, `fps` (1–60), `loop` (0 = forever), `clear` | |
| `keyframe` | `target` (layer or `canvas`) or `targets` (list), **`property`**, **`time`**, **`value`**, `easing`, `extend` | Replaces a key at the same time. A key past the end lengthens the timeline and the result's `warnings` say `timeline duration changed 8000 -> 8400 ms`; `extend: false` keeps the duration. |
| `keyframe-remove` | `target`, `property`, `time` | Track or single key. |
| `animate` | `target` or `targets`, **`property`**, **`to`**, `from`, `start`, `end`/`duration`, `easing`, `extend` | Two keys; `from` defaults to the current value. `targets` gives several parts the same keys. |
| `animate-preset` | `target` or `targets`, **`preset`**, `start`, `duration`, `easing`, `amount`, `distance`, `fade`, `to`, `extend` | fade/slide/pop/zoom/spin/pulse/shake/bounce/float/blink/typewriter/color-shift/draw-on/draw-off. |
| `marker` | **`name`**, `time` or `delete` | Named times usable wherever a time is accepted. |

## Legacy aliases (avoid in new code)

`operation`→`type`, `layer`→`target`; `set_opacity`, `set_blend`, `add_layer`, `remove_layer`,
`move_layer`, `set_effect`, `make_selection`.

## Results

Apply returns `{"success": true, "dry_run": bool, "operations": N, "changes": {...}}` plus, when relevant,
`warnings` (text cut off by the canvas or overflowing its box/group; valid fields that change nothing for
that shape; effects no operation asked for, such as a timeline that grew to fit a keyframe), `normalized`, `edit_layers` and `adapt_layout`. `detail:"brief"` (MCP default) keys changes by layer ID
with only `added`/`name`/`type`/`bounds`, or `changed` field names and `bounds`, or `removed`.
`detail:"compact"` (CLI/REST default; `Project.apply(..., detail="compact")`) gives the new values of changed
fields; added layers include name, type and bounds. `detail:"full"` (Python default, CLI `--detail full`)
includes complete before/after layer snapshots.
`vixl_operation_schema(types=[…])` returns each operation's JSON Schema with a one-line `description`, a typed and described
field list and, for the common ones, `examples` (gradients, glows, shadows, radial repeats …). `vixl_guide(brief="operations")`
lists every operation by purpose.

## Newer operation families

| type | key fields | reference |
| --- | --- | --- |
| `chart` / `chart-data` | `kind`, `categories`+`series` / `table` / `csv`, `title`, `colors`, `legend`, `value_labels`, `number_format`, `target` (restyle); `chart-data`: `set`, `append`, `remove_categories`, `add_series`, `remove_series`, `reload` | [charts](charts.md) |
| `organic` | `preset` or `parts`, `params`, `colors`, `fill`, `stroke`, `stroke_width`, `seed`, `name`, `target` (regrow) | [organic shapes](drawing-shapes-guides.md#organic-shapes) |
| `irregular` | **`seed`** (or `remove`), `target`/`targets`, `strength` (`subtle`/`natural`/`rough`), `amount`, `only`, `wobble`, `wobble_length`, `jitter`, `roughness`, `width_variation`, `pressure`, `lightness_drift`, `chroma_drift`, `hue_drift`, `rotation_jitter`, `scale_jitter`, `position_jitter` — opt-in, bounded imperfection; not for logos, charts, text or anything that must align | [imperfection](drawing-shapes-guides.md#imperfection-irregular-and-tear) |
| `tear` | **`seed`** (or `remove`), `target`, `as` (`mask`/`clip`/`path`), `edges`, `strength`, `depth`, `length`, `roughness`, `rim_width`, `rim_color`, `fibres`, `fill`, `name`, `width`/`height`/`x`/`y` (no target) — torn edge with rim and fibres | [imperfection](drawing-shapes-guides.md#imperfection-irregular-and-tear) |
| `guide` / `grid` | `guide`: `kind` (`axis`, `line`, `ray`, `segment`, `point`, `circle`, `path`) and its geometry; `grid`: `kind` (`columns`, `baseline`, `thirds`, `golden`, `armature`, `golden-spiral`, `polar`, `isometric`, `triangular`, `hex`, `oblique`, `perspective`), `region`, `delete` | [guides](drawing-shapes-guides.md#guides-grids-and-placement) |
| `place` / `snap` | `targets`, `guide`, `at`/`start`/`end`/`spacing`/`with`, `anchor`, `orient`; `snap`: `tolerance` | [guides](drawing-shapes-guides.md#guides-grids-and-placement) |
| `rich-text` / `text-style` | `markdown` or `spans`, `paragraphs`; `text-style`: `match`/`start`/`end`, character styles, `paragraphs` settings | [documents](documents.md#rich-text) |
| `page` / `master` | `action` (`add`, `select`, `remove`, `move`, `set`), `name`/`page`, `master`, `notes`, `background`, `hidden`, `transition` | [documents](documents.md#pages-masters-and-decks) |
| `field` / `field-set` / `form` | `kind`, `key`, `label`/`label_layer`, `required`, `max_length`, `format`, `pattern`/`message` (rules a fillable PDF enforces), `options`, `option`, `default`, `appearance`; `form`: `tab_order`, `title`, `lang` | [documents](documents.md#forms) |
| `drawing` | `action` (`import`, `clean`, `vectorize`, `straighten`, `smooth`, `fill`, `stroke`, `restyle`), `asset`, `target`, `strokes`, `points`, `settings` | [hand drawings](drawing-shapes-guides.md#building-on-a-hand-drawing) |
| `diagram` / `diagram-from-text` / `diagram-set` | `name`, `nodes`, `edges` or `text`, `layout`, `direction`, `routing`, `lanes`, `fit`, `x/y/width/height`; `diagram-set`: `remove_nodes`, `remove_edges`, `delete` | [diagrams](drawing-shapes-guides.md#diagrams-flowcharts-dependency-graphs-org-charts-mind-maps) |
| `text-flow` | `action` (`create`, `set`, `add-frame`, `link`, `unlink`, `reflow`, `style`, `delete`), `name`, `text`/`markdown`/`spans`, `frames` or `x/y/width/height/columns/gutter/page/shape`, `keep_together`, `orphans`, `widows` | [text flow](documents.md#text-flow-one-story-through-linked-frames) |

Any operation also accepts `"page"` to address a page of a multi-page document.

