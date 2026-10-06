# T16 · Café menu (lane V, Vixl)

## Files
| File | How it was made |
| --- | --- |
| `menu.vixl` | Editable Vixl source. Made through the Vixl MCP tools: `vixl_document_create(size="legal")` (2550 × 4200 px, 300 dpi, no bleed), `vixl_font_pair` (dm-serif-dm-sans), `vixl_font_install` (DM Sans 700, DM Sans 400 italic, plus DM Mono 400, which is registered but no longer used), and then `vixl_operations_apply` batches (`solid`, `shape`, `text`, `text-set`, `text-style`, `move`, `constrain`, `edit-layers`). Every text layer is still live text. |
| `menu.pdf` | `vixl_export_batch` → vector PDF, one page of 612 × 1008 pt (8.5 × 14 in), RGB. The text is real, selectable text: `pdffonts` lists 4 embedded subset fonts (DM Serif Display, DM Sans Regular, Bold and Italic). `pdftotext` gets every item and price back out in reading order. `raster_fallbacks` is empty. |
| `menu-preview.png` | The same export batch at scale 0.5 and dpi 150 → 1275 × 2100 px RGB. I checked the size with PIL. |
| `REPORT.md` | This file, written with a shell heredoc. |

## Design and typesetting
- **Page:** the page background is white. A cream (`#f7f1e5`) panel is inset 0.5 in (150 px) from every edge, so nothing prints to the paper edge. A navy hairline frame sits at 0.6 in and a navy footer band runs along the bottom of the frame. All text starts 0.85 in (255 px) from the left and right edges. Nothing sits closer than 0.5 in to the trim.
- **Type and colors:** the title is DM Serif Display at 200 px (48 pt). The subtitle is DM Sans Italic at 64 px. Section heads are DM Sans Bold at 54 px with +8 tracking and a short amber (`#f2a541`) bar under each. Item names and prices are DM Sans at 50 px (12 pt). Navy `#14263b` is used for text. Amber appears only in rules, never in text, because it has too little contrast on cream.
- **Smallest text:** the seasonal descriptions are 42 px = 10.1 pt in muted navy `#3f4b5c`, which has 7.87:1 contrast on cream. The key is 44 px (10.6 pt) and the footer is 46 px (11 pt). Nothing is under 9 pt.
- **Decimal alignment:** each price is two text layers. `p-*` holds the dollars ("$3") and is pinned by its right edge at x = 2215 (`constrain right: canvas.left+2215`). `c-*` holds the decimal point and cents (".00") and starts at x = 2215. Every decimal point therefore sits at the same x. Because DM Sans figures are proportional, the right edge of the price column is ragged by up to about 12 px. I chose this over a monospaced font: DM Mono, my first try, draws slashed zeros that look wrong on a menu.
- **Baselines:** names, dollars and cents in each row share one exact baseline (e.g. 916, 998, 1080 …, checked in the apply results). Vixl places text by the top of the ink, so I moved each layer by the reported baseline offset to line them up.
- **Dot leaders:** each row has a dotted `line` shape (`dash [0.5, 17.5]`, round caps, grey `#6e7682`). It starts 24 px after the measured right edge of the item name and ends about 34 px before the price. The lengths are set by hand from the measured name widths, so a leader will not follow its name if the name text changes.
- **Content:** all sections, names, prices, tags, descriptions, the key text and the footer text are exactly as given in the brief, including é, û, en dashes and middle dots. Every glyph is present in the fonts; I checked this with fontTools.

## Checks
- `vixl_check` (bounds, overlap, contrast, safe_area=150 px, legibility, fonts, print) passed with 0 errors.
- It gave 3 "review" warnings. The checker could not measure contrast for the centered layers subtitle, key and footer: it reports an internal array-size mismatch, apparently from their half-pixel x positions. I checked those colors by hand with `vixl_color`: navy on cream is 13.63:1, and the footer is cream on navy, the same pair.
- I looked at the full-page preview and zoomed renders to check alignment.

## Deviations, choices and doubts
- The brief does not name a layout. I typeset by hand instead of using a Vixl `layout-apply` layout, because a price list needs exact rows.
- The tags (N), (V) and (GF) are set in the same style as the item names.
- There is extra space between the key and the footer band (about 0.5 in). The layout is a single column and fits on one page with room to spare.
- The PDF is RGB, not CMYK, because it is for a desktop printer.
- DM Mono 400 is still registered in `menu.vixl` but is not used by any layer and is not in the PDF.
- I have not test-printed the page. Printers that cannot print within about 0.5 in of the edge will still print everything, because the cream panel starts at exactly 0.5 in.
