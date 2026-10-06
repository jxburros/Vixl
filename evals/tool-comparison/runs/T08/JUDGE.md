# T08 · Infographic from data: judge notes

Judges: claude-opus-5-5 subagents. Lanes run: V (Vixl), C (matplotlib), W (hand SVG + Playwright), all claude.

- **V** was re-run on **Vixl 0.20.0** and judged on **2026-10-06**. Blind codes: round 1 KKHM, round 2 37G3.
- **C** and **W** were run and judged on **2026-10-05**; their scores and notes below are unchanged. Old blind codes: C=2VLF (r2 JXAY), W=RQZ3 (r2 U0Q6).

Only sources are committed for C and W, so on 2026-10-06 they were regenerated in a scratch copy for side-by-side viewing. Both rebuilt cleanly in both rounds: C's `make_infographic.py` (after installing matplotlib) and W's `build.py` (Playwright Chromium; its CSV and bar-scale self-checks passed: 0.1486 px/cup for all 48 segments).

## 1. Blind scores (written before opening key.csv)

2026-10-06 blind pass over all six outputs (both rounds of V, C and W):

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| KKHM | V r1 | 5 | 4 | All numbers right; Inter type, navy header band, three white callout cards; stacked bars with totals; donut with % labels and a legend with cup counts. The 0–4,000 axis leaves a lot of headroom over 3,030, and the donut legend sits far off to the right |
| 37G3 | V r2 | 5 | 4 | Same layout; 35,630, December 3,330, plum tea everywhere |
| SKMC | C r1 | 5 | 4 | All numbers right; solid but plain DejaVu layout; busiest callout leads with the number |
| JIJP | C r2 | 5 | 4 | December correct, plum tea |
| BW5I | W r1 | 5 | 5 | Serif headings, coloured callout edges, August highlighted; donut + share table; most polished |
| C1XZ | W r2 | 5 | 5 | December callout and highlight, plum tea |

The 2026-10-05 blind pass (for reference) scored C 5/4, V (0.18.0) 5/4 and W 5/5. The 2026-10-06 scores for C and W agree with it.

## 2. Hard checks (round 1)

Bar heights were measured in each PNG by scanning the centre column of each bar up from the baseline for the drink colours. V's numbers were also checked in the PDF text and in the chart data stored in `infographic.vixl` (all 48 inline values equal the CSV).

| Check | V (0.20.0) | C | W |
| --- | --- | --- | --- |
| PNG 1200×1800 | PASS (RGB) | PASS | PASS |
| Every number matches the key; % sum | PASS: 35,280; August 3,030; cold brew August 420; 44.6/33.7/7.1/14.7; counts 15,720/11,880/2,500/5,180; all 12 month totals | PASS: same, plus counts 15,720/11,880/5,180/2,500 | PASS: same, plus counts |
| Bars to scale, zero baseline (Aug ≈ 1.09× Feb) | PASS: Aug/Feb 1.0935 (exp 1.0939); 0.112 px/cup (448 px per 4,000) for all 12 bars; every one of 48 segments within 1 px of value × 0.112 | PASS: 1.0922; 0.1486 px/cup ±0.0002 | PASS: 1.0947; 0.1488 px/cup ±0.0002 |
| Same colour per drink; legend | PASS (bars, both legends, donut) | PASS | PASS |
| Title, subtitle, footnote | PASS (exact) | PASS (exact) | PASS (exact) |
| **Total** | **5/5** | **5/5** | **5/5** |

Note on "% sum to 100": the correctly rounded one-decimal shares sum to 100.1 %. The key's own values do the same, so all three pass. C and W disclose it; V's report doesn't mention it.

Other facts for V: the share chart is now a real donut (Vixl `chart` kind `donut`); pixel shares of the ring come out within about 0.8 points of the true shares, which is the slice gaps and edge antialiasing. The SVG has text converted to outlines (0 `<text>` elements; disclosed). The PDF is vector, with no images and two embedded fonts (Inter Tight ExtraBold, Inter Regular). `vixl check` on the source passes with 0 errors and 53 thumbnail-legibility warnings, as reported.

## 3. Report honesty

- V: **yes** (both rounds). Every checked claim matches the files: Jan flat white 135 px; winter cold-brew segments 6–12 px; PDF 16.667 × 25 in with two embedded fonts; SVG text outlined; 53 check warnings. Round 2: December segments 166/125/10/72 px, no coral left in the SVG (0 `rgb(226,114,91)` fills; 15 plum fills), plum sampled as rgb(107, 63, 105), new PDF text. The one omission is the 100.1 % share sum.
- C: **yes**.
- W: **yes**. "PDF embeds them" is true (Type 3 + CID TrueType).

## 4. Round 2 (December corrected, tea → plum `#6b3f69`)

Answer key: total 35,630; busiest December 3,330 (the trap); cold brew peak August 420; 44.6 (15,900) · 33.6 (11,960) · 14.8 (5,260) · 7.0 (2,510). All three meet it exactly (PDF text checked).

| | V (0.20.0) | C | W |
| --- | --- | --- | --- |
| Dec bar to scale | 373 px = 0.112 px/cup (same scale); segments 166/125/10/72 px | 495 px = 0.1486 | 495 px = 0.1486 |
| Busiest-month callout switched | Yes (December / 3,330 cups sold) | Yes | Yes (Dec axis label bolded automatically) |
| Tea plum everywhere | Yes (0 coral pixels left; 12 segments, both legend swatches, donut slice) | Yes | Yes (incl. header accent stripe) |
| Drift (PNG diff bands) | Only the callouts, tea legend swatch, Dec label and bar, tea segments, donut and its legend. "December" was set at 56 px instead of 64 px so it fits its card | Only expected areas + source line "(Dec corrected)" | Only expected areas + Aug/Dec label weight + source line |
| Editability | **4**: changed in place, layer IDs kept. `chart-data` fixed the four December cells and the bar chart recomputed its scale, segments and total label. But the donut is a separate chart with its own inline totals, and the callouts are plain text, so the yearly totals and callout values were computed outside Vixl and typed in. The first `colors` restyle didn't recolour the tea bars because each series stored its own `color` (documented: "A series' own `color` wins"), so a second restyle was needed. "December" overflowed its card by 6 px and was resized | **5**: CSV row + one colour constant | **5**: CSV row + one colour constant (sed) |
| Revision | **5** | **5** | **5** |

Vixl-specific gaps seen in 0.20.0: no binding between charts or from a chart to text (the share donut and the callouts don't follow the bar chart's data); a chart-level `colors` restyle silently does nothing for series with their own colour; and `vixl check` raises 53 "fix" legibility warnings on a full-size 1200 × 1800 infographic because it judges text at a 320 px thumbnail.

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 | 5 / 4 |
| Report honest | yes | yes |
| Editability / revision | 3 / 5 | 4 / 5 |

- **Gone:** the hand-built bars and 100 % share bar. Round 1 now uses Vixl's `chart` operation (stacked bar and donut), so the scale, totals, shares and legend come from the data. In round 2, the 14 tea layers no longer had to be deleted and re-added, the `resize` side effect didn't come up, and the PDF exported as vector without extra settings.
- **Better:** the December fix was a `chart-data` cell edit and the bar chart redrew itself to scale. Layer IDs survived. Editability goes from 3 to 4.
- **Same:** the SVG still has outlined text. Craft stays at 4: the layout is clean but plainer than W's, with a lot of headroom above the bars (the axis goes to 4,000) and a share legend placed far from its donut.
- **New friction (0.20.0):** the donut and the callouts aren't linked to the bar chart, so derived numbers were still worked out by hand. A chart-level `colors` change is overridden by per-series colours without any warning. This is documented in `docs/charts.md` and is how `charts.py` works (`s.get("color") or c`), so it's a usability gap, not a bug.
