# T14 · Lyric video

A lyric video from a song and its timed lyrics:

- song: `evals/tool-comparison/fixtures/lighthouse.wav` (32 s);
- lyrics: `evals/tool-comparison/fixtures/lighthouse.lrc` (standard LRC: `[mm:ss.xx]` timestamps).

**How the LRC works here.**

- `[ti:…]` and `[ar:…]` are the song title and artist.
- A line whose whole text is a bracketed label, such as `[Chorus]` or `[Verse 2]`, marks the start of a
  section; it is not a lyric.
- A timestamp with no text clears the screen (an instrumental break).
- A line with two timestamps is sung at both times.

**The video.**

- 1280 × 720, with the song as its audio track.
- For the first 2 s: a title card with the song title and artist from the LRC tags.
- Each lyric line appears at its timestamp and stays until the next timestamp. The current line is
  large and centered; the next line is shown smaller beneath it.
- The current section's name is shown small in a top corner, once the first section begins.
- The background looks clearly different during choruses than during verses.
- Whenever the current line contains the word "Lighthouse", a warm beam or glow appears.

## Deliverables

| File | Spec |
| --- | --- |
| `lighthouse.mp4` | 1280 × 720, H.264 video, AAC audio, same length as the song (±0.1 s) |
| your editable source | if your tool has one |

## When you're done

Put every file in the run folder you were given. Then write `REPORT.md` there, listing each file
and how you made it, anything in this brief you didn't do or did differently and why, and anything
you're unsure about. Be exact: the report is checked against the files.
