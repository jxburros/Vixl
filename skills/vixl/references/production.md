# Checked production for agents

Discover actions with `vixl_workflow_schema()` or `vixl workflow schema`.
Full reference: [production workflows](https://github.com/jxburros/Vixl/blob/main/docs/production.md).

1. Inspect the base document and create explicit `suite-set` rules for its requirements.
   Use `suite-capture` for protected layer structures/pixel regions. Do not overwrite
   baselines during an ordinary repair.
2. Use `fit-text`, `arrange-grid`, or `adapt-layout` for predictable layout tasks;
   save a bounded sequence with `action-define`. `role-set`, `motion-define`, and
   `motion-apply` produce editable staggered/relative animation tracks.
3. Workflow `act` accepts operations, suites and dry_run. It returns measurements and
   commits only if checks pass. `check` reports failed or needs_review; neither is a pass.
4. Workflow `capture` saves a `.vixl` recipe from explicit typed inputs and text/color
   bindings. Include defaults and difficult examples. Image slots use embedded asset IDs.
5. Workflow `plan` accepts a spec with rows, matrix, artboards, format and quality.
   Inspect its count before `run`, which also needs an output directory. Every output
   gets checks; up to three named repair_actions can run without changing the suites.
6. For long production, call `submit` with `start:true`, then `status` with its returned
   ID. The source is snapshotted. `cancel` is cooperative; `resume` preserves remote IDs.
   Never blindly repeat an uncertain provider request.
7. Reuse components with library-save/search/open/place. Open preserves the editable
   document; place inserts its rendered snapshot. Preview draft/final without regenerating
   image assets. Persistent caches are enabled by production and workflow previews.
8. Film plans accept shots from stills, `.vixl` timelines or video clips, camera poses,
   crossfades, captions and explicit audio tracks. MP4/WebM/audio need ffmpeg. Generated
   video requires an explicitly configured HTTP job gateway; other image providers do
   not automatically gain video support.

9. Lyric videos: `lyric-video-plan` validates a song, an LRC file (timestamps, `[Section]`
   markers) and a template document with a `lyric` text layer (optional `lyric-next`,
   `section-label`, `intro`, `bg-<section>` and `cue-<words>` layers) and reports the timed lines;
   `lyric-video-build` writes an editable keyframed document; `lyric-video-export` renders the
   MP4/WebM with the song as audio, rendering an existing hand-edited build as it is (`rebuild: true`
   rebuilds; `build_stale` if the settings changed under edits). An empty timestamp clears the lyric and the
   preview, a line sung twice in a row holds instead of re-fading, and `cue_animation` (`in`/`out`,
   `motion: "sweep"`) animates `cue-*` layers. Long songs run as the `lyric-video` job kind. See
   `docs/lyric-video.md`.
10. Form filling: `form-fill` fills the open form from `values` (one copy) or a `data` CSV (one
   file per row, or `combine` into one PDF); the `form-fill` job kind freezes the form and the data
   and deletes the data copy when done. See `docs/forms.md`.

MCP paths must remain inside the workspace. REST exposes check/act/plan/film-plan for
its single project; filesystem, library and queue operations use CLI/Python/MCP.
Checks certify only their declared rules and sampled times. Review the initial design,
material visual changes and unresolved/unsupported measurements.
