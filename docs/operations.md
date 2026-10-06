# Operations and document semantics

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

See [spacing checks and pixel animation](pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

`vixl schema` or REST `GET /schema` returns the full Draft 2020-12 JSON Schema. MCP exposes the same schema at `vixl://operations`. Every editing operation is schema-checked before I/O, then validated against the document and resource limits.

```json
{"operations":[
  {"type":"add","path":"portrait.png","name":"portrait"},
  {"type":"resize","target":"portrait","width":800,"keep_aspect":true},
  {"type":"align","target":"portrait","alignment":"top-right","margin":40},
  {"type":"select","shape":"rect","x":0,"y":0,"width":500,"height":300},
  {"type":"effect","target":"portrait","name":"brightness","amount":15},
  {"type":"mask","target":"portrait","action":"from-selection"}
]}
```

`Project.apply` accepts a single operation, an array, or an `operations` envelope. The complete batch succeeds or none of its state/assets/history changes do. File reads may occur during validation; dry-run never saves or changes the live project. Dry-run returns the same before/after document changes that a real apply would make. Generated IDs in separate dry-run and apply calls need not match.

Operations are normalized before validation (see [interfaces](interfaces.md#forgiving-input-and-actionable-errors)): legacy `operation`/`layer` keys, type aliases (`set_opacity`, `rect`, `circle`, `add-text`, `drop_shadow`, …), camelCase keys, field aliases (`font_size`, `fill`/`color`), opacity percentages and CSS colors. Each rewrite is reported in the result's `normalized` list. Geometry fields `x`/`y` accept pixels, `"center"` or `"N%"`; `width`/`height` accept pixels or `"N%"`, relative to the canvas or the target's parent group. Unknown fields, malformed dimensions, nonfinite numbers, and unknown types are still rejected, with the failing operation index, field, allowed values and suggestions in the error.

**Editing an existing layer.** `shape`, `solid`, `gradient` and `text` add a layer, unless `target` names an existing layer of the same kind: then they change that layer in place and only the fields you pass change, so its ID, stacking order, effects, masks and constraints stay put. `{"type":"shape","target":"bar","fill":"#6b3f69"}` recolours a bar; `{"type":"shape","target":"bar","height":120}` changes its height (width untouched); `{"type":"gradient","target":"sky","start":"#01030a","end":"#3a3058"}` recolours a gradient (on a multi-stop gradient `start`/`end` recolour the first and last stop; pass `stops` to replace them all); `{"type":"text","target":"headline","size":190}` resizes text (same as `text-set`). `name` renames the layer and `x`/`y` move it. A target of another kind, or `target` on `add`, `frame`, `adjustment` or `symbol-instance`, is rejected with the operation to use (`text-set`, `replace-contents`, `effect-set`, …) rather than silently adding a layer. From the CLI use `--target`, e.g. `vixl shape --target bar --fill '#6b3f69'`.

Common operation fields:

| Type | Fields |
| --- | --- |
| add | path **or** embedded asset; name, x, y, linked |
| solid / gradient | name, width, height, color **or** start/end/direction/stops/angle; `target` edits an existing layer |
| text | text, name, font, size, color, align, spacing, hide_if_empty, x/y; `target` edits an existing text layer |
| shape | shape, name, width, height, x/y, fill, stroke, stroke_width, line_cap, trim_start/trim_end, radius, sides, inner_radius, path; `target` edits an existing shape |
| text-set | target; text, size, color, align, spacing, stroke_width/stroke_color, hide_if_empty, font — the whole layer; on rich text keeps formatting that still applies and reports what it drops under `warnings` ([rich text](rich-text.md#editing)) |
| stack | target (a group) **or** name + targets; direction, gap, padding, align, justify, width/height, hide_if_empty; `remove` releases it |
| move / resize / scale | target; x/y/relative **or** width/height (+ `keep_aspect`; one side alone leaves the other except on imported images) **or** `value` factor (or per-axis `x`/`y`; negative factors mirror) |
| rotate / opacity / blend | target, value |
| align | target, alignment, margin |
| constrain | target, constraints object |
| select | shape, shape-specific coordinates/color/target/asset; mode, feather |
| mask | target, action; path for import |
| effect | target, name, amount; seed, radius, strength, black/white, points, shadow_color/highlight_color; luminance, chroma, search (denoise) |
| effect-set / enable / disable / remove | target, effect ID or 1-based index; amount etc. for set |
| variable | name, value; or delete: true |
| preset-save / preset-apply | name, target; overrides for apply |
| canvas | width, height, background; or `size`/`preset` (named size) with orientation, bleed, dpi; or dpi alone |

History transitions and project lifecycle use explicit methods / commands, not editing operations. Provider results are recorded as `ai-result` / `ai-mask` audit events; those audit events are not public operation types. History snapshots and embedded assets reproduce their pixels without recontacting a provider.

## `.vixl` format, version 2

A ZIP archive contains `project.json`, `assets/<sha256>.<png|jpg|webp>`, `masks/<sha256>.png`, and optionally `fonts/<sha256>.ttf`. Imported PNG, JPEG and WebP files keep their original bytes (orientation is applied when decoding); other formats are normalized to PNG. Image members are stored without recompression. All members are checksummed. No archive paths are extracted to disk. Version 1 archives (complete snapshots in every revision) still load; saving writes version 2.

The manifest stores current state, stable object IDs, the history DAG (each revision holds either a full `state` snapshot or a `delta` from its parent; squashed revisions are marked `squashed`), branch/checkpoint references, redo stack, and an optional open transaction. Image bytes are shared between revisions by content hash. Asset hashes identify bytes; revision and object IDs are intentionally unique, not pixel-deterministic. Archive timestamps/IDs are not intended for byte-identical builds.

Rendering resolves variables and acyclic layout constraints, loads source layers, crops/resizes/flips/rotates, applies effects with their captured selection masks, applies the layer mask and opacity, then composites bottom-to-top. Raster sources and text stay editable. Layer masks are defined in transformed local bounds; effect selections are defined in canvas coordinates. Blur spreads a layer past its box instead of being cut off at it (the mask's edges continue over that margin; at the canvas edge the layer's edge pixels continue, so a full-bleed photo does not fade), unless a later effect in the stack depends on the image's size or position (wave, noise, vignette, contrast, artistic filters), which keeps the stack within the box as before. Group members draw past the group's box. These conventions are explicit so scripts can reason about moving a selected/filtered layer.

Default text size tracks the text's rendered bounds. Explicit resize turns off automatic sizing; editing text turns it back on. Imported fonts are embedded. PNG/SVG share HarfBuzz shaping and outlined glyph layout, rendered through resvg for pixel output; see [artistic filters and SVG policies](artistic-filters.md). The bundled default font makes supported text independent of host font installation. Pin font and imaging-library versions for reproducible builds.

History is state-based (deltas plus periodic snapshots), not a replay engine. Undo, checkpoints, branching and comparison use captured state and assets. AI replay is a separate network operation and may vary with provider/model revisions even when a seed is retained.

## Reusable design data (0.11)

New shared operations are `palette-apply` (`name`, optional `prefix`), `template-apply` (`name`, optional `variables`), `guidance` (`name`, optional `text`, `style`, `delete`), and `font-register` (`name`, imported font `asset`). Guidance and registered font references are embedded in the document state and participate in undo/history. Template operations use the normal validation boundary and execute atomically. `shape` accepts the expanded catalog and `shape:"path"` with a bounded single-contour SVG command string in `path`. See [resource and path semantics](agent-resources.md).

## Sizes, layouts, color, brushes and timelines (0.13)

| Operation | Fields |
| --- | --- |
| canvas | `size` or `preset` (named size), `orientation` (portrait/landscape), `bleed` (true or amount in the size's unit), `dpi`, `background`; or `width`/`height`; or `dpi` alone |
| layout-apply | `name`; content `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items`, `image` (asset ID); `seed`, `palette` (name or colors), `colors` (role overrides), `mode`, `type_scale`, `base_size`, `density`, `align`, `accent`, `mark`, `font`, `display_font`, `transparent`, `uppercase_labels`, `prefix`, `replace` |
| type-scale | `base` (px), `ratio` (name or number), `prefix`, `color` — defines character styles caption … display |
| palette-generate | `name`, `color`, `scheme` (`scale` or a harmony), `count` |
| paint-layer | `name`, `width`, `height`, `x`, `y` |
| paint | `target` (paint layer; omitted → active paint layer or a new one), `brush`, `points` [[x, y(, pressure)]] or `path` (SVG), `pressure`, `space`, `size`, `color`, `opacity`, `mode` (paint/erase), `seed`, `settings` (brush overrides) |
| paint-clear | `target`, `last` (N strokes; omitted → all) |
| brush-define | `name`, `base` (built-in brush), `settings`, `description` |
| timeline-set | `duration`, `fps`, `loop`, `clear` |
| keyframe | `target` (layer or `canvas`), `property`, `time`, `value`, `easing` |
| keyframe-remove | `target`, optional `property`, `time` |
| animate | `target`, `property`, `to`, optional `from`, `start`, `end` or `duration`, `easing` |
| animate-preset | `target`, `preset`, `start`, `duration`, `easing`, `amount`, `distance`, `fade`, `to` |
| marker | `name`, `time` or `delete` |

New document state: `canvas.size`, `canvas.dpi`, `canvas.physical`, `canvas.bleed` and `canvas.safe` (pixels) with generated `trim-*`/`safe-*` guides; `layout` (the last applied layout's choices and layer IDs); `brushes` (custom brush definitions); paint layers (`type: "paint"`, `surface`, `strokes`); and `timeline` (`duration`, `fps`, `loop`, `markers`, `tracks` of `{target, property, keys}`). All participate in history and validation like other state. Color fields accept the [color language](color-and-print.md).

## Shapes, guides, text, pages, forms and drawings (unreleased)

| Operation | Fields |
| --- | --- |
| irregular | **`seed`** (or `remove`), `target`/`targets`, `strength`, `amount`, `only`, `wobble`, `wobble_length`, `jitter`, `roughness`, `width_variation`, `pressure`, `lightness_drift`, `chroma_drift`, `hue_drift`, `rotation_jitter`, `scale_jitter`, `position_jitter` — [irregularity](irregular.md) |
| tear | **`seed`** (or `remove`), `target`, `as`, `edges`, `strength`, `depth`, `length`, `roughness`, `rim_width`, `rim_color`, `fibres`, `fibre_width`, `fill`, `name`, `x`, `y`, `width`, `height` — [torn edges](irregular.md#tear) |
| organic | `preset` or `parts`, `params`, `colors`, `fill`, `stroke`, `stroke_width`, `seed`, `naturalness`, `name`, `x`, `y`, `width`, `height`, `target` (regrow) — [organic shapes](organic.md) |
| guide | `name`, `kind` (`axis`, `line`, `ray`, `segment`, `point`, `circle`, `path`) and its geometry, `delete` — [guides](guides.md) |
| grid | `name`, `kind` (`columns`, `baseline`, `thirds`, `golden`, `armature`, `golden-spiral`, `polar`, `isometric`, `triangular`, `hex`, `oblique`, `perspective`), kind settings, `region`, `delete` |
| place / snap | `targets`, `guide`, `at`, `start`/`end`, `spacing`, `with`, `index`, `anchor`, `orient`, `rotate`, `offset`; `snap`: `tolerance` |
| rich-text | `markdown` or `spans` + `paragraphs`, `name`/`target`, `font`, `size`, `color`, `align`, `width`, `height`, `fit`, `line_height`, `paragraph_spacing`, `list_indent`, `x`, `y` — [rich text](rich-text.md) |
| text-style | `target`, `match`/`occurrence` or `start`/`end`, character styles, `clear`, `paragraphs` with paragraph settings — parts of a text layer; use `text-set` for the whole layer's text, color, size or font |
| page | `action` (`add`, `select`, `remove`, `move`, `set`), `page`/`name`, `after`/`before`/`index`, `duplicate`, `master`, `notes`, `background`, `variables`, `hidden`, `transition`, `rename`, `select` — [pages](slides.md) |
| master | `action` (`add`, `select`, `remove`, `set`), `name`, `from`, `background`, `rename` |
| field / field-set | `kind`, `name`/`target`, `key`, `label`, `label_layer`, `group_label`, `required`, `read_only`, `default`, `max_length`, `comb`, `format`, `pattern`, `message`, `options`, `editable`, `option`, `on_value`, `tab`, `overflow`, `min_size`, `font`, `size`, `color`, `align`, `padding`, `appearance`, `x`, `y`, `width`, `height` — [forms](forms.md) |
| form | `tab_order`, `entry_font`, `title`, `lang` |
| drawing | `action` (`import`, `clean`, `vectorize`, `straighten`, `smooth`, `fill`, `stroke`, `restyle`), `asset`/`path`, `name`/`target`, `strokes`, `points`, `color`, `settings`, `x`, `y`, `width`, `height` — [hand drawings](drawing.md) |

Every operation also accepts `page` (a page name or number) in a multi-page document.

## Bulk edits and resizing a whole layout (unreleased)

Repetitive work (menus, badge sheets, price tags, a campaign in six sizes) should not cost one call per layer.

| Operation | Fields |
| --- | --- |
| edit-layers | `where` (selector), `do` (an operation or a list of up to 20), `dry_run`, `expect` |
| adapt-layout | without `targets`: `size` **or** `width` + `height`, `orientation`/`dpi`/`bleed` (named print sizes), `scale` (`fit`, `fill`, `width`, `height` or a number), `anchors`, `where`, `text` (`scale`/`keep`), `report`; with `targets`: the existing vertical reflow (`targets`, `width`, `height`, `margin`, `gap`) |

**`edit-layers`** runs `do` once for every layer on the active page that matches `where`, with `target` set to the layer, atomically with the rest of the batch. Every key of `where` must match; values may be lists (any of):

| Key | Matches |
| --- | --- |
| `role` | the layer's intent role (`content`, `decoration`, `background`) or a named role bound with `role-set` |
| `name`, `name_regex` | a case-insensitive glob (`badge-*`, `price-?`) or a regular expression on the layer name |
| `kind` (or `type`) | the layer type: `text`, `shape`, `raster` (`image`), `group`, `solid`, `gradient`, `frame`, … |
| `shape` | the shape kind of shape layers (`ellipse`, `rounded-rectangle`, …) |
| `tag` | a label set with `layer-intent` `tags` |
| `group` | every descendant of that group |
| `text_contains`, `text_regex` | text layers whose text contains / matches (regexes read the first 2,000 characters) |
| `id` | exact layer IDs or names |
| `visible` | `true` / `false` |
| `page` | a page number or name, a list, or `"all"` (default: the active page; the active page is restored afterwards) |
| `not` | a `where` object to exclude |

```json
{"type":"edit-layers","where":{"kind":"text","name":"price-*"},"do":{"type":"text-set","color":"#c0392b","size":28}}
{"type":"edit-layers","where":{"tag":"badge"},"do":[{"type":"layer-style","name":"drop-shadow","settings":{"blur":6}},{"type":"opacity","value":0.9}]}
```

Unknown `where` keys, unknown kinds and invalid regexes are errors with suggestions; `do` operations are validated (and normalized) once up front, so a typo fails before anything is applied. `do` cannot create layers or change the whole document (`text`, `shape`, `canvas`, `layout-apply`, …) and must not name a `target` or `page`. The result reports `edit_layers: [{matched, layers, pages?, dry_run?}]` (one entry per `edit-layers` operation, in order); a selector that matches nothing adds a warning. `expect: N` fails the batch unless exactly N layers match, which guards a selector against being too wide or too narrow; `dry_run` on the operation only counts and names the matches, and the batch-level `dry_run` (`vixl_operations_apply(dry_run=true)`) previews the whole edit without saving. `layer-intent` also takes `tags` (replacing the layer's labels), so a pattern can tag layers once and later edits select them by tag.

**`adapt-layout`** (proportional mode) resizes the canvas, then re-lays out every top-level layer, so one design can be carried to another size and the result checked at once:

- sizes scale uniformly by `scale` (default `fit`, the smaller of the two ratios, so nothing leaves the canvas); text scales its font size and the box of wrapping text; `text: "keep"` leaves font sizes alone;
- along each axis a layer is anchored from where it sat in the old canvas: in the first or last third it keeps its (scaled) margin to that edge, in the middle third it keeps its relative position, and a layer spanning at least 90% of the axis stretches with the canvas. Groups, rotated layers and auto-sized text are never stretched; a full-canvas photo is scaled to cover instead of distorted;
- `anchors` overrides this for layers named by glob, `role:NAME`, `kind:TYPE` or `tag:NAME` (first match wins) with `top-left`, `top`, `top-right`, `left`, `center`, `right`, `bottom-left`, `bottom`, `bottom-right`, `stretch`, `stretch-x`, `stretch-y`, `cover` or `keep`; `where` limits the layers that are adapted;
- layers with constraints keep them: numeric values follow the axis ratio and `canvas.edge±N` offsets follow the scale, so constraint-driven layouts stay constraint-driven;
- pixel and field layers keep their size (reported under `skipped`). Multi-page documents are not supported yet. Guides that are not part of a named size stay where they are.

The result adds `adapt_layout: [{canvas: {from, to}, scale, adapted, moved, layers: [{layer, from, to, anchor, font_size?}], skipped?}]` (up to 60 layers; `report: false` omits the list), and the usual `warnings` flag layers that ended up cut off or overflowing. Adapt a document to several sizes in one call with `vixl_adapt_layout(sizes, directory, name, options, formats)`: each size becomes a saved (and optionally exported) copy, the source is untouched, and the reply lists per size the new canvas, scale, moved count and warnings.

Without `targets` the verb is proportional; with `targets` it keeps its earlier meaning (vertical reflow in priority order that refuses content that cannot fit, see [production](production.md)). Mixing the two option sets is an error that says which mode each option belongs to. `vixl apply` (JSON) runs both modes from the CLI.

## What an apply result contains

`success`, `dry_run`, `operations` and `changes`, plus when relevant `warnings`, `normalized`, `layout`/`unfilled_slots` (layout-apply), `paint`, `edit_layers` and `adapt_layout`. `detail` is `brief` (MCP default: per layer ID only `added`/`name`/`type`/`bounds`, or `changed` field names and `bounds`, or `removed`), `compact` (REST and CLI default: the new values of changed fields) or `full` (before/after snapshots; the Python default).

`warnings` lists problems with the layers this call added or changed: text or artwork cut off by the canvas edge (a bleed of up to a quarter of a non-text layer is ignored), text that does not fit its `text-layout` box or spills out of its group, and fields the engine accepted that change nothing for that operation (`radius` on a plain rectangle, `sides` or `inner_radius` on other shapes, `stroke_width` without `stroke`, `angle` on a non-angled gradient, `start`/`end` next to `stops`, `margin` on a centring `align`, unknown keys in an `adjustment`'s `effects`, `preset-apply` overrides naming no effect of the preset). They never fail an edit; `vixl_check` audits the whole document.

