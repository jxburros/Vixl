# T09 · Tidewick Café winter menu campaign (lane V: Vixl MCP)

**Timing:** start 22:19:25 UTC, end 22:33:37 UTC on 2026-10-05 (about 14 minutes). About 96 tool calls in total: roughly 75 Vixl MCP calls, plus Bash, Read and ToolSearch.

## Files

| File | Size | Editable source | How it was made |
| --- | --- | --- | --- |
| `instagram-square.png` | 1080×1080 | `instagram-square.vixl` | Vixl MCP: document_create, font_pair, text_add ×5, operations_apply (shapes, gradient, text-style, moves), check, render_preview, export_file |
| `instagram-story.png` | 1080×1920 | `instagram-story.vixl` | same steps; centred vertical layout, text placed with `constrain center-x` |
| `x-post.png` | 1600×900 | `x-post.vixl` | same steps; text on the left, lamp on the right |
| `facebook-event.png` | 1920×1005 | `facebook-event.vixl` | same steps; text on the left, larger lamp on the right |
| `leaderboard.png` | 728×90 | `leaderboard.vixl` | same steps; one row: lamp, two-line text stack, coral divider, café name |
| `email-header.png` | 600×200 | `email-header.vixl` | same steps; café name, one-line headline, date line, lamp on the right |

A Python check confirmed every PNG has the exact pixel size above (all are RGBA).

## Shared system (the same in all six)
- **Palette:** only the five brand colors. Navy `#14263b` background; cream `#f7f1e5` for the headline and date line; lamp amber `#f2a541` for "Winter Menu", the lamp, the café-name label and the URL line; sea-foam `#a8d5c8` for the menu line and a wave band; coral `#e2725b` for a short accent rule (vertical in the leaderboard). The back wave band is a tint, `mix(#a8d5c8, #14263b, 45%)`. The lamp glow is a radial gradient from amber to transparent.
- **Type:** Vixl's curated "young-serif-rubik" pairing. Headline in Young Serif 400. Everything else in Rubik 400. Both are embedded in each .vixl file.
- **Motif:** a "harbor lamp" (an amber disc with a soft glow) and three layered wave bands along the bottom edge (muted teal, sea-foam, cream foam). They are vector path shapes, and each size has its own amplitude and wavelength. A small Python helper in my scratchpad only computed the numbers for those path strings; Vixl drew everything.
- Every layout was placed for its own canvas. Nothing is scaled, stretched or letterboxed.

## Copy
- Square, story, X and Facebook use all four lines, character for character. The headline wraps onto two lines: "The Winter Menu / is here", or "The Winter / Menu is here" in the story.
- The leaderboard and email header (the two smallest) drop lines 2 and 4, as the brief allows. They show the headline on one line plus "From Tuesday, December 1 at Tidewick Café".
- **Added text:** every size also has a small "TIDEWICK CAFÉ" label. This is brand-name text that is not in the copy block. Remove the `label` layer if only the given copy is allowed.

## Checks
- Story: `vixl_check` with reserved zones [0,0,1080,250] and [0,1670,1080,250] on all text layers found no problems. Text runs from y=380 to about y=1387. Only the lamp glow and the waves (not text) enter those zones.
- All sizes: no errors for bounds, overlap or contrast.
- The only remaining warnings are "legibility at 320 px thumbnail width" for the small Rubik lines on the X, Facebook, email and leaderboard files. I left them, because those formats are shown much larger than 320 px (the leaderboard and email at full size).
- On the square, the lamp glow is cut off by the canvas edge on purpose.

## Choices and caveats
- The menu line is never broken into a stacked list, so the copy stays exact. On the square it runs close to the right margin (it ends at x=1012 of 1080).
- I chose separate .vixl files per size over one file with artboards, because each layout is designed independently. The layer names are the same in every file (headline, label, menu, date, cta, rule, lamp, lamp-glow, wave-back/mid/front).
- Through MCP, text fonts can only be set with `vixl_text_add(font=...)`; the `font` field is rejected in operations. So text layers were added one by one per document.
- In Young Serif, the headline's line-height had to be set to 0.75 to get tight leading. Rich-text spans (the amber "Winter Menu") give the text box extra height, so spacing was set by eye from previews.
- One `operations_apply` call on the email header timed out (60 s) but had applied. I confirmed this with a fresh preview and the exported PNG.
- Unsure: Facebook event covers are cropped differently on different devices. The key text sits in the left and middle area, but the lamp is near the right edge.
