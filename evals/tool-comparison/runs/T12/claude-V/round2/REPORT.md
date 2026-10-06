# T12 round 2 · Tidewick Café intro, 8-second version (lane V, Vixl)

Requested changes: make it 8 seconds, slow the beam to half speed, change the tagline to
"Open daily from 7 am", and extend the final hold to 3 seconds. Everything else stays as in round 1.

## How

I copied round 1's `intro.vixl` into `round2/` with `cp` and edited only that copy. Every edit used
the Vixl MCP tools: `vixl_operations_apply`, then `vixl_timeline_inspect`, `vixl_timeline_preview`
and `vixl_check` to check the result, and `vixl_export_timeline` / `vixl_export_file` for the exports.
I ran scripts only to check the exported files, using ffprobe, ffmpeg and PIL. Nothing outside
`round2/` was changed.

Operations applied to `round2/intro.vixl`:

1. `keyframe-remove` on the tagline's `text` track (the 21 old typewriter keys).
2. `text-set` on the tagline, changing it to "Open daily from 7 am". The text is now 483 px wide
   (it was 467 px).
3. `keyframe-remove` on the beam's `scale-x` track.
4. `timeline-set` with a duration of 8000 ms. fps stays 30 and loop stays 0 (forever).
5. `move` on the tagline to x=298 (it was 306), keeping y=226. This re-centres the finished line
   on x ≈ 540, as before. The x stays fixed while it types on, so the text grows rightward.
6. `animate-preset typewriter` on the tagline from 3000 ms for 2000 ms. That makes 21 keys, one
   character every 100 ms.
7. Beam `scale-x` keys: 1 at 2.0 s, −1 at 4.0 s, 1 at 6.0 s and −1 at 8.0 s, all with
   `ease-in-out-sine`. Each swing across now takes 2 s instead of 1 s, so the beam runs at exactly
   half speed. The beam's fade-in (opacity 0 to 1 over 2.0–2.4 s) is unchanged.

The waves, lighthouse rise, wordmark, colours, fonts, layer structure and the `allow_crop` intent
on the waves are all unchanged.

## New timing

| Time | What happens |
| --- | --- |
| 0.0–1.5 s | Waves draw on (unchanged) |
| 1.0–3.0 s | Lighthouse rises (unchanged). The beam fades in at 2.0–2.4 s and sweeps from 2.0 s to the end, one swing every 2 s |
| 2.0–3.5 s | Wordmark slides up and fades in (unchanged) |
| 3.0–5.0 s | Tagline "Open daily from 7 am" types on, 100 ms per character |
| 5.0–8.0 s | Hold for 3.0 s, with everything visible and the beam still sweeping |

## Files

| File | How it was made | Verified |
| --- | --- | --- |
| `intro.vixl` | Copy of round 1's source, edited as above | `vixl_check` passed with 0 errors and 0 warnings. The only notes were the 3 intentional wave crops (informational). The timeline is 8000 ms, 240 frames at 30 fps, loop 0 |
| `intro.mp4` | `vixl_export_timeline` as mp4, fps 30, scale 1 | ffprobe: h264, yuv420p, 1080×1080, 30/1, 240 frames, 8.000 s, 150,485 bytes |
| `intro.gif` | `vixl_export_timeline` as gif, scale 0.5, fps 15, 64 colours (same settings as round 1) | 540×540, loop=0, 118 frames whose durations add up to 8000 ms, 322,128 bytes (under 5 MB) |
| `intro-last-frame.png` | `vixl_export_file` with `time=7966.667` ms, which is frame 239, the MP4's last frame | 1080×1080 RGB. Its mean per-channel difference from the MP4's decoded last frame is about 1.2–2.1/255, which is H.264 loss |

## Choices and deviations

- **8 s total with a 3 s hold.** These two numbers conflict. In round 1 the last intro event, the
  tagline, ended at 4.5 s, and 4.5 + 3 = 7.5 s, not 8. I kept both of your explicit numbers
  (8.0 s total, 3.0 s hold). To fill the extra 0.5 s, I lengthened the tagline's type-on: it still
  starts at 3.0 s but now ends at 5.0 s instead of 4.5 s. The new tagline is 20 characters, so the
  pace is 100 ms per character; round 1 was about 71 ms per character. I had to rebuild the tagline's
  keys anyway, because the text changed. If you would rather keep the 3.0–4.5 s type-on, the hold
  becomes 3.5 s instead.
- **Beam end position.** At half speed, 2.0–8.0 s holds three half-swings instead of four, so the
  beam ends the video mirrored, pointing left (`scale-x` −1). In round 1 it ended pointing right.
  It is still moving in the hold. It slows into the 8.0 s key the same way round 1 slowed into
  its 6.0 s key.
- **Last frame.** As in round 1, I rendered the final frame at the time of the MP4's last frame
  (7.967 s), not at 8.000 s.

## Unsure about

- **GIF frame count.** PIL reads 118 GIF frames, while Vixl rendered 120. The encoder probably
  merges identical frames during the hold. The total duration is still exactly 8.0 s.
- **Tagline pace.** The slower type-on (100 ms per character) is a judgement call that comes from
  the timing conflict above.
- **Not mine.** `git status` shows unrelated pending changes elsewhere in the repo, including the
  round-1 `REPORT.md` and a previously tracked `round2/REPORT.md` that was shown as deleted. These
  were already there when I started; I only wrote files inside `round2/`.
