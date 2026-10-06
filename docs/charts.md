# Charts

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

The `chart` operation turns a table into a bar, stacked, line, area, pie or donut chart. The chart is
a **group of ordinary vector layers** (rectangles, paths, text and thin rules), so every renderer,
export and check treats it like any other group. The data stays attached to the group, and
`chart-data` changes it: one operation fixes one number, and the scale, tick labels, bars, value
labels, totals, gridlines and legend all follow, on the same layers with the same IDs. When the
document is exported to PowerPoint the group becomes a **native chart with an embedded data table**.

```bash
vixl chart bar --name sales --csv cups.csv --title "Cups sold" --x 60 --y 80 --width 1000 --height 560
vixl chart-data --target sales --set Dec=3330            # December's number was wrong
vixl chart stacked-bar --target sales --total-labels      # restyle: same layers, new look
vixl export deck.pptx                                     # the chart is a real chart in PowerPoint
```

```json
{"type": "chart", "name": "sales", "kind": "stacked-bar", "x": 60, "y": 80, "width": 1000, "height": 560,
 "title": "Cups sold", "total_labels": true, "number_format": "#,##0",
 "categories": ["Jan", "Feb", "Mar"],
 "series": [{"name": "Espresso", "values": [1200, 1100, 1250]},
            {"name": "Latte", "values": [800, 760, 820]}]}
{"type": "chart-data", "target": "sales", "set": [{"category": "Feb", "series": "Latte", "value": 790}]}
```

## Kinds

| `kind` | Draws |
| --- | --- |
| `bar` | Vertical bars, one per series in each category (default). |
| `stacked-bar` | Series stacked per category; negatives stack downward. `total_labels` adds each stack's sum. |
| `percent-bar` | Stacks scaled to 100 %. The axis reads 0–100 %; labels show the values. |
| `horizontal-bar`, `stacked-horizontal-bar`, `percent-horizontal-bar` | The same, with the first category on top. |
| `line` | One line per series with point markers; a `null` value leaves a gap. |
| `area`, `stacked-area` | Filled areas from the baseline (translucent) or stacked. Needs two or more categories. |
| `pie`, `donut` | One series; the categories are the slices, labelled with their share. Donuts take `hole` and `center_text`. |

Other spellings are accepted and reported under `normalized` (`column`, `doughnut`, `chartType`,
`labels`/`datasets` from Chart.js, a `data` object…).

## Data

Give the table once, any of three ways. All of them are checked: category labels and series names are
unique, every series has one value per category, values are finite numbers or `null` (a gap).
At most 200 categories and 24 series.

- `categories` + `series` — `[{"name": "Espresso", "values": [...], "color": "#c46a2d"?}]`.
- `table` — rows, header first: `[["", "Espresso", "Latte"], ["Jan", 1200, 800], …]`.
- `csv` — a path **inside the workspace**; the first column (or `category_column`) holds the
  categories and the other columns (or `series_columns`) are the series. Blank cells are gaps;
  thousands separators and a leading `$`, `€` or `£` are read. The file is bound to the chart:
  `chart-data` with `reload: true` reads it again, so the fix is one CSV row plus one operation.
  A path that leaves the workspace is refused (`forbidden`), also through MCP and REST.

## Editing the data: `chart-data`

`target` is the chart group (default: the active layer, which is the chart right after it is drawn).
Several edits can be combined; they apply in this order:

| Field | Effect |
| --- | --- |
| `categories`+`series`, `table`, `csv`, `reload` | Replace the table, or re-read the bound CSV (series colors set by name are kept). |
| `remove_categories`, `remove_series` | Drop them by name. |
| `add_series` | `[{"name", "values", "color"?}]`. |
| `append` | New categories at the end: `[{"category": "Jan", "values": [1, 2]}]`, or `values` as `{series: value}` (missing series stay empty). |
| `set` | Cell edits: `[{"category": "Dec", "series": "Latte", "value": 3330}]`. `series` may be left out on a one-series chart; `value: null` clears the cell. |

An unknown category or series name fails with the available names and the closest match, and the
operation changes nothing (batches are atomic, like every operation).

## What is kept in sync

Everything is recomputed from the data on every `chart` and `chart-data`: a round-numbered value
scale (`min`, `max` and `ticks` steer it; bars and areas always include zero), tick labels and
gridlines, bar and segment geometry (stacked segments tile exactly), value labels, totals, the legend
and its swatches, label wrapping and thinning, and slice angles. Layers are **updated in place**: a
bar keeps its ID when its value changes; new categories add layers, removed ones delete theirs.
Fields the chart does not own survive a redraw: layer styles, effects, opacity, blend mode, masks and
visibility. (A bar whose value is zero or empty has no layer; it is created when the value is not.)
Generated layers are named `NAME/part` and carry a `chart_part` key; do not edit their geometry by
hand, because the next redraw sets it again. Resize a chart with `chart --target NAME --width … --height …`
(not `resize`, which would stretch its text).

The numbers the chart says are on the group as `chart.summary`, so nothing has to be recomputed outside Vixl:

```json
{"totals": {"by_category": {"Jan": 2100, …}, "by_series": {"Espresso": 7230, …}, "grand": 21290},
 "shares": {"Espresso": 44.6247, …},          // pie and donut
 "scale": {"min": 0, "max": 3000, "step": 500, "ticks": [0, 500, …], "format": "#,##0"},
 "layers": 141}
```

## Options

Every option is also accepted by `chart --target NAME` to restyle the chart; set an option to `null`
to clear it.

| Option | Meaning |
| --- | --- |
| `title`, `subtitle` | Top-left, in the heading font and the muted text color. |
| `colors` | Series (pie: slice) colors, any color or `@swatch`. A series' own `color` wins, and an edit that sets `colors` warns which series it does not recolour. The value axis picks round maxima with little headroom (3,330 gives 0–3,500). Default: the document's active palette (colors that stand out from the background), then a color-blind-safe set; one series uses `@accent` when the document has it. |
| `legend` | `auto` (default: for two or more series, and for pies), `none`, `top`, `bottom`, `left`, `right`. `legend_values` adds each total. |
| `value_labels` | `auto` (default: label what fits its bar and does not collide, for charts of up to 60 values), `true` (label everything), `false`; pie/donut: `value`, `percent` (default) or `both`. Inside stacked segments the label color is chosen for contrast. |
| `total_labels` | Stacked charts: each stack's total above it. |
| `gridlines` | On by default. |
| `number_format` | An Excel-style format for ticks and labels: `#,##0`, `0.0`, `0%`, `$#,##0.00`, `#,##0,"K"` (a trailing comma divides by 1,000). The same string is written to the PowerPoint chart. |
| `min`, `max`, `ticks` | Value-axis limits and the approximate number of intervals (2–20, default 5). |
| `value_title`, `category_title` | Axis titles; the value-axis title is rotated beside a vertical axis. |
| `font_size` | Label size in pixels (default: a thirtieth of the chart's shorter side, 10–40); the title is 1.5×, value labels 0.85×. When the document defines a type scale (character styles, e.g. from `type-scale`) the sizes snap to it. |
| `title_font`, `label_font` | A registered font name or the `heading`/`body` role (defaults: heading for the title, body for the rest, so a `font pair` changes their typeface; redraw the chart to re-fit the labels). Files and URLs are not accepted here. |
| `text_color`, `grid_color`, `axis_color`, `background` | Colors. By default text uses `@ink` (or light/dark to suit the canvas), secondary text is faded just far enough to keep 4.5:1, and there is no background. |
| `bar_gap`, `line_width`, `markers`, `hole`, `start_angle`, `center_text`, `padding` | Bar spacing (0–0.9), line thickness, point dots, donut hole (0.2–0.9), first slice's angle clockwise from 12 o'clock, donut text (`{total}` is the sum), outer padding. |

Colors come from the document, so `palette-apply` or a `swatch` change followed by a redraw recolors
the chart; role swatches (`@accent`, `@ink`) recolor it without one.

## Checks and exports

- `check` sees inside the chart: contrast of every label against what is under it, overlaps between
  labels, bounds and legibility (a chart on a large canvas needs a `font_size` that survives the
  320 px thumbnail the legibility check uses). Contrast for a chart's labels is measured in two
  renders per chart rather than two per label.
- PNG, JPEG, WebP, TIFF, SVG and PDF need nothing special: the chart is vector paths and text
  (`pdf_content: "vector"` keeps it vector in a PDF).
- **PPTX**: a chart group becomes a native chart with its categories, series, colors, fonts, scale,
  number formats, gridlines, legend, titles and value labels, plus an embedded workbook with the
  table, so *Edit Data* works in PowerPoint, Keynote and Google Slides. No extra Python package is
  needed (the chart XML and the workbook are written directly). The export report lists
  `charts: {"slide": [{"layer", "native": true}]}`. What cannot be native stays honest:
  total labels are not exported; a donut's center text is a text box over the chart; text boxes or
  shapes added to the group stay shapes on top; a chart that is rotated or flipped is exported as the
  shapes it is made of (`native: false` with the reason), and one with effects, a layer style,
  blending or opacity below 1 is a picture, listed under `raster_fallbacks`, like any other group.
  The chart's labels and legend use PowerPoint's own layout, so positions differ slightly from Vixl's
  render; the data, colors, scale and fonts match.

## Limits

A chart is at most 200 categories by 24 series and must fit the document's layer limit (4,096): a
12 × 4 stacked chart with every label is about 140 layers. Over the limit the operation fails and
names the way out (fewer categories, or `value_labels: false`, `markers: false`). A chart that is too small
for its labels says so; enlarge it or lower `font_size`.
