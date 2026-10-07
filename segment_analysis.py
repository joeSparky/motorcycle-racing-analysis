"""Analyze saved sections with the existing track/interval/timing tools."""
import argparse
import json
from pathlib import Path
import sys
import track
from interval import visits
from timing import summarize


def analyze(race_path, track_path):
    geometry = track.load_track(Path(track_path))
    config = geometry['config']
    D = config['divisions']
    sections = config.get('sections') or []
    if not sections:
        raise ValueError('No saved segments. Use Edit Segments and save boundaries first.')
    sections = sorted(sections, key=lambda s: s['start'])
    previous = 0
    for section in sections:
        a, b = section['start'], section['end']
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int) or a != previous or not a < b <= D:
            raise ValueError('Segments must cover the track in order, with shared boundaries and no gaps or overlaps.')
        previous = b
    if previous != D:
        raise ValueError('The last segment must end at the track divisions value.')
    with Path(race_path).open(encoding='utf-8-sig', newline='') as f:
        header, rows, _ = track.read_rows(f)
    if not rows:
        raise ValueError('Race CSV has no samples.')
    if set(header) & set(track.ADDED):
        raise ValueError('Choose the original race CSV, not an already enriched export.')
    track.enrich(rows, geometry)
    results = []
    for section in sections:
        passes = summarize(visits(rows, section['start'], section['end'], D))
        complete = [p for p in passes if p['Complete'] == 'true']
        best = min(complete, key=lambda p: float(p['IntervalTime'])) if complete else None
        results.append({'start': section['start'], 'end': section['end'], 'passes': passes, 'best': best})
    lap_passes = summarize(visits(rows, 0, D, D))
    complete_laps = [p for p in lap_passes if p['Complete'] == 'true']
    best_lap = min(complete_laps, key=lambda p: float(p['IntervalTime'])) if complete_laps else None
    total = sum(float(s['best']['IntervalTime']) for s in results) if all(s['best'] for s in results) else None
    return {'track': config.get('track', Path(track_path).stem), 'segments': results, 'theoretical_time': total, 'best_actual_lap': best_lap}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--race', required=True)
    parser.add_argument('--track', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.race, args.track)))
    except Exception as exc:
        print(f'Segment analysis: {exc}', file=sys.stderr)
        sys.exit(2)
