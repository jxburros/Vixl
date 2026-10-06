# T07 · Name badges: judge notes

Runs: claude-V, claude-W, claude-C (round 1 + round2/).

- **V** was re-run on Vixl 0.20.0 and judged on 2026-10-06 by a claude-opus-5-5 subagent.
- **W** and **C** were run and judged on 2026-10-05. Their scores and notes below are unchanged.
  Only their sources are committed, so for the 2026-10-06 blind look their deliverables were
  regenerated from `build.py` and `make_badges.py` in a scratch copy outside the repo. Both
  regenerated cleanly in both rounds.

## 1. Blind scores (written before opening key.csv)

**2026-10-06** (V on Vixl 0.20.0, alongside regenerated W and C):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| O50J | 5 | 4 | Every name exact, CJK included. Left-aligned Montserrat/Open Sans on a cream ground, a short rule in the role colour above the event name. Bartholomew's long row fits. Sam's badge leaves the company line out. Clean 2×3 sheet with crop marks; page 2 keeps the grid positions. Polished but fairly standard. |
| GEUB | 5 | 4 | (regenerated W) Every name exact. Refined grotesque with letter-spaced role text and a hairline rule in the role colour. |
| ULE7 | 5 | 3 | (regenerated C) Every name exact. Centred DejaVu Bold, first and last name nearly touch, looks generic. |

Key: O50J = **V** (round 2: 6Y52), GEUB = W (round 2: U5RK), ULE7 = C (round 2: EJXP).

**2026-10-05** (the scores of record for W and C):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 34JO | 5 | 5 | Every name exact, CJK included. Clean grotesque type, tracked caps on the bar, a hairline rule in the role colour, Sam's block re-centred, tidy 2×3 sheet with crop marks. |
| EOFH | 5 | 4 | Every name exact. Montserrat/Open Sans looks good, but the gaps between first and last name are loose and uneven. Sam's badge is top-aligned with an empty area where the company would go. Page 2 of the PDF is centred vertically. |
| YVP2 | 5 | 3 | Every name exact. Looks generic (DejaVu bold, centred, plain white). First and last name nearly touch (cramped leading). |

Key: 34JO = **W**, EOFH = **V on 0.18.0**, YVP2 = **C**.

The 2026-10-06 look gave W craft 4 rather than 5. W's recorded score stays at 5, as instructed.

## 2. Hard checks (round 1)

Evidence for V (2026-10-06):
- `inspect_outputs.py`.
- The PDF's vector rectangles read with pdfplumber.
- The PDF rendered at 100 and 300 dpi.
- The bar and text colours sampled on every PNG.
- Ink extents measured on every PNG.
- `pdftotext` compared with the CSV.
- The template's `project.json`.

W and C results are from 2026-10-05.

| Check | V (0.20.0) | W | C |
| --- | --- | --- | --- |
| 10 PNGs, 1200×900, file order | pass (300 dpi tag) | pass | pass |
| Names exact (O'Brien, Zoë Ångström-Okonkwo, 花子 山田 with no tofu, Ana Lucía Gómez) | pass. Every name, company and role is in the PDF text. The name and company cells in `badges-data.csv` are identical to the fixture. CJK uses the Noto Sans JP Medium fallback. | pass (WenQuanYi fallback) | pass (IPAGothic fallback, regular weight) |
| Row 4 fits with no clipping or overlap | pass. The ink spans x 83–1112 inside the 80–1120 box. | pass | pass |
| Row 6: no empty gap or placeholder | **fail (borderline)**. No placeholder, and `hide_if_empty` removes the company layer. But the block is top-aligned and does not re-centre, so there are 199 px of empty space above the bar instead of about 94 px. The 0.18.0 run was failed for the same look. Vixl 0.20.0's `stack` operation reflows and re-centres; the agent didn't use it. | pass (re-centred) | pass (re-centred) |
| Row 7 `VOLUNTEER` on the sea-foam bar | pass (`#a8d5c8`) | pass | pass |
| Bar colours by role; readable text on the navy bar | pass. Exact hex values. Contrast: white on navy 15.33:1, navy on amber 7.47, on sea-foam 9.50, on coral 4.96. | pass | pass |
| PDF: 2 Letter pages, 2×3, exactly 4×3 in, crop marks | pass. Cells are 288×216 pt at x 18/306 and y 72/288/504, so the grid is centred (0.25 in sides, 1 in top and bottom). Hairline crop marks sit in the margins at every cut line. Page 2 keeps the grid positions. The PDF is vector, with 4 subset fonts embedded. | pass (vector, fonts embedded) | pass |
| **Total** | **6/7** | **7/7** | **7/7** |

V's PDF and PNGs match: cell 1 rendered at 300 dpi differs from `badge-01.png` by a mean of 1.8/765, which is antialiasing only.

**Lane rule.** V used `prepare_data.py` to add `role_label`, `bar_color` and `bar_ink` columns before the Vixl merge.
- That is more than reading inputs. The role→colour map, the text colour per bar and the upper-casing are design decisions, and they live in Python.
- It is not drawing, and the report discloses it.
- It is forced by a real gap: Vixl's merge substitutes `${name}` only, with no lookup or case transform.
- Verdict: it bends the rule but doesn't break it, so the run was not zeroed.

## 3. Report honesty

- **V (0.20.0): yes.** Every checkable claim matches:
  - type sizes, the 1040 px fit boxes and 80 px margins, the 180 px bar;
  - the contrast figures, the grid offsets, the 4 embedded subset fonts;
  - the template size (6.9 MB) with an unused Noto Sans JP 700;
  - both CJK names in Medium, the crop marks in the margins only, the PDF text matching the CSV.

  It discloses the data script, the single fallback weight and the leftover thumbnail warning.
  Round 2's claims also hold:
  - the template is byte-identical to round 1;
  - the Sponsor bars sample at (107, 63, 105);
  - the nine other badges have 0 px of drift;
  - the sheet's links point at the round-2 template.
- **W: yes.** Geometry, fonts, CJK fallback and page-2 layout all match (2026-10-05).
- **C: yes.** Sizes, fallback font, crop-mark placement and contrast figures all match (2026-10-05).

## 4. Revision (round 2)

Answer key: 11 PNGs; 05 and 09 plum; PDF still 2 pages, with 5 badges on page 2.

| | V (0.20.0) | W | C |
| --- | --- | --- | --- |
| 11 PNGs, 1200×900 | yes | yes | yes |
| 05 and 09 bars = `6b3f69` (sampled) | yes. The text is white and the rule above the event name is plum. | yes, white text; the header rule is plum too | yes, white text |
| PDF: 2 pages, page 2 with 5 badges | yes (vector, same grid) | yes | yes |
| Drift on 01–04, 06–08, 10 | 0 px (exact pixel diff) | 0 px | 0 px |
| Effort and method | The template was not touched. The agent edited 2 lines of `prepare_data.py` (Sponsor colour and ink) and appended Iris as a row. Then it ran `merge-impose` again (with the same sheet settings) and one `export_batch`. The colour map lives in the script, not in Vixl. | 9 calls: 3 edits to `build.py` and a rerun | 8 calls: a `sed` edit to the colour, a CSV copy and a rerun |
| Editability | **5** | **5** | **5** |
| Revision | **5** | **5** | **5** |

**White Sponsor text.** This change wasn't requested, but V disclosed it.
- Navy on plum is 1.85:1, which would break the brief's rule that bar text must contrast with the bar. White on plum is 8.27:1.
- So the change follows from the brief, and all three lanes made it. It is not counted as collateral.

## Findings

- All three lanes printed every name exactly, CJK included, with no tofu.
- On 0.20.0, Vixl does the whole data-to-print path as the code lanes do. `merge-impose` reads the CSV and writes a vector PDF with embedded fonts plus a live sheet document. Round 2 was a data change and a rerun.
- Vixl gap: the merge has no value lookup or text transform. Role→colour and upper-case still need a script outside Vixl.
- Vixl bug: `font-fallbacks` ignores its `target` and replaces one document-wide list (`src/vixl/authoring.py`, the `font-fallbacks` branch of `execute`).
  - The agent set Noto Sans JP 700 for `first-name` and 500 for `last-name` and `company`.
  - The state kept only the 500 font, so 花子 renders in Medium.
  - The unused 5.7 MB 700 font stays embedded, which is most of the template's 6.9 MB.
  - All three operations were accepted with their `target`, which the code never reads.
- Vixl fit boxes keep fixed positions. Without a `stack`, an empty field leaves extra space and the block does not re-centre. The code lanes reflowed and re-centred.

## Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 6/7 (row 6) | 6/7 (row 6, borderline) |
| Fidelity / craft | 5 / 4 | 5 / 4 |
| Report honest | yes | yes |
| Editability / revision | 3 / 5 | **5** / 5 |
| Print PDF | Raster: a static collage of exported PNGs, with crop marks drawn by hand as 3 px rectangles | Vector text with 4 subset fonts embedded, made by `merge-impose`, with crop marks generated |
| Round 2 | About 50 calls: images re-imported and swapped, page-2 layers and marks moved and duplicated by hand | A data edit plus a rerun of the merge and the batch export. The template is unchanged and there is 0 px of drift. |
| Empty company | An empty string; the blank slot stays | `hide_if_empty` removes the layer, but the block still doesn't re-centre |
| CJK weight | Regular, not bold | Medium (the fallback is document-wide, see the bug above) |
| Outside Vixl | Nothing | `prepare_data.py` derives the role colour and label (bends the lane rule) |

The big change is round 2: V now matches W and C on editability, because the print sheet is generated from the data instead of assembled by hand. Craft and the row-6 result are unchanged.
