# T04 round 2: rename to "Tidewick & Co." (lane V, Vixl MCP)

**Change requested:** rename the business "Tidewick & Co." and change the tagline to "Coffee · Bakery · Harbor" (with U+00B7 middle dots), in every file.
**Timing:** 22:36:45 to 22:39 UTC, about 3 minutes. **Tool calls:** 42 in total: 30 Vixl MCP (`document_inspect` ×5, `operations_apply` ×8 including one failed dry run, `render_preview` ×3, `export_file` ×9, `import_image` ×4, `check` ×1), 8 Bash, 2 Read, 1 ToolSearch and the final hand-back.

Nothing outside `round2/` was changed. I copied every `.vixl` source and the `work/` PNGs into `round2/` first, then edited only the copies.

## What changed, file by file

| File | Change | How |
| --- | --- | --- |
| `logo-horizontal.svg` | Wordmark now reads "Tidewick & Co.", tagline reads "Coffee · Bakery · Harbor". Canvas widened from 1400×440 to **1968×440** so the longer wordmark fits with the same 60 px right margin. Mark, type sizes (200 px / 54 px), fonts, colors and positions are the same as before. | `round2/logo-horizontal.vixl`: `text-set` on `wordmark` and `tagline`, then `canvas` width 1968. Exported with `svg_policy="strict"`. |
| `logo-stacked.svg` | Same text change. Canvas widened from 1000×800 to **1480×800**. Mark, wordmark (180 px) and tagline (52 px) keep their sizes and vertical positions and are now centered with `constrain center-x: canvas.center-x`, which replaces the old hand-computed x values. | `round2/logo-stacked.vixl`, exported strict. |
| `logo-horizontal-reversed.svg`, `logo-stacked-reversed.svg` (extras from round 1) | Same changes as their positive versions: 1968×440 and 1480×800. | Their `round2/*.vixl` copies, exported strict. |
| `logo-sheet.png` | Rebuilt with the new lockups. Still 1600×1200 and still split cream/navy. | I re-exported the four lockups to full-size PNGs (`round2/work/work-h-light.png`, `work-h-dark.png`, `work-s-light.png`, `work-s-dark.png`, overwriting the copies) and imported them into `round2/logo-sheet.vixl`. I removed the old `h-*`/`s-*` raster layers and gave the new ones the same names. Because the lockups are wider, they are placed at new sizes: horizontal 680×152 at y=180 (was 640×201 at y=110), stacked 340×184 at y=460 (was 330×264 at y=420). Every other layer is unchanged. `vixl_check` (bounds, overlap, contrast, fonts) passed. |
| `mark.svg`, `mark-mono.svg`, `mark-reversed.svg`, `favicon.ico`, `app-icon-1024.png` | **No visual change.** These files have no lettering, so neither the name nor the tagline appears in them. They are copied byte-for-byte from round 1 so `round2/` is a complete kit. | `cp`. |

Their `.vixl` sources are in `round2/` as well. The four lockup sources and `logo-sheet.vixl` are edited, and the rest are unchanged copies.

## Checks on the output

- All 7 SVGs: no `<text>`, `<image>`, `base64`, font references or `<mask>` elements. Lettering, including "&" and the middle dots, is converted to outline paths. viewBoxes: 1968×440 (horizontal), 1480×800 (stacked), 512×512 (marks).
- `round2/logo-horizontal.svg` renders correctly in Inkscape: the name, "&", "Co." and the dots all appear.
- `logo-sheet.png` is 1600×1200. `favicon.ico` holds 16, 32 and 48 px images. `app-icon-1024.png` is 1024×1024 and fully opaque.

## Notes and things I'm unsure about

- **The lockup aspect ratios changed** (horizontal 3.18:1 → 4.47:1, stacked 1.25:1 → 1.85:1) because the name is about 60% longer. I kept the type sizes and widened the canvases instead of shrinking the wordmark relative to the mark. As a result the mark looks a little smaller next to the name than it did before.
- On the sheet, the tagline under the scaled-down stacked lockup is only about 11 px tall. It is readable but small. The full-size SVGs are not affected.
- `app-icon-1024.png` is still RGBA, with every alpha value at 255, as noted in round 1. I did not touch it.
- I checked the "&" spacing in "Tidewick & Co." only by eye in previews. I did not add kerning.
