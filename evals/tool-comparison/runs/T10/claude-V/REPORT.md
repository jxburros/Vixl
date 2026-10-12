# T10 photo correction: report (lane V, Vixl via MCP)

I did all of the editing in Vixl through its MCP tools. I used small Python/PIL scripts only to read pixel statistics from the input and from test exports: horizon slope, empty corners and noise. The original `evals/tool-comparison/fixtures/coast-raw.jpg` was never written to. Its sha256 is still `86ec0e7c…cc7a4c`, the same hash Vixl recorded when it imported the file.

## Files

| File | Size | How it was made |
| --- | --- | --- |
| `coast.vixl` | 1512 × 1008 canvas | Editable master. It holds one `photo` layer (the embedded raw JPEG) with a rotation and four non-destructive effects (listed below). The canvas is the leveling crop. |
| `coast-edited.jpg` | 1512 × 1008, JPEG q95 | Exported from `coast.vixl`. |
| `coast-instagram.vixl` | 1080 × 1350 | A live `link` layer pointing at `coast.vixl`. It shows the source crop x=690, y=0, w=806, h=1008 (whole corrected height), with `fit: fill`. |
| `coast-instagram.jpg` | 1080 × 1350, JPEG q95 | Exported from `coast-instagram.vixl`. |
| `coast-caption.vixl` | 1600 × 900 | A live `link` layer to `coast.vixl` showing the crop x=0, y=80, w=1512, h=850 with `fit: fill`. On top are a radial `scrim` gradient and a `caption` text layer. |
| `coast-caption.png` | 1600 × 900, RGB PNG | Exported from `coast-caption.vixl`. |

The two derived documents link to the master, so a change to the corrections in `coast.vixl` carries through to both when they are re-exported.

## Corrections (all on layer `photo` in `coast.vixl`, in stack order)

1. **Tilt.** I fitted a line to the sky/sea edge in the raw image between x≈620 and x≈1580. It slopes **+2.20°** (the right side is lower). I rotated the layer by **−2.2°** (counter-clockwise) about its centre. Re-measuring the exported `coast-edited.jpg` gives a slope of 0.03°, with the horizon at y≈612.
2. **Crop for leveling.** The rotation leaves empty corners. I cropped to the largest centred rectangle with the original aspect ratio that contains no empty corner: canvas **1512 × 1008**, starting at x=44, y=28.5 of the 1600 × 1067 frame (about 94.5 % of each side). The aspect ratio is 1.500 against the original 1.4995. The exported image has no empty (0,0,0) pixels at its edges. The only pure-black pixels left are inside the figure's silhouette. The one corner pixel at the top left is slightly darker from anti-aliasing (10,11,62 against the sky's ~11,13,73).
3. **Noise.** Effect `denoise` with luminance 60 and chroma 60 (search radius left at its default of 5). On a high-pass measure (pixel minus a 2 px Gaussian blur), noise in the sky fell from 3.84 to 1.22. In the open water it fell from 3.93 to 1.54. This held even though the image is now brighter.
4. **Color cast.** Effect `white-balance` with gains **[1.06, 0.94, 1.04]**. The raw sun core read (179, 200, 177) and the glow at the horizon was lime-green, which points to a green cast in the highlights. After the edit the sun reads (237, 228, 210), a warm white, and the horizon glow is orange-yellow.
5. **Exposure, first step.** Effect `levels` with black 2 and white 205. The raw image was underexposed: its 99.5th percentile was only 186 (red), 196 (green) and 113 (blue), and its mean was (62, 42, 50).
6. **Exposure, second step.** Effect `curves` with points [[0,0],[64,78],[128,146],[255,255]], to lift the mid-tones and open up the water and sky. The mean afterwards is (92, 56, 74). The deep shadows (rock, figure) stay near black.

Nothing in the scene was moved, added, removed or repainted.

## Instagram crop

The 4:5 crop takes the full corrected height, x 690–1496 of the 1512 px width. It frames the sun, the glitter path and the figure on the rock, keeps the horizon at roughly the 45 % line, and includes one bird. The lighthouse falls outside the crop, because it is ~1000 px from the figure and a 4:5 crop can't hold both.

**Difference from the brief:** the corrected photo is only 1008 px tall, so a 1350 px tall crop has to be **enlarged about 1.34×**. No crop of this photo can reach 1080 × 1350 at native resolution.

## Caption card

- **Crop and scale.** A 16:9 crop of the corrected photo (x=0, y=80, 1512 × 850), scaled 1.058× to 1600 × 900. It keeps the lighthouse, all the birds, the sun and the figure. It trims 80 px of sky at the top and 78 px of rock at the bottom.
- **Scrim.** `scrim` is a radial gradient centred on the bottom-left corner (layer box x −500, y 420, 1800 × 960). It is colour rgba(8,5,14), with alpha 0.62 at the centre, 0.40 at 45 % and 0 at the edge, using `smooth` falloff. It darkens only the bottom-left area.
- **Caption text.** "Port Ellery at golden hour" in Libre Baskerville 400, 50 px, colour #fbf3e6. It sits at x=72, y=778, with the baseline at 819.5. Its box measures 665 × 55. I installed the font with `vixl_font_pair` (pairing libre-franklin-libre-baskerville, mood "editorial", seed 3) and used the body face for the caption.
- **Checks.**
  - `vixl_check` reported no fix or review findings, only two informational notes that the scrim intentionally bleeds off the edge.
  - An attached suite named `caption` passed all three rules: contrast ≥ 4.5, at least 48 px inside the canvas, and the exact caption text.
  - `vixl_measure` gives the caption a contrast of 14.7:1 at minimum and 17.0:1 on average.

## Choices and uncertainties

- **Amount of color correction.** The cast correction is a judgment call. I neutralised the green in the highlights using the sun as a near-white reference. The water and the upper sky still read purple or magenta, which I took to be the real colour of the sunset light rather than a cast. If the cast was meant to be magenta overall, I would want somewhat more green in the shadows: the rock now reads about (5, 2, 8).
- **Highlights.** No channel clips at 255. Red peaks around 239 in the brightest glow, so the highlights are compressed but not blown.
- **Re-encoding.** Both JPEGs are JPEG-encoded a second time from a JPEG source at quality 95. That adds a small amount of generation loss.
- **What I didn't read.** I did not open `fixtures/make_fixtures.py`, which apparently generates this photo, so the corrections are estimated from the image alone. I did not open TESTS.md or any other run folder.
- **Sharpening.** I applied none, which leaves the slight softness from denoising.
