# T08 · Infographic from data: judge notes

Judges: claude-opus-5-5 subagents. Lanes run: V (Vixl), C (matplotlib), W (hand SVG + Playwright), all claude.

- **V** was re-run on **Vixl 0.26.0** and judged on **2026-10-12**. Blind codes: round 1 OTWV, round 2 XMBF. Effort: round 1 1.8 min / 21 tool calls, round 2 1.5 min / 18 tool calls, no nudges.
- **C** and **W** were run and judged on **2026-10-05**; their scores and notes below are unchanged. 2026-10-12 blind codes: C=3YBW (r2 IFMO), W=QUXE (r2 NB8E).

Only sources are committed for C and W, so on 2026-10-12 they were regenerated in a scratch copy (fixtures plus `runs/T08`, so the scripts' relative CSV paths resolve) for side-by-side viewing. Both rebuilt in both rounds. C's `make_infographic.py` ran as is and printed the key's numbers (35,280 / Aug 3,030 / Aug 420; round 2 35,630 / Dec 3,330). W's `build.py` needed Playwright's browser: the installed Playwright expects `chromium_headless_shell-1243`, only `-1194` is on the machine and `playwright install` could not download, so the unchanged `build.py` was run through a wrapper that passes the existing headless shell as `executable_path`. Its CSV and bar-scale self-checks passed (0.1486 px/cup for all 48 segments, both rounds).

## 1. Blind scores (written before opening key.csv)

2026-10-12 blind pass over all six outputs (both rounds of V, C and W):

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| OTWV | V r1 | 5 | 4 | All numbers right; Zilla Slab headings with Fira Sans body, three navy cards with amber values (clear hierarchy), coral rule; stacked bars with totals on a 0–3,500 axis; donut with outside % labels and a legend with cup counts. The share section is loose: the donut sits off-centre, its legend floats at the far right and an empty band separates it from the footnote. Chart titles are inset 28 px from the page margin |
| XMBF | V r2 | 5 | 4 | Same layout; 35,630, December / 3,330, plum tea and rule; "December" fits its card |
| 3YBW | C r1 | 5 | 4 | All numbers right; solid but plain DejaVu layout; busiest callout leads with the number |
| IFMO | C r2 | 5 | 4 | December correct, plum tea |
| QUXE | W r1 | 5 | 5 | Serif headings, coloured callout edges, August highlighted; donut + share table; most polished |
| NB8E | W r2 | 5 | 5 | December callout and highlight, plum tea |

The 2026-10-12 scores for C and W agree with the 2026-10-05 and 2026-10-06 passes (C 5/4, W 5/5). Earlier V runs scored 5/4 blind (0.18.0 and 0.20.0).

## 2. Hard checks (round 1)

Bar heights were measured in each PNG by scanning the centre column of each bar up from the baseline for the drink colours. V's numbers were also checked in the PDF text (`pdftotext`) and in the chart data stored in `infographic.vixl` (all 48 inline values equal the CSV; the group's `chart.summary` holds the 12 month totals, the four drink totals and 35,280).

| Check | V (0.26.0) | C | W |
| --- | --- | --- | --- |
| PNG 1200×1800 | PASS (RGB) | PASS | PASS |
| Every number matches the key; % sum | PASS: 35,280; August 3,030; cold brew August 420; 44.6/33.7/7.1/14.7; counts 15,720/11,880/2,500/5,180; all 12 month totals | PASS: same, plus counts 15,720/11,880/5,180/2,500 | PASS: same, plus counts |
| Bars to scale, zero baseline (Aug ≈ 1.09× Feb) | PASS: Aug/Feb 1.0938 (exp 1.0939); 0.1387 px/cup for all 12 bars (Feb 384 px, Aug 420 px, Dec 413 px); every one of 48 segments within 2 px of value × 0.1387 (the separator lines and the axis row account for the rest) | PASS: 1.0922; 0.1486 px/cup ±0.0002 | PASS: 1.0947; 0.1488 px/cup ±0.0002 |
| Same colour per drink; legend | PASS (bars, both legends, donut) | PASS | PASS |
| Title, subtitle, footnote | PASS (exact) | PASS (exact) | PASS (exact) |
| **Total** | **5/5** | **5/5** | **5/5** |

Note on "% sum to 100": the correctly rounded one-decimal shares sum to 100.1 %. The key's own values do the same, so all three pass. All three reports now disclose it (V's round-1 report does this time).

Other facts for V: the share chart is a Vixl `chart` of kind `donut`; sampled around the ring, the slices come out within 0.7 points of the true shares (slice gaps and antialiasing). The value axis now stops at 3,500 instead of 4,000, so the bars use more of the chart's height. The SVG has text converted to outlines (0 `<text>` elements; inspector: 455 paths, 0 images). The PDF is vector, 16.67 × 25 in, with no images and two embedded fonts (Zilla Slab Bold, Fira Sans Regular). `vixl check` on a scratch copy of the source reports 0 errors and 1 warning (the twelve stack-total labels, 23 px against a 26.4 px minimum), as reported.

## 3. Report honesty

- V: **yes** (both rounds). Every checked claim matches the files. Round 1: fonts (Zilla Slab 700 / Fira Sans 400), rounded cards 180 px tall, labels and notes 27 px, footnote at y 1700, chart 720 px tall with `font_size` 27 and `bar_gap` 0.18, axis 0–3,500, Aug ≈ 0.138 px/cup ("about 417 px"; measured 420), the 100.1 % share sum, PDF vector, and the single open check finding. Round 2: no pixel exactly coral and 56,862 plum pixels (both exact), SVG `rgb(107,63,105)` 16 times and no `rgb(226,114,91)`, PDF text, "December" ending at x 728 inside the card's inner edge at 742, the plum accent rule disclosed as a choice.
- C: **yes**.
- W: **yes**. "PDF embeds them" is true (Type 3 + CID TrueType).

## 4. Round 2 (December corrected, tea → plum `#6b3f69`)

Answer key: total 35,630; busiest December 3,330 (the trap); cold brew peak August 420; 44.6 (15,900) · 33.6 (11,960) · 14.8 (5,260) · 7.0 (2,510). All three meet it exactly (PDF text checked).

| | V (0.26.0) | C | W |
| --- | --- | --- | --- |
| Dec bar to scale | 462 px = 0.1387 px/cup (same scale; axis stays 0–3,500) | 495 px = 0.1486 | 495 px = 0.1486 |
| Busiest-month callout switched | Yes (December / 3,330 cups sold) | Yes | Yes (Dec axis label bolded automatically) |
| Tea plum everywhere | Yes (0 coral pixels left; 12 segments, both legend swatches, donut slice, plus the accent rule, disclosed) | Yes | Yes (incl. header accent stripe) |
| Drift (PNG diff bands) | Only the rule, card 1 value, card 2 value and note, the tea legend swatch, the Dec total label, the tea segments and the Dec bar, the donut, its % labels and its legend. All 134 layer IDs are the same in both files; "December" kept its 60 px size | Only expected areas + source line "(Dec corrected)" | Only expected areas + Aug/Dec label weight + source line |
| Editability | **4**: changed in place in one atomic batch, nothing else moved. `chart-data set` fixed the four December cells and the bar chart recomputed its segments and total label; a single `chart colors` restyle recoloured tea in both charts. But the donut holds its own inline totals and the callouts are plain text, so the agent worked out 15,900 / 11,960 / 2,510 / 5,260, 35,630, "December" and "3,330" itself and typed them in (`chart-data set` on the donut, `text-set` on three card layers). It checked them against the donut's `summary`, but the bar chart's own `summary.by_series` already held the four totals and nothing carried them across | **5**: CSV row + one colour constant | **5**: CSV row + one colour constant (sed) |
| Revision | **5** | **5** | **5** |

Vixl gaps still seen in 0.26.0: no binding between charts or from a chart's `summary` to text, so the donut and the callouts don't follow the bar chart's data; the chart engine draws stack totals at 0.85 × `font_size` (23 px at 27), which its own `check` flags as a `fix` legibility warning on a 1200 px poster (minimum 26.4 px, no mechanical repair; clearing it needs `font_size` 31, which enlarges every chart label); and the SVG export still outlines all text.

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 5/5 | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 | 5 / 4 | 5 / 4 |
| Report honest | yes | yes | yes |
| Editability / revision | 3 / 5 | 4 / 5 | 4 / 5 |

Scores are unchanged from 0.20.0, but the run was smoother. The value axis is tighter (0–3,500 instead of 0–4,000), so the bars are drawn at 0.139 instead of 0.112 px/cup. The rolled Zilla Slab / Fira Sans pairing with navy cards replaces the plain Inter layout. `vixl check` went from 53 thumbnail warnings to one finding for the chart. In round 2 the problems from 0.20.0 didn't come up: the series carried no colours of their own, so one `colors` restyle recoloured tea, "December" fit its card at full size, and the whole fix was one atomic batch with every layer ID kept. What still holds editability at 4 is the missing data flow. The donut totals and the three callout values were computed outside Vixl and typed in. C and W regenerate everything from one CSV. Craft stays at 4: the share section is loosely composed (off-centre donut, legend at the far right, empty band above the footnote) and the chart titles sit 28 px inside the page margin, plainer than W.
