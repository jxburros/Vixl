# T16 round 2: menu revisions, lane V (Vixl via MCP)

## What I changed
1. **Coffee prices up $0.25.** Espresso $3.25, Macchiato $3.75, Cortado $4.25, Flat white $5.00, Cappuccino $5.00, Latte $5.25, Crème brûlée latte $6.00, Drip coffee $3.00. I read "coffee price" as the items in the COFFEE section. The Seasonal lattes, Tea and Bakery prices are unchanged.
2. **Removed "Drip refill"** along with its $1.00 price and its leader line.
3. **Added "Oat milk +$0.75"** under the Coffee items, at x=425, y=1518 (layer `coffee-note`). It uses the same style as the seasonal descriptions: Lato Italic, 42 px (10.1 pt), color #3b4c60.

Nothing else changed. Every other layer keeps its position, font and color. Removing the refill line freed about 81 px, and the note now fills that space, so the gap before TEA is about the same as before. The note ends at y=1579 and the TEA heading starts at y=1680.

## How
- First I copied `../menu.vixl` to `round2/menu.vixl` and edited only the copy. Nothing outside round2/ was modified.
- `vixl_document_open` and `vixl_document_inspect` (full detail) on the three Coffee rich-text layers: `coffee-names`, `coffee-leaders` and `coffee-prices`.
- One atomic `vixl_operations_apply` batch with four operations:
  - three `rich-text` re-sets with 8 lines in place of 9, the same Lato span font, line_height 1.3 and right-aligned paragraphs where they were before;
  - each of those boxes shortened from 734 to 653 px;
  - one new `rich-text` layer for the note.
- Verification:
  - `vixl_render_preview` zoomed on the Coffee section. Prices are still right-aligned with the decimals lined up, and the dot leaders match up with the names.
  - `vixl_check` for bounds, overlap, contrast, safe_area=150 px and print: it passed with 0 issues.
- Exports with `vixl_export_file`:
  - `menu.pdf` as a vector PDF;
  - `menu-preview.png` at scale 0.5 and 150 dpi.
- Output checks (scripts):
  - PIL: the PNG is 1275×2100.
  - `pdfinfo`: 1 page at 612×1008 pt.
  - `pdffonts`: Playfair Display Bold, Lato Regular and Lato Italic are embedded.
  - `pdftotext`: shows the new prices and the note, and no "Drip refill".

## Files (round2/)
- `menu.vixl`: the edited, editable source
- `menu.pdf`: one US Legal page with real text
- `menu-preview.png`: 1275×2100 px
- `REPORT.md`: this file

## Notes
- The round-1 caveats still apply. In particular, `vixl_check`'s fallback-font warning is a false positive, because fonts are set per span.
- Tool calls: 23 in total for this round, counting the call that writes this report and the final handback.
