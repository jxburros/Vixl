# T15 · Seamless pattern: judging

Runs: `claude-C` (pycairo), `claude-V` (Vixl MCP), `claude-W` (SVG + Chromium), each with `round2/`.

- **C and W:** run and judged on 2026-10-05 (claude-code-subagent judge). Their scores and notes below are
  unchanged from that judging.
- **V:** re-run on Vixl 0.20.0 by fresh agents and judged on 2026-10-06. This replaces the Vixl 0.18.0 run
  judged on 2026-10-05 (see "Changes since the Vixl 0.18.0 run").

For the 2026-10-06 judging, only the C and W sources are committed, so I regenerated their deliverables in a
scratch copy outside the repo (`make_pattern.py` for C after `pip install pycairo`; `make_pattern.py` plus
`render.py` in Playwright Chromium for W). Both regenerated cleanly, rounds 1 and 2. Their ink shares match
the 2026-10-05 numbers exactly (C 9.0→5.8 %, W 7.4→4.9 %), so the regenerated files are the judged ones.

## 1. Blind scores (written before opening the key)

2026-10-05 codes (C, W and the old V run):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| U96H | 5 | 4 | Kelp, spiral shells, curling waves and dots all clearly readable; even spread; five colours; varied sizes; shells are simple spiral blobs; waves bunch slightly in a middle band |
| W2GK | 4 | 4 | Detailed nautilus shells and kelp, even spread, lively; the wave glyph reads as a bird head/hook rather than a curling wave |
| WXZP | 5 | 4 | (revision) all shells amber, fewer motifs, still even |
| 10PA | 4 | 4 | (revision) all shells amber, fewer motifs; same bird-like waves |

Key: U96H = claude-C, W2GK = claude-W, WXZP = claude-C/round2, 10PA = claude-W/round2.

2026-10-06 codes for the new V run. All six folders were blinded together. My blind scores for the
regenerated C and W files were within one point of the 2026-10-05 scores, so the two judgings agree.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 5L2A | 4 | 3 | All four motifs in the five colours, with neat nautilus shells and leafy kelp. The spread is uneven: empty diagonal bands, a large empty patch in the lower centre and three navy kelps stacked on the left. The repeat rhythm shows in the 3×3. Sea-foam waves have a pale halo. |
| 90QR | 4 | 3 | (revision) All shells amber, fewer motifs. Now very sparse, with large empty areas. |

Key: 5L2A = claude-V, 90QR = claude-V/round2.

## 2. Hard checks (round 1)

Inspector seams: C seam_x 2.01 / seam_y 0.31; V 1.11 / 0.97; W 1.34 / 1.31.
The inspector ratio compares one edge column with the mean of all columns, so in a sparse tile a motif straddling the edge inflates it. My own checks:
(a) count of pixel pairs with a >100 jump across the wrap vs interior column/row pairs: C x 9 (interior 4–20), y 3 (0–5); V x 7 (interior 5th–95th percentile 0–15), y 1 (0–10); W x 12 (8–16), y 12 (0–22);
(b) the wrap difference sits at the 75th–92nd percentile of interior column differences, never above the interior maximum (V: mean wrap step 1.87 across x, 65th percentile; 1.48 across y, 56th percentile);
(c) visual zoom of the tile rolled by 512 px and of the 3×3 at x=1024: the C coral shell, V kelp/shell and W kelp continue cleanly.
So none of the three has a real seam; C's 2.01 is a false positive from the metric.
`preview-3x3.png` equals `tile.png` tiled 3×3: C and V exactly (max diff 0); W max diff 75 on AA pixels only (mean 0.02, re-rendered in Chromium).
Label measured from navy border pixels: all three ≈600×300 at x 975–1575, y 375–675, rounded, centred, "Tidewick" in navy (all added a navy outline, all disclosed).
Colours: share of pixels not on a blend between two palette colours: C 0.000 % (tile), W 0.002 %, V 1.1 %. For V this is not a sixth design colour. It comes from three-colour edges on the shells (navy lines on coral/amber), resampling overshoot halos in the PNG (6,350 pixels outside the palette's channel range; the same SVG rendered with cairosvg has 842) and 272 near-white pixels. The white comes from the kelp stalks: these are open stroked paths with no `fill`, so Vixl fills them white by default, which leaves thin white slivers along the stalks.

Even spread (4×4 cells of the tile, coefficient of variation of ink share; largest empty radius on the torus): C 0.27 / 82 px, W 0.28 / 77 px, V 0.62 / 131 px. V is the least even. Round 2: C 0.42 / 100 px, W 0.31 / 97 px, V 0.95 / 182 px.

| Check | claude-C | claude-V | claude-W |
| --- | --- | --- | --- |
| tile.png 1024², seams ≈1 | PASS: 1024×1024; seam_x 2.01 is a metric false positive, own checks show continuity | PASS: 1024×1024; 1.11/0.97 | PASS: 1024×1024; 1.34/1.31 |
| preview-3x3 3072², no seams/obvious grid | PASS: exact tiling, even spread | PASS (marginal): exact tiling, no seams, no grid. The spread is uneven (empty bands, kelp clustered left), so the repeat is easy to spot. | PASS: even Poisson-disc spread |
| mug-wrap 2550×1050, cream rounded label, navy "Tidewick" | PASS (no 300 dpi metadata, disclosed; label text has LCD-style subpixel colour fringes) | PASS: 300 dpi; label 600×300 r48 centred; Fraunces SemiBold navy; tile drawn at 850 px so the wrap's two ends join (end-to-end diff 0.28) | PASS (no dpi metadata, disclosed) |
| Only the five colours; varied sizes and rotations | PASS: only palette + AA; kelp/wave rotation limited to about ±35° (disclosed) | PASS (marginal): the five colours, with navy shell linework. Off-palette pixels are AA, resampling halos and hairline white slivers on the kelp stalks, none visible at 1×. Scales 0.45–0.78; kelp ±28°, waves ±18°, shells any angle | PASS: palette + AA only; rotations vary |
| **Total** | **4/4** | **4/4** | **4/4** |

C's and W's mug wraps repeat a 1024 tile across 2550 px, so the two ends don't join on a real mug. Both disclosed this; the brief didn't require it. V scaled the tile to 850 px, so exactly 3 tiles span the wrap and the two ends join.

**Lane rule (V).** In round 1 the agent ran a short Python script in its scratchpad to compute the layout: a seeded toroidal Poisson scatter that chose motif centres, sizes and rotations and listed the motifs crossing an edge. It then pasted the numbers into Vixl batches. The V rule allows scripts "only for reading inputs and checking outputs", so this bends the rule. Placement is design work, even though no pixels, SVG or HTML were made outside Vixl. It was disclosed in the first paragraph of the report. Vixl 0.20.0 has no layer-level seamless or toroidal scatter that would do this job (see the product notes in section 5), so the script filled a real gap. I noted it and didn't penalise the scores. Round 2 used no layout script.

## 3. Report honesty (round 1)

- **claude-C: yes.** Motif counts, rotation limits, the missing dpi metadata, the SVG geometry running past the viewBox and the uneven middle band are all stated and accurate. Not mentioned: subpixel colour fringing on the label text (trivial).
- **claude-V: yes.** Motif counts (6 kelp, 6 waves, 8 shells, 34 dots, 7 wrap copies), the seam numbers (1.87/1.48, matching mine), pixel-identical 3×3 cells, label geometry, 300 dpi, the 850 px mug scale, the ~92 % cream share, the left-heavy navy kelp, the label outline and the layout script are all stated and accurate. Two small gaps. It says "only the five brief colours are used", but there are hairline white slivers from the unfilled stalk paths. It also reports the PNG fringe as faint, only where kelp blades overlap the stalk, and blames anti-aliasing. In fact a resampling halo runs around every sea-foam shape (waves included) and, more faintly, the coral and amber ones. Neither gap is visible at 1×, and it flagged the fringe as a doubt.
- **claude-W: yes.** Counts, method, label geometry (matches my measurement) and the hook-like waves are all disclosed.

## 4. Round 2 (all shells amber; about a third fewer motifs; regenerate everything)

Ink pixels (non-cream) r1→r2 and the share of r2 ink left unchanged from r1:
C 9.0→5.8 % (×0.64), 11 % unchanged; V 7.0→4.8 % (×0.69), 87 % unchanged; W 7.4→4.9 % (×0.66), 40 % unchanged.
All r2 tiles stay seamless by the same checks (inspector C 1.75/0.19, V 1.60/1.38, W 3.04/0.96, all inflated by edge-straddling motifs; jump counts are within the interior range). All shells are amber in all three. Sizes and labels are unchanged.

- **claude-C (editability 4, revision 3).** Four-number edit in the generator (counts 168→111, shells `[AMBER]`), ~2 min. The rejection sampler re-rolls, so the whole layout is new (89 % of ink moved). Disclosed. The request is met but the pattern isn't recognisably the same tile.
- **claude-V (editability 5, revision 4).** One atomic, dry-run-tested batch of 29 operations on a copy of the live `tile.vixl`. It recoloured every remaining coral shell body to amber in place (the navy linework stayed) and removed 7 of the 20 main motifs (kelp 6→4, waves 6→4, shells 8→5) together with their wrap copies. It then repointed the 9 + 6 `link` layers in the 3×3 and mug documents to `round2/tile.vixl` and re-exported. No workarounds and no failed operations. Nothing moved: 87 % of the r2 ink is pixel-identical to r1, and the rest is the shell recolour. I checked the file: 13 motifs, 23 dots, all shell fills `#f2a541`. Collateral: it also removed every third filler dot (34→23), which wasn't asked for but was disclosed. Removing motifs without rebalancing leaves the tile very sparse and patchy (cell CV 0.95, largest gap 182 px), which the report also notes.
- **claude-W (editability 4, revision 3).** Edited the counts, widened the spacing gaps and set the shell palette to amber only; 158→106 motifs. Same seed, but with fewer throws the placement partly re-rolls: kelp keep their spots, while shells, waves and dots move (60 % of ink moved). Disclosed. Amber shells now have navy linework; spread is still even.

## 5. Vixl product notes (from the V run)

- **No seamless scatter for layers.** `repeat` steps copies by a fixed dx/dy (a grid). The organic `scatter` rule does a Poisson-disc spread inside a boundary, but only for one organic shape, and it doesn't wrap. `pattern-define`/`pattern-fill` work on raster tiles plus a seam check. Nothing places layer motifs on a torus or adds the ±tile-size copies for motifs that cross an edge. The `vixl_guide` pattern recipe (`src/vixl/briefs.py`, "pattern") recommends repeating along x and y, which gives the visible grid this brief rules out. That is why the agent computed positions in Python.
- **Resampling halo in PNG exports.** Groups are rasterised, resized with LANCZOS and rotated with BICUBIC (`src/vixl/render.py`, `transform_layer_image`). On scaled and rotated motif groups this rings at the edges: `tile.png` has 6,350 pixels outside the palette's channel range, against 842 in the exported SVG rendered by cairosvg. You can see it as a bright rim around the sea-foam waves and kelp. The SVG doesn't have it.
- **Open stroked paths are filled white by default.** A `shape path` with only `stroke` gets `fill` "white" (`src/vixl/design_render.py`, `layer.get(field, "white" if field == "fill" …)`). The SVG export shows `fill="rgb(255,255,255)"` on each stalk's centre-line path. The result is a thin white sliver along every wavy kelp stalk, and `vixl_check` doesn't flag it.

## 6. Changes since the Vixl 0.18.0 run

| | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- |
| V on 0.18.0 (2026-10-05, R7KE/JREA) | 3/4 | 4 | 3 | yes | 4 | 4 |
| V on 0.20.0 (2026-10-06, 5L2A/90QR) | 4/4 | 4 | 3 | yes | 5 | 4 |

- **Palette now passes.** On 0.18.0 the `shell` preset drew brown outlines and ignored the navy stroke override, and the brush gave off-palette sea-foam tones. On 0.20.0 the shells have navy chamber lines and the kelp is drawn from custom Bézier paths instead of the blobby preset. What's left off-palette is rendering artefacts (halo, white stalk slivers), not a sixth colour.
- **Better structure.** The 3×3 and mug are now live `link` layers to `tile.vixl`, not embedded rasters, so round 2 only had to repoint links. The mug tile is scaled to 850 px so its ends join. The label font is Fraunces, installed through `vixl_font_install`. Inspector seams went from 1.84/1.01 to 1.11/0.97.
- **Round 2 was cleaner.** On 0.18.0 the agent had to regrow shells with `organic` because `shape` with `target` added a layer instead of editing one. `text_add` failed until `font_pair` ran, and two shells moved. On 0.20.0 one batch edited the fills in place with no failed operations. 87 % of the ink stayed put (84 % before).
- **Unchanged weaknesses.** The spread is still the least even of the three lanes, and round 2 still leaves the tile very sparse, so craft stays at 3. New on this run: the PNG resampling halo, the white stalk slivers and a Python layout script, which bends the lane rule (disclosed).

## Summary

| Lane | Date | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | 2026-10-05 | 4/4 | 5 | 4 | yes | 4 | 3 |
| V | 2026-10-06 | 4/4 | 4 | 3 | yes | 5 | 4 |
| W | 2026-10-05 | 4/4 | 4 | 4 | yes | 4 | 3 |
