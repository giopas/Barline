#!/usr/bin/env bash
# Rebuilds the spoken count-in (web/static/voice/one..four.wav): 22050 Hz
# mono 16-bit, trimmed tight so "four" fits a beat even at 200 BPM.
# Synthesised with espeak-ng (sudo apt install espeak-ng ffmpeg); swap in
# your own recordings of the four words if you prefer, same format.
set -euo pipefail
OUT="$(cd "$(dirname "$0")/.." && pwd)/web/static/voice"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"
for w in one two three four; do
  espeak-ng -v en-us+m3 -s 230 -p 45 -a 180 -w "$TMP/$w.wav" "$w"
  ffmpeg -loglevel error -y -i "$TMP/$w.wav" \
    -af "silenceremove=start_periods=1:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_threshold=-40dB,areverse,afade=t=out:st=0.28:d=0.05,loudnorm=I=-14:TP=-1.5,atrim=0:0.34" \
    -ar 22050 -ac 1 -sample_fmt s16 "$OUT/$w.wav"
done
echo "voice written to $OUT"
