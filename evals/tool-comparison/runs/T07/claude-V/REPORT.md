# T07 Name badges — claude-V (Vixl MCP)

Timing: start 22:19:09 UTC, end 22:26 UTC, 2026-10-05 (about 7 minutes). About 62 tool calls in all (Vixl MCP, Bash, Read and ToolSearch together).

## Files
| File | How it was made |
| --- | --- |
| `badge.vixl` | Editable source and template. A 1200×900 px, 300 dpi Vixl document. The fonts are Montserrat 700 (names, role) and Open Sans 400 (event, company), from the `montserrat-open-sans` pairing, plus Noto Sans JP 700/400 set as font fallbacks for the CJK names. The text layers use the variables `${first}`, `${last}`, `${company}` and `${role}`. The bar fill is `${bar}` and the role text color is `${bar_ink}`. |
| `badges/badge-01.png` … `badge-10.png` | One `vixl_export_file` call per CSV row, in file order, passing that row's values as `variables`. Each is 1200×900 px (checked with PIL). |
| `badges-print.vixl` | Editable imposition source. A two-page Letter document at 300 dpi (2550×3300 px). It holds the ten badge PNGs as image layers and the crop marks as 3 px black rectangles. |
| `badges-print.pdf` | Exported from `badges-print.vixl`: 2 pages, 612×792 pt (US Letter, portrait). Each badge is a 1200×900 px image placed at 288×216 pt, which is 4×3 in at actual size. |

## Design
- Top-left: "HARBOR MAKERS SUMMIT 2026" (34 px), with "November 20–21, 2026 · Port Ellery" (32 px) under it, then a short coral rule.
- First name: Montserrat Bold in a 1040×180 box with `fit: true`. Last name: a 1040×110 fit box. Company: Open Sans in a 1040×72 fit box. The fit boxes shrink long names (Bartholomew / Featherstonehaugh-Villanueva / Port Ellery Maritime Museum & Historical Society) and enlarge short ones (Jo / Li). Because the boxes are nested in size, the first name is always the largest line, then the last name, then the company.
- Bar: full width, y 690–900, in the role color. The role is in capitals and centered. Text on the bar is navy `#14263b` on amber, sea-foam and coral, and white on navy (Staff). The contrast check passed.
- Priya Raman's role, Volunteer, gets the sea-foam bar and prints "VOLUNTEER".
- Sam Okafor has no company, so the company line is an empty string and nothing prints there. Nothing else moves, so his badge has blank space where that line would be.
- I passed every name to Vixl exactly as it appears in the CSV, including Zoë, Ångström, O'Brien, Ana Lucía, Gómez, Tidewick Café and 花子 山田. I checked the renders visually.

## Print sheet
- Six badges per page in 2 columns × 3 rows, centered. The grid is 8×9 in, with margins of 0.25 in left and right and 1 in top and bottom.
- There are only 10 badges, so page 2 has 4 of them (2×2). They are centered on that page (y offset 2.5 in).
- Crop marks sit only in the margins. Every cut line, including the shared edges between badges, gets a mark about 0.2 in long, 0.06 in from the trim. The marks are 3 px wide (0.24 pt).

## Differences from the brief and open questions
- **The PDF is raster, not vector.** Each badge sits in the PDF as a 300 dpi PNG (the export reports 0 embedded fonts). This keeps each badge identical to its PNG, but the text in the PDF is not selectable vector text.
- **The badges are butted together.** Badges touch inside the grid, so there is no bleed and no gutter. A slightly-off cut will show a sliver of the next badge's cream or bar color.
- **The Japanese names are not bold.** 花子 山田 render through the Noto Sans JP fallback, and they look regular weight rather than bold. I set the bold fallback, but the renderer may have picked the 400 weight instead.
- **Fonts had to be set with `vixl_text_add`.** The MCP rejects the `font` field in `text` and `text-set` operations, so I added each text layer with `vixl_text_add(font=...)`.
- **Short names leave a larger gap.** The fit boxes have fixed positions, so for short names (Jo / Li) the space between the first-name and last-name lines is larger. Nothing overlaps.
- **Check results.** `vixl_check` (40 px safe area) found no errors. It gave three warnings: the full-width bar leaves the safe area, which is intended, and the event and date lines are small at thumbnail width. Those lines are about 8 pt at print size, which I chose on purpose.
- **I only ran the check once.** It ran on the template's default values (the longest row, row 4). The other nine rows I checked by looking at the renders, not with the automatic check.
