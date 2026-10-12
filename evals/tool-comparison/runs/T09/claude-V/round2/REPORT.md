# T09 round 2: copy change (lane V, Vixl)

## What changed

- **Headline:** "The Winter Menu is here" became **"Winter Menu: now pouring"** on all six sizes.
- **Menu items:** "Smoked maple latte" became **"Spiced honey cortado"**. The line now reads "Gingerbread flat white · Spiced honey cortado · Cardamom bun". This applies to the square, story, X post and Facebook event. The leaderboard and email header never carried the items line (see the round-1 report), so only their headline changed.
- Everything else (palette, fonts, motif, date and URL lines, brand label, layer structure) is unchanged.

## How

1. I copied the six round-1 `.vixl` sources into `round2/` with `cp`. Vixl autosaves every edit, so I edited only these copies, and the round-1 files were not touched.
2. I opened each copy with `vixl_document_open` and changed the existing live text layers in place with `vixl_operations_apply` `text-set` (on the `headline` and `items` layers). I ran each batch with `check=true, preview=true`.
3. I made layout fixes where the new copy caused problems. On three sizes the new headline is a little wider than the old one, so it wrapped to three lines with "pouring" alone on the last line. That pushed it into the coral rule and the items line: `vixl_check` reported a `overlap.text-text` fix and a `legibility.runt` review on the square, story and Facebook event, plus contrast fixes on Facebook where the text ran over the waves. To fix this I reduced the headline size so it sets as two lines, "Winter Menu: / now pouring", inside the same text box:
   - Square: 124 → 112 px. The amber lamp also moved from (800, 90) to (840, 60) because its glow touched the colon (`overlap.text-object` review).
   - Story: 136 → 128 px. The text still sits between y = 540 and y = 1400, clear of the top and bottom 250 px.
   - Facebook event: 163 → 156 px.
   - The X post, leaderboard and email header needed no layout change. Their headline already fit on the same number of lines as before.
4. After the fixes, `vixl_check` reported **no fix or review findings** on all six. What remains is informational: the intentional wave bleed (`allow_crop`) and small text at 320 px thumbnail width, the same as round 1.
5. I exported each PNG with `vixl_export_file` to the same file names. A Pillow check confirmed the sizes: 1080×1080, 1080×1920, 1600×900, 1920×1005, 728×90 and 600×200, all RGB.

I drew no pixels and wrote no SVG or HTML. The only script was the Pillow size check.

## Files in round2/

`instagram-square`, `instagram-story`, `x-post`, `facebook-event`, `leaderboard`, `email-header`: each has an exported `.png` and its editable `.vixl` source.

## Notes

- **Headline sizes changed:** the three smaller headline sizes keep the headline clearly dominant, but the type is slightly smaller than in round 1 on the square, story and Facebook event.
- **Line breaks:** the two-line break comes from the text box width, not a manual line break, the same as round 1.
- **Items line width:** on the square, the items line is now about 928 px wide, still inside the 54 px safe margin.
