# T01 round 2: report (lane V, Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, RGB, 137 KB | `vixl_export_file` from `round2/picture.vixl` with `alpha="flatten"`. Checked with PIL: size (2400, 1600), mode RGB. |
| `picture.vixl` | Editable source, 60 layers (54 from round 1 plus the 6 layers of the new boat group) | A copy of round 1's `picture.vixl`, edited with `vixl_operations_apply`. Its history continues from round 1. |
| `REPORT.md` | This report | |

Nothing outside `round2/` was changed. The round 1 files are untouched.

## What changed

1. **Night sky.** I re-stopped the `sky` gradient and kept it vertical with five stops: `#03061a` at the top, then `#0a1236`, `#16204a` and `#222d5c`, down to `#2e3a6a` at the horizon. The amber and mauve sunset stops are gone. The `horizon-glow` was a warm amber radial glow, so it belongs to the sunset. I changed it to a faint cool blue (`#8a9ad0` at 30% alpha, fading out) so the sky stays dark. In the PNG, pixel (1200,5) = rgb(3,6,26) and (1200,1045) = rgb(45,58,106), so the sky still runs from near-black down to a lighter blue.
2. **Brighter beam.** `beam-outer` went from opacity 0.16 to 0.30 and `beam-inner` from 0.20 to 0.42. Both fills went from `#ffe9b0` to a paler, whiter `#fff4d0`.
3. **Lighthouse and rocks moved to the right half.** I mirrored the headland around the canvas centre line:
   - `rock-main`, `rock-light-1` to `rock-light-4`, `rock-front` and `rock-islet` got a horizontal `flip` and were moved to x' = 2400 − x − width. The rocky point now enters from the right edge and reaches to x = 1320.
   - The `lighthouse` group was **moved, not flipped**, to x = 1885 (y unchanged), so the tower looks exactly as it did. It now spans x 1885 to 2055. The `lantern-glow` moved with it.
   - `beam-outer` and `beam-inner` were flipped and re-anchored. They now start at the lantern (about x 1960, y 400) and sweep left to the left edge, angled down toward the sea, with the same geometry as before in mirror image.
4. **Third sailboat.** I made `sailboat-3` by duplicating `sailboat-1`. It is scaled to 0.7 so it reads as farther away and placed at x 1080 to 1171, y 1000 to 1129, out on open water between the other boats and the rocky point. Its parts are named `hull-3`, `mast-3`, `sail-3`, `jib-3` and `wake-3`.

## Consequential moves (needed for the brief, not new design)

The rocky point now covers the right side of the sea, where the boats and some details used to be. To keep the scene's layout, I mirrored those elements as well:

- `sailboat-1` moved to x 790 and `sailboat-2` to x 264. They kept their y, size and orientation; they were moved, not flipped. Left where they were, both would have sat on the rocks.
- `far-headland` was flipped and moved to the left horizon (x 0 to 760), because the lighthouse rocks would have hidden it.
- The four shimmer strokes moved to their mirrored x positions (480, 500, 1020 and 70). Their y, size, colour and opacity are unchanged.

Nothing else was changed: the stars, the sea gradient, every colour except the sky, the glow and the beam, the lighthouse parts and the boat parts.

## Checks

- **Suite.** I updated the document's `brief` suite to match this round. It has 10 rules, and all of them pass:
  - no text layers;
  - exactly 3 `sailboat-?` groups;
  - at least 5 stars;
  - the sky top is `#03061a`;
  - the sky near the horizon is `#2d3969` ± 20, which shows it is still a gradient;
  - the lighthouse is at x = 1885 and `rock-main` is at x = 1320, both in the right half;
  - the lighthouse is to the right of `sailboat-3`;
  - the beam's ink reaches the left edge;
  - `beam-inner` opacity is 0.42.
- **Old rules.** Three round 1 rules now contradict the brief, so I replaced them: "lighthouse left of sailboat-1", "sailboat-2 right of lighthouse" and "beam reaches right edge". I also updated the sky-top colour and the boat count.
- **Design check.** `vixl_check` has no fix or review findings. The only notices are informational ones for intentional full-bleed crops.
- **Visual.** I looked at the full preview and at a zoom of the waterline. No boat touches the rocks.

## Judgement calls and caveats

- **Amber band on the sea.** The `sea` gradient's thin amber band at the horizon (`#d08f5c`) is unchanged, because you asked to keep everything else as it was. Under a night sky it reads as a faint last-light line. If you want a full night palette, recolouring that one stop is the obvious next edit.
- **Two position rules pin exact values.** The suite's `property` rule did not honour a tolerance for `x`, so "right half" is checked by pinning the exact positions rather than a range.
- **Rock facets are mirrored.** The rocks' light facets are mirror images of the originals, while the lighthouse's shaded half stays on its right side, because I did not flip the tower.
