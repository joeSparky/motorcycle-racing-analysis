#!/usr/bin/env bash
# plotElevation.sh
#
# Usage:
#   ./plotElevation.sh --track-csv path/to/track.csv
#   ./plotElevation.sh
#
# If --track-csv is omitted, uses $track_csv.
# $track_csv should point directly to the track CSV file.

set -euo pipefail

track_csv_arg=""

usage() {
    cat <<'EOF'
Usage: plotElevation.sh [--track-csv TRACK.csv]

Options:
  --track-csv TRACK.csv   Track CSV file.
                      If omitted, uses the environment variable $track_csv.
  -h, --help          Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --track-csv|-track-csv)
            [[ $# -ge 2 ]] || {
                echo "Error: $1 requires a CSV filename." >&2
                exit 2
            }
            track_csv_arg="$2"
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

# Command-line argument takes priority over the environment variable.
if [[ -n "$track_csv_arg" ]]; then
    track_csv="$track_csv_arg"
elif [[ -n "${track_csv:-}" ]]; then
    track_csv="$track_csv"
else
    echo 'Error: no track CSV specified and $track_csv is not set.' >&2
    echo 'Use --track-csv TRACK.csv or set $track_csv.' >&2
    exit 1
fi

if [[ ! -f "$track_csv" ]]; then
    echo "Error: track CSV not found: $track_csv" >&2
    exit 1
fi

if [[ "${track_csv,,}" != *.csv ]]; then
    echo "Error: track must be a .csv file: $track_csv" >&2
    exit 1
fi

track_csv="$(realpath "$track_csv")"
track_name="$(basename "${track_csv%.*}")"
output_file="$(pwd)/${track_name}-elevation.png"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Prefer plot.py beside this script, otherwise use plot.py from PATH.
if [[ -f "$script_dir/plot.py" ]]; then
    plot_command=(python3 "$script_dir/plot.py")
elif command -v plot.py >/dev/null 2>&1; then
    plot_command=(plot.py)
else
    echo "Error: plot.py was not found beside this script or on PATH." >&2
    exit 1
fi

"${plot_command[@]}" "$track_csv" \
    --x longitude_deg --y latitude_deg \
    --color elevation_m_inferred \
    --color-label "Elevation (m; inferred units)" \
    --fill-closed-color --type line --line-width 4 \
    --geo --xlabel Longitude --ylabel Latitude \
    --title "$track_name elevation" \
    -o "$output_file"

echo "Created: $output_file"
