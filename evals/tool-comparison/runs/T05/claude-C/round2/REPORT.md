# T05 round 2 · lane C (claude-C)

I worked in `round2/` only. I copied `build_deck.py` into it, edited the copy, and ran `python3 build_deck.py` there. That rebuilt `deck.pptx` (python-pptx) and `deck.pdf` (reportlab) from the same layout spec. Nothing outside `round2/` was changed.

**Tool calls:** 10, counting this report and the final hand-off.

## Files in round2/
| File | What it is |
| --- | --- |
| `build_deck.py` | The edited source (a copy of the round-1 script) |
| `deck.pptx` | Rebuilt by python-pptx. Now has **7** slides, each with speaker notes. |
| `deck.pdf` | Rebuilt by reportlab. 7 pages, 960 × 540 pt, with real text |
| `previews/contact-sheet.png` | A QA image of all 7 PDF pages, made with pdftoppm and Pillow |

## What changed
1. **Q4 corrected to 9,250.** The chart data changed from `("Q4", 8900)` to `("Q4", 9250)`. In the PPTX this is the native chart's embedded data, and its data label now reads "9,250". In the PDF the bar and its label are redrawn. The value axis is still fixed at 0–10,000 and the bars still start at zero. Check: 8,560 + 8,830 + 8,990 + 9,250 = 35,630.
2. **Total updated to 35,630 everywhere it appears:** the "By the numbers" stat card ("35,630" / "cups poured") and that slide's speaker notes ("We poured 35,630 cups…"). The total appears nowhere else: not in the titles, the other notes or the document properties.
3. **Follow-on fixes caused by the correction.** Q4 is now the highest quarter, so the script's "highlight the best quarter" rule moves the amber bar from Q3 to Q4 automatically. The round-1 chart caption ("Steady all year, with a summer peak in Q3") and the chart notes ("Q3 was our best quarter…") were now wrong. I rewrote the caption as "Steady all year, finishing strongest in Q4", and the notes now give Q4 as 9,250 and call it the best quarter.
4. **New slide 3, "Our regulars"**, placed right after "By the numbers". It has a new `quote` slide kind with the same content-slide frame as the others: the 36 pt navy title in the same position, the amber rule and the footer (café name plus a real slide-number field). The body is a white card like the stat cards, with a sea-foam top band and an amber vertical quote bar. The quote “Best flat white on the coast.” uses real curly quotes and is set in Arial Bold 54 pt navy. The attribution "— Jo, regular since 2019" is in 26 pt soft navy (`#4a5a6c`). The slide has 3 sentences of speaker notes.
5. **Renumbering.** The later slides moved down one place (chart 4, What worked 5, 2026 priorities 6, Thank you 7). Slide numbers come from the slide-number field (PPTX) and the slide index (PDF), so they updated themselves.

## Checks
- I read the PPTX back with python-pptx and confirmed the 7 slide texts, the chart values `[8560, 8830, 8990, 9250]` and notes on every slide.
- I ran `pdftotext` on the PDF and found no "35,280" or "8,900".
- I looked at the contact sheet and a close-up render of slide 3. In my first try the two-line quote overlapped the attribution, so I gave the quote box room for two lines and moved the attribution down. It's clean now.

## Unsure
- As in round 1, I didn't open the PPTX in PowerPoint, Keynote or Google Slides. At 54 pt the quote wraps after "the" in the PDF. If an app substitutes a wider font than Arial, the line break may differ, but the box has room for two lines.
- The brief asked for six slides, and this round adds a seventh as requested.
