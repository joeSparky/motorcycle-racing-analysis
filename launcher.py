"""File picker and launcher for Windows race analysis."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import uuid
from video_pieces import ordered_pieces, create_timeline

BASE = Path(__file__).resolve().parent

class Launcher:
    def __init__(self, root):
        self.root = root
        self.child = None
        self.log = None
        self.csv_children = {}
        self.csv_buttons = {}
        self.video_socket = r"\\.\pipe\race-statistics-" + uuid.uuid4().hex
        self.sync_state = BASE/("video-link-" + uuid.uuid4().hex + ".json")
        root.title("Steve's Race Analysis")
        root.geometry('950x610')
        root.minsize(760, 380)
        self.race = tk.StringVar()
        self.video = tk.StringVar()
        self.track = tk.StringVar()
        self.points = tk.StringVar()
        self.data_root = tk.StringVar(value=str(Path.home()/'racingData'))
        self.track_directory = tk.StringVar()
        self.status = tk.StringVar(value='Choose a race CSV and its helmet video.')
        try:
            saved = json.loads((BASE/'last-race.json').read_text(encoding='utf-8-sig'))
            self.race.set(saved.get('race', ''))
            self.video.set(saved.get('video', ''))
            self.track.set(saved.get('track', ''))
            self.points.set(saved.get('points', ''))
            self.data_root.set(saved.get('data_root',self.data_root.get()))
            self.track_directory.set(saved.get('track_directory',''))
        except (OSError, ValueError):
            pass
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text='Race Analysis', font=('Segoe UI', 20, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 18))
        for i, (label, var) in enumerate([('Race CSV', self.race), ('Helmet video', self.video)], 1):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='w', padx=(0,10), pady=6)
            ttk.Entry(frame, textvariable=var).grid(row=i, column=1, sticky='ew')
            ttk.Button(frame, text='Browse...', command=lambda v=var: self.choose(v)).grid(row=i, column=2, padx=(10,0))
        ttk.Button(frame, text='Select Video Pieces...', command=self.choose_pieces).grid(row=2, column=3, padx=(10,0))
        ttk.Label(frame, text='Track project').grid(row=3, column=0, sticky='w', padx=(0,10), pady=6)
        ttk.Entry(frame, textvariable=self.track).grid(row=3, column=1, sticky='ew')
        ttk.Button(frame, text='Browse...', command=lambda: self.choose(self.track)).grid(row=3, column=2, padx=(10,0))
        ttk.Label(frame,text='Interesting points').grid(row=4,column=0,sticky='w',padx=(0,10),pady=6)
        ttk.Entry(frame,textvariable=self.points).grid(row=4,column=1,sticky='ew')
        ttk.Button(frame,text='Browse...',command=lambda:self.choose(self.points)).grid(row=4,column=2,padx=(10,0))
        ttk.Button(frame,text='Import .ztracks...',command=self.import_track).grid(row=3,column=3,padx=(10,0))
        self.file_controls = [w for w in frame.winfo_children() if isinstance(w, (ttk.Entry, ttk.Button))]
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky='w', pady=20)
        self.buttons = []
        for label, script in [('Calibrate Video', 'videoCalibration.py'), ('Open Dashboard', 'dashboard.py')]:
            b = ttk.Button(buttons, text=label, command=lambda s=script:self.launch(s))
            b.pack(side='left', padx=(0,12))
            self.buttons.append(b)
        statistics_button = ttk.Button(buttons, text='Statistics', command=self.open_statistics)
        statistics_button.pack(side='left', padx=(0,12))
        self.csv_buttons['statisticsScreen.py'] = statistics_button
        editor_button = ttk.Button(buttons, text='Edit Segments', command=self.edit_segments)
        editor_button.pack(side='left', padx=(0,12))
        self.buttons.append(editor_button)
        metadata_button = ttk.Button(frame, text='Session Information', command=lambda:self.open_csv_screen('sessionInfo.py'))
        metadata_button.grid(row=6,column=0,columnspan=3,sticky='w',pady=(0,8))
        self.csv_buttons['sessionInfo.py'] = metadata_button
        ttk.Label(frame, text='New recording: calibrate first. Saved calibration: open the dashboard directly.', wraplength=690).grid(row=7, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, textvariable=self.status, wraplength=690).grid(row=8, column=0, columnspan=3, sticky='w', pady=(16,0))
        for widget in frame.winfo_children():
            info=widget.grid_info()
            if info and int(info['row'])>0:widget.grid_configure(row=int(info['row'])+2)
        folder_controls=[]
        for row,label,var,callback in [(1,'racingData folder',self.data_root,self.choose_data_root),(2,'Track data folder',self.track_directory,self.choose_track_directory)]:
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=6)
            entry=ttk.Entry(frame,textvariable=var,state='readonly');entry.grid(row=row,column=1,sticky='ew')
            button=ttk.Button(frame,text='Browse...',command=callback);button.grid(row=row,column=2,padx=(10,0))
            folder_controls.extend([entry,button])
        create=ttk.Button(frame,text='New track folder...',command=self.create_track_directory)
        create.grid(row=2,column=3,padx=(10,0));folder_controls.append(create)
        self.file_controls.extend(folder_controls)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def initial_directory(self):
        for value in (self.track_directory.get(),self.data_root.get()):
            if value and Path(value).is_dir():return value
        return str(Path.home())

    def choose_data_root(self):
        if self.running():return
        folder=filedialog.askdirectory(parent=self.root,title='Choose racingData folder',initialdir=self.initial_directory(),mustexist=False)
        if not folder:return
        try:
            Path(folder).mkdir(parents=True,exist_ok=True)
            self.data_root.set(folder);self.track_directory.set('');self.save()
        except OSError as exc:messagebox.showerror('Cannot create data folder',str(exc),parent=self.root)

    def set_track_directory(self,folder):
        self.track_directory.set(str(folder))
        for var in (self.race,self.video,self.track,self.points):var.set('')
        self.save();self.status.set('Track folder selected. Choose its race CSV, video, track project and points.')
        self.offer_track_import()

    def offer_track_import(self):
        folder=Path(self.track_directory.get())
        for path in folder.glob('*.json'):
            try:
                if json.loads(path.read_text(encoding='utf-8-sig')).get('format')=='track-editor-master-v1':return
            except (OSError,ValueError,AttributeError):pass
        archives=sorted(p for p in folder.iterdir() if p.suffix.lower()=='.ztracks' and p.is_file())
        if archives and messagebox.askyesno('Import track','No track project was found. Import a Race Studio .ztracks export now?',parent=self.root):
            self.import_track(archives[0] if len(archives)==1 else None)

    def import_track(self,source=None):
        if self.running():return
        if source is None:
            source=filedialog.askopenfilename(parent=self.root,title='Import Race Studio track export',initialdir=self.initial_directory(),filetypes=[('Race Studio tracks','*.ztracks')])
        if not source:return
        try:
            from track_import import members, project
            names=members(source)
            member=names[0]
            if len(names)>1:
                choice=simpledialog.askinteger('Select exported track','Choose track number:\n'+ '\n'.join(f'{i+1}. {n}' for i,n in enumerate(names)),minvalue=1,maxvalue=len(names),parent=self.root)
                if choice is None:return
                member=names[choice-1]
            name=simpledialog.askstring('Track name','Name for this track:',initialvalue=Path(self.track_directory.get() or source).stem,parent=self.root)
            if not name or not name.strip():return
            data=project(source,member,name.strip())
            output=filedialog.asksaveasfilename(parent=self.root,title='Save track project',initialdir=self.initial_directory(),initialfile=''.join(c if c not in '<>:"/\\|?*' and ord(c)>=32 else '-' for c in name.strip()).rstrip('. ')+'.json',defaultextension='.json',filetypes=[('Track project JSON','*.json')])
            if not output:return
            if Path(output).resolve()==Path(source).resolve():raise ValueError('Output must differ from the track export.')
            from expression_editor import save_json
            save_json(Path(output),data)
            self.track.set(output);self.save()
            self.status.set('Track project imported. Use Edit Segments to define segments.')
        except (OSError,ValueError,KeyError,RuntimeError) as exc:
            messagebox.showerror('Cannot import track',str(exc),parent=self.root)

    def choose_track_directory(self):
        if self.running():return
        folder=filedialog.askdirectory(parent=self.root,title='Choose track data folder',initialdir=self.initial_directory())
        if folder:self.set_track_directory(folder)

    def create_track_directory(self):
        if self.running():return
        name=simpledialog.askstring('New track folder','Track folder name (for example Barber):',parent=self.root)
        if name is None:return
        name=name.strip()
        if not name or name in ('.','..') or any(c in name for c in '<>:"/\\|?*') or name.endswith('.'):
            messagebox.showerror('Invalid folder name','Enter a single folder name without path separators or special characters.',parent=self.root);return
        try:
            folder=Path(self.data_root.get())/name
            folder.mkdir(parents=True,exist_ok=True);self.set_track_directory(folder)
        except OSError as exc:messagebox.showerror('Cannot create track folder',str(exc),parent=self.root)

    def choose(self, var):
        if self.running():
            return
        types = [('CSV files','*.csv'),('All files','*.*')] if var is self.race else [('Video or saved timeline','*.mp4 *.mov *.mkv *.avi *.m4v *.edl'),('All files','*.*')]
        if var is self.track:
            types = [('Track project JSON','*.json'),('All files','*.*')]
        if var is self.points:
            types = [('Interesting points JSON','*.json'),('All files','*.*')]
        path = filedialog.askopenfilename(parent=self.root, initialdir=self.initial_directory(), filetypes=types)
        if path:
            var.set(path)
            self.save()

    def choose_pieces(self):
        if self.running():
            messagebox.showinfo('Close analysis first', 'Close the open analysis windows before changing video pieces.', parent=self.root)
            return
        paths = filedialog.askopenfilenames(parent=self.root, title='Select all pieces of ONE continuous recording', initialdir=self.initial_directory(), filetypes=[('Video files','*.mp4 *.mov *.mkv *.avi *.m4v')])
        if not paths:
            return
        try:
            pieces = ordered_pieces(paths)
            if len(pieces) == 1:
                self.video.set(str(pieces[0]))
            else:
                names = '\n'.join(f'{i}. {p.name}' for i,p in enumerate(pieces,1))
                if not messagebox.askyesno('Confirm video order', f'Use these {len(pieces)} pieces in this order?\n\n{names}\n\nChoose only pieces from one continuous recording.', parent=self.root):
                    return
                self.video.set(str(create_timeline(pieces)))
            self.save()
            self.status.set(f'{len(pieces)} video pieces selected. Ready to calibrate the complete recording.')
        except (OSError, ValueError) as e:
            messagebox.showerror('Video pieces', str(e), parent=self.root)

    def save(self):
        (BASE/'last-race.json').write_text(json.dumps({'race':self.race.get(),'video':self.video.get(),'track':self.track.get(),'points':self.points.get(),'data_root':self.data_root.get(),'track_directory':self.track_directory.get()},indent=2),encoding='utf-8')

    def edit_segments(self):
        if self.child and self.child.poll() is None:
            return
        if not self.track.get().strip():
            self.choose(self.track)
            if not self.track.get().strip():
                return
        try:
            track = Path(self.track.get()).resolve()
            data = json.loads(track.read_text(encoding='utf-8-sig'))
            if data.get('format') != 'track-editor-master-v1' or len(data.get('nodes', [])) < 2:
                raise ValueError('Choose the prepared track-project JSON, not a points file or race CSV.')
            script = BASE/'sectionEditor.py'
            if not script.is_file():
                raise ValueError('sectionEditor.py is missing from the setup folder. Copy it from the update ZIP.')
            self.save()
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            self.log = open(BASE/'analysis-log.txt', 'w', encoding='utf-8')
            command=[sys.executable, str(script), '--track', str(track)]
            if self.points.get().strip(): command.extend(['--points',str(Path(self.points.get()).resolve())])
            self.child = subprocess.Popen(command,
                cwd=BASE, env=env, stdout=self.log, stderr=self.log)
            self.refresh_controls()
            self.status.set('Edit boundaries and save sections, then close the editor window.')
            self.root.after(300, self.poll)
        except Exception as exc:
            if self.log:
                self.log.close()
                self.log = None
            messagebox.showerror('Cannot open segment editor', str(exc), parent=self.root)

    def open_statistics(self):
        self.open_csv_screen('statisticsScreen.py')

    def open_csv_screen(self, script):
        if script in self.csv_children:
            return
        log = None
        try:
            race = Path(self.race.get()).resolve()
            if not race.is_file():
                raise ValueError('Choose an existing original AIM race CSV first.')
            command = [sys.executable, str(BASE/script), '--race', str(race)]
            if script == 'statisticsScreen.py':
                command.extend(['--socket',self.video_socket,'--sync-state',str(self.sync_state)])
            if script == 'statisticsScreen.py' and self.track.get().strip():
                command.extend(['--track', str(Path(self.track.get()).resolve())])
            self.save()
            env = os.environ.copy(); env['PYTHONIOENCODING'] = 'utf-8'
            path = BASE/(Path(script).stem + '-log.txt')
            log = open(path, 'w', encoding='utf-8')
            process = subprocess.Popen(command, cwd=BASE, env=env, stdout=log, stderr=log)
            self.csv_children[script] = (process, log, path)
            self.refresh_controls()
            self.root.after(300, lambda:self.poll_csv(script))
        except Exception as exc:
            if log: log.close()
            messagebox.showerror('Cannot open CSV screen', str(exc), parent=self.root)

    def poll_csv(self, script):
        process, log, path = self.csv_children[script]
        code = process.poll()
        if code is None:
            self.root.after(300, lambda:self.poll_csv(script))
            return
        log.close()
        del self.csv_children[script]
        self.refresh_controls()
        if code:
            detail = path.read_text(encoding='utf-8',errors='replace')
            messagebox.showerror('Analysis stopped', detail[-2500:] or f'See {path.name}.', parent=self.root)

    def running(self):
        return bool(self.csv_children) or (self.child is not None and self.child.poll() is None)

    def refresh_controls(self):
        video_active = self.child is not None and self.child.poll() is None
        for button in self.buttons:
            button.state(['disabled'] if video_active else ['!disabled'])
        for script, button in self.csv_buttons.items():
            button.state(['disabled'] if script in self.csv_children else ['!disabled'])
        for widget in self.file_controls:
            widget.state(['disabled'] if self.running() else ['!disabled'])
        if self.running():
            self.status.set('Analysis windows are open. Statistics and Dashboard can run together. Close all analysis windows to change files.')
        else:
            self.status.set('Ready. Choose calibration, dashboard, statistics, or session information.')

    def launch(self, script):
        if self.child and self.child.poll() is None:
            return
        try:
            race = Path(self.race.get()).resolve()
            video = Path(self.video.get()).resolve()
            if not race.is_file() or not video.is_file():
                raise ValueError('Choose an existing race CSV and video first.')
            settings = json.loads((BASE/'setup-settings.json').read_text(encoding='utf-8-sig'))
            if not Path(settings['mpv']).is_file():
                raise ValueError('mpv could not be found. Run Setup.cmd again.')
            if script == 'dashboard.py':
                calibration = race.with_suffix('.calibration')
                if not calibration.is_file():
                    raise ValueError('This race has no saved calibration. Click Calibrate Video first.')
                data = json.loads(calibration.read_text(encoding='utf-8-sig'))
                slope = float(data['slope']); offset = float(data['offset'])
                if not math.isfinite(slope) or slope <= 0 or not math.isfinite(offset):
                    raise ValueError('Calibration is invalid. Calibrate Video again with a later second point.')
                old_video = data.get('video')
                if old_video and os.path.normcase(str(Path(old_video).resolve())) != os.path.normcase(str(video)):
                    if not messagebox.askyesno('Different video', 'The calibration was saved for a different video. Use it with this video?', parent=self.root):
                        return
            self.save()
            env = os.environ.copy()
            env['MPV_EXE'] = settings['mpv']
            env['PYTHONIOENCODING'] = 'utf-8'
            pipe = self.video_socket if script == 'dashboard.py' else r'\\.\pipe\race-calibration-' + uuid.uuid4().hex
            self.log = open(BASE/'analysis-log.txt','w',encoding='utf-8')
            command = [sys.executable,str(BASE/script),'--race',str(race),'--video',str(video),'--socket',pipe]
            if script == 'dashboard.py':
                from expression_editor import save_json
                save_json(self.sync_state,dict(slope=slope,offset=offset,adjustment=0))
                command.extend(['--sync-state',str(self.sync_state)])
            if script == 'dashboard.py' and self.track.get().strip():
                command.extend(['--track', str(Path(self.track.get()).resolve())])
            if script == 'dashboard.py' and self.points.get().strip():
                command.extend(['--points',str(Path(self.points.get()).resolve())])
            self.child = subprocess.Popen(command,cwd=BASE,env=env,stdout=self.log,stderr=self.log)
            self.refresh_controls()
            self.root.after(300,self.poll)
        except Exception as e:
            if self.log: self.log.close(); self.log=None
            messagebox.showerror('Cannot start analysis', str(e),parent=self.root)

    def poll(self):
        code = self.child.poll()
        if code is None:
            self.root.after(300,self.poll)
            return
        self.log.close(); self.log=None; self.child=None
        self.refresh_controls()
        if code:
            detail=(BASE/'analysis-log.txt').read_text(encoding='utf-8',errors='replace')
            messagebox.showerror('Analysis stopped', detail[-2500:] or 'See analysis-log.txt.',parent=self.root)

    def close(self):
        if self.running():
            messagebox.showinfo('Close analysis first','Close the open analysis windows first, then close this launcher.',parent=self.root)
            return
        try: self.save()
        except OSError: pass
        self.sync_state.unlink(missing_ok=True)
        self.root.destroy()

if __name__ == '__main__':
    root=tk.Tk()
    Launcher(root)
    root.mainloop()
