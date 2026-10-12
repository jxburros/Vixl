# T08 infographic, round 2 (lane V, Vixl)

## What changed

The December row now uses the corrected values: flat white 1,480, drip 1,120, cold brew 90 and tea 640. Tea's colour is now plum `#6b3f69` everywhere.

| Item | Before | After |
| --- | --- | --- |
| December bar (stacked) | 1,300 / 1,040 / 80 / 560, total 2,980 | 1,480 / 1,120 / 90 / 640, total **3,330** |
| Yearly totals (donut legend) | 15,720 / 11,880 / 2,500 / 5,180 | **15,900 / 11,960 / 2,510 / 5,260** |
| Grand total (card 1 and donut centre) | 35,280 | **35,630** |
| Donut percentages | 44.6 / 33.7 / 7.1 / 14.7 % | **44.6 / 33.6 / 7.0 / 14.8 %** (these now add up to exactly 100.0 %) |
| "Busiest month" card | August, 3,030 cups sold | **December, 3,330 cups sold** |
| "Cold brew peaked in" card | August, 420 cold brews sold | unchanged. December's 90 doesn't change the peak, so it is still August at 420. |
| Tea colour (bars, both legend swatches, donut slice) | coral `#e2725b` | plum `#6b3f69` |
| Accent rule under the subtitle | coral `#e2725b` | plum `#6b3f69` (see below) |

The value axis still runs from 0 to 3,500, so the taller December bar (3,330) fits without rescaling.

## How

1. I copied `../infographic.vixl` to `round2/infographic.vixl` and opened it with `vixl_document_open`. Everything else was done on that copy.
2. I made one atomic `vixl_operations_apply` batch:
   - `chart-data` `set` on the `monthly` chart for the four December cells. The chart engine redrew the bars and recomputed the "3,330" total label.
   - `chart-data` `set` on the `share` donut for the four yearly totals. The engine recomputed the slices, the percentages, the legend values and the "{total} cups" centre text. I checked its `summary`: grand total 35,630, shares 44.63 / 33.57 / 7.04 / 14.76 %. These match my own sum from the CSV with December replaced.
   - `chart` with `target` on both charts to set `colors` with plum for tea. This keeps the layer IDs.
   - `text-set` on `c1-value` (35,630), `c2-value` (December) and `c2-note` (3,330 cups sold).
   - `shape` with `target: rule` to set the fill to plum.
3. `vixl_export_file` to `infographic.png`, `.svg` and `.pdf`.
4. `round2/build-ops.json`: a small script copied the original first batch and put the same corrections in it (December row, donut values, the three card texts, plum instead of coral). As in round 1, this file holds only the first batch. The later layout edits (rounded cards, 27 px labels, and so on) live only in `infographic.vixl`.

## Checks

- **PNG pixels:** no pixel is exactly coral `#e2725b`, and 56,862 pixels are plum.
- **SVG:** no `rgb(226,114,91)`, while `rgb(107,63,105)` appears 16 times. The SVG text is outlined, so I checked the numbers through the PDF.
- **PDF text** (`pdftotext`) shows 35,630, 3,330, December, 15,900 / 11,960 / 2,510 / 5,260 and 44.6 / 33.6 / 7.0 / 14.8 %. No stale values remain. "August" is left only in the cold-brew card and on the month axis.
- **`vixl_check`:** it reports the same single finding as round 1, a legibility warning on the twelve stack-total labels (23 px, threshold 26.4 px). That issue was already there, and this round's request didn't touch it, so I left it as it was. No other findings.
- **Visual check:** I looked at a preview of the result. "December" fits inside its card (it ends at x 728, and the card's inner edge is at 742).

## Choices and open items

- **The decorative accent rule was coral too, and I made it plum.** It is not a data mark, but it echoed tea's old colour, and leaving it coral would have kept a colour that no longer means anything in the piece. If it should stay coral, change it back with one `shape` edit on `rule`.
- **Busiest month changed.** With the corrected figures, December (3,330) beats August (3,030), so the card text changed with the numbers.
- **Not inspected visually:** the SVG and PDF. I checked them only by searching their colours and text.
