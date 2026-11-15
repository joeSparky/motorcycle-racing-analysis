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
    def __init__(self,root,session,link=None):
        self.root=root; self.session=session
        self.link=link; self.result=None; self.cursors=[]; self.video_time=None
        self.results=[]; self.evaluated_items=[]; self.graph_items=[]; self.active_graph=0
        root.title('Race Statistics — '+session.filename.name); root.geometry('1100x830'); root.minsize(950,700)
        frame=ttk.Frame(root,padding=12); frame.pack(fill='both',expand=True)
        self.editor=ExpressionEditor(frame,session.evaluator); self.editor.pack(fill='x')
        self.graph_items=[dict(self.editor.get()) for _ in range(3)]
        graph_controls=ttk.Frame(frame); graph_controls.pack(fill='x',pady=(6,0))
        ttk.Label(graph_controls,text='Graphs shown').pack(side='left')
        self.graph_count=tk.StringVar(value='1')
        count=ttk.Combobox(graph_controls,textvariable=self.graph_count,values=['1','2','3'],state='readonly',width=3)
        count.pack(side='left',padx=6)
        count.bind('<<ComboboxSelected>>',lambda e:self.change_graph_count())
        ttk.Label(graph_controls,text='Edit graph / show statistics').pack(side='left',padx=6)
        self.graph_choice=ttk.Combobox(graph_controls,values=['Graph 1'],state='readonly',width=12)
        self.graph_choice.current(0); self.graph_choice.pack(side='left')
        self.graph_choice.bind('<<ComboboxSelected>>',lambda e:self.choose_graph())
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
        self.hint=tk.StringVar(); ttk.Label(box,textvariable=self.hint).grid(row=2,column=0,columnspan=5,sticky='w')
        self.summary=tk.StringVar(value='Choose an expression and interval, then click Evaluate.')
        ttk.Label(frame,textvariable=self.summary,font=('TkDefaultFont',11),wraplength=1050).pack(fill='x',pady=8)
        self.figure=Figure(figsize=(10,4),dpi=100)
        self.plot_axes=[self.figure.add_subplot(111)]
        self.axes=self.plot_axes[0]
        self.canvas=FigureCanvasTkAgg(self.figure,master=frame); self.canvas.get_tk_widget().pack(fill='both',expand=True)
        self.toolbar=NavigationToolbar2Tk(self.canvas,frame)
        navigation=ttk.Frame(frame); navigation.pack(fill='x')
        self.link_status=tk.StringVar(value='Open Dashboard and start its video to link playback.' if link else 'Video linking is available when opened from the launcher.')
        ttk.Label(navigation,textvariable=self.link_status).pack(side='left')
        for label,key in [('Go to Min','minimum_time'),('Go to Max','maximum_time')]:
            ttk.Button(navigation,text=label,command=lambda k=key:self.go_extreme(k)).pack(side='right',padx=5)
        self.canvas.mpl_connect('button_press_event',self.graph_click)
        root.protocol('WM_DELETE_WINDOW',self.close)
        if link: root.after(200,self.follow_video)
        self.change_mode()

    def capture_graph(self):
        self.graph_items[self.active_graph]=self.editor.get()

    def choose_graph(self):
        target=self.graph_choice.current()
        try: self.capture_graph()
        except ValueError as exc:
            self.graph_choice.current(self.active_graph)
            messagebox.showerror('Cannot change graph',str(exc),parent=self.root); return
        self.active_graph=target
        self.editor.load(self.graph_items[target]); self.editor.name.set(self.graph_items[target]['label'])
        self.result=self.results[target] if target < len(self.results) else None
        if self.result: self.show_summary(self.evaluated_items[target],self.result)
        else: self.summary.set('Click Evaluate to update all displayed graphs.')

    def change_graph_count(self):
        count=int(self.graph_count.get())
        self.graph_choice.configure(values=[f'Graph {i+1}' for i in range(count)])
        if self.active_graph >= count:
            self.graph_choice.current(0); self.choose_graph()
            if self.active_graph >= count:
                self.graph_count.set(str(self.active_graph+1))
                self.graph_choice.configure(values=[f'Graph {i+1}' for i in range(self.active_graph+1)])
                return
        self.evaluate()

    def show_summary(self,item,result):
        fmt=lambda v: f'{v:,.{item["decimals"]}f}' if v is not None else 'unavailable'
        self.summary.set(f'Graph {self.active_graph+1} — Mean: {fmt(result["mean"])}   Median: {fmt(result["median"])}   Min: {fmt(result["minimum"])} at {result["minimum_time"]:.3f} s   Max: {fmt(result["maximum"])} at {result["maximum_time"]:.3f} s {item["units"]}\n'
            f'Valid: {result["valid"]:,}   Omitted: {result["omitted"]:,}   Selected: {result["selected"]:,}   '
            f'Time-weighted mean: {fmt(result["weighted_mean"])} (over {result["weighted_duration"]:.3f} s; trapezoids, gaps >1 s excluded)')

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
            self.capture_graph(); mode=self.mode.get(); args={}
            if mode in ('Time interval','Race running'): args.update(start=float(self.start.get()),end=float(self.end.get()))
            if mode=='Engine running': args['rpm']=float(self.rpm.get())
            if mode in ('Lap','Segment of lap'): args['lap']=int(self.lap.get())
            if mode=='Segment of lap': args.update(position_start=int(self.a.get()),position_end=int(self.b.get()))
            mask=self.session.select(mode,**args)
            items=self.graph_items[:int(self.graph_count.get())]
            results=[self.session.calculate(item['expression'],mask) for item in items]
            if mode=='Race running':
                save_json(self.race_path,dict(race_start=args['start'],race_end=args['end'])); self.race_bounds=(args['start'],args['end'])
            self.figure.clear(); self.plot_axes=[]; self.cursors=[]
            selected_times=[t for t,chosen in zip(self.session.times,mask) if chosen]
            for index,(item,result) in enumerate(zip(items,results)):
                axes=self.figure.add_subplot(len(items),1,index+1,sharex=self.plot_axes[0] if index else None)
                self.plot_axes.append(axes)
                x=[]; y=[]
                for i,(t,v) in enumerate(zip(self.session.times,result['values'])):
                    if i and t-self.session.times[i-1]>1: x.append(math.nan); y.append(math.nan)
                    x.append(t); y.append(v if v is not None else math.nan)
                axes.plot(x,y,linewidth=1,marker='.',markersize=2,color=f'C{index}')
                if len(selected_times)>1: axes.set_xlim(selected_times[0],selected_times[-1])
                axes.set_ylabel(item['units'] or 'Value')
                axes.set_title(f'Graph {index+1}: '+item['expression']+' — '+mode)
                axes.grid(True,alpha=.25)
                if index==len(items)-1: axes.set_xlabel('Recording time (seconds)')
                else: axes.tick_params(labelbottom=False)
            self.axes=self.plot_axes[0]; self.evaluated_items=[dict(item) for item in items]; self.results=results; self.result=results[self.active_graph]
            self.show_summary(items[self.active_graph],self.result)
            self.toolbar.update(); self.figure.tight_layout(); self.canvas.draw()
        except (ValueError,OSError,KeyError) as exc:
            self.result=None; self.results=[]; self.cursors=[]
            self.summary.set('No current result — '+str(exc))
            for axes in self.plot_axes: axes.clear()
            self.toolbar.update(); self.canvas.draw()
            messagebox.showerror('Cannot evaluate',str(exc),parent=self.root)


    def close(self):
        if self.link: self.link.close()
        self.root.destroy()

    def follow_video(self):
        try:
            self.video_time=self.link.current()
            if self.video_time is not None:
                self.link_status.set(f'Video at recording {self.video_time:.3f} s — click graph to seek')
                if self.result:
                    if not self.cursors:
                        self.cursors=[axes.axvline(self.video_time,color='red',linewidth=1) for axes in self.plot_axes]
                    for axes,cursor in zip(self.plot_axes,self.cursors):
                        cursor.set_xdata([self.video_time,self.video_time])
                        low,high=axes.get_xlim(); cursor.set_visible(low <= self.video_time <= high)
                    self.canvas.draw_idle()
        except (OSError,ValueError,KeyError,ConnectionError):
            self.video_time=None; self.link.close()
            self.link_status.set('Open Dashboard and start its video to link playback.')
            for cursor in self.cursors: cursor.set_visible(False)
            self.canvas.draw_idle()
        self.root.after(200,self.follow_video)

    def seek(self,time):
        if not self.link:
            self.link_status.set('Open Statistics from the launcher to link video.'); return
        try:
            if not self.link.seek(time): raise ValueError('Video seek failed.')
        except (OSError,ValueError,KeyError,ConnectionError) as exc:
            self.link.close(); self.link_status.set('Cannot seek: '+str(exc))

    def graph_click(self,event):
        if event.button == 1 and event.inaxes in self.plot_axes and event.xdata is not None and not self.toolbar.mode:
            self.seek(float(event.xdata))

    def go_extreme(self,key):
        if self.result: self.seek(self.result[key])
        else: self.link_status.set('Evaluate an expression first.')


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--race',required=True); parser.add_argument('--track')
    parser.add_argument('--socket'); parser.add_argument('--sync-state')
    args=parser.parse_args(); root=tk.Tk(); root.withdraw()
    try:
        session=Session(args.race)
        if args.track: session.load_track(args.track)
        from video_link import VideoLink
        link=VideoLink(args.socket,args.sync_state) if args.socket and args.sync_state else None
        StatisticsScreen(root,session,link); root.deiconify(); root.mainloop()
    except (ValueError,OSError,KeyError) as exc:
        messagebox.showerror('Cannot open statistics',str(exc),parent=root); root.destroy(); raise SystemExit(2)


if __name__=='__main__': main()
