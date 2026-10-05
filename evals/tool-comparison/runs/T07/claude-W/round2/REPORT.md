# T07 round 2 · Name badges: claude, lane W (HTML/CSS + Playwright/Chromium)

## What changed
1. **11th badge added:** Iris / Van der Berg / Speaker / Lowtide Labs. Output: `badges/badge-11.png`.
2. **Sponsor colour is now plum `#6b3f69`** (it was coral `#e2725b`). Navy text on plum would only reach about 1.85:1, so the sponsor bar text is now **white**, which measures 8.27:1. This affects badges 05 (花子 山田) and 09 (Ana Lucía Gómez). The header rule on those badges also takes the role colour, so it is plum too.
3. **Everything regenerated:** `badges/badge-01.png` … `badge-11.png` (1200 × 900 px each) and `badges-print.pdf`.

## How
- I copied `build.py`, `badge.css` and `fonts/` from the round-1 folder into `round2/`. Nothing outside `round2/` was changed.
- **Data:** the fixture CSV was not edited. I copied it to `round2/badges.csv` and appended the row `Iris,Van der Berg,Speaker,Lowtide Labs`.
- **`round2/build.py`** has three edits:
  - It reads `CSV = HERE / "badges.csv"` (the local copy).
  - It asserts 11 rows instead of 10.
  - The sponsor entry is now `("#6b3f69", "#ffffff")` (bar colour, then text colour).
- `badge.css` and the layout and imposition code are unchanged.
- To rebuild, run `python3 build.py` from `round2/`. It also rewrites `_badges.html`, `_print.html` and `_png_geometry.json`, which are intermediates kept for inspection.
- **Checks:**
  - The script's geometry check reported `problems: none` for both the PNGs and the PDF. That covers text inside the badge, text inside the margins and no overlapping blocks.
  - Badge 11 needed no shrinking: first name 210 px, last name 104 px, company 58 px.
  - Badge 04 still shrinks as in round 1.
  - `pdftotext` returns "Iris", "Van der Berg" and "Lowtide Labs".
  - I viewed badges 05, 09 and 11 and both PDF pages as images.

## Print PDF
- US Letter portrait, still **2 pages**.
- Page 1 holds rows 1–6, as before.
- Page 2 now holds rows 7–11. That is five badges: two full rows, plus Iris in the left slot of the bottom row. The bottom-right slot is empty.
- Crop marks now cover all three rows on page 2. The marks for the right column's outer edge are still printed at the bottom, because that cut line serves the rows above it.

## Caveats carried over from round 1
- The CJK name falls back to the system font WenQuanYi Zen Hei. That font is not copied into the folder.
- The badges have no bleed, and the PDF is RGB.

## Tool calls
9 tool calls in this round. That counts 6 Bash calls, 2 image Reads, and the final hand-back. The Bash count includes the call that wrote this report and one that corrected its contrast figures.
