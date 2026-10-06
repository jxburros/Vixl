# T12 · Animated intro (Tidewick Café): lane V (Vixl)

All visual work was done with the Vixl MCP tools (`vixl_document_create`, `vixl_font_pair`,
`vixl_operations_apply`, `vixl_timeline_preview`, `vixl_render_preview`, `vixl_check`,
`vixl_export_timeline`, `vixl_export_file`). I only used scripts to compute wave point coordinates
(a sine function written as numbers) and to check the exported files with ffprobe/PIL.

## Files

| File | What it is | How it was made | Verified |
| --- | --- | --- | --- |
| `intro.vixl` | Editable source: layers, keyframe timeline (6 s, 30 fps, loop 0), embedded fonts | `vixl_document_create` 1080×1080, background `#14263b`, then `vixl_operations_apply` batches | opens and previews in Vixl; `vixl_check` passes (0 errors) |
| `intro.mp4` | Main video | `vixl_export_timeline` (mp4, fps 30, scale 1) | ffprobe: h264, yuv420p, 1080×1080, 30/1 fps, 180 frames, 6.000 s; 139,936 bytes |
| `intro.gif` | Half-size loop | `vixl_export_timeline` (gif, scale 0.5, fps 15, colors 64) | 540×540, loop=0 (forever), frame durations add up to 6000 ms; 269,936 bytes (under 5 MB). PIL reads 88 frames, though Vixl reported writing 90. The encoder probably merged two identical frames. |
| `intro-last-frame.png` | Final frame | `vixl_export_file` with `time=5966.667` ms (frame 179/179, the last frame of the MP4) | 1080×1080 RGB; mean per-channel difference from the MP4's decoded last frame is about 1.6/255, from H.264 compression |

## What's in the animation

- **Fonts:** pairing `fraunces-work-sans` (Fraunces 700 for the wordmark, Work Sans 400 for the tagline), installed and embedded with `vixl_font_pair`.
- **Waves (0.0–1.5 s):** three sine-wave pen strokes, 14 px wide with round caps, in the bottom third (y ≈ 790–980). Their colours are sea-foam at 100 %, 65 % and 38 %. Each is drawn on left to right by animating `trim_end` from 0 to 100 with ease-in-out, staggered: wave 1 runs 0–1.1 s, wave 2 runs 0.2–1.3 s and wave 3 runs 0.4–1.5 s.
- **Lighthouse (1.0–3.0 s):** built from pen and shape layers. The tower is cream with sea-foam stripes, a navy door, a sea-foam gallery, an amber lantern room with a glow look and navy mullions, and a cream roof and finial. All of it, including the beam, sits in the group `lighthouse`. The group animates `translate-y` from 520 to 0 with `ease-in-out-cubic`. A navy rectangle (`water-mask`, the same colour as the background) sits under the waves, so the lighthouse rises out from behind the water instead of sliding in from the frame edge.
- **Beam (from 2.0 s to the end):** a translucent amber wedge (`alpha(#f2a541,0.55)`, blurred by 6). Its pivot is at the lantern. It fades in over 2.0–2.4 s and sweeps by animating `scale-x` through 1 → −1 → 1 → −1 → 1, with keys at 2, 3, 4, 5 and 6 s and `ease-in-out-sine`. So it swings from right to left and back through the lantern, and is still moving during the hold.
- **Wordmark (2.0–3.5 s):** "Tidewick Café", 112 px, cream, centred near the top. It uses the `slide-in-up` preset: it rises 90 px and fades from 0 to 1 opacity, with ease-in-out-cubic.
- **Tagline (3.0–4.5 s):** "Coffee by the harbor", 46 px, sea-foam, under the wordmark. It uses the `typewriter` preset, which keys one character at a time (21 text keys). The tagline is placed at a fixed left x, so the text grows rightward and doesn't re-centre as letters appear.
- **Hold (4.5–6.0 s):** everything stays visible and the beam keeps sweeping.

## Choices and differences from the brief

- **Layout:** the brief says the wordmark is "above the waves". I put the wordmark and tagline at the top of the frame, above the lighthouse, and the lighthouse stands in the water in the centre. The text never overlaps the lighthouse or the waves.
- **Beam:** the sweep is a 2D swing, a horizontal mirror of a light wedge about the lantern. It is not a 3D rotating beam. It passes edge-on (invisible) at the midpoint of each swing, about every second.
- **Beam fade:** the beam fades in over 0.4 s at 2.0 s so it doesn't pop on. That fade is the only addition to the timing.
- **Typewriter timing:** I assume the typewriter preset is linear, with the same time per character; I didn't change its easing. Letters appear in steps, as typing should. The other movements use ease-in-out curves.
- **GIF:** I chose 15 fps and a 64-colour palette to keep the file small (270 KB). The brief sets no frame rate for the GIF.
- **Last frame:** the PNG is rendered at the time of the MP4's last frame (5.967 s) rather than 6.000 s, so it matches the video exactly. The beam is at nearly the same position at both times.
- **`vixl_check`:** it flagged the waves as cut off at the canvas edges. That is deliberate (they bleed off both sides), so I marked them `layer-intent allow_crop`. After that, no fix findings remain.

## Unsure about

- **GIF frame count:** PIL counts 88 GIF frames, while Vixl reported 90. The total duration is still exactly 6.0 s.
- **Lantern glow:** the glow look is subtle at this size.
- **Beam end:** the wedge has a fairly hard straight far end, which is softened only by the blur.
- **Beam colour:** the translucent amber over navy reads as a warm brownish-amber rather than bright amber.
