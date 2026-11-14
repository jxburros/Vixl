# Charts

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

The `chart` operation turns a table into a bar, stacked, line, area, pie or donut chart. The chart is
a **group of ordinary vector layers** (rectangles, paths, text and thin rules), so every renderer,
export and check treats it like any other group. The data stays attached to the group, and
`chart-data` changes it: one operation fixes one number, and the scale, tick labels, bars, value
labels, totals, gridlines and legend all follow, on the same layers with the same IDs.
`chart-emphasis` makes chosen categories stand out, and operations can name a bar, slice or label by its
series and category. When the
document is exported to PowerPoint the group becomes a **native chart with an embedded data table**.

## Shared datasets

Use `dataset` when charts, tables and callout text must agree. A named dataset holds a numeric table, an explicit
snapshot of a workspace CSV, or a live reference to another chart. Bind a chart or table with `data: "sales"`;
the generated parts remain ordinary editable layers. One dataset edit redraws every dependent in the same atomic
apply, keeping the existing part IDs and styles. Edit shared values with `dataset`; `chart-data` and `table-data`
refuse cell edits while bound. Supplying a new inline `table` or `csv` detaches a consumer.

```json
[
  {"type":"dataset","name":"sales","table":[["Month","Tea","Coffee"],["Jan",10,30],["Feb",20,40]]},
  {"type":"chart","name":"sales-bars","data":"sales","width":400,"height":300},
  {"type":"chart","name":"sales-shares","kind":"donut","data":"sales","derive":{"kind":"share","by":"series"},"x":420,"width":350,"height":300},
  {"type":"text","name":"sales-total","text":"Total: ${data.sales.total|number}","size":24,"y":340},
  {"type":"dataset","name":"sales","set":[{"category":"Jan","series":"Tea","value":70}]}
]
```

`derive` aggregates into one series. `by: "series"` produces one category for each original series;
`by: "category"` (the default) produces one for each original category. `sum` totals the group, `max` takes its
largest nonempty cell, and `share` divides each group total by the grand total, giving fractions from 0 to 1.
Shares require non-negative data; all-zero data gives zero shares. Null cells are omitted from aggregates.
`derive: null` restores the original dataset. Derivations work on both charts and tables.

Text fields use the existing filters: `${data.sales.total|number}`, `${data.sales.max.value|number:2}`,
`${data.sales.max.label}`, `${data.sales.max.series}`, and `${data.sales.Tea.Jan}`. Dataset names use letters,
numbers, underscores or hyphens. In series/category field segments, punctuation and spaces become hyphens,
preserving case: `Cold brew` becomes `Cold-brew`. Ambiguous keys are refused. Empty cells have no value; use
`|default:—` to show a fallback. The `placeholders` check reports a missing dataset key as a fix. Escape a literal
field with `$${data.sales.total}`.

`dataset` accepts `table`, `categories` plus `series`, `csv` (with optional `category_column` and
`series_columns`), or `from` naming a chart. `from` follows source-chart edits, including its derivation, and cycles
are refused. CSV data is saved in the document and only re-read with `action: "reload"`; rendering stays offline.
`action: "remove"` refuses removal while a chart or table needs the dataset. Documents hold at most 64 datasets,
each with up to 200 categories and 24 series. The CLI exposes the same fields:

```bash
vixl dataset sales --csv cups.csv
vixl chart bar --name sales-bars --data sales
vixl table --name sales-table --data sales
vixl dataset sales --set Dec:Tea=3330
vixl dataset sales --action reload
```

## Individual charts

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

When many documents take their numbers from one keyed CSV (a price list, a product sheet), the `data-sync` workflow
binds it to a group or a campaign and re-checks and re-exports only the documents whose rows changed; see
[sync from a data source](../automation/production.md#sync-from-a-data-source).

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

## Addressing marks by data

A chart's parts can be named by what they stand for instead of by layer name. Wherever an operation takes
`target` or `targets`, a chart mark is an object:

```json
[
  {"type": "chart", "name": "sales", "width": 800, "height": 450,
   "table": [["Month", "Tea", "Coffee"], ["Nov", 10, 30], ["Dec", 20, 40]]},
  {"type": "opacity", "target": {"chart": "sales", "series": "Tea", "category": "Dec"}, "value": 0.5},
  {"type": "blur", "target": {"chart": "sales", "category": "Nov"}, "radius": 2},
  {"type": "hide", "target": {"chart": "sales", "series": "Coffee", "part": "legend"}}
]
```

| Field | Meaning |
| --- | --- |
| `chart` | The chart group, by name or ID (required). |
| `series`, `category` | Names as the data has them. Leave one out to mean all of them: `{chart, category}` is every bar of that category, `{chart, series}` a whole series, `{chart}` every data mark. |
| `part` | `bar`, `slice`, `point` (a line's marker), `line`, `area`, `value` (a value or slice label), `total`, `legend` (the entry's swatch and label), `category-label` (the axis label) or `callout`. Without it, the data marks: bars, slices, points, lines and areas. |

An address stands for the layers it names when the operation runs, so it can name a chart drawn earlier in
the same batch. A per-layer operation (`opacity`, `hide`, the effects ...) is applied to each of them and a
joint one (`group`, `align` ...) takes them together; an operation that takes one layer (`rename`) needs an
address that names exactly one and says how many it found otherwise. A line or an area belongs to a series,
not to a category, so `{series, category}` on a line chart is the point. An unknown series or category fails
with the valid names and the closest match, like `chart-data`; an address that names nothing the chart draws
(a value label on a chart without labels) lists the parts the chart has.

Addresses follow the data. Each generated layer records what it stands for (`chart_mark`: `part`, `series`,
`category`), and a redraw matches layers by that, not by position: after `chart-data` adds, removes or
reorders rows, the layer of Tea in December is still the layer of Tea in December, with its ID and whatever
was added to it. What the chart owns is still set again on every redraw (fill, geometry, text), so use an
address for what survives (opacity, effects, blend mode, visibility), and `chart-emphasis` or the series
colours for colour.

In Python, `vixl.plugins.charts.charts.resolve_mark(project, address)` returns the layer IDs.

## Emphasis: `chart-emphasis`

"Make this one stand out" is one operation: the categories in `focus` keep their colours, every other mark
is muted, and `annotate` sets a callout beside each focus mark.

```json
[
  {"type": "chart", "name": "sales", "width": 800, "height": 450,
   "categories": ["Sep", "Oct", "Nov", "Dec"], "series": [{"name": "Cups", "values": [2100, 2400, 2900, 3330]}]},
  {"type": "chart-emphasis", "target": "sales", "focus": ["Dec"], "annotate": "Best month: ${value}"},
  {"type": "chart-data", "target": "sales", "set": [{"category": "Dec", "value": 3410}]}
]
```

```bash
vixl chart-emphasis Dec --target sales --annotate 'Best month: ${value}'
vixl chart-emphasis --target sales --clear
```

| Field | Meaning |
| --- | --- |
| `target` | The chart group (default: the active layer). |
| `focus` | Categories to keep in colour (the slices of a pie or donut). `[]` removes the emphasis and restores the chart exactly. |
| `series` | Limits the focus to one series: with `focus`, that series' marks in those categories; alone, the whole series (one line among several). `null` removes the limit. |
| `mute` | How the rest is drawn: `fade` (default: the colour mixed toward the chart's background) or `desaturate` (a grey of the same lightness). |
| `opacity` | For `fade`: how much of a muted mark's own colour stays, 0-1 (default 0.35; `"35%"` is read as 0.35). It is a colour mix, not layer opacity, so muted marks stay opaque and every export draws the same colour. |
| `annotate` | Callout text for each focus mark. `${value}`, `${percent}` (the share of the chart's total), `${category}` and `${series}` are filled in from the data, with the chart's `number_format`. `null` removes it. |

- **What counts as in focus.** A mark is in focus when it matches the focus on every name it has. A bar,
  point or slice has a series and a category; a line or area has only a series, so a category focus leaves
  the lines in colour and marks the point (a larger dot ringed in the background colour, also on area charts,
  which have no markers); a stack's total has only a category. Legend swatches follow their series (or, on a
  pie, their slice). Value labels beside muted marks take the chart's secondary text colour.
- **Callouts.** With one series in focus (or a one-series chart) the callout speaks for that mark and takes
  the place of its value label; otherwise it speaks for the category and `${value}` is the category's total.
  It sits above a bar, stack or point (below a negative one), past the end of a horizontal bar and where the
  slice label would be on a pie or donut; the chart reserves the room, and automatic value labels keep clear
  of it. Other fields such as `${data.NAME.total}` stay ordinary merge fields of the callout's text layer.
- **It is part of the chart.** The emphasis is stored with the chart's data and options, so `chart-data`,
  a `dataset` edit and a restyle keep it, on the same layers. Sending the operation again changes only the
  fields it names. When the data loses a focus category or the focus series, the emphasis drops it and says
  so under `warnings`; with nothing left in focus it is removed.
- **Checks.** `check --checks color_vision` reports an emphasised chart whose focus and muted marks look
  alike, to typical vision or with a colour-vision deficiency (`emphasis-indistinct`: lower `opacity` or
  use `desaturate`), and one whose muted marks nearly vanish into the background (`emphasis-faint`: raise
  `opacity`). `layer-intent` with `color_vision_safe` on the chart accepts it.
- **Summary.** `chart.summary.emphasis` records the focus, the mute mode and the colours drawn
  (`focus_colors`, `muted_colors`, and the `surface` they are judged against).
- **Kinds.** Every chart kind takes it. A table, a key-value list or any other group is refused: it is not
  a chart.

## Placement

A chart's group is placed where `x`, `y`, `width` and `height` say. Fields left out start inside the
document's safe area, inset by two spacing units (about one body size): a chart drawn with no geometry
fills the safe area with that padding, so it passes the `safe_area` check as created. Pass
`"x": 0, "y": 0` with the canvas `width` and `height` for the full canvas. A canvas without a safe area keeps the whole canvas.

## What is kept in sync

Everything is recomputed from the data on every `chart` and `chart-data`: a round-numbered value
scale (`min`, `max` and `ticks` steer it; bars and areas always include zero), tick labels and
gridlines, bar and segment geometry (stacked segments tile exactly), value labels, totals, the legend
and its swatches, label wrapping and thinning, and slice angles. Layers are **updated in place**: a
bar keeps its ID when its value changes; new categories add layers, removed ones delete theirs, and a
reorder keeps each series and category on its own layer (see [addressing marks by data](#addressing-marks-by-data)).
Fields the chart does not own survive a redraw: layer styles, effects, opacity, blend mode, masks and
visibility. (A bar whose value is zero or empty has no layer; it is created when the value is not.)
Generated layers are named `NAME/part` and carry a `chart_part` key (and `chart_mark` when they stand for a
series or category); do not edit their geometry by
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
| `colors` | Series (pie: slice) colors, any color or `@swatch`. A series' own `color` wins, and an edit that sets `colors` warns which series it does not recolour. The value axis picks round maxima with little headroom (3,330 gives 0–3,500). Default: the document's active palette, else the palette its layout or rolled direction used (colors that stand out from the background), then a color-blind-safe set; one series uses `@accent` when the document has it. |
| `legend` | `auto` (default: for two or more series, and for pies), `none`, `top`, `bottom`, `left`, `right`. |
| `legend_values` | Draws the legend as a [key-value list](../layout/containers-and-templates.md#key-value-lists): swatch and name flush left, each total right-aligned in one column and, for pies and donuts, each share right-aligned in another, with a hairline rule between rows. It is the same geometry as the `key-value-list` operation, so a chart's value legend and a separate list agree. It appears where the `legend` does (a single series on `auto` or `legend: "none"` draws none). Beside the plot it takes at most half the chart's width (names wrap). On a pie or donut the `auto` value labels around the ring are left out, since the list already pairs every name with its number and share; `value_labels: "percent"` (or `value`, `both`, `true`) keeps them. |
| `value_labels` | `auto` (default, for charts of up to 60 values: decided for the whole chart so labels thin evenly. Every value is labelled if the labels fit their marks without colliding, at a smaller size (down to about 0.6 × `font_size`) when that is what fits; on a line chart, otherwise the largest series keeps its labels above its points and the others put theirs below their points; otherwise whole series, the largest first; otherwise every second (third ...) value of the largest series; otherwise none. A series never keeps labels on only some of its marks, and on a line chart a label never rests on another series' line or marker (its own line may run under it). Value labels may overlap the chart's own areas and bars, which `check` does not report), `true` (label everything), `false`; pie/donut: `value`, `percent` (default) or `both`. Inside stacked segments the label color is chosen for contrast. |
| `total_labels` | Stacked charts: each stack's total above it. |
| `gridlines` | On by default. |
| `number_format` | An Excel-style format for ticks and labels: `#,##0`, `0.0`, `0%`, `$#,##0.00`, `#,##0,"K"` (a trailing comma divides by 1,000). The same string is written to the PowerPoint chart. |
| `min`, `max`, `ticks` | Value-axis limits and the approximate number of intervals (2–20, default 5). |
| `value_title`, `category_title` | Axis titles; the value-axis title is rotated beside a vertical axis. |
| `font_size` | Label size in pixels (default: a thirtieth of the chart's shorter side, 10–40); the title is 1.5×, value labels 0.85×. When the document defines a type scale (character styles, e.g. from `type-scale`) the sizes snap to it. |
| `title_font`, `label_font` | A registered font name or the `heading`/`body` role (defaults: heading for the title, body for the rest, so a `font pair` changes their typeface; redraw the chart to re-fit the labels). Files and URLs are not accepted here. |
| `text_color`, `grid_color`, `axis_color`, `background` | Colors. By default text uses `@ink` (or light/dark to suit the canvas), secondary text is faded just far enough to keep 4.5:1, and there is no background. |
| `bar_gap`, `line_width`, `markers`, `hole`, `start_angle`, `center_text`, `padding` | Bar spacing (0–0.9), line thickness, point dots, donut hole (0.2–0.9), first slice's angle clockwise from 12 o'clock, donut text (`{total}` is the sum), outer padding in pixels (default two spacing units of the label size, about one label size). |

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
  total labels are not exported; a donut's center text is a text box over the chart; an
  [emphasis](#emphasis-chart-emphasis) is native point colours (muted bars, slices and markers, a larger
  marker on a line's focus point) and its callouts are text boxes over the chart, which the report notes;
  text boxes or
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

## Tables

`table` lays rows out as a **group of ordinary vector layers** in the same way: cell text, a header
band, zebra bands and thin rules, sized together so columns line up and rows grow to fit wrapped
text. The rows stay attached to the group under `table`, and `table-data` changes them on the same
layers with the same IDs. Menus, price lists, pricing tables, schedules and spec sheets are one
operation each, and a price change is one more.

```bash
vixl table --name menu --table '[["Item","Price"],["Espresso",3.25],["Flat white",4.5],["Tea",3]]' --align left,decimal --width 520
vixl table-data --target menu --set Tea:Price=3.5
```

```json
{"type": "table", "name": "menu", "x": 60, "y": 80, "width": 520,
 "table": [["Item", "Price"], ["Espresso", 3.25], ["Flat white", 4.5], ["Tea", 3]],
 "columns": [{"width": "1fr"}, {"align": "decimal", "format": "$0.00"}], "zebra": true}
{"type": "table-data", "target": "menu", "set": [{"row": "Tea", "column": "Price", "value": 3.5}],
 "append": [{"Item": "Mocha", "Price": 4.75}]}
```

- **Rows**, once: `table` (a list of rows; the first is the header unless `header: false`) or `csv` (a
  workspace CSV; `csv_columns` picks and orders columns). `table-data` with `reload: true` rereads the CSV.
- **Columns**: `columns` holds one `{width, align, format}` per column. `width` is pixels, `auto` (fits
  its widest cell, the default) or a share of what is left (`"1fr"`, `"2fr"`). With a table `width`,
  spare room widens the auto columns and a shortfall narrows them toward their longest word (text
  wraps); a table that still does not fit warns and reports `summary.overflow`. `align` is `left`,
  `center`, `right` or **`decimal`**: figures share their decimal point, and a whole number ends where
  the point would be, which is what a price list needs. Numeric columns right-align by default.
  `format` (or `number_format` for every numeric column) is the Excel-style format charts use.
  `leader` (such as `"."`) runs a dot leader from the end of each body cell to the next cell's text in the
  row, so a menu needs no hand-drawn dots: `"columns": [{"width": "1fr", "leader": "."}, {"align": "decimal"}]`.
  The dots sit on a grid from the column's left edge, so every row's dots line up; each row's leader is a
  text layer (`leader-ROW-COLUMN`), and `summary.leaders` counts them.
- **Look**: `font_size`, `header_font_size`, `header_font` (default the heading role), `body_font`,
  `text_color`, `header_color`, `header_fill`, `fill`, `zebra` (`true` or a color), `borders`
  (`horizontal`, the default; `all`, `outer`, `header` or `none`), `border_color`, `border_width`,
  `padding` and `row_height` (a minimum). `table` with `target` restyles; a `null` option returns to
  the default.
- **`table-data`**: `set` (`row` is a body row number from 1 or the text of its first cell, `0` the
  header; `column` is a number or the header text), `append` (a list of cells or `{column: value}`),
  `remove_rows`, `add_columns` (`{name, values}`), `remove_columns`, `reload`, or new `table`/`csv` rows.
  Cells keep their positions, so editing one value moves nothing else.
- `inspect` the group for `table.summary`: `column_widths`, `row_heights`, `aligns`, `font_size` and `overflow`.
- **Exports**: PNG, SVG and PDF draw the layers (vector text and rules). **PPTX writes a native table**
  with the same column widths, row heights, fonts, colors, fills and rules, editable in PowerPoint,
  Keynote and Google Slides; the export report lists it under `tables` (decimal columns are
  right-aligned there, and a leader is written into its cell as characters that stop at the cell edge). A rotated or flipped table, or one whose layers carry effects, exports as its shapes.
- `check` sees every cell like any other text (contrast is measured in two renders per table).
  Up to 200 body rows by 24 columns.
