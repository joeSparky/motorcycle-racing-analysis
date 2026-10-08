"""Track outline and actual recorded GPS position, driven by Dashboard playback."""
import math
import tkinter as tk
from tkinter import ttk
import numpy as np
import track


def recorded_position(row, geometry):
    try:
        lat,lon=float(row['GPS Latitude']),float(row['GPS Longitude'])
    except (KeyError,TypeError,ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or (lat==0 and lon==0):
        return None
    point=(np.array([lon,lat])-geometry['origin'])*geometry['scale']
    return float(point[0]),float(point[1])


def segment_markers(geometry):
    """Number saved segments in start-position order, as in Statistics."""
    sections=sorted(geometry['config'].get('sections',[]),key=lambda s:s['start'])
    divisions=geometry['config']['divisions']
    markers=[]
    for number,section in enumerate(sections,1):
        position=float(section['start'])
        if not math.isfinite(position) or not 0 <= position < divisions:
            raise ValueError('Segment start is outside the track position scale.')
        index=max(0,int(np.searchsorted(geometry['positions'],position,side='right'))-1)
        fraction=np.clip((position-geometry['positions'][index])/geometry['spans'][index],0,1)
        point=geometry['starts'][index]+fraction*geometry['vectors'][index]
        markers.append((number,position,point))
    return markers


class TrackView:
    def __init__(self,parent,path):
        self.geometry=track.load_track(path)
        self.points=(self.geometry['points']-self.geometry['origin'])*self.geometry['scale']
        self.segment_points=segment_markers(self.geometry)
        self.window=tk.Toplevel(parent)
        self.window.title('Track Position — '+str(self.geometry['config'].get('track',path.stem)))
        self.window.geometry('620x620'); self.window.minsize(320,320)
        self.canvas=tk.Canvas(self.window,background='white',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Start the video to show the recorded position.')
        ttk.Label(self.window,textvariable=self.status,wraplength=600).pack(fill='x',padx=12,pady=8)
        self.position=None; self.dot=None
        self.canvas.bind('<Configure>',lambda e:self.draw())

    def exists(self): return bool(self.window.winfo_exists())

    def draw(self):
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        low=self.points.min(axis=0)-30; high=self.points.max(axis=0)+30
        scale=min(max(1,width-50)/(high[0]-low[0]),max(1,height-50)/(high[1]-low[1]))
        middle=(low+high)/2
        self.transform=lambda p:(width/2+(p[0]-middle[0])*scale,height/2-(p[1]-middle[1])*scale)
        self.canvas.delete('all')
        coords=[v for point in self.points for v in self.transform(point)]
        self.canvas.create_line(*coords,fill='#64748b',width=3)
        x,y=self.transform(self.points[0])
        self.canvas.create_rectangle(x-4,y-4,x+4,y+4,fill='#111827',outline='')
        start_label='Start / finish'
        if self.segment_points and self.segment_points[0][1] == 0:
            start_label+=' • 0'
        self.canvas.create_text(x+8,y-12,text=start_label,anchor='w',fill='#475569')
        for number,position,point in self.segment_points:
            if position == 0: continue
            sx,sy=self.transform(point)
            self.canvas.create_rectangle(sx-4,sy-4,sx+4,sy+4,fill='#2563eb',outline='white')
            dx=10 if sx < width/2 else -10
            label=self.canvas.create_text(sx+dx,sy-12,text=f'{position:g}',anchor='w' if dx > 0 else 'e',fill='#1d4ed8')
            bounds=self.canvas.bbox(label)
            background=self.canvas.create_rectangle(bounds,fill='white',outline='')
            self.canvas.tag_lower(background,label)
        self.canvas.create_text(25,20,text='N ↑',anchor='w',fill='#475569')
        self.dot=self.canvas.create_oval(0,0,0,0,fill='#dc2626',outline='white',width=2,state='hidden')
        self.place_dot()

    def place_dot(self):
        if self.dot is None: return
        if self.position is None:
            self.canvas.itemconfigure(self.dot,state='hidden'); return
        x,y=self.transform(self.position)
        self.canvas.coords(self.dot,x-6,y-6,x+6,y+6)
        self.canvas.itemconfigure(self.dot,state='normal')

    def update(self,recording_time,sample_time,row):
        if abs(recording_time-sample_time) > .5:
            self.unavailable('No nearby GPS sample at this video time.'); return
        self.position=recorded_position(row,self.geometry)
        self.place_dot()
        self.status.set(f'Recording {recording_time:.3f} s • GPS sample {sample_time:.3f} s' if self.position is not None else 'GPS position unavailable at this sample.')

    def unavailable(self,message='Waiting for video playback…'):
        self.position=None; self.place_dot(); self.status.set(message)
