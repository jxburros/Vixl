# T05 · Slide deck — judge notes

Runs:

- **claude-V (Vixl 0.26.0)**: re-run and judged 2026-10-12 by a claude-opus-5-5 judge subagent. The V deliverables (`deck.vixl`, `deck.pptx`, `deck.pdf`, both rounds) were judged as delivered. Effort: round 1 took 4.8 min and 43 tool calls, round 2 took 2.2 min and 21 tool calls.
- **claude-C (python-pptx + reportlab)**: run and judged 2026-10-05. Its scores below are unchanged from that judging. For the 2026-10-12 blind pass, C's deliverables were regenerated from the committed `build_deck.py` (round 1 and round 2) in a scratch copy outside the repo. Both scripts ran cleanly.

## 1. Blind scores (written before opening key.csv)

2026-10-12 blind pass (V re-run, C regenerated). Slides were looked at as PDF pages (pdftoppm) and as PPTX rendered by LibreOffice. Neither Young Serif nor Rubik is installed on the judge machine, so the LibreOffice PPTX renders of V show substitute fonts.

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| PZ0Y | r1 | 4 | 4 | Copy right apart from "4.8★": the star is a separate vector shape, so the text reads "4.8". Young Serif headings and Rubik body text, an amber "lamp" and sea-foam waves on a navy cover, white stat cards with coloured tabs, and "2025"/"2026" panels on slides 4–5. The chart starts at zero, with an axis, gridlines and value labels, but all four bars are navy with no emphasis. Slide 2 leaves the lower third empty, and Young Serif's old-style figures make "312" sit higher than the other stats. Footer "Tidewick Café" and "n / 6" on every slide. |
| 317Q | r1 | 5 | 4 | All copy exact, with ★ as text. Native chart from zero, with the Q3 bar in amber. Clean and consistent, but a generic Arial/Liberation look. The PPTX and PDF match closely. |
| JQBW | r2 | – | – | 7 slides, 35,630, Q4 bar at 9,250 and taller than Q3. "Our regulars" quote card in the same style. Page numbers read "n / 7". |
| VWZZ | r2 | – | – | 7 slides, 35,630, Q4 bar at 9,250 and highlighted. Caption reads "finishing strongest in Q4". Quote card slide in the same style. |

Key: PZ0Y = claude-V, 317Q = claude-C, JQBW = claude-V/round2, VWZZ = claude-C/round2.

C's blind scores (fidelity 5, craft 4) match its 2026-10-05 scores, which are kept.

Earlier blind passes, kept for the record: 2026-10-06 (Vixl 0.20.0): 0UKY = claude-V, fidelity 4, craft 4; E86F = claude-C, fidelity 5, craft 4. 2026-10-05 (Vixl 0.18.0): 4QDL = claude-V, fidelity 5, craft 5; ZJIV = claude-C, fidelity 5, craft 4.

## 2. Hard checks (round 1)

| Check | V (Vixl 0.26.0, 2026-10-12) | C (2026-10-05) |
| --- | --- | --- |
| slides=6, 16:9 | PASS: 6 slides, 13.33×7.5 in | PASS: 6 slides, 13.33×7.5 in |
| picture_only_slides=0 | PASS (0 pictures) | PASS (0 pictures) |
| slides_without_notes=0 | PASS (every slide has 3 sentences) | PASS (every slide has 3 sentences) |
| All copy exact ("—", "·", "★") | **FAIL**: "—" and "·" are exact in both files, but "4.8★" is the text "4.8" plus a freeform star shape (alt text "star (4.8 out of 5 stars)"). Neither the PPTX nor the PDF text contains ★. The two long titles are split into two paragraphs at the dash; the words are exact. Vixl itself can set the character: in a scratch copy, `text-set stat-3 "4.8★"` exports "4.8★" to PDF (DejaVu Sans fallback, embedded) and to PPTX (the ★ run names DejaVu Sans). Replacing it was the agent's choice, disclosed in REPORT.md. | PASS (same split of number and label) |
| Chart: 4 labeled bars, to scale, zero baseline | PASS: native clustered column chart with values [8560, 8830, 8990, 8900], axis 0–10,000 and series data labels `#,##0`. In the PDF at 72 dpi the bars measure 166/172/175/173 px from the same baseline, 19.39–19.48 px per 1,000 cups. | PASS: native column chart, values [8560, 8830, 8990, 8900], axis min 0 / max 10000, data labels `#,##0` |
| Footer café name + slide number; title position/sizes consistent | PASS: "Tidewick Café" and "n / 6" on all 6 slides. Content titles are the slide's title placeholder at (0.83, 0.93) in, Young Serif 45 pt; slide 5's sits at 0.91 in (a 0.02 in ink-top offset). Body 30 pt, stat labels 20 pt, footer 13.5 pt. | PASS: footer on slides 2–6 with a real `slidenum` field; titles at (0.8, 0.55) in, 36 pt; body 28 pt |
| deck.pdf 6 pages, matches PPTX | PASS: 6 pages at 13.33×7.5 in, with the same content and layout. Young Serif and Rubik are embedded as subsets. The PPTX has no bold mismatch this time (both faces are regular weight). | PASS: 6 pages at 13.33×7.5 in; drawn by reportlab from the same spec, not converted |
| Opens cleanly in PowerPoint/Google Slides | PASS (structural only): the judge had no PowerPoint or Drive upload. The OOXML check is clean: all parts parse, every relationship target exists and the content types are complete. LibreOffice opens both rounds. | PASS (structural only): same check, clean |
| **Total** | **7/8** | **8/8** |

Other facts about V:

- Fonts are not embedded in the PPTX (no `ppt/fonts`). It names Young Serif and Rubik, both OFL Google Fonts. The PDF embeds subsets of both.
- The .vixl has two masters (`deck`, `cover`) and embeds both fonts. The PPTX has one slide master and one blank layout; each slide's title is a title placeholder.
- The waves were made with a stroke and **no** `fill` (`build-ops.json`), and they export with `<a:noFill/>`. The 0.20.0 white-fill bug is gone.
- `vixl check --checks deck` on both rounds: passed, 1 warning (46 px chart labels off the type scale) and 10 info findings (cover decorations that bleed on purpose).

## 3. Report honesty

- V (2026-10-12): **yes**. The files match what it claims: two masters, Young Serif/Rubik, the native chart with labels and a zero axis, 13.333×7.5 in PDF with embedded fonts, the footer, three-sentence notes and the check result. It discloses the ★ drawn as a shape (and that the slide text therefore reads "4.8"), the hard line breaks in the two titles, the footer on the cover slides, the extra year panels, the unembedded PPTX fonts, that no real app was tried, and the per-corner radius crash (confirmed below). Small points:
  - It counts 11 info findings in round 1; the judge's re-run of the check finds 10 info plus the 1 warning.
  - `build-ops.json` still gives the card tabs per-corner radii (`[28, 28, 0, 0]`). The single-radius workaround was applied in an unsaved inline batch, so replaying the saved batches alone would hit the PPTX crash. The report does mention "one inline batch".

  Round-2 report: **yes**. Every change it lists is in the files, and nothing else changed. Its "grep of `round2/` finds no 35,280, 8,900 or 8900" is true of the files as grep sees them. The current document state is clean, but the old values are still in the `.vixl`'s undo history (inside the zipped `project.json`). That is expected and harmless.
- C (2026-10-05): **yes**. It discloses the missing title-slide footer, the reportlab PDF route, the ★ fallback and that the PPTX wasn't tested in an app. It doesn't mention the unembedded Helvetica in the PDF, which is harmless.

## 4. Round 2 (Q4 = 9,250, total 35,630, new "Our regulars" slide)

Answer key: 7 slides; slide 2 reads 35,630; the Q4 bar reads 9,250 and is taller than Q3. Both runs meet it.

| | V (2026-10-12) | C (2026-10-05) |
| --- | --- | --- |
| Result | 7 slides. 35,630 on slide 2 and in its notes. The native chart's data reads [8560, 8830, 8990, 9250]; in the PDF the Q4 bar is 180 px against Q3's 175 px, on the same 19.46 px per 1,000 scale. The chart notes and alt text were rewritten because Q4 is now the peak. The bars stay all navy, so the new peak is not emphasised. New slide 3 uses the `deck` master, with the title placeholder at the same spot and size (45 pt), a full-width card (about 1680×540 px) with the amber tab, and its own three-sentence notes. The quote and attribution are exact, with curly quotes and the em dash. The quote is the same size as the title (both 90 px). | 7 slides. 35,630 on slide 2 and in its notes. Chart data 9,250, with the highlight moving to Q4 automatically. Caption changed from "summer peak in Q3" to "finishing strongest in Q4". Chart notes rewritten. New slide 3 in the same frame, with notes. Quote and attribution exact. |
| Drift (r1→r2 page diff at 50 dpi) | Pixel differences outside the intended edits are anti-aliasing only: the re-subset fonts shift a few edge pixels in the titles, stats and year panels, with no visible change at 100 dpi. Otherwise only the page numbers ("n / 7"), the stat and the Q4 bar and label changed. The PPTX text and notes are identical apart from the intended edits. `polish-ops.json` is unchanged; `deck.md` and `build-ops.json` were updated to the new values. | Only TextBox 6, the caption, the slide numbers and the two notes changed |
| Editability | **5**: the agent edited a copy of the .vixl in place in one atomic batch, plus a one-op size tweak. `chart-data set` changed Q4 on the existing chart, and `text-set` changed the stat, so the layer IDs `cups-chart` (`lyr_e583f13afb3f62bc`) and `stat-1` (`lyr_799d8905387de6a2`) are the same in both rounds. The new slide came from `page add … duplicate/after "by-the-numbers"`. Nothing was deleted and rebuilt. 2.2 min, 21 tool calls. | **5**: edits to the data, caption and notes, plus a new `quote` slide kind in the script |
| Revision | **5** | **5** |

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 8/8 | 8/8 | 7/8 |
| Fidelity / craft | 5 / 5 | 4 / 4 | 4 / 4 |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 | 5 / 5 |

On 0.26.0 both PPTX bugs the 0.20.0 judge found are fixed, and the judge confirmed this with fresh scratch documents. A plain text layer in a bold registered face (`public-sans-700`) now exports with `b="1"`. A `wave` with a stroke and no fill now exports with `<a:noFill/>`, and this run's waves set no fill and come out unfilled. The round-2 workflow is as good as on 0.20.0: in-place `chart-data`/`text-set`/`page add duplicate`, with IDs kept and no drift. It was also fast (2.2 min). The lost hard check is the agent's choice to draw the ★ as a shape after a font check warned about fallback glyphs, which Vixl would in fact have handled. The fidelity point is lost for the same reason. Craft stays at 4: the deck is distinctive (serif, lamp and waves, year panels), but the chart bars have no emphasis, slide 2 leaves the lower third empty, and the quote is the same size as the title.

Still open:

- **Fonts in PPTX.** Fonts are still not embedded in the PPTX.
- **New bug.** PPTX export crashes on a `rounded-rectangle` with per-corner `radius`.

## 6. Vixl bugs and gaps reproduced on 0.26.0

- **PPTX export crashes on per-corner radii (confirmed).** In a scratch document, `{"type":"shape","shape":"rounded-rectangle","radius":[20,20,0,0],...}` applies and renders, and it exports to PDF and SVG. `vixl export --out b.pptx` dies with an uncaught `TypeError: unsupported operand type(s) for -: 'list' and 'int'` at `src/vixl/pptx_export.py:272` (`radius = layer.get("radius", ...) - pad` in `geometry`). This is a raw traceback rather than a JSON error. The PPTX `roundRect` preset can't express per-corner radii, so a custom geometry (or a clear refusal) is needed.
- **No font embedding in PPTX** (known; documented as a limitation).
- **Fixed since 0.20.0**: bold flag on plain text in a bold registered face, and unfilled open shapes (wave) exporting white.
