# Editable vector shapes, strokes and paths

All examples are operations for `Project.apply`, the CLI edit command, or `vixl_operations_apply`.
Changes participate in the same validation, atomic batches, save/load and undo history as
other edits. `shape` with `target` updates a recipe without changing the layer ID.

## Corners, stars and arrows

`radius` accepts pixels, a percentage of the shorter box edge, or four values in CSS order:
top-left, top-right, bottom-right, bottom-left. Adjacent radii are reduced proportionally
when they would overlap. `corner_style` is `round`, `chamfer`, or `inverted`.

```json
{"type":"shape","shape":"rounded-rectangle","name":"tab","width":240,"height":80,"radius":[24,24,0,0],"fill":"navy"}
```

Stars and polygons accept `point_radius`, `valley_radius`, `corner_style`, and
`rotation_offset` in degrees. `burst`/`starburst`, `seal`, and `flower` use the same radial
family; `sides`/`count` controls points or petals and `inner_radius` controls edge depth.

Arrows accept `head_length`, `head_width`, `shaft_width`, `heads` (`start`, `end`, `both`),
and `head_style` (`triangle`, `open`, `concave`, `round`). Lengths accept pixels, fractions
up to 1, or percentages. `curve` bends the shaft; `from`, `to`, and `control` instead give
explicit local coordinates for a quadratic curved arrow. `point_radius` rounds straight
arrow corners. Head geometry is shared with open-path markers.

## Catalog

Every entry remains a shape layer. Width/height, fill/stroke, transforms, and applicable
parameters can be changed later. Paths and holes export as real vector geometry.

| Family | Kinds | Parameters |
| --- | --- | --- |
| Labels and UI | `ring`/`donut`, `cloud`, `teardrop`, `crescent`/`moon`, `half-circle`, `banner`/`ribbon`, `tag`, `callout`, `bracket`, `brace`, `button`, `toggle`, `browser-window`, `phone-frame`, `tablet-frame` | `thickness`, `radius`, `depth`, `fold`, `hole`, `pointer_size`, `pointer_position`, according to shape |
| Diagram solids | `cylinder`, `cube`, `document`, `folder` | Box size; cylinder/cube `depth` |
| Curves | `squircle`/`superellipse`, `lens`/`vesica`, `reuleaux`, `quarter-circle`, `semicircle`, `ellipse-segment` | `exponent`, lens `depth`, Reuleaux `sides`, segment `start_angle`/`end_angle` |
| Polygons | `kite`, `rhombus`, `isosceles-triangle`, `star-polygon`, `hexagram`, `octagram`, `stairs`/`steps` | `apex`, rhombus `angle`, star-polygon `sides` and `step`, stairs `count` |
| Frames and marks | `frame`, `corner-bracket`, `L-shape`, `T-shape`, `notched-rectangle`, `plus`, `minus`, `x`/`saltire`, `asterisk`, `trefoil`, `quatrefoil`, `infinity` | `frame_shape` (`rectangle`, `ellipse`, `polygon`), `thickness`, `notch`, `sides`, `arms` |
| Mechanical | `gear`/`cog`, `ruler`/`tick-strip` | `teeth`, `depth`, `hole`; ruler `count`, `thickness` |
| Structured lines | `wave`, `zigzag`, `sawtooth`, `square-wave`, `dashed-line`, `curve` section divider | `amplitude`, `wavelength`, `phase`, `count`; stroke controls below |
| Symbols | `checkmark`, `x-mark`, `lightning`/`lightning-bolt`, `sun`, `flame`, `map-pin`, `house`, `bell`, `lock`, `magnifier`, `envelope`, `play`, `pause`, `stop`, `skip`, `info`, `question`, `warning`, `music-note`, `sparkle`, `star-rating` | `thickness` for line symbols; sun `count`/`ray_length`; rating `count`/`rating` with fractional stars |
| Decoration | `flourish`, `swash-underline`, `scroll`, `laurel`/`wreath`, `divider`, `corner-ornament`, `sunburst`, `radial-burst`, `motion-lines`/`speed-lines`, `confetti`, `scribble`/`squiggle` | `count`, `thickness`; wave-like ornaments `amplitude`, `wavelength`, `phase` |
| Print/craft | `ticket`, `stamp`/`postmark`, `scalloped-border`, `sticker` | `notch`, edge `count`/`depth`, `thickness`, `peel` |

Image content can be placed in UI frames with the existing image `frame`, `replace-contents`
and clipping operations; the decorative shape does not embed an additional hidden image slot.
Speech bubbles use the existing bubble/container operations.

## Strokes

Shapes, lines and pen paths support:

- `dash`: positive dash/gap lengths, or `dashed`/`dotted`; `dash_offset` moves the pattern.
- `line_cap`: `butt`, `round`, `square`; `line_join`: `miter`, `round`, `bevel`; `miter_limit`.
- `stroke_align`: `center`, `inside`, `outside`. Alignment is meaningful for closed contours.
- `strokes`: additional ordered `{color,width,stroke_align,...}` records, painted after the base stroke.
- `width_profile`: increasing `[fraction,width_multiplier]` points from fraction 0 to 1.
  `taper_start` and `taper_end` are endpoint multipliers, interpolated to full width at the midpoint.
- `marker_start`/`marker_end`: `none`, `triangle`, `open`, `concave`, `round`, with `marker_size` in pixels.

```json
{"type":"shape","target":"tab","stroke":"white","stroke_width":3,"stroke_align":"inside","strokes":[{"color":"navy","width":2,"stroke_align":"outside"}]}
```

These controls are shared by raster, SVG and PDF through filled vector stroke outlines.
Outside strokes and rounded caps may extend beyond the layer's layout box. `dash_offset`
and `stroke_width` are numeric timeline properties. `trim_start`/`trim_end` reveal a
percentage of the contour; they compose with dashes, rather than replacing the dash pattern.

## Indexed path editing

`shape-to-path` converts parametric and organic shapes to editable Bézier paths while
keeping identity, fill and stroke. `vixl_document_inspect` exposes `path_nodes`, an array of
contours with `closed`, and nodes containing `index`, `point`, and optional `in`/`out` handles.
Coordinates are in the layer's local pixel space. Compound paths keep their separate contours.

```json
[
  {"type":"shape-to-path","target":"tab"},
  {"type":"path-edit","target":"tab","action":"move","contour":0,"index":2,"point":[3,-4],"relative":true},
  {"type":"path-edit","target":"tab","action":"insert","index":0,"fraction":0.5}
]
```

Actions: `move`, `move-handle` (choose `handle: in/out`), `insert` (exact Bézier split),
`delete`, `corner`, `smooth`, `round` (`radius`), `open`, `close`, `reverse`.
`relative` supports node and handle moves; `symmetric` mirrors handles or makes smooth
handles equal in length. `path-simplify` reduces nodes by a pixel `tolerance`;
`path-smooth` computes smooth tangents with `amount` and `iterations`.

## Constructive paths

- `offset-path`: positive/negative pixel `distance`, `join` and `miter_limit`.
- `outline-stroke`: convert visible strokes into filled paths. Different paints produce separate layers.
- `round-corners`: round every path corner with `radius`.
- `pathfinder`: adds `exclude` (XOR), `minus-back` (last operand minus earlier operands),
  `divide` (independent faces), `trim` (remove covered portions), and `merge` (trim then
  combine pieces of the same fill). Divide/trim/merge return a group of editable paths;
  originals are preserved and hidden, as with existing pathfinder modes. Divide is limited
  to 256 faces, and the established boolean engine's geometry limits still apply.

Repeats and blends remain the existing `repeat`, `repeat-blend`, and `organic` `along`
features; no parallel duplicate operation was introduced.

## Vector distortions

`distort` stores an editable setting without replacing source shape parameters or nodes.
Use `remove:true` to restore the source. Supported kinds: `arc`, `arch`, `bulge`, `flag`,
`wave`, `fisheye`, `inflate`, `squeeze`, `twist`, `corner-pin`/`free-distort`, `pucker`,
`bloat`, `zig-zag`. Roughening remains the existing seeded `irregular` operation.

```json
{"type":"distort","target":"tab","kind":"wave","amount":0.15,"frequency":2,"phase":0}
```

`amount` is signed strength; waves use `frequency` and `phase`, twist uses `angle`,
zig-zag uses `size`, `ridges` and `smooth`. Corner pin uses four local `corners` in CSS
order. Curves are adaptively subdivided to vector line segments when a nonlinear warp
cannot be represented by their original Bézier controls. Group warps apply in the group's
content coordinate system and require shape/path descendants. Nested groups and affine
child placement remain editable.

Animate `distort:amount`, `distort:angle`, `distort:phase`, `distort:frequency`, or
`distort:size` with ordinary keyframes. Save/load and undo retain the original recipes.
