# T12 · Animated intro (lane V, Vixl)

All visual work was done with the Vixl MCP tools (`mcp__vixl__*`). Python, ffprobe and ffmpeg were used only to read and check the outputs.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `intro.vixl` | Editable source: 21 layers (two groups) plus the keyframe timeline (6000 ms, 30 fps) | `vixl_document_create` (1080×1080, background `#14263b`), `vixl_font_pair` (`fraunces-work-sans`), then two `vixl_operations_apply` batches (artwork, then motion) and one fix batch for the wave boxes |
| `intro.mp4` | 1080×1080, H.264 (High), yuv420p, 30 fps, 180 frames, 6.000 s, 130,346 bytes | `vixl_export_timeline` (fps 30, quality 90) |
| `intro.gif` | 540×540, loops forever (loop=0), 176 frames, 1,085,274 bytes (about 1.09 MB, under the 5 MB limit) | `vixl_export_timeline` (scale 0.5, fps 30, 256 colours, no dither) |
| `intro-last-frame.png` | 1080×1080 RGB, the frame at t = 5966.667 ms (frame 180 of 180) | `vixl_export_file` with `time=5966.667` |
| `REPORT.md` | This file | |

Checked with ffprobe and PIL: the MP4 specs are as listed above. The PNG matches the MP4's decoded last frame (mean absolute difference 1.24/255, which is H.264 compression noise).

## The design

- **Background:** a flat navy `#14263b` canvas.
- **Waves:** three stroked sine-wave paths in sea-foam `#a8d5c8` at opacity 0.4, 0.7 and 1.0 (back to front), with round caps, across the bottom third (y ≈ 790–1000). They run past both canvas edges on purpose.
- **Lighthouse:** built from vector shapes (paths, rectangles, a triangle and an ellipse) and grouped as `lighthouse`. It has a cream `#f7f1e5` tapered tower with two sea-foam bands, a navy door, a cream gallery, roof and finial, and an amber `#f2a541` lantern with navy mullions. It stands on a sea-foam "island" bar.
- **Beam:** two blurred amber cones (outer at opacity 0.28, inner at 0.45), grouped as `beam` with the pivot at the lamp.
- **Text:** the wordmark "Tidewick Café" is set in Fraunces 700 at 104 px, cream. The tagline "Coffee by the harbor" is set in Work Sans 400 at 40 px, sea-foam, with 2 px tracking.

## Timing as built

| Time | Brief | What the file does |
| --- | --- | --- |
| 0.0–1.5 s | Three waves draw in, left to right | `trim_end` goes from 0 to 100 on each wave path (ease-in-out-sine). Each draw takes 1.1 s, and they start 0.2 s apart (at 0, 0.2 and 0.4 s), so the last finishes at 1.5 s. |
| 1.0–3.0 s | Lighthouse rises into view | The `lighthouse` group's `translate-y` goes from 180 to 0 over 1.0–3.0 s (ease-in-out-cubic). Its opacity goes from 0 to 1 over 1.0–2.0 s, and the island bar fades in over 1.0–1.6 s. A navy rectangle the colour of the background sits above the lighthouse in the layer stack, below the island line. The tower therefore emerges from behind a "horizon" instead of sliding over the text area. |
| 2.0 s → end | Amber beam sweeps back and forth, keeps going | The beam's opacity goes from 0 to 1 over 2.0–2.4 s. Its `scale-x` follows a sine wave sampled every 33 ms from 2.0 s to 6.0 s (period 2.4 s, amplitude 1). The cone grows out of the lamp, swings across to the other side through zero width and back. This gives a rotating-lantern sweep from right to left and back that never stops. |
| 2.0–3.5 s | Wordmark slides up and fades in, above the waves | `translate-y` goes from 50 to 0 over 2.0–3.5 s (ease-in-out-cubic), and opacity from 0 to 1 over 2.0–3.2 s. |
| 3.0–4.5 s | Tagline types on, one letter at a time | `text-animate` with the `typewriter` preset, `unit: char`, starting at 3.0 s and lasting 1.5 s. The text stays a single editable text layer. |
| 4.5–6.0 s | Hold, beam still moving | Everything else is static. The beam keeps sweeping until the last frame, where it points left at scale-x ≈ −0.87. |

## Differences from the brief, and choices I made

- **Beam motion:** the sweep is a 3D-style rotation: the cone flips through zero width via `scale-x`. It is not a 2D rotation of the cone around the lamp. I chose this because it reads as a lighthouse lantern turning. If "back and forth" was meant as a pendulum swing in the picture plane, this is a different reading. Near each crossing the beam is briefly very narrow, about every 1.2 s.
- **Typewriter:** the letters appear one at a time with no movement, as typing does. That is the one deliberately "stepped" element. Everything that moves is eased.
- **The GIF loops** (loop count 0, as the brief asks). The animation is a play-once intro, so the loop restarts from the empty first frame. Vixl's motion check reports this as "loop seam" review warnings. I left them, because closing the loop would mean un-drawing the logo before the end, which the timing table doesn't call for.
- **First frame is empty navy:** at 0.0 s nothing has drawn in yet, so apps that show only the first frame will show a blank card. This follows the brief's timing. Vixl flags it as `motion.empty-poster` for review.
- **GIF frame timing:** GIF delays are stored in hundredths of a second. Vixl writes alternating 30/30/40 ms delays to average 30 fps, and merged the four identical blank opening frames into one 170 ms frame. That gives 176 frames instead of 180, with the same 6.0 s total.
- **Fonts:** the brief names none. I chose Fraunces (a warm old-style serif) for the wordmark and Work Sans for the tagline. The fonts from the document's first roll (Atkinson Hyperlegible Next and Source Serif 4) stay embedded but unused in `intro.vixl`, kept by undo history; `vixl_check` reports this as informational.
- **No audio.** None was requested.

## Checks

- **`vixl_check`** (bounds, overlap, contrast, legibility, fonts, motion) passed with no `fix` findings. The review items are the loop-seam and empty-poster warnings explained above. There is also one note that the tagline is hidden for 52% of a looped playback, which is expected for a type-on that starts at 3 s.
- **Previews:** I reviewed a contact sheet at 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5.2 and 5.97 s, plus a decoded MP4 frame at 0.5 s.
- **Wave fix:** the first preview showed the wave troughs cut flat by the path's box. I fixed it by giving each wave an explicit box (`path_view`) and re-exported everything.

## Unsure about

- Whether the flip-style beam counts as "sweeps back and forth" (see above).
- The beam cones are semi-transparent and blurred, so in the 540 px GIF (256 colours, no dither) the beam edges may show slight banding; I did not inspect the GIF frames themselves. The MP4 is smooth.
