#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VIDEO="${1:-test-video.mp4}"
RACE="${race:-}"
PASS_A="${pass:-}"
SEGMENT_A="${start:-}"
PASS_B="${2:-}"
SEGMENT_B="${3:-}"

[[ -n "$RACE" ]] || { echo "Race is not set. Use: source setRace FILE" >&2; exit 1; }
[[ -n "$PASS_A" ]] || { echo "Point A pass is not set. Use: source setPass N" >&2; exit 1; }
[[ -n "$SEGMENT_A" ]] || { echo "Point A segment is not set. Use: source setStart N" >&2; exit 1; }
[[ -f "$RACE" ]] || { echo "Race file not found: $RACE" >&2; exit 1; }
[[ -f "$VIDEO" ]] || { echo "Video file not found: $VIDEO" >&2; exit 1; }
[[ -x "$SCRIPT_DIR/transition.sh" ]] || { echo "transition.sh not found or not executable." >&2; exit 1; }

[[ -n "$PASS_B" ]] || read -r -p "Point B pass: " PASS_B
[[ -n "$SEGMENT_B" ]] || read -r -p "Point B segment: " SEGMENT_B

[[ "$PASS_A" =~ ^[1-9][0-9]*$ ]] || { echo "Point A pass must be a positive integer." >&2; exit 1; }
[[ "$PASS_B" =~ ^[1-9][0-9]*$ ]] || { echo "Point B pass must be a positive integer." >&2; exit 1; }
[[ "$SEGMENT_A" =~ ^[0-9]+$ ]] || { echo "Point A segment must be an integer." >&2; exit 1; }
[[ "$SEGMENT_B" =~ ^[0-9]+$ ]] || { echo "Point B segment must be an integer." >&2; exit 1; }

get_transition() {
    "$SCRIPT_DIR/transition.sh" --pass "$1" --segment "$2"
}

TA="$(get_transition "$PASS_A" "$SEGMENT_A")"
TB="$(get_transition "$PASS_B" "$SEGMENT_B")"

REC_A="$(printf '%s\n' "$TA" | awk '/^Record:/ {print $2; exit}')"
CSV_A="$(printf '%s\n' "$TA" | awk '/^Time:/ {print $2; exit}')"
REC_B="$(printf '%s\n' "$TB" | awk '/^Record:/ {print $2; exit}')"
CSV_B="$(printf '%s\n' "$TB" | awk '/^Time:/ {print $2; exit}')"

[[ -n "$REC_A" && -n "$CSV_A" && -n "$REC_B" && -n "$CSV_B" ]] || {
    echo "Could not read calibration transitions." >&2
    exit 1
}

CAL_FILE="${RACE%.*}.calibration"
SOCKET="/tmp/racing-mpv-$$"
trap 'rm -f "$SOCKET"' EXIT

echo
echo "POINT A: Pass $PASS_A, Segment $SEGMENT_A, Record $REC_A, CSV Time $CSV_A"
echo "POINT B: Pass $PASS_B, Segment $SEGMENT_B, Record $REC_B, CSV Time $CSV_B"
echo
echo "mpv: Space play/pause | Up/Down +/-1 min | Left/Right +/-5 sec"
echo "     [ ] speed | Backspace normal speed | , . previous/next frame"
echo

mpv --pause --no-audio --input-ipc-server="$SOCKET" "$VIDEO" &
MPV_PID=$!

for _ in {1..50}; do
    [[ -S "$SOCKET" ]] && break
    sleep 0.1
done

[[ -S "$SOCKET" ]] || {
    echo "Could not connect to mpv." >&2
    kill "$MPV_PID" 2>/dev/null || true
    exit 1
}

get_video_time() {
python3 - "$SOCKET" <<'PY'
import json, socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sys.argv[1])
s.sendall(b'{"command":["get_property","time-pos"]}\n')
buf = b""
while b"\n" not in buf:
    chunk = s.recv(4096)
    if not chunk:
        raise SystemExit("mpv closed")
    buf += chunk
reply = json.loads(buf.split(b"\n",1)[0].decode())
print("{:.6f}".format(float(reply["data"])))
PY
}

echo "Find POINT A and pause."
read -r -p "Press Enter to SET POINT A..."
VIDEO_A="$(get_video_time)"

echo "Find POINT B and pause."
read -r -p "Press Enter to SET POINT B..."
VIDEO_B="$(get_video_time)"

python3 - "$CSV_A" "$VIDEO_A" "$CSV_B" "$VIDEO_B" "$CAL_FILE" "$VIDEO" "$RACE" \
 "$PASS_A" "$SEGMENT_A" "$REC_A" "$PASS_B" "$SEGMENT_B" "$REC_B" <<'PY'
import json, sys

ca, va, cb, vb = map(float, sys.argv[1:5])
fn, video, race = sys.argv[5:8]
pa, sa, ra, pb, sb, rb = sys.argv[8:14]

if cb == ca:
    raise SystemExit("CSV calibration times are identical.")

slope = (vb - va) / (cb - ca)
offset = va - slope * ca

data = {
    "race": race,
    "video": video,
    "slope": slope,
    "offset": offset,
    "pointA": {
        "pass": int(pa), "segment": int(sa), "record": int(ra),
        "csvTime": ca, "videoTime": va
    },
    "pointB": {
        "pass": int(pb), "segment": int(sb), "record": int(rb),
        "csvTime": cb, "videoTime": vb
    }
}

with open(fn, "w") as f:
    json.dump(data, f, indent=2)

print()
print("VIDEO CALIBRATION")
print("-----------------")
print("Slope:  {:.12f}".format(slope))
print("Offset: {:.6f}".format(offset))
print("Saved:  {}".format(fn))
PY

echo
echo "Close mpv when finished."
wait "$MPV_PID" || true
