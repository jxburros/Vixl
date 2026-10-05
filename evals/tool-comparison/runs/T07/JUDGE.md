# T07 · Name badges: judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Runs: claude-V, claude-W, claude-C (round 1 + round2/).

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 34JO | 5 | 5 | Every name exact, CJK included. Clean grotesque type, tracked caps on the bar, a hairline rule in the role colour, Sam's block re-centred, tidy 2×3 sheet with crop marks. |
| EOFH | 5 | 4 | Every name exact. Montserrat/Open Sans looks good, but the gaps between first and last name are loose and uneven. Sam's badge is top-aligned with an empty area where the company would go. Page 2 of the PDF is centred vertically. |
| YVP2 | 5 | 3 | Every name exact. Looks generic (DejaVu bold, centred, plain white). First and last name nearly touch (cramped leading). |

Key: 34JO = **W**, EOFH = **V**, YVP2 = **C** (round 2: FP2W = V, WGWI = W, UCD4 = C).

## 2. Hard checks (round 1)

Evidence: `inspect_outputs.py`, the PDF rendered at 100 dpi (bounding boxes of the colour bars), the bar pixel sampled at (20,860) on every PNG, and a visual check of every badge.

| Check | V | W | C |
| --- | --- | --- | --- |
| 10 PNGs, 1200×900, file order | pass | pass | pass |
| Names exact (O'Brien, Zoë Ångström-Okonkwo, 花子 山田 with no tofu, Ana Lucía Gómez) | pass (Noto Sans JP fallback, regular weight) | pass (WenQuanYi fallback) | pass (IPAGothic fallback, regular weight) |
| Row 4 fits with no clipping or overlap | pass | pass | pass |
| Row 6: no empty gap or placeholder | **fail**: no `None` printed, but the company slot is left as blank space and the block does not reflow (REPORT admits "blank space where that line would be") | pass (re-centred) | pass (re-centred) |
| Row 7 `VOLUNTEER` on the sea-foam bar | pass | pass | pass |
| Bar colours by role; readable text on the navy bar | pass (exact hex; white on navy) | pass | pass |
| PDF: 2 Letter pages, 2×3, exactly 4×3 in, crop marks | pass (grid 800×900 px at 100 dpi = 8×9 in; page 2 is a centred 2×2) | pass (vector, fonts embedded) | pass |
| **Total** | **6/7** | **7/7** | **7/7** |

All three PDFs: bars span x = 25–825 px at 100 dpi (8.00 in) and are spaced 300 px (3.00 in) apart, with the grid centred horizontally. V and C embed 300 dpi raster badges (no live text). W is vector text with InstrumentSans and WenQuanYi subset-embedded.

## 3. Report honesty

- **V: yes.** It discloses the raster PDF, the non-bold CJK and the blank space on Sam's badge. Small slip: 3 px marks at 300 dpi are 0.72 pt, not 0.24 pt.
- **W: yes.** Geometry, fonts, CJK fallback and page-2 layout all match.
- **C: yes.** Sizes, fallback font, crop-mark placement and contrast figures all match.

## 4. Revision (round 2)

Answer key: 11 PNGs; 05 and 09 plum; PDF still 2 pages, with 5 badges on page 2.

| | V | W | C |
| --- | --- | --- | --- |
| 11 PNGs, 1200×900 | yes | yes | yes |
| 05 and 09 bars = `6b3f69` (sampled) | yes, with text switched to white | yes, white text; the header rule is plum too | yes, white text |
| PDF: 2 pages, page 2 with 5 badges | yes | yes | yes |
| Drift on 01–04, 06–08, 10 (pixel diff, threshold 30) | 0 px | 0 px | 0 px |
| Effort and method | ~50 tool calls. Badges were simple re-exports with variables. Every image in the imposition doc had to be re-imported and swapped, and page 2's layers and crop marks were moved and duplicated by hand. The role-to-colour map lives only in the agent's calls, not in the template. | 9 calls: 3 edits to `build.py` and a rerun | 8 calls: a `sed` edit to the colour, a CSV copy and a rerun |
| Editability | **3** | **5** | **5** |
| Revision | **5** | **5** | **5** |

## Findings
- All three lanes got every name exactly right, CJK included. None produced tofu.
- Vixl-specific gap: there is no data-merge or imposition link between `badge.vixl` and `badges-print.vixl`. The print sheet is a static collage of exported PNGs, so any data change means rebuilding it by hand. The code lanes regenerate the sheet in one rerun.
- Vixl's fit boxes keep fixed positions, so an empty field leaves a hole and short names get big gaps. The code lanes reflowed and re-centred.
