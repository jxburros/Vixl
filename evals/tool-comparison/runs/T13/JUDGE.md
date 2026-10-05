# T13 · Pixel-art sprite — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes: V (Vixl pixel-art and frames), C (Pillow/NumPy).

## 1. Blind scores (before key)

Round 1 codes are the 192 px sheets. B21F and YYJN are the 256 px round-2 sheets with the wave frames.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2FRK | 5 | 4 | Clear keeper in a yellow hooded coat with dark boots and a lantern. Good shading and outline. The walk legs read (frame 4 is a bit muddled); the idle bob is subtle. |
| GSSV | 5 | 3 | Reads as a keeper, but the coat is one blobby hood mass with a boxed face. The lantern is nice, with a glow. The walk legs read but are small. |

Key: 2FRK = C, GSSV = V.

## 2. Hard checks (round 1)

Method: the inspector, plus a script that compares every GIF frame with an 8× nearest-neighbour upscale (np.kron) of its sheet frame and finds the lowest opaque row in each frame.

| Check | V | C |
| --- | --- | --- |
| Sheet 192×32 RGBA, partial_alpha 0, ≤16 colours | PASS (15 opaque colours, alpha only {0,255}) | PASS (13) |
| idle 2×400 ms, walk 4×120 ms, 256², loop=0 | PASS | PASS |
| GIF colours ≤ sheet (no smoothing) | PASS (13 and 14, subsets of the sheet; every frame equals the exact 8× upscale) | PASS (13, exact) |
| JSON: six frames, correct rectangles and durations | PASS | PASS (plus an `animations` map) |
| Same feet row in every frame; walk reads as a walk | PASS (lowest row 30 in all frames; contact/passing cycle) | PASS (lowest row 31 in all frames; contact/passing cycle) |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V — yes.** Its "bbox bottom = 31" is an exclusive bound and matches the measured last row of 30. It discloses the per-animation copy workaround.
- **C — yes.** Every claim was verified.

## 4. Round 2 (red raincoat; 2-frame wave at 250 ms; sheet 256×32; JSON updated; keeper-wave.gif)

| | V | C |
| --- | --- | --- |
| Recolour | `pixel-palette` on the `upper` layer, repeated for each of the 6 saved frames (frame-apply, pixel-palette, frame-save) in one 29-operation batch | 3 palette constants |
| First 6 frames after the change | Alpha identical; only 3 colour remaps (yellow to red) | Alpha identical; only 3 colour remaps |
| Wave | Far arm on new layers behind the body; the hand swings side to side; reads well | Far arm rises from behind the hood; the hand swings back and forth over the head; reads |
| Sheet / JSON / GIF | 256×32; wave1 and wave2 at x 192/224, 250 ms; wave GIF 2×250 ms, exact 8× | Same, plus `animations.wave` |
| Process friction | `animation-set` must list every saved frame, so three per-animation `cp` copies had to be rebuilt; one apply call timed out but its edit was saved | None |
| Editability / revision | 4 / 5 | 5 / 5 |

Vixl gaps seen: a document cannot export a subset of its frames as a separate GIF, because the animation order must list every saved frame. Saved frames are snapshots, so a palette change has to be reapplied and re-saved frame by frame. One MCP timeout.
