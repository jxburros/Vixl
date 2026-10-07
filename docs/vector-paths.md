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
The comic `speech-bubble` operation builds a bubble sized around its text; the `speech-bubble`
shape below is a single outline whose body and tail you shape yourself.

## Shape-specific parameters

The shortcut shapes take parameters of their own. Without them each keeps its fixed outline;
any of them makes the shape parametric (redrawn crisply in every output). Lengths accept pixels,
a fraction up to 1 (of the dimension named) or a percentage.

| Shape | Parameters (defaults) |
| --- | --- |
| `heart` | `apex` 0.5: where the cleft and tip sit across the width (below 0.5 the left lobe is smaller); `cleft` 0.2: how far the top notch dips; `tip` 0.95: how far down the point reaches (both of the height, from the top) |
| `speech-bubble` | `pointer_side` `bottom` (`top`, `left`, `right`): the side the tail comes from; `pointer_position` 0.2: the tail tip along that side, 0-1 (at 0.2 or less the tail base runs from the tip toward the middle, at 0.5 it is centred, at 0.8 or more it runs back); `pointer_size` 0.25: tail base width, of the side; `body` 0.75: depth of the body, of the height (of the width for a left/right tail); the rest is tail |
| `shield` | `depth` 0.55: depth of the point, of the height |
| `chevron` | `thickness` 0.4: band thickness, of the width; `point_radius` |
| `trapezoid`, `parallelogram` | `slant` 0.25: top-corner inset (trapezoid) or top-edge offset (parallelogram), of the width; `point_radius` |
| `triangle` | `apex` 0.5: the top vertex across the width (0 is a right triangle); `point_radius` |
| `tag` | `depth` 0.22: length of the point, of the width; `hole` |
| `star`, `polygon`, `burst`, `seal` … | `sides`/`count`, `inner_radius`, `point_radius`, `valley_radius`, `rotation_offset` (see above) |
| `ring`, `frame`, `plus`, `cross`, `minus` | `thickness`: band or arm thickness |
| `arrow`, `callout` | `head_length`, `head_width`, `shaft_width` …; `pointer_position`, `pointer_size` |

```json
{"type":"shape","shape":"speech-bubble","name":"bubble","width":320,"height":200,"pointer_side":"left","pointer_position":0.7,"body":0.85,"fill":"white","stroke":"#17202a","stroke_width":3}
{"type":"shape","shape":"heart","name":"heart","width":200,"height":180,"cleft":0.3,"tip":0.9,"apex":0.45,"fill":"crimson"}
```

`tail_side`, `tail_position`, `tail_size`/`tail_width`, `body_ratio`, `lobe_balance` (heart
`apex`), `points` (star `sides`) and `arm_width` (`thickness`) are accepted spellings, reported
under `normalized`. A parameter a shape does not read (`cleft` on a rectangle) is reported under
`warnings`. `vixl_capabilities("shapes")` lists every shape's parameters.

## Content boxes

A shape's content box is its usable inner area: a speech bubble's body (without the tail and
rounded corners), a tag without its point, the circle inside a star, badge, seal or polygon, the
inscribed rectangle of an ellipse or rounded rectangle, a ring or frame opening, a device or
browser screen, a banner between its folds, and the largest rectangle inside organic outlines
(heart, shield, cloud, triangle, arrow …). `inspect` and apply results report it in canvas
coordinates as `content_bounds` whenever it is smaller than the box (rotation and flips included;
a rectangle, a line or an icon has none).

Centre text in it, or pin it to a corner of it:

```json
{"type":"text","text":"Hello!","name":"line","size":28,"color":"#17202a","within":"bubble"}
{"type":"place","targets":["line"],"within":"bubble","anchor":"top-left","margin":8}
{"type":"align","targets":["line"],"relative_to":"bubble","box":"content","alignment":"center"}
```

`text` with `within` centres the text in the content box (no `x`/`y`). `place` with `within`
instead of `guide` puts each target's `anchor` (default `center`) on the same point of the
content box, inset by `margin`; `box: "bounds"` uses the whole box. Both work across groups.
`align` with `box: "content"` aligns sibling layers to the content box of the `relative_to` layer.

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

## Path coordinates and the layer box

`{"type":"shape","shape":"path","path":"…"}` draws SVG path data (`M L H V C S Q T A Z`,
absolute or relative, several sub-paths `M…M…` in one layer). The contract:

- **Coordinates are literal local pixels.** A path point `(px, py)` draws at
  `(x + px, y + py)` in the layer's parent (the canvas, or the group's box), where `x`/`y` are the
  layer's position (default `0, 0`). They are never normalized to the box.
- **Without `width`/`height` the box reaches the path's farthest point:** `width` is the
  largest x the drawn path reaches (curves included), `height` the largest y, so the box runs from
  the layer origin to the path's far corner. It is never the whole canvas. Giving only one of them
  sets that side; the other still comes from the path. The path text is kept exactly as written.
- **With `width`/`height` at creation**, coordinates are still literal: the given size is the box
  the path is drawn in (`path_view`), and geometry beyond it still draws (shapes do not clip).
- **Resizing scales the path.** A later `resize`/`scale` (or `shape` with `target` and a new
  `width`/`height`) scales the drawn path with the box. Replacing `path` with `target` keeps the
  current box, so the new path is again read in literal pixels of that box.
- **Negative coordinates** draw left of / above the layer origin, outside its box: the box (and so
  alignment, `center`, pivots and checks) does not include them. Keep paths in positive
  coordinates, move the layer with `x`/`y`, or use `path-fit` to scale geometry into a box.
- An open path (no `Z`) with a `stroke` and no `fill` is stroked only; otherwise set
  `fill: "none"` (read as `transparent`) for an outline.

```json
{"type":"shape","shape":"path","name":"flick","path":"M300 200 Q320 150 340 140 M310 210 Q330 170 352 165","stroke":"#5a3a1a","stroke_width":3}
```

This layer's box is `0, 0, 352, 210`: the strokes draw at their literal coordinates.

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
  originals are preserved and hidden, as with existing pathfinder modes. Each piece reaches 1 px under the
  pieces stacked above it (never past the outline of the whole), so abutting pieces render without a hairline
  seam. Divide is limited
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
