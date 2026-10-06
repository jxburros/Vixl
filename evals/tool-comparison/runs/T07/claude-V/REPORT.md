# T07 · Name badges — lane V (Vixl)

All the visual work was done with the Vixl MCP tools: document create, font pair/install, operations_apply, check, render_preview, workflow `merge-impose`, and export_batch. I did not draw pixels or write SVG/HTML myself. The only script, `prepare_data.py`, adds columns to the CSV; I explain why below. I used Python/Poppler only to check outputs (PNG sizes, `pdfinfo`, `pdftotext`, `pdffonts`, and a contact sheet for viewing).

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `badge-template.vixl` | Editable source: one 1200 × 900 px badge at 300 dpi (4 × 3 in) with `${first_name}`, `${last_name}`, `${company}`, `${role_label}`, `${bar_color}` and `${bar_ink}` variables | `vixl_document_create` (1200×900, dpi 300, background `#fbf8f2`), `vixl_font_pair montserrat-open-sans`, `vixl_font_install` (Montserrat 500, Noto Sans JP 500 and 700), then one `vixl_operations_apply` batch (variables, shapes, text, `text-layout` fit boxes, `font-fallbacks`) and a few small edits to move or resize layers |
| `badges-data.csv` | The fixture plus three columns the template needs: `role_label`, `bar_color` and `bar_ink` | `python3 prepare_data.py ../../../fixtures/badges.csv badges-data.csv` |
| `prepare_data.py` | Script that maps each role to its bar colour, bar text colour and capitalised label. It copies the name, role and company cells unchanged | Written by hand |
| `badges/badge-01.png` … `badge-10.png` | One badge per CSV row, in file order, 1200 × 900 RGB PNG | `vixl_export_batch` on the template, with each target's `variables` set to that row's values |
| `badges-print.pdf` | US Letter portrait, 2 pages, 2 columns × 3 rows, actual size (4 × 3 in per badge), grid centred (0.25 in left/right, 1 in top/bottom), crop marks at every cut line. Page 2 holds badges 7–10 in the same grid positions | `vixl_workflow merge-impose` with template + `badges-data.csv`, `sheet {size: letter, orientation: portrait, cols: 2, rows: 3, align: center, crop_marks: true}`, `check: design`. The PDF is vector, its text is selectable, and its 4 fonts are embedded subsets |
| `badges-sheet.vixl` | Editable imposition sheet written by the same merge: one page per sheet, one live link per badge. Re-running is `{"rerun": "…/badges-sheet.vixl"}` | `merge-impose` `sheet_document` |

## Design

- **Type:** Montserrat Bold for the first name (170 px) and the role, Montserrat Medium for the last name (84 px), Open Sans Regular for the company (42 px) and the dates (32 px). The event name is Montserrat Bold 38 px in capitals.
- **Layout:** The event name and dates sit at the top left under a short rule in the role colour. Then come first name, last name and company. A full-width bar 180 px tall runs along the bottom with the role in capitals, centred.
- **Fitting:** Each of the four variable text layers has a fixed `text-layout` box, 1040 px wide (80 px margins), with `fit: true`. Long text shrinks to fit the box instead of being clipped. The merge's validation reported no overflow on any row.
- **Empty company:** The company layer has `hide_if_empty`, so Sam Okafor's badge (row 6) leaves the line out entirely.
- **Bar colours:** Speaker `#f2a541`, Attendee `#a8d5c8`, Staff `#14263b`, Sponsor `#e2725b`. Volunteer (row 7) uses the Attendee colour and prints "VOLUNTEER".
- **Bar text and contrast (WCAG, from `vixl_color contrast`):** Bar text is navy `#14263b` on amber (7.47:1), sea-foam (9.5:1) and coral (4.96:1), and white on navy (15.33:1).
- **Names:** Every name prints exactly as written in the file, accents included. The PDF text extraction (`pdftotext`) matches the CSV for all 10 rows, including Zoë, Ångström-Okonkwo, O'Brien, Ana Lucía, Gómez, 花子 and 山田.

## Departures, choices and uncertainties

1. **I added columns to the CSV with a script.** Vixl's merge maps CSV columns to template variables directly. It has no lookup from role to colour and no upper-casing, so I generated `badges-data.csv` with the derived columns. It is data preparation, not drawing, but it is outside Vixl.
   - To add a role or change a colour, edit the mapping in `prepare_data.py`, regenerate the CSV and rerun the merge.
   - The original `role` column is kept but unused; the merge was run with `unknown: ignore`.
2. **Japanese glyphs share one fallback weight.** Montserrat and Open Sans have no CJK glyphs, so Noto Sans JP is set as a fallback font.
   - In Vixl, `font-fallbacks` is a single setting for the whole document. My second call (Noto Sans JP 500) replaced the first (700).
   - As a result, both 花子 and 山田 render in Noto Sans JP Medium. 花子 is therefore lighter than the Latin first names, though it is still the largest line.
   - Noto Sans JP 700 is still embedded in the template but unused, which is most of the template's 6.9 MB size.
   - The merge logged "uses fallback glyphs" warnings for row 5. That is expected: no character prints as tofu.
3. **One check warning left on purpose.** The last `vixl_check` passed with one legibility warning: `event-dates` is small at a 320 px thumbnail width. That check targets screen thumbnails. At print size the dates are 32 px = about 7.7 pt, which fits "small" in the brief. I accepted it.
4. **No bleed and no gutter.** The badges are flat colour with no bleed, so the six badges butt together and share cut lines. Crop marks are in the margins only, with none inside the sheet. Background areas meet exactly at the shared trim lines.
5. **Badge background.** The badge background is a warm off-white `#fbf8f2`, not pure white, so the PNGs and the PDF cells show it up to the trim.
6. **PDF colour.** The PDF is RGB, which is the merge-impose default. I did not make a CMYK version, since the brief didn't ask for one.
