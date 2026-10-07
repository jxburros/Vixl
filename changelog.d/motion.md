### Changed defaults

- **`wiggle` and `line-boil` last the rest of the timeline** when `duration` is not given, as `spin` and `attach` do. They stopped after 1000 ms, so a longer loop froze for its remainder. Pass `duration: 1000` for the old result (#290).
- **In a seamless loop, a `wiggle` or `line-boil` that runs to the loop end closes it**: wiggle rounds `frequency` to whole cycles and line boil holds each drawing for an equal share so a whole number of `variants` cycles fits; both say so in `warnings`. Pass a `duration` that ends before the loop end for the old timing (#290).
- **The standard character walks like a front-facing figure**: `character-cycle` `walk` and `run` lift each foot in turn, bend the knee a little, open the opposite arm and bob the body, and `react` keeps the feet planted. The legs used to swing ±30 degrees in the picture plane, which read as the splits. Pass `view: "side"` on `character-cycle` for the old result; bound artwork (`parts`) keeps the side-view swing (#304).
- **In a seamless loop, a staggered `animate`/`animate-preset` whose keys would run past the loop end wraps around it** instead of lengthening the timeline (2400 -> 2520 -> 2640 ms) and leaving tracks that cannot close; the result's `normalized` says so. A stagger that fits the loop is still a plain delay. Use a loop that is not seamless, or fewer repeats, for the old result (#294).

### Added

- `character-cycle` takes `view` (`front` or `side`), and the `character` check reports `front-view-leg-swing` when a front-facing character's upper legs swing more than 15 degrees in the picture plane (#304).
- Motion findings carry the animated `property` next to `layer` (#298).

### Fixes

- **WebP loop count**: timeline WebP exports played one time fewer than GIF and APNG (`loop: 2` wrote a WebP loop count of 2, which is two plays in total). All three now play `loop + 1` times, as the pixel `export-animation` already did (#372).
- A timeline whose frames are all identical exports as a one-frame animated WebP that lasts the whole range (`duration` 1000 for a 1000 ms timeline), as GIF does, instead of a still with duration 0. The same applies to pixel `export-animation` (#296).
- The `bounce` recipe writes a key on the ground at each contact, on the nearest frame of the timeline's `fps`, so the ball is seen landing (it hovered 1.8 px above the ground at 20 fps) (#297).
- Loop-seam and linear-motion findings name the layer and round values (`translate-y on 'ball' ends at -5.6 but starts at 0`) instead of printing layer ids and long floats; the two-key linear note is no longer raised for a `spin`, whose whole turns are constant speed by design (#298).
- Size warnings agree with the settings in use: no 1 MB note when `target_bytes` or a `preset` set the size, no `dither: 'ordered'` advice when the GIF already used it, one warning when `target_bytes` is missed, and the WebP comparison reads as a sentence ("or export MP4 (a WebP of these frames measured no smaller: 3,463,542 bytes)") (#301).
- `loop-seam-speed` is no longer raised for a track that turns around smoothly at the seam, such as a pendulum's baked `attach` track or a staggered float (#303).
