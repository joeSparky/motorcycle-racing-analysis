#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Exported shell variables provide the defaults.
# Command-line options override them.
RACE="${race:-}"
TRACK="${track:-}"
START="${start:-}"
END="${end:-}"
DIVISIONS="${divisions:-10000}"
POINTS="${points:-}"

usage() {
    echo "Usage: $0 [--race RACE] [--track TRACK] [--start START] [--end END] [--divisions N] [--points FILE]"
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

OUTPUT="times.png"
TEMP_CSV="$(mktemp --suffix=.csv)"
trap 'rm -f "$TEMP_CSV"' EXIT

python3 "$SCRIPT_DIR/aimcsv.py" "$RACE" |
    python3 "$SCRIPT_DIR/track.py" --track-config "$TRACK" |
    python3 "$SCRIPT_DIR/interval.py" --start "$START" --end "$END" --divisions "$DIVISIONS" |
    python3 "$SCRIPT_DIR/timing.py" |
    mlr --csv sort -n BehindBest then cut -f Pass,IntervalTime,BehindBest,Complete > "$TEMP_CSV"

python3 - "$TEMP_CSV" "$OUTPUT" "$START" "$END" <<'PY'
import csv
import sys
import matplotlib.pyplot as plt

csv_file, output_file, start, end = sys.argv[1:]

with open(csv_file, newline="", encoding="utf-8") as f:
    rows = list(csv.reader(f))

if not rows:
    raise SystemExit("No timing data was produced.")

headers = rows[0]
data = rows[1:]

height = max(2.5, 0.38 * (len(data) + 2))
fig, ax = plt.subplots(figsize=(9, height))
ax.axis("off")

table = ax.table(
    cellText=data,
    colLabels=headers,
    loc="center",
    cellLoc="center"
)
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 1.35)

ax.set_title(f"Interval timing: {start} - {end}", pad=16)
fig.tight_layout()
fig.savefig(output_file, dpi=150, bbox_inches="tight")
plt.close(fig)
PY

echo "Created $OUTPUT"

if command -v feh >/dev/null 2>&1; then
    feh --scale-down "$OUTPUT" >/dev/null 2>&1 &
else
    echo "feh is not installed; PNG was created but not opened."
fi
