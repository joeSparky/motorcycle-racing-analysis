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
POINTS="${points:-}"
OUTPUT="routes.png"

usage() {
    echo "Usage: $0 [--race RACE] [--track TRACK] [--start START] [--end END] [--divisions N] [--points FILE] [--output FILE]"
    echo "Defaults come from: race track start end divisions points"
    echo "Command-line options override those shell variables."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --race) RACE="$2"; shift 2 ;;
        --track) TRACK="$2"; shift 2 ;;
        --start) START="$2"; shift 2 ;;
        --end) END="$2"; shift 2 ;;
        --divisions) DIVISIONS="$2"; shift 2 ;;
        --points) POINTS="$2"; shift 2 ;;
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

[[ -f "$RACE" ]] || { echo "Race file not found: $RACE" >&2; exit 1; }
[[ -f "$TRACK" ]] || { echo "Track file not found: $TRACK" >&2; exit 1; }
if [[ -n "$POINTS" ]]; then
    [[ -f "$POINTS" ]] || { echo "Points file not found: $POINTS" >&2; exit 1; }
fi

PLOT_ARGS=(
    --x TrackX
    --y TrackY
    --type line
    --group IntervalPass
    --no-markers
    --gap-column Time
    --track-json "$TRACK"
    --interval "$START-$END"
    --output "$OUTPUT"
)

if [[ -n "$POINTS" ]]; then
    PLOT_ARGS+=(--points-json "$POINTS")
fi

python3 "$SCRIPT_DIR/aimcsv.py" "$RACE" |
    python3 "$SCRIPT_DIR/track.py" --track-config "$TRACK" |
    python3 "$SCRIPT_DIR/interval.py" --start "$START" --end "$END" --divisions "$DIVISIONS" |
    python3 "$SCRIPT_DIR/plot.py" "${PLOT_ARGS[@]}"


# Open the completed PNG automatically.
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
