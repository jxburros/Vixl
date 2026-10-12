# T01 · A picture: judge notes

Judges: claude-opus-5-5 subagents. Lanes run: V, C, W (claude).

- **V** was re-run on **Vixl 0.26.0** and judged on **2026-10-12**. Blind codes: round 1 US2Y, round 2 BUHM. Effort: round 1 3.5 min / 17 tool calls, round 2 2.8 min / 21 tool calls, no nudges.
- **C** and **W** were run and judged on **2026-10-05**; their scores and notes below are unchanged. Old blind codes: C=AIL8 (r2 OZMM), W=RX4F (r2 UYTE).

Only sources are committed for C and W, so on 2026-10-12 they were regenerated in a scratch copy for side-by-side viewing (nothing was written into their run folders). C's `make_picture.py` (both rounds) rebuilt cleanly to 2400×1600 RGB. W still cannot be regenerated: `render.py` reads `picture.svg`, which is in no commit, so W stands on its 2026-10-05 judging only.

## 1. Blind scores (written before opening key.csv)

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| US2Y | V r1 (2026-10-12) | 4 | 4 | Clean dusk poster: a tall striped lighthouse with gallery and glowing lantern on a faceted rocky point (left), 2 boats, 10 five-point stars, smooth navy-to-mauve-to-amber sky. The beam points right and angles down, but its lower edge ends at y 1010 on the right edge, 40 px above the sea (y 1050): it never lies on the water. It reads mauve-grey rather than golden. |
| BUHM | V r2 (2026-10-12) | 4 | 4 | Night, lighthouse on the right, beam sweeping left and clearly brighter, 3 boats. Beam is still all sky and flat grey-white; the amber horizon line and amber wakes are left over from dusk (disclosed). |
| UA7U | C r1 (regenerated) | 5 | 4 | The beam's lower edge reaches the sea on the right. 2 boats with reflections, 14 stars. Heavy dark foreground cliff; sun halo bands. Matches the recorded 5/4. |
| UMQ5 | C r2 (regenerated) | 4 | 3 | Cross-check only: night with the sun and its halo still up, whole scene mirrored. Same as the 2026-10-06 cross-check; C's recorded scores are not changed. |
| W4HR | old V r1 (0.20.0, 2026-10-06) | 4 | 4 | Superseded by US2Y. 13 stars, keeper's house; beam level and well above the horizon, greyish. |
| 5J7W | old V r1 (0.18.0, 2026-10-05) | 4 | 4 | Superseded. Beam angled up into the sky toward the top-right corner. |

## 2. Hard checks (round 1)

Sources: `inspect_outputs.py` facts, a visual count on the full-resolution PNGs, and for V the layer list from `vixl layers` and `vixl check` on scratch copies of `picture.vixl`. A `vixl render` of both `.vixl` files is pixel-identical to the delivered PNGs (max difference 0).

| Check | V (0.26.0) | C | W |
| --- | --- | --- | --- |
| `picture.png` 2400×1600 RGB | PASS (exported RGB with `alpha=flatten`) | PASS | PASS |
| Exactly two sailboats | PASS (`sailboat-1`, `sailboat-2` groups) | PASS | PASS |
| Lighthouse left half; beam sweeps right across the sea | PASS* (lighthouse group x 345–515, rocks x ≤ 1256; beam reaches the right edge, angled down, lower edge 40 px above the sea) | PASS (beam lower edge crosses the horizon) | PASS (beam slopes down to meet the sea at the right edge) |
| ≥ 5 stars | PASS (10 `star` shapes) | PASS (14) | PASS (10 dots) |
| No text, letters or logos | PASS (0 text layers) | PASS | PASS |
| Flat: no outlines, no photo texture | PASS (no strokes, no effects, all blends normal; only sky/sea/glows are smooth gradients) | PASS | PASS |
| **Total** | **6/6** | **6/6** | **6/6** |

\* Borderline, judged as in the 0.18.0 and 0.20.0 runs: the beam points across the sea's span and now gets close to the horizon, but never overlaps the water. It costs a fidelity point.

## 3. Report honesty

- **V (0.26.0): yes.** r1: layer count (54), 10 stars, beam opacities 0.16/0.20, lighthouse x 345–515, boat extents 1480–1610 and 1960–2136, the RGB export and both sky samples ((1200,5) = (11,22,57), (1200,1045) = (244,174,76)) match the files. It states plainly that the beam ends above the horizon. r2: 60 layers, beam 0.30/0.42 with `#fff4d0`, lighthouse at x 1885, rocks from x 1320, boats moved to x 790 and 264, headland at x 0–760, the four shimmer x positions, the third boat's box and both sky samples all match. Two slips:
  - `horizon-glow` was also mirrored (x 1000 → −400); the report mentions only its recolour.
  - It says the suite's `property` rule "did not honour a tolerance for `x`". Not reproduced: `expected: 1800, tolerance: 100` passes for x 1885 and `tolerance: 10` fails, both through `suite-set`. What is true is that `property` has no `minimum`/`maximum` range form.
  - Both rounds' "beam reaches the edge" suite rules are vacuous: they are `ink` rules over the opaque sky with no `background`, and the r1 suite still passes 7/7 with both beam layers deleted. The reports' "all rules pass" is literally true.
- **C: yes.** It reports 14 stars, the beam geometry, and the halo bands near the sun, all accurately.
- **W: yes.** It reports 10 dot stars, the beam meeting the sea only at the right, and the RGB conversion.

## 4. Round 2 (night, lighthouse to the right half, beam left, third boat, keep everything else)

All three made the sky a darker gradient, made the beam brighter, put the lighthouse in the right half with the beam sweeping left, and have 3 boats. Stars are at identical positions in all three (V: identical star boxes and a pixel diff that is zero on every star; C and W by overlay on 2026-10-05).

V (0.26.0) detail: the whole revision is one atomic 29-operation batch on the round-1 layers, plus renames and a suite update. Sky stops edited in place (y 300: (38,43,87) → (7,14,44); horizon (244,174,76) → (45,58,106)); beam opacity 0.16/0.20 → 0.30/0.42 and fill `#ffe9b0` → `#fff4d0`, normal blend (core pixel (157,127,126) → (157,155,149)); 10 path layers mirrored with one `flip` and moved; lighthouse group moved, not flipped; `sailboat-3` is a `duplicate` of `sailboat-1` scaled 0.7. Layer order is unchanged, no layer was removed, and the sea gradient is unchanged (pixel-identical where nothing sits on it).

| | V (0.26.0) | C | W |
| --- | --- | --- | --- |
| Original 2 boats kept in place | NO: both moved left (−690 and −1696 px), same waterlines, not flipped | NO: both mirrored to the left | Near boat kept at the same spot; far boat mirrored (it would have been hidden by the rocks) |
| Shoreline / headland kept | NO: far headland flipped to the left | NO: both headlands mirrored | YES (now partly behind the rocks) |
| Sun | None in r1, so nothing to fix | Kept but mirrored | Removed. Not requested, but sensible; disclosed |
| Other drift | Shimmer strokes and horizon glow mirrored; amber horizon band and wakes left at night | Waves, foam and reflections mirrored | Sea rocks and waves left in place |
| Editability | 4: all edits in place in one batch with no rejected operations and no `allow_crop` workarounds; the drift is the agent's choice, not forced by the tool | 4: a mirror helper, a clean script edit, but the approach mirrors everything | 5: one `<g transform>` plus string replacements |
| Revision | 3: right, but both original boats, the headland, shimmer and glow moved | 3: right, but large collateral drift | 4: right, with minor disclosed drift |

All three disclosed their drift in round-2 REPORT.md (V missed only the glow). The answer key says the two original boats and the shoreline should stay where they were. Only W mostly honoured that.

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 6/6 | 6/6 | 6/6 |
| Fidelity / craft | 4 / 4 | 4 / 4 | 4 / 4 |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 3 | 4 / 3 | 4 / 3 |

The scores did not move; the process got cleaner. In 0.26.0 every path layer ends up in a tight box. The agent drew paths in absolute coordinates, then spent a 22-operation batch re-basing them and an ungroup/regroup batch so position rules could measure them. As a result `vixl check` covers 54/54 (r2 60/60) layers and now labels the count `layers_checked`/`layers_total`. The 0.20.0 skip of full-canvas path layers is also gone (a full-canvas path box is checked in a fresh document), and moving the boats needed no `allow_crop`. Round 2 went through in one batch with no rejected operations (0.20.0 had one `opacity`-on-`shape` rejection). The picture itself is a sideways step: the beam now angles down to 40 px above the horizon instead of running level high in the sky, but it still never touches the water and still reads grey. There are 10 stars instead of 13 and no keeper's house; the lighthouse is taller and has a gallery. The round-2 strategy is unchanged: the agent mirrored the boats and headland out of the rocks' way instead of leaving them in place, so revision stays at 3.

Vixl gaps reproduced on 0.26.0 (scratch documents only):

- **`relation` with `bounds: "ink"` measures a path shape's box, not its drawn path.** A path `M 1500 1000 … Z` added with no box gets box [0, 0, 1600, 1100]. "right-of a rectangle at x 200–400" then fails with `positions: ["overlapping", "contains"]` for both `box` and `ink`, on the path and on its group, although the rendered ink is at x 1501–1698. (`spatial.canvas_boxes` uses `render.extent` for non-text layers.) This is why the r1 agent re-based every path.
- **A path drawn in absolute coordinates gets an origin-anchored box,** and a group of such paths inherits it ([0, 0, 1700, 1100]). `vixl check` then warns that the group "extends outside the safe area" although its ink sits well inside.
- **`suite-set` with an unsupported rule key returns only `{"error": "invalid_operation", "message": "Unknown check field"}`.** It has no `field`, no key name and no suggestions (`assurance.py:67`). For example, `property` with `minimum` fails this way; the rule only accepts `expected`/`tolerance`.
- **An `ink` rule over an opaque background without `background` always measures 1.0.** Vixl gives no warning, so both rounds' beam rules pass with the beam deleted.
- Not reproduced: the r2 report's claim that `property` ignores `tolerance` on `x`.
