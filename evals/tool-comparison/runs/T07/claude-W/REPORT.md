# T07 · Name badges: claude, lane W (HTML/CSS + Playwright/Chromium)

**Timing:** start 2026-10-05 22:22:51 UTC, end 2026-10-05 22:24:20 UTC (wall clock as `date` reported it). About 11 tool calls, counting this report and the hand-back.

## Files

| File | How it was made |
| --- | --- |
| `badges/badge-01.png` … `badge-10.png` | 1200 × 900 px, 8-bit sRGB. One per CSV row, in file order. `build.py` writes each badge as HTML in `_badges.html`, styles it with `badge.css` and loads it in headless Chromium (Python Playwright). An element screenshot of each `.badge` gives one PNG. |
| `badges-print.pdf` | 2 pages, US Letter portrait (612 × 792 pt). Made by Chromium `page.pdf()` from `_print.html`. Each badge is the same HTML, scaled by 0.32 into a 4 × 3 in slot. Text stays as vector text, with fonts embedded and subset. The 2 × 3 grid is 8 × 9 in, centred: 0.25 in side margins and 1 in top/bottom margins. Badges butt against each other, so they share their cut lines. Page 1 holds rows 1–6; page 2 holds rows 7–10 in the top two rows, with the bottom row empty. |
| `build.py` | **Editable source.** It reads `../../../fixtures/badges.csv` (UTF-8), maps each role to its colours, shrinks any line that would overflow and checks geometry. It then exports the PNGs and the PDF. Run it with `python3 build.py`. |
| `badge.css` | **Editable source.** The badge design, shared by all 10 badges and by both outputs. |
| `fonts/InstrumentSans-Bold.ttf`, `-Regular.ttf` | The main typeface (SIL OFL), copied from the local canvas-fonts folder. |
| `_badges.html`, `_print.html` | Intermediate pages that `build.py` generates. They are kept so you can inspect them. |
| `_png_geometry.json` | Measured boxes and final font sizes for each text block on each PNG badge, from the overlap check. |

## Design
- Warm off-white background (#fbf8f2) with navy text (#14263b).
- Header at the top: "Harbor Makers Summit 2026" (Bold, 40 px) and "November 20–21, 2026 · Port Ellery" (Regular, 30 px). A rule under the header uses the role colour.
- First name: Bold, 210 px. Last name: Bold, 104 px. Company: Regular, 58 px, grey-navy. The block is centred vertically between the header and the bar.
- The role bar is full width, 200 px tall, at the bottom. The role is printed in capitals (CSS `text-transform`) at 100 px with letter-spacing.
- Bar colours follow the brief: Speaker #f2a541, Attendee #a8d5c8, Staff #14263b, Sponsor #e2725b. Any other role ("Volunteer") gets the Attendee colour and prints its own name.
- Bar text is navy #14263b on amber, sea-foam and coral (roughly 5:1 or better). It is white on navy.
- An empty company field means no company element is rendered at all (row 6, Sam Okafor), so there is no blank line. The name block re-centres.
- Fitting: `build.py` steps a line's font size down until it fits a 1060 px measure (badge width minus 70 px margins), but never below 40 % of the design size. Only row 4 needed it: first name 166 px, last name 71 px, company 46 px. The script then checks that every text block sits inside the badge, stays inside the margins and doesn't overlap the next block. It reported no problems for either the PNGs or the PDF.
- Names come straight from the CSV (HTML-escaped) and appear exactly as written: Café, O'Brien, Zoë Ångström-Okonkwo, 花子 山田, Ana Lucía Gómez. `pdftotext` on the PDF returns them correctly.

## Crop marks
- Hairline marks (about 0.25 pt, black) sit at every cut line, outside the grid only. They start 0.04 in from the trim and are 0.18 in long.
- They are short because the side margin is only 0.25 in.
- Page 2's marks cover only the two filled rows.

## Deviations and uncertainties
- **CJK font.** Instrument Sans has no CJK glyphs, so 花子 / 山田 falls back to the system font "WenQuanYi Zen Hei". The PDF embeds it as a subset. That font isn't copied into the run folder because it is about 17 MB, so rebuilding on another machine needs the font installed.
- **CJK weight.** WenQuanYi has a single weight, so the last name 山田 looks lighter than the bold Latin last names on the other badges.
- **No bleed.** Badges butt edge to edge with no gutter. A cut slightly off the line will show a sliver of the neighbouring badge's background or bar colour. The brief asked for actual size and crop marks, not bleed.
- **PDF colour.** The PDF is RGB, not CMYK, because the brief didn't ask for CMYK. The PNGs have no DPI metadata; 300 dpi is implied by the 1200 × 900 px size.
- **Text sizes.** I didn't measure the smallest text against a minimum print size. The date line is 30 px, about 0.1 in (7.2 pt) at actual size.
- **Page 2 not viewed.** I only looked at page 1 of the PDF as an image. Page 2 passed the automated geometry check and its text extracts correctly.
