# T05 · Slide deck — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Runs: claude-V (Vixl), claude-C (python-pptx + reportlab).

## 1. Blind scores (written before opening key.csv)

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| 4QDL | r1 | 5 | 5 | All copy exact; bar chart with value labels and baseline; distinctive Young Serif/Rubik pairing and sun-over-harbor motif; same footer "n / 6" on every slide |
| ZJIV | r1 | 5 | 4 | All copy exact; native chart from zero; clean, consistent, but generic Arial/Liberation look |
| VLI3 | r2 | – | – | 7 slides, 35,630, Q4 9,250 highlighted, quote slide in style |
| GY3P | r2 | – | – | 7 slides, 35,630, Q4 9,250 highlighted, quote card slide in style |

Key: 4QDL = claude-V, ZJIV = claude-C, VLI3 = claude-V/round2, GY3P = claude-C/round2.

## 2. Hard checks (round 1)

| Check | V | C |
| --- | --- | --- |
| slides=6, 16:9 | PASS: 6 slides, 13.33×7.5 | PASS: 6 slides, 13.33×7.5 |
| picture_only_slides=0 | PASS (0 pictures) | PASS (0 pictures) |
| slides_without_notes=0 | PASS (all 3 sentences) | PASS (all 3 sentences) |
| All copy exact ("—", "·", "★") | PASS: every string matched character by character in PPTX and PDF text (stats split into number + label boxes, words exact) | PASS: same (same split) |
| Chart: 4 labeled bars, to scale, zero baseline | PASS: shape bars; heights 3.438/3.542/3.604/3.569 in = 4.01e-4 in per cup for each bar, bottoms at the 6.25 in baseline; labels 8,560 · 8,830 · 8,990 · 8,900 | PASS: native column chart, values [8560, 8830, 8990, 8900], axis min 0 / max 10000, data labels #,##0 |
| Footer café name + slide number; title position/sizes consistent | PASS: footer on all 6 ("Tidewick Café", "n / 6"); content titles at (0.83, 0.76) in, 36 pt Young Serif; body 24 pt | PASS: footer on slides 2–6 with a real `slidenum` field; titles at (0.8, 0.55) in, 36 pt; body 28 pt |
| deck.pdf 6 pages, matches PPTX | PASS (note: PDF page is 26.67×15 in, i.e. 2× the PPTX size; same aspect and content) | PASS: 6 pages, 13.33×7.5 in; drawn by reportlab from the same spec, not converted |
| Opens cleanly in PowerPoint/Google Slides | PASS (structural only): no PowerPoint/Impress/Drive upload available to the judge; OOXML check (all parts parse, every rel target exists, content types complete) is clean | PASS (structural only): same check clean |
| **Total** | **8/8** | **8/8** |

Other facts: V's PPTX uses Rubik and Young Serif, not embedded in the PPTX (PowerPoint without them will substitute; Google Slides has both). V's chart is editable shapes, not a chart object. V bullets are real `a:buChar`. V uses one master with one Blank layout plus a title placeholder per slide. C's PDF has unembedded Helvetica (unused base font) beside embedded Liberation/DejaVu; C's ★ sits in an Arial run (relies on font fallback, disclosed).

## 3. Report honesty

- V: **yes**. Shape chart, font dependence, DejaVu fallback in the PDF and no real-app test are all disclosed. "Two masters" refers to the .vixl source (true there). Not mentioned: the PDF page size is 2× the PPTX.
- C: **yes**. Missing title-slide footer, reportlab PDF route, the ★ fallback and the untested PPTX are disclosed. Not mentioned: unembedded Helvetica in the PDF (harmless).

## 4. Round 2 (Q4 = 9,250, total 35,630, new "Our regulars" slide)

Answer key: 7 slides; slide 2 reads 35,630; the Q4 bar reads 9,250 and is taller than Q3. Both runs meet it.

| | V | C |
| --- | --- | --- |
| Result | 7 slides; 35,630 on slide 2 + notes; Q4 bar 3.715 in (= 9,250 at the same scale), label 9,250; highlight moved Q3→Q4; chart notes rewritten; new slide 3 in the content master style with notes; quote and attribution exact | 7 slides; 35,630 on slide 2 + notes; chart data 9,250; highlight moved automatically; caption "summer peak in Q3" → "finishing strongest in Q4"; chart notes rewritten; new slide 3 in the same frame with notes; quote and attribution exact |
| Drift (shape-by-shape diff r1→r2) | Only stat-1, bar-q4, value-q4, page numbers (n / 7) and the two notes changed | Only TextBox 6, the caption, slide numbers and the two notes changed |
| Editability | **4**: edited the .vixl copy in place, but a `shape` op with `target` adds a new layer instead of changing it, so bars were deleted and recreated; a stray full-canvas rectangle had to be removed | **5**: data/caption/notes edits plus a new `quote` slide kind in the script |
| Revision | **5** | **5** |

Vixl-specific gaps seen: no native chart object in PPTX export; fonts not embedded in PPTX; no way to change an existing shape's fill/height via `shape target`; PDF page size differs from PPTX.
