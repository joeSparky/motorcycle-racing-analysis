#!/usr/bin/env bash
# Plot rider paths through a track section.
#
# Environment convention:
#   $race  = current race CSV
#   $track = current track YAML
#
# Command-line values override the environment variables.

set -euo pipefail

usage() {
    cat <<'EOF'
Plot rider paths through a track section.

Usage:
  ./plotSection.sh <section> [options]

Environment:
  race              Current rider race/practice CSV.
  track             Current track YAML configuration.

Options:
  --race FILE       Override $race.
  --track FILE      Override $track.
  --passes 5,6      Optional pass numbers. Default: all passes.
  --no-legend       Hide the pass legend. Default: show legend.
  --output-dir DIR  Directory for generated PNG. Default: current directory.
  -h, --help        Show this help.

Examples:
  ./plotSection.sh 4
  ./plotSection.sh 3 --passes 5,6
  ./plotSection.sh 3 --race ../racingData/138.csv --track ../racingData/nelsonLedges.yaml
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

section="$1"
shift

csv="${race:-}"
yaml="${track:-}"
passes=""
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
        --passes)
            [[ $# -ge 2 ]] || { echo "Error: --passes requires pass numbers." >&2; exit 2; }
            passes="$2"
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

[[ "$section" =~ ^[1-9][0-9]*$ ]] || {
    echo "Error: section must be a positive integer." >&2
    exit 2
}

[[ -f "$csv" ]] || { echo "Error: race CSV not found: $csv" >&2; exit 1; }
[[ -f "$yaml" ]] || { echo "Error: track YAML not found: $yaml" >&2; exit 1; }

csv="$(realpath "$csv")"
yaml="$(realpath "$yaml")"
mkdir -p "$output_dir"
output_dir="$(realpath "$output_dir")"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Prefer Python tools beside this script, then commands on PATH.
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
output_file="${session_name}-section${section}.png"
title="${session_name} - Section ${section}"
filter="\$Section == ${section}"

if [[ -n "$passes" ]]; then
    # Accept comma-separated passes, remove duplicates, and sort numerically.
    mapfile -t pass_array < <(
        tr ',' '\n' <<<"$passes" |
        sed '/^[[:space:]]*$/d; s/^[[:space:]]*//; s/[[:space:]]*$//' |
        sort -n -u
    )

    [[ ${#pass_array[@]} -gt 0 ]] || {
        echo "Error: --passes did not contain any pass numbers." >&2
        exit 2
    }

    for p in "${pass_array[@]}"; do
        [[ "$p" =~ ^[1-9][0-9]*$ ]] || {
            echo "Error: invalid pass number: $p" >&2
            exit 2
        }
    done

    pass_tag="$(IFS=-; echo "${pass_array[*]}")"
    pass_title="$(IFS=', '; echo "${pass_array[*]}")"
    output_file="${session_name}-section${section}-passes${pass_tag}.png"
    title="${title} - Passes ${pass_title}"

    conditions=""
    for p in "${pass_array[@]}"; do
        [[ -n "$conditions" ]] && conditions+=" || "
        conditions+="\$Pass == ${p}"
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
        --group Pass --line-width 2 \
        --title "$title" -o "$output_file" \
        "${plot_options[@]}"

echo "Created: $output_file"
