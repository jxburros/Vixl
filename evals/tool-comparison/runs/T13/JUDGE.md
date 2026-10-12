# T13 · Pixel-art sprite — judge notes

Lanes: V (Vixl pixel-art and frames), C (Pillow/NumPy).

- **V:** re-run on Vixl 0.26.0, judged 2026-10-12 by a claude-opus-5-5 subagent. Round 1 took
  3.4 min and 18 tool calls; round 2 took 2.8 min and 25 tool calls.
- **C:** run and judged on 2026-10-05. Its scores and notes below are unchanged. For the
  2026-10-12 blind look, C's deliverables (round 1 and round 2) were regenerated from the committed
  `make_keeper.py` sources in a scratch copy outside the repo. Both ran cleanly and match the
  2026-10-05 facts (13 colours, feet on row 31).

## 1. Blind scores (before key)

### 2026-10-12 (V re-run on 0.26.0; C regenerated)

Round-1 codes are the 192 px sheets. 71YF and Q5QK are the 256 px round-2 sheets with the wave
frames, and were not scored blind. Sheets were viewed at 8× nearest on a flat background; every
GIF frame is an exact 8× of its sheet cell (section 2), so the sheets stand for the GIFs.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| AADI | 5 | 4 | A large keeper: a shaded yellow hood and coat, a face with a nose, navy trousers, dark boots and a round lit lantern that swings in the walk. The stride reads. The hood and coat are one big mass. |
| GCBN | 5 | 4 | A slimmer keeper in a tall yellow hooded coat with a white beard, crisp outlines and a rectangular lantern. The walk reads, with the rear foot lifted in the passing frames. The hood is a tall slab. |

Key: AADI = C (regenerated), GCBN = V (0.26.0). The blind score for C matches its stored 5/4.

### 2026-10-06 (V re-run; C regenerated)

Round-1 codes are the 192 px sheets. 8BFZ and B0XB are the 256 px round-2 sheets with the wave
frames, and were not scored blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2LBP | 5 | 4 | A large keeper that fills the frame: a shaded yellow hood and coat, a face with a nose, navy trousers, brown boots and a lit lantern. The lantern swings in the walk, the stride legs read and the idle bob shows. The hood and coat are one big mass. |
| Y27T | 5 | 4 | A smaller, clean keeper with crisp outlines. The walk legs read, the lantern is round with a glow, and the character uses less of the frame. |

Key: 2LBP = V (0.20.0), Y27T = C (regenerated).

### 2026-10-05 (original run)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2FRK | 5 | 4 | Clear keeper in a yellow hooded coat with dark boots and a lantern. Good shading and outline. The walk legs read (frame 4 is a bit muddled); the idle bob is subtle. |
| GSSV | 5 | 3 | Reads as a keeper, but the coat is one blobby hood mass with a boxed face. The lantern is nice, with a glow. The walk legs read but are small. |

Key: 2FRK = C, GSSV = V (0.18.0).

## 2. Hard checks (round 1)

Method: the inspector, plus a script that compares every GIF frame with an 8× nearest-neighbour
upscale of its sheet cell (using the JSON rectangles), checks that GIF colours are a subset of the
sheet's, and finds the lowest opaque row in each frame.

| Check | V (0.26.0, 2026-10-12) | C (2026-10-05) |
| --- | --- | --- |
| Sheet 192×32 RGBA, partial_alpha 0, ≤16 colours | PASS (13 opaque colours, alpha only {0,255}) | PASS (13) |
| idle 2×400 ms, walk 4×120 ms, 256², loop=0 | PASS | PASS |
| GIF colours ≤ sheet (no smoothing) | PASS (idle 12, walk 13, subsets of the sheet; every frame equals the exact 8× upscale, 0 px differ) | PASS (13, exact) |
| JSON: six frames, correct rectangles and durations | PASS (x 0–160 step 32, 32×32, 400/400/120×4; plus sheet size, `loop` and an `animations` map) | PASS (plus an `animations` map) |
| Same feet row in every frame; walk reads as a walk | PASS (lowest row 30 in all frames; contact/passing cycle with a 1 px body bob and lantern swing). The two contact frames share one silhouette, as do the two passing frames; only the near/far leg colours swap (12 and 11 px differ) | PASS (lowest row 31 in all frames; contact/passing cycle) |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V (0.26.0) — yes.** Every checkable claim holds: 192×32 RGBA, alpha {0,255}, 13 opaque
  colours, lowest row 30 in every frame, top row 4 or 5 with the bob, character within x 10–23,
  the idle2 lantern shift (1 px left, 1 px down), GIF timings and loop 0, and 0-pixel differences
  against the 8× upscale. The sheet and wave GIF re-export byte-identically from the committed
  `round2/keeper.vixl` in a scratch copy. It does not say that the contact frames share one
  outline (the 0.20.0 report did), but "legs swapped" is accurate. `round2/REPORT.md` also
  matches: the three remaps are exactly #f4c430→#d63a2f (633 px), #c98d1a→#962231 (78 px) and
  #fff08a→#f2765e (48 px), the map is one-to-one, alpha of the first six frames is identical to
  round 1, the wave hand reaches y 1 and x 27, and the `.vixl` holds layers `arm-wave1`/`arm-wave2`
  under `upper`, frames wave1/wave2 and the `wave` animation.
- **C — yes.** Every claim was verified.

## 4. Round 2 (red raincoat; 2-frame wave at 250 ms; sheet 256×32; JSON updated; keeper-wave.gif)

| | V (0.26.0, 2026-10-12) | C (2026-10-05) |
| --- | --- | --- |
| Recolour | One `frames-edit` (scene: true) wrapping `pixel-palette` on the `upper` layer recoloured all six saved frames and the scene | 3 palette constants |
| First 6 frames after the change | Alpha identical; only 3 colour remaps (yellow to red) | Alpha identical; only 3 colour remaps |
| Wave | Two raised-arm layers under `upper`, one shown per frame; each wave frame is idle1 plus the arm (50–51 px differ, all in x 21–27, y 1–13); the hand swings 2 px between frames, the lantern stays in the front hand. Reads. The hand stays inside the cell (top row 1), and the body does not bob | Far arm rises from behind the hood; the hand swings back and forth over the head and touches the top edge (row 0) in wave_2; reads |
| Sheet / JSON / GIF | 256×32; wave1 and wave2 at x 192/224, 250 ms; `animations.wave` (500 ms); wave GIF 2×250 ms, exact 8×; idle and walk GIFs re-exported red | Same, plus `animations.wave` |
| Process friction | None reported or seen | None |
| Editability / revision | 5 / 5 | 5 / 5 |

Vixl issues: none reproduced in this run. Both 0.20.0 issues are fixed in 0.26.0 (checked on a
scratch copy of `round2/keeper.vixl`):

- The sheet export result now reports `"size":[256,32]` plus `"frame_size":[32,32]` (and
  `[64,32]` for `--animation wave`), so the file size and the result agree.
- `pixel-art` now accepts a `width` that matches the rows (3 for 3-wide rows) and refuses only a
  mismatch, with a clear message ("Rows are 3x2, so width must be 3 (or omit it); got 4").

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 5/5 | 5/5 | 5/5 |
| Fidelity / craft | 5 / 3 (blobby hood mass, boxed face) | 5 / 4 (shaded hood, face with a nose, lantern swing, fills the frame) | 5 / 4 (bearded keeper, crisp outline, lantern swing; tall slab hood) |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 | 5 / 5 |

On 0.18.0 per-animation GIFs needed `cp` copies of the document and the round-2 recolour was
repeated per frame (29 ops), with one timeout. 0.20.0 fixed both (`vixl_export_animation(animation=…)`
and `frames-edit` with `scene: true`), leaving two small issues: the sheet export result reported
the frame size, and `pixel-art` refused any `width` with rows. 0.26.0 fixes both, and the run had no
friction at all (3.4 and 2.8 minutes). Scores are unchanged from 0.20.0: V ties C on every scored
column, and the remaining differences between runs are the agent's drawing, not the tool.
