# T16 · Café menu — judge notes

Lanes: V (Vixl), W (HTML/CSS + Chromium print).

- **V:** re-run on Vixl 0.20.0, judged 2026-10-06 by a claude-opus-5-5 subagent.
- **W:** run and judged 2026-10-05. Its scores and notes below are unchanged. For the 2026-10-06 blind look, its deliverables were regenerated from the committed `menu.html` + `render.py` (rounds 1 and 2) with Playwright Chromium, in a scratch copy outside the repo.

## 1. Blind scores (before key)

2026-10-06 blind set. BRI4 and QDK3 are round 1; KD52 and N615 are round 2.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| BRI4 | 5 | 4 | All copy present. DM Serif Display title, DM Sans body, dot leaders, decimal points lined up with a slightly ragged right edge. Tidy cream panel inside a hairline frame and a navy footer band. Clean but generic. There is a tall empty gap above the footer, and the band sticks out 1 px past the frame line on each side. |
| QDK3 | 5 | 5 | All copy present. Navy header with a small mark, serif type, amber tag labels, a highlighted seasonal panel and aligned prices. Looks finished. |

Key: BRI4 = V (0.20.0), QDK3 = W. W's 2026-10-05 blind code (OO3J) and scores (5/5) still stand. The new look agrees with them.

## 2. Hard checks (round 1)

Method: a script matched every name+price line and every other string from `pdftotext -layout`. pdfplumber gave the character positions and point sizes. Margins came from the preview's non-white bounding box, and the PDF rendered at 150 dpi was compared against the preview.

| Check | V (0.20.0, 2026-10-06) | W (2026-10-05) |
| --- | --- | --- |
| One 8.5×14 in page, real text | PASS (612×1008 pt, 837 text chars; DM Serif Display and DM Sans Regular/Bold/Italic embedded as CID TrueType; the PDF matches the preview) | PASS (612×1008 pt; P052 and URW Gothic embedded as Type 3) |
| 22 items, prices, 3 descriptions, tags, key and footer exact | PASS (0 misses, including é, û, en dashes and middle dots) | PASS (letter-spaced heads extract as "C O F F E E") |
| Prices right-aligned, decimals lined up, leaders | PASS (all 22 decimal points centred at x = 1110.0 px; right edge ragged 1139.6–1145.7 px, about 6 px at 150 dpi, because the figures are proportional; dot leaders) | PASS (every price box at x 478.18–508.56 pt; dotted-border leaders) |
| Nothing below 9 pt | PASS (smallest 10.08 pt, the descriptions) | PASS (smallest 9.49 pt, the tags) |
| Margins ≥ 0.5 in, one page | PASS (all ink starts at exactly 75 px = 0.5 in, the cream panel; text starts 128 px in) | PASS (frame at exactly 75 px = 0.5 in) |
| Preview 1275×2100 | PASS (150 dpi tagged) | PASS |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty

- **V — yes.** The report gives exact figures, and they all check out: 0.5 in panel inset, frame at 0.6 in, text at 0.85 in, 48/12/10.1/10.6/11 pt sizes, decimal alignment by pinned dollars + cents layers, the ragged right edge ("up to about 12 px" at 300 dpi, measured 6 px at 150 dpi), and about 0.5 in of space above the footer. The three `vixl_check` contrast warnings are real; I reproduced them with the `vixl` Python API. The one loose figure: leaders end "about 34 px" before the price, but the visible gap is 25–47 px at 300 dpi, because the dash phase moves the last dot. That is minor.
- **W — yes.** Sizes, Type 3 embedding and the letter-spacing extraction quirk are all disclosed.

## 4. Round 2 (+$0.25 on coffee, remove Drip refill, add "Oat milk +$0.75" under Coffee)

The answer key raises only the Coffee section. Tea, Bakery and Seasonal must not change. Both lanes read it that way: the Seasonal Smoked maple latte ($6.00) and Gingerbread flat white ($5.75) are unchanged in both. V's report says it made this choice and invites correction. Both PDFs match the key exactly: Espresso 3.25, Macchiato 3.75, Cortado 4.25, Flat white 5.00, Cappuccino 5.00, Latte 5.25, Crème brûlée latte 6.00, Drip coffee 3.00. Drip refill is gone and the oat-milk note is present.

| | V (0.20.0) | W |
| --- | --- | --- |
| Method | Copied `menu.vixl`. One batch ran `text-set` on 16 dollars/cents layers, removed the 4 refill layers (name, dollars, cents, leader) and duplicated a description layer for the note. A second batch moved 5 cents layers back onto their baselines | Edited the data array (prices, row removed, note field) and added one `.note` CSS rule |
| Drift (preview diff) | Only the Coffee price column and the refill/note row changed (box x 126–1147, y 438–794). Names, leaders and everything below y 800 are pixel-identical | Coffee changed; later sections reflowed by up to 8 px (normal flow, no content drift) |
| Editability / revision | 5 / 5 | 5 / 5 |

Vixl note: the edit was done in place. Because Vixl places text by the top of the ink, changing ".75" to ".00" moved the cents' baseline by 0.6 px, and the agent had to move five layers back by hand. The note reuses the slot of the removed refill row, so nothing below moved.

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 6/6 | 6/6 |
| Fidelity / craft | 5 / 4 | 5 / 4 |
| Report honest | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 |
| Type | Playfair + Lato, tabular figures, identical right edges | DM Serif Display + DM Sans, decimal points aligned, right edge ragged about 6 px |
| Page | Cream fill to the page edge; content margins 1.4 in | White margin of exactly 0.5 in, cream panel, frame, navy footer band |
| Structure | One rich-text box per column per section | One layer per name, dollars, cents and leader |

- The new structure made round 2 much easier. Each price is its own layer, so the agent changed only the affected layers. It no longer had to rewrite whole columns and resize boxes by hand. Editability went from 4 to 5.
- Craft is the same. The page is tidier and uses its width better, but it is still generic, and the leaders are lengths set by hand that will not follow a name if it changes.
- The 0.18.0 font-check false positive is gone. It has been replaced by a contrast-check failure on centred layers (see below).

## 6. Vixl product issues seen

- **Contrast check fails on half-pixel layers.** `check_design(checks=['contrast'])` reports "Could not measure 'subtitle': boolean index did not match … size of axis is 626 but size of corresponding boolean axis is 624" (the same for `key`, 954/952, and `footer`, 1486/1484). All three are centred layers with x = 962.5, 798.5 and 532.5. The agent had to check those colors by hand.
- **No tab stops, decimal tabs or leaders.** There is nothing in `src/vixl` for leaders or tab stops. The agent built decimal alignment from two layers per price (dollars pinned right, cents starting at the same x) and drew each leader as a dashed line sized by hand from measured name widths.
- **Text placed by ink top, not baseline.** Metrics report a `baseline`, but placement uses the ink box. Rows needed manual baseline moves in round 1, and again in round 2 after changing cents digits (0.6 px shift).
