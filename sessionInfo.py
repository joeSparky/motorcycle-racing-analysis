#!/usr/bin/env python3
"""Display original AIM CSV metadata without changing the recording."""
import argparse
import csv
import io
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from aimcsv import extract


def read_metadata(filename):
    output = io.StringIO()
    with Path(filename).open(encoding='utf-8-sig',newline='') as source:
        extract(source,output,'metadata')
    # Keep repeated fields, empty values, multiline comments and value order.
    return [(row[0], ', '.join(row[1:])) for row in csv.reader(io.StringIO(output.getvalue())) if row]


class SessionInfo:
    def __init__(self,root,filename,metadata):
        root.title('Session Information — '+Path(filename).name)
        root.geometry('900x620'); root.minsize(650,430)
        frame=ttk.Frame(root,padding=15); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Session Information',font=('TkDefaultFont',18,'bold')).pack(anchor='w')
        ttk.Label(frame,text=str(Path(filename).resolve()),wraplength=850).pack(anchor='w',pady=(4,12))
        table_frame=ttk.Frame(frame); table_frame.pack(fill='both',expand=True)
        table=ttk.Treeview(table_frame,columns=('field','value'),show='headings',selectmode='browse')
        table.heading('field',text='CSV field'); table.heading('value',text='Value')
        table.column('field',width=190,stretch=False); table.column('value',width=600)
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=table.yview)
        table.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); table.pack(fill='both',expand=True)
        for i,(field,value) in enumerate(metadata):
            table.insert('', 'end',iid=str(i),values=(field,value.replace('\n',' ⏎ ')))
        ttk.Label(frame,text='Select a field to read its full value below. Fields are shown exactly as supplied by the CSV.').pack(anchor='w',pady=(8,3))
        detail_frame=ttk.Frame(frame); detail_frame.pack(fill='x')
        detail=tk.Text(detail_frame,height=6,wrap='word',state='disabled')
        detail_scroll=ttk.Scrollbar(detail_frame,command=detail.yview); detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side='right',fill='y'); detail.pack(fill='x',expand=True)
        def selected(event=None):
            selection=table.selection()
            if selection:
                field,value=metadata[int(selection[0])]
                detail.configure(state='normal'); detail.delete('1.0','end'); detail.insert('1.0',field+'\n'+value); detail.configure(state='disabled')
        table.bind('<<TreeviewSelect>>',selected)
        if metadata: table.selection_set('0'); selected()
        else:
            detail.configure(state='normal'); detail.insert('1.0','No metadata fields were found.'); detail.configure(state='disabled')


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--race',required=True); args=parser.parse_args()
    root=tk.Tk(); root.withdraw()
    try:
        metadata=read_metadata(args.race); SessionInfo(root,args.race,metadata); root.deiconify(); root.mainloop()
    except (OSError,ValueError,csv.Error) as exc:
        messagebox.showerror('Cannot read session information',str(exc),parent=root); root.destroy(); raise SystemExit(2)


if __name__=='__main__': main()
