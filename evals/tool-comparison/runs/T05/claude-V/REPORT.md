# T05 slide deck: Vixl lane (claude-V)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `deck.vixl` | Editable Vixl source: 6 pages, 2 masters (`deck` for content slides, `cover` for the title and closing slides), brand swatches, speaker notes, embedded fonts | Vixl MCP: `vixl_workflow("deck-from-markdown")` built the first version from `deck.md`. I then restyled it with `vixl_operations_apply` batches (`build-ops.json`, `polish-ops.json`, plus one inline batch) |
| `deck.pptx` | 6 slides at 16:9 (13.333 x 7.5 in), with editable text, a native PowerPoint bar chart on slide 3, real bullet paragraphs on slides 4-5, and speaker notes on all 6 slides. No raster images | `vixl_export_file(path="deck.pptx")` |
| `deck.pdf` | The same 6 slides, one per page, 13.333 x 7.5 in. Vector, with selectable text and fonts embedded | `vixl_export_file(path="deck.pdf")` |
| `deck.md` | Markdown source: slide text plus speaker notes (the `Notes:` sections) | Written by hand. This was the input to `deck-from-markdown` |
| `build-ops.json`, `polish-ops.json` | The Vixl operation batches I applied (brand swatches, masters and footer, per-slide layouts) | Written as JSON with a small Python script and applied with `vixl_operations_apply(operations_path=...)` |

## Design

- **Brand colours.** All five are used as swatches: navy `#14263b` (text, cover background, bars), lamp amber `#f2a541` (lamp disc, 2026 panel, footer dot, star, card tab), sea-foam `#a8d5c8` (waves, footer rule, 2025 panel, card tab, cover subtitle), coral `#e2725b` (title accent bars, card tab) and cream `#f7f1e5` (content background, cover text).
- **Type.** Young Serif for headings and Rubik for body text (the Vixl pairing `young-serif-rubik`).
- **Consistent look.** On every content slide (2-5) the title is in the same place, Young Serif 90 px at x 120, y 128, with a coral bar above it. The type sizes are the same across those slides, and they all use the `deck` master, which carries the footer: an amber dot, "Tidewick Café" on the left, a sea-foam rule, and `N / 6` on the right.
- **Title and closing slides.** Slides 1 and 6 use the `cover` master. It has a navy background and the same footer in light colours. Its decoration is an amber "lamp" disc with a halo, plus three sea-foam wave lines.
- **Slide 3 chart.** A native bar chart, with each bar labelled with its value (8,560 / 8,830 / 8,990 / 8,900). The axis starts at 0.
- **Speaker notes.** Each slide has 3 sentences.

## Checks

`vixl_check(checks=["deck"])` on the final document reports **passed** with 0 fix findings. It found one review-level warning: the chart's label size (46 px) is not on the document's type scale. That size is needed to keep the chart's value labels at or above the 18 pt projected minimum. All 11 informational findings are on the cover decorations (lamp, halo and waves), which bleed off the edge on purpose and are marked `allow_crop`.

I also checked the output files outside Vixl:
- **PPTX** (python-pptx): 6 slides, each with notes, and all slide text present as text.
- **PDF** (pypdf): 6 pages with extractable text.
- **Visual check:** I rendered the PDF pages with pdftoppm and looked at them.

## Differences from the brief

1. **Title line breaks.** The two long titles have a hard line break: "Tidewick Café —" / "2025 in Review" and "Thank you —" / "see you on the quay." Without it, automatic wrapping put the em dash at the start of the second line. In the PPTX and PDF text, the space before the second line is therefore a line break.
2. **The ★ in "4.8★".** The star is drawn as a vector star shape next to the text "4.8", not as a text character. With the ★ character, Vixl's font check reported fallback glyphs in the chosen fonts. The shape has alt text ("star (4.8 out of 5 stars)"). As a result, the editable text on that slide reads "4.8" and "average review", and the star is a separate shape.
3. **Footer on title and closing slides.** The brief asks for the footer on every content slide. Slides 1 and 6 also have it, in light colours on navy.
4. **Year panels.** Slides 4 and 5 have a decorative coloured panel showing "2025" and "2026". This is not in the brief.

## Unsure about / known issues

- **Fonts in the PPTX.** Young Serif and Rubik are **not embedded in the PPTX** because Vixl cannot embed fonts in PowerPoint files. Both are OFL Google Fonts. Machines without them will substitute another font, so line wrapping may change in PowerPoint and Keynote, and Google Slides may substitute too. The PDF does embed both fonts.
- **PowerPoint, Keynote and Google Slides.** I did not open the deck in any of them. I only checked it structurally with python-pptx.
- **Vixl bug found.** PPTX export failed with `unsupported operand type(s) for -: 'list' and 'int'` when a `rounded-rectangle` had per-corner `radius` (a 4-item list). The cause is in `src/vixl/pptx_export.py` around line 272, which assumes `radius` is a number. I worked around it by giving the card accent tabs a single radius value. I did not fix Vixl itself.
- **Old-style figures.** Young Serif uses old-style numerals, so "312" sits visually higher than "35,280" on slide 2. That comes from the typeface; I chose to keep it.
