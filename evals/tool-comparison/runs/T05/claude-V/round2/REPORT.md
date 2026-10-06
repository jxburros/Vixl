# T05 round 2 · Slide deck revisions — lane V (Vixl)

All edits were made with the Vixl MCP tools (`vixl_document_open`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview`, `vixl_export_batch`). I drew no pixels and wrote no SVG/HTML. I copied `../deck.vixl` to `round2/deck.vixl` with `cp` and edited only the copy. Short Python/poppler scripts were used only to read the original notes and to check the exports. Nothing outside `round2/` was changed.

## Files

| File | What it is |
| --- | --- |
| `deck.vixl` | Editable source, now 7 pages (history kept: round-1 edits plus these) |
| `deck.pptx` | 7 slides, 16:9, native editable chart, speaker notes on all 7, no raster fallbacks |
| `deck.pdf` | 7 vector pages with selectable text and embedded fonts |
| `REPORT.md` | This report |

## 1. Q4 correction: 8,900 → 9,250; total 35,280 → 35,630

Check: 8,560 + 8,830 + 8,990 + 9,250 = 35,630.

| Place | Before | After | How |
| --- | --- | --- | --- |
| Slide "Cups by quarter" chart (Q4 bar and its value label) | 8,900 | 9,250 | `chart-data` with `set: [{category: "Q4", value: 9250}]` on the existing chart group, so the bars, labels and layer IDs are redrawn in place. The axis still runs 0–10,000, so 9,250 fits. The chart's stored total is now 35,630. |
| Chart in the PPTX | 8,900 | 9,250 | Re-exported; the native chart's data table reads 8560, 8830, 8990, 9250 (checked with python-pptx). |
| Slide "By the numbers", first stat card | 35,280 | 35,630 | `text-set` on `stat-1` (same font, size, position). |
| Speaker notes, "By the numbers" | "We poured 35,280 cups" | "We poured 35,630 cups" | `page set notes`. |
| Speaker notes, "Cups by quarter" | said Q3 (8,990) was the peak and Q4 "held almost level at 8,900" | Q4 is now the strongest quarter at 9,250 | `page set notes`. The old wording would have been wrong, not just out of date, so I rewrote that sentence: "The fourth quarter was our strongest at 9,250, even as the weather turned." |

I searched the whole document (layers, notes, chart data) for 35,280 / 35280 / 8,900 / 8900; those were the only places. The total does not appear on the title, closing or other slides. The round-1 notes did not mention the total elsewhere.

## 2. New slide 3, "Our regulars"

Inserted with `page add ... after: "numbers"`, so it is slide 3 of 7; the later slides moved down one and the `${page} / ${pages}` footers now read 1 / 7 … 7 / 7 automatically.

- **Same style:** `content` master (cream background, amber bar above the title, sea-foam rule, footer). Title layer named `title` at x=120, y=130, Fraunces 700, 88 px, navy, matching slides 2 and 4–6, so it becomes the slide title placeholder in the PPTX.
- **Quote:** “Best flat white on the coast.” in Fraunces 700, 120 px, navy (the same size as the stats), in a 1100 px wrapping box so it breaks as "Best flat white / on the coast." The text itself has no manual line break and uses typographic curly quotes.
- **Attribution:** "— Jo, regular since 2019" in Work Sans 400, 60 px, navy (the bullet size used on other slides).
- **Accent:** a 14 px amber vertical rule at the left of the quote and attribution, a pull-quote mark built from the brand amber.
- **Speaker notes:** "Numbers only tell part of the story, so here is one of our regulars in her own words. Jo has been coming in since 2019, and this is what she wrote about us. Moments like this come from the care you put into every cup."

## Checks

- `vixl_check(checks=["deck"])` on all 7 pages: 0 errors, 0 warnings, 1 informational note (the intentionally cropped lamp circle on slides 1 and 7, as in round 1).
- Previewed every page (`page="all"`) and the new slide at full size.
- PPTX (python-pptx): 7 slides, titles correct, notes on 7/7, one native chart with Q4 = 9250, stat reads 35,630. PDF (pdftotext): contains 35,630, 9,250 and the new slide text; no 35,280 or 8,900.

## Notes and caveats

- **Pronoun in the notes.** The notes call Jo "her". The brief gives no gender; change it to "their" if that is wrong.
- **Inferred story in the cups notes.** Saying Q4 was the strongest quarter is just what the corrected numbers show; the phrase "the winter menu helped us finish the year on a high" is my wording, replacing round 1's "should help us hold that line", which no longer fit.
- Round-1 caveats still apply: fonts are not embedded in the PPTX (install Fraunces, Work Sans and Noto Sans Symbols 2, or use the PDF), and PPTX heading runs carry no bold flag.
- **Repository state I found and left alone.** Before I started, `git status` already showed `../REPORT.md` modified and a tracked `round2/REPORT.md` deleted in the working tree (the round-1 files were not changed by me; their timestamps are before this run). This file replaces the deleted `round2/REPORT.md` path with this round's report.
