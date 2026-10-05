# T08 Infographic, round 2 — Lane C (code + free libraries)

## What changed

1. **December data corrected.** New values: flat white 1,480, drip 1,120, cold brew 90, tea 640, so December's total is 3,330 (it was 2,980).
2. **Tea is now plum `#6b3f69`** everywhere it appears: its bar segments, the legend swatch, its donut slice and its swatch in the share table. It was coral `#e2725b`. Coral is no longer used anywhere (the SVG contains no `#e2725b`).

## Numbers that changed as a result (all recomputed by the script, none typed in by hand)

| Item | Round 1 | Round 2 |
| --- | --- | --- |
| Total cups (callout, donut centre, share subtitle) | 35,280 | **35,630** |
| Busiest month (callout) | August, 3,030 | **December, 3,330** |
| Cold brew peak (callout) | August, 420 | August, 420 (unchanged; December's cold brew is only 90) |
| December bar and its total label | 2,980 | **3,330** |
| Flat white | 44.6% (15,720) | 44.6% (**15,900**) |
| Drip | 33.7% (11,880) | **33.6%** (**11,960**) |
| Tea | 14.7% (5,180) | **14.8%** (**5,260**) |
| Cold brew | 7.1% (2,500) | **7.0%** (**2,510**) |

The other month totals (Jan to Nov) are unchanged. The size order of the drinks is unchanged (flat white, drip, tea, cold brew), so the donut and the table keep the same order. The rounded percentages now add up to exactly 100.0% (in round 1 they added up to 100.1%). The value axis still runs from 0 to 3,500, which fits the new 3,330 maximum, so I left the scale as it was.

## How

- I copied `../make_infographic.py` and the fixture `evals/tool-comparison/fixtures/coffee-2025.csv` into `round2/`. I edited only the copies. The fixture CSV and all files outside `round2/` are untouched.
- `round2/coffee-2025.csv`: changed the `Dec` row to `Dec,1480,1120,90,640`.
- `round2/make_infographic.py`: three changes.
  1. `CSV` now reads `HERE / "coffee-2025.csv"`, the corrected copy.
  2. Added `PLUM = "#6b3f69"` and set `COLORS["tea"] = PLUM`.
  3. The source line at bottom right now reads "Source: coffee-2025.csv (Dec corrected)".
  The layout code is the same as round 1.
- I reran the script (`python3 make_infographic.py` in `round2/`) with matplotlib's Agg backend. It wrote `infographic.png`, `infographic.svg` and `infographic.pdf` again.

## Files in round2/

| File | Notes |
| --- | --- |
| `infographic.png` | 1200 × 1800 px (checked with Pillow) |
| `infographic.svg` | Vector version. Text is kept as text and set in DejaVu Sans, as in round 1. |
| `infographic.pdf` | Vector version with the fonts embedded. 864 × 1296 pt. |
| `make_infographic.py` | Editable source (copy of the round 1 script, edited) |
| `coffee-2025.csv` | Corrected copy of the data |
| `REPORT.md` | This file |

## Checks

- The script's printed output matched the table above: total 35,630; busiest month December at 3,330; cold brew peak August at 420; and the drink totals and shares shown.
- I extracted the PDF text with pypdf. It contains 35,630, 3,330, December, 15,900, 11,960, 5,260, 2,510, 33.6%, 14.8% and 7.0%, and it no longer contains 35,280.
- Bars are to scale. Measured in the PNG, the plum top of December's bar is at y = 657 against an expected 655.3 (3,330/3,500 × 520 px above the baseline at y = 1150). January's is at y = 724 against an expected 722.1. The roughly 1.5 px gap comes from the cream segment outline, as in round 1.
- I looked at the rendered PNG. The December label "3,330" sits just above its bar, below the top of the plot, and nothing is clipped or overlapping.

## Unsure about

- Plum and navy are both dark. They are still easy to tell apart here because amber and sea-foam sit between them in each bar, and the donut slices are separated by cream gaps.
- As before, the SVG needs DejaVu Sans installed to look exactly like the PNG.

## Tool calls

8 tool calls in this round: 7 before the hand-back (read the files, read the script and CSV, regenerate, view the PNG, check the vectors, re-measure the bars, write this report), plus the final hand-back. Time: 22:24:54 to about 22:26 UTC.
