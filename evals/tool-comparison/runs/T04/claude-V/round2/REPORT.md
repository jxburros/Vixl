# T04 round 2: Tidewick & Co. (lane V, Vixl)

The business is now **Tidewick & Co.** and the tagline is **"Coffee · Bakery · Harbor"**. All editing was done with Vixl's MCP tools on copies of the round 1 sources in `round2/src/`. Nothing outside `round2/` was changed.

## What changed, file by file

| File | Change | How |
| --- | --- | --- |
| `logo-horizontal.svg` | New wordmark and tagline. **Canvas is now 1554 × 400 (was 1240 × 400).** | Opened `src/logo-horizontal.vixl` and used `text-set` on `wordmark` and `tagline`. See "Sizing" below. Re-exported with `svg_policy="strict"`. |
| `logo-stacked.svg` | New wordmark and tagline. **Canvas is now 1140 × 627 (was 900 × 655).** | Same edits in `src/logo-stacked.vixl`. Moved the mark 120 px right to stay centred, re-centred the text on the canvas, then did a strict SVG export. |
| `logo-sheet.png` | Shows the new lockups on both halves. Still 1600 × 1200 and RGB. | Re-exported the four lockup images at sheet scale (`src/sheet-{h,s}-{cream,navy}.png`, with the cream and navy variables). In `src/logo-sheet.vixl` I removed the old image layers, imported the new ones and moved them into place. The horizontal lockup is now 940 px wide (was 760) because it is wider; the stacked lockup is 460 px wide, and its labels moved up to sit under it. I also used `links-relink` to point the sheet's mark, mono and app-icon links at `round2/src/`. |
| `mark.svg`, `mark-mono.svg`, `favicon.ico`, `app-icon-1024.png` | **Copied unchanged.** | These files contain no name or tagline (the mark is purely pictorial), so the rename doesn't affect them. Re-exporting them would have produced the same artwork. |
| `src/*` | Sources updated to match | `horizontal.json`, `stacked.json` and `gen.py` now hold the new text, sizes and positions. `sheet.py` points at `round2/src/`. The edited `.vixl` files and the new sheet PNGs are here too. |

## Sizing

"Tidewick & Co." is about 60% longer than "Tidewick". At the old 172 px it would have been 1275 px wide, which is more than the old horizontal canvas, so Vixl's bounds check flagged it as cut off. I made these changes:

- **Horizontal lockup:** the wordmark is now 150 px. Its baseline is at 220 and the tagline baseline at 296, so the text block (y 108 to 296) stays centred on the mark (centre y 200). The right margin of 50 px matches the mark's left margin.
- **Stacked lockup:** the wordmark is now 140 px. The canvas is wider and a little shorter. The gap between the mark and the wordmark is the same as before (about 59 px), and the bottom margin is about 50 px.
- **Unchanged:** the tagline stays Work Sans 40 px, uppercase, with tracking of 5. "COFFEE · BAKERY · HARBOR" is 658 px wide, so it fits under the wordmark in both lockups. The middle dots are U+00B7, written with a space on each side.

The new aspect ratios matter if anything consumes these SVGs at a fixed box size: the horizontal lockup is now 3.9:1 (was 3.1:1) and the stacked one 1.8:1 (was 1.37:1).

## Checks

- `vixl_check` passes on both lockups with no findings. The sheet has no `fix` findings. It still has the same review-level safe-area notes as round 1: the full-bleed navy half, and the two cream lockup images at 40 px from the top.
- Both SVGs have no `<text>` and no `<image>`; the lettering is outlined paths (35 path elements each). I rendered them with resvg outside Vixl. In the horizontal lockup the ink spans 50 to 1505 of 1554 px wide, and the tagline ends at x 1061. In the stacked lockup the wordmark ink is 54 to 1082 and the tagline 238 to 897, both centred at about 568 to 570 on the 1140 px canvas.
- I looked at the resvg render of the stacked SVG and at the sheet preview, and both read correctly.

## Notes

- **Preview tracking bug.** Vixl's small `preview` (scaled down) draws the tracked tagline too wide; this matches the round 1 note about scaled link layers. The full-size SVG and the scale exports are correct (measured above). That is why the sheet still uses pre-rendered lockup PNGs rather than live links.
- **"Co." styling.** "Co." is set in the same Fraunces 700 as the rest of the wordmark. I did not try a smaller "& Co." treatment, so the name reads as one unit.
