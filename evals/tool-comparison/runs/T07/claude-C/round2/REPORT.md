# T07 Batch badges, Lane C, round 2

## Changes requested
1. Add an 11th badge: Iris, Van der Berg, Speaker, Lowtide Labs.
2. Change the Sponsor colour from coral `#e2725b` to plum `#6b3f69`.
3. Regenerate every badge and the print PDF.

## How it was done
Everything is inside `round2/`. Nothing outside `round2/` was changed, including the round-1 files and the fixture CSV.

- `round2/badges.csv` is a copy of `evals/tool-comparison/fixtures/badges.csv` (the fixture file ends with a newline). One row was appended at the end: `Iris,Van der Berg,Speaker,Lowtide Labs`. That makes 11 data rows.
- `round2/make_badges.py` is a copy of the round-1 script with two edits made by `sed`:
  - `ROLE_COLORS["sponsor"]` is now `"#6b3f69"`.
  - The default CSV path is now `badges.csv` next to the script, not `../../../fixtures/badges.csv`. A CSV path can still be passed as the first argument.
  - The design, layout and PDF code are unchanged.
- I ran `python3 make_badges.py` in `round2/`. It uses Pillow, fontTools and reportlab, as in round 1.

## Deliverables (round2/)
| File | Notes |
| --- | --- |
| `badges/badge-01.png` … `badges/badge-11.png` | Pillow, 1200 × 900 px RGB, 300 dpi metadata, one per CSV row in file order. Badges 01–10 are the same people as round 1; 11 is Iris Van der Berg (Speaker, amber bar). |
| `badges-print.pdf` | reportlab, 2 US Letter portrait pages (612 × 792 pt), 2 × 3 grid at actual size (288 × 216 pt each), centred, crop marks outside the grid as in round 1. Page 1 holds badges 1–6. Page 2 holds badges 7–11; only the bottom-right slot is empty. |
| `make_badges.py`, `badges.csv` | The editable source and its input data. |
| `REPORT.md` | This file. |

## Effect of the colour change
- The bar text rule is unchanged: the script picks navy `#14263b` or white, whichever contrasts more with the bar. On plum, white contrasts more, so the Sponsor badges (05 花子 山田 and 09 Ana Lucía Gómez) now have white "SPONSOR" text. The ratio is 8.27:1 (round 1, navy on coral, was 4.96:1).
- Other bar contrasts are unchanged: Speaker 7.47:1, Attendee and Volunteer 9.50:1, Staff 15.33:1.
- "Van der Berg" fits at its nominal size (104 px), so it was not shrunk.

## Checks
- A script confirmed there are 11 PNGs, all 1200 × 900, and that the PDF has 2 pages with a 612 × 792 mediabox.
- I looked over a contact sheet of all 11 PNGs by eye: plum bars with white text on badges 05 and 09, and badge 11 laid out like the rest. I did not render the PDF pages for this round. The PDF layout code is the same as in round 1, where page 1 was checked.

## Unsure about
- Same as round 1: whether regular-weight CJK beside bold Latin is acceptable, and whether crop marks are wanted inside the grid.

## Tool calls
8 in total, counting this report and the final hand-off. One Bash call failed partway (`xxd` is not installed) and was re-run. One image Read showed an unrelated old contact sheet left in the scratchpad, so I ignored it.
