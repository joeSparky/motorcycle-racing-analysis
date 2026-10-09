#!/usr/bin/env python3
"""Graphically define named track sections inside the $track JSON project."""
import argparse,json,math,os,tkinter as tk
from tkinter import messagebox,simpledialog,filedialog
from interesting_points import InterestingPoints, POINT_COLORS
from pathlib import Path
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class App:
    def __init__(self,root,fn):
        self.root=root; self.fn=Path(fn)
        raw=self.fn.read_text(encoding="utf-8")
        try:
            self.data=json.loads(raw)
        except json.JSONDecodeError as e:
            # Recover files corrupted by sectionEditor v1, which appended a YAML
            # "sections:" block after an otherwise complete JSON document.
            dec=json.JSONDecoder()
            self.data,end=dec.raw_decode(raw)
            tail=raw[end:].strip()
            if not tail.startswith("sections:"):
                raise
            recovered=[]
            current=None
            for line in tail.splitlines()[1:]:
                t=line.strip()
                if t.startswith("- name:"):
                    if current: recovered.append(current)
                    name=t.split(":",1)[1].strip().strip(chr(34)).strip(chr(39))
                    current={"name":name}
                elif current is not None and t.startswith("start:"):
                    current["start"]=int(t.split(":",1)[1].strip())
                elif current is not None and t.startswith("end:"):
                    current["end"]=int(t.split(":",1)[1].strip())
            if current: recovered.append(current)
            if recovered:
                self.data["sections"]=recovered
            messagebox.showinfo("Recovered track project",
                "I found the old YAML sections appended after the JSON.\\n"
                "They were recovered in memory. Press SAVE SECTIONS to repair the file as valid JSON.")
        self.div=int(self.data.get("divisions",10000))
        nodes=self.data.get("nodes",[])
        if len(nodes)<2: raise ValueError("Track project has no usable nodes.")
        self.pts=[(float(n["position"]),float(n["reference"][0]),float(n["reference"][1])) for n in nodes]
        self.pts.sort()
        # 10000 duplicates 0 geometrically; use 0 as the fixed lap boundary.
        self.pts=[p for p in self.pts if p[0] < self.div]
        self.sections=[]
        saved=self.data.get("sections",[])
        if saved:
            for s in saved:
                self.sections.append({"start":int(s["start"])%self.div})
            self.sections.sort(key=lambda s:s["start"])
            if not any(s["start"]==0 for s in self.sections):
                self.sections.insert(0,{"start":0})
        else:
            self.sections=[{"start":0}]
        self.drag=None
        self.points_model=InterestingPoints({'config':self.data})
        self.show_points=tk.BooleanVar(value=True)

        root.title("Track Section Editor");root.geometry("1050x780")
        bar=tk.Frame(root);bar.pack(fill="x",padx=8,pady=6)
        tk.Button(bar,text="SAVE SECTIONS",command=self.save).pack(side="left")
        tk.Button(bar,text="CLEAR",command=self.clear).pack(side="left")
        tk.Label(bar,text="Click track: split  •  Drag boundary: resize  •  Right-click boundary: merge").pack(side="left",padx=10)
        points_bar=tk.Frame(root);points_bar.pack(fill='x',padx=8,pady=3)
        tk.Button(points_bar,text='Load points',command=self.load_points).pack(side='left')
        tk.Checkbutton(points_bar,text='Show interesting points (read only)',variable=self.show_points,command=self.draw).pack(side='left',padx=8)
        self.points_info=tk.Label(points_bar,text='No points loaded');self.points_info.pack(side='left')
        self.info=tk.Label(root);self.info.pack(fill="x")
        fig=Figure(figsize=(9,6.5),dpi=100);self.ax=fig.add_subplot(111)
        self.cv=FigureCanvasTkAgg(fig,root);self.cv.get_tk_widget().pack(fill="both",expand=True)
        self.cv.mpl_connect("button_press_event",self.press)
        self.cv.mpl_connect("motion_notify_event",self.motion)
        self.cv.mpl_connect("button_release_event",self.release)
        self.draw()

    def load_points(self):
        filename=filedialog.askopenfilename(parent=self.root,title='Load interesting points',filetypes=[('Points JSON','*.json')])
        if not filename:return
        try:self.points_model.load(Path(filename))
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('Cannot load points',str(exc),parent=self.root);return
        self.show_points.set(True)
        self.points_info.config(text=f'{len(self.points_model.markers)} points • {Path(filename).name}')
        self.draw()

    def point_at_pixel(self,e,limit=12):
        if not self.show_points.get():return False
        for marker in self.points_model.markers:
            x,y=self.ax.transData.transform((marker['x_m'],marker['y_m']))
            if math.hypot(x-e.x,y-e.y)<=limit:return True
        return False

    def q(self,pos): return min(self.pts,key=lambda p:abs(p[0]-pos))
    def nearest_track(self,x,y):
        xr=max(p[1] for p in self.pts)-min(p[1] for p in self.pts) or 1
        yr=max(p[2] for p in self.pts)-min(p[2] for p in self.pts) or 1
        return min(self.pts,key=lambda p:((p[1]-x)/xr)**2+((p[2]-y)/yr)**2)
    def starts(self): return [s["start"] for s in self.sections]
    def boundary_at_pixel(self,e,limit=14):
        best=None
        for i,s in enumerate(self.sections):
            q=self.q(s["start"]); px,py=self.ax.transData.transform((q[1],q[2]))
            d=math.hypot(px-e.x,py-e.y)
            if d<=limit and (best is None or d<best[0]):best=(d,i)
        return None if best is None else best[1]
    def section_midpoint(self,i):
        a=self.sections[i]["start"]; b=self.sections[(i+1)%len(self.sections)]["start"]
        length=(b-a)%self.div
        return (a+length/2)%self.div
    def label_at_pixel(self,e,limit=35):
        best=None
        if len(self.sections)<2:return None
        for i,s in enumerate(self.sections):
            q=self.q(self.section_midpoint(i));px,py=self.ax.transData.transform((q[1],q[2]))
            d=math.hypot(px-e.x,py-e.y)
            if d<=limit and (best is None or d<best[0]):best=(d,i)
        return None if best is None else best[1]
    def section_id(self,i):
        """Section identifier is its ending TrackPosition; wrap section ends at 10000."""
        if i + 1 < len(self.sections):
            return self.sections[i+1]["start"]
        return self.div

    def press(self,e):
        if e.inaxes!=self.ax or e.xdata is None:return
        if self.point_at_pixel(e):return
        bi=self.boundary_at_pixel(e)
        if e.button==3:
            if bi is not None and self.sections[bi]["start"]!=0:
                # Removing boundary merges into preceding section; preceding name survives.
                del self.sections[bi];self.draw()
            return
        if e.button!=1:return
        if bi is not None and self.sections[bi]["start"]!=0:
            self.drag=bi;return
        p=int(round(self.nearest_track(e.xdata,e.ydata)[0]))%self.div
        if p==0 or p in self.starts():return
        # Split: old/first part keeps its name, new/second part gets a default name.
        insert=next((i for i,s in enumerate(self.sections) if s["start"]>p),len(self.sections))
        self.sections.insert(insert,{"start":p})
        self.draw()
    def motion(self,e):
        if self.drag is None or e.inaxes!=self.ax or e.xdata is None:return
        p=int(round(self.nearest_track(e.xdata,e.ydata)[0]))%self.div
        i=self.drag; prev=self.sections[i-1]["start"]
        nxt=self.sections[i+1]["start"] if i+1<len(self.sections) else self.div
        # Never cross neighbors; leave at least one TrackPosition unit.
        p=max(prev+1,min(nxt-1,p))
        self.sections[i]["start"]=p;self.draw()
    def release(self,e):self.drag=None
    def clear(self):
        if messagebox.askyesno("Clear sections","Remove all section boundaries and names?"):
            self.sections=[{"start":0}];self.draw()
    def draw(self):
        self.ax.clear();self.ax.set_aspect("equal",adjustable="datalim")
        self.ax.plot([p[1] for p in self.pts]+[self.pts[0][1]],[p[2] for p in self.pts]+[self.pts[0][2]],linewidth=1.5)
        for s in self.sections:
            q=self.q(s["start"]);self.ax.plot(q[1],q[2],"o",markersize=7)
            self.ax.annotate(str(s["start"]),(q[1],q[2]),xytext=(5,5),textcoords="offset points",fontsize=8)
        if self.show_points.get():
            for marker in self.points_model.markers:
                x,y=marker['x_m'],marker['y_m'];color=POINT_COLORS[marker['type']]
                self.ax.plot(x,y,marker='D' if marker['type']=='marker' else 'o',color=color,markersize=7)
                self.ax.annotate(marker['label'],(x,y),xytext=(9,-10),textcoords='offset points',fontsize=9,color=color)
        self.ax.set_title("Track Sections")
        self.info.config(text=f'{len(self.sections)} section{"s" if len(self.sections)!=1 else ""} • TrackPosition 0–{self.div}')
        self.cv.draw_idle()
    def save(self, quiet=False):
        if len(self.sections)<2:
            messagebox.showwarning("Sections","Create at least two sections before saving.")
            return False
        out=[]
        for i,s in enumerate(self.sections):
            end = self.sections[i+1]["start"] if i+1 < len(self.sections) else self.div
            out.append({"start":s["start"],"end":end})
        self.data["sections"]=out
        # Atomic-ish save: backup then temporary file then replace.
        backup=self.fn.with_suffix(self.fn.suffix+".bak")
        backup.write_bytes(self.fn.read_bytes())
        tmp=self.fn.with_suffix(self.fn.suffix+".tmp")
        tmp.write_text(json.dumps(self.data,indent=2)+"\n",encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8")) # verify before replacing
        tmp.replace(self.fn)
        if not quiet:
            messagebox.showinfo("Saved",f"Saved {len(out)} sections.\nBackup: {backup.name}")
        return True

    def done(self):
        if self.save(quiet=True):
            self.root.destroy()

def main():
    p=argparse.ArgumentParser();p.add_argument("--track",default=os.getenv("track"));a=p.parse_args()
    if not a.track:p.error("Set $track or use --track FILE.")
    r=tk.Tk()
    try:App(r,a.track)
    except Exception as e:r.withdraw();messagebox.showerror("Section Editor",str(e));raise
    r.mainloop()
if __name__=="__main__":main()

