# T08 · Infographic from data — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Runs: claude-V (Vixl), claude-C (matplotlib), claude-W (hand SVG + Playwright).

## 1. Blind scores (written before opening key.csv)

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| 2VLF | r1 | 5 | 4 | All numbers right; stacked bars with totals; donut + legend with counts; slightly generic type; donut legend order differs from bar legend |
| KOPZ | r1 | 5 | 4 | All numbers right; elegant serif display type; 100% share bar with % labels (7.1 % and 14.7 % crowd a little); large empty band at the bottom |
| RQZ3 | r1 | 5 | 5 | All numbers right; polished editorial layout; donut + table with counts; source line |
| JXAY, HWEF, U0Q6 | r2 | – | – | All show 35,630, December 3,330, plum tea |

Key: 2VLF = claude-C, KOPZ = claude-V, RQZ3 = claude-W; JXAY = C/round2, HWEF = V/round2, U0Q6 = W/round2.

## 2. Hard checks (round 1)

Bar heights were measured in each PNG by scanning the centre column of each bar for the drink colours.

| Check | V | C | W |
| --- | --- | --- | --- |
| PNG 1200×1800 | PASS | PASS | PASS |
| Every number matches the key; % sum | PASS: 35,280; August 3,030; cold brew August 420; 44.6/33.7/14.7/7.1; all 12 month totals | PASS: same, plus counts 15,720/11,880/5,180/2,500 | PASS: same, plus counts |
| Bars to scale, zero baseline (Aug ≈ 1.09× Feb) | PASS: Aug/Feb 1.0944 (exp 1.0939); 0.1607 px/cup for all 12 bars; Aug segments 229/139/68/51 px ∝ 1420/870/420/320 | PASS: 1.0922; 0.1486 px/cup ±0.0002 | PASS: 1.0947; 0.1488 px/cup ±0.0002 |
| Same colour per drink; legend | PASS | PASS | PASS |
| Title, subtitle, footnote | PASS (exact) | PASS (exact) | PASS (exact) |
| **Total** | **5/5** | **5/5** | **5/5** |

Note on "% sum to 100": the correctly rounded one-decimal shares sum to 100.1 %. The key's own values do the same, so all three pass; all three reports disclose it.

Other facts: V's SVG has text converted to outlines (0 `<text>` elements; disclosed). V's share chart is a 100 % bar because Vixl has no arc/wedge shape (disclosed). V shows no per-drink cup counts (not required). The inspector printed `?` unembedded for W's PDF, but pdffonts shows P052-Bold as an embedded Type 3 font; nothing is unembedded. C's SVG relies on installed DejaVu Sans (disclosed).

## 3. Report honesty

- V: **yes**. Numbers, scale method, outlined SVG text, the share-bar choice and the check warnings all match the files.
- C: **yes**.
- W: **yes**. "PDF embeds them" is true (Type 3 + CID TrueType).

## 4. Round 2 (December corrected, tea → plum `#6b3f69`)

Answer key: total 35,630; busiest December 3,330 (the trap); cold brew peak August 420; 44.6 (15,900) · 33.6 (11,960) · 14.8 (5,260) · 7.0 (2,510). All three meet it exactly (PDF text checked).

| | V | C | W |
| --- | --- | --- | --- |
| Dec bar to scale | 535 px = 0.1607 px/cup (same scale) | 495 px = 0.1486 | 495 px = 0.1486 |
| Busiest-month callout switched | Yes (December / 3,330 cups sold) | Yes | Yes (Dec axis label bolded automatically) |
| Tea plum everywhere | Yes (0 coral pixels left) | Yes | Yes (incl. header accent stripe) |
| Drift (PNG diff bands) | Only callouts, Dec bar and label, tea fills, share bar and labels | Only expected areas + source line "(Dec corrected)" | Only expected areas + Aug/Dec label weight + source line |
| Editability | **3**: no data binding, so the run recomputed the totals, shares and bar geometry outside Vixl and typed them in; no op to change a shape's fill, so 14 tea layers were deleted and re-added (new IDs); a `resize` with only height also scaled width (fixed in a second batch); re-export defaulted to a raster PDF until `pdf_content="vector"` was set | **5**: CSV row + one colour constant | **5**: CSV row + one colour constant (sed) |
| Revision | **5** | **5** | **5** |

Vixl-specific gaps seen: no chart or data-binding primitive (values are baked into geometry, so a data fix is manual), no arc/wedge shape (no pie or donut), no in-place fill change for shapes, a resize side effect, a PDF export that defaults to raster, and SVG text exported as outlines.
