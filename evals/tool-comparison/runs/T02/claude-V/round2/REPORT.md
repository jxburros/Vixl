# T02 round 2: date change, host line, story version (lane V, Vixl)

## Files

| File | What it is |
| --- | --- |
| `post.vixl` | Editable source for the 1080 × 1350 post. I copied the round-1 `post.vixl` here, then edited it with `vixl_operations_apply`. |
| `post.png` | `vixl_export_file` from `post.vixl`, 1080 × 1350 px. |
| `story.vixl` | Editable source for the story. `vixl_adapt_layout` made it from the updated `post.vixl` at 1080 × 1920, then I moved layers with one `vixl_operations_apply` batch. |
| `story.png` | `vixl_export_file` from `story.vixl`, 1080 × 1920 px. |
| `REPORT.md` | This file. |

I changed nothing outside `round2/`.

## Changes to the post

- **Date:** I used `text-set` on the existing `date` layer, so it keeps its font, size and colour and stays on the amber band. It now reads "Thursday, November 19 · 7–10 pm" (en dash, middle dot).
- **Host line:** I added a new text layer `host` reading "Hosted by Mara Quinn" directly under the headline, at x = 82 and y = 508:
  - It uses the same Work Sans font, at 38 px.
  - It is lamp amber (`@accent`), the same colour as the kicker, so the top block reads kicker / headline / host.
  - The headline's ink ends at about y 475, so the gap is about 33 px. The line sits well clear of the microphone on the right and of the date band below (y 650).
- Nothing else moved.

## Story version (1080 × 1920)

- It has the same layers, copy, fonts, colours and decoration as the post, at the same scale (1.0).
- `vixl_adapt_layout` re-anchored the post onto the tall canvas. That pushed the URL to y 1782, inside the bottom 250 px. So I respaced the lower half:
  - date band at y 900
  - address at 1070
  - CTA at 1132
  - waves at 1330, 1386 and 1442
  - URL at 1560
- The top block (kicker, headline, host, mic) stays where adapt-layout put it: kicker at y 303, headline at 371, host at 719.
- Text runs from y 303 (kicker) to y 1589 (URL). That clears the 250 px zones at the top and bottom by 53 px and 81 px.

## Checks

- **Suite.** I replaced the document's `brief` suite with the round-2 requirements (25 rules). It passes on both `post.vixl` and `story.vixl`. The rules cover:
  - all seven copy strings, character for character, plus exact-match rules for the date and host lines;
  - a rule that forbids "November 12";
  - exactly 7 text layers;
  - every text layer at least 60 px inside the canvas;
  - contrast of at least 4.5:1 for every text layer;
  - three hierarchy chains at a 1.25 ratio, including headline > date > host > kicker;
  - `host` below the headline ink, left-aligned with it, 12–48 px away; above the date band; at least 40 px from the microphone.
- **`vixl_check`.** There are no `fix` findings on either file. The only `review` finding is `legibility.runt`, because "Night" sits alone on the headline's second line. That break was deliberate in round 1 and I kept it.
- **Story zones.** I ran `vixl_check` on the seven text layers with `avoid` zones `[0,0,1080,250]` and `[0,1670,1080,250]`, and it found nothing. Then I read `story.png` back with a short script: there are 0 non-background pixels in the top 250 rows and in the bottom 250 rows. The first ink is at row 303 and the last at row 1588.
- **Sizes.** I read both PNG sizes back: 1080 × 1350 and 1080 × 1920.

## Notes and choices

- I first tried to put the story's zone limits in the suite as `assert` rules (`layer.kicker.bounds.top >= 250`), but that expression is not supported. I ran it only as a dry run and never saved it. Instead, the zones are checked with `vixl_check avoid=` and by reading the pixels, as described above.
- The story is the post re-spaced, not re-composed. There is a lot of empty navy in the top and bottom 250 px. That is intended, because those zones are where the platform puts its own interface.
- I left `story.vixl` next to `story.png` so the story stays editable.
