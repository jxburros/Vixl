# T09 round 2: copy changes (lane V, Vixl MCP)

**Timing:** 22:34 to about 22:36 UTC on 2026-10-05 (about 3 minutes).
**Tool calls:** 57 in total: 49 Vixl MCP calls, 4 Bash, 3 ToolSearch and 1 SubagentHandback.
The Vixl calls were 6 document_open, 10 document_inspect, 1 operation_schema, 8 operations_apply, 6 check, 6 render_preview, 6 export_file and 6 document_close.

## What changed
1. **Headline:** "The Winter Menu is here" became **"Winter Menu: now pouring"** in all six files.
   - "Winter Menu" stays in lamp amber, as in round 1. The colon and "now pouring" are cream.
   - Square, story, X and Facebook break it onto two lines: "Winter Menu:" / "now pouring". The leading is still 0.75.
   - Leaderboard and email header keep it on one line.
2. **Menu line:** "Smoked maple latte" became **"Spiced honey cortado"**. The line now reads "Gingerbread flat white · Spiced honey cortado · Cardamom bun" in the four sizes that have a menu line: square, story, X and Facebook.
   - **Leaderboard and email header have no menu line, so there was nothing to replace.** In round 1 they dropped copy lines 2 and 4, as the brief allows. I did not add a menu line to them, because it would be new copy in two very small formats. If the cortado has to appear in all six, a menu line must be added to those two files.

## Size changes needed to keep the layouts clean
The new item name is longer, and so is the one-line headline.
- **Square:** the menu line went from 33 px to 31 px. Without that change it would have ended at x=1043 of 1080. It now ends at x=985.
- **Story:** the menu line went from 34 px to 32 px, so it keeps a margin of about 73 px.
- **Email header:** the headline went from 38 px to 34 px. At 38 px the longer headline ran under the lamp (x=500). It now ends at x=490.
- **X, Facebook and leaderboard:** no size changes were needed.

Nothing else changed: no positions, colors, fonts, motif, label, date or CTA.

## How
- I copied the six round-1 `.vixl` files into `round2/` with Bash and edited only those copies. Nothing outside `round2/` was touched.
- Each copy was opened in Vixl with an explicit `document=` path.
- **Headline:** one `rich-text` operation per file on the existing `headline` layer. It rewrote the spans and kept the layer's embedded Young Serif font and paragraph settings.
- **Menu:** `text-set` on the `menu` layer, with a size change where listed above.
- I ran `vixl_check` on all six. Every file passed with 0 errors. On the story I reused the round-1 reserved zones (top and bottom 250 px) for the text layers, and the result was clean.
- The remaining warnings are the same kinds as in round 1: the lamp glow is cut off by the canvas edge on purpose, and small Rubik lines warn about legibility at 320 px thumbnail width. On the square and story, the shrunk menu line now also warns at 9.2 px and 9.5 px, against a 10 px target.
- I looked at a render preview of every file, then used `vixl_export_file` to write the full-size PNGs.
- A Python check confirmed the PNG sizes: 1080×1080, 1080×1920, 1600×900, 1920×1005, 728×90 and 600×200, all RGBA.

## Files in round2/
instagram-square, instagram-story, x-post, facebook-event, leaderboard and email-header, each as `.png` plus its editable `.vixl` source.
