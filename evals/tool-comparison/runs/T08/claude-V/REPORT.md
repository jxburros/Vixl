# T08 Infographic: claude-V (Vixl lane)

**Timing:** start 22:16:24 UTC, end about 22:23 UTC on 2026-10-05 (about 7 minutes). About 27 tool calls in total, counting this report and the hand-off.

## Files
| File | How it was made |
| --- | --- |
| `infographic.vixl` | The editable Vixl source. I created it with `vixl_document_create` (1200×1800, cream `#f7f1e5`) and set its fonts with `vixl_font_pair("dm-serif-dm-sans")`: DM Serif Display for headings, DM Sans for body text. Everything else came from one atomic `vixl_operations_apply` batch of 310 operations. That batch drew every rectangle and bar as a procedural `shape` layer and every label as a live text layer, positioned with canvas constraints. All layers have meaningful names, e.g. `bar_Aug_cold_brew`, `share_tea_pct`. |
| `infographic.png` | `vixl_export_file`, 1200×1800 (I checked the size with PIL). |
| `infographic.svg` | `vixl_export_file` with `svg_policy="strict"`. It is all vector with no embedded raster images, and the text is turned into outlines (paths, not `<text>`). |
| `infographic.pdf` | `vixl_export_file`, vector PDF with the 2 fonts embedded and no raster fallbacks. |

A small Python script (in my scratchpad, not a deliverable) read the CSV, worked out the totals and shares, and turned the data into bar geometry for the operation list. All drawing was done by Vixl.

## Content and numbers (worked out from `fixtures/coffee-2025.csv`)
- The title and subtitle match the brief exactly.
- **Stacked bar chart**: 12 bars, stacked from the bottom up as flat white, drip, cold brew, tea. It has a legend, gridlines, and a value axis from 0 to 3,500 in steps of 500 that starts at zero. Each bar has its month total above it: Jan 2,880, Feb 2,770, Mar 2,910, Apr 2,910, May 2,950, Jun 2,970, Jul 2,980, Aug 3,030, Sep 2,980, Oct 2,970, Nov 2,950, Dec 2,980.
- **Share of the year**: a horizontal 100% bar with segment widths in proportion to the share. Flat white 44.6% (15,720), drip 33.7% (11,880), cold brew 7.1% (2,500), tea 14.7% (5,180). The rounded percentages add up to 100.1% because of rounding to one decimal place. I left them unadjusted.
- **Callouts**: total cups in 2025 is 35,280. The busiest month is August with 3,030 cups. Cold brew peaked in August with 420 cups.
- The footnote matches the brief exactly.
- **Colors** stay the same for each drink everywhere (legend, bars, share bar): flat white navy `#14263b`, drip amber `#f2a541`, cold brew sea-foam `#a8d5c8`, tea coral `#e2725b`.

## Scale check
The chart scale is 560 px for 3,500 cups (0.16 px per cup). The bar coordinates were computed from running totals and rounded to whole pixels, so each segment is within ±1 px (about ±6 cups) of exact. I sampled the PNG down the middle of each bar: segment heights match the plan, e.g. Jan is 192/176/10/83 px. The share bar is 1,080 px wide and its segment edges are rounded to the nearest pixel.

## Choices and deviations
- The share chart is a 100% stacked bar, not a pie or donut. Vixl has no arc or wedge shape, and a bar is easy to read and drawn exactly to scale.
- The MCP rejects the `font` field inside operations. To get the paired fonts, I added one prototype text layer per font with `vixl_text_add(font=…)`. I made every label with `duplicate` + `text-set`, then removed the two prototypes.
- The share chart labels show the drink name and percentage. The yearly cup counts appear only in this report, not on the image, to avoid label collisions under the narrow cold-brew segment.

## Known issues and uncertainties
- `vixl_check` passed with 0 errors and 59 warnings:
  - 3 warnings say the 3,000 gridline crosses the month-total labels for Jan, Mar and Apr. The thin line passes behind the figures, which are still readable. I left it.
  - The other warnings are about thumbnail legibility at 320 px wide, which is expected for a 1200 px infographic with 16–21 px chart labels.
- Cold brew in Jan and Feb is only 10–11 px tall. It is visible but small, and sea-foam is a light color against the cream background.
