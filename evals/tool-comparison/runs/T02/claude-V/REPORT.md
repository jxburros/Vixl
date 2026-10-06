# T02 · Social post — Lane V (Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `post.png` | The Instagram post: 1080 × 1350 px, RGB PNG (I checked the size with PIL) | Exported from `post.vixl` with `vixl_export_file` |
| `post.vixl` | The editable Vixl source. Every layer is live: 6 text layers, plus shape and gradient layers | Built only with Vixl MCP tools (listed below) |
| `REPORT.md` | This report | Written by hand |

## How it was made (all through Vixl MCP)

1. I called `vixl_guide` with the brief. Then I made the document with `vixl_document_create(size="instagram-portrait")`, which gave 1080×1350 with a 60 px safe area.
2. Fonts: `vixl_font_pair("fraunces-work-sans")` set the headline font to Fraunces 700 and the body font to Work Sans 400. I added Work Sans 600 with `vixl_font_install` for the kicker, date line, button text and URL. All three are open-licensed Google Fonts and are embedded in the `.vixl`.
3. I applied the `event-poster` layout first, using the brand colours as roles. I kept its navy `background` layer and swatches. Then I removed its text and shape layers and rebuilt the composition by hand with `vixl_operations_apply`. The layout made the date block the main element, which pushed "Open Mic Night" into second place, and the brief asks for the headline to lead.
4. Hierarchy, from top to bottom:
   - kicker `TIDEWICK CAFÉ PRESENTS`: Work Sans 600, 36 px, amber
   - headline `Open Mic Night`: Fraunces 700, 176 px, cream. It wraps to two lines ("Open Mic" / "Night") in a 900 px text box, but the stored text is the single exact string.
   - a short amber rule
   - date line: Work Sans 600, 54 px, amber
   - address: Work Sans 400, 46 px, cream
   - `Free entry · Sign up at the counter`: Work Sans 600, 38 px, navy, on a coral pill
   - `tidewick.example`: Work Sans 600, 38 px, sea-foam
5. Decoration, all vector shapes and with no text in it:
   - a hanging café lamp at top right: a cream cord, a coral half-circle shade, and an amber bulb with an outer glow
   - a soft amber radial "lamp-glow" gradient behind the lamp
   - three sea-foam wave lines along the bottom for the harbour
   - no anchors and no ship wheels
6. QA:
   - `vixl_check(safe_area=60)` found no errors and no warnings. Before that, it flagged the kicker as too small at thumbnail width at 32 px, so I raised it to 36 px.
   - The only findings left are informational. The waves, lamp cord and glow run off the canvas on purpose, and I marked them `layer-intent allow_crop` / `decoration`.
   - All text layers passed the WCAG contrast check, including navy text on coral.
   - I looked at it with `vixl_render_preview`, including a zoomed view to confirm that É, the en dash and the middle dots render correctly.

## Copy and margins

- The copy is used exactly as given, one text layer per line: `TIDEWICK CAFÉ PRESENTS`, `Open Mic Night`, `Thursday, November 12 · 7–10 pm`, `12 Quay Street, Port Ellery`, `Free entry · Sign up at the counter`, `tidewick.example`. It uses U+00C9 É, U+2013 en dash and U+00B7 middle dot. There is no other text.
- Text bounds from `vixl_document_inspect` are all inside the 60 px margin:
  - leftmost text starts at x = 90
  - rightmost text box ends at x = 990 (the headline box; its ink ends near x ≈ 910)
  - the widest single line (the date line) ends at x = 969
  - topmost text is at y = 130
  - lowest text ends at y = 1146
- Only decoration reaches the canvas edges.

## Choices and things I did differently

- The brief doesn't say what the editable source should be called, so I named it `post.vixl`.
- I used the `event-poster` layout only as a starting point. The final layout is placed by hand, with its swatches and the navy background kept.
- The brand colours are used as given. Navy is the background, cream is the headline and address, amber is the kicker, date and lamp, coral is the button and lamp shade, and sea-foam is the URL and waves.

## Things I'm unsure about

- The headline's line break ("Open Mic" / "Night") comes from wrapping in the text box, not a typed newline. I think this keeps the copy exact, but a checker that reads the image's text line by line will see two lines.
- I couldn't confirm the 60 px margin from the pixels alone, because the decoration deliberately runs to the edges. The margin numbers above come from the text layer bounds.
- The lamp is a simple, flat illustration.
