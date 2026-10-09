# Emoji workflows

The full authoring guide is `docs/emojis.md` in the Vixl repository. Unicode 17 includes
3,953 offline SVGs and editable VIXL masters, including tones, flags and joined sequences.
VIXL Line 2 adds 100 originals (4,053 total entries): 24 faces, 44 reactions and 32 everyday
symbols. Search groups `VIXL Faces`, `VIXL Reactions` and `VIXL Everyday`;
built-in shortcodes such as `:approved:`, `:support:` and
`:in_progress:` render immediately in either preference mode.

Use `vixl_workflow_schema` to discover the `emoji-*` actions. `emoji-list` pages the
catalog with query, group, offset and limit. `emoji-get` accepts emoji and optional
output/format (vixl, svg, png). `emoji-template` creates blank, face, symbol or sheet
masters at output. `emoji-replace` embeds source in the open document for emoji
(Unicode, hex or :custom_name:); `emoji-pack-install` merges a pack atomically.
`emoji-export` takes output (.zip), emojis (optional subset), destination
(images, discord, slack), sources (default true), size (image packs only), overwrite.
`emoji-requirements` checks destination names, dimensions and actual encoded bytes.
`emoji-destinations` includes upload instructions and linked policy sources.

Canonical operations: emoji-mode {mode: vixl|font} (default vixl: bundled art; CLI
`vixl -p F.vixl emoji settings --mode font`, workflow `emoji-settings`); emoji-set {emoji, format, data}
with base64 source and optional name/license; emoji-reset {emoji?}. Custom overrides
win in either mode; font mode still falls back to artwork when an entire sequence
cannot be shaped. Text-default symbols need VS16; VS15 keeps text presentation.

Keep identifying details within an 8 px margin on a 72 px canvas, use simple navy
#23364D strokes around 1.7 px, straight sides with softly curved corners, and preserve
small round details. Avoid grid snapping. Preview at 24/32 px against light and dark backgrounds.
Check bounds before preview/export. Sheet guides must be removed before individual
emoji delivery. Retain the VIXL source; PNG replacements remain raster artwork.

PNG and SVG share layout; SVG retains vector art. PDF/PPTX report a raster fallback
for emoji text layers. Emoji artwork does not support text warp bending. Art derived
from bundled Unicode masters retains OpenMoji CC BY-SA 4.0; bundled originals
use CC BY-SA 4.0 too. Original user art keeps its own
license. Every export includes attribution, manifest, upload help and offline preview.
