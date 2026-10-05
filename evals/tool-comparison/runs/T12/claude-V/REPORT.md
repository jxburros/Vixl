# T12 · Animated intro (Tidewick Café): lane V (Vixl)

**Timing:** started 22:16:24 UTC, ended 22:23:05 UTC (about 7 minutes), 2026-10-05. About 37 tool calls, counting this report and the handback.

## Files

| File | How it was made | Verified |
| --- | --- | --- |
| `intro.vixl` | The editable Vixl source. Built with `vixl_document_create` (1080×1080, background `#14263b`), `vixl_operations_apply` (shapes, gradients, groups, clips, pivots and keyframes), `vixl_font_pair` and `vixl_text_add`. The timeline is 6 s at 30 fps. | n/a |
| `intro.mp4` | `vixl_export_timeline` (mp4, 30 fps, scale 1) | ffprobe: h264, yuv420p, 1080×1080, 30/1, 180 frames, 6.000 s, 140 KB |
| `intro.gif` | `vixl_export_timeline` (gif, scale 0.5, 25 fps, 256 colours) | Pillow: 540×540, loop=0 (loops forever), frame durations add up to 6000 ms, 699 KB |
| `intro-last-frame.png` | `vixl_export_file` with `time=5.967s`, which is frame 179/180 and the last frame of the MP4 | 1080×1080. Average pixel difference from the MP4's actual last frame, extracted with ffmpeg, is about 1.6/255 (H.264 compression) |
| `REPORT.md` | this file | |

## What happens when

- **0.0–1.5 s, waves.** There are three filled wave paths. Back to front they are sea-foam mixed 62% into navy, sea-foam mixed 35% into navy, and plain sea-foam. Each wave is clipped to a white gradient layer set to multiply blend, so the gradient itself doesn't show; it only acts as a reveal mask. The mask slides left to right with ease-in-out-cubic and has a soft leading edge. The three waves are staggered: back 0–1.1 s, middle 0.2–1.3 s, front 0.4–1.5 s.
- **1.0–3.0 s, lighthouse.** The lighthouse is a group of simple shapes: a cream tower with two amber bands, a gallery, an amber lantern, a roof and a finial. It sits between the back wave and the middle wave, so it rises from behind the sea. It moves up 470 px with ease-in-out-cubic and fades in from 1.0 to 1.7 s.
- **From 2.0 s to the end, beam.** The lamp glow and the beam fade in from 2.0 to 2.5 s. The sweep is a fake 3D rotation: two beam wedges, one pointing right and one pointing left, each pivoted at the lamp. Their `scale-x` alternates between 1 and 0 with sine easing, so the beam narrows toward the viewer and widens on the other side. One full back-and-forth cycle takes 2.67 s. The beam is mid-sweep at 6.0 s, at full extension to the left.
- **2.0–3.5 s, wordmark.** "Tidewick Café" in Young Serif 124 px, cream, slides up 70 px (ease-out-cubic) while fading in from 2.0 to 3.2 s (ease-in-out).
- **3.0–4.5 s, tagline.** "Coffee by the harbor" in Rubik 48 px, sea-foam, uses the `typewriter` preset: 21 text keys, one character at a time.
- **4.5–6.0 s, hold.** Everything stays visible and the beam keeps sweeping.

## Choices and differences from the brief

- **Fonts.** I used the Young Serif / Rubik pairing ("warm, retro, friendly"). The MCP server rejects the `font` field on text operations, so I added the text with `vixl_text_add`, using the registered font names.
- **Beam sweep.** Vixl's `scale-x` can't go below 0, so a single mirrored beam wasn't possible. I used two wedges instead, which together make one beam that sweeps both ways.
- **Wave draw-in.** I read "draw in" as a left-to-right wipe reveal of filled wave shapes, not a stroke being traced, because Vixl can't animate a path's stroke length.
- **Layout.** The lighthouse is centred, and the wordmark and tagline are centred above it in the top third. The beam stays below the text.
- **GIF frame rate.** The GIF is 25 fps, not 30, because GIF frame delays are counted in hundredths of a second (25 fps is exactly 4 per frame). Pillow reads 147 frames rather than 150, probably because identical consecutive frames were merged; the total duration is still 6.0 s. The GIF is well under 5 MB.
- **Check warnings.** `vixl_check` passed with no errors. Its 6 warnings are only the reveal-mask layers, which are deliberately wider than the canvas.

## Unsure about

- The wave masks fade over a soft gradient edge, so during the draw-in a translucent band shows at the leading edge (visible at 0.4 s and 0.8 s). This is intentional, but it could read as a fade rather than a crisp draw.
- When the beam passes through "facing the viewer" (scale-x near 0), it briefly disappears. That is the intended effect, but a viewer might expect a beam that rotates in the plane of the picture.
- I checked the motion on a 16-frame contact sheet and in the final frame. I did not watch the MP4 or GIF frame by frame.
