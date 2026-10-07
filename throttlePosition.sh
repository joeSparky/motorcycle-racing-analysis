#!/usr/bin/env bash
# throttlePositionOneTrack.sh
#
# Plot throttle position through a selected track interval.
#
# Standard environment variables:
#   $race  = current race CSV
#   $track = current track configuration
#
# Command-line values override the environment variables.

set -euo pipefail

usage() {
    cat <<'EOF'
Plot throttle position through a track interval.

Usage:
  ./throttlePositionOneTrack.sh <start> <end> [options]

Environment:
  race              Current race CSV.
  track             Current track configuration.

Options:
  --race FILE       Override $race.
  --track FILE      Override $track.
  --divisions N     Track-position divisions. Default: 10000.
  --pass N          Interval pass to plot. Default: 7.
  --output FILE     Output PNG. Default: throttle.png.
  -h, --help        Show this help.

Examples:
  ./throttlePositionOneTrack.sh 2437 4215
  ./throttlePositionOneTrack.sh 2437 4215 --pass 5
  ./throttlePositionOneTrack.sh 2437 4215 --pass 5 --output throttle-pass5.png
EOF
}

if [[ $# -eq 0 || "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -lt 2 ]]; then
    echo "Error: supply start and end track positions. Use -h for help." >&2
    exit 2
fi

start="$1"
end="$2"
shift 2

race_file="${race:-}"
track_file="${track:-}"
divisions=10000
pass=7
output="throttle.png"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --race)
            [[ $# -ge 2 ]] || { echo "Error: --race requires a file." >&2; exit 2; }
            race_file="$2"
            shift 2
            ;;
        --track)
            [[ $# -ge 2 ]] || { echo "Error: --track requires a file." >&2; exit 2; }
            track_file="$2"
            shift 2
            ;;
        --divisions)
            [[ $# -ge 2 ]] || { echo "Error: --divisions requires a number." >&2; exit 2; }
            divisions="$2"
            shift 2
            ;;
        --pass)
            [[ $# -ge 2 ]] || { echo "Error: --pass requires a number." >&2; exit 2; }
            pass="$2"
            shift 2
            ;;
        --output|-o)
            [[ $# -ge 2 ]] || { echo "Error: --output requires a filename." >&2; exit 2; }
            output="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ "$start" =~ ^[0-9]+$ ]] || { echo "Error: start must be an integer." >&2; exit 2; }
[[ "$end" =~ ^[0-9]+$ ]] || { echo "Error: end must be an integer." >&2; exit 2; }
[[ "$divisions" =~ ^[1-9][0-9]*$ ]] || { echo "Error: divisions must be a positive integer." >&2; exit 2; }
[[ "$pass" =~ ^[0-9]+$ ]] || { echo "Error: pass must be a non-negative integer." >&2; exit 2; }

[[ -n "$race_file" ]] || {
    echo 'Error: no race specified and $race is not set.' >&2
    echo 'Use setRace or --race FILE.' >&2
    exit 1
}

[[ -n "$track_file" ]] || {
    echo 'Error: no track specified and $track is not set.' >&2
    echo 'Use setTrack or --track FILE.' >&2
    exit 1
}

[[ -f "$race_file" ]] || { echo "Error: race file not found: $race_file" >&2; exit 1; }
[[ -f "$track_file" ]] || { echo "Error: track file not found: $track_file" >&2; exit 1; }

race_file="$(realpath "$race_file")"
track_file="$(realpath "$track_file")"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

for tool in aimcsv.py track.py interval.py plot.py; do
    [[ -f "$script_dir/$tool" ]] || {
        echo "Error: $tool not found beside this script." >&2
        exit 1
    }
done

command -v mlr >/dev/null 2>&1 || {
    echo "Error: mlr was not found on PATH." >&2
    exit 1
}

python3 "$script_dir/aimcsv.py" "$race_file" |
    python3 "$script_dir/track.py" --track-config "$track_file" |
    python3 "$script_dir/interval.py" --start "$start" --end "$end" --divisions "$divisions" |
    mlr --csv filter "\$IntervalPass == $pass" |
    python3 "$script_dir/plot.py" \
        --x "TrackPosition" \
        --y "Throttle" \
        --type line \
        --no-markers \
        --gap-column "Time" \
        --xlabel "Track position" \
        --ylabel "Throttle (%)" \
        --title "Throttle - pass $pass" \
        --output "$output"

echo "Created: $output"
