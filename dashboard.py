#!/usr/bin/env python3
"""
dashboard.py

Configurable MPV/AiM video dashboard.

Standard environment variables:
    $race   raw AiM race CSV
    $video  helmet video

Configuration:
    dashboard.yaml (beside this script by default)

The race is cleaned internally through aimcsv.py.
"""
import re
import argparse
import ast
import csv
import io
import json
import math
import os
import socket
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from bisect import bisect_left
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit(
        "PyYAML is required. Install it with:\n"
        "  sudo apt install python3-yaml"
    )


def display_number(value, decimals=0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "---"
    return f"{n:,.{int(decimals)}f}"


def format_video_time(seconds):
    if seconds is None:
        return "--:--.---"
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:06.3f}"


from expressions import ExpressionEvaluator


def read_timed_laps(filename):
    """Use complete beacon-to-beacon intervals; omit the session's lead-in."""
    with Path(filename).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if row and row[0] == "Beacon Markers":
                markers = [float(v) for v in row[1:] if v.strip()]
                if not all(math.isfinite(v) for v in markers) or any(b <= a for a, b in zip(markers, markers[1:])):
                    raise ValueError("Beacon markers must increase in time.")
                return [{"number": i, "start": a, "end": b, "duration": b-a}
                        for i, (a, b) in enumerate(zip(markers, markers[1:]), 1)]
            if row[:2] == ["Time", "GPS Speed"]:
                break
    return []


def lap_time(seconds):
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


class RaceData:
    def __init__(self, filename):
        self.filename = Path(filename)
        self.rows = []
        self.times = []

        aimcsv = Path(__file__).resolve().parent / "aimcsv.py"
        if not aimcsv.is_file():
            raise ValueError(f"aimcsv.py not found beside dashboard.py: {aimcsv}")

        try:
            result = subprocess.run(
                [sys.executable, str(aimcsv), str(self.filename)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or "").strip()
            raise ValueError(f"aimcsv.py failed: {detail}")

        reader = csv.DictReader(io.StringIO(result.stdout))
        self.fields = reader.fieldnames or []
        if "Time" not in self.fields:
            raise ValueError("Cleaned race CSV does not contain a Time column.")

        for row in reader:
            try:
                t = float(row["Time"])
            except (TypeError, ValueError):
                continue
            self.times.append(t)
            self.rows.append(row)

        if not self.rows:
            raise ValueError("Race CSV contains no usable data rows.")

    def nearest(self, target_time):
        i = bisect_left(self.times, target_time)
        if i <= 0:
            return self.times[0], self.rows[0]
        if i >= len(self.times):
            return self.times[-1], self.rows[-1]

        before = i - 1
        after = i
        if abs(self.times[after] - target_time) < abs(target_time - self.times[before]):
            return self.times[after], self.rows[after]
        return self.times[before], self.rows[before]


from mpv_ipc import MpvConnection, DEFAULT_PIPE


class Dashboard:
    def __init__(self, root, race_data, calibration, socket_path, video_path, config, track_path=None):
        self.root = root
        self.race_data = race_data
        self.slope = float(calibration["slope"])
        self.offset = float(calibration["offset"])
        self.sync_adjustment = 0.0
        self.sync_state = None
        self.mpv = MpvConnection(socket_path)
        self.socket_path = socket_path
        self.video_path = video_path
        self.mpv_process = None
        self.config = config
        self.config_path = Path(__file__).resolve().parent / "dashboard.yaml"
        self.expression_evaluator = ExpressionEvaluator(race_data.fields)
        self.widgets = []
        self.active_lap = None
        self.pending_lap = None
        self.lap_dialog = None
        self.track_path = Path(track_path) if track_path else None
        self.segment_process = None
        self.segment_dialog = None
        self.segment_output = None
        self.repeat_lap = tk.BooleanVar(value=False)
        try:
            self.laps = read_timed_laps(race_data.filename)
            self.lap_error = ""
        except (OSError, ValueError) as exc:
            self.laps = []
            self.lap_error = str(exc)

        root.title(config.get("title", "Race Dashboard"))
        root.geometry(config.get("window", "650x650"))

        tk.Label(
            root,
            text=config.get("title", "RACE DASHBOARD"),
            font=("TkDefaultFont", 20, "bold"),
        ).pack(pady=(14, 8))

        self.display_frame = tk.Frame(root)
        self.display_frame.pack(fill="both", expand=True, padx=25)

        self.build_display()

        info = tk.Frame(root)
        info.pack(pady=(8, 2))
        self.video_time_label = tk.Label(info, text="Video --:--.---")
        self.video_time_label.pack(side="left", padx=12)
        self.csv_time_label = tk.Label(info, text="CSV ---")
        self.csv_time_label.pack(side="left", padx=12)

        controls = tk.Frame(root)
        controls.pack(pady=(10, 2))

        self.start_video_button = tk.Button(
            controls, text="START VIDEO", width=20, height=2,
            command=self.start_video
        )
        self.start_video_button.pack(side="left", padx=(0, 14))

        default_audio = bool(config.get("video", {}).get("audio", False))
        self.audio_enabled = tk.BooleanVar(value=default_audio)
        tk.Checkbutton(
            controls, text="Audio", variable=self.audio_enabled,
            font=("TkDefaultFont", 12)
        ).pack(side="left", padx=(0, 12))

        default_flip = bool(config.get("video", {}).get("flip", False))
        self.flip_enabled = tk.BooleanVar(value=default_flip)
        tk.Checkbutton(
            controls, text="Flip Video", variable=self.flip_enabled,
            font=("TkDefaultFont", 12)
        ).pack(side="left")

        transport = tk.Frame(root)
        transport.pack(pady=(8, 2))

        tk.Button(transport, text="-10s", width=6,
                  command=lambda: self.send_mpv("seek", -10, "relative")).pack(side="left", padx=2)
        tk.Button(transport, text="-1s", width=6,
                  command=lambda: self.send_mpv("seek", -1, "relative")).pack(side="left", padx=2)
        tk.Button(transport, text="PLAY / PAUSE", width=13,
                  command=lambda: self.send_mpv("cycle", "pause")).pack(side="left", padx=2)
        tk.Button(transport, text="+1s", width=6,
                  command=lambda: self.send_mpv("seek", 1, "relative")).pack(side="left", padx=2)
        tk.Button(transport, text="+10s", width=6,
                  command=lambda: self.send_mpv("seek", 10, "relative")).pack(side="left", padx=2)

        frames = tk.Frame(root)
        frames.pack(pady=(2, 4))
        tk.Button(frames, text="< FRAME", width=10,
                  command=lambda: self.send_mpv("frame-back-step")).pack(side="left", padx=2)
        tk.Button(frames, text="FRAME >", width=10,
                  command=lambda: self.send_mpv("frame-step")).pack(side="left", padx=2)

        sync = tk.Frame(root)
        sync.pack(pady=2)
        tk.Label(sync, text="Video sync:").pack(side="left", padx=4)
        tk.Button(sync, text="-0.1 s", command=lambda: self.adjust_sync(-0.1)).pack(side="left", padx=2)
        tk.Button(sync, text="+0.1 s", command=lambda: self.adjust_sync(0.1)).pack(side="left", padx=2)
        self.sync_label = tk.Label(sync, text="+0.0 s")
        self.sync_label.pack(side="left", padx=6)
        tk.Button(sync, text="Reset", command=self.reset_sync).pack(side="left", padx=2)
        tk.Button(frames, text="Best lap / Laps...", width=18,
                  command=self.show_laps).pack(side="left", padx=8)
        tk.Button(frames, text="Best segments...", width=16,
                  command=self.show_segments).pack(side="left", padx=2)
        from expression_editor import edit_dashboard
        tk.Button(root, text="Edit gauges...", command=lambda: edit_dashboard(self)).pack(pady=3)
        self.status = tk.Label(root, text="MPV is not running.")
        self.status.pack(pady=(7, 12))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.update_dashboard()

    def show_segments(self):
        if self.segment_process is not None:
            self.status.config(text="Calculating segment times...")
            return
        if self.segment_dialog is not None and self.segment_dialog.winfo_exists():
            self.segment_dialog.lift()
            return
        if self.track_path is None:
            filename = filedialog.askopenfilename(parent=self.root, title="Choose track project with saved segments",
                filetypes=[("Track project JSON", "*.json")])
            if not filename:
                return
            self.track_path = Path(filename)
        try:
            # Temporary stdout storage prevents a full pipe from blocking the worker.
            import tempfile
            self.segment_output = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
            self.segment_process = subprocess.Popen([sys.executable,
                str(Path(__file__).resolve().parent / "segment_analysis.py"),
                "--race", str(self.race_data.filename), "--track", str(self.track_path)],
                stdout=self.segment_output, stderr=self.segment_output,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.status.config(text="Calculating segment times...")
            self.root.after(150, self.poll_segments)
        except OSError as exc:
            if self.segment_output:
                self.segment_output.close()
            self.segment_process = None
            messagebox.showerror("Segment analysis", str(exc))

    def poll_segments(self):
        code = self.segment_process.poll()
        if code is None:
            self.root.after(150, self.poll_segments)
            return
        self.segment_output.seek(0)
        output = self.segment_output.read()
        self.segment_output.close()
        self.segment_output = None
        self.segment_process = None
        try:
            if code:
                raise ValueError(output[-2000:] or "Segment calculation failed.")
            result = json.loads(output)
            self.build_segment_dialog(result)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Segment analysis", str(exc))

    def build_segment_dialog(self, result):
        dialog = self.segment_dialog = tk.Toplevel(self.root)
        dialog.title("Best segment timing")
        dialog.geometry("860x630")
        total = result['theoretical_time']
        best_lap = result.get('best_actual_lap')
        actual = float(best_lap['IntervalTime']) if best_lap else None
        best_text = f"Best complete lap: {lap_time(actual)} — observed lap {best_lap['Lap']}" if best_lap else "Best complete lap: unavailable"
        tk.Label(dialog, text=best_text, font=("TkDefaultFont", 15, "bold")).pack(pady=(8, 0))
        heading = "Sum of best segments: " + (lap_time(total) if total is not None else "unavailable (missing complete pass)")
        tk.Label(dialog, text=heading, font=("TkDefaultFont", 15, "bold")).pack(pady=8)
        if actual is not None and total is not None:
            tk.Label(dialog, text=f"Difference: {actual - total:.3f} s (best complete lap minus best segments)").pack()
        tk.Label(dialog, text="Complete forward passes only. Times interpolate boundary crossings; interrupted visits are excluded.").pack()
        summary = ttk.Treeview(dialog, columns=("segment", "range", "time", "lap", "count"), show="headings", height=7, selectmode="browse")
        for key, title, width in [("segment", "Segment", 90), ("range", "Positions", 180), ("time", "Best time", 130), ("lap", "Observed lap", 120), ("count", "Complete passes", 130)]:
            summary.heading(key, text=title);summary.column(key, width=width, anchor="center")
        for segment in result['segments']:
            best = segment['best']
            count = sum(p['Complete'] == 'true' for p in segment['passes'])
            summary.insert("", "end", iid=str(segment['end']), values=(segment['end'], f"{segment['start']}–{segment['end']}",
                f"{float(best['IntervalTime']):.3f} s" if best else "—", best['Lap'] if best else "—", count))
        summary.pack(fill="both", expand=True, padx=12, pady=8)
        tk.Label(dialog, text="Passes through selected segment — fastest first").pack()
        detail = ttk.Treeview(dialog, columns=("pass", "lap", "time", "gap", "entry", "status"), show="headings", height=8, selectmode="browse")
        for key, title in [("pass", "Pass"), ("lap", "Observed lap"), ("time", "Time (s)"), ("gap", "Behind best (s)"), ("entry", "CSV entry (s)"), ("status", "Status")]:
            detail.heading(key, text=title);detail.column(key, width=120, anchor="center")
        detail.pack(fill="both", expand=True, padx=12, pady=8)
        current = {'segment': None, 'passes': {}}
        def fill(event=None):
            selection = summary.selection()
            if not selection:
                return
            segment = next(s for s in result['segments'] if str(s['end']) == selection[0])
            current['segment'] = segment
            current['passes'] = {}
            detail.delete(*detail.get_children())
            passes = sorted(segment['passes'], key=lambda p: (p['Complete'] != 'true', float(p['IntervalTime']) if p['IntervalTime'] else float('inf')))
            for p in passes:
                iid = str(p['Pass']);current['passes'][iid] = p
                detail.insert("", "end", iid=iid, values=(p['Pass'], p['Lap'],
                    f"{float(p['IntervalTime']):.3f}" if p['IntervalTime'] else "—",
                    f"{float(p['BehindBest']):.3f}" if p['BehindBest'] else "—", p['EntryTime'] or "—", p['Status']))
            if passes:
                detail.selection_set(str(passes[0]['Pass']))
        def play(best=False):
            segment = current['segment']
            if segment is None:
                return
            selected = detail.selection()
            p = segment['best'] if best else current['passes'].get(selected[0]) if selected else None
            if not p or p['Complete'] != 'true':
                messagebox.showinfo("Segment playback", "Select a complete pass to play.", parent=dialog)
                return
            self.play_lap({'number': p['Lap'], 'start': float(p['EntryTime']), 'end': float(p['ExitTime']),
                'duration': float(p['IntervalTime']), 'label': f"Segment {segment['end']} — observed lap {p['Lap']}"})
        buttons = tk.Frame(dialog);buttons.pack(pady=6)
        tk.Button(buttons, text="Play best segment", command=lambda: play(True)).pack(side="left", padx=4)
        tk.Button(buttons, text="Play selected pass", command=play).pack(side="left", padx=4)
        tk.Checkbutton(buttons, text="Repeat", variable=self.repeat_lap).pack(side="left", padx=4)
        tk.Label(dialog, text="Observed lap counts track-position-zero crossings; it may differ from the beacon lap list.").pack(pady=(0,6))
        summary.bind("<<TreeviewSelect>>", fill)
        detail.bind("<Double-1>", lambda event: play())
        summary.selection_set(str(result['segments'][0]['end']))
        fill()

    def show_laps(self):
        if not self.laps:
            messagebox.showinfo("Lap times", self.lap_error or "No complete beacon-to-beacon laps were found in this CSV.")
            return
        if self.lap_dialog is not None and self.lap_dialog.winfo_exists():
            self.lap_dialog.lift()
            return
        dialog = self.lap_dialog = tk.Toplevel(self.root)
        dialog.title("Lap analysis")
        dialog.geometry("610x450")
        best = min(self.laps, key=lambda lap: lap["duration"])
        tk.Label(dialog, text=f"Best timed lap: {best['number']} — {lap_time(best['duration'])}",
                 font=("TkDefaultFont", 15, "bold")).pack(pady=10)
        tk.Label(dialog, text="Complete laps between beacon crossings; the initial lead-in is excluded.").pack()
        table = ttk.Treeview(dialog, columns=("lap", "time", "behind", "start"), show="headings", selectmode="browse")
        for key, title, width in [("lap", "Timed lap", 90), ("time", "Time", 120), ("behind", "Behind best", 120), ("start", "CSV start", 120)]:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="center")
        for lap in self.laps:
            table.insert("", "end", iid=str(lap["number"]), values=(lap["number"], lap_time(lap["duration"]),
                f"+{lap['duration']-best['duration']:.3f} s", f"{lap['start']:.3f} s"))
        table.pack(fill="both", expand=True, padx=12, pady=8)
        table.selection_set(str(best["number"]))
        table.see(str(best["number"]))
        def selected():
            choice = table.selection()
            return next((lap for lap in self.laps if choice and str(lap["number"]) == choice[0]), best)
        buttons = tk.Frame(dialog)
        buttons.pack(pady=8)
        tk.Button(buttons, text="Play best lap", command=lambda: self.play_lap(best)).pack(side="left", padx=4)
        tk.Button(buttons, text="Play selected lap", command=lambda: self.play_lap(selected())).pack(side="left", padx=4)
        tk.Checkbutton(buttons, text="Repeat lap", variable=self.repeat_lap).pack(side="left", padx=4)
        table.bind("<Double-1>", lambda event: self.play_lap(selected()))

    def play_lap(self, lap):
        self.active_lap = None
        self.pending_lap = lap
        if self.mpv_process is None or self.mpv_process.poll() is not None:
            self.start_video()
            if self.mpv_process is None or self.mpv_process.poll() is not None:
                self.pending_lap = None

    def seek_lap_start(self, lap):
        start = self.slope * lap["start"] + self.offset + self.sync_adjustment
        if start < 0:
            messagebox.showwarning("Lap video", "This lap starts before the available video.")
            return False
        duration = self.mpv.get_property("duration")
        end = self.slope * lap["end"] + self.offset + self.sync_adjustment
        if duration is not None and end > float(duration) + 0.1:
            messagebox.showwarning("Lap video", "The available video does not cover this complete lap.")
            return False
        if not self.mpv.command("seek", start, "absolute+exact"):
            return False
        self.mpv.command("set_property", "pause", False)
        return True

    def publish_sync(self):
        if self.sync_state:
            from expression_editor import save_json
            save_json(self.sync_state,dict(slope=self.slope,offset=self.offset,adjustment=self.sync_adjustment))

    def adjust_sync(self, amount):
        # Positive adjustment puts video ahead of dashboard data.
        self.sync_adjustment = round(self.sync_adjustment + amount, 1)
        self.sync_label.config(text=f"{self.sync_adjustment:+.1f} s")
        self.publish_sync()

    def reset_sync(self):
        self.sync_adjustment = 0.0
        self.sync_label.config(text="+0.0 s")
        self.publish_sync()

    def close(self):
        if self.segment_process is not None and self.segment_process.poll() is None:
            self.segment_process.terminate()
            try:
                self.segment_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.segment_process.kill()
                self.segment_process.wait()
        if self.segment_output is not None:
            self.segment_output.close()
        self.mpv.close()
        if self.mpv_process is not None and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
        self.root.destroy()

    def build_display(self):
        for item in self.config.get("display", []):
            # "expression" is preferred. "channel" remains supported so old
            # dashboard.yaml files continue to work unchanged.
            expression = item.get("expression", item.get("channel"))
            if not expression:
                continue

            kind = item.get("type", "number").lower()
            label = item.get("label", expression)

            try:
                # Validate syntax and column names now. Numeric values are
                # supplied later from each race-data row.
                self.expression_evaluator.compile(expression)
            except (ValueError, SyntaxError) as e:
                tk.Label(
                    self.display_frame,
                    text=f"{label}: {e}",
                ).pack(anchor="w", pady=3)
                continue

            if kind == "bar":
                frame = tk.Frame(self.display_frame)
                frame.pack(fill="x", pady=7)

                tk.Label(
                    frame, text=label, width=12, anchor="e",
                    font=("TkDefaultFont", 13, "bold")
                ).pack(side="left", padx=(0, 10))

                canvas = tk.Canvas(
                    frame, height=24, width=330,
                    highlightthickness=1, highlightbackground="gray"
                )
                canvas.pack(side="left", fill="x", expand=True)
                fill = canvas.create_rectangle(0, 0, 0, 24, outline="", fill="gray")

                value_label = tk.Label(
                    frame, text="---", width=12, anchor="w",
                    font=("TkFixedFont", 13, "bold")
                )
                value_label.pack(side="left", padx=(10, 0))

                self.widgets.append({
                    "item": item, "kind": "bar",
                    "canvas": canvas, "fill": fill, "value": value_label,
                })

            else:
                frame = tk.Frame(self.display_frame)
                frame.pack(fill="x", pady=5)

                size = str(item.get("size", "normal")).lower()
                font_size = 30 if size == "large" else 16

                tk.Label(
                    frame, text=label, width=14, anchor="e",
                    font=("TkDefaultFont", 14, "bold")
                ).pack(side="left", padx=(0, 15))

                value_label = tk.Label(
                    frame, text="---", anchor="w",
                    font=("TkFixedFont", font_size, "bold")
                )
                value_label.pack(side="left")

                self.widgets.append({
                    "item": item, "kind": "number", "value": value_label
                })

    @staticmethod
    def converted_value(raw, item):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None

        conversion = item.get("conversion")
        if conversion == "m_to_ft":
            value *= 3.28084

        scale = item.get("scale")
        if scale is not None:
            value *= float(scale)

        offset = item.get("offset")
        if offset is not None:
            value += float(offset)

        return value

    def update_item(self, widget, row):
        item = widget["item"]
        expression = item.get("expression", item.get("channel"))
        try:
            raw_value = self.expression_evaluator.evaluate(expression, row)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
            raw_value = None
        value = self.converted_value(raw_value, item)
        decimals = int(item.get("decimals", 0))
        units = item.get("units", "")

        if value is None:
            widget["value"].config(text="---")
            if widget["kind"] == "bar":
                widget["canvas"].coords(widget["fill"], 0, 0, 0, 24)
            return

        text = f"{value:,.{decimals}f}"
        if units:
            text += f" {units}"
        widget["value"].config(text=text)

        if widget["kind"] == "bar":
            low = float(item.get("min", 0))
            high = float(item.get("max", 100))
            fraction = 0 if high == low else (value - low) / (high - low)
            fraction = max(0.0, min(1.0, fraction))
            canvas = widget["canvas"]
            width = max(1, canvas.winfo_width())
            canvas.coords(widget["fill"], 0, 0, width * fraction, 24)

    def send_mpv(self, *args):
        try:
            ok = self.mpv.command(*args)
            self.status.config(text="Following MPV" if ok else "MPV command failed")
        except (OSError, socket.timeout, ConnectionError, json.JSONDecodeError):
            self.mpv.close()
            self.status.config(text="Waiting for MPV...")

    def start_video(self):
        self.active_lap = None
        if not self.video_path:
            self.status.config(text="Video is not set. Use: source setVideo FILE")
            return
        if not self.video_path.is_file():
            self.status.config(text=f"Video file not found: {self.video_path}")
            return

        if self.mpv_process is not None and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
            try:
                self.mpv_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.mpv_process.kill()

        self.mpv.close()
        try:
            Path(self.socket_path).unlink(missing_ok=True)
        except OSError:
            pass

        video_cfg = self.config.get("video", {})
        width = int(video_cfg.get("width", 640))
        height = int(video_cfg.get("height", 360))

        cmd = [
            os.environ.get("MPV_EXE", "mpv"),
            "--pause",
            "--keep-open=yes",
            "--no-config",
            "--no-fullscreen",
            f"--geometry={width}x{height}",
            f"--input-ipc-server={self.socket_path}",
        ]

        if not self.audio_enabled.get():
            cmd.append("--no-audio")

        if self.flip_enabled.get():
            cmd.append("--vf=hflip,vflip")

        cmd.append(str(self.video_path))

        try:
            self.mpv_process = subprocess.Popen(cmd)
        except FileNotFoundError:
            self.status.config(text="mpv was not found on PATH.")
            return

        self.start_video_button.config(text="RESTART VIDEO")
        self.status.config(text="Starting MPV...")

    def update_dashboard(self):
        try:
            video_time = self.mpv.get_property("time-pos")
            if video_time is None:
                raise ConnectionError

            if self.pending_lap is not None:
                lap = self.pending_lap
                self.pending_lap = None
                if self.seek_lap_start(lap):
                    self.active_lap = lap
                self.root.after(50, self.update_dashboard)
                return

            csv_target = (float(video_time) - self.offset - self.sync_adjustment) / self.slope
            csv_time, row = self.race_data.nearest(csv_target)

            self.video_time_label.config(text=f"Video {format_video_time(video_time)}")
            self.csv_time_label.config(text=f"CSV {csv_time:.3f} s")

            for widget in self.widgets:
                self.update_item(widget, row)

            lap = self.active_lap
            if lap is not None and csv_target >= lap["end"]:
                if self.repeat_lap.get():
                    self.pending_lap = lap
                else:
                    self.mpv.command("set_property", "pause", True)
                    self.active_lap = None
            label = lap.get("label") or "Timed lap " + str(lap["number"]) if lap else "Following MPV"
            self.status.config(text=f"{label} — {lap_time(lap['duration'])}" if lap else label)
        except (OSError, ConnectionError, json.JSONDecodeError):
            self.mpv.close()
            self.status.config(text="Waiting for MPV...")

        self.root.after(50, self.update_dashboard)


def main():
    parser = argparse.ArgumentParser(description="Configurable race video dashboard.")
    parser.add_argument("--race", help="Override $race.")
    parser.add_argument("--video", help="Override $video.")
    parser.add_argument("--sync-state", help="Shared statistics video mapping")
    parser.add_argument("--config", help="Dashboard YAML file.")
    parser.add_argument("--track", help="Prepared track project with saved segments")
    parser.add_argument("--socket", default=DEFAULT_PIPE)
    args = parser.parse_args()

    race_value = args.race or os.environ.get("race")
    video_value = args.video or os.environ.get("video")

    if not race_value:
        raise SystemExit("Race is not set. Use: source setRace FILE")

    race_path = Path(race_value).expanduser().resolve()
    if not race_path.is_file():
        raise SystemExit(f"Race file not found: {race_path}")

    video_path = Path(video_value).expanduser().resolve() if video_value else None

    script_dir = Path(__file__).resolve().parent
    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else script_dir / "dashboard.yaml"
    )
    if not config_path.is_file():
        raise SystemExit(f"Dashboard configuration not found: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    calibration_path = race_path.with_suffix(".calibration")
    if not calibration_path.is_file():
        raise SystemExit(f"Calibration file not found: {calibration_path}")

    with calibration_path.open(encoding="utf-8") as f:
        calibration = json.load(f)

    if "slope" not in calibration or "offset" not in calibration:
        raise SystemExit(f"Calibration lacks slope/offset: {calibration_path}")

    race_data = RaceData(race_path)

    root = tk.Tk()
    dashboard = Dashboard(
        root, race_data, calibration, args.socket,
        video_path, config, args.track
    )
    dashboard.sync_state = Path(args.sync_state) if args.sync_state else None
    dashboard.publish_sync()
    dashboard.config_path = config_path
    root.mainloop()


if __name__ == "__main__":
    main()

