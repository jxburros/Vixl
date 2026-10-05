# T16 · Café menu — lane W (claude-W)

## Files
| File | What it is | How it was made |
| --- | --- | --- |
| `menu.html` | Editable source: HTML/CSS + small inline SVG wave mark; menu items live in one JS array | Hand-written |
| `render.py` | Render script (Python Playwright, headless Chromium) | Hand-written |
| `menu.pdf` | 1 page, 612 × 1008 pt (US Legal 8.5 × 14 in, portrait), real selectable text, fonts embedded | `page.pdf(width=8.5in, height=14in, print_background=True, margins 0)`; page geometry handled in CSS (`@page` margin 0, content box inset 0.5 in) |
| `menu-preview.png` | 1275 × 2100 px (150 dpi) | Playwright screenshot of the same page, viewport 816 × 1344 CSS px at device scale factor 1.5625 |

## Design
- Navy header band with the title "Tidewick Café" (54 pt) and "Coffee by the harbor" (17 pt, amber italic); navy footer band holding the hours/address line. A double navy frame sits on the 0.5 in margin line; everything is inside it. The paper stays white (no cream page flood, since a desktop printer can't print to the edge). Cream is used only for the SEASONAL panel.
- Fonts are local system fonts: P052 (Palatino clone) for text, URW Gothic Demi for section heads and dietary tags. No web fonts.
- Item names 13.5 pt; descriptions 11 pt italic; key 11 pt; footer 11.5 pt; the smallest text is the tags (N)/(V)/(GF) at 9.5 pt. The script checks every computed font size, and the smallest is 12.67 px = 9.5 pt.
- Dot leaders are a dotted CSS border running from each name to its price, not "." characters, so the PDF text stays clean.
- Prices sit in a fixed-width, right-aligned column using tabular figures. The script measures where each decimal point lands: all 22 decimal points share one x position (655.56 CSS px), so they line up.
- Sections, item names, prices, tags and descriptions are exactly as given in the brief. The key ("V = vegan · GF = gluten-free · N = contains nuts") is just above the footer, and the footer text matches the brief.

## Deviations / choices
- Tags are styled in amber Gothic caps but kept as the literal text "(N)", "(V)" and "(GF)" after the name.
- The brief's three brand colours are used. I added one darker amber (#b8730f) for the tag and key letters, so they read better on white than #f2a541 would.
- The preview PNG is a screenshot of the HTML, not a rasterised PDF. I rasterised the PDF at 150 dpi with pdftoppm and compared it to the PNG: RMSE is 0.063, which only shows anti-aliasing differences, and the layout is the same.

## Unsure about
- Chromium embedded the OpenType-CFF fonts (P052, URW Gothic) as Type 3 fonts. They are embedded, carry Unicode maps, and the text extracts correctly. Type 3 prints fine on normal desktop printers, but some preflight tools flag it.
- Section headings have 4 pt letter-spacing, so pdftotext pulls them out as "C O F F E E" and so on. The text is otherwise correct.
- The bottom margin from the outer frame to the page edge is exactly 0.5 in. Some desktop printers can't print within about 0.25 in of the edge, but 0.5 in is safe.

## Timing
Start 22:21:45 UTC, end 22:22:55 UTC (2026-10-05), about 1 min 10 s. 8 tool calls.
