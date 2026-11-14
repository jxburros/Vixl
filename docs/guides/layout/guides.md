# Guides, grids and placement

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

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

`rect: [x, y, width, height]` (CLI `--rect X Y W H`) is shorthand for a closed rectangular `path` guide. Any guide
may carry a `role` from a printer's template; see [a printer's template](#a-printers-template-guide-roles).

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
| `within`, `box`, `margin` | Instead of `guide`: place inside a layer. The anchor lands on the same point of that layer's content box (`box: "bounds"` for its whole box), inset by `margin` pixels; see [content boxes](../shapes/vector-paths.md#content-boxes). |

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

Guides with a print role (`safe`, `keep-out`, `fold`) are enforced by the default `safe_area` check, not by these
two: see [a printer's template](#a-printers-template-guide-roles).

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

## A printer's template: guide roles

A print-on-demand template (a book wrap with back, spine and front; a mug; a box) marks its rules as coloured
dashed lines: the board or trim edge, a safe area per panel, a barcode keep-out, the fold lines. A guide can say
which of those it is, and the default `safe_area` check then enforces it.

| Role | Guide | What `check` reports (`safe_area`) |
| --- | --- | --- |
| `safe` | A closed outline (`rect`, a closed `path`, a circle): one per panel. It need not be a rectangle: a safe area with a barcode notch cut out is an eight-corner path | `outside-safe-guide`: a layer's ink leaves the safe outline it belongs to (the one it overlaps most). `outside-safe-guides`: it lies in no safe outline at all (on the spine, in the bleed) |
| `keep-out` | A closed outline: the barcode box, a hinge zone | `keep-out`: a layer's ink reaches into it |
| `fold` | A line: an axis guide, a segment | `crosses-fold` (review): a text layer or a `role: title` layer runs across it. Artwork may wrap around a spine |
| `trim`, `bleed` | Any guide | Nothing: they label the cut edge and the bleed edge on the overlay and in a saved guide set |

```bash
vixl guide front-safe --rect 1890 150 1500 2100 --role safe
vixl guide barcode --rect 300 1900 600 380 --role keep-out
vixl guide spine-left x 1740 --role fold
vixl check --checks safe_area
vixl render --out guides.png --show-guides     # safe green, keep-out red, folds orange, trim and bleed magenta
```

```json
[{"type": "guide", "name": "front-safe", "rect": [1890, 150, 1500, 2100], "role": "safe"},
 {"type": "guide", "name": "back-safe", "role": "safe", "kind": "path",
  "d": "M 150 150 L 1650 150 L 1650 2250 L 1000 2250 L 1000 1850 L 250 1850 L 250 2250 L 150 2250 Z"},
 {"type": "guide", "name": "barcode", "rect": [300, 1900, 600, 380], "role": "keep-out"},
 {"type": "guide", "name": "spine-left", "axis": "x", "position": 1740, "role": "fold"}]
```

- Ink is what the layer draws: its geometry with strokes, grown by what its effects and layer styles paint around
  it (a blur, a drop shadow, an outer glow). Text is an error, other layers a warning; a layer marked
  `layer-intent allow_crop`, or non-text decoration, reports as information.
- A non-text layer that covers a whole safe or keep-out outline is a backdrop running under it and is not reported:
  a cover image fills its panel and bleeds off it, and the printer's barcode box sits on top of it.
- Once a document has a `safe` guide, the safe guides are the safe area: the size preset's own inset is no longer
  checked, unless you pass `safe_area` yourself.
- `safe` and `keep-out` name an area, so they need a closed guide; an axis line with one of them is refused with
  the way to draw it. Spellings such as `keep_out`, `barcode`, `spine` and `cut` are accepted and reported under
  `normalized`.

### Importing the template

The `guides-import` workflow reads the lines out of the template file. Call it once without a mapping to see what
the template draws with, then map each colour to a role:

```bash
vixl guides-import wrap-template.png            # lists the line colours (and a PSD's layers and ruler guides)
vixl guides-import wrap-template.png --color '#00a651=safe' --color '#ed1c24=keep-out' \
     --color '#00aeef=fold' --color '#ff00ff=trim' --save acme-journal-wrap
vixl check --checks safe_area
```

```json
{"workflow": "guides-import",
 "request": {"source": "wrap-template.png",
             "colors": {"#00a651": "safe", "#ed1c24": "keep-out", "#00aeef": "fold", "#ff00ff": "trim"},
             "save": "acme-journal-wrap", "description": "Acme hardcover journal, 6 x 9 in wrap"}}
```

MCP: `vixl_apply(workflow="guides-import", request={…})`. The result lists the guides it wrote (`guides`, `counts`
per role), the `scale` from template pixels to the canvas and `warnings`.

- **What is read.** Dashed or solid horizontal and vertical lines of the mapped colour (`tolerance`, default 40
  of 255 per channel, takes in the anti-aliased edge). Lines whose ends meet become one closed outline, each the
  smallest outline around an area, so a safe area with a notch stays one eight-corner guide and two boxes sharing
  an edge are two guides. A line that closes nothing becomes an axis guide when it spans the template, else a
  segment. Diagonal and curved lines are not read: draw those with `guide kind: path`.
- **What is not a line.** Lettering and patches in a line colour: anything thicker than `max_thickness`, anything
  with more of the colour right beside it, and short strays that close no outline (the result counts them).
  `gap` is the widest dash gap bridged and `min_length` the shortest line kept.
- **Whole pixels.** Positions are the centre of each line, on whole canvas pixels. A template at another
  resolution is scaled onto the canvas when the proportions agree (`fit: "scale"`, the default); `fit: "stretch"`
  scales each axis on its own and `fit: "none"` keeps template pixels. Make the document at the template's
  proportions first (`vixl new 5400x2475 -o wrap.vixl`).
- **Names.** `safe-1`, `safe-2`, `fold-1` …: numbered per role from left to right, then top to bottom, so the
  back cover of a wrap is `safe-1` and the front `safe-2`. `name` puts a prefix before them; `replace: true`
  removes the document's earlier role guides first; `dry_run: true` only reports.
- **PSD templates.** `layers: {"Safe Area": "safe"}` reads whatever a named layer draws (in any colour) as lines,
  `ruler_guides: "fold"` takes the file's ruler guides as axis guides with that role (`plain`: no role), and
  `colors` works on the flattened picture as for a PNG. Only that much of the PSD is read (8-bit RGB or greyscale,
  raw or RLE): a PSB, a 16-bit or CMYK file is refused with the way out, which is a flattened PNG of the template.

### Guide sets: the same product again

`save` stores the imported guides as a **guide set**, a `guide-sets` resource holding the guides and the canvas
size they were made for. `guide-set-save` saves the role guides of any document the same way (`guides: [names]`
picks others), and `resource-list`, `resource-get` and `resource-save` with `kind: "guide-sets"` list, read and
write them like other [resources](agent-resources.md). The `guide-set` operation puts one on a document:

```bash
vixl guide-set acme-journal-wrap                # same proportions at any resolution: scaled to whole pixels
vixl guide-set acme-journal-wrap --replace      # drop the document's other role guides first
vixl guide-set-save my-box-dieline --guides lid-safe base-safe glue-flap
```

As an operation: `{"type": "guide-set", "name": "acme-journal-wrap"}`, with `fit` (`scale`, `stretch`, `none`),
`prefix` (to hold two sets side by side) and `replace`. It is one undo step, and a canvas with other proportions
is refused rather than guessed at.

## Composition

The `composition` family is on by default. It reports what reads as "not designed" even when every other check
passes, as `review` warnings: they never fail a plain `check`, but they fail the `final` profile (and any run
with `fail_on: review`) until they are fixed or waived with a reason. Distances are in the craft spacing unit, half
the document's body size (`craft.spacing.unit` in the [house style](../../project/house-style.md)). Five codes
measure space (`dead_band`, `margin_drift`, `uneven_rhythm`, `crowding`, `clumped_scatter`) and four measure
hierarchy (`flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`).

| Code | What it finds | Threshold |
| --- | --- | --- |
| `dead_band` | An empty horizontal band between content blocks, or between content and an edge, from the free rectangles of `spatial` | At least 6% of the frame's height, 4 units and 2.25× the median gap between stacked blocks (the median-gap term is capped at 20% of the frame, so airy spacing never licenses a quarter-page band); across a third of the content width (a narrower band only when artwork, not a line of text, closes its sides); an edge band must also be 1.75× the opposite margin. Only frames with two or more lines of type whose blocks fill half their height, and bands up to 42% of it; except a hole: an interior band of 22–70% of the frame's height with type directly above and below it (a headline over an empty middle; a panel that holds text, such as a date block, closes it as text does; under 30% both sides must carry copy, so a credit line far below a headline is a minimal composition, not a hole), reported in any frame and judged against the other gaps |
| `margin_drift` | Stacked text, rules, charts, images and free-standing marks whose left edges (right edges of right-aligned text, centres of centred text) are close but not equal | More than 2 px and at most 2 units apart |
| `uneven_rhythm` | A stack of three lines where the middle line sits further from the line above it, which it matches more closely in size, than from the line below (a first name, a last name and a company); for lines of one size, gaps up to 3 units that differ. A subtitle tight under its title and away from what follows is by design. Also a small block (secondary text, a row of dots, a subtitle under a display title 2.5 times its size) as far from the block above as from the one below, between blocks of other kinds, so it belongs to neither | Gaps differing by 1.6× and 2 units (1 unit for lines of one size); a floating block has gaps of at least 3 units on both sides, within 1.5× of each other |
| `crowding` | A rule, band or heading less than half a unit above the text below it | Half a unit |
| `clumped_scatter` | A `pattern-scatter` or `scatter` whose motifs bunch in some cells of the tile and leave others empty | Coverage varies by more than 0.6 (coefficient of variation over 4×4 cells); seeded `pattern-scatter` tiles stay under 0.5 |
| `flat_hierarchy` | Two or more text blocks whose largest text is barely larger than the body: the type has no clear steps | The largest size is under 1.6× the body size (`type-scale` base, else the canvas rule). The largest lines each sitting in a card of their own (name badges, a row of cards) are a series, and initials set in a mark are part of the mark |
| `single_weight` | Three or more text blocks in one face and one weight (no bold, no second face): size is the only contrast | Counted from the font files each run is drawn in; the bundled proofing font is the `fonts` check's finding, and two registered names sharing one file cannot be told apart, so neither is judged |
| `no_focal` | The two heaviest blocks of a page of type and pictures weigh about the same, so the eye has two places to start | A block of type weighs its size² × the square root of its characters (up to 40) × its size over the body size × its contrast against what it sits on; a picture weighs its area. The second is within 15% of the first and the third is lighter; three equals are a series. Not judged where non-text art covers over 8% of the canvas |
| `accent_unused` | The page is built on the document's palette (a visible layer takes one of its colours) and the accent its rolled direction chose is drawn nowhere: no visible layer, nor the canvas, uses `@accent`, `@accent-text` or their colours. With two or three accents, the same for `@accent-2` and `@accent-3` (their layout defines them only where it draws them; `values.role` names the one missing) | At least three blocks and a direction whose accent is not `none` (for the first accent) and whose `accent_count` is not 0. A page in its own colours (hex everywhere) is not asked for the document's accent, and pure white and black do not count as the palette |

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
regions; add `preview=true` and their real-size crops follow the preview ([interfaces](../../reference/interfaces.md)). Workflow
`repair-layout` repairs most spacing findings (snap the drift, re-space the stack, open the gap, spread the band, thin the
tile) without adding any; the four hierarchy codes are judgement calls (which line leads, which weight, where the accent
goes), so it applies nothing for them and lists `suggestions` with the finding under `reviews_remaining`; see [layout
repair](../../reference/agent-trust.md#layout-repair). A deliberate finding (an optical
indent, a field of space on purpose) is accepted with a reason, on the layer (`layer-intent waive`) or the
document:

```json
{"type": "waiver", "check": "composition", "reason": "the open lower half is the quiet field of this layout"}
```

The thresholds were tuned on the [craft backtest](../../../evals/craft_backtest/README.md): reconstructions of the 16
round-1 Vixl documents of the tool comparison with the defects the blind judges named. Of the 21 composition
defects there, the family catches 12 (dead band 5 of 10, margin drift 4 of 5, uneven rhythm 2 of 4, crowding 1 of
1, clumped scatter 0 of 1) with no false findings, and it finds nothing on the 144 rolled designs of the
house-style eval. It misses bands that thin lines cross (three wave strokes in an empty third, faint ripples), dead space beside a
lone footnote, and a scatter whose density is even but whose like motifs line up.

The four hierarchy codes were gated on the same backtest and landed with no false finding, but it cannot show what
they catch: no judged defect of the reconstructions is a hierarchy one, and the reconstructions are set in the proofing font and carry no
rolled direction, so `single_weight` and `accent_unused` cannot fire there at all. On the 20 documents the closest
`flat_hierarchy` call is 2.13× the body (the limit is 1.6×) and no page has two heaviest blocks within 15% of each
other with a lighter third. The 144 rolled designs of the house-style eval stay free of all nine codes, and of the four
hierarchy codes also when the heading and the body are given two different stand-in faces (the eval's own stand-ins
share one file, which `single_weight` cannot judge).
