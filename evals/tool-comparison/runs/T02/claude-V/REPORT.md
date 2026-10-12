# T02 · Social post (lane V, Vixl)

## Files

| File | How it was made |
| --- | --- |
| `post.vixl` | Editable Vixl source. Made with the Vixl MCP tools: `vixl_document_create` (named size `instagram-portrait`, 1080 × 1350, background navy `#14263b`, font pairing `fraunces-work-sans`), then `layout-apply` `event-poster` (seed 7, dark mode, brand colours as the layout roles), then three `vixl_operations_apply` batches that rearranged and resized the text and added the decoration. Fonts are embedded (Fraunces 700 for the headline and date, Work Sans 400 for the rest). |
| `post.png` | `vixl_export_file` from `post.vixl`, 1080 × 1350 px, RGB PNG. |
| `REPORT.md` | This file. |

## Design

- Background: flat navy `#14263b`.
- Top: "TIDEWICK CAFÉ PRESENTS" as a small tracked kicker in lamp amber (30 px), then the headline "Open Mic Night" in Fraunces Bold, 160 px, cream `#f7f1e5`. It wraps onto two lines ("Open Mic" / "Night").
- To the right of "Night" there is a simple microphone built from shapes: a coral `#e2725b` capsule head with navy grille lines and a cream holder, stand and base. Behind it is a soft amber radial glow, like a lamp.
- Below that is the date, "Thursday, November 12 · 7–10 pm" (Fraunces Bold 48 px), in navy on a full-width lamp-amber band. It is the second level of the hierarchy.
- Next come the address in cream (38 px) and "Free entry · Sign up at the counter" in sea-foam `#a8d5c8` (38 px).
- Three sea-foam wave lines at lower opacity suggest the harbor. I left out anchors and ship wheels, as the brief asked.
- Bottom left: "tidewick.example" in cream, 30 px.
- All colours come from the brief's five brand colours. The only extra fill is the transparent amber glow.

## Copy

The document has exactly six text layers, and their text matches the brief character for character: É, the en dash in "7–10" and the middle dots. I checked this by reading the layer text back out of `post.vixl`, and the suite rules check it too. No other text appears. The headline's line break comes from wrapping in its text box; the stored text is still "Open Mic Night".

## Checks

- `vixl_check` passes with no `fix` findings. The one `review` finding left is `legibility.runt`, because "Night" sits alone on the headline's second line. I kept that two-line break on purpose. The glow is informational: it runs off the right edge on purpose.
- I attached a custom suite, `brief`, to the document (18 rules), and all of them pass:
  - Every text layer is at least 60 px inside the canvas.
  - Contrast is at least 4.5:1 for every text layer.
  - The hierarchy steps by at least 1.25× each time, from the headline through the date, then the address and CTA, then the kicker and URL.
  - There are exactly 6 text layers.
  - The exact copy strings are present.
- From `post.png` itself: the size is 1080 × 1350. The nearest text ink is 82 px from the left edge, and the top text ink is 92 px from the top. The URL ends about 1240 px down, which leaves about 110 px below it.

## Differences and choices

- The 60 px margin rule covers text, which is what the brief asks for. The decorative wave strokes are boxed at 66 px from the sides, but their round line caps reach to about 63 px from the left and right edges. They are decoration, not text.
- When I first wrote the hierarchy rule, it compared all six text layers in one chain at a 1.25 ratio. The address (38 px) and the CTA (38 px) are on purpose the same size, so a single chain can never pass. I split it into two chains with the same 1.25 ratio and did not lower the ratio. Then I changed the design (date 48 px, details 38 px, kicker and URL 30 px) to pass.
- I did not add a logo. The brief gave none, and making one up was out of scope.

## Unsure about

- Fraunces is a soft, slightly retro serif. I chose it for warmth, and it can read a little "vintage" rather than "coastal".
- The microphone is deliberately simple and flat. It may look clip-art-like next to the headline.
