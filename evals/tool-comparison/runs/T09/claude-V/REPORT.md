# T09 · Tidewick Café winter menu campaign (lane V: Vixl)

All visual work was done with the Vixl MCP tools (`vixl_document_create`, `vixl_font_pair`,
`vixl_font_install`, `vixl_operations_apply`, `vixl_adapt_layout`, `vixl_check`,
`vixl_render_preview`, `vixl_export_batch`). No pixels, SVG or HTML were drawn by hand. The only
script was a Python/PIL check that read back the exported PNG sizes.

## Files

| File | Size | How it was made |
| --- | --- | --- |
| `instagram-square.png` | 1080 × 1080 | Exported from `instagram-square.vixl`, the master design built from scratch with Vixl operations |
| `instagram-story.png` | 1080 × 1920 | `vixl_adapt_layout` copy of the master, then re-laid out by hand for the tall format: larger type, lamp higher, five tide lines instead of three |
| `x-post.png` | 1600 × 900 | Adapted copy, re-laid out for landscape: text on the left, lamp at top right, wider tide lines |
| `facebook-event.png` | 1920 × 1005 | Adapted copy, re-laid out for landscape. Here the menu line fits on one line |
| `leaderboard.png` | 728 × 90 | Adapted copy, rebuilt as a single strip: lamp on the left, headline and date in the middle, a short stack of tide lines on the right |
| `email-header.png` | 600 × 200 | Adapted copy, rebuilt: headline on one line, coral rule, date, lamp at top right, tide lines across the bottom |
| `instagram-square.vixl`, `instagram-story.vixl`, `x-post.vixl`, `facebook-event.vixl`, `leaderboard.vixl`, `email-header.vixl` | — | The editable Vixl sources, one per size. Text stays live text, shapes stay vector, and the fonts are embedded |

## Shared system (the same in all six)

- **Palette:** only the five brand colors, saved as swatches: navy `#14263b` (background), cream
  `#f7f1e5` (headline and URL), sea-foam `#a8d5c8` (menu line), amber `#f2a541` (date line and
  lamp), coral `#e2725b` (rule under the headline).
- **Type:** Fraunces 700 for the headline. Work Sans 400 for the menu and URL lines, Work Sans 600
  for the date line. All are open-licensed Google Fonts, installed and embedded through
  `vixl_font_pair` (pairing `fraunces-work-sans`) and `vixl_font_install`.
- **Motif:**
  - A glowing amber "harbor lamp" disc: an ellipse with Vixl's `glow` look, over a soft amber
    radial halo.
  - Parallel wavy "tide lines" (Vixl `wave` shapes with round caps) in sea-foam, coral and amber.
  - A short coral rule under the headline (left out of the leaderboard only, for lack of room).

## Copy

The text strings are the four brief lines exactly, including the `·` separators and "Café".

- The square, story, X post and Facebook event use all four lines. In the square, story and X post
  the menu line wraps onto two lines inside its text box, but the stored text is a single line.
- The leaderboard and the email header use only the headline and the date line (lines 1 and 3).
  The brief allows dropping lines 2 and 4 in the two smallest sizes.
- In the leaderboard and the email header the headline is on one line. In the four larger sizes it
  breaks after "Winter" (a line break inside the headline text layer).

## Deviations and things I'm unsure about

- **Story safe zones:** no text is in the top 250 px or the bottom 250 px. Text runs from y≈680
  (headline) to y≈1288 (URL). The decoration does enter those zones: the lamp halo starts at y=50,
  and tide lines 3–5 sit at y≈1660–1890. Running `vixl_check` with those zones marked as reserved
  flags these decoration layers. I kept them on purpose, because the brief restricts only text.
- **Thumbnail-legibility warnings left in place:** `vixl_check` scores text by how it reads when
  the whole image is shrunk to 320 px wide.
  - The X post and Facebook event still get warnings for the menu, date and URL lines (44–50 px
    type). Reaching the tool's target would need about 50–60 px type, which would crowd the layouts.
    Both formats are normally shown much wider than 320 px.
  - The leaderboard date (18 px) still gets one. Banner ads are shown at their real size.
  - The email header date was raised to 19 px, as the check asked. The square passes with no
    warnings.
- **Starting point for the other sizes:** `vixl_adapt_layout` made the first version of the other
  five sizes. I then moved, resized and re-set every layer in each one, so no layout is a stretched
  or letterboxed copy. The tide lines were redrawn with their own wavelength and amplitude for each
  width.
- There are no images or logos, and the brief supplied none. The lamp and tide lines are my own
  graphic interpretation of "warm, coastal, unfussy".
- The PNGs are opaque RGB at exactly the sizes the brief lists (checked with PIL).
