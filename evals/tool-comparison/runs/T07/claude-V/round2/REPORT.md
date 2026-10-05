# T07 Name badges, round 2 (claude-V, Vixl MCP)

## What I was asked to change
1. Add an 11th badge: Iris / Van der Berg / Speaker / Lowtide Labs.
2. Change the Sponsor color to plum `#6b3f69`.
3. Regenerate every badge and the print PDF.

I wrote everything to `round2/` and changed nothing outside it. The round-1 files and the fixture CSV are untouched.

## Files in round2/
| File | What it is / how I made it |
| --- | --- |
| `badges.csv` | A copy of `fixtures/badges.csv` with one row added at the end: `Iris,Van der Berg,Speaker,Lowtide Labs`. This is the data for round 2. |
| `badge.vixl` | A copy of the round-1 template. I made no layout edits. The Sponsor color is a per-badge variable (`bar`, plus `bar_ink` for the role text), so I changed it at export time and didn't edit the template. The template's default variables are still row 4 (Bartholomew, Attendee). |
| `badges/badge-01.png` … `badge-11.png` | One `vixl_export_file(document=round2/badge.vixl, variables={...})` call per CSV row, in file order. All 11 are 1200×900 px. |
| `badges-print.vixl` | A copy of the round-1 imposition document, which I edited (details below). |
| `badges-print.pdf` | Exported from `round2/badges-print.vixl`. It has 2 pages, each 612×792 pt (US Letter, portrait). |

## Color change
- Sponsor bar: `#6b3f69`. The sampled bar pixel is (107, 63, 105) on badges 05 (花子 山田) and 09 (Ana Lucía Gómez).
- The role text on the plum bar is now **white** `#ffffff`, where it used to be navy on coral. Navy on plum would have too little contrast. `vixl_color contrast` gives white on `#6b3f69` a ratio of 8.27:1, which passes AA and AAA.
- The other role colors are unchanged.

## Badge 11
Iris / Van der Berg / Lowtide Labs on an amber `#f2a541` SPEAKER bar with navy text. It uses the same template, and the fit boxes handle the name length. I looked at the render: nothing is clipped or overlapping.

## Regeneration check
I compared the new PNGs pixel by pixel against round 1 with PIL:
- Badges 01–04, 06–08 and 10 are identical to round 1.
- Badges 05 and 09 differ, and only because of the Sponsor color change.
- Badge 11 is new.

## Print PDF changes
- **Page 1 (badges 1–6):** I replaced all six badge images with the round-2 PNGs. The grid and crop marks are unchanged.
- **Page 2 (badges 7–11):** It now holds 5 badges, not 4, so I re-laid it out on the same 2×3 grid as page 1: 0.25 in side margins and a 1 in top margin.
  - Row 1: badges 7 and 8. Row 2: badges 9 and 10. Row 3: badge 11 in the left column.
  - The sixth slot (bottom right) is blank.
  - The crop marks now sit in exactly the same places as on page 1, including the extra horizontal mark pair at the bottom cut line (y = 10 in). The grid is centered on the page as a full 6-slot frame. Badge 11 on its own is not centered horizontally; it stays in the left column so all the cut lines line up.
- **How I did it in Vixl:**
  - I imported the new PNGs with `vixl_import_image`.
  - On page 1, I removed the old image layers and put the imported ones in their place with `rename` and `move`.
  - On page 2, I swapped each layer's image with `replace-contents` (by asset id), moved b07–b10 up by 450 px, and made b11 by duplicating b10 and swapping in badge 11's image.
  - I moved the page-2 crop marks with `move` and added two more by duplicating existing marks.
  - I checked the result with `vixl_render_preview(page="all")` and by rasterizing the PDF with pdftoppm.

## Still true from round 1
- The PDF content is raster: 300 dpi badge images, 0 embedded fonts.
- Badges are butted together with no gutter or bleed.
- The CJK name renders in the regular weight of the Noto Sans JP fallback, not bold.

## Notes and uncertainties
- One `vixl_import_image` call (badge 02) timed out after 60 s on the client side, but the layer had been imported. I confirmed this by inspecting the document and used it.
- I didn't re-run `vixl_check` per row. I checked the two changed badges and the new one by looking at their renders, and checked the rest by the pixel comparison above.

## Tool calls
About 50 tool calls in this round: Vixl MCP, Bash, Read and ToolSearch together, counting this report and the final hand-off.
- 29 Vixl calls that touched files: 11 badge exports, 11 image imports, 1 PDF export, 4 `operations_apply` (including one rejected dry run), 2 document opens.
- 4 Vixl inspects, 2 operation-schema lookups, 1 color contrast check, 1 preview and 2 document closes.
- The rest were Bash, Read and ToolSearch.
