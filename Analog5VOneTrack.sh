#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Exported shell variables provide defaults.
# Command-line options override them.
RACE="${race:-}"
TRACK="${track:-}"
START="${start:-}"
END="${end:-}"
DIVISIONS="${divisions:-10000}"
PASS="${pass:-7}"
OUTPUT="suspension.png"

usage() {
    echo "Usage: $0 [--race RACE] [--track TRACK] [--start START] [--end END] [--divisions N] [--pass N] [--output FILE]"
    echo "Defaults come from: race track start end divisions pass"
    echo "Command-line options override those shell variables."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --race) RACE="$2"; shift 2 ;;
        --track) TRACK="$2"; shift 2 ;;
        --start) START="$2"; shift 2 ;;
        --end) END="$2"; shift 2 ;;
        --divisions) DIVISIONS="$2"; shift 2 ;;
        --pass) PASS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [[ -z "$RACE" ]]; then echo "Race is not set. Use setRace or --race." >&2; exit 1; fi
if [[ -z "$TRACK" ]]; then echo "Track is not set. Use setTrack or --track." >&2; exit 1; fi
if [[ -z "$START" ]]; then echo "Start is not set. Use setStart or --start." >&2; exit 1; fi
if [[ -z "$END" ]]; then echo "End is not set. Use setEnd or --end." >&2; exit 1; fi

[[ "$START" =~ ^[0-9]+$ ]] || { echo "Start must be an integer: $START" >&2; exit 1; }
[[ "$END" =~ ^[0-9]+$ ]] || { echo "End must be an integer: $END" >&2; exit 1; }
[[ "$DIVISIONS" =~ ^[1-9][0-9]*$ ]] || { echo "Divisions must be a positive integer: $DIVISIONS" >&2; exit 1; }
[[ "$PASS" =~ ^[0-9]+$ ]] || { echo "Pass must be an integer: $PASS" >&2; exit 1; }

[[ -f "$RACE" ]] || { echo "Race file not found: $RACE" >&2; exit 1; }
[[ -f "$TRACK" ]] || { echo "Track file not found: $TRACK" >&2; exit 1; }

python3 "$SCRIPT_DIR/aimcsv.py" "$RACE" |
    python3 "$SCRIPT_DIR/track.py" --track-config "$TRACK" |
    python3 "$SCRIPT_DIR/interval.py" --start "$START" --end "$END" --divisions "$DIVISIONS" |
    mlr --csv filter "\$IntervalPass == $PASS" |
    python3 "$SCRIPT_DIR/plot.py" \
        --x TrackPosition \
        --y Analog5V \
        --type line \
        --no-markers \
        --gap-column Time \
        --xlabel "Track position" \
        --ylabel "Analog5V" \
        --title "Analog5V - pass $PASS" \
        --output "$OUTPUT"


# Open the completed PNG in the background.
if [[ -f "$OUTPUT" ]]; then
    if command -v feh >/dev/null 2>&1; then
        feh --scale-down "$OUTPUT" >/dev/null 2>&1 &
    else
        echo "Created $OUTPUT, but feh is not installed."
    fi
else
    echo "Expected output file was not created: $OUTPUT" >&2
    exit 1
fi
