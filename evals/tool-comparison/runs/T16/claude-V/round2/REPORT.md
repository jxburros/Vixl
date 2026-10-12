# T16 Café menu, round 2: report (lane V, Vixl)

## What changed

| Change | Result |
| --- | --- |
| Every coffee price up by $0.25 | Espresso $3.00 → $3.25, Macchiato $3.50 → $3.75, Cortado $4.00 → $4.25, Flat white $4.75 → $5.00, Cappuccino $4.75 → $5.00, Latte $5.00 → $5.25, Crème brûlée latte $5.75 → $6.00, Drip coffee $2.75 → $3.00 |
| "Drip refill" removed | Its row ($1.00) and its dot leader are gone. |
| Note under Coffee | "Oat milk +$0.75" now sits directly under the last coffee row. It uses the same style as the seasonal descriptions: DM Sans 24 px (11.5 pt), muted navy `#4a5668`, no leader and no price column. |

Nothing else changed. The Tea, Bakery and Seasonal prices are the same as in round 1. That includes the Smoked maple and Gingerbread lattes, which are listed under SEASONAL, not COFFEE. The key, the footer, the fonts, the colors and the frames are also unchanged. The removed row and the added note are the same height, so the Coffee table keeps its 420 px height. As a result the Tea, Bakery and Seasonal sections, their leaders, the key and the footer stay in the same positions.

## How

All edits were made with the Vixl MCP tools. I wrote no SVG, HTML or pixels.

1. I copied `../menu.vixl` to `round2/menu.vixl` and opened it with `vixl_document_open`. I then ran `vixl_document_inspect` to read the layer tree.
2. I applied one atomic `vixl_operations_apply` batch. I ran it as a dry run first, then applied it with `check=true`:
   - `table-data` on the `coffee` table. `set` changed the eight prices, `remove_rows: ["Drip refill"]` removed that row, and `append: [["Oat milk +$0.75", null]]` added the note row. The table redraws in place and keeps its layer IDs. Because the price column uses decimal alignment, the new prices still line up on the decimal point.
   - `remove leader-09`. This was the dotted leader for the Drip refill row.
   - `text-set` on the new note cell to set it to 24 px and `#4a5668`, so it reads as a note rather than a menu item.
3. I ran `vixl_check` with bounds, overlap, contrast, print, legibility, fonts, placeholders and a 75 px (0.5 in) safe area. It passed with no findings. I then looked at a full-page preview and a zoomed preview of the Coffee section.
4. I exported with `vixl_export_file`:
   - `menu.pdf`: one page, 612 × 1008 pt (US Legal), vector, with DM Serif Display and DM Sans embedded.
   - `menu-preview.png`: 1275 × 2100 px, RGB, 150 dpi.

To check the outputs I used `pdftotext`, `pdfinfo`, `pdffonts` and PIL. `pdftotext` shows the new prices and the note line, and "Drip refill" no longer appears in the text.

## Files in round2/

- `menu.vixl`: the editable source.
- `menu.pdf`
- `menu-preview.png`
- `REPORT.md`: this file.

## Notes

- I read "every coffee price" as the eight items in the COFFEE section. The seasonal lattes were not changed.
- In the source, the note layer keeps the table's cell name `coffee/r9c1`.
