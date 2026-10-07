#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RACE=""
TRACK=""
START=""
END=""
DIVISIONS=10000
POINTS=""
OUTPUT="routes.png"

usage() {
    echo "Usage: $0 --race RACE --track TRACK --start START --end END [--divisions N] [--points FILE] [--output FILE]"
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

if [[ -z "$RACE" || -z "$TRACK" || -z "$START" || -z "$END" ]]; then
    usage >&2
    exit 1
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
