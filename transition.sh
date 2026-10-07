#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RACE="${race:-}"
TRACK="${track:-}"
PASS="${pass:-}"
SEGMENT="${start:-}"
DIVISIONS="${divisions:-10000}"

usage() {
    echo "Usage: transition [--pass N] [--segment N] [--race FILE] [--track FILE] [--divisions N]"
    echo "Defaults: race=\$race track=\$track pass=\$pass segment=\$start divisions=\${divisions:-10000}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --race) RACE="$2"; shift 2 ;;
        --track) TRACK="$2"; shift 2 ;;
        --pass) PASS="$2"; shift 2 ;;
        --segment) SEGMENT="$2"; shift 2 ;;
        --divisions) DIVISIONS="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -n "$RACE" ]] || { echo "Race is not set. Use setRace or --race." >&2; exit 1; }
[[ -n "$TRACK" ]] || { echo "Track is not set. Use setTrack or --track." >&2; exit 1; }
[[ -n "$PASS" ]] || { echo "Pass is not set. Use setPass or --pass." >&2; exit 1; }
[[ -n "$SEGMENT" ]] || { echo "Segment is not set. Use setStart or --segment." >&2; exit 1; }

[[ "$PASS" =~ ^[1-9][0-9]*$ ]] || { echo "Pass must be a positive integer: $PASS" >&2; exit 1; }
[[ "$SEGMENT" =~ ^[0-9]+$ ]] || { echo "Segment must be an integer: $SEGMENT" >&2; exit 1; }
[[ "$DIVISIONS" =~ ^[1-9][0-9]*$ ]] || { echo "Divisions must be a positive integer: $DIVISIONS" >&2; exit 1; }

(( SEGMENT >= 0 && SEGMENT < DIVISIONS )) || {
    echo "Segment must be between 0 and $((DIVISIONS-1))." >&2
    exit 1
}

[[ -f "$RACE" ]] || { echo "Race file not found: $RACE" >&2; exit 1; }
[[ -f "$TRACK" ]] || { echo "Track file not found: $TRACK" >&2; exit 1; }

END=$(( (SEGMENT + 1) % DIVISIONS ))

python3 "$SCRIPT_DIR/aimcsv.py" "$RACE" |
    python3 "$SCRIPT_DIR/track.py" --track-config "$TRACK" |
    python3 "$SCRIPT_DIR/interval.py" --start "$SEGMENT" --end "$END" --divisions "$DIVISIONS" |
    python3 -c '
import csv
import sys

wanted = int(sys.argv[1])
segment = int(sys.argv[2])

reader = csv.DictReader(sys.stdin)
matches = [
    r for r in reader
    if r.get("IntervalPass") == str(wanted)
    and r.get("IntervalStartBracket") in ("before", "after")
]

if not matches:
    print("No crossing found for pass {}, segment {}.".format(wanted, segment), file=sys.stderr)
    raise SystemExit(1)

before = next((r for r in matches if r["IntervalStartBracket"] == "before"), None)
after = next((r for r in matches if r["IntervalStartBracket"] == "after"), None)
chosen = after or before

print("Pass:          {}".format(wanted))
print("Segment:       {}".format(segment))
print("Record:        {}".format(chosen.get("Record", "")))
print("Time:          {}".format(chosen.get("Time", "")))
print("TrackPosition: {}".format(chosen.get("TrackPosition", "")))

if before and after:
    print()
    print("Crossing bracket:")
    print("  before: Record {}, Time {}, Position {}".format(
        before.get("Record", ""), before.get("Time", ""), before.get("TrackPosition", "")
    ))
    print("  after:  Record {}, Time {}, Position {}".format(
        after.get("Record", ""), after.get("Time", ""), after.get("TrackPosition", "")
    ))
' "$PASS" "$SEGMENT"
