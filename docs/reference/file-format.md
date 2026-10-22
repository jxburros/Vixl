# The `.vixl` file format

[Documentation home](../README.md) · [Converting older documents](converting.md) · [Exporting](../guides/output/exporting.md)

A `.vixl` document is a ZIP archive: one JSON member, `project.json`, holding the document model and its history,
plus the binary files that model references. Nothing in it is executable, and every member is named by its content
hash, so a document can be read, diffed, generated or repaired by other tools without Vixl.

The JSON is described by a published JSON Schema (draft 2020-12),
[`src/vixl/data/vixl-document.schema.json`](../../src/vixl/data/vixl-document.schema.json). Print it with
`vixl schema document`; in Python, `vixl.document_schema.document_schema()` returns it and
`vixl.document_schema.validate_manifest(value)` lists a `project.json` value's problems. The schema is generated from
the engine's own constants and field registry, and the test suite checks every `.vixl` file in the repository against
it (except the older releases' documents the [conversion kit](converting.md) is tested on) and fails when the code uses a layer or document field the schema does not describe.

```bash
vixl schema document > vixl-document.schema.json
```

## Archive layout

| Member | Contents |
| --- | --- |
| `project.json` | The manifest below (UTF-8 JSON, deflated). |
| `assets/<sha256>.<ext>` | Images of raster and frame layers (PNG, JPEG, WebP …) and audio (`.wav`). |
| `masks/<sha256>.png` | Layer masks, effect selections and the pixel selection (8-bit alpha PNGs). |
| `fonts/<sha256>.<ext>` | Embedded font files (`.ttf`, `.otf`), registered by name in `state.fonts`. |
| `sources/<sha256>.svg` | The original SVG of an appearance-mode SVG import (kept for provenance, never rendered). |
| `emoji-sources/<sha256>.<ext>` | Masters of custom emoji (`.vixl` or `.png`), inert. |

Every member other than `project.json` lives in one of those five folders, its name is the SHA-256 of its bytes plus
an extension, and `project.json`'s `asset_hashes` lists exactly those members with their hashes. Vixl refuses an
archive with any other member, a duplicate or unsafe name, a hash mismatch, or more than the resource limits allow
(see [limits](#limits)). A member that no revision references any more is dropped on the next save. Image members
are stored uncompressed (they are already compressed); `project.json` and fonts are deflated.

## The manifest (`project.json`)

```json
{
  "format_version": 2,
  "vixl_version": "0.30.0",
  "state": {
    "canvas": {"width": 400, "height": 300, "background": "#ffffff", "color_mode": "rgba8"},
    "layers": [
      {"id": "lyr_fabf55c98c3bc34a", "name": "title", "type": "text", "parent": "lyr_fef4caa18a7d242e",
       "x": 0, "y": 0, "width": 122, "height": 38, "rotation": 0, "flip_x": false, "flip_y": false,
       "opacity": 1.0, "blend": "normal", "visible": true, "effects": [], "mask": null, "constraints": {},
       "text": "Hello", "font": "DejaVuSans.ttf", "size": 48, "color": "#1d3557", "align": "left",
       "auto_size": true, "line_height": 1.0, "spacing": -8},
      {"id": "lyr_fef4caa18a7d242e", "name": "badge", "type": "group", "parent": null,
       "x": 40, "y": 40, "width": 320, "height": 200, "content_width": 320, "content_height": 200,
       "rotation": 0, "flip_x": false, "flip_y": false, "opacity": 1.0, "blend": "normal", "visible": true,
       "effects": [], "mask": null, "constraints": {}}
    ],
    "active_layer": "lyr_fef4caa18a7d242e",
    "selection": null,
    "variables": {},
    "presets": {}
  },
  "nodes": {"rev_2c723eb25d1c42d0": {"id": "rev_2c723eb25d1c42d0", "parent": null, "operations": [],
                                     "label": "Create document", "state": {"…": "a full state"}}},
  "head": "rev_2c723eb25d1c42d0",
  "branches": {"main": "rev_2c723eb25d1c42d0"},
  "checkpoints": {},
  "current_branch": "main",
  "redo_stack": [],
  "transaction": null,
  "asset_hashes": {}
}
```

| Field | Meaning |
| --- | --- |
| `format_version` | Archive format version: 2. Any other value is refused; format-1 archives (0.10 and earlier) open after [`vixl convert`](converting.md). |
| `vixl_version` | The Vixl release that saved the file (informational). |
| `state` | The current document: the canvas, layers and every document-level resource. It is always equal to the state of the `head` revision. |
| `nodes`, `head`, `branches`, `checkpoints`, `current_branch`, `redo_stack`, `transaction` | The [history](#history). |
| `asset_hashes` | `member name → SHA-256` for every other archive member. |

## Document state

`state` always has `canvas`, `layers`, `active_layer` (a layer ID or null), `selection` (a `masks/` member or null),
`variables` and `presets`. Everything else is optional and appears when a feature uses it: `fonts`, `typography`,
`swatches`, `palettes`, `pages` and `masters`, `timeline`, `symbols`, `artboards`, `guides`, `grids`, check `suites`
and many more. The schema lists every key with a description (`$defs/state`).

The **canvas** holds `width` and `height` in pixels, `background` (a colour, `transparent` for none) and
`color_mode` (always `rgba8`), and for named and print sizes `size`, `dpi`, `bleed`, `safe` and `physical` (the trim
size in inches, millimetres, centimetres or points).

**Colours** are strings anywhere in the document: CSS names and functions, `#hex`, `@swatch` references to
`state.swatches`, modifiers such as `lighten(@brand, 10%)` and `${variable}` references. Vixl resolves them when
it draws.

## Layers

`state.layers` lists the layers bottom to top. Every layer has the common fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable ID (`lyr_` and 16 hex digits); unique, never reused, and what other layers refer to. |
| `name` | Unique, non-empty name. Operations address layers by ID or name. |
| `type` | `raster`, `text`, `solid`, `gradient`, `shape`, `group`, `frame`, `adjustment`, `pathfinder`, `symbol`, `pixel`, `paint`, `field` or `link`. |
| `x`, `y`, `width`, `height` | The unrotated box in pixels: canvas pixels for a top-level layer, the parent group's content pixels for a child. |
| `rotation`, `flip_x`, `flip_y` | Clockwise degrees around the pivot (`pivot`, default the box centre) and mirroring. `skew_x`, `skew_y` and an exact `affine` matrix are optional. |
| `opacity`, `blend`, `visible` | 0–1 opacity, blend mode (`normal`, `multiply`, `screen`, `overlay`, `darken`, `lighten`, `difference`, `add`, `subtract`) and visibility. |
| `effects` | The effect stack: `{id, name, enabled, selection, amount, …}`, applied in order in the layer's own frame before flip, rotation and skew. |
| `mask` | `null` or `{asset: "masks/<sha256>.png", enabled}`. |
| `constraints` | Layout constraints (anchors to the canvas or other layers). |

The rest depend on the type. The main ones:

| Type | Fields |
| --- | --- |
| `shape` | `shape` (rectangle, rounded-rectangle, capsule, ellipse, line, polygon, star, path or a catalog shape), `fill`, `fill_gradient` (a gradient fill spanning the box, with the gradient layer's `start`/`end` or `stops`, `direction`, `angle`, `center`, `falloff`; `fill` then holds its middle colour), `stroke`, `stroke_width`, `radius` (pixels, a percentage string such as `"25%"` of the shorter side, or four corner radii `[top-left, top-right, bottom-right, bottom-left]`), `sides`, `inner_radius`; paths store SVG path data in `path` within a `path_view` box `[w, h]` that is stretched to the layer. Stroke details: `line_cap`, `line_join`, `dash` (with `dash_fit`, default true: the pattern fitted to corners), markers, trims and `stroke_align` (`inside`, `center` or `outside`; unset it is `inside` for closed shapes, flush with the outline, and `center` for paths, arcs, lines and open shapes). |
| `text` | `text`, `font` (a `state.fonts` name, a `fonts/` member or the bundled `DejaVuSans.ttf`; the typography role it follows is `font_role`), `size` in pixels, `color`, `align`, `line_height`, `spacing`, `tracking`, `auto_size` (the box follows the text) or `text_layout` (a fixed box it wraps in), and `rich` for styled spans. Text stays live: it is laid out with the embedded font each time the document is drawn. |
| `solid` | `fill`. |
| `gradient` | `start` and `end` or `stops` (`[{offset, color}]`), `direction` (horizontal, vertical, radial, angled), `angle`, `center`, `falloff`. |
| `raster`, `frame` | `asset`: an `assets/` member drawn into the box. |
| `group` | `content_width`, `content_height`: the coordinate space of its children, which name it in `parent`. The group's box scales that space, so resizing a group scales its contents. Groups do not clip. Charts, tables, objects and characters are groups with a record (`chart`, `table`, `object`, `character`); a group made by `radial-repeat` keeps `radial` (`count`, `center`, `sweep`, `start_angle`, `mirror`). |
| `pathfinder` | `mode` (union, subtract, intersect …) and the `operands` it combines. |
| `symbol` | `symbol`: the name of a master in `state.symbols`. |
| `pixel` | `pixels` (rows of palette keys) and `palette`. |
| `paint` | `strokes`: recorded brush strokes. |
| `field` | `field`: a form field record (key, kind, label, options …). |
| `link` | `source`: a path to another `.vixl` file, relative to this document, with `fit`, `crop`, `source_page`. |
| `adjustment` | Only `effects`; they apply to what is beneath. |

Optional fields on any layer include `clip` (the ID of the layer whose alpha clips it), `styles` (drop-shadow, stroke,
outer-glow, color-overlay, gradient-overlay), `repeat`, `alt` and `decorative` (accessibility), `role`, `tags`, and
intent flags read by the checks (`allow_overlap`, `allow_crop` …). The schema's `$defs/layer` lists every field
(it rejects fields it does not know).

## Groups and nesting

A child layer names its group in `parent`. Children keep their place in `state.layers` (bottom to top within the
group); a group sits above its children. A child's `x`, `y`, `width` and `height` are in the group's content space
(`content_width × content_height`), which the group's own box maps onto the page, so nesting composes. Groups nest at
most 15 deep.

## Pages and masters

A multi-page document has `state.pages`, a list of `{id, name, notes, master, background, variables, hidden,
transition, content}`, and `state.page`, the active page's ID. The active page's content (its `layers`,
`active_layer`, `selection`, `timeline`, `symbols`, `artboards` and the other page-scoped keys) lives at the top level
of `state`; every other page keeps it in its `content`. `state.masters` maps a master name to `{background, content}`;
a page with `master` draws that master's layers underneath its own.

## Assets and fonts

Layers refer to archive members by name (`assets/…`, `masks/…`). Fonts are registered by name in `state.fonts`
(`name → fonts/<sha256>.ttf`), and a text layer's `font` is such a name, the `fonts/` member itself (what the
operations store) or the bundled `DejaVuSans.ttf`. A layer that follows a typography role (`heading`, `body`) names it
in `font_role`; `state.typography` maps the role to a registered font, and the layer's `font` follows it when the
typography changes. `state.font_fallbacks` lists font members tried for glyphs the main font lacks. Fonts are
embedded so a document renders the same on any machine.

## History

Every applied batch of operations is a revision in `nodes`, keyed by ID: `{id, parent, operations, label}` plus
either a full `state` snapshot or a `delta` from its parent's state. The root revision and every 32nd revision on a
chain store a snapshot; the others store deltas, so the history stays small. Revisions form a DAG: `branches` maps a
branch name to its tip, `checkpoints` maps a checkpoint name to a revision, `head` is the current revision,
`current_branch` the checked-out branch, `redo_stack` the revisions undo stepped back over and `transaction` an open
transaction (`{state, operations}`) or null. History holds at most 2,000 revisions; older ones are compacted
(`squashed`).

A tool that only reads or writes the current design can ignore the history: read `state`, and when writing a new
document give it one root revision whose `state` equals the top-level `state`
(`{"id": "rev_…", "parent": null, "operations": [], "label": "Create document", "state": …}`) with `head` pointing at
it.

## Limits

When it opens a document Vixl checks the archive before decoding anything: at most 256 MiB on disk and expanded,
10,000 members, 64 MiB per asset, 64 fonts and 160 million decoded pixels across all images; at most 4,096 layers per
page, canvases up to 16,384 px a side and 40 million pixels. Then it validates the state and verifies that the
history is acyclic and every reference resolves. History is checked before it is rebuilt: the snapshot a revision
starts from holds at most 4,096 layers, a revision is at most 64 deltas from its nearest snapshot (Vixl itself
stores a snapshot every 32), and a list delta names each layer once, names no layer it neither keeps nor adds, and
holds no more items than the layer limit. A file that breaks one of these is refused with `invalid_project`.

## Documents from earlier releases

This release reads only format 2 and the current fields. A document saved by an earlier release (format 1, a
layer `lookup` field, `upgraded_from`, house-style versions, recipes from before 0.23, strokes placed by the old
rule) opens after a one-time [`vixl convert`](converting.md), which rewrites it for the current code, keeps its look
and reports every change.

## Other formats

- [Exporting](../guides/output/exporting.md) covers PNG, SVG, PDF, PPTX, PSD and HTML. Vixl's own SVG embeds this document model, so
  importing it back gives the same editable layers ([SVG round trip](../guides/output/exporting.md#svg-round-trip)). It names the
  archive's fonts instead of storing them; the import finds them again.
- [Reviewing projects in Git](commands.md#reviewing-editable-projects-in-git) unpacks a document into a folder of
  readable files and back.
