# T02 round 2 · Lane V (Vixl)

## Files in `round2/`

| File | What it is |
| --- | --- |
| `post.png` | Updated Instagram post, 1080 × 1350, RGB |
| `post.vixl` | Editable source for the post. It started as a byte copy of round 1's `post.vixl` and was then edited with Vixl |
| `story.png` | New story version, 1080 × 1920, RGB |
| `story.vixl` | Editable source for the story, made from the updated `post.vixl` |
| `REPORT.md` | This report |

Nothing outside `round2/` was changed. The only file operation outside Vixl was `cp post.vixl round2/post.vixl`, so that round 1 stays untouched.

## What changed in the post (all with `vixl_operations_apply`)

- **Date.** `text-set` on the `date-time` layer, now `Thursday, November 19 · 7–10 pm` (U+00B7 middle dot, U+2013 en dash). The font, size and colour are unchanged.
- **Host line.** I added a new text layer, `host`, reading `Hosted by Mara Quinn`. It's set in Work Sans 400 (the body role), 44 px, sea-foam `#a8d5c8`, at x 90, y 674. That puts it directly under the headline: the headline's ink ends at y ≈ 637. It's one step below the date in weight and colour, so the headline still leads.
- **Reflow to make room.** The lower block moved down: rule +17 px, date and address +15, pill and button text +12, URL +8. The URL now ends at y 1154, still above the waves at 1210.
- The kicker, headline, lamp, waves and background did not move. A pixel diff of round 1 against round 2 `post.png` shows changes only inside x 90–967, y 674–1154.
- **Checks.** `vixl_check(safe_area=60)` passed with 0 errors and 0 warnings. The only findings are informational, about the decoration I marked as bleeding off the edge on purpose in round 1. I also looked at the result with `vixl_render_preview`.

## Story version (1080 × 1920)

1. `vixl_adapt_layout(sizes=[1080x1920])` made `story.vixl` from the updated post. It stretched the background and kept the waves anchored to the bottom (now y 1780–1910). It left the kicker at y 130, inside the top band, and spaced the rest unevenly, so I re-placed the text by hand.
2. I edited the text with `vixl_operations_apply`:
   - **Headline:** 188 px, up from 176, in a 900 × 470 box. It still breaks "Open Mic" / "Night" by wrapping, and the stored text is still the exact single string.
   - **Host, address, button text and URL:** 48 / 48 / 40 / 40 px.
   - **Date:** stays at 54 px. I tried 58 px, but at that size the line ran past the 60 px side margin and `vixl_check` flagged it, so I went back.
   - **Pill:** widened to 745 × 92 to fit the larger button text.
   - **Stack:** kicker 420, headline 530 (ink to 943), host 1000, rule 1108, date 1152, address 1236, pill 1366–1458, URL 1518–1555. The block is roughly centred in the band between the two reserved strips.
3. The lamp now hangs lower: the cord runs 0–350, the shade sits at 340 and the bulb ends at 428. The glow moved with it. It's decoration only, with no text, and it sits above and to the right of the headline.
4. **Checks:**
   - `vixl_check(safe_area={left:60, right:60, top:250, bottom:250})` passed with 0 errors and 0 warnings. Only the decoration findings remain, all informational.
   - All text sits in **y 420–1555**, well clear of the top 250 px (0–250) and the bottom 250 px (1670–1920).
   - The only things in those bands are the lamp cord, shade and glow, the background and the waves, and none of them contain text.
   - Contrast passed for every text layer.
5. Exported with `vixl_export_file`. I checked the size and mode with PIL: 1080 × 1920, RGB.

## Copy in both pieces (one text layer per line)

1. `TIDEWICK CAFÉ PRESENTS`
2. `Open Mic Night`
3. `Hosted by Mara Quinn`
4. `Thursday, November 19 · 7–10 pm`
5. `12 Quay Street, Port Ellery`
6. `Free entry · Sign up at the counter`
7. `tidewick.example`

## Notes

- I treated "directly under the headline" as the next line of text, set above the amber rule, so the rule still introduces the event details.
- The host line uses sea-foam, the same as the URL. That keeps it apart from the amber date and the cream address.
