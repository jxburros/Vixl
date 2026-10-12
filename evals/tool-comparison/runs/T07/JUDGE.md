# T07 · Name badges: judge notes

Runs: claude-V, claude-W, claude-C (round 1 + round2/).

- **V** was re-run on Vixl 0.26.0 and judged on 2026-10-12 by a claude-opus-5-5 subagent.
  Effort: round 1 took 3.4 min and 34 tool calls; round 2 took 1.5 min and 25 tool calls.
- **W** and **C** were run and judged on 2026-10-05. Their scores and notes below are unchanged.
  Only their sources are committed, so for the 2026-10-12 blind look their deliverables were
  regenerated from `build.py` and `make_badges.py` in a scratch copy outside the repo. Both
  regenerated cleanly in both rounds. W needed Playwright's Chromium installed first.

## 1. Blind scores (written before opening key.csv)

**2026-10-12** (V on Vixl 0.26.0, alongside regenerated W and C):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| J5JY | 5 | 4 | Every name exact, CJK included. Centred Inter Tight ExtraBold names with Inter for the company, on white, with a grey hairline under a centred event header. Tracked caps on the bars. Bartholomew's row shrinks to fit. Sam's badge re-centres with no gap. Clean 2×3 sheet with hairline crop marks, and page 2 keeps the grid. Strong and consistent, but the line spacing is fixed per slot, so it is uneven: on Zoë's badge the descender of Ångström sits 16 px above the company, against 43–57 px on the other badges. |
| 15TT | 5 | 5 | (regenerated W) Every name exact. Left-aligned grotesque on cream, hairline rule in the role colour, tracked caps on the bar, Sam re-centred. |
| WZ25 | 5 | 3 | (regenerated C) Every name exact. Centred DejaVu Bold, first and last name nearly touch, looks generic. |

Key: J5JY = **V** (round 2: 8RIY), 15TT = W (round 2: J2DY), WZ25 = C (round 2: Z2HV).

**2026-10-06** (V on Vixl 0.20.0):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| O50J | 5 | 4 | (V on 0.20.0) Every name exact, CJK included. Left-aligned Montserrat/Open Sans on a cream ground, a short rule in the role colour above the event name. Sam's badge leaves the company line out but does not re-centre. Polished but fairly standard. |
| GEUB | 5 | 4 | (regenerated W) Every name exact. Refined grotesque with letter-spaced role text and a hairline rule in the role colour. |
| ULE7 | 5 | 3 | (regenerated C) Every name exact. Centred DejaVu Bold, looks generic. |

**2026-10-05** (the scores of record for W and C):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 34JO | 5 | 5 | Every name exact, CJK included. Clean grotesque type, tracked caps on the bar, a hairline rule in the role colour, Sam's block re-centred, tidy 2×3 sheet with crop marks. |
| EOFH | 5 | 4 | Every name exact. Montserrat/Open Sans looks good, but the gaps between first and last name are loose and uneven. Sam's badge is top-aligned with an empty area where the company would go. Page 2 of the PDF is centred vertically. |
| YVP2 | 5 | 3 | Every name exact. Looks generic (DejaVu bold, centred, plain white). First and last name nearly touch (cramped leading). |

Key: 34JO = **W**, EOFH = **V on 0.18.0**, YVP2 = **C**.

The 2026-10-12 look agrees with the record for W (5/5) and C (5/3). The 2026-10-06 look had given W craft 4; its recorded 5 stands.

## 2. Hard checks (round 1)

Evidence for V (2026-10-12):
- `inspect_outputs.py`.
- The PDF's vector rectangles read with pdfplumber.
- The PDF rendered at 50 and 300 dpi, and every cell compared with its PNG.
- The bar and bar-text colours sampled on every PNG, with WCAG ratios computed.
- Ink extents and line runs measured on every PNG.
- `pdftotext` and `pdffonts` compared with the CSV.
- The template's `project.json`, and `vixl check` plus a merge-impose dry run on a scratch copy.

W and C results are from 2026-10-05.

| Check | V (0.26.0) | W | C |
| --- | --- | --- | --- |
| 10 PNGs, 1200×900, file order | pass (RGB, 300 dpi tag) | pass | pass |
| Names exact (O'Brien, Zoë Ångström-Okonkwo, 花子 山田 with no tofu, Ana Lucía Gómez) | pass. Every name, company and role is in the PDF text. The role names come out letter-spaced (`AT T E N D E E`) because of the tracking, as the report says. CJK uses the Noto Sans JP Bold fallback (embedded as `NotoSansJP-Bold`). The PNGs were exported with hand-typed variables; every PNG matches its PDF cell (mean difference 2.3–6.0 of 765), so there are no typos. | pass (WenQuanYi fallback) | pass (IPAGothic fallback, regular weight) |
| Row 4 fits with no clipping or overlap | pass. The first name, last name and 48-character company all shrank (`text_layout fit`). Ink spans x 66–1138 inside the 60–1140 boxes, and the three lines are separate runs (y 241–366, 465–537, 594–637). | pass | pass |
| Row 6: no empty gap or placeholder | **pass**. `hide_if_empty` removes the company layer, and the `stack` group (vertical, justify centre) re-centres the two remaining lines. The ink block runs y 281–578 (centre 430) against a centre of 436–442 on the other badges, with 101 px above and 142 px below. 0.18.0 and 0.20.0 failed this. | pass (re-centred) | pass (re-centred) |
| Row 7 `VOLUNTEER` on the sea-foam bar | pass (`#a8d5c8`, the map's `*` fallback; `text_transform: uppercase`) | pass | pass |
| Bar colours by role; readable text on the navy bar | pass. Exact hex values. Contrast: white on navy 15.33:1, navy on amber 7.47, on sea-foam 9.50, on coral 4.96. | pass | pass |
| PDF: 2 Letter pages, 2×3, exactly 4×3 in, crop marks | pass. Cells are 288×216 pt at x 18/306 and y 72/288/504, so the grid is centred (0.25 in sides, 1 in top and bottom). Crop marks are 0.24 pt hairlines in the margins at every cut line. Page 2 keeps the grid positions. The PDF is vector, with 3 subset fonts embedded (Inter Tight ExtraBold, Inter Regular, Noto Sans JP Bold). | pass (vector, fonts embedded) | pass |
| **Total** | **7/7** | **7/7** | **7/7** |

**Lane rule.** On 0.26.0 the design logic is inside Vixl.
- The role→colour and role→ink lookups are document maps (`variable-map` `barcolor` and `barink`, with a `*` fallback) used through `${role|map:barcolor}`.
- The capitals are `text_transform: uppercase`. The 0.20.0 `prepare_data.py` is gone.
- The one gap: MCP has no CSV-driven per-row PNG export. `render --data` exists in the CLI and Python only. So round 1 typed each row's values into `vixl_export_batch`, and round 2 used a small script that printed the CSV as JSON. Reading inputs is within the rule.

## 3. Report honesty

- **V (0.26.0): yes.** Every checkable claim matches:
  - the canvas, type sizes and fonts (Inter Tight 800 / Inter 400, Noto Sans JP 700 as the fallback);
  - the 1080 × 500 stack, `hide_if_empty`, the 180 px bar and the maps;
  - the contrast figures, the grid, the embedded fonts and the 3.6 MB template;
  - the two contrast waivers and the `allow_crop` on the bar;
  - `vixl check` passing with 0 fix and 0 review findings (4 informational);
  - the letter-spaced `pdftotext` output.

  The report discloses the hand-typed PNG variables, the zero gutter and the lack of bleed. The 1.00:1 contrast false positive is real (see Findings).

  One small mechanism error. The report says merge-impose's design check "does not apply layer waivers". It does apply them: otherwise the 1.00:1 findings would be errors and every row invalid. What happens is that it lists the waived findings among its warnings without marking them as waived. The visible effect the report describes is correct.

  Round 2's claims also hold:
  - the template differs from round 1 only by one revision with the two `variable-map` merges;
  - the Sponsor bars sample at (107, 63, 105);
  - badge 11 is amber;
  - the sheet links resolve to `round2/badge.vixl`.
- **W: yes.** Geometry, fonts, CJK fallback and page-2 layout all match (2026-10-05).
- **C: yes.** Sizes, fallback font, crop-mark placement and contrast figures all match (2026-10-05).

## 4. Revision (round 2)

Answer key: 11 PNGs; 05 and 09 plum; PDF still 2 pages, with 5 badges on page 2.

| | V (0.26.0) | W | C |
| --- | --- | --- | --- |
| 11 PNGs, 1200×900 | yes | yes | yes |
| 05 and 09 bars = `6b3f69` (sampled) | yes, with white text (8.27:1) | yes, white text; the header rule is plum too | yes, white text |
| PDF: 2 pages, page 2 with 5 badges | yes (vector, same grid; 5 cells and 5 bars on page 2) | yes | yes |
| Drift on 01–04, 06–08, 10 | 0 px (exact pixel diff). On 05 and 09 only the bar region (y 720–900) changed. | 0 px | 0 px |
| Effort and method | One `vixl_operations_apply` with two `variable-map` merges (`barcolor.Sponsor`, `barink.Sponsor`). Then a CSV copy with Iris appended, one `export_batch` and one `merge-impose` with the same sheet settings. Nothing in the layout was touched. | 9 calls: 3 edits to `build.py` and a rerun | 8 calls: a `sed` edit to the colour, a CSV copy and a rerun |
| Editability | **5** | **5** | **5** |
| Revision | **5** | **5** | **5** |

**White Sponsor text.** This change wasn't requested, but V disclosed it.
- Navy on plum is 1.85:1, which would break the brief's rule that bar text must contrast with the bar. White on plum is 8.27:1.
- So the change follows from the brief, and all three lanes made it. It is not counted as collateral.

## Findings

- All three lanes printed every name exactly, CJK included, with no tofu.
- On 0.26.0 Vixl passes every hard check. The template now carries the whole design:
  - the role maps;
  - the upper-casing;
  - a `stack` that re-centres when the company is empty;
  - `fit` boxes for the long row.

  `merge-impose` turns the CSV into a vector PDF and a live sheet. Round 2 was a two-entry map edit plus reruns.
- **Vixl bug (reproduced): the contrast check reports 1.00:1 for text inside a `stack` group.**
  - The setup: `vixl check --checks contrast --no-waivers` on a scratch copy of `badge.vixl`. It reports `first` and `last` as `text-contrast` errors at 1.00:1. The real figures are #14263b / #34475b on white, 15.3:1 and above.
  - The cause is in `measure.measure(target=…)` (`src/vixl/measure.py`). To build the backdrop it hides the siblings stacked above the target and keeps them hidden for the foreground render. The `stack` then reflows around the hidden members, so the target moves: `first` goes from local y 41 to y 145 when `last` and `company` are hidden. The foreground render no longer has glyphs where the coverage mask (taken from the full layout) says they are.
  - Shown and backdrop are identical there, so the result is 1.00:1. `company` is the last member and passes. With the `stack` removed, the same measurement gives 15.33:1.
  - `merge-impose --check design` repeats the finding for every row. With the layer waivers it lists the findings as plain warnings (20 per run) without marking them as waived.
- **Vixl gap: MCP has no CSV-driven per-row raster export.** `render --data rows.csv` exists in the CLI and Python only (`docs/design-tools.md`). An MCP-only agent has to put each row's variables into `vixl_export_batch` by hand or with a script, while `merge-impose` reads the same CSV directly.
- **Vixl craft limit:** stack members are fixed-height slots, so the visible gap between lines depends on each name's ascenders and descenders. On Zoë's badge the gap is 16 px against 43–57 px on the others. The code lanes size each line from its own metrics.
- The 0.20.0 `font-fallbacks` finding no longer applies. Since 0.21.0 `target` is rejected, and this run registered a single document-wide Noto Sans JP 700, so the CJK names are bold.

## Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 6/7 (row 6) | 6/7 (row 6, borderline) | **7/7** |
| Fidelity / craft | 5 / 4 | 5 / 4 | 5 / 4 |
| Report honest | yes | yes | yes (one minor mechanism error) |
| Editability / revision | 3 / 5 | 5 / 5 | 5 / 5 |
| Effort (r1 / r2) | not recorded; about 50 calls in r2 | not recorded | 3.4 min, 34 calls / 1.5 min, 25 calls |
| Print PDF | Raster: a static collage of exported PNGs, with crop marks drawn by hand as 3 px rectangles | Vector, 4 subset fonts, `merge-impose`, generated crop marks | Vector, 3 subset fonts, `merge-impose`, generated hairline crop marks |
| Round 2 | Images re-imported and swapped; page-2 layers and marks moved by hand | A data edit in `prepare_data.py` plus a rerun of the merge and the batch export | Two `variable-map` entries in the template plus a rerun; 0 px drift |
| Empty company | An empty string; the blank slot stays | `hide_if_empty`, but no re-centring | `hide_if_empty` inside a `stack`, so the block re-centres |
| CJK weight | Regular | Medium (`font-fallbacks` ignored `target`) | Bold (one document-wide fallback) |
| Outside Vixl | Nothing | `prepare_data.py` derives the role colour, ink and label (bends the lane rule) | Nothing in the design. Per-row PNG variables were typed in by hand (r1) or printed by a script (r2), because MCP has no CSV-driven raster export. |
| New Vixl issue | | | The contrast check reports 1.00:1 for text inside a `stack`, so the agent waived 2 layers |

**What changed.**
- V now passes all seven hard checks. Its template uses three features it skipped on 0.20.0: the `stack` that re-centres Sam's badge, the `map:` merge filter, and `text_transform`. So no data-preparation script is needed, and round 2 became a two-entry map edit with zero drift.
- Craft holds at 4. The centred Inter Tight design is cleaner than before, but the fixed-height stack slots make the line spacing uneven.
- The new cost is a false positive in the contrast check for stacked text. The agent had to waive it, and merge-impose reports it on every row.
