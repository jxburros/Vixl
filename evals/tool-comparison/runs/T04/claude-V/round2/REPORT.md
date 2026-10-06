# T04 round 2 · Rename to "Tidewick & Co." (Lane V: Vixl)

The changes:
- The business name is now **"Tidewick & Co."**
- The tagline is now **"Coffee · Bakery · Harbor"**. It keeps round 1's all-caps Work Sans treatment, so it reads `COFFEE · BAKERY · HARBOR`.

All the editing and exporting was done with the Vixl MCP tools: `vixl_document_inspect`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview` and `vixl_export_batch`. I didn't hand-write any SVG, HTML or pixels. I used `cp` only to copy the round-1 `.vixl` sources into `round2/src/` so I could edit the copies. Python (PIL, resvg_py, `cmp`) was used only to check the outputs. Nothing outside `round2/` was changed.

## What changed, file by file

| File | Change |
| --- | --- |
| `logo-horizontal.svg` | I changed the wordmark and tagline with `text-set` (same fonts and sizes: Fraunces 700 at 160 px, Work Sans at 40 px). The longer name needed more room, so the canvas grew from 1164 × 392 to **1608 × 392**. The 50 px right margin and the left-aligned mark are unchanged. |
| `logo-stacked.svg` | I made the same `text-set` edits. The canvas grew from 834 × 627 to **1274 × 627**, and I re-centered the mark, wordmark and tagline. The wordmark ink has 50 px side margins. The vertical positions are unchanged. |
| `logo-sheet.png` | I repointed all 14 live `link` layers from `src/` to `round2/src/`, so the sheet shows the new logos. The horizontal and stacked logos have a new aspect ratio, so I resized and re-centered their link boxes: horizontal 640 × 156 at y = 106, stacked 581 × 286, both centered in each half. The navy half still passes `ink = #f7f1e5`. Canvas, labels and the actual-size row are unchanged. |
| `mark.svg`, `mark-mono.svg`, `favicon.ico`, `app-icon-1024.png` | These files contain no name or tagline. I re-exported them from the `round2/src` copies with the same settings as round 1 (strict SVG; ICO 16/32/48; PNG `alpha=flatten`). They are byte-identical to round 1 (checked with `cmp`). |
| `src/*.vixl` | Editable sources for every file above. In `logo-horizontal`, `logo-stacked` and `logo-sheet` the text is still live and editable, and the links are still live. |

## Checks

- `vixl_check` (bounds, overlap, fonts or links) passes with 0 issues on the horizontal logo, the stacked logo and the sheet.
- I previewed all three in Vixl and also rendered the exported SVGs with resvg. The text is not clipped and the spacing is balanced.
- Both logo SVGs are strict. They contain no `<text>`, no `<image>` and no leftover `${`. Lettering is glyph outlines.
- `logo-sheet.png` is 1600 × 1200 RGB. `app-icon-1024.png` is 1024 × 1024 RGB. `favicon.ico` contains 16, 32 and 48 px images.

## Notes

- **The logos got wider.** "Tidewick & Co." is about 60 % wider than "Tidewick". I kept the type size and widened the canvases instead of shrinking the wordmark, so the logos are about 4.1:1 (horizontal) and 2.0:1 (stacked). Anywhere that placed the old files in a fixed-size box will show them smaller.
- **The tagline uses U+00B7 (middle dot) as its separator.** Spaces surround each dot.
- The mark, favicon and app icon don't include the name, so the brand change didn't require any change to them.
