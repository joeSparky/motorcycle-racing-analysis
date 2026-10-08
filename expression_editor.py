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


def save_dashboard_config(dashboard, items):
    """Persist the complete list before changing the live dashboard."""
    config = dict(dashboard.config); config['display'] = items
    path = dashboard.config_path
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
    temp.replace(path)
    dashboard.config = config
    for child in dashboard.display_frame.winfo_children(): child.destroy()
    dashboard.widgets.clear(); dashboard.build_display()


def edit_dashboard(dashboard):
    import copy
    window = tk.Toplevel(dashboard.root); window.title('Dashboard gauges')
    window.transient(dashboard.root); window.grab_set()
    items = copy.deepcopy(dashboard.config.get('display',[]))
    choice = ttk.Combobox(window,state='readonly',width=45)
    choice.pack(fill='x',padx=12,pady=8)
    actions = ttk.Frame(window); actions.pack(fill='x',padx=12)
    editor = ExpressionEditor(window,dashboard.expression_evaluator); editor.pack(fill='x',padx=12,pady=8)
    limits = ttk.Frame(window); limits.pack(pady=5)
    kind = tk.StringVar(value='number')
    ttk.Label(limits,text='Display').pack(side='left',padx=5)
    ttk.Combobox(limits,textvariable=kind,values=['number','bar'],state='readonly',width=9).pack(side='left')
    low = tk.StringVar(value='0'); high = tk.StringVar(value='100')
    for label,var in [('Gauge minimum',low),('Gauge maximum',high)]:
        ttk.Label(limits,text=label).pack(side='left',padx=5); ttk.Entry(limits,textvariable=var,width=10).pack(side='left')
    selected = None
    def load(index):
        nonlocal selected
        selected = index
        choice.configure(values=[f'{i+1}. {v.get("label", "Gauge")}' for i,v in enumerate(items)])
        if index is None:
            choice.set('No gauges — click Add Gauge')
        else:
            choice.current(index)
            item=items[index]; editor.load(item); editor.name.set(item.get('label','Gauge'))
            kind.set(item.get('type','number').lower())
            low.set(str(item.get('min',0))); high.set(str(item.get('max',100)))
        delete_button.state(['disabled'] if index is None else ['!disabled'])
        up_button.state(['disabled'] if index is None or index == 0 else ['!disabled'])
        down_button.state(['disabled'] if index is None or index == len(items)-1 else ['!disabled'])

    def capture():
        if selected is None: return
        item = editor.get(); a,b = float(low.get()),float(high.get())
        if not item['label']: raise ValueError('Enter a gauge label in Saved name.')
        if not math.isfinite(a) or not math.isfinite(b) or a >= b: raise ValueError('Gauge minimum must be less than maximum.')
        item.update(min=a,max=b,type=kind.get())
        updated = dict(items[selected])
        if item['expression'] != updated.get('expression',updated.get('channel')):
            for key in ('channel','conversion','scale','offset'): updated.pop(key,None)
        updated.update(item); items[selected] = updated

    def perform(action):
        try: action()
        except (OSError,ValueError) as exc:
            messagebox.showerror('Cannot update gauges',str(exc),parent=window)

    def choose():
        new = choice.current()
        try: capture()
        except ValueError:
            if selected is not None: choice.current(selected)
            raise
        load(new)

    def add():
        capture()
        expression = 'RPM' if 'RPM' in dashboard.expression_evaluator.fields else '['+dashboard.expression_evaluator.fields[0]+']'
        items.append(dict(expression=expression,label='New Gauge',type='number',units='',decimals=2,min=0,max=100))
        load(len(items)-1)

    def delete():
        if selected is None: return
        old = selected; items.pop(old)
        load(min(old,len(items)-1) if items else None)

    def move(delta):
        if selected is None: return
        capture(); target=selected+delta
        if 0 <= target < len(items):
            items[selected],items[target]=items[target],items[selected]
            load(target)

    def apply():
        capture(); save_dashboard_config(dashboard,items); window.destroy()

    ttk.Button(actions,text='Add Gauge',command=lambda:perform(add)).pack(side='left',padx=4)
    delete_button=ttk.Button(actions,text='Delete Gauge',command=lambda:perform(delete)); delete_button.pack(side='left',padx=4)
    up_button=ttk.Button(actions,text='Move Up',command=lambda:perform(lambda:move(-1))); up_button.pack(side='left',padx=4)
    down_button=ttk.Button(actions,text='Move Down',command=lambda:perform(lambda:move(1))); down_button.pack(side='left',padx=4)
    choice.bind('<<ComboboxSelected>>',lambda e:perform(choose))
    load(0 if items else None)
    ttk.Label(window,text='Changes take effect with Apply and save gauges. Closing this window discards gauge changes.').pack(padx=12,pady=6)
    ttk.Button(window,text='Apply and save gauges',command=lambda:perform(apply)).pack(pady=12)
