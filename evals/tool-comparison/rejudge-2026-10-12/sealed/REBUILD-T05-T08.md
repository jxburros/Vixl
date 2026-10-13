# Rebuild of T05–T08 deliverables (lanes C and W, rounds 1 and 2)

The deliverables were rebuilt by running each run folder's committed source in the scratch mirror. claude-V was not touched. Tool versions here: python-pptx 1.0.2, reportlab 5.0.1, pypdf 6.17.0, Playwright with the pre-installed Chromium (`/opt/pw-browsers/chromium` -> chromium-1194), matplotlib with the Agg backend.

Every font the sources needed was already on this machine. **No fonts were downloaded.** The two Instrument Sans files for T07 claude-W were copied from the folder its REPORT names, the local canvas-fonts folder (`/mnt/skills/examples/canvas-design/canvas-fonts/`).

The only source edits were Chromium executable paths in the claude-W build scripts. They are listed per run below.

## T05 · claude-C (round 1): rebuilt yes
- Command: `python3 build_deck.py`. No edits. Fonts are system files: Liberation Sans Regular/Bold and DejaVu Sans/Bold under `/usr/share/fonts/truetype/`.
- `deck.pptx`: 6 slides, 13.333 × 7.5 in.
- `deck.pdf`: 6 pages, 960 × 540 pt (pdfinfo reports 959.976 × 540).
- **Not rebuilt:** `previews/contact-sheet.png`. The REPORT describes it as a QA image made with pdftoppm and Pillow, but no script for it was committed and `build_deck.py` does not make it.

## T05 · claude-C/round2: rebuilt yes
- Command: `python3 build_deck.py`. No edits.
- `deck.pptx`: 7 slides, 13.333 × 7.5 in.
- `deck.pdf`: 7 pages, 960 × 540 pt. Slide 3 is "Our regulars" and slide 4 shows the Q4 bar as 9,250 in amber.
- **Not rebuilt:** `previews/contact-sheet.png`, for the same reason as round 1.

## T06 · claude-C (round 1): rebuilt yes
- Command: `python3 make_form.py`. No edits.
- `signup-form.pdf`: 1 page, 612 × 792 pt (Letter). The /Annots order matches the REPORT: performer_name, email, phone, act_type ×4, performers, needs_* ×4, pieces, slot, photo_consent, signature, date.
- `signup-sample.pdf`: 1 page, 612 × 792 pt.
- Difference: pypdf here is 6.17.0. The REPORT names pypdf 6.19.

## T06 · claude-C/round2: rebuilt yes
- Command: `python3 make_form.py`. No edits.
- `signup-form.pdf`: 1 page, Letter. instagram comes after email in the /Annots order.
- `signup-sample.pdf`: 1 page, Letter.
- Difference: pypdf 6.17.0, as in round 1.

## T07 · claude-C (round 1): rebuilt yes
- Command: `python3 make_badges.py`. No edits. It reads `../../../fixtures/badges.csv`. Fonts are system files: DejaVu Sans/Bold, and IPAGothic at `/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf`.
- `badges/badge-01.png` … `badge-10.png`: each 1200 × 900, RGB, 300 dpi.
- `badges-print.pdf`: 2 pages, 612 × 792 pt.
- The bar contrast ratios printed by the script match the REPORT: 7.47, 9.50, 4.96 and 15.33.

## T07 · claude-C/round2: rebuilt yes
- Command: `python3 make_badges.py`. No edits. It reads `round2/badges.csv`, which is the fixture plus the Iris row.
- `badges/badge-01.png` … `badge-11.png`: each 1200 × 900, RGB, 300 dpi.
- `badges-print.pdf`: 2 pages, Letter.
- The Sponsor contrast is 8.27:1, as the REPORT says.

## T07 · claude-W (round 1): rebuilt yes
- **Edit to `build.py`:** `p.chromium.launch()` became `p.chromium.launch(executable_path="/opt/pw-browsers/chromium")`. The default headless-shell build is not installed here.
- **Fonts added:** `fonts/InstrumentSans-Bold.ttf` (sha256 444f85bf…) and `fonts/InstrumentSans-Regular.ttf` (sha256 a22cb26e…). Both were copied from the local canvas-fonts folder, which the REPORT names as the original source. The CJK fallback, WenQuanYi Zen Hei, is installed system-wide.
- `badges/badge-01.png` … `badge-10.png`: each 1200 × 900, RGB, with no DPI metadata (the REPORT says the same).
- `badges-print.pdf`: 2 pages, Letter. Embedded fonts: InstrumentSans-Bold, InstrumentSans-Regular and WenQuanYiZenHei, all subset.
- Result: the script printed `problems: none`. Badge 04 shrank to 166 / 71 / 46 px, which matches the REPORT.
- **Intermediates overwritten:** the build regenerated `_badges.html`, `_print.html` and `_png_geometry.json` in place of the committed copies.
- **Difference from the committed geometry:** `_png_geometry.json` matches it except for text widths. Some text widths differ by up to 4.6 px; the largest is the event-name line, 627.5 against 631.5 px right edge. The widest name line differs by about 1–4.6 px. Every vertical position and font size is identical. This is probably a Chromium-version difference in glyph advances, but I did not confirm the cause.

## T07 · claude-W/round2: rebuilt yes
- **Edit to `round2/build.py`:** the same `executable_path` change as round 1.
- **Fonts added:** the same two Instrument Sans files, copied into `round2/fonts/`.
- `badges/badge-01.png` … `badge-11.png`: each 1200 × 900, RGB.
- `badges-print.pdf`: 2 pages, Letter.
- Result: `problems: none`. Badge 11 is at 210 / 104 / 58 px.
- Intermediates were regenerated, and the geometry differs from the committed file in the same way as round 1 (widths up to 4.6 px).

## T08 · claude-C (round 1): rebuilt yes
- Command: `python3 make_infographic.py`. No edits. It reads `../../../fixtures/coffee-2025.csv` and uses DejaVu Sans.
- `infographic.png`: 1200 × 1800, RGBA. The REPORT gives the size but not the colour mode.
- `infographic.svg`: 864 × 1296 pt.
- `infographic.pdf`: 1 page, 864 × 1296 pt, with DejaVu fonts embedded.
- The printed values match the REPORT: total 35,280, Aug 3,030, and shares of 44.6, 33.7, 7.1 and 14.7.

## T08 · claude-C/round2: rebuilt yes
- Command: `python3 make_infographic.py`. No edits.
- `infographic.png`: 1200 × 1800, RGBA.
- `infographic.svg`: 864 × 1296 pt.
- `infographic.pdf`: 1 page, 864 × 1296 pt.
- The numbers match the REPORT: 35,630, Dec 3,330, and shares of 44.6, 33.6, 7.0 and 14.8. `#e2725b` does not appear in the SVG.

## T08 · claude-W (round 1): rebuilt yes
- **Edit to `build.py`:** `p.chromium.launch()` became `p.chromium.launch(executable_path="/opt/pw-browsers/chromium")`. The fonts are system fonts: P052 Bold and DejaVu Sans/Bold.
- `infographic.png`: 1200 × 1800, RGB.
- `infographic.svg`: viewBox 1200 × 1800.
- `infographic.pdf`: 1 page, 900 × 1350 pt.
- Checks: the embedded-CSV assertion against the fixture passed. All 48 segments have a pixel-per-cup ratio of 0.1486. The totals match the REPORT.

## T08 · claude-W/round2: rebuilt yes
- **Edit to `round2/build.py`:** the same `executable_path` change as round 1.
- `infographic.png`: 1200 × 1800, RGB.
- `infographic.svg`: viewBox 1200 × 1800.
- `infographic.pdf`: 1 page, 900 × 1350 pt.
- Checks: the CSV assertion against `coffee-2025-corrected.csv` passed. The ratio is 0.1486, the total 35,630 and the busiest month Dec at 3,330. `#e2725b` does not appear in the SVG.

## Visual spot check
I compared low-resolution renders of the following against the REPORTs and found no problems:
- T05 round 2: all slides.
- T06 round 2: the sample form.
- T07: badges 04, 05, 09 and 11 from both lanes.
- T08 round 2: both lanes.
