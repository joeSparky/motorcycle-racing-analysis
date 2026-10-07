#!/usr/bin/env python3
"""Select visits to a track interval from enriched CSV. No timing calculations.

python track.py --track track.json < clean.csv | python interval.py --start 2437 --end 4215 --divisions 10000

All samples in a visit are emitted, plus boundary-bracketing samples.
IntervalContext=true identifies samples outside the requested interval retained
for interpolation. Filter these out for ordinary plots/calculations, but keep
these records for a downstream timing tool. Boundary flags mark before/after
samples, even if an entire small interval falls between two input samples.
Pass counts include partial visits, in chronological order. Complete visits
require forward start AND end crossings without continuity interruptions.
The tool buffers one visit to annotate completeness on every emitted row.
"""
import argparse
import csv
import math
from pathlib import Path
import sys

ADDED=['IntervalPass','IntervalStart','IntervalEnd','IntervalDivisions','IntervalContext',
       'IntervalStartBracket','IntervalEndBracket','IntervalComplete','IntervalStatus']


def number(row,key):
    try:v=float(row[key])
    except (KeyError,ValueError,TypeError):raise ValueError(f'{key} must contain finite numbers.')
    if not math.isfinite(v):raise ValueError(f'{key} must contain finite numbers.')
    return v


def visits(rows,start,end,divisions,max_gap=1.0,time_column='Time'):
    length=(end-start)%divisions
    if length==0:length=divisions
    start_gate=start%divisions;end_gate=end%divisions
    active=None;previous=None;previous_time=None;count=0
    def inside(p):return (p-start_gate)%divisions < length
    def begin(entered=False):
        nonlocal active,count
        count+=1;active={'pass':count,'entered':entered,'samples':{}}
    def add(sample,start_flag='',end_flag=''):
        if active is None:return
        seq,row,p,t=sample
        item=active['samples'].setdefault(seq,{'row':row,'p':p,'start':'','end':''})
        if start_flag:item['start']=start_flag
        if end_flag:item['end']=end_flag
    def finish(exited=False,status='Partial'):
        nonlocal active
        if active is None:return []
        complete=active['entered'] and exited
        output=[]
        for item in active['samples'].values():
            row=dict(item['row']);row.update(IntervalPass=active['pass'],IntervalStart=start,IntervalEnd=end,
                IntervalDivisions=divisions,IntervalContext=str(not inside(item['p'])).lower(),
                IntervalStartBracket=item['start'],IntervalEndBracket=item['end'],
                IntervalComplete=str(complete).lower(),IntervalStatus='Complete' if complete else status)
            output.append(row)
        active=None;return output
    for seq,row in enumerate(rows):
        t=number(row,time_column)
        if previous_time is not None and t<=previous_time:raise ValueError('Time must strictly increase.')
        gap=previous_time is not None and t-previous_time>max_gap
        previous_time=t
        if row['OffTrack'].strip().lower() not in {'true','false'}:raise ValueError('OffTrack must be true or false.')
        if row['OffTrack'].strip().lower()=='true':
            yield from finish(status='Partial: off-track or invalid GPS');previous=None;continue
        p=number(row,'TrackPosition')
        if not 0<=p<=divisions:raise ValueError('TrackPosition is outside the position scale.')
        p=p%divisions
        current=(seq,row,p,t)
        interrupted=None
        if previous is not None:
            old_seq,old_row,old_p,old_t=previous
            delta=(p-old_p+divisions/2)%divisions-divisions/2
            if row['Continuity']!=old_row['Continuity']:interrupted='continuity break'
            elif gap:interrupted='time gap'
            elif abs(delta)>divisions*.1:interrupted='position jump'
        if previous is None or interrupted:
            if interrupted:yield from finish(status='Partial: '+interrupted)
            if inside(p):begin();add(current)
            previous=current;continue
        crossings=[]
        if delta>0:
            for kind,gate in [('start',start_gate),('end',end_gate)]:
                for shift in (0,divisions):
                    b=gate+shift
                    if old_p<b<=old_p+delta:crossings.append((b,kind))
            # At a full-lap boundary, finish the old visit before starting another.
            crossings.sort(key=lambda x:(x[0],x[1]=='start'))
            for _,kind in crossings:
                if kind=='start':
                    yield from finish(status='Partial: repeated start')
                    begin(True);add(previous,start_flag='before');add(current,start_flag='after')
                else:
                    if active is None:begin()
                    add(previous,end_flag='before');add(current,end_flag='after')
                    yield from finish(True,status='Partial: no start crossing')
        elif delta<0 and inside(p)!=inside(old_p):
            yield from finish(status='Partial: reverse boundary crossing')
            if inside(p):begin();add(current)
        if active is not None and inside(p):add(current)
        previous=current
    yield from finish(status='Partial: recording ended')


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file',nargs='?',help='Enriched CSV; omit for stdin')
    p.add_argument('--start',required=True,type=int)
    p.add_argument('--end',required=True,type=int)
    p.add_argument('--divisions',required=True,type=int,help='Position scale from prepared track (Nelson: 10000)')
    p.add_argument('--max-gap',type=float,default=1.0)
    p.add_argument('--time',default='Time')
    p.add_argument('-o','--output',type=Path,help='Default: stdout')
    args=p.parse_args()
    if args.divisions<=0 or not 0<=args.start<=args.divisions or not 0<=args.end<=args.divisions or args.start==args.end or (args.start==args.divisions and args.end==0):p.error('Invalid interval or position scale.')
    if not math.isfinite(args.max_gap) or args.max_gap<=0:p.error('--max-gap must be positive.')
    if args.file and args.output and Path(args.file).resolve()==args.output.resolve():p.error('Output must differ from input.')
    source=open(args.file,newline='',encoding='utf-8-sig') if args.file else sys.stdin
    target=None
    try:
        reader=csv.DictReader(source)
        header=reader.fieldnames or []
        if not {args.time,'TrackPosition','OffTrack','Continuity'}.issubset(header):raise ValueError('Input must contain Time, TrackPosition, OffTrack and Continuity from track.py.')
        if len(header)!=len(set(header)) or set(header)&set(ADDED):raise ValueError('Duplicate or existing interval columns.')
        if not args.output and hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(newline='')
        target=args.output.open('w',newline='',encoding='utf-8') if args.output else sys.stdout
        writer=csv.DictWriter(target,fieldnames=header+ADDED);writer.writeheader()
        for row in visits(reader,args.start,args.end,args.divisions,args.max_gap,args.time):writer.writerow(row)
    finally:
        if args.file:source.close()
        if target is not None and args.output:target.close()

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,csv.Error) as exc:
        print(f'interval.py: error: {exc}',file=sys.stderr);sys.exit(2)

