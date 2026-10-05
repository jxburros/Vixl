# T05 · Slide deck: Tidewick Café, 2025 in Review (lane V, Vixl MCP)

**Timing:** started 22:16:25 UTC, finished 22:24 UTC on 2026-10-05, so about 8 minutes. I made about 59 tool calls, counting the Vixl MCP calls plus a few Bash calls to read docs, check the exports and write this report.

## Files

| File | How it was made |
| --- | --- |
| `deck.vixl` | The editable Vixl source. I made it with `vixl_document_create(size="slide")`, which gives 1920×1080 (16:9). It has two masters, `content` (cream) and `dark` (navy), and six pages. Each page has speaker notes. I built everything with `vixl_operations_apply`, plus `vixl_text_add` for the two page-number layers. |
| `deck.pptx` | `vixl_export_file`. It has 6 slides at 13.33×7.5 in (16:9), and all text is editable text boxes. Each slide has a title placeholder: the layers are named `title`, and python-pptx reads the right title on every slide. Each slide has its speaker notes (6 of 6). The export reported no `raster_fallbacks`. Fonts used: Rubik and Young Serif, plus Arial, which Vixl writes as the bullet-character font. |
| `deck.pdf` | `vixl_export_file`. Six pages, one per slide, vector content, real selectable text (I checked it with pypdf). |
| `REPORT.md` | This file. |

## Design choices (made on my own)

- **Fonts:** Young Serif for headings and numbers, Rubik for body text. This is the curated pairing `young-serif-rubik`, which Vixl downloads and embeds. I picked it for a warm, harbor-café feel.
- **Colors:** I used only the five brand colors. Content slides have a cream background, navy text, and a short amber bar above the title. The title and closing slides are navy, with a stylized "lamp-sun over the harbor": an amber circle, a sea-foam sea band and navy wave lines. Coral marks Q3 in the chart and the 4.8★ statistic.
- **Same layout on every slide:** every content slide (2–5) has its title at x=120, y=124, 72 px, on the `content` master. The footer is a rule at y=992, with "Tidewick Café" on the left and "N / 6" on the right, both 24 px. The title and thank-you slides use the `dark` master, with the same footer in light colors. Type sizes used: 24 (footer), 40, 48, 72, 96 and 128 px.
- **Chart:** I drew it from native shapes (bars, a baseline) plus text labels; it is not an embedded chart object. The axis starts at zero, so the bars look nearly equal, which is true of the data. Each bar has its value above it and Q1–Q4 below it. I added the caption "Cups poured per quarter, 2025", and colored Q3, the peak, coral.
- **Stats slide:** three navy cards, each with a big number and a short label underneath. I split each statistic into number and label, for example "35,280" / "cups poured".

## Differences from the brief and open questions

- **Speaker notes** are 2–3 sentences per slide, written by me. Some contain details I made up (cold brew helping Q3, sharing owners and timelines by the end of the month); the presenter should check or edit them.
- **Chart in PowerPoint:** the bars are editable shapes, but they are not a PowerPoint chart object, so the data can't be edited as a table.
- **Fonts on other machines:** PowerPoint, Keynote and Google Slides need Young Serif and Rubik (both free Google Fonts). Google Slides has both; on other machines they may be substituted unless installed. The PDF embeds them.
- **"Fallback font" warnings:** the final `vixl_check(checks=["deck"])` passes with 0 errors. It still shows `fonts` warnings that the text layers use the bundled fallback font. I believe this is a false positive: through MCP I set fonts per text span (rich text), because the MCP blocks the `font` field on `text`. The renders and the PPTX runs use Young Serif and Rubik.
- **DejaVu Sans in the PDF:** the PDF's font list for pages 2–6 includes a DejaVu Sans subset. I did not track down which glyph uses it. It may be the ★ or the • bullets falling back. Nothing looks wrong in the renders.
- **Line break on the title slide:** "Tidewick Café — 2025 in Review" is one string that wraps in its box. It is not two separate lines.
- **Not opened in real apps:** I did not open the deck in PowerPoint, Keynote or Google Slides. I only checked the PPTX structure with python-pptx and the XML, and the PDF with pypdf.
