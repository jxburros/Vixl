# T16 · Café menu — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes: V (Vixl), W (HTML/CSS + Chromium print).

## 1. Blind scores (before key)

Round 1 codes have the original prices. H1EA and EYKV are round 2.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| LQ3Z | 5 | 4 | All copy present, dense dot leaders, aligned tabular prices, cream page, classic serif head. Type on the small side, and about 15 % of the page is empty at the bottom. |
| OO3J | 5 | 5 | All copy present. Navy header and footer bands, letter-spaced section heads, a highlighted seasonal panel, aligned prices. Fills the page well. |

Key: LQ3Z = V, OO3J = W.

## 2. Hard checks (round 1)

Method: a script matched every name+price line from `pdftotext`; `pdftotext -bbox` gave the price x positions; pypdf text-matrix sizes gave the point sizes; margins came from the preview content bounding box.

| Check | V | W |
| --- | --- | --- |
| One 8.5×14 in page, real text | PASS (612×1008 pt; Playfair and Lato embedded as CID TrueType) | PASS (612×1008 pt; P052 and URW Gothic embedded as Type 3) |
| 22 items, prices, 3 descriptions, tags, key and footer exact | PASS | PASS (letter-spaced heads extract as "C O F F E E") |
| Prices right-aligned, decimals lined up, leaders | PASS (every price box at x 479.62–510.00 pt; dot leaders) | PASS (every price box at x 478.18–508.56 pt; dotted-border leaders) |
| Nothing below 9 pt | PASS (smallest 10.08 pt) | PASS (smallest 9.49 pt, the tags) |
| Margins ≥ 0.5 in, one page | PASS (content margins 211/211/150/157 px at 150 dpi; the cream background runs to the page edge) | PASS (frame at exactly 75 px = 0.5 in) |
| Preview 1275×2100 | PASS | PASS |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty

- **V — yes.** Margins, sizes, fonts, tabular-figure alignment and the full-page cream flood are all accurately stated. It explains that the `vixl_check` font warning is a false positive: the font can only be set per span through MCP.
- **W — yes.** Sizes, Type 3 embedding and the letter-spacing extraction quirk are all disclosed.

## 4. Round 2 (+$0.25 on coffee, remove Drip refill, add "Oat milk +$0.75" under Coffee)

Both PDFs match the answer key exactly: Espresso 3.25, Macchiato 3.75, Cortado 4.25, Flat white 5.00, Cappuccino 5.00, Latte 5.25, Crème brûlée latte 6.00, Drip coffee 3.00. Drip refill is gone and the oat-milk note is present. Tea, Bakery and Seasonal are unchanged in both, including the lattes in Seasonal and the Chai latte.

| | V | W |
| --- | --- | --- |
| Method | Re-set the three coffee rich-text boxes (names, leaders, prices) with 8 lines each, shortened them by hand from 734 to 653 px, and added a note layer, all in one batch | Edited the data array (prices, row removed, note field) and added one `.note` CSS rule |
| Drift (preview row diff) | Changed rows only within the Coffee section (y 438–788) | Coffee changed; later sections reflowed by up to 8 px (normal flow, no content drift) |
| Editability / revision | 4 / 5 | 5 / 5 |

Vixl note: rich-text columns hold whole sections, so removing one line meant rewriting all three columns and setting box heights and leader dot counts by hand. It took 23 tool calls, against 5 for W.
