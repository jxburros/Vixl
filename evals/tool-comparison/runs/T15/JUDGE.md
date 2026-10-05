# T15 · Seamless pattern: judging (claude-code-subagent judge, 2026-10-05)

Runs: `claude-C` (pycairo), `claude-V` (Vixl MCP), `claude-W` (SVG + Chromium), each with `round2/`.

## 1. Blind scores (written before opening `blind/T15/key.csv`)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| U96H | 5 | 4 | Kelp, spiral shells, curling waves and dots all clearly readable; even spread; five colours; varied sizes; shells are simple spiral blobs; waves bunch slightly in a middle band |
| W2GK | 4 | 4 | Detailed nautilus shells and kelp, even spread, lively; the wave glyph reads as a bird head/hook rather than a curling wave |
| R7KE | 4 | 3 | Heavy, blobby kelp silhouettes dominate; waves are thin squiggles; sparse and uneven density; the tile repeat is obvious in the 3×3 |
| WXZP | 5 | 4 | (revision) all shells amber, fewer motifs, still even |
| 10PA | 4 | 4 | (revision) all shells amber, fewer motifs; same bird-like waves |
| JREA | 3 | 3 | (revision) very sparse; repeat lattice obvious in the 3×3; kelp butts against the mug label |

Key: U96H = claude-C, W2GK = claude-W, R7KE = claude-V, WXZP = claude-C/round2, 10PA = claude-W/round2, JREA = claude-V/round2.

## 2. Hard checks (round 1)

Inspector seams: C seam_x 2.01 / seam_y 0.31; V 1.84 / 1.01; W 1.34 / 1.31.
The inspector ratio compares one edge column with the mean of all columns, so in a sparse tile a motif straddling the edge inflates it. My own checks:
(a) count of pixel pairs with a >100 jump across the wrap vs interior column/row pairs: C x 9 (interior 4–20), y 3 (0–5); V x 3 (0–6), y 1 (1–5); W x 12 (8–16), y 12 (0–22);
(b) the wrap difference sits at the 75th–92nd percentile of interior column differences, never above the interior maximum;
(c) visual zoom of the tile rolled by 512 px and of the 3×3 at x=1024: the C coral shell, V kelp/shell and W kelp continue cleanly.
So none of the three has a real seam; C's 2.01 is a false positive from the metric.
`preview-3x3.png` equals `tile.png` tiled 3×3: C and V exactly (max diff 0); W max diff 75 on AA pixels only (mean 0.02, re-rendered in Chromium).
Label measured from navy border pixels: all three ≈600×300 at x 975–1575, y 375–675, rounded, centred, "Tidewick" in navy (all added a navy outline, all disclosed).
Colours: share of pixels not on a blend between two palette colours: C 0.000 % (tile), W 0.002 %, V 0.40 %.

| Check | claude-C | claude-V | claude-W |
| --- | --- | --- | --- |
| tile.png 1024², seams ≈1 | PASS: 1024×1024; seam_x 2.01 is a metric false positive, own checks show continuity | PASS: 1024×1024; 1.84/1.01 | PASS: 1024×1024; 1.34/1.31 |
| preview-3x3 3072², no seams/obvious grid | PASS: exact tiling, even spread | PASS (marginal): exact tiling, no seams; density is uneven (big kelp clumps, empty areas) so the repeat is easy to spot, but not a grid | PASS: even Poisson-disc spread |
| mug-wrap 2550×1050, cream rounded label, navy "Tidewick" | PASS (no 300 dpi metadata, disclosed; label text has LCD-style subpixel colour fringes) | PASS (300 dpi metadata set) | PASS (no dpi metadata, disclosed) |
| Only the five colours; varied sizes and rotations | PASS: only palette + AA; kelp/wave rotation limited to about ±35° (disclosed) | FAIL: shell preset draws brown outlines/chamber lines (#8a5a3b/#9b6b47) plus lighter sea-foam brush tones (#b3e3d5); sizes/rotations vary | PASS: palette + AA only; rotations vary |
| **Total** | **4/4** | **3/4** | **4/4** |

All three mug wraps repeat a 1024 tile across 2550 px, so the two ends don't join on a real mug. All three disclosed this; the brief didn't require it.

## 3. Report honesty (round 1)

- **claude-C: yes.** Motif counts, rotation limits, the missing dpi metadata, the SVG geometry running past the viewBox and the uneven middle band are all stated and accurate. Not mentioned: subpixel colour fringing on the label text (trivial).
- **claude-V: yes.** It discloses the brown shell outlines (and says it tried to set a navy stroke, which Vixl stored but didn't apply to the preset's child outlines), the bushy kelp, the label stroke, the mug-end mismatch and that the 3×3/mug `.vixl` files embed a raster. Its seam numbers use a different threshold from mine but reach the same conclusion.
- **claude-W: yes.** Counts, method, label geometry (matches my measurement) and the hook-like waves are all disclosed.

## 4. Round 2 (all shells amber; about a third fewer motifs; regenerate everything)

Ink pixels (non-cream) r1→r2 and the share of r2 ink left unchanged from r1:
C 9.0→5.8 % (×0.64), 11 % unchanged; V 10.7→7.7 % (×0.72), 84 % unchanged; W 7.4→4.9 % (×0.66), 40 % unchanged.
All r2 tiles stay seamless by the same checks (inspector C 1.75/0.19, V 2.37/1.60, W 3.04/0.96, all inflated by edge-straddling motifs; jump counts are within the interior range). All shells are amber in all three. Sizes and labels are unchanged.

- **claude-C (editability 4, revision 3).** Four-number edit in the generator (counts 168→111, shells `[AMBER]`), ~2 min. The rejection sampler re-rolls, so the whole layout is new (89 % of ink moved). Disclosed. The request is met but the pattern isn't recognisably the same tile.
- **claude-V (editability 4, revision 4).** Edited the live `tile.vixl` layers: removed 13 of 39 motifs (exactly a third), regrew the shells amber, moved two shells to fill gaps, then rebuilt the 3×3 and mug from the new raster, as they embed `tile.png`. The most stable revision: 84 % of ink unchanged. Workarounds needed: a `shape` op with `target` adds a layer instead of editing one, so shells had to be regrown with `organic`; `text_add` failed until `font_pair` ran; one constrain syntax was rejected. Collateral: the regrow turned the shell outlines navy (this fixes the r1 off-palette brown) and two shells moved. The thinned tile is now very sparse, with an obvious repeat in the 3×3.
- **claude-W (editability 4, revision 3).** Edited the counts, widened the spacing gaps and set the shell palette to amber only; 158→106 motifs. Same seed, but with fewer throws the placement partly re-rolls: kelp keep their spots, while shells, waves and dots move (60 % of ink moved). Disclosed. Amber shells now have navy linework; spread is still even.

## Summary

| Lane | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- |
| C | 4/4 | 5 | 4 | yes | 4 | 3 |
| V | 3/4 | 4 | 3 | yes | 4 | 4 |
| W | 4/4 | 4 | 4 | yes | 4 | 3 |
