#!/usr/bin/env python3
"""
plot.py - Generic CSV plotting tool.

Reads ordinary CSV from stdin or an optional input file and writes a graph.

Examples:

    plot --x Time --y RPM --type line -o rpm.png

    plot --x Time --y RPM --y Speed --type line -o combined.png

    plot --x Time --graph RPM --graph Speed --type line -o stacked.png
"""

import json
from pathlib import Path
import argparse
import copy
import csv
import math
import sys

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot numeric columns from ordinary CSV.")
    p.add_argument("file", nargs="?", help="CSV input file; omit to read stdin")
    p.add_argument("-x", "--x", required=True, help="X-axis column")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "-y", "--y", action="append",
        help="Y column; repeat to draw multiple series on one graph"
    )
    mode.add_argument(
        "--graph", action="append",
        help="Y column for a separate vertically stacked graph; repeat as needed"
    )

    p.add_argument(
        "--type", choices=["scatter", "line"], default="scatter",
        help="Graph type (default: scatter)"
    )
    p.add_argument("-o", "--output", default="plot.png", help="Output image/PDF filename")
    p.add_argument("--title")
    p.add_argument(
        "--source",
        help="Source filename or other source description to display below the title"
    )
    p.add_argument("--xlabel")
    p.add_argument("--ylabel")
    p.add_argument("--xmin", type=float)
    p.add_argument("--xmax", type=float)
    p.add_argument("--ymin", type=float)
    p.add_argument("--ymax", type=float)
    p.add_argument("--width", type=float, default=10)
    p.add_argument("--height", type=float, default=6)
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--marker-size", type=float)
    p.add_argument("--line-width", type=float, default=1.0)
    p.add_argument("--no-grid", action="store_true")
    p.add_argument("--no-legend", action="store_true")
    p.add_argument("--overlay", help="Reference CSV drawn behind the main data")
    p.add_argument("--overlay-x", help="Reference X column (defaults to --x)")
    p.add_argument("--overlay-y", help="Reference Y column (defaults to the single --y)")
    p.add_argument("--overlay-label", default="Track reference")
    p.add_argument("--label", help="Label for the main series")
    p.add_argument("--geo", action="store_true", help="Longitude X / latitude Y with corrected map proportions")
    p.add_argument("--aim", action="store_true", help="Read an original AiM CSV, skipping metadata and units")
    p.add_argument("--time-min", type=float)
    p.add_argument("--time-max", type=float)
    p.add_argument("--color", help="Numeric column used to color the main points or line")
    p.add_argument("--color-label", help="Color bar label")
    p.add_argument("--color-low", default="blue", help="Color at minimum value")
    p.add_argument("--color-high", default="red", help="Color at maximum value")
    p.add_argument("--fill-closed-color", action="store_true", help="Interpolate blank colors at the duplicated endpoint of a closed track")
    p.add_argument("--no-markers", action="store_true", help="Draw lines without point markers")
    p.add_argument("--gap-column", help="Break lines when this numeric column jumps forward or resets")
    p.add_argument("--gap-max", type=float, default=1.0, help="Maximum gap before breaking a line")
    p.add_argument("--group", help="Numeric column identifying separate series (for example Pass)")
    p.add_argument('--track-json', help='Prepared track JSON; requires --x TrackX --y TrackY')
    p.add_argument('--points-json', help='Interesting-points JSON linked to --track-json')
    p.add_argument('--interval', help='Clip the reference and markers to START-END positions; filter rider samples with Miller')
    args = p.parse_args()
    if args.points_json and not args.track_json:
        p.error('--points-json requires --track-json')
    if args.interval and not args.track_json:
        p.error('--interval requires --track-json')
    if args.track_json and (args.graph or args.y != ['TrackY'] or args.x != 'TrackX' or args.geo or args.overlay):
        p.error('--track-json requires --x TrackX --y TrackY, without --geo, --overlay or --graph')
    if args.group and (args.color or args.graph or len(args.y) != 1):
        p.error("--group requires one --y and cannot be combined with --color or --graph")
    if (args.overlay or args.geo or args.color) and (args.graph or len(args.y) != 1):
        p.error("--overlay and --geo require exactly one --y and no --graph")
    return args


def read_numeric_csv(source, xcol, ycols, aim=False, time_min=None, time_max=None, color_col=None):
    if aim:
        records = csv.reader(source)
        for header in records:
            if header and header[0] == "Time" and xcol in header and all(c in header for c in ycols):
                break
        else:
            raise ValueError("AiM channel header not found.")
        next(records, None)  # Units row
        reader = csv.DictReader([], fieldnames=header)
        rows = (dict(zip(header, row)) for row in records if row and any(row))
    else:
        reader = csv.DictReader(source)
        rows = reader

    if not reader.fieldnames:
        raise ValueError("CSV input has no header row.")

    required = [xcol] + ycols
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        raise ValueError("Missing column(s): " + ", ".join(missing))

    xs = []
    ys = {c: [] for c in ycols}

    if (time_min is not None or time_max is not None) and "Time" not in reader.fieldnames:
        raise ValueError("Time filtering requires a Time column.")
    for row_number, row in enumerate(rows, start=2):
        if time_min is not None or time_max is not None:
            t = float(row["Time"])
            if (time_min is not None and t < time_min) or (time_max is not None and t > time_max):
                continue
        try:
            x = float(row[xcol])
            values = {c: (float("nan") if c == color_col and not row[c].strip() else float(row[c])) for c in ycols}
        except (TypeError, ValueError):
            raise ValueError(
                f"Non-numeric or missing value in required column at CSV row {row_number}."
            )

        if not math.isfinite(x) or any(not math.isfinite(v) for c, v in values.items() if c != color_col):
            raise ValueError(
                f"Non-finite value in required column at CSV row {row_number}."
            )

        xs.append(x)
        for c, v in values.items():
            ys[c].append(v)

    if not xs:
        raise ValueError("CSV contains no data rows.")

    return xs, ys


def set_title(fig, title, source):
    if title and source:
        fig.suptitle(f"{title}\nSource: {source}")
    elif title:
        fig.suptitle(title)
    elif source:
        fig.suptitle(f"Source: {source}")


def draw_series(ax, xs, values, label, args):
    if args.type == "scatter":
        ax.scatter(xs, values, s=args.marker_size or 12, label=label)
    else:
        if args.gap_column:
            px, py = [], []
            for i, (x, y) in enumerate(zip(xs, values)):
                if i and (args.gap_values[i] - args.gap_values[i-1] > args.gap_max or args.gap_values[i] < args.gap_values[i-1]):
                    px.append(float("nan")); py.append(float("nan"))
                px.append(x); py.append(y)
            xs, values = px, py
        ax.plot(
            xs,
            values,
            marker=None if args.no_markers else ".",
            markersize=args.marker_size or 3,
            linewidth=args.line_width,
            label=label,
        )


def configure_common_axis(ax, args):
    if args.xmin is not None or args.xmax is not None:
        ax.set_xlim(left=args.xmin, right=args.xmax)

    if args.ymin is not None or args.ymax is not None:
        ax.set_ylim(bottom=args.ymin, top=args.ymax)

    if not args.no_grid:
        ax.grid(True)


def make_single_graph(args, xs, ys):
    ycols = args.y
    fig, ax = plt.subplots(figsize=(args.width, args.height))

    if args.overlay:
        ox = args.overlay_x or args.x
        oy = args.overlay_y or ycols[0]
        with open(args.overlay, newline="", encoding="utf-8-sig") as reference:
            rx, ry = read_numeric_csv(reference, ox, [oy])
        ax.plot(rx, ry[oy], color="0.55", linewidth=2, label=args.overlay_label, zorder=1)
    for col in ycols:
        if args.color:
            colors = np.asarray(ys[args.color], dtype=float).copy()
            missing = ~np.isfinite(colors)
            if missing.any():
                closed = len(xs) > 3 and xs[0] == xs[-1] and ys[col][0] == ys[col][-1]
                if not args.fill_closed_color or not closed or missing[1:-1].any():
                    raise ValueError("Blank/non-finite colors: --fill-closed-color only fills missing endpoints of a closed track.")
                endpoint = (colors[1] + colors[-2]) / 2
                if np.isfinite(colors[0]):
                    endpoint = colors[0]
                elif np.isfinite(colors[-1]):
                    endpoint = colors[-1]
                colors[missing] = endpoint
            cmap = LinearSegmentedColormap.from_list("height", [args.color_low, args.color_high])
            norm = plt.Normalize(float(colors.min()), float(colors.max()))
            if args.type == "line":
                points = np.column_stack([xs, ys[col]])
                segments = np.stack([points[:-1], points[1:]], axis=1)
                artist = LineCollection(segments, cmap=cmap, norm=norm, linewidths=args.line_width)
                artist.set_array((colors[:-1] + colors[1:]) / 2)
                ax.add_collection(artist)
                ax.autoscale_view()
            else:
                artist = ax.scatter(xs, ys[col], c=colors, cmap=cmap, norm=norm, s=args.marker_size or 12)
            fig.colorbar(artist, ax=ax, label=args.color_label or args.color)
        elif args.group:
            groups = np.asarray(ys[args.group])
            for group in sorted(set(groups)):
                indices = np.flatnonzero(groups == group)
                series_args = copy.copy(args)
                if args.gap_column:
                    series_args.gap_values = [args.gap_values[i] for i in indices]
                draw_series(ax, [xs[i] for i in indices], [ys[col][i] for i in indices],
                            f"{args.group} {group:g}", series_args)
        else:
            draw_series(ax, xs, ys[col], args.label or col, args)
    if args.track_json:
        draw_track_overlays(ax, args)
    if args.geo:
        lat = sum(ys[ycols[0]]) / len(xs)
        if not all(-180 <= x <= 180 for x in xs) or not all(-90 <= y <= 90 for y in ys[ycols[0]]):
            raise ValueError("--geo requires longitude X and latitude Y in degrees.")
        ax.set_aspect(1 / math.cos(math.radians(lat)), adjustable="box")
        ax.ticklabel_format(useOffset=False, style="plain")

    configure_common_axis(ax, args)

    ax.set_xlabel(args.xlabel or ('East (m)' if args.track_json else args.x))
    if args.ylabel:
        ax.set_ylabel(args.ylabel)
    elif len(ycols) == 1:
        ax.set_ylabel('North (m)' if args.track_json else ycols[0])

    if (len(ycols) > 1 or args.overlay or args.track_json or args.label or args.group) and not args.no_legend:
        ax.legend(bbox_to_anchor=(1.03, 1), loc="upper left") if args.track_json else ax.legend()

    set_title(fig, args.title, args.source)
    fig.tight_layout(rect=(0, 0, 1, 0.94) if (args.title or args.source) else None)
    return fig


def draw_track_overlays(ax, args):
    """Draw world-metre reference and markers, using the editor's exact positions."""
    project = json.loads(Path(args.track_json).read_text(encoding='utf-8-sig'))
    if project.get('format') != 'track-editor-master-v1':
        raise ValueError('Expected a prepared track JSON.')
    divisions = project['divisions']
    nodes = project['nodes']
    positions = np.array([n['position'] for n in nodes], dtype=float)
    reference = np.array([n['reference'][:2] for n in nodes], dtype=float)
    if len(nodes) < 2 or not np.isfinite(reference).all() or not np.isfinite(positions).all() or (np.diff(positions) <= 0).any():
        raise ValueError('Invalid track reference.')
    if not isinstance(divisions,int) or divisions <= 0 or positions[0] != 0 or abs(positions[-1]-divisions)>1e-6:
        raise ValueError('Invalid position scale.')
    ranges = [(0, divisions)]
    if args.interval:
        import re
        match = re.fullmatch(r'(\d+)\s*[-–,]\s*(\d+)', args.interval.strip())
        if not match:
            raise ValueError('Expected --interval START-END.')
        start,end = map(int,match.groups())
        if start>divisions or end>divisions or start==end or (start==divisions and end==0):
            raise ValueError('Invalid interval positions.')
        ranges = [(start,end)] if start<end else [(start,divisions),(0,end)]
    def at(pos):
        return np.array([np.interp(pos, positions, reference[:,j]) for j in (0,1)])
    for i,(start,end) in enumerate(ranges):
        if end <= start:
            continue
        selected = reference[(positions>start)&(positions<end)]
        line = np.vstack([at(start),selected,at(end)])
        ax.plot(line[:,0],line[:,1],color='0.4',linestyle='--',linewidth=1.8,
                label='Track reference' if i==0 else None,zorder=1)
    if args.interval:
        for pos,label,color in [(int(match[1]),'Start','#279655'),(int(match[2]),'End','#d55344')]:
            q=at(pos);ax.scatter(*q,s=55,color=color,zorder=5)
            ax.annotate(f'{label} {pos}',q,xytext=(8,9),textcoords='offset points',fontsize=10)
    if args.points_json:
        points=json.loads(Path(args.points_json).read_text(encoding='utf-8-sig'))
        identity=dict(track=project['track'],divisions=divisions,origin=project['origin'],
                      reference=[[n['position'],*n['reference'][:2]] for n in nodes])
        if points.get('format')!='track-interesting-points-v1' or points.get('track_identity') != identity:
            raise ValueError('Points file does not match the prepared track reference.')
        palette={'entry':('#16a085','s'),'apex':('#b33ed2','D'),'exit':('#d14b39','^')}
        used=set()
        for marker in points['markers']:
            kind=marker['type']
            if kind not in palette or not all(math.isfinite(float(marker[k])) for k in ['x_m','y_m','track_position']):
                raise ValueError('Invalid interesting point.')
            if not any(a<=marker['track_position']<=b for a,b in ranges):
                continue
            color,symbol=palette[kind]
            ax.scatter(marker['x_m'],marker['y_m'],s=85,color=color,marker=symbol,
                       edgecolor='white',linewidth=.8,label=kind.title() if kind not in used else None,zorder=6)
            used.add(kind)
            ax.annotate(marker['label'],(marker['x_m'],marker['y_m']),xytext=(9,-12),
                        textcoords='offset points',fontsize=10,color=color,
                        bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1))
    ax.margins(.12)
    ax.set_aspect('equal',adjustable='box')
    ax.set_xlabel(args.xlabel or 'East (m)')
    ax.set_ylabel(args.ylabel or 'North (m)')


def make_stacked_graphs(args, xs, ys):
    graph_cols = args.graph
    count = len(graph_cols)

    # Treat --height as the approximate height of one graph. This keeps
    # two or three stacked plots readable without requiring another option.
    fig_height = args.height * count
    fig, axes = plt.subplots(
        count,
        1,
        sharex=True,
        figsize=(args.width, fig_height),
        squeeze=False,
    )
    axes = axes[:, 0]

    for ax, col in zip(axes, graph_cols):
        draw_series(ax, xs, ys[col], col, args)
        configure_common_axis(ax, args)
        ax.set_ylabel(args.ylabel or col)

        # Each subplot contains one series, so a legend would just repeat
        # the Y-axis label and is intentionally omitted.

    axes[-1].set_xlabel(args.xlabel or args.x)

    set_title(fig, args.title, args.source)
    fig.tight_layout(rect=(0, 0, 1, 0.96) if (args.title or args.source) else None)
    return fig


def main():
    args = parse_args()
    ycols = args.graph if args.graph else args.y

    if args.color:
        ycols = ycols + [args.color]

    if args.gap_column and args.gap_column not in ycols:
        ycols = ycols + [args.gap_column]

    if args.group and args.group not in ycols:
        ycols = ycols + [args.group]

    source = (
        open(args.file, "r", newline="", encoding="utf-8-sig")
        if args.file
        else sys.stdin
    )

    try:
        xs, ys = read_numeric_csv(source, args.x, ycols, args.aim, args.time_min, args.time_max, args.color)
    finally:
        if args.file:
            source.close()

    if args.gap_column:
        args.gap_values = ys[args.gap_column]

    if args.graph:
        fig = make_stacked_graphs(args, xs, ys)
    else:
        fig = make_single_graph(args, xs, ys)

    fig.savefig(args.output, dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, csv.Error) as exc:
        print(f"plot.py: error: {exc}", file=sys.stderr)
        sys.exit(2)
