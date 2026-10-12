# T05 round 2: Vixl lane (claude-V)

## What changed

1. **Q4 corrected to 9,250.** The year's total is now **35,630** cups (8,560 + 8,830 + 8,990 + 9,250).
   - **Slide 4, "Cups by quarter":**
     - The Q4 bar and its value label now show 9,250. It is still a native PowerPoint chart, with data 8,560 / 8,830 / 8,990 / 9,250.
     - The chart's alt text now says Q4 9,250.
     - The speaker notes used to say Q4 "dipped only slightly, to 8,900", which is no longer true. They now say cups grew every quarter and Q4 was the best quarter, at 9,250.
   - **Slide 2, "By the numbers":** the stat card and the speaker notes now say 35,630.
   - **Source files:** `deck.md` and `build-ops.json` now say 35,630 and 9,250, so they match the deck. `deck.md` also has the new slide and its notes.
2. **New slide 3, "Our regulars"** comes after "By the numbers". It shows the quote “Best flat white on the coast.” with the attribution "— Jo, regular since 2019".
   - **Same style as the rest of the deck.** I built it by duplicating the "By the numbers" page. It keeps:
     - the `deck` master (cream background and footer);
     - the title style: a coral bar, then the title in Young Serif 90 px at x 120, y 128;
     - the card style: a cream-white rounded card with a beige stroke and an amber tab.
   - **Layout.** The card is widened to the full content width (1680 x 540). The quote is Young Serif 90 px in navy. The attribution is Rubik 40 px in muted grey, in the same place as the stat labels on slide 2.
   - **Speaker notes:** 3 sentences, like the other slides.
   - **Page numbers** now read `N / 7`. They come from the master's `${page} / ${pages}` variable, so they updated automatically.
3. **Re-exported** `deck.pptx` and `deck.pdf`. Both have 7 slides at 13.333 x 7.5 in, with notes on every slide.

## How

I used only Vixl MCP tools for the deck. I copied the round-1 files into `round2/` and opened `round2/deck.vixl`.

I made the changes in one atomic `vixl_operations_apply` batch. A second, small batch then set the quote size to 90 px. The first batch used:
- `text-set` on `stat-1`
- `chart-data` with Q4 set to 9250, which changes the chart in place and keeps its layer IDs
- `layer-intent` for the alt text
- `page set notes` for the speaker notes
- `page add` with `duplicate: "by-the-numbers"` and `after: "by-the-numbers"`
- `remove`, `rename`, `shape`, `text` and `text-set` to turn the copied page into the quote slide

Both batches are recorded together in `round2-ops.json`, which is a new file; the other file names are unchanged. I exported the PPTX and PDF with `vixl_export_batch`. I edited `deck.md` and `build-ops.json` with a small Python text-replacement script.

## Checks

- **Deck check.** `vixl_check(checks=["deck"])` passes on all 7 pages with 0 fix findings.
  - One review warning is left, the same as in round 1: the chart labels' 46 px size is not on the type scale.
  - My first quote size, 96 px, added a second type-scale warning, so I set the quote to 90 px, which is on the scale.
  - The 10 informational findings are the cover decorations, which bleed off the edge on purpose.
- **PPTX** (python-pptx):
  - 7 slides, each with notes.
  - Slide 3's text is "Our regulars", “Best flat white on the coast.” and "— Jo, regular since 2019".
  - Slide 4's native chart series is [8560, 8830, 8990, 9250].
- **PDF** (pypdf): 7 pages. Page 2 reads 35,630, and page 3 has the quote text.
- **No old numbers left.** A grep of `round2/` finds no "35,280", "8,900" or "8900".
- **Visual check.** I looked at Vixl previews of slide 3, slide 4 and all 7 pages together.

## Notes and known issues

- **Characters in the quote.** It keeps the curly quotes and the em dash exactly as given. The fonts check reported no fallback glyphs.
- **The quote and the title are both 90 px.** The quote reads as a quote because it sits inside the card, but it is not larger than the title.
- **Unchanged from round 1:**
  - Fonts are not embedded in the PPTX, because Vixl cannot embed fonts in PowerPoint files. Young Serif and Rubik are OFL Google Fonts, and the PDF embeds them.
  - I did not open the deck in PowerPoint, Keynote or Google Slides.
- **`polish-ops.json`** is copied unchanged, because it holds no data values.
- **Nothing written outside `round2/`.**
