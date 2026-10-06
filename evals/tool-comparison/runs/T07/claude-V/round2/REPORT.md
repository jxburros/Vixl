# T07 round 2 · Name badges — lane V (Vixl)

## What I changed

1. **New 11th badge: Iris Van der Berg, Speaker, Lowtide Labs.** It is the last row of `badges-data.csv` and is exported as `badges/badge-11.png`. On the print PDF it sits on page 2, row 3, left column, after Kwame (badge 10).
2. **Sponsor colour is now plum `#6b3f69`.** It replaces coral `#e2725b` on badges 5 (花子 山田) and 9 (Ana Lucía Gómez), in both the bottom bar and the short rule above the event name.
   - **The Sponsor bar text is now white.** On coral it was navy, but navy on plum is too dark to read. White on plum is 8.27:1 (WCAG AAA), according to `vixl_color contrast`.
3. **Everything was regenerated from the round-1 template.** That covers all 11 PNGs, `badges-print.pdf` and `badges-sheet.vixl`. The other nine badges look the same as in round 1.

## How

- **`badge-template.vixl` was not edited.** It is a byte-identical copy of round 1. Bar colour and bar text colour were already template variables (`${bar_color}` and `${bar_ink}`), so neither change needed a design edit.
- **`prepare_data.py` (the round-1 data script, copied and edited):**
  - It now maps Sponsor to `("#6b3f69", "#ffffff")`.
  - It appends Iris as an `EXTRA` row after the fixture rows.
  - The fixture at `evals/tool-comparison/fixtures/badges.csv` was left untouched, because it is outside round2/.
  - Command: `python3 prepare_data.py ../../../../fixtures/badges.csv badges-data.csv`.
- **Print PDF:** `vixl_workflow merge-impose` with the round2 template and CSV. The sheet settings match round 1: letter, portrait, 2 × 3, centred, crop marks, `check: design`, `unknown: ignore`. All 11 rows were valid, with no overflow, on 2 pages. The new `badges-sheet.vixl` links point to the round2 template and data.
- **PNGs:** one `vixl_export_batch` call on the template, with one target per CSV row and that row's `variables`. This produced 11 files, each 1200 × 900.

## Checks (Python/Poppler, reading only)

- **PDF (`pdfinfo` / `pdffonts`):** letter size, 2 pages, 4 embedded subset fonts.
- **Text (`pdftotext`):** includes "Iris", "Van der Berg" and "Lowtide Labs".
- **Bar colour:** the pixel sampled in the Sponsor bar of badge-05 and badge-09 is (107, 63, 105), which is `#6b3f69`.
- **Visual check:** I viewed a contact sheet of all 11 PNGs and a render of PDF page 2. The new badge matches the others, and its name fits without shrinking.

## Notes and leftover warnings

- **Same as round 1:**
  - The merge again warns that row 5 uses fallback glyphs for its first and last name. Noto Sans JP is the intended fallback for 花子 and 山田.
  - Both of those names still render in Noto Sans JP Medium.
- **"Van der Berg":** the surname prints exactly as given, with lower-case "der" and no sorting changes.
- **Page 2 layout:** it now holds 5 badges (7–11), leaving one empty cell.
