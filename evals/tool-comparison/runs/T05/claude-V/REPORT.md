# T05 · Slide deck — lane V (Vixl)

All visual work was done with the Vixl MCP tools (`vixl_document_create`, `vixl_font_pair`, `vixl_font_install`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview`, `vixl_export_batch`). I did not draw pixels, write SVG/HTML or use an image generator. Small Python scripts (python-pptx, poppler, LibreOffice, PIL) were used only to read and check the exported files.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `deck.vixl` | Editable Vixl source: 6 pages, 2 masters (`feature`, `content`), swatches, embedded fonts, speaker notes | Built with `vixl_operations_apply` (master / page / text / rich-text / shape / chart operations) |
| `deck.pptx` | 6 slides, 13.333 × 7.5 in (16:9), editable text boxes, slide title placeholders, a native column chart with its data table, speaker notes on all 6 slides, no raster fallbacks | `vixl_export_batch` from `deck.vixl` |
| `deck.pdf` | 6 pages, 960 × 540 pt (16:9), vector with real selectable text; fonts embedded as subsets (Fraunces Bold, Work Sans Regular, Noto Sans Symbols 2) | `vixl_export_batch` from `deck.vixl` |
| `REPORT.md` | This report | Written by hand |

## Design

- Canvas: Vixl named size `slide` (1920 × 1080).
- Brand colours only: navy `#14263b`, amber `#f2a541`, sea-foam `#a8d5c8`, coral `#e2725b` and cream `#f7f1e5`. The stat cards are also filled white (`#ffffff`).
- Type: Fraunces 700 for headings and numbers, Work Sans 400 for body text (Vixl pairing `fraunces-work-sans`). The ★ is set in Noto Sans Symbols 2, because Fraunces has no ★ glyph and Vixl's font check flagged it.
- Masters:
  - `feature` (slides 1 and 6): navy background, an amber "lamp" circle cropped at the top right, two sea-foam wave lines, and a sea-foam footer.
  - `content` (slides 2–5): cream background, a short amber bar above the title, a sea-foam rule, and a navy footer.
- Footer on every slide: "Tidewick Café" at the left and `${page} / ${pages}` at the right (renders as "1 / 6" … "6 / 6"), 26 px, at the same position on all slides.
- Content slides 2–5 all put the title (layer named `title`) at x=120, y=130, 88 px. The type sizes are 26 (footer), 44 (labels, chart text, subtitle), 60 (bullets), 88 (content titles) and 120 (cover and closing titles, statistics).
- Slide 3 uses Vixl's `chart` operation (bar chart): amber bars, with every bar labelled with its value (`#,##0`). The value axis runs from 0 to 10,000. In the PPTX it is a native, editable chart (data labels on, number format `#,##0`).
- Final `vixl_check(checks=["deck"])`: 0 errors and 0 warnings. One informational note remains: the lamp circle is cropped on purpose (marked `allow_crop`).

## Speaker notes

Each slide has 2–3 sentences of speaker notes. They are stored on the pages in `deck.vixl` and exported as slide notes in `deck.pptx`. The PDF has no notes, as expected.

## Differences from the brief and choices I made

- **Footer on the title and closing slides.** The brief asks for the footer on content slides. I also put it, in sea-foam, on slides 1 and 6 so that every slide shows its number.
- **Line breaks.** The cover and closing titles wrap across two lines because the text box is 1300 px wide. The text itself has no line break, so it stays exactly "Tidewick Café — 2025 in Review" and "Thank you — see you on the quay.".
- **The 4.8★ statistic** is one rich-text box with two runs, "4.8" (Fraunces, navy) and "★" (Noto Sans Symbols 2, coral).
- **The chart axis starts at 0.** This is honest, but the four quarters look similar because the values differ by only about 5%.

## Issues found and what I'm unsure about

- **I fixed a Vixl export bug.** Vixl's `wave` shapes had no fill set. They rendered unfilled in Vixl and in the PDF, but the PPTX export gave them a white fill (LibreOffice showed white bands). Setting `fill: "transparent"` explicitly fixed it: the PPTX now writes `<a:noFill/>`, which I checked by re-rendering the PPTX in LibreOffice.
- **Heading weight in the PPTX.** Heading runs reference the family "Fraunces" with no bold flag (`b="1"` is missing). In PowerPoint, Keynote or Google Slides with Fraunces installed, the headings may appear at regular weight instead of the 700 used in the PDF. I did not work around this: adding synthetic bold would have made the Vixl/PDF render too heavy.
- **Fonts are not embedded in the PPTX** (a stated Vixl limitation). Fraunces, Work Sans and Noto Sans Symbols 2 must be installed where the deck is shown, or the app will substitute other fonts. The LibreOffice check render used fallback fonts, so the layout held but the typography changed. All three are Google Fonts, so Google Slides should find them. The PDF embeds all fonts.
- **I could not open the PPTX in PowerPoint, Keynote or Google Slides here.** I checked it with python-pptx (6 slides, a title placeholder on each, notes on each, 1 native chart, 0 pictures) and by converting it with LibreOffice.
- **Wave phase may differ.** In Vixl's own preview the two wave lines crossed each other, but in the PDF export they run parallel (the second wave's `phase` seems to be handled differently). Both look fine; I'm noting it only as a mismatch between preview and export.
- **Footer size.** The footer text is 26 px, which is about 13 pt on the projected slide and below Vixl's 18 pt minimum. Vixl's deck check exempts footers and page numbers from that minimum.
