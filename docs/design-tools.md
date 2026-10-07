# Design tools and template production

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

All edits below are canonical operations, available through Python `Project.apply`, CLI commands/scripts, REST `/operations`, and MCP `vixl_operations_apply`. `vixl schema` describes their fields. Successful edits participate in atomic batches, dry runs, undo/redo, transactions, and `.vixl` persistence. Existing documents remain readable. New design documents require this version of the engine.

## Groups, clipping, shapes, and repeats

```bash
vixl shape ellipse --name sun --width 640 --height 640 --x 564 --y 165 --fill '#e8885c'
vixl layer-style sun gradient-overlay --settings '{"start":"#e8885c","end":"#4853a4"}'
vixl shape rectangle --name stripe --width 700 --height 6 --x 534 --y 190 --fill '#152235'
vixl repeat stripe --count 16 --dy 37 --dh 1
vixl group stripes stripe
vixl clip stripes sun
```

The stripe stays one editable layer. Repeat counts include the original; `dx/dy` are nonnegative offsets between copies and `dw/dh` change each copy's size (per-step turns, scale, opacity, jitter and `merge` make real copies instead: see [below](#per-step-transforms-jitter-and-merged-repeats)). `repeat-blend stripe --count 16 --dy 37 --end '{"height":21,"fill":"#4853a4"}'` interpolates size and RGBA color to the last copy. Reapplying repeat replaces its settings; `--count 1` leaves only the original. Counts are bounded to 512 and all resulting dimensions are checked before allocation.

Shapes support `rectangle`, `rounded-rectangle`, `ellipse`, `polygon`, `star`, `arc`, and `line`; `vixl shape --target NAME --fill COLOR` (JSON `{"type":"shape","target":"NAME",…}`) changes the fill, stroke or geometry of an existing shape in place, keeping its layer ID; options include `--fill`, `--stroke`, `--stroke-width`, `--line-cap`, `--trim-start`/`--trim-end` (draw only part of the stroke, 0–100 %, animatable: see [Drawing a line on](brushes-and-animation.md#drawing-a-line-on)), `--radius`, `--sides`, and star `--inner-radius` (0.01–1). Geometry is retained and redrawn at the layer's current size with bounded antialiasing. Version 0.11.0 adds named shape shortcuts and editable single-contour Bézier paths, plus SVG export of simple geometry. See [design resources and vector export](agent-resources.md) for syntax and raster fallback limits.

### Arcs, pie wedges and donut segments

`shape: "arc"` draws a slice of the ellipse that fills the layer box. `start_angle` and `end_angle`
are degrees, 0 at 3 o'clock and growing clockwise (as SVG and gradient angles do), so -90 is 12
o'clock; the wedge runs clockwise from start to end, an `end_angle` below the start wraps around,
and 360° or more past the start is the full disc or ring (the default when you give no angles).
`inner_radius` (0–0.99, a fraction of the outer radius, default 0) cuts the hole: 0 is a pie wedge,
0.6 a donut segment. Wedges that share one box and differ only in their angles make a pie or donut
chart:

```bash
vixl shape arc --name flat-white --width 300 --height 300 --x 50 --y 50 --start-angle -90 --end-angle 70.6 --fill '#14263b'
vixl shape arc --name drip --width 300 --height 300 --x 50 --y 50 --start-angle 70.6 --end-angle 192 --inner-radius 0.55 --fill '#f2a541'
```

Each wedge is one editable layer; a visible stroke is drawn inside the box, so strokes of
neighbouring wedges meet cleanly. A non-square box gives elliptical wedges. SVG, vector PDF
(`pdf_content: vector`, the default for paged documents) and PowerPoint exports write native curves
(no arc commands, no raster), and the spellings `pie`, `wedge`, `donut`, `ring` and `sector` are
accepted for `shape` (`donut`/`ring` start with an inner radius of 0.6/0.8).
`vixl.wedge.wedge_path(cx, cy, radius, start, end, inner=0, aspect=1)` returns the same outline as
SVG path data for code that draws its own wedges, such as chart layers.

Groups preserve member stacking order and use local child coordinates. Moving, hiding, masking, styling, or changing the opacity of a group affects its combined contents once. Groups nest to 16 dependency levels and duplicate with independent child IDs; edits address children by their existing names or IDs. A group's layout box is the union of member bounds at creation; constraints, alignment, `resize` and `canvas` inside the group use that box. Groups do not clip: members that later move, grow or rotate past the box (an animated limb, a resized sprite) still draw, and scale, flip and rotate with the group. `inspect` adds `drawn_bounds` to a layer that draws past its box. Resizing transforms the combined group raster; a group holding only pixel layers resamples nearest-neighbor, so scaled sprites stay crisp. Constraints between layers and clipping references must stay among siblings; `canvas` inside a group means the group's local content box. Grouping nonadjacent layers places the group at the highest selected slot.

`reparent LAYER… --into GROUP` (`{type: reparent, targets, into}`; aliases `move-into`, `adopt`) moves existing
layers or groups into a group, between groups, or out to the top level with `into: null` (CLI `--into page`), without
ungrouping, so the group keeps its rotation, scale, flips, effects and other settings. With `keep: appearance` (the
default) every target stays where it is drawn: its transform is converted into the new parent's space (a turn or
mirror of the new parent becomes the layer's own rotation and flips; uneven scaling or skew is held in its `affine`
matrix, which goes away again when it moves back), so moving into an unscaled group, or one turned by a right angle or
mirrored, leaves the render pixel-identical, and into a scaled or freely rotated group the geometry is exact up to
resampling. `keep: local` keeps the stored x, y and transform instead. The targets stack on top of the new parent's
children unless `above`/`below` (a child of the new parent) or `index` (0 at the bottom) says otherwise; lifted to the
top level they sit directly above the group they left. The group's content box grows to include them (its size and
position change so nothing moves on the canvas) unless `fit: false`; an animated or constrained group is left as it is,
with a note (groups do not clip). Moving a group into its own descendant, a layer into a non-group or a repeating group,
or a clip pair apart is refused. Animated targets keep their tracks: position keys are shifted when the new parent is
only translated, rotation and scale tracks carry over through any parent, and position or size tracks under a turned or
scaled parent are refused with the tracks named. The whole call is one undoable step.

`clip TARGET BASE` multiplies TARGET's rendered alpha by the sibling BASE's alpha. It follows base transforms and masks, works on groups, and rejects cycles. The base remains an ordinary visible layer. `clip TARGET --release` removes the relationship. `ungroup NAME` restores local members to their parent; reset group appearance and transforms first when ungrouping would discard those settings. A group's timeline tracks (position, rotation, scale, size, visibility, and opacity on a one-layer group) move onto its children as per-frame keys, so the animation looks the same; tracks that cannot be rewritten exactly (effects, mirroring, opacity over several overlapping children, uneven scaling of a rotated child) refuse the ungroup and are named in the error. `remove GROUP` removes its descendants. Reordering always stays among siblings.

## Examples: gradients, glows, shadows and radial repeats

Shapes take a flat `fill`. Gradients, glows and shadows are layer styles or looks on the same layer, so one shape stays one
editable layer. `vixl_operation_schema(types=[...])` returns these (and more) as `examples` next to each operation's fields.

```json
{"type":"gradient","name":"sky","start":"#1e3a8a","end":"#7dd3fc","direction":"vertical"}
{"type":"gradient","name":"sunset","direction":"angled","angle":35,"stops":[{"offset":0,"color":"#f97316"},{"offset":0.55,"color":"#db2777"},{"offset":1,"color":"#4c1d95"}]}
{"type":"gradient","name":"glow-disc","width":400,"height":400,"start":"#fde68a","end":"#00000000","direction":"radial"}
{"type":"layer-style","target":"card","name":"gradient-overlay","settings":{"start":"#6366f1","end":"#ec4899","direction":"angled","angle":45}}
{"type":"layer-style","target":"badge","name":"outer-glow","settings":{"color":"#fde047","blur":18,"opacity":0.9}}
{"type":"layer-style","target":"card","name":"drop-shadow","settings":{"color":"#00000066","dx":0,"dy":12,"blur":24}}
{"type":"radial-repeat","target":"petal","count":12,"cx":"50%","cy":"50%","mirror":true,"name":"mandala"}
```

`look` wraps the common finishes in one operation (`{"type":"look","target":"badge","look":"glow"}`); see [looks](looks.md).

## Radial repeat

`repeat` steps a layer along a line. `radial-repeat` turns it about a point: `count` copies spread over `sweep` degrees
(default 360) around `cx`, `cy` (pixels, `"50%"` or `"center"`; default the canvas, or the parent group, center), each turned
to face outward, starting at `start_angle`. `mirror: true` adds a reflection of every copy across the vertical axis through
the center (the symmetry of a kaleidoscope: `count` 6 makes 12 copies). Copies are ordinary layers (turned about their own
centers and moved onto the circle) inside one group named `name` (default `<layer>-radial`); `group: false` leaves them
loose. At most 360 copies including mirrors. The group records its `radial` settings.

```bash
vixl shape ellipse --name petal --x 380 --y 120 --width 40 --height 150 --fill '#7c3aed'
vixl radial-repeat petal --count 12 --cx 50% --cy 50% --mirror --name rosette
```

### Per-step transforms, jitter and merged repeats

`repeat` and `radial-repeat` also take `rotation_step` (degrees each copy turns more than the one before),
`scale_step` (a factor applied once more per copy, 0.9 = each copy 10% smaller), `opacity_step` (added per
copy, clamped to 0-1), seeded `rotation_jitter`, `scale_jitter`, `position_jitter` and `opacity_jitter`
(`seed`, default 0), and `merge: true`, which draws every copy as one path layer (one per color; shape layers
only). A live `repeat` draws an unrotated strip, so with any of these fields `repeat` makes real copies
instead: a group named `name` (default `<layer>-repeat`) holding the original and its copies, or one merged
path. `dx`/`dy` may then be negative. Copies count against the document's layer limit; `merge` costs one layer.

```json
{"type": "repeat", "target": "badge", "count": 6, "dx": 50, "rotation_step": 15, "scale_step": 0.9, "opacity_step": -0.12, "name": "trail"}
{"type": "radial-repeat", "target": "petal", "count": 16, "cx": "50%", "cy": "50%", "rotation_jitter": 6, "scale_jitter": 0.1, "seed": 3, "merge": true, "name": "bloom"}
```

## Scatter and seamless pattern tiles

`scatter` places copies of one or more motif layers (`source`, a name or a list picked at random per copy) or
of a motif drawn on the fly (`mark`: a shape spec such as `{"shape": "ellipse", "width": 8, "height": 8, "fill":
"#fff"}`, or a built-in `{"mark": "tuft"}`/`{"mark": "flick"}`) over a target layer's outline:

- `placement: inside` (default): Poisson-disc samples inside the outline (holes and even-odd shapes respected),
  at least `spacing` pixels apart; `count` alone sets the spacing from the area. No grid look.
- `placement: along`: evenly along the edge (`spacing` or `count`), pointing out along the normal
  (`direction: normal`), along the edge (`tangent`), in a cone of `spread` degrees around the normal (`cone`) or
  anywhere (`random`); `anchor: base` (the default here) puts each motif's bottom centre on the line, so blades
  and tufts grow out of it; `offset` moves the line out (positive) or in.
- Each copy gets `scale` × (1 ± `scale_jitter`), `rotation` ± `rotation_jitter`, a move up to `position_jitter`
  pixels, a fill from `colors`, and a lightness shift up to `tone_variation` (OKLab L) in `tones` steps.
  `exclude` lists layers whose outlines stay clear (plus `exclude_margin`).
- Output: a group named `name` (default `<target>-scatter`) right above the target, in the target's parent
  group, with copies `NAME/1`, `NAME/2` …; or with `merge: true` one path layer per tone (a group of them when
  there are several), so a thousand marks cost a few layers. Without `merge` the copies count against the
  layer limit, and the error says so. Motif layers are hidden afterwards (`hide_source: false` keeps them).
- `preset: fur` grows tufts in the target's fill along its edge, behind it, and a second merged layer of darker
  inner flicks (`flicks` per tuft, default 0.5) above it; `length` sets the tuft length. The `plush` look does
  the same with a soft gradient, and the organic `fur-blob` preset is a ready furry body.

The result reports `scatter: [{name, copies, spacing, seed, layers}]`, and the first output layer keeps the
recipe under `scatter`.

```json
{"type": "scatter", "target": "card", "source": ["dot", "star"], "count": 60, "seed": 4, "rotation_jitter": 180, "scale_jitter": 0.3, "tone_variation": 0.08, "exclude": ["title"], "merge": true, "name": "confetti"}
{"type": "scatter", "target": "bear", "preset": "fur", "seed": 2}
```

`pattern-scatter` scatters motifs in a `width` × `height` tile (at `x`, `y`, default 0, 0) with toroidal
Poisson-disc spacing: distances wrap across the edges, and a copy that crosses an edge gets a wrapped copy on the
opposite side, so the tile repeats without a seam. `background` adds a colored rectangle under the motifs;
`pattern: NAME` also saves the tile (cropped to its box) as a document pattern for `pattern-fill`. The result
reports `pattern_scatter: [{name, copies, ghosts, spacing, seed, seam}]`, where `seam` is the same
`seamless_check` report `pattern-define` gives (`edge_error` close to `interior_variation` means no visible
seam). The recipe stays on the tile group (`pattern_scatter`): after editing a motif, `{"type":
"pattern-scatter", "target": "tile"}` rebuilds it with the same seed, so the tile re-wraps; any field passed
with it changes the recipe. The group shows wrapped copies past its box on the canvas; the saved pattern is the
cropped tile. Hide the tile once the pattern is saved.

```json
{"type": "pattern-scatter", "source": ["leaf", "dot"], "width": 200, "height": 200, "count": 14, "seed": 11, "rotation_jitter": 180, "background": "#fff7ed", "pattern": "leaves", "name": "tile"}
{"type": "pattern-fill", "target": "ground", "pattern": "leaves", "tile_variation": 0.3}
```

`pattern-fill` and `pattern-stroke` take `tile_variation` (0-1): each repeat of the tile is lightened or darkened
by its own seeded amount (up to 25%), so a large fill does not read as a grid. `pattern-define` reports its seam
check under `patterns` in the result.

## Attached layer styles

```bash
vixl layer-style title drop-shadow --settings '{"color":"#000000","dx":4,"dy":6,"blur":8,"opacity":0.65}'
vixl layer-style title stroke --settings '{"color":"#ffffff","width":2}'
vixl layer-style logo outer-glow --settings '{"color":"#80cfff","blur":12}'
vixl layer-style logo color-overlay --settings '{"color":"@brand"}'
vixl layer-style title drop-shadow --remove
```

Looks (`look`) are named recipes over these styles and the effect stack; a layer remembers which looks it carries so that
`remove` takes one off without touching hand-made styles.

Styles are editable settings, one per kind, applied after effects and masks. `enabled` and `opacity` are shared settings. Shadow, glow, and outer stroke sit behind the content; color and gradient overlays recolor it while preserving alpha. Overlays use the visible silhouette's bounding box. Group/layer opacity is applied to the styled result, then it is composited with the selected blend mode. Shadows and glows extend past the layer's geometric bounds and past a parent group's box. Inspection/alignment report geometry bounds; `inspect` adds `drawn_bounds` when styles, blur or group members reach further. Rasterizing a styled or externally clipped layer requires removing those attachments first.

## Alignment and distribution

```bash
vixl align title left --relative-to logo
vixl align title center-y --targets title logo badge
vixl distribute horizontal title logo badge
vixl distribute vertical first second third --gap 24
```

`align` supports `targets` and `relative_to`: `canvas`, `selection` (the union of the selected bounds), or another sibling's name/ID; with a sibling, `box: "content"` (`--box content`) aligns to its content box, such as a speech bubble's body (see [content boxes](vector-paths.md#content-boxes)). Multiple targets default to selection bounds; one target defaults to the canvas. Distribution sorts by current position. Without a gap it preserves the outer edges and computes equal edge-to-edge spacing, accounting for unequal sizes; with a gap it starts at the first layer. It requires at least three siblings. Both commands bake resolved positions and clear constraints on affected layers.

## Named character styles, paragraph styles, and swatches

```bash
vixl swatch brand '#e8885c'
vixl style-define Heading --settings '{"size":80,"color":"@brand","stroke_width":1}'
vixl style-define Caption --kind paragraph --settings '{"align":"center","spacing":8}'
vixl style-apply title Heading
vixl style-apply title Caption --kind paragraph
vixl swatch brand '#78bbdc'
```

Swatch references use `@name` in color fields. Character styles support size, color, stroke width/color; paragraph styles support alignment and line spacing. Named styles remain linked and take precedence over the layer's corresponding local values. Redefining a style or swatch updates all uses on the next render, including constraint measurements. Resource names use letters, numbers, underscores and hyphens (maximum 100 characters).

## Artboards, data sets, and image frames

```bash
vixl artboard square --preset instagram-square
vixl artboard story --preset story
vixl artboard banner --width 1600 --height 600
vixl render --artboard story --out story.png
vixl export-screens --out screens --scales 1 2
```

Artboards are views of one design at several sizes. For a sequence of different designs at one
size (slides, carousel frames, booklet pages) use [pages and masters](slides.md), which export to
multi-page PDF and PowerPoint. Mixed styles inside one text box are [rich text](rich-text.md);
places for people to write are [form fields](forms.md), which export as fillable PDFs and fill from CSV.

Artboards are named canvas configurations in one document. They share the editable layer stack and resolve canvas constraints at each board's size. A board with `x`/`y` (`vixl artboard crop --width 1080 --height 1080 --x 260 --y 1400`) is instead a viewport: it shows that region of the document canvas, laid out at the document's size. Optional `variables` supply board defaults and `targets` selects top-level layer IDs; absent `targets` means all layers, while an empty stored list shows none. Render overrides take precedence over board variables. `export-screens` writes every board at each scale as `NAME@SCALE x.png` (without the space, e.g. `story@2x.png`); `--artboards square story` selects boards. PNG outputs are staged before publication and existing destinations are rejected. Scaled exports resample the composed raster, as existing Vixl exports do.

```bash
vixl frame --path portrait.jpg --name photo --width 400 --height 500 --fit fill
vixl replace-contents photo --path replacement.jpg
vixl replace-contents photo --fit fit --asset assets/EMBEDDED_HASH.png
```

Frames center and fill/crop or fit/letterbox their boxes. Replacement keeps the layer ID, box, position, transforms, styles, effects and mask. Explicit replacement clears an old source crop, linked-file path, and image-variable binding. Frame imports embed the image in the project. Remote clients use already-imported `asset` IDs instead of paths.

Image variables reference embedded assets during ordinary rendering:

```bash
vixl variable set photo_asset assets/EMBEDDED_HASH.png
vixl replace-contents photo --variable photo_asset
vixl render --set photo_asset=assets/OTHER_HASH.png --out variant.png
vixl render --data rows.csv --out campaign
```

CSV requires unique headers and at least one complete row. Each row becomes render variables and produces `0001.png`, `0002.png`, etc., without mutating the project. Quoted commas, quoted newlines, and UTF-8 BOMs are supported. `--set` overrides row values. Bound image columns may contain an embedded asset ID or a file path relative to the CSV; only this explicit local CSV workflow imports paths. CSVs are limited to 8 MiB and 10,000 rows. All rows are rendered to temporary files before output publication; bad rows leave no partial campaign. Existing outputs are never overwritten. Data rendering also accepts `--artboard` and `--comp`.

Python exposes `project.render(artboard=..., comp=..., variables=...)`, `project.render_data(csv_path, directory, ...)`, and `project.export_screens(directory, scales=(1, 2), ...)`. REST POST `/render` and MCP previews accept `artboard` and `comp`; local-directory batch exports remain CLI/Python operations.

## Empty content and stacks

A template filled from data meets empty fields: a badge row with no company, a card with no subtitle. Fixed text frames leave a hole where the empty line was. Two features let the layout react instead:

- **`hide_if_empty`** on a text layer (`text`, `text-set`, `vixl text add --hide-if-empty`, or the `text` operation over MCP): while the text is empty or blank after `${variable}` substitution, the layer is not drawn, not checked, not exported and takes no space in a stack. `inspect` marks it `collapsed: true`; the layer and its settings stay, so a later non-empty value brings it back.
- **`stack`** turns a group into an auto-layout column or row. `{"type":"stack","name":"names","targets":["first","last","company"],"direction":"vertical","gap":20,"align":"center","justify":"center","width":1000,"height":400}` groups the layers and lays them out in the group's box; `{"type":"stack","target":"names","gap":12}` changes an existing stack. `direction` is `vertical` (default) or `horizontal`; `gap` and `padding` are pixels; `align` places members across the stack and `justify` along it (`start`, `center` or `end`); `width`/`height` set the box (pixels or `N%`). Members are laid out in document order. Members that are hidden (`hide`) or collapsed by `hide_if_empty` take no space, so the others reflow and, with `justify: "center"`, stay centred. A stack with `hide_if_empty: true` collapses when all its members do, so stacks nest. `stack` with `remove: true` releases the members at their current positions.

Stacks are resolved whenever the document is laid out (render, export, check, `inspect`), so `render --data rows.csv`, `--set company=` and export-time `variables` re-centre each row; only the settings are stored. A stack positions its members, so `move`, `align`, `distribute`, `constrain` and `unconstrain` on a member fail with `stack_managed` and say what to use; resize and reorder members, or move the stack. A group's box is fixed (members may overflow it), and members are positioned individually, so put overlapping artwork (a pill behind its label) in a sub-group and stack the sub-group.

Template containers stay static: `container-reflow` and the container check skip hidden and empty members, so hiding one and reflowing closes the gap, and container placement leaves no gap for an empty `hide_if_empty` member. For a container that follows variables at export time, add a `stack` to it (set its `padding`/`gap` to the container's rules); the stack then replaces the container's layout rule.

## Measuring the rendered image

```bash
vixl sample 100 150
vixl histogram --region 40 40 300 200
vixl info --region 40 40 300 200 --foreground '#ffffff'
vixl info --target title
```

Measurements return JSON: RGBA/hex point sample, alpha-weighted average RGB, mean alpha, four 256-bin histograms (excluding fully transparent pixels), and optional WCAG luminance contrast minimum/mean/maximum. `--foreground` compares the specified RGBA color against every pixel in the region; transparency composites over `--background white` by default. `--target` uses the actual rendered layer (including nested group children) against the stack below it, including opacity, styles and blending, with antialiased fringe pixels excluded. The target must be visible and drawable. Top-level bounds must be within the canvas; grouped targets measure their visible canvas coverage. A target outlined with a `stroke` style at least 3 px wide (and 2% of its font size) also reports `outline`: the outline ring against the backdrop. Contrast thresholds are 4.5 for normal text and 3 for large text, met by the fill or, for outlined text, by its outline; font size eligibility remains the caller's responsibility.

Use `project.measure(...)`, REST POST `/measure`, or MCP `vixl_measure` for the same read-only results. These are measurements, not a GUI info panel.

## Gradients, adjustments, automatic corrections, and LUTs

```bash
vixl gradient --name sky --direction angled --angle 35 --stops '[{"offset":0,"color":"#152235"},{"offset":0.4,"color":"#b36881"},{"offset":1,"color":"#e8885c"}]'
vixl adjustment warmth --effects '[{"name":"temperature","amount":40},{"name":"contrast","amount":10}]'
vixl auto-tone photo
vixl auto-color photo
vixl auto-contrast photo
```

Gradient directions are `vertical`, `horizontal`, `angled` (0° left-to-right, 90° top-to-bottom), and `radial` (center to the inscribed ellipse: the last stop sits where the ellipse touches the middle of each edge, and the corners beyond it take its color, so a radial fade to transparency leaves transparent corners). `falloff` shapes the curve between the stops: `linear` (default), `smooth` (smoothstep), `ease` (fast near the start, soft at the end), `quadratic` (a dome) or `gaussian` (a soft halo). A falloff is drawn as extra stops, so PNG, SVG, PDF and PPTX show the same curve; PPTX radial gradients are scaled to end at the inscribed ellipse too. The `bounds` check reports a fade-to-transparent gradient whose box edge is still painted inside the canvas (`code: gradient-edge`, review) because that edge shows as a hard rectangle. Supply 2–64 strictly increasing stops at offsets 0–1; start/end remain backward compatible. Transparency interpolates in premultiplied alpha. Gradient overlays use the same fields.

Adjustment layers process the already-composited stack below them in their parent group. They accept built-in effects, opacity, masks and blend modes; layers above are unaffected. Auto Tone stretches channels independently between their visible-pixel 0.5th and 99.5th percentiles; Auto Contrast uses a shared range; Auto Color adds gray-world channel balancing. Alpha is preserved and flat ranges are handled without division by zero.

Named 3D LUTs are embedded, shareable JSON resources:

```json
{"type":"lut","name":"look","size":2,"values":[[0,0,0],[1,0,0],[0,1,0],[1,1,0],[0,0,1],[1,0,1],[0,1,1],[1,1,1]]}
```

This is an identity table. Sizes 2–33 require exactly `size³` normalized RGB triples, with red varying fastest, then green, then blue (cube ordering). `vixl lookup photo look --amount 0.8` adds the named look to the layer's effect stack as a `lookup` effect (trilinear interpolation, alpha preserved): it applies in stack order, can be disabled, removed, reordered with `effect-move` or limited to the current selection, and works on adjustment layers. Redefining the table updates all uses. Documents that stored a LUT as a layer's `lookup` field open with it converted to a `lookup` effect at the end of the stack. Share the `lut` operation through JSON; native `.cube` parsing is not included.

## Comps, text layout, guides, pathfinder, and symbols

```bash
vixl comp-save with-logo
vixl hide logo
vixl comp-save without-logo
vixl render --comp with-logo --out branded.png
vixl comp-apply with-logo
vixl text-layout title --width 600 --height 180 --fit
vixl text-layout title --width 600 --height 180 --warp arc --amount 0.15
vixl text-layout title --width 600 --height 180 --path '[[10,90],[300,20],[590,90]]'
vixl guide left-margin x 64
vixl constrain title --left guide:left-margin.left
vixl grid editorial --columns 3 --rows 2 --margin 64 --gutter 24
vixl pathfinder badge outer inner --mode subtract
vixl symbol logo Brandmark
vixl symbol-instance Brandmark --name footer-logo --x 100 --y 800 --width 100 --height 100
```

Comps capture visibility, position, rotation, opacity, blend, constraints, and layer styles by ID, without duplicating imagery or full document history. New layers are unaffected and deleted IDs are ignored. `render --comp` is read-only; `comp-apply` is an undoable edit.

Text boxes wrap paragraphs and oversized words. Given only a `width`, the box is as tall as the wrapped lines (a box whose height was set before only grows), so nothing is cut off; `fit` shrinks from the configured font size until the text fits, and at least until its longest word fits on a line, so a word is broken across lines only when it cannot fit even at 1 px. Warps are `none`, `arc`, `flag`, and `bulge`, with amounts −1 to 1, applied inside the box. Paths are local pixel polylines: glyphs follow segment tangents and content beyond the path is omitted. This is basic glyph placement, not full shaping/kerning on Bézier paths. A warp moves glyphs up or down by a fraction of the box height; the warped line is moved back inside the box so lifted letters keep their tops. Content taller than the box keeps its top and is clipped at the bottom, so allow room for curvature. A new `text-layout` operation replaces the previous settings.

Guides are named absolute x/y positions used in constraint expressions such as `guide:left-margin.left+8`. Angled lines, rays, points, circles and curves, generated grid systems (thirds, golden, armature, polar, isometric, perspective …), `place` and `snap` are described in [guides](guides.md). Grids generate guides `NAME-x1-start`, `NAME-x1-end`, `NAME-y1-start`, etc.; redefining the grid replaces its generated guides. Guides/grids are document metadata, never painted into output, and remain absolute when the canvas changes.

Pathfinder combines procedural shape silhouettes by union, subtraction in target order, or intersection. It retains procedural operand snapshots for resizing, hides the originals, and uses the first operand's fill. It does not rewrite editable vector paths or track subsequent edits to the original operands.

**In SVG, PDF and PowerPoint a pathfinder layer is real geometry**: one compound path (a contour for the outline and one for each hole, wound in opposite directions and never overlapping, so even-odd and nonzero fills agree), computed exactly from the operands' lines and Bézier curves. Curves stay curves, edges where operands touch or coincide are handled, and the file renders the same in browsers, Inkscape, resvg, PDF viewers and PowerPoint. No alpha masks are written. A pathfinder whose pixels are not just the combined coverage of its operands' outlines (a stroked, translucent, line, masked or effect/style-carrying operand, curves that overlap along part of their length, or more than 1200 segments) cannot be geometry: the SVG draws it as an image and lists the reason under `raster_fallbacks`, `svg_policy="strict"` rejects the export naming the layer and the reason, and PDF and PowerPoint draw the layer as an image with the same reason. Draw a stroke as its own layer, or use fills only, to keep a boolean as geometry.

Symbols refer to a drawable master by immutable ID. Instances follow the master's content, styles and effects, with independent placement, size, opacity, blend, visibility and transforms. Group/adjustment/instance masters are excluded. Removing a master still used by instances is rejected atomically; update the master layer normally to refresh its instances.

## Provider-backed editing tools

```bash
vixl select rect 100 100 200 200
vixl ai remove --provider local --as removed-object
vixl ai content-aware-fill --prompt 'Continue the brick wall' --provider local --as filled-wall
vixl ai select-subject --provider vision
```

Remove and Content-Aware Fill call the existing provider's inpainting capability, retain generation provenance, and insert an editable layer masked to the selection. Select Subject calls segmentation and stores the returned mask as the active selection. They use configured providers and make no claim of an offline content-aware algorithm. Provider errors and invalid responses leave the document unchanged. Contract tests use fixtures; live service/model quality requires configured credentials.
