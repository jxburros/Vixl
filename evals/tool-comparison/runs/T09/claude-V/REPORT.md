# T09 · Tidewick Café winter menu campaign: run report (lane V, Vixl)

All visual work went through the Vixl MCP tools (`vixl_document_create`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview` via `preview=true`, `vixl_export_file`). I drew no pixels and wrote no SVG or HTML. The only script was a Pillow check of the PNG sizes after export.

## Files

| File | Size | How it was made |
| --- | --- | --- |
| `instagram-square.png` | 1080 × 1080 | Exported from `instagram-square.vixl` |
| `instagram-story.png` | 1080 × 1920 | Exported from `instagram-story.vixl` |
| `x-post.png` | 1600 × 900 | Exported from `x-post.vixl` |
| `facebook-event.png` | 1920 × 1005 | Exported from `facebook-event.vixl` |
| `leaderboard.png` | 728 × 90 | Exported from `leaderboard.vixl` |
| `email-header.png` | 600 × 200 | Exported from `email-header.vixl` |
| `*.vixl` (6 files) | — | Editable sources: one layered Vixl document per size. Text is live text and shapes are vectors |

I checked the PNG sizes with Pillow after export. All six match the brief exactly and are RGB.

## The shared look

- **Palette:** only the five brand colours, each also saved as a document swatch (`@navy`, `@amber`, `@seafoam`, `@coral`, `@cream`). Every canvas has a navy `#14263b` background. The headline is cream, the menu items line is sea-foam, the date is cream (sea-foam on the two small sizes), the URL and the "TIDEWICK CAFÉ" label are amber, and the accent rule is coral.
- **Type:** the curated pairing `fraunces-work-sans`, embedded in every document. Fraunces 700 is used for the headline and Work Sans 400 for everything else.
- **Motif:** an amber "harbour lamp" circle with a soft outer glow, plus layered harbour waves: a translucent sea-foam back wave, a solid sea-foam wave, a coral crest line and a cream foreground wave. A short coral rule separates the headline from the details. It is horizontal on the large sizes and becomes a vertical tick on the two small ones.
- **Layouts are drawn for each shape, not scaled.** I built each size separately with its own coordinates, wave paths and type sizes:
  - Square: the text column sits top-left, the lamp top-right and the waves along the bottom.
  - Story: the headline is set larger and the details wrap over two lines, centred vertically. The waves are taller. All text sits between y = 540 and y = 1400, well clear of the top and bottom 250 px. `vixl_check` with those two bands as `avoid` zones on the text layers passed.
  - X post and Facebook event: wide left text column with a two-line headline, the lamp on the right and a shallow wave band.
  - Leaderboard and email header: the text is on the left, and the lamp and waves form a small scene rising from the bottom-right corner.

## Copy

- Square, story, X post and Facebook event use all four lines, word for word: "The Winter Menu is here", "Gingerbread flat white · Smoked maple latte · Cardamom bun", "From Tuesday, December 1 at Tidewick Café" and "See the menu at tidewick.example". The text is stored without manual line breaks. Where a line wraps (the headline on every size, and the items and date lines on the story), it wraps inside a text box (`text-layout` width).
- Leaderboard (728 × 90) and email header (600 × 200) are the two smallest sizes. As the brief allows, they drop the second line (menu items) and the fourth line (URL), and show only the headline and the date line.

## Differences from the brief and choices I made

- **Extra text:** I added a small "TIDEWICK CAFÉ" brand label (uppercase, tracked, amber) above the headline on the square, story, X post, Facebook event and email header. It isn't one of the four copy lines; it is the café's name used as branding. The leaderboard leaves it out because there is no room.
- **Rendered case:** the label's text is stored as "Tidewick Café" and drawn in capitals with `text_transform`.
- **No logo:** the brief gives no logo, so none was made. The lamp-and-waves motif carries the brand.
- **No photos:** there are no photos or AI imagery; the artwork is all vector shapes.
- **No separate master file:** the "editable source" is six `.vixl` documents, one per size, not a single master with artboards. I composed each size by hand rather than with `vixl_adapt_layout`, so that each layout is designed for its shape.

## Checks

Before each export, `vixl_check` (the default set: bounds, overlap, contrast, safe area, legibility, blanks, placeholders, fonts and more) reported **no fix or review findings** on all six documents. What remained was informational:

- **Waves at the edges:** the wave layers deliberately bleed off the canvas edges and are marked with `layer-intent allow_crop`.
- **Thumbnail-size text:** small text (the label, items line, date or URL, depending on size) would be under 10 px if the image were shrunk to a 320 px thumbnail.

I did not attach custom check suites (`suite-set`); I relied on the built-in checks, the story's avoid-zone check and the previews.

## Things I'm unsure about

- **Thumbnail legibility:** the 17 px date on the leaderboard and the 16 px date on the email header are readable at full size but small. The checker marks them informational only.
- **Facebook overlays:** the Facebook event layout keeps text in the left ~70 % and above the waves. I don't know how Facebook's own overlays crop the image on every device.
- **How close two layouts are:** the X post (16:9) and Facebook event (≈1.91:1) layouts are close relatives: both use a left column with the lamp on the right. Their proportions, type sizes and wave paths differ, but the structure is the same.
- **Outer-glow strength:** the glow (`layer-style outer-glow`, blur scaled to each size) is subtle. On the smallest sizes it is barely visible.
