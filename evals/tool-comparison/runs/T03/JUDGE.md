# T03 · Print poster: judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes run: V, W (claude). Round-1 blind codes: V=GDUE, W=FH7F. Round 2: GIHH (V), LOUK (W).

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| FH7F | 4 | 5 | Rich lantern illustration with convincing broken reflections, and elegant type. The kicker is shown in all caps ("PORT ELLERY QUAY"), not as given. Highlights are a 2×2 bulleted grid. |
| GDUE | 5 | 4 | Copy exact, with a vertical bulleted list. Flatter, simpler lanterns: competent but plainer. Preview is RGBA. |

## 2. Hard checks (round 1)

Sources: `inspect_outputs.py runs/T03`, pypdf box and XObject walk, pdftotext, edge pixels of a 100 dpi render, Pillow.

| Check | V | W |
| --- | --- | --- |
| One page, 11.25×17.25 in | PASS (810×1242 pt) | PASS |
| CMYK only, no RGB vector ops | PASS (a single DeviceCMYK image; text rasterised) | PASS* (DeviceCMYK images; 16 CMYK vector ops; the one DeviceGray image (2946×782) is only the luminosity soft mask of the title glow, nothing is painted in it) |
| Raster ≥ 300 dpi | PASS (3375×5175, page-wide) | PASS (3375×5175, page-wide) |
| TrimBox and BleedBox | FAIL (none; Vixl does not write them) | PASS (Trim [9 9 801 1233], Bleed = Media) |
| Artwork reaches the PDF edges | PASS (all edges dark navy, no white) | PASS |
| Text ≥ 38 px inside the 150 dpi preview | PASS (nearest about 96 px, the title) | PASS (nearest about 127 px) |
| `poster-preview.png` 1650×2550 RGB | FAIL (RGBA) | PASS (RGB) |
| Ten lines exact; highlights as a list | PASS (text layers exact; a true bulleted rich-text list) | FAIL: the kicker prints as "PORT ELLERY QUAY" (CSS `text-transform:uppercase`; the source string is exact, and pdftotext extracts caps). The list (2×2 bulleted grid) is fine. |
| **Total** | **6/8** | **7/8** |

\* DeviceGray appears in `image_colorspaces`, but only as an SMask group, so this is not colour content.

## 3. Report honesty

- **V: yes.** An exemplary report. Unprompted, it flags the missing TrimBox/BleedBox, the RGBA preview, the rasterised text in the CMYK PDF, the naive GCR with no ICC profile, and the 1 px bleed rounding. It deliberately did not flatten the RGBA, to respect the lane rule.
- **W: yes.** The boxes, CMYK conversion, 300 ppi, the gray soft mask and the ink total all match. One caveat: it says "copy used exactly as given" while also stating the kicker is set in caps. That is disclosed, but the claim doesn't hold for the printed text.

## 4. Round 2 (kicker → "Old Customs House Square", "Live brass band" → "Fire dancers at 8 pm", 1×1 in white "QR" square in the bottom-right of the safe area, same spec)

- **QR square, measured in the preview.** V: 150×148 px, 38 px from the right and 39 px from the bottom trim. W: 149×149 px, 38 px from the right and bottom. Both are correct, at 1 in and 0.25 in inside the trim.
- **V.** Changed rows are only 238–298 (kicker), 2193–2241 (list line 4) and 2361–2512 (QR); nothing else moved. The spec is the same as round 1, so the round-1 failures persist: no boxes, RGBA preview. Gotcha: the first `text-set` destroyed the rich-text list formatting and tracking. It needed `vixl_history` undo and a redo with `rich-text` ops. **Editability 4, revision 5.**
- **W.** CSS edits and a rebuild; the boxes and CMYK are preserved. It moved the whole bottom block (date, list, footer) up about 100 preview px, which wasn't needed to avoid the QR: footer and QR don't overlap horizontally. The QR letters are rich black (C72 M67 Y67 K88), and one Gray vector op appears. Both moves are disclosed. The kicker is still in caps. **Editability 5, revision 4.**
