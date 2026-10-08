# VIXL Originals

100 original VIXL illustrations: 24 faces and moods, 44 reactions and gestures, and
32 everyday symbols. They are by VIXL contributors, licensed
under CC BY-SA 4.0. The license text is bundled at
`src/vixl/data/emojis/LICENSE.txt` and in exported packs. These are original designs,
separate from the Unicode artwork adapted from OpenMoji.

Edit each transparent 72×72 SVG or extract its bundled `.vixl` master with
`vixl emoji get ':approved:' --out approved.vixl`. Keep metadata in `catalog.json`
in sync with the source filenames. Rebuild with `scripts/build_emojis.py` as described
in `docs/emojis.md`.

The source directory retains its original `reactions` name. `catalog.json` assigns
entries to `VIXL Faces`, `VIXL Reactions` and `VIXL Everyday`. Keep stable shortcodes
when refining artwork, so saved documents and exported manifests continue to match.

Use 1.7 px navy outlines, straight contours with short curved corners, and a few
muted accents. Preserve the identifying detail at 24 and 32 px. Avoid text labels,
grid snapping and decorative patterns.
