# Lyric videos

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

The `lyric-video` workflow turns three files into an MP4 or WebM with the lyrics in sync:

- a song (any format ffmpeg reads: MP3, WAV, FLAC, M4A, OGG);
- a user-timed [LRC](#lrc-rules) file;
- a styled `.vixl` [template](#template-contract) that follows a naming contract.

Vixl does no audio analysis. Every timestamp comes from the LRC file. The workflow compiles the
lyrics into an ordinary keyframed timeline document, then renders it with the film exporter and
the song as its audio track. The generated document stays editable: open it, change a keyframe or
a style, and export again without rebuilding (see [Editing a build](#editing-a-build)).

MP4/WebM export and reading the song's length need `ffmpeg` and `ffprobe` on `PATH`.

```bash
vixl workflow lyric-video-plan   --request request.json --workspace .   # validate; nothing written
vixl workflow lyric-video-build  --request request.json --workspace .   # write the timeline document
vixl workflow lyric-video-export --request request.json --workspace .   # build (or reuse the build), then render the video
```

Python: `vixl.lyrics.parse_lrc`, `plan`, `build` and `export`. MCP: `vixl_workflow` with the same
actions. REST: `POST /workflow/lyric-video-plan` (build and export stay CLI/MCP/jobs only). A full
song is a multi-minute render, so long exports usually go through a durable job:

```json
{"action": "submit", "job": {"kind": "lyric-video", "output": "song.mp4",
  "request": {"audio": "song.mp3", "lyrics": "song.lrc", "template": "style.vixl", "build": "song-lyrics.vixl"}},
 "start": true}
```

The job freezes copies of the song, lyrics and template when it is submitted, so later edits do
not change a queued render. It publishes the video to `output` and the built document to `build`. A job always
builds from those frozen inputs, so it does not carry hand edits. To render an edited build as a durable
job, submit a `film` job with the built document as its one shot and the song as its audio:

```json
{"action": "submit", "job": {"kind": "film", "output": "song.mp4", "spec": {"version": 1, "width": 1280, "height": 720,
  "fps": 24, "quality": "final", "shots": [{"source": "song-lyrics.vixl", "duration": 32000, "trim": 0}],
  "audio": [{"source": "song.mp3", "start": 0, "trim": 0, "volume": 1}]}}, "start": true}
```

## Worked example

`examples/lyric-video/` holds a template, original lyrics (`lighthouse.lrc`) and a script that
synthesizes a melody and renders the video:

```bash
python examples/lyric-video/build_lyric_video.py --draft
```

`request.json` for your own song:

```json
{
  "audio": "song.mp3",
  "lyrics": "song.lrc",
  "template": "lyric-style.vixl",
  "build": "song-lyrics.vixl",
  "output": "song.mp4",
  "fps": 24,
  "quality": "final",
  "lead": 150,
  "animation": {"in": "fade-in", "out": "fade-out", "duration": 300},
  "cue_animation": {"in": "fade-in", "out": "fade-out", "motion": "sweep", "amount": 14, "period": 3000},
  "next_line": true,
  "camera": {"from": [0.5, 0.5, 1], "to": [0.5, 0.5, 1.08]}
}
```

Typical agent loop: `lyric-video-plan` (read the warnings and the section list) → design or adjust
the template → `lyric-video-build` → `vixl_timeline_preview` at markers such as `chorus-1` or
`line-007` → `lyric-video-export` with `quality: "draft"` and a short `start`/`end` window →
the final export.

## LRC rules

```
[ti:Streetlights]
[ar:Example Artist]
[offset:+120]

[00:08.41]Streetlights hum like they know my name
[00:11.92]Every window's got a different flame
[00:15.30][Chorus]
[00:15.30]And I keep on driving
[00:31.00]
[00:44.10][01:52.40]This line repeats in both choruses
```

1. **Timestamps** are `[mm:ss.xx]` or `[mm:ss.xxx]` (a missing or one-digit fraction is also
   accepted). Minutes may exceed 59. Several timestamps before one text expand into one line each.
2. **Metadata** `ti`, `ar` and `al` become the template variables `${title}`, `${artist}` and
   `${album}` (empty when the file has none). Other tags are ignored with an `unknown_tag` warning.
3. **Offset** `[offset:N]` is in milliseconds and adds to the request's `offset`. As in the LRC
   convention, a positive offset shows lyrics **earlier**.
4. **Sections:** a timestamped line whose whole text is one bracketed label, such as `[Chorus]` or
   `[Verse 2]`, is a section marker, not a lyric. The label is slugged (`chorus`, `verse-2`).
5. **Empty text** (`[00:31.00]` alone) is an instrumental break: it hides the lyric and clears the
   next-line preview too, until the first line after the break shows.
6. **Word tags:** enhanced-LRC `<mm:ss.xx>` tags are removed from the displayed line and kept in
   the plan's `words` for a later karaoke phase.
7. Lines are sorted by time. Different lyrics at one timestamp are an `lrc_conflict` error.
8. **Repeated lines:** a line with several timestamps, or the same text on consecutive lines, that is
   sung again straight after itself stays on screen: it does not fade out and back in, and its entry
   animation (typewriter included) does not replay. A break, an earlier `max_hold` cut or a different line
   in between makes it a new line again. A `gap` does not blank a repeat.

The file must be UTF-8 (a byte-order mark and CRLF line endings are fine) and at most 1 MiB.

## Template contract

An ordinary Vixl document designed with the usual tools. Only `lyric` is required.

| Layer name | Role |
| --- | --- |
| `lyric` | Text layer showing the current line. Give it a fitted text box (`text-layout --width --height --fit`) so long lines wrap inside it. |
| `lyric-next` | Text layer showing the upcoming line, styled quieter. Hidden when `next_line` is false. It leaves with the lyric at an instrumental break and returns with the next line. |
| `section-label` | Text layer showing the current section's label. |
| `intro` | Layer or group visible before the first lyric (for example the title and artist). |
| `bg-<section>` | Layer or group visible only during that section, such as `bg-chorus`. A numbered section also matches its base name (`Verse 2` uses `bg-verse-2`, else `bg-verse`). `bg-default` shows when nothing matches. |
| `cue-<words>` | Layer or group visible while the current line contains those words: `cue-fire`, `cue-city-lights`. This lets the lyrics drive graphics. By default it cuts on and off; `cue_animation` can fade, slide or sweep it. |

The template may use `${title}`, `${artist}` and `${album}` wherever variables work. Its own
timeline is replaced. The video is the template's canvas size unless the request sets `width` and
`height`; a different aspect ratio is cropped from the centre with a `size_mismatch` warning.

Center text that changes length with constraints (`constrain intro --center-x canvas.center-x`),
not a one-time `x: "center"`, so it stays centred when the variables are filled in.

## Request fields

| Field | Default | Meaning |
| --- | --- | --- |
| `audio`, `lyrics`, `template` | required | Workspace-relative input paths. |
| `build` | required for build/export | The generated `.vixl`. For `lyric-video-build` it must be new unless `replace` is true. For `lyric-video-export` an existing build is rendered as it is, see [Editing a build](#editing-a-build). |
| `output` | required for export | `.mp4` or `.webm`. It must be new unless `replace` is true. |
| `fps` | 24 | 1–60. |
| `quality` | `final` | `draft` renders at most 640 px wide, for quick checks. |
| `offset` | 0 | Milliseconds added to the LRC `[offset:]`; positive shows lyrics earlier. |
| `lead` | 150 | Show each line this many ms before its timestamp, so it can be read as it is sung. |
| `gap` | 0 | Milliseconds of empty screen between consecutive lines. |
| `max_hold` | 8000 | The longest a line stays up, for long instrumental stretches. |
| `animation.in` | `fade-in` | `fade-in`, `slide-in-left/right/up/down`, `pop-in`, `zoom-in`, `typewriter` or `none` (a cut). Short names `fade`, `slide-up`, `pop`, `zoom`, `cut` also work. |
| `animation.out` | `fade-out` | `fade-out`, `slide-out-left/right/up/down`, `pop-out`, `zoom-out` or `none`. |
| `animation.duration` | 300 | Milliseconds for each entry and exit. |
| `animation.distance` | 6% of the canvas | How far slides travel, in pixels. |
| `cue_animation.in` | `none` | How a `cue-*` layer enters: `none` (a cut) or the lyric entries except `typewriter`. |
| `cue_animation.out` | `none` | How it leaves: `none` or the lyric exits. |
| `cue_animation.duration`, `.distance` | 300, 6% of the canvas | Milliseconds and slide distance for the cue's entry and exit. |
| `cue_animation.motion` | `none` | `sweep` swings the layer back and forth the whole time its words are sung. It turns about the layer's pivot, so give a beam a pivot at its lamp (`pivot` operation) or it turns about its centre. |
| `cue_animation.amount`, `.period` | 12, 2800 | A sweep swings ±`amount` degrees (0–180) about the layer's own rotation; `period` is milliseconds for one back and forth (200–60000). |
| `next_line` | true | Fill `lyric-next` with the upcoming line. |
| `camera` | none | A slow camera move over the whole video, as film-export camera poses `[x, y, zoom]`. |
| `start`, `end` | 0, song length | Render only part of the song. Audio is trimmed to match. |
| `width`, `height` | template canvas | Video size. |
| `sample_rate` | the song's, up to 48000 | Audio rate in Hz (8000–96000). WebM uses the nearest Opus rate at or above it. The result's `video` reports `sample_rate` and `channels`. |
| `check` | false | Run the design checks on one frame per unique line and return the findings. |
| `replace` | false | Allow `output` to replace an existing file, and `lyric-video-build` (or an export that has to build again) to replace `build`. |
| `rebuild` | false | Export only: build `build` again from the template and LRC even though it exists, discarding hand edits in it. |

## Timing

For line *i* with timestamp *tᵢ* (after the offset):

- **show** = *tᵢ* − `lead`, but not before the previous line hides (a `lead_clamped` warning) or 0.
- **hide** = the earliest of: the next line's show time − `gap` (an empty-text line hides at its
  own timestamp); *tᵢ* + `max_hold`; the end of the video.

Because the next line shows `lead` early, the current line hides at that moment too, so lines
never overlap. A line sung again straight after itself (rule 8) is one continuous display: the first
occurrence has no exit and the repeat has no entry, and the plan marks the repeat with `"repeat": true`.
A line followed by an empty timestamp has `"break_at"`, the time the screen clears. When a line is shorter than its entry plus exit animation, both are shortened in
proportion and a `short_line` warning names the line.

## What the build writes

- `timeline-set` with the song's length, and the requested fps.
- `lyric`: a stepped `text` key at each show time; opacity (and translate or scale) keys for the
  entry at show time and the exit ending at hide time. Between lines the values hold, so nothing
  drifts while the lyric is hidden.
- `lyric-next`: the following line's text at each show time. At an instrumental break the text is
  cleared at the empty timestamp, with an opacity fade out (the lyric's exit) and back in (the next
  entry) when the lyric animates.
- `section-label`: the label at each section start.
- `bg-*`: stepped `visible` keys so exactly one background shows at a time.
- `intro`: visible from 0 until the first line shows.
- `cue-*`: visible from each matching line's show time to its hide time; consecutive matching lines
  are one window. With `cue_animation`, opacity and slide/scale keys for the entry and exit, and
  `rotation` keys for a sweep (`ease-in-out-sine` between ±`amount`, the last key at the window's end).
- Markers: one per section occurrence (`chorus-1`, `chorus-2`) and per line (`line-001`, …).
- `state["lyric_build"]`: a record of the settings and sources the document was built from and a hash of
  what was written, so export can tell an edited build from an untouched one.

## Editing a build

The built document is an ordinary Vixl document: open it, add keyframes, restyle a layer, hide the preview
for a stretch, and keep going. `lyric-video-export` keeps those edits.

- If `build` does not exist, export builds it and renders it (as before).
- If it exists and its recorded settings and sources (`fps`, `offset`, `lead`, `gap`, `max_hold`,
  `animation`, `cue_animation`, `next_line`, a windowing `end`, the LRC file, the template file and the
  audio length) still match the request, export renders the document as it is, edits and all, and
  reports `build_reused: true`. Rendering-only fields (`quality`, `width`, `height`, `camera`, `start`,
  `check`) do not matter, and an `end` inside the built range is fine. The build file is never touched.
- If something that shapes the build changed and the document has hand edits, export stops with
  `build_stale` naming what changed, instead of ignoring the new settings or throwing the edits away.
  Pass `rebuild: true` to discard the edits and build again, restore the old settings, or choose a new
  `build` path.
- If it changed but the document is untouched, nothing is lost: export rebuilds when `replace` or
  `rebuild` is true, and otherwise reports that `build` already exists (as before). A document with no
  record (made by an earlier version) is treated the same way.

The export response's `warnings` carry a `build_reused` entry when a build with hand edits was rendered
as it is, so the edits are never applied unannounced.

## Errors and warnings

Errors use the standard structured format; parse errors also carry `source_line`.

| Code | When |
| --- | --- |
| `lrc_parse` | A timestamp is malformed, or a line has text but no timestamp. |
| `lrc_conflict` | Two different lyrics share one timestamp. |
| `lrc_empty` | No timed lyric lines. |
| `lyrics_beyond_audio` | A line or section starts after the end of the audio. Lines after a requested `end` are simply outside the render window. |
| `template_invalid` | No `lyric` text layer, a reserved name on the wrong layer type, or a `bg-`/`cue-` name that is not a slug. |
| `missing_file` | An input path does not exist in the workspace. |
| `codec_error` | ffmpeg/ffprobe is missing, or the audio has no readable stream. |
| `build_stale` | Export found a hand-edited build made with different settings or sources; see [Editing a build](#editing-a-build). |
| `resource_limit` | More than 1,000 lines, 500 characters in a line, 100 sections, a 1 MiB LRC file or 10 minutes of video. |

Warnings (`short_line`, `unknown_tag`, `unmatched_section`, `size_mismatch`, `lead_clamped`,
`build_reused`) never stop a render.

## Video length

MP4 and WebM stream frames one at a time into ffmpeg as raw pixels, so they are limited only by
the 10-minute duration (14,400 frames at 24 fps, 36,000 at 60 fps). GIF, APNG, WebP, sprite
sheets and PNG sequences buffer or write every frame and keep the 3,600-frame cap. Frames whose
animated state does not change (a line held on screen) reuse the previous render, so a lyric
video renders much faster than its frame count suggests.
