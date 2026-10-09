"""Track outline and actual recorded GPS position, driven by Dashboard playback."""
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import track
from pathlib import Path
from interesting_points import InterestingPoints, identity, POINT_COLORS


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
    def __init__(self,parent,path,is_paused=None):
        self.is_paused=is_paused or (lambda:False)
        self.points_model=InterestingPoints(track.load_track(path))
        self.selected=None; self.point_drag=None; self.add_pending=False
        self.geometry=self.points_model.geometry
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
        self.show_points=tk.BooleanVar(value=True); self.edit_points=tk.BooleanVar(value=False)
        point_controls=ttk.Frame(self.window); point_controls.pack(fill='x',padx=8,pady=3)
        ttk.Button(point_controls,text='Load points',command=self.load_points).pack(side='left')
        ttk.Checkbutton(point_controls,text='Show points',variable=self.show_points,command=self.draw).pack(side='left')
        ttk.Checkbutton(point_controls,text='Edit points (paused)',variable=self.edit_points,command=self.toggle_edit).pack(side='left')
        edit_controls=ttk.Frame(self.window); edit_controls.pack(fill='x',padx=8,pady=3)
        for label,callback in [('Add point',self.arm_add),('Place at Steve',self.place_at_steve),('Delete',self.delete_point),('Save points',self.save_points),('Cancel',self.cancel_points)]:
            ttk.Button(edit_controls,text=label,command=callback).pack(side='left',padx=2)
        properties=ttk.Frame(self.window); properties.pack(fill='x',padx=8,pady=3)
        self.point_label=tk.StringVar(); self.point_type=tk.StringVar(value='apex')
        ttk.Label(properties,text='Name').pack(side='left')
        ttk.Entry(properties,textvariable=self.point_label,width=22).pack(side='left',padx=3)
        ttk.Combobox(properties,textvariable=self.point_type,values=['entry','apex','exit','marker'],state='readonly',width=8).pack(side='left')
        ttk.Button(properties,text='Apply name/type',command=self.apply_point).pack(side='left',padx=3)
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
        self.window.protocol('WM_DELETE_WINDOW',self.close)

    def can_edit(self):
        try: paused=self.is_paused() is True
        except (OSError,ConnectionError): paused=False
        if not self.edit_points.get() or not paused:
            self.status.set('Pause the video and enable Edit points to change points.')
            return False
        return True

    def toggle_edit(self):
        if self.edit_points.get():
            try: identity(self.geometry)
            except ValueError as exc:
                self.edit_points.set(False); self.status.set(str(exc)); return
        if self.edit_points.get() and not self.can_edit(): self.edit_points.set(False)
        self.add_pending=False
        if self.edit_points.get():
            self.show_points.set(True); self.status.set('Drag a point to move it. Add point, then click the map to create one.')
        self.draw()

    def choose_point(self,marker):
        self.selected=marker
        self.point_label.set(marker['label'] if marker else '')
        self.point_type.set(marker['type'] if marker else 'apex')

    def load_points(self):
        if self.points_model.dirty:
            messagebox.showinfo('Unsaved points','Save or Cancel your changes before loading another file.',parent=self.window); return
        path=filedialog.askopenfilename(parent=self.window,title='Load interesting points',filetypes=[('Points JSON','*.json')])
        if not path: return
        try: self.points_model.load(Path(path))
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('Cannot load points',str(exc),parent=self.window); return
        self.choose_point(None); self.show_points.set(True); self.draw()
        self.status.set(f'Loaded {len(self.points_model.markers)} points from {Path(path).name}.')

    def arm_add(self):
        if self.can_edit(): self.add_pending=True; self.status.set('Click the map to add a point.')

    def place_at_steve(self):
        if not self.can_edit(): return
        if self.position is None: self.status.set('Steve has no valid GPS position at this time.'); return
        if self.selected is None: self.choose_point(self.points_model.add(self.position))
        else: self.points_model.move(self.selected,self.position)
        self.draw(); self.status.set('Point placed at Steve’s current GPS sample. Save points to keep it.')

    def delete_point(self):
        if not self.can_edit() or self.selected is None: return
        self.points_model.markers.remove(self.selected); self.choose_point(None); self.draw()

    def apply_point(self):
        if not self.can_edit() or self.selected is None: return
        self.selected.update(label=self.point_label.get().strip() or self.point_type.get(),type=self.point_type.get())
        self.draw()

    def save_points(self):
        path=self.points_model.path
        if path is None:
            filename=filedialog.asksaveasfilename(parent=self.window,title='Save interesting points',defaultextension='.json',initialfile='track-points.json',filetypes=[('Points JSON','*.json')])
            if not filename: return
            path=Path(filename)
        try: self.points_model.save(path)
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('Cannot save points',str(exc),parent=self.window); return
        self.status.set(f'Points saved to {path}.')

    def cancel_points(self):
        self.points_model.cancel(); self.choose_point(None); self.add_pending=False; self.draw()
        self.status.set('Unsaved point changes discarded.')

    def close(self):
        if self.points_model.dirty:
            answer=messagebox.askyesnocancel('Unsaved points','Save your point changes before closing?',parent=self.window)
            if answer is None: return
            if answer:
                self.save_points()
                if self.points_model.dirty: return
        self.window.destroy()

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
        if self.edit_points.get():
            if not self.can_edit(): return
            if self.add_pending:
                point=self.viewport.world(event.x,event.y,self.canvas.winfo_width(),self.canvas.winfo_height())
                self.choose_point(self.points_model.add(point)); self.add_pending=False; self.draw(); return
            hits=[]
            for marker in self.points_model.markers:
                x,y=self.transform((marker['x_m'],marker['y_m']))
                distance=math.hypot(x-event.x,y-event.y)
                if distance <= 14: hits.append((distance,marker))
            if hits:
                self.choose_point(min(hits,key=lambda item:item[0])[1]); self.point_drag=self.selected; self.draw(); return
            self.choose_point(None); self.draw()
        self.drag_origin=(event.x,event.y); self.canvas.configure(cursor='fleur')

    def pan(self,event):
        if self.point_drag is not None:
            if self.can_edit():
                self.points_model.move(self.point_drag,self.viewport.world(event.x,event.y,self.canvas.winfo_width(),self.canvas.winfo_height()))
                self.draw()
            return
        if self.drag_origin is None: return
        x,y=self.drag_origin; self.viewport.pan(event.x-x,event.y-y)
        self.drag_origin=(event.x,event.y); self.initial_fit=False; self.draw()

    def end_pan(self,event):
        self.point_drag=None; self.drag_origin=None; self.canvas.configure(cursor='')

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
        if self.show_points.get():
            for marker in self.points_model.markers:
                px,py=self.transform((marker['x_m'],marker['y_m']))
                color=POINT_COLORS[marker['type']]
                self.canvas.create_oval(px-7,py-7,px+7,py+7,fill=color,outline='black' if marker is self.selected else 'white',width=2)
                self.canvas.create_text(px+11,py-10,text=marker['label'],anchor='w',fill=color)
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
        if self.edit_points.get(): return
        self.status.set(f'Recording {recording_time:.3f} s • GPS sample {sample_time:.3f} s' if self.position is not None else 'GPS position unavailable at this sample.')

    def unavailable(self,message='Waiting for video playback…'):
        self.position=None; self.place_dot(); self.status.set(message)
