# T16 Café menu, lane V (Vixl via MCP)

**Timing:** start Mon Oct 5 22:21:18 UTC 2026, end Mon Oct  5 22:29:11 UTC 2026 (about 9 minutes). 39 tool calls, counting this one and the final handback.

## Files
| File | How it was made |
| --- | --- |
| `menu.vixl` | The editable Vixl source. Made with `vixl_document_create(size="legal")` (2550×4200 px at 300 dpi, cream `#f7f1e5` background). Fonts came from `vixl_font_pair("playfair-lato")` plus `vixl_font_install(Lato italic)`. All the content went in through `vixl_operations_apply`: `rich-text` layers whose spans name registered fonts, and `shape` layers for the rules and the ornament. |
| `menu.pdf` | `vixl_export_file`, vector PDF. One page, 612×1008 pt (8.5×14 in). The text is real, selectable text: `pdftotext` extracts it. Playfair Display Bold, Lato Regular and Lato Italic are embedded as subsets (checked with `pdffonts`). |
| `menu-preview.png` | `vixl_export_file` at scale 0.5 and 150 dpi. It is 1275×2100 px (checked with PIL). |

## Design and typesetting
- **Page and margins:** single column. Text runs from x=425 to 2125 px, so the side margins are 1.42 in. Top margin is about 0.77 in and bottom about 1 in. Every element is at least 0.5 in from the edge (`vixl_check` with safe_area 150 px passed). There is no bleed.
- **Colors:** the brand colors are used. Navy for the text, amber for the section rules and the header ornament, cream for the page.
- **Type:** Playfair Display 700 for the title (190 px = 45.6 pt) and the letter-spaced section heads (68 px = 16 pt). Lato for everything else:
  - Items and prices: Lato 50 px (12 pt).
  - Seasonal descriptions, the key and the footer: 42 px (10.1 pt).
  - Nothing is below 9 pt.
- **Prices:** each section has one rich-text box, right-aligned to x=2125. Lato's figures are tabular (I measured "$3" and "$5" both at 58 px, ".00" and ".75" both at 69 px). Since every price is $X.XX, the right edges line up and so do the decimal points. I checked this in zoomed previews.
- **Dot leaders:** each section has a right-aligned box of ". " leaders that ends 26 px before the price column, with the same line height as the names box so the baselines match. I measured each name's width with a dry-run `rich-text` batch and then set the dot count per line. The gap between a name and its first dot is roughly 25–50 px.
- **Text:** all sections, names, prices, descriptions and tags are exactly as in the brief, including the (N), (V) and (GF) tags. The tags are colored dark amber `#8a5212` (contrast 5.66:1 on cream). The key and footer text match the brief exactly, with single spaces around the "·".

## Deviations and things I'm unsure about
- **Cream page in the PDF:** the background is cream across the whole page. A desktop printer can't print to the edge, so the paper margins will come out white or unprinted. Only the cream tint is affected; nothing with content sits in that area. If you'd rather have a pure white page, change the canvas background.
- **Font warning from `vixl_check`:** it reports that 29 text layers use the bundled fallback font. That is a false positive. Through MCP, a layer's base font can't be set in operations (`font` is rejected), so I set the font on every span instead. The rendered previews and `pdffonts` both confirm Playfair and Lato are the fonts actually used. All other checks passed: bounds, overlap, contrast, safe area and print.
- **Decimal alignment:** the decimal points line up because the digits are equal width (tabular figures), not because of a true decimal tab.
- **Seasonal layers:** each seasonal item is its own set of layers (name, leader, price, description). The other sections use one box per column.
- **Spacing:** the vertical gaps between sections were chosen by eye, and there is a little more white space at the bottom than at the top.
