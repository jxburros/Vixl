# Hand drawings, organic shapes, guides

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
  photographed sheet of paper is left out (`sheet: false` keeps it, for a border drawn along the photo's edge).
- `vectorize` makes editable strokes `NAME/s001…` (longest first); `straighten` (only the strokes
  the user asked about — pass `strokes`), `smooth`, `restyle` and `stroke` change them.
- Before `fill`, call `vixl_workflow("drawing-report", {"target": "house"})`: it lists closed
  regions with a point inside each, and how much of the original line work is kept.
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
presets; `parts` compose your own. Regrow with a new `seed` and the same `target`. Full
reference: `docs/organic.md`.

## Guides, grids and placement

Guides can be angled lines, rays, segments, points, circles and curves; `grid --kind` makes
thirds, golden, armature, golden-spiral, polar, isometric, triangular, hex, oblique and
perspective systems. Place layers exactly on them instead of computing coordinates:

```json
{"type": "grid", "name": "dial", "kind": "polar", "rings": 3, "spokes": 12}
{"type": "place", "targets": ["n1", "n2", "n3"], "guide": "dial-r3", "orient": "radial"}
{"type": "snap", "targets": ["logo", "title"], "tolerance": 8}
```

`vixl_check(checks=["guides", "alignment"])` reports near misses with the fixing move;
`vixl_render_preview(guides=true)` draws them. Full reference: `docs/guides.md`.
