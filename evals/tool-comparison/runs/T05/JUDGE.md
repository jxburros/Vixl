# T05 · Slide deck — judge notes

Runs:

- **claude-V (Vixl 0.20.0)**: re-run and judged 2026-10-06 by a claude-opus-5-5 judge subagent. The V deliverables (`deck.vixl`, `deck.pptx`, `deck.pdf`, both rounds) were judged as delivered.
- **claude-C (python-pptx + reportlab)**: run and judged 2026-10-05. Its scores below are unchanged from that judging. For the 2026-10-06 blind pass, C's deliverables were regenerated from the committed `build_deck.py` (round 1 and round 2) in a scratch copy outside the repo. Both scripts ran cleanly.

## 1. Blind scores (written before opening key.csv)

2026-10-06 blind pass (V re-run, C regenerated):

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| 0UKY | r1 | 4 | 4 | All copy exact. Chart starts at zero, with value labels and gridlines. Fraunces Bold and Work Sans, white stat cards, sea-foam wave lines and an amber "lamp" circle. Footer "Tidewick Café" and "n / 6" on every slide. The PPTX doesn't match the PDF's type: headings and the 35,280 and 312 stats come out at regular weight, while "4.8" is bold. All bars are amber, with no emphasis. |
| E86F | r1 | 5 | 4 | All copy exact. Native chart from zero, with the Q3 bar in amber. Clean and consistent, but a generic Arial/Liberation look. The PPTX and PDF match closely. |
| RJRW | r2 | – | – | 7 slides, 35,630, Q4 bar at 9,250 and taller than Q3. "Our regulars" quote slide in the same style. |
| MDR8 | r2 | – | – | 7 slides, 35,630, Q4 bar at 9,250 and highlighted. Caption updated. Quote card slide in the same style. |

Key: 0UKY = claude-V, E86F = claude-C, RJRW = claude-V/round2, MDR8 = claude-C/round2.

C's blind scores (fidelity 5, craft 4) match its 2026-10-05 scores, which are kept.

2026-10-05 blind pass (earlier V run on Vixl 0.18.0, kept for the record): 4QDL = claude-V, fidelity 5, craft 5. ZJIV = claude-C, fidelity 5, craft 4.

## 2. Hard checks (round 1)

| Check | V (Vixl 0.20.0, 2026-10-06) | C (2026-10-05) |
| --- | --- | --- |
| slides=6, 16:9 | PASS: 6 slides, 13.33×7.5 in | PASS: 6 slides, 13.33×7.5 in |
| picture_only_slides=0 | PASS (0 pictures) | PASS (0 pictures) |
| slides_without_notes=0 | PASS (every slide has 3 sentences) | PASS (every slide has 3 sentences) |
| All copy exact ("—", "·", "★") | PASS: every string matches in both the PPTX and the PDF text. Stats are split into a number box and a label box; the words are exact. | PASS (same split) |
| Chart: 4 labeled bars, to scale, zero baseline | PASS: native column chart with values [8560, 8830, 8990, 8900], axis 0–10,000 and series data labels `#,##0`. In the PDF, the bar heights measure 258/267/272/269 px for 8,560/8,830/8,990/8,900. That is 0.0302 px per cup for each bar, all from the same baseline. | PASS: native column chart, values [8560, 8830, 8990, 8900], axis min 0 / max 10000, data labels `#,##0` |
| Footer café name + slide number; title position/sizes consistent | PASS: the footer ("Tidewick Café", "n / 6") is on all 6 slides. Every content title is at (0.83, 0.74) in, Fraunces 44 pt; slide 5's title sits at 0.72 in, an ink-top offset of 0.02 in. Body text is 30 pt. Each title is the slide's title placeholder. | PASS: footer on slides 2–6 with a real `slidenum` field; titles at (0.8, 0.55) in, 36 pt; body 28 pt |
| deck.pdf 6 pages, matches PPTX | PASS, with a caveat: 6 pages at 13.33×7.5 in (the same size as the PPTX now), with the same content and layout. However, the PPTX headings have no bold flag, so they show at regular weight where the PDF shows Fraunces Bold. | PASS: 6 pages at 13.33×7.5 in; drawn by reportlab from the same spec, not converted |
| Opens cleanly in PowerPoint/Google Slides | PASS (structural only): the judge had no PowerPoint or Drive upload. The OOXML check is clean: all parts parse, every relationship target exists and the content types are complete. LibreOffice opens both rounds. | PASS (structural only): same check, clean |
| **Total** | **8/8** | **8/8** |

Other facts about V:

- Fonts are not embedded in the PPTX. It names Fraunces, Work Sans and Noto Sans Symbols 2, which are all Google Fonts. The PDF embeds subsets of all three.
- There are two masters (`feature`, `content`) in the .vixl. The waves are exported with `<a:noFill/>` because the agent set `fill: "transparent"` explicitly.
- The PPTX type sizes are 13 (footer), 22 (labels, subtitle), 30 (bullets), 44 (content titles) and 60 pt (cover title, closing title, stats).

## 3. Report honesty

- V (2026-10-06): **yes**. Every file claim checks out: the masters, the title placeholders, the native chart with labels and a 0–10,000 axis, the 960×540 pt PDF with embedded fonts, the type sizes and the footer. The report discloses the wave fill workaround, the missing bold flag, the unembedded PPTX fonts, the footer on the cover slide and that no real app was tried. Two small points:
  - It doesn't say that the "4.8" run *is* bold in the PPTX, so the stats are inconsistent with each other.
  - Its note that the wave phase differs between preview and export could not be reproduced. The Python renderer and the PDF draw the waves the same way.

  Round-2 report: **yes**. Every change it lists is in the files, and nothing else changed.
- C (2026-10-05): **yes**. It discloses the missing title-slide footer, the reportlab PDF route, the ★ fallback and that the PPTX wasn't tested in an app. It doesn't mention the unembedded Helvetica in the PDF, which is harmless.

## 4. Round 2 (Q4 = 9,250, total 35,630, new "Our regulars" slide)

Answer key: 7 slides; slide 2 reads 35,630; the Q4 bar reads 9,250 and is taller than Q3. Both runs meet it.

| | V (2026-10-06) | C (2026-10-05) |
| --- | --- | --- |
| Result | 7 slides. 35,630 on slide 2 and in its notes. The native chart's data reads 9,250 for Q4, and the PDF bar is 279 px, on the same scale as the others and taller than Q3. The chart notes were rewritten because Q4 is now the peak. New slide 3 uses the `content` master, with the title at the same spot and size and its own notes. The quote and attribution are exact, with curly quotes. | 7 slides. 35,630 on slide 2 and in its notes. Chart data 9,250, with the highlight moving to Q4 automatically. Caption changed from "summer peak in Q3" to "finishing strongest in Q4". Chart notes rewritten. New slide 3 in the same frame, with notes. Quote and attribution exact. |
| Drift (r1→r2 page diff at 50 dpi) | The pages that didn't change differ only in the page-number area ("n / 7"). Slide 2 differs only in the stat, and the chart slide only in the Q4 bar and its label. The PPTX text and notes are identical apart from the intended edits. | Only TextBox 6, the caption, the slide numbers and the two notes changed |
| Editability | **5**: the agent edited a copy of the .vixl in place. It used `chart-data set` on the existing chart, so the layer IDs were kept. It changed the stat with `text-set` and added the slide with `page add … after "numbers"`. Nothing was deleted and rebuilt. | **5**: edits to the data, caption and notes, plus a new `quote` slide kind in the script |
| Revision | **5** | **5** |

## 5. Changes since the Vixl 0.18.0 run

| | V on 0.18.0 (2026-10-05) | V on 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 8/8 | 8/8 |
| Fidelity / craft | 5 / 5 | 4 / 4 |
| Report honest | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 |

- **Fixed.** The chart is now a native, editable PowerPoint chart; before, it was drawn as shapes. The PDF page size now matches the PPTX (13.33×7.5 in; it used to be 2×). In round 2, the chart and the stat were edited in place (`chart-data`, `text-set`); before, the bars had to be deleted and recreated.
- **Still open.** Fonts are still not embedded in the PPTX.
- **New problems seen on 0.20.0, both confirmed by the judge:**
  - **Heading bold flag.** Plain text layers set in a bold registered face (`fraunces-700`) export without `b="1"`, so the PPTX headings and stats show at regular weight. Rich-text runs in the same face do get `b="1"`.
  - **Wave fill.** A `wave` shape with no `fill` exports to PPTX with a white fill, although Vixl's renderer and the PDF leave it unfilled.
- **Craft.** The scores are lower partly because of the different design: the bars are plain and all amber, where the earlier run used a more distinctive sun-over-harbor motif. The rest comes from the bold-flag gap, which makes the PPTX visibly weaker than the PDF.
