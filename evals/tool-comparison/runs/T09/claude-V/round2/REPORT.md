# T09 round 2 · Tidewick Café winter menu (lane V: Vixl)

## What changed

| Change | Where |
| --- | --- |
| Headline "The Winter Menu is here" → "Winter Menu: now pouring" | All six sizes |
| Menu item "Smoked maple latte" → "Spiced honey cortado" | The four sizes that carry the menu line (square, story, X post, Facebook event). The leaderboard and email header had no menu line in round 1, so there is nothing to replace there |

The rest of the menu line is unchanged: "Gingerbread flat white · Spiced honey cortado · Cardamom bun"
(same `·` separators). The date and URL lines, palette, fonts, lamp, halo, rule and tide lines are
unchanged in every file.

## How

All edits were made with the Vixl MCP tools. No pixels, SVG or HTML were drawn by hand.

1. I copied the six round-1 `.vixl` sources into `round2/`. The round-1 files outside `round2/` were not touched.
2. I opened each copy and ran `vixl_operations_apply` with `text-set` on the existing `headline` and
   `menu` text layers. The layers kept their IDs, positions, fonts, sizes and colors.
   - In the four large sizes, the headline keeps the round-1 two-line break: "Winter Menu:" / "now pouring".
   - In the leaderboard and email header it stays on one line.
3. I checked each file with `vixl_render_preview` and `vixl_check`, then exported the PNGs with
   `vixl_export_batch`. A Python/PIL read-back confirmed the sizes: 1080×1080, 1080×1920,
   1600×900, 1920×1005, 728×90 and 600×200, all RGB.

## Layout adjustments (only where the new copy needed them)

- **Email header:** at the old 36 px size the new headline ran to x≈519, into the lamp (x 500–560).
  I reduced it to 32 px and moved it down 4 px (y 30→34) so its baseline stays at ≈57, where it was.
  The headline now ends at x≈465.
- **Leaderboard:** at the old 32 px size the new headline ran to x≈521, touching the tide lines that
  start at x=520. I reduced it to 29 px and moved it down 3 px (y 15→18) so its baseline stays at ≈39.
  It now ends at x≈481, about where the old headline ended (x≈482), and lines up with the date line below.
- **Square, story, X post, Facebook event:** no size or position changes.
  - The headline is a little wider than before. Its widest line, "Winter Menu:", stays clear of the
    lamp in every size.
  - The menu line rewraps the same way as in round 1: two lines on the square, story and X post, one
    line on Facebook. As before, line 1 ends with "·".

## Checks

- `vixl_check` reports no overlaps, no contrast problems and no new issues.
- The square, story text and email header are clean.
- The remaining warnings are thumbnail-legibility warnings that round 1 already had and accepted:
  - X post and Facebook: the menu, date and URL lines.
  - Leaderboard: the 18 px date line.
- Story: running `vixl_check` with the top and bottom 250 px reserved, on the text layers and the
  rule, found nothing. Text runs from y=680 to y≈1288.
