# Precise transforms and spatial queries

Vector geometry keeps fractional pixel positions and dimensions. Shape, path, text, rich-text,
solid, gradient and vector group sizes survive repeated scaling without integer rounding.
SVG and PDF retain these coordinates; raster previews resample fractional placement. Images,
pixel layers and form fields snap to whole pixels. `snap-to-pixel` controls a layer override or
the document default:

```json
{"type":"snap-to-pixel","target":"icon","value":true}
{"type":"snap-to-pixel","scope":"document","value":false}
```

`resize` and `scale` accept `anchor`: `top-left`, `top`, `top-right`, `left`, `center`,
`right`, `bottom-left`, `bottom`, `bottom-right`, or `[x,y]` fractions of the artwork.
An explicit anchor stays fixed even when the layer or its ancestors are rotated, skewed,
scaled or mirrored. Omitting it retains the stored origin, for backward compatibility.

```json
{"type":"resize","target":"card","width":520.5,"anchor":"center"}
{"type":"scale","target":"icon","value":0.75,"anchor":[0.25,0.8]}
{"type":"resize","target":"card","width":"+8","height":"-5%"}
{"type":"match-size","targets":["card-a","card-b"],"to":"reference","axis":"width"}
{"type":"fit","target":"logo","box":[40,40,200,100],"mode":"contain","align":"center"}
```

Signed resize strings are changes relative to the current dimension. Unsigned percentages
retain their existing meaning: a fraction of the canvas or parent group. `match-size` defaults
to both dimensions. `fit` accepts another layer's name/ID as its box; `contain` preserves
aspect and fits inside, `cover` preserves aspect and fills with overflow, and `stretch` fills
both dimensions. Fit boxes and alignment use canvas space, including nested groups.

Grouped layers store parent-relative positions. Default `move` coordinates are in that parent
space; use `space: "canvas"` (or `absolute: true`) to position a nested layer by its canvas
bounding-box corner. `shape`, `text`, `solid` and `gradient` with `target` take the same `space`
for their `x`/`y`, and `pivot` takes `units: "canvas"` to set a joint at a document point (it is
converted through the parent groups' transforms). `inspect` returns both `resolved_bounds` in parent space and
`canvas_bounds` in canvas space. Canvas moves round-trip those bounds, including transformed
ancestors. Edits that move content entirely off the canvas return an apply warning.

```json
{"type":"move","target":"label","space":"canvas","x":700,"y":500}
{"type":"move","target":"label","space":"canvas","relative":true,"x":1,"y":-1,"step":0.25}
{"type":"skew","target":"banner","x":20,"y":0}
{"type":"transform","target":"panel","matrix":[1,0,0.3,1,20,0]}
```

`skew` angles are degrees around the pivot (center by default). Set `relative: true` to add
angles. `transform` takes the standard six affine coefficients `[a,b,c,d,e,f]`, where
`x'=a*x+c*y+e` and `y'=b*x+d*y+f`. It decomposes the linear transform into editable rotation,
dimensions, mirroring and shear; translation offsets the stored origin. `relative: true`
composes it with the current linear transform. Singular matrices and collapsing shears are
rejected. Form fields cannot skew or take a matrix. SVG/PDF export native transforms;
`skew_x` and `skew_y` are numeric timeline properties, with `skew-x`/`skew-y` aliases.

## Spatial API

Use `Project.spatial(...)` or `vixl_spatial`. All returned geometry is in canvas space. Select
by `target` name/ID/glob, `targets` list, `group:name` descendants, or selector objects in a
`targets` list. `page` and `artboard` scope the query; `bounds` is `box` (default) or `ink`.
The ink mode uses glyph outline bounds for text and rich-text, transformed into canvas
coordinates, and includes conservative effects/overflow extents. Hit queries verify actual rendered alpha.
Queries do not mutate the document.

- `relations`: compare selected layers, optionally to a separate `to` selector. Returns
  left/right/above/below, overlap and containment, signed axis gaps, nearest-edge distance,
  overlap area and percentages of each layer, center offsets/distance/angle, and aligned
  edges/centers within `tolerance` (default 1 px).
- `matrix`: the relation matrix and nearest neighbour of each selected layer.
- `canvas`: canvas, safe-area, trim and bleed edge distances, fractional center, quadrant,
  thirds region, and whether bounds extend outside canvas or parent. Group overflow remains
  visible unless a mask clips it; the parent flag describes its geometric extent.
- `grid`: selected or most recently defined `grid`; occupied one-based columns/rows and
  spans, nearest gridline offsets at start/center/end, and snapped status. Grid columns
  exclude gutters; generated non-column grids use adjacent axis lines where available.
- `guides`: nearest guide on each axis, all edge/center matches, and distances to axis,
  oblique, point, circle and path guides.
- `composition`: distances to thirds/golden-ratio lines and intersection points, plus
  canvas center axes and point.
- `hit`: `point: [x,y]` or `region: [x,y,w,h]`, topmost first, reporting inherited visibility
  and opacity. Hidden/transparent layers are omitted unless `include_hidden` is true.
- `free`: largest maximal empty rectangles in a region (canvas by default), excluding
  selected visible bounds. Results sort by area; `limit` defaults to 20. Use targets to
  exclude intentional background panels from the obstacles.
- `snap`: nearest guide moves and valid edge-resize fits returned as directly applicable `operation` objects; when
  `grid` is given, also returns a fit operation that resizes into the nearest grid cell. An affine stretch that cannot retain the layer's rotation falls back to an aspect-preserving contain fit.
- `all`: layer/canvas relationships, grid, guides, and composition in one query.

`describe: true` adds compact summaries suitable for reasoning. Queries retain exact numeric
values; `tolerance` affects classification and snapped/aligned status, not the measurements.
