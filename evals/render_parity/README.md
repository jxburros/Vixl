# Render parity

Measures Vixl's raster output against Chromium and, where geometry has a closed form, against an
exact supersampled reference. Findings and what was fixed: [docs/project/render-parity.md](../../docs/project/render-parity.md).

```bash
pip install playwright            # eval-only dependency; do not add it to the package
python -m evals.render_parity     # all cases -> render-parity-results/ (git-ignored)
python -m evals.render_parity -k text -k gradient --out /tmp/parity
python -m evals.render_parity --list
```

Run from the repository root with Vixl importable (`pip install -e .` or `PYTHONPATH=$PWD/src`).
Playwright finds its own Chromium; otherwise the harness launches `VIXL_PARITY_CHROMIUM` or
`/opt/pw-browsers/chromium`. Chromium runs headless at 1x with `--font-render-hinting=none`
(unhinted outlines, as Vixl draws them; `--hinting slight` shows the browser's default look).

## What a case is

Each case in `cases.py` builds a `Project` and the equivalent HTML: the same bundled font
(`NotoSans-Regular.ttf`, through `@font-face`), sizes, colours and positions, written as CSS or
inline SVG. Text markup is placed from Vixl's own layout (`placed_glyphs`): the first baseline and
pen position are copied, so the comparison is about shaping and rasterization, not about defaults
such as line height. Blur and shadows use SVG `feGaussianBlur`/`feDropShadow`, whose
`stdDeviation` is the same number Vixl's SVG export writes.

| Group | Cases | Measures |
| --- | --- | --- |
| Text | body 11-16 px, display 64-120 px, kerning, ligatures, tracking, paragraphs, `baseline_y`, rotation | pen positions from Chromium's layout vs Vixl's (`layout_dx`), per-glyph ink shift (`glyph_shift`), ink box, total ink (`ink_weight_ratio`), edge sharpness, line breaks and pitch |
| Shapes | circles, rounded rectangle and capsule, fractional positions, hairlines 0.5-2 px, rotated rectangle | coverage error against the exact shape (`vs_ideal`, `edge_vs_ideal`), area |
| Gradients | full range, subtle dark ramp, saturated, radial | error against the exact ramp, distinct levels, longest flat run, `banding` (deviation from a straight ramp after a 9 x 9 average) |
| Compositing | 8 blend modes at 100% and 50% opacity | per-patch colour against the W3C compositing formulas |
| Effects | blur sigma 2 and 6, drop shadow | error against an exact Gaussian; estimated or fitted sigma |
| Images | 512 px photo-like image at 128 and 170 px | error against an exact area average, aliasing left in fine stripes and a zone plate |

## Output

`--out` (default `render-parity-results/`) receives, per case, `NAME.vixl.png`, `NAME.chromium.png`,
`NAME.html` and `NAME.compare.png` (Vixl | Chromium | difference x4 | reference), plus
`report.md` and `report.json` with every metric, the Chromium version and the platform. Results are
not committed; publish notable runs in VixlExamples.

Differences in 0-255 levels are expected between any two rasterizers; read the per-case metrics and
the reference column before calling something a defect. The area-average reference for images is a
box filter and aliases itself: lower `stripe_alias_std` is better there, not closeness to it.
