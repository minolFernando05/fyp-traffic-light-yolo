#!/usr/bin/env bash
set -e

VIDEO="../../week1/videos/traffic_2.mp4"
OUT="../data/raw/negatives_from_video"

mkdir -p "$OUT"

# Extract 1 frame per second (good starting point)
ffmpeg -i "$VIDEO" -vf "fps=2" "$OUT/neg_%05d.jpg"

echo "Done. Extracted negatives into: $OUT"
ls "$OUT" | wc -l
