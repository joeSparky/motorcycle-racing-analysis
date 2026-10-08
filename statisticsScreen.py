#!/usr/bin/env python3
"""Offline statistics screen for an original AIM recording."""
import argparse
import math
from pathlib import Path
import json
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from race_statistics import Session
from expression_editor import ExpressionEditor, save_json

MODES = ['Entire recording','Engine running','Race running','Lap','Segment of lap','Time interval']


class StatisticsScreen:
    def __init__(self,root,session):
        self.root=root; self.session=session
        root.title('Race Statistics — '+session.filename.name); root.geometry('1100x830'); root.minsize(950,700)
        frame=ttk.Frame(root,padding=12); frame.pack(fill='both',expand=True)
        self.editor=ExpressionEditor(frame,session.evaluator); self.editor.pack(fill='x')
        box=ttk.LabelFrame(frame,text='Evaluation interval',padding=8); box.pack(fill='x',pady=8)
        self.mode=tk.StringVar(value=MODES[0]); self.start=tk.StringVar(value=str(session.times[0])); self.end=tk.StringVar(value=str(session.times[-1]))
        self.rpm=tk.StringVar(value='0'); self.lap=tk.StringVar(value='1'); self.a=tk.StringVar(value='0')
        self.b=tk.StringVar(value=str(session.geometry['config']['divisions'] if session.geometry else 10000))
        self.race_path=session.filename.with_suffix('.statistics.json')
        try:
            saved=json.loads(self.race_path.read_text(encoding='utf-8')); self.race_bounds=(saved['race_start'],saved['race_end'])
        except FileNotFoundError: self.race_bounds=None
        selection=ttk.Combobox(box,textvariable=self.mode,values=MODES,state='readonly',width=22)
        selection.grid(row=0,column=0,padx=4); selection.bind('<<ComboboxSelected>>',lambda e:self.change_mode())
        self.inputs=[]
        for col,(label,var) in enumerate([('Start seconds',self.start),('End seconds',self.end),('RPM >',self.rpm),('Lap',self.lap)],1):
            sub=ttk.Frame(box); sub.grid(row=0,column=col,padx=5)
            ttk.Label(sub,text=label).pack(); entry=ttk.Entry(sub,textvariable=var,width=12); entry.pack(); self.inputs.append(entry)
        row=ttk.Frame(box); row.grid(row=1,column=0,columnspan=5,sticky='w',pady=7)
        self.positions=[]
        for label,var in [('Start position',self.a),('End position',self.b)]:
            ttk.Label(row,text=label).pack(side='left',padx=5); entry=ttk.Entry(row,textvariable=var,width=10); entry.pack(side='left'); self.positions.append(entry)
        self.segment=tk.StringVar()
        sections=session.geometry['config'].get('sections',[]) if session.geometry else []
        self.sections=sections
        self.segments=ttk.Combobox(row,textvariable=self.segment,values=[f'{i+1}: {s["start"]}–{s["end"]}' for i,s in enumerate(sections)],state='readonly',width=20)
        self.segments.pack(side='left',padx=8); self.segments.bind('<<ComboboxSelected>>',lambda e:self.choose_segment())
        ttk.Button(row,text='Evaluate',command=self.evaluate).pack(side='left',padx=8)
        ttk.Button(row,text='Done',command=root.destroy).pack(side='left')
        self.hint=tk.StringVar(); ttk.Label(box,textvariable=self.hint).grid(row=2,column=0,columnspan=5,sticky='w')
        self.summary=tk.StringVar(value='Choose an expression and interval, then click Evaluate.')
        ttk.Label(frame,textvariable=self.summary,font=('TkDefaultFont',11),wraplength=1050).pack(fill='x',pady=8)
        self.figure=Figure(figsize=(10,4),dpi=100); self.axes=self.figure.add_subplot()
        self.canvas=FigureCanvasTkAgg(self.figure,master=frame); self.canvas.get_tk_widget().pack(fill='both',expand=True)
        NavigationToolbar2Tk(self.canvas,frame)
        self.change_mode()

    def change_mode(self):
        mode=self.mode.get()
        for entry,enabled in zip(self.inputs,[mode in ('Time interval','Race running')]*2+[mode=='Engine running',mode in ('Lap','Segment of lap')]):
            entry.configure(state='normal' if enabled else 'disabled')
        for entry in self.positions: entry.configure(state='normal' if mode=='Segment of lap' else 'disabled')
        self.segments.configure(state='readonly' if mode=='Segment of lap' else 'disabled')
        if mode=='Race running' and self.race_bounds:
            self.start.set(str(self.race_bounds[0])); self.end.set(str(self.race_bounds[1]))
        hints={'Race running':'Enter the race start and finish in recording seconds. Evaluate saves these for this recording.',
               'Engine running':'Includes only records above the RPM threshold; engine-off gaps remain visible.',
               'Lap':f'{len(self.session.laps)} complete beacon-to-beacon laps. Warm-up laps may be included; these are not official race lap numbers.',
               'Segment of lap':'Uses beacon lap plus track positions. End before start selects a range crossing position zero; off-track samples are excluded.'}
        self.hint.set(hints.get(mode,f'Recording: {self.session.times[0]:.3f} to {self.session.times[-1]:.3f} seconds.'))

    def choose_segment(self):
        section=self.sections[self.segments.current()]; self.a.set(str(section['start'])); self.b.set(str(section['end']))

    def evaluate(self):
        try:
            item=self.editor.get(); mode=self.mode.get(); args={}
            if mode in ('Time interval','Race running'): args.update(start=float(self.start.get()),end=float(self.end.get()))
            if mode=='Engine running': args['rpm']=float(self.rpm.get())
            if mode in ('Lap','Segment of lap'): args['lap']=int(self.lap.get())
            if mode=='Segment of lap': args.update(position_start=int(self.a.get()),position_end=int(self.b.get()))
            mask=self.session.select(mode,**args); result=self.session.calculate(item['expression'],mask,item['bin_width'])
            if mode=='Race running':
                save_json(self.race_path,dict(race_start=args['start'],race_end=args['end'])); self.race_bounds=(args['start'],args['end'])
            fmt=lambda v: f'{v:,.{item["decimals"]}f}' if v is not None else 'unavailable'
            if result['mode_count']==1: mode_text='No repeated values / bins'
            else:
                def mode_label(v):
                    return f'[{fmt(v*item["bin_width"])}, {fmt((v+1)*item["bin_width"])})' if item['bin_width'] else fmt(v)
                mode_text=', '.join(mode_label(v) for v in result['modes'][:5])
                if len(result['modes'])>5: mode_text+=f' (+{len(result["modes"])-5} tied modes)'
                mode_text+=f' ({result["mode_count"]} samples each)'
            self.summary.set(f'Mean: {fmt(result["mean"])}   Median: {fmt(result["median"])}   Min: {fmt(result["minimum"])}   Max: {fmt(result["maximum"])} {item["units"]}\n'
                f'Mode: {mode_text}\nValid: {result["valid"]:,}   Omitted: {result["omitted"]:,}   Selected: {result["selected"]:,}   '
                f'Time-weighted mean: {fmt(result["weighted_mean"])} (over {result["weighted_duration"]:.3f} s; trapezoids, gaps >1 s excluded)')
            x=[]; y=[]
            for i,(t,v) in enumerate(zip(self.session.times,result['values'])):
                if i and t-self.session.times[i-1]>1: x.append(math.nan); y.append(math.nan)
                x.append(t); y.append(v if v is not None else math.nan)
            self.axes.clear(); self.axes.plot(x,y,linewidth=1,marker='.',markersize=2)
            selected_times=[t for t,chosen in zip(self.session.times,mask) if chosen]
            if len(selected_times)>1: self.axes.set_xlim(selected_times[0],selected_times[-1])
            self.axes.set_xlabel('Recording time (seconds)'); self.axes.set_ylabel(item['units'] or 'Value')
            self.axes.set_title(item['expression']+' — '+mode); self.axes.grid(True,alpha=.25)
            self.figure.tight_layout(); self.canvas.draw()
        except (ValueError,OSError,KeyError) as exc:
            self.summary.set('No current result — '+str(exc)); self.axes.clear(); self.canvas.draw()
            messagebox.showerror('Cannot evaluate',str(exc),parent=self.root)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--race',required=True); parser.add_argument('--track')
    args=parser.parse_args(); root=tk.Tk(); root.withdraw()
    try:
        session=Session(args.race)
        if args.track: session.load_track(args.track)
        StatisticsScreen(root,session); root.deiconify(); root.mainloop()
    except (ValueError,OSError,KeyError) as exc:
        messagebox.showerror('Cannot open statistics',str(exc),parent=root); root.destroy(); raise SystemExit(2)


if __name__=='__main__': main()
