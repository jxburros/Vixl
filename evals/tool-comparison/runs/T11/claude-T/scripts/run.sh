#!/bin/sh
# Rebuild everything (run from this scripts/ dir's parent output folder working copy)
set -e
python3 s1.py      # perspective deskew + background normalisation + threshold -> bin.png
python3 s2.py      # fit lines / circle / canopy / ground -> geom.json
python3 gen.py     # write sketch-lines.svg and sketch-color.svg
inkscape sketch-lines.svg -o sketch-clean.png -w 2000 -b white
convert sketch-clean.png -alpha remove -alpha off -colorspace gray -type grayscale sketch-clean.png
inkscape sketch-color.svg -o sketch-color.png -w 2000
convert ../../../fixtures/sketch.jpg -resize 1000x \( sketch-color.png -resize 1000x \) -background white -gravity center +append compare.png
