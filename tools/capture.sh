#!/usr/bin/env bash
# Pull one raw screenshot off the phone into .raw/, which git never sees.
#
# Raw captures carry whatever the real NAS was showing at the time - photographs,
# camera frames, file names. They are staged here and only reach docs/screenshots
# through blur_regions.py and frame_shot.py, so an unprocessed capture cannot be
# committed by accident.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$PATH:$HOME/Android/Sdk/platform-tools"
DEVICE="${SYNO_SHOT_DEVICE:-57100DLCQ003PT}"
[ $# -ge 1 ] || { echo "usage: capture.sh NAME [settle-seconds]" >&2; exit 1; }
sleep "${2:-2}"
adb -s "$DEVICE" exec-out screencap -p > "$REPO/.raw/$1.png"
printf '%s  %s\n' "$1" "$(identify -format '%wx%h' "$REPO/.raw/$1.png" 2>/dev/null || echo captured)"
