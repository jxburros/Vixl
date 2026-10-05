#!/usr/bin/env bash
# Editable source for T10 photo correction. Re-run to regenerate all outputs.
# Tools: ffmpeg (denoise), ImageMagick 6 `convert` (colour, rotation, crop, caption).
set -euo pipefail
cd "$(dirname "$0")"
SRC=../../../fixtures/coast-raw.jpg      # original, never written to
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# ---- adjustment settings -------------------------------------------------
DENOISE="nlmeans=s=3:p=7:r=15"   # ffmpeg non-local means, strength 3
# White balance + exposure as per-channel gains (sun core measured at
# R179 G199 B174 = green/cool cast and under-exposed; gains map it to ~R250 G242 B228)
GAIN_R=1.397; GAIN_G=1.216; GAIN_B=1.310
GAMMA=1.10                       # midtone lift to open the shadows
SAT=108                          # +8% saturation (modulate)
ANGLE=-2.2                       # degrees; horizon measured at +2.21 deg (falls to the right), counter-rotate
CROP=1558x1004                   # largest centred rectangle free of rotation corners (1562x1007) minus a 2px safety margin
FONT=DejaVu-Sans-Bold
# ---------------------------------------------------------------------------

# 1. denoise (on the original, before any gain amplifies noise)
ffmpeg -hide_banner -loglevel error -y -i "$SRC" -vf "$DENOISE" "$TMP/dn.png"

# 2. colour/exposure, 3. level the horizon, 4. crop away the rotation corners
convert "$TMP/dn.png" \
  -color-matrix "$GAIN_R 0 0  0 $GAIN_G 0  0 0 $GAIN_B" \
  -gamma $GAMMA -modulate 100,$SAT,100 \
  -virtual-pixel black -filter Lanczos -distort SRT $ANGLE \
  -gravity center -crop $CROP+0+0 +repage \
  -unsharp 0x0.8+0.4+0.02 \
  "$TMP/edited.png"
convert "$TMP/edited.png" -quality 95 -sampling-factor 1x1 coast-edited.jpg

# 5. Instagram 4:5 portrait (1080x1350). The edited photo is 1004 px tall, so the
#    crop window (803x1004, 4:5) is taken full-height and upscaled 1.345x.
#    Window x-offset 595 keeps sun, sun-path, horizon and the figure in frame.
convert "$TMP/edited.png" -crop 803x1004+595+0 +repage \
  -filter Lanczos -resize 1080x1350\! -unsharp 0x0.8+0.3+0.02 \
  -quality 92 coast-instagram.jpg

# 6. 1600x900 caption card: cover-scale the full edited photo to 1600 wide
#    (1600x1031), crop 900 rows (offset 66 keeps the sky/horizon balance),
#    subtle bottom-left dark gradient, caption bottom-left.
convert "$TMP/edited.png" -filter Lanczos -resize 1600x \
  -crop 1600x900+0+66 +repage "$TMP/card.png"
# gradient: transparent at top -> 55% black at bottom, over the lower 45%, fading out to the right
convert -size 1600x405 gradient:'rgba(0,0,0,0)-rgba(0,0,0,0.55)' "$TMP/vgrad.png"
convert -size 405x1600 gradient:'white-rgba(255,255,255,0.35)' -rotate 90 "$TMP/hfade.png"   # left strong, right weaker
convert "$TMP/vgrad.png" \( "$TMP/hfade.png" -alpha extract \) \
  \( -clone 0 -alpha extract \) -delete 0 -compose multiply -composite \
  "$TMP/mask.png"
convert -size 1600x405 xc:black "$TMP/mask.png" -alpha off -compose copy-opacity -composite "$TMP/grad.png"
convert "$TMP/card.png" "$TMP/grad.png" -gravity south -compose over -composite \
  -gravity southwest -font $FONT -pointsize 64 \
  -fill 'rgba(0,0,0,0.45)' -annotate +82+70 'Port Ellery at golden hour' \
  -fill '#FFF6E8' -annotate +80+72 'Port Ellery at golden hour' \
  -quality 95 -sampling-factor 1x1 coast-caption.png
