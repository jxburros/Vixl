# T05 round 2: Q4 correction and "Our regulars" slide (lane V, Vixl MCP)

I made about 32 tool calls in this round: 20 Vixl MCP calls, 8 Bash calls (reading the brief, the old report and the skill docs, reading inputs from the `.vixl` file, checking the exports, and writing this report), 1 ToolSearch, plus this report and the hand-off.

## Files in `round2/`

| File | How it was made |
| --- | --- |
| `deck.vixl` | I copied `../deck.vixl` here first and edited only the copy, using `vixl_operations_apply`. Nothing outside `round2/` was changed. |
| `deck.pptx` | `vixl_export_file`. It has 7 slides with editable text and 7 sets of speaker notes, and `raster_fallbacks` came back empty. |
| `deck.pdf` | `vixl_export_file`. It has 7 vector pages with selectable text. |
| `REPORT.md` | This file. |

## Changes

1. **Q4 = 9,250 (slide "Cups by quarter", now slide 4)**
   - The Q4 value label now reads "9,250", and I moved it up to y=300 so it stays above its bar.
   - The Q4 bar is now 535 px tall (y 365–900). That uses the same px-per-cup scale as the other bars (about 0.0578), and the axis still starts at zero.
   - Q4 is now the peak, so I moved the coral highlight from Q3 to Q4. Q3 is navy like Q1 and Q2.
   - How I did it: Vixl's `shape` operation with a `target` adds a new layer instead of changing the existing one. So I removed the old `bar-q3` and `bar-q4` layers and replaced them with new layers of the same names and positions, in the new colors. My first try also left a stray full-canvas rectangle, which I removed in the same fix.
   - I rewrote the speaker notes. They used to say Q3 was the best quarter at 8,990; they now say cups grew every quarter from 8,560 to 9,250 and Q4 was the best quarter.
2. **Total = 35,630 (8,560 + 8,830 + 8,990 + 9,250)**
   - The "cups poured" statistic on "By the numbers" now reads 35,630. I set it with `rich-text`, keeping the Young Serif span font and the centered paragraph.
   - The speaker notes for that slide now say 35,630.
   - The total appears nowhere else in the deck. In the PDF text, "35,280" and "8,900" no longer appear; "35,630" and "9,250" do.
3. **New slide 3, "Our regulars", placed right after "By the numbers"**
   - I added it with `page add` (`after: "numbers"`) on the same `content` master. That gives it the cream background, the amber accent bar above the title, and the footer rule with "Tidewick Café" and the page number.
   - The page numbers are master variables (`${page} / ${pages}`), so every slide now reads N / 7 automatically.
   - The title layer is named `title` and sits at x=120, y=124, 72 px Young Serif navy, the same as the other content slides. It becomes the PowerPoint title placeholder.
   - The quote “Best flat white on the coast.” is 112 px Young Serif navy, with curly quotes as given. I made its box 960 px wide so it breaks as "“Best flat white / on the coast.”" and doesn't leave "coast." alone on the second line.
   - The attribution "— Jo, regular since 2019" is 48 px Rubik navy. I tried coral first, but `vixl_check` failed it on contrast (2.75:1 on cream), so I switched to navy.
   - A 12 px amber vertical rule runs to the left of the quote and attribution.
   - Speaker notes (3 sentences): "Numbers only tell part of the story, so here is one of our regulars in her own words. Jo has been coming in since 2019, and this is what she wrote about us. Moments like this come from the care each of you puts into every cup."

## Checks

- `vixl_check(checks=["deck","contrast","overlap","bounds"])` on all 7 pages: passed, 0 errors and 0 warnings. My first check of the new slide found two problems, which I fixed: the quote was cut off by its text box, and the coral attribution failed contrast.
- I looked at previews of all pages, the new slide and the chart.
- python-pptx shows 7 slides with the right titles in order (title, By the numbers, Our regulars, Cups by quarter, What worked, 2026 priorities, Thank you), notes on all 7, and the values 35,630 and 9,250. pypdf shows 7 pages.

## Unsure or worth checking

- **"her" in the notes:** the notes for the new slide call Jo "her". The brief doesn't give Jo's gender, so edit that if it's wrong.
- **Q4 notes:** "a strong finish through the winter months" is my wording, not from the brief.
- **Still from round 1:** the caveats in `../REPORT.md` still apply. The chart is made of shapes, not a PowerPoint chart object. The decks need the Young Serif and Rubik fonts installed. I did not open the deck in PowerPoint, Keynote or Google Slides.
