# Canonical operations reference

Vixl is a headless design engine for AI agents; people can drive the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

Every edit in Vixl is a JSON object with a `type`. Send a single object, an array, or
`{"operations": [...]}` to: MCP `vixl_apply(operations=[...])`, CLI `vixl apply FILE|-`,
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
docs/reference/operations.md (`x-targets` in the schema).

Conventions used below: **bold** = required. `target` is a layer name or `lyr_…` ID and, when
omitted, defaults to the active layer. Colors accept CSS names, `#rgb`, `#rrggbb`, `#rrggbbaa`,
`rgb()`/`rgba()` (alpha 0–1), `hsl()`, `transparent`, `@swatch`, and `${variable}`. Geometry: `x`/`y`
accept pixels, `"center"` or `"N%"`; `width`/`height` accept pixels or `"N%"` (of the canvas, or of
the parent group) on creation ops, `move`, `resize`, `select` and `text-layout`.

The authoritative schema is always `vixl schema OPERATION` (bare `vixl schema` lists names) / `GET /schema` / `vixl://operations` / `vixl_reference('operations', name=[…])`.

## Operations by need

| Need | Operations / commands |
| --- | --- |
| Start | named sizes (`canvas` `size`, `vixl new NAME`, `vixl_document(action='create', size=)`), `layout-apply`, `type-scale`, `palette-generate`, `guidance` |
| New layers | `add` (image), `solid`, `gradient` (linear/angled/radial, multi-stop, `falloff` curves for soft halos), `text`, `shape` (`solid`/`gradient`/`shape`/`text` with `target` edit that layer in place instead of adding one), `frame` (image box with fill/fit), `pixel-art`, `paint-layer`, `adjustment`, `symbol-instance` |
| Transform | `move`, `resize`, `scale`, `rotate`, `skew`, `transform` (affine), `distort` (envelope, corner-pin), `flip`, `crop`, `opacity`, `blend`, `hide`/`show` |
| Stacking | `raise`, `lower`, `top`, `bottom`, `reorder` (`above`/`below`), `group`/`ungroup`, `reparent` (into/out of a group, keeps position), `clip` |
| Objects | `object` (kind, named parts, sub-objects, paths like `dog/head`), `object-save`/`object-place`, `inspect object=`, `isolate` with `views: [parts]`, isolated `export` |
| Layout | `align` (to canvas/selection/layer), `distribute`, `constrain`/`unconstrain`, `stack` (auto-layout column/row that re-flows around hidden or empty members; text `hide_if_empty`), `guide`, `grid`, `canvas` (resize/preset), `artboard` |
| Color & filters | 27 built-in effects (brightness … white-balance … auto-contrast), `effect-set/enable/disable/remove/move`, `lut` + `lookup` (a stack effect), `preset-save/apply` |
| Selections & masks | `select` (rect/ellipse/color/alpha/all/none/invert, add/subtract/intersect, feather), `mask` (create/from-selection/import/gradient/invert/enable/disable/delete; `gradient` fades a layer out, which a `gradient-overlay` style cannot: its transparent stops show the layer's own fill) |
| Typography | `text`, `text-set` (`tabs`), `text-layout` (box, fit, wrap, warp, path), `style-define`/`style-apply`, `swatch` |
| Decoration | `layer-style` (drop-shadow, stroke, outer-glow, color-overlay, gradient-overlay), `look` (named finishes: clean-flat, subtle-grain, light-paper, glow, neon, soft-shadow, hard-shadow, outline, gradient, soft-halo, grain, paper, film, duotone, risograph, sketch, watercolor, halftone, hand-made, plush), `repeat`, `repeat-blend`, `radial-repeat` (copies around a center, optional mirror, per-step/jitter, `merge`), `scatter`, `pattern-scatter`, `pathfinder` |
| Templates | `variable`, `replace-contents`, `comp-save`/`comp-apply`, CSV `render --data`, `export-screens` |
| Painting | `paint` (17 brushes, points or SVG path, pressure, erase), `paint-clear`, `brush-define` |
| Motion | `timeline-set` (`loop_mode`), `keyframe`, `keyframes` (or `sample` a wave), `keyframe-remove`, `animate`, `animate-preset`, `text-animate` (per char/word/line), `motion` (wiggle, line-boil …), `character-pose` (`time` keys), `audio-track`, `marker`; `vixl_render(action='timeline')`, `vixl_export(kind='timeline')` |
| Pixel art & sprite frames | `pixel-art`, `pixel-draw`, `pixel-palette`, `frame-save/apply/delete`, `animation-set` (`name`+`order`: named animations, each exportable alone with `animation=`), `frames-edit` (one edit applied to every saved frame), `export-animation` (GIF/APNG/WebP/MP4/sheet) |
| Color & print | color language in every color field, `vixl_reference('color')`, CMYK/PDF/ICO export, `vixl_export(kind='icons')`, proof/simulate previews, `print`/`color_vision` checks |
| History | undo/redo (a count larger than the history goes as far as it can and says so), checkpoint, branch, checkout, compare, transactions |
| Styles | `vixl_reference('styles')` (28 design styles: principles, palettes, type, layout, imagery, do/don't), `style-set` tags the document, `check --checks style` evaluates the style's premade rules |
| QA | check (bounds/overlap/contrast/safe area/legibility/composition, and object for declared objects: parts, gaps, proportions, mirrored pairs, layering against the kind; opt-in print, color_vision, style, connected (floating parts of a grouped object), cost (layers that take over 10× the median to draw, naming the blur radius or stroke points), accessibility (alt text, language, small text, colour-only charts, reading order, plus contrast and colour vision); every finding has an `action`: fix / review / informational), inspect, measure (sample/histogram/contrast), spacing, validate/assert, render preview (zoomable, time, proof, simulate, isolate one object), compare revisions |
| AI (provider) | generate/inpaint/img2img, extend (outpaint), upscale, regenerate, background-remove, select object/subject, remove, content-aware-fill, describe/detect/OCR, natural-language plan |

When unsure of a field, get the authoritative schema: MCP `vixl_reference('operations', name=[…])`
(also resource `vixl://operations`); CLI `vixl schema OPERATION` (bare `vixl schema` lists the operations; `--all` is the whole 900 KB schema; `vixl schema document` for the `.vixl` file format); REST `GET /schema`; per-command
syntax via `vixl COMMAND --help`.

## Creating layers

| type | fields | notes |
| --- | --- | --- |
| `add` | **`path`** *or* **`asset`**, `name`, `x`, `y`, `linked`, `credit`, `license` | `path` is CLI/Python only (MCP: use `import-image`, which also takes a `url`). `asset` = an embedded ID like `assets/<sha256>.png`. `linked` keeps an external reference (needs `--allow-linked`). `credit`/`license` are stored in the layer's `provenance` for attribution. `max_pixels` / `downsample: "placed@2x"` shrink the embedded copy; with them a source up to 4× the pixel limit imports (image imports downsample such a source on their own). |
| `solid` | `name`, `width`, `height`, `color`, `x`, `y`, `target` | Defaults to canvas size; `color` defaults to `@surface` (a neutral grey without a palette). With `target`, edits that solid in place. |
| `gradient` | `name`, `width`, `height`, `start`, `end`, `direction`, `stops`, `angle`, `falloff`, `x`, `y`, `target` | `direction`: `vertical` (default), `horizontal`, `angled` (`angle` 0°=left→right, 90°=top→bottom), `radial` (ends at the inscribed ellipse; corners take the last stop). `stops`: 2–64 `{"offset":0..1,"color":…}` strictly increasing. `falloff`: `linear` (default), `smooth`, `ease`, `quadratic`, `gaussian` (soft halo); same in every export. |
| `text` | **`text`** *or* `target`, `name`, `size`, `hide_if_empty`, `color`, `align` (`left`/`center`/`right`), `spacing` (px added to the font's line pitch, may be negative), `line_height` (multiple of the size), `tracking` (letter spacing, px), `text_transform` (`uppercase`, `lowercase`, `capitalize`), `font`, `tabs`, `x`, `y`, `baseline_y` | Without `size`, the body size of the type scale (about 2.6% of the canvas short side); without `spacing`/`line_height`, the line-height table (body 1.45, lead 1.35, headings 1.1, display 1.0, captions 1.3); the result lists filled values under `defaults`. `x`/`y` may be `"center"` or `"N%"`. `baseline_y` (instead of `y`) puts the first line's baseline at that y. `font`: a registered name, `heading`/`body` (follows the document typography), or a file path (CLI/Python only); default font DejaVu Sans is the proofing fallback. Multiline via `\n`. `tabs`: tab stops `[{at, align: left/right/center/decimal, leader}]` for `\t` in the text (`at` px or `"100%"` of the box); a line with a tab is not wrapped. With `target`, edits that text layer in place (like `text-set`; `text` is then optional). `within`: a shape to centre the text in (its content box; no `x`/`y`). |
| `shape` | **`shape`** *or* `target`, `name`, `width`, `height`, `x`, `y`, `fill`, `fill_gradient`, `stroke`, `stroke_width`, `line_cap`, `trim_start`, `trim_end`, `radius`, `sides`, `inner_radius`, `start_angle`, `end_angle`, `opacity`, `rotation`, `space` | `shape`: `rectangle`, `rounded-rectangle` (`radius`; a `rectangle` with a `radius` becomes one), `ellipse`, `polygon` (`sides`), `star` (`sides`, `inner_radius` 0.01–1), `arc`, `line`. `arc` is a pie wedge or donut segment of the ellipse filling the box: angles in degrees, 0 = 3 o'clock, clockwise (-90 = 12 o'clock), `inner_radius` 0–0.99 of the outer radius (0 = wedge, 0.6 = donut), no angles = full disc/ring. `closed: false` draws only the curve (an open stroke: no default fill, takes `line_cap`, no `inner_radius`). Wedges sharing a box and differing in angles make a pie/donut chart. Procedural, redrawn crisply on resize. `trim_start`/`trim_end` (0–100 %) draw only that part of the stroke, and are animatable (draw-on); `line_cap`: `butt`/`round`/`square`. `pen` takes the same three, and `opacity`/`rotation` too. A closed shape's stroke sits inside its outline (outer edge on the box edge; `radius` stays the outer corner radius); `stroke_align` `center`/`outside` moves it; paths, arcs and lines are stroked on their centre line. Fill: a new closed shape with no `fill` gets `@accent` (a neutral grey without a palette; layers saved before 0.23 keep white); a `stroke` without `stroke_width` is about 1.5% of the short side, a `stroke_width` without `stroke` draws in `@ink`, and an open shape with neither fill nor stroke is an `@ink` line; a `rounded-rectangle` without `radius` takes the document corner style (soft when it is sharp); an open one (`line`, a `path` with no closing `Z`, or an `arc` with `closed: false`) that has a `stroke` and no `fill` is unfilled in every output (render, SVG, PDF, PPTX). `fill: "none"` means `transparent`. `fill_gradient` (the `gradient` fields: `start`/`end` or `stops`, `direction`, `angle`, `center`, `falloff`) fills the shape with a gradient spanning its box in every output, the stroke keeping its colour; `fill` then holds the gradient's middle colour (what checks read) unless given too; a `fill` object such as `{"start":…,"end":…}` is read as `fill_gradient`. With `target`, a `fill` colour replaces the gradient and `fill_gradient: null` removes it. `path`: literal local pixels from x/y; without width/height the box reaches the path's farthest point (never the canvas); negative coordinates draw outside the box. `opacity` (0–1) and `rotation` (degrees) apply at creation or edit; with `target`, `space: "canvas"` reads x/y as document coordinates for a grouped layer. Shortcut parameters: `heart` `apex`/`cleft`/`tip`; `speech-bubble` `pointer_side` (bottom/top/left/right), `pointer_position` (0-1), `pointer_size`, `body` (body share of the depth, default 0.75); `shield` `depth`; `chevron` `thickness`; `trapezoid`/`parallelogram` `slant`; `triangle` `apex`; `tag` `depth` (all optional; defaults keep the fixed outlines; `vixl_reference('capabilities', name="shapes")` lists every shape's). Results and inspect report `content_bounds` (the usable inner area: bubble body, badge centre, frame opening, device screen) when it is smaller than the box. |
| `frame` | `name`, `width`, `height`, `x`, `y`, `path` *or* `asset`, `fit` (`fill`/`fit`), `frame_shape`, `outline`, `max_pixels`, `downsample` | Image placed in a fixed box; `fill` crops, `fit` letterboxes. `frame_shape`: `rectangle` (default), `ellipse`, `star`, `hexagon`, `heart`; `outline` (a closed SVG path in frame-local pixels) overrides it. Both become an embedded mask that survives `replace-contents`; keep the canvas transparent for a shaped image file. |
| `pixel-art` | `name`, `width`, `height`, `x`, `y`, `palette`, `background`, **or** `rows` | Character-grid sprite (1–256 per side). See *Pixel art* below. |
| `adjustment` | **`effects`** (list of effect objects), `name` | Adjustment layer: filters the composited stack *below it* in its parent. |
| `symbol-instance` | **`symbol`**, `name`, `x`, `y`, `width`, `height` | Live copy of a symbol master. |
| `duplicate` | `target`, `name` | |
| `link` | **`source`** (workspace `.vixl`; or `target` to edit one), `name`, `x`, `y`, `width`, `height`, `fit` (`fill`/`fit`/`stretch`), `position`, `crop` `{x,y,width,height}`, `artboard`, `source_page`, `variables` | Another document, drawn live: edits to the source show at the next render. Sources stay in the workspace; cycles and depth > 4 are errors. `link` with a `target` edits it (`null` clears), `link-refresh` records the seen revision (see `links` in `vixl_apply(workflow=…)`), `link-embed` freezes it into an image. Sources resolve beside the document first, then in the workspace (a source in the document's folder is stored relative to it, so the folder can be copied). |
| `qr` | **`data`** (may use `${var}`), `error` (`L`/`M`/`Q`/`H`), `quiet` (modules, default 4), `module` (px) or `size`, `color`, `background` (`none` = no group), `name`, `x`, `y`; `target` edits | Vector QR code: one merged path layer (`NAME code`) grouped with `NAME background`. Re-encoded at render for merges. `check codes`: module size at dpi, contrast, clear quiet zone. See `docs/guides/output/codes.md`. |
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
| `rasterize` | `target` — bakes text/shape/etc. to pixels, with effects, mask, layer styles and clipping |
| `path-split` | **`target`**, `polygon` or `line` (`[[x, y], …]`), `overlap`, `names`, `space` (`layer`/`canvas`), `curves` | Cuts a filled path into two named parts (inside/outside a polygon, or left/right of a line); `overlap` makes both reach across the cut; the target is hidden. |
| `die-cut` | **`targets`**, `distance` (px, default 12), `name` (default `cut-line`), `stroke`, `stroke_width`, `join` | A sticker cut line: the targets' ink silhouette (holes filled) grown by `distance`, as one stroked, unfilled path above them; separate parts stay separate contours. |
| `merge-layers` | **`targets`** (≥2, one parent; groups bring their members), `name` — one raster layer at the topmost's slot; blends composite among the merged layers only (warns otherwise); hidden targets are discarded |
| `flatten` | `name` (default `flattened`), `keep_hidden` — the page's visible top-level layers become one canvas-size raster layer |
| `group` | **`name`**, **`targets`** (list), `above`/`below` (a layer: the new group's z-slot; default its topmost member's) — children keep local coordinates; nest ≤16. Edit a member by canvas coordinates with `space: "canvas"` on `move` or `shape`/`text` with `target`. |
| `ungroup` | `target` |
| `reparent` (aliases `move-into`, `adopt`) | **`targets`**, **`into`** (a group, or `null`/`"page"` for the top level), `above`/`below` (a child of the new parent) or `index` (0 = bottom; default on top), `keep` (`appearance` default: stays where drawn, transform converted into the new parent, uneven scale held in `affine`; `local`), `fit` (default true: the group's content box grows, nothing moves) | Move layers into or out of a group without ungrouping; groups keep their transforms and effects. Refuses cycles, non-group or repeating `into`, split clip pairs, and position/size tracks under a turned or scaled parent (names them). |
| `clip` | `target`, `base` (sibling) — multiplies target alpha by base alpha; `release: true` removes |

## Transform and appearance

| type | fields | notes |
| --- | --- | --- |
| `move` | `target`, `x`, `y`, `relative`, `baseline_y` | Absolute move clears constraints; `relative: true` adds offsets. `baseline_y` (text only) places the first baseline. |
| `resize` | `target`, `width`, `height`, `keep_aspect` | One dimension changes only that side of shapes, text, groups and solids (reported under `normalized`) but scales imported images (raster) proportionally; `keep_aspect: true` scales the other side proportionally on any layer, `false` changes only the given side; two dimensions stretch. Turns off text auto-size. |
| `scale` | `target`, **`value`** or `x`/`y`, `anchor` (alias `about`) | Factor (0.8 = 80 %), 0.001–100. Negative mirrors: `value` flips both axes, `x: -1` flips horizontally (like `flip`) and keeps the size. `anchor`: the point kept fixed, `pivot`, an anchor name or `[x, y]` fractions (default: the pivot on a pivoted layer, else the bounds' top-left). |
| `rotate` | `target`, **`value`**, `about` | Degrees clockwise about the layer's pivot (default: its center, which stays put); bounds expand. `about`: another fixed point, an anchor name (`top-left` …) or `[x, y]` fractions of the unrotated box (clears constraints). |
| `pivot` | `target`, **`value`** (`[x, y]` fractions of the unrotated box, or `top-left`…`bottom-right`/`center`), `units` (`fraction`/`px`/`canvas` — a document point, through parent groups), or `clear` | Point that rotation and scale turn about; stays fixed on the canvas (stills, timeline, SVG). Keeps the drawn pose. A pivoted layer's stored `x`/`y` is its unrotated box. |
| `flip` | `target`, **`direction`** | `horizontal` / `vertical`. |
| `crop` | `target`, **`x`, `y`, `width`, `height`** | In the original embedded raster's coordinates. |
| `opacity` | `target`/`targets`, **`value`** | 0–1, or `"N%"`; a bare number above 1 is an error. |
| `blend` | `target`, **`value`** | `normal`, `multiply`, `screen`, `overlay`, `darken`, `lighten`, `difference`, `add`, `subtract`. |
| `text-set` | `target`, `text`, `size`, `color`, `align`, `spacing`, `line_height`, `stroke_width`, `stroke_color`, `font`, `tabs` (`[]` removes), `baseline_y` | Edit a whole text layer (content, colour, size, font); keeps a `text-layout` box and, on rich text, the formatting that still applies (`warnings` lists what was dropped). Partial styling is `text-style`. `font`: registered name, `heading`/`body` role, or a file (CLI/Python). |
| `text-layout` | `target`, `width`, `height`, `fit`, `wrap`, `warp`, `amount`, `path` | Box wrapping; with only `width` the height grows to the wrapped lines; `wrap`: `greedy`, `balance` (even lines, same count; headings default to it in new documents) or `pretty` (no one-word last line; body text), kept when the box changes; `fit: true` shrinks font to fit; `warp`: `none`/`arc`/`flag`/`bulge` with `amount` −1..1; `path`: polyline `[[x,y],…]` in local px. Replaces previous layout. |
| `layer-style` | `target`, **`name`**, `settings`, `remove` | See *Layer styles*. |
| `replace-contents` | `target`, `path` *or* `asset` *or* `variable`, `fit` | Swap image, keep ID/box/effects/mask/styles. |

## Layout

| type | fields | notes |
| --- | --- | --- |
| `align` | **`alignment`**, `target`, `targets`, `margin`, `relative_to`, `box` | `alignment`: `center`, `center-x`, `center-y`, `top`, `bottom`, `left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, `baseline` (text only: first baselines match the first target's or a `relative_to` text layer's). `relative_to`: `canvas` (default for one target), `selection` (default for several; union bounds) or a sibling. `box: "content"` (with a sibling `relative_to`) aligns to that shape's content box (a bubble's body, a badge's centre). Bakes positions, clears constraints. |
| `distribute` | **`targets`** (≥3 siblings), **`axis`** (`horizontal`/`vertical`), `gap` | Without `gap`: equal edge-to-edge spacing between outer items. |
| `constrain` | `target`, **`constraints`** | e.g. `{"center-x":"canvas.center-x","top":"logo.bottom+40"}`. Keys `left/right/center-x` (one per axis) and `top/bottom/center-y`. Values: `canvas`, layer name/ID, or `guide:NAME`, then `.edge` and optional `+N`/`-N`. Cycles rejected. Siblings only inside groups. |
| `unconstrain` | `target` | |
| `canvas` | `width`, `height`, `background`, `preset` (same as `size`: any named size such as `instagram-post`, `story`, `youtube-thumbnail`) | Constraints reflow. Named sizes: see *Sizes, layouts and color* below. |
| `guide` | **`name`**, **`axis`** (`x`/`y`), **`position`** | Named, never rendered; use in constraints as `guide:NAME.left+8`. |
| `grid` | **`name`**, `columns`, `rows`, `margin`, `gutter` | Generates guides `NAME-x1-start`, `NAME-x1-end`, `NAME-y1-start`, … |
| `artboard` | **`name`**, `preset` *or* `width`/`height`, `x`, `y`, `background`, `variables`, `targets`, `delete` | Named alternate canvas sizes in one document. `targets` = top-level layer IDs shown (absent = all). |
| `edit-layers` | **`where`**, **`do`**, `dry_run`, `expect` | Bulk edit: runs the operation(s) in `do` on every layer matching `where` (`role`, `name` glob, `name_regex`, `kind`, `shape`, `tag`, `group`, `object` (an object or path and its subtree), `object_kind` (objects of a kind or below it), `part`, `text_contains`, `text_regex`, `id`, `visible`, `page`, `not`; keys AND together, values may be lists). Result `edit_layers: [{matched, layers}]`; `expect` fails unless exactly that many match; no match warns. `do` must not set `target` or create layers. Tag layers with `layer-intent` `tags`. |
| `adapt-layout` | `size` (+ `orientation`, `dpi`, `bleed`) *or* `width`+`height`, `mode` (`proportional`/`stack`), `scale` (`fit`/`fill`/`width`/`height`/number), `anchors`, `where`, `text` (`scale`/`keep`), `min_text`, `safe`, `together`, `report`, `recompose`; or with `targets`: `targets`, `width`, `height`, `margin`, `gap` | Without `targets`: resize the canvas and re-lay out every layer proportionally (edge margins kept, middle content keeps its relative place, backgrounds and bands stretch, other decoration scales uniformly, photos cover, text scales but not below `min_text`, layers that sat together move together, content keeps inside the size's safe area; `optional`-tagged text too small to read is hidden); result `adapt_layout` lists where each layer moved. `recompose: true` instead reapplies the stored generated-layout recipe at the new size, replacing edits to generated layers and their IDs. With `targets`: vertical reflow. For several sizes at once use `vixl_apply(workflow='adapt-sizes')`. |

## Selections and masks

| type | fields | notes |
| --- | --- | --- |
| `select` | **`shape`**, `x`, `y`, `width`, `height`, `color`, `tolerance`, `target`, `asset`, `mode`, `feather` | `shape`: `rect`, `ellipse` (x,y,w,h), `color` (`color`, `tolerance`), `alpha` (`target` layer), `asset` (grayscale mask asset), `all`, `none`, `invert`. `mode`: `replace`/`add`/`subtract`/`intersect`. Canvas coordinates. |
| `mask` | `target`, **`action`**, `path`, `start`, `end`, `stops`, `direction`, `angle`, `center`, `falloff` | `action`: `create` (white), `from-selection`, `import` (`path`; CLI/Python only), `gradient` (a fade over the layer's box: `start` white and `end` black by default, `direction` horizontal; the gradient fields as on `gradient`), `invert`, `enable`, `disable`, `delete`. White = visible, black or a transparent stop = hidden. Masks follow the layer's transform. To fade a shape out (a light beam, a vignette band) use `gradient`, not a `gradient-overlay` style: an overlay recolours the layer and its transparent stops show the layer's own fill. |

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
| `gradient-overlay` | `start`, `end`, `stops`, `direction`, `angle`, `falloff` (same as `gradient`) |

## Text styles, swatches, variables, comps, symbols

| type | fields | notes |
| --- | --- | --- |
| `swatch` | **`name`**, **`color`**, or `delete: true` (+ `detach`) | Use as `@name`; redefining updates every use. `delete` is refused (`swatch_in_use`, users under `used_by`) while layers, swatches, styles or variables use it; `detach: true` writes its color into them first. |
| `style-define` | **`name`**, **`settings`**, `kind` | `character`: `size`, `color`, `stroke_width`, `stroke_color` (ints). `paragraph`: `align`, `spacing`. |
| `style-apply` | **`name`**, `target`, `kind` | Linked: redefining the style updates layers. |
| `variable` | **`name`**, `value`, or `delete: true` | `${name}` in text/colors/gradients/asset IDs. Filters: `${name|upper}`, `lower`, `title`, `default:TEXT`, `map:NAME`, `number[:DECIMALS]`, `format:SPEC`, chained left to right; unknown filters are errors. `$${name}` is a literal `${name}`. |
| `variable-map` | **`name`**, **`values`** (`{value: replacement}`, `"*"` = fallback), `merge`, or `delete: true` | Named lookup table for `${var|map:NAME}` (e.g. state codes to names, tiers to colours). |
| `stack` | `target` (a group) *or* **`name`** + **`targets`**, `direction` (`vertical`/`horizontal`), `gap` (px or spacing units such as `"2u"`, 1u = half the body size; the default is 2u), `padding`, `align`, `justify` (`start`/`center`/`end`), `width`, `height`, `hide_if_empty`, `remove` | Auto-layout: lays the group's members out in a column or row inside its box, re-flowing around members that are hidden or empty (see below). Members cannot be moved/aligned/constrained by hand (`stack_managed`). |
| `comp-save` | **`name`** | Captures visibility/position/rotation/opacity/blend/constraints/styles. |
| `comp-apply` | **`name`** | Undoable; `render --comp NAME` previews read-only. |
| `symbol` | **`name`**, `target` | Turn a drawable layer into a master. |
| `pathfinder` | **`name`**, **`targets`** (shapes), **`mode`** (`union`/`subtract`/`intersect`) | New layer; hides originals; uses first operand's fill. Exports to SVG/PDF/PPTX as one compound path (real geometry, no masks); a stroked, translucent or effect-carrying operand cannot be geometry and becomes a listed raster fallback (rejected by `svg_policy="strict"`). |
| `repeat` | `target`, **`count`** (≤512, includes original), `dx`, `dy` (≥0), `dw`, `dh`; per-step `rotation_step`, `scale_step`, `opacity_step`, seeded `rotation_jitter`/`scale_jitter`/`position_jitter`/`opacity_jitter` (`seed`), `merge`, `name` | Stays one layer; re-applying replaces settings. Any per-step, jitter or `merge` field makes real copies instead (a group `name`, or one merged path with `merge`). |
| `repeat-blend` | as `repeat` plus **`end`** `{width,height,fill,color}` | Interpolates size/color to the last copy. |
| `radial-repeat` | `target`, **`count`** (2–360), `cx`, `cy` (pixels, `"50%"`, `"center"`; default canvas center), `sweep` (degrees, default 360), `start_angle`, `mirror`, `group` (default true), `name`, plus the per-step/jitter/`merge` fields of `repeat` | N copies of a layer around a center, each turned to face outward; `mirror` adds a reflection of every copy (kaleidoscope symmetry). Copies are ordinary layers inside one group, or one path with `merge`. |
| `scatter` | **`target`** (the region), `source` (motif layer or list) or `mark` (shape spec, or `{mark: tuft|flick}`) or `preset: fur`, `placement` (`inside`/`along`), `direction` (`normal`/`tangent`/`cone`/`random`), `spread`, `anchor` (`center`/`base`), `offset`, `spacing` or `count`, `seed`, `scale`, `scale_jitter`, `rotation`, `rotation_jitter`, `position_jitter`, `colors`, `tone_variation`, `tones`, `exclude`, `exclude_margin`, `merge`, `name`, `hide_source`, `length`/`flicks` (fur) | Poisson-disc copies inside the target's outline, or along its edge; a group of copies above the target, or with `merge` one path per tone. Result: `scatter` report. |
| `pattern-scatter` | `source`/`mark`, **`width`**, **`height`**, `x`, `y`, `count`/`spacing`, `seed`, jitter and tone fields as `scatter`, `background`, `pattern` (save as a pattern), `merge`, `name`, `distribution` (`progressive`, the default, or `poisson`), `thin` (share to keep, `{keep}` or `{count}`); or `target` (a tile) to rebuild | Seamless tile: toroidal Poisson-disc, copies crossing an edge get wrapped copies; result `pattern_scatter` with a `seam` score. Rebuild after motif edits with `{type: pattern-scatter, target: TILE}`. Progressive: a lower `count` keeps the first copies in place; `thin` removes the most crowded copies and keeps the rest. |
| `look` | **`look`** (`clean-flat`, `subtle-grain`, `light-paper`, `glow`, `neon`, `soft-shadow`, `hard-shadow`, `outline`, `gradient`, `soft-halo`, `grain`, `paper`, `film`, `duotone`, `risograph`, `sketch`, `watercolor`, `halftone`, `hand-made`, `plush`), `target`/`targets`, `color`, `amount` (0–1, default 0.5), `remove` | One-step finish built from layer styles and effects; reapplying replaces, `remove` takes only that look off. Styles and blur-like looks export as native SVG filters; grain/paper/film/etc. use the raster fallback under `svg_policy`. |
| `layer-intent` | `target`, `role` (`content`/`decoration`/`background`/`title`), `allow_overlap`, `allow_crop`, `tags`, `color_vision_safe`, `detached_ok`, `waive`, `alt`, `decorative` | `role: title` marks the heading that names a page (deck checks, PPTX title, PDF title; otherwise a layer named exactly `title`/`heading`/`headline`, then the largest top text). `allow_crop: true` marks a deliberate edge crop or bleed: checks report it as informational. `detached_ok: true` marks a part that floats on purpose (or a group of separate parts), so the `connected` check skips it. `alt` describes a meaningful image, frame, chart, link or group (not text; `""` clears it), `decorative: true` marks an ornament readers skip; both reach HTML, SVG, PPTX and PDF. `waive` (check names or `{check, reason, expires, with}`; replaces the layer's, `[]` clears) keeps the layer's findings of those checks as informational `waived` ones. |
| `waiver` | `check` or `rule` (+ `suite`), `target`, `reason`, `expires`, `with`, `remove` | Accept a finding on the record: with `target` on that layer, else for the whole document (a check, or a suite rule). Needs a `reason`; after `expires` (YYYY-MM-DD) the finding is back and an expired-waiver `fix` finding asks for a decision. |
| `object` | `target`/`targets`, `action` (`set` default, `part`, `unset`), `kind` (taxonomy kind or alias), `label`, `notes`, `references`, `stylized`, `proportions` (`check`/`ignore`); `part`, `side` (`left`/`right`/`center`), `depth` (`far`/`near`) | Declares a group one object (`group.object`), names a part (`layer.object_part`) or removes the declaration; the result's `next_steps` points to the kind's build block. Paths `dog/head`, `dog/leg[left]`, `person/guitar/neck` then work wherever a layer name does; `isolate` also takes `object:KIND`. The `object` check measures it against its kind (`stylized: true` skips proportions; `depth` orders side-view limbs). `ungroup` refuses an object unless `force: true`. A character group is a `person`. See [objects](../../../docs/guides/shapes/objects.md). |
| `object-save` | **`name`**, `target` (the object group), `description`, `tags` | Keeps an editable copy of the subtree (records, recipes, timeline tracks, fonts) in the document's object library. |
| `object-place` | **`name`**, `source` (a portable object `.vixl` in the workspace), `name_as`, `x`, `y`, `width`/`height`/`scale`, `recolor` (`{part: colour}`), `motion` | Inserts a saved or exported object as an editable group with new IDs; copies are independent. |
| `accessibility` | `lang` (BCP 47), `title`, `page_alt`, `page_lang`, `reading_order` (layers) | Document language and title; the active page's description, language and reading order (per page). HTML, SVG, PPTX and PDF exports carry them; `check --checks accessibility` asks for what is missing. |
| `style-set` | **`style`** (name, up to three names, or `null` to clear), `options` (`{rule: false | {param: value, severity, enabled}}`) | Tags the document with a design style; `check --checks style` evaluates its premade rules. See [styles](../../../docs/guides/layout/styles.md). |

## Pixel art and animation

| type | fields | notes |
| --- | --- | --- |
| `pixel-art` | `name`, `width`, `height`, `palette`, `background`, `x`, `y` — **or** `rows` (+`palette`); `shading`, `outline` | `rows`: list of equal-length strings, one char per pixel. `palette`: `{"symbol":"color"}` (1–94 printable ASCII symbols). Default palette `.`=transparent, `#`=black. Sprites draw with a shading ramp (`shading`: `true` or `{light: auto|top-left|top|top-right, colors: 16, highlight}`) and a 1 px outline (`outline`: `true` or a colour); the stored rows stay as drawn, `false` turns either off. |
| `pixel-draw` | `target`, **`x`**, **`y`**, **`color`** (palette symbol), `tool`, `x2`, `y2`, `width`, `height` | `tool`: `pixel` (default), `line` (to `x2`,`y2`), `rect` (`width`×`height` filled), `fill` (4-way flood). Native grid coordinates. |
| `pixel-palette` | `target`, `colors`, `shading`, `outline` (at least one) | Recolor symbols everywhere; turn the shading ramp or outline on (`true`, settings, a colour) or off (`false`). |
| `frame-save` | **`name`**, `duration` (10–60 000 ms, multiple of 10; default 100) | Snapshot the current scene as an animation frame (any canvas size; frames × canvas pixels ≤ pixel budget). |
| `frame-apply` | **`name`** | Restore a frame for editing. |
| `frame-delete` | **`name`** | |
| `animation-set` | `order` (frame names), `loop` (extra repeats; 0 = infinite); with **`name`** also `duration` (ms for every entry), `durations` (one per entry), `delete` | Without `name`: reorder the default animation (every saved frame exactly once). With `name`: define/replace a **named animation**, any subset of saved frames in any order (repeats allowed), own timing and loop; update only `loop`/`duration`/`durations` of an existing one; `delete: true` removes it. Export one with `vixl_export(kind='animation', animation=NAME)`. `frame-delete` refuses frames a named animation uses. |
| `frames-edit` | **`operations`** (1–200 normal operations), `animation` (named animation's frames) *or* `frames` (names), `scene` (also edit the working scene; default false) | Apply the same edit to every saved frame (default), e.g. `{"type":"pixel-palette","target":"upper","colors":{"Y":"#d93a2b"}}` to recolour all poses. Atomic; errors name the frame. No animation ops, layouts, templates, pages or filesystem fields inside. |

## Sizes, layouts and color (0.13)

| type | fields | notes |
| --- | --- | --- |
| `canvas` | **`size`** (or `preset`), `orientation`, `bleed` (true/amount), `dpi`, `background` — or `width`/`height` — or `dpi` | Named sizes record dpi/bleed/safe and `trim-*`/`safe-*` guides. |
| `layout-apply` | **`name`**, `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items`, `image` (asset), `seed`, `palette`, `colors`, `keep_order`, `mode`, `type_scale`, `base_size`, `density`, `align`, `accent`, `accent_words` (headline words set in `@accent-text`, whole words, any case; missing ones warn), `mark`, `font`, `display_font`, `transparent`, `uppercase_labels`, `prefix`, `replace`, `gap` (px or `"2u"`), `images`, `unfilled` (`blank`/`omit`), `variety`, `predictable`, `direction` | Creates layers, role swatches, type scale and grid. The result lists `unfilled_slots` and `next_steps` (how to fill an image slot) and `layout.roles` (which color became which role, and why). `keep_order: true` uses `palette` as background, surface, accents. See design-system.md. |
| `type-scale` | `base` (px, default 16), `ratio` (name or 1.05–2), `prefix`, `color` | Character styles caption/body/lead/subhead/title/headline/display. |
| `palette-generate` | **`name`**, **`color`**, `scheme` (`scale` default or a harmony), `count` | Swatches `NAME-50…950` or `NAME-1…n`. |

## Painting and timelines (0.13)

| type | fields | notes |
| --- | --- | --- |
| `paint-layer` | `name`, `width`, `height`, `x`, `y` | Empty paint layer (canvas-sized by default). |
| `paint` | `target`, `brush`, **`points`** or **`path`**, `pressure`, `space`, `size`, `color`, `opacity`, `mode` (`paint`/`erase`), `seed`, `settings` | Adds one editable stroke; `size` defaults to 1.5% of the layer's short side and `color` to `@ink`. No target → active paint layer or a new `paint` layer. |
| `paint-clear` | `target`, `last` | Remove the last N (or all) strokes. |
| `brush-define` | **`name`**, `base`, `settings`, `description` | Custom brush in the document. |
| `timeline-set` | `duration`, `fps` (1–60), `loop` (0 = forever), `loop_mode` (`seamless`/`off`), `close`, `clear` | `seamless` warns about tracks that end differently from how they start and makes `animate-preset` entrances close themselves; `close: true` appends each track's start value at the end. A new timeline is seamless unless it is longer than 10 s or `loop: 1`; pass `loop_mode: "off"` for a play-once sequence. |
| `keyframe` | `target` (layer or `canvas`) or `targets` (list), **`property`**, **`time`**, **`value`**, `easing`, `extend` | Replaces a key at the same time. A key past the end lengthens the timeline and the result's `warnings` say `timeline duration changed 8000 -> 8400 ms`; `extend: false` keeps the duration. |
| `keyframe-remove` | `target`, `property`, `time` | Track or single key. |
| `animate` | `target` or `targets`, **`property`**, **`to`**, `from`, `start`, `end`/`duration`, `easing`, `intent`, `repeat`/`until`, `period`, `stagger`, `close`, `extend` | Two keys; `from` defaults to the current value. `targets` gives several parts the same keys (`stagger` ms apart). Without `easing`, `intent` (`entrance`/`exit`/`loop`/`emphasis`) picks the house easing (ease-out, ease-in, ease-in-out); otherwise ease-in-out. |
| `animate-preset` | `target` or `targets`, **`preset`**, `start`, `duration`, `easing`, `amount`, `distance`, `fade`, `to`, `repeat`/`until`, `period`, `stagger`, `close`, `extend` | fade/slide/pop/zoom/spin/pulse/shake/bounce/float/blink/typewriter/color-shift/draw-on/draw-off. |
| `marker` | **`name`**, `time` or `delete` | Named times usable wherever a time is accepted. |
| `character-pose` | `target` (the character), **`angles`** (`{bone: degrees}`), `time`, `easing` | Without `time`: a static pose. With `time`: joint keys (`joint:BONE` tracks); the rig is solved on every frame so limbs stay attached. Don't mix with x/y/rotation keys on the same limbs. Rigging: `character`, `character-rig`, `character-cycle`, `character-ik`. |
| `text-animate` | `target` or `targets` (text layers), **`preset`**, `unit` (`char`/`word`/`line`), `start`, `duration` (each unit), `stagger` (ms or `"30%"` of duration), `easing`, `direction` (forward/reverse/center/edges/random + `seed`), `mode` (in/out/in-out), `distance`, `amount`, `rotate`, `from`, `repeat`, `remove`, `extend` | Kinetic type: fade/fade-up/fade-down/slide-left/slide-right/pop/wave/typewriter/color-sweep per unit. The text stays one editable layer; stills, SVG, PDF and PPTX show the resting text. |

## Session steps (MCP `vixl_apply`)

Besides operations, a `vixl_apply` batch takes steps that need the workspace or the network. They run in order inside
the same all-or-nothing batch, so a later operation can use what an earlier step made (an `import-image` result, `steps[i].result`,
carries the new layer's `id`, `name` and `asset`). CLI equivalents: `vixl import`, `vixl font install|pair|cover`, `vixl roll --apply`.

| step | fields | notes |
| --- | --- | --- |
| `import-image` | `path` *or* `data_base64` *or* `url`, `name` (default `image`), `credit`, `license` | Embeds an image as a new layer. A name that exists already is an error: name it when a layout has an `image` layer. |
| `import-document` | `path` *or* `data_base64` (SVG, PDF) *or* `source` (Figma URL or key); `format` (`svg`, `pdf`, `figma`), `name`, `page`, `dpi`, `svg_mode` (`editable`, `auto`, `appearance`), `node_id`, `rasterize_unsupported`, `font_map` (PDF: `{family: registered name}`), `install_fonts` | Editable layers; `report` lists what a Figma import could not map, `fonts` how each PDF font was matched. See SKILL.md and `docs/guides/images/figma.md`. |
| `import-font` | **`name`**, `path` *or* `url` | Registers a TTF/OTF under that name. |
| `font-pair` | `pairing` (name or `random`), `seed`, `mood`, `best_for`, `scope` (`document`, `workspace`) | Installs and sets the heading and body fonts. |
| `font-install` | **`family`**, `weight`, `italic`, `name`, `role`, `scope` | One Google Fonts style, optionally as a role's font. |
| `font-cover` | `text`, `scripts` (`Devanagari`, `Han`, `Hiragana/Katakana`, `Hangul`, `Thai`, `Arabic`), `weight` | Installs the Noto face for each script no font draws and appends it to `font-fallbacks`; default: every text layer's characters. Refuses offline when a face is not cached. |
| `style-use` | **`name`**, `palette` | Tags the document with a catalog style (and applies its first palette). |
| `roll` | `purpose`, `mood`, `seed`, `variety`, `locks`, `slots`, `unfilled`, `replace` | Rolls a direction and applies fonts and layout; `replace` re-rolls a document that already has a layout. |

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
`vixl_reference('operations', name=[…])` returns each operation's JSON Schema with a one-line `description`, a typed and described
field list and, for the common ones, `examples` (gradients, glows, shadows, radial repeats …). `vixl_reference("operations")`
lists every operation by purpose.

## Newer operation families

| type | key fields | reference |
| --- | --- | --- |
| `chart` / `chart-data` | `kind`, `categories`+`series` / `table` / `csv`, `title`, `colors`, `legend`, `legend_values` (the legend as a key-value list), `value_labels`, `number_format`, `padding`, `target` (restyle); without `x`/`y`/`width`/`height` a new chart fills the safe area inset by two spacing units; `chart-data`: `set`, `append`, `remove_categories`, `add_series`, `remove_series`, `reload` | [charts](charts.md) |
| `table` / `table-data` | `table` (rows, header first) / `csv`, `columns` (`width`, `align` incl. `decimal`, `format`, `leader` such as `"."`), `header_fill`, `zebra`, `borders`, `font_size`, `width`, `target` (restyle); `table-data`: `set` (`row`, `column`, `value`), `append`, `remove_rows`, `add_columns`, `remove_columns`, `reload` | [charts](charts.md#tables) |
| `key-value-list` | `rows` (`{label, value, share}`) *or* `items` text (`label \| value \| share` per line), `shares: "auto"` (each value's share of the total), `number_format`, `colors` (a swatch per row), `rules`, `font_size`, `font`, `value_font`, `text_color`, `share_color`, `rule_color`, `name`, `x`, `y`, `width`; `target` restyles or gives new rows | [charts](charts.md#key-value-lists) |
| `organic` | `preset` or `parts`, `params`, `colors`, `fill`, `stroke`, `stroke_width`, `seed`, `name`, `target` (regrow) | [organic shapes](drawing-shapes-guides.md#organic-shapes) |
| `reflection` | **`horizon`**, `targets` (default: what stands above it), `squash`, `ripple`, `breakup`, `fade`, `blur`, `opacity`, `tint`, `seed`; `target` re-renders an existing reflection | [scene atmosphere](drawing-shapes-guides.md#scene-atmosphere-and-motifs) |
| `haze` / `bokeh` | `haze`: `target` (the light) or `x`/`y`, `form` (`band`/`round`), `width`, `height`, `color`, `strength`; `bokeh`: `region`, `count`, `size`, `opacity`, `colors`, `softness`, `blend`, `seed` | [scene atmosphere](drawing-shapes-guides.md#scene-atmosphere-and-motifs) |
| `star-field` / `string-lights` | `star-field`: `region`, `count`, `size`, `sparkles`, `fade`, `avoid` (default text), `clearance`, `seed`; `string-lights`: `target` path or `from`/`to`/`sag`, `count`/`spacing`, `size`, `bulb` (`globe`/`pear`/`lantern`), `colors`, `glow`, `hang`, `seed` | [scene atmosphere](drawing-shapes-guides.md#scene-atmosphere-and-motifs) |
| `irregular` | **`seed`** (or `remove`), `target`/`targets`, `strength` (`subtle` default/`natural`/`rough`), `amount`, `only`, `wobble`, `wobble_length`, `jitter`, `roughness`, `width_variation`, `pressure`, `lightness_drift`, `chroma_drift`, `hue_drift`, `rotation_jitter`, `scale_jitter`, `position_jitter` — opt-in, bounded imperfection; not for logos, charts, text or anything that must align | [imperfection](drawing-shapes-guides.md#imperfection-irregular-and-tear) |
| `tear` | **`seed`** (or `remove`), `target`, `as` (`mask`/`clip`/`path`), `edges`, `strength`, `depth`, `length`, `roughness`, `rim_width`, `rim_color`, `fibres`, `fill`, `name`, `width`/`height`/`x`/`y` (no target) — torn edge with rim and fibres | [imperfection](drawing-shapes-guides.md#imperfection-irregular-and-tear) |
| `guide` / `grid` | `guide`: `kind` (`axis`, `line`, `ray`, `segment`, `point`, `circle`, `path`) and its geometry; `grid`: `kind` (`columns`, `baseline`, `thirds`, `golden`, `armature`, `golden-spiral`, `polar`, `isometric`, `triangular`, `hex`, `oblique`, `perspective`), `region`, `delete` | [guides](drawing-shapes-guides.md#guides-grids-and-placement) |
| `place` / `snap` | `targets`, `guide`, `at`/`start`/`end`/`spacing`/`with`, `anchor`, `orient`; or `within` (a layer: anchor onto its content box; `box`, `margin`); `snap`: `tolerance` | [guides](drawing-shapes-guides.md#guides-grids-and-placement) |
| `rich-text` / `text-style` | `markdown` or `spans`, `paragraphs`; `text-style`: `match`/`start`/`end`, character styles, `paragraphs` settings | [documents](documents.md#rich-text) |
| `page` / `master` | `action` (`add`, `select`, `remove`, `move`, `set`), `name`/`page`, `master`, `notes`, `background`, `hidden`, `transition` | [documents](documents.md#pages-masters-and-decks) |
| `field` / `field-set` / `form` | `kind`, `key`, `label`/`label_layer`, `required`, `max_length`, `format`, `pattern`/`message` (rules a fillable PDF enforces), `options`, `option`, `default`, `appearance`; `form`: `tab_order`, `title`, `lang` | [documents](documents.md#forms) |
| `drawing` | `action` (`import`, `clean`, `vectorize`, `straighten`, `smooth`, `fill`, `stroke`, `restyle`), `asset`, `target`, `strokes`, `points`, `settings` | [hand drawings](drawing-shapes-guides.md#building-on-a-hand-drawing) |
| `diagram` / `diagram-from-text` / `diagram-set` | `name`, `nodes`, `edges` or `text`, `layout`, `direction`, `routing`, `lanes`, `fit`, `x/y/width/height`; `diagram-set`: `remove_nodes`, `remove_edges`, `delete` | [diagrams](drawing-shapes-guides.md#diagrams-flowcharts-dependency-graphs-org-charts-mind-maps) |
| `text-flow` | `action` (`create`, `set`, `add-frame`, `link`, `unlink`, `reflow`, `style`, `delete`), `name`, `text`/`markdown`/`spans`, `frames` or `x/y/width/height/columns/gutter/page/shape`, `keep_together`, `orphans`, `widows` | [text flow](documents.md#text-flow-one-story-through-linked-frames) |

Any operation also accepts `"page"` to address a page of a multi-page document.

