# T08 Infographic — Lane C (code + free libraries)

## Files

| File | How it was made |
| --- | --- |
| `make_infographic.py` | Editable source. Python 3 + matplotlib (Agg backend). Reads `../../../fixtures/coffee-2025.csv`, computes every number, draws the layout in pixel coordinates on a 12 × 18 in figure at 100 dpi, and saves all three outputs. Rerun with `python3 make_infographic.py`. |
| `infographic.png` | 1200 × 1800 px raster, `fig.savefig(dpi=100)`. Size checked with Pillow. |
| `infographic.svg` | Vector version from the same figure. Text is kept as `<text>` elements (`svg.fonttype = none`), so it renders in DejaVu Sans only if that font is installed, otherwise in a fallback font. Page size is 864 × 1296 pt (the same 2:3 ratio). |
| `infographic.pdf` | Vector version from the same figure, with TrueType fonts embedded (`pdf.fonttype = 42`). Page size 864 × 1296 pt. |
| `REPORT.md` | This file. |

## Content and computed numbers (from the CSV)

- Title "A Year of Coffee at Tidewick"; subtitle "Cups sold per month, 2025".
- Stacked bar chart: one bar per month, stacked bottom to top: flat white, drip, cold brew, tea. Legend above the chart. The value axis runs from 0 to 3,500 with gridlines every 500. Each month's total is printed above its bar (Jan 2,880 · Feb 2,770 · Mar 2,910 · Apr 2,910 · May 2,950 · Jun 2,970 · Jul 2,980 · Aug 3,030 · Sep 2,980 · Oct 2,970 · Nov 2,950 · Dec 2,980).
- Share of the year: a donut chart plus a table showing each drink's percentage (one decimal place) and its cup total: flat white 44.6% (15,720), drip 33.7% (11,880), tea 14.7% (5,180), cold brew 7.1% (2,500). The donut's centre shows the 35,280 total.
- Callouts: total 35,280 cups; busiest month August with 3,030 cups; cold brew peaked in August with 420 cups.
- Footnote "Fictional data, made for testing." (I also added "Source: coffee-2025.csv" at bottom right.)
- Each drink keeps the same colour everywhere: flat white = navy `#14263b`, drip = amber `#f2a541`, cold brew = sea-foam `#a8d5c8`, tea = coral `#e2725b`. The background is cream `#f7f1e5`.

## Checks done

- The script prints every computed value, and I compared the output against the figures above. It also asserts that the sum of the month totals equals the sum of the drink totals.
- I checked the bars are to scale by measuring pixels in the PNG. Each bar's top (the top of the coral segment), measured from the axis baseline, is within 1–1.5 px of total/3500 × 520 px. The small shortfall comes from the 0.8 px cream outline drawn around each segment to separate them.
- I looked at the rendered PNG to check the layout: no clipping or overlaps.

## Choices and deviations

- Share chart: a donut, sorted largest first, with a percentage table beside it. The cold brew slice is small, so labels on the slices would have been cramped.
- Rounding: each percentage is correctly rounded to one decimal place, but they add up to 100.1% (44.6 + 33.7 + 14.7 + 7.1). I left them as true roundings rather than forcing a 100.0% total.
- The bar chart stacks drinks in CSV column order. The share table and donut are sorted by size, so the order there is flat white, drip, tea, cold brew.
- Extras not in the brief: month totals above the bars, cup counts next to the percentages, the total in the donut's centre, and the source line.
- Font: DejaVu Sans, the system font that was available. I did not install any extra fonts.

## Unsure about

- The SVG relies on DejaVu Sans being installed where it is viewed. The PDF embeds the font, so it is the safer vector file.
- The value labels for the tallest bars (around 2,950–3,030) sit near the 3,000 gridline. They stay readable, but they touch the gridline.

## Timing

Start 22:16:25 UTC, end 22:17:52 UTC (both from `date`, 2026-10-05). 18 tool calls, including the report write, a refused first attempt to write it, and the final hand-back.
