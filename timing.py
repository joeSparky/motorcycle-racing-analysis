#!/usr/bin/env python3
"""Convert interval.py sample CSV to one timing CSV row per visit.

python interval.py ... | python timing.py
Reads stdin and writes stdout by default. Keep IntervalContext rows: they
contain boundary brackets. Times are interpolated from TrackPosition and Time,
not taken from first/last selected samples. No GPS matching or plotting occurs.
Partial visits remain in output but have blank IntervalTime and BehindBest.
"""
import argparse
import csv
import math
from pathlib import Path
import sys

FIELDS=['StartPosition','EndPosition','Pass','Lap','LapKnown','Continuity',
        'EntryTime','ExitTime','IntervalTime','BehindBest','Complete','Status']
REQUIRED={'IntervalPass','IntervalStart','IntervalEnd','IntervalDivisions',
          'IntervalStartBracket','IntervalEndBracket','IntervalComplete','IntervalStatus',
          'TrackPosition','Continuity'}


def num(row,key):
    try:value=float(row[key])
    except (KeyError,TypeError,ValueError):raise ValueError(f'{key} must contain finite numbers.')
    if not math.isfinite(value):raise ValueError(f'{key} must contain finite numbers.')
    return value


def crossing(rows,kind,gate,divisions,time_column):
    key='Interval'+kind+'Bracket'
    before=[(i,r) for i,r in enumerate(rows) if r[key]=='before']
    after=[(i,r) for i,r in enumerate(rows) if r[key]=='after']
    if not before and not after:return None
    if len(before)!=1 or len(after)!=1:raise ValueError(f'Incomplete or duplicate {kind.lower()} boundary brackets. Keep all context rows.')
    i,a=before[0];j,b=after[0]
    if j!=i+1:raise ValueError('Boundary bracket samples must be adjacent.')
    if a['Continuity']!=b['Continuity']:raise ValueError('Boundary brackets cross a continuity break.')
    ta,tb=num(a,time_column),num(b,time_column)
    pa,pb=num(a,'TrackPosition')%divisions,num(b,'TrackPosition')%divisions
    delta=(pb-pa+divisions/2)%divisions-divisions/2
    distance=(gate-pa)%divisions
    if delta<=0 or distance>delta+1e-6 or tb<=ta:raise ValueError('Invalid forward boundary brackets.')
    fraction=max(0,min(1,distance/delta))
    return ta+fraction*(tb-ta)


def summarize(reader,time_column='Time'):
    groups={}
    for row in reader:
        if None in row or any(v is None for v in row.values()):raise ValueError('Malformed CSV row.')
        try:pass_number=int(row['IntervalPass'])
        except ValueError:raise ValueError('IntervalPass must be a positive integer.')
        if pass_number<1:raise ValueError('IntervalPass must be positive.')
        groups.setdefault(pass_number,[]).append(row)
    output=[]
    for pass_number,rows in groups.items():
        first=rows[0]
        for key in ['IntervalStart','IntervalEnd','IntervalDivisions','IntervalComplete','IntervalStatus']:
            if any(r[key]!=first[key] for r in rows):raise ValueError(f'Inconsistent {key} within pass {pass_number}.')
        start,end,D=(num(first,k) for k in ['IntervalStart','IntervalEnd','IntervalDivisions'])
        if not all(v.is_integer() for v in [start,end,D]) or D<=0 or not 0<=start<=D or not 0<=end<=D or start==end:raise ValueError('Invalid interval scale.')
        times=[num(r,time_column) for r in rows]
        if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Sample times must increase within a pass.')
        for key in ['IntervalStartBracket','IntervalEndBracket']:
            if any(r[key] not in {'','before','after'} for r in rows):raise ValueError('Invalid boundary flag.')
        claimed=first['IntervalComplete'].lower()
        if claimed not in {'true','false'}:raise ValueError('IntervalComplete must be true or false.')
        entry=crossing(rows,'Start',start%D,D,time_column)
        exit_time=crossing(rows,'End',end%D,D,time_column)
        complete=claimed=='true' and entry is not None and exit_time is not None
        if claimed=='true' and not complete:raise ValueError(f'Pass {pass_number} lacks boundary samples. Keep context rows for timing.')
        if complete and exit_time<=entry:raise ValueError('Exit time must follow entry time.')
        continuities={r['Continuity'] for r in rows}
        if complete and len(continuities)!=1:raise ValueError('Complete pass crosses a continuity break.')
        # Lap label belongs to the first sample after entry, where available.
        lap_row=next((r for r in rows if r['IntervalStartBracket']=='after'),first)
        output.append(dict(StartPosition=int(start),EndPosition=int(end),Pass=pass_number,
                           Lap=lap_row.get('Lap',''),LapKnown=lap_row.get('LapKnown',''),
                           Continuity=first['Continuity'],EntryTime=entry,ExitTime=exit_time,
                           IntervalTime=exit_time-entry if complete else None,BehindBest=None,
                           Complete=str(complete).lower(),Status='Complete' if complete else first['IntervalStatus']))
    valid=[r['IntervalTime'] for r in output if r['Complete']=='true']
    best=min(valid) if valid else None
    for r in output:
        if r['IntervalTime'] is not None:r['BehindBest']=r['IntervalTime']-best
        for key in ['EntryTime','ExitTime','IntervalTime','BehindBest']:
            r[key]='' if r[key] is None else f'{r[key]:.6f}'
    return sorted(output,key=lambda r:r['Pass'])


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file',nargs='?',help='Interval sample CSV; omit for stdin')
    p.add_argument('--time',default='Time',help='Sample time column in seconds')
    p.add_argument('-o','--output',type=Path,help='Default: stdout')
    args=p.parse_args()
    if args.file and args.output and Path(args.file).resolve()==args.output.resolve():p.error('Output must differ from input.')
    source=open(args.file,newline='',encoding='utf-8-sig') if args.file else sys.stdin
    try:
        reader=csv.DictReader(source)
        if not (REQUIRED|{args.time}).issubset(reader.fieldnames or []):raise ValueError('Expected interval.py sample CSV including boundary brackets.')
        if len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('Duplicate column names.')
        result=summarize(reader,args.time)
    finally:
        if args.file:source.close()
    if not args.output and hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(newline='')
    target=args.output.open('w',newline='',encoding='utf-8') if args.output else sys.stdout
    try:
        writer=csv.DictWriter(target,fieldnames=FIELDS);writer.writeheader();writer.writerows(result)
    finally:
        if args.output:target.close()

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,csv.Error) as exc:
        print(f'timing.py: error: {exc}',file=sys.stderr);sys.exit(2)

