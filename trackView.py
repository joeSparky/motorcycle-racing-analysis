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


class MapViewport:
    """North-up map coordinates with equal distance scale on both axes."""
    def __init__(self):
        self.center = np.array([0., 0.])
        self.meters_per_pixel = 1.

    def fit(self, points, width, height):
        points = np.asarray(points, dtype=float)
        low, high = points.min(axis=0)-30, points.max(axis=0)+30
        self.center = (low+high)/2
        self.meters_per_pixel = max((high[0]-low[0])/max(1, width-50),
                                    (high[1]-low[1])/max(1, height-50))

    def screen(self, point, width, height):
        delta = (np.asarray(point)-self.center)/self.meters_per_pixel
        return width/2+delta[0], height/2-delta[1]

    def world(self, x, y, width, height):
        return self.center + np.array([x-width/2, height/2-y])*self.meters_per_pixel

    def zoom(self, factor, x, y, width, height):
        anchor = self.world(x, y, width, height)
        self.meters_per_pixel = min(1e7, max(.01, self.meters_per_pixel/factor))
        self.center += anchor-self.world(x, y, width, height)

    def pan(self, dx, dy):
        self.center += np.array([-dx, dy])*self.meters_per_pixel


class TrackView:
    def __init__(self,parent,path):
        self.geometry=track.load_track(path)
        self.points=(self.geometry['points']-self.geometry['origin'])*self.geometry['scale']
        self.segment_points=segment_markers(self.geometry)
        self.window=tk.Toplevel(parent)
        self.window.title('Track Position — '+str(self.geometry['config'].get('track',path.stem)))
        self.window.geometry('620x620'); self.window.minsize(320,320)
        controls=ttk.Frame(self.window); controls.pack(fill='x',padx=8,pady=6)
        ttk.Button(controls,text='Fit track',command=self.fit_track).pack(side='left',padx=3)
        self.fit_steve_button=ttk.Button(controls,text='Fit track + Steve',command=lambda:self.fit_track(True))
        self.fit_steve_button.pack(side='left',padx=3); self.fit_steve_button.state(['disabled'])
        self.viewport=MapViewport(); self.initial_fit=True; self.drag_origin=None
        self.canvas=tk.Canvas(self.window,background='white',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Start the video to show the recorded position.')
        ttk.Label(self.window,textvariable=self.status,wraplength=600).pack(fill='x',padx=12,pady=8)
        self.position=None; self.dot=None
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<MouseWheel>',self.zoom)
        self.canvas.bind('<Button-4>',lambda e:self.zoom(e,1))
        self.canvas.bind('<Button-5>',lambda e:self.zoom(e,-1))
        self.canvas.bind('<ButtonPress-1>',self.start_pan)
        self.canvas.bind('<B1-Motion>',self.pan)
        self.canvas.bind('<ButtonRelease-1>',self.end_pan)
        ttk.Label(controls,text='Wheel: zoom • Drag: pan').pack(side='left',padx=8)

    def exists(self): return bool(self.window.winfo_exists())

    def fit_track(self, include_steve=False):
        points=self.points
        if include_steve and self.position is not None:
            points=np.vstack([points,self.position])
        self.viewport.fit(points,self.canvas.winfo_width(),self.canvas.winfo_height())
        self.initial_fit=False; self.draw()

    def zoom(self,event,direction=None):
        if direction is None:
            if not event.delta: return
            direction=1 if event.delta > 0 else -1
        self.viewport.zoom(1.25 if direction > 0 else 1/1.25,event.x,event.y,
                           self.canvas.winfo_width(),self.canvas.winfo_height())
        self.initial_fit=False; self.draw()

    def start_pan(self,event):
        self.drag_origin=(event.x,event.y); self.canvas.configure(cursor='fleur')

    def pan(self,event):
        if self.drag_origin is None: return
        x,y=self.drag_origin; self.viewport.pan(event.x-x,event.y-y)
        self.drag_origin=(event.x,event.y); self.initial_fit=False; self.draw()

    def end_pan(self,event):
        self.drag_origin=None; self.canvas.configure(cursor='')

    def draw(self):
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        if self.initial_fit:
            self.viewport.fit(self.points,width,height)
            self.initial_fit=width <= 1 or height <= 1
        self.transform=lambda p:self.viewport.screen(p,width,height)
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
        bar_pixels=80
        distance=bar_pixels*self.viewport.meters_per_pixel
        self.canvas.create_line(25,height-25,25+bar_pixels,height-25,fill='#475569',width=2)
        self.canvas.create_text(25,height-38,text=f'{distance:.3g} m',anchor='w',fill='#475569')
        self.dot=self.canvas.create_oval(0,0,0,0,fill='#dc2626',outline='white',width=2,state='hidden')
        self.place_dot()

    def place_dot(self):
        self.fit_steve_button.state(['disabled'] if self.position is None else ['!disabled'])
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
