# T16 round 2 · Café menu changes (lane V, Vixl)

## What changed
| Item | Before | After |
| --- | --- | --- |
| Espresso | $3.00 | $3.25 |
| Macchiato | $3.50 | $3.75 |
| Cortado | $4.00 | $4.25 |
| Flat white | $4.75 | $5.00 |
| Cappuccino | $4.75 | $5.00 |
| Latte | $5.00 | $5.25 |
| Crème brûlée latte | $5.75 | $6.00 |
| Drip coffee | $2.75 | $3.00 |
| Drip refill | $1.00 | removed (name, price, cents and dot-leader layers) |
| New note | — | "Oat milk +$0.75" under the Coffee list |

"Every coffee price" was read as every item in the **Coffee** section. The two coffee drinks in the
Seasonal section (Smoked maple latte $6.00, Gingerbread flat white $5.75) were **not** raised; say so
if they should be. Nothing outside the Coffee section changed.

## How
- `cp ../menu.vixl round2/menu.vixl`, then every edit went through the Vixl MCP tools on that copy
  (`document=` passed on each call); the round-1 files were not opened or touched.
- One `vixl_operations_apply` batch: `text-set` on the 16 `p-*`/`c-*` price layers, `remove` on
  `n-refill`, `p-refill`, `c-refill`, `l-refill`, and `duplicate` of the seasonal description layer
  `d-smokedmaple` → `rename` `note-oatmilk` → `text-set "Oat milk +$0.75"`. The note therefore uses
  the existing description style: DM Sans Italic 42 px (10.1 pt), muted navy `#3f4b5c` (7.87:1 on cream).
- Second batch: `move`s to restore exact baselines. Changing cents between ".75" and ".00"/".25"
  shifts the ink top by 0.6 px, so c-macchiato, c-flatwhite, c-cappuccino, c-cremebrulee and c-drip
  were moved so every row's name, dollars and cents again share one baseline (916, 998 … 1490). The
  note sits on baseline 1572, the slot the refill row occupied, so the Tea section and everything
  below stay exactly where they were.
- Decimal alignment holds: dollars stay right-pinned at x = 2215 by their constraints, cents start
  at 2215. The leaders were not changed; they still end 33–35 px before each price.
- `vixl_check` (bounds, overlap, contrast, safe_area=150, legibility, fonts, print): passed,
  0 errors, the same 3 "review" warnings as round 1 (the checker cannot measure subtitle/key/footer).
- Zoomed `vixl_render_preview` of the Coffee section looked right.
- `vixl_export_batch` → `menu.pdf` (vector, 8.5 × 14 in, 4 embedded fonts, no raster fallbacks) and
  `menu-preview.png` (scale 0.5, 150 dpi, 1275 × 2100, size checked with PIL). `pdftotext` shows the
  new prices, no "Drip refill", and "Oat milk +$0.75" after Drip coffee.

## Files
`menu.vixl`, `menu.pdf`, `menu-preview.png`, `REPORT.md`. All are in this round2/ folder.
