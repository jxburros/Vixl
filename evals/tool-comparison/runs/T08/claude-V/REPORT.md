# T08 infographic, lane V (Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `infographic.vixl` | Editable source: layer stack with two data-bound `chart` groups (`monthly`, `share`), the callout cards and the text layers | `vixl_document_create` (1200 × 1800, background `#f7f1e5`, purpose poster, seed 8; the rolled font pairing installed was Zilla Slab 700 for headings and Fira Sans 400 for body), then `vixl_operations_apply` |
| `infographic.png` | 1200 × 1800 px, RGB | `vixl_export_file` |
| `infographic.svg` | Vector version: no embedded `<image>` elements | `vixl_export_file` |
| `infographic.pdf` | Vector version too: 1 page, `content: vector`, no raster fallbacks | `vixl_export_file` |
| `build-ops.json` | The first operation batch (title, cards, both charts, footnote) | A short Python script wrote it from the CSV. It read the CSV, put the twelve rows into the chart's `table` and summed the drink totals for the donut. Vixl applied the file through `operations_path`. The script did not draw anything. |

After the first batch I made these edits with further `vixl_operations_apply` calls. They are not in `build-ops.json`, so `infographic.vixl` is the only source that holds the final design:
- The cards became `rounded-rectangle`, 180 px tall.
- Every label and note was raised to 27 px.
- The footnote moved to y 1700 to sit inside the safe area.
- The bar chart is now 720 px tall with font_size 27 and bar_gap 0.18.
- The donut got font_size 27 and number_format `#,##0`.

## Content and numbers

The numbers come from `fixtures/coffee-2025.csv`. I checked them in Python, and Vixl's `chart.summary` for the donut matched.

- Title "A Year of Coffee at Tidewick"; subtitle "Cups sold per month, 2025".
- **Stacked bar chart** (`kind: stacked-bar`, `min: 0`): one bar per month, stacked flat white (bottom), drip, cold brew, tea (top). It has a legend at the top, a value axis titled "Cups" from 0 to 3,500 at 500-step ticks, and a total label over each bar. The bars are drawn to scale by the chart engine. As a spot check, the August stack measures about 417 px against a 3,030-cup total at roughly 0.138 px per cup.
- **Share of the year** as a donut with percentage labels to one decimal place: Flat white 44.6 %, Drip 33.7 %, Cold brew 7.1 %, Tea 14.7 %. The legend gives each drink's yearly total (15,720 / 11,880 / 2,500 / 5,180), and the centre reads "35,280 cups".
- **Callouts:**
  - Total cups in 2025: 35,280.
  - Busiest month: August, 3,030 cups.
  - Cold brew peaked in August with 420 cold brews.
- Footnote "Fictional data, made for testing."
- **Colours** are the same for each drink everywhere: flat white navy `#14263b`, drip amber `#f2a541`, cold brew sea-foam `#a8d5c8`, tea coral `#e2725b`. The cream `#f7f1e5` is the background.

## Choices and deviations

- I renamed the series to "Flat white", "Drip", "Cold brew" and "Tea" for display instead of the CSV column names.
- I added a chart title above each chart: "Cups sold by month and drink" and "Share of the year's cups".
- The busiest month and the cold-brew peak are both August, so two callouts say "August".
- The percentages are rounded independently and add up to 100.1 %. I left them that way so that each one is correct to one decimal place.

## Open items and uncertainty

- **One check finding is still open.** The final `vixl_check` reports a legibility warning on the twelve stack-total labels above the bars. The chart draws them at about 23 px; the threshold is 26.4 px at full width. Every other check passes, including bounds, overlap, contrast and safe area.
- **SVG and PDF were not inspected visually.** They come from the same document, but I looked only at the PNG.
