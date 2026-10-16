# Scene atmosphere and motifs

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Organic shapes](../shapes/organic.md) · [Looks](looks.md)

A scene reads as designed when it shows the specific thing the brief names and the light around it: lanterns
that glow, a reflection that mirrors the quay, stars that leave the title alone. Each of these is one operation.
Hand-placing dozens of dots, dashes and glows takes a script and still reads as a placeholder.

| Operation | What it makes | Result | Exports |
| --- | --- | --- | --- |
| `haze` | a soft glow band (or round halo) behind a light source | group `haze`: two radial gradients, placed directly below the light | vector gradients everywhere |
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
you name. A new `reflection` sits above the layers it mirrors and the water it falls into, and below the copy.

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

**`haze`**: `target` (the light; or `x`, `y`), `form` (`band`, a wide band as light spreads over a horizon, or
`round`), `width`/`height` (default 6x the light's width and at least 15% of the canvas; the band is 45% as tall as
wide), `color` (default the light's fill), `strength` (0-1, default 0.45).

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
`vixl_reference('motifs')` lists every theme (coffee and cafés, sea and coast, lakes, markets and festivals, night city,
night sky, concerts). The knowledge lives in one data file read by the guidance registry, so the guide, the
resources and the capabilities agree.

| Brief | Draw | Not |
| --- | --- | --- |
| café, coffee, tea | shape `cup` with shape `steam` above it (object `cup`) | a disc |
| sea, harbor, lighthouse | organic preset `water` (filled bands); shape `lighthouse` with its base between two bands; reflection | stroked wave lines; a tower on a bar |
| winter or night market, festival | `string-lights` with `bulb: lantern`; stalls with a `scalloped-border` awning; `star-field` for snow | dots on a line |
| night city | buildings of varied size with irregular lit windows; `star-field`, `haze` over the skyline, `reflection` | equal boxes |

The motif shapes `cup`, `steam`, `lighthouse` and `lantern` are catalog shapes like `house` or `bell`: one editable
vector outline each, with holes (the cup's handle, the lighthouse's lantern window and door) so whatever is behind
shows through. Put a `haze` or a lit ellipse behind the lighthouse's window to light it.

```json
[{"type": "shape", "shape": "cup", "name": "cup", "x": 480, "y": 380, "width": 260, "height": 220, "fill": "#14263b"},
 {"type": "shape", "shape": "steam", "name": "steam", "x": 520, "y": 230, "width": 110, "height": 140, "fill": "#14263b", "opacity": 0.6},
 {"type": "group", "name": "coffee", "targets": ["cup", "steam"]},
 {"type": "object", "target": "coffee", "kind": "cup"}]
```
