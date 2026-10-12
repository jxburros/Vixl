# T07 round 2 · Name badges: Vixl lane (claude-V)

## What changed

1. **Badge 11 added:** Iris · Van der Berg · Speaker · Lowtide Labs. It is an amber Speaker badge, like badges 1, 3 and 10.
2. **Sponsor colour is now plum `#6b3f69`** (it was coral `#e2725b`).
3. **Bar text on Sponsor badges is now white.** I had to change this. The old navy `#14263b` text measures only 1.85:1 on plum, which fails WCAG. White on plum measures 8.27:1 (AAA). Speaker, Attendee, Volunteer and Staff badges are unchanged.
4. **Everything was regenerated:** 11 PNGs and the 2-page print PDF. Page 2 now holds badges 7–11, and its bottom-right cell is empty.

## Files in round2/

| File | What it is | How it was made |
| --- | --- | --- |
| `badges.csv` | Copy of the fixture with the Iris row added | Copied the fixture and appended one line with the shell. The fixture itself is not modified |
| `badge.vixl` | The template with the colour change | Copied from round 1 and opened with `vixl_document_open`. One `vixl_operations_apply` batch with `check=true` made two `variable-map` edits with `merge: true`: `barcolor.Sponsor = #6b3f69` and `barink.Sponsor = #ffffff`. Nothing else in the design was touched |
| `badges/badge-01.png` … `badge-11.png` | One per CSV row, 1200 × 900 RGB | One `vixl_export_batch` call. This time the targets' `variables` came from a small script that read `round2/badges.csv` and printed JSON, which I passed through unchanged. In round 1 I typed these values by hand |
| `badges-print.pdf` | US Letter portrait, 2 pages, 2 × 3 grid at actual size, crop marks, vector text | `vixl_workflow("merge-impose")` with the same sheet spec as round 1 (`letter`, `portrait`, `cols: 2`, `rows: 3`, `check: "design"`), using the round2 template and CSV |
| `badges-sheet.vixl` | Editable imposition sheet, with its link layers pointing at `round2/badge.vixl` | Written by the same merge-impose call |

## Checks

- **Template:** `vixl_check` passed with 0 fix and 0 review findings. The two stack-group contrast waivers from round 1 still apply.
- **Previews:** I looked at a Sponsor badge (Ana Lucía Gómez) and at Iris before exporting.
- **merge-impose:** 11 of 11 rows valid, with no overflow, missing-glyph or missing-column errors. Its warnings are the same known false positives as in round 1: "1.00:1 contrast" on the stacked name lines, plus the expected fallback glyphs for row 5.
- **PNGs:** all 11 are 1200 × 900. The bar pixel is plum `(107, 63, 105)` on badges 5 and 9, and amber on badge 11.
- **PDF:** 2 Letter pages (612 × 792 pt). Fonts are Inter Tight, Inter and Noto Sans JP, all embedded. `pdftotext` finds "Iris", "Van der Berg" and "Lowtide Labs". I rendered and viewed both pages.

## Notes

- The edit took four Vixl calls (open, map edit, batch export, merge-impose), plus checks and previews. The layout itself was not touched.
- I changed nothing outside `round2/`.
