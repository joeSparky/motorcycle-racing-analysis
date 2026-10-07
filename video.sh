#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VIDEO="${1:-test-video.mp4}"
RACE="${race:-}"
PASS="${pass:-}"
SEGMENT="${start:-}"

[[ -n "$RACE" ]] || { echo "Race is not set. Use: source setRace FILE" >&2; exit 1; }
[[ -n "$PASS" ]] || { echo "Pass is not set. Use: source setPass N" >&2; exit 1; }
[[ -n "$SEGMENT" ]] || { echo "Segment is not set. Use: source setStart N" >&2; exit 1; }
[[ -f "$RACE" ]] || { echo "Race file not found: $RACE" >&2; exit 1; }
[[ -f "$VIDEO" ]] || { echo "Video file not found: $VIDEO" >&2; exit 1; }

CAL_FILE="${RACE%.*}.calibration"

[[ -f "$CAL_FILE" ]] || {
    echo "Calibration file not found: $CAL_FILE" >&2
    echo "Run videoCalibration.sh for this race first." >&2
    exit 1
}

T="$("$SCRIPT_DIR/transition.sh" --pass "$PASS" --segment "$SEGMENT")"

RECORD="$(printf '%s\n' "$T" | awk '/^Record:/ {print $2; exit}')"
CSV_TIME="$(printf '%s\n' "$T" | awk '/^Time:/ {print $2; exit}')"

[[ -n "$RECORD" && -n "$CSV_TIME" ]] || {
    echo "Could not determine race position." >&2
    exit 1
}

VIDEO_TIME="$(python3 - "$CAL_FILE" "$CSV_TIME" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    c = json.load(f)
t = c["slope"] * float(sys.argv[2]) + c["offset"]
print("{:.6f}".format(max(0.0, t)))
PY
)"

echo
echo "Pass:       $PASS"
echo "Segment:    $SEGMENT"
echo "Record:     $RECORD"
echo "CSV Time:   $CSV_TIME"
echo "Video Time: $VIDEO_TIME"
echo "Calibration: $CAL_FILE"
echo

mpv \
    --pause \
    --no-audio \
    --no-fullscreen \
    --geometry=640x360 \
    --input-ipc-server=/tmp/mpvsocket \
    --start="$VIDEO_TIME" \
    "$VIDEO"
