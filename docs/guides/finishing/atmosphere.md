# Scene atmosphere and motifs

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Organic shapes](../shapes/organic.md) · [Looks](looks.md)

A scene reads as designed when it shows the specific thing the brief names and the light around it: lanterns
that glow, a reflection that mirrors the quay, stars that leave the title alone. Each of these is one operation.
Hand-placing dozens of dots, dashes and glows takes a script and still reads as a placeholder.

| Operation | What it makes | Result | Exports |
| --- | --- | --- | --- |
| `haze` | a soft glow band (or round halo) behind a light source; with `form: "fog"`, stacked soft bands of mist that wash out toward the horizon | group `haze`: two radial gradients, placed directly below the light; group `fog`: gaussian gradients in 2-5 bands, below the layers you name | vector gradients everywhere |
| `star-field` | seeded stars of varied size and brightness, a few four-point sparkles, thinning toward the horizon; keeps clear of every text layer | group `stars` of ellipse and sparkle shapes, just above the backdrop | vector |
| `string-lights` | bulbs or paper lanterns hung evenly along a sagging wire or an existing path, each with a lit core and a glow | group `string-lights`: the wire, then per bulb a glow, hanger, cap and body | vector |
| `bokeh` | soft out-of-focus light discs with a brighter rim | group `bokeh` of radial gradients with the screen blend | vector |
| `reflection` | the layers above a horizon mirrored into the water below it, squashed, rippled, broken into bands and faded with depth | one raster layer `reflection` that keeps its settings | an image in SVG, PDF and PowerPoint, as any raster layer |

Every one is deterministic for its `seed`. The groups are ordinary editable layers: recolor, move, hide or delete a
star or a bulb, or re-run the operation with another seed. A reflection mirrors rendered pixels, so it is the one
raster result; it is drawn with the same renderer as the preview and keeps its settings under `reflection`, so after
you change the scene above the waterline, `{"type": "reflection", "target": "reflection"}` re-renders it with the
same seed and settings (any field you pass changes that setting).

Where the new layers go: `haze` sits directly below its light; `string-lights` along a `target` path sits directly
above that path, otherwise below the lowest text layer; `star-field` and `bokeh` sit just above the backdrop (the
full-width sky, sea or background layers at the bottom of the stack). `below: LAYER` puts any of them under a layer
you name. A new `reflection` sits above the layers it mirrors and the water it falls into, and below the copy. `fog`
sits directly below the lowest layer you name in `behind` (the hills, the lighthouse, the trees that must stay crisp),
else below the lowest text layer, so it veils the whole scene and leaves the copy alone.

## Operations, not stack effects

Each of these could have been an effect on a layer's stack (a fog filter, a reflection effect, a light-falloff effect).
They are operations that write ordinary layers because an effect has no parts: one star, one bulb or one band of mist
could not be moved, recoloured, hidden or deleted, an exporter would have to learn to draw each effect (SVG, PDF and
PowerPoint draw gradients, shapes and paths natively and nothing else here), and a re-run with another `seed` could not
keep your edits to the rest. The one exception is the one that is already data: light falloff is the `lighting`
operation, whose lights fall off with a gaussian radius, and it stays that way. A `reflection` mirrors rendered pixels,
so it is the single raster layer, and it keeps its settings so it can be re-rendered.

## A harbor at night

```json
{"width": 1080, "height": 1350, "operations": [
  {"type": "gradient", "name": "sky", "width": 1080, "height": 860, "direction": "vertical",
   "stops": [{"offset": 0, "color": "#060e1c"}, {"offset": 1, "color": "#1d3157"}]},
  {"type": "organic", "preset": "water", "name": "sea", "x": 0, "y": 820, "width": 1080, "height": 530,
   "params": {"tones": ["#1d3557", "#13284a", "#081428"], "amplitude": 0.02, "crest": false}},
  {"type": "shape", "shape": "rectangle", "name": "quay", "x": 0, "y": 760, "width": 700, "height": 62, "fill": "#071223"},
  {"type": "shape", "shape": "lighthouse", "name": "lighthouse", "x": 790, "y": 560, "width": 110, "height": 262, "fill": "#071223"},
  {"type": "shape", "shape": "ellipse", "name": "lamp", "x": 832, "y": 604, "width": 26, "height": 26, "fill": "#ffcf6e"},
  {"type": "text", "name": "title", "text": "Harbor Lights", "size": 110, "color": "#fbf1dc", "x": 150, "y": 330},
  {"type": "star-field", "region": [0, 0, 1080, 700], "count": 120, "seed": 5},
  {"type": "string-lights", "from": [-20, 120], "to": [1100, 140], "sag": 110, "count": 11, "bulb": "lantern",
   "size": 46, "colors": ["#f4b942", "#e8743b", "#d9534f", "#f7d488"], "seed": 2},
  {"type": "haze", "target": "lamp", "strength": 0.5},
  {"type": "reflection", "horizon": 822, "squash": 0.8, "ripple": 0.35, "seed": 1, "tint": "#13284a"}
]}
```

## Fields

**`reflection`**: `horizon` (the waterline, canvas y; required on creation), `targets` (layers to mirror; default every
visible top-level layer above the horizon except text and full-canvas backgrounds), `squash` (0.2-1.5, default 0.8),
`ripple` (sideways displacement, 0-1, default 0.35, growing toward the viewer), `breakup` (horizontal ripple bands, 0-1,
default 0.4), `fade` (0-1, default 0.6), `blur` (vertical smear in pixels, default 0.3% of the canvas height),
`opacity` (default 0.7), `tint` and `tint_amount` (the water colour mixed in), `seed`, `name`, and `target` to re-render.
The reflection reaches as far below the waterline as the canvas allows, so lights high above the horizon land low
in the water and fade; lower `squash` brings them closer to the horizon.

**`haze`**: `target` (the light; or `x`, `y`), `form` (`band`, a wide band as light spreads over a horizon, `round`, or
`fog`), `width`/`height` (default 6x the light's width and at least 15% of the canvas; the band is 45% as tall as
wide), `color` (default the light's fill), `strength` (0-1, default 0.45).

**`haze` with `form: "fog"`** stacks soft horizontal bands, as mist lies between ranges of hills or over still water.
`layers` (2-5, default 3) is the number of bands, the farthest first; `density` (0-1, default 0.5) how thick the fog is;
`color` the colour of the nearest band (default `#dfe6ee`; use the pale colour of the sky at the horizon). The bands
toward the horizon are lighter, less saturated and denser (distance washes colour out, and fog thickens with it), and the
near bands are taller. Each band is a few wide gaussian gradients at seeded positions (`seed`), so the mist drifts
instead of lying in a ruled stripe. `y` is the middle of the zone the bands are stacked over and `height` its height
(defaults 60% and 30% of the canvas; `x` and `width` default to the canvas centre and 110% of its width), or give
`target`, a layer whose box is the zone (the valley, the water). `behind` lists the foreground layers the fog sits
behind, so they stay crisp; for fog between several ranges, run the operation once per gap with `behind` naming the range
in front of that gap, the farther gap in a paler `color`. `strength`, which sets a glow's opacity, is not used.

```json
{"width": 1080, "height": 720, "operations": [
  {"type": "gradient", "name": "sky", "width": 1080, "height": 720, "direction": "vertical",
   "stops": [{"offset": 0, "color": "#9fbfd8"}, {"offset": 1, "color": "#e9eef2"}]},
  {"type": "shape", "shape": "triangle", "name": "far-ridge", "x": 80, "y": 220, "width": 900, "height": 420, "fill": "#7d97ad"},
  {"type": "shape", "shape": "triangle", "name": "near-ridge", "x": 380, "y": 360, "width": 800, "height": 300, "fill": "#2c4452"},
  {"type": "haze", "form": "fog", "y": 520, "height": 240, "layers": 3, "density": 0.55, "color": "#cfdbe6",
   "behind": ["near-ridge"], "seed": 3}
]}
```

**`star-field`**: `region` (`[x, y, width, height]`, default the canvas; or `target`, a layer such as the sky whose box is the region), `count` (default from the area), `size`
(`[smallest, largest]` radius), `opacity` (`[dimmest, brightest]`), `color` (default `#fff6e0`), `sparkles` (default
count/25), `fade` (thin toward the bottom of the region, 0-1, default 0.5), `avoid` (default every visible text,
table and field layer) and `clearance` (default 2.5% of the shorter canvas side), `seed`. No star or sparkle comes
within `clearance` of an avoided layer's box. For snow, use white with `sparkles: 0` and `fade: 0`.

```json
{"type": "star-field", "region": [0, 0, 1200, 500], "count": 90, "color": "#ffffff", "sparkles": 0, "fade": 0, "seed": 9}
```

**`string-lights`**: `target` (a path or shape to hang along; it stays the wire) or `from`, `to` and `sag` (a wire is
drawn; `sag` defaults to 12% of the span), `count` or `spacing` (default 4 bulbs' widths), `size`, `bulb` (`globe`,
`pear` or `lantern`), `colors` (used in turn), `glow` (0-1), `hang` (drop below the wire), `jitter` (seeded
variation of the drop), `wire`, `wire_width`, `seed`. Bulbs are spaced evenly by length along the wire, so they
follow its curve. Two strings at different depths (the back one smaller and dimmer) read as space.

```json
[{"type": "pen", "name": "awning-line", "nodes": [{"point": [60, 220], "out": [400, 420]}, {"point": [1140, 200], "in": [800, 420]}],
  "fill": "transparent", "stroke": "#3b3328", "stroke_width": 3},
 {"type": "string-lights", "target": "awning-line", "count": 12, "bulb": "globe", "colors": ["#ffd77a"], "glow": 0.7}]
```

**`bokeh`**: `region` (or `target`, as for star-field), `count` (default 14), `size` (`[smallest, largest]` diameter, default 4%-12% of the shorter
side), `opacity` (default `[0.2, 0.55]`), `colors`, `softness` (0-1, default 0.3), `blend` (default `screen`),
`avoid`, `seed`.

## Motifs: drawing the thing the brief names

`vixl_reference(brief)` returns `motifs` when a brief implies a setting: the concrete elements to draw, the placeholder
each one replaces, and the catalog shapes, organic presets, object kinds and operations that draw them.
`vixl_reference('motifs')` lists every theme: coffee and cafés, sea and coast, lakes, markets and festivals, night
city, night sky, concerts, bakeries, gardens and botanicals, winter and the holiday season, sport, tech and product
launches, wellness, travel, books and reading, and kids' parties. The knowledge lives in one data file read by the
guidance registry, so the guide, the resources and the capabilities agree.

### Make the motif specific: three questions

Before drawing, answer three questions, each with a drawn element:

1. **What is the object?** The one thing the brief names, with the detail that identifies it: a cup's steam, a leaf's
   veins, a ball's seams, a balloon's knot and string.
2. **What does it emit or reflect?** Steam, a glow, light on the page, motion lines, a shadow, a reflection in water, mist.
3. **What frames it?** The place that holds it: a shelf, a window, a horizon, a pot, a field, a border.

Each theme lists its answers as elements (what to draw, the placeholder it replaces, and the shapes, presets,
operations and object kinds that draw it), in that order. If the preview shows a shape that could be anything, one of
the three answers is missing.

| Brief | Draw | Not |
| --- | --- | --- |
| café, coffee, tea | shape `cup` with shape `steam` above it (object `cup`) | a disc |
| sea, harbor, lighthouse | organic preset `water` (filled bands); shape `lighthouse` with its base between two bands; reflection | stroked wave lines; a tower on a bar |
| winter or night market, festival | `string-lights` with `bulb: lantern`; stalls with a `scalloped-border` awning; `star-field` for snow | dots on a line |
| night city | buildings of varied size with irregular lit windows; `star-field`, `haze` over the skyline, `reflection` | equal boxes |
| sea, coast, lake at dawn | `haze` with `form: "fog"` over the water and behind the nearest headland or trees | a flat grey overlay |
| concert, open mic | shape `microphone` with a `haze` for the spotlight behind its head | a capsule on a stick |
| bakery, bread, pastry | a loaf as a capsule with slanted score marks, a croissant as a `crescent` with segment lines; `steam`; a counter with a scalloped awning | a brown circle |
| garden, plants, botanical | shape `leaf` (veined, on a stem) in two or three greens, organic `fern`, `frond`, `flower`; a pot or wreath | green ovals |
| winter, snow, Christmas | shape `snowflake` at three sizes, `star-field` for the fall, warm `string-lights`, organic `pine` | white dots |
| sport, fitness, marathon | the ball with its seams, `speed-lines` trailing it, the field's lines | a plain circle |
| tech, software, launch | `phone-frame` or `browser-window` with interface blocks, a glow behind the screen, orbit rings | a grey rectangle |
| wellness, yoga, spa | a stack of stones, a lotus or a candle, `haze`, `steam`, one soft shape behind it | a stock silhouette |
| travel, trip, passport | a `map-pin` on the place, a suitcase, a `ticket` or `postmark`, layered hills | a globe |
| books, reading, library | shape `book` (curved pages, text lines, cover edge), a lamp's `haze`, a shelf of varied spines | a rectangle with a line down the middle |
| kids, birthday, party | shape `balloon` in three colours at different heights, `confetti`, bunting | coloured circles on sticks |

The motif shapes `cup`, `steam`, `lighthouse`, `lantern`, `microphone`, `snowflake`, `leaf`, `book` and `balloon` are
catalog shapes like `house` or `bell`: one editable vector outline each, with holes (the cup's handle, the lighthouse's
lantern window and door, the microphone's grille slots, a leaf's veins, a book's lines of text, a balloon's highlight)
so whatever is behind shows through. They are drawn as plain curves, so SVG, PDF and PowerPoint flatten them with the
same evaluator as the preview, and each is meant to read at 24 px as well as at poster size. Like every catalog shape
they stretch to their box; they are drawn at these proportions (width to height):

| Shape | Proportion | Notes |
| --- | --- | --- |
| `microphone` | 0.43 | a stand microphone: slotted grille head, cradle, stem and base |
| `snowflake` | 1 | six arms with two pairs of branches, one merged outline; `thickness` sets the arm width (default 6.5% of the shorter side) |
| `leaf` | 0.63 | a pointed leaf with a stem, cut by a midrib and three pairs of side veins; rotate it for a spray |
| `book` | 1.33 | an open book: two curved pages with a gap at the spine, four lines of text on each and the cover showing below |
| `balloon` | 0.59 | a balloon with a highlight, a knot and a wavy string |

Put a `haze` or a lit ellipse behind the lighthouse's window to light it.

```json
[{"type": "shape", "shape": "balloon", "name": "balloon-front", "x": 440, "y": 300, "width": 190, "height": 325, "fill": "#e63946", "rotation": -6},
 {"type": "shape", "shape": "balloon", "name": "balloon-left", "x": 290, "y": 360, "width": 150, "height": 256, "fill": "#f4c56a", "rotation": -14},
 {"type": "shape", "shape": "snowflake", "name": "flake", "x": 700, "y": 200, "width": 200, "height": 200, "fill": "#14263b", "thickness": 0.09},
 {"type": "shape", "shape": "microphone", "name": "mic", "x": 120, "y": 300, "width": 120, "height": 280, "fill": "#14263b"}]
```

```json
[{"type": "shape", "shape": "cup", "name": "cup", "x": 480, "y": 380, "width": 260, "height": 220, "fill": "#14263b"},
 {"type": "shape", "shape": "steam", "name": "steam", "x": 520, "y": 230, "width": 110, "height": 140, "fill": "#14263b", "opacity": 0.6},
 {"type": "group", "name": "coffee", "targets": ["cup", "steam"]},
 {"type": "object", "target": "coffee", "kind": "cup"}]
```
