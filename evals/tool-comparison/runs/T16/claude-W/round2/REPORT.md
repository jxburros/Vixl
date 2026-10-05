# T16 · Café menu, round 2 (lane W, claude-W)

## What changed
- **Coffee prices +$0.25.** Espresso is now $3.25, Macchiato $3.75, Cortado $4.25, Flat white $5.00, Cappuccino $5.00, Latte $5.25, Crème brûlée latte $6.00 and Drip coffee $3.00.
- **"Drip refill" removed.** The Coffee section now has 8 items.
- **Note added under Coffee.** "Oat milk +$0.75" sits directly below Drip coffee and above the TEA heading. It is set in 11 pt italic, the same muted slate (#3c4b5e) as the seasonal descriptions, and right-aligned so it ends on the price column's right edge.
- Nothing else changed. Tea, Bakery, Seasonal, the key, the footer and the layout are the same as round 1.

## Interpretation
- I read "every coffee price" as the items in the COFFEE section. The coffee drinks in SEASONAL (Smoked maple latte, Gingerbread flat white) and Chai latte under TEA keep their original prices.

## Files (all in round2/)
| File | How it was made |
| --- | --- |
| `menu.html` | Copied from round 1 and edited. I changed the COFFEE row of the data array: new prices, refill row removed, and a third element added for the section note. The render loop now writes a `<p class="note">` when a section has a note, and I added one `.note` CSS rule. |
| `render.py` | Copied from round 1. The only change is the file path, which now points to `round2/menu.html`. |
| `menu.pdf` | Made by `python3 render.py` (Playwright headless Chromium `page.pdf`). It is 1 page, 612 × 1008 pt (US Legal), and the text is real text. |
| `menu-preview.png` | A Playwright screenshot from the same run, 1275 × 2100 px (150 dpi). |

## Checks
- I checked these in the render script's output: every price's decimal point sits at the same x position (655.56 CSS px); nothing overflows; the page is 1344 CSS px tall, so it fits on one page; the smallest font is still 12.67 px, which is 9.5 pt.
- `pdfinfo` reports 1 page at 612 × 1008 pt. `identify` reports the PNG at 1275 × 2100. `pdftotext` shows the new prices.
- I looked at the preview by eye. Removing a row and adding the note row roughly cancel out, so the vertical rhythm is unchanged.

## Unsure about
- The Type 3 font embedding and the letter-spaced headings come out the same as in round 1 (see ../REPORT.md).

## Tool calls
5 tool calls: 4 to make and check the files, plus 1 to write this report.
