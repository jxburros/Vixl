# T02 round 2 · Social post revisions (lane V, Vixl MCP)

## Files in round2/

| File | What it is | How it was made |
| --- | --- | --- |
| `post.vixl` | Editable source for the updated post | `cp ../post.vixl` with Bash, then edited with `vixl_operations_apply` |
| `post.png` | 1080 × 1350 px updated post | `vixl_export_file` from `round2/post.vixl` |
| `story.vixl` | Editable source for the story | `cp round2/post.vixl` (after the edits above), then the canvas was resized and the layout redone with `vixl_operations_apply` |
| `story.png` | 1080 × 1920 px story | `vixl_export_file` from `round2/story.vixl` |
| `REPORT.md` | This report | written with a Bash heredoc |

I changed nothing outside round2/. The original `post.png`, `post.vixl` and `REPORT.md` are untouched.

## Changes to post.png / post.vixl

1. **Date:** used `text-set` on the `date` layer to change it to "Thursday, November 19 · 7–10 pm". It keeps the en dash and middle dot, Rubik 50 px, amber.
2. **Host line:** made the new text layer `host` by duplicating `address` (so it has the same Rubik font), then `text-set` to "Hosted by Mara Quinn" at 38 px in coral `#e2725b`. It is centred and constrained to top y=820, just under the headline, whose layer box ends at y=800.
3. **Reflow:** moved the lower text down to make room:
   - coral divider: y=838 → 888
   - date: 888 → 930
   - address: 968 → 1006
   - details: 1032 → 1066 (bottom edge 1100, still clear of the coral wave at about y=1140)

   The kicker, headline, URL and all decoration did not move.
4. **Checks:**
   - `vixl_check(safe_area=60)` on all 7 text layers passed, with 0 errors and 0 warnings (bounds, overlap, contrast, safe area, legibility, fonts).
   - I looked at the full render preview.
   - PIL confirms the PNG is 1080 × 1350.

## story.png / story.vixl (1080 × 1920)

**Copy:** exactly the same seven lines and styling as the updated post.

**Layout:**
- **Canvas:** changed from 1080×1350 to 1080×1920 with the `canvas` operation. That operation keeps the top-left corner fixed.
- **Lamps:** the festoon lamps and the glow stay at the top, inside the top 250 px. They are decoration, not text.
- **Waves:** the coral wave and the sea-foam band moved down 570 px, so the band still runs off the bottom edge.
- **Headline:** enlarged from 180 to 200 px, because the taller canvas has room. It is still two lines, with bounds x=66–1013.
- **Text block positions (top edges):**

  | Line | Top edge |
  | --- | --- |
  | kicker | 440 |
  | headline | 510–992 |
  | host | 1030 |
  | divider (shape, not text) | 1102 |
  | date | 1150 |
  | address | 1234 |
  | details | 1300–1334 |
  | URL | 1530–1567 |

- **URL:** in the post, the URL sits on the sea-foam band. In the story the band is inside the bottom 250 px, so I moved the URL up into the navy area above the wave. I changed its colour to sea-foam `#a8d5c8` (it was navy) and its size from 38 to 40 px. The sea-foam band is now decoration only.
- **Margins:** all text is between y=440 and y=1567, which is well inside the 250–1670 band, and at least 60 px from the left and right edges.

**Checks:**
- `vixl_check(safe_area={left:60, right:60, top:250, bottom:250})` on all 7 text layers passed, with 0 errors and 0 warnings.
- I viewed two render previews. After the first, I moved the text block down 40 px (the URL down 10 px) to balance the empty space.
- PIL confirms the PNG is 1080 × 1920.

## Notes / deviations

- The host line uses coral, a brand colour. The contrast check passes on navy.
- In the story the URL is a different colour and size from the post, for the reason given above. Everything else matches.
- The headline layer still holds "Open Mic\nNight" (a line break instead of the space), the same as in round 1.

## Tool calls

25 tool calls in total, counting this report, the edit that fixed this count, and the hand-back:
- Vixl MCP: 16 (2 open, 1 inspect, 4 operations_apply, 3 check, 3 render_preview, 2 export_file, 1 operation_schema)
- ToolSearch: 2
- Bash: 6 (setup, copies, size check, writing this report, fixing this count)
- SubagentHandback: 1

Start: 22:25 UTC; end: about 22:27 UTC (by `date`).
