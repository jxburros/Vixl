# T16 · Café menu — judge notes

Lanes: V (Vixl), W (HTML/CSS + Chromium print).

- **V:** re-run on Vixl 0.26.0, judged 2026-10-12 by a claude-opus-5-5 subagent. Round 1 took 4.4 min and 32 tool calls; round 2 took 1.2 min and 15 tool calls.
- **W:** run and judged 2026-10-05. Its scores and notes below are unchanged. For the 2026-10-12 blind look, its deliverables were regenerated from the committed `menu.html` + `render.py` (rounds 1 and 2) with Playwright Chromium (`executable_path` pointed at `/opt/pw-browsers`), in a scratch copy outside the repo. Both rounds rebuilt without errors.

## 1. Blind scores (before key)

2026-10-12 blind set. YFOF and UHSR are round 1; P1RP and OCS8 are round 2. These scores were written down before `key.csv` was opened.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| YFOF | 5 | 3 | All copy present. DM Serif Display heads, DM Sans body, dotted leaders that all end at one x, decimal points lined up ($1.00 nudged right), right edge ragged. The spacing is cramped around each section head: the head sits on its amber rule, and the rule is 2 px above the first row's ink (measured at 150 dpi). There is then about 70 px between sections. The descriptions are flush with the names, not indented, and the leaders stop about 25 px short of the prices. Tidy, but generic, and the head spacing looks unfinished. |
| UHSR | 5 | 5 | All copy present. Navy header with a small mark, serif type, amber tag labels, a highlighted seasonal panel and aligned prices. Looks finished. |
| P1RP | 5 | 3 | Same page as YFOF with the round-2 changes. The oat-milk note is small grey text, flush left under Drip coffee. |
| OCS8 | 5 | 5 | Same page as UHSR with the round-2 changes. The note is right-aligned italic. |

Key: YFOF/P1RP = V (0.26.0), UHSR/OCS8 = W. W's 2026-10-05 blind code (OO3J) and scores (5/5) still stand, and the new look agrees with them.

## 2. Hard checks (round 1)

Method:

- A script parsed the brief's item block and matched every name+price line, and every other string, against `pdftotext -layout`.
- pdfplumber gave the character positions, baselines and point sizes. Decimal points were measured as the centre of each price's "." glyph.
- Margins came from the preview's non-background bounding box.
- The PDF was rendered with pdftoppm (80 and 200 dpi) and compared against the preview.

| Check | V (0.26.0, 2026-10-12) | W (2026-10-05) |
| --- | --- | --- |
| One 8.5×14 in page, real text | PASS (612×1008 pt, 796 text chars; DM Serif Display and DM Sans Regular embedded as subsets; the PDF matches the preview) | PASS (612×1008 pt; P052 and URW Gothic embedded as Type 3) |
| 22 items, prices, 3 descriptions, tags, key and footer exact | PASS (0 misses, including é, û, è, en dashes and middle dots) | PASS (letter-spaced heads extract as "C O F F E E") |
| Prices right-aligned, decimals lined up, leaders | PASS (`table` column with `align: "decimal"`. The 22 decimal points fall between x 496.34 and 497.15 pt, a 0.81 pt (1.7 px) spread; see §6. The right edge is ragged, 513.9–517.7 pt. Dotted-path leaders) | PASS (every price box at x 478.18–508.56 pt; dotted-border leaders) |
| Nothing below 9 pt | PASS (smallest 11.52 pt, the descriptions) | PASS (smallest 9.49 pt, the tags) |
| Margins ≥ 0.5 in, one page | PASS (the cream fill runs to the page edge, as the report says; the first ink is the navy frame at 91 px = 0.6 in; text starts at 89.0 pt = 1.24 in on both sides) | PASS (frame at exactly 75 px = 0.5 in) |
| Preview 1275×2100 | PASS (150 dpi tagged) | PASS |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty

- **V — yes.** These claims check out against the files:
  - Canvas and sizes: the canvas is 1275×2100. The point sizes are 59.52, 21.12, 17.28, 14.4, 13.44, 12.48 and 11.52.
  - Frames and text inset: the navy frame is at x 90 (0.6 in) and the amber frame at 102 (0.68 in). Text is at least 1.2 in from the side edges.
  - Tables: the four tables share x, width 895 and columns 775/120. "$1.00" sits at x 816 against 807 for the others. The stack gap is 58.
  - Leaders: there are 22 of them, `dash [0.01, 12]`, round caps, 3.5 px, `#7d8794`. They start on a 12 px grid and all end at x 972, 25 px before the `$` ink at 997.
  - Name-to-leader gaps are 16–26 px; the report says 16–28.
  - `vixl_check`: I reproduced the run with the same checks and a 75 px safe area on a scratch copy. It passed with 0 findings.
  - Disclosures: the report says the descriptions were taken out of the table's wrapping with `text-set` at 24 px and re-baselined by hand. It also says the decimal alignment was checked only by eye.

  One figure is loose. The leaders sit "about 6 px above the text baseline", but the dot centre is 4.0 px above it on every row. That is minor.

  The round-2 report is accurate. It names the `table-data` set/remove_rows/append edits, the removal of `leader-09` and the `text-set` on `coffee/r9c1`. The Coffee table is still 420 px high, and nothing outside Coffee changed.
- **W — yes.** Sizes, Type 3 embedding and the letter-spacing extraction quirk are all disclosed.

## 4. Round 2 (+$0.25 on coffee, remove Drip refill, add "Oat milk +$0.75" under Coffee)

The answer key raises only the Coffee section; Tea, Bakery and Seasonal must not change. Both lanes read it that way, and both PDFs match the key exactly:

- Espresso 3.25, Macchiato 3.75, Cortado 4.25, Flat white 5.00, Cappuccino 5.00, Latte 5.25, Crème brûlée latte 6.00, Drip coffee 3.00.
- Drip refill is gone, and the oat-milk note is present.
- The Seasonal Smoked maple latte ($6.00) and Gingerbread flat white ($5.75) are unchanged.

| | V (0.26.0) | W |
| --- | --- | --- |
| Method | Copied `menu.vixl`. One batch, dry-run first: `table-data` on `coffee` (8 `set`, `remove_rows: ["Drip refill"]`, `append` the note row), `remove leader-09`, then `text-set` on the note cell (24 px, `#4a5668`) | Edited the data array (prices, row removed, note field) and added one `.note` CSS rule |
| Drift | Layer diff: 8 price cells changed text, 2 of them moved 1 px in x; `coffee/r9c2` and `leader-09` were removed; `coffee/r9c1` became the note. The preview diff covers only the Coffee price column and the refill/note row (box x 197–1076, y 468–832). Everything below y 832 is pixel-identical | Coffee changed; later sections reflowed by up to 8 px (normal flow, no content drift) |
| Editability / revision | 5 / 5 | 5 / 5 |

Vixl note: unlike 0.20.0, no baselines needed fixing by hand. The table redraws in place and keeps the decimal alignment. The note fits in the refill row's 42 px slot, so nothing below moved.

The round-2 result is right, but the document is fragile for the next edit. I tested this on a scratch copy of round 2. A further `table-data` edit on `coffee` reset the oat-milk note to 30 px navy. The same kind of edit on `seasonal` put the descriptions back to 30 px wrapped on two lines and moved the Gingerbread row from y 125 to 168. The leaders are free layers outside the tables, so they would stay where they were (see §6).

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 6/6 | 6/6 | 6/6 |
| Fidelity / craft | 5 / 4 | 5 / 4 | 5 / 3 |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 | 5 / 5 |
| Type | Playfair + Lato, tabular figures, identical right edges | DM Serif Display + DM Sans, decimal points aligned at one x, right edge ragged about 6 px | DM Serif Display + DM Sans, decimal points within 1.7 px of each other, right edge ragged about 8 px |
| Page | Cream fill to the page edge; content margins 1.4 in | White margin of exactly 0.5 in, cream panel, frame, navy footer band | Cream fill to the page edge, navy frame at 0.6 in and amber frame at 0.68 in, text at 1.24 in |
| Structure | One rich-text box per column per section | One layer per name, dollars, cents and leader | One `table` per section (decimal price column) in a `stack`; 22 free dotted-path leaders |
| Effort (r1 / r2) | n/a | n/a | 4.4 min, 32 calls / 1.2 min, 15 calls |

What changed:

- The run used the new `table` with a decimal column, so decimal alignment came from Vixl rather than from separate dollar and cents layers.
- Round 2 was one batch of `table-data` edits with no hand fixes. In 0.20.0, five layers had to be moved back onto their baselines.
- The contrast-check failure on centred half-pixel layers is gone: the subtitle at x 443.5 is measured without error.
- Craft went down a point because the table's header rule crowds the first row. Most of the remaining effort went on working around the table: the descriptions had to be taken out of its wrapping, and the leaders are still drawn by hand outside it.

## 6. Vixl product issues seen

- **No tab stops or dot leaders.** This is still missing (`docs/use-cases.md` BLK-07). The agent drew 22 dotted paths, placed from measured name widths. They are not tied to the table rows, so any row reflow leaves them behind.
- **Table redraw discards per-cell edits.** Reproduced on a scratch copy of round 2. After a `table-data` `set` on `coffee`, `coffee/r9c1` (the note) went from 24 px `#4a5668` back to 30 px `@navy`. After a `set` on `seasonal`, `seasonal/r2c1` went back to 30 px and wrapped ("…double ristretto,\nsteamed milk."), and the `seasonal/r3c1` row moved from y 125.25 to 168. Nothing warns that the overrides were lost. A table has no per-row style or spanning note/description row, which is what a menu needs.
- **Decimal alignment is off by up to 1.7 px.** The decimal points measure between 496.34 and 497.15 pt. The figure depends on the leading digit: "$6" sits 0.8 pt left and "$3" 0.25 pt left of the others. `tables.layout` places the fraction at `right - points - kit.width(whole)`. `kit.width` is the ink-box width, so it misses the last digit's right side-bearing, and `charts.Parts.text` then rounds x to whole pixels. The same rounding of ink-top y leaves some names up to 0.35 pt (0.7 px) off their price's baseline (Espresso 239.18 vs 239.53 pt). You cannot see either at print size, but alignment that is meant to be exact is not exact.
- **Header rule crowds the first row.** With `borders: "header"` and `padding: 6`, the header row is 42 px for 44 px type. The rule is drawn at y 40–44, the head's ink ends at 34, and the first row's "$" starts at 46, 2 px below the rule (measured in the preview). The table offers no separate spacing around the header rule.
