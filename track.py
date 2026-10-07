#!/usr/bin/env python3
"""Reusable CSV-in/CSV-out race enrichment for Miller.
Adds track position, reference distance, metre coordinates, observed lap number
and continuity. Retains all records; YAML breaks and AIM beacons are ignored.
Lap 0 is initial partial; LapKnown becomes false after interrupted coverage.
Lap counts observed forward position-zero crossings, not official race laps.
Example: python aimcsv.py race.csv | python track.py --track track-project.json
Interval timing is deliberately a separate downstream operation.
Requires numpy and PyYAML (same dependencies as the previous track.py).
"""
import json
import re
import argparse
import bisect
import csv
import math
from pathlib import Path
import sys
import numpy as np
import yaml

ADDED = ['TrackPosition', 'TrackDistanceM', 'OffTrack', 'TrackX', 'TrackY', 'Lap', 'LapKnown', 'Continuity', 'ContinuityReason']


def read_rows(stream):
    records = list(csv.reader(stream))
    if not records:
        raise ValueError('Input is empty.')
    beacons = []
    if records[0][:2] == ['Format', 'AiM CSV File']:
        index = next((i for i, r in enumerate(records) if r and r[0] == 'Time' and 'GPS Latitude' in r and 'GPS Longitude' in r), None)
        if index is None:
            raise ValueError('AiM GPS channel header not found.')
        for r in records[:index]:
            if r and r[0] == 'Beacon Markers':
                beacons = [float(v) for v in r[1:] if v.strip()]
        header, data = records[index], records[index+2:]
    else:
        header, data = records[0], records[1:]
    if len(header) != len(set(header)):
        raise ValueError('Duplicate CSV columns.')
    rows = []
    for r in data:
        if not r or not any(r):
            continue
        if len(r) != len(header):
            raise ValueError('Wrong number of sample fields.')
        rows.append(dict(zip(header, r)))
    if any(not math.isfinite(v) for v in beacons) or beacons != sorted(set(beacons)):
        raise ValueError('Invalid beacon markers.')
    return header, rows, beacons


def load_track(path):
    if path.suffix.lower() == '.json':
        config = json.loads(path.read_text(encoding='utf-8-sig'))
        if config.get('format') != 'track-editor-master-v1':
            raise ValueError('Expected a prepared whole-track JSON.')
        divisions = config['divisions']
        origin = np.array([config['origin']['longitude'], config['origin']['latitude']], dtype=float)
        scale = np.array([math.cos(math.radians(origin[1])), 1.0]) * (math.pi / 180 * 6371000)
        xy = np.array([n['reference'][:2] for n in config['nodes']], dtype=float)
        positions = np.array([n['position'] for n in config['nodes']], dtype=float)
        points = xy / scale + origin
    else:
        config = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
        divisions = config['divisions']
        with (path.parent / config['reference_csv']).open(newline='', encoding='utf-8-sig') as f:
            points = np.array([(float(r['longitude_deg']), float(r['latitude_deg'])) for r in csv.DictReader(f)])
        if len(points) < 2:
            raise ValueError('Reference needs two points.')
        if not np.allclose(points[0], points[-1], rtol=0, atol=1e-9):
            points = np.vstack([points, points[0]])
        origin = points[0]
        scale = np.array([math.cos(math.radians(origin[1])), 1.0]) * (math.pi / 180 * 6371000)
        xy = (points-origin)*scale
        lengths = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        if lengths.sum() <= 0:
            raise ValueError('Reference has zero length.')
        positions = np.r_[0, np.cumsum(lengths)] / lengths.sum() * divisions
    if isinstance(divisions, bool) or not isinstance(divisions, int) or divisions <= 0:
        raise ValueError('divisions must be a positive integer.')
    if len(xy) < 2 or not np.isfinite(xy).all() or not np.isfinite(points).all() or not np.isfinite(positions).all():
        raise ValueError('Reference must contain finite coordinates.')
    if (np.abs(points[:,0]) > 180).any() or (np.abs(points[:,1]) > 90).any():
        raise ValueError('Reference coordinates out of range.')
    if positions[0] != 0 or abs(positions[-1]-divisions) > 1e-6 or (np.diff(positions) < 0).any():
        raise ValueError('Reference position scale must run from 0 to divisions.')
    vectors = np.diff(xy, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    keep = lengths > 0
    if not keep.any():
        raise ValueError('Reference has zero length.')
    threshold = float(config.get('off_track', {}).get('max_distance_m', 20))
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError('Invalid off-track threshold.')
    return dict(config=config, points=points, origin=origin, scale=scale,
                starts=xy[:-1][keep], vectors=vectors[keep], lengths=lengths[keep],
                positions=positions[:-1][keep], spans=np.diff(positions)[keep], threshold=threshold)


def classify(lon, lat, geometry, previous=None):
    g = geometry
    point = (np.array([lon,lat])-g['origin'])*g['scale']
    fractions = np.clip(np.sum((point-g['starts'])*g['vectors'],axis=1)/g['lengths']**2,0,1)
    distances = np.linalg.norm(point-(g['starts']+fractions[:,None]*g['vectors']),axis=1)
    D = g['config']['divisions']
    positions = (g['positions']+fractions*g['spans']) % D
    index = int(np.argmin(distances))
    if previous is not None:
        candidates = np.flatnonzero(distances <= distances[index]+0.5)
        delta = (positions[candidates]-previous+D/2)%D-D/2
        index = int(candidates[np.argmin(np.abs(delta))])
    distance = float(distances[index])
    return float(positions[index]), distance, distance > g['threshold'], float(point[0]), float(point[1])


def enrich(rows, geometry, time_column='Time', latitude='GPS Latitude', longitude='GPS Longitude', max_gap=1.0):
    """Keep every record. Lap counts observed forward start-line crossings.
    Lap 0 is the initial partial lap. LapKnown is false after an interruption
    until the next observed crossing; missed laps are never guessed.
    """
    D=geometry['config']['divisions']
    previous=None;old_time=None;previous_status=None;continuity=0;lap=0;lap_known=False
    since_crossing=float('inf');samples=[]
    for row in rows:
        t=float(row[time_column])
        if not math.isfinite(t) or (old_time is not None and t<=old_time):
            raise ValueError('Time must increase and contain finite numeric seconds.')
        gap=old_time is not None and t-old_time>max_gap
        old_time=t
        row.update({c:'' for c in ADDED})
        try:
            lon=float(row[longitude]);lat=float(row[latitude])
            if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon)>180 or abs(lat)>90:
                raise ValueError()
        except (ValueError,TypeError):
            status='invalid_gps';row['OffTrack']='true';position=None
        else:
            candidate_previous=previous[1] if previous and not gap else None
            position,distance,off,x,y=classify(lon,lat,geometry,candidate_previous)
            row.update(TrackPosition='' if off else f'{position:.6f}',TrackDistanceM=f'{distance:.3f}',OffTrack=str(off).lower(),TrackX=f'{x:.6f}',TrackY=f'{y:.6f}')
            status='off_track' if off else 'on_track';samples.append((lon,lat,off))
        reason=''
        if previous_status is None:reason='recording_start'
        elif gap:reason='time_gap'
        elif status!=previous_status:reason='returned_to_track' if status=='on_track' else status
        delta=None
        if status=='on_track' and previous is not None and not gap:
            old_p=previous[1];delta=(position-old_p+D/2)%D-D/2
            if abs(delta)>D*.1:reason='position_jump'
            elif delta < -D*.01:reason='reverse_movement'
        if reason:
            continuity+=1
            if reason!='recording_start':lap_known=False
        if status!='on_track':
            lap_known=False;previous=None
        else:
            if delta is not None and not reason:
                if delta>0:
                    since_crossing+=delta
                    crossed=previous[1]>D*.8 and position<D*.2
                    if crossed and since_crossing>=D*.5:
                        lap+=1;lap_known=True;since_crossing=0
            previous=t,position
        row.update(Lap=lap,LapKnown=str(lap_known).lower(),Continuity=continuity,ContinuityReason=reason)
        previous_status=status
    return samples


def diagnostic(path, geometry, samples):
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,9))
    points=geometry['points'];ax.plot(points[:,0],points[:,1],color='0.6',label='Reference')
    for off,color,label in [(False,'tab:blue','Accepted'),(True,'tab:orange','OffTrack')]:
        chosen=np.array([(lo,la) for lo,la,o in samples if o==off])
        if len(chosen):ax.scatter(chosen[:,0],chosen[:,1],s=3,color=color,label=label)
    ax.set_aspect(1/math.cos(math.radians(geometry['origin'][1])))
    ax.ticklabel_format(useOffset=False,style='plain');ax.legend();ax.grid(alpha=.25)
    ax.set_title(geometry['config']['track']);fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description='Enrich race CSV for Miller: track positions, observed laps and continuity. Retains every sample; no interval timing.')
    p.add_argument('file',nargs='?',help='Ordinary sample CSV; omit for stdin. Original AIM CSV is also accepted.')
    p.add_argument('--input',dest='input_file')
    p.add_argument('--track-config','--config','--track',required=True,type=Path,dest='config',help='Prepared track JSON, or YAML and reference CSV; breaks ignored')
    p.add_argument('--samples-out','-o','--output',dest='output',type=Path,help='Default: CSV to stdout')
    p.add_argument('--diagnostic-map','--map',dest='map_file',type=Path)
    p.add_argument('--time',default='Time')
    p.add_argument('--latitude',default='GPS Latitude')
    p.add_argument('--longitude',default='GPS Longitude')
    p.add_argument('--max-gap',type=float,default=1.0)
    p.add_argument('--max-distance',type=float,help='Reference-distance threshold in metres (JSON default: 20)')
    if len(sys.argv)==1:p.print_help();return
    args=p.parse_args()
    if args.file and args.input_file:p.error('Use one input option.')
    source_path=args.input_file or args.file
    if not math.isfinite(args.max_gap) or args.max_gap<=0:p.error('--max-gap must be positive.')
    inputs=[Path(v).resolve() for v in (source_path,args.config) if v]
    outputs=[v.resolve() for v in (args.output,args.map_file) if v]
    if len(set(outputs))!=len(outputs) or set(inputs)&set(outputs):p.error('Output paths must differ from inputs and from each other.')
    g=load_track(args.config)
    if args.max_distance is not None:
        if not math.isfinite(args.max_distance) or args.max_distance<=0:p.error('--max-distance must be positive.')
        g['threshold']=args.max_distance
    if source_path:
        with open(source_path,newline='',encoding='utf-8-sig') as f:header,rows,_=read_rows(f)
    else:header,rows,_=read_rows(sys.stdin)
    if not rows:raise ValueError('No samples.')
    if any(c not in header for c in [args.time,args.latitude,args.longitude]):raise ValueError('Time/GPS columns missing.')
    if set(header)&set(ADDED):raise ValueError('Input already has enrichment columns.')
    samples=enrich(rows,g,args.time,args.latitude,args.longitude,args.max_gap)
    if not args.output and hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(newline='')
    target=args.output.open('w',newline='',encoding='utf-8') if args.output else sys.stdout
    try:
        w=csv.DictWriter(target,fieldnames=header+ADDED);w.writeheader();w.writerows(rows)
    finally:
        if args.output:target.close()
    if args.map_file:diagnostic(args.map_file,g,samples)
    off_count=sum(r['OffTrack']=='true' for r in rows)
    print(f"{len(rows):,} samples retained; {off_count:,} OffTrack; {max(r['Lap'] for r in rows)} observed forward crossings. Lap 0 is initial partial; interruptions may hide laps.",file=sys.stderr)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,csv.Error,yaml.YAMLError) as exc:
        print(f'track.py: error: {exc}',file=sys.stderr);sys.exit(2)

