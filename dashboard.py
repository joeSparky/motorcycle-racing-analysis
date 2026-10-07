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


class ExpressionEvaluator:
    """Safely evaluate arithmetic expressions using values from one CSV row."""

    ALLOWED_BINOPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }
    ALLOWED_UNARY = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    def __init__(self, fields):
        self.fields = list(fields)
        # Longest first prevents a shorter column name from being substituted
        # inside a longer one.
        self.fields_by_length = sorted(self.fields, key=len, reverse=True)

    def _prepare(self, expression):
        """
        Convert CSV column references to internal variables.

        Both of these work:
            RPM / Speed
            RPM / [GPS Speed]

        Brackets are recommended for headings containing spaces or punctuation.
        """
        expression = str(expression).strip()
        values = {}
        counter = 0

        def add_field(field):
            nonlocal counter
            name = f"__c{counter}"
            counter += 1
            values[name] = field
            return name

        # First replace explicit [column name] references.
        bracket_pattern = re.compile(r"\[([^\]]+)\]")

        def bracket_replace(match):
            field = match.group(1)
            if field not in self.fields:
                raise ValueError(f"CSV column not found: {field}")
            return add_field(field)

        prepared = bracket_pattern.sub(bracket_replace, expression)

        # Then replace ordinary identifier-like CSV headings, such as RPM,
        # Speed, Throttle, BrakePressure.
        for field in self.fields_by_length:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                continue
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])"
            if re.search(pattern, prepared):
                variable = add_field(field)
                prepared = re.sub(pattern, variable, prepared)

        return prepared, values

    def evaluate(self, expression, row):
        prepared, variables = self._prepare(expression)
        tree = ast.parse(prepared, mode="eval")

        numeric_values = {}
        for variable, field in variables.items():
            raw = row.get(field)
            try:
                numeric_values[variable] = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"Non-numeric value in CSV column: {field}")

        def visit(node):
            if isinstance(node, ast.Expression):
                return visit(node.body)

            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    return float(node.value)
                raise ValueError("Only numeric constants are allowed.")

            if isinstance(node, ast.Name):
                if node.id not in numeric_values:
                    raise ValueError(f"Unknown name in expression: {node.id}")
                return numeric_values[node.id]

            if isinstance(node, ast.BinOp) and type(node.op) in self.ALLOWED_BINOPS:
                left = visit(node.left)
                right = visit(node.right)
                if isinstance(node.op, ast.Div) and right == 0:
                    return None
                return self.ALLOWED_BINOPS[type(node.op)](left, right)

            if isinstance(node, ast.UnaryOp) and type(node.op) in self.ALLOWED_UNARY:
                return self.ALLOWED_UNARY[type(node.op)](visit(node.operand))

            raise ValueError("Expression contains an unsupported operation.")

        return visit(tree)


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


class MpvConnection:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.sock = None
        self.buffer = b""
        self.request_id = 0

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def connect(self):
        self.close()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.05)
        s.connect(self.socket_path)
        self.sock = s
        self.buffer = b""

    def get_property(self, name):
        if self.sock is None:
            self.connect()

        self.request_id += 1
        rid = self.request_id
        request = {"command": ["get_property", name], "request_id": rid}
        self.sock.sendall((json.dumps(request) + "\n").encode())

        while True:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line:
                    continue
                response = json.loads(line.decode())
                if response.get("request_id") != rid:
                    continue
                if response.get("error") != "success":
                    return None
                return response.get("data")

            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("MPV closed the IPC connection.")
            self.buffer += chunk


    def command(self, *args):
        """Send an MPV command and wait for its matching reply."""
        if self.sock is None:
            self.connect()

        self.request_id += 1
        rid = self.request_id
        request = {"command": list(args), "request_id": rid}
        self.sock.sendall((json.dumps(request) + "\n").encode())

        while True:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line:
                    continue
                response = json.loads(line.decode())
                if response.get("request_id") != rid:
                    continue
                return response.get("error") == "success"

            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("MPV closed the IPC connection.")
            self.buffer += chunk


class Dashboard:
    def __init__(self, root, race_data, calibration, socket_path, video_path, config):
        self.root = root
        self.race_data = race_data
        self.slope = float(calibration["slope"])
        self.offset = float(calibration["offset"])
        self.mpv = MpvConnection(socket_path)
        self.socket_path = socket_path
        self.video_path = video_path
        self.mpv_process = None
        self.config = config
        self.expression_evaluator = ExpressionEvaluator(race_data.fields)
        self.widgets = []

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

        self.status = tk.Label(root, text="MPV is not running.")
        self.status.pack(pady=(7, 12))

        self.update_dashboard()

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
                self.expression_evaluator._prepare(expression)
                ast.parse(self.expression_evaluator._prepare(expression)[0], mode="eval")
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
            "mpv",
            "--pause",
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

            csv_target = (float(video_time) - self.offset) / self.slope
            csv_time, row = self.race_data.nearest(csv_target)

            self.video_time_label.config(text=f"Video {format_video_time(video_time)}")
            self.csv_time_label.config(text=f"CSV {csv_time:.3f} s")

            for widget in self.widgets:
                self.update_item(widget, row)

            self.status.config(text="Following MPV")
        except (OSError, ConnectionError, json.JSONDecodeError):
            self.mpv.close()
            self.status.config(text="Waiting for MPV...")

        self.root.after(50, self.update_dashboard)


def main():
    parser = argparse.ArgumentParser(description="Configurable race video dashboard.")
    parser.add_argument("--race", help="Override $race.")
    parser.add_argument("--video", help="Override $video.")
    parser.add_argument("--config", help="Dashboard YAML file.")
    parser.add_argument("--socket", default="/tmp/mpvsocket")
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
    Dashboard(
        root, race_data, calibration, args.socket,
        video_path, config
    )
    root.mainloop()


if __name__ == "__main__":
    main()
