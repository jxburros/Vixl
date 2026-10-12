# T16 Café menu: report (lane V, Vixl)

All visual work was done through the Vixl MCP tools (`vixl_document_create`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview`, `vixl_export_file`). I wrote no SVG, HTML or pixels. I ran one small Python one-liner to work out dot-leader start and end points from the text bounds Vixl had reported. I also used `PIL`, `pdfinfo`, `pdffonts` and `pdftotext` to check the outputs.

## Files

| File | How it was made |
| --- | --- |
| `menu.vixl` | The editable Vixl source. I created it with `vixl_document_create(size="legal", dpi=150, background="#f7f1e5", font_pairing="dm-serif-dm-sans")`, so the canvas is 1275 × 2100 px (8.5 × 14 in at 150 dpi, no bleed). I then built the page in five `vixl_operations_apply` batches. |
| `menu.pdf` | `vixl_export_file` to PDF. It is one page, 612 × 1008 pt (US Legal), with vector content and real, selectable text. DM Serif Display and DM Sans are embedded as subsets. `pdftotext` returns every item, price, description, the key and the footer. |
| `menu-preview.png` | `vixl_export_file` to PNG at 150 dpi: 1275 × 2100 px, RGB. |
| `REPORT.md` | This file. |

## Design

- **Palette.** I used the brand colors from the brief. The page is cream (`#f7f1e5`). Text is navy (`#14263b`). Amber (`#f2a541`) is used only for decoration: the inner frame, the rules under section headings and the short rule above the key. Amber on cream does not have enough contrast for text.
- **Type.** DM Serif Display is used for the title (124 px, about 59.5 pt) and the section headings (44 px, about 21 pt). DM Sans is used for:
  - item names and prices: 30 px, 14.4 pt
  - the subtitle: 36 px
  - the seasonal descriptions: 24 px, 11.5 pt, muted navy `#4a5668`
  - the key: 26 px, 12.5 pt
  - the footer: 28 px, 13.4 pt

  The smallest text on the page is 11.5 pt, which meets the 9 pt minimum.
- **Margins.** There is a navy frame inset 0.6 in from each edge and an amber frame at 0.68 in. All text sits inside both frames, at least 1.2 in from the side edges. Nothing is placed within 0.5 in of the edge.
- **Item lists.** Each section is a Vixl `table` (`coffee`, `tea`, `bakery`, `seasonal`). It has a header row for the section name, a `1fr` name column and a price column with `align: "decimal"`, so the decimal points line up. You can see this on "$1.00": it sits a little to the right so that its point lines up with the others. All four tables share the same x position, width and column widths, so the price column lines up across sections too. A `stack` group (`sections`, 58 px gap) spaces the four tables.
- **Dot leaders.** Vixl has no tab-leader feature (`docs/use-cases.md` lists this as BLK-07). I drew each leader as a dotted path shape: `dash: [0.01, 12]`, round caps, 3.5 px stroke, `#7d8794`, about 6 px above the text baseline. There are 22 of them, grouped as `leaders`. Each leader starts and ends on a 12 px grid, so the dots line up vertically from row to row. Every leader ends at x = 972, 26 px before the price column.
- **Seasonal descriptions.** The table wrapped each description onto two lines at 30 px, so I put each one back on a single line with `text-set` at 24 px. I then used `move baseline_y` to place the description baselines and the rows that follow, so each description sits directly under its item.

## Checks

The last `vixl_check` passed with no findings. It ran these checks: bounds, overlap, contrast, print (which includes minimum type size in points), legibility, fonts and placeholders, with a 75 px (0.5 in) safe area. The checks also passed after every build batch. I looked at the full page and zoomed-in previews before exporting.

## Differences from the brief and choices I made

- **Copy.** All sections, names, prices, descriptions, tags, the key and the footer are exactly as given.
- **Layout.** I used a single column, with section headings in capitals as the brief lists them.
- **Leaders.** They are drawn dots (vector shapes), not period characters. In the PDF text layer, names and prices are therefore separated by spaces rather than by "....".
- **Background.** The cream fill covers the whole page. A desktop printer will leave its usual unprinted white border, which only trims the cream at the very edge. All content and both frames stay well inside the printable area.
- **Rules.** The short amber rule above the key is a path shape. I also used it to replace an earlier `line` shape.

## Things I'm unsure about

- I checked decimal alignment in the preview only, by eye. It looks right, including the "$1.00" offset, but I did not measure the position of each decimal point.
- The gap between where the name ends and where the leader starts varies from 16 to 28 px, because the leaders snap to the 12 px grid.
- I did not attach a custom check suite (`suite-set`). I relied on the built-in checks, including the print check for type size.
