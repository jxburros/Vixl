#!/bin/bash
# usage (from the repo root): logos/jeffrey-x-guntly/explorations/2-remake/source/run.sh NN-slug buildNN.py
# Needs the `vixl` CLI on PATH (or VIXL=/path/to/vixl).
set -e
V=${VIXL:-vixl}
D=$(cd "$(dirname "$0")" && pwd)
P=logos/jeffrey-x-guntly/explorations/2-remake/$1.vixl
(cd "$D" && python3 "$2")
rm -f "$P"
$V new 1000x1000 -o "$P" --background white >/dev/null
$V --project "$P" apply "$D/ops.json" > "$D/apply.log" 2>&1 || (tail -20 "$D/apply.log"; exit 1)
$V --project "$P" render --out "${P%.vixl}.png" --overwrite --no-check > /dev/null
echo rendered
