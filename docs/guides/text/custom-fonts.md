# Making a font

[Documentation home](../../README.md) · [Typography](typography.md) · [Exporting](../output/exporting.md) · [Vector paths](../shapes/vector-paths.md)

Vixl can draw a font as well as use one. Each glyph is ordinary layers (rectangles, pen paths, stroked lines,
pathfinder results, even a text layer set in another face), so every shape and path tool works on letters. The
document's **font design** says which character each glyph is and how it sits on the line. `export` writes a
TrueType, OpenType or WOFF file that other apps can install, and `font-build` embeds the font in the same document,
so you can set text in it straight away.

## A two-letter font in a dozen commands

```bash
vixl new 800x500 --house-style off -o mono.vixl
vixl -p mono.vixl font-design --family 'Mono Block' --em 200 --designer 'Ada Example'
vixl -p mono.vixl font-grid --chars Hi
vixl -p mono.vixl shape rectangle --name h-left --x 65 --y 70 --width 28 --height 140 --fill black
vixl -p mono.vixl shape rectangle --name h-right --x 127 --y 70 --width 28 --height 140 --fill black
vixl -p mono.vixl shape rectangle --name h-bar --x 65 --y 128 --width 90 --height 24 --fill black
vixl -p mono.vixl shape rectangle --name i-stem --x 266 --y 110 --width 28 --height 100 --fill black
vixl -p mono.vixl shape ellipse --name i-dot --x 264 --y 64 --width 32 --height 32 --fill black
vixl -p mono.vixl render --out cells.png
vixl -p mono.vixl export mono-block.otf
vixl -p mono.vixl font-build
vixl -p mono.vixl text add 'Hi Hi' --font Mono-Block --size 100 --x 50 --y 330 --color black
vixl -p mono.vixl render --out specimen.png
```

`font-grid` laid out one cell per character with guides for the ascent, cap height, x-height, baseline and
descent. With `em` 200 the first cell's baseline starts at (50, 210), its cap height is at y 70 (0.7 em above
the baseline), the x-height at y 110, and each cell is 120 px (0.6 em) wide with 50 px between cells. The shapes
are simply drawn inside the cells: the `i` is two shapes, a stem and a dot, merged into one glyph. The export
reports the family, the glyph count, the characters and any warnings (a glyph that draws nothing, a kerning pair
naming a character the font lacks, an image skipped in a cell).

## The font design

`font-design` sets the font's name and metrics. All metrics are canvas pixels, and one pixel is `1000 / em` font
units:

| Field | Default | Meaning |
| --- | --- | --- |
| `family`, `style` | none, `Regular` | Names apps list. `Bold`, `Italic` and `Bold Italic` set the style flags. A family is required to build or export. |
| `em` | 200 | The em, the font's size unit. Text at size 100 draws one em as 100 px. |
| `ascent`, `descent`, `line_gap` | 0.8 em, 0.2 em, 0 | Line spacing above and below the baseline. |
| `x_height`, `cap_height` | 0.5 em, 0.7 em | Metrics for apps, and the guides `font-grid` draws. |
| `side_bearing` | 0.05 em | Space each side of a glyph whose advance is not given. |
| `space` | 0.25 em | Width of the space when no glyph draws it. |
| `weight`, `italic_angle` | 400 (700 for Bold), 0 | Weight class and slant. |
| `version`, `designer`, `copyright`, `license`, `url`, `description` | | Written to the font's name table. |
| `kerning` | none | Pairs of two characters → pixels, e.g. `{"AV": -12}`. Merged into the existing pairs; `0` removes a pair. |

Changing `em` or the vertical metrics later does not move cells `font-grid` already laid out. Run `font-grid`
again (it keeps glyphs for other characters) or set glyph origins yourself.

## Glyphs: cells or named layers

A glyph has an `origin` (the canvas point where its baseline starts) and an `advance` (its width). It takes its
outlines in one of two ways:

- **From its cell.** Without a layer list, the glyph uses every visible vector layer whose centre lies in its cell
  (from the origin across the advance, from the ascent down to the descent) and that reaches at most half a cell
  beyond it, so an overhanging `f` or `j` still counts but a backdrop does not. Images in a cell (a sketch to
  trace over) and layers with the `background` or `decoration` role are skipped, with a warning for images.
- **From named layers.** `font-glyph` with `target` or `targets` uses exactly those layers. A group contributes
  its visible children. Without an `origin` the glyph sits on the layers' bottom edge with a side bearing to the
  left; without an `advance` it is as wide as the layers plus a side bearing on each side. That is the quick
  way to turn drawn icons into an icon font.

```json
[
  {"type": "font-design", "family": "Trail Marks", "em": 100},
  {"type": "shape", "shape": "star", "name": "star-icon", "x": 40, "y": 40, "width": 80, "height": 80, "fill": "black"},
  {"type": "shape", "shape": "heart", "name": "heart-icon", "x": 160, "y": 40, "width": 80, "height": 80, "fill": "black"},
  {"type": "font-glyph", "char": "U+E001", "target": "star-icon"},
  {"type": "font-glyph", "char": "U+E002", "target": "heart-icon"},
  {"type": "font-build", "name": "trail-marks"}
]
```

`char` is one character or a code point (`U+E001`; the Private Use Area U+E000–U+F8FF is the usual home for
icons). `font-glyph` with `origin` and `advance` and no layers defines a cell by hand; `remove: true` drops a glyph.
`font-grid` takes `chars` as a string or a set (`uppercase`, `lowercase`, `letters`, `digits`, `punctuation`,
`ascii`), with `columns`, `advance`, `gap`, `x`, `y` and `guides: false`. It refuses a canvas too small for the
grid and names the size it needs.

## What becomes an outline

A font glyph is one shape with no colour, so:

- Shape fills and strokes both count. A stroked open path becomes its outlined stroke, so monoline lettering
  drawn with `pen` or a path and a `stroke_width` works directly. Lines count by their stroke.
- Pathfinder layers count by their result, and plain text layers by their glyph outlines.
- Everything in a glyph is merged into one outline. Overlaps disappear, and counters drawn as holes (a path with
  an inner contour, or a pathfinder `subtract`) stay holes. A light shape on a dark one does **not** cut a hole:
  use `pathfinder` with `subtract`.
- Colour, opacity, gradients, effects and layer styles are ignored. Layers with masks, clipping or repeats are
  refused (combine them with `pathfinder` first), as are images, rich text and colour emoji.

Hand lettering on paper becomes glyphs through the [drawing](../images/drawing.md) tools: `drawing import` cleans a photo or
scan of the letters, and `drawing vectorize` with `mode: "outline"` and `curves: true` (add `split: "components"`
for one layer per letter) traces them into filled paths. Place the paths in the cells, or name them with
`font-glyph`.

Hidden layers and layers inside hidden groups are left out.

## Building and exporting

| Output | How | Notes |
| --- | --- | --- |
| `.ttf` | `export NAME.ttf` | TrueType, quadratic outlines (converted from Vixl's cubic curves within one font unit). |
| `.otf` | `export NAME.otf` | OpenType with CFF (PostScript) cubic outlines, exactly as drawn. |
| `.woff` | `export NAME.woff` | Compressed TrueType for the web (`@font-face`). |
| `.woff2` | `export NAME.woff2` | Needs the optional `brotli` package (`pip install brotli`). |
| In the document | `font-build [--name NAME] [--format ttf\|otf]` | Embeds and registers the font (default name: the family with spaces as hyphens) so text layers can use it. Run it again after editing glyphs. |

Every font has a `.notdef` box for missing characters and a space. The no-break space (U+00A0) shares the
space's glyph. Kerning becomes an OpenType `kern` feature. Fonts are written with installable embedding
permission (`fsType` 0). Exports refuse to overwrite a file unless `overwrite` is set, as for every format.
Page, artboard, profile, proof and CMYK options do not apply to a font. Over MCP, `vixl_export(path='brand.otf')`
writes the font, and REST `POST /export` takes `format` `TTF`, `OTF`, `WOFF` or `WOFF2`. In Python,
`project.export('brand.ttf', report=report)`.

## Tips

- Draw on the guides: cap-height letters from `font-rN-cap` to `font-rN-baseline`, lowercase from `font-rN-x`.
  Round letters (O, C, S) usually overshoot the baseline and cap height by about 1–2 % of the em so they look
  the same size as flat ones.
- Proof often: `font-build`, then a text layer with a pangram or `HOHOHO` / `nonono` spacing strings, and render.
- Spacing is part of the design: tune `advance` per glyph with `font-glyph --char A --advance 130` (keeping the
  cell's origin), and fix pairs such as `AV`, `To` and `LT` with `kerning`.
