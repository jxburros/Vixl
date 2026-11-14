# Chart edit audit

[Project documentation](README.md) · [Charts guide](../guides/output/charts.md) · [Use-case catalog](../use-cases.md)

Which edits people make to a chart after `chart` has drawn it, whether each is one operation that names
the data or still drops to edits of the chart's generated layers, and what that costs in calls. It answers
issue #780 and sets the order of the chart work in roadmap stage 7.

## Method

- **Edits listed from:** the chart rows of the use-case catalog (DAT-10, 20, 21, 32, 40, 41, 50), the one
  chart task in `evals/tasks/` (`chart-fix-value.json`), the operations of the measured infographic run
  (`evals/craft_backtest/ops/T08-build-ops.json`) and the judged defects of the craft backtest
  (`evals/craft_backtest/manifest.json`).
- **Frequency** is the number of those seven catalog rows whose work includes the edit, plus the other
  evidence that shows it. It is a ranking aid, not a count of agent traces: the published eval traces live
  in the VixlExamples repository and were not re-read for this page.
- **Calls** are tool calls of an agent session (`vixl_apply`, `vixl_document`), counted from the operations
  each route needs. "Per data change" means the route has to be repeated after `chart-data`, because the
  chart sets the fill, geometry and text of its generated layers again on every redraw; only what the chart
  does not own (opacity, effects, blend mode, visibility) survives.
- `N` is the number of marks in the chart (bars, slices or points).

What the evidence shows:

- `chart-fix-value` passes in 4 tool calls with one `chart-data` cell edit (`evals/token-baseline.json`).
  Data edits were never the problem.
- The infographic run (DAT-20, 18 calls) drew 2 charts and 12 text layers. Five of those text layers repeat
  numbers or names that the chart data already holds (the total, the busiest month and its count, the peak
  month of one series and its count). Its revision (DAT-21, 24 calls) changed one cell; text that repeats
  a number has to be retyped whenever that number changes.
- The craft backtest's judged defects include "Plain chart: labels as large as data, nothing emphasised":
  the chart was correct and nobody was told where to look.

## Edits that are already one operation

| Edit | Operation | Calls |
| --- | --- | --- |
| Fix a value, add or remove a category or series, reload the CSV | `chart-data` | 1 |
| Change the kind, title, colours, legend, number format, axis range, fonts | `chart` with `target` | 1 |
| Move or resize the chart | `chart` with `target` and `x`/`y`/`width`/`height` | 1 |
| Show totals or shares beside the chart | `total_labels`, `legend_values` | 1 |
| Keep several charts, a table and the numbers in text in step | `dataset`, `data: NAME`, `${data.NAME.…}` (#214) | 1 per edit |
| Hand the chart to PowerPoint as an editable chart | `export` to `.pptx` | 1 |

## Edits that needed layer operations, ranked

Ranked by how many of the seven rows include the edit, then by the calls saved.

| Rank | Edit | Rows | Route before | Calls before | As one operation | Calls after | Issue | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Make one category stand out: keep its colour, tone down the rest | DAT-20, 40, 41, 50; backtest defect | List the group's children, then recolour `N − 1` marks (and the legend and labels) one layer at a time | 2, with `N − 1` layer edits, per data change | `chart-emphasis` with `focus` and `mute`, stored with the chart | 1, once | #779 | Shipped |
| 2 | Put a callout on one mark ("Best month: 3,330") | DAT-20, 40 | Read the mark's box, place a text layer by coordinates, type the number | 2 per data change, and the number is typed by hand | `chart-emphasis` with `annotate` and `${value}` | 1, once | #779 | Shipped |
| 3 | Apply an effect, opacity or blend mode to one bar, slice, point or label | DAT-40, 50 | List the children and match layer names; a layer was keyed to the row's position, so what was added to it stayed with the position when the rows were reordered | 2 | Any operation with `target: {chart, series, category, part}` | 1 | #778 | Shipped |
| 4 | Repeat the chart's numbers in text (KPI figures, "busiest month") | DAT-20, 21, 32, 40 | Typed by hand, retyped after every data change | 1 per text layer per data change | `${data.NAME.total}`, `.max.label`, `.SERIES.CATEGORY` | 0 after the first | #214 | Shipped earlier; the catalog still listed it as missing (BLK-09) |
| 5 | Draw a target, average or threshold line with a label | DAT-32, 41 | Read `chart.summary.scale` and the gridline layers to find the plot rectangle, compute the pixel position, add a shape and a text layer | 3, with hand arithmetic, per scale change | A `reference_lines` option: `[{value, label, color?}]` | 1, once | To file | Proposed (stage 7.4) |
| 6 | A bare chart for a KPI tile: no axis, ticks, gridlines or legend | DAT-32 | `chart` with `legend: "none"`, `gridlines: false`, `value_labels: false`, then list and hide the tick and category labels and the axis line; ticks added by a later scale change come back | 3, and again when the scale changes | An `axes: false` option (or a `sparkline` kind) | 1 | To file | Proposed (stage 7.5) |
| 7 | Sort the categories by value, or put one first | DAT-20, 41 | `chart-data` with the whole table retyped in the new order | 1, with the whole table as payload | `chart-data` with `sort: {by, order}` or `order: [categories]` | 1, a few names | To file | Proposed (stage 7.6) |
| 8 | Rename a category or series | DAT-21 | `chart-data` with the whole table retyped; the renamed row is a new row, so what was added to its layers and an emphasis on it are lost | 1, with the whole table as payload | `chart-data` with `rename: {old: new}` | 1 | To file with rank 7 | Proposed (stage 7.6) |
| 9 | Tell series apart by pattern as well as colour | DAT-50 | `pattern-fill` on each mark; the chart sets the fill again on redraw | 1 with `N` targets, per data change | A per-series `pattern` | 1, once | None | Not proposed: value labels and `layer-intent color_vision_safe` already answer the check |

Ranks 1 to 3 were the known candidates and are done. Rank 4 was done before this audit and only the
catalog was stale. Ranks 5 to 8 are the cases worth an issue each (7 and 8 share one, because both are
table edits by name on `chart-data`); none of them needs layer addressing any more, since rank 3 gave the
chart's parts stable addresses.

## Proposed stage-7 items

These are for the roadmap; they are not built.

- **7.4 Reference lines.** `reference_lines` on `chart` (cartesian kinds): a value, an optional label and
  colour; drawn on the value scale, kept through `chart-data`, exported as a line and text over the native
  PPTX chart. Done when a target line stays at its value after a data change that rescales the axis.
- **7.5 Bare charts for tiles.** `axes: false` on `chart`: no axis line, tick or category labels, gridlines
  or legend, the plot filling the group; the emphasis and callouts still apply, so a tile can mark its last
  point. Done when a 240 × 80 line chart passes `check` with no hidden layers.
- **7.6 Reorder and rename by name.** `chart-data` gains `sort` (`by: "value" | "category"`, `order`,
  optionally a `series`), `order` (a list of categories) and `rename` (categories and series). Layer
  identity follows the data (stage 7.2), so a renamed row keeps its layers and its emphasis. Done when a
  sorted chart keeps every layer ID and a renamed category keeps its emphasis.

## Use-case rows changed by this audit

- **DAT-20**: its note no longer says totals and callouts are typed by hand; the measured 18 calls predate
  shared datasets and `chart-emphasis` and stay until the brief is run again.
- **DAT-54, DAT-55** (new, one-shot tier): chart emphasis, and addressing a chart's marks by data.
- **DAT-56** (new, one-shot tier) replaces **BLK-09**: binding chart values into text and into other
  charts shipped with shared datasets.
