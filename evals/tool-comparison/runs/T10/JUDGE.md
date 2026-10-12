# T10 · Photo correction — judge notes

Lanes: V (Vixl), C (Python/OpenCV), T (ImageMagick + ffmpeg).

- **V** was re-run on Vixl 0.26.0 and judged on 2026-10-12 by a claude-opus-5-5 subagent. Round 1 took 4.6 min (43 tool calls), round 2 took 2.1 min (23 tool calls).
- **C and T** were run and judged on 2026-10-05. Their scores and notes below are unchanged.
- For the 2026-10-12 blind pass, the C and T deliverables (rounds 1 and 2) were regenerated again from their committed sources (`edit_coast.py`, `build.sh`) in a scratch copy outside the repo, with the fixture placed so the scripts' relative paths resolved unchanged. Both regenerated without errors (ImageMagick `convert` and ffmpeg are installed here), and the regenerated files match the earlier facts (sizes, C mean G 84.5).

## 1. Blind scores (written before opening key.csv)

### 2026-10-12 pass (all six runs, both rounds)

Output sizes give the lane away (C 1509×1005, T 1558×1004, V 1512×1008), so this pass is only partly blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| B0T6 | 4 | 4 | Level, no wedges, 4 birds, green cast gone. Grain is now mostly gone (high-pass 1.07 against raw 3.9), birds sharp. Still darker than the reconstructed scene with a magenta lean: sea (40,26,46) against about (66,49,62), mid-sky green 46 against 70; rocks crushed to (5,2,8); the sun core is a neutral grey-white (236,236,233). Small Libre Baskerville caption with a soft radial scrim: elegant and readable. |
| 07R6 | 4 | 4 | A warmer, softer version of B0T6. Shadows lift to a neutral (12,8,14); the sun core dulls to (221,214,201). Caption "Port Ellery, October evening". |
| SDB1 | 5 | 4 | Colour closest to the reconstructed scene, clean denoise (0.58). Bold sans caption a bit heavy. |
| 0ZZ4 | 5 | 4 | Same as SDB1, slightly warmer. Caption "October evening". |
| PTWC | 4 | 3 | Cyan-white sun, yellow-green band at the horizon, water washed grey-blue. |
| NT2D | 4 | 3 | Same look as PTWC. Caption "October evening". |

Key: B0T6 = V round 1, 07R6 = V round 2, SDB1 = T, 0ZZ4 = T round 2, PTWC = C, NT2D = C round 2.

The blind scores for C (4/3) and T (5/4) match the 2026-10-05 and 2026-10-06 scores, so the three passes are consistent.

### 2026-10-06 pass (V on 0.20.0, now superseded)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| Y8X0 | 4 | 4 | (V 0.20.0) Level, 4 birds, about 20% darker than the scene, rocks crushed, residual grain (1.6). Serif caption. |
| S48S | 4 | 3 | (V 0.20.0 round 2) Warmer and flatter; sun dulls, shadows turn red-brown (15,7,7). |
| ACJU / KAM7 | 5 | 4 | T rounds 1 and 2. |
| N46Y / 5VRH | 4 | 3 | C rounds 1 and 2. |

### 2026-10-05 pass (C and T scores still stand)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| MBPP | 5 | 4 | Level, warm natural colour, noise cleanly reduced, crops right. The bold sans caption is a bit heavy and generic. |
| RJG8 | 4 | 4 | (V on Vixl 0.18.0, now superseded) Level, warm colour, elegant serif caption. Visible grain and blotches remain in the sky and rocks: noise under-reduced. |
| YO0V | 4 | 3 | Level. Colour drifts grey-cyan: water desaturated grey-blue, sky washed yellow, shadows lifted. Speckle remains on the figure and rocks. |

Key: MBPP = T, RJG8 = V (0.18.0), YO0V = C.

## 2. Hard checks (round 1)

How it was measured:
- **Horizon:** a robust line fit to the sky/sea edge (x 40–97 %).
- **Wedges:** corner and edge pixels compared with the rows and columns 5 px inside; the crop rectangle tested against the rotated frame.
- **Noise:** high-pass σ (luma minus a 5 px median) in a flat sky patch (x 70–95 %, y 3–12 %). On this measure the raw is 3.9 and the clean synthetic scene is 0.3, the same anchors as the earlier passes; T measures 0.58 here (0.7 in the earlier pass).
- **Scene:** the clean scene was rebuilt from `synth.py` without the faults. Phase correlation of V's output against it gives the origin (44.0, 28.5) with peak 0.92, exactly the offset the report states, so the geometry is a pure re-levelling.
- **Original file:** md5 of the fixture.

| Check | V (0.26.0, 2026-10-12) | C (2026-10-05) | T (2026-10-05) |
| --- | --- | --- | --- |
| Horizon level within 0.3° (raw measures 2.20°) | PASS: +0.02° (instagram +0.02°, caption 0.00°). The layer is rotated 357.8° (−2.2°); the answer key says 2.2°. | PASS 0.00° | PASS 0.01° |
| No rotation wedges in corners | PASS: 1512×1008 lies inside the rotated frame; no (0,0,0) pixel on any edge, corners match the pixels 5 px in (top-left (10,12,71) against sky (12,15,73)). | PASS | PASS |
| Natural exposure/colour; noise reduced without smearing | PASS: green cast gone, sun core neutral white (236,236,233), mean (91,56,74). Sky noise 3.9 → 1.07, birds sharp. Still a little dark with a magenta lean (sea (40,26,46) against about (66,49,62) for the clean scene), and the rocks crush to (5,2,8). | **FAIL**: gray-world WB pushed green up (mean G 84.5 vs 53–59 for V/T). Water grey-cyan, sky yellow-washed, shadow noise amplified on rocks (σ 6.6 vs raw 3.2). | PASS: warm and natural, sky noise 0.6–0.7, birds sharp. |
| Same scene: 4 birds, same figure and lighthouse | PASS: 4 birds, same figure and lighthouse. The embedded raw is the fixture (sha256 86ec0e7c…cc7a4c); only rotation and non-destructive effects are applied. | PASS: 4 birds | PASS: 4 birds |
| Instagram 1080×1350; caption 1600×900, exact text, readable | PASS: 1080×1350. The caption is 1600×900 with the exact text in Libre Baskerville 50 px, #fbf3e6, over a radial dark scrim at the bottom-left; contrast about 16.8:1 against the background under the text. | PASS | PASS |
| Original untouched (md5 0adf9cb2…) | PASS: md5 unchanged, no git change | PASS | PASS |
| **Total** | **6/6** | **5/6** | **6/6** |

Sizes of `coast-edited.jpg`: V 1512×1008, T 1558×1004, C 1509×1005. V and C kept 3:2 and so crop about 50 px more width than the maximum-area crop (1562×1007 is valid); V's report states the choice. T used the maximum-area crop.

All three Instagram crops leave out the lighthouse to frame the sun and the figure, and all three reports say so. V's Instagram file matches its stated crop (x 690–1496, full height, scaled 1.339×) of the edited photo to within 0.25 px; the caption card matches its crop (0, 80, 1512, 930) to within 0.16 px.

Expected scene colour, reconstructed from the synthetic scene:
- Sky top about (44,40,89); V (19,19,80), T (24,24,81).
- Sea about (66,49,62); V (40,26,46), T (47,33,50).
- Rock about (20,16,22); V (5,2,8), T (11,9,14).

V is again the darkest of the three in the sea and shadows, with the right hue in the sky.

## 3. Report honesty

- **V — yes.** Almost every number checks out against the files and the `.vixl` documents:
  - rotation −2.2° (stored 357.8), crop origin x 44 / y 28.5, canvas 1512×1008, re-measured slope 0.03° (measured 0.02°), horizon at y≈612;
  - effects in order: `denoise` 60/60, `white-balance` gains [1.06, 0.94, 1.04], `levels` 2/205, `curves` with the stated points;
  - raw mean (62,42,50) and sun core (179,200,177) (measured (179,198,172));
  - output mean (92,56,74) (measured (91.5,55.6,74.3)); the sun "(237,228,210)" holds for a ~40 px box (the 5 px core is neutral (236,236,233));
  - pure-black pixels only inside the figure (measured: 30 px, all in the figure's box);
  - link crops, scale factors, scrim stops, font, size, colour, position and box size of the caption; `vixl check` passes with two informational notes, as stated.

  One composition claim is wrong: the Instagram crop "keeps the horizon at roughly the 45 % line"; it sits at 61 % (y 820 of 1350). "No channel clips at 255" is true apart from 8 pixels. The report discloses the 1.34× upscale for the Instagram crop, the extra JPEG generation and the remaining softness. Round 2's table of means, R/B ratios and luma σ matches the files to the decimal.
- **C — partly.** The process is described accurately, but it diagnoses the raw cast as "magenta/red, green suppressed". The fault is a green cast, and acting on that diagnosis made the output worse. It also says residual speckle is "only visible when brightened strongly", but it shows on the rocks and figure at normal viewing.
- **T — yes.** The output claims are all correct. One input statistic is misquoted ("mean B 51 > mean R 42"; the actual means are R 62, G 42, B 50), but the deliverables are unaffected.

## 4. Round 2 ("warmer, slightly less contrast, caption 'Port Ellery, October evening', all three files")

| | V (0.26.0, 2026-10-12) | C (2026-10-05) | T (2026-10-05) |
| --- | --- | --- | --- |
| Method | Copied the three `.vixl` files into `round2/`; the relative `link` sources then point at `round2/coast.vixl`. Appended live `temperature` 22 and `contrast` −12 to the photo layer after the round-1 stack. Ran `link-refresh` in both derived documents (crops unchanged), `text-set` on the caption and updated the caption test suite's text rule. Exported with `vixl_export_batch`. | Added constants (WARM 1.04/1.01/0.94, CONTRAST 0.90) and the caption string to the copied script, then re-ran it from the raw. | Added WARM gains, `+sigmoidal-contrast 2x50%` and a CAPTION variable to the copied build.sh, then re-ran it from the raw. |
| Compounding damage | None: re-rendered from the embedded raw. Noise 1.07 → 0.95. | None: rebuilt from the raw | None: rebuilt from the raw |
| Geometry drift r1 → r2 (phase correlation) | ≤0.002 px for the edited and Instagram files, ≤0.12 px for the caption card (the changed text lowers the peak); same sizes | ≤0.2 px | ≤0.1 px |
| Warmer / less contrast measured | R/B 1.232 → 1.294 (mean R −2, B −5). Luma σ 55.9 → 49.6 (−11 %). Shadows lift to a neutral (12,8,14) with no colour cast; the sun core dims from (236,236,233) to (221,214,201) and p99 red drops 238 → 222. | R +3, B −6; σ 57 → 51 | R +3.6, B −1; σ −2.6 % (very slight but present) |
| Caption | Correct, same font, size, colour and position. The line is now 728 px wide. Contrast about 16.6:1. | Correct; "evening" runs over the dark rock but stays readable | Correct |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 5 |

V scores 5 for revision: everything asked for is done and nothing moved. The dimmer sun is the ordinary side effect of a contrast cut around the mean, and the report states it ("the brightest highlight drops from 255 to 232"). The red-brown shadows of the 0.20.0 round 2 are gone because `temperature` is now a multiplicative gain.

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05, RJG8) | 0.20.0 (2026-10-06, Y8X0 / S48S) | 0.26.0 (2026-10-12, B0T6 / 07R6) |
| --- | --- | --- | --- |
| Hard checks | 6/6 | 6/6 | 6/6 |
| Fidelity / craft | 4 / 4 | 4 / 4 | 4 / 4 |
| Report honest | yes | yes | yes (one wrong composition claim: horizon at "45 %", actually 61 %) |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 5 |
| Effort (r1 / r2 minutes) | not recorded | 5.0 / 2.1 | 4.6 / 2.1 (43 / 23 tool calls) |
| Denoise | No denoise filter; blur 1.4 + sharpen. Sky noise 4.0 → 1.5 | `denoise` 90/90, but effects ran after rotation. Sky noise 3.9 → 1.6 | `denoise` 60/60, effects now run in the layer's own frame before rotation. Sky noise 3.9 → 1.07 |
| White balance | Tone adjustment layer | 2×2×2 LUT `wb-green-cast` (G ×0.9); `tint` rejected as additive | `white-balance` effect with gains [1.06, 0.94, 1.04] |
| Edited size | 1562×1007 | 1556×1002 | 1512×1008 (kept 3:2) |
| Round 2 grade | Temperature/contrast on a tone layer, re-export swapped into derived documents | `temperature` 250 (additive; shadows red-brown), `contrast` −12, links repointed | `temperature` 22 (multiplicative; shadows neutral), `contrast` −12, links refreshed |

The three product issues the 0.20.0 judge reported are fixed (Vixl 0.21.0, see section 6), and this run uses each fix: a real `white-balance` effect replaces the LUT workaround, `temperature` works at a sensible amount (22 instead of 250) without tinting the blacks, and `denoise` now runs before rotation, so sky noise falls to 1.07 at a lower strength (60 against 90). The visible result is cleaner than 0.20.0, but the scores do not move: V is still darker and more magenta than the reconstructed scene, the rocks still crush, and T is still cleaner (noise 0.58). A test render of V's own master at `denoise` 90/90 gives 0.72, so the remaining noise gap is the agent's choice of strength, not a Vixl limit.

## 6. Vixl product issues

### Fixed since the 0.20.0 run (verified on 0.26.0)

1. **`denoise` on a rotated layer.** Effects now run in the layer's own frame before flip, rotate and skew (`render.transform_layer_image`; CHANGELOG 0.21.0). Rendering V's master in a scratch copy: with only `denoise`, sky noise is 0.80 with the −2.2° rotation and 0.96 with rotation 0, so rotation no longer weakens it (under 0.20.0 it was 1.14 against 0.62).
2. **`temperature` scale.** It is now a multiplicative white-point shift along the blackbody locus (`render.channel_gains`): temperature 100 maps grey 128 to (145,125,103) and leaves black at 0; temperature 22 gives (131,127,122).
3. **`tint` scale.** Now matched to temperature and multiplicative: tint 100 maps grey 128 to (144,121,144), tint 10 to (129,127,129), black stays black.
4. **No channel-gain effect.** There is now `white-balance` with `gains` or a `neutral` colour; this run used it.

### Still open

1. **Tonal effects truncate instead of rounding, and quantise to 8 bits between effects.**
   - `render.apply_effect` ends with `np.uint8(np.clip(a, 0, 1) * 255)`, which floors. Each tonal effect (white-balance, temperature, tint, levels, curves, gamma, exposure …) therefore darkens by about half a level on average.
   - Evidence: `white-balance` gains [0.999]×3 shifts a 0–255 ramp by −1.00 on average (expected −0.13); gains [1.06, 0.94, 1.04] map grey 128 to (135,120,133) instead of (136,120,133).
   - V's round-1 stack (white-balance, levels, curves) plus round 2's `temperature`, run through `apply_effect`, ends about 2.0 levels darker on every channel than the same maths in float. The intermediate 8-bit steps also throw away precision before `levels` and `curves` stretch it.
2. **No help for levelling a photo.** There is no horizon or tilt measurement and no crop-to-valid-area option for a rotated layer (no `horizon`, `deskew` or photo `straighten` anywhere in `src/vixl`; `straighten` exists only for hand drawings). The agent fitted the horizon slope, checked for empty corners and measured noise with its own PIL scripts, as its report says.
