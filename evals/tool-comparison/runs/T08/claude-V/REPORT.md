# T08 Infographic: Vixl lane (claude-V)

All visual work was done through the Vixl MCP tools. A small Python script only read the CSV to
check the numbers and checked the exported PNG's size.

## Files

| File | How it was made |
| --- | --- |
| `infographic.vixl` | Editable Vixl source. Made with `vixl_document_create` (1200x1800, cream `#f7f1e5` background), `vixl_font_pair` (Inter Tight 800 for headings, Inter 400 for body), and one atomic `vixl_operations_apply` batch: the header band, title and subtitle, three callout cards, two `chart` operations, and the footnote. |
| `infographic.png` | `vixl_export_batch`. Confirmed as 1200 x 1800 px, RGB. |
| `infographic.svg` | `vixl_export_batch`. Vector with no embedded `<image>` rasters. Text is drawn as outlined paths, not `<text>` elements. |
| `infographic.pdf` | `vixl_export_batch`. Vector PDF with real, selectable text, two embedded fonts and no raster fallbacks. Page size is 16.667 x 25 in, which is 1200 x 1800 px at 72 dpi. |
| `REPORT.md` | This file. |

## Content
1. **Title and subtitle:** the text is exactly as the brief gives it.
2. **Stacked bar chart:** Vixl's `chart` operation with `kind: stacked-bar` and `min: 0`. It has one bar per month,
   stacked from bottom to top as Flat white, Drip, Cold brew, Tea. It has a legend at the top, a value axis from 0 to 4,000
   titled "Cups", and the month's total above each bar. Vixl's chart engine sets the segment heights from the data. I
   spot-checked one: Jan Flat white 1,200 is 135 px tall on a 448 px plot for 0–4,000, and 1200/4000*448 = 134.4.
   I turned off the value labels on each segment to keep the chart readable; the monthly totals are shown.
3. **Share of the year:** a donut chart with a percent label on each slice (44.6%, 33.7%, 7.1%, 14.7%). The legend
   also shows each drink's yearly total (15,720 / 11,880 / 2,500 / 5,180), and the centre shows "35,280 cups".
4. **Callouts:** I computed these from the CSV and they match the chart's own totals.
   - Total cups in 2025: **35,280**
   - Busiest month: **August**, 3,030 cups
   - Cold brew peak: **August**, 420 cups
5. **Footnote:** "Fictional data, made for testing."

The same colour is used for each drink in both charts and both legends: Flat white navy `#14263b`, Drip amber `#f2a541`,
Cold brew sea-foam `#a8d5c8`, Tea coral `#e2725b`.

## Choices and deviations
- The data was entered into the chart operation inline (categories and series), not linked to the CSV.
  I did this so the series could have readable names ("Flat white" rather than `flat_white`). The values are the CSV's values exactly.
- The busiest month and the cold-brew peak are both in August, so two callouts say "August". That is what the data says.
- `vixl_check` found no errors and no problems with overlap, contrast or bounds. It gave 53 legibility warnings. These mean
  most text would be smaller than 10 px if the whole 1200 px image were shrunk to a 320 px thumbnail. I left these as they are:
  this is a tall infographic meant to be read at full size, where the smallest text is 20 px. Clearing the warnings
  would need text of 38 px or more everywhere.

## Uncertainties
- The SVG draws its text as paths, so the words in the SVG can't be selected or searched. The PDF does keep real text.
- In the stacked bars, cold-brew segments for winter months are small (about 6–12 px), but they are drawn to scale.
