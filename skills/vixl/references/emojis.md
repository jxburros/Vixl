# Emoji workflows

The full authoring guide is `docs/guides/text/emojis.md` in the Vixl repository. Unicode 17 includes
3,953 SVGs and editable VIXL masters, including tones, flags and joined sequences. The artwork is a
content pack Vixl downloads and caches on first use; `emoji-artwork` shows it or fetches it now
(`download: true`), or installs a local copy (`pack`). Without it, emojis draw from the fonts with a warning.
VIXL Line 2 adds 100 originals (4,053 total entries): 24 faces, 44 reactions and 32 everyday
symbols. Search groups `VIXL Faces`, `VIXL Reactions` and `VIXL Everyday`;
built-in shortcodes such as `:approved:`, `:support:` and
`:in_progress:` render immediately in either preference mode.

Use `vixl_reference('workflows')` to discover the `emoji-*` actions. `emoji-list` pages the
catalog with query, group, offset and limit. `emoji-get` accepts emoji and optional
output/format (vixl, svg, png). `emoji-template` creates blank, face, symbol or sheet
masters at output. `emoji-replace` embeds source in the open document for emoji
(Unicode, hex or :custom_name:); `emoji-pack-install` merges a pack atomically.
`emoji-export` takes output (.zip), emojis (optional subset), destination, sources (default true),
size (images: any; imessage: 300, 408 or 618), animated, overwrite. Destinations: images, discord, slack
(128 px PNG), whatsapp (3–30 stickers, 512 px WebP, tray.png, contents.json), telegram (512 px PNG),
telegram-emoji (100 px PNG), telegram-animated (.tgs), twitch (28/56/112 px PNG), imessage (a sticker folder
with Xcode steps, no project). `destination` may be a list: one call writes OUTPUT-DESTINATION.zip per
destination (e.g. `["slack", "discord", "whatsapp"]`), drawing each emoji once, and writes nothing if any
destination's rule fails. `animated: true` exports emojis whose registered VIXL master has a timeline (square
canvas) as GIF (discord, slack, twitch, images), WebP (whatsapp; images with `animated: "webp"`) or APNG
(imessage) inside the destination's byte, frame and duration budgets, stepping colours or quality and then
the frame rate down; `telegram-animated` always writes vector TGS (at most 3 s, no effects or images).
WhatsApp and Telegram animated packs must be animated throughout; elsewhere stills are listed under `still`.
Custom shortcodes in a WhatsApp pack come back under `untagged`: add emoji tags in contents.json.
`emoji-requirements` takes the same destination (or list), emojis, animated and size and checks names,
dimensions, actual encoded bytes and pack rules.
`emoji-destinations` lists every limit with upload instructions, the source page (`url`) and the day checked.

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
for emoji text layers. Emoji artwork does not support text warp bending. emoji-mode font
draws emoji from the layer's font when it has the sequence, colour fonts (Noto Color Emoji:
COLR, SVG, CBDT, sbix) included; the default stays VIXL Line even when the font has a colour glyph. Art derived
from bundled Unicode masters retains OpenMoji CC BY-SA 4.0; bundled originals
use CC BY-SA 4.0 too. Original user art keeps its own
license. Every export includes attribution, manifest, upload help and offline preview.
