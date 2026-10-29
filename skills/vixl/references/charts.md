# Charts

For several charts, tables and numeric callouts, define one `dataset` (`name`, `table` or workspace `csv`) and bind
consumers with `data: "NAME"`. `dataset` cell edits (`set: [{category, series, value}]`) update them atomically.
`derive: {kind: "sum"|"share"|"max", by: "series"|"category"}` aggregates to one series; `share` yields fractions.
Text reads `${data.NAME.total|number}`, `.max.value`, `.max.label`, `.max.series`, or `.SERIES.CATEGORY` (spaces in
labels become hyphens). Missing keys need a fix; `|default:TEXT` supplies an intentional fallback.
CSV reload is explicit (`action: "reload"`); `from: "chart-name"` follows another chart and refuses cycles.
Supplying inline data detaches a consumer; bound consumers refuse independent `chart-data`/`table-data` cell edits.

Use `chart` for any bar, line, area, pie or donut instead of drawing shapes and computing heights,
totals and percentages yourself. The chart is a group of ordinary vector layers bound to a table;
fixing a number is one operation and nothing is recomputed by hand. Full reference: `docs/guides/output/charts.md`;
`vixl_reference('capabilities', name='charts')` lists the chart, table and key-value operations with the `charts` guidance.

```json
{"type": "chart", "name": "sales", "kind": "stacked-bar", "x": 60, "y": 80, "width": 1000, "height": 560,
 "title": "Cups sold", "total_labels": true, "number_format": "#,##0",
 "categories": ["Jan", "Feb", "Mar"],
 "series": [{"name": "Espresso", "values": [1200, 1100, 1250]}, {"name": "Latte", "values": [800, 760, 820]}]}
{"type": "chart-data", "target": "sales", "set": [{"category": "Feb", "series": "Latte", "value": 790}]}
{"type": "chart", "name": "split", "kind": "donut", "csv": "cups.csv", "center_text": "{total}\ncups", "legend": "bottom"}
```

- `kind`: `bar`, `stacked-bar`, `percent-bar`, `horizontal-bar`, `stacked-horizontal-bar`,
  `percent-horizontal-bar`, `line`, `area`, `stacked-area`, `pie`, `donut`.
- Data, once: `categories` + `series`, `table` (header row first), or `csv` (a workspace path; first
  column = categories, other columns = series; blanks are gaps). `chart-data` with `reload: true` rereads the CSV.
- `chart-data` edits in place: `set` (`category`, `series`, `value`), `append`, `remove_categories`,
  `add_series`, `remove_series`, `reload`, or a whole new table. Layer IDs survive; unknown names
  fail with the available ones. `chart` with `target` restyles or resizes (`width`/`height`, never `resize`).
- The group keeps the numbers: `inspect` the chart layer and read `chart.summary` (`totals`,
  `shares`, `scale`). Generated layers are named `NAME/part` and are owned by the chart: edit the
  data or options, not their geometry; effects, styles and opacity you add to them survive.
- Colors and fonts come from the document: `colors` / `@swatch`, the active palette (else the layout's palette), `@accent`/`@ink`,
  the heading and body font roles. Set `number_format` (`#,##0`, `0.0%`, `$#,##0`) once for ticks,
  labels and the PPTX chart. `value_labels: "auto"` labels every value if the labels fit (shrinking them if needed; never on another line's path or marker), else on a line chart the largest series above its points and the others below theirs, else whole series largest first, else every k-th value of the largest series; `true` labels everything.
- Placement: without `x`/`y`/`width`/`height` a new chart fills the document's safe area, inset by two spacing
  units, so it passes `safe_area` as created; give all four (`x: 0, y: 0` and the canvas size) for the full canvas.
- `legend_values: true` draws the legend as a key-value list: swatch and name left, totals right-aligned and, for
  pies and donuts, shares in their own column, ruled between rows (the auto labels around the ring are dropped;
  `value_labels: "percent"` keeps them). Use it when names, numbers and percentages belong together.
- `check` sees inside the chart (contrast, overlap, legibility). Raise `font_size` when the chart sits
  on a large canvas and the legibility check complains.
- Export: PNG/SVG/PDF are vector layers as usual; **`.pptx` writes a native chart with the table
  embedded** (editable in PowerPoint). Total labels, rotated charts and charts with effects are the
  exceptions (see the export report's `charts` and `raster_fallbacks`).
- Through MCP/REST a `csv` path must lie inside the workspace; fonts are registered names or the
  `heading`/`body` roles (`title_font`, `label_font`).

## Key-value lists

`key-value-list` sets label / value / share rows in aligned columns (labels left, figures right-aligned on shared
edges, a hairline rule between rows, spacing from the spacing scale) as editable text layers. Use it for a
summary beside a chart, a price list, stats or a schedule; the chart value legend uses the same geometry.

```json
{"type": "key-value-list", "name": "shares", "x": 80, "y": 80, "width": 420, "shares": "auto", "number_format": "#,##0",
 "rows": [{"label": "Drip", "value": 15900}, {"label": "Espresso", "value": 11960}, {"label": "Tea", "value": 5260}]}
```

- Rows: `rows` (`{label, value, share}` or `[label, value, share]`) or `items` text (`label | value | share` per line).
  `shares: "auto"` computes each share of the total; `width` pins the figures to its right edge and wraps labels.
- Look: `font_size` (default: body size), `font`, `value_font`, `text_color`, `share_color`, `rules`, `rule_color`,
  `colors` (a swatch per row). `key-value-list` with `target` restyles it on the same layer IDs.
- The `key-value-list` container places one under a title (`variables: {title, items}`).

## Tables

`table` draws rows (inline `table`, header row first, or a workspace `csv`) as a group of text and rule
layers; `table-data` edits cells on the same layer IDs. Use it for menus, price lists, pricing tables,
schedules and spec sheets instead of one text layer per cell.

```json
{"type": "table", "name": "menu", "x": 60, "y": 80, "width": 520,
 "table": [["Item", "Price"], ["Espresso", 3.25], ["Tea", 3]],
 "columns": [{}, {"align": "decimal", "format": "$0.00"}], "zebra": true, "borders": "horizontal"}
{"type": "table-data", "target": "menu", "set": [{"row": "Tea", "column": "Price", "value": 3.5}]}
```

- `columns[i]`: `width` (px, `auto`, `"1fr"`), `align` (`left`, `center`, `right`, `decimal`: prices share
  their point), `format` (Excel-style), `leader` (`"."`: dots from each body cell to the next cell's text, for
  menus; in PPTX they stop at the cell edge). Rows grow to fit wrapped text; a table too narrow for its words warns.
- Look: `font_size`, `header_fill`, `header_color`, `text_color`, `fill`, `zebra`, `borders`
  (`horizontal`/`all`/`outer`/`header`/`none`), `border_color`, `border_width`, `padding`, `row_height`.
- `table-data`: `set` (`row`: number from 1 or first-cell text; `column`: number or header), `append`,
  `remove_rows`, `add_columns`, `remove_columns`, `reload` (CSV).
- PPTX export writes a native, editable table (report `tables`); SVG/PDF keep vector text.
