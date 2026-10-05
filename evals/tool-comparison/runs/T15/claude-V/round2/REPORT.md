# T15 · Seamless pattern, round 2 (lane V, Vixl MCP)

Requested changes: **make every shell amber** and **cut the motifs by about a third**. Every file was made again. Round-1 files outside `round2/` are untouched.

Tool calls: **43** in total (Vixl MCP, Bash, ToolSearch, Read, plus the final hand-back). Two of them failed and were retried (see "Notes").

## What changed in the tile (`tile.vixl`)
I copied `../tile.vixl` into `round2/` and edited it with `vixl_operations_apply`. Its layers are still live vectors.

**Motif count: 39 → 26 (−13, exactly one third).** Wrap copies are not counted.

| Motif | Round 1 | Round 2 | Removed |
| --- | --- | --- | --- |
| Kelp fronds | 4 (K1–K4) | 3 (K2, K3, K4) | K1 |
| Spiral shells | 7 (S1–S7) | 5 (S1, S2, S3, S4, S6) | S5, S7 |
| Waves | 5 (W1–W5) | 3 (W1, W3, W4) | W2 and its wrap copy W2_wx, W5 |
| Dots | 23 (D01–D23) | 15 | D02, D06, D09, D11, D13, D15, D19, D22 |

- I removed with `remove` ops. No wrap copy is left without its original, so the tile still repeats seamlessly. The kept edge pairs are K3/K3_wx, K4/K4_wy, S4 plus its three copies, W4/W4_wx, D16, D17 and D18 with their copies.
- To even out the spacing after the removals, I moved two shells: S1 from (320,370) to (190,560), filling the space K1 left, and S2 from (800,360) to (830,470).

**All shells amber.** Every shell was regrown with an `organic` op on its own layer (`preset: shell`, same seed, `params.color: #f2a541`, `stroke: #14263b`, `stroke_width: 1.5`): S1 (seed 2) and S3 (seed 9), which were coral, plus S2, S4, S4_wx, S4_wy, S4_wxy and S6. Rotations and positions stayed the same, apart from the two moves above.
- Side effect: regrowing with `stroke` set also gave the shells **navy outlines and chamber lines**. Round 1 had an off-palette brown (`#8a5a3b` / `#9b6b47`) there. The shells now use only brief colours (amber body, navy linework).
- Coral is still in the pattern, but only as dots (D04, D07, D17 and its copy D17_wy).

## Files
| File | Check | How |
| --- | --- | --- |
| `tile.vixl` | 1024×1024, editable | Edited as described above |
| `tile.png` | 1024×1024 RGBA, fully opaque | `vixl_export_file` |
| `tile.svg` | viewBox 0 0 1024 1024, 0 `<image>` elements | `vixl_export_file`, `svg_policy=strict` |
| `preview-3x3.vixl` / `.png` | 3072×3072 | New document (cream background). Imported the new `tile.png`, then `repeat` (count 3, dx 1024), then `duplicate` + `move` for rows at y=1024 and y=2048. Exported as PNG. |
| `mug-wrap.vixl` / `.png` | 2550×1050, 300 dpi in the PNG metadata | New document, 300 dpi. New `tile.png` repeated 3 across and 2 down (anchored top-left, cropped by the canvas). Centered 600×300 cream `#f7f1e5` rounded rectangle at (975,375), radius 44, 4 px navy stroke. "Tidewick" in Young Serif 100 px navy `#14263b` (pairing `young-serif-rubik` added with `vixl_font_pair`; text added with `vixl_text_add`). The text is centered on the label with a `constrain` (center-x / center-y set to the label's centre). |

## Checks (script, on exported files)
- `preview-3x3.png` is exactly `tile.png` tiled 3×3 (max pixel difference 0).
- Wrap seams look like interior seams. Pixel pairs that differ strongly: 18 across the x seam against 0–6 for interior columns, and 7 across the y seam against 5–13 for interior rows. The extra pairs at the x seam come from shape outlines crossing the edge (K3, W4, D16), not from breaks.
- `mug-wrap.png` is 2550×1050 at about 300 dpi. The new `tile.png` (sha256 `0a136dc2…`) is the same asset embedded in both new `.vixl` files.
- I looked at the tile and the mug wrap: shells are amber with navy outlines, and the label and text are centered.

## Notes and deviations
- A `shape` op with `target` doesn't edit an existing layer; it adds a new one (found in a dry run, not applied). That is why I recoloured the shells with `organic` regrow ops.
- Two calls failed and were retried. `vixl_text_add` failed until the font was registered in the new document with `vixl_font_pair`. The first `constrain` expression (`"label"`) was rejected; `"label.center-x"` / `"label.center-y"` worked.
- These still apply from round 1: the mug wrap (2550 px) is not a multiple of 1024 px, so its two ends don't join on a mug. The label stroke was not in the brief. The 3×3 and mug `.vixl` files embed `tile.png` and won't update by themselves if `tile.vixl` changes.
- With fewer motifs, the tile has more open cream space, which is the intended effect. Spacing is still hand-placed and not on a grid.
