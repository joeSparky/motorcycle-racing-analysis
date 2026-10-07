#!/usr/bin/env bash
# Plot rider paths through a track-position interval.
#
# Environment convention:
#   $race  = current race CSV
#   $track = current track YAML
#
# Command-line values override the environment variables.

set -euo pipefail

usage() {
    cat <<'EOF'
Plot rider paths through a track-position interval.

Usage:
  ./plotInterval.sh <start> <end> [options]

Environment:
  race              Current rider race/practice CSV.
  track             Current track YAML configuration.

Options:
  --race FILE       Override $race.
  --track FILE      Override $track.
  --laps 5,6      Optional lap numbers. Default: all laps.
  --no-legend       Hide the pass legend. Default: show legend.
  --output-dir DIR  Directory for generated PNG. Default: current directory.
  -h, --help        Show this help.

Examples:
  ./plotInterval.sh 2437 4215
  ./plotInterval.sh 2437 4215 --laps 5,6
  ./plotInterval.sh 2437 4215 --race ../racingData/138.csv --track ../racingData/nelsonLedges.yaml

Outputs:
  All laps:      138-interval2437-4215.png
  Selected laps: 138-interval2437-4215-passes5-6.png
EOF
}

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
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

csv="${race:-}"
yaml="${track:-}"
laps=""
no_legend=0
output_dir="."

while [[ $# -gt 0 ]]; do
    case "$1" in
        --race)
            [[ $# -ge 2 ]] || { echo "Error: --race requires a CSV filename." >&2; exit 2; }
            csv="$2"
            shift 2
            ;;
        --track)
            [[ $# -ge 2 ]] || { echo "Error: --track requires a YAML filename." >&2; exit 2; }
            yaml="$2"
            shift 2
            ;;
        --laps)
            [[ $# -ge 2 ]] || { echo "Error: --laps requires lap numbers." >&2; exit 2; }
            laps="$2"
            shift 2
            ;;
        --no-legend)
            no_legend=1
            shift
            ;;
        --output-dir)
            [[ $# -ge 2 ]] || { echo "Error: --output-dir requires a directory." >&2; exit 2; }
            output_dir="$2"
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

[[ "$start" =~ ^[0-9]+$ ]] || {
    echo "Error: start must be an integer from 0 through 9999." >&2
    exit 2
}
[[ "$end" =~ ^[0-9]+$ ]] || {
    echo "Error: end must be an integer from 0 through 9999." >&2
    exit 2
}
(( start <= 9999 && end <= 9999 )) || {
    echo "Error: track positions must be from 0 through 9999." >&2
    exit 2
}
(( start <= end )) || {
    echo "Error: start position must not be greater than end position." >&2
    exit 2
}

[[ -n "$csv" ]] || {
    echo 'Error: no race CSV specified and $race is not set.' >&2
    echo 'Use setRace or --race FILE.' >&2
    exit 1
}

[[ -n "$yaml" ]] || {
    echo 'Error: no track YAML specified and $track is not set.' >&2
    echo 'Use setTrack or --track FILE.' >&2
    exit 1
}

[[ -f "$csv" ]] || { echo "Error: race CSV not found: $csv" >&2; exit 1; }
[[ -f "$yaml" ]] || { echo "Error: track YAML not found: $yaml" >&2; exit 1; }

csv="$(realpath "$csv")"
yaml="$(realpath "$yaml")"
mkdir -p "$output_dir"
output_dir="$(realpath "$output_dir")"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$script_dir/track.py" ]]; then
    track_cmd=(python3 "$script_dir/track.py")
elif command -v track.py >/dev/null 2>&1; then
    track_cmd=(track.py)
elif command -v track >/dev/null 2>&1; then
    track_cmd=(track)
else
    echo "Error: track.py/track was not found." >&2
    exit 1
fi

if [[ -f "$script_dir/plot.py" ]]; then
    plot_cmd=(python3 "$script_dir/plot.py")
elif command -v plot.py >/dev/null 2>&1; then
    plot_cmd=(plot.py)
elif command -v plot >/dev/null 2>&1; then
    plot_cmd=(plot)
else
    echo "Error: plot.py/plot was not found." >&2
    exit 1
fi

command -v mlr >/dev/null 2>&1 || {
    echo "Error: mlr was not found on PATH." >&2
    exit 1
}

session_name="$(basename "${csv%.*}")"
output_file="${session_name}-interval${start}-${end}.png"
title="${session_name} - Positions ${start}-${end}"

# Current track.py emits TrackPosition on the 0-9999 scale.
filter="\$TrackPosition >= ${start} && \$TrackPosition <= ${end}"

if [[ -n "$laps" ]]; then
    mapfile -t lap_array < <(
        tr ',' '\n' <<<"$laps" |
        sed '/^[[:space:]]*$/d; s/^[[:space:]]*//; s/[[:space:]]*$//' |
        sort -n -u
    )

    [[ ${#lap_array[@]} -gt 0 ]] || {
        echo "Error: --laps did not contain any lap numbers." >&2
        exit 2
    }

    for p in "${lap_array[@]}"; do
        [[ "$p" =~ ^[0-9]+$ ]] || {
            echo "Error: invalid lap number: $p" >&2
            exit 2
        }
    done

    lap_tag="$(IFS=-; echo "${lap_array[*]}")"
    lap_title="$(IFS=', '; echo "${lap_array[*]}")"
    output_file="${session_name}-interval${start}-${end}-laps${lap_tag}.png"
    title="${title} - Laps ${lap_title}"

    conditions=""
    for p in "${lap_array[@]}"; do
        [[ -n "$conditions" ]] && conditions+=" || "
        conditions+="\$Lap == ${p}"
    done
    filter+=" && (${conditions})"
fi

plot_options=()
(( no_legend )) && plot_options+=(--no-legend)

output_file="${output_dir}/${output_file}"

"${track_cmd[@]}" "$csv" --config "$yaml" |
    mlr --csv filter "$filter" |
    "${plot_cmd[@]}" \
        --x "GPS Longitude" --y "GPS Latitude" \
        --geo --type line --no-markers \
        --gap-column Time --gap-max 1 \
        --group Lap --line-width 2 \
        --title "$title" -o "$output_file" \
        "${plot_options[@]}"

echo "Created: $output_file"
