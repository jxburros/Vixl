# T14 · Lyric video — claude-V (Vixl lane)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `lighthouse.mp4` | 1280×720, H.264 (yuv420p) video + AAC audio (192 kb/s), 24 fps, 32.000 s (ffprobe: video 32.000, audio 32.000, container 32.000) | Video frames rendered by Vixl `vixl_export_timeline` (mp4) from `lighthouse-lyrics.vixl`; the song was then muxed in with ffmpeg (`-c:v copy -c:a aac`) — no re-encode of the picture. |
| `lighthouse-lyrics.vixl` | Editable source: the built, keyframed timeline document (76+2 keyframes, markers `chorus-1`, `verse-2-1`, `chorus-2`, `line-001`…`line-008`) | `vixl_workflow lyric-video-build` from the template + LRC + WAV (lead 0 ms, fps 24, fade-in/fade-out 250 ms), then two hand edits (see below). |
| `lyric-style.vixl` | Editable template that follows Vixl's lyric-video naming contract | Built with Vixl MCP ops (gradients, shapes, groups, text, text-layout, constraints, layer styles); fonts DM Serif Display + DM Sans via `vixl_font_pair` (dm-serif-dm-sans). |

## Design

- **Title card (0–2.0 s):** `intro` group — "${title}" (DM Serif Display 128) over a gold rule and "${artist}" (DM Sans 38), filled from the LRC tags: "Lighthouse" / "The Vixl Examples". Album tag (Demo Tapes) not shown. Intro is visible 0→2000 ms, the first lyric fades in at 2000 ms.
- **Lyrics:** `lyric` is DM Serif Display 50 px, white, centred in a 1160×120 fitted box above centre, with a soft drop shadow; `lyric-next` is DM Sans 30 px, near-white, centred beneath. Each line shows at its LRC timestamp (lead set to 0, not Vixl's default 150 ms) with a 250 ms fade in and a 250 ms fade out ending at the next timestamp.
- **Section label:** `section-label` top-left (56, 44), DM Sans 26 px; empty until the first section marker at 9.0 s, then "Chorus" → "Verse 2" (18.0 s) → "Chorus" (25.0 s). It shows the LRC label text as written (title case, not upper case).
- **Backgrounds:** verses = cold night (navy-to-steel-blue sky, moon, dark sea, blue horizon line); choruses = warm sunset (violet → magenta → coral → amber sky, setting sun, plum sea, gold horizon). `bg-default` (used for the two opening lines, which come before any section marker) is a copy of the verse look, since those lines are musically verse 1. A lighthouse silhouette sits bottom-left in every section.
- **Lighthouse cue:** `cue-lighthouse` group = a warm radial lamp glow (screen blend), a lit lamp window, and a translucent amber beam (screen blend, 22 % opacity) sweeping from the lamp across the frame. Visible exactly while the current line contains "Lighthouse": 9.0–12.5 s and 25.0–32.0 s.
- **Instrumental break 16.0–18.0 s:** lyric hidden (empty LRC timestamp). Background stays chorus (the break falls inside the Chorus section, before the [Verse 2] marker).
- **Double-timestamped line:** "Lighthouse, lighthouse, sweep across the sea" plays at 25.0 and 28.5 s (expanded by the workflow into two lines). At 28.5 s it fades out and back in (a 250 ms dip) because the workflow treats it as a new line.

## Hand edits after the build (in `lighthouse-lyrics.vixl`)

1. Added `visible` keys on `lyric-next`: false at 16000 ms, true at 18000 ms — the workflow kept showing the upcoming line during the instrumental break; the brief says an empty timestamp clears the screen, so I hid it.
2. Lyric box height 150→120 (tighter spacing to the next line) and lyric-next colour/shadow strengthened for contrast over the beam (same changes also made in the template).

Because of these edits I did **not** use `lyric-video-export` (it rebuilds from the template and would have discarded them). Instead: `vixl_export_timeline` → silent H.264 MP4, then ffmpeg mux with the WAV. To reproduce: re-run the build, re-apply the two edits, export, mux.

## Checks

- `lyric-video-plan`: 8 lines, 3 sections, no warnings.
- `vixl_check` contrast on `lyric`, `lyric-next`, `section-label` over the worst-case template state (chorus + beam): passes. The full template check reports overlaps/contrast for intro vs lyric layers — false positives, since they are stacked in the template but never visible at the same time — and safe-area/bounds warnings for full-bleed background art (intended).
- Looked at timeline previews (contact sheet, 10 s, 13 s, 17 s) and at 8 frames extracted from the final MP4 (1 s, 3 s, 7 s, 10 s, 17 s, 20 s, 27.5 s, 30 s): all as intended.

## Unsure / differences

- Thumbnail-legibility warnings for section-label (26 px) and lyric-next (30 px): kept small on purpose, per the brief ("small" / "smaller").
- Lines 1–2 have no section, so no section label shows and they use the verse-style default background — my reading of "once the first section begins".
- Verse 2's label reads "Verse 2"; there is no "Verse 1" label since the LRC has none.
- The beam is static (shown/hidden with a cut on line boundaries), not animated sweeping.

## Timing

Start: Mon Oct  5 22:20:34 UTC 2026 · End: Mon Oct  5 22:29:04 UTC 2026 · about 54 tool calls (Vixl MCP + Bash/Read/ToolSearch).
