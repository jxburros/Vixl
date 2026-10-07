# Hand drawings, organic shapes, imperfection, guides

## Building on a hand drawing

When a person gives you a photo or scan of their drawing, keep their lines and build on them:

```json
{"type": "drawing", "action": "import", "asset": "assets/<sha>.png", "name": "house"}
{"type": "drawing", "action": "vectorize", "target": "house"}
{"type": "drawing", "action": "straighten", "target": "house", "strokes": ["house/s001"], "settings": {"close_gaps": 30}}
{"type": "drawing", "action": "fill", "target": "house", "points": [[700, 500, "#f4a259"]], "settings": {"gap": 12}}
{"type": "drawing", "action": "stroke", "target": "house", "points": [[960, 330], [960, 230], [1010, 230]]}
```

- `import` (MCP: import the image with `vixl_import_image` first, then pass `asset`) cleans the
  photo into `NAME/ink` over a hidden, aligned `NAME/original`. `clean` re-runs it (`sensitivity`,
  `weight`, `ink: "original"` keeps the pencil colour, `despeckle`, `deskew`). The desk around a
  photographed sheet of paper is left out (`sheet: false` keeps it, for a border drawn along the photo's edge), and a page
  photographed at an angle is flattened first (`perspective: false` skips it). The lines are `#1d1d1f` (near-black) unless you
  set `ink` (or `color`) on `import`; `drawing report` tells you `paper_found`, `perspective_corrected`, `tilt_corrected`.
- `vectorize` makes editable strokes `NAME/s001…` (longest first); `settings.width: "uniform"` gives every stroke one
  weight (a number sets it). `straighten` (only the strokes the user asked about — pass `strokes`), `smooth`, `restyle`
  and `stroke` change them. `straighten` keeps each line at the angle it was drawn at; add `angles: "axes"` to square up
  walls and floors or `"45"` for diagonals only when asked, and `close_gaps: 30` (or `"auto"`) to close corner and
  T gaps (corners get sharp, lines keep their angles).
- Before `fill`, call `vixl_workflow("drawing-report", {"target": "house"})`: it lists closed
  regions with a point inside each (`point` on the canvas, `group_point` in the drawing's own
  coordinates), the drawing group's `offset`, `scale` and `rotation`, and how much of the original line
  work is kept. `fill` and `stroke` points are canvas positions by default, wherever the drawing has been
  moved; pass `space: "group"` to give them in the drawing's own coordinates instead.
- After edits, check `preserved` (aim for ≥ 0.9 unless told to redraw) and look at
  `vixl_workflow("drawing-compare", {"target": "house", "output": "compare.png"})` (original red,
  result blue). `vixl_check(checks=["drawing"])` warns when original lines were lost.
- Optional colouring with a provider: `vixl ai drawing-color house --prompt …` (CLI/Python).

Full reference: `docs/drawing.md`.

## Diagrams: flowcharts, dependency graphs, org charts, mind maps

`diagram-from-text` (or `diagram` with `nodes` and `edges`) lays a graph out and writes ordinary layers in one group
(`flow/<id>`, `flow/<from>-><to>`, labels as `….label`). `diagram-set` changes it and re-lays it out in place (same layer IDs).

```json
{"type": "diagram-from-text", "name": "flow", "direction": "LR", "text": "Start([Start]) -> Check{Valid?}\nCheck -> Save[(DB)]: yes\nCheck -> Fix[Show error]: no\nFix -> Check"}
{"type": "diagram", "name": "org", "layout": "tree", "text": "CEO\n  CTO\n    Dev lead\n  CFO"}
{"type": "diagram-set", "name": "flow", "text": "Save -> Done([Done])", "remove_nodes": ["Fix"]}
```

- Text format: `A -> B -> C`, `A -> B: label`, `A{Question?}` (decision), `A([x])` terminator, `A[/x/]` io, `A[(x)]` database,
  `@color=… @icon=check @group=…`, `group Lane: A, B`, indentation for hierarchies, `direction: LR`.
- `layout`: `layered` (flows, dependencies), `tree`, `radial`, `mindmap`, `grid`; `direction` TB/LR/BT/RL; `routing`
  orthogonal/curved/straight; `lanes: true` for swimlanes. The diagram shrinks to fit the canvas (`fit`, `x/y/width/height`).
- Check with `vixl_check(checks=["diagram"])`: overlapping nodes, edges through nodes, labels that do not fit or lack
  contrast, text scaled below 9 px. Full reference: `docs/diagrams.md`.

## Organic shapes

For living things (flowers, trees, leaves, shells, creatures, coral, markings) use `organic`
rather than hand-placing ellipses: `{"type": "organic", "preset": "sunflower", "name": "bloom",
"seed": 7}`. `vixl organics` / workflow `organic-catalog` lists 18 generators, 19 rules and 32
presets; `parts` compose your own. Regrow with a new `seed` and the same `target`. To keep a
form inside a brand palette pass `fill` (every filled part), `stroke` and `stroke_width` (every
line, extra outputs such as shell chambers and leaf veins included); `colors` names single
parts and wins over `fill`. A regrow with `stroke`/`fill` restyles the same way as creating
with them. Full reference: `docs/organic.md`.

## Imperfection: irregular and tear

Opt-in, for chosen things: an original character, hand-inked outlines, a set of copies that must
not look identical, ripped paper. **Do not use it** on logos, icons, UI, charts or diagrams, on
anything that must align or measure (grids, form fields, barcodes, bleed), on text (refused), on
tiny elements, or as a finish over the whole document.

```json
{"type": "irregular", "targets": ["hero", "leaves"], "seed": 7, "strength": "natural"}
{"type": "irregular", "target": "hero", "seed": 8}          # regrow: new seed, same recipe, from the source
{"type": "irregular", "target": "hero", "remove": true}      # exact source back
{"type": "tear", "target": "photo", "seed": 3, "edges": ["bottom"], "strength": "rough"}   # mask + rim + fibres
{"type": "tear", "name": "scrap", "as": "path", "seed": 9, "width": 600, "height": 400, "edges": ["all"]}
```

`seed` is required and decides everything; each layer of a group gets its own stream. `strength`
is `subtle` (the default), `natural` or `rough` (magnitudes scale with each layer's size),
`amount` scales it, `only` picks effects (`wobble`, `jitter`, `width`, `pressure`, `color`,
`placement`), and explicit fields (`wobble` px, `wobble_length` px, `pressure`, `lightness_drift`,
`rotation_jitter`…) set exact bounds. Shapes become path layers (a stroke with `pressure` becomes a
ribbon, a `NAME-ink` sibling when the layer has a fill); regrow or `remove` always start from the
kept source, so edits made since are replaced. `tear` `as`: `mask` (default with a target), `clip`
(vector face the target is clipped to), `path` (free rim, face and fibre layers); regrow by
targeting the torn layer (the `-face` layer for a free sheet). Reference: `docs/irregular.md`.

## Scatter, seamless tiles and fur

```json
{"type": "scatter", "target": "hill", "source": ["leaf", "flower"], "count": 80, "seed": 3, "rotation_jitter": 40, "scale_jitter": 0.3, "tone_variation": 0.06, "merge": true}
{"type": "scatter", "target": "card", "mark": {"shape": "ellipse", "width": 6, "height": 6, "fill": "#fff"}, "placement": "along", "spacing": 18}
{"type": "scatter", "target": "bear", "preset": "fur", "seed": 2}
{"type": "pattern-scatter", "source": ["leaf", "dot"], "width": 200, "height": 200, "count": 14, "seed": 11, "rotation_jitter": 180, "background": "#fff7ed", "pattern": "leaves", "name": "tile"}
{"type": "pattern-scatter", "target": "tile"}                 # rebuild and re-wrap after editing a motif
```

`scatter` copies motifs inside a layer's outline (Poisson-disc, no grid look) or `along` its edge
(`direction` normal/tangent/cone/random, `anchor: base` grows marks out of the line), with seeded
jitter, `colors`/`tone_variation` and `exclude`. `merge: true` draws every copy as one path per tone
(shape motifs), so large scatters stay within the layer limit. `pattern-scatter` makes a seamless
tile: motifs crossing an edge get wrapped copies, the result reports `seam`, and `pattern` saves it
for `pattern-fill` (`tile_variation` varies each repeat). Fur: `preset: fur`, the `plush` look or
the organic `fur-blob` preset; the `hand-made` look applies a removable irregular wobble.
`repeat`/`radial-repeat` take `rotation_step`, `scale_step`, `opacity_step`, seeded jitter and
`merge`. Reference: `docs/design-tools.md#scatter-and-seamless-pattern-tiles`.

## Guides, grids and placement

Guides can be angled lines, rays, segments, points, circles and curves; `grid --kind` makes
thirds, golden, armature, golden-spiral, polar, isometric, triangular, hex, oblique and
perspective systems. Place layers exactly on them instead of computing coordinates:

```json
{"type": "grid", "name": "dial", "kind": "polar", "rings": 3, "spokes": 12}
{"type": "place", "targets": ["n1", "n2", "n3"], "guide": "dial-r3", "orient": "radial"}
{"type": "snap", "targets": ["logo", "title"], "tolerance": 8}
{"type": "snap", "targets": ["title", "body"], "anchors": ["baseline"]}
```

`place` with `within` (instead of `guide`) puts each target's `anchor` on the same point of a
shape's content box (`content_bounds`: a speech bubble's body, a badge, a frame opening), inset
by `margin`; `text` with `within` centres new text there.

`vixl_check(checks=["guides", "alignment"])` reports near misses with the fixing move;
`vixl_render_preview(guides=true)` draws them. Full reference: `docs/guides.md`.
