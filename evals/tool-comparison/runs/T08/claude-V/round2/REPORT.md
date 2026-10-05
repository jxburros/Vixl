# T08 Infographic, round 2: claude-V (Vixl lane)

The change request: December's numbers were wrong. The correct values are flat_white 1480, drip 1120, cold_brew 90, tea 640. Tea's color changes to plum `#6b3f69`. Every chart and number had to be updated.

**Tool calls:** 26 in total, counting this report and the hand-off.

## Files (all in `round2/`; nothing outside `round2/` changed)
| File | How it was made |
| --- | --- |
| `infographic.vixl` | I copied the round-1 source into `round2/` and edited it in place with `vixl_operations_apply` (always with `document=` set). That took one atomic batch of 50 operations and a fix-up batch of 11. |
| `infographic.png` | `vixl_export_file`, 1200×1800. I checked the size with PIL. |
| `infographic.svg` | `vixl_export_file` with `svg_policy="strict"`. It is all vector, with no `<image>` elements. |
| `infographic.pdf` | `vixl_export_file` with `pdf_content="vector"`. It has 2 embedded fonts and no raster fallbacks. |

## Corrected numbers (the CSV with December replaced)
- **Dec total**: 3,330 (was 2,980). The other months are unchanged.
- **Total cups in 2025**: 35,630 (was 35,280). This appears in the first callout and in the share subtitle.
- **Busiest month**: now **December, 3,330 cups** (was August, 3,030).
- **Cold brew peak**: still August, 420 cups. December's 90 cups doesn't change it.
- **Share of the year**: flat white 44.6% (15,900), drip 33.6% (11,960), cold brew 7.0% (2,510), tea 14.8% (5,260). The rounded figures add up to exactly 100.0%.

## What changed in the document
- **December bar**: I redrew it to the same scale as before (0.16 px per cup, baseline y=1240), using running totals rounded to whole pixels. Flat white is 237 px (y 1003), drip 179 px (y 824), cold brew 14 px (y 810) and tea 103 px (y 707). The PNG sampled down the bar's centre matches these exactly. The `total_Dec` label reads "3,330" and moved up to sit above the taller bar. It still fits under the 3,500 axis maximum, so the axis is unchanged.
- **Callouts**: I changed the text of `card0_value` (35,630), `card1_value` (December) and `card1_sub` (3,330 cups sold). "December" is 273 px wide and fits inside its card.
- **Share bar** (1,080 px, edges at the rounded running share): flat white is 482 px wide, drip 362 px (x 542), cold brew 77 px (x 904) and tea 159 px (x 981). I updated the percentage labels. The flat white labels moved to the new segment centre (x 301).
- **Tea color**: I changed all 14 tea shapes (12 bars, the legend swatch and the share segment) to `#6b3f69`. I couldn't find an operation in the reference that changes an existing shape's fill: a `shape` op with `target` adds a new layer instead. So I removed each tea layer and added it again with the same name, bounds and radius and the new fill. That means those 14 layers have new layer IDs. The PNG has 0 coral pixels left. The SVG's coral fills were all replaced by plum (14 of each).

## Problems found along the way
- A `resize` with only `height` also scaled the width to keep the proportions. This made the December bars 54–57 px wide and the cold-brew share segment 91 px tall. The second batch reset width and height explicitly. All the bounds are now correct: 50 px bars and 90 px share segments.
- The first PDF export used the default content setting and came out rasterized (one image, no fonts). I re-exported it with `pdf_content="vector"`, which matches round 1.

## Checks
`vixl_check` (bounds, overlap, contrast, blanks) passed with 0 errors. It gave 3 warnings, the same ones as round 1: the 3,000 gridline runs through the Jan/Mar/Apr total labels. I looked over the full rendered preview and it has no problems.
