# Understand the document

[Documentation home](README.md) · [First design](getting-started.md)

![Editable design and descriptions of its component layers](assets/generated/document-anatomy.png)

## Master and deliverable

The `.vixl` file is your editable master, a portable ZIP archive holding document state,
embedded assets and branching history. A PNG is a rendered deliverable; exporting it does
not replace the master. Retain both when handing off a project. Supported SVG, PDF and
PowerPoint exports preserve some geometry and text, with explicit appearance fallbacks.
To review a master in Git, `vixl unpack design.vixl design-source` writes its current state as a
readable `project.json` with content-addressed assets, and `vixl pack` rebuilds a `.vixl` from it;
undo history is not kept ([commands](commands.md#reviewing-editable-projects-in-git)).

The public interfaces share canonical JSON operations. A CLI command compiles to the same
operation engine used by `Project.apply`, MCP and REST. Their persistence differs: CLI and
MCP edits autosave; direct Python requires `save`. Services restrict local file access;
import files through the relevant interface instead of passing unrestricted paths.

## Layers, order and coordinates

Layers are stacked bottom to top. They may be images, text, shapes, groups, paint, pixel
grids, adjustments or form fields. Give them useful names; use immutable `lyr_…` IDs when
names could change during a long automation. Most operations use the active layer if
`target` is omitted, so explicit targets make scripts easier to understand. Operations on
existing layers also take `targets`, a list: per-layer operations (opacity, move, effects …)
apply to each, joint ones (group, align, distribute) treat them together; see
[operations](operations.md). Opacity is always 0–1 (`"70%"` also works).

The canvas origin is top-left. Positive x moves right; positive y moves down. Positions
and dimensions are pixels. Print metadata adds physical dimensions and dpi; it does not
turn ordinary coordinates into inches. A 300 dpi, 1-inch gap is 300 px. Groups introduce
local coordinates; inspect resolved bounds after grouping, rotation or constraints, or pass
`space: "canvas"` (move, and shape/text edits with `target`) and pivot `units: "canvas"` to work
in document coordinates. A new group takes its topmost member's slot in the stack unless
`group` names `above` or `below` a layer. The `group` result lists each member's offset from
the group's top-left corner (`groups[].members`, `{name: [dx, dy]}`), and edit results for a grouped
layer name its `parent` and add `canvas_bounds` beside the group-local `bounds`
(`coordinate_space: "parent"`).

Stacking inside groups follows three rules:

- A group draws as one picture at its own slot among its siblings; everything inside it is
  above the layers below the group and below the layers above it, however deep it is nested.
- Children stack among themselves, bottom to top, in their order in the layer list. `raise`,
  `lower`, `top`, `bottom` and `reorder` move a layer only among its siblings (the layers with the
  same parent); `reorder` refuses a layer from another group.
- A layer cannot sit between two layers of another group. To put a part of one group in front
  of a part of another, move it out of its group (`reparent`, or `ungroup`), or split the group in two.
  `ungroup` keeps every child where it was drawn, also over time: a group's animation (position,
  rotation, scale, size, visibility, and opacity on a group of one) becomes per-frame keys on its
  children, and an animation that cannot be rewritten exactly is refused with the tracks named.

`move` changes position, `resize` changes dimensions and `scale` uses a factor (`0.8`
means 80%). Procedural shapes retain geometry. Raster images have a fixed original
resolution; enlarging them cannot recover detail. Text wraps and fits through
`text-layout`, rather than stretching its pixels.

## Position versus relationship

`align` places a layer once. `constrain` retains a relationship so future changes can
reflow. Absolute movement or alignment clears constraints on that layer.

```json
{"type": "constrain", "target": "title", "constraints": {
  "center-x": "canvas.center-x", "top": "canvas.top+60"
}}
```

Use one anchor per axis. Constraints may reference canvas edges, sibling layers or guides;
cyclic dependencies fail validation. Guides are metadata and do not appear in normal exports.
Named layouts create ordinary layers, color roles, grids and type scales; fill their required
copy slots before checking. [Sizes and layouts](sizes-and-layouts.md) explains seeds and slots.

## Assets, masks and effects

Imported images, fonts and masks can be embedded, making the master portable. The source
photo is not overwritten. Linked files are a separate, explicitly trusted mode; see
[architecture](architecture.md) for loading and service restrictions.

Effects remain in a stack that can be edited, disabled or removed. A mask controls layer
visibility: white reveals, black hides. Selection state affects an effect **when it is
added**; clear the selection for whole-layer effects. Rasterizing, merging or flattening layers
bakes editable detail into pixels (the originals stay in the new layer's `provenance`, and undo
restores them); keep a checkpoint first.

## Variables, swatches and styles

Use `${headline}` for variable text, and `@accent` for a named color swatch. Variables
allow content changes without rebuilding geometry; render overrides leave the saved master
unchanged. Undefined variables fail rather than silently becoming blank; write `$${headline}` for the literal
text `${headline}`. Font roles,
linked text styles and palettes let repeated elements follow shared choices.

Placeholders take filters, applied left to right: `${name|upper}`, `lower`, `title`,
`${company|default:Independent}` (used when the variable is undefined or empty),
`${state|map:states}` (looks the value up in a document map defined with `variable-map`; a `"*"`
entry catches values the map does not list), `${price|number:2}` (thousands separators, 2
decimals) and `${seat|format:03d}` (a Python format spec). An unknown filter or an undefined map is a
validation error. Text, colours (`${tier|map:tier_colors}`), link variables and merge-impose
templates all substitute the same way, and `inspect` lists every placeholder with its filters under
`placeholders`.

Pages share canvas dimensions and resources but have their own layers and settings.
Masters draw underneath pages that use them. Artboards offer alternate canvases or subsets;
timeline frames are poses over time; pixel frames are saved sprite states. Choose the model
that fits the output instead of duplicating unrelated documents.

## History and verification

Atomic operation batches create an all-or-nothing change. A checkpoint names a revision;
undo/redo moves through history; branches retain alternate directions. Persistent
transactions combine CLI commands into one committed edit. Shared-file locks serialize
writes, but transactions do not isolate independent clients: use separate branch documents
for simultaneous work. [Studio](studio.md) explains branch merging and project groups.

Inspect answers “what is in the document?” Checks answer “does it satisfy these rules?”
Preview answers “does it look right?” Use all three. Bounds checks cannot establish
legibility, provider quality or an artistic outcome; saved suites cover their declared
rules and sample times. [Production workflows](production.md) explains coverage and repairs.

Defaults include 40 MP per canvas/layer, 16,384 px per side, 4,096 layers and 10,000 operations
per batch. See [architecture](architecture.md#resource-policy) for the complete resource policy
and [coverage](coverage.md) for unsupported features.
