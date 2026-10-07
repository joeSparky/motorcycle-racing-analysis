#!/usr/bin/env python3
"""
videoCalibration.py

Interactive two-point calibration between:
  * the helmet video ($video)
  * the AiM race CSV ($race)

Steve independently seeks MPV to a recognizable physical event and moves the
dot through the GPS samples until both show the same event. CALIBRATE START
records the first pair. CALIBRATE END records the second pair and writes:

    ${race without extension}.calibration

Standard environment variables:
    $race   current race CSV
    $video  current video file

MPV IPC socket:
    /tmp/mpvsocket
"""

import argparse
import csv
import json
import math
import os
import socket
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError:
    raise SystemExit(
        "Matplotlib/Tk support is required.\n"
        "Install the Raspberry Pi packages for python3-matplotlib and python3-tk."
    )


SOCKET_PATH = "/tmp/mpvsocket"


def load_race(path):
    """Read a raw AiM export through the local aimcsv.py cleaner."""
    aimcsv = Path(__file__).resolve().parent / "aimcsv.py"
    if not aimcsv.is_file():
        raise ValueError(f"aimcsv.py not found beside videoCalibration.py: {aimcsv}")

    try:
        result = subprocess.run(
            [sys.executable, str(aimcsv), str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        raise ValueError(f"aimcsv.py failed: {detail}")

    import io
    reader = csv.DictReader(io.StringIO(result.stdout))
    fields = reader.fieldnames or []

    needed = ["Time", "GPS Latitude", "GPS Longitude"]
    missing = [x for x in needed if x not in fields]
    if missing:
        raise ValueError("Missing CSV column(s): " + ", ".join(missing))

    rows = []
    for record_number, row in enumerate(reader, start=1):
        try:
            t = float(row["Time"])
            lat = float(row["GPS Latitude"])
            lon = float(row["GPS Longitude"])
        except (TypeError, ValueError):
            continue

        if not (math.isfinite(t) and math.isfinite(lat) and math.isfinite(lon)):
            continue
        if lat == 0.0 and lon == 0.0:
            continue

        rows.append({
            "record": record_number,
            "time": t,
            "lat": lat,
            "lon": lon,
        })

    if not rows:
        raise ValueError("No usable GPS samples were found in the race CSV.")
    return rows


class Mpv:
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
        s.settimeout(0.10)
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
                raise ConnectionError("MPV closed its IPC connection.")
            self.buffer += chunk


class CalibrationApp:
    def __init__(self, root, race_path, video_path, rows, mpv, mpv_process):
        self.root = root
        self.race_path = race_path
        self.video_path = video_path
        self.rows = rows
        self.mpv = mpv
        self.mpv_process = mpv_process
        self.index = 0
        self.start_pair = None
        self.end_pair = None

        root.title("Video Calibration")
        root.geometry("900x760")

        heading = tk.Label(
            root,
            text="VIDEO / GPS CALIBRATION",
            font=("TkDefaultFont", 18, "bold"),
        )
        heading.pack(pady=(10, 2))

        tk.Label(
            root,
            text="Seek MPV to a recognizable turn, then move the GPS dot to the same event.",
        ).pack(pady=(0, 8))

        self.figure = Figure(figsize=(8.4, 5.0), dpi=100)
        self.ax = self.figure.add_subplot(111)

        lons = [r["lon"] for r in rows]
        lats = [r["lat"] for r in rows]

        self.ax.plot(lons, lats, linewidth=1)
        self.dot, = self.ax.plot(
            [rows[0]["lon"]], [rows[0]["lat"]],
            marker="o", markersize=3, linestyle="None"
        )
        self.ax.set_xlabel("GPS Longitude")
        self.ax.set_ylabel("GPS Latitude")
        self.ax.set_title("All GPS samples")
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.grid(True, alpha=0.25)

        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10)

        info = tk.Frame(root)
        info.pack(pady=(5, 4))

        self.csv_label = tk.Label(
            info, text="", font=("TkFixedFont", 12, "bold")
        )
        self.csv_label.pack()

        self.video_label = tk.Label(
            info, text="MPV: connecting...", font=("TkFixedFont", 12)
        )
        self.video_label.pack()

        controls = tk.Frame(root)
        controls.pack(pady=6)

        for text, amount in [
            ("◀◀ 100", -100),
            ("◀ 10", -10),
            ("◀ 1", -1),
            ("1 ▶", 1),
            ("10 ▶", 10),
            ("100 ▶▶", 100),
        ]:
            tk.Button(
                controls,
                text=text,
                width=9,
                command=lambda n=amount: self.move(n),
            ).pack(side="left", padx=3)

        jump_controls = tk.Frame(root)
        jump_controls.pack(pady=(2, 5))

        tk.Button(
            jump_controls,
            text="GO TO START",
            width=16,
            command=self.go_to_start,
        ).pack(side="left", padx=5)

        tk.Button(
            jump_controls,
            text="GO TO END",
            width=16,
            command=self.go_to_end,
        ).pack(side="left", padx=5)

        calibrate = tk.Frame(root)
        calibrate.pack(pady=8)

        self.start_button = tk.Button(
            calibrate,
            text="CALIBRATE START",
            width=20,
            height=2,
            command=self.calibrate_start,
        )
        self.start_button.pack(side="left", padx=10)

        self.end_button = tk.Button(
            calibrate,
            text="CALIBRATE END",
            width=20,
            height=2,
            command=self.calibrate_end,
        )
        self.end_button.pack(side="left", padx=10)

        self.status = tk.Label(root, text="Start point has not been set.")
        self.status.pack(pady=(0, 10))

        # Keyboard GPS-dot movement. MPV keeps its own normal keyboard controls.
        root.bind("<Left>", lambda e: self.move(-1))
        root.bind("<Right>", lambda e: self.move(1))
        root.bind("<Shift-Left>", lambda e: self.move(-10))
        root.bind("<Shift-Right>", lambda e: self.move(10))
        root.bind("<Control-Left>", lambda e: self.move(-100))
        root.bind("<Control-Right>", lambda e: self.move(100))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_dot()
        self.poll_mpv()

    def current(self):
        return self.rows[self.index]

    def move(self, amount):
        self.index = max(0, min(len(self.rows) - 1, self.index + amount))
        self.refresh_dot()

    def go_to_start(self):
        self.index = 0
        self.refresh_dot()

    def go_to_end(self):
        self.index = len(self.rows) - 1
        self.refresh_dot()

    def refresh_dot(self):
        row = self.current()
        self.dot.set_data([row["lon"]], [row["lat"]])
        self.csv_label.config(
            text=(
                f"GPS sample {self.index + 1:,} / {len(self.rows):,}    "
                f"CSV Time {row['time']:.3f} s    Record {row['record']:,}"
            )
        )
        self.canvas.draw_idle()

    def video_time(self):
        try:
            value = self.mpv.get_property("time-pos")
            if value is None:
                raise ConnectionError
            return float(value)
        except (OSError, ConnectionError, json.JSONDecodeError):
            self.mpv.close()
            return None

    def poll_mpv(self):
        value = self.video_time()
        if value is None:
            self.video_label.config(text="MPV: waiting for connection...")
        else:
            self.video_label.config(text=f"MPV Video Time {value:.3f} s")
        self.root.after(100, self.poll_mpv)

    def capture_pair(self):
        video_time = self.video_time()
        if video_time is None:
            messagebox.showerror(
                "MPV not available",
                "Could not read the current MPV video time."
            )
            return None

        row = self.current()
        return {
            "record": row["record"],
            "csvTime": row["time"],
            "videoTime": video_time,
            "latitude": row["lat"],
            "longitude": row["lon"],
        }

    def calibrate_start(self):
        pair = self.capture_pair()
        if pair is None:
            return
        self.start_pair = pair
        self.status.config(
            text=(
                f"START set: CSV {pair['csvTime']:.3f} s  "
                f"↔ Video {pair['videoTime']:.3f} s"
            )
        )

    def calibrate_end(self):
        if self.start_pair is None:
            messagebox.showwarning(
                "Set start first",
                "Set CALIBRATE START before CALIBRATE END."
            )
            return

        pair = self.capture_pair()
        if pair is None:
            return

        if pair["csvTime"] == self.start_pair["csvTime"]:
            messagebox.showerror(
                "Invalid calibration",
                "Start and end CSV times cannot be identical."
            )
            return

        self.end_pair = pair
        self.save_calibration()

    def save_calibration(self):
        a = self.start_pair
        b = self.end_pair

        slope = (b["videoTime"] - a["videoTime"]) / (
            b["csvTime"] - a["csvTime"]
        )
        offset = a["videoTime"] - slope * a["csvTime"]

        output = self.race_path.with_suffix(".calibration")
        data = {
            "race": str(self.race_path),
            "video": str(self.video_path),
            "slope": slope,
            "offset": offset,
            "pointA": a,
            "pointB": b,
        }

        with output.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.status.config(
            text=(
                f"CALIBRATION SAVED — slope {slope:.12f}, "
                f"offset {offset:.6f}"
            )
        )

        messagebox.showinfo(
            "Calibration saved",
            f"Saved:\n{output}\n\n"
            f"Start: CSV {a['csvTime']:.3f} ↔ Video {a['videoTime']:.3f}\n"
            f"End:   CSV {b['csvTime']:.3f} ↔ Video {b['videoTime']:.3f}"
        )

    def close(self):
        self.mpv.close()
        if self.mpv_process and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
        self.root.destroy()


def launch_mpv(video_path, socket_path):
    try:
        Path(socket_path).unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [
        "mpv",
        "--pause",
        "--no-audio",
        "--no-fullscreen",
        "--geometry=640x360",
        f"--input-ipc-server={socket_path}",
        str(video_path),
    ]

    try:
        process = subprocess.Popen(cmd)
    except FileNotFoundError:
        raise SystemExit("mpv was not found on PATH.")

    for _ in range(50):
        if Path(socket_path).exists():
            return process
        if process.poll() is not None:
            raise SystemExit("mpv exited before its IPC socket was created.")
        time.sleep(0.1)

    process.terminate()
    raise SystemExit("Could not connect to mpv.")


def main():
    parser = argparse.ArgumentParser(
        description="Interactively calibrate helmet video to AiM GPS data."
    )
    parser.add_argument("--race", help="Override the $race CSV.")
    parser.add_argument("--video", help="Override the $video file.")
    parser.add_argument(
        "--socket", default=SOCKET_PATH,
        help=f"MPV IPC socket (default: {SOCKET_PATH})"
    )
    args = parser.parse_args()

    race_value = args.race or os.environ.get("race")
    video_value = args.video or os.environ.get("video")

    if not race_value:
        raise SystemExit("Race is not set. Use: source setRace FILE")
    if not video_value:
        raise SystemExit("Video is not set. Use: source setVideo VIDEOFILE")

    race_path = Path(race_value).expanduser().resolve()
    video_path = Path(video_value).expanduser().resolve()

    if not race_path.is_file():
        raise SystemExit(f"Race file not found: {race_path}")
    if not video_path.is_file():
        raise SystemExit(f"Video file not found: {video_path}")

    try:
        rows = load_race(race_path)
    except ValueError as e:
        raise SystemExit(str(e))

    process = launch_mpv(video_path, args.socket)
    mpv = Mpv(args.socket)

    root = tk.Tk()
    CalibrationApp(root, race_path, video_path, rows, mpv, process)
    root.mainloop()


if __name__ == "__main__":
    main()
