# T08 Infographic — claude, lane W (web code + headless Chromium)

**Timing:** start 2026-10-05 22:16:24 UTC, end 22:18:15 UTC (date timestamps; roughly 2 minutes of wall time as reported by `date`). 16 tool calls in total, including writing this report.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `infographic.html` | Editable source. One HTML page with the CSV embedded verbatim in a `<script type="text/csv">` block. Vanilla JS parses it, computes every number and draws one 1200x1800 inline SVG. No external libraries. | Hand-written |
| `build.py` | Build script (Python Playwright, headless Chromium). It checks that the embedded CSV matches `fixtures/coffee-2025.csv`, renders the page and writes the three outputs. It also prints the computed totals and runs a bar-scale check. | Hand-written. Run with `python3 build.py` |
| `infographic.png` | 1200 x 1800 px, RGB | Element screenshot of the SVG at device scale factor 1 |
| `infographic.svg` | Vector version, 1200x1800 viewBox, live text | `XMLSerializer` of the rendered SVG element |
| `infographic.pdf` | Vector version, 1 page, 1200x1800 CSS px (900x1350 pt), fonts embedded | Chromium `page.pdf` |

## Content against the brief

- Title "A Year of Coffee at Tidewick", subtitle "Cups sold per month, 2025".
- **Stacked bar chart:** 12 bars, stacked bottom to top as flat white, drip, cold brew, tea. It has a legend, a y-axis from 0 to 3,500 with gridlines every 500, and each month's total printed above its bar. Bars are drawn to scale: `build.py` checks that all 48 segment heights equal value x 0.1486 px per cup (520 px / 3,500). Thin cream lines (1 px) separate the segments. They are drawn on top and centred on the boundaries, so segment geometry is unchanged.
- **Share of the year:** a donut chart plus a table with the cup totals and percentages to one decimal place:
  - Flat white: 15,720 cups, 44.6%
  - Drip: 11,880 cups, 33.7%
  - Cold brew: 2,500 cups, 7.1%
  - Tea: 5,180 cups, 14.7%
- **Callouts:**
  - Total cups in 2025: 35,280.
  - Busiest month: August, 3,030 cups.
  - Cold brew peak: 420 cups in August.
  - There are no ties for either maximum. The totals and shares were cross-checked with a separate Python `csv` calculation.
- Footnote "Fictional data, made for testing." is at bottom left.
- Colors are the same for each drink everywhere (legend, bars, donut, table, header accent): flat white navy `#14263b`, drip amber `#f2a541`, cold brew sea-foam `#a8d5c8`, tea coral `#e2725b`. The background is cream `#f7f1e5`.

## Choices and differences

- **Extras not asked for:** I added "Source: coffee-2025.csv" at bottom right, month totals above the bars, and the cup counts in the share table.
- **Percentages add up to 100.1%.** Each one is rounded on its own (44.6 + 33.7 + 7.1 + 14.7 = 100.1). I kept standard rounding rather than adjusting a value so they sum to 100.0, because adjusting would make one percentage wrong.
- **Busiest month and cold-brew peak are both August.** This is what the data says, so two callouts name the same month.
- **Fonts are system fonts:** P052 (a Palatino clone) for headings and DejaVu Sans for body text.
  - The PDF embeds them.
  - The SVG keeps live text with fallback font stacks, so on a machine without these fonts it will render with substitutes and the text widths may shift slightly. I rendered the SVG in Inkscape here and it matched.
  - The footnote's italic is synthesized: there is no DejaVu Sans Oblique in the PDF font list.

## Unsure about

- **Color contrast:** sea-foam is a light color, so it has low contrast against cream. That only matters for the small legend swatch and the callout accent bar, and every value is also given as text.
