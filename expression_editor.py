"""Expression controls shared by statistics and the dashboard."""
import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import yaml

BASE = Path(__file__).resolve().parent


def save_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


class ExpressionEditor(ttk.LabelFrame):
    def __init__(self, parent, evaluator):
        super().__init__(parent, text='Expression', padding=8)
        self.evaluator = evaluator
        self.path = BASE/'expressions.json'
        try:
            self.saved = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            self.saved = {}
        self.name = tk.StringVar(value='RPM')
        self.expression = tk.StringVar(value='RPM')
        self.units = tk.StringVar()
        self.decimals = tk.StringVar(value='2')
        self.bin_width = tk.StringVar(value='0')
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text='Saved name').grid(row=0,column=0,sticky='w')
        self.names = ttk.Combobox(self,textvariable=self.name,values=list(self.saved))
        self.names.grid(row=0,column=1,sticky='ew')
        self.names.bind('<<ComboboxSelected>>',lambda e:self.load(self.saved[self.name.get()]))
        ttk.Button(self,text='Save expression',command=self.save).grid(row=0,column=2,padx=6)
        ttk.Label(self,text='Formula').grid(row=1,column=0,sticky='w')
        ttk.Entry(self,textvariable=self.expression).grid(row=1,column=1,columnspan=2,sticky='ew',pady=5)
        channels = ttk.Combobox(self,values=evaluator.fields,state='readonly')
        channels.grid(row=2,column=1,sticky='ew')
        channels.bind('<<ComboboxSelected>>',lambda e:self.expression.set(self.expression.get()+'['+channels.get()+']'))
        ttk.Label(self,text='Append channel').grid(row=2,column=0,sticky='w')
        settings = ttk.Frame(self); settings.grid(row=3,column=0,columnspan=3,sticky='w',pady=5)
        for label,var in [('Units',self.units),('Decimals',self.decimals),('Mode bin width',self.bin_width)]:
            ttk.Label(settings,text=label).pack(side='left',padx=4)
            ttk.Entry(settings,textvariable=var,width=9).pack(side='left')
        ttk.Label(self,text='Use [GPS Speed] for channel names with spaces. Operators: + − * / % ** and comparisons. Mode width 0 = exact values.').grid(row=4,column=0,columnspan=3,sticky='w')
        if self.saved:
            self.name.set(next(iter(self.saved))); self.load(self.saved[self.name.get()])
        elif 'RPM' not in evaluator.fields:
            self.expression.set('['+evaluator.fields[-1]+']')

    def load(self, item):
        self.expression.set(item.get('expression',item.get('channel','RPM')))
        self.units.set(item.get('units',''))
        self.decimals.set(str(item.get('decimals',2)))
        self.bin_width.set(str(item.get('bin_width',0)))

    def get(self):
        self.evaluator.compile(self.expression.get())
        decimals = int(self.decimals.get()); width = float(self.bin_width.get())
        if not 0 <= decimals <= 8 or not math.isfinite(width) or width < 0:
            raise ValueError('Decimals must be 0–8; bin width must be finite and nonnegative.')
        return dict(expression=self.expression.get(),label=self.name.get().strip(),units=self.units.get(),decimals=decimals,bin_width=width)

    def save(self):
        try:
            item = self.get()
            if not item['label']: raise ValueError('Enter a saved expression name.')
            updated = dict(self.saved); updated[item['label']] = item
            save_json(self.path,updated)
            self.saved = updated; self.names.configure(values=list(updated))
        except (OSError,ValueError) as exc:
            messagebox.showerror('Cannot save expression',str(exc),parent=self)


def edit_dashboard(dashboard):
    window = tk.Toplevel(dashboard.root); window.title('Dashboard expressions')
    window.transient(dashboard.root); window.grab_set()
    items = dashboard.config.get('display',[])
    if not items:
        window.destroy(); return
    choice = ttk.Combobox(window,values=[f'{i+1}. {v.get("label", "Gauge")}' for i,v in enumerate(items)],state='readonly',width=45)
    choice.pack(fill='x',padx=12,pady=8); choice.current(0)
    editor = ExpressionEditor(window,dashboard.expression_evaluator); editor.pack(fill='x',padx=12,pady=8)
    limits = ttk.Frame(window); limits.pack(pady=5)
    low = tk.StringVar(); high = tk.StringVar()
    for label,var in [('Gauge minimum',low),('Gauge maximum',high)]:
        ttk.Label(limits,text=label).pack(side='left',padx=5); ttk.Entry(limits,textvariable=var,width=10).pack(side='left')
    def load():
        item=items[choice.current()]; editor.load(item); editor.name.set(item.get('label','Gauge'))
        low.set(str(item.get('min',0))); high.set(str(item.get('max',100)))
    choice.bind('<<ComboboxSelected>>',lambda e:load()); load()
    def apply():
        try:
            item = editor.get(); a,b = float(low.get()),float(high.get())
            if not math.isfinite(a) or not math.isfinite(b) or a >= b: raise ValueError('Gauge minimum must be less than maximum.')
            item.update(min=a,max=b)
            updated = dict(items[choice.current()])
            # The edited expression produces the display units directly.
            for key in ('channel','conversion','scale','offset'): updated.pop(key,None)
            updated.update(item)
            config = dict(dashboard.config); display=list(items); display[choice.current()]=updated; config['display']=display
            path = dashboard.config_path
            temp = path.with_name(path.name+'.tmp')
            temp.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8'); temp.replace(path)
            dashboard.config = config
            for child in dashboard.display_frame.winfo_children(): child.destroy()
            dashboard.widgets.clear(); dashboard.build_display(); window.destroy()
        except (OSError,ValueError) as exc:
            messagebox.showerror('Cannot update gauge',str(exc),parent=window)
    ttk.Button(window,text='Apply and save gauge',command=apply).pack(pady=12)
