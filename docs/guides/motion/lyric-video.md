# Lyric videos

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

The `lyric-video` workflow turns three files into an MP4 or WebM with the lyrics in sync:

- a song (any format ffmpeg reads: MP3, WAV, FLAC, M4A, OGG);
- a user-timed [LRC](#lrc-rules) file or a reviewed [alignment record](#aligned-timing);
- a styled `.vixl` [template](#template-contract) that follows a naming contract.

Timestamps come from the LRC file or an explicitly configured alignment provider. The workflow compiles the
lyrics into an ordinary keyframed timeline document, then renders it with the film exporter and
the song as its audio track. The generated document stays editable: open it, change a keyframe or
a style, and export again without rebuilding (see [Editing a build](#editing-a-build)).

MP4/WebM export and reading the song's length need `ffmpeg` and `ffprobe` on `PATH`.

```bash
vixl workflow lyric-video-plan   --request request.json --workspace .   # validate; nothing written
vixl workflow lyric-video-build  --request request.json --workspace .   # write the timeline document
vixl workflow lyric-video-export --request request.json --workspace .   # build (or reuse the build), then render the video
```

Python: `vixl.plugins.lyrics.lyrics.parse_lrc`, `plan`, `build` and `export`. MCP: `vixl_apply(workflow=…)` with the same
actions. REST: `POST /workflow/lyric-video-plan` (build and export stay CLI/MCP/jobs only). A full
song is a multi-minute render, so long exports usually go through a durable job, the request of workflow `submit`
(`vixl workflow submit --request job.json --workspace .`, or `vixl_apply(workflow='submit', request=…)`; follow it with
`status` or `vixl_job`, see [durable jobs](../automation/production.md#durable-jobs)):

```json
{"job": {"kind": "lyric-video", "output": "song.mp4",
  "request": {"audio": "song.mp3", "lyrics": "song.lrc", "template": "style.vixl", "build": "song-lyrics.vixl"}},
 "start": true}
```

The job freezes copies of the song, lyrics and template when it is submitted, so later edits do
not change a queued render. It publishes the video to `output` and the built document to `build`. A job always
builds from those frozen inputs, so it does not carry hand edits. To render an edited build as a durable
job, submit a `film` job with the built document as its one shot and the song as its audio:

```json
{"job": {"kind": "film", "output": "song.mp4", "spec": {"version": 1, "width": 1280, "height": 720,
  "fps": 24, "quality": "final", "shots": [{"source": "song-lyrics.vixl", "duration": 32000, "trim": 0}],
  "audio": [{"source": "song.mp3", "start": 0, "trim": 0, "volume": 1}]}}, "start": true}
```

## Worked example

[`showcases/lyric-video/`](https://github.com/jxburros/VixlExamples/tree/main/showcases/lyric-video) in
VixlExamples holds original lyrics (`lighthouse.lrc`) and a script that builds a styled template, synthesizes a
melody and renders the video. From the root of a VixlExamples checkout:

```bash
python showcases/lyric-video/build_lyric_video.py --draft
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
  "lead_in": 4000,
  "tail": 6000,
  "animation": {"in": "fade-in", "out": "fade-out", "duration": 300},
  "cue_animation": {"in": "fade-in", "out": "fade-out", "duration": 300,
                    "cues": {"cue-lighthouse": {"motion": "sweep", "amount": 14, "period": 3000}}},
  "next_line": true,
  "camera": {"from": [0.5, 0.5, 1], "to": [0.5, 0.5, 1.08]}
}
```

Typical agent loop: `lyric-video-plan` (read the warnings and the section list) → design or adjust
the template → `lyric-video-build` → `vixl_render(action='timeline')` at markers such as `chorus-1` or
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
| `intro` | Layer or group visible before the first lyric (for example the title and artist). Give it room with `lead_in`; `lyric-video-plan` warns `intro_hidden` when the first line shows within 1 s of the start. |
| `outro` | Layer or group for an end card: hidden until the last line hides, then shown to the end with the lyric's entry animation (a fade for `typewriter`). Give it room with `tail`; the plan warns `outro_hidden` when less than 1 s is left after the last line. |
| `bg-<section>` | Layer or group visible only during that section, such as `bg-chorus`. A numbered section also matches its base name (`Verse 2` uses `bg-verse-2`, else `bg-verse`). `bg-default` shows when nothing matches. |
| `cue-<words>` | Layer or group visible while the current line contains those words: `cue-fire`, `cue-city-lights`. This lets the lyrics drive graphics. By default it cuts on and off; `cue_animation` can fade, slide or sweep it, each cue its own way. |
| `lyric-<section>` | Optional text layer that replaces `lyric` for lines in that section, with its own font, size, colour and position: `lyric-chorus`. Matched like `bg-<section>` (exact name, then the name without its number); other lines use `lyric`. |
| `next-<section>` | The same for `lyric-next`: `next-chorus` shows the upcoming line during the chorus. Needs `lyric-next`. |

A line belongs to the section its timestamp falls in. The variant switches when that line shows, after the previous line's exit, so a line is never restyled while it is on screen.

The template may use `${title}`, `${artist}` and `${album}` wherever variables work. Define them in
the template first (`vixl variable set title 'Song'`, or `{"type": "variable", "name": "title", "value": "Song"}`):
a text that names an undefined variable is refused with `missing_variable`. The build fills them from the LRC
tags. `lyric-video-plan` warns (`lyric_too_wide`) when a line is wider than the canvas in an unwrapped `lyric`
layer; give `lyric` a `text-layout` box so long lines wrap. The video is the template's canvas size unless the request sets `width` and
`height`; a different aspect ratio is cropped from the centre with a `size_mismatch` warning.

Only templates with at least one `bg-<section>` layer get an `unmatched_section` warning for a section
without a background. A template with no `bg-*` layers at all keeps one background throughout on
purpose, so the plan reports that once, as an info note under `notes` (`no_section_backgrounds`).

### Template motion

Motion designed in the template survives the build: flickering flames, a bobbing figure, a sweeping
spotlight. The template's timeline tracks are copied into the build as they are, with its markers. The
build wins only on a layer and property it writes itself (a role layer's `visible`, `opacity`, `text`,
the slide and scale of an animated lyric, and so on); each such template track is replaced, and a
`template_track_replaced` warning names it. To animate a role layer the build drives, animate a property
it does not write, or a group around it.

Template keys are times in the video. A cue layer's own motion usually belongs to its words instead:
with `cue_animation.replay` (globally or for one cue), the cue layer's own tracks restart at the start of
each of its windows and are cut off where the window ends, so a loop authored once from time 0 plays
every time its words are sung.

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
| `cue_animation.replay` | false | Restart the cue layer's own template tracks at each of its windows (see [Template motion](#template-motion)). |
| `cue_animation.cues` | none | Per-cue overrides keyed by cue layer name: `{"cue-cell": {"in": "slide-in-down", "duration": 450}, "cue-stage": {"motion": "sweep", "amount": 16}}`. Each takes the fields above (not `cues`) and inherits the rest from the shared settings. A name that is not a `cue-*` layer of the template is an error that lists the template's cue layers. Part of the build, like the rest of `cue_animation`. |
| `next_line` | true | Fill `lyric-next` with the upcoming line. |
| `camera` | none | A slow camera move over the whole video, as film-export camera poses `[x, y, zoom]`. A `start`/`end` window gets the poses the full video has at that window's first and last frames, so windows rendered separately join without a jump. |
| `start`, `end` | 0, video length | Render only part of the video. Audio is trimmed to match. Times are on the video's clock: with `lead_in`, the song starts at `lead_in`. |
| `lead_in` | 0 | Milliseconds of silence before the song (0–60000), for a title card. Every lyric, section and marker time moves this much later; the input files are not touched. |
| `tail` | 0 | Milliseconds of silence after the song (0–60000), for an end card. |
| `end_at_audio` | false | Hide the last line (and any line) no later than the end of the song, instead of holding it into the `tail` until `max_hold` or the end of the video. |
| `segments` | none | Export only: render the video in parts of this many milliseconds (1000–600000). See [Long renders](#long-renders). |
| `width`, `height` | template canvas | Video size. |
| `section_styles` | none | Restyle the lyric per section without extra layers: `{"chorus": {"size": 72, "color": "#ffd166", "y": 400}, "default": {...}}`. Each section takes `size`, `color`, `x` and `y`; a section is matched like `bg-<section>`, then `default`, else the template's own values come back. The keys are written on `lyric` and every `lyric-<section>` layer when a line from a differently styled section shows. Fonts cannot change by keyframe: use a `lyric-<section>` layer. Part of the build: changing it rebuilds an unedited build and makes an edited one `build_stale`. |
| `sample_rate` | the song's, up to 48000 | Audio rate in Hz (8000–96000). WebM uses the nearest Opus rate at or above it. The result's `video` reports `sample_rate` and `channels`. |
| `check` | false | Run the design checks on one settled frame per cue occurrence, including repeated choruses. |
| `verify` | `basic` | `basic` checks encoded streams and every cue's timing/text; `full` also decodes the entire file and samples visual and brand checks. |
| `replace` | false | Allow `output` to replace an existing file, and `lyric-video-build` (or an export that has to build again) to replace `build`. |
| `rebuild` | false | Export only: build `build` again from the template and LRC even though it exists, discarding hand edits in it. |

## Timing

For line *i* with timestamp *tᵢ* (after the offset, plus `lead_in`):

- **show** = *tᵢ* − `lead`, but not before the previous line hides (a `lead_clamped` warning) or 0.
- **hide** = the earliest of: the next line's show time − `gap` (an empty-text line hides at its
  own timestamp); *tᵢ* + `max_hold`; the end of the song with `end_at_audio`; the end of the video.

Because the next line shows `lead` early, the current line hides at that moment too, so lines
never overlap. A line sung again straight after itself (rule 8) is one continuous display: the first
occurrence has no exit and the repeat has no entry, and the plan marks the repeat with `"repeat": true`.
A line followed by an empty timestamp has `"break_at"`, the time the screen clears. When a line is shorter than its entry plus exit animation, both are shortened in
proportion and a `short_line` warning names the line.

Each planned line also carries `settled`, when its entry animation has finished, and `exit`, when its
exit animation begins (its `hide` time for a line that holds into a repeat). The plan returns the
windows the build uses, so scripts and agents can time extra motion without re-deriving the rules:

```json
{"cues": {"cue-fire": [[8100, 12000]]},
 "section_windows": {"chorus": [[5300, 7800], [15300, 24000]]},
 "lines": [{"index": 0, "text": "…", "show": 850, "settled": 1150, "exit": 3049, "hide": 3350}]}
```

`cues` lists `[show, hide]` per `cue-*` layer, with consecutive matching lines merged into one window;
`section_windows` lists `[start, end]` per section name, one pair per occurrence.

## What the build writes

- `timeline-set` with the video's length (`lead_in` + the song + `tail`), and the requested fps.
- The template's own tracks and markers, except tracks on a layer and property listed below
  (see [Template motion](#template-motion)).
- `lyric`: a stepped `text` key at each show time; opacity (and translate or scale) keys for the
  entry at show time and the exit ending at hide time. Between lines the values hold, so nothing
  drifts while the lyric is hidden.
- `lyric-next`: the following line's text at each show time. At an instrumental break the text is
  cleared at the empty timestamp, with an opacity fade out (the lyric's exit) and back in (the next
  entry) when the lyric animates.
- `lyric-<section>` / `next-<section>`: the same keys as `lyric` / `lyric-next`, plus stepped `visible` keys so only the one
  chosen for the current line shows.
- `section_styles`: `hold` keys for `size`, `color`, `x`, `y` on the lyric layers at the show time of the first line of each
  differently styled section.
- `section-label`: the label at each section start.
- `bg-*`: stepped `visible` keys so exactly one background shows at a time.
- `intro`: visible from 0 until the first line shows.
- `outro`: hidden until the last line's hide time, then visible to the end, with opacity (and slide or
  scale) keys for the lyric's entry animation.
- `cue-*`: visible from each matching line's show time to its hide time; consecutive matching lines
  are one window. With `cue_animation` (or the cue's own entry in `cue_animation.cues`), opacity and
  slide/scale keys for the entry and exit, and `rotation` keys for a sweep (`ease-in-out-sine` between
  ±`amount`, the last key at the window's end). With `replay`, the cue layer's own template tracks again
  from each window's start.
- Markers: one per section occurrence (`chorus-1`, `chorus-2`) and per line (`line-001`, …).
- `state["lyric_build"]`: a record of the settings and sources the document was built from and a hash of
  what was written, so export can tell an edited build from an untouched one.

## Editing a build

The built document is an ordinary Vixl document: open it, add keyframes, restyle a layer, hide the preview
for a stretch, and keep going. `lyric-video-export` keeps those edits.

- If `build` does not exist, export builds it and renders it (as before).
- If it exists and its recorded settings and sources (`fps`, `offset`, `lead`, `gap`, `max_hold`,
  `animation`, `cue_animation` with its per-cue `cues`, `next_line`, `section_styles`, `lead_in`, `tail`,
  `end_at_audio`, a windowing `end`, the LRC file, the template file and the
  audio content and length) still match the request, export renders the document as it is, edits and all, and
  reports `build_reused: true`. Rendering-only fields (`quality`, `width`, `height`, `camera`, `start`,
  `segments`, `check`) do not matter, and an `end` inside the built range is fine. The build file is never touched.
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
| `template_invalid` | No `lyric` text layer, a reserved name on the wrong layer type (`lyric-<section>` and `next-<section>` must be text), or a `bg-`/`cue-`/`lyric-`/`next-` name that is not a slug. |
| `invalid_operation` | A request field is out of range, or `cue_animation.cues` names a layer the template does not have (`allowed` lists its cue layers). |
| `missing_file` | An input path does not exist in the workspace. |
| `codec_error` | ffmpeg/ffprobe is missing, or the audio has no readable stream. |
| `build_stale` | Export found a hand-edited build made with different settings or sources; see [Editing a build](#editing-a-build). |
| `resource_limit` | More than 1,000 lines, 500 characters in a line, 100 sections, a 1 MiB LRC file or 10 minutes of video. |

Warnings (`short_line`, `unknown_tag`, `unmatched_section`, `size_mismatch`, `lead_clamped`,
`lyric_too_wide`, `intro_hidden`, `outro_hidden`, `template_track_replaced`, `build_reused`,
`verification_failed`) never stop a render. Info notes (`no_section_backgrounds`) are listed under
`notes`, apart from the warnings.

## Video length

MP4 and WebM stream frames one at a time into ffmpeg as raw pixels, so they are limited only by
the 10-minute duration (14,400 frames at 24 fps, 36,000 at 60 fps), `lead_in` and `tail` included.
GIF, APNG, WebP, sprite sheets and PNG sequences buffer or write every frame and keep the 3,600-frame
cap. Frames whose animated state does not change (a line held on screen) reuse the previous render, so
a lyric video renders much faster than its frame count suggests.

### Long renders

A full song with motion in every frame can still take many minutes, and an interrupted single render
loses everything (an MP4 is unreadable until ffmpeg finishes it). `segments` renders the video in parts
instead:

```json
{"audio": "song.mp3", "lyrics": "song.lrc", "template": "style.vixl", "build": "song-lyrics.vixl",
 "output": "song.mp4", "segments": 10000}
```

Each part (10 s here) is encoded on its own into `.song.mp4.parts/` beside the output and kept there
once it is complete. When every part is done they are joined without re-encoding and the song is mixed
in once, then the folder is removed. Running the same request again after a crash, a restart or a
cancel skips the parts already on disk; parts made for a different request, build or Vixl version are
discarded. The result's `video.segments` reports `parts`, `reused`, `rendered` and `frames_per_part`.
The camera move is the same as in a single render, so the parts join without a jump. A durable
`lyric-video` job with `segments` resumes the same way when it is run again.

### Verification and review

After the file is written, export reads it back with ffprobe and returns `verification`: whether the
encoded video has the rendered width and height (odd sizes are padded to even ones), fps, frame count
and duration, whether the audio stream is present with the mixed sample rate and channel count, and
the frame quantisation: a video is a whole number of frames, so its length can differ from the
requested length by less than one frame (`delta_ms`; 5,170 frames at 24 fps run 16.7 ms past a 215.4 s
song). That is reported, not treated as a failure. `status` is `passed`, `failed` (with a
`verification_failed` warning naming the checks) or `skipped` when ffprobe is not on `PATH`.

Every export also checks each cue occurrence's show/hide range and compares its source text with
the visible lyric layer after its entrance. Repeated choruses are checked separately. Set
`verify: "full"` to decode the complete encoded file and check bounds, overlap, contrast, safe area,
blank content and brand rules at entrance start, midpoint, settled and exit frames. There are at
most four samples per cue and 400 samples total. These are source-document design checks; they do
not measure compression quality or inspect every encoded frame.

The report separates `execution`, `structural`, `brand`, `visual_sampled`, `unreviewed` and `review`.
`coverage.sampled_ms` lists sampled times; `checked_ms` totals their one-frame windows, and
`unsampled_intervals` explicitly lists the remaining ranges. `sources` records SHA-256 identities
for the audio, lyrics (or timing file) and built document, plus audio codecs, rates and trims.
Sources changed during an export fail verification.

Export leaves `review.status: "pending"`. After reviewing the build, its motion and synchronization,
record the decision with `vixl lyrics review song-lyrics.vixl --approve --workspace .`, or
`--changes-requested --findings '["Adjust the second chorus"]'`. The equivalent workflow is
`lyric-video-review` with `build`, `approve` or `changes_requested`, and optional `findings`.
The decision is saved in the build and becomes pending again if its content or source audio/lyrics
change, including a replacement song of the same length. Review requires the recorded sources to
still match the build; rebuild older documents that do not yet record audio identities. Approval
alone does not validate an encoded delivery: `validated` is true only after full verification
passes and no required checks or reviews remain. Basic verification never claims full validation.

## Aligned timing

`vixl lyrics align song.wav lyrics.txt -o song.timing.json --provider aligner` calls one explicitly
configured [alignment adapter](../../reference/providers.md#lyric-alignment). Input lyrics can be plain text
(one occurrence per line) or LRC. There is no bundled speech model. The timing JSON is independent of any
`.vixl` document and records audio/lyric hashes, provider identity, each line and word's start/end in
milliseconds, confidence, and whether its timing is `aligned`, `lrc` or `edited`.

Repeated chorus lines keep distinct indices. Supplied LRC line starts are preserved; pass `--replace-lines`
only when they should be replaced. Low confidence and detected silence need review. Unmatched lines,
non-monotonic times, words outside their line, and ranges beyond the audio set `valid: false`; the record
is still saved for repair, but cannot be built or exported as LRC until those findings are fixed. A valid
record is structurally usable and still has `review.status: pending`; it is not a claim of musical accuracy.

Edit without another provider call:

```bash
vixl lyrics timing-edit song.timing.json -o corrected.timing.json \
  --edits '[{"line":0,"shift":100},{"line":1,"word":2,"start":2500,"end":2900}]'
vixl lyrics timing-export corrected.timing.json -o corrected.lrc
```

`line` and `word` are zero-based indices. A line `shift` moves its words too; `start`/`end` set only the
selected line or word. `--replace` explicitly permits overwriting an output. Enhanced LRC preserves word
starts; the JSON keeps word ends, confidence and provenance that LRC cannot express.

A build request can use `"timing": "corrected.timing.json"` instead of `lyrics`. The audio must match its
recorded hash and duration. `"animation": {"in": "typewriter", "out": "fade-out", "unit": "word"}` reveals
whole words at their timestamps and writes ordinary editable text keys. Every line needs complete word
timings for this mode. Offsets and `lead_in` move word times together with their lines. Queued lyric jobs
freeze the timing JSON along with the song and template.

The equivalent workflow actions are `lyrics-align`, `lyrics-timing-edit` and `lyrics-timing-export`;
use `audio`, `lyrics`, `output`, `provider`, `replace_lines`, `confidence` (default 0.7), and `replace`
for alignment, or `timing`, `output`, `edits` and `replace` for edits.

## Compositions

`compositions` selects a dedicated editable group for each matching cue. Rules are evaluated in order;
the first matching rule wins. `match` accepts `section` (the section slug), `occurrence` (one-based
occurrence of that section), `cue` (zero-based lyric index), and `contains` (case-insensitive text).
A `variant` is a template group name, a layout object, or a list of either. `assign: "cycle"` walks the
list in order; `assign: "seeded"` with an integer `seed` makes a repeatable random choice.

For example, this alternates the two repeated choruses' opening lines:

```json
{"compositions":[{"match":{"contains":"city lights"},"assign":"cycle","variant":[
  {"layout":{"kind":"stack","fit":{"min_size":16,"max_size":64},"entrance":"fade-up","unit":"line"}},
  {"layout":{"kind":"setup-payoff","fit":{"min_size":16,"max_size":64},"entrance":"pop","unit":"word"}}
]}]}
```

`single` uses one text layer. `stack` uses one per phrase. `setup-payoff` gives the first phrase a smaller
maximum size. `|` marks a phrase break in the source lyric and is omitted from the displayed text. Without
it, the largest gap in word timings selects the break; without word timings, the split is near the middle.
The existing `fit-text` operation sizes each phrase inside the requested `x`, `y`, `width`, `height` and
`gap` (default region: the middle 80% × 60% of the canvas). The minimum must fit, or the build fails
without replacing the previous build. Entrances use `text-animate` presets, with zero stagger so all
words/lines settle inside the cue. This is distinct from the aligned, sequential word reveal described above.

A named template group is duplicated per cue; its first text layer is the lyric placeholder, and other
children retain their artwork and labels. The source group is hidden in the build. Put `layout.fit` beside
the named `variant` to fit its placeholder. Template group descendants keep stable names prefixed by
`composition-NNNN/`, allowing `motion: {parts: {"flame*": {preset: "flicker", amplitude: 2}}, span: "cue"}`.
`flicker` uses the existing seeded wiggle recipe; `hover` and `wiggle` also work. Motion is vertical and
bounded to 0–10 pixels. `span: "entrance"` limits motion to the entry instead of the whole cue.

`attach: {symbol: "saved-badge", to: "baseline", gap: 8, width: 24}` places a saved object beside the
last phrase. `baseline`, `cap-height` and `ink-right` anchors use rendered text metrics; the object becomes
a child of that cue's group. Attachment and motion fields may sit on the rule or a layout variant.

After editing a cue's generated layers, approve the build with `vixl lyrics review BUILD --approve`.
A rebuild preserves those approved field edits and removals by the generated layer names, while recording
new IDs in `lyric_build.overrides`. The rebuilt content still needs a fresh review. Previously approved
overrides survive later rebuilds; new unapproved edits are discarded by `rebuild`. Overrides carry forward only while the cue index, text, section and occurrence still match, so timing-only
edits keep approved styles and changed lyrics do not inherit another cue’s edits.

Preview just one built cue with `vixl lyrics preview BUILD --cue 2 -o cue.png`; PNG shows its settled
frame, while GIF, ZIP or video outputs use that cue's interval through the film preview writer.
The equivalent workflow is `lyrics-preview` with `build`, `cue` and `output`. Builds support at most
200 composed cues, leaving the existing timeline/resource limits in force.
