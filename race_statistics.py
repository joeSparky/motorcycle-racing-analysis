"""Sample statistics and interval selection, independent of the user interface."""
import csv
import io
import math
from pathlib import Path
import statistics
import numpy as np
from aimcsv import extract
from expressions import ExpressionEvaluator


class Session:
    def __init__(self, filename):
        self.filename = Path(filename)
        output = io.StringIO()
        with self.filename.open(encoding='utf-8-sig', newline='') as source:
            extract(source, output)
        reader = csv.DictReader(io.StringIO(output.getvalue()))
        self.fields = reader.fieldnames
        self.rows = list(reader)
        self.times = [float(row['Time']) for row in self.rows]
        if not self.rows or any(b <= a for a, b in zip(self.times, self.times[1:])):
            raise ValueError('The recording must have samples with strictly increasing times.')
        output = io.StringIO()
        with self.filename.open(encoding='utf-8-sig', newline='') as source:
            extract(source, output, 'metadata')
        self.metadata = list(csv.reader(io.StringIO(output.getvalue())))
        markers = next((r[1:] for r in self.metadata if r and r[0] == 'Beacon Markers'), [])
        markers = [float(v) for v in markers if v.strip()]
        if any(not math.isfinite(v) for v in markers) or any(b <= a for a,b in zip(markers, markers[1:])):
            raise ValueError('Beacon markers must be finite and increase in time.')
        self.laps = [(a,b) for a,b in zip(markers, markers[1:]) if self.times[0] <= a < b <= self.times[-1]]
        self.geometry = None
        self.evaluator = ExpressionEvaluator(self.fields)

    def load_track(self, filename):
        import track
        geometry = track.load_track(Path(filename))
        rows = [dict(row) for row in self.rows]
        track.enrich(rows, geometry)
        self.rows = rows
        self.geometry = geometry
        self.evaluator = ExpressionEvaluator(list(rows[0]))

    def select(self, mode, start=None, end=None, rpm=0, lap=1, position_start=0, position_end=None):
        if mode not in ('Entire recording','Engine running','Race running','Lap','Segment of lap','Time interval'):
            raise ValueError('Unknown evaluation interval.')
        if mode in ('Time interval', 'Race running'):
            if start is None or end is None or not all(math.isfinite(v) for v in (start,end)) or not self.times[0] <= start < end <= self.times[-1]:
                raise ValueError('Start and end must lie within the recording, with start before end.')
        if mode in ('Lap', 'Segment of lap'):
            if not 1 <= lap <= len(self.laps):
                raise ValueError('Select an available beacon-to-beacon lap.')
            start, end = self.laps[lap-1]
        if mode == 'Engine running' and (not math.isfinite(rpm) or rpm < 0):
            raise ValueError('RPM threshold must be finite and nonnegative.')
        if mode == 'Segment of lap':
            if self.geometry is None:
                raise ValueError('Select a prepared track project in the launcher for segment analysis.')
            divisions = self.geometry['config']['divisions']
            if position_end is None or not 0 <= position_start < divisions or not 0 <= position_end <= divisions or position_start == position_end:
                raise ValueError(f'Position range must use 0 to {divisions}; start and end must differ.')
        mask = []
        for t,row in zip(self.times,self.rows):
            selected = True
            if mode in ('Time interval','Race running','Lap','Segment of lap'):
                selected = start <= t <= end if mode in ('Time interval','Race running') else start <= t < end
            if mode == 'Engine running':
                try: value = float(row['RPM']); selected = math.isfinite(value) and value > rpm
                except (KeyError,TypeError,ValueError): selected = False
            if mode == 'Segment of lap' and selected:
                try:
                    p = float(row['TrackPosition']) % divisions
                    length = (position_end-position_start) % divisions or divisions
                    selected = row['OffTrack'] == 'false' and (p-position_start) % divisions < length
                except (KeyError,ValueError,TypeError): selected = False
            mask.append(selected)
        if mode == 'Engine running' and 'RPM' not in self.fields:
            raise ValueError('This recording has no RPM channel.')
        return mask

    def calculate(self, expression, mask, bin_width=0):
        if len(mask) != len(self.rows):
            raise ValueError('Selection length differs from recording.')
        if not math.isfinite(bin_width) or bin_width < 0:
            raise ValueError('Histogram bin width must be zero (automatic) or a positive finite number.')
        self.evaluator.compile(expression)
        values = [self.evaluator.evaluate(expression,row) if chosen else None for row,chosen in zip(self.rows,mask)]
        valid = [v for v in values if v is not None]
        if not valid:
            raise ValueError('No valid expression results in the selected interval.')
        if bin_width:
            first = math.floor(min(valid)/bin_width)
            last = math.floor(max(valid)/bin_width) + 1
            if last-first > 1000:
                raise ValueError('Histogram would exceed 1000 bins. Increase the bin width or use 0 for automatic bins.')
            edges = np.arange(first,last+1,dtype=float)*bin_width
        else:
            edges = np.histogram_bin_edges(valid,bins=min(100,max(1,math.ceil(math.sqrt(len(valid))))))
        if not np.isfinite(edges).all() or not (np.diff(edges)>0).all():
            raise ValueError('Histogram bin width is too small for these values.')
        counts, edges = np.histogram(valid,bins=edges)
        # Trapezoids only between adjacent valid selected samples. Never span gaps.
        area = duration = 0.0
        for i in range(1,len(values)):
            if values[i-1] is not None and values[i] is not None:
                dt = self.times[i]-self.times[i-1]
                if dt <= 1.0:
                    area += dt*(values[i-1]/2 + values[i]/2); duration += dt
        minimum, maximum = min(valid), max(valid)
        return dict(mean=statistics.mean(valid), median=statistics.median(valid), minimum=minimum, maximum=maximum,
                    minimum_time=self.times[values.index(minimum)], maximum_time=self.times[values.index(maximum)],
                    histogram_counts=counts.tolist(), histogram_edges=edges.tolist(), bin_width=bin_width, valid=len(valid), omitted=sum(mask)-len(valid),
                    selected=sum(mask), weighted_mean=area/duration if duration else None, weighted_duration=duration,
                    values=values)
