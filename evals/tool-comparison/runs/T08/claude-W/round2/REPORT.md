# T08 Infographic, round 2: claude, lane W (web code + headless Chromium)

**Tool calls:** I made 7 tool calls for this round: 6 Bash/Read calls, including writing this report, plus the final hand-back.

## What changed

1. **December data corrected.** The old row was `Dec,1300,1040,80,560`. The new row is `Dec,1480,1120,90,640`, so December's total goes from 2,980 to **3,330** cups.
2. **Tea color.** Tea changed from coral `#e2725b` to plum **`#6b3f69`** everywhere it appears: the header accent stripe, legend, bar segments, donut slice and share-table swatch. The other drink colors stay the same.

## Numbers that changed as a result

All of these are computed from the embedded CSV by the page script. I cross-checked them with a separate Python `csv` calculation.

| Item | Round 1 | Round 2 |
| --- | --- | --- |
| Total cups in 2025 (callout, donut centre, share subtitle) | 35,280 | **35,630** |
| Busiest month (callout) | August, 3,030 | **December, 3,330** |
| Cold brew peak (callout) | August, 420 | August, 420 (unchanged; December's new 90 is still well below the peak) |
| Flat white | 15,720 / 44.6% | **15,900 / 44.6%** |
| Drip | 11,880 / 33.7% | **11,960 / 33.6%** |
| Cold brew | 2,500 / 7.1% | **2,510 / 7.0%** |
| Tea | 5,180 / 14.7% | **5,260 / 14.8%** |
| Dec bar label | 2,980 | **3,330** (bold, because it is now the busiest month) |

- The percentages now add up to exactly 100.0%. In round 1 they added up to 100.1%.
- The y-axis maximum is still 3,500, because 3,330 rounds up to 3,500, so the scale (0.1486 px per cup) is the same. `build.py` re-checked all 48 segment heights against value x 0.1486.
- The bold month highlight on the bar chart moved from Aug to Dec automatically.
- The donut slices were redrawn from the new totals.

## How

1. I created `round2/` and copied `infographic.html` and `build.py` into it. Nothing outside `round2/` was edited, including the fixture CSV.
2. I wrote `round2/coffee-2025-corrected.csv`. It is the fixture with only the December row replaced.
3. In `round2/infographic.html` (edited with `sed`):
   - replaced the December row in the embedded `<script type="text/csv">` block;
   - renamed the constant `CORAL = '#e2725b'` to `PLUM = '#6b3f69'` and pointed tea at it;
   - updated the data comment;
   - changed the bottom-right source note to "Source: coffee-2025.csv, December corrected", so the figure no longer claims to match the unmodified fixture.
4. In `round2/build.py`, the integrity check now compares the embedded CSV against `round2/coffee-2025-corrected.csv` instead of the original fixture. It still writes its outputs next to itself, which is `round2/`.
5. I ran `python3 build.py` in `round2/`. It used Playwright with headless Chromium, as in round 1, and regenerated the three outputs.

## Files in round2/

| File | What it is |
| --- | --- |
| `infographic.html` | Editable source (updated data and tea color) |
| `build.py` | Build and check script (now checks against the corrected CSV) |
| `coffee-2025-corrected.csv` | Supporting data file: the fixture with the corrected December row (new in round 2) |
| `infographic.png` | 1200 x 1800 px, Chromium element screenshot |
| `infographic.svg` | Vector version (serialized SVG, live text) |
| `infographic.pdf` | Vector version, 1 page, 1200x1800 CSS px |

I checked the PNG visually. "December" fits inside the busiest-month card, and nothing overlaps. `pdftotext` and a grep of the SVG both show the new numbers.

## Unsure about

- Plum and navy are both dark. They sit next to each other only where the tea slice meets the flat white slice at the top of the donut, and a 3 px cream stroke separates them there. In the bars they are never adjacent (flat white is at the bottom, tea at the top). Labels carry the values in every case.
- The sea-foam contrast caveat from round 1 still applies.
