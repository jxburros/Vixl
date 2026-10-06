# Operations and document semantics

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

See [spacing checks and pixel animation](pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

`vixl schema` or REST `GET /schema` returns the full Draft 2020-12 JSON Schema. MCP exposes the same schema at `vixl://operations`. Every editing operation is schema-checked before I/O, then validated against the document and resource limits.

```json
{"operations":[
  {"type":"add","path":"portrait.png","name":"portrait"},
  {"type":"resize","target":"portrait","width":800},
  {"type":"align","target":"portrait","alignment":"top-right","margin":40},
  {"type":"select","shape":"rect","x":0,"y":0,"width":500,"height":300},
  {"type":"effect","target":"portrait","name":"brightness","amount":15},
  {"type":"mask","target":"portrait","action":"from-selection"}
]}
```

`Project.apply` accepts a single operation, an array, or an `operations` envelope. The complete batch succeeds or none of its state/assets/history changes do. File reads may occur during validation; dry-run never saves or changes the live project. Dry-run returns the same before/after document changes that a real apply would make. Generated IDs in separate dry-run and apply calls need not match.

Operations are normalized before validation (see [interfaces](interfaces.md#forgiving-input-and-actionable-errors)): legacy `operation`/`layer` keys, type aliases (`set_opacity`, `rect`, `circle`, `add-text`, `drop_shadow`, …), camelCase keys, field aliases (`font_size`, `fill`/`color`), opacity percentages and CSS colors. Each rewrite is reported in the result's `normalized` list. Geometry fields `x`/`y` accept pixels, `"center"` or `"N%"`; `width`/`height` accept pixels or `"N%"`, relative to the canvas or the target's parent group. Unknown fields, malformed dimensions, nonfinite numbers, and unknown types are still rejected, with the failing operation index, field, allowed values and suggestions in the error.

Common operation fields:

| Type | Fields |
| --- | --- |
| add | path **or** embedded asset; name, x, y, linked |
| solid / gradient | name, width, height, color **or** start/end/direction |
| text | text, name, font, size, color, align, spacing, x/y |
| text-set | target; text, size, color, align, spacing, stroke_width/stroke_color |
| move / resize / scale | target; x/y/relative **or** width/height **or** value factor |
| rotate / opacity / blend | target, value |
| align | target, alignment, margin |
| constrain | target, constraints object |
| select | shape, shape-specific coordinates/color/target/asset; mode, feather |
| mask | target, action; path for import |
| effect | target, name, amount; seed, radius, strength, black/white, points, shadow_color/highlight_color |
| effect-set / enable / disable / remove | target, effect ID or 1-based index; amount etc. for set |
| variable | name, value; or delete: true |
| preset-save / preset-apply | name, target; overrides for apply |
| canvas | width, height, background; or `size`/`preset` (named size) with orientation, bleed, dpi; or dpi alone |
| link | **source** (a workspace `.vixl`); name, x, y, width, height, fit (`fill`/`fit`/`stretch`), position, crop, artboard, source_page, variables. A live [linked document](linked-documents.md). With `target` instead of `source` it changes that link (`null` clears a setting) |
| link-refresh / link-embed | target (link-refresh: omit for every link); link-refresh records the revision a link has seen, link-embed freezes the link into an image |

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
| organic | `preset` or `parts`, `params`, `colors`, `seed`, `naturalness`, `name`, `x`, `y`, `width`, `height`, `target` (regrow) — [organic shapes](organic.md) |
| guide | `name`, `kind` (`axis`, `line`, `ray`, `segment`, `point`, `circle`, `path`) and its geometry, `delete` — [guides](guides.md) |
| grid | `name`, `kind` (`columns`, `baseline`, `thirds`, `golden`, `armature`, `golden-spiral`, `polar`, `isometric`, `triangular`, `hex`, `oblique`, `perspective`), kind settings, `region`, `delete` |
| place / snap | `targets`, `guide`, `at`, `start`/`end`, `spacing`, `with`, `index`, `anchor`, `orient`, `rotate`, `offset`; `snap`: `tolerance` |
| rich-text | `markdown` or `spans` + `paragraphs`, `name`/`target`, `font`, `size`, `color`, `align`, `width`, `height`, `fit`, `line_height`, `paragraph_spacing`, `list_indent`, `x`, `y` — [rich text](rich-text.md) |
| text-style | `target`, `match`/`occurrence` or `start`/`end`, character styles, `clear`, `paragraphs` with paragraph settings |
| page | `action` (`add`, `select`, `remove`, `move`, `set`), `page`/`name`, `after`/`before`/`index`, `duplicate`, `master`, `notes`, `background`, `variables`, `hidden`, `transition`, `rename`, `select` — [pages](slides.md) |
| master | `action` (`add`, `select`, `remove`, `set`), `name`, `from`, `background`, `rename` |
| field / field-set | `kind`, `name`/`target`, `key`, `label`, `label_layer`, `group_label`, `required`, `read_only`, `default`, `max_length`, `comb`, `format`, `options`, `editable`, `option`, `on_value`, `tab`, `overflow`, `min_size`, `font`, `size`, `color`, `align`, `padding`, `appearance`, `x`, `y`, `width`, `height` — [forms](forms.md) |
| form | `tab_order`, `entry_font`, `title`, `lang` |
| drawing | `action` (`import`, `clean`, `vectorize`, `straighten`, `smooth`, `fill`, `stroke`, `restyle`), `asset`/`path`, `name`/`target`, `strokes`, `points`, `color`, `settings`, `x`, `y`, `width`, `height` — [hand drawings](drawing.md) |

Every operation also accepts `page` (a page name or number) in a multi-page document.

