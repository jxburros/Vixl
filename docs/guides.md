# Guides, grids and placement

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Guides are named document metadata that are never painted into output. They give an agent
something exact to place against, and something to check against when it cannot see the
result. Besides vertical and horizontal guides, a guide can be an angled line, a ray, a segment,
a point, a circle or a curve, and `grid` generates whole systems of them: compositional grids
(thirds, golden section, harmonic armature, golden spiral), radial and polar grids, isometric,
triangular, hexagonal and oblique grids, and one-, two- and three-point perspective.

```bash
vixl grid dial --kind polar --rings 3 --spokes 12            # circles + spokes + a centre point
vixl grid rule --kind thirds                                  # thirds lines + four "power points"
vixl guide slope --kind line --x 0 --y 900 --angle -30        # any angle
vixl guide horizon --kind segment --points '[[0, 400], [1920, 380]]'
vixl guide wave --kind path --d 'M0 500 C480 300 1440 700 1920 500'
vixl place n1 n2 n3 n4 n5 n6 n7 n8 n9 n10 n11 n12 --guide dial-r3  # evenly round the circle
vixl place hero --guide rule-x2 --with rule-y1                # on an intersection
vixl place tick --guide dial-r2 --at 0.25 --orient normal     # turned to point outward
vixl place line --within bubble --anchor top-left --margin 8   # inside a shape's content box
vixl snap logo title --tolerance 8                            # fix near misses
vixl check --checks guides alignment                          # report near misses
vixl render --out guides.png --show-guides                    # see the guides over the design
vixl guides                                                   # list guides and grids
```

## Guide kinds

| Kind | Fields | Notes |
| --- | --- | --- |
| axis (default) | `axis` x or y, `position` | The original guides: `vixl guide margin x 64`. |
| `line` | `x`, `y`, `angle` — or `points` [[x1, y1], [x2, y2]] | Infinite line. Angles are degrees clockwise from pointing right (y down); 90 is vertical. |
| `ray` | `x`, `y`, `angle` | Starts at the point. Perspective and polar spokes are rays. |
| `segment` | `points` [[x1, y1], [x2, y2]] | A bounded line. |
| `point` | `x`, `y` | Focal points, vanishing points, power points, hex centres. |
| `circle` | `x`, `y`, `radius` | Rings for radial layouts, dials, wreaths. |
| `path` | `d` (SVG path) | Curves: S-curves, spirals, waves, any line of action. |

`guide NAME --delete` removes one guide; `grid NAME --delete` removes a grid and its guides.
Redefining a grid replaces its guides. A document holds at most 1,024 guides.

Constraints still work with guides: `guide:NAME.left` and friends read axis guides, horizontal
and vertical lines, points (their x or y) and circles (their centre, or `left`/`right`/`top`/
`bottom` for their extent). Angled guides are for `place`.

## Grid systems

`grid NAME --kind KIND`. Every kind accepts `region` [x, y, width, height] (default: the canvas).
Generated guides are named `NAME-…` and tagged with the grid.

| Kind | Generates | Settings |
| --- | --- | --- |
| `columns` (default) | column and row edge guides `NAME-x1-start`, `NAME-y1-end` … | `columns`, `rows`, `margin`, `gutter` |
| `baseline` | horizontal lines every `spacing` px (`NAME-b1` …) | `spacing` 8, `offset` |
| `thirds` | lines at ⅓ and ⅔ (`-x1`, `-x2`, `-y1`, `-y2`) and their four crossings (`-p11` … `-p22`) | — |
| `golden` | lines at the golden section (0.382 and 0.618) and their crossings | — |
| `armature` | the harmonic armature: both diagonals, the four reciprocal diagonals (each from a corner, perpendicular to the other diagonal), centre lines, rabatment lines (squares on the short side) and the centre point | — |
| `golden-spiral` | a golden spiral path fitted to the region, and its `eye` | `turns` 4, `corner` (bottom-right, bottom-left, top-right, top-left) |
| `polar` | concentric circles (`-r1` …), spokes (`-s1` …) and the centre | `x`, `y` (centre), `rings` (count or a list of radii), `radius`, `spokes` 12, `angle` −90 (first spoke) |
| `isometric` | three families of parallel lines at 30°, 150° and 90° | `spacing` 40, `x`, `y` (a point every family passes through) |
| `triangular` | three families at 0°, 60° and 120° (equilateral triangles) | `spacing`, `x`, `y` |
| `oblique` | any 1–4 families of parallel lines | `angles` [15, 105], `spacing` or `spacings`, `x`, `y` |
| `hex` | hexagon centres as point guides (`-c1-1` …) | `spacing` (hexagon size) |
| `perspective` | the horizon, vanishing points (`-vp1` …) and fans of rays from each | `points` 1–3, or `vanishing` [[x, y] …]; `horizon`; `rays` 16 |

All lattice families pass through one origin, so isometric and triangular lines cross at shared
points that `place --with` can use.

## Placing layers

`place` puts one or more layers on a guide. The layer's `anchor` (a name such as `center`,
`bottom` or `top-left`, or [fx, fy] fractions of its box; default `center`) lands on the guide.

| Field | Meaning |
| --- | --- |
| `guide` | The guide to place on. |
| `at` | Fraction 0–1 along the guide. Lines are measured across the visible canvas; circles clockwise from `angle` (default −90, the top). |
| `start`, `end` | Several targets spread evenly from `start` to `end` (default the whole guide; once round a circle). |
| `spacing` | Several targets this many pixels apart along the guide, from `at`. |
| `with`, `index` | Place on the intersection(s) of two guides; several targets take successive intersections. |
| `orient` | `none` (default), `tangent` (follow the guide), `normal` (perpendicular, pointing outward on circles), `radial` (pointing inward) or `upright`. `rotate` adds degrees. |
| `offset` | Pixels to the side of the guide (along its normal). |
| `within`, `box`, `margin` | Instead of `guide`: place inside a layer. The anchor lands on the same point of that layer's content box (`box: "bounds"` for its whole box), inset by `margin` pixels; see [content boxes](vector-paths.md#content-boxes). |

Placement works for layers inside groups, scaled or rotated groups included: positions are in
canvas pixels. `place` clears a layer's constraints, as `move` does.

```json
[{"type": "grid", "name": "dial", "kind": "polar", "rings": [240, 200], "spokes": 12},
 {"type": "place", "targets": ["n1", "n2", "n3"], "guide": "dial-r2", "start": 0, "end": 0.25},
 {"type": "place", "targets": ["tick1", "tick2"], "guide": "dial-r1", "orient": "normal"},
 {"type": "place", "target": "title", "guide": "wave", "at": 0.5, "orient": "tangent", "anchor": "bottom"}]
```

`snap` moves each target so its nearest anchor lands exactly on the nearest guide point,
intersection or guide within `tolerance` px (default 8), and straightens a rotation within
`angle_tolerance` degrees (default 4) of a straight guide's angle (`angles: false` keeps it).
`guides` limits the guides it considers; `anchors` limits which anchors snap.

## Checks

Two opt-in check families report what an agent cannot see. Both are warnings: deliberate
offsets are allowed, but they should be clear, not a few pixels.

- `guides`: a layer anchor that is close to (default within 6 px) but not on a guide or guide
  point, with the move that fixes it; a rotation within 4° of a straight guide's angle but not on it.
- `alignment`: sibling layers whose edges or centres are 1–3 px apart, or whose rotations are
  within 3° of each other without matching.

```bash
vixl check --checks guides alignment
```

MCP: `vixl_check(checks=["guides", "alignment"])`; previews draw the guides with
`vixl_render(guides=true)` (or a list of guide or grid names). Python:
`vixl.proxy.render_preview(project, w, h, guides=True)` and `vixl.guides.draw_overlay(image, project)`.

## Composition

The `composition` family is on by default. It reports what reads as "not designed" even when every other check
passes, as `review` warnings: they never fail a plain `check`, but they fail the `final` profile (and any run
with `fail_on: review`) until they are fixed or waived with a reason. Distances are in the craft spacing unit, half
the document's body size (`craft.spacing.unit` in the [house style](house-style.md)).

| Code | What it finds | Threshold |
| --- | --- | --- |
| `dead_band` | An empty horizontal band between content blocks, or between content and an edge, from the free rectangles of `spatial` | At least 6% of the frame's height, 4 units and 2.25× the median gap between stacked blocks; across a third of the content width (a narrower band only when artwork, not a line of text, closes its sides); an edge band must also be 1.75× the opposite margin. Only frames with two or more lines of type whose blocks fill half their height, and bands up to 42% of it |
| `margin_drift` | Stacked text, rules, charts, images and free-standing marks whose left edges (right edges of right-aligned text, centres of centred text) are close but not equal | More than 2 px and at most 2 units apart |
| `uneven_rhythm` | A stack of three lines where the middle line sits further from the line above it, which it matches more closely in size, than from the line below (a first name, a last name and a company); for lines of one size, gaps up to 3 units that differ. A subtitle tight under its title and away from what follows is by design. Also a small block (secondary text, a row of dots, a subtitle under a display title 2.5 times its size) as far from the block above as from the one below, between blocks of other kinds, so it belongs to neither | Gaps differing by 1.6× and 2 units (1 unit for lines of one size); a floating block has gaps of at least 3 units on both sides, within 1.5× of each other |
| `crowding` | A rule, band or heading less than half a unit above the text below it | Half a unit |
| `clumped_scatter` | A `pattern-scatter` or `scatter` whose motifs bunch in some cells of the tile and leave others empty | Coverage varies by more than 0.6 (coefficient of variation over 4×4 cells); seeded `pattern-scatter` tiles stay under 0.5 |

What is not judged: backgrounds and canvas-covering layers, gradient fills that run to two page edges and cover a
fifth of it (a sky, the water), layers drawn fainter than 30% opacity (smoke, haze, the last stripes of a
reflection), layers marked `role: decoration` (they still fill space, so a band they close off is not dead), art
that bleeds off the canvas, glows that fade to transparent, and the insides of charts, scatters and repeats (each
is one block). Text is measured from the top to the bottom of its glyphs, not its line box, so the leading above a
tall title counts as the space a reader sees; it aligns by its layout box. A signed value or a share set beside
its data ("−9", "+6", "38%") is not a margin. Text inside a panel or card is aligned and spaced
against that panel; text in a chip that hugs it (a highlight, pill or button) aligns by the chip's edge; a panel that covers a fifth of the canvas frames its own bands, a list hangs its markers, and a
label after an icon follows the icon. A capitalised kicker may sit tight to the line it labels.

Each finding carries `code` (rule `composition.dead_band` …), `layer_ids` and `layers`, the `region` it concerns,
`measured` (actual against expected), the `values` it measured (gaps, edges, the band's height and the typical
gap), the `threshold` it applied and `spacing_unit`, and a message that says what to do.

```bash
vixl check --checks composition
vixl check --profile final --strict
```

MCP: `vixl_check(checks=["composition"])`, or `vixl_check(profile="final")`. `vixl_apply` with
`check=true` lists every composition finding with the batch, wherever it is, and `check.regions`: the two weakest
regions; add `preview=true` and their real-size crops follow the preview ([interfaces](interfaces.md)). Workflow
`repair-layout` repairs most findings (snap the drift, re-space the stack, open the gap, spread the band, thin the
tile) without adding any; see [layout repair](agent-trust.md#layout-repair). A deliberate finding (an optical
indent, a field of space on purpose) is accepted with a reason, on the layer (`layer-intent waive`) or the
document:

```json
{"type": "waiver", "check": "composition", "reason": "the open lower half is the quiet field of this layout"}
```

The thresholds were tuned on the [craft backtest](../evals/craft_backtest/README.md): reconstructions of the 16
round-1 Vixl documents of the tool comparison with the defects the blind judges named. Of the 21 composition
defects there, the family catches 12 (dead band 5 of 10, margin drift 4 of 5, uneven rhythm 2 of 4, crowding 1 of
1, clumped scatter 0 of 1) with no false findings, and it finds nothing on the 144 rolled designs of the
house-style eval. It misses bands that thin lines cross (three wave strokes in an empty third, faint ripples), dead space beside a
lone footnote, and a scatter whose density is even but whose like motifs line up.
