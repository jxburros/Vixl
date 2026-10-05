# T10 · Photo correction — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes: V (Vixl), C (Python/OpenCV), T (ImageMagick + ffmpeg).

## 1. Blind scores (written before opening key.csv)

Round 1 codes were picked out by caption text ("golden hour"). Round 2 copies (38AH, NMW2, N0QS) were looked at but not scored blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| MBPP | 5 | 4 | Level, warm natural colour, noise cleanly reduced, crops right. The bold sans caption is a bit heavy and generic. |
| RJG8 | 4 | 4 | Level, warm colour, elegant serif caption. Visible grain and blotches remain in the sky and rocks: noise under-reduced. |
| YO0V | 4 | 3 | Level. Colour drifts grey-cyan: water desaturated grey-blue, sky washed yellow, shadows lifted. Speckle remains on the figure and rocks. |

Key: MBPP = T, RJG8 = V, YO0V = C.

## 2. Hard checks (round 1)

Measurements: horizon angle from a robust line fit to the sky/sea edge (x 40–97 %); dark components counted in the sky band; high-pass noise σ in flat patches; md5 of the fixture.

| Check | V | C | T |
| --- | --- | --- | --- |
| Horizon level within 0.3° (raw measures 2.21°) | PASS 0.00° | PASS 0.00° | PASS 0.01° |
| No rotation wedges in corners | PASS (corners checked at 3×) | PASS | PASS |
| Natural exposure/colour; noise reduced without smearing | PASS: warm and natural. Sky noise 4.0 → 1.5; grain still visible. | **FAIL**: gray-world WB pushed green up (mean G 84.5 vs 53–59 for V/T). Water grey-cyan, sky yellow-washed, shadow noise amplified on rocks (σ 6.6 vs raw 3.2). | PASS: warm and natural, sky noise 0.7, birds sharp. |
| Same scene: 4 birds, same figure and lighthouse | PASS: 4 birds | PASS: 4 birds | PASS: 4 birds |
| Instagram 1080×1350; caption 1600×900, exact text, readable | PASS | PASS | PASS |
| Original untouched (md5 0adf9cb2… = explorations source) | PASS | PASS | PASS |
| **Total** | **6/6** | **5/6** | **6/6** |

Sizes of `coast-edited.jpg`: V 1562×1007, T 1558×1004, C 1509×1005. C kept 3:2 and so cropped about 50 px more width; V and T used the maximum-area crop. All three Instagram crops leave out the lighthouse to frame the sun and the figure, and all three reports say so.

Expected scene colour, reconstructed by inverting the synthetic faults: sky about (57,46,96), sea about (70,50,63). Measured sky: V (49,31,95), T (52,36,98), C (56,53,127). C's green and blue are too high.

## 3. Report honesty

- **V — yes.** The crop, rotation (−2.22°), stack and caption specs match. It says plainly that Vixl has no denoise filter and that grain remains.
- **C — partly.** The process is described accurately, but it diagnoses the raw cast as "magenta/red, green suppressed". The fault is a green cast, and acting on that diagnosis made the output worse. It also says residual speckle is "only visible when brightened strongly", but it shows on the rocks and figure at normal viewing.
- **T — yes.** The output claims are all correct. One input statistic is misquoted ("mean B 51 > mean R 42"; the actual means are R 62, G 42, B 50), but the deliverables are unaffected.

## 4. Round 2 ("warmer, slightly less contrast, caption 'Port Ellery, October evening', all three files")

| | V | C | T |
| --- | --- | --- | --- |
| Method | Added live `temperature` 250 and `contrast` −10 effects to the existing tone adjustment layer in a copy of `coast-edit.vixl`. Re-exported `_master.png` and swapped it into the Instagram and caption docs with `replace-contents`. Changed the caption with `text-set`. | Added constants (WARM 1.04/1.01/0.94, CONTRAST 0.90) and the caption string to the copied script, then re-ran it from the raw. | Added WARM gains, `+sigmoidal-contrast 2x50%` and a CAPTION variable to the copied build.sh, then re-ran it from the raw. |
| Compounding damage | None: rebuilt from the source photo layer, noise σ 1.48 → 1.41 | None: rebuilt from the raw | None: rebuilt from the raw |
| Geometry drift r1 → r2 (phase correlation) | ≤0.2 px, same sizes | ≤0.2 px | ≤0.1 px |
| Warmer / less contrast measured | B −7, R +2; luma σ 50 → 45 | R +3, B −6; σ 57 → 51 | R +3.6, B −1; σ −2.6 % (very slight but present) |
| Caption | Correct, same style and position | Correct; "evening" runs over the dark rock but stays readable | Correct |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 5 |

Vixl note: the derived docs import a flattened `_master.png`, not the live correction document, so a grade change needs a manual re-export and `replace-contents` in each derived doc. The agent handled this cleanly, in about 27 tool calls against 7–8 for C and T.
