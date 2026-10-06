# T08 Round 2: corrected December and plum tea (claude-V)

All the visual edits went through the Vixl MCP tools. A small Python script only computed the corrected totals
and checked the exported files. Nothing outside `round2/` was changed. I only read the round-1 files.

## What changed

**December data.** The old values were flat_white 1300, drip 1040, cold_brew 80, tea 560. The new values are 1480, 1120, 90, 640.

| Number shown | Round 1 | Round 2 |
| --- | --- | --- |
| Total cups in 2025 (callout and donut centre) | 35,280 | **35,630** |
| Busiest month (callout) | August, 3,030 | **December, 3,330** |
| Cold brew peak (callout) | August, 420 | August, 420 (no change; Dec cold brew is now 90) |
| December bar total label | 2,980 | **3,330** |
| Flat white yearly total and share | 15,720, 44.6% | 15,900, 44.6% |
| Drip yearly total and share | 11,880, 33.7% | 11,960, 33.6% |
| Cold brew yearly total and share | 2,500, 7.1% | 2,510, 7.0% |
| Tea yearly total and share | 5,180, 14.7% | 5,260, 14.8% |

Because December's total rose, the busiest month moved from August to December. The axis still runs from 0 to 4,000
in steps of 1,000, since 3,330 is under 4,000. The new December segments are drawn to the same scale of 448 px per
4,000 cups: Flat white 166 px, Drip 125 px, Cold brew 10 px and Tea 72 px.

**Tea colour.** Tea changed from coral `#e2725b` to plum `#6b3f69` everywhere: in all 12 tea bar segments, in the
stacked-bar legend swatch, and in the donut slice and its legend swatch. The other drinks keep their colours. No coral
remains in the SVG. A sample of the PNG at the December tea segment reads rgb(107, 63, 105).

## How

1. I copied `../infographic.vixl` to `round2/infographic.vixl` and opened the copy.
2. One atomic `vixl_operations_apply` batch made these changes:
   - `chart-data` on `monthly` set the four December cells.
   - `chart-data` on `share` set the four new yearly totals. Vixl recomputed the percentages, the slice angles,
     the legend values and the `{total}` centre text.
   - `chart` restyle with the new `colors` on both charts.
   - `text-set` on the three callout values that changed (total, busiest month, busiest-month note).
3. In the stacked-bar chart, each series had its own `color` stored, and that overrode the chart-level `colors`.
   As a result the tea bars were still coral after step 2. I fixed this with a second `chart` restyle on `monthly`
   that sets the four series again, using the same values with Tea's `color: #6b3f69`. The layer IDs were kept.
4. "December" at 64 px came out 314 px wide and ran 6 px past the right edge of its callout card. I reduced it to
   56 px (274 px wide) and moved it down 6 px so its baseline (438.7) lines up with the other two callout values (438.6).
5. `vixl_check` found no errors and no overlap, contrast or bounds problems. It gave the same 53 thumbnail-legibility
   warnings as round 1, which I left for the reason given in the round-1 report. I looked at `vixl_render_preview`
   of the full page and of the callout row.
6. I exported with `vixl_export_batch`:
   - `infographic.png` is 1200 x 1800 px, RGB.
   - `infographic.svg` is vector, with no `<image>` elements.
   - `infographic.pdf` is a vector PDF with 2 embedded fonts and no raster fallbacks. `pdftotext` shows 35,630, December, 3,330 and the new percentages.

## Files in round2/
`infographic.vixl`, `infographic.png`, `infographic.svg`, `infographic.pdf`, and `REPORT.md`. The file names are the same as round 1.

## Notes
- The fixture CSV was not edited. The charts hold their data inline, as they did in round 1.
- The busiest-month callout now uses a smaller type size (56 px) than the other two callout values (64 px).
