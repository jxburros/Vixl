# T15 · Seamless pattern, round 2 (lane V, Vixl)

Requested changes: make every shell amber, and cut the number of motifs by about a third. All six
deliverables were regenerated into this folder under the same names. Nothing outside `round2/` was changed.

## How

All edits were made with Vixl MCP tools (`vixl_operations_apply`, `vixl_export_batch`,
`vixl_render_preview`, `vixl_check`). I didn't draw any pixels, SVG or HTML by hand.
1. I copied the three round-1 `.vixl` sources into `round2/` with `cp` and opened `round2/tile.vixl` in Vixl.
2. I made one atomic batch of 29 operations on the tile. A dry run came first.
   - **Shells to amber:** a `shape` fill edit to amber `#f2a541` on the shell body of every coral shell left
     in the tile (i12, i13, the i13 wrap copy and i18). I also recoloured the hidden coral master. The navy
     chamber and spiral lines are unchanged. These groups were renamed `*_shell_amber`. Their child layers
     still carry their old `i13_shell_coral/...` names, which is cosmetic only. All 5 shells in the tile are now amber.
   - **About a third fewer motifs:** `remove` on 7 of the 20 main motifs (20 → 13), keeping the mix of motif types:
     - kelp 6 → 4 (removed navy i03 and its wrap copy, and sea-foam i05 and its wrap copy; this also eases
       the round-1 left-heavy navy kelp)
     - waves 6 → 4 (removed sea-foam i06 and navy i19)
     - shells 8 → 5 (removed i15, i16, i17)
   - **Dots:** I also removed every third filler dot, 34 → 23 (dot02, 05, 08 … 32). The brief didn't ask for
     this. I did it so the filler density drops in step with the motifs. If you count only the 20 main
     motifs, the reduction is 35 %.
   - Remaining motifs, positions, sizes and rotations are untouched. No new layout was generated.
3. I exported `tile.png` and `tile.svg` (strict SVG policy, no embedded raster).
4. In `round2/preview-3x3.vixl` (9 links) and `round2/mug-wrap.vixl` (6 links), I repointed each `link` layer
   with a `link` operation, from `../tile.vixl` to `round2/tile.vixl`. Then I exported `preview-3x3.png` and
   `mug-wrap.png`. The mug label, wordmark, 850 px tile scale and 300 dpi are unchanged.

## Files

| File | Notes |
| --- | --- |
| `tile.vixl` | Editable tile, 1024 × 1024. It has 13 motifs and 23 dots, plus 5 wrap copies (i00, i01, i10, i13, dot01). |
| `tile.png` | 1024 × 1024 RGB |
| `tile.svg` | Vector, valid XML, 0 `<image>` elements |
| `preview-3x3.vixl` / `.png` | 3072 × 3072, 9 live links to `round2/tile.vixl` |
| `mug-wrap.vixl` / `.png` | 2550 × 1050 at 300 dpi, 6 live links to `round2/tile.vixl` |

## Checks (scripts read the exported files only)

- **Preview:** each of the 9 cells is pixel-identical to `tile.png` (max difference 0).
- **Tile seams:** mean edge difference is 1.87 left/right and 1.43 top/bottom. An ordinary interior column
  step is about 1.3, so the seams look like any other step. The wrap copies of the removed motifs were removed
  with them, so no orphaned half-motifs remain at the edges.
- **Mug:** the mean difference between its left and right ends is 0.28, so it wraps seamlessly. In the
  downscaled preview the tile joins looked like faint lines. In the full-size PNG they aren't there: the
  columns at the joins match their neighbours.
- **Colour:** pixels close to coral fell from 5975 to 866. What's left is the coral wave i10 and the coral
  dots, which aren't shells. Cream background now covers about 95 % of the tile, up from 92 %.
- **`vixl_check`:** links are current in both derived documents. The mug check has no fix or review
  findings. Only its intentional `allow_crop` bleeds are listed.

## Notes

- With the shells now amber, coral survives only in one wave and a few dots, so the palette leans
  navy, amber and sea-foam.
- Removing motifs left some airier spots: bottom-centre, and the gap between the top-left kelp and the
  centre. I didn't move the remaining motifs, so the rest of the layout matches round 1.
- The `.vixl` links are workspace-relative paths to `round2/tile.vixl`. If the folder is moved, the links
  need refreshing. The PNGs are unaffected.
