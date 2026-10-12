# T15 · Seamless pattern: judging

Runs: `claude-C` (pycairo), `claude-V` (Vixl MCP), `claude-W` (SVG + Chromium), each with `round2/`.

- **C and W:** run and judged on 2026-10-05 (claude-code-subagent judge). Their scores and notes below are
  unchanged from that judging.
- **V:** re-run on Vixl 0.26.0 by fresh agents and judged on 2026-10-12. This replaces the Vixl 0.20.0 run
  judged on 2026-10-06 and the Vixl 0.18.0 run judged on 2026-10-05 (see "Changes since earlier Vixl runs").
  Effort: round 1 took 3.8 min and 31 tool calls, round 2 took 2.4 min and 30 tool calls, with no nudges.

For the 2026-10-12 judging, only the C and W sources are committed, so I regenerated their deliverables in a
scratch copy outside the repo (`make_pattern.py` for C after `pip install pycairo`; `make_pattern.py` plus
`render.py` in Playwright Chromium for W, with `executable_path` pointed at the Chromium under `/opt/pw-browsers`).
Both regenerated cleanly, rounds 1 and 2. Their inspector seams (C 2.01/0.31 and 1.75/0.19, W 1.34/1.31 and
3.04/0.96), ink shares (C 9.1→5.8 %, W 7.5→4.9 %) and spread figures match the earlier judgings, so the
regenerated files are the judged ones.

## 1. Blind scores (written before opening the key)

2026-10-05 codes (C, W and the 0.18.0 V run):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| U96H | 5 | 4 | Kelp, spiral shells, curling waves and dots all clearly readable; even spread; five colours; varied sizes; shells are simple spiral blobs; waves bunch slightly in a middle band |
| W2GK | 4 | 4 | Detailed nautilus shells and kelp, even spread, lively; the wave glyph reads as a bird head/hook rather than a curling wave |
| WXZP | 5 | 4 | (revision) all shells amber, fewer motifs, still even |
| 10PA | 4 | 4 | (revision) all shells amber, fewer motifs; same bird-like waves |

Key: U96H = claude-C, W2GK = claude-W, WXZP = claude-C/round2, 10PA = claude-W/round2.

2026-10-12 codes. All six folders (V on 0.26.0 plus the regenerated C and W) were blinded together. My blind
scores for C and W were identical to the 2026-10-05 ones (C9RW 5/4, 7EER 4/4, I130 5/4, WW8T 4/4), so the
judgings agree and the old C and W scores stand.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| HYD0 | 4 | 3 | Neat nautilus shells (coral and amber with navy chamber lines), wispy two-tone kelp, dots in all four colours. Spread is even, with no empty bands, but the tile is airy. Only three waves, drawn as single thick strokes ending in a curl, so they read as hooks or question marks more than curling waves. Two sea-foam kelps sit one above the other, which gives a faint vertical stripe in the 3×3. |
| A9TH | 4 | 3 | (revision) All shells amber, fewer motifs. Still evenly spread but sparse and shell-heavy (only two kelp); the repeat shows in the 3×3. |

Key: HYD0 = claude-V, A9TH = claude-V/round2.

## 2. Hard checks (round 1)

Inspector seams: C seam_x 2.01 / seam_y 0.31; V 1.25 / 0.33; W 1.34 / 1.31.
The inspector ratio compares one edge column with the mean of all columns, so in a sparse tile a motif straddling the edge inflates it. My own checks:
(a) count of pixel pairs with a >100 jump across the wrap vs interior column/row pairs (5th–95th percentile): C x 2 (0–13), y 0 (0–15); V x 5 (0–12), y 0 (0–11); W x 10 (0–15), y 0 (0–16);
(b) the mean wrap step sits inside the interior range, far below the interior maximum (V: 1.96 across x, 68th percentile, interior max 8.3; 0.48 across y, 15th percentile, interior max 6.2);
(c) visual zoom of the tile and of the 3×3 at x=1024: the C coral shell, V navy wave and kelp, and W kelp continue cleanly.
So none of the three has a real seam; C's 2.01 is a false positive from the metric.
`preview-3x3.png` equals `tile.png` tiled 3×3: C and V exactly (max diff 0); W max diff 75 on AA pixels only (mean 0.02, re-rendered in Chromium).
Label measured from navy border pixels: all three ≈600×300 at x 975–1575, y 375–675, rounded, centred, "Tidewick" in navy (all added a navy outline, all disclosed). V's label is radius 40 with Noto Serif Bold 100 px.
Colours: share of pixels not on a blend between two palette colours: C 0.000 % (tile), W 0.002 %, V 0.010 % (1.1 % on the 0.20.0 run). V's tile has 115 pixels outside the palette's channel range (6,350 on 0.20.0), a slight overshoot on amber edges, and no near-white pixels (272 on 0.20.0). The same SVG rendered with cairosvg has 0 off-blend and 0 out-of-range pixels.

Even spread (4×4 cells of the tile, coefficient of variation of ink share; largest empty radius on the torus): C 0.27 / 82 px, W 0.28 / 77 px, V 0.34 / 110 px (0.62 / 131 px on 0.20.0). V is now close to the other two. Round 2: C 0.42 / 101 px, W 0.31 / 97 px, V 0.35 / 128 px (0.95 / 182 px on 0.20.0).

| Check | claude-C | claude-V | claude-W |
| --- | --- | --- | --- |
| tile.png 1024², seams ≈1 | PASS: 1024×1024; seam_x 2.01 is a metric false positive, own checks show continuity | PASS: 1024×1024; 1.25/0.33 | PASS: 1024×1024; 1.34/1.31 |
| preview-3x3 3072², no seams/obvious grid | PASS: exact tiling, even spread | PASS: exact tiling, toroidal Poisson spread, no grid. A faint vertical rhythm from two stacked sea-foam kelps (disclosed). | PASS: even Poisson-disc spread |
| mug-wrap 2550×1050, cream rounded label, navy "Tidewick" | PASS (no 300 dpi metadata, disclosed; label text has LCD-style subpixel colour fringes) | PASS: 300 dpi; label 600×300 r40 centred; Noto Serif Bold navy; pattern outside the label matches the tile exactly at offset (−261, −499) | PASS (no dpi metadata, disclosed) |
| Only the five colours; varied sizes and rotations | PASS: only palette + AA; kelp/wave rotation limited to about ±35° (disclosed) | PASS: palette + AA only (0.010 % off-blend). Scale 1.15 ± 30 %, rotation ± 70° on every motif, two dot sizes per colour | PASS: palette + AA only; rotations vary |
| **Total** | **4/4** | **4/4** | **4/4** |

None of the three mug wraps joins end to end now: C and W repeat a 1024 tile across 2550 px, and V uses the tile at full size too (end-to-end column difference 4.7 against an interior step of 1.6). All three disclosed it; the brief didn't require it. The 0.20.0 V run had scaled the tile to 850 px so the ends joined.

**Lane rule (V).** Both rounds were made with Vixl operations only. The layout comes from Vixl's own `pattern-scatter` (toroidal Poisson-disc placement with wrapped ghost copies, seeded), and the agent's scripts only read the exported files. The 0.20.0 run's Python layout script is no longer needed.

## 3. Report honesty (round 1)

- **claude-C: yes.** Motif counts, rotation limits, the missing dpi metadata, the SVG geometry running past the viewBox and the uneven middle band are all stated and accurate. Not mentioned: subpixel colour fringing on the label text (trivial).
- **claude-V: yes.** I checked the claims against the files. 16 motif copies plus 10 wrapped ghosts and 45 dots (`tile.vixl` has 26 and 46 copy layers); seeds 5 and 31, scale 1.15 ± 30 %, rotation ± 70° as stored in the recipes; seam 1.96/0.48 (mine: 1.96/0.48); pixel-identical 3×3; label at 975, 375, 600 × 300, radius 40, 4 px navy outline, Noto Serif Bold 100 px; 300 dpi; nine and six `link` layers to `tile.vixl`; SVG with no `<image>`; `vixl_check` on the mug passes with only the two overlap `review` items (I re-ran it on a scratch copy). It also disclosed the soft spots I found: the faint vertical kelp rhythm, only three waves, dots overlapping motifs between the two passes, and that the mug ends don't join. Not mentioned: PNG edges of rotated motifs are slightly frayed compared with the SVG (see section 5), invisible at 1×.
- **claude-W: yes.** Counts, method, label geometry (matches my measurement) and the hook-like waves are all disclosed.

The V round-2 report is also accurate (12 motifs: 7 shells, 2 kelp, 3 waves; 30 dots; no coral shell fills left; coral only on dots), but it undersells the drift: it says the layout "is not identical" and the dots "keep a similar feel", when only 6 % of the round-2 ink is unchanged.

## 4. Round 2 (all shells amber; about a third fewer motifs; regenerate everything)

Ink pixels (non-cream) r1→r2 and the share of r2 ink left unchanged from r1:
C 9.1→5.8 % (×0.64), 11 % unchanged; V 9.7→7.2 % (×0.74), 6 % unchanged; W 7.5→4.9 % (×0.66), 40 % unchanged.
(The 0.20.0 V run kept 87 %, the 0.18.0 run 84 %.)
All r2 tiles stay seamless by the same checks (inspector C 1.75/0.19, V 0.61/0.77, W 3.04/0.96; jump counts within the interior range). All shells are amber in all three. Sizes and labels are unchanged.

- **claude-C (editability 4, revision 3).** Four-number edit in the generator (counts 168→111, shells `[AMBER]`), ~2 min. The rejection sampler re-rolls, so the whole layout is new (89 % of ink moved). Disclosed. The request is met but the pattern isn't recognisably the same tile.
- **claude-V (editability 4, revision 3).** Worked on copies of the three `.vixl` sources in `round2/`. Recoloured the hidden coral shell source to amber in place (navy linework kept, group renamed), then re-ran `pattern-scatter` on the `motifs` group with count 18→12 and on `dots` with 48→32, same seeds. Links in the 3×3 and mug are relative, so a `link-refresh` and re-export finished the job. No failed operations, 2.4 min. The edit itself is clean and parametric, but `pattern-scatter` derives its spacing from the count, so a lower count re-rolls the Poisson layout: only the first motif and first dot keep their place, and 94 % of the r2 ink is new. The result meets the request (all 9 shell copies amber, motifs 16→12 = −25 %, dots 45→30, all elements −31 %) and stays even (cell CV 0.35), but it is not recognisably the same tile, the mix drifted to 7 shells out of 12 large motifs with only 2 kelp, and the tile is sparse.
- **claude-W (editability 4, revision 3).** Edited the counts, widened the spacing gaps and set the shell palette to amber only; 158→106 motifs. Same seed, but with fewer throws the placement partly re-rolls: kelp keep their spots, while shells, waves and dots move (60 % of ink moved). Disclosed. Amber shells now have navy linework; spread is still even.

## 5. Vixl product notes (from the V run)

Fixed since 0.20.0:

- **Seamless scatter exists.** `pattern-scatter` places layer motifs on a torus with Poisson-disc spacing, adds ghost copies for motifs crossing an edge, reports a seam score, keeps the recipe on the group for rebuilds, and `vixl_guide`'s pattern recipe (`src/vixl/briefs.py`) now points to it. The agent needed no layout script.
- **Open stroked paths stay unfilled.** `geometry.default_fill` returns transparent for an open path with a stroke and no fill; a scratch test (open Bézier path, stroke only, no `fill`) exported SVG `fill-opacity="0.0"` and a PNG with no white pixels. (The agent also set `fill: transparent` explicitly on its waves.)
- **Resampling halo mostly gone.** 115 out-of-range pixels in `tile.png`, against 6,350 on 0.20.0.

Gaps reproduced on this run:

- **Changing `count` re-rolls the whole layout.** `execute_pattern_scatter` sets `spacing = sqrt(0.68·W·H/count)` (`src/vixl/scatter.py`), so a new count gives a new spacing and a new Poisson set. There is no way to thin an existing scatter (drop N copies with their ghosts, keep the rest). Round 2 kept 6 % of its ink, against 87 % when the 0.20.0 agent deleted layers by hand.
- **`count` is a ceiling, not a target.** count 18 placed 16 motifs and count 48 placed 45 dots; in round 2 the agent tried count 11 and got 10 (reported). The 0.68 packing factor rarely reaches the requested number.
- **No source weights or exclusion in `pattern-scatter`.** Sources are picked uniformly (`Variation`, `rng.integers(len(self.sources))`), listing a source twice is rejected ("source lists a layer twice"), and `exclude` exists only on `scatter`. So the agent needed two passes (dots, then motifs), the passes don't keep clear of each other (dots sit under kelp blades and shells), and the motif mix is luck of the seed (7 of 12 shells in round 2).
- **Rotated motifs have frayed edges in PNG.** `tile.png` against the same `tile.svg` rendered with cairosvg: 3,417 pixels differ by more than 40, all along the edges of rotated motif groups (kelp blades and shell outlines look slightly furry at 3× zoom; the SVG is clean). Groups are still rasterised, resized with LANCZOS and rotated with BICUBIC (`src/vixl/render.py`, around lines 1026 and 1048). Not visible at 1×.
- **Rebuilt copies get " 2" names** (`motifs/3 2`), because the namer runs before the old copies are removed. Cosmetic.

## 6. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Blind codes | R7KE / JREA | 5L2A / 90QR | HYD0 / A9TH |
| Hard checks | 3/4 | 4/4 | 4/4 |
| Fidelity / craft | 4 / 3 | 4 / 3 | 4 / 3 |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 4 | 5 / 4 | 4 / 3 |
| r2 ink unchanged | 84 % | 87 % | 6 % |
| Spread r1 / r2 (cell CV) | — | 0.62 / 0.95 | 0.34 / 0.35 |
| Off-blend pixels (r1 tile) | sixth colour (brown) | 1.1 % | 0.010 % |
| Effort r1 / r2 | — | — | 3.8 / 2.4 min |

On 0.26.0 the three 0.20.0 problems are fixed: `pattern-scatter` gives an even toroidal spread without a Python layout script, open stroked paths are no longer filled white, and the PNG halo is mostly gone (off-blend 1.1 % → 0.010 %). Spread is now nearly as even as C and W in both rounds. Craft stays at 3 because the waves read as thick hooks, there are only three of them, and the tile is airy. Round 2 regressed: the agent used the documented rebuild path (re-run `pattern-scatter` with a lower count), which re-rolls every position, so editability drops from 5 to 4 and revision from 4 to 3, the same as C and W. The mug tile also went back to full size, so its ends no longer join (not required).

## Summary

| Lane | Date | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | 2026-10-05 | 4/4 | 5 | 4 | yes | 4 | 3 |
| V | 2026-10-12 | 4/4 | 4 | 3 | yes | 4 | 3 |
| W | 2026-10-05 | 4/4 | 4 | 4 | yes | 4 | 3 |
