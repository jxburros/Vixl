# T07 · Name badges: Vixl lane (claude-V)

Everything was made with the Vixl MCP tools (`mcp__vixl__*`). I drew no pixels, wrote no SVG or HTML and used no image generator. The only scripts read the outputs to check them: PIL for sizes and a contact sheet, plus `pdfinfo`/`pdftotext`/`pdffonts`/`pdftoppm`, and one contrast-ratio calculation.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `badge.vixl` | Editable template: 1200 × 900 px at 300 dpi (4 × 3 in), with `${first_name}`, `${last_name}`, `${role}` and `${company}` variables | `vixl_document_create`, `vixl_font_pair` (inter-tight-inter: Inter Tight 800 for headings, Inter 400 for body), `vixl_font_install` (Noto Sans JP 700, registered as a `font-fallbacks` entry for the Japanese row), then `vixl_operations_apply` batches |
| `badges/badge-01.png` … `badge-10.png` | One per CSV row in file order, 1200 × 900 RGB PNG | `vixl_export_batch` on the template, each target with that row's values as `variables`. I typed the values from the CSV into the call by hand |
| `badges-print.pdf` | US Letter portrait, 2 pages; 2 columns × 3 rows of 4 × 3 in badges at actual size (scale 1.0), grid centred, crop marks at every cut line. Vector, with selectable text (embedded subsets of Inter Tight, Inter and Noto Sans JP) | `vixl_workflow("merge-impose")` with the template and `evals/tool-comparison/fixtures/badges.csv`, `sheet: {size: letter, orientation: portrait, cols: 2, rows: 3}`, `check: "design"`. It was dry-run first and then rerun after the last template fix |
| `badges-sheet.vixl` | Editable imposition sheet: one page per sheet, and each badge is a live `link` layer to `badge.vixl` with its row's variables. It records the merge, so `{"rerun": "badges-sheet.vixl"}` rebuilds the PDF | Written by the same merge-impose call |
| `REPORT.md` | This file | |

## Design

- **Top of the badge:** the event name "Harbor Makers Summit 2026" (Inter Tight 46 px, navy `#14263b`) with "November 20–21, 2026 · Port Ellery" under it (Inter 32 px, grey). A thin rule sits below them.
- **Name block:** a vertical `stack` group (1080 × 500, centred) holding three lines:
  - first name: Inter Tight 190 px, navy;
  - last name: Inter Tight 96 px, slate `#34475b`;
  - company: Inter 50 px, grey.

  Each line is a fixed-width text box (1080 px) with `text-layout fit: true`, so a long value shrinks to one line instead of being cut off or overflowing. In row 4, "Bartholomew", "Featherstonehaugh-Villanueva" and the 48-character company all shrank to fit.
- **Empty company:** the company layer has `hide_if_empty`. Row 6 (Sam Okafor, Staff) has no company, so the line disappears and the stack re-centres the name block, leaving no hole.
- **Role bar:** a full-width bar, 180 px high, at the bottom of the badge. Its fill is `${role|map:barcolor}`: Speaker `#f2a541`, Attendee `#a8d5c8`, Staff `#14263b`, Sponsor `#e2725b`, and any other role (`*`) the Attendee colour. The role is printed from `${role}` with `text_transform: uppercase`, so "Volunteer" prints VOLUNTEER on sea-foam.
- **Text on the bar:** the colour is `${role|map:barink}`, white on navy (Staff) and navy `#14263b` on the others. WCAG contrast is 7.47:1 on amber, 9.5:1 on sea-foam, 4.96:1 on coral and 15.33:1 for white on navy.
- **Names exactly as written:** Zoë, Ångström-Okonkwo, O'Brien, Ana Lucía and Gómez are printed exactly as in the CSV. 花子 山田 draws through the Noto Sans JP fallback. `pdftotext` on the PDF returns these strings exactly.

## Checks

- **Template:** `vixl_check` passes, with 0 fix and 0 review findings after the two waivers described below.
- **merge-impose:** 10 of 10 rows valid, with no overflow, missing-glyph or missing-column errors. Row 5 reports "uses fallback glyphs", which is expected: the Japanese text is drawn by the Noto Sans JP fallback, not by Inter.
- **Outputs:** I checked that all 10 PNGs are 1200 × 900 and viewed a contact sheet of them. The PDF has 2 Letter pages (612 × 792 pt), and I rendered and viewed it.

## Deviations and choices

- **The 10 badges fill two pages.** Page 1 holds badges 1–6. Page 2 holds badges 7–10 in the top two rows of the same centred grid, so the cut lines line up with page 1, and its bottom row is empty.
- **No gutter between badges.** Neighbouring badges share cut lines (gutter 0); with a 0.25 in side margin, two 4 in columns take the full 8.5 in width. The crop marks sit in the margins. Badges have no bleed, so the role bar's colour stops at the trim line; a slightly off cut could leave a hairline of white or of the neighbouring badge.
- **I typed the per-badge PNG values into the export call by hand.** Merge-impose reads the CSV directly, but the single-badge PNGs were exported with variables I copied from the CSV into the call. I compared them against the file on the contact sheet.
- **Fonts:** Inter Tight / Inter came from the font cache and Noto Sans JP was downloaded from Google Fonts. All three are embedded in `badge.vixl`, which is why it is about 3.6 MB.

## Unsure / known issues

- **Contrast waivers on two layers.** Inside the stack group, Vixl's contrast check reports 1.00:1 for the `first` and `last` text layers. I believe this is a false positive in the checker: the same check passes when the stack is removed (I ran a dry run), and the text is navy or slate on white, over 10:1. I waived `contrast` on those two layers with that reason recorded in the document. Merge-impose's `check: "design"` does not apply layer waivers, so its report still lists these as warnings for every row. The PNGs show the text clearly legible.
- **Role-bar text extraction.** In the PDF, the role names are set with letter-spacing (tracking 10 px), so `pdftotext` extracts them as spaced letters (e.g. "AT T E N D E E"). The drawn text is correct.
- **Bar marked as an intentional crop.** The bar runs to the canvas edges, so I marked it `allow_crop`. The role text was moved up 8 px to sit inside the 45 px safe area.
