# T02 · Social post (lane V, Vixl MCP)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `post.png` | 1080 × 1350 px RGBA PNG, the final post | `vixl_export_file` from `post.vixl` |
| `post.vixl` | Editable Vixl source (26 layers; all text is live text) | `vixl_document_create(size="instagram-portrait", background="#14263b")`, `vixl_font_pair`, `vixl_operations_apply`, `vixl_text_add` |
| `REPORT.md` | This report | written by hand |

## Design

- **Fonts:** the curated pairing `young-serif-rubik` (Young Serif 400 for the headline, Rubik 400 for everything else), downloaded and embedded by `vixl_font_pair`.
- **Background:** navy `#14263b`, with a faint radial amber glow at the top.
- **Imagery:** a string of nine café festoon lamps (cream wire, cream sockets, amber bulbs with an outer glow) hangs across the top. At the bottom are a coral wave line and a sea-foam wave band. There are no anchors or ship wheels. I built every shape from Vixl `shape` operations (path, ellipse, rounded-rectangle, capsule). A small Python script only worked out the bulb positions along the curve and the wave path strings.
- **Hierarchy, top to bottom:** all text is centred. Text colours on navy all pass contrast; the URL is navy on sea-foam.

| Line | Font | Size | Colour | Top edge |
| --- | --- | --- | --- | --- |
| "TIDEWICK CAFÉ PRESENTS" (kicker) | Rubik | 36 px | sea-foam | y=300 |
| "Open Mic Night" (headline) | Young Serif | 180 px | cream | y=365–800 |
| short divider (shape, no text) | – | – | coral | y=838 |
| "Thursday, November 12 · 7–10 pm" | Rubik | 50 px | amber | y=888 |
| "12 Quay Street, Port Ellery" | Rubik | 40 px | cream | y=968 |
| "Free entry · Sign up at the counter" | Rubik | 36 px | sea-foam | y=1032 |
| "tidewick.example" | Rubik | 38 px | navy, on the sea-foam band | y=1252 |

## Checks

- `vixl_check(safe_area=60)` on the six text layers: passed, with 0 errors and 0 warnings. That covers bounds, overlap, contrast, safe area, legibility and fonts.
- The full-document check gave only 2 warnings, both about the decorative `lamp-glow` gradient. It runs past the canvas edge on purpose, so I left it.
- I checked the output size with PIL: 1080 × 1350.
- I looked at the full render preview before exporting.

## Deviations / choices

- **Headline line break:** at 180 px, "Open Mic Night" does not fit on one line inside the 60 px margins. I set the headline layer's text to `"Open Mic\nNight"`. The words and punctuation are unchanged, but the layer's text holds a line break where the copy has a space.
- **Decoration near the edges:** the lamp wire, the glow and the waves run to the canvas edges. The 60 px margin applies to text only, and all text is inside it.
- **Kicker letter-spacing:** I set `spacing: 6` on the kicker, but its bounds did not change. It may have had no visible effect, which does not matter for the brief.
- **Copy:** all six lines are used, with the exact spelling: É, the en dash in "7–10" and the middle dots. There is no other text.

## Unsure about

- I trust that Rubik renders É, – and · correctly (the preview shows them correctly), but I did not run pixel-level OCR.

## Timing

Start: Mon Oct 5 22:17:54 UTC 2026. End: Mon Oct 5 22:19:42 UTC 2026 (about 2 minutes by the `date` clock; actual wall time may be longer because of model latency). Tool calls: 29, including writing this report and the hand-back.
