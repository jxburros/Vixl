# Charts

Use `chart` for any bar, line, area, pie or donut instead of drawing shapes and computing heights,
totals and percentages yourself. The chart is a group of ordinary vector layers bound to a table;
fixing a number is one operation and nothing is recomputed by hand. Full reference: `docs/charts.md`.

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
- Colors and fonts come from the document: `colors` / `@swatch`, the active palette, `@accent`/`@ink`,
  the heading and body font roles. Set `number_format` (`#,##0`, `0.0%`, `$#,##0`) once for ticks,
  labels and the PPTX chart. `value_labels: "auto"` labels every value if the labels fit (shrinking them if needed), else whole series largest first, else every k-th value of the largest series; `true` labels everything.
- `check` sees inside the chart (contrast, overlap, legibility). Raise `font_size` when the chart sits
  on a large canvas and the legibility check complains.
- Export: PNG/SVG/PDF are vector layers as usual; **`.pptx` writes a native chart with the table
  embedded** (editable in PowerPoint). Total labels, rotated charts and charts with effects are the
  exceptions (see the export report's `charts` and `raster_fallbacks`).
- Through MCP/REST a `csv` path must lie inside the workspace; fonts are registered names or the
  `heading`/`body` roles (`title_font`, `label_font`).
