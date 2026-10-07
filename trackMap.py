#!/usr/bin/env python3
"""Draw equal-distance track sections: python trackMap.py nelsonLedges.yaml"""
import argparse
import csv
from pathlib import Path
import numpy as np
import yaml
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('-o', '--output')
    parser.add_argument('--no-legend', action='store_true', help='Hide the section legend')
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    divisions = int(config['divisions'])
    breaks = config['breaks']
    if divisions <= 0 or breaks != sorted(set(breaks)) or any(not isinstance(b, int) or not 0 < b < divisions for b in breaks):
        parser.error('Breaks must be unique increasing integers between 0 and divisions.')
    reference = args.config.parent / config['reference_csv']
    with reference.open(newline='', encoding='utf-8-sig') as f:
        points = np.array([(float(r['longitude_deg']), float(r['latitude_deg'])) for r in csv.DictReader(f)])
    if not np.allclose(points[0], points[-1], rtol=0, atol=1e-9):
        points = np.vstack([points, points[0]])
    latitude = points[:, 1].mean()
    scale = np.array([np.cos(np.radians(latitude)), 1]) * (np.pi / 180 * 6371000)
    lengths = np.linalg.norm(np.diff(points, axis=0) * scale, axis=1)
    distance = np.r_[0, np.cumsum(lengths)]
    target = np.linspace(0, distance[-1], divisions + 1)
    lon = np.interp(target, distance, points[:, 0])
    lat = np.interp(target, distance, points[:, 1])
    boundaries = [0] + breaks + [divisions]
    fig, ax = plt.subplots(figsize=(11, 10))
    palette = plt.get_cmap('tab20')
    for section, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        color = palette((section-1) % 20)
        ax.plot(lon[start:end+1], lat[start:end+1], lw=4, color=color,
                label=f'{section}: {start} → {end if end < divisions else 0}')
        middle = (start + end) // 2
        delta = min(8, max(1, (end-start)//3))
        ax.annotate('', xy=(lon[middle+delta], lat[middle+delta]),
                    xytext=(lon[middle], lat[middle]),
                    arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    offsets = {0:(18,0), 47:(20,-12), 193:(18,-14), 239:(20,12),
               464:(-38,8), 511:(-45,-18), 514:(-45,18), 574:(-40,14),
               757:(-28,20), 940:(20,18), 960:(20,0)}
    for number in boundaries[:-1]:
        ax.scatter(lon[number], lat[number], s=35, color='white', edgecolor='black', zorder=5)
        ax.annotate(str(number) if number else '0 · Start/finish',
                    (lon[number], lat[number]), xytext=offsets.get(number,(12,12)),
                    textcoords='offset points', fontsize=10,
                    bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.6'),
                    arrowprops=dict(arrowstyle='-', color='0.35'), zorder=6)
    ax.set_aspect(1 / np.cos(np.radians(latitude)))
    ax.ticklabel_format(useOffset=False, style='plain')
    ax.set_xlabel('Longitude'); ax.set_ylabel('Latitude')
    ax.grid(alpha=0.25)
    ax.margins(0.12)
    ax.set_title(f"{config['track']} — section breaks\n{divisions} equal-distance divisions · CSV direction", pad=18)
    if not args.no_legend:
        ax.legend(title='Section: start → end', bbox_to_anchor=(1.03,1), loc='upper left')
    fig.tight_layout()
    output = args.output or str(args.config.with_name(args.config.stem + '-sections.png'))
    fig.savefig(output, dpi=160, bbox_inches='tight')
    plt.close(fig)
    print(output)

if __name__ == '__main__':
    main()
