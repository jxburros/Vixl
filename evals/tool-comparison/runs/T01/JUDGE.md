# T01 · A picture: judge notes

Judges: claude-opus-5-5 subagents. Lanes run: V, C, W (claude).

- **V** was re-run on **Vixl 0.20.0** and judged on **2026-10-06**. Blind codes: round 1 W4HR, round 2 UTN5.
- **C** and **W** were run and judged on **2026-10-05**; their scores and notes below are unchanged. Old blind codes: C=AIL8 (r2 OZMM), W=RX4F (r2 UYTE).

Only sources are committed for C and W, so on 2026-10-06 they were regenerated in a scratch copy for side-by-side viewing. C's `make_picture.py` (both rounds) rebuilt cleanly. W could not be regenerated: `render.py` reads `picture.svg`, which was never committed, so W stands on its 2026-10-05 judging only.

## 1. Blind scores (written before opening key.csv)

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| W4HR | V r1 (2026-10-06) | 4 | 4 | Clean dusk poster: lighthouse with keeper's house on the left, 2 boats, 13 stars (8 five-point, 5 dots), smooth navy-to-amber sky. The beam points right but stays entirely in the sky (y 150–600 at the right edge; horizon at y 1000), and it reads greyish rather than golden. |
| UTN5 | V r2 (2026-10-06) | 4 | 4 | Night, lighthouse on the right, beam left and clearly brighter, 3 boats. Beam is still all sky, white-grey. Amber water glints and wakes left over from dusk. |
| AIL8 | C r1 (2026-10-05) | 5 | 4 | The beam angles down across the sea. 2 boats with reflections, 14 stars. The foreground cliff is a large, heavy dark mass, and the beam over the sun's halo looks a bit muddy. |
| RX4F | W r1 (2026-10-05) | 5 | 4 | The beam descends across the sea to the horizon. 2 boats, 10 dot stars, a keeper's cottage, a smooth gradient. Well balanced. |
| 5J7W | old V r1 (0.18.0, 2026-10-05) | 4 | 4 | Superseded by W4HR. Clean flat poster with 2 boats and 9 stars, but the beam angles up into the sky toward the top-right corner and never crosses the water. |

The 2026-10-06 blind set also held the regenerated C images (r1 DHMW, r2 KQCR). They were scored 4/4 and 4/3 as a cross-check only; C's recorded scores were not changed.

## 2. Hard checks (round 1)

Sources: `inspect_outputs.py` facts, a visual count on the full-resolution PNGs, and for V the layer list read from `lighthouse.vixl` (the `vixl render` of both `.vixl` files is pixel-identical to the delivered PNGs).

| Check | V (0.20.0) | C | W |
| --- | --- | --- | --- |
| `picture.png` 2400×1600 RGB | PASS (exported RGB directly with `alpha=flatten`) | PASS | PASS |
| Exactly two sailboats | PASS (`boat1-*`, `boat2-*`) | PASS | PASS |
| Lighthouse left half; beam sweeps right across the sea | PASS* (tower x 470–650, rocks x ≤ 1180; beam runs right to the edge but stays above the horizon) | PASS (beam lower edge crosses the horizon) | PASS (beam slopes down to meet the sea at the right edge) |
| ≥ 5 stars | PASS (13) | PASS (14) | PASS (10 dots) |
| No text, letters or logos | PASS (0 text layers) | PASS | PASS |
| Flat: no outlines, no photo texture | PASS (no strokes, no effects; only the lamp halo is a soft gradient) | PASS | PASS |
| **Total** | **6/6** | **6/6** | **6/6** |

\* Borderline, judged as in the 0.18.0 run: the beam points right over the sea's span but never overlaps the water. It costs a fidelity point.

## 3. Report honesty

- **V (0.20.0): yes.** Layer count (55, then 59), star count, beam opacities, rock extents and all five sky samples match the files exactly (r1 and r2). The r2 report lists every element it moved that the brief did not name. One loose phrase: r1 says the beam passes "over the sea", though it stays above the horizon; r2 states this correctly.
- **C: yes.** It reports 14 stars, the beam geometry, and the halo bands near the sun, all accurately.
- **W: yes.** It reports 10 dot stars, the beam meeting the sea only at the right, and the RGB conversion.

## 4. Round 2 (night, lighthouse to the right half, beam left, third boat, keep everything else)

All three made the sky a darker gradient, made the beam brighter, put the lighthouse in the right half with the beam sweeping left, and have 3 boats. Stars are at identical positions in all three (V checked per star box; C and W by overlay on 2026-10-05).

V (0.20.0) detail: sky stops edited in place (y 300: (31,42,92) → (7,14,45)); beam opacity 0.20/0.30 → 0.45/0.70 with screen blend (core pixel ~(136,126,125) → (214,208,194)); 13 full-canvas path layers mirrored with one `flip`, 12 box layers moved; 4 new `boat3-*` layers. Layer order and every other fill are unchanged, and the sea is pixel-identical where nothing sits on it.

| | V (0.20.0) | C | W |
| --- | --- | --- | --- |
| Original 2 boats kept in place | NO: both moved left (−700 and −1600 px), same waterlines | NO: both mirrored to the left | Near boat kept at the same spot; far boat mirrored (it would have been hidden by the rocks) |
| Shoreline / headland kept | NO: far headland flipped to the left | NO: both headlands mirrored | YES (now partly behind the rocks) |
| Sun | None in r1, so nothing to fix | Kept but mirrored | Removed. Not requested, but sensible; disclosed |
| Other drift | Glints and foam mirrored; amber glints/wakes left at night | Waves, foam and reflections mirrored | Sea rocks and waves left in place |
| Editability | 4: all edits in place on the round-1 layers; one batch rejected (`opacity` is not a `shape` field); moved full-canvas boat paths needed `allow_crop` to quiet the bounds check | 4: a mirror helper, a clean script edit, but the approach mirrors everything | 5: one `<g transform>` plus string replacements |
| Revision | 3: right, but both original boats, headland and glints moved | 3: right, but large collateral drift | 4: right, with minor disclosed drift |

All three disclosed every drift in their round-2 REPORT.md. The answer key says the two original boats and the shoreline should stay where they were. Only W mostly honoured that.

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 6/6 | 6/6 |
| Fidelity / craft | 4 / 4 | 4 / 4 |
| Report honest | yes | yes |
| Editability / revision | 4 / 3 | 4 / 3 |

- **Gone:** the PNG no longer needs flattening outside Vixl (`alpha=flatten` exports RGB). The round-2 gradient edit changed the existing `sky` layer in place; in 0.18.0 the first `target` gradient op added a new full-canvas layer. Round 1 uses no blur at all, so the flat-style check is cleaner.
- **Better:** 13 real star shapes instead of 9; a keeper's house; the beam is roughly level instead of angled up to the top-right corner. Mirroring the headland was one `flip` on 13 layers.
- **Same:** the beam still never overlaps the water (still PASS* and −1 fidelity), and on the dark sky it reads grey rather than golden. Round 2 still moved both original boats and the headland, so revision stays at 3.
- **New friction (0.20.0):**
  - `vixl check` reports `layers: 36` for a 55-layer document (43 for 59). `checks.py` treats any non-text layer whose box covers the canvas as background and skips it, so all 19 path shapes drawn on full-canvas boxes (tower, rocks, beam, boats) are left out of the overlap, contrast and bounds checks. The count is labelled `layers`, which looks like a bug.
  - Moving a full-canvas path layer moves its box off the canvas, so the bounds check flags drawn content that is fully inside. The agent had to mark six boat layers `allow_crop`.
  - Per the r1 report, editing `path` on an existing path layer by `target` warns "path is only drawn for shape 'path', not None", though the edit applies. Not reproduced here (MCP tools not used).
