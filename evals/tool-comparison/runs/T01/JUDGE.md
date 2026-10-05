# T01 · A picture: judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes run: V, C, W (claude). Round-1 blind codes: V=5J7W, C=AIL8, W=RX4F. Round 2: L19P (V), OZMM (C), UYTE (W).

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 5J7W | 4 | 4 | Clean flat poster with 2 boats and 9 stars, but the beam angles up into the sky toward the top-right corner and never crosses the water. Beam edges are slightly soft. |
| AIL8 | 5 | 4 | The beam angles down across the sea. 2 boats with reflections, 14 stars. The foreground cliff is a large, heavy dark mass, and the beam over the sun's halo looks a bit muddy. |
| RX4F | 5 | 4 | The beam descends across the sea to the horizon. 2 boats, 10 dot stars, a keeper's cottage, a smooth gradient. Well balanced. |

## 2. Hard checks (round 1)

Sources: `inspect_outputs.py runs/T01`, plus a visual count on the full-resolution PNGs.

| Check | V | C | W |
| --- | --- | --- | --- |
| `picture.png` 2400×1600 RGB | PASS (RGB; the Vixl export was RGBA and was flattened with PIL) | PASS | PASS |
| Exactly two sailboats | PASS | PASS | PASS |
| Lighthouse left half; beam sweeps right across the sea | PASS* (tower x≈485–635; the beam points right but angles upward over the sky, not down over the water) | PASS (beam lower edge crosses the horizon) | PASS (beam slopes down to meet the sea at the right edge) |
| ≥ 5 stars | PASS (9) | PASS (14) | PASS (10 dots) |
| No text, letters or logos | PASS | PASS | PASS |
| Flat: no outlines, no photo texture | PASS (small blur on the glow and beam only) | PASS | PASS |
| **Total** | **6/6** | **6/6** | **6/6** |

\* Borderline. It passes because the beam does sweep right over the sea's span, but it cost a fidelity point.

## 3. Report honesty

- **V: yes.** The star count, layers, blur and screen blend all match. It discloses that the RGBA→RGB step was done with PIL outside Vixl. That step bends the V lane rule, which allows scripts only for reading and checking, and it was disclosed with a pixel-identity check.
- **C: yes.** It reports 14 stars, the beam geometry, and the halo bands near the sun, all accurately.
- **W: yes.** It reports 10 dot stars, the beam meeting the sea only at the right, and the RGB conversion.

## 4. Round 2 (night, lighthouse to the right half, beam left, third boat, keep everything else)

All three made the sky a darker gradient (mean luminance of the top 200 rows: V 43→26, C 35→11, W 36→9), made the beam brighter, put the lighthouse in the right half with the beam sweeping left, and have 3 boats. Stars are at identical positions in all three (checked by overlay).

| | V | C | W |
| --- | --- | --- | --- |
| Original 2 boats kept in place | NO: both mirrored to the left | NO: both mirrored to the left | Near boat kept at the same spot; far boat mirrored (it would have been hidden by the rocks) |
| Shoreline / headland kept | NO: headland flipped to the left | NO: both headlands mirrored | YES (now partly behind the rocks) |
| Sun | Kept but mirrored. A dusk sun in a night scene | Kept but mirrored | Removed. Not requested, but sensible; disclosed |
| Other drift | Waves and glints mirrored; sea not darkened | Waves, foam and reflections mirrored | Sea rocks and waves left in place |
| Editability | 4: layer ops in place; the first gradient `target` op added a new full-canvas layer instead of editing, and was fixed | 4: a mirror helper, a clean script edit, but the approach mirrors everything | 5: one `<g transform>` plus string replacements |
| Revision | 3: right, but large collateral drift | 3: right, but large collateral drift | 4: right, with minor disclosed drift |

All three disclosed every drift in their round-2 REPORT.md. The answer key says the two original boats and the shoreline should stay where they were. Only W mostly honoured that.
