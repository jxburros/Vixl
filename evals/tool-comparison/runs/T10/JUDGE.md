# T10 · Photo correction — judge notes

Lanes: V (Vixl), C (Python/OpenCV), T (ImageMagick + ffmpeg).

- **V** was re-run on Vixl 0.20.0 and judged on 2026-10-06 by a claude-opus-5-5 subagent.
- **C and T** were run and judged on 2026-10-05. Their scores and notes below are unchanged.
- For the 2026-10-06 blind pass, the C and T deliverables (rounds 1 and 2) were regenerated from their committed sources (`edit_coast.py`, `build.sh`) in a scratch copy outside the repo. Only the fixture path was changed. Both regenerated without errors.

## 1. Blind scores (written before opening key.csv)

### 2026-10-06 pass (all six runs, both rounds)

Output sizes give the lane away (C 1509×1005, T 1558×1004, V 1556×1002), so this pass is only partly blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| Y8X0 | 4 | 4 | Level, no wedges, 4 birds. Colour is close to the reconstructed scene but about 20% darker, and the rocks are crushed to black. Visible residual grain: high-pass σ 1.6, against about 0.7 for the cleanest runs. The serif caption is the best of the set. |
| S48S | 4 | 3 | A warmer, flatter version of Y8X0. The sun core dulls to (219,207,202) and the deep shadows turn red-brown (15,7,7). Grain remains. Caption "October evening". |
| ACJU | 5 | 4 | Colour closest to the reconstructed scene, clean denoise. Bold sans caption. |
| KAM7 | 5 | 4 | Same as ACJU, slightly warmer. Caption "October evening". |
| N46Y | 4 | 3 | Cyan-white sun, yellow-green band at the horizon, water washed grey-blue. |
| 5VRH | 4 | 3 | Same look as N46Y. Caption "October evening". |

Key: Y8X0 = V round 1, S48S = V round 2, ACJU = T, KAM7 = T round 2, N46Y = C, 5VRH = C round 2.

The new blind scores for C (4/3) and T (5/4) match the 2026-10-05 scores, which suggests the two passes are consistent.

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
- **Wedges:** corners and edges inspected at 4× with auto-contrast.
- **Noise:** high-pass σ in a flat sky patch (x 70–95 %, y 3–12 %). On this measure the raw is 3.9 and the clean synthetic scene is 0.3.
- **Scene:** the clean scene was rebuilt from `synth.py` without the faults. Phase correlation of V's output against it gives a shift of 0.55 px with a strong peak, so the geometry is a pure re-levelling.
- **Original file:** md5 of the fixture.

| Check | V (0.20.0, 2026-10-06) | C (2026-10-05) | T (2026-10-05) |
| --- | --- | --- | --- |
| Horizon level within 0.3° (raw measures 2.22°) | PASS: −0.003°. The layer is rotated by −2.22°; the answer key says 2.2°. | PASS 0.00° | PASS 0.01° |
| No rotation wedges in corners | PASS: crop is 1556×1002, inside the 1562×1007 valid rectangle | PASS | PASS |
| Natural exposure/colour; noise reduced without smearing | PASS: warm and natural, with no green left (sun core about (235,230,229)). A little dark: mean (87,53,70) against about (107,71,82) for the clean scene. Sky noise 3.9 → 1.6, birds sharp, grain still visible. | **FAIL**: gray-world WB pushed green up (mean G 84.5 vs 53–59 for V/T). Water grey-cyan, sky yellow-washed, shadow noise amplified on rocks (σ 6.6 vs raw 3.2). | PASS: warm and natural, sky noise 0.7, birds sharp. |
| Same scene: 4 birds, same figure and lighthouse | PASS: 4 birds, same figure and lighthouse. The embedded raw is byte-identical to the fixture; only rotation and tonal effects are applied. | PASS: 4 birds | PASS: 4 birds |
| Instagram 1080×1350; caption 1600×900, exact text, readable | PASS: 1080×1350. The caption is 1600×900 with the exact text in DM Serif Display 64 px over a 0→55 % black gradient. | PASS | PASS |
| Original untouched (md5 0adf9cb2…) | PASS: md5 unchanged, no git change | PASS | PASS |
| **Total** | **6/6** | **5/6** | **6/6** |

Sizes of `coast-edited.jpg`: V 1556×1002, T 1558×1004, C 1509×1005. C kept 3:2 and so cropped about 50 px more width; V and T used the maximum-area crop.

All three Instagram crops leave out the lighthouse to frame the sun and the figure, and all three reports say so. V's Instagram crop (x 620–1422 of the edited photo) matches its stated box to within about 1 source pixel.

Expected scene colour, reconstructed from the synthetic scene:
- Sky top about (45,41,88); V (21,21,75), T (27,25,80).
- Sea about (85,58,67); V (55,34,51), T (63,41,54).

V is the darkest of the three but has the right hue.

## 3. Report honesty

- **V — yes.** Every number checked out against the files and the `.vixl` documents:
  - rotation 357.78 (−2.22°);
  - crop 1556×1002;
  - denoise luminance 90 / chroma 90;
  - LUT `wb-green-cast` with G ×0.9;
  - levels 3/195 and gamma 1.1;
  - mean RGB (88,53,70) (measured (87,53,70));
  - clipping under 0.001 % (measured 0.0006 %);
  - the link crops and caption spec.

  It says that faint grain remains. It also says it rejected `tint` because tint turned the blacks magenta, which the code confirms (see Vixl issues below).
- **C — partly.** The process is described accurately, but it diagnoses the raw cast as "magenta/red, green suppressed". The fault is a green cast, and acting on that diagnosis made the output worse. It also says residual speckle is "only visible when brightened strongly", but it shows on the rocks and figure at normal viewing.
- **T — yes.** The output claims are all correct. One input statistic is misquoted ("mean B 51 > mean R 42"; the actual means are R 62, G 42, B 50), but the deliverables are unaffected.

## 4. Round 2 ("warmer, slightly less contrast, caption 'Port Ellery, October evening', all three files")

| | V (0.20.0, 2026-10-06) | C (2026-10-05) | T (2026-10-05) |
| --- | --- | --- | --- |
| Method | Copied the three `.vixl` files into `round2/`. Appended live `temperature` 250 and `contrast` −12 effects to the photo layer of the master, after denoise/levels/gamma. Repointed the two `link` layers to the round-2 master; the crops are unchanged. Changed the caption with `text-set`. | Added constants (WARM 1.04/1.01/0.94, CONTRAST 0.90) and the caption string to the copied script, then re-ran it from the raw. | Added WARM gains, `+sigmoidal-contrast 2x50%` and a CAPTION variable to the copied build.sh, then re-ran it from the raw. |
| Compounding damage | None: re-rendered from the embedded raw (md5 unchanged). Noise σ 1.61 → 1.45. | None: rebuilt from the raw | None: rebuilt from the raw |
| Geometry drift r1 → r2 (phase correlation) | ≤0.02 px in all three files, same sizes | ≤0.2 px | ≤0.1 px |
| Warmer / less contrast measured | Mean R−B 17.8 → 27.3 (B −8, R +2). Luma σ 49 → 43 (−12 %). Side effects: shadows go from (3,2,7) to a red-brown (15,7,7), and p99 drops 195 → 178, so the sun dims. | R +3, B −6; σ 57 → 51 | R +3.6, B −1; σ −2.6 % (very slight but present) |
| Caption | Correct, same font, style and position. The line is now 798 px wide. | Correct; "evening" runs over the dark rock but stays readable | Correct |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 5 |

V scores 5 for revision: everything asked for is done, and nothing moved. The red-brown shadows come from Vixl's additive `temperature` effect (it adds red even to black), and the report says so ("warms the deepest shadows a little").

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05, RJG8) | 0.20.0 (2026-10-06, Y8X0 / S48S) |
| --- | --- | --- |
| Scores (hard, fid, craft, honest, edit, rev) | 6/6, 4, 4, yes, 5, 5 | 6/6, 4, 4, yes, 5, 5 (no change) |
| Denoise | No denoise filter; blur 1.4 + sharpen. Sky noise 4.0 → 1.5 | Real `denoise` effect (non-local means), 90/90. Sky noise 3.9 → 1.6, about the same, because of the effect-order issue below |
| White balance | Tone adjustment layer | 2×2×2 LUT `wb-green-cast` (G ×0.9) applied with `lookup` |
| Edited size | 1562×1007 | 1556×1002 (3 px safety margin per side) |
| Derived files | Imported a flattened `_master.png`. Round 2 needed a re-export plus `replace-contents` in each derived document (about 27 tool calls). | Live `link` layers to the master, with crops. Round 2 only repointed the links and changed one text layer. |

Net: the workflow is cleaner (live links, a real denoise effect, everything rebuilt from the untouched raw), but the visible result is about the same. V is still behind T on noise (1.6 against 0.7) and slightly dark.

## 6. Vixl product issues found

1. **`denoise` loses about half its effect on a rotated layer.**
   - `render.transform_layer_image` applies the layer's effects after it rotates the layer with bicubic resampling.
   - The resampling smooths and correlates the grain. `denoise` then estimates the noise from the image itself and sees less noise than is really there, so it smooths too little.
   - The same document gives sky noise 0.93 with rotation set to 0, and 1.63 with the −2.22° rotation.
   - `denoise` alone on the raw gives 0.62; on the rotated layer it gives 1.14.
   - This is why V's output keeps visible grain despite a strength of 90.
2. **The `temperature` scale is tiny and doesn't match its description.**
   - The code is `a += [v/10000, 0, -v/10000]`. At 100 ("about 100 is a visible shift"), mid grey 128 becomes (130,128,125), only ±2 levels.
   - The round-2 agent tried 0.15 first, saw no change, and needed 250 to get ±6 levels.
3. **The `tint` scale is 50–100× stronger than `temperature`, and it is additive.**
   - The code is `a += [v/200, -v/100, v/200]`. At tint 10, black becomes (12,0,12) and grey 128 becomes (140,102,140). At tint 100, every tone goes to pure magenta or black-magenta.
   - So tint turns the blacks magenta. The round-1 agent rejected it for exactly that reason and had to build a LUT to make a multiplicative channel gain.
4. **There is no multiplicative white-balance or channel-gain effect.**
   - `temperature` and `tint` are both offsets, so they also shift the blacks.
   - In round 2, temperature 250 turned V's shadows red-brown: from (3,2,7) to (15,7,7) together with contrast −12.
