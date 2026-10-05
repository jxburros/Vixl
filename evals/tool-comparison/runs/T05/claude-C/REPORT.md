# T05 · Slide deck — lane C (claude-C)

**Timing:** start 22:16:26 UTC, end 22:20 UTC (2026-10-05), about 4 minutes of wall-clock time. 13 tool calls.

## Files

| File | How it was made |
| --- | --- |
| `build_deck.py` | The editable source. One Python layout spec (in inches, on a 13.333 × 7.5 in 16:9 canvas) feeds two renderers: python-pptx for the PPTX and reportlab for the PDF. Run `python3 build_deck.py` to rebuild both files. |
| `deck.pptx` | Made by python-pptx 1.0.2. Six 16:9 slides (13.333 × 7.5 in). All text is in real, editable text boxes. Bullets are real paragraph bullets (`a:buChar` ■, colored). The bar chart on slide 3 is a native, editable PowerPoint column chart with its data embedded, value data labels (`#,##0`) and the value axis fixed at 0–10,000. The footer slide number is a real `slidenum` field. Each slide has 2–3 sentences of speaker notes in its notes page. |
| `deck.pdf` | Made by reportlab from the same layout spec, not converted from the PPTX. Six pages at 960 × 540 pt, one slide per page, with real (selectable) text. Liberation Sans (metric-compatible with Arial) is embedded, and the ★ and ■ glyphs use DejaVu Sans. |
| `previews/contact-sheet.png` | A QA image of all six PDF pages, made with pdftoppm and Pillow. |

## Design
- Brand colors as given: navy `#14263b`, amber `#f2a541`, sea-foam `#a8d5c8`, coral `#e2725b`, cream `#f7f1e5`. I also used white for the stat cards, `#4a5a6c` (a softened navy) for secondary text, and `#f6c27a` (a lighter amber) for the inner "lamp" circle.
- Slides 1 and 6 (title and closing) are navy with an amber "harbor lamp" circle and sea-foam/coral "water" lines. Slides 2–5 are cream.
- Content slides 2–5 all use the same layout: the title at (0.8 in, 0.55 in) in Arial Bold 36 pt navy, an amber rule under it, body text at 28 pt, and the same footer.
- The footer appears on slides 2–6: a thin rule, "Tidewick Café" on the left (12 pt bold) and the slide number on the right.
- Slide 3: the bars start at zero, so the four quarters honestly look almost equal. I colored Q3, the highest quarter, amber and added the caption "Steady all year, with a summer peak in Q3".

## Differences from the brief and choices I made
- **Title slide has no footer.** I read "footer on every content slide" as excluding the title slide. Slide 6 does have the footer.
- **Added text the brief didn't ask for:** the caption on slide 3 (above).
- **Stat layout:** each statistic is split into a big number ("35,280") and a label ("cups poured") in separate text boxes. The words match the brief, but they are not stored as one string.
- **PDF route:** the lane allows only free libraries and non-LibreOffice converters, so I didn't export the PDF through LibreOffice. reportlab draws the PDF from the same spec instead.
- **Title line break:** the title box on slide 1 is 7.0 in wide so that the title wraps after "—" ("Tidewick Café — / 2025 in Review"). The text is still the exact single string from the brief, with no manual line break.

## Things I'm unsure about
- **I never opened the PPTX in PowerPoint, Keynote or Google Slides.** I checked it only by reading it back with python-pptx and inspecting its XML. The visual check covered only the PDF. In the PPTX:
  - The chart's plot area is laid out automatically, so bar positions will differ slightly from the PDF.
  - Arial is not a font Keynote/Google ship under that exact name; they substitute Helvetica or Arial, which may change line breaks slightly.
- **The ★ in "4.8★".** It is in an Arial run, and Arial has no ★ glyph. The PPTX relies on each app's font fallback to show it, which should work but I didn't verify it. The PDF embeds it from DejaVu Sans.
- **Text boxes use fixed sizes with autofit off.** I left plenty of room, but if a substituted font is wider, a title could wrap.
