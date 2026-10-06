# T13 · Pixel-art sprite — judge notes

Lanes: V (Vixl pixel-art and frames), C (Pillow/NumPy).

- **V:** re-run on Vixl 0.20.0, judged 2026-10-06 by a claude-opus-5-5 subagent.
- **C:** run and judged on 2026-10-05. Its scores and notes below are unchanged. For the
  2026-10-06 blind look, C's deliverables (round 1 and round 2) were regenerated from the committed
  `make_keeper.py` sources in a scratch copy outside the repo. Both ran cleanly and match the
  2026-10-05 facts (13 colours, feet on row 31).

## 1. Blind scores (before key)

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
upscale of its sheet frame (using the JSON rectangles), checks that GIF colours are a subset of the
sheet's, and finds the lowest opaque row in each frame.

| Check | V (0.20.0, 2026-10-06) | C (2026-10-05) |
| --- | --- | --- |
| Sheet 192×32 RGBA, partial_alpha 0, ≤16 colours | PASS (13 opaque colours, alpha only {0,255}) | PASS (13) |
| idle 2×400 ms, walk 4×120 ms, 256², loop=0 | PASS | PASS |
| GIF colours ≤ sheet (no smoothing) | PASS (13 in each GIF, subsets of the sheet; every frame equals the exact 8× upscale) | PASS (13, exact) |
| JSON: six frames, correct rectangles and durations | PASS (plus sheet size, `loop` and an `animations` map) | PASS (plus an `animations` map) |
| Same feet row in every frame; walk reads as a walk | PASS (lowest row 30 in all frames; contact/passing cycle with lantern swing) | PASS (lowest row 31 in all frames; contact/passing cycle) |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V (0.20.0) — yes.** Every claim checks out: 192×32 RGBA, alpha {0,255}, the 13 listed hex
  colours, lowest row 30 in every frame, GIF timings and loop, and exact 8× matches. It honestly
  notes that the two contact frames share an outline (only leg colours swap) and that the sheet
  export result reported `"size":[32,32]`. `round2/REPORT.md` also matches: the three coat remaps
  are exactly #f4c430→#d23a2c, #c98e16→#8e1f1c and #fff09a→#f47a5e, nothing else changed, the alpha
  of the first six frames is identical to round 1, and the `.vixl` holds frames wave1/wave2 and the
  `wave` animation.
- **C — yes.** Every claim was verified.

## 4. Round 2 (red raincoat; 2-frame wave at 250 ms; sheet 256×32; JSON updated; keeper-wave.gif)

| | V (0.20.0, 2026-10-06) | C (2026-10-05) |
| --- | --- | --- |
| Recolour | One `frames-edit` (scene: true) wrapping `pixel-palette` on the `body` layer recoloured all six saved frames at once | 3 palette constants |
| First 6 frames after the change | Alpha identical; only 3 colour remaps (yellow to red) | Alpha identical; only 3 colour remaps |
| Wave | Two new raised far-arm layers behind the body; switching them gives the wave; lantern stays in the front hand. Reads. In wave1 the hand touches the frame's left edge, and in wave2 the arm outline runs along the hood outline | Far arm rises from behind the hood; the hand swings back and forth over the head; reads |
| Sheet / JSON / GIF | 256×32; wave1 and wave2 at x 192/224, 250 ms; `animations.wave` (500 ms); wave GIF 2×250 ms, exact 8×; idle and walk GIFs re-exported red | Same, plus `animations.wave` |
| Process friction | None reported or seen. Per-animation GIFs came straight from `vixl_export_animation(animation=…)`; no document copies | None |
| Editability / revision | 5 / 5 | 5 / 5 |

Vixl issues seen in this run (minor, none affected the files):

- The sheet export result reports `"size":[32,32]` (the frame size) although the written file is
  192×32 (round 1) and 256×32 (round 2). Both reports note it.
- `pixel-art` refuses `width` when `rows` are given, because the rows set the size. Round 2 notes
  this; it is strict rather than wrong, but a matching width could be accepted.

## 5. Changes since the Vixl 0.18.0 run

| | V on 0.18.0 (2026-10-05) | V on 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 5/5 | 5/5 |
| Fidelity / craft | 5 / 3 (blobby hood mass, boxed face) | 5 / 4 (shaded hood, face with a nose, lantern swing, fills the frame) |
| Colours | 15 on the sheet | 13 |
| Report honest | yes | yes |
| Per-animation GIFs | `animation-set` had to list every saved frame, so each GIF needed a `cp` copy of the document | `vixl_export_animation(animation=idle/walk/wave)` exports each named animation directly |
| Round-2 recolour | frame-apply / pixel-palette / frame-save repeated for all 6 frames (29 ops) plus rebuilding the copies | One `frames-edit` with `scene: true` |
| Timeouts | One apply call timed out (its edit was saved) | None |
| Editability / revision | 4 / 5 | 5 / 5 |

The 0.18.0 gaps (no subset-of-frames export, frames as snapshots that need per-frame re-edits) are
fixed in 0.20.0. V now ties C on every scored column. The craft gain likely owes as much to the
agent's drawing as to the tool.
